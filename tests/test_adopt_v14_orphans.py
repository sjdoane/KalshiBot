"""Tests for the v14 orphan-adoption helper (pure reconstruction + units).

The script lives at scripts/v14/adopt_v14_orphans.py and is not an importable
package, so it is loaded by file path. Only the pure helper is tested here;
the API-calling main() is exercised by the real-data dry-run smoke.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from kalshi_bot.strategy.live_order_manager import LiveOrderStatus

_SCRIPT = (
    Path("C:/Users/SamJD/OneDrive/Desktop/AI Projects/Project Kalshi")
    / "scripts" / "v14" / "adopt_v14_orphans.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location("adopt_v14_orphans", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_reconstruct_filled_order_units() -> None:
    mod = _load_module()
    rec = {
        "client_order_id": "14abcdef",
        "ticker": "KXMLBGAME-26MAY292005KCTEX-KC",
        "yes_price_dollars": "0.4700",   # dollar string -> 47 cents
        "fill_count_fp": "2.00",         # fixed-point string -> 2 contracts
        "order_id": "oid-1",
        "created_time": "2026-05-29T21:39:36Z",
        "last_update_time": "2026-05-29T21:39:37Z",
    }
    o = mod.reconstruct_filled_order(rec, "2026-05-30T00:00:00Z")
    assert o.filled_price_cents == 47
    assert o.target_price_cents == 47
    assert o.filled_count == 2
    assert o.contracts == 2
    assert o.status == LiveOrderStatus.LIVE_FILLED
    assert o.order_id == "oid-1"
    assert o.intent_id == "14abcdef"
    assert o.event_ticker == "KXMLBGAME-26MAY292005KCTEX"
    assert o.side == "yes"
    # No P&L at adoption: reconcile_settlements is the single writer.
    assert o.realized_pnl_usd is None
    assert o.resolution_outcome is None


def test_reconstruct_price_cents_in_range() -> None:
    mod = _load_module()
    # A dollars-as-cents bug (e.g. reading "47" as 4700c) must be impossible:
    # the field is always a sub-1.0 dollar string for a 1..99c market.
    for px, expect in (("0.0100", 1), ("0.9900", 99), ("0.5000", 50)):
        rec = {
            "client_order_id": "14x", "ticker": "KXMLBGAME-26X-T",
            "yes_price_dollars": px, "fill_count_fp": "1.00", "order_id": "o",
        }
        o = mod.reconstruct_filled_order(rec, "2026-05-30T00:00:00Z")
        assert o.filled_price_cents == expect
        assert 1 <= o.filled_price_cents <= 99


def test_reconstruct_rejects_nonphysical_price() -> None:
    import pytest
    mod = _load_module()
    # Missing / zero / out-of-range price must raise, never adopt (a 0-cent
    # entry would book a phantom +$1/contract win at settlement).
    for bad in (None, "0.0000", "1.0000"):
        rec = {
            "client_order_id": "14x", "ticker": "KXMLBGAME-26X-T",
            "yes_price_dollars": bad, "fill_count_fp": "1.00", "order_id": "o",
        }
        with pytest.raises(ValueError):
            mod.reconstruct_filled_order(rec, "2026-05-30T00:00:00Z")
