# Monte Carlo TEQ reliability — convergence study

*Scenario:* Panattoni benchmark (Restaurant 64x13x3.5, one openable wall, sect 135, b=1200, 500C, no factors). *Base seed:* 42. *Runtime:* 9643 s. *Repeats per nSim (K):* {'100': 100, '500': 100, '1000': 100, '2000': 100, '5000': 100, '10000': 50, '20000': 50, '50000': 25}.

For each nSim the full reliability run was repeated K times with independent
seeds; the spread of the K estimates measures run-to-run variability at that
nSim. The chart shows the empirical min–max envelope of the K repeats (the
measure used by the precedent CFDOpenPlan appendix study). The 95 %
percentile band is tabulated as a supplementary, K-stable measure; the
recommendation rule runs on the (wider, conservative) envelope.

![convergence chart](convergence_full_restaurant.png)

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
| 30 | 100 | 100 | 52.06% | ±1.50% | ±1.50% |
| 30 | 500 | 100 | 51.95% | ±0.90% | ±0.70% |
| 30 | 1,000 | 100 | 52.07% | ±0.50% | ±0.45% |
| 30 | 2,000 | 100 | 52.02% | ±0.38% | ±0.33% |
| 30 | 5,000 | 100 | 52.04% | ±0.25% | ±0.21% |
| 30 | 10,000 | 50 | 52.02% | ±0.25% | ±0.16% |
| 30 | 20,000 | 50 | 52.03% | ±0.09% | ±0.09% |
| 30 | 50,000 | 25 | 52.02% | ±0.07% | ±0.06% |
| 60 | 100 | 100 | 97.11% | ±2.50% | ±2.26% |
| 60 | 500 | 100 | 97.33% | ±1.60% | ±1.25% |
| 60 | 1,000 | 100 | 97.27% | ±1.05% | ±0.78% |
| 60 | 2,000 | 100 | 97.28% | ±0.73% | ±0.60% |
| 60 | 5,000 | 100 | 97.29% | ±0.42% | ±0.32% |
| 60 | 10,000 | 50 | 97.30% | ±0.25% | ±0.22% |
| 60 | 20,000 | 50 | 97.30% | ±0.14% | ±0.12% |
| 60 | 50,000 | 25 | 97.30% | ±0.13% | ±0.11% |
| 90 | 100 | 100 | 99.21% | ±1.50% | ±1.00% |
| 90 | 500 | 100 | 99.13% | ±1.00% | ±0.55% |
| 90 | 1,000 | 100 | 99.10% | ±0.70% | ±0.40% |
| 90 | 2,000 | 100 | 99.08% | ±0.43% | ±0.33% |
| 90 | 5,000 | 100 | 99.08% | ±0.27% | ±0.20% |
| 90 | 10,000 | 50 | 99.09% | ±0.16% | ±0.14% |
| 90 | 20,000 | 50 | 99.08% | ±0.12% | ±0.10% |
| 90 | 50,000 | 25 | 99.08% | ±0.07% | ±0.06% |

## Recommendation

- FR 30 min: min–max envelope half-width first within ±0.5% at **nSim = 2,000**.
- FR 60 min: min–max envelope half-width first within ±0.5% at **nSim = 5,000**.
- FR 90 min: min–max envelope half-width first within ±0.5% at **nSim = 2,000**.
