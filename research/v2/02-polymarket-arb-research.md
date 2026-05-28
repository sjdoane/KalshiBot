# Agent B Brief: Polymarket Cross-Platform Arbitrage Research

Author: Research Agent B
Date: 2026-05-23
Topic: Operational tractability of a retail Kalshi vs. Polymarket arbitrage scanner
Scope: Research only. No wallet setup. No live capital. No code merged to live v1.

## TL;DR verdict

**Operationally tractable for US retail in May 2026: NO, with one narrow path.**

The main offshore polymarket.com platform still **IP-blocks all US users** per Polymarket's own help center (US is one of 33 fully restricted countries). The CFTC-blessed US replacement (Polymarket US, formerly QCEX) launched its iOS app on **May 12, 2026** and has removed its waitlist, but it is a **separate venue with a separate orderbook** that is only weeks out of beta. It also requires full KYC, including SSN and liveness selfie, and its API documentation is access-gated.

The economics are also unfavorable at our $32 bankroll: a profitable arb requires roughly a **2 cent gross spread** after Kalshi taker fees, which yields **less than a dollar net P&L per arb** at 100-contract size. We can only afford 10 to 20 contracts per leg. Most documented spreads decay within seconds.

Recommendation: archive this path. Revisit after Polymarket US has been live for six months with public liquidity data, OR if operator chooses to set up a non-US Polygon wallet (requires VPN, T&C violation, and creates withdrawal/KYC complications). Neither is recommended for a $32 retail account.

## 1. US-access threshold question

This was the gating question, so I answered it first.

