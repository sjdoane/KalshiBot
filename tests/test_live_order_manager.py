"""Tests for LiveOrderManager (mocked Kalshi client).

Each test exercises one transition in the LIVE order state machine.
All Kalshi I/O is mocked; no network access.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator

from kalshi_bot.strategy.live_order_manager import (
    LiveOrderManager,
    LiveOrderStatus,
)


class MockKalshiClient:
    """Minimal stand-in for KalshiClient that records calls and returns
    pre-staged responses.

    Set `post_responses`, `paginate_responses`, `get_responses`, and
    `delete_responses` to canned data. Set `post_raises`, etc. to make
    a call raise. Calls accumulate in `self.calls` for assertion.
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


def _place(mgr: LiveOrderManager, *, target_price: float = 0.75, contracts: int = 1):
    return mgr.place_live_order(
        ticker="KXNBA-26-LAL", series_ticker="KXNBA", event_ticker="KXNBA-26",
        target_price=target_price, contracts=contracts,
        expected_net_edge=0.05, market_mid_at_placement=target_price,
    )


def test_place_records_intent_before_post(tmp_state_path: Path) -> None:
    """Even before the POST is made, the intent must hit disk so a
    crash mid-POST doesn't lose the client_order_id."""
    client = MockKalshiClient()
    client.post_responses.append({
        "order": {"order_id": "kalshi-abc-1", "status": "resting"},
    })
    mgr = LiveOrderManager(client=client, state_path=tmp_state_path)
    order = _place(mgr, target_price=0.75)
    # After success, intent moved from intents -> resting.
    assert order.status == LiveOrderStatus.LIVE_RESTING
    assert order.order_id == "kalshi-abc-1"
    assert order.intent_id in mgr.state.resting
    assert order.intent_id not in mgr.state.intents
    # The intent IS the client_order_id.
    method, endpoint, body = client.calls[0]
    assert method == "POST"
    assert endpoint == "/portfolio/orders"
    assert body["client_order_id"] == order.intent_id
    assert body["yes_price"] == 75
    assert body["count"] == 1
    assert body["action"] == "buy"
    assert body["side"] == "yes"
    assert body["type"] == "limit"


def test_intent_persisted_before_post_call(tmp_state_path: Path) -> None:
    """Simulate a POST that raises; intent must already be on disk."""
    client = MockKalshiClient()
    client.post_raises.append(RuntimeError("network down"))
    mgr = LiveOrderManager(client=client, state_path=tmp_state_path)
    order = _place(mgr)
    assert order.status == LiveOrderStatus.INTENT_RECORDED
    # Reload from disk; intent is preserved.
    mgr2 = LiveOrderManager(client=client, state_path=tmp_state_path)
    assert order.intent_id in mgr2.state.intents


def test_ack_missing_order_id_keeps_intent(tmp_state_path: Path) -> None:
    """If Kalshi acks with no order_id, treat as failure."""
    client = MockKalshiClient()
    client.post_responses.append({"order": {}})  # no order_id
    mgr = LiveOrderManager(client=client, state_path=tmp_state_path)
    order = _place(mgr)
    assert order.status == LiveOrderStatus.INTENT_RECORDED
    assert order.intent_id in mgr.state.intents


def test_ack_with_filled_status_jumps_to_filled(tmp_state_path: Path) -> None:
    """FOK/IOC path: Kalshi can fill on the POST. Handle inline."""
    client = MockKalshiClient()
    client.post_responses.append({
        "order": {"order_id": "kalshi-fok-1", "status": "filled"},
    })
    mgr = LiveOrderManager(client=client, state_path=tmp_state_path)
    order = _place(mgr, target_price=0.80, contracts=2)
    assert order.status == LiveOrderStatus.LIVE_FILLED
    assert order.filled_count == 2
    assert order.filled_price_cents == 80
    assert order.intent_id in mgr.state.filled


def test_reconcile_intents_finds_lost_ack_order(tmp_state_path: Path) -> None:
    """Intent recorded, POST exception, Kalshi actually has the order."""
    client = MockKalshiClient()
    client.post_raises.append(RuntimeError("connection reset"))
    mgr = LiveOrderManager(client=client, state_path=tmp_state_path)
    order = _place(mgr)
    assert order.status == LiveOrderStatus.INTENT_RECORDED

    # Now Kalshi reports the order is resting under our client_order_id.
    client.paginate_responses.append([{
        "client_order_id": order.intent_id,
        "order_id": "kalshi-lost-1",
        "status": "resting",
    }])
    changed = mgr.reconcile_intents()
    assert len(changed) == 1
    assert order.intent_id in mgr.state.resting
    assert order.intent_id not in mgr.state.intents
    assert mgr.state.resting[order.intent_id].order_id == "kalshi-lost-1"


