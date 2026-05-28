# v2 Data Sources Catalog (Agent A)

**Date:** 2026-05-23
**Author:** Agent A (Wave 1 research, autonomous)
**Probe script:** `scripts/v2/probe_data_source.py`
**Probe outputs:** `data/v2/probe_*.parquet`, `data/v2/probe_summary.json`

## 1. Scope and method

Catalogs free + cheap data for v2 sports prediction. Need (a) historical Kalshi sports markets and (b) sports stats to join against. Every source below was probed live; numbers, latencies, and shapes are recorded inline or in `data/v2/probe_*.parquet`. The READ-scope Kalshi key from `.env` was used for the Kalshi probes.

## 2. Kalshi historical endpoints (the demand side of the join)

### 2.1 Endpoints and cutoff

Live against `external-api.kalshi.com`:

- `GET /historical/cutoff` = `{"market_settled_ts":"2026-03-24T00:00:00Z", ...}` as of 2026-05-23. Rolling boundary ~2 months in the past. Pre-cutoff markets live under `/historical/*`; post-cutoff under live endpoints. The dataset build must handle the seam.
- `GET /historical/markets` returns `{cursor, markets}`. Each market has `ticker`, `event_ticker`, `series_ticker`, `open_time`, `close_time`, `status` (`finalized`), `result` (`yes`/`no`/`scalar`), `last_price_dollars`, `volume_fp`, `liquidity_dollars`, `settlement_ts`, `settlement_value_dollars`, `rules_primary`, `rules_secondary`. Settlement fully populated.
- `GET /historical/trades` returns tick-level: `{created_time, ticker, yes_price_dollars, no_price_dollars, count_fp, taker_side, taker_book_side, taker_outcome_side, trade_id}`. Prices are dollar strings (per March 2026 migration).
- `GET /historical/orders` and `/historical/fills` are account-scoped (own orders only); not for cross-market modeling.

### 2.2 Filters that work

- `series_ticker=KXNBAGAME` confirmed working (full league filter).
- `min_close_ts` / `max_close_ts` as Unix integer seconds (UTC) confirmed.
- `category=Sports` filters server-side but the `category` field is null in the response; resolve via `/events` (which does populate it).
- `event_ticker=<exact>` did NOT return matches; only series filtering is reliable.

### 2.3 Throughput

No explicit token cost listed for `/historical/*` in `/account/endpoint_costs`; defaults to 10/req per `research/briefs/agent-a-api-infra.md` Section 3. Basic ceiling: 200 read tok/sec = ~20 req/sec.

Observed: `/historical/markets` 30 pages in 1.4s (~21 req/s, ~2,100 rows/s); `/historical/trades` 30 pages in 2.9s (~1,024 rows/s). No 429s. Rate limits are not the bottleneck for v2.

### 2.4 Sample sizes confirmed

| Series | Markets | Date range | Pull time |
|---|---|---|---|
| KXNBAGAME | 2,394 | 2025-04-14 to 2026-03-20 | 2.8s |
| KXMLBGAME | 4,414 | 2025-04-16 to 2025-10-29 | 5.3s |
| KXNFLGAME | 666 | 2025-05-20 to 2026-01-23 | 1.2s |
| KXNHLGAME | 2,528 | 2025-04-18 to 2026-03-20 | 3.0s |

All `finalized`. Result is 50/50 yes/no by construction (each game has YES and NO markets). Unique-game counts: ~MLB 2,207, NHL 1,264, NBA 1,197, NFL 333. NBA/MLB/NHL samples saved at `data/v2/probe_kalshi_KX*GAME_history.parquet`. A full year of any sport's binary game outcomes is pullable in <6s on the Basic READ tier.

### 2.5 What is NOT available

L2 orderbook depth is not exposed under `/historical/*` (confirmed in the api-infra brief Section 10). Backtests must reconstruct from `/historical/trades` prints.

## 3. Free sports stats sources (the supply side of the join)

### 3.1 MLB Stats API (`statsapi.mlb.com`)