**Polymarket offshore (polymarket.com)**: blocked. The Polymarket help center page on geographic restrictions lists **the United States among 33 fully restricted countries** as of May 2026 ([source](https://help.polymarket.com/en/articles/13364163-geographic-restrictions)). California has no exemption. KYC checks flag US residents. Using a VPN violates terms of service. The platform uses USDC on Polygon with a relayer-paid gas model (effectively gasless for users).

**Polymarket US (QCEX-routed)**: technically open. Polymarket acquired QCX LLC and QC Clearing for $112M in July 2025 ([source](https://www.prnewswire.com/news-releases/polymarket-acquires-cftc-licensed-exchange-and-clearinghouse-qcex-for-112-million-302509626.html)) and received an Amended Order of Designation from the CFTC on November 25, 2025. The US version is hosted at `polymarketexchange.com` (operating name "Polymarket US"). The **iOS-only app launched May 12, 2026 and the waitlist was removed** ([Covers source](https://www.covers.com/industry/polymarket-removes-waitlist-launches-for-american-ios-users-may-12-2026)). KYC is mandatory: government ID, SSN, address proof, liveness selfie ([copytradeinsider source](https://www.copytradeinsider.com/blog/polymarket-kyc-requirements/)).

**Critical structural divergence:** Polymarket US is a **separate CFTC-regulated DCM with a separate orderbook**, not a US frontend to polymarket.com. As of May 2026 it is **far less liquid**: roughly **$5M/week volume vs. ~$3B/month on the offshore** ([Sacra source](https://sacra.com/c/polymarket/)), about **440 markets** total, and only sports markets in beta. The offshore versus US prices "usually track but aren't identical" per industry coverage. Arbitrage exists between the two Polymarkets themselves, but as a US retailer we can only see one side.

**API access for Polymarket US**: The developer docs at `apidocs.polymarketexchange.com` are **access-gated** (require a code obtained via onboarding@qcex.com). Authentication uses **Ed25519 signing**, distinct from the offshore CLOB's HMAC-SHA256. Twenty-three REST endpoints and two WebSocket channels exist per third-party coverage but the schema is not public.

## 2. Polymarket offshore API surface (for completeness)

Confirmed live and public via `scripts/v2/probe_polymarket.py`. Sample written to `data/v2/polymarket_samples.json`.

| Service | Base URL | Auth | Use |
|---|---|---|---|
| Gamma | `https://gamma-api.polymarket.com` | None | Markets, events, tags, sports, public-search |
| CLOB | `https://clob.polymarket.com` | None for prices; HMAC-SHA256 for orders | Orderbook, midpoint, price history |
| Data | `https://data-api.polymarket.com` | None | Positions, trades, holders, leaderboards |
| WS public | `wss://ws-subscriptions-clob.polymarket.com/ws/market` | None | Live deltas |

Probe results:
- `GET /markets?limit=5&active=true` returned 5 markets, 91 fields each, no auth. Confirmed.
- `GET /events?limit=5&active=true` returned 5 events.
- `GET /public-search?q=...` returned matched events for all 5 queries we tried.
- `GET /sports` returned 192 configured leagues (epl, ncaab, mls, lal, ipl, acn, etc).
- `GET /price?token_id=...&side=BUY` returned `{"price": "0.53"}`. Pricing confirmed.

Rate limits are not numerically published. Public sources note no explicit ceiling; community guidance is to keep request rates polite.

Official Python client: `py-clob-client` on the `Polymarket/` GitHub org. Last updated 2025 per searches. For order placement, requires Polygon wallet + USDC + EIP-712 signed messages over the L2-resolver contract.

**Bottom line on the API**: the offshore API is excellent and free for read-only research. We could absolutely build a paper-only scanner that pairs Kalshi YES prices against Polymarket YES prices to log apparent spreads. We cannot trade them.

## 3. Event-matching: the structural blocker

Kalshi tickers are short canonicalized strings like `KXNFLWINS-27DET-8`. Polymarket questions are free-text English like "Will the Detroit Lions win 8 or more games in the 2026 season?" There is no shared identifier. Five sample probes:

| Kalshi ticker | Free-text query I tried | Polymarket result | Match quality |
|---|---|---|---|
| `KXNFLWINS-27DET-8` | "NFL Detroit Lions 8 wins 2027" | "NFL Win Totals: Over or Under?" (end 2026-01-10) | **FALSE** (wrong season, generic title) |
| `KXMLBALEAST-25-NYY` | "Yankees AL East 2025 division" | "MLB: 2026 AL East Champion" (end 2026-10-11) | **FALSE** (wrong year) |
| `KXBUNDESLIGA-25-BM` | "Bundesliga 2025 Bayern Munich champion" | "Bundesliga: Team to qualify for UEFA Champions League" | **FALSE** (different question) |
| `KXBOXING-26APR11TFURAMAK-TFUR` | "Boxing Tyson Fury Anthony Joshua April 2026" | "Boxing: Tyson Fury vs. Arslanbek Makhmudov" (end 2026-04-12) | **TRUE** (Kalshi ticker actually had Makhmudov not Joshua; my query was wrong, result was right) |
| `KXBALLONDOR-25-LYAM` | "Ballon d'Or 2025 Yamal" | "Ballon d'Or Winner 2025" | **TRUE event**, requires sub-market matching to find Yamal contract |

**False-positive rate: 3/5 (60%) with naive text search.** With tag-and-date filters this would drop, but most of the FPs involve season-year mismatches that defeat tag filtering. To get to a low-FP matcher we would need: (a) a parser that decodes the Kalshi ticker grammar per series (the existing project has `kxhigh.py` as a template), (b) date-window restriction, (c) sport/league tag lookup via `/sports`, and (d) per-pair human spot-check for any candidate that triggers a trade.

That last point fails success criterion A3 ("identification does not require subjective human judgment per case") from the master plan. A non-trivial fraction of pairs would need manual review.

## 4. Settlement-divergence risk: confirmed, with named examples

This is the most important hidden risk. Even if matching is perfect, the two platforms can resolve the same event differently because of different rule sources.

**Cardi B Super Bowl 2025 performance** ([defirate source](https://defirate.com/prediction-markets/how-contracts-settle/)): Kalshi invoked rule 6.3(c), determined the event ambiguous, settled at last-traded price ($0.26 YES, $0.74 NO). Polymarket resolved YES at $1.00. A trader long YES on Kalshi and long NO on Polymarket would have lost on both sides on what looked like a guaranteed-payout pair.

**Khamenei ouster, February 28, 2026**: US and Israeli forces killed Ayatollah Khamenei. Polymarket's contract resolved YES, paid out $529M. Kalshi halted its market and settled $21.7M at last-traded pre-death price (not $1.00). Long YES on Kalshi got a much smaller payout than long YES on Polymarket on the same factual outcome.

Both cases stem from a structural difference: Kalshi names specific third-party sources per contract; Polymarket uses UMA's optimistic oracle with token-holder governance. They disagree about edge cases (ambiguity, market halt, source unavailable). Cross-platform arb assumes the two sides cancel; **they don't always**.

The substack source [building-a-prediction-market-arbitrage](https://navnoorbawa.substack.com/p/building-a-prediction-market-arbitrage) explicitly recommends: **"Avoid cross-platform positions unless spread exceeds 15 cents."** That is a 5x to 7x buffer over our cost-only break-even, and it is there to absorb resolution divergence.

## 5. Trading-cost recap and edge sizing

Numbers from `scripts/v2/edge_sizing.py` (output captured in this doc, script self-contained).

**Kalshi side**:
- Taker fee: `ceil(7 * p * (1-p))` cents per contract.
- At p=0.30: **2c/contract**; at p=0.50: **2c**; at p=0.70: **2c**.
- Maker fee: 1/4 of taker, capped at 1c at our retail price range.

**Polymarket offshore side** (sports category):
- Taker: **0.3% of notional** (`docs.polymarket.com/trading/fees`). At p=0.50 that's $0.0015/contract = **0.15c**.
- Maker: zero.
- Gas: relayer-paid, effectively zero per trade in normal conditions; can spike during election-night-class events but irrelevant to sports.
- Settlement: zero.

**USDC entry/exit (offshore path, hypothetical)**:
- Buy USDC on a CEX, transfer to Polygon wallet: ~$0.01 gas.
- ACH/wire USD into the CEX: ~$0 for ACH at most large CEXes.
- Realistically: a few cents to fund a small position. Negligible against Kalshi-side fees.

**Polymarket US side** (relevant if operator routes through QCEX):
- Fees rumored 0.01% to 0.04% per trade per industry coverage. Below Kalshi taker cost.
- Fiat USD, ACH or bank wire. KYC required. No crypto leg.

**Minimum profitable gross spread** (Kalshi taker + Polymarket offshore taker):

| YES price | Kalshi fee | Poly fee | Total breakeven spread |
|---|---|---|---|
| $0.30 | 2.00c | 0.21c | **2.21c** |
| $0.50 | 2.00c | 0.15c | **2.15c** |
| $0.70 | 2.00c | 0.09c | **2.09c** |

With **Kalshi maker** (resting limit) the breakeven drops to ~1.1c. But we'd still need to be filled on the maker side, which is non-trivial under arb conditions where prices are converging.

**Net P&L at break-even spread**:
- 1 contract: ~$0.008. One cent.
- 10 contracts: ~$0.08.
- 100 contracts: ~$0.80.

At $32 bankroll, 10 contracts at $0.30/each is $3 of capital, and we'd need ~$3 on the other leg too. That fits. But **8 cents per arb** is the realistic ceiling, and **gross spreads have to be larger than 2c after fees**, which corresponds to actual mid-price gaps of roughly 4 to 6 cents pre-fees. With the 15-cent recommendation from the divergence-risk source layered on, **a defensible trade requires gaps of 15c+ which are rare and disappear in seconds**.

## 6. Historical arbitrage evidence

**Documented**: AhaSignals and Quantpedia reference an academic study of October 23 to November 5, 2024 (Kalshi vs. Polymarket pre-election) showing **prices for identical contracts diverging on 62 of 65 days**, with divergences peaking in the final two weeks. Polymarket led Kalshi due to higher liquidity. Specific magnitudes were not quantified in the public summaries I could access; the original study (cited as "Price Discovery and Trading in Prediction Markets") would need to be pulled for exact spread distributions.

**Aggregate**: A separate substack analysis cites $40M in cumulative arbitrage profits extracted from Polymarket between April 2024 and April 2025, with single-condition arb of $10.58M of that. Top performer: 4,049 trades, $2.01M, average $496/trade. **This is institutional-grade infrastructure, not retail**.

**Recent (2026)**: I could not find a single documented post-election Kalshi-Polymarket spread of >5c in 2026 on a sports market. The AhaSignals scanner currently displays "No validated active matched markets" with a PMDI score of 0/100 as of late May 2026, suggesting current spreads are routinely sub-fee.

**Conclusion on historical evidence**: arbitrage opportunities existed during the 2024 election peak, were extracted predominantly by sophisticated bots with sub-second execution and institutional capital, and have largely closed in 2026 outside of high-volatility event windows.

## 7. Operational tractability check against master-plan criteria

The master plan locks in three success criteria for this path:

| Criterion | Outcome |
|---|---|
| A1: At least 5 historical Kalshi-Polymarket event pairs identifiable | **Partial pass.** Pairs exist (election 2024) but we cannot retroactively validate them from free historical data because Kalshi's pre-2025 historical API is paginated and slow, and Polymarket's data API requires market IDs we don't yet have a Kalshi-to-Polymarket mapping for. Would need a one-time hand-curated list. |
| A2: At least 1 historical price divergence >5c (after fees on both sides) | **Pass via secondary citation.** 2024 election data per Quantpedia, but I do not have first-party spread series. |
| A3: Identification of matched events does not require subjective human judgment per case | **FAIL.** Naive search hits 60% false positives on 5 test tickers; reducing FPs to <5% requires either per-series Kalshi-ticker parsers (engineering cost) plus per-pair manual review (operator time), or an embedding-based matcher with a labeled training set that we don't have. |

Per master plan: "If A3 fails, arb gets archived as 'needs more research, not actionable now.'"

## 8. Operator setup that would be required to actually trade

If the operator decides to proceed despite the above, the minimum setup:

**Path 1 - Polymarket US (QCEX), only legal US path**:
1. Download iOS app (no Android, no web yet as of May 2026). Operator must have an iPhone or iPad.
2. Complete KYC: government ID, SSN, address proof, liveness selfie.
3. Fund via ACH USD or bank wire. Fiat, no crypto required.
4. Apply for API access via `onboarding@qcex.com`. Access code required for docs. Retail API access is unconfirmed; partner APIs are advertised but availability for individuals is opaque.
5. Build an Ed25519-signing client against the gated docs.
6. Accept that the US version's liquidity is ~1/600th of offshore and may not list the markets we care about (sports beta only).

**Path 2 - Offshore Polymarket (legal risk, not recommended)**:
1. VPN that consistently resolves to a non-US, non-restricted country.
2. Crypto wallet (MetaMask) on Polygon.
3. KYC bypass relies on no US flagging during onboarding; if flagged, account freezes.
4. USDC funding requires fiat-to-crypto ramp (Coinbase et al.), which itself KYCs the operator as US.
5. Builds the auth layer against the (well-documented) offshore CLOB.
6. Withdrawals risk freezing if the operator's KYC ever ties the wallet back to a US identity.

This path **violates Polymarket's terms** and the consent decree they signed with the CFTC, and most importantly creates real legal/withdrawal risk for an account with $32 in it. Not recommended.

## 9. Recommendation

**Archive this path.** Specifically:

- Do NOT proceed to Wave 2 Agent D (arb scanner prototype) as a trading tool.
- DO build a paper-only logger if it costs ~30 minutes of engineering: poll Gamma + Kalshi every 15 minutes for matched-pair candidates (manually curated list), log apparent spreads to `data/v2/arb_log.parquet`. This produces evidence for or against the thesis with zero capital exposure. If 90 days of logging reveals consistent post-fee spreads above 5c on sports, revisit. The substack guidance of 15c minimum is the actionable threshold.
- Revisit the US-side question in 6 months. Polymarket US liquidity in May 2026 is too thin to host real arb. If by November 2026 it grows toward the offshore platform, the API picture clarifies, and the partner-API retail eligibility resolves, this analysis may flip.

The kill-early principle from the project memory applies here. We do not have a tractable trading path for a US retail account today.

## Sources

- [Polymarket Documentation: Introduction](https://docs.polymarket.com/api-reference/introduction)
- [Polymarket Documentation: Trading Fees](https://docs.polymarket.com/trading/fees)
- [Polymarket Help Center: Geographic Restrictions](https://help.polymarket.com/en/articles/13364163-geographic-restrictions)
- [Polymarket Acquires QCEX](https://www.prnewswire.com/news-releases/polymarket-acquires-cftc-licensed-exchange-and-clearinghouse-qcex-for-112-million-302509626.html)
- [Polymarket Removes Waitlist for US iOS, May 12 2026](https://www.covers.com/industry/polymarket-removes-waitlist-launches-for-american-ios-users-may-12-2026)
- [Polymarket KYC Requirements 2026](https://www.copytradeinsider.com/blog/polymarket-kyc-requirements/)
- [Polymarket US Exchange Site](https://www.polymarketexchange.com/)
- [Polymarket Exchange API Docs (access-gated)](https://apidocs.polymarketexchange.com/api-reference/introduction)
- [Polymarket Wikipedia entry](https://en.wikipedia.org/wiki/Polymarket)
- [Polymarket vs Kalshi market settlement (defirate)](https://defirate.com/prediction-markets/how-contracts-settle/)
- [Sacra: Polymarket research](https://sacra.com/c/polymarket/)
- [Quantpedia: Systematic edges in prediction markets](https://quantpedia.com/systematic-edges-in-prediction-markets/)
- [Navnoor Bawa: Building a prediction market arbitrage bot](https://navnoorbawa.substack.com/p/building-a-prediction-market-arbitrage)
- [Alphascope: Is Polymarket legal in the US](https://www.alphascope.app/blog/is-polymarket-legal-in-us)
- [QuantVPS: Polymarket US API Available](https://www.quantvps.com/blog/polymarket-us-api-available)
- [Reason: The Return of Polymarket Jan 2026](https://reason.com/2026/01/04/the-return-of-polymarket/)

## Unknowns / blockers

1. **Polymarket US partner API retail eligibility**: docs are access-gated. Whether an individual without an FCM relationship can get API keys is unconfirmed. Email contact required.
2. **Polymarket US fee schedule exact numbers**: rumored 0.01 to 0.04% per trade but I could not pull the official fee schedule because the partner docs are gated.
3. **Polymarket US live market catalog**: only sports in beta per industry coverage. The specific sports leagues and overlap with Kalshi's KXNFLWINS, KXMLB, KXNBA, KXNHL series is unverified. Could be major overlap or zero overlap. Requires QCEX account to verify.
4. **Polymarket US liquidity by market**: aggregate is ~$5M/week. Per-market depth is unknown. Even if matching works, fills at our scale may not be available on the US side.
5. **Historical 2024 election spread distribution**: Quantpedia cites the divergence but exact (date, market, spread, fee-adjusted spread) records require pulling the original academic paper, which I did not retrieve in this brief. Not a blocker for the no-go verdict but would matter if operator wants to revisit.
6. **2026 spread frequency on sports**: AhaSignals' live scanner shows zero validated matches as of late May 2026, but the scanner's matching criteria are stricter than ours might be. A 90-day passive logger from a paper scanner would resolve this empirically at low cost.
