# Backup Strategy Proposal: Sports × Long-Horizon Maker-Quote

**Author:** Round 2 strategy-selection context (autonomous run)
**Date:** 2026-05-23
**Status:** PRE-DRAFT. Only escalated to active strategy if Politics x H
fails the Phase 2 gate AND operator explicitly authorizes (or implicitly
authorizes via the "full authority" + "validate the model and sector"
grant in the 2026-05-23 evening message).

This document fills the 6-question decision framework from
[STRATEGY_BRIEF.md](../STRATEGY_BRIEF.md) for the matrix's runner-up
candidate. Kept here for fast pivot. Pre-data; methodology lock-in would
follow in a separate doc if activated.

## Mission delta from Politics x H

Same maker-quote thesis (post-Oct-2024 makers win on Kalshi per Becker;
mechanism is order-flow accommodation per Becker; behavioral surplus per
Bartlett). Different category. Different empirical risks.

## Why Sports x Long-Horizon is the runner-up

From [strategy-comparison.md](strategy-comparison.md):

| Metric | Politics | Sports | Source |
|---|---|---|---|
| Per-trade gross maker-taker gap (full-sample) | 1.02pp | 2.23pp | Becker "Per-category maker-taker gap" |
| Markets in 2025 sample | 6,609 | 55,637 | Le "Per-domain breakdown" |
| Trades in 2025 sample | 4.9M | 43.2M (66.7%) | Le |
| Long-horizon slope (>1mo) | 1.83 | 1.74 | Le "Domain-by-horizon trajectories" |
| Short-horizon slope (<1h) | 0.93 | 0.90-1.10 | Le |
| Per-market median trades (lifetime) | 127 | 76 | Le |

Sports has 2.2x larger per-trade gap and 8.8x more volume than politics.
Long-horizon sports slope (1.74) is comparable to long-horizon politics
(1.83). The compression mechanism is documented in both, but sports'
larger gap suggests more headroom after fees.

## The six-question framework (provisional answers)

### Q1. Which (category, strategy) pair?

**Sports x Long-Horizon Maker-Quote.** Maker-side bids on Kalshi sports
markets that are >= 30 days from resolution (futures-style:
championship winners, season totals, season-long awards). Mid-band
price [0.20, 0.45] ∪ [0.55, 0.80]. Same calibration-regime exploitation
as Politics x H, applied to sports.

Specifically EXCLUDE single-game markets resolving within 24-48h
(these are where Jump/Susquehanna sit on the inside and where Bartlett's
single-name adverse selection is sharpest).

### Q2. Why does it survive fees?

Round-trip maker fee unchanged from Politics: ~2pp across all tradable
price bands.

Sports long-horizon slope (Le): 1.74. At market YES = 0.30, slope = 1.74:
logit(market) = -0.847, logit(truth) = -1.474, truth = sigmoid(-1.474)
= 0.186. Gross edge per contract (maker NO at $0.70): expected (1 - 0.186)
- 0.70 = 0.114 = 11.4pp gross on cost basis. After 2pp round-trip fee +
1.5pp slippage = 7.9pp net.

But this is the slice-average; Becker's full-sample sports gross is
2.23pp per-trade. A focused long-horizon-mid-band slice plausibly
delivers 3-6pp net.

### Q3. Why does it survive the 2024 sign flip?

The mechanism is documented in post-2024 Becker (same dataset Le uses).
Sports volume EXPLODED post-Oct-2024 (driver of the 27x volume surge).
Post-flip economics for sports are the dominant share of Becker's
2.23pp average. No regime change needed for thesis to hold.

### Q4. Why does it survive variance?

Bürgi's 33% per-trade SD applies cross-category to the >=50c
subpopulation. Sports markets have more idiosyncratic noise (game
outcomes are largely random conditional on prior) but our slice (long-
horizon futures) is closer to a binomial mean than single-game spreads.
SD assumption: ~33% holds.

Sizing math identical to Politics x H: $1 per fill, max 5 concurrent,
drawdown breakers at 5/10/15/25% of bankroll.

### Q5. What's the OOS gate?

Locked methodology TBD (would write
`research/sports-longhorizon-methodology.md` if activated). Same
structural shape as Phase 2 methodology:

- **Dataset:** settled Kalshi sports markets in [2024-10-01, 2026-04-30].
  Exclude pre-flip data.
- **Filters:**
  - Long-horizon: market lifetime > 60 days (futures-style, NOT single-game)
  - Binary contracts only (game outcomes are typically binary; futures
    can be multi-strike, handle case-by-case)
  - Min 50 lifetime trades; min 20 trades in trading window
- **Trading window:** [resolution - 35d, resolution - 28d] (or 14d
  per Option A if needed)
- **Splits:** Walk-forward 180d/30d/14d-purge/30d-step + leave-one-event-
  out (probably leave-one-major-league-out: NFL, NBA, MLB, NHL, NCAA)
- **Five criteria:** identical shape to Phase 2 (C1a, C1b, C2, C3, C4,
  C5). C3 threshold: TBD based on actual split count.

### Q6. What does the critic say?

To be addressed via critic spawn AFTER methodology lock-in if activated.

## Key risks specific to Sports

1. **Jump/Susquehanna competition**: institutional MMs are heavily active
   in sports. Per Bürgi "Why hasn't the bias been arbitraged away", top-
   of-book on liquid markets is dominated by pros at $33 with retail
   queued at $3,336. Our $1 maker orders may sit unfilled.
2. **Adverse selection in single-name markets** (Bartlett): one-sided
   informed flow predicts maker losses. The "exclude single-game markets"
   rule above is the primary defense. Long-horizon futures have lower
   information asymmetry than next-game outcomes.
3. **Multi-strike sports markets** (futures with multiple champion
   candidates): same binary-only filter as Politics x H. May cut sample
   significantly.
4. **League seasonality**: NFL season Sept-Feb, NBA Oct-June, MLB Apr-
   Oct. The corpus may be uneven across leagues; leave-one-league-out
   accommodates this but reduces per-fold sample.

## Liquidity check (CANNOT verify without data)

The proposal author cannot verify per-market liquidity of long-horizon
sports futures from the literature alone. This is a known weakness
flagged by the Phase 2 plan-critic. If activated, the FIRST step is to
discover the population of long-horizon sports markets and verify there
are enough binary-only ones to support a 12-split gate (~500-1000
markets target).

If long-horizon sports binary markets are < 200, the strategy ends at
discovery; the broader sports universe is single-game-dominated and not
in scope for this strategy.

## What this proposal does NOT do

- It does NOT propose competing with Jump/Susquehanna on tight short-
  horizon markets. The long-horizon filter is the differentiator.
- It does NOT propose hedging across leagues or seasons.
- It does NOT propose intraday rebalancing. Buy-to-hold-to-settlement
  same as Politics x H.

## Path forward if activated

1. Operator authorization OR autonomous-mode pivot (documented in
   autonomous-log).
2. Write `research/sports-longhorizon-methodology.md` with locked C1-C5
   thresholds.
3. Plan-critic on proposal (this doc).
4. Methodology-critic on methodology lock.
5. Build sports discovery + fetcher (reuse politics scripts as
   templates).
6. Code review milestone 1.
7. Pull sports data.
8. Build dataset.
9. Run gate.
10. Honor verdict.

The ~9 hour pipeline can be compressed if we reuse the existing engineering
scaffolding (the politics scripts are 90% category-agnostic).
