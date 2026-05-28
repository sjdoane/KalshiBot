# v12 Phase 1.5 Methodology Lock

**Round:** 17 (v12)
**Date:** 2026-05-27 by orchestrator after operator authorized "Methodology v12: fix + re-test, no capital".
**Inherits:** v11 lock v2 + v3 amendment (universe, split, sample). v12 amends only the analytic spec.
**Status:** binding. Phase 2 entry permitted on this document.
**Scope:** addresses Phase 3 v11 critic findings KILLER-1 (already fixed in v11 Phase 4), KILLER-2 (day/night), KILLER-3 / IMPORTANT-A (offset reporting), IMPORTANT-C (NFL window expansion), IMPORTANT-F (block bootstrap).

No capital deployment. No new trading rule. v12 is a confirmatory re-test.

---

## What v12 changes from v11 v3

| Component | v11 v3 lock | v12 lock |
|---|---|---|
| Strata | 3 sports (MLB, NBA, NFL) | 4 strata: MLB-day, MLB-night, NBA, NFL |
| MLB stratification | none | UTC close hour [17, 23) = day, [0, 9) U [23, 24) = night |
| Commence offset | 3.5h all sports | sport-specific: MLB 3.5h, NBA 2.5h, NFL 3.5h |
| Offset robustness | none | sport-specific +/- 0.5h; signal must pass at all 3 offsets |
| NFL window | T-6h to T-1h only | classic T-6h to T-1h AND expanded T-24h to T-6h; OR-of-2 sub-test (within-NFL Bonferroni 0.05/8) |
| Bonferroni | 0.05/3 = 0.01667 | 0.05/4 = 0.0125 (top-level across 4 strata) |
| CI on gamma | OLS SE only | OLS SE AND block-bootstrap (block_size = 1 calendar day, 10k resamples) |
| Gate on CI | p <= alpha AND gamma > 0 | p <= alpha AND gamma > 0 AND block-bootstrap 95% CI lower > 0 |
| Verdict map | 3 -> CONFIRMED, 2 -> PARTIAL | 4 -> CONFIRMED-v12, 3 -> PARTIAL-v12-3of4, 2 -> PARTIAL-v12-2of4, 0 or 1 -> NULL-v12 |

---

## 1. Universe (unchanged from v11 v2 Section 1)

- Sports: KXMLBGAME, KXNBAGAME, KXNFLGAME
- Cohort: Becker post-Oct-2024 settled markets
- Splits: per-sport median chronological with 7-day purge (already computed in v11 Phase 2 Step 1a)
- Sample: same 408 matched events from v11 Phase 4 (post-KILLER-1 date-tz fix)

## 2. Strata definitions (pre-registered)

### MLB-day

`sport_prefix == 'KXMLBGAME' AND close_time UTC hour in [17, 23)`

Rationale: MLB games ending in afternoon UTC = evening ET = day games starting roughly 1 PM to 4 PM ET. Pre-Phase-3-critic empirical bucketing showed approximately 38 of 89 MLB events fall here.

### MLB-night

`sport_prefix == 'KXMLBGAME' AND close_time UTC hour in [0, 9) UNION [23, 24)`

Rationale: MLB games ending late UTC = late evening ET = night games starting 7 PM to 10 PM ET. Includes UTC 23 (late primetime ET) and UTC 0-8 (very late night ET). Pre-Phase-3-critic showed approximately 51 of 89 MLB events fall here.

### NBA

`sport_prefix == 'KXNBAGAME'`

No sub-strata. NBA games are concentrated 7 PM to 10 PM ET (commence UTC 0-3 in EST, 23-2 in EDT).

### NFL

`sport_prefix == 'KXNFLGAME'`

No sub-strata. NFL games span Sun 1 PM ET / 4 PM ET / 8 PM ET, Mon 8 PM ET, Thu 8 PM ET. v12 tests two SIGNAL WINDOWS for NFL (see Section 4) but treats them as one stratum at the top-level Bonferroni.

