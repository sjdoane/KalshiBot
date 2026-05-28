"""Unit tests for v7 Kronos feature helpers.

Tests:
- parse_strike correctness on the KXBTCD ticker format.
- build_context_window honors v6 cache shape and the 120-min preference.
- kronos_to_p_yes_det / _mc correctness on synthetic distributions.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from kalshi_bot_v7.kronos_features import (
    build_context_window,
    clip_p_yes,
    kronos_to_p_yes_det,
    kronos_to_p_yes_mc,
    parse_strike,
)


def test_parse_strike_basic() -> None:
    assert parse_strike("KXBTCD-24DEC1209-T100749.99") == 100749.99
    assert parse_strike("KXBTCD-26JAN0114-T98249.99") == 98249.99
    assert parse_strike("KXBTCD-25JUL1503-T120000") == 120000.0


def test_parse_strike_invalid() -> None:
    with pytest.raises(ValueError):
        parse_strike("KXBTCD-noformat")
    with pytest.raises(ValueError):
        parse_strike("KXBTCD-24DEC1209-X100749.99")


def _make_cb(n: int, start: str = "2025-01-01 00:00:00") -> pd.DataFrame:
    times = pd.date_range(start=start, periods=n, freq="1min", tz="UTC")
    np.random.seed(0)
    close = 100000 + np.cumsum(np.random.normal(0, 50, n))
    return pd.DataFrame({
        "time": times,
        "low": close - 10,
        "high": close + 10,
        "open": close,
        "close": close,
        "volume": np.random.uniform(0.5, 5, n),
    })


def test_build_context_window_happy() -> None:
    cb = _make_cb(300, "2025-01-01 00:00:00")
    t = pd.Timestamp("2025-01-01 02:30:00", tz="UTC")
    df, x_ts, nan_pct = build_context_window(cb, t, 120)
    assert len(df) == 120
    assert nan_pct == 0.0
    assert (df["close"] > 0).all()
    assert "amount" in df.columns


def test_build_context_window_short_history() -> None:
    """Coinbase starts only 70 min before t -> ctx truncates to 70 (>= 60 floor)."""
    cb = _make_cb(70, "2025-01-01 01:20:00")
    t = pd.Timestamp("2025-01-01 02:30:00", tz="UTC")
    df, x_ts, nan_pct = build_context_window(cb, t, 120, min_context_min=60)
    assert len(df) >= 60
    assert nan_pct <= 0.20  # some NaN allowed


def test_build_context_window_too_short() -> None:
    """Coinbase starts only 30 min before t -> below floor -> empty."""
    cb = _make_cb(30, "2025-01-01 02:00:00")
    t = pd.Timestamp("2025-01-01 02:30:00", tz="UTC")
    df, x_ts, nan_pct = build_context_window(cb, t, 120, min_context_min=60)
    assert df.empty
    assert nan_pct == 1.0


def test_kronos_to_p_yes_mc_basic() -> None:
    # 100 samples; 30 above strike -> p_yes = 0.30
    finals = np.array([100.0] * 70 + [200.0] * 30)
    p = kronos_to_p_yes_mc(finals, strike=150.0)
    assert p == pytest.approx(0.30, abs=1e-9)


def test_kronos_to_p_yes_det_normal() -> None:
    # mu=100, sigma=0.10 (10% log-sd); strike=100 -> p_yes ~ 0.50
    p = kronos_to_p_yes_det(100.0, 0.10, 100.0)
    assert 0.45 <= p <= 0.55


def test_kronos_to_p_yes_det_far_below_strike() -> None:
    # mu=100, sigma=0.01 (1% log-sd); strike=110 -> p_yes near 0
    p = kronos_to_p_yes_det(100.0, 0.01, 110.0)
    assert p < 0.05


def test_kronos_to_p_yes_det_far_above_strike() -> None:
    p = kronos_to_p_yes_det(110.0, 0.01, 100.0)
    assert p > 0.99


def test_clip_p_yes() -> None:
    assert clip_p_yes(0.0) == pytest.approx(1e-3)
    assert clip_p_yes(1.0) == pytest.approx(1.0 - 1e-3)
    assert clip_p_yes(0.5) == 0.5
    assert math.isnan(clip_p_yes(float("nan")))
