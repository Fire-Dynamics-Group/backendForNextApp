"""Tests for the multi-building warehouse smoke layer report.

Same approach as test_smoke_layer_report.py: wording is checked on the rendered text,
a three-building scenario is pinned as a snapshot (``UPDATE_SNAPSHOTS=1`` regenerates
it), and a few tests open the .docx.
"""
import os
import zipfile
from pathlib import Path

from models.smoke_layer_models import (
    SmokeLayerBuilding,
    SmokeLayerBuildingDetails,
    SmokeLayerDoorGroup,
    SmokeLayerProjectDetails,
    SmokeLayerReportRequest,
)
from services.smoke_layer_report_service import generate_multi_building_report
from services.warehouse_report.render import build_multi_context, multi_tables, render_multi_report, render_multi_text
from test_smoke_layer_report import FULL_DETAILS, SNAPSHOT_DIR, docx_text, make_inputs, make_results

PROJECT = SmokeLayerProjectDetails(
    client_name="Shed Zone Ltd",
    project_location="Haydock, St Helens",
    site_description="three new build warehouse units with ancillary office accommodation",
    intended_purpose="storage and distribution purposes",
    staircases=2,
    racking_source="indicative fit-out drawings in Appendix B",
    occupancy_known=True,
    occupancy_source="the Fire Strategy Report supplied by Michael Sparks Associates",
    occupancy_reference="Michael Sparks Associates, Fire Strategy Report, 7th August 2025.",
)


def building(name, *, area=43047, height=15.0, travel=115.0, occupancy=1431.0, racking=0.33, triggered=False,
             aset=1200.0, rset=460.0, doors=((21, 850),), storeys=1, office_height="4m", undercroft=True, **inputs):
    return SmokeLayerBuilding(
        name=name,
        inputs=make_inputs(room_area=area, room_height=height, maximum_travel_distance=travel, occupancy=occupancy,
                           racking_perc=racking, **inputs),
        results=make_results(aset_triggered=triggered, aset=aset, rset=rset, margin_of_safety=aset - rset),
        details=SmokeLayerBuildingDetails(
            has_undercroft=undercroft, office_storeys=storeys, office_height=office_height, racking_known=True,
            doors=[SmokeLayerDoorGroup(count=c, width_mm=w) for c, w in doors],
        ),
    )


def three_units():
    return [
        building("Unit 1", triggered=True, aset=705),
        building("Unit 3", area=12500, height=12, travel=51.3, occupancy=416, racking=0.4, triggered=True, aset=540,
                 rset=380, doors=((6, 850), (2, 1000)), storeys=2, office_height="8m"),
        building("Unit 4", area=9800, height=10, travel=40.5, occupancy=210, rset=350, doors=((5, 1050),), undercroft=False),
    ]


def text_for(buildings, project=PROJECT) -> str:
    return render_multi_text(build_multi_context("Shed Zone", "Kathryn Kleijn", project, buildings))


