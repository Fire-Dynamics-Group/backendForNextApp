"""House-style report figures for the warehouse smoke layer report.

Re-plots the browser results with matplotlib; nothing is recomputed. The styling
mirrors the MACS+ / time-eq Monte Carlo report charts (i-macs macs_automation/report.py,
backend-time-eq-monte-carlo services/teq_reliability_charts.py) so the FDG report
figures read as one family: Segoe UI, light grey text and axes, hairline grid, mid
blue and coral series, red dashed limit lines, legend in a strip above the axes,
axes pinned to the origin.
"""

import threading
from io import BytesIO
from typing import Dict, List, Optional, Tuple

import matplotlib

matplotlib.use("Agg")  # no display on Railway
import matplotlib.pyplot as plt  # noqa: E402

from models.smoke_layer_models import SmokeLayerInputs, SmokeLayerResults, SmokeLayerStep  # noqa: E402

# rc_context and pyplot's figure registry are process-global; FastAPI runs sync
# endpoints on a threadpool, so concurrent reports must not interleave.
MPL_LOCK = threading.RLock()

HOUSE_LIGHT_TEXT = (0.59, 0.56, 0.56)
HOUSE_CHART_CONFIG = {
    "font.family": "Segoe UI",
    "xtick.color": HOUSE_LIGHT_TEXT,
    "ytick.color": HOUSE_LIGHT_TEXT,
    "axes.titlecolor": HOUSE_LIGHT_TEXT,
    "axes.labelcolor": HOUSE_LIGHT_TEXT,
    "axes.edgecolor": HOUSE_LIGHT_TEXT,
    "legend.labelcolor": HOUSE_LIGHT_TEXT,
    "figure.figsize": [6, 4],
    "axes.grid": True,
    "grid.linewidth": "0.05",
    "grid.color": HOUSE_LIGHT_TEXT,
}
HOUSE_BLUE = "#4798EA"
HOUSE_CORAL = "coral"
HOUSE_LIMIT = "red"
HOUSE_MARKER = HOUSE_LIGHT_TEXT
HOUSE_DPI = 300

TENABILITY_HEIGHT = 2.0

Series = Tuple[str, str, str]  # (attribute, label, colour)
Line = Tuple[float, str, str]  # (value, label, colour)


def _place_legend(ax) -> None:
    """Legend in a strip above the axes, stretched to exactly the plot width."""
    handles, _ = ax.get_legend_handles_labels()
    if handles:
        # Two columns once there are more than two entries: four labels at the
        # default size overflow a single row on a 6-inch chart.
        ax.legend(loc="lower left", bbox_to_anchor=(0, 1.02, 1, 0.102), mode="expand",
                  ncol=min(len(handles), 2), borderaxespad=0)


def _plot(
    steps: List[SmokeLayerStep],
    series: List[Series],
    ylabel: str,
    hlines: Optional[List[Line]] = None,
    vlines: Optional[List[Line]] = None,
) -> BytesIO:
    times = [s.time for s in steps]
    fig, ax = plt.subplots()

    for attr, label, colour in series:
        ax.plot(times, [getattr(s, attr) for s in steps], color=colour, linewidth=1.5, label=label)
    for value, label, colour in hlines or []:
        ax.axhline(value, color=colour, linestyle="--", linewidth=1.5, label=label)
    for value, label, colour in vlines or []:
        ax.axvline(value, color=colour, linestyle="--", linewidth=1.0, label=label)

    ax.set_xlabel("Time (s)")
    ax.set_ylabel(ylabel)
    # Pinned to the origin: no autoscale padding before zero.
    ax.set_xlim(0, times[-1] if len(times) > 1 else max(times[-1], 1))
    ax.set_ylim(bottom=0)
    _place_legend(ax)

    stream = BytesIO()
    fig.savefig(stream, format="png", dpi=HOUSE_DPI, bbox_inches="tight")
    plt.close(fig)
    stream.seek(0)
    return stream


def report_figures(inputs: SmokeLayerInputs, results: SmokeLayerResults) -> Dict[str, BytesIO]:
    """The three result figures the report body refers to, keyed for the template."""
    with MPL_LOCK, plt.rc_context(HOUSE_CHART_CONFIG):
        return _render(inputs, results)


def _render(inputs: SmokeLayerInputs, results: SmokeLayerResults) -> Dict[str, BytesIO]:
    height_lines: List[Line] = [(TENABILITY_HEIGHT, f"{TENABILITY_HEIGHT:g} m tenability limit", HOUSE_LIMIT)]
    if inputs.reference_height != TENABILITY_HEIGHT:
        height_lines.append((inputs.reference_height, f"{inputs.reference_height:g} m reference", HOUSE_MARKER))

    markers: List[Line] = []
    if results.aset_triggered:
        markers.append((results.aset, f"ASET {round(results.aset):,} s", HOUSE_LIMIT))
    if results.steps and results.rset <= results.steps[-1].time:
        markers.append((results.rset, f"RSET {round(results.rset):,} s", HOUSE_MARKER))

    return {
        "hrr": _plot(
            results.steps,
            [("hrr", "Total HRR", HOUSE_BLUE), ("convective_hrr", "Convective HRR", HOUSE_CORAL)],
            "Heat release rate (MW)",
        ),
        "temperature": _plot(
            results.steps,
            [("smoke_layer_temp", "Smoke layer", HOUSE_BLUE), ("added_smoke_temp", "Smoke entering layer", HOUSE_CORAL)],
            "Temperature (°C)",
            vlines=markers,
        ),
        "height": _plot(
            results.steps,
            [("clear_height", "Smoke layer height", HOUSE_BLUE)],
            "Height above floor (m)",
            hlines=height_lines,
            vlines=markers,
        ),
    }
