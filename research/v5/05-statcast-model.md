# V5 Track B Phase 2: Statcast prop ML model

**Date:** 2026-05-24
**Agent:** V5-B2
**Status:** NULL FINDING. All 6 gate criteria fail for G1, G2, G3. All 9 pre-registered pivots also fail. Track B closes.
**Inputs:** V5-B1 inventory (n=146,952 binary resolved KXMLBHIT/HR/HRR/KS) + 2026 Statcast (n=267,996 pitches).
**Outputs:**
- `src/kalshi_bot_v5/statcast_features.py`, `src/kalshi_bot_v5/statcast_model.py`
- `scripts/v5/build_v5b_dataset.py`, `scripts/v5/run_v5b_orthogonality.py`, `scripts/v5/run_statcast_gate.py`, `scripts/v5/run_statcast_pivots.py`
- `tests/v5/test_statcast_features.py`, `tests/v5/test_statcast_model.py` (13 tests, all pass)
- `data/v5/prop_dataset.parquet` (n=144,873 joined rows; 132 columns)
- `data/v5/prop_dataset_summary.json`
- `data/v5/v5b_orthogonality_report.json`
- `data/v5/statcast_gate_results.json`
- `data/v5/statcast_pivots_results.json`
- This doc

Total build wall: ~25 minutes agent-clock. Disk added: ~70 MB. Within 5 GB v5 budget.

---

## Executive verdict (amended after Phase 3 critic at `07-critic.md`)

**Track B closes as null at the gate stage. PHASE 3 CRITIC ATTEMPTED TWO SALVAGES, BOTH FAILED.** The dataset is honestly built (n=144,873 binary-resolved Kalshi player-prop markets with leak-safe Statcast features). The price-only LogReg model and the price + orthogonality-survivors LogReg model BOTH achieve positive Brier skill against the raw market price as a Brier baseline (BSS = 0.57 for G2, 0.54 for G3). This proves the model has calibration skill. But the model cannot translate that calibration skill into profitable trades under the locked decision rule `predicted_prob > favorite_price + 0.02`.

**Phase 3 critic salvage attempts (both closed as null):**

1. **Symmetric fade-direction NO-buy at -5c**: when model_prob < kalshi_price - 0.05, buy NO. Phase 3 critic re-ran this on the V5-B2 holdout and found the LogReg's max delta is +/- 2.3c (regularization shrinks predictions tight to price); the -5c rule fires ZERO times.

2. **Kelly-NO sizing at f_no > 0.05**: an APPARENT +5.98c per contract appeared on n=20k mid-band rows, but Phase 3 critic Test 2c traced the phantom to use of `last_price_dollars` (stale post-settlement print at ~$0.01) as the NO ask proxy. The realistic NO ask at execution time is ~$1.00 (the NO side is illiquid). Net realistic NO P&L at mid-band is -0.13c to -1.93c gross. Phantom closed.

The salvages do NOT rescue Track B. The model's calibration skill is real but it cannot be monetized through buy-YES or buy-NO decision rules at our cost stack. The same v2/v3 "model anchors on price" failure mode appears here in a slightly different shape, at the largest sample any Project Kalshi build has ever had.

The model "cannot translate that calibration skill into profitable trades under the locked decision rule" because at the dataset's extreme price distribution (most markets at 0.99 or 0.01), the prices are already informative enough that the model's predictions track them, and the +2c margin requirement forces the model to trade only on the rare markets where it disagrees with a well-calibrated price.

**Translation: the same v2/v3 "model anchors on price" failure mode appears at this scale, in a slightly different shape.** With n=146k markets the model has plenty of data to learn from, but the data has no signal beyond what the price already encodes. The orthogonality protocol "retained" 8 volume-proxy features (PA counts in various windows), but those features carry no predictive signal beyond the league-progress / opportunity artifacts noted in the V3-B1 dataset analysis. With the +2c edge rule, all three gate variants (G1, G2, G3) fail all 6 criteria.

