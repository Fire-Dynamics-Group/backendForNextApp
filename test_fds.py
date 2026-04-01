"""Tests for fds.py - FDS generation with controls and header integration."""
import pytest
from fds import sim_header, testFunction, add_door_holes_to_fds, create_stair_roof, create_stair_aov, generate_door_leakage_vents, create_extract_shaft
from controls import Control_ID_Apartment, Control_ID_Stair


class TestSimHeader:
    def test_contains_head(self):
        result = sim_header(chid='test_model', sim_end_time=300)
        assert any("&HEAD" in line for line in result)
        assert any("test_model" in line for line in result)

    def test_contains_time(self):
        result = sim_header(sim_end_time=1800)
        time_lines = [l for l in result if "&TIME" in l]
        assert len(time_lines) == 1
        assert "T_END=1800" in time_lines[0]

    def test_contains_dump(self):
        result = sim_header()
        assert any("&DUMP" in line for line in result)

    def test_contains_comb(self):
        result = sim_header()
        assert any("&COMB" in line for line in result)


class TestDoorHolesWithCtrl:
    def setup_method(self):
        self.elements = [
            {"comments": "door", "id": 0, "points": [{"x": 5.0, "y": 3.0}, {"x": 5.0, "y": 4.0}], "type": "polyline"},
            {"comments": "door", "id": 1, "points": [{"x": 10.0, "y": 3.0}, {"x": 10.0, "y": 4.0}], "type": "polyline"},
        ]
        self.roles = {"0": "apartment", "1": "stair"}

    def test_ctrl_id_added_for_moe(self):
        result = add_door_holes_to_fds(self.elements, z=10, wall_height=3, wall_thickness=0.2, fds_array=[], scenario_type="MOE", door_roles=self.roles)
        assert len(result) == 2
        assert f"CTRL_ID='{Control_ID_Apartment}'" in result[0]
        assert f"CTRL_ID='{Control_ID_Stair}'" in result[1]

    def test_ctrl_id_added_for_fsa(self):
        result = add_door_holes_to_fds(self.elements, z=10, wall_height=3, wall_thickness=0.2, fds_array=[], scenario_type="FSA", door_roles=self.roles)
        assert f"CTRL_ID='{Control_ID_Apartment}'" in result[0]

    def test_no_ctrl_for_none_scenario(self):
        result = add_door_holes_to_fds(self.elements, z=10, wall_height=3, wall_thickness=0.2, fds_array=[], scenario_type="none", door_roles=self.roles)
        assert "CTRL_ID" not in result[0]

    def test_no_ctrl_when_no_role_assigned(self):
        result = add_door_holes_to_fds(self.elements, z=10, wall_height=3, wall_thickness=0.2, fds_array=[], scenario_type="MOE", door_roles={})
        assert "CTRL_ID" not in result[0]
        assert "CTRL_ID" not in result[1]

    def test_hole_id_uses_role_name(self):
        result = add_door_holes_to_fds(self.elements, z=10, wall_height=3, wall_thickness=0.2, fds_array=[], scenario_type="MOE", door_roles=self.roles)
        assert "Apartment Door Hole" in result[0]
        assert "Stair Door Hole" in result[1]


class TestTestFunctionIntegration:
    def setup_method(self):
        self.elements = [
            {"comments": "obstruction", "id": 0, "points": [{"x": 0, "y": 0}, {"x": 100, "y": 0}, {"x": 100, "y": 50}, {"x": 0, "y": 50}, {"x": 0, "y": 0}], "type": "polyline"},
            {"comments": "mesh", "id": 1, "points": [{"x": 0, "y": 0}, {"x": 100, "y": 50}], "type": "rect"},
            {"comments": "door", "id": 2, "points": [{"x": 50, "y": 0}, {"x": 50, "y": 10}], "type": "polyline"},
            {"comments": "fire", "id": 3, "points": [{"x": 25, "y": 25}], "type": "point"},
        ]

    def test_moe_output_contains_header(self):
        result = testFunction(
            self.elements, z=10, wall_height=3, wall_thickness=0.2,
            stair_height=30, px_per_m=10, fire_floor=2, total_floors=7,
            stair_enclosure_roof_z=40, scenario_type="MOE", sim_end_time=300,
            door_openings={"apartment_open": "30", "apartment_close": "60", "stair_open": "35", "stair_close": "65"}
        )
        assert "&HEAD CHID='model'" in result
        assert "&TIME T_END=300" in result
        assert "&TAIL" in result

    def test_moe_output_contains_controls(self):
        result = testFunction(
            self.elements, z=10, wall_height=3, wall_thickness=0.2,
            stair_height=30, px_per_m=10, fire_floor=2, total_floors=7,
            stair_enclosure_roof_z=40, scenario_type="MOE", sim_end_time=300,
            door_openings={"apartment_open": "30", "apartment_close": "60"}
        )
        assert "&RAMP" in result
        assert "&CTRL" in result
        assert "Apartment Door Hole" in result

    def test_fsa_output_contains_controls(self):
        result = testFunction(
            self.elements, z=10, wall_height=3, wall_thickness=0.2,
            stair_height=30, px_per_m=10, fire_floor=2, total_floors=7,
            stair_enclosure_roof_z=40, scenario_type="FSA", sim_end_time=300,
        )
        assert "&RAMP" in result
        assert "Apartment Door Hole" in result

    def test_both_output_contains_hybrid_controls(self):
        result = testFunction(
            self.elements, z=10, wall_height=3, wall_thickness=0.2,
            stair_height=30, px_per_m=10, fire_floor=2, total_floors=7,
            stair_enclosure_roof_z=40, scenario_type="Both", sim_end_time=1800,
            door_openings={
                "apartment_open": "30", "apartment_close": "60",
                "stair_open": "35", "stair_close": "65",
                "fsa_apartment_open": "900", "fsa_stair_open": "900"
            }
        )
        assert "&TIME T_END=1800" in result
        assert "Apartment Door Hole" in result
        assert "Stair Door Hole" in result

    def test_output_contains_reaction(self):
        result = testFunction(
            self.elements, z=10, wall_height=3, wall_thickness=0.2,
            stair_height=30, px_per_m=10, fire_floor=2, total_floors=7,
            stair_enclosure_roof_z=40, scenario_type="MOE", sim_end_time=300,
        )
        assert "POLYURETHANE" in result

    def test_door_holes_have_ctrl_id_with_roles(self):
        result = testFunction(
            self.elements, z=10, wall_height=3, wall_thickness=0.2,
            stair_height=30, px_per_m=10, fire_floor=2, total_floors=7,
            stair_enclosure_roof_z=40, scenario_type="MOE", sim_end_time=300,
            door_roles={"2": "apartment"},
        )
        assert "CTRL_ID='Apartment Door Hole'" in result

    def test_door_holes_no_ctrl_without_roles(self):
        result = testFunction(
            self.elements, z=10, wall_height=3, wall_thickness=0.2,
            stair_height=30, px_per_m=10, fire_floor=2, total_floors=7,
            stair_enclosure_roof_z=40, scenario_type="MOE", sim_end_time=300,
            door_roles={},
        )
        assert "CTRL_ID" not in result


