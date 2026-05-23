# Burgi, Deng, Whelan (2026): "Makers and Takers: The Economics of the Kalshi Prediction Market"

**Citation.** Burgi, Deng, Whelan (Jan 2026), UCD WP2025-19 / CEPR DP20631.
PDF at https://www.karlwhelan.com/Papers/Kalshi.pdf (retrieved 2026-05-23).

**Why it matters for Project Kalshi.** First academic paper with
transaction-level Kalshi data. The "takers lose 32%, makers lose 10%
per trade" headline that anchors all Kalshi strategy discussion comes
from here. It also breaks down economics BY CATEGORY (Table 8) and by
year (Table 9) - both load-bearing for the EC-1 hypothesis.

## TL;DR for future Claude

1. **Average pre-fee return on a Kalshi contract is -20%.** Not zero,
   because most trades cluster at extreme strikes (<10c and >90c make up
   ~68% of all observations) and the favorite-longshot bias makes
   cheap contracts dramatic losers and expensive contracts mild winners.
2. **Maker -9.64%, Taker -31.46% on average** (post-fee, pre-2025 fee
   regime where only Takers paid fees).
3. **Makers on contracts >= 50c earn +2.6% avg return.** This is the
   most important subpopulation finding for EC-1. The shoulder-strike
   range 60-85c falls inside this profitable range.
4. **Climate / Weather has a SMALLER favorite-longshot bias than the
   average market category.** Table 8 ψ coefficient is 0.031 vs 0.034
   all-market average; constant is -0.997 vs -1.736. Less retail "dumb
   money" in weather than in crypto/entertainment. This is BAD news
   for EC-1 specifically.
5. **The bias is weakening over time.** 2025 ψ is 0.021 (only *
   significance) vs 0.041*** in 2021. By mid-2026 we should assume
   the edge is even smaller. Kalshi started charging Makers fees in
   April 2025, which the paper does not analyze.
6. **The structural cause is a small probability-overweighting bias**
   (model parameter β = 0.09): people systematically overestimate small
   probabilities and underestimate large ones, the classic
   Kahneman-Tversky pattern. Modest disagreement between traders plus
   this bias explains everything in the data.

## Sample and methodology

- **Time range:** Kalshi inception (2021) through April 2025. Sample
  cutoff because Kalshi began charging Maker fees after April 2025.
- **Coverage:** 46,282 distinct Yes contracts on 12,403 events. With
  Yes+No mirror observations and multi-day price snapshots, 313,972
  total price observations.
- **Filter:** lifetime contract volume >= $1,000, bid-ask spread <= 20c,
  market duration >= 24 hours. Excludes hourly-resetting crypto and
  index markets.
- **Data source:** Kalshi REST API (their `kalshi.com` keys, Python
  scrapes). They captured both the final trade price AND daily snapshots
  going back up to 10 days before close. Daily data is sparse: 24h
  observations exist for 12,861 contracts; 10-day-out for only 6,754.
- **Maker/Taker identification:** Kalshi's API returns `taker_side` and
  `taker_book_side` per trade, eliminating the Lee-Ready (1991)
  classification noise that plagues equity microstructure work.
- **Volume distribution:** median lifetime volume per contract is
  $8,982; top decile averages $526,245; deep illiquidity in most
  markets.
- **Average transaction size:** $100 mean, $35 median. Small trades
  dominate.

## Headline numbers to pin

| Stat | Value | Source |
|---|---|---|
| Pre-fee avg return, all contracts | -20% | Section 3.3 |
| Post-fee Maker avg return | -9.64% | Figure 6 / Section 4 |
| Post-fee Taker avg return | -31.46% | Figure 6 / Section 4 |
| Avg return on <10c contracts | -60%+ | Section 3.3 |
| Avg return on 50c+ contracts (all) | small positive | Section 3.3 |
| Avg return on 50c+ contracts (Makers only) | +2.6% | Section 6 |
| SD of return on 50c+ Maker contracts | 33% | Section 6 |
| Fraction of trades at <10c or >90c | 67.6% | Table 2 |
| Maker fraction of volume | 50.0% (overall) | Table 10 |
| Maker share, 1-10c contracts | 43.5% | Table 10 |
| Maker share, 90-99c contracts | 56.5% | Table 10 |

**Reading the Maker shares:** Makers are over-represented on the
expensive (90c+) side and under-represented on the cheap (<10c) side.
Translation: when retail traders take a cheap-longshot YES at 4c, a
Maker is selling it to them. When retail takes a near-certainty 96c
YES, a Maker is also typically selling. The Maker is consistently the
side WITH the higher-probability belief, and that side wins more often.

