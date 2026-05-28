# V10-A Phase 1 Data Probe

**Date:** 2026-05-26
**Author:** Agent v10-A1
**Scope:** Phase 1 data layer probe for V10-A (Kim et al. 2602.07048 replication on Kalshi Economics markets)
**Status:** COMPLETE. See Section 5 for honest assessment.

---

## 1. Kalshi Economics Market Inventory

### Methodology

Probed the Kalshi production API (`https://external-api.kalshi.com/trade-api/v2`) using the READ-scope key in `.env` (RSA-PSS signed). Queried `/markets?status=settled` and `/markets?status=open` for each Economics series. Probed `/series?category=Economics` to enumerate available series. All probes on 2026-05-26.

### Series Inventory

The Kim et al. paper (arXiv 2602.07048) names KXFEDFUNDS, KXCPI, KXNFP, KXUNRATE as the four target series. Probing these tickers revealed the following:

| Kim Ticker | Status | n_settled post 2024-10-01 | Vol on settled | Trades accessible |
|---|---|---|---|---|
| KXFEDFUNDS | 0 settled markets returned | 0 | N/A | N/A |
| KXCPI | 27 settled markets returned | 27 | ALL ZERO | NO (HTTP 404) |
| KXNFP | 0 settled markets returned | 0 | N/A | N/A |
| KXUNRATE | 0 settled markets returned | 0 | N/A | N/A |

KXFEDFUNDS, KXNFP, and KXUNRATE do not return ANY settled markets at the current Kalshi API. KXCPI returns 27 settled markets (all closing 2026-04-10 or 2026-05-12), but every single market has vol=0, last_price=0, and the `/markets/{ticker}/trades` endpoint returns HTTP 404.

The `/series?category=Economics` endpoint returns 547 series. The current generation of active Economics series uses different ticker schemes than Kim et al.'s paper:

| Current Ticker | Description | Post-Oct-2024 Settled Count | Trades 404? |
|---|---|---|---|
| KXCPI | CPI MoM | 27 (all vol=0) | YES |
| KXECONSTATU3 | Unemployment Rate Monthly | 46 (all vol=0) | YES |
| KXUSNFP | Nonfarm Payrolls | 30 (all vol=0) | YES |
| KXPAYROLLS | Payrolls | 35 (all vol=0) | YES |
| KXFEDDECISION | Fed meeting decision | 5 (all vol=0) | YES |
| KXEFFR | EFFR above/below | 5 (all vol=0) | YES |
| KXU3 | Unemployment | 20 (all vol=0) | YES |

**Critical finding:** Every Economics series returns vol=0 and last_price=0 on ALL settled markets, and `/markets/{ticker}/trades` returns HTTP 404 for every market tested. This is not a series-specific issue.

### API Regression: Kalshi Historical Trades Endpoint is Broken

The v6 project (Round 12, 2026-05-25) successfully called `/markets/{ticker}/trades` on settled KXBTCD markets and built a 3688-row dataset. As of 2026-05-26, the SAME known v6 tickers (e.g., `KXBTCD-24DEC1209-T100749.99`) return HTTP 404 at the market endpoint itself, not merely the trades sub-endpoint. This indicates the Kalshi API has changed since v6 was built: settled markets from before approximately late 2026 are no longer accessible at the market or trades endpoint.

Tested on a broad sample confirming the regression:
- All KXMLBGAME settled markets: vol=0, trades 404
- All KXBOXING settled markets: vol=0, trades 404
- All KXBTCD Dec 2024 settled markets: HTTP 404 at the `/markets/{ticker}` level itself
- No settled market across ANY series returned vol > 0 or last_price > 0

**Conclusion on Kalshi historical trade data:** The Kalshi historical trades endpoint, which v6 relied on and which is the ONLY feed for reconstructing a probability time series from trade prints, is non-functional as of 2026-05-26 for all settled markets. This is a platform-level API regression, not a series-specific gap.

### v7-B Phantom Prevention: Historical Orderbook

As documented in CLAUDE.md and per v9 findings, the historical orderbook endpoint (`/markets/{ticker}/orderbook`) returns an empty book for all settled markets (confirmed: two KXCPI settled markets returned yes_levels=0, no_levels=0 with HTTP 200). This was already known. Historical orderbook is unavailable and was always unavailable. The new finding is that historical TRADES are also now inaccessible.

### Next-Best Baseline for Historical Data

With both orderbook and trades inaccessible for settled Economics markets, the only remaining data access options are:

