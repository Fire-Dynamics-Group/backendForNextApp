"""Fee proposal for the Word add-in task pane (fd-toolstation app/addin/word).

Deliberately self-contained (fee generator + python-docx only) so it can ship to master
ahead of the rest of the Word add-in backend (routers/word_addin.py).
"""
from io import BytesIO
import json
import tempfile
from pathlib import Path

from docx import Document
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import database
from models.db_models import FeeProposalGeneration, FeeTextBlock, FeeTextBlockHistory
from models.fee_proposal_models import FeeProposalRequest
from services.fee_document_service import generate_proposal
from services.fee_generation_log import FeeGenerationContext, record_fee_generation
from services.fee_text_blocks import WORD_ADDIN_PREFIX, build_text_map, get_word_addin_seed_blocks, token_errors

router = APIRouter()
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
LOCAL_WORD_STORE = Path(tempfile.gettempdir()) / "fd-toolstation-word-addin-text-blocks.json"


class WordTextBlockOut(BaseModel):
    key: str
    label: str
    kind: str
    group_name: str
    sort_order: int
    content: str
    placeholders: List[str] = []
    updated_by: Optional[str] = None


class WordTextBlockEdit(BaseModel):
    content: str
    edited_by: str


class WordActorOnly(BaseModel):
    edited_by: str


class WordHistoryOut(BaseModel):
    id: int
    content: str
    edited_by: str
    created_at: Optional[datetime] = None


def _word_block_out(block: FeeTextBlock) -> WordTextBlockOut:
    return WordTextBlockOut(
        key=block.key[len(WORD_ADDIN_PREFIX):], label=block.label, kind=block.kind,
        group_name=block.group_name, sort_order=block.sort_order, content=block.content,
        placeholders=block.placeholders or [], updated_by=block.updated_by,
    )


def _local_store():
    """Use a per-machine JSON store for offline/local development without Postgres."""
    if LOCAL_WORD_STORE.exists():
        store = json.loads(LOCAL_WORD_STORE.read_text(encoding="utf-8"))
    else:
        store = {"blocks": {}, "history": {}, "next_id": 1}

    changed = False
    for seed in get_word_addin_seed_blocks():
        if seed["key"] not in store["blocks"]:
            store["blocks"][seed["key"]] = seed
            changed = True
    if changed or not LOCAL_WORD_STORE.exists():
        _save_local_store(store)
    return store


def _save_local_store(store):
    temp_path = LOCAL_WORD_STORE.with_suffix(".tmp")
    temp_path.write_text(json.dumps(store, indent=2), encoding="utf-8")
    temp_path.replace(LOCAL_WORD_STORE)


def _local_require_block(store, key: str):
    block = store["blocks"].get(key)
    if block is None:
        raise HTTPException(status_code=404, detail=f"Word add-in text block '{key}' not found")
    return block


def _local_block_out(block) -> WordTextBlockOut:
    return WordTextBlockOut(
        key=block["key"], label=block["label"], kind=block["kind"],
        group_name=block["group_name"], sort_order=block["sort_order"], content=block["content"],
        placeholders=block["placeholders"], updated_by=block.get("updated_by"),
    )


