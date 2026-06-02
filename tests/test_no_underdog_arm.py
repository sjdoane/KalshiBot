"""Tests for the v18 NO-underdog arm + band sizing.

Covers the strategy decision (decide_favorite_side, band_size_multiplier) and the
real-money-critical order-path side handling in LiveOrderManager: NO-side order
body, side-aware fill-price conversion (Kalshi reports YES terms; a NO order must
record its no_price), and side-aware realized P&L (a NO contract wins when the
market resolves NO).
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator

from kalshi_bot.strategy.favorite_maker import (
    band_size_multiplier,
    decide_favorite_side,
)
from kalshi_bot.strategy.live_order_manager import (
    LiveOrder,
    LiveOrderManager,
    LiveOrderStatus,
)


class MockClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict]] = []
        self.post_responses: list[dict] = []
        self.paginate_responses: list[list[dict]] = []

    def post(self, endpoint: str, json: dict) -> dict:
        self.calls.append(("POST", endpoint, json))
        return self.post_responses.pop(0)

    def get(self, endpoint: str, **params: Any) -> dict:
        self.calls.append(("GET", endpoint, dict(params)))
        return {}

    def delete(self, endpoint: str, **params: Any) -> dict:
        self.calls.append(("DELETE", endpoint, dict(params)))
        return {}

    def paginate(self, endpoint: str, *, item_key: str, **params: Any) -> Iterator[dict]:
        self.calls.append(("PAGINATE", endpoint, {"item_key": item_key, **params}))
        if not self.paginate_responses:
            return iter([])
        return iter(self.paginate_responses.pop(0))


@pytest.fixture
def state_path() -> Iterator[Path]:
    with tempfile.TemporaryDirectory() as tmp:
        yield Path(tmp) / "state.json"


# --- decide_favorite_side --------------------------------------------------
def test_decide_yes_favorite() -> None:
    d = decide_favorite_side(0.80, 0.82)
    assert d is not None
    assert d.side == "yes"
    assert d.target_price == 0.80
    assert d.fav_price == 0.80
    assert d.expected_net_edge > 0


def test_decide_no_favorite_underdog() -> None:
    # Underdog-framed market: yes ~0.25, so no_bid = 1 - yes_ask = 0.74 is the
    # favorite side.
    d = decide_favorite_side(0.24, 0.26)
    assert d is not None
    assert d.side == "no"
    assert d.target_price == pytest.approx(0.74)
    assert d.expected_net_edge > 0


def test_decide_dead_zone_returns_none() -> None:
    # No clear favorite on either side.
    assert decide_favorite_side(0.50, 0.52) is None


def test_decide_yes_takes_precedence_and_mutual_exclusion() -> None:
    # When YES is the favorite, NO cannot also be (yes_bid 0.80 -> no_bid 0.18).
    d = decide_favorite_side(0.80, 0.82)
    assert d.side == "yes"


def test_decide_net_must_be_positive() -> None:
    # At yes 0.95 the net edge after fees+slippage is <= 0, so no trade.
    assert decide_favorite_side(0.95, 0.97) is None


def test_decide_boundaries() -> None:
    assert decide_favorite_side(0.70, 0.72).side == "yes"  # yes_bid at floor
    # no_bid = 1 - 0.30 = 0.70 at the floor -> NO eligible
    d = decide_favorite_side(0.28, 0.30)
    assert d is not None and d.side == "no" and d.target_price == pytest.approx(0.70)


# --- band_size_multiplier --------------------------------------------------
def test_band_multiplier_low_high_outside() -> None:
    assert band_size_multiplier(0.75) == 1.3  # LOW band default m_low
    assert band_size_multiplier(0.90) == 0.8  # heavy band default m_high
    assert band_size_multiplier(0.86) == 0.8  # boundary is heavy (>= 0.86)
    assert band_size_multiplier(0.60) == 0.0  # outside eligible band
    assert band_size_multiplier(0.75, m_low=2.0, m_high=0.5) == 2.0


# --- LiveOrderManager NO-side order body -----------------------------------
def test_place_no_order_body(state_path: Path) -> None:
    client = MockClient()
    client.post_responses.append({"order": {"order_id": "k1", "status": "resting"}})
    mgr = LiveOrderManager(client=client, state_path=state_path)
    order = mgr.place_live_order(
        ticker="KXMLBGAME-X-HOME", series_ticker="KXMLBGAME",
        event_ticker="KXMLBGAME-X", target_price=0.74, contracts=2,
        expected_net_edge=0.06, market_mid_at_placement=0.74, side="no",
    )
    assert order.side == "no"
    _m, _e, body = client.calls[0]
    assert body["side"] == "no"
    assert body["no_price"] == 74
    assert "yes_price" not in body
    assert body["count"] == 2


def test_place_rejects_bad_side(state_path: Path) -> None:
    mgr = LiveOrderManager(client=MockClient(), state_path=state_path)
    with pytest.raises(ValueError):
        mgr.place_live_order(
            ticker="t", series_ticker="s", event_ticker="e", target_price=0.74,
            contracts=1, expected_net_edge=0.0, market_mid_at_placement=0.74,
            side="maybe",
        )


# --- side-aware realized P&L -----------------------------------------------
def _order(side: str, price_cents: int, count: int = 1) -> LiveOrder:
    return LiveOrder(
        intent_id="i", ticker="t", series_ticker="s", event_ticker="e",
        side=side, target_price_cents=price_cents, contracts=count,
        expected_net_edge=0.0, market_mid_at_placement=price_cents / 100.0,
        placed_ts="2026-06-01T00:00:00+00:00", filled_price_cents=price_cents,
        filled_count=count,
    )


def test_pnl_no_order_wins_on_no_outcome(state_path: Path) -> None:
    mgr = LiveOrderManager(client=MockClient(), state_path=state_path)
    # NO bought at 0.74. Market resolves NO (outcome 0): NO wins.
    pnl = mgr._compute_realized_pnl(_order("no", 74), 0)
    # payoff 1-0.74=0.26; fee 2*ceil(1.75*0.74*0.26)/100 = 0.02; net 0.24
    assert pnl == pytest.approx(0.24, abs=1e-9)
    # Market resolves YES (outcome 1): NO loses.
    pnl_loss = mgr._compute_realized_pnl(_order("no", 74), 1)
    assert pnl_loss == pytest.approx(-0.76, abs=1e-9)


def test_pnl_yes_order_regression(state_path: Path) -> None:
    mgr = LiveOrderManager(client=MockClient(), state_path=state_path)
    # YES bought at 0.80. Resolves YES: win 0.20 - fee 0.02 = 0.18.
    assert mgr._compute_realized_pnl(_order("yes", 80), 1) == pytest.approx(0.18, abs=1e-9)
    # Resolves NO: lose 0.80 + fee.
    assert mgr._compute_realized_pnl(_order("yes", 80), 0) == pytest.approx(-0.82, abs=1e-9)


def test_pnl_void_is_fee_only_both_sides(state_path: Path) -> None:
    mgr = LiveOrderManager(client=MockClient(), state_path=state_path)
    # Void (outcome -1): payoff 0 minus the entry/exit maker fee, either side.
    assert mgr._compute_realized_pnl(_order("no", 74), -1) == pytest.approx(-0.02, abs=1e-9)
    assert mgr._compute_realized_pnl(_order("yes", 80), -1) == pytest.approx(-0.02, abs=1e-9)


# --- side-aware fill-price conversion in reconcile_fills --------------------
def test_reconcile_fills_converts_yes_price_to_no_for_no_order(state_path: Path) -> None:
    client = MockClient()
    client.post_responses.append({"order": {"order_id": "ord-1", "status": "resting"}})
    mgr = LiveOrderManager(client=client, state_path=state_path)
    order = mgr.place_live_order(
        ticker="KXMLBGAME-X-HOME", series_ticker="KXMLBGAME",
        event_ticker="KXMLBGAME-X", target_price=0.74, contracts=1,
        expected_net_edge=0.06, market_mid_at_placement=0.74, side="no",
    )
    assert order.intent_id in mgr.state.resting
    # Kalshi reports the fill in YES terms (0.26). The NO order must record its
    # OWN side price: 1 - 0.26 = 0.74 -> 74 cents.
    client.paginate_responses.append([{
        "trade_id": "f1", "order_id": "ord-1", "count_fp": "1",
        "yes_price_dollars": "0.26", "created_time": "2026-06-01T01:00:00Z",
    }])
    changed = mgr.reconcile_fills()
    assert len(changed) == 1
    filled = mgr.state.filled[order.intent_id]
    assert filled.filled_price_cents == 74
    assert filled.status == LiveOrderStatus.LIVE_FILLED


def test_reconcile_fills_yes_order_unchanged(state_path: Path) -> None:
    client = MockClient()
    client.post_responses.append({"order": {"order_id": "ord-2", "status": "resting"}})
    mgr = LiveOrderManager(client=client, state_path=state_path)
    order = mgr.place_live_order(
        ticker="KXMLBGAME-Y-HOME", series_ticker="KXMLBGAME",
        event_ticker="KXMLBGAME-Y", target_price=0.80, contracts=1,
        expected_net_edge=0.05, market_mid_at_placement=0.80, side="yes",
    )
    client.paginate_responses.append([{
        "trade_id": "f2", "order_id": "ord-2", "count_fp": "1",
        "yes_price_dollars": "0.80", "created_time": "2026-06-01T01:00:00Z",
    }])
    mgr.reconcile_fills()
    assert mgr.state.filled[order.intent_id].filled_price_cents == 80
