"""Sports series discovery. Writes data/sports/sports_series_index.json."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import structlog

from kalshi_bot.config import load_settings
from kalshi_bot.data.kalshi_client import KalshiClient
from kalshi_bot.logging import configure_logging

OUTPUT_DIR = Path("data/sports")
OUTPUT_PATH = OUTPUT_DIR / "sports_series_index.json"


def fetch_sports_series(client: KalshiClient) -> list[dict]:
    rows: list[dict] = []
    for row in client.paginate("/series", item_key="series", limit=200, category="Sports"):
        rows.append(row)
    return rows


def main() -> int:
    configure_logging()
    log = structlog.get_logger("discover_sports_series")
    settings = load_settings()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with KalshiClient(settings) as client:
        series_list = fetch_sports_series(client)
    if not series_list:
        log.warning("no_sports_series_found")
        return 1
    OUTPUT_PATH.write_text(json.dumps(series_list, indent=2, default=str), encoding="utf-8")
    log.info("wrote_series_index", n_series=len(series_list), path=str(OUTPUT_PATH))
    print(f"\n=== {len(series_list)} sports series discovered ===")
    for s in series_list[:30]:
        ticker = s.get("ticker") or s.get("series_ticker") or "<unknown>"
        title = s.get("title") or ""
        print(f"  {ticker}: {title[:80]}")
    if len(series_list) > 30:
        print(f"  ... and {len(series_list) - 30} more")
    return 0


if __name__ == "__main__":
    sys.exit(main())
