"""Generate EFS Word report using docxtpl."""

import os
from io import BytesIO
from typing import List

from docxtpl import DocxTemplate

from services.efs_calculator import run_single_calc

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE_PATH = os.path.join(BASE_DIR, "templates", "efs_report_template.docx")


def generate_efs_report(
    height_list: List[float],
    width_list: List[float],
    boundary_dist_list: List[float],
    has_suppression_list: List[bool],
    is_commercial: bool = True,
    building_fire_resistance_period: int = 60,
) -> BytesIO:
    """Generate an EFS Word report and return as BytesIO stream."""

    doc = DocxTemplate(TEMPLATE_PATH)

    elevations_list = []
    elevation_obj = []

    for idx in range(len(height_list)):
        height = height_list[idx]
        width = width_list[idx]
        boundary_dist = boundary_dist_list[idx]
        has_suppression = has_suppression_list[idx]

        percentage, actual_percentage, actual_area, allowable_area, actual_allowable_area, area, bre_height, bre_width = run_single_calc(
            height, width, boundary_dist, has_suppression, is_commercial
        )

        if boundary_dist < 1:
            bd_display = "<1"
            width_d = "-"
            height_d = "-"
            bre_height_d = "-"
            bre_width_d = "-"
            percentage = 0
            percentage_s = "0%"
            allowable_area_d = "-"
            actual_area_d = "-"
            actual_allowable_area_d = "-"
            actual_percentage_s = "-"
        elif boundary_dist == 1:
            bd_display = str(boundary_dist)
            width_d = "-"
            height_d = "-"
            bre_height_d = "-"
            bre_width_d = "-"
            percentage_s = "0%"
            allowable_area_d = "-"
            actual_area_d = "-"
            actual_allowable_area_d = "-"
            actual_percentage_s = "-"
        elif percentage == 100:
            bd_display = str(boundary_dist)
            width_d = width
            height_d = height
            bre_height_d = bre_height
            bre_width_d = bre_width
            percentage_s = "100%"
            allowable_area_d = "-"
            actual_area_d = "-"
            actual_allowable_area_d = "-"
            actual_percentage_s = "-"
        else:
            bd_display = ">120" if boundary_dist > 120 else str(boundary_dist)
            width_d = width
            height_d = height
            bre_height_d = bre_height
            bre_width_d = bre_width
            percentage_s = str(round(percentage, 1)) + "%"
            allowable_area_d = round(allowable_area, 1)
            actual_area_d = actual_area
            actual_allowable_area_d = actual_allowable_area
            actual_percentage_s = str(actual_percentage) + "%"

        elevations_list.append([
            bd_display, width_d, height_d, bre_height_d, bre_width_d,
            percentage_s, allowable_area_d, actual_area_d,
            actual_allowable_area_d, actual_percentage_s,
        ])

        elevation_obj.append({
            "BRE_perc": percentage_s if isinstance(percentage_s, str) else str(round(percentage, 1)) + "%",
            "perc": actual_percentage_s,
            "ER_area": actual_area_d,
            "allow_area": allowable_area_d,
            "BRE_area": area,
            "BR_height": bre_height_d,
            "BR_width": bre_width_d,
            "b_dist": bd_display,
            "ER_height": height_d,
            "ER_width": width_d,
            "less_1m": boundary_dist < 1,
        })

    # Build conditional text
    unprotected_bool_list = [
        obj["BRE_perc"] == "100%" or obj["perc"] == "100.0%"
        for obj in elevation_obj
    ]
    all_unprotected = True not in unprotected_bool_list

    elevations_less_1m_bool_list = [obj["less_1m"] for obj in elevation_obj]
    elevations_less_1m_list = [
        str(i + 1) for i, v in enumerate(elevations_less_1m_bool_list) if v
    ]
    has_elevations_less_1m = len(elevations_less_1m_list) > 0

    has_elevations_protected_bool_list = [
        not unprotected_bool_list[i] and not elevations_less_1m_bool_list[i]
        for i in range(len(unprotected_bool_list))
    ]
    has_elevations_protected = True in has_elevations_protected_bool_list
    elevations_protected_list = [
        str(i + 1) for i, v in enumerate(has_elevations_protected_bool_list) if v
    ]
    elevations_protected_percentage_list = [
        elevation_obj[i]["perc"]
        for i, v in enumerate(has_elevations_protected_bool_list) if v
    ]

    some_unprotected_list = [
        str(i + 1) for i, v in enumerate(unprotected_bool_list) if v
    ]
    some_unprotected = len(some_unprotected_list) > 0

    frp = building_fire_resistance_period

    # Elevations protected text
    if elevations_protected_list:
        if len(elevations_protected_list) == 1:
            plural = "elevation"
            this_text = "this elevation"
            list_text = elevations_protected_list[0]
            perc_text = str(elevations_protected_percentage_list[0])
        else:
            plural = "elevations"
            this_text = "these elevations"
            list_text = ", ".join(elevations_protected_list[:-1]) + " and " + elevations_protected_list[-1]
            perc_text = ", ".join(str(p) for p in elevations_protected_percentage_list[:-1]) + " and " + str(elevations_protected_percentage_list[-1])
        elevations_protected_text = (
            f"The results of the external fire spread assessment show that {plural} {list_text} "
            f"should be designed to achieve {perc_text} fire resistance to prevent external fire spread "
            f"across the site boundary. Specifically, {this_text} should be designed to achieve a fire "
            f"resistance period of {frp} minutes integrity and 15 minutes insulation. The remainder of "
            f"these elevations are not required to be designed to achieve fire resistance."
        )
    else:
        elevations_protected_text = ""

    # Elevations less than 1m text
    if elevations_less_1m_list:
        if len(elevations_less_1m_list) == 1:
            el_plural = "elevation"
        else:
            el_plural = "elevations"
        el_list_text = (
            elevations_less_1m_list[0]
            if len(elevations_less_1m_list) == 1
            else ", ".join(elevations_less_1m_list[:-1]) + " and " + elevations_less_1m_list[-1]
        )
        elevations_less_1m_text = (
            f"Given that the distance to the relevant boundary on {el_plural} {el_list_text} is less than 1m, "
            f"the whole elevation should be designed to achieve a fire resistance period of {frp} minutes "
            f"integrity and {frp} minutes insulation. It is permitted to have some small areas of the elevation "
            f"which do not meet this requirement as long as their size and spacing is as per Diagram 13.5 of "
            f"AD-B (extracted below)."
        )
    else:
        elevations_less_1m_text = ""

    # Some unprotected text
    if some_unprotected_list:
        if len(some_unprotected_list) == 1:
            s_plural = "elevation"
            s_list_text = some_unprotected_list[0]
        else:
            s_plural = "elevations"
            s_list_text = ", ".join(some_unprotected_list[:-1]) + " and " + some_unprotected_list[-1]
        some_unprotected_text = (
            f"The table shows that there is no requirement for {s_plural} {s_list_text} to be designed to "
            f"achieve a particular period of fire resistance to prevent external fire spread across the site boundary."
        )
    else:
        some_unprotected_text = ""

    context = {
        "t": elevations_list,
        "no_ext_fire_spread_needed": False,
        "all_unprotected": all_unprotected,
        "has_elevations_protected": has_elevations_protected,
        "elevations_protected": elevations_protected_list,
        "has_elevations_less_1m": has_elevations_less_1m,
        "elevations_less_1m": elevations_less_1m_list,
        "some_unprotected": some_unprotected,
        "elevations_protected_text": elevations_protected_text,
        "elevations_less_1m_text": elevations_less_1m_text,
        "some_unprotected_text": some_unprotected_text,
    }

    doc.render(context)

    output = BytesIO()
    doc.save(output)
    output.seek(0)
    return output
