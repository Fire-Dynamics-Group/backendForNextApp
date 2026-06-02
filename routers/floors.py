import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database import get_db
from models.db_models import Element, Floor
from models.project_schemas import ElementIn, ElementOut, FloorDetail
from services.s3_service import delete_pdf, get_presigned_url, s3_key_for_pdf, upload_pdf

router = APIRouter()


@router.get(
    "/{project_id}/floors/{floor_id}",
    response_model=FloorDetail,
)
async def get_floor(
    project_id: uuid.UUID,
    floor_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Floor)
        .where(Floor.id == floor_id, Floor.project_id == project_id)
        .options(selectinload(Floor.elements))
    )
    floor = result.scalar_one_or_none()
    if not floor:
        raise HTTPException(404, "Floor not found")
    return floor


# --- PDF upload / download ---

@router.post("/{project_id}/floors/{floor_id}/pdf")
async def upload_floor_pdf(
    project_id: uuid.UUID,
    floor_id: uuid.UUID,
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Floor).where(Floor.id == floor_id, Floor.project_id == project_id)
    )
    floor = result.scalar_one_or_none()
    if not floor:
        raise HTTPException(404, "Floor not found")

    file_bytes = await file.read()
    key = upload_pdf(str(project_id), str(floor_id), file_bytes)
    floor.pdf_s3_key = key
    await db.commit()
    return {"pdf_s3_key": key}


@router.get("/{project_id}/floors/{floor_id}/pdf")
async def get_floor_pdf_url(
    project_id: uuid.UUID,
    floor_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Floor).where(Floor.id == floor_id, Floor.project_id == project_id)
    )
    floor = result.scalar_one_or_none()
    if not floor:
        raise HTTPException(404, "Floor not found")
    if not floor.pdf_s3_key:
        raise HTTPException(404, "No PDF uploaded for this floor")

    url = get_presigned_url(floor.pdf_s3_key)
    return {"url": url}


# --- Elements ---

@router.get(
    "/{project_id}/floors/{floor_id}/elements",
    response_model=list[ElementOut],
)
async def get_elements(
    project_id: uuid.UUID,
    floor_id: uuid.UUID,
    mode: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Floor).where(Floor.id == floor_id, Floor.project_id == project_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(404, "Floor not found")

    query = select(Element).where(Element.floor_id == floor_id)
    if mode is not None:
        query = query.where(Element.mode == mode)
    result = await db.execute(query)
    return result.scalars().all()


@router.put(
    "/{project_id}/floors/{floor_id}/elements",
    response_model=list[ElementOut],
)
async def replace_elements(
    project_id: uuid.UUID,
    floor_id: uuid.UUID,
    elements: list[ElementIn],
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Floor).where(Floor.id == floor_id, Floor.project_id == project_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(404, "Floor not found")

    # Delete existing elements
    await db.execute(delete(Element).where(Element.floor_id == floor_id))

    # Insert new
    new_elements = []
    for el in elements:
        element = Element(
            floor_id=floor_id,
            element_index=el.element_index,
            type=el.type,
            points=[p.model_dump() for p in el.points],
            comments=el.comments,
            mode=el.mode,
        )
        db.add(element)
        new_elements.append(element)

    await db.commit()
    for e in new_elements:
        await db.refresh(e)
    return new_elements
