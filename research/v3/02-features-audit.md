# V3 External Features Audit

**Agent:** V3-B
**Date:** 2026-05-24
**Mandate:** Catalog external (non-Kalshi-price) features that could plausibly improve calibration of long-horizon sports market outcomes beyond what v1's price feature alone captures. The model's edge has to come from something other than the Kalshi market price itself; otherwise it collapses to v1's heuristic.

## TL;DR

I probed nine candidate feature sources live and recorded raw responses to `data/v3/feature_probe_*.json`. Key findings:

- **MLB Stats API is gold for v3 baseball features.** Supports AS-OF-DATE queries (`standings?date=2025-08-20`), team `byDateRange` stat windows, schedule, rosters, and injuries with explicit date parameters. No auth, no key, no rate limit warnings hit in my probe. Effort 1.
- **Polymarket history endpoint has a hard 30-day ceiling.** `clob.polymarket.com/prices-history` returns 400 for any window > ~30 days. This blocks training on Polymarket as a feature unless we either (a) build a 30-day rolling fetcher and accumulate over time, or (b) accept that historical Polymarket data is essentially unavailable for events that closed > 30 days ago. **This is the single most important finding for the v3 thesis.**
- **Polymarket order book is current-only.** No historical depth via free API.
- **538 / FiveThirtyEight is dead.** Direct URLs at `projects.fivethirtyeight.com/*` redirect to `abcnews.com/politics` (Disney shut down the property in 2025). The `github.com/fivethirtyeight/data` repo is a frozen archive. NFL ELO has a Wayback snapshot from 2023-04-27. NBA ELO has none. **538 ELO is a one-shot frozen feature, not a live updater.**
- **the-odds-api free tier requires a key.** Every endpoint returns 401 without auth. Operator signup not confirmed; effort to integrate is +1 step.
- **ESPN injuries endpoint is current snapshot only**, no AS-OF support. Useful for forward sampling, useless for historical OOS training.
- **Reddit JSON API is alive, throttled by IP. Time filtering is coarse (`t=week`, `t=year`, no arbitrary date).** Counts can only be assembled by paginating posts and binning client-side.
- **GDELT Doc API supports arbitrary `startdatetime`/`enddatetime` (back to 2017).** Free, no key. Genuine AS-OF support. Slow (12s in my probe).
- **nflverse parquet releases work, downloadable, season-aggregated.** Good for NFL team stats.
- **Open-Meteo historical archive works, free, full hourly data back to 1940.** Genuine AS-OF.

Coverage rate for v1's long-horizon sports universe (KXMLBWINS, KXNFLWINS, KXNBAWINS, etc.) is bounded by **how many of those tickers have a matching Polymarket event**. v2 research found that's the hard ceiling on the Polymarket-as-feature thesis (60% naive false-positive rate). For all the *non-market-data* features (team stats, weather, news), coverage is roughly the union of leagues each source covers (MLB Stats API: MLB only; nflverse: NFL only; etc).

Detailed audit follows.

## Category 1: Team Performance Baselines

### 1.1 MLB Stats API (verified)

**What it is:** Official MLB data API, public no-auth. Covers all MLB games 1901+. Per-team and per-player stats, standings, schedule, rosters, splits.

**Hypothesis under test:** A team's true win probability deviates from its market-implied probability when its Pythagorean expected win pct (`exp_w_pct = (R^1.83) / (R^1.83 + RA^1.83)`) materially diverges from its actual win pct, indicating mean reversion or persistence to come.

**URL pattern (probed):**
```
GET https://statsapi.mlb.com/api/v1/standings
    ?leagueId=103,104&season=2025&date=2025-08-20
    &standingsTypes=regularSeason
```
Response (probed status 200, 148ms): `records` list of league/division standings with `teamRecords[].leagueRecord.{wins,losses,pct}`, splits (home/away, day/night, vs LHP/RHP, lastTen), gamesBack, runs scored/allowed (via `byDateRange`).

For per-team stat windows:
```
GET https://statsapi.mlb.com/api/v1/teams/{teamId}/stats
    ?season=2025&stats=byDateRange
    &startDate=2025-04-01&endDate=2025-08-20
    &group=hitting,pitching
```
Returns runs/RA, OPS, ERA, WHIP, etc. for the window, which is exactly what we need for AS-OF T-35d sampling.

**History depth:** Effectively unlimited for our purposes. Statcast (pitch tracking) starts 2008; standings/win-loss data extends back to franchise origin. v3 needs 2022+ to overlap with Kalshi sports history; trivially available.

**Latency at T-35d sampling moment:** Genuine AS-OF support. Pass `date=YYYY-MM-DD` to standings; pass `startDate`/`endDate` to byDateRange. No reconstruction from event logs required.

**OOS-discipline rule:** For a Kalshi market with `close_time = 2025-09-25`, sample at T-35d = 2025-08-21. Issue these calls with `date=2025-08-20` and `endDate=2025-08-20` (one day before T-35d to be conservative against same-day game leakage; doubleheaders settled late-night). **Strict rule:** never pass a date >= the Kalshi T-35d sampling moment. The API is well-behaved and will faithfully return the state as of that date.

**Estimated effort:** 1 (trivial HTTP GET, JSON). v2 already has a working `build_mlb_dataset.py` that pulls schedule + games; the team-stat call adds 2-3 lines.

**Coverage rate over Kalshi sports markets:** MLB-only. Covers `KXMLBWINS`, `KXMLBALEAST`/`NLEAST`/etc., `KXMLBPLAYOFFS`, `KXMLBALMVP`, `KXMLBGAME`. v1's filled-orders log so far hits MLB heavily; per `phase-2-autonomous-log.md` Round 7, 39 of the 47 eligible >=70c long-horizon markets are MLB-related. So MLB Stats API populates ~80%+ of the v1-domain rows where the market is MLB-team-based.

