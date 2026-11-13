"""Audit logging for fee proposal generations (inputs, Synergy gaps, and actor)."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel

import database
from models.db_models import FeeProposalGeneration
from models.fee_proposal_models import FeeProposalRequest


class FeeGenerationContext(BaseModel):
    user_email: Optional[str] = None
    user_name: Optional[str] = None
    is_test: Optional[bool] = None
    synergy_project_ref: Optional[str] = None
    synergy_project_label: Optional[str] = None
    suggested_filename: Optional[str] = None
    active_filename: Optional[str] = None
    prefill_statuses: Optional[Dict[str, Any]] = None
    provenance: Optional[Dict[str, Any]] = None
    directory_applied: Optional[Dict[str, Any]] = None
    directory_proposals: Optional[Dict[str, Any]] = None
    directory_declined: Optional[Dict[str, Any]] = None
    directory_review: Optional[List[str]] = None
    carried_from: Optional[Dict[str, str]] = None
    client_role_notice: Optional[str] = None


def is_test_actor(user_email: Optional[str], user_name: Optional[str], explicit: Optional[bool]) -> bool:
    """Flag Ian's runs as test generations so team-review exports can filter them out."""
    if explicit is not None:
        return bool(explicit)
    email = (user_email or "").strip().lower()
    if email:
        local = email.split("@", 1)[0]
        if local == "ian" or local.startswith("ian.") or local.startswith("ian+"):
            return True
    name = " ".join((user_name or "").strip().lower().split())
    if name in {"ian", "ian shaw"}:
        return True
    return False


def _prov_kind(provenance: Dict[str, Any], key: str) -> Optional[str]:
    entry = provenance.get(key)
    return entry.get("kind") if isinstance(entry, dict) else None


def summarize_synergy_gaps(
    data: FeeProposalRequest,
    ctx: Optional[FeeGenerationContext],
) -> Dict[str, Any]:
    """Compute which Synergy fields were missing/flagged and which ones the user filled or edited."""
    missing: List[str] = []
    user_filled: List[str] = []

    if ctx is None:
        return {
            "missing_from_synergy": missing,
            "user_filled_missing": user_filled,
            "has_missing_or_edited": False,
        }

    statuses = ctx.prefill_statuses or {}
    fields = statuses.get("fields") if isinstance(statuses.get("fields"), dict) else {}
    provenance = ctx.provenance or {}

    client_status = statuses.get("client_status")
    if client_status and client_status != "found":
        missing.append(f"client_role:{client_status}")
    elif statuses.get("client_lookup") == "unavailable":
        missing.append("client_role:unavailable")

    if statuses.get("site_address_present") is False:
        missing.append("site_address")

    for field_key in (
        "projectName",
        "projectCountry",
        "clientFirstName",
        "clientSurname",
        "clientCompanyName",
        "clientAddressLines",
    ):
        st = fields.get(field_key)
        if st and st != "from_synergy":
            missing.append(f"{field_key}:{st}")

    def _check_user_filled(
        label: str,
        has_value: bool,
        prefill_key: Optional[str],
        prov_key: Optional[str],
    ) -> None:
        if not has_value:
            return
        prov = _prov_kind(provenance, prov_key) if prov_key else None
        st = fields.get(prefill_key) if prefill_key else None
        if prov in ("edited", "carried", "contact") or (st is not None and st != "from_synergy"):
            user_filled.append(label)

    _check_user_filled("client_first_name", bool(data.client.first_name.strip()), "clientFirstName", "names")
    _check_user_filled("client_surname", bool(data.client.surname.strip()), "clientSurname", "names")
    _check_user_filled("client_company_name", bool(data.client.company_name.strip()), "clientCompanyName", "company")
    _check_user_filled(
        "client_address_lines",
        any(line.strip() for line in data.client.address_lines),
        "clientAddressLines",
        "address",
    )
    _check_user_filled("project_name", bool(data.project.project_name.strip()), "projectName", "projectName")

    country_prov = _prov_kind(provenance, "country")
    country_st = fields.get("projectCountry")
    if country_prov in ("edited", "carried") or (country_st is not None and country_st != "from_synergy"):
        user_filled.append("project_country")

    if data.project.project_location.strip():
        user_filled.append("project_location")

    has_gaps = bool(
        missing
        or user_filled
        or (ctx.directory_declined and len(ctx.directory_declined) > 0)
        or (ctx.directory_review and len(ctx.directory_review) > 0)
    )
    return {
        "missing_from_synergy": missing,
        "user_filled_missing": user_filled,
        "has_missing_or_edited": has_gaps,
    }


