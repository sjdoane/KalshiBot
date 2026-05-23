# Phase 1.5: Methodology Lock-In (Pre-Data)

**Author:** Project Kalshi research workflow
**Date:** 2026-05-22
**Status:** Methodology defined BEFORE pulling market data. Any change after the
first analysis run must be flagged in this document with date and rationale.

This document fixes the train/test split rules, the metrics, the pass criteria,
and the failure modes for the Phase 1.5 Zerve replication. Locking in
methodology pre-data is the standard discipline for avoiding p-hacking and is
non-negotiable for a gate that decides live-capital deployment. The operator
explicitly asked for "very cognizant and balanced" choices on splitting.

## 1. The question we are answering

Does the calibration miscalibration that Zerve reported on KXHIGH markets
(14.8x ECE improvement via isotonic regression on 8,494 settled markets)
survive an honest out-of-sample test? If yes, EC-1 is a real candidate and
Phase 2 strategy work is defensible. If no, the project ends here.

The Zerve study did not document an in-sample vs out-of-sample partition. The
critic flagged this as the central analytical mistake of the pre-critic
synthesis. Phase 1.5 corrects it.

## 2. Data we will pull (codified now to prevent ad-hoc edits later)

- **Source:** Kalshi production `/markets`, `/historical/trades` for series
  KXHIGHNY, KXHIGHCHI, KXHIGHMIA, KXHIGHLAX, KXHIGHDEN.
- **Window:** 2024-01-01 through 2026-04-30 (16 months). 2024 chosen as the
  starting point because Kalshi sports markets and major institutional MMs
  (Jump, Susquehanna) came online in early 2025; we need a window that
  reflects post-pro-entry microstructure, not the 2022-2023 retail-only era.
  2026-05 is excluded as the "out-of-time" buffer that may still be moving.
- **Market filter:** status = "settled", contract_type = "regular" (we
  exclude any composite markets if present).
- **Per-market features captured:**
  - ticker, series_ticker, event_ticker, city
  - market_open_time, market_close_time (UTC)
  - strike_price_F (Fahrenheit threshold)
  - settle_outcome (1 if observed high exceeded strike, else 0)
  - mid_price_at_T (VWAP over the 60 minutes ending 30 minutes before close)
    -- this is the "market probability we would have traded against"
  - last_trade_price (sanity check)
  - n_trades_total (liquidity proxy)

The 30-minute-before-close timestamp is chosen because Kalshi resolves
post-close based on NWS observations; the last 30 minutes typically include
the resolution itself becoming clear, which would contaminate the analysis
with realized information. Using mid_price_at_T = close - 30min keeps the
analysis on a horizon where edge would be tradable.

## 3. The split design (locked)

Two complementary splits. Both must show the calibration generalizes
out-of-sample for the gate to pass.

### 3.1 Walk-forward time splits (primary)

Parameters fixed in code (`make_walk_forward_splits` in
`src/kalshi_bot/analysis/train_test_split.py`):

- train_window = 180 days
- test_window = 30 days
- purge = 7 days
- step = 30 days (test windows tile the calendar, no overlap)

With the 2024-01-01 to 2026-04-30 corpus, this yields approximately 22 disjoint
walk-forward splits. The gate requires the calibration to show OOS improvement
in at least 4 of these splits and a positive median improvement across all
splits.

**Why time-based, not random K-fold:** financial time series have regime
changes (Fed cycle, election cycle, weather seasonality, MM entry). Random
K-fold would let the model see future regimes during training, which is the
classic backtest leakage source. Walk-forward respects the arrow of time.

**Why 7-day purge:** KXHIGH markets are daily-resolution, but the same
underlying weather forecast informs many markets. NWS forecast skill rolls
forward in 6-12 hour cycles, but the GFS-ensemble-based calibration signal
itself can have weekly correlations (e.g., persistent ridge or trough). A
7-day gap is conservative; 2 days would be defensible too but I am erring
on the more anti-leakage side.

### 3.2 Leave-one-city-out (secondary)

Parameters: train on 4 cities, test on the 5th. Repeat for each of the 5
cities as test set. The gate requires that the OOS ECE improvement is
positive on at least 3 of 5 cities and not negative on any single city by
more than 20%.

**Why cross-city:** if the calibration is real, it should generalize across
climates and across city-specific market microstructure. If it only works
on NYC (e.g., because NYC has a specific trader cohort that mispriced in a
specific way that does not exist in MIA), the apparent calibration is a
local artifact, not a tradable edge.

## 4. The metrics (locked)

All implemented in `src/kalshi_bot/analysis/metrics.py` with unit tests.

- **Primary: Expected Calibration Error (ECE)**, equal-width 10 bins on
  [0, 1]. Formula: sum_b (count_b / N) * |mean_pred_b - mean_outcome_b|.
- **Secondary: Brier score** (mean squared error). Used as a complementary
  comparator because ECE is binned and can hide point-wise miscalibration.
- **Per-trade gross edge:** |model_prob - market_prob|. We report median
  across the test set and median on shoulder strikes (market_prob in
  [0.15, 0.40] union [0.60, 0.85]). Shoulder is the EC-1 focus.
- **Hit rate at edge thresholds:** fraction of correct directional bets
  among trades that clear thresholds {0.02, 0.05, 0.10}.
- **Fee-adjusted edge:** subtract the Kalshi maker round-trip fee
  (~0.88% at P=0.5; less at deep strikes) from gross edge and report the
  net for shoulder strikes. EC-1 is a maker strategy.

## 5. Pass criteria (locked, sourced from research-document.md §8)

The Phase 1.5 gate PASSES if ALL of the following hold on the walk-forward
splits:

1. **OOS ECE improvement (median across splits) is at least 5x**, i.e.,
   `median(ECE_raw_test / ECE_recalibrated_test) >= 5`.
2. **Median per-trade gross edge on shoulder strikes is at least 2pp**,
   measured across all walk-forward test windows pooled.
3. **At least 4 of the 22 walk-forward splits each show OOS ECE improvement
   >= 3x** (per-split stability check).
4. **Leave-one-city-out: ECE improvement positive on >= 3 of 5 cities and
   no single city shows a > 20% worsening.**
5. **Fee-adjusted shoulder-strike edge (median, maker fees, no slippage)
   is positive.** A nominal 2pp gross that turns negative after fees is
   not a candidate.

The gate FAILS otherwise. Failure means EC-1 is not a tradable hypothesis
at the scale and infrastructure available, and the project ends without
Phase 2.

## 6. Anti-leakage checklist

Run at the start of every analysis batch (`scripts/phase_1_5/run_gate.py`
will emit these as assertions; failures block the run).

- [ ] Every market in a split's test set has market_close_time AFTER the
      split's purge buffer ends.
- [ ] Every market in a split's train set has market_close_time BEFORE the
      split's train_end (i.e., fully resolved in train, no future
      information).
- [ ] mid_price_at_T uses ONLY trades whose timestamp is at or before T
      (verified with assert on the trade window query).
- [ ] settle_outcome is derived from Kalshi's official settlement, not
      from any third-party weather observation (avoids two-source
      disagreement).
- [ ] No feature is computed using data with timestamp >= market_close_time.
- [ ] The isotonic calibrator is fit ONLY on the train partition; predict()
      is called only on test partition rows.

## 7. What we will NOT do (also locked)

- We will NOT change the pass criteria after seeing initial results. If the
  numbers look promising but a criterion fails, we report the partial
  result honestly and the gate fails.
- We will NOT try alternative model families (Platt scaling, beta
  calibration, etc.) until the isotonic baseline has been honestly
  evaluated. Adding model families post-hoc is p-hacking.
- We will NOT tune the purge window or the shoulder-strike range after
  seeing results. These are pre-committed.
