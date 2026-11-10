"""Phase 1 modelling-runs dashboard: machines, runs, events, commands.

Red-green: these tests describe the contract in internal/phase-1-contract.md.
They fail until the routes, tables, and startup check exist.
"""

import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

TEST_DATABASE_URL = "sqlite+aiosqlite:///./test_modelling_runs.db"
DB_FILE = "./test_modelling_runs.db"
STARTUP_DB = "./test_modelling_runs_startup.db"

os.environ["DATABASE_URL"] = ""
os.environ["FDS_API_KEY"] = "test-key"

from database import Base  # noqa: E402
from models.cfd_models import CfdRunnerState, CfdSimulation  # noqa: E402, F401
from models.db_models import Element, Floor, Project  # noqa: E402, F401

API_KEY_HEADER = {"X-API-Key": "test-key"}
HEAD_REVISION = "e5f1a9c3d7b2"


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


async def _heartbeat(client: AsyncClient, machine_name: str, event: str = "heartbeat"):
    return await client.post(
        "/cfd-dashboard/status",
        json={"event": event, "machine_name": machine_name},
        headers=API_KEY_HEADER,
    )


async def _start_run(client: AsyncClient, machine_name: str, case_name: str, **extra):
    body = {
        "machine_name": machine_name,
        "case_name": case_name,
        "input_file_ref": f"s3://cases/{case_name}",
        "created_by": "ada",
    }
    body.update(extra)
    return await client.post("/cfd-dashboard/runs", json=body, headers=API_KEY_HEADER)


# --- Auth: the old unauthenticated GET /state is a known gap ---


@pytest.mark.asyncio
async def test_get_state_requires_api_key(client: AsyncClient):
    resp = await client.get("/cfd-dashboard/state")
    assert resp.status_code in (401, 403, 422)