class TestStairRoof:
    def test_stair_roof_generated(self):
        """Verify create_stair_roof produces an OBST line at the correct Z height."""
        elements = [
            {"comments": "stairObstruction", "id": 0, "points": [
                {"x": 0.0, "y": 0.0}, {"x": 3.0, "y": 0.0},
                {"x": 3.0, "y": 2.0}, {"x": 0.0, "y": 2.0}, {"x": 0.0, "y": 0.0}
            ], "type": "polyline"},
        ]
        roof_z = 21.0
        result = create_stair_roof(elements, roof_z)
        assert len(result) == 1
        assert "&OBST ID='Stair Roof'" in result[0]
        assert "SURF_ID='Plasterboard'" in result[0]
        # Z range should be roof_z - 0.2 to roof_z
        assert "20.8" in result[0]
        assert "21.0" in result[0]

    def test_stair_roof_bounding_box(self):
        """Verify the roof covers the bounding box of all stairObstruction elements."""
        elements = [
            {"comments": "stairObstruction", "id": 0, "points": [
                {"x": 1.0, "y": 1.0}, {"x": 3.0, "y": 1.0},
                {"x": 3.0, "y": 2.0}, {"x": 1.0, "y": 2.0}, {"x": 1.0, "y": 1.0}
            ], "type": "polyline"},
            {"comments": "stairObstruction", "id": 1, "points": [
                {"x": 2.0, "y": 0.0}, {"x": 5.0, "y": 0.0},
                {"x": 5.0, "y": 4.0}, {"x": 2.0, "y": 4.0}, {"x": 2.0, "y": 0.0}
            ], "type": "polyline"},
        ]
        roof_z = 15.0
        result = create_stair_roof(elements, roof_z)
        assert len(result) == 1
        # Bounding box: x_min=1.0, x_max=5.0, y_min=0.0, y_max=4.0
        line = result[0]
        assert "1.0" in line
        assert "5.0" in line
        assert "0.0" in line
        assert "4.0" in line

    def test_stair_roof_empty_when_no_stair_obstructions(self):
        """Return empty list when there are no stairObstruction elements."""
        elements = [
            {"comments": "obstruction", "id": 0, "points": [
                {"x": 0.0, "y": 0.0}, {"x": 3.0, "y": 3.0}
            ], "type": "polyline"},
        ]
        result = create_stair_roof(elements, 10.0)
        assert result == []


