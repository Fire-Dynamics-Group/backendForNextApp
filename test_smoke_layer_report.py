"""Tests for the warehouse smoke layer report renderer.

The renderer must not compute anything — it reports the numbers it is handed. These
tests feed it fabricated results and check the wording that comes out.

Most assertions run on the rendered *text* (``render_text``), which is the whole
report as one readable string, so a wording change is a one-line diff. A scenario
matrix is pinned as snapshots in ``test_smoke_layer_report_snapshots/``; regenerate
them deliberately with ``UPDATE_SNAPSHOTS=1 pytest test_smoke_layer_report.py``.
A few tests open the finished .docx to prove the Word side holds together.
"""
import os
import re
import zipfile
from datetime import date
from pathlib import Path

import pytest
from docx import Document

from models.smoke_layer_models import (
    SmokeLayerInputs,
    SmokeLayerReportDetails,
    SmokeLayerResults,
    SmokeLayerStep,
)
from services.smoke_layer_report_service import generate_smoke_layer_report
from services.warehouse_report.render import build_context, render_report, render_text

SNAPSHOT_DIR = Path(__file__).parent / "test_smoke_layer_report_snapshots"


def make_inputs(**overrides) -> SmokeLayerInputs:
    base = dict(
        room_area=43047,
        racking_perc=0.33,
        room_height=15,
        fgr=0.188,
        detection_time=120,
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
            escaped=min(max(22.61 * (t - 395.83), 0), 1431),
        )
        for t in range(1, 1201)
    ]
    base = dict(
        steps=steps,
        rset=460,
        aset=1200 if not aset_triggered else 54,
        aset_triggered=aset_triggered,
        margin_of_safety=740 if not aset_triggered else -406,
        reference_height_breached=True,
        breach_time=1197,
        final_clear_height=5.27,
        total_pre_evac=395.83,
        people_per_second=22.61,
        queue_time=64,
    )
    base.update(overrides)
    return SmokeLayerResults(**base)


FULL_DETAILS = SmokeLayerReportDetails(
    client_name="Shed Zone Ltd",
    project_location="Haydock, St Helens",
    building_name="Unit 1",
    site_description="three new build warehouse units with ancillary office accommodation",
    intended_purpose="storage and distribution purposes",
    racking_known=True,
    racking_source="indicative fit-out drawing in Appendix A",
    occupancy_known=True,
    occupancy_source="the Fire Strategy Report supplied by Michael Sparks Associates",
    occupancy_reference="Michael Sparks Associates, Fire Strategy Report, 7th August 2025.",
    has_undercroft=True,
    office_storeys=2,
    office_height="8.5m",
    staircases=2,
    number_of_doors=21,
    door_width_mm=850,
)


def text_for(inputs=None, results=None, details=None, project="Shed Zone", engineer="Kathryn Kleijn") -> str:
    ctx = build_context(project, engineer, inputs or make_inputs(), results or make_results(), details or SmokeLayerReportDetails())
    return render_text(ctx)


def docx_text(stream) -> str:
    """Every paragraph's text in body order, including table cells and text boxes."""
    document = Document(stream)
    w = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    return "\n".join(
        "".join(t.text or "" for t in p.iter(w + "t")) for p in document.element.body.iter(w + "p")
    )


# ---------------------------------------------------------------- wording


class TestFitOut:
    def test_unknown_fitout_uses_the_no_layout_wording(self):
        body = text_for()
        assert "does not currently have a proposed fit-out layout" in body
        assert "85m greater than the 30m limit" in body
        assert "reasonable worst-case" in body

    def test_known_fitout_names_the_use_and_the_45m_limit(self):
        body = text_for(details=FULL_DETAILS)
        assert "anticipated that it will be used for storage and distribution purposes" in body
        assert "70m greater than the 45m maximum limit" in body
        assert "“typical” layout for storage and distribution purposes" in body
        assert "does not currently have a proposed fit-out layout" not in body


class TestAssumptions:
    def test_unknown_racking_is_the_conservative_50_percent(self):
        body = text_for(make_inputs(racking_perc=0.5))
        assert "conservative assumption is used that 50% of the space" in body
        assert "50% of the total floor area, in this case 21,524m²" in body

    def test_known_racking_reports_the_given_percentage(self):
        body = text_for(details=FULL_DETAILS)
        assert "33% of the space will be taken up by obstructions" in body
        assert "as per the indicative fit-out drawing in Appendix A" in body
        assert "67% of the total floor area, in this case 28,841m²" in body

    def test_undercroft_sentences_appear_only_when_present(self):
        with_ = text_for(details=FULL_DETAILS)
        without = text_for()
        assert "under the location of the office accommodation" in with_
        assert "(discounting the office undercroft)" in with_
        assert "does not spread beneath the office undercroft" in with_
        for phrase in ("office accommodation, reducing", "office undercroft"):
            assert phrase not in without

    def test_occupancy_source_drives_wording_and_reference_2(self):
        known = text_for(details=FULL_DETAILS)
        unknown = text_for()
        assert "Fire Strategy Report supplied by Michael Sparks Associates[2]" in known
        assert "[2] Michael Sparks Associates, Fire Strategy Report" in known
        assert "based on guidance from the Approved Document B[3]" in unknown
        assert "[2] Not used." in unknown


