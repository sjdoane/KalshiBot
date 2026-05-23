"""Probe live trades endpoints for both a recent and older KXHIGHNY market.

The cutoff (per /historical/cutoff) is 2026-03-23. Trades created before
that live in /historical/trades; trades after live somewhere else (likely
/markets/trades or just /trades). This script tries both for a recent and
an older ticker so we know which routing to use.
"""

from __future__ import annotations

import json
import sys

from kalshi_bot.config import load_settings
from kalshi_bot.data.kalshi_client import KalshiClient, KalshiHTTPError
from kalshi_bot.logging import configure_logging


def attempt(client: KalshiClient, label: str, endpoint: str, **params: object) -> int:
    print(f"\n--- {label}: GET {endpoint} {params} ---")
    try:
        payload = client.get(endpoint, **params)
    except KalshiHTTPError as exc:
        print(f"  HTTP {exc.status}: {exc.body[:300]}")
        return 0
    keys = list(payload)
    print(f"  top-level keys: {keys}")
    trades = payload.get("trades", []) or []
    print(f"  trades: {len(trades)}")
    if trades:
        print(f"  first: {json.dumps(trades[0], indent=2, default=str)[:400]}")
    return len(trades)


def main() -> int:
    configure_logging()
    settings = load_settings()

    # A recent market (post-cutoff): trades should NOT be in /historical/trades.
    recent = "KXHIGHNY-26APR28-T66"
    # An older market (pre-cutoff): trades should be in /historical/trades.
    older = "KXHIGHNY-25MAY17-B80.5"

    with KalshiClient(settings) as client:
        attempt(client, "recent_historical", "/historical/trades", ticker=recent, limit=5)
        attempt(client, "recent_markets_trades", "/markets/trades", ticker=recent, limit=5)
        attempt(client, "older_historical", "/historical/trades", ticker=older, limit=5)
        attempt(client, "older_historical_with_ts",
                "/historical/trades",
                ticker=older,
                min_ts=1747533540,
                max_ts=1747540740,
                limit=5)
        attempt(client, "older_markets_trades", "/markets/trades", ticker=older, limit=5)

    return 0


if __name__ == "__main__":
    sys.exit(main())
