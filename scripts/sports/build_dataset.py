"""Sports dataset builder. Adapt of phase_2/build_dataset.py.

Joins per-series markets + trades into one DataFrame for the sports gate.
Schema (matches gate_sports.evaluate):

    ticker, series_ticker, event_ticker,
    market_open_time, market_close_time,
    outcome, mid_price_at_T_small, mid_price_at_T_all,
    n_trades_in_window, n_small_trades_in_window,
    one_sided_flow_pct,
    league, is_binary_market, lifetime_days
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import structlog

from kalshi_bot.data.sports import is_tradable_event_size, market_tier, tag_league
from kalshi_bot.logging import configure_logging

RAW_MARKETS_DIR = Path("data/sports/markets")
RAW_TRADES_DIR = Path("data/sports/trades")
PROCESSED_DIR = Path("data/processed")
OUT_PATH = PROCESSED_DIR / "sports_dataset.parquet"

SMALL_TRADE_MAX_CONTRACTS = 10
# Round 3.1 revision: lowered from 20 to 10. The Round 3 dataset with
# MIN_TRADES_IN_WINDOW=20 produced 237 markets but only 19 eligible
# in the test partitions; bootstrap CI on n=19 with SD=49pp is too
# wide to validate. Lowering the trades-in-window floor to 10 brings
# in more markets; the per-market VWAP becomes noisier with fewer
# trades but the aggregate gate has more statistical power.
MIN_TRADES_IN_WINDOW = 5
# Long-horizon filter per sports methodology Section 2.2 (revised per
# critic finding 8: 30d matches Le's >1mo bin and excludes single-game).
MIN_LIFETIME_DAYS = 30

CORPUS_START = pd.Timestamp("2024-10-01", tz="UTC")
CORPUS_END = pd.Timestamp("2026-04-30", tz="UTC")


def _vwap_and_flow_per_ticker(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame(columns=[
            "ticker", "mid_price_at_T_all", "mid_price_at_T_small",
            "n_trades_in_window", "n_small_trades_in_window", "one_sided_flow_pct",
        ])
    t = trades.copy()
    if "yes_price_dollars" in t.columns:
        t["yes_price"] = t["yes_price_dollars"].astype(float)
    elif "yes_price" in t.columns:
        t["yes_price"] = t["yes_price"].astype(float) / 100.0
    else:
        raise ValueError("trades missing yes_price column")
    if "count_fp" in t.columns:
        t["count"] = t["count_fp"].astype(float)
    else:
        t["count"] = t["count"].astype(float)
    out: list[dict] = []
    for ticker, g in t.groupby("ticker"):
        all_w = g["count"].sum()
        if all_w <= 0:
            continue
        vwap_all = float((g["yes_price"] * g["count"]).sum() / all_w)
        small = g[g["count"] <= SMALL_TRADE_MAX_CONTRACTS]
        if small["count"].sum() > 0:
            vwap_small = float((small["yes_price"] * small["count"]).sum() / small["count"].sum())
        else:
            vwap_small = float("nan")
        if "taker_side" in g.columns:
            yes_side = (g["taker_side"].str.lower() == "yes").sum()
            no_side = (g["taker_side"].str.lower() == "no").sum()
            total = yes_side + no_side
            one_sided = float(max(yes_side, no_side) / total) if total > 0 else float("nan")
        else:
            one_sided = float("nan")
        out.append({
            "ticker": ticker,
            "mid_price_at_T_all": vwap_all,
            "mid_price_at_T_small": vwap_small,
            "n_trades_in_window": int(len(g)),
            "n_small_trades_in_window": int(len(small)),
            "one_sided_flow_pct": one_sided,
        })
    return pd.DataFrame(out)


def build_for_series(series_ticker: str) -> pd.DataFrame:
    markets_path = RAW_MARKETS_DIR / f"{series_ticker}.parquet"
    trades_path = RAW_TRADES_DIR / f"{series_ticker}.parquet"
    if not markets_path.exists():
        return pd.DataFrame()
    markets = pd.read_parquet(markets_path)
    if trades_path.exists():
        trades = pd.read_parquet(trades_path)
        vwap = _vwap_and_flow_per_ticker(trades)
    else:
        vwap = pd.DataFrame(columns=[
            "ticker", "mid_price_at_T_all", "mid_price_at_T_small",
            "n_trades_in_window", "n_small_trades_in_window", "one_sided_flow_pct",
        ])
    df = markets.merge(vwap, on="ticker", how="left")
    df["series_ticker"] = series_ticker
    df["market_open_time"] = pd.to_datetime(df["open_time"], utc=True, format="ISO8601")
    df["market_close_time"] = pd.to_datetime(df["close_time"], utc=True, format="ISO8601")
    df["outcome"] = df["result"].map({"yes": 1, "no": 0})
    df["league"] = tag_league(df)
    df["market_tier"] = market_tier(df)
    df["is_tradable_event_size"] = is_tradable_event_size(df)
    df["lifetime_days"] = (df["market_close_time"] - df["market_open_time"]).dt.total_seconds() / 86400.0

    keep = (
        df["outcome"].notna()
        & df["is_tradable_event_size"]
        & (df["market_close_time"] >= CORPUS_START)
        & (df["market_close_time"] <= CORPUS_END)
        & (df["lifetime_days"] >= MIN_LIFETIME_DAYS)
        & df["mid_price_at_T_small"].notna()
        & (df["mid_price_at_T_small"] > 0)
        & (df["mid_price_at_T_small"] < 1)
        & (df["n_trades_in_window"] >= MIN_TRADES_IN_WINDOW)
        & df["one_sided_flow_pct"].notna()
    )
    df = df.loc[keep].copy()
    df["outcome"] = df["outcome"].astype(int)

    return df[[
        "ticker", "series_ticker", "event_ticker",
        "market_open_time", "market_close_time",
        "outcome", "mid_price_at_T_small", "mid_price_at_T_all",
        "n_trades_in_window", "n_small_trades_in_window", "one_sided_flow_pct",
        "league", "market_tier", "is_tradable_event_size", "lifetime_days",
    ]]


def build_full_dataset() -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for parquet in sorted(RAW_MARKETS_DIR.glob("*.parquet")):
        frame = build_for_series(parquet.stem)
        if not frame.empty:
            frames.append(frame)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def main() -> int:
    configure_logging()
    log = structlog.get_logger("build_sports_dataset")
    df = build_full_dataset()
    if df.empty:
        log.error("empty_dataset")
        return 1
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT_PATH, index=False)
    summary = {
        "rows": len(df),
        "unique_series": int(df["series_ticker"].nunique()),
        "date_min": str(df["market_close_time"].min()),
        "date_max": str(df["market_close_time"].max()),
        "outcome_rate": round(float(df["outcome"].mean()), 4),
        "median_trades_in_window": int(df["n_trades_in_window"].median()),
        "median_small_trades_in_window": int(df["n_small_trades_in_window"].median()),
        "median_lifetime_days": int(df["lifetime_days"].median()),
        "mid_small_p50": round(float(df["mid_price_at_T_small"].quantile(0.50)), 4),
        "leagues": df["league"].value_counts().to_dict(),
    }
    log.info("dataset_summary", **summary, path=str(OUT_PATH))
    print("\n=== Sports dataset summary ===")
    for k, v in summary.items():
        if k != "leagues":
            print(f"  {k}: {v}")
    print("  league distribution:")
    for lg, n in summary["leagues"].items():
        print(f"    {lg:12s} {n}")
    print(f"  output: {OUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
