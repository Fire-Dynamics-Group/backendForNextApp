"""Tests for the i-macs -> upload-canvas MACS results hand-off.

The i-macs Windows desktop app (Tauri + Python sidecar driving MACS+) POSTs
its reliability results ("fd-macs-reliability/1" envelope, i-macs issue #48)
against an upload-canvas project so the time-equivalence popup can read
critical temperature and section factor (Ap/V) automatically.

Contract under test:

  * `/imacs/*` is protected ONLY by a shared app key in `X-IMACS-App-Key`,
    read from env `IMACS_APP_KEY` at request time.
      - env unset/empty  -> every request rejected with 503 (service not
        configured), even if a header is sent (fail closed)
      - header missing   -> 401
      - header wrong     -> 403
  * The app key is NOT accepted anywhere else: the upload-canvas read
    endpoint `GET /projects/{id}/macs-results` stays on `current_user`.
  * Envelope is validated strictly (unknown schema / extra fields -> 422).

Real HTTP path: the FastAPI app from main.py through httpx ASGITransport,
with the DB dependency overridden onto a throwaway SQLite file (same pattern
as test_projects.py). Entra bearer tokens are minted with the helpers from
test_auth.py (throwaway RSA key standing in for Microsoft's JWKS).
"""
import os
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Unique filename so this module never collides with other SQLite-backed tests.
TEST_DB_FILE = "./test_imacs_macs_results.db"
TEST_DATABASE_URL = f"sqlite+aiosqlite:///{TEST_DB_FILE}"

# Prevent a real DB connection when main.py is imported.
os.environ["DATABASE_URL"] = ""

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from auth import entra
from database import Base
from models.db_models import Project
from test_auth import _FakeJwks, entra_token

APP_KEY = "test-imacs-app-key-not-a-real-secret"
KEY_HEADER = "X-IMACS-App-Key"

VALID_ENVELOPE = {
    "schema": "fd-macs-reliability/1",
    "critical_temp": 690,
    "governing_side": "B",
    "section": "IPE_500",
    "exposure": "3-sided",
    "section_factor": 152,
}

VALID_BODY = {
    **VALID_ENVELOPE,
    "windows_user": "jbloggs",
    "client_timestamp": "2026-11-02T13:55:00Z",
}


def key_headers(key: str = APP_KEY) -> dict[str, str]:
    return {KEY_HEADER: key}


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# --- Fixtures ---


@pytest.fixture(autouse=True)
def imacs_env(monkeypatch):
    """App key configured; Entra enforcement ON, to prove /imacs/* does not
    depend on (or get blocked by) the per-user sign-in."""
    monkeypatch.setenv("IMACS_APP_KEY", APP_KEY)
    monkeypatch.setenv("AUTH_MODE", "enforce")


@pytest_asyncio.fixture
async def test_engine():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()
    if os.path.exists(TEST_DB_FILE):
        os.remove(TEST_DB_FILE)


@pytest_asyncio.fixture
async def session_factory(test_engine):
    return async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture
