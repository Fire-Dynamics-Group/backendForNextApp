"""Integration test for the POST /timeEqReliability endpoint via FastAPI TestClient."""
import matplotlib
matplotlib.use("Agg")

import pytest
from fastapi.testclient import TestClient

import main

client = TestClient(main.app)


def _mock_points():
    """Panattoni-ish rectangular compartment (64 x 13) as drawn ConvertedElements."""
    rect = [(0, 0), (64, 0), (64, 13), (0, 13), (0, 0)]
    return [
        {"id": 0, "comments": "obstruction",
         "finalPoints": [{"x": x, "y": y} for x, y in rect]},
        {"id": 1, "comments": "opening",
         "finalPoints": [{"x": 0, "y": 0}, {"x": 64, "y": 0}]},
    ]


def _payload(**over):
    base = dict(
        convertedPoints=_mock_points(),
        occupancy="Office",
        compartmentHeight=3.5,
        fireResistancePeriod=60,
        isSprinklered=False,
        nSim=500,
        openableWidths=[64, 0, 0, 0],   # one openable wall, like Panattoni
        combustionFactor=1.0,
    )
    base.update(over)
    return base


def _office_canvas_points():
    """A real 19.2 x 7.4 m office drawn on the upload canvas (Sep 2026), kept
    verbatim as exported — including the duplicated vertex in opening id 3 —
    so the derivation is tested against genuine canvas output, not idealised
    rectangles. Six 1 m-high openings: five on the long wall, one on a short
    wall."""
    return [
        {"id": 0, "comments": "obstruction",
         "finalPoints": [{"x": 0, "y": 0}, {"x": 0, "y": 7.4},
                         {"x": 19.2, "y": 7.4}, {"x": 19.2, "y": 0},
                         {"x": 0, "y": 0}]},
        {"id": 1, "comments": "opening",
         "finalPoints": [{"x": 1, "y": 7.4}, {"x": 3, "y": 7.4}]},
        {"id": 2, "comments": "opening",
         "finalPoints": [{"x": 5.3, "y": 7.4}, {"x": 6.4, "y": 7.4}]},
        {"id": 3, "comments": "opening",
         "finalPoints": [{"x": 8.4, "y": 7.4}, {"x": 10.5, "y": 7.4},
                         {"x": 10.5, "y": 7.4}]},
        {"id": 4, "comments": "opening",
         "finalPoints": [{"x": 12.8, "y": 7.4}, {"x": 14, "y": 7.4}]},
        {"id": 5, "comments": "opening",
         "finalPoints": [{"x": 16.2, "y": 7.4}, {"x": 18.3, "y": 7.4}]},
        {"id": 6, "comments": "opening",
         "finalPoints": [{"x": 19.2, "y": 6.9}, {"x": 19.2, "y": 5.8}]},
    ]


def _office_canvas_payload(**over):
    """The full form submission that accompanied _office_canvas_points: FR 90,
    critical temp 945 C (max steel temp from the MACS+ desktop 10k batch),
    concrete throughout (b 1742), party-wall openable widths."""
    base = dict(
        convertedPoints=_office_canvas_points(),
        occupancy="Office",
        compartmentHeight=3.15,
        fireResistancePeriod=90,
        isSprinklered=False,
        nSim=100,
        openableWidths=[7.4, 19.2, 7.4, 19.2],
        bValue=1742,
        sectionFactor=135,
        criticalTemp=945,
        combustionFactor=0.8,
        seed=42,
    )
    base.update(over)
    return base


class TestReliabilityEndpoint:
    def test_returns_reliability_json(self):
        r = client.post("/timeEqReliability", json=_payload())
        assert r.status_code == 200, r.text
        body = r.json()
        assert 0.0 <= body["reliability"] <= 1.0
        assert body["protectionThickness_mm"] == 16          # Panattoni FR60
        assert body["nSim"] == 500
        assert body["nFailed"] + round(body["reliability"] * 500) == 500
        assert body["factorsApplied"]["combustibility"] == 1.0

    def test_nsim_capped(self):
        body = client.post("/timeEqReliability", json=_payload(nSim=999999)).json()
        assert body["nSim"] == 10000


class TestNsimDefault:
    """Default and cap follow the convergence study (scripts/convergence_out/):
    the min-max envelope of repeat runs first narrows to +/-0.5% at nSim=10,000
    in the worst case across occupancies (Clothing store FR30 fast growth /
    FR60); larger sync runs buy nothing the guide tolerance needs and belong to
    job-based runs."""

    def test_endpoint_default_matches_study(self):
        assert main.TimeEqReliabilityData.model_fields["nSim"].default == 10000

    def test_engine_default_matches_study(self):
        import inspect
        import teq_reliability
        sig = inspect.signature(teq_reliability.compute_reliability)
        assert sig.parameters["n_sim"].default == 10000

    def test_custom_overrides_applied(self):
        body = client.post("/timeEqReliability",
                            json=_payload(sectionFactor=200, criticalTemp=550, bValue=1800)).json()
        assert body["sectionFactor"] == 200
        assert body["criticalTemp"] == 550
        assert body["bValue"] == 1800

    def test_unknown_occupancy_errors(self):
        r = client.post("/timeEqReliability", json=_payload(occupancy="Nonexistent"))
        assert r.status_code == 400
        assert "not found" in r.json()["detail"]