**Orthogonality check candidate (for Phase 2):** Run a logistic regression of v2's outcome on `[favorite_price, pyth_win_pct_diff, run_diff_per_game]`. If `pyth_win_pct_diff` keeps a |coefficient| > 0.5 and its bootstrap CI excludes zero after partialling out `favorite_price`, the feature adds independent signal. Otherwise it's a noisy reflection of price (which is what v2 found at n=123).

### 1.2 nflverse releases (verified)

**What it is:** Community-maintained NFL data releases on GitHub (`nflverse/nflverse-data`). Weekly stats, schedules, play-by-play, ELO-style ratings, snap counts, depth charts. Distributed as parquet files per season.

**Hypothesis under test:** NFL team strength differential predicts NFL season-win-total contracts (KXNFLWINS-27DET-8 family) beyond what the Kalshi price reveals.

**URL pattern (probed):**
```
GET https://api.github.com/repos/nflverse/nflverse-data/releases
GET https://github.com/nflverse/nflverse-data/releases/download/stats_team/stats_team_week_2024.parquet
```
Probe: 20 releases returned including `stats_team`, `players`, `injuries`, `schedules`, `pbp`, `rosters`, `trades`. The 2024 parquet downloads cleanly (status 200, ~400ms, parquet body).

**History depth:** Releases go back to ~1999 for some series; 2010+ for advanced metrics. Plenty for v3.

**Latency at T-35d sampling moment:** Parquet releases are point-in-time SNAPSHOTS published periodically (often weekly). The `published_at` timestamp on a release is the only AS-OF stamp we have; we must pick the latest release whose `published_at < T-35d` to avoid leak. nflverse releases for `stats_team_week_YYYY` get updated weekly during the season, so a model training on 2024 should use the latest 2024 release ONLY for the season being predicted, with care to truncate by week. **This requires manual sampling discipline; the API doesn't do it for us.**

**OOS-discipline rule:** For Kalshi `close_time = 2026-01-05`, T-35d = 2025-12-01. Use `stats_team_week_2025.parquet` filtered to weeks where the game date is < 2025-12-01. Drop any row whose `gameday >= 2025-12-01`. Doable but requires per-row date filtering on the parquet, not just a different URL.

**Estimated effort:** 2 (HTTP GET + parquet read + date filter).

**Coverage rate:** NFL-only. Covers KXNFLWINS, KXNFLGAME, KXSUPERBOWL series. v1's filled-orders log includes NFL (`KXNFLWINS-27DET-8` is a Round 6 fill), so this hits a meaningful subset of v1's domain.

**Orthogonality check:** Similar pattern to MLB Stats API: regress holdout outcome on `[favorite_price, team_dvoa_diff, team_pyth_w_pct_diff]`, check if the team features add signal partialled out of price. v3-B1 (dataset construction) must build this before v3-B2 trains.

### 1.3 ESPN site API + core API (partial verified)

**What it is:** ESPN's undocumented but stable web APIs at `site.api.espn.com` (legacy v2) and `sports.core.api.espn.com` (newer v2). Covers all major US sports. Scoreboard, team pages, injuries, news, standings.

**Hypothesis under test:** ESPN's published team records and team metadata give us a quick all-sport coverage layer.

**URL patterns (probed):**
- `GET https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?dates=20240901` (status 200, 97ms, returns full Week 1 NFL games)
- `GET https://site.api.espn.com/apis/site/v2/sports/football/nfl/injuries` (status 200, returns current injuries by team)
- `GET https://sports.core.api.espn.com/v2/sports/football/leagues/nfl/seasons/2024/teams/28` (status 200, returns Washington Commanders 2024 record + venue)
- `GET https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/standings` returned `{"fullViewLink": ...}` only -- the public path is gated to a website redirect. **MLB standings via ESPN is not a usable feature; use MLB Stats API instead.**
- `GET https://sports.core.api.espn.com/v2/sports/football/leagues/nfl/seasons/2024/types/2/powerindex` returned 404. The FPI (Football Power Index) endpoint path I tried is wrong; could be `/types/2/groups/9/teams/{teamId}/powerindex/{statId}` or similar but I didn't enumerate.

