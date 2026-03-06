"""External Fire Spread API endpoints."""

from fastapi import APIRouter, HTTPException

from models.efs_models import EfsRequest, EfsResponse, ElevationResult
from services.efs_calculator import run_efs_calcs

router = APIRouter()


@router.post("/calculate", response_model=EfsResponse)
async def calculate_efs(data: EfsRequest):
    """Run BRE 135 external fire spread calculations."""
    try:
        height_list = [e.height for e in data.elevations]
        width_list = [e.width for e in data.elevations]
        boundary_dist_list = [e.boundary_distance for e in data.elevations]
        has_suppression_list = [e.has_suppression for e in data.elevations]

        results = run_efs_calcs(
            height_list=height_list,
            width_list=width_list,
            boundary_dist_list=boundary_dist_list,
            has_suppression_list=has_suppression_list,
            is_commercial=data.is_commercial,
        )

        return EfsResponse(
            elevations=[ElevationResult(**r) for r in results]
        )
    except Exception as e:
        print(f"Error calculating EFS: {e}")
        raise HTTPException(status_code=500, detail=f"Calculation failed: {str(e)}")
