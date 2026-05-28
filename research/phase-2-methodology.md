# Phase 2: Methodology Lock-In (Pre-Data)

**Strategy:** Politics x H from [strategy-comparison.md](strategy-comparison.md).
Maker-quote on Kalshi politics markets exhibiting Le's chronically-
compressed regime, at long horizon, in mid-band price ranges.

**Author:** Round 2 strategy-selection context
**Lock date:** 2026-05-23 (revised same-day to incorporate methodology-
critic findings)
**Status:** LOCKED before any politics data is pulled. Any change after the
first analysis run must be flagged in the Section 12 change log with date
and rationale.

Provenance: operator-approved proposal
[phase-2-proposal.md](phase-2-proposal.md); plan-critic findings 1-9
addressed at [critic-plan-phase-2.md](critic-plan-phase-2.md); methodology-
critic findings (3 BLOCKING + 4 IMPORTANT + 3 NICE-TO-HAVE) addressed at
[critic-methodology-phase-2.md](critic-methodology-phase-2.md).

This document is the Phase 2 analog of
[phase-1.5-methodology.md](phase-1.5-methodology.md). Sections 9 (what we
will NOT do) and 11 (kill-on-fail) are non-negotiable per the inherited
discipline.

## 1. The question we are answering

Does the chronically-compressed calibration regime that Le 2026 documents
for Kalshi politics markets (slope > 1, strongest at >1mo horizon)
produce a positive net-edge maker-quote opportunity for a $25 retail
account AT REALISTIC FILL PRICES, AFTER:

- Round-trip maker fees (Kalshi April 2025+ schedule)
- 1.5pp slippage allowance for residential retail latency
- Adverse selection from informed political traders (Bartlett VPIN-style)
- Small-trade VWAP (verifying retail-tradable fill prices, not large-trade
  compression we cannot capture)

If yes, Phase 3 = live strategy design + paper trading. If no, the
strategy ends per the no-third-bite rule.

**Phase 2 pass is NECESSARY-NOT-SUFFICIENT for Phase 3 deployment.** A
backtest gate validates that the mispricing exists in historical fills;
it does NOT validate fill rate, order-book liquidity at the quoted price,
or regime stability going forward. Phase 3 paper trading exists to test
those.

## 2. Data we will pull (codified now)

### 2.1 Series discovery

- Source: Kalshi production `/series` endpoint, filter for category =
  "Politics". Exact filter values discovered at pull time. Captured to
  `data/phase2/politics_series_index.json` for reproducibility.
- Expect KX-prefixed series tickers (post-2024 schema). Pre-2024
  legacy prefixes excluded; our window starts 2024-10-01 (post sign-flip;
  Section 2.3).

### 2.2 Market filter

- Status: settled.
- Resolution date in [2024-10-01, 2026-04-30]. The 2026-05-01-onward
  buffer is held out as out-of-time for a real-life sanity check after
  the gate runs.
- **Binary contracts only**: contract_type = "regular" (single Yes/No
  outcome). Multi-strike politics markets (5-candidate primaries etc.)
  are EXCLUDED in Phase 2 per plan-critic finding 4. Slope-based
  calibration is binary; multi-strike extension is a Phase 3 question.
- **Minimum lifetime trades >= 50** per market. Matches Le's per-market
  median for politics ([le-2026-crowd-wisdom.md](literature/le-2026-crowd-wisdom.md)
  "Per-domain breakdown on Kalshi").
- **Minimum trades in the trading window >= 20** (see Section 3).
- All filter values are HARD-LOCKED. If we discover during data pull that
  these filters select < 1000 markets, we report the count honestly and
  decide whether to widen the trading window per Option A/B in Section 3
  (pre-committed below). We do NOT silently relax filters.

### 2.3 Why 2024-10-01 is the start

The October 2024 CFTC ruling triggered a 27x volume surge and the maker-
taker sign flip ([becker-2026-microstructure.md](literature/becker-2026-microstructure.md)
"The 2024 sign flip"; Q3 2024 = $30M, Q4 2024 = $820M). Pre-flip Kalshi
politics economics are structurally different from current economics.

### 2.4 Per-market features captured

- ticker, series_ticker, event_ticker
- market_open_time, market_close_time, resolution_time (UTC)
- contract structure (binary Yes/No)
- settle_outcome (1 if YES resolved, else 0)
- All trades with timestamp, price, contract count, taker side, maker
  side
