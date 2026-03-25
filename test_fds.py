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
        """Verify create_stair_aov produces a HOLE line at roughly the right location."""
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
        assert len(result) == 1
        assert "&HOLE ID='AOV'" in result[0]
        # Default mode is always_open — no CTRL_ID
        assert "CTRL_ID" not in result[0]
        # Z range: roof_z - 0.4 to roof_z + 0.4
        assert "20.6" in result[0]
        assert "21.4" in result[0]

    def test_aov_timed_has_ctrl_id(self):
        """When mode is timed, AOV should have CTRL_ID."""
        elements = [
            {"comments": "landing", "id": 0, "points": [
                {"x": 1.0, "y": 1.0}, {"x": 3.0, "y": 3.0}
            ], "type": "polyline"},
        ]
        result = create_stair_aov(elements, 21.0, aov_mode="timed")
        assert "CTRL_ID='Extract Vent1'" in result[0]

    def test_aov_sprinkler_has_ctrl_id(self):
        """When mode is sprinkler, AOV should have CTRL_ID."""
        elements = [
            {"comments": "landing", "id": 0, "points": [
                {"x": 1.0, "y": 1.0}, {"x": 3.0, "y": 3.0}
            ], "type": "polyline"},
        ]
        result = create_stair_aov(elements, 21.0, aov_mode="sprinkler")
        assert "CTRL_ID='Extract Vent1'" in result[0]

    def test_aov_1m_square(self):
        """Verify the AOV hole is 1m x 1m."""
        elements = [
            {"comments": "landing", "id": 0, "points": [
                {"x": 2.0, "y": 2.0}, {"x": 4.0, "y": 2.0},
                {"x": 4.0, "y": 4.0}, {"x": 2.0, "y": 4.0}, {"x": 2.0, "y": 2.0}
            ], "type": "polyline"},
        ]
        roof_z = 10.0
        result = create_stair_aov(elements, roof_z, cell_size=0.2)
        line = result[0]
        # Parse the XB values from the line
        xb_part = line.split("XB = ")[1].rstrip("/").rstrip()
        vals = [float(v.strip()) for v in xb_part.split(",")]
        x1, x2, y1, y2, z1, z2 = vals
        assert abs((x2 - x1) - 1.0) < 0.01
        assert abs((y2 - y1) - 1.0) < 0.01

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

    # --- LEAK_ENTHALPY ---

    def test_hvac_always_has_leak_enthalpy(self):
        """All HVAC lines should include LEAK_ENTHALPY=.TRUE."""
        door = self.elements[0]
        result = generate_door_leakage_vents(
            door, door_index=0, z=10, seal_type="non-smoke-sealed"
        )
        hvac_lines = [l for l in result if "&HVAC" in l]
        for line in hvac_lines:
            assert "LEAK_ENTHALPY=.TRUE." in line

    # --- Naming convention ---

    def test_prefix_from_seal_type(self):
        """Seal type determines prefix: smoke_sealed or nonsmoke_sealed."""
        door = self.elements[0]
        result_smoke = generate_door_leakage_vents(
            door, door_index=0, z=10, seal_type="smoke-sealed"
        )
        result_nonsmoke = generate_door_leakage_vents(
            door, door_index=0, z=10, seal_type="non-smoke-sealed"
        )
        hvac_smoke = [l for l in result_smoke if "&HVAC" in l][0]
        hvac_nonsmoke = [l for l in result_nonsmoke if "&HVAC" in l][0]
        assert "smoke_sealed" in hvac_smoke
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

    def test_natural_shaft_has_open_top_vent(self):
        config = {"type": "natural", "shaftWidth": 0.9, "shaftDepth": 0.9}
        result = create_extract_shaft(self.extract, config, z=10, wall_height=3, stair_enclosure_roof_z=40, wall_thickness=0.2)
        vent_lines = [l for l in result if "&VENT" in l and "OPEN" in l]
        assert len(vent_lines) == 1
        assert "Extract Top 1" in vent_lines[0]

    def test_natural_shaft_has_no_surf(self):
        config = {"type": "natural"}
        result = create_extract_shaft(self.extract, config, z=10, wall_height=3, stair_enclosure_roof_z=40, wall_thickness=0.2)
        surf_lines = [l for l in result if "&SURF" in l]
        assert len(surf_lines) == 0

    def test_mechanical_shaft_has_surf_and_vent(self):
        config = {"type": "mechanical", "flowRate": 6.0, "shaftWidth": 0.9, "shaftDepth": 0.9}
        result = create_extract_shaft(self.extract, config, z=10, wall_height=3, stair_enclosure_roof_z=40, wall_thickness=0.2)
        surf_lines = [l for l in result if "&SURF" in l]
        assert len(surf_lines) == 1
        assert "VOLUME_FLOW=6.0" in surf_lines[0]
        vent_lines = [l for l in result if "&VENT" in l]
        assert len(vent_lines) == 1
        assert "Extract_1" in vent_lines[0]

    def test_shaft_has_opening_hole(self):
        config = {"type": "natural", "shaftWidth": 0.9, "shaftDepth": 0.9}
        result = create_extract_shaft(self.extract, config, z=10, wall_height=3, stair_enclosure_roof_z=40, wall_thickness=0.2)
        hole_lines = [l for l in result if "&HOLE" in l]
        assert len(hole_lines) == 1
        assert "Extract Opening 1" in hole_lines[0]

    def test_timed_activation_generates_devc(self):
        config = {"type": "natural", "activation": "timed", "activationTime": 60}
        result = create_extract_shaft(self.extract, config, z=10, wall_height=3, stair_enclosure_roof_z=40, wall_thickness=0.2)
        devc_lines = [l for l in result if "&DEVC" in l]
        assert len(devc_lines) == 1
        assert "SETPOINT=60" in devc_lines[0]
        # HOLE should reference the timer
        hole_lines = [l for l in result if "&HOLE" in l]
        assert "Extract_Timer_1" in hole_lines[0]

    def test_sprinkler_activation_generates_devc_and_prop(self):
        config = {"type": "natural", "activation": "sprinkler"}
        result = create_extract_shaft(self.extract, config, z=10, wall_height=3, stair_enclosure_roof_z=40, wall_thickness=0.2)
        devc_lines = [l for l in result if "&DEVC" in l]
        prop_lines = [l for l in result if "&PROP" in l]
        assert len(devc_lines) == 1
        assert len(prop_lines) == 1
        assert "Extract_Sprinkler_1" in devc_lines[0]

    def test_custom_opening_dimensions(self):
        """openingHeight and openingBase control the HOLE Z range."""
        config = {"type": "natural", "openingHeight": 1.6, "openingBase": 0.4}
        result = create_extract_shaft(self.extract, config, z=10, wall_height=3, stair_enclosure_roof_z=40, wall_thickness=0.2)
        hole_lines = [l for l in result if "&HOLE" in l]
        assert len(hole_lines) == 1
        # z=10, base=0.4, height=1.6 -> hole from 10.4 to 12.0
        assert "10.4" in hole_lines[0]
        assert "12.0" in hole_lines[0]

    def test_default_opening_uses_full_wall_height(self):
        """Without openingHeight/Base, HOLE spans full wall height."""
        config = {"type": "natural"}
        result = create_extract_shaft(self.extract, config, z=10, wall_height=3, stair_enclosure_roof_z=40, wall_thickness=0.2)
        hole_lines = [l for l in result if "&HOLE" in l]
        # z=10, base=0, height=wall_height=3 -> hole from 10.0 to 13.0
        assert "10.0" in hole_lines[0] or "10," in hole_lines[0]
        assert "13.0" in hole_lines[0]

    def test_always_open_has_no_controls(self):
        config = {"type": "natural", "activation": "always_open"}
        result = create_extract_shaft(self.extract, config, z=10, wall_height=3, stair_enclosure_roof_z=40, wall_thickness=0.2)
        devc_lines = [l for l in result if "&DEVC" in l]
        assert len(devc_lines) == 0
        hole_lines = [l for l in result if "&HOLE" in l]
        assert "DEVC_ID" not in hole_lines[0]

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
        assert "Extract Top 1" in result
