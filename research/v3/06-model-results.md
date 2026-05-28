# V3 Model Results (Phase 2, Agent V3-B2)

**Date:** 2026-05-24
**Agent:** V3-B2
**Inputs:** `data/v3/joined_v3_dataset.parquet` (147 rows from V3-B1), the locked 6-criteria gate at `src/kalshi_bot_v2/gate.py`.
**Outputs:** `data/v3/gate_results.json`, `src/kalshi_bot_v3/__init__.py`, `src/kalshi_bot_v3/model.py`, `scripts/v3/run_v3_gate.py`, this doc.
**Run time:** ~1s wall-clock for all three gate evaluations across full / NFL-only / MLB-only slices.

## Verdict (TL;DR)

**GATE FAILS. NULL FINDING (with Phase 3 critic amendments applied).** All three trade rules (G1 v1-style flat-prior baseline, G2 price-only LogReg with prob >= 0.70 threshold, G3 price + league-dummy LogReg) fail the locked gate on the v3 dataset.

The original write-up of this doc claimed "v1 confirmed" and treated C6=0pp as a measured null. The Phase 3 critic flagged BOTH framings as overreach. The amended verdict reads:

1. **C6 = 0pp is a structural identity, not a measured null.** G2 and G3 trade the IDENTICAL 45 holdout rows v1 trades because the LogReg's predicted prob is `>= 0.70` on every holdout row (G2 min 0.8953, G3 min 0.7039). v3 was unable to express a non-trivial decision rule given the train set's 96% YES single-class composition. C6's "v3 minus v1 = 0pp" is mechanical equality, not a measurement.

2. **v1's measured edge has never been demonstrated on KXNFLWINS markets.** v1's `+12.47pp` claim from `research/time-scale-analysis.md` was computed on `data/processed/sports_dataset.parquet` (n=39 eligible), which contains zero KXNFLWINS markets. v3's holdout is 22/45 = 49% KXNFLWINS, and the NFL slice realizes -40.19pp. v1's claimed edge is silent on the distribution that dominates the v3 holdout failure. v3 reveals untested v1 distributional exposure; it does NOT confirm v1.

3. **S3 domain match materially fails.** v1's live attempted-orders cover 19 distinct series-prefixes (KXBOXING, KXUFCFIGHT, KXWCGAME, KXMLBSTATCOUNT, etc.); v3 holdout covers 5; overlap is 2/19 = 10.5%. The v3 probe (`scripts/v3/probe_inventory.py:93-156`) enumerated 5 sports-major series families and skipped the rest of v1's actual trading universe.

The dataset's chronological 70/30 split puts most NFL favorite-NO outcomes in the holdout (NFL holdout YES rate 46%, vs train YES rate 100%). Neither a heuristic nor a thin-feature ML rule can recover positive expected value on a holdout where favorites under-perform that severely.

**Honest verdict (post-critic-amendment):** v3 cannot demonstrate ML lift on this holdout; the holdout simultaneously reveals an untested v1 distributional exposure on KXNFLWINS late-season markets. v1 continues running on its current configuration; an honest v1 rebuild on a complete sports universe is a separate work item flagged for the operator.

Per the operator brief: "A 'fail' verdict, documented cleanly with the specific failure modes, is exactly what v3 needs." This document plus the Phase 3 critic at `07-critic.md` together comprise that delivery.

## 1. What was run

Three trade-decision rules, all evaluated through the locked gate in `src/kalshi_bot_v2/gate.py` (HOLDOUT_FRAC=0.30, N_FOLDS=5, BOOTSTRAP_N_RESAMPLES=5000, seed=42, slippage 1.5pp, round-trip maker fees).

