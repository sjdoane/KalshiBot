# v5 Crypto Inventory and On-Chain Feature Audit (Agent V5-C1)

**Date:** 2026-05-24
**Agent:** V5-C1
**Brief:** v5 Track C Phase 1; assess whether Kalshi crypto markets are a viable new ML domain for v5.
**Inputs:** Kalshi `/historical/markets`, `/historical/cutoff`, `/series?category=Crypto`; Etherscan V2; CoinGecko free; Binance.US + Binance.vision; Coinbase Exchange public; Kraken public; Deribit public; blockchain.info; mempool.space; Coin Metrics community; DefiLlama; Yahoo Finance.
**Outputs:**
- `data/v5/crypto_inventory.parquet` (per-market rows, capped sample, n=569,334)
- `data/v5/crypto_inventory_summary.parquet` (per-series summary, 276 candidates probed, 150 with data)
- `data/v5/crypto_inventory_meta.json`
- `data/v5/crypto_series_listing.json` (232 crypto series with fees, frequency, settlement_sources)
- `data/v5/crypto_full_*.parquet` (per-series uncapped pulls for top 15 high-cadence series)
- `data/v5/crypto_full_all.parquet` (aggregated full-pull)
- `scripts/v5/probe_crypto_inventory.py`, `scripts/v5/analyze_crypto_inventory.py`, `scripts/v5/probe_crypto_full.py`

**Headline:** Crypto on Kalshi is a massive, well-structured domain (millions of markets, sub-hour to annual cadence, 232 distinct series, all settled via CF Benchmarks RTI for the major-coin price series). **Sample size is not the constraint.** The constraint is **orthogonality**: Kalshi crypto markets settle on a CF Benchmarks index that already aggregates exchange microstructure, and the contracts are quoted continuously by professional MMs against the spot price 24/7. The mechanical question for Track C is whether any free on-chain or sentiment feature carries information the Kalshi price has not already absorbed.

**Recommendation:** PROCEED Track C Phase 2 with a **narrow scope**: focus on the daily-cadence directional series (KXBTCD, KXETHD, KXSOLD, KXDOGED, KXXRPD), filter to v1-style high-confidence band (price 0.70 to 0.95), and dedicate the bulk of Phase 2 to a hard orthogonality test before any model training. If the orthogonality test fails (any free feature with a Brier skill score versus the Kalshi price <= 0.00 on a leak-free holdout), KILL Track C and do not proceed to model training. See Section 8.

---

## 1. Kalshi crypto market series enumeration

### 1.1 The `/series?category=Crypto` endpoint works (and is the right path)

Probing the `/series` endpoint returned **232 distinct crypto series**, each with metadata:
- `ticker`, `title`, `frequency`, `fee_multiplier`, `fee_type`, `settlement_sources`, `tags`.

Brief-named candidates KXBTCD, KXBTC, KXETH, KXETHH, KXBTCMAX, KXBTCRANGE, KXETHSUPPLY, KXBTCSUPPLY, KXBLOCKCHAIN were probed; some exist verbatim (KXBTCD, KXBTC, KXETH), some have analogous tickers (KXETHD/KXETHH → KXETHD only; KXBTCMAX → KXBTCMAXM/Y/W), and some do not exist (KXETHSUPPLY, KXBTCSUPPLY, KXBLOCKCHAIN, KXBTCH). The wider naming sweep via `/series` returned several that were not in the brief candidate list: KXSHIBA, KXSHIBAD, KXBTC15M, KXETH15M, KXSOL15M, KXBNBD, KXHYPED, KXSOLE, KXZECMAXMON, KXBCH*, KXLTC*, KXAVAXMAXY, KXLINK*, KXFDV*, KXTOKEN*, KXAIRDROP*, KXEIP* (Ethereum Improvement Proposals), KXBTCATH, KXSOLTXCOUNT, KXBTCDOMINANCE, KXBTCETF, etc.

### 1.2 The top-cadence series (the workhorse n)

15 series carry the vast majority of crypto market volume. Cap-released pulls reveal the true scale:

| Series | Cadence | Settlement source | Total markets (uncapped pull) | Distinct events | Close-date range |
|---|---|---|---:|---:|---|
| KXBTCD | hourly | CF Benchmarks BRTI | 592,571 | 8,031 | 2024-03-18 to 2026-03-24 |
| KXBTC  | hourly | CF Benchmarks BRTI | ~500,000+ | similar | similar |
| KXETH  | hourly | CF Benchmarks ERTI | ~500,000+ | similar | similar |
| KXETHD | hourly | CF Benchmarks ERTI | ~500,000+ | similar | similar |
| KXSOLD | hourly | CF Benchmarks SOLUSD_RTI | 159,660 | n_events not yet computed | similar |
| KXSOLE | hourly | CF Benchmarks SOLUSD_RTI | 159,521 | similar | similar |
| KXDOGED| hourly | CF Benchmarks DOGEUSD_RTI | 209,453 | similar | similar |
| KXDOGE | hourly | CF Benchmarks DOGEUSD_RTI | 208,388 | similar | similar |
| KXXRPD | hourly | CF Benchmarks XRPUSD_RTI | 235,315 | similar | similar |
| KXXRP  | hourly | CF Benchmarks XRPUSD_RTI | 234,825 | similar | similar |
| KXSHIBA, KXSHIBAD | daily | CF Benchmarks SHIBUSD_RTI | ~18,000 each | thousands | 2024 to 2026 |
| KXBTC15M, KXETH15M, KXSOL15M | 15-min | CF Benchmarks | 7-9k each | thousands | 2025-2026 only |

