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
        # Simulate Kalshi server-side behavior so tests exercise the real
        # contract: a `ticker` filter returns only that market's records, and
        # the walk truncates at max_pages * limit (max_pages None = drain all).
        ticker = params.get("ticker")
        if ticker is not None:
            items = [r for r in items if r.get("ticker") == ticker]
        max_pages = params.get("max_pages")
        if max_pages is not None:
            items = items[: max_pages * params.get("limit", 100)]
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


def _settled_order(intent_id: str, placed_ts: str, outcome, pnl, side: str = "yes"):
    from kalshi_bot.strategy.live_order_manager import LiveOrder
    return LiveOrder(
        intent_id=intent_id, ticker=f"KX-{intent_id}", series_ticker="",
        event_ticker=f"KX-{intent_id}", side=side, target_price_cents=80,
        contracts=1, expected_net_edge=0.1, market_mid_at_placement=0.8,
        placed_ts=placed_ts, status=LiveOrderStatus.LIVE_SETTLED,
        resolution_outcome=outcome, realized_pnl_usd=pnl,
    )


def test_realized_summary_since_cutoff_and_side_aware(tmp_state_path: Path) -> None:
    """research/v20 tally: counts only settled bets PLACED at/after the cutoff,
    drops pre-cutoff and unsettled (no-pnl) records, parses +00:00 and Z, AND is
    SIDE-AWARE so the NO-underdog arm's wins/losses are not inverted. The counts
    below differ from a naive outcome-based bucketing, so this guards that bug."""
    mgr = LiveOrderManager(client=MockKalshiClient(), state_path=tmp_state_path)
    mgr.state.closed = {
        # NO bets resolving NO are WINS (side-aware); outcome-based would call
        # them losses. Placed today (post-cutoff).
        "a": _settled_order("a", "2026-06-03T18:00:00+00:00", 0, 0.20, side="no"),
        "b": _settled_order("b", "2026-06-03T19:00:00+00:00", 0, 0.18, side="no"),
        # NO bet resolving YES is a LOSS (side-aware); outcome-based -> win.
        "c": _settled_order("c", "2026-06-03T20:00:00+00:00", 1, -0.85, side="no"),
        # Old (pre-cutoff) bets, must be excluded by the cutoff.
        "d": _settled_order("d", "2026-05-25T00:00:00+00:00", 0, -0.80, side="yes"),
        "e": _settled_order("e", "2026-05-26T00:00:00+00:00", 1, 0.25, side="yes"),
        # Unsettled (no pnl) must be ignored entirely.
        "f": _settled_order("f", "2026-06-03T21:00:00+00:00", None, None, side="no"),
    }

    # All-time, side-aware: wins = a,b (NO->NO), e (YES->YES) = 3; losses =
    # c (NO->YES), d (YES->NO) = 2. (Outcome-based would wrongly give 2W/3L.)
    total, w, lo, v, n = mgr.realized_summary_since(None)
    assert (w, lo, v, n) == (3, 2, 0, 5)
    assert abs(total - (0.20 + 0.18 - 0.85 - 0.80 + 0.25)) < 1e-9

    # Since the cutoff: only a,b,c (placed today). Side-aware: a,b win, c loses.
    # (Outcome-based would wrongly give 1W/2L.)
    total2, w2, lo2, v2, n2 = mgr.realized_summary_since("2026-06-03T17:00:00+00:00")
    assert (w2, lo2, v2, n2) == (2, 1, 0, 3)
    assert abs(total2 - (0.20 + 0.18 - 0.85)) < 1e-9

    # 'Z' suffix parses identically to '+00:00'.
    total3, *_rest = mgr.realized_summary_since("2026-06-03T17:00:00Z")
    assert abs(total3 - total2) < 1e-9


def test_format_settlement_alert_side_aware_labels() -> None:
    """A NO bet resolving NO is a WIN; a NO bet resolving YES is a LOSS. YES-side
    (default) behavior is unchanged."""
    from kalshi_bot.alerts.discord import format_settlement_alert
    common = dict(
        bot_name="v1", ticker="KXX-1", realized_pnl_usd=0.10, filled_count=1,
        entry_price=0.88, cumulative_pnl_usd=0.0, settled_count=1, winners=1, losers=0,
    )
    # NO bet, market resolved NO -> our side won.
    no_win = format_settlement_alert(outcome=0, side="no", **common)
    assert "NO (win)" in no_win and "WIN" in no_win
    # NO bet, market resolved YES -> our side lost.
    no_loss = format_settlement_alert(outcome=1, side="no", **{**common, "realized_pnl_usd": -0.85})
    assert "YES (loss)" in no_loss and "LOSS" in no_loss
    # YES bet (default side) is unchanged: resolved YES -> win, NO -> loss.
    assert "YES (win)" in format_settlement_alert(outcome=1, **common)
    assert "NO (loss)" in format_settlement_alert(outcome=0, **common)


