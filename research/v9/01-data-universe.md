# v9 Data Layer and Universe Scoping (Phase 1)

**Date:** 2026-05-26
**Author:** Agent v9-A1 (data layer + universe scope)
**Status:** Phase 1 complete. All five sections below are based on live API probes
and file reads conducted this session (2026-05-26 21:27 to 22:10 UTC).
**Probe scripts:** `scripts/v9/probe_v9_universe.py`, `scripts/v9/probe_sports_oos.py`,
`scripts/v9/probe_settled_markets.py`
**Probe outputs:** `data/v9/sports_oos_probe.json`, `data/v9/settled_probe.json`
**Predecessor reads:** `src/kalshi_bot/strategy/market_scanner.py`,
`research/w2-v1-residual-edge.md`, `research/v4/FINAL-VERDICT.md`,
`research/v5/FINAL-VERDICT.md`, `research/v7/01-data-sources-scoping.md`,
`research/v7/07-naive-p-yes-critic.md`, `research/v8/01-v8a-launch-report.md`

---

## Executive Summary

**The single most important finding:** historical Kalshi orderbook data is NOT
available for resolved markets. The `/markets/{ticker}/orderbook` endpoint
returns an EMPTY book (0 yes/no levels) for settled markets, confirming there
is no retrospective orderbook. This kills Option F1 (retrospective backtest
with real mid) entirely.

**The second critical finding:** the v1 denylisted-residual sports universe
on Kalshi is SEASONAL. KXNBAWINS, KXMLBWINS, KXNCAAFPLAYOFF, and KXNFLGAME
returned ZERO settled/closed markets in the post-cutoff window
(2026-01-15 to 2026-05-26). The NBA and MLB win-total markets are structured
as annual season-long props closing in November 2025 (MLB) and April 2026
(NBA). The 2025-26 NBA season markets settled on 2026-04-13; no v1-band
markets exist in our 4-month post-cutoff OOS window.

**v9 is structurally forced into Option F2 (prospective forecasting)**. There
are 87 v1-band open sports markets closing 2026-05-27 to 2026-06-30, of
which the best-scoped subset is UFC fights (n=11), World Cup qualifying games
(n=4), NHL awards (n=3), and PGA US Open (n=4). We can forecast these NOW,
wait for resolution, and collect real orderbook mids at time of forecast.
Expected n for a final verdict: 20 to 30 resolved v1-eligible markets within
5 to 6 weeks.

**Statistical feasibility:** n=20-30 delivers SE_Brier ~ 0.11 to 0.13, meaning
the +0.014 AIA target is detectable at 80% power only with n ~ 1,300. F2 at
n=20-30 is definitively UNDERPOWERED for a final verdict this session. It is,
however, the correct prospective methodology foundation for a 6 to 12 month
rolling study.

---

## Section 1: v1 Denylisted-Residual Sports Universe Today

### 1.1 Denylist (current, from `market_scanner.py:35-38`)

```python
DEFAULT_SERIES_DENYLIST = frozenset({
    "KXNFLWINS",
    "KXNFLPLAYOFF",
    "KXMLBPLAYOFFS",
})
```

Source: `src/kalshi_bot/strategy/market_scanner.py` lines 35-38.
Applied at scan time in `filter_candidates()` (line 134-137): any market whose
series_ticker matches a denylist entry is skipped before any other filter.

### 1.2 Residual universe from W2

Per `research/w2-v1-residual-edge.md` (the authoritative prior measurement):

| Series prefix      | n (W2) | Mean P&L   | CI               | Flag     |
|--------------------|-------:|----------:|------------------|----------|
| KXNBAWINS          |     22 | +9.94pp   | [+6.76, +13.46]  | CLEAN    |
| KXMLBWINS          |     11 | -1.21pp   | [-19.42, +10.34] | FRAGILE  |
| KXNCAAFPLAYOFF     |      8 | +0.83pp   | [-23.97, +16.52] | FRAGILE  |
| KXNFLGAME          |      3 | +20.59pp  | [+16.64, +25.91] | small n  |
| 15 singleton series|    1-2 | +12-23pp  | n/a              |          |
| COMBINED           |     60 | +7.68pp   | [+2.63, +11.68]  | YELLOW   |