def _local_set_content(store, block, content: str, actor: str):
    if content != block["content"]:
        block["content"] = content
        block["updated_by"] = actor
        store["history"].setdefault(block["key"], []).insert(0, {
            "id": store["next_id"], "content": content, "edited_by": actor,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        store["next_id"] += 1
        _save_local_store(store)


async def _word_require_block(db: AsyncSession, key: str) -> FeeTextBlock:
    block = await db.get(FeeTextBlock, WORD_ADDIN_PREFIX + key)
    if block is None:
        raise HTTPException(status_code=404, detail=f"Word add-in text block '{key}' not found")
    return block


def _word_require_actor(edited_by: str) -> str:
    actor = (edited_by or "").strip()
    if not actor:
        raise HTTPException(status_code=400, detail="edited_by is required")
    return actor


async def _word_set_content(db: AsyncSession, block: FeeTextBlock, content: str, actor: str):
    if content != block.content:
        block.content = content
        block.updated_by = actor
        db.add(FeeTextBlockHistory(key=block.key, content=content, edited_by=actor))
    await db.commit()


async def _load_word_text_map():
    """Load Word add-in wording separately from the web proposal wording."""
    if database.async_session is None:
        store = _local_store()
        return build_text_map([
            (key, block["kind"], block["content"])
            for key, block in store["blocks"].items()
        ])
    try:
        async with database.async_session() as session:
            rows = (await session.execute(
                select(FeeTextBlock).where(FeeTextBlock.key.like(f"{WORD_ADDIN_PREFIX}%"))
            )).scalars().all()
        if not rows:
            return None
        return build_text_map([
            (row.key[len(WORD_ADDIN_PREFIX):], row.kind, row.content) for row in rows
        ])
    except Exception as exc:  # noqa: BLE001 — wording storage must not block document generation
        print(f"Warning: failed to load Word add-in fee text blocks: {exc}")
        return None


@router.get("/fee-proposal/text-blocks", response_model=List[WordTextBlockOut])
async def list_word_text_blocks():
    if database.async_session is None:
        store = _local_store()
        blocks = sorted(store["blocks"].values(), key=lambda block: block["sort_order"])
        return [_local_block_out(block) for block in blocks]
    async with database.async_session() as db:
        rows = (await db.execute(
            select(FeeTextBlock)
            .where(FeeTextBlock.key.like(f"{WORD_ADDIN_PREFIX}%"))
            .order_by(FeeTextBlock.sort_order)
        )).scalars().all()
        return [_word_block_out(row) for row in rows]


@router.put("/fee-proposal/text-blocks/{key}", response_model=WordTextBlockOut)
async def update_word_text_block(key: str, body: WordTextBlockEdit):
    actor = _word_require_actor(body.edited_by)
    if database.async_session is None:
        store = _local_store()
        block = _local_require_block(store, key)
        errors = token_errors(block["placeholders"] or [], body.content)
        if errors:
            raise HTTPException(status_code=400, detail="; ".join(errors))
        _local_set_content(store, block, body.content, actor)
        return _local_block_out(block)
    async with database.async_session() as db:
        block = await _word_require_block(db, key)
        errors = token_errors(block.placeholders or [], body.content)
        if errors:
            raise HTTPException(status_code=400, detail="; ".join(errors))
        await _word_set_content(db, block, body.content, actor)
        return _word_block_out(block)


@router.post("/fee-proposal/text-blocks/{key}/reset", response_model=WordTextBlockOut)
async def reset_word_text_block(key: str, body: WordActorOnly):
    actor = _word_require_actor(body.edited_by)
    if database.async_session is None:
        store = _local_store()
        block = _local_require_block(store, key)
        _local_set_content(store, block, block["default_content"], actor)
        return _local_block_out(block)
    async with database.async_session() as db:
        block = await _word_require_block(db, key)
        await _word_set_content(db, block, block.default_content, actor)
        return _word_block_out(block)


@router.get("/fee-proposal/text-blocks/{key}/history", response_model=List[WordHistoryOut])
async def word_text_block_history(key: str):
    if database.async_session is None:
        store = _local_store()
        _local_require_block(store, key)
        return [WordHistoryOut(**entry) for entry in store["history"].get(key, [])]
    async with database.async_session() as db:
        block = await _word_require_block(db, key)
        rows = (await db.execute(
            select(FeeTextBlockHistory).where(FeeTextBlockHistory.key == block.key)
            .order_by(FeeTextBlockHistory.id.desc())
        )).scalars().all()
        return [WordHistoryOut(id=row.id, content=row.content, edited_by=row.edited_by, created_at=row.created_at) for row in rows]


@router.post("/fee-proposal/text-blocks/{key}/restore/{history_id}", response_model=WordTextBlockOut)
async def restore_word_text_block(key: str, history_id: int, body: WordActorOnly):
    actor = _word_require_actor(body.edited_by)
    if database.async_session is None:
        store = _local_store()
        block = _local_require_block(store, key)
        snapshot = next((entry for entry in store["history"].get(key, []) if entry["id"] == history_id), None)
        if snapshot is None:
            raise HTTPException(status_code=404, detail="History entry not found for this block")
        _local_set_content(store, block, snapshot["content"], actor)
        return _local_block_out(block)
    async with database.async_session() as db:
        block = await _word_require_block(db, key)
        snapshot = await db.get(FeeTextBlockHistory, history_id)
        if snapshot is None or snapshot.key != block.key:
            raise HTTPException(status_code=404, detail="History entry not found for this block")
        await _word_set_content(db, block, snapshot.content, actor)
        return _word_block_out(block)


class WordFeeProposalRequest(FeeProposalRequest):
    generation_context: Optional[FeeGenerationContext] = None


class FeeGenerationOut(BaseModel):
    id: str
    created_at: Optional[datetime] = None
    source: str
    user_email: Optional[str] = None
    user_name: Optional[str] = None
    engineer_name: Optional[str] = None
    is_test: bool
    synergy_project_ref: Optional[str] = None
    synergy_project_label: Optional[str] = None
    project_name: Optional[str] = None
    client_company_name: Optional[str] = None
    has_missing_or_edited: bool
    missing_from_synergy: List[str] = []
    user_filled_missing: List[str] = []
    inputs: Dict[str, Any] = {}
    synergy_context: Optional[Dict[str, Any]] = None


@router.post("/fee-proposal/render")
async def render_fee_proposal(data: WordFeeProposalRequest, request: Request):
    """The letter as a docx fragment for insertFileFromBase64.

    Word merges an inserted file's last paragraph into the paragraph it lands in, taking
    that paragraph's style, so a sacrificial empty paragraph is appended to absorb it.
    createDocument (the "New document" path) is unaffected by the extra paragraph.
    """
    try:
        texts = await _load_word_text_map()
        doc = Document(generate_proposal(data, texts))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await record_fee_generation(
        data,
        source="word_addin",
        ctx=data.generation_context,
        forwarded_user_email=request.headers.get("x-forwarded-user"),
    )
    doc.add_paragraph("")
    out = BytesIO()
    doc.save(out)
    return Response(content=out.getvalue(), media_type=DOCX)


@router.get("/fee-proposal/generations", response_model=List[FeeGenerationOut])
async def list_fee_proposal_generations(
    include_tests: bool = False,
    only_with_gaps: bool = False,
    synergy_project_ref: Optional[str] = None,
    limit: int = Query(50, ge=1, le=500),
):
    """List recorded fee proposal generations for reviewing missing/edited Synergy details."""
    if database.async_session is None:
        return []
    stmt = select(FeeProposalGeneration).order_by(FeeProposalGeneration.created_at.desc()).limit(limit)
    if not include_tests:
        stmt = stmt.where(FeeProposalGeneration.is_test.is_(False))
    if only_with_gaps:
        stmt = stmt.where(FeeProposalGeneration.has_missing_or_edited.is_(True))
    if synergy_project_ref:
        stmt = stmt.where(FeeProposalGeneration.synergy_project_ref == synergy_project_ref)
    async with database.async_session() as db:
        rows = (await db.execute(stmt)).scalars().all()
    out: List[FeeGenerationOut] = []
    for row in rows:
        ctx = row.synergy_context if isinstance(row.synergy_context, dict) else {}
        out.append(
            FeeGenerationOut(
                id=str(row.id),
                created_at=row.created_at,
                source=row.source,
                user_email=row.user_email,
                user_name=row.user_name,
                engineer_name=row.engineer_name,
                is_test=bool(row.is_test),
                synergy_project_ref=row.synergy_project_ref,
                synergy_project_label=row.synergy_project_label,
                project_name=row.project_name,
                client_company_name=row.client_company_name,
                has_missing_or_edited=bool(row.has_missing_or_edited),
                missing_from_synergy=list(ctx.get("missing_from_synergy") or []),
                user_filled_missing=list(ctx.get("user_filled_missing") or []),
                inputs=row.inputs or {},
                synergy_context=row.synergy_context,
            )
        )
    return out
