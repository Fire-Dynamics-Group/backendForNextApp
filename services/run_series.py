"""Per-run HRR and DEVC series for the live charts.

The runner pushes POST /cfd-dashboard/series and reads selected_devc.
The page polls GET /runs/{id}/series?since=&devices=.

Stored caps match the runner: SERIES_MIN_DT is 1 second and
SERIES_MAX_POINTS is 60. A new sample closer than 1s to one already
stored is dropped. Past 60 points the series is thinned and still keeps
the first and last sample, so a long run does not lose t=0.

With no selection a push stores at most MAX_DEFAULT_DEVC_COLUMNS (4).
The page's latest devices list is the selection, up to 12 ids. At most
that many columns keep samples; room for a newly selected column is made
by deleting samples of a column that is no longer selected. The catalog
stays.

Seq is one counter per run and is never reused. The GET cursor is the
newest seq included in that response, as a decimal string. Pass it back
as since. Omit since to load history, which is what the page does when
the selected device changes.
"""

from __future__ import annotations

import math
import uuid
from typing import Optional

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.cfd_models import (
    RunDevcSelection,
    RunSeriesColumn,
    RunSeriesCounter,
    RunSeriesPoint,
)

# Same numbers the runner uses before it pushes.
SERIES_MIN_DT = 1
SERIES_MAX_POINTS = 60
# Samples stored from a push when the page has not picked columns yet.
MAX_DEFAULT_DEVC_COLUMNS = 4
# The devices query. More than this is a 400, so a poll cannot pull 300 series.
MAX_SELECTED_DEVC_COLUMNS = 12
# Columns that may hold samples at once. Unselected samples are dropped
# only to make room for a column the page has selected.
MAX_DEVC_SAMPLE_COLUMNS = 12
# Catalog rows (id and quantity). A common-corridor file is a few hundred.
MAX_CATALOG_COLUMNS = 2000
HRR_UNIT = "kW"

HRR_COLUMN = "HRR"
KIND_HRR = "hrr"
KIND_DEVC = "devc"


class SeriesRejected(ValueError):
    """The push or the selection cannot be stored as sent."""


def _keep_time(t: float, known: list[float]) -> bool:
    """True for a new sample, or for a rewrite of a time already stored.

    A time within SERIES_MIN_DT of a stored sample is the same bin the
    runner would have skipped.
    """
    for prev in known:
        if prev == t:
            return True
        if abs(t - prev) < SERIES_MIN_DT:
            return False
    return True


