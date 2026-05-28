# Project Kalshi: Lessons Learned (Phase 1 + Phase 2 + Autonomous Run)

**Date:** 2026-05-23 evening
**Scope:** What Project Kalshi taught us about Kalshi quant strategy
development, methodology design, and AI-driven research workflows. Stays
valid regardless of the Sports x Long-Horizon gate verdict.

This doc preserves the meta-knowledge. The individual phase docs
preserve the specific evidence; this doc preserves the patterns.

## Methodology design lessons

### 1. The trading-window-swamps-model lesson (Phase 1.5 -> 1.6)

Phase 1.5 measured 9pp shoulder edge OOS using a VWAP window 60 min
before market close. Phase 1.6 measured 1.5pp using a VWAP window
[open+1h, open+13h]. The difference was not the model; it was that
Phase 1.5's window contained post-resolution information (KXHIGH
markets close AFTER NWS reports the daily high).

**The pattern**: when designing a backtest window for a maker-quote
strategy, the window must represent prices the bot could REALISTICALLY
HAVE TRADED AT. Post-resolution windows, late-day windows on settling
markets, and any window where future information has leaked - these
artifacts produce phantom edge that doesn't survive.

**Generalization**: any time you see backtest results that look too
good, the first hypothesis should be window leakage, not real edge.

### 2. The strategy-methodology compatibility lesson (Politics x H)

The Politics x H gate failed mechanically because the methodology's
lifetime-straddle filter (required test market open > train_end + purge)
was incompatible with the strategy's long-horizon thesis (target
lifetime >= 30 days). With 30-day test windows, only short-lifetime
markets could be in test, but the strategy targeted long-lifetime.

**The pattern**: the methodology critic recommended the straddle filter
without modeling the data shape. The recommendation was correct in
isolation (leakage prevention) but mechanically incompatible with the
strategy that the methodology was supposed to test. The gate failed
without ever testing the strategy.

**Generalization**: before locking a methodology, the methodology critic
should know the EXPECTED DATA SHAPE (lifetime distribution, sample
sizes per likely-split). Without this, critic-recommended fixes can
create incompatibilities. For Sports x Long-Horizon, the methodology
was DESIGNED with the data shape in mind (60d test windows, straddle
filter removed, MIN_TEST_SIZE reduced).

### 3. The C3 binomial-power lesson (Politics x H)

The original C3 ("9 of 17 splits show net edge > 0") had binomial null
alpha = 0.500 - a coin flip. Methodology critic raised to 13/17 (alpha
= 0.05). Code reviewer discovered the corpus actually yields 12 splits
not 17, and recomputed to 10/12 (alpha = 0.019).

For Sports x Long-Horizon at N = 6 splits, no integer threshold gives
alpha = 0.05 without either being overly strict (6/6 = 0.016 but any
one fail kills) or too permissive (4/6 = 0.34). The sports critic
recommended DEMOTING the per-split count to diagnostic and PROMOTING a
pooled-bootstrap CI lower bound as the actual gate.

**The pattern**: per-split count criteria are fragile to N. For small
N (< 15) they cannot achieve both meaningful alpha AND robustness to
walk-forward correlation. Pooled bootstrap on per-trade outcomes
scales naturally.

**Generalization**: for small-N walk-forward designs, prefer pooled
bootstrap to per-split counts.

### 4. The category sample-size lesson

Politics x H: 243 markets in 19-month corpus after all filters. 
Sports x Long-Horizon (estimated by critic): 150-400 markets.

Neither is comfortable for a 6-12 split walk-forward gate at
MIN_TEST_SIZE = 30-50 per partition. Kalshi's market universe outside
the dominant categories (single-game sports, near-resolution macro)
is sparser than the headline trade counts (Le's 4.9M politics trades,
43.2M sports) suggest. The TRADE counts are concentrated in a few
high-volume markets; per-MARKET counts are much lower.

**Generalization**: when sizing a backtest at a NEW category, estimate
both market count AND per-market volume distributions. Use the filtered
market count (post all locked filters) as the planning baseline.

### 5. The "no third bite" tension with mechanical failures

The methodology lock-in rule "no third bite" was designed for the case
where a strategy LOOKED PROMISING but failed criteria narrowly (Phase
1.5 ECE ratio 4.77 vs 5x required). It correctly prevented post-hoc
parameter tuning to push past the threshold.

