# v11 Phase 2 Step 2: Granger Lead-Lag Test Results

**Round:** 16 (v11) Track 1 Granger-first.
**Date:** 2026-05-27. **Script:** scripts/v11/phase2_step2_granger.py
**Lock:** v3 amendment (research/v11/04-lock-v3-granger-amendment.md)

## Hypothesis (locked verbatim per v3 amendment)

H0: sportsbook movement in T-6h to T-3h does NOT predict Kalshi trade-print movement in T-3h to T-1h, given Kalshi's own T-6h to T-3h movement.

Granger F-test on the gamma=0 restriction in:
  delta_kalshi_post = alpha + beta * delta_kalshi_pre + gamma * delta_sportsbook + epsilon

## Sample coverage

- Total joined events: 408
- Events with all 3 deltas non-null: 372
- Per-sport joined: {'KXMLBGAME': np.int64(167), 'KXNBAGAME': np.int64(151), 'KXNFLGAME': np.int64(90)}

## Per-sport Granger F-test

Bonferroni-corrected alpha: 0.05 / 3 = 0.01667

| Sport | n | F | p_value | gamma | gamma_se | passes (p<=0.01667) | positive direction |
|---|---|---|---|---|---|---|---|
| KXMLBGAME | 131 | 17.2248 | 0.000060 | 0.7847 | 0.1891 | True | True |
| KXNBAGAME | 151 | 7.9089 | 0.005587 | 0.2855 | 0.1015 | True | True |
| KXNFLGAME | 90 | 0.3998 | 0.528853 | -0.1326 | 0.2098 | False | False |

## Pooled (descriptive, not gated)

- n=372, F=33.1505, p=0.000000, gamma=0.5007 (se=0.0870)

## G_GRANGER verdict

Sports passing G_GRANGER (p<=0.01667 AND gamma>0): 2 of 3
- KXMLBGAME: PASS
- KXNBAGAME: PASS
- KXNFLGAME: FAIL

**Verdict: GRANGER-PARTIAL (2 of 3)**

## Recommendation

2 of 3 sports confirm sportsbook leads Kalshi. Recommend v12 follow-up scoped to the passing sports only. Single-sport failure may reflect low n, league-specific market microstructure, or true absence of lead-lag in that sport. v11 Track 1 closes GRANGER-PARTIAL.

---

*Anti-em-dash and anti-en-dash verification: written without U+2014 or U+2013 throughout.*