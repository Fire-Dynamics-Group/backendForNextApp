import pytest
import re
from stairs_fds import setup_landings


def make_landing_elements(landing_pts, halflanding_pts):
    """Create mock landing elements matching the format setup_landings expects."""
    return [
        {"comments": "landing", "id": "1", "points": landing_pts},
        {"comments": "landing", "id": "2", "points": halflanding_pts},
    ]


def parse_xb(line):
    match = re.search(r"XB\s*=\s*([\d.\-,\s]+),\s*SURF", line)
    vals = [float(v.strip()) for v in match.group(1).split(",")]
    return {"x1": vals[0], "x2": vals[1], "y1": vals[2], "y2": vals[3], "z1": vals[4], "z2": vals[5]}


def get_parsed_lines(lines):
    return {
        "step1": [parse_xb(l) for l in lines if "STEP1" in l],
        "step2": [parse_xb(l) for l in lines if "STEP2" in l],
        "halflanding": [parse_xb(l) for l in lines if "HALFLANDING" in l],
        "landing": [parse_xb(l) for l in lines if "ID='LANDING'" in l],
    }


def run_setup(landing_pts, halflanding_pts, landing_up_side, landing_roles=None,
              fire_floor=1, total_floors=8, z=3.0, stair_enclosure_roof_z=25.0,
              stair_style="overlapping"):
    elements = make_landing_elements(landing_pts, halflanding_pts)
    if landing_roles is None:
        landing_roles = {"1": "floor", "2": "half"}
    return setup_landings(
        comments="landing",
        fire_floor=fire_floor,
        total_floors=total_floors,
        elements=elements,
        px_per_m=1,
        z=z,
        stair_enclosure_roof_z=stair_enclosure_roof_z,
        landing_roles=landing_roles,
        landing_up_side=landing_up_side,
        stair_style=stair_style,
    )


# ── Real data from the FDS file: x-direction stair, half landing to the right ──
LANDING_RIGHT = [{"x": 10.143, "y": 8.241}, {"x": 12.805, "y": 14.327}]
HALFLANDING_RIGHT = [{"x": 14.58, "y": 8.621}, {"x": 16.229, "y": 14.2}]

# ── Half landing to the LEFT of floor landing (mirrored) ──
LANDING_LEFT = [{"x": 14.58, "y": 8.241}, {"x": 16.229, "y": 14.327}]
HALFLANDING_LEFT = [{"x": 10.143, "y": 8.621}, {"x": 12.805, "y": 14.2}]


# ─────────────────────────────────────────────────────────────────────────────
# Gap assertion helpers
# ─────────────────────────────────────────────────────────────────────────────

def assert_no_gap_x_plus(data, halflanding_x1, label=""):
    """For +x stairs: last step x2 must reach or overlap halflanding_x1."""
    first_flight = data["step1"][:8]
    last_step_x2 = max(s["x2"] for s in first_flight)
    gap = halflanding_x1 - last_step_x2
    assert gap <= 0, f"{label}STEP1 gap of {gap:.3f}m (x2={last_step_x2}, hl_x1={halflanding_x1})"

    first_flight_s2 = data["step2"][:8]
    nearest_x2 = max(s["x2"] for s in first_flight_s2)
    gap2 = halflanding_x1 - nearest_x2
    assert gap2 <= 0, f"{label}STEP2 gap of {gap2:.3f}m (x2={nearest_x2}, hl_x1={halflanding_x1})"


def assert_no_gap_x_minus(data, halflanding_x2, label=""):
    """For -x stairs: last step x1 must reach or pass halflanding_x2."""
    first_flight = data["step1"][:8]
    furthest_x1 = min(s["x1"] for s in first_flight)
    gap = furthest_x1 - halflanding_x2
    assert gap <= 0, f"{label}STEP1 gap of {gap:.3f}m (x1={furthest_x1}, hl_x2={halflanding_x2})"

    first_flight_s2 = data["step2"][:8]
    furthest_x1_s2 = min(s["x1"] for s in first_flight_s2)
    gap2 = furthest_x1_s2 - halflanding_x2
    assert gap2 <= 0, f"{label}STEP2 gap of {gap2:.3f}m (x1={furthest_x1_s2}, hl_x2={halflanding_x2})"


# ─────────────────────────────────────────────────────────────────────────────
# All 4 configs: parameterised across both stair styles
# ─────────────────────────────────────────────────────────────────────────────

ALL_STYLES = ["overlapping", "individual"]


@pytest.mark.parametrize("style", ALL_STYLES)
class TestHalfLandingRight_UpflightRight:
    """Config 1: half landing to the right, upflight goes right (toward half landing)."""

    def test_no_gap(self, style):
        lines = run_setup(LANDING_RIGHT, HALFLANDING_RIGHT, "right", stair_style=style)
        data = get_parsed_lines(lines)
        assert_no_gap_x_plus(data, HALFLANDING_RIGHT[0]["x"], label=f"[{style}] ")

    def test_steps_generated(self, style):
        lines = run_setup(LANDING_RIGHT, HALFLANDING_RIGHT, "right", stair_style=style)
        data = get_parsed_lines(lines)
        assert len(data["step1"]) > 0
        assert len(data["step2"]) > 0