### Per-stratum n>=50 floor

All 4 strata must have n>=50 after match + joint-coverage filtering. Strata below 50 are reported but not gated (verdict drops one stratum from the count).

## 3. Sport-specific commence offsets (pre-registered)

For each sport, COMMENCE_OFFSET = (close_time minus offset) approximates first-pitch/tip-off/kickoff.

| Sport | Offset center | Offset sensitivity range |
|---|---|---|
| MLB-day | 3.5h | [3.0h, 4.0h] |
| MLB-night | 3.5h | [3.0h, 4.0h] |
| NBA | 2.5h | [2.0h, 3.0h] |
| NFL | 3.5h | [3.0h, 4.0h] |

**Offset robustness gate:** for each stratum, the F-test must clear at ALL 3 offsets in the sensitivity range (center, center minus 0.5h, center plus 0.5h). Failure of even one offset point disqualifies the stratum. This pre-registers the robustness range that v11 lock v3 did NOT pre-register and that the v11 Phase 3 critic flagged as a gap.

## 4. NFL signal definitions (pre-registered, OR-of-2)

NFL-A (classic): same as v11 v3.
  delta_sportsbook_pre_A = implied_T-3h minus implied_T-6h
  delta_kalshi_pre_A = VWAP_T-3h minus VWAP_T-6h
  delta_kalshi_post_A = VWAP_T-1h minus VWAP_T-3h
  Granger: delta_kalshi_post_A ~ alpha + beta * delta_kalshi_pre_A + gamma_A * delta_sportsbook_pre_A

NFL-B (expanded): sharper-action window.
  delta_sportsbook_pre_B = implied_T-12h minus implied_T-24h
  delta_kalshi_pre_B = VWAP_T-12h minus VWAP_T-24h
  delta_kalshi_post_B = VWAP_T-6h minus VWAP_T-12h
  Granger: delta_kalshi_post_B ~ alpha + beta * delta_kalshi_pre_B + gamma_B * delta_sportsbook_pre_B

The NFL stratum passes if EITHER NFL-A or NFL-B clears the within-NFL Bonferroni alpha 0.05/(4 strata * 2 NFL sub-tests) = 0.05/8 = 0.00625 AND has positive gamma AND has block-bootstrap CI lower > 0.

The 0.05/8 within-NFL alpha is the corrected alpha after accounting for the 2-way OR-of-tests within the NFL stratum, while keeping the top-level family-wise alpha at 0.05 across 4 strata.

## 5. Granger F-test specification (per stratum, unchanged from v11 v3)

```
restricted:   delta_kalshi_post = alpha + beta * delta_kalshi_pre + eps
unrestricted: delta_kalshi_post = alpha + beta * delta_kalshi_pre + gamma * delta_sportsbook + eps
F = ((ss_R - ss_U) / 1) / (ss_U / (n - 3))
p = 1 - F_cdf(F, 1, n - 3)
```

gamma_se from (X'X)^-1 of the unrestricted design.

## 6. Block-bootstrap CI on gamma (NEW per v12)

For each stratum:
1. Group events by floor(close_time, day).
2. Resample CALENDAR DAYS with replacement (block_size = 1 day).
3. For each resample, refit the unrestricted regression and record gamma.
4. Compute the 2.5th and 97.5th percentiles of bootstrapped gammas = 95% CI.
5. 10,000 resamples, seed = 42.

**Block-CI gate:** the lower bound of the 95% block-bootstrap CI must exceed 0 for the stratum to pass.

This is a STRICTER gate than the OLS-SE gate (OLS assumes per-event independence, which underestimates SE when events on the same day share information shocks).

## 7. Pre-registered per-stratum binding gates

For each of the 4 strata, ALL of the following must hold:

a) Top-level Bonferroni p_value <= 0.05 / 4 = 0.0125 (or for NFL: within-NFL Bonferroni 0.05/8 = 0.00625 on the BETTER of NFL-A and NFL-B)
b) gamma > 0 (positive direction; sportsbook moves UP should lead Kalshi moves UP)
c) block-bootstrap 95% CI lower bound > 0
d) Offset robustness: F-test passes at the center offset AND at center +/- 0.5h (3 of 3 offsets)
e) n >= 50

