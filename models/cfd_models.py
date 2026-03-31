"""SQLAlchemy models for CFD simulation monitoring dashboard."""

from sqlalchemy import CheckConstraint, Column, DateTime, Float, Integer, Text
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