## Category breakdown (Table 8) - critical for EC-1

Mincer-Zarnowitz regressions of `(outcome - price)` on `price` per
category. Larger `ψ` (price coefficient) = more favorite-longshot bias =
more profit opportunity if you can capture the right side.

| Category | ψ (price coef) | Constant | N | Bias magnitude |
|---|---|---|---|---|
| Crypto | 0.058*** | -1.944** | 8,150 | LARGEST |
| Other | 0.053*** | -2.392*** | 15,192 | |
| Economics | 0.034*** | -0.978 | 24,405 | |
| All (average) | 0.034*** | -1.736*** | 156,986 | |
| Financials | 0.032*** | -1.431*** | 27,123 | |
| Climate & Weather | **0.031*** | **-0.997*** | **29,924** | **SMALLEST among significant categories** |
| Politics | 0.022 | -1.912*** | 26,819 | weak, p > 0.05 |
| Entertainment | 0.020 | -2.809*** | 25,541 | weak, p > 0.05 |

**Implication for EC-1:** Climate & Weather is on the
less-mispriced end of the spectrum. The retail-driven longshot
inflation that gives makers their edge in crypto markets is muted in
weather markets. That is consistent with weather being
already-professionally-traded (Northlake Labs et al.) - the
inefficiency has been competed down. EC-1 starts from a smaller-edge
baseline than other Kalshi categories.

## Time-period trend (Table 9)

| Year | ψ | p-value | Constant | N |
|---|---|---|---|---|
| 2021 | 0.041 | *** | -1.649 | 3,855 |
| 2022 | 0.023 | ** | -1.589 | 24,913 |
| 2023 | 0.036 | *** | -1.531 | 23,559 |
| 2024 | 0.048 | *** | -1.793 | 53,338 |
| 2025 | 0.021 | * | -1.851 | 51,321 |

**2025 number is striking:** ψ dropped from 0.048 (2024 peak) to 0.021
(2025 partial sample through April), and statistical significance
dropped from *** to *. This is the institutional MM entry effect
(Susquehanna 2024, Jump 2025, DRW, Flow Traders) compressing the bias.
**Project Kalshi launching mid-2026 should expect even further
compression of the edge** relative to the 2024 peak.

## Volume and transaction-size do NOT explain the bias

- Table 6: bias persists across all five volume quintiles. The lowest
  volume quintile has the largest ψ (0.045) but Q2-Q5 are not
  systematically smaller.
- Table 7: bias persists across all five mean-transaction-size
  quintiles. The HIGHEST mean-transaction-size quintile actually has
  the largest ψ (0.043), opposite of the "smart money pays more
  attention" hypothesis.

Translation: the bias is not driven by tiny illiquid markets or by
unsophisticated tiny traders. Even large markets with large average
trades exhibit it.

## Day-by-day evolution (Table 5)

Mincer-Zarnowitz regression run on prices captured at 0, 1, 2, ..., 10
days before close. Bias is significantly nonzero (F-test rejects null)
at every horizon. Magnitude of mispricing is roughly constant across
horizons, though MAE (Figure 4) falls steeply on the final closing
day. **Implication: a pre-resolution trading window does not magically
fix the bias - it's there at +0d, +5d, and +10d.**

## The "Yogi Berra effect"

Page 2012 phenomenon: losses for both Makers and Takers on cheap
contracts are PARTICULARLY bad on the closing day relative to earlier
days. The authors interpret this as over-optimism intensifying as the
market closes. **This is directly relevant to our Phase 1.5 vs 1.6
window decision:** the close-window measures peak-bias prices, which
may inflate the apparent calibration signal but is also the LEAST
liquid window for a real trading bot to actually capture.

## Structural model (Section 5)

A simple model with three parameters fits the observed maker / taker
return patterns:
- **β = 0.09**: probability over-weighting (Kahneman-Tversky).
  Tightly identified (best-fit range 0.06-0.12). Without this, the
  model cannot fit the favorite-longshot pattern at all.
- **θ = 0.60**: matching rate (probability a Maker's posted order gets
  filled). Weakly identified; trades off with σ.
- **σ = 0.107**: belief dispersion (SD of subjective probability
  beliefs around the true value).

The model has multiple equilibria (thick and thin market), and the
authors fix θ exogenously to pick one. The key non-trivial finding is
that **bias in beliefs is structurally NECESSARY** to fit the data; a
model with belief disagreement alone (β = 0) predicts the OPPOSITE
of what's observed for cheap contracts (Figure 10).

## Why hasn't the bias been arbitraged away? (Section 6)

