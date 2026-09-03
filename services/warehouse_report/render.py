"""Build the report context from inputs/results and render the Word document.

Everything the prose template sees is a pre-formatted string or a boolean flag.
Number formatting and the wording decisions that depend on arithmetic live here, so
the template stays a readable document rather than a program.
"""

import json
import math
import os
from datetime import date
from io import BytesIO
from typing import Dict, List, Optional

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from models.smoke_layer_models import (
    SmokeLayerBuilding,
    SmokeLayerInputs,
    SmokeLayerProjectDetails,
    SmokeLayerReportDetails,
    SmokeLayerResults,
    single_building_details,
)
from services.warehouse_report.builder import DocBuilder
from services.warehouse_report.figures import report_figures

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates", "warehouse")
BLOCKS_DIR = os.path.join(TEMPLATE_DIR, "blocks")
SKIN = os.path.join(TEMPLATE_DIR, "skin_single_building.docx")
SITE_PLAN_PLACEHOLDER = os.path.join(BLOCKS_DIR, "site_plan_placeholder.png")
ENGINEERS_PATH = os.path.join(BASE_DIR, "data", "engineers.json")

# Fixed in the browser model (fd-toolstation lib/smoke-layer-types.ts ZONE_CONSTANTS).
AMBIENT_K = 293
RHO_AMBIENT = 1.195
CP = 1.016
MAX_PLUME_RISE_K = 900

GROWTH_RATE_LABELS = {0.0029: "Slow", 0.0117: "Medium", 0.0469: "Fast", 0.188: "Ultra-fast"}
DEFAULT_PRE_MOVEMENT = 180
DEFAULT_FLOW_RATE = 1.33
FLOOR_NAMES = ["Ground", "First", "Second", "Third", "Fourth", "Fifth", "Sixth", "Seventh"]

# No trim_blocks: it would also eat the newline after an inline "{% endif %}" that
# ends a line, gluing the next paragraph on. Block-only lines leave blank lines
# behind instead, which the builder ignores.
_env = Environment(loader=FileSystemLoader(TEMPLATE_DIR), undefined=StrictUndefined)


def _g(value: float) -> str:
    return f"{value:g}"


def _int(value: float) -> str:
    return f"{round(value):,}"


def _floor_list(storeys: int, has_undercroft: bool) -> str:
    start = 1 if has_undercroft else 0
    names = [f"{FLOOR_NAMES[i]} Floor" for i in range(start, start + storeys)]
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + " and " + names[-1]


def _growth_rate_label(fgr: float) -> str:
    for value, label in GROWTH_RATE_LABELS.items():
        if math.isclose(fgr, value, rel_tol=1e-6):
            return label
    return f"custom ({fgr:g} kW/s²)"


def _email_prefix(engineer_name: str) -> str:
    try:
        with open(ENGINEERS_PATH, encoding="utf-8") as f:
            engineers = json.load(f)
    except OSError:
        return ""
    row = next((e for e in engineers if e["full_name"] == engineer_name), None)
    return row["email_prefix"] if row else ""


