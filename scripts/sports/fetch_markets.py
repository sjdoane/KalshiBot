"""Sports markets fetcher. Adapt of phase_2/fetch_politics_markets.py."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd
import structlog

from kalshi_bot.config import load_settings
from kalshi_bot.data.kalshi_client import KalshiClient
from kalshi_bot.logging import configure_logging

WINDOW_START = pd.Timestamp("2024-10-01", tz="UTC")
WINDOW_END = pd.Timestamp("2026-04-30", tz="UTC")

SERIES_INDEX_PATH = Path("data/sports/sports_series_index.json")
OUTPUT_DIR = Path("data/sports/markets")


def load_series_tickers() -> list[str]:
    if not SERIES_INDEX_PATH.exists():
        raise FileNotFoundError(
            f"Series index not found at {SERIES_INDEX_PATH}. Run "
            "scripts.sports.discover_series first."
        )
    payload = json.loads(SERIES_INDEX_PATH.read_text(encoding="utf-8"))
    return [s.get("ticker") or s.get("series_ticker") for s in payload if s.get("ticker") or s.get("series_ticker")]


def fetch_series(
    client: KalshiClient,
    series_ticker: str,
    *,
    sample: int | None = None,
) -> list[dict]:
    log = structlog.get_logger().bind(series=series_ticker)
    log.info("fetch_series_start")
    seen: set[str] = set()
    rows: list[dict] = []

    def collect(it, source: str) -> int:
        added = 0
        for row in it:
            ticker = row.get("ticker")
            if not ticker or ticker in seen:
                continue
            seen.add(ticker)
            rows.append(row)
            added += 1
            if sample is not None and len(rows) >= sample:
                break
        log.info("fetch_endpoint_done", source=source, added=added, total=len(rows))
        return added

    live_iter = client.paginate(
        "/markets",
        item_key="markets",
        limit=200,
        series_ticker=series_ticker,
        status="settled",
        min_close_ts=int(WINDOW_START.timestamp()),
        max_close_ts=int(WINDOW_END.timestamp()),
    )
    collect(live_iter, source="markets")
    if sample is not None and len(rows) >= sample:
        return rows

    hist_iter = client.paginate(
        "/historical/markets",
        item_key="markets",
        limit=200,
        series_ticker=series_ticker,
        min_close_ts=int(WINDOW_START.timestamp()),
        max_close_ts=int(WINDOW_END.timestamp()),
    )
    collect(hist_iter, source="historical/markets")

    log.info("fetch_series_done", n_markets=len(rows))
    return rows


def write_parquet(rows: list[dict], series_ticker: str) -> Path:
    df = pd.DataFrame(rows)
    df["series_ticker"] = series_ticker
    out_path = OUTPUT_DIR / f"{series_ticker}.parquet"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    for col in df.columns:
        if df[col].dtype == object and df[col].apply(lambda x: isinstance(x, dict | list)).any():
            df[col] = df[col].apply(lambda x: json.dumps(x) if x is not None else None)
    df.to_parquet(out_path, index=False)
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", type=int, default=None)
    parser.add_argument("--series", action="append")
    args = parser.parse_args()

    configure_logging()
    log = structlog.get_logger("fetch_sports_markets")
    settings = load_settings()
    targets = args.series or load_series_tickers()
    log.info("targets", n_series=len(targets))

    with KalshiClient(settings) as client:
        for series in targets:
            try:
                rows = fetch_series(client, series, sample=args.sample)
            except Exception as exc:
                log.error("fetch_failed", series=series, error=str(exc))
                continue
            if not rows:
                continue
            if args.sample is not None:
                print(f"\n=== {series} sample ({len(rows)}) ===")
                print("columns:", sorted(rows[0]))
                print(json.dumps(rows[0], indent=2, default=str))
                continue
            out = write_parquet(rows, series)
            log.info("wrote_parquet", series=series, n_markets=len(rows), path=str(out))

    return 0


if __name__ == "__main__":
    sys.exit(main())
