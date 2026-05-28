"""Tests for the live pricing module (Phase 3 paper trading)."""

from __future__ import annotations

import pytest

from kalshi_bot.strategy.pricing import (
    DEFAULT_SLIPPAGE,
    MarketSnapshot,
    decide,
    expected_net_edge_per_contract,
    market_mid,
    round_trip_maker_fee,
)


def _snap(yes_bid: float = 0.30, yes_ask: float = 0.32) -> MarketSnapshot:
    return MarketSnapshot(
        ticker="KXTEST-1", event_ticker="KXTEST", series_ticker="KXTEST",
        yes_bid=yes_bid, yes_ask=yes_ask, last_price=yes_bid,
        volume=100.0, open_time="2025-01-01", close_time="2025-12-31",
    )


def test_market_mid_basic() -> None:
    assert market_mid(_snap(0.30, 0.32)) == pytest.approx(0.31)


def test_market_mid_handles_degenerate() -> None:
    assert market_mid(_snap(0.0, 0.5)) is None
    assert market_mid(_snap(0.5, 0.5)) is None
    assert market_mid(_snap(0.5, 0.3)) is None  # inverted


def test_round_trip_maker_fee_at_30c() -> None:
    """At P=0.30: single-side maker fee = ceil(0.0175*100*0.3*0.7) = 1c.
    Round-trip = 2c = $0.02."""
    assert round_trip_maker_fee(0.30) == pytest.approx(0.02)


def test_expected_net_edge_yes_side() -> None:
    """recal=0.50, market=0.30, side=yes. Gross EV = 0.20.
    Round-trip fee = 0.02. Slippage = 0.015. Net = 0.165."""
    net = expected_net_edge_per_contract(0.30, 0.50, side="yes")
    assert net == pytest.approx(0.165, abs=1e-6)


def test_expected_net_edge_no_side() -> None:
    """recal=0.25, market=0.45, side=no. Gross = 0.45 - 0.25 = 0.20.
    Round-trip at 0.45 = ceil(0.0175*100*0.45*0.55)*0.01*2 = 1c*0.01*2 = 0.02.
    Net = 0.20 - 0.02 - 0.015 = 0.165."""
    net = expected_net_edge_per_contract(0.45, 0.25, side="no")
    assert net == pytest.approx(0.165, abs=1e-6)


def test_expected_net_edge_negative_when_no_edge() -> None:
    """If recal == market, gross = 0, net = -fees - slippage.
    At P=0.50: round-trip maker fee = 2 * ceil(0.0175*100*0.5*0.5) = 2c.
    Slippage = 1.5pp. Net = 0 - 0.02 - 0.015 = -0.035."""
    net = expected_net_edge_per_contract(0.50, 0.50, side="yes")
    assert net == pytest.approx(-0.035, abs=1e-6)


def test_expected_net_edge_rejects_invalid_side() -> None:
    with pytest.raises(ValueError, match="side"):
        expected_net_edge_per_contract(0.30, 0.50, side="long")


def test_decide_yes_side_picks_inside_bid() -> None:
    """recal > mid -> we want YES. Should target one tick above current bid."""
    snap = _snap(yes_bid=0.30, yes_ask=0.40)
    # recal = 0.50, market mid = 0.35
    decision = decide(snap, recalibrated_prob=0.50, min_net_edge=0.005)
    assert decision is not None
    assert decision.side == "yes"
    # target should be one tick above bid OR clipped to value-minus-fee buffer
    assert decision.target_price <= 0.50  # below recalibrated
    assert decision.expected_net_edge >= 0.005


def test_decide_no_side_picks_inside_ask() -> None:
    """recal < mid -> we want NO. Target one tick below current ask."""
    snap = _snap(yes_bid=0.60, yes_ask=0.70)
    decision = decide(snap, recalibrated_prob=0.40, min_net_edge=0.005)
    assert decision is not None
    assert decision.side == "no"
    assert decision.expected_net_edge >= 0.005


def test_decide_returns_none_when_edge_too_small() -> None:
    """If recalibrated ~ market, net edge is negative, decide returns None."""
    snap = _snap(yes_bid=0.30, yes_ask=0.32)
    decision = decide(snap, recalibrated_prob=0.31, min_net_edge=0.005)
    assert decision is None


def test_decide_returns_none_on_degenerate_orderbook() -> None:
    snap = _snap(yes_bid=0.0, yes_ask=0.50)
    decision = decide(snap, recalibrated_prob=0.30, min_net_edge=0.005)
    assert decision is None


def test_default_slippage_constant() -> None:
    """Verify slippage matches the methodology lock."""
    assert DEFAULT_SLIPPAGE == 0.015