- We will NOT include the most recent 30 days in the corpus (out-of-time
  buffer); that data is held out for a "real-life" sanity check after the
  gate passes (if it does).

## 8. If the gate passes

The Phase 2 strategy proposal would be a maker-quoting bot on KXHIGH
shoulder strikes that uses the isotonic-recalibrated probability vs market
mid to decide which side to quote. Strategy design will reference this
methodology for the historical edge basis but will independently validate
on the held-out 30-day buffer and then on live paper trading for >= 200
fills before any real capital. Pass criteria for live trading remain those
in research-document.md §8.

## 9. If the gate fails

Project ends. README is updated to reflect Phase 1.5 result. The engineering
artifacts (auth, client, analysis modules, tests) remain in the repo as a
reference implementation. No live capital is deployed.

## 10. Change log

- 2026-05-22: Initial draft, pre-data. Methodology locked.
- 2026-05-23: Phase 1.5 run produced gate FAIL on C1 (4.77x vs 5x required;
  other 4 criteria PASS by wide margins). Post-run diagnosis: the locked
  window (60 min ending 30 min before close) measures POST-resolution
  prices, not the pre-resolution mispricing a trading bot would face.
  Hit rates of 100% and dataset mid p50 = $0.01 / p95 = $0.99 confirmed
  the calibration was learning extreme-strike near-settlement behavior,
  not tradable forecast edge. See Phase 1.6 below for the corrected
  window. The Phase 1.5 result stands as recorded; Phase 1.6 is a NEW
  experiment with its own pre-data lock.

---

# Phase 1.6: Repeat with Pre-Resolution Trading Window

**Lock date:** 2026-05-23 (before refetching trades).

## What changed from Phase 1.5

Window only. Everything else is identical: same split parameters
(180d/30d/7d/30d), same shoulder strike ranges, same pass thresholds
(5x ECE, 2pp shoulder edge, 4 splits >= 3x, 3 of 5 LOCO, positive net
edge), same isotonic calibration, same five locked criteria.

## New window (locked)

VWAP over `[open + 1h, open + 13h]`. This is:

- 12 contiguous hours starting 1 hour after market open (skip the first
  hour to avoid initial price-discovery noise).
- Ending 1 hour BEFORE the measurement period begins. KXHIGH markets
  open at ~14:00 UTC the day before measurement and close ~04:00 UTC of
  the day after; measurement period is the calendar day in the city's
  local time. The new window ends safely before any hourly NWS
  observation could have started arriving for the measurement day.
- 13-14 hours of trading time remain after this window for the market
  to converge to settlement; that period is what Phase 1.5 was
  measuring and is explicitly excluded here.

## What this changes about the input

mid_price_at_T is now the trade-VWAP in the 12-hour pre-resolution
window. Markets with zero trades in this window are dropped (same
filter rule as Phase 1.5). Empirically this is expected to lose more
markets than the close-window cut (early-market liquidity is thinner),
which is acceptable - it costs us some sample size but only on markets
that no live trading bot could have entered into anyway.

## What this does NOT change

- The 5 pass criteria thresholds (C1-C5)
- The walk-forward and LOCO methodology
- The purge buffer (7 days)
- The shoulder strike definitions ([0.15, 0.40] and [0.60, 0.85])
- The isotonic calibrator behavior

## Why this isn't p-hacking

The methodology lock-in clause says "we will NOT change the pass
criteria after seeing results." We are not changing criteria. We are
fixing a flawed input definition (window placement) that was a latent
bug, not a tuning knob. The pass criteria numbers stay the same.

Concrete commitment: if Phase 1.6 FAILS the same five criteria (or
fails by a similar narrow margin on C1), the project ends. We do not
get a third bite. This is the last shot.

## Phase 1.6 change log

- 2026-05-23: Phase 1.6 locked. Window changed; pass criteria unchanged.