**History depth:** Scoreboard date queries appear to support arbitrary YYYYMMDD back to at least 2014 per community documentation. Injuries endpoint is current-snapshot only (no `as_of` parameter; comments dated 2024-2026 appear in the response, so it's a rolling current view).

**Latency at T-35d sampling moment:** Scoreboard and team-history queries support AS-OF via `?dates=YYYYMMDD` or `/seasons/YYYY/teams/N`. Injuries endpoint does NOT. We can only use ESPN injuries as a real-time feature, not as a historical training feature.

**OOS-discipline rule:** For training, use `scoreboard?dates=YYYYMMDD` for games on or before T-35d. **Do not use the current injuries endpoint for training; only for live inference.** This makes ESPN injuries a "future feature" the model can't actually train on, which is a contamination risk we need to flag in dataset construction.

**Estimated effort:** 2 (multiple endpoint shapes, no schema doc, undocumented response format).

**Coverage rate:** Multi-sport (NFL, NBA, NHL, MLB, NCAAF, MLS, etc.). For v1's domain, coverage is broad: ~95% of v1's eligible markets are in leagues ESPN tracks. But the *practical* coverage of historical AS-OF data is limited to scoreboard + season-team endpoints; injuries are excluded.

**Recommendation:** Use ESPN ONLY for: (a) team-by-season record lookup, (b) historical scoreboard for cross-verification of MLB Stats API. Skip ESPN injuries for v3 (no AS-OF). Skip MLB endpoints; use MLB Stats API directly.

## Category 2: Player-Level Injury / Availability

### 2.1 ESPN injuries (NOT usable for training)

Per Category 1.3: snapshot-only. **Cannot use for historical OOS training.** Live inference only.

### 2.2 MLB Stats API roster + DL transactions (verified)

**What it is:** MLB Stats API has `/teams/{id}/roster?rosterType=active&date=YYYY-MM-DD` which returns the active roster as of a specific date. Players on the 10-day or 60-day IL are excluded from the active roster, so this is a proxy for "who's available."

**URL pattern (probed):**
```
GET https://statsapi.mlb.com/api/v1/teams/147/roster?rosterType=active&date=2025-08-20
```
Status 200, 87ms, returns 26-man active roster for the Yankees on the given date.

**History depth:** Same as MLB Stats API generally. Supports any past date.

**Latency at T-35d:** Native AS-OF.

**OOS-discipline rule:** Pass `date < T-35d`. Trivial.

**Effort:** 1.

**Coverage:** MLB-only. Same as Category 1.1.

**Feature ideas:** "Days since star player X went on IL" or "fraction of expected wins coming from currently-available players" require additional joins to player WAR. Engineering effort to make this work as a numeric feature: 3 (must aggregate per-team based on a player WAR table).

### 2.3 nflverse `injuries.parquet` (probed, exists)

Probe showed `injuries` as one of the 20 released datasets. Schema documented at nflverse repo: `team`, `gsis_id`, `position`, `report_status`, `practice_status`, `date_modified`. Weekly cadence. Can be filtered by `report_date < T-35d` for AS-OF discipline.

**Effort:** 2 (parquet + filter).
**Coverage:** NFL-only.

## Category 3: Betting-Market Consensus (the-odds-api)

### 3.1 the-odds-api free tier (probe failed without key)

**What it is:** Aggregates sportsbook odds across DraftKings, FanDuel, BetMGM, Caesars, Pinnacle, etc. Free tier = 500 req/mo, requires API key.

**URL pattern:**
```
GET https://api.the-odds-api.com/v4/sports/baseball_mlb/odds/?regions=us&markets=h2h
```
All probes returned 401 `{"error_code": "MISSING_KEY"}`.

**History depth (per docs, not probed):** `/v4/historical/sports/{sport}/odds?date=YYYY-MM-DDTHH:MM:SSZ`. Historical access is on PAID tier ($30/mo for 5,000 req/mo + historical). **The free tier does NOT include historical odds.**

**Latency at T-35d:** For LIVE inference, free tier works. For training, we need paid tier ($30/mo) or a workaround.

**OOS-discipline rule (for live inference only):** Read current odds at the moment we sample T-35d. Cannot be replayed historically without paid plan.

**Estimated effort:** 2 (HTTP GET + key management). But the "free" assumption breaks down for training data; either we collect prospectively (build a 6-month logger) or upgrade to paid.

**Coverage:** Excellent breadth -- all major US sports, all major US sportsbooks. If we had historical it would be the #1 feature for outcome prediction.

**Blocker flagged for orchestrator:** Operator signup status on the-odds-api is UNCONFIRMED. Without the key we get nothing. Even with a free key, we cannot get historical odds for training. **Path forward:** (a) operator signs up free, we build a prospective logger that collects odds every day from now forward; v3 training cannot use this without 6+ months of accumulated data; or (b) skip this feature for v3.

**Recommendation:** Skip for Phase 2 (dataset build). Document the prospective-logger path for a future v4 if v3 closes as null.

### 3.2 Free alternative: Pinnacle CSV mirrors (not probed, mentioned for completeness)

OddsPortal and SBR scrape historical closing lines back ~5 years. These are scrape targets (not APIs), JS-rendered, against robots.txt for some sites (Pro-Football-Reference returned 403 in v2's probe). Skip.

## Category 4: Polymarket Mid-Price + Price History (DEEP DIVE)

### 4.1 Endpoint catalog (verified)

| Service | Base URL | Auth | What we use it for |
|---|---|---|---|
| Gamma | `https://gamma-api.polymarket.com` | None | Discover events, search by free-text, list sports markets, lookup event by id |
| CLOB | `https://clob.polymarket.com` | None for reads | Order book, midpoint, spread, prices-history |
| Data | `https://data-api.polymarket.com` | None | Trades (with `market=` filter via condition_id) |

Probed status of each: 200. Latency 30 to 350ms. No rate-limit headers observed; v2's probe documented unwritten guidance to keep request rates polite (no formal ceiling).

### 4.2 Polymarket-specific deep dive

#### (a) Can we get historical price snapshots at arbitrary timestamps?

**Yes, but with a hard 30-day ceiling.** Probed `clob.polymarket.com/prices-history` with the NYY 2026 World Series token (`52854...984865`):

| Interval | n_points | Span | First point | Last point |
|---|---|---|---|---|
| `1m` | 719 | 29.99d | 2026-04-24 09:00Z | 2026-05-24 08:52Z |
| `1h` | 2 | 0.04d | 2026-05-24 08:00Z | 2026-05-24 08:52Z |
| `6h` | 7 | 0.24d | 2026-05-24 03:00Z | 2026-05-24 08:52Z |
| `1d` | 25 | 0.99d | 2026-05-23 09:00Z | 2026-05-24 08:52Z |
| `1w` | 169 | 6.99d | 2026-05-17 09:00Z | 2026-05-24 08:52Z |
| `max` | 719 | **29.99d** (NOT actually max!) | 2026-04-24 09:00Z | 2026-05-24 08:52Z |

Note the trap: `interval=max` returns only ~30 days of data despite the name. The `1h`/`6h`/`1d`/`1w` intervals work as documented but only return the most recent slice of that duration. `1m` gives full 1-minute resolution over the last 30 days.

I then tested AS-OF window queries with `startTs`/`endTs`:

| Query window | Status | n_points returned |
|---|---|---|
| T-35d to T-34d (windowed) | 200 | 8 points (history STARTING at T-35d through NOW; endTs ignored) |
| T-60d to T-59d (windowed) | 200 | 25 points |
| T-90d to T-89d (windowed) | 200 | 24 points |
| `startTs=now-90d, endTs=now` (90-day full pull) | **400** | n/a |
| `startTs=now-180d, endTs=now` | **400** | n/a |
| `startTs=now-365d, endTs=now` | **400** | n/a |

Decoding: the API accepts a `startTs` up to ~90d back (returns 200 with a small number of points starting at that ts), but it REJECTS any explicit window > 30d. When you pass an old `startTs`, the API returns history STARTING from that point, but it caps the total returned at 30d of data and the `endTs` parameter is ignored (it returns up to now). **Effectively the data depth available is 30 days for arbitrary recent windows and unknown for older starts.**

For first-point reach: `T-90d` start with `endTs=now` returns 24 points where `first_t = 2026-02-22, first_p = 0.07`. So we got Yankees WS data back to mid-February 2026, ~92 days back. That suggests the cap is closer to ~90 days for *very* old start timestamps, but the response is a thin sampling, NOT minute-level. **The 30-day rich-detail ceiling is real; older data is degraded.**

**Implication for v3:** If we sample Polymarket at Kalshi-T-35d for a Kalshi market closing on 2025-09-25, that means we want Polymarket price as of 2025-08-21. Polymarket would not let us go back to 2025-08-21 today (it's > 30 days ago AND > 90 days ago). The price history we want for a model TRAINED on 2024-2025 Kalshi markets is essentially **unavailable** from this endpoint.

**There are two workarounds:**

1. **Start logging Polymarket prices prospectively.** Build a daily fetcher that records the price-history-1m result for every Kalshi-mapped Polymarket market and stores it locally. After 60-90 days we accumulate enough history. **This requires a 60-90 day build delay; not Phase-2-compatible.**

2. **Live-only thesis.** Use Polymarket exclusively as a LIVE feature at the moment v3 makes a trade decision, not as a training feature. This means we cannot evaluate v3's gate on the historical Kalshi corpus; we have to walk-forward train on a small live-collected sample. **This collapses our training data to whatever we can accumulate live.**

Per the master plan H1/H2 hypotheses, both REQUIRE historical Polymarket. The H3 (statistical rule) hypothesis can be tested live with a paper-mode logger. Given the master plan's preference for kill-early on data-shape blockers, **the Polymarket-as-feature path may be a Phase 2 blocker** unless we accept option 2 (live-only with very short data).

#### (b) Walk through one concrete example end-to-end

**Goal:** Sample Polymarket price for the New York Yankees 2026 World Series market at T-35d before the Kalshi `KXMLBWINS-NYY-26-T90` market's close.

**Step 1: Map the Kalshi market to its Polymarket counterpart.**
- Kalshi: `KXMLBWINS-NYY-26-T90` ("Yankees over 90 wins in 2026 season"). Note: this is the V1 ROUND 6 LIVE TICKER, currently open.
- Polymarket: searching `gamma-api.polymarket.com/public-search?q=Yankees+90+wins+2026` -- I didn't find an exact match; Polymarket has `MLB World Series Champion 2026 / Will the New York Yankees win the 2026 World Series?` (event id 179312) which is conceptually different (championship vs win-total).
- **Match failure type:** Kalshi's KXMLBWINS uses a numeric threshold (8+/9+/10+ for NFL or 80+/85+/90+ for MLB), Polymarket lists championship win/no-win contracts but not season-win-total contracts. The Yankees example does not have a perfect Polymarket counterpart for win-totals; it would only match for "Will the Yankees win the World Series 2026?"
- Per `02-polymarket-arb-research.md` Section 3, naive match has 60% FP rate. This is a real engineering ceiling.

**Step 2 (assuming a match exists): Pull Polymarket token id.**
- Event 179312 markets list contains `NYY 2026 WS YES` with tokens `[52854...984865, 95543...272271]`. The first is YES, the second is NO.

**Step 3: Pull historical price at T-35d.**
- T-35d for a Kalshi market closing 2026-09-25 is 2026-08-21.
- Today is 2026-05-24. 2026-08-21 is in the future; we cannot have sampled it yet. **Probe with a past T-35d:**
- T-35d for a market that closed 2026-04-30 would be 2026-03-26 (today: 2026-05-24, that's 59 days ago).
- Try: `GET https://clob.polymarket.com/prices-history?market=52854...984865&startTs=1774343000&endTs=1774429400&fidelity=60`. Status 200, returned a thin scatter of 25 points spanning from T-60d to now.
- **The point at 2026-03-26 is recoverable for this market.** First valid price-point near T-35d for the NYY WS market would be a single best-effort interpolation: the API returns points clustered around the queried `startTs` (8 points in the T-35d window in my probe).

**Step 4: Match Polymarket sampling time to Kalshi market lifetime.** Polymarket sport-event markets often have a different lifetime than Kalshi's. Polymarket NYY-2026-WS opened 2026-01-21, ends 2026-10-31. Kalshi `KXMLBWINS-NYY-26-T90` opened earlier (post-2025-WS) and closes 2026-10-04 (end-of-MLB regular season). T-35d for Kalshi closes at different points along Polymarket's own lifetime. We need to flag any Kalshi market where T-35d is BEFORE Polymarket's `startDate` (Polymarket data doesn't exist yet) and drop those rows.

**Step 5: Net.** End-to-end the call costs ~300ms wall-clock per market. For 100 matched markets in a training set, ~30s total. Live latency is acceptable.

#### (c) Polymarket order book depth: historical or current?

**Current only.** Probed `clob.polymarket.com/book?token_id=...`: returns immediately with `{bids, asks, market, asset_id, timestamp, hash, ...}`. No `as_of` parameter, no `startTs`. Order books are not historicized in the free API.

I extracted top-5 bid/ask for the Yankees WS YES at probe time:

| Side | Price | Size |
|---|---|---|
| ask 5 | 0.18 | 40 |
| ask 4 | 0.17 | 10 |
| ask 3 | 0.16 | 2440 |
| ask 2 | 0.15 | 4991 |
| ask 1 | 0.14 | 9369 |
| bid 1 | 0.13 | 629 |
| bid 2 | 0.12 | 20430 |
| bid 3 | 0.11 | 1456 |
| bid 4 | 0.10 | 1500 |
| bid 5 | 0.09 | 550 |

Spread = 0.01 (one tick), depth healthy. But this is one snapshot at probe time; we have no way to retrieve the book at T-35d in the past.

**Implication:** Order-book-derived features (bid-ask spread, imbalance, depth-weighted mid) **cannot be features for historical OOS training**. They can be features only for live inference, joined to a model trained on price-history-only data. That's a feature poverty case for v3's primary thesis.

**One indirect proxy:** The CLOB exposes `/spread?token_id=...`, which probed to `{"spread": "0.01"}`. It's a single number (current bid/ask gap). Not historicized either.

#### (d) Settlement-divergence flag

Per `02-polymarket-arb-research.md` Section 4: documented divergence cases:
- **Cardi B Super Bowl 2025**: Kalshi invoked rule 6.3(c) ambiguity, settled at last-traded ($0.26 YES). Polymarket settled YES at $1.00.
- **Khamenei ouster Feb 2026**: Polymarket resolved YES, paid $529M. Kalshi halted and settled at pre-death price.

Both are non-sports edge cases involving (a) novel resolution sources, (b) ambiguity, (c) external interruption. Sports markets are far less prone to these; the resolution sources (MLB, NFL official standings) are unambiguous and consistent across both platforms.

**Risk magnitude for v3 (sports-only domain):** Low but nonzero. Specific risk categories:
1. **Mid-season rule changes** (e.g., MLB playoff format change). Kalshi and Polymarket might handle a tie or wild-card adjustment differently.
2. **Cancellation / postponement** (rare but happens, e.g., COVID 2020). Both platforms have language saying "resolves based on official record at year-end"; in practice they've agreed on sports outcomes.
3. **Player eligibility / forfeit** (extremely rare for adult pro leagues).

**Mitigation for v3:**

a) **Drop any Kalshi market whose resolution language references a different source than its Polymarket counterpart.** Kalshi tickers reference `MLB.com` standings; Polymarket WS markets typically reference `MLB.com` too. If they diverge in language, flag and exclude.

b) **Drop any markets covering "ambiguous-prone" events** (Hall of Fame, MVP, Heisman, awards where the criteria are subjective). Sports outcomes that resolve by W/L are safe.

c) **If using Polymarket as a feature, the model should NOT mechanically copy the Polymarket price.** It should weight Polymarket by some posterior on "settlement agreement probability." Worst case, an event that fails the H2 model's prediction is just one bad bet. Documented in dataset metadata.