@pytest.mark.asyncio
async def test_get_state_wrong_key_is_forbidden(client: AsyncClient):
    resp = await client.get("/cfd-dashboard/state", headers={"X-API-Key": "wrong-key"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_get_state_with_key_keeps_old_fields(client: AsyncClient):
    resp = await client.get("/cfd-dashboard/state", headers=API_KEY_HEADER)
    assert resp.status_code == 200
    state = resp.json()
    assert set(state) >= {"runner", "current", "queue", "completed", "errors"}
    assert state["runner"]["status"] == "offline"


@pytest.mark.asyncio
async def test_new_routes_reject_missing_or_wrong_key(client: AsyncClient):
    missing = await client.get("/cfd-dashboard/machines")
    assert missing.status_code in (401, 403, 422)
    wrong = await client.get(
        "/cfd-dashboard/runs", headers={"X-API-Key": "wrong-key"}
    )
    assert wrong.status_code == 403
    posted = await client.post(
        "/cfd-dashboard/runs",
        json={"machine_name": "Superbot", "case_name": "a.fds", "input_file_ref": "a"},
    )
    assert posted.status_code in (401, 403, 422)


# --- Machines: a second runner must not overwrite the first ---


@pytest.mark.asyncio
async def test_two_machines_do_not_overwrite_each_other(client: AsyncClient):
    first = await client.post(
        "/cfd-dashboard/status",
        json={
            "event": "runner_started",
            "machine_name": "Superbot",
            "data": {"pending_files": ["super.fds"], "machine_name": "Superbot"},
        },
        headers=API_KEY_HEADER,
    )
    assert first.status_code == 200
    second = await client.post(
        "/cfd-dashboard/status",
        json={
            "event": "runner_started",
            "machine_name": "Tinybot",
            "data": {"pending_files": ["tiny.fds"], "machine_name": "Tinybot"},
        },
        headers=API_KEY_HEADER,
    )
    assert second.status_code == 200

    state = (await client.get("/cfd-dashboard/state", headers=API_KEY_HEADER)).json()
    assert state["runner"]["machine_name"] == "Superbot"
    queue_names = [row["name"] for row in state["queue"]]
    assert "super.fds" in queue_names
    assert "tiny.fds" not in queue_names

    machines = (
        await client.get("/cfd-dashboard/machines", headers=API_KEY_HEADER)
    ).json()["machines"]
    by_name = {row["name"]: row for row in machines}
    assert set(by_name) == {"Superbot", "Tinybot"}
    assert by_name["Superbot"]["status"] == "online"
    assert by_name["Tinybot"]["status"] == "online"
    assert by_name["Superbot"]["target_type"] == "local"
    assert by_name["Tinybot"]["last_heartbeat_at"]


@pytest.mark.asyncio
async def test_runner_idle_and_stale_heartbeat(client: AsyncClient, test_engine):
    started = await _heartbeat(client, "Superbot", event="runner_started")
    assert started.status_code == 200
    idle = await _heartbeat(client, "Superbot", event="runner_idle")
    assert idle.status_code == 200
    machines = (
        await client.get("/cfd-dashboard/machines", headers=API_KEY_HEADER)
    ).json()["machines"]
    assert machines[0]["status"] == "idle"

    stale = (datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat()
    async with test_engine.begin() as conn:
        await conn.execute(
            text("UPDATE machines SET last_heartbeat_at = :ts"),
            {"ts": stale},
        )
    machines = (
        await client.get("/cfd-dashboard/machines", headers=API_KEY_HEADER)
    ).json()["machines"]
    assert machines[0]["status"] == "offline"


# --- Runs, events, commands ---


@pytest.mark.asyncio
async def test_start_queues_run_and_submit_command(client: AsyncClient):
    assert (await _heartbeat(client, "Superbot")).status_code == 200
    created = await _start_run(client, "Superbot", "warehouse.fds")
    assert created.status_code == 200
    run = created.json()
    assert run["status"] == "queued"
    assert run["target"] == "local"
    assert run["case_name"] == "warehouse.fds"
    assert run["input_file_ref"] == "s3://cases/warehouse.fds"
    assert run["created_by"] == "ada"
    assert run["progress_pct"] is None
    assert run["external_id"] is None
    assert run["cost_estimate"] is None
    assert run["cost_actual"] is None
    assert run["cost_currency"] is None
    run_id = run["id"]

    listed = (
        await client.get("/cfd-dashboard/runs", headers=API_KEY_HEADER)
    ).json()["runs"]
    assert [row["id"] for row in listed] == [run_id]

    polled = await client.get(
        "/cfd-dashboard/commands",
        params={"machine_name": "Superbot"},
        headers=API_KEY_HEADER,
    )
    assert polled.status_code == 200
    commands = polled.json()["commands"]
    assert len(commands) == 1
    assert commands[0]["command"] == "submit"
    assert commands[0]["status"] == "acked"
    assert commands[0]["run_id"] == run_id
    assert commands[0]["payload"]["case_name"] == "warehouse.fds"
    assert commands[0]["payload"]["input_file_ref"] == "s3://cases/warehouse.fds"
    assert commands[0]["payload"]["run_id"] == run_id

    again = await client.get(
        "/cfd-dashboard/commands",
        params={"machine_name": "Superbot"},
        headers=API_KEY_HEADER,
    )
    assert again.json()["commands"] == []

    unknown = await client.post(
        "/cfd-dashboard/runs",
        json={
            "machine_name": "Missingbot",
            "case_name": "nope.fds",
            "input_file_ref": "nope",
        },
        headers=API_KEY_HEADER,
    )
    assert unknown.status_code == 404


@pytest.mark.asyncio
async def test_sim_events_drive_run_status_and_detail_log(client: AsyncClient):
    assert (await _heartbeat(client, "Superbot")).status_code == 200
    run_id = (await _start_run(client, "Superbot", "warehouse.fds")).json()["id"]

    # Heartbeat must not move the queued run.
    beat = await client.post(
        "/cfd-dashboard/status",
        json={"event": "heartbeat", "machine_name": "Superbot", "run_id": run_id},
        headers=API_KEY_HEADER,
    )
    assert beat.status_code == 200
    detail = (
        await client.get(f"/cfd-dashboard/runs/{run_id}", headers=API_KEY_HEADER)
    ).json()
    assert detail["status"] == "queued"

    started = await client.post(
        "/cfd-dashboard/status",
        json={
            "event": "sim_started",
            "machine_name": "Superbot",
            "run_id": run_id,
            "case_name": "warehouse.fds",
            "message": "fds started",
        },
        headers=API_KEY_HEADER,
    )
    assert started.status_code == 200
    detail = (
        await client.get(f"/cfd-dashboard/runs/{run_id}", headers=API_KEY_HEADER)
    ).json()
    assert detail["status"] == "running"
    assert detail["started_at"]
    assert any(event["event_type"] == "sim_started" for event in detail["events"])
    assert any(event["message"] == "fds started" for event in detail["events"])

    progress = await client.post(
        "/cfd-dashboard/status",
        json={
            "event": "sim_progress",
            "machine_name": "Superbot",
            "run_id": run_id,
            "progress": 42.5,
            "sim_time": 12.0,
            "end_time": 300.0,
        },
        headers=API_KEY_HEADER,
    )
    assert progress.status_code == 200
    detail = (
        await client.get(f"/cfd-dashboard/runs/{run_id}", headers=API_KEY_HEADER)
    ).json()
    assert detail["status"] == "running"
    assert detail["progress_pct"] == 42.5
    assert detail["sim_time"] == 12.0
    assert detail["end_time"] == 300.0

    done = await client.post(
        "/cfd-dashboard/status",
        json={
            "event": "sim_completed",
            "machine_name": "Superbot",
            "run_id": run_id,
            "results_link": "s3://results/warehouse/",
            "sim_time": 300.0,
        },
        headers=API_KEY_HEADER,
    )
    assert done.status_code == 200
    detail = (
        await client.get(f"/cfd-dashboard/runs/{run_id}", headers=API_KEY_HEADER)
    ).json()
    assert detail["status"] == "completed"
    assert detail["results_link"] == "s3://results/warehouse/"
    assert detail["ended_at"]
    assert detail["sim_time"] == 300.0


@pytest.mark.asyncio
async def test_sim_error_marks_run_failed(client: AsyncClient):
    assert (await _heartbeat(client, "Tinybot")).status_code == 200
    run_id = (await _start_run(client, "Tinybot", "bad.fds")).json()["id"]
    await client.post(
        "/cfd-dashboard/status",
        json={"event": "sim_started", "machine_name": "Tinybot", "run_id": run_id},
        headers=API_KEY_HEADER,
    )
    failed = await client.post(
        "/cfd-dashboard/status",
        json={
            "event": "sim_error",
            "machine_name": "Tinybot",
            "run_id": run_id,
            "error": "Mesh overlap detected",
        },
        headers=API_KEY_HEADER,
    )
    assert failed.status_code == 200
    detail = (
        await client.get(f"/cfd-dashboard/runs/{run_id}", headers=API_KEY_HEADER)
    ).json()
    assert detail["status"] == "failed"
    assert detail["error"] == "Mesh overlap detected"


@pytest.mark.asyncio
async def test_stop_and_restart_commands(client: AsyncClient):
    assert (await _heartbeat(client, "Superbot")).status_code == 200
    run_id = (await _start_run(client, "Superbot", "warehouse.fds")).json()["id"]
    # Drain the submit so the next poll is only the stop.
    await client.get(
        "/cfd-dashboard/commands",
        params={"machine_name": "Superbot"},
        headers=API_KEY_HEADER,
    )

    too_soon = await client.post(
        f"/cfd-dashboard/runs/{run_id}/restart", headers=API_KEY_HEADER
    )
    assert too_soon.status_code == 400
    assert "restart" in too_soon.json()["detail"].lower()

    stopped = await client.post(
        f"/cfd-dashboard/runs/{run_id}/stop", headers=API_KEY_HEADER
    )
    assert stopped.status_code == 200
    still = (
        await client.get(f"/cfd-dashboard/runs/{run_id}", headers=API_KEY_HEADER)
    ).json()
    assert still["status"] == "queued"

    polled = (
        await client.get(
            "/cfd-dashboard/commands",
            params={"machine_name": "Superbot"},
            headers=API_KEY_HEADER,
        )
    ).json()["commands"]
    assert len(polled) == 1
    assert polled[0]["command"] == "stop"
    ack = await client.post(
        f"/cfd-dashboard/commands/{polled[0]['id']}/ack",
        json={"status": "done"},
        headers=API_KEY_HEADER,
    )
    assert ack.status_code == 200
    after_stop = (
        await client.get(f"/cfd-dashboard/runs/{run_id}", headers=API_KEY_HEADER)
    ).json()
    assert after_stop["status"] == "stopped"

    restart = await client.post(
        f"/cfd-dashboard/runs/{run_id}/restart", headers=API_KEY_HEADER
    )
    assert restart.status_code == 200
    polled = (
        await client.get(
            "/cfd-dashboard/commands",
            params={"machine_name": "Superbot"},
            headers=API_KEY_HEADER,
        )
    ).json()["commands"]
    assert polled[0]["command"] == "restart"
    assert polled[0]["run_id"] == run_id
    missing = await client.post(
        f"/cfd-dashboard/commands/{polled[0]['id']}/ack",
        json={
            "status": "failed",
            "error": "No FDS .restart file or DT_RESTART for this case",
        },
        headers=API_KEY_HEADER,
    )
    assert missing.status_code == 200
    detail = (
        await client.get(f"/cfd-dashboard/runs/{run_id}", headers=API_KEY_HEADER)
    ).json()
    assert detail["id"] == run_id
    assert detail["error"] == "No FDS .restart file or DT_RESTART for this case"
    assert any("DT_RESTART" in (event["message"] or "") for event in detail["events"])

    # A later successful restart stays on the same row and returns to running.
    restart = await client.post(
        f"/cfd-dashboard/runs/{run_id}/restart", headers=API_KEY_HEADER
    )
    assert restart.status_code == 200
    polled = (
        await client.get(
            "/cfd-dashboard/commands",
            params={"machine_name": "Superbot"},
            headers=API_KEY_HEADER,
        )
    ).json()["commands"]
    done = await client.post(
        f"/cfd-dashboard/commands/{polled[0]['id']}/ack",
        json={"status": "done"},
        headers=API_KEY_HEADER,
    )
    assert done.status_code == 200
    detail = (
        await client.get(f"/cfd-dashboard/runs/{run_id}", headers=API_KEY_HEADER)
    ).json()
    assert detail["id"] == run_id
    assert detail["status"] == "running"


@pytest.mark.asyncio
async def test_sim_stopped_marks_the_same_run_stopped(client: AsyncClient):
    assert (await _heartbeat(client, "Superbot")).status_code == 200
    run_id = (await _start_run(client, "Superbot", "warehouse.fds")).json()["id"]
    await client.post(
        "/cfd-dashboard/status",
        json={"event": "sim_started", "machine_name": "Superbot", "run_id": run_id},
        headers=API_KEY_HEADER,
    )
    stopped = await client.post(
        "/cfd-dashboard/status",
        json={
            "event": "sim_stopped",
            "machine_name": "Superbot",
            "run_id": run_id,
            "message": "process killed",
        },
        headers=API_KEY_HEADER,
    )
    assert stopped.status_code == 200
    detail = (
        await client.get(f"/cfd-dashboard/runs/{run_id}", headers=API_KEY_HEADER)
    ).json()
    assert detail["id"] == run_id
    assert detail["status"] == "stopped"
    assert detail["ended_at"]
    assert any(event["event_type"] == "sim_stopped" for event in detail["events"])


@pytest.mark.asyncio
async def test_runner_idle_refreshes_heartbeat_like_heartbeat(client: AsyncClient, test_engine):
    assert (await _heartbeat(client, "Superbot")).status_code == 200
    run_id = (await _start_run(client, "Superbot", "warehouse.fds")).json()["id"]
    await client.post(
        "/cfd-dashboard/status",
        json={"event": "sim_started", "machine_name": "Superbot", "run_id": run_id},
        headers=API_KEY_HEADER,
    )
    # heartbeat while a run is active: machine online, run status unchanged.
    beat = await _heartbeat(client, "Superbot", event="heartbeat")
    assert beat.status_code == 200
    detail = (
        await client.get(f"/cfd-dashboard/runs/{run_id}", headers=API_KEY_HEADER)
    ).json()
    assert detail["status"] == "running"
    machines = (
        await client.get("/cfd-dashboard/machines", headers=API_KEY_HEADER)
    ).json()["machines"]
    assert machines[0]["status"] == "online"

    stale = (datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat()
    async with test_engine.begin() as conn:
        await conn.execute(
            text("UPDATE machines SET last_heartbeat_at = :ts"),
            {"ts": stale},
        )
    offline = (
        await client.get("/cfd-dashboard/machines", headers=API_KEY_HEADER)
    ).json()["machines"]
    assert offline[0]["status"] == "offline"

    idle = await _heartbeat(client, "Superbot", event="runner_idle")
    assert idle.status_code == 200
    refreshed = (
        await client.get("/cfd-dashboard/machines", headers=API_KEY_HEADER)
    ).json()["machines"][0]
    assert refreshed["status"] == "idle"
    assert refreshed["last_heartbeat_at"]
    seen = datetime.fromisoformat(refreshed["last_heartbeat_at"])
    if seen.tzinfo is None:
        seen = seen.replace(tzinfo=timezone.utc)
    assert (datetime.now(timezone.utc) - seen).total_seconds() < 30
    # Idle must not stop the run. The runner only sends this when nothing is active,
    # but a late idle event is not itself a stop.
    detail = (
        await client.get(f"/cfd-dashboard/runs/{run_id}", headers=API_KEY_HEADER)
    ).json()
    assert detail["status"] == "running"


@pytest.mark.asyncio
async def test_legacy_status_names_mirror_onto_the_run(client: AsyncClient):
    assert (await _heartbeat(client, "Superbot")).status_code == 200
    run_id = (await _start_run(client, "Superbot", "warehouse.fds")).json()["id"]
    started = await client.post(
        "/cfd-dashboard/status",
        json={
            "event": "sim_started",
            "data": {"name": "warehouse.fds", "t_end": 600, "machine_name": "Superbot"},
        },
        headers=API_KEY_HEADER,
    )
    assert started.status_code == 200
    detail = (
        await client.get(f"/cfd-dashboard/runs/{run_id}", headers=API_KEY_HEADER)
    ).json()
    assert detail["case_name"] == "warehouse.fds"
    assert detail["status"] == "running"
    # t_end is the legacy name for end_time.
    assert detail["end_time"] == 600

    progress = await client.post(
        "/cfd-dashboard/status",
        json={
            "event": "sim_progress",
            "data": {
                "name": "warehouse.fds",
                "progress_pct": 15,
                "machine_name": "Superbot",
            },
        },
        headers=API_KEY_HEADER,
    )
    assert progress.status_code == 200
    detail = (
        await client.get(f"/cfd-dashboard/runs/{run_id}", headers=API_KEY_HEADER)
    ).json()
    assert detail["progress_pct"] == 15

    failed = await client.post(
        "/cfd-dashboard/status",
        json={
            "event": "sim_error",
            "data": {
                "name": "warehouse.fds",
                "error_msg": "mesh overlap",
                "machine_name": "Superbot",
            },
        },
        headers=API_KEY_HEADER,
    )
    assert failed.status_code == 200
    detail = (
        await client.get(f"/cfd-dashboard/runs/{run_id}", headers=API_KEY_HEADER)
    ).json()
    assert detail["status"] == "failed"
    assert detail["error"] == "mesh overlap"

    # The old dashboard still reads t_end / error_msg / name.
    state = (await client.get("/cfd-dashboard/state", headers=API_KEY_HEADER)).json()
    legacy = next(row for row in state["errors"] if row["name"] == "warehouse.fds")
    assert legacy["error_msg"] == "mesh overlap"
    assert legacy["t_end"] == 600


@pytest.mark.asyncio
async def test_submit_ack_done_means_fds_started(client: AsyncClient):
    assert (await _heartbeat(client, "Superbot")).status_code == 200
    created = await _start_run(
        client, "Superbot", "warehouse.fds", input_file_ref=r"D:\fds\cases\warehouse.fds"
    )
    assert created.status_code == 200
    run_id = created.json()["id"]
    polled = await client.get(
        "/cfd-dashboard/commands",
        params={"machine_name": "Superbot"},
        headers=API_KEY_HEADER,
    )
    assert polled.status_code == 200
    body = polled.json()
    assert "commands" in body
    cmd = body["commands"][0]
    assert set(cmd) >= {"id", "command", "run_id", "payload"}
    assert cmd["command"] == "submit"
    assert cmd["run_id"] == run_id
    assert cmd["payload"]["input_file_ref"] == r"D:\fds\cases\warehouse.fds"

    ack = await client.post(
        f"/cfd-dashboard/commands/{cmd['id']}/ack",
        json={"status": "done"},
        headers=API_KEY_HEADER,
    )
    assert ack.status_code == 200
    detail = (
        await client.get(f"/cfd-dashboard/runs/{run_id}", headers=API_KEY_HEADER)
    ).json()
    assert detail["status"] == "running"
    assert detail["ended_at"] is None
    assert detail["status"] != "completed"


@pytest.mark.asyncio
async def test_restart_failed_ack_is_not_sim_error(client: AsyncClient):
    assert (await _heartbeat(client, "Superbot")).status_code == 200
    run_id = (await _start_run(client, "Superbot", "warehouse.fds")).json()["id"]
    await client.post(
        "/cfd-dashboard/status",
        json={"event": "sim_stopped", "machine_name": "Superbot", "run_id": run_id},
        headers=API_KEY_HEADER,
    )
    await client.get(
        "/cfd-dashboard/commands",
        params={"machine_name": "Superbot"},
        headers=API_KEY_HEADER,
    )
    restart = await client.post(
        f"/cfd-dashboard/runs/{run_id}/restart", headers=API_KEY_HEADER
    )
    assert restart.status_code == 200
    polled = (
        await client.get(
            "/cfd-dashboard/commands",
            params={"machine_name": "Superbot"},
            headers=API_KEY_HEADER,
        )
    ).json()["commands"]
    assert polled[0]["command"] == "restart"
    assert polled[0]["run_id"] == run_id
    ack = await client.post(
        f"/cfd-dashboard/commands/{polled[0]['id']}/ack",
        json={"status": "failed", "error": "No .restart file and no DT_RESTART"},
        headers=API_KEY_HEADER,
    )
    assert ack.status_code == 200
    detail = (
        await client.get(f"/cfd-dashboard/runs/{run_id}", headers=API_KEY_HEADER)
    ).json()
    assert detail["id"] == run_id
    assert detail["status"] == "stopped"
    assert detail["error"] == "No .restart file and no DT_RESTART"
    assert not any(event["event_type"] == "sim_error" for event in detail["events"])


@pytest.mark.asyncio
async def test_run_filters_and_search_logging(client: AsyncClient, caplog):
    assert (await _heartbeat(client, "Superbot")).status_code == 200
    assert (await _heartbeat(client, "Tinybot")).status_code == 200
    super_id = (await _start_run(client, "Superbot", "warehouse.fds")).json()["id"]
    tiny = (await _start_run(client, "Tinybot", "atrium.fds")).json()
    tiny_id = tiny["id"]
    machine_id = tiny["machine_id"]

    caplog.set_level(logging.INFO, logger="routers.cfd_dashboard")
    found = await client.get(
        "/cfd-dashboard/runs",
        params={"q": "warehouse", "user": "ada", "target": "local", "status": "queued"},
        headers=API_KEY_HEADER,
    )
    assert found.status_code == 200
    assert [row["id"] for row in found.json()["runs"]] == [super_id]
    search_logs = [
        record.message
        for record in caplog.records
        if record.name == "routers.cfd_dashboard" and "modelling_run_search" in record.message
    ]
    assert search_logs
    assert "warehouse" in search_logs[-1]
    assert "ada" in search_logs[-1]

    by_machine = await client.get(
        "/cfd-dashboard/runs",
        params={"machine_id": machine_id},
        headers=API_KEY_HEADER,
    )
    assert [row["id"] for row in by_machine.json()["runs"]] == [tiny_id]

    caplog.clear()
    opened = await client.get(
        f"/cfd-dashboard/runs/{super_id}",
        params={"from": "search", "q": "warehouse", "user": "ada"},
        headers=API_KEY_HEADER,
    )
    assert opened.status_code == 200
    open_logs = [
        record.message
        for record in caplog.records
        if "modelling_run_search_open" in record.message
    ]
    assert open_logs
    assert super_id in open_logs[-1]
    assert "warehouse" in open_logs[-1]
    assert "ada" in open_logs[-1]


@pytest.mark.asyncio
async def test_legacy_nested_status_still_works(client: AsyncClient):
    resp = await client.post(
        "/cfd-dashboard/status",
        json={
            "event": "sim_started",
            "data": {"name": "case1.fds", "meshes": 4, "t_end": 300.0},
        },
        headers=API_KEY_HEADER,
    )
    assert resp.status_code == 200
    state = (await client.get("/cfd-dashboard/state", headers=API_KEY_HEADER)).json()
    assert state["current"]["name"] == "case1.fds"
    assert state["current"]["status"] == "running"
    assert state["current"]["meshes"] == 4
    assert state["current"]["t_end"] == 300.0


@pytest.mark.asyncio
async def test_cloudhpc_start_is_rejected(client: AsyncClient, test_engine):
    from models.cfd_models import Machine

    factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        machine = Machine(
            name="Cloud-1",
            target_type="cloudhpc",
            status="idle",
            last_heartbeat_at=datetime.now(timezone.utc),
        )
        session.add(machine)
        await session.commit()
        machine_id = str(machine.id)

    resp = await client.post(
        "/cfd-dashboard/runs",
        json={
            "machine_id": machine_id,
            "case_name": "paid.fds",
            "input_file_ref": "cloud://paid.fds",
            "created_by": "ada",
        },
        headers=API_KEY_HEADER,
    )
    assert resp.status_code == 400
    assert "cloud" in resp.json()["detail"].lower()
    listed = (await client.get("/cfd-dashboard/runs", headers=API_KEY_HEADER)).json()
    assert listed["runs"] == []


def test_cloudhpc_flag_defaults_off():
    from services.modelling_runs import CLOUDHPC_ENABLED

    assert CLOUDHPC_ENABLED is False


def test_health_lists_modelling_tables():
    from services.health_service import REQUIRED_TABLES

    for name in (
        "machines",
        "runs",
        "run_events",
        "run_commands",
        "run_series_columns",
        "run_series_points",
        "run_series_counters",
        "run_devc_selections",
    ):
        assert name in REQUIRED_TABLES


def test_alembic_revision_follows_current_head():
    versions = Path("alembic/versions")
    matches = list(versions.glob("*modelling_run*.py"))
    assert matches, "alembic revision for modelling-run tables is missing"
    text_body = matches[0].read_text()
    assert f"down_revision: str | Sequence[str] | None = '{HEAD_REVISION}'" in text_body or (
        f"down_revision: Union[str, None] = '{HEAD_REVISION}'" in text_body
    )


@pytest.mark.asyncio
async def test_startup_creates_modelling_tables_and_is_idempotent(monkeypatch):
    import database
    import main

    if os.path.exists(STARTUP_DB):
        os.remove(STARTUP_DB)
    engine = create_async_engine(f"sqlite+aiosqlite:///{STARTUP_DB}", echo=False)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "async_session", factory)

    try:
        await main._ensure_modelling_run_tables()
        await main._ensure_modelling_run_tables()

        async with engine.connect() as conn:
            names = set(await conn.run_sync(lambda sync: inspect(sync).get_table_names()))
        for table in (
            "machines",
            "runs",
            "run_events",
            "run_commands",
            "run_series_columns",
            "run_series_points",
            "run_series_counters",
            "run_devc_selections",
        ):
            assert table in names
    finally:
        await engine.dispose()
        if os.path.exists(STARTUP_DB):
            os.remove(STARTUP_DB)


@pytest.mark.asyncio
async def test_startup_fails_loudly_when_tables_are_missing(monkeypatch):
    import database
    import main

    db_path = "./test_modelling_runs_missing.db"
    if os.path.exists(db_path):
        os.remove(db_path)
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", echo=False)
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(Base.metadata, "create_all", lambda *args, **kwargs: None)

    try:
        with pytest.raises(RuntimeError, match="machines") as missing:
            await main._ensure_modelling_run_tables()
        assert "run_series_points" in str(missing.value)
    finally:
        await engine.dispose()
        if os.path.exists(db_path):
            os.remove(db_path)
