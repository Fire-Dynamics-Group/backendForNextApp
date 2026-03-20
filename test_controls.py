"""Tests for controls.py - door control FDS line generation."""
import pytest
from controls import (
    moe_door_controls,
    fsa_door_deactivate,
    hybrid_door_controls,
    generate_door_controls,
    extract_controls_fds,
    return_hole_controls,
    Control_ID_Apartment,
    Control_ID_Stair,
)


class TestMoeDoorControls:
    def test_returns_ramp_and_ctrl_lines(self):
        result = moe_door_controls(30, 60, 35, 65)
        assert len(result) > 0
        ramp_lines = [l for l in result if "&RAMP" in l]
        ctrl_lines = [l for l in result if "&CTRL" in l]
        devc_lines = [l for l in result if "&DEVC" in l]
        assert len(ramp_lines) >= 4  # at least open+close for both doors
        assert len(ctrl_lines) == 2  # one per door
        assert len(devc_lines) == 2

    def test_contains_apartment_and_stair_ids(self):
        result = moe_door_controls(30, 60, 35, 65)
        joined = "\n".join(result)
        assert Control_ID_Apartment in joined
        assert Control_ID_Stair in joined

    def test_timing_offset(self):
        """RAMP times should be +-0.25 from specified times."""
        result = moe_door_controls(30, 60, 35, 65)
        ramp_lines = [l for l in result if "&RAMP" in l]
        # First RAMP should be at 29.75 (30 - 0.25)
        assert "T = 29.75" in ramp_lines[0]
        assert "T = 30.25" in ramp_lines[1]

    def test_skip_stair_close_when_inlet_needed(self):
        without_inlet = moe_door_controls(30, 60, 35, 65, is_stair_door_needed_for_inlet=False)
        with_inlet = moe_door_controls(30, 60, 35, 65, is_stair_door_needed_for_inlet=True)
        # With inlet should have fewer RAMP lines (no stair close)
        ramp_without = [l for l in without_inlet if "&RAMP" in l and Control_ID_Stair in l]
        ramp_with = [l for l in with_inlet if "&RAMP" in l and Control_ID_Stair in l]
        assert len(ramp_with) < len(ramp_without)


class TestFsaDoorDeactivate:
    def test_returns_lines(self):
        result = fsa_door_deactivate(35, 30)
        assert len(result) > 0

    def test_no_close_ramps(self):
        """FSA mode has no door close - only open RAMP lines."""
        result = fsa_door_deactivate(35, 30)
        ramp_lines = [l for l in result if "&RAMP" in l]
        # Should have exactly 4 RAMP lines: 2 per door (open only)
        assert len(ramp_lines) == 4

    def test_contains_both_door_ids(self):
        result = fsa_door_deactivate(35, 30)
        joined = "\n".join(result)
        assert Control_ID_Apartment in joined
        assert Control_ID_Stair in joined


class TestHybridDoorControls:
    def test_returns_lines(self):
        timings = {
            "moe_apartment_open": 30,
            "moe_apartment_close": 60,
            "moe_stair_open": 35,
            "moe_stair_close": 65,
            "fsa_apartment_open": 900,
            "fsa_stair_open": 900,
        }
        result = hybrid_door_controls(timings)
        assert len(result) > 0

    def test_has_moe_and_fsa_timings(self):
        timings = {
            "moe_apartment_open": 30,
            "moe_apartment_close": 60,
            "moe_stair_open": 35,
            "moe_stair_close": 65,
            "fsa_apartment_open": 900,
            "fsa_stair_open": 900,
        }
        result = hybrid_door_controls(timings)
        joined = "\n".join(result)
        # Should contain MOE timings
        assert "T = 29.75" in joined  # moe apt open - 0.25
        # Should contain FSA timings
        assert "T = 899.75" in joined  # fsa open - 0.25


class TestGenerateDoorControls:
    """Tests using the same key names the frontend sends."""

    def test_moe_mode_with_defaults(self):
        # Frontend sends these defaults for MOE
        result = generate_door_controls("MOE", {
            "apartment_open": 60, "apartment_close": 80,
            "stair_open": 70, "stair_close": 90,
        })
        assert len(result) > 0
        joined = "\n".join(result)
        assert "T = 59.75" in joined  # apt open - 0.25
        assert "T = 79.75" in joined  # apt close - 0.25

    def test_fsa_mode_with_defaults(self):
        result = generate_door_controls("FSA", {
            "stair_open": 0, "apartment_open": 60,
        })
        assert len(result) > 0
        joined = "\n".join(result)
        assert "T = 59.75" in joined  # apt open

    def test_both_mode_with_defaults(self):
        result = generate_door_controls("Both", {
            "apartment_open": 60, "apartment_close": 80,
            "stair_open": 70, "stair_close": 90,
            "fsa_apartment_open": 400, "fsa_stair_open": 400,
        })
        assert len(result) > 0
        joined = "\n".join(result)
        # MOE phase timings
        assert "T = 59.75" in joined
        # FSA phase timings
        assert "T = 399.75" in joined

    def test_unknown_mode_returns_empty(self):
        result = generate_door_controls("unknown", {})
        assert result == []

    def test_defaults_when_no_timings(self):
        result = generate_door_controls("MOE", {})
        assert len(result) > 0


class TestExtractControls:
    def test_returns_lines(self):
        result = extract_controls_fds(30, 1)
        assert len(result) > 0
        joined = "\n".join(result)
        assert "Extract Vent1" in joined

    def test_firefighting_mode(self):
        result_normal = extract_controls_fds(30, 1, is_firefighting=False)
        result_ff = extract_controls_fds(30, 1, is_firefighting=True)
        # Firefighting mode activates at door open time, not +10
        normal_ramps = [l for l in result_normal if "&RAMP" in l]
        ff_ramps = [l for l in result_ff if "&RAMP" in l]
        # Normal: activation at 40 (30+10), so T=39.75
        assert "T = 39.75" in normal_ramps[0]
        # FF: activation at 30, so T=29.75
        assert "T = 29.75" in ff_ramps[0]


class TestHoleControls:
    def test_activation(self):
        result = return_hole_controls(activation_time=50)
        assert len(result) > 0
        joined = "\n".join(result)
        assert "T = 49.75" in joined

    def test_deactivation(self):
        result = return_hole_controls(deactivation_time=100)
        assert len(result) > 0
        joined = "\n".join(result)
        assert "T = 99.75" in joined

    def test_no_times_returns_empty(self):
        result = return_hole_controls()
        assert result == []