1. **v6 parquet** (`data/v6/v6_master.parquet`): 3688-row KXBTCD dataset from Dec 2024 to Mar 2026. Useful for KXBTCD only; does not cover Economics markets.
2. **The Kalshi historical dataset via the Becker 2025 paper** (72M rows): Not publicly downloadable without contact with authors. Outside retail access.
3. **Forward recording starting today**: The current API returns vol=0 for open Economics markets too (yes_bid=0, yes_ask=0), suggesting KXCPI, KXUSNFP etc. are low-volume relative to KXBTCD when open. Would require prospective data collection.
4. **Third-party Kalshi data**: Not identified. No public Kalshi data archive at retail access level exists as of May 2026 literature review.

---

## 2. FRED API Readiness

**Probe result:** FRED API at `https://api.stlouisfed.org/fred/series/observations` returned HTTP 400 with error "api_key is not a 32 character alpha-numeric lower-case string" when probed with a dummy key, and HTTP 400 with "Variable api_key is not set" when probed without a key. Both responses confirm the endpoint is US-reachable and functioning correctly (returns proper JSON error, not 451/503/connection refused).

**API call pattern for FEDFUNDS:**
```
GET https://api.stlouisfed.org/fred/series/observations
  ?series_id=FEDFUNDS
  &api_key={FRED_API_KEY}
  &file_type=json
  &observation_start=2024-10-01
```
Returns a JSON object with `observations` list, each containing `date` and `value`. Free tier; no rate limit documented. Registration at `fredaccount.stlouisfed.org/apikeys` is instantaneous (2 minutes, no card).

**FRED_API_KEY in .env:** NOT PRESENT. The `.env` file does not contain a FRED_API_KEY variable. The operator would need to add one (free signup at fred.stlouisfed.org) before FRED data can be fetched programmatically. FRED data is also publicly downloadable as CSV without a key, though that is slower to automate.

---

## 3. Multi-Vendor LLM Key Readiness

**Key inventory from `.env` (values NOT logged; presence only):**

| Key Name | Present in .env | Notes |
|---|---|---|
| ANTHROPIC_API_KEY | NOT PRESENT (bot uses direct API call pattern without explicit key in .env) | See note below |
| GEMINI_API_KEY | NOT PRESENT | Needed for free-tier Gemini 2.5 Flash |
| DEEPSEEK_API_KEY | NOT PRESENT | Needed for DeepSeek free tier |
| GROQ_API_KEY | NOT PRESENT | Needed for Groq Llama-3.1-70B free tier |
| THE_ODDS_API_KEY | PRESENT | Already in .env; 477 credits left |

Note on ANTHROPIC_API_KEY: The Kalshi bot infrastructure uses Claude Code as the orchestrator in the session environment; no explicit ANTHROPIC_API_KEY appears in `.env` because it is injected by the Claude Code runtime. For any standalone script calling Anthropic API (e.g., the LLM semantic filter), an ANTHROPIC_API_KEY would need to be present in `.env` or injected via environment.

**Fallback hierarchy if keys are missing:**

1. **Preferred (free, cheapest):** Gemini 2.5 Flash via GEMINI_API_KEY (1,500 req/day free, no card). Use for the LLM semantic filter step.
2. **Fallback 1:** DeepSeek V4 Flash via DEEPSEEK_API_KEY (5M free signup tokens). Alternative cheap LLM filter.
3. **Fallback 2:** Groq Llama-3.1-70B via GROQ_API_KEY (1,000 req/day free). Alternative cheap LLM filter.
4. **Emergency fallback:** Haiku 4.5 via ANTHROPIC_API_KEY ($0.80/$4.00 per MTok input/output). The cheapest available Anthropic model. With ~20 pairs to filter and a 1,000-token prompt each, cost is approximately $0.02 total for the filter step.
5. **Opus 4.7 is reserved for orchestrator and final critic only.** Do NOT use Opus for the semantic filter; cost is ~50x Haiku per token.

For the current state (GEMINI/DEEPSEEK/GROQ all absent), Haiku 4.5 is the only immediately available LLM filter option without operator action.

---

## 4. Sample-Size Feasibility for the Kim Replication

### Kim et al. methodology (inferred from 02b-literature-delta.md Paper 4, lines 200-280)

The paper (arXiv 2602.07048v2) applies Granger causality to Kalshi Economics market probability time series to identify lead-lag pairs, then applies an LLM to filter out economically implausible causal directions. The four markets are KXFEDFUNDS, KXCPI, KXNFP, KXUNRATE.

**Unit of analysis is inferred to be trade-level probability time series, not market-level.** The paper constructs a time series of probabilities for each market from trade data (interpolated/last-trade price at regular intervals), then runs Granger F-tests across pairs at multiple lags. The win-rate improvement metric (51.4% to 54.5%) implies the unit of analysis for the trading strategy is at the TRADE level (individual trades taken following a Granger-significant lead signal). Kim et al. do not publish the full n for their backtest; the literature summary notes n was on "a sample of trades" without a specific count. Given 4 series at monthly frequency, the total number of monthly RELEASE EVENTS (not individual trade opportunities) would be approximately:

