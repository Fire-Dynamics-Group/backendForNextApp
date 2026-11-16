"""Tests for project persistence: DB models, API endpoints, and S3 service."""
import asyncio
import os
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Use SQLite for tests (no Postgres required)
TEST_DATABASE_URL = "sqlite+aiosqlite:///./test_projects.db"

# Patch database module before importing app
os.environ["DATABASE_URL"] = ""  # prevent real DB connection

from database import Base  # noqa: E402
from models.db_models import Element, Floor, Project  # noqa: E402, F401


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
    # Clean up test db file
    if os.path.exists("./test_projects.db"):
        os.remove("./test_projects.db")


@pytest_asyncio.fixture
async def test_session(test_engine):
    session_factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def client(test_engine):
    """Create a test client with overridden DB dependency."""
    import database
    from main import app

    session_factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

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


# --- ORM unit tests ---

@pytest.mark.asyncio
async def test_create_project(test_session: AsyncSession):
    project = Project(name="Test Project", settings={"scenarioType": "MOE"})
    test_session.add(project)
    await test_session.commit()
    await test_session.refresh(project)

    assert project.id is not None
    assert project.name == "Test Project"
    assert project.settings["scenarioType"] == "MOE"


@pytest.mark.asyncio
async def test_create_floor_with_elements(test_session: AsyncSession):
    project = Project(name="Floor Test")
    test_session.add(project)
    await test_session.commit()
    await test_session.refresh(project)

    floor = Floor(
        project_id=project.id,
        floor_number=0,
        name="Fire Floor",
        pixels_per_mesh=2.5,
        settings={"doorRoles": {}},
    )
    test_session.add(floor)
    await test_session.commit()
    await test_session.refresh(floor)

    element = Element(
        floor_id=floor.id,
        element_index=0,
        type="polyline",
        points=[{"x": 0, "y": 0}, {"x": 100, "y": 0}],
        comments="obstruction",
    )
    test_session.add(element)
    await test_session.commit()
    await test_session.refresh(element)

    assert floor.id is not None
    assert element.floor_id == floor.id
    assert element.points == [{"x": 0, "y": 0}, {"x": 100, "y": 0}]


@pytest.mark.asyncio
async def test_cascade_delete(test_session: AsyncSession):
    """Deleting a project should cascade to floors and elements."""
    from sqlalchemy import select

    project = Project(name="Cascade Test")
    test_session.add(project)
    await test_session.commit()
    await test_session.refresh(project)

    floor = Floor(project_id=project.id, floor_number=0, name="Ground")
    test_session.add(floor)
    await test_session.commit()
    await test_session.refresh(floor)

    element = Element(
        floor_id=floor.id, element_index=0, type="rect",
        points=[{"x": 0, "y": 0}], comments="mesh",
    )
    test_session.add(element)
    await test_session.commit()

    floor_id = floor.id
    await test_session.delete(project)
    await test_session.commit()

    result = await test_session.execute(select(Element).where(Element.floor_id == floor_id))
    assert result.scalars().all() == []


# --- API endpoint tests ---

@pytest.mark.asyncio
async def test_api_create_and_list_projects(client: AsyncClient):
    resp = await client.post("/projects", json={"name": "API Test", "settings": {"a": 1}})
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "API Test"
    project_id = data["id"]

    resp = await client.get("/projects")
    assert resp.status_code == 200
    projects = resp.json()
    assert any(p["id"] == project_id for p in projects)


