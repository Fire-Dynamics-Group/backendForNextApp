"""Live HRR and DEVC series for one modelling run.

The runner pushes samples with the same X-API-Key as status. The page polls
with a cursor and only receives points it does not already have. A finished
run keeps its series. CloudHPC pull_csv does not call out while the flag is off.

Push:
    POST /cfd-dashboard/runs/{run_id}/series
    {"hrr": [{"t": 0.0, "hrr": 0.0}],
     "devc_columns": [{"id": "TC01", "quantity": "TEMPERATURE", "unit": "C"}],
     "devc": [{"t": 0.0, "values": {"TC01": 20.0}}]}

Read:
    GET /cfd-dashboard/runs/{run_id}/series?hrr_after=&devc_after=&devc_ids=

Selection (what the runner should sample next):
    PUT /cfd-dashboard/runs/{run_id}/series/devc-selection
    {"ids": ["TC01"]}
"""

import os
import socket
import urllib.request
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

TEST_DATABASE_URL = "sqlite+aiosqlite:///./test_run_series.db"
DB_FILE = "./test_run_series.db"

os.environ["DATABASE_URL"] = ""
os.environ["FDS_API_KEY"] = "test-key"

from database import Base  # noqa: E402
from models.cfd_models import CfdRunnerState, CfdSimulation  # noqa: E402, F401
from models.db_models import Element, Floor, Project  # noqa: E402, F401

API_KEY_HEADER = {"X-API-Key": "test-key"}
PHASE1_HEAD = "f6a7b8c9d0e1"


@pytest_asyncio.fixture
async def test_engine():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()
    if os.path.exists(DB_FILE):
        os.remove(DB_FILE)


