# Monte Carlo TEQ reliability — convergence study

*Scenario:* cellular benchmark (Office 5x4x2.7, one openable wall, sect 135, b=1200, 500C, no factors). *Base seed:* 42. *Runtime:* 3987 s. *Repeats per nSim (K):* {'100': 100, '500': 100, '1000': 100, '2000': 100, '5000': 100, '10000': 50, '20000': 50, '50000': 25}.

For each nSim the full reliability run was repeated K times with independent
seeds; the spread of the K estimates measures run-to-run variability at that
nSim. The chart shows the empirical min–max envelope of the K repeats (the
measure used by the precedent CFDOpenPlan appendix study). The 95 %
percentile band is tabulated as a supplementary, K-stable measure; the
recommendation rule runs on the (wider, conservative) envelope.

![convergence chart](convergence_full_cellular_fr120.png)

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
| 120 | 100 | 100 | 99.92% | ±0.50% | ±0.50% |
| 120 | 500 | 100 | 99.90% | ±0.20% | ±0.20% |
| 120 | 1,000 | 100 | 99.88% | ±0.20% | ±0.15% |
| 120 | 2,000 | 100 | 99.88% | ±0.17% | ±0.12% |
| 120 | 5,000 | 100 | 99.89% | ±0.13% | ±0.09% |
| 120 | 10,000 | 50 | 99.89% | ±0.06% | ±0.05% |
| 120 | 20,000 | 50 | 99.88% | ±0.05% | ±0.04% |
| 120 | 50,000 | 25 | 99.88% | ±0.02% | ±0.02% |

## Recommendation

- FR 120 min: min–max envelope half-width first within ±0.5% at **nSim = 500**.
