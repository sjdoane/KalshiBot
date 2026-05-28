"""v6 feature definitions.

Per phase-1.5-methodology.md Section 2. All features sampled AS-OF the
horizon timestamp t using only data observable AT THAT TIME.

CVD sign convention (verified empirically on data/v6/kxbtcd_sample_trades.parquet,
n=9446, zero off-diagonal):
- taker_outcome_side='yes' (taker bought YES, bullish)  -> sign = +1
  EQUIVALENT to taker_book_side='bid'
- taker_outcome_side='no'  (taker bought NO, bearish)   -> sign = -1
  EQUIVALENT to taker_book_side='ask'

Killer Finding 1: F1 sign is anchored to taker_outcome_side ground truth,
NOT to the verbal description "ask = taker bought yes" (which is the OPPOSITE
of the data).
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def cvd_sign(taker_outcome_side: str) -> int:
    """Return +1 for 'yes' (bullish), -1 for 'no' (bearish)."""
    if taker_outcome_side == "yes":
        return 1
    if taker_outcome_side == "no":
        return -1
    raise ValueError(f"unknown taker_outcome_side: {taker_outcome_side!r}")


def kalshi_cvd_N(
    trades: pd.DataFrame,
    t: pd.Timestamp,
    horizon_min: int,
) -> float:
    """F1: signed CVD over [t - horizon_min, t].

    trades is a DataFrame for a SINGLE ticker, with columns:
    - created_time (datetime64[ns, UTC])
    - count_fp (float)
    - taker_outcome_side ('yes' or 'no')

    Returns sum over trades in window of count_fp * sign(taker_outcome_side).
    Returns 0.0 if no trades (NOT NaN, since 0-flow has informational meaning).
    """
    if trades.empty:
        return 0.0
    window_start = t - pd.Timedelta(minutes=horizon_min)
    mask = (trades["created_time"] > window_start) & (trades["created_time"] <= t)
    sub = trades[mask]
    if sub.empty:
        return 0.0
    signs = sub["taker_outcome_side"].map({"yes": 1, "no": -1}).astype(float)
    return float((sub["count_fp"].astype(float) * signs).sum())


def kalshi_trade_count_N(
    trades: pd.DataFrame,
    t: pd.Timestamp,
    horizon_min: int,
) -> int:
    """F2: number of trades in [t - horizon_min, t]."""
    if trades.empty:
        return 0
    window_start = t - pd.Timedelta(minutes=horizon_min)
    mask = (trades["created_time"] > window_start) & (trades["created_time"] <= t)
    return int(mask.sum())


def kalshi_time_since_last_trade(
    trades: pd.DataFrame,
    t: pd.Timestamp,
) -> float:
    """F3: minutes between t and most recent trade <= t. NaN if no prior trades."""
    if trades.empty:
        return float("nan")
    mask = trades["created_time"] <= t
    sub = trades[mask]
    if sub.empty:
        return float("nan")
    last_t = sub["created_time"].max()
    delta = (t - last_t).total_seconds() / 60.0
    return float(delta)


def kalshi_mid_at_t(
    trades: pd.DataFrame,
    t: pd.Timestamp,
) -> float:
    """Baseline: last_traded_price (yes_price_dollars) at most recent trade <= t.

    Returns NaN if no prior trades.
    """
    if trades.empty:
        return float("nan")
    mask = trades["created_time"] <= t
    sub = trades[mask].sort_values("created_time")
    if sub.empty:
        return float("nan")
    return float(sub["yes_price_dollars"].iloc[-1])


def kalshi_price_drift_N(
    trades: pd.DataFrame,
    t: pd.Timestamp,
    horizon_min: int,
    open_time: pd.Timestamp,
) -> float:
    """F4: last_traded_price at t minus last_traded_price at t - horizon_min.

    Per Killer Finding 5 (K1b guard):
    - Returns NaN if t - horizon_min falls before contract open_time.
    - Returns NaN if there are no trades in [t - horizon_min, t]
      (no second trade -> drift is structurally 0, encodes contract-state).
    - Returns NaN if there is no trade <= t - horizon_min from this ticker.
    """
    window_start = t - pd.Timedelta(minutes=horizon_min)
    if window_start < open_time:
        return float("nan")
    if trades.empty:
        return float("nan")
    # last trade at or before t
    sub_t = trades[trades["created_time"] <= t]
    if sub_t.empty:
        return float("nan")
    # last trade at or before t - horizon
    sub_start = trades[trades["created_time"] <= window_start]
    if sub_start.empty:
        return float("nan")
    # Require at least one trade strictly inside (window_start, t]
    sub_in = trades[
        (trades["created_time"] > window_start) & (trades["created_time"] <= t)
    ]
    if sub_in.empty:
        return float("nan")
    price_t = float(sub_t.sort_values("created_time")["yes_price_dollars"].iloc[-1])
    price_start = float(
        sub_start.sort_values("created_time")["yes_price_dollars"].iloc[-1],
    )
    return price_t - price_start


def coerce_trade_dtypes(trades: pd.DataFrame) -> pd.DataFrame:
    """Normalize raw /historical/trades columns into numeric / datetime types."""
    if trades.empty:
        return trades
    out = trades.copy()
    if "created_time" in out.columns and not pd.api.types.is_datetime64_any_dtype(
        out["created_time"],
    ):
        out["created_time"] = pd.to_datetime(out["created_time"], utc=True)
    for c in ("count_fp", "yes_price_dollars", "no_price_dollars"):
        if c in out.columns and not pd.api.types.is_numeric_dtype(out[c]):
            out[c] = pd.to_numeric(out[c], errors="coerce")
    return out


def features_for_contract(
    ticker: str,
    open_time: pd.Timestamp,
    close_time: pd.Timestamp,
    trades: pd.DataFrame,
    horizon_min: int,
) -> dict[str, Any]:
    """Compute all Kalshi-internal features for one (ticker, horizon) sample.

    trades must be pre-filtered to this ticker (caller is responsible).
    """
    t = close_time - pd.Timedelta(minutes=horizon_min)
    trades_norm = coerce_trade_dtypes(trades)
    return {
        "ticker": ticker,
        "open_time": open_time,
        "close_time": close_time,
        "horizon_min": horizon_min,
        "t": t,
        "kalshi_mid_at_t": kalshi_mid_at_t(trades_norm, t),
        "time_since_last_trade_at_t": kalshi_time_since_last_trade(trades_norm, t),
        f"kalshi_cvd_{horizon_min}": kalshi_cvd_N(trades_norm, t, horizon_min),
        f"kalshi_trade_count_{horizon_min}": kalshi_trade_count_N(
            trades_norm, t, horizon_min,
        ),
        f"kalshi_price_drift_{horizon_min}": kalshi_price_drift_N(
            trades_norm, t, horizon_min, open_time,
        ),
    }
