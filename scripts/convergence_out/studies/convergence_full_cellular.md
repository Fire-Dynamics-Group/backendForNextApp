# Monte Carlo TEQ reliability — convergence study

*Scenario:* cellular benchmark (Office 5x4x2.7, one openable wall, sect 135, b=1200, 500C, no factors). *Base seed:* 42. *Runtime:* 9153 s. *Repeats per nSim (K):* {'100': 100, '500': 100, '1000': 100, '2000': 100, '5000': 100, '10000': 50, '20000': 50, '50000': 25}.

For each nSim the full reliability run was repeated K times with independent
seeds; the spread of the K estimates measures run-to-run variability at that
nSim. The chart shows the empirical min–max envelope of the K repeats (the
measure used by the precedent CFDOpenPlan appendix study). The 95 %
percentile band is tabulated as a supplementary, K-stable measure; the
recommendation rule runs on the (wider, conservative) envelope.

![convergence chart](convergence_full_cellular.png)

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
| 30 | 100 | 100 | 48.02% | ±1.50% | ±1.50% |
| 30 | 500 | 100 | 47.97% | ±0.70% | ±0.60% |
| 30 | 1,000 | 100 | 48.11% | ±0.70% | ±0.45% |
| 30 | 2,000 | 100 | 48.08% | ±0.45% | ±0.32% |
| 30 | 5,000 | 100 | 48.07% | ±0.30% | ±0.21% |
| 30 | 10,000 | 50 | 48.04% | ±0.17% | ±0.15% |
| 30 | 20,000 | 50 | 48.06% | ±0.12% | ±0.10% |
| 30 | 50,000 | 25 | 48.06% | ±0.06% | ±0.06% |
| 60 | 100 | 100 | 99.08% | ±1.00% | ±1.00% |
| 60 | 500 | 100 | 99.02% | ±0.60% | ±0.60% |
| 60 | 1,000 | 100 | 99.00% | ±0.55% | ±0.35% |
| 60 | 2,000 | 100 | 99.02% | ±0.35% | ±0.24% |
| 60 | 5,000 | 100 | 99.02% | ±0.31% | ±0.18% |
| 60 | 10,000 | 50 | 99.01% | ±0.15% | ±0.11% |
| 60 | 20,000 | 50 | 99.03% | ±0.09% | ±0.08% |
| 60 | 50,000 | 25 | 99.02% | ±0.06% | ±0.06% |
| 90 | 100 | 100 | 99.52% | ±1.00% | ±0.76% |
| 90 | 500 | 100 | 99.58% | ±0.50% | ±0.40% |
| 90 | 1,000 | 100 | 99.56% | ±0.35% | ±0.33% |
| 90 | 2,000 | 100 | 99.53% | ±0.27% | ±0.21% |
| 90 | 5,000 | 100 | 99.54% | ±0.17% | ±0.13% |
| 90 | 10,000 | 50 | 99.55% | ±0.09% | ±0.08% |
| 90 | 20,000 | 50 | 99.54% | ±0.07% | ±0.06% |
| 90 | 50,000 | 25 | 99.54% | ±0.04% | ±0.04% |

## Recommendation

- FR 30 min: min–max envelope half-width first within ±0.5% at **nSim = 2,000**.
- FR 60 min: min–max envelope half-width first within ±0.5% at **nSim = 2,000**.
- FR 90 min: min–max envelope half-width first within ±0.5% at **nSim = 1,000**.