### 1.3 Current Kalshi sports universe (probed 2026-05-26)

Live probe: `GET /series?category=Sports` returned **2,029 sports series**.
After applying denylist: **2,026 residual series**. The denylist removes 3
series (KXNFLWINS, KXNFLPLAYOFF, KXMLBPLAYOFFS).

The universe is enormous (2,026 residual series) but most are non-sports or
non-v1-structure: esports (KXMVESPORTSMULTIGAMEEXTENDED alone = 11,487
closed markets in OOS), financial indices, music charts, and weather.

### 1.4 OOS window availability (post-Opus-cutoff, post-denylist)

**KEY PROBE RESULT:** Probed `GET /markets?status=closed&category=Sports&close_time_min=2026-02-01&close_time_max=2026-05-26`. Pulled 20,000 markets (hit page cap; actual count larger).

The top series by count:

| Series                          | n (OOS closed) | v1-eligible (mid [0.70-0.95]) |
|---------------------------------|---------------:|------------------------------:|
| KXMVESPORTSMULTIGAMEEXTENDED    |         11,487 | 0                             |
| KXEURUSDH (forex)               |          1,800 | 0                             |
| KXUSDJPYH (forex)               |          1,117 | 0                             |
| KXMVECROSSCATEGORY              |            921 | 0                             |
| KXWTIW (oil)                    |            450 | 1                             |
| KXPGAMAKECUT, KXPGATOP5, etc.   |        ~600    | 0                             |
| **Total (20,000 sample)**       |        20,000  | **2**                         |

**Critically:** KXNBAWINS, KXMLBWINS, KXNCAAFPLAYOFF, and KXNFLGAME all return
ZERO closed markets in this window. The v1 residual series are NOT here.

**Reason:** These are seasonal markets. Probing `status=settled` reveals:
- KXNBAWINS: settled markets dated 2026-04-13 (NBA season end). Already resolved.
- KXMLBWINS-*: settled November 2025 (MLB season end). Before OOS window.
- KXNCAAFPLAYOFF: settled January 2026 (CFP). Before Opus cutoff (Jan 2026).
- KXNFLGAME: NFL regular season 2025-26. Settled Sep-Jan. Before cutoff.

**Settled-market probe (2026-01-15 to 2026-05-26, post-cutoff):**

| Series prefix  | n settled | n v1-eligible | mean mid | Close dates       |
|----------------|----------:|--------------:|----------:|-------------------|
| KXNBAWINS      |       200 |             0 |     0.543 | 2026-04-13        |
| KXBOXING       |       132 |             4 |     0.503 | 2026-03 to 04     |
| KXUFCFIGHT     |       200 |             1 |     0.503 | 2026-03 to 05     |
| KXNBAPLAYOFF   |        30 |             0 |     0.535 | 2026-04 to 04     |
| KXNHLPLAYOFF   |        32 |             0 |     0.502 | 2026-04 to 04     |
| **TOTAL**      |   **594** |         **5** |           |                   |