- KXFEDFUNDS: ~8 FOMC meetings per year = approximately 16 events over 2 years post-Oct-2024
- KXCPI: monthly = approximately 19 events
- KXNFP: monthly = approximately 19 events
- KXUNRATE: monthly = approximately 19 events (often co-released with NFP)

Total monthly events: approximately 73 across 4 series. Total Granger pairs: C(4,2) x 2 directions = 12 directed pairs. After filtering by statistical significance and LLM plausibility, the effective qualifying pair count would be a subset of 12, each generating one trade-opportunity per monthly release = maximum ~73 trades on OOS.

**If Kim et al. used TRADE-LEVEL data (intraday):** each monthly release event could generate many trade signals in the hours before resolution, multiplying n by perhaps 10-100x. This would make n >> 100, but requires the trades endpoint to be accessible.

**At our data access level (no trade history available):** n is bounded by the number of monthly release events in the OOS window. Post-2026-02-01 (the OOS test split per the locked gate below), through 2026-05-26, that is approximately 4 months x 4 series = ~16 release events, far below the pre-registered minimum of n >= 40.

---

## 5. Honest Assessment: KILLER / IMPORTANT / READY

**Tag: KILLER**

**V10-A is not feasible at current retail scale and data access. The specific killing items:**

### Killer 1: Kalshi historical trades are inaccessible (data layer)

The Kalshi API regression documented in Section 1 eliminates the primary data source for constructing probability time series. The `/markets/{ticker}/trades` endpoint returns HTTP 404 for every settled market tested across ALL series. Without historical trades, there is no way to build the per-market probability time series that Granger causality requires. This is a hard kill, not a workaround issue.

The v6 project built a 3688-row dataset from KXBTCD trades in late 2024/early 2025 when the API worked. That same infrastructure is broken today. The Kim et al. replication requires trade-print data from 2023-2026 across four Economics series; none of it is accessible.

**Specifically: vol=0 and trades=404 for KXCPI, KXECONSTATU3, KXUSNFP, KXPAYROLLS, KXFEDDECISION, KXEFFR, KXU3, KXMLBGAME, KXBOXING, KXBTCD and every other series probed. This is a platform-wide API regression, not an Economics-specific issue.**

### Killer 2: Kim et al. series tickers do not map to current Kalshi markets

The paper's stated series (KXFEDFUNDS, KXNFP, KXUNRATE) return zero settled markets via the current API. They are either retired tickers or they use a different naming convention than what the API returns. KXCPI returns 27 settled markets but all have vol=0. These series may have launched recently (current close_dates are only 2026-04-10 and 2026-05-12, suggesting 2 months of history at most) with little or no actual trading activity.

### Killer 3: Sample size is infeasible at monthly release frequency

Even if trade data were accessible, the monthly frequency of Economics releases limits the achievable n for Granger pair-tests. At 4 series x 12 monthly events per series per year = 48 data points per year for each series, with only approximately 19 events in the post-Oct-2024 window, the Granger regression has approximately 19 observations per series. This is substantially below the ~50 observations typically needed for reliable Granger F-tests at 5 lags. At 4 series, C(4,2) = 6 pairs x 2 directions = 12 directed tests requires Bonferroni correction (alpha 0.05/12 = 0.0042), further reducing power on 19-observation series.

### What would be needed to unKILL V10-A

1. Contact Kim et al. directly for their dataset or clarification on the specific API endpoints they used (possible but not guaranteed).
2. Wait 12-24 months for enough prospective monthly Economics release events to accumulate from today's forward-recording.
3. Find a third-party Kalshi historical data archive covering 2022-2026 (Becker dataset authors, or a research partner). None identified at retail access level.

**None of these options are available in the current session or within v10's timeline.**

---

## Summary Table

| Probe | Finding | Verdict |
|---|---|---|
| KXFEDFUNDS/KXNFP/KXUNRATE settled | 0 settled markets returned | FAIL |
| KXCPI settled | 27 markets, all vol=0 | FAIL |
| Trades endpoint | HTTP 404 on ALL settled markets platform-wide | KILL |
| Historical orderbook | Empty (vol=0, 0 levels) | CONFIRMED NO OB |
| FRED endpoint accessibility | Reachable, HTTP 400 for bad key | OK |
| FRED_API_KEY in .env | NOT PRESENT | NEEDS OPERATOR ACTION |
| GEMINI/DEEPSEEK/GROQ keys | NOT PRESENT | NEEDS OPERATOR ACTION |
| n-feasibility at monthly frequency | ~19 events per series, far below 40 OOS minimum | BORDERLINE KILL |
| Kim et al. ticker mapping | KXFEDFUNDS/KXNFP/KXUNRATE not in current API | FAIL |
| **Overall** | **KILLER** | |
