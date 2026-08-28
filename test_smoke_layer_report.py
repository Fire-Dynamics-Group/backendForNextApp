"""Tests for the warehouse smoke layer report renderer.

The renderer must not compute anything — it reports the numbers it is handed. These
tests therefore feed it fabricated results and assert those exact values come back
out in the document.
"""
import zipfile

import pytest
from docx import Document

from models.smoke_layer_models import (
    SmokeLayerInputs,
    SmokeLayerResults,
    SmokeLayerStep,
)
from services.smoke_layer_report_service import generate_smoke_layer_report


def make_inputs(**overrides) -> SmokeLayerInputs:
    base = dict(
        room_area=43047,
        racking_perc=0.33,
        room_height=15,
        fgr=0.188,
        detection_time=60,
        pre_movement_time=180,
        maximum_travel_distance=115,
        walking_speed=1.2,
        total_exit_width=17,
        flow_rate=1.33,
        occupancy=1431,
        assessment_time=1200,
        reference_height=5.3,
        tstep=1,
    )
    base.update(overrides)
    return SmokeLayerInputs(**base)


def make_results(aset_triggered=False, **overrides) -> SmokeLayerResults:
    steps = [
        SmokeLayerStep(
            time=float(t),
            hrr=0.000188 * t**2,
            convective_hrr=0.0001316 * t**2,
            smoke_layer_temp=20 + t * 0.3,
            added_smoke_temp=20 + t * 0.7,
            clear_height=15 - t * 0.008,
            depth_change=0.008,
            velocity=0.008,
            escaped=min(max(22.61 * (t - 335.83), 0), 1431),
        )
        for t in range(1, 1201)
    ]
    base = dict(
        steps=steps,
        rset=400,
        aset=1200 if not aset_triggered else 54,
        aset_triggered=aset_triggered,
        margin_of_safety=800 if not aset_triggered else -346,
        reference_height_breached=True,
        breach_time=1197,
        final_clear_height=5.27,
        total_pre_evac=335.83,
        people_per_second=22.61,
        queue_time=64,
    )
    base.update(overrides)
    return SmokeLayerResults(**base)


def text_of(stream) -> str:
    document = Document(stream)
    parts = [p.text for p in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            parts.extend(cell.text for cell in row.cells)
    return "\n".join(parts)


class TestReportContent:
    def test_returns_a_valid_docx(self):
        stream = generate_smoke_layer_report("Unit 6", "A Engineer", make_inputs(), make_results())
        stream.seek(0)
        assert zipfile.is_zipfile(stream)

    def test_reports_the_supplied_aset_and_rset(self):
        stream = generate_smoke_layer_report("Unit 6", "A Engineer", make_inputs(), make_results())
        body = text_of(stream)
        assert "400 s" in body  # RSET
        assert "> 1,200 s" in body  # ASET never reached
        assert "at least 800 s" in body

    def test_states_the_verdict_when_tenability_holds(self):
        stream = generate_smoke_layer_report("Unit 6", "", make_inputs(), make_results())
        body = text_of(stream)
        assert "available safe escape time exceeds the required" in body

    def test_states_the_verdict_when_tenability_is_exceeded(self):
        results = make_results(aset_triggered=True)
        stream = generate_smoke_layer_report("Unit 6", "", make_inputs(), results)
        body = text_of(stream)
        assert "Tenability limits are exceeded" in body
        assert "54 s" in body

    def test_shows_the_plan_area_left_after_racking(self):
        stream = generate_smoke_layer_report("Unit 6", "", make_inputs(), make_results())
        assert "28,841 m²" in text_of(stream)

    def test_carries_the_project_and_engineer_through(self):
        stream = generate_smoke_layer_report("Atlantic Park", "A Engineer", make_inputs(), make_results())
        body = text_of(stream)
        assert "Atlantic Park" in body
        assert "A Engineer" in body

    def test_reports_the_reference_height_breach(self):
        stream = generate_smoke_layer_report("Unit 6", "", make_inputs(), make_results())
        body = text_of(stream)
        assert "Reference height (5.3 m)" in body
        assert "1,197 s" in body

    def test_says_not_breached_when_the_reference_height_holds(self):
        results = make_results(reference_height_breached=False, breach_time=None)
        stream = generate_smoke_layer_report("Unit 6", "", make_inputs(), results)
        assert "Not breached" in text_of(stream)

    def test_embeds_the_figures(self):
        stream = generate_smoke_layer_report("Unit 6", "", make_inputs(), make_results())
        document = Document(stream)
        images = [p for p in document.part.package.parts if p.partname.ext == "png"]
        assert len(images) == 4
        body = text_of(stream)
        assert "Figure 1: Smoke layer height" in body
        assert "Figure 4: Occupants escaped" in body

    def test_records_the_conservative_assumption_in_the_methodology(self):
        stream = generate_smoke_layer_report("Unit 6", "", make_inputs(), make_results())
        body = text_of(stream)
        assert "whole accumulated smoke mass" in body
        assert "more conservative" in body


class TestReportEdgeCases:
    def test_falls_back_when_no_project_name_is_given(self):
        stream = generate_smoke_layer_report("", "", make_inputs(), make_results())
        assert "Untitled project" in text_of(stream)

    def test_omits_the_reference_line_when_it_equals_the_tenability_limit(self):
        # Should still render; the 2 m line is drawn once, not twice.
        inputs = make_inputs(reference_height=2)
        stream = generate_smoke_layer_report("Unit 6", "", inputs, make_results())
        assert "Reference height (2 m)" in text_of(stream)

    def test_handles_a_single_timestep(self):
        results = make_results()
        results.steps = results.steps[:1]
        stream = generate_smoke_layer_report("Unit 6", "", make_inputs(), results)
        stream.seek(0)
        assert zipfile.is_zipfile(stream)