class TestWording:
    def test_names_and_count_are_joined_in_prose(self):
        body = text_for(three_units())
        assert "This report addresses Unit 1, Unit 3 and Unit 4." in body
        assert "Each of the three units have multi-directional travel distances" in body
        assert "the same parameters are used for all three of the units" in body

    def test_mixture_of_aset_outcomes_names_the_units(self):
        body = text_for(three_units())
        assert "For Unit 4, the figures cover the full length of the 20-minute reference period. For this unit," in body
        assert "For Unit 1 and Unit 3, the smoke layer descends to below 2m" in body

    def test_all_units_reach_aset(self):
        units = three_units()
        units[2] = building("Unit 4", triggered=True, aset=900)
        body = text_for(units)
        assert "For all units, the smoke layer descends to below 2m" in body

    def test_racking_per_building_refers_to_the_table(self):
        body = text_for(three_units())
        assert "are given in Table {tab:racking}, as per the indicative fit-out drawings in Appendix B." in body
        assert "!table racking |" in body
        assert "were given in Table {tab:racking}, and are repeated for clarity in Table {tab:area}" in body

    def test_same_racking_everywhere_uses_the_single_figure(self):
        units = [building("Unit 1"), building("Unit 2", area=9000)]
        body = text_for(units)
        assert "It is assumed that under the proposed fit-out, 33% of the space" in body
        assert "!table racking" not in body
        assert "for each building is 33%. This is accounted for" in body

    def test_queueing_names_the_units_over_220_people(self):
        body = text_for(three_units())
        assert "This applies to Unit 1 and Unit 3. For the remaining units, with lower occupancy" in body

    def test_shared_parameter_mismatch_prompts_the_engineer(self):
        units = three_units()
        units[1] = building("Unit 3", detection_time=60, pre_movement_time=240)
        body = text_for(units)
        assert "!! The units were run with different values for detection time and pre-movement time." in body

    def test_missing_doors_and_offices_prompt_the_engineer(self):
        units = [building("Unit 1", doors=(), storeys=None, office_height=""), building("Unit 2")]
        body = text_for(units)
        assert "!! No exit doors were entered for Unit 1" in body
        assert "!! Complete the office accommodation for Unit 1" in body

    def test_three_unit_snapshot(self):
        body = text_for(three_units())
        path = SNAPSHOT_DIR / "multi_three_units.txt"
        if os.environ.get("UPDATE_SNAPSHOTS") or not path.exists():
            path.write_text(body, encoding="utf-8")
        assert body == path.read_text(encoding="utf-8")


class TestTables:
    def test_rows_follow_building_order_and_door_widths_are_listed(self):
        tables = multi_tables(build_multi_context("Shed Zone", "", PROJECT, three_units()))
        assert [r[0] for r in tables["doors"][1:]] == ["Unit 1", "Unit 3", "Unit 4"]
        assert tables["doors"][2][2:4] == ["8", "850 / 1000"]
        assert tables["office"][2][1:] == ["First Floor and Second Floor", "8m"]
        assert tables["office"][3][1] == "Ground Floor"  # no undercroft: offices start at ground
        assert tables["results"][0] == ["", "Factor", "Unit 1 (s)", "Unit 3 (s)", "Unit 4 (s)"]
        assert tables["results"][-1][2:] == ["245", "160", ">850"]
        assert "results_a" in tables and "office_a" not in tables


class TestDocument:
    def test_renders_a_docx_with_numbered_tables_and_per_unit_figures(self):
        stream = generate_multi_building_report("Shed Zone", "Kathryn Kleijn", PROJECT, three_units())
        stream.seek(0)
        assert zipfile.is_zipfile(stream)
        body = docx_text(stream)
        assert "{{" not in body and "{tab:" not in body and "{fig:" not in body and "!!" not in body
        assert "Table 1: Details of Office Accommodation within the Warehouses." in body
        assert "Table 10: Result of ASET/RSET Calculation" in body
        assert "Figure 5: Calculated Smoke Layer Height Above Floor vs Time, Unit 1." in body
        assert "Figure 9: Calculated Smoke Layer Height Above Floor vs Time, Unit 4." in body
        assert "Table A.9: Result of ASET/RSET Calculation" in body
        assert "Figure A.8: Calculated Smoke Layer Height Above Floor vs Time, Unit 4." in body
        assert "shown below in: Figure 4 and Figure 5 (Unit 1); Figure 6 and Figure 7 (Unit 3), and Figure 8 and Figure 9 (Unit 4)." in body
        assert "850 / 1000" in body

    def test_one_building_uses_the_single_building_report(self):
        stream = render_multi_report("Shed Zone", "Kathryn Kleijn", PROJECT, [building("Unit 1")])
        body = docx_text(stream)
        assert "Figure 5: Calculated Smoke Layer Height Above Floor vs Time." in body
        assert "Table 1: Result of ASET/RSET Calculation" in body
        assert "21 doors (one of which is discounted), each with a 850mm clear width" in body


class TestRequestShapes:
    def test_legacy_single_building_body_still_validates(self):
        req = SmokeLayerReportRequest(inputs=make_inputs(), results=make_results(), details=FULL_DETAILS)
        assert req.buildings == [] and req.inputs is not None

    def test_buildings_body_validates(self):
        req = SmokeLayerReportRequest(project=PROJECT, buildings=three_units())
        assert len(req.buildings) == 3 and req.inputs is None
