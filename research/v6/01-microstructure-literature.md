# v6 Microstructure Literature Survey

## Executive summary

Of the four candidate v6 features, order book imbalance (OBI) and order flow imbalance (OFI) have the strongest published support, but the literature is almost entirely at sub-minute horizons (5 to 60s) with alpha decay measured in seconds, not minutes. CVD has thin academic backing as a standalone predictor; it is mostly a divergence indicator. Deribit options skew has documented info content about implied vol shape, but explicit evidence that 25-delta risk reversal forecasts spot direction at sub-hour horizons is weak and partly negative (Da Fonseca and Wang 2024 is an explicit null). Funding rate level has near-zero R-squared (0.003 over 8h, Fulgur 2020) and funding rate delta has essentially no peer-reviewed coverage. Adverse selection literature warns that maker rebates of 1 to 2.5 bps on Binance/Deribit are dominated by adverse selection beyond seconds, a serious headwind for any Kalshi maker strategy at T-30 to T-5 min.

## 1. Crypto orderbook imbalance at 5 to 30 minute horizons

- Cont, Kukanov, Stoikov, "The Price Impact of Order Book Events" (2014), https://arxiv.org/abs/1011.6402. Linear relation between OFI and short-horizon price change in US equities, slope inversely proportional to depth. Use the Cont OFI form in v6, not naive bid/ask ratio.
- Silantyev, "Price Impact of Order Book Imbalance in Cryptocurrency Markets" (2020), https://towardsdatascience.com/price-impact-of-order-book-imbalance-in-cryptocurrency-markets-bf39695246f6/. ETHUSD 2019, 1.9M obs. Signal "short-lived, quickly deteriorates with time horizon"; returns under 10 bps over 10s. Direct warning: signal half-life is seconds.
- Markwick, "Order Flow Imbalance: A High Frequency Trading Signal" (2022), https://dm13450.github.io/2022/02/02/Order-Flow-Imbalance.html. Crypto OFI at 1s: out-of-sample R-squared 3.0%, hit rate 53%, Sharpe 0.12. Statistically real, economically marginal.
- "Exploring Microstructural Dynamics in Cryptocurrency Limit Order Books" (2025), https://arxiv.org/html/2506.05764v2. Binance Futures 2022 to 2025, 5 majors. OFI, spread, VWAP-to-mid universally important at 3s; taker backtest 4 to 8% annualized on mid caps, BTC positive but insignificant.
- "Nowcasting Bitcoin's Crash Risk with Order Imbalance" (2023), https://pmc.ncbi.nlm.nih.gov/articles/PMC10040314/. Daily McFadden R-squared 30.7% for crash days. Does NOT test sub-hour, but confirms order imbalance Granger-causes returns daily.

Application to v6: real signal but published alpha is sub-minute. T-5 is a stretch; T-30 and T-15 likely too far.

## 2. Cumulative volume delta (CVD)

- Phemex Academy CVD guide (2024), https://phemex.com/academy/what-is-cumulative-delta-cvd-indicator. Practitioner overview; CVD used for divergence, not raw direction.
- CryptoQuant Spot Taker CVD (2026), https://cryptoquant.com/asset/btc/chart/market-indicator/spot-taker-cvdcumulative-volume-delta-90-day. Widely tracked but mathematically equivalent to integrated trade-flow imbalance, so academic backing collapses into OFI.
- Literature thin: no peer-reviewed paper tests CVD as a standalone direction forecaster at 5 to 30 min.

Application to v6: treat CVD as a slow variant of trade-side OFI, not an independent feature.

## 3. Deribit options skew at sub-hour horizons

- Alexander, Deng, Feng, Wan, "Net Buying Pressure and the Information in Bitcoin Option Trades" (2022), https://arxiv.org/abs/2109.02776. Deribit tick 2019 to 2020. OTM flow contains directional info, ATM is volatility-driven. Caveat: documents flow predicting implied vol shape, NOT spot direction at minute scale.
- Da Fonseca and Wang, "Implied volatility slopes and jumps in bitcoin options" (2024), Op Research Letters, https://www.sciencedirect.com/science/article/abs/pii/S0167637724000713. Deribit Sep 2020 to Aug 2023. Both skew slopes "lack predictive capability for returns" but forecast realized vol weekly. Explicit null.
- Hou et al. (2021), "Implied volatility estimation of bitcoin options," https://pmc.ncbi.nlm.nih.gov/articles/PMC8418903/. Bitcoin has forward (positive both sides) skew vs equity-style negative. Standard intuition does not transfer.
- Recovering Risk Aversion from Bitcoin Option Prices (2026), https://www.tandfonline.com/doi/full/10.1080/13504851.2024.2381564. Weak directional info, weekly to monthly only.

