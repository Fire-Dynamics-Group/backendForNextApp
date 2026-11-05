"""Endpoints for the i-macs Windows desktop app, mounted under `/imacs`.

Every route here is gated by `require_imacs_app` (shared app key) and NOT by
`current_user`. The upload-canvas read side lives on the projects and handoffs
routers behind the normal user auth.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.imacs import require_imacs_app
from database import get_db
from models.db_models import ImacsJobLink, MacsHandoff, MacsRun, Project
from models.macs_schemas import (
    ImacsJobLinkCreate,
    ImacsJobLinkOut,
    ImacsJobSummary,
    ImacsProjectOut,
    MacsHandoffResponse,
    MacsRunCreate,
    MacsRunOut,
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


async def _save_macs_run(
    db: AsyncSession,
    body: MacsRunCreate,
    project_id: uuid.UUID | None,
) -> MacsRun:
    outputs = dict(body.outputs or {})
    if body.macs_batch:
        outputs["macs_batch"] = body.macs_batch

    row = MacsRun(
        project_id=project_id,
        schema_=body.schema_,
        inputs=body.inputs,
        outputs=outputs,
        checks=body.checks,
        time_series=body.time_series,
        section=body.section,
        exposure=body.exposure,
        critical_temp=body.critical_temp,
        section_factor=body.section_factor,
        governing_side=body.governing_side,
        windows_user=body.windows_user,
        machine_name=body.machine_name,
        client_timestamp=body.client_timestamp,
        client_version=body.client_version,
        run_id=body.run_id,
        label=body.label,
        imacs_job_id=body.imacs_job_id,
        received_at=datetime.now(timezone.utc),
    )
    db.add(row)
    await db.flush()

    if project_id is not None:
        if body.macs_batch:
            project = (
                await db.execute(select(Project).where(Project.id == project_id))
            ).scalar_one_or_none()
            if project is not None:
                from sqlalchemy.orm.attributes import flag_modified
                project.settings = {**(project.settings or {}), "macsBatch": body.macs_batch}
                flag_modified(project, "settings")

        if body.imacs_job_id:
            link = (
                await db.execute(
                    select(ImacsJobLink).where(ImacsJobLink.imacs_job_id == body.imacs_job_id)
                )
            ).scalar_one_or_none()
            if link is not None:
                link.project_id = project_id
                link.updated_at = datetime.now(timezone.utc)
            else:
                db.add(ImacsJobLink(imacs_job_id=body.imacs_job_id, project_id=project_id))

    return row


@router.post(
    "/projects/{project_id}/macs-runs", response_model=MacsRunOut, status_code=201
)
@router.post(
    "/projects/{project_id}/macs-results", response_model=MacsRunOut, status_code=201, include_in_schema=False
)
async def post_macs_run(
    project_id: uuid.UUID,
    body: MacsRunCreate,
    db: DbSession,
):
    project = (
        await db.execute(select(Project.id).where(Project.id == project_id))
    ).scalar_one_or_none()
    if project is None:
        raise HTTPException(404, "Project not found")

    row = await _save_macs_run(db, body, project_id)
    await db.commit()
    await db.refresh(row)
    return row


@router.post("/handoffs", response_model=MacsHandoffResponse, status_code=201)
async def create_handoff(
    body: MacsRunCreate,
    db: DbSession,
):
    """Store a run with no project and return {handoff_id, expires_at}."""
    run = await _save_macs_run(db, body, project_id=None)
    handoff = MacsHandoff(
        id=uuid.uuid4(),
        run_id=run.id,
        imacs_job_id=body.imacs_job_id,
        created_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
    )
    db.add(handoff)
    await db.commit()
    return MacsHandoffResponse(handoff_id=handoff.id, expires_at=handoff.expires_at)


@router.get("/jobs/{imacs_job_id}/summary", response_model=ImacsJobSummary | None)
async def get_job_summary(
    imacs_job_id: str,
    db: DbSession,
):
    """Return linked project id, name, last_sent_at and stored outcome, or null if unlinked."""
    link = (
        await db.execute(
            select(ImacsJobLink).where(ImacsJobLink.imacs_job_id == imacs_job_id)
        )
    ).scalar_one_or_none()
    if link is None:
        return None

    project = (
        await db.execute(select(Project).where(Project.id == link.project_id))
    ).scalar_one_or_none()
    if project is None:
        return None

    max_received = (
        await db.execute(
            select(func.max(MacsRun.received_at)).where(MacsRun.project_id == project.id)
        )
    ).scalar()

    settings = project.settings or {}
    outcome = settings.get("timeEqResult") or settings.get("timeEqOutcome")

    return ImacsJobSummary(
        project_id=project.id,
        project_name=project.name,
        last_sent_at=max_received,
        outcome=outcome,
    )


@router.post("/jobs/{imacs_job_id}/link", response_model=ImacsJobLinkOut)
@router.put("/jobs/{imacs_job_id}/link", response_model=ImacsJobLinkOut)
async def link_job(
    imacs_job_id: str,
    body: ImacsJobLinkCreate,
    db: DbSession,
):
    """Map client-generated imacs_job_id to an upload-canvas project."""
    project = (
        await db.execute(select(Project.id).where(Project.id == body.project_id))
    ).scalar_one_or_none()
    if project is None:
        raise HTTPException(404, "Project not found")

    link = (
        await db.execute(
            select(ImacsJobLink).where(ImacsJobLink.imacs_job_id == imacs_job_id)
        )
    ).scalar_one_or_none()
    if link is not None:
        link.project_id = body.project_id
        link.updated_at = datetime.now(timezone.utc)
    else:
        link = ImacsJobLink(imacs_job_id=imacs_job_id, project_id=body.project_id)
        db.add(link)

    await db.commit()
    return ImacsJobLinkOut(imacs_job_id=imacs_job_id, project_id=body.project_id, linked=True)


@router.delete("/jobs/{imacs_job_id}/link")
@router.post("/jobs/{imacs_job_id}/unlink")
async def unlink_job(
    imacs_job_id: str,
    db: DbSession,
):
    """Remove the mapping for this imacs_job_id."""
    await db.execute(
        delete(ImacsJobLink).where(ImacsJobLink.imacs_job_id == imacs_job_id)
    )
    await db.commit()
    return {"imacs_job_id": imacs_job_id, "unlinked": True}