def test_place_records_intent_before_post(tmp_state_path: Path) -> None:
    """Even before the POST is made, the intent must hit disk so a
    crash mid-POST doesn't lose the client_order_id."""
    client = MockKalshiClient()
    client.post_responses.append({
        "order_id": "kalshi-abc-1", "fill_count": "0", "remaining_count": "1",
    })
    mgr = LiveOrderManager(client=client, state_path=tmp_state_path)
    order = _place(mgr, target_price=0.75)
    # After success, intent moved from intents -> resting.
    assert order.status == LiveOrderStatus.LIVE_RESTING
    assert order.order_id == "kalshi-abc-1"
    assert order.intent_id in mgr.state.resting
    assert order.intent_id not in mgr.state.intents
    # The intent IS the client_order_id. V2 single-book body: a YES favorite
    # is a "bid" priced from the YES side, count/price as fixed-point strings,
    # posted to /portfolio/events/orders.
    method, endpoint, body = client.calls[0]
    assert method == "POST"
    assert endpoint == "/portfolio/events/orders"
    assert body["client_order_id"] == order.intent_id
    assert body["side"] == "bid"
    assert body["price"] == "0.75"
    assert body["count"] == "1"
    assert body["time_in_force"] == "good_till_canceled"
    assert body["self_trade_prevention_type"] == "taker_at_cross"
    assert "yes_price" not in body and "action" not in body


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
    client.post_responses.append({})  # no order_id
    mgr = LiveOrderManager(client=client, state_path=tmp_state_path)
    order = _place(mgr)
    assert order.status == LiveOrderStatus.INTENT_RECORDED
    assert order.intent_id in mgr.state.intents


def test_ack_with_filled_status_jumps_to_filled(tmp_state_path: Path) -> None:
    """Immediate-fill path: Kalshi can fill on the POST. V2 reports it via the
    counts (fill_count > 0, remaining_count 0), not a status string."""
    client = MockKalshiClient()
    client.post_responses.append({
        "order_id": "kalshi-fok-1", "fill_count": "2", "remaining_count": "0",
    })
    mgr = LiveOrderManager(client=client, state_path=tmp_state_path)
    order = _place(mgr, target_price=0.80, contracts=2)
    assert order.status == LiveOrderStatus.LIVE_FILLED
    assert order.filled_count == 2
    assert order.filled_price_cents == 80
    assert order.intent_id in mgr.state.filled


def test_place_no_arm_maps_to_ask_at_yes_equivalent_price(tmp_state_path: Path) -> None:
    """The NO-underdog arm buys NO at its own-side price; on the V2 single book
    that is an ASK at the YES-equivalent price (100 - no_price cents). Getting
    this inverted would place the OPPOSITE real-money bet, so guard it."""
    client = MockKalshiClient()
    client.post_responses.append({
        "order_id": "kalshi-no-1", "fill_count": "0", "remaining_count": "2",
    })
    mgr = LiveOrderManager(client=client, state_path=tmp_state_path)
    order = mgr.place_live_order(
        ticker="KXNBA-26-LAL", series_ticker="KXNBA", event_ticker="KXNBA-26",
        target_price=0.30, contracts=2, side="no",
        expected_net_edge=0.05, market_mid_at_placement=0.30,
    )
    assert order.status == LiveOrderStatus.LIVE_RESTING
    method, endpoint, body = client.calls[0]
    assert endpoint == "/portfolio/events/orders"
    assert body["side"] == "ask"      # selling YES == buying NO
    assert body["price"] == "0.70"    # YES-equivalent of buying NO at 0.30
    assert body["count"] == "2"
    # The order keeps its own-side identity (side="no", no_price 30c) for P&L.
    assert order.side == "no"
    assert order.target_price_cents == 30


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
        "ticker": order.ticker,
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
        "order_id": "k-1", "fill_count": "0", "remaining_count": "1",
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


