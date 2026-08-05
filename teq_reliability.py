"""Monte Carlo time-equivalence *reliability* engine (numpy port).

Reliability = the probability that a steel member, fire-protected to a chosen standard
fire-resistance rating, survives a realistic fire in this compartment:

  1. Size protection so the steel reaches its critical temperature exactly at the FR
     period under the standard ISO fire (deterministic; rounded UP to whole mm).
  2. Expose that protected member to N Monte-Carlo EC1 parametric fires with sampled
     fuel load and opening %.
  3. reliability = 1 - failures/N, where failure = peak steel temp > critical temp.

Ported from the standalone PyTorch engine (``04. Monte Carlo TEQ/SB_has_a_go_main.py``)
to numpy + scipy (no torch / pyDOE). Where the source diverged from EC1, the EC1-correct
behaviour is used and noted with ``# FIDELITY``; see PRD for the full list.
"""
from __future__ import annotations

import os
import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy.stats import lognorm, gumbel_l

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CSV_PATH = os.path.join(BASE_DIR, "data", "fire_load_density.csv")

OPENING_FACTOR_ROW = "Opening Factor"  # CSV row defining the window-breakage distribution


# --------------------------------------------------------------------------- params
@dataclass
class SteelParams:
    """Steel + protection + numerical constants. Defaults match the validated source
    (Panattoni). All are overridable per request."""
    thermal_inertia: float = 1200.0      # b-value W/m2 s^0.5 K (a.k.a. thermal inertia)
    sect_factor: float = 135.0           # Ap/V (1/m)
    steel_fail_temp: float = 500.0       # critical temperature (C)
    rho_steel: float = 7850.0
    rho_prot: float = 375.0
    c_prot: float = 1200.0
    therm_cond_prot: float = 0.14
    ambient_temp: float = 20.0
    t_lim_hours: float = 20.0 / 60.0     # fire growth rate (medium = 20 min)
    delta_t_s: float = 5.0               # heat-transfer time step (seconds) — INTERNAL
    calc_time_hours: float = 300.0 / 60.0  # simulated duration (300 min) — INTERNAL


# --------------------------------------------------------------- fire-load distribution
def read_fld_data(occupancy: str, csv_path: str = DEFAULT_CSV_PATH):
    """Return (distribution_type, mean, std_dev) for an occupancy row in the CSV."""
    df = pd.read_csv(csv_path, encoding="utf-8-sig")
    df["Occupancy"] = df["Occupancy"].astype(str).str.strip()
    matches = df[df["Occupancy"] == occupancy]
    if matches.empty:
        raise ValueError(f"Occupancy {occupancy!r} not found in {os.path.basename(csv_path)}")
    row = matches.iloc[0]
    distr_type = str(row["Distribution"]).split()[0]  # "Gumbel"/"Log-normal" (strips spaces)
    mean = float(row["Mean Fire Density"])
    cov = float(row["Coefficient of Variation"])
    return distr_type, mean, mean * cov


def sample_distribution(u: np.ndarray, distr_type: str, mean: float, std_dev: float) -> np.ndarray:
    """Inverse-CDF transform of uniform samples ``u`` for a Gumbel or lognormal fit."""
    if distr_type.startswith("Gumbel"):
        scale = std_dev * math.sqrt(6) / math.pi
        loc = mean + np.euler_gamma * scale
        return gumbel_l.ppf(u, loc, scale)
    # lognormal
    cov = std_dev / mean
    sln = np.sqrt(np.log(1 + cov ** 2))
    mln = np.log(mean) - 0.5 * sln ** 2
    return lognorm.ppf(u, sln, 0, np.exp(mln))


def lhs_uniform(n: int, rng: np.random.Generator) -> np.ndarray:
    """1-D Latin Hypercube sample on [0, 1): one random point per 1/n stratum, shuffled."""
    cut = (np.arange(n) + rng.random(n)) / n
    rng.shuffle(cut)
    return cut


