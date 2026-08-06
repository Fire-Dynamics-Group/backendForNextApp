# Monte Carlo TEQ reliability — convergence study

*Scenario:* Panattoni benchmark (Office 64x13x3.5, one openable wall, sect 135, b=1200, 500C, no factors). *Base seed:* 42. *Runtime:* 4406 s. *Repeats per nSim (K):* {'100': 100, '500': 100, '1000': 100, '2000': 100, '5000': 100, '10000': 50, '50000': 25}.

For each nSim the full reliability run was repeated K times with independent
seeds; the spread of the K estimates measures run-to-run variability at that
nSim. The chart shows the empirical min–max envelope of the K repeats (the
measure used by the precedent CFDOpenPlan appendix study) beside the analytic
plain-Monte-Carlo 95 % interval ±1.96·√(p(1−p)/N) — the engine samples by
Latin Hypercube, so its empirical envelope is expected to sit inside the
analytic curve. The 95 % percentile band is tabulated as a supplementary,
K-stable measure; the acceptance rule runs on the (wider, conservative)
envelope.

![convergence chart](convergence_full.png)

Tolerance used: envelope half-width ≤ ±0.5 percentage points.

| FR (min) | nSim | K | mean | min–max half-width | 95% band half-width | analytic 1.96·SE |
|---|---|---|---|---|---|---|
| 35 | 100 | 100 | 0.8918 | ±0.0450 | ±0.0376 | ±0.0615 |
| 35 | 500 | 100 | 0.8882 | ±0.0210 | ±0.0165 | ±0.0275 |
| 35 | 1,000 | 100 | 0.8897 | ±0.0150 | ±0.0123 | ±0.0194 |
| 35 | 2,000 | 100 | 0.8891 | ±0.0105 | ±0.0084 | ±0.0137 |
| 35 | 5,000 | 100 | 0.8893 | ±0.0071 | ±0.0052 | ±0.0087 |
| 35 | 10,000 | 50 | 0.8894 | ±0.0046 | ±0.0037 | ±0.0061 |
| 35 | 50,000 | 25 | 0.8895 | ±0.0014 | ±0.0014 | ±0.0027 |
| 60 | 100 | 100 | 0.9677 | ±0.0250 | ±0.0226 | ±0.0351 |
| 60 | 500 | 100 | 0.9667 | ±0.0140 | ±0.0105 | ±0.0157 |
| 60 | 1,000 | 100 | 0.9666 | ±0.0105 | ±0.0078 | ±0.0111 |
| 60 | 2,000 | 100 | 0.9670 | ±0.0068 | ±0.0051 | ±0.0078 |
| 60 | 5,000 | 100 | 0.9669 | ±0.0033 | ±0.0028 | ±0.0050 |
| 60 | 10,000 | 50 | 0.9665 | ±0.0019 | ±0.0018 | ±0.0035 |
| 60 | 50,000 | 25 | 0.9668 | ±0.0006 | ±0.0006 | ±0.0016 |

## Recommendation

- FR 35 min: min–max envelope half-width first within ±0.5 pp at **nSim = 10,000**.
- FR 60 min: min–max envelope half-width first within ±0.5 pp at **nSim = 5,000**.
