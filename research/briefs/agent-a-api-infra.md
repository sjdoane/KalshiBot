# Agent A Brief: Kalshi API and Infrastructure

Author: Research Agent A
Date: 2026-05-22
Topic: Kalshi REST/WebSocket API, fees, auth, client libraries, historical data, demo environment

## 1. API version and base URLs

Canonical version as of 2026-05-22: **v2**. No v3 announced in the public changelog through May 2026.

| Environment | Type | URL |
|---|---|---|
| Production | REST | `https://external-api.kalshi.com/trade-api/v2` |
| Production | WebSocket | `wss://external-api-ws.kalshi.com/trade-api/ws/v2` |
| Demo | REST | `https://external-api.demo.kalshi.co/trade-api/v2` |
| Demo | WebSocket | `wss://external-api-ws.demo.kalshi.co/trade-api/ws/v2` |

Legacy hosts `api.elections.kalshi.com` and `trading-api.kalshi.com` still resolve but Kalshi explicitly labels `external-api.*` as the "Recommended base URL." Use `external-api.kalshi.com` for new code.

## 2. Authentication (RSA-PSS signing)

Every authenticated request requires three headers:

- `KALSHI-ACCESS-KEY`: the Key ID returned at key creation
- `KALSHI-ACCESS-TIMESTAMP`: current Unix time in **milliseconds** (not seconds, this is a common gotcha)
- `KALSHI-ACCESS-SIGNATURE`: base64 of RSA-PSS-SHA256 signature of `timestamp + HTTP_METHOD + path`

Signature string construction:
- Concatenate: `<timestamp_ms_string> + <UPPERCASE_HTTP_METHOD> + <request_path_without_query_string>`
- Example: for `GET /trade-api/v2/portfolio/orders?limit=5`, sign `"1747938400000" + "GET" + "/trade-api/v2/portfolio/orders"`.
- Sign with RSA-PSS using MGF1+SHA256, salt length = digest length (32 bytes), then base64 encode.

Key creation: Settings -> API. Kalshi generates the RSA keypair and shows the private key **once** in PEM format. You cannot retrieve it again. The Key ID is the public identifier.

Key rotation: not formally documented as a workflow in the public docs. Mechanism is to generate a new key, deploy, then revoke the old one in the dashboard. Multiple active keys appear to be allowed (no documented per-account key cap). As of Dec 2025 keys also support a `scopes` field (`read`/`write`) for least-privilege.

## 3. Rate limits

Token-bucket model rolled out April 2025. Two independent buckets per account: **read** and **write**. Each request consumes a token cost (default 10, varies by endpoint; `GET /account/endpoint_costs` lists costs).

| Tier | Read tokens/sec | Write tokens/sec | Qualification |
|---|---|---|---|
| Basic | 200 | 100 | Default on signup |
| Advanced | 300 | 300 | Form submission |
| Premier | 1,000 | 1,000 | ~3.75% monthly exchange volume |
| Paragon | 2,000 | 2,000 | Higher volume |
| Prime | 4,000 | 4,000 | ~7.5% monthly exchange volume |

(Per-second request equivalents for Basic: ~20 reads/s, ~10 writes/s at default 10-token cost.) Bucket capacity ~2 seconds of budget for most tiers; Basic holds only 1 second (no burst).

Overage: returns **HTTP 429** with body `{"error":"too many requests"}`. **No `Retry-After` or `X-RateLimit-*` headers** are emitted. Exponential backoff is the documented mitigation. No documented IP ban for transient bursts. WebSocket rate limits are not numerically published.

## 4. Fees (numbers, current as of Feb 2026 schedule)

### Trading fees per contract (in dollars)