Three reasons offered:
1. **Small volumes.** Top-decile average lifetime volume is $526k.
   Top-of-book liquidity is much smaller (Figure 2 shows ~$33 at best
   ask, $3,336 at next-best ask in a CPI example). Pros need too much
   liquidity to bother.
2. **Riskiness.** 33% standard deviation on the Maker-profitable 50c+
   contracts. Even if avg return is +2.6%, that is a Sharpe of roughly
   0.08 per trade, which is genuinely terrible. Samuelson 1963 / Pratt
   Zeckhauser 1987 argued log-utility investors should decline gambles
   with this risk profile.
3. **Lack of information.** The paper is the first to publish these
   facts. The authors literally say "interesting to see if the biases
   persist now they've been publicly documented." They have been now;
   future Claude should assume the bias is being competed down faster.

## Implications for Project Kalshi (EC-1)

1. **The 5-criteria gate we built measures the right thing**
   (calibration improvement out-of-sample). The paper validates that
   the bias exists, is statistically significant, and persists in
   weather markets specifically.
2. **The shoulder-strike focus is RIGHT but should lean upper shoulder.**
   The +2.6% Maker return is specifically on contracts >= 50c. Our
   shoulder definition (0.15-0.40) AND (0.60-0.85) includes the
   upper-shoulder profitable range and the lower-shoulder unprofitable
   range. Phase 2 strategy design should weight the upper shoulder
   more heavily.
3. **The weather-specific edge is smaller than the market average.**
   We should not assume "Bürgi shows 10pp Maker edge on Kalshi" - the
   weather edge is closer to half that.
4. **Maker fees post-April-2025 are NOT in the paper.** Our methodology
   uses 25%-of-taker maker fees. The paper's +2.6% number is based on a
   ZERO-Maker-fee regime. Post-2025, the realistic +2.6% number becomes
   roughly +1.7% after the new Maker fees (rough back-of-envelope).
5. **2025 trend is unfavorable.** ψ dropped 2024 -> 2025 by more than
   half. Project Kalshi is launching mid-2026; expect another step
   down.
6. **Yogi Berra effect validates Phase 1.6 window choice.** The peak
   bias is at close (especially on the closing day), but liquidity is
   thinnest there and the bias is partly information-driven (Page
   2012). Our pre-resolution window [open+1h, open+13h] avoids the
   Yogi Berra distortion.
7. **The 33% return SD is the dominant risk.** Even if we capture the
   2.6% Maker edge, a $50 bankroll trading 5-10 markets at a time has
   meaningful drawdown probability. The methodology's drawdown
   circuit breakers (5/10/15/25%) are genuinely necessary.

## What is NOT in the paper

- **L2 orderbook depth.** Only trade prints, not full book history.
  Their "best bid / best ask" comes from the trade tape, not a snapshot
  feed.
- **Per-strike profitability within a series.** They bucket all
  contracts into 10c price bins; they do not compare e.g. KXHIGHNY T65
  vs T70 individually.
- **Post-April-2025 fee regime.** Their sample ends precisely because
  Kalshi changed the fee structure.
- **Strategy design.** They are economists describing what happened.
  They do not propose or test a maker-quoting algorithm.
- **Time-of-day or day-of-week effects.** No intraday analysis.
- **Withdrawal/funding economics.** Pure trading P&L.

## Pin quotes

> "The average return on contracts for Makers was -9.64% while for
> Takers it was -31.46%." (Section 4)

> "Makers who buy contracts costing 50c and over earn a 2.6% rate of
> return." (Section 6)

> "There is some evidence of a weakening in the favorite-longshot bias
> because the ψ coefficient for the 2025 data is smaller and less
> statistically significant." (Section 3.4)

> "The standard deviation of the rate of return on contracts bought by
> Makers costing 50c and over is 33%." (Section 6)

> "It will be interesting to see if the biases and return patterns
> that we have reported persist now that they have been publicly
> documented." (Section 6)

## Action items this paper drives for Project Kalshi

1. In Phase 2 strategy design (if 1.6 passes), weight the **upper
   shoulder (60-85c) more heavily than the lower shoulder (15-40c)**.
   The maker-profitable subpopulation lives at >= 50c.
2. **Recompute maker fee assumptions** explicitly for post-2025 regime
   when modeling expected P&L. The paper's +2.6% is a zero-maker-fee
   number.
3. **Build a position-sizing model that handles 33% per-trade SD**.
   This is the dominant practical risk; the methodology's existing
   $1-2 flat sizing per trade is appropriate for this variance.
4. **Plan for further edge compression**. Monitor live performance vs
   backtest, particularly through the 2026 mid-terms and any further
   institutional-MM volume entry.
