"""Tests for the v1 orphan-adoption helper (series derivation + price guard).

Loaded by file path (scripts/ is not a clean import package). Only the pure
helper is unit-tested; the API-calling main() is exercised by the dry-run.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from kalshi_bot.strategy.live_order_manager import LiveOrderStatus

_SCRIPT = (
    Path("C:/Users/SamJD/OneDrive/Desktop/AI Projects/Project Kalshi")
    / "scripts" / "adopt_v1_orphan.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("adopt_v1_orphan", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_reconstruct_v1_derives_series_from_ticker() -> None:
    mod = _load()
    rec = {
        "client_order_id": "342f2cb131214e84a4407513fda976c7",
        "ticker": "KXUFCOCCUR-26CMCGMHOL-26JUL13",
        "yes_price_dollars": "0.7500",
        "fill_count_fp": "1.00",
        "order_id": "bc1c6967-e872-4ddf-aecf-81ab61299186",
        "created_time": "2026-05-25T03:29:04Z",
    }
    o = mod.reconstruct_v1_filled_order(rec, "2026-05-30T00:00:00Z")
    # v1 trades many series, so series must come from the ticker, not a
    # hardcoded KXMLBGAME.
    assert o.series_ticker == "KXUFCOCCUR"
    assert o.event_ticker == "KXUFCOCCUR-26CMCGMHOL"
    assert o.filled_price_cents == 75
    assert o.filled_count == 1
    assert o.status == LiveOrderStatus.LIVE_FILLED
    assert o.realized_pnl_usd is None  # single P&L writer is reconcile_settlements


def test_reconstruct_v1_rejects_nonphysical_price() -> None:
    mod = _load()
    for bad in (None, "0.0000", "1.0000"):
        rec = {
            "client_order_id": "34x", "ticker": "KXUFCOCCUR-26X-T",
            "yes_price_dollars": bad, "fill_count_fp": "1.00", "order_id": "o",
        }
        with pytest.raises(ValueError):
            mod.reconstruct_v1_filled_order(rec, "2026-05-30T00:00:00Z")
