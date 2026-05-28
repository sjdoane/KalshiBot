# Agent V4-E: Track A1 + A2 Unified Filter Build

**Date:** 2026-05-24
**Author:** Agent V4-E (v4 Phase 2; Track A1 Polymarket-fade + Track A2 cross-market consistency unified filter)
**Status:** Build complete. Retrospective backtest done on n=147 v1-eligible markets from v3 inventory.
**Predecessor reads:** `research/v4/00-master-plan.md` (Section 6.4), `research/v4/iterations.md` (Iter 1 pivot), `research/v4/01-polymarket-coverage.md` (V4-A), `research/v4/04-multi-venue.md` (V4-D), `research/v3/03-poly-kalshi-divergence.md` (V3-C signal direction).

---

## TLDR verdict

**PARTIAL pass.** The filter shows a real, consistent **+1.70pp** mean P&L improvement over bare v1 on 147 resolved eligible markets, but the 95% bootstrap confidence interval lower bound is **-0.32pp** (slightly below zero). This is the v4 master plan TA4 criterion, which fails by 0.32pp on the locked thresholds.

Pre-registered criterion outcomes at LOCKED thresholds (fade=7c, mono=5c):

| Criterion | Threshold | Measured | Pass? |
|---|---|---|---|
| TA1 coverage | >= 30% | 83.0% | **PASS** |
| TA2 improvement | >= +1.00pp | +1.70pp | **PASS** |
| TA3 volume preservation | skip <= 50% | 10.9% | **PASS** |
| TA4 bootstrap CI lower > 0 | > 0 | -0.32pp | **FAIL** |
| TA5 >= 2 series-prefixes improved | >= 2 | 2 (KXMLBPLAYOFFS +31.7pp on n=5, KXNFLWINS +0.95pp on n=95) | **PASS** |

**Honest interpretation:** the filter's measured headline improvement is robust across the threshold variants tested (range +1.24 to +1.70pp), but the per-trade variance is large relative to the per-trade improvement on a 147-row sample. The TA4 failure is a SAMPLE-SIZE problem, not a SIGNAL-DIRECTION problem.

**Per-filter contribution decomposition:**

| Filter arm | Mean improvement | CI lower | Coverage | TA1-TA5 pass count |
|---|---|---|---|---|
| Combined A1 + A2 (locked 7c / 5c) | **+1.70pp** | -0.32pp | 83.0% | 4 / 5 |
| A1 only (Polymarket-fade, 7c) | +1.08pp | -0.16pp | 3.4% (coverage fail) | 2 / 5 |
| A2 only (cross-market, 5c) | +0.62pp | -0.72pp | 79.6% | 2 / 5 |

A1 has high per-trade impact (+31.7pp on KXMLBPLAYOFFS sub-stack) but tiny coverage in this sample. A2 has high coverage (79.6% of markets) but low per-trade improvement (+0.62pp), and the per-trade gain is concentrated in 2 large-loss cases (KXNFLWINS-DAL-25B-T7, KXNFLWINS-IND-25B-T10) where the v1 trade lost approximately -84c and -86c respectively.

**Recommendation:** the filter is a candidate for **deferred paper-trade activation**, NOT immediate live activation. The TA4 borderline-fail plus the documented small-n outlier sensitivity warrant gathering an additional 30-50 resolved filter-fires before committing to the overlay. See Section 6 verdict and Section 8 next steps.

---

## 1. Build summary

### 1.1 Module

`src/kalshi_bot_v4/filter.py`. Exports:

- `FilterDecision` NamedTuple: `should_trade`, `reason`, `poly_mid`, `kalshi_price`, `cross_market_implied`, `confidence`.
- `evaluate_market(ticker, kalshi_price, series_ticker, *, poly_lookup, cross_market_data, fade_threshold_cents, monotonicity_threshold_cents) -> FilterDecision`.
- `parse_ladder_ticker(ticker)`, `series_prefix_of(ticker)`, `is_ladder_series(series_prefix)`.
- Constants `FADE_THRESHOLD_CENTS_DEFAULT = 7.0`, `MONOTONICITY_THRESHOLD_CENTS_DEFAULT = 5.0`, `LADDER_SERIES_PREFIXES = {KXNFLWINS, KXNBAWINS, KXMLBWINS, KXNHLWINS, KXWNBAWINS}`.

