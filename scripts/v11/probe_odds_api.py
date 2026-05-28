"""Probe the-odds-api Starter tier to verify the key works and inspect
the historical-odds response shape before bulk fetching.

Runs ONE call (10 credits) to the historical-odds endpoint for an MLB
game from the Becker dataset's known range. Prints the response shape
and the remaining-credits header.

Cost: 10 credits of 20,000.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv


BASE = Path("C:/Users/SamJD/OneDrive/Desktop/AI Projects/Project Kalshi")
load_dotenv(BASE / ".env")

KEY = os.environ.get("THE_ODDS_API_KEY")
if not KEY:
    print("ERROR: THE_ODDS_API_KEY not set in .env", file=sys.stderr)
    raise SystemExit(2)


def probe_historical(sport_key: str, iso_time: str) -> None:
    """Fetch historical odds for one sport at one timestamp."""
    url = f"https://api.the-odds-api.com/v4/historical/sports/{sport_key}/odds"
    params = {
        "apiKey": KEY,
        "regions": "us",
        "markets": "h2h",
        "date": iso_time,
        "oddsFormat": "decimal",
    }
    print(f"--- {sport_key} @ {iso_time}")
    r = httpx.get(url, params=params, timeout=30.0)
    print(f"  status={r.status_code}")
    print(
        f"  remaining={r.headers.get('x-requests-remaining', 'n/a')}, "
        f"used={r.headers.get('x-requests-used', 'n/a')}, "
        f"last={r.headers.get('x-requests-last', 'n/a')}"
    )
    if r.status_code != 200:
        print(f"  body: {r.text[:500]}")
        return
    body = r.json()
    print(f"  response top-level keys: {list(body.keys())}")
    data = body.get("data", [])
    print(f"  data entries (games): {len(data)}")
    if data:
        g = data[0]
        print(f"  first game keys: {list(g.keys())}")
        print(
            f"    id={g.get('id')}, "
            f"home={g.get('home_team')}, away={g.get('away_team')}, "
            f"commence_time={g.get('commence_time')}"
        )
        bks = g.get("bookmakers", [])
        print(f"    n_bookmakers: {len(bks)}")
        if bks:
            bk = bks[0]
            print(
                f"    first bookmaker: key={bk.get('key')}, "
                f"title={bk.get('title')}, "
                f"last_update={bk.get('last_update')}"
            )
            mks = bk.get("markets", [])
            for mk in mks[:1]:
                print(f"    market key: {mk.get('key')}")
                for outcome in mk.get("outcomes", []):
                    print(
                        f"      outcome: name={outcome.get('name')} "
                        f"price={outcome.get('price')}"
                    )


def main() -> int:
    # Test 1: known MLB date in season, from Becker range
    probe_historical("baseball_mlb", "2025-07-15T20:00:00Z")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
