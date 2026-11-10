"""SQLAlchemy models for CFD simulation monitoring dashboard."""

import uuid

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Text,
    Uuid,
)
from sqlalchemy import JSON as JSONB

from database import Base
from models.db_models import utcnow


class CfdSimulation(Base):
    __tablename__ = "cfd_simulations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(Text, nullable=False)
    status = Column(Text, nullable=False)  # queued/running/completed/error
    meshes = Column(Integer, nullable=True)
    t_end = Column(Float, nullable=True)
    progress_pct = Column(Float, default=0)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    error_msg = Column(Text, nullable=True)
    machine_name = Column(Text, nullable=True)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class CfdRunnerState(Base):
    __tablename__ = "cfd_runner_state"

    id = Column(Integer, primary_key=True, default=1)
    status = Column(Text, nullable=False, default="offline")
    pending_files = Column(JSONB, nullable=True)
    machine_name = Column(Text, nullable=True)
    last_heartbeat = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint("id = 1", name="singleton_runner_state"),
    )


class Machine(Base):
    """One office PC or, later, a CloudHPC target. Name is unique so a second
    runner cannot overwrite the first."""

    __tablename__ = "machines"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    name = Column(Text, nullable=False, unique=True)
    target_type = Column(Text, nullable=False, default="local")
    last_heartbeat_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(Text, nullable=False, default="offline")

    __table_args__ = (
        CheckConstraint(
            "target_type IN ('local', 'cloudhpc')", name="ck_machines_target_type"
        ),
        CheckConstraint(
            "status IN ('online', 'idle', 'offline')", name="ck_machines_status"
        ),
    )


class Run(Base):
    """One FDS attempt. Restart stays on this row. external_id and the cost
    columns are unused until CloudHPC (phase 2)."""

    __tablename__ = "runs"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    target = Column(Text, nullable=False, default="local")
    machine_id = Column(
        Uuid, ForeignKey("machines.id", ondelete="SET NULL"), nullable=True, index=True
    )
    case_name = Column(Text, nullable=False)
    input_file_ref = Column(Text, nullable=False)
    status = Column(Text, nullable=False, default="queued")
    progress_pct = Column(Float, nullable=True)
    sim_time = Column(Float, nullable=True)
    end_time = Column(Float, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    ended_at = Column(DateTime(timezone=True), nullable=True)
    error = Column(Text, nullable=True)
    results_link = Column(Text, nullable=True)
    cost_estimate = Column(Float, nullable=True)
    cost_actual = Column(Float, nullable=True)
    cost_currency = Column(Text, nullable=True)
    created_by = Column(Text, nullable=True)
    external_id = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        CheckConstraint("target IN ('local', 'cloudhpc')", name="ck_runs_target"),
        CheckConstraint(
            "status IN ('queued', 'running', 'stopped', 'failed', 'completed')",
            name="ck_runs_status",
        ),
    )


class RunEvent(Base):
    """Log tail for a run or a machine. run_id and machine_id are nullable so a
    heartbeat can be stored before a run exists."""

    __tablename__ = "run_events"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    run_id = Column(
        Uuid, ForeignKey("runs.id", ondelete="CASCADE"), nullable=True, index=True
    )
    machine_id = Column(
        Uuid, ForeignKey("machines.id", ondelete="SET NULL"), nullable=True, index=True
    )
    event_type = Column(Text, nullable=False)
    message = Column(Text, nullable=True)
    payload = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)


class RunCommand(Base):
    """Per-machine queue. The runner polls pending rows; nothing dials the PC."""

    __tablename__ = "run_commands"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    machine_id = Column(
        Uuid, ForeignKey("machines.id", ondelete="CASCADE"), nullable=False, index=True
    )
    run_id = Column(
        Uuid, ForeignKey("runs.id", ondelete="CASCADE"), nullable=True, index=True
    )
    command = Column(Text, nullable=False)
    payload = Column(JSONB, nullable=True)
    status = Column(Text, nullable=False, default="pending")
    created_at = Column(DateTime(timezone=True), default=utcnow)
    picked_up_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "command IN ('submit', 'stop', 'restart')", name="ck_run_commands_command"
        ),
        CheckConstraint(
            "status IN ('pending', 'acked', 'done', 'failed')",
            name="ck_run_commands_status",
        ),
    )