- **Taker fee**: `ceil(0.07 * C * P * (1 - P) / 0.01) * 0.01` per contract, where `C` = contract count for that fill, `P` = fill price in dollars (0.01 to 0.99). Practical form: per-contract taker fee = `ceil(7 * P * (1-P))` cents. Max = $0.0175/contract at P=$0.50.
- **Maker fee**: 25% of taker = `ceil(0.0175 * C * P * (1 - P) / 0.01) * 0.01`. Max ~$0.0044/contract at $0.50. Resting (unfilled) orders pay nothing.
- Rounding: trade fee rounded up to nearest centicent ($0.0001), then balance floored to cent; a fee accumulator carries the sub-cent overcharge and issues a $0.01 rebate whenever it crosses $0.01.
- Special-event markets (elections, major sports) can have **bespoke higher fee schedules**, published per-market. Confirm before strategy assumes the standard 7%.

### Deposit fees

| Method | Fee | Min | Speed |
|---|---|---|---|
| ACH | $0 | None documented | 1 to 3 business days |
| Wire | $0 from Kalshi (your bank may charge $15 to $30) | $1,000 (returns below) | Same day |
| Debit card | Up to 2% (Kalshi); some third-party blogs cite 2.9% + $0.30 (likely outdated/wrong) | None | Instant |

### Withdrawal fees

| Method | Fee | Speed | Notes |
|---|---|---|---|
| ACH | $0 | 1 to 3 business days | 3-day hold if debit-funded, 7-day if same-bank ACH, 30-day if cross-bank |
| Wire | $0 from Kalshi | Same day | Minimum $500,000; not available for smaller amounts (effectively wire withdrawal is institutional-only) |

### Settlement fees

**Zero.** Winners receive $1.00/contract, losers receive $0.00. No exchange fee at settlement.

### Fee-drag worked examples

**Trade 1 (winning, taker):** Buy 10 contracts at $0.55, market resolves YES, position pays out $1.00/contract.
- Entry fee: ceil(7 * 10 * 0.55 * 0.45) cents = ceil(17.325) = **$0.18**
- No exit fee on settlement
- Gross P&L: ($1.00 - $0.55) * 10 = $4.50
- Net P&L: $4.50 - $0.18 = **$4.32**
- Fee drag on gross: **4.0%**

**Trade 1 (winning, maker, identical fill price):** same trade but as resting limit
- Entry fee: ceil(1.75 * 10 * 0.55 * 0.45) cents = ceil(4.33) = **$0.05**
- Net P&L: $4.45. Fee drag: **1.1%**

**Trade 2 (losing, taker):** Buy 10 contracts at $0.55, market resolves NO, position settles to $0.
- Entry fee: **$0.18**
- Settlement loss: $5.50
- Total loss: $5.50 + $0.18 = **$5.68**
- Fee drag on the $5.50 nominal loss: **3.3%**

Implication: on a binary 50/50 with mid-price ~0.50 and taker-only execution, the breakeven edge needed just to cover fees is `2 * 0.0175 / 0.50` ~ **7% mispricing** for a round-turn (entry taker fee + opposite-side fee if you exit before settlement). If you hold to settlement, only the entry fee applies: ~3.5% edge needed at mid-price.

## 5. Settlement

- Binary outcome: YES contract pays $1.00 if event resolves YES, $0.00 if NO. Vice versa for NO contracts.
- Process: market closes -> Kalshi enters "determination" phase -> markets team verifies against the source named in the market's rule text -> settlement posts ~3 hours after determination (sometimes longer). Sources report typical end-to-end as a few hours.
- Manual vs automatic: **manual review** by Kalshi's markets team is the norm. Members can submit a "Request to Settle" via the UI. Kalshi can also exercise discretion or extend resolution to a later date defined in the market rules.
- Void / no-result: markets have a "latest possible determination date" specified in their rules; if the source is unresolvable, Kalshi may declare the market void and refund positions (returns positions to entry cost). Specific void mechanics are case-by-case and only loosely documented in public help center articles; mass-void edge cases (e.g., source ambiguity) are at Kalshi's discretion.
- Losing positions: settle to $0.00. No fees deducted on settlement.