def test_reconcile_intents_orphan_is_cancelled(tmp_state_path: Path) -> None:
    """Intent recorded, POST exception, Kalshi has nothing."""
    client = MockKalshiClient()
    client.post_raises.append(RuntimeError("timeout"))
    mgr = LiveOrderManager(client=client, state_path=tmp_state_path)
    order = _place(mgr)
    # Kalshi paginate returns empty.
    client.paginate_responses.append([])
    changed = mgr.reconcile_intents()
    assert len(changed) == 1
    assert order.intent_id in mgr.state.closed
    assert mgr.state.closed[order.intent_id].status == LiveOrderStatus.LIVE_CANCELLED


def test_reconcile_fills_applies_full_fill(tmp_state_path: Path) -> None:
    client = MockKalshiClient()
    client.post_responses.append({
        "order": {"order_id": "k-1", "status": "resting"},
    })
    mgr = LiveOrderManager(client=client, state_path=tmp_state_path)
    order = _place(mgr, target_price=0.75, contracts=1)
    # Kalshi reports a fill at our price.
    client.paginate_responses.append([{
        "trade_id": "fill-1", "order_id": "k-1", "count": 1, "yes_price": 75,
        "created_time": "2026-05-23T20:00:00Z",
    }])
    changed = mgr.reconcile_fills()
    assert len(changed) == 1
    assert order.intent_id in mgr.state.filled
    assert order.intent_id not in mgr.state.resting
    settled = mgr.state.filled[order.intent_id]
    assert settled.status == LiveOrderStatus.LIVE_FILLED
    assert settled.filled_count == 1
    assert settled.filled_price_cents == 75


def test_reconcile_fills_idempotent_on_same_fill_id(tmp_state_path: Path) -> None:
    client = MockKalshiClient()
    client.post_responses.append({
        "order": {"order_id": "k-1", "status": "resting"},
    })
    mgr = LiveOrderManager(client=client, state_path=tmp_state_path)
    _place(mgr, target_price=0.75, contracts=1)
    client.paginate_responses.append([{
        "trade_id": "fill-1", "order_id": "k-1", "count": 1, "yes_price": 75,
    }])
    first = mgr.reconcile_fills()
    assert len(first) == 1
    # Replay the same fill; it must NOT be applied again.
    client.paginate_responses.append([{
        "trade_id": "fill-1", "order_id": "k-1", "count": 1, "yes_price": 75,
    }])
    second = mgr.reconcile_fills()
    assert len(second) == 0


def test_reconcile_fills_partial_keeps_in_resting(tmp_state_path: Path) -> None:
    client = MockKalshiClient()
    client.post_responses.append({
        "order": {"order_id": "k-1", "status": "resting"},
    })
    mgr = LiveOrderManager(client=client, state_path=tmp_state_path)
    order = _place(mgr, target_price=0.75, contracts=3)
    # Partial fill: 1 of 3.
    client.paginate_responses.append([{
        "trade_id": "fill-partial-1", "order_id": "k-1", "count": 1, "yes_price": 75,
    }])
    mgr.reconcile_fills()
    assert order.intent_id in mgr.state.resting
    assert mgr.state.resting[order.intent_id].status == LiveOrderStatus.LIVE_PARTIAL
    assert mgr.state.resting[order.intent_id].filled_count == 1


def test_reconcile_settlements_yes_winner(tmp_state_path: Path) -> None:
    client = MockKalshiClient()
    client.post_responses.append({
        "order": {"order_id": "k-1", "status": "filled"},
    })
    mgr = LiveOrderManager(client=client, state_path=tmp_state_path)
    order = _place(mgr, target_price=0.75, contracts=2)
    # Filled inline above. Now market settles YES.
    client.get_responses.append({
        "market": {"status": "settled", "result": "yes",
                   "settled_time": "2026-05-24T01:00:00Z"},
    })
    settled = mgr.reconcile_settlements()
    assert len(settled) == 1
    # 2 contracts * (1.0 - 0.75 - fee). Fee at 0.75 = 2 * ceil(1.75*0.75*0.25)/100
    # = 2 * ceil(0.328)/100 = 2 * 1/100 = 0.02. Net per contract = 0.25 - 0.02
    # = 0.23. Total = 0.46.
    assert settled[0].realized_pnl_usd == pytest.approx(0.46, abs=1e-6)
    assert order.intent_id in mgr.state.closed
    assert order.intent_id not in mgr.state.filled


