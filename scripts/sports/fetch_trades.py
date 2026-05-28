"""Sports trades fetcher. Adapt of phase_2/fetch_politics_trades.py."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
import structlog

from kalshi_bot.config import load_settings
from kalshi_bot.data.kalshi_client import KalshiClient
from kalshi_bot.logging import configure_logging

MARKETS_DIR = Path("data/sports/markets")
TRADES_DIR = Path("data/sports/trades")

END_DAYS_BEFORE_RESOLUTION = 28
DEFAULT_WINDOW_DAYS = 14  # sports methodology starts with 14d Option A directly
                          # given the long-horizon strategy expects sparser fills


def load_market_index(
    series_ticker: str, min_volume: float, window_days: int,
    min_lifetime_days: int,
) -> pd.DataFrame:
    df = pd.read_parquet(MARKETS_DIR / f"{series_ticker}.parquet")
    if "volume_fp" in df.columns:
        df["volume_fp"] = pd.to_numeric(df["volume_fp"], errors="coerce").fillna(0)
    else:
        df["volume_fp"] = pd.to_numeric(df.get("volume", 0), errors="coerce").fillna(0)
    df["close_time"] = pd.to_datetime(df["close_time"], utc=True, format="ISO8601")
    df["open_time"] = pd.to_datetime(df["open_time"], utc=True, format="ISO8601")
    df["lifetime_days"] = (df["close_time"] - df["open_time"]).dt.total_seconds() / 86400.0
    keep = (df["volume_fp"] >= min_volume) & (df["lifetime_days"] >= min_lifetime_days)
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
    rows: list[dict] = []
    if window_start < cutoff:
        rows.extend(client.paginate(
            "/historical/trades", item_key="trades", limit=1000, ticker=ticker,
            min_ts=int(window_start.timestamp()),
            max_ts=int(min(window_end, cutoff).timestamp()),
        ))
    if window_end > cutoff:
        rows.extend(client.paginate(
            "/markets/trades", item_key="trades", limit=1000, ticker=ticker,
            min_ts=int(max(window_start, cutoff).timestamp()),
            max_ts=int(window_end.timestamp()),
        ))
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
    min_volume: float, smoke: bool, progress_every: int, cutoff: pd.Timestamp,
    window_days: int, min_lifetime_days: int,
) -> int:
    log = structlog.get_logger().bind(series=series_ticker)
    idx = load_market_index(series_ticker, min_volume=min_volume,
                            window_days=window_days, min_lifetime_days=min_lifetime_days)
    if len(idx) == 0:
        log.info("series_no_markets_after_filters")
        return 0
    if smoke:
        idx = idx.head(2)
    log.info("series_start", n_markets=len(idx), window_days=window_days,
             min_volume=min_volume, min_lifetime_days=min_lifetime_days)

    all_trades: list[dict] = []
    n_with_trades = 0
    for i, row in enumerate(idx.itertuples(index=False), 1):
        trades = fetch_one_market_trades(client, ticker=row.ticker,
            window_start=row.window_start, window_end=row.window_end, cutoff=cutoff)
        if trades:
            n_with_trades += 1
            all_trades.extend(trades)
        if i % progress_every == 0 or i == len(idx):
            log.info("series_progress", i=i, n=len(idx),
                     trades_collected=len(all_trades),
                     markets_with_window_trades=n_with_trades)

    if not all_trades:
        log.warning("no_trades_collected")
        return 0
    out_path = write_series_trades(all_trades, series_ticker)
    log.info("wrote_parquet", n_trades=len(all_trades), path=str(out_path))
    return len(all_trades)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--min-volume", type=float, default=50.0)
    parser.add_argument("--min-lifetime-days", type=int, default=30,
                        help="Long-horizon filter per methodology Section 2.2. Default 30d.")
    parser.add_argument("--series", action="append")
    parser.add_argument("--progress-every", type=int, default=200)
    parser.add_argument("--window-days", type=int, default=DEFAULT_WINDOW_DAYS)
    args = parser.parse_args()

    configure_logging()
    settings = load_settings()
    log = structlog.get_logger("fetch_sports_trades")
    series_list = args.series or sorted(p.stem for p in MARKETS_DIR.glob("*.parquet"))

    with KalshiClient(settings) as client:
        cutoff = fetch_historical_cutoff(client)
        log.info("cutoff_loaded", cutoff=str(cutoff))
        for s in series_list:
            try:
                run_series(client, s,
                    min_volume=args.min_volume, smoke=args.smoke,
                    progress_every=args.progress_every, cutoff=cutoff,
                    window_days=args.window_days, min_lifetime_days=args.min_lifetime_days)
            except Exception as exc:
                log.error("series_failed", series=s, error=str(exc))
                continue
    return 0


if __name__ == "__main__":
    sys.exit(main())