## 8. Verdict mapping

| Strata passing all 5 gate conditions | Verdict |
|---|---|
| 4 of 4 | GRANGER-CONFIRMED-v12 |
| 3 of 4 | GRANGER-PARTIAL-v12-3of4 |
| 2 of 4 | GRANGER-PARTIAL-v12-2of4 |
| 1 of 4 | NULL-v12 (with sport-specific commentary) |
| 0 of 4 | NULL-v12 |

If GRANGER-CONFIRMED-v12 fires, v13 designs the execution model and forward spot-check.

If GRANGER-PARTIAL-v12 fires, the verdict carries scope to the passing strata. v13 (if pursued) scopes to those strata.

If NULL-v12 fires, the v11 GRANGER-PARTIAL stays as the cumulative-history verdict; v12 attempted to elevate but did not.

## 9. NFL window expansion (Phase 2a data pull)

For each NFL event in the v11 matched sample, pull additional historical odds at:
- T-24h relative to commence_estimate
- T-18h relative to commence_estimate
- T-12h relative to commence_estimate

Estimated cost: 90 NFL events * 3 new snapshots * 10 credits = 2,700 credits of 14,740 remaining.

Reuse v11 odds pulls for T-6h, T-3h, T-1h (no new credits needed for those).

If T-24h or T-12h coverage is below 60% on NFL events (the-odds-api may not have NFL historical snapshots that far back consistently), NFL-B sub-test is REPORTED-ONLY and the NFL stratum reverts to NFL-A only.

## 10. What v12 will NOT do (preserved from v11 v2 Section 7, plus extensions)

a) No capital deployment (operator-confirmed scope)
b) No new trading rule design
c) No execution-model assumptions; F11 phantom unresolved by v12
d) No prior-round numerical threshold borrows for gates (the v12 alpha is theory-derived; the offset center is theory-grounded; the block size is structural to MLB-game-day correlation)
e) No post-hoc adjustment of strata definitions, offsets, or gates after seeing v12 P&L results (v12 has no P&L, so this is moot)
f) No re-running v11 Track 2 (Track 2 SHIPPED stands)
g) No modifications to v1 production code

## 11. Phase 2 sequencing

Step 1: confirm v11 data assets present (joint_dataset.parquet, granger_sample_events.parquet, raw odds pulls). No new data needed except NFL extended windows.

Step 2a (Phase 2a task #10): pull NFL T-24h, T-18h, T-12h snapshots; verify coverage; persist.

Step 2b (Phase 2b task #11): build v12 joint dataset with new strata. For each stratum, compute Granger F-test at center offset and at +/- 0.5h offset (3 fits per stratum). Compute block-bootstrap CI for the center offset only (the +/- 0.5h offsets are gate checks only, not CI sources). Apply all 5 binding gate conditions per stratum. Write v12 results doc.

Step 3 (Phase 3 critic, task #12): adversarial review by agent. Reproduce numbers; audit pre-registration adherence.

Step 4 (Phase 4 salvage if any) + Step 5 (FINAL-VERDICT, task #13).

---

## 12. Pre-registration commitment

Before Phase 2 runs, this lock fixes the following choices:
- 4 strata definitions (Section 2)
- 3 commence offsets per sport (Section 3)
- 6 offset robustness points across strata (3 strata * 2 sport offsets; 3 MLB offsets shared by day and night)
- 2 NFL signal windows (Section 4)
- Block bootstrap params (Section 6)
- 5-gate per-stratum criteria (Section 7)
- 5-verdict mapping (Section 8)

NO post-data tuning of any of these. If gates fail, the verdict drops. If new failure modes surface, document in research/v12/replay-prevention.md.

---

*Anti-em-dash and anti-en-dash verification: written without U+2014 or U+2013 throughout.*
