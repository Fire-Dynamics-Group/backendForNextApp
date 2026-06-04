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