@pytest.mark.asyncio
async def test_api_get_project_detail(client: AsyncClient):
    resp = await client.post("/projects", json={"name": "Detail Test"})
    project_id = resp.json()["id"]

    resp = await client.get(f"/projects/{project_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Detail Test"
    assert "floors" in data


@pytest.mark.asyncio
async def test_api_update_project(client: AsyncClient):
    resp = await client.post("/projects", json={"name": "Update Test"})
    project_id = resp.json()["id"]

    resp = await client.put(f"/projects/{project_id}", json={"name": "Updated Name"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "Updated Name"


@pytest.mark.asyncio
async def test_api_delete_project(client: AsyncClient):
    resp = await client.post("/projects", json={"name": "Delete Test"})
    project_id = resp.json()["id"]

    resp = await client.delete(f"/projects/{project_id}")
    assert resp.status_code == 204

    resp = await client.get(f"/projects/{project_id}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_api_bulk_save(client: AsyncClient):
    resp = await client.post("/projects", json={"name": "Save Test"})
    project_id = resp.json()["id"]

    save_payload = {
        "name": "Save Test Updated",
        "settings": {"scenarioType": "MOE", "simEndTime": 600},
        "floors": [
            {
                "floor_number": 0,
                "name": "Fire Floor",
                "pixels_per_mesh": 2.0,
                "settings": {"doorRoles": {"door1": "apartment"}},
                "elements": [
                    {
                        "element_index": 0,
                        "type": "polyline",
                        "points": [{"x": 0, "y": 0}, {"x": 100, "y": 50}],
                        "comments": "obstruction",
                    },
                    {
                        "element_index": 1,
                        "type": "polyline",
                        "points": [{"x": 10, "y": 10}, {"x": 20, "y": 10}],
                        "comments": "door",
                    },
                ],
            },
            {
                "floor_number": 1,
                "name": "Level 1",
                "elements": [],
            },
        ],
    }

    resp = await client.post(f"/projects/{project_id}/save", json=save_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Save Test Updated"
    assert len(data["floors"]) == 2

    # Verify floor detail has elements
    floor_id = data["floors"][0]["id"]
    resp = await client.get(f"/projects/{project_id}/floors/{floor_id}")
    assert resp.status_code == 200
    floor_data = resp.json()
    assert len(floor_data["elements"]) == 2
    assert floor_data["elements"][0]["comments"] == "obstruction"


@pytest.mark.asyncio
async def test_save_preserves_floor_id(client: AsyncClient):
    """Floor ids must be stable across saves.

    The frontend caches floorId (from the first save) and reuses it for PDF
    upload/fetch. A delete-then-recreate save mints a new floor uuid each time,
    leaving that cached id stale -> mid-session PDF calls 404. Saving the same
    floor_number twice must keep the same floor id.
    """
    resp = await client.post("/projects", json={"name": "Stable Floor"})
    project_id = resp.json()["id"]

    payload = {
        "settings": {},
        "floors": [{"floor_number": 0, "name": "Fire Floor", "elements": [
            {"element_index": 0, "type": "polyline", "points": [{"x": 0, "y": 0}], "comments": "obstruction"},
        ]}],
    }
    first = await client.post(f"/projects/{project_id}/save", json=payload)
    second = await client.post(f"/projects/{project_id}/save", json=payload)

    assert second.json()["floors"][0]["id"] == first.json()["floors"][0]["id"]


@pytest.mark.asyncio
async def test_save_preserves_pdf_key_and_updates_elements(client: AsyncClient, test_session: AsyncSession):
    """A re-save must keep a previously-attached PDF and apply element edits.

    The PDF is attached out-of-band (S3 upload sets pdf_s3_key); here we set it
    directly. A subsequent save that adds an element must not drop the PDF.
    """
    from sqlalchemy import select

    resp = await client.post("/projects", json={"name": "PDF Keep"})
    project_id = resp.json()["id"]
    payload = {"settings": {}, "floors": [{"floor_number": 0, "name": "F", "elements": [
        {"element_index": 0, "type": "rect", "points": [{"x": 0, "y": 0}], "comments": "mesh"},
    ]}]}
    first = await client.post(f"/projects/{project_id}/save", json=payload)
    floor_id = first.json()["floors"][0]["id"]

    floor = (await test_session.execute(
        select(Floor).where(Floor.id == uuid.UUID(floor_id))
    )).scalar_one()
    floor.pdf_s3_key = "plans/floor0.pdf"
    await test_session.commit()

    payload["floors"][0]["elements"].append(
        {"element_index": 1, "type": "point", "points": [{"x": 5, "y": 5}], "comments": "fire"}
    )
    await client.post(f"/projects/{project_id}/save", json=payload)

    detail = (await client.get(f"/projects/{project_id}/floors/{floor_id}")).json()
    assert detail["pdf_s3_key"] == "plans/floor0.pdf"
    assert len(detail["elements"]) == 2


@pytest.mark.asyncio
async def test_save_removes_floor_dropped_from_payload(client: AsyncClient):
    """A floor no longer present in the payload is deleted (cascading elements)."""
    resp = await client.post("/projects", json={"name": "Drop Floor"})
    project_id = resp.json()["id"]

    two = await client.post(f"/projects/{project_id}/save", json={"settings": {}, "floors": [
        {"floor_number": 0, "name": "Fire", "elements": []},
        {"floor_number": 1, "name": "Level 1", "elements": []},
    ]})
    floor0_id = next(f["id"] for f in two.json()["floors"] if f["floor_number"] == 0)

    one = await client.post(f"/projects/{project_id}/save", json={"settings": {}, "floors": [
        {"floor_number": 0, "name": "Fire", "elements": []},
    ]})
    floors = one.json()["floors"]
    assert len(floors) == 1
    assert floors[0]["id"] == floor0_id  # surviving floor kept its id


def _is_project_load(statement) -> bool:
    descriptions = getattr(statement, "column_descriptions", None) or []
    return any(d.get("entity") is Project for d in descriptions)


def _hold_both_project_loads(monkeypatch):
    """Release both saves only after each has loaded the project.

    Without this, SQLite often runs one request to commit before the other
    starts, which hides the check-then-insert race on uq_project_floor.
    """
    release = asyncio.Event()
    state = {"n": 0}
    real_execute = AsyncSession.execute

    async def gated_execute(self, statement, *args, **kwargs):
        result = await real_execute(self, statement, *args, **kwargs)
        if _is_project_load(statement):
            state["n"] += 1
            if state["n"] >= 2:
                release.set()
            await release.wait()
        return result

    monkeypatch.setattr(AsyncSession, "execute", gated_execute)
    return state


def _save_snapshot(result) -> str:
    if isinstance(result, Exception):
        return f"{type(result).__name__}: {result}"
    return f"{result.status_code} {result.text}"


@pytest.mark.asyncio
async def test_save_duplicate_floor_numbers_does_not_500(client: AsyncClient):
    """One payload that lists the same floor_number twice must not 500.

    save_project inserts a floor when its in-memory map misses that number,
    and it does not put the row it just inserted back into the map. The second
    copy inserts again and Postgres raises UniqueViolation on uq_project_floor.
    """
    resp = await client.post("/projects", json={"name": "Duplicate floors"})
    project_id = resp.json()["id"]

    resp = await client.post(f"/projects/{project_id}/save", json={
        "settings": {"scenarioType": "MOE"},
        "floors": [
            {
                "floor_number": 0,
                "name": "First copy",
                "elements": [
                    {"element_index": 0, "type": "polyline", "points": [{"x": 0, "y": 0}], "comments": "drop-me"},
                ],
            },
            {
                "floor_number": 0,
                "name": "Kept copy",
                "pixels_per_mesh": 3.5,
                "elements": [
                    {"element_index": 0, "type": "rect", "points": [{"x": 1, "y": 1}], "comments": "keep-me"},
                ],
            },
        ],
    })
    assert resp.status_code == 200, resp.text
    floors = resp.json()["floors"]
    assert len(floors) == 1
    assert floors[0]["floor_number"] == 0
    assert floors[0]["name"] == "Kept copy"
    floor_id = floors[0]["id"]

    detail = (await client.get(f"/projects/{project_id}/floors/{floor_id}")).json()
    assert detail["pixels_per_mesh"] == 3.5
    assert [el["comments"] for el in detail["elements"]] == ["keep-me"]

    # The collapsed floor keeps its id on the next save.
    again = await client.post(f"/projects/{project_id}/save", json={
        "settings": {"scenarioType": "MOE"},
        "floors": [{"floor_number": 0, "name": "Kept copy", "elements": [
            {"element_index": 0, "type": "rect", "points": [{"x": 1, "y": 1}], "comments": "keep-me"},
        ]}],
    })
    assert again.status_code == 200, again.text
    assert again.json()["floors"][0]["id"] == floor_id


@pytest.mark.asyncio
async def test_overlapping_saves_of_a_new_floor_do_not_500(client: AsyncClient, monkeypatch):
    """Two saves that both loaded no floors must not both INSERT floor 0.

    A handoff project has no floor until the first save. Autosave and the PDF
    upload can both pass that check before either commits, and the loser's
    INSERT hits uq_project_floor. Both requests should succeed and leave one
    floor row (the same id).
    """
    resp = await client.post("/projects", json={"name": "Overlapping save"})
    assert resp.status_code == 201, resp.text
    project_id = resp.json()["id"]
    _hold_both_project_loads(monkeypatch)

    payload = {
        "settings": {},
        "floors": [{"floor_number": 0, "name": "Fire Floor", "elements": [
            {"element_index": 0, "type": "polyline", "points": [{"x": 0, "y": 0}], "comments": "obstruction"},
        ]}],
    }
    results = await asyncio.wait_for(
        asyncio.gather(
            client.post(f"/projects/{project_id}/save", json=payload),
            client.post(f"/projects/{project_id}/save", json={**payload, "name": "Second saver"}),
            return_exceptions=True,
        ),
        timeout=8,
    )
    snapshot = [_save_snapshot(r) for r in results]
    assert all(not isinstance(r, Exception) for r in results), snapshot
    assert [r.status_code for r in results] == [200, 200], snapshot

    ids = [r.json()["floors"][0]["id"] for r in results]
    assert ids[0] == ids[1]
    detail = (await client.get(f"/projects/{project_id}")).json()
    assert [f["floor_number"] for f in detail["floors"]] == [0]
    assert detail["floors"][0]["id"] == ids[0]


@pytest.mark.asyncio
async def test_save_floor_unique_conflict_returns_409(client: AsyncClient, monkeypatch):
    """A uq_project_floor violation that still escapes the upsert is a 409.

    The save is idempotent on (project_id, floor_number). This covers a
    conflict the upsert did not absorb: the client gets a clear 409, not an
    unhandled IntegrityError (which uvicorn turns into a 500).
    """
    resp = await client.post("/projects", json={"name": "Conflict fallback"})
    project_id = resp.json()["id"]

    async def commit_unique_violation(self):
        raise IntegrityError(
            "INSERT INTO floors",
            {},
            Exception('duplicate key value violates unique constraint "uq_project_floor"'),
        )

    monkeypatch.setattr(AsyncSession, "commit", commit_unique_violation)
    resp = await client.post(
        f"/projects/{project_id}/save",
        json={"settings": {}, "floors": [{"floor_number": 0, "name": "F", "elements": []}]},
    )
    assert resp.status_code == 409, getattr(resp, "text", resp)
    detail = resp.json()["detail"]
    assert detail["constraint"] == "uq_project_floor"
    assert "floor" in detail["message"].lower()


@pytest.mark.asyncio
async def test_floor_upsert_keeps_id_and_pdf_key(client: AsyncClient, test_session: AsyncSession):
    """ON CONFLICT update must not mint a new floor id or clear pdf_s3_key."""
    from sqlalchemy import select

    from routers.projects import _upsert_floor

    resp = await client.post("/projects", json={"name": "Upsert PDF"})
    project_id = resp.json()["id"]
    saved = await client.post(f"/projects/{project_id}/save", json={
        "settings": {},
        "floors": [{"floor_number": 0, "name": "Original", "elements": []}],
    })
    assert saved.status_code == 200, saved.text
    floor_id = saved.json()["floors"][0]["id"]

    floor = (await test_session.execute(
        select(Floor).where(Floor.id == uuid.UUID(floor_id))
    )).scalar_one()
    floor.pdf_s3_key = "plans/floor0.pdf"
    await test_session.commit()

    from models.project_schemas import FloorSavePayload

    kept_id = await _upsert_floor(
        test_session,
        uuid.UUID(project_id),
        FloorSavePayload(floor_number=0, name="Renamed", pixels_per_mesh=4.0),
    )
    await test_session.commit()

    assert str(kept_id) == floor_id
    detail = (await client.get(f"/projects/{project_id}/floors/{floor_id}")).json()
    assert detail["name"] == "Renamed"
    assert detail["pdf_s3_key"] == "plans/floor0.pdf"
    assert detail["pixels_per_mesh"] == 4.0


@pytest.mark.asyncio
async def test_api_replace_elements(client: AsyncClient):
    # Create project with a floor via bulk save
    resp = await client.post("/projects", json={"name": "Elements Test"})
    project_id = resp.json()["id"]

    resp = await client.post(f"/projects/{project_id}/save", json={
        "settings": {},
        "floors": [{"floor_number": 0, "name": "Ground", "elements": [
            {"element_index": 0, "type": "rect", "points": [{"x": 0, "y": 0}], "comments": "mesh"},
        ]}],
    })
    floor_id = resp.json()["floors"][0]["id"]

    # Replace elements
    new_elements = [
        {"element_index": 0, "type": "polyline", "points": [{"x": 1, "y": 1}, {"x": 2, "y": 2}], "comments": "wall"},
        {"element_index": 1, "type": "point", "points": [{"x": 5, "y": 5}], "comments": "inlet"},
    ]
    resp = await client.put(f"/projects/{project_id}/floors/{floor_id}/elements", json=new_elements)
    assert resp.status_code == 200
    assert len(resp.json()) == 2

    # Verify
    resp = await client.get(f"/projects/{project_id}/floors/{floor_id}/elements")
    assert resp.status_code == 200
    assert len(resp.json()) == 2
    assert resp.json()[0]["comments"] == "wall"


# --- Project mode (fdsGen / timeEq / ...) ---

@pytest.mark.asyncio
async def test_api_project_mode_defaults_to_fdsgen(client: AsyncClient):
    resp = await client.post("/projects", json={"name": "Legacy-style create"})
    assert resp.status_code == 201
    assert resp.json()["mode"] == "fdsGen"

    detail = await client.get(f"/projects/{resp.json()['id']}")
    assert detail.json()["mode"] == "fdsGen"


@pytest.mark.asyncio
async def test_api_create_project_with_mode(client: AsyncClient):
    resp = await client.post("/projects", json={"name": "TEQ", "mode": "timeEq"})
    assert resp.status_code == 201
    assert resp.json()["mode"] == "timeEq"


@pytest.mark.asyncio
async def test_api_list_projects_filters_by_mode(client: AsyncClient):
    fds = (await client.post("/projects", json={"name": "FDS one"})).json()
    teq = (await client.post("/projects", json={"name": "TEQ one", "mode": "timeEq"})).json()

    # unfiltered list returns everything (backwards compatible)
    everything = {p["id"] for p in (await client.get("/projects")).json()}
    assert {fds["id"], teq["id"]} <= everything

    teq_only = (await client.get("/projects", params={"mode": "timeEq"})).json()
    assert [p["id"] for p in teq_only] == [teq["id"]]
    assert all(p["mode"] == "timeEq" for p in teq_only)

    fds_only = {p["id"] for p in (await client.get("/projects", params={"mode": "fdsGen"})).json()}
    assert fds["id"] in fds_only
    assert teq["id"] not in fds_only


@pytest.mark.asyncio
async def test_bulk_save_does_not_change_mode(client: AsyncClient):
    teq = (await client.post("/projects", json={"name": "TEQ", "mode": "timeEq"})).json()
    resp = await client.post(
        f"/projects/{teq['id']}/save",
        json={"name": "TEQ renamed", "settings": {"timeEqInputs": {"use": "Office"}}, "floors": []},
    )
    assert resp.status_code == 200
    assert resp.json()["mode"] == "timeEq"
    assert resp.json()["settings"]["timeEqInputs"] == {"use": "Office"}