- Derived in dataset builder (Section 3):
  - mid_price_at_T_all: VWAP over all trades in window
  - mid_price_at_T_small: VWAP over trades with size <= 10 contracts
  - n_trades_in_window
  - n_small_trades_in_window
  - one_sided_flow_pct: max(buy_side_trades, sell_side_trades) / total
  - is_federal_election_market: bool, set by ticker/event keyword tagger
  - resolves_in_federal_election_month: bool (Nov-2024 or Nov-2026)

## 3. Trading window (locked)

For each market, the trade-window VWAP is computed over trades whose
timestamp falls in `[resolution_time - 35 days, resolution_time - 28 days]`.

Rationale:

- **Long-horizon (>= 28 days to resolution)**: Le's slope at >1mo is
  posterior mean ~1.65 (95% CI 1.46-1.83), well above the slope = 1
  calibrated baseline ([le-2026-crowd-wisdom.md](literature/le-2026-crowd-wisdom.md)
  "Domain-by-horizon trajectories"). This is the regime the strategy
  targets.
- **7-day window**: covers ~1 week of late-pre-resolution trading.
  28-day pre-resolution margin large enough that news/resolution
  information has not arrived; wide enough to typically include 20+
  trades per market.
- **Two VWAPs computed**: all-trade and small-trade (<= 10 contracts).
  Critic finding (trade-size scale effect, Le Delta = 0.53 95% CI
  [0.29, 0.75]) - small trades are LESS compressed than large.
  Gate must pass on small-trade VWAP to validate retail tradability.

**Anti-Phase-1.5-bug check**: trades with timestamp > resolution_time -
28 days are STRICTLY EXCLUDED from VWAP. The 28-day margin is far larger
than Phase 1.5's 30-minute margin because politics markets can have
news-driven jumps multiple days from resolution.

**Window-widening pre-commitment (Option A vs B)**: if after running the
fetcher the median market has < 20 trades in [-35d, -28d]:

- **Option A (preferred)**: widen to `[resolution - 42d, resolution - 28d]`
  (14-day window). The 28-day pre-resolution margin is preserved.
  Re-check median >= 20 trades. If still not, go to Option B.
- **Option B**: keep the 7-day window; drop markets with < 20 in-window
  trades. Report sample size loss honestly.

The choice is locked BEFORE seeing gate results. The criterion for
Option A is purely the median-trades sanity check on the FULL post-flip
politics dataset before any modeling.

## 4. Market filters (locked)

Beyond the data filters in Section 2.2, the strategy enters only markets
that satisfy ALL of:

- **Mid-band price filter**: small-trade VWAP in [0.20, 0.45] union
  [0.55, 0.80]. Avoids extreme strikes (Bartlett single-name adverse-
  selection, [bartlett-ohara-2026-adverse-selection.md](literature/bartlett-ohara-2026-adverse-selection.md)
  TL;DR items 2 and 4) and the dead-zone 0.45-0.55 where logit
  linearization makes slope > 1 produce near-zero edge.
- **Price-conditional one-sided-flow filter** (revised per methodology-
  critic finding 5):
  - If `one_sided_flow_pct > 0.65` AND small-trade VWAP in [0.30, 0.70]:
    EXCLUDE the market. The narrow mid-band is where Bartlett's adverse-
    selection effect concentrates; one-sided flow in this band signals
    informed trader activity, not consensus.
  - If `one_sided_flow_pct > 0.65` AND small-trade VWAP in [0.20, 0.30]
    or [0.70, 0.80]: KEEP the market. Consensus on a high-prior outcome
    is consistent with Le's compression and is the strategy's target.
- **Per-market minimum 20 trades in the [-35d, -28d] window**. Sample-
  size for VWAP. Below-threshold markets dropped; Section 3's window-
  widening pre-commitment determines whether we widen first.