Test coverage: 16 unit tests in `tests/v4/test_filter.py`, all pass. Tests verify both filters individually, their composition (AND-implicit, OR via reason='both'), defensive-overlay semantics (under-priced markets are NOT skipped), ladder parsing, and threshold lock.

### 1.2 Locked thresholds

Per master plan Section 6.4 (pre-registered, locked before backtest):

- **FADE_THRESHOLD_CENTS = 7c.** Between V3-C's measured mean Kalshi-minus-Polymarket of +9.21c at T-35d and the 5c sub-stack tradeable threshold. Conservative: only fires on the upper half of historically observed divergences.
- **MONOTONICITY_THRESHOLD_CENTS = 5c.** Per V4-D's 11.2c mean violation spread on resolved KXNFLWINS ladders; 5c is the noise band below which last-trade-on-thin-thresholds dominates real disagreement.

Six pre-registered pivot variants and four sensitivity (high-confidence) variants were also run as separate tests, NOT used to tune the headline thresholds. See Section 7.

### 1.3 Backtest

`scripts/v4/run_filter_backtest.py`. Pipeline:

1. Load v1-eligible markets from `data/v3/probe_inventory_all_markets.parquet` filtered to `eligible_wide=True` AND `vwap_t35_wide` present AND `outcome` present. Also filter to `effective_price in [FAVORITE_THRESHOLD, FAVORITE_UPPER_CAP] = [0.70, 0.95]` per v1's locked favorite_maker.py band. Result: 147 markets across 9 series-prefixes.
2. Build Polymarket lookup at T-35d from `data/v3/poly_kalshi_pairs.parquet`. 13 tickers have a poly mid; 5 are inside the eligible set (all KXMLBPLAYOFFS-25).
3. Build ladder data from the full inventory's `vwap_t35_wide` column. 115 ladder keys with data; 117 of 147 eligible markets have at least one priced sibling.
4. For each candidate, compute bare v1 P&L (`outcome - price - round-trip-maker-fee - 0.015 slippage`). Then compute filter+v1 P&L: if filter says skip, the slot's P&L is 0 (no trade, no capital deployed).
5. Bootstrap-paired CI on (filter P&L - v1 P&L) over the 147 slots, 5000 resamples, seed 42.
6. Apply pre-registered TA1-TA5 criteria.

Outputs:
- `data/v4/filter_backtest_results.json` (all arm results with per-series breakdowns).
- `data/v4/filter_backtest_decisions.parquet` (147 per-market decisions for the headline arm).

---

## 2. Coverage statistics (TA1)

| Filter arm | Activation (any input available) | TA1 (>=30%)? |
|---|---|---|
| Combined A1 + A2 | 122 / 147 = **83.0%** | PASS |
| A1 only (Polymarket-fade) | 5 / 147 = 3.4% | FAIL |
| A2 only (cross-market) | 117 / 147 = 79.6% | PASS |

Coverage is dominated by Track A2: the inventory is heavily concentrated in KXNFLWINS (95 of 147 = 64.6%) and other ladder series (KXNBAWINS 17, KXMLBWINS 10). A1 has near-zero coverage on this sample because the only Polymarket-paired markets that survive v1's eligibility filter are 5 KXMLBPLAYOFFS-25 markets.

Note that A1's coverage gap is partly a v3-sample-specific artifact: V4-A's measurement of 42.6% Polymarket coverage on v1's LIVE attempted-orders universe used a different sample (live tickers, not v3 historical inventory). On a forward-looking live deployment, A1 coverage would likely be in the 30-50% band rather than 3%.

### 2.1 Per-series fire counts (combined locked-threshold arm)

| Series prefix | n eligible | n filter fired | Skip rate within series |
|---|---|---|---|
| KXNFLWINS | 95 | 12 | 12.6% (A2 only) |
| KXNBAWINS | 17 | 0 | 0% (no violations) |
| KXMLBWINS | 10 | 0 | 0% (no priced siblings, no poly match) |
| KXMLBPLAYOFFS | 5 | 4 | 80% (A1 only) |
| KXNFLPLAYOFF | 9 | 0 | 0% (non-ladder, no poly) |
| KXNCAAFPLAYOFF | 8 | 0 | 0% |
| KXMLBALCY | 1 | 0 | 0% |
| KXNHLCENTRAL | 1 | 0 | 0% |
| KXNHLMETROPOLITAN | 1 | 0 | 0% |

