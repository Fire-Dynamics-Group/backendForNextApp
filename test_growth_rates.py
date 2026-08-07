"""Per-occupancy fire growth rate -> t_lim (EN 1991-1-2 Annex A(10) + Table E.5,
supplemented by BS 9999 Table 3).

Table E.5 assigns growth rates by occupancy (office medium, shopping centre fast,
library fast, ...); BS 9999 Table 3 covers occupancies EC1 omits (shop sales areas
fast, factories/storage fast, warehousing ultra-fast — capped at fast, EC1's top
tier); Annex A(10) maps slow/medium/fast to t_lim = 25/20/15 min. Occupancies
neither source lists (e.g. Restaurant) default to medium, matching the engine's
historical global setting.
"""
import pytest

import teq_reliability as tr

PANATTONI = dict(
    floor_area=64 * 13,
    total_area=2 * (64 * 3.5) + 2 * (13 * 3.5) + 2 * (64 * 13),
    vent_widths=[0, 0, 64, 0],
    vent_heights=[0, 0, 3.5, 0],
)


class TestTlimHoursFor:
    def test_table_e5_assignments(self):
        assert tr.tlim_hours_for("Office") == pytest.approx(20 / 60)
        assert tr.tlim_hours_for("Clothing store") == pytest.approx(15 / 60)
        assert tr.tlim_hours_for("Library") == pytest.approx(15 / 60)
        assert tr.tlim_hours_for("Dwelling") == pytest.approx(20 / 60)

    def test_bs9999_table3_assignments(self):
        # shop sales areas / factories / storage -> fast (BS 9999 Table 3 cat 3;
        # EC1's t_lim scheme has no ultra-fast tier, so warehousing caps at fast)
        assert tr.tlim_hours_for("Retail unit storage area") == pytest.approx(15 / 60)
        assert tr.tlim_hours_for(
            "Manufacturing and storage of combustible goods (<150 kg/m2)") == pytest.approx(15 / 60)
        assert tr.tlim_hours_for(
            "Manufacturing and storage of combustible goods (>150 kg/m2)") == pytest.approx(15 / 60)

    def test_unlisted_occupancy_defaults_to_medium(self):
        # Restaurant: not in EC1 Table E.5; BS 9999 Table 3 puts lounges/seating
        # areas at medium
        assert tr.tlim_hours_for("Restaurant") == pytest.approx(20 / 60)
        assert tr.tlim_hours_for("Kitchen") == pytest.approx(20 / 60)
        assert tr.tlim_hours_for("No such occupancy") == pytest.approx(20 / 60)


class TestEndpointGrowthRate:
    """POST /timeEqReliability builds SteelParams from the occupancy growth rate;
    an explicit tLimMinutes override still wins."""

    def _posted_params(self, monkeypatch, **payload_over):
        import matplotlib
        matplotlib.use("Agg")
        from fastapi.testclient import TestClient
        import main

        captured = {}

        def stub(**kwargs):
            captured.update(kwargs)
            return tr.ReliabilityResult(
                reliability=1.0, n_failed=0, n_sim=1, fr_period=30,
                protection_thickness_mm=1, b_value=1200.0, section_factor=135.0,
                critical_temp=500.0)

        monkeypatch.setattr(main, "compute_reliability", stub)
        rect = [(0, 0), (64, 0), (64, 13), (0, 13), (0, 0)]
        payload = dict(
            convertedPoints=[{"id": 0, "comments": "obstruction",
                              "finalPoints": [{"x": x, "y": y} for x, y in rect]}],
            occupancy="Clothing store", compartmentHeight=3.5,
            fireResistancePeriod=30, nSim=100, openableWidths=[64, 0, 0, 0])
        payload.update(payload_over)
        r = TestClient(main.app).post("/timeEqReliability", json=payload)
        assert r.status_code == 200, r.text
        return captured["params"]

    def test_occupancy_growth_rate_reaches_engine(self, monkeypatch):
        params = self._posted_params(monkeypatch)
        assert params.t_lim_hours == pytest.approx(15 / 60)

    def test_explicit_tlim_minutes_wins(self, monkeypatch):
        params = self._posted_params(monkeypatch, tLimMinutes=25)
        assert params.t_lim_hours == pytest.approx(25 / 60)


class TestEngineUsesOccupancyGrowthRate:
    def _run(self, occupancy, **kw):
        return tr.compute_reliability(
            **PANATTONI, occupancy=occupancy, fr_period_min=30, n_sim=500,
            combustion_factor=1.0, is_sprinklered=False, seed=3, **kw).reliability

    def test_clothing_store_defaults_to_fast(self):
        default = self._run("Clothing store")
        fast = self._run("Clothing store",
                         params=tr.SteelParams(t_lim_hours=15 / 60))
        medium = self._run("Clothing store",
                           params=tr.SteelParams(t_lim_hours=20 / 60))
        assert default == fast
        assert default != medium

    def test_office_still_medium(self):
        default = self._run("Office")
        medium = self._run("Office", params=tr.SteelParams(t_lim_hours=20 / 60))
        assert default == medium

    def test_explicit_params_win(self):
        # a caller-supplied SteelParams must not be second-guessed
        slow = self._run("Clothing store",
                         params=tr.SteelParams(t_lim_hours=25 / 60))
        fast = self._run("Clothing store",
                         params=tr.SteelParams(t_lim_hours=15 / 60))
        assert slow != fast
