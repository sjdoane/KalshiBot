"""Tests for the Strategy B favorite-maker module."""

from __future__ import annotations

import numpy as np
import pytest

from kalshi_bot.strategy.favorite_maker import (
    FAVORITE_THRESHOLD,
    SLIPPAGE_ALLOWANCE,
    decide,
    expected_net_edge,
    is_eligible,
    realized_pnl_array,
    realized_pnl_per_contract,
    round_trip_maker_fee,
)


def test_constants_match_methodology() -> None:
    assert FAVORITE_THRESHOLD == 0.70
    assert SLIPPAGE_ALLOWANCE == 0.015


def test_is_eligible_below_threshold() -> None:
    assert is_eligible(0.65) is False
    assert is_eligible(0.50) is False
    assert is_eligible(0.30) is False


def test_is_eligible_above_threshold() -> None:
    assert is_eligible(0.70) is True
    assert is_eligible(0.85) is True
    assert is_eligible(0.95) is True  # at upper cap, inclusive


def test_is_eligible_caps_at_upper() -> None:
    """Upper cap 0.95 (per critic finding: 96-99c data thin, break-even
    too close)."""
    assert is_eligible(0.96) is False
    assert is_eligible(0.99) is False
    assert is_eligible(1.0) is False


def test_round_trip_maker_fee_at_80c() -> None:
    # At P=0.80: single-side maker fee = ceil(0.0175*100*0.80*0.20) = ceil(0.28) = 1c
    # Round-trip = 2c = 0.02
    assert round_trip_maker_fee(0.80) == pytest.approx(0.02)


def test_expected_net_edge_at_80c_with_97pct_yes() -> None:
    """At YES=0.80 and empirical YES-rate=0.97: gross=0.97-0.80=0.17.
    Fee at 0.80=0.02. Slippage=0.015. Net=0.135."""
    net = expected_net_edge(0.80, empirical_yes_rate=0.97)
    assert net == pytest.approx(0.135, abs=1e-6)


def test_decide_picks_favorite() -> None:
    decision = decide(0.80)
    assert decision is not None
    assert decision.side == "yes"
    assert decision.target_price == 0.80
    assert decision.expected_net_edge > 0


def test_decide_skips_non_favorite() -> None:
    assert decide(0.60) is None
    assert decide(0.50) is None


def test_decide_skips_negative_edge() -> None:
    """At a price where empirical YES rate of 0.97 doesn't compensate
    for fees + slippage. At YES=0.99: gross = 0.97 - 0.99 = -0.02. Fee
    = 2 * ceil(0.0175*100*0.99*0.01) = 2*0.0099 → ceil=1c → 2c. Net
    < 0."""
    assert decide(0.99) is None


def test_realized_pnl_yes_wins_at_80c() -> None:
    # bought at 0.80, YES wins (outcome=1). Gross = 1 - 0.80 = 0.20.
    # Net = 0.20 - 0.02 fee - 0.015 slippage = 0.165
    pnl = realized_pnl_per_contract(0.80, 1)
    assert pnl == pytest.approx(0.165, abs=1e-6)


def test_realized_pnl_yes_loses_at_80c() -> None:
    # bought at 0.80, YES loses. Gross = -0.80. Net = -0.80 - 0.02 -
    # 0.015 = -0.835
    pnl = realized_pnl_per_contract(0.80, 0)
    assert pnl == pytest.approx(-0.835, abs=1e-6)


def test_realized_pnl_ineligible_returns_zero() -> None:
    """If we wouldn't have traded, realized P&L is 0 (no position)."""
    assert realized_pnl_per_contract(0.50, 1) == 0.0
    assert realized_pnl_per_contract(0.50, 0) == 0.0


def test_realized_pnl_array_filters_ineligible() -> None:
    yes_prices = np.array([0.30, 0.50, 0.70, 0.85, 0.95, 0.96, 1.0])
    outcomes = np.array([0, 1, 1, 1, 0, 1, 1])
    pnl = realized_pnl_array(yes_prices, outcomes)
    # 0.70, 0.85, 0.95 are eligible (>=0.70 and <=0.95). 0.96, 1.0 are
    # excluded by upper cap. 0.30, 0.50 are excluded by lower threshold.
    assert len(pnl) == 3


def test_realized_pnl_array_matches_per_contract() -> None:
    yes_prices = np.array([0.75, 0.80, 0.90])
    outcomes = np.array([1, 0, 1])
    pnl = realized_pnl_array(yes_prices, outcomes)
    expected = np.array([
        realized_pnl_per_contract(0.75, 1),
        realized_pnl_per_contract(0.80, 0),
        realized_pnl_per_contract(0.90, 1),
    ])
    np.testing.assert_array_almost_equal(pnl, expected, decimal=6)


def test_favorable_dataset_produces_positive_mean() -> None:
    """Synthetic dataset where YES wins 97% at >=70c: mean P&L should be
    positive after fees/slippage."""
    rng = np.random.default_rng(42)
    n = 200
    yes_prices = rng.uniform(0.70, 0.95, size=n)
    outcomes = (rng.uniform(size=n) < 0.97).astype(int)
    pnl = realized_pnl_array(yes_prices, outcomes)
    assert pnl.mean() > 0


# ============================================================
# compute_dynamic_max_concurrent (dynamic-cap helper)
# ============================================================

from kalshi_bot.strategy.favorite_maker import compute_dynamic_max_concurrent


def test_compute_dynamic_max_concurrent_full_bankroll() -> None:
    """At $32 bankroll with $0.95 per-trade ceiling, max = 33."""
    assert compute_dynamic_max_concurrent(32.0, per_trade_max_usd=0.95) == 33


def test_compute_dynamic_max_concurrent_scales_down_on_loss() -> None:
    """Losses shrink the bankroll and therefore the cap."""
    assert compute_dynamic_max_concurrent(16.0, per_trade_max_usd=0.95) == 16
    assert compute_dynamic_max_concurrent(8.0, per_trade_max_usd=0.95) == 8
    assert compute_dynamic_max_concurrent(2.0, per_trade_max_usd=0.95) == 2


def test_compute_dynamic_max_concurrent_scales_up_on_win() -> None:
    """Wins grow the bankroll and the cap."""
    assert compute_dynamic_max_concurrent(64.0, per_trade_max_usd=0.95) == 67
    assert compute_dynamic_max_concurrent(100.0, per_trade_max_usd=0.95) == 105


def test_compute_dynamic_max_concurrent_floor() -> None:
    """Below the per-trade price the bot keeps at least the floor (1)
    to avoid permanent zero state. Pass floor=0 to allow zero."""
    assert compute_dynamic_max_concurrent(0.50, per_trade_max_usd=0.95) == 1
    assert compute_dynamic_max_concurrent(0.0, per_trade_max_usd=0.95) == 1
    assert compute_dynamic_max_concurrent(0.0, per_trade_max_usd=0.95, floor=0) == 0


def test_compute_dynamic_max_concurrent_handles_zero_per_trade() -> None:
    """Defensive: per_trade <= 0 returns the floor without dividing by zero."""
    assert compute_dynamic_max_concurrent(32.0, per_trade_max_usd=0.0) == 1
    assert compute_dynamic_max_concurrent(32.0, per_trade_max_usd=-1.0) == 1