class TestAset:
    def test_not_triggered_says_at_least_and_uses_the_assessment_period(self):
        body = text_for()
        assert "margin of safety of at least 740 seconds" in body
        assert "descends to just over 5.2m above ground level" in body
        assert "the ASET is taken to be 20 minutes" in body
        assert "terminated 30 seconds" not in body

    def test_triggered_reports_the_aset_and_termination(self):
        body = text_for(results=make_results(aset_triggered=True, margin_of_safety=200, rset=54 - 200 + 54))
        assert "terminated 30 seconds after the smoke layer breaches 2m" in body
        assert "The calculated ASET value before which escape would be possible is 54 seconds" in body
        assert "at least" not in body

    def test_negative_margin_flags_the_conclusions(self):
        body = text_for(results=make_results(aset_triggered=True))
        assert "!! The ASET is less than the RSET" in body and "conclusions below do not hold" in body


class TestRset:
    def test_travel_time_is_distance_over_speed_rounded_up(self):
        body = text_for()
        assert "the travel time is taken to be 96 seconds" in body

    def test_defaults_keep_the_standard_justifications(self):
        body = text_for()
        assert "A pre-movement time of 180 seconds has been assumed. This figure has been taken from" in body
        assert "not the 180 s default" not in body
        assert "not the 1.33 persons/m/s" not in body

    def test_non_default_values_get_engineer_prompts(self):
        body = text_for(make_inputs(pre_movement_time=120, flow_rate=1.0, fgr=0.0469))
        assert "A pre-movement time of 120 seconds has been assumed." in body
        assert "not the 180 s default" in body
        assert "flow rate used (1 persons/m/s) is not the 1.33" in body
        assert "A Fast growth rate has been assumed" in body
        assert "Justify the choice of Fast growth" in body

    def test_door_schedule_when_given_else_total_width(self):
        with_doors = text_for(details=FULL_DETAILS)
        without = text_for()
        assert "21 doors (one of which is discounted), each with a 850mm clear width" in with_doors
        assert "total available exit width of 17m (with the largest exit discounted)" in without


class TestEngineerPrompts:
    def test_missing_descriptions_become_prompts_not_blanks(self):
        body = text_for()
        assert "[client name]" in body
        assert "ENGINEER TO EDIT" not in body  # prompts are added by the builder, text carries "!!"
        assert "!! Describe the site here" in body
        assert "!! Describe the office accommodation" in body

    def test_office_floor_list(self):
        body = text_for(details=FULL_DETAILS)
        assert "contained over 2 storeys above the warehouse – First Floor and Second Floor" in body
        no_undercroft = FULL_DETAILS.model_copy(update={"has_undercroft": False, "office_storeys": 1})
        assert "contained over 1 storey above the warehouse – Ground Floor." in text_for(details=no_undercroft)


# ---------------------------------------------------------------- snapshots

SCENARIOS = {
    "minimal": (make_inputs(), make_results(), SmokeLayerReportDetails()),
    "full_known": (make_inputs(), make_results(), FULL_DETAILS),
    "aset_triggered": (make_inputs(), make_results(aset_triggered=True), SmokeLayerReportDetails(building_name="Unit 6")),
    "no_undercroft_racking_known": (
        make_inputs(racking_perc=0.4),
        make_results(),
        SmokeLayerReportDetails(racking_known=True, intended_purpose="cold storage"),
    ),
    "non_default_inputs": (make_inputs(pre_movement_time=120, flow_rate=1.0, fgr=0.0469, detection_time=60), make_results(), FULL_DETAILS),
}


@pytest.mark.parametrize("name", sorted(SCENARIOS))
def test_scenario_snapshot(name):
    inputs, results, details = SCENARIOS[name]
    body = render_text(build_context("Shed Zone", "Kathryn Kleijn", inputs, results, details))
    body = "\n".join(line for line in body.splitlines() if line.strip())
    path = SNAPSHOT_DIR / f"{name}.txt"
    if os.environ.get("UPDATE_SNAPSHOTS") or not path.exists():
        SNAPSHOT_DIR.mkdir(exist_ok=True)
        path.write_text(body, encoding="utf-8")
    assert body == path.read_text(encoding="utf-8"), f"snapshot {name} differs; review and set UPDATE_SNAPSHOTS=1 to accept"


# ---------------------------------------------------------------- the .docx


