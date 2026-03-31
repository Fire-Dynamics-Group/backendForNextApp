"""Tests for CFD simulation monitoring dashboard endpoints."""

import os

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

TEST_DATABASE_URL = "sqlite+aiosqlite:///./test_cfd_dashboard.db"

os.environ["DATABASE_URL"] = ""  # prevent real DB connection
os.environ["FDS_API_KEY"] = "test-key"

from database import Base  # noqa: E402
from models.cfd_models import CfdRunnerState, CfdSimulation  # noqa: E402, F401
from models.db_models import Project, Floor, Element  # noqa: E402, F401


# --- Fixtures ---


@pytest_asyncio.fixture
async def test_engine():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()
    if os.path.exists("./test_cfd_dashboard.db"):
        os.remove("./test_cfd_dashboard.db")


@pytest_asyncio.fixture
async def client(test_engine):
    """Create a test client with overridden DB dependency."""
    import database
    from main import app

    session_factory = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[database.get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


API_KEY_HEADER = {"X-API-Key": "test-key"}


# --- Test 1: runner_started with valid key returns 200 ---


@pytest.mark.asyncio
async def test_runner_started_valid_key(client: AsyncClient):
    resp = await client.post(
        "/cfd-dashboard/status",
        json={
            "event": "runner_started",
            "data": {"pending_files": ["sim_a.fds", "sim_b.fds"]},
        },
        headers=API_KEY_HEADER,
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


# --- Test 2: missing API key returns 403 (or 422 since header is required) ---


@pytest.mark.asyncio
async def test_status_without_api_key(client: AsyncClient):
    resp = await client.post(
        "/cfd-dashboard/status",
        json={"event": "runner_started", "data": {}},
    )
    # FastAPI returns 422 when a required header is missing
    assert resp.status_code in (401, 403, 422)


# --- Test 3: wrong API key returns 403 ---


@pytest.mark.asyncio
async def test_status_with_wrong_api_key(client: AsyncClient):
    resp = await client.post(
        "/cfd-dashboard/status",
        json={"event": "runner_started", "data": {}},
        headers={"X-API-Key": "wrong-key"},
    )
    assert resp.status_code == 403


# --- Test 4: sim_started creates a running simulation ---


@pytest.mark.asyncio
async def test_sim_started_creates_running_sim(client: AsyncClient):
    # First start the runner so heartbeat row exists
    await client.post(
        "/cfd-dashboard/status",
        json={"event": "runner_started", "data": {"pending_files": ["case1.fds"]}},
        headers=API_KEY_HEADER,
    )
    # Start simulation
    resp = await client.post(
        "/cfd-dashboard/status",
        json={
            "event": "sim_started",
            "data": {"name": "case1.fds", "meshes": 4, "t_end": 300.0},
        },
        headers=API_KEY_HEADER,
    )
    assert resp.status_code == 200

    # Verify via GET /state
    state_resp = await client.get("/cfd-dashboard/state")
    state = state_resp.json()
    assert state["current"] is not None
    assert state["current"]["name"] == "case1.fds"
    assert state["current"]["status"] == "running"
    assert state["current"]["meshes"] == 4
    assert state["current"]["t_end"] == 300.0


# --- Test 5: sim_progress updates progress ---


@pytest.mark.asyncio
async def test_sim_progress_updates(client: AsyncClient):
    await client.post(
        "/cfd-dashboard/status",
        json={"event": "runner_started", "data": {"pending_files": ["case2.fds"]}},
        headers=API_KEY_HEADER,
    )
    await client.post(
        "/cfd-dashboard/status",
        json={
            "event": "sim_started",
            "data": {"name": "case2.fds", "meshes": 2, "t_end": 600.0},
        },
        headers=API_KEY_HEADER,
    )
    resp = await client.post(
        "/cfd-dashboard/status",
        json={
            "event": "sim_progress",
            "data": {"name": "case2.fds", "progress_pct": 45.5},
        },
        headers=API_KEY_HEADER,
    )
    assert resp.status_code == 200

    state = (await client.get("/cfd-dashboard/state")).json()
    assert state["current"]["progress_pct"] == 45.5


# --- Test 6: sim_completed marks simulation completed ---


@pytest.mark.asyncio
async def test_sim_completed(client: AsyncClient):
    await client.post(
        "/cfd-dashboard/status",
        json={"event": "runner_started", "data": {"pending_files": ["case3.fds"]}},
        headers=API_KEY_HEADER,
    )
    await client.post(
        "/cfd-dashboard/status",
        json={
            "event": "sim_started",
            "data": {"name": "case3.fds", "meshes": 1, "t_end": 100.0},
        },
        headers=API_KEY_HEADER,
    )
    resp = await client.post(
        "/cfd-dashboard/status",
        json={"event": "sim_completed", "data": {"name": "case3.fds"}},
        headers=API_KEY_HEADER,
    )
    assert resp.status_code == 200

    state = (await client.get("/cfd-dashboard/state")).json()
    # No longer running
    assert state["current"] is None
    # Should appear in completed list
    assert any(s["name"] == "case3.fds" for s in state["completed"])
    completed_sim = next(s for s in state["completed"] if s["name"] == "case3.fds")
    assert completed_sim["status"] == "completed"
    assert completed_sim["completed_at"] is not None


# --- Test 7: GET /state returns correct structure ---


@pytest.mark.asyncio
async def test_get_state_structure(client: AsyncClient):
    state = (await client.get("/cfd-dashboard/state")).json()
    assert "runner" in state
    assert "current" in state
    assert "queue" in state
    assert "completed" in state
    assert "errors" in state
    assert state["runner"]["status"] == "offline"
    assert state["current"] is None
    assert state["queue"] == []
    assert state["completed"] == []
    assert state["errors"] == []


# --- Test 8: runner_started inserts queued simulations ---


@pytest.mark.asyncio
async def test_runner_started_creates_queued_sims(client: AsyncClient):
    await client.post(
        "/cfd-dashboard/status",
        json={
            "event": "runner_started",
            "data": {"pending_files": ["alpha.fds", "beta.fds"]},
        },
        headers=API_KEY_HEADER,
    )

    state = (await client.get("/cfd-dashboard/state")).json()
    queue_names = [s["name"] for s in state["queue"]]
    assert "alpha.fds" in queue_names
    assert "beta.fds" in queue_names


# --- Test 9: sim_error marks simulation as error ---


@pytest.mark.asyncio
async def test_sim_error(client: AsyncClient):
    await client.post(
        "/cfd-dashboard/status",
        json={"event": "runner_started", "data": {"pending_files": ["bad.fds"]}},
        headers=API_KEY_HEADER,
    )
    await client.post(
        "/cfd-dashboard/status",
        json={
            "event": "sim_started",
            "data": {"name": "bad.fds", "meshes": 1, "t_end": 50.0},
        },
        headers=API_KEY_HEADER,
    )
    resp = await client.post(
        "/cfd-dashboard/status",
        json={
            "event": "sim_error",
            "data": {"name": "bad.fds", "error_msg": "Mesh overlap detected"},
        },
        headers=API_KEY_HEADER,
    )
    assert resp.status_code == 200

    state = (await client.get("/cfd-dashboard/state")).json()
    assert state["current"] is None
    assert any(s["name"] == "bad.fds" for s in state["errors"])
    error_sim = next(s for s in state["errors"] if s["name"] == "bad.fds")
    assert error_sim["error_msg"] == "Mesh overlap detected"


# --- Test 10: runner_idle clears pending_files ---


@pytest.mark.asyncio
async def test_runner_idle(client: AsyncClient):
    await client.post(
        "/cfd-dashboard/status",
        json={
            "event": "runner_started",
            "data": {"pending_files": ["x.fds"]},
        },
        headers=API_KEY_HEADER,
    )
    resp = await client.post(
        "/cfd-dashboard/status",
        json={"event": "runner_idle", "data": {}},
        headers=API_KEY_HEADER,
    )
    assert resp.status_code == 200

    state = (await client.get("/cfd-dashboard/state")).json()
    assert state["runner"]["status"] == "idle"