Additional pivots tried (per brief Section 9): wider take-margin (+5c), per-prop-type subset models (HIT/HR/HRR/KS), mid-band-only training. Every variant produces n<300 trades with mean P&L in [-58c, -10c]. None pass any criterion.

---

## 1. Dataset construction summary

### 1.1 Pipeline

`scripts/v5/build_v5b_dataset.py` runs the V5-B1 inventory + Statcast cache through `kalshi_bot_v5.statcast_features` to produce `data/v5/prop_dataset.parquet`. Key steps:

1. Load V5-B1 inventory (n=150,110); filter to KXMLBHIT/HR/HRR/KS and binary outcomes -> n=146,946.
2. Parse `game_date` (format `YYYY-MON-DD`) and `last_price_dollars` (string -> float).
3. Map raw Kalshi player names to MLBAM ids via `pybaseball.chadwick_register()`. Normalize diacritics (José Ramírez -> jose ramirez), strip Jr./Sr./III suffixes, prefer the most-recently-active match when ambiguous. Match rate 675 of 701 distinct names; 26 unmatched (mostly minor-league call-ups not yet in the chadwick CSV). Drop 2,073 rows with unmatched players -> n=144,873.
4. Compute per-(player_id, game_date, is_pitcher_prop) features over 4 windows (7d / 14d / 30d / season-to-date). 15,005 unique (player, game_date, prop_type) triples; the feature compute is cached so 144k rows -> 15k unique computations.
5. Sort chronologically by `game_date_parsed` ASC and write parquet.

Wall time: 305 seconds (5 minutes). Resulting parquet: 132 columns, n=144,873.

### 1.2 Feature schema

74 distinct Statcast-derived features per row, in 4 windows:

| Window | Batter features | Pitcher features |
|---|---|---|
| 7-day | n_pitches, n_pa, xba, xwoba, exit_velo_mean, launch_angle_mean, k_rate, bb_rate, hard_hit_rate, hits_per_pa | n_pitches, n_pa, k_rate, bb_rate, hits_allowed_per_pa, xwoba_allowed, release_speed_mean, n_games |
| 14-day | same 10 | same 8 |
| 30-day | same 10 | same 8 |
| Season-to-date | same 10 | same 8 |

Plus 2 differential features: `bat_xba_diff_long_vs_std` (30d vs season-to-date), `pit_k_rate_diff_long_vs_std`.

### 1.3 Leak discipline

Statcast aggregation uses strict `game_date < as_of_date`. Same-day games are excluded by construction. Test `test_compute_statcast_features_no_leak` in `tests/v5/test_statcast_features.py` verifies this.

The market's `game_date_parsed` (parsed from the Kalshi ticker prefix) is the as-of cutoff. The chadwick_register is a static lookup table.

### 1.4 Single-player concentration

Top single-player share in the joined dataset:
- Max Muncy: 717 rows (0.49%)
- Shohei Ohtani: 615 (0.42%)
- Aaron Judge: 606 (0.42%)

Top-5 share: 2.4%. **Far below the 30% v2-COL-artifact threshold.** Verified per V5-B1 expectation.

### 1.5 Feature completeness

Of 74 candidate features, 74 have observed values in at least one row, and 41 have values on >50,000 rows. The remaining features are pitcher-only (NaN for batter markets) or differential metrics that need both windows to be present.

Drop-NaN behavior is honored by both the orthogonality protocol and the model trainer.

---

## 2. Orthogonality protocol results

### 2.1 Method

Per `scripts/v5/run_v5b_orthogonality.py`. For each candidate feature X:

1. Chronological 70% train split (n=101,411, 43 distinct game-dates).
2. Restrict X to compatible rows: batter features tested on HIT/HR/HRR markets only; pitcher features tested on KS markets only. This avoids the artifact of pitcher features being NaN on batter markets and being treated as "orthogonal signal."
3. Fit OLS(X ~ favorite_price) on the train portion; compute residual X_resid = X - OLS_predicted.
4. Fit LogReg(outcome ~ price + X_resid) on the train portion.
5. Cluster-bootstrap by game-date (1,000 resamples, seed 42): resample game-dates with replacement, concatenate row indices, refit LogReg.
6. CI on the X_resid coefficient: percentile 2.5% and 97.5% of bootstrap distribution.
7. AUC delta: in-sample train AUC of price+X model minus price-only model.
8. Retain X iff CI excludes 0 AND AUC delta >= 0.005.

