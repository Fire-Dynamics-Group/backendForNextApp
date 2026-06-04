"""Characterization + unit tests around time_eq geometry.

The characterization tests pin the *current* behaviour of compute_time_eq on a fixed
mock compartment so the upcoming derive_geometry() extraction can be proven to change
nothing. The TestDeriveGeometry tests drive that extraction (red until it exists).
"""
import io
import re
import contextlib
import math
from types import SimpleNamespace as NS

import matplotlib
matplotlib.use("Agg")  # headless; must precede time_eq's pyplot import

import pytest

import time_eq


def _p(x, y):
    return NS(x=x, y=y)


def make_mock():
    """The mock compartment from time_eq.__main__: one obstruction + two openings."""
    return [
        NS(id=0, comments="obstruction", finalPoints=[
            _p(0.2, 0.0), _p(0.2, 5.2), _p(0.0, 5.2), _p(0.0, 5.8), _p(9.7, 5.8),
            _p(9.7, 5.6), _p(10.0, 5.6), _p(10.0, 2.4), _p(10.4, 2.4), _p(10.4, 0.1),
            _p(7.3, 0.1), _p(7.3, 0.0), _p(0.2, 0.0)]),
        NS(id=1, comments="opening", finalPoints=[_p(10.0, 5.5), _p(10.0, 4.2)]),
        NS(id=2, comments="opening", finalPoints=[_p(10.4, 2.4), _p(10.4, 0.1)]),
    ]


MOCK_ROOM_COMPOSITION = ["concrete"] * 15
MOCK_OPENING_HEIGHTS = [1.5, 1.5]
COMPARTMENT_HEIGHT = 3.15  # compute_time_eq default


class TestComputeTimeEqCharacterization:
    """End-to-end golden values for the deterministic calc. These must not move."""

    def _run_capture(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            img = time_eq.compute_time_eq(
                data=make_mock(),
                opening_heights=MOCK_OPENING_HEIGHTS,
                room_composition=MOCK_ROOM_COMPOSITION,
            )
        return img, buf.getvalue()

    def test_returns_nonempty_jpeg(self):
        img, _ = self._run_capture()
        assert isinstance(img, (bytes, bytearray)) and len(img) > 1000

    def test_bvalue_weighted(self):
        _, out = self._run_capture()
        m = re.search(r"bvalue weighted = ([\d.]+)", out)
        assert m, out
        assert float(m.group(1)) == pytest.approx(1741.61993557722, rel=1e-9)

    def test_protection_thickness(self):
        _, out = self._run_capture()
        m = re.search(r"thickness ([\d.]+)", out)
        assert m, out
        assert float(m.group(1)) == pytest.approx(19.6, abs=0.05)

    def test_time_equivalence(self):
        _, out = self._run_capture()
        m = re.search(r"time equivalency value = ([\d.]+) minutes", out)
        assert m, out
        assert float(m.group(1)) == pytest.approx(101.0, abs=1e-9)


class TestDeriveGeometry:
    """Drives extraction of time_eq.derive_geometry() — the obstruction-derived geometry
    shared by the deterministic and Monte Carlo reliability calcs."""

    def test_floor_area_and_At(self):
        geo = time_eq.derive_geometry(make_mock(), COMPARTMENT_HEIGHT)
        assert geo.floor_area == pytest.approx(57.55, abs=1e-6)
        assert geo.At == pytest.approx(217.16, abs=1e-6)

    def test_wall_segments(self):
        geo = time_eq.derive_geometry(make_mock(), COMPARTMENT_HEIGHT)
        assert len(geo.wall_lengths) == 12
        assert sum(geo.wall_lengths) == pytest.approx(32.4, abs=1e-6)

    def test_room_dimensions_structure(self):
        """room_dimensions = [floor_area, *wall_dimensions, floor_area]; wall_dim = len*height."""
        geo = time_eq.derive_geometry(make_mock(), COMPARTMENT_HEIGHT)
        assert geo.room_dimensions[0] == pytest.approx(geo.floor_area)
        assert geo.room_dimensions[-1] == pytest.approx(geo.floor_area)
        assert len(geo.room_dimensions) == len(geo.wall_lengths) + 2
        for length, dim in zip(geo.wall_lengths, geo.room_dimensions[1:-1]):
            assert dim == pytest.approx(length * COMPARTMENT_HEIGHT)
        assert geo.At == pytest.approx(sum(geo.room_dimensions))
