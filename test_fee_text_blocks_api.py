"""API tests for the Manage Proposal Text endpoints (issue #6)."""
import os

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ["DATABASE_URL"] = ""

from database import Base  # noqa: E402
from models.db_models import FeeTextBlock  # noqa: E402, F401
from services import fee_text_templates as txt  # noqa: E402
from services.fee_text_blocks import seed_fee_text_blocks  # noqa: E402

TEST_DATABASE_URL = "sqlite+aiosqlite:///./test_fee_text_blocks_api.db"
PARA_KEY = "INTRO_OPEN_PLAN"             # paragraph, no placeholders
TPL_KEY = "STAGE_3_DELIVERABLES_TEMPLATE"  # template, placeholders == ["legislation"]


@pytest_asyncio.fixture
async def client():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as s:
        await seed_fee_text_blocks(s)

    import database
    from main import app

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[database.get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()
    if os.path.exists("./test_fee_text_blocks_api.db"):
        os.remove("./test_fee_text_blocks_api.db")


@pytest.mark.asyncio
async def test_list_text_blocks(client):
    resp = await client.get("/fee-proposals/text-blocks")
    assert resp.status_code == 200
    blocks = resp.json()
    assert len(blocks) > 50
    keys = {b["key"] for b in blocks}
    assert PARA_KEY in keys and TPL_KEY in keys


@pytest.mark.asyncio
async def test_update_block_writes_content_and_history(client):
    resp = await client.put(f"/fee-proposals/text-blocks/{PARA_KEY}",
                            json={"content": "BRAND NEW INTRO", "edited_by": "Ian"})
    assert resp.status_code == 200
    assert resp.json()["content"] == "BRAND NEW INTRO"

    hist = await client.get(f"/fee-proposals/text-blocks/{PARA_KEY}/history")
    assert hist.status_code == 200
    entries = hist.json()
    assert len(entries) == 1
    assert entries[0]["content"] == "BRAND NEW INTRO"
    assert entries[0]["edited_by"] == "Ian"


@pytest.mark.asyncio
async def test_update_rejects_empty_edited_by(client):
    resp = await client.put(f"/fee-proposals/text-blocks/{PARA_KEY}",
                            json={"content": "x", "edited_by": "  "})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_update_rejects_unknown_placeholder(client):
    resp = await client.put(f"/fee-proposals/text-blocks/{TPL_KEY}",
                            json={"content": "Per {legislation} and {bogus}.", "edited_by": "Ian"})
    assert resp.status_code == 400
    assert "bogus" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_update_rejects_removed_required_placeholder(client):
    resp = await client.put(f"/fee-proposals/text-blocks/{TPL_KEY}",
                            json={"content": "No placeholder here.", "edited_by": "Ian"})
    assert resp.status_code == 400
    assert "legislation" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_reset_restores_default(client):
    await client.put(f"/fee-proposals/text-blocks/{PARA_KEY}",
                     json={"content": "EDITED", "edited_by": "Ian"})
    resp = await client.post(f"/fee-proposals/text-blocks/{PARA_KEY}/reset",
                             json={"edited_by": "Ian"})
    assert resp.status_code == 200
    assert resp.json()["content"] == txt.INTRO_OPEN_PLAN


@pytest.mark.asyncio
async def test_restore_returns_to_chosen_snapshot(client):
    await client.put(f"/fee-proposals/text-blocks/{PARA_KEY}",
                     json={"content": "VERSION ONE", "edited_by": "Ian"})
    await client.put(f"/fee-proposals/text-blocks/{PARA_KEY}",
                     json={"content": "VERSION TWO", "edited_by": "Ian"})

    hist = (await client.get(f"/fee-proposals/text-blocks/{PARA_KEY}/history")).json()
    v1_id = next(h["id"] for h in hist if h["content"] == "VERSION ONE")

    resp = await client.post(f"/fee-proposals/text-blocks/{PARA_KEY}/restore/{v1_id}",
                             json={"edited_by": "Ian"})
    assert resp.status_code == 200
    assert resp.json()["content"] == "VERSION ONE"