def test_reconcile_fills_captures_actual_fee_cost(tmp_state_path: Path) -> None:
    """reconcile_fills records Kalshi's real per-fill fee_cost (dollar string)
    onto the order, summed across partial fills, so realized P&L uses the
    actual fee rather than a model. Guards the 2026-06-13 over-fee fix."""
    client = MockKalshiClient()
    client.post_responses.append({
        "order_id": "k-1", "fill_count": "0", "remaining_count": "1",
    })
    mgr = LiveOrderManager(client=client, state_path=tmp_state_path)
    order = _place(mgr, target_price=0.75, contracts=2)
    # First partial fill carries a $0.0030 fee.
    client.paginate_responses.append([{
        "trade_id": "fill-1", "order_id": "k-1", "count_fp": "1.00",
        "yes_price_dollars": "0.7500", "fee_cost": "0.003000",
    }])
    mgr.reconcile_fills()
    assert mgr.state.resting[order.intent_id].fee_cost_usd == pytest.approx(0.003, abs=1e-9)
    # Second partial fill carries a $0.0040 fee; total accumulates to $0.0070.
    client.paginate_responses.append([{
        "trade_id": "fill-2", "order_id": "k-1", "count_fp": "1.00",
        "yes_price_dollars": "0.7500", "fee_cost": "0.004000",
    }])
    mgr.reconcile_fills()
    filled = mgr.state.filled[order.intent_id]
    assert filled.status == LiveOrderStatus.LIVE_FILLED
    assert filled.fee_cost_usd == pytest.approx(0.007, abs=1e-9)


def test_reconcile_fills_idempotent_on_same_fill_id(tmp_state_path: Path) -> None:
    client = MockKalshiClient()
    client.post_responses.append({
        "order_id": "k-1", "fill_count": "0", "remaining_count": "1",
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
        "order_id": "k-1", "fill_count": "0", "remaining_count": "1",
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
        "order_id": "k-1", "fill_count": "1", "remaining_count": "0",
    })
    mgr = LiveOrderManager(client=client, state_path=tmp_state_path)
    order = _place(mgr, target_price=0.75, contracts=2)
    # Realized P&L uses Kalshi's ACTUAL captured fee (order.fee_cost_usd), as
    # if reconcile_fills had recorded a $0.02 total fee on the fill.
    order.fee_cost_usd = 0.02
    # Filled inline above. Now market settles YES. Live Kalshi reports the
    # terminal state as status "finalized" with a "settlement_ts" field.
    client.get_responses.append({
        "market": {"status": "finalized", "result": "yes",
                   "settlement_ts": "2026-05-24T01:00:00Z"},
    })
    settled = mgr.reconcile_settlements()
    assert len(settled) == 1
    assert settled[0].resolution_ts == "2026-05-24T01:00:00Z"
    # 2 contracts * (1.0 - 0.75) = 0.50 gross, minus the actual fee 0.02 = 0.48.
    assert settled[0].realized_pnl_usd == pytest.approx(0.48, abs=1e-6)
    assert order.intent_id in mgr.state.closed
    assert order.intent_id not in mgr.state.filled


def test_reconcile_settlements_no_loser(tmp_state_path: Path) -> None:
    client = MockKalshiClient()
    client.post_responses.append({
        "order_id": "k-1", "fill_count": "1", "remaining_count": "0",
    })
    mgr = LiveOrderManager(client=client, state_path=tmp_state_path)
    order = _place(mgr, target_price=0.80, contracts=1)
    order.fee_cost_usd = 0.01  # actual captured fee
    # "settled" kept here to cover the defensively-accepted status value.
    client.get_responses.append({
        "market": {"status": "settled", "result": "no"},
    })
    settled = mgr.reconcile_settlements()
    # YES order, market resolved NO -> loses the entry price, minus actual fee:
    # -0.80 - 0.01 = -0.81.
    assert settled[0].realized_pnl_usd == pytest.approx(-0.81, abs=1e-6)


def test_reconcile_settlements_void(tmp_state_path: Path) -> None:
    client = MockKalshiClient()
    client.post_responses.append({
        "order_id": "k-1", "fill_count": "1", "remaining_count": "0",
    })
    mgr = LiveOrderManager(client=client, state_path=tmp_state_path)
    order = _place(mgr, target_price=0.75, contracts=1)
    order.fee_cost_usd = 0.005  # actual captured entry fee
    client.get_responses.append({
        "market": {"status": "finalized", "result": "void"},
    })
    settled = mgr.reconcile_settlements()
    # Outcome -1 (void): payoff 0, but the entry fee Kalshi charged still nets.
    assert settled[0].resolution_outcome == -1
    assert settled[0].realized_pnl_usd == pytest.approx(-0.005, abs=1e-6)


