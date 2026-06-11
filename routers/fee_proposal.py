"""Fee Proposal API endpoints."""

import json
import os
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.db_models import FeeTextBlock, FeeTextBlockHistory
from models.fee_proposal_models import FeeProposalRequest, EngineerResponse
from services.fee_document_service import generate_proposal, get_proposal_filename, rendered_block_keys
from services.fee_text_blocks import build_text_map, token_errors

router = APIRouter()


class TextBlockOut(BaseModel):
    key: str
    label: str
    kind: str
    group_name: str
    sort_order: int
    content: str
    placeholders: List[str] = []
    updated_by: Optional[str] = None


class TextBlockEdit(BaseModel):
    content: str
    edited_by: str


class ActorOnly(BaseModel):
    edited_by: str


class HistoryOut(BaseModel):
    id: int
    content: str
    edited_by: str
    created_at: Optional[datetime] = None


def _block_out(b: FeeTextBlock) -> TextBlockOut:
    return TextBlockOut(
        key=b.key, label=b.label, kind=b.kind, group_name=b.group_name,
        sort_order=b.sort_order, content=b.content,
        placeholders=b.placeholders or [], updated_by=b.updated_by,
    )

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGINEERS_PATH = os.path.join(BASE_DIR, "data", "engineers.json")


async def _load_text_map(data: FeeProposalRequest):
    """Resolve the text map from the DB (override > DB > constant). Falls back to
    None (pure-constant generation) when no database is configured/reachable."""
    import database

    overrides = getattr(data, "text_overrides", None) or None

    if database.async_session is None:
        # No DB: still apply per-proposal overrides on top of the constants.
        return build_text_map([], overrides=overrides) if overrides else None
    try:
        from models.db_models import FeeTextBlock

        async with database.async_session() as session:
            rows = (await session.execute(select(FeeTextBlock))).scalars().all()
        return build_text_map([(r.key, r.kind, r.content) for r in rows], overrides=overrides)
    except Exception as e:  # noqa: BLE001 — never fail generation over text loading
        print(f"Warning: failed to load fee text blocks, using constants: {e}")
        return build_text_map([], overrides=overrides) if overrides else None


@router.get("/engineers", response_model=List[EngineerResponse])
async def get_engineers():
    """Return list of engineers for the frontend dropdown."""
    try:
        with open(ENGINEERS_PATH, "r", encoding="utf-8") as f:
            engineers = json.load(f)
        return engineers
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="Engineers data file not found")


@router.post("/applicable-text-blocks", response_model=List[str])
async def applicable_text_blocks(data: FeeProposalRequest):
    """Dry run: which text-block keys this proposal would actually render.

    The frontend uses this to show override fields only for blocks that will
    appear, instead of duplicating the renderer's conditional logic. The
    engineer doesn't affect which narrative blocks render, so a missing/invalid
    engineer is tolerated by substituting any known engineer for the dry run.
    """
    try:
        return sorted(rendered_block_keys(data))
    except ValueError:
        try:
            with open(ENGINEERS_PATH, "r", encoding="utf-8") as f:
                engineers = json.load(f)
            if engineers:
                probe = data.model_copy(deep=True)
                probe.fee_options.engineer_name = engineers[0]["full_name"]
                return sorted(rendered_block_keys(probe))
        except Exception as e:  # noqa: BLE001
            print(f"Warning: applicable-text-blocks dry run failed: {e}")
        return []


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


# --- Manage Proposal Text (editable defaults) ---


async def _require_block(db: AsyncSession, key: str) -> FeeTextBlock:
    block = await db.get(FeeTextBlock, key)
    if block is None:
        raise HTTPException(status_code=404, detail=f"Text block '{key}' not found")
    return block


def _require_actor(edited_by: str) -> str:
    actor = (edited_by or "").strip()
    if not actor:
        raise HTTPException(status_code=400, detail="edited_by is required")
    return actor


async def _set_content(db: AsyncSession, block: FeeTextBlock, content: str, edited_by: str):
    """Write new content and append a history snapshot (only on actual change)."""
    if content != block.content:
        block.content = content
        block.updated_by = edited_by
        db.add(FeeTextBlockHistory(key=block.key, content=content, edited_by=edited_by))
    await db.commit()


@router.get("/text-blocks", response_model=List[TextBlockOut])
async def list_text_blocks(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(FeeTextBlock).order_by(FeeTextBlock.sort_order))).scalars().all()
    return [_block_out(b) for b in rows]


@router.put("/text-blocks/{key}", response_model=TextBlockOut)
async def update_text_block(key: str, body: TextBlockEdit, db: AsyncSession = Depends(get_db)):
    block = await _require_block(db, key)
    actor = _require_actor(body.edited_by)
    errors = token_errors(block.placeholders or [], body.content)
    if errors:
        raise HTTPException(status_code=400, detail="; ".join(errors))
    await _set_content(db, block, body.content, actor)
    return _block_out(block)


@router.post("/text-blocks/{key}/reset", response_model=TextBlockOut)
async def reset_text_block(key: str, body: ActorOnly, db: AsyncSession = Depends(get_db)):
    block = await _require_block(db, key)
    actor = _require_actor(body.edited_by)
    await _set_content(db, block, block.default_content, actor)
    return _block_out(block)


@router.get("/text-blocks/{key}/history", response_model=List[HistoryOut])
async def text_block_history(key: str, db: AsyncSession = Depends(get_db)):
    await _require_block(db, key)
    rows = (await db.execute(
        select(FeeTextBlockHistory)
        .where(FeeTextBlockHistory.key == key)
        .order_by(FeeTextBlockHistory.id.desc())
    )).scalars().all()
    return [HistoryOut(id=r.id, content=r.content, edited_by=r.edited_by, created_at=r.created_at) for r in rows]


@router.post("/text-blocks/{key}/restore/{history_id}", response_model=TextBlockOut)
async def restore_text_block(key: str, history_id: int, body: ActorOnly, db: AsyncSession = Depends(get_db)):
    block = await _require_block(db, key)
    actor = _require_actor(body.edited_by)
    snapshot = await db.get(FeeTextBlockHistory, history_id)
    if snapshot is None or snapshot.key != key:
        raise HTTPException(status_code=404, detail="History entry not found for this block")
    await _set_content(db, block, snapshot.content, actor)
    return _block_out(block)