**Estimated impact on v3 if we ignore divergence risk:** Per V2 research, post-2024 there's no documented sports Kalshi/Polymarket divergence > 5c that wasn't an arbitrage opportunity that closed in seconds. The sports domain is largely safe; main risk is during championships or rule changes.

### 4.3 Polymarket summary table

| Property | Value |
|---|---|
| Auth | None (read-only) |
| Rate limit | Unpublished, polite use expected |
| History depth (free) | ~30 days rich detail, ~90 days degraded |
| AS-OF support | Partial (startTs works but with depth caps; endTs is buggy/ignored) |
| Order book history | None |
| Coverage of v1 sports universe | Depends on event-matching; v2 found 60% naive FP rate, lower with careful tag-and-date filtering |
| Effort to integrate | 3 (matching is the hard part; data fetch is trivial) |
| Recommendation | **Live-only feature. Cannot be used for historical OOS training without 60-90d prospective logging.** |

## Category 5: News / Sentiment Signal

### 5.1 Reddit JSON API (verified)

**What it is:** `reddit.com/r/{sub}/{type}.json` returns Reddit listings as JSON. No auth required (rate limited per IP). Stable enough that the community uses it widely.

**URL pattern (probed):**
- `GET https://www.reddit.com/r/baseball/new.json?limit=10` (status 200, 507ms)
- `GET https://www.reddit.com/r/baseball/search.json?q=Yankees&restrict_sr=on&limit=25&t=week&sort=new` (status 200, 534ms)
- `GET https://www.reddit.com/r/baseball/search.json?q=Dodgers&restrict_sr=on&limit=25&t=year&sort=new` (status 200)

