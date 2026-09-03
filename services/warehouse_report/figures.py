"""House-style report figures for the warehouse smoke layer report.

Re-plots the browser results with matplotlib; nothing is recomputed. The styling
follows the common-corridor CFD report charts (cfd-post-processing pipeline/hrr_graph.py,
constants.py) so the FDG report figures read as one family: Segoe UI, light grey text
and axes, hairline grid, thin mid-blue and coral series, legend centred below the
axes with no frame, axes pinned to the origin. Every static line has its own colour
and dash pattern so none can be confused in the legend (agreed with Ian, Sep 2026):
tenability limit red dash-dot, RSET blue dotted, ASET green dashed. The tenability
limit is drawn at the run's tenability height, which is the height that defines ASET
(head height, 2 m, unless the engineer set another).
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
    "axes.labelsize": 10,
    "xtick.labelsize": 8,
    "ytick.labelsize": 8,
    "legend.fontsize": 8,
}
HOUSE_BLUE = "#4798EA"
HOUSE_CORAL = "coral"
HOUSE_DPI = 300
SERIES_WIDTH = 0.75

# (colour, linestyle, linewidth) per static line role.
TENABILITY_STYLE = ("red", "-.", 0.75)
RSET_STYLE = ("blue", ":", 1.0)
ASET_STYLE = ("green", "--", 0.75)

Series = Tuple[str, str, str]  # (attribute, label, colour)
Line = Tuple[float, str, Tuple[object, str, float]]  # (value, label, style)


def _place_legend(ax) -> None:
    """Legend centred below the axes, no frame, as the CFD report charts do."""
    handles, _ = ax.get_legend_handles_labels()
    if handles:
        ax.legend(loc="lower center", bbox_to_anchor=(0.5, -0.37), frameon=False,
                  ncol=3 if len(handles) > 4 else 2)


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
        ax.plot(times, [getattr(s, attr) for s in steps], color=colour, linewidth=SERIES_WIDTH, label=label)
    for value, label, (colour, style, width) in hlines or []:
        ax.axhline(value, color=colour, linestyle=style, linewidth=width, label=label)
    for value, label, (colour, style, width) in vlines or []:
        ax.axvline(value, color=colour, linestyle=style, linewidth=width, label=label)

    ax.set_xlabel("Time (Seconds)")
    ax.set_ylabel(ylabel)
    # Pinned to the origin: no autoscale padding before zero.
    ax.set_xlim(0, times[-1] if len(times) > 1 else max(times[-1], 1))
    # Bottom pinned at zero, top rounded up to the next major tick so the frame
    # closes on a labelled line rather than an autoscaled 189 or 15.75.
    ax.set_ylim(bottom=0)
    top = ax.get_ylim()[1]
    ax.set_ylim(0, max(t for t in ax.yaxis.get_major_locator().tick_values(0, top) if t >= top))
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
    limit = inputs.tenability_height
    height_lines: List[Line] = [(limit, f"Tenability Limit ({limit:g}m)", TENABILITY_STYLE)]

    markers: List[Line] = []
    if results.steps and results.rset <= results.steps[-1].time:
        markers.append((results.rset, f"RSET ({round(results.rset):,}s)", RSET_STYLE))
    if results.aset_triggered:
        markers.append((results.aset, f"ASET ({round(results.aset):,}s)", ASET_STYLE))

    return {
        "hrr": _plot(
            results.steps,
            [("hrr", "Total HRR", HOUSE_BLUE), ("convective_hrr", "Convective HRR", HOUSE_CORAL)],
            "Heat Release Rate (MW)",
        ),
        "temperature": _plot(
            results.steps,
            [("smoke_layer_temp", "Smoke Layer Temperature", HOUSE_BLUE),
             ("added_smoke_temp", "Temperature of Smoke Entering Layer", HOUSE_CORAL)],
            "Temperature (°C)",
            vlines=markers,
        ),
        "height": _plot(
            results.steps,
            [("clear_height", "Smoke Layer Height", HOUSE_BLUE)],
            "Smoke Layer Height (m)",
            hlines=height_lines,
            vlines=markers,
        ),
    }