Free, official, no auth. Probe of `/api/v1/schedule?sportId=1&date=2026-05-22`: 16 games in 108ms. Full 2024 regular season pull (startDate=2024-03-28, endDate=2024-09-29, gameType=R): **2,465 games in 0.6s, 3.1 MB JSON**. Saved at `data/v2/probe_mlb_2024_season.parquet`. Coverage: 1900+, with per-pitch detail via `/game/{pk}/playByPlay` (same backend Baseball Savant uses). For Statcast pitch-level CSVs, use `pybaseball` (scrapes the export endpoint) since `baseballsavant.mlb.com/statcast_search` returns HTML.

### 3.2 nflverse parquet releases

Free, direct from GitHub releases. `nfl-data-py` PyPI wrapper has a hard pandas==1.5.3 pin that conflicts with this repo's pandas 3.0.3, so **bypass the wrapper**.

- `releases/download/pbp/play_by_play_2024.parquet`: **49,492 plays, 372 columns, 19.6 MB in 1.4s**. Saved week-1 sample at `data/v2/probe_nfl_pbp_2024_wk1.parquet`.
- `nfldata/data/games.csv`: **7,548 games covering 1999 to 2026**, 46 cols including spread, total, surface, weather. Sample at `data/v2/probe_nfl_schedules_sample.parquet`.
- Access difficulty 1 (static HTTP GET). Maintenance risk low (large community).

### 3.3 ESPN site API (`site.api.espn.com`)

Free, no auth, stable. All four major-league scoreboards returned in under 200ms (NFL 16 events, NBA 1, MLB 16, NHL 1 on 2026-05-23). Use for live cross-checks; for static historical, prefer the source-specific APIs. Saved at `data/v2/probe_espn_scoreboard_summary.parquet`.

### 3.4 NBA Stats API (`stats.nba.com`)

**Broken from this environment.** `/leaguegamelog` timed out at 30s; `/scoreboardv2` timed out at 60s; `data.nba.net` SSL cert mismatch; `cdn.nba.com` 403. Known to geoblock and aggressively rate-limit. Workaround: ESPN NBA scoreboard + 538 ELO archive + Basketball-Reference scrape if needed. Sufficient for v2 training.

### 3.5 538 ELO archive (via Wayback Machine)

538 was shut down by Disney in March 2023. The CSVs survive on web.archive.org. `web.archive.org/web/2024/https://projects.fivethirtyeight.com/nba-model/nba_elo.csv` returned **73,363 NBA games from 1947 to 2023**, 27 columns including `elo1_pre`, `elo2_pre`, `elo_prob1`, `elo_prob2`, `carm-elo1_pre`. Saved sample at `data/v2/probe_538_nba_elo_sample.parquet`. Frozen archive: pull once, treat as prior or baseline, never as a live feed.

### 3.6 Sports-Reference family

Free HTML scrape with declared crawl-delay. Basketball-Reference (20 disallows + crawl-delay), Baseball-Reference (49 disallows), and Hockey-Reference reachable on 200; **Pro-Football-Reference returned 403** on robots.txt from default UA. Practical ceiling: 1 req per 3s with a residential UA. Not needed for the rolling Kalshi historical window (Apr 2025 onward).

### 3.7 The Odds API

Free tier: 500 requests/month per account. Endpoint reachable, returns 401 without a key. Sufficient for live closing-line snapshots, not for historical backfill. **Operator action: sign up at the-odds-api.com (free, just email).** Cost $0.

### 3.8 Retrosheet (MLB)

Free. Probe: `www.retrosheet.org/gamelogs/gl2024.zip` = 455 KB zip with all 2,461 MLB 2024 regular-season games as positional pipe-separated CSV. Fallback for pre-2000 history or fields MLB Stats API misses. Otherwise MLB Stats API is preferred (proper JSON).

### 3.9 Polymarket (cross-reference, Agent B's lane)

`gamma-api.polymarket.com/events?limit=100&active=true&tag_slug=sports` returned 100 active sports events including `2026-nba-champion`, `2026-nhl-stanley-cup-champion`, `2026-fifa-world-cup-winner`. Cross-matching feasibility is Agent B's deliverable.

## 4. Decision matrix

