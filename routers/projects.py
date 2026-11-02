import uuid
from datetime import datetime, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from auth.deps import current_user
from auth.entra import Identity
from database import get_db
from models.db_models import Element, Floor, ImacsJobLink, MacsHandoff, MacsRun, Project
from models.macs_schemas import MacsRunOut
from models.project_schemas import (
    ProjectCreate,
    ProjectDetail,
    ProjectSavePayload,
    ProjectSummary,
    ProjectUpdate,
)

router = APIRouter()


@router.post("", response_model=ProjectSummary, status_code=201)
async def create_project(
    body: ProjectCreate,
    db: AsyncSession = Depends(get_db),
    user: Identity | None = Depends(current_user),
):
    handoff = None
    if body.handoff_id is not None:
        handoff = (
            await db.execute(
                select(MacsHandoff)
                .where(MacsHandoff.id == body.handoff_id)
                .options(selectinload(MacsHandoff.run))
            )
        ).scalar_one_or_none()
        if handoff is None:
            raise HTTPException(404, "Handoff not found")
        if handoff.claimed_at is not None:
            raise HTTPException(409, "Handoff has already been claimed")
        exp = handoff.expires_at if handoff.expires_at.tzinfo else handoff.expires_at.replace(tzinfo=timezone.utc)
        if exp < datetime.now(timezone.utc):
            raise HTTPException(410, "Handoff has expired")

    project = Project(
        name=body.name,
        mode=body.mode,
        settings=body.settings,
        # In enforce mode this is always the verified Entra oid; the body field
        # remains only so the log-mode rollout does not break existing clients.
        created_by=(user.oid or user.email) if user else body.created_by,
    )
    db.add(project)
    await db.flush()

    if handoff is not None:
        handoff.run.project_id = project.id
        handoff.claimed_at = datetime.now(timezone.utc)
        handoff.claimed_project_id = project.id
        if handoff.imacs_job_id:
            link = (
                await db.execute(
                    select(ImacsJobLink).where(ImacsJobLink.imacs_job_id == handoff.imacs_job_id)
                )
            ).scalar_one_or_none()
            if link is not None:
                link.project_id = project.id
                link.updated_at = datetime.now(timezone.utc)
            else:
                db.add(ImacsJobLink(imacs_job_id=handoff.imacs_job_id, project_id=project.id))

    await db.commit()
    await db.refresh(project)
    return project


@router.get("", response_model=list[ProjectDetail])
async def list_projects(
    mode: Optional[str] = Query(None, description="Only projects owned by this canvas mode"),
    db: AsyncSession = Depends(get_db),
):
    query = select(Project).options(selectinload(Project.floors))
    if mode is not None:
        query = query.where(Project.mode == mode)
    result = await db.execute(query.order_by(Project.updated_at.desc()))
    return result.scalars().all()


@router.get("/{project_id}/macs-runs", response_model=list[MacsRunOut])
@router.get(
    "/{project_id}/macs-results", response_model=list[MacsRunOut], include_in_schema=False
)
async def list_macs_runs(
    project_id: uuid.UUID, db: Annotated[AsyncSession, Depends(get_db)]
):
    """MACS runs posted by i-macs for this project, newest first. Read by the
    upload-canvas web app (user auth; the i-macs app key is not accepted here)."""
    exists = (
        await db.execute(select(Project.id).where(Project.id == project_id))
    ).scalar_one_or_none()
    if exists is None:
        raise HTTPException(404, "Project not found")
    result = await db.execute(
        select(MacsRun)
        .where(MacsRun.project_id == project_id)
        .order_by(MacsRun.received_at.desc())
    )
    return result.scalars().all()