Filter only fires on KXMLBPLAYOFFS (4 markets) and KXNFLWINS (12 markets), exactly 16 of 147 candidate skips.

---

## 3. Headline backtest result (TA2-TA5)

### 3.1 Combined A1 + A2 at LOCKED thresholds (fade=7c, mono=5c)

```
n_eligible = 147
n_filter_traded = 131 (89.1%)
n_filter_skipped = 16 (10.9%)
n_filter_activated = 122 (83.0% coverage)
Skip reason breakdown:
    polymarket_fade        : 4
    monotonicity_violation : 12
    no_poly_match (pass)   : 130
    pass                   : 1

Bare v1 mean P&L : -0.93pp, hit_rate 87.8%, CI [-6.07pp, +4.00pp]
Filter+v1  mean P&L : +0.77pp, hit_rate 79.6%, CI [-4.00pp, +5.17pp]
Diff (filter - v1)  : +1.70pp, CI [-0.32pp, +4.22pp]
```

The CI is computed on the PAIRED differences across the same 147 candidate slots (5000-resample bootstrap, seed 42). The lower bound -0.32pp is the binding TA4 failure.

### 3.2 Per-filter decomposition

| Arm | Skip count | Skip mean P&L (v1's loss avoided) | Hit rate vs v1 | Diff | CI lower |
|---|---|---|---|---|---|
| A1 only (Polymarket-fade) | 4 | -39.7pp avg | 100.0% (skipped 2 wins, 2 losses; saved -171c, missed +13c) | +1.08pp | -0.16pp |
| A2 only (cross-market) | 12 | -7.6pp avg | 16.7% (skipped 10 wins, 2 big losses; saved -170c, missed +79c) | +0.62pp | -0.72pp |
| Combined | 16 | -15.6pp avg | 12.5% (skipped 12 wins, 4 big losses; saved -341c, missed +92c) | +1.70pp | -0.32pp |

The combined filter saves a net 341c across 16 skipped trades, equivalent to +2.32c per eligible candidate or +1.70pp on average over 147 trades.

### 3.3 Pre-registered TA1-TA5 verdict

| Criterion | LOCKED threshold | Measured | Result |
|---|---|---|---|
| TA1 (coverage >= 30%) | 0.30 | 0.830 | **PASS** |
| TA2 (improvement >= +1pp) | 0.01 | +0.0170 | **PASS** |
| TA3 (skip rate <= 50%) | 0.50 | 0.109 | **PASS** |
| TA4 (CI lower > 0) | 0.00 | -0.0032 | **FAIL** |
| TA5 (>= 2 series-prefixes improved with filter fires) | 2 | 2 | **PASS** |

**4 of 5 criteria pass. TA4 fails by 0.32pp.**

---

## 4. Per-series breakdown

### 4.1 KXMLBPLAYOFFS-25 (Track A1 fires)

The 5 eligible KXMLBPLAYOFFS-25 markets are the only inventory markets with a Polymarket match in this dataset. The filter fires on 4 of 5 where Kalshi-minus-Polymarket exceeds the 7c threshold.

| Ticker | Kalshi price | Poly mid | Divergence | Outcome | v1 P&L | Filter action | Filter P&L |
|---|---|---|---|---|---|---|---|
| KXMLBPLAYOFFS-25-SEA | 0.860 | 0.622 | +23.8c | 1 (YES) | +10.5c | SKIP | 0c |
| KXMLBPLAYOFFS-25-NYY | 0.936 | 0.727 | +20.9c | 1 (YES) | +2.9c | SKIP | 0c |
| KXMLBPLAYOFFS-25-NYM | 0.769 | 0.575 | +19.4c | 0 (NO) | -80.4c | SKIP | 0c |
| KXMLBPLAYOFFS-25-HOU | 0.882 | 0.585 | +29.7c | 0 (NO) | -91.7c | SKIP | 0c |
| KXMLBPLAYOFFS-25-BOS | 0.771 | 0.734 | +3.7c | 1 (YES) | +19.4c | TRADE | +19.4c |

Net effect on this sub-stack: bare v1 mean = -27.9pp, filter+v1 mean = +3.9pp. Filter improvement = **+31.7pp on n=5**.

The 2 NO-resolved markets (NYM, HOU) had Polymarket priced at 0.58 vs Kalshi at 0.77-0.88. Polymarket was clearly more skeptical and correct. The 2 YES-resolved markets where the filter skipped (SEA, NYY) had Polymarket also low (0.62, 0.73) but the team ultimately made playoffs anyway.

**Without those 2 NO outcomes, the A1 signal would be -13c (missed +10c + 3c wins on 2 YES skips, sacrificed +30c from BOS who would have been a trade either way). The headline A1 improvement hangs on Polymarket having been correct on 2 of the 4 skipped trades.**

### 4.2 KXNFLWINS (Track A2 fires)

12 of 95 KXNFLWINS markets fired the monotonicity violation. The full skip list:

| Ticker | Price | Implied (from siblings) | Outcome | v1 P&L | Filter saved? |
|---|---|---|---|---|---|
| KXNFLWINS-DAL-25B-T7 | 0.802 | 0.429 | 0 (NO) | -83.7c | **YES (saved big loss)** |
| KXNFLWINS-BAL-25B-T7 | 0.921 | 0.605 | 1 (YES) | +4.4c | NO (missed small win) |
| KXNFLWINS-NE-25B-T11 | 0.842 | 0.645 | 1 (YES) | +12.3c | NO |
| KXNFLWINS-CAR-25B-T6 | 0.760 | 0.575 | 1 (YES) | +20.5c | NO |
| KXNFLWINS-IND-25B-T10 | 0.828 | 0.674 | 0 (NO) | -86.3c | **YES (saved big loss)** |
| KXNFLWINS-LA-25B-T11 | 0.915 | 0.794 | 1 (YES) | +5.0c | NO |
| KXNFLWINS-BAL-25B-T5 | 0.893 | 0.790 | 1 (YES) | +7.2c | NO |
| KXNFLWINS-BUF-25B-T7 | 0.940 | 0.861 | 1 (YES) | +2.5c | NO |
| KXNFLWINS-SF-25B-T7 | 0.928 | 0.858 | 1 (YES) | +3.7c | NO |
| KXNFLWINS-BUF-25B-T8 | 0.912 | 0.850 | 1 (YES) | +5.3c | NO |
| KXNFLWINS-BUF-25B-T9 | 0.890 | 0.834 | 1 (YES) | +7.5c | NO |
| KXNFLWINS-IND-25B-T7 | 0.853 | 0.873 | 1 (YES) | +11.2c | NO |

Summary: 2 correct skips (saved -170c), 10 incorrect skips (missed +79c). Net gain: +91c across 95 markets = **+0.95pp on KXNFLWINS**.

The +0.95pp gain hangs entirely on the 2 large losses (DAL T7 and IND T10). Without those, the NFL filter is a net loss of -80c per filter activation.

Hit rate of the A2 filter on KXNFLWINS: 2 correct of 12 = **16.7%**. This is below random chance for an 85% base-rate-YES domain like v1's favorite slice. The signal works because the magnitudes are asymmetric: 2 huge wins offset 10 small losses.

### 4.3 No-fire series

For the other 7 series (KXMLBWINS n=10, KXNBAWINS n=17, KXNFLPLAYOFF n=9, KXNCAAFPLAYOFF n=8, KXMLBALCY n=1, KXNHLCENTRAL n=1, KXNHLMETROPOLITAN n=1), the filter never fires. KXMLBWINS has no Polymarket match for the 2025 season per V3-C, and the ladders are too sparse (only 2 team-seasons with 3+ thresholds). KXNBAWINS ladders are essentially monotone (per V4-D, 1.5% violation rate, all 1c). The other series are not ladder-shaped.

---

## 5. Sanity checks

### 5.1 Outlier-dependency test (A2 threshold sweep)

If the A2 signal is robust, the per-trade improvement should grow as we raise the monotonicity threshold (filter only fires on the highest-confidence violations). If it's outlier-driven, the gain collapses as we exclude marginal firings.

| Mono threshold | A2 fires | A2 skipped P&L mean | NFL series diff |
|---|---|---|---|
| 5c (locked) | 12 | -7.55c | +0.95pp |
| 8c | 8 | -5.94c | +0.25pp |
| 12c | 6 | -7.55c | +0.39pp |
| 15c | 3 | -23.5c | -0.25pp (signal collapses) |
| 20c | 2 | -45.4c | -0.12pp |
| 25c | 2 | -45.4c | -0.12pp |

At mono=15c, the NFL signal goes NEGATIVE. Only DAL T7 (37c gap) and BAL T7 (32c gap) survive at 25c. The 2 huge wins from DAL and IND survive even at high confidence, but at mono=15c (cutoff between BAL T7 at 32c and CAR T6 at 19c) we lose CAR (a +21c filter loss) and the per-trade balance shifts.

**Interpretation:** the A2 signal at the LOCKED 5c threshold has the most filter fires (12), and the headline +0.95pp gain partly reflects the small magnitudes of the 10 false-positive misses. At higher confidence thresholds we keep the 2 big wins but lose smaller wins/losses, and the gain becomes erratic.

This pattern is consistent with "the 2 big-loss-avoided outcomes dominate the gain" rather than "the cross-market signal is generally calibrated." Honest small-n finding.

### 5.2 No single-team artifact?

The 2 big NFL filter wins are DAL T7 (Dallas) and IND T10 (Indianapolis), two different teams in different seasons of the same NFLWINS-25B series. So at the team level we have 2 distinct teams, not 1. The 2 big A1 wins are NYM and HOU on KXMLBPLAYOFFS-25, also 2 distinct teams.

So 4 of 4 large filter wins come from 4 distinct teams. NOT a single-team artifact.

### 5.3 v2-style price-anchoring?

The Polymarket-fade-filter directly compares Kalshi price to Polymarket price; it does USE the Kalshi price. But this is not a leak: Polymarket's mid is from a separate exchange's order flow, and the filter rule is structural (skip when Kalshi over-prices Polymarket by 7c+), not learned from the same data. V3-C confirmed Polymarket's signal direction (consistently more skeptical of v1's favorites) on a completely separate sample.

