"""Shared reliability execution for the sync endpoint and teq-reliability jobs."""
from __future__ import annotations

from types import SimpleNamespace

from time_eq import derive_geometry, get_b_value
from teq_reliability import (
    SteelParams,
    compute_reliability,
    compute_reliability_details,
    tlim_hours_for,
)


def _elements(converted_points: list) -> list:
    els = []
    for el in converted_points:
        pts = [SimpleNamespace(x=p["x"], y=p["y"]) for p in el["finalPoints"]]
        els.append(SimpleNamespace(comments=el.get("comments"), finalPoints=pts))
    return els


def _engine_kwargs(payload: dict, *, n_sim_cap: int | None) -> dict:
    """Translate an API-shaped payload dict into compute_reliability kwargs.

    ``n_sim_cap`` is applied for sync execution (10k). Pass ``None`` for job
    execution so larger N is allowed.
    """
    unprotected = bool(payload.get("unprotected"))
    fr_period = payload.get("fireResistancePeriod")
    if not unprotected and fr_period is None:
        raise ValueError("fireResistancePeriod is required for protected members")

    occupancy = payload["occupancy"]
    height = float(payload["compartmentHeight"])
    geo = derive_geometry(_elements(payload["convertedPoints"]), height)
    vent_widths = payload.get("openableWidths")
    if vent_widths is None:
        vent_widths = geo.wall_lengths
    vent_heights = [height] * len(vent_widths)

    params = SteelParams(t_lim_hours=tlim_hours_for(occupancy))
    if payload.get("sectionFactor") is not None:
        params.sect_factor = payload["sectionFactor"]
    if payload.get("criticalTemp") is not None:
        params.steel_fail_temp = payload["criticalTemp"]
    if payload.get("tLimMinutes") is not None:
        params.t_lim_hours = payload["tLimMinutes"] / 60.0
    if payload.get("bValue") is not None:
        params.thermal_inertia = payload["bValue"]
    elif payload.get("roomComposition"):
        params.thermal_inertia = get_b_value(
            room_composition=payload["roomComposition"],
            room_dimensions=geo.room_dimensions, At=geo.At)

    n_sim = max(int(payload.get("nSim") or 10000), 1)
    if n_sim_cap is not None:
        n_sim = min(n_sim, n_sim_cap)

    return dict(
        occupancy=occupancy, total_area=geo.At, floor_area=geo.floor_area,
        vent_widths=vent_widths, vent_heights=vent_heights,
        fr_period_min=fr_period, n_sim=n_sim,
        is_sprinklered=bool(payload.get("isSprinklered")),
        combustion_factor=float(payload.get("combustionFactor", 0.8)),
        sprinkler_factor=float(payload.get("sprinklerFactor", 0.65)),
        params=params, unprotected=unprotected,
        seed=payload.get("seed"),
    )


def run_reliability_from_payload(payload: dict, *, n_sim_cap: int | None = 10000):
    """Run compute_reliability from an API-shaped payload dict."""
    return compute_reliability(**_engine_kwargs(payload, n_sim_cap=n_sim_cap))


def run_reliability_details_from_payload(payload: dict, *, n_sim_cap: int | None = 10000):
    """As run_reliability_from_payload, but keeping the per-sample data the
    report charts need (identical run under the same seed)."""
    return compute_reliability_details(**_engine_kwargs(payload, n_sim_cap=n_sim_cap))


def reliability_http_body(result, *, unprotected: bool = False) -> dict:
    body = {
        "reliability": result.reliability,
        "reliabilityPercent": round(result.reliability * 100, 2),
        "nFailed": result.n_failed,
        "nSim": result.n_sim,
        "frPeriod": result.fr_period,
        "protectionThickness_mm": result.protection_thickness_mm,
        "bValue": result.b_value,
        "sectionFactor": result.section_factor,
        "criticalTemp": result.critical_temp,
        "factorsApplied": result.factors_applied,
        # The seed the run actually used (auto-resolved when the request had
        # none), so a charts request can reproduce the exact run shown here.
        "seed": result.seed,
    }
    if unprotected:
        del body["protectionThickness_mm"]
        del body["frPeriod"]
        body["unprotected"] = True
    return body
