"""External Fire Spread API endpoints."""

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from models.efs_models import EfsRequest, EfsResponse, ElevationResult
from services.efs_calculator import run_efs_calcs
from services.efs_report_service import generate_efs_report

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


@router.post("/report")
async def generate_efs_report_endpoint(data: EfsRequest):
    """Generate an EFS Word report and return as download."""
    try:
        height_list = [e.height for e in data.elevations]
        width_list = [e.width for e in data.elevations]
        boundary_dist_list = [e.boundary_distance for e in data.elevations]
        has_suppression_list = [e.has_suppression for e in data.elevations]

        doc_bytes = generate_efs_report(
            height_list=height_list,
            width_list=width_list,
            boundary_dist_list=boundary_dist_list,
            has_suppression_list=has_suppression_list,
            is_commercial=data.is_commercial,
        )

        response = StreamingResponse(
            doc_bytes,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        response.headers["Content-Disposition"] = 'attachment; filename="EFS_Report.docx"'
        return response
    except Exception as e:
        print(f"Error generating EFS report: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to generate report: {str(e)}"
        )