def test_reconcile_settlements_no_loser(tmp_state_path: Path) -> None:
    client = MockKalshiClient()
    client.post_responses.append({
        "order": {"order_id": "k-1", "status": "filled"},
    })
    mgr = LiveOrderManager(client=client, state_path=tmp_state_path)
    _place(mgr, target_price=0.80, contracts=1)
    client.get_responses.append({
        "market": {"status": "settled", "result": "no"},
    })
    settled = mgr.reconcile_settlements()
    # -0.80 - 0.02 (round-trip fee at 0.80) = -0.82
    fee = 2.0 * 0.01  # ceil(1.75 * 0.80 * 0.20) = ceil(0.28) = 1c, *2 = 2c
    assert settled[0].realized_pnl_usd == pytest.approx(-0.80 - fee, abs=1e-6)


def test_reconcile_settlements_void(tmp_state_path: Path) -> None:
    client = MockKalshiClient()
    client.post_responses.append({
        "order": {"order_id": "k-1", "status": "filled"},
    })
    mgr = LiveOrderManager(client=client, state_path=tmp_state_path)
    _place(mgr, target_price=0.75, contracts=1)
    client.get_responses.append({
        "market": {"status": "settled", "result": "void"},
    })
    settled = mgr.reconcile_settlements()
    # Outcome -1 (void); payoff=0, fees still apply.
    assert settled[0].resolution_outcome == -1
    assert settled[0].realized_pnl_usd is not None


def test_reconcile_settlements_unsettled_market_no_change(tmp_state_path: Path) -> None:
    client = MockKalshiClient()
    client.post_responses.append({
        "order": {"order_id": "k-1", "status": "filled"},
    })
    mgr = LiveOrderManager(client=client, state_path=tmp_state_path)
    _place(mgr, target_price=0.75, contracts=1)
    client.get_responses.append({
        "market": {"status": "open"},
    })
    settled = mgr.reconcile_settlements()
    assert len(settled) == 0
    # Still in filled, not closed.
    assert len(mgr.state.filled) == 1


def test_cancel_all_resting_calls_delete(tmp_state_path: Path) -> None:
    client = MockKalshiClient()
    client.post_responses.append({
        "order": {"order_id": "k-1", "status": "resting"},
    })
    mgr = LiveOrderManager(client=client, state_path=tmp_state_path)
    order = _place(mgr, target_price=0.75)
    client.delete_responses.append({"order": {"status": "cancelled"}})
    ids = mgr.cancel_all_resting()
    assert order.intent_id in ids
    assert order.intent_id in mgr.state.closed
    method, endpoint, _ = client.calls[1]
    assert method == "DELETE"
    assert endpoint == "/portfolio/orders/k-1"


def test_cancel_all_resting_continues_on_failure(tmp_state_path: Path) -> None:
    client = MockKalshiClient()
    client.post_responses.append({
        "order": {"order_id": "k-1", "status": "resting"},
    })
    client.post_responses.append({
        "order": {"order_id": "k-2", "status": "resting"},
    })
    mgr = LiveOrderManager(client=client, state_path=tmp_state_path)
    o1 = _place(mgr, target_price=0.75)
    o2 = mgr.place_live_order(
        ticker="KXNBA-26-BOS", series_ticker="KXNBA", event_ticker="KXNBA-26",
        target_price=0.80, contracts=1,
        expected_net_edge=0.04, market_mid_at_placement=0.80,
    )
    # First cancel fails, second succeeds.
    client.delete_raises.append(RuntimeError("network"))
    client.delete_raises.append(None)
    client.delete_responses.append({"order": {"status": "cancelled"}})
    ids = mgr.cancel_all_resting()
    # One success, one still in resting.
    assert len(ids) == 1
    # Cancellation order is unspecified; just check the counts.
    assert (
        (o1.intent_id in mgr.state.resting and o2.intent_id in mgr.state.closed)
        or (o2.intent_id in mgr.state.resting and o1.intent_id in mgr.state.closed)
    )


def test_state_persists_across_instances(tmp_state_path: Path) -> None:
    client = MockKalshiClient()
    client.post_responses.append({
        "order": {"order_id": "k-1", "status": "resting"},
    })
    mgr1 = LiveOrderManager(client=client, state_path=tmp_state_path)
    o = _place(mgr1)
    mgr2 = LiveOrderManager(client=client, state_path=tmp_state_path)
    assert o.intent_id in mgr2.state.resting


