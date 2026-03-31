"""CFD simulation monitoring dashboard API endpoints."""

import os
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Any, Dict, List, Optional

from database import get_db
from models.cfd_models import CfdRunnerState, CfdSimulation
from models.db_models import utcnow

router = APIRouter()


class StatusUpdate(BaseModel):
    event: str
    data: Dict[str, Any] = {}


def verify_api_key(x_api_key: str = Header(...)):
    expected = os.environ.get("FDS_API_KEY", "")
    if not expected or not secrets.compare_digest(x_api_key, expected):
        raise HTTPException(status_code=403, detail="Invalid API key")


async def _upsert_runner(
    db: AsyncSession,
    status: str,
    pending_files: Optional[List[str]] = None,
) -> None:
    result = await db.execute(select(CfdRunnerState).where(CfdRunnerState.id == 1))
    runner = result.scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if runner is None:
        runner = CfdRunnerState(
            id=1,
            status=status,
            pending_files=pending_files,
            last_heartbeat=now,
        )
        db.add(runner)
    else:
        runner.status = status
        if pending_files is not None:
            runner.pending_files = pending_files
        runner.last_heartbeat = now
    await db.flush()


async def _update_runner_heartbeat(db: AsyncSession) -> None:
    result = await db.execute(select(CfdRunnerState).where(CfdRunnerState.id == 1))
    runner = result.scalar_one_or_none()
    if runner is not None:
        runner.last_heartbeat = datetime.now(timezone.utc)
        await db.flush()


@router.post("/status")
async def post_status(
    body: StatusUpdate,
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(verify_api_key),
):
    event = body.event
    data = body.data
    now = datetime.now(timezone.utc)

    if event == "runner_started":
        pending = data.get("pending_files", [])
        await _upsert_runner(db, status="online", pending_files=pending)
        # Insert queued simulations for pending files
        for filename in pending:
            # Check if simulation already exists
            result = await db.execute(
                select(CfdSimulation).where(CfdSimulation.name == filename)
            )
            existing = result.scalar_one_or_none()
            if existing is None:
                sim = CfdSimulation(name=filename, status="queued")
                db.add(sim)
        await db.commit()
        return {"ok": True}

    elif event == "sim_started":
        name = data.get("name", "")
        meshes = data.get("meshes")
        t_end = data.get("t_end")
        # Upsert simulation
        result = await db.execute(
            select(CfdSimulation).where(CfdSimulation.name == name)
        )
        sim = result.scalar_one_or_none()
        if sim is None:
            sim = CfdSimulation(
                name=name,
                status="running",
                meshes=meshes,
                t_end=t_end,
                started_at=now,
            )
            db.add(sim)
        else:
            sim.status = "running"
            sim.meshes = meshes
            sim.t_end = t_end
            sim.started_at = now
        await _update_runner_heartbeat(db)
        await db.commit()
        return {"ok": True}

    elif event == "sim_progress":
        name = data.get("name", "")
        progress = data.get("progress_pct", 0)
        result = await db.execute(
            select(CfdSimulation).where(
                CfdSimulation.name == name,
                CfdSimulation.status == "running",
            )
        )
        sim = result.scalar_one_or_none()
        if sim is not None:
            sim.progress_pct = progress
        await _update_runner_heartbeat(db)
        await db.commit()
        return {"ok": True}

    elif event == "sim_completed":
        name = data.get("name", "")
        result = await db.execute(
            select(CfdSimulation).where(CfdSimulation.name == name)
        )
        sim = result.scalar_one_or_none()
        if sim is not None:
            sim.status = "completed"
            sim.completed_at = now
        await _update_runner_heartbeat(db)
        await db.commit()
        return {"ok": True}

    elif event == "sim_error":
        name = data.get("name", "")
        error_msg = data.get("error_msg", "")
        result = await db.execute(
            select(CfdSimulation).where(CfdSimulation.name == name)
        )
        sim = result.scalar_one_or_none()
        if sim is not None:
            sim.status = "error"
            sim.error_msg = error_msg
        await _update_runner_heartbeat(db)
        await db.commit()
        return {"ok": True}

    elif event == "runner_idle":
        await _upsert_runner(db, status="idle", pending_files=[])
        await db.commit()
        return {"ok": True}

    else:
        raise HTTPException(status_code=400, detail=f"Unknown event: {event}")


@router.get("/state")
async def get_state(db: AsyncSession = Depends(get_db)):
    now = datetime.now(timezone.utc)

    # Runner state
    result = await db.execute(select(CfdRunnerState).where(CfdRunnerState.id == 1))
    runner_row = result.scalar_one_or_none()
    if runner_row is None:
        runner_info = {"status": "offline", "last_heartbeat": None}
    else:
        heartbeat = runner_row.last_heartbeat
        # SQLite returns strings; Postgres returns datetime objects
        if isinstance(heartbeat, str):
            heartbeat = datetime.fromisoformat(heartbeat)
        if heartbeat.tzinfo is None:
            heartbeat = heartbeat.replace(tzinfo=timezone.utc)
        elapsed = (now - heartbeat).total_seconds()
        status = "offline" if elapsed > 90 else runner_row.status
        runner_info = {
            "status": status,
            "last_heartbeat": heartbeat.isoformat(),
        }

    # Current running simulation
    result = await db.execute(
        select(CfdSimulation)
        .where(CfdSimulation.status == "running")
        .order_by(CfdSimulation.started_at.desc())
        .limit(1)
    )
    current_sim = result.scalar_one_or_none()

    # Queued simulations
    result = await db.execute(
        select(CfdSimulation).where(CfdSimulation.status == "queued")
    )
    queue = result.scalars().all()

    # Last 20 completed
    result = await db.execute(
        select(CfdSimulation)
        .where(CfdSimulation.status == "completed")
        .order_by(CfdSimulation.completed_at.desc())
        .limit(20)
    )
    completed = result.scalars().all()

    # Last 10 errors
    result = await db.execute(
        select(CfdSimulation)
        .where(CfdSimulation.status == "error")
        .order_by(CfdSimulation.updated_at.desc())
        .limit(10)
    )
    errors = result.scalars().all()

    def sim_to_dict(s):
        return {
            "id": s.id,
            "name": s.name,
            "status": s.status,
            "meshes": s.meshes,
            "t_end": s.t_end,
            "progress_pct": s.progress_pct,
            "started_at": s.started_at.isoformat() if s.started_at else None,
            "completed_at": s.completed_at.isoformat() if s.completed_at else None,
            "error_msg": s.error_msg,
            "updated_at": s.updated_at.isoformat() if s.updated_at else None,
        }

    return {
        "runner": runner_info,
        "current": sim_to_dict(current_sim) if current_sim else None,
        "queue": [sim_to_dict(s) for s in queue],
        "completed": [sim_to_dict(s) for s in completed],
        "errors": [sim_to_dict(s) for s in errors],
    }