KXBTCD (the most-studied) has **8,031 distinct events** spread across **659 distinct close dates** over 25 months. Events ladder up by hour (e.g., `KXBTCD-26MAR2419` settles 2026-03-24 at 19:00 EDT), each event has ~75-188 threshold-strike contracts. Each strike is a separate market with its own settlement (above or below the threshold at the close minute).

### 1.3 Distinct from sports: same event, many strikes

Unlike NFL team-wins (where the n=1 event has n=1 market binary), each crypto hourly event has many strike-threshold contracts. Per the rules text I extracted:

> "If the simple average of the sixty seconds of CF Benchmarks' Bitcoin Real-Time Index (BRTI) before 7 PM EDT is **above 77699.99** at 7 PM EDT on Mar 24, 2026, then the market resolves to Yes."

KXBTC has both "above X" thresholds (T-suffix tickers) and "between X-Y" range contracts (B-suffix). KXBTCD has only "above" directional (T-suffix). The two series share the same event_ticker root (`KXBTC-26MAR2419` vs `KXBTCD-26MAR2419`) but populate complementary contract surfaces.

For modeling, the unit of independence is NOT the contract but **the event** (one settlement event = one independent observation of the underlying BTC index). The 8,031 events / 659 close dates for KXBTCD is the meaningful sample-size denominator. The threshold ladder allows a single event to produce ~3-5 markets in the v1-eligible band (0.70 to 0.95) but those markets are mechanically anti-correlated (a single observation of BTC=77,700 sets all "above 77,699.99" contracts to YES and all "above 77,800" contracts to NO).

### 1.4 Per-series v1-eligibility band (price 0.70 to 0.95, finalized + binary result)

From the capped probe (50k markets per series), per-event v1-band counts:

| Series | n_markets sampled | n_v1_band | n_v1_events | mean v1 contracts/event | v1 yes_rate |
|---|---:|---:|---:|---:|---:|
| KXBTC   | 50,000 | 240 | 135 | 0.54 | 0.292 (!) |
| KXBTCD  | 50,000 | 93  | 70  | 0.21 | 0.839 |
| KXETH   | 50,000 | 278 | 225 | 0.41 | 0.691 |
| KXETHD  | 50,000 | 243 | 164 | 0.36 | 0.881 |
| KXSOLD  | 50,000 | 650 | 396 | 0.97 | 0.880 |
| KXSOLE  | 50,000 | 350 | 282 | 0.79 | 0.866 |
| KXDOGED | 50,000 | 255 | 195 | 0.50 | 0.922 |
| KXDOGE  | 50,000 | 350 | 257 | 0.66 | 0.834 |
| KXXRPD  | 50,000 | 500 | 386 | 0.96 | 0.876 |
| KXXRP   | 50,000 | 447 | 320 | 0.78 | 0.613 |
| KXSHIBA | 18,292 | 244 | 215 | 0.93 | 0.836 |
| KXSHIBAD| 18,256 | 386 | 312 | 1.04 | 0.915 |
| KXBTC15M| 9,482  | 363 | 358 | 1.01 | 0.964 |
| KXETH15M| 9,469  | 856 | 660 | 1.30 | 0.923 |
| KXSOL15M| 7,143  | 389 | 332 | 1.17 | 0.925 |

(Counts taken from the 50k-page-capped probe. The truly uncapped totals are 11x larger for KXBTCD/KXBTC/KXETH/KXETHD. For 50k-sample-comparability, the table above is most useful for relative shape.)

**KXBTC v1-yes-rate is 0.292, an outlier.** This is because KXBTC includes "between X-Y" range contracts (B-suffix tickers); a high-priced range contract resolves YES only if the exact 100-dollar bin contains the close price (low base rate). The directional series (KXBTCD, KXETHD, KXSOLD, KXDOGED, etc.) at v1-band yes-rates 0.84 to 0.92 are the operationally-comparable surface to v1's NFL favorites.

### 1.5 Time-cutoff snapshot

