# Phase 2 Strategy Proposal: Politics x Maker-Quote on Compressed Long-Horizon Markets

**Author:** Round 2 strategy-selection context
**Date:** 2026-05-23 (operator's local date)
**Status:** PROPOSAL. Operator approval required before methodology lock-in.
No data has been pulled, no code written. This document is purely a
literature-grounded strategy proposal for review.

This document fills in the 6-question decision framework from
[STRATEGY_BRIEF.md](../STRATEGY_BRIEF.md) for a single candidate strategy.

## Headline

**Candidate: Politics x H from the matrix in [strategy-comparison.md](strategy-comparison.md):**
post resting maker bids on Kalshi politics markets that are in
**Le's chronically-compressed regime** (long-horizon, slope > 1.3),
in **mid-band price range** (avoid extreme strikes for adverse-selection
reasons), expecting prices to extend toward the more-extreme truth that
Le's recalibration mapping implies.

This is **NOT** a forecasting strategy. We do not predict elections better
than Polymarket; we sit on the resting side as taker flow accommodates
the maker-favorable compression that Le 2026 documented.

## Why this candidate over the alternatives in the matrix

| Candidate | Pros | Cons | Decision |
|---|---|---|---|
| **Politics x H (this proposal)** | Le directly documents the regime; Bartlett's behavioral-surplus mechanism explains it; politics has the lowest Jump/SIG MM competition; highest per-market liquidity (127 median trades, Le); pipeline reuses Phase 1.5/1.6 with category swap. | Becker's per-trade gap is the smallest non-Finance category (1.02pp); Bürgi's politics psi is NOT significant (p > 0.05); episodic volume around elections; bias compression trend (Bürgi 2025 psi half of 2024). | **PROPOSED** |
| Sports x Long-Horizon (>1mo) | Becker gap is 2.23pp (2.2x politics); 43.6M trades (largest volume); Le slope 1.74 at long horizon; behavioral mechanism (fan-overbet) plausible. | Jump and Susquehanna dominate sports MM; adverse selection in single-name games is highest of all categories (Bartlett); long-horizon sports markets may be sparse on Kalshi (most are single-game). | Backup if H fails. |
| Sports x E (behavioral surplus) | Bartlett mechanism direct; large volume. | Adverse selection in single-name; need a market-classification model (which markets are YES-overbet?); HFT competition. | Skipped. |
| Bürgi >=50c cross-cat | +2.6% gross documented (Bürgi Section 6). | Pre-2025 fee regime; sample dominated by pre-flip data per Becker; bias-shrinkage trend (Bürgi 2025 psi half of 2024); not category-specific so methodology cannot lock a clean dataset definition. | Pattern is reflected in our price-range filter below, not the core thesis. |
| Politics x C (calibration model) | Same mechanism as H but adds isotonic fit. | More complex; politics multi-strike markets complicate the fit; H is sufficient to test the core hypothesis without model overhead. | Possible Phase 3 extension after H validates. |

Net: Politics x H has the cleanest literature support for a persistent
post-flip mechanism with lower institutional MM competition. Sports x
Long-Horizon has higher gross-edge potential but adds two big risks
(Jump/SIG, single-name adverse selection) and we cannot verify long-horizon
sports market depth on Kalshi without data.

## The six-question framework

### Q1. Which (category, strategy) pair?

**Politics x H** from [strategy-comparison.md](strategy-comparison.md).

**Refinements within H:**

- **Trading horizon:** target markets with >= 30 days to resolution at the
  time of trade. This is where Le's compression slope is largest
  (1.83 at >1mo, vs 0.93 at <1h). Phase 2 backtest data filtering will
  enforce this.
- **Price band:** market YES mid in [0.20, 0.45] or [0.55, 0.80]. Avoid
  extreme strikes (<0.10, >0.90) due to Bartlett's adverse-selection
  concentration. Avoid the 0.45-0.55 dead zone where the compression edge
  is smallest (logit linearization near 0.5 makes slope > 1 produce
  near-zero edge).
- **Direction (maker side):** for prices < 0.50, maker is on the NO side
  (lets retail buy YES at too-high a price). For prices > 0.50, maker is
  on the YES side (lets retail buy NO at too-high a price, equivalent
  to maker selling NO at too-low a price). Both cases exploit compression.

### Q2. Why does it survive fees?

**Round-trip maker fee math** (verified, [metrics.py](../src/kalshi_bot/analysis/metrics.py)):

- Maker fee = ceil(0.0175 * 100 * P * (1 - P)) cents per contract.
- At P = 0.30: maker fee = ceil(0.3675) = 1 cent = 1pp per side, 2pp round-trip.
- At P = 0.50: ceil(0.4375) = 1 cent = 1pp per side, 2pp round-trip.
- At P = 0.80: ceil(0.28) = 1 cent = 1pp per side, 2pp round-trip.

In all the tradable price bands the round-trip maker fee is approximately
**2pp**. Net edge must therefore exceed ~3pp gross (2pp fees + 1pp slippage / adverse-selection buffer) to be tradable.

**Gross edge under Le's compression regime:**

Le's calibration model: `logit(truth) = a + slope * logit(market)`.
For politics at long horizons, slope = 1.83 (Table 2 of Le 2026, see
[le-2026-crowd-wisdom.md](literature/le-2026-crowd-wisdom.md)).

Worked example at market YES = 0.30:
- logit(0.30) = -0.847
- logit(truth) = 0 + 1.83 * (-0.847) = -1.550
- truth = sigmoid(-1.550) = 0.175

Maker on NO side: pays $0.70 per share, receives $1 if NO resolves.
- P(NO resolves) = 1 - 0.175 = 0.825
- Expected payoff: 0.825 * $1 = $0.825
- Expected gross P&L per share: $0.825 - $0.70 = $0.125 = 12.5pp on cost
- Per-contract gross edge (Becker normalization): (0.825 - 0.70) / 0.70 = +17.9%

This is far above the 1.02pp Becker average for politics. Two reasons:
1. The 1.02pp average is across ALL politics trades including pro-priced
   short-horizon ones; the targeted slice (long-horizon, mid-band) has a
   higher concentration of mispricing.
2. Becker's normalization is per-trade (treating each trade equally) while
   the per-contract cost-basis return I computed here matches Bürgi's
   approach for the >= 50c subpopulation (+2.6% pre-fee).

**Caveat:** Le's slope = 1.83 is the posterior MEAN across markets in the
>1mo bin. Individual markets vary; some will have slope ~1.0 (already
calibrated) and some > 2.0. The strategy assumes we can identify markets
with above-average compression, OR that the average across many bets
captures the mean edge. The OOS gate tests this.

**Bottom line on fees:** if Le's regime holds in our backtest sample, we
expect gross edge of **3-10pp** per fill on the targeted slice, vs ~2pp
round-trip maker fees. Net edge target: **>= 1pp** after fees (criterion C5
below). The point-estimate edge of 12.5pp at P=0.30 is best-case; the gate
will accept anything > 1pp on the median.

### Q3. Why does it survive the 2024 sign flip?

The mechanism (Bartlett's behavioral surplus from partisans on opposing
sides) is documented in **post-flip data**. Specifically:

- Bartlett & O'Hara 2026 ([extraction](literature/bartlett-ohara-2026-adverse-selection.md)):
  41.6M trades through (probably) late 2025. The "behavioral surplus
  cross-subsidizes adverse selection" finding is in their abstract; full
  sample bounds need PDF access but the sample is post-flip dominant.
- Le 2026 ([extraction](literature/le-2026-crowd-wisdom.md)): Sample is
  Kalshi through 2025-12-31. The chronically-underconfident politics
  finding is computed on data that includes the 2024 election spike. The
  posterior 95% CI on politics slope at >1mo is presented as 1.46-1.83
  (Le Section 4) - tight and well clear of slope = 1.0.
- Becker 2026 ([extraction](literature/becker-2026-microstructure.md)):
  The 2024 sign flip is documented BUT the per-category table (1.02pp
  politics) is a full-sample number; the post-flip-only per-category
  numbers are not separately published. Becker DOES say the post-flip
  maker average is +2.5pp per trade in aggregate.

**Verification commitment:** Phase 2 dataset will be restricted to markets
that resolved on or after 2024-10-01 (the sign-flip date). Any backtest
edge estimated from pre-flip politics data is discarded.

### Q4. Why does it survive variance?

Bürgi's 33% per-trade SD on the maker-profitable >= 50c subpopulation is
the variance baseline ([burgi-deng-whelan-2025.md](literature/burgi-deng-whelan-2025.md) Section 6).
Our strategy targets a broader price band (0.20-0.45 + 0.55-0.80), so the
relevant SD is plausibly similar or slightly larger (more deep-OTM
exposure on the lower shoulder).

**Sizing math at $25 initial deployment:**

- Per-fill notional: $1 (flat sizing). This is small for Kalshi where
  the minimum is 1 contract priced anywhere from $0.01 to $0.99. At
  market price $0.30 NO, $1 buys 3.33 contracts ($1 cost basis), capped
  at integer contracts so likely 3.
- Max concurrent positions: 5 ($5 of $25 deployed at any time, 80%
  reserve for adverse swings).
- Per-trade SD on cost basis: 33% (Bürgi)
- 100 fills at flat $1, IID with mean edge +0.05 (5pp net, optimistic):
  expected P&L = $5, SD = sqrt(100) * (0.33 * $1) = $3.30. So mean - 2*SD
  = -$1.60, mean + 2*SD = +$11.60. 95% CI on $25 stake over 100 trades:
  drawdown peak likely in -$3 to -$5 range, recoverable within bankroll.
- 100 fills with mean edge +0.01 (1pp net, marginal): expected P&L = $1,
  SD = $3.30. 95% CI = -$5.60 to +$7.60. Higher relative drawdown risk
  but still within bankroll.

**Drawdown breakers** (inherited from Phase 1 risk brief, [agent-c-risk.md](briefs/agent-c-risk.md)):

- 5% bankroll drawdown: warning alert (Discord)
- 10% drawdown: halve max concurrent positions to 2-3
- 15% drawdown: pause new orders, wait 24h before resume
- 25% drawdown: hard stop, manual operator review required

At $25 bankroll: warning at -$1.25, halve at -$2.50, pause at -$3.75,
hard stop at -$6.25. The 25% breaker is a clean kill switch consistent
with the post-Phase-1 critic's recommendation.

### Q5. What's the OOS gate?

**Lock the methodology BEFORE pulling new data.** This is enforced by the
methodology doc (`research/phase-2-methodology.md`, to be written after
proposal approval). High-level shape, modeled on Phase 1.5/1.6:

- **Dataset:** all settled Kalshi politics markets, resolution date in
  [2024-10-01, 2026-04-30]. Out-of-time buffer: 2026-05-01 onward
  reserved for live-validation sanity check.
- **Series filter:** politics markets with >= 50 historical trades
  (per-market liquidity floor, matches Le's median for politics).
- **Trading window:** for each market, simulated fill at VWAP of trades
  occurring in [resolution - 35 days, resolution - 28 days]. This is the
  ">= 30 days to resolution" trading bucket where Le's slope >= 1.46.
  Resolution day prices (and the last 28 days) are EXCLUDED from the
  fill computation - that's the "trading window" vs "measurement window"
  distinction the Phase 1.5/1.6 lesson hardened.
- **Splits:**
  - Walk-forward time splits: 180d train / 30d test / 7d purge / 30d
    step. ~16-18 splits in the 19-month corpus.
  - Leave-one-major-event-out: train on all markets except those resolved
    around a specific election week, test on the held-out election.
    Politics's natural "city" analog for the LOCO check.
- **Five pass criteria** (locked thresholds, copy of Phase 1.5/1.6 shape):
  - C1: median OOS shoulder edge improvement (recalibrated vs raw) >= 1.5x
    (more lenient than weather's 5x because politics's absolute bias is
    smaller; the proposed criterion is multiple over baseline calibration
    error, not ECE ratio).
  - C2: median per-trade gross edge on mid-band targets >= 4pp (must
    clear 2pp fees + 2pp safety buffer).
  - C3: at least 4 of the walk-forward splits show net (after-fee) edge > 0.
  - C4: leave-one-event-out positive on >= 3 of 5 election weeks tested.
  - C5: median net edge after maker fees and 0.5pp slippage allowance > 0.
- **No third bite:** if any criterion fails, the strategy ends. No
  re-running with different filters, no excluding "noisy" splits, no
  swapping isotonic for Platt.

These thresholds and the gate design will be FINALIZED in
`research/phase-2-methodology.md` before any data is pulled. The numbers
above are the proposal; the methodology critic will challenge them.

### Q6. What does the critic say?

To be answered. After this proposal is operator-approved, spawn a
plan-critic sub-agent (per [STRATEGY_BRIEF.md](../STRATEGY_BRIEF.md)
process step 3 and CLAUDE.md "review agents" section) with the brief:

> Adversarial review of the Politics x H Phase 2 proposal in
> research/phase-2-proposal.md. Identify weak assumptions (especially
> around the 2024-flip-robustness of Le's slope estimate, the price-band
> selection, and the >= 30 days horizon choice), challenge the gate
> thresholds (Q5), and find counter-evidence from the 7-paper corpus that
> Politics x H won't survive fees. Report under 500 words; address each
> weak assumption in priority order.

After the critic returns, every weak assumption must be addressed
explicitly in this document or in the methodology lock. No silent
ignoring.

## What I am NOT proposing

- I am NOT proposing to add a Polymarket cross-platform component. Le
  shows the trade-size scale effect is Kalshi-specific; Clinton & Huang
  (cited in [research-document.md](research-document.md)) show 78%
  execution failure on cross-platform arb at low volume. Residential
  latency makes the operator uncompetitive.
- I am NOT proposing isotonic calibration for the maker selection (yet).
  Politics x H is the "post bids in a range" strategy. If H gates pass,
  Politics x C (calibration model layer) is a Phase 3 enhancement.
- I am NOT proposing to trade short-horizon politics. Le's slope at <1h
  is 0.93 (slightly overconfident) - opposite regime sign from the
  long-horizon thesis. We avoid that horizon entirely in this phase.
- I am NOT proposing to re-open EC-1 or any weather strategy. No
  third bite per the locked Phase 1.5/1.6 methodology.

## Open questions for operator decision

1. **Approve Politics x H as the Phase 2 candidate?** Or redirect to
   Sports x Long-Horizon, Bürgi >=50c cross-cat, or something else?
2. **Confirm the dataset bounds (2024-10-01 to 2026-04-30 corpus,
   reserve 2026-05+ for out-of-time)?**
3. **Confirm the >= 30 days horizon as the locked filter?** Alternatives
   (>= 60 days, >= 90 days) would push us further into the high-slope
   regime but reduce sample size.
4. **Confirm the C1-C5 threshold shape, with concrete numbers to be
   tuned in the methodology doc but the SHAPE (5 criteria with no third
   bite) locked in?**

## Required next steps if approved

1. Write `research/phase-2-methodology.md` with finalized C1-C5
   thresholds and full split parameters. NO data pulled until written.
2. Spawn plan-critic on this proposal. Address all findings either here
   or in the methodology doc.
3. Spawn methodology-critic on the locked methodology. Address findings.
4. Build the politics ticker parser (template: `kxhigh.py`).
5. Pull the 19-month politics dataset.
6. Run the gate. Honor the verdict.

## Required next steps if redirected

If operator redirects to a different candidate, this document remains as
the reasoning record for why Politics x H was the top pick. The
alternative becomes the subject of a new proposal doc following the same
6-question structure.
