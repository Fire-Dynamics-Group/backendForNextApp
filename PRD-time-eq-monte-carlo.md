# PRD — Monte Carlo Time-Equivalence Reliability

**Status:** Draft for build · **Branch:** `time-eq-monte-carlo` (both repos) ·
**Author context:** distilled from the design/grilling session, June 2026

---

## 1. Context & problem

The app's **Time Equivalence** mode runs a single **deterministic** EC1 Annex-A parametric-fire
calc (`backend/time_eq.py::compute_time_eq`) and returns one time–temperature chart. It answers
"what is the equivalent standard-fire exposure for *one* assumed fire?" — but a real compartment
fire's severity is uncertain, driven mostly by how much fuel is present and how much the façade
vents. A single deterministic curve hides that uncertainty.

The fire team already has a **validated standalone Monte Carlo engine** (PyTorch; Dropbox
`05 R&D/06 KK/04. Monte Carlo TEQ/`, with the `Panattoni_reliability.xlsx` reference results)
that quantifies it probabilistically. This PRD brings that engine's **reliability** capability
into the app, **alongside** the existing deterministic calc (nothing retired), so an engineer can
get a reliability figure straight from a drawing.

## 2. What "reliability" means (the method)

Confirmed against the source code, the Panattoni workbook, and the published reliability-based
fire-resistance-period method ([MDPI *Fire* 2023](https://www.mdpi.com/2571-6255/6/1/30);
[PD 7974-7](https://link.springer.com/article/10.1007/s10694-018-0775-2)):

> **Reliability = the probability that a steel member, fire-protected to a chosen standard
> rating, survives a realistic fire in this compartment.**

Mechanically:

1. The **FR-period input** (e.g. 60 min) sizes the protection: thickness is found such that, under
   the **standard ISO furnace fire**, the steel reaches its critical temperature exactly at that
   rating. Thickness is **rounded up to the next whole mm** (discrete product thicknesses).
2. That protected member is exposed to **N Monte-Carlo real fires** (EC1 parametric curves) with
   sampled fuel load and ventilation.
3. **Reliability = `1 − failures/N`**, where a "failure" is peak steel temperature ≥ critical
   temperature.

Reliability rises monotonically with the FR period (more protection → more survivals). This round
implements the **forward** direction only (FR period → reliability). The **inverse** —
target reliability → required FR period (the `92.8%`-style target) — is explicitly out of scope.

## 3. Goals / non-goals

**Goals**
- New **Monte Carlo Reliability** option inside the existing Time Equivalence mode.
- Reproduce the validated engine's reliability numbers (Panattoni parity).
- Surface the methodology constants as visible, overridable inputs.

**Non-goals (this round)**
- Reliability **targeting** (solve for required FR period).
- **Travelling fire** branch (stays disabled, as in source).
- Appendix **distribution scatter charts** (TEQ vs opening %, vs fuel load).
- Any change to the deterministic `/timeEq` behaviour or output.

## 4. Users

Fire engineers using the drawing-canvas app who already draw a compartment + openings for the
deterministic time-equivalence calc and want a probabilistic reliability figure for protected
steelwork without leaving the app or running the standalone Python engine.

## 5. Functional requirements

### 5.1 Stochastic inputs (exactly two)
Per simulation the engine samples **only**:
- **Fire load density** — occupancy → Gumbel or lognormal (`fire_load_density.csv`).
- **Window breakage = opening %** — `Opening Factor` lognormal (mean 0.2, CoV 1), via LHS.

The other three LHS variables in the source (HRRPUA, max fire area, column location) feed **only**
the disabled travelling-fire branch and are **not sampled**. Re-sample both variables at runtime
via Latin Hypercube Sampling; do **not** bundle the frozen 10k `.txt` dumps.

### 5.2 Ventilation model (faithful to `calc_op_fac`)
The ported `calc_op_fac` maths is unchanged (area = w×h, open area = area×perc, heq = h×√perc,
opening factor clamped to **[0.01, 0.2]**). It is fed:
- **width** = engineer's **openable width per wall** (full glazed wall = full length; party/fire
  wall = 0) — exactly the source's per-wall `VENT*_WIDTH`.
- **height** = the **compartment/storey height** (already collected) — **not** drawn window
  heights (that would break the opening-% distribution's calibration).
- **opening %** = sampled, untouched.

### 5.3 Engine behaviour
- EC1 Annex-A parametric fire per simulation from sampled fuel load + opening factor + b-value.
- Protected-steel heat transfer (EC3 protected-section step), per-step ambient clamp, 4-branch
  `calc_c_steel`.
- Protection sizing: thickness reaching critical temp at the FR period under ISO, **ceil to whole
  mm**.
- Reliability = fraction of N fires with peak steel temp **<** critical temp.

### 5.4 Constants — validated defaults, shown, overridable
Every constant below uses the **source MC value as default**, is **displayed** in the UI, and
accepts an **optional custom override**:

| Constant | Default | Notes |
|---|---|---|
| Section factor `Ap/V` | **202** | Dominant lever on result |
| Critical (failure) temp | **500 °C** | |
| Protection density `ρ_p` | **375** | `c_p` 1200, `k` 0.14 |
| `t_lim` (growth rate) | **20 min (medium)** | selector: slow 25 / medium 20 / fast 15; custom allowed |
| b-value (thermal inertia) | **derived from materials** | show per-material b (concrete ≈1741.6, brick ≈1674.8, plasterboard ≈421.5); custom override |
| Combustibility factor | **0.8** | applied to fuel load |
| Sprinkler factor | **0.65** | applied **only** when sprinklered |
| `nSim` | **2000** | hard cap 10000 |

**Internal-only** (fixed named constants, *not* surfaced — they are numerical-method params, a
wrong value is a bug not a judgement): `DELTA_T` = 5 s, `CALC_TIME` = 300 min.

### 5.5 Occupancy
Reliability-mode occupancy dropdown is **populated from the bundled CSV** (the 13 fire-load rows;
exclude the `Opening Factor` row). Each entry **displays its values** (distribution type, mean,
CoV) next to the name. A **custom occupancy** (manual mean/CoV/type) is allowed. The deterministic
mode keeps its existing 4-item list untouched.

### 5.6 Output
JSON (no chart this round):
```
{ reliability, nFailed, nSim, frPeriod, protectionThickness_mm,
  bValue, criticalTemp, sectionFactor, factorsApplied: { combustibility, sprinkler } }
```

## 6. UX / frontend (`upload-canvas`, worktree `fd/time-eq-monte-carlo`)

- `TimeEquivalenceInputPopup.jsx`: calc-type toggle at top — **Deterministic** (unchanged) vs
  **Monte Carlo Reliability**. All existing geometry/material/opening inputs reused. When
  Reliability is selected, additionally show: `nSim`; **per-wall openable width**; per-material
  b-values + custom b; the constants table (section factor, critical temp, protection density)
  with defaults + override; growth-rate selector; combustibility + sprinkler factors with
  defaults + override; CSV occupancy dropdown with values shown.
- `ApiCalls.jsx`: add `sendTimeEqReliabilityData(...)` — POST inputs + overrides to
  `/timeEqReliability`, parse **JSON** (no blob download).
- Result panel: render reliability % + `nFailed/nSim`, FR period, protection thickness, and the
  effective constants/factors used.
- `ModePopup.jsx`: unchanged (reliability lives inside Time Equivalence mode).

## 7. Technical approach (`backendForNextApp`, worktree `fd/backend-time-eq-monte-carlo`)

- **Dependencies:** add **`scipy`** only (for `lognorm.ppf`/`gumbel_l.ppf`). Reimplement the
  engine's vectorized math in **numpy** (drop `torch`); reimplement LHS in ~10 lines (drop
  `pyDOE`); reuse `time_eq.py`'s incremental thickness search instead of scipy `broyden1`. The
  source's pinned CUDA torch build must never ship to Railway.
- **Execution (sync, but guarded for large N):**
  - Vectorize across the simulation axis (per-step `(n_sim,)` rows); CPU ≈ 2–4 s at N=10k.
  - **Chunk** sims in ~1–2k blocks, accumulating only the fail count → peak memory flat
    regardless of N (a full `(10000×3600)` float64 array is ~290 MB and several are materialized
    → ~1–2 GB if done in one shot, which OOMs small instances). Use **float32**.
  - Run the blocking calc via `starlette.concurrency.run_in_threadpool` so it doesn't freeze the
    event loop.
- **New module `teq_reliability.py`:** numpy port of the reliability path only. Port
  `get_distribution`, `calc_op_fac`, `calc_param_fire` (+ `calc_qtd`, `calc_op_fac_lim`,
  `calc_gamma`, `gamma_lim_check`, `calc_t_max`, `calc_t_star_max`, `calc_max_temp`,
  `calc_cooling_phase_temp`), a vectorized `calc_steel_temp`, the ceil-to-mm thickness sizing, and
  the failure count. **Drop** travelling-fire, graphical-TEQ, appendix, GPU/threading, debug/CSV
  code, and the unused `fr_period_iso` path. **Time-base caution:** source MC uses `DELTA_T` in
  **seconds**; `time_eq.py::calculate_protsteeltemp` uses **minutes** (×60) — keep separate.
- **Geometry reuse:** extract `derive_geometry()` from `compute_time_eq` (no behaviour change)
  returning floor area, room dimensions, `At`, per-wall lengths — shared by both calcs. The MC
  path builds its own vent width/height arrays from openable-width inputs and does **not** call
  `get_Av`/`get_Heq`/`get_opening_factor` (those use drawn openings, which MC ignores).
- **Data:** bundle `fire_load_density.csv` into `backend/data/`, load via a `__file__`-relative
  path (mirrors `routers/fee_proposal.py`'s `BASE_DIR`/`data/` pattern). Do not bundle the `.txt`
  sample dumps.
- **Endpoint:** `POST /timeEqReliability` mirroring `/timeEq` (main.py ~198–228), Pydantic
  `TimeEqReliabilityData` = `TimeEqData` minus `fireLoadDensity`, plus `occupancy`, `nSim`,
  per-wall `openableWidths`, growth rate, and the optional constant/factor overrides.

## 8. Acceptance criteria & verification

1. **Panattoni parity (primary gate).** The workbook was generated by `SB_has_a_go_main.py`
   with: Office, building **64 × 13 × 3.5 m**, one openable wall **`0/0/64/0`** at storey height,
   **section factor 135**, **b = 1200**, crit temp 500 °C, no combustibility/sprinkler factor.
   (These are the engine defaults in `teq_reliability.SteelParams`.)
   - **Protection thickness is deterministic** (no sampling, unaffected by the source quirks
     below) → **exact** gate. Verified matching the workbook at FR 10/15/20/25/30/35/40/45/46/
     50/60/70/80/90 → 2/3/4/6/7/9/10/11/12/13/16/19/22/25 mm. ✅ (`test_teq_reliability.py`)
   - **Reliability is stochastic** → checked for shape, not exact rows. With corrected physics it
     tracks Panattoni within ~1–3 % across the design-relevant high-reliability band (FR ≥ 35:
     ours 0.89/0.93/0.97/0.99 vs 0.92/0.93/0.95/0.98 at FR 35/46/60/90). The large gap at FR 30
     (0.10 vs 0.27) is where the source quirks bite hardest and is below any design target.
     `Panattoni_2k_curves.png` is the visual reference.

   **Source fidelity findings (decision pending).** The engine uses EC1-correct physics; the
   validated source has three quirks it deviates from (each marked `# FIDELITY` in code):
   (a) reuses one LHS column for fuel load *and* opening % → forces correlation (we sample
   independently); (b) drops the EC1 `t*max ≤ 0.5` cooling branch (rate 625) via an overwrite
   (we restore it); (c) evaluates steel specific heat from column 0 only (we do it per
   simulation). These only affect the reliability number (not thickness) and only materially in
   the low-FR tail. **Open decision:** keep corrected physics (recommended) vs replicate the
   source for bit-exact reliability parity.
2. **Monotonicity:** FR 30 / 60 / 90 → strictly increasing reliability and non-decreasing
   thickness.
3. **Regression:** deterministic `/timeEq` jpeg is byte-for-byte unchanged after the
   `derive_geometry` extraction.
4. **Local run:** backend `uvicorn main:app --reload --port 8001`; exercise via `/docs` with the
   `mockConvertedPoints`. Frontend dev server: draw a compartment, toggle Monte Carlo Reliability,
   submit, confirm reliability renders and constants/occupancy values display + override.
5. **Perf:** N=10k responds in < ~5 s and does not exceed a sane memory ceiling (verify chunking).

## 9. Risks

1. **Recursive steel-temp loop fidelity** — the 5 s vs 0.5 min time-base mismatch, `calc_c_steel`
   branch boundaries, per-step ambient clamp. Highest fidelity risk; caught by Panattoni parity.
2. **Distribution params** — Gumbel/lognormal ppf formulas, occupancy→CSV mapping, factor
   placement (×0.8 before `q_td`).
3. **Vectorized rewrite** — broadcasting shapes for chunked per-step arrays vs source per-column
   torch ops; chunk boundaries must not change results.
4. **Resource exhaustion at high N** — mitigated by chunking + threadpool + float32; failure mode
   if skipped is OOM / blocked event loop, not wrong numbers.

## 10. Future (out of scope, noted for sequencing)

- Reliability **targeting** (target reliability → required FR period); needs the `92.8%`-style
  target provenance pinned down first.
- **Travelling fire** branch + the HRRPUA/fire-area/column-location stochastic inputs it needs.
- **Distribution charts** (appendix scatter plots) and graphical-TEQ output.
- Promote internal numerical constants to an "advanced" panel if ever needed.
