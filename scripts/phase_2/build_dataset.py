"""Phase 2 step 3: build the analysis-ready politics dataset.

Joins per-series markets + trades parquet files into one DataFrame with the
schema the gate (gate_phase2.evaluate) consumes:

    ticker                     str
    series_ticker              str
    event_ticker               str
    market_open_time           pd.Timestamp (UTC)
    market_close_time          pd.Timestamp (UTC)
    outcome                    int  (1 if YES resolved, else 0)
    mid_price_at_T_small       float  VWAP of trades with count <= 10
    mid_price_at_T_all         float  VWAP of all trades in window
    n_trades_in_window         int
    n_small_trades_in_window   int
    one_sided_flow_pct         float  max(buy, sell) / total
    is_federal_election_market bool
    is_binary_market           bool

Filters applied (matching phase-2-methodology Section 2.2 and 4):
- Binary contracts only (is_binary_market == True)
- Minimum 20 trades in trading window
- Outcome present (yes/no settle)
- VWAP small in (0, 1) (defensive)

Section 4's mid-band, one-sided-flow, and price-conditional filters are
NOT applied here - those are evaluated INSIDE the gate per-test-partition.

Outputs:
    data/processed/politics_phase2_dataset.parquet
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import structlog

from kalshi_bot.data.politics import is_binary_market, tag_federal_election
from kalshi_bot.logging import configure_logging

RAW_MARKETS_DIR = Path("data/phase2/markets")
RAW_TRADES_DIR = Path("data/phase2/trades")
PROCESSED_DIR = Path("data/processed")
OUT_PATH = PROCESSED_DIR / "politics_phase2_dataset.parquet"

# Small-trade threshold per phase-2-methodology Section 3
SMALL_TRADE_MAX_CONTRACTS = 10
# Methodology section 4 minimum trades-in-window
MIN_TRADES_IN_WINDOW = 20
# Corpus window per phase-2-methodology Section 2.2. The Kalshi historical
# endpoint sometimes returns pre-window markets despite the min_close_ts
# parameter (~23 markets in our pull leaked through); enforce here.
CORPUS_START = pd.Timestamp("2024-10-01", tz="UTC")
CORPUS_END = pd.Timestamp("2026-04-30", tz="UTC")


def _vwap_and_flow_per_ticker(trades: pd.DataFrame) -> pd.DataFrame:
    """Compute per-ticker VWAP (all and small), counts, and one-sided-flow pct."""
    if trades.empty:
        return pd.DataFrame(
            columns=[
                "ticker", "mid_price_at_T_all", "mid_price_at_T_small",
                "n_trades_in_window", "n_small_trades_in_window",
                "one_sided_flow_pct",
            ]
        )
    t = trades.copy()
    # Kalshi trade fields: `yes_price` cents (int), `count` contracts (int),
    # `taker_side` "yes" or "no". Names match the archived KXHIGH fetcher.
    if "yes_price_dollars" in t.columns:
        t["yes_price"] = t["yes_price_dollars"].astype(float)
    elif "yes_price" in t.columns:
        # Trade endpoint returns yes_price in cents (1-99).
        t["yes_price"] = t["yes_price"].astype(float) / 100.0
    else:
        raise ValueError("trades parquet missing yes_price column")
    if "count_fp" in t.columns:
        t["count"] = t["count_fp"].astype(float)
    else:
        t["count"] = t["count"].astype(float)

    out_rows: list[dict] = []
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
        n_trades = len(g)
        n_small = len(small)
        if "taker_side" in g.columns:
            yes_side = (g["taker_side"].str.lower() == "yes").sum()
            no_side = (g["taker_side"].str.lower() == "no").sum()
            total_sides = yes_side + no_side
            one_sided = float(max(yes_side, no_side) / total_sides) if total_sides > 0 else float("nan")
        else:
            one_sided = float("nan")
        out_rows.append(
            {
                "ticker": ticker,
                "mid_price_at_T_all": vwap_all,
                "mid_price_at_T_small": vwap_small,
                "n_trades_in_window": int(n_trades),
                "n_small_trades_in_window": int(n_small),
                "one_sided_flow_pct": one_sided,
            }
        )
    return pd.DataFrame(out_rows)


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
        vwap = pd.DataFrame(
            columns=[
                "ticker", "mid_price_at_T_all", "mid_price_at_T_small",
                "n_trades_in_window", "n_small_trades_in_window",
                "one_sided_flow_pct",
            ]
        )

    df = markets.merge(vwap, on="ticker", how="left")
    df["series_ticker"] = series_ticker
    df["market_open_time"] = pd.to_datetime(df["open_time"], utc=True, format="ISO8601")
    df["market_close_time"] = pd.to_datetime(df["close_time"], utc=True, format="ISO8601")
    df["outcome"] = df["result"].map({"yes": 1, "no": 0})
    df["is_federal_election_market"] = tag_federal_election(df)
    df["is_binary_market"] = is_binary_market(df)

    # Locked filters (Section 2.2 and Section 4 of the methodology). Note:
    # one_sided_flow_pct must be non-NaN; a missing taker_side column upstream
    # would otherwise silently bypass the Section 4 adverse-selection filter.
    keep = (
        df["outcome"].notna()
        & df["is_binary_market"]
        & (df["market_close_time"] >= CORPUS_START)
        & (df["market_close_time"] <= CORPUS_END)
        & df["mid_price_at_T_small"].notna()
        & (df["mid_price_at_T_small"] > 0)
        & (df["mid_price_at_T_small"] < 1)
        & (df["n_trades_in_window"] >= MIN_TRADES_IN_WINDOW)
        & df["one_sided_flow_pct"].notna()
    )
    df = df.loc[keep].copy()
    df["outcome"] = df["outcome"].astype(int)

    return df[
        [
            "ticker",
            "series_ticker",
            "event_ticker",
            "market_open_time",
            "market_close_time",
            "outcome",
            "mid_price_at_T_small",
            "mid_price_at_T_all",
            "n_trades_in_window",
            "n_small_trades_in_window",
            "one_sided_flow_pct",
            "is_federal_election_market",
            "is_binary_market",
        ]
    ]


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
    log = structlog.get_logger("build_dataset_phase2")

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
        "fed_election_rate": round(float(df["is_federal_election_market"].mean()), 4),
        "median_trades_in_window": int(df["n_trades_in_window"].median()),
        "median_small_trades_in_window": int(df["n_small_trades_in_window"].median()),
        "mid_small_p50": round(float(df["mid_price_at_T_small"].quantile(0.50)), 4),
        "mid_small_p05": round(float(df["mid_price_at_T_small"].quantile(0.05)), 4),
        "mid_small_p95": round(float(df["mid_price_at_T_small"].quantile(0.95)), 4),
    }
    log.info("dataset_summary", **summary, path=str(OUT_PATH))
    print("\n=== Phase 2 dataset summary ===")
    for k, v in summary.items():
        print(f"  {k}: {v}")
    print(f"  output: {OUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
