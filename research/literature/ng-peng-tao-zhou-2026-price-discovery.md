# Ng, Peng, Tao, Zhou (2026): "Price Discovery and Trading in Modern Prediction Markets"

**Citation.** Ng, Hunter; Peng, Lin; Tao, Yubo; Zhou, Dexin (Apr 2026), SSRN 5331995 / posted 2026-04-27. DOI: 10.2139/ssrn.5331995. Authors are at Baruch College / CUNY and University of Macau. Presented at FSS-DECO Seminar (University of Macau, 2026-01-28). Full PDF gated behind SSRN auth; extraction below is from the SSRN abstract, the Macau seminar page, the Quantpedia summary, and cross-checked secondary sources (DL News, AhaSignals derivative work).

**Why it matters for Project Kalshi.** This is the most-recent academic paper directly addressing the v3 thesis question: does Polymarket lead Kalshi in price discovery? It is the source Quantpedia cites in its "Systematic Edges in Prediction Markets" piece. The v2 critic flagged that earlier Polymarket-vs-Kalshi evidence was Substack-grade. This is the academic version. Full PDF unavailable through SSRN without auth; we have abstract + seminar + secondary-citation level coverage.

## TL;DR for future Claude

1. **Polymarket leads Kalshi in price discovery** during 2024 US election period, "particularly when liquidity and trading activity are high." This is the foundational citation for the v3 lead-lag thesis.
2. **Arbitrage opportunities exist but are very short-lived.** Per Quantpedia summary: opportunities "typically exist only for a few seconds, at best a few minutes, and transaction costs significantly reduce the potential profits."
3. **The result is order-flow driven, not platform-structural.** "The market experiencing greater directional order flow from large trades tends to lead price discovery." This means lead-lag is conditional on which side gets the informed flow, not a permanent property.
4. **Sample is 2024 US presidential election only.** No sports markets analyzed in this paper. Generalizing "Polymarket leads Kalshi" from politics 2024 to sports 2025/2026 requires inference; the paper does NOT support it directly.
5. **More-liquid prediction markets outperform polls.** Validates Kalshi/Polymarket as forecasting venues in aggregate.
6. **The 2026 sports landscape is asymmetric.** Per separate trade-press evidence (DefiRate, Sports Illustrated, QuantVPS as of Q1-Q2 2026): Kalshi sports volume is roughly $2.7B/week (53% market share, 90% of Kalshi volume is NFL/NBA/MLB); Polymarket US sports is $5M/week (444 markets, $650k open interest). The "Polymarket leads" finding from 2024 politics likely INVERTS for US-tradeable sports markets in 2026 because Polymarket US is the smaller, less-liquid venue. Polymarket Global (offshore) is $2.1B/week but ~40% sports, and US retail cannot trade it.

## Sample and methodology (per abstract / seminar)

- **Time range:** "the period leading up to the 2024 U.S. presidential election" (specific figures in Quantpedia cite Oct 23 to Nov 5, 2024).
- **Platforms:** Polymarket, Kalshi, PredictIt, Robinhood.
- **Markets:** common contracts available on at least two platforms during the election window. No sports markets.
- **Method:** Inter-platform price comparison; large-trade order-imbalance regressions to identify which venue moves first; arbitrage-opportunity quantification via probability-sum-below-1-minus-fees test.

## Headline numbers to pin

| Stat | Value | Source |
|---|---|---|
| Platforms compared | Polymarket, Kalshi, PredictIt, Robinhood | Abstract |
| Period analyzed | Oct 23 - Nov 5 2024 (per Quantpedia Fig 2) | Quantpedia |
| Arbitrage window duration | "a few seconds, at best a few minutes" | Quantpedia summary |
| Typical cross-platform spread | 2-5% on major events | DL News / trade press derivative |
| Lead-lag direction | Polymarket -> Kalshi (when Polymarket has more liquidity) | Abstract |

## Pin quotes

