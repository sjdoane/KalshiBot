"""V3 feature-source probes.

Tests each candidate external-feature source for:
- Endpoint behavior (auth, latency, response shape)
- History depth available
- AS-OF support (can we query a specific past timestamp?)
- Rate-limit posture

Writes results to data/v3/feature_probe_<source>.json.

Run: uv run python -m scripts.v3.probe_features
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data" / "v3"
DATA_DIR.mkdir(parents=True, exist_ok=True)

UA = {"User-Agent": "Mozilla/5.0 (ProjectKalshi v3 research probe; sjdoane@usc.edu)"}


def write(name: str, payload: dict[str, Any]) -> None:
    p = DATA_DIR / f"feature_probe_{name}.json"
    p.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(f"  wrote {p.name}")


def timed_get(client: httpx.Client, url: str, params: dict | None = None, headers: dict | None = None) -> dict:
    t0 = time.perf_counter()
    try:
        r = client.get(url, params=params or {}, headers=headers or {})
        elapsed_ms = (time.perf_counter() - t0) * 1000
        info = {"url": str(r.request.url), "status": r.status_code, "latency_ms": round(elapsed_ms, 1)}
        try:
            body = r.json()
        except Exception:
            body = r.text[:500]
        info["body_sample"] = body if isinstance(body, str) else _truncate(body)
        if isinstance(body, dict):
            info["top_level_keys"] = list(body.keys())[:20]
        elif isinstance(body, list) and body:
            info["list_len"] = len(body)
            if isinstance(body[0], dict):
                info["first_item_keys"] = list(body[0].keys())[:20]
        return info
    except Exception as e:
        return {"url": url, "error": str(e)}


def _truncate(obj: Any, max_chars: int = 2000) -> Any:
    s = json.dumps(obj, default=str)
    if len(s) <= max_chars:
        return obj
    return s[:max_chars] + "...TRUNCATED"


# ---------- 1. Polymarket deep dive ----------

def probe_polymarket() -> None:
    print("\n=== Polymarket ===")
    out: dict[str, Any] = {"probed_at_unix": int(time.time())}
    with httpx.Client(timeout=20.0, headers=UA) as client:
        # 1a. Search for a sports event we can use as a token_id source
        out["search_nfl"] = timed_get(
            client,
            "https://gamma-api.polymarket.com/public-search",
            params={"q": "NFL Super Bowl 2026 winner", "limit_per_type": 5},
        )
        out["search_mlb"] = timed_get(
            client,
            "https://gamma-api.polymarket.com/public-search",
            params={"q": "MLB World Series 2026", "limit_per_type": 5},
        )

        # 1b. Active markets - sports tag
        out["events_sports_tag"] = timed_get(
            client,
            "https://gamma-api.polymarket.com/events",
            params={"limit": 5, "tag": "sports", "active": "true"},
        )

        # 1c. Get a single market to extract clobTokenIds for price history
        markets_resp = timed_get(
            client,
            "https://gamma-api.polymarket.com/markets",
            params={"limit": 50, "active": "true", "closed": "false"},
        )
        out["markets_first_page"] = {
            "list_len": markets_resp.get("list_len"),
            "latency_ms": markets_resp.get("latency_ms"),
        }

        sample_token = None
        sample_market_meta = None
        if isinstance(markets_resp.get("body_sample"), list):
            for m in markets_resp["body_sample"]:
                tokens = m.get("clobTokenIds")
                if isinstance(tokens, str):
                    try:
                        tokens = json.loads(tokens)
                    except Exception:
                        tokens = None
                if tokens and len(tokens) >= 1:
                    sample_token = tokens[0]
                    sample_market_meta = {
                        "question": m.get("question"),
                        "slug": m.get("slug"),
                        "startDateIso": m.get("startDateIso"),
                        "endDateIso": m.get("endDateIso"),
                        "tokens": tokens,
                    }
                    break

        out["sample_market_for_history"] = sample_market_meta

        if sample_token:
            # 1d. CLOB price-history. Documented interval values: 1m, 1h, 6h, 1d, 1w, max
            for interval in ["1m", "1h", "6h", "1d", "1w", "max"]:
                out[f"price_history_{interval}"] = timed_get(
                    client,
                    "https://clob.polymarket.com/prices-history",
                    params={"market": sample_token, "interval": interval, "fidelity": 60},
                )
                time.sleep(0.4)

            # 1e. Try a startTs/endTs range query (custom window)
            now = int(time.time())
            t_minus_35d = now - 35 * 24 * 3600
            t_minus_36d = now - 36 * 24 * 3600
            out["price_history_range_35d"] = timed_get(
                client,
                "https://clob.polymarket.com/prices-history",
                params={"market": sample_token, "startTs": t_minus_36d, "endTs": t_minus_35d, "fidelity": 60},
            )

            # 1f. CLOB orderbook (current depth only)
            out["orderbook"] = timed_get(
                client,
                "https://clob.polymarket.com/book",
                params={"token_id": sample_token},
            )

            # 1g. midpoint
            out["midpoint"] = timed_get(
                client,
                "https://clob.polymarket.com/midpoint",
                params={"token_id": sample_token},
            )

            # 1h. spread
            out["spread"] = timed_get(
                client,
                "https://clob.polymarket.com/spread",
                params={"token_id": sample_token},
            )

            # 1i. Data API - try to find historical trades for this token
            out["data_api_trades"] = timed_get(
                client,
                "https://data-api.polymarket.com/trades",
                params={"market": sample_token, "limit": 5},
            )

        # 1j. Sports tag listing
        out["sports_list"] = timed_get(
            client,
            "https://gamma-api.polymarket.com/sports",
        )

    write("polymarket", out)


# ---------- 2. MLB Stats API ----------

def probe_mlb_stats() -> None:
    print("\n=== MLB Stats API ===")
    out: dict[str, Any] = {"probed_at_unix": int(time.time())}
    with httpx.Client(timeout=20.0, headers=UA) as client:
        # 2a. Teams list (no auth)
        out["teams"] = timed_get(
            client,
            "https://statsapi.mlb.com/api/v1/teams",
            params={"sportId": 1, "season": 2025},
        )
        # 2b. Team standings at a specific season-date (AS-OF the date supplied)
        out["standings_as_of_2025_08_20"] = timed_get(
            client,
            "https://statsapi.mlb.com/api/v1/standings",
            params={
                "leagueId": "103,104",
                "season": 2025,
                "date": "2025-08-20",
                "standingsTypes": "regularSeason",
            },
        )
        # 2c. Team stats endpoint with date filter
        out["team_stats_byDateRange_2025"] = timed_get(
            client,
            "https://statsapi.mlb.com/api/v1/teams/147/stats",
            params={
                "season": 2025,
                "stats": "byDateRange",
                "startDate": "2025-04-01",
                "endDate": "2025-08-20",
                "group": "hitting,pitching",
            },
        )
        # 2d. Schedule for a date range
        out["schedule_window"] = timed_get(
            client,
            "https://statsapi.mlb.com/api/v1/schedule",
            params={
                "sportId": 1,
                "startDate": "2025-08-10",
                "endDate": "2025-08-20",
                "hydrate": "team",
            },
        )
        # 2e. Injuries / roster
        out["roster_active"] = timed_get(
            client,
            "https://statsapi.mlb.com/api/v1/teams/147/roster",
            params={"rosterType": "active", "date": "2025-08-20"},
        )
    write("mlb_stats", out)


# ---------- 3. ESPN site API ----------

def probe_espn() -> None:
    print("\n=== ESPN site API ===")
    out: dict[str, Any] = {"probed_at_unix": int(time.time())}
    with httpx.Client(timeout=20.0, headers=UA, follow_redirects=True) as client:
        # 3a. NFL scoreboard (current)
        out["nfl_scoreboard_current"] = timed_get(
            client,
            "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard",
        )
        # 3b. NFL scoreboard for a historical date
        out["nfl_scoreboard_20240901"] = timed_get(
            client,
            "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard",
            params={"dates": "20240901"},
        )
        # 3c. NFL injuries (current)
        out["nfl_injuries"] = timed_get(
            client,
            "https://site.api.espn.com/apis/site/v2/sports/football/nfl/injuries",
        )
        # 3d. MLB standings (current)
        out["mlb_standings_current"] = timed_get(
            client,
            "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/standings",
        )
        # 3e. Try team-specific historic stat (season-based)
        out["nfl_team_28"] = timed_get(
            client,
            "https://sports.core.api.espn.com/v2/sports/football/leagues/nfl/seasons/2024/teams/28",
        )
        # 3f. Power index endpoint
        out["nfl_powerindex_2024"] = timed_get(
            client,
            "https://sports.core.api.espn.com/v2/sports/football/leagues/nfl/seasons/2024/types/2/powerindex",
        )
    write("espn", out)


# ---------- 4. Reddit JSON API ----------

def probe_reddit() -> None:
    print("\n=== Reddit JSON API ===")
    out: dict[str, Any] = {"probed_at_unix": int(time.time())}
    reddit_headers = dict(UA)
    with httpx.Client(timeout=20.0, headers=reddit_headers, follow_redirects=True) as client:
        # 4a. Subreddit JSON listing
        out["r_baseball_new"] = timed_get(
            client,
            "https://www.reddit.com/r/baseball/new.json",
            params={"limit": 10},
        )
        # 4b. Search within a subreddit with restrict_sr (date filter via t param)
        out["search_yankees_week"] = timed_get(
            client,
            "https://www.reddit.com/r/baseball/search.json",
            params={"q": "Yankees", "restrict_sr": "on", "limit": 25, "t": "week", "sort": "new"},
        )
        # 4c. Search with after= cursor pagination
        out["search_dodgers_year"] = timed_get(
            client,
            "https://www.reddit.com/r/baseball/search.json",
            params={"q": "Dodgers", "restrict_sr": "on", "limit": 25, "t": "year", "sort": "new"},
        )
        # 4d. Check r/nfl too
        out["r_nfl_about"] = timed_get(
            client,
            "https://www.reddit.com/r/nfl/about.json",
        )
    write("reddit", out)


# ---------- 5. The-odds-api (no key) ----------

def probe_odds_api() -> None:
    print("\n=== the-odds-api (no key) ===")
    out: dict[str, Any] = {"probed_at_unix": int(time.time())}
    with httpx.Client(timeout=20.0, headers=UA) as client:
        # 5a. Sports list (does not require API key on some endpoints)
        out["sports_no_key"] = timed_get(
            client,
            "https://api.the-odds-api.com/v4/sports/",
        )
        # 5b. Odds endpoint - expect 401 without key
        out["odds_no_key"] = timed_get(
            client,
            "https://api.the-odds-api.com/v4/sports/baseball_mlb/odds/",
            params={"regions": "us", "markets": "h2h"},
        )
        # 5c. Historical odds (paid feature; will likely fail without key)
        out["historical_no_key"] = timed_get(
            client,
            "https://api.the-odds-api.com/v4/historical/sports/baseball_mlb/odds",
            params={"regions": "us", "markets": "h2h", "date": "2024-05-01T00:00:00Z"},
        )
    write("odds_api", out)


# ---------- 6. 538 Wayback ELO ----------

def probe_538() -> None:
    print("\n=== 538 archives ===")
    out: dict[str, Any] = {"probed_at_unix": int(time.time())}
    with httpx.Client(timeout=30.0, headers=UA, follow_redirects=True) as client:
        # 6a. Direct from projects.fivethirtyeight.com (often 200 but HTML, not CSV)
        out["nba_elo_csv_direct"] = timed_get(
            client,
            "https://projects.fivethirtyeight.com/nba-model/nba_elo.csv",
        )
        # 6b. GitHub mirror of 538 data
        out["github_nba_elo"] = timed_get(
            client,
            "https://raw.githubusercontent.com/fivethirtyeight/data/master/nba-elo/nbaallelo.csv",
        )
        out["github_nfl_elo"] = timed_get(
            client,
            "https://projects.fivethirtyeight.com/nfl-api/nfl_elo.csv",
        )
        out["github_nfl_elo_latest"] = timed_get(
            client,
            "https://projects.fivethirtyeight.com/nfl-api/nfl_elo_latest.csv",
        )
        # 6c. Wayback Machine availability check
        out["wayback_nba"] = timed_get(
            client,
            "https://archive.org/wayback/available",
            params={"url": "projects.fivethirtyeight.com/nba-model/nba_elo.csv", "timestamp": "20230601"},
        )
        out["wayback_nfl"] = timed_get(
            client,
            "https://archive.org/wayback/available",
            params={"url": "projects.fivethirtyeight.com/nfl-api/nfl_elo.csv", "timestamp": "20230601"},
        )
    write("538", out)


# ---------- 7. nflverse ----------

def probe_nflverse() -> None:
    print("\n=== nflverse releases ===")
    out: dict[str, Any] = {"probed_at_unix": int(time.time())}
    with httpx.Client(timeout=30.0, headers=UA, follow_redirects=True) as client:
        # nflverse-data releases JSON
        out["nfldata_releases"] = timed_get(
            client,
            "https://api.github.com/repos/nflverse/nflverse-data/releases",
            params={"per_page": 20},
        )
        # nfl_data_py weekly stats parquet (sample URL pattern)
        out["weekly_stats_2024"] = timed_get(
            client,
            "https://github.com/nflverse/nflverse-data/releases/download/stats_team/stats_team_week_2024.parquet",
        )
    write("nflverse", out)


# ---------- 8. Weather (open-meteo, free) ----------

def probe_weather() -> None:
    print("\n=== Open-Meteo historical archive ===")
    out: dict[str, Any] = {"probed_at_unix": int(time.time())}
    with httpx.Client(timeout=20.0, headers=UA) as client:
        # Yankee Stadium ~ 40.83, -73.93
        out["historical_archive_yankee"] = timed_get(
            client,
            "https://archive-api.open-meteo.com/v1/archive",
            params={
                "latitude": 40.83,
                "longitude": -73.93,
                "start_date": "2025-08-20",
                "end_date": "2025-08-20",
                "hourly": "temperature_2m,precipitation,wind_speed_10m",
            },
        )
        out["forecast_yankee"] = timed_get(
            client,
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": 40.83,
                "longitude": -73.93,
                "hourly": "temperature_2m,precipitation,wind_speed_10m",
            },
        )
    write("weather", out)


# ---------- 9. GDELT (news/events) ----------

def probe_gdelt() -> None:
    print("\n=== GDELT ===")
    out: dict[str, Any] = {"probed_at_unix": int(time.time())}
    with httpx.Client(timeout=30.0, headers=UA, follow_redirects=True) as client:
        out["doc_v2_yankees"] = timed_get(
            client,
            "https://api.gdeltproject.org/api/v2/doc/doc",
            params={
                "query": "Yankees baseball",
                "mode": "ArtList",
                "format": "json",
                "maxrecords": 5,
                "startdatetime": "20250810000000",
                "enddatetime": "20250820000000",
            },
        )
    write("gdelt", out)


def main() -> int:
    probes = [
        probe_polymarket,
        probe_mlb_stats,
        probe_espn,
        probe_reddit,
        probe_odds_api,
        probe_538,
        probe_nflverse,
        probe_weather,
        probe_gdelt,
    ]
    summary = {"runs": []}
    for fn in probes:
        t0 = time.perf_counter()
        try:
            fn()
            summary["runs"].append({"probe": fn.__name__, "ok": True, "elapsed_s": round(time.perf_counter() - t0, 2)})
        except Exception as e:
            print(f"  FAIL: {fn.__name__} -> {e}")
            summary["runs"].append({"probe": fn.__name__, "ok": False, "error": str(e)})
    (DATA_DIR / "feature_probe_summary.json").write_text(
        json.dumps(summary, indent=2, default=str), encoding="utf-8"
    )
    print("\nALL DONE.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
