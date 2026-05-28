# V6 Data Feasibility Audit (Phase 1, Agent B)

**Date:** 2026-05-25
**Scope:** Per-source verification that v6 features fit a $30-60 one-time budget. Live probes preferred.
**Inherited constraint:** v5 Killer Finding 2c, backtest features must use bid/ask AT SAMPLE TIME, never `last_price_dollars`.

## 1. ccxt for Binance L2

**FREE TIER:** ccxt itself is free. `fetch_order_book()` returns CURRENT snapshot only. `fetch_funding_rate_history()` exists but Binance.com is geo-blocked from US (HTTP 451 verified). `binanceus` works for current spot L2 + 1m klines + recent aggTrades; no perpetuals.

**PAID TIER:** N/A.

**LIMITATIONS:** L2 historical orderbook NOT exposed (`hasattr(ccxt.binance, 'fetchOrderBookHistory') == False`). ccxt is a trading wrapper, not a historical archive.

**VERIFIED:** `api.binance.com -> 451`, `api.binance.us/api/v3/depth -> 200 (current state)`, `ccxt.binanceus().fetch_order_book('BTC/USDT', limit=5)` returns current only with no timestamp.

**GAP:** Historical L2 unavailable; must record forward or pay tardis/coinglass.

## 2. Tardis.dev

**FREE TIER:** No always-free tier. Sample CSVs on docs page require contact-sales for trial.

**PAID TIER:** Academic $350-650/mo, Solo $700-1,200, Professional $900-2,200, Business $2,500-6,000. Monthly billing grants 4 months historical lookback.

**LIMITATIONS:** Minimum cost 6x to 22x the v6 budget.

**VERIFIED VIA WEBFETCH:** Pricing page on tardis.dev. Lowest published price $350/mo.

**VERDICT:** Out of budget.

## 3. Coinbase Exchange public API

**FREE TIER:** `/products/BTC-USD/candles?granularity=60` returns 1m OHLCV, 300 candles per call, lookback verified to 90+ days. `/products/BTC-USD/book?level=2` returns current L2 (50+ levels). `/products/BTC-USD/trades?limit=1000` returns recent ~4 minutes. WebSocket feed for live recording.

**PAID TIER:** N/A.

**LIMITATIONS:** L2 historical NOT exposed; only current state. `/trades` lookback ~minutes, not days. Rate limit 10 reqs/sec public.

**VERIFIED:** All endpoints 200 OK on 2026-05-25.

**GAP:** Sub-hour Coinbase L2 NOT historically reconstructible. CVD computable forward only.

## 4. Deribit options public API

**FREE TIER:** Public unauthenticated. Rate limit ~20 reqs/sec/IP. Live endpoints expose current Greeks (delta/gamma/vega/theta/rho) + mark_iv + bid_iv + ask_iv per option via `/public/ticker`. Historical: `/public/get_volatility_index_data?currency=BTC&resolution=3600` returns DVOL OHLC time series (free, deep). `/public/get_funding_rate_history?instrument_name=BTC-PERPETUAL` returns 1-hour `interest_1h` and 8h cadence rates (free, deep).

**PAID TIER:** N/A.

**LIMITATIONS:** Greeks endpoint is CURRENT STATE ONLY. Historical 25-delta risk reversal NOT a single API call; must reconstruct via option-by-option OHLC + Black-Scholes inversion.

**METHOD (25-delta RR from free Deribit):**
1. Underlying S(t) from `/public/get_tradingview_chart_data?instrument_name=BTC_USD&resolution=60`.
2. Per option in `get_instruments(currency=BTC, expiry=T)`, OHLC at t from `get_tradingview_chart_data`.
3. Invert Black-Scholes (rate from `get_funding_rate_history`) to recover IV(K, t).
4. Numerically find K_call_25d (BS_delta=+0.25) and K_put_25d (BS_delta=-0.25).
5. RR_25d(t) = IV(K_call_25d, t) - IV(K_put_25d, t).

For live recording: batch `/public/ticker` over all 884 BTC options (45 sec under rate limit), interpolate IV across delta. Forward-only.

**VERIFIED:** `get_volatility_index_data` returns hourly DVOL OHLC. `ticker BTC-29MAY26-100000-C` returns `greeks{delta=1e-05, gamma=0, vega=0.00358, theta=-0.01026, rho=8e-05}` + `mark_iv=60.33`.

**GAP:** Historical 25d skew is reconstructable but engineering-heavy; DVOL is a free proxy for ATM-IV-level changes (NOT skew direction).

