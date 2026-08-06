"""Per-FR comparison charts (issue #13/#17): one chart per FR period, panels for
Office / Clothing store / Restaurant, built from the convergence_out study JSONs.

Clothing store FR30 comes from the fast-growth re-run (the engine's Table E.5 /
BS 9999 mapping); its other FRs are growth-rate-insensitive (ventilation-
controlled), so the medium-growth sweep data remains valid for them.

Usage:  python scripts/comparison_charts.py
Writes scripts/convergence_out/comparison_fr{30,60,90}.png
"""
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from convergence_study import envelope_half_width, recommend_n, TOLERANCE

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "convergence_out")

# occupancy -> FR -> (study tag, growth-rate note)
SOURCES = {
    "Office": {30: ("full_fr30-90", "medium"), 60: ("full", "medium"),
               90: ("full_fr30-90", "medium")},
    "Clothing store": {30: ("full_clothing_store_fr30", "fast"),
                       60: ("full_clothing_store", "medium*"),
                       90: ("full_clothing_store", "medium*")},
    "Restaurant": {30: ("full_restaurant", "medium"), 60: ("full_restaurant", "medium"),
                   90: ("full_restaurant", "medium")},
}
COLORS = {"Office": "limegreen", "Clothing store": "deepskyblue",
          "Restaurant": "orange"}


def load(tag):
    with open(os.path.join(OUT_DIR, f"convergence_{tag}.json"), encoding="utf-8") as f:
        return json.load(f)


def main():
    studies = {}
    for occ, by_fr in SOURCES.items():
        for fr, (tag, _) in by_fr.items():
            if tag not in studies:
                studies[tag] = load(tag)

    for fr in (30, 60, 90):
        occs = list(SOURCES)
        fig, axes = plt.subplots(len(occs), 1, figsize=(9, 12), squeeze=False)
        for ax, occ in zip(axes[:, 0], occs):
            tag, growth = SOURCES[occ][fr]
            stats = {int(n): s for n, s in studies[tag]["results"][str(fr)].items()}
            ns = sorted(stats)
            mean = [stats[n]["mean"] for n in ns]
            lo = [stats[n]["min"] for n in ns]
            hi = [stats[n]["max"] for n in ns]
            p_hat = mean[-1]
            c = COLORS[occ]
            ax.fill_between(ns, lo, hi, color=c, alpha=0.45,
                            label="min–max envelope of K repeats")
            ax.plot(ns, mean, "k--", lw=1.2, label="mean of K repeats")
            rec = recommend_n(stats, TOLERANCE)
            if rec is not None:
                ax.axvline(rec, color="crimson", ls="-", lw=1.2, alpha=0.8)
                ax.annotate(f"envelope $\\leq\\pm${TOLERANCE * 100:.1f}%"
                            f"\nfrom N = {rec:,}", xy=(rec, p_hat),
                            xytext=(6, 14), textcoords="offset points",
                            fontsize=8, color="crimson")
            ax.set_xscale("log")
            ax.set_xticks(ns)
            ax.get_xaxis().set_major_formatter(
                plt.FuncFormatter(lambda v, _: f"{int(v):,}"))
            ax.set_ylabel("Reliability estimate")
            ax.set_title(f"{occ} — reliability $\\approx$ {p_hat * 100:.1f}% "
                         f"({growth} growth)", fontsize=10)
            ax.legend(loc="best", fontsize=7)
            ax.grid(True, which="both", alpha=0.25)
        axes[-1, 0].set_xlabel("Number of simulations (nSim)")
        fig.suptitle(f"FR {fr} min — convergence by occupancy (Panattoni geometry, "
                     "PD 7974 Table A.5 fire loads)", y=0.995)
        fig.tight_layout()
        path = os.path.join(OUT_DIR, f"comparison_fr{fr}.png")
        fig.savefig(path, dpi=200)
        plt.close(fig)
        print("wrote", path)

    halfwidth_chart(studies)


def halfwidth_chart(studies):
    """The stopping-rule figure: envelope half-width vs nSim (log-log), one line
    per occupancy x FR cell, with the +/-0.5% tolerance as a horizontal line each
    curve visibly crosses at its own N."""
    fig, ax = plt.subplots(figsize=(9, 6))
    styles = {30: "-", 60: "--", 90: ":"}
    for occ, by_fr in SOURCES.items():
        for fr, (tag, _) in by_fr.items():
            stats = {int(n): s for n, s in studies[tag]["results"][str(fr)].items()}
            ns = sorted(stats)
            ax.plot(ns, [envelope_half_width(stats[n]) * 100 for n in ns],
                    color=COLORS[occ], ls=styles[fr], marker="o", ms=3.5, lw=1.4,
                    label=f"{occ} FR{fr}")
    ax.axhline(TOLERANCE * 100, color="crimson", lw=1.4,
               label=f"tolerance $\\pm${TOLERANCE * 100:.1f}%")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("Number of simulations (nSim)")
    ax.set_ylabel("Run-to-run spread, min–max envelope half-width (±%)")
    ax.set_title("Convergence of the reliability estimate — all occupancies and FR periods")
    ax.legend(fontsize=8, ncol=2)
    ax.grid(True, which="both", alpha=0.25)
    fig.tight_layout()
    path = os.path.join(OUT_DIR, "comparison_halfwidth.png")
    fig.savefig(path, dpi=200)
    plt.close(fig)
    print("wrote", path)


if __name__ == "__main__":
    main()