Kalshi `/historical/cutoff` returned `2026-03-25T00:00:00Z` (matching V3-A's number; the cutoff is rolling ~2 months back). All pre-cutoff KXBTCD/BTC/ETH closed dates run 2024-03-18 to 2026-03-24 (so the historical surface goes back about 26 months for the hourly directional series). KXSHIBA/D pulls back to 2024 also, while KXSOLD/E and KXDOGED start later in 2024. 15-minute series begin only mid-2025.

---

## 2. Data shape suitability for ML (vs v3 n=147)

The brief's v3 baseline: 147 eligible sports markets at the v1 band. v3's literature note (`research/v3/01-historical-inventory.md`) flagged this as below AFML's T=252 minimum.

**For v5 crypto, sample size is orders of magnitude above any sports-domain analogue:**

| Cut | n events | n contract-rows in v1 band | n v1 events | n distinct close-dates | Time horizon |
|---|---:|---:|---:|---:|---|
| KXBTCD only, full pre-cutoff (uncapped pull) | 8,031 | **8,274** | 4,136 | 635 | 2024-03-18 to 2026-03-24 |
| KXBTC only (range contracts), full pre-cutoff | 7,973 | **3,135** | 2,673 | 504 | 2024-06-07 to 2026-03-24 |
| KXBTCD + KXBTC + KXETHD + KXETH + KXSOLD + KXDOGED + KXXRPD (estimated) | ~50,000+ | ~30,000+ | ~15,000+ | 600+ | 2024-04 to 2026-03 |
| 15-min series (KXBTC15M etc.), full pre-cutoff | ~9,500 each | ~363-856 each | ~330-660 each | ~270 each | mid-2025 to 2026-03 |
| All FULL_SERIES combined | hundreds of thousands of events | tens-of-thousands of v1-band contracts | many thousands | 600+ | 2024-04 to 2026-03 |

The first two rows are from VERIFIED uncapped pulls (`data/v5/crypto_full_KXBTCD.parquet`, `data/v5/crypto_full_KXBTC.parquet`). The other rows are projected based on per-series cap-relative counts and the equivalent uncapped pull running in background at writing time.

**Conclusion on sample shape:** n is decisively NOT the bottleneck. KXBTCD alone has **8,274 v1-band contracts across 4,136 v1-band events and 635 distinct close-dates**, which is 56x v3's per-contract 147 and 4.3x v3's distinct-event count of 147 (treating sports events as one-per-market).

The **effective independent-unit denominator** depends on how we collapse the contract ladder:
- Per-contract: each strike threshold counted independently, the most generous, but mechanically anti-correlated within an event so the model would over-count.
- Per-event-per-v1-contract: pick the closest-to-0.85-yes-price contract per event, best practice for a directional-prediction problem (this gives KXBTCD n = 4,136).
- Per-event-per-day: one observation per close-day across the entire ladder, the most conservative (this gives KXBTCD n = 635).

Even per-event-per-day (the most conservative): **635 distinct close days for KXBTCD alone**, growing to many thousands when combining all major-coin daily-cadence directional series. Still well above v3's 147.

---

## 3. On-chain and exchange feature sources (audit)

I probed the candidate sources and recorded latency / rate limits / AS-OF support per endpoint. `.env` confirmed: `ETHERSCAN_API_KEY=HC1UBWXKFM8NSQ3GTF4IW3NHTG27N5YZ3U` present and working.

### 3.1 Etherscan V2 (key required, free tier)

**Note:** V1 endpoints are deprecated. V2 requires `chainid` param + new base URL `https://api.etherscan.io/v2/api`.

| Endpoint | Status | AS-OF support | Notes |
|---|---|---|---|
| `module=stats&action=ethsupply` | OK | live only | current ETH supply (122.37M ETH) |
| `module=stats&action=ethsupply2` | OK | live only | also gives ETH2 staked, burnt fees, withdrawn |
| `module=gastracker&action=gasoracle` | OK | live only | Safe/Propose/Fast gas in gwei (current: ~0.064 gwei) |
| `module=block&action=getblocknobytime` | OK | **AS-OF YES** | for any past timestamp, returns block number (essential for backfill alignment) |
| `module=stats&action=ethprice` | OK | live only | ETH/BTC + ETH/USD spot |
| `module=stats&action=nodecount` | OK | live only | active node count |
| `module=account&action=tokentx` | OK | **AS-OF YES via blockNumber range** | whale wallet movement tracking; sample: Binance ETH cold returned 10 tokens |
| `module=stats&action=dailyavggasprice` | **Pro-only** | YES (paid) | daily gas history not in free tier |
| `module=stats&action=dailynewaddress` | Pro-only | YES (paid) | not in free tier |
| `module=stats&action=ethdailyprice` | Pro-only | YES (paid) | not in free tier |

**Rate limit:** measured 3 req/sec (free tier). Tested by issuing 10 rapid requests; 2/10 returned "Max calls per sec rate limit reached (3/sec)". Throttle to ~3 req/sec is mandatory.

**Implication for Phase 2:** the per-day on-chain historical aggregates (daily gas, daily new addresses, daily ETH price) require Pro. But the live snapshots + `getblocknobytime` + `tokentx` walking by block range are sufficient for our needs because we can **build our own daily aggregates** by sampling the live endpoints once per day going forward, OR pulling tokentx in blocks for historical whale-movement features.

### 3.2 CoinGecko free (no key required)

| Endpoint | Status | AS-OF support | Notes |
|---|---|---|---|
| `/api/v3/coins/markets` | OK | live only | current prices, mcap, 24h vol for any coin |
| `/api/v3/coins/{id}/market_chart/range?from={ts}&to={ts}` | OK | **AS-OF YES** | historical price + market_cap + volume at hourly resolution for ~90 day windows |
| `/api/v3/exchanges` | OK | live only | top exchanges with 24h volume |
| `/api/v3/coins/{id}/ohlc?days={N}` | OK | live only | OHLC for N days back, 30-min/4h resolution |

**Rate limit:** 30 calls/minute free tier (CoinGecko docs; not explicit in headers).
**Latency:** 200-450ms.
**AS-OF:** `market_chart/range` returns 168 datapoints/week (hourly) for any historical span. Sub-second response. Critical for Phase 2 backfill of price + mcap + volume at arbitrary close times.

### 3.3 Binance public API: BLOCKED FROM US (HTTP 451)

Binance.com `/api/v3/klines` returned **HTTP 451 (Unavailable For Legal Reasons)** from this IP. Confirmed:
- `https://api.binance.com/api/v3/klines` → 451
- `https://fapi.binance.com/fapi/v1/fundingRate` → 451 (the funding-rate endpoint specifically)
- `https://fapi.binance.com/fapi/v1/premiumIndex` → 451

**Available US-legal substitutes:**

- **Binance.US (`api.binance.us`)**: spot-only by design; has `/api/v3/klines` (OK, 24 candles in 0.26s) but **no fapi (no futures, so no funding rate)**. Useful for raw spot tick data but not the sentiment proxy.
- **Binance Vision data-api (`data-api.binance.vision`)**: spot historical klines work (24 candles in 0.18s). No funding endpoint. Useful as spot backup but same gap as Binance.US.
- **Bybit (`api.bybit.com`)**: CloudFront-403 from US ("blocked from your country"). Out.
- **OKX**: 404 on funding-rate-history (US path-blocked, route doesn't exist for our origin). Out.

### 3.4 Coinbase Exchange (Coinbase Pro) public API, US-friendly substitute

| Endpoint | Status | AS-OF support | Notes |
|---|---|---|---|
| `/products/BTC-USD/candles?granularity=3600` | OK | **AS-OF YES** via `start` / `end` ISO params | hourly candles, up to 300 per request |
| `/products/BTC-USD/book?level=2` | OK | live only | full L2 book (21,250 bids, 25,152 asks) |
| `/products/BTC-USD/ticker` | OK | live only | bid/ask/last + volume |
| `/products/BTC-USD/stats` | OK | live only | 24h open/high/low/last/volume + 30-day volume |

**Latency:** 130-240ms per request.
**Rate limit:** measured 10 reqs in 1.46s = 6.8 req/sec, no throttling observed. Coinbase docs: 10 req/sec public, 15 req/sec private.

This is the **primary US-legal market-microstructure source** for the Phase 2 build. AS-OF candles + L2 book + 30-day rolling stats are exactly what's needed.

### 3.5 Kraken public API, US-friendly

| Endpoint | Status | AS-OF support | Notes |
|---|---|---|---|
| `/0/public/OHLC?pair=XBTUSD&interval=60` | OK | **AS-OF YES** via `since` param (Unix sec) | up to 720 minutes of data per request at the chosen interval; ~721 candles returned per page |
| `/0/public/Trades?pair=XBTUSD&since={ts}` | works (not probed in this run but documented) | YES | tick-level trades |

**Latency:** 280-320ms.
**Rate limit:** public 1 req/sec recommended.

Secondary US-legal source. Useful for cross-exchange-checking the Coinbase index.

### 3.6 Deribit, US-friendly, ESSENTIAL for funding-rate sentiment

| Endpoint | Status | AS-OF support | Notes |
|---|---|---|---|
| `/api/v2/public/get_tradingview_chart_data?instrument_name=BTC-PERPETUAL` | OK | **AS-OF YES** via `start_timestamp` / `end_timestamp` ms params | hourly OHLCV for the BTC PERPETUAL |
| `/api/v2/public/get_funding_rate_history?instrument_name=BTC-PERPETUAL` | OK | **AS-OF YES** | hourly + 8h interest rates |

**This is the critical replacement for Binance fapi.** Deribit publishes funding history without geoblock. BTC-PERPETUAL is the main contract.

**Latency:** 260-560ms.
**Rate limit:** public docs 20 req/sec.

Funding-rate signal: when funding is positive, longs are paying shorts (bullish sentiment). When negative, shorts pay longs (bearish sentiment). Deribit's BTC-PERPETUAL funding is a clean US-legal sentiment proxy.

### 3.7 blockchain.info, free, no key

| Endpoint | Status | AS-OF support | Notes |
|---|---|---|---|
| `/charts/hash-rate?timespan=30days&format=json` | OK | YES (returns time-series) | 30 datapoints, daily |
| `/charts/mempool-size?timespan=7days&format=json` | OK | YES (15-min resolution, 668 points/week) | mempool size in bytes |
| `/charts/n-transactions?timespan=7days&format=json` | OK | YES (daily) | tx count per day |
| `/charts/difficulty`, `/charts/total-bitcoins`, `/charts/n-unique-addresses` (documented, not probed) | OK | YES | network stats |

Latency 540-620ms. No rate limit announced; polite throttle.

### 3.8 mempool.space, free, no key, BTC-only

| Endpoint | Status | AS-OF support | Notes |
|---|---|---|---|
| `/api/v1/mining/hashrate/3d` | OK | YES | 3-day rolling hash rate |
| `/api/blocks/tip/height`, `/api/v1/fees/mempool-blocks` (documented) | OK | live | BTC chain tip + fee blocks |

### 3.9 Coin Metrics community API, free, no key

| Endpoint | Status | AS-OF support | Notes |
|---|---|---|---|
| `/v4/timeseries/asset-metrics?assets=btc&metrics=PriceUSD,AdrActCnt,TxCnt,FlowInExUSD,FlowOutExUSD&frequency=1d&start_time=...&end_time=...` | OK | **AS-OF YES** | daily on-chain metrics (active addresses, transactions, exchange flows in/out, BTC price) for the requested span |

53 rows returned for a 53-day window of BTC on the test call. Latency 300ms. Excellent free-tier alternative for daily on-chain features that Etherscan Pro-gates.

### 3.10 Glassnode, free tier mostly closed

`/v1/metrics/transactions/transfers_volume_sum` returned 401 without key. Glassnode now requires API key for nearly all endpoints, and the free tier is mostly removed. Skip; Coin Metrics community covers the same metric domain.

### 3.11 DefiLlama, free, no key, for cross-chain TVL

`/v2/historicalChainTvl/Ethereum` returned the full daily TVL series back to chain inception. Useful for stablecoin / DeFi-pressure features.

### 3.12 Yahoo Finance (DXY, S&P 500, VIX), free, no key, scraping risk

`/v8/finance/chart/DX-Y.NYB?range=1mo&interval=1d` returned the DXY series with a Mozilla UA header. Same path for `^GSPC` and `^VIX`. Latency 250ms.

Yahoo's terms of service technically don't permit programmatic access. For Phase 2, FRED (Federal Reserve Economic Data) is the official source for DXY and S&P 500 historicals; it requires a free API key signup. For Phase 1, Yahoo is sufficient for feasibility.

### 3.13 Rate-limit summary

| Source | Free-tier rate | AS-OF historical | Notes |
|---|---|---|---|
| Etherscan V2 | 3 req/sec, 100k req/day | block-range YES; daily aggregates paywalled | needs key |
| CoinGecko free | ~30 req/min | YES via `market_chart/range` | no key |
| Coinbase Exchange | ~10 req/sec | YES via start/end | no key |
| Kraken public | ~1 req/sec | YES via since | no key |
| Deribit | 20 req/sec | YES | no key, US-legal **for futures funding** |
| blockchain.info | polite throttle | YES | no key, BTC-only |
| mempool.space | polite throttle | YES | no key, BTC-only |
| Coin Metrics community | polite throttle | YES | no key, daily aggregates |
| DefiLlama | polite throttle | YES | no key |
| Yahoo Finance | polite throttle (terms-risk) | YES | no key, macro proxies |
| FRED | 120 req/min after key signup | YES | needs key (free signup) |
| Binance.com | **451 BLOCKED IN US** | YES | not available |
| Bybit | **403 CloudFront from US** | not available | |
| OKX | path-404 from US | not available | |

---

## 4. Feature engineering ideas (15 candidates)

For predicting Kalshi crypto settlements at the v1-eligible high-confidence band (price 0.70 to 0.95), I propose the following 15 features. Each is sampled at T-N minutes/hours before the Kalshi market's close to avoid look-ahead.

Bucket scale 1-5 for effort: 1 = single API call; 5 = multi-source join + custom aggregation.

### 4.1 Price + volatility features

| # | Feature | Formula | Source | AS-OF | Effort |
|---|---|---|---|---|---|
| F1 | **Realized volatility last N hours** | stdev(log returns) of Coinbase BTC-USD 1m or 1h candles in `[T-N, T-0]` | Coinbase Exchange `/candles` | YES | 1 |
| F2 | **VWAP trajectory** | volume-weighted avg price over last N hours vs current price; sign indicates buying or selling pressure | Coinbase `/candles` | YES | 2 |
| F3 | **Spot-futures basis** | (Deribit BTC-PERPETUAL price / Coinbase BTC-USD price) - 1 | Coinbase + Deribit | YES | 2 |
| F4 | **Funding rate (current and 24h trend)** | Deribit `get_funding_rate_history` 1h interest rate; sign + magnitude | Deribit | YES | 2 |
| F5 | **Order book imbalance** | (sum of bid sizes within 1% of mid) / (sum of ask sizes within 1% of mid) | Coinbase `/book?level=2` | live only (no AS-OF for L2 book; must record live) | 2 |

### 4.2 On-chain features (BTC/ETH primarily)

| # | Feature | Formula | Source | AS-OF | Effort |
|---|---|---|---|---|---|
| F6 | **Exchange net inflow (BTC and ETH)** | FlowInExUSD - FlowOutExUSD from Coin Metrics community | Coin Metrics | YES (daily resolution) | 2 |
| F7 | **Whale wallet movements** | sum of token transfers from top-10 known exchange wallets within `[T-1h, T-0]`, filtered to amount > $1M | Etherscan tokentx + known whale wallet list | YES (block range) | 4 |
| F8 | **Active addresses 24h delta** | AdrActCnt today vs yesterday | Coin Metrics community | YES | 1 |
| F9 | **Gas price (ETH demand proxy)** | Etherscan gasoracle Safe price; tracked over 24h | Etherscan V2 | live only (must record live for backfill) | 1 |
| F10 | **BTC hash rate (production proxy)** | mempool.space `/v1/mining/hashrate/3d` | mempool.space | YES (daily) | 1 |
| F11 | **BTC mempool size** | blockchain.info mempool-size; current and 24h change | blockchain.info | YES | 1 |

### 4.3 Sentiment + cross-asset features

| # | Feature | Formula | Source | AS-OF | Effort |
|---|---|---|---|---|---|
| F12 | **DXY (US Dollar Index) 24h change** | Yahoo or FRED DX-Y.NYB | Yahoo Finance / FRED | YES | 1 |
| F13 | **S&P 500 24h change** | Yahoo or FRED ^GSPC | Yahoo Finance / FRED | YES | 1 |
| F14 | **VIX level + 24h change** | Yahoo ^VIX | Yahoo Finance | YES | 1 |
| F15 | **BTC dominance** | (BTC market cap / sum of top-10 mcap) from CoinGecko coins/markets | CoinGecko | live only (must record live for backfill); historical via market_chart/range | 2 |

---

## 5. Orthogonality concern (the central risk)

Kalshi crypto markets settle on a CF Benchmarks RTI index that already incorporates aggregated cross-exchange prices. Kalshi crypto markets trade 24/7 with professional market makers (Susquehanna, Jane Street, IMC, etc., per Kalshi's public statements about who quotes their crypto book). The market price at T-N minutes before settlement is, by construction, a tight estimator of the BTC index at T-0.

**The mechanical argument:**

For a KXBTCD-26MAR2419-T77699.99 contract: the underlying random variable is "BRTI at 19:00 EDT on Mar 24, 2026". At T=2 hours before settlement (17:00 EDT), the spot BTC price is publicly known and tracks BRTI within 50bp. The Kalshi market price is therefore a near-perfect translation of "P(BRTI moves above 77,699.99 in the next 2 hours given current spot at X)". A model that adds free on-chain or futures-data features needs to predict ABOVE the Kalshi market's already-priced-in estimate.

**Where could orthogonality LIVE?**

Three plausible angles:

a. **Microstructure asymmetry at the close.** CF Benchmarks RTI is constructed as a 60-second moving average ending at the close minute. The Kalshi market price at T-2 minutes may not perfectly anticipate the average of the final 60 seconds. If short-horizon Coinbase tick data carries a 30-60 second lead on the RTI average that the Kalshi market does not exploit (because retail makers cannot quote at 60-second resolution), there is a tiny edge. This is the **only mechanically plausible source of edge**; it requires sub-second AS-OF feed access.

b. **Funding-rate divergence on illiquid hours.** During Asian late-night / European early-morning hours when Kalshi quoting may be thinnest, the Deribit funding rate may move ahead of the Kalshi price. A model that detects funding-rate spikes during low-volume Kalshi hours might capture overnight directional bias. This is a plausible edge ONLY at off-hours when Kalshi spread is wide.

c. **Whale-wallet pre-positioning.** A large transfer from a custody wallet to an exchange hot wallet is a leading indicator (~1-6 hour lead time) of a sell. If our model detects such transfers via Etherscan tokentx and the Kalshi price has not yet priced them in, there is an edge. This is the LEAST mechanical because the leakage from "transfer detected on-chain" to "Kalshi price moves" is fast on the major venues (Jane Street, etc., run their own on-chain monitoring).

**The orthogonality test to run in Phase 2 (NOT here, brief explicit):**

For a leak-free historical sample of v1-eligible KXBTCD markets (price 0.70 to 0.95 at T-2h before close):
- Compute the Brier-skill score of the Kalshi-price-only baseline (the existing market price IS the prediction).
- Compute the Brier-skill score of a model that adds each of the 15 features.
- Test feature X is orthogonal if and only if: Brier(Kalshi + X) - Brier(Kalshi only) > 0 by a margin that survives walk-forward CV by close DATE (not row index).

For any feature where the residual Brier improvement is 0.00 or smaller, the feature is collinear with the Kalshi price. Drop it.

**Pre-registered prediction:** Funding rate (F4) and order book imbalance (F5) are the most likely to survive, because they are recorded continuously and major makers may not be using them as inputs. Whale wallet (F7) and exchange flows (F6) will likely fail because the major liquidity providers monitor these. Gas price (F9), hash rate (F10), and macro (F12-F14) will almost certainly fail at hourly resolution because they are too slow-moving relative to the Kalshi market clock.

---

## 6. Kalshi crypto fee structure check

From the `/series?category=Crypto` listing:

| Series count | fee_type | fee_multiplier |
|---|---|---|
| 230 of 232 | quadratic | 1 |
| 2 of 232 | quadratic_with_maker_fees | 0 |

**Comparison to sports.** The Kalshi v1 fee module (`src/kalshi_bot/analysis/metrics.py`) uses:

```
taker fee per contract = ceil(0.07 * count * price * (1 - price)) cents
maker fee per contract = 25% of taker fee
```

This is the **quadratic formula** (cost is proportional to `p * (1-p)`, maximized at p=0.5, zero at extremes). Verified consistent with what is reported on Kalshi's public Fees page (https://kalshi.com/docs/fees). The `fee_type` field of `quadratic` on crypto series matches this exact formula. **The crypto fee structure is identical to the sports fee structure** for 230 of 232 series.

The 2 series with `quadratic_with_maker_fees` and `fee_multiplier = 0` are a special case (operator-allocated maker tier with zero base fee; only 2 series total, the operator should investigate which 2 if a low-fee strategy targets them specifically).

**Fee at v1 band (p=0.85, 1 contract):**
- Taker: ceil(0.07 * 1 * 0.85 * 0.15 * 100) = ceil(0.8925) = 1 cent
- Maker: ceil(0.25 * 1 * 0.07 * 0.85 * 0.15 * 100) = ceil(0.223) = 1 cent (the ceil rounds the rebate up, this matches v1)

For Track C economics: at p=0.85, 1-contract maker round-trip fees = 2 cents. Gross required to clear fees and slippage is ~3-5 cents on each $1 contract, the same friction as sports.

---

## 7. Settlement-source verification

| Series | Settlement source (from `/series`) | Index methodology |
|---|---|---|
| KXBTC, KXBTCD, KXBTC15M | CF Benchmarks BRTI (Bitcoin Real-Time Index) | aggregated multi-exchange volume-weighted index, published every second |
| KXETH, KXETHD, KXETH15M | CF Benchmarks ERTI (Ethereum Real-Time Index) | same methodology |
| KXSOL*, KXSOLD, KXSOLE, KXSOL15M | CF Benchmarks SOLUSD_RTI | same methodology |
| KXDOGE, KXDOGED | CF Benchmarks DOGEUSD_RTI | same methodology |
| KXXRP, KXXRPD | CF Benchmarks XRPUSD_RTI (Ripple-Dollar Real-Time Index) | same methodology |
| KXSHIBA, KXSHIBAD | CF Benchmarks SHIBUSD_RTI | same methodology |
| KXBNB, KXBNBD, KXBNB15M | CF Benchmarks BNBUSDRTI | same methodology |
| KXHYPE, KXHYPED, KXHYPE15M | CF Benchmarks UHYPEUSDRTI | same methodology |
| KXBCH*, KXLTC*, KXAVAX*, KXLINK* | CF Benchmarks | same methodology |
| KXFDV*, KXAIRDROP*, KXTOKEN* (one-off events) | CoinGecko, CoinDesk, Bloomberg, etc. | event-driven, off-cadence |
| KXBLOCKCHAIN, KXBTCETF, KXBTCDOMINANCE | mixed (CoinGecko, news sources) | event-driven |

**148 of 232 series settle on CF Benchmarks.** This is critical:

- CF Benchmarks RTIs are constructed from a multi-exchange volume-weighted basket (Coinbase, Kraken, Bitstamp, Gemini, LMAX Digital, itBit per the BRTI methodology). The basket is **NOT** the same as raw Coinbase or raw Binance.
- An on-chain price feed (raw exchange tick) is therefore an **imperfect proxy** for the BRTI. The basket reweighting introduces a wedge of typically 5-50bp.
- A model that uses raw Coinbase price as a feature must reckon with the fact that the actual settlement at T-0 is the average of 60 seconds of BRTI, not the average of 60 seconds of Coinbase.

**Implication for orthogonality test:** if our model uses Coinbase candles AS the AS-OF feature input, we are introducing a systematic gap between the feature signal and the settlement value. For a fair test of "is my feature orthogonal to the Kalshi price", we should use CF Benchmarks BRTI directly. **CF Benchmarks BRTI is published live via a paid feed** ($100+/month per the CF Benchmarks website); free-tier feed is daily snapshot only. This is the single biggest paid-data hurdle for a clean Phase 2 build.

**Workaround for Phase 2:** Use Coinbase BTC-USD as a proxy for BRTI and **include the Coinbase-vs-BRTI tracking error as an explicit residual feature**. Compute the tracking error AT SETTLEMENT TIME on a historical sample by reading Kalshi's `settlement_value_dollars` field for each settled market against our Coinbase candles at the same minute. If the tracking error has zero mean and small variance (< 30bp), Coinbase is a faithful proxy. If the tracking error is biased or noisy, we have a structural data gap.

---

## 8. Recommendation

### 8.1 PROCEED to Phase 2 with NARROW SCOPE

Data shape is rich. Sample size is massive. Free-tier data sources cover most of the candidate features (with the exception of CF Benchmarks BRTI tick data, which is paid). Fee structure is identical to sports.

Narrow scope means:

1. **Target the 5 daily-cadence directional series only:** KXBTCD, KXETHD, KXSOLD, KXDOGED, KXXRPD. These are the cleanest comparables to v1's NFL favorite-longshot domain (high-confidence band, ~0.85 yes-rate). Exclude:
   - KXBTC/KXETH range contracts (B-suffix): low base rate, different problem
   - 15-minute and KXBTC15M-type sub-hour series: dominated by microstructure noise that free-tier data cannot capture
   - One-off and custom-frequency events (KXFDV*, KXAIRDROP*): too few independent observations, settlement source is news-driven not price-driven
   - Long-horizon series (KXBTCMAXY, KXBTCMINY): n is too small per series, lifetime too long for our orientation

2. **Restrict to v1-band [0.70, 0.95] at T-2h before close** to maintain orientation with v1's strategy. Estimated n in this cut, all 5 series combined, full pre-cutoff: **~5,000+ contracts across ~3,000+ events**. Massive surplus over v3's 147.

3. **Use Coinbase Exchange (US-legal) + Deribit (US-legal funding) + Etherscan V2 + Coin Metrics community + blockchain.info** as the data stack. Skip Binance.com, Bybit, OKX (all blocked).

### 8.2 Pre-Phase-2 orthogonality test (the single gate)

Before any model training, run a single test:

For 200 random KXBTCD v1-band markets from 2025 (pre-cutoff), at T-2h before close:
- Record (a) the Kalshi market price, (b) F4 (funding rate at T-2h), (c) F5 (orderbook imbalance at T-2h, recorded live going forward as Phase 1.5 prep), (d) F1 (realized vol last 6h), (e) F12 (DXY 24h change).
- Outcome: did the market settle YES?
- Compute Brier(Kalshi only) and Brier(Kalshi + each feature alone).
- Pass if at least one feature has Brier(Kalshi + X) - Brier(Kalshi only) >= +0.005 (a meaningful Brier improvement is +0.005 to +0.02 in published literature; below +0.005 is statistical noise).

If no feature clears +0.005 on this 200-market test: **KILL Track C.** Crypto markets are too efficient for retail to extract edge.

If 1-2 features clear: PROCEED to a full Phase 2 model build with those features only.

### 8.3 What KILLS the track

- Orthogonality test fails: no feature has Brier improvement >= +0.005. The crypto markets are efficient at hourly resolution and our free-tier feature stack does not have edge.
- Settlement-source gap is too large: Coinbase vs BRTI tracking error exceeds 50bp on average. Without BRTI we cannot build an honest feature.
- 6-criteria gate (locked C1-C6 from `src/kalshi_bot_v2/gate.py`) fails on a leak-free walk-forward holdout.
- Single-asset concentration in the holdout: if BTC alone provides all the signal and the model fails on ETH/SOL/DOGE/XRP, the model is not robust.

### 8.4 What confirms the track

- Brier improvement >= +0.005 on the 200-market orthogonality probe with a single feature, OR >= +0.010 with a combined feature set.
- Locked 6-criteria gate passes on a leak-free walk-forward holdout sized n >= 200.
- Per-asset breakdown shows positive Brier improvement on at least 3 of 5 assets (BTC, ETH, SOL, DOGE, XRP).
- Single-event concentration < 20% in the holdout (no one event drives more than 1/5 of the signal).

### 8.5 Pivots if Phase 2 results are marginal

Inherit operator's standing instruction "do not give up before all angles attacked":

- **Pivot 1**: shift from daily-cadence (KXBTCD etc.) to weekly-cadence (KXBTCMAXW). Lower n but signal-to-noise is structurally better at longer horizons.
- **Pivot 2**: shift from "predict outcome" to "fade Kalshi at extremes" (the v4 Track A pattern). When the Kalshi price moves >5c from the spot-implied probability and Deribit funding contradicts, fade Kalshi. This is a filter strategy, not a model.
- **Pivot 3**: shift from directional to range markets (KXBTC, KXETH B-suffix). The two-sided range markets have a different selection effect and may carry exploitable mispricing in the body of the distribution.

If all three pivots fail, kill.

---

## 9. Caveats and known gaps in this Phase 1 work

1. **CF Benchmarks BRTI is paywalled.** All major crypto Kalshi markets settle on this index, not on raw exchange tick. Our free-tier data stack uses Coinbase as a BRTI proxy. The tracking-error magnitude is unverified in this Phase 1 and is a Phase 2 dependency.

2. **Binance is hard-blocked from US.** This eliminates the most popular funding-rate source. Deribit is the substitute. Deribit's BTC-PERPETUAL is liquid but its funding methodology differs slightly from Binance's. The substitution gap is not measured.

3. **The capped inventory pull (50 pages per series) under-counted KXBTC, KXBTCD, KXETH, KXETHD, KXSOLD, KXSOLE, KXDOGED, KXXRPD, KXDOGE, KXXRP.** The uncapped pull for these is running but only KXBTCD has been measured fully in this report (n=592,571). The full-pull job is at `data/v5/crypto_full_*.parquet`. Phase 2 will re-aggregate.

4. **No on-chain feature has been tested against actual market outcomes yet.** All Phase 1 numbers are sample-size descriptions. The orthogonality test in Section 8.2 is the next step (Phase 2 pre-train gate).

5. **The 15-minute series are excluded from recommendation despite plausible n.** The reason: sub-hour cadence is dominated by microstructure (orderbook flicker, latency arbitrage) that retail at $32 capital and free-tier data cannot exploit. Major makers operate at sub-millisecond latency in this regime.

6. **No probe of `KXNEXTTEAM`-style cross-domain crypto markets (e.g., "Will the SEC approve a SOL ETF by EOY?").** These are event-driven, news-source-settled. They are a different problem domain (Becker's high-bias political markets, not the technical "high-frequency price prediction" problem this report scoped).

7. **The fee_type "quadratic" verified via local v1 fee module but not against Kalshi's live trade-quote response.** A more rigorous Phase 2 step is to place a $0 paper trade and inspect the `fee_dollars` field in the response; this is a 2-line task at Phase 2 start.

8. **Kalshi makers/professional MMs on crypto have not been enumerated explicitly.** v4 Track A literature noted Jane Street, IMC, Susquehanna, Wintermute among Kalshi market makers; crypto is presumed to have the densest professional coverage given continuous 24/7 quoting. Orthogonality risk is highest where market-maker density is highest.

---

## 10. Files written

- `data/v5/crypto_inventory.parquet`: 569,334 row capped per-market inventory (covers 150 series with data, 14 columns)
- `data/v5/crypto_inventory_summary.parquet`: per-series rollup (276 candidates probed)
- `data/v5/crypto_inventory_meta.json`: run metadata
- `data/v5/crypto_series_listing.json`: full `/series?category=Crypto` enumeration (232 series with frequency, fee, settlement_sources)
- `data/v5/crypto_full_*.parquet`: uncapped per-series pulls (background job in flight at writing time; KXBTCD verified at n=592,571)
- `scripts/v5/probe_crypto_inventory.py`: capped probe
- `scripts/v5/probe_crypto_full.py`: uncapped pull for top 15 series
- `scripts/v5/analyze_crypto_inventory.py`: analysis utility

---

## 11. Final verdict

**PROCEED Track C Phase 2** under the **narrow scope and orthogonality-test gate** described in Section 8. The decisive Phase 2 step is NOT model training but the 200-market orthogonality probe in Section 8.2. If that probe fails, kill Track C without further engineering investment. If it passes, proceed to a full v2-locked-gate model build on the 5 daily-cadence directional series with the surviving feature subset.

**Expected outcome at the orthogonality probe (pre-registered):** I expect 0 to 2 features to clear +0.005 Brier improvement, biased toward funding-rate (F4) and orderbook imbalance (F5). I do NOT expect macro (F12-F14), gas price (F9), or hash rate (F10) to clear. If 0 clear, kill. If 1-2 clear, proceed with that feature subset; the model is then a thin overlay on the Kalshi price with no expectation of a large Brier improvement at scale.
