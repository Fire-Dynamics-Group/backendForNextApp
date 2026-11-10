"""Live HRR and DEVC series, locked to the runner push and the page poll.

Runner (fds-runner PR 2):
    POST /cfd-dashboard/series
    X-API-Key
    {
      "run_id", "machine_name", "case_name", "chid",
      "devc_columns": [{"id", "quantity", "unit"}] once,
      "hrr": [{"t", "hrr"}],
      "devc": [{"t", "values": {id: number}}],
      "design": [{"t", "hrr"}] or null, once
    }
    Response is exactly {"selected_devc": [...]}.
    The runner applies that list on the next push, and advances its file
    cursor only after a 2xx.

Page (fd-toolstation PR 10):
    GET /cfd-dashboard/runs/{id}/series?since={cursor}&devices={id,id}
    {
      "cursor": "2",
      "hrr": {"unit": "kW", "points": [{"t", "v"}], "design": [{"t", "hrr"}] or null},
      "devices": [{"id", "quantity", "unit"}],
      "series": {"TC_01": [{"t", "v"}]}
    }
    devices= (empty) is the catalog only. The latest devices list is what
    the next runner push receives as selected_devc.
"""

import os
import socket
import urllib.request

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
PUSH = "/cfd-dashboard/series"


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


def _series(run_id: str) -> str:
    return f"/cfd-dashboard/runs/{run_id}/series"


def _body(run_id: str, **extra) -> dict:
    payload = {
        "run_id": run_id,
        "machine_name": "Superbot",
        "case_name": "warehouse.fds",
        "chid": "warehouse",
    }
    payload.update(extra)
    return payload


def _columns(n: int) -> list:
    columns = []
    for i in range(n):
        quantity = "TEMPERATURE" if i % 2 == 0 else "VISIBILITY"
        columns.append({"id": f"D{i:02d}", "quantity": quantity, "unit": "C"})
    return columns


def _devc_row(columns: list, t: float) -> dict:
    return {
        "t": t,
        "values": {column["id"]: float(index) for index, column in enumerate(columns)},
    }


# --- Auth and a missing run. A non-2xx leaves the runner's file cursor put. ---


@pytest.mark.asyncio
async def test_series_push_and_poll_require_the_api_key(client: AsyncClient):
    run_id = await _run(client)
    missing = await client.post(PUSH, json=_body(run_id, hrr=[{"t": 1, "hrr": 2}]))
    assert missing.status_code in (401, 403, 422)
    wrong = await client.post(
        PUSH,
        json=_body(run_id, hrr=[{"t": 1, "hrr": 2}]),
        headers={"X-API-Key": "wrong-key"},
    )
    assert wrong.status_code == 403
    polled = await client.get(_series(run_id), params={"devices": ""})
    assert polled.status_code in (401, 403, 422)


