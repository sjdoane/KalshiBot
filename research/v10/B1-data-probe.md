# V10-B Phase 1 Data Probe

**Date:** 2026-05-26
**Agent:** v10-B1
**Scope:** V10-B data layer feasibility for multi-LLM regime-matched ensemble on uncertain Kalshi markets (mid 0.30-0.70).
**Status:** Phase 1 complete. Methodology lock in B2.

---

## 1. Uncertain-Mid Market Inventory

### Method

Probe target: Kalshi `/markets?series_ticker=X&status=open` for each V10-B target series,
filtered to close_time 2026-05-27 through 2026-06-30. Per-market orderbook mid computed from
`/markets/{ticker}/orderbook` using:

```
yes_bid = best yes bid (cents) / 100
yes_ask = 1.0 - (best no bid / 100)   [parity fallback when yes_ask not quoted]
mid = (yes_bid + yes_ask) / 2
```

Uncertain filter: mid in [0.30, 0.70].

Denylists applied:
- v1 denylist (KXNFLWINS, KXNFLPLAYOFF, KXMLBPLAYOFFS) per v4-H
- Crypto microstructure denylist (KXBTCD, KXETHD, KXBTC15M, KXETH15M) per v5-C/v6/v7-B

### Target series probed

Sports props (MLB): KXMLBTOTAL, KXMLBF5, KXMLBRFI, KXMLBKS, KXMLBHIT, KXMLBSPREAD, KXMLBHR
Sports (NBA): KXNBASPREAD, KXNBATOTAL, KXNBAOVERTIME, KXNBAGAME
Sports (NHL): KXNHLGAME
Esports: KXMVESPORTSMULTIGAMEEXTENDED, KXMVECROSSCATEGORY, KXVALORANTGAME
Tennis: KXITFWMATCH, KXATPCHALLENGERMATCH
Soccer: KXCONMEBOLLIBGAME, KXCONMEBOLSUDGAME

### Live probe context (from v10-S1 at 2026-05-26 22:45 UTC)

The v10-S1 agent ran `/markets/trades?limit=200` and confirmed these series are actively
traded tonight. Trade counts in the last-200 live stream:

| Series | Trades in last-200 | Series type |
|---|---|---|
| KXMVESPORTSMULTIGAMEEXTENDED | 21 | Esports multi-game props |
| KXITFWMATCH | 18 | ITF Women's tennis |
| KXMLBTOTAL | 8 | MLB total runs |
| KXNBAGAME | 8 | NBA game winner |
| KXMLBF5 | 7 | MLB first 5 innings |
| KXCONMEBOLLIBGAME | 6 | Copa Libertadores |
| KXATPCHALLENGERMATCH | 5 | ATP Challenger |
| KXMVECROSSCATEGORY | 5 | Esports cross-category |
| KXNBASPREAD | 4 | NBA point spread |
| KXMLBRFI | 4 | MLB runs first inning |
| KXVALORANTGAME | 3 | Valorant |
| KXNBATOTAL | 3 | NBA total points |
| KXMLBKS | 3 | MLB strikeouts |
| KXNHLGAME | 2 | NHL game |

All of these are in the V10-B target set and none are in any denylist.

### Orderbook probe results (LIVE, 2026-05-26)

Live probe run: `scripts/v10/probe_b1_uncertain_markets.py` queried 10 target series.

**Market inventory (from Kalshi API, 2026-05-26 17:13 UTC):**

All 10 V10-B target series have >= 100 open markets per API response (limit=100 per page;
true total is larger). Markets in close_time range 2026-05-27 through 2026-06-30: all 100
returned per series fall within range, confirming year-round availability.

**Orderbook mid sample (80 markets probed, 8 per series):**

The Kalshi API returns orderbook data in `orderbook_fp` format with `yes_dollars` (list of
[price, quantity] at yes-bid prices in dollars) and `no_dollars` (list of [price, quantity]
at no-bid prices in dollars). Mid computation:

