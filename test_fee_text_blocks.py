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
from services.fee_text_blocks import (  # noqa: E402
    seed_fee_text_blocks, build_text_map, token_errors,
)

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


# --- build_text_map: pure resolution of override -> DB -> constant ---

def test_build_text_map_falls_back_to_constants_when_empty():
    m = build_text_map([])
    assert m["INTRO_OPEN_PLAN"] == txt.INTRO_OPEN_PLAN          # paragraph: native str
    assert m["STAGE_1_SCOPE"] == list(txt.STAGE_1_SCOPE)        # bullet_list: native list


def test_build_text_map_db_block_overrides_constant():
    m = build_text_map([("INTRO_OPEN_PLAN", "paragraph", "NEW TEXT")])
    assert m["INTRO_OPEN_PLAN"] == "NEW TEXT"


def test_build_text_map_splits_bullet_list_content():
    m = build_text_map([("STAGE_1_SCOPE", "bullet_list", "first bullet\nsecond bullet")])
    assert m["STAGE_1_SCOPE"] == ["first bullet", "second bullet"]


def test_build_text_map_override_beats_db_and_constant():
    m = build_text_map(
        [("INTRO_OPEN_PLAN", "paragraph", "DB TEXT")],
        overrides={"INTRO_OPEN_PLAN": "OVERRIDE TEXT"},
    )
    assert m["INTRO_OPEN_PLAN"] == "OVERRIDE TEXT"


# --- token_errors: validation for default-text edits ---

def test_token_errors_flags_unknown_token():
    errs = token_errors(["legislation"], "Per {legislation} and {bogus}.")
    assert any("bogus" in e for e in errs)


def test_token_errors_flags_removed_required_token():
    errs = token_errors(["legislation"], "No placeholder at all.")
    assert any("legislation" in e for e in errs)


def test_token_errors_empty_when_tokens_match():
    assert token_errors(["legislation"], "Issued under {legislation}.") == []