class TestDocument:
    def test_returns_a_valid_docx_via_the_service(self):
        stream = generate_smoke_layer_report("Shed Zone", "Kathryn Kleijn", make_inputs(), make_results(), FULL_DETAILS)
        stream.seek(0)
        assert zipfile.is_zipfile(stream)

    def test_no_placeholder_or_marker_survives(self):
        stream = render_report("Shed Zone", "Kathryn Kleijn", make_inputs(), make_results(), FULL_DETAILS, today=date(2026, 9, 2))
        with zipfile.ZipFile(stream) as z:
            for name in ("word/document.xml", "word/header1.xml"):
                xml = z.read(name).decode("utf-8")
                assert "{{" not in xml, name
                assert "{fig:" not in xml and "{tab:" not in xml, name
        body = docx_text(stream)
        assert "!!" not in body and "[[" not in body

    def test_cover_and_table_carry_the_values(self):
        stream = render_report("Shed Zone", "Kathryn Kleijn", make_inputs(), make_results(), FULL_DETAILS, today=date(2026, 9, 2))
        body = docx_text(stream)
        assert "2 September 2026" in body
        assert "Shed Zone Ltd" in body
        assert "kathryn@firedynamicsgroup.com" in body
        for value in ("120", "180", "96", "64", "460", ">1,200", ">740"):
            assert value in body

    def test_figures_numbered_in_order(self):
        stream = render_report("Shed Zone", "", make_inputs(), make_results(), FULL_DETAILS)
        body = docx_text(stream)
        assert "Figure 1: Site Plan of Shed Zone Development." in body
        assert "Figure 3: Heat Release Rate Over the 20-minute Reference Period" in body
        assert "Figure 5: Calculated Smoke Layer Height Above Floor vs Time." in body
        assert "Table 1: Result of ASET/RSET Calculation" in body
        assert "shown below in Figure 4 and Figure 5" in body
        document = Document(stream)
        pngs = [p for p in document.part.package.iter_parts() if str(p.partname).endswith(".png")]
        assert len(pngs) >= 4  # site plan + 3 result figures (+ cover art)

    def test_appendix_repeats_the_calculation_with_a_numbering(self):
        stream = render_report("Shed Zone", "", make_inputs(), make_results(), FULL_DETAILS)
        body = docx_text(stream)
        # Section 3 in the body, numbered plainly...
        assert "Figure 3: Heat Release Rate Over the 20-minute Reference Period" in body
        assert "Table 1: Result of ASET/RSET Calculation" in body
        # ...and again as Appendix A with A-numbering, as in Kathryn's appendix template.
        assert "Figure A.2: Heat Release Rate Over the 20-minute Reference Period" in body
        assert "shown below in Figure A.3 and Figure A.4" in body
        assert "Table A.1: Result of ASET/RSET Calculation" in body
        assert body.count("Heat Release Rate of the Fire") == 2
        document = Document(stream)
        styled = {(p.text, p.style.name) for p in document.paragraphs if p.text.strip()}
        assert ("Quantitative Justification of Extended Travel Distances within the Warehouse", "Style1") in styled
        assert ("Summary of ASET / RSET Calculation", "FD Subheading 1") in styled
        # The appendix headings and paragraphs sit on a cloned list numbered A.1. / A.1.1.
        w = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
        numbering = document.part.numbering_part.element
        appendix_nums = {
            n.get(w + "numId")
            for n in numbering.findall(w + "num")
            if any(t.get(w + "val") == "A.%2." for t in n.iter(w + "lvlText"))
        }
        assert len(appendix_nums) == 1
        summary = next(p for p in document.paragraphs if p.text == "Summary of ASET / RSET Calculation")
        num_id = summary._p.find(w + "pPr").find(w + "numPr").find(w + "numId").get(w + "val")
        assert num_id in appendix_nums
        first_body = next(p for p in document.paragraphs if p.text.startswith("The ASET has been calculated") and p._p.find(w + "pPr").find(w + "numPr") is not None)
        assert first_body._p.find(w + "pPr").find(w + "numPr").find(w + "numId").get(w + "val") in appendix_nums

    def test_engineer_prompts_are_highlighted(self):
        stream = render_report("Shed Zone", "", make_inputs(), make_results())
        document = Document(stream)
        prompts = [p for p in document.paragraphs if p.text.startswith("ENGINEER TO EDIT")]
        assert prompts
        assert all(run.font.highlight_color is not None for p in prompts for run in p.runs)

    def test_heading_paragraphs_use_the_team_styles(self):
        stream = render_report("Shed Zone", "", make_inputs(), make_results())
        document = Document(stream)
        styled = {(p.text, p.style.name) for p in document.paragraphs if p.text.strip()}
        assert ("Introduction", "Main Headd") in styled
        assert ("Introduction", "FD Subheading 1") in styled  # section 3.1
        assert ("Calculation of ASET", "FD Subheading 1") in styled
        assert ("Site Description", "FD Subheading 1") in styled
        assert ("Heat Release Rate of the Fire", "Astute References") in styled

    def test_handles_a_single_timestep(self):
        results = make_results()
        results.steps = results.steps[:1]
        stream = render_report("Shed Zone", "", make_inputs(), results)
        stream.seek(0)
        assert zipfile.is_zipfile(stream)

    def test_missing_variable_is_an_error_not_a_blank(self):
        ctx = build_context("Shed Zone", "", make_inputs(), make_results(), SmokeLayerReportDetails())
        del ctx["client_name"]
        with pytest.raises(Exception):
            render_text(ctx)