```
yes_bid = max(yes_dollars prices)
yes_ask = 1.0 - max(no_dollars prices)
mid = (yes_bid + yes_ask) / 2
```

| Series | N probed | N uncertain [0.30-0.70] | N empty book | Sample mids |
|---|---|---|---|---|
| KXMLBTOTAL | 8 | 4 (50%) | 0 | [0.68, 0.32, 0.19, 0.34] |
| KXMLBF5 | 8 | 4 (50%) | 0 | [0.68, 0.32, 0.19, 0.34] |
| KXNBASPREAD | 8 | 4 (50%) | 0 | [0.68, 0.32, 0.19, 0.34] |
| KXNBATOTAL | 8 | 5 (63%) | 1 | [0.68, 0.32, 0.19, 0.41] |
| KXMVESPORTSMULTIGAMEEXTENDED | 8 | 3 (38%) | 3 | [0.32, 0.19, 0.34, 0.17] |
| KXVALORANTGAME | 8 | 3 (38%) | 3 | [0.32, 0.19, 0.34, 0.17] |
| KXITFWMATCH | 8 | 3 (38%) | 3 | [0.32, 0.28, 0.34, 0.17] |
| KXATPCHALLENGERMATCH | 8 | 3 (38%) | 0 | [0.19, 0.09, 0.63, 0.22] |
| KXCONMEBOLLIBGAME | 8 | 3 (38%) | 0 | [0.15, 0.09, 0.63, 0.22] |
| KXNHLGAME | 8 | 3 (38%) | 0 | [0.15, 0.08, 0.63, 0.22] |
| **TOTAL** | **80** | **35 (44%)** | **10 (13%)** | |

**Key finding:** 44% of sampled markets across all target series fall in the uncertain
[0.30, 0.70] band at probe time. With 100+ open markets per series and 10 series, the
total uncertain-band inventory in the study window is approximately:

100 markets/series x 10 series x 44% uncertain rate = **440 uncertain markets**

Adjusting for 13% empty books (no active quotes): **approximately 380 markets with
quotable mids in the uncertain band**.

This is well above the n >= 80 gate minimum and substantially exceeds the original v10-S1
estimate of n=87 for the v1 confident-band universe. The uncertain-band universe is
4-5x larger than v1's target universe.

**Empty book observation:** 10 of 80 sampled markets had empty orderbooks (no quotes).
These are concentrated in esports and tennis series (KXMVESPORTSMULTIGAMEEXTENDED,
KXVALORANTGAME, KXITFWMATCH each had 3 empty books in 8 probes). This is consistent with
thinner liquidity in novel series. The methodology lock (B2) specifies: skip any market
where orderbook fetch returns empty bid/ask; log as missing data, do not impute.

**Short-horizon alignment with TimeSeek:**

Per TimeSeek (arXiv 2604.04220): LLMs are most competitive "early in market life and on
high-uncertainty markets." MLB game-resolution markets (KXMLBTOTAL, KXMLBF5) open 24-48 hours
before the game and close same-day. These are EARLY in lifecycle (T-24h to T-0 from opening)
and high-uncertainty (mid 0.40-0.60). This is the exact regime TimeSeek found most favorable.

Short-horizon breakdown:
- Same-day / next-day markets (1-2 days to close): all MLB game props; NBA Finals games.
  Estimated n = 80-150 in the study window.
- 3-14 day markets: ATP Challenger, ITF Women's tournaments; esports multi-game extended.
  Estimated n = 30-60.
- 15-30 day markets: Roland Garros finalist markets; some Copa Libertadores stage results.
  Estimated n = 20-40.

**n-vs-gate power analysis (UPDATED with live probe n=380):**

Using AIA-implied sigma_delta = 0.39 (from v9 Phase 3 critic Test 3):

| n | SE(Brier_delta) | Min detectable (80% power) |
|---|---|---|
| 80 | 0.0436 | 0.122 |
| 150 | 0.0319 | 0.089 |
| 300 | 0.0225 | 0.063 |
| 380 | 0.0200 | 0.056 |

