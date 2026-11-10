import os
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import delete, select, update
from sqlalchemy.exc import OperationalError
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


def claimed_handoff_detail(project_id) -> dict:
    """Same 409 object as GET /handoffs/{id}."""
    return {
        "message": "Handoff has already been claimed",
        "claimed_by_project_id": str(project_id) if project_id else None,
    }


async def claim_handoff_once(
    db: AsyncSession, handoff: MacsHandoff, project_id: uuid.UUID
) -> None:
    """Attach this handoff to project_id only when claimed_at is still null.

    Two requests can both observe a null claimed_at. The conditional update is
    the gate: one row matches, the other comes back empty and raises 409.
    """
    now = datetime.now(timezone.utc)
    handoff_id = handoff.id
    lock_error = None
    try:
        claimed_id = (
            await db.execute(
                update(MacsHandoff)
                .where(
                    MacsHandoff.id == handoff_id,
                    MacsHandoff.claimed_at.is_(None),
                )
                .values(claimed_at=now, claimed_project_id=project_id)
                .returning(MacsHandoff.id)
            )
        ).scalar_one_or_none()
    except OperationalError as exc:
        claimed_id = None
        lock_error = exc
    if claimed_id is not None:
        handoff.claimed_at = now
        handoff.claimed_project_id = project_id
        return

    await db.rollback()
    # Column select, not the entity: rollback expired the loaded handoff, and
    # touching that instance would lazy-load outside the async greenlet.
    current = (
        await db.execute(
            select(MacsHandoff.claimed_at, MacsHandoff.claimed_project_id).where(
                MacsHandoff.id == handoff_id
            )
        )
    ).one_or_none()
    if current is not None and current.claimed_at is not None:
        raise HTTPException(409, claimed_handoff_detail(current.claimed_project_id))
    if lock_error is not None:
        raise lock_error
    raise HTTPException(404, "Handoff not found")


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
            raise HTTPException(409, claimed_handoff_detail(handoff.claimed_project_id))
        exp = handoff.expires_at if handoff.expires_at.tzinfo else handoff.expires_at.replace(tzinfo=timezone.utc)
        if exp < datetime.now(timezone.utc):
            raise HTTPException(410, "Handoff has expired")

    creator = None
    if user:
        creator = user.name or user.email or user.oid
    if not creator:
        creator = body.created_by
    if not creator and handoff and handoff.run and handoff.run.windows_user:
        creator = handoff.run.windows_user

    project = Project(
        name=body.name,
        mode=body.mode,
        settings=body.settings,
        created_by=creator,
    )
    db.add(project)
    await db.flush()

    if handoff is not None:
        await claim_handoff_once(db, handoff, project.id)
        handoff.run.project_id = project.id
        macs_batch = dict((handoff.run.outputs or {}).get("macs_batch") or {})

        # If project name is default/generic, adopt the batch/project name from desktop
        resolved_name = (
            macs_batch.get("project_name")
            or handoff.run.label
            or macs_batch.get("name")
        )
        if resolved_name and resolved_name != "MACS Run" and (not project.name or project.name in ("Untitled Project", "MACS Run", "Structural Fire Assessment")):
            project.name = resolved_name

        # Ensure governing section & critical temp are populated on macs_batch
        if handoff.run.section and not macs_batch.get("governing_section"):
            macs_batch["governing_section"] = handoff.run.section
        if handoff.run.critical_temp is not None and macs_batch.get("critical_temp") is None:
            macs_batch["critical_temp"] = handoff.run.critical_temp
        if handoff.run.section_factor is not None and macs_batch.get("section_factor") is None:
            macs_batch["section_factor"] = handoff.run.section_factor

        new_settings = dict(project.settings or {})
        if macs_batch:
            new_settings["macsBatch"] = macs_batch

        time_eq_inputs = dict(new_settings.get("timeEqInputs") or {})
        if not time_eq_inputs.get("section") and handoff.run.section:
            time_eq_inputs["section"] = handoff.run.section
        if not time_eq_inputs.get("criticalTemp") and handoff.run.critical_temp is not None:
            time_eq_inputs["criticalTemp"] = handoff.run.critical_temp
        if not time_eq_inputs.get("sectionFactor") and handoff.run.section_factor is not None:
            time_eq_inputs["sectionFactor"] = handoff.run.section_factor
        if not time_eq_inputs.get("macsRunId") and handoff.run.id:
            time_eq_inputs["macsRunId"] = str(handoff.run.id)
        new_settings["timeEqInputs"] = time_eq_inputs

        from sqlalchemy.orm.attributes import flag_modified
        project.settings = new_settings
        flag_modified(project, "settings")
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