async def record_fee_generation(
    data: FeeProposalRequest,
    *,
    source: str,
    ctx: Optional[FeeGenerationContext] = None,
    forwarded_user_email: Optional[str] = None,
) -> Optional[str]:
    """Persist a fee proposal generation row. Never raises so document generation cannot fail."""
    if database.async_session is None:
        return None
    try:
        user_email = (ctx.user_email if ctx and ctx.user_email else forwarded_user_email) or None
        user_name = ctx.user_name if ctx else None
        is_test = is_test_actor(user_email, user_name, ctx.is_test if ctx else None)
        summary = summarize_synergy_gaps(data, ctx)

        synergy_context = ctx.model_dump(mode="json") if ctx else {}
        synergy_context["missing_from_synergy"] = summary["missing_from_synergy"]
        synergy_context["user_filled_missing"] = summary["user_filled_missing"]

        row = FeeProposalGeneration(
            source=source,
            user_email=user_email,
            user_name=user_name,
            engineer_name=data.fee_options.engineer_name or None,
            is_test=is_test,
            synergy_project_ref=ctx.synergy_project_ref if ctx else None,
            synergy_project_label=(
                (ctx.synergy_project_label if ctx else None)
                or getattr(data.project, "synergy_project_label", None)
            ),
            project_name=data.project.project_name or None,
            client_company_name=data.client.company_name or None,
            has_missing_or_edited=summary["has_missing_or_edited"],
            inputs=data.model_dump(mode="json"),
            synergy_context=synergy_context,
        )
        async with database.async_session() as db:
            db.add(row)
            await db.commit()
            return str(row.id)
    except Exception as exc:  # noqa: BLE001 — never fail generation over audit logging
        print(f"Warning: failed to record fee proposal generation: {exc}")
        return None


def _norm_str(value: Any) -> str:
    return " ".join(str(value or "").strip().split()).lower()


def _add_option(
    buckets: Dict[str, Dict[str, Any]],
    field: str,
    dedup_key: str,
    value: Any,
    *,
    by: Optional[str],
    created_at: Any,
) -> None:
    bucket = buckets[field]
    existing = bucket.get(dedup_key)
    if existing is not None:
        existing["count"] += 1
        return
    bucket[dedup_key] = {
        "value": value,
        "count": 1,
        "latest_at": created_at.isoformat() if hasattr(created_at, "isoformat") else created_at,
        "by": by,
    }


def collect_previous_fee_options(rows: List[FeeProposalGeneration]) -> Dict[str, List[Dict[str, Any]]]:
    """Deduplicate non-empty client/project values from past generations (most-recent-first)."""
    fields = ("company", "names", "address", "projectName", "projectLocation", "country")
    buckets: Dict[str, Dict[str, Any]] = {f: {} for f in fields}

    for row in rows:
        inputs = row.inputs if isinstance(row.inputs, dict) else {}
        client = inputs.get("client") if isinstance(inputs.get("client"), dict) else {}
        project = inputs.get("project") if isinstance(inputs.get("project"), dict) else {}
        by = row.user_name or row.engineer_name or row.user_email or None
        ts = row.created_at

        company = str(client.get("company_name") or "").strip()
        if company:
            _add_option(buckets, "company", _norm_str(company), company, by=by, created_at=ts)

        first = str(client.get("first_name") or "").strip()
        last = str(client.get("surname") or "").strip()
        if first or last:
            _add_option(
                buckets,
                "names",
                f"{_norm_str(first)}|{_norm_str(last)}",
                {"firstName": first, "lastName": last},
                by=by,
                created_at=ts,
            )

        raw_lines = client.get("address_lines")
        if isinstance(raw_lines, list):
            lines = [str(line).strip() for line in raw_lines if str(line or "").strip()]
            if lines:
                _add_option(
                    buckets,
                    "address",
                    "\n".join(_norm_str(line) for line in lines),
                    lines,
                    by=by,
                    created_at=ts,
                )

        pname = str(project.get("project_name") or "").strip()
        if pname:
            _add_option(buckets, "projectName", _norm_str(pname), pname, by=by, created_at=ts)

        ploc = str(project.get("project_location") or "").strip()
        if ploc:
            _add_option(buckets, "projectLocation", _norm_str(ploc), ploc, by=by, created_at=ts)

        country = str(project.get("country") or "").strip()
        if country in ("EW", "J", "OTHER"):
            _add_option(buckets, "country", country, country, by=by, created_at=ts)

    return {f: list(buckets[f].values()) for f in fields}