def kept_indexes(count: int, limit: int) -> list[int]:
    """Indexes to keep, including both ends, spread across the series."""
    if limit <= 0 or count <= 0:
        return []
    if count <= limit:
        return list(range(count))
    if limit == 1:
        return [count - 1]
    chosen: list[int] = []
    seen: set[int] = set()
    span = count - 1
    denom = limit - 1
    for i in range(limit):
        idx = (i * span + denom // 2) // denom
        if idx not in seen:
            seen.add(idx)
            chosen.append(idx)
    while len(chosen) < limit:
        chosen.sort()
        gap_at = max(
            range(len(chosen) - 1),
            key=lambda i: chosen[i + 1] - chosen[i],
        )
        insert_at = (chosen[gap_at] + chosen[gap_at + 1]) // 2
        if insert_at in seen or insert_at == chosen[gap_at]:
            break
        seen.add(insert_at)
        chosen.append(insert_at)
    chosen.sort()
    return chosen


def _clean_id(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _clean_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _require_finite(value: float, label: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise SeriesRejected(f"{label} must be a finite number")
    return number


def _sample_order(points: list[tuple[float, dict]]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for _t, values in points:
        for column_id in values:
            if column_id not in seen:
                seen.add(column_id)
                ordered.append(column_id)
    return ordered


def _payload_order(
    columns: list[tuple[str, Optional[str], Optional[str]]],
    points: list[tuple[float, dict]],
) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for column_id, _quantity, _unit in columns:
        if column_id not in seen:
            seen.add(column_id)
            ordered.append(column_id)
    for column_id in _sample_order(points):
        if column_id not in seen:
            seen.add(column_id)
            ordered.append(column_id)
    return ordered


def _candidate_columns(
    sample_ids: list[str],
    payload_order: list[str],
    selected: list[str],
) -> list[str]:
    sample_set = set(sample_ids)
    if selected:
        return [column_id for column_id in selected if column_id in sample_set]
    ordered = [column_id for column_id in payload_order if column_id in sample_set]
    return ordered[:MAX_DEFAULT_DEVC_COLUMNS]


def _fit_sample_budget(
    existing: list[str],
    candidates: list[str],
    selected: set[str],
) -> tuple[list[str], list[str]]:
    """Accept candidates that fit. Evict unselected samples only for a selection."""
    limit = MAX_DEVC_SAMPLE_COLUMNS
    keep = list(existing)
    accepted: list[str] = []
    to_delete: list[str] = []
    for column_id in candidates:
        if column_id in keep or column_id in accepted:
            accepted.append(column_id)
            continue
        if len(set(keep) | set(accepted) | {column_id}) <= limit:
            accepted.append(column_id)
            continue
        if column_id not in selected:
            continue
        while len(set(keep) | set(accepted) | {column_id}) > limit:
            victim = next(
                (
                    item
                    for item in keep
                    if item not in selected and item not in accepted
                ),
                None,
            )
            if victim is None:
                break
            keep.remove(victim)
            to_delete.append(victim)
        if len(set(keep) | set(accepted) | {column_id}) <= limit:
            accepted.append(column_id)
    return accepted, to_delete


async def _selection_ids(db: AsyncSession, run_id: uuid.UUID) -> list[str]:
    result = await db.execute(
        select(RunDevcSelection.column_id)
        .where(RunDevcSelection.run_id == run_id)
        .order_by(RunDevcSelection.position)
    )
    return list(result.scalars().all())


async def _next_seq(db: AsyncSession, run_id: uuid.UUID) -> int:
    result = await db.execute(
        select(RunSeriesCounter).where(RunSeriesCounter.run_id == run_id)
    )
    counter = result.scalar_one_or_none()
    if counter is None:
        counter = RunSeriesCounter(run_id=run_id, last_seq=0)
        db.add(counter)
        await db.flush()
    counter.last_seq = int(counter.last_seq) + 1
    return int(counter.last_seq)


async def _catalog_count(db: AsyncSession, run_id: uuid.UUID) -> int:
    result = await db.execute(
        select(func.count())
        .select_from(RunSeriesColumn)
        .where(RunSeriesColumn.run_id == run_id)
    )
    return int(result.scalar_one())


async def _upsert_columns(
    db: AsyncSession,
    run_id: uuid.UUID,
    columns: list[tuple[str, Optional[str], Optional[str]]],
) -> None:
    if not columns:
        return
    result = await db.execute(
        select(RunSeriesColumn).where(
            RunSeriesColumn.run_id == run_id,
            RunSeriesColumn.kind == KIND_DEVC,
        )
    )
    by_id = {row.column_id: row for row in result.scalars().all()}
    count = len(by_id)
    for column_id, quantity, unit in columns:
        row = by_id.get(column_id)
        if row is None:
            if count >= MAX_CATALOG_COLUMNS:
                continue
            row = RunSeriesColumn(
                id=uuid.uuid4(),
                run_id=run_id,
                kind=KIND_DEVC,
                column_id=column_id,
                quantity=quantity,
                unit=unit,
            )
            db.add(row)
            by_id[column_id] = row
            count += 1
            continue
        if quantity is not None:
            row.quantity = quantity
        if unit is not None:
            row.unit = unit
    await db.flush()


async def _load_points(
    db: AsyncSession,
    run_id: uuid.UUID,
    kind: str,
    column_ids: list[str],
) -> dict[tuple[str, float], RunSeriesPoint]:
    if not column_ids:
        return {}
    result = await db.execute(
        select(RunSeriesPoint).where(
            RunSeriesPoint.run_id == run_id,
            RunSeriesPoint.kind == kind,
            RunSeriesPoint.column_id.in_(column_ids),
        )
    )
    return {(row.column_id, row.t): row for row in result.scalars().all()}


async def _write_cell(
    db: AsyncSession,
    run_id: uuid.UUID,
    kind: str,
    column_id: str,
    t: float,
    value: float,
    existing: dict[tuple[str, float], RunSeriesPoint],
) -> None:
    key = (column_id, t)
    row = existing.get(key)
    if row is not None:
        row.value = value
        return
    row = RunSeriesPoint(
        id=uuid.uuid4(),
        run_id=run_id,
        kind=kind,
        column_id=column_id,
        t=t,
        value=value,
        seq=await _next_seq(db, run_id),
    )
    db.add(row)
    existing[key] = row


async def _downsample(
    db: AsyncSession, run_id: uuid.UUID, kind: str, column_id: str
) -> None:
    result = await db.execute(
        select(RunSeriesPoint)
        .where(
            RunSeriesPoint.run_id == run_id,
            RunSeriesPoint.kind == kind,
            RunSeriesPoint.column_id == column_id,
        )
        .order_by(RunSeriesPoint.t, RunSeriesPoint.seq)
    )
    points = list(result.scalars().all())
    keep = set(kept_indexes(len(points), SERIES_MAX_POINTS))
    if len(keep) == len(points):
        return
    for index, point in enumerate(points):
        if index not in keep:
            await db.delete(point)
    await db.flush()


async def _existing_sample_columns(
    db: AsyncSession, run_id: uuid.UUID
) -> list[str]:
    result = await db.execute(
        select(RunSeriesPoint.column_id, func.min(RunSeriesPoint.seq))
        .where(
            RunSeriesPoint.run_id == run_id,
            RunSeriesPoint.kind == KIND_DEVC,
        )
        .group_by(RunSeriesPoint.column_id)
        .order_by(func.min(RunSeriesPoint.seq))
    )
    return [row[0] for row in result.all()]


async def _delete_column_samples(
    db: AsyncSession, run_id: uuid.UUID, column_ids: list[str]
) -> None:
    if not column_ids:
        return
    await db.execute(
        delete(RunSeriesPoint).where(
            RunSeriesPoint.run_id == run_id,
            RunSeriesPoint.kind == KIND_DEVC,
            RunSeriesPoint.column_id.in_(column_ids),
        )
    )
    await db.flush()


def _normalize_columns(
    columns: list[tuple[str, Optional[str], Optional[str]]],
) -> list[tuple[str, Optional[str], Optional[str]]]:
    normalized: list[tuple[str, Optional[str], Optional[str]]] = []
    seen: set[str] = set()
    for raw_id, quantity, unit in columns:
        column_id = _clean_id(raw_id)
        if column_id is None or column_id in seen:
            continue
        seen.add(column_id)
        normalized.append((column_id, _clean_text(quantity), _clean_text(unit)))
    return normalized


def _normalize_points(
    points: list[tuple[float, dict]],
) -> list[tuple[float, dict[str, float]]]:
    normalized: list[tuple[float, dict[str, float]]] = []
    for raw_t, values in points:
        t = _require_finite(raw_t, "t")
        cleaned: dict[str, float] = {}
        for raw_id, raw_value in values.items():
            column_id = _clean_id(raw_id)
            if column_id is None or raw_value is None:
                continue
            cleaned[column_id] = _require_finite(raw_value, column_id)
        normalized.append((t, cleaned))
    return normalized


async def set_devc_selection(
    db: AsyncSession, run_id: uuid.UUID, ids: list[str]
) -> list[str]:
    chosen: list[str] = []
    seen: set[str] = set()
    for raw in ids:
        column_id = _clean_id(raw)
        if column_id is None:
            raise SeriesRejected("DEVC id is empty")
        if column_id not in seen:
            seen.add(column_id)
            chosen.append(column_id)
    if len(chosen) > MAX_SELECTED_DEVC_COLUMNS:
        raise SeriesRejected(
            f"Request at most {MAX_SELECTED_DEVC_COLUMNS} DEVC columns"
        )
    await db.execute(
        delete(RunDevcSelection).where(RunDevcSelection.run_id == run_id)
    )
    for position, column_id in enumerate(chosen):
        db.add(
            RunDevcSelection(
                run_id=run_id, column_id=column_id, position=position
            )
        )
    await db.flush()
    return chosen


async def get_devc_selection(db: AsyncSession, run_id: uuid.UUID) -> list[str]:
    return await _selection_ids(db, run_id)


async def store_series(
    db: AsyncSession,
    run_id: uuid.UUID,
    hrr: list[tuple[float, float]],
    devc_columns: list[tuple[str, Optional[str], Optional[str]]],
    devc: list[tuple[float, dict]],
) -> dict:
    hrr_stored = await _store_hrr(db, run_id, hrr)
    await _store_devc(db, run_id, devc_columns, devc)
    return hrr_stored


async def _store_hrr(
    db: AsyncSession, run_id: uuid.UUID, hrr: list[tuple[float, float]]
) -> int:
    if not hrr:
        return 0
    existing = await _load_points(db, run_id, KIND_HRR, [HRR_COLUMN])
    known = [row.t for row in existing.values()]
    stored = 0
    for raw_t, raw_value in hrr:
        t = _require_finite(raw_t, "t")
        value = _require_finite(raw_value, "hrr")
        if not _keep_time(t, known):
            continue
        await _write_cell(db, run_id, KIND_HRR, HRR_COLUMN, t, value, existing)
        if t not in known:
            known.append(t)
        stored += 1
    await db.flush()
    await _downsample(db, run_id, KIND_HRR, HRR_COLUMN)
    return stored


async def _store_devc(
    db: AsyncSession,
    run_id: uuid.UUID,
    devc_columns: list[tuple[str, Optional[str], Optional[str]]],
    devc: list[tuple[float, dict]],
) -> tuple[list[str], list[str], int]:
    columns = _normalize_columns(devc_columns)
    points = _normalize_points(devc)
    sample_ids = _sample_order(points)
    await _upsert_columns(db, run_id, columns)
    # Ids that arrived only as samples still belong in the picker.
    await _upsert_columns(
        db, run_id, [(column_id, None, None) for column_id in sample_ids]
    )
    selected = await _selection_ids(db, run_id)
    candidates = _candidate_columns(
        sample_ids, _payload_order(columns, points), selected
    )
    existing = await _existing_sample_columns(db, run_id)
    accepted, evict = _fit_sample_budget(existing, candidates, set(selected))
    await _delete_column_samples(db, run_id, evict)
    accepted_set = set(accepted)
    dropped = [column_id for column_id in sample_ids if column_id not in accepted_set]
    if not accepted:
        return [], dropped, 0
    existing_points = await _load_points(db, run_id, KIND_DEVC, accepted)
    known: dict[str, list[float]] = {}
    for column_id, t in existing_points:
        known.setdefault(column_id, []).append(t)
    stored = 0
    touched: list[str] = []
    touched_set: set[str] = set()
    for t, values in points:
        for column_id in accepted:
            if column_id not in values:
                continue
            column_times = known.setdefault(column_id, [])
            if not _keep_time(t, column_times):
                continue
            await _write_cell(
                db,
                run_id,
                KIND_DEVC,
                column_id,
                t,
                values[column_id],
                existing_points,
            )
            stored += 1
            if t not in column_times:
                column_times.append(t)
            if column_id not in touched_set:
                touched_set.add(column_id)
                touched.append(column_id)
    await db.flush()
    for column_id in touched:
        await _downsample(db, run_id, KIND_DEVC, column_id)
    return accepted, dropped, stored


def _cursor(seqs: list[int], since: Optional[int]) -> str:
    if seqs:
        return str(max(seqs))
    if since is not None:
        return str(since)
    return "0"


async def read_series(
    db: AsyncSession,
    run_id: uuid.UUID,
    since: Optional[int],
    device_ids: list[str],
) -> dict:
    """Page payload. device_ids is the devices query, already stored."""
    hrr_rows = await _read_points(db, run_id, KIND_HRR, [HRR_COLUMN], since)
    series: dict[str, list[dict]] = {column_id: [] for column_id in device_ids}
    series_rows = await _read_points(db, run_id, KIND_DEVC, device_ids, since)
    seqs: list[int] = []
    hrr_points = []
    for row in hrr_rows:
        hrr_points.append({"t": row.t, "v": row.value})
        seqs.append(int(row.seq))
    for row in series_rows:
        series[row.column_id].append({"t": row.t, "v": row.value})
        seqs.append(int(row.seq))
    return {
        "cursor": _cursor(seqs, since),
        "hrr": {"unit": HRR_UNIT, "points": hrr_points, "design": None},
        "devices": await _read_columns(db, run_id),
        "series": series,
    }


async def _read_points(
    db: AsyncSession,
    run_id: uuid.UUID,
    kind: str,
    column_ids: list[str],
    after: Optional[int],
) -> list[RunSeriesPoint]:
    if not column_ids:
        return []
    stmt = select(RunSeriesPoint).where(
        RunSeriesPoint.run_id == run_id,
        RunSeriesPoint.kind == kind,
        RunSeriesPoint.column_id.in_(column_ids),
    )
    if after is not None:
        stmt = stmt.where(RunSeriesPoint.seq > after)
    stmt = stmt.order_by(RunSeriesPoint.t, RunSeriesPoint.seq)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def _read_columns(db: AsyncSession, run_id: uuid.UUID) -> list[dict]:
    result = await db.execute(
        select(RunSeriesColumn)
        .where(
            RunSeriesColumn.run_id == run_id,
            RunSeriesColumn.kind == KIND_DEVC,
        )
        .order_by(RunSeriesColumn.column_id)
    )
    return [
        {"id": row.column_id, "quantity": row.quantity, "unit": row.unit}
        for row in result.scalars().all()
        if row.quantity
    ]
