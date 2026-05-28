"""V5-A2: build a Kalshi-ticker -> sportsbook implied probability lookup.

For each Kalshi ticker candidate, map to the-odds-api sport_key, find
the matching event, fetch h2h odds, and compute the de-vigged median
implied probability across books for the Kalshi YES side.

Reuses V5-A1's cached `/v4/sports/{sport}/odds?markets=h2h&regions=us`
responses when available. For tickers NOT covered by the cache, an
incremental fetch is performed (controlled by `--max-credits` budget;
default 0 to make the script fully cache-only and credit-free).

Output:
    data/v5/sportsbook_lookup_<date>.parquet (ticker, sport_key,
    sportsbook_implied, n_books, sample_min, sample_max, source, fetched_at)
    data/v5/sportsbook_lookup_latest.parquet (symlink/copy of latest)
    data/v5/sportsbook_lookup_meta.json (run metadata)

Series sport-key mapping is taken from V5-A1's coverage matrix at
data/v5/odds_api_coverage_per_series.json. Only MATCH-class series are
treated as direct h2h candidates; PARTIAL series with outright market
types would require sport-specific outright sport_keys and are skipped
in this build (covered by future scope per V5 master plan).

Credit budget: defaults to 0 (cache-only). If --max-credits N is passed
the script may consume up to N additional credits to fetch sport_keys
not in the cache, throttled at <1 req/sec.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parents[2]
DATA_V5 = ROOT / "data" / "v5"
LIVE_CACHE = DATA_V5 / "odds_api_live_cache"
COVERAGE_JSON = DATA_V5 / "odds_api_coverage_per_series.json"
UNIVERSE_PARQUET = DATA_V5 / "v1_post_denylist_universe.parquet"

BASE = "https://api.the-odds-api.com/v4"
KEY = os.environ.get("THE_ODDS_API_KEY", "")
THROTTLE_SEC = 1.1
TODAY = datetime.now(timezone.utc).strftime("%Y%m%d")
OUT_PARQUET = DATA_V5 / f"sportsbook_lookup_{TODAY}.parquet"
LATEST_PARQUET = DATA_V5 / "sportsbook_lookup_latest.parquet"
META_JSON = DATA_V5 / "sportsbook_lookup_meta.json"


# Team-name lookup tables. The-odds-api uses full team names; Kalshi
# uses short codes. Maps short_code -> full_name per league. These
# tables are deliberately conservative; missing entries become unmatched
# rather than mis-matched (silent failures are flagged in meta output).
MLB_TEAMS = {
    "ARI": "Arizona Diamondbacks", "AZ": "Arizona Diamondbacks",
    "ATL": "Atlanta Braves", "BAL": "Baltimore Orioles",
    "BOS": "Boston Red Sox", "CHC": "Chicago Cubs", "CHI": "Chicago Cubs",
    "CWS": "Chicago White Sox", "CIN": "Cincinnati Reds",
    "CLE": "Cleveland Guardians", "COL": "Colorado Rockies",
    "DET": "Detroit Tigers", "HOU": "Houston Astros",
    "KC": "Kansas City Royals", "LAA": "Los Angeles Angels",
    "LAD": "Los Angeles Dodgers", "MIA": "Miami Marlins",
    "MIL": "Milwaukee Brewers", "MIN": "Minnesota Twins",
    "NYM": "New York Mets", "NYY": "New York Yankees",
    "OAK": "Oakland Athletics", "ATH": "Athletics",
    "PHI": "Philadelphia Phillies", "PIT": "Pittsburgh Pirates",
    "SD": "San Diego Padres", "SEA": "Seattle Mariners",
    "SF": "San Francisco Giants", "STL": "St. Louis Cardinals",
    "TB": "Tampa Bay Rays", "TEX": "Texas Rangers",
    "TOR": "Toronto Blue Jays", "WSH": "Washington Nationals",
    "WAS": "Washington Nationals",
}
NFL_TEAMS = {
    "ARI": "Arizona Cardinals", "ATL": "Atlanta Falcons",
    "BAL": "Baltimore Ravens", "BUF": "Buffalo Bills",
    "CAR": "Carolina Panthers", "CHI": "Chicago Bears",
    "CIN": "Cincinnati Bengals", "CLE": "Cleveland Browns",
    "DAL": "Dallas Cowboys", "DEN": "Denver Broncos",
    "DET": "Detroit Lions", "GB": "Green Bay Packers",
    "HOU": "Houston Texans", "IND": "Indianapolis Colts",
    "JAC": "Jacksonville Jaguars", "JAX": "Jacksonville Jaguars",
    "KC": "Kansas City Chiefs", "LA": "Los Angeles Rams",
    "LAR": "Los Angeles Rams", "LAC": "Los Angeles Chargers",
    "LV": "Las Vegas Raiders", "MIA": "Miami Dolphins",
    "MIN": "Minnesota Vikings", "NE": "New England Patriots",
    "NO": "New Orleans Saints", "NYG": "New York Giants",
    "NYJ": "New York Jets", "PHI": "Philadelphia Eagles",
    "PIT": "Pittsburgh Steelers", "SEA": "Seattle Seahawks",
    "SF": "San Francisco 49ers", "TB": "Tampa Bay Buccaneers",
    "TEN": "Tennessee Titans", "WAS": "Washington Commanders",
}


def implied_from_decimal(d: float) -> float:
    if d <= 0:
        return 0.0
    return 1.0 / d


def devig_2way(p1: float, p2: float) -> tuple[float, float]:
    s = p1 + p2
    if s <= 0:
        return 0.0, 0.0
    return p1 / s, p2 / s


def devig_3way(p1: float, p2: float, p3: float) -> tuple[float, float, float]:
    s = p1 + p2 + p3
    if s <= 0:
        return 0.0, 0.0, 0.0
    return p1 / s, p2 / s, p3 / s


# Kalshi ticker parsers per supported series prefix.

def parse_kxmlbgame(ticker: str) -> Optional[dict]:
    """KXMLBGAME-26MAY261940NYYKC-NYY -> dict with away/home/team codes."""
    m = re.match(
        r"^KXMLBGAME-(\d{2})(\w{3})(\d{2})(\d{4})([A-Z]{2,3})([A-Z]{2,3})-([A-Z]{2,3})$",
        ticker,
    )
    if not m:
        return None
    yy, mon, day, hhmm, away, home, team = m.groups()
    return {
        "series": "KXMLBGAME",
        "yy": yy, "mon": mon, "day": day, "hhmm": hhmm,
        "away_code": away, "home_code": home, "team_code": team,
    }


def parse_kxnflgame(ticker: str) -> Optional[dict]:
    """KXNFLGAME-26SEP13CLEJAC-JAC -> dict with away/home/team codes."""
    m = re.match(
        r"^KXNFLGAME-(\d{2})(\w{3})(\d{2})(?:(\d{4}))?([A-Z]{2,3})([A-Z]{2,3})-([A-Z]{2,3})$",
        ticker,
    )
    if not m:
        return None
    yy, mon, day, hhmm, away, home, team = m.groups()
    return {
        "series": "KXNFLGAME",
        "yy": yy, "mon": mon, "day": day, "hhmm": hhmm or "",
        "away_code": away, "home_code": home, "team_code": team,
    }


def parse_kxwcgame(ticker: str) -> Optional[dict]:
    """KXWCGAME-26JUN23ENGGHA-ENG -> dict.

    Country codes can be 3 chars (FIFA standard). Pattern matches
    AAACCC where AAA is away, BBB is home, hyphen, target country.
    """
    m = re.match(
        r"^KXWCGAME-(\d{2})(\w{3})(\d{2})([A-Z]{3})([A-Z]{3})-([A-Z]{3})$",
        ticker,
    )
    if not m:
        return None
    yy, mon, day, away, home, team = m.groups()
    return {
        "series": "KXWCGAME",
        "yy": yy, "mon": mon, "day": day,
        "away_code": away, "home_code": home, "team_code": team,
    }


def parse_kxufcfight(ticker: str) -> Optional[dict]:
    """KXUFCFIGHT-26JUL11MCGHOL-HOL.

    Fighter codes are variable length (3-7 chars). We split the trailing
    -CODE off, and treat everything between the date and the dash as the
    pair-of-fighters mash.
    """
    m = re.match(
        r"^KXUFCFIGHT-(\d{2})(\w{3})(\d{2})(\w+)-(\w+)$",
        ticker,
    )
    if not m:
        return None
    yy, mon, day, pair, target = m.groups()
    return {
        "series": "KXUFCFIGHT",
        "yy": yy, "mon": mon, "day": day,
        "pair_blob": pair, "target_code": target,
    }


def parse_kxboxing(ticker: str) -> Optional[dict]:
    """KXBOXING-26MAY30FOSTERFORD-FOSTER."""
    m = re.match(
        r"^KXBOXING-(\d{2})(\w{3})(\d{2})(\w+)-(\w+)$",
        ticker,
    )
    if not m:
        return None
    yy, mon, day, pair, target = m.groups()
    return {
        "series": "KXBOXING",
        "yy": yy, "mon": mon, "day": day,
        "pair_blob": pair, "target_code": target,
    }


SERIES_TO_SPORTKEY = {
    "KXMLBGAME": "baseball_mlb",
    "KXNFLGAME": "americanfootball_nfl",
    "KXWCGAME": "soccer_fifa_world_cup",
    "KXUFCFIGHT": "mma_mixed_martial_arts",
    "KXBOXING": "boxing_boxing",
}

SERIES_PARSERS = {
    "KXMLBGAME": parse_kxmlbgame,
    "KXNFLGAME": parse_kxnflgame,
    "KXWCGAME": parse_kxwcgame,
    "KXUFCFIGHT": parse_kxufcfight,
    "KXBOXING": parse_kxboxing,
}

# Country name lookup for WC (subset; expand on demand).
WC_COUNTRIES = {
    "ENG": "England", "GHA": "Ghana", "SCO": "Scotland", "BRA": "Brazil",
    "AUT": "Austria", "JOR": "Jordan", "USA": "USA", "MEX": "Mexico",
    "ARG": "Argentina", "GER": "Germany", "FRA": "France", "ESP": "Spain",
    "ITA": "Italy", "BEL": "Belgium", "NED": "Netherlands",
    "POR": "Portugal", "POL": "Poland", "CRO": "Croatia", "DEN": "Denmark",
    "SUI": "Switzerland", "SRB": "Serbia", "MAR": "Morocco",
    "SEN": "Senegal", "JPN": "Japan", "KOR": "South Korea",
    "AUS": "Australia", "URU": "Uruguay", "CAN": "Canada",
    "COL": "Colombia", "ECU": "Ecuador", "TUN": "Tunisia",
    "CMR": "Cameroon", "GHA": "Ghana", "WAL": "Wales", "IRN": "Iran",
    "SAU": "Saudi Arabia", "QAT": "Qatar", "ALG": "Algeria",
    "EGY": "Egypt", "NGA": "Nigeria", "RSA": "South Africa",
}


def kalshi_to_team_name(parsed: dict) -> Optional[str]:
    series = parsed.get("series", "")
    code = parsed.get("team_code") or parsed.get("target_code", "")
    if series == "KXMLBGAME":
        return MLB_TEAMS.get(code)
    if series == "KXNFLGAME":
        return NFL_TEAMS.get(code)
    if series == "KXWCGAME":
        return WC_COUNTRIES.get(code)
    # UFC / Boxing: the target_code is a short string from the fighter
    # surname. We cannot reliably map without an exhaustive name table,
    # so for these series we return the raw code and use substring
    # matching against bookmaker outcome names below.
    return code or None


def load_cached_odds(sport_key: str) -> Optional[dict]:
    """Load the cached /v4/sports/{sport}/odds?markets=h2h&regions=us
    response. Returns None if no cache present.
    """
    cache_path = LIVE_CACHE / f"{sport_key}_h2h_us.json"
    if not cache_path.exists():
        return None
    return json.loads(cache_path.read_text(encoding="utf-8"))


def fetch_live_odds(sport_key: str) -> dict:
    """Hit the-odds-api for live h2h odds. Costs 1 credit per call."""
    cache_path = LIVE_CACHE / f"{sport_key}_h2h_us.json"
    url = (
        f"{BASE}/sports/{sport_key}/odds"
        f"?apiKey={KEY}&regions=us&markets=h2h&oddsFormat=decimal"
    )
    req = urllib.request.Request(
        url, headers={"User-Agent": "project-kalshi-v5a2"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read()
        used = r.headers.get("x-requests-used", "")
        remaining = r.headers.get("x-requests-remaining", "")
        last_cost = r.headers.get("x-requests-last", "")
    data = json.loads(body)
    out = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "x_requests_used": used,
        "x_requests_remaining": remaining,
        "x_requests_last_cost": last_cost,
        "events": data,
    }
    LIVE_CACHE.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    time.sleep(THROTTLE_SEC)
    return out


def extract_implied_for_team(
    event: dict,
    target_team_name: str,
) -> tuple[Optional[float], list[float]]:
    """Return (median_implied, per_book_list) for the target team in this
    event. De-vigging is 2-way for h2h, 3-way if soccer with draw.
    """
    per_book: list[float] = []
    for bm in event.get("bookmakers", []):
        for market in bm.get("markets", []):
            if market.get("key") != "h2h":
                continue
            outcomes = market.get("outcomes", [])
            if len(outcomes) == 2:
                ps = [implied_from_decimal(float(o.get("price", 0) or 0)) for o in outcomes]
                names = [o.get("name", "") for o in outcomes]
                if not all(p > 0 for p in ps):
                    continue
                ps_dv = devig_2way(*ps)
                for nm, p in zip(names, ps_dv, strict=False):
                    if nm == target_team_name:
                        per_book.append(p)
                        break
                else:
                    # Try substring match for surname-only targets (UFC/Boxing).
                    for nm, p in zip(names, ps_dv, strict=False):
                        if target_team_name.lower() in nm.lower():
                            per_book.append(p)
                            break
            elif len(outcomes) == 3:
                ps = [implied_from_decimal(float(o.get("price", 0) or 0)) for o in outcomes]
                names = [o.get("name", "") for o in outcomes]
                if not all(p > 0 for p in ps):
                    continue
                ps_dv = devig_3way(*ps)
                for nm, p in zip(names, ps_dv, strict=False):
                    if nm == target_team_name:
                        per_book.append(p)
                        break
    if not per_book:
        return None, []
    median = float(pd.Series(per_book).median())
    return median, per_book


def match_event_for_ticker(
    parsed: dict,
    odds_events: list[dict],
) -> Optional[dict]:
    """Find the event in odds_events that matches the parsed Kalshi
    ticker. Matching is by (home_team, away_team) where the team names
    map via the league-specific lookup. For UFC/Boxing, both fighter
    surnames need to substring-match the event's home/away.
    """
    series = parsed.get("series", "")
    if series in ("KXMLBGAME", "KXNFLGAME", "KXWCGAME"):
        home_name = (
            MLB_TEAMS if series == "KXMLBGAME"
            else NFL_TEAMS if series == "KXNFLGAME"
            else WC_COUNTRIES
        ).get(parsed.get("home_code", ""))
        away_name = (
            MLB_TEAMS if series == "KXMLBGAME"
            else NFL_TEAMS if series == "KXNFLGAME"
            else WC_COUNTRIES
        ).get(parsed.get("away_code", ""))
        if not home_name or not away_name:
            return None
        for ev in odds_events:
            if (ev.get("home_team") == home_name
                    and ev.get("away_team") == away_name):
                return ev
            # Some leagues swap home/away in API; try both.
            if (ev.get("home_team") == away_name
                    and ev.get("away_team") == home_name):
                return ev
        return None
    if series in ("KXUFCFIGHT", "KXBOXING"):
        # Try substring match: target_code must appear in one of the
        # team names, and ALSO some token from the pair_blob must appear
        # in the other team name.
        target = parsed.get("target_code", "")
        pair = parsed.get("pair_blob", "")
        opponent_blob = pair.replace(target, "")
        for ev in odds_events:
            h = ev.get("home_team", "")
            a = ev.get("away_team", "")
            if target.lower() in h.lower() and (
                opponent_blob.lower()[:4] in a.lower()
                or any(tok in a.lower() for tok in [opponent_blob.lower()[:3], opponent_blob.lower()[:4]] if tok)
            ):
                return ev
            if target.lower() in a.lower() and (
                opponent_blob.lower()[:4] in h.lower()
                or any(tok in h.lower() for tok in [opponent_blob.lower()[:3], opponent_blob.lower()[:4]] if tok)
            ):
                return ev
            # Looser: any substring of target in either side.
            if (
                target.lower() in h.lower() or target.lower() in a.lower()
            ) and len(target) >= 4:
                return ev
        return None
    return None


def build_lookup(
    candidate_tickers: list[str],
    max_credits: int = 0,
    verbose: bool = False,
) -> tuple[list[dict], dict]:
    """Build the (ticker -> sportsbook implied) lookup.

    Returns (rows, meta). Rows have one entry per candidate ticker
    (matched and unmatched both included for transparency). Meta has
    counters of credits used, unmatched reasons, etc.
    """
    # Group candidates by series and discover which sport_keys we need.
    series_groups: dict[str, list[str]] = {}
    for t in candidate_tickers:
        prefix = t.split("-", 1)[0]
        if prefix not in SERIES_TO_SPORTKEY:
            continue
        series_groups.setdefault(prefix, []).append(t)

    # Load cached responses; fetch missing if budget allows.
    sport_responses: dict[str, dict] = {}
    credits_used = 0
    fetch_attempts: list[dict] = []
    for series, _ in series_groups.items():
        sport_key = SERIES_TO_SPORTKEY[series]
        if sport_key in sport_responses:
            continue
        cached = load_cached_odds(sport_key)
        if cached is not None:
            sport_responses[sport_key] = cached
            fetch_attempts.append({
                "sport_key": sport_key, "source": "cache",
                "events_count": len(cached.get("events", [])),
            })
        else:
            if credits_used < max_credits:
                if not KEY:
                    fetch_attempts.append({
                        "sport_key": sport_key, "source": "skipped_no_key",
                    })
                    continue
                try:
                    resp = fetch_live_odds(sport_key)
                    sport_responses[sport_key] = resp
                    credits_used += 1
                    fetch_attempts.append({
                        "sport_key": sport_key, "source": "live_fetch",
                        "events_count": len(resp.get("events", [])),
                        "x_requests_remaining": resp.get("x_requests_remaining"),
                    })
                except urllib.error.HTTPError as exc:
                    fetch_attempts.append({
                        "sport_key": sport_key, "source": "fetch_failed",
                        "error": str(exc),
                    })
            else:
                fetch_attempts.append({
                    "sport_key": sport_key, "source": "skipped_budget",
                })

    # For each candidate ticker, run parser, find event, extract implied.
    rows: list[dict] = []
    unmatched_reasons: dict[str, int] = {}
    for ticker in candidate_tickers:
        prefix = ticker.split("-", 1)[0]
        parser = SERIES_PARSERS.get(prefix)
        sport_key = SERIES_TO_SPORTKEY.get(prefix)
        row: dict = {
            "ticker": ticker,
            "series_prefix": prefix,
            "sport_key": sport_key,
            "sportsbook_implied": None,
            "n_books": 0,
            "sample_min": None,
            "sample_max": None,
            "source": None,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "matched_event_id": None,
            "matched_home_team": None,
            "matched_away_team": None,
            "target_team_resolved": None,
            "unmatched_reason": None,
        }
        if parser is None or sport_key is None:
            row["unmatched_reason"] = "series_unsupported"
            unmatched_reasons["series_unsupported"] = unmatched_reasons.get("series_unsupported", 0) + 1
            rows.append(row)
            continue
        parsed = parser(ticker)
        if parsed is None:
            row["unmatched_reason"] = "parser_failed"
            unmatched_reasons["parser_failed"] = unmatched_reasons.get("parser_failed", 0) + 1
            rows.append(row)
            continue
        target_name = kalshi_to_team_name(parsed)
        row["target_team_resolved"] = target_name
        if target_name is None:
            row["unmatched_reason"] = "team_code_unmapped"
            unmatched_reasons["team_code_unmapped"] = unmatched_reasons.get("team_code_unmapped", 0) + 1
            rows.append(row)
            continue
        resp = sport_responses.get(sport_key)
        if resp is None:
            row["unmatched_reason"] = "no_sport_response"
            unmatched_reasons["no_sport_response"] = unmatched_reasons.get("no_sport_response", 0) + 1
            rows.append(row)
            continue
        events = resp.get("events", []) or []
        match = match_event_for_ticker(parsed, events)
        if match is None:
            row["unmatched_reason"] = "no_event_match"
            unmatched_reasons["no_event_match"] = unmatched_reasons.get("no_event_match", 0) + 1
            rows.append(row)
            continue
        row["matched_event_id"] = match.get("id")
        row["matched_home_team"] = match.get("home_team")
        row["matched_away_team"] = match.get("away_team")
        median, per_book = extract_implied_for_team(match, target_name)
        if median is None:
            row["unmatched_reason"] = "no_book_for_target"
            unmatched_reasons["no_book_for_target"] = unmatched_reasons.get("no_book_for_target", 0) + 1
            rows.append(row)
            continue
        row["sportsbook_implied"] = round(median, 6)
        row["n_books"] = len(per_book)
        row["sample_min"] = round(min(per_book), 6)
        row["sample_max"] = round(max(per_book), 6)
        row["source"] = "live_cache" if resp.get("fetched_at") else "live_fresh"
        if verbose:
            print(f"  matched {ticker} ({target_name}) -> implied={median:.4f} n_books={len(per_book)}")
        rows.append(row)

    meta = {
        "candidate_count": len(candidate_tickers),
        "matched_count": sum(1 for r in rows if r["sportsbook_implied"] is not None),
        "unmatched_count": sum(1 for r in rows if r["sportsbook_implied"] is None),
        "unmatched_reasons": unmatched_reasons,
        "credits_used_this_run": credits_used,
        "max_credits_budget": max_credits,
        "sport_key_fetch_attempts": fetch_attempts,
        "build_completed_at": datetime.now(timezone.utc).isoformat(),
        "supported_series": list(SERIES_TO_SPORTKEY.keys()),
    }
    return rows, meta


def candidate_tickers_from_universe() -> list[str]:
    """Return v1's currently-resting candidate tickers + open-market
    tickers from the divergence probe. Falls back to a hard-coded list
    if no parquet present.
    """
    candidates: set[str] = set()
    # V1 resting from divergence summary (already cached).
    sum_path = DATA_V5 / "divergence_summary.json"
    if sum_path.exists():
        data = json.loads(sum_path.read_text(encoding="utf-8"))
        for r in data.get("rows", []):
            candidates.add(r["ticker"])
    return sorted(candidates)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build sportsbook lookup")
    parser.add_argument(
        "--tickers", nargs="*", default=None,
        help=(
            "Specific Kalshi tickers to look up. If omitted, uses the "
            "cached universe of v1-resting + MLB/UFC/Boxing probe tickers."
        ),
    )
    parser.add_argument(
        "--max-credits", type=int, default=0,
        help=(
            "Maximum the-odds-api credits to consume on this run. Default "
            "0 = cache-only mode (zero new credits)."
        ),
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Print per-ticker matches",
    )
    args = parser.parse_args()

    if args.tickers:
        candidate_tickers = list(args.tickers)
    else:
        candidate_tickers = candidate_tickers_from_universe()

    if not candidate_tickers:
        print("No candidate tickers. Provide --tickers or populate "
              "divergence_summary.json first.")
        sys.exit(2)

    print(f"Building sportsbook lookup for {len(candidate_tickers)} candidates")
    print(f"  Budget: {args.max_credits} credits (cache-first)")

    rows, meta = build_lookup(
        candidate_tickers,
        max_credits=args.max_credits,
        verbose=args.verbose,
    )

    # Persist outputs
    DATA_V5.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)
    df.to_parquet(OUT_PARQUET, index=False)
    df.to_parquet(LATEST_PARQUET, index=False)
    META_JSON.write_text(json.dumps(meta, indent=2, default=str), encoding="utf-8")

    print(f"\nWrote {OUT_PARQUET}")
    print(f"Wrote {LATEST_PARQUET}")
    print(f"Wrote {META_JSON}")
    print()
    print("=== Summary ===")
    print(f"  Candidates: {meta['candidate_count']}")
    print(f"  Matched (have sportsbook_implied): {meta['matched_count']}")
    print(f"  Unmatched: {meta['unmatched_count']}")
    if meta["unmatched_reasons"]:
        print("  Unmatched reasons:")
        for k, v in sorted(meta["unmatched_reasons"].items(), key=lambda kv: -kv[1]):
            print(f"    {k}: {v}")
    print(f"  Credits used this run: {meta['credits_used_this_run']}")


if __name__ == "__main__":
    main()
