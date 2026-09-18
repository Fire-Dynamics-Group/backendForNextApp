# Monte Carlo TEQ reliability — convergence study

> **Note — FR 30 superseded.** This sweep ran all FR periods with medium fire
> growth (t_lim 20 min). Clothing store is a **fast**-growth occupancy
> (EN 1991-1-2 Table E.5 / BS 9999 Table 3), which changes the FR 30 result
> substantially (reliability ≈ 73.1 %, recommendation nSim = 10,000 — see
> `convergence_full_clothing_store_fr30.md`). The FR 30 rows below are kept for
> the record only. FR 60 and FR 90 are unaffected (growth-rate-insensitive,
> ventilation-controlled) and remain the governing results for those periods.

*Scenario:* Panattoni benchmark (Clothing store 64x13x3.5, one openable wall, sect 135, b=1200, 500C, no factors). *Base seed:* 42. *Runtime:* 7423 s. *Repeats per nSim (K):* {'100': 100, '500': 100, '1000': 100, '2000': 100, '5000': 100, '10000': 50, '50000': 25}.

For each nSim the full reliability run was repeated K times with independent
seeds; the spread of the K estimates measures run-to-run variability at that
nSim. The chart shows the empirical min–max envelope of the K repeats (the
measure used by the precedent CFDOpenPlan appendix study). The 95 %
percentile band is tabulated as a supplementary, K-stable measure; the
recommendation rule runs on the (wider, conservative) envelope.

![convergence chart](convergence_full_clothing_store.png)

Tolerance used: envelope half-width ≤ ±0.5% (a guide value, not a hard requirement; all ± values are absolute differences in the reliability percentage).

**Definitions.** *Envelope*: the measured random scatter — the range from
the lowest to the highest answer seen across the K repeats at one nSim
(the shaded band on the chart); half of it is the "min–max half-width".
*95 % band half-width*: as above but using the middle 95 % of the K
repeats instead of the extremes (narrower, less sensitive to one-off
outliers; supplementary only). *K*: how many times the whole reliability
run was repeated, with different random seeds, at each nSim.

| FR (min) | nSim | K | mean | min–max half-width | 95% band half-width |
|---|---|---|---|---|---|
| 30 | 100 | 100 | 20.36% | ±1.50% | ±1.00% |
| 30 | 500 | 100 | 20.47% | ±0.60% | ±0.50% |
| 30 | 1,000 | 100 | 20.47% | ±0.50% | ±0.38% |
| 30 | 2,000 | 100 | 20.46% | ±0.37% | ±0.29% |
| 30 | 5,000 | 100 | 20.47% | ±0.27% | ±0.17% |
| 30 | 10,000 | 50 | 20.49% | ±0.16% | ±0.12% |
| 30 | 50,000 | 25 | 20.48% | ±0.06% | ±0.05% |
| 60 | 100 | 100 | 96.33% | ±3.00% | ±2.50% |
| 60 | 500 | 100 | 96.34% | ±1.50% | ±1.11% |
| 60 | 1,000 | 100 | 96.31% | ±1.10% | ±0.85% |
| 60 | 2,000 | 100 | 96.31% | ±0.75% | ±0.63% |
| 60 | 5,000 | 100 | 96.32% | ±0.50% | ±0.34% |
| 60 | 10,000 | 50 | 96.31% | ±0.25% | ±0.21% |
| 60 | 50,000 | 25 | 96.31% | ±0.11% | ±0.10% |
| 90 | 100 | 100 | 98.77% | ±1.50% | ±1.50% |
| 90 | 500 | 100 | 98.68% | ±1.20% | ±0.75% |
| 90 | 1,000 | 100 | 98.65% | ±0.70% | ±0.50% |
| 90 | 2,000 | 100 | 98.69% | ±0.48% | ±0.36% |
| 90 | 5,000 | 100 | 98.68% | ±0.36% | ±0.21% |
| 90 | 10,000 | 50 | 98.67% | ±0.15% | ±0.13% |
| 90 | 50,000 | 25 | 98.68% | ±0.07% | ±0.07% |

## Recommendation

- FR 30 min: min–max envelope half-width first within ±0.5% at **nSim = 2,000**.
- FR 60 min: min–max envelope half-width first within ±0.5% at **nSim = 10,000**.
- FR 90 min: min–max envelope half-width first within ±0.5% at **nSim = 2,000**.