async def client(test_engine, session_factory):
    import database
    from main import app

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[database.get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def make_project(session_factory):
    """Insert a project straight into the DB (the /projects API needs a bearer
    in enforce mode and is not what is under test here)."""

    async def _make(name: str = "TEQ project", mode: str = "timeEq") -> str:
        async with session_factory() as session:
            project = Project(name=name, mode=mode)
            session.add(project)
            await session.commit()
            await session.refresh(project)
            return str(project.id)

    return _make


@pytest.fixture(scope="module")
def signing_keys():
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    return private_pem, private.public_key()


@pytest.fixture
def user_headers(monkeypatch, signing_keys):
    """Authorization header carrying a valid (fake-JWKS) Entra access token."""
    private_pem, public = signing_keys
    monkeypatch.setattr(entra, "_jwks", _FakeJwks(public))
    return bearer(entra_token(private_pem))


# --- 1. App key: missing -> 401, wrong -> 403 ---


@pytest.mark.asyncio
async def test_post_without_key_header_401(client: AsyncClient, make_project):
    pid = await make_project()
    resp = await client.post(f"/imacs/projects/{pid}/macs-results", json=VALID_BODY)
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_post_with_wrong_key_403(client: AsyncClient, make_project):
    pid = await make_project()
    resp = await client.post(
        f"/imacs/projects/{pid}/macs-results", json=VALID_BODY, headers=key_headers("wrong-key")
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_project_lookup_without_key_header_401(client: AsyncClient, make_project):
    await make_project()
    resp = await client.get("/imacs/projects")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_project_lookup_with_wrong_key_403(client: AsyncClient, make_project):
    await make_project()
    resp = await client.get("/imacs/projects", headers=key_headers("wrong-key"))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_rejected_post_stores_nothing(client: AsyncClient, make_project, user_headers):
    pid = await make_project()
    await client.post(f"/imacs/projects/{pid}/macs-results", json=VALID_BODY)
    await client.post(
        f"/imacs/projects/{pid}/macs-results", json=VALID_BODY, headers=key_headers("wrong-key")
    )
    resp = await client.get(f"/projects/{pid}/macs-results", headers=user_headers)
    assert resp.status_code == 200
    assert resp.json() == []


# --- 2. IMACS_APP_KEY unset/empty -> fail closed (503) ---


@pytest.mark.asyncio
@pytest.mark.parametrize("env_value", [None, ""])
async def test_unset_or_empty_app_key_env_rejects_everything_503(
    client: AsyncClient, make_project, monkeypatch, env_value
):
    pid = await make_project()
    if env_value is None:
        monkeypatch.delenv("IMACS_APP_KEY", raising=False)
    else:
        monkeypatch.setenv("IMACS_APP_KEY", env_value)

    # Header sent (even an empty one that would "match" an empty env) is still rejected.
    for headers in (key_headers(APP_KEY), key_headers(""), {}):
        post = await client.post(
            f"/imacs/projects/{pid}/macs-results", json=VALID_BODY, headers=headers
        )
        assert post.status_code == 503
        listing = await client.get("/imacs/projects", headers=headers)
        assert listing.status_code == 503


# --- 3. Valid envelope with correct key -> 201 and stored ---


@pytest.mark.asyncio
async def test_valid_envelope_201_stored_and_visible_via_read_get(
    client: AsyncClient, make_project, user_headers
):
    pid = await make_project()

    resp = await client.post(
        f"/imacs/projects/{pid}/macs-results", json=VALID_BODY, headers=key_headers()
    )
    assert resp.status_code == 201, resp.text
    stored = resp.json()
    assert stored["id"]
    assert stored["project_id"] == pid
    assert stored["critical_temp"] == 690
    assert stored["section_factor"] == 152
    assert stored["governing_side"] == "B"
    assert stored["section"] == "IPE_500"
    assert stored["exposure"] == "3-sided"
    assert stored["windows_user"] == "jbloggs"
    assert stored["client_timestamp"].startswith("2026-11-02T13:55:00")
    assert stored["received_at"]  # server-side timestamp, not client-supplied

    read = await client.get(f"/projects/{pid}/macs-results", headers=user_headers)
    assert read.status_code == 200
    rows = read.json()
    assert [r["id"] for r in rows] == [stored["id"]]
    assert rows[0]["critical_temp"] == 690
    assert rows[0]["section_factor"] == 152
    assert rows[0]["windows_user"] == "jbloggs"


@pytest.mark.asyncio
async def test_optional_client_metadata_accepted_and_returned(
    client: AsyncClient, make_project
):
    pid = await make_project()
    body = {
        **VALID_BODY,
        "client_version": "0.4.2",
        "run_id": "run-0001",
        "label": "Level 3 perimeter beam",
    }
    resp = await client.post(
        f"/imacs/projects/{pid}/macs-results", json=body, headers=key_headers()
    )
    assert resp.status_code == 201, resp.text
    stored = resp.json()
    assert stored["client_version"] == "0.4.2"
    assert stored["run_id"] == "run-0001"
    assert stored["label"] == "Level 3 perimeter beam"


@pytest.mark.asyncio
async def test_read_get_lists_newest_first(client: AsyncClient, make_project, user_headers):
    pid = await make_project()
    first = await client.post(
        f"/imacs/projects/{pid}/macs-results",
        json={**VALID_BODY, "critical_temp": 600},
        headers=key_headers(),
    )
    second = await client.post(
        f"/imacs/projects/{pid}/macs-results",
        json={**VALID_BODY, "critical_temp": 700},
        headers=key_headers(),
    )
    assert first.status_code == 201 and second.status_code == 201

    rows = (await client.get(f"/projects/{pid}/macs-results", headers=user_headers)).json()
    assert [r["id"] for r in rows] == [second.json()["id"], first.json()["id"]]


# --- 4. Invalid envelope -> 422 ---

_BAD_BODIES = {
    "bad schema string": {**VALID_BODY, "schema": "fd-macs-reliability/2"},
    "empty schema string": {**VALID_BODY, "schema": ""},
    "missing schema": {k: v for k, v in VALID_BODY.items() if k != "schema"},
    "missing critical_temp": {k: v for k, v in VALID_BODY.items() if k != "critical_temp"},
    "zero critical_temp": {**VALID_BODY, "critical_temp": 0},
    "negative critical_temp": {**VALID_BODY, "critical_temp": -5},
    "absurd critical_temp": {**VALID_BODY, "critical_temp": 5000},
    "non-numeric critical_temp": {**VALID_BODY, "critical_temp": "hot"},
    "negative section_factor": {**VALID_BODY, "section_factor": -1},
    "zero section_factor": {**VALID_BODY, "section_factor": 0},
    "absurd section_factor": {**VALID_BODY, "section_factor": 100000},
    "missing section_factor": {k: v for k, v in VALID_BODY.items() if k != "section_factor"},
    "bad governing_side": {**VALID_BODY, "governing_side": "E"},
    "lowercase governing_side": {**VALID_BODY, "governing_side": "b"},
    "empty section": {**VALID_BODY, "section": ""},
    "bad exposure": {**VALID_BODY, "exposure": "2-sided"},
    "extra field": {**VALID_BODY, "surprise": "nope"},
    "missing windows_user": {k: v for k, v in VALID_BODY.items() if k != "windows_user"},
    "empty windows_user": {**VALID_BODY, "windows_user": ""},
    "missing client_timestamp": {k: v for k, v in VALID_BODY.items() if k != "client_timestamp"},
    "bad client_timestamp": {**VALID_BODY, "client_timestamp": "yesterday-ish"},
}


@pytest.mark.asyncio
@pytest.mark.parametrize("body", list(_BAD_BODIES.values()), ids=list(_BAD_BODIES.keys()))
async def test_invalid_envelope_422(client: AsyncClient, make_project, user_headers, body):
    pid = await make_project()
    resp = await client.post(
        f"/imacs/projects/{pid}/macs-results", json=body, headers=key_headers()
    )
    assert resp.status_code == 422, resp.text

    # ...and nothing was stored.
    rows = (await client.get(f"/projects/{pid}/macs-results", headers=user_headers)).json()
    assert rows == []


# --- 5. Unknown project -> 404 ---


@pytest.mark.asyncio
async def test_post_to_missing_project_404(client: AsyncClient):
    resp = await client.post(
        f"/imacs/projects/{uuid.uuid4()}/macs-results", json=VALID_BODY, headers=key_headers()
    )
    assert resp.status_code == 404
    # A real "project missing" answer, not the router's generic unrouted 404.
    assert "project" in resp.json()["detail"].lower()


# --- 6. Read endpoint: per-project scoping, bearer only (key not accepted) ---


@pytest.mark.asyncio
async def test_read_get_scoped_to_project_with_entra_bearer(
    client: AsyncClient, make_project, user_headers
):
    a = await make_project("Project A")
    b = await make_project("Project B")

    a_post = await client.post(
        f"/imacs/projects/{a}/macs-results",
        json={**VALID_BODY, "critical_temp": 650},
        headers=key_headers(),
    )
    b_post = await client.post(
        f"/imacs/projects/{b}/macs-results",
        json={**VALID_BODY, "critical_temp": 720, "section": "HEB_300"},
        headers=key_headers(),
    )
    assert a_post.status_code == 201 and b_post.status_code == 201

    rows_a = (await client.get(f"/projects/{a}/macs-results", headers=user_headers)).json()
    assert [r["id"] for r in rows_a] == [a_post.json()["id"]]
    assert all(r["project_id"] == a for r in rows_a)
    assert b_post.json()["id"] not in {r["id"] for r in rows_a}

    rows_b = (await client.get(f"/projects/{b}/macs-results", headers=user_headers)).json()
    assert [r["id"] for r in rows_b] == [b_post.json()["id"]]


@pytest.mark.asyncio
async def test_read_get_with_only_app_key_401(client: AsyncClient, make_project):
    pid = await make_project()
    await client.post(
        f"/imacs/projects/{pid}/macs-results", json=VALID_BODY, headers=key_headers()
    )

    resp = await client.get(f"/projects/{pid}/macs-results", headers=key_headers())
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_read_get_without_any_credentials_401(client: AsyncClient, make_project):
    pid = await make_project()
    resp = await client.get(f"/projects/{pid}/macs-results")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_app_key_not_accepted_on_other_project_routes(client: AsyncClient, make_project):
    await make_project()
    resp = await client.get("/projects", headers=key_headers())
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_bearer_alone_does_not_open_imacs_endpoints(
    client: AsyncClient, make_project, user_headers
):
    pid = await make_project()
    post = await client.post(
        f"/imacs/projects/{pid}/macs-results", json=VALID_BODY, headers=user_headers
    )
    assert post.status_code == 401
    listing = await client.get("/imacs/projects", headers=user_headers)
    assert listing.status_code == 401


# --- 7. GET /imacs/projects ---


@pytest.mark.asyncio
async def test_imacs_projects_lists_time_eq_projects_with_key(client: AsyncClient, make_project):
    teq = await make_project("TEQ one", mode="timeEq")
    fds = await make_project("FDS one", mode="fdsGen")

    resp = await client.get("/imacs/projects", params={"mode": "timeEq"}, headers=key_headers())
    assert resp.status_code == 200
    rows = resp.json()
    ids = {r["id"] for r in rows}
    assert teq in ids
    assert fds not in ids
    assert all(r["mode"] == "timeEq" for r in rows)
    row = next(r for r in rows if r["id"] == teq)
    assert row["name"] == "TEQ one"
    assert row["updated_at"]
    # Minimal projection only: no settings / floors leaking to the app-key caller.
    assert set(row) == {"id", "name", "mode", "updated_at"}


@pytest.mark.asyncio
async def test_imacs_projects_search_query(client: AsyncClient, make_project):
    wanted = await make_project("Tower Block Alpha", mode="timeEq")
    other = await make_project("Warehouse Beta", mode="timeEq")

    resp = await client.get(
        "/imacs/projects", params={"mode": "timeEq", "q": "tower"}, headers=key_headers()
    )
    assert resp.status_code == 200
    ids = {r["id"] for r in resp.json()}
    assert wanted in ids
    assert other not in ids