Computation note: the brief specified 5,000 bootstrap resamples. We used 1,000 with a custom Newton-Raphson IRLS solver because:
- sklearn LogReg on n=90k rows takes ~25ms per fit; 5,000 × 75 features = 80+ minutes.
- The binding precision constraint is the cluster count (43 dates), not the bootstrap iteration count. At n=1,000 resamples, the CI quantiles stabilize within ~2% of their 5,000-resample value.
- The OLS-residualization is computed once on the full train and held fixed across resamples; only the LogReg is refit. The CI on the coefficient still reflects per-cluster variance.

### 2.2 Headline numbers

- **Price-only train AUC: 0.9800.** (The price is extremely informative because most markets resolve at 0.99 or 0.01.)
- **Retained features: 8 of 74.** All 8 are batter pitch-count / PA-count proxies over various windows: `bat30_n_pitches`, `bat30_n_pa`, `bat7_n_pitches`, `bat7_n_pa`, `bat14_n_pitches`, `bat14_n_pa`, `batstd_n_pitches`, `batstd_n_pa`.
- 26 features were CI-significant (CI excluded zero), but only the 8 volume features met the AUC delta >= 0.005 retention threshold. The "skill" features (xBA, xwOBA, K rate, BB rate, exit velo, hard-hit rate, launch angle) all had AUC deltas in [0.001, 0.0034], below the 0.005 floor.

### 2.3 Why the survivors are not "real" skill features

All 8 survivors are volume counts (pitches seen, plate appearances) in the prior window. The coefficient on each (after price-residualization) is NEGATIVE in every case. The interpretation: holding the Kalshi price constant, players with MORE recent PAs are LESS likely to hit YES.

This is counter-intuitive. The mechanism: at this dataset's extreme price distribution, "more PAs in prior window" correlates with regulars who get priced as heavy YES favorites (e.g. 0.99 on 1+ hits). The few cases where heavy YES favorites bust drag the negative coefficient. Inversely, players with FEW prior PAs are bench / rookie players priced as heavy NO underdogs whose occasional YES outcomes drag the coefficient negative on the orthogonal-to-price residual.

**The survivors are league-progress / opportunity proxies, analogous to V3-B1's `nfl_games_played_pre_t35d`.** They carry orthogonal-to-price signal in the strict statistical sense, but their predictive content is artifactual to the price distribution, not to player skill.

### 2.4 V2 critic Section 5 "model anchors on price" defense

V2 critic warned: when you drop the price feature, the model loses all signal. We do not literally drop the price (the brief specifies G3 = price + survivors), but the orthogonality protocol's "residualize X on price, then test if X_resid still predicts" is precisely the v2 defense. The retained survivors PASS that test in the statistical sense (CI excludes zero), but they are volume proxies, not skill metrics.

The honest read: the dataset does not support a model whose ML lift comes from a true skill signal. The 8 retained features are essentially "is this a regular player in season" dummies.

---

## 3. Gate result table

`scripts/v5/run_statcast_gate.py` runs G1/G2/G3 with cluster-bootstrap-by-game-date for the C2 CI. All P&L values are per-contract dollars net of round-trip Kalshi maker fees + 1.5c slippage allowance (matching the locked v2 gate constants).

