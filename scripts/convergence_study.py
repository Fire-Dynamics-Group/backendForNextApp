"""Convergence study for the Monte Carlo TEQ reliability engine (issue #13).

Answers "how many sims are enough?" in the style of the CFDOpenPlan appendix study:
for each nSim, repeat the whole reliability run K times with independent seeds and
plot the spread (2.5-97.5 percentile band) of the reliability estimate against nSim,
with the analytic plain-MC standard error sqrt(p(1-p)/N) overlaid — LHS sampling
should beat the analytic curve, which is part of the story.

Runs OFFLINE against the engine module directly (never through the web endpoint —
the sweep is millions of simulations). Scenario is the Panattoni parity benchmark.

Usage (from the repo root, with the backend venv):
    python scripts/convergence_study.py            # full study (~1 h)
    python scripts/convergence_study.py --quick    # smoke run (~1 min)

Outputs land in scripts/convergence_out/: raw results JSON, chart PNG, write-up MD.
"""
import argparse
import json
import math
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import teq_reliability as tr

# Panattoni benchmark compartment (matches test_teq_reliability.py / the workbook).
# Occupancy is a separate knob: the study repeats across fire-load distributions
# (Gumbel vs log-normal, rising CoV) and the worst-case N across them wins.
PANATTONI = dict(
    floor_area=64 * 13,                                          # 832
    total_area=2 * (64 * 3.5) + 2 * (13 * 3.5) + 2 * (64 * 13),  # 2203
    vent_widths=[0, 0, 64, 0],
    vent_heights=[0, 0, 3.5, 0],
)

DEFAULT_OCCUPANCY = "Office"

# Standard UK fire resistance ratings. Reliability bands they hit vary by
# occupancy (e.g. Office ~0.10 / 0.97 / 0.99, Restaurant ~0.52 / 0.97 / 0.99).
FR_PERIODS = [30, 60, 90]

# nSim -> K seeded repeats. K tapers at large nSim to keep the sweep ~1 h;
# the flattening story is told by the smaller nSim anyway.
FULL_SCHEDULE = {100: 100, 500: 100, 1000: 100, 2000: 100,
                 5000: 100, 10000: 50, 50000: 25}
QUICK_SCHEDULE = {100: 5, 500: 3, 1000: 2}

TOLERANCE = 0.005  # +/- 0.5 percentage points on the reliability estimate

OUT_DIR = os.path.join(os.path.dirname(__file__), "convergence_out")


# ------------------------------------------------------------------ pure logic
def summarize(values) -> dict:
    """Spread statistics of K repeated reliability estimates at one nSim."""
    v = np.asarray(values, dtype=float)
    lo, hi = np.percentile(v, [2.5, 97.5])
    return {
        "k": int(v.size),
        "mean": float(v.mean()),
        "std": float(v.std(ddof=1)) if v.size > 1 else 0.0,
        "min": float(v.min()),
        "max": float(v.max()),
        "p2_5": float(lo),
        "p97_5": float(hi),
        "band_half_width": float((hi - lo) / 2),
    }


def analytic_se(p: float, n: int) -> float:
    """Plain-MC binomial standard error — the overlay LHS is expected to beat."""
    return math.sqrt(max(p * (1.0 - p), 0.0) / n)


def seed_for(base_seed: int, n_sim: int, k: int) -> int:
    """Distinct deterministic seed per (nSim, repeat) cell. k < 1000 assumed."""
    return base_seed + n_sim * 1000 + k


def recommend_n(stats_by_n: dict, tol: float):
    """Smallest nSim whose 95% percentile band half-width is within tol, else None."""
    for n in sorted(stats_by_n):
        if stats_by_n[n]["band_half_width"] <= tol:
            return n
    return None


# ------------------------------------------------------------------ the sweep
def run_study(fr_periods, schedule, base_seed, engine=None, log=None,
              occupancy=DEFAULT_OCCUPANCY) -> dict:
    """Repeat the reliability run K times per (FR, nSim) cell and aggregate spread.

    ``engine`` defaults to ``tr.compute_reliability``; injectable for tests.
    Result dict is JSON-ready (string keys).
    """
    engine = engine or (lambda **kw: tr.compute_reliability(
        **PANATTONI, occupancy=occupancy, combustion_factor=1.0,
        is_sprinklered=False, **kw))
    t0 = time.perf_counter()
    results, raw = {}, {}
    for fr in fr_periods:
        results[str(fr)], raw[str(fr)] = {}, {}
        for n_sim in sorted(schedule):
            k_reps = schedule[n_sim]
            rels = [engine(fr_period_min=fr, n_sim=n_sim,
                           seed=seed_for(base_seed, n_sim, k)).reliability
                    for k in range(k_reps)]
            results[str(fr)][str(n_sim)] = summarize(rels)
            raw[str(fr)][str(n_sim)] = rels
            if log:
                s = results[str(fr)][str(n_sim)]
                log(f"FR{fr} n={n_sim} K={k_reps}: mean={s['mean']:.4f} "
                    f"band=+/-{s['band_half_width']:.4f} "
                    f"[{time.perf_counter() - t0:.0f}s elapsed]")
    return {
        "scenario": f"Panattoni benchmark ({occupancy} 64x13x3.5, one openable "
                    "wall, sect 135, b=1200, 500C, no factors)",
        "occupancy": occupancy,
        "fr_periods": [str(f) for f in fr_periods],
        "schedule": {str(n): k for n, k in schedule.items()},
        "base_seed": base_seed,
        "tolerance": TOLERANCE,
        "results": results,
        "raw": raw,
        "runtime_s": round(time.perf_counter() - t0, 1),
    }


