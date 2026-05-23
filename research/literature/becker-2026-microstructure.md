# Becker (2026): "The Microstructure of Wealth Transfer in Prediction Markets"

**URL:** https://www.jbecker.dev/research/prediction-market-microstructure
**Author:** Jacob Becker (jbecker.dev personal research page)
**Date:** Early 2026
**Venue:** Personal research site (not peer-reviewed; trade-level
empirical work using public Kalshi API data)
**Retrieved:** 2026-05-23

**Why this matters for Project Kalshi.** Largest available empirical
sample (72.1M trades vs Bürgi's 313k price observations) and the only
source that publishes **per-category maker-taker gaps in basis-point
form, comparable across market types**. Critically, Becker also
documents a **2024 sign flip**: takers used to win, then makers
started winning after Kalshi's October 2024 CFTC ruling. This is the
single most policy-relevant temporal finding for whether the
EC-1-style maker edge will persist.

## TL;DR for future Claude

1. **Maker-taker gap is real, persistent, and category-dependent.**
   Weather gap is 2.57pp per trade (mid of the table). Finance is
   nearly arbed away (0.17pp). Sports is 2.23pp. World Events is
   7.32pp. Project Kalshi's EC-1 lives in a mid-tier category.

2. **Wealth transfer flips direction at the 2024 election.**
   Pre-October 2024: takers won +2.0%, makers lost -2.0% per trade
   (early Kalshi was a thin market where Makers carried inventory
   risk that didn't pay). Post-October 2024: makers win +2.5%, takers
   lose -2.5%. The aggregate (full dataset) is taker -1.12% / maker
   +1.12%, weighted heavily toward post-flip volume.

3. **The mechanism is order-flow accommodation, not forecasting.**
   Makers achieve nearly identical returns whether they buy YES or
   NO (Cohen's d = 0.02). They don't need to predict the future;
   they just sit on the resting side as taker flow disproportionately
   buys YES on longshots that lose.

4. **The signature pattern: takers overpay for YES longshots.**
   5c YES contracts win only 4.18% of the time. Takers fill nearly
   half the volume in the <10c bucket despite YES longshots
   underperforming NO longshots by up to 64pp.

5. **Becker's per-trade returns differ from Bürgi's contract-level
   numbers but agree on rank ordering.** Becker's normalization is
   per-trade gross excess return; Bürgi's is post-fee, dollar-weighted
   contract return. Both papers identify the same ordering: makers
   > takers, weather is mid-pack, world events / entertainment most
   biased, finance least biased.

## Per-category maker-taker gap (the headline table)

| Category | Taker return | Maker return | Gap | N trades |
|---|---|---|---|---|
| Finance | -0.08% | +0.08% | 0.17 pp | 4.4M |
| Politics | -0.51% | +0.51% | 1.02 pp | 4.9M |
| Sports | -1.11% | +1.12% | 2.23 pp | 43.6M |
| **Weather** | **-1.29%** | **+1.29%** | **2.57 pp** | **4.4M** |
| Crypto | -1.34% | +1.34% | 2.69 pp | 6.7M |
| Entertainment | -2.40% | +2.40% | 4.79 pp | 1.5M |
| Media | -3.64% | +3.64% | 7.28 pp | 0.6M |
| World Events | -3.66% | +3.66% | 7.32 pp | 0.2M |

**Reading the weather row for Project Kalshi:** every weather trade
on average transfers 1.29% from the taker to the maker (gross of
fees). With ~4.4M weather trades total in the corpus, that's a
meaningful cumulative wealth transfer, but per-trade is modest. Our
$25 cap means an expected maker edge of ~$0.32 per "weather trade
unit" before fees - small absolute dollars, but a positive sign.

## The 2024 sign flip

Before the October 2024 CFTC ruling and the November 2024 election:
- **Takers won an average +2.0% per trade.**
- **Makers lost an average -2.0% per trade.**

After that inflection:
- **Takers lose -2.5% per trade.**
- **Makers earn +2.5% per trade.**

The swing is **5.3 percentage points per trade.** Volume surged
~27x in Q4 2024 ($30M → $820M) and stayed elevated. Becker's
interpretation: thin early markets penalized Makers (they had to
carry inventory in markets that might never see a fill). Once volume
rose, Makers could quote thinner spreads, fills became more reliable,
and the residual fee + longshot-bias profit flipped them into the
black.

**Project Kalshi implication:** the EC-1 hypothesis is testing a
post-flip regime. Pre-flip Kalshi data is structurally different
from current markets; do not use any Kalshi data before October 2024
to estimate forward maker economics.

## Methodology

- **Sample:** 72.1M trades, 7.68M markets, $18.26B notional volume.
- **Date range:** Kalshi launch through 2025-11-25 17:00 ET (Q4
  2025 incomplete).
- **Filter:** resolved markets only (no voided / delisted / open);
  minimum $100 notional volume per market.
- **Maker/taker identification:** Kalshi's API returns `taker_side`
  and `taker_book_side` directly. No Lee-Ready inference needed.
- **Return formula:** per-trade gross excess return,
  `r = (100 * outcome - price_cents) / price_cents`. Pre-fee.
- **Comparison normalization:** cost basis (capital at risk), with
  NO-side equivalent prices computed as `100 - YES_price`.

## Specific numbers worth pinning

- **Sparsest price bin (81-90c)** still has 5.8M trades; statistical
  power is enormous.
- **5c YES contracts win 4.18% of the time** (16pp mispricing).
- **Cohen's d on YES vs NO maker returns: 0.02** (statistically
  identical; confirms accommodation mechanism, not forecasting).
- **5.3pp swing** from pre-election to post-election in maker-taker
  gap.
- **Q3 2024 volume: $30M; Q4 2024 volume: $820M** (27x).

## Limitations Becker flags

1. **Taker classification is API-derived, not from unique trader
   IDs.** A sophisticated trader crossing the spread for time-
   sensitive reasons could be misclassified.
2. **No bid-ask spread data.** Cannot decompose spread capture
   from biased-flow exploitation strictly.
3. **CFTC-specific.** Offshore venues with different leverage and
   fee rules may show different patterns.
4. **No account-level persistence analysis.** Can't tell whether
   the same makers always win or whether the maker pool churns.
5. **No causality claim** between market maturity and the sign
   flip - just correlation.

## Cross-reference with Bürgi 2026

Becker does NOT cite Bürgi/Deng/Whelan; both papers were produced
independently in late 2025 / early 2026 with different methodologies.

- Bürgi: 313k price snapshots, contract-level, post-fee,
  dollar-weighted; -9.64% maker / -31.46% taker average return.
- Becker: 72.1M trades, trade-level, pre-fee, cost-basis-normalized;
  +1.12% maker / -1.12% taker average return (aggregate).

The numerical gap (~22pp vs ~2.2pp) reflects different definitions:
Bürgi's per-contract dollar-weighted return captures the
heavy-extreme-strike distribution (67% of trades < 10c or > 90c)
plus fees, while Becker's per-trade excess return treats each trade
equally and excludes fees.

**Both papers agree on:**
- Sign: Makers earn more than Takers (post-2024)
- Rank: Weather is mid-tier in mispricing magnitude
- Mechanism: longshot overweighting by Takers
- Direction: 2025 trend continues but at smaller magnitude than peak

## Implications for Project Kalshi (EC-1)

1. **Weather's 2.57pp per-trade gap is the cleanest number for
   sizing EC-1 expectations.** It is recent (through Nov 2025),
   trade-weighted, and category-specific. The Bürgi +2.6% number
   for >= 50c contracts is consistent but applies only to the upper-
   shoulder subpopulation.

2. **Use only post-October-2024 data for any model fitting.**
   Pre-flip Kalshi data does not represent the regime we'd be
   trading. Our 5-city sample starts in 2021-08 (KXHIGHNY) but the
   bulk of relevant data is post-Oct 2024.

3. **The maker advantage comes from order-flow accommodation, not
   from forecasting skill.** This is why isotonic recalibration of
   market prices (the Zerve / EC-1 thesis) is conceptually
   defensible: we are extracting the systematic longshot
   overpricing baked into taker order flow, not trying to forecast
   weather better than NWS.

4. **Becker's per-trade SD is not published but is large** (similar
   to Bürgi's 33% on the maker-profitable subpopulation). Our
   methodology's flat $1-2 sizing + drawdown breakers is the
   correct posture for this variance.

5. **The 2024 sign-flip is a regime-change reminder.** Whatever
   edge we measure now could flip again with a future regulatory
   change, fee change, or institutional MM exit. Maintain regime-
   monitoring in any deployed bot.

## Pin quotes

> "Makers do not need to predict the future; they simply need to act
> as the counterparty to optimism."

> "Contracts trading at 5 cents win only 4.18% of the time, implying
> mispricing of -16.36%."

> "Takers disproportionately purchase YES contracts at longshot
> prices, accounting for nearly half of all volume in that range,
> despite YES longshots underperforming NO longshots by up to 64
> percentage points."

> "Financial questions attract traders who think in probabilities
> and expected values rather than fans betting on their favorite
> team or partisans betting on a preferred candidate." (explains
> the Finance vs World Events gap)

> "The wealth transfer observed in late 2024 is a function of
> market depth."

## What is NOT in the paper

- No trading strategy proposal.
- No fee schedule analysis.
- No per-strike-bucket return decomposition.
- No L2 orderbook analysis.
- No comparison to Bürgi (even though contemporaneous).
- No bid-ask spread data.
- No individual-trader persistence analysis.
