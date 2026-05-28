# Adversarial Critic: Project Kalshi v3 (External-Feature ML Null Finding)

**Date:** 2026-05-24
**Reviewer:** Phase 3 adversarial-critic context
**Subject:** [06-model-results.md](06-model-results.md) gate report; [05-dataset-build.md](05-dataset-build.md); `src/kalshi_bot_v3/model.py`; `scripts/v3/run_v3_gate.py`; `scripts/v3/build_v3_dataset.py`; `scripts/v3/probe_inventory.py`.
**Mandate:** Stress-test the v3 null finding before the operator accepts it as the final verdict. Three orthogonal possibilities to disprove: (A) honest null, (B) gate-construction artifact, (C) repeat of an uncaught v2 failure mode.

## Executive summary

**Verdict: REJECT WITH AMENDED FRAMING.** The gate failure itself is real and the null direction is the right conclusion. But the FINAL-VERDICT cannot be written the way V3-B2's Section 6 wants. There is one Killer finding plus three Important findings that change the verdict's wording:

1. **Killer / verdict-correction.** V3-B2's C6 comparison is an empty test on this holdout. G2 and G3 trade the IDENTICAL 45 rows that v1 trades because the LogReg's predicted probability is `>= 0.70` on every holdout row (G2 min 0.8953, G3 min 0.7039 [`scripts/v3/run_v3_gate.py:431` anchored fit; my re-run]). C6 = 0.0pp is therefore not an ML-vs-v1 comparison; it is a mechanical equality. Saying "v3 fails C6" understates the situation: v3 was never able to PRODUCE a v1-differing rule on this holdout at all. The verdict must say "v3 was unable to express a non-trivial decision rule given the train set's structural single-class composition", not "v3 ran and lost by 2pp."

2. **Important / "v1 baseline" framing must change.** V3-B2 reports the v1 holdout mean as `-18.89pp` and notes this contradicts the time-scale-analysis.md `+12.47pp` claim. The root cause is concrete: v1's backtest dataset (`data/processed/sports_dataset.parquet`, n=423 total, 39 eligible) has **zero KXNFLWINS markets**, while V3-A's probe (`data/v3/probe_inventory_all_markets.parquet`, n=2828) found 955 KXNFLWINS markets in the same time window. The v3 holdout is 22/45 = 49% KXNFLWINS rows (`scripts/v3/run_v3_gate.py:489`, my reproduction below). v1's `+12.47pp` claim is from a 39-market universe v1 never traded the bulk of; v3's `-18.89pp` is from a 45-market universe that includes the entire NFL-team-wins block v1's backtest skipped. **The C6 comparison runs on a market mix that v1's "+12.47pp" was never measured on.** This is the v2 critic Section 9 finding repeated: false comparison on a domain v1 didn't trade.

3. **Important / "v1 confirmed" overreach.** V3-B2 Section 6.4 item 1 says the null finding "rejects H4 in the operator-friendly direction: v1 is the right strategy for this scale." That sentence is overstated by the data. On v3's holdout NFL slice (n=26, mean price 0.8285, mean P&L -40.19pp [my re-run via `kalshi_bot_v2.gate.realized_pnl_per_contract`]), v1's heuristic loses badly. v1 has actually attempted KXNFLWINS-27DET-8 in production (currently in the `closed` bucket of `data/live_trades/state.json`, status `live_cancelled`). If v1 had been filled on that order, late-2025 NFL underdog distribution would have hit v1's actual P&L. The honest framing is "v3 cannot beat v1 with external features on this holdout, AND this holdout reveals v1 has untested distributional fragility on NFL late-season wins. v1 keeps running on its tested-by-luck-of-the-fill universe, not because v3 proved v1 robust."

4. **Important / "Sanity check S3 passed" overstated.** S3's holdout (series, lifetime, price) table is computed but never INTERSECTED with v1's live trade universe (V3-B2 Section 4.3 explicitly defers this to Phase 3). I did the intersection. v1's attempted-orders log has 19 distinct series; v3's holdout has 5 series-prefixes; overlap is only `{KXNFLPLAYOFF, KXNFLWINS}` = 2 series. v1's actual attempted-orders sit in 17 series NOT in the v3 holdout (KXBOXING, KXUFCFIGHT, KXWCGAME, KXFOMEN, KXCS2, KXMLBSTATCOUNT, KXSTARTINGQBWEEK1, etc.). S3 is NOT a domain match.

5. **Minor / orthogonality protocol amendments.** With a stratified bootstrap, `season_month` flips from "drop" to "EXCLUDES 0" (CI [0.011, 1.437]). Adding `season_month` to the model does NOT fix the gate (in my re-run G4=[price, season_month] fails C1 by -36pp; G5=[price, season_month, league_dummy] passes C5 at +1.99pp but fails C1/C2/C6 by even larger margins). The protocol's strict-CI rule was not the binding failure. Minor noted; verdict unchanged.

**Net verdict: I do NOT sign off on V3-B2's writeup as-is. The data IS consistent with the null direction (sub-scenario (A) below) BUT the FINAL-VERDICT must be reframed to acknowledge that (a) C6 was a mechanical-equality test on this holdout, not an ML test; (b) the "v1 confirmed" claim is unsupported because v1's measured-edge dataset structurally excludes the KXNFLWINS markets dominating v3's holdout failure; (c) the S3 domain match check materially fails when intersected with v1's live attempted-orders log. The operator should proceed to write a NULL verdict, but use the language at the bottom of this doc, not V3-B2's.**