class TestStairAOV:
    def test_aov_generated(self):
        """Verify create_stair_aov produces a shaft OBST and AOV HOLE."""
        elements = [
            {"comments": "landing", "id": 0, "points": [
                {"x": 1.0, "y": 1.0}, {"x": 3.0, "y": 1.0},
                {"x": 3.0, "y": 3.0}, {"x": 1.0, "y": 3.0}, {"x": 1.0, "y": 1.0}
            ], "type": "polyline"},
            {"comments": "landing", "id": 1, "points": [
                {"x": 1.0, "y": 5.0}, {"x": 3.0, "y": 5.0},
                {"x": 3.0, "y": 7.0}, {"x": 1.0, "y": 7.0}, {"x": 1.0, "y": 5.0}
            ], "type": "polyline"},
        ]
        roof_z = 21.0
        result = create_stair_aov(elements, roof_z)
        assert len(result) == 2
        assert "&OBST ID='AOV Shaft'" in result[0]
        assert "&HOLE ID='AOV'" in result[1]
        # Default mode is always_open — no CTRL_ID on either line
        assert "CTRL_ID" not in result[0]
        assert "CTRL_ID" not in result[1]

    def test_aov_timed_has_ctrl_id(self):
        """When mode is timed, AOV HOLE should have CTRL_ID but shaft OBST should not."""
        elements = [
            {"comments": "landing", "id": 0, "points": [
                {"x": 1.0, "y": 1.0}, {"x": 3.0, "y": 3.0}
            ], "type": "polyline"},
        ]
        result = create_stair_aov(elements, 21.0, aov_mode="timed")
        hole_line = [l for l in result if "&HOLE" in l][0]
        obst_line = [l for l in result if "&OBST" in l][0]
        assert "CTRL_ID='Extract Vent1'" in hole_line
        assert "CTRL_ID" not in obst_line

    def test_aov_sprinkler_has_ctrl_id(self):
        """When mode is sprinkler, AOV HOLE should have CTRL_ID but shaft OBST should not."""
        elements = [
            {"comments": "landing", "id": 0, "points": [
                {"x": 1.0, "y": 1.0}, {"x": 3.0, "y": 3.0}
            ], "type": "polyline"},
        ]
        result = create_stair_aov(elements, 21.0, aov_mode="sprinkler")
        hole_line = [l for l in result if "&HOLE" in l][0]
        obst_line = [l for l in result if "&OBST" in l][0]
        assert "CTRL_ID='Extract Vent1'" in hole_line
        assert "CTRL_ID" not in obst_line

    def test_aov_1m_square(self):
        """Verify the AOV HOLE is 1m x 1m and the shaft OBST is 1.4m x 1.4m."""
        elements = [
            {"comments": "landing", "id": 0, "points": [
                {"x": 2.0, "y": 2.0}, {"x": 4.0, "y": 2.0},
                {"x": 4.0, "y": 4.0}, {"x": 2.0, "y": 4.0}, {"x": 2.0, "y": 2.0}
            ], "type": "polyline"},
        ]
        roof_z = 10.0
        result = create_stair_aov(elements, roof_z, cell_size=0.2)
        # Check HOLE is 1m x 1m
        hole_line = [l for l in result if "&HOLE" in l][0]
        xb_part = hole_line.split("XB=")[1].split("/")[0].split(",CTRL_ID")[0].split(", CTRL_ID")[0]
        vals = [float(v.strip()) for v in xb_part.split(",")]
        x1, x2, y1, y2, z1, z2 = vals
        assert abs((x2 - x1) - 1.0) < 0.01
        assert abs((y2 - y1) - 1.0) < 0.01
        # Check shaft OBST is 1.4m x 1.4m
        obst_line = [l for l in result if "&OBST" in l][0]
        xb_part = obst_line.split("XB=")[1].split(",")[0:6]
        # Re-parse: split on ", SURF_ID" first to isolate XB
        xb_str = obst_line.split("XB=")[1].split(", SURF_ID")[0]
        vals = [float(v.strip()) for v in xb_str.split(",")]
        sx1, sx2, sy1, sy2, sz1, sz2 = vals
        assert abs((sx2 - sx1) - 1.4) < 0.01
        assert abs((sy2 - sy1) - 1.4) < 0.01

    def test_aov_shaft_z_range(self):
        """Verify shaft OBST z from roof_z to roof_z+2.0, HOLE z from roof_z-cell_size to roof_z+3.0."""
        elements = [
            {"comments": "landing", "id": 0, "points": [
                {"x": 2.0, "y": 2.0}, {"x": 4.0, "y": 2.0},
                {"x": 4.0, "y": 4.0}, {"x": 2.0, "y": 4.0}, {"x": 2.0, "y": 2.0}
            ], "type": "polyline"},
        ]
        roof_z = 21.0
        cell_size = 0.2
        result = create_stair_aov(elements, roof_z, cell_size=cell_size)
        # Shaft OBST z range: 21.0 to 23.0
        obst_line = [l for l in result if "&OBST" in l][0]
        xb_str = obst_line.split("XB=")[1].split(", SURF_ID")[0]
        vals = [float(v.strip()) for v in xb_str.split(",")]
        assert vals[4] == 21.0  # shaft z1 = roof_z
        assert vals[5] == 23.0  # shaft z2 = roof_z + 2.0
        # HOLE z range: 20.8 to 24.0
        hole_line = [l for l in result if "&HOLE" in l][0]
        xb_part = hole_line.split("XB=")[1].split("/")[0].split(",CTRL_ID")[0].split(", CTRL_ID")[0]
        hvals = [float(v.strip()) for v in xb_part.split(",")]
        assert hvals[4] == 20.8  # hole z1 = roof_z - cell_size
        assert hvals[5] == 24.0  # hole z2 = roof_z + 3.0

    def test_aov_empty_when_no_landings(self):
        """Return empty list when there are no landing elements."""
        elements = [
            {"comments": "obstruction", "id": 0, "points": [
                {"x": 0.0, "y": 0.0}, {"x": 3.0, "y": 3.0}
            ], "type": "polyline"},
        ]
        result = create_stair_aov(elements, 10.0)
        assert result == []


