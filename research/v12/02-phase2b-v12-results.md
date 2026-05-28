# v12 Phase 2b: Granger Lead-Lag Test, Refined Methodology

**Round:** 17 (v12). **Date:** 2026-05-27. **Script:** scripts/v12/phase2b_v12_analysis.py.
**Lock:** research/v12/01-methodology-lock.md.

## Per-stratum results (center offset, +/- 0.5h checks, block-bootstrap CI)

Top-level Bonferroni alpha = 0.05/4 = 0.01250. NFL within-stratum alpha = 0.05/8 = 0.00625.

| Stratum | n | F (center) | p (center) | gamma (center) | gamma_se | bb_ci_lower | bb_ci_upper | offset_robust | bb_pass | OVERALL |
|---|---|---|---|---|---|---|---|---|---|---|
| MLB-day | 19 | 0.4152 | 0.528493 | 0.1381 | 0.2143 | -0.5677 | 0.4359 | False | False | False |
| MLB-night | 109 | 29.5013 | 0.000000 | 1.0891 | 0.2005 | 0.1188 | 1.9381 | False | True | False |
| NBA | 151 | 0.0034 | 0.953849 | 0.0058 | 0.0994 | -0.1029 | 0.1160 | False | False | False |
| NFL-A | 90 | 0.8620 | 0.355742 | -0.1899 | 0.2046 | -0.5267 | 0.1049 | False | False | False |
| NFL-B | 90 | 0.2547 | 0.615069 | -0.0553 | 0.1097 | -0.2433 | 0.8477 | False | False | False |
| NFL combined | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | False (via neither) |

## Offset robustness detail

**MLB-day** (alpha 0.01250):
- offset -0.5h: p=0.005587, gamma=0.7440, passes=True
- offset +0.0h: p=0.528493, gamma=0.1381, passes=False
- offset +0.5h: p=0.288223, gamma=-0.3403, passes=False

**MLB-night** (alpha 0.01250):
- offset -0.5h: p=0.026702, gamma=0.7516, passes=False
- offset +0.0h: p=0.000000, gamma=1.0891, passes=True
- offset +0.5h: p=0.000685, gamma=0.9849, passes=True

**NBA** (alpha 0.01250):
- offset -0.5h: p=0.441132, gamma=0.2242, passes=False
- offset +0.0h: p=0.953849, gamma=0.0058, passes=False
- offset +0.5h: p=0.183429, gamma=0.1392, passes=False

**NFL-A** (alpha 0.00625):
- offset -0.5h: p=0.827803, gamma=-0.0547, passes=False
- offset +0.0h: p=0.355742, gamma=-0.1899, passes=False
- offset +0.5h: p=0.506414, gamma=-0.1278, passes=False

**NFL-B** (alpha 0.00625):
- offset -0.5h: p=0.723929, gamma=0.0277, passes=False
- offset +0.0h: p=0.615069, gamma=-0.0553, passes=False
- offset +0.5h: p=0.843774, gamma=0.0236, passes=False

## v12 verdict

Strata passing all 5 binding gates: 0 of 4

**Verdict: NULL-v12**

---

*Anti-em-dash and anti-en-dash verification: written without U+2014 or U+2013.*