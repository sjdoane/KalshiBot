"""Unit tests for v11 Track 2 join script (scripts/v11/join_filter_vs_v1.py).

Per v11 Phase 1.5 methodology lock v2 Section 9.6 minimum 7 cases:
- empty inputs
- no v1 orders
- all v1 orders match filter
- mismatched ticker
- mismatched timestamp window
- v1 order placed then cancelled
- v1 order placed then never filled

Plus extra cases for v1_decision enum derivation and arm-decision
reconstruction.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from kalshi_bot_v11.filter_v1_join import (
    build_cross_row,
    collect_intents,
    derive_arm_decisions,
    derive_v1_decision,
    join_logs,
    match_intent,
    run_join,
)


# Reusable helpers


def _shadow_row(
    timestamp: str,
    ticker: str,
    should_trade: bool = True,
    fired_rules: list[str] | None = None,
    sportsbook_implied: float | None = None,
    poly_mid: float | None = None,
) -> dict:
    return {
        "timestamp": timestamp,
        "ticker": ticker,
        "series_ticker": "",
        "kalshi_price": 0.75,
        "poly_mid": poly_mid,
        "sportsbook_implied": sportsbook_implied,
        "cross_market_implied": None,
        "should_trade": should_trade,
        "fired_rules": fired_rules or [],
        "reason": "test",
        "confidence": 0.0,
        "fetch_status": {"poly": "ok", "book": "ok"},
        "fetch_latency_ms": 100,
    }


def _intent(
    ticker: str,
    placed_ts: str,
    *,
    acked_ts: str | None = None,
    filled_ts: str | None = None,
    filled_count: int = 0,
    cancelled_ts: str | None = None,
    resolution_ts: str | None = None,
    status: str = "live_resting",
) -> dict:
    return {
        "intent_id": "test_intent",
        "ticker": ticker,
        "series_ticker": "",
        "event_ticker": "",
        "side": "yes",
        "target_price_cents": 75,
        "contracts": 1,
        "expected_net_edge": 0.1,
        "market_mid_at_placement": 0.75,
        "placed_ts": placed_ts,
        "status": status,
        "order_id": "test_order" if acked_ts else None,
        "acked_ts": acked_ts,
        "filled_ts": filled_ts,
        "filled_price_cents": 75 if filled_count else None,
        "filled_count": filled_count,
        "cancelled_ts": cancelled_ts,
        "resolution_ts": resolution_ts,
        "resolution_outcome": None,
        "realized_pnl_usd": None,
    }


# Required test cases (1 to 7)


def test_empty_inputs():
    rows = join_logs([], {})
    assert rows == []


def test_no_v1_orders():
    shadow = _shadow_row("2026-05-25T01:05:48.760697+00:00", "KXMLBGAME-A")
    rows = join_logs([json.dumps(shadow)], {"resting": {}, "filled": {}, "closed": {}})
    assert len(rows) == 1
    assert rows[0]["v1_decision"] == "not_placed"


def test_all_v1_orders_match_filter():
    shadow1 = _shadow_row("2026-05-25T01:05:00+00:00", "KXMLBGAME-A")
    shadow2 = _shadow_row("2026-05-25T02:10:00+00:00", "KXMLBGAME-B")
    state = {
        "filled": {
            "i1": _intent(
                "KXMLBGAME-A",
                "2026-05-25T01:05:30+00:00",
                acked_ts="2026-05-25T01:05:31+00:00",
                filled_ts="2026-05-25T01:30:00+00:00",
                filled_count=1,
                status="live_filled",
            ),
            "i2": _intent(
                "KXMLBGAME-B",
                "2026-05-25T02:10:10+00:00",
                acked_ts="2026-05-25T02:10:11+00:00",
                filled_ts="2026-05-25T02:30:00+00:00",
                filled_count=1,
                status="live_filled",
            ),
        }
    }
    rows = join_logs([json.dumps(shadow1), json.dumps(shadow2)], state)
    assert len(rows) == 2
    assert all(r["v1_decision"] == "placed_and_filled" for r in rows)


def test_mismatched_ticker():
    shadow = _shadow_row("2026-05-25T01:05:00+00:00", "KXMLBGAME-A")
    state = {
        "resting": {
            "i1": _intent(
                "KXNBAGAME-OTHER",
                "2026-05-25T01:05:30+00:00",
                acked_ts="2026-05-25T01:05:31+00:00",
            )
        }
    }
    rows = join_logs([json.dumps(shadow)], state)
    assert rows[0]["v1_decision"] == "not_placed"


def test_mismatched_timestamp_window():
    # v1 order placed 10 minutes after shadow log, outside +/- 5 min window
    shadow = _shadow_row("2026-05-25T01:05:00+00:00", "KXMLBGAME-A")
    state = {
        "resting": {
            "i1": _intent(
                "KXMLBGAME-A",
                "2026-05-25T01:15:00+00:00",
                acked_ts="2026-05-25T01:15:01+00:00",
            )
        }
    }
    rows = join_logs([json.dumps(shadow)], state)
    assert rows[0]["v1_decision"] == "not_placed"


def test_v1_order_placed_then_cancelled():
    shadow = _shadow_row("2026-05-25T01:05:00+00:00", "KXMLBGAME-A")
    state = {
        "closed": {
            "i1": _intent(
                "KXMLBGAME-A",
                "2026-05-25T01:05:30+00:00",
                acked_ts="2026-05-25T01:05:31+00:00",
                cancelled_ts="2026-05-25T01:06:00+00:00",
                status="live_cancelled",
            )
        }
    }
    rows = join_logs([json.dumps(shadow)], state)
    assert rows[0]["v1_decision"] == "placed_and_cancelled"


def test_v1_order_placed_then_never_filled():
    # Acked but not filled and not cancelled and past resolution_ts =
    # placed_and_expired
    shadow = _shadow_row("2026-05-25T01:05:00+00:00", "KXMLBGAME-A")
    state = {
        "closed": {
            "i1": _intent(
                "KXMLBGAME-A",
                "2026-05-25T01:05:30+00:00",
                acked_ts="2026-05-25T01:05:31+00:00",
                resolution_ts="2026-05-26T03:00:00+00:00",
                status="live_expired",
            )
        }
    }
    rows = join_logs([json.dumps(shadow)], state)
    assert rows[0]["v1_decision"] == "placed_and_expired"


# Extra coverage: v1_decision derivation


def test_derive_filled():
    intent = _intent(
        "X",
        "2026-05-25T01:05:30+00:00",
        acked_ts="2026-05-25T01:05:31+00:00",
        filled_ts="2026-05-25T01:30:00+00:00",
        filled_count=1,
    )
    assert derive_v1_decision(intent) == "placed_and_filled"


def test_derive_rejected_no_ack():
    intent = _intent(
        "X",
        "2026-05-25T01:05:30+00:00",
        acked_ts=None,
        cancelled_ts="2026-05-25T01:05:35+00:00",
    )
    # cancelled_ts present takes priority over no-ack per ordering in
    # derive_v1_decision; this exercise documents that placed_and_cancelled
    # wins. To get placed_and_rejected we need no ack AND no cancel.
    assert derive_v1_decision(intent) == "placed_and_cancelled"


def test_derive_rejected_no_ack_no_cancel():
    intent = _intent("X", "2026-05-25T01:05:30+00:00", acked_ts=None)
    assert derive_v1_decision(intent) == "placed_and_rejected"


def test_derive_resting():
    intent = _intent(
        "X",
        "2026-05-25T01:05:30+00:00",
        acked_ts="2026-05-25T01:05:31+00:00",
    )
    assert derive_v1_decision(intent) == "placed_and_resting"


def test_arm_decisions_sportsbook_fired():
    row = _shadow_row(
        "2026-05-25T01:05:00+00:00",
        "X",
        fired_rules=["sportsbook_fade"],
        sportsbook_implied=0.65,
        poly_mid=None,
    )
    sb, poly = derive_arm_decisions(row)
    assert sb is True
    assert poly is None


def test_arm_decisions_polymarket_fired():
    row = _shadow_row(
        "2026-05-25T01:05:00+00:00",
        "X",
        fired_rules=["polymarket_fade"],
        sportsbook_implied=None,
        poly_mid=0.65,
    )
    sb, poly = derive_arm_decisions(row)
    assert sb is None
    assert poly is True


def test_arm_decisions_both_arms_no_fire():
    row = _shadow_row(
        "2026-05-25T01:05:00+00:00",
        "X",
        fired_rules=[],
        sportsbook_implied=0.65,
        poly_mid=0.70,
    )
    sb, poly = derive_arm_decisions(row)
    assert sb is False
    assert poly is False


# End-to-end via tmp_path


def test_run_join_writes_file(tmp_path):
    shadow_log = tmp_path / "shadow.jsonl"
    shadow_log.write_text(
        json.dumps(_shadow_row("2026-05-25T01:05:00+00:00", "KXMLBGAME-A")) + "\n"
    )
    state_json = tmp_path / "state.json"
    state_json.write_text(
        json.dumps(
            {
                "resting": {
                    "i1": _intent(
                        "KXMLBGAME-A",
                        "2026-05-25T01:05:30+00:00",
                        acked_ts="2026-05-25T01:05:31+00:00",
                    )
                }
            }
        )
    )
    output = tmp_path / "out" / "shadow_filter_decisions.jsonl"
    n_rows = run_join(shadow_log, state_json, output)
    assert n_rows == 1
    assert output.exists()
    lines = output.read_text().strip().splitlines()
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert row["ticker"] == "KXMLBGAME-A"
    assert row["v1_decision"] == "placed_and_resting"
    assert row["shadow_filter_decision"] is True
