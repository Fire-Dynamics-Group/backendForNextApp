"""Render the warehouse smoke layer Word report.

This module formats numbers it is given — it does not run the zone model. The
calculation lives in the browser (fd-toolstation, lib/smoke-layer-calc.ts) and the
results arrive with the request, so the report always matches what the engineer saw.

The document itself is assembled by ``services.warehouse_report`` from the team's
report skin, a prose template and extracted equation blocks.
"""

from io import BytesIO
from typing import Optional

from models.smoke_layer_models import SmokeLayerInputs, SmokeLayerReportDetails, SmokeLayerResults
from services.warehouse_report.render import render_report


def generate_smoke_layer_report(
    project_name: str,
    engineer_name: str,
    inputs: SmokeLayerInputs,
    results: SmokeLayerResults,
    details: Optional[SmokeLayerReportDetails] = None,
) -> BytesIO:
    """Build the Word report and return it as a BytesIO stream."""
    return render_report(project_name, engineer_name, inputs, results, details)
