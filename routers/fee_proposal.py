"""Fee Proposal API endpoints."""

import json
import os
from typing import List

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from models.fee_proposal_models import FeeProposalRequest, EngineerResponse
from services.fee_document_service import generate_proposal, get_proposal_filename

router = APIRouter()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGINEERS_PATH = os.path.join(BASE_DIR, "data", "engineers.json")


@router.get("/engineers", response_model=List[EngineerResponse])
async def get_engineers():
    """Return list of engineers for the frontend dropdown."""
    try:
        with open(ENGINEERS_PATH, "r", encoding="utf-8") as f:
            engineers = json.load(f)
        return engineers
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="Engineers data file not found")


@router.post("/generate")
async def generate_fee_proposal(data: FeeProposalRequest):
    """Generate a fee proposal Word document and return as download."""
    try:
        doc_bytes = generate_proposal(data)
        filename = get_proposal_filename(data)

        response = StreamingResponse(
            doc_bytes,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        print(f"Error generating proposal: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to generate proposal: {str(e)}"
        )