## 6. Order types, minimums, tick size

- **Only `limit` is accepted via the API as of Sep 25, 2025.** The legacy `market` order type was deprecated and removed. To simulate a market order you submit a limit at $0.99 (buy) or $0.01 (sell) with IOC time-in-force.
- Time-in-force options on limit orders: **IOC** (immediate-or-cancel), **EOD** (end-of-day, default for GTC-like behavior), and custom expiration timestamp. **FOK** is referenced indirectly via error codes (`FOK_INSUFFICIENT_VOLUME`) and `POST_ONLY_CROSS`, so post-only and FOK appear supported but documentation is thin.
- **Stop orders: not natively supported** in the public REST API. Client-side stops only.
- Tick size: **$0.01** standard. Some markets support sub-penny ticks down to $0.001 ("price_level_structure" field replaced the legacy `tick_size` field as of May 2026). Price field type migrated from integer cents to fixed-point dollar strings ("0.5500") in March 2026.
- Minimum order size: no general minimum (1 contract is acceptable). Special exception: **Congressional Control** contracts require multiples of 5,000 contracts. No notional minimum on standard markets.

## 7. Position limits

- Default retail: documented as **$25,000 per market** for typical traders historically.
- November 2024: rulebook moved from hard "position limits" to **"position accountability levels"**, giving Kalshi discretion to monitor concentrated risk rather than auto-block.
- Per-account category caps cited in CFTC filings: **$7M per strike per member** for individuals/entities, **$100M per strike per member** for Eligible Contract Participants.
- These are exchange-level caps. Most retail bots will never touch them. No documented API tier limits affect position size.

## 8. WebSocket vs REST coverage

Production WS endpoint: `wss://external-api-ws.kalshi.com/trade-api/ws/v2`. Auth via API key headers in the handshake.

Channels (11 total):
- **Public**: `orderbook_delta`, `ticker`, `trade`, `market_lifecycle_v2`, `multivariate_market_lifecycle`, `multivariate`
- **Authenticated/private**: `fill`, `market_positions`, `communications`, `order_group_updates`, `user_orders`

Coverage notes:
- `orderbook_delta` starts with a full `orderbook_snapshot` then ships incremental updates with sequence numbers. Clients must maintain a local book and handle gap recovery via REST snapshot.
- Real-time fills via `fill` channel. Order acks via `user_orders`.
- Latency expectations not published. Community reports order-of-100ms for WS deltas under normal load. No SLA.
- REST is the only canonical source for historical and account-state queries; WS is for live deltas and notifications.

Subscription cap and per-connection message rate limits: **not numerically published.**

## 9. Client libraries

### Official

- **`kalshi-python` on PyPI**: version **2.1.4**, last release **2025-09-06**. Maintainers listed as `hsousak` and `Kalshi`. **License: proprietary (`LicenseRef-Proprietary`)**. Requires Python 3.9+. This appears to be the auto-generated SDK from Kalshi's OpenAPI spec. The proprietary license is a real consideration; review terms before distribution.
- **`Kalshi/kalshi-starter-code-python`** on GitHub: this is the **official starter code**, not an SDK. 94 stars, 16 commits, 6 open issues, license not in summary. Use as a reference implementation for the RSA-PSS auth flow; do not depend on it as a library.

### Third-party

- `lowgrind/kalshi-python`: claims to be "official" but is a community Swagger-generated wrapper. 3 stars, 3 commits, supports Python 2.7+/3.4+ (stale). Apache-2.0. **Skip.**
- `humz2k/kalshi-python-unofficial`: lightweight wrapper, small community project, low activity.
- `the-odds-company/aiokalshi`: asyncio-native Kalshi client. Worth evaluating for async-heavy bots.
- `sswadkar/kalshi-interface`: FastAPI dashboard plus REST wrapper, includes RSA-PSS signing.
- `AndrewNolte/KalshiPythonClient`: minimal Python client.
- TypeScript SDK exists per docs (`docs.kalshi.com/typescript-sdk/api/MarketsApi`).