@router.get("/macs-runs", response_model=list[MacsRunOut])
async def list_all_macs_runs(
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    """List recent MACS runs across all projects or unlinked, newest first."""
    result = await db.execute(
        select(MacsRun)
        .order_by(MacsRun.received_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return result.scalars().all()


@router.get("/macs-runs/{run_id}", response_model=MacsRunOut)
async def get_macs_run(
    run_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Retrieve full details of a specific MACS run."""
    run = (
        await db.execute(select(MacsRun).where(MacsRun.id == run_id))
    ).scalar_one_or_none()
    if run is None:
        raise HTTPException(404, "MACS run not found")
    return run


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


IMACS_DB_PATH = os.environ.get(
    "IMACS_DB_PATH",
    r"C:\Users\IanShaw\Documents\localProgramming\fd\i-macs\results.db",
)


@router.get("/{project_id}/macs-batch/{batch_id}")
async def get_batch_summary(
    project_id: uuid.UUID,
    batch_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Retrieve full batch summary, metadata, setup, and shear connection checks."""
    # 1. Return project.settings["macsBatch"] first if available
    project = (
        await db.execute(select(Project).where(Project.id == project_id))
    ).scalar_one_or_none()
    if project and project.settings and "macsBatch" in project.settings:
        cached = project.settings["macsBatch"]
        if isinstance(cached, dict) and (str(cached.get("batch_id")) == str(batch_id) or not cached.get("batch_id")):
            return cached

    db_path = IMACS_DB_PATH
    if not os.path.exists(db_path):
        alt = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "i-macs", "results.db")
        )
        if os.path.exists(alt):
            db_path = alt

    if not os.path.exists(db_path):
        raise HTTPException(500, f"MACS results database not found at {db_path}")

    imacs_root = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "i-macs")
    )
    if imacs_root not in sys.path:
        sys.path.insert(0, imacs_root)

    try:
        from macs_automation.db import ResultsDB
        from macs_automation.app import _batch_response
        from macs_automation.batch_setup import derive_setup
        from macs_automation.shear_check import flags_for_run

        db = ResultsDB(db_path)
        batches = db.get_batches()
        row = next((r for r in batches if r["batch_id"] == batch_id), None)
        if row is None:
            db.close()
            raise HTTPException(404, f"Batch {batch_id} not found")

        resp = _batch_response(db, row)
        runs = db.get_batch_runs(batch_id)
        resp["setup"] = derive_setup(runs)
        sub_limit = [
            {"run_id": r.get("id"), "flags": flags}
            for r in runs
            if (flags := flags_for_run(r))
        ]
        resp["shear_check"] = {
            "batch_id": batch_id,
            "checked": len(runs),
            "sub_limit_runs": sub_limit,
        }
        total = resp.get("run_count") or 0
        passes = resp.get("pass_count") or 0
        resp["reliability_percent"] = round((passes / total) * 100, 2) if total > 0 else 0
        db.close()
        return resp
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Failed to retrieve batch {batch_id}: {e}")


@router.get("/{project_id}/macs-batch/{batch_id}/distribution")
async def get_batch_distribution(
    project_id: uuid.UUID,
    batch_id: str,
    column: Annotated[str, Query()],
    spaghetti_n: Annotated[int, Query()] = 500,
):
    """Return spaghetti + exact server-side average for a batch's distribution curves."""
    imacs_root = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "i-macs")
    )
    if imacs_root not in sys.path:
        sys.path.insert(0, imacs_root)

    try:
        from macs_automation.app import api_batch_distribution
        resp = api_batch_distribution(batch_id, column, spaghetti_n)
        if hasattr(resp, "body"):
            import json
            return json.loads(resp.body)
        return resp
    except Exception as e:
        raise HTTPException(500, f"Failed to compute distribution for {column}: {e}")