**Hypothesis under test:** A surge in posts mentioning a team in a fixed window before T-35d correlates with disagreement on the team's prospects, which correlates with miscalibration.

**History depth:** Posts persist indefinitely (modulo deletions). Search supports time filter `t={hour,day,week,month,year,all}`. **No arbitrary date range.** This is a limitation: we cannot directly query "posts mentioning Yankees between 2025-07-20 and 2025-08-20."

**Latency at T-35d:** Coarse. We can search `t=month` to get the most recent month of activity, but to get a historical AS-OF window we'd have to paginate `&after=t3_xxxxx` through results and bin client-side by created_utc.

**OOS-discipline rule:** If we use `t=month` at the live moment, we get the most recent month of activity which is essentially T-0 (today). For historical training, we have to paginate older posts and filter to `created_utc < T-35d`. Doable but engineering effort is 3.

**Effort to integrate:** 3 (pagination + client-side date binning).

**Coverage:** All sports, all teams. Reddit /r/baseball, /r/nfl, /r/nba, /r/hockey, /r/soccer are all active.

**Risk of being a noisy reflection of Kalshi price:** **HIGH.** Sports markets are widely discussed on Reddit. Posts about a team trend together with their performance, which trends together with their Kalshi price. The orthogonality check in Phase 2 must show post-count diff is not a proxy for current win pct.

**Recommendation:** Lower priority. Use as a SECONDARY feature after MLB Stats API team-stats. Even if it adds signal, the engineering cost is moderate and the risk of price-correlation is high.

### 5.2 GDELT Doc API (verified)

**What it is:** GDELT 2.0 Document API (`api.gdeltproject.org/api/v2/doc`). Indexes news articles globally. Supports arbitrary `startdatetime`/`enddatetime` parameters back to 2017-01-01.

