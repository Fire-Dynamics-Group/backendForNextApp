"""Tests for fee_text_block persistence + idempotent seeding (issue #3)."""
import os

import pytest
import pytest_asyncio
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ["DATABASE_URL"] = ""  # prevent real DB connection

from database import Base  # noqa: E402
from models.db_models import FeeTextBlock, FeeTextBlockHistory  # noqa: E402, F401
from services import fee_text_templates as txt  # noqa: E402
from services.fee_text_blocks import seed_fee_text_blocks  # noqa: E402

TEST_DATABASE_URL = "sqlite+aiosqlite:///./test_fee_text_blocks.db"


@pytest_asyncio.fixture
async def test_session():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()
    if os.path.exists("./test_fee_text_blocks.db"):
        os.remove("./test_fee_text_blocks.db")


@pytest.mark.asyncio
async def test_seed_creates_block_with_content_equal_default(test_session):
    await seed_fee_text_blocks(test_session)

    block = await test_session.get(FeeTextBlock, "INTRO_OPEN_PLAN")
    assert block is not None
    assert block.content == txt.INTRO_OPEN_PLAN
    assert block.default_content == txt.INTRO_OPEN_PLAN
    assert block.kind == "paragraph"


@pytest.mark.asyncio
async def test_seed_classifies_kinds_and_derives_placeholders(test_session):
    await seed_fee_text_blocks(test_session)

    bullets = await test_session.get(FeeTextBlock, "STAGE_1_SCOPE")
    assert bullets.kind == "bullet_list"
    assert bullets.content == "\n".join(txt.STAGE_1_SCOPE)

    template = await test_session.get(FeeTextBlock, "STAGE_3_DELIVERABLES_TEMPLATE")
    assert template.kind == "template"
    assert template.placeholders == ["legislation"]


@pytest.mark.asyncio
async def test_seed_excludes_non_narrative_constants(test_session):
    await seed_fee_text_blocks(test_session)
    assert await test_session.get(FeeTextBlock, "OFFICE_ADDRESS") is None
    assert await test_session.get(FeeTextBlock, "HOURLY_RATES") is None


@pytest.mark.asyncio
async def test_seed_is_idempotent(test_session):
    first = await seed_fee_text_blocks(test_session)
    assert first > 0
    count1 = (await test_session.execute(select(func.count()).select_from(FeeTextBlock))).scalar_one()

    second = await seed_fee_text_blocks(test_session)
    assert second == 0
    count2 = (await test_session.execute(select(func.count()).select_from(FeeTextBlock))).scalar_one()
    assert count1 == count2 == first


@pytest.mark.asyncio
async def test_reseed_preserves_edited_content(test_session):
    await seed_fee_text_blocks(test_session)
    block = await test_session.get(FeeTextBlock, "INTRO_OPEN_PLAN")
    block.content = "EDITED BY USER"
    await test_session.commit()

    await seed_fee_text_blocks(test_session)
    block = await test_session.get(FeeTextBlock, "INTRO_OPEN_PLAN")
    assert block.content == "EDITED BY USER"          # edit survives re-seed
    assert block.default_content == txt.INTRO_OPEN_PLAN  # default still original