Each of the 8 tests below documents method, my result, and where it lands among Killer / Important / Minor.

## Test 1: C5 leak retest

**Method.** Re-execute `gate._kfold_splits(df_v3, n_folds=5)` on `data/v3/joined_v3_dataset.parquet` (147 rows). For each of the 4 folds, count training rows whose `close_time >= test_min`. Verify that the `trainer=` parameter is wired in `scripts/v3/run_v3_gate.py:431` so the anchored holdout model is never reused inside the CV.

**Result.** All 4 folds are chronologically clean (test_min strictly > train_cutoff, 0 training rows at or after each fold's `test_min`):

| Fold | train_n | test_n | train_cutoff | test_min | train_rows_>=_test_min |
|---|---:|---:|---|---|---:|
| 1 | 29 | 29 | 2025-10-27 14:46:51 UTC | 2025-11-03 08:01:39 UTC | 0 |
| 2 | 58 | 29 | 2025-11-24 08:01:48 UTC | 2025-11-25 08:01:56 UTC | 0 |
| 3 | 87 | 29 | 2025-12-09 08:02:13 UTC | 2025-12-15 08:01:45 UTC | 0 |
| 4 | 116 | 29 | 2025-12-30 08:02:49 UTC | 2025-12-30 08:02:56 UTC | 0 |

`scripts/v3/run_v3_gate.py:431` calls `evaluate(df, anchored, trainer=make_trainer(features), note=label)` for both G2 and G3. The trainer is wired correctly. The v2 Round-5 leak shape (pre-trained model evaluated on its own training set in folds 1-3 of 4) is structurally impossible in v3 because the gate retrains per fold.

Note Fold 4's boundary is uncomfortably tight: test_min is 7 SECONDS after train_cutoff. The chronological-order rule holds because Kalshi's `close_time` is timestamped to microseconds, but on a data shape where multiple markets close at near-identical timestamps a millisecond-jitter pipeline could produce a leak. Not a current bug; flagging as a Minor follow-up.

**Conclusion: C5 leak is NOT present. Sub-scenario (B) "gate-construction artifact" is rejected for the kfold mechanism.** S2's reported verdict is correct.

**Classification: Minor (Fold-4 boundary fragility).**

## Test 2: domain-match audit (v3 holdout vs v1 actual)

**Method.** Read `data/live_trades/state.json` (v1's runtime state). Enumerate every order across `intents`, `resting`, `filled`, `closed`. Compute series-prefix counts. Intersect with the v3 holdout's series-prefix counts from `data/v3/joined_v3_dataset.parquet` (chronological 30% tail of n=147). Then quantify what v1 actually trades vs what v3 evaluates v1 on. Then reproduce v1's "+12.47pp" claim from `research/time-scale-analysis.md` directly against `data/processed/sports_dataset.parquet`.

**Result A: v1's live attempted-orders distribution.**

34 orders total across all state buckets (3 filled, 12 resting, 19 cancelled-never-filled, 0 intents). Distinct series-prefixes attempted by v1:

```
KXNBAPLAYOFFWINS=4, KXMLBWINS=4, KXWCGAME=3, KXNFLPLAYOFF=3,
KXSTARTINGQBWEEK1=2, KXUFCFIGHT=2, KXNCAAFPLAYOFF=2, KXMLBSTATCOUNT=2,
KXNFLWINS=2, KXWCSQUAD=1, KXBOXING=1, KXWNBAWINS=1, KXWCSTAGEOFELIM=1,
KXFOMEN=1, KXNFLGAME=1, KXCS2=1, KXNEXTTEAMNFL=1, KXCITYNBAEXPAND=1, KXNEXTTEAMNHL=1
```

19 distinct series, every one with `market_mid_at_placement >= 0.70` (matches v1's eligibility filter).

**Result B: v3 holdout series-prefix distribution** (chronological 30% tail of n=147).

```
KXNFLWINS=22, KXNBAWINS=17, KXNFLPLAYOFF=4, KXNHLMETROPOLITAN=1, KXNHLCENTRAL=1
```

5 distinct series-prefixes.

**Result C: Intersection.**

| Quantity | Value |
|---|---:|
| v1 attempted orders that fall in series ALSO in v3 holdout | 5 of 34 = 14.7% |
| v3 holdout rows in series ALSO attempted by v1 | 26 of 45 = 57.8% |
| Series v1 attempted but NOT in v3 holdout | 17 of 19 (89%) |
| Series in v3 holdout but NOT in v1 attempted | 3 of 5 (60%) |

The v3 holdout's KXNBAWINS (17 rows) and KXNHL* (2 rows) are series v1 has never attempted in its live operations. The v3 holdout's KXNFLWINS (22 rows) IS a series v1 has attempted (specifically `KXNFLWINS-27DET-8` is in the `closed` bucket as a cancelled-not-filled order).

**Result D: reproduce v1's `+12.47pp` claim.**

Reading `data/processed/sports_dataset.parquet` (n=423 total markets) and applying v1's eligibility (lifetime [30, 180] days, `mid_price_at_T_small` in [0.70, 0.95]) yields exactly **n=39 eligible markets**, **100% YES rate**, **mean P&L +12.47pp**. The series mix of this n=39:

```
KXNBAWINS=16, KXMLBWINS=5, KXNFLGAME=3, KXUCLROUND=2, KXATPGRANDSLAM=1,
KXBALLONDOR=1, KXBOXING=1, KXCHARCOUNTLOLWORLDS=1, KXLEADERNBAAST=1,
KXMLBSTATCOUNT=1, KXNCAAFGAME=1, KXNFLTRADE=1, KXNHLCENTRAL=1,
KXNHLMETROPOLITAN=1, KXSTARTCLEBROWNS=1, KXSWIFTATTEND=1, KXWNBAROTY=1
```

**Zero KXNFLWINS markets.** Yet v3's probe (`data/v3/probe_inventory_all_markets.parquet`) finds **955 KXNFLWINS markets** in the same time window. The omission is structural to v1's backtest source, not just an empty cell.

**Result E: v1 backtest restricted to v3 holdout months.**

The v3 holdout close_time range is 2025-12-22 to 2026-04-13. On v1's BACKTEST dataset, restricting to `close_month >= 2025-12` gives n=23 markets, YES rate 100%, mean P&L +11.75pp. The slice consists of 16 KXNBAWINS + 7 misc (KXATPGRANDSLAM, KXBOXING, KXLEADERNBAAST, KXMLBSTATCOUNT, KXNFLTRADE, KXNHLCENTRAL, KXNHLMETROPOLITAN). **One KXNFLWINS in late-2025 onward in v1's backtest. v3's holdout has 22 KXNFLWINS in the same period.**

**Result F: v1 baseline broken out by v1-universe membership.**

On the v3 holdout, restricting v1's baseline to rows whose series-prefix v1 has attempted at least once in production:

| Slice | n | mean P&L (v1) |
|---|---:|---:|
| v3 holdout rows in series v1 has attempted (KXNFLWINS + KXNFLPLAYOFF) | 26 | **-40.19pp** |
| v3 holdout rows in series v1 has NEVER attempted (KXNBAWINS + KXNHL*) | 19 | **+10.26pp** |
| All v3 holdout (used in C6) | 45 | -18.89pp |

The v3 holdout's positive contribution is entirely from KXNBAWINS-and-KXNHL, series v1 has never traded.

**Conclusion.**

This intersects directly with the master plan S3 criterion ("holdout dataset's market characteristics must overlap v1's actual trading universe"). The S3 check as run is materially failing:

- v1's attempted-orders universe and v3's holdout universe overlap on only 2 of 19 series (`{KXNFLPLAYOFF, KXNFLWINS}`).
- v1's backtest-measured edge of +12.47pp was computed on a universe (39 markets, 0 KXNFLWINS) that doesn't include the dominant subgroup of v3's holdout failure (22 KXNFLWINS = -40.19pp).
- The C6 comparison "v3 minus v1 = 0.0pp" is therefore not a real test of "does v3 beat v1 on v1's domain"; it is the mechanical equality of two rules that both trade everything (Test 6).

Sub-scenario (A) "honest null on the data shape" SURVIVES but with an amended framing: the v3 holdout is NOT v1's domain. The honest claim is "an external-feature ML model has no demonstrated edge on long-horizon sports markets, and the same chronological-30% holdout reveals v1's untested NFL win-totals exposure costs -40pp at scale."

**Classification: Killer for the V3-B2 framing of "v3 cannot beat v1 on v1's domain." Important: the C6 comparison was never a v1-domain test. The verdict must say so.**

## Test 3: feature look-ahead spot-check

**Method.** Pull 5 random NFL rows from `data/v3/joined_v3_dataset.parquet` (seed 42). For each, recompute `nfl_games_played_pre_t35d` from `data/v3/nflverse_cache/games.parquet` using the build script's stated rule (game_type='REG', gameday strictly < t35d - 1 day, in season_year). Confirm the most recent counted game is strictly before t35d - 1 day.

**Result.**

| Ticker | Team | T-35d UTC | Strict cutoff | Stored gp | Recomputed gp | Most recent counted game | Match |
|---|---|---|---|---:|---:|---|---|
| KXNFLWINS-KC-25B-T8 | KC | 2025-11-17 08:02:26 | < 2025-11-16 | 9 | 9 | 2025-11-02 | OK |
| KXNFLWINS-BUF-25B-T7 | BUF | 2025-10-27 08:01:39 | < 2025-10-26 | 6 | 6 | 2025-10-13 | OK |
| KXNFLWINS-NO-25B-T3 | NO | 2025-11-10 08:02:06 | < 2025-11-09 | 9 | 9 | 2025-11-02 | OK |
| KXNFLWINS-SEA-25B-T4 | SEA | 2025-09-16 07:01:18 | < 2025-09-15 | 2 | 2 | 2025-09-14 | OK |
| KXNFLWINS-DET-25B-T8 | DET | 2026-01-05 17:43:07 | < 2025-11-30 | 12 | 12 | 2025-11-27 | OK |

All 5 rows match. The most recent game counted in each row is strictly before the conservative cutoff (T-35d - 1 day). I additionally verified the KC row against the full 2025 NFL season: KC played its 9th regular-season game 2025-11-02 (loss to BUF); KC's pre-2025-11-16 record was 5-4 (matches stored `nfl_w_pct_pre_t35d = 0.5556`).

**Conclusion: No look-ahead leak in `nfl_games_played_pre_t35d` for the 5-row sample. Sub-scenario (C) "v3 inherited a feature look-ahead v2 missed" is rejected for this feature.**

**Classification: Clean. No finding.**

## Test 4: orthogonality protocol reconsideration

**Method.** Re-run the orthogonality bootstrap with stratified resampling (each bootstrap forced to contain both YES and NO outcomes proportional to actuals) for the 5 features the original protocol dropped due to "CI includes zero." Specifically: `lifetime_days`, `season_month`, `mlb_w_pct_pre_t35d`, `mlb_pyth_w_pct_pre_t35d`, `mlb_games_back`, `mlb_run_diff_per_game`. Confirm the NFL team-stat features cannot be saved by stratification because the NFL train subset has zero NO outcomes (75 of 75 YES).

**Result A: NFL team-stat features are unrecoverable.**

| Feature | n_train_with_feature | NOs in train | YESes in train |
|---|---:|---:|---:|
| nfl_w_pct_pre_t35d | 75 | 0 | 75 |
| nfl_pyth_w_pct_pre_t35d | 75 | 0 | 75 |
| nfl_recent5_w_pct | 75 | 0 | 75 |
| nfl_point_diff_per_game | 75 | 0 | 75 |

Stratified bootstrap requires at least one row from each class; the NFL training subset's outcome variance is identically zero. The original protocol's "drop, single-class subsample" verdict was the correct call. Stratification cannot help. **NOT a protocol failure.**

**Result B: stratified bootstrap on other features.**

| Feature | Standard CI | Stratified CI | CI excludes 0? |
|---|---|---|---|
| lifetime_days | [-0.024, +0.010] | (drops in standard, auc_delta -0.059) | No |
| season_month | [-0.182, +1.483] | **[+0.011, +1.437]** | **Yes (stratified flips it)** |
| mlb_w_pct_pre_t35d (n=15) | [-0.102, +0.028] | [-0.096, +0.027] | No |
| mlb_pyth_w_pct_pre_t35d (n=15) | [-0.083, +0.087] | [-0.081, +0.079] | No |
| mlb_games_back (n=15) | [-0.068, +0.451] | [-0.052, +0.464] | No |
| mlb_run_diff_per_game (n=15) | [-0.515, +0.630] | [-0.499, +0.584] | No |

Only `season_month` flips. The 4 MLB features stay dropped under stratified bootstrap; the n=15 sample is too small for any reasonable CI to exclude zero.

**Result C: actually run the gate with `season_month` added.**

I ran 4 gate variants (full n=147 dataset, locked criteria, leak-free CV via `trainer=`):

| Variant | Features | C1 holdout mean | C2 CI lo | C5 pooled | C6 v3-v1 | Overall |
|---|---|---:|---:|---:|---:|---|
| G2 (baseline) | price | -18.89pp | -32.54pp | -1.49pp | 0.00pp | FAIL |
| G3 (baseline) | price + nfl_games_played | -18.89pp | -32.54pp | -1.26pp | 0.00pp | FAIL |
| G4 (new) | price + season_month | **-36.42pp** | **-60.70pp** | -1.03pp | **-17.53pp** | FAIL (worse) |
| G5 (new) | price + season_month + nfl_games_played | -35.21pp | -56.90pp | **+1.99pp** | -16.32pp | FAIL (C5 only passes) |

G4 fails C1/C2/C6 BY LARGER MARGINS than G2. The model now abstains on some holdout rows (n=16 trades vs 45 in G2/G3), but the trades it does take are catastrophic. G5's C5 = +1.99pp is interesting but C1/C2 fail much harder. The protocol's strict-CI test was NOT the binding failure; even with the additional feature retained, the gate still fails the C1/C2 binding criteria.

**Conclusion. The protocol's "season_month dropped due to CI includes zero" was a marginal call. Stratified bootstrap retains it. Running the locked gate with the retained feature makes the verdict FAIL HARDER, not pass. Sub-scenario (B) "protocol over-aggression hides a passing model" is REJECTED.**

**Classification: Minor finding (protocol should use stratified bootstrap for documentation completeness; verdict unchanged).**

## Test 5: multiple-testing audit

**Method.** Search `src/kalshi_bot_v3/model.py`, `scripts/v3/run_v3_gate.py`, `scripts/v3/build_v3_dataset.py` for: (a) variable-name suffixes `_grid` / `_best` / `_tuned`; (b) iterations over threshold or hyperparameter lists; (c) hidden hyperparameter sweeps; (d) the locked constants TRADE_PROB_THRESHOLD, LOGREG_C, class_weight.

**Result.**

- `model.py:50` locks `TRADE_PROB_THRESHOLD = 0.70` at module top.
- `model.py:54` locks `LOGREG_C = 1.0`.
- `model.py:108` and `model.py:156` hardcode `class_weight=None`.
- No grids, no sweeps, no `for thresh in [...]` patterns. The runner exercises exactly 3 rules (G1, G2, G3) per `06-model-results.md` Section 2.
- The trainer's `max_iter=1000` and `random_state=42` are locked.

The orthogonality script (`build_v3_dataset.py`) has 12 candidate features but applies a uniform retain/drop test; it is feature selection, not hyperparameter selection. Even counting it as such, 12 feature decisions + 3 rule trials = 15 trials. Bonferroni at family-wise alpha 0.05/15 = 0.00333 (99.67% CI). At that CI level on the v3 holdout's n=45, the CI lower bound stays well below zero (the 95% CI lower is already -32.54pp; widening the CI makes failure MORE certain).

**Conclusion: No multiple-testing inflation; the locked rules are honestly locked.**

**Classification: Clean.**

## Test 6: G2/G3 mechanical equivalence with v1

**Method.** Fit G2 and G3 anchored models on the chronological 70% (n=102). Score every holdout row. Count rows where predicted prob >= 0.70 (the trade threshold).

**Result.**

| Rule | Holdout predicted probs (min / max / mean) | Rows >= 0.70 |
|---|---|---:|
| G2 [price] | 0.8953 / 0.9828 / 0.9561 | **45 of 45** |
| G3 [price, nfl_games_played] | 0.7039 / 0.9996 / 0.9533 | **45 of 45** |

Both G2 and G3 produce predicted probs >= 0.70 on EVERY holdout row, so both trade the identical 45 rows v1 trades. Realized P&L = identical = -18.89pp. C6 = `v3_mean - v1_mean` = `-18.89 - (-18.89)` = 0.0pp. By construction.

**Conclusion.** This is scenario (a) in the test prompt: v3 traded the same 45 rows as v1 by mechanical equality. C6 = 0.0pp does NOT mean "v3 fails to add signal on this holdout"; it means "v3 was unable to express a v1-differing decision on this holdout because the train set is 96% YES and the LogReg saturates above 0.70 on every plausible price/feature combination in the holdout."

The C6 criterion as locked is informative only when the v3 rule and the v1 rule can differ. On this holdout they cannot. **The "v3 minus v1 = 0pp" reported in V3-B2 Section 2 is NOT a statistically interpretable test result; it is a structural identity given (i) the train YES rate 96% and (ii) the gate's `prob >= 0.70` threshold.**

The honest C6-related sentence the FINAL-VERDICT should say: "v3 was unable to produce a non-trivial decision rule on the chronological 70/30 holdout because the train set's 96% YES rate forces the LogReg above 0.70 on every plausible feature vector. C6's reading of 0.0pp is a structural identity, not a measured null."

**Classification: Killer for verdict framing. Verdict direction unchanged.**

## Test 7: counter-narrative attempt

**Method.** Three alternative gate designs: (i) 60/40 split (larger holdout dilutes late-NFL); (ii) 80/20 split (smaller, later holdout); (iii) rolling-origin per-fold retrained predictions pooled. For each, re-fit G2 and compute v3 mean and v1 mean.

**Result.**

| Variant | train_n | holdout_n | v3 mean | v1 mean | delta |
|---|---:|---:|---:|---:|---:|
| 60/40 split | 88 | 59 | -11.57pp | -11.57pp | 0.00pp |
| 80/20 split | 117 | 30 | -11.52pp | -11.52pp | 0.00pp |
| Rolling-origin pooled (5 folds, per-fold retrain) | walking | 114 | -1.49pp | -1.03pp | -0.46pp |

A 60/40 split still fails C1 by 11.57pp; the larger holdout dilutes but doesn't eliminate the late-season NFL hit. An 80/20 split is structurally similar.

**Per-month breakdown of the entire dataset (v1 baseline P&L):**

| Close month | n | YES rate | mean P&L |
|---|---:|---:|---:|
| 2025-09 | 6 | 67% | (mixed) |
| 2025-10 | 23 | 96% | + |
| 2025-11 | 32 | 100% | + |
| 2025-12 | 57 | 84% | + |
| 2026-01 | 10 | 40% | -46.24pp (NFL season-end) |
| 2026-03 | 1 | 100% | + |
| 2026-04 | 18 | 100% | +10.6pp (NBA season-end) |

The Jan-2026 NFL slice (n=10, 40% YES) is the dominant failure source. Any chronological split that puts this slice in the holdout fails. December 2025 is mixed (84% YES) and contains both NFL late-season under-performers and NBA in-season favorites.

**Other counter-narratives:**

- **What if v3 added GDELT or news features?** Per V3-B audit Section 5.2, GDELT has true AS-OF support back to 2017. It was deferred because of orthogonality risk and the project's time budget. The literature ceiling (V3-D: "free-public-feature sports prediction tops out at 65-67% game-level accuracy, +1-3pp gross edge on season-long markets") foreshadows a tiny effect even if GDELT survives. Given the literature ceiling sits AT or BELOW C6's 2pp floor, adding GDELT is unlikely to flip the verdict.

- **What if v3 trained on multiple seasons (back to 2023)?** Per V3-A Section 6: Kalshi `/historical/cutoff` returned 2026-03-25. The cache and probe cover 2025-03 to 2026-04. Going back to 2023 would require pulling additional historical Kalshi market data; V3-A specifically tested this and the probe inventory cap on n=147 is what the data shape allows. The cache does not have a multi-season pull and this critic is not authorized to expand it. **Not a same-day-actionable counter-narrative.**

- **What if v3 used per-league models?** V3-B2 Section 5 ran this: NFL-only (n=104) has train YES rate 100% so the trainer returns a degenerate fit; G2/G3 abstain entirely; v1 trades all 32 holdout markets and loses -30.88pp. MLB-only (n=16) has structural C4 fail (holdout n=5 < 15). Per-league does not work.

**Conclusion: I tried to find a leak-free, design-variation gate that flips the verdict. None of the three plausible variants do.**

**Classification: Clean. No counter-narrative survives.**

## Test 8: foreshadow audit

**Method.** Two sub-scenarios from the test prompt:
- **Sub-scenario A:** v3 holdout is brutal because of chronological shift; v1 fails there because v1 doesn't actually trade this distribution.
- **Sub-scenario B:** v3 holdout reveals v1's edge is also fragile to distribution; v1 has been lucky on its actual distribution.

I tested by comparing v1's backtest distribution against v3's holdout distribution.

**Result.**

(a) **v1's `+12.47pp` claim is from a 39-eligible-market universe** computed in `research/time-scale-analysis.md`. Reproducing it from `data/processed/sports_dataset.parquet`: n=39, YES rate 100%, mean P&L +12.47pp.

(b) **v1's backtest dataset has ZERO KXNFLWINS markets.** v3's probe of the same time window found 955 KXNFLWINS markets total, 95 of them v1-eligible. **The v1 backtest source structurally excludes the entire NFL-team-wins block that dominates v3's holdout.**

(c) **v1's live strategy DOES include KXNFLWINS.** Per `scripts/paper_trade_favorite.py:460` (`category="Sports"`) and `src/kalshi_bot/strategy/market_scanner.py:131-138` (iterates `/series?category=Sports` and pulls every series's open markets), v1 trades the FULL sports universe. The `data/live_trades/state.json` `closed` bucket contains `KXNFLWINS-27DET-8` as a cancelled-not-filled order. v1 has been ATTEMPTING to trade KXNFLWINS markets; the +12.47pp claim was just never measured on KXNFLWINS because the backtest dataset's market enumeration didn't include them.

(d) **v3 holdout NFL slice = the precise failure zone.** v3 holdout NFL n=26, YES rate 46.2%, mean P&L -40.19pp. v3 holdout's non-NFL slice (NBA + NHL) n=19, mean P&L +10.26pp (broadly matching v1's backtest claim on its NBA-heavy universe).

(e) **The literature ceiling foreshadow alone does NOT explain the -18.89pp magnitude.** Per V3-D, free-public-feature edge tops out at +1-3pp. If the v3 model added zero signal and v1 was honestly +5 to +12pp on its true distribution, the gate would fail by 1-3pp (signal isn't there), not by 21pp. The 21pp failure is dominated by v1's own per-NFL-slice exposure (-40pp on a 49%-of-holdout slice), which is sub-scenario B territory.

**Which sub-scenario does the data support?**

Both. The chronological-shift mechanic AND the v1-edge fragility are simultaneously real:

- **Sub-scenario A in action.** The NFL train slice is single-class (100% YES); the NFL holdout slice is 46% YES. No ML rule trained on the prefix can flag the NFL NOs because the prefix has zero NFL NOs. This IS the literature-ceiling story for the v3 model failing to add lift over v1.
- **Sub-scenario B in action.** The v1 baseline on the v3 holdout's NFL slice realizes -40.19pp. v1's backtest claim of +12.47pp was computed on a 39-market dataset that omits the entire NFL-team-wins block; v1's claim has never been measured on KXNFLWINS markets in the literature. **v1's edge has not been demonstrated on the distribution that dominates the v3 failure zone.**

The v3 holdout's information about v1 is: "if v1's live strategy had filled enough KXNFLWINS markets to span late-2025, v1's realized P&L would have been -40pp on that subgroup." This is novel information about v1, not just about v3.

**Conclusion: A clean null finding for v3 is honest. Conjointly, the v3 holdout REVEALED a v1 fragility the backtest never tested. The FINAL-VERDICT must note both.**

**Classification: Important for the FINAL-VERDICT framing. The v3 null is honest BUT it cannot be reported as "v1 confirmed" without noting that v1's claim was never measured on KXNFLWINS.**

## Findings, in priority order

### Killer (one item)

1. **The C6 comparison is mechanical-equality, not a measured null.** G2 and G3 trade the same 45 holdout rows as v1 (G2 min predicted prob 0.8953; G3 min 0.7039; both > 0.70 on every row). C6 = 0.0pp is a structural identity, not a measured difference between rules. The FINAL-VERDICT must say "v3 was unable to express a non-trivial decision rule on this holdout because the train YES rate of 96% saturates the LogReg above 0.70 on every row", not "v3 ran and lost to v1 by 2pp." (Source: my reproduction via `scripts/v3/run_v3_gate.py:431` + `src/kalshi_bot_v3/model.py:125`.)

   *Action required:* rewrite V3-B2 Section 2 and the FINAL-VERDICT's C6 sentence to acknowledge mechanical equality.

### Important (three items)

2. **The "v1 confirmed" framing in V3-B2 Section 6.4 item 1 overreaches.** v1's `+12.47pp` claim is from a 39-market backtest dataset that contains zero KXNFLWINS markets. v3's holdout is 49% KXNFLWINS (22 of 45). v1's measured edge has never been tested on the distribution that dominates v3's holdout failure. The honest verdict is "v3 cannot beat v1 with external features on this holdout, AND this holdout reveals v1's claimed edge has untested distributional exposure on NFL late-season win-totals." (Source: `data/processed/sports_dataset.parquet` filtered by v1 eligibility; `data/v3/probe_inventory_all_markets.parquet` series counts.)

   *Action required:* rewrite V3-B2 Section 6.4 item 1 to remove "v1 confirmed" and replace with the bilateral framing above. The FINAL-VERDICT should specifically note that v1's measured-edge dataset structurally omits KXNFLWINS.

3. **S3 domain-match check materially fails when intersected with v1's actual attempted-orders universe.** The S3 audit reported the v3 holdout's (series, lifetime, price) cells but never intersected them with v1's live trade universe (V3-B2 Section 4.3 explicitly defers this to the critic). I did the intersection: v1's attempted-orders universe = 19 distinct series-prefixes; v3 holdout = 5 series-prefixes; overlap = 2 (`{KXNFLPLAYOFF, KXNFLWINS}`). v1 has attempted 17 series-prefixes in production that the v3 holdout contains zero rows of (`KXBOXING`, `KXUFCFIGHT`, `KXWCGAME`, `KXFOMEN`, `KXCS2`, `KXMLBSTATCOUNT`, etc.). The S3 criterion as defined is NOT a clean pass.

   *Action required:* re-classify S3 as "FAIL (v3 holdout 2/19 = 10.5% series-prefix overlap with v1's live attempted-orders)" in the FINAL-VERDICT. Or amend S3's pass criteria to be probe-coverage-based (was the v3 probe representative of v1's universe? No, by 17/19) rather than holdout-coverage-based.

4. **v1's backtest dataset is structurally narrower than v3's probe.** v1's `sports_dataset.parquet` has n=423 markets with 39 v1-eligible across 17 series-prefixes; v3's `probe_inventory_all_markets.parquet` has n=2828 markets with 147 v1-eligible across 8 groups. The two datasets disagree by 2.4x on the same time window for the same eligibility filter. This is a long-standing project-state finding, not a v3 bug. But it means the v1 backtest's +12.47pp result has unknown coverage and the FINAL-VERDICT cannot use it as "v1's known edge."

   *Action required:* flag this for a future v1 rebuild (out of v3 scope, but operator-relevant).

### Minor (three items)

5. **Stratified bootstrap on the orthogonality protocol retains `season_month`.** The protocol's strict CI test dropped `season_month` (CI [-0.182, +1.483] standard); stratified bootstrap gives CI [+0.011, +1.437], excludes zero. Running the gate with `season_month` added makes the verdict FAIL HARDER (C1 worsens to -36.4pp). The original protocol was not over-aggressive; the verdict is unchanged.

   *Action required:* none for the v3 verdict. Update the orthogonality script to use stratified bootstrap if v3 is ever revived.

6. **Fold-4 boundary is 7 seconds.** Test 1 verified the 4 walk-forward fold splits are chronologically clean, but Fold 4's test_min is only 7 SECONDS after its train_cutoff (`2025-12-30 08:02:49` vs `08:02:56`). With Kalshi's microsecond timestamps this is technically clean; with a coarser-resolution timestamp pipeline a leak would emerge.

   *Action required:* document in the FINAL-VERDICT that future v3-style work should use embargo (Lopez de Prado per V3-D's literature) to add a safety buffer.

7. **`KC` 2025-2026 record in nflverse is consistent with the dataset.** Spot-check on KXNFLWINS-KC-25B-T8: stored `nfl_w_pct=0.5556` = 5/9 wins by 2025-11-16. Recomputed: 5-4 by 2025-11-02 (last counted game). Matches. (KC's actual final 2025 record was 6-11 per nflverse; the dataset's pre-T-35d snapshot is internally consistent.)

   *Action required:* none.

## Specific recommended changes

To `research/v3/06-model-results.md`:

- Section 2.1 "Criteria pass/fail": footnote on C6=0.0pp must read "C6 = 0.0pp by construction; G2 and G3 trade the same 45 rows as v1 because LogReg predicted probs are >= 0.70 on every holdout row (G2 min 0.8953, G3 min 0.7039). C6 cannot distinguish v3 from v1 on this holdout."
- Section 2.2 "Why G2 and G3 produce identical holdout numbers to G1" already gets this RIGHT. The fix is to propagate this acknowledgement to Sections 6.1, 6.4 and the executive summary so the reader cannot mistake "v3 fails C6" for "v3 ran a real comparison and lost."
- Section 6.4 item 1: replace "rejects H4 in the operator-friendly direction: v1 is the right strategy for this scale" with "rejects H4 directionally: external team-stat features at n=147 with leak-free CV cannot improve over v1's heuristic on the available data. v1's measured edge has not been demonstrated on KXNFLWINS markets, which dominate the v3 holdout failure zone; v1 IS the right strategy for the project's known scale but its edge magnitude on KXNFLWINS specifically remains untested."
- Section 4.3 "S3 domain match" final paragraph: change "V3-B2 does not perform that intersection here" to "Performed by Phase 3 critic: 2/19 = 10.5% series-prefix overlap with v1's live attempted-orders. S3 materially fails."
- Section 7 v2 failure-mode table, "Domain mismatch" row: change PARTIALLY ADDRESSED to "Domain mismatch unresolved. v3 holdout is built on the same eligibility filter as v1 but v3's probe enumerates 95 KXNFLWINS markets while v1's own backtest dataset has 0. The C6 comparison is computed on a market type v1's measured edge has never been demonstrated on."

To `research/v3/iterations.md` Iter 2:

- "Verdict: NULL FINDING": add "with verdict-framing amendments from Phase 3 critic" pointer.

To the eventual FINAL-VERDICT.md:

- Don't write "v1 confirmed." Write "v3 closes as null at n=147 with leak-free CV; v3 holdout REVEALS that v1's measured edge has untested exposure on KXNFLWINS late-season markets which v1's backtest dataset structurally omits. v1 continues running on its current configuration; an honest v1 rebuild on a complete sports universe is a separate work item."

## Citations

- Gate code: `src/kalshi_bot_v2/gate.py:139-149` (`_kfold_splits`), `:152-160` (`v1_decision_fn`), `:163-303` (`evaluate`), `:283-292` (C6 logic)
- Trainer + decision rule: `src/kalshi_bot_v3/model.py:50` (`TRADE_PROB_THRESHOLD=0.70`), `:54` (`LOGREG_C=1.0`), `:78-127` (`make_trainer`), `:182-197` (`make_anchored_decision_fn`)
- Gate runner: `scripts/v3/run_v3_gate.py:399-432` (G1/G2/G3 wiring; trainer kwarg confirmed at `:428` and `:431`)
- Dataset build: `scripts/v3/build_v3_dataset.py:272-399` (build loop with strict t35d_minus1), `:402-442` (leak audit), `:445-617` (orthogonality protocol)
- v3 dataset: `data/v3/joined_v3_dataset.parquet` (n=147, sorted by close_time)
- v3 inventory: `data/v3/probe_inventory_all_markets.parquet` (n=2828 markets across 100 series-prefixes), `data/v3/probe_inventory_eligible_with_team.parquet` (n=147)
- v1 backtest source: `data/processed/sports_dataset.parquet` (n=423; 39 v1-eligible; 0 KXNFLWINS)
- v1 live state: `data/live_trades/state.json` (3 filled + 12 resting + 19 closed/cancelled = 34 orders across 19 series-prefixes)
- v1 strategy: `src/kalshi_bot/strategy/favorite_maker.py:47-66` (eligibility filter); `src/kalshi_bot/strategy/market_scanner.py:118-152` (scanner iterates all series in `category=Sports`); `scripts/paper_trade_favorite.py:460` (`category="Sports"`)
- v3 probe inventory: `scripts/v3/probe_inventory.py:93-156` (hardcoded series list; does NOT enumerate KXBOXING, KXUFCFIGHT, KXWCGAME, KXFOMEN, KXCS2, KXMLBSTATCOUNT, etc.)
- v1 +12.47pp claim: `research/time-scale-analysis.md` Section 2 (n=39 eligible markets, all 30-180d)
- v2 critic for voice and prior failure modes: `research/v2/06-critic.md` Section 9 (false comparison on a domain v1 doesn't trade), Section 3 (in-sample CV leak)
- v1 critic for voice: `research/critic-favorite-maker.md`
- v3 master plan S3 criterion: `research/v3/00-master-plan.md` Section 5 (S1/S2/S3)
- V3-B2 model results doc: `research/v3/06-model-results.md` Sections 2-7
- V3-B1 dataset doc: `research/v3/05-dataset-build.md` Sections 1-9 (orthogonality protocol Section 3, leak audit Section 5)
- V3-D literature ceiling: `research/v3/04-literature.md` Topic B (free-public-feature edge +1-3pp), Topic C (Lopez de Prado embargo)
- Reproductions: all 8 tests above re-ran the dataset and code directly via inline Python, not from cached JSON.

## Final position

**I do NOT sign off on V3-B2's framing of the null finding.** The verdict direction (null) is right. The verdict's framing is not.

If V3-B2's Section 6 is rewritten per the recommendations above (and the FINAL-VERDICT carries those amendments forward), the v3 verdict can proceed. The honest claim is "v3 cannot demonstrate ML lift on this holdout; the holdout simultaneously reveals an untested v1 distributional exposure on KXNFLWINS."

If V3-B2's Section 6 is NOT rewritten, the FINAL-VERDICT will mislead by claiming "v1 confirmed" when in fact v1's claimed edge has never been measured on the dominant subgroup of v3's holdout failure. That is the exact false-comparison failure mode the v2 critic flagged in 2026-05-23 v2/06-critic.md Section 9, and v3 has reproduced it in a slightly different shape.

Operator's choice: rewrite, or accept the published-as-is framing as a known limitation.

The kill-early preference (per `feedback_kill_early.md`) and the project's stated commitment to honest-null-over-contaminated-ship both lean toward "rewrite the verdict, then ship the kill."