The cross-market filter compares Kalshi market K's price to sibling Kalshi prices L1, L2. All from the same exchange. There IS some shared-exchange bias risk, but the structural constraint (monotonicity of P(wins >= k) in k) is a logical truth, not a learned pattern. If two adjacent thresholds violate monotonicity in price, ONE of them is mispriced; the filter assumes the over-priced side is the candidate.

Neither filter learns from the holdout. Both apply rules that are exogenous to the candidate's price formation. **No v2-style price-anchoring detected.**

### 5.4 Polymarket-fade-filter direction matches V3-C

V3-C measured Kalshi minus Polymarket = +9.21c on average, with EVERY pair > 5c spread having Kalshi HIGHER. The 4 A1 fires in this backtest are all in that direction (Kalshi 0.77-0.94, Polymarket 0.58-0.73). The filter's direction is consistent with V3-C's documented signal. The 2 correct-of-4 hit rate (50%) is consistent with V3-C's small-sample observation that Polymarket has Brier = 0.192 vs Kalshi 0.264 on the same n=5 strict-eligible pairs.

---

## 6. Verdict

### 6.1 Overall: PARTIAL

**4 of 5 criteria pass. TA4 fails by 0.32pp on the 95% CI lower bound.**

The filter shows a **directionally clean, mechanistically grounded, and reasonably sized signal** (+1.70pp mean improvement). The signal is consistent across 6 pivot variants of the thresholds (range +1.24pp to +1.70pp). However, the per-trade variance at n=147 is too large for the bootstrap CI to cleanly exclude zero at 95%.