### Recommendation

**Use `kalshi-python` 2.1.4 from PyPI** as the primary client because (a) it is the official package, (b) it tracks the OpenAPI spec and was rebuilt 8 months ago covering the April 2025 rate-limit changes and historical-data endpoints, and (c) any community wrapper will lag the changelog (e.g., the Sep 2025 `market` order removal, the March 2026 string-price migration). **Caveat**: the proprietary license may restrict redistribution; read the terms. If license is a blocker, fall back to writing a thin RSA-PSS-signed `httpx` client using `Kalshi/kalshi-starter-code-python` as the reference. For async-first design, evaluate `aiokalshi` as a secondary.

## 10. Historical market data (CRITICAL FOR BACKTESTING)

- Kalshi provides **historical endpoints** as of Feb 2025: `GET /historical/cutoff`, `/historical/markets`, `/historical/fills`, `/historical/orders`, `/historical/trades`, plus candlesticks (including a batch candlesticks endpoint added Nov 2025).
- Live data window: ~3 months. Older data moves to `/historical/*`.
- **Granularity**: tick-level trades are available via `/historical/trades`. Candlesticks available at varying intervals. **Orderbook snapshots and L2 depth history are NOT directly downloadable**; you must reconstruct from `orderbook_delta` WS captures going forward, or use a third party.
- **Pagination**: 100 rows max per page. Reconstructing a full history requires thousands of requests against the rate limit. Practical for retail-scale strategies but tedious.
- **Pricing**: historical endpoints are part of the same API and use the same token-bucket budget. **No separate paywall** mentioned in docs.
- **FLAG**: there is no documented bulk dump or archive download from Kalshi. If you need years of tick history, you are looking at days of paginated pulls or a third party.

### Third-party historical providers

- **Lychee** (`lycheedata.com`) markets a **36 GB dataset** of all Kalshi trades/markets/resolutions since 2021 launch, with CSV/JSON/XLSX export. Pricing **not public**; "contact sales" model. Likely the most complete commercial archive but cost unverified.
- Apify scrapers exist (`apify.com/mild_costume/kalshi-scraper`) but quality is unknown.
- No prominent free Kaggle/GitHub dataset covering Kalshi at tick depth as of May 2026.

### Implication for the project

- **Backtesting on tick-level orderbook depth is hard.** Kalshi exposes historical trades but not historical L2 depth. You either (a) start capturing WS `orderbook_delta` to your own storage now and accept zero pre-launch backtest depth, (b) limit backtests to trade-prints and candlestick reconstructions, or (c) pay an undisclosed amount to Lychee for the existing archive.
- For a $50 to $100 budget project this is a **moderate constraint**. Trade-print and candlestick backtests are achievable; full L2 replay is not free.

## 11. Demo / sandbox environment

- **Exists as of May 2026.** REST: `https://external-api.demo.kalshi.co/trade-api/v2`. WS: `wss://external-api-ws.demo.kalshi.co/trade-api/ws/v2`.
- Credentials: separate signup flow at demo dashboard; you generate distinct API keys. Demo keys do not authenticate against production and vice versa.
- Mock funds, real(ish) market data mirroring. Documented behavior: orderbook and market data "mirror" production conditions per Kalshi docs and community write-ups (e.g., amiable.dev Jan 2026 post).
- **Gotchas / divergences**:
  - Demo has **no real counterparty liquidity for fills**. Reports indicate fills happen against a simulated book; you cannot trust execution quality measurements from demo as predictive of production slippage.
  - Special-fee event markets in production may have different fee schedules than the demo standard.
  - Demo lifecycle events (settlement, market close timing) may not exactly mirror production for live events.
  - Aug 2025 changelog: `BatchCreateOrders` and `BatchCancelOrders` became available to Basic tier in demo, useful for testing high-throughput logic.
  - Account tier in demo is fixed; you cannot test Prime-tier rate limits without production qualification.

