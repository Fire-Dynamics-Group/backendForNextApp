import uuid
from datetime import datetime, timezone

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database import get_db
from models.db_models import Element, Floor, Project
from models.project_schemas import (
    FloorSavePayload,
    ProjectCreate,
    ProjectDetail,
    ProjectSavePayload,
    ProjectSummary,
    ProjectUpdate,
)

router = APIRouter()


@router.post("", response_model=ProjectSummary, status_code=201)
async def create_project(body: ProjectCreate, db: AsyncSession = Depends(get_db)):
    project = Project(
        name=body.name, mode=body.mode, settings=body.settings, created_by=body.created_by
    )
    db.add(project)
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