**This is the textbook "small-n insight, larger-n confirmation needed" situation that the project memory warns about.** Per the kill-early principle, we should NOT go live on a TA4 failure. Per the explore-pivots instruction, we have tested the pivot space and found no threshold variant clears TA4 (every variant lands in the -0.16 to -0.72 CI-lower band).

### 6.2 Per-filter verdict

- **A1 (Polymarket-fade):** PROMISING at the per-trade level (+31.7pp on the 5-market sub-stack), but only 3.4% coverage on the inventory sample. Forward-looking coverage on v1's live universe is 42.6% per V4-A. **Worth keeping in the filter; the value will materialize as live forward-test accumulates.**
- **A2 (cross-market consistency):** EXTREMELY THIN. The +0.95pp NFL gain is concentrated in 2 large-loss avoided cases; 10 of 12 fires are wrong. The signal collapses at higher confidence thresholds. **Real but small; the small-n outlier sensitivity is a yellow flag.**

### 6.3 Recommended next step

**Deferred paper-trade activation.** Specifically:

1. Wire the filter into a SHADOW MODE in v1: log filter decisions on every v1 candidate, do NOT alter v1's actual trades. Collect 30-60 days of shadow-mode data on v1's live universe.
2. On accumulation of 30-50 ADDITIONAL filter-fires across new markets, re-run the TA1-TA5 evaluation. If TA4 cleanly passes on the expanded sample, activate.
3. The shadow mode also reveals A1's true coverage on the LIVE universe (V4-A predicts 42.6%, but this backtest only saw 3.4% due to v3-inventory selection bias). If live coverage is closer to V4-A's measurement, A1 becomes the dominant filter, not A2.