@router.get("/{project_id}/macs-batch/{batch_id}/runs")
async def list_batch_runs(
    project_id: uuid.UUID,
    batch_id: str,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    search: Annotated[Optional[str], Query()] = None,
    status: Annotated[Optional[str], Query()] = None,
    sort_by: Annotated[str, Query()] = "id",
    sort_order: Annotated[str, Query()] = "asc",
):
    """List runs within a specific MACS batch with pagination, search, and sorting."""
    db_path = IMACS_DB_PATH
    if not os.path.exists(db_path):
        alt = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "i-macs", "results.db")
        )
        if os.path.exists(alt):
            db_path = alt

    if not os.path.exists(db_path):
        raise HTTPException(500, f"MACS results database not found at {db_path}")

    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    where_clauses = ["batch_id = ?"]
    params: list[object] = [batch_id]

    if search and search.strip():
        s = search.strip()
        where_clauses.append("(CAST(id AS TEXT) LIKE ? OR uuid LIKE ?)")
        params.extend([f"%{s}%", f"%{s}%"])

    if status == "pass":
        where_clauses.append(
            "(uf_max <= 1.001 AND (comp_failure = 0 OR comp_failure IS NULL) AND error IS NULL)"
        )
    elif status == "fail":
        where_clauses.append(
            "(uf_max > 1.001 OR comp_failure = 1 OR error IS NOT NULL)"
        )

    where_sql = " AND ".join(where_clauses)

    cur.execute(f"SELECT COUNT(*) FROM runs WHERE {where_sql}", params)
    total_count = cur.fetchone()[0]

    col_map = {
        "id": "id",
        "qf": "qf",
        "window_percent": "window_percent",
        "uf_max": "uf_max",
        "crit_temp": "COALESCE(side_a_critical_temp, side_b_critical_temp, 0)",
        "deflection": "max_deflection",
        "temperature": "max_temperature",
    }
    order_col = col_map.get(sort_by, "id")
    direction = "DESC" if sort_order.lower() == "desc" else "ASC"

    offset = (page - 1) * limit
    cur.execute(
        f"""
        SELECT id, uuid, qf, window_percent, uf_max, max_temperature, max_deflection, 
               side_a_critical_temp, side_a_load_ratio,
               side_b_critical_temp, side_b_load_ratio,
               side_c_critical_temp, side_c_load_ratio,
               side_d_critical_temp, side_d_load_ratio,
               comp_failure, error
        FROM runs 
        WHERE {where_sql} 
        ORDER BY {order_col} {direction} 
        LIMIT ? OFFSET ?
        """,
        params + [limit, offset],
    )
    rows = [dict(r) for r in cur.fetchall()]
    con.close()

    items = []
    for r in rows:
        temps = [
            ("A", r.get("side_a_critical_temp")),
            ("B", r.get("side_b_critical_temp")),
            ("C", r.get("side_c_critical_temp")),
            ("D", r.get("side_d_critical_temp")),
        ]
        valid_temps = [(s, t) for s, t in temps if t is not None and t > 0]
        gov_side, gov_temp = min(valid_temps, key=lambda x: x[1]) if valid_temps else (None, None)
        is_pass = bool(
            (r.get("uf_max") or 0) <= 1.001
            and not r.get("comp_failure")
            and not r.get("error")
        )

        items.append({
            "id": r["id"],
            "uuid": r["uuid"],
            "qf": round(r["qf"], 1) if r.get("qf") is not None else None,
            "window_percent": (
                round(r["window_percent"], 1)
                if r.get("window_percent") is not None
                else None
            ),
            "uf_max": round(r["uf_max"], 3) if r.get("uf_max") is not None else None,
            "max_temperature": (
                round(r["max_temperature"])
                if r.get("max_temperature") is not None
                else None
            ),
            "max_deflection": (
                round(r["max_deflection"], 1)
                if r.get("max_deflection") is not None
                else None
            ),
            "governing_temp": round(gov_temp) if gov_temp is not None else None,
            "governing_side": gov_side,
            "pass": is_pass,
            "error": r.get("error"),
        })

    return {
        "batch_id": batch_id,
        "total": total_count,
        "page": page,
        "limit": limit,
        "total_pages": (total_count + limit - 1) // limit if limit > 0 else 1,
        "runs": items,
    }


