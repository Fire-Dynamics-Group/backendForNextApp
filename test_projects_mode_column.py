"""Reproduce production GET /projects?mode=fdsGen 500.

The browser reports CORS because the 500 body has no ACAO headers. The real
fault is schema: Railway starts uvicorn only (no alembic), so a projects table
created before alembic d4e8f2a7b310 never got a `mode` column. Postgres then
parses `projects.mode` as the ordered-set aggregate mode() and raises:

    WITHIN GROUP is required for ordered-set aggregate mode

SQLite says "no such column" for the same missing column; the startup helper
must ALTER the existing table on boot, matching _seed_text_blocks.
"""
import os
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import inspect, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ["DATABASE_URL"] = ""

import database  # noqa: E402
from database import Base  # noqa: E402
from models.db_models import Project  # noqa: E402

SQLITE_DB = "./test_projects_mode_column.db"
POSTGRES_URL = os.environ.get(
    "TEST_POSTGRES_URL", "postgresql+asyncpg://ubuntu@/fdg_mode_test"
)


def _column_names(sync_conn, table="projects"):
    return {c["name"] for c in inspect(sync_conn).get_columns(table)}


@pytest_asyncio.fixture
async def sqlite_engine(monkeypatch):
    if os.path.exists(SQLITE_DB):
        os.remove(SQLITE_DB)
    engine = create_async_engine(f"sqlite+aiosqlite:///{SQLITE_DB}", echo=False)
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(
        database,
        "async_session",
        async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False),
    )
    yield engine
    await engine.dispose()
    if os.path.exists(SQLITE_DB):
        os.remove(SQLITE_DB)


@pytest_asyncio.fixture
async def pg_engine(monkeypatch):
    engine = create_async_engine(POSTGRES_URL, echo=False)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 — skip when this machine has no Postgres
        await engine.dispose()
        pytest.skip(f"Postgres not available: {exc}")
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(
        database,
        "async_session",
        async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False),
    )
    yield engine
    await engine.dispose()


async def _legacy_projects_table(engine, *, postgres: bool):
    """projects table as it existed before alembic d4e8f2a7b310 (no mode)."""
    async with engine.begin() as conn:
        await conn.execute(text("DROP TABLE IF EXISTS elements"))
        await conn.execute(text("DROP TABLE IF EXISTS floors"))
        await conn.execute(text("DROP TABLE IF EXISTS projects"))
        if postgres:
            await conn.execute(
                text(
                    """
                    CREATE TABLE projects (
                        id uuid PRIMARY KEY,
                        name text NOT NULL,
                        settings jsonb,
                        created_by text,
                        created_at timestamptz,
                        updated_at timestamptz
                    )
                    """
                )
            )
        else:
            await conn.execute(
                text(
                    """
                    CREATE TABLE projects (
                        id CHAR(32) NOT NULL PRIMARY KEY,
                        name TEXT NOT NULL,
                        settings JSON,
                        created_by TEXT,
                        created_at DATETIME,
                        updated_at DATETIME
                    )
                    """
                )
            )


@pytest.mark.asyncio
async def test_postgres_missing_mode_column_raises_within_group(pg_engine):
    """The exact production exception — missing column, not a CORS misconfig."""
    await _legacy_projects_table(pg_engine, postgres=True)
    async with pg_engine.connect() as conn:
        with pytest.raises(Exception) as raised:
            await conn.execute(
                select(Project).where(Project.mode == "fdsGen")
            )
    message = str(raised.value)
    assert "WITHIN GROUP is required for ordered-set aggregate mode" in message


@pytest.mark.asyncio
async def test_startup_adds_mode_column_to_legacy_projects_table(sqlite_engine):
    await _legacy_projects_table(sqlite_engine, postgres=False)
    async with sqlite_engine.connect() as conn:
        names = await conn.run_sync(_column_names)
    assert "mode" not in names

    import main

    await main._ensure_projects_mode_column()

    async with sqlite_engine.connect() as conn:
        names = await conn.run_sync(_column_names)
    assert "mode" in names


@pytest.mark.asyncio
async def test_ensure_projects_mode_column_is_idempotent(sqlite_engine):
    await _legacy_projects_table(sqlite_engine, postgres=False)
    import main

    await main._ensure_projects_mode_column()
    await main._ensure_projects_mode_column()

    async with sqlite_engine.connect() as conn:
        names = await conn.run_sync(_column_names)
    assert "mode" in names


@pytest.mark.asyncio
async def test_postgres_list_by_mode_works_after_startup_heal(pg_engine):
    await _legacy_projects_table(pg_engine, postgres=True)
    legacy_id = uuid.uuid4()
    async with pg_engine.begin() as conn:
        await conn.execute(
            text("INSERT INTO projects (id, name) VALUES (:id, :name)"),
            {"id": legacy_id, "name": "pre-mode row"},
        )

    import main

    await main._ensure_projects_mode_column()

    session_factory = async_sessionmaker(
        pg_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        rows = (
            await session.execute(select(Project).where(Project.mode == "fdsGen"))
        ).scalars().all()
    assert [p.name for p in rows] == ["pre-mode row"]
    assert all(p.mode == "fdsGen" for p in rows)


@pytest.mark.asyncio
async def test_api_list_projects_by_mode_after_healing_legacy_schema(sqlite_engine):
    """GET /projects?mode=fdsGen must 200 after the boot helper ALTERs the table."""
    async with sqlite_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("DROP INDEX IF EXISTS ix_projects_mode"))
        await conn.execute(text("ALTER TABLE projects DROP COLUMN mode"))

    import main

    await main._ensure_projects_mode_column()

    session_factory = async_sessionmaker(
        sqlite_engine, class_=AsyncSession, expire_on_commit=False
    )

    async def override_get_db():
        async with session_factory() as session:
            yield session

    from main import app

    app.dependency_overrides[database.get_db] = override_get_db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            created = await client.post(
                "/projects", json={"name": "Canvas FDS", "mode": "fdsGen"}
            )
            assert created.status_code == 201, created.text
            listed = await client.get("/projects", params={"mode": "fdsGen"})
            assert listed.status_code == 200, listed.text
            names = [p["name"] for p in listed.json()]
            assert "Canvas FDS" in names
            assert all(p["mode"] == "fdsGen" for p in listed.json())
    finally:
        app.dependency_overrides.clear()