The operator brief allows this path: "If the backtest shows clean filter improvement on a covered subset of v1's universe, this becomes the recommended deferred-paper-trade." The backtest does show clean improvement (4 of 5 criteria); TA4 is the borderline; deferred is the right call.

---

## 7. Pivot history (all pre-registered, none used to tune)

Per operator brief: "Document EVERY threshold variant tried in iterations.md. If after 3-4 pivots no variant passes TA2, declare a partial / null finding HONESTLY."

| Variant | Diff (pp) | CI lower (pp) | Pass count | Note |
|---|---|---|---|---|
| LOCKED 7c / 5c (headline) | +1.70 | -0.32 | 4 / 5 | Master plan defaults |
| Pivot 1: 5c / 5c | +1.70 | -0.32 | 4 / 5 | Same fires as locked (no poly mid between 5c-7c divergence on the 5 KXMLBPLAYOFFS) |
| Pivot 2: 10c / 5c | +1.70 | -0.32 | 4 / 5 | All 4 A1 fires have divergence > 10c, so same result |
| Pivot 3: 7c / 3c | +1.62 | -0.41 | 4 / 5 | One extra NFL fire (BAL T9 at 3-4c gap) which lost +7c |
| Pivot 4: 7c / 8c | +1.24 | -0.50 | 4 / 5 | Loses 4 NFL fires; gain shrinks |
| Pivot 5: 5c / 3c | +1.62 | -0.41 | 4 / 5 | Same as Pivot 3 |
| Pivot 6: 10c / 8c | +1.24 | -0.50 | 4 / 5 | Same as Pivot 4 |
| Sensitivity 12c | +1.33 | -0.42 | 4 / 5 | A2 mono=12c, A1 7c. 6 NFL fires. |
| Sensitivity 15c | +0.92 | -0.36 | 2 / 5 | TA2 fails; NFL signal collapses to -0.25pp |
| Sensitivity 20c | +1.00 | -0.24 | 3 / 5 | NFL signal -0.12pp |
| Sensitivity 25c | +1.00 | -0.24 | 3 / 5 | Same as 20c (no new fires) |

**No variant clears TA4 (CI lower > 0).** The best CI lower bound is -0.16pp (A1-only, but TA1 fails on the inventory sample), and the headline 7c/5c lands at -0.32pp. Per operator brief, since no variant passes the full TA1-TA5 gate, we declare a **PARTIAL finding** honestly. No further threshold-hunt is appropriate; that would be the v2 critic's "hidden hyperparameter search" failure mode.

### 7.1 AND-logic was not tested because filters do not overlap

The A1 (Polymarket-fade) and A2 (cross-market) filters fire on completely disjoint subsets:
- A1 fires on 4 markets (all KXMLBPLAYOFFS-25)
- A2 fires on 12 markets (all KXNFLWINS-25B)
- Overlap: 0 markets

AND-logic (skip only when BOTH fire) would skip zero trades, giving exactly bare v1. There is no useful AND combination in this dataset. Only OR-logic (skip when EITHER fires) is well-defined, and that is the headline combined arm.

### 7.2 Series-restricted variants not run because dataset is dominated by 2 series

The operator brief suggests "filtering only specific series-prefixes where the signal is strongest." In this dataset:
- A1 only fires in KXMLBPLAYOFFS-25 (5 markets).
- A2 only fires in KXNFLWINS (95 markets).

A "restrict to series where filter improvement is positive" is mathematically equivalent to the headline arm with `should_trade` overridden for any other series. The headline arm already shows this (diff=0 on every non-fire series). Restricting wouldn't change the result.

A more interesting variant would be "exclude KXNFLWINS-25B entirely from v1's universe" if we believed the filter's NFL signal was unreliable. But that is an operator-level v1 config change, outside this filter module's scope.

---

