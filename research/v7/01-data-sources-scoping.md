# V7 Data Sources Scoping (Phase 1)

**Date:** 2026-05-25
**Scope:** Identify US-accessible APIs that unblock the angles killed or deferred in v6: historical L2 orderbook for crypto, sportsbook line-movement, news/sentiment, and on-chain signal sources. Within budget: $30 to $60 one-time, ~$22 LLM remaining.
**Method:** WebFetch on docs and pricing pages, live curl probes from this US machine (CA IP), verified HTTP status + sample payloads.

## Executive summary

Three sources are the highest priority to integrate for v7. (1) **Hyperliquid** (https://api.hyperliquid.xyz) is free, US-accessible, returned 200 on l2Book, candleSnapshot, and fundingHistory in live probes; it is the cleanest unblock for the v6 "Binance.com 451" problem for forward-recorded L2 plus retrospective 1h candles and 1h funding. (2) **the-odds-api 20K tier at $30/mo** is the only paid item worth the budget; historical odds back to 2020 across major sportsbooks unlocks the v6 deferred sports-line-movement angle. (3) **dYdX v4 indexer** (https://indexer.dydx.trade) is the free retrospective complement to Hyperliquid, exposing historical trades, candles, and funding (orderbook is current-state only). v6's $29 Coinglass Hobbyist plan is **not** worth buying because the public pricing page does not list tick-level L2 on Hobbyist; that tier starts at $299/mo Standard. Coinglass Hobbyist's value (1h funding history 180d) is fully duplicated by Hyperliquid free.

## 1. US-accessible L2 orderbook historical for crypto

The structural finding from v6 (no free US-accessible source for historical L2 below $350/mo Tardis) **remains true**. Hyperliquid and dYdX v4 expose L2 only at current state, so historical L2 still requires forward-recording or paid Tardis. v7 should accept this and either (a) forward-record L2 on Hyperliquid for 60 to 90 days (BTC-PERP, $1B+ daily volume, free), or (b) skip L2 entirely and use 1m candle plus funding plus on-chain features that ARE retrospectively available.

### Hyperliquid (https://api.hyperliquid.xyz)
- **ACCESS:** Free, no API key for /info POST endpoints. JSON RPC style.
- **US ACCESSIBILITY:** VERIFIED via probe from CA IP, l2Book and fundingHistory both 200 OK on 2026-05-25.
- **HISTORICAL DEPTH:** l2Book is current state only (20 levels per side). candleSnapshot exposes "5000 most recent candles" per docs (3.5 days at 1m; 208 days at 1h; deep at 1d). fundingHistory probe returned 1-hour funding rates with `time` and `premium` fields, deep history confirmed. No historical L2 endpoint.
- **RATE LIMITS:** Not publicly documented; "userRateLimit" query exists; informal community guidance is ~100 req/sec well-behaved.
- **WHAT IT UNLOCKS:** US-accessible BTC-PERP 1h funding history (substitute for Binance.com 451), 1m candle backtests, forward-recorded L2 imbalance and depth-change features. Probe sample: `{"coin":"BTC","time":1779746607537,"levels":[[{"px":"77262.0","sz":"8.11675","n":56},...]]}`.
- **VERDICT:** Top-3 integration. Free.

### dYdX v4 indexer (https://indexer.dydx.trade)
- **ACCESS:** Free, no API key for public endpoints.
- **US ACCESSIBILITY:** VERIFIED, /v4/orderbooks/perpetualMarket/BTC-USD returned 200 with full bids/asks payload from CA IP on 2026-05-25.
- **HISTORICAL DEPTH:** Orderbook current state only. **Historical trades, candles (1MIN/1HOUR/1DAY), and funding rates all exposed with fromISO/toISO range filters per docs.** No documented hard lookback cap.
- **RATE LIMITS:** Not publicly documented.
- **WHAT IT UNLOCKS:** Cross-exchange retrospective comparator (Hyperliquid plus dYdX gives two independent on-chain perp venues); historical trades by block height enables CVD reconstruction; historical funding parallel to Deribit interest_1h. Smaller venue (~$50M to $200M daily BTC vs $1B+ Hyperliquid) so probably noisier; useful as confirmation, not as primary.
- **VERDICT:** Top-3 integration. Free.

### Kraken / Bitstamp
- Both free, US-accessible, depth endpoints probed 200 OK. Kraken `/0/public/Trades?since=` exposes paginated deep trade history; useful only if Coinbase /trades 4-min lookback binds. Neither has historical L2. Lower priority than Hyperliquid/dYdX.

### Coinglass Hobbyist ($29/mo)
- **ACCESS:** Paid only ($29/mo), public-endpoint probe without key returned `{"code":"401","msg":"API key missing."}` confirming endpoint exists.
- **HISTORICAL DEPTH PER OFFICIAL PRICING PAGE:** Hobbyist gets 30 req/min, 80+ endpoints, 1m history 6 days, 1h history 180 days, daily all-time. **Tick-level L2 and L3 orderbook is NOT listed as a Hobbyist feature on the public pricing page; the "Tick-Level L2 & L3 Order Book" capability appears under Standard ($299/mo) and Professional ($699/mo).** This contradicts v6 Section 7's earlier assumption that Hobbyist might cover L2.
- **WHAT IT UNLOCKS AT $29:** 1h Binance.com funding rate history (US 451 workaround), 1h longs/shorts ratio, liquidations. ALL of this is duplicated by Hyperliquid funding plus DefiLlama plus free Deribit per v6 Section 7. **No marginal value at Hobbyist tier.**
- **VERDICT:** SKIP. Re-classified relative to v6: Coinglass Standard at $299 is the lowest tier that actually adds tick L2, OUT OF BUDGET.

### CoinAPI (https://www.coinapi.io)
- **ACCESS:** Free tier is one-time $25 credit, no recurring free quota. Lowest paid tier $79/mo Startup.
- **VERDICT:** OUT OF BUDGET monthly recurring; one-time $25 credit not worth the integration burden.

### Tardis.dev
- **VERDICT:** OUT OF BUDGET, confirmed in v6 Section 2 ($350/mo minimum). Unchanged.

### Amberdata
- **VERDICT:** Enterprise contact-sales, OUT OF BUDGET per v6 Section 8.

## 2. Sports line-movement time-series

### the-odds-api 20K ($30/mo) (https://the-odds-api.com)
- **ACCESS:** $30/mo Starter. Endpoint probe with `apiKey=test` returned 401 confirming the endpoint is reachable from CA.
- **US ACCESSIBILITY:** Yes.
- **HISTORICAL DEPTH:** "Historical Odds" is included on all paid tiers including $30 Starter. The Historical Sports Odds API per docs goes back to 2020. Coverage: 70+ leagues including NFL, NBA, MLB, NHL, soccer, MMA, US sportsbooks (DraftKings, FanDuel, BetMGM, Caesars, Pinnacle, Bovada).
- **RATE LIMITS:** 20,000 credits/month on $30 tier; each historical odds request typically 10 to 100 credits depending on parameters. Conservative budget: ~200 to 2000 historical snapshots/month.
- **WHAT IT UNLOCKS:** Direct test of v6 deferred angle: do sportsbook line movements lead Kalshi for game-resolution markets (KXNFLGAME, KXMLBGAME, KXNBAGAME) over 1 to 6 hour windows? This was Phase 1's flagged deferred angle and is the only paid item that buys a genuinely new data dimension at v7 budget.
- **VERDICT:** TOP-3 integration. $30 one-month buy is in budget.

### Other sportsbook sources
- **Pinnacle, OddsJam, Action Network**: OddsJam $100 to $400/mo OUT OF BUDGET; Pinnacle/Action no public API.
- **DraftKings / FanDuel unofficial endpoints** (`sportsbook-nash-usnj.draftkings.com`, `sbapi.dc.sportsbook.fanduel.com`): grey-area scraping, fragile, rate-limit unfriendly. Avoid.
- **OddsPortal**: Cloudflare + ToS forbid scraping.
- **Sportradar / Genius Sports**: enterprise, OUT OF BUDGET.

## 3. News and sentiment for sports/crypto

### GDELT 2.0 (https://api.gdeltproject.org, https://www.gdeltproject.org)
- **ACCESS:** Free, no key. Per gdeltproject.org/data.html, "the entire GDELT database is 100% free and open."
- **US ACCESSIBILITY:** Network-level note: api.gdeltproject.org **timed out** on three probe attempts from this CA machine over 15s each (curl exit 28). Could be transient outage, GeoDNS issue, or local network. Bulk-download URLs (15-min event files at http://data.gdeltproject.org/gdeltv2/) are widely mirrored. **Mark as "doubted US accessibility from this network" until re-probed; recommend retry from production host before committing.**
- **HISTORICAL DEPTH:** Bulk GKG and Event tables go back to 2015 (GDELT 2.0); 2.0 is real-time 15-min cadence.
- **RATE LIMITS:** Doc API soft-rate-limits ~30 sec between heavy queries; bulk download unrestricted.
- **WHAT IT UNLOCKS:** NLP-tagged sentiment + theme + tone for every news article in the database, indexed by time. For sports markets: news-event-driven movement features (injury announcements, team-related tone shifts). For crypto: macro/regulatory news tone alignment with KXBTCD.
- **VERDICT:** Free; high upside IF re-probe confirms access. Recommend testing from v7 build host before committing.

### NewsAPI.org / Alpha Vantage news
- NewsAPI: free 100/day with 1-month lookback and dev-only license (no production); Business $449/mo OUT OF BUDGET.
- Alpha Vantage NEWS_SENTIMENT: free 25/day, demo probe returned 200, ~2y archive, sentiment per ticker. Marginal fallback only.

### ESPN unofficial (site.api.espn.com)
- **ACCESS:** Free, no key. /apis/site/v2/sports/baseball/mlb/scoreboard returned 200 from CA with full leagues/events payload. /apis/site/v2/sports/football/nfl/teams/12/injuries returned 200.
- **HISTORICAL DEPTH:** Scoreboard historical via `dates=YYYYMMDD` parameter; injuries are current-state.
- **VERDICT:** Free and US-accessible. Use for sports KXNFLGAME / KXMLBGAME news/injury features. Free path for sports news.

### Social firehoses
- **X/Twitter Basic** $200/mo OUT OF BUDGET.
- **Bluesky** public.api searchPosts 403 from CA without auth; free signup unlocks key, Jetstream firehose (wss://jetstream2.us-east.bsky.network) open without key. Forward-record only, no historical archive. Low priority.
- **Mastodon, Pushshift Reddit**: thin signal or restricted access. Skip.

## 4. On-chain crypto signal sources

### Hyperliquid funding / OI / candles
- Covered in Section 1. Free, deep, US-accessible.

### DefiLlama (https://api.llama.fi)
- **ACCESS:** Free, no key. /v2/historicalChainTvl/Ethereum returned 200 with daily TVL since 2017-09-27.
- **WHAT IT UNLOCKS:** Stablecoin supply changes, chain TVL, DEX volumes; macro-on-chain features for v7 retrospective backtest on KXBTCD or KXETHD.
- **VERDICT:** Free, integrate.

### Other on-chain sources (lower priority)
- **Glassnode**: 401 without key; free tier thin; v5-C already tested null at daily cadence.
- **Bitquery**: GraphQL 401, free 100k req/mo with signup. SQL-over-chain useful for whale-tx features. Medium engineering cost; lower priority than Hyperliquid + DefiLlama.
- **Coinglass free tier**: anemic; Standard $299 OUT OF BUDGET.
- **Etherscan / blockchain.info / mempool.space**: free, all tested null in v5-C.
- **Velo Data**: 403 without key; News API alone $129/mo OUT OF BUDGET.
- **Coin Metrics community-api**: free, daily-only, tested null in v5.

## 5. Foundation model APIs (sketch only; full scope is another agent)

- **Anthropic Claude Haiku 4.5**: ~$0.25/M input, $1.25/M output. v4-G2 used Haiku, ~$0.50 per 200-sample backtest. Budget-friendly.
- **OpenAI gpt-4o-mini**: ~$0.15/M input, $0.60/M output. Cheaper than Haiku; v7 could comparison-baseline.
- **Hugging Face Inference API free tier**: rate-limited but free for small open-source models (Chronos-T5-tiny, ~$0).
- **Together AI / Replicate**: $0.20 to $0.80/M tokens for hosted Llama-3, Mistral. Bulk-cheap.
- **Time-series foundation models (TimesFM, Chronos, TabPFN)**: weights on HuggingFace, can run locally on CPU for small windows. $0.

## Verified live probes (this session, 2026-05-25)

```
hyperliquid /info l2Book BTC                 200  current L2 levels with px/sz/n
hyperliquid /info candleSnapshot BTC 1m      200  1m OHLCV array
hyperliquid /info fundingHistory BTC         200  1h funding+premium series
dydx /v4/orderbooks/perpetualMarket/BTC-USD  200  current L2 bids/asks
kraken /0/public/Depth?pair=XBTUSD           200  current L2
bitstamp /api/v2/order_book/btcusd           200  current L2
defillama /v2/historicalChainTvl/Ethereum    200  daily TVL since 2017
espn site.api .../mlb/scoreboard             200  current+date-param historical scoreboard
espn site.api .../nfl/teams/12/injuries      200  current injuries
the-odds-api /v4/sports?apiKey=test          401  endpoint reachable, needs paid key
coinglass /public/v2/funding                 200  endpoint reachable but key-gated
coinglass-v4 /futures/funding-rate/history   200  endpoint reachable but key-gated
alpha-vantage /query?function=NEWS_SENTIMENT 200  demo-key informational
glassnode /v1/metrics/transactions/...       401  paid key required
bitquery /graphql                            401  signup key required
polygon /v2/reference/news                   401  paid key required
okx /v5/market/history-trades                200  free, deep, US-accessible
gdelt /api/v2/doc/doc                        timeout (3 attempts, exit 28)  retry from prod host
bluesky public.api searchPosts               403  needs auth
velo /api/v1/exchanges                       403  paid key required
```

## Recommended top-3 data integration list

Total cost: **$30 one-time (1 month of the-odds-api Starter), $0 ongoing infra**. Leaves $30 of the $30 to $60 authorization unspent for retry/contingency.

1. **the-odds-api 20K Starter, $30 for one month**: buy ONE month, drain historical odds for the v6 deferred sports-line-movement angle on KXNFLGAME / KXMLBGAME / KXNBAGAME for the entire 2024-25 and 2025-26 seasons. After download, cancel. The historical archive does not expire after the subscription ends if cached locally. This is the only paid item worth the budget at v7 sample sizes.
2. **Hyperliquid /info (free)**: replace v6's Deribit interest_1h with Hyperliquid BTC-PERP fundingHistory (higher-volume venue, more honest signal), add forward-recorded L2 imbalance and depth-change features starting day 0 of v7 build. Retrospective 1m candle to T-30 horizon also.
3. **GDELT 2.0 (free, conditional on access retry)**: if api.gdeltproject.org responds from the v7 build host (this CA machine timed out, treat as transient), pull GKG news sentiment by hour for crypto and by team for sports. Falls back to ESPN injuries + scoreboard plus Alpha Vantage news sentiment 25/day if GDELT is dead.

**Not recommended:** Coinglass Hobbyist (re-classified after pricing-page audit: tick L2 is Standard tier $299 only, OUT OF BUDGET; Hobbyist's 180d 1h funding is fully duplicated by Hyperliquid free). CoinAPI, Tardis, Amberdata, Velo, NewsAPI, X all OUT OF BUDGET.

**Forward-recording reminder**: v6 already accepted that historical L2 is unobtainable below $350/mo. v7 must either (a) accept Hyperliquid current-state L2 forward-recorded over 60+ days for any depth-imbalance feature, or (b) skip depth-based features entirely and bet on candle + funding + on-chain + news features that ARE retrospectively available within budget.
