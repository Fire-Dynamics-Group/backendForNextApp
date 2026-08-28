"""Warehouse smoke layer API endpoints.

The zone model runs in the browser. These endpoints format results they are given
and store named input sets — they never recompute the model.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.smoke_layer_models import (
    SavedRunCreate,
    SavedRunResponse,
    SmokeLayerReportRequest,
    SmokeLayerRun,
)
from services.smoke_layer_report_service import generate_smoke_layer_report

router = APIRouter()

DOCX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)


@router.post("/report")
async def generate_report(data: SmokeLayerReportRequest):
    """Render the Word report from the supplied inputs and results."""
    if not data.results.steps:
        raise HTTPException(status_code=422, detail="No results to report on.")

    try:
        doc_bytes = generate_smoke_layer_report(
            project_name=data.project_name,
            engineer_name=data.engineer_name,
            inputs=data.inputs,
            results=data.results,
        )
    except Exception as e:  # noqa: BLE001 — surfaced to the client as a 500
        print(f"Error generating smoke layer report: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate report: {e}")

    filename = (data.project_name.strip().replace(" ", "_") or "Warehouse") + "_Smoke_Layer.docx"
    response = StreamingResponse(doc_bytes, media_type=DOCX_MEDIA_TYPE)
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@router.get("/runs", response_model=list[SavedRunResponse])
async def list_runs(db: AsyncSession = Depends(get_db)):
    """List saved input sets, most recently updated first."""
    result = await db.execute(select(SmokeLayerRun).order_by(SmokeLayerRun.updated_at.desc()))
    return result.scalars().all()


@router.post("/runs", response_model=SavedRunResponse)
async def create_run(data: SavedRunCreate, db: AsyncSession = Depends(get_db)):
    """Save a named set of inputs, replacing any run of the same name."""
    existing = await db.execute(select(SmokeLayerRun).where(SmokeLayerRun.name == data.name))
    run = existing.scalar_one_or_none()

    if run is None:
        run = SmokeLayerRun(id=uuid.uuid4(), name=data.name)
        db.add(run)

    run.project_name = data.project_name or None
    run.inputs = data.inputs.model_dump(by_alias=True)

    await db.commit()
    await db.refresh(run)
    return run


@router.delete("/runs/{run_id}", status_code=204)
async def delete_run(run_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Delete a saved input set."""
    result = await db.execute(select(SmokeLayerRun).where(SmokeLayerRun.id == run_id))
    run = result.scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="Saved run not found.")

    await db.delete(run)
    await db.commit()
