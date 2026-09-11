"""Monte Carlo time-equivalence *reliability* engine (numpy port).

Reliability = the probability that a steel member survives a realistic fire in this
compartment. Two member modes:

  **Protected** (default):
    1. Size protection so the steel reaches its critical temperature exactly at the FR
       period under the standard ISO fire (deterministic; rounded UP to whole mm).
    2. Expose that protected member to N Monte-Carlo EC1 parametric fires with sampled
       fuel load and opening %.
    3. reliability = 1 - failures/N, where failure = peak steel temp > critical temp.

  **Unprotected**: skip protection sizing; step bare-steel (EC3 unprotected-section)
  heat transfer per sampled fire; reliability is the fraction whose peak steel
  temperature stays below the (member-specific) critical temperature. The FR period
  is unused and no protection thickness is returned.

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

# Fire growth rate -> t_lim, EN 1991-1-2 Annex A(10): slow 25 / medium 20 / fast 15 min.
GROWTH_RATE_TLIM_MIN = {"slow": 25.0, "medium": 20.0, "fast": 15.0}

# Occupancy -> growth rate. Sources: EN 1991-1-2 Table E.5 (office/dwelling/
# hospital/hotel/classroom medium, shopping centre/library fast) and BS 9999
# Table 3 (shop sales areas/factories/storage fast; lounges/seating medium —
# hence Restaurant, absent from Table E.5, stays medium). BS 9999's ultra-fast
# tier has no EC1 t_lim value, so warehousing caps at fast. Unlisted
# occupancies default to medium (the engine's historical global setting).
OCCUPANCY_GROWTH_RATE = {
    "Dwelling": "medium",
    "Hospital": "medium",
    "Hotel room": "medium",
    "Library": "fast",
    "Office": "medium",
    "School": "medium",
    "Clothing store": "fast",
    "Retail unit storage area": "fast",
    "Manufacturing and storage of combustible goods (<150 kg/m2)": "fast",
    "Manufacturing and storage of combustible goods (>150 kg/m2)": "fast",
}


def tlim_hours_for(occupancy: str) -> float:
    """t_lim (hours) for an occupancy's fire growth rate; medium if unlisted."""
    rate = OCCUPANCY_GROWTH_RATE.get(occupancy, "medium")
    return GROWTH_RATE_TLIM_MIN[rate] / 60.0


# EC3-1-2 unprotected-section net-heat-flux constants (parametric fire).
# Internal numerical/code constants — not surfaced. α_c = 35 W/m²K is EN 1991-1-2
# 3.3.1(1) for parametric fires; ε_m = 0.7 is EN 1993-1-2 2.2(2). k_sh = 1.0 is
# the conservative (no-shadow) value; Table 4.2 would give 0.9 for an I-section.
_UNPROT_ALPHA_C = 35.0
_UNPROT_EPSILON_M = 0.7
_UNPROT_EPSILON_F = 1.0
_UNPROT_SIGMA = 5.67e-8
_UNPROT_K_SH = 1.0
_UNPROT_TK = 273.0  # Eurocode writes (θ + 273)


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
    t_lim_hours: float = 20.0 / 60.0     # medium fallback; overridden per occupancy via tlim_hours_for()
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


def _step_steel(gas: np.ndarray, p: SteelParams, prot_thick_m: float | None,
                keep: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray | None]:
    """Time-step the steel recursion over a gas-temp array (n_steps, n_cols).

    ``prot_thick_m`` selects the mode: a thickness steps the EC3 protected
    section; ``None`` steps the bare EC3 unprotected section (§4.2.5.1,
    ḣ_net = α_c (θ_g − θ_a) + Φ ε_m ε_f σ [(θ_g+273)^4 − (θ_a+273)^4], Φ = 1).

    Returns ``(peak, series)``: the running max per column, and — only when
    ``keep`` (sorted step indices) is given — the steel temperatures at those
    steps, shape (len(keep), n_cols) float32. Without ``keep`` memory stays
    O(n_cols), not O(n_steps * n_cols)."""
    steel = gas[0].astype(float).copy()                 # first step = gas (~ambient)
    mx = steel.copy()
    keep_pos = None if keep is None else {int(k): i for i, k in enumerate(keep)}
    series = None if keep is None else np.empty((len(keep), gas.shape[1]), dtype=np.float32)
    if keep_pos is not None and 0 in keep_pos:
        series[keep_pos[0]] = steel
    if prot_thick_m is not None:
        coeff = p.therm_cond_prot * p.sect_factor / (prot_thick_m * p.rho_steel)
    for k in range(1, gas.shape[0]):
        c_steel = _c_steel(steel)
        if prot_thick_m is not None:
            phi = p.c_prot * p.rho_prot / (c_steel * p.rho_steel) * prot_thick_m * p.sect_factor
            delta = (coeff / c_steel * (gas[k] - steel) / (1 + phi / 3) * p.delta_t_s
                     - (np.exp(phi / 10) - 1) * (gas[k] - gas[k - 1]))
        else:
            h_conv = _UNPROT_ALPHA_C * (gas[k] - steel)
            h_rad = (_UNPROT_EPSILON_M * _UNPROT_EPSILON_F * _UNPROT_SIGMA
                     * ((gas[k] + _UNPROT_TK) ** 4 - (steel + _UNPROT_TK) ** 4))
            delta = _UNPROT_K_SH * p.sect_factor / (c_steel * p.rho_steel) * (h_conv + h_rad) * p.delta_t_s
        steel = np.maximum(steel + delta, p.ambient_temp)
        mx = np.maximum(mx, steel)
        if keep_pos is not None and k in keep_pos:
            series[keep_pos[k]] = steel
    return mx, series


