"""Tests for generate_slice_lines() - SLCF generation for FDS output."""
import pytest
from fds import generate_slice_lines


# -- Helpers to build mock elements --

def make_element(comments, points, el_id=1):
    return {"comments": comments, "id": el_id, "points": [{"x": p[0], "y": p[1]} for p in points], "type": "line"}


def make_fire(x, y):
    return make_element("fire", [(x, y)], el_id=100)


def make_door(p1, p2, el_id=200):
    return make_element("door", [p1, p2], el_id=el_id)


def make_obstruction(points, el_id=300):
    """Closed polygon obstruction."""
    return make_element("obstruction", points, el_id=el_id)


def make_extract(p1, p2, el_id=400):
    return make_element("extract", [p1, p2], el_id=el_id)


# -- Fixtures --

@pytest.fixture
def basic_elements():
    """Simple layout: corridor (10m x 2m), fire at (5,1), stair door, apt door, extract."""
    corridor = make_obstruction([(0, 0), (10, 0), (10, 2), (0, 2), (0, 0)], el_id=1)
    fire = make_fire(5.0, 1.0)
    stair_door = make_door((0, 0.5), (0, 1.5), el_id=10)   # vertical door on left wall -> PBX slice
    apt_door = make_door((8, 2), (9, 2), el_id=11)          # horizontal door on top wall -> PBY slice
    extract = make_extract((0.5, 0.5), (1.5, 0.5), el_id=20)
    return [corridor, fire, stair_door, apt_door, extract]


@pytest.fixture
def basic_zone_config():
    """Corridor zone with slices and sensors enabled."""
    return {
        "1": {
            "type": "corridor",
            "name": "Main Corridor",
            "slices": True,
            "sensors": True,
            "points": [{"x": 0, "y": 0}, {"x": 10, "y": 0}, {"x": 10, "y": 2}, {"x": 0, "y": 2}]
        }
    }


@pytest.fixture
def door_roles():
    return {"10": "stair", "11": "apartment"}


# -- Tests --

class TestSliceLineGeneration:
    """Core slice generation tests."""

    def test_returns_list_of_strings(self, basic_elements, basic_zone_config, door_roles):
        result = generate_slice_lines(basic_elements, z=10.0, wall_height=2.5,
                                       door_roles=door_roles, zone_config=basic_zone_config)
        assert isinstance(result, list)
        assert all(isinstance(line, str) for line in result)

    def test_all_lines_are_slcf(self, basic_elements, basic_zone_config, door_roles):
        result = generate_slice_lines(basic_elements, z=10.0, wall_height=2.5,
                                       door_roles=door_roles, zone_config=basic_zone_config)
        assert len(result) > 0
        for line in result:
            assert line.startswith("&SLCF")

    def test_four_quantities_per_position(self, basic_elements, basic_zone_config, door_roles):
        result = generate_slice_lines(basic_elements, z=10.0, wall_height=2.5,
                                       door_roles=door_roles, zone_config=basic_zone_config)
        # Each unique position should produce exactly 4 lines
        assert len(result) % 4 == 0

    def test_quantities_present(self, basic_elements, basic_zone_config, door_roles):
        result = generate_slice_lines(basic_elements, z=10.0, wall_height=2.5,
                                       door_roles=door_roles, zone_config=basic_zone_config)
        joined = "\n".join(result)
        assert "TEMPERATURE" in joined
        assert "VISIBILITY" in joined
        assert "VELOCITY" in joined
        assert "PRESSURE" in joined

    def test_velocity_has_vector(self, basic_elements, basic_zone_config, door_roles):
        result = generate_slice_lines(basic_elements, z=10.0, wall_height=2.5,
                                       door_roles=door_roles, zone_config=basic_zone_config)
        vel_lines = [l for l in result if "VELOCITY" in l]
        assert len(vel_lines) > 0
        for line in vel_lines:
            assert "VECTOR=.TRUE." in line