Application to v6: thin and partly negative. Likely dead end at T-30 to T-5.

## 4. Funding rate delta vs level

- Fulgur Ventures (2020), https://medium.com/@fulgur.ventures/bitcoin-funding-rates-and-price-predictability-27ce95535af1. BitMEX funding vs 8h BTC returns: beta -0.087 (p=0.008), R-squared 0.003. Statistically real, economically useless.
- Inan, "Predictability of Funding Rates" (2024), SSRN 5576424, https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5576424. Forecasts funding rates themselves (not BTC returns) with DAR; time-varying stability. Indirect evidence innovations carry info beyond level.
- "Designing funding rates for perpetual futures" (2025), https://arxiv.org/html/2506.08573v1. Theory: linear funding rule induces mean-reverting basis; deltas mechanically tied to basis, not exogenous direction signals.
- Literature thin: no peer-reviewed paper explicitly tests funding rate DELTA as a sub-hour BTC direction predictor. Combined with the null on levels, the absence is itself informative.

Application to v6: largely untested. Worth one column, low prior; do not anchor on it.

## 5. Adverse selection cost for makers at sub-hour horizons

- Tinic et al., "Adverse Selection in Cryptocurrency Markets" (2023), J Financial Research, https://onlinelibrary.wiley.com/doi/10.1111/jfir.12317. Bitfinex order/trade data. Adverse selection averages roughly 10% of effective spread; predicts intraday vol, liquidity, toxicity, returns. LPs detect informed flow rapidly.
- Deribit Insights, "Maker & Taker Fees on Crypto Exchanges," https://insights.deribit.com/market-research/maker-taker-fees-on-crypto-exchanges-a-market-structure-analysis/. Binance/Bitmex/Deribit: maker rebate 1.0 to 2.5 bps; taker fee 2.0 to 7.5 bps. Adverse selection systematically eats rebates.
- The Block, "Polymarket adds taker fees to 15-minute crypto markets" (2025), https://www.theblock.co/post/384461/polymarket-adds-taker-fees-to-15-minute-crypto-markets-to-fund-liquidity-rebates. Polymarket sized taker fees up to 1.80% on 15-min BTC markets to compensate makers against latency arbs. Direct read: at 5 to 15 min on a comparable hourly product, adverse selection needs rebates in the 100+ bp range to be viable.

Application to v6: at T-30, adverse selection is dominated by directional moves; at T-5, latency arb dominates. Kalshi maker economics on KXBTCD almost certainly do not compensate without a strong pure-direction edge.

## 6. Published null findings (so we do not repeat them)

- Fulgur (2020): funding rate level R-squared 0.003 on 8h BTC. Killed in v5; do not redo.
- Da Fonseca and Wang (2024): IV skew slopes "lack predictive capability for returns," only forecast realized vol. Caution against using 25-delta RR as a directional feature.
- Markwick (2022), Silantyev (2020): OFI/OBI signals decay in seconds; cannot bear fees alone beyond microstructure scale.
- Project Kalshi v5 Track C: 0 of 7 macro/on-chain features cleared +0.005 Brier at T-1h. Slow-moving features do not work at hourly scale.

## What the literature suggests will work

Sub-minute OFI/OBI is the only feature with consistently positive empirical support across independent studies. If v6 can pull T-5 min data and the signal still has residual force (a generous extrapolation from 30s findings), it is the most credible feature. Combine OFI with VWAP-to-mid and spread per arxiv 2506.05764 and the Cont framework. Funding rate delta is worth one column but should not anchor the model.

## What the literature suggests is a dead end

- 25-delta options skew as a directional feature at sub-hour (Da Fonseca and Wang explicit null).
- Funding rate level (killed in v5).
- CVD as a standalone direction predictor at 5 to 30 min; folklore only.
- Making liquidity on KXBTCD at T-5 without an exceptional pure-direction signal; adverse selection plus Polymarket's 1.8% taker calibration imply the rebate is eaten.

Recommendation: narrow to OFI/OBI at T-5 as the primary feature, funding rate delta as low-prior secondary. Drop options skew and CVD as primary candidates. If T-5 OFI does not clear the Brier threshold, kill v6.