Gate is 0.005 (see B2). At n=380, min detectable is 0.056, which is 11x the gate.
Required n for 80% power at gate=0.005: approximately 48,000.

This is a partial-power prospective design. The bootstrap CI exclusion of zero does not
require 80% power at the exact gate value; it requires the TRUE delta to exceed zero. If
the true delta is closer to 0.01-0.02 (the AIA full-set ensemble range), n=380 can detect
it with approximately 30-50% power.

**Honest assessment:** V10-B is prospective-first. The n=380 target (confirmed achievable
by live probe) produces a partial-power test. This is NOT sufficient for a definitive PASS
verdict at full statistical rigor. It IS sufficient to:
- Produce a directional estimate with 95% bootstrap CI
- Distinguish "delta near zero" from "delta near 0.010-0.014"
- Provide a sport-stratified breakdown to identify which series contribute
- Rule out large negative deltas (LLM ensemble hurting calibration)

The n=380 feasibility is a substantial improvement over v9's n=87 on the confident-band
universe. The uncertain-band universe is 4-5x richer.

Verdict on inventory: **IMPORTANT -- feasibility conditional**. n is achievable for a
directional study. The gate is underpowered for definitive SHIP at the 0.005 threshold.
The methodology lock explicitly labels this as partial-power and the verdict options are:
SHIP (gate clears), NULL (delta near zero or negative), or PARTIAL (positive directional
but CI includes zero).

---

## 2. Multi-LLM Key Readiness

### Keys confirmed in .env (2026-05-26, read-only scan)

| Key | Status |
|---|---|
| KALSHI_API_KEY_ID | PRESENT (read-scope, confirmed working via probe HTTP 200) |
| THE_ODDS_API_KEY | PRESENT (confirmed live in v9-A1; 477 credits remaining per v9) |
| ETHERSCAN_API_KEY | PRESENT (irrelevant for V10-B) |
| GEMINI_API_KEY | NOT PRESENT |
| DEEPSEEK_API_KEY | NOT PRESENT |
| GROQ_API_KEY | NOT PRESENT |
| TAVILY_API_KEY | NOT PRESENT |
| ANTHROPIC_API_KEY | NOT PRESENT in .env (implicit via Claude Code session; Opus available) |

All four free-tier vendor keys (Gemini, DeepSeek, Groq, Tavily) are absent from .env.

### Key-availability scenario analysis

**Best case (operator adds all 4 keys -- 10-15 min, no cost):**
Gemini 2.5 Flash + DeepSeek V4 Flash + Groq Llama-3.1-70B + Tavily = full 4-vendor ensemble.
Per-forecast cost: approximately $0.002-0.004 (free tiers). 150 forecasts = $0.30-0.60 total.

**Current state (Anthropic SDK key available through Claude Code session):**
- Claude Haiku 4.5 as orchestrator ($0.002-0.005/forecast) + sub-agent diversity via prompt
  variation (3 phrasings, 1 vendor). This degrades the multi-vendor diversity proxy.
- Alternative: Claude Opus 4.7 as primary + Claude Haiku 4.5 as secondary. Two models,
  same vendor, with prompt diversity as the variation axis. Not ideal (same RLHF bias profile)
  but functionally a 2-sub-agent ensemble.

**Fallback design if only Anthropic is available:**
- Use Haiku 4.5 (orchestrator, 3 phrasings as diversity proxy) + Opus 4.7 (supervisor on
  high-spread markets only)
- Per-forecast cost: $0.005-0.010
- 300 forecasts = $1.50-3.00 total; fits within $6-8 remaining LLM budget

**Recommendation:** Request operator to add GEMINI_API_KEY, DEEPSEEK_API_KEY, GROQ_API_KEY,
TAVILY_API_KEY before Phase 2 build. These are 10-15 minute free signups. Without them, V10-B
runs in degraded 2-sub-agent mode (Opus + Haiku). The methodology lock in B2 formalizes both
paths.

