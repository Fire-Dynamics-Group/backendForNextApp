"""Tests for the convergence-study stats/batching logic (scripts/convergence_study.py).

The study itself is an offline script (issue #13); these tests cover the pure logic —
summary statistics, the analytic binomial overlay, seed derivation, the recommendation
rule, and the sweep orchestration (via a stub engine, no Monte Carlo compute).
"""
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "scripts"))
import convergence_study as cs


class TestSummarize:
    def test_known_values(self):
        s = cs.summarize([0.90, 0.92, 0.94, 0.96, 0.98])
        assert s["k"] == 5
        assert s["mean"] == pytest.approx(0.94)
        assert s["min"] == 0.90 and s["max"] == 0.98
        assert s["std"] == pytest.approx(np.std([0.90, 0.92, 0.94, 0.96, 0.98], ddof=1))

    def test_percentile_band(self):
        vals = np.linspace(0.0, 1.0, 1001)  # p2.5 = 0.025, p97.5 = 0.975
        s = cs.summarize(vals)
        assert s["p2_5"] == pytest.approx(0.025)
        assert s["p97_5"] == pytest.approx(0.975)
        assert s["band_half_width"] == pytest.approx((0.975 - 0.025) / 2)

    def test_constant_values_zero_band(self):
        s = cs.summarize([0.5, 0.5, 0.5])
        assert s["band_half_width"] == 0.0
        assert s["std"] == 0.0

    def test_envelope_half_width(self):
        s = cs.summarize([0.90, 0.92, 0.94, 0.96, 0.98])
        assert s["envelope_half_width"] == pytest.approx((0.98 - 0.90) / 2)


class TestAnalyticSe:
    def test_half_at_100(self):
        assert cs.analytic_se(0.5, 100) == pytest.approx(0.05)

    def test_degenerate_p(self):
        assert cs.analytic_se(0.0, 1000) == 0.0
        assert cs.analytic_se(1.0, 1000) == 0.0

    def test_shrinks_with_n(self):
        assert cs.analytic_se(0.9, 10000) < cs.analytic_se(0.9, 100)


class TestSeedFor:
    def test_deterministic(self):
        assert cs.seed_for(42, 2000, 7) == cs.seed_for(42, 2000, 7)

    def test_unique_across_grid(self):
        seeds = {cs.seed_for(42, n, k)
                 for n in (100, 500, 1000, 2000, 5000, 10000, 50000)
                 for k in range(100)}
        assert len(seeds) == 7 * 100

    def test_base_seed_shifts(self):
        assert cs.seed_for(1, 100, 0) != cs.seed_for(2, 100, 0)


class TestRecommendN:
    """The acceptance rule runs on the min-max envelope (the CFDOpenPlan-appendix
    measure, wider than the percentile band, so conservative)."""

    def test_picks_smallest_qualifying(self):
        stats = {100: {"envelope_half_width": 0.04}, 1000: {"envelope_half_width": 0.009},
                 5000: {"envelope_half_width": 0.003}}
        assert cs.recommend_n(stats, tol=0.01) == 1000

    def test_none_when_no_n_qualifies(self):
        stats = {100: {"envelope_half_width": 0.04}, 1000: {"envelope_half_width": 0.02}}
        assert cs.recommend_n(stats, tol=0.005) is None

    def test_unsorted_input(self):
        stats = {5000: {"envelope_half_width": 0.003}, 500: {"envelope_half_width": 0.008}}
        assert cs.recommend_n(stats, tol=0.01) == 500

    def test_falls_back_to_min_max_for_older_results(self):
        # JSONs written before envelope_half_width existed still carry min/max
        stats = {100: {"min": 0.90, "max": 0.94}, 1000: {"min": 0.917, "max": 0.923}}
        assert cs.recommend_n(stats, tol=0.005) == 1000


class TestRunStudy:
    """Sweep orchestration against a stub engine — checks the calls made and the
    aggregation, without any Monte Carlo compute."""

    def _stub_engine(self, calls):
        def engine(*, fr_period_min, n_sim, seed, **kwargs):
            calls.append((fr_period_min, n_sim, seed))
            # deterministic fake reliability that varies with seed so std > 0
            class R:
                reliability = 0.9 + (seed % 10) * 1e-4
            return R()
        return engine

    def test_call_grid_and_aggregation(self):
        calls = []
        out = cs.run_study(fr_periods=[35, 60], schedule={100: 3, 500: 2},
                           base_seed=42, engine=self._stub_engine(calls))
        # one call per (fr, n, k)
        assert len(calls) == 2 * (3 + 2)
        # every n_sim ran with K distinct seeds
        seeds_100 = [s for fr, n, s in calls if n == 100 and fr == 35]
        assert len(set(seeds_100)) == 3
        # aggregated stats present for each fr/n with correct K
        assert out["results"]["35"]["100"]["k"] == 3
        assert out["results"]["60"]["500"]["k"] == 2
        assert 0.89 < out["results"]["35"]["100"]["mean"] < 0.91

    def test_reproducible(self):
        out1 = cs.run_study(fr_periods=[60], schedule={100: 2}, base_seed=7,
                            engine=self._stub_engine([]))
        out2 = cs.run_study(fr_periods=[60], schedule={100: 2}, base_seed=7,
                            engine=self._stub_engine([]))
        assert out1["results"] == out2["results"]

    def test_metadata_recorded(self):
        out = cs.run_study(fr_periods=[60], schedule={100: 1}, base_seed=7,
                           engine=self._stub_engine([]))
        assert out["schedule"] == {"100": 1}
        assert out["base_seed"] == 7
        assert "runtime_s" in out

    def test_occupancy_defaults_to_office_and_is_recorded(self):
        out = cs.run_study(fr_periods=[60], schedule={100: 1}, base_seed=7,
                           engine=self._stub_engine([]))
        assert out["occupancy"] == "Office"
        out2 = cs.run_study(fr_periods=[60], schedule={100: 1}, base_seed=7,
                            engine=self._stub_engine([]), occupancy="Restaurant")
        assert out2["occupancy"] == "Restaurant"
        assert "Restaurant" in out2["scenario"]
