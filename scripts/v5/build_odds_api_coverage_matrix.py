"""V5-A1: build per-series coverage matrix mapping Kalshi series-prefixes
to the-odds-api sport_key + markets parameters.

Uses ZERO live-odds credits (only the FREE /v4/sports and /v4/events
endpoints). For each post-denylist Kalshi series-prefix v1 has touched,
classify coverage as:
  - MATCH: the-odds-api has an exact event-class counterpart with the
    needed market_type (h2h for game outcomes, outrights for futures).
  - PARTIAL: same league but Kalshi's specific market type is not
    available (e.g. KXNBAPLAYOFFWINS team-playoff-wins thresholds; the
    sportsbooks list team championship futures, not playoff-win
    thresholds).
  - NO MATCH: league not in the catalog OR market type fundamentally
    unavailable (e.g. KXMLBSTATCOUNT immaculate-inning props are not a
    standard sportsbook market).

Output:
  - data/v5/odds_api_coverage_per_series.json: list of dicts per series.
  - data/v5/odds_api_coverage_per_series.parquet: same as table.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parents[2]
UNIVERSE = ROOT / "data" / "v5" / "v1_post_denylist_universe.parquet"
SPORTS_CACHE = ROOT / "data" / "v5" / "odds_api_sports.json"
OUT_JSON = ROOT / "data" / "v5" / "odds_api_coverage_per_series.json"
OUT_PARQUET = ROOT / "data" / "v5" / "odds_api_coverage_per_series.parquet"
EVENTS_CACHE = ROOT / "data" / "v5" / "odds_api_events_cache"
EVENTS_CACHE.mkdir(parents=True, exist_ok=True)

BASE = "https://api.the-odds-api.com/v4"
KEY = os.environ.get("THE_ODDS_API_KEY", "")
THROTTLE_SEC = 1.1  # < 1 req/sec per project constraint


# Mapping from Kalshi series-prefix to:
#   sport_keys: list of the-odds-api sport keys that cover this series
#   market_type: 'h2h' (head-to-head game) | 'outrights' (futures)
#                | 'spreads_totals' (line markets) | 'player_props'
#                | 'none' (no sportsbook counterpart)
#   coverage_class: MATCH | PARTIAL | NO_MATCH
#   notes: explanation
SERIES_MAP: dict[str, dict] = {
    # ===== MLB =====
    "KXMLBWINS": {
        "sport_keys": ["baseball_mlb"],
        "market_type": "spreads_totals",
        "coverage_class": "PARTIAL",
        "notes": (
            "Kalshi lists per-team season win-total thresholds (T70,T75,T80,...). "
            "Sportsbooks list ONE season-win-total per team. Conversion via "
            "monotonicity required (same gap V4-A documented for Polymarket)."
        ),
    },
    "KXMLBPLAYOFFS": {  # denylisted
        "sport_keys": ["baseball_mlb"],
        "market_type": "outrights",
        "coverage_class": "PARTIAL",
        "notes": "Denylisted by W1. Coverage moot.",
    },
    "KXMLBSTATCOUNT": {
        "sport_keys": ["baseball_mlb"],
        "market_type": "player_props",
        "coverage_class": "NO_MATCH",
        "notes": (
            "Immaculate-inning prop is not a standard sportsbook market type. "
            "Player_pitching_strikeouts exists, but Kalshi's STATCOUNT props "
            "are typically specific count thresholds (e.g., '3+ pitches in inning')."
        ),
    },
    "KXMLBALROTY": {
        "sport_keys": ["baseball_mlb"],
        "market_type": "outrights",
        "coverage_class": "PARTIAL",
        "notes": (
            "Sportsbooks list AL Rookie of the Year futures but coverage by "
            "the-odds-api requires special outright sport_key (not in default "
            "baseball_mlb)."
        ),
    },

    # ===== NBA / WNBA =====
    "KXNBAWINS": {
        "sport_keys": ["basketball_nba"],
        "market_type": "spreads_totals",
        "coverage_class": "PARTIAL",
        "notes": (
            "Same as MLB: sportsbooks list per-team season win-total once; "
            "Kalshi lists multiple thresholds per team. Monotonicity translation."
        ),
    },
    "KXNBAPLAYOFFWINS": {
        "sport_keys": ["basketball_nba"],
        "market_type": "outrights",
        "coverage_class": "NO_MATCH",
        "notes": (
            "Team-playoff-wins threshold (e.g., 'OKC playoff wins >= 15') is "
            "NOT a standard sportsbook futures market. Closest is championship "
            "futures (basketball_nba_championship_winner) which is a different "
            "claim. Same NO_MATCH as Polymarket per V4-A."
        ),
    },
    "KXCITYNBAEXPAND": {
        "sport_keys": [],
        "market_type": "none",
        "coverage_class": "NO_MATCH",
        "notes": "NBA expansion city votes are not a sportsbook market.",
    },
    "KXLEADERNBAAST": {
        "sport_keys": ["basketball_nba"],
        "market_type": "outrights",
        "coverage_class": "PARTIAL",
        "notes": "Season assist leader futures exist on sportsbooks but require dedicated outright keys.",
    },
    "KXWNBAWINS": {
        "sport_keys": ["basketball_wnba"],
        "market_type": "spreads_totals",
        "coverage_class": "PARTIAL",
        "notes": "WNBA season win-totals available; threshold-mismatch with Kalshi same as NBA.",
    },

    # ===== NFL =====
    "KXNFLWINS": {  # denylisted
        "sport_keys": ["americanfootball_nfl"],
        "market_type": "spreads_totals",
        "coverage_class": "PARTIAL",
        "notes": "Denylisted by W1. Coverage moot.",
    },
    "KXNFLPLAYOFF": {  # denylisted
        "sport_keys": ["americanfootball_nfl"],
        "market_type": "outrights",
        "coverage_class": "PARTIAL",
        "notes": "Denylisted by W1.",
    },
    "KXNFLGAME": {
        "sport_keys": ["americanfootball_nfl"],
        "market_type": "h2h",
        "coverage_class": "MATCH",
        "notes": (
            "Game-resolution market. h2h moneyline is the canonical sportsbook "
            "equivalent. Direct comparison possible after de-vigging."
        ),
    },
    "KXSTARTINGQBWEEK1": {
        "sport_keys": [],
        "market_type": "player_props",
        "coverage_class": "NO_MATCH",
        "notes": (
            "Week-1 starting QB identity is not a standard sportsbook market. "
            "Some books list 'first pass attempt by player X' props but the "
            "claim differs. NO_MATCH on the-odds-api default markets."
        ),
    },
    "KXNEXTTEAMNFL": {
        "sport_keys": ["americanfootball_nfl"],
        "market_type": "outrights",
        "coverage_class": "PARTIAL",
        "notes": "Some books list 'next team' for marquee free agents; coverage on the-odds-api default markets is limited.",
    },
    "KXNFLTRADE": {
        "sport_keys": [],
        "market_type": "none",
        "coverage_class": "NO_MATCH",
        "notes": "Player trade prop not standard sportsbook market.",
    },
    "KXSTARTCLEBROWNS": {
        "sport_keys": [],
        "market_type": "none",
        "coverage_class": "NO_MATCH",
        "notes": "Specific team-coaching/QB-start prop not standard sportsbook market.",
    },

    # ===== NCAA-FB =====
    "KXNCAAFGAME": {
        "sport_keys": ["americanfootball_ncaaf"],
        "market_type": "h2h",
        "coverage_class": "MATCH",
        "notes": "h2h game line; direct comparison.",
    },
    "KXNCAAFPLAYOFF": {
        "sport_keys": ["americanfootball_ncaaf_championship_winner"],
        "market_type": "outrights",
        "coverage_class": "MATCH",
        "notes": "CFB championship/playoff outright winner. Direct match.",
    },

    # ===== Soccer =====
    "KXWCGAME": {
        "sport_keys": ["soccer_fifa_world_cup"],
        "market_type": "h2h",
        "coverage_class": "MATCH",
        "notes": "World Cup match outcome via h2h. Note: book may show draw as separate outcome (3-way market).",
    },
    "KXWCSQUAD": {
        "sport_keys": [],
        "market_type": "player_props",
        "coverage_class": "NO_MATCH",
        "notes": (
            "Player squad selection is a structural Kalshi-specific prop. "
            "Some books offer 'will player X make the squad' specials but "
            "rarely; not on the-odds-api default markets."
        ),
    },
    "KXWCSTAGEOFELIM": {
        "sport_keys": ["soccer_fifa_world_cup_winner"],
        "market_type": "outrights",
        "coverage_class": "PARTIAL",
        "notes": (
            "WC outright winner futures listed; per-team 'stage of elimination' "
            "is a separate prop usually under 'World Cup specials' that "
            "the-odds-api may not enumerate. Conversion via monotonicity "
            "(P(win) -> implied stage probabilities) is loose."
        ),
    },
    "KXEPLGAME": {
        "sport_keys": ["soccer_epl"],
        "market_type": "h2h",
        "coverage_class": "MATCH",
        "notes": "EPL game h2h (3-way: home/draw/away).",
    },
    "KXMLSGAME": {
        "sport_keys": ["soccer_usa_mls"],
        "market_type": "h2h",
        "coverage_class": "MATCH",
        "notes": "MLS game h2h.",
    },
    "KXLALIGA": {
        "sport_keys": ["soccer_spain_la_liga"],
        "market_type": "h2h",
        "coverage_class": "MATCH",
        "notes": "La Liga h2h.",
    },
    "KXUCL": {
        "sport_keys": ["soccer_uefa_champs_league"],
        "market_type": "h2h",
        "coverage_class": "MATCH",
        "notes": "UEFA Champions League games via h2h.",
    },
    "KXUCLROUND": {
        "sport_keys": ["soccer_uefa_champs_league"],
        "market_type": "outrights",
        "coverage_class": "PARTIAL",
        "notes": "UCL round-of-elimination outright less commonly listed; partial.",
    },
    "KXBALLONDOR": {
        "sport_keys": [],
        "market_type": "outrights",
        "coverage_class": "NO_MATCH",
        "notes": "Ballon d'Or futures exist on books but are NOT in the-odds-api default soccer sport keys.",
    },

    # ===== UCL specials -> separate from regular soccer leagues
    # ===== Combat sports =====
    "KXUFCFIGHT": {
        "sport_keys": ["mma_mixed_martial_arts"],
        "market_type": "h2h",
        "coverage_class": "MATCH",
        "notes": "UFC fight h2h.",
    },
    "KXBOXING": {
        "sport_keys": ["boxing_boxing"],
        "market_type": "h2h",
        "coverage_class": "MATCH",
        "notes": "Boxing fight h2h.",
    },

    # ===== Tennis =====
    "KXATPGRANDSLAM": {
        "sport_keys": [
            "tennis_atp_french_open",
            "tennis_atp_wimbledon",
            "tennis_atp_us_open",
            "tennis_atp_aus_open",
        ],
        "market_type": "outrights",
        "coverage_class": "MATCH",
        "notes": (
            "Grand slam winner futures. Specific tournament keys vary by season; "
            "the-odds-api lists in-season tournaments only."
        ),
    },

    # ===== F1 =====
    "KXFOMEN": {
        "sport_keys": [],
        "market_type": "outrights",
        "coverage_class": "NO_MATCH",
        "notes": (
            "F1 race winner or championship futures exist on most major books, "
            "but the-odds-api does NOT enumerate F1 by default. (Cross-check "
            "with /v4/sports.) NO_MATCH on the-odds-api specifically; data "
            "exists on individual sportsbooks but not via this aggregator."
        ),
    },

    # ===== Esports =====
    "KXCS2": {
        "sport_keys": [],
        "market_type": "h2h",
        "coverage_class": "NO_MATCH",
        "notes": "CS2 / Esports outside the-odds-api scope.",
    },
    "KXCHARCOUNTLOLWORLDS": {
        "sport_keys": [],
        "market_type": "h2h",
        "coverage_class": "NO_MATCH",
        "notes": "LoL Worlds outside the-odds-api scope.",
    },

    # ===== NHL =====
    "KXNEXTTEAMNHL": {
        "sport_keys": [],
        "market_type": "outrights",
        "coverage_class": "NO_MATCH",
        "notes": "Player next-team prop not standard.",
    },
    "KXNHLCENTRAL": {
        "sport_keys": ["icehockey_nhl"],
        "market_type": "outrights",
        "coverage_class": "PARTIAL",
        "notes": "NHL division winners listed on sportsbooks; the-odds-api default markets focus on game h2h. Coverage partial.",
    },
    "KXNHLMETROPOLITAN": {
        "sport_keys": ["icehockey_nhl"],
        "market_type": "outrights",
        "coverage_class": "PARTIAL",
        "notes": "Same as NHLCENTRAL.",
    },
}


def fetch_events(sport_key: str) -> list[dict]:
    """Fetch /v4/sports/{sport}/events (FREE per docs) for a sport_key.

    Cached locally as JSON. Returns [] on 404 or other error.
    """
    cache_file = EVENTS_CACHE / f"{sport_key}.json"
    if cache_file.exists():
        try:
            return json.loads(cache_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    url = f"{BASE}/sports/{sport_key}/events?apiKey={KEY}"
    req = urllib.request.Request(url, headers={"User-Agent": "project-kalshi-v5-research"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read())
    except urllib.error.HTTPError as exc:
        cache_file.write_text(json.dumps({"error": str(exc), "status": exc.code}), encoding="utf-8")
        return []
    except Exception as exc:
        cache_file.write_text(json.dumps({"error": str(exc)}), encoding="utf-8")
        return []
    cache_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
    time.sleep(THROTTLE_SEC)
    return data if isinstance(data, list) else []


def main() -> None:
    universe = pd.read_parquet(UNIVERSE)
    sports = json.loads(SPORTS_CACHE.read_text(encoding="utf-8"))
    sport_keys_in_catalog = {s["key"] for s in sports}

    # Universe of series-prefixes v1 has touched (>0 anywhere) or that have
    # v3 inventory eligible counts >= 1.
    relevant = universe[
        (universe["v1_live_all_orders"] > 0) | (universe["v3_inventory_eligible"] >= 1)
    ]
    series_to_classify = sorted(relevant["series_prefix"].unique().tolist())

    # Always include the denylisted three for completeness/transparency.
    for s in ("KXNFLWINS", "KXNFLPLAYOFF", "KXMLBPLAYOFFS"):
        if s not in series_to_classify:
            series_to_classify.append(s)

    rows = []
    events_calls = 0
    for series in series_to_classify:
        info = SERIES_MAP.get(series)
        if info is None:
            # Unmapped: classify as NO_MATCH and flag for follow-up.
            info = {
                "sport_keys": [],
                "market_type": "unknown",
                "coverage_class": "NO_MATCH",
                "notes": "Not yet mapped in SERIES_MAP; default to NO_MATCH.",
            }
        # Validate sport_keys against the live catalog
        valid_keys = [k for k in info["sport_keys"] if k in sport_keys_in_catalog]
        invalid_keys = [k for k in info["sport_keys"] if k not in sport_keys_in_catalog]
        # For MATCH/PARTIAL classes, probe /v4/events to confirm there are
        # currently-listed events. This is a FREE endpoint.
        active_event_counts: dict[str, int] = {}
        for k in valid_keys:
            evs = fetch_events(k)
            events_calls += 1
            active_event_counts[k] = len(evs) if isinstance(evs, list) else 0
        total_active_events = sum(active_event_counts.values())
        # Refine coverage class: if MATCH/PARTIAL but catalog has zero
        # in-season key AND zero events, downgrade to NO_MATCH (off-season).
        coverage_class = info["coverage_class"]
        if coverage_class in ("MATCH", "PARTIAL") and not valid_keys:
            coverage_class = "NO_MATCH_OFFSEASON"
        # Carry universe weights
        row_in_universe = universe[universe["series_prefix"] == series]
        if not row_in_universe.empty:
            r = row_in_universe.iloc[0]
            v1_live_all = int(r["v1_live_all_orders"])
            v1_live_acked = int(r["v1_live_acked_orders"])
            v3_eligible = int(r["v3_inventory_eligible"])
            league = r["league"]
        else:
            v1_live_all = v1_live_acked = v3_eligible = 0
            league = ""
        rows.append({
            "series_prefix": series,
            "league": league,
            "v1_live_all_orders": v1_live_all,
            "v1_live_acked_orders": v1_live_acked,
            "v3_inventory_eligible": v3_eligible,
            "denylisted": series in {"KXNFLWINS", "KXNFLPLAYOFF", "KXMLBPLAYOFFS"},
            "sport_keys": info["sport_keys"],
            "valid_sport_keys_in_catalog": valid_keys,
            "invalid_or_offseason_keys": invalid_keys,
            "active_event_counts": active_event_counts,
            "total_active_events": total_active_events,
            "market_type": info["market_type"],
            "coverage_class": coverage_class,
            "notes": info["notes"],
        })
    OUT_JSON.write_text(json.dumps({
        "events_calls_made": events_calls,
        "series": rows,
    }, indent=2), encoding="utf-8")
    df = pd.DataFrame([{k: v for k, v in r.items() if k not in {"active_event_counts"}} for r in rows])
    df.to_parquet(OUT_PARQUET, index=False)

    # Summary
    by_class = df["coverage_class"].value_counts().to_dict()
    print(f"Series classified: {len(df)}")
    print(f"Free /v4/events calls made: {events_calls}")
    print("Coverage classes:", by_class)
    print()
    print("MATCH-class series (with v1 weight):")
    print(df[df["coverage_class"] == "MATCH"][[
        "series_prefix", "league", "v1_live_all_orders", "v3_inventory_eligible",
        "total_active_events", "market_type"]].to_string(index=False))
    print()
    print("PARTIAL-class series (with v1 weight):")
    print(df[df["coverage_class"] == "PARTIAL"][[
        "series_prefix", "league", "v1_live_all_orders", "v3_inventory_eligible",
        "total_active_events", "market_type"]].to_string(index=False))
    print()
    print("NO_MATCH series:")
    print(df[df["coverage_class"].str.startswith("NO_MATCH", na=False)][[
        "series_prefix", "league", "v1_live_all_orders", "v3_inventory_eligible",
        "market_type", "notes"]].to_string(index=False))
    print()
    # Weighted coverage on v1 live attempted orders (post-denylist)
    post = df[~df["denylisted"]]
    total_live = int(post["v1_live_all_orders"].sum())
    weight_class = {
        "MATCH": 1.0,
        "PARTIAL": 0.4,
        "NO_MATCH": 0.0,
        "NO_MATCH_OFFSEASON": 0.0,
    }
    post = post.copy()
    post["weight_factor"] = post["coverage_class"].map(weight_class).fillna(0.0)
    post["weighted_live"] = post["v1_live_all_orders"] * post["weight_factor"]
    post["weighted_acked"] = post["v1_live_acked_orders"] * post["weight_factor"]
    post["weighted_v3"] = post["v3_inventory_eligible"] * post["weight_factor"]
    total_v3 = int(post["v3_inventory_eligible"].sum())
    print(f"=== POST-DENYLIST WEIGHTED COVERAGE ===")
    print(f"v1 LIVE attempted orders (n={total_live}): "
          f"weighted={post['weighted_live'].sum():.2f} -> "
          f"{(post['weighted_live'].sum()/total_live*100) if total_live else 0:.1f}% (inclusive)")
    print(f"v1 LIVE acked orders (n={int(post['v1_live_acked_orders'].sum())}): "
          f"weighted={post['weighted_acked'].sum():.2f} -> "
          f"{(post['weighted_acked'].sum()/post['v1_live_acked_orders'].sum()*100):.1f}% (inclusive)")
    print(f"v3 INVENTORY eligible (n={total_v3}): "
          f"weighted={post['weighted_v3'].sum():.2f} -> "
          f"{(post['weighted_v3'].sum()/total_v3*100) if total_v3 else 0:.1f}% (inclusive)")
    # MATCH-only strict
    match_post = post[post["coverage_class"] == "MATCH"]
    print(f"MATCH-only strict v1 LIVE: "
          f"{match_post['v1_live_all_orders'].sum()}/{total_live} = "
          f"{match_post['v1_live_all_orders'].sum()/total_live*100 if total_live else 0:.1f}%")
    print(f"MATCH-only strict v3 INVENTORY: "
          f"{match_post['v3_inventory_eligible'].sum()}/{total_v3} = "
          f"{match_post['v3_inventory_eligible'].sum()/total_v3*100 if total_v3 else 0:.1f}%")


if __name__ == "__main__":
    main()