def build_context(
    project_name: str,
    engineer_name: str,
    inputs: SmokeLayerInputs,
    results: SmokeLayerResults,
    details: SmokeLayerReportDetails,
) -> dict:
    fitout_known = bool(details.intended_purpose.strip())
    racking_percent = round(inputs.racking_perc * 100)
    smoke_area = inputs.room_area * (1 - inputs.racking_perc)
    travel_time = math.ceil(inputs.maximum_travel_distance / inputs.walking_speed)
    assessment_minutes = _g(inputs.assessment_time / 60)
    office_known = bool(details.office_storeys and details.office_height.strip() and details.staircases)
    growth_label = _growth_rate_label(inputs.fgr)
    occupancy_source = details.occupancy_source.strip() or "the Fire Strategy Report"

    if details.occupancy_known:
        occupancy_basis = (
            f"Occupancy rates are based on values given in {occupancy_source}[2]. "
            "(These assume a rate of one person per 30 m² of floor area, with the full floor "
            "area of the warehouse used for calculation, as per the Approved Document B[3].)"
        )
    else:
        occupancy_basis = (
            "Occupancy rates are based on guidance from the Approved Document B[3]. These assume "
            "a rate of one person per 30 m² of floor area, with the full floor area of the "
            "warehouse used for calculation."
        )

    occupancy = _int(inputs.occupancy)
    if details.number_of_doors and details.door_width_mm:
        door_sentence = (
            f"With an estimated warehouse population of {occupancy} people and "
            f"{details.number_of_doors} doors (one of which is discounted), each with a "
            f"{_g(details.door_width_mm)}mm clear width, the total travel time through the doors is "
            f"{_int(results.queue_time)} seconds."
        )
    else:
        door_sentence = (
            f"With an estimated warehouse population of {occupancy} people and a total available "
            f"exit width of {_g(inputs.total_exit_width)}m (with the largest exit discounted), the "
            f"total travel time through the doors is {_int(results.queue_time)} seconds."
        )

    return {
        # identity
        "project_name": project_name.strip() or "[project name]",
        "client_name": details.client_name.strip() or "[client name]",
        "project_location": details.project_location.strip() or "[project location]",
        "building_name": details.building_name.strip() or "[building name]",
        "site_description": details.site_description.strip(),
        "intended_purpose": details.intended_purpose.strip(),
        "site_plan_supplied": False,
        # flags
        "fitout_known": fitout_known,
        "racking_known": details.racking_known,
        "racking_source": details.racking_source.strip() or "indicative fit-out layout",
        "racking_source_given": bool(details.racking_source.strip()),
        "occupancy_known": details.occupancy_known,
        "occupancy_basis": occupancy_basis,
        "occupancy_reference": details.occupancy_reference.strip() or occupancy_source,
        "has_undercroft": details.has_undercroft,
        "aset_triggered": results.aset_triggered,
        "tenability_met": results.margin_of_safety > 0,
        "office_known": office_known,
        "office_storeys": details.office_storeys or 0,
        "storey_word": "storey" if details.office_storeys == 1 else "storeys",
        "floor_list": _floor_list(details.office_storeys, details.has_undercroft) if office_known else "",
        "office_height": details.office_height.strip(),
        "staircases": details.staircases or 0,
        "growth_rate_is_ultra_fast": growth_label == "Ultra-fast",
        "growth_rate_label": growth_label,
        "pre_movement_is_default": math.isclose(inputs.pre_movement_time, DEFAULT_PRE_MOVEMENT),
        "flow_rate_is_default": math.isclose(inputs.flow_rate, DEFAULT_FLOW_RATE),
        # numbers, pre-formatted
        "max_travel_distance": _g(inputs.maximum_travel_distance),
        "excess_over_30": _g(inputs.maximum_travel_distance - 30),
        "excess_over_45": _g(inputs.maximum_travel_distance - 45),
        "racking_percent": str(racking_percent),
        "smoke_area_percent": str(100 - racking_percent),
        "room_area": f"{inputs.room_area:,.0f}",
        "smoke_area": f"{smoke_area:,.0f}",
        "room_height": _g(inputs.room_height),
        "fgr": _g(inputs.fgr),
        "assessment_minutes": assessment_minutes,
        "ambient_c": str(AMBIENT_K - 273),
        "ambient_k": str(AMBIENT_K),
        "rho_ambient": _g(RHO_AMBIENT),
        "cp": _g(CP),
        "max_temp_c": str(AMBIENT_K - 273 + MAX_PLUME_RISE_K),
        "final_height": f"{math.floor(results.final_clear_height * 10) / 10:.1f}",
        "aset": _int(results.aset),
        "rset": _int(results.rset),
        "margin_of_safety": _int(results.margin_of_safety),
        "detection_time": _g(inputs.detection_time),
        "pre_movement_time": _g(inputs.pre_movement_time),
        "walking_speed": _g(inputs.walking_speed),
        "travel_time": str(travel_time),
        "queue_time": _int(results.queue_time),
        "flow_rate": _g(inputs.flow_rate),
        "door_sentence": door_sentence,
    }