## 5. Binance funding rate

**FREE TIER:** `/fapi/v1/fundingRate` returns 8h-cadence history, paginated, 500 reqs / 5 min. NOT REACHABLE: US IP returns HTTP 451 verified.

**PAID TIER:** N/A.

**LIMITATIONS:** Geo-blocked. Bybit also CloudFront-blocks US.

**VERIFIED:** `fapi.binance.com -> 451`, `api.bybit.com -> blocked`.

**WORKING SUBSTITUTES:**
- **OKX** `/api/v5/public/funding-rate-history?instId=BTC-USDT-SWAP`: 200 OK, 8h cadence, ~33 day lookback per 100-row page, deep history via `before` pagination. Free, no auth.
- **Deribit** `BTC-PERPETUAL interest_1h`: 1-hour granularity (finer than 8h, matches v6 sub-hour requirement), free.

**VERDICT:** Use Deribit `interest_1h` for v6 funding-rate-delta feature. OKX as 8h-cadence comparator.

## 6. Kalshi historical KXBTCD

**FREE TIER:** `/historical/markets` and `/historical/trades` accessible with existing READ key. Per v1 production, low hundreds of reqs/min sustainable.

**`crypto_full_KXBTCD.parquet` SCHEMA (verified 592,571 rows total):** `ticker, series_ticker, event_ticker, open_time, close_time, status, result, last_price_dollars, volume_fp, settlement_value_dollars, last_price, volume, lifetime_hours`. ONLY contract-level summaries. NO bid/ask, NO minute snapshots.

**`/historical/markets` PROBE:** Returns ONE snapshot per ticker (188 distinct tickers in one event, 188 rows, each ticker has exactly 1 unique `updated_time` which is the POST-SETTLEMENT time). Snapshot DOES include `yes_bid_dollars, yes_ask_dollars, no_bid_dollars, no_ask_dollars, yes_bid_size_fp, yes_ask_size_fp, previous_yes_bid_dollars, previous_yes_ask_dollars, liquidity_dollars, volume_24h_fp, open_interest_fp`, BUT all values are at the final post-settlement state (typically yes_bid=0, yes_ask=1, no liquidity). NOT useful for backtesting mid-contract.

**`/historical/trades` PROBE:** Returns per-execution rows: `created_time, taker_book_side (bid|ask), taker_outcome_side, taker_side, yes_price_dollars, no_price_dollars, count_fp, trade_id, ticker`. One probe ticker had 10 trades across 4 distinct minutes. This is the ONLY minute-resolution Kalshi source. Reconstructable: per-minute last-trade price, signed CVD = sum(count_fp * (+1 if taker_book_side=='ask' else -1)), per-minute volume. NOT reconstructable: bid/ask between executions, resting depth, queue position.

**LIVE `/markets/{ticker}/orderbook`:** Returns full current-state L2 (`orderbook_fp.yes_dollars` and `no_dollars` arrays of `[price, size]` pairs). Forward-record only.

**Killer-finding consequence:** v6 backtest on settled contracts MUST restrict samples to minutes where a real trade printed, so the executable price is a real fill. Cannot infer Kalshi bid/ask at non-execution minutes from the parquet OR the historical endpoints.

## 7. Bookmap / Kaiko / CryptoCompare / Coinglass

- **Bookmap:** Desktop replay, not API-first. $99-$199/mo. Skip.
- **Kaiko:** Enterprise contact-sales. $9.5k-$55k/yr per Vendr / Datarade. Out of budget.
- **CryptoCompare:** Free `min-api/data/v2/histominute` (OHLCV only, verified). L2 historical at `data-api.cryptocompare.com/spot/v1/historical/orderbook/l2/...` returns 401 without paid key. Paid pricing opaque. Free tier insufficient for L2.
- **Coinglass:** HOBBYIST $29/month, 80+ endpoints, 30 reqs/min, includes funding history OHLC and "Tick-Level L2 & L3 Order Book" per pricing page. Within budget. **Best paid candidate.** Depth-tier coverage at Hobbyist not verified; assume L1-L5 sufficient.

## 8. Glassnode / Coin Metrics / Amberdata

- **Coin Metrics community-api:** v5 used `AdrActCnt`. No options skew, no funding delta. Daily cadence only. Free, no key.
- **Glassnode:** Free 7-10 on-chain metrics daily, 1-year lookback. No options skew, no sub-hour data.
- **Amberdata:** Advertises Deribit options skew, 25d RR, IV surface as paid endpoints. Pricing not public; enterprise-priced per Datarade. Skip; Deribit free path covers the same data.

