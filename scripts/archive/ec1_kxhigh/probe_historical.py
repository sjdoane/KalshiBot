"""Probe Kalshi's /historical/markets to learn its parameter shape.

Per Agent A's brief, /markets only has ~3 months of live data; older data
moves to /historical/*. This script tries a few request shapes against
/historical/markets and prints whatever we get so we can wire the real
fetcher correctly.
"""

from __future__ import annotations

import json
import sys

from kalshi_bot.config import load_settings
from kalshi_bot.data.kalshi_client import KalshiClient, KalshiHTTPError
from kalshi_bot.logging import configure_logging


def try_call(client: KalshiClient, label: str, endpoint: str, **params: object) -> None:
    print(f"\n--- {label} ---")
    print(f"GET {endpoint} params={params}")
    try:
        payload = client.get(endpoint, **params)
    except KalshiHTTPError as exc:
        print(f"HTTP {exc.status}: {exc.body[:200]}")
        return
    except Exception as exc:
        print(f"ERROR: {exc}")
        return
    keys = list(payload)
    print(f"top-level keys: {keys}")
    for k in keys:
        v = payload[k]
        if isinstance(v, list):
            print(f"  {k}: list of {len(v)}")
            if v:
                print(f"    first item keys: {sorted(v[0]) if isinstance(v[0], dict) else type(v[0])}")
                if isinstance(v[0], dict):
                    print(f"    first item sample: {json.dumps(v[0], indent=2, default=str)[:800]}")
        else:
            sval = str(v)
            if len(sval) > 100:
                sval = sval[:100] + "..."
            print(f"  {k}: {sval}")


def main() -> int:
    configure_logging()
    settings = load_settings()
    with KalshiClient(settings) as client:
        # Per Agent A: historical endpoint list includes /historical/markets.
        try_call(
            client,
            "historical_markets_default",
            "/historical/markets",
            limit=5,
            series_ticker="KXHIGHNY",
        )
        try_call(
            client,
            "historical_markets_status_settled",
            "/historical/markets",
            limit=5,
            series_ticker="KXHIGHNY",
            status="settled",
        )
        # Maybe it requires explicit time range
        try_call(
            client,
            "historical_markets_2024",
            "/historical/markets",
            limit=5,
            series_ticker="KXHIGHNY",
            min_close_ts=1704067200,    # 2024-01-01
            max_close_ts=1735689600,    # 2025-01-01
        )
        # Cutoff endpoint may tell us where /markets ends and /historical/ starts
        try_call(client, "historical_cutoff", "/historical/cutoff")
    return 0


if __name__ == "__main__":
    sys.exit(main())
