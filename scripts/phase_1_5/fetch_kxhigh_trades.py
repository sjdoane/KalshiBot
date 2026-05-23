"""Phase 1.5 step 2: pull trades in the methodology window for every market.

For each settled KXHIGH market with non-trivial volume, pull all trades in
the window [close_time - 90min, close_time - 30min]. This is the "60 minutes
ending 30 minutes before close" window locked in research/phase-1.5-
methodology.md. The downstream dataset builder will compute VWAP and
trade-weighted mid from these trades.

Inputs:
    data/raw/kalshi/markets/<series>.parquet  (from fetch_kxhigh_markets.py)

Outputs:
    data/raw/kalshi/trades/<series>.parquet   (per-series concatenated)

Usage:
    uv run python -m scripts.phase_1_5.fetch_kxhigh_trades --smoke
    uv run python -m scripts.phase_1_5.fetch_kxhigh_trades --min-volume 100
"""

from __future__ import annotations

import argparse
import sys
from datetime import timedelta
from pathlib import Path

import pandas as pd
import structlog

from kalshi_bot.config import load_settings
from kalshi_bot.data.kalshi_client import KalshiClient
from kalshi_bot.logging import configure_logging

# Window per research/phase-1.5-methodology.md section 2:
#   mid_price_at_T = VWAP over 60 minutes ending 30 minutes before close.
WINDOW_END_OFFSET = timedelta(minutes=30)
WINDOW_LENGTH = timedelta(minutes=60)

MARKETS_DIR = Path("data/raw/kalshi/markets")
TRADES_DIR = Path("data/raw/kalshi/trades")


def load_market_index(series_ticker: str, min_volume: float) -> pd.DataFrame:
    df = pd.read_parquet(MARKETS_DIR / f"{series_ticker}.parquet")
    df["volume_fp"] = df["volume_fp"].astype(float)
    df["close_time"] = pd.to_datetime(df["close_time"], utc=True, format="ISO8601")
    keep = df["volume_fp"] >= min_volume
    df = df.loc[keep, ["ticker", "close_time", "volume_fp"]].reset_index(drop=True)
    df["window_start"] = df["close_time"] - WINDOW_END_OFFSET - WINDOW_LENGTH
    df["window_end"] = df["close_time"] - WINDOW_END_OFFSET
    return df


def fetch_historical_cutoff(client: KalshiClient) -> pd.Timestamp:
    """Read the boundary timestamp from /historical/cutoff once at startup."""
    payload = client.get("/historical/cutoff")
    return pd.Timestamp(payload["trades_created_ts"])


def fetch_one_market_trades(
    client: KalshiClient,
    ticker: str,
    window_start: pd.Timestamp,
    window_end: pd.Timestamp,
    cutoff: pd.Timestamp,
) -> list[dict]:
    """Drain trades within the methodology window for one market.

    Trades created before `cutoff` are in /historical/trades; trades after
    are in /markets/trades. We pick based on the window, not the market
    close, so straddling markets still get the right endpoint coverage
    for their window. If both regions matter (rare edge case), we hit both.
    """
    rows: list[dict] = []
    if window_start < cutoff:
        rows.extend(
            client.paginate(
                "/historical/trades",
                item_key="trades",
                limit=1000,
                ticker=ticker,
                min_ts=int(window_start.timestamp()),
                max_ts=int(min(window_end, cutoff).timestamp()),
            )
        )
    if window_end > cutoff:
        rows.extend(
            client.paginate(
                "/markets/trades",
                item_key="trades",
                limit=1000,
                ticker=ticker,
                min_ts=int(max(window_start, cutoff).timestamp()),
                max_ts=int(window_end.timestamp()),
            )
        )
    return rows


def write_series_trades(rows: list[dict], series_ticker: str) -> Path:
    df = pd.DataFrame(rows)
    TRADES_DIR.mkdir(parents=True, exist_ok=True)
    out_path = TRADES_DIR / f"{series_ticker}.parquet"
    df.to_parquet(out_path, index=False)
    return out_path


def run_series(
    client: KalshiClient,
    series_ticker: str,
    *,
    min_volume: float,
    smoke: bool,
    progress_every: int,
    cutoff: pd.Timestamp,
) -> int:
    log = structlog.get_logger().bind(series=series_ticker)
    idx = load_market_index(series_ticker, min_volume=min_volume)
    if smoke:
        # For smoke, pick a known-active older market and a recent one so
        # both endpoints get exercised in one shot.
        recent = idx[idx["close_time"] > cutoff].head(1)
        older = idx[idx["close_time"] <= cutoff].sort_values("volume_fp", ascending=False).head(1)
        idx = pd.concat([recent, older], ignore_index=True)
    log.info("series_start", n_markets=len(idx), min_volume=min_volume)

    all_trades: list[dict] = []
    n_with_trades = 0
    for i, row in enumerate(idx.itertuples(index=False), 1):
        trades = fetch_one_market_trades(
            client,
            ticker=row.ticker,
            window_start=row.window_start,
            window_end=row.window_end,
            cutoff=cutoff,
        )
        if trades:
            n_with_trades += 1
            all_trades.extend(trades)
        if i % progress_every == 0 or i == len(idx):
            log.info(
                "series_progress",
                i=i,
                n=len(idx),
                pct=round(100 * i / max(1, len(idx)), 1),
                trades_collected=len(all_trades),
                markets_with_window_trades=n_with_trades,
            )

    if smoke:
        log.info("smoke_done", n_trades=len(all_trades))
        if all_trades:
            log.info("smoke_first_trade", **{k: v for k, v in all_trades[0].items()})
        return len(all_trades)

    if not all_trades:
        log.warning("no_trades_collected", series=series_ticker)
        return 0

    out_path = write_series_trades(all_trades, series_ticker)
    log.info(
        "wrote_parquet",
        series=series_ticker,
        n_trades=len(all_trades),
        path=str(out_path),
    )
    return len(all_trades)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true", help="Fetch one market per series only.")
    parser.add_argument("--min-volume", type=float, default=100.0)
    parser.add_argument("--series", action="append", help="Restrict to one or more series.")
    parser.add_argument("--progress-every", type=int, default=200)
    args = parser.parse_args()

    configure_logging()
    settings = load_settings()
    log = structlog.get_logger("fetch_kxhigh_trades")

    series_list = args.series or sorted(p.stem for p in MARKETS_DIR.glob("*.parquet"))

    with KalshiClient(settings) as client:
        cutoff = fetch_historical_cutoff(client)
        log.info("cutoff_loaded", cutoff=str(cutoff))
        for s in series_list:
            try:
                run_series(
                    client,
                    s,
                    min_volume=args.min_volume,
                    smoke=args.smoke,
                    progress_every=args.progress_every,
                    cutoff=cutoff,
                )
            except Exception as exc:
                log.error("series_failed", series=s, error=str(exc))
                continue

    return 0


if __name__ == "__main__":
    sys.exit(main())