But the rule was less clear about MECHANICAL FAILURE (where the gate
doesn't run at all). Politics x H's straddle-filter incompatibility
created a mechanical failure: zero tests, zero results, zero verdict.
The autonomous run's interpretation: the strategy itself ends per the
rule, but a CORRECTLY-DESIGNED methodology for a different strategy
(Sports x Long-Horizon) can proceed under the operator's "full
authority" grant.

**Generalization**: distinguish:
- Strategy failure (gate runs, criteria fail): no third bite, project ends.
- Methodology failure (gate doesn't run mechanically): document the
  failure, the methodology design needs revision for ANY similar
  strategy. Strategy-specific results are inconclusive.

## AI-research-workflow lessons

### 6. The plan / methodology / code critic sequence

Three critic spawns at three decision points caught real issues:

- Plan critic (post-proposal): 9 findings on Politics x H, including
  the slope-distribution-not-mean concern, the C2 4pp vs Becker 1.02pp
  inconsistency, and the trade-size scale effect.
- Methodology critic (post-lock): 3 BLOCKING + 4 IMPORTANT on Phase
  2; 3 BLOCKING + 5 IMPORTANT on Sports.
- Code reviewer (post-implementation): caught the unreachable C3
  threshold at N=12 (was set for assumed N=17).

Each critic found things the prior layer missed. The sequence is
load-bearing for honest research.

### 7. The "self-contained brief" cost

Sub-agents have no memory of the parent conversation. Each critic
prompt was 1000-2000 words of context (project history, methodology,
literature). This is expensive in tokens but necessary for honest
review. Shorter prompts produced shallower reviews in early Phase 1.

**Generalization**: when delegating analysis to a sub-agent, the brief
length should match the complexity of the question. Single-point
fact-checks can be terse; methodology reviews must be context-heavy.

### 8. The autonomous-run authorization shape

The operator granted "full authority" for an 8-hour autonomous run.
The autonomous Claude (this context) interpreted this as:
- Make and document strategy pivots (Politics -> Sports).
- Apply critic recommendations autonomously.
- Build Phase 3 scaffolding speculatively.
- Do NOT deploy live capital (config gate enforces).

The "no third bite" rule was honored at the strategy level (Politics x
H ended), but a NEW strategy with a different methodology was allowed
to proceed. This is documented in the autonomous log for operator
review on wake-up.

**Generalization**: autonomous mandates should explicitly enumerate
what's authorized and what's NOT. The operator's "full authority" was
broad but capital deployment was still gated by code config, which is
the right pattern.

## Strategy-specific findings to remember

### 9. Politics has the smallest non-Finance per-trade gap

Per Becker, politics gap is 1.02pp (smaller than weather's 2.57pp).
Combined with the 79-day median lifetime making it hard to backtest in
short test windows, politics is structurally hard for a retail
maker-quote strategy at Kalshi's current scale.

### 10. Multi-strike politics events are the norm

Of 7,733 in-corpus politics markets, only 816 (~11%) pass the binary
(single-contract-per-event) filter. Most politics markets are
multi-strike: 5-candidate primaries, 7-rate-bucket FOMC, etc. The
binary-only filter is a heavy cut.

### 11. Long-horizon politics liquidity is thin

Of 816 binary in-corpus politics markets, only 427 have any trades in
a 7-day pre-resolution window 28 days from close. Of those, only 179
have >= 20 trades. The filter funnel is severe.

### 12. Kalshi historical endpoint can return out-of-window markets

The `/historical/markets?min_close_ts=...` parameter is unreliable;
23 of our 10,506 returned markets had close_time before our requested
2024-10-01. Always re-filter at the DataFrame level.

## What we DON'T yet know (open questions)

1. Whether long-horizon sports markets have enough liquidity for a
   robust 6-split walk-forward gate. Sports markets fetch in progress
   at autonomous-run time of writing.
2. Whether maker fills are achievable against institutional MMs
   (Jump/SIG) on sports markets. Cannot be tested in historical
   trade data; requires Phase 3 paper trading.
3. Whether the small-trade VWAP slope on sports actually exceeds 1.2
   (C1a gate). Le's all-trade slope of 1.74 implies the small-trade
   slope could fall to 1.12-1.39 due to the trade-size scale effect.
4. Whether Polymarket cross-validation would distinguish "real edge"
   from "Kalshi-specific microstructure artifact" for any strategy
   that passes. Not yet implemented.

## What we should NOT try

Based on Phase 1 + Phase 2 + autonomous-run evidence:

- DO NOT re-open EC-1 weather (Round 1 killed, no third bite).
- DO NOT re-open Politics x H without methodology redesign (Round 2
  mechanically failed; redesign would need much larger test windows
  AND replacement of the lifetime-straddle filter).
- DO NOT attempt cross-platform arbitrage with Polymarket at retail
  scale (Clinton & Huang showed 78% execution failure at low volume).
- DO NOT attempt sub-daily crypto strategies (HFT-dominated per Le).
- DO NOT attempt macro/FOMC directional strategies (Fed paper says
  these are pro-priced, no retail edge).

## Strategies still worth exploring (post-autonomous-run, with operator authorization)

If both Politics x H and Sports x Long-Horizon are exhausted:

- **Bürgi >=50c subpopulation**: cross-category, +2.6% gross pre-fees,
  33% SD. Not horizon-specific. Sample limited by per-category mid-band
  density.
- **Bartlett behavioral surplus on single-name markets**: requires a
  market-classification model (which markets attract YES-overbet behavior?).
- **Manipulation reversal trades (Rasooly & Rozzi)**: 60+ day
  persistence; sparse manipulation events.
- **Calibration recalibration as model-based predictor with shorter
  trading windows**: revisit short-horizon markets with the per-market
  slope distribution as the primary signal rather than the per-partition
  median.

Each of these requires its own methodology design with the data shape
of the target category in mind (Lesson 2 + Lesson 4).

## The single biggest takeaway

**Methodology must be designed AROUND the data shape, not against it.**

Phase 1 (weather, ~24h lifetime markets) tolerated tight test windows
and lifetime-straddle filters. Phase 2 (politics, ~79d lifetime
markets) did not - and the methodology critic's recommendation
inherited from Phase 1's pattern killed the gate mechanically. Sports
x Long-Horizon was DESIGNED for long lifetimes (60d test windows,
straddle removed, MIN_TEST_SIZE reduced). Its verdict will be honest
either way.

For any future strategy: characterize the data BEFORE locking the
methodology. The methodology critic should know the lifetime
distribution, market count, and trade-density estimates.
