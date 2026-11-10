"""MACs table setup must be visible, and Alembic must match the ORM inserts.

A fresh Postgres database has no `projects` table. `_ensure_macs_tables`
create_all then fails the foreign key, the exception is swallowed, and uvicorn
still serves. `POST /imacs/handoffs` 500s with `relation "macs_runs" does not
exist`. `/health` does not list `macs_runs`, `macs_handoffs`, or
`imacs_job_links`.

Alembic `e5f1a9c3d7b2` creates `macs_runs` without `outputs`, `checks`, or
`time_series`, which the ORM always inserts.

A boot where `projects` already exists must keep creating the three tables
from the ORM, including those columns. The lifespan must not create
`projects`. `smoke_layer_runs` stays on its own alembic revision.
"""
from __future__ import annotations

import importlib.util
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session

os.environ["DATABASE_URL"] = ""

import database  # noqa: E402
from database import Base  # noqa: E402
from models.db_models import MacsRun, Project  # noqa: E402
from services.health_service import REQUIRED_TABLES, build_health  # noqa: E402

MACS_TABLES = ("macs_runs", "macs_handoffs", "imacs_job_links")
ORM_JSON_COLUMNS = ("outputs", "checks", "time_series")

SQLITE_DB = "./test_macs_table_setup.db"
POSTGRES_URL = os.environ.get(
    "TEST_POSTGRES_URL", "postgresql+asyncpg://ubuntu@/macs_setup_test"
)


def _sync_names(sync_conn) -> set[str]:
    return set(inspect(sync_conn).get_table_names())


def _sync_columns(sync_conn, table: str) -> set[str]:
    return {c["name"] for c in inspect(sync_conn).get_columns(table)}