def max_protected_steel_temp(gas: np.ndarray, prot_thick_m: float, p: SteelParams) -> np.ndarray:
    """Peak protected-steel temperature per column for a gas-temp array (n_steps, n_cols)."""
    return _step_steel(gas, p, prot_thick_m)[0]


def max_unprotected_steel_temp(gas: np.ndarray, p: SteelParams) -> np.ndarray:
    """Peak unprotected-steel temperature per column (EN 1993-1-2 §4.2.5.1)."""
    return _step_steel(gas, p, None)[0]


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
    fr_period: float | None
    protection_thickness_mm: int | None
    b_value: float
    section_factor: float
    critical_temp: float
    factors_applied: dict = field(default_factory=dict)
    unprotected: bool = False
    # The seed the run actually used (auto-resolved when the caller passed
    # None), so a charts request can reproduce the exact run shown to the user.
    seed: int | None = None


@dataclass
class ReliabilityDetails:
    """A reliability run plus the per-sample data the report charts need."""
    result: ReliabilityResult
    fld: np.ndarray                # sampled fuel-load density (n_sim,) MJ/m2
    glazing_breakage: np.ndarray   # sampled open fraction (n_sim,), 0-1
    peak_temp: np.ndarray          # peak steel temperature per sample (n_sim,)
    time_min: np.ndarray           # strided series grid (minutes)
    steel_series: np.ndarray       # steel temps, (len(time_min), n_sim) float32


def sample_stochastic_inputs(*, occupancy: str, n_sim: int, rng: np.random.Generator,
                             combustion_factor: float, is_sprinklered: bool,
                             sprinkler_factor: float,
                             csv_path: str = DEFAULT_CSV_PATH) -> tuple[np.ndarray, np.ndarray]:
    """Sample the two stochastic inputs (independent LHS columns).

    Returns ``(fld, opening_perc)`` each of length ``n_sim``. Fuel-load density is
    already multiplied by the combustibility / sprinkler factors.
    FIDELITY: the source reused one LHS column for both variables.
    """
    fld_type, fld_mean, fld_std = read_fld_data(occupancy, csv_path)
    of_type, of_mean, of_std = read_fld_data(OPENING_FACTOR_ROW, csv_path)
    fld = sample_distribution(lhs_uniform(n_sim, rng), fld_type, fld_mean, fld_std)
    fld = fld * combustion_factor * (sprinkler_factor if is_sprinklered else 1.0)
    opening_perc = factorise_opening_percentage(
        sample_distribution(lhs_uniform(n_sim, rng), of_type, of_mean, of_std), rng)
    return fld, opening_perc


def _resolve_seed(seed: int | None) -> int:
    """A concrete seed for the run — the caller's, or a fresh 32-bit one. The
    run is then reproducible from the seed echoed in the result."""
    if seed is None:
        return int(np.random.SeedSequence().generate_state(1)[0])
    return seed


