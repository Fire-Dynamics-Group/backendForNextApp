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

Tolerance used: envelope half-width ≤ ±0.5 percentage points.

| FR (min) | nSim | K | mean | min–max half-width | 95% band half-width | analytic 1.96·SE |
|---|---|---|---|---|---|---|
| 30 | 100 | 100 | 0.1033 | ±0.0150 | ±0.0100 | ±0.0598 |
| 30 | 500 | 100 | 0.1038 | ±0.0060 | ±0.0040 | ±0.0267 |
| 30 | 1,000 | 100 | 0.1038 | ±0.0035 | ±0.0025 | ±0.0189 |
| 30 | 2,000 | 100 | 0.1037 | ±0.0020 | ±0.0018 | ±0.0134 |
| 30 | 5,000 | 100 | 0.1036 | ±0.0016 | ±0.0012 | ±0.0085 |
| 30 | 10,000 | 50 | 0.1037 | ±0.0008 | ±0.0007 | ±0.0060 |
| 30 | 50,000 | 25 | 0.1037 | ±0.0003 | ±0.0002 | ±0.0027 |
| 90 | 100 | 100 | 0.9880 | ±0.0150 | ±0.0100 | ±0.0222 |
| 90 | 500 | 100 | 0.9871 | ±0.0090 | ±0.0055 | ±0.0099 |
| 90 | 1,000 | 100 | 0.9866 | ±0.0050 | ±0.0040 | ±0.0070 |
| 90 | 2,000 | 100 | 0.9872 | ±0.0040 | ±0.0030 | ±0.0050 |
| 90 | 5,000 | 100 | 0.9871 | ±0.0033 | ±0.0019 | ±0.0031 |
| 90 | 10,000 | 50 | 0.9871 | ±0.0014 | ±0.0011 | ±0.0022 |
| 90 | 50,000 | 25 | 0.9870 | ±0.0005 | ±0.0004 | ±0.0010 |

## Recommendation

- FR 30 min: min–max envelope half-width first within ±0.5 pp at **nSim = 1,000**.
- FR 90 min: min–max envelope half-width first within ±0.5 pp at **nSim = 2,000**.