class TestZSlice:
    """Z slice at configurable height above fire floor."""

    def test_z_slice_default_2m(self, basic_elements, basic_zone_config, door_roles):
        result = generate_slice_lines(basic_elements, z=10.0, wall_height=2.5,
                                       door_roles=door_roles, zone_config=basic_zone_config)
        pbz_lines = [l for l in result if "PBZ=" in l]
        assert len(pbz_lines) >= 4  # 4 quantities at z=12.0
        assert any("PBZ=12.0" in l for l in pbz_lines)

    def test_z_slice_custom_height(self, basic_elements, basic_zone_config, door_roles):
        result = generate_slice_lines(basic_elements, z=10.0, wall_height=2.5,
                                       door_roles=door_roles, zone_config=basic_zone_config,
                                       slice_z_height=1.5)
        pbz_lines = [l for l in result if "PBZ=" in l]
        assert any("PBZ=11.5" in l for l in pbz_lines)


class TestFireSlices:
    """Slices through fire centre X and Y."""

    def test_fire_x_slice(self, basic_elements, basic_zone_config, door_roles):
        result = generate_slice_lines(basic_elements, z=10.0, wall_height=2.5,
                                       door_roles=door_roles, zone_config=basic_zone_config)
        pbx_lines = [l for l in result if "PBX=" in l]
        assert any("PBX=5.0" in l for l in pbx_lines)

    def test_fire_y_slice(self, basic_elements, basic_zone_config, door_roles):
        result = generate_slice_lines(basic_elements, z=10.0, wall_height=2.5,
                                       door_roles=door_roles, zone_config=basic_zone_config)
        pby_lines = [l for l in result if "PBY=" in l]
        assert any("PBY=1.0" in l for l in pby_lines)


class TestFireRoomSlices:
    """Slices through fire room enclosed area midpoint."""

    def test_fire_room_zone_midpoint(self):
        """Fire room zone should produce slices through the enclosed area midpoint."""
        fire_room = make_obstruction([(0, 0), (4, 0), (4, 3), (0, 3), (0, 0)], el_id=50)
        fire = make_fire(2.0, 1.5)
        zone_config = {
            "50": {
                "type": "fire_room",
                "name": "Fire Room",
                "slices": True,
                "sensors": False,
                "points": [{"x": 0, "y": 0}, {"x": 4, "y": 0}, {"x": 4, "y": 3}, {"x": 0, "y": 3}]
            }
        }
        result = generate_slice_lines([fire_room, fire], z=10.0, wall_height=2.5,
                                       door_roles={}, zone_config=zone_config)
        pbx_lines = [l for l in result if "PBX=" in l]
        pby_lines = [l for l in result if "PBY=" in l]
        # Midpoint of fire room: X=2.0, Y=1.5
        assert any("PBX=2.0" in l for l in pbx_lines)
        assert any("PBY=1.5" in l for l in pby_lines)


class TestDoorSlices:
    """Slices through door centres on perpendicular axis."""

    def test_stair_door_perpendicular_slice(self, basic_elements, basic_zone_config, door_roles):
        """Vertical stair door (x=0, y 0.5->1.5) should create PBX slice at x=0."""
        result = generate_slice_lines(basic_elements, z=10.0, wall_height=2.5,
                                       door_roles=door_roles, zone_config=basic_zone_config)
        pbx_lines = [l for l in result if "PBX=" in l]
        assert any("PBX=0.0" in l or "PBX=0/" in l for l in pbx_lines)

    def test_apt_door_perpendicular_slice(self, basic_elements, basic_zone_config, door_roles):
        """Horizontal apt door (y=2, x 8->9) should create PBY slice at y=2."""
        result = generate_slice_lines(basic_elements, z=10.0, wall_height=2.5,
                                       door_roles=door_roles, zone_config=basic_zone_config)
        pby_lines = [l for l in result if "PBY=" in l]
        assert any("PBY=2.0" in l for l in pby_lines)


class TestCorridorCentreSlices:
    """Slices through corridor zone centre."""

    def test_corridor_centre_x(self, basic_elements, basic_zone_config, door_roles):
        """Corridor 0-10m in X, centre at X=5."""
        result = generate_slice_lines(basic_elements, z=10.0, wall_height=2.5,
                                       door_roles=door_roles, zone_config=basic_zone_config)
        pbx_lines = [l for l in result if "PBX=" in l]
        assert any("PBX=5.0" in l for l in pbx_lines)

    def test_corridor_centre_y(self, basic_elements, basic_zone_config, door_roles):
        """Corridor 0-2m in Y, centre at Y=1."""
        result = generate_slice_lines(basic_elements, z=10.0, wall_height=2.5,
                                       door_roles=door_roles, zone_config=basic_zone_config)
        pby_lines = [l for l in result if "PBY=" in l]
        assert any("PBY=1.0" in l for l in pby_lines)