class TestLeakageDoors:
    """Tests for Crown Wharf style door leakage: bottom-only, fixed area, configurable connectivity."""

    def setup_method(self):
        # Y-extending door (thin in X) at x=5.0, y spans 3.0-4.0
        # X-extending door (thin in Y) at y=3.0, x spans 10.0-11.0
        self.elements = [
            {"comments": "door", "id": 0, "points": [{"x": 5.0, "y": 3.0}, {"x": 5.0, "y": 4.0}], "type": "polyline"},
            {"comments": "door", "id": 1, "points": [{"x": 10.0, "y": 3.0}, {"x": 11.0, "y": 3.0}], "type": "polyline"},
        ]

    def test_leakage_door_excluded_from_holes(self):
        """Doors with role 'leakage' should NOT produce a HOLE."""
        roles = {"0": "leakage", "1": "apartment"}
        result = add_door_holes_to_fds(
            self.elements, z=10, wall_height=3, wall_thickness=0.2,
            fds_array=[], scenario_type="MOE", door_roles=roles
        )
        assert len(result) == 1
        assert "Apartment Door Hole" in result[0]

    def test_single_bottom_vent_only(self):
        """Crown Wharf pattern: only one bottom vent, no top/left/right."""
        door = self.elements[0]
        result = generate_door_leakage_vents(door, door_index=0, z=10, seal_type="non-smoke-sealed")
        vent_lines = [l for l in result if "&VENT" in l]
        assert len(vent_lines) == 1
        assert "bottom vent" in vent_lines[0].lower()

    def test_hvac_leaks_to_ambient(self):
        """All leakages go to AMBIENT, not a second vent."""
        door = self.elements[0]
        result = generate_door_leakage_vents(door, door_index=0, z=10, seal_type="non-smoke-sealed")
        hvac_lines = [l for l in result if "&HVAC" in l]
        assert len(hvac_lines) == 1
        assert "VENT2_ID='AMBIENT'" in hvac_lines[0]
        assert "LEAK_ENTHALPY=.TRUE." in hvac_lines[0]

    def test_fixed_area_single_smoke_sealed(self):
        """Smoke sealed single door: fixed area 0.01."""
        door = self.elements[0]
        result = generate_door_leakage_vents(door, door_index=0, z=10, seal_type="smoke-sealed")
        hvac_lines = [l for l in result if "&HVAC" in l]
        assert "AREA=0.01" in hvac_lines[0]

    def test_fixed_area_non_smoke_sealed(self):
        """Non-smoke sealed door: fixed area 0.01."""
        door = self.elements[0]
        result = generate_door_leakage_vents(door, door_index=0, z=10, seal_type="non-smoke-sealed")
        hvac_lines = [l for l in result if "&HVAC" in l]
        assert "AREA=0.01" in hvac_lines[0]

    def test_frontend_format_single_smoke_sealed(self):
        """Frontend sends single_smoke_sealed (underscores): fixed area 0.01."""
        door = self.elements[0]
        result = generate_door_leakage_vents(door, door_index=0, z=10, seal_type="single_smoke_sealed")
        hvac_lines = [l for l in result if "&HVAC" in l]
        assert "AREA=0.01" in hvac_lines[0]

    def test_frontend_format_double_smoke_sealed(self):
        """Frontend sends double_smoke_sealed (underscores): fixed area 0.03."""
        door = self.elements[0]
        result = generate_door_leakage_vents(door, door_index=0, z=10, seal_type="double_smoke_sealed")
        hvac_lines = [l for l in result if "&HVAC" in l]
        assert "AREA=0.03" in hvac_lines[0]

    def test_fixed_area_double_smoke_sealed(self):
        """Double smoke sealed door: fixed area 0.03."""
        door = self.elements[0]
        result = generate_door_leakage_vents(door, door_index=0, z=10, seal_type="double-smoke-sealed")
        hvac_lines = [l for l in result if "&HVAC" in l]
        assert "AREA=0.03" in hvac_lines[0]

    def test_fixed_area_lift(self):
        """Lift door: fixed area 0.06."""
        door = self.elements[0]
        result = generate_door_leakage_vents(door, door_index=0, z=10, seal_type="lift")
        hvac_lines = [l for l in result if "&HVAC" in l]
        assert "AREA=0.06" in hvac_lines[0]

    def test_prefix_from_seal_type(self):
        """Seal type determines prefix in naming."""
        door = self.elements[0]
        result_smoke = generate_door_leakage_vents(door, door_index=0, z=10, seal_type="smoke-sealed")
        result_nonsmoke = generate_door_leakage_vents(door, door_index=0, z=10, seal_type="non-smoke-sealed")
        hvac_smoke = [l for l in result_smoke if "&HVAC" in l][0]
        hvac_nonsmoke = [l for l in result_nonsmoke if "&HVAC" in l][0]
        assert "smoke_sealed_single" in hvac_smoke
        assert "nonsmoke_sealed" in hvac_nonsmoke

    # --- Integration tests ---

    def test_integration_leakage_role_in_testfunction(self):
        """Full integration: leakage role door should produce HVAC lines, no HOLE."""
        elements = [
            {"comments": "obstruction", "id": 0, "points": [
                {"x": 0, "y": 0}, {"x": 100, "y": 0}, {"x": 100, "y": 50},
                {"x": 0, "y": 50}, {"x": 0, "y": 0}
            ], "type": "polyline"},
            {"comments": "mesh", "id": 1, "points": [{"x": 0, "y": 0}, {"x": 100, "y": 50}], "type": "rect"},
            {"comments": "door", "id": 2, "points": [{"x": 50, "y": 0}, {"x": 50, "y": 10}], "type": "polyline"},
            {"comments": "fire", "id": 3, "points": [{"x": 25, "y": 25}], "type": "point"},
        ]
        result = testFunction(
            elements, z=10, wall_height=3, wall_thickness=0.2,
            stair_height=30, px_per_m=10, fire_floor=2, total_floors=7,
            stair_enclosure_roof_z=40, scenario_type="MOE", sim_end_time=300,
            door_roles={"2": "leakage"},
            door_leakage_config={"2": {"sealType": "non-smoke-sealed"}},
            door_leakages_enabled=True,
        )
        assert "Leakage Door Hole" not in result
        assert "&HVAC" in result
        assert "LEAK" in result


class TestAlwaysOpenDoors:
    """Tests for always-open doors: HOLE with no CTRL_ID."""

    def setup_method(self):
        self.elements = [
            {"comments": "door", "id": 0, "points": [{"x": 5.0, "y": 3.0}, {"x": 5.0, "y": 4.0}], "type": "polyline"},
            {"comments": "door", "id": 1, "points": [{"x": 10.0, "y": 3.0}, {"x": 11.0, "y": 3.0}], "type": "polyline"},
        ]

    def test_always_open_produces_hole(self):
        """always_open doors should produce a HOLE."""
        roles = {"0": "always_open"}
        result = add_door_holes_to_fds(
            self.elements, z=10, wall_height=3, wall_thickness=0.2,
            fds_array=[], scenario_type="MOE", door_roles=roles
        )
        hole_lines = [l for l in result if "Always Open Door Hole" in l]
        assert len(hole_lines) == 1

    def test_always_open_has_no_ctrl_id(self):
        """always_open doors should NOT have a CTRL_ID."""
        roles = {"0": "always_open"}
        result = add_door_holes_to_fds(
            self.elements, z=10, wall_height=3, wall_thickness=0.2,
            fds_array=[], scenario_type="MOE", door_roles=roles
        )
        hole_line = [l for l in result if "Always Open" in l][0]
        assert "CTRL_ID" not in hole_line

    def test_always_open_and_apartment_together(self):
        """Mix of always_open and apartment doors: apartment gets CTRL, always_open does not."""
        roles = {"0": "always_open", "1": "apartment"}
        result = add_door_holes_to_fds(
            self.elements, z=10, wall_height=3, wall_thickness=0.2,
            fds_array=[], scenario_type="MOE", door_roles=roles
        )
        assert len(result) == 2
        always_open_line = [l for l in result if "Always Open" in l][0]
        apartment_line = [l for l in result if "Apartment" in l][0]
        assert "CTRL_ID" not in always_open_line
        assert "CTRL_ID" in apartment_line


