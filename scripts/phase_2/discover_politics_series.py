"""Phase 2 step 0: discover Kalshi politics series tickers.

Lists series with category = "Politics" and writes the index to
`data/phase2/politics_series_index.json` per
research/phase-2-methodology.md Section 2.1.

Also prints summary statistics so we can sanity-check the discovered set
BEFORE pulling settled market data (which takes minutes per series).

Usage:
    uv run python -m scripts.phase_2.discover_politics_series

Output:
    data/phase2/politics_series_index.json    # array of series dicts
    stdout                                    # one line per series with counts
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import structlog

from kalshi_bot.config import load_settings
from kalshi_bot.data.kalshi_client import KalshiClient
from kalshi_bot.logging import configure_logging

OUTPUT_DIR = Path("data/phase2")
OUTPUT_PATH = OUTPUT_DIR / "politics_series_index.json"


def fetch_politics_series(client: KalshiClient) -> list[dict]:
    """Paginate `/series?category=Politics` and return all series records."""
    rows: list[dict] = []
    for row in client.paginate("/series", item_key="series", limit=200, category="Politics"):
        rows.append(row)
    return rows


def main() -> int:
    configure_logging()
    log = structlog.get_logger("discover_politics_series")

    settings = load_settings()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    with KalshiClient(settings) as client:
        series_list = fetch_politics_series(client)

    if not series_list:
        log.warning("no_politics_series_found")
        return 1

    OUTPUT_PATH.write_text(json.dumps(series_list, indent=2, default=str), encoding="utf-8")
    log.info("wrote_series_index", n_series=len(series_list), path=str(OUTPUT_PATH))

    print(f"\n=== {len(series_list)} politics series discovered ===")
    for s in series_list:
        ticker = s.get("ticker") or s.get("series_ticker") or "<unknown>"
        title = s.get("title") or ""
        print(f"  {ticker}: {title[:80]}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