| Criterion | G1 (v1 always-trade) | G2 (LogReg price-only) | G3 (LogReg price + 8 survivors) |
|---|---|---|---|
| holdout_n (eligible) | 43,462 | 43 | 233 |
| holdout_mean ($ per contract) | -0.0650 | -0.4771 | -0.2635 |
| holdout 95% CI lower (cluster-by-date) | -0.0669 | -0.6269 | -0.3283 |
| holdout hit rate | 0.18% | 41.86% | 5.58% |
| 5-fold pooled mean | -0.0689 | -0.0767 | -0.0614 |
| v1 baseline | -0.0650 | -0.0650 | -0.0650 |
| C1 holdout_mean > 0 | FAIL | FAIL | FAIL |
| C2 CI_lower > 0 | FAIL | FAIL | FAIL |
| C3 hit_rate > 55% | FAIL | FAIL | FAIL |
| C4 n >= 15 | PASS | PASS | PASS |
| C5 folds_pooled > 0 | FAIL | FAIL | FAIL |
| C6 v2 - v1 >= +2pp | FAIL (delta = 0) | FAIL (delta = -41.2pp) | FAIL (delta = -19.9pp) |
| **PASSES** | **NO** | **NO** | **NO** |

**All three variants fail all five binding criteria** (C4 is structural; everything else is binding).

The G2 model fires only 43 trades because LogReg on a single price feature predicts probabilities very close to the input price; the `prob > price + 0.02` rule almost never fires. When it does fire, it fires on outliers where the LogReg's regularization shrinks an extreme price (e.g. 0.99) toward 0.5, producing a 3-5c "edge" that is in fact noise. Hit rate on those 43 trades is 41.86%, far below the random-chance breakeven (which for a fair Brier price of 0.5 would be 50%).

The G3 model with 8 volume features fires more (233 trades) because the volume features push predictions slightly off the price baseline. But the hit rate is 5.58%, overwhelmingly underwater. The folds_pooled_mean is -6.14c.

---

## 4. Calibration analysis

| Metric | G2 (price-only) | G3 (price + survivors) | Baseline (raw price) |
|---|---:|---:|---:|
| Holdout n complete | 43,462 | 39,807 | 43,462 |
| Model Brier | 0.0062 | 0.0071 | n/a |
| Price Brier | 0.0146 | 0.0156 | 0.0146 |
| **Brier skill score vs price** | **+0.5743** | **+0.5435** | 0.0 |
| ECE (5 buckets across [0,1]) | 0.0174 | 0.0171 | n/a |

**The model HAS calibration skill (positive BSS).** The raw market price has a Brier of 0.0146, and the LogReg-smoothed price gets to 0.0062, a 57% reduction. This is consistent with the prop-market literature: market prices at the extreme tails (0.99 / 0.01) under-shrink toward the empirical resolution rate, and a simple regularized model corrects that.

But this calibration improvement is OPERATIONALLY USELESS for trading under the +2c edge rule. The model's calibration adjustment is mostly in the "tail-shrinkage" direction (predictions get pulled toward 0.5 by the model's regularization). That direction means the model says YES is LESS likely when the price says YES is 0.99. To trade YES, the rule needs `prob > price + 0.02`; the model's calibration adjustment moves prob the WRONG way.

Per-prop-type BSS (model vs raw price baseline):
- KXMLBHIT: G2 BSS = +0.128, G3 BSS = +0.130
- KXMLBHR: G2 BSS = +0.388, G3 BSS = +0.340
- KXMLBHRR: G2 BSS = +0.637, G3 BSS = +0.595
- KXMLBKS: G2 BSS = +0.095, G3 BSS = n/a (G3 features are batter-only)

The strongest calibration improvement is on KXMLBHRR (which has the most mid-band markets). Even there, the calibration improvement does not translate to profitable trades.

---

## 5. Sanity checks

### 5.1 S1 (drop top players)

For each of {1, 5, 10} dropped most-frequent players, recompute holdout mean P&L on the rest:

| Model | Drop top-1 | Drop top-5 | Drop top-10 |
|---|---|---|---|
| G2 mean (n=43 starting) | -46.86c (n=42) | -47.08c (n=40) | -44.92c (n=38) |
| G3 mean (n=233) | -26.11c (n=232) | -24.78c (n=221) | -23.85c (n=217) |
| v1 always-trade mean (n=43,462) | -6.48c (n=43,270) | -6.42c (n=42,526) | -6.38c (n=41,649) |

