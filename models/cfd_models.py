"""SQLAlchemy models for CFD simulation monitoring dashboard."""

import uuid

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
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


class RunSeriesColumn(Base):
    """DEVC catalog for one run: id, quantity, and unit. Not the samples."""

    __tablename__ = "run_series_columns"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    run_id = Column(
        Uuid, ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind = Column(Text, nullable=False)
    column_id = Column(Text, nullable=False)
    quantity = Column(Text, nullable=True)
    unit = Column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "run_id", "kind", "column_id", name="uq_run_series_column"
        ),
        CheckConstraint(
            "kind IN ('hrr', 'devc')", name="ck_run_series_columns_kind"
        ),
    )


class RunSeriesPoint(Base):
    """One sample of HRR or of one DEVC column. seq is never reused."""

    __tablename__ = "run_series_points"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    run_id = Column(
        Uuid, ForeignKey("runs.id", ondelete="CASCADE"), nullable=False
    )
    kind = Column(Text, nullable=False)
    column_id = Column(Text, nullable=False)
    t = Column(Float, nullable=False)
    value = Column(Float, nullable=False)
    seq = Column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "run_id", "kind", "column_id", "t", name="uq_run_series_point_t"
        ),
        CheckConstraint("kind IN ('hrr', 'devc')", name="ck_run_series_points_kind"),
        Index("ix_run_series_points_cursor", "run_id", "kind", "seq"),
        Index("ix_run_series_points_column", "run_id", "kind", "column_id"),
    )


class RunSeriesCounter(Base):
    """One high-water seq per run, shared by HRR and DEVC. Never reused."""

    __tablename__ = "run_series_counters"

    run_id = Column(
        Uuid, ForeignKey("runs.id", ondelete="CASCADE"), primary_key=True
    )
    last_seq = Column(Integer, nullable=False, default=0)


class RunHrrDesign(Base):
    """Design HRR curve for one run. Points stay {t, hrr}, as the runner sent them."""

    __tablename__ = "run_hrr_designs"

    run_id = Column(
        Uuid, ForeignKey("runs.id", ondelete="CASCADE"), primary_key=True
    )
    points = Column(JSONB, nullable=False)


class RunDevcSelection(Base):
    """Columns the page asked the runner to sample, in picker order."""

    __tablename__ = "run_devc_selections"

    run_id = Column(
        Uuid, ForeignKey("runs.id", ondelete="CASCADE"), primary_key=True
    )
    column_id = Column(Text, primary_key=True)
    position = Column(Integer, nullable=False)
