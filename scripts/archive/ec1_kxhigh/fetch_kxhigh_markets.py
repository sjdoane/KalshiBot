"""Phase 1.5 step 1: pull settled KXHIGH market metadata from Kalshi.

Iterates over the daily-high-temperature series for each of NY/CHI/MIA/LAX/DEN,
pulls all settled markets in the configured date window, and writes parquet
files under data/raw/kalshi/markets/<series>.parquet.

Default mode pulls the full corpus per research/phase-1.5-methodology.md
(2024-01-01 to 2026-04-30). `--sample N` pulls only the first N markets per
series and dumps the parsed schema to stdout; use this to verify the
response shape before committing to the full ~hour-long pull.

Usage:
    uv run python -m scripts.phase_1_5.fetch_kxhigh_markets --sample 5
    uv run python -m scripts.phase_1_5.fetch_kxhigh_markets

Output:
    data/raw/kalshi/markets/KXHIGHNY.parquet
    data/raw/kalshi/markets/KXHIGHCHI.parquet
    ...
"""

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

# Series tickers per Agent B's brief; verified against Kalshi search.
KXHIGH_SERIES = {
    "KXHIGHNY": "NY",
    "KXHIGHCHI": "CHI",
    "KXHIGHMIA": "MIA",
    "KXHIGHLAX": "LAX",
    "KXHIGHDEN": "DEN",
}

# Window from research/phase-1.5-methodology.md section 2.
WINDOW_START = pd.Timestamp("2024-01-01", tz="UTC")
WINDOW_END = pd.Timestamp("2026-04-30", tz="UTC")

OUTPUT_DIR = Path("data/raw/kalshi/markets")


def fetch_series(
    client: KalshiClient,
    series_ticker: str,
    *,
    sample: int | None = None,
) -> list[dict]:
    """Pull settled markets for one series across both endpoints.

    Kalshi splits market data at `/historical/cutoff`: anything settled before
    the cutoff is in `/historical/markets`; anything after is in `/markets`.
    We hit both and dedupe by ticker. Returns list of raw dicts.
    """
    log = structlog.get_logger().bind(series=series_ticker)
    log.info("fetch_series_start")
    seen_tickers: set[str] = set()
    rows: list[dict] = []

    def collect(payload_iter, source: str) -> int:
        added = 0
        for row in payload_iter:
            ticker = row.get("ticker")
            if not ticker or ticker in seen_tickers:
                continue
            seen_tickers.add(ticker)
            rows.append(row)
            added += 1
            if sample is not None and len(rows) >= sample:
                break
        log.info("fetch_endpoint_done", source=source, added=added, total=len(rows))
        return added

    # 1) Live endpoint: status=settled gives recently-resolved markets.
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
        log.info("fetch_series_done", n_markets=len(rows))
        return rows

    # 2) Historical endpoint: everything settled before the cutoff. The
    #    series_ticker filter narrows by series; we drain the cursor.
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
    """Materialize to parquet. We attach the city before writing."""
    city = KXHIGH_SERIES[series_ticker]
    df = pd.DataFrame(rows)
    df["city"] = city
    df["series_ticker"] = series_ticker
    out_path = OUTPUT_DIR / f"{series_ticker}.parquet"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # Cast object-typed nested fields to JSON strings so parquet can store them.
    for col in df.columns:
        if df[col].dtype == object and df[col].apply(lambda x: isinstance(x, dict | list)).any():
            df[col] = df[col].apply(lambda x: json.dumps(x) if x is not None else None)
    df.to_parquet(out_path, index=False)
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--sample",
        type=int,
        default=None,
        help="If set, pull only N markets per series and dump schema to stdout.",
    )
    parser.add_argument(
        "--series",
        action="append",
        choices=list(KXHIGH_SERIES),
        help="Restrict to one or more series. Repeatable. Defaults to all 5.",
    )
    args = parser.parse_args()

    configure_logging()
    log = structlog.get_logger("fetch_kxhigh_markets")

    settings = load_settings()
    target = args.series or list(KXHIGH_SERIES)

    with KalshiClient(settings) as client:
        for series in target:
            try:
                rows = fetch_series(client, series, sample=args.sample)
            except Exception as exc:
                log.error("fetch_failed", series=series, error=str(exc))
                continue
            if not rows:
                log.warning("no_markets", series=series)
                continue
            if args.sample is not None:
                print(f"\n=== {series} sample ({len(rows)} markets) ===")
                print("columns:", sorted(rows[0]))
                print("\nfirst row:")
                print(json.dumps(rows[0], indent=2, default=str))
                continue
            out = write_parquet(rows, series)
            log.info("wrote_parquet", series=series, n_markets=len(rows), path=str(out))

    return 0


if __name__ == "__main__":
    sys.exit(main())
