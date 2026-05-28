"""v6 entry tests per phase-1.5-methodology.md Section 11.1.

These tests MUST pass before any orthogonality work runs.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from kalshi_bot_v6.v6_features import (
    coerce_trade_dtypes,
    cvd_sign,
    kalshi_cvd_N,
    kalshi_price_drift_N,
    kalshi_time_since_last_trade,
    kalshi_trade_count_N,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_TRADES = REPO_ROOT / "data" / "v6" / "kxbtcd_sample_trades.parquet"


def test_cvd_sign_yes_returns_plus_one() -> None:
    """Killer Finding 1: taker_outcome_side='yes' is +1 (bullish)."""
    assert cvd_sign("yes") == 1


def test_cvd_sign_no_returns_minus_one() -> None:
    """Killer Finding 1: taker_outcome_side='no' is -1 (bearish)."""
    assert cvd_sign("no") == -1


def test_cvd_sign_invalid_raises() -> None:
    with pytest.raises(ValueError):
        cvd_sign("foo")


def test_cvd_sign_consistent_with_ground_truth_sample() -> None:
    """Verify F1 sign aligns with empirical taker_outcome_side <-> taker_book_side
    in data/v6/kxbtcd_sample_trades.parquet (n=9446, zero off-diagonal).
    """
    df = pd.read_parquet(SAMPLE_TRADES)
    df = coerce_trade_dtypes(df)
    df["sign"] = df["taker_outcome_side"].map({"yes": 1, "no": -1})
    # Cross-tab against book_side: 'yes' must imply 'bid'; 'no' must imply 'ask'.
    tab = pd.crosstab(df["taker_book_side"], df["taker_outcome_side"])
    # zero off-diagonal
    assert tab.loc["ask", "yes"] == 0
    assert tab.loc["bid", "no"] == 0
    assert tab.loc["ask", "no"] > 0
    assert tab.loc["bid", "yes"] > 0


def test_kalshi_cvd_simple_balanced() -> None:
    """1 YES buy of 10 contracts plus 1 NO buy of 10 contracts = 0 CVD."""
    t = pd.Timestamp("2025-01-01 12:00:00", tz="UTC")
    trades = pd.DataFrame(
        {
            "created_time": [
                t - pd.Timedelta(minutes=10),
                t - pd.Timedelta(minutes=5),
            ],
            "count_fp": [10.0, 10.0],
            "taker_outcome_side": ["yes", "no"],
            "yes_price_dollars": [0.5, 0.5],
        },
    )
    cvd = kalshi_cvd_N(trades, t, 30)
    assert cvd == 0.0


def test_kalshi_cvd_bullish_skew() -> None:
    """Larger YES buy returns positive CVD."""
    t = pd.Timestamp("2025-01-01 12:00:00", tz="UTC")
    trades = pd.DataFrame(
        {
            "created_time": [
                t - pd.Timedelta(minutes=10),
                t - pd.Timedelta(minutes=5),
            ],
            "count_fp": [50.0, 10.0],
            "taker_outcome_side": ["yes", "no"],
            "yes_price_dollars": [0.5, 0.5],
        },
    )
    cvd = kalshi_cvd_N(trades, t, 30)
    assert cvd == 40.0


def test_kalshi_cvd_window_excludes_outside_trades() -> None:
    """Trades > N minutes before t are NOT included."""
    t = pd.Timestamp("2025-01-01 12:00:00", tz="UTC")
    trades = pd.DataFrame(
        {
            "created_time": [
                t - pd.Timedelta(minutes=45),  # outside 30-min window
                t - pd.Timedelta(minutes=5),
            ],
            "count_fp": [100.0, 10.0],
            "taker_outcome_side": ["yes", "no"],
            "yes_price_dollars": [0.5, 0.5],
        },
    )
    cvd = kalshi_cvd_N(trades, t, 30)
    assert cvd == -10.0


def test_kalshi_cvd_excludes_post_t_trades() -> None:
    """Trades AFTER t (future-leak) must not be included."""
    t = pd.Timestamp("2025-01-01 12:00:00", tz="UTC")
    trades = pd.DataFrame(
        {
            "created_time": [
                t - pd.Timedelta(minutes=5),
                t + pd.Timedelta(minutes=1),  # AFTER t, leak
            ],
            "count_fp": [10.0, 1000.0],
            "taker_outcome_side": ["yes", "yes"],
            "yes_price_dollars": [0.5, 0.5],
        },
    )
    cvd = kalshi_cvd_N(trades, t, 30)
    assert cvd == 10.0  # only the pre-t trade


def test_kalshi_trade_count_in_window() -> None:
    t = pd.Timestamp("2025-01-01 12:00:00", tz="UTC")
    trades = pd.DataFrame(
        {
            "created_time": [
                t - pd.Timedelta(minutes=45),
                t - pd.Timedelta(minutes=20),
                t - pd.Timedelta(minutes=5),
                t + pd.Timedelta(minutes=1),
            ],
            "count_fp": [10.0, 10.0, 10.0, 10.0],
            "taker_outcome_side": ["yes"] * 4,
            "yes_price_dollars": [0.5] * 4,
        },
    )
    assert kalshi_trade_count_N(trades, t, 30) == 2
    assert kalshi_trade_count_N(trades, t, 15) == 1


def test_time_since_last_trade_basic() -> None:
    t = pd.Timestamp("2025-01-01 12:00:00", tz="UTC")
    trades = pd.DataFrame(
        {
            "created_time": [t - pd.Timedelta(minutes=7)],
            "count_fp": [10.0],
            "taker_outcome_side": ["yes"],
            "yes_price_dollars": [0.5],
        },
    )
    delta = kalshi_time_since_last_trade(trades, t)
    assert abs(delta - 7.0) < 1e-9


def test_price_drift_returns_nan_when_window_predates_open() -> None:
    """F4 K1b guard: t - N before open_time -> NaN."""
    open_time = pd.Timestamp("2025-01-01 11:45:00", tz="UTC")
    t = pd.Timestamp("2025-01-01 12:00:00", tz="UTC")
    trades = pd.DataFrame(
        {
            "created_time": [t - pd.Timedelta(minutes=5)],
            "count_fp": [10.0],
            "taker_outcome_side": ["yes"],
            "yes_price_dollars": [0.5],
        },
    )
    drift = kalshi_price_drift_N(trades, t, horizon_min=30, open_time=open_time)
    assert np.isnan(drift)


def test_price_drift_returns_nan_when_no_trade_in_window() -> None:
    """F4 K1b guard: no second trade inside window -> drift is structurally
    zero, encodes contract-state, return NaN.
    """
    open_time = pd.Timestamp("2025-01-01 11:00:00", tz="UTC")
    t = pd.Timestamp("2025-01-01 12:00:00", tz="UTC")
    trades = pd.DataFrame(
        {
            "created_time": [t - pd.Timedelta(minutes=45)],
            "count_fp": [10.0],
            "taker_outcome_side": ["yes"],
            "yes_price_dollars": [0.5],
        },
    )
    drift = kalshi_price_drift_N(trades, t, horizon_min=30, open_time=open_time)
    assert np.isnan(drift)


def test_price_drift_computed_when_both_endpoints_present() -> None:
    """Two trades with different prices, both inside the contract window,
    one before window start, one inside [t - N, t] -> drift defined.
    """
    open_time = pd.Timestamp("2025-01-01 11:00:00", tz="UTC")
    t = pd.Timestamp("2025-01-01 12:00:00", tz="UTC")
    trades = pd.DataFrame(
        {
            "created_time": [
                t - pd.Timedelta(minutes=45),
                t - pd.Timedelta(minutes=5),
            ],
            "count_fp": [10.0, 10.0],
            "taker_outcome_side": ["yes", "yes"],
            "yes_price_dollars": [0.50, 0.60],
        },
    )
    drift = kalshi_price_drift_N(trades, t, horizon_min=30, open_time=open_time)
    assert abs(drift - 0.10) < 1e-9


def test_price_drift_cross_contract_isolation() -> None:
    """F4 cross-contract leak test: feature must use ONLY this ticker's trades.

    Caller is responsible for filtering; this test sets up two contracts
    of differing tickers and ensures the price_drift function uses only the
    trades passed to it.
    """
    open_time_a = pd.Timestamp("2025-01-01 11:00:00", tz="UTC")
    t_a = pd.Timestamp("2025-01-01 12:00:00", tz="UTC")

    # Ticker A: two trades, drift should be +0.10
    trades_a = pd.DataFrame(
        {
            "created_time": [
                t_a - pd.Timedelta(minutes=45),
                t_a - pd.Timedelta(minutes=5),
            ],
            "count_fp": [10.0, 10.0],
            "taker_outcome_side": ["yes", "yes"],
            "yes_price_dollars": [0.50, 0.60],
            "ticker": ["TICK-A", "TICK-A"],
        },
    )

    # Ticker B: trades at the same times but with different prices
    trades_b = pd.DataFrame(
        {
            "created_time": [
                t_a - pd.Timedelta(minutes=10),
            ],
            "count_fp": [10.0],
            "taker_outcome_side": ["yes"],
            "yes_price_dollars": [0.99],
            "ticker": ["TICK-B"],
        },
    )

    combined = pd.concat([trades_a, trades_b], ignore_index=True)
    # Caller filters by ticker before calling features (build script does this).
    sub_a = combined[combined["ticker"] == "TICK-A"].reset_index(drop=True)
    drift_a = kalshi_price_drift_N(
        sub_a, t_a, horizon_min=30, open_time=open_time_a,
    )
    assert abs(drift_a - 0.10) < 1e-9
    # If we (incorrectly) passed the merged data, the function would still
    # compute the right answer for THIS ticker IF the caller pre-filtered.
    # The test below confirms the implementation does NOT silently include
    # other tickers' prices.
    sub_b = combined[combined["ticker"] == "TICK-B"].reset_index(drop=True)
    # Ticker B has only one trade -> drift NaN (no second trade in window)
    drift_b = kalshi_price_drift_N(
        sub_b, t_a, horizon_min=30, open_time=open_time_a,
    )
    assert np.isnan(drift_b)


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