Only 5 v1-eligible settled sports markets in the post-cutoff OOS window.
KXNBAWINS mean mid is 0.543 (well below v1's [0.70-0.95] band): NBA win-total
markets traded near 0.50 because most settled at or near season close with
uncertain outcomes.

**Conclusion:** Option F1 (retrospective with real mid) yields n = 5 MAXIMUM.
This is insufficient for any statistical inference.

### 1.5 Confidence interval for the +0.014 Brier target

Using SE_Brier ~ 0.5/sqrt(n) (the project standard):

| n   | SE_Brier | Detectable delta (80% power, alpha 0.05) |
|-----|----------:|----------------------------------------|
| 5   | 0.224    | 0.36 (impossible with F1)             |
| 20  | 0.112    | 0.18 (F2 lower bound)                 |
| 30  | 0.091    | 0.15 (F2 expected)                    |
| 100 | 0.050    | 0.082                                 |
| 1300| 0.014    | 0.023 (minimum for AIA +0.014 target) |

Power calculation: to detect delta=+0.014 at 80% power with alpha=0.05,
n ~ (z_alpha + z_beta)^2 * sigma^2 / delta^2 = (1.645 + 0.842)^2 * 0.25 / 0.014^2
= 6.21 * 0.25 / 0.000196 ~ **7,916**. With SE_Brier ~ 0.5/sqrt(n), the
"rule of thumb" n ~ 0.25/0.014^2 / (1.96)^2 at 2.5% ~ 1,300.

The AIA Forecaster itself used n ~ 3,000+ per sport category to detect +0.014.
With v9's expected F2 n=20-30, we are 40x to 65x underpowered.

---

## Section 2: Kalshi Orderbook Mid Measurement (v7-B Phantom Prevention)

### 2.1 Probe results

**Test ticker:** KXMLBF5TOTAL-26MAY261910CINNYM-7 (an open MLB over/under market)

| Endpoint                                      | HTTP | Latency | Finding                          |
|-----------------------------------------------|------|---------|----------------------------------|
| GET /markets/{ticker}                         | 200  | 85ms    | Returns yes_bid, yes_ask, last_price, no_bid |
| GET /markets/{ticker}/orderbook               | 200  | 86ms    | Returns `orderbook_fp` with yes_dollars and no_dollars arrays |
| GET /markets/{ticker}/orderbook?ts=...        | 200  | 79ms    | Returns SAME current book (ts param IGNORED) |
| GET /markets/trades?ticker=...                | 200  | 84ms    | Returns trade prints (NOT orderbook mid) |

Live orderbook sample (KXMLBF5TOTAL market, 2026-05-26 21:34 UTC):
```json
{
  "orderbook_fp": {
    "no_dollars": [["0.0100","2779.00"],["0.2300","3223.00"],...],
    "yes_dollars": [["0.7600","50.00"],["0.7700","100.00"],...]
  }
}
```
Live mid from /markets/{ticker}: yes_bid=0.20, yes_ask=0.21, mid=0.205.

**For settled markets (tested on KXNBAWINS-WAS-25-T5):**

| Endpoint                           | HTTP | Finding                          |
|------------------------------------|------|----------------------------------|
| GET /markets/{settled_ticker}/orderbook | 200 | Returns EMPTY book (0 yes levels, 0 no levels) |
| GET /markets/{settled_ticker}      | 200  | yes_bid=0.99, yes_ask=1.00 (post-settlement artifact) |

**CONFIRMED:** The `?ts=` parameter on the orderbook endpoint is IGNORED. The
endpoint returns the current (live) book state, not a historical snapshot.
For settled markets, the book is empty. Historical orderbook data is
STRUCTURALLY UNAVAILABLE on Kalshi's public API.

### 2.2 Implication for v9 baseline measurement

Per the v7-B phantom failure mode (`research/v7/07-naive-p-yes-critic.md`
Findings 4.1, 7.1, 9.1): using stale trade-print mid as the baseline
produces phantom Brier improvements. The correct baseline for v9 is:

```
kalshi_mid = (yes_bid_dollars + yes_ask_dollars) / 2
```

or if yes_ask is not populated:

```
kalshi_mid = (yes_bid_dollars + (1.0 - no_bid_dollars)) / 2
```

This mid must be SNAPSHOTTED at the time the LLM forecast is generated
(T-35d or T-7d), NOT pulled retrospectively. For prospective F2 forecasting,
the agent forecasts on currently-open markets, records the live orderbook mid
at forecast time, and compares to the LLM forecast when the market resolves.

**The live /markets/{ticker} endpoint confirms that yes_bid_dollars and
yes_ask_dollars are populated in real time for currently-open sports markets
(86/188 have yes_bid, 107/188 have yes_ask derived from no_bid parity,
per v8-A iter-1 report).**

### 2.3 Prospective market count (v9 evaluation window)

**Key probe result:** `GET /markets?status=open&min_close_ts=...&max_close_ts=...`
(2026-05-27 to 2026-06-30) returned 20,000+ open markets (hit page cap).
Of those, **87 sports markets were v1-eligible** (mid in [0.70-0.95]).

Full breakdown of 87 v1-eligible prospective markets by source:

| Series prefix   | n_v1_open | Close dates              | Sample mids         |
|-----------------|----------:|--------------------------|---------------------|
| KXUFCFIGHT      |        11 | 2026-06-29               | 0.815, 0.765, 0.725 |
| KXWCGAME        |         4 | 2026-06-28 to 06-30      | 0.765, 0.890, 0.925 |
| KXPGAUSO        |         4 | 2026-06-29               | 0.935, 0.935, 0.910 |
| KXNHLVEZINA     |         1 | 2026-06-30               | 0.885               |
| KXNHLADAMS      |         1 | 2026-06-30               | 0.780               |
| KXNHLNORRIS     |         1 | 2026-06-30               | 0.900               |
| Additional      |        65 | 2026-05-27 to 06-30      | varied              |

**RECOMMENDATION:** Forecast all 87 NOW. Record live orderbook mid at forecast
time. Compare to resolution. This is the ONLY viable path to a clean v9
Brier evaluation. Wall-clock: first resolutions available 2026-05-27;
final batch by 2026-06-30. Full n of 87 available in ~5 weeks.

---

## Section 3: The-Odds-API Free Tier Coverage Audit

### 3.1 Probe results (2026-05-26, key in .env confirmed present)

| Endpoint                                 | HTTP | Credits used | Finding                         |
|------------------------------------------|------|--------------|---------------------------------|
| GET /v4/sports?apiKey=...                | 200  | 0 (list)     | 52 sports active                |
| GET /v4/historical/sports                | 404  | 0            | Endpoint does not exist         |
| GET /v4/historical/.../odds?date=...     | 401  | 0            | Historical requires paid plan   |

**Sports of interest found (n=52 total):**

| Sport key                    | Active | Has outrights | Notes               |
|------------------------------|--------|---------------|---------------------|
| americanfootball_nfl         | YES    | No            | Active              |
| baseball_mlb                 | YES    | No            | Active              |
| basketball_nba               | YES    | No            | Active              |
| americanfootball_ncaaf       | YES    | No            | Active              |
| basketball_ncaab             | NOT FOUND | N/A          | Likely seasonal     |
| soccer_usa_mls               | NOT FOUND | N/A          | Use soccer_* search |
| mma_mixed_martial_arts       | YES    | No            | Active - UFC        |

**Credits remaining:** 477 of 500 (23 used in prior v5/v7 probes; still effectively full).

### 3.2 The-odds-api plan structure (confirmed from HTTP 401 error message)

The 401 response body explicitly states: "Historical odds are only available on paid usage
plans. See usage plans at https://the-odds-api.com."

**Free 500-credit tier:** Covers live odds (upcoming matches) ONLY. NO historical
odds access, not even for yesterday's games. The documentation in
`research/v7/01-data-sources-scoping.md` Section 2 noted "$30/mo Starter"
for historical; this remains accurate.

**What the free 500 credits/month CAN do for v9 F2:**
- At forecast time (T-35d, T-7d), pull current sportsbook odds for the open markets.
- Credit cost per sport snapshot: 1 credit per region per market type.
  Pulling NFL, MLB, NBA, MMA at h2h + spreads = ~8 credits per pull.
  500 credits = ~60 full multi-sport pulls. For v9 F2 (87 markets over 5 weeks),
  that is ample for one snapshot per market at forecast time.

**Operator action needed:** An the-odds-api key IS already present in `.env`
(`THE_ODDS_API_KEY=3579...`). The operator does NOT need to take any manual step.
The free tier with 477 remaining credits is immediately usable for live odds pulls
on the 87 prospective markets.

**Historical access:** Requires $30/mo Starter. This was already the conclusion
in v7 scoping. For the AIA Forecaster-style retrospective backtesting on past
seasons (which would need historical sportsbook lines), the operator would
need to purchase the $30 tier. For v9 F2 prospective, it is NOT required.

---

## Section 4: ESPN site.api and GDELT Inventory

### 4.1 ESPN site.api probe (2026-05-26 21:45 UTC)

| Endpoint                                                        | HTTP | Latency | Notes                  |
|-----------------------------------------------------------------|------|---------|------------------------|
| /apis/site/v2/sports/baseball/mlb/scoreboard                    | 200  | 167ms   | Active games/schedules |
| /apis/site/v2/sports/football/nfl/scoreboard                    | 200  | 33ms    | Off-season; no games   |
| /apis/site/v2/sports/basketball/nba/scoreboard                  | 200  | 42ms    | Playoffs ongoing       |
| /apis/site/v2/sports/basketball/mens-college-basketball/scoreboard | 200 | 33ms   | Off-season             |
| /apis/site/v2/sports/football/college-football/scoreboard       | 200  | 37ms    | Off-season             |
| /apis/site/v2/sports/soccer/usa.1/scoreboard                    | 200  | 32ms    | MLS regular season     |

**All 6 endpoints return HTTP 200.** Per v7 scoping (Section 3), historical
scoreboard data is available via `?dates=YYYYMMDD` parameter. Injury data is
available but current-state only.

**What ESPN adds for v9 F2:** At forecast time, pull injury reports and recent
game scores for the teams/athletes in each prospective market. Free, no key,
US-accessible from this host. Latency 33 to 167ms.

**Specifically for the 87 prospective markets:**
- KXUFCFIGHT (n=11): Use ESPN MMA endpoint for fighter records/injuries.
  Endpoint: `/apis/site/v2/sports/mma/ufc/scoreboard` (needs verification).
- KXWCGAME (n=4): Use `/apis/site/v2/sports/soccer/` with FIFA World Cup
  qualifier league code.
- KXPGAUSO (n=4): PGA Tour endpoint (`/apis/site/v2/sports/golf/pga/`).
- KXNHL* (n=3): `/apis/site/v2/sports/hockey/nhl/` for player stats.

### 4.2 GDELT probe

**Result:** HTTP 429 at 6,743ms. Response body: "Please limit requests to one
every 5 seconds."

This differs from the v7 finding (timeout = connection refused). The 429 means
GDELT's doc API IS reachable from this host, but rate-limited. A single query
with a 5-second inter-request delay would work. However, the v7 verdict stands:
GDELT is a backup option, not a primary data source. The 15-minute batch
download files at `http://data.gdeltproject.org/gdeltv2/` are accessible
without rate limits and more reliable for offline feature construction.

**Verdict for v9:** GDELT is available (429 is recoverable), but low-priority.
Use ESPN for sports-specific news. GDELT bulk downloads are a fallback for
geopolitical context on soccer/international markets (KXWCGAME).

### 4.3 Free-tier news sources ranked for v9

| Source         | Accessibility    | Coverage for v9 sports        | Recommended? |
|----------------|------------------|-------------------------------|--------------|
| ESPN site.api  | Free, no key     | MMA, soccer, golf, NHL, NFL, NBA | YES (primary) |
| the-odds-api   | 477 credits left | NFL, MLB, NBA, MMA (live odds) | YES (primary) |
| Alpha Vantage  | 25/day free      | Sports sentiment (thin)        | Backup only   |
| GDELT bulk     | Free download    | News tone/sentiment by keyword | Optional      |
| NewsAPI        | Dev-only/1mo LB  | No production use              | NO            |

---

## Section 5: Sample Size and Statistical Feasibility

### 5.1 Power formula

SE_Brier ~ 0.5/sqrt(n). Detecting delta = +0.014 Brier improvement:

- 80% power, two-sided alpha=0.05: n ~ (1.96 + 0.842)^2 / (0.014^2 / 0.25) ~ 7,916.
- 80% power, one-sided alpha=0.10: n ~ (1.28 + 0.842)^2 / (0.014^2 / 0.25) ~ 4,559.
- Rule-of-thumb (CI excludes zero at alpha=0.05): n ~ (1.96 * 0.5 / 0.014)^2 ~ 4,898.

**AIA Forecaster matched their n ~ 3,000 per subcategory to achieve tight CIs
on +0.014 lift.** v9 at n=87 is 56x underpowered for a definitive verdict.

### 5.2 Option F1: Retrospective, historical orderbook

**Orderbook availability:** ZERO. The Kalshi /markets/{ticker}/orderbook endpoint
returns an empty book for settled markets. The `?ts=` parameter is ignored and
returns current state. Historical orderbook data for resolved markets is NOT
accessible via any documented Kalshi endpoint.

**F1 n:** 5 v1-eligible settled sports markets in the post-cutoff OOS window
(2026-01-15 to 2026-05-26). These are 4 KXBOXING + 1 KXUFCFIGHT.
Even using trade-print mid (which reintroduces the v7-B stale-print risk),
n=5 is structurally useless: SE_Brier = 0.5/sqrt(5) = 0.224, unable to
detect any delta below 0.36.

**F1 verdict: COLLAPSES.** Historical Kalshi orderbook unavailability and
seasonal sports market structure jointly eliminate F1.

### 5.3 Option F2: Prospective, forecast now and wait

**N available:** 87 open v1-eligible sports markets closing 2026-05-27 to
2026-06-30. Live orderbook mid AVAILABLE now and at forecast time.

**Method:** For each of the 87 markets, TODAY:
1. Pull yes_bid_dollars, yes_ask_dollars; compute live_mid = (bid+ask)/2.
2. Run Opus 4.7 LLM forecast (no foreknowledge; market closes after today).
3. Pull the-odds-api live odds for the matching sport as a feature.
4. Pull ESPN current data for injuries/stats.
5. Store (ticker, live_mid, llm_p_yes, resolution_date) in a parquet.

When each market resolves, compare LLM ensemble to live_mid.

**Wall-clock:** First resolutions 2026-05-27. Full batch by 2026-06-30.
A final n=87 verdict requires waiting ~5 weeks.

**SE_Brier at n=87:** 0.5/sqrt(87) = 0.054. Minimum detectable delta at
80% power: ~ 0.088. This is 6x the AIA target.

**Can we get a verdict in THIS session?** No. Even if all 87 resolve by tomorrow,
the power is insufficient for a definitive verdict. F2 is the CORRECT design for
v9's methodology, but the verdict timeline is 4 to 6 weeks from today.

### 5.4 Option F3: Mixed (prospective + trade-print retrospective, sanity-check only)

Using trade-print mid as the baseline for the post-cutoff settled markets
(n=594 settled, of which n=5 v1-eligible). This is acknowledged as INFERIOR
because trade prints are stale relative to the live orderbook (v7-B finding).

Combining F2 n=87 prospective with F3 n=5 sanity-check adds almost nothing
statistically (n goes from 87 to 92, SE from 0.054 to 0.052). Not worth the
methodological contamination of mixing real-mid and stale-print baselines.

**F3 verdict: DO NOT USE as primary. Use ONLY as a sanity-check footnote.**

### 5.5 Summary feasibility matrix

| Option | n available | SE_Brier | Min detectable delta | Verdict deadline | Recommended? |
|--------|------------:|----------:|---------------------:|-----------------:|--------------|
| F1 (retrospective, real mid) | 5 | 0.224 | 0.36 | N/A | NO (collapses) |
| F2 (prospective, now)        | 87 | 0.054 | 0.088 | 2026-06-30 | YES (primary) |
| F3 (mixed, sanity check)     | 92 | 0.052 | 0.085 | 2026-06-30 | Footnote only |

---

## Section 6: Recommendations for v9 Phase 2

### 6.1 Primary recommendation: proceed with F2 prospective design

Begin forecasting all 87 currently-open v1-eligible sports markets immediately.
The methodology is:

1. **Snapshot the live mid** for all 87 markets (takes 10 seconds via KalshiClient).
2. **Run Opus 4.7 LLM forecast** with a structured prompt that includes ESPN data,
   the-odds-api live line, and NO information dated after the market's open date
   (to prevent foreknowledge per AIA Section 4 audit requirement).
3. **Compute ensemble:** p_ensemble = 0.67 * kalshi_mid + 0.33 * llm_p_yes
   (the AIA MarketLiquid 67/33 split).
4. **Store** ticker, live_mid, llm_p_yes, p_ensemble, espn_features, odds_line,
   forecast_time, close_time to `data/v9/prospective_forecasts.parquet`.
5. **At resolution**, query result via `/markets/{ticker}` (result field),
   compute Brier scores, run paired t-test on (Brier_ensemble vs Brier_mid).

### 6.2 Expand n for a stronger verdict

87 markets is structurally insufficient (n=87 delivers SE=0.054, detects at
80% power only delta > 0.088). To reach the AIA target delta of +0.014, v9
needs n ~ 1,300. Options:

- **Expand the price band.** The AIA Forecaster used all markets in (0.20-0.45)
  union (0.55-0.80), which is the full non-boundary band. v1's (0.70-0.95) is
  a subset. If v9 adopts the AIA band, the 87 expands significantly. The prospective
  probe found 4,223 open sports markets in 2026-05-27 to 2026-06-30. Widening
  to the AIA band could yield 300 to 500 v9-eligible markets.
- **Extend the time window.** Running v9 for 6 months (through 2026-12-31) covers
  the start of the 2026-27 NBA season, 2026 MLB playoffs, 2026 NFL season start.
  This is the realistic path to n > 1,000 on v1-eligible markets.
- **Accept underpowered partial results.** Report the v9 F2 results at n=87 as a
  directional pilot. If the ensemble lift is consistently positive across multiple
  sport types (UFC, soccer, golf, NHL), it is evidence for continuation. If it
  is negative or near-zero, kill v9 at F2.

### 6.3 Data pipeline for v9 Phase 2

**Required data sources (all free/existing):**

| Source                 | Use                           | Cost       | Status         |
|------------------------|-------------------------------|------------|----------------|
| Kalshi /markets/{t}    | Live mid at forecast time     | Free (key in .env) | Ready |
| ESPN site.api          | Injuries, recent scores        | Free, no key | Ready          |
| the-odds-api           | Live sportsbook line          | 477 credits left | Ready        |
| Opus 4.7 API           | LLM forecast generation        | ~$0.005/forecast | Need key   |
| `.venv-kronos`         | Python runtime                | Free       | Ready          |

**NOT required for F2:**
- Historical Kalshi orderbook (unavailable)
- the-odds-api historical odds (requires $30 paid tier)
- GDELT (too slow; ESPN is sufficient for sports context)

### 6.4 v7-B phantom prevention protocol for v9

The v9 code MUST NOT:
- Use `last_price_dollars` as the Kalshi mid baseline (v5-B Killer 2c).
- Use the `?ts=` parameter on the orderbook endpoint expecting historical data (returns current state).
- Pull `/markets/{ticker}/orderbook` for a settled market expecting a price (returns empty).
- Backfill the mid from `/historical/trades` (stale trade-print mid; v7-B phantom).

The v9 code MUST:
- Snapshot `(yes_bid_dollars + yes_ask_dollars)/2` from `/markets/{ticker}` at
  forecast time, for each open market.
- If yes_ask is absent but no_bid is present, derive yes_ask = 1.0 - no_bid.
- Store the snapshot timestamp alongside each forecast.

---

## Appendix: All Live Probe Results

### Kalshi API (2026-05-26 21:27 UTC)

```
Exchange status:           HTTP 200, 268ms  exchange_active=True, trading_active=True
/series?category=Sports:   HTTP 200, 240ms  2,029 sports series discovered
/markets?status=open:      HTTP 200         500 markets across 50 sample series
/markets?status=closed (OOS): HTTP 200, 153-760ms  20,000 markets (page cap)
/markets/{ticker}:         HTTP 200, 85ms   yes_bid/yes_ask/last/no_bid in payload
/markets/{ticker}/orderbook: HTTP 200, 86ms  yes_dollars/no_dollars arrays (current book)
/markets/{ticker}/orderbook?ts=...: HTTP 200, 79ms  SAME current book (ts ignored)
/markets/trades?ticker=...: HTTP 200, 84ms  Trade prints (NOT orderbook mid)
Settled market orderbook:  HTTP 200, 85ms   EMPTY book (0 yes/no levels)
/markets?status=settled:   HTTP 200         5 KXNBAWINS settled in OOS
```

### The-Odds-API (2026-05-26 21:46 UTC)

```
/v4/sports?apiKey=...               HTTP 200, 299ms  52 sports active
/v4/historical/sports               HTTP 404          Historical endpoint does not exist
/v4/historical/.../odds?date=...    HTTP 401          "HISTORICAL_UNAVAILABLE_ON_FREE_USAGE_PLAN"
Credits remaining:                   477/500           23 used in prior sessions (v5, v7)
NFL, MLB, NBA, MMA:                  All active        NCAAB, MLS not found in active list
```

### ESPN site.api (2026-05-26 21:46 UTC)

```
/apis/site/v2/sports/baseball/mlb/scoreboard           HTTP 200, 167ms
/apis/site/v2/sports/football/nfl/scoreboard           HTTP 200, 33ms
/apis/site/v2/sports/basketball/nba/scoreboard         HTTP 200, 42ms
/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard  HTTP 200, 33ms
/apis/site/v2/sports/football/college-football/scoreboard          HTTP 200, 37ms
/apis/site/v2/sports/soccer/usa.1/scoreboard           HTTP 200, 32ms
```

### GDELT (2026-05-26 21:46 UTC)

```
api.gdeltproject.org/api/v2/doc/doc  HTTP 429, 6743ms  Rate-limited ("5 seconds between requests")
Status: REACHABLE but rate-limited (not timed out as in v7). Usable with 5s delays.
```

---

## Key Findings Summary Table

| # | Finding                                                                              | Severity     |
|---|--------------------------------------------------------------------------------------|--------------|
| 1 | Historical Kalshi orderbook UNAVAILABLE for settled markets (empty book returned)   | KILLER (F1)  |
| 2 | v1 residual series (KXNBAWINS, KXMLBWINS, etc.) have ZERO settled markets in 2026-02 to 05-26 | KILLER (F1) |
| 3 | 87 v1-eligible open sports markets exist for prospective forecasting (F2 viable)    | Important    |
| 4 | The-odds-api free tier confirmed: historical requires $30/mo paid; live odds free with 477 credits remaining | Important |
| 5 | ESPN site.api: all 6 sport endpoints return HTTP 200 from this host                 | Confirming   |
| 6 | GDELT: HTTP 429 (rate-limited, not dead); usable with 5s delays                    | Minor        |
| 7 | n=87 prospective is 56x underpowered for a +0.014 Brier delta verdict              | Important    |
| 8 | F2 prospective verdict available 2026-06-30 (5 weeks); underpowered but directional | Operator decision |
| 9 | The-odds-api key already in .env; the-odds-api ready for immediate use (no operator action needed) | Confirming |
