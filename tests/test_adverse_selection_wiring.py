"""Tests for the Round 15c adverse-selection wiring in LiveOrderManager.

Covers:
- Cancel fires when drift exceeds threshold
- Cancel does NOT fire when within threshold
- Cancel does NOT fire for orders younger than min_order_age_minutes
- Multiple resting orders processed independently
- API failure during orderbook pull does not crash the loop
- Cancel API failure leaves order resting (no state corruption)
- Empty resting state is a no-op

Each test uses the MockKalshiClient from test_live_order_manager.py.
"""

from __future__ import annotations

import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator

from kalshi_bot.risk.adverse_selection_monitor import AdverseSelectionConfig
from kalshi_bot.strategy.live_order_manager import (
    LiveOrderManager,
    LiveOrderStatus,
)


class MockKalshiClient:
    """Same shape as the mock in test_live_order_manager.py.

    Kept local to this test module so it does not couple to that
    module's private fixtures.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any]]] = []
        self.post_responses: list[dict[str, Any]] = []
        self.post_raises: list[Exception | None] = []
        self.paginate_responses: list[list[dict[str, Any]]] = []
        self.paginate_raises: list[Exception | None] = []
        self.get_responses: list[dict[str, Any]] = []
        self.get_raises: list[Exception | None] = []
        self.delete_responses: list[dict[str, Any]] = []
        self.delete_raises: list[Exception | None] = []

    def _pop(self, queue: list, raises: list, kind: str) -> Any:
        exc = raises.pop(0) if raises else None
        if exc is not None:
            raise exc
        if not queue:
            raise AssertionError(f"no canned {kind} response staged")
        return queue.pop(0)

    def post(self, endpoint: str, json: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(("POST", endpoint, json))
        return self._pop(self.post_responses, self.post_raises, "POST")

    def get(self, endpoint: str, **params: Any) -> dict[str, Any]:
        self.calls.append(("GET", endpoint, dict(params)))
        return self._pop(self.get_responses, self.get_raises, "GET")

    def delete(self, endpoint: str, **params: Any) -> dict[str, Any]:
        self.calls.append(("DELETE", endpoint, dict(params)))
        return self._pop(self.delete_responses, self.delete_raises, "DELETE")

    def paginate(
        self, endpoint: str, *, item_key: str, **params: Any,
    ) -> Iterator[dict[str, Any]]:
        self.calls.append(("PAGINATE", endpoint, {"item_key": item_key, **params}))
        exc = self.paginate_raises.pop(0) if self.paginate_raises else None
        if exc is not None:
            raise exc
        if not self.paginate_responses:
            return iter([])
        items = self.paginate_responses.pop(0)
        return iter(items)


@pytest.fixture
def tmp_state_path() -> Path:
    with tempfile.TemporaryDirectory() as tmp:
        yield Path(tmp) / "state.json"


def _orderbook_with_mid(yes_bid_dollars: float, yes_ask_dollars: float) -> dict:
    """Build a Kalshi /markets/{ticker}/orderbook response payload with
    yes bid and yes ask at the given dollar levels (each as a single
    top-of-book level). yes_ask is expressed as 1 - no_bid; the parser
    expects orderbook_fp.no_dollars to carry the NO side bid.
    """
    no_bid_dollars = 1.0 - yes_ask_dollars
    return {
        "orderbook_fp": {
            "yes_dollars": [[yes_bid_dollars, 100]],
            "no_dollars": [[no_bid_dollars, 100]],
        },
    }


def _place_aged_resting_order(
    mgr: LiveOrderManager,
    client: MockKalshiClient,
    *,
    ticker: str = "KXMLBGAME-26-LAL-T1",
    series_ticker: str = "KXMLBGAME",
    target_price: float = 0.75,
    age_minutes: int = 30,
    order_id: str = "k-1",
) -> str:
    """Place an order and back-date its placed_ts so it satisfies the
    min_order_age_minutes gate during evaluation. Returns intent_id.
    """
    client.post_responses.append({
        "order_id": order_id, "fill_count": "0", "remaining_count": "1",
    })
    order = mgr.place_live_order(
        ticker=ticker, series_ticker=series_ticker,
        event_ticker=series_ticker + "-26",
        target_price=target_price, contracts=1,
        expected_net_edge=0.05, market_mid_at_placement=target_price,
    )
    past = (datetime.now(UTC) - timedelta(minutes=age_minutes)).isoformat()
    order.placed_ts = past
    mgr.state.resting[order.intent_id].placed_ts = past
    return order.intent_id


def test_no_op_when_no_resting_orders(tmp_state_path: Path) -> None:
    """Empty resting state means no API calls and an empty result."""
    client = MockKalshiClient()
    mgr = LiveOrderManager(client=client, state_path=tmp_state_path)
    cancelled = mgr.reconcile_adverse_selection()
    assert cancelled == []
    assert client.calls == []


def test_cancel_fires_on_adverse_drift(tmp_state_path: Path) -> None:
    """YES bid at 75c, current mid 70c, drift -5c > 3c threshold -> cancel."""
    client = MockKalshiClient()
    mgr = LiveOrderManager(client=client, state_path=tmp_state_path)
    intent_id = _place_aged_resting_order(
        mgr, client, target_price=0.75, age_minutes=30, order_id="k-1",
    )
    # Mid dropped 5c against our bid.
    client.get_responses.append(_orderbook_with_mid(0.69, 0.71))
    client.delete_responses.append({"order_id": "k-1", "reduced_by": 1, "ts_ms": 0})

    cancelled = mgr.reconcile_adverse_selection()

    assert cancelled == [intent_id]
    assert intent_id not in mgr.state.resting
    assert intent_id in mgr.state.closed
    assert mgr.state.closed[intent_id].status == LiveOrderStatus.LIVE_CANCELLED
    delete_call = [c for c in client.calls if c[0] == "DELETE"][0]
    assert delete_call[1] == "/portfolio/events/orders/k-1"


def test_no_cancel_when_drift_within_threshold(tmp_state_path: Path) -> None:
    """YES bid at 75c, current mid 73c, drift -2c < 3c threshold -> no cancel."""
    client = MockKalshiClient()
    mgr = LiveOrderManager(client=client, state_path=tmp_state_path)
    intent_id = _place_aged_resting_order(
        mgr, client, target_price=0.75, age_minutes=30, order_id="k-1",
    )
    client.get_responses.append(_orderbook_with_mid(0.72, 0.74))

    cancelled = mgr.reconcile_adverse_selection()

    assert cancelled == []
    assert intent_id in mgr.state.resting
    assert not any(c[0] == "DELETE" for c in client.calls)


def test_no_cancel_for_young_order(tmp_state_path: Path) -> None:
    """Order placed 5 minutes ago; default min_order_age is 15m -> no cancel
    even when drift would otherwise trigger.
    """
    client = MockKalshiClient()
    mgr = LiveOrderManager(client=client, state_path=tmp_state_path)
    intent_id = _place_aged_resting_order(
        mgr, client, target_price=0.75, age_minutes=5, order_id="k-1",
    )
    # 10c adverse drift, well over threshold, but order is too young.
    client.get_responses.append(_orderbook_with_mid(0.64, 0.66))

    cancelled = mgr.reconcile_adverse_selection()

    assert cancelled == []
    assert intent_id in mgr.state.resting


def test_multiple_orders_processed_independently(tmp_state_path: Path) -> None:
    """Three resting orders on different tickers. Only the one with
    drift > threshold should be cancelled.
    """
    client = MockKalshiClient()
    mgr = LiveOrderManager(client=client, state_path=tmp_state_path)
    a = _place_aged_resting_order(
        mgr, client, ticker="KXA-1", target_price=0.70, order_id="k-a",
    )
    b = _place_aged_resting_order(
        mgr, client, ticker="KXB-1", target_price=0.72, order_id="k-b",
    )
    c = _place_aged_resting_order(
        mgr, client, ticker="KXC-1", target_price=0.80, order_id="k-c",
    )
    # A at mid (no drift), B with -7c drift (cancel), C with +5c (favorable).
    client.get_responses.append(_orderbook_with_mid(0.69, 0.71))   # A mid 0.70
    client.get_responses.append(_orderbook_with_mid(0.64, 0.66))   # B mid 0.65 vs target 72c
    client.get_responses.append(_orderbook_with_mid(0.84, 0.86))   # C mid 0.85 vs target 80c
    client.delete_responses.append({"order_id": "k-1", "reduced_by": 1, "ts_ms": 0})

    cancelled = mgr.reconcile_adverse_selection()

    assert cancelled == [b]
    assert a in mgr.state.resting
    assert b in mgr.state.closed
    assert c in mgr.state.resting


def test_orderbook_fetch_failure_does_not_crash(tmp_state_path: Path) -> None:
    """If the orderbook API call raises, the loop continues without
    error and that ticker is skipped (no cancel without a live mid).
    """
    client = MockKalshiClient()
    mgr = LiveOrderManager(client=client, state_path=tmp_state_path)
    a = _place_aged_resting_order(
        mgr, client, ticker="KXA-1", target_price=0.75, order_id="k-a",
    )
    b = _place_aged_resting_order(
        mgr, client, ticker="KXB-1", target_price=0.75, order_id="k-b",
    )
    # First orderbook fetch raises; second returns a drifted book. The
    # raises queue is independent of get_responses, so we only need ONE
    # response staged for the second call (the first call short-circuits
    # via the raise without consuming a response).
    client.get_raises.append(RuntimeError("rate limit"))
    client.get_responses.append(_orderbook_with_mid(0.65, 0.67))   # mid 0.66
    client.delete_responses.append({"order_id": "k-1", "reduced_by": 1, "ts_ms": 0})

    cancelled = mgr.reconcile_adverse_selection()

    # Only B was cancelled; A was skipped because its orderbook fetch failed.
    assert cancelled == [b]
    assert a in mgr.state.resting
    assert b in mgr.state.closed


def test_orderbook_with_one_sided_book_skipped(tmp_state_path: Path) -> None:
    """When the orderbook returns only a YES side and no NO side
    (one-sided), mid is not computable and the ticker is skipped.
    """
    client = MockKalshiClient()
    mgr = LiveOrderManager(client=client, state_path=tmp_state_path)
    intent_id = _place_aged_resting_order(
        mgr, client, target_price=0.75, order_id="k-1",
    )
    client.get_responses.append({
        "orderbook_fp": {
            "yes_dollars": [[0.72, 100]],
            "no_dollars": [],  # empty NO side
        },
    })

    cancelled = mgr.reconcile_adverse_selection()

    assert cancelled == []
    assert intent_id in mgr.state.resting


def test_cancel_api_failure_leaves_order_resting(tmp_state_path: Path) -> None:
    """If the DELETE call fails (network error), the order stays in
    state.resting and is not moved to closed. The next sweep can retry.
    """
    client = MockKalshiClient()
    mgr = LiveOrderManager(client=client, state_path=tmp_state_path)
    intent_id = _place_aged_resting_order(
        mgr, client, target_price=0.75, order_id="k-1",
    )
    client.get_responses.append(_orderbook_with_mid(0.65, 0.67))
    client.delete_raises.append(RuntimeError("network"))
    client.delete_responses.append({})

    cancelled = mgr.reconcile_adverse_selection()

    assert cancelled == []
    assert intent_id in mgr.state.resting
    assert intent_id not in mgr.state.closed


def test_custom_threshold_applied(tmp_state_path: Path) -> None:
    """A wider threshold should NOT fire on a moderate drift."""
    client = MockKalshiClient()
    mgr = LiveOrderManager(client=client, state_path=tmp_state_path)
    intent_id = _place_aged_resting_order(
        mgr, client, target_price=0.75, order_id="k-1",
    )
    # 5c adverse drift, but threshold is 7c -> no cancel.
    client.get_responses.append(_orderbook_with_mid(0.69, 0.71))

    cancelled = mgr.reconcile_adverse_selection(
        config=AdverseSelectionConfig(
            drift_against_bid_cents=7.0,
            drift_against_ask_cents=7.0,
            min_order_age_minutes=15,
        ),
    )

    assert cancelled == []
    assert intent_id in mgr.state.resting


def test_state_persists_cancellation(tmp_state_path: Path) -> None:
    """After a cancel, the state file is saved and a fresh manager
    sees the same closed state on reload.
    """
    client = MockKalshiClient()
    mgr = LiveOrderManager(client=client, state_path=tmp_state_path)
    intent_id = _place_aged_resting_order(
        mgr, client, target_price=0.75, order_id="k-1",
    )
    client.get_responses.append(_orderbook_with_mid(0.65, 0.67))
    client.delete_responses.append({"order_id": "k-1", "reduced_by": 1, "ts_ms": 0})
    mgr.reconcile_adverse_selection()

    mgr2 = LiveOrderManager(client=client, state_path=tmp_state_path)
    assert intent_id in mgr2.state.closed
    assert intent_id not in mgr2.state.resting