def results_table_values(ctx: dict) -> Dict[str, str]:
    """Cell values for the team's ASET/RSET summary table block (blocks/results_table.xml)."""
    more_than = "" if ctx["aset_triggered"] else ">"
    return {
        "DETECTION_TIME": ctx["detection_time"],
        "PRE_MOVEMENT_TIME": ctx["pre_movement_time"],
        "TRAVEL_TIME": ctx["travel_time"],
        "QUEUE_TIME": ctx["queue_time"],
        "RSET": ctx["rset"],
        "ASET": more_than + ctx["aset"],
        "MARGIN_OF_SAFETY": more_than + ctx["margin_of_safety"],
    }


def render_text(ctx: dict) -> str:
    """The rendered line-oriented body, before it becomes Word paragraphs."""
    return _env.get_template("report_single_building.j2").render(**ctx)


def render_report(
    project_name: str,
    engineer_name: str,
    inputs: SmokeLayerInputs,
    results: SmokeLayerResults,
    details: Optional[SmokeLayerReportDetails] = None,
    today: Optional[date] = None,
) -> BytesIO:
    details = details or SmokeLayerReportDetails()
    today = today or date.today()
    ctx = build_context(project_name, engineer_name, inputs, results, details)

    builder = DocBuilder(SKIN, BLOCKS_DIR)
    builder.substitute(
        {
            "PROJECT_NAME": ctx["project_name"],
            "CLIENT_NAME": ctx["client_name"],
            "TODAYS_DATE": f"{today.day} {today:%B %Y}",
            "AUTHOR_NAME": engineer_name.strip() or "Fire Dynamics Group",
            "EMAIL_PREFIX": _email_prefix(engineer_name),
        }
    )

    figures: Dict[str, object] = dict(report_figures(inputs, results))
    figures["site_plan"] = SITE_PLAN_PLACEHOLDER
    # The calculation renders twice (section 3 and Appendix A); the appendix uses
    # "_a" keys so its figures number separately. Same images, deduplicated by docx.
    for key in list(figures):
        figures[key + "_a"] = figures[key]

    builder.render(render_text(ctx), figures=figures, substitutions=results_table_values(ctx))
    return builder.save()


# ---------------------------------------------------------------- several buildings

NUMBER_WORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"]
SHARED_PARAMS = {
    "fgr": "fire growth rate",
    "detection_time": "detection time",
    "pre_movement_time": "pre-movement time",
    "walking_speed": "walking speed",
    "flow_rate": "flow rate",
    "assessment_time": "assessment period",
    "reference_height": "reference height",
}


def _join_names(names: List[str]) -> str:
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + " and " + names[-1]


def _number_word(n: int) -> str:
    return NUMBER_WORDS[n] if n < len(NUMBER_WORDS) else str(n)


def _door_columns(building: SmokeLayerBuilding) -> Dict[str, str]:
    doors = [d for d in building.details.doors if d.count]
    if not doors:
        return {"number_of_doors": "\u2014", "width_of_doors": "\u2014"}
    widths = sorted({d.width_mm for d in doors})
    return {
        "number_of_doors": str(sum(d.count for d in doors)),
        "width_of_doors": " / ".join(_g(w) for w in widths),
    }


