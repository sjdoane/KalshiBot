# Sports x Long-Horizon: Methodology Lock-In (Pre-Data)

**Strategy:** Sports x Long-Horizon Maker-Quote per
[sports-longhorizon-proposal.md](sports-longhorizon-proposal.md). Apply
Le's compression-slope thesis to long-horizon sports markets (futures,
season totals, championship winners) where the regime is documented.

**Author:** Round 2 autonomous-execution context (operator-asleep)
**Lock date:** 2026-05-23 (post-Politics-x-H mechanical fail)
**Status:** LOCKED before any sports data is pulled. Any change after
the first analysis run must be flagged in Section 12 change log.

**Provenance:** Pivot from Politics x H, which failed mechanically at
2026-05-23 with all 12 walk-forward splits skipped due to test
partitions having n=0 markets (see
[phase-2-results.md](phase-2-results.md)). The lifetime-straddle filter
(politics methodology Section 5.1 IMPORTANT fix) was incompatible with
the long-horizon strategy: it required test market lifetime < test
window length (30 days), but politics median lifetime is 79 days. This
methodology revises the split design to accommodate long-horizon sports
markets while preserving leakage controls in a different form.

Operator authorization for this pivot: 2026-05-23 evening message
("full authority" + "validate the model and sector" + "mostly set up
to start setting up live trading"). Documented in
[phase-2-autonomous-log.md](phase-2-autonomous-log.md) Entry 5.

This document is structured to mirror
[phase-2-methodology.md](phase-2-methodology.md) so the operator can
diff the two. The differences from Phase 2 are flagged with "DELTA"
markers in each section.

## 1. The question we are answering

Does the chronically-compressed calibration regime that Le 2026 documents
for long-horizon (>1mo) Kalshi sports markets (slope = 1.74,
[le-2026-crowd-wisdom.md](literature/le-2026-crowd-wisdom.md)
"Domain-by-horizon trajectories") produce a positive net-edge maker-quote
opportunity for a $25 retail account AT REALISTIC FILL PRICES, AFTER:

- Round-trip maker fees (Kalshi April 2025+ schedule)
- 1.5pp slippage allowance for residential retail latency
- Adverse selection from Jump/Susquehanna institutional MMs
- Small-trade VWAP (verifying retail-tradable fill prices, not large-
  trade compression we cannot capture)

**DELTA from Phase 2:** the adverse-selection concern is sharper for
sports (Jump and Susquehanna are actively making sports books). The
long-horizon filter (lifetime >= 60 days) is the primary defense.

If yes, Phase 3 = live strategy design + paper trading. If no, the
project ends per the no-third-bite rule.

## 2. Data we will pull (codified now)

### 2.1 Series discovery

Source: Kalshi `/series` endpoint, filter for category = "Sports".
Captured to `data/sports/sports_series_index.json`.

**DELTA from Phase 2:** different category filter, different output path.

### 2.2 Market filter

- Status: settled.
- Resolution date in [2024-10-01, 2026-04-30].
- Binary contracts only (`contract_type = "regular"`; events with 1
  contract).
- **DELTA: long-horizon filter**: `market_close_time - market_open_time
  >= 30 days`. Matches Le's documented >1mo horizon bin
  ([le-2026-crowd-wisdom.md](literature/le-2026-crowd-wisdom.md)
  "Domain-by-horizon trajectories" with slope 1.74). REVISED from
  60d per methodology-critic finding 8: 30d preserves literature
  alignment AND excludes single-game markets (which have ~1-7 day
  lifetimes).
- Minimum lifetime trades >= 50.
- Minimum trades in trading window >= 20.

### 2.3 Why 2024-10-01 start

Same as Phase 2: post-flip (Becker 2024 sign flip), excludes pre-flip
data.

### 2.4 Per-market features captured (same schema as Phase 2)

ticker, series_ticker, event_ticker, market_open_time,
market_close_time, outcome, mid_price_at_T_small, mid_price_at_T_all,
n_trades_in_window, n_small_trades_in_window, one_sided_flow_pct,
is_federal_election_market (will be False for almost all sports),
is_binary_market.

**DELTA from Phase 2:** the federal-election tag is replaced by a
LEAGUE tag (NFL, NBA, MLB, NHL, NCAA, MLS, PGA, F1, BOXING, ...) for the
leave-one-league-out check.

## 3. Trading window (locked)

Same as Phase 2: trade-VWAP over `[resolution_time - 35d, resolution_time
- 28d]`. Pre-committed Option A widens to 14-day window if median trades
< 20.

Two VWAPs (all-trade and small-trade <= 10 contracts) per the
trade-size scale concern. Gate must pass on small-trade VWAP.

## 4. Market filters (locked)

- **Mid-band price filter**: small-trade VWAP in [0.20, 0.45] union
  [0.55, 0.80].
- **Price-conditional one-sided-flow filter**: exclude if
  `one_sided_flow_pct > 0.65` AND small-trade VWAP in [0.30, 0.70].
  Outside narrow band, KEEP.
- **Per-market minimum 20 trades in window**.
- **DELTA: League diversity**: at least 30% of markets in BOTH train
  AND test partitions must be NON-NFL (NFL is the largest sport on
  Kalshi and could dominate the calibration fit if not balanced).
  Implementation: tag markets by league via ticker / event keyword tagger
  in `src/kalshi_bot/data/sports.py`.

## 5. Split design (locked)

**DELTA from Phase 2:** larger test window to accommodate long-horizon
market lifetimes; lifetime-straddle filter REMOVED with documented
residual leakage trade-off.

### 5.1 Walk-forward time splits

Parameters:

- train_window = 180 days
- **test_window = 60 days (was 30 days in Phase 2)**
- purge = 14 days
- step = 60 days

With the 2024-10-01 to 2026-04-30 corpus (577 days):
splits = floor((577 - 180 - 14 - 60) / 60) + 1 = floor(323 / 60) + 1 =
5 + 1 = 6 splits.

Each split: 180d train / 14d purge / 60d test.

**Lifetime-straddle filter REMOVED:** test markets are assigned by
`close_time in [test_start, test_end]` only. There is NO requirement on
`market_open_time`. Markets with long lifetimes that span train and
test periods ARE in test.

**CORRECTED claim per methodology-critic finding 3 (BLOCKING)**: the
leave-one-league-out check does NOT compensate for news-period leakage.
LOCO catches cross-LEAGUE generalization (NFL-only injury cluster).
The news-period leakage path runs through SHARED TIME (e.g., a Nov
2025 macro shock hits NFL futures and NBA futures concurrently); LOCO
is structurally orthogonal to this. The residual leakage is ACCEPTED
as the unavoidable cost of testability for long-horizon strategies.

**MIN_TEST_SIZE_PER_SPLIT = 30** (pre-committed, methodology-critic
finding 2 BLOCKING). Splits with fewer than 30 markets in test are
SKIPPED and excluded from C3 denominator. The Phase 2 default (50) was
calibrated for politics; sports' smaller corpus warrants a lower
threshold to avoid trivial skips, but 30 is the floor below which the
per-split logistic slope fit becomes too noisy to interpret.

**Resolution-time-purge sensitivity check** (methodology-critic finding
4 IMPORTANT): in addition to the locked split, also report results
under the stricter constraint that train markets must RESOLVE before
test_start (not merely OPEN before train_end). If the gate passes the
locked split but FAILS the resolution-time-purge variant, the apparent
edge is plausibly leakage-driven.

Rationale for removing straddle filter: Phase 2 demonstrated that the
lifetime-straddle filter is mechanically incompatible with long-horizon
strategies (n_test=0 for all 12 splits). We accept the residual leakage
in exchange for being able to run the test at all, AND mitigate via
the resolution-time-purge sensitivity check above.

### 5.2 Leave-one-league-out (secondary)

**REVISED per methodology-critic finding 6 (IMPORTANT):** threshold
reduced from 100 markets to **50 markets per league** to capture more
leagues. If N (number of leagues with >= 50 markets) is < 3, **C4
FAILS** for insufficient cross-sport sample (was previously a "2-of-2
fallback"; the fallback was too permissive).

For each major league with >= 50 markets in the corpus:

- Hold out all markets in that league as test.
- Train on all other leagues.

Expected leagues: NFL, NBA, MLB, NHL, NCAA-FB, NCAA-BB. Maybe MLS,
PGA, F1, Boxing depending on volume.

The check validates that the calibration regime generalizes across
SPORTS, not just the dominant league. Note (per methodology-critic
finding 3): LOCO does NOT compensate for news-period leakage; it only
catches league-specific shocks.

## 6. Metrics (locked)

Same as Phase 2 Section 6 (primary slope, ECE, per-trade gross/net
edge, pooled bootstrap, per-series slope distribution, league
composition). Implementation in `src/kalshi_bot/analysis/gate_phase2.py`
is mostly reusable; only the event windows replaced with leagues.

## 7. Pass criteria (locked, REVISED per methodology critic)

**DELTAS from Phase 2 + delta from initial sports draft:** C3 demoted
to diagnostic, replaced with pooled-bootstrap gate per critic finding
1 (BLOCKING). C2 reverted to 2.23pp unmodified per critic finding 7
(IMPORTANT).

1. **C1a**: median per-partition logistic slope on test partition
   (small-trade VWAP) >= 1.2. Same as Phase 2. Splits below
   MIN_TEST_SIZE_PER_SPLIT = 30 excluded from this median.
2. **C1b**: per-partition slope lower-quartile (25th pct of partition
   slopes) >= 1.0. Same as Phase 2. Same skip rule as C1a.
3. **C2**: median per-trade gross edge on mid-band strategy-eligible
   markets >= **2.23pp (1x Becker sports, NOT 2x)**. **REVISED per
   critic finding 7**: Becker's 2.23pp full-sample gap mixes high-
   adverse-selection single-game markets with futures. The long-horizon
   slice removes some adverse selection BUT also removes behavioral
   surplus (which concentrates in single-game YES longshots per Becker
   TL;DR item 4). Net effect is unknown; setting C2 at 1x Becker is
   the conservative honest choice.
4. **C3 (revised per critic finding 1, BLOCKING)**: pooled mean
   per-trade net edge across all eligible test partitions has
   bootstrap 95% CI lower bound > 0pp on small-trade VWAP. The
   bootstrap uses 5000 resamples and seed 42 (deterministic). Skipped
   per-split count is reported as diagnostic, not gate.
   - Rationale: at N=6 splits with walk-forward correlation (180d
     train / 60d step = 67% overlap), effective independent N is ~4-5.
     The 5/6 binomial gate (alpha = 0.109 nominal) inflates to
     effective alpha 0.15-0.20. Pooled bootstrap sidesteps per-split
     correlation by computing SE on concatenated test data.
5. **C4 (leagues-based generalization, REVISED per critic finding 6)**:
   if N (number of leagues with >= 50 markets) >= 3, require >= 3 of N
   leagues to show median net edge > 0. If N < 3, **C4 FAILS** for
   insufficient cross-sport sample.
6. **C5**: BOTH median AND mean per-trade net edge > 0pp across all
   test partitions concatenated, with maker fees AND 1.5pp slippage,
   on small-trade VWAP. If C5 passes on all-trade VWAP but FAILS on
   small-trade VWAP, the strategy is NOT retail-tradable and gate FAILS.

**Sensitivity check (NOT gate)**: re-run criteria under resolution-
time-purge variant. If the pooled mean edge collapses, leakage
suspected. Report results explicitly.

**Single-name vs broad-based segment-report (per critic finding 5)**:
tag each market by parent-event sibling-count (single-name = 1
contract under event; broad-based = >= 5 contracts under event).
Report C3-equivalent (pooled mean net) separately per segment. Do NOT
exclude single-name; segment-report prevents silent overweighting of
high-adverse-selection regime.

### 7.1 Threshold justifications and risk notes

**C1a, C1b**: same as Phase 2.

**C2 = 4.46pp**: 2x Becker sports gap. Sports has 9x the volume of
politics, so even thin per-trade slices have larger absolute liquidity.
The 2x multiplier matches Phase 2 logic.

**C3 = 5/6 (alpha = 0.109)**: trade-off acknowledged. The pooled
bootstrap diagnostic (Section 6.4) is the higher-power complement; it
is informational, not gate.

**Sample-size power**: with ~600 markets in sports corpus estimate and
6 splits, per-test ~100 markets. After Section 4 filters, perhaps 30-
50 eligible. Per-trade SD ~0.5, per-split SE on mean net edge ~0.07
(50 sample). For a true 4pp edge, single-split power ~Phi(0.04/0.07) =
0.72. Across 6 splits, the pooled mean has SE ~0.5 / sqrt(300) ~ 3pp,
power to detect 4pp ~ 0.7. The gate is appropriately powered for the
size of edge we expect IF the data shape matches estimates.

**Removed lifetime-straddle filter**: residual leakage risk. The
isotonic fit on train can absorb news-period joint structure that also
affects test market prices. Mitigation: leave-one-league-out checks
cross-sport generalization. Document explicitly in the results report.

**Jump/Susquehanna competition risk**: sports markets are dominated by
institutional MMs (per Bürgi "Why hasn't the bias been arbitraged
away"). Our $1 maker orders may not get filled because pros sit on the
inside. This is UNTESTED in historical trade data; Phase 3 paper
trading is the first measurement.

## 8. Anti-leakage checklist

Same as Phase 2 Section 8, with the lifetime-straddle item removed.
The 9 remaining checks are:

- [ ] Every market in test set has resolution_time in [test_start,
      test_end].
- [ ] Every market in train set has resolution_time BEFORE train_end.
- [ ] VWAP windows use ONLY trades with timestamp <=
      resolution_time - 28 days.
- [ ] settle_outcome from Kalshi official settlement.
- [ ] No feature is computed using data with timestamp >=
      resolution_time.
- [ ] Isotonic / logistic fit ONLY on train partition.
- [ ] Per-series slope computed only within the partition.
- [ ] is_federal_election / league tagging uses only metadata visible
      at market_open_time.
- [ ] Pooled bootstrap on test-partition data only.

## 9. What we will NOT do

Same as Phase 2 Section 9, plus:

- We will NOT pivot to a SHORT-horizon sports strategy if this gate
  fails. The thesis depends on Le's long-horizon compression. Short-
  horizon sports is well-calibrated (slope ~0.90-1.10) per Le.
- We will NOT include single-game sports markets even if they're
  binary. The long-horizon filter (lifetime >= 60d) is the strategy.

## 10. If the gate passes

Phase 3 commitment identical to Phase 2 Section 10. The Phase 3 design
doc ([phase-3-design.md](phase-3-design.md)) is category-agnostic and
applies to sports with the strategy module re-parameterized.

## 11. If the gate fails

Project ends. The autonomous-run mandate to "validate the model and
sector" will have honestly found that the compression-maker thesis
cannot be cleanly tested on Kalshi at retail scale. Report this
finding in `research/sports-results.md` and `phase-2-autonomous-log.md`.
Operator decides next step on wake-up: end the project, or authorize a
fundamentally different thesis.

## 12. Change log

- 2026-05-23 17:00: Initial draft. Pivot from Politics x H gate
  mechanical fail. Methodology design delta: removed lifetime-straddle
  filter, increased test window to 60d, replaced event windows with
  league-out check.
- 2026-05-23 18:00: Methodology-critic review completed
  ([critic-methodology-sports.md](critic-methodology-sports.md)).
  Three BLOCKING + five IMPORTANT + two NICE-TO-HAVE items. Applied:
  - BLOCKING 1: C3 demoted to diagnostic, replaced with pooled
    bootstrap 95% CI lower bound > 0 gate. Section 7 C3.
  - BLOCKING 2: MIN_TEST_SIZE_PER_SPLIT = 30 pre-committed. Section
    5.1.
  - BLOCKING 3: Corrected "LOCO compensates" framing in Section 5.1.
  - IMPORTANT 4: Resolution-time-purge sensitivity check added. 5.1.
  - IMPORTANT 5: Single-name vs broad-based segment-report added. 7.
  - IMPORTANT 6: LOCO threshold reduced 100 -> 50, fallback removed.
    Section 5.2.
  - IMPORTANT 7: C2 reverted to 1x Becker (2.23pp), not 2x. Section
    7.
  - IMPORTANT 8: Long-horizon filter reduced 60d -> 30d to match
    Le's >1mo bin. Section 2.2.
  - NICE-TO-HAVE 9, 10: deferred to post-data follow-ups.

## Citations to literature

- Becker sports per-category gap 2.23pp:
  [becker-2026-microstructure.md](literature/becker-2026-microstructure.md)
  "Per-category maker-taker gap"
- Le sports long-horizon slope 1.74 at >1mo:
  [le-2026-crowd-wisdom.md](literature/le-2026-crowd-wisdom.md)
  "Domain-by-horizon trajectories"
- Le sports trades volume 43.2M (66.7% of Kalshi total):
  [le-2026-crowd-wisdom.md](literature/le-2026-crowd-wisdom.md)
  "Per-domain breakdown on Kalshi"
- Bartlett single-name adverse selection in single-game markets:
  [bartlett-ohara-2026-adverse-selection.md](literature/bartlett-ohara-2026-adverse-selection.md)
  TL;DR items 2 and 6
- Bürgi Jump/Susquehanna competition note:
  [burgi-deng-whelan-2025.md](literature/burgi-deng-whelan-2025.md)
  "Why hasn't the bias been arbitraged away" item 1
- Phase 2 mechanical fail (justifies methodology design delta):
  [phase-2-results.md](phase-2-results.md)
- Operator authorization for pivot:
  [phase-2-autonomous-log.md](phase-2-autonomous-log.md) Entry 5
