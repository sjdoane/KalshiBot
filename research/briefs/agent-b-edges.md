# Agent B: Edge Identification on Kalshi (2026)

**Bottom line up front:** The literature is consistent and unkind to a $100 retail algo. Kalshi takers (anyone who hits the book) lose ~32% on a transactional basis; makers lose ~10% (Bürgi, Deng, Whelan 2025, n=300k+ contracts). Jump Trading, Susquehanna, DRW, and Flow Traders now run dedicated desks. The classic favorite-longshot bias is documented but already weakening in 2025 data. The "obvious" edges (cross-exchange arb, weather, crypto-lag) are professionally farmed. At least one candidate (residual KXHIGH calibration via isotonic regression + maker quoting) plausibly clears the ~3.5% fee drag, but margin is thin and the operator should expect single-digit annualized returns at best on $100 of risk capital.

## 1. Academic Literature: What Survives on Regulated US Markets

- **Wolfers & Zitzewitz (2004), "Prediction Markets" (JEP):** Documented that prediction markets weakly outperform alternative forecasts. Identified overpricing of extreme S&P 500 tails (favorite-longshot bias, FLB) on Tradesports/Iowa Electronic Markets. Most of the FLB findings still replicate today.
- **Manski (2006), "Interpreting the predictions of prediction markets" (Econ Letters):** Showed prices equal the 100(1-pi)th percentile of belief, not the mean, under risk-neutral heterogeneous beliefs. FLB emerges as an equilibrium property, not a "mistake." Implication: FLB is structural and only partially arbitrageable.
- **Tetlock / Good Judgment Project:** ~2% of forecasters ("superforecasters") are 30% more accurate than intelligence analysts; calibration accuracy drops when predictions are rounded to nearest 0.05. Direct implication for Kalshi: human calibration is achievable but rare, and the marginal trader on Kalshi is not a superforecaster.
- **Bürgi, Deng, Whelan (2025), "Makers and Takers: The Economics of the Kalshi Prediction Market" (UCD WP2025-19 / CEPR DP20631):** Transaction data on 300k+ contracts. Takers average -32%, makers -10% per trade; contracts <10c lose >60% of stake; contracts >50c yield makers +1.9% post-commission. FLB is real but weakening in 2025.
- **Clinton & Huang (2025), "Prediction Markets? Accuracy and Efficiency of $2.4B in the 2024 Election" (SocArXiv):** PredictIt 93% directional accuracy, Kalshi 78%, Polymarket 67%. Cross-platform arbitrage opportunities peaked in final 2 weeks; daily price changes weakly/negatively autocorrelated, i.e., overreaction.
- **Becker (2026), "Microstructure of Wealth Transfer in Prediction Markets":** Maker-taker gap varies by category: Finance 0.17pp, Politics 1.02pp, Sports 2.23pp, Entertainment 4.79pp, World Events 7.32pp. Post-2024 the maker-taker sign flipped (was +2% to takers in 2021-2023, now -1.12%).
- **"Decomposing Crowd Wisdom" (arXiv 2602.19520, 2026):** 292M trades on Kalshi+Polymarket; politics is "chronically compressed toward 50%" (underconfidence); on Kalshi this widens with trade size (Delta=0.53). The four-component model explains 87.3% of Kalshi calibration variance.
- **Rasooly & Rozzi (2025), "How manipulable are prediction markets?" (arXiv 2503.03312):** Manipulative trades persist visible 60+ days. Implies short-term price reversion after large flow.

**What survives in 2026 on Kalshi vs what was arbitraged out:** FLB at the deep tails (<10c, >90c) is still real but the easy money on the favorite side (>90c) has compressed; cross-exchange Kalshi vs Polymarket arb windows now last seconds and require co-located infrastructure; intra-market sum>$1 arbitrage that worked on PredictIt through ~2018 is essentially gone on Kalshi due to active MM. Political underconfidence (prices too close to 50%) is the most persistent published anomaly.

## 2. Common Amateur Mispricings (with magnitudes)