def test_rejects_contracts_below_one(tmp_state_path: Path) -> None:
    client = MockKalshiClient()
    mgr = LiveOrderManager(client=client, state_path=tmp_state_path)
    with pytest.raises(ValueError, match="contracts"):
        mgr.place_live_order(
            ticker="KXNBA-26-LAL", series_ticker="KXNBA", event_ticker="KXNBA-26",
            target_price=0.75, contracts=0,
            expected_net_edge=0.05, market_mid_at_placement=0.75,
        )


def test_rejects_target_price_out_of_range(tmp_state_path: Path) -> None:
    client = MockKalshiClient()
    mgr = LiveOrderManager(client=client, state_path=tmp_state_path)
    with pytest.raises(ValueError, match="target_price_cents"):
        mgr.place_live_order(
            ticker="KXNBA-26-LAL", series_ticker="KXNBA", event_ticker="KXNBA-26",
            target_price=1.5, contracts=1,
            expected_net_edge=0.05, market_mid_at_placement=0.75,
        )


def test_bankroll_accounts_for_realized_pnl(tmp_state_path: Path) -> None:
    client = MockKalshiClient()
    client.post_responses.append({
        "order": {"order_id": "k-1", "status": "filled"},
    })
    mgr = LiveOrderManager(client=client, state_path=tmp_state_path)
    _place(mgr, target_price=0.75, contracts=2)
    client.get_responses.append({
        "market": {"status": "settled", "result": "yes"},
    })
    mgr.reconcile_settlements()
    # +0.46 from the YES winner test above.
    assert mgr.current_live_bankroll() == pytest.approx(25.0 + 0.46, abs=1e-6)


def test_open_order_count_includes_intents_and_resting(tmp_state_path: Path) -> None:
    client = MockKalshiClient()
    client.post_raises.append(RuntimeError("net down"))
    client.post_responses.append({
        "order": {"order_id": "k-2", "status": "resting"},
    })
    mgr = LiveOrderManager(client=client, state_path=tmp_state_path)
    _place(mgr, target_price=0.75)
    _place(mgr, target_price=0.80)
    assert mgr.open_order_count() == 2  # 1 intent + 1 resting


def test_reconcile_fills_parses_count_fp_and_yes_price_dollars(tmp_state_path: Path) -> None:
    """Bug regression (2026-05-23): Kalshi /portfolio/fills uses count_fp
    (fixed-point string) and yes_price_dollars (dollar string) since the
    March 2026 API. Code was reading "count" and "yes_price" which don't
    exist in the response, so filled_count_this was always 0 and the
    fill never transitioned the order to LIVE_FILLED.
    """
    client = MockKalshiClient()
    client.post_responses.append({
        "order": {"order_id": "k-1", "status": "resting"},
    })
    mgr = LiveOrderManager(client=client, state_path=tmp_state_path)
    _place(mgr, target_price=0.70, contracts=1)
    # Kalshi response with the new field names.
    client.paginate_responses.append([{
        "trade_id": "fill-fp-1",
        "fill_id": "fill-fp-1",
        "order_id": "k-1",
        "count_fp": "1.00",
        "yes_price_dollars": "0.7000",
        "created_time": "2026-05-24T04:11:45Z",
        "side": "yes",
    }])
    changed = mgr.reconcile_fills()
    assert len(changed) == 1
    order = list(mgr.state.filled.values())[0]
    assert order.filled_count == 1
    assert order.filled_price_cents == 70
    assert order.status == LiveOrderStatus.LIVE_FILLED


def test_reconcile_fills_handles_partial_count_fp(tmp_state_path: Path) -> None:
    """Partial fills also need count_fp parsing."""
    client = MockKalshiClient()
    client.post_responses.append({
        "order": {"order_id": "k-1", "status": "resting"},
    })
    mgr = LiveOrderManager(client=client, state_path=tmp_state_path)
    mgr.place_live_order(
        ticker="KX-T", series_ticker="KX", event_ticker="KX-T",
        target_price=0.70, contracts=3,
        expected_net_edge=0.10, market_mid_at_placement=0.70,
    )
    client.paginate_responses.append([{
        "trade_id": "fill-fp-partial",
        "order_id": "k-1",
        "count_fp": "1.00",
        "yes_price_dollars": "0.7000",
    }])
    mgr.reconcile_fills()
    o = list(mgr.state.resting.values())[0]
    assert o.filled_count == 1
    assert o.status == LiveOrderStatus.LIVE_PARTIAL


