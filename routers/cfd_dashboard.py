"""CFD simulation monitoring dashboard API endpoints.

Phase 1 adds machines, runs, run_events, and a per-machine command queue.
The singleton cfd_runner_state row is still written for the first machine so
GET /state keeps its old shape. A second machine does not overwrite it.
Live charts: the runner POSTs /series, the page GETs /runs/{id}/series.
Every route requires X-API-Key (FDS_API_KEY).
"""

import logging
import os
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.cfd_models import (
    CfdRunnerState,
    CfdSimulation,
    Machine,
    Run,
    RunCommand,
    RunEvent,
)
from services.modelling_runs import (
    CLOUDHPC_ENABLED,
    as_utc,
    effective_machine_status,
)
from services.run_series import (
    SeriesRejected,
    get_devc_selection,
    read_series,
    set_devc_selection,
    store_series,
)

logger = logging.getLogger(__name__)


class StatusUpdate(BaseModel):
    event: str
    data: Dict[str, Any] = {}
    # Flat fields used by the phase-1 runner. Old callers keep nesting under data.
    machine_name: Optional[str] = None
    run_id: Optional[str] = None
    case_name: Optional[str] = None
    progress: Optional[float] = None
    sim_time: Optional[float] = None
    end_time: Optional[float] = None
    error: Optional[str] = None
    message: Optional[str] = None
    results_link: Optional[str] = None


class RunCreate(BaseModel):
    machine_id: Optional[str] = None
    machine_name: Optional[str] = None
    case_name: str
    input_file_ref: str
    created_by: Optional[str] = None


class CommandAck(BaseModel):
    status: str
    error: Optional[str] = None


class HrrPointIn(BaseModel):
    t: float
    hrr: float


class DevcColumnIn(BaseModel):
    id: str
    quantity: Optional[str] = None
    unit: Optional[str] = None


class DevcSampleIn(BaseModel):
    t: float
    values: Dict[str, float]


class SeriesPush(BaseModel):
    """Runner push. hrr points are {t, hrr} only. devc rows are one time
    and the columns the runner is sampling."""

    run_id: str
    machine_name: Optional[str] = None
    case_name: Optional[str] = None
    chid: Optional[str] = None
    devc_columns: List[DevcColumnIn] = []
    hrr: List[HrrPointIn] = []
    devc: List[DevcSampleIn] = []


def verify_api_key(x_api_key: str = Header(...)):
    expected = os.environ.get("FDS_API_KEY", "")
    if not expected or not secrets.compare_digest(x_api_key, expected):
        raise HTTPException(status_code=403, detail="Invalid API key")


# Applied to every route on this router, including the previously open GET /state.
router = APIRouter(dependencies=[Depends(verify_api_key)])

_RUN_EVENTS = {
    "runner_started",
    "heartbeat",
    "sim_started",
    "sim_progress",
    "sim_completed",
    "sim_error",
    "sim_stopped",
    "runner_idle",
}
_NO_RUN_STATUS_CHANGE = {"runner_started", "heartbeat", "runner_idle"}


def _copy_if_absent(data: Dict[str, Any], dest: str, src: str) -> None:
    if data.get(dest) is None and data.get(src) is not None:
        data[dest] = data[src]


def _merged_data(body: StatusUpdate) -> Dict[str, Any]:
    """Nested `data` wins when both shapes send the same fact.

    Legacy names and the phase-1 names are mirrors:
    progress_pct/progress, error_msg/error, t_end/end_time, name/case_name.
    """
    data = dict(body.data or {})
    _copy_if_absent(data, "case_name", "name")
    _copy_if_absent(data, "progress", "progress_pct")
    _copy_if_absent(data, "error", "error_msg")
    _copy_if_absent(data, "end_time", "t_end")
    if body.machine_name and not data.get("machine_name"):
        data["machine_name"] = body.machine_name
    if body.case_name and not data.get("case_name"):
        data["case_name"] = body.case_name
    if body.run_id and not data.get("run_id"):
        data["run_id"] = body.run_id
    if body.progress is not None and data.get("progress") is None:
        data["progress"] = body.progress
    if body.sim_time is not None and data.get("sim_time") is None:
        data["sim_time"] = body.sim_time
    if body.end_time is not None and data.get("end_time") is None:
        data["end_time"] = body.end_time
    if body.error and not data.get("error"):
        data["error"] = body.error
    if body.message and not data.get("message"):
        data["message"] = body.message
    if body.results_link and not data.get("results_link"):
        data["results_link"] = body.results_link
    _copy_if_absent(data, "name", "case_name")
    _copy_if_absent(data, "progress_pct", "progress")
    _copy_if_absent(data, "error_msg", "error")
    _copy_if_absent(data, "t_end", "end_time")
    return data