Rank columns: lower is easier/better. Programmatic-access difficulty is 1 (HTTP GET on a stable URL) to 5 (login + JS rendering + IP rotation). Maintenance risk is 1 (institutional API) to 5 (frozen archive that may disappear).

| Source | Sport coverage | History years | Granularity | Free? | Access difficulty | Maint risk | Rank for v2 |
|---|---|---|---|---|---|---|---|
| MLB Stats API | MLB | 1900+ (modern 2008+) | game + play + Statcast | Yes | 1 | 1 | A |
| nflverse parquet | NFL | 1999 to 2026 | play-by-play | Yes | 1 | 2 | A |
| Kalshi `/historical/markets` | All Kalshi-listed | rolling ~1 year, expanding | per-market settlement | Yes (READ key) | 1 | 1 | A (required) |
| ESPN site API | NFL/NBA/MLB/NHL/+ | live + recent seasons | game-level | Yes | 1 | 2 | B (live cross-check) |
| 538 NBA ELO (Wayback) | NBA | 1947 to 2023 | game + ELO probs | Yes | 2 | 5 (frozen) | B (priors only) |
| Retrosheet | MLB | 1871+ | game + play | Yes | 3 | 1 | C (fallback) |
| basketball-reference scrape | NBA | 1947+ | game/season | Yes | 3 | 3 | C (only if NBA picked) |
| Pro-Football-Reference scrape | NFL | 1920+ | game/season | Yes | 4 (403 from default UA) | 3 | D (avoid) |
| stats.nba.com | NBA | 1946+ | play-by-play | Yes | 5 (timed out here) | 3 | D (avoid for prod) |
| The Odds API free tier | NFL/NBA/MLB/NHL/soccer | live + 6mo | sportsbook odds | Yes (500/mo) | 2 (key needed) | 2 | B (closing line feature) |
| Sportradar / Stats Perform | All | full | full | No (enterprise) | n/a | n/a | skip per master plan |

Rank A = pull and persist now. Rank B = pull on demand when needed for a specific feature. Rank C = fallback if A fails. Rank D = avoid in v2 unless a specific need emerges.

## 5. Recommendation: pick MLB (with NBA as secondary)

1. **Data quality.** MLB Stats API is the strongest free official source of any league: JSON, no auth, sub-second latency, 1900+ depth, per-pitch detail. 2024 full season in 0.6s; 2025 Kalshi history in 5s. Both halves of the join are trivial. No scraping, no UA tricks.

2. **Kalshi market coverage.** MLB is the largest Kalshi sample of the four majors: **4,414 historical markets vs 2,394 NBA, 2,528 NHL, 666 NFL**. KXMLBGAME ran continuously Apr-Oct 2025. May 2026 active markets include KXMLBHRR, KXMLBTB, KXMLBKS, KXMLBHIT, KXMLBHR and KXMVE multi-game series.

3. **Seasonal alignment.** Today 2026-05-23, MLB 2026 regular season is active (March-September). 2025 history = training corpus; 2026 season = immediate paper-trade out-of-sample. NFL offseason until September; NBA Finals nearly over; NHL late playoffs. MLB is the only major where both training and live validation work right now.

4. **Predictability literature.** Deepest stat stack of any sport: Pythagorean expectation, Statcast xwOBA, FanGraphs WAR, park factors, batter/pitcher splits. ~2,430 regular-season games per season vs NFL 272 or NBA 1,230. More games means more statistical power to detect model edge versus the v1 heuristic.

**Caveat.** Becker reports Sports as a high-bias category (7+ pp range), but MLB-specific bias is not measured in our literature. If NBA favorites are mispriced more than MLB favorites, C6 (beating v1 by 2pp) may be easier in NBA despite worse data. **Recommend Agent C build the join for both MLB (primary) and NBA (secondary)** so Agent E can compare edge across leagues before locking in.

## 6. Blockers requiring operator input

None for Wave 1 research. All A-rank sources work from this environment with existing READ-scope key plus no-auth HTTP. Two soft asks (non-blocking):

1. Sign up at the-odds-api.com free tier (email only, $0) if Agent E wants closing-line features later.
2. If we ever need NBA Stats API, test from a residential IP to determine whether the timeouts are geoblocking or transient. Not needed for the MLB recommendation.