def factorise_opening_percentage(distr: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Window-breakage open fraction = 1 - sampled opening factor; values >1 are redrawn
    uniformly in (0, 1) before the subtraction (faithful to source)."""
    distr = np.asarray(distr, dtype=float).copy()
    above = distr > 1
    distr[above] = rng.uniform(0, 1, size=int(above.sum()))
    return 1.0 - distr


# ------------------------------------------------------------------ opening factor
def calc_op_fac(vent_widths: np.ndarray, vent_heights: np.ndarray,
                total_area: float, perc: np.ndarray) -> np.ndarray:
    """Randomised opening factor per simulation, clamped to [0.01, 0.2].

    ``perc`` (n_sim,) scales each wall's openable area; equivalent height grows as sqrt(perc).
    """
    vent_widths = np.asarray(vent_widths, dtype=float)
    vent_heights = np.asarray(vent_heights, dtype=float)
    av = vent_widths * vent_heights                     # (n_walls,)
    av_sum = av.sum()
    if av_sum <= 0:                                      # no openable area -> minimum O
        return np.full(perc.shape, 0.01)
    perc = np.asarray(perc, dtype=float)
    av_open = av[None, :] * perc[:, None]               # (n_sim, n_walls)
    heq_open = vent_heights[None, :] * (perc[:, None] ** 0.5)
    heq_weighted = (heq_open * av[None, :]).sum(axis=1) / av_sum   # (n_sim,)
    op_fac = (av_open * heq_weighted[:, None] ** 0.5 / total_area).sum(axis=1)
    return np.clip(op_fac, 0.01, 0.2)


# ------------------------------------------------------------- EC1 parametric fire
def _calc_max_temp(t_star_max: np.ndarray) -> np.ndarray:
    return 20 + 1325 * (1 - 0.324 * np.exp(-0.2 * t_star_max)
                        - 0.204 * np.exp(-1.7 * t_star_max)
                        - 0.472 * np.exp(-19 * t_star_max))


def parametric_fire_curves(time_hours: np.ndarray, op_fac: np.ndarray, qtd: np.ndarray,
                           p: SteelParams) -> np.ndarray:
    """EC1 Annex-A parametric gas temperatures, shape (n_steps, n_sim).

    Vectorised over simulations; cooling uses all three EC1 rate branches (625 / 250(3-t*max)
    / 250) — FIDELITY: the source dropped the 625 branch."""
    b = p.thermal_inertia
    t_lim = p.t_lim_hours
    gamma = (op_fac / b) ** 2 / (0.04 / 1160) ** 2
    op_fac_lim = 0.1e-3 * qtd / t_lim
    gamma_lim = (op_fac_lim / b) ** 2 / (0.04 / 1160) ** 2
    # EC1 A.10 k-factor correction
    k = 1 + (op_fac_lim - 0.04) / 0.04 * (qtd - 75) / 75 * (1160 - b) / 1160
    k_mask = (op_fac_lim > 0.04) & (qtd < 75) & (b < 1160)
    gamma_lim = np.where(k_mask, gamma_lim * k, gamma_lim)

    t_max = 0.2e-3 * qtd / op_fac
    is_fuel_ctrl = t_max <= t_lim                       # fuel-controlled (t_max hits the floor)
    t_max_used = np.where(is_fuel_ctrl, t_lim, t_max)
    t_star_max = np.where(is_fuel_ctrl, t_lim * gamma_lim, t_max * gamma)
    max_temp = _calc_max_temp(t_star_max)               # (n_sim,)

    t = time_hours[:, None]                             # (n_steps, 1)
    t_star = np.where(is_fuel_ctrl[None, :], t * gamma_lim[None, :], t * gamma[None, :])
    tsm = t_star_max[None, :]
    growing = 20 + 1325 * (1 - 0.324 * np.exp(-0.2 * t_star)
                           - 0.204 * np.exp(-1.7 * t_star)
                           - 0.472 * np.exp(-19 * t_star))
    # cooling: x = t_lim*gamma/(t_max_used*gamma) when fuel controlled, else 1
    x = np.where(is_fuel_ctrl, t_lim / t_max_used, 1.0)[None, :]
    decay = t_star - tsm * x
    cooling = np.where(
        tsm >= 2.0, max_temp[None, :] - 250 * decay,
        np.where(tsm > 0.5,
                 max_temp[None, :] - 250 * (3 - tsm) * decay,
                 max_temp[None, :] - 625 * decay))       # FIDELITY: 625 branch restored
    temp = np.where(t_star <= tsm, growing, cooling)
    return np.maximum(temp, 20.0)


# --------------------------------------------------------------- protected steel
def _c_steel(temp: np.ndarray) -> np.ndarray:
    """EC3 temperature-dependent specific heat of steel (J/kg.K), vectorised per element.
    FIDELITY: the source evaluated this from column 0 only; here it is per-simulation."""
    temp = np.asarray(temp, dtype=float)
    return np.select(
        [temp < 600, temp < 735, temp < 900],
        [425 + 7.73e-1 * temp - 1.69e-3 * temp ** 2 + 2.22e-6 * temp ** 3,
         666 + 13002 / (738 - temp),
         545 + 17820 / (temp - 731)],
        default=650.0,
    )


def max_protected_steel_temp(gas: np.ndarray, prot_thick_m: float, p: SteelParams) -> np.ndarray:
    """Peak protected-steel temperature per column for a gas-temp array (n_steps, n_cols).

    Time-stepped recursion (EC3 protected section), vectorised over columns; only the running
    max is kept, so memory is O(n_cols) not O(n_steps * n_cols)."""
    steel = gas[0].astype(float).copy()                 # first step = gas (~ambient)
    mx = steel.copy()
    coeff = p.therm_cond_prot * p.sect_factor / (prot_thick_m * p.rho_steel)
    for k in range(1, gas.shape[0]):
        c_steel = _c_steel(steel)
        phi = p.c_prot * p.rho_prot / (c_steel * p.rho_steel) * prot_thick_m * p.sect_factor
        delta = (coeff / c_steel * (gas[k] - steel) / (1 + phi / 3) * p.delta_t_s
                 - (np.exp(phi / 10) - 1) * (gas[k] - gas[k - 1]))
        steel = np.maximum(steel + delta, p.ambient_temp)
        mx = np.maximum(mx, steel)
    return mx


def iso_curve(fr_period_min: float, p: SteelParams) -> np.ndarray:
    """Standard ISO 834 gas temperatures sampled every delta_t, from 0 to the FR period."""
    step_min = p.delta_t_s / 60.0
    t_min = np.arange(0, fr_period_min + step_min, step_min)
    return p.ambient_temp + 345 * np.log10(8 * t_min + 1)


def calc_prot_thickness_mm(fr_period_min: float, p: SteelParams, max_mm: int = 100) -> int:
    """Smallest whole-mm protection thickness keeping the steel below failure temp at the FR
    period under the ISO fire (== ceil of the continuous solution the source found)."""
    gas = iso_curve(fr_period_min, p)[:, None]          # (n_steps, 1)
    for thick_mm in range(1, max_mm + 1):
        if max_protected_steel_temp(gas, thick_mm / 1000.0, p)[0] <= p.steel_fail_temp:
            return thick_mm
    return max_mm


# ----------------------------------------------------------------- reliability
@dataclass
class ReliabilityResult:
    reliability: float
    n_failed: int
    n_sim: int
    fr_period: float
    protection_thickness_mm: int
    b_value: float
    section_factor: float
    critical_temp: float
    factors_applied: dict = field(default_factory=dict)


def compute_reliability(*, occupancy: str, total_area: float, floor_area: float,
                        vent_widths, vent_heights, fr_period_min: float,
                        n_sim: int = 2000, is_sprinklered: bool = False,
                        combustion_factor: float = 0.8, sprinkler_factor: float = 0.65,
                        params: SteelParams | None = None, csv_path: str = DEFAULT_CSV_PATH,
                        chunk_size: int = 2000, seed: int | None = None) -> ReliabilityResult:
    """Run the Monte Carlo reliability assessment for one compartment + FR period."""
    p = params or SteelParams()
    rng = np.random.default_rng(seed)

    # 1. deterministic protection sizing
    prot_thick_mm = calc_prot_thickness_mm(fr_period_min, p)
    prot_thick_m = prot_thick_mm / 1000.0

    # 2. sample the two stochastic inputs (independent LHS columns) — FIDELITY: source reused one
    fld_type, fld_mean, fld_std = read_fld_data(occupancy, csv_path)
    of_type, of_mean, of_std = read_fld_data(OPENING_FACTOR_ROW, csv_path)
    fld = sample_distribution(lhs_uniform(n_sim, rng), fld_type, fld_mean, fld_std)
    fld = fld * combustion_factor * (sprinkler_factor if is_sprinklered else 1.0)
    opening_perc = factorise_opening_percentage(
        sample_distribution(lhs_uniform(n_sim, rng), of_type, of_mean, of_std), rng)

    # 3. chunked Monte Carlo (flat memory regardless of n_sim)
    time_hours = np.arange(0, p.calc_time_hours + p.delta_t_s / 3600, p.delta_t_s / 3600)
    n_failed = 0
    for start in range(0, n_sim, chunk_size):
        sl = slice(start, min(start + chunk_size, n_sim))
        op_fac = calc_op_fac(vent_widths, vent_heights, total_area, opening_perc[sl])
        qtd = fld[sl] * floor_area / total_area
        gas = parametric_fire_curves(time_hours, op_fac, qtd, p).astype(np.float32)
        peak = max_protected_steel_temp(gas, prot_thick_m, p)
        n_failed += int((peak > p.steel_fail_temp).sum())

    reliability = 1.0 - n_failed / n_sim
    return ReliabilityResult(
        reliability=reliability, n_failed=n_failed, n_sim=n_sim, fr_period=fr_period_min,
        protection_thickness_mm=prot_thick_mm, b_value=p.thermal_inertia,
        section_factor=p.sect_factor, critical_temp=p.steel_fail_temp,
        factors_applied={"combustibility": combustion_factor,
                         "sprinkler": sprinkler_factor if is_sprinklered else 1.0},
    )
