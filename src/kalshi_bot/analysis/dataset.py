"""Build the analysis-ready dataset from raw market and trade parquet files.

One row per settled KXHIGH market. The columns the gate consumes:

    ticker                  (str)
    series_ticker           (KX-prefixed canonical)
    city                    (str: NY/CHI/MIA/LAX/DEN)
    occurrence_date         (date the high temperature was measured)
    market_open_time        (pd.Timestamp, UTC)
    market_close_time       (pd.Timestamp, UTC)
    strike_F                (float: NWS-reported high must exceed this)
    observed_high_F         (float: actual high reported at settlement)
    outcome                 (int: 1 if YES resolved, 0 if NO)
    mid_price_at_T          (float in (0,1): trade VWAP in the 60-min
                            window ending 30 min before close)
    n_trades_in_window      (int)
    volume_in_window        (float, contract count)

Rows excluded:
    - non-binary results (e.g., 'scalar', 'void')
    - markets with zero trades in the window (mid undefined)
    - VWAP outside (0, 1) (shouldn't happen, but defensive)
    - markets whose event_ticker we couldn't parse to a date

The window definition (30 min before close, 60 min long) is locked by
research/phase-1.5-methodology.md section 2.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from kalshi_bot.data.kxhigh import SERIES_TO_CITY, parse_occurrence_date

RAW_MARKETS_DIR = Path("data/raw/kalshi/markets")
RAW_TRADES_DIR = Path("data/raw/kalshi/trades")
PROCESSED_DIR = Path("data/processed")


def _vwap_per_ticker(trades: pd.DataFrame) -> pd.DataFrame:
    """Return one row per ticker with VWAP + window statistics."""
    if trades.empty:
        return pd.DataFrame(
            columns=["ticker", "mid_price_at_T", "n_trades_in_window", "volume_in_window"]
        )
    t = trades.copy()
    t["yes_price"] = t["yes_price_dollars"].astype(float)
    t["count"] = t["count_fp"].astype(float)
    grouped = t.groupby("ticker")
    return grouped.apply(
        lambda g: pd.Series(
            {
                "mid_price_at_T": (
                    (g["yes_price"] * g["count"]).sum() / g["count"].sum()
                    if g["count"].sum() > 0
                    else float("nan")
                ),
                "n_trades_in_window": len(g),
                "volume_in_window": float(g["count"].sum()),
            }
        ),
        include_groups=False,
    ).reset_index()


def build_for_series(series_ticker: str) -> pd.DataFrame:
    markets_path = RAW_MARKETS_DIR / f"{series_ticker}.parquet"
    trades_path = RAW_TRADES_DIR / f"{series_ticker}.parquet"
    if not markets_path.exists():
        return pd.DataFrame()
    markets = pd.read_parquet(markets_path)

    if trades_path.exists():
        trades = pd.read_parquet(trades_path)
        vwap = _vwap_per_ticker(trades)
    else:
        vwap = pd.DataFrame(
            columns=["ticker", "mid_price_at_T", "n_trades_in_window", "volume_in_window"]
        )

    df = markets.merge(vwap, on="ticker", how="left")

    df["city"] = SERIES_TO_CITY.get(series_ticker)
    df["series_ticker"] = series_ticker
    df["occurrence_date"] = df["event_ticker"].apply(parse_occurrence_date)
    df["market_open_time"] = pd.to_datetime(df["open_time"], utc=True, format="ISO8601")
    df["market_close_time"] = pd.to_datetime(df["close_time"], utc=True, format="ISO8601")
    df["strike_F"] = df["floor_strike"].astype(float)
    df["observed_high_F"] = pd.to_numeric(df["expiration_value"], errors="coerce")
    df["outcome"] = df["result"].map({"yes": 1, "no": 0})

    keep = (
        df["outcome"].notna()
        & df["occurrence_date"].notna()
        & df["mid_price_at_T"].notna()
        & (df["mid_price_at_T"] > 0)
        & (df["mid_price_at_T"] < 1)
    )
    df = df.loc[keep].copy()
    df["outcome"] = df["outcome"].astype(int)

    return df[
        [
            "ticker",
            "series_ticker",
            "city",
            "occurrence_date",
            "market_open_time",
            "market_close_time",
            "strike_F",
            "observed_high_F",
            "outcome",
            "mid_price_at_T",
            "n_trades_in_window",
            "volume_in_window",
        ]
    ]


def build_full_dataset() -> pd.DataFrame:
    """Concatenate per-series datasets into one DataFrame."""
    frames: list[pd.DataFrame] = []
    for parquet in sorted(RAW_MARKETS_DIR.glob("*.parquet")):
        frame = build_for_series(parquet.stem)
        if not frame.empty:
            frames.append(frame)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def write_dataset(df: pd.DataFrame, name: str = "kxhigh_dataset") -> Path:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PROCESSED_DIR / f"{name}.parquet"
    df.to_parquet(out_path, index=False)
    return out_path
