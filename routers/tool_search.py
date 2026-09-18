"""Ingest homepage tool-search logs and clicks. Never required for search UX."""

import uuid
from typing import Optional, Tuple

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.tool_search import ToolSearchClick, ToolSearchClickIn, ToolSearchLog, ToolSearchLogIn

router = APIRouter()


def _identity_from_request(
    request: Request,
    user_id: Optional[str],
    user_email: Optional[str],
    anon_id: Optional[str],
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Body identity wins; otherwise copy Entra / Easy Auth / Access headers."""
    headers = request.headers
    if not user_id:
        user_id = headers.get("x-ms-client-principal-id") or headers.get("x-forwarded-user")
    if not user_email:
        user_email = (
            headers.get("x-ms-client-principal-name")
            or headers.get("x-forwarded-email")
            or headers.get("cf-access-authenticated-user-email")
        )
    return user_id or None, user_email or None, anon_id or None


@router.post("/log", status_code=204)
async def record_log(
    data: ToolSearchLogIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    user_id, user_email, anon_id = _identity_from_request(
        request, data.user_id, data.user_email, data.anon_id
    )
    db.add(
        ToolSearchLog(
            id=uuid.uuid4(),
            client_search_id=data.client_search_id,
            query=data.query,
            query_normalized=data.query_normalized or data.query.lower(),
            result_count=data.result_count,
            top_ids=data.top_ids,
            suggestion_id=data.suggestion_id,
            confidence=data.confidence,
            mode=data.mode,
            latency_ms=data.latency_ms,
            anon_id=anon_id,
            user_id=user_id,
            user_email=user_email,
            source=data.source,
        )
    )
    await db.commit()


@router.post("/click", status_code=204)
async def record_click(
    data: ToolSearchClickIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    user_id, user_email, anon_id = _identity_from_request(
        request, data.user_id, data.user_email, data.anon_id
    )
    db.add(
        ToolSearchClick(
            id=uuid.uuid4(),
            client_search_id=data.client_search_id,
            part_id=data.part_id,
            rank=data.rank,
            anon_id=anon_id,
            user_id=user_id,
            user_email=user_email,
            source=data.source,
        )
    )
    await db.commit()
