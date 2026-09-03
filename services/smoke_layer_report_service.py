"""Render the warehouse smoke layer Word report.

This module formats numbers it is given — it does not run the zone model. The
calculation lives in the browser (fd-toolstation, lib/smoke-layer-calc.ts) and the
results arrive with the request, so the report always matches what the engineer saw.

The document itself is assembled by ``services.warehouse_report`` from the team's
report skin, a prose template and extracted equation blocks.
"""

from io import BytesIO
from typing import List, Optional

from models.smoke_layer_models import (
    SmokeLayerBuilding,
    SmokeLayerInputs,
    SmokeLayerProjectDetails,
    SmokeLayerReportDetails,
    SmokeLayerResults,
)
from services.warehouse_report.render import render_multi_report, render_report


def generate_smoke_layer_report(
    project_name: str,
    engineer_name: str,
    inputs: SmokeLayerInputs,
    results: SmokeLayerResults,
    details: Optional[SmokeLayerReportDetails] = None,
    document: str = "report",
) -> BytesIO:
    """Build the Word report (or the standalone calculation appendix) as a BytesIO stream."""
    return render_report(project_name, engineer_name, inputs, results, details, document=document)


def generate_multi_building_report(
    project_name: str,
    engineer_name: str,
    project: Optional[SmokeLayerProjectDetails],
    buildings: List[SmokeLayerBuilding],
    document: str = "report",
) -> BytesIO:
    """Build the report or appendix for one or more buildings and return it as a BytesIO stream."""
    return render_multi_report(project_name, engineer_name, project or SmokeLayerProjectDetails(), buildings,
                               document=document)
