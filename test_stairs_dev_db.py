"""Integration test: validate stair geometry against the REAL projects in the
dev database, fetched live from the dev backend API.

Unlike the unit tests (test_stairs.py), this runs setup_landings on actual
user-drawn landings and asserts the steps form a usable staircase — in
particular that each flight BRIDGES its two landings (the rule the static unit
invariants missed: a flight can be non-degenerate, monotonic in z and inside the
landings' bounding box yet still stop short of the destination landing — see
Sam's Big Residential Project, a y-direction stair).

Network test. Skips cleanly when the dev API is unreachable (offline / CI
without egress). Override the endpoint with STAIRS_DEV_API.

Run just this file:  pytest test_stairs_dev_db.py -v
"""
import json
import os
import re
import urllib.request

import pytest

from fds import convertElPointsToCoords, makeElementsRelativeToOrigin, returnOrigin
from stairs_fds import setup_landings

API = os.environ.get("STAIRS_DEV_API", "https://backendfornextapp-dev.up.railway.app")
# Geometry invariants below are independent of the vertical params (they affect z
# heights / flight count, not the run-axis placement), so fixed values are fine.
PARAMS = dict(fire_floor=2, total_floors=6, z=10.0, stair_enclosure_roof_z=30.0, px_per_m=33.6)
TOL = 0.05  # metres of slack for edge overlap / footprint checks


def _get(path):
    with urllib.request.urlopen(API + path, timeout=30) as r:
        return json.load(r)


try:
    _PROJECTS = _get("/projects")
except Exception:  # noqa: BLE001 - any network/HTTP failure => skip the suite
    _PROJECTS = None

pytestmark = pytest.mark.skipif(_PROJECTS is None, reason=f"dev API unreachable at {API}")


def _floor_cases():
    """(project_id, floor_id, label) for every floor the dev DB exposes."""
    cases = []
    for p in _PROJECTS or []:
        for fl in p.get("floors", []):
            cases.append((p["id"], fl["id"], f"{p['name']}#floor{fl.get('floor_number')}"))
    return cases


CASES = _floor_cases()


# ── geometry helpers (mirror the production transform + stair parsing) ──────────
def _transform(elements):
    """Exactly what fds.testFunction does before setup_landings."""
    origin = returnOrigin(elements)
    elements = makeElementsRelativeToOrigin([dict(e) for e in elements], origin)
    elements = convertElPointsToCoords(elements, PARAMS["px_per_m"])
    ys = [pt["y"] for e in elements for pt in e["points"]]
    max_y = max(ys) if ys else 0
    for e in elements:
        for pt in e["points"]:
            pt["y"] = round(max_y - pt["y"], 5)
    return elements


def _xb(line):
    m = re.search(r"ID='([^']+)', XB = ([-0-9.,\s]+), SURF", line)
    return (m.group(1), [float(v) for v in m.group(2).split(",")]) if m else None


def _area(el):
    xs = [pt["x"] for pt in el["points"]]
    ys = [pt["y"] for pt in el["points"]]
    return (max(xs) - min(xs)) * (max(ys) - min(ys))


def _overlap(a_lo, a_hi, b_lo, b_hi):
    return min(a_hi, b_hi) >= max(a_lo, b_lo) - TOL


def _run_axis(land_box, half_box):
    """Axis the two landings are offset along — the direction the flight runs."""
    dy = abs((land_box[2] + land_box[3]) / 2 - (half_box[2] + half_box[3]) / 2)
    dx = abs((land_box[0] + land_box[1]) / 2 - (half_box[0] + half_box[1]) / 2)
    return (2, 3) if dy >= dx else (0, 1)  # XB indices for the run axis


@pytest.mark.parametrize("project_id,floor_id,label", CASES, ids=[c[2] for c in CASES])
def test_real_stair_bridges_landings(project_id, floor_id, label):
    els = _get(f"/projects/{project_id}/floors/{floor_id}/elements")
    landings = [e for e in els if e.get("comments") == "landing"]
    if len(landings) < 2:
        pytest.skip(f"{label}: <2 landings (no stair / incomplete drawing)")
    # setup_landings uses landings[0]=floor, landings[1]=half (array order). If
    # either is a degenerate point/line it's bad input data, not a code failure.
    if _area(landings[0]) < 0.01 or _area(landings[1]) < 0.01:
        pytest.skip(f"{label}: degenerate landing rectangle(s) in source data")

    te = _transform(els)
    boxes = [b for b in (_xb(l) for l in setup_landings(comments="landing", elements=te, **PARAMS)) if b]
    floor = [x for i, x in boxes if i == "LANDING"]
    half = [x for i, x in boxes if i == "HALFLANDING"]
    step1 = [x for i, x in boxes if i == "STEP1"]
    step2 = [x for i, x in boxes if i == "STEP2"]
    assert floor and half and step1 and step2, f"{label}: stair geometry missing"

    Lb, Hb = floor[0], half[0]
    r0, r1 = _run_axis(Lb, Hb)

    # Per-flight building blocks (8 steps each, emitted in climb order).
    flights1 = [step1[i:i + 8] for i in range(0, len(step1), 8)]
    flights2 = [step2[i:i + 8] for i in range(0, len(step2), 8)]

    # 1) No degenerate treads (real footprint in both horizontal axes).
    for tag, steps in (("STEP1", step1), ("STEP2", step2)):
        for s in steps:
            assert abs(s[1] - s[0]) > 0.02 and abs(s[3] - s[2]) > 0.02, f"{label}: degenerate {tag} tread {s}"

    # 2) Monotonic z climb within each flight.
    for fl in flights1 + flights2:
        zc = [(s[4] + s[5]) / 2 for s in fl]
        assert all(zc[k] > zc[k - 1] for k in range(1, len(zc))), f"{label}: non-monotonic z in flight"

    # 3) THE key rule: each flight bridges its two landings on the run axis —
    #    bottom tread overlaps the SOURCE platform, top tread overlaps the DEST.
    #    STEP1: floor -> half ; STEP2: half -> next floor (same footprint as floor).
    for fl in flights1:
        bottom, top = fl[0], fl[-1]
        assert _overlap(bottom[r0], bottom[r1], Lb[r0], Lb[r1]), f"{label}: STEP1 bottom doesn't meet floor landing"
        assert _overlap(top[r0], top[r1], Hb[r0], Hb[r1]), (
            f"{label}: STEP1 top run[{top[r0]:.2f},{top[r1]:.2f}] never reaches "
            f"half landing run[{Hb[r0]:.2f},{Hb[r1]:.2f}] — flight stops short of the landing"
        )
    for fl in flights2:
        bottom, top = fl[0], fl[-1]
        assert _overlap(bottom[r0], bottom[r1], Hb[r0], Hb[r1]), f"{label}: STEP2 bottom doesn't meet half landing"
        assert _overlap(top[r0], top[r1], Lb[r0], Lb[r1]), (
            f"{label}: STEP2 top run[{top[r0]:.2f},{top[r1]:.2f}] never reaches "
            f"next floor landing run[{Lb[r0]:.2f},{Lb[r1]:.2f}] — flight stops short"
        )