def build_multi_context(
    project_name: str,
    engineer_name: str,
    project: SmokeLayerProjectDetails,
    buildings: List[SmokeLayerBuilding],
) -> dict:
    """Project-level context plus one single-building context per building.

    Shared parameters (growth rate, detection, pre-movement, walking speed, flow rate,
    assessment period, reference height) are quoted from the first building; if any
    building differs the template gets an engineer prompt naming them.
    """
    if not buildings:
        raise ValueError("at least one building is required")
    per_building = []
    for i, b in enumerate(buildings, start=1):
        ctx = build_context(project_name, engineer_name, b.inputs, b.results, single_building_details(project, b))
        ctx.update(_door_columns(b))
        ctx["name"] = b.name
        ctx["key"] = f"b{i}"
        ctx["occupancy"] = _int(b.inputs.occupancy)
        ctx["over_220"] = b.inputs.occupancy > 220
        ctx["over_45"] = b.inputs.maximum_travel_distance > 45
        ctx["office_row_known"] = bool(b.details.office_storeys and b.details.office_height.strip())
        ctx["floor_list"] = (
            _floor_list(b.details.office_storeys, b.details.has_undercroft) if ctx["office_row_known"] else "\u2014"
        )
        ctx["office_height"] = b.details.office_height.strip() or "\u2014"
        per_building.append(ctx)

    first = per_building[0]
    names = [c["name"] for c in per_building]
    racking = [c["racking_percent"] for c in per_building]
    known = [b.details.racking_known for b in buildings]
    triggered = [c["aset_triggered"] for c in per_building]
    differ = [
        label for attr, label in SHARED_PARAMS.items()
        if len({getattr(b.inputs, attr) for b in buildings}) > 1
    ]
    aset_names = [c["name"] for c in per_building if c["aset_triggered"]]
    no_aset_names = [c["name"] for c in per_building if not c["aset_triggered"]]
    over_220 = [c["name"] for c in per_building if c["over_220"]]

    ctx = {key: first[key] for key in (
        "project_name", "client_name", "project_location", "site_description", "intended_purpose",
        "site_plan_supplied", "fitout_known", "occupancy_known", "occupancy_basis", "occupancy_reference",
        "racking_source", "racking_source_given", "growth_rate_is_ultra_fast", "growth_rate_label", "fgr",
        "assessment_minutes", "ambient_c", "ambient_k", "rho_ambient", "cp", "max_temp_c",
        "detection_time", "pre_movement_time", "pre_movement_is_default", "walking_speed", "flow_rate",
        "flow_rate_is_default", "smoke_area_percent",
    )}
    ctx.update({
        "buildings": per_building,
        "building_names": _join_names(names),
        "number_of_buildings": _number_word(len(buildings)),
        "staircases": project.staircases or 0,
        "office_known_all": all(c["office_row_known"] for c in per_building) and bool(project.staircases),
        "office_missing_names": _join_names([c["name"] for c in per_building if not c["office_row_known"]]),
        "racking_known_all": all(known),
        "racking_known_none": not any(known),
        "racking_same": len(set(racking)) == 1,
        "racking_percent": first["racking_percent"],
        "has_undercroft_any": any(b.details.has_undercroft for b in buildings),
        "all_over_45": all(c["over_45"] for c in per_building),
        "tenability_met_all": all(c["tenability_met"] for c in per_building),
        "aset_all": all(triggered),
        "aset_none": not any(triggered),
        "aset_names": _join_names(aset_names),
        "no_aset_names": _join_names(no_aset_names),
        "no_aset_this_these": "this unit" if len(no_aset_names) == 1 else "these units",
        "all_over_220": all(c["over_220"] for c in per_building),
        "over_220_names": _join_names(over_220),
        "doors_missing_names": _join_names([c["name"] for c in per_building if c["number_of_doors"] == "\u2014"]),
        "shared_params_differ": _join_names(differ),
    })
    return ctx