class TestLobbySlices:
    """Lobby zones get slices by default."""

    def test_lobby_centre_slices(self):
        lobby = make_obstruction([(0, 0), (3, 0), (3, 4), (0, 4), (0, 0)], el_id=60)
        zone_config = {
            "60": {
                "type": "lobby",
                "name": "Lobby 1",
                "slices": True,
                "sensors": True,
                "points": [{"x": 0, "y": 0}, {"x": 3, "y": 0}, {"x": 3, "y": 4}, {"x": 0, "y": 4}]
            }
        }
        result = generate_slice_lines([lobby], z=10.0, wall_height=2.5,
                                       door_roles={}, zone_config=zone_config)
        pbx_lines = [l for l in result if "PBX=" in l]
        pby_lines = [l for l in result if "PBY=" in l]
        # Lobby centre: X=1.5, Y=2.0
        assert any("PBX=1.5" in l for l in pbx_lines)
        assert any("PBY=2.0" in l for l in pby_lines)


class TestZoneSlicesFlag:
    """Only zones with slices=True get slice planes."""

    def test_zone_with_slices_false_excluded(self):
        corridor = make_obstruction([(0, 0), (10, 0), (10, 2), (0, 2), (0, 0)], el_id=1)
        zone_config = {
            "1": {
                "type": "other",
                "name": "Store Room",
                "slices": False,
                "sensors": False,
                "points": [{"x": 0, "y": 0}, {"x": 10, "y": 0}, {"x": 10, "y": 2}, {"x": 0, "y": 2}]
            }
        }
        result = generate_slice_lines([corridor], z=10.0, wall_height=2.5,
                                       door_roles={}, zone_config=zone_config)
        # No zone centre slices should be generated (fire slices still possible but no fire element)
        zone_pbx = [l for l in result if "PBX=5.0" in l]
        assert len(zone_pbx) == 0


class TestDeduplication:
    """Duplicate slice positions should be collapsed."""

    def test_no_duplicate_positions(self, basic_elements, basic_zone_config, door_roles):
        result = generate_slice_lines(basic_elements, z=10.0, wall_height=2.5,
                                       door_roles=door_roles, zone_config=basic_zone_config)
        # Extract (axis, position) pairs
        positions = []
        for line in result:
            if "TEMPERATURE" in line:  # Only check one quantity to count unique positions
                positions.append(line.split("PB")[1] if "PB" in line else "")
        assert len(positions) == len(set(positions))


class TestExtractSlices:
    """Slices through extract/AOV midpoint."""

    def test_extract_midpoint_slices(self, basic_elements, basic_zone_config, door_roles):
        """Extract from (0.5,0.5) to (1.5,0.5) — midpoint X=1.0, Y=0.5."""
        result = generate_slice_lines(basic_elements, z=10.0, wall_height=2.5,
                                       door_roles=door_roles, zone_config=basic_zone_config)
        pbx_lines = [l for l in result if "PBX=" in l]
        pby_lines = [l for l in result if "PBY=" in l]
        assert any("PBX=1.0" in l for l in pbx_lines)
        assert any("PBY=0.5" in l for l in pby_lines)


class TestEmptyInputs:
    """Edge cases with missing data."""

    def test_no_elements_still_has_z_slice(self):
        """Even with no elements, the Z slice is always generated."""
        result = generate_slice_lines([], z=10.0, wall_height=2.5,
                                       door_roles={}, zone_config={})
        assert len(result) == 4  # 4 quantities at Z slice only
        assert all("PBZ=" in l for l in result)

    def test_no_zone_config_still_generates_fire_and_door_slices(self):
        fire = make_fire(5.0, 1.0)
        door = make_door((0, 0.5), (0, 1.5), el_id=10)
        result = generate_slice_lines([fire, door], z=10.0, wall_height=2.5,
                                       door_roles={"10": "stair"}, zone_config={})
        assert len(result) > 0
        assert any("PBX=5.0" in l for l in result)  # fire X