def test_reconcile_fills_falls_back_to_old_field_names(tmp_state_path: Path) -> None:
    """Mocked legacy response uses count / yes_price. Code should still
    parse correctly via fallback (defensive for future API changes)."""
    client = MockKalshiClient()
    client.post_responses.append({
        "order": {"order_id": "k-1", "status": "resting"},
    })
    mgr = LiveOrderManager(client=client, state_path=tmp_state_path)
    _place(mgr, target_price=0.70, contracts=1)
    client.paginate_responses.append([{
        "trade_id": "fill-legacy",
        "order_id": "k-1",
        "count": 1,
        "yes_price": 70,
    }])
    changed = mgr.reconcile_fills()
    assert len(changed) == 1
    o = list(mgr.state.filled.values())[0]
    assert o.filled_count == 1
    assert o.filled_price_cents == 70


def test_reconcile_resting_detects_external_cancellation(tmp_state_path: Path) -> None:
    """If Kalshi has cancelled a resting order externally (e.g., via a
    separate cancel script or operator UI), reconcile_resting must
    detect it and move the order to closed."""
    client = MockKalshiClient()
    client.post_responses.append({
        "order": {"order_id": "k-1", "status": "resting"},
    })
    mgr = LiveOrderManager(client=client, state_path=tmp_state_path)
    o = _place(mgr, target_price=0.70)
    # Kalshi reports the order is no longer resting (empty result).
    client.paginate_responses.append([])
    changed = mgr.reconcile_resting()
    assert len(changed) == 1
    assert o.intent_id in mgr.state.closed
    assert o.intent_id not in mgr.state.resting
    assert mgr.state.closed[o.intent_id].status == LiveOrderStatus.LIVE_CANCELLED


def test_reconcile_resting_detects_external_fill(tmp_state_path: Path) -> None:
    """If Kalshi reports a resting order is now filled, reconcile_resting
    must move it to state.filled."""
    client = MockKalshiClient()
    client.post_responses.append({
        "order": {"order_id": "k-1", "status": "resting"},
    })
    mgr = LiveOrderManager(client=client, state_path=tmp_state_path)
    o = _place(mgr, target_price=0.70)
    client.paginate_responses.append([{
        "client_order_id": o.intent_id,
        "order_id": "k-1",
        "status": "filled",
    }])
    changed = mgr.reconcile_resting()
    assert len(changed) == 1
    assert o.intent_id in mgr.state.filled
    assert o.intent_id not in mgr.state.resting


def test_reconcile_resting_noop_when_still_resting(tmp_state_path: Path) -> None:
    """No state change when Kalshi confirms the order is still resting."""
    client = MockKalshiClient()
    client.post_responses.append({
        "order": {"order_id": "k-1", "status": "resting"},
    })
    mgr = LiveOrderManager(client=client, state_path=tmp_state_path)
    o = _place(mgr, target_price=0.70)
    client.paginate_responses.append([{
        "client_order_id": o.intent_id,
        "order_id": "k-1",
        "status": "resting",
    }])
    changed = mgr.reconcile_resting()
    assert len(changed) == 0
    assert o.intent_id in mgr.state.resting


def test_open_order_count_includes_filled(tmp_state_path: Path) -> None:
    """Bug regression: filled orders MUST count toward the cap so
    capital doesn't escape max_concurrent as positions fill."""
    client = MockKalshiClient()
    client.post_responses.append({
        "order": {"order_id": "k-1", "status": "filled"},
    })
    client.post_responses.append({
        "order": {"order_id": "k-2", "status": "resting"},
    })
    mgr = LiveOrderManager(client=client, state_path=tmp_state_path)
    _place(mgr, target_price=0.75)  # straight to filled
    mgr.place_live_order(
        ticker="KXNBA-26-BOS", series_ticker="KXNBA", event_ticker="KXNBA-26",
        target_price=0.80, contracts=1,
        expected_net_edge=0.04, market_mid_at_placement=0.80,
    )
    # 1 filled + 1 resting = 2 positions counted
    assert mgr.open_order_count() == 2


def test_fills_fetch_failure_does_not_raise(tmp_state_path: Path) -> None:
    client = MockKalshiClient()
    client.post_responses.append({
        "order": {"order_id": "k-1", "status": "resting"},
    })
    mgr = LiveOrderManager(client=client, state_path=tmp_state_path)
    _place(mgr)
    client.paginate_raises.append(RuntimeError("rate limit"))
    changed = mgr.reconcile_fills()
    assert changed == []  # graceful no-op


def test_settle_fetch_failure_continues(tmp_state_path: Path) -> None:
    client = MockKalshiClient()
    client.post_responses.append({
        "order": {"order_id": "k-1", "status": "filled"},
    })
    mgr = LiveOrderManager(client=client, state_path=tmp_state_path)
    _place(mgr)
    client.get_raises.append(RuntimeError("rate limit"))
    settled = mgr.reconcile_settlements()
    assert settled == []