@pytest.mark.asyncio
async def test_unknown_run_is_not_a_successful_push(client: AsyncClient):
    missing = "00000000-0000-4000-8000-000000000099"
    resp = await client.post(
        PUSH,
        json=_body(missing, hrr=[{"t": 1.0, "hrr": 1.0}]),
        headers=API_KEY_HEADER,
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Unknown run"
    fetched = await client.get(
        _series(missing), params={"devices": ""}, headers=API_KEY_HEADER
    )
    assert fetched.status_code == 404
    assert fetched.json()["detail"] == "Unknown run"


# --- Page poll: one since cursor, {t, v} points, design stays null ---


@pytest.mark.asyncio
async def test_since_returns_only_new_points(client: AsyncClient):
    run_id = await _run(client)
    first = await client.post(
        PUSH,
        json=_body(
            run_id,
            hrr=[{"t": 0.0, "hrr": 0.0}, {"t": 1.0, "hrr": 10.0}],
        ),
        headers=API_KEY_HEADER,
    )
    assert first.status_code == 200
    assert first.json() == {"selected_devc": []}

    full = await client.get(
        _series(run_id), params={"devices": ""}, headers=API_KEY_HEADER
    )
    assert full.status_code == 200
    body = full.json()
    assert body["hrr"]["unit"] == "kW"
    assert body["hrr"]["design"] is None
    assert body["hrr"]["points"] == [{"t": 0.0, "v": 0.0}, {"t": 1.0, "v": 10.0}]
    assert body["series"] == {}
    assert body["devices"] == []
    cursor = body["cursor"]
    assert cursor == "2"
    assert isinstance(cursor, str)

    again = await client.get(
        _series(run_id),
        params={"since": cursor, "devices": ""},
        headers=API_KEY_HEADER,
    )
    assert again.json()["hrr"]["points"] == []
    assert again.json()["hrr"]["design"] is None
    assert again.json()["cursor"] == cursor

    second = await client.post(
        PUSH,
        json=_body(run_id, hrr=[{"t": 2.0, "hrr": 25.0}]),
        headers=API_KEY_HEADER,
    )
    assert second.status_code == 200
    fresh = await client.get(
        _series(run_id),
        params={"since": cursor, "devices": ""},
        headers=API_KEY_HEADER,
    )
    assert fresh.json()["hrr"]["points"] == [{"t": 2.0, "v": 25.0}]
    assert fresh.json()["cursor"] == "3"


@pytest.mark.asyncio
async def test_same_time_replaces_the_value_without_a_new_point(client: AsyncClient):
    run_id = await _run(client)
    await client.post(
        PUSH,
        json=_body(run_id, hrr=[{"t": 1.0, "hrr": 10.0}]),
        headers=API_KEY_HEADER,
    )
    full = await client.get(
        _series(run_id), params={"devices": ""}, headers=API_KEY_HEADER
    )
    cursor = full.json()["cursor"]

    replaced = await client.post(
        PUSH,
        json=_body(run_id, hrr=[{"t": 1.0, "hrr": 12.5}]),
        headers=API_KEY_HEADER,
    )
    assert replaced.status_code == 200
    after = await client.get(
        _series(run_id), params={"devices": ""}, headers=API_KEY_HEADER
    )
    assert after.json()["hrr"]["points"] == [{"t": 1.0, "v": 12.5}]
    assert after.json()["cursor"] == cursor
    polled = await client.get(
        _series(run_id),
        params={"since": cursor, "devices": ""},
        headers=API_KEY_HEADER,
    )
    assert polled.json()["hrr"]["points"] == []


@pytest.mark.asyncio
async def test_series_stay_on_their_own_run(client: AsyncClient):
    first = await _run(client, "one.fds")
    second = await _run(client, "two.fds")
    await client.post(
        PUSH, json=_body(first, hrr=[{"t": 1.0, "hrr": 5.0}]), headers=API_KEY_HEADER
    )
    await client.post(
        PUSH,
        json=_body(second, case_name="two.fds", chid="two", hrr=[{"t": 1.0, "hrr": 9.0}]),
        headers=API_KEY_HEADER,
    )
    one = (
        await client.get(_series(first), params={"devices": ""}, headers=API_KEY_HEADER)
    ).json()
    two = (
        await client.get(_series(second), params={"devices": ""}, headers=API_KEY_HEADER)
    ).json()
    assert [point["v"] for point in one["hrr"]["points"]] == [5.0]
    assert [point["v"] for point in two["hrr"]["points"]] == [9.0]


@pytest.mark.asyncio
async def test_empty_run_serves_an_honest_empty_series(client: AsyncClient):
    run_id = await _run(client)
    body = (
        await client.get(_series(run_id), params={"devices": ""}, headers=API_KEY_HEADER)
    ).json()
    assert body == {
        "cursor": "0",
        "hrr": {"unit": "kW", "points": [], "design": None},
        "devices": [],
        "series": {},
    }


# --- Caps the runner already uses: 1s gap, 60 points. Default is 4 columns. ---


def test_series_caps_match_the_runner():
    from services import run_series

    assert run_series.SERIES_MIN_DT == 1
    assert run_series.SERIES_MAX_POINTS == 60
    assert run_series.MAX_DEFAULT_DEVC_COLUMNS == 4
    assert run_series.MAX_SELECTED_DEVC_COLUMNS == 12
    assert run_series.MAX_DEVC_SAMPLE_COLUMNS == 12


@pytest.mark.asyncio
async def test_points_closer_than_one_second_are_not_stored(client: AsyncClient):
    run_id = await _run(client)
    pushed = await client.post(
        PUSH,
        json=_body(
            run_id,
            hrr=[
                {"t": 0.0, "hrr": 0.0},
                {"t": 0.4, "hrr": 1.0},
                {"t": 1.0, "hrr": 2.0},
                {"t": 1.5, "hrr": 3.0},
                {"t": 2.0, "hrr": 4.0},
            ],
        ),
        headers=API_KEY_HEADER,
    )
    assert pushed.status_code == 200
    points = (
        await client.get(_series(run_id), params={"devices": ""}, headers=API_KEY_HEADER)
    ).json()["hrr"]["points"]
    assert points == [
        {"t": 0.0, "v": 0.0},
        {"t": 1.0, "v": 2.0},
        {"t": 2.0, "v": 4.0},
    ]


@pytest.mark.asyncio
async def test_hrr_is_capped_at_sixty_points_and_keeps_both_ends(client: AsyncClient):
    from services.run_series import SERIES_MAX_POINTS

    run_id = await _run(client)
    count = SERIES_MAX_POINTS + 10
    points = [{"t": float(i), "hrr": float(i)} for i in range(count)]
    pushed = await client.post(
        PUSH, json=_body(run_id, hrr=points), headers=API_KEY_HEADER
    )
    assert pushed.status_code == 200
    body = (
        await client.get(_series(run_id), params={"devices": ""}, headers=API_KEY_HEADER)
    ).json()
    stored = body["hrr"]["points"]
    assert len(stored) == SERIES_MAX_POINTS
    assert stored[0] == {"t": 0.0, "v": 0.0}
    assert stored[-1]["t"] == float(count - 1)
    assert stored == sorted(stored, key=lambda point: point["t"])
    cursor = body["cursor"]

    extra = await client.post(
        PUSH,
        json=_body(run_id, hrr=[{"t": 1000.0, "hrr": 1000.0}]),
        headers=API_KEY_HEADER,
    )
    assert extra.status_code == 200
    polled = (
        await client.get(
            _series(run_id),
            params={"since": cursor, "devices": ""},
            headers=API_KEY_HEADER,
        )
    ).json()
    assert polled["hrr"]["points"] == [{"t": 1000.0, "v": 1000.0}]
    full = (
        await client.get(_series(run_id), params={"devices": ""}, headers=API_KEY_HEADER)
    ).json()["hrr"]["points"]
    assert len(full) == SERIES_MAX_POINTS
    assert full[0]["t"] == 0.0
    assert full[-1]["t"] == 1000.0


# --- DEVC catalog, the page's devices list, and the 4-column default ---


@pytest.mark.asyncio
async def test_devc_catalog_and_four_column_default(client: AsyncClient):
    run_id = await _run(client)
    columns = _columns(6)
    catalog = await client.post(
        PUSH,
        json=_body(run_id, devc_columns=columns),
        headers=API_KEY_HEADER,
    )
    assert catalog.status_code == 200
    assert catalog.json() == {"selected_devc": []}

    listed = (
        await client.get(_series(run_id), params={"devices": ""}, headers=API_KEY_HEADER)
    ).json()
    assert listed["series"] == {}
    assert [column["id"] for column in listed["devices"]] == [
        column["id"] for column in columns
    ]
    by_id = {column["id"]: column for column in listed["devices"]}
    assert by_id["D00"]["quantity"] == "TEMPERATURE"
    assert by_id["D00"]["unit"] == "C"
    assert by_id["D01"]["quantity"] == "VISIBILITY"

    pushed = await client.post(
        PUSH,
        json=_body(run_id, devc=[_devc_row(columns, 1.0)]),
        headers=API_KEY_HEADER,
    )
    assert pushed.json() == {"selected_devc": []}
    stored = (
        await client.get(
            _series(run_id),
            params={"devices": ",".join(column["id"] for column in columns)},
            headers=API_KEY_HEADER,
        )
    ).json()
    assert [point["v"] for point in stored["series"]["D00"]] == [0.0]
    assert [point["v"] for point in stored["series"]["D03"]] == [3.0]
    assert stored["series"]["D04"] == []
    assert stored["series"]["D05"] == []


@pytest.mark.asyncio
async def test_page_devices_list_is_what_the_runner_is_told(client: AsyncClient):
    run_id = await _run(client)
    columns = _columns(6)
    chosen = await client.get(
        _series(run_id), params={"devices": "D05"}, headers=API_KEY_HEADER
    )
    assert chosen.status_code == 200

    pushed = await client.post(
        PUSH,
        json=_body(
            run_id,
            devc_columns=columns,
            devc=[_devc_row(columns, 2.0)],
        ),
        headers=API_KEY_HEADER,
    )
    assert pushed.status_code == 200
    assert pushed.json() == {"selected_devc": ["D05"]}

    body = (
        await client.get(
            _series(run_id),
            params={"devices": "D05,D00"},
            headers=API_KEY_HEADER,
        )
    ).json()
    assert body["series"]["D05"] == [{"t": 2.0, "v": 5.0}]
    assert body["series"]["D00"] == []
    assert any(column["id"] == "D00" for column in body["devices"])

    follow = await client.post(
        PUSH,
        json=_body(run_id, devc=[_devc_row(columns, 3.0)]),
        headers=API_KEY_HEADER,
    )
    # The previous poll asked for D05 and D00, so that is the next push's list.
    assert follow.json() == {"selected_devc": ["D05", "D00"]}


@pytest.mark.asyncio
async def test_since_appends_only_the_requested_device(client: AsyncClient):
    run_id = await _run(client)
    columns = _columns(2)
    await client.get(
        _series(run_id), params={"devices": "D00,D01"}, headers=API_KEY_HEADER
    )
    await client.post(
        PUSH,
        json=_body(run_id, devc_columns=columns, devc=[_devc_row(columns, 1.0)]),
        headers=API_KEY_HEADER,
    )
    first = (
        await client.get(
            _series(run_id),
            params={"devices": "D00"},
            headers=API_KEY_HEADER,
        )
    ).json()
    cursor = first["cursor"]
    assert first["series"]["D00"] == [{"t": 1.0, "v": 0.0}]

    await client.post(
        PUSH,
        json=_body(run_id, devc=[_devc_row(columns, 4.0)]),
        headers=API_KEY_HEADER,
    )
    polled = (
        await client.get(
            _series(run_id),
            params={"since": cursor, "devices": "D00"},
            headers=API_KEY_HEADER,
        )
    ).json()
    assert polled["series"] == {"D00": [{"t": 4.0, "v": 0.0}]}
    assert polled["hrr"]["points"] == []
    assert int(polled["cursor"]) > int(cursor)


@pytest.mark.asyncio
async def test_too_many_devices_is_rejected(client: AsyncClient):
    from services.run_series import MAX_SELECTED_DEVC_COLUMNS

    run_id = await _run(client)
    too_many = [f"D{i:02d}" for i in range(MAX_SELECTED_DEVC_COLUMNS + 1)]
    resp = await client.get(
        _series(run_id),
        params={"devices": ",".join(too_many)},
        headers=API_KEY_HEADER,
    )
    assert resp.status_code == 400
    assert str(MAX_SELECTED_DEVC_COLUMNS) in resp.json()["detail"]


@pytest.mark.asyncio
async def test_unselected_samples_are_evicted_past_the_column_cap(
    client: AsyncClient, monkeypatch
):
    import services.run_series as run_series

    monkeypatch.setattr(run_series, "MAX_DEVC_SAMPLE_COLUMNS", 2)
    monkeypatch.setattr(run_series, "MAX_DEFAULT_DEVC_COLUMNS", 2)
    run_id = await _run(client)
    columns = _columns(3)
    await client.get(
        _series(run_id), params={"devices": "D00,D01"}, headers=API_KEY_HEADER
    )
    first = await client.post(
        PUSH,
        json=_body(run_id, devc_columns=columns, devc=[_devc_row(columns, 1.0)]),
        headers=API_KEY_HEADER,
    )
    assert first.json() == {"selected_devc": ["D00", "D01"]}

    await client.get(
        _series(run_id), params={"devices": "D00,D02"}, headers=API_KEY_HEADER
    )
    second = await client.post(
        PUSH,
        json=_body(run_id, devc=[_devc_row(columns, 2.0)]),
        headers=API_KEY_HEADER,
    )
    assert second.json() == {"selected_devc": ["D00", "D02"]}
    body = (
        await client.get(
            _series(run_id),
            params={"devices": "D00,D02,D01"},
            headers=API_KEY_HEADER,
        )
    ).json()
    assert [point["t"] for point in body["series"]["D00"]] == [1.0, 2.0]
    assert [point["t"] for point in body["series"]["D02"]] == [2.0]
    assert body["series"]["D01"] == []
    assert [column["id"] for column in body["devices"]] == ["D00", "D01", "D02"]


# --- Design curve from the runner (fds-runner ac6d225). Sent once as
# top-level design: [{t, hrr}] or null. Stored on the run. Returned as
# hrr.design, null when no list has been stored. Sample caps and the
# since cursor do not apply to it.


DESIGN = [{"t": 0.0, "hrr": 0.0}, {"t": 0.4, "hrr": 12.0}, {"t": 30.0, "hrr": 1000.0}]


@pytest.mark.asyncio
async def test_design_curve_is_stored_on_the_run_and_returned_as_hrr_design(
    client: AsyncClient,
):
    run_id = await _run(client)
    pushed = await client.post(
        PUSH,
        json=_body(
            run_id,
            hrr=[{"t": 1.0, "hrr": 10.0}],
            design=DESIGN,
        ),
        headers=API_KEY_HEADER,
    )
    assert pushed.status_code == 200
    assert pushed.json() == {"selected_devc": []}

    body = (
        await client.get(_series(run_id), params={"devices": ""}, headers=API_KEY_HEADER)
    ).json()
    assert body["hrr"]["design"] == DESIGN
    assert body["hrr"]["points"] == [{"t": 1.0, "v": 10.0}]
    assert body["hrr"]["unit"] == "kW"
    # Design is not a sample, so it does not consume the cursor.
    assert body["cursor"] == "1"

    again = await client.get(
        _series(run_id),
        params={"since": body["cursor"], "devices": ""},
        headers=API_KEY_HEADER,
    )
    assert again.json()["hrr"]["points"] == []
    assert again.json()["hrr"]["design"] == DESIGN
    assert again.json()["cursor"] == "1"


@pytest.mark.asyncio
async def test_design_is_kept_when_later_pushes_omit_it_or_send_null(
    client: AsyncClient,
):
    run_id = await _run(client)
    first = await client.post(
        PUSH,
        json=_body(run_id, design=DESIGN, hrr=[{"t": 1.0, "hrr": 1.0}]),
        headers=API_KEY_HEADER,
    )
    assert first.status_code == 200

    omitted = await client.post(
        PUSH,
        json=_body(run_id, hrr=[{"t": 2.0, "hrr": 2.0}]),
        headers=API_KEY_HEADER,
    )
    assert omitted.status_code == 200
    kept = (
        await client.get(_series(run_id), params={"devices": ""}, headers=API_KEY_HEADER)
    ).json()
    assert kept["hrr"]["design"] == DESIGN

    cleared = await client.post(
        PUSH,
        json=_body(run_id, design=None, hrr=[{"t": 3.0, "hrr": 3.0}]),
        headers=API_KEY_HEADER,
    )
    assert cleared.status_code == 200
    still = (
        await client.get(_series(run_id), params={"devices": ""}, headers=API_KEY_HEADER)
    ).json()
    assert still["hrr"]["design"] == DESIGN
    assert [point["t"] for point in still["hrr"]["points"]] == [1.0, 2.0, 3.0]


@pytest.mark.asyncio
async def test_a_later_design_list_replaces_the_stored_curve(client: AsyncClient):
    run_id = await _run(client)
    await client.post(
        PUSH, json=_body(run_id, design=DESIGN), headers=API_KEY_HEADER
    )
    replacement = [{"t": 0.0, "hrr": 0.0}, {"t": 10.0, "hrr": 500.0}]
    replaced = await client.post(
        PUSH, json=_body(run_id, design=replacement), headers=API_KEY_HEADER
    )
    assert replaced.status_code == 200
    body = (
        await client.get(_series(run_id), params={"devices": ""}, headers=API_KEY_HEADER)
    ).json()
    assert body["hrr"]["design"] == replacement
    assert body["cursor"] == "0"


@pytest.mark.asyncio
async def test_design_null_with_no_curve_stays_null(client: AsyncClient):
    run_id = await _run(client)
    pushed = await client.post(
        PUSH,
        json=_body(run_id, design=None, hrr=[{"t": 1.0, "hrr": 4.0}]),
        headers=API_KEY_HEADER,
    )
    assert pushed.status_code == 200
    body = (
        await client.get(_series(run_id), params={"devices": ""}, headers=API_KEY_HEADER)
    ).json()
    assert body["hrr"]["design"] is None
    assert body["hrr"]["points"] == [{"t": 1.0, "v": 4.0}]


@pytest.mark.asyncio
async def test_design_curves_do_not_cross_runs(client: AsyncClient):
    first = await _run(client, case_name="one.fds")
    second = await _run(client, case_name="two.fds")
    await client.post(
        PUSH, json=_body(first, design=DESIGN), headers=API_KEY_HEADER
    )
    await client.post(
        PUSH,
        json=_body(second, case_name="two.fds", chid="two", design=None),
        headers=API_KEY_HEADER,
    )
    one = (
        await client.get(_series(first), params={"devices": ""}, headers=API_KEY_HEADER)
    ).json()
    two = (
        await client.get(_series(second), params={"devices": ""}, headers=API_KEY_HEADER)
    ).json()
    assert one["hrr"]["design"] == DESIGN
    assert two["hrr"]["design"] is None


@pytest.mark.asyncio
async def test_design_is_not_thinned_or_capped_like_samples(client: AsyncClient):
    run_id = await _run(client)
    design = [{"t": i * 0.25, "hrr": float(i)} for i in range(61)]
    pushed = await client.post(
        PUSH, json=_body(run_id, design=design), headers=API_KEY_HEADER
    )
    assert pushed.status_code == 200
    body = (
        await client.get(_series(run_id), params={"devices": ""}, headers=API_KEY_HEADER)
    ).json()
    assert body["hrr"]["design"] == design
    assert body["hrr"]["points"] == []
    assert body["cursor"] == "0"


@pytest.mark.asyncio
async def test_non_finite_design_is_rejected_and_leaves_the_stored_curve(
    client: AsyncClient,
):
    run_id = await _run(client)
    stored = await client.post(
        PUSH, json=_body(run_id, design=DESIGN), headers=API_KEY_HEADER
    )
    assert stored.status_code == 200
    rejected = await client.post(
        PUSH,
        json=_body(run_id, design=[{"t": 1.0, "hrr": "NaN"}]),
        headers=API_KEY_HEADER,
    )
    assert rejected.status_code == 400
    body = (
        await client.get(_series(run_id), params={"devices": ""}, headers=API_KEY_HEADER)
    ).json()
    assert body["hrr"]["design"] == DESIGN


@pytest.mark.asyncio
async def test_completed_run_keeps_its_design_curve(client: AsyncClient):
    run_id = await _run(client)
    await client.post(
        PUSH,
        json=_body(run_id, design=DESIGN, hrr=[{"t": 1.0, "hrr": 40.0}]),
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
    body = (
        await client.get(_series(run_id), params={"devices": ""}, headers=API_KEY_HEADER)
    ).json()
    assert body["hrr"]["design"] == DESIGN
    assert body["hrr"]["points"] == [{"t": 1.0, "v": 40.0}]


# --- A finished run keeps the series. The same GET still works. ---


@pytest.mark.asyncio
async def test_completed_run_keeps_its_series(client: AsyncClient):
    run_id = await _run(client)
    await client.get(
        _series(run_id), params={"devices": "TC01"}, headers=API_KEY_HEADER
    )
    await client.post(
        PUSH,
        json=_body(
            run_id,
            hrr=[{"t": 1.0, "hrr": 40.0}, {"t": 2.0, "hrr": 80.0}],
            devc_columns=[{"id": "TC01", "quantity": "TEMPERATURE", "unit": "C"}],
            devc=[{"t": 2.0, "values": {"TC01": 33.0}}],
        ),
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

    body = (
        await client.get(
            _series(run_id), params={"devices": "TC01"}, headers=API_KEY_HEADER
        )
    ).json()
    assert body["hrr"]["points"] == [
        {"t": 1.0, "v": 40.0},
        {"t": 2.0, "v": 80.0},
    ]
    assert body["series"]["TC01"] == [{"t": 2.0, "v": 33.0}]
    assert body["hrr"]["design"] is None

    later = await client.post(
        PUSH,
        json=_body(run_id, hrr=[{"t": 3.0, "hrr": 90.0}]),
        headers=API_KEY_HEADER,
    )
    assert later.status_code == 200
    final = (
        await client.get(
            _series(run_id), params={"devices": "TC01"}, headers=API_KEY_HEADER
        )
    ).json()
    assert [point["t"] for point in final["hrr"]["points"]] == [1.0, 2.0, 3.0]


# --- CloudHPC seam stays off ---


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
    from pathlib import Path

    matches = list(Path("alembic/versions").glob("*run_series*.py"))
    assert len(matches) == 1
    body = matches[0].read_text()
    assert PHASE1_HEAD in body
    for name in (
        "run_series_columns",
        "run_series_points",
        "run_series_counters",
        "run_devc_selections",
        "run_hrr_designs",
    ):
        assert name in body