## Sources

- https://docs.kalshi.com/welcome
- https://docs.kalshi.com/getting_started/api_environments
- https://docs.kalshi.com/getting_started/api_keys
- https://docs.kalshi.com/getting_started/demo_env
- https://docs.kalshi.com/getting_started/fee_rounding
- https://docs.kalshi.com/getting_started/rate_limits
- https://docs.kalshi.com/getting_started/historical_data
- https://docs.kalshi.com/websockets/websocket-connection
- https://docs.kalshi.com/api-reference/account/get-account-api-limits
- https://docs.kalshi.com/changelog
- https://help.kalshi.com/trading/fees
- https://help.kalshi.com/trading/order-types/limit-orders
- https://help.kalshi.com/markets/markets-101/request-to-settle-market
- https://news.kalshi.com/p/order-types
- https://kalshi.com/fee-schedule
- https://kalshi.com/docs/kalshi-fee-schedule.pdf (returned 429 on direct fetch; numbers confirmed via pm.wiki, marketmath.io, and Kalshi help center)
- https://pm.wiki/learn/kalshi-fees-explained
- https://marketmath.io/blog/kalshi-fees-guide-2026
- https://www.alphascope.app/blog/kalshi-fees
- https://amiable.dev/blog/arbiter-bot/2026-01-22-kalshi-demo-environment/
- https://agentbets.ai/guides/kalshi-api-guide/
- https://near.blog/kalshi-cftc-market-limits/
- https://www.cftc.gov/filings/orgrules/rules1114248723.pdf (CFTC position accountability filing)
- https://github.com/Kalshi/kalshi-starter-code-python
- https://github.com/lowgrind/kalshi-python
- https://pypi.org/project/kalshi-python/
- https://lycheedata.com/guides/kalshi-historical-data
- https://defirate.com/prediction-markets/how-contracts-settle/
- https://www.tradetheoutcome.com/how-long-does-kalshi-take-to-pay-out/

## Unknowns / blockers

1. **Direct Kalshi fee schedule PDF (kalshi.com/docs/kalshi-fee-schedule.pdf) returned HTTP 429 on every fetch attempt.** Trading-fee formula constants (0.07 taker, 0.0175 maker) are confirmed from multiple secondary sources (pm.wiki, marketmath.io) but I could not verify the official PDF directly today. Operator should download the PDF manually before going live.
2. **Special-event market fees** can deviate from the standard formula. Per-market schedules are not aggregated anywhere I could find. Need to inspect each target market's rule text.
3. **WebSocket rate limits** (max subscriptions per connection, message rate, reconnection backoff) are not publicly documented with numbers. Must be measured empirically against the demo environment.
4. **Demo environment fill realism**: docs claim "mirrored" market data but multiple secondary sources note simulated fills. Execution quality on demo is not predictive of production. Must be empirically tested.
5. **Key rotation procedure**: not formally documented as an SOP. Generation/revoke flow is inferable from the dashboard but the official cookbook is missing.
6. **`kalshi-python` PyPI license**: tagged `LicenseRef-Proprietary`. I did not pull the full license text; this could restrict redistribution of any derivative code. Read the terms before depending on it in any deployed bot.
7. **Lychee dataset pricing**: not public. Could be $50/month or $5,000/month. Budget-relevant unknown if L2 history is required.
8. **Historical L2 orderbook depth is not API-accessible.** Confirmed unknown: whether any tier of paid Kalshi access unlocks this. As of public docs, no.
9. **Stop orders / OCO / advanced order types**: not in public REST API. FIX gateway documentation referenced (`docs.kalshi.com/fix/order-entry`) may expose more order types; FIX access likely gated behind volume tier.
10. **Sub-penny tick markets**: the schedule for which markets support $0.001 tick is not enumerated; must read per-market `price_level_structure` field at runtime.
