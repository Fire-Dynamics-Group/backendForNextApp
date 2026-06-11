"""Fee Proposal API endpoints."""

import json
import os
from typing import List

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from sqlalchemy import select

from models.fee_proposal_models import FeeProposalRequest, EngineerResponse
from services.fee_document_service import generate_proposal, get_proposal_filename
from services.fee_text_blocks import build_text_map

router = APIRouter()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGINEERS_PATH = os.path.join(BASE_DIR, "data", "engineers.json")


async def _load_text_map(data: FeeProposalRequest):
    """Resolve the text map from the DB (override > DB > constant). Falls back to
    None (pure-constant generation) when no database is configured/reachable."""
    import database

    if database.async_session is None:
        return None
    try:
        from models.db_models import FeeTextBlock

        async with database.async_session() as session:
            rows = (await session.execute(select(FeeTextBlock))).scalars().all()
        overrides = getattr(data, "text_overrides", None)
        return build_text_map([(r.key, r.kind, r.content) for r in rows], overrides=overrides)
    except Exception as e:  # noqa: BLE001 — never fail generation over text loading
        print(f"Warning: failed to load fee text blocks, using constants: {e}")
        return None


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
        texts = await _load_text_map(data)
        doc_bytes = generate_proposal(data, texts)
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