class TestStairRoofAndAOVInOutput:
    """Integration tests: verify stair roof, AOV, and extract controls appear in testFunction output."""

    def setup_method(self):
        self.elements = [
            {"comments": "obstruction", "id": 0, "points": [
                {"x": 0, "y": 0}, {"x": 100, "y": 0}, {"x": 100, "y": 50},
                {"x": 0, "y": 50}, {"x": 0, "y": 0}
            ], "type": "polyline"},
            {"comments": "mesh", "id": 1, "points": [{"x": 0, "y": 0}, {"x": 100, "y": 50}], "type": "rect"},
            {"comments": "door", "id": 2, "points": [{"x": 50, "y": 0}, {"x": 50, "y": 10}], "type": "polyline"},
            {"comments": "fire", "id": 3, "points": [{"x": 25, "y": 25}], "type": "point"},
            {"comments": "stairObstruction", "id": 4, "points": [
                {"x": 110, "y": 0}, {"x": 150, "y": 0}, {"x": 150, "y": 50},
                {"x": 110, "y": 50}, {"x": 110, "y": 0}
            ], "type": "polyline"},
            {"comments": "stairMesh", "id": 5, "points": [{"x": 110, "y": 0}, {"x": 150, "y": 50}], "type": "rect"},
            {"comments": "landing", "id": 6, "points": [
                {"x": 115, "y": 10}, {"x": 140, "y": 10}, {"x": 140, "y": 25},
                {"x": 115, "y": 25}, {"x": 115, "y": 10}
            ], "type": "polyline"},
            {"comments": "landing", "id": 7, "points": [
                {"x": 115, "y": 30}, {"x": 140, "y": 30}, {"x": 140, "y": 45},
                {"x": 115, "y": 45}, {"x": 115, "y": 30}
            ], "type": "polyline"},
        ]

    def test_stair_roof_in_output(self):
        result = testFunction(
            self.elements, z=10, wall_height=3, wall_thickness=0.2,
            stair_height=30, px_per_m=10, fire_floor=2, total_floors=7,
            stair_enclosure_roof_z=40, scenario_type="MOE", sim_end_time=300,
        )
        assert "&OBST ID='Stair Roof'" in result

    def test_aov_in_output(self):
        result = testFunction(
            self.elements, z=10, wall_height=3, wall_thickness=0.2,
            stair_height=30, px_per_m=10, fire_floor=2, total_floors=7,
            stair_enclosure_roof_z=40, scenario_type="MOE", sim_end_time=300,
        )
        assert "&HOLE ID='AOV'" in result

    def test_no_extract_controls_in_always_open(self):
        """Default always_open mode should not include extract controls."""
        result = testFunction(
            self.elements, z=10, wall_height=3, wall_thickness=0.2,
            stair_height=30, px_per_m=10, fire_floor=2, total_floors=7,
            stair_enclosure_roof_z=40, scenario_type="MOE", sim_end_time=300,
        )
        assert "Extract Vent" not in result

    def test_extract_controls_in_timed_output(self):
        """Timed mode should include extract controls."""
        result = testFunction(
            self.elements, z=10, wall_height=3, wall_thickness=0.2,
            stair_height=30, px_per_m=10, fire_floor=2, total_floors=7,
            stair_enclosure_roof_z=40, scenario_type="MOE", sim_end_time=300,
            aov_mode="timed", aov_activation_time=45,
        )
        assert "Extract Vent" in result

    def test_sprinkler_devc_in_sprinkler_output(self):
        """Sprinkler mode should include sprinkler DEVC lines."""
        result = testFunction(
            self.elements, z=10, wall_height=3, wall_thickness=0.2,
            stair_height=30, px_per_m=10, fire_floor=2, total_floors=7,
            stair_enclosure_roof_z=40, scenario_type="MOE", sim_end_time=300,
            aov_mode="sprinkler",
        )
        assert "AOV Sprinkler" in result
        assert "AOV Link" in result