## Recommended acquisition plan

**Total estimated spend: $0 free path first, then conditional $29 Coinglass after Phase 1.5 review.**

**Order:**
1. (Free, day 0): Drain Kalshi `/historical/trades` for all 8,274 v1-band KXBTCD. Bin to 1-minute. Compute Kalshi CVD + last-traded price + count.
2. (Free, day 0-1): Coinbase 1m candles AS-OF T-30/T-15/T-5 per contract, extending existing `coinbase_candles_for_window()` helper.
3. (Free, day 1): Deribit `interest_1h` history full date range, compute funding-rate delta over previous 3 hours.
4. (Free, day 1): Deribit `get_volatility_index_data` BTC hourly, compute DVOL term-structure delta as IV proxy.
5. (Phase 1.5 gate): Review whether free-source features clear orthogonality. If yes, no spend.
6. (Conditional $29): Coinglass Hobbyist for one month, fetch Binance BTC-USDT-PERP funding rate (US 451 workaround) plus tick-level L2 if depth-tier exposed.

**Features unlocked free:** Kalshi CVD, Coinbase candle features (realized vol, VWAP dev), Deribit funding 1h + delta, DVOL term structure, spot-futures basis. Phase 2 backtest on n ≈ 3,000-7,000 trade-minutes.

## HONEST flag list (features NOT acquirable within budget)

1. **Historical L2 orderbook on Binance/Coinbase at the v5-C 8,274-contract horizon.** Tardis $350/mo. Coinglass $29 MIGHT cover at Hobbyist; depth tier unverified.
2. **Historical Binance.com funding.** US 451. Substitute: Deribit `interest_1h` (finer) or OKX 8h. Largest-perp-by-volume substitution does shift the signal.
3. **Historical 25-delta risk reversal as single call.** Requires per-option BS inversion across hundreds of OHLCVs. Feasible but engineering-heavy (~6 hrs batch). DVOL is partial substitute (level not direction).
4. **Historical Kalshi bid/ask at non-execution minutes.** One post-settlement snapshot per ticker. Forward-record from Phase 2 only.
5. **Kalshi own orderbook history.** Same as (4).

**Phase 1.5 consequence:** v6 must split. **Backtest track** (Coinbase candles + Deribit funding + DVOL + Kalshi trade-derived CVD/last-price) restricted to trade-minutes, n ≈ 3-7k. **Forward-record track** (Binance/Coinbase OB imbalance + live 25d RR + Kalshi own OB) starts Phase 2 day 0, evaluable after 60-90 days, beyond v6's expected clock. Without forward-recording, OB imbalance and exchange-CVD features cannot be tested on v5-C history within budget. Phase 1.5 should drop them or flag as "forward-only" with no v6 verdict.

## Verified probe log

```
api.binance.com/api/v3/exchangeInfo            451  US-blocked
api.binance.us/api/v3/depth                    200  current L2, 20 levels
api.binance.us/api/v3/klines (1m)              200  works as Coinbase backup
fapi.binance.com/fapi/v1/fundingRate           451  blocks Binance funding
api.exchange.coinbase.com .../candles?60       200  1m OHLCV, 90d+ lookback
api.exchange.coinbase.com .../book?level=2     200  current L2
api.exchange.coinbase.com .../trades?limit=1k  200  ~4 min lookback
deribit /public/get_volatility_index_data      200  DVOL hourly, deep history
deribit /public/get_funding_rate_history       200  interest_1h, free
deribit /public/ticker BTC-...-C               200  current Greeks + IVs (NO history)
deribit /public/get_book_summary_by_currency   200  current state, 884 BTC options
okx /api/v5/public/funding-rate-history        200  8h cadence, free, deep
okx /api/v5/market/index-candles               200  1m index history, free backup
api.bybit.com                                  CF-country-blocked
api.coingecko.com/api/v3/derivatives           200  current funding only
min-api.cryptocompare.com .../histominute      200  free OHLCV, no L2
data-api.cryptocompare.com .../orderbook/l2/   401  paid only
Kalshi /historical/markets ?ticker=...         200  1 post-settlement row per ticker
Kalshi /historical/trades  ?ticker=...         200  per-execution, taker_book_side
Kalshi /markets/{ticker}/orderbook             200  live L2, forward-record only
```