def _office_polygon_points():
    """A real 12-wall office polygon drawn on the upload canvas (Sep 2026):
    24.1 x 21 m overall with a re-entrant doorway notch on the north wall and
    two rectangular cut-outs, plus 21 one-metre-high openings (two of them on
    the angled notch walls). Kept verbatim as exported."""
    poly = [(0.9, 21), (8.5, 21), (10.3, 18.9), (11, 18.9), (13.3, 21),
            (24.1, 21), (24.1, 7.7), (20.8, 7.7), (20.8, 0), (0, 0),
            (0, 8.6), (0.9, 8.6), (0.9, 21)]
    openings = [
        [(8.9, 20.6), (9.7, 19.6)], [(11.8, 19.6), (12.7, 20.4)],
        [(13.5, 21), (15, 21)], [(16, 21), (17.5, 21)], [(17.8, 21), (19.2, 21)],
        [(20.2, 21), (21.7, 21)], [(22, 21), (23.4, 21)],
        [(24.1, 20.2), (24.1, 18)], [(24.1, 16.1), (24.1, 13.9)],
        [(20.8, 0), (18.2, 0)], [(16.9, 0), (15.4, 0)], [(14.2, 0), (12.8, 0)],
        [(12.5, 0), (11.2, 0)], [(9.9, 0), (8.5, 0)], [(8.2, 0), (6.9, 0)],
        [(5.7, 0), (4.2, 0)], [(3, 0), (1.6, 0)], [(1.3, 0), (0, 0)],
        [(0.9, 14.6), (0.9, 16.4)], [(0.9, 18.5), (0.9, 20.3)],
        [(0.9, 12.2), (0.9, 12.8)],
    ]
    return (
        [{"id": 0, "comments": "obstruction",
          "finalPoints": [{"x": x, "y": y} for x, y in poly]}]
        + [{"id": i + 1, "comments": "opening",
            "finalPoints": [{"x": a[0], "y": a[1]}, {"x": b[0], "y": b[1]}]}
           for i, (a, b) in enumerate(openings)]
    )


def _office_polygon_payload(**over):
    """The form submission that accompanied _office_polygon_points: FR 90,
    critical temp 500 C, concrete throughout (b 1742), 10k sims. The app's
    unseeded run showed 25 mm protection and 12 of 10000 over 500 C."""
    base = dict(
        convertedPoints=_office_polygon_points(),
        occupancy="Office",
        compartmentHeight=3.15,
        fireResistancePeriod=90,
        isSprinklered=False,
        nSim=10000,
        openableWidths=[7.6, 2.77, 0.7, 3.11, 10.8, 13.3,
                        3.3, 7.7, 20.8, 8.6, 0.9, 12.4],
        bValue=1742,
        sectionFactor=135,
        criticalTemp=500,
        combustionFactor=0.8,
        seed=42,
    )
    base.update(over)
    return base


class TestOfficeCanvasCompartment:
    """Pins the real-canvas office run: same numbers the desktop form showed
    (protection 4 mm, 0 of 100 over 945 C) and the derived geometry."""

    def test_geometry_derivation(self):
        from types import SimpleNamespace

        from services.teq_reliability_run import _elements
        from time_eq import derive_geometry

        geo = derive_geometry(_elements(_office_canvas_points()), 3.15)
        assert geo.floor_area == pytest.approx(142.08)
        assert geo.At == pytest.approx(451.74)
        assert sorted(geo.wall_lengths) == pytest.approx([7.4, 7.4, 19.2, 19.2])

    def test_seeded_run_matches_desktop_form_result(self):
        r = client.post("/timeEqReliability", json=_office_canvas_payload())
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["protectionThickness_mm"] == 4
        assert body["nFailed"] == 0
        assert body["reliability"] == 1.0
        assert body["nSim"] == 100
        assert body["criticalTemp"] == 945
        assert body["bValue"] == 1742
        assert body["sectionFactor"] == 135
        assert body["frPeriod"] == 90


class TestOfficePolygonCompartment:
    """Pins the real-canvas 12-wall office run (protection 25 mm as the form
    showed; the failure count is pinned under seed 42 — the app's unseeded run
    gave 12 of 10000, both inside the convergence study's +/-0.5pp band)."""

    def test_geometry_derivation(self):
        from services.teq_reliability_run import _elements
        from time_eq import derive_geometry

        geo = derive_geometry(_elements(_office_polygon_points()), 3.15)
        assert geo.floor_area == pytest.approx(463.755)
        assert geo.At == pytest.approx(1217.248, abs=1e-3)
        assert len(geo.wall_lengths) == 12

    def test_seeded_run_matches_desktop_form_result(self):
        r = client.post("/timeEqReliability", json=_office_polygon_payload())
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["protectionThickness_mm"] == 25
        assert body["nFailed"] == 18
        assert body["reliability"] == pytest.approx(0.9982)
        assert body["nSim"] == 10000
        assert body["criticalTemp"] == 500
        assert body["frPeriod"] == 90