def _iso(value) -> Optional[str]:
    parsed = as_utc(value)
    return parsed.isoformat() if parsed else None


def _parse_uuid(value: Optional[str]) -> Optional[uuid.UUID]:
    if not value:
        return None
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError):
        return None


def _first_present(data: Dict[str, Any], *keys: str):
    for key in keys:
        if data.get(key) is not None:
            return data[key]
    return None


def _search_user(user: Optional[str], created_by: Optional[str]) -> str:
    chosen = (user or created_by or "").strip()
    return chosen or "unknown"


def _like_pattern(query: str) -> str:
    escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _machine_status_for_event(event: str) -> Optional[str]:
    # heartbeat: a run is active, so the machine is online.
    # runner_idle: the runner is up and no run is active. Posted about every
    # 15s, and it refreshes last_heartbeat_at the same way heartbeat does.
    # Quiet for 90s is offline either way.
    # sim_completed / sim_error / sim_stopped only refresh the heartbeat.
    if event in ("runner_started", "heartbeat", "sim_started", "sim_progress"):
        return "online"
    if event == "runner_idle":
        return "idle"
    return None


async def _singleton_writable(db: AsyncSession, machine_name: Optional[str]) -> bool:
    """The id=1 row is the legacy single-machine view.

    No name (the original runner) may write it. The first named machine claims
    it. A different machine must not overwrite it.
    """
    if not machine_name:
        return True
    result = await db.execute(select(CfdRunnerState).where(CfdRunnerState.id == 1))
    runner = result.scalar_one_or_none()
    if runner is None or not runner.machine_name:
        return True
    return runner.machine_name == machine_name


async def _upsert_runner(
    db: AsyncSession,
    status: str,
    pending_files: Optional[List[str]] = None,
    machine_name: Optional[str] = None,
) -> None:
    result = await db.execute(select(CfdRunnerState).where(CfdRunnerState.id == 1))
    runner = result.scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if runner is None:
        runner = CfdRunnerState(
            id=1,
            status=status,
            pending_files=pending_files,
            machine_name=machine_name,
            last_heartbeat=now,
        )
        db.add(runner)
    else:
        runner.status = status
        if pending_files is not None:
            runner.pending_files = pending_files
        if machine_name is not None:
            runner.machine_name = machine_name
        runner.last_heartbeat = now
    await db.flush()


async def _update_runner_heartbeat(db: AsyncSession) -> None:
    result = await db.execute(select(CfdRunnerState).where(CfdRunnerState.id == 1))
    runner = result.scalar_one_or_none()
    if runner is not None:
        runner.last_heartbeat = datetime.now(timezone.utc)
        await db.flush()


async def _machine_by_name(db: AsyncSession, name: str) -> Optional[Machine]:
    result = await db.execute(select(Machine).where(Machine.name == name))
    return result.scalar_one_or_none()


async def _touch_machine(
    db: AsyncSession,
    name: Optional[str],
    now: datetime,
    status: Optional[str],
) -> Optional[Machine]:
    if not name:
        return None
    machine = await _machine_by_name(db, name)
    if machine is None:
        machine = Machine(
            id=uuid.uuid4(),
            name=name,
            target_type="local",
            status=status or "online",
            last_heartbeat_at=now,
        )
        db.add(machine)
    else:
        if status is not None:
            machine.status = status
        machine.last_heartbeat_at = now
    await db.flush()
    return machine


