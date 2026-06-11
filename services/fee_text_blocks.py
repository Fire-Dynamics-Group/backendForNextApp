"""Registry derivation + idempotent seeding for editable fee-proposal text blocks.

The narrative text lives in ``services/fee_text_templates.py`` as Python
constants. This module derives a registry of editable blocks from that module
(rather than hand-maintaining a parallel list) and seeds them into the
``fee_text_block`` table. The constants file stays the seed-only source of
truth + fallback; the DB owns the editable text once seeded.
"""
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.db_models import FeeTextBlock
from services import fee_text_templates as txt

# Constants that are not user-editable narrative text.
EXCLUDE = {"OFFICE_ADDRESS", "HOURLY_RATES"}

_PLACEHOLDER_RE = re.compile(r"\{(\w+)\}")

# Prefix -> human group label, checked in order (first match wins).
_GROUP_RULES = [
    ("INTRO_", "Introductions"),
    ("STAGE_1", "RIBA Stage 1"),
    ("STAGE_2", "RIBA Stage 2"),
    ("STAGE_3", "RIBA Stage 3"),
    ("STAGE_4", "RIBA Stage 4"),
    ("LONDON_PLAN", "London Plan & Gateway"),
    ("GATEWAY", "London Plan & Gateway"),
    ("COMMON_CORRIDOR", "CFD Modelling"),
    ("OPEN_PLAN", "CFD Modelling"),
    ("WAREHOUSE_CFD", "CFD Modelling"),
    ("STRUCTURAL_FE", "Structural Fire Engineering"),
    ("WAREHOUSE_STRUCTURAL", "Structural Fire Engineering"),
    ("PEER_REVIEW", "Peer Review"),
    ("CONSTRUCTION_ADVICE", "RIBA Stage 5 Services"),
    ("SITE_VISITS", "RIBA Stage 5 Services"),
    ("PHASED_OCCUPATION", "RIBA Stage 5 Services"),
    ("CFSMP", "RIBA Stage 5 Services"),
    ("CONSTRUCTION_RA", "RIBA Stage 5 Services"),
    ("CLIENT_MONITORING", "RIBA Stage 5 Services"),
    ("REG38", "RIBA Stage 6 Services"),
    ("EWS1", "RIBA Stage 6 Services"),
    ("COMPLETION_RA", "RIBA Stage 6 Services"),
    ("TERMS_", "Terms of Business"),
    ("EXCL", "Exclusions"),
]


def _is_str_list(value):
    return isinstance(value, (list, tuple)) and all(isinstance(x, str) for x in value)


def _classify(value):
    """Return (kind, content) for a constant, or (None, None) if not narrative."""
    if _is_str_list(value):
        return "bullet_list", "\n".join(value)
    if isinstance(value, str):
        return ("template" if _PLACEHOLDER_RE.search(value) else "paragraph"), value
    return None, None


def _label_for(key: str) -> str:
    return key.replace("_", " ").title()


def _group_for(key: str) -> str:
    for prefix, group in _GROUP_RULES:
        if key.startswith(prefix):
            return group
    return "Other"


def get_seed_blocks():
    """Derive the editable text blocks from the constants module, in source order."""
    blocks = []
    order = 0
    for name, value in vars(txt).items():
        if name.startswith("_") or not name.isupper() or name in EXCLUDE:
            continue
        kind, content = _classify(value)
        if kind is None:
            continue
        blocks.append({
            "key": name,
            "kind": kind,
            "default_content": content,
            "content": content,
            "placeholders": sorted(set(_PLACEHOLDER_RE.findall(content))),
            "label": _label_for(name),
            "group_name": _group_for(name),
            "sort_order": order,
        })
        order += 1
    return blocks


def token_errors(placeholders, content: str):
    """Validate an edited block's tokens against its allow-list.

    Returns a list of human-readable error strings (empty == valid). The token
    set must match exactly: unknown tokens are rejected, and a token present in
    the allow-list (i.e. the original default) may not be removed.
    """
    found = set(_PLACEHOLDER_RE.findall(content or ""))
    allowed = set(placeholders or [])
    errors = []
    unknown = found - allowed
    if unknown:
        errors.append("Unknown placeholder(s): " + ", ".join("{" + t + "}" for t in sorted(unknown)))
    missing = allowed - found
    if missing:
        errors.append("Missing required placeholder(s): " + ", ".join("{" + t + "}" for t in sorted(missing)))
    return errors


def _to_native(kind: str, content: str):
    """Convert stored/override string content into the shape the renderer wants."""
    if kind == "bullet_list":
        return [line.strip() for line in content.split("\n") if line.strip()]
    return content


def build_text_map(blocks, overrides=None):
    """Resolve the text the renderer should use, precedence override > DB > constant.

    ``blocks`` is an iterable of ``(key, kind, content)`` (the rows present in the
    DB). ``overrides`` is an optional ``{key: raw_string}`` for a single proposal.
    Missing keys fall back to the module constant (native shape preserved), so
    generation never breaks on an absent row.
    """
    seed = get_seed_blocks()
    kinds = {b["key"]: b["kind"] for b in seed}
    resolved = {key: getattr(txt, key) for key in kinds}  # constant fallback (native)

    for key, kind, content in blocks:
        resolved[key] = _to_native(kind, content)
        kinds[key] = kind

    for key, content in (overrides or {}).items():
        resolved[key] = _to_native(kinds.get(key, "paragraph"), content)

    return resolved


async def seed_fee_text_blocks(session: AsyncSession) -> int:
    """Idempotently insert any missing blocks. Returns the number inserted.

    Existing rows are never modified, so user-edited content survives re-seeds
    and brand-new constants self-heal on the next run.
    """
    existing = set((await session.execute(select(FeeTextBlock.key))).scalars().all())
    inserted = 0
    for block in get_seed_blocks():
        if block["key"] in existing:
            continue
        session.add(FeeTextBlock(**block))
        inserted += 1
    await session.commit()
    return inserted