class TestUnprotectedEndpoint:
    def test_protected_payload_omitting_flag_is_unchanged(self):
        r = client.post("/timeEqReliability", json=_payload())
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["protectionThickness_mm"] == 16
        assert "unprotected" not in body
        assert body["frPeriod"] == 60

    def test_unprotected_returns_reliability_without_thickness(self):
        r = client.post("/timeEqReliability",
                         json=_payload(unprotected=True, criticalTemp=550, nSim=200))
        assert r.status_code == 200, r.text
        body = r.json()
        assert 0.0 <= body["reliability"] <= 1.0
        assert body["nSim"] == 200
        assert body["nFailed"] + round(body["reliability"] * 200) == 200
        assert body["criticalTemp"] == 550
        assert "protectionThickness_mm" not in body
        assert body["unprotected"] is True
        assert "sectionFactor" in body
        assert "bValue" in body
        assert "factorsApplied" in body

    def test_unprotected_does_not_require_fr_period(self):
        payload = _payload(unprotected=True, criticalTemp=500, nSim=100)
        del payload["fireResistancePeriod"]
        r = client.post("/timeEqReliability", json=payload)
        assert r.status_code == 200, r.text
        assert "protectionThickness_mm" not in r.json()

    def test_protected_still_requires_fr_period(self):
        payload = _payload()
        del payload["fireResistancePeriod"]
        r = client.post("/timeEqReliability", json=payload)
        assert r.status_code == 400


class TestFireCurveExportEndpoint:
    def test_returns_zip_with_manifest(self):
        import io
        import json
        import zipfile

        payload = _payload(nSim=4, seed=3)
        del payload["fireResistancePeriod"]
        r = client.post("/timeEqFireCurves", json=payload)
        assert r.status_code == 200, r.text
        assert r.headers["content-type"].startswith("application/zip")
        with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
            manifest = json.loads(zf.read("manifest.json"))
            assert manifest["nSim"] == 4
            assert manifest["seed"] == 3
            assert len(manifest["samples"]) == 4


class TestSeedInResponse:
    """The reliability body reports the seed the run used, so a follow-up
    charts request can reproduce the exact run the user was shown."""

    def test_explicit_seed_echoed(self):
        body = client.post("/timeEqReliability", json=_payload(seed=42, nSim=50)).json()
        assert body["seed"] == 42

    def test_generated_seed_reproduces_run(self):
        first = client.post("/timeEqReliability", json=_payload(nSim=200)).json()
        assert isinstance(first["seed"], int)
        again = client.post("/timeEqReliability",
                            json=_payload(nSim=200, seed=first["seed"])).json()
        assert again["nFailed"] == first["nFailed"]


class TestReliabilityChartsEndpoint:
    """POST /timeEqReliabilityCharts: the reliability run plus the two report
    charts (steel time-temperature spaghetti with the critical-temperature
    line, and the pass/fail scatter), PNG base64 in JSON."""

    @staticmethod
    def _png(b64: str) -> bytes:
        import base64
        raw = base64.b64decode(b64)
        assert raw[:8] == b"\x89PNG\r\n\x1a\n"
        return raw

    def test_returns_reliability_body_and_charts(self):
        r = client.post("/timeEqReliabilityCharts",
                        json=_payload(nSim=50, seed=5, criticalTemp=500))
        assert r.status_code == 200, r.text
        body = r.json()
        assert 0.0 <= body["reliability"] <= 1.0
        assert body["seed"] == 5
        assert body["criticalTemp"] == 500
        self._png(body["charts"]["steelTempSpaghetti"])
        self._png(body["charts"]["passFailScatter"])

    def test_matches_reliability_run_with_same_seed(self):
        rel = client.post("/timeEqReliability", json=_payload(nSim=200, seed=9)).json()
        charts = client.post("/timeEqReliabilityCharts",
                             json=_payload(nSim=200, seed=9)).json()
        assert charts["nFailed"] == rel["nFailed"]
        assert charts["reliability"] == rel["reliability"]

    def test_unprotected_supported(self):
        r = client.post("/timeEqReliabilityCharts",
                        json=_payload(unprotected=True, criticalTemp=550,
                                      nSim=50, seed=3))
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["unprotected"] is True
        assert "protectionThickness_mm" not in body
        self._png(body["charts"]["steelTempSpaghetti"])

    def test_unknown_occupancy_errors(self):
        r = client.post("/timeEqReliabilityCharts",
                        json=_payload(occupancy="Nonexistent", nSim=10))
        assert r.status_code == 400