async def _resolve_run(
    db: AsyncSession, data: Dict[str, Any], machine: Optional[Machine]
) -> Optional[Run]:
    run_id = _parse_uuid(data.get("run_id"))
    if data.get("run_id"):
        if run_id is None:
            return None
        result = await db.execute(select(Run).where(Run.id == run_id))
        return result.scalar_one_or_none()
    case_name = data.get("case_name") or data.get("name")
    if not case_name:
        return None
    stmt = select(Run).where(Run.case_name == case_name)
    if machine is not None:
        stmt = stmt.where(Run.machine_id == machine.id)
    stmt = stmt.order_by(Run.created_at.desc())
    runs = (await db.execute(stmt)).scalars().all()
    for preferred in ("running", "queued"):
        for run in runs:
            if run.status == preferred:
                return run
    return runs[0] if runs else None


async def _apply_run_event(
    db: AsyncSession,
    event: str,
    data: Dict[str, Any],
    machine: Optional[Machine],
    now: datetime,
) -> Optional[Run]:
    run = await _resolve_run(db, data, machine)
    if run is None or event in _NO_RUN_STATUS_CHANGE:
        return run
    if event == "sim_started":
        run.status = "running"
        if run.started_at is None:
            run.started_at = now
        end_time = _first_present(data, "end_time", "t_end")
        if end_time is not None:
            run.end_time = end_time
    elif event == "sim_stopped":
        if run.status in ("queued", "running"):
            run.status = "stopped"
            run.ended_at = now
    elif event == "sim_progress":
        run.status = "running"
        progress = _first_present(data, "progress_pct", "progress")
        if progress is not None:
            run.progress_pct = progress
        sim_time = _first_present(data, "sim_time")
        if sim_time is not None:
            run.sim_time = sim_time
        end_time = _first_present(data, "end_time", "t_end")
        if end_time is not None:
            run.end_time = end_time
    elif event == "sim_completed":
        run.status = "completed"
        run.ended_at = now
        if data.get("results_link"):
            run.results_link = data["results_link"]
        sim_time = _first_present(data, "sim_time")
        if sim_time is not None:
            run.sim_time = sim_time
        progress = _first_present(data, "progress_pct", "progress")
        if progress is not None:
            run.progress_pct = progress
    elif event == "sim_error":
        run.status = "failed"
        run.ended_at = now
        run.error = data.get("error") or data.get("error_msg") or ""
    await db.flush()
    return run


async def _add_event(
    db: AsyncSession,
    *,
    event_type: str,
    message: Optional[str],
    payload: Optional[dict],
    run: Optional[Run] = None,
    machine: Optional[Machine] = None,
) -> None:
    db.add(
        RunEvent(
            id=uuid.uuid4(),
            run_id=run.id if run is not None else None,
            machine_id=machine.id if machine is not None else None,
            event_type=event_type,
            message=message,
            payload=payload,
            created_at=datetime.now(timezone.utc),
        )
    )
    await db.flush()


