import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy import JSON as JSONB  # renders as JSONB on Postgres, JSON on SQLite
from sqlalchemy.orm import relationship

from database import Base


def utcnow():
    return datetime.now(timezone.utc)


class Project(Base):
    __tablename__ = "projects"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    name = Column(Text, nullable=False)
    # Which canvas mode owns this project (fdsGen / timeEq / ...). Each mode
    # has its own dashboard; a project is only ever opened by the mode that
    # created it, because the settings/floor payloads are mode-specific.
    # Existing Railway DBs are healed on boot by _ensure_projects_mode_column
    # (create_all will not ALTER a table that already exists).
    mode = Column(
        Text, nullable=False, default="fdsGen", server_default="fdsGen", index=True
    )
    settings = Column(JSONB, default=dict)
    created_by = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    floors = relationship("Floor", back_populates="project", cascade="all, delete-orphan")


class Floor(Base):
    __tablename__ = "floors"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id = Column(Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    floor_number = Column(Integer, nullable=False)
    name = Column(Text, nullable=True)
    pdf_s3_key = Column(Text, nullable=True)
    canvas_dimensions = Column(JSONB, nullable=True)
    pixels_per_mesh = Column(Float, default=1.0)
    origin_pixels = Column(JSONB, nullable=True)
    settings = Column(JSONB, default=dict)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    project = relationship("Project", back_populates="floors")
    elements = relationship("Element", back_populates="floor", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("project_id", "floor_number", name="uq_project_floor"),
    )


class MacsRun(Base):
    """A MACS+ run record linked to an upload-canvas project.

    Stores the full run history, inputs, and client provenance. Handoffs start
    with project_id=None until claimed by an upload-canvas project.
    """

    __tablename__ = "macs_runs"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id = Column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True
    )
    schema_ = Column("schema", Text, nullable=False, default="fd-macs-reliability/1")
    inputs = Column(JSONB, nullable=False, default=dict)
    outputs = Column(JSONB, nullable=False, default=dict)
    checks = Column(JSONB, nullable=False, default=list)
    time_series = Column(JSONB, nullable=False, default=list)
    section = Column(Text, nullable=False)
    exposure = Column(Text, nullable=False)
    critical_temp = Column(Float, nullable=False)
    section_factor = Column(Float, nullable=False)
    governing_side = Column(Text, nullable=False)
    windows_user = Column(Text, nullable=False)
    machine_name = Column(Text, nullable=True)
    client_timestamp = Column(DateTime(timezone=True), nullable=False)
    client_version = Column(Text, nullable=True)
    run_id = Column(Text, nullable=True)
    label = Column(Text, nullable=True)
    imacs_job_id = Column(Text, nullable=True, index=True)
    received_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)


MacsResult = MacsRun


class MacsHandoff(Base):
    """Temporary handoff container for runs created before a project exists."""

    __tablename__ = "macs_handoffs"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    run_id = Column(
        Uuid, ForeignKey("macs_runs.id", ondelete="CASCADE"), nullable=False
    )
    imacs_job_id = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    claimed_at = Column(DateTime(timezone=True), nullable=True)
    claimed_project_id = Column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=True
    )

    run = relationship("MacsRun")


class ImacsJobLink(Base):
    """Mapping between a client-generated imacs_job_id and an upload-canvas project_id."""

    __tablename__ = "imacs_job_links"

    imacs_job_id = Column(Text, primary_key=True)
    project_id = Column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    project = relationship("Project")


class FeeTextBlock(Base):
    __tablename__ = "fee_text_block"

    key = Column(Text, primary_key=True)
    default_content = Column(Text, nullable=False)  # immutable, written once at seed
    content = Column(Text, nullable=False)           # editable live value
    kind = Column(Text, nullable=False)              # paragraph | bullet_list | template
    label = Column(Text, nullable=False, default="")
    group_name = Column(Text, nullable=False, default="")  # 'group' is a SQL reserved word
    sort_order = Column(Integer, nullable=False, default=0)
    placeholders = Column(JSONB, default=list)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    updated_by = Column(Text, nullable=True)


class FeeTextBlockHistory(Base):
    __tablename__ = "fee_text_block_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(Text, ForeignKey("fee_text_block.key"), nullable=False)
    content = Column(Text, nullable=False)
    edited_by = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow)


class Element(Base):
    __tablename__ = "elements"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    floor_id = Column(Uuid, ForeignKey("floors.id", ondelete="CASCADE"), nullable=False)
    element_index = Column(Integer, nullable=False)
    type = Column(Text, nullable=False)
    points = Column(JSONB, nullable=False)
    comments = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    floor = relationship("Floor", back_populates="elements")
