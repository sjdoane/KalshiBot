"""Probe Kalshi's /candlesticks and /historical/trades endpoints.

We need per-market mid prices at T = (close - 30 min). Two candidate paths:

  1) /markets/{ticker}/candlesticks - per-market OHLCV bars at minute
     resolution. Cheap if the response carries vwap/volume; expensive if we
     have to issue one request per market across ~30k markets.

  2) /historical/trades - tick-level. If it supports a series_ticker filter
     we can drain all trades for a series in one paginated walk; if only
     per-market, it's the same cost as option 1 but with bigger payloads.

This script picks one historical KXHIGHNY market (high volume preferred)
and probes both endpoints, printing the response shape so we can wire the
proper fetcher.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

from kalshi_bot.config import load_settings
from kalshi_bot.data.kalshi_client import KalshiClient, KalshiHTTPError
from kalshi_bot.logging import configure_logging

MARKETS_DIR = Path("data/raw/kalshi/markets")


def pick_high_volume_ticker() -> tuple[str, pd.Timestamp]:
    """Return (ticker, close_time) for a historical KXHIGHNY market with
    above-median volume, so the probe sees real trade data."""
    df = pd.read_parquet(MARKETS_DIR / "KXHIGHNY.parquet")
    df["volume_fp"] = df["volume_fp"].astype(float)
    df = df[df["volume_fp"] > df["volume_fp"].quantile(0.75)]
    df["close_time"] = pd.to_datetime(df["close_time"], utc=True, format="ISO8601")
    # Pick a 2025 market - new enough that the API still has its trades,
    # old enough that it lived through a full trading day.
    df_2025 = df[(df["close_time"].dt.year == 2025) & (df["close_time"].dt.month <= 6)]
    row = df_2025.sort_values("volume_fp", ascending=False).iloc[0]
    return row["ticker"], row["close_time"]


def probe_candlesticks(client: KalshiClient, ticker: str, close_time: pd.Timestamp) -> None:
    print(f"\n=== /markets/{ticker}/candlesticks ===")
    end_ts = int(close_time.timestamp())
    start_ts = end_ts - 60 * 60 * 2  # 2 hours before close
    # Kalshi's candlestick endpoint typically requires series_ticker context
    # in the URL: /series/{series_ticker}/markets/{ticker}/candlesticks
    series = ticker.split("-", 1)[0]
    endpoint = f"/series/{series}/markets/{ticker}/candlesticks"
    try:
        payload = client.get(
            endpoint,
            start_ts=start_ts,
            end_ts=end_ts,
            period_interval=1,  # 1-minute bars
        )
    except KalshiHTTPError as exc:
        print(f"  HTTP {exc.status}: {exc.body[:300]}")
        # Try alternative location
        endpoint = f"/markets/{ticker}/candlesticks"
        print(f"  retrying at {endpoint}")
        try:
            payload = client.get(endpoint, start_ts=start_ts, end_ts=end_ts, period_interval=1)
        except KalshiHTTPError as exc2:
            print(f"  HTTP {exc2.status}: {exc2.body[:300]}")
            return
    print(f"  top-level keys: {list(payload)}")
    candles = payload.get("candlesticks", [])
    print(f"  candles: {len(candles)}")
    if candles:
        print(f"  first candle:\n{json.dumps(candles[0], indent=2, default=str)}")
        print(f"  last candle:\n{json.dumps(candles[-1], indent=2, default=str)}")


def probe_historical_trades(client: KalshiClient, ticker: str) -> None:
    print(f"\n=== /historical/trades ticker={ticker} ===")
    try:
        payload = client.get("/historical/trades", limit=3, ticker=ticker)
    except KalshiHTTPError as exc:
        print(f"  HTTP {exc.status}: {exc.body[:300]}")
        return
    print(f"  top-level keys: {list(payload)}")
    trades = payload.get("trades", [])
    print(f"  trades returned: {len(trades)}")
    if trades:
        print(f"  first trade:\n{json.dumps(trades[0], indent=2, default=str)}")

    # Try with series_ticker filter (would be a big win if it works)
    series = ticker.split("-", 1)[0]
    print(f"\n=== /historical/trades series_ticker={series} (does it filter?) ===")
    try:
        payload = client.get("/historical/trades", limit=3, series_ticker=series)
    except KalshiHTTPError as exc:
        print(f"  HTTP {exc.status}: {exc.body[:300]}")
        return
    trades = payload.get("trades", [])
    print(f"  trades returned: {len(trades)}")
    if trades:
        print(f"  first trade ticker: {trades[0].get('ticker')!r}")
        print(f"  first trade:\n{json.dumps(trades[0], indent=2, default=str)}")


def main() -> int:
    configure_logging()
    settings = load_settings()

    ticker, close_time = pick_high_volume_ticker()
    print(f"probe target: {ticker}, close_time={close_time}")

    with KalshiClient(settings) as client:
        probe_candlesticks(client, ticker, close_time)
        probe_historical_trades(client, ticker)

    return 0


if __name__ == "__main__":
    sys.exit(main())
