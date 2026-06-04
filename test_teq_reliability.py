"""Tests for the Monte Carlo reliability engine.

The protection-thickness sizing is deterministic (no sampling) and the source's quirks do
not touch it, so it is an EXACT parity gate against Panattoni_reliability.xlsx. Reliability
itself is stochastic and the source has fidelity quirks, so it is checked for sane shape only.
"""
import numpy as np
import pytest

import teq_reliability as tr

# Panattoni compartment (the config that generated Panattoni_reliability.xlsx)
PANATTONI = dict(
    occupancy="Office",
    floor_area=64 * 13,                 # 832
    total_area=2 * (64 * 3.5) + 2 * (13 * 3.5) + 2 * (64 * 13),  # 2203
    vent_widths=[0, 0, 64, 0],
    vent_heights=[0, 0, 3.5, 0],
)

# FR period -> protection thickness (mm), read from Panattoni_reliability.xlsx sheet1
PANATTONI_THICKNESS = {
    10: 2, 15: 3, 20: 4, 25: 6, 30: 7, 35: 9, 40: 10, 45: 11,
    46: 12, 50: 13, 60: 16, 70: 19, 80: 22, 90: 25,
}


class TestProtectionThicknessParity:
    """Default SteelParams == Panattoni steel config; sizing must match the workbook exactly."""

    @pytest.mark.parametrize("fr,expected_mm", sorted(PANATTONI_THICKNESS.items()))
    def test_thickness_matches_panattoni(self, fr, expected_mm):
        assert tr.calc_prot_thickness_mm(fr, tr.SteelParams()) == expected_mm

    def test_thickness_monotonic(self):
        frs = sorted(PANATTONI_THICKNESS)
        thicks = [tr.calc_prot_thickness_mm(fr, tr.SteelParams()) for fr in frs]
        assert thicks == sorted(thicks)


class TestUnits:
    def test_opening_factor_clamped(self):
        # huge opening -> clamps at 0.2; zero openable area -> 0.01
        of = tr.calc_op_fac([64], [3.5], 2203, np.array([1.0, 0.5, 0.01]))
        assert of.max() <= 0.2 and of.min() >= 0.01
        assert np.allclose(tr.calc_op_fac([0], [0], 2203, np.array([0.5])), 0.01)

    def test_sample_distribution_gumbel_monotone(self):
        u = np.array([0.1, 0.5, 0.9])
        vals = tr.sample_distribution(u, "Gumbel", 420, 420 * 0.3)
        assert np.all(np.diff(vals) > 0)        # ppf increasing in u
        assert vals.min() > 0

    def test_factorise_in_range(self):
        rng = np.random.default_rng(0)
        out = tr.factorise_opening_percentage(np.array([0.2, 0.8, 1.5, 3.0]), rng)
        assert np.all(out <= 1.0)


class TestReliability:
    """Stochastic — checked for sane shape, not exact Panattoni values (source quirks + seed)."""

    def _run(self, fr, n_sim=2000, seed=42):
        return tr.compute_reliability(
            **PANATTONI, fr_period_min=fr, n_sim=n_sim,
            combustion_factor=1.0, is_sprinklered=False, seed=seed,
        )

    def test_bounds_and_thickness(self):
        r = self._run(60)
        assert 0.0 <= r.reliability <= 1.0
        assert r.n_failed + round(r.reliability * r.n_sim) == r.n_sim
        assert r.protection_thickness_mm == 16        # Panattoni FR60

    def test_monotonic_in_fr(self):
        rels = [self._run(fr).reliability for fr in (30, 60, 90)]
        assert rels[0] < rels[1] < rels[2]
        assert rels[2] > 0.8                          # high FR -> high reliability
