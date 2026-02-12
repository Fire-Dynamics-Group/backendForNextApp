"""Fee calculation helpers for the fee proposal generator."""

import re
from typing import List, Dict, Any


def number_to_word(num: int) -> str:
    """Convert numbers 1-10 to their word equivalents."""
    words = {
        1: "one", 2: "two", 3: "three", 4: "four", 5: "five",
        6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten",
    }
    return words.get(num, str(num))


def get_ordinal_suffix(day: int) -> str:
    """Get the ordinal suffix for a day number (st, nd, rd, th)."""
    if day in (1, 21, 31):
        return "st"
    elif day in (2, 22):
        return "nd"
    elif day in (3, 23):
        return "rd"
    return "th"


def get_legislation(country: str) -> str:
    """Return the appropriate legislation reference based on country."""
    if country == "J":
        return "Building Bye Laws (Jersey) 2007 (Part 2)"
    return "Building Regulations 2010 (Part B)"


def format_riba_stages(stages: List[int]) -> str:
    """Format RIBA stage numbers into a readable string."""
    if not stages:
        return ""
    stages = sorted(set(stages))
    if len(stages) == 1:
        return f"Stage {stages[0]}"
    min_stage = min(stages)
    max_stage = max(stages)
    if len(stages) == max_stage - min_stage + 1:
        return f"Stages {min_stage}-{max_stage}"
    parts = ", ".join(str(s) for s in stages)
    last_comma = parts.rfind(",")
    return "Stages " + parts[:last_comma] + " &" + parts[last_comma + 1:]


def determine_riba_stages(data) -> List[int]:
    """Determine which RIBA stages are included based on service selections."""
    stages = []
    s14 = data.design_stages_1_4
    s5 = data.design_stages_5
    s6 = data.design_stages_6

    if s14.stage_1.included:
        stages.append(1)
    if s14.stage_2.included or s14.london_plan.included or s14.gateway.included:
        stages.append(2)
    if s14.stage_3.included:
        stages.append(3)
    if (s14.stage_4.included or s14.peer_review.included or
        s14.common_corridor_cfd.included or s14.open_plan_cfd.included or
        s14.warehouse_cfd.included or s14.warehouse_structural.included):
        stages.append(4)
    if (s5.construction_advice.included or s5.site_visits.included or
        s5.cfsmp.included or s5.phased_occupation.included or
        s5.site_risk_assessment.included or s5.client_monitoring.included):
        stages.append(5)
    if (s6.regulation_38.included or s6.ews1_forms.included or
        s6.rro_risk_assessment.included):
        stages.append(6)
    return sorted(set(stages))


def build_input_data(data) -> List[Dict[str, Any]]:
    """Build the list of included services with their display data."""
    s14 = data.design_stages_1_4
    s5 = data.design_stages_5
    s6 = data.design_stages_6

    all_services = [
        (s14.stage_1, "RIBA Stage 1", "stage_1"),
        (s14.stage_2, "RIBA Stage 2", "stage_2"),
        (s14.london_plan, "London Plan", "london_plan"),
        (s14.gateway, "Gateway 1", "gateway"),
        (s14.stage_3, "RIBA Stage 3", "stage_3"),
        (s14.stage_4, "RIBA Stage 4", "stage_4"),
        (s14.common_corridor_cfd, "Common Corridor CFD Modelling", "common_corridor_cfd"),
        (s14.open_plan_cfd, "Open Plan Apartments CFD Modelling", "open_plan_cfd"),
        (s14.warehouse_cfd, "CFD Modelling of the Warehouse", "warehouse_cfd"),
        (s14.warehouse_structural, "Structural Fire Engineering Assessment", "warehouse_structural"),
        (s14.peer_review, "Peer Review", "peer_review"),
        (s5.client_monitoring, "RIBA Stage 5: Client Monitoring Strategy", "client_monitoring"),
        (s5.construction_advice, "RIBA Stage 5: Construction Advice", "construction_advice"),
        (s5.site_visits, "RIBA Stage 5: Site Visits", "site_visits"),
        (s5.phased_occupation, "RIBA Stage 5: Phased Occupation Strategy", "phased_occupation"),
        (s5.cfsmp, "RIBA Stage 5: Construction Fire Safety Management Plan", "cfsmp"),
        (s5.site_risk_assessment, "Construction Fire Risk Assessment", "site_risk_assessment"),
        (s6.regulation_38, "RIBA Stage 6: Regulation 38", "regulation_38"),
        (s6.ews1_forms, "RIBA Stage 6: EWS1 Forms", "ews1_forms"),
        (s6.rro_risk_assessment, "RIBA Stage 6: Completion Risk Assessments", "rro_risk_assessment"),
    ]

    result = []
    for svc, ref, key in all_services:
        if svc.included:
            end_date = ""
            if svc.end_date_month and svc.end_date_year:
                if "Select" not in svc.end_date_month and "Select" not in svc.end_date_year:
                    end_date = f"{svc.end_date_month} {svc.end_date_year}"
            result.append({
                "ref": ref,
                "fee": svc.fee,
                "optional": svc.optional,
                "meeting_limit": svc.limit_meetings,
                "meeting_number": svc.meeting_number,
                "end_date": end_date,
                "num_models": svc.num_models,
                "hours_per_month": svc.hours_per_month,
                "meetings_per_month": svc.meetings_per_month,
                "extended_travel_distance": svc.extended_travel_distance,
                "key": key,
            })
    return result


def get_initials(full_name: str) -> str:
    """Extract uppercase initials from a name."""
    cleaned = re.sub(r'\W+', '', full_name)
    return re.sub(r'[a-z]', '', cleaned)