async def _apply_legacy(db: AsyncSession, event: str, data: Dict[str, Any], now: datetime) -> None:
    machine_name = data.get("machine_name")
    if event == "runner_started":
        pending = data.get("pending_files", [])
        await _upsert_runner(
            db, status="online", pending_files=pending, machine_name=machine_name
        )
        for filename in pending:
            result = await db.execute(
                select(CfdSimulation).where(CfdSimulation.name == filename)
            )
            if result.scalar_one_or_none() is None:
                db.add(CfdSimulation(name=filename, status="queued"))
    elif event == "heartbeat":
        await _upsert_runner(db, status="online", machine_name=machine_name)
    elif event == "sim_started":
        name = data.get("name", "")
        result = await db.execute(select(CfdSimulation).where(CfdSimulation.name == name))
        sim = result.scalar_one_or_none()
        if sim is None:
            db.add(
                CfdSimulation(
                    name=name,
                    status="running",
                    meshes=data.get("meshes"),
                    t_end=data.get("t_end"),
                    machine_name=machine_name,
                    started_at=now,
                )
            )
        else:
            sim.status = "running"
            sim.meshes = data.get("meshes")
            sim.t_end = data.get("t_end")
            sim.machine_name = machine_name
            sim.started_at = now
        await _update_runner_heartbeat(db)
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
    elif event == "sim_completed":
        name = data.get("name", "")
        result = await db.execute(select(CfdSimulation).where(CfdSimulation.name == name))
        sim = result.scalar_one_or_none()
        if sim is not None:
            sim.status = "completed"
            sim.completed_at = now
        await _update_runner_heartbeat(db)
    elif event == "sim_error":
        name = data.get("name", "")
        result = await db.execute(select(CfdSimulation).where(CfdSimulation.name == name))
        sim = result.scalar_one_or_none()
        if sim is not None:
            sim.status = "error"
            sim.error_msg = data.get("error_msg", "")
        await _update_runner_heartbeat(db)
    elif event == "sim_stopped":
        name = data.get("name", "")
        if name:
            result = await db.execute(
                select(CfdSimulation).where(CfdSimulation.name == name)
            )
            sim = result.scalar_one_or_none()
            if sim is not None and sim.status == "running":
                sim.status = "stopped"
        await _update_runner_heartbeat(db)
    elif event == "runner_idle":
        await _upsert_runner(db, status="idle", pending_files=[], machine_name=machine_name)


async def _get_run(db: AsyncSession, run_id: str) -> Optional[Run]:
    parsed = _parse_uuid(run_id)
    if parsed is None:
        return None
    result = await db.execute(select(Run).where(Run.id == parsed))
    return result.scalar_one_or_none()


async def _machine_for_run(db: AsyncSession, run: Run) -> Optional[Machine]:
    if run.machine_id is None:
        return None
    result = await db.execute(select(Machine).where(Machine.id == run.machine_id))
    return result.scalar_one_or_none()


def _run_dict(run: Run, machine_name: Optional[str], events: Optional[list] = None) -> dict:
    payload = {
        "id": str(run.id),
        "target": run.target,
        "machine_id": str(run.machine_id) if run.machine_id else None,
        "machine_name": machine_name,
        "case_name": run.case_name,
        "input_file_ref": run.input_file_ref,
        "status": run.status,
        "progress_pct": run.progress_pct,
        "sim_time": run.sim_time,
        "end_time": run.end_time,
        "started_at": _iso(run.started_at),
        "ended_at": _iso(run.ended_at),
        "error": run.error,
        "results_link": run.results_link,
        "cost_estimate": run.cost_estimate,
        "cost_actual": run.cost_actual,
        "cost_currency": run.cost_currency,
        "created_by": run.created_by,
        "external_id": run.external_id,
        "created_at": _iso(run.created_at),
    }
    if events is not None:
        payload["events"] = events
    return payload


def _event_dict(event: RunEvent) -> dict:
    return {
        "id": str(event.id),
        "run_id": str(event.run_id) if event.run_id else None,
        "machine_id": str(event.machine_id) if event.machine_id else None,
        "event_type": event.event_type,
        "message": event.message,
        "payload": event.payload,
        "created_at": _iso(event.created_at),
    }


def _command_dict(cmd: RunCommand) -> dict:
    return {
        "id": str(cmd.id),
        "machine_id": str(cmd.machine_id),
        "run_id": str(cmd.run_id) if cmd.run_id else None,
        "command": cmd.command,
        "payload": cmd.payload,
        "status": cmd.status,
        "created_at": _iso(cmd.created_at),
        "picked_up_at": _iso(cmd.picked_up_at),
    }


async def _recent_events(db: AsyncSession, run_id) -> list:
    result = await db.execute(
        select(RunEvent)
        .where(RunEvent.run_id == run_id)
        .order_by(RunEvent.created_at.desc())
        .limit(100)
    )
    return [_event_dict(event) for event in reversed(result.scalars().all())]


