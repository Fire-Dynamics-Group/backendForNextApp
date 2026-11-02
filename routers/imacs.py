"""Endpoints for the i-macs Windows desktop app, mounted under `/imacs`.

Every route here is gated by `require_imacs_app` (shared app key) and NOT by
`current_user`. The upload-canvas read side lives on the projects router
(`GET /projects/{id}/macs-results`) behind the normal user auth.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.imacs import require_imacs_app
from database import get_db
from models.db_models import MacsResult, Project
from models.macs_schemas import (
    ENVELOPE_FIELDS,
    ImacsProjectOut,
    MacsResultCreate,
    MacsResultOut,
)

router = APIRouter(dependencies=[Depends(require_imacs_app)])

DbSession = Annotated[AsyncSession, Depends(get_db)]


@router.get("/projects", response_model=list[ImacsProjectOut])
async def list_projects(
    db: DbSession,
    mode: Annotated[
        str | None, Query(description="Only projects owned by this canvas mode")
    ] = None,
    q: Annotated[str | None, Query(description="Case-insensitive name search")] = None,
):
    query = select(Project)
    if mode is not None:
        query = query.where(Project.mode == mode)
    if q:
        escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        query = query.where(Project.name.ilike(f"%{escaped}%", escape="\\"))
    result = await db.execute(query.order_by(Project.updated_at.desc()))
    return result.scalars().all()


@router.post(
    "/projects/{project_id}/macs-results", response_model=MacsResultOut, status_code=201
)
async def post_macs_result(
    project_id: uuid.UUID,
    body: MacsResultCreate,
    db: DbSession,
):
    project = (
        await db.execute(select(Project.id).where(Project.id == project_id))
    ).scalar_one_or_none()
    if project is None:
        raise HTTPException(404, "Project not found")

    row = MacsResult(
        project_id=project_id,
        schema_=body.schema_,
        envelope=body.model_dump(by_alias=True, include=set(ENVELOPE_FIELDS)),
        critical_temp=body.critical_temp,
        section_factor=body.section_factor,
        governing_side=body.governing_side,
        section=body.section,
        exposure=body.exposure,
        windows_user=body.windows_user,
        client_timestamp=body.client_timestamp,
        client_version=body.client_version,
        run_id=body.run_id,
        label=body.label,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row