- **Election-cycle diversity** (revised per methodology-critic finding 6
  and 7):
  - Tag each market via `is_federal_election_market` (ticker / event
    keyword tag for "senate", "house", "president", "POTUS", or specific
    candidate names from the 2024 and 2026 cycles).
  - After data pull and BEFORE running the gate: manually audit the top
    50 most-traded markets and verify the is_federal_election_market tag.
    If actual non-federal-election proportion in the corpus is < 30%,
    we have two pre-committed options:
    - **Audit Option A**: widen the corpus to 2024-09-01 to 2026-04-30
      (one extra month) and re-check.
    - **Audit Option B**: proceed with the federal-election-dominated
      corpus and explicitly flag in the results that gate verdict applies
      only to federal-election-cycle markets.
  - In either case: report per-split mean net edge SEPARATELY for splits
    where test partition is > 50% federal-election-month vs not (see
    Section 6.6).

## 5. Split design (locked)

Two complementary splits. Walk-forward as primary; leave-one-event-out
as secondary generalization check.

### 5.1 Walk-forward time splits (revised per methodology-critic finding 4)

Parameters (fixed in code in
`src/kalshi_bot/analysis/train_test_split.py`):

- train_window = 180 days (by resolution_time)
- test_window = 30 days (by resolution_time)
- purge = 14 days
- step = 30 days

**Lifetime-straddle filter (NEW)**: in addition to the resolution_time-
based assignment, a market is in test partition i ONLY IF its
`market_open_time` falls AFTER `train_end_i + 14 days`. Markets that open
during train and resolve during test (their lifetimes straddle the
boundary) are DROPPED from the test set for split i. This prevents the
isotonic / logistic train fit from absorbing test-market price dynamics
through shared news exposure during overlapping lifetimes.

Markets dropped from one split's test set may still appear in OTHER
splits where the lifetime fits. We expect a 10-30% test-set sample
reduction from this filter, which is acceptable - the alternative is
biased calibration.

With the 2024-10-01 to 2026-04-30 corpus (577 days), the parameter set
yields **exactly 12 walk-forward splits**: (577 - 180 - 14 - 30) / 30 + 1
= 11.77 + 1, floored to 12. An earlier draft of this methodology stated
"16-18 splits" assuming a wider corpus; the code-review milestone 1
discovered the actual count is 12. The C3 threshold below is recomputed
for N=12 to preserve the same alpha = 0.05 binomial-null Type-I control.

### 5.2 Leave-one-major-event-out (secondary)

Four event windows; hold out all markets resolving in each window and
train on the rest:

- Nov 2024 federal election cycle (resolution_time 2024-10-01 to
  2024-12-31)
- Q1 2025 FOMC + policy events (2025-01-01 to 2025-03-31)
- Mid-2025 special elections / primary cycle (2025-04-01 to 2025-09-30)
- Q4 2025 / Q1 2026 pre-midterm primary cycle (2025-10-01 to 2026-03-31)

Gate requires >= 3 of 4 windows to show positive net edge with all
C1-C5 criteria intact.

## 6. Metrics (locked)

All implemented in `src/kalshi_bot/analysis/metrics.py` with unit tests.

### 6.1 Primary calibration metric: empirical slope on small-trade VWAP

For each test partition:

1. Compute logistic regression of outcome on `logit(mid_price_at_T_small)`:
   `logit(outcome_prob) = a + b * logit(market_prob)`. Fit MLE on test set.
2. Report slope `b` per partition.
3. ALSO compute per-MARKET slope distribution: for markets with > 50
   trades in window, fit a within-market slope and report the median,
   lower quartile, upper quartile across markets in the test partition.

Critic finding 1: per-partition slope median can be dragged up by 2-3
high-slope splits. The lower-quartile check below in C1 controls for
this.

### 6.2 Secondary calibration metric: ECE

Equal-width 10-bin ECE on raw small-trade VWAP and on isotonic-
recalibrated price. ECE ratio (raw / recalibrated) reported but NOT a
gate criterion. ECE remains useful as a sanity comparator across phases.

### 6.3 Per-trade gross edge

For each market in the test set, gross edge =
`|recalibrated_prob - mid_price_at_T_small|`. Recalibrated_prob comes
from the isotonic fit on the TRAIN partition.

Report median across all test markets AND median restricted to mid-band
strategy-eligible markets (Section 4 filters applied).

### 6.4 Net edge (the binding criterion)

Per-trade net edge =
`gross_edge - round_trip_maker_fee - 0.015 (slippage allowance)`.

Round-trip maker fee uses the Kalshi formula
(`ceil(0.0175 * 100 * P * (1 - P)) cents`, doubled for round-trip),
computed on `mid_price_at_T_small`.