async def _queue_command(
    db: AsyncSession, run: Run, command: str, payload: dict
) -> RunCommand:
    existing = await db.execute(
        select(RunCommand).where(
            RunCommand.run_id == run.id,
            RunCommand.command == command,
            RunCommand.status == "pending",
        )
    )
    cmd = existing.scalar_one_or_none()
    if cmd is not None:
        return cmd
    cmd = RunCommand(
        id=uuid.uuid4(),
        machine_id=run.machine_id,
        run_id=run.id,
        command=command,
        payload=payload,
        status="pending",
        created_at=datetime.now(timezone.utc),
    )
    db.add(cmd)
    await db.flush()
    machine = await _machine_for_run(db, run)
    await _add_event(
        db,
        event_type="command_queued",
        message=f"{command} queued",
        payload=payload,
        run=run,
        machine=machine,
    )
    return cmd


def _reject_cloud(machine_or_target: str) -> None:
    if machine_or_target == "cloudhpc" and not CLOUDHPC_ENABLED:
        raise HTTPException(status_code=400, detail="CloudHPC is disabled")


@router.post("/status")
async def post_status(
    body: StatusUpdate,
    db: AsyncSession = Depends(get_db),
):
    event = body.event
    if event not in _RUN_EVENTS:
        raise HTTPException(status_code=400, detail=f"Unknown event: {event}")
    data = _merged_data(body)
    now = datetime.now(timezone.utc)
    machine_name = data.get("machine_name")
    legacy = await _singleton_writable(db, machine_name)
    # The old dashboard keys simulations by file name. A phase-1 event that
    # only carries run_id still updates that row for the machine that owns it.
    if legacy and not data.get("name") and data.get("run_id"):
        linked = await _resolve_run(db, data, None)
        if linked is not None and linked.case_name:
            data["name"] = linked.case_name
            data.setdefault("case_name", linked.case_name)
    if legacy:
        await _apply_legacy(db, event, data, now)
    machine = await _touch_machine(
        db, machine_name, now, _machine_status_for_event(event)
    )
    run = await _apply_run_event(db, event, data, machine, now)
    await _add_event(
        db,
        event_type=event,
        message=data.get("message") or data.get("error") or data.get("error_msg"),
        payload=data,
        run=run,
        machine=machine,
    )
    await db.commit()
    return {"ok": True}


def _sim_to_dict(sim: CfdSimulation) -> dict:
    return {
        "id": sim.id,
        "name": sim.name,
        "status": sim.status,
        "meshes": sim.meshes,
        "t_end": sim.t_end,
        "progress_pct": sim.progress_pct,
        "started_at": sim.started_at.isoformat() if sim.started_at else None,
        "completed_at": sim.completed_at.isoformat() if sim.completed_at else None,
        "error_msg": sim.error_msg,
        "machine_name": sim.machine_name,
        "updated_at": sim.updated_at.isoformat() if sim.updated_at else None,
    }


@router.get("/state")
async def get_state(db: AsyncSession = Depends(get_db)):
    now = datetime.now(timezone.utc)

    result = await db.execute(select(CfdRunnerState).where(CfdRunnerState.id == 1))
    runner_row = result.scalar_one_or_none()
    if runner_row is None:
        runner_info = {"status": "offline", "last_heartbeat": None, "machine_name": None}
    else:
        heartbeat = as_utc(runner_row.last_heartbeat)
        runner_info = {
            "status": effective_machine_status(runner_row.status, heartbeat, now),
            "last_heartbeat": heartbeat.isoformat() if heartbeat else None,
            "machine_name": runner_row.machine_name,
        }

    result = await db.execute(
        select(CfdSimulation)
        .where(CfdSimulation.status == "running")
        .order_by(CfdSimulation.started_at.desc())
        .limit(1)
    )
    current_sim = result.scalar_one_or_none()

    result = await db.execute(
        select(CfdSimulation).where(CfdSimulation.status == "queued")
    )
    queue = result.scalars().all()

    result = await db.execute(
        select(CfdSimulation)
        .where(CfdSimulation.status == "completed")
        .order_by(CfdSimulation.completed_at.desc())
        .limit(20)
    )
    completed = result.scalars().all()

    result = await db.execute(
        select(CfdSimulation)
        .where(CfdSimulation.status == "error")
        .order_by(CfdSimulation.updated_at.desc())
        .limit(10)
    )
    errors = result.scalars().all()

    return {
        "runner": runner_info,
        "current": _sim_to_dict(current_sim) if current_sim else None,
        "queue": [_sim_to_dict(sim) for sim in queue],
        "completed": [_sim_to_dict(sim) for sim in completed],
        "errors": [_sim_to_dict(sim) for sim in errors],
    }


