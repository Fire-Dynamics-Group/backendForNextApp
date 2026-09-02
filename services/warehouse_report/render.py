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
from typing import Dict, Optional

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from models.smoke_layer_models import SmokeLayerInputs, SmokeLayerReportDetails, SmokeLayerResults
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

    builder.render(render_text(ctx), figures=figures, substitutions=results_table_values(ctx))
    return builder.save()
