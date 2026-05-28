"""Phase 1 / Agent V4-A: per-live-order Polymarket-match audit.

For each distinct v1 live attempted-order ticker, attempt to find the EXACT
Polymarket counterpart that would be available at this moment for the
fade-filter to act on. This is the BINDING test: the filter only acts on
markets where (a) Polymarket lists the counterpart now and (b) Polymarket's
CLOB returns a current mid.

For each live ticker:
  1. Build the most-specific Polymarket query/slug we can
  2. Search via public-search and/or direct slug guess
  3. If a candidate is found, fetch CLOB /midpoint to confirm live pricing
  4. Record: match_status (CONFIRMED / NO_CURRENT_MATCH / NEEDS_REVIEW),
     poly_event_slug, poly_market_slug, poly_yes_token_id, poly_mid_now

Cache to data/v4/live_orders_poly_audit.json
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

import httpx

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_V4 = REPO_ROOT / "data" / "v4"
LIVE_STATE = REPO_ROOT / "data" / "live_trades" / "state.json"

GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"

POLITE_SLEEP_S = 0.15

OUT = DATA_V4 / "live_orders_poly_audit.json"


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


# Country code to team-slug for World Cup
WC_COUNTRY_SLUG = {
    "ESP": ("esp", "Spain"),
    "ENG": ("eng", "England"),
    "GHA": ("gha", "Ghana"),
    "BRA": ("bra", "Brazil"),
    "SCO": ("sco", "Scotland"),
    "JOR": ("jor", "Jordan"),
    "AUT": ("aut", "Austria"),
    "CPV": ("cpv", "Cape Verde"),
}

# NFL/NBA/MLB/NHL team abbrev -> Polymarket slug
NFL_TEAM_SLUG = {
    "DET": "detroit-lions", "KC": "kansas-city-chiefs", "PIT": "pittsburgh-steelers",
    "ATL": "atlanta-falcons", "CLE": "cleveland-browns", "JAC": "jacksonville-jaguars",
    "LV": "las-vegas-raiders",
}
NBA_TEAM_SLUG = {
    "SAS": "san-antonio-spurs", "OKC": "oklahoma-city-thunder", "LV": "las-vegas",
}
MLB_TEAM_SLUG = {
    "HOU": "houston-astros", "ATH": "athletics", "KC": "kansas-city-royals",
}
NHL_TEAM_SLUG = {
    "TOR": "toronto-maple-leafs", "SEA": "seattle-kraken",
}

# UFC fighter abbrev (rough) -> Polymarket slug components
UFC_FIGHTER_SLUG = {
    "MCG": "conor-mcgregor",
    "HOL": "max-holloway",
    "HOK": "ankalaev",  # placeholder; we'll do search
    "LEW": "derrick-lewis",
}


def extract_wc_match_slug(ticker: str) -> tuple[str | None, str | None]:
    """KXWCGAME-26JUN23ENGGHA-ENG -> ('fifwc-eng-gha-2026-06-23', 'eng')"""
    m = re.match(r"^KXWCGAME-(\d{2})([A-Z]{3})(\d{2})([A-Z]{3})([A-Z]{3})-([A-Z]{3})$", ticker)
    if not m:
        return None, None
    yy, mon, dd, t1, t2, side = m.groups()
    months = {"JAN": "01", "FEB": "02", "MAR": "03", "APR": "04", "MAY": "05", "JUN": "06",
              "JUL": "07", "AUG": "08", "SEP": "09", "OCT": "10", "NOV": "11", "DEC": "12"}
    mm = months.get(mon)
    if not mm:
        return None, None
    return f"fifwc-{t1.lower()}-{t2.lower()}-20{yy}-{mm}-{dd}", side.lower()


def extract_squad_slug(ticker: str) -> tuple[str | None, str | None]:
    """KXWCSQUAD-26ESP-BIGL -> ('2026-fifa-world-cup-player-to-make-spain-squad', 'big-l')"""
    m = re.match(r"^KXWCSQUAD-(\d{2})([A-Z]{3})-([A-Z]+)$", ticker)
    if not m:
        return None, None
    yy, country, player = m.groups()
    full = {"ESP": "spain", "ENG": "england", "BRA": "brazil", "ARG": "argentina",
            "USA": "usa", "NED": "netherlands", "GER": "germany"}.get(country)
    if not full:
        return None, None
    return f"20{yy}-fifa-world-cup-player-to-make-{full}-squad", player.lower()


def search_query_for_ticker(ticker: str) -> list[str]:
    """Return a list of search queries for public-search, ordered by specificity."""
    series = ticker.split("-", 1)[0]
    queries: list[str] = []
    if series == "KXBOXING":
        # KXBOXING-26SEP12CALVARMBILLI-CALVAR: Canelo Alvarez vs Mbilli September 12 2026
        # extract names by parsing camelcase-ish suffix
        m = re.match(r"^KXBOXING-(\d{2})([A-Z]{3})(\d{2})([A-Z]+)-([A-Z]+)$", ticker)
        if m:
            yy, mon, dd, fighters, side = m.groups()
            queries.append(f"{fighters} boxing 20{yy} {mon} {dd}")
            queries.append("Canelo Mbilli September 2026")
    elif series == "KXUFCFIGHT":
        m = re.match(r"^KXUFCFIGHT-(\d{2})([A-Z]{3})(\d{2})([A-Z]{3,})([A-Z]{3,})-([A-Z]+)$", ticker)
        if m:
            yy, mon, dd, f1, f2, side = m.groups()
            queries.append(f"UFC {f1} vs {f2} 20{yy} {mon}")
            queries.append(f"{f1} {f2} UFC")
    elif series == "KXNFLPLAYOFF":
        m = re.match(r"^KXNFLPLAYOFF-(\d{2})-([A-Z]+)$", ticker)
        if m:
            yy, team = m.groups()
            queries.append(f"{team} NFL playoffs 20{yy}")
    elif series == "KXMLBWINS":
        m = re.match(r"^KXMLBWINS-([A-Z]+)-(\d{2})-T(\d+)$", ticker)
        if m:
            team, yy, t = m.groups()
            queries.append(f"{team} MLB 20{yy} win totals")
            queries.append(f"MLB 20{yy} regular season win totals")
    elif series == "KXNFLWINS":
        m = re.match(r"^KXNFLWINS-(\d{2})([A-Z]+)-(\d+)$", ticker)
        if m:
            yy, team, t = m.groups()
            queries.append(f"{team} NFL 20{yy} win totals over")
            queries.append(f"NFL win totals over under 20{yy}")
    elif series == "KXNCAAFPLAYOFF":
        m = re.match(r"^KXNCAAFPLAYOFF-(\d{2})-([A-Z]+)$", ticker)
        if m:
            yy, team = m.groups()
            queries.append(f"{team} college football playoff 20{yy}")
    elif series == "KXNBAPLAYOFFWINS":
        m = re.match(r"^KXNBAPLAYOFFWINS-(\d{2})([A-Z]+)-(\d+)$", ticker)
        if m:
            yy, team, wins = m.groups()
            queries.append(f"{team} NBA playoffs {wins} wins 20{yy}")
    elif series == "KXNBAWINS":
        m = re.match(r"^KXNBAWINS-(\d{2})([A-Z]+)-T(\d+)$", ticker)
        if m:
            yy, team, t = m.groups()
            queries.append(f"{team} NBA win totals 20{yy}")
            queries.append(f"NBA win totals over under 20{yy}")
    elif series == "KXWNBAWINS":
        m = re.match(r"^KXWNBAWINS-(\d{2})([A-Z]+)-(\d+)$", ticker)
        if m:
            yy, team, t = m.groups()
            queries.append(f"{team} WNBA win totals 20{yy}")
    elif series == "KXFOMEN":
        m = re.match(r"^KXFOMEN-(\d{2})-([A-Z]+)$", ticker)
        if m:
            yy, race = m.groups()
            queries.append(f"F1 {race} Grand Prix 20{yy}")
    elif series == "KXCS2":
        queries.append(ticker.replace("KX", "").replace("-", " ") + " counter-strike")
    elif series == "KXCITYNBAEXPAND":
        queries.append("NBA expansion next city")
    elif series == "KXNEXTTEAMNFL":
        m = re.match(r"^KXNEXTTEAMNFL-(\d{2})K?([A-Z]+)-([A-Z]+)$", ticker)
        if m:
            yy, p1, p2 = m.groups()
            queries.append(f"NFL next team {p1}")
    elif series == "KXNEXTTEAMNHL":
        queries.append("NHL next team")
    elif series == "KXMLBSTATCOUNT":
        queries.append("MLB immaculate inning 2026")
    elif series == "KXSTARTINGQBWEEK1":
        queries.append("NFL starting QB week 1 Raiders Chiefs")
    # fallback
    if not queries:
        queries.append(ticker.replace("KX", "").replace("-", " "))
    return queries


def fetch_midpoint(token_id: str) -> float | None:
    res = http_get(f"{CLOB}/midpoint", params={"token_id": token_id})
    time.sleep(POLITE_SLEEP_S)
    if isinstance(res, dict) and "mid" in res:
        try:
            return float(res["mid"])
        except (TypeError, ValueError):
            return None
    return None


def audit_one_ticker(ticker: str, event_ticker: str, market_mid: float) -> dict[str, Any]:
    """Audit one v1-attempted ticker."""
    out: dict[str, Any] = {
        "kalshi_ticker": ticker,
        "kalshi_event_ticker": event_ticker,
        "kalshi_market_mid_at_placement": market_mid,
        "series_prefix": ticker.split("-", 1)[0],
        "poly_event_slug": None,
        "poly_market_slug": None,
        "poly_market_question": None,
        "poly_yes_token_id": None,
        "poly_mid_now": None,
        "match_status": "NEEDS_REVIEW",
        "match_method": None,
        "match_notes": "",
    }
    series = out["series_prefix"]
    # Strategy 1: deterministic slug for World Cup games
    if series == "KXWCGAME":
        slug, side = extract_wc_match_slug(ticker)
        if slug:
            res = http_get(f"{GAMMA}/events/slug/{slug}")
            time.sleep(POLITE_SLEEP_S)
            if isinstance(res, dict) and not res.get("_http_error"):
                # Find market for the side
                target_market_slug = f"{slug}-{side}"
                for m in res.get("markets", []):
                    if (m.get("slug") or "") == target_market_slug:
                        cti = m.get("clobTokenIds")
                        if isinstance(cti, str):
                            cti = json.loads(cti)
                        out["poly_event_slug"] = slug
                        out["poly_market_slug"] = m.get("slug")
                        out["poly_market_question"] = m.get("question")
                        out["poly_yes_token_id"] = cti[0] if cti else None
                        out["match_method"] = "deterministic_wc_slug"
                        if out["poly_yes_token_id"]:
                            out["poly_mid_now"] = fetch_midpoint(out["poly_yes_token_id"])
                            out["match_status"] = "CONFIRMED" if out["poly_mid_now"] is not None else "MATCH_NO_MID"
                        break
                if not out["poly_market_slug"]:
                    out["match_notes"] = f"event {slug} found but market {target_market_slug} not in markets"
            else:
                out["match_notes"] = f"slug {slug} 404"
    # Strategy 2: deterministic slug for World Cup squads
    elif series == "KXWCSQUAD":
        slug, _ = extract_squad_slug(ticker)
        if slug:
            res = http_get(f"{GAMMA}/events/slug/{slug}")
            time.sleep(POLITE_SLEEP_S)
            if isinstance(res, dict) and not res.get("_http_error"):
                out["poly_event_slug"] = slug
                out["match_method"] = "deterministic_squad_slug"
                # We need to find the player; squad events have many markets, one per player
                # We don't have a deterministic player slug mapping, so this is PARTIAL
                out["match_notes"] = f"event {slug} found; player-level match would need lookup table (event has {len(res.get('markets', []))} markets)"
                out["match_status"] = "EVENT_MATCH_PLAYER_TODO"
                # Pull mid for first market as availability check
                first = (res.get("markets") or [])[0] if res.get("markets") else None
                if first:
                    cti = first.get("clobTokenIds")
                    if isinstance(cti, str):
                        cti = json.loads(cti)
                    if cti:
                        out["poly_yes_token_id_sample"] = cti[0]
                        out["poly_mid_sample"] = fetch_midpoint(cti[0])
    # Strategy 3 (general): public-search
    if out["match_status"] == "NEEDS_REVIEW":
        queries = search_query_for_ticker(ticker)
        candidates: list[dict] = []
        for q in queries:
            res = http_get(f"{GAMMA}/public-search", params={"q": q, "limit_per_type": 5})
            time.sleep(POLITE_SLEEP_S)
            if isinstance(res, dict):
                for e in (res.get("events") or [])[:5]:
                    candidates.append({
                        "slug": e.get("slug"),
                        "title": (e.get("title") or "")[:140],
                        "active": e.get("active"),
                        "closed": e.get("closed"),
                        "endDate": e.get("endDate"),
                        "query_that_found_it": q,
                    })
        # Dedup
        seen = set()
        deduped = []
        for c in candidates:
            if c["slug"] in seen:
                continue
            seen.add(c["slug"])
            deduped.append(c)
        out["poly_search_candidates"] = deduped[:10]
        # Heuristic auto-classify
        active_open = [c for c in deduped if c.get("active") and not c.get("closed")]
        if not deduped:
            out["match_status"] = "NO_SEARCH_HITS"
        elif not active_open:
            out["match_status"] = "ONLY_CLOSED_HITS"
        else:
            out["match_status"] = "NEEDS_REVIEW"  # human verification ahead
    return out


def main() -> None:
    with open(LIVE_STATE) as f:
        state = json.load(f)
    # Collect all distinct tickers across all buckets
    tickers: dict[str, dict[str, Any]] = {}
    for bucket in ("intents", "resting", "filled", "closed"):
        for order in state.get(bucket, {}).values():
            t = order.get("ticker")
            if t and t not in tickers:
                tickers[t] = {
                    "event_ticker": order.get("event_ticker", ""),
                    "market_mid": order.get("market_mid_at_placement", None),
                }
    print(f"Auditing {len(tickers)} distinct v1 attempted-order tickers")
    audit: list[dict[str, Any]] = []
    for t, ctx in tickers.items():
        if (DATA_V4 / OUT.name).exists():
            pass
        result = audit_one_ticker(t, ctx["event_ticker"], ctx["market_mid"])
        audit.append(result)
        status_short = result["match_status"]
        n_cands = len(result.get("poly_search_candidates", []) or [])
        print(f"  {t} -> {status_short} (cands={n_cands})")
    with open(OUT, "w") as f:
        json.dump(audit, f, indent=2)
    # Print summary
    from collections import Counter
    statuses = Counter(r["match_status"] for r in audit)
    print()
    print("Status counts:")
    for s, n in sorted(statuses.items(), key=lambda kv: -kv[1]):
        print(f"  {s}: {n}")
    print()
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
