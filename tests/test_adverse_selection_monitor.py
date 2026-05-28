"""Tests for the adverse selection monitor (Round 15b)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from kalshi_bot.risk.adverse_selection_monitor import (
    AdverseSelectionConfig,
    CancelRecommendation,
    RestingOrderView,
    evaluate_resting_orders,
)


def _iso(dt: datetime) -> str:
    return dt.replace(tzinfo=UTC).isoformat()


def _now() -> datetime:
    return datetime.now(UTC)


def _order(
    intent_id: str = "x",
    ticker: str = "KXMLBGAME-1",
    side: str = "yes",
    target: int = 70,
    age_minutes: int = 30,
) -> RestingOrderView:
    placed = _now() - timedelta(minutes=age_minutes)
    return RestingOrderView(
        intent_id=intent_id,
        ticker=ticker,
        side=side,
        target_price_cents=target,
        placed_ts=placed.isoformat(),
    )


def test_no_cancellations_when_mid_at_bid() -> None:
    orders = [_order(target=70)]
    mids = {"KXMLBGAME-1": 70.0}
    recs = evaluate_resting_orders(orders, mids, config=AdverseSelectionConfig(),
                                   now_iso=_now().isoformat())
    assert recs == []


def test_cancel_yes_bid_on_adverse_drift() -> None:
    """YES bid at 70c, mid dropped to 66c (drift -4c); threshold is 3c."""
    orders = [_order(side="yes", target=70)]
    mids = {"KXMLBGAME-1": 66.0}
    recs = evaluate_resting_orders(orders, mids, config=AdverseSelectionConfig(),
                                   now_iso=_now().isoformat())
    assert len(recs) == 1
    assert recs[0].drift_cents == pytest.approx(-4.0)
    assert "drift -4.0c" in recs[0].reason


def test_yes_bid_no_cancel_within_threshold() -> None:
    """YES bid at 70c, mid dropped to 68c (drift -2c); under 3c threshold."""
    orders = [_order(side="yes", target=70)]
    mids = {"KXMLBGAME-1": 68.0}
    recs = evaluate_resting_orders(orders, mids, config=AdverseSelectionConfig(),
                                   now_iso=_now().isoformat())
    assert recs == []


def test_yes_bid_no_cancel_when_mid_above_bid() -> None:
    """YES bid at 70c, mid moved UP to 75c (drift +5c); not adverse, no cancel."""
    orders = [_order(side="yes", target=70)]
    mids = {"KXMLBGAME-1": 75.0}
    recs = evaluate_resting_orders(orders, mids, config=AdverseSelectionConfig(),
                                   now_iso=_now().isoformat())
    assert recs == []


def test_min_age_prevents_immediate_cancel() -> None:
    """Order placed 5 minutes ago; min_age is 15 minutes; no cancel even on drift."""
    orders = [_order(side="yes", target=70, age_minutes=5)]
    mids = {"KXMLBGAME-1": 60.0}  # 10c adverse drift
    recs = evaluate_resting_orders(orders, mids, config=AdverseSelectionConfig(),
                                   now_iso=_now().isoformat())
    assert recs == []


def test_custom_threshold() -> None:
    """With a 5c threshold, 4c drift should not cancel."""
    orders = [_order(side="yes", target=70)]
    mids = {"KXMLBGAME-1": 66.0}  # 4c drift
    recs = evaluate_resting_orders(
        orders, mids,
        config=AdverseSelectionConfig(drift_against_bid_cents=5.0),
        now_iso=_now().isoformat(),
    )
    assert recs == []


def test_ticker_not_in_mids_skipped() -> None:
    orders = [_order(side="yes", target=70, ticker="KXSOMETHING-1")]
    mids = {}
    recs = evaluate_resting_orders(orders, mids, config=AdverseSelectionConfig(),
                                   now_iso=_now().isoformat())
    assert recs == []


def test_no_side_cancel_on_mid_above_ask() -> None:
    """NO side: we 'ask' YES at 30c (equivalent to bid NO at 70c). Mid moved
    UP to 35c; drift +5c which is adverse to a NO maker. Cancel.
    """
    orders = [_order(side="no", target=30)]
    mids = {"KXMLBGAME-1": 35.0}
    recs = evaluate_resting_orders(orders, mids, config=AdverseSelectionConfig(),
                                   now_iso=_now().isoformat())
    assert len(recs) == 1
    assert recs[0].drift_cents == pytest.approx(5.0)


def test_multiple_orders_only_drifted_ones_cancelled() -> None:
    orders = [
        _order(intent_id="a", ticker="KXA-1", side="yes", target=70),
        _order(intent_id="b", ticker="KXB-1", side="yes", target=72),
        _order(intent_id="c", ticker="KXC-1", side="yes", target=80),
    ]
    mids = {"KXA-1": 70.0, "KXB-1": 65.0, "KXC-1": 80.0}
    recs = evaluate_resting_orders(orders, mids, config=AdverseSelectionConfig(),
                                   now_iso=_now().isoformat())
    assert len(recs) == 1
    assert recs[0].intent_id == "b"