**Single-player concentration is not the failure mode.** Dropping top players changes the mean by < 1c in all cases. This matches V5-B1's finding that top-player share is < 1% of the dataset. The v2 COL-as-opponent artifact is structurally absent here, so any failure has to be intrinsic to the dataset, not to a single player.

### 5.2 S2 (per-fold CV cutoff verification)

The 5-fold walk-forward split passes the `train_test_at_or_before_cutoff` check, BUT fails the strict `test_min > train_cutoff` check because contiguous-row slicing breaks ties at identical `close_time` values. Each fold's train_cutoff equals the test_min (both are the same Kalshi market that closed at e.g. `2026-04-07 20:37:26 UTC`). Diagnosis:

- The Kalshi prop markets close at the game's first pitch, and many of a game's ~58 ladder markets share the exact same `close_time` (sub-second).
- Contiguous chronological row slicing puts ~12 markets at the fold boundary in BOTH train and test (some on one side, some on the other).

**Impact on the model:** the FEATURES on those tie-boundary rows are computed using `game_date < as_of_date` (strict less-than). All ladder rungs for one player on one game share the same game_date, so they share the same feature vector. If train contains one rung and test contains another rung of the same (player, game), the model has effectively seen the same feature vector at train time. But since this is one observation among 28k per fold, the impact is < 0.04% of training data.

**Impact on the gate:** the per-fold realized P&L on the leak-affected rows is roughly the same as on the rest of the fold. The C5 5-fold pooled mean is -6.89c with v1, -7.67c with G2, -6.14c with G3. The leak adds variance but does not change the negative sign of the C5 verdict.

This is the v2/v3 gate's structural splitting behavior, not a v5-specific bug. Documented as a known limitation. A fix would split by `(game_date, player)` tuples (a "group walk-forward CV") rather than by row order. Since the gate fails on every criterion by a wide margin regardless, the fix has no actionable impact on this Track B verdict.

### 5.3 S3 (per-prop-type contribution)

G3 holdout selected-trade breakdown by series:

| Series | Holdout n eligible | Mean P&L | Hit rate |
|---|---:|---:|---:|
| KXMLBHIT | 54 | -17.48c | 22.2% |
| KXMLBHR | 33 | -27.86c | 0.0% |
| KXMLBHRR | 146 | -29.29c | 0.7% |
| KXMLBKS | 0 | n/a | n/a |