**URL pattern (probed):**
```
GET https://api.gdeltproject.org/api/v2/doc/doc
    ?query=Yankees baseball&mode=ArtList&format=json
    &maxrecords=5
    &startdatetime=20250810000000&enddatetime=20250820000000
```
Status 200, 12,392ms (slow!), returned 5 articles between 2025-08-17 and 2025-08-20 about Yankees.

**History depth:** Back to 2017.

**Latency at T-35d:** Genuine AS-OF support via `startdatetime`/`enddatetime`. Best AS-OF support of any free source for arbitrary historical news queries.

**OOS-discipline rule:** For Kalshi T-35d = 2025-08-20, query `startdatetime=20250810000000&enddatetime=20250820235959`. Use `mode=TimelineVolRaw` to get article counts directly without paginating articles.

**Effort to integrate:** 2 (single HTTP GET; slow latency but only matters for training, not live).

**Coverage:** Multi-sport, all teams, multi-language. Very broad.

**Risk of being a price-proxy:** **MEDIUM.** Article counts trend with team performance and major events. But GDELT also captures stadium news, ownership changes, injuries, suspensions, etc. -- so it has some orthogonal information. The orthogonality check would be to regress on `[favorite_price, gdelt_article_count]` and check independence.

**Recommendation:** **Tier 2 feature.** Cheap to integrate; uses arbitrary AS-OF; has plausible information beyond price. Mode `TimelineVolRaw` is much faster than ArtList for our use case and reduces the 12s latency.

### 5.3 Hacker News (DISMISSED)

Per the brief: probably irrelevant for sports. HN front page is engineering/startup; very few sports headlines reach it. Skip.

## Category 6: Macro / Weather Context

### 6.1 Open-Meteo historical archive (verified)

**What it is:** Free, no-auth weather API. Historical archive at `archive-api.open-meteo.com/v1/archive`. Provides hourly weather for any lat/lon back to 1940.

**URL pattern (probed):**
```
GET https://archive-api.open-meteo.com/v1/archive
    ?latitude=40.83&longitude=-73.93
    &start_date=2025-08-20&end_date=2025-08-20
    &hourly=temperature_2m,precipitation,wind_speed_10m
```
Status 200, 755ms, returns hourly data with full 24-hour-per-day fidelity.

**Hypothesis under test:** For outdoor sports (MLB, NFL, NCAAF, MLS), weather at gametime affects scoring. Aggregated over the season-window, weather quality could plausibly predict outcomes for high-altitude or weather-prone teams (Rockies high altitude, Patriots cold weather, etc.).

**History depth:** Back to 1940.

**Latency at T-35d:** Native AS-OF. Pass `start_date`/`end_date` directly.

**OOS-discipline rule:** `end_date < T-35d`. Trivial.

**Effort:** 1.

**Coverage:** Any sport with a fixed-venue lat/lon. MLB stadiums all known; NFL outdoor venues; NCAAF outdoor venues. Coverage broad.

**Risk of being price-proxy:** **LOW.** Weather is highly orthogonal to Kalshi market price (markets do not deeply incorporate weather forecasts at T-35d, since the actual game weather is unknown that far in advance).

**Recommendation:** **Niche use.** Only relevant for outdoor sports outcomes IF the model is predicting individual games. For season-win-total markets the per-game weather signal averages out. For v3's long-horizon season markets, this is probably noise. Use only if we pivot to short-horizon outdoor-game markets.

The KXHIGH project (Round 1) tested weather features on a different question (NYC daily-high temperatures) and KILLED at OOS gate. The Le-2026 literature noted weather has SMALLER favorite-longshot bias than the cross-category average (ψ 0.031 vs 0.034). Weather is unlikely to give us the lift we need.

## Category 7: 538 ELO Ratings (mostly DEAD)

### 7.1 Direct site (DEAD)

`projects.fivethirtyeight.com/*` URLs **redirect to `abcnews.com/politics`**. Probed: all 538 NBA/NFL ELO direct URLs return 200 status BUT the body is the ABC News politics homepage HTML, not the CSV. **Disney shut down the property in 2025; the URLs are non-functional.**

### 7.2 GitHub mirror at `fivethirtyeight/data` (FROZEN, partial verified)

**What it is:** GitHub repo at `github.com/fivethirtyeight/data`. Contains a snapshot of 538's data products at the time the project shut down. **Not updated.**

**URL pattern (probed):**
```
GET https://raw.githubusercontent.com/fivethirtyeight/data/master/nba-elo/nbaallelo.csv
```
Status 200, 1,650ms, returns NBA all-time ELO CSV: `gameorder, game_id, lg_id, _iscopy, year_id, date_game, seasongame, is_playoffs, team_id, fran_id, pts, elo_i, elo_n, win_equiv, opp_id, opp_fran, opp_pts, opp_elo_i, opp_elo_n, game_location, game_result, forecast, notes`. First row: 1946-11-01, last row date varies by file but stops at 538 shutdown.

**Hypothesis under test:** Frozen 538 ELO for past NBA games gives us a clean point-in-time team-strength feature for training on historical Kalshi markets.

**History depth:** 1946 to ~2023 for NBA (depending on file); 1920+ to ~2023 for NFL.

**Latency at T-35d:** AS-OF via row filtering (`date_game < T-35d`).

**OOS-discipline rule:** Filter the parquet/CSV to rows with `date_game < T-35d`. Then aggregate per-team ELO.

**Effort:** 2 (CSV download + filter + per-team aggregation).

**Coverage:** NBA (back to 1946) and NFL (back to 1920). **No live updates.** For Kalshi markets closing 2024 or later, 538 ELO is **stale**. We can construct a feature like "538 ELO as of 2023-04 for this team" but it loses freshness rapidly.

**Recommendation:** **Use only for backtest training on Kalshi 2022-2023 markets.** Cannot be used as a live feature.

### 7.3 NFL ELO Wayback (partial, NFL-only)

