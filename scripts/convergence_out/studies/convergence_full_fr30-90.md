# Monte Carlo TEQ reliability — convergence study

*Scenario:* Panattoni benchmark (Office 64x13x3.5, one openable wall, sect 135, b=1200, 500C, no factors). *Base seed:* 42. *Runtime:* 4907 s. *Repeats per nSim (K):* {'100': 100, '500': 100, '1000': 100, '2000': 100, '5000': 100, '10000': 50, '50000': 25}.

For each nSim the full reliability run was repeated K times with independent
seeds; the spread of the K estimates measures run-to-run variability at that
nSim. The chart shows the empirical min–max envelope of the K repeats (the
measure used by the precedent CFDOpenPlan appendix study). The 95 %
percentile band is tabulated as a supplementary, K-stable measure; the
recommendation rule runs on the (wider, conservative) envelope.

![convergence chart](convergence_full_fr30-90.png)

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
| 30 | 100 | 100 | 10.33% | ±1.50% | ±1.00% |
| 30 | 500 | 100 | 10.38% | ±0.60% | ±0.40% |
| 30 | 1,000 | 100 | 10.38% | ±0.35% | ±0.25% |
| 30 | 2,000 | 100 | 10.37% | ±0.20% | ±0.18% |
| 30 | 5,000 | 100 | 10.36% | ±0.16% | ±0.12% |
| 30 | 10,000 | 50 | 10.37% | ±0.08% | ±0.07% |
| 30 | 50,000 | 25 | 10.37% | ±0.03% | ±0.02% |
| 90 | 100 | 100 | 98.80% | ±1.50% | ±1.00% |
| 90 | 500 | 100 | 98.71% | ±0.90% | ±0.55% |
| 90 | 1,000 | 100 | 98.66% | ±0.50% | ±0.40% |
| 90 | 2,000 | 100 | 98.72% | ±0.40% | ±0.30% |
| 90 | 5,000 | 100 | 98.71% | ±0.33% | ±0.19% |
| 90 | 10,000 | 50 | 98.71% | ±0.14% | ±0.11% |
| 90 | 50,000 | 25 | 98.70% | ±0.05% | ±0.04% |

## Recommendation

- FR 30 min: min–max envelope half-width first within ±0.5% at **nSim = 1,000**.
- FR 90 min: min–max envelope half-width first within ±0.5% at **nSim = 2,000**.