@pytest.mark.parametrize("style", ALL_STYLES)
class TestHalfLandingRight_UpflightLeft:
    """Config 2: half landing to the right, upflight goes left (away from half landing)."""

    def test_steps_generated(self, style):
        lines = run_setup(LANDING_RIGHT, HALFLANDING_RIGHT, "left", stair_style=style)
        data = get_parsed_lines(lines)
        assert len(data["step1"]) > 0
        assert len(data["step2"]) > 0


@pytest.mark.parametrize("style", ALL_STYLES)
class TestHalfLandingLeft_UpflightLeft:
    """Config 3: half landing to the left, upflight goes left (toward half landing)."""

    def test_no_gap(self, style):
        lines = run_setup(LANDING_LEFT, HALFLANDING_LEFT, "left", stair_style=style)
        data = get_parsed_lines(lines)
        assert_no_gap_x_minus(data, HALFLANDING_LEFT[1]["x"], label=f"[{style}] ")

    def test_steps_generated(self, style):
        lines = run_setup(LANDING_LEFT, HALFLANDING_LEFT, "left", stair_style=style)
        data = get_parsed_lines(lines)
        assert len(data["step1"]) > 0
        assert len(data["step2"]) > 0


@pytest.mark.parametrize("style", ALL_STYLES)
class TestHalfLandingLeft_UpflightRight:
    """Config 4: half landing to the left, upflight goes right (away from half landing)."""

    def test_steps_generated(self, style):
        lines = run_setup(LANDING_LEFT, HALFLANDING_LEFT, "right", stair_style=style)
        data = get_parsed_lines(lines)
        assert len(data["step1"]) > 0
        assert len(data["step2"]) > 0


# ─────────────────────────────────────────────────────────────────────────────
# Swapped roles: tested across both styles
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("style", ALL_STYLES)
class TestSwappedRoles:
    def test_swapped_upflight_left(self, style):
        lines = run_setup(
            LANDING_RIGHT, HALFLANDING_RIGHT, "left",
            landing_roles={"1": "half", "2": "floor"},
            stair_style=style,
        )
        data = get_parsed_lines(lines)
        assert_no_gap_x_minus(data, LANDING_RIGHT[1]["x"], label=f"[{style}] ")

    def test_swapped_upflight_right(self, style):
        lines = run_setup(
            LANDING_RIGHT, HALFLANDING_RIGHT, "right",
            landing_roles={"1": "half", "2": "floor"},
            stair_style=style,
        )
        data = get_parsed_lines(lines)
        assert len(data["step1"]) > 0


# ─────────────────────────────────────────────────────────────────────────────
# Varying floor heights: tested across both styles
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("style", ALL_STYLES)
@pytest.mark.parametrize("z,roof_z,fire_floor,total_floors", [
    (3.0, 25.0, 1, 8),
    (3.0, 9.0, 1, 3),
    (6.0, 30.0, 2, 10),
    (2.5, 50.0, 1, 20),
    (4.0, 12.0, 1, 4),
    (3.0, 6.0, 1, 2),
])
class TestVaryingFloorHeights:
    def test_no_gap_upflight_right(self, style, z, roof_z, fire_floor, total_floors):
        lines = run_setup(
            LANDING_RIGHT, HALFLANDING_RIGHT, "right",
            z=z, stair_enclosure_roof_z=roof_z,
            fire_floor=fire_floor, total_floors=total_floors,
            stair_style=style,
        )
        data = get_parsed_lines(lines)
        if data["step1"]:
            assert_no_gap_x_plus(data, HALFLANDING_RIGHT[0]["x"],
                                 label=f"[{style}] z={z},roof={roof_z}: ")

    def test_no_gap_upflight_left_mirrored(self, style, z, roof_z, fire_floor, total_floors):
        lines = run_setup(
            LANDING_LEFT, HALFLANDING_LEFT, "left",
            z=z, stair_enclosure_roof_z=roof_z,
            fire_floor=fire_floor, total_floors=total_floors,
            stair_style=style,
        )
        data = get_parsed_lines(lines)
        if data["step1"]:
            assert_no_gap_x_minus(data, HALFLANDING_LEFT[1]["x"],
                                  label=f"[{style}] z={z},roof={roof_z}: ")


