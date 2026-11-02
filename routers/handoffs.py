"""User-authenticated handoff endpoints for upload-canvas.

Gated by `current_user` (Entra bearer / session). The i-macs app key is NOT accepted here.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database import get_db
from models.db_models import MacsHandoff
from models.macs_schemas import MacsHandoffDetail

router = APIRouter()

DbSession = Annotated[AsyncSession, Depends(get_db)]


@router.get("/{handoff_id}", response_model=MacsHandoffDetail)
async def get_handoff(
    handoff_id: uuid.UUID,
    db: DbSession,
):
    """Retrieve an unexpired, unclaimed MACs run handoff so upload-canvas can prefill."""
    handoff = (
        await db.execute(
            select(MacsHandoff)
            .where(MacsHandoff.id == handoff_id)
            .options(selectinload(MacsHandoff.run))
        )
    ).scalar_one_or_none()

    if handoff is None:
        raise HTTPException(404, "Handoff not found")

    if handoff.claimed_at is not None:
        raise HTTPException(409, "Handoff has already been claimed")

    if handoff.expires_at.tzinfo is None:
        expires_at = handoff.expires_at.replace(tzinfo=timezone.utc)
    else:
        expires_at = handoff.expires_at

    if expires_at < datetime.now(timezone.utc):
        raise HTTPException(410, "Handoff has expired")

    return MacsHandoffDetail(
        handoff_id=handoff.id,
        expires_at=handoff.expires_at,
        created_at=handoff.created_at,
        imacs_job_id=handoff.imacs_job_id,
        run=handoff.run,
    )