Slippage of 1.5pp per plan-critic finding C5. Phase 1.5/1.6 used 0pp
(unrealistic for residential retail latency on news-driven markets).

Report:
- Per-split median and mean net edge.
- Per-split count of markets with net edge > 0.
- **Pooled bootstrap diagnostic** (NEW per methodology-critic finding 8):
  estimate the pooled mean per-trade net edge across all test partitions
  concatenated, with 95% CI from 5000 bootstrap resamples. Report the
  pooled mean and CI as a DIAGNOSTIC (not a gate). The pooled estimate
  has higher statistical power than per-split counts but doesn't replace
  the gate criteria.

### 6.5 Per-market slope distribution

Detail of 6.1.3. For markets with >= 50 trades in window, compute per-
market slope (within the +/- 35d window). Report distribution. Used by
C1 lower-quartile clause.

### 6.6 Election-cycle composition report (NEW per methodology-critic finding 6)

For each walk-forward split, report:

- Fraction of test-set markets that resolve in a federal-election month
  (Nov 2024, Nov 2026).
- Fraction tagged as federal-election-market (regardless of resolution
  month).
- Per-split mean net edge SEPARATELY for federal-election-dominated
  splits (> 50% test markets are federal-election) vs not.

If the strategy passes C1-C5 only on federal-election-dominated splits,
the verdict must explicitly state: "Gate passes only in election-
dominated regime; Phase 3 deployment in off-cycle periods may not
generalize."

## 7. Pass criteria (locked, revised per methodology-critic findings 1-3)

The Phase 2 gate PASSES if ALL of the following hold on the walk-forward
splits AND the leave-one-event-out check passes >= 3 of 4:

1. **C1 (regime presence, dual-clause per critic finding 2)**:
   - C1a: median per-partition logistic-recalibration slope on test
     partition (small-trade VWAP) >= 1.2 across walk-forward splits.
   - C1b: per-partition slope lower-quartile (25th percentile of the
     per-partition slope estimates) >= 1.0.
   Both clauses must hold. C1b prevents a marginal pass driven by 2-3
   outlier splits.
2. **C2 (gross edge)**: median per-trade gross edge on mid-band
   strategy-eligible markets >= 2.04pp (2x Becker politics 1.02pp
   average; [becker-2026-microstructure.md](literature/becker-2026-microstructure.md)
   "Per-category maker-taker gap").
3. **C3 (per-split stability, revised per critic finding 1)**: at least
   **10 of the 12 walk-forward splits** show median net (after-fee, after-
   slippage) edge > 0 on small-trade VWAP. Binomial null cumulative
   probability under H0 (true edge = 0) at 10/12 is
   `(C(12,10) + C(12,11) + C(12,12)) / 2^12 = 79/4096 ~= 0.019`, well
   below the 0.05 target alpha. Walk-forward correlation pushes the
   effective false-acceptance rate higher than 0.019 but still below
   0.05, and far below the ~50% that the original 9/17 threshold
   allowed. If `_split_metrics` skips splits for sample-size reasons,
   the denominator (12) does not shrink; the unmet splits count as
   "did not show net > 0" and the threshold is harder to meet, which is
   the conservative direction.
4. **C4 (event-level generalization)**: >= 3 of 4 leave-one-event-out
   windows show net edge > 0.
5. **C5 (the binding net edge)**: BOTH median AND mean per-trade net
   edge > 0pp, computed across ALL test partitions concatenated, with
   maker fees AND 1.5pp slippage applied, on small-trade VWAP.
   - If C5 passes on all-trade VWAP but FAILS on small-trade VWAP, the
     strategy is NOT retail-tradable and the gate FAILS.

Gate FAILS otherwise. Failure = strategy ends, project pivots (operator
authorization required) or ends.

### 7.1 Threshold justifications, sample-size considerations, and risk
notes

**C1a threshold = 1.2**: ~80% of Le's posterior 95% CI lower bound at
>1mo politics (1.46 * 0.82). Conservative.

**C1b threshold = 1.0** (lower quartile): ensures > 75% of splits have
slope >= 1.0 (some compression detectable). If lower quartile drops
below 1.0, the regime is too thinly populated to underwrite a strategy.

