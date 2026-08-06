# Monte Carlo TEQ reliability — convergence study

*Scenario:* Panattoni benchmark (Office 64x13x3.5, one openable wall, sect 135, b=1200, 500C, no factors). *Base seed:* 42. *Runtime:* 4907 s. *Repeats per nSim (K):* {'100': 100, '500': 100, '1000': 100, '2000': 100, '5000': 100, '10000': 50, '50000': 25}.

For each nSim the full reliability run was repeated K times with independent
seeds; the spread of the K estimates measures run-to-run variability at that
nSim. The chart shows the empirical min–max envelope of the K repeats (the
measure used by the precedent CFDOpenPlan appendix study) beside the analytic
plain-Monte-Carlo 95 % interval ±1.96·√(p(1−p)/N) — the engine samples by
Latin Hypercube, so its empirical envelope is expected to sit inside the
analytic curve. The 95 % percentile band is tabulated as a supplementary,
K-stable measure; the acceptance rule runs on the (wider, conservative)
envelope.

![convergence chart](convergence_full_fr30-90.png)

Tolerance used: envelope half-width ≤ ±0.5% (all ± values are absolute differences in the reliability percentage).

| FR (min) | nSim | K | mean | min–max half-width | 95% band half-width | analytic 1.96·SE |
|---|---|---|---|---|---|---|
| 30 | 100 | 100 | 10.33% | ±1.50% | ±1.00% | ±5.98% |
| 30 | 500 | 100 | 10.38% | ±0.60% | ±0.40% | ±2.67% |
| 30 | 1,000 | 100 | 10.38% | ±0.35% | ±0.25% | ±1.89% |
| 30 | 2,000 | 100 | 10.37% | ±0.20% | ±0.18% | ±1.34% |
| 30 | 5,000 | 100 | 10.36% | ±0.16% | ±0.12% | ±0.85% |
| 30 | 10,000 | 50 | 10.37% | ±0.08% | ±0.07% | ±0.60% |
| 30 | 50,000 | 25 | 10.37% | ±0.03% | ±0.02% | ±0.27% |
| 90 | 100 | 100 | 98.80% | ±1.50% | ±1.00% | ±2.22% |
| 90 | 500 | 100 | 98.71% | ±0.90% | ±0.55% | ±0.99% |
| 90 | 1,000 | 100 | 98.66% | ±0.50% | ±0.40% | ±0.70% |
| 90 | 2,000 | 100 | 98.72% | ±0.40% | ±0.30% | ±0.50% |
| 90 | 5,000 | 100 | 98.71% | ±0.33% | ±0.19% | ±0.31% |
| 90 | 10,000 | 50 | 98.71% | ±0.14% | ±0.11% | ±0.22% |
| 90 | 50,000 | 25 | 98.70% | ±0.05% | ±0.04% | ±0.10% |

## Recommendation

- FR 30 min: min–max envelope half-width first within ±0.5% at **nSim = 1,000**.
- FR 90 min: min–max envelope half-width first within ±0.5% at **nSim = 2,000**.