**URL pattern:** `https://archive.org/wayback/available?url=projects.fivethirtyeight.com/nfl-api/nfl_elo.csv&timestamp=20230601` returns a Wayback snapshot at `http://web.archive.org/web/20230427025725/...nfl_elo.csv`. NBA equivalent returned `archived_snapshots: {}` (no snapshot at the queried date).

**History depth:** NFL ELO via Wayback exists back to ~2017 (multiple snapshots throughout). NBA ELO via Wayback is sparse.

**Effort:** 3 (Wayback URL discovery + CSV parse).

**Recommendation:** Skip. The GitHub mirror covers the same data with less effort. Only use Wayback if a specific year's snapshot is needed.

## Category 8: Power Rankings

### 8.1 ESPN Power Rankings / FPI (incomplete probe)

Probed `https://sports.core.api.espn.com/v2/sports/football/leagues/nfl/seasons/2024/types/2/powerindex` -> 404. Correct path is not obvious; likely requires authenticating with ESPN+ for FPI. Skip.

### 8.2 nflverse PFR ratings (worth probing in Phase 2)

PFR publishes DVOA / power rankings; nflverse has them in `pfr_advstats` releases. Effort 2 to extract. Coverage NFL-only.

### 8.3 Reddit/Twitter scraping for power rankings (DISMISSED)

Per the brief: text-form rankings would need scraping plus parsing of natural-language rankings. JS rendering required for ESPN's web ranking pages. Effort 5. **Dismissed.**

## Ranked Recommendation for Phase 2

Given v2's failure modes (model anchored on price; team-stat features added nothing detectable at n=123), the orthogonality discipline is non-negotiable: each feature must demonstrate independent signal partialled out of Kalshi price. Below are the 5-8 features I'd prioritize, in order:

### Priority 1: MLB Stats API team byDateRange stats (effort 1)

**Features:** `runs_scored_per_game`, `runs_allowed_per_game`, `pythagorean_w_pct` (computed from R/RA), `w_pct_diff_vs_opponent`, `wins_last_10`, `gamesBack`.

**Hypothesis:** A team's true win pct at T-35d, conditioned on the Kalshi price, deviates from market expectations enough that signal exists at the cohort level (not just for COL outliers).

**Expected lift per literature:** Burgi/Whelan suggest weather (and by analogy macro-team stats) have ψ ~0.03 favorite-longshot bias. For our long-horizon set, the deviation from `favorite_price` direction is small but on the right side. Conservative estimate: 1-3pp lift in calibrated edge over v1's flat 0.95 prior, **conditional on the team-stat feature surviving the orthogonality check**.

**Risk if v2 failure mode repeats:** Critic-favorite-maker found team stats added nothing detectable at v2's n=123. We need to ensure: (a) MUCH larger n (>200), (b) explicit orthogonalization against price in the loss function or via residual regression.

### Priority 2: Polymarket mid-price as a LIVE feature (effort 3, contingent)

**Features:** `poly_mid_yes_T-35d`, `poly_spread_T-35d`.

**Hypothesis:** Polymarket leads Kalshi on price discovery for events listed on both. Per master plan Section 2.

**Expected lift per literature:** 2024 election research documented Kalshi-Polymarket spreads on 62 of 65 days. For sports, the magnitude is smaller; v2 found no documented spread > 5c in 2026 sports.

**Critical blocker:** Historical price data is unavailable for events that closed > 30 days ago via the free CLOB endpoint. **For Phase 2 training, this feature must either (a) come from a prospective logger we don't have, or (b) be omitted.**

**Risk if used live-only:** The model has no historical OOS evidence of edge; gate would have to be evaluated on live-collected walk-forward data only.

### Priority 3: nflverse stats_team_week (effort 2)

**Features:** NFL team `wins_pythagorean`, `ppg_diff`, `dvoa_diff` (if available in `pfr_advstats`), `injuries_count_starters`.

**Hypothesis:** NFL season-win-total contracts (`KXNFLWINS-XX-N`) have correlated team-strength signals beyond market price.

**Expected lift:** ~1-2pp if team strength is incrementally informative. NFL season is short (17 games) so noise is high.

**Coverage:** NFL-only.

### Priority 4: GDELT TimelineVolRaw (effort 2)

**Features:** `gdelt_article_count_30d_window_pre_T35d` for each team.

**Hypothesis:** Disagreement (high news volume) correlates with miscalibration; quiet teams are mean-reverting.

**Expected lift:** Speculative. Volume of news is more a proxy for "popular team" than "right team."

**Risk:** Article count is correlated with team market visibility, which is correlated with price level. Strong orthogonality check needed.

### Priority 5: MLB roster active-as-of-date (effort 1)

**Features:** `n_active_star_players_T35d`, `days_since_top_pitcher_il_event`.

**Hypothesis:** Roster availability at T-35d predicts season-end outcomes.

**Expected lift:** Small. By T-35d most injuries are already reflected in the Kalshi price.

**Use:** Supplementary feature; not load-bearing.

### Priority 6: 538 ELO frozen (effort 2, narrow use)

**Features:** `elo_at_T35d` from 538 mirror.

**Use:** Only for Kalshi markets that closed in 2022-2023. Cannot be used for 2024+ markets (data is frozen).

### Priorities 7-8: Open-Meteo weather (effort 1, niche) and ESPN scoreboard (effort 2, cross-check)

Both are supplementary; don't expect them to drive primary signal.

### Features I would NOT prioritize for Phase 2

- **ESPN injuries**: no AS-OF support, contamination risk for training.
- **the-odds-api historical**: requires paid plan; free tier gives no historical.
- **Reddit search**: t=week/t=year is too coarse for AS-OF; pagination effort is moderate; high price-correlation risk.
- **Pinnacle / SBR scrapes**: against robots.txt for some sites; effort 5.
- **ESPN FPI**: 404 on the obvious path; needs more probing or auth.

