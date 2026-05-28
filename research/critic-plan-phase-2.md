# Phase 2 Plan Critic: Politics x H Maker-Quote Proposal

**Date:** 2026-05-23
**Author:** Plan-Critic sub-agent
**Scope:** Adversarial review of [phase-2-proposal.md](phase-2-proposal.md)
before methodology lock-in.

## Executive summary

The Politics x H proposal is conceptually defensible (Le's slope > 1
finding is real; Bartlett's behavioral-surplus mechanism is plausible)
but **needs substantial revision before methodology lock-in**. Three
load-bearing assumptions are softer than the proposal treats them; the
C1 gate threshold measures the wrong thing for a compression regime;
and the proposal does not address adverse selection from informed
political traders, which Bartlett identifies as the dominant cost in
single-name markets. The operator should require the nine concrete
changes in Section 5 before authoring phase-2-methodology.md.

## 1. Top three load-bearing risks

### Risk 1: Le's posterior MEAN slope is not a per-market trading signal

**Quoted assumption (proposal Q2):**
> "For politics at long horizons, slope = 1.83 (Table 2 of Le 2026)
> [...] Expected gross P&L per share: $0.825 - $0.70 = $0.125 =
> 12.5pp on cost."

The proposal pins headline edge math on slope = 1.83 then admits in
a caveat that "individual markets vary; some will have slope ~1.0
(already calibrated) and some > 2.0." Dismissed with "OR that the
average across many bets captures the mean edge." That OR is doing
enormous work.

**Counter-evidence (le-2026-crowd-wisdom.md "The four components of
calibration error" table):** Le decomposes calibration error into
four additive components. Universal horizon effect explains only
30.2% of variance; domain-by-horizon interactions add 26.0%;
structural biases and trade-size scale effect add 31.1%. The 1.83
figure is the summed effect at one horizon bin for one domain, not a
per-market predictor. Le's posterior 95% CI is 1.46-1.83 (proposal
Q3), implying posterior MEAN closer to ~1.65. The proposal uses the
upper-CI endpoint, inflating implied edge by ~30%.

Recomputing with slope = 1.65 at YES = 0.30: logit(0.30) = -0.847,
logit(truth) = 1.65 * -0.847 = -1.398, truth = sigmoid(-1.398) =
0.198 (not 0.175). Maker NO gross edge: (1 - 0.198) - 0.70 = 0.102,
or 10.2pp on cost. Still tradable, smaller cushion, still posterior
MEAN.

**Recommended test:** phase-2-methodology.md must measure the
EMPIRICAL distribution of per-market calibration slopes on the
training partition. Gate should require the LOWER QUARTILE of slopes
to be >= 1.2 (not just the median). Otherwise we select markets with
positive edge in train but cannot tell which will have positive edge
in test.

### Risk 2: Becker's 1.02pp politics gap is the relevant ceiling, not 12.5pp

**Quoted assumption (proposal Q2):**
> "This is far above the 1.02pp Becker average for politics [...] the
> targeted slice (long-horizon, mid-band) has a higher concentration
> of mispricing."

Asserted, not derived.

**Counter-evidence (becker-2026-microstructure.md "Per-category
maker-taker gap" + le-2026-crowd-wisdom.md "Cross-references in the
paper"):** Le and Becker use the SAME Kalshi dataset (Le: "uses
Becker [6]'s pre-collected dataset"). The same trades that produce
Le's slope = 1.83 produce Becker's 1.02pp gap. The proposal cannot
use Le's slope to justify edge MUCH larger than Becker's measured
per-trade return on the same data.

Becker's 1.02pp is on 4.9M politics trades across all horizons.
Becker's "The 2024 sign flip" shows much of this volume is post-flip
election-cycle long-horizon, so the targeted slice is NOT a small
unrepresentative subset. The 12.5pp number coexists with Becker's
1.02pp only if (a) the slice is a tiny minority of Becker's politics
volume, (b) Becker is wrong, or (c) the slope > 1 mechanism does not
produce per-trade returns matching the back-of-envelope math.

**Recommended test:** New C2: "median per-trade gross edge on the
targeted slice >= 2x the Becker politics population average, i.e.,
>= 2.04pp gross." A 2x multiplier is defensible because we select a
sub-slice; a 4pp threshold asserts the slice carries the bulk of
total politics bias, contradicting the population average.

### Risk 3: 7-day VWAP window at [-35d, -28d] is not validated as tradable

**Quoted assumption (proposal Q5):**
> "Trading window: for each market, simulated fill at VWAP of trades
> in [resolution - 35 days, resolution - 28 days]."

Choice of trading window swamps choice of model (Phase 1.5 vs 1.6
lesson, phase-1.5-methodology.md Section 10 change log).

**Counter-evidence (le-2026-crowd-wisdom.md "Per-domain breakdown on
Kalshi"):** Politics has 6,609 markets and 4.9M trades, median 127
trades per market LIFETIME. A 7-day window at the 28-35 day mark
covers ~5-7% of a typical market's lifetime. If volume concentrates
near close (Becker), the window may contain only 6-15 trades for the
median market. A VWAP on 6-15 trades is noisy and can be dominated
by a single large trade.

Compounding: Le's trade-size scale effect documents that LARGE trades
(>100 contracts) in Kalshi politics are MORE compressed than small
trades (Delta = 0.53, 95% CI [0.29, 0.75];
le-2026-crowd-wisdom.md "Trade-size scale effect"). A $1 retail order
is on the opposite end. If VWAP is dominated by large-trade
compression but our orders fill against small-trade flow, we measure
one regime and trade in another.

**Recommended test:** phase-2-methodology.md must include a
sample-size check (median trade count per market in window must be
>= 20 or widen) AND a small-trade-only VWAP comparison. If all-trade
VWAP and small-trade-only (< 10 contracts) VWAP diverge by more than
2pp, the trade-size effect is active and the strategy may be measuring
the wrong price.

## 2. Gate threshold critique (C1 through C5)

### C1 ("median OOS shoulder edge improvement >= 1.5x") measures the wrong thing

For Politics x H the bias is COMPRESSION (slope > 1), not extreme-
strike mispricing as in weather. ECE captures both directions via
binning, but the phrasing "shoulder edge improvement" is imported
from Phase 1.5/1.6 where the regime was weather-overconfident (Le's
slope 0.69-0.97 for weather at short horizons,
le-2026-crowd-wisdom.md "The weather-specific finding"). Applying the
same metric to a regime where the bias is structurally different is a
category error.

A more direct primary metric is **the test-set logistic recalibration
slope**. If the test-partition slope is >= 1.2 (consistent with Le's
lower CI bound minus 20% safety margin), the regime is empirically
present. ECE improvement should remain as a secondary diagnostic.

**Recommended C1 replacement:** "Median per-market logistic
recalibration slope on the test partition is >= 1.2."

### C2 ("median gross edge >= 4pp") is more than 4x Becker

As detailed in Risk 2: not literature-defensible. 4pp is achievable
only if the (long-horizon, mid-band) filter delivers ~4x the
politics-average per-trade edge, and the proposal does not justify
that multiplier. Le-derived edge under slope = 1.65 at YES = 0.30 is
roughly 10.2pp on COST BASIS (Bürgi's normalization,
burgi-deng-whelan-2025.md "Headline numbers to pin") but only ~1.02pp
on Becker's per-trade normalization on the same trades.

**Recommended C2 replacement:** ">= 2.04pp gross" (2x Becker
politics).

### C5 0.5pp slippage allowance is too optimistic for residential retail

Two reasons:

First, Becker (becker-2026-microstructure.md "The 2024 sign flip")
documents Q4 2024 volume surge driven by institutional MM entry.
Susquehanna actively makes Kalshi macro markets
(diercks-katz-wright-2026-feds.md "Volume / depth") and per CLAUDE.md
"What's reusable" the same MM family is active in politics. When news
breaks (poll release, debate, court ruling), institutional quotes
cancel within milliseconds. A residential retail order takes seconds.
Slippage between a stale maker order and updated fair value can
easily be 2-5pp on a single news event.

Second, Bartlett & O'Hara (bartlett-ohara-2026-adverse-selection.md
TL;DR item 6) document VPIN one-sided flow predicting maker losses in
single-name markets. The proposal includes no toxicity monitor. The
slippage distribution is bimodal (most fills 0pp, tails 5-10pp on
news), so the median may stay near 0.5pp while the mean is 1-2pp.

**Recommended C5 replacement:** "median net edge after maker fees and
1.5pp slippage allowance > 0pp AND mean net edge > 0pp." Requiring
BOTH catches news-event tail losses that the median hides.

## 3. Unaddressed failure modes

### Election-year sample selection bias

The corpus window [2024-10-01, 2026-04-30] includes the November 2024
federal election and 2026 midterm primary cycle but NOT the November
2026 general election. The corpus is dominated by federal-election
cycle markets, which may not represent typical politics markets the
bot will trade on after go-live. If the strategy generalizes only
because training data is election-cycle-dominated, late-2026 or
2027 non-election-year deployment will underperform.

**Fix:** Require >= 30% non-federal-election markets in both train
AND test partitions.

### Adverse selection from informed political traders

Politics markets attract polling firms, campaign staff, embargoed
journalists, and political-arbitrage desks. Bartlett
(bartlett-ohara-2026-adverse-selection.md TL;DR items 2 and 4) finds
single-name markets have higher adverse selection. Kalshi politics are
predominantly single-name. The 2x maker advantage Bartlett reports is
NET of adverse selection. The proposal targets long-horizon (>= 30
days), which may filter OUT peak-partisan-fervor periods and KEEP
high-adverse-selection periods (early markets where insider
information dominates).

**Fix:** One-sided-flow filter: exclude markets where > 65% of trades
in window are on the same side. Direct implementation of Bartlett.

### Multi-strike politics markets break the binary calibration model

Le's calibration model fits binary outcomes. Many Kalshi politics
markets are MULTI-STRIKE: a 5-candidate primary has 5 mutually-
exclusive YES contracts that must sum to 1. The slope-based truth
recovery (logit(truth) = a + slope * logit(market)) does NOT
trivially extend: per-strike slope > 1 implies truth probabilities
across the 5 strikes sum to >> 1, which is incoherent.

**Fix:** Restrict Phase 2 to BINARY politics markets only. Multi-
strike becomes a Phase 3 question after binary validates.

### Trade-size scale effect: $1 retail orders are on the wrong side

The sharpest failure mode and the proposal does not address it. Le
explicitly finds large trades (>100 contracts) in Kalshi politics are
MORE compressed than small trades (Delta = 0.53, 95% CI [0.29, 0.75];
le-2026-crowd-wisdom.md "Trade-size scale effect"). The effect does
NOT replicate on Polymarket (Kalshi-specific microstructure). Our $1
orders (3-5 contracts) are the small-trade end. The VWAP we measure
may be dominated by large trades (slope > 2 perhaps) while our fills
clear against small-trade book (Le: less compressed). Net: we may
select markets where the headline signal looks strong but our fills
clear much closer to fair value than the VWAP suggests. Phase 1.6
did not have to deal with this because weather has no documented
trade-size effect.

**Fix:** Require gate criterion C5 to hold on SMALL-TRADE VWAP (< 10
contracts). If the strategy survives only on large-trade VWAP, it is
not tradable at retail size.

### Liquidity at maker-fill price

Even if mispricing exists at YES = 0.30, a $1 maker order may not get
filled because institutional MMs sit inside. Bürgi
(burgi-deng-whelan-2025.md "Why hasn't the bias been arbitraged away"
item 1) notes Kalshi top-of-book ~$33 vs next level ~$3,336;
institutional MMs sit on top and retail queues behind. Whelan
(whelan-2026-betfair.md "Multiple equilibria") shows politics
non-event periods may be in the thin equilibrium where maker fills
are rare.

**Fix:** Acknowledge fill-rate is untested in historical trade data
and require >= 100-order live paper-trade fill-rate measurement
before live capital.

## 4. Competitor analysis pushback: Sports x Long-Horizon

The proposal's dismissal of Sports x Long-Horizon may be too quick.
It cites three concerns: Jump/Susquehanna dominance, adverse selection
in single-name games, and that long-horizon sports markets "may be
sparse on Kalshi." First two well-grounded. Third is the load-bearing
dismissal and is asserted, not checked.

Le (le-2026-crowd-wisdom.md "Per-domain breakdown on Kalshi"): Sports
has 55,637 markets and 43.2M trades (66.7% of Kalshi volume), median
76 trades. Becker gives sports 2.23pp gap, 2x politics' 1.02pp. Le's
politics long-horizon slope 1.83; sports long-horizon 1.74. Sports
short-horizon prices are well-calibrated (slope 0.90-1.10) meaning
the underconfidence regime is concentrated specifically in
long-horizon sports.

**The proposal cannot verify per-market long-horizon politics
liquidity from literature either; it applies the no-data standard
asymmetrically.** This critic does NOT propose a switch (per brief).
But the operator should know: if Politics x H fails, Sports x
Long-Horizon is a closer second-best than the proposal frames.

## 5. Recommended changes before methodology lock-in

Priority order. Incorporate into phase-2-methodology.md BEFORE any
data is pulled.

1. **Replace C1 with the empirical slope test.** Primary criterion:
   "median per-market logistic recalibration slope on test partition
   >= 1.2." ECE improvement becomes secondary diagnostic.

2. **Replace C2 with 2x-Becker, not 4pp.** New C2: "median per-trade
   gross edge on targeted slice >= 2.04pp gross (2x Becker politics
   average of 1.02pp)."

3. **Replace C5 slippage allowance with 1.5pp not 0.5pp, and require
   BOTH median and mean net edge > 0pp.**

4. **Add binary-only market filter.** Exclude multi-strike politics
   markets from Phase 2 dataset.

5. **Add small-trade VWAP check.** Compute both all-trade and small-
   trade (< 10 contracts) VWAP. Gate must pass on small-trade VWAP.

6. **Add one-sided-flow adverse-selection filter.** Exclude markets
   where > 65% of trades in window are on the same side.

7. **Require minimum 20 trades per market in the [-35d, -28d]
   window.** If median below 20, widen window or drop thin markets.
   Set BEFORE data pull.

8. **Require >= 30% non-federal-election markets in both train and
   test.** Avoid election-cycle selection bias.

9. **Acknowledge fill-rate is untested; require >= 100-order live
   paper-trade fill-rate measurement before live capital.** Add a
   monthly regime monitor (if fill rate < 30% or P&L lags backtest by
   > 2 SDs, pause and re-evaluate) per Whelan multiple equilibria
   and Becker 2024 sign flip lesson.

## 6. Citations table

| Claim in this report | Paper file | Section / Table / Figure |
|---|---|---|
| Le slope 1.83 at >1mo politics is posterior MEAN | le-2026-crowd-wisdom.md | "Domain-by-horizon trajectories" table |
| Le posterior 95% CI on politics slope at >1mo is 1.46 to 1.83 | le-2026-crowd-wisdom.md | "Domain-by-horizon trajectories" |
| 4 additive components, 87.3% of variance | le-2026-crowd-wisdom.md | "The four components of calibration error" table |
| Universal horizon effect mu = 30.2%, beta = 26.0% | le-2026-crowd-wisdom.md | same table |
| Becker politics gap 1.02pp on 4.9M trades | becker-2026-microstructure.md | "Per-category maker-taker gap" table |
| Le uses Becker's pre-collected dataset | le-2026-crowd-wisdom.md | "Cross-references in the paper" |
| Maker advantage is order-flow accommodation not forecasting | becker-2026-microstructure.md | TL;DR item 3 |
| Q4 2024 volume 27x Q3 2024 ($30M to $820M) | becker-2026-microstructure.md | "The 2024 sign flip" |
| Politics median 127 trades per market lifetime (highest of any domain) | le-2026-crowd-wisdom.md | "Per-domain breakdown on Kalshi" table |
| Trade-size scale effect: large trades MORE compressed Delta = 0.53 | le-2026-crowd-wisdom.md | "Trade-size scale effect" |
| Scale-effect 95% CI [0.29, 0.75] | le-2026-crowd-wisdom.md | "Trade-size scale effect" |
| Scale effect does NOT replicate on Polymarket | le-2026-crowd-wisdom.md | "Trade-size scale effect" |
| Single-name markets have higher informed price impact | bartlett-ohara-2026-adverse-selection.md | TL;DR item 2 |
| Behavioral surplus exceeds adverse selection by ~2x in single-name | bartlett-ohara-2026-adverse-selection.md | TL;DR items 4 and 5 |
| VPIN-style one-sided flow predicts maker losses in single-name | bartlett-ohara-2026-adverse-selection.md | TL;DR item 6 |
| Bartlett sample 41.6M Kalshi trades | bartlett-ohara-2026-adverse-selection.md | TL;DR item 1 |
| Bürgi top-of-book ~$33 vs next-level ~$3,336 | burgi-deng-whelan-2025.md | "Why hasn't the bias been arbitraged away" item 1 |
| Bürgi cost-basis return on >= 50c maker is +2.6% | burgi-deng-whelan-2025.md | "Headline numbers to pin" |
| Bürgi 33% per-trade SD on >= 50c maker subpopulation | burgi-deng-whelan-2025.md | Section 6 |
| Whelan multiple equilibria (thick / thin market) | whelan-2026-betfair.md | "Multiple equilibria" |
| Susquehanna actively makes Kalshi macro markets | diercks-katz-wright-2026-feds.md | "Volume / depth" |
| Sports gap 2.23pp per Becker | becker-2026-microstructure.md | "Per-category maker-taker gap" table |
| Sports long-horizon slope 1.74 per Le | le-2026-crowd-wisdom.md | "Domain-by-horizon trajectories" table |
| Sports 55,637 markets, 43.2M trades, median 76 trades | le-2026-crowd-wisdom.md | "Per-domain breakdown on Kalshi" table |
| Phase 1.5/1.6 lesson: trading window swamps model choice | phase-1.5-methodology.md | Section 10 change log entry 2026-05-23 |
| Phase 1.6 result: 1.49pp gross, -0.51pp net, gate FAIL | phase-1.6-results.md | "Pass criteria" table |
| Zerve is in-sample artifact; not a tradable proof | zerve-calibshi-2026.md | "The single most important deficiency" |
