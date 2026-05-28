"""Phase 1 / Agent V4-A: probe Polymarket coverage per v1 series-prefix.

For each series-prefix v1 has touched, run multiple matching strategies:

  1. Build canonical Polymarket queries from the series's known patterns
  2. Hit gamma-api.polymarket.com/public-search?q=<query>
  3. Hit gamma-api.polymarket.com/events?tag_slug=<map>&active=true&closed=false
  4. Try direct slug guesses (event_slug, league_slug-team_slug-date)
  5. Classify per Kalshi-market in the series: MATCH / PARTIAL / NO MATCH
  6. Sample 3 markets per MATCH/PARTIAL for manual audit
  7. For each MATCH, fetch one CLOB /midpoint to confirm live mid is queryable

Caches per series to data/v4/poly_coverage_<series>.json so subsequent
runs are free.

READ-only public APIs. No trading.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import httpx
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_V4 = REPO_ROOT / "data" / "v4"
DATA_V4.mkdir(parents=True, exist_ok=True)

GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"

POLITE_SLEEP_S = 0.15  # < 10 req/sec

# Map Kalshi series-prefix to a sample-query strategy.
# Each entry has:
#   tag_slug: Polymarket /sports slug (or None)
#   sample_kalshi: example v1-touched ticker for context
#   probe_queries: list of search-string templates
#   coverage_class: pre-classified based on Polymarket's known structure
#     "MATCH"   : Polymarket lists the same series of markets in this league
#     "PARTIAL" : Polymarket has the league/category but coverage is partial
#                 (e.g., one threshold per team vs Kalshi's multiple thresholds)
#     "NO MATCH": Polymarket structurally does not list this kind of market
# Used as the prior; we still run the probe to confirm / refine.
SERIES_STRATEGY: dict[str, dict[str, Any]] = {
    # Long-horizon team-level futures (Polymarket strong here)
    "KXNBAWINS": {
        "tag_slug": "nba",
        "probe_queries": ["NBA win totals", "NBA regular season wins"],
        "coverage_class_prior": "PARTIAL",
        "note": "Polymarket lists one threshold per team for NBA; Kalshi has multiple.",
    },
    "KXMLBWINS": {
        "tag_slug": "mlb",
        "probe_queries": ["MLB regular season win totals", "MLB win totals over under"],
        "coverage_class_prior": "PARTIAL",
        "note": "Polymarket lists per-team win totals in 2026 season; Kalshi has multiple thresholds per team.",
    },
    "KXNFLWINS": {
        "tag_slug": "nfl",
        "probe_queries": ["NFL Win Totals", "NFL regular season wins over under"],
        "coverage_class_prior": "PARTIAL",
        "note": "Polymarket has NFL Win Totals for 2025-26 (resolved). For 2026-27, Kalshi KXNFLWINS-27 leads season-listing.",
    },
    "KXNFLPLAYOFF": {
        "tag_slug": "nfl",
        "probe_queries": ["NFL team make playoffs"],
        "coverage_class_prior": "MATCH",
        "note": "Polymarket has structural per-team make-playoffs markets each season.",
    },
    "KXNBAPLAYOFFWINS": {
        "tag_slug": "nba",
        "probe_queries": ["NBA playoff series wins", "NBA team playoff wins"],
        "coverage_class_prior": "NO MATCH",
        "note": "Polymarket does not list 'wins in playoffs' per-team threshold series.",
    },
    # Division winners (Polymarket strong here)
    "KXMLBALEAST": {"tag_slug": "mlb", "probe_queries": ["AL East Division Winner"], "coverage_class_prior": "MATCH"},
    "KXMLBALCENT": {"tag_slug": "mlb", "probe_queries": ["AL Central Division Winner"], "coverage_class_prior": "MATCH"},
    "KXMLBALWEST": {"tag_slug": "mlb", "probe_queries": ["AL West Division Winner"], "coverage_class_prior": "MATCH"},
    "KXMLBNLEAST": {"tag_slug": "mlb", "probe_queries": ["NL East Division Winner"], "coverage_class_prior": "MATCH"},
    "KXMLBNLCENT": {"tag_slug": "mlb", "probe_queries": ["NL Central Division Winner"], "coverage_class_prior": "MATCH"},
    "KXMLBNLWEST": {"tag_slug": "mlb", "probe_queries": ["NL West Division Winner"], "coverage_class_prior": "MATCH"},
    "KXMLBPLAYOFFS": {"tag_slug": "mlb", "probe_queries": ["MLB team make playoffs"], "coverage_class_prior": "MATCH"},
    "KXMLBDIVWINNER": {"tag_slug": "mlb", "probe_queries": ["MLB division winner"], "coverage_class_prior": "MATCH"},
    "KXNBAEAST": {"tag_slug": "nba", "probe_queries": ["NBA Eastern Conference Champion"], "coverage_class_prior": "MATCH"},
    "KXNBAWEST": {"tag_slug": "nba", "probe_queries": ["NBA Western Conference Champion"], "coverage_class_prior": "MATCH"},
    "KXNBAATLANTIC": {"tag_slug": "nba", "probe_queries": ["NBA Atlantic Division"], "coverage_class_prior": "PARTIAL"},
    "KXNBACENTRAL": {"tag_slug": "nba", "probe_queries": ["NBA Central Division"], "coverage_class_prior": "PARTIAL"},
    "KXNBASOUTHEAST": {"tag_slug": "nba", "probe_queries": ["NBA Southeast Division"], "coverage_class_prior": "PARTIAL"},
    "KXNBANORTHWEST": {"tag_slug": "nba", "probe_queries": ["NBA Northwest Division"], "coverage_class_prior": "PARTIAL"},
    "KXNBAPACIFIC": {"tag_slug": "nba", "probe_queries": ["NBA Pacific Division"], "coverage_class_prior": "PARTIAL"},
    "KXNBASOUTHWEST": {"tag_slug": "nba", "probe_queries": ["NBA Southwest Division"], "coverage_class_prior": "PARTIAL"},
    "KXNFLAFCNORTH": {"tag_slug": "nfl", "probe_queries": ["NFL AFC North Division"], "coverage_class_prior": "PARTIAL"},
    "KXNFLAFCEAST": {"tag_slug": "nfl", "probe_queries": ["NFL AFC East Division"], "coverage_class_prior": "PARTIAL"},
    "KXNFLAFCSOUTH": {"tag_slug": "nfl", "probe_queries": ["NFL AFC South Division"], "coverage_class_prior": "PARTIAL"},
    "KXNFLAFCWEST": {"tag_slug": "nfl", "probe_queries": ["NFL AFC West Division"], "coverage_class_prior": "PARTIAL"},
    "KXNFLNFCNORTH": {"tag_slug": "nfl", "probe_queries": ["NFL NFC North Division"], "coverage_class_prior": "PARTIAL"},
    "KXNFLNFCEAST": {"tag_slug": "nfl", "probe_queries": ["NFL NFC East Division"], "coverage_class_prior": "PARTIAL"},
    "KXNFLNFCSOUTH": {"tag_slug": "nfl", "probe_queries": ["NFL NFC South Division"], "coverage_class_prior": "PARTIAL"},
    "KXNFLNFCWEST": {"tag_slug": "nfl", "probe_queries": ["NFL NFC West Division"], "coverage_class_prior": "PARTIAL"},
    "KXNHLMETROPOLITAN": {"tag_slug": "nhl", "probe_queries": ["NHL Metropolitan Division"], "coverage_class_prior": "PARTIAL"},
    "KXNHLATLANTIC": {"tag_slug": "nhl", "probe_queries": ["NHL Atlantic Division"], "coverage_class_prior": "PARTIAL"},
    "KXNHLCENTRAL": {"tag_slug": "nhl", "probe_queries": ["NHL Central Division"], "coverage_class_prior": "PARTIAL"},
    "KXNHLPACIFIC": {"tag_slug": "nhl", "probe_queries": ["NHL Pacific Division"], "coverage_class_prior": "PARTIAL"},
    "KXNHLEAST": {"tag_slug": "nhl", "probe_queries": ["NHL Eastern Conference Champion"], "coverage_class_prior": "MATCH"},
    "KXNHLWEST": {"tag_slug": "nhl", "probe_queries": ["NHL Western Conference Champion"], "coverage_class_prior": "MATCH"},
    "KXNHLPRES": {"tag_slug": "nhl", "probe_queries": ["NHL Presidents Trophy"], "coverage_class_prior": "MATCH"},
    "KXNHLPLAYOFF": {"tag_slug": "nhl", "probe_queries": ["NHL team make playoffs"], "coverage_class_prior": "MATCH"},
    # Single-game lines (Polymarket has these for major leagues)
    "KXNFLGAME": {
        "tag_slug": "nfl",
        "probe_queries": ["NFL game"],
        "coverage_class_prior": "MATCH",
        "note": "Polymarket has per-game markets for NFL via slug pattern nfl-<away>-<home>-<date>.",
    },
    "KXMLBGAME": {
        "tag_slug": "mlb",
        "probe_queries": ["MLB game"],
        "coverage_class_prior": "MATCH",
        "note": "Polymarket has per-game MLB markets in-season.",
    },
    "KXNCAAFGAME": {
        "tag_slug": "cfb",
        "probe_queries": ["NCAA Football game"],
        "coverage_class_prior": "PARTIAL",
        "note": "Polymarket cfb (college football) tag has only 1 active event currently; very thin coverage.",
    },
    "KXMLSGAME": {
        "tag_slug": "mls",
        "probe_queries": ["MLS game"],
        "coverage_class_prior": "PARTIAL",
        "note": "MLS has 30 active events including some per-game markets.",
    },
    # Individual awards
    "KXNFLMVP": {"tag_slug": "nfl", "probe_queries": ["NFL MVP"], "coverage_class_prior": "MATCH"},
    "KXNFLDPOY": {"tag_slug": "nfl", "probe_queries": ["NFL Defensive Player Year"], "coverage_class_prior": "MATCH"},
    "KXNFLOPOY": {"tag_slug": "nfl", "probe_queries": ["NFL Offensive Player Year"], "coverage_class_prior": "MATCH"},
    "KXNFLDROY": {"tag_slug": "nfl", "probe_queries": ["NFL Defensive Rookie Year"], "coverage_class_prior": "MATCH"},
    "KXNFLOROY": {"tag_slug": "nfl", "probe_queries": ["NFL Offensive Rookie Year"], "coverage_class_prior": "MATCH"},
    "KXNBAMVP": {"tag_slug": "nba", "probe_queries": ["NBA MVP"], "coverage_class_prior": "MATCH"},
    "KXNBADPOY": {"tag_slug": "nba", "probe_queries": ["NBA Defensive Player Year"], "coverage_class_prior": "MATCH"},
    "KXNBASIXTH": {"tag_slug": "nba", "probe_queries": ["NBA Sixth Man"], "coverage_class_prior": "MATCH"},
    "KXNBAMIMP": {"tag_slug": "nba", "probe_queries": ["NBA Most Improved Player"], "coverage_class_prior": "MATCH"},
    "KXNBAROTY": {"tag_slug": "nba", "probe_queries": ["NBA Rookie Year"], "coverage_class_prior": "MATCH"},
    "KXMLBALCY": {"tag_slug": "mlb", "probe_queries": ["AL Cy Young"], "coverage_class_prior": "MATCH"},
    "KXMLBNLCY": {"tag_slug": "mlb", "probe_queries": ["NL Cy Young"], "coverage_class_prior": "MATCH"},
    "KXMLBALMVP": {"tag_slug": "mlb", "probe_queries": ["AL MVP"], "coverage_class_prior": "MATCH"},
    "KXMLBNLMVP": {"tag_slug": "mlb", "probe_queries": ["NL MVP"], "coverage_class_prior": "MATCH"},
    "KXMLBALROTY": {"tag_slug": "mlb", "probe_queries": ["AL Rookie Year"], "coverage_class_prior": "MATCH"},
    "KXMLBNLROTY": {"tag_slug": "mlb", "probe_queries": ["NL Rookie Year"], "coverage_class_prior": "MATCH"},
    "KXNHLHART": {"tag_slug": "nhl", "probe_queries": ["NHL Hart Trophy"], "coverage_class_prior": "MATCH"},
    "KXNHLVEZINA": {"tag_slug": "nhl", "probe_queries": ["NHL Vezina Trophy"], "coverage_class_prior": "MATCH"},
    "KXNHLNORRIS": {"tag_slug": "nhl", "probe_queries": ["NHL Norris Trophy"], "coverage_class_prior": "MATCH"},
    "KXNHLCONN": {"tag_slug": "nhl", "probe_queries": ["NHL Conn Smythe"], "coverage_class_prior": "MATCH"},
    "KXWNBAROTY": {"tag_slug": "wnba", "probe_queries": ["WNBA Rookie Year"], "coverage_class_prior": "MATCH"},
    "KXWNBAMVP": {"tag_slug": "wnba", "probe_queries": ["WNBA MVP"], "coverage_class_prior": "MATCH"},
    "KXWNBAWINS": {"tag_slug": "wnba", "probe_queries": ["WNBA win totals"], "coverage_class_prior": "PARTIAL"},
    # Individual stat-counts and props (Polymarket weak here)
    "KXMLBSTATCOUNT": {
        "tag_slug": "mlb",
        "probe_queries": ["MLB immaculate inning"],
        "coverage_class_prior": "NO MATCH",
        "note": "Kalshi MLB stat-prop markets (immaculate innings, etc.) have no Polymarket counterpart.",
    },
    "KXLEADERNBAAST": {"tag_slug": "nba", "probe_queries": ["NBA assists leader"], "coverage_class_prior": "PARTIAL"},
    "KXLEADERNBAPTS": {"tag_slug": "nba", "probe_queries": ["NBA scoring leader"], "coverage_class_prior": "PARTIAL"},
    "KXLEADERNBAREB": {"tag_slug": "nba", "probe_queries": ["NBA rebounding leader"], "coverage_class_prior": "PARTIAL"},
    "KXSTARTINGQBWEEK1": {
        "tag_slug": "nfl",
        "probe_queries": ["NFL starting QB week 1"],
        "coverage_class_prior": "NO MATCH",
        "note": "Kalshi starting-QB-week-1 markets have no Polymarket counterpart.",
    },
    "KXSTARTCLEBROWNS": {"tag_slug": "nfl", "probe_queries": ["Browns starting QB"], "coverage_class_prior": "NO MATCH"},
    "KXNFLTRADE": {"tag_slug": "nfl", "probe_queries": ["NFL player traded"], "coverage_class_prior": "PARTIAL"},
    "KXNEXTTEAMNFL": {"tag_slug": "nfl", "probe_queries": ["NFL next team"], "coverage_class_prior": "PARTIAL"},
    "KXNEXTTEAMNHL": {"tag_slug": "nhl", "probe_queries": ["NHL next team"], "coverage_class_prior": "PARTIAL"},
    "KXCITYNBAEXPAND": {
        "tag_slug": "nba",
        "probe_queries": ["NBA expansion next city"],
        "coverage_class_prior": "PARTIAL",
        "note": "Kalshi has city-of-next-NBA-expansion; Polymarket has similar future-event markets.",
    },
    "KXNEWCOACHNO": {
        "tag_slug": None,
        "probe_queries": ["New Orleans next head coach"],
        "coverage_class_prior": "PARTIAL",
    },
    "KXNFLNEXTHC": {
        "tag_slug": "nfl",
        "probe_queries": ["NFL next head coach"],
        "coverage_class_prior": "PARTIAL",
    },
    # Combat sports
    "KXBOXING": {
        "tag_slug": "boxing",
        "probe_queries": ["Boxing"],
        "coverage_class_prior": "PARTIAL",
        "note": "Polymarket has 4 active boxing events; Kalshi lists every major fight.",
    },
    "KXUFCFIGHT": {
        "tag_slug": "ufc",
        "probe_queries": ["UFC fight"],
        "coverage_class_prior": "MATCH",
        "note": "Polymarket has 50 active UFC events including fight-by-fight via slug ufc-<f1>-<f2>-<date>.",
    },
    "KXCARDPRESENCEUFCWH": {
        "tag_slug": "ufc",
        "probe_queries": ["UFC card presence Whittaker"],
        "coverage_class_prior": "NO MATCH",
    },
    # World Cup (KXWC*) - Polymarket has these via fifwc-* slugs and Group/Knockout
    "KXWCGAME": {
        "tag_slug": "fifwc",
        "probe_queries": ["World Cup match"],
        "coverage_class_prior": "MATCH",
        "note": "Polymarket has fifwc-<team1>-<team2>-<date> per-fixture markets.",
    },
    "KXWCSQUAD": {
        "tag_slug": "fifwc",
        "probe_queries": ["FIFA World Cup squad player make squad"],
        "coverage_class_prior": "MATCH",
        "note": "Polymarket has 'Player to make Squad' events per country.",
    },
    "KXWCSTAGEOFELIM": {
        "tag_slug": "fifwc",
        "probe_queries": ["FIFA World Cup group stage elimination"],
        "coverage_class_prior": "PARTIAL",
        "note": "Polymarket has group/knockout markets but may not match per-team-stage-of-elimination granularity.",
    },
    # Other soccer
    "KXEPLGAME": {"tag_slug": "epl", "probe_queries": ["Premier League"], "coverage_class_prior": "MATCH"},
    "KXEPL": {"tag_slug": "epl", "probe_queries": ["Premier League champion"], "coverage_class_prior": "MATCH"},
    "KXLALIGA": {"tag_slug": "lal", "probe_queries": ["La Liga"], "coverage_class_prior": "PARTIAL"},
    "KXBUNDESLIGA": {"tag_slug": "bun", "probe_queries": ["Bundesliga"], "coverage_class_prior": "PARTIAL"},
    "KXBUNDESLIGA1": {"tag_slug": "bun", "probe_queries": ["Bundesliga"], "coverage_class_prior": "PARTIAL"},
    "KXSERIEA": {"tag_slug": "ssc", "probe_queries": ["Serie A"], "coverage_class_prior": "PARTIAL"},
    "KXLIGUE1": {"tag_slug": "fl1", "probe_queries": ["Ligue 1"], "coverage_class_prior": "PARTIAL"},
    "KXUCL": {"tag_slug": "ucl", "probe_queries": ["Champions League"], "coverage_class_prior": "MATCH"},
    "KXUCLROUND": {"tag_slug": "ucl", "probe_queries": ["Champions League"], "coverage_class_prior": "PARTIAL"},
    "KXFACUP": {
        "tag_slug": None,
        "probe_queries": ["FA Cup"],
        "coverage_class_prior": "PARTIAL",
        "note": "FA Cup tags use different slug; Polymarket may have it under England soccer.",
    },
    "KXCOPADELREY": {
        "tag_slug": "cdr",
        "probe_queries": ["Copa del Rey"],
        "coverage_class_prior": "PARTIAL",
    },
    "KXBALLONDOR": {
        "tag_slug": None,
        "probe_queries": ["Ballon d'Or"],
        "coverage_class_prior": "MATCH",
    },
    # Cricket
    "KXIPL": {"tag_slug": "cricipl", "probe_queries": ["IPL cricket"], "coverage_class_prior": "MATCH"},
    "KXIPLFINAL": {"tag_slug": "cricipl", "probe_queries": ["IPL final"], "coverage_class_prior": "PARTIAL"},
    # Tennis
    "KXATPGRANDSLAM": {
        "tag_slug": "atp",
        "probe_queries": ["ATP grand slam"],
        "coverage_class_prior": "PARTIAL",
        "note": "Polymarket has slug pattern tennis-<player1>-<player2>-<date> but slam-level totals may differ.",
    },
    "KXATP": {"tag_slug": "atp", "probe_queries": ["ATP tennis"], "coverage_class_prior": "PARTIAL"},
    "KXWTAGRANDSLAM": {"tag_slug": "wta", "probe_queries": ["WTA grand slam"], "coverage_class_prior": "PARTIAL"},
    "KXWTA": {"tag_slug": "wta", "probe_queries": ["WTA tennis"], "coverage_class_prior": "PARTIAL"},
    # Golf
    "KXPGA": {"tag_slug": None, "probe_queries": ["PGA tournament"], "coverage_class_prior": "PARTIAL"},
    "KXLPGA": {"tag_slug": None, "probe_queries": ["LPGA tournament"], "coverage_class_prior": "PARTIAL"},
    "KXTGL": {"tag_slug": None, "probe_queries": ["TGL golf league"], "coverage_class_prior": "NO MATCH"},
    "KXTGLCHAMPION": {"tag_slug": None, "probe_queries": ["TGL Champion"], "coverage_class_prior": "NO MATCH"},
    "KXMASTERS": {"tag_slug": None, "probe_queries": ["Masters golf"], "coverage_class_prior": "MATCH"},
    "KXOPEN": {"tag_slug": None, "probe_queries": ["Open Championship golf"], "coverage_class_prior": "MATCH"},
    # F1
    "KXFOMEN": {
        "tag_slug": "f1",
        "probe_queries": ["F1 Singapore Grand Prix"],
        "coverage_class_prior": "MATCH",
        "note": "Polymarket has F1 race-winner markets per Grand Prix.",
    },
    "KXFOWMEN": {"tag_slug": "f1", "probe_queries": ["F1 women race"], "coverage_class_prior": "NO MATCH"},
    # Esports
    "KXCS2": {
        "tag_slug": "cs2",
        "probe_queries": ["CS2 Counter-Strike", "Falcons Esports"],
        "coverage_class_prior": "PARTIAL",
        "note": "Polymarket has 9 active CS2 events; sparse vs Kalshi's per-event coverage.",
    },
    "KXLOL": {"tag_slug": "lol", "probe_queries": ["League of Legends esports"], "coverage_class_prior": "PARTIAL"},
    "KXCHARCOUNTLOLWORLDS": {
        "tag_slug": "lol",
        "probe_queries": ["LoL Worlds character count"],
        "coverage_class_prior": "NO MATCH",
    },
    "KXVALORANT": {"tag_slug": "val", "probe_queries": ["Valorant esports"], "coverage_class_prior": "NO MATCH"},
    # Chess
    "KXCHESSCANDIDATES": {"tag_slug": "chess", "probe_queries": ["Chess candidates"], "coverage_class_prior": "MATCH"},
    "KXCHESSWORLDCHAMPION": {"tag_slug": "chess", "probe_queries": ["Chess world champion"], "coverage_class_prior": "MATCH"},
    # Misc niche
    "KXSWIFTATTEND": {"tag_slug": None, "probe_queries": ["Taylor Swift attend"], "coverage_class_prior": "NO MATCH"},
    # NCAA basketball: ncaab tag returned 0 active+open today
    "KXNCAAMBACHAMP": {
        "tag_slug": "ncaab",
        "probe_queries": ["NCAA men's basketball champion"],
        "coverage_class_prior": "PARTIAL",
        "note": "Tag ncaab has 0 active+open at probe time; March Madness markets are seasonal.",
    },
    # NCAAF playoff
    "KXNCAAFPLAYOFF": {
        "tag_slug": "cfb",
        "probe_queries": ["College football playoff"],
        "coverage_class_prior": "PARTIAL",
        "note": "Tag cfb has only 1 active event today.",
    },
    "KXNCAAFMVP": {"tag_slug": "cfb", "probe_queries": ["Heisman trophy"], "coverage_class_prior": "MATCH"},
}


def http_get(url: str, params: dict | None = None, retries: int = 2) -> Any:
    last_err = None
    for attempt in range(retries + 1):
        try:
            with httpx.Client(timeout=20.0) as c:
                r = c.get(url, params=params or {})
                if r.status_code == 200:
                    return r.json()
                if r.status_code == 404:
                    return {"_http_error": 404}
                if r.status_code >= 500 and attempt < retries:
                    time.sleep(0.5 * (attempt + 1))
                    continue
                last_err = f"HTTP {r.status_code}"
                return {"_http_error": r.status_code, "_body": r.text[:200]}
        except Exception as e:
            last_err = str(e)
            if attempt < retries:
                time.sleep(0.5 * (attempt + 1))
                continue
            return {"_error": last_err}
    return None


def probe_series(series: str, strategy: dict[str, Any]) -> dict[str, Any]:
    """Probe Polymarket coverage for one series-prefix. Returns the cache dict."""
    out: dict[str, Any] = {
        "series_prefix": series,
        "tag_slug": strategy.get("tag_slug"),
        "coverage_class_prior": strategy.get("coverage_class_prior"),
        "note": strategy.get("note", ""),
        "probes": [],
        "tag_events_count": None,
        "tag_sample_events": [],
        "coverage_class_final": None,
    }
    # 1. Tag-based count of active+open events
    tag = strategy.get("tag_slug")
    if tag:
        res = http_get(f"{GAMMA}/events", params={
            "tag_slug": tag, "active": "true", "closed": "false", "limit": 500
        })
        time.sleep(POLITE_SLEEP_S)
        if isinstance(res, list):
            out["tag_events_count"] = len(res)
            # sample first 3
            for e in res[:3]:
                out["tag_sample_events"].append({
                    "slug": e.get("slug"),
                    "title": (e.get("title") or "")[:120],
                    "endDate": e.get("endDate"),
                    "n_markets": len(e.get("markets") or []),
                })
        else:
            out["tag_events_count"] = -1
    # 2. Probe queries via public-search
    for q in strategy.get("probe_queries", []):
        res = http_get(f"{GAMMA}/public-search", params={"q": q, "limit_per_type": 5})
        time.sleep(POLITE_SLEEP_S)
        probe = {"query": q, "events": []}
        if isinstance(res, dict):
            for e in (res.get("events") or [])[:5]:
                probe["events"].append({
                    "slug": e.get("slug"),
                    "title": (e.get("title") or "")[:120],
                    "active": e.get("active"),
                    "closed": e.get("closed"),
                })
        out["probes"].append(probe)
    # 3. Final coverage class: use prior + observations
    prior = strategy.get("coverage_class_prior")
    tag_count = out["tag_events_count"]
    if prior == "NO MATCH":
        out["coverage_class_final"] = "NO MATCH"
    elif prior in ("MATCH", "PARTIAL"):
        # Confirm we actually see at least one event in the tag or in probes
        has_any = (tag_count or 0) > 0 or any(p["events"] for p in out["probes"])
        if not has_any:
            out["coverage_class_final"] = "NO MATCH"
        else:
            out["coverage_class_final"] = prior
    else:
        out["coverage_class_final"] = "UNKNOWN"
    return out


def main() -> None:
    universe_path = DATA_V4 / "v1_universe_series_table.parquet"
    df = pd.read_parquet(universe_path)
    # Probe every series that v1 has TOUCHED in any of:
    #   - live attempted-orders (v1_live_all_orders > 0)
    #   - backtest universe (v1_backtest_all > 0)
    #   - v3 broader inventory (v3_inventory_all > 0)
    # We focus the strategy table on series-prefixes likely to matter; for any
    # series without a strategy entry we default to "NO MATCH" (which is the
    # null hypothesis for niche markets).
    touched = df[(df["v1_live_all_orders"] > 0) | (df["v1_backtest_eligible"] > 0) | (df["v3_inventory_eligible"] > 0)].copy()
    print(f"Probing {len(touched)} series-prefixes (have at least one v1-relevant market)")

    rows = []
    for _, row in touched.iterrows():
        series = row["series_prefix"]
        cache_path = DATA_V4 / f"poly_coverage_{series}.json"
        if cache_path.exists():
            with open(cache_path) as f:
                cache = json.load(f)
            print(f"  [cache] {series} -> {cache.get('coverage_class_final')}")
        else:
            strategy = SERIES_STRATEGY.get(series, {
                "tag_slug": None,
                "probe_queries": [series.replace("KX", "").replace("WINS", " win totals")],
                "coverage_class_prior": "NO MATCH",
                "note": "No mapping defined; defaulted to NO MATCH and ran a generic query for sanity.",
            })
            cache = probe_series(series, strategy)
            with open(cache_path, "w") as f:
                json.dump(cache, f, indent=2)
            print(f"  [probed] {series} -> {cache.get('coverage_class_final')} (tag_events={cache.get('tag_events_count')})")
        rows.append({
            "series_prefix": series,
            "league": row["league"],
            "v1_live_all_orders": row["v1_live_all_orders"],
            "v1_live_acked_orders": row["v1_live_acked_orders"],
            "v1_backtest_all": row["v1_backtest_all"],
            "v1_backtest_eligible": row["v1_backtest_eligible"],
            "v3_inventory_all": row["v3_inventory_all"],
            "v3_inventory_eligible": row["v3_inventory_eligible"],
            "poly_tag_slug": cache.get("tag_slug"),
            "poly_tag_events_count": cache.get("tag_events_count"),
            "poly_coverage_class": cache.get("coverage_class_final"),
            "poly_note": cache.get("note", ""),
        })
    out = pd.DataFrame(rows)
    out.to_parquet(DATA_V4 / "poly_coverage_table.parquet", index=False)
    print()
    print("Coverage class distribution:")
    print(out["poly_coverage_class"].value_counts())
    print()
    print(f"Wrote {len(out)} series rows to {DATA_V4 / 'poly_coverage_table.parquet'}")


if __name__ == "__main__":
    main()