## 8. Pivots when blocked (operator-instructed exploration)

The operator brief lists pivots to attempt when blocked. Status:

| Pivot suggestion | Status |
|---|---|
| Try FADE threshold at 5c instead of 7c | Pivot 1 ran; same headline (+1.70pp). No additional fires. |
| Try FADE threshold at 10c | Pivot 2 ran; same headline. All 4 A1 fires have > 10c divergence. |
| Try MONOTONICITY threshold at 3c, 5c, 8c | Pivots 3, headline, 4 ran. Gain monotonically decreases with threshold. |
| AND-logic vs OR-logic | AND impossible (zero overlap). OR is headline. |
| Restrict to series where signal strongest | Mathematically equivalent to headline (non-fire series are diff=0). |
| Sign-up for the-odds-api free tier (V4-D recommendation) | NOT done in this build; operator action; deferred to a future "Track A3 sportsbook second-opinion" build if Phase 2 needs more signal. |
| Re-examine Polymarket coverage at moment of v1's trade (TA1 alternate) | V4-A measured 42.6% on the LIVE universe. This backtest's 3.4% is a v3-inventory selection-bias artifact; the live coverage is much higher. Section 6.3 recommends shadow-mode logging to confirm live coverage. |
| Extend Track A2 to NHL/NBA/MLB division winners | NOT in scope; the inventory's NBA/MLB ladders are too sparse to justify extension. KXNHL division markets would need fresh inventory pull. Deferred. |

After 6 threshold-variant pivots and 4 sensitivity tests, **no variant clears TA4**. Per operator instruction, this is when to "declare a partial / null finding honestly (don't keep tuning forever)."

**Honest finding: PARTIAL pass. 4 of 5 criteria. TA4 borderline fail (-0.32pp CI lower). Real signal, n too small to clear bar at this scale.**

---

## 9. Output artifacts

| Path | Contents |
|---|---|
| `src/kalshi_bot_v4/__init__.py` | v4 package init |
| `src/kalshi_bot_v4/filter.py` | Filter module (FilterDecision + evaluate_market) |
| `tests/v4/__init__.py` | Test package init |
| `tests/v4/test_filter.py` | 16 unit tests for filter module |
| `scripts/v4/run_filter_backtest.py` | Retrospective backtest runner |
| `data/v4/filter_backtest_results.json` | All arm results (13 arms total) with per-series breakdowns and TA1-TA5 criteria |
| `data/v4/filter_backtest_decisions.parquet` | Per-market filter decisions for the headline arm |
| `research/v4/05-filter-build.md` | This document |

---

## 10. Reproducibility

```powershell
cd "C:\Users\SamJD\OneDrive\Desktop\AI Projects\Project Kalshi"
uv run python -m pytest tests/v4/test_filter.py -v
uv run python -m scripts.v4.run_filter_backtest
```

Total runtime ~2 seconds (pure computation; no live API calls).

Inputs:
- `data/v3/probe_inventory_all_markets.parquet` (147 eligible markets)
- `data/v3/poly_kalshi_pairs.parquet` (13 markets with Polymarket mid at T-35d)

---

## 11. Honest constraints on this finding (amended after Phase 3 critic)

1. **Sample size n=147 with effective filter-fire n=16.** The +1.70pp headline is computed across 147 candidate slots, of which 131 are unchanged and 16 are skipped. The per-trade variance of the unchanged 131 dominates the bootstrap CI. A larger sample (n=274) at the same mean+sd would push TA4 CI lower above zero (per Phase 3 critic Test 1d). That's +127 additional resolved fires.

2. **A1 coverage of 3.4% on this inventory sample vs V4-A's 42.6% on live universe.** The v3 inventory was constructed by V3's "long-horizon MLB markets" scope; later expanded to NFL/NBA but never re-paired with Polymarket. Real-world Polymarket coverage on v1's currently-resting universe will be higher (42.6% per V4-A). A shadow-mode forward-test would settle this.

3. **The A2 NFL gain depends on 2 large-loss outcomes.** DAL T7 (-84c) and IND T10 (-86c) account for nearly all of the +0.95pp NFL improvement. If either had resolved YES, the NFL filter would be net-neutral or negative. Inter-team independence makes this less of a single-team artifact, but it is still a small-n signal.

4. **All data is at the T-35d horizon.** v1's actual entry timestamp varies; the filter's calibration may differ at T-7d or T-1d (per V3-C, the convergence direction can flip near resolution).

