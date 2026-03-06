from pydantic import BaseModel
from typing import List


class Elevation(BaseModel):
    boundary_distance: float
    height: float
    width: float
    has_suppression: bool = False


class EfsRequest(BaseModel):
    elevations: List[Elevation]
    is_commercial: bool = True


class ElevationResult(BaseModel):
    elevation_number: int
    boundary_distance: str
    er_height: str
    er_width: str
    bre_height: str
    bre_width: str
    bre_percentage: str
    allowable_area: str
    actual_area: str
    actual_protected_area: str
    actual_percentage: str


class EfsResponse(BaseModel):
    elevations: List[ElevationResult]
