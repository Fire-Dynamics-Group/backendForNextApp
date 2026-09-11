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


# EC3-1-2 unprotected-section constants (parametric fire). Kept here so the
# hand-calc test does not import private module names.
_ALPHA_C = 35.0          # EN 1991-1-2 3.3.1(1)
_EPSILON_M = 0.7         # EN 1993-1-2 2.2(2)
_EPSILON_F = 1.0
_SIGMA = 5.67e-8
_K_SH = 1.0
_TK = 273.0              # Eurocode writes (θ + 273)


class TestUnprotectedSteel:
    """Bare-steel (EC3 unprotected section) heat transfer + reliability path."""

    def test_one_step_matches_ec3_hand_calc(self):
        p = tr.SteelParams()
        gas = np.array([[20.0], [820.0]], dtype=float)
        peak = tr.max_unprotected_steel_temp(gas, p)

        steel = 20.0
        c_a = tr._c_steel(np.array([steel]))[0]
        h_conv = _ALPHA_C * (820.0 - steel)
        h_rad = (_EPSILON_M * _EPSILON_F * _SIGMA
                 * ((820.0 + _TK) ** 4 - (steel + _TK) ** 4))
        expected = steel + _K_SH * p.sect_factor / (c_a * p.rho_steel) * (h_conv + h_rad) * p.delta_t_s
        expected = max(expected, p.ambient_temp)
        assert peak[0] == pytest.approx(expected, rel=1e-12)

    def test_never_below_ambient(self):
        p = tr.SteelParams()
        gas = np.array([[20.0], [20.0], [15.0]], dtype=float)
        peak = tr.max_unprotected_steel_temp(gas, p)
        assert peak[0] >= p.ambient_temp

    def _unprotected(self, critical_temp, n_sim=400, seed=42):
        params = tr.SteelParams(steel_fail_temp=critical_temp)
        return tr.compute_reliability(
            **PANATTONI, fr_period_min=60, n_sim=n_sim,
            combustion_factor=1.0, is_sprinklered=False, seed=seed,
            params=params, unprotected=True,
        )

    def test_unprotected_result_has_no_protection_thickness(self):
        r = self._unprotected(500)
        assert 0.0 <= r.reliability <= 1.0
        assert r.n_failed + round(r.reliability * r.n_sim) == r.n_sim
        assert r.protection_thickness_mm is None
        assert r.unprotected is True
        assert r.critical_temp == 500

    def test_higher_critical_temp_does_not_decrease_reliability(self):
        low = self._unprotected(400).reliability
        high = self._unprotected(800).reliability
        assert high >= low

    def test_unprotected_reliability_le_protected(self):
        seed, n_sim = 7, 400
        unprotected = tr.compute_reliability(
            **PANATTONI, fr_period_min=60, n_sim=n_sim,
            combustion_factor=1.0, is_sprinklered=False, seed=seed,
            unprotected=True,
        )
        protected = tr.compute_reliability(
            **PANATTONI, fr_period_min=60, n_sim=n_sim,
            combustion_factor=1.0, is_sprinklered=False, seed=seed,
        )
        assert unprotected.reliability <= protected.reliability

    def test_protected_default_unchanged(self):
        r = tr.compute_reliability(
            **PANATTONI, fr_period_min=60, n_sim=200,
            combustion_factor=1.0, is_sprinklered=False, seed=1,
        )
        assert r.protection_thickness_mm == 16
        assert r.unprotected is False


class TestUdfBatchExport:
    """Sampled EC1 curves packaged for MACS+ AnalyseUDF."""

    def _export(self, n_sim=8, seed=42):
        return tr.export_udf_batch(
            **PANATTONI, n_sim=n_sim, combustion_factor=1.0,
            is_sprinklered=False, seed=seed,
        )

    def test_seed_reproducible(self):
        assert self._export(seed=1) == self._export(seed=1)

    def test_different_seeds_differ(self):
        assert self._export(seed=1) != self._export(seed=2)

    def test_manifest_joins_curves_to_sampled_inputs(self):
        import io
        import json
        import zipfile

        raw = self._export(n_sim=8, seed=11)
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            names = set(zf.namelist())
            assert "manifest.json" in names
            assert "curves/00000.udf" in names
            assert "curves/00007.udf" in names
            manifest = json.loads(zf.read("manifest.json"))
            assert manifest["nSim"] == 8
            assert manifest["seed"] == 11
            assert len(manifest["samples"]) == 8
            for sample in manifest["samples"]:
                curve = tr.parse_udf_curve(zf.read(sample["file"]).decode())
                assert curve.shape[1] == 2
                assert curve[0, 0] == pytest.approx(0.0)
                assert curve[0, 1] >= 20.0
                assert np.all(np.diff(curve[:, 0]) > 0)
                assert sample["fuelLoad"] > 0
                assert 0.0 <= sample["openingPercent"] <= 1.0
                assert 0.01 <= sample["openingFactor"] <= 0.2
                assert sample["seed"] == 11

    def test_curve_matches_parametric_sampling_path(self):
        """First sample's UDF temperatures match parametric_fire_curves at 1 min."""
        import io
        import json
        import zipfile

        n_sim, seed = 4, 5
        raw = self._export(n_sim=n_sim, seed=seed)
        p = tr.SteelParams(t_lim_hours=tr.tlim_hours_for("Office"))
        rng = np.random.default_rng(seed)
        fld, opening_perc = tr.sample_stochastic_inputs(
            occupancy="Office", n_sim=n_sim, rng=rng,
            combustion_factor=1.0, is_sprinklered=False, sprinkler_factor=0.65)
        time_hours = np.arange(0, p.calc_time_hours + p.delta_t_s / 3600, p.delta_t_s / 3600)
        op_fac = tr.calc_op_fac(PANATTONI["vent_widths"], PANATTONI["vent_heights"],
                                PANATTONI["total_area"], opening_perc)
        qtd = fld * PANATTONI["floor_area"] / PANATTONI["total_area"]
        gas = tr.parametric_fire_curves(time_hours, op_fac, qtd, p)
        stride = tr._udf_stride(p, 1.0)

        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            manifest = json.loads(zf.read("manifest.json"))
            curve = tr.parse_udf_curve(zf.read(manifest["samples"][0]["file"]).decode())
            assert manifest["samples"][0]["fuelLoad"] == pytest.approx(float(fld[0]))
            assert curve[1, 1] == pytest.approx(float(gas[stride, 0]), rel=1e-4, abs=0.05)