def _run_reliability(*, occupancy: str, total_area: float, floor_area: float,
                     vent_widths, vent_heights, fr_period_min: float | None,
                     n_sim: int, is_sprinklered: bool, combustion_factor: float,
                     sprinkler_factor: float, params: SteelParams | None,
                     csv_path: str, chunk_size: int, seed: int | None,
                     unprotected: bool, keep: np.ndarray | None):
    """Shared chunked run. Returns (result, fld, opening_perc, peak, series);
    ``series`` is None unless ``keep`` (step indices to record) is given."""
    p = params or SteelParams(t_lim_hours=tlim_hours_for(occupancy))
    seed = _resolve_seed(seed)
    rng = np.random.default_rng(seed)

    prot_thick_mm = None
    prot_thick_m = None
    if not unprotected:
        if fr_period_min is None:
            raise ValueError("fr_period_min is required for protected members")
        prot_thick_mm = calc_prot_thickness_mm(fr_period_min, p)
        prot_thick_m = prot_thick_mm / 1000.0

    fld, opening_perc = sample_stochastic_inputs(
        occupancy=occupancy, n_sim=n_sim, rng=rng,
        combustion_factor=combustion_factor, is_sprinklered=is_sprinklered,
        sprinkler_factor=sprinkler_factor, csv_path=csv_path)

    time_hours = np.arange(0, p.calc_time_hours + p.delta_t_s / 3600, p.delta_t_s / 3600)
    peak = np.empty(n_sim)
    series = None if keep is None else np.empty((len(keep), n_sim), dtype=np.float32)
    for start in range(0, n_sim, chunk_size):
        sl = slice(start, min(start + chunk_size, n_sim))
        op_fac = calc_op_fac(vent_widths, vent_heights, total_area, opening_perc[sl])
        qtd = fld[sl] * floor_area / total_area
        gas = parametric_fire_curves(time_hours, op_fac, qtd, p).astype(np.float32)
        peak[sl], chunk_series = _step_steel(gas, p, prot_thick_m, keep)
        if series is not None:
            series[:, sl] = chunk_series

    n_failed = int((peak > p.steel_fail_temp).sum())
    result = ReliabilityResult(
        reliability=1.0 - n_failed / n_sim, n_failed=n_failed, n_sim=n_sim,
        fr_period=None if unprotected else fr_period_min,
        protection_thickness_mm=prot_thick_mm, b_value=p.thermal_inertia,
        section_factor=p.sect_factor, critical_temp=p.steel_fail_temp,
        factors_applied={"combustibility": combustion_factor,
                         "sprinkler": sprinkler_factor if is_sprinklered else 1.0},
        unprotected=unprotected, seed=seed,
    )
    return result, fld, opening_perc, peak, series, time_hours, p


def compute_reliability(*, occupancy: str, total_area: float, floor_area: float,
                        vent_widths, vent_heights, fr_period_min: float | None = None,
                        n_sim: int = 10000, is_sprinklered: bool = False,
                        combustion_factor: float = 0.8, sprinkler_factor: float = 0.65,
                        params: SteelParams | None = None, csv_path: str = DEFAULT_CSV_PATH,
                        chunk_size: int = 2000, seed: int | None = None,
                        unprotected: bool = False) -> ReliabilityResult:
    """Run the Monte Carlo reliability assessment for one compartment.

    Protected mode (default) sizes insulation to ``fr_period_min`` then exposes
    that member to N sampled fires. Unprotected mode skips sizing and steps
    bare-steel heat transfer; ``fr_period_min`` is ignored.
    """
    return _run_reliability(
        occupancy=occupancy, total_area=total_area, floor_area=floor_area,
        vent_widths=vent_widths, vent_heights=vent_heights,
        fr_period_min=fr_period_min, n_sim=n_sim, is_sprinklered=is_sprinklered,
        combustion_factor=combustion_factor, sprinkler_factor=sprinkler_factor,
        params=params, csv_path=csv_path, chunk_size=chunk_size, seed=seed,
        unprotected=unprotected, keep=None)[0]


def compute_reliability_details(*, occupancy: str, total_area: float, floor_area: float,
                                vent_widths, vent_heights, fr_period_min: float | None = None,
                                n_sim: int = 10000, is_sprinklered: bool = False,
                                combustion_factor: float = 0.8, sprinkler_factor: float = 0.65,
                                params: SteelParams | None = None, csv_path: str = DEFAULT_CSV_PATH,
                                chunk_size: int = 2000, seed: int | None = None,
                                unprotected: bool = False,
                                series_dt_minutes: float = 1.0) -> ReliabilityDetails:
    """compute_reliability, plus the per-sample data the report charts need.

    Identical sampling and stepping to compute_reliability under the same seed
    (same chunking, same rng draws), with the steel temperature series recorded
    on a ``series_dt_minutes`` stride — memory stays modest (float32, ~24 MB at
    10k sims) where the full 5 s grid would not be.
    """
    p = params or SteelParams(t_lim_hours=tlim_hours_for(occupancy))
    stride = _udf_stride(p, series_dt_minutes)
    n_steps = int(np.arange(0, p.calc_time_hours + p.delta_t_s / 3600,
                            p.delta_t_s / 3600).size)
    keep = np.arange(0, n_steps, stride)
    result, fld, opening_perc, peak, series, time_hours, _ = _run_reliability(
        occupancy=occupancy, total_area=total_area, floor_area=floor_area,
        vent_widths=vent_widths, vent_heights=vent_heights,
        fr_period_min=fr_period_min, n_sim=n_sim, is_sprinklered=is_sprinklered,
        combustion_factor=combustion_factor, sprinkler_factor=sprinkler_factor,
        params=params, csv_path=csv_path, chunk_size=chunk_size, seed=seed,
        unprotected=unprotected, keep=keep)
    return ReliabilityDetails(
        result=result, fld=fld, glazing_breakage=opening_perc, peak_temp=peak,
        time_min=time_hours[keep] * 60.0, steel_series=series)


