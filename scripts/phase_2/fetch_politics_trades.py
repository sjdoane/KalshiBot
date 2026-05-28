"""Phase 2 step 2: pull trades in the [resolution - 35d, resolution - 28d]
window for every settled politics market.

Inputs:
    data/phase2/markets/<series>.parquet    (from fetch_politics_markets.py)

Outputs:
    data/phase2/trades/<series>.parquet     (per-series concatenated)

Per phase-2-methodology.md Section 3 the trading window is
`[resolution_time - 35 days, resolution_time - 28 days]`. The 28-day
pre-resolution margin enforces the anti-Phase-1.5-bug rule (no data
within 28 days of resolution).

Window-widening pre-commitment: if median per-market trades in this
7-day window is < 20, we may widen to 14 days
`[resolution_time - 42d, resolution_time - 28d]` per the methodology.
This script implements both modes via --window-days.

Usage:
    uv run python -m scripts.phase_2.fetch_politics_trades --smoke
    uv run python -m scripts.phase_2.fetch_politics_trades --min-volume 100
    uv run python -m scripts.phase_2.fetch_politics_trades --window-days 14
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
import structlog

from kalshi_bot.config import load_settings
from kalshi_bot.data.kalshi_client import KalshiClient
from kalshi_bot.logging import configure_logging

MARKETS_DIR = Path("data/phase2/markets")
TRADES_DIR = Path("data/phase2/trades")

# Methodology Section 3: end window is 28 days BEFORE resolution.
END_DAYS_BEFORE_RESOLUTION = 28
DEFAULT_WINDOW_DAYS = 7  # 7-day window = [-35d, -28d]


def load_market_index(
    series_ticker: str, min_volume: float, window_days: int
) -> pd.DataFrame:
    df = pd.read_parquet(MARKETS_DIR / f"{series_ticker}.parquet")
    if "volume_fp" in df.columns:
        df["volume_fp"] = df["volume_fp"].astype(float)
    else:
        df["volume_fp"] = pd.to_numeric(df.get("volume", 0), errors="coerce").fillna(0)
    df["close_time"] = pd.to_datetime(df["close_time"], utc=True, format="ISO8601")
    keep = df["volume_fp"] >= min_volume
    df = df.loc[keep, ["ticker", "close_time", "volume_fp"]].reset_index(drop=True)
    df["window_end"] = df["close_time"] - pd.Timedelta(days=END_DAYS_BEFORE_RESOLUTION)
    df["window_start"] = df["window_end"] - pd.Timedelta(days=window_days)
    return df


def fetch_historical_cutoff(client: KalshiClient) -> pd.Timestamp:
    payload = client.get("/historical/cutoff")
    return pd.Timestamp(payload["trades_created_ts"])


def fetch_one_market_trades(
    client: KalshiClient,
    ticker: str,
    window_start: pd.Timestamp,
    window_end: pd.Timestamp,
    cutoff: pd.Timestamp,
) -> list[dict]:
    """Drain trades in the window for one market, splitting at historical
    cutoff. Same pattern as the archived KXHIGH fetcher."""
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
    window_days: int,
) -> int:
    log = structlog.get_logger().bind(series=series_ticker)
    idx = load_market_index(series_ticker, min_volume=min_volume, window_days=window_days)
    if smoke:
        recent = idx[idx["close_time"] > cutoff].head(1)
        older = idx[idx["close_time"] <= cutoff].sort_values("volume_fp", ascending=False).head(1)
        idx = pd.concat([recent, older], ignore_index=True)
    log.info("series_start", n_markets=len(idx), min_volume=min_volume, window_days=window_days)

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
                i=i, n=len(idx), pct=round(100 * i / max(1, len(idx)), 1),
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
    log.info("wrote_parquet", series=series_ticker, n_trades=len(all_trades), path=str(out_path))
    return len(all_trades)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true", help="Fetch one market per series only.")
    parser.add_argument("--min-volume", type=float, default=50.0,
                        help="Per-market lifetime volume floor. Default 50 matches the "
                        "phase-2-methodology Section 2.2 minimum lifetime trades >= 50.")
    parser.add_argument("--series", action="append", help="Restrict to one or more series.")
    parser.add_argument("--progress-every", type=int, default=200)
    parser.add_argument("--window-days", type=int, default=DEFAULT_WINDOW_DAYS,
                        help="VWAP window length in days (ending 28 days before resolution). "
                        "Default 7 = methodology's locked window. Use 14 only per the "
                        "pre-committed window-widening option A in Section 3.")
    args = parser.parse_args()

    configure_logging()
    settings = load_settings()
    log = structlog.get_logger("fetch_politics_trades")

    series_list = args.series or sorted(p.stem for p in MARKETS_DIR.glob("*.parquet"))

    with KalshiClient(settings) as client:
        cutoff = fetch_historical_cutoff(client)
        log.info("cutoff_loaded", cutoff=str(cutoff))
        for s in series_list:
            try:
                run_series(
                    client, s,
                    min_volume=args.min_volume,
                    smoke=args.smoke,
                    progress_every=args.progress_every,
                    cutoff=cutoff,
                    window_days=args.window_days,
                )
            except Exception as exc:
                log.error("series_failed", series=s, error=str(exc))
                continue

    return 0


if __name__ == "__main__":
    sys.exit(main())