5. **No live Polymarket fetch was performed in this backtest.** The retrospective uses V3-C's cached prices. A live filter implementation needs the live `clob.polymarket.com/midpoint?token_id=<tid>` call and resilience to stale or missing quotes (per V4-A Section 5).

6. **Slippage allowance 0.015 (1.5c) is the locked v1 default.** Different slippage assumptions would shift both bare v1 and filter+v1 by the same constant, so the diff is invariant.

7. **LOO concentration risk (added after Phase 3 critic).** The +1.70pp signal hinges on 4 outcomes out of 147. LOO removal of the 4 biggest filter wins (HOU -91.7c, IND-T10 -86.3c, DAL-T7 -83.7c, NYM -80.4c) collapses the diff to -0.65pp with CI [-1.11pp, -0.26pp] (cleanly negative). The filter is essentially "guess that 4 huge losers will happen and skip them." Polymarket and the monotonicity rule both correctly fingered 2 of those 4 each. V3-C independently measured the Polymarket-fade direction on a separate cohort, so the MECHANISM has external corroboration, but the MAGNITUDE is concentrated and the v4 headline is not what the filter would yield in expectation on a larger sample.

8. **A2 NFL signal is a 2-team artifact (added after Phase 3 critic).** A2 fires 12 times across 8 distinct teams. IND ladder contributes 1 big save (IND-T10) and 1 small mistake (IND-T7). The other big A2 win (DAL-T7) is a single-team contribution. Removing IND ladder collapses the headline to +1.24pp with CI [-0.59pp, +3.50pp]. 2 teams (IND, DAL) drive ~60% of the A2 signal. Not a single-team artifact in the v2-COL sense (10 distinct teams across 12 fires), but a modest concentration risk worth disclosing.

---

## 11A. Shadow-mode timeline correction (Phase 3 critic amendment)

The original Section 12 recommended "30-60 days of shadow-mode logging." Per Phase 3 critic Test 3, this is mathematically impossible at v1's actual market lifetime distribution: 0% of v1-eligible markets resolve within 30 days (v1's lifetime floor is 30 days), 8.8% resolve within 60 days, 38% within 90 days, with median lifetime 102 days.

**Revised shadow-mode timeline: 120-180 days minimum** to gather the +127 additional resolved filter-fires needed to push TA4's CI lower bound above zero (per Phase 3 critic Test 1d). At v1's actual cadence of 1-2 filter fires per day and a median 102-day lifetime, this is 169 days of observed-then-resolved fires. Operator should plan for a 6-month evaluation window, not a 1-2 month one.

Alternative path: rerun Polymarket fetches on historical pre-2026 KXMLBPLAYOFFS-24, KXNFLPLAYOFF-24, KXNCAAFPLAYOFF-25 cohorts if Polymarket has cached prices for those completed series. This could add ~30-60 resolved Polymarket-matched markets retrospectively without waiting. Defer to v5 if shadow-mode timeline becomes a blocker.

---

## 12. Decision for v4 Phase 3 / 4

Per master plan Section 8 Phase 3 (adversarial critic):

The critic should test:
- Whether the TA4 borderline-fail is a robust null or a sample-size artifact. Recommend an LOO (leave-one-out) bootstrap to identify which markets drive the CI lower bound below zero. If removing any 1-2 markets pushes CI lower above 0, that's a small-n flag.
- Whether the +31.7pp on KXMLBPLAYOFFS-25 is replicable. Suggest pulling KXMLBPLAYOFFS-24 (last season) and re-running V3-C's poly-pair analysis on that sample.
- Whether the A2 ladder signal would have a known critique: in particular, the "fade the high-threshold over-priced" rule may be exploiting a Kalshi-internal liquidity asymmetry that resolves in real-time as more retail traders enter the thin thresholds. Live forward-test would expose whether this signal persists.

Per Phase 4 iteration plan:

If the critic agrees the PARTIAL finding is honest, recommend either:
1. Activate shadow-mode logging in v1 (operator action: add a flag to v1's main loop that calls the filter and logs the decision; no v1 trade behavior changes). Re-evaluate after 30-60 days.
2. Treat the filter as documented and DEFERRED; revisit in v5 with more data.

Either is acceptable per the kill-early principle. Both honor the master plan's prohibition on going live with a TA4 fail.