def _macs_upgrade():
    path = (
        Path(__file__).resolve().parent
        / "alembic/versions/e5f1a9c3d7b2_add_macs_results_table.py"
    )
    spec = importlib.util.spec_from_file_location("e5f1a9c3d7b2_add_macs_results_table", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.upgrade


def _run_macs_upgrade(sync_conn) -> None:
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    ctx = MigrationContext.configure(sync_conn)
    with Operations.context(ctx):
        _macs_upgrade()()


def _create_projects(sync_conn) -> None:
    Project.__table__.create(sync_conn, checkfirst=True)


def _legacy_macs_runs_without_json(sync_conn) -> None:
    """macs_runs as alembic e5f1a9c3d7b2 creates it: no ORM JSON columns."""
    meta = sa.MetaData()
    sa.Table(
        "macs_runs",
        meta,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.Column("schema", sa.Text(), nullable=False),
        sa.Column("inputs", sa.JSON(), nullable=False),
        sa.Column("section", sa.Text(), nullable=False),
        sa.Column("exposure", sa.Text(), nullable=False),
        sa.Column("critical_temp", sa.Float(), nullable=False),
        sa.Column("section_factor", sa.Float(), nullable=False),
        sa.Column("governing_side", sa.Text(), nullable=False),
        sa.Column("windows_user", sa.Text(), nullable=False),
        sa.Column("machine_name", sa.Text(), nullable=True),
        sa.Column("client_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("client_version", sa.Text(), nullable=True),
        sa.Column("run_id", sa.Text(), nullable=True),
        sa.Column("label", sa.Text(), nullable=True),
        sa.Column("imacs_job_id", sa.Text(), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    meta.create_all(sync_conn)


def _insert_orm_run(bind) -> None:
    now = datetime.now(timezone.utc)
    with Session(bind) as session:
        session.add(
            MacsRun(
                id=uuid.uuid4(),
                schema_="fd-macs-reliability/1",
                inputs={"span1": 9.0},
                outputs={"ok": True},
                checks=[{"name": "a"}],
                time_series=[{"t": 0}],
                section="IPE_500",
                exposure="3-sided",
                critical_temp=690,
                section_factor=152,
                governing_side="B",
                windows_user="jbloggs",
                client_timestamp=now,
                received_at=now,
            )
        )
        session.commit()
        stored = session.query(MacsRun).one()
        assert stored.outputs == {"ok": True}
        assert stored.checks == [{"name": "a"}]
        assert stored.time_series == [{"t": 0}]


async def _reset_public(engine) -> None:
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))


@pytest.fixture
def sqlite_file():
    if os.path.exists(SQLITE_DB):
        os.remove(SQLITE_DB)
    yield SQLITE_DB
    if os.path.exists(SQLITE_DB):
        os.remove(SQLITE_DB)


@pytest_asyncio.fixture
async def sqlite_engine(sqlite_file, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{sqlite_file}", echo=False)
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(
        database,
        "async_session",
        async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False),
    )
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{sqlite_file}")
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def pg_engine(monkeypatch):
    engine = create_async_engine(POSTGRES_URL, echo=False)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 — skip when this machine has no Postgres
        await engine.dispose()
        pytest.skip(f"Postgres not available: {exc}")
    await _reset_public(engine)
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(
        database,
        "async_session",
        async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False),
    )
    monkeypatch.setenv("DATABASE_URL", POSTGRES_URL)
    yield engine
    await _reset_public(engine)
    await engine.dispose()


class TestHealthNamesMacsTables:
    def test_missing_macs_tables_are_not_ok_and_named(self):
        tables = {name: True for name in REQUIRED_TABLES}
        for name in MACS_TABLES:
            assert name in REQUIRED_TABLES
            tables[name] = False

        payload = build_health(database=True, tables=tables, storage=True)

        assert payload["status"] != "healthy"
        assert payload["status"] == "degraded"
        for name in MACS_TABLES:
            assert payload["tables"][name] is False
            assert any(name in err for err in payload["errors"])
        assert "smoke_layer_runs" not in REQUIRED_TABLES

    @pytest.mark.asyncio
    async def test_health_route_names_macs_tables_when_database_is_empty(
        self, sqlite_engine, monkeypatch
    ):
        import services.s3_service
        from main import health

        monkeypatch.setattr(services.s3_service, "storage_available", lambda: True)

        payload = await health()

        assert payload["database"] is True
        assert payload["status"] != "healthy"
        for name in MACS_TABLES:
            assert payload["tables"][name] is False
            assert any(name in err for err in payload["errors"])
        assert "smoke_layer_runs" not in payload["tables"]


class TestSetupFailureIsVisible:
    @pytest.mark.asyncio
    async def test_unset_database_does_not_fail_startup(self, monkeypatch):
        monkeypatch.setattr(database, "engine", None)
        monkeypatch.setattr(database, "async_session", None)
        monkeypatch.delenv("DATABASE_URL", raising=False)

        import main

        await main._ensure_macs_tables()

    @pytest.mark.asyncio
    async def test_fresh_postgres_lifespan_fails_and_does_not_create_projects(
        self, pg_engine
    ):
        """DATABASE_URL is set. Without projects the FK create fails, and that
        must not be swallowed. The lifespan must not create projects to paper
        over it. SQLite allows the CREATE without the parent table, so this
        case is Postgres, matching the serving 500.
        """
        import main

        with pytest.raises(Exception, match='relation "projects" does not exist'):
            async with main._lifespan(main.app):
                pytest.fail("lifespan started serving after MACs setup failed")

        async with pg_engine.connect() as conn:
            names = await conn.run_sync(_sync_names)
        assert "projects" not in names
        for name in MACS_TABLES:
            assert name not in names
        assert "smoke_layer_runs" not in names


class TestProjectsExistBootStillCreatesOrmTables:
    @pytest.mark.asyncio
    async def test_sqlite_boot_creates_macs_tables_with_orm_columns(self, sqlite_engine):
        import main

        async with sqlite_engine.begin() as conn:
            await conn.run_sync(_create_projects)

        await main._ensure_macs_tables()
        await main._ensure_macs_tables()

        async with sqlite_engine.connect() as conn:
            names = await conn.run_sync(_sync_names)
            cols = await conn.run_sync(_sync_columns, "macs_runs")
        assert "projects" in names
        for name in MACS_TABLES:
            assert name in names
        for col in ORM_JSON_COLUMNS:
            assert col in cols
        assert "smoke_layer_runs" not in names

    @pytest.mark.asyncio
    async def test_postgres_boot_creates_macs_tables_with_orm_columns(self, pg_engine):
        import main

        async with pg_engine.begin() as conn:
            await conn.run_sync(_create_projects)

        await main._ensure_macs_tables()
        await main._ensure_macs_tables()

        async with pg_engine.connect() as conn:
            names = await conn.run_sync(_sync_names)
            cols = await conn.run_sync(_sync_columns, "macs_runs")
            await conn.run_sync(_insert_orm_run)
        assert "projects" in names
        for name in MACS_TABLES:
            assert name in names
        for col in ORM_JSON_COLUMNS:
            assert col in cols


class TestAlembicMatchesOrmColumns:
    def test_fresh_upgrade_creates_columns_the_orm_inserts(self, tmp_path):
        engine = create_engine(f"sqlite:///{tmp_path / 'macs.db'}")
        with engine.begin() as conn:
            _create_projects(conn)
            _run_macs_upgrade(conn)
            cols = _sync_columns(conn, "macs_runs")
            missing = set(ORM_JSON_COLUMNS) - cols
            assert not missing, f"macs_runs missing ORM columns: {sorted(missing)}"
        _insert_orm_run(engine)

    def test_upgrade_adds_json_columns_when_macs_runs_already_exists(self, tmp_path):
        engine = create_engine(f"sqlite:///{tmp_path / 'macs.db'}")
        with engine.begin() as conn:
            _create_projects(conn)
            _legacy_macs_runs_without_json(conn)
            _run_macs_upgrade(conn)
            cols = _sync_columns(conn, "macs_runs")
            missing = set(ORM_JSON_COLUMNS) - cols
            assert not missing, f"macs_runs missing ORM columns: {sorted(missing)}"
        _insert_orm_run(engine)