class TestExtractShaft:
    """Tests for extract shaft generation."""

    def setup_method(self):
        self.extract = {
            "comments": "extract", "id": 0,
            "points": [{"x": 5.0, "y": 3.0}, {"x": 5.0, "y": 4.0}],
            "type": "polyline"
        }

    def test_natural_shaft_generates_mesh(self):
        config = {"type": "natural", "shaftWidth": 0.9, "shaftDepth": 0.9}
        result = create_extract_shaft(self.extract, config, z=10, wall_height=3, stair_enclosure_roof_z=40, wall_thickness=0.2)
        mesh_lines = [l for l in result if "&MESH" in l]
        assert len(mesh_lines) == 1
        assert "Extract_Shaft_1" in mesh_lines[0]

    def test_natural_shaft_has_roof_hole_and_mesh_vent(self):
        """Natural shaft: HOLE through roof + OPEN mesh vent at ZMAX."""
        config = {"type": "natural", "shaftWidth": 0.9, "shaftDepth": 0.9}
        result = create_extract_shaft(self.extract, config, z=10, wall_height=3, stair_enclosure_roof_z=40, wall_thickness=0.2)
        roof_holes = [l for l in result if "&HOLE" in l and "Roof" in l]
        assert len(roof_holes) == 1
        assert "Extract Roof Opening 1" in roof_holes[0]
        mesh_vents = [l for l in result if "&VENT" in l and "ZMAX" in l]
        assert len(mesh_vents) == 1
        assert "SURF_ID='OPEN'" in mesh_vents[0]

    def test_natural_shaft_has_no_surf(self):
        config = {"type": "natural"}
        result = create_extract_shaft(self.extract, config, z=10, wall_height=3, stair_enclosure_roof_z=40, wall_thickness=0.2)
        surf_lines = [l for l in result if "&SURF" in l]
        assert len(surf_lines) == 0

    def test_mechanical_shaft_has_surf_and_fan_at_zmax(self):
        """Mechanical shaft: SURF with HEAT_TRANSFER_COEFFICIENT=0.0, fan VENT at ZMAX, no corridor-level vent."""
        config = {"type": "mechanical", "flowRate": 6.0, "shaftWidth": 0.9, "shaftDepth": 0.9}
        result = create_extract_shaft(self.extract, config, z=10, wall_height=3, stair_enclosure_roof_z=40, wall_thickness=0.2)
        surf_lines = [l for l in result if "&SURF" in l]
        assert len(surf_lines) == 1
        assert "VOLUME_FLOW=6.0" in surf_lines[0]
        assert "HEAT_TRANSFER_COEFFICIENT=0.0" in surf_lines[0]
        zmax_vents = [l for l in result if "&VENT" in l and "Extract_1" in l]
        assert len(zmax_vents) == 1
        assert "SURF_ID='Extract_1'" in zmax_vents[0]
        assert "40,40" in zmax_vents[0]
        corridor_vents = [l for l in result if "&VENT" in l and "Extract Opening" in l]
        assert len(corridor_vents) == 0
        roof_holes = [l for l in result if "&HOLE" in l and "Roof" in l]
        assert len(roof_holes) == 0

    def test_mechanical_shaft_mesh_offset_by_wall_thickness(self):
        """Mechanical shaft mesh is offset by wall_thickness from the opening line."""
        config = {"type": "mechanical", "shaftDepth": 0.9}
        result = create_extract_shaft(self.extract, config, z=10, wall_height=3, stair_enclosure_roof_z=40, wall_thickness=0.2)
        mesh_lines = [l for l in result if "&MESH" in l]
        assert "5.2,6.1" in mesh_lines[0]

    def test_mechanical_has_wall_hole_and_damper(self):
        """Mechanical shaft: HOLE at opening zone, damper OBST for timed activation."""
        config = {"type": "mechanical", "flowRate": 6.0, "activation": "timed", "activationTime": 45, "openingHeight": 1.5, "openingBase": 0.5}
        result = create_extract_shaft(self.extract, config, z=10, wall_height=3, stair_enclosure_roof_z=40, wall_thickness=0.2)
        wall_holes = [l for l in result if "&HOLE" in l and "Extract Wall Hole" in l]
        assert len(wall_holes) == 1
        # HOLE spans only the opening zone, existing corridor wall stays above/below
        assert "10.5" in wall_holes[0]  # opening base z
        assert "12.0" in wall_holes[0]  # opening top z
        damper_obsts = [l for l in result if "&OBST" in l and "Shaft Damper" in l]
        assert len(damper_obsts) == 1
        assert "CTRL_ID='Extract_CTRL_1'" in damper_obsts[0]

    def test_mechanical_timed_has_ctrl_and_devc(self):
        """Mechanical timed: CTRL with INITIAL_STATE, DEVC timer, DEVC_ID on ZMAX vent."""
        config = {"type": "mechanical", "flowRate": 6.0, "activation": "timed", "activationTime": 45}
        result = create_extract_shaft(self.extract, config, z=10, wall_height=3, stair_enclosure_roof_z=40, wall_thickness=0.2)
        ctrl_lines = [l for l in result if "&CTRL" in l]
        assert len(ctrl_lines) == 1
        assert "INITIAL_STATE=.TRUE." in ctrl_lines[0]
        devc_lines = [l for l in result if "&DEVC" in l]
        assert len(devc_lines) == 1
        assert "SETPOINT=45.0" in devc_lines[0]
        zmax_vents = [l for l in result if "&VENT" in l and "Extract_1" in l]
        assert "DEVC_ID='Extract_Timer_1'" in zmax_vents[0]

    def test_mechanical_always_open_no_damper_or_controls(self):
        """Mechanical always_open (FSA): no damper, no CTRL, no DEVC."""
        config = {"type": "mechanical", "flowRate": 6.0, "activation": "always_open"}
        result = create_extract_shaft(self.extract, config, z=10, wall_height=3, stair_enclosure_roof_z=40, wall_thickness=0.2)
        damper_obsts = [l for l in result if "&OBST" in l and "Damper" in l]
        assert len(damper_obsts) == 0
        ctrl_lines = [l for l in result if "&CTRL" in l]
        assert len(ctrl_lines) == 0
        devc_lines = [l for l in result if "&DEVC" in l]
        assert len(devc_lines) == 0
        zmax_vents = [l for l in result if "&VENT" in l and "Extract_1" in l]
        assert "DEVC_ID" not in zmax_vents[0]

    def test_natural_shaft_has_opening_vent(self):
        """Natural shaft: OPEN vent at corridor level."""
        config = {"type": "natural", "shaftWidth": 0.9, "shaftDepth": 0.9}
        result = create_extract_shaft(self.extract, config, z=10, wall_height=3, stair_enclosure_roof_z=40, wall_thickness=0.2)
        opening_vents = [l for l in result if "&VENT" in l and "Extract Opening" in l]
        assert len(opening_vents) == 1

    def test_natural_timed_activation_generates_devc(self):
        config = {"type": "natural", "activation": "timed", "activationTime": 60}
        result = create_extract_shaft(self.extract, config, z=10, wall_height=3, stair_enclosure_roof_z=40, wall_thickness=0.2)
        devc_lines = [l for l in result if "&DEVC" in l]
        assert len(devc_lines) == 1
        assert "SETPOINT=60" in devc_lines[0]

    def test_natural_sprinkler_activation_generates_devc_and_prop(self):
        config = {"type": "natural", "activation": "sprinkler"}
        result = create_extract_shaft(self.extract, config, z=10, wall_height=3, stair_enclosure_roof_z=40, wall_thickness=0.2)
        devc_lines = [l for l in result if "&DEVC" in l]
        prop_lines = [l for l in result if "&PROP" in l]
        assert len(devc_lines) == 1
        assert len(prop_lines) == 1
        assert "Extract_Sprinkler_1" in devc_lines[0]

    def test_natural_custom_opening_dimensions(self):
        """openingHeight and openingBase control the opening VENT Z range."""
        config = {"type": "natural", "openingHeight": 1.6, "openingBase": 0.4}
        result = create_extract_shaft(self.extract, config, z=10, wall_height=3, stair_enclosure_roof_z=40, wall_thickness=0.2)
        opening_vents = [l for l in result if "&VENT" in l and "Extract Opening" in l]
        assert len(opening_vents) == 1
        assert "10.4" in opening_vents[0]
        assert "12.0" in opening_vents[0]

    def test_default_opening_uses_wharf_dimensions(self):
        """Without openingHeight/Base, defaults to Crown Wharf: base=0.9m, height=1.3m."""
        config = {"type": "natural"}
        result = create_extract_shaft(self.extract, config, z=10, wall_height=3, stair_enclosure_roof_z=40, wall_thickness=0.2)
        opening_vents = [l for l in result if "&VENT" in l and "Extract Opening" in l]
        assert "10.9" in opening_vents[0]
        assert "12.2" in opening_vents[0]

    def test_natural_always_open_has_no_controls(self):
        config = {"type": "natural", "activation": "always_open"}
        result = create_extract_shaft(self.extract, config, z=10, wall_height=3, stair_enclosure_roof_z=40, wall_thickness=0.2)
        devc_lines = [l for l in result if "&DEVC" in l]
        assert len(devc_lines) == 0

    def test_integration_extract_in_testfunction(self):
        """Full integration: extract element in testFunction produces shaft lines."""
        elements = [
            {"comments": "obstruction", "id": 0, "points": [
                {"x": 0, "y": 0}, {"x": 100, "y": 0}, {"x": 100, "y": 50},
                {"x": 0, "y": 50}, {"x": 0, "y": 0}
            ], "type": "polyline"},
            {"comments": "mesh", "id": 1, "points": [{"x": 0, "y": 0}, {"x": 100, "y": 50}], "type": "rect"},
            {"comments": "fire", "id": 3, "points": [{"x": 25, "y": 25}], "type": "point"},
            {"comments": "extract", "id": 4, "points": [{"x": 50, "y": 0}, {"x": 50, "y": 10}], "type": "polyline"},
        ]
        result = testFunction(
            elements, z=10, wall_height=3, wall_thickness=0.2,
            stair_height=30, px_per_m=10, fire_floor=2, total_floors=7,
            stair_enclosure_roof_z=40, scenario_type="MOE", sim_end_time=300,
            extract_config={"4": {"type": "natural", "shaftWidth": 0.9, "shaftDepth": 0.9, "activation": "always_open"}},
        )
        assert "Extract_Shaft_1" in result
        assert "Extract Opening 1" in result
        assert "Extract Roof Opening 1" in result
        assert "Mesh Vent: Extract_Shaft_1 [ZMAX]" in result


