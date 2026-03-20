from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# --- Projects ---

class ProjectCreate(BaseModel):
    name: str
    settings: dict[str, Any] = {}
    created_by: Optional[str] = None


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    settings: Optional[dict[str, Any]] = None


class ProjectSummary(BaseModel):
    id: uuid.UUID
    name: str
    created_by: Optional[str] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ProjectDetail(ProjectSummary):
    settings: dict[str, Any] = {}
    created_at: Optional[datetime] = None
    floors: list[FloorSummary] = []

    model_config = {"from_attributes": True}


# --- Floors ---

class FloorCreate(BaseModel):
    floor_number: int
    name: Optional[str] = None
    canvas_dimensions: Optional[dict[str, Any]] = None
    pixels_per_mesh: float = 1.0
    origin_pixels: Optional[dict[str, Any]] = None
    settings: dict[str, Any] = {}


class FloorUpdate(BaseModel):
    name: Optional[str] = None
    floor_number: Optional[int] = None
    canvas_dimensions: Optional[dict[str, Any]] = None
    pixels_per_mesh: Optional[float] = None
    origin_pixels: Optional[dict[str, Any]] = None
    settings: Optional[dict[str, Any]] = None


class FloorSummary(BaseModel):
    id: uuid.UUID
    floor_number: int
    name: Optional[str] = None
    pdf_s3_key: Optional[str] = None

    model_config = {"from_attributes": True}


class FloorDetail(FloorSummary):
    canvas_dimensions: Optional[dict[str, Any]] = None
    pixels_per_mesh: float = 1.0
    origin_pixels: Optional[dict[str, Any]] = None
    settings: dict[str, Any] = {}
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    elements: list[ElementOut] = []

    model_config = {"from_attributes": True}


# --- Elements ---

class PointSchema(BaseModel):
    x: float
    y: float


class ElementIn(BaseModel):
    element_index: int
    type: str
    points: list[PointSchema]
    comments: Optional[str] = None


class ElementOut(ElementIn):
    id: uuid.UUID

    model_config = {"from_attributes": True}


# --- Bulk save ---

class FloorSavePayload(BaseModel):
    """One floor's worth of data for the bulk-save endpoint."""
    floor_number: int
    name: Optional[str] = None
    canvas_dimensions: Optional[dict[str, Any]] = None
    pixels_per_mesh: float = 1.0
    origin_pixels: Optional[dict[str, Any]] = None
    settings: dict[str, Any] = {}
    elements: list[ElementIn] = []


class ProjectSavePayload(BaseModel):
    """Full project save: settings + all floors + all elements in one shot."""
    name: Optional[str] = None
    settings: dict[str, Any] = {}
    floors: list[FloorSavePayload] = []


# Rebuild forward refs
ProjectDetail.model_rebuild()
FloorDetail.model_rebuild()