**Small-trade slope collapse risk** (BLOCKING-fix note per critic
finding 3): Le's slope of 1.46-1.83 was fit on ALL trades. Trade-size
scale effect (Delta = 0.53 95% CI [0.29, 0.75]) implies small trades are
LESS compressed than large. The small-trade slope is structurally lower
than 1.65 by some fraction of 0.53. Worst-case: small-trade slope = 1.12,
implying ~1.9pp gross edge at YES = 0.30, BELOW C2's 2.04pp threshold and
WAY below the ~3.5pp needed for net positive after fees + slippage. In
this worst case the gate fails C2 and C5, which is the correct kill
signal. The methodology does NOT silently accept partial passes that
mask this collapse.

**C2 threshold = 2.04pp**: 2x Becker politics per-trade average. Becker
uses the same underlying Kalshi data as Le ([le-2026-crowd-wisdom.md](literature/le-2026-crowd-wisdom.md)
"Cross-references in the paper"); we cannot claim per-trade edge >>
Becker's aggregate. A 2x multiplier acknowledges sub-slicing while
respecting the aggregate.

**C3 threshold = 10/12 (binomial alpha = 0.019)**: with N=12 actual
walk-forward splits (see Section 5.1 update), 10/12 gives
`P(>= 10 of 12 | true edge = 0) = (C(12,10) + C(12,11) + C(12,12)) /
2^12 = 79/4096 = 0.0193`. Walk-forward correlation degrades effective
independence (consecutive splits share 150d of training); effective
false-acceptance is somewhat higher than 0.019 but well below 0.05. An
earlier draft of this methodology assumed N=17 splits and set C3 =
13/17 = 0.0245 alpha; the code-review milestone 1 discovered the actual
N is 12 and the threshold was recomputed pre-data to preserve
equivalent Type-I control.

**C5 threshold = both median AND mean net > 0**: median-only gate hides
news-event tail losses; mean-only gate can be dragged positive by single
outliers. Both > 0 is the genuinely-additive constraint that catches
adverse-selection tail loss AND average positive edge.

**Sample-size power calculation**: per-test-partition sample depends on
politics market density (estimate 30-100 eligible markets per partition
after Section 4 filters). Per-trade SD ~ 0.5 (binary outcome variance
bounded by p(1-p) ~ 0.25, SD of (outcome - p) ~ 0.5). Per-split SE on
mean net edge ~ 0.5 / sqrt(n_eligible). At n_eligible=50: SE ~ 7pp;
at n_eligible=200: SE ~ 3.5pp. Pooled across 12 splits (effective
independent ~ 7 due to walk-forward overlap), pooled SE on a 2pp true
edge is roughly 1.5-3pp, giving modest detection power. The pooled
bootstrap diagnostic (Section 6.4) provides a complementary higher-
power view that is not bottlenecked by per-split counts.

**Fee-schedule regime risk** (NICE-TO-HAVE per critic finding 10):
Becker documents that the 2024 sign flip was driven partly by Kalshi
imposing maker fees in April 2025 ([becker-2026-microstructure.md](literature/becker-2026-microstructure.md)
"The 2024 sign flip"). Any future fee-schedule change (Kalshi has
discretion) could re-flip the sign or rescale the maker advantage. Le's
trade-size scale effect may also flip if Kalshi alters fees in a way that
changes large-vs-small trader incentives. Phase 3 deployment must include
fee-schedule monitoring (alert on any Kalshi fee announcement).

## 8. Anti-leakage checklist (run at every analysis batch)

`scripts/phase_2/run_gate.py` emits these as assertions; failures block
the run.

- [ ] Every market in test set has resolution_time AFTER train_end +
      purge (14 days).
- [ ] Every market in test set has market_open_time AFTER train_end +
      purge (the new lifetime-straddle filter from Section 5.1).
- [ ] Every market in train set has resolution_time BEFORE train_end.
- [ ] VWAP windows use ONLY trades with timestamp <=
      resolution_time - 28 days.
- [ ] settle_outcome from Kalshi's official settlement, not third-party.
- [ ] No feature is computed using data with timestamp >=
      resolution_time.
- [ ] Isotonic / logistic calibrators are fit ONLY on the train
      partition; predict() only on test rows.
- [ ] Per-market slope is computed ONLY on the partition the market
      belongs to (no slope from test data leaks into train).
- [ ] is_federal_election_market tagging uses only metadata visible at
      market_open_time (no post-resolution information).