class TestFDSOutputValidation:
    """Full FDS output validation checklist — catches regressions across all features.

    Uses a realistic element set resembling North Finchley: corridor, stair, doors with
    various roles, mechanical extract, natural extract, inlet, fire.
    """

    def setup_method(self):
        # Realistic element set
        self.elements = [
            # Corridor obstruction
            {"comments": "obstruction", "id": 0, "points": [
                {"x": 0, "y": 0}, {"x": 130, "y": 0}, {"x": 130, "y": 50},
                {"x": 0, "y": 50}, {"x": 0, "y": 0}
            ], "type": "polyline"},
            # Main corridor mesh
            {"comments": "mesh", "id": 1, "points": [{"x": 0, "y": 0}, {"x": 130, "y": 50}], "type": "rect"},
            # Stair mesh
            {"comments": "stair_mesh", "id": 2, "points": [{"x": 10, "y": 50}, {"x": 60, "y": 80}], "type": "rect"},
            # Fire
            {"comments": "fire", "id": 3, "points": [{"x": 80, "y": 25}], "type": "point"},
            # Stair door (controlled, opens at t=0 for FSA)
            {"comments": "door", "id": 10, "points": [{"x": 30, "y": 50}, {"x": 40, "y": 50}], "type": "polyline"},
            # Apartment door (controlled, opens at t=60)
            {"comments": "door", "id": 11, "points": [{"x": 70, "y": 0}, {"x": 80, "y": 0}], "type": "polyline"},
            # Leakage door (smoke sealed)
            {"comments": "door", "id": 12, "points": [{"x": 100, "y": 0}, {"x": 100, "y": 10}], "type": "polyline"},
            # Leakage door (lift)
            {"comments": "door", "id": 13, "points": [{"x": 0, "y": 20}, {"x": 0, "y": 30}], "type": "polyline"},
            # Always open door
            {"comments": "door", "id": 14, "points": [{"x": 50, "y": 50}, {"x": 60, "y": 50}], "type": "polyline"},
            # Mechanical extract
            {"comments": "extract", "id": 20, "points": [{"x": 120, "y": 0}, {"x": 120, "y": 10}], "type": "polyline"},
            # Natural extract
            {"comments": "extract", "id": 21, "points": [{"x": 0, "y": 40}, {"x": 0, "y": 50}], "type": "polyline"},
            # Inlet
            {"comments": "inlet", "id": 30, "points": [{"x": 130, "y": 20}, {"x": 130, "y": 35}], "type": "polyline"},
        ]
        self.door_roles = {
            "10": "stair", "11": "apartment", "12": "leakage",
            "13": "leakage", "14": "always_open"
        }
        self.door_leakage_config = {
            "12": {"doorType": "single_smoke_sealed"},
            "13": {"doorType": "lift"},
        }
        self.extract_config = {
            "20": {"type": "mechanical", "flowRate": 5.0, "tauV": -10, "shaftDepth": 0.9,
                   "openingHeight": 1.3, "openingBase": 0.9, "activation": "always_open"},
            "21": {"type": "natural", "shaftDepth": 0.9, "activation": "always_open"},
        }
        self.inlet_config = {
            "30": {"openingHeight": 2.0, "openingBase": 0.0},
        }
        self.result = testFunction(
            self.elements, z=3.1, wall_height=2.4, wall_thickness=0.2,
            stair_height=12.2, px_per_m=10, fire_floor=1, total_floors=4,
            stair_enclosure_roof_z=12.2, scenario_type="FSA", sim_end_time=300,
            door_roles=self.door_roles,
            door_leakage_config=self.door_leakage_config,
            door_openings={"stair_open": 0, "apartment_open": 60},
            door_leakages_enabled=True,
            extract_config=self.extract_config,
            inlet_config=self.inlet_config,
            fire_hrr=2500, fire_dimension=2.0, fire_type="steady_state",
        )
        self.lines = self.result.split("\n")

    # --- 1. DOORS ---

    def test_stair_door_has_controlled_hole(self):
        holes = [l for l in self.lines if "&HOLE" in l and "Stair Door" in l]
        assert len(holes) >= 1
        assert any("CTRL_ID" in h for h in holes)

    def test_apartment_door_has_controlled_hole(self):
        holes = [l for l in self.lines if "&HOLE" in l and "Apartment Door" in l]
        assert len(holes) >= 1
        assert any("CTRL_ID" in h for h in holes)

    def test_always_open_door_has_hole_no_ctrl(self):
        holes = [l for l in self.lines if "&HOLE" in l and "Always Open" in l]
        assert len(holes) >= 1
        assert all("CTRL_ID" not in h for h in holes)

    def test_leakage_door_has_no_hole(self):
        """Leakage doors should NOT produce a HOLE."""
        holes = [l for l in self.lines if "&HOLE" in l and "Leakage" in l]
        assert len(holes) == 0

    def test_leakage_vents_bottom_only_to_ambient(self):
        """All leakage: single bottom vent, VENT2_ID='AMBIENT', fixed area."""
        hvac_lines = [l for l in self.lines if "&HVAC" in l and "LEAK" in l]
        assert len(hvac_lines) >= 2  # at least the two leakage doors
        for h in hvac_lines:
            assert "VENT2_ID='AMBIENT'" in h
            assert "LEAK_ENTHALPY=.TRUE." in h
        # No top/left/right vents
        top_vents = [l for l in self.lines if "top vent" in l.lower()]
        left_vents = [l for l in self.lines if "left vent" in l.lower()]
        right_vents = [l for l in self.lines if "right vent" in l.lower()]
        assert len(top_vents) == 0
        assert len(left_vents) == 0
        assert len(right_vents) == 0

    def test_lift_door_area_006(self):
        hvac_lines = [l for l in self.lines if "&HVAC" in l and "lift" in l.lower()]
        assert len(hvac_lines) >= 1
        assert "AREA=0.06" in hvac_lines[0]

    def test_smoke_sealed_door_area_001(self):
        hvac_lines = [l for l in self.lines if "&HVAC" in l and "smoke_sealed" in l.lower()]
        assert len(hvac_lines) >= 1
        assert "AREA=0.01" in hvac_lines[0]

    # --- 2. MECHANICAL EXTRACT ---

    def test_mech_extract_surf_at_zmax(self):
        surf_lines = [l for l in self.lines if "&SURF" in l and "Extract_1" in l]
        assert len(surf_lines) == 1
        assert "HEAT_TRANSFER_COEFFICIENT=0.0" in surf_lines[0]
        assert "VOLUME_FLOW=5.0" in surf_lines[0]
        assert "TAU_V=-10" in surf_lines[0]

    def test_mech_extract_fan_vent_at_zmax(self):
        vents = [l for l in self.lines if "&VENT" in l and "Extract_1" in l]
        assert len(vents) == 1
        assert "SURF_ID='Extract_1'" in vents[0]
        # Should be at ZMAX (z values equal)
        xb = vents[0].split("XB=")[1].split("/")[0]
        vals = [float(v) for v in xb.split(",")]
        assert vals[4] == vals[5]  # zmin == zmax = face

    def test_mech_extract_no_corridor_vent(self):
        corridor_vents = [l for l in self.lines if "Extract Opening" in l and "Extract_1" in l]
        assert len(corridor_vents) == 0

    def test_mech_extract_no_roof_hole(self):
        roof_holes = [l for l in self.lines if "&HOLE" in l and "Extract Roof" in l]
        # Only natural shaft should have a roof hole
        for h in roof_holes:
            assert "Extract_Shaft_1" not in h  # mechanical shaft shouldn't have one

    def test_mech_extract_wall_hole_exists(self):
        wall_holes = [l for l in self.lines if "&HOLE" in l and "Extract Wall Hole" in l]
        assert len(wall_holes) >= 1

    def test_mech_extract_always_open_no_damper(self):
        dampers = [l for l in self.lines if "Shaft Damper" in l]
        assert len(dampers) == 0  # always_open = no damper

    def test_mech_extract_opening_not_full_wall(self):
        """Opening should use configured dimensions, not default to full wall height."""
        wall_holes = [l for l in self.lines if "&HOLE" in l and "Extract Wall Hole" in l]
        assert len(wall_holes) >= 1
        # The hole should NOT span full wall height (3.1 to 5.5)
        for h in wall_holes:
            xb = h.split("XB=")[1].split("/")[0]
            vals = [float(v) for v in xb.split(",")]
            z_range = vals[5] - vals[4]
            assert z_range < 2.4, f"Opening z_range {z_range} looks like full wall height"

    # --- 3. NATURAL EXTRACT ---

    def test_natural_extract_has_open_vent(self):
        opening_vents = [l for l in self.lines if "Extract Opening 2" in l]
        assert len(opening_vents) == 1
        assert "SURF_ID='OPEN'" in opening_vents[0]

    def test_natural_extract_has_roof_hole(self):
        roof_holes = [l for l in self.lines if "Extract Roof Opening 2" in l]
        assert len(roof_holes) == 1

    def test_natural_extract_no_surf(self):
        surf_lines = [l for l in self.lines if "&SURF" in l and "Extract_2" in l]
        assert len(surf_lines) == 0

    # --- 4. MESHES ---

    def test_meshes_exist(self):
        mesh_lines = [l for l in self.lines if l.strip().startswith("&MESH")]
        assert len(mesh_lines) >= 2  # at least corridor + stair

    def test_no_overlapping_mesh_boundaries(self):
        """Adjacent meshes should abut, not overlap."""
        mesh_lines = [l for l in self.lines if l.strip().startswith("&MESH")]
        meshes = []
        for line in mesh_lines:
            xb_match = line.split("XB=")
            if len(xb_match) < 2:
                continue
            vals = [float(v) for v in xb_match[1].split("/")[0].split(",")]
            meshes.append(vals)
        # Check no two meshes fully contain each other in XY
        for i, a in enumerate(meshes):
            for j, b in enumerate(meshes):
                if i >= j:
                    continue
                x_contains = a[0] <= b[0] and a[1] >= b[1]
                y_contains = a[2] <= b[2] and a[3] >= b[3]
                z_same = abs(a[4] - b[4]) < 0.01 and abs(a[5] - b[5]) < 0.01
                assert not (x_contains and y_contains and z_same), f"Mesh {i} contains mesh {j}"

    # --- 5. FIRE ---

    def test_fire_obst_exists(self):
        fire_obsts = [l for l in self.lines if "&OBST" in l and "Fire" in l]
        assert len(fire_obsts) >= 1

    def test_fire_surf_exists(self):
        fire_surfs = [l for l in self.lines if "&SURF" in l and "Fire" in l]
        assert len(fire_surfs) == 1
        # HRRPUA may be on next line (multiline SURF)
        assert "HRRPUA" in self.result

    # --- 6. GENERAL ---

    def test_head_time_comb_present(self):
        assert any("&HEAD" in l for l in self.lines)
        assert any("&TIME" in l for l in self.lines)
        assert any("&COMB" in l for l in self.lines)

    def test_plasterboard_surf_defined(self):
        assert any("Plasterboard" in l and "&SURF" in l for l in self.lines)

    def test_reac_spec_present(self):
        assert any("&REAC" in l for l in self.lines)
        assert any("&SPEC" in l for l in self.lines)