# ------------------------------------------------------------------ outputs
def make_chart(study: dict, path: str):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    frs = study["fr_periods"]
    fig, axes = plt.subplots(len(frs), 1, figsize=(9, 4.5 * len(frs)), squeeze=False)
    palette = ["limegreen", "deepskyblue", "orange", "orchid"]
    for i, (ax, fr) in enumerate(zip(axes[:, 0], frs)):
        stats = study["results"][fr]
        ns = sorted(int(n) for n in stats)
        mean = [stats[str(n)]["mean"] for n in ns]
        lo = [stats[str(n)]["p2_5"] for n in ns]
        hi = [stats[str(n)]["p97_5"] for n in ns]
        p_hat = mean[-1]  # best estimate of true p from the largest nSim
        an_lo = [p_hat - 1.96 * analytic_se(p_hat, n) for n in ns]
        an_hi = [p_hat + 1.96 * analytic_se(p_hat, n) for n in ns]
        c = palette[i % len(palette)]
        ax.fill_between(ns, lo, hi, color=c, alpha=0.45,
                        label="empirical 2.5–97.5% band (LHS engine)")
        ax.plot(ns, mean, "k--", lw=1.2, label="mean of K repeats")
        ax.plot(ns, an_lo, color="dimgray", ls=":", lw=1.5)
        ax.plot(ns, an_hi, color="dimgray", ls=":", lw=1.5,
                label="analytic plain-MC 95% ($\\pm1.96\\sqrt{p(1-p)/N}$)")
        ax.set_xscale("log")
        ax.set_xticks(ns)
        ax.get_xaxis().set_major_formatter(plt.FuncFormatter(lambda v, _: f"{int(v):,}"))
        ax.set_xlabel("Number of simulations (nSim)")
        ax.set_ylabel("Reliability estimate")
        ax.set_title(f"FR {fr} min — spread of reliability estimate vs nSim")
        ax.legend(loc="best", fontsize=8)
        ax.grid(True, which="both", alpha=0.25)
    fig.suptitle("Monte Carlo TEQ reliability — convergence study "
                 f"({study.get('occupancy', 'Office')}, Panattoni geometry, "
                 f"base seed {study['base_seed']})", y=0.995)
    fig.tight_layout()
    fig.savefig(path, dpi=300)
    plt.close(fig)


def make_writeup(study: dict, chart_name: str) -> str:
    lines = [
        "# Monte Carlo TEQ reliability — convergence study",
        "",
        f"*Scenario:* {study['scenario']}. *Base seed:* {study['base_seed']}. "
        f"*Runtime:* {study['runtime_s']:.0f} s. "
        f"*Repeats per nSim (K):* {study['schedule']}.",
        "",
        "For each nSim the full reliability run was repeated K times with independent",
        "seeds; the spread of the K estimates measures run-to-run variability at that",
        "nSim. The chart shows the empirical 2.5–97.5 % band beside the analytic",
        "plain-Monte-Carlo 95 % interval ±1.96·√(p(1−p)/N) — the engine samples by",
        "Latin Hypercube, so its empirical band is expected to sit inside the analytic",
        "curve.",
        "",
        f"![convergence chart]({chart_name})",
        "",
        f"Tolerance used: half-band ≤ ±{study['tolerance'] * 100:.1f} percentage points.",
        "",
        "| FR (min) | nSim | K | mean | 95% band half-width | analytic 1.96·SE |",
        "|---|---|---|---|---|---|",
    ]
    recs = {}
    for fr in study["fr_periods"]:
        stats = {int(n): s for n, s in study["results"][fr].items()}
        p_hat = stats[max(stats)]["mean"]
        for n in sorted(stats):
            s = stats[n]
            lines.append(
                f"| {fr} | {n:,} | {s['k']} | {s['mean']:.4f} "
                f"| ±{s['band_half_width']:.4f} | ±{1.96 * analytic_se(p_hat, n):.4f} |")
        recs[fr] = recommend_n(stats, study["tolerance"])
    lines.append("")
    lines.append("## Recommendation")
    lines.append("")
    for fr, rec in recs.items():
        rec_txt = f"nSim = {rec:,}" if rec else "not reached within the sweep"
        lines.append(f"- FR {fr} min: band half-width first within "
                     f"±{study['tolerance'] * 100:.1f} pp at **{rec_txt}**.")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--quick", action="store_true", help="smoke run (~1 min)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--occupancy", default=DEFAULT_OCCUPANCY,
                    help="fire-load distribution to sample (PD 7974 Table A.5 name)")
    ap.add_argument("--fr-periods", type=int, nargs="+", default=FR_PERIODS,
                    help="FR periods (min) spanning mid and high reliability bands")
    args = ap.parse_args()

    schedule = QUICK_SCHEDULE if args.quick else FULL_SCHEDULE
    study = run_study(args.fr_periods, schedule, args.seed, log=print,
                      occupancy=args.occupancy)

    os.makedirs(OUT_DIR, exist_ok=True)
    tag = "quick" if args.quick else "full"
    if args.occupancy != DEFAULT_OCCUPANCY:
        tag += "_" + args.occupancy.lower().replace(" ", "_")
    if args.fr_periods != FR_PERIODS:
        tag += "_fr" + "-".join(str(f) for f in args.fr_periods)
    json_path = os.path.join(OUT_DIR, f"convergence_{tag}.json")
    chart_path = os.path.join(OUT_DIR, f"convergence_{tag}.png")
    md_path = os.path.join(OUT_DIR, f"convergence_{tag}.md")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(study, f, indent=1)
    make_chart(study, chart_path)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(make_writeup(study, os.path.basename(chart_path)))
    print(f"\nWrote {json_path}\n      {chart_path}\n      {md_path}")


if __name__ == "__main__":
    main()