- **Favorite-longshot bias on Kalshi:** Contracts at 5c win ~4.18% (mispriced -16% relative). Contracts at 1c win ~0.43% (mispriced -57%). On the NO side, NO longshots have outperformed YES longshots by up to 64pp (Becker 2026). Asymmetry: takers comprise 41-47% of volume on 1-10c YES, only ~23% on 91-99c "YES as a wrapper for NO longshot."
- **Recency/overreaction:** 58% of Polymarket presidential markets showed negative day-over-day serial correlation in 2024 (Clinton & Huang). Kalshi exhibits similar daily mean reversion in political contracts.
- **Political underconfidence:** Prices chronically compressed toward 50%; Delta=0.53 widening effect on Kalshi by trade size.
- **Weather forecast lag:** NWS HRRR runs every hour, GFS every 6 hours. Documented latency arms race: pros react within seconds of NWS cycle; retail polling 15-60 min is "exit liquidity" (Northlake Labs, 0-for-32 record on weather trades). Residual calibration error on KXHIGHNY raw market prices: ECE=0.01624; isotonic recalibration cuts to ECE=0.00109, a 14.8x improvement (Zerve CalibShi study, 8,494 settled markets).
- **Sports model bias:** Pinnacle is treated as the de facto sharp benchmark. Kalshi sports volume is now $3-5B/yr on NFL alone, with Jump/Susquehanna making markets. Closing-line spreads vs Pinnacle averaged 3-8c on Kalshi vs 2-5c on Polymarket. Quant firms already farm CLV here.
- **Crypto-lag:** Real but tight; pros front-run with co-located feeds. Henry Zhang substack noted the lag is "where the edge lives" but a public substack post is not a moat.

## 3. Category Ranking by Signal-to-Noise (S/N) for a $100 Algo

Format: [S/N for retail algo] | smart vs dumb composition | spread/volume notes.

1. **Weather (KXHIGH-, KXSNOW-, KXRAIN-)** | S/N high in raw forecast skill, but pros saturate it | Volume moderate, spreads 1-3c on liquid cities, sub-second latency arms race. Smart: weather arb bots (multiple known operators). Dumb: vibes traders. Residual edge requires calibration model (isotonic) on top of GFS ensemble; viable as maker, near-impossible as taker.
2. **Crypto (KXBTC-, KXETH-, hourly/daily ranges)** | S/N medium | Pros front-run on co-lo; retail can scrape Coinbase feed but pros have it cheaper. Smart: HFT lat-arb. Dumb: directional crypto bros. Spreads 1-2c on near-money strikes.
3. **Economics (CPI, NFP, FOMC, GDP, unemployment)** | S/N medium-low for retail | Kalshi macro markets outperform Fed Funds futures and Bloomberg consensus on CPI (per Fed FEDS paper 2026-010). Smart: macro funds, prop desks. Dumb: very little dumb money - the bar is high.
4. **Sports (KXNFLGAME-, NBA, MLB)** | S/N low for retail | 72% of Kalshi volume, intense competition with traditional sportsbooks. Jump and Susquehanna make markets here. Pinnacle is the sharp benchmark and is faster than Kalshi. Sharp retail can chase CLV if the model beats Pinnacle, which is the same problem as winning at Pinnacle (very hard).
5. **Politics (elections, polling, Senate votes)** | S/N moderate but episodic | Underconfidence bias is the strongest published anomaly. Smart: a few politics-focused syndicates. Dumb: ideologues. Spreads widen and overreaction is documented (58% negative autocorrelation). Volume concentrates near events.
6. **Entertainment / awards / culture** | S/N decent | 4.79pp maker-taker gap; less covered by quant firms. Dumb money dominates. But volume is small ($10-100k per market) so position sizing is constrained.

## 4. Concrete Edge Candidates