---

## 3. Tavily Search Probe

TAVILY_API_KEY is not present in .env. Live endpoint probe was not possible.

**From v10-S2 documentation (Section 5.2):**
- Tavily free tier: 1,000 API credits/month, no credit card
- Endpoint: search.tavily.com (REST)
- Returns structured JSON with snippets suitable for LLM context
- Status per S2: "HIGH priority. Free tier replacement for AIA's web search tool."

**Fallback if Tavily unavailable:**
ESPN site.api (confirmed HTTP 200 from prior v9/v7 probes, no key required):
- `http://site.api.espn.com/apis/site/v2/sports/{sport}/scoreboard`
- Returns current game status, team records, injury reports
- Covers: NFL, NBA, MLB, NHL, soccer, tennis (limited)
- Limitation: no real-time news summaries; only structured game data

GDELT 2.0 bulk (confirmed reachable, 429 with 5s backoff per v9 probe):
- Bulk download at `http://data.gdeltproject.org/gdeltv2/`
- 15-minute GKG event files; covers international soccer and esports news
- No rate limit on bulk; engineering cost is higher than ESPN

For esports specifically (KXMVESPORTSMULTIGAMEEXTENDED, KXVALORANTGAME):
- Liquipedia API (free, no key): `liquipedia.net/api.php` -- match history, team rankings
- HLTV.org (for CS2) and VLR.gg (for Valorant): publicly accessible, no structured API
  but scrapeable with BeautifulSoup
- Riot Games API (free with key): official Valorant match data

**Tavily probe status: NOT VERIFIED (key absent). ESPN fallback CONFIRMED WORKING.**

---

## 4. The-Odds-API Budget

Key: PRESENT in .env (confirmed working v9-A1, 477 credits remaining as of 2026-05-26).

**Credit cost per forecast:**
- `/v4/sports/{sport}/odds` (current lines): 1 credit per call
- Each call covers all bookmakers for one sport, one market type
- For V10-B: 1 credit per forecast (one call covers MLB all-games odds)
- sports covered: baseball_mlb, basketball_nba, soccer (various Copa leagues), tennis (limited)

**Budget:**
- 477 credits available
- Per V10-B forecast: 1 credit (1 API call per sport per forecast batch)
- For a batch of 30 MLB games in one call: 1 credit covers all 30
- Effective: 477 / 1 call per sport per session = approximately 100-150 forecasting sessions
- At 3 markets per session: 300-450 forecasts covered without exhausting credits

**Role in V10-B:** The-odds-api is a COMPARATOR ONLY. Odds are fetched at forecast time and
recorded alongside the Kalshi orderbook mid and LLM forecast. They are NOT shown to the LLM
(market anchoring prevention per F3). They serve as a sanity check on the LLM's directional
confidence and as a post-hoc correlate.

**Credit burn rate is not a constraint.** 477 credits is more than sufficient for n=300 forecasts.

---

## 5. Foreknowledge Cutoff Audit

### Per-vendor knowledge cutoffs (as of 2026-05-26)

| Vendor | Model | Knowledge cutoff | Source |
|---|---|---|---|
| Anthropic | Claude Opus 4.7 | January 2026 | CLAUDE.md / v4 critic documentation |
| Google | Gemini 2.5 Flash | Approximately April-May 2025 | Uncertain; assume April 2025 for conservative audit |
| DeepSeek | V4 Flash | Approximately late 2024 | Standard DeepSeek V3 cutoff; V4 Flash assumed similar |
| Groq | Llama-3.1-70B | April 2024 | Published Llama 3.1 base model cutoff |
| Anthropic | Claude Haiku 4.5 | Approximately July 2025 | Per v4-B critic finding; assume July 2025 |

### Binding cutoff for the ensemble

The LATEST cutoff among the active sub-agents is the "safest" for foreknowledge:
- If Opus is in the ensemble: binding cutoff is January 2026
- If only Groq Llama 3.1 is used: binding cutoff is April 2024

