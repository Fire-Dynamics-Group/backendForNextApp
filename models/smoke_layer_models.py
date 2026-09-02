"""Warehouse smoke layer models.

The zone model itself runs in the browser (fd-toolstation, lib/smoke-layer-calc.ts).
Nothing here recomputes it: the report endpoint is handed the results that were on
screen and only formats them, so the document and the charts the engineer signed off
cannot disagree.

Wire format is camelCase to match the TypeScript types; Python attributes stay
snake_case via the alias generator.
"""

import uuid
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel
from sqlalchemy import Column, DateTime, Text, UniqueConstraint, Uuid
from sqlalchemy import JSON as JSONB

from database import Base
from models.db_models import utcnow


# --------------------------------------------------------------------------
# Request / response models
# --------------------------------------------------------------------------


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class SmokeLayerInputs(CamelModel):
    """The inputs the model was run with."""

    room_area: float
    racking_perc: float
    room_height: float
    fgr: float

    detection_time: float
    pre_movement_time: float
    maximum_travel_distance: float
    walking_speed: float
    total_exit_width: float
    flow_rate: float
    occupancy: float

    assessment_time: float
    reference_height: float
    tstep: float


class SmokeLayerStep(CamelModel):
    """One timestep of the computed results."""

    time: float
    hrr: float
    convective_hrr: float
    smoke_layer_temp: float
    added_smoke_temp: float
    clear_height: float
    depth_change: float
    velocity: float
    escaped: float


class SmokeLayerResults(CamelModel):
    steps: List[SmokeLayerStep]
    rset: float
    aset: float
    aset_triggered: bool
    margin_of_safety: float
    reference_height_breached: bool
    breach_time: Optional[float] = None
    final_clear_height: float
    total_pre_evac: float
    people_per_second: float
    queue_time: float


class SmokeLayerReportDetails(BaseModel):
    """Report wording inputs that are not part of the calculation.

    Empty strings / None mean "not known": the report then uses the conservative
    wording and, where the engineer must write something, a highlighted prompt.
    """

    client_name: str = ""
    project_location: str = ""
    building_name: str = ""
    site_description: str = ""
    intended_purpose: str = ""  # e.g. "storage and distribution purposes"; empty = fit-out unknown

    racking_known: bool = False
    racking_source: str = ""  # e.g. "indicative fit-out drawing in Appendix A"
    occupancy_known: bool = False
    occupancy_source: str = ""  # e.g. "the Fire Strategy Report supplied by Michael Sparks Associates"
    occupancy_reference: str = ""  # full reference-list entry for [2]
    has_undercroft: bool = False

    office_storeys: Optional[int] = None
    office_height: str = ""  # e.g. "8.5m"
    staircases: Optional[int] = None

    number_of_doors: Optional[int] = None
    door_width_mm: Optional[float] = None


class SmokeLayerReportRequest(BaseModel):
    project_name: str = ""
    engineer_name: str = ""
    inputs: SmokeLayerInputs
    results: SmokeLayerResults
    details: Optional[SmokeLayerReportDetails] = None


class SavedRunCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    project_name: str = ""
    inputs: SmokeLayerInputs


class SavedRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    project_name: Optional[str]
    inputs: SmokeLayerInputs
    created_at: object
    updated_at: object


# --------------------------------------------------------------------------
# Persistence
# --------------------------------------------------------------------------


class SmokeLayerRun(Base):
    """A named set of inputs an engineer saved to come back to."""

    __tablename__ = "smoke_layer_runs"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    name = Column(Text, nullable=False)
    project_name = Column(Text, nullable=True)
    inputs = Column(JSONB, nullable=False)
    created_by = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    # Saving under an existing name replaces that run rather than creating a duplicate.
    __table_args__ = (UniqueConstraint("name", name="uq_smoke_layer_run_name"),)