- **G1: v1-style flat-prior baseline.** Calls `v1_decision_fn` from `gate.py` directly; trades every eligible row. The same v1 rule that runs live. This is the C6 reference.
- **G2: price-only LogReg.** `LogisticRegression(C=1.0, class_weight=None, max_iter=1000, random_state=42)` on `{favorite_price}`. Decision rule: `should_trade = predicted_prob >= 0.70` (matches v1's eligibility threshold on the underlying price).
- **G3: price + league-dummy LogReg.** Same LogReg on `{favorite_price, nfl_games_played_pre_t35d}`. The second feature is the V3-B1 orthogonality survivor, which is effectively a "league=NFL and season-progressed" indicator (zero for all MLB/NBA/NCAA/NHL rows by construction). Same threshold rule.

C5 (5-fold pooled mean) is wired with `trainer=make_trainer(features)` so each fold's LogReg is fit on that fold's chronological prefix only. The v2 Round-5 leak is structurally precluded by this design and verified by S2.

## 2. Gate result table (FULL n=147)

| | G1 v1-baseline | G2 price-only LogReg | G3 price + league-dummy |
|---|---:|---:|---:|
| holdout_eligible_n | 45 | 45 | 45 |
| holdout_mean | **-18.89pp** | **-18.89pp** | **-18.89pp** |
| holdout_median | +4.64pp | +4.64pp | +4.64pp |
| holdout_sd | 44.71pp | 44.71pp | 44.71pp |
| holdout_hit_rate | 68.89% | 68.89% | 68.89% |
| holdout_ci_lower (95%) | -32.54pp | -32.54pp | -32.54pp |
| holdout_ci_upper (95%) | -4.55pp | -4.55pp | -4.55pp |
| folds_eligible_total | 116 | 114 | 115 |
| folds_pooled_mean | -1.03pp | -1.49pp | -1.26pp |
| folds_pooled_ci_lower | -7.27pp | -7.66pp | -7.46pp |
| v1_holdout_mean | -18.89pp | -18.89pp | -18.89pp |
| v2_minus_v1 | 0.0pp | 0.0pp | 0.0pp |

### 2.1 Criteria pass/fail (FULL n=147)

| Criterion | Threshold | G1 | G2 | G3 |
|---|---|---|---|---|
| C1: holdout_mean > 0 | > 0 | FAIL (-18.89pp) | FAIL (-18.89pp) | FAIL (-18.89pp) |
| C2: holdout_ci_lower > 0 | > 0 | FAIL (-32.54pp) | FAIL (-32.54pp) | FAIL (-32.54pp) |
| C3: hit_rate > 55% | > 55% | PASS (68.89%) | PASS (68.89%) | PASS (68.89%) |
| C4: holdout_n >= 15 | >= 15 | PASS (45) | PASS (45) | PASS (45) |
| C5: folds_pooled_mean > 0 | > 0 | FAIL (-1.03pp) | FAIL (-1.49pp) | FAIL (-1.26pp) |
| C6: v3 beats v1 by >= 2pp | >= +2pp | FAIL (0.0pp) | FAIL (0.0pp) [1] | FAIL (0.0pp) [1] |
| **Overall** | | **FAIL** | **FAIL** | **FAIL** |

[1] C6 = 0.0pp by construction; G2 and G3 trade the same 45 rows as v1 because LogReg predicted probs are `>= 0.70` on every holdout row (G2 min 0.8953, G3 min 0.7039). C6 cannot distinguish v3 from v1 on this holdout. See Phase 3 critic `07-critic.md` Test 6 for the verification re-run.

### 2.2 Why G2 and G3 produce identical holdout numbers to G1

The chronological train (n=102) has YES rate 0.9608 (4 NO outcomes total: 3 MLB, 1 NCAA, zero NFL/NBA/NHL). With one feature (price) and class_weight=None, the LogReg solution sits at the intercept-dominated regime where every plausible holdout price maps to predicted prob > 0.70:

- G2 (price-only) holdout predicted probs: min 0.8953, max 0.9828, mean 0.9561. All 45 holdout rows clear the 0.70 trade threshold.
- G3 (price + league-dummy) holdout predicted probs: min 0.7039, max 0.9996, mean 0.9533. All 45 holdout rows clear the threshold.

When every eligible holdout row trades, G2 and G3 execute the same trade set as v1, producing identical realized P&L. C6 = v3_mean - v1_mean = 0.0 by construction; this is NOT a tuning failure, it is the dataset shape telling us that a price-only or price-plus-league-dummy LogReg cannot find a meaningful "abstain" condition with only 4 NO outcomes in training.

The 5-fold pooled mean numbers (-1.03 / -1.49 / -1.26 pp) DO differ slightly because each fold's retrained model produces fold-specific predictions; in earlier folds the model is occasionally selective (e.g. drops 1-2 trades), but the differences are within bootstrap noise.

### 2.3 The structural problem this exposes

The chronological 70/30 split puts almost all NFL favorite-NO outcomes in the holdout. NFL training rows are 78/78 YES; NFL holdout rows are 12/26 YES (46.15%). The remaining holdout breakdown:

| Holdout league | n | YES rate | mean P&L (per v1) |
|---|---:|---:|---:|
| NFL | 26 | 46.2% | -40.19pp |
| NBA | 17 | 100% | +10.53pp |
| NHL | 2 | 100% | +8.01pp |
| **Total** | **45** | **68.9%** | **-18.89pp** |

The -18.89pp holdout mean is driven entirely by the NFL slice. NBA and NHL holdouts both hit 100% YES, but the NFL collapse swamps them. No price-or-league-dummy ML rule has the discriminative information to flag the 14 NFL NOs in the holdout because the train set has zero NFL NOs to learn from.

## 3. Calibration analysis

Brier (lower is better), Brier skill score vs raw favorite_price baseline (positive means model beats raw price), and ECE at 5 price buckets across [0.70, 0.95].

| Metric | G2 (price-only) | G3 (price + league-dummy) | Raw favorite_price baseline |
|---|---:|---:|---:|
| Holdout Brier | 0.2813 | 0.3180 | 0.2236 |
| Brier skill score vs raw price | -0.258 | -0.422 | n/a (reference) |
| ECE (5 buckets, weighted) | 0.157 | 0.041 | n/a |

**Both G2 and G3 are LESS calibrated than raw favorite_price** (negative BSS, larger Brier than 0.2236). The "raw favorite_price" baseline literally uses the market price as the probability prediction; it beats both ML rules on holdout calibration. This is consistent with the V3-D literature ceiling ("free-public-feature sports prediction tops out at 65-67% game-level accuracy, +1-3pp gross edge") and confirms the V3-B1 foreshadow.

### 3.1 ECE bucket breakdown

G2 (price-only) predictions cluster in [0.90, 0.95]:

| Bucket | n | mean_pred | mean_actual | abs_gap | weight |
|---|---:|---:|---:|---:|---:|
| [0.70, 0.75) | 0 | n/a | n/a | n/a | 0.000 |
| [0.75, 0.80) | 0 | n/a | n/a | n/a | 0.000 |
| [0.80, 0.85) | 0 | n/a | n/a | n/a | 0.000 |
| [0.85, 0.90) | 1 | 0.895 | 1.000 | 0.105 | 0.022 |
| [0.90, 0.95] | 14 | 0.927 | 0.429 | **0.499** | 0.311 |

Note: 30 of G2's 45 holdout predictions lie above 0.95 and fall outside the standard ECE bin range. The model is severely over-confident on the holdout: it predicts 93% YES on rows that actually go 43% YES. ECE of 0.157 understates this because the buckets that catch the most-confident predictions sit above 0.95.

G3 (price + league-dummy) spreads predictions more usefully:

| Bucket | n | mean_pred | mean_actual | abs_gap | weight |
|---|---:|---:|---:|---:|---:|
| [0.70, 0.75) | 3 | 0.716 | 1.000 | 0.284 | 0.067 |
| [0.75, 0.80) | 1 | 0.771 | 1.000 | 0.229 | 0.022 |
| [0.80, 0.85) | 0 | n/a | n/a | n/a | 0.000 |
| [0.85, 0.90) | 3 | 0.887 | 1.000 | 0.113 | 0.067 |
| [0.90, 0.95] | 7 | 0.942 | 1.000 | 0.058 | 0.156 |

G3 also has ~31 predictions above 0.95 (the NFL rows, which the league dummy pushes to near-certainty). G3's apparent ECE of 0.041 looks better than G2's 0.157, but its Brier is WORSE (0.318 vs 0.281). The reason: G3 makes the cluster of "near-1.0 for NFL" predictions much more extreme; when the holdout NFL rows go 46% YES, the squared error on those high-confidence wrong predictions is enormous. G3 is more spread out across the price band (better ECE in-band) but more confidently wrong on the league it predicts most confidently (worse Brier).

### 3.2 G3 per-league predicted vs actual

| Holdout league | n | G3 mean_pred | G3 actual YES rate |
|---|---:|---:|---:|
| NFL | 26 | 0.998 | 0.462 |
| NBA | 17 | 0.888 | 1.000 |
| NHL | 2 | 0.923 | 1.000 |

G3 has learned the opposite of what would help: it is most confident on the league that under-performs in holdout (NFL) and least confident on the league that over-performs (NBA). The league dummy carries a positive coefficient because the train NFL slice is 100% YES, but the holdout NFL slice flips. The feature is wrong-direction OOS.

## 4. Sanity checks

### 4.1 S1: drop-top-team artifact check

The holdout's most-frequent team is **TB** (Tampa Bay Buccaneers, 3 NFL win-totals + 1 NFL playoff = 4 rows; the runner counts the `team` field). Dropping all TB rows from the holdout:

| Rule | TB rows in holdout | remaining n | remaining mean P&L | passes (mean > 0)? |
|---|---:|---:|---:|---|
| G1 v1-baseline | 4 | 41 | -14.50pp | FAIL |
| G2 price-only | 4 | 41 | -14.50pp | FAIL |
| G3 price + league-dummy | 4 | 41 | -14.50pp | FAIL |

All three rules fail S1 because the holdout is dominated by NFL favorite-NO outcomes that no single team carries. This is the OPPOSITE of v2's COL artifact (where COL was 75% of the holdout). Here the bad performance is broad-based; removing the top team only moves the mean from -18.9pp to -14.5pp, still deeply negative.

**Interpretation:** S1 says "the model's loss is not a single-team artifact." It is a distribution-shift artifact, distributed across NFL teams that all under-performed their over-thresholds in the late-season holdout window. This is a different failure mode than v2's COL artifact.

### 4.2 S2: CV out-of-sample verification

Audit of the 5-fold walk-forward splitter (`gate._kfold_splits`). For each fold, verify the fold's test slice is strictly chronologically after the fold's train cutoff:

| Fold | train_n | test_n | train_cutoff | test_min | clean? |
|---|---:|---:|---|---|---|
| 1 | 29 | 29 | 2025-10-27 14:46:51 UTC | 2025-11-03 08:01:39 UTC | PASS |
| 2 | 58 | 29 | 2025-11-24 08:01:48 UTC | 2025-11-25 08:01:56 UTC | PASS |
| 3 | 87 | 29 | 2025-12-09 08:02:13 UTC | 2025-12-15 08:01:45 UTC | PASS |
| 4 | 116 | 29 | 2025-12-30 08:02:49 UTC | 2025-12-30 08:02:56 UTC | PASS |

All four folds: test slice starts strictly after train cutoff. S2 PASSES. The v2 Round-5 leak (where the same pre-trained decision_fn was reused across folds, evaluating it on rows that were inside its original training set) is structurally precluded by the gate's `trainer=` mechanism plus the chronological slice geometry.

### 4.3 S3: domain-match distribution

Holdout (n=45) `(series, lifetime_bucket, price_bucket)` distribution. Lifetime buckets are 30d wide closed-open in [30, 180); the [150, 180] bucket is closed-closed to include 180-day markets. Price buckets are 5c wide closed-open across [0.70, 0.95]; the [0.90, 0.95] bucket is closed-closed.

Series-level counts in the holdout:

| Series | n | notes |
|---|---:|---|
| KXNBAWINS | 17 | NBA team season-win-total markets |
| KXNFLPLAYOFF | 4 | NFL team playoff-qualification markets |
| KXNFLWINS-* | 22 | NFL team season-win-total markets across 15 teams (TB top with 3) |
| KXNHL* | 2 | one NHL division-winner each (KXNHLMETROPOLITAN, KXNHLCENTRAL) |

Cells with n > 0 (representative subset; full list in `data/v3/gate_results.json`):

| Series | lifetime | price | n |
|---|---|---|---:|
| KXNBAWINS | [150, 180] | [0.90, 0.95] | 10 |
| KXNBAWINS | [150, 180] | [0.70, 0.75) | 4 |
| KXNBAWINS | [150, 180] | [0.80, 0.85) | 2 |
| KXNBAWINS | [150, 180] | [0.85, 0.90) | 1 |
| KXNFLPLAYOFF | [150, 180] | [0.80, 0.85) | 2 |
| KXNFLPLAYOFF | [150, 180] | [0.70, 0.75) | 2 |
| KXNFLWINS-TB | [120, 150) | [0.85, 0.90) | 1 |
| KXNFLWINS-TB | [120, 150) | [0.90, 0.95] | 1 |
| KXNFLWINS-TB | [90, 120) | [0.75, 0.80) | 1 |
| KXNFLWINS-KC | [90, 120) | [0.85, 0.90) | 1 |
| KXNFLWINS-KC | [90, 120) | [0.90, 0.95] | 1 |

The holdout concentrates in long-lifetime (>= 90 day) markets in the [0.75, 0.95] price band, consistent with V3-A's eligibility filter (T-35d sampling on 30-180d markets at YES >= 0.70). NBA dominates the [150, 180] lifetime bucket; NFL spans [90, 150] (markets that close in Dec-Apr from a Sept-Dec opening). MLB has zero holdout rows in the FULL split because all MLB markets close before the chronological 70/30 cutoff (2025-12-22).

This distribution is reported for the Phase 3 critic. The critic can compare the v3 holdout's (series, lifetime, price) cells to v1's filled-orders log distribution at `data/live_trades/` to determine whether the v3 holdout overlaps the markets v1 actually trades. V3-B2 does not perform that intersection here.

**Update from Phase 3 critic.** The intersection was performed in `07-critic.md` Test 2 / Important Finding #3. v1's live attempted-orders cover 19 distinct series-prefixes; v3 holdout covers 5; overlap is 2/19 = 10.5%. **S3 materially FAILS.** The v3 probe enumerated 5 sports-major series families (NFL/NBA/NHL/MLB/NCAA) and skipped the 17 other series v1 actually trades (KXBOXING, KXUFCFIGHT, KXWCGAME, KXFOMEN, KXCS2, KXMLBSTATCOUNT, KXSTARTINGQBWEEK1, etc.). See `07-critic.md` Test 2 Results A through F for the full intersection.

## 5. Per-league sub-analysis

The locked gate runs on FULL n=147. The NFL-only and MLB-only slices are diagnostic only.

### 5.1 NFL-only (n=104)

| | G1 v1-baseline | G2 price-only | G3 price + league-dummy |
|---|---:|---:|---:|
| holdout_eligible_n | 32 | 0 | 0 |
| holdout_mean | -30.88pp | n/a | n/a |
| holdout_ci_lower | -47.54pp | n/a | n/a |
| folds_pooled_mean | -2.71pp (4 folds) | n/a | n/a |
| v1_holdout_mean | -30.88pp | -30.88pp | -30.88pp |
| passes | FAIL | FAIL (n=0 < 15) | FAIL (n=0 < 15) |

The NFL-only training portion (n=72) is **single-class** (100% YES, zero NOs). The trainer correctly returns a degenerate fit (cannot fit a 2-class LogReg on single-class y); the runner's anchored decision_fn is `never_trade`. The CV trainer also produces `constant_fn` rules per fold, but the holdout anchored model abstains entirely. G2 and G3 on NFL-only execute zero trades; v1 trades all 32 and loses 30.9pp.

**Diagnostic implication:** an ML rule trained on a 100% YES NFL slice cannot learn to abstain. Either the strategy never trades (passes C1 trivially with mean=NaN, fails C4 trivially with n=0) or it trades everything (matches v1's -30.88pp). Neither option clears C6. The NFL data shape forecloses an ML-improvement story.

### 5.2 MLB-only (n=16)

| | G1 v1-baseline | G2 price-only | G3 price + league-dummy |
|---|---:|---:|---:|
| holdout_eligible_n | 5 | 4 | 4 |
| holdout_mean | +9.19pp | +5.82pp | +5.82pp |
| holdout_ci_lower | +5.30pp | +5.17pp | +5.17pp |
| holdout_hit_rate | 100% | 100% | 100% |
| folds_pooled_mean | (fold_size=3 < 5; no folds run) | (same) | (same) |
| v1_holdout_mean | +9.19pp | +9.19pp | +9.19pp |
| v2_minus_v1 | 0.0pp | -3.37pp | -3.37pp |
| passes | FAIL (C4: 5 < 15) | FAIL (C4: 4 < 15) | FAIL (C4: 4 < 15) |

MLB-only has 16 rows total; the chronological 30% holdout is only 5 rows. C4 (n >= 15) is structurally unreachable. The 5-fold CV does not run either (fold_size = 16//5 = 3 < 5 minimum). The headline diagnostic: v1 makes +9.19pp on 5 MLB markets (3 KXMLBWINS team-win-totals + 2 KXMLBNL division-winners; all settled YES). G2 abstains on 1 of the 5 (where the LogReg dropped below 0.70 due to a low-price MLB row), so G2's slice realizes +5.82pp on 4 trades. G3 produces the same 4 trades.

**Diagnostic implication:** on the tiny MLB-only slice, the heuristic and the ML rules all make money because the holdout MLB favorites all hit. This is the only league subset where the rules are positive-mean, but the n is far too small to clear C4. Notably, G2 and G3 SLIGHTLY UNDERPERFORM v1 on MLB (skipping a favorite that hit), so even here the ML rules add no value.

### 5.3 Synthesis across leagues

| League slice | n total | n holdout | v1 holdout mean | best ML rule mean | C4 satisfied? |
|---|---:|---:|---:|---:|---|
| FULL (NFL+NBA+MLB+NCAA+NHL) | 147 | 45 | -18.89pp | -18.89pp | yes |
| NFL-only | 104 | 32 | -30.88pp | n/a (never-trade) | n/a |
| MLB-only | 16 | 5 | +9.19pp | +5.82pp | NO |

No slice produces both (i) C4 satisfied AND (ii) a positive v1 baseline. The slices where v1 is positive are too small; the slice large enough for C4 is dominated by the late-season NFL collapse.

## 6. Honest interpretation

### 6.1 Verdict

**GATE FAILS, NULL FINDING.** None of G1, G2, G3 pass any of C1, C2, C5, or C6 on the locked FULL n=147 split. C3 (hit rate > 55%) and C4 (n >= 15) pass trivially because the holdout n is 45 and 31 of 45 rows settled YES; these are not the binding constraints. The binding failures are:

1. **C1 fails by 18.89pp.** Holdout mean P&L is deeply negative.
2. **C2 fails by 32.54pp.** Bootstrap 95% CI lower bound is -32.54pp, far below zero.
3. **C5 fails by 1pp+.** 5-fold pooled means range -1.03pp to -1.49pp, with bootstrap CI lower bounds at -7.27pp to -7.66pp.
4. **C6 fails by 2pp.** v3 minus v1 is 0.0pp on G2/G3 because they trade the same rows v1 does.

All four binding criteria fail by margins much larger than the locked thresholds. This is not a marginal fail; the model genuinely cannot beat v1 on this data because v1 itself is unprofitable on this holdout.

### 6.2 Why the gate fails (root cause)

The dataset's chronological 70/30 split has **distribution shift built in by construction**:

- Train (n=102, period 2025-09-17 to 2025-12-22): 96% YES outcomes. Most rows are early-season NFL/NBA/MLB markets where favorites cleared their thresholds.
- Holdout (n=45, period 2025-12-22 to 2026-04-13): 69% YES outcomes overall, but 46% YES on the 26 NFL rows that dominate the slice.

The distribution shift is not a bug; it reflects when NFL season-win-total markets actually resolve. Markets that closed Dec 22 onward are typically NFL teams whose path-to-target became uncertain in late November and Dec, exactly where NFL favorites historically miss. This is the structural data shape V3-B1 flagged in their Section 8.5.

No price-only or price-plus-thin-feature ML rule has the discriminative power to flag those NFL NOs because the train set has zero NFL NOs. The orthogonality protocol in V3-B1 confirmed this by dropping every NFL team-stat feature (single-class y in train made bootstraps fail). The retained `nfl_games_played_pre_t35d` is effectively a league dummy that is wrong-direction on the holdout (it pushes NFL predictions to near-certainty YES, exactly when NFL is going 46% YES).

### 6.3 Specific failure modes per criterion

- **C1 (mean > 0): FAIL by 18.89pp.** Driven by the NFL holdout -40.19pp. NBA +10.53pp and NHL +8.01pp cannot offset.
- **C2 (CI lower > 0): FAIL by 32.54pp.** Wide CI from the bimodal P&L distribution (favorites that hit make ~5-10pp, favorites that miss lose ~80pp).
- **C3 (hit rate > 55%): PASS (68.89%).** Most trades settle YES even on the bad holdout; the bad trades are catastrophic but not numerous.
- **C4 (n >= 15): PASS (45).** Sample is adequate.
- **C5 (folds pooled mean > 0): FAIL by 1pp.** The first two folds are +9.5pp / +10.6pp; folds 3-4 flip to -11.8pp / -12.5pp as the chronological window enters the late-season NFL collapse. Pooled mean is -1.03 to -1.49 pp across rules.
- **C6 (v3 beats v1 by 2pp): FAIL by 2pp.** v3 and v1 trade identical rows on the locked FULL split; v2 minus v1 is identically zero.

### 6.4 What this null finding means (amended after Phase 3 critic)

This result was foreshadowed by V3-B1 (whose Section 4 endorsed "Path B: acknowledge the data shape rejection") and by V3-D's literature ceiling (free-public-feature models add +1-3pp gross edge at best). The Phase 3 critic at `07-critic.md` further sharpened the framing. The honest result is:

1. **External team-stat features at n=147 with leak-free CV cannot improve over v1's heuristic on the available data.** This rejects H4 directionally: free-public-feature ML at this scale does not add edge. **v1's measured edge has NOT been demonstrated on KXNFLWINS markets**, which dominate the v3 holdout failure zone. v1 IS the right strategy for the project's known scale (where it has been running), but its edge magnitude on the specific subgroup KXNFLWINS late-season remains untested. The phrase "v1 confirmed" is overreach.

2. **v1's measured-edge dataset (`data/processed/sports_dataset.parquet`) contains zero KXNFLWINS markets.** v3's probe enumerates 95 v1-eligible KXNFLWINS markets in the same time window. The C6 comparison is computed on a market type v1's measured edge has never been demonstrated on (Phase 3 critic Important Finding #2).

3. **The C6 comparison is mechanical-equality on this holdout** (Phase 3 critic Killer Finding #1). G2/G3 predicted probs are >= 0.70 on every holdout row; both rules trade the same 45 rows v1 does; v3 minus v1 = 0pp by construction. C6 cannot distinguish v3 from v1 on this holdout regardless of feature richness, because the train set's 96% YES rate saturates the LogReg above the trade threshold for every plausible holdout feature vector.

4. **The v3 holdout reveals an untested v1 distributional exposure.** The chronological 70/30 holdout's NFL slice (n=26, 46% YES) is the precise failure zone (-40.19pp v1 baseline). v1 in production scans the full sports universe (`src/kalshi_bot/strategy/market_scanner.py:118-152`), so this exposure is real for the live bot, not a v3 artifact. An honest v1 rebuild on a complete sports universe is a separate work item out of v3 scope.

### 6.5 What would need to change for a future attempt

Per the master plan Section 6 (null-finding criteria):

1. **Multi-season pull.** n=147 is too small to support feature richness. A 3-4 season pull (~400-500 markets) would let CV detect smaller edges and would dilute the NFL late-season chronological-shift bias.
2. **Different time horizon or market type.** Long-horizon season-win markets are extremely path-dependent (a team's late-season form dominates the outcome regardless of early signals). Short-horizon markets (KXMLBGAME, weekly NFL futures) might be more learnable.
3. **Match the holdout to v1's actual trading distribution.** The current chronological 70/30 over-weights NFL late-season; stratifying holdout selection by series and lifetime bucket might produce a more representative test slice. But that risks domain-matching the gate to v1's wins, which would defeat the purpose of an honest OOS test.
4. **Paid feature data (Sharp Sports, FantasyPros, the-odds-api paid tier).** Free features cap out at the literature ceiling. Higher-fidelity inputs MIGHT cross the 2pp C6 gap, but the operator's $100 capital cap makes paid data uneconomical (a $30/mo data subscription at 1% return on $32 of capital generates -$30/mo).
5. **Different venue.** Polymarket has lower fees but US retail blockers (V3-C). The math changes meaningfully without the 14% maker fee + 1.5pp slippage cost stack, but this is not a near-term option.

Per the operator's kill-early preference in `feedback_kill_early.md`: the cleanest action is to write this null verdict, leave v1 running on its actual domain, and stop. The Phase 3 critic will independently re-verify; the Phase 5 verdict synthesis will write the final operator-facing FINAL-VERDICT.md.

## 7. v2 failure-mode comparison

The operator brief required v3 to not repeat v2's failure modes. Status of each:

| v2 failure mode | v3 status |
|---|---|
| C5 in-sample leak | **PREVENTED.** `trainer=make_trainer(features)` is wired correctly in the gate runner; S2 verifies all 4 folds are chronologically clean. |
| Feature look-ahead | **PREVENTED.** V3-B1's leak audit passed 0 violations across 147 rows; all external queries strictly AS-OF at t35d_minus1. |
| Single-entity artifact (COL was 75% of v2 holdout) | **NOT PRESENT.** v3 holdout's top team (TB) is 4/45 = 8.9%, well below the 30% threshold. Dropping TB only moves mean from -18.9pp to -14.5pp; the loss is distributed across NFL teams, not concentrated. |
| Domain mismatch (v2 used per-game MLB markets while v1 trades season-long) | **UNRESOLVED after Phase 3 critic.** v3 dataset is built on v1's eligibility filter (30-180d lifetime, YES >= 0.70 at T-35d) but on a 5-series-family probe (NFL/NBA/NHL/MLB/NCAA) that excludes 17 of 19 series v1 actually attempts in live operations. v1's own backtest dataset has zero KXNFLWINS markets; v3's probe enumerates 95 of them. The C6 comparison is computed on a market type v1's measured edge has never been demonstrated on. Phase 3 critic Important Finding #2 + #3 + #4. |
| False C6 comparison | **PREVENTED.** C6 uses `v1_decision_fn` from `gate.py` verbatim on the same holdout the v3 rule is evaluated on. No v1-redefining or holdout-narrowing. |
| Pooled-mean = in-sample fit | **PREVENTED.** Per-fold retraining via `trainer` is verified by S2; fold means are honestly OOS within each fold. |

v3 does not inherit any of v2's specific failure modes. v3 fails for a different reason: the underlying data shape (96% YES train, 69% YES holdout, 46% NFL holdout YES) is structurally hostile to learning a price-deviation signal. This is exactly what V3-B1 foreshadowed.

## 8. Files written

- `src/kalshi_bot_v3/__init__.py` (package docstring; no executable code).
- `src/kalshi_bot_v3/model.py` (trainer factory + helper for anchored decision_fn).
- `scripts/v3/run_v3_gate.py` (the gate runner; invocable via `uv run python -m scripts.v3.run_v3_gate`).
- `data/v3/gate_results.json` (full GateResult + calibration + S1/S2/S3 + per-league for G1/G2/G3 on FULL / NFL-only / MLB-only slices).
- This research doc.

No modifications to `src/kalshi_bot/`, `src/kalshi_bot_v2/`, `scripts/v2/`, `scripts/` outside `scripts/v3/`, `tests/`, `data/` outside `data/v3/`, `.env`, or `data/live_trades/`. v1 continues running on the Windows scheduled task untouched.

## 9. Handoff to Phase 3 critic

The Phase 3 critic should verify, per the master plan Section 7 Phase 3 brief:

1. **C5 leak retest.** Re-execute `_kfold_splits` on the dataset and confirm S2's all-folds-clean verdict.
2. **Domain match audit.** Intersect the S3 holdout (series, lifetime, price) distribution with v1's `data/live_trades/` filled-orders log. Quantify the overlap; if v1's actual trades are NOT well-represented in the v3 holdout, that diminishes the C6 comparison's relevance.
3. **Single-entity retest at a deeper level.** S1 dropped the top-team only. Try dropping all NFL playoff markets (KXNFLPLAYOFF, 4 rows) or all of one fold's worth of NFL win-total markets. The point: confirm the negative holdout mean is not a single SUB-categorical artifact either.
4. **False-comparison audit.** Confirm `v1_decision_fn` is unchanged from `gate.py` (it is at `src/kalshi_bot_v2/gate.py:152-160` and was used verbatim).
5. **Feature look-ahead retest.** Spot-check the dataset's `nfl_games_played_pre_t35d` against the actual NFL schedule for 5 random rows.
6. **Multiple-testing audit.** v3 ran two LogReg variants (G2, G3) with locked hyperparameters and no holdout-tuning. Confirm no implicit hyperparameter search occurred. The thresholds `TRADE_PROB_THRESHOLD=0.70`, `LOGREG_C=1.0`, `class_weight=None` are all locked at module top and unchanged by the runner.

The critic should NOT redo the gate with tuned thresholds; per the operator brief, the locked criteria ARE the bar.