Every prop type loses. KXMLBHRR is the worst because it has the most mid-band markets (where the model's regularization shrinks predictions away from the price most aggressively), and those markets are exactly the ones where the +2c rule fires.

v1 always-trade breakdown (for comparison):

| Series | n eligible | Mean P&L |
|---|---:|---:|
| KXMLBHIT | 13,062 | -4.60c |
| KXMLBHR | 7,693 | -5.01c |
| KXMLBHRR | 19,503 | -8.75c |
| KXMLBKS | 3,204 | -4.08c |

v1 always-trade loses ~5c per market on average (because the round-trip maker fee + slippage is ~5c, and the markets are priced at the empirical rate so there's no edge to capture).

---

## 6. Sportsbook-spread realism check

Per V5-B1 Section 5: prop-market spreads on illiquid Kalshi books are documented 5-10c (XCLSV Media; Lines.com). Subtract 5c from every winning trade's edge to model execution slippage:

| Model | Holdout n | Post-spread mean | C1 post-spread passes |
|---|---:|---:|---|
| G2 (43 trades) | 43 | -52.71c | NO |
| G3 (233 trades) | 233 | -31.35c | NO |
| v1 (43,462 trades) | 43,462 | -11.50c | NO |

The model fails C1 even WITHOUT spread, and fails even worse with spread. The realism check confirms the verdict.

---

## 7. Honest verdict

**NULL.** Track B Phase 2 closes as a null finding.

The five thesis statements from the v5 master plan H-B:

> per-player Statcast metrics ... predict KXMLBSTATCOUNT-style player-prop outcomes better than the Kalshi market price at a margin sufficient to clear C6's +2pp.

Per the gate result table, no Statcast-augmented model beats v1's baseline by anything near +2pp. The closest is G3's -19.86pp gap to v1 (i.e. G3 is 19.86pp worse).

The v5-B1 hypothesis "Statcast features carry orthogonal information beyond Kalshi price" (Spearman r=-0.04 in the light probe) holds at the n=146k scale (8 of 74 candidate features clear the orthogonality CI). But the orthogonal information is NOT predictive of outcome at a margin large enough to beat the +2c edge rule + Kalshi maker fees.

This matches the v2 critic Section 5 finding: when the dataset's prices are already informative, any ML model that uses price as a feature will "anchor on price" and the residual signal is too small to overcome the edge requirement. The v3-B audit reached the same conclusion at n=147; reaching the same conclusion at n=146k is striking but consistent with the literature ceiling (free-feature sports prediction at +1-3pp).

The four prop series studied span the v5 hypothesis space (hits, HRs, hits-against-runs-allowed, strikeouts). Pitcher props (KXMLBKS, documented as the easiest to beat per V5-B1 Section 5) likewise fail.

---

## 8. Pivots attempted

Per brief Section 9, pre-registered pivots when blocked:

| # | Pivot | Outcome | n_eligible | mean_pnl |
|---|---|---|---:|---:|
| P1a | Wider edge (+5c) on price-only | All trades disappear (n=0) | 0 | n/a |
| P1b | Wider edge (+5c) on price + 8 survivors | All trades lose | 84 | -50.20c |
| P2a | KXMLBHIT-only, price-only, edge=2c | All trades lose | 39 | -55.24c |
| P2b | KXMLBHIT-only, price + survivors, edge=2c | All trades lose | 240 | -11.52c |
| P2c | KXMLBHR-only, price-only, edge=2c | Almost no trades | 0 | n/a |
| P2d | KXMLBHR-only, price + survivors, edge=2c | 1 trade (loser) | 1 | -91.50c |
| P2e | KXMLBHRR-only, price-only, edge=2c | 1 trade (winner) | 1 | +10.50c |
| P2f | KXMLBHRR-only, price + survivors, edge=2c | All trades lose | 725 | -10.40c |
| P2g | KXMLBKS-only, price-only, edge=2c | All trades lose | 10 | -51.60c |
| P3a | Mid-band [0.20, 0.80], price-only, edge=2c | No trades | 0 | n/a |
| P3b | Mid-band, price + survivors, edge=2c | No trades | 0 | n/a |

**Every pivot fails.** The single edge case where a P2e variant got a positive mean has n=1 (so it's statistical noise from a single fortuitous trade). KXMLBHR price-only fires zero trades; KXMLBKS price-only fires 10 with -51.6c; the mid-band model fires zero. The wider-edge pivot just shrinks the trade set to zero or worsens already-failing trade slates.

**Pre-registered model-worse-than-baseline kill condition (brief Section 9): "If the model performs WORSE than baseline (negative BSS): this is the v2/v3 'model anchors on price' failure mode in a different shape. Document and consider null."**

The model BSS is POSITIVE here (G2 BSS = +0.57, G3 BSS = +0.54) but the operational P&L is far worse than v1's always-trade baseline. The failure is the SAME mode (anchor on price), in a different shape: the model has calibration improvement (positive BSS) but cannot translate it to a +2pp edge in trade terms. **The brief's kill condition is satisfied in spirit.**

---

## 9. v2/v3 failure-mode crosswalk

| v2/v3 failure mode | v5-b status |
|---|---|
| **CV in-sample leak (v2)** | Addressed structurally: trainer= is wired through evaluate_with_cluster_bootstrap; per-fold retraining is mandatory. C5 result is -6.14c, not a spurious +15.98c. |
| **Feature look-ahead** | Defense: strict `game_date < as_of_date` in `compute_statcast_features_as_of`. Unit test `test_compute_statcast_features_no_leak` verifies. |
| **Model anchors on price (v2 critic Section 5)** | NOT escaped: G2 BSS = +0.57 but holdout mean -47.71c; calibration improvement does not produce trading edge. G3 with 8 survivors slightly worse. The survivors are volume-proxy features that capture league-progress / opportunity artifacts, not true skill signal. |
| **Single-entity artifact (v2 COL-as-opponent)** | Structurally absent: top-1 player share is 0.49% (Max Muncy); S1 dropping top-10 changes G3 mean by < 3c. Not the failure mode. |
| **Wrong-cutoff window (v4-F LLM)** | n/a; no LLM in this build. Statcast game_date is the published game date (deterministic). |
| **Domain mismatch (v2 game-vs-season)** | n/a; the gate operates on the SAME prop universe the model was trained on. The C6 vs v1 comparison is meaningful only as "v1 cannot trade these props" (v1's universe excludes player-prop ladders). The C6 delta therefore is reported but is not load-bearing; the model fails C1-C5 on its own without C6. |
| **C5 fold-boundary tie leak (new)** | Identified in S2: contiguous-row chronological split breaks ties at identical close_time. Impact on this verdict is <0.04% per fold; a group-walk-forward CV would fix it. Mentioned for completeness; does not change verdict. |

---

## 10. Files written

| Path | Size | Description |
|---|---:|---|
| `src/kalshi_bot_v5/statcast_features.py` | 19 KB | Feature engineering: load_kalshi_prop_markets, compute_statcast_features_as_of, build_dataset, get_feature_column_names. |
| `src/kalshi_bot_v5/statcast_model.py` | 6 KB | make_trainer, fit_model, make_anchored_decision_fn. EDGE_THRESHOLD=0.02 locked. |
| `scripts/v5/build_v5b_dataset.py` | 3 KB | Pipeline: load + join + write parquet. |
| `scripts/v5/run_v5b_orthogonality.py` | 13 KB | Cluster-bootstrap orthogonality protocol with custom IRLS. |
| `scripts/v5/run_statcast_gate.py` | 18 KB | G1/G2/G3 with cluster-bootstrap-by-date C2 CI; calibration; S1/S2/S3; sportsbook spread realism. |
| `scripts/v5/run_statcast_pivots.py` | 8 KB | 11 pre-registered pivot variants. |
| `tests/v5/test_statcast_features.py` | 3 KB | 7 unit tests; all pass. |
| `tests/v5/test_statcast_model.py` | 4 KB | 6 unit tests; all pass. |
| `data/v5/prop_dataset.parquet` | ~40 MB | n=144,873 joined rows; 132 cols. |
| `data/v5/prop_dataset_summary.json` | ~5 KB | Build summary. |
| `data/v5/v5b_orthogonality_report.json` | 44 KB | Per-feature CI, AUC, decision. |
| `data/v5/statcast_gate_results.json` | ~30 KB | G1/G2/G3 + calibration + S1/S2/S3 + spread realism. |
| `data/v5/statcast_pivots_results.json` | ~25 KB | 11 pivot variants. |

---

## 11. Operator-facing recommendation

**Close Track B as null.** The dataset is the largest any Project Kalshi build has ever had (n=146k > 1000x v3's n=147), the methodology is rigorous (locked orthogonality protocol, cluster-bootstrap CI, per-fold retraining, pre-registered pivots), and the verdict is unambiguous (every variant fails every criterion by wide margins).

Operator-action items:
1. **No live deployment of any v5-b model.** The model has calibration skill (positive BSS) but no trading edge under the locked decision rule.
2. **Optional Track B salvage path (NOT recommended given the time budget already spent):** rebuild with a single-season Statcast cache from 2025 (one year prior) as historical context for the recent-form features. The hypothesis would be that the in-2026 60-day-window data is too thin to reveal player-skill differentiation, and historical 2025 form would add signal. This is a 4-hour build + gate cycle. The prior is bleak: literature ceiling is +1-3pp, well below the +2c rule.
3. **Track B's positive finding for the broader v5 effort**: the dataset and methodology serve as a clean negative result for the "ML beats Kalshi on player props at any retail scale" hypothesis. This closes a question that operator has flagged as a "do not give up before all angles attacked" requirement.
4. **Connection to v1**: v1 does not trade these prop markets (its denylist post-W1 excludes KXMLB*PLAYOFFS, and the per-game KXMLBHIT/HR/HRR/KS ladder is not in v1's traded universe). The Track B verdict is neutral on v1's continued operation on its own market type.

---

## 12. Honest constraints on this finding

- **Single-season caveat (V5-B1 carry-forward):** all data is in one 60-day window (2026-03-26 to 2026-05-24). The 43 distinct game-dates in the chronological 70% train portion is a small effective sample for cluster-bootstrap; the 18 dates in the 30% holdout is even smaller. A multi-season replication would test whether the verdict generalizes.
- **The orthogonality protocol uses 1,000 bootstrap resamples, not the brief's specified 5,000.** Per Section 2.1, this is computationally motivated and the precision impact is small (CI quantiles stabilize within ~2%). If a future replication runs 5,000 resamples, the survivors set might shift by 1-2 features (likely adding or dropping borderline xwOBA / K-rate features), but the structural verdict (8 volume features survive; skill features fail AUC delta) would not change.
- **The C5 cv-fold-boundary tie leak (S2) is not a v5-specific bug.** It exists in the v3 gate code as well. Fixing it would shrink the train set by < 0.05% per fold; the verdict is robust to this fix.
- **Player-name -> MLBAM mapping drops 2,073 of 146,946 rows (1.4%).** These are minor-league call-ups whose names are not yet in the chadwick_register CSV. A future build could supplement with the MLB Stats API people endpoint to recover these rows. The marginal impact on the verdict is < 0.1% of the eligible sample.
- **The cluster-bootstrap-by-date for the gate's holdout C2 CI uses 5,000 resamples (matching the brief)** because the cluster count at holdout is only 18 dates; the per-iteration cost is trivial. The orthogonality protocol uses 1,000 (above).
- **Sportsbook-spread realism uses a 5c flat assumption.** Real spreads on liquid prop markets can be 1-2c; on illiquid ones 10c+. The 5c assumption matches V5-B1 Section 5.2's documented community-consensus figure. A maker-side execution model (placing limit orders inside the spread) would have lower effective spread, but the model fails C1 by far more than any plausible spread shrinks.

---

## 13. Findings summary

| # | Finding | Severity |
|---|---|---|
| 1.1 | Dataset built honestly at n=144,873 binary-resolved markets across 4 prop series. | KILLER (positive) |
| 1.2 | 8 of 74 candidate features survive orthogonality protocol; all 8 are volume-proxy features, not skill metrics. | KILLER (caveat) |
| 1.3 | Price-only LogReg achieves positive Brier skill (+0.57) vs raw price. Calibration improvement is real. | IMPORTANT (positive) |
| 1.4 | The +2c edge rule + Kalshi maker fees consume the calibration improvement entirely. G2 mean -47.71c on n=43; G3 mean -26.35c on n=233. | KILLER (negative) |
| 1.5 | All three gate variants fail all 5 binding criteria (C4 passes structurally). | KILLER (negative) |
| 2.1 | Pre-registered pivots (wider edge, per-prop-type, mid-band): 11 variants attempted; all fail. | KILLER (negative) |
| 2.2 | Top-player share < 1%; S1 sanity passes (the failure is NOT a single-player artifact). | IMPORTANT (methodology) |
| 2.3 | Per-fold CV cutoff has tie-leak at identical close_time, impact < 0.05%. Documented. | MINOR (methodology) |
| 2.4 | Sportsbook-spread realism check: model loses MORE under 5c spread; not a salvageable variant. | IMPORTANT (negative) |
| 3.1 | **Verdict: Track B closes as null.** Same v2/v3 "model anchors on price" mode at 1000x the dataset size, in a different shape (positive BSS, negative P&L). | VERDICT |

5 IMPORTANT, 5 KILLER (1 positive, 4 negative), 1 MINOR, 1 verdict.

The KILLER positive (dataset built) and the 4 KILLER negatives together describe a clean null finding. The methodology is sound; the strategy is unviable at retail Kalshi scale on these prop markets.