### EC-1: KXHIGH weather residual calibration (maker-only)
- **Series:** KXHIGHNY, KXHIGHCHI, KXHIGHMIA, KXHIGHLAX, KXHIGHDEN (verified 2026).
- **Inefficiency:** Raw market probabilities are mildly miscalibrated; isotonic regression cuts ECE 14.8x on 8,494 settled markets. NWS-based ensemble probability vs market mid often diverges by 5-15pp on shoulder strikes.
- **Data needed:** NWS API (free), Open-Meteo GFS 31-member ensemble (free), Kalshi WS for quotes. Historical settled KXHIGH data is available via Kalshi API.
- **Mechanic:** Compute ensemble probability per strike; only post maker quotes (0.44c maker fee at 50c, 25% of taker); when ensemble prob differs from book mid by >8pp, post a passive order on the cheaper side. Cancel if NWS cycle updates.
- **Estimated edge:** 4-7pp gross on shoulder strikes (15-40c bucket); ~1.5-3pp net after 0.88c round-trip maker fees, capped by adverse selection.
- **Why this might not work:** Multiple known weather arb bots already operate; the maker fee is small but adverse selection (taker fills only when you're wrong) is large. The maker-taker sign flipped to +1.12% for makers post-2024, but only after fees, and weather specifically may already be competitive.
- **Backtest feasibility:** Kalshi historical trades + NWS archive (Iowa State NWS archive) + Open-Meteo historical reanalysis. Doable but engineering-intensive.

### EC-2: Politics underconfidence (compression toward 50%)
- **Series:** Senate/House control, FOMC rate moves with political stakes, polling-related contracts.
- **Inefficiency:** Prices chronically compressed toward 50%. On Kalshi specifically, this widens with trade size (Delta=0.53). Combined with documented overreaction (58% negative day-over-day autocorrelation).
- **Data needed:** 538/Silver Bulletin/Race-to-the-White-House model, polling averages, Polymarket prices for cross-check.
- **Mechanic:** When Kalshi YES price is between 60-85c but external model says >90%, buy YES; symmetric on 15-40c sells. Bounded position size (politics is event-driven and not continuous).
- **Estimated edge:** 5-12pp gross at moderate strikes, but volume is event-clustered and 2025 already saw partial compression of this anomaly.
- **Why this might not work:** Anomaly was strongest pre-2024 election; 2025 data show weakening. Liquidity dries up post-election cycle; in non-election years there isn't much volume. Polymarket leads Kalshi on politics (more liquidity), so by the time you act, the cross-market spread is gone.
- **Backtest feasibility:** Tough. Need historical Kalshi tick data plus contemporaneous external model snapshots. External-model archives are spotty.

### EC-3: Cross-platform arb Kalshi vs Polymarket (latency-bounded)
- **Series:** Any contract with identical-defined Polymarket equivalent.
- **Inefficiency:** Prices diverge by >5pp ~15-20% of the time; Polymarket leads Kalshi due to deeper liquidity.
- **Data needed:** Both APIs, low-latency execution, USDC wallet on Polygon for Polymarket side.
- **Mechanic:** Detect simultaneous YES_K + NO_P (or vice versa) sum below 0.98 plus fees; lock arb.
- **Estimated edge:** 1-3% per arb when found, but 78% of low-volume opportunities fail at execution (2025 study). Net of fees often near zero on $100 sizing.
- **Why this might not work:** Windows are seconds; pros are co-located. With $100 of capital you can take maybe 1 contract per side and the fees alone are ~1-2c per side. Operationally complex (KYC on both, Polygon gas, custody).
- **Backtest feasibility:** Possible by replaying historical orderbooks; quality of historical Polymarket data is uneven.

### EC-4: KXBTC short-dated range lat-arb (likely not viable)
- **Series:** KXBTC-{date}-{strike} hourly and daily.
- **Inefficiency:** Kalshi prices lag Coinbase BTC by seconds during fast moves.
- **Data needed:** Coinbase WS, Kalshi WS, low-latency colocation.
- **Mechanic:** When BTC mid moves >0.3% in 30s, recompute strike probability, hit the stale Kalshi quote.
- **Estimated edge:** Theoretically 2-5% per fill, but pros already do this from AWS us-east-1. Retail home connection latency (10-50ms) makes this losing.
- **Why this might not work:** Pure latency game with HFT competition. Strongly dominated by infrastructure. Round-trip fees at ~1.75c on 50c contracts eat the edge.
- **Backtest feasibility:** Easy in theory (Coinbase + Kalshi historical), but backtest will be optimistic vs live latency.

### EC-5: Entertainment/awards/culture inefficiency (low volume)
- **Series:** Oscars, Emmys, Spotify Wrapped, viral-event markets.
- **Inefficiency:** Largest maker-taker gap (4.79pp). Less covered by quants. Dumb money dominates.
- **Data needed:** Domain knowledge, Polymarket prices, betting forums.
- **Mechanic:** Quote both sides when liquidity is thin; harvest the spread plus directional edge from model.
- **Estimated edge:** 3-7pp gross when you can fill, but markets are small ($10-100k notional total). On $100 of capital you can't size up enough for it to matter.
- **Why this might not work:** Low volume caps absolute dollar profit. Adverse selection from informed counterparties (e.g., industry insiders on award markets). Settlement risk on subjective markets.
- **Backtest feasibility:** Hard; events are unique and non-repeating.

## 5. Smart Money vs Dumb Money on Kalshi

- **Documented institutional MMs:** Susquehanna (first official MM, 2024), Jump Trading (equity-for-liquidity deal, 2025), DRW, Flow Traders, plus specialist funds (Kirin, Anti Capital). Institutional volume up 800% over six months ending May 2026.
- **Dumb money:** Retail sports bettors (Kalshi's NFL volume hit $3-5B in 2025, $871M on Super Bowl Sunday 2026), political ideologues, viral-event chasers, crypto vibes traders. Top-1000 trader study by Kalshi suggests these are NOT Ivy League quants.
- **Counterparty composition by category:** Sports = retail-heavy on the dumb side but Jump/SIG on the smart side; politics = ideological retail vs a few sharp syndicates; weather = bot vs bot mostly (retail is exit liquidity per Northlake); economics = mostly prop desks on both sides (high bar). Entertainment = retail on retail, lowest professional coverage.
- **Implication:** Edge is concentrated where dumb money is large AND smart money has not fully arrived. That intersection is shrinking fast.

## 6. Sanity Check vs Fees

Kalshi taker fee = ceil(0.07 * C * (1-C)) cents per contract. At C=0.5, 1.75c per side, 3.5c round trip per $1 notional = 3.5% drag. Maker fee = 25% of taker = 0.44c at 50c = ~0.88c round trip (~0.88%). Add 2% drag for "deep" strikes (~30c or ~70c the fee is 1.47c taker / 0.37c maker).

| Edge candidate | Gross edge | Fee mode | Net edge | Clears 5% bar? |
|---|---|---|---|---|
| EC-1 KXHIGH (maker) | 4-7pp | maker, ~0.88% | 3-6pp | Marginal yes |
| EC-2 Politics underconf | 5-12pp | mixed | 3-10pp | Yes when active, but episodic |
| EC-3 Cross-platform arb | 1-3pp | taker x2 + Polygon | -1 to +1pp | No |
| EC-4 KXBTC lat-arb | 2-5pp | taker, ~3.5% | -1 to +2pp | No (infra dominated) |
| EC-5 Entertainment | 3-7pp | maker | 2-6pp | Marginal yes, but dollar-capped |

**Eliminated by fees + competition:** EC-3 (cross-platform arb) and EC-4 (BTC lat-arb) cannot clear the bar from a residential connection with $100. **Survivors:** EC-1 (KXHIGH maker calibration) and EC-2 (politics underconfidence) are the only candidates with documented inefficiencies large enough to plausibly survive fees, and both are at the edge of professional coverage. EC-5 has the largest residual bias but its absolute notional is too small for meaningful PnL.

## Conclusion

Honest assessment: there is **probably** real edge in KXHIGH calibration via maker quoting plus an ensemble forecast, and **maybe** in politics underconfidence around events. Everything else for a $100 retail account is at or below break-even after fees and competition. Expected outcome on $100 over a 3-6 month live test: range of -$30 to +$15, with mode near zero. **No edge candidate is robust enough to justify scaling beyond a deliberate, instrumented pilot.** If Phase 2 proceeds, scope must be narrow: KXHIGH maker quoting only, with politics as opportunistic add-on. If after a 200-trade live pilot the maker fill rate is not adverse-selected (i.e., win rate >55% on filled orders), pull the plug.

## Sources

- Wolfers & Zitzewitz (2004): https://www.nber.org/papers/w10504 and https://users.nber.org/~jwolfers/papers/wolfers04a.pdf
- Manski (2006), Economics Letters 91(3): https://ideas.repec.org/a/eee/ecolet/v91y2006i3p425-429.html
- Wolfers & Zitzewitz, "Interpreting Prediction Market Prices as Probabilities" (NBER 12200): https://users.nber.org/~jwolfers/papers/InterpretingPredictionMarketPrices.pdf
- Tetlock, Good Judgment Project: https://goodjudgment.com/ and https://aiimpacts.org/evidence-on-good-forecasting-practices-from-the-good-judgment-project/
- Bürgi, Deng, Whelan (2025) "Makers and Takers: The Economics of the Kalshi Prediction Market": https://www.karlwhelan.com/Papers/Kalshi.pdf and https://www.ucd.ie/economics/t4media/WP2025_19.pdf and https://cepr.org/voxeu/columns/economics-kalshi-prediction-market
- Becker (2026) "The Microstructure of Wealth Transfer in Prediction Markets": https://www.jbecker.dev/research/prediction-market-microstructure
- Clinton & Huang (2025) "Prediction Markets? The Accuracy and Efficiency of $2.4 Billion in the 2024 Presidential Election": https://ideas.repec.org/p/osf/socarx/d5yx2_v1.html
- "Decomposing Crowd Wisdom: Domain-Specific Calibration Dynamics in Prediction Markets" (arXiv 2602.19520): https://arxiv.org/pdf/2602.19520
- Rasooly & Rozzi (2025), arXiv 2503.03312: https://arxiv.org/pdf/2503.03312
- Federal Reserve FEDS 2026-010 "Kalshi and the Rise of Macro Markets": https://www.federalreserve.gov/econres/feds/files/2026010pap.pdf
- Northlake Labs weather postmortem: https://www.northlakelabs.com/max/blog/kalshi-weather-postmortem-and-pivot/
- Zerve CalibShi KXHIGHNY calibration study: https://www.zerve.ai/gallery/85cce830-f612-4b23-8b78-34d7da65a2c6
- Quantpedia "Systematic Edges in Prediction Markets": https://quantpedia.com/systematic-edges-in-prediction-markets/
- Kalshi fee schedule: https://kalshi.com/fee-schedule and https://help.kalshi.com/trading/fees
- Kalshi KXHIGHNY market: https://kalshi.com/markets/KXHIGHNY
- Kalshi KXNFLGAME: https://kalshi.com/markets/kxnflgame/professional-football-game
- Open-source weather bot (KXHIGH + GFS): https://github.com/suislanchez/polymarket-kalshi-weather-bot
- Open-source Kalshi+Polymarket arb bot: https://github.com/ImMike/polymarket-arbitrage
- Wall Street quants in prediction markets: https://www.financemagnates.com/fintech/wall-street-quants-move-into-prediction-markets-to-hunt-for-arbitrage-not-to-bet/
- Jump Trading entry: https://defirate.com/news/equity-for-liquidity-jump-trading-set-to-take-stakes-in-kalshi-and-polymarket/
- Sports volume / Super Bowl: https://fortune.com/2026/02/10/kalshi-super-bowl-sunday-871-million-sports-gambling-michael-lewis-warning/
- Kalshi vs Polymarket arbitrage analysis: https://laikalabs.ai/prediction-markets/polymarket-kalshi-arbitrage-guide and https://ahasignals.com/research/prediction-market-arbitrage-strategies/
- Kalshi crypto edge substack (paywalled, partial): https://henryzhang.substack.com/p/the-hidden-edge-in-kalshis-crypto

## Unknowns / Blockers

1. **Maker fill rate vs adverse selection on KXHIGH:** the published edge (4-7pp gross) is calibration-based on settled prices. Whether a passive limit order would actually fill at those prices without being adversely selected by a faster bot is the single biggest unknown. Could be tested with a $20 pilot over 50 markets.
2. **Politics market depth in non-election years:** the documented edge (Delta=0.53 compression) was measured during a high-volume election period. Whether it persists with $100k/day total volume across politics is unverified.
3. **Kalshi historical tick data access for backtesting:** Kalshi API gives recent trades but full-depth orderbook history is not openly available. Without it, EC-1 and EC-3 backtests will be optimistic.
4. **Fed paper (FEDS 2026-010) full results:** PDF extraction failed; could not confirm exact magnitude of Kalshi CPI/NFP edge vs fed funds futures. Need a clean text version.
5. **Cross-validation with Agent A on fees:** the formula ceil(0.07 * C * (1-C)) and maker discount (25% of taker) must be verified against the live fee schedule PDF for sports (which may carry a different fee schedule per Kalshi help center).
6. **Tax treatment:** Kalshi PnL treatment for WA-state retail account, especially around the recent CFTC vs state-court rulings (Massachusetts red-line case 2026), may impose unexpected reporting friction.
7. **Regulatory tail risk:** India just cracked down on prediction markets (May 22, 2026). US state-level action against Kalshi sports markets is escalating. A bot built around sports could be shut down by regulation mid-Phase 2.
8. **EC-1 capital constraint:** Maker quoting on five KXHIGH cities with 5-10 strikes each implies ~25-50 resting orders. On $100 of capital, average position size is ~$2-4. Slippage and minimum-tick effects may dominate; need to confirm Kalshi allows partial sub-dollar contracts and what the minimum-margin requirement is.