- [ ] Pooled bootstrap is computed on test-partition data ONLY (each
      sample's underlying market belongs to a test partition; train
      markets never enter the bootstrap).

## 9. What we will NOT do (also locked)

- We will NOT change the pass criteria after seeing initial results.
- We will NOT swap calibration model families (isotonic vs Platt vs
  beta) post-hoc.
- We will NOT tune the price band, the horizon window, the one-sided-
  flow threshold, the lifetime-straddle rule, or the election-tagging
  keywords after seeing results.
- We will NOT include the most recent 30 days in the corpus (2026-05-01+
  is out-of-time buffer).
- We will NOT relax filter thresholds to recover sample size. Per
  Section 2.2 and 3 the pre-committed options (widen window, drop
  markets, widen corpus by one month for election-audit) are the only
  fallbacks.
- We will NOT use any pre-2024-10-01 data.
- We will NOT re-open EC-1 or any weather strategy under the no-third-
  bite rule.

## 10. If the gate passes (Phase 3 commitment)

Phase 2 pass is NECESSARY-NOT-SUFFICIENT for Phase 3. If all five
criteria pass:

1. Live strategy design with maker-quoting bot. Strategy uses small-
   trade VWAP as fair-value reference, posts maker orders inside the
   bid-ask spread, respects mid-band + price-conditional one-sided-flow
   filters, drawdown breakers.
2. Critic pass on the live strategy design.
3. Two weeks paper trading on real Kalshi prod data, zero capital.
   Measure fill rate per plan-critic finding 9; this is the FIRST time
   fill rate is measured (backtest cannot measure it).
4. Paper P&L must match backtest expectations within +/- 2 SDs over
   200+ fills. Specifically: if backtest expected per-fill net edge is
   X pp +/- Y pp SD, paper must measure within X +/- 2 * Y / sqrt(N).
5. Per-month regime monitor: if fill rate falls below 30% OR realized
   P&L lags backtest by > 2 SDs OR Kalshi announces a fee-schedule
   change, pause and re-evaluate.
6. Operator explicit go-live approval required.
7. Deploy with $25 initial cap; $100 operator-authorized ceiling,
   enforced in `src/kalshi_bot/config.py`.

## 11. If the gate fails

Project Politics x H ends. No iterating on filter parameters. Honest
failure mode documented in `research/phase-2-results.md`. Operator
decides whether to pivot to Sports x Long-Horizon (runner-up per the
proposal) or end the project.

## 12. Change log

- 2026-05-23 09:00: Initial draft, pre-data. Plan-critic findings 1-9
  incorporated.
- 2026-05-23 15:00: Data pull discoveries during build_dataset, applied
  per pre-committed Section 2.2 and Section 3 options:
  - **Option A invoked (Section 3)**: median n_trades_in_window in the
    7-day [-35d, -28d] window is 14 across the 427 binary in-corpus markets
    with any in-window trades, which is below the methodology's >= 20
    threshold. Per pre-commitment, trades were refetched in the wider
    14-day [-42d, -28d] window. The 28-day pre-resolution margin is
    preserved. NOT a post-data tuning event - Option A was pre-committed.
  - **Kalshi historical/markets endpoint leak**: Kalshi's
    `/historical/markets?min_close_ts=...` returned ~23 markets with
    close_time before 2024-10-01 despite the filter. `build_dataset.py`
    now enforces the corpus window [2024-10-01, 2026-04-30] as a hard
    filter using the response's `close_time` field. This is a defect fix,
    not a methodology change.
  - **Binary filter takes a heavy cut**: of 7,733 markets in corpus and
    6,591 above the volume floor, only 816 (~12%) pass the binary
    (single-contract-per-event) filter. Most politics markets on Kalshi
    are multi-strike (e.g., KXFEDDECISION-26APR has 5+ rate-bucket
    contracts, KXSPEAKER has one contract per candidate). The
    methodology's binary-only locked filter holds; downstream impact is
    a smaller-than-anticipated sample.
