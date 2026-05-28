# v10 Data Scout: US-Accessible Free / Near-Free Sources

**Date:** 2026-05-26
**Author:** Agent v10-S2 (Data + Literature Scout)
**Prior baseline:** `research/v7/01-data-sources-scoping.md` (2026-05-25) plus
`research/v9/01-data-universe.md` (2026-05-26)
**Budget constraint:** $30-60 external data, ~$0-cost incremental preferred.
**Method:** WebSearch / WebFetch probes; no live curl from this session (those
were done in v7/v9 sessions; findings cited from those docs).

---

## Executive Summary

The v7 and v9 data-source inventories are largely still valid. The main new
findings in this scout:

1. **Multi-LLM free/cheap roster is now clearly definable.** Google Gemini
   2.5 Flash (1,500 req/day free), DeepSeek V4 Flash ($0.14/M input with
   5M free signup tokens), and Groq hosted Llama (1,000 req/day free) form a
   credible three-vendor ensemble at under $0.003 per forecast call.
   Collectively they provide a multi-LLM architecture at effectively $0
   for the first ~300-500 forecasts.

2. **FRED + EIA + BLS APIs are all free with a simple key registration.**
   The biggest new signal: FRED covers Kalshi macro market underlying data
   directly (FEDFUNDS, CPI, UNRATE, NFP series). The Diercks/Katz/Wright
   2026 paper (lit #6) already confirmed macro markets are efficiently priced
   by institutions, so FRED's value is as a feature, not an edge, on these
   markets.

3. **Polymarket CLOB historical data degraded significantly in Feb 2026.**
   The `/orderbook-history` endpoint stopped producing new snapshots after
   Feb 20, 2026. The `/prices-history` endpoint only returns data at 12+ hour
   granularity for resolved markets. Cross-venue Polymarket features are
   substantially weaker than v7 hoped.

4. **TabPFN-3 (May 2026) supersedes TabPFN v2** with 1M-row support and
   time-series specialist checkpoint (TabPFN-TS-3). Breaks the prior
   10k-row ceiling. However, GPU (H100) required at 1M rows; consumer CPU
   feasibility for < 10k rows is not documented as changed from v2.

5. **Brave Search API free tier was eliminated in early 2026** (now metered,
   credit card required). Tavily free tier (1,000 req/month, no card) is the
   live LLM-friendly search API at zero cost.

6. **SEC EDGAR full-text search API is free and requires no key** (10 req/sec,
   filings from 2001-present). Useful for macro/financial event research.

7. **Kraken Futures funding rate history is publicly documented** as free with
   no key for historical rates. Direct US-accessible alternative to Deribit.

---

## Section 1: Multi-LLM Free Tiers for Ensemble

### 1.1 Context

The AIA Forecaster (arXiv 2511.07678) and AMA (arXiv 2510.11695) both showed
that framework matters more than model choice. v9 was killed partly on design
grounds (wrong regime). For any future LLM ensemble angle, a roster of 3-5
cheap-but-functional models matters for diversification and redundancy. This
section identifies the accessible no-cost / near-zero-cost LLM endpoints as of
May 2026 from a CA IP.

### 1.2 Google Gemini (AI Studio free tier)

- **Free tier (May 2026):** Gemini 2.5 Flash: 1,500 req/day, 15 RPM, 1M TPM.
  Gemini 2.5 Flash-Lite: same limits. Gemini 2.5 Pro: 50 req/day only.
- **Status change:** December 2025 Google cut free-tier limits by 50-80% citing
  abuse. Gemini 2.0 Flash deprecated March 2026. Current stable free model is
  Gemini 2.5 Flash (March 2026 generation).
- **No credit card required** for the free tier. Key via Google AI Studio
  (aistudio.google.com), instantaneous.
- **Geo accessibility:** No documented US geo-block. Standard Google service.
- **Calibration note:** Gemini 2.5 Flash is mid-frontier; no published
  ForecastBench Brier. PolyBench (arXiv 2604.14199) documents Gemini-3-Flash
  as one of only 2 of 7 models that was CWR-positive (+6.2%) in Feb 2026.
  The PolyBench finding is a positive signal for Gemini in prediction markets.
- **Integration cost:** python-genai SDK, identical structure to Anthropic SDK.
  Platt-scaling post-processing needed (AIA recipe).
- **PRIORITY: HIGH.** Gemini 2.5 Flash is free at 1,500 req/day, Brier not
  benchmarked at tier-1 level but PolyBench Gemini-3-Flash positive. Easiest
  non-Anthropic vendor to add.
- **v7 note:** v7 scoping only listed Hugging Face Inference as a free option;
  did not probe Gemini free tier. This is NEW.

### 1.3 DeepSeek V4 Flash

- **Free tier:** 5M tokens free at signup (30-day expiry), no credit card.
  After expiry: $0.14/M input, $0.28/M output (V4 Flash). No documented
  hard rate limit; best-effort with 429/503 at peak.
- **Geo accessibility:** No documented US geo-block as of May 2026. DeepSeek
  API (api.deepseek.com) is a commercial service; China-origin but API is
  globally accessible. No 451 documented.
- **Calibration note:** DeepSeek v3 Brier 0.1798 (Janna Lu 2025); R1 variant
  comparable. In PolyBench Feb 2026, DeepSeek was NOT one of the 2 CWR-positive
  models (5 of 7 lost money). Treat as a useful diversifier, not the best
  single model.
- **Integration cost:** OpenAI-compatible API endpoint. Minimal porting from
  openai-python.
- **PRIORITY: MEDIUM.** 5M free tokens cover ~2,500 long forecasting prompts.
  $0.14/M thereafter is cheapest commercial-grade LLM. Good for budget
  redundancy. Weaker PolyBench signal than Gemini.
- **v7 note:** v7 scoping mentioned DeepSeek in passing. This entry adds
  current pricing and geo verification.

### 1.4 Groq (hosted Llama 3 / Mixtral)

- **Free tier:** No credit card. 1,000 req/day on most models. 30 RPM / 6,000
  TPM / 1,000 RPD on the standard rate-limited tier. Llama-3.1-70B and Mixtral
  8x7B available on free tier.
- **Geo accessibility:** US-headquartered. No geo-block.
- **Calibration note:** Llama 3.1 70B is an open-source model. No dedicated
  ForecastBench Brier for Groq-hosted inference. Llama 3 70B is roughly
  GPT-4o-class from a forecasting calibration standpoint: expected Brier ~0.19
  (unmeasured, extrapolated from Janna Lu 2025 tiers).
- **Speed:** 315 TPS is the headline. For a forecasting use case, speed matters
  less than calibration.
- **Integration cost:** OpenAI-compatible. One line change from OpenAI SDK.
- **PRIORITY: MEDIUM.** Free is free; 1,000 req/day is ample for v10's 87-
  market pilot. Weakest calibration of the three but zero marginal cost.
- **v7 note:** v7 scoping listed Groq in the "Together AI / Replicate / Groq"
  bucket. This entry specifies the free-tier limits (1,000 RPD confirmed from
  tokenmix.ai 2026 documentation).

### 1.5 OpenAI gpt-4o-mini / o4-mini

- **Pricing:** $0.15/M input, $0.60/M output (gpt-4o-mini). o4-mini is more
  expensive (~$1-3/M) but has documented Brier 0.1589 (Janna Lu 2025) placing
  it above most free-tier alternatives.
- **Free tier:** None (credit card required, $5 prepay). Lowest practical
  spend is $5.
- **Calibration note:** gpt-4o-mini Brier is UNMEASURED in any published
  benchmark (documented gap in lit #14). o4-mini at 0.1589 Brier is behind
  o3 (0.1352) but ahead of GPT-4o (0.1883).
- **PRIORITY: MEDIUM** (o4-mini, if budget allows). **SKIP** (gpt-4o-mini as
  primary, calibration unknown). Cost is not the barrier but calibration
  uncertainty is.

### 1.6 Mistral (Le Chat API)

- **Pricing:** Ministral 3B at $0.04/M. Mistral Large 2 at $2/$6/M.
- **Free tier:** Le Chat consumer interface free; API (api.mistral.ai) requires
  paid plan. No documented free API tier comparable to Groq.
- **PRIORITY: LOW.** No free API tier for programmatic use; paid but cheap
  at Ministral tier. Skip unless Groq / Gemini / DeepSeek prove insufficient.

### 1.7 Hugging Face Inference API

- **Free tier:** Inference API for small open-source models (< 10B params)
  is free but heavily rate-limited. The Serverless Inference API allows
  ~100-300 req/hour on popular models. Larger models (> 10B) require PRO tier
  ($9/mo) or dedicated endpoints.
- **Calibration note:** Any model small enough to run free is unlikely to
  be competitive on forecasting calibration vs Gemini 2.5 Flash or DeepSeek
  V4 Flash.
- **PRIORITY: LOW.** Use for Chronos-2 or TabPFN local weights, not for
  LLM forecasting.

### 1.8 Cohere

- **Free tier:** "Trial" key with 1,000 req/month and 1,000 tokens/min.
  Very limited vs Gemini free tier.
- **PRIORITY: LOW.** No documented prediction-market Brier; smaller free
  quota than Gemini. Skip.

### 1.9 Multi-LLM ensemble roster recommendation

For a multi-model ensemble at < $5 per 100 forecasts:

| Vendor | Model | Cost / 100 forecasts (1k tok prompt + 200 tok output) | Free budget |
|--------|-------|------------------------------------------------------|-------------|
| Google AI Studio | Gemini 2.5 Flash | $0.00 (free tier 1,500/day) | 1,500 req/day |
| DeepSeek | V4 Flash | ~$0.017 (after 5M free tokens) | 5M tokens signup |
| Groq | Llama-3.1-70B | $0.00 (free tier 1,000/day) | 1,000 req/day |
| Anthropic | Haiku 4.5 | ~$0.05 (cheap tier) | none |

Three-vendor free pilot: Gemini 2.5 Flash + DeepSeek V4 Flash (use signup
credits) + Groq Llama-3.1-70B. For 87 prospective markets: total cost $0
within free-tier envelope. After free tiers exhaust: < $0.03 per forecast.
**This is under the $5 / 100 forecast target.**

---

## Section 2: Economic / Macro Data (Free)

### 2.1 FRED (Federal Reserve Economic Data)

- **Access:** Free API key, no cost. Registration at
  fredaccount.stlouisfed.org/apikeys. FRED API v2 launched November 2025
  and now requires a key for programmatic access (previously open).
- **US accessibility:** Yes. St. Louis Fed is US-hosted.
- **Rate limits:** Not publicly documented hard cap; "liberal" per community.
- **Historical depth:** 816,000+ time series. Key Kalshi macro market
  underlying data:
  - `FEDFUNDS` (effective federal funds rate, daily / monthly)
  - `CPIAUCSL` (CPI all urban, monthly)
  - `PAYEMS` (nonfarm payroll employment, monthly)
  - `UNRATE` (unemployment rate, monthly)
  - `DGS10` (10-year Treasury, daily)
  - `GDP` (quarterly)
  - `VIXCLS` (CBOE VIX, daily, sourced from FRED)
- **Kalshi market fit:** KXFEDFUNDS, KXCPI, KXNFP, KXUNRATE markets are
  directly related to FRED series. Diercks/Katz/Wright 2026 (lit #6)
  confirmed these markets are efficient (institutions make them); FRED is not
  an edge but IS a legitimate feature for calibrating LLM macro forecasts
  (provide current FRED value to LLM as context, observe whether LLM output
  correlates with or diverges from market price).
- **Integration:** `fredapi` Python package (pip install fredapi). Well-
  maintained.
- **PRIORITY: HIGH** for macro market context features in any LLM forecasting
  angle. $0 cost. New finding: FRED now requires a key (v7 scoping did not
  note this change, which occurred November 2025).

### 2.2 BLS API (Bureau of Labor Statistics)

- **Access:** Free with key (data.bls.gov/registrationEngine/). Key is
  instantaneous via email.
- **Rate limits:** With key: 50 series per query, up to 20 years history.
  Without key: 25 series per query, 10 years history.
- **Coverage:** CPI-U, CPI-W, PPI, employment situation (NFP, UNRATE),
  JOLTS, employment cost index.
- **Overlap with FRED:** FRED ingests most BLS series. BLS direct API is
  faster for same-day releases (FRED has ~1 day lag for some series).
- **Kalshi market fit:** Same as FRED for KXCPI / KXNFP / KXUNRATE markets.
  BLS direct gives same-day release data which is valuable if building a
  prediction window around release day.
- **PRIORITY: MEDIUM.** Use FRED as primary (covers BLS data plus much more).
  BLS direct only needed for same-day release timing where FRED lag matters.

### 2.3 BEA API (Bureau of Economic Analysis)

- **Access:** Free with key (apps.bea.gov/api/signup/).
- **Coverage:** GDP (quarterly), personal income, personal consumption
  expenditures (PCE), trade balance.
- **Kalshi market fit:** KXGDP markets if they exist. Lower coverage than
  FRED.
- **PRIORITY: LOW.** FRED already ingests most BEA series. Direct BEA API
  only needed if FRED coverage has gaps.

### 2.4 Census API

- **Access:** Free with key (api.census.gov/data/key_signup.html).
- **Coverage:** Demographics, population estimates, American Community Survey,
  housing starts.
- **Kalshi market fit:** Low direct relevance. Housing starts could be a
  feature for any KXHOUSING market.
- **PRIORITY: LOW.** Skip unless a specific housing or demographic Kalshi
  market becomes the v10 angle.

### 2.5 World Bank API / OECD API

- **Access:** Both free, no key.
- **Coverage:** Global economic indicators; less granular than FRED for US data.
- **Kalshi market fit:** Very low for a US-focused Kalshi portfolio.
- **PRIORITY: SKIP.** No identifiable Kalshi market the operator currently
  trades that requires non-US data.

---

## Section 3: Politics / Polling (Free)

### 3.1 Assessment for v10 context

The operator's universe is currently sports + crypto via v1. Political markets
are not in v1's current active set. This section is catalogued for future
reference but none of these sources are HIGH priority for v10.

### 3.2 FiveThirtyEight / ABC News archive

- **Status:** 538 political model archive is publicly accessible
  (projects.fivethirtyeight.com/polls/). Historical polling averages and
  model outputs through the 2024 election cycle are available as CSV downloads.
  Post-2024 polling and model data is more limited (ABC News merger dynamics).
- **Kalshi fit:** KXPRES (presidential), KXSEN (senate), KXHSE markets.
- **PRIORITY: LOW** for current v10 scope (sports / crypto primary). File for
  future political angle.

### 3.3 Polymarket as cross-venue politics feature

- **Status:** Polymarket.com US geoblocked but API accessible (confirmed in
  v7 scoping). The Polymarket API is documented as no longer geoblocked as of
  a 2026 update per one source (quantvps.com/blog). However, the Becker
  dataset (lit #2) and prior v3 work showed Kalshi volumes dwarf Polymarket
  on US sports. For politics, Polymarket is the larger venue.
- **Caveat (NEW 2026):** The `/orderbook-history` endpoint stopped new
  snapshots after Feb 20, 2026. Historical politics data from 2024 election
  is accessible but current-market cross-venue signaling is weakened.
- **PRIORITY: LOW** for v10 current scope. File for any future politics angle.

---

## Section 4: Sports Analytics (Free, Beyond ESPN site.api)

### 4.1 ESPN site.api (confirmed from v9/v7)

- **Status:** HTTP 200 from CA IP confirmed v7 and v9 probes. All 6 sport
  endpoints return live data. Historical via `?dates=YYYYMMDD` parameter.
- **PRIORITY: HIGH** (unchanged from v7/v9). The primary free sports news
  and stats source.

### 4.2 FiveThirtyEight sports archives

- **Status:** NFL Elo ratings, NBA RAPTOR, MLB, soccer SPI are historical
  archives. Some are available as CSV on GitHub or the 538 data page
  (data.fivethirtyeight.com). Updated models post-2024 are uncertain given
  ABC News integration.
- **Kalshi fit:** For any KXNFLGAME, KXNBAWINS, KXMLBWINS angle: pregame
  Elo spread is a free public feature.
- **PRIORITY: MEDIUM** for any future sports ML angle. Note v5-B (Statcast
  at n=146k) and v3 (sports ML) were CONFIRMED NULL; 538 features are one
  more public feature that is unlikely to clear the orthogonality threshold
  alone. Marginal value as an additional feature in a multi-feature pipeline.

### 4.3 SportsReference / Baseball-Reference (scraping)

- **ToS check (current):** Sports-Reference's Terms of Service prohibit
  automated scraping without a license. Their API tier starts at ~$10/mo.
  Scraping risk: Cloudflare + ToS violation potential.
- **PRIORITY: SKIP.** ToS forbid it; API is paid.

### 4.4 Sportradar

- **PRIORITY: SKIP.** Enterprise pricing, confirmed out of budget in all
  prior rounds.

---

## Section 5: News / Sentiment (Free)

### 5.1 GDELT 2.0

- **Status update from v9:** v9 probe (2026-05-26) got HTTP 429 ("Please limit
  requests to one every 5 seconds"). This CONFIRMS GDELT is reachable from the
  CA host (v7 got timeout = transient). 429 is recoverable with 5s delays.
- **Bulk download (no rate limit):** http://data.gdeltproject.org/gdeltv2/ --
  15-minute event files going back to 2015, no key, no rate limit. The bulk
  download path is the recommended integration: download GKG files offline
  for keywords relevant to the market in question, compute sentiment tone
  feature.
- **PRIORITY: MEDIUM.** Confirmed accessible (429 not 451). Bulk download
  path is more reliable than the doc API. Engineering cost is higher than
  ESPN. Valuable for non-sports markets (geopolitical, international soccer
  KXWCGAME context). For v1's primary sports universe, ESPN is simpler.

### 5.2 Tavily Search API

- **Free tier (confirmed 2026):** 1,000 API credits/month. No credit card.
  Free plan includes Search + Extract endpoints.
- **Rate limits:** Not published explicitly; standard web search query limits.
- **What it provides:** LLM-optimized search results for any query; returns
  structured JSON with relevant snippets. Ideal as the retrieval tool in an
  AIA-style agentic forecasting pipeline (provides real-time news context to
  the LLM forecaster).
- **US accessibility:** US-headquartered service. No geo-block.
- **PRIORITY: HIGH.** This is a direct free-tier replacement for the web-search
  tool that AIA Forecaster used. At 1,000 queries/month, it covers ~87 markets
  times 10 queries per market (current events, injury, form) = 870 queries,
  within the free budget. No credit card required. **This is NEW vs v7 scoping
  which only listed news APIs like NewsAPI (dev-only) and Alpha Vantage (25/day
  slim).**

### 5.3 Brave Search API

- **Status change (NEW):** Brave eliminated the free tier for new users in
  early 2026. Previously offered 5,000 free queries/month; now metered billing
  with credit card required (approximately $0.003-0.005 per query).
- **v7 discrepancy:** v7 scoping did not test Brave; this confirms it is now
  NOT free for new users.
- **PRIORITY: SKIP** (use Tavily instead, which is free with no card).

### 5.4 Reddit / Pushshift

- **Status (2026):** Reddit's Pushshift partnership ended in 2023. Third-party
  Pushshift access requires API keys no longer distributed. Direct Reddit API
  requires app registration and has rate limits; historical data beyond 1,000
  posts requires paid data products.
- **PRIORITY: SKIP.** Historical depth unavailable at no cost.

### 5.5 HackerNews API

- **Status:** Free, no key, open (hn.algolia.com API). Search by keyword,
  date range, points. Historical back to 2006.
- **Kalshi fit:** Marginal. HN covers tech/startup topics that rarely
  overlap with Kalshi sports or even macro markets. Possible for any KXTECH
  or KXAI market if such a category exists.
- **PRIORITY: LOW.** Irrelevant for v1's current sports-heavy universe.

### 5.6 Bluesky Jetstream Firehose

- **Status:** Jetstream WebSocket (jetstream2.us-east.bsky.network) is free
  and open without auth. Real-time post stream.
- **Historical access (NEW 2026):** Bluesky launched "Tap" for repo
  synchronization. Tap backfills a specific account's history but does NOT
  provide full network historical search by keyword. Network-level
  historical search is not freely available.
- **PRIORITY: LOW.** Forward-record only. Thin signal for sports prediction
  markets vs ESPN. Skip for v10.

---

## Section 6: Crypto Cross-Venue (Beyond Hyperliquid + dYdX)

### 6.1 Binance.US

- **Status:** US-accessible (separate platform from Binance.com which returned
  451 in v6). Historical spot data available since 2019-09-25. Futures data
  available since 2021-04-12.
- **API access:** Free, REST API at api.binance.us. Spot candles, trades,
  and order book depth are documented. Funding rate history for futures
  contracts is available.
- **Relevance:** For v6/v7 crypto angle: Binance.US perpetuals have lower
  volume than Hyperliquid ($1B+) but higher volume than dYdX. Could be a
  third cross-venue comparison point.
- **New vs v7:** v7 scoping explicitly said "Binance.com 451" but did NOT
  probe Binance.US separately. Binance.US is a distinct entity (BAM Trading
  Services) and is US-licensed. **This is NEW** in the data inventory.
- **PRIORITY: MEDIUM.** Adds a third US-accessible perp venue for any future
  crypto microstructure angle. Free. Given v6 and v5-C NULLs on crypto
  microstructure, only relevant if a genuinely new crypto angle appears.

### 6.2 Kraken Futures

- **Status:** Free API documented at docs.kraken.com/api/docs/futures-api.
  Historical funding rates endpoint: GET /api/v3/historicalfundingrates.
  No key required for public market data.
- **US accessibility:** Kraken is US-licensed and US-accessible from CA.
  This is a direct free alternative to Deribit (which v7 scoping noted is
  accessible but UK-based).
- **Historical depth:** Not explicitly documented but funding rate history
  appears to go back to futures launch.
- **PRIORITY: MEDIUM.** Free Kraken Futures funding rate history was NOT in
  v7 scoping (which only mentioned "Kraken /0/public/Trades" for spot, not
  futures). **This is NEW.**

### 6.3 Bybit US

- **Status (2026):** Bybit US is not clearly a distinct entity from the main
  Bybit platform. Bybit has faced US regulatory scrutiny; as of May 2026
  accessibility from CA is UNCERTAIN without a live probe. Do not rely on.
- **PRIORITY: SKIP** until a probe confirms US accessibility.

### 6.4 GMX (on-chain perps)

- **Status:** GMX is a decentralized protocol on Arbitrum. Data is publicly
  available via the GMX subgraph (The Graph) and on-chain. No IP geo-block.
- **Volume:** GMX is smaller than Hyperliquid ($100-200M daily volume vs $1B+).
- **Relevance:** For a cross-venue funding rate comparison: GMX funding
  (borrowing fee) mechanism is different from linear funding on Hyperliquid/
  dYdX. The signal profile is different.
- **PRIORITY: LOW.** Lower volume than Hyperliquid; different mechanism; v6
  already killed the funding rate angle.

---

## Section 7: Stock / Business Event Data

### 7.1 Polygon.io (free tier)

- **Free tier (2026):** 5 API calls/minute, up to 2 years of daily historical
  data (delayed; not real-time). Free plan is end-of-day data only.
- **News:** Polygon does provide news but is inferior to dedicated news APIs
  for depth.
- **Kalshi fit:** Potentially relevant for any KXSPX (S&P 500 level) or stock-
  specific Kalshi markets. Not in v1's current universe.
- **PRIORITY: LOW.** Current v1 universe is sports + crypto. Polygon is
  relevant only if v10 targets equity-linked Kalshi markets.

### 7.2 Alpha Vantage

- **Free tier (confirmed in v7/v9):** 25 calls/day demo; full free API with
  signup: 500 calls/day (reduced from 500 to 25 for unregistered). Historical
  data back ~2 years.
- **PRIORITY: LOW.** Very thin daily limit. Use only as a spot check, not as
  a primary data feed. v7 confirmed this.

### 7.3 SEC EDGAR Full-Text Search

- **Access (NEW):** Free, no key required. 10 req/sec. Full-text search of
  all EDGAR filings since 2001. Available at efts.sec.gov/LATEST/search-index?
  and sec.gov/cgi-bin/browse-edgar.
- **Rate limits:** 10 req/sec; fairly liberal for research purposes.
- **Kalshi fit:** Potential feature for any Kalshi market related to corporate
  earnings, executive departures, regulatory decisions, or financial event
  markets. Current v1 universe does not target these.
- **PRIORITY: LOW** for current v1 universe. **MEDIUM** if v10 explores
  financial event markets (KXEARNINGS-style or regulatory).

---

## Section 8: Weather Data (NOAA)

### 8.1 NOAA CDO API

- **Access:** Free with key (ncdc.noaa.gov/cdo-web/webservices/v2). Key
  instantaneous via token request page. Rate: 5 req/sec, 10,000 req/day.
- **Also available (no key):** NCEI Access Data Service at
  www.ncei.noaa.gov/access/services/data/v1 (no key needed for this endpoint).
  National Weather Service API (api.weather.gov) is also free without key for
  current/forecast data.
- **Historical depth:** Global historical weather since 1800s. GHCN daily
  summaries, hourly ASOS data at US stations.
- **Kalshi fit:** Weather was tested in EC-1 (Round 1, KXHIGH KILLED). The
  Burgi finding (lit #1) shows weather has smaller bias than cross-category
  average (ψ = 0.031). NOAA is the data source IF a weather angle is revisited.
  For v10, weather is NOT a priority angle given EC-1's kill.
- **PRIORITY: MEDIUM** (data is there and free; just not a priority for v10's
  specific scope).

---

## Section 9: Other Novel Sources

### 9.1 EIA Energy API

- **Access:** Free with key (eia.gov/opendata). Key via email, instantaneous.
- **Coverage:** Natural gas prices, oil (WTI), electricity prices, crude oil
  inventories (weekly), refinery utilization.
- **Kalshi fit:** KXWTI (WTI crude), KXNATGAS markets if they exist in v10's
  scope. v9 scoping found KXWTIW (oil) with ~450 closed markets in OOS but
  0 v1-eligible. Mid-band coverage is the key question.
- **PRIORITY: MEDIUM** if WTI or natural gas markets are identified with
  predictable mid-band pricing. EIA is the canonical free US energy data
  source.

### 9.2 USDA NASS / ERS APIs

- **Access:** Free with registration. NASS (National Agricultural Statistics
  Service) provides crop reports, planting/harvest progress, commodity prices.
  ERS (Economic Research Service) provides processed agricultural statistics.
- **Kalshi fit:** Any KXCORN / KXSOYBEANS agricultural futures Kalshi markets.
  Not in v1's universe.
- **PRIORITY: LOW** for current scope.

### 9.3 Tavily (for LLM retrieval)

Already covered in Section 5.2 above. Repeat: **HIGH priority** as the free
web-search retrieval tool for any LLM forecasting pipeline.

### 9.4 Polymarket lifecycle dataset (arXiv 2604.20421)

- **Source:** Huaiyu Jia et al., "Unlocking the Forecasting Economy: A Suite
  of Datasets for the Full Lifecycle of Prediction Market," April 2026.
- **Content:** 770,000+ Polymarket market records, 943M fill records (trades),
  2M oracle resolution events, October 2020 to March 2026. Full lifecycle data.
- **Access:** Academic dataset. Specific download URL not confirmed in this
  scout; check the arXiv paper's data section or supplementary materials.
- **Relevance:** For any Polymarket cross-venue analysis. Primary value is as
  a calibration training dataset for a fine-tuned LLM or ML model on prediction
  market outcomes. The NBA calibration and CPI case studies in the paper confirm
  the data is usable for quantitative modeling.
- **PRIORITY: MEDIUM** if v10 pursues a Polymarket-feature or calibration-
  training angle. The CLOB `/orderbook-history` degradation (Feb 2026) makes
  the full dataset paper more valuable as a historical record.

### 9.5 Jon Becker prediction-market-analysis GitHub dataset

- **Source:** github.com/Jon-Becker/prediction-market-analysis. Described as
  "the largest publicly available dataset of Polymarket and Kalshi market and
  trade data." Kalshi 72.1M trades through November 2025 (previously documented
  as Becker 2026, lit #2).
- **New development:** As of May 2026, a new "comprehensive dataset spanning
  October 2020 to March 2026 with more than 700,000 market records, over 900
  million trade fill records, and nearly 2 million oracle events" was described
  in one search result (possibly associated with arXiv 2604.20421 above or with
  an extended Becker release).
- **Access:** GitHub (open access). No API key.
- **PRIORITY: MEDIUM.** The Kalshi trade data in Becker 2026 was already
  used in lit #2 extraction. If an updated version includes data through early
  2026, it could feed a sports microstructure analysis for v10 (non-crypto
  series: KXNFLGAME, KXBOXING, KXUFCFIGHT trade history).

---

## Section 10: Verified Probe Status Summary

All probe results below are inherited from v7 and v9 sessions (live probes
from this session's CA IP on 2026-05-25 and 2026-05-26). No new live curl
probes were executed in this scout (budget constraint; scope is mapping, not
re-probing).

```
Source                        v7 probe        v9 probe       Status
----------------------------  --------------  -------------  -------------------
Hyperliquid /info             200 OK          (not re-probed) CONFIRMED FREE
dYdX v4 indexer               200 OK          (not re-probed) CONFIRMED FREE
Kraken /public/Trades         200 OK          (not re-probed) CONFIRMED FREE
Bitstamp /api/v2/order_book   200 OK          (not re-probed) CONFIRMED FREE
DefiLlama /v2/historicalTvl   200 OK          (not re-probed) CONFIRMED FREE
ESPN site.api (6 sports)      200 OK          200 OK         CONFIRMED FREE
the-odds-api (live)           401 (key OK)    200 OK (key in .env) KEY PRESENT
GDELT api.gdeltproject.org    timeout (3x)    429 (rate-lim)  REACHABLE (use bulk)
Bluesky public.api            403 (needs auth) (not re-probed) AUTH REQUIRED
Polygon /v2/reference/news    401 (key needed)(not re-probed) KEY REQUIRED (paid)
Alpha Vantage NEWS_SENTIMENT  200 demo        (not re-probed) CONFIRMED (25/day)
Coinglass /public/v2/funding  200 (key-gated)(not re-probed) PAID ONLY
Glassnode /v1/metrics         401             (not re-probed) PAID ONLY
---
NEW sources (not probed live, status from web research only)
---
Google Gemini 2.5 Flash       (not probed)    (not probed)   FREE (docs confirmed)
DeepSeek V4 Flash             (not probed)    (not probed)   FREE trial + cheap paid
Groq Llama-3.1-70B            (not probed)    (not probed)   FREE tier 1k/day
Tavily Search API             (not probed)    (not probed)   FREE 1k/month
FRED API                      (not probed)    (not probed)   FREE (key required)
Kraken Futures funding rate   (not probed)    (not probed)   DOCUMENTED FREE
Binance.US REST API           (not probed)    (not probed)   LIKELY FREE (docs)
SEC EDGAR full-text search    (not probed)    (not probed)   FREE no key
EIA energy API                (not probed)    (not probed)   FREE (key via email)
NOAA CDO API                  (not probed)    (not probed)   FREE (key via web)
```

---

## Priority Matrix Summary

| Source | Priority | Cost | Kalshi market fit | New vs v7? |
|--------|----------|------|-------------------|------------|
| Gemini 2.5 Flash (AI Studio) | HIGH | Free | LLM ensemble | YES |
| Tavily Search API | HIGH | Free (1k/mo) | LLM retrieval | YES |
| FRED API | HIGH | Free (key) | KXFEDFUNDS / KXCPI / KXNFP | NEW key req |
| ESPN site.api | HIGH | Free | All sports | Confirmed |
| DeepSeek V4 Flash | MEDIUM | $0.14/M (5M free) | LLM ensemble | YES |
| Groq (Llama-3.1-70B) | MEDIUM | Free (1k/day) | LLM ensemble | YES |
| GDELT 2.0 bulk download | MEDIUM | Free | News sentiment | Confirmed |
| Kraken Futures funding | MEDIUM | Free | Crypto cross-venue | YES |
| Binance.US API | MEDIUM | Free | Crypto cross-venue | YES |
| 538 sports archives | MEDIUM | Free (CSV) | Sports ML features | Existing |
| NOAA CDO API | MEDIUM | Free (key) | Weather (EC-1 killed) | Existing |
| EIA energy API | MEDIUM | Free (key) | KXWTI / KXNATGAS | NEW |
| Polymarket lifecycle dataset | MEDIUM | Free (academic) | Calibration training | NEW |
| Becker extended dataset | MEDIUM | Free (GitHub) | Kalshi trade history | NEW ext |
| BLS API | MEDIUM | Free (key) | KXCPI / KXNFP | Existing |
| o4-mini (OpenAI) | MEDIUM | ~$1/M | LLM ensemble top | Existing |
| Polygon.io free | LOW | Free (5 calls/min) | Equity Kalshi markets | Existing |
| SEC EDGAR full-text | LOW | Free (no key) | Financial event mkt | NEW |
| FiveThirtyEight sports | LOW-MED | Free CSV | Sports features | Existing |
| Bluesky Jetstream | LOW | Free | Sports sentiment | Existing |
| HackerNews API | LOW | Free | KXAI/KXTECH only | Existing |
| BEA API | LOW | Free (key) | KXGDP | Existing |
| World Bank / OECD | SKIP | Free | Non-US | Existing |
| Brave Search API | SKIP | Paid only new users | LLM retrieval | CHANGED |
| Coinglass Hobbyist | SKIP | $29/mo | Crypto (dup Hyperliquid) | Unchanged |
| NewsAPI | SKIP | Dev-only/paid | News | Unchanged |
| Sportradar | SKIP | Enterprise | Sports | Unchanged |
| Tardis | SKIP | $350+/mo | Crypto L2 | Unchanged |
| Trading Economics | SKIP | Paid | Macro | Unchanged |
| X / Twitter API | SKIP | $200/mo | Social | Unchanged |
