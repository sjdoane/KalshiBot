"""Probe free public sports + odds data sources for v2 model feasibility.

Run as: uv run python -m scripts.v2.probe_data_source

For each source, perform a small live HTTP request, report shape and a
sample, note rate-limit headers if any, and save tiny parquet snapshots
under data/v2/probe_*.parquet for downstream agents to inspect.

Does NOT require any auth other than the read-scope Kalshi key for the
Kalshi portion (which is optional and gated behind --include-kalshi).

This is a v2 research artifact; it does not touch live v1 code paths.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = REPO_ROOT / "data" / "v2"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def _ok(name: str, msg: str) -> None:
    print(f"[OK]    {name}: {msg}")


def _fail(name: str, msg: str) -> None:
    print(f"[FAIL]  {name}: {msg}")


def _info(name: str, msg: str) -> None:
    print(f"[INFO]  {name}: {msg}")


def _save_parquet(df: pd.DataFrame, name: str) -> Path:
    path = OUT_DIR / f"probe_{name}.parquet"
    df.to_parquet(path, index=False)
    return path


def probe_mlb_stats_api(client: httpx.Client) -> dict[str, Any]:
    """statsapi.mlb.com is the official MLB free endpoint."""
    name = "mlb-stats-api"
    url = "https://statsapi.mlb.com/api/v1/schedule"
    # Pull yesterday's schedule (always present, even off-season has spring training or empty list)
    yesterday = (datetime.now(UTC) - timedelta(days=1)).strftime("%Y-%m-%d")
    params = {"sportId": 1, "date": yesterday}
    t0 = time.time()
    try:
        r = client.get(url, params=params, timeout=20.0)
        elapsed_ms = (time.time() - t0) * 1000
    except Exception as e:
        _fail(name, f"http error: {e!s}")
        return {"source": name, "ok": False, "error": str(e)}
    if r.status_code != 200:
        _fail(name, f"status={r.status_code}")
        return {"source": name, "ok": False, "status": r.status_code}
    j = r.json()
    games = []
    for d in j.get("dates", []):
        for g in d.get("games", []):
            games.append({
                "game_pk": g.get("gamePk"),
                "date": d.get("date"),
                "status": g.get("status", {}).get("detailedState"),
                "home": g.get("teams", {}).get("home", {}).get("team", {}).get("name"),
                "away": g.get("teams", {}).get("away", {}).get("team", {}).get("name"),
                "home_score": g.get("teams", {}).get("home", {}).get("score"),
                "away_score": g.get("teams", {}).get("away", {}).get("score"),
            })
    df = pd.DataFrame(games)
    path = _save_parquet(df, "mlb_schedule")
    _ok(name, f"{len(df)} games on {yesterday}, latency {elapsed_ms:.0f}ms, saved {path.name}")
    # Probe historical: 2024 World Series
    ws_url = "https://statsapi.mlb.com/api/v1/schedule"
    ws_params = {"sportId": 1, "startDate": "2024-10-25", "endDate": "2024-10-30", "gameType": "W"}
    r2 = client.get(ws_url, params=ws_params, timeout=20.0)
    if r2.status_code == 200:
        ws_games = sum(len(d.get("games", [])) for d in r2.json().get("dates", []))
        _info(name, f"2024 World Series window returned {ws_games} games (historical depth OK)")
    return {"source": name, "ok": True, "n_yesterday": len(df), "latency_ms": elapsed_ms}


def probe_nba_stats_api(client: httpx.Client) -> dict[str, Any]:
    """stats.nba.com is unofficial but stable. Needs a browser-like UA."""
    name = "nba-stats-api"
    url = "https://stats.nba.com/stats/leaguegamelog"
    params = {
        "Counter": 1000,
        "Direction": "DESC",
        "LeagueID": "00",
        "PlayerOrTeam": "T",
        "Season": "2024-25",
        "SeasonType": "Regular Season",
        "Sorter": "DATE",
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
        "Referer": "https://www.nba.com/",
        "Accept-Language": "en-US,en;q=0.9",
        "x-nba-stats-origin": "stats",
        "x-nba-stats-token": "true",
    }
    t0 = time.time()
    try:
        r = client.get(url, params=params, headers=headers, timeout=30.0)
        elapsed_ms = (time.time() - t0) * 1000
    except Exception as e:
        _fail(name, f"http error: {e!s}")
        return {"source": name, "ok": False, "error": str(e)}
    if r.status_code != 200:
        _fail(name, f"status={r.status_code} body={r.text[:200]}")
        return {"source": name, "ok": False, "status": r.status_code}
    j = r.json()
    result_set = j.get("resultSets", [{}])[0]
    headers_list = result_set.get("headers", [])
    rows = result_set.get("rowSet", [])
    df = pd.DataFrame(rows, columns=headers_list)
    path = _save_parquet(df.head(500), "nba_gamelog_sample")
    _ok(name, f"{len(df)} rows (regular season game log), cols={len(headers_list)}, latency {elapsed_ms:.0f}ms")
    return {"source": name, "ok": True, "n_rows": len(df), "latency_ms": elapsed_ms}


def probe_espn_api(client: httpx.Client) -> dict[str, Any]:
    """ESPN unofficial site API. No key required."""
    name = "espn-api"
    sports = [
        ("nfl", "football/nfl"),
        ("nba", "basketball/nba"),
        ("mlb", "baseball/mlb"),
        ("nhl", "hockey/nhl"),
    ]
    out_rows = []
    for sport_name, path in sports:
        url = f"https://site.api.espn.com/apis/site/v2/sports/{path}/scoreboard"
        t0 = time.time()
        try:
            r = client.get(url, timeout=20.0)
            elapsed_ms = (time.time() - t0) * 1000
        except Exception as e:
            _fail(f"{name}/{sport_name}", str(e))
            continue
        if r.status_code != 200:
            _fail(f"{name}/{sport_name}", f"status={r.status_code}")
            continue
        events = r.json().get("events", [])
        out_rows.append({
            "sport": sport_name,
            "n_events_today": len(events),
            "latency_ms": elapsed_ms,
        })
        _ok(f"{name}/{sport_name}", f"{len(events)} events on scoreboard, latency {elapsed_ms:.0f}ms")
    df = pd.DataFrame(out_rows)
    if not df.empty:
        _save_parquet(df, "espn_scoreboard_summary")
    return {"source": name, "ok": bool(out_rows), "leagues_tested": len(out_rows)}


def probe_odds_api(client: httpx.Client, api_key: str | None) -> dict[str, Any]:
    """The Odds API requires a free-tier key (500 req/month). Without a
    key we can still inspect the public sports list endpoint via the
    documented sample without a key (returns 401 unauthorized though).
    """
    name = "the-odds-api"
    if not api_key:
        # Hit the public docs sports endpoint without key; this confirms reachability and the 401 shape.
        url = "https://api.the-odds-api.com/v4/sports"
        try:
            r = client.get(url, timeout=10.0)
        except Exception as e:
            _fail(name, str(e))
            return {"source": name, "ok": False, "error": str(e)}
        if r.status_code == 401:
            _info(name, "endpoint reachable, requires API key (status 401 as expected)")
            return {"source": name, "ok": False, "reason": "no api key supplied",
                    "next_step": "operator can register at the-odds-api.com for 500 req/mo free"}
        _info(name, f"unexpected status without key: {r.status_code}")
        return {"source": name, "ok": False, "status": r.status_code}
    url = "https://api.the-odds-api.com/v4/sports"
    r = client.get(url, params={"apiKey": api_key}, timeout=10.0)
    if r.status_code != 200:
        _fail(name, f"status={r.status_code}")
        return {"source": name, "ok": False, "status": r.status_code}
    sports = r.json()
    _ok(name, f"{len(sports)} sports listed; sample: {[s.get('key') for s in sports[:5]]}")
    return {"source": name, "ok": True, "n_sports": len(sports)}


def probe_nfl_data_py() -> dict[str, Any]:
    """nfl-data-py is a PyPI library; probe by attempting import and a
    small play-by-play pull. Library is NOT in pyproject deps yet, so
    this probes whether installation/use is feasible."""
    name = "nfl-data-py"
    try:
        import nfl_data_py as nfl  # type: ignore
    except ImportError:
        _info(name, "package not installed; will attempt install")
        # Attempt pip install via uv
        import subprocess
        try:
            res = subprocess.run(
                ["uv", "pip", "install", "nfl-data-py"],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                timeout=180,
            )
            if res.returncode != 0:
                _fail(name, f"install failed: {res.stderr[:300]}")
                return {"source": name, "ok": False, "error": "install failed", "stderr": res.stderr[:300]}
            _info(name, "installed via uv pip")
        except Exception as e:
            _fail(name, f"install exception: {e!s}")
            return {"source": name, "ok": False, "error": str(e)}
        try:
            import nfl_data_py as nfl  # type: ignore
        except ImportError as e:
            _fail(name, f"still cannot import after install: {e!s}")
            return {"source": name, "ok": False, "error": "post-install import failed"}
    # Pull schedules for 2024 (small and fast)
    t0 = time.time()
    try:
        sched = nfl.import_schedules([2024])
    except Exception as e:
        _fail(name, f"import_schedules failed: {e!s}")
        return {"source": name, "ok": False, "error": str(e)}
    elapsed = time.time() - t0
    _ok(name, f"loaded 2024 schedule: {len(sched)} games in {elapsed:.1f}s")
    # Try a tiny play-by-play sample (1 week of 1 season)
    t0 = time.time()
    try:
        # weeks param keeps the download small
        pbp = nfl.import_pbp_data([2024], downcast=True, cache=False)
        elapsed = time.time() - t0
        # subset to a single week to keep parquet small
        small = pbp.head(2000) if len(pbp) > 2000 else pbp
        path = _save_parquet(small.reset_index(drop=True), "nfl_pbp_sample")
        _ok(name, f"play-by-play 2024: {len(pbp)} plays, cols={len(pbp.columns)}, "
                   f"sample {len(small)} saved to {path.name}, latency {elapsed:.1f}s")
        return {"source": name, "ok": True, "n_pbp": int(len(pbp)),
                "n_cols": int(len(pbp.columns)), "load_seconds": elapsed}
    except Exception as e:
        _fail(name, f"pbp pull failed: {e!s}")
        return {"source": name, "ok": False, "error": str(e)}


def probe_pfr_robots(client: httpx.Client) -> dict[str, Any]:
    """Pro-Football-Reference and Basketball-Reference robots.txt + a single page."""
    name = "sports-reference"
    out: dict[str, Any] = {"source": name, "checks": []}
    for sub in ["www.pro-football-reference.com", "www.basketball-reference.com",
                "www.baseball-reference.com"]:
        try:
            r = client.get(f"https://{sub}/robots.txt", timeout=10.0)
            if r.status_code == 200:
                # Look for crawl-delay or relevant disallows
                txt = r.text
                disallow_count = txt.lower().count("disallow:")
                crawl_delay = "crawl-delay" in txt.lower()
                _info(name, f"{sub}: robots.txt OK, disallows={disallow_count}, crawl-delay={crawl_delay}")
                out["checks"].append({"host": sub, "robots_ok": True,
                                       "disallows": disallow_count, "crawl_delay": crawl_delay})
            else:
                _fail(name, f"{sub}: robots status={r.status_code}")
                out["checks"].append({"host": sub, "robots_ok": False, "status": r.status_code})
        except Exception as e:
            _fail(name, f"{sub}: {e!s}")
            out["checks"].append({"host": sub, "robots_ok": False, "error": str(e)})
    return out


def probe_538_archive(client: httpx.Client) -> dict[str, Any]:
    """538 NBA/NFL ELO archives. As of 2023 538 was shut down by Disney/ABC;
    the public CSVs may be gone. Probe known historical URLs."""
    name = "538-archives"
    urls = [
        "https://projects.fivethirtyeight.com/nba-model/nba_elo.csv",
        "https://projects.fivethirtyeight.com/soccer-api/club/spi_matches.csv",
    ]
    out = []
    for url in urls:
        try:
            r = client.get(url, timeout=15.0, follow_redirects=True)
            if r.status_code == 200 and "html" not in r.headers.get("content-type", "").lower():
                # Got real CSV
                size_kb = len(r.content) / 1024
                _ok(name, f"{url} OK ({size_kb:.0f} KB)")
                out.append({"url": url, "ok": True, "size_kb": size_kb})
            else:
                _fail(name, f"{url} status={r.status_code} ctype={r.headers.get('content-type')}")
                out.append({"url": url, "ok": False, "status": r.status_code})
        except Exception as e:
            _fail(name, f"{url}: {e!s}")
            out.append({"url": url, "ok": False, "error": str(e)})
    return {"source": name, "checks": out}


def probe_kalshi_sports_count(args: argparse.Namespace) -> dict[str, Any]:
    """Optional: count active Kalshi sports markets per league. Requires the
    existing READ-scope key. Skip if not requested or if env not set."""
    name = "kalshi-sports-count"
    if not args.include_kalshi:
        _info(name, "skipped (pass --include-kalshi to run)")
        return {"source": name, "skipped": True}
    # Inject the repo src/ so we can import the existing client
    sys.path.insert(0, str(REPO_ROOT / "src"))
    try:
        from kalshi_bot.config import Settings  # type: ignore
        from kalshi_bot.data.kalshi_client import KalshiClient  # type: ignore
        from kalshi_bot.data.sports import classify_market_league  # type: ignore
    except Exception as e:
        _fail(name, f"cannot import existing kalshi_bot modules: {e!s}")
        return {"source": name, "ok": False, "error": str(e)}
    try:
        settings = Settings()
    except Exception as e:
        _fail(name, f"settings init failed: {e!s}")
        return {"source": name, "ok": False, "error": str(e)}
    out_counts: dict[str, int] = {}
    out_status: dict[str, int] = {}
    try:
        with KalshiClient(settings) as client:
            client.ping()
            _info(name, "kalshi auth OK")
            # Pull a sample of active markets in the Sports category
            n = 0
            cap = args.kalshi_sample_cap
            for m in client.paginate(
                "/markets", item_key="markets", limit=100,
                status="active", category="Sports",
            ):
                league = classify_market_league(m)
                out_counts[league] = out_counts.get(league, 0) + 1
                out_status[m.get("status", "?")] = out_status.get(m.get("status", "?"), 0) + 1
                n += 1
                if n >= cap:
                    break
    except Exception as e:
        _fail(name, f"kalshi pull failed: {e!s}")
        return {"source": name, "ok": False, "error": str(e), "partial_counts": out_counts}
    _ok(name, f"sampled {sum(out_counts.values())} active sports markets")
    for league, c in sorted(out_counts.items(), key=lambda kv: -kv[1]):
        print(f"        {league:12s}: {c}")
    # Save
    df = pd.DataFrame([{"league": k, "count": v} for k, v in out_counts.items()])
    if not df.empty:
        _save_parquet(df.sort_values("count", ascending=False), "kalshi_sports_active")
    return {"source": name, "ok": True, "league_counts": out_counts}


def probe_kalshi_historical(args: argparse.Namespace) -> dict[str, Any]:
    """Touch the /historical/cutoff and /historical/markets endpoints with the
    READ-scope key to confirm access shape and date window."""
    name = "kalshi-historical"
    if not args.include_kalshi:
        _info(name, "skipped (pass --include-kalshi to run)")
        return {"source": name, "skipped": True}
    sys.path.insert(0, str(REPO_ROOT / "src"))
    try:
        from kalshi_bot.config import Settings  # type: ignore
        from kalshi_bot.data.kalshi_client import KalshiClient, KalshiHTTPError  # type: ignore
    except Exception as e:
        _fail(name, f"cannot import: {e!s}")
        return {"source": name, "ok": False, "error": str(e)}
    try:
        settings = Settings()
    except Exception as e:
        _fail(name, f"settings init failed: {e!s}")
        return {"source": name, "ok": False, "error": str(e)}
    out: dict[str, Any] = {"source": name}
    try:
        with KalshiClient(settings) as client:
            # 1) historical/cutoff
            try:
                cutoff = client.get("/historical/cutoff")
                _ok(name, f"/historical/cutoff -> {cutoff}")
                out["cutoff"] = cutoff
            except KalshiHTTPError as e:
                _fail(name, f"/historical/cutoff status={e.status} body={e.body[:200]}")
                out["cutoff_error"] = {"status": e.status, "body": e.body[:200]}
            # 2) historical/markets with a small sample
            try:
                hist = client.get("/historical/markets", limit=5)
                keys = list(hist.keys()) if isinstance(hist, dict) else type(hist).__name__
                _ok(name, f"/historical/markets keys={keys}")
                out["hist_markets_keys"] = keys
                if isinstance(hist, dict) and "markets" in hist:
                    out["hist_markets_sample_n"] = len(hist["markets"])
            except KalshiHTTPError as e:
                _fail(name, f"/historical/markets status={e.status} body={e.body[:200]}")
                out["hist_markets_error"] = {"status": e.status, "body": e.body[:200]}
            # 3) historical/trades sample - try a small recent window
            try:
                trades = client.get("/historical/trades", limit=5)
                keys = list(trades.keys()) if isinstance(trades, dict) else type(trades).__name__
                _ok(name, f"/historical/trades keys={keys}")
                out["hist_trades_keys"] = keys
            except KalshiHTTPError as e:
                _fail(name, f"/historical/trades status={e.status} body={e.body[:200]}")
                out["hist_trades_error"] = {"status": e.status, "body": e.body[:200]}
            # 4) endpoint costs to know token cost per request
            try:
                costs = client.get("/account/endpoint_costs")
                _ok(name, "endpoint_costs OK")
                out["endpoint_costs_sample"] = dict(list((costs or {}).get("costs", {}).items())[:5]) \
                    if isinstance(costs, dict) else None
            except KalshiHTTPError as e:
                _fail(name, f"endpoint_costs status={e.status} body={e.body[:200]}")
                out["endpoint_costs_error"] = {"status": e.status, "body": e.body[:200]}
    except Exception as e:
        _fail(name, f"client error: {e!s}")
        out["client_error"] = str(e)
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--include-kalshi", action="store_true",
                        help="Include Kalshi historical + market-count probes (needs .env)")
    parser.add_argument("--include-nfl-data-py", action="store_true",
                        help="Install and probe nfl-data-py (heavy install)")
    parser.add_argument("--kalshi-sample-cap", type=int, default=2000,
                        help="Max number of active sports markets to sample (default 2000)")
    parser.add_argument("--odds-api-key", default=None,
                        help="The Odds API key, optional")
    args = parser.parse_args()
    print("=" * 60)
    print(f"v2 data source probe @ {datetime.now(UTC).isoformat()}")
    print(f"out_dir: {OUT_DIR}")
    print("=" * 60)
    results = []
    with httpx.Client(headers={"User-Agent": "kalshi-v2-probe/0.1"}) as client:
        results.append(probe_mlb_stats_api(client))
        results.append(probe_nba_stats_api(client))
        results.append(probe_espn_api(client))
        results.append(probe_odds_api(client, args.odds_api_key))
        results.append(probe_pfr_robots(client))
        results.append(probe_538_archive(client))
    if args.include_nfl_data_py:
        results.append(probe_nfl_data_py())
    results.append(probe_kalshi_sports_count(args))
    results.append(probe_kalshi_historical(args))
    # Persist all
    summary_path = OUT_DIR / "probe_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump({"timestamp": datetime.now(UTC).isoformat(), "results": results},
                  f, indent=2, default=str)
    print("=" * 60)
    print(f"summary written to {summary_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