- 2026-05-23 14:00: Code-review milestone 1 completed
  ([code-review-phase-2-milestone-1.md](code-review-phase-2-milestone-1.md)).
  Pre-data discoveries applied to keep the methodology in sync with the
  actual split count and to wire missing diagnostics:
  - BLOCKING: corpus + step parameters yield exactly 12 walk-forward
    splits, not "~17" as earlier draft stated. C3 threshold recomputed
    from 13/17 (alpha 0.0245) to 10/12 (alpha 0.0193) to preserve
    Type-I control. Section 5.1 and Section 7 C3 updated.
  - IMPORTANT: per-MARKET (per-series) slope distribution diagnostic
    (Section 6.5) wired into the gate output.
  - IMPORTANT: skipped-split counter surfaced in the gate result and
    report so silent sample-size failures are visible.
  - IMPORTANT: NaN one_sided_flow handled defensively (filter excludes
    rather than admits when flow is missing).
  - IMPORTANT: Section 8 anti-leakage checklist wired as runtime
    assertions in `scripts/phase_2/run_gate.py`.
- 2026-05-23 12:00: Methodology-critic review completed
  ([critic-methodology-phase-2.md](critic-methodology-phase-2.md)).
  Revisions applied:
  - BLOCKING #1 fixed: C3 threshold raised 9/17 -> 13/17.
  - BLOCKING #2 fixed: C1 now dual-clause (C1a median + C1b lower
    quartile).
  - BLOCKING #3 fixed: small-trade-slope-collapse risk documented in
    Section 7.1 with worst-case math.
  - IMPORTANT #4 fixed: Section 5.1 lifetime-straddle filter added.
  - IMPORTANT #5 fixed: Section 4 one-sided-flow filter is now price-
    conditional.
  - IMPORTANT #6 fixed: Section 6.6 election-composition reporting
    added.
  - IMPORTANT #7 fixed: Section 4 pre-commits the manual top-50 audit
    process with two pre-committed audit options.
  - NICE-TO-HAVE #8 added: Section 6.4 includes pooled-bootstrap
    diagnostic.
  - NICE-TO-HAVE #9 added: Section 1 and Section 10 explicitly flag
    Phase 2 pass as necessary-not-sufficient.
  - NICE-TO-HAVE #10 added: Section 7.1 fee-schedule regime risk note.

## Citations to literature (one-line each)

- Becker per-category gap table:
  [becker-2026-microstructure.md](literature/becker-2026-microstructure.md)
  "Per-category maker-taker gap"
- Becker 2024 sign flip and 27x volume surge:
  [becker-2026-microstructure.md](literature/becker-2026-microstructure.md)
  "The 2024 sign flip"
- Le politics slope 0.93 to 1.83 by horizon:
  [le-2026-crowd-wisdom.md](literature/le-2026-crowd-wisdom.md)
  "Domain-by-horizon trajectories"
- Le politics 95% CI 1.46-1.83 at >1mo:
  [le-2026-crowd-wisdom.md](literature/le-2026-crowd-wisdom.md)
  "Domain-by-horizon trajectories"
- Le politics 127-trade median per-market liquidity:
  [le-2026-crowd-wisdom.md](literature/le-2026-crowd-wisdom.md)
  "Per-domain breakdown on Kalshi"
- Le trade-size scale effect Delta = 0.53 CI [0.29, 0.75]:
  [le-2026-crowd-wisdom.md](literature/le-2026-crowd-wisdom.md)
  "Trade-size scale effect"
- Le four-component decomposition 87.3% variance:
  [le-2026-crowd-wisdom.md](literature/le-2026-crowd-wisdom.md)
  "The four components of calibration error"
- Bartlett single-name adverse selection + VPIN one-sided-flow:
  [bartlett-ohara-2026-adverse-selection.md](literature/bartlett-ohara-2026-adverse-selection.md)
  TL;DR items 2 and 6
- Bürgi 33% SD on >= 50c subpop:
  [burgi-deng-whelan-2025.md](literature/burgi-deng-whelan-2025.md)
  Section 6
- Bürgi bias-shrinkage trend (psi 0.041 to 0.021 by 2025):
  [burgi-deng-whelan-2025.md](literature/burgi-deng-whelan-2025.md)
  "Time-period trend (Table 9)"
- Phase 1.5/1.6 lesson on trading-window-swamps-model:
  [phase-1.5-methodology.md](phase-1.5-methodology.md) Section 10
- Plan-critic findings 1-9:
  [critic-plan-phase-2.md](critic-plan-phase-2.md)
- Methodology-critic findings (3 BLOCKING + 4 IMPORTANT + 3 NICE-TO-HAVE):
  [critic-methodology-phase-2.md](critic-methodology-phase-2.md)