@router.get("/{project_id}/macs-batch/{batch_id}/runs/{run_id}")
async def get_batch_run_detail(
    project_id: uuid.UUID,
    batch_id: str,
    run_id: int,
):
    """Retrieve full run details, time-series curves, and FRACOF checks for an arbitrary run in the batch."""
    db_path = IMACS_DB_PATH
    if not os.path.exists(db_path):
        alt = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "i-macs", "results.db")
        )
        if os.path.exists(alt):
            db_path = alt

    if not os.path.exists(db_path):
        raise HTTPException(500, f"MACS results database not found at {db_path}")

    imacs_root = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "i-macs")
    )
    if imacs_root not in sys.path:
        sys.path.insert(0, imacs_root)

    try:
        from macs_automation.db import ResultsDB
        from macs_automation.upload_canvas import build_macs_run_payload

        db = ResultsDB(db_path)
        run_row = db.get_run(run_id)
        if not run_row:
            db.close()
            raise HTTPException(404, f"Run #{run_id} not found in batch {batch_id}")

        payload = build_macs_run_payload(run_row, imacs_job_id=batch_id, db=db)
        db.close()
        return payload
    except Exception as e:
        raise HTTPException(500, f"Failed to load run #{run_id}: {e}")


@router.post(
    "/{project_id}/macs-handoffs/{handoff_id}/claim",
    response_model=MacsRunOut,
)
async def claim_macs_handoff(
    project_id: uuid.UUID,
    handoff_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Identity | None = Depends(current_user),
):
    """Claim a handoff onto an existing project, attaching the run and recording the link."""
    project = (
        await db.execute(select(Project).where(Project.id == project_id))
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
        raise HTTPException(409, claimed_handoff_detail(handoff.claimed_project_id))
    exp = handoff.expires_at if handoff.expires_at.tzinfo else handoff.expires_at.replace(tzinfo=timezone.utc)
    if exp < datetime.now(timezone.utc):
        raise HTTPException(410, "Handoff has expired")

    await claim_handoff_once(db, handoff, project_id)
    handoff.run.project_id = project_id

    macs_batch = dict((handoff.run.outputs or {}).get("macs_batch") or {})
    if handoff.run.section and not macs_batch.get("governing_section"):
        macs_batch["governing_section"] = handoff.run.section
    if handoff.run.critical_temp is not None and macs_batch.get("critical_temp") is None:
        macs_batch["critical_temp"] = handoff.run.critical_temp
    if handoff.run.section_factor is not None and macs_batch.get("section_factor") is None:
        macs_batch["section_factor"] = handoff.run.section_factor

    new_settings = dict(project.settings or {})
    if macs_batch:
        new_settings["macsBatch"] = macs_batch

    time_eq_inputs = dict(new_settings.get("timeEqInputs") or {})
    if not time_eq_inputs.get("section") and handoff.run.section:
        time_eq_inputs["section"] = handoff.run.section
    if not time_eq_inputs.get("criticalTemp") and handoff.run.critical_temp is not None:
        time_eq_inputs["criticalTemp"] = handoff.run.critical_temp
    if not time_eq_inputs.get("sectionFactor") and handoff.run.section_factor is not None:
        time_eq_inputs["sectionFactor"] = handoff.run.section_factor
    if not time_eq_inputs.get("macsRunId") and handoff.run.id:
        time_eq_inputs["macsRunId"] = str(handoff.run.id)
    new_settings["timeEqInputs"] = time_eq_inputs

    from sqlalchemy.orm.attributes import flag_modified
    project.settings = new_settings
    flag_modified(project, "settings")

    if not project.created_by or project.created_by == "Unknown":
        creator = (user.name or user.email) if user else (handoff.run.windows_user if handoff.run else None)
        if creator:
            project.created_by = creator

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


@router.post("/{project_id}/structural-fire-report")
async def generate_structural_fire_report_endpoint(
    project_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[Optional[Identity], Depends(current_user)] = None,
):
    project = (
        await db.execute(select(Project).where(Project.id == project_id))
    ).scalar_one_or_none()
    if project is None:
        raise HTTPException(404, "Project not found")

    runs_result = await db.execute(
        select(MacsRun)
        .where(MacsRun.project_id == project_id)
        .order_by(MacsRun.received_at.desc())
    )
    latest_run = runs_result.scalars().first()

    from services.structural_fire_report import build_structural_fire_report_docx
    docx_bytes = build_structural_fire_report_docx(project, latest_run)

    import re
    safe_name = re.sub(r"[^\w\s-]", "", project.name or "Project").strip().replace(" ", "_")
    filename = f"Structural_Fire_Report_{safe_name}.docx"

    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