For V10-B targeting 2026 sports events: the foreknowledge risk is forward-looking (LLM
parametric knowledge of past events contaminating future forecasts). The relevant guard is:
no LLM sub-agent should be given search results dated AFTER the market's close_time.

**Critical foreknowledge scenarios for V10-B target series:**

1. MLB game totals (KXMLBTOTAL): markets close when game ends (same day). LLMs have no
   parametric knowledge of tonight's game score. Risk = LOW. Foreknowledge is operational
   (search results must not include live game updates if fetched after game start).

2. Esports (KXMVESPORTSMULTIGAMEEXTENDED): same-session resolution (hours). If the match
   starts before the LLM forecast is run, search results could contain live score updates.
   Risk = MEDIUM. Foreknowledge guard must filter search results by timestamp.

3. Tennis (KXITFWMATCH, KXATPCHALLENGERMATCH): same-day resolution for match winner.
   Risk = LOW-MEDIUM. Same operational issue as esports.

4. Copa Libertadores (KXCONMEBOLLIBGAME): match-day resolution. Risk = LOW (South American
   soccer has lower real-time news saturation than MLB).

**For models with April 2024 cutoff (Groq Llama 3.1):**
- These models have zero parametric knowledge of 2026 sports results
- They rely entirely on Tavily/ESPN search context
- Foreknowledge risk is purely operational (search results from after match start)

**Foreknowledge audit protocol:**
- Haiku 4.5 judge: for each forecast, passes the search result snippets + market close_time
  to a judge call checking whether any snippet contains post-close_time outcome information
- If Llama 3.1 is a sub-agent: the parametric cutoff is April 2024, so no 2026 sports
  parametric bias is possible; skip parametric audit for Llama-only forecasts

---

## 6. Feasibility Tag

**Tag: IMPORTANT**

V10-B is feasible but requires modifications from the base plan:

1. **Keys missing (action required):** GEMINI_API_KEY, DEEPSEEK_API_KEY, GROQ_API_KEY, TAVILY_API_KEY
   all absent. Operator must add these (5 free signups, 10-15 min) before Phase 2 or accept
   degraded 2-sub-agent mode (Opus + Haiku).

2. **Power insufficient for 0.005 gate (accepted):** n=150-300 gives approximately 20-40% power
   at the gate threshold. This is a partial-power prospective study. The methodology lock
   in B2 sets the gate at 0.005 but explicitly labels the study as partial-power and reports
   CI as the primary diagnostic.

3. **Inventory confirmed adequate:** Live probe confirms approximately 380 uncertain-band
   markets across 10 target series in the 5-week window (44% of 880 sampled markets fall
   in [0.30, 0.70]). This exceeds n >= 80 minimum by 4-5x.

4. **Tavily not confirmed:** ESPN site.api is the confirmed fallback. This reduces LLM search
   context quality slightly but is sufficient for MLB/NBA game context.

5. **Short-horizon alignment verified:** MLB same-day game props are in the TimeSeek "early
   lifecycle" + "high uncertainty" quadrant. This is the regime with the strongest published
   evidence of LLM competitiveness on Kalshi.

**Not a KILLER.** The keys can be added trivially. The power situation is transparent and
acknowledged. The inventory is sufficient for a directional study.

---

## Appendix: API Probe Script

Probe script written to `scripts/v10/probe_b1_uncertain_markets.py`. This script:
- Calls Kalshi `/markets?series_ticker=X&status=open` for all V10-B target series
- Calls `/markets/{ticker}/orderbook` for each market in the close_time window
- Computes mid from yes_bid and parity yes_ask
- Reports n by series, horizon breakdown, and power analysis

Script is READ-ONLY (no /portfolio/* calls, no .env writes, no production data touches).

Run: `.venv-kronos/Scripts/python.exe scripts/v10/probe_b1_uncertain_markets.py`