> "Polymarket leads Kalshi in price discovery, particularly when liquidity and trading activity are high, implying economically meaningful arbitrage opportunities." (Abstract)

> "Net order imbalance from large trades strongly predicts subsequent returns, and the market experiencing greater directional order flow from large trades tends to lead price discovery." (Abstract)

> "More liquid prediction markets substantially outperform polls in predicting subsequent election results, yet there are significant price disparities across platforms." (Abstract)

> "Opportunities typically exist only for a few seconds, at best a few minutes, and transaction costs significantly reduce the potential profits." (Secondary citation: Quantpedia summary)

## What is NOT in the paper

- **Sports markets.** Analysis is 2024 election-only. The v3 thesis (sports lead-lag) requires inference beyond what this paper measures.
- **2025-2026 data.** Sample ends Nov 2024. Post-election period (where Polymarket US is gated to iOS/limited launch and where institutional MMs piled into Kalshi sports) is not covered.
- **Per-market-type breakdown.** Reading the abstract closely: lead-lag is conditional on which platform has greater liquidity. The result is asymmetric and venue-specific.
- **Long-horizon markets.** Election-eve trading is ~hours to ~days from settlement. v1's domain is 30-180 day lifetime markets. Whether lead-lag holds on the long-horizon end is untested.

## Implications for Project Kalshi v3

1. **The Polymarket-leads-Kalshi thesis is academically grounded for 2024 politics, not for 2026 sports.** v3's H1/H2/H3 are built on extrapolating this result; the extrapolation is plausible but not paper-supported.

2. **The asymmetric liquidity in 2026 sports inverts the natural reading.** Per QuantVPS / Sports Illustrated trade press (Q1-Q2 2026): Kalshi handles 90% NFL/NBA/MLB volume at $2.7B/week; Polymarket US handles $5M/week sports. Under the Ng et al. mechanism ("market with greater directional order flow leads"), Kalshi sports SHOULD lead Polymarket US sports in 2026. This directly contradicts the v3 working thesis as stated in master plan Section 2.

3. **Polymarket Global is the only large-volume Polymarket sports venue ($2.1B/week)**, but US retail cannot trade it. We can read its prices via Gamma API (which v3 already plans). For events listed on both Polymarket Global and Kalshi US, Polymarket Global is the larger venue and might still lead. This is the actual v3-relevant version of the lead-lag thesis.

4. **Arbitrage is a high-frequency phenomenon.** Seconds-to-minutes windows. v1 operates at 15-minute cadence and 30-180 day market lifetimes. The Ng et al. arbitrage finding does NOT apply to v1's operational tempo. H3 (statistical divergence rule at trade-window scale) is the only v3 hypothesis where this paper's mechanism plausibly transfers.

5. **Order-flow conditioning is key.** The paper says lead-lag depends on which platform gets directional informed flow. For v3, this implies: if there's an information event (injury report, lineup change, weather) that hits Polymarket Global first because crypto-native traders are faster, then Kalshi prices lag. The feature engineering implication is to use Polymarket Global price + price-change-velocity as a feature, NOT just the static mid.

6. **Transaction costs kill the arbitrage edge for retail.** Quantpedia summary explicit: "transaction costs significantly reduce the potential profits." This re-validates v2's general lesson that retail edge is structurally small after fees. v3 must explicitly carry fees through any P&L projection.

## Verdict on the v3 master-plan thesis

The master plan's Section 2 reads: "**Polymarket leads Kalshi on price discovery for events listed on both platforms** (documented during 2024 election; Wolfers/Zitzewitz literature; AhaSignals/Quantpedia summaries)." This paper validates that claim for 2024 election only. For 2026 sports the underlying mechanism (greater-liquidity-venue-leads) suggests the OPPOSITE direction. The v3 design must therefore treat Polymarket-as-target (H1) skeptically and use Polymarket Global rather than Polymarket US as the comparison feed.
