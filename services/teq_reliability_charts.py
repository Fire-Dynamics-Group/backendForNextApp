"""House-style report charts for the time-eq Monte Carlo reliability run.

Two charts, agreed with the team (Aug 2026) to match the MACS+ report charts:

  1. Steel time-temperature spaghetti — every sampled fire's steel curve with
     a dashed line at the critical temperature. Unlike the 60-minute MACS+
     report window, these show the full simulation span: protected members in
     ventilation-starved fires peak well after 60 minutes.
  2. Pass/fail scatter — glazing breakage vs fireload, coloured by whether the
     sample's peak steel temperature reached the critical temperature.

The styling mirrors the i-macs house chart style (macs_automation/report.py)
so the two tools' report figures read as one family. Axes are pinned to start
at zero — no autoscale padding before the origin.
"""
from __future__ import annotations

import io
import threading

from teq_reliability import ReliabilityDetails

# matplotlib's pyplot keeps its figures in process-global state, and FastAPI
# runs sync endpoints on a threadpool — concurrent chart requests must not
# interleave on the same axes.
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
HOUSE_SPAGHETTI = "#4798EA33"     # mid blue at 20% alpha
HOUSE_SCATTER_BLUE = "#4798EA"
HOUSE_CORAL = "coral"
HOUSE_DPI = 300

# Glazing breakage is a share of the opening, stored as a 0-1 fraction but
# labelled "%", matching the MACS+ report scatter.
GLAZING_TICKS = [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]
GLAZING_TICK_LABELS = ["0", "20", "40", "60", "80", "100"]


def _place_legend(plt) -> None:
    """Legend in a strip above the axes, stretched to exactly the plot width —
    outside placement can never cover data on a 10,000-run chart."""
    handles, _ = plt.gca().get_legend_handles_labels()
    plt.legend(loc="lower left", bbox_to_anchor=(0, 1.02, 1, 0.102),
               mode="expand", ncol=max(1, len(handles)), borderaxespad=0)


def _save(plt) -> bytes:
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=HOUSE_DPI, bbox_inches="tight")
    plt.close()
    return buf.getvalue()


def render_reliability_charts(details: ReliabilityDetails) -> dict[str, bytes]:
    """Render both charts as PNG bytes, keyed by their API names."""
    with MPL_LOCK:
        return _render_locked(details)


def _render_locked(details: ReliabilityDetails) -> dict[str, bytes]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    critical = details.result.critical_temp
    failed = details.peak_temp > critical
    charts: dict[str, bytes] = {}

    with plt.rc_context(HOUSE_CHART_CONFIG):
        # ── Steel time-temperature spaghetti ─────────────────────────────────
        plt.plot(details.time_min, details.steel_series[:, 0],
                 color=HOUSE_SPAGHETTI, linewidth=0.5,
                 label="Temperature Curves Calculated")
        if details.steel_series.shape[1] > 1:
            plt.plot(details.time_min, details.steel_series[:, 1:],
                     color=HOUSE_SPAGHETTI, linewidth=0.5)
        plt.axhline(critical, color="red", linestyle="--", linewidth=1.5,
                    label="Critical Temperature")
        _place_legend(plt)
        plt.xlabel("Time (minutes)")
        plt.ylabel("Temperature (C)")
        # Both axes pinned to the origin: no padding before zero.
        plt.xlim(0, float(details.time_min[-1]))
        plt.ylim(0, max(float(details.peak_temp.max()), critical) * 1.08)
        charts["steelTempSpaghetti"] = _save(plt)

        # ── Pass/fail scatter ────────────────────────────────────────────────
        ok = ~failed
        plt.scatter(details.fld[ok], details.glazing_breakage[ok], s=6,
                    color=HOUSE_SCATTER_BLUE,
                    label=f"Temperature < {critical:g}C")
        if failed.any():
            plt.scatter(details.fld[failed], details.glazing_breakage[failed],
                        s=8, color=HOUSE_CORAL,
                        label=f"Temperature >= {critical:g}C")
        plt.xlabel("Fireload (MJ/m2)")
        plt.ylabel("Glazing Breakage (%)")
        # A share of the opening: 0 to 100, never outside it; the fireload
        # axis starts at zero (the Gumbel fit's rare negative samples fall
        # outside the frame rather than padding the chart before zero).
        plt.ylim(0.0, 1.0)
        plt.yticks(GLAZING_TICKS, GLAZING_TICK_LABELS)
        plt.xlim(left=0)
        _place_legend(plt)
        charts["passFailScatter"] = _save(plt)

    return charts
