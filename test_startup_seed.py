"""Regression test: app startup creates the fee_text_block tables and seeds them
even when no migration has run (the production Procfile starts uvicorn only)."""
import os

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ["DATABASE_URL"] = ""

import database  # noqa: E402
from models.db_models import FeeTextBlock  # noqa: E402

DB_FILE = "./test_startup_seed.db"


@pytest.mark.asyncio
async def test_startup_creates_and_seeds_tables(monkeypatch):
    if os.path.exists(DB_FILE):
        os.remove(DB_FILE)
    # Fresh engine with NO tables created — the startup hook must create them.
    engine = create_async_engine(f"sqlite+aiosqlite:///{DB_FILE}", echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "async_session", session_factory)

    import main
    await main._seed_text_blocks()

    async with session_factory() as session:
        count = (await session.execute(select(func.count()).select_from(FeeTextBlock))).scalar_one()
    assert count > 50  # tables were created and seeded

    await engine.dispose()
    if os.path.exists(DB_FILE):
        os.remove(DB_FILE)