@pytest_asyncio.fixture
async def client(test_engine):
    import database
    from main import app

    session_factory = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[database.get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


async def _run(client: AsyncClient, case_name: str = "warehouse.fds") -> str:
    started = await client.post(
        "/cfd-dashboard/status",
        json={"event": "heartbeat", "machine_name": "Superbot"},
        headers=API_KEY_HEADER,
    )
    assert started.status_code == 200
    created = await client.post(
        "/cfd-dashboard/runs",
        json={
            "machine_name": "Superbot",
            "case_name": case_name,
            "input_file_ref": f"s3://cases/{case_name}",
            "created_by": "ada",
        },
        headers=API_KEY_HEADER,
    )
    assert created.status_code == 200
    return created.json()["id"]


def _url(run_id: str) -> str:
    return f"/cfd-dashboard/runs/{run_id}/series"


def _selection_url(run_id: str) -> str:
    return f"/cfd-dashboard/runs/{run_id}/series/devc-selection"


# --- Auth and a missing run ---


@pytest.mark.asyncio
async def test_series_routes_require_the_runner_api_key(client: AsyncClient):
    run_id = await _run(client)
    missing = await client.post(_url(run_id), json={"hrr": [{"t": 1, "hrr": 2}]})
    assert missing.status_code in (401, 403, 422)
    wrong = await client.post(
        _url(run_id),
        json={"hrr": [{"t": 1, "hrr": 2}]},
        headers={"X-API-Key": "wrong-key"},
    )
    assert wrong.status_code == 403
    get_missing = await client.get(_url(run_id))
    assert get_missing.status_code in (401, 403, 422)
    put_wrong = await client.put(
        _selection_url(run_id),
        json={"ids": ["TC01"]},
        headers={"X-API-Key": "wrong-key"},
    )
    assert put_wrong.status_code == 403


@pytest.mark.asyncio
async def test_unknown_run_is_404(client: AsyncClient):
    missing = "00000000-0000-4000-8000-000000000099"
    resp = await client.post(
        _url(missing),
        json={"hrr": [{"t": 1.0, "hrr": 1.0}]},
        headers=API_KEY_HEADER,
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Unknown run"
    fetched = await client.get(_url(missing), headers=API_KEY_HEADER)
    assert fetched.status_code == 404
    assert fetched.json()["detail"] == "Unknown run"
    selected = await client.put(
        _selection_url(missing),
        json={"ids": ["TC01"]},
        headers=API_KEY_HEADER,
    )
    assert selected.status_code == 404
    assert selected.json()["detail"] == "Unknown run"


# --- Cursor: the page only fetches points it does not have ---


@pytest.mark.asyncio
async def test_cursor_returns_only_new_points(client: AsyncClient):
    run_id = await _run(client)
    first = await client.post(
        _url(run_id),
        json={"hrr": [{"t": 0.0, "hrr": 0.0}, {"t": 1.0, "hrr": 10.0}]},
        headers=API_KEY_HEADER,
    )
    assert first.status_code == 200
    assert first.json()["hrr_stored"] == 2

    full = await client.get(_url(run_id), headers=API_KEY_HEADER)
    assert full.status_code == 200
    body = full.json()
    assert body["run_id"] == run_id
    assert [(p["t"], p["hrr"]) for p in body["hrr"]] == [(0.0, 0.0), (1.0, 10.0)]
    assert [p["seq"] for p in body["hrr"]] == [1, 2]
    cursor = body["hrr_cursor"]
    assert cursor == 2

    again = await client.get(
        _url(run_id), params={"hrr_after": cursor}, headers=API_KEY_HEADER
    )
    assert again.json()["hrr"] == []
    assert again.json()["hrr_cursor"] == cursor

    second = await client.post(
        _url(run_id),
        json={"hrr": [{"t": 2.0, "hrr": 25.0}]},
        headers=API_KEY_HEADER,
    )
    assert second.status_code == 200
    assert second.json()["hrr_stored"] == 1

    fresh = await client.get(
        _url(run_id), params={"hrr_after": cursor}, headers=API_KEY_HEADER
    )
    assert [(p["t"], p["hrr"]) for p in fresh.json()["hrr"]] == [(2.0, 25.0)]
    assert fresh.json()["hrr_cursor"] == fresh.json()["hrr"][0]["seq"]
    assert fresh.json()["hrr"][0]["seq"] > cursor


@pytest.mark.asyncio
async def test_same_time_replaces_the_value_without_a_new_point(client: AsyncClient):
    run_id = await _run(client)
    await client.post(
        _url(run_id),
        json={"hrr": [{"t": 1.0, "hrr": 10.0}]},
        headers=API_KEY_HEADER,
    )
    full = await client.get(_url(run_id), headers=API_KEY_HEADER)
    cursor = full.json()["hrr_cursor"]

    replaced = await client.post(
        _url(run_id),
        json={"hrr": [{"t": 1.0, "hrr": 12.5}]},
        headers=API_KEY_HEADER,
    )
    assert replaced.status_code == 200
    assert replaced.json()["hrr_stored"] == 1

    after = await client.get(_url(run_id), headers=API_KEY_HEADER)
    assert [(p["t"], p["hrr"]) for p in after.json()["hrr"]] == [(1.0, 12.5)]
    assert after.json()["hrr_cursor"] == cursor
    polled = await client.get(
        _url(run_id), params={"hrr_after": cursor}, headers=API_KEY_HEADER
    )
    assert polled.json()["hrr"] == []


@pytest.mark.asyncio
async def test_series_stay_on_their_own_run(client: AsyncClient):
    first = await _run(client, "one.fds")
    second = await _run(client, "two.fds")
    await client.post(
        _url(first),
        json={"hrr": [{"t": 1.0, "hrr": 5.0}]},
        headers=API_KEY_HEADER,
    )
    await client.post(
        _url(second),
        json={"hrr": [{"t": 1.0, "hrr": 9.0}]},
        headers=API_KEY_HEADER,
    )
    one = (await client.get(_url(first), headers=API_KEY_HEADER)).json()
    two = (await client.get(_url(second), headers=API_KEY_HEADER)).json()
    assert [p["hrr"] for p in one["hrr"]] == [5.0]
    assert [p["hrr"] for p in two["hrr"]] == [9.0]


# --- Cap: downsample on write, keep the ends of each series ---


def test_series_caps_match_the_contract():
    from services import run_series

    assert run_series.MAX_POINTS_PER_SERIES == 2000
    assert run_series.MAX_DEFAULT_DEVC_COLUMNS == 8
    assert run_series.MAX_SELECTED_DEVC_COLUMNS == 12
    assert run_series.MAX_DEVC_SAMPLE_COLUMNS == 32
    assert run_series.MAX_CATALOG_COLUMNS == 2000


@pytest.mark.asyncio
async def test_hrr_is_downsampled_to_the_cap_and_keeps_both_ends(
    client: AsyncClient, monkeypatch
):
    import services.run_series as run_series

    monkeypatch.setattr(run_series, "MAX_POINTS_PER_SERIES", 5)
    run_id = await _run(client)
    points = [{"t": float(i), "hrr": float(i * 10)} for i in range(10)]
    pushed = await client.post(
        _url(run_id), json={"hrr": points}, headers=API_KEY_HEADER
    )
    assert pushed.status_code == 200

    body = (await client.get(_url(run_id), headers=API_KEY_HEADER)).json()
    times = [p["t"] for p in body["hrr"]]
    assert len(times) == 5
    assert times[0] == 0.0
    assert times[-1] == 9.0
    assert times == sorted(times)
    assert any(3.0 <= t <= 6.0 for t in times)
    cursor = body["hrr_cursor"]

    extra = await client.post(
        _url(run_id),
        json={"hrr": [{"t": 99.0, "hrr": 123.0}]},
        headers=API_KEY_HEADER,
    )
    assert extra.status_code == 200
    polled = (
        await client.get(
            _url(run_id), params={"hrr_after": cursor}, headers=API_KEY_HEADER
        )
    ).json()
    assert [p["t"] for p in polled["hrr"]] == [99.0]
    full = (await client.get(_url(run_id), headers=API_KEY_HEADER)).json()
    assert len(full["hrr"]) == 5
    assert full["hrr"][0]["t"] == 0.0
    assert full["hrr"][-1]["t"] == 99.0


@pytest.mark.asyncio
async def test_real_hrr_cap_keeps_two_thousand_points(client: AsyncClient):
    from services.run_series import MAX_POINTS_PER_SERIES

    run_id = await _run(client)
    extra = 25
    points = [
        {"t": float(i), "hrr": float(i)} for i in range(MAX_POINTS_PER_SERIES + extra)
    ]
    pushed = await client.post(
        _url(run_id), json={"hrr": points}, headers=API_KEY_HEADER
    )
    assert pushed.status_code == 200
    body = (await client.get(_url(run_id), headers=API_KEY_HEADER)).json()
    assert len(body["hrr"]) == MAX_POINTS_PER_SERIES
    assert body["hrr"][0]["t"] == 0.0
    assert body["hrr"][-1]["t"] == float(MAX_POINTS_PER_SERIES + extra - 1)


# --- DEVC catalog, selection, and column caps ---


def _columns(n: int) -> list:
    columns = []
    for i in range(n):
        quantity = "TEMPERATURE" if i % 2 == 0 else "VISIBILITY"
        columns.append({"id": f"D{i:02d}", "quantity": quantity, "unit": "C"})
    return columns


def _devc_point(columns: list, t: float) -> dict:
    return {
        "t": t,
        "values": {column["id"]: float(index) for index, column in enumerate(columns)},
    }


@pytest.mark.asyncio
async def test_devc_catalog_is_stored_once_and_selection_filters_samples(
    client: AsyncClient,
):
    from services.run_series import MAX_DEFAULT_DEVC_COLUMNS

    run_id = await _run(client)
    columns = _columns(MAX_DEFAULT_DEVC_COLUMNS + 2)
    catalog = await client.post(
        _url(run_id),
        json={"devc_columns": columns},
        headers=API_KEY_HEADER,
    )
    assert catalog.status_code == 200
    assert catalog.json()["accepted_columns"] == []
    assert catalog.json()["dropped_columns"] == []
    listed = (await client.get(_url(run_id), headers=API_KEY_HEADER)).json()
    assert listed["devc"] == {}
    assert [column["id"] for column in listed["devc_columns"]] == [
        column["id"] for column in sorted(columns, key=lambda item: item["id"])
    ]
    by_id = {column["id"]: column for column in listed["devc_columns"]}
    assert by_id["D00"]["quantity"] == "TEMPERATURE"
    assert by_id["D00"]["unit"] == "C"
    assert by_id["D01"]["quantity"] == "VISIBILITY"

    pushed = await client.post(
        _url(run_id),
        json={"devc": [_devc_point(columns, 1.0)]},
        headers=API_KEY_HEADER,
    )
    assert pushed.status_code == 200
    accepted = [column["id"] for column in columns[:MAX_DEFAULT_DEVC_COLUMNS]]
    dropped = [column["id"] for column in columns[MAX_DEFAULT_DEVC_COLUMNS:]]
    assert pushed.json()["accepted_columns"] == accepted
    assert pushed.json()["dropped_columns"] == dropped
    assert pushed.json()["devc_stored"] == MAX_DEFAULT_DEVC_COLUMNS

    stored = (await client.get(_url(run_id), headers=API_KEY_HEADER)).json()
    assert set(stored["devc"]) == set(accepted)
    assert stored["devc"]["D00"][0]["value"] == 0.0
    assert "D08" not in stored["devc"]
    cursor = stored["devc_cursor"]

    chosen = await client.put(
        _selection_url(run_id),
        json={"ids": ["D09", "D01", "D09"]},
        headers=API_KEY_HEADER,
    )
    assert chosen.status_code == 200
    assert chosen.json()["ids"] == ["D09", "D01"]
    current = await client.get(_selection_url(run_id), headers=API_KEY_HEADER)
    assert current.json()["ids"] == ["D09", "D01"]

    follow = await client.post(
        _url(run_id),
        json={"devc": [_devc_point(columns, 2.0)]},
        headers=API_KEY_HEADER,
    )
    assert follow.json()["accepted_columns"] == ["D09", "D01"]
    assert "D00" in follow.json()["dropped_columns"]
    assert follow.json()["devc_selection"] == ["D09", "D01"]

    polled = (
        await client.get(
            _url(run_id),
            params={"devc_after": cursor, "devc_ids": "D09,D01,D00"},
            headers=API_KEY_HEADER,
        )
    ).json()
    assert [p["t"] for p in polled["devc"]["D09"]] == [2.0]
    assert [p["t"] for p in polled["devc"]["D01"]] == [2.0]
    assert polled["devc"]["D00"] == []
    assert polled["devc_selection"] == ["D09", "D01"]

    history = (
        await client.get(
            _url(run_id), params={"devc_ids": "D00"}, headers=API_KEY_HEADER
        )
    ).json()
    assert [(p["t"], p["value"]) for p in history["devc"]["D00"]] == [(1.0, 0.0)]


@pytest.mark.asyncio
async def test_selection_over_the_cap_is_rejected(client: AsyncClient):
    from services.run_series import MAX_SELECTED_DEVC_COLUMNS

    run_id = await _run(client)
    too_many = [f"D{i:02d}" for i in range(MAX_SELECTED_DEVC_COLUMNS + 1)]
    resp = await client.put(
        _selection_url(run_id),
        json={"ids": too_many},
        headers=API_KEY_HEADER,
    )
    assert resp.status_code == 400
    assert str(MAX_SELECTED_DEVC_COLUMNS) in resp.json()["detail"]
    blank = await client.put(
        _selection_url(run_id),
        json={"ids": ["TC01", " "]},
        headers=API_KEY_HEADER,
    )
    assert blank.status_code == 400
    fetched = await client.get(
        _url(run_id),
        params={"devc_ids": ",".join(too_many)},
        headers=API_KEY_HEADER,
    )
    assert fetched.status_code == 400


@pytest.mark.asyncio
async def test_clearing_selection_stores_the_small_default_again(client: AsyncClient):
    from services.run_series import MAX_DEFAULT_DEVC_COLUMNS

    run_id = await _run(client)
    columns = _columns(MAX_DEFAULT_DEVC_COLUMNS + 2)
    await client.put(
        _selection_url(run_id),
        json={"ids": ["D09"]},
        headers=API_KEY_HEADER,
    )
    await client.put(
        _selection_url(run_id), json={"ids": []}, headers=API_KEY_HEADER
    )
    pushed = await client.post(
        _url(run_id),
        json={"devc_columns": columns, "devc": [_devc_point(columns, 1.0)]},
        headers=API_KEY_HEADER,
    )
    assert pushed.json()["devc_selection"] == []
    assert pushed.json()["accepted_columns"] == [
        column["id"] for column in columns[:MAX_DEFAULT_DEVC_COLUMNS]
    ]


@pytest.mark.asyncio
async def test_unselected_samples_are_evicted_so_a_new_selection_fits(
    client: AsyncClient, monkeypatch
):
    import services.run_series as run_series

    monkeypatch.setattr(run_series, "MAX_DEVC_SAMPLE_COLUMNS", 2)
    run_id = await _run(client)
    columns = _columns(3)
    await client.put(
        _selection_url(run_id),
        json={"ids": ["D00", "D01"]},
        headers=API_KEY_HEADER,
    )
    first = await client.post(
        _url(run_id),
        json={"devc_columns": columns, "devc": [_devc_point(columns, 1.0)]},
        headers=API_KEY_HEADER,
    )
    assert first.json()["accepted_columns"] == ["D00", "D01"]

    await client.put(
        _selection_url(run_id),
        json={"ids": ["D00", "D02"]},
        headers=API_KEY_HEADER,
    )
    second = await client.post(
        _url(run_id),
        json={"devc": [_devc_point(columns, 2.0)]},
        headers=API_KEY_HEADER,
    )
    assert second.json()["accepted_columns"] == ["D00", "D02"]
    body = (await client.get(_url(run_id), headers=API_KEY_HEADER)).json()
    assert set(body["devc"]) == {"D00", "D02"}
    assert [p["t"] for p in body["devc"]["D00"]] == [1.0, 2.0]
    assert [p["t"] for p in body["devc"]["D02"]] == [2.0]
    assert [column["id"] for column in body["devc_columns"]] == ["D00", "D01", "D02"]


@pytest.mark.asyncio
async def test_empty_run_serves_an_honest_empty_series(client: AsyncClient):
    run_id = await _run(client)
    body = (await client.get(_url(run_id), headers=API_KEY_HEADER)).json()
    assert body["hrr"] == []
    assert body["hrr_cursor"] == 0
    assert body["devc"] == {}
    assert body["devc_columns"] == []
    assert body["devc_cursor"] == 0
    assert body["devc_selection"] == []


# --- Finished runs keep the series ---


@pytest.mark.asyncio
async def test_completed_run_keeps_its_series(client: AsyncClient):
    run_id = await _run(client)
    await client.post(
        _url(run_id),
        json={
            "hrr": [{"t": 1.0, "hrr": 40.0}, {"t": 2.0, "hrr": 80.0}],
            "devc_columns": [{"id": "TC01", "quantity": "TEMPERATURE", "unit": "C"}],
            "devc": [{"t": 2.0, "values": {"TC01": 33.0}}],
        },
        headers=API_KEY_HEADER,
    )
    done = await client.post(
        "/cfd-dashboard/status",
        json={
            "event": "sim_completed",
            "machine_name": "Superbot",
            "run_id": run_id,
            "case_name": "warehouse.fds",
        },
        headers=API_KEY_HEADER,
    )
    assert done.status_code == 200
    detail = await client.get(f"/cfd-dashboard/runs/{run_id}", headers=API_KEY_HEADER)
    assert detail.json()["status"] == "completed"

    body = (await client.get(_url(run_id), headers=API_KEY_HEADER)).json()
    assert [(p["t"], p["hrr"]) for p in body["hrr"]] == [(1.0, 40.0), (2.0, 80.0)]
    assert body["devc"]["TC01"][0]["value"] == 33.0

    later = await client.post(
        _url(run_id),
        json={"hrr": [{"t": 3.0, "hrr": 90.0}]},
        headers=API_KEY_HEADER,
    )
    assert later.status_code == 200
    final = (await client.get(_url(run_id), headers=API_KEY_HEADER)).json()
    assert [p["t"] for p in final["hrr"]] == [1.0, 2.0, 3.0]


# --- CloudHPC seam: flag off, no adapter, no network ---


def test_pull_csv_raises_while_cloudhpc_is_off(monkeypatch):
    from services.modelling_runs import CLOUDHPC_ENABLED, CloudHpcDisabled, pull_csv

    assert CLOUDHPC_ENABLED is False

    def boom(*_args, **_kwargs):
        raise AssertionError("pull_csv touched the network")

    monkeypatch.setattr(socket, "create_connection", boom)
    monkeypatch.setattr(urllib.request, "urlopen", boom)
    monkeypatch.setattr(httpx, "get", boom)
    monkeypatch.setattr(httpx, "request", boom)
    with pytest.raises(CloudHpcDisabled):
        pull_csv({"id": "run-1", "external_id": "job-9"})


def test_series_migration_follows_phase1_head():
    matches = list(Path("alembic/versions").glob("*run_series*.py"))
    assert len(matches) == 1
    body = matches[0].read_text()
    assert PHASE1_HEAD in body
    for name in (
        "run_series_columns",
        "run_series_points",
        "run_series_counters",
        "run_devc_selections",
    ):
        assert name in body