class TestReliabilityDetails:
    """compute_reliability_details: the same run as compute_reliability, but
    keeping the per-sample data the report charts need (sampled inputs, peak
    steel temps, and the steel time-temperature series on a 1-minute stride)."""

    def _kwargs(self, n_sim=200, seed=42, **over):
        kw = dict(**PANATTONI, fr_period_min=60, n_sim=n_sim,
                  combustion_factor=1.0, is_sprinklered=False, seed=seed)
        kw.update(over)
        return kw

    def test_aggregates_match_compute_reliability(self):
        d = tr.compute_reliability_details(**self._kwargs())
        r = tr.compute_reliability(**self._kwargs())
        assert d.result.n_failed == r.n_failed
        assert d.result.reliability == r.reliability
        assert d.result.protection_thickness_mm == r.protection_thickness_mm

    def test_per_sample_shapes_and_ranges(self):
        n = 200
        d = tr.compute_reliability_details(**self._kwargs(n_sim=n))
        assert d.fld.shape == (n,)
        assert d.glazing_breakage.shape == (n,)
        assert np.all(d.glazing_breakage >= 0) and np.all(d.glazing_breakage <= 1)
        assert d.peak_temp.shape == (n,)
        assert d.steel_series.shape == (len(d.time_min), n)
        assert d.time_min[0] == 0
        # 1-minute stride over the 300-minute simulation
        assert d.time_min[1] == pytest.approx(1.0)

    def test_series_consistent_with_peaks(self):
        d = tr.compute_reliability_details(**self._kwargs())
        series_max = d.steel_series.max(axis=0)
        # The strided series can miss the true peak, but never exceed it,
        # and protected steel moves slowly so it cannot miss by much.
        assert np.all(series_max <= d.peak_temp + 1e-3)
        assert np.all(d.peak_temp - series_max < 20.0)

    def test_failure_count_derivable_from_peaks(self):
        d = tr.compute_reliability_details(**self._kwargs())
        assert int((d.peak_temp > d.result.critical_temp).sum()) == d.result.n_failed

    def test_unprotected_mode(self):
        params = tr.SteelParams(steel_fail_temp=500)
        d = tr.compute_reliability_details(
            **self._kwargs(params=params, unprotected=True))
        assert d.result.unprotected is True
        assert d.result.protection_thickness_mm is None
        assert d.steel_series.shape[1] == 200


class TestSeedEcho:
    """An unseeded run resolves a real seed and reports it, so a later charts
    request can reproduce the exact run the user was shown."""

    def test_explicit_seed_echoed(self):
        r = tr.compute_reliability(
            **PANATTONI, fr_period_min=60, n_sim=50,
            combustion_factor=1.0, is_sprinklered=False, seed=42)
        assert r.seed == 42

    def test_none_seed_resolved_and_reproducible(self):
        kw = dict(**PANATTONI, fr_period_min=60, n_sim=200,
                  combustion_factor=1.0, is_sprinklered=False)
        r1 = tr.compute_reliability(**kw, seed=None)
        assert isinstance(r1.seed, int)
        r2 = tr.compute_reliability(**kw, seed=r1.seed)
        assert r2.n_failed == r1.n_failed
        assert r2.reliability == r1.reliability


class TestDetailsOpeningFactor:
    """QA needs the opening factor each sample actually ran with — it is the
    third derived quantity (after fld and glazing) an engineer recomputes when
    spot-checking a row."""

    def test_opening_factor_per_sample_in_range(self):
        d = tr.compute_reliability_details(
            **PANATTONI, fr_period_min=60, n_sim=150,
            combustion_factor=1.0, is_sprinklered=False, seed=42)
        assert d.opening_factor.shape == (150,)
        # calc_op_fac clamps to [0.01, 0.2]
        assert np.all(d.opening_factor >= 0.01) and np.all(d.opening_factor <= 0.2)

    def test_opening_factor_matches_direct_calc(self):
        n = 100
        d = tr.compute_reliability_details(
            **PANATTONI, fr_period_min=60, n_sim=n,
            combustion_factor=1.0, is_sprinklered=False, seed=7)
        expected = tr.calc_op_fac(
            PANATTONI["vent_widths"], PANATTONI["vent_heights"],
            PANATTONI["total_area"], d.glazing_breakage)
        assert np.allclose(d.opening_factor, expected)
