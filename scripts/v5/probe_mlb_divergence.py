"""V5-A1 supplementary: measure Kalshi vs sportsbook divergence on KXMLBGAME
markets matched to the-odds-api baseball_mlb h2h.

Uses the ALREADY-CACHED live MLB h2h call (no new credits). Pulls Kalshi
KXMLBGAME open markets, matches each Kalshi (away,home,date) tuple to
the the-odds-api event, computes the divergence for the FAVORITE side of
each game (so the sample is biased toward Kalshi YES at favorite prices,
consistent with v1's strategy).
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from kalshi_bot.config import load_settings
from kalshi_bot.data.kalshi_client import KalshiClient

ROOT = Path(__file__).resolve().parents[2]
LIVE_CACHE = ROOT / "data" / "v5" / "odds_api_live_cache"
OUT_JSON = ROOT / "data" / "v5" / "mlb_divergence_probe.json"


TEAM_CODE_TO_NAME = {
    "ARI": "Arizona Diamondbacks", "AZ": "Arizona Diamondbacks",
    "ATL": "Atlanta Braves", "BAL": "Baltimore Orioles", "BOS": "Boston Red Sox",
    "CHC": "Chicago Cubs", "CHI": "Chicago Cubs", "CWS": "Chicago White Sox",
    "CIN": "Cincinnati Reds", "CLE": "Cleveland Guardians", "COL": "Colorado Rockies",
    "DET": "Detroit Tigers", "HOU": "Houston Astros", "KC": "Kansas City Royals",
    "LAA": "Los Angeles Angels", "LAD": "Los Angeles Dodgers", "MIA": "Miami Marlins",
    "MIL": "Milwaukee Brewers", "MIN": "Minnesota Twins", "NYM": "New York Mets",
    "NYY": "New York Yankees", "OAK": "Oakland Athletics", "ATH": "Athletics",
    "PHI": "Philadelphia Phillies", "PIT": "Pittsburgh Pirates", "SD": "San Diego Padres",
    "SEA": "Seattle Mariners", "SF": "San Francisco Giants", "STL": "St. Louis Cardinals",
    "TB": "Tampa Bay Rays", "TEX": "Texas Rangers", "TOR": "Toronto Blue Jays",
    "WSH": "Washington Nationals", "WAS": "Washington Nationals",
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


def parse_kalshi_ticker(ticker: str):
    """KXMLBGAME-26MAY261940NYYKC-NYY -> (date, away_code, home_code, team_code)."""
    m = re.match(r"KXMLBGAME-(\d{2})(\w{3})(\d{2})(\d{4})(\w{2,3})(\w{2,3})-(\w{2,3})", ticker)
    if not m:
        return None
    yy, mon, day, hhmm, away, home, team = m.groups()
    return {"yy": yy, "mon": mon, "day": day, "hhmm": hhmm, "away_code": away, "home_code": home, "team_code": team}


def main():
    # Load cached MLB sportsbook events
    book_cache = json.loads((LIVE_CACHE / "baseball_mlb_h2h_us.json").read_text(encoding="utf-8"))
    book_events = book_cache.get("events", [])
    book_by_teams: dict[tuple[str, str, str], dict] = {}
    for ev in book_events:
        home = ev.get("home_team", "")
        away = ev.get("away_team", "")
        ct = ev.get("commence_time", "")
        if ct and home and away:
            day = ct[:10]  # YYYY-MM-DD
            book_by_teams[(day, away, home)] = ev

    # Pull Kalshi KXMLBGAME markets (read-only)
    s = load_settings()
    client = KalshiClient(s)
    resp = client.get("/markets", series_ticker="KXMLBGAME", status="open", limit=200)
    markets = resp.get("markets", [])

    rows = []
    matched_games: set[tuple] = set()  # dedupe by game key
    for mk in markets:
        ticker = mk.get("ticker", "")
        parsed = parse_kalshi_ticker(ticker)
        if not parsed:
            continue
        team_name = TEAM_CODE_TO_NAME.get(parsed["team_code"])
        away_name = TEAM_CODE_TO_NAME.get(parsed["away_code"])
        home_name = TEAM_CODE_TO_NAME.get(parsed["home_code"])
        # The Kalshi date code: yy=26, mon=MAY, day=27 -> 2026-05-27
        # (Kalshi schedules in ET; we just match by calendar day.)
        month_map = {"JAN":"01","FEB":"02","MAR":"03","APR":"04","MAY":"05","JUN":"06",
                     "JUL":"07","AUG":"08","SEP":"09","OCT":"10","NOV":"11","DEC":"12"}
        try:
            iso_day = f"20{parsed['yy']}-{month_map[parsed['mon']]}-{parsed['day']}"
        except KeyError:
            continue
        # The-odds-api commence_time is UTC; a US 7pm ET game = ~00:00 UTC
        # next day. So try both YYYY-MM-DD and YYYY-MM-DD+1.
        ev = book_by_teams.get((iso_day, away_name, home_name))
        if ev is None:
            # Try +1 day shift (for night games crossing UTC midnight)
            from datetime import datetime, timedelta
            shifted = (datetime.fromisoformat(iso_day) + timedelta(days=1)).isoformat()[:10]
            ev = book_by_teams.get((shifted, away_name, home_name))
        if ev is None:
            continue
        # Compute book implied probability for this team (de-vigged 2-way)
        bookmaker_probs = []
        for bm in ev.get("bookmakers", []):
            for market in bm.get("markets", []):
                if market.get("key") != "h2h":
                    continue
                outcomes = market.get("outcomes", [])
                if len(outcomes) != 2:
                    continue
                names = [o.get("name", "") for o in outcomes]
                ps = [implied_from_decimal(float(o.get("price", 0) or 0)) for o in outcomes]
                if not all(p > 0 for p in ps):
                    continue
                ps = devig_2way(*ps)
                for nm, p in zip(names, ps, strict=False):
                    if nm == team_name:
                        bookmaker_probs.append({"bookmaker": bm.get("key", ""), "p": p})
                        break
        if not bookmaker_probs:
            continue
        ps_vals = [b["p"] for b in bookmaker_probs]
        median_p = float(pd.Series(ps_vals).median())
        yes_bid = mk.get("yes_bid_dollars")
        yes_ask = mk.get("yes_ask_dollars")
        last = mk.get("last_price_dollars")
        if yes_bid not in (None, "", 0) and yes_ask not in (None, "", 0):
            kalshi_mid = (float(yes_bid) + float(yes_ask)) / 2.0
        elif last not in (None, "", 0):
            kalshi_mid = float(last)
        else:
            kalshi_mid = None
        if kalshi_mid is None:
            continue
        divergence_cents = round((kalshi_mid - median_p) * 100, 2)
        # FAVORITE-only filter: keep rows where book_implied >= 0.55 (the
        # natural favorite side). This gives us a sample comparable to
        # V3-C's Polymarket-on-favorites measurement.
        is_favorite = median_p >= 0.55
        rows.append({
            "ticker": ticker,
            "team": team_name,
            "iso_day": iso_day,
            "kalshi_yes_bid": yes_bid,
            "kalshi_yes_ask": yes_ask,
            "kalshi_mid": round(kalshi_mid, 4),
            "sportsbook_implied_median": round(median_p, 4),
            "sportsbook_implied_min": round(min(ps_vals), 4),
            "sportsbook_implied_max": round(max(ps_vals), 4),
            "n_bookmakers": len(ps_vals),
            "divergence_cents": divergence_cents,
            "is_favorite_side": is_favorite,
            "in_v1_eligible_band_70_95": 0.70 <= kalshi_mid <= 0.95,
        })

    df = pd.DataFrame(rows)
    print(f"Total KXMLBGAME-vs-sportsbook pairs: {len(df)}")
    if df.empty:
        OUT_JSON.write_text(json.dumps({"rows": []}, indent=2), encoding="utf-8")
        return
    print(df[["ticker","team","kalshi_mid","sportsbook_implied_median","divergence_cents","is_favorite_side","in_v1_eligible_band_70_95"]].to_string(index=False))

    fav = df[df["is_favorite_side"]]
    print(f"\n=== FAVORITE-side subset (book_implied >= 0.55, n={len(fav)}) ===")
    print(f"Mean Kalshi - Sportsbook: {fav['divergence_cents'].mean():.2f} cents")
    print(f"Median Kalshi - Sportsbook: {fav['divergence_cents'].median():.2f} cents")
    print(f"Std: {fav['divergence_cents'].std():.2f} cents")
    pos = (fav["divergence_cents"] > 0).sum()
    neg = (fav["divergence_cents"] < 0).sum()
    print(f"Kalshi over: {pos} / {len(fav)} = {pos/len(fav)*100:.1f}%")
    print(f"Kalshi under: {neg} / {len(fav)} = {neg/len(fav)*100:.1f}%")

    elig = df[df["in_v1_eligible_band_70_95"]]
    print(f"\n=== v1-eligible-band subset (kalshi_mid in [0.70, 0.95], n={len(elig)}) ===")
    if not elig.empty:
        print(f"Mean Kalshi - Sportsbook: {elig['divergence_cents'].mean():.2f} cents")
        print(f"Median: {elig['divergence_cents'].median():.2f} cents")

    OUT_JSON.write_text(json.dumps({
        "rows": rows,
        "summary": {
            "n_total": len(df),
            "favorite_mean_cents": float(fav["divergence_cents"].mean()) if not fav.empty else None,
            "favorite_median_cents": float(fav["divergence_cents"].median()) if not fav.empty else None,
            "favorite_n": int(len(fav)),
            "v1_band_mean_cents": float(elig["divergence_cents"].mean()) if not elig.empty else None,
            "v1_band_n": int(len(elig)),
        },
    }, indent=2, default=str), encoding="utf-8")


if __name__ == "__main__":
    main()
