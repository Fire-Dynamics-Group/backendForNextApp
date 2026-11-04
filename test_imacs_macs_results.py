"""Tests for the reworked i-macs <-> upload-canvas MACs link and run history.

Model:
  * i-macs desktop app can run before any upload-canvas project exists.
  * Handoffs: POST /imacs/handoffs (app key) -> {handoff_id, expires_at}.
    GET /handoffs/{id} (current_user/Entra) lets upload-canvas prefill.
    Claim on project create (POST /projects with handoff_id) or via
    POST /projects/{id}/macs-handoffs/{handoff_id}/claim.
  * Run history: POST /imacs/projects/{id}/macs-runs (app key) adds a run to an
    existing project. Full history is returned newest first via
    GET /projects/{id}/macs-runs (current_user).
  * Job link: client-generated imacs_job_id mapped to project_id. Endpoints to
    link, unlink, and relink.
  * Summary: GET /imacs/jobs/{imacs_job_id}/summary (app key) returns linked project
    id and name, last_sent_at, and the latest time-eq outcome stored on the project
    (or null if not stored).
  * App key works only on /imacs/*; Entra / current_user on browser routes.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

TEST_DB_FILE = "./test_imacs_macs_results.db"
TEST_DATABASE_URL = f"sqlite+aiosqlite:///{TEST_DB_FILE}"

os.environ["DATABASE_URL"] = ""

from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402

from auth import entra  # noqa: E402
from database import Base  # noqa: E402
from models.db_models import Project  # noqa: E402
from test_auth import _FakeJwks, entra_token  # noqa: E402

APP_KEY = "test-imacs-app-key-not-a-real-secret"
KEY_HEADER = "X-IMACS-App-Key"

VALID_RUN = {
    "schema": "fd-macs-reliability/1",
    "critical_temp": 690,
    "governing_side": "B",
    "section": "IPE_500",
    "exposure": "3-sided",
    "section_factor": 152,
    "windows_user": "jbloggs",
    "machine_name": "WORKSTATION-01",
    "client_timestamp": "2026-11-02T13:55:00Z",
    "client_version": "i-macs 0.9.0",
    "run_id": "run-xyz-123",
    "label": "Perimeter beam B1",
    "inputs": {"span1": 9.0, "span2": 6.0, "numbeam": 2},
    "imacs_job_id": "job-777",
}


def key_headers(key: str = APP_KEY) -> dict[str, str]:
    return {KEY_HEADER: key}


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def imacs_env(monkeypatch):
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
    async def _make(
        name: str = "TEQ project", mode: str = "timeEq", settings: dict | None = None
    ) -> str:
        async with session_factory() as session:
            project = Project(name=name, mode=mode, settings=settings or {})
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
    private_pem, public = signing_keys
    monkeypatch.setattr(entra, "_jwks", _FakeJwks(public))
    return bearer(entra_token(private_pem))


# ==============================================================================
# 1. Auth enforcement on /imacs/* (App key required, wrong -> 403, unset -> 503)
# ==============================================================================


@pytest.mark.asyncio
async def test_imacs_routes_without_key_header_401(client: AsyncClient, make_project):
    pid = await make_project()
    assert (await client.post(f"/imacs/projects/{pid}/macs-runs", json=VALID_RUN)).status_code == 401
    assert (await client.post("/imacs/handoffs", json=VALID_RUN)).status_code == 401
    assert (await client.get("/imacs/projects")).status_code == 401
    assert (await client.get("/imacs/jobs/job-1/summary")).status_code == 401
    assert (
        await client.post("/imacs/jobs/job-1/link", json={"project_id": pid})
    ).status_code == 401
    assert (await client.delete("/imacs/jobs/job-1/link")).status_code == 401


@pytest.mark.asyncio
async def test_imacs_routes_with_wrong_key_403(client: AsyncClient, make_project):
    pid = await make_project()
    wrong = key_headers("wrong-key")
    assert (
        await client.post(f"/imacs/projects/{pid}/macs-runs", json=VALID_RUN, headers=wrong)
    ).status_code == 403
    assert (await client.post("/imacs/handoffs", json=VALID_RUN, headers=wrong)).status_code == 403
    assert (await client.get("/imacs/projects", headers=wrong)).status_code == 403
    assert (await client.get("/imacs/jobs/job-1/summary", headers=wrong)).status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("env_val", [None, ""])
async def test_unset_or_empty_app_key_env_rejects_everything_503(
    client: AsyncClient, make_project, monkeypatch, env_val
):
    pid = await make_project()
    if env_val is None:
        monkeypatch.delenv("IMACS_APP_KEY", raising=False)
    else:
        monkeypatch.setenv("IMACS_APP_KEY", env_val)

    for h in (key_headers(APP_KEY), key_headers(""), {}):
        assert (
            await client.post(f"/imacs/projects/{pid}/macs-runs", json=VALID_RUN, headers=h)
        ).status_code == 503
        assert (await client.post("/imacs/handoffs", json=VALID_RUN, headers=h)).status_code == 503
        assert (await client.get("/imacs/projects", headers=h)).status_code == 503


# ==============================================================================
# 2. POST /imacs/projects/{id}/macs-runs & GET /projects/{id}/macs-runs (History)
# ==============================================================================


@pytest.mark.asyncio
async def test_post_macs_run_stores_record_with_history(
    client: AsyncClient, make_project, user_headers
):
    pid = await make_project()

    # Post run 1
    run1_payload = {**VALID_RUN, "critical_temp": 620.0, "label": "Run 1"}
    r1 = await client.post(
        f"/imacs/projects/{pid}/macs-runs", json=run1_payload, headers=key_headers()
    )
    assert r1.status_code == 201, r1.text
    d1 = r1.json()
    assert d1["id"]
    assert d1["project_id"] == pid
    assert d1["critical_temp"] == 620.0
    assert d1["section_factor"] == 152.0
    assert d1["governing_side"] == "B"
    assert d1["section"] == "IPE_500"
    assert d1["exposure"] == "3-sided"
    assert d1["windows_user"] == "jbloggs"
    assert d1["machine_name"] == "WORKSTATION-01"
    assert d1["inputs"] == {"span1": 9.0, "span2": 6.0, "numbeam": 2}
    assert d1["label"] == "Run 1"
    assert d1["received_at"]

    # Post run 2 on the same project
    run2_payload = {**VALID_RUN, "critical_temp": 710.0, "label": "Run 2"}
    r2 = await client.post(
        f"/imacs/projects/{pid}/macs-runs", json=run2_payload, headers=key_headers()
    )
    assert r2.status_code == 201
    d2 = r2.json()

    # Web app reads history: newest first
    read = await client.get(f"/projects/{pid}/macs-runs", headers=user_headers)
    assert read.status_code == 200
    history = read.json()
    assert len(history) == 2
    assert [h["id"] for h in history] == [d2["id"], d1["id"]]
    assert history[0]["critical_temp"] == 710.0
    assert history[1]["critical_temp"] == 620.0


@pytest.mark.asyncio
async def test_macs_run_rejects_missing_project_404(client: AsyncClient):
    missing_id = uuid.uuid4()
    resp = await client.post(
        f"/imacs/projects/{missing_id}/macs-runs", json=VALID_RUN, headers=key_headers()
    )
    assert resp.status_code == 404
    assert "project" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_get_macs_runs_without_user_auth_401(client: AsyncClient, make_project):
    pid = await make_project()
    # Unauthenticated
    assert (await client.get(f"/projects/{pid}/macs-runs")).status_code == 401
    # App key alone is NOT accepted on user route
    assert (
        await client.get(f"/projects/{pid}/macs-runs", headers=key_headers())
    ).status_code == 401


# ==============================================================================
# 3. Validation: strict schema & field validation (422)
# ==============================================================================

_INVALID_RUN_CASES = {
    "unknown schema": {**VALID_RUN, "schema": "fd-macs-reliability/99"},
    "missing schema": {k: v for k, v in VALID_RUN.items() if k != "schema"},
    "missing critical_temp": {k: v for k, v in VALID_RUN.items() if k != "critical_temp"},
    "zero critical_temp": {**VALID_RUN, "critical_temp": 0},
    "negative critical_temp": {**VALID_RUN, "critical_temp": -10},
    "over 1200 critical_temp": {**VALID_RUN, "critical_temp": 1201},
    "non-numeric critical_temp": {**VALID_RUN, "critical_temp": "600"},
    "zero section_factor": {**VALID_RUN, "section_factor": 0},
    "negative section_factor": {**VALID_RUN, "section_factor": -5},
    "over 1000 section_factor": {**VALID_RUN, "section_factor": 1001},
    "invalid governing_side": {**VALID_RUN, "governing_side": "E"},
    "lowercase governing_side": {**VALID_RUN, "governing_side": "b"},
    "empty section": {**VALID_RUN, "section": ""},
    "invalid exposure": {**VALID_RUN, "exposure": "2-sided"},
    "empty windows_user": {**VALID_RUN, "windows_user": ""},
    "missing client_timestamp": {k: v for k, v in VALID_RUN.items() if k != "client_timestamp"},
    "bad client_timestamp": {**VALID_RUN, "client_timestamp": "not-a-date"},
    "unrecognized extra field": {**VALID_RUN, "disallowed_extra_field": "bad"},
}


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", list(_INVALID_RUN_CASES.values()), ids=list(_INVALID_RUN_CASES.keys()))
async def test_invalid_run_rejected_422(client: AsyncClient, make_project, payload):
    pid = await make_project()
    resp = await client.post(
        f"/imacs/projects/{pid}/macs-runs", json=payload, headers=key_headers()
    )
    assert resp.status_code == 422


# ==============================================================================
# 4. Handoffs: POST /imacs/handoffs -> GET /handoffs/{id} -> Claiming
# ==============================================================================


@pytest.mark.asyncio
async def test_handoff_lifecycle_and_claim_on_project_create(
    client: AsyncClient, user_headers
):
    # 1. i-macs creates a handoff
    create_resp = await client.post(
        "/imacs/handoffs",
        json={**VALID_RUN, "critical_temp": 680.0, "imacs_job_id": "job-handoff-1"},
        headers=key_headers(),
    )
    assert create_resp.status_code == 201, create_resp.text
    hdata = create_resp.json()
    assert "handoff_id" in hdata
    assert "expires_at" in hdata
    hid = hdata["handoff_id"]

    # 2. upload-canvas inspects handoff via GET /handoffs/{id} (current_user)
    get_resp = await client.get(f"/handoffs/{hid}", headers=user_headers)
    assert get_resp.status_code == 200, get_resp.text
    hdetail = get_resp.json()
    assert hdetail["handoff_id"] == hid
    assert hdetail["imacs_job_id"] == "job-handoff-1"
    run_info = hdetail["run"]
    assert run_info["critical_temp"] == 680.0
    assert run_info["section"] == "IPE_500"

    # GET /handoffs without auth is 401; with app key is 401
    assert (await client.get(f"/handoffs/{hid}")).status_code == 401
    assert (await client.get(f"/handoffs/{hid}", headers=key_headers())).status_code == 401

    # 3. upload-canvas creates project pre-filling from handoff and claims it
    proj_resp = await client.post(
        "/projects",
        json={"name": "Handoff Created Project", "mode": "timeEq", "handoff_id": hid},
        headers=user_headers,
    )
    assert proj_resp.status_code == 201, proj_resp.text
    pid = proj_resp.json()["id"]

    # Check that run is now attached to this project
    runs_resp = await client.get(f"/projects/{pid}/macs-runs", headers=user_headers)
    assert runs_resp.status_code == 200
    runs = runs_resp.json()
    assert len(runs) == 1
    assert runs[0]["project_id"] == pid
    assert runs[0]["critical_temp"] == 680.0

    # Job link is recorded!
    sum_resp = await client.get(
        "/imacs/jobs/job-handoff-1/summary", headers=key_headers()
    )
    assert sum_resp.status_code == 200
    summary = sum_resp.json()
    assert summary is not None
    assert summary["project_id"] == pid
    assert summary["project_name"] == "Handoff Created Project"

    # Cannot claim already claimed handoff
    claim_again = await client.post(
        f"/projects/{pid}/macs-handoffs/{hid}/claim", headers=user_headers
    )
    assert claim_again.status_code == 409


@pytest.mark.asyncio
async def test_claim_handoff_onto_existing_project(
    client: AsyncClient, make_project, user_headers
):
    pid = await make_project("Existing Project")

    # Create handoff
    create_resp = await client.post(
        "/imacs/handoffs",
        json={**VALID_RUN, "critical_temp": 640.0, "imacs_job_id": "job-handoff-2"},
        headers=key_headers(),
    )
    assert create_resp.status_code == 201
    hid = create_resp.json()["handoff_id"]

    # Claim onto existing project
    claim_resp = await client.post(
        f"/projects/{pid}/macs-handoffs/{hid}/claim", headers=user_headers
    )
    assert claim_resp.status_code == 200, claim_resp.text
    claimed_run = claim_resp.json()
    assert claimed_run["project_id"] == pid
    assert claimed_run["critical_temp"] == 640.0

    # Verify run is in project history
    runs_resp = await client.get(f"/projects/{pid}/macs-runs", headers=user_headers)
    assert runs_resp.status_code == 200
    assert len(runs_resp.json()) == 1

    # Verify link is recorded
    sum_resp = await client.get(
        "/imacs/jobs/job-handoff-2/summary", headers=key_headers()
    )
    assert sum_resp.status_code == 200
    summary = sum_resp.json()
    assert summary["project_id"] == pid


@pytest.mark.asyncio
async def test_claim_missing_handoff_or_project_404(
    client: AsyncClient, make_project, user_headers
):
    pid = await make_project()
    random_hid = uuid.uuid4()
    # Unknown handoff
    r1 = await client.post(
        f"/projects/{pid}/macs-handoffs/{random_hid}/claim", headers=user_headers
    )
    assert r1.status_code == 404

    # Create valid handoff
    create_resp = await client.post(
        "/imacs/handoffs", json=VALID_RUN, headers=key_headers()
    )
    hid = create_resp.json()["handoff_id"]

    # Unknown project
    r2 = await client.post(
        f"/projects/{uuid.uuid4()}/macs-handoffs/{hid}/claim", headers=user_headers
    )
    assert r2.status_code == 404


# ==============================================================================
# 5. Job links: link, unlink, relink & summary endpoint
# ==============================================================================


@pytest.mark.asyncio
async def test_job_summary_empty_when_not_linked(client: AsyncClient):
    resp = await client.get("/imacs/jobs/unlinked-job/summary", headers=key_headers())
    assert resp.status_code == 200
    assert resp.json() is None


@pytest.mark.asyncio
async def test_job_link_unlink_and_relink(client: AsyncClient, make_project):
    p1 = await make_project("Building 1")
    p2 = await make_project("Building 2")
    job_id = "desktop-job-99"

    # Link to Building 1
    link_resp = await client.post(
        f"/imacs/jobs/{job_id}/link", json={"project_id": p1}, headers=key_headers()
    )
    assert link_resp.status_code == 200
    assert link_resp.json()["project_id"] == p1

    # Summary reflects Building 1
    s1 = await client.get(f"/imacs/jobs/{job_id}/summary", headers=key_headers())
    assert s1.status_code == 200
    assert s1.json()["project_id"] == p1
    assert s1.json()["project_name"] == "Building 1"
    assert s1.json()["last_sent_at"] is None

    # Relink to Building 2
    relink_resp = await client.post(
        f"/imacs/jobs/{job_id}/link", json={"project_id": p2}, headers=key_headers()
    )
    assert relink_resp.status_code == 200
    assert relink_resp.json()["project_id"] == p2

    s2 = await client.get(f"/imacs/jobs/{job_id}/summary", headers=key_headers())
    assert s2.json()["project_id"] == p2
    assert s2.json()["project_name"] == "Building 2"

    # Unlink
    unlink_resp = await client.delete(f"/imacs/jobs/{job_id}/link", headers=key_headers())
    assert unlink_resp.status_code == 200

    s3 = await client.get(f"/imacs/jobs/{job_id}/summary", headers=key_headers())
    assert s3.json() is None


@pytest.mark.asyncio
async def test_job_summary_reports_last_sent_at_and_stored_time_eq_outcome(
    client: AsyncClient, make_project
):
    outcome_data = {
        "reliability": 0.985,
        "reliabilityPercent": 98.5,
        "nFailed": 30,
        "nSim": 2000,
        "frPeriod": 60,
        "criticalTemp": 690.0,
    }
    pid = await make_project(
        "Warehouse A", settings={"timeEqResult": outcome_data}
    )
    job_id = "wh-job-01"

    # Post a run for this project and job
    run_resp = await client.post(
        f"/imacs/projects/{pid}/macs-runs",
        json={**VALID_RUN, "imacs_job_id": job_id},
        headers=key_headers(),
    )
    assert run_resp.status_code == 201
    sent_time = run_resp.json()["received_at"]

    # Summary reports project id, name, last_sent_at, and outcome
    sum_resp = await client.get(f"/imacs/jobs/{job_id}/summary", headers=key_headers())
    assert sum_resp.status_code == 200
    summary = sum_resp.json()
    assert summary["project_id"] == pid
    assert summary["project_name"] == "Warehouse A"
    assert summary["last_sent_at"] == sent_time
    assert summary["outcome"] == outcome_data


# ==============================================================================
# 6. GET /imacs/projects (Search & mode filter)
# ==============================================================================


@pytest.mark.asyncio
async def test_imacs_projects_filtering_and_search(client: AsyncClient, make_project):
    teq1 = await make_project("Alpha Complex", mode="timeEq")
    teq2 = await make_project("Beta Tower", mode="timeEq")
    fds = await make_project("Alpha CFD", mode="fdsGen")

    # Mode filter
    r_mode = await client.get("/imacs/projects", params={"mode": "timeEq"}, headers=key_headers())
    assert r_mode.status_code == 200
    ids_mode = {p["id"] for p in r_mode.json()}
    assert teq1 in ids_mode and teq2 in ids_mode and fds not in ids_mode

    # Query search
    r_q = await client.get(
        "/imacs/projects", params={"mode": "timeEq", "q": "alpha"}, headers=key_headers()
    )
    assert r_q.status_code == 200
    ids_q = {p["id"] for p in r_q.json()}
    assert teq1 in ids_q
    assert teq2 not in ids_q


# ==============================================================================
# 7. Additional Edge Cases: Expiration, empty lists, schema 2
# ==============================================================================


@pytest.mark.asyncio
async def test_expired_handoff_returns_410(client: AsyncClient, session_factory, user_headers):
    from models.db_models import MacsHandoff

    # Create a handoff
    create_resp = await client.post(
        "/imacs/handoffs", json=VALID_RUN, headers=key_headers()
    )
    assert create_resp.status_code == 201
    hid = create_resp.json()["handoff_id"]

    # Manually expire it in the DB
    async with session_factory() as session:
        handoff = (
            await session.execute(select(MacsHandoff).where(MacsHandoff.id == uuid.UUID(hid)))
        ).scalar_one()
        handoff.expires_at = datetime.now(timezone.utc) - timedelta(minutes=10)
        await session.commit()

    # GET /handoffs/{id} -> 410
    get_resp = await client.get(f"/handoffs/{hid}", headers=user_headers)
    assert get_resp.status_code == 410

    # Claim -> 410
    proj_resp = await client.post(
        "/projects",
        json={"name": "Expired Handoff Project", "mode": "timeEq", "handoff_id": hid},
        headers=user_headers,
    )
    assert proj_resp.status_code == 410


@pytest.mark.asyncio
async def test_schema_2_envelope_accepted(client: AsyncClient, make_project):
    pid = await make_project()
    payload = {**VALID_RUN, "schema": "fd-macs-reliability/2"}
    resp = await client.post(
        f"/imacs/projects/{pid}/macs-runs", json=payload, headers=key_headers()
    )
    assert resp.status_code == 201
    assert resp.json()["schema"] == "fd-macs-reliability/2"


@pytest.mark.asyncio
async def test_project_with_no_macs_runs_returns_empty_list(
    client: AsyncClient, make_project, user_headers
):
    pid = await make_project()
    resp = await client.get(f"/projects/{pid}/macs-runs", headers=user_headers)
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_unlink_nonexistent_job_is_idempotent_200(client: AsyncClient):
    resp = await client.delete("/imacs/jobs/does-not-exist/link", headers=key_headers())
    assert resp.status_code == 200
    assert resp.json()["unlinked"] is True


@pytest.mark.asyncio
async def test_macs_run_with_full_outputs_checks_and_timeseries(
    client: AsyncClient, make_project, user_headers
):
    pid = await make_project()
    ts = [
        {
            'time_step': 1,
            'time_min': 1.0,
            'fire_temp': 349.2,
            'lofl_temp': 120.5,
            'mesh_temp': 95.0,
            'slabtop_temp': 22.0,
            'slabbot_temp': 180.4,
            'beam_hot_capacity': 450.2,
            'deflection': 12.4,
            'slab_yield': 1.0,
            'enhancement': 1.0,
            'slab_cap': 310.0,
            'total_plate_capacity': 760.2,
            'utilization_factor': 0.42,
        }
    ]
    outputs = {
        'uf_max': 0.85,
        'max_deflection': 88.0,
        'max_temperature': 650.0,
        'comp_failure': 0,
        'side_a_critical_temp': 685.0,
        'side_a_load_ratio': 0.32,
        'side_b_critical_temp': 631.0,
        'side_b_load_ratio': 0.45,
    }
    checks = [
        {'name': 'Composite failure', 'pass': True},
        {'name': 'UF max check', 'pass': True, 'value': 0.85},
    ]
    payload = {
        **VALID_RUN,
        'outputs': outputs,
        'checks': checks,
        'time_series': ts,
    }
    resp = await client.post(
        f'/imacs/projects/{pid}/macs-runs', json=payload, headers=key_headers()
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data['outputs']['uf_max'] == 0.85
    assert len(data['checks']) == 2
    assert len(data['time_series']) == 1
    assert data['time_series'][0]['fire_temp'] == 349.2

    # Verify retrieval via GET /projects/{pid}/macs-runs
    list_resp = await client.get(f'/projects/{pid}/macs-runs', headers=user_headers)
    assert list_resp.status_code == 200
    runs = list_resp.json()
    assert len(runs) == 1
    assert runs[0]['outputs']['uf_max'] == 0.85
    assert len(runs[0]['time_series']) == 1

    # Verify retrieval via GET /projects/macs-runs/{run_id}
    run_id = data['id']
    single_resp = await client.get(f'/projects/macs-runs/{run_id}', headers=user_headers)
    assert single_resp.status_code == 200
    assert single_resp.json()['id'] == run_id

    # Verify global list GET /projects/macs-runs
    all_resp = await client.get('/projects/macs-runs', headers=user_headers)
    assert all_resp.status_code == 200
    assert any(r['id'] == run_id for r in all_resp.json())


@pytest.mark.asyncio
async def test_macs_batch_persisted_on_push_and_retrieved(client, user_headers):
    create_resp = await client.post(
        "/projects",
        json={"name": "Project Batch Test", "mode": "timeEq", "settings": {}},
        headers=user_headers,
    )
    assert create_resp.status_code == 201
    pid = create_resp.json()["id"]

    sample_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    macs_batch = {
        "batch_id": "b-test-123",
        "name": "Batch Test 123",
        "run_count": 100,
        "pass_count": 98,
        "fail_count": 2,
        "error_count": 0,
        "reliability_percent": 98.0,
        "setup": {
            "run_count": 100,
            "groups": [
                {
                    "title": "Geometry",
                    "fields": [
                        {"key": "span1", "label": "Span 1", "unit": "m", "value": 12.0, "varies": False}
                    ]
                }
            ]
        },
        "shear_check": {
            "batch_id": "b-test-123",
            "checked": 100,
            "sub_limit_runs": []
        },
        "charts": {
            "scatter": sample_b64,
            "totalCapacity": sample_b64,
            "beamTemp": sample_b64,
            "meshTemp": sample_b64,
        }
    }

    payload = {
        **VALID_RUN,
        "macs_batch": macs_batch,
    }
    push_resp = await client.post(
        f"/imacs/projects/{pid}/macs-runs", json=payload, headers=key_headers()
    )
    assert push_resp.status_code == 201

    # Check project settings
    proj_resp = await client.get(f"/projects/{pid}", headers=user_headers)
    assert proj_resp.status_code == 200
    assert proj_resp.json()["settings"]["macsBatch"]["batch_id"] == "b-test-123"

    # Check GET /projects/{pid}/macs-batch/{batch_id} returns from settings without needing IMACS_DB_PATH
    batch_resp = await client.get(f"/projects/{pid}/macs-batch/b-test-123", headers=user_headers)
    assert batch_resp.status_code == 200
    batch_data = batch_resp.json()
    assert batch_data["batch_id"] == "b-test-123"
    assert batch_data["reliability_percent"] == 98.0
    assert "charts" in batch_data


@pytest.mark.asyncio
async def test_macs_batch_persisted_on_handoff_claim(client, user_headers):
    sample_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    macs_batch = {
        "batch_id": "b-handoff-456",
        "name": "Handoff Batch",
        "run_count": 50,
        "pass_count": 50,
        "fail_count": 0,
        "error_count": 0,
        "reliability_percent": 100.0,
        "setup": {"run_count": 50, "groups": []},
        "shear_check": {"batch_id": "b-handoff-456", "checked": 50, "sub_limit_runs": []},
        "charts": {"scatter": sample_b64, "totalCapacity": sample_b64, "beamTemp": sample_b64, "meshTemp": sample_b64}
    }
    payload = {
        **VALID_RUN,
        "macs_batch": macs_batch,
    }
    handoff_resp = await client.post("/imacs/handoffs", json=payload, headers=key_headers())
    assert handoff_resp.status_code == 201
    hid = handoff_resp.json()["handoff_id"]

    # Claim into new project
    claim_resp = await client.post(
        "/projects",
        json={"name": "Handoff Project", "mode": "timeEq", "handoff_id": hid},
        headers=user_headers,
    )
    assert claim_resp.status_code == 201
    pid = claim_resp.json()["id"]

    # Verify settings has macsBatch
    proj_resp = await client.get(f"/projects/{pid}", headers=user_headers)
    assert proj_resp.status_code == 200
    assert proj_resp.json()["settings"]["macsBatch"]["batch_id"] == "b-handoff-456"


@pytest.mark.asyncio
async def test_structural_fire_report_endpoint(client, user_headers):
    sample_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    macs_batch = {
        "batch_id": "b-rpt-1",
        "name": "Report Batch",
        "run_count": 100,
        "pass_count": 99,
        "fail_count": 1,
        "error_count": 0,
        "reliability_percent": 99.0,
        "setup": {
            "run_count": 100,
            "groups": [
                {"title": "Geometry", "fields": [{"key": "span1", "label": "Span 1", "unit": "m", "value": 12.0, "varies": False}]}
            ]
        },
        "shear_check": {"batch_id": "b-rpt-1", "checked": 100, "sub_limit_runs": []},
        "charts": {"scatter": sample_b64, "totalCapacity": sample_b64, "beamTemp": sample_b64, "meshTemp": sample_b64}
    }
    time_eq_inputs = {
        "mcOccupancy": "Office",
        "fireResistancePeriod": 60,
        "compartmentHeight": 3.5,
        "isSprinklered": True,
        "criticalTemp": 540,
        "sectionFactor": 140,
        "customBValue": "1200",
    }
    time_eq_result = {
        "failure_prob": 0.02,
        "reliabilityPercent": 98.0,
        "seed": 42,
        "nSim": 1000,
        "nFailed": 20,
        "charts": {
            "steelTempSpaghetti": sample_b64,
            "passFailScatter": sample_b64,
        }
    }

    create_resp = await client.post(
        "/projects",
        json={
            "name": "Panattoni California Drive",
            "mode": "timeEq",
            "settings": {
                "macsBatch": macs_batch,
                "timeEqInputs": time_eq_inputs,
                "timeEqResult": time_eq_result,
            }
        },
        headers=user_headers,
    )
    assert create_resp.status_code == 201
    pid = create_resp.json()["id"]

    # Also push a run with side critical temps so perimeter beam breakdown is present
    payload = {
        **VALID_RUN,
        "outputs": {
            "side_a_critical_temp": 580.0,
            "side_b_critical_temp": 540.0,
            "side_c_critical_temp": 600.0,
            "side_d_critical_temp": 610.0,
        }
    }
    await client.post(f"/imacs/projects/{pid}/macs-runs", json=payload, headers=key_headers())

    report_resp = await client.post(
        f"/projects/{pid}/structural-fire-report",
        headers=user_headers,
    )
    assert report_resp.status_code == 200
    assert report_resp.headers["content-type"] == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    assert "attachment; filename=" in report_resp.headers["content-disposition"]
    docx_bytes = report_resp.content
    assert len(docx_bytes) > 1000

    # Parse with python-docx
    import io
    from docx import Document
    doc = Document(io.BytesIO(docx_bytes))
    full_text = "\n".join([p.text for p in doc.paragraphs])
    assert "MACS+" in full_text or "Composite Slab" in full_text
    assert "Monte Carlo" in full_text or "Time Equivalence" in full_text
    assert "Panattoni California Drive" in full_text