@router.post(
    "/{project_id}/macs-handoffs/{handoff_id}/claim",
    response_model=MacsRunOut,
)
async def claim_macs_handoff(
    project_id: uuid.UUID,
    handoff_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Claim a handoff onto an existing project, attaching the run and recording the link."""
    project = (
        await db.execute(select(Project.id).where(Project.id == project_id))
    ).scalar_one_or_none()
    if project is None:
        raise HTTPException(404, "Project not found")

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
    exp = handoff.expires_at if handoff.expires_at.tzinfo else handoff.expires_at.replace(tzinfo=timezone.utc)
    if exp < datetime.now(timezone.utc):
        raise HTTPException(410, "Handoff has expired")

    handoff.run.project_id = project_id
    handoff.claimed_at = datetime.now(timezone.utc)
    handoff.claimed_project_id = project_id

    if handoff.imacs_job_id:
        link = (
            await db.execute(
                select(ImacsJobLink).where(ImacsJobLink.imacs_job_id == handoff.imacs_job_id)
            )
        ).scalar_one_or_none()
        if link is not None:
            link.project_id = project_id
            link.updated_at = datetime.now(timezone.utc)
        else:
            db.add(ImacsJobLink(imacs_job_id=handoff.imacs_job_id, project_id=project_id))

    await db.commit()
    await db.refresh(handoff.run)
    return handoff.run


@router.get("/{project_id}", response_model=ProjectDetail)
async def get_project(project_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Project)
        .where(Project.id == project_id)
        .options(selectinload(Project.floors))
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(404, "Project not found")
    return project


@router.put("/{project_id}", response_model=ProjectSummary)
async def update_project(
    project_id: uuid.UUID, body: ProjectUpdate, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(404, "Project not found")
    if body.name is not None:
        project.name = body.name
    if body.settings is not None:
        project.settings = body.settings
    project.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(project)
    return project


@router.delete("/{project_id}", status_code=204)
async def delete_project(project_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(404, "Project not found")
    await db.delete(project)
    await db.commit()


@router.post("/{project_id}/save", response_model=ProjectDetail)
async def save_project(
    project_id: uuid.UUID,
    body: ProjectSavePayload,
    db: AsyncSession = Depends(get_db),
):
    """Bulk save: update project settings + replace all floors and elements in one transaction."""
    result = await db.execute(
        select(Project)
        .where(Project.id == project_id)
        .options(selectinload(Project.floors).selectinload(Floor.elements))
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(404, "Project not found")

    # Update project-level fields
    if body.name is not None:
        project.name = body.name
    project.settings = body.settings
    project.updated_at = datetime.now(timezone.utc)

    # Reconcile floors by floor_number, updating in place so floor ids stay
    # stable across saves. The frontend caches floorId for PDF upload/fetch, so
    # minting a new floor uuid on every save (the old delete-then-recreate)
    # left that cached id stale -> mid-session PDF calls 404. Existing floors'
    # pdf_s3_key is preserved automatically (we never reassign it here).
    existing_floors = {f.floor_number: f for f in project.floors}
    incoming_numbers = {fp.floor_number for fp in body.floors}

    # Drop floors that are no longer present (cascades to their elements).
    for floor_number, floor in existing_floors.items():
        if floor_number not in incoming_numbers:
            await db.delete(floor)

    for fp in body.floors:
        floor = existing_floors.get(fp.floor_number)
        if floor is None:
            floor = Floor(project_id=project_id, floor_number=fp.floor_number)
            db.add(floor)
        floor.name = fp.name
        floor.canvas_dimensions = fp.canvas_dimensions
        floor.pixels_per_mesh = fp.pixels_per_mesh
        floor.origin_pixels = fp.origin_pixels
        floor.settings = fp.settings
        await db.flush()  # ensure floor.id for the elements below

        # Replace this floor's elements wholesale (element identity isn't
        # tracked across saves; element_index carries the frontend's id).
        await db.execute(delete(Element).where(Element.floor_id == floor.id))
        for el in fp.elements:
            db.add(Element(
                floor_id=floor.id,
                element_index=el.element_index,
                type=el.type,
                points=[p.model_dump() for p in el.points],
                comments=el.comments,
            ))

    await db.commit()

    # Expire cached state so the reload sees fresh data
    db.expire_all()

    # Reload for response
    result = await db.execute(
        select(Project)
        .where(Project.id == project_id)
        .options(selectinload(Project.floors))
    )
    return result.scalar_one()