def test_reconcile_settlements_unsettled_market_no_change(tmp_state_path: Path) -> None:
    client = MockKalshiClient()
    client.post_responses.append({
        "order_id": "k-1", "fill_count": "1", "remaining_count": "0",
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


def test_reconcile_settlements_determined_not_yet_settled(tmp_state_path: Path) -> None:
    # "determined" is the result-known-but-pre-payout intermediate state.
    # We deliberately wait for "finalized" rather than settle early.
    client = MockKalshiClient()
    client.post_responses.append({
        "order_id": "k-1", "fill_count": "1", "remaining_count": "0",
    })
    mgr = LiveOrderManager(client=client, state_path=tmp_state_path)
    _place(mgr, target_price=0.75, contracts=1)
    client.get_responses.append({
        "market": {"status": "determined", "result": "yes"},
    })
    settled = mgr.reconcile_settlements()
    assert len(settled) == 0
    assert len(mgr.state.filled) == 1


def test_reconcile_settlements_finalized_unrecognized_result_voids(tmp_state_path: Path) -> None:
    # A market in a TERMINAL status (finalized) with a non-yes/no result
    # must settle as void and release its capital, never strand in filled.
    # Covers empty, scalar, and any other unexpected token.
    for bad_result in ("", "scalar", "all_no"):
        client = MockKalshiClient()
        client.post_responses.append({
            "order_id": "k-1", "fill_count": "1", "remaining_count": "0",
        })
        mgr = LiveOrderManager(client=client, state_path=tmp_state_path)
        _place(mgr, target_price=0.75, contracts=1)
        client.get_responses.append({
            "market": {"status": "finalized", "result": bad_result},
        })
        settled = mgr.reconcile_settlements()
        assert len(settled) == 1, f"result={bad_result!r} should settle"
        assert settled[0].resolution_outcome == -1
        assert len(mgr.state.filled) == 0  # capital released
        assert mgr.state.closed[settled[0].intent_id].realized_pnl_usd is not None


def _fill_and_age(mgr: LiveOrderManager, *, ticker: str = "KXMLBGAME-26X-T",
                  price: float = 0.50, contracts: int = 2,
                  age_hours: float = 48.0):
    """Place an order, force it into `filled`, and backdate filled_ts so the
    stuck-position reconcile treats it as old."""
    from datetime import UTC, datetime, timedelta
    o = mgr.place_live_order(
        ticker=ticker, series_ticker="KXMLBGAME", event_ticker="KXMLBGAME-26X",
        target_price=price, contracts=contracts,
        expected_net_edge=0.05, market_mid_at_placement=price,
    )
    iid = o.intent_id
    mgr.state.intents.pop(iid, None)
    mgr.state.resting.pop(iid, None)
    o.status = LiveOrderStatus.LIVE_FILLED
    o.filled_count = contracts
    o.filled_price_cents = int(round(price * 100))
    o.filled_ts = (datetime.now(UTC) - timedelta(hours=age_hours)).isoformat()
    mgr.state.filled[iid] = o
    return o


def test_stuck_position_flat_voids(tmp_state_path: Path) -> None:
    # Stuck filled order; Kalshi shows position flat -> void-settle, release.
    client = MockKalshiClient()
    client.post_responses.append({"order_id": "k-1", "fill_count": "0", "remaining_count": "1"})
    mgr = LiveOrderManager(client=client, state_path=tmp_state_path)
    o = _fill_and_age(mgr, age_hours=48.0)
    client.get_responses.append({
        "market_positions": [{"ticker": o.ticker, "position_fp": "0.00"}],
    })
    void_settled, flagged = mgr.reconcile_stuck_positions(stuck_age_hours=24.0)
    assert len(void_settled) == 1
    assert len(flagged) == 0
    assert o.intent_id in mgr.state.closed
    assert o.intent_id not in mgr.state.filled
    assert mgr.state.closed[o.intent_id].resolution_outcome == -1


def test_stuck_position_held_flags_once(tmp_state_path: Path) -> None:
    # Position still held -> flag once, never void, never re-flag.
    client = MockKalshiClient()
    client.post_responses.append({"order_id": "k-1", "fill_count": "0", "remaining_count": "1"})
    mgr = LiveOrderManager(client=client, state_path=tmp_state_path)
    o = _fill_and_age(mgr, age_hours=48.0)
    client.get_responses.append({
        "market_positions": [{"ticker": o.ticker, "position_fp": "2.00"}],
    })
    void_settled, flagged = mgr.reconcile_stuck_positions(stuck_age_hours=24.0)
    assert void_settled == []
    assert len(flagged) == 1
    assert o.intent_id in mgr.state.filled
    assert mgr.state.filled[o.intent_id].stuck_alert_ts is not None
    # Second pass must NOT re-flag.
    client.get_responses.append({
        "market_positions": [{"ticker": o.ticker, "position_fp": "2.00"}],
    })
    _v2, f2 = mgr.reconcile_stuck_positions(stuck_age_hours=24.0)
    assert f2 == []


def test_stuck_position_missing_key_is_not_flat(tmp_state_path: Path) -> None:
    # CRITICAL: a ticker ABSENT from positions is UNKNOWN, never flat.
    # Must flag, never void (else we recreate the phantom-exit foot-gun).
    client = MockKalshiClient()
    client.post_responses.append({"order_id": "k-1", "fill_count": "0", "remaining_count": "1"})
    mgr = LiveOrderManager(client=client, state_path=tmp_state_path)
    o = _fill_and_age(mgr, age_hours=48.0)
    client.get_responses.append({"market_positions": []})
    void_settled, flagged = mgr.reconcile_stuck_positions(stuck_age_hours=24.0)
    assert void_settled == []
    assert len(flagged) == 1
    assert o.intent_id in mgr.state.filled


def test_stuck_position_young_order_no_api_call(tmp_state_path: Path) -> None:
    # A recently-filled order is not stuck; positions must not even be polled.
    client = MockKalshiClient()
    client.post_responses.append({"order_id": "k-1", "fill_count": "0", "remaining_count": "1"})
    mgr = LiveOrderManager(client=client, state_path=tmp_state_path)
    _fill_and_age(mgr, age_hours=1.0)
    void_settled, flagged = mgr.reconcile_stuck_positions(stuck_age_hours=24.0)
    assert void_settled == []
    assert flagged == []
    assert not any(c[1] == "/portfolio/positions" for c in client.calls)


def test_stuck_position_fetch_error_is_safe(tmp_state_path: Path) -> None:
    # Positions fetch failure must leave state untouched (no guesswork).
    client = MockKalshiClient()
    client.post_responses.append({"order_id": "k-1", "fill_count": "0", "remaining_count": "1"})
    mgr = LiveOrderManager(client=client, state_path=tmp_state_path)
    o = _fill_and_age(mgr, age_hours=48.0)
    client.get_raises.append(RuntimeError("rate limit"))
    void_settled, flagged = mgr.reconcile_stuck_positions(stuck_age_hours=24.0)
    assert void_settled == []
    assert flagged == []
    assert o.intent_id in mgr.state.filled


def _iso(hours_from_now: float) -> str:
    from datetime import UTC, datetime, timedelta
    return (datetime.now(UTC) + timedelta(hours=hours_from_now)).isoformat()


def test_flag_stuck_past_close_flags_once_no_void(tmp_state_path: Path) -> None:
    # Past its close_time + buffer, not terminal -> flag once. v1 NEVER voids:
    # the order stays in filled and realized P&L is not mutated.
    client = MockKalshiClient()
    client.post_responses.append({"order_id": "k-1", "fill_count": "0", "remaining_count": "1"})
    mgr = LiveOrderManager(client=client, state_path=tmp_state_path)
    o = _fill_and_age(mgr, ticker="KXNFLGAME-26X-T", age_hours=1.0)
    client.get_responses.append(
        {"market": {"status": "active", "close_time": _iso(-72)}},
    )
    flagged = mgr.flag_stuck_past_close(min_hours_past_close=48.0)
    assert len(flagged) == 1
    assert o.intent_id in mgr.state.filled  # NOT voided
    assert mgr.state.filled[o.intent_id].stuck_alert_ts is not None
    assert mgr.state.realized_pnl_total_usd == 0.0
    # Already flagged -> no re-flag and no fetch (no staged response needed).
    assert mgr.flag_stuck_past_close(min_hours_past_close=48.0) == []


def test_flag_stuck_past_close_future_close_not_flagged(tmp_state_path: Path) -> None:
    # A normal long-horizon OPEN position (close_time in the future) is never
    # flagged. This is the guard against false-flagging v1's 24 season-long bets.
    client = MockKalshiClient()
    client.post_responses.append({"order_id": "k-1", "fill_count": "0", "remaining_count": "1"})
    mgr = LiveOrderManager(client=client, state_path=tmp_state_path)
    o = _fill_and_age(mgr, age_hours=1.0)
    client.get_responses.append(
        {"market": {"status": "active", "close_time": _iso(24 * 60)}},
    )
    flagged = mgr.flag_stuck_past_close(min_hours_past_close=48.0)
    assert flagged == []
    assert o.intent_id in mgr.state.filled


def test_flag_stuck_past_close_terminal_left_for_settlement(tmp_state_path: Path) -> None:
    client = MockKalshiClient()
    client.post_responses.append({"order_id": "k-1", "fill_count": "0", "remaining_count": "1"})
    mgr = LiveOrderManager(client=client, state_path=tmp_state_path)
    _fill_and_age(mgr, age_hours=1.0)
    client.get_responses.append(
        {"market": {"status": "finalized", "result": "yes", "close_time": _iso(-72)}},
    )
    assert mgr.flag_stuck_past_close(min_hours_past_close=48.0) == []


def test_flag_stuck_past_close_missing_close_time(tmp_state_path: Path) -> None:
    client = MockKalshiClient()
    client.post_responses.append({"order_id": "k-1", "fill_count": "0", "remaining_count": "1"})
    mgr = LiveOrderManager(client=client, state_path=tmp_state_path)
    o = _fill_and_age(mgr, age_hours=1.0)
    client.get_responses.append({"market": {"status": "active"}})
    assert mgr.flag_stuck_past_close(min_hours_past_close=48.0) == []
    assert o.intent_id in mgr.state.filled


def test_flag_stuck_past_close_fetch_error_safe(tmp_state_path: Path) -> None:
    client = MockKalshiClient()
    client.post_responses.append({"order_id": "k-1", "fill_count": "0", "remaining_count": "1"})
    mgr = LiveOrderManager(client=client, state_path=tmp_state_path)
    o = _fill_and_age(mgr, age_hours=1.0)
    client.get_raises.append(RuntimeError("rate limit"))
    assert mgr.flag_stuck_past_close(min_hours_past_close=48.0) == []
    assert o.intent_id in mgr.state.filled


def test_flag_stuck_past_close_garbage_close_time(tmp_state_path: Path) -> None:
    # An unparseable close_time must not flag (never act on garbage data).
    client = MockKalshiClient()
    client.post_responses.append({"order_id": "k-1", "fill_count": "0", "remaining_count": "1"})
    mgr = LiveOrderManager(client=client, state_path=tmp_state_path)
    o = _fill_and_age(mgr, age_hours=1.0)
    client.get_responses.append(
        {"market": {"status": "active", "close_time": "soon-ish"}},
    )
    assert mgr.flag_stuck_past_close(min_hours_past_close=48.0) == []
    assert o.intent_id in mgr.state.filled


def test_cancel_all_resting_calls_delete(tmp_state_path: Path) -> None:
    client = MockKalshiClient()
    client.post_responses.append({
        "order_id": "k-1", "fill_count": "0", "remaining_count": "1",
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
        "order_id": "k-1", "fill_count": "0", "remaining_count": "1",
    })
    client.post_responses.append({
        "order_id": "k-2", "fill_count": "0", "remaining_count": "1",
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
        "order_id": "k-1", "fill_count": "0", "remaining_count": "1",
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


def _rest_order(mgr: LiveOrderManager, *, ticker: str, series: str, oid: str):
    """Put a synthetic LIVE_RESTING order directly into state."""
    from datetime import UTC, datetime

    from kalshi_bot.strategy.live_order_manager import LiveOrder
    o = LiveOrder(
        intent_id=oid, ticker=ticker, series_ticker=series,
        event_ticker=ticker.rsplit("-", 1)[0], side="yes",
        target_price_cents=72, contracts=1, expected_net_edge=0.05,
        market_mid_at_placement=0.72, placed_ts=datetime.now(UTC).isoformat(),
        status=LiveOrderStatus.LIVE_RESTING, order_id=oid,
    )
    mgr.state.resting[oid] = o
    return o


def test_cancel_resting_by_series_cancels_only_denylisted(tmp_state_path: Path) -> None:
    client = MockKalshiClient()
    mgr = LiveOrderManager(client=client, state_path=tmp_state_path)
    _rest_order(mgr, ticker="KXWCGAME-26-ARG", series="KXWCGAME", oid="r1")
    _rest_order(mgr, ticker="KXPGATOP20-26-X", series="KXPGATOP20", oid="r2")
    client.delete_responses.append({})  # one cancel succeeds
    cancelled = mgr.cancel_resting_by_series(frozenset({"KXWCGAME"}))
    assert cancelled == ["r1"]
    assert "r1" not in mgr.state.resting and "r1" in mgr.state.closed
    assert "r2" in mgr.state.resting  # not denylisted: kept
    assert mgr.state.closed["r1"].status == LiveOrderStatus.LIVE_CANCELLED


def test_cancel_resting_by_series_empty_denylist_noops(tmp_state_path: Path) -> None:
    client = MockKalshiClient()
    mgr = LiveOrderManager(client=client, state_path=tmp_state_path)
    _rest_order(mgr, ticker="KXWCGAME-26-ARG", series="KXWCGAME", oid="r1")
    assert mgr.cancel_resting_by_series(frozenset()) == []
    assert not any(c[0] == "DELETE" for c in client.calls)
    assert "r1" in mgr.state.resting


def test_cancel_resting_by_series_delete_failure_is_safe(tmp_state_path: Path) -> None:
    client = MockKalshiClient()
    mgr = LiveOrderManager(client=client, state_path=tmp_state_path)
    _rest_order(mgr, ticker="KXWCGAME-26-ARG", series="KXWCGAME", oid="r1")
    client.delete_raises.append(RuntimeError("net down"))
    assert mgr.cancel_resting_by_series(frozenset({"KXWCGAME"})) == []
    assert "r1" in mgr.state.resting  # stays on cancel failure


def test_bankroll_accounts_for_realized_pnl(tmp_state_path: Path) -> None:
    client = MockKalshiClient()
    client.post_responses.append({
        "order_id": "k-1", "fill_count": "1", "remaining_count": "0",
    })
    mgr = LiveOrderManager(client=client, state_path=tmp_state_path)
    order = _place(mgr, target_price=0.75, contracts=2)
    order.fee_cost_usd = 0.02  # actual captured fee
    client.get_responses.append({
        "market": {"status": "settled", "result": "yes"},
    })
    mgr.reconcile_settlements()
    # 2 * (1.0 - 0.75) = 0.50 gross, minus actual fee 0.02 = +0.48.
    assert mgr.current_live_bankroll() == pytest.approx(25.0 + 0.48, abs=1e-6)


def test_open_order_count_includes_intents_and_resting(tmp_state_path: Path) -> None:
    client = MockKalshiClient()
    client.post_raises.append(RuntimeError("net down"))
    client.post_responses.append({
        "order_id": "k-2", "fill_count": "0", "remaining_count": "1",
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
        "order_id": "k-1", "fill_count": "0", "remaining_count": "1",
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
        "order_id": "k-1", "fill_count": "0", "remaining_count": "1",
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
        "order_id": "k-1", "fill_count": "0", "remaining_count": "1",
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
        "order_id": "k-1", "fill_count": "0", "remaining_count": "1",
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
        "order_id": "k-1", "fill_count": "0", "remaining_count": "1",
    })
    mgr = LiveOrderManager(client=client, state_path=tmp_state_path)
    o = _place(mgr, target_price=0.70)
    client.paginate_responses.append([{
        "client_order_id": o.intent_id,
        "order_id": "k-1",
        "status": "filled",
        "ticker": o.ticker,
    }])
    changed = mgr.reconcile_resting()
    assert len(changed) == 1
    assert o.intent_id in mgr.state.filled
    assert o.intent_id not in mgr.state.resting


def test_reconcile_resting_noop_when_still_resting(tmp_state_path: Path) -> None:
    """No state change when Kalshi confirms the order is still resting."""
    client = MockKalshiClient()
    client.post_responses.append({
        "order_id": "k-1", "fill_count": "0", "remaining_count": "1",
    })
    mgr = LiveOrderManager(client=client, state_path=tmp_state_path)
    o = _place(mgr, target_price=0.70)
    client.paginate_responses.append([{
        "client_order_id": o.intent_id,
        "order_id": "k-1",
        "status": "resting",
        "ticker": o.ticker,
    }])
    changed = mgr.reconcile_resting()
    assert len(changed) == 0
    assert o.intent_id in mgr.state.resting


def test_reconcile_intents_scopes_lookup_by_ticker(tmp_state_path: Path) -> None:
    """The lookup must scope GET /portfolio/orders by ticker (a server-honored
    filter) and must NOT depend on client_order_id, which Kalshi ignores as a
    query parameter. Guards the latent false-cancel bug where an order outside
    the unscoped first-page window was wrongly marked cancelled."""
    client = MockKalshiClient()
    client.post_raises.append(RuntimeError("connection reset"))
    mgr = LiveOrderManager(client=client, state_path=tmp_state_path)
    order = _place(mgr)
    assert order.status == LiveOrderStatus.INTENT_RECORDED
    client.paginate_responses.append([{
        "client_order_id": order.intent_id, "order_id": "kalshi-lost-1",
        "status": "resting", "ticker": order.ticker,
    }])
    mgr.reconcile_intents()
    paginate_calls = [c for c in client.calls if c[0] == "PAGINATE"]
    assert paginate_calls, "expected a paginate lookup"
    _method, endpoint, params = paginate_calls[-1]
    assert endpoint == "/portfolio/orders"
    assert params.get("ticker") == order.ticker
    assert "client_order_id" not in params
    assert order.intent_id in mgr.state.resting


def test_reconcile_resting_finds_order_beyond_unscoped_window(tmp_state_path: Path) -> None:
    """With ticker scoping the order is found even when the account has more
    orders than an unscoped pagination window (max_pages * limit). Before the
    fix, an order past that window was missed and falsely cancelled."""
    client = MockKalshiClient()
    client.post_responses.append({
        "order_id": "k-1", "fill_count": "0", "remaining_count": "1",
    })
    mgr = LiveOrderManager(client=client, state_path=tmp_state_path)
    o = _place(mgr, target_price=0.70)
    # 300 unrelated orders on OTHER tickers (which would crowd ours out of an
    # unscoped 2-page / 200-row window), plus ours on its own ticker last.
    decoys = [
        {"client_order_id": f"other-{i}", "order_id": f"o-{i}",
         "status": "resting", "ticker": f"KXOTHER-{i}"}
        for i in range(300)
    ]
    ours = {"client_order_id": o.intent_id, "order_id": "k-1",
            "status": "resting", "ticker": o.ticker}
    client.paginate_responses.append([*decoys, ours])
    changed = mgr.reconcile_resting()
    # Found and confirmed still resting, NOT falsely cancelled.
    assert changed == []
    assert o.intent_id in mgr.state.resting
    assert o.intent_id not in mgr.state.closed


def test_reconcile_resting_matches_only_our_coid_on_same_ticker(tmp_state_path: Path) -> None:
    """Sibling orders on the SAME ticker (different client_order_ids) must not
    be mistaken for ours; only the exact client_order_id match drives the
    transition. The decoy is listed first to prove we do not blindly take
    results[0]."""
    client = MockKalshiClient()
    client.post_responses.append({
        "order_id": "k-1", "fill_count": "0", "remaining_count": "1",
    })
    mgr = LiveOrderManager(client=client, state_path=tmp_state_path)
    o = _place(mgr, target_price=0.70)
    client.paginate_responses.append([
        {"client_order_id": "someone-else", "order_id": "x-9",
         "status": "canceled", "ticker": o.ticker},
        {"client_order_id": o.intent_id, "order_id": "k-1",
         "status": "filled", "ticker": o.ticker},
    ])
    changed = mgr.reconcile_resting()
    assert len(changed) == 1
    assert o.intent_id in mgr.state.filled
    assert o.intent_id not in mgr.state.resting


def test_open_order_count_includes_filled(tmp_state_path: Path) -> None:
    """Bug regression: filled orders MUST count toward the cap so
    capital doesn't escape max_concurrent as positions fill."""
    client = MockKalshiClient()
    client.post_responses.append({
        "order_id": "k-1", "fill_count": "1", "remaining_count": "0",
    })
    client.post_responses.append({
        "order_id": "k-2", "fill_count": "0", "remaining_count": "1",
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
        "order_id": "k-1", "fill_count": "0", "remaining_count": "1",
    })
    mgr = LiveOrderManager(client=client, state_path=tmp_state_path)
    _place(mgr)
    client.paginate_raises.append(RuntimeError("rate limit"))
    changed = mgr.reconcile_fills()
    assert changed == []  # graceful no-op


def test_settle_fetch_failure_continues(tmp_state_path: Path) -> None:
    client = MockKalshiClient()
    client.post_responses.append({
        "order_id": "k-1", "fill_count": "1", "remaining_count": "0",
    })
    mgr = LiveOrderManager(client=client, state_path=tmp_state_path)
    _place(mgr)
    client.get_raises.append(RuntimeError("rate limit"))
    settled = mgr.reconcile_settlements()
    assert settled == []
