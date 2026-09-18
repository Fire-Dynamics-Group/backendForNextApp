"""TDD tests for homepage tool-search analytics ingest.

Contract: fd-toolstation `lib/tools/ANALYTICS.md` and the browser client in
`lib/tools/analytics.ts`. Frontend posts camelCase JSON to:

  POST {NEXT_PUBLIC_API_URL}/tool-search/log
  POST {NEXT_PUBLIC_API_URL}/tool-search/click

Identity (user_email / user_id / anon_id) is optional — homepage Profile/Logout
are decorative. Entra / Easy Auth headers are copied when present.
"""

import os
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

TEST_DATABASE_URL = "sqlite+aiosqlite:///./test_tool_search.db"

os.environ["DATABASE_URL"] = ""  # prevent real DB connection

from database import Base  # noqa: E402
from models.db_models import Element, Floor, Project  # noqa: E402, F401
from models.tool_search import ToolSearchClick, ToolSearchLog  # noqa: E402, F401

CLIENT_SEARCH_ID = "3f1c0a7e-8b2d-4c9a-91e4-0d5f6a7b8c9d"
VERCEL_ORIGIN = "https://fd-toolstation.vercel.app"
VERCEL_PREVIEW_ORIGIN = "https://fd-toolstation-git-home-nl-tool-search-fire-dynamics-projects.vercel.app"

FRONTEND_LOG = {
    "clientSearchId": CLIENT_SEARCH_ID,
    "query": "br",
    "queryNormalized": "br",
    "resultCount": 5,
    "topIds": [
        "efs-calculator",
        "upload-canvas-efs",
        "radiation",
        "br187-excel",
        "br187-desktop",
    ],
    "suggestionId": "efs-calculator",
    "confidence": "high",
    "mode": "keyword",
    "latencyMs": 12,
    "anonId": "anon-cookie-1",
    "userId": None,
    "userEmail": None,
    "source": "toolstation-home",
    "ts": "2026-09-18T08:00:00.000Z",
}

FRONTEND_CLICK = {
    "clientSearchId": CLIENT_SEARCH_ID,
    "partId": "upload-canvas-efs",
    "rank": 2,
    "anonId": "anon-cookie-1",
    "userId": None,
    "userEmail": None,
    "source": "toolstation-home",
    "ts": "2026-09-18T08:00:01.000Z",
}


@pytest_asyncio.fixture
async def test_engine():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()
    if os.path.exists("./test_tool_search.db"):
        os.remove("./test_tool_search.db")


@pytest_asyncio.fixture
async def session_factory(test_engine):
    return async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture
async def client(session_factory):
    import database
    from main import app

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


@pytest.mark.asyncio
async def test_log_frontend_payload_returns_204_and_persists(client, session_factory):
    resp = await client.post("/tool-search/log", json=FRONTEND_LOG)
    assert resp.status_code == 204
    assert resp.content == b""

    async with session_factory() as session:
        row = (await session.execute(select(ToolSearchLog))).scalar_one()
        assert str(row.client_search_id) == CLIENT_SEARCH_ID
        assert row.query == "br"
        assert row.query_normalized == "br"
        assert row.result_count == 5
        assert row.top_ids[0] == "efs-calculator"
        assert row.suggestion_id == "efs-calculator"
        assert row.confidence == "high"
        assert row.mode == "keyword"
        assert row.latency_ms == 12
        assert row.anon_id == "anon-cookie-1"
        assert row.user_id is None
        assert row.user_email is None
        assert row.source == "toolstation-home"


@pytest.mark.asyncio
async def test_click_frontend_payload_returns_204_and_persists(client, session_factory):
    resp = await client.post("/tool-search/click", json=FRONTEND_CLICK)
    assert resp.status_code == 204
    assert resp.content == b""

    async with session_factory() as session:
        row = (await session.execute(select(ToolSearchClick))).scalar_one()
        assert str(row.client_search_id) == CLIENT_SEARCH_ID
        assert row.part_id == "upload-canvas-efs"
        assert row.rank == 2
        assert row.anon_id == "anon-cookie-1"
        assert row.user_id is None
        assert row.user_email is None
        assert row.source == "toolstation-home"


@pytest.mark.asyncio
async def test_identity_fields_are_optional(client, session_factory):
    payload = {
        "clientSearchId": str(uuid.uuid4()),
        "query": "warehouse",
        "queryNormalized": "warehouse",
        "resultCount": 1,
        "topIds": ["warehouse-smoke-web"],
    }
    resp = await client.post("/tool-search/log", json=payload)
    assert resp.status_code == 204

    click = {
        "clientSearchId": payload["clientSearchId"],
        "partId": "warehouse-smoke-web",
        "rank": 1,
    }
    resp = await client.post("/tool-search/click", json=click)
    assert resp.status_code == 204

    async with session_factory() as session:
        log = (await session.execute(select(ToolSearchLog))).scalar_one()
        click_row = (await session.execute(select(ToolSearchClick))).scalar_one()
        assert log.user_id is None
        assert log.user_email is None
        assert log.anon_id in (None, "")
        assert click_row.user_id is None
        assert click_row.user_email is None
        assert click_row.anon_id in (None, "")


@pytest.mark.asyncio
async def test_identity_copied_from_entra_headers_when_body_null(client, session_factory):
    payload = {
        **FRONTEND_LOG,
        "clientSearchId": str(uuid.uuid4()),
        "userId": None,
        "userEmail": None,
    }
    resp = await client.post(
        "/tool-search/log",
        json=payload,
        headers={
            "x-ms-client-principal-id": "entra-oid-1",
            "x-ms-client-principal-name": "ian@firedynamics.com",
        },
    )
    assert resp.status_code == 204

    async with session_factory() as session:
        row = (await session.execute(select(ToolSearchLog))).scalar_one()
        assert row.user_id == "entra-oid-1"
        assert row.user_email == "ian@firedynamics.com"


@pytest.mark.asyncio
async def test_cors_allows_toolstation_vercel_and_previews(client):
    for origin in (VERCEL_ORIGIN, VERCEL_PREVIEW_ORIGIN):
        preflight = await client.options(
            "/tool-search/log",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        assert preflight.status_code in (200, 204)
        assert preflight.headers.get("access-control-allow-origin") in ("*", origin)
        allow_methods = preflight.headers.get("access-control-allow-methods", "")
        assert "POST" in allow_methods.upper() or allow_methods == "*"

        posted = await client.post(
            "/tool-search/log",
            json={**FRONTEND_LOG, "clientSearchId": str(uuid.uuid4())},
            headers={"Origin": origin},
        )
        assert posted.status_code == 204
        assert posted.headers.get("access-control-allow-origin") in ("*", origin)


@pytest.mark.asyncio
async def test_log_requires_query(client):
    resp = await client.post(
        "/tool-search/log",
        json={"clientSearchId": str(uuid.uuid4())},
    )
    assert resp.status_code == 422
