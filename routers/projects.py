import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
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
    project = Project(name=body.name, settings=body.settings, created_by=body.created_by)
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project


@router.get("", response_model=list[ProjectDetail])
async def list_projects(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Project)
        .options(selectinload(Project.floors))
        .order_by(Project.updated_at.desc())
    )
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

    # Build a map of existing floors by floor_number to preserve pdf_s3_key
    existing_floors = {f.floor_number: f for f in project.floors}

    # Delete all existing elements for this project's floors
    floor_ids = [f.id for f in project.floors]
    if floor_ids:
        await db.execute(delete(Element).where(Element.floor_id.in_(floor_ids)))

    # Delete all existing floors
    await db.execute(delete(Floor).where(Floor.project_id == project_id))

    # Re-create floors and elements
    new_floors = []
    for fp in body.floors:
        # Preserve existing pdf_s3_key if the floor existed before
        old_floor = existing_floors.get(fp.floor_number)
        pdf_key = old_floor.pdf_s3_key if old_floor else None

        floor = Floor(
            project_id=project_id,
            floor_number=fp.floor_number,
            name=fp.name,
            canvas_dimensions=fp.canvas_dimensions,
            pixels_per_mesh=fp.pixels_per_mesh,
            origin_pixels=fp.origin_pixels,
            settings=fp.settings,
            pdf_s3_key=pdf_key,
        )
        db.add(floor)
        await db.flush()  # get floor.id

        for el in fp.elements:
            element = Element(
                floor_id=floor.id,
                element_index=el.element_index,
                type=el.type,
                points=[p.model_dump() for p in el.points],
                comments=el.comments,
            )
            db.add(element)
        new_floors.append(floor)

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
