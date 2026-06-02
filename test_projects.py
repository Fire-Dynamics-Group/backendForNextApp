"""Tests for project persistence: DB models, API endpoints, and S3 service."""
import os
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
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


# --- Multi-mode schema: mode-tagged elements ---
#
# Elements carry an optional `mode` so a single project/floor can hold geometry
# for more than one analysis mode (fdsGen / radiation / timeEq). Untagged
# elements (mode is None) are legacy/fdsGen and must keep working unchanged.

@pytest.mark.asyncio
async def test_element_mode_orm_roundtrip(test_session: AsyncSession):
    project = Project(name="Mode ORM")
    test_session.add(project)
    await test_session.commit()
    await test_session.refresh(project)

    floor = Floor(project_id=project.id, floor_number=0)
    test_session.add(floor)
    await test_session.commit()
    await test_session.refresh(floor)

    element = Element(
        floor_id=floor.id, element_index=0, type="polyline",
        points=[{"x": 0, "y": 0}], comments="escapeRoute", mode="radiation",
    )
    test_session.add(element)
    await test_session.commit()
    await test_session.refresh(element)

    assert element.mode == "radiation"


@pytest.mark.asyncio
async def test_element_mode_defaults_none(test_session: AsyncSession):
    project = Project(name="Mode default")
    test_session.add(project)
    await test_session.commit()
    await test_session.refresh(project)

    floor = Floor(project_id=project.id, floor_number=0)
    test_session.add(floor)
    await test_session.commit()
    await test_session.refresh(floor)

    element = Element(
        floor_id=floor.id, element_index=0, type="rect",
        points=[{"x": 0, "y": 0}], comments="mesh",
    )
    test_session.add(element)
    await test_session.commit()
    await test_session.refresh(element)

    assert element.mode is None


@pytest.mark.asyncio
async def test_bulk_save_persists_element_mode(client: AsyncClient):
    resp = await client.post("/projects", json={"name": "Mode Save"})
    project_id = resp.json()["id"]

    payload = {
        "settings": {},
        "floors": [{
            "floor_number": 0, "name": "F", "elements": [
                {"element_index": 0, "type": "polyline", "points": [{"x": 0, "y": 0}],
                 "comments": "escapeRoute", "mode": "radiation"},
                {"element_index": 1, "type": "rect", "points": [{"x": 1, "y": 1}],
                 "comments": "mesh"},  # no mode -> None (legacy/fdsGen)
            ],
        }],
    }
    resp = await client.post(f"/projects/{project_id}/save", json=payload)
    assert resp.status_code == 200
    floor_id = resp.json()["floors"][0]["id"]

    resp = await client.get(f"/projects/{project_id}/floors/{floor_id}")
    els = {e["element_index"]: e for e in resp.json()["elements"]}
    assert els[0]["mode"] == "radiation"
    assert els[1]["mode"] is None


@pytest.mark.asyncio
async def test_elements_endpoint_mode_filter(client: AsyncClient):
    resp = await client.post("/projects", json={"name": "Mode Filter"})
    project_id = resp.json()["id"]
    resp = await client.post(f"/projects/{project_id}/save", json={
        "settings": {}, "floors": [{"floor_number": 0, "name": "F", "elements": []}],
    })
    floor_id = resp.json()["floors"][0]["id"]

    new_elements = [
        {"element_index": 0, "type": "rect", "points": [{"x": 0, "y": 0}],
         "comments": "mesh", "mode": "fdsGen"},
        {"element_index": 1, "type": "polyline", "points": [{"x": 1, "y": 1}],
         "comments": "escapeRoute", "mode": "radiation"},
    ]
    resp = await client.put(f"/projects/{project_id}/floors/{floor_id}/elements", json=new_elements)
    assert resp.status_code == 200
    assert resp.json()[1]["mode"] == "radiation"

    # Filter returns only the requested mode
    resp = await client.get(f"/projects/{project_id}/floors/{floor_id}/elements?mode=radiation")
    data = resp.json()
    assert len(data) == 1
    assert data[0]["comments"] == "escapeRoute"

    # No filter returns all
    resp = await client.get(f"/projects/{project_id}/floors/{floor_id}/elements")
    assert len(resp.json()) == 2
