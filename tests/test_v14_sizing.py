"""Tests for v14 fractional-Kelly position sizing + shared Discord formatters.

v14 had NO committed tests (flagged in research/v14/04-LIVE-DEPLOYMENT-GUIDE.md
known limitations). This covers the new sizing function and the shared
alert formatters since both now drive live capital decisions.
"""

from __future__ import annotations

import importlib
import os

import pytest


def _reload_daemon(**env):
    """Reload the v14 daemon module with the given env vars set, so the
    module-level Kelly constants pick up overrides. Returns the module."""
    for k, v in env.items():
        os.environ[k] = v
    import kalshi_bot_v14.daemon as d
    importlib.reload(d)
    return d


def test_half_kelly_default_budget():
    """Default half-Kelly: 0.5 * 0.30 * cap = 0.15 * cap."""
    for k in ("V14_KELLY_FRACTION", "V14_MAX_FIRE_FRACTION_OF_CAP"):
        os.environ.pop(k, None)
    d = _reload_daemon()
    # cap $20 -> 0.5*0.30*20 = $3.00
    assert d.v14_per_fire_budget_usd(20.0) == pytest.approx(3.0, abs=1e-9)
    # cap $13.20 -> $1.98
    assert d.v14_per_fire_budget_usd(13.20) == pytest.approx(1.98, abs=1e-9)


def test_quarter_kelly_env_override():
    d = _reload_daemon(V14_KELLY_FRACTION="0.25")
    # 0.25 * 0.30 * 20 = $1.50
    assert d.v14_per_fire_budget_usd(20.0) == pytest.approx(1.50, abs=1e-9)


def test_hard_ceiling_caps_overbet():
    """Even an absurd Kelly fraction is capped at MAX_FIRE_FRACTION_OF_CAP."""
    d = _reload_daemon(V14_KELLY_FRACTION="5.0", V14_MAX_FIRE_FRACTION_OF_CAP="0.40")
    # raw kelly = 5.0*0.30*20 = $30 but ceiling = 0.40*20 = $8
    assert d.v14_per_fire_budget_usd(20.0) == pytest.approx(8.0, abs=1e-9)


def test_zero_cap_returns_zero():
    d = _reload_daemon(V14_KELLY_FRACTION="0.50")
    assert d.v14_per_fire_budget_usd(0.0) == 0.0


def test_budget_scales_linearly_with_cap():
    d = _reload_daemon(V14_KELLY_FRACTION="0.50")
    b50 = d.v14_per_fire_budget_usd(50.0)
    b100 = d.v14_per_fire_budget_usd(100.0)
    assert b100 == pytest.approx(2 * b50, abs=1e-9)


def test_contracts_derivation_at_realistic_price():
    """At $51 total -> cap $20.40 -> $3.06 budget -> 6 contracts @ $0.47."""
    d = _reload_daemon(V14_KELLY_FRACTION="0.50")
    cap = 0.40 * 51.0
    budget = d.v14_per_fire_budget_usd(cap)
    contracts = max(1, int(budget // 0.47))
    assert contracts == 6


# --- Shared Discord formatters --------------------------------------------

def test_heartbeat_labels_unambiguous():
    from kalshi_bot.alerts.discord import format_loop_heartbeat
    msg = format_loop_heartbeat(
        bot_name="v14", cash_usd=18.60, positions_usd=14.53, placed=0,
        skip_counts={"outside_window": 15, "no_cash": 0},
    )
    assert "free_cash=$18.60" in msg
    assert "in_positions=$14.53" in msg
    assert "total=$33.13" in msg
    # zero-count skip reasons are dropped
    assert "no_cash" not in msg
    assert "outside_window=15" in msg


def test_heartbeat_handles_failed_balance_read():
    from kalshi_bot.alerts.discord import format_loop_heartbeat
    msg = format_loop_heartbeat(
        bot_name="v1", cash_usd=None, positions_usd=None, placed=0,
    )
    assert "$?.??" in msg  # still emits, signals read failure


def test_settlement_alert_win_and_loss_signs():
    from kalshi_bot.alerts.discord import format_settlement_alert
    win = format_settlement_alert(
        bot_name="v1", ticker="KX-1", outcome=1, realized_pnl_usd=0.25,
        filled_count=1, entry_price=0.75, cumulative_pnl_usd=0.71,
        settled_count=20, winners=12, losers=8,
    )
    assert "WIN" in win
    assert "realized=+$0.25" in win
    assert "RUNNING TOTAL: +$0.71" in win
    assert "(12W / 8L)" in win

    loss = format_settlement_alert(
        bot_name="v14", ticker="KX-2", outcome=0, realized_pnl_usd=-1.15,
        filled_count=2, entry_price=0.57, cumulative_pnl_usd=-0.44,
        settled_count=3, winners=1, losers=2,
    )
    assert "LOSS" in loss
    # negative renders as -$1.15, NOT $-1.15
    assert "realized=-$1.15" in loss
    assert "$-" not in loss
    assert "RUNNING TOTAL: -$0.44" in loss


def test_settlement_alert_void():
    from kalshi_bot.alerts.discord import format_settlement_alert
    msg = format_settlement_alert(
        bot_name="v1", ticker="KX-3", outcome=-1, realized_pnl_usd=-0.02,
        filled_count=1, entry_price=0.50, cumulative_pnl_usd=0.10,
        settled_count=5, winners=3, losers=2,
    )
    assert "VOID" in msg