UDF_README = """MACS+ user-defined fire curves (AnalyseUDF)
==========================================

Each curves/NNNNN.udf file is a two-column whitespace-separated text file:

    <time_minutes> <gas_temperature_C>

No header. Time starts at 0. This is the file path passed to the i-macs
engine as run(method='udf', udf_path=...).

manifest.json joins each curve to the sampled inputs that produced it
(sample index, fuel load, opening %, opening factor, seed).
"""


def format_udf_curve(time_min: np.ndarray, temp: np.ndarray) -> str:
    """MACS+ AnalyseUDF text: one ``time_min temperature_C`` pair per line."""
    return "\n".join(f"{t:.4f} {T:.2f}" for t, T in zip(time_min, temp)) + "\n"


def parse_udf_curve(text: str) -> np.ndarray:
    """Parse an AnalyseUDF text file into an (n, 2) array of (time_min, temp)."""
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        rows.append((float(parts[0]), float(parts[1])))
    return np.asarray(rows, dtype=float)


def _udf_stride(p: SteelParams, dt_minutes: float = 1.0) -> int:
    return max(1, int(round(dt_minutes * 60.0 / p.delta_t_s)))


def export_udf_batch(*, occupancy: str, total_area: float, floor_area: float,
                     vent_widths, vent_heights, n_sim: int = 10000,
                     is_sprinklered: bool = False, combustion_factor: float = 0.8,
                     sprinkler_factor: float = 0.65, params: SteelParams | None = None,
                     csv_path: str = DEFAULT_CSV_PATH, chunk_size: int = 2000,
                     seed: int | None = None, dt_minutes: float = 1.0) -> bytes:
    """Sample N EC1 parametric fires (same path as compute_reliability) and pack
    them as a MACS+ UDF zip: ``curves/NNNNN.udf`` + ``manifest.json``.

    Curves are written at ``dt_minutes`` (default 1 min) subsampled from the
    engine's 5 s grid so a 10k payload stays small; the sampled inputs are
    identical to the reliability calc under the same seed.
    """
    import io
    import json
    import zipfile

    p = params or SteelParams(t_lim_hours=tlim_hours_for(occupancy))
    rng = np.random.default_rng(seed)
    fld, opening_perc = sample_stochastic_inputs(
        occupancy=occupancy, n_sim=n_sim, rng=rng,
        combustion_factor=combustion_factor, is_sprinklered=is_sprinklered,
        sprinkler_factor=sprinkler_factor, csv_path=csv_path)

    time_hours = np.arange(0, p.calc_time_hours + p.delta_t_s / 3600, p.delta_t_s / 3600)
    stride = _udf_stride(p, dt_minutes)
    pick = np.arange(0, time_hours.size, stride)
    if pick[-1] != time_hours.size - 1:
        pick = np.append(pick, time_hours.size - 1)
    time_min = time_hours[pick] * 60.0

    samples: list[dict] = []
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=1) as zf:
        zf.writestr("README.txt", UDF_README)
        for start in range(0, n_sim, chunk_size):
            end = min(start + chunk_size, n_sim)
            sl = slice(start, end)
            op_fac = calc_op_fac(vent_widths, vent_heights, total_area, opening_perc[sl])
            qtd = fld[sl] * floor_area / total_area
            gas = parametric_fire_curves(time_hours, op_fac, qtd, p).astype(np.float32)
            for j, idx in enumerate(range(start, end)):
                fname = f"curves/{idx:05d}.udf"
                zf.writestr(fname, format_udf_curve(time_min, gas[pick, j]))
                samples.append({
                    "index": idx,
                    "file": fname,
                    "fuelLoad": float(fld[idx]),
                    "openingPercent": float(opening_perc[idx]),
                    "openingFactor": float(op_fac[j]),
                    "seed": seed,
                })
        manifest = {
            "nSim": n_sim,
            "seed": seed,
            "occupancy": occupancy,
            "dtMinutes": dt_minutes,
            "format": {
                "engine": "MACS+ AnalyseUDF",
                "columns": ["time_min", "temperature_C"],
                "delimiter": " ",
            },
            "factorsApplied": {
                "combustibility": combustion_factor,
                "sprinkler": sprinkler_factor if is_sprinklered else 1.0,
            },
            "samples": samples,
        }
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))
    return buf.getvalue()