# ─────────────────────────────────────────────────────────────────────────────
# Varying gap sizes: tested across both styles
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("style", ALL_STYLES)
@pytest.mark.parametrize("gap_size", [0.5, 1.0, 1.775, 2.5, 3.0, 5.0])
class TestVaryingGapSizes:
    def test_no_gap_right(self, style, gap_size):
        landing = [{"x": 10.0, "y": 8.0}, {"x": 12.0, "y": 14.0}]
        hl_x1 = 12.0 + gap_size
        halflanding = [{"x": hl_x1, "y": 8.0}, {"x": hl_x1 + 2.0, "y": 14.0}]
        lines = run_setup(landing, halflanding, "right", stair_style=style)
        data = get_parsed_lines(lines)
        assert_no_gap_x_plus(data, hl_x1, label=f"[{style}] gap={gap_size}: ")

    def test_no_gap_left(self, style, gap_size):
        hl_x2 = 10.0 - gap_size
        landing = [{"x": 10.0, "y": 8.0}, {"x": 12.0, "y": 14.0}]
        halflanding = [{"x": hl_x2 - 2.0, "y": 8.0}, {"x": hl_x2, "y": 14.0}]
        lines = run_setup(landing, halflanding, "left", stair_style=style)
        data = get_parsed_lines(lines)
        assert_no_gap_x_minus(data, hl_x2, label=f"[{style}] gap={gap_size}: ")


# ─────────────────────────────────────────────────────────────────────────────
# Individual style specific: steps should each be one tread wide, not overlapping
# ─────────────────────────────────────────────────────────────────────────────

class TestIndividualStyleStepWidth:
    """In individual style, each step should be exactly one tread wide."""

    def test_step_width_equals_tread(self):
        lines = run_setup(LANDING_RIGHT, HALFLANDING_RIGHT, "right", stair_style="individual")
        data = get_parsed_lines(lines)
        first_flight = data["step1"][:8]
        # All steps should have the same width (one tread)
        widths = [round(s["x2"] - s["x1"], 3) for s in first_flight]
        assert len(set(widths)) == 1, f"Steps have varying widths: {widths}"
        # The width should be much smaller than the landing width
        landing_width = LANDING_RIGHT[1]["x"] - LANDING_RIGHT[0]["x"]  # 2.662
        assert widths[0] < landing_width, (
            f"Individual step width {widths[0]} should be less than landing width {landing_width}"
        )

    def test_steps_do_not_overlap_in_stair_direction(self):
        lines = run_setup(LANDING_RIGHT, HALFLANDING_RIGHT, "right", stair_style="individual")
        data = get_parsed_lines(lines)
        first_flight = data["step1"][:8]
        # Sort by x1 and check no overlaps
        sorted_steps = sorted(first_flight, key=lambda s: s["x1"])
        for i in range(len(sorted_steps) - 1):
            assert sorted_steps[i]["x2"] <= sorted_steps[i + 1]["x1"] + 0.001, (
                f"Step {i} x2={sorted_steps[i]['x2']} overlaps step {i+1} x1={sorted_steps[i+1]['x1']}"
            )


class TestOverlappingStyleStepWidth:
    """In overlapping style, each step should be the full landing width."""

    def test_step1_width_equals_halflanding_width(self):
        """STEP1 goes TO the half landing, so uses half landing width."""
        lines = run_setup(LANDING_RIGHT, HALFLANDING_RIGHT, "right", stair_style="overlapping")
        data = get_parsed_lines(lines)
        first_flight = data["step1"][:8]
        hl_width = HALFLANDING_RIGHT[1]["x"] - HALFLANDING_RIGHT[0]["x"]  # 1.649
        for i, step in enumerate(first_flight):
            step_width = round(step["x2"] - step["x1"], 3)
            assert abs(step_width - hl_width) < 0.01, (
                f"Overlapping STEP1 {i} width {step_width} should equal half landing width {hl_width}"
            )

    def test_step2_width_equals_landing_width(self):
        """STEP2 goes TO the floor landing, so uses floor landing width."""
        lines = run_setup(LANDING_RIGHT, HALFLANDING_RIGHT, "right", stair_style="overlapping")
        data = get_parsed_lines(lines)
        first_flight = data["step2"][:8]
        landing_width = LANDING_RIGHT[1]["x"] - LANDING_RIGHT[0]["x"]  # 2.662
        for i, step in enumerate(first_flight):
            step_width = round(step["x2"] - step["x1"], 3)
            assert abs(step_width - landing_width) < 0.01, (
                f"Overlapping STEP2 {i} width {step_width} should equal landing width {landing_width}"
            )


# ─────────────────────────────────────────────────────────────────────────────
# Default style should be overlapping
# ─────────────────────────────────────────────────────────────────────────────

class TestDefaultStyle:
    def test_default_is_overlapping(self):
        """When stair_style is not provided, behaviour should match overlapping."""
        elements = make_landing_elements(LANDING_RIGHT, HALFLANDING_RIGHT)
        lines_default = setup_landings(
            comments="landing", fire_floor=1, total_floors=8,
            elements=elements, px_per_m=1, z=3.0, stair_enclosure_roof_z=25.0,
            landing_roles={"1": "floor", "2": "half"}, landing_up_side="right",
        )
        lines_explicit = run_setup(
            LANDING_RIGHT, HALFLANDING_RIGHT, "right", stair_style="overlapping"
        )
        assert lines_default == lines_explicit
