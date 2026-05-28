"""Tests for paper-mode order manager."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from kalshi_bot.strategy.order_manager import OrderStatus, PaperOrderManager


@pytest.fixture
def tmp_state_path() -> Path:
    with tempfile.TemporaryDirectory() as tmp:
        yield Path(tmp) / "state.json"


def test_place_paper_order_creates_record(tmp_state_path: Path) -> None:
    mgr = PaperOrderManager(state_path=tmp_state_path)
    order = mgr.place_paper_order(
        ticker="KXTEST-1", series_ticker="KXTEST", event_ticker="KXTEST",
        side="yes", target_price=0.30, contracts=3,
        expected_net_edge=0.05, recalibrated_prob=0.40, market_mid_at_placement=0.32,
    )
    assert order.status == OrderStatus.PAPER_PENDING
    assert order.order_id in mgr.state.open_orders


def test_state_persists_across_instances(tmp_state_path: Path) -> None:
    mgr1 = PaperOrderManager(state_path=tmp_state_path)
    mgr1.place_paper_order(
        ticker="KXTEST-1", series_ticker="KXTEST", event_ticker="KXTEST",
        side="yes", target_price=0.30, contracts=3,
        expected_net_edge=0.05, recalibrated_prob=0.40, market_mid_at_placement=0.32,
    )
    mgr2 = PaperOrderManager(state_path=tmp_state_path)
    assert len(mgr2.state.open_orders) == 1


def test_reconcile_fills_yes_side(tmp_state_path: Path) -> None:
    mgr = PaperOrderManager(state_path=tmp_state_path)
    mgr.place_paper_order(
        ticker="KXTEST-1", series_ticker="KXTEST", event_ticker="KXTEST",
        side="yes", target_price=0.30, contracts=3,
        expected_net_edge=0.05, recalibrated_prob=0.40, market_mid_at_placement=0.32,
    )
    # A taker SELL of YES at 0.28 (below our 0.30 bid) means our bid got hit.
    trades = [{"yes_price_dollars": "0.28", "taker_side": "no", "created_time": "2025-01-01T00:00:00Z"}]
    filled = mgr.reconcile_fills("KXTEST-1", trades)
    assert len(filled) == 1
    assert filled[0].filled_price == 0.30
    assert filled[0].status == OrderStatus.PAPER_FILLED
    assert len(mgr.state.open_orders) == 0
    assert len(mgr.state.filled_orders) == 1


def test_reconcile_fills_no_side(tmp_state_path: Path) -> None:
    mgr = PaperOrderManager(state_path=tmp_state_path)
    mgr.place_paper_order(
        ticker="KXTEST-1", series_ticker="KXTEST", event_ticker="KXTEST",
        side="no", target_price=0.70, contracts=3,
        expected_net_edge=0.05, recalibrated_prob=0.20, market_mid_at_placement=0.65,
    )
    # A taker BUY of YES at 0.72 means our sell-YES (=buy-NO) ask got hit
    trades = [{"yes_price_dollars": "0.72", "taker_side": "yes", "created_time": "2025-01-01T00:00:00Z"}]
    filled = mgr.reconcile_fills("KXTEST-1", trades)
    assert len(filled) == 1
    assert filled[0].filled_price == 0.70


def test_reconcile_fills_no_match_keeps_open(tmp_state_path: Path) -> None:
    mgr = PaperOrderManager(state_path=tmp_state_path)
    mgr.place_paper_order(
        ticker="KXTEST-1", series_ticker="KXTEST", event_ticker="KXTEST",
        side="yes", target_price=0.30, contracts=3,
        expected_net_edge=0.05, recalibrated_prob=0.40, market_mid_at_placement=0.32,
    )
    # No taker sell at or below 0.30
    trades = [{"yes_price_dollars": "0.35", "taker_side": "yes", "created_time": "2025-01-01T00:00:00Z"}]
    filled = mgr.reconcile_fills("KXTEST-1", trades)
    assert len(filled) == 0
    assert len(mgr.state.open_orders) == 1


def test_settle_at_resolution_yes_wins(tmp_state_path: Path) -> None:
    mgr = PaperOrderManager(state_path=tmp_state_path)
    mgr.place_paper_order(
        ticker="KXTEST-1", series_ticker="KXTEST", event_ticker="KXTEST",
        side="yes", target_price=0.30, contracts=10,
        expected_net_edge=0.05, recalibrated_prob=0.40, market_mid_at_placement=0.32,
    )
    trades = [{"yes_price_dollars": "0.29", "taker_side": "no", "created_time": "2025-01-01T00:00:00Z"}]
    mgr.reconcile_fills("KXTEST-1", trades)
    settled = mgr.settle_at_resolution("KXTEST-1", outcome=1, resolution_ts="2025-02-01")
    assert len(settled) == 1
    # YES won; bought at 0.30, payoff = 1.0. Per contract = 1.0 - 0.30 = 0.70 gross
    # Fee = 2 * ceil(0.0175*100*0.30*0.70)/100 = 2 * 1/100 = 0.02
    # Net per contract = 0.70 - 0.02 = 0.68. Total = 10 * 0.68 = 6.80
    assert settled[0].realized_pnl_usd == pytest.approx(6.80, abs=1e-6)
    assert mgr.state.realized_pnl_total_usd == pytest.approx(6.80, abs=1e-6)


def test_settle_at_resolution_yes_loses(tmp_state_path: Path) -> None:
    mgr = PaperOrderManager(state_path=tmp_state_path)
    mgr.place_paper_order(
        ticker="KXTEST-1", series_ticker="KXTEST", event_ticker="KXTEST",
        side="yes", target_price=0.30, contracts=10,
        expected_net_edge=0.05, recalibrated_prob=0.40, market_mid_at_placement=0.32,
    )
    trades = [{"yes_price_dollars": "0.29", "taker_side": "no", "created_time": "2025-01-01T00:00:00Z"}]
    mgr.reconcile_fills("KXTEST-1", trades)
    settled = mgr.settle_at_resolution("KXTEST-1", outcome=0, resolution_ts="2025-02-01")
    # YES lost; bought at 0.30, payoff = 0. Per contract = 0 - 0.30 = -0.30 gross
    # Net = -0.30 - 0.02 = -0.32. Total = 10 * -0.32 = -3.20
    assert settled[0].realized_pnl_usd == pytest.approx(-3.20, abs=1e-6)


def test_current_paper_bankroll_starts_at_default(tmp_state_path: Path) -> None:
    mgr = PaperOrderManager(state_path=tmp_state_path)
    assert mgr.current_paper_bankroll() == 25.0


def test_current_paper_bankroll_updates_after_settlement(tmp_state_path: Path) -> None:
    mgr = PaperOrderManager(state_path=tmp_state_path)
    mgr.place_paper_order(
        ticker="KXTEST-1", series_ticker="KXTEST", event_ticker="KXTEST",
        side="yes", target_price=0.30, contracts=2,
        expected_net_edge=0.05, recalibrated_prob=0.40, market_mid_at_placement=0.32,
    )
    trades = [{"yes_price_dollars": "0.29", "taker_side": "no", "created_time": "2025-01-01T00:00:00Z"}]
    mgr.reconcile_fills("KXTEST-1", trades)
    mgr.settle_at_resolution("KXTEST-1", outcome=1, resolution_ts="2025-02-01")
    # Started at 25.0, +1.36 P&L (2 contracts * 0.68) = 26.36
    assert mgr.current_paper_bankroll() == pytest.approx(26.36, abs=1e-6)