## Orthogonality check protocol (for Phase 2)

For each candidate feature X in {pyth_win_pct_diff, poly_mid, gdelt_count, ...}, the dataset builder must:

1. **Compute residual feature.** Fit `OLS(X ~ favorite_price)` on the training-portion only. Subtract the predicted X-given-price. Call this `X_resid`.

2. **Test predictive power of X_resid.** Add `X_resid` as a feature alongside `favorite_price`. Check whether the model's holdout AUC, Brier score, and gate-criterion C1 (holdout mean P&L) improve over the baseline model trained on `favorite_price` alone.

3. **Survival criterion.** If `X_resid`'s coefficient has bootstrap CI excluding zero AND if model-with-X improves over model-without by >= 0.5pp in holdout P&L, retain. Otherwise drop.

4. **Combined survival check.** Even if individual features pass, the final feature set must survive a joint walk-forward CV with proper per-fold retraining (v2 critic's Section 3 finding). The C5 leak is fixed in `src/kalshi_bot_v2/gate.py`; ensure the trainer= parameter is set.

This protocol directly addresses the v2 critic's "model anchored on price; team-stat features alone produced max prob 0.67" failure mode. Features that don't survive the residual test are dropped before training begins.

## Feature freshness budget at T-35d sampling moment

| Feature | AS-OF support | Freshness at T-35d | Effort | Coverage |
|---|---|---|---|---|
| MLB Stats API standings | Native (`date=` param) | Same day (yesterday's data, finalized) | 1 | MLB |
| MLB Stats API byDateRange | Native (`endDate=`) | Same day | 1 | MLB |
| MLB roster active | Native (`date=`) | Same day | 1 | MLB |
| nflverse weekly parquet | Manual (filter on game_date) | Week-old (release cadence) | 2 | NFL |
| nflverse injuries parquet | Manual (filter on date_modified) | Week-old | 2 | NFL |
| ESPN scoreboard | Native (`dates=`) | Same day | 2 | Multi-sport |
| ESPN injuries | NONE (current only) | UNUSABLE FOR TRAINING | - | Multi-sport |
| ESPN team-by-season | Native (`/seasons/2024/teams/{id}`) | Season-snapshot only (not intra-season) | 2 | Multi-sport |
| Polymarket prices-history | Partial (30-day ceiling) | UNUSABLE FOR HISTORICAL > 30d | 3 | Subset of v1 universe |
| Polymarket order book | NONE | UNUSABLE FOR HISTORICAL | 3 | Subset of v1 universe |
| Reddit search | Coarse (`t=week/year` only) | Approximate; pagination needed for AS-OF | 3 | All teams |
| GDELT Doc / TimelineVolRaw | Native (`startdatetime=`) | Same day | 2 | All teams, news-mediated |
| Open-Meteo archive | Native (`start_date=`) | Day-of game | 1 | Outdoor venues |
| 538 ELO GitHub mirror | Manual (filter on `date_game`) | FROZEN at 2023 | 2 | NBA / NFL (frozen) |
| the-odds-api free | Live only (no historical on free) | UNUSABLE FOR TRAINING | 2 | All US sports |
| the-odds-api paid | Native | Live | 2 | All US sports |

**Stalest (unusable):** ESPN injuries, the-odds-api historical (free tier), Polymarket price history > 30 days, Polymarket order book historical.

**Freshest (same-day, native AS-OF):** MLB Stats API endpoints, ESPN scoreboard, Open-Meteo archive, GDELT.

**The freshness budget reveals the v3 thesis vulnerability:** the proposed leading feature (Polymarket) has the worst freshness at T-35d. The features with the best freshness are team-stat features, which v2 already found added nothing detectable at small n.

## Final pessimist's view

Per the v2 critic Section 5: "the model is not adding signal; it is concentrating on the sub-bucket where the price-conditioning is most favorable." The orthogonality check is the single most important Phase 2 discipline. Even if all eight of my recommended features integrate cleanly, **none of them are guaranteed to add lift past v1's price prior** unless we (a) get the n above 200, (b) survive per-fold retraining, and (c) survive the COL/per-team holdout drop.

If Polymarket as a live feature is the load-bearing feature (because the master plan thesis says it's the only known predictor that LEADS Kalshi), then the 30-day history ceiling forces v3 to either:

1. **Pivot to a prospective-only design** (collect Polymarket history for 60 days, then train on what we've collected, with very small training n). This significantly delays Phase 2.

2. **Use Polymarket as a live-only signal in an H3 statistical rule** rather than a model feature. Skip the ML model entirely.

3. **Accept that v3 is fundamentally constrained by Polymarket data availability** and pivot to a different external feature set (team stats only, no Polymarket) with the understanding that we're testing what v2 already tested at slightly bigger n.

This is a Phase 2 decision for the orchestrator. The feature audit cannot resolve it; the audit's job is to flag that the Polymarket history ceiling is a v3-thesis blocker.

## Sources (probed, in `data/v3/`)

- `feature_probe_polymarket.json`
- `feature_probe_polymarket_history.json`
- `feature_probe_polymarket_followup.json`
- `feature_probe_mlb_stats.json`
- `feature_probe_espn.json`
- `feature_probe_reddit.json`
- `feature_probe_odds_api.json`
- `feature_probe_538.json`
- `feature_probe_nflverse.json`
- `feature_probe_weather.json`
- `feature_probe_gdelt.json`
- `feature_probe_summary.json`

Probe scripts: `scripts/v3/probe_features.py`, `scripts/v3/probe_polymarket_history.py`, `scripts/v3/probe_polymarket_followup.py`.

Citations:
- `research/v2/02-polymarket-arb-research.md` (v2 Polymarket research, Section 2/3/4)
- `research/v2/06-critic.md` (v2 critic, Sections 5 and 7)
- `research/literature/INDEX.md` (Burgi/Le/Becker on bias magnitudes)
- `research/v3/00-master-plan.md` (v3 thesis and gate criteria)