def multi_tables(ctx: dict) -> Dict[str, List[List[str]]]:
    """Rows for the per-building tables, for the body and again ("_a") for the appendix."""
    b = ctx["buildings"]
    if ctx["racking_known_all"] and ctx["racking_same"]:
        area = [["Building", "Floor Area (m\u00b2)", f"Floor Area with {ctx['racking_percent']}% Obstructed (m\u00b2)"]]
        area += [[c["name"], c["room_area"], c["smoke_area"]] for c in b]
    else:
        area = [["Building", "Floor Area (m\u00b2)", "Percentage Obstructed (%)", "Non-Obstructed Floor Area (m\u00b2)"]]
        area += [[c["name"], c["room_area"], c["racking_percent"], c["smoke_area"]] for c in b]

    def more(c):
        return "" if c["aset_triggered"] else ">"

    results = [["", "Factor"] + [f"{c['name']} (s)" for c in b]]
    results += [
        ["RSET", "TDET"] + [c["detection_time"] for c in b],
        ["^", "TALARM"] + ["0" for _ in b],
        ["^", "TPRE"] + [c["pre_movement_time"] for c in b],
        ["^", "TTRAV \u2013 Travel Time"] + [c["travel_time"] for c in b],
        ["^", "TTRAV \u2013 Queueing Time"] + [c["queue_time"] for c in b],
        ["^", "Total RSET"] + [c["rset"] for c in b],
        ["ASET", "Calculated ASET"] + [more(c) + c["aset"] for c in b],
        ["^", "Margin of Safety"] + [more(c) + c["margin_of_safety"] for c in b],
    ]
    tables = {
        "office": [["Building", "Office Level", "Height of Top Floor Above Ground Level (m)"]]
        + [[c["name"], c["floor_list"], c["office_height"]] for c in b],
        "travel": [["Building", "Maximum Direct Travel Distance (m)"]] + [[c["name"], c["max_travel_distance"]] for c in b],
        "racking": [["Building", "Racking Percentage (%)"]] + [[c["name"], c["racking_percent"]] for c in b],
        "margin": [["Building", "Margin of Safety (s)"]] + [[c["name"], more(c) + c["margin_of_safety"]] for c in b],
        "height": [["Building", "Average Internal Height (m)"]] + [[c["name"], c["room_height"]] for c in b],
        "area": area,
        "aset": [["Building", "Calculated ASET (s)"]] + [[c["name"], more(c) + c["aset"]] for c in b],
        "travel_time": [["Building", "Maximum Direct Travel Distance (m)", "Travel Time (s)"]]
        + [[c["name"], c["max_travel_distance"], c["travel_time"]] for c in b],
        "doors": [["Building", "Number of Occupants", "Number of Doors", "Width of Doors (mm)", "Travel Time through the Doors (s)"]]
        + [[c["name"], c["occupancy"], c["number_of_doors"], c["width_of_doors"], c["queue_time"]] for c in b],
        "results": results,
    }
    for key in list(tables):
        if key != "office":
            tables[key + "_a"] = tables[key]
    return tables


def render_multi_text(ctx: dict) -> str:
    return _env.get_template("report_multiple_buildings.j2").render(**ctx)


def render_multi_report(
    project_name: str,
    engineer_name: str,
    project: SmokeLayerProjectDetails,
    buildings: List[SmokeLayerBuilding],
    today: Optional[date] = None,
) -> BytesIO:
    """The multi-building report. One building is rendered with the single-building template."""
    if len(buildings) == 1:
        return render_report(project_name, engineer_name, buildings[0].inputs, buildings[0].results,
                             single_building_details(project, buildings[0]), today)
    today = today or date.today()
    ctx = build_multi_context(project_name, engineer_name, project, buildings)

    builder = DocBuilder(SKIN, BLOCKS_DIR)
    builder.substitute(
        {
            "PROJECT_NAME": ctx["project_name"],
            "CLIENT_NAME": ctx["client_name"],
            "TODAYS_DATE": f"{today.day} {today:%B %Y}",
            "AUTHOR_NAME": engineer_name.strip() or "Fire Dynamics Group",
            "EMAIL_PREFIX": _email_prefix(engineer_name),
        }
    )

    figures: Dict[str, object] = {"site_plan": SITE_PLAN_PLACEHOLDER}
    # One fire curve (the growth rate is shared), then a temperature + height pair per building.
    figures["hrr"] = report_figures(buildings[0].inputs, buildings[0].results)["hrr"]
    for b, c in zip(buildings, ctx["buildings"]):
        figs = report_figures(b.inputs, b.results)
        figures[f"temperature_{c['key']}"] = figs["temperature"]
        figures[f"height_{c['key']}"] = figs["height"]
    for key in list(figures):
        figures[key + "_a"] = figures[key]

    builder.render(render_multi_text(ctx), figures=figures, tables=multi_tables(ctx))
    return builder.save()
