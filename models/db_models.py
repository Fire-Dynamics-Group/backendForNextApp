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