@router.get("/machines")
async def list_machines(db: AsyncSession = Depends(get_db)):
    now = datetime.now(timezone.utc)
    result = await db.execute(select(Machine).order_by(Machine.name.asc()))
    machines = []
    for machine in result.scalars().all():
        machines.append(
            {
                "id": str(machine.id),
                "name": machine.name,
                "target_type": machine.target_type,
                "status": effective_machine_status(
                    machine.status, machine.last_heartbeat_at, now
                ),
                "last_heartbeat_at": _iso(machine.last_heartbeat_at),
            }
        )
    return {"machines": machines}


@router.get("/runs")
async def list_runs(
    target: Optional[str] = None,
    machine_id: Optional[str] = None,
    status: Optional[str] = None,
    q: Optional[str] = None,
    user: Optional[str] = None,
    created_by: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    if q and q.strip():
        logger.info(
            "modelling_run_search query=%s user=%s timestamp=%s",
            q.strip(),
            _search_user(user, created_by),
            datetime.now(timezone.utc).isoformat(),
        )
    stmt = select(Run)
    if target:
        stmt = stmt.where(Run.target == target)
    if status:
        stmt = stmt.where(Run.status == status)
    if machine_id:
        parsed = _parse_uuid(machine_id)
        if parsed is None:
            raise HTTPException(status_code=400, detail="machine_id must be a uuid")
        stmt = stmt.where(Run.machine_id == parsed)
    if q and q.strip():
        pattern = _like_pattern(q.strip())
        stmt = stmt.where(
            or_(
                Run.case_name.ilike(pattern, escape="\\"),
                Run.input_file_ref.ilike(pattern, escape="\\"),
            )
        )
    stmt = stmt.order_by(Run.created_at.desc())
    runs = (await db.execute(stmt)).scalars().all()
    names = await _machine_names(db, runs)
    return {"runs": [_run_dict(run, names.get(run.machine_id)) for run in runs]}


@router.get("/runs/{run_id}")
async def get_run(
    run_id: str,
    from_search: Optional[str] = Query(None, alias="from"),
    q: Optional[str] = None,
    user: Optional[str] = None,
    created_by: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    run = await _get_run(db, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Unknown run")
    if from_search == "search":
        logger.info(
            "modelling_run_search_open query=%s user=%s timestamp=%s run_id=%s",
            (q or "").strip(),
            _search_user(user, created_by),
            datetime.now(timezone.utc).isoformat(),
            str(run.id),
        )
    machine = await _machine_for_run(db, run)
    events = await _recent_events(db, run.id)
    return _run_dict(run, machine.name if machine else None, events)


@router.post("/runs")
async def create_run(body: RunCreate, db: AsyncSession = Depends(get_db)):
    case_name = body.case_name.strip()
    input_file_ref = body.input_file_ref.strip()
    if not case_name or not input_file_ref:
        raise HTTPException(
            status_code=400, detail="case_name and input_file_ref are required"
        )
    machine = await _machine_for_create(db, body.machine_id, body.machine_name)
    _reject_cloud(machine.target_type)
    now = datetime.now(timezone.utc)
    run = Run(
        id=uuid.uuid4(),
        target=machine.target_type,
        machine_id=machine.id,
        case_name=case_name,
        input_file_ref=input_file_ref,
        status="queued",
        created_by=(body.created_by or "").strip() or None,
        created_at=now,
    )
    db.add(run)
    await db.flush()
    payload = {
        "run_id": str(run.id),
        "case_name": run.case_name,
        "input_file_ref": run.input_file_ref,
    }
    command = await _queue_command(db, run, "submit", payload)
    await db.commit()
    result = _run_dict(run, machine.name)
    result["command_id"] = str(command.id)
    return result


@router.post("/runs/{run_id}/stop")
async def stop_run(run_id: str, db: AsyncSession = Depends(get_db)):
    run = await _require_local_run(db, run_id)
    payload = {"run_id": str(run.id), "case_name": run.case_name}
    command = await _queue_command(db, run, "stop", payload)
    await db.commit()
    return {"ok": True, "command_id": str(command.id), "command": "stop"}


@router.post("/runs/{run_id}/restart")
async def restart_run(run_id: str, db: AsyncSession = Depends(get_db)):
    run = await _require_local_run(db, run_id)
    if run.status == "queued":
        raise HTTPException(
            status_code=400,
            detail=(
                "Restart needs an FDS .restart file or DT_RESTART; "
                "this run has not started"
            ),
        )
    payload = {"run_id": str(run.id), "case_name": run.case_name}
    command = await _queue_command(db, run, "restart", payload)
    await db.commit()
    return {"ok": True, "command_id": str(command.id), "command": "restart"}


@router.get("/commands")
async def poll_commands(
    machine_name: str,
    db: AsyncSession = Depends(get_db),
):
    machine = await _machine_by_name(db, machine_name)
    if machine is None:
        return {"commands": []}
    result = await db.execute(
        select(RunCommand)
        .where(RunCommand.machine_id == machine.id, RunCommand.status == "pending")
        .order_by(RunCommand.created_at.asc())
    )
    now = datetime.now(timezone.utc)
    commands = []
    for cmd in result.scalars().all():
        cmd.status = "acked"
        cmd.picked_up_at = now
        commands.append(_command_dict(cmd))
    await db.commit()
    return {"commands": commands}


@router.post("/commands/{command_id}/ack")
async def ack_command(
    command_id: str,
    body: CommandAck,
    db: AsyncSession = Depends(get_db),
):
    if body.status not in ("done", "failed"):
        raise HTTPException(status_code=400, detail="status must be done or failed")
    parsed = _parse_uuid(command_id)
    cmd = None
    if parsed is not None:
        result = await db.execute(select(RunCommand).where(RunCommand.id == parsed))
        cmd = result.scalar_one_or_none()
    if cmd is None:
        raise HTTPException(status_code=404, detail="Unknown command")
    now = datetime.now(timezone.utc)
    cmd.status = body.status
    if cmd.picked_up_at is None:
        cmd.picked_up_at = now
    if body.error:
        payload = dict(cmd.payload or {})
        payload["error"] = body.error
        cmd.payload = payload
    run = None
    if cmd.run_id is not None:
        result = await db.execute(select(Run).where(Run.id == cmd.run_id))
        run = result.scalar_one_or_none()
    if run is not None:
        if body.status == "done" and cmd.command == "submit" and run.status == "queued":
            # The runner acks submit when FDS starts, not when the sim finishes.
            run.status = "running"
            if run.started_at is None:
                run.started_at = now
        elif body.status == "done" and cmd.command == "stop" and run.status in (
            "queued",
            "running",
        ):
            # sim_stopped is the explicit event. Ack done covers a stop that
            # never gets a follow-up event.
            run.status = "stopped"
            run.ended_at = now
        elif body.status == "done" and cmd.command == "restart":
            # Same row. The runner's sim_started also sets running.
            run.status = "running"
            run.ended_at = None
            run.error = None
        elif body.status == "failed":
            # A restart with no .restart file is acked failed and does not
            # send sim_error. Keep the run's previous status and store the text.
            run.error = body.error or "Command failed"
    machine = None
    if cmd.machine_id is not None:
        result = await db.execute(select(Machine).where(Machine.id == cmd.machine_id))
        machine = result.scalar_one_or_none()
    message = body.error if body.status == "failed" else f"{cmd.command} {body.status}"
    await _add_event(
        db,
        event_type="command_ack",
        message=message,
        payload={"command_id": str(cmd.id), "status": body.status, "error": body.error},
        run=run,
        machine=machine,
    )
    await db.commit()
    return {
        "ok": True,
        "id": str(cmd.id),
        "status": cmd.status,
        "error": body.error,
    }


async def _machine_names(db: AsyncSession, runs: list) -> dict:
    ids = {run.machine_id for run in runs if run.machine_id is not None}
    if not ids:
        return {}
    result = await db.execute(select(Machine).where(Machine.id.in_(ids)))
    return {machine.id: machine.name for machine in result.scalars().all()}


async def _machine_for_create(
    db: AsyncSession, machine_id: Optional[str], machine_name: Optional[str]
) -> Machine:
    if not machine_id and not (machine_name and machine_name.strip()):
        raise HTTPException(
            status_code=400, detail="machine_id or machine_name is required"
        )
    machine = None
    if machine_id:
        parsed = _parse_uuid(machine_id)
        if parsed is None:
            raise HTTPException(status_code=404, detail="Unknown machine")
        result = await db.execute(select(Machine).where(Machine.id == parsed))
        machine = result.scalar_one_or_none()
        if machine is None:
            raise HTTPException(status_code=404, detail="Unknown machine")
        if machine_name and machine_name.strip() and machine.name != machine_name.strip():
            raise HTTPException(
                status_code=400, detail="machine_id and machine_name do not match"
            )
        return machine
    found = await _machine_by_name(db, machine_name.strip())
    if found is None:
        raise HTTPException(status_code=404, detail="Unknown machine")
    return found


async def _require_local_run(db: AsyncSession, run_id: str) -> Run:
    run = await _get_run(db, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Unknown run")
    _reject_cloud(run.target)
    if run.machine_id is None:
        raise HTTPException(status_code=400, detail="Run has no machine")
    return run


def _parse_since(raw: Optional[str]) -> Optional[int]:
    if raw is None or not str(raw).strip():
        return None
    try:
        return int(str(raw).strip())
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail="since must be an integer cursor"
        ) from exc


def _parse_device_ids(raw: str) -> List[str]:
    chosen: List[str] = []
    seen = set()
    for part in raw.split(","):
        column_id = part.strip()
        if not column_id or column_id in seen:
            continue
        seen.add(column_id)
        chosen.append(column_id)
    return chosen


async def _require_run(db: AsyncSession, run_id: str) -> Run:
    run = await _get_run(db, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Unknown run")
    return run


@router.post("/series")
async def push_series(body: SeriesPush, db: AsyncSession = Depends(get_db)):
    """Runner push. 2xx only after the rows commit, so the file cursor can move."""
    run = await _require_run(db, body.run_id)
    try:
        await store_series(
            db,
            run.id,
            [(point.t, point.hrr) for point in body.hrr],
            [
                (column.id, column.quantity, column.unit)
                for column in body.devc_columns
            ],
            [(point.t, dict(point.values)) for point in body.devc],
        )
    except SeriesRejected as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    selected = await get_devc_selection(db, run.id)
    await db.commit()
    return {"selected_devc": selected}


@router.get("/runs/{run_id}/series")
async def get_series(
    run_id: str,
    since: Optional[str] = None,
    devices: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Page poll. since is the previous cursor. devices is the selection.

    An empty devices list returns the column catalog and no DEVC samples,
    and clears the selection the runner is told on its next push.
    """
    run = await _require_run(db, run_id)
    parsed_since = _parse_since(since)
    if devices is not None:
        try:
            device_ids = await set_devc_selection(
                db, run.id, _parse_device_ids(devices)
            )
        except SeriesRejected as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        await db.commit()
    else:
        device_ids = await get_devc_selection(db, run.id)
    return await read_series(db, run.id, parsed_since, device_ids)
