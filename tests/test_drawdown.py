"""Tests for the drawdown circuit breaker."""

from __future__ import annotations

import pytest

from kalshi_bot.risk.drawdown import (
    DrawdownAction,
    DrawdownMonitor,
    DrawdownThresholds,
)


def test_initial_state_no_action() -> None:
    monitor = DrawdownMonitor(starting_bankroll_usd=25.0)
    assert monitor.state.current_action == DrawdownAction.NONE
    assert monitor.state.high_water_mark_usd == 25.0
    assert monitor.allowed_to_place_orders() is True
    assert monitor.position_size_multiplier() == 1.0


def test_high_water_mark_advances_on_gain() -> None:
    monitor = DrawdownMonitor(starting_bankroll_usd=25.0)
    monitor.update(30.0)
    assert monitor.state.high_water_mark_usd == 30.0
    assert monitor.state.current_drawdown_pct == 0.0


def test_warn_action_at_5pct_drawdown() -> None:
    monitor = DrawdownMonitor(starting_bankroll_usd=25.0)
    monitor.update(30.0)
    action = monitor.update(28.4)  # -5.33% from HWM
    assert action == DrawdownAction.WARN
    assert monitor.allowed_to_place_orders() is True
    assert monitor.position_size_multiplier() == 1.0


def test_halve_action_at_10pct() -> None:
    monitor = DrawdownMonitor(starting_bankroll_usd=25.0)
    monitor.update(30.0)
    action = monitor.update(27.0)  # -10% from HWM
    assert action == DrawdownAction.HALVE_POSITIONS
    assert monitor.allowed_to_place_orders() is True
    assert monitor.position_size_multiplier() == 0.5


def test_pause_action_at_15pct() -> None:
    monitor = DrawdownMonitor(starting_bankroll_usd=25.0)
    monitor.update(30.0)
    action = monitor.update(25.5)  # -15% from HWM
    assert action == DrawdownAction.PAUSE
    assert monitor.allowed_to_place_orders() is False
    assert monitor.position_size_multiplier() == 0.0


def test_halt_action_at_25pct() -> None:
    monitor = DrawdownMonitor(starting_bankroll_usd=25.0)
    monitor.update(30.0)
    action = monitor.update(22.4)  # -25.3% from HWM
    assert action == DrawdownAction.HALT
    assert monitor.allowed_to_place_orders() is False
    assert monitor.position_size_multiplier() == 0.0


def test_recovery_resets_action() -> None:
    """If bankroll recovers above warn threshold, action should go back to NONE."""
    monitor = DrawdownMonitor(starting_bankroll_usd=25.0)
    monitor.update(30.0)
    monitor.update(27.5)  # WARN/HALVE territory
    action = monitor.update(30.5)  # full recovery, new HWM
    assert action == DrawdownAction.NONE
    assert monitor.allowed_to_place_orders() is True


def test_history_accumulates() -> None:
    monitor = DrawdownMonitor(starting_bankroll_usd=25.0)
    monitor.update(30.0)
    monitor.update(28.0)
    monitor.update(25.0)
    assert len(monitor.state.history) == 3
    assert monitor.state.history[-1]["bankroll_usd"] == 25.0


def test_custom_thresholds_override() -> None:
    custom = DrawdownThresholds(warn=0.10, halve=0.20, pause=0.30, halt=0.50)
    monitor = DrawdownMonitor(starting_bankroll_usd=25.0, thresholds=custom)
    monitor.update(30.0)
    action = monitor.update(28.5)  # -5% from HWM, below custom warn=10%
    assert action == DrawdownAction.NONE


def test_rejects_zero_starting_bankroll() -> None:
    with pytest.raises(ValueError, match="must be"):
        DrawdownMonitor(starting_bankroll_usd=0.0)
    with pytest.raises(ValueError, match="must be"):
        DrawdownMonitor(starting_bankroll_usd=-10.0)


def test_kill_tier_not_armed_by_default() -> None:
    """Paper mode does not enable the kill tier; 20% drawdown still PAUSEs."""
    monitor = DrawdownMonitor(starting_bankroll_usd=25.0)
    monitor.update(30.0)
    action = monitor.update(24.0)  # -20% from HWM
    assert action == DrawdownAction.PAUSE


def test_kill_tier_armed_in_live_mode() -> None:
    """Live mode sets kill=0.20; at 20% drawdown the action is KILL not PAUSE."""
    live_thresholds = DrawdownThresholds(
        warn=0.05, halve=0.10, pause=0.15, kill=0.20, halt=0.25,
    )
    monitor = DrawdownMonitor(starting_bankroll_usd=25.0, thresholds=live_thresholds)
    monitor.update(30.0)
    action = monitor.update(24.0)  # -20% from HWM
    assert action == DrawdownAction.KILL
    assert monitor.allowed_to_place_orders() is False
    assert monitor.position_size_multiplier() == 0.0


def test_kill_below_halt_above_pause() -> None:
    """In live mode the KILL tier sits between PAUSE (15%) and HALT (25%)."""
    live_thresholds = DrawdownThresholds(
        warn=0.05, halve=0.10, pause=0.15, kill=0.20, halt=0.25,
    )
    monitor = DrawdownMonitor(starting_bankroll_usd=25.0, thresholds=live_thresholds)
    monitor.update(30.0)
    assert monitor.update(25.4) == DrawdownAction.PAUSE  # 15.3% drawdown
    monitor.update(30.0)
    assert monitor.update(22.4) == DrawdownAction.HALT   # 25.3% drawdown


def test_halt_takes_precedence_over_kill() -> None:
    """If both kill and halt would apply, halt wins (deeper drawdown)."""
    live_thresholds = DrawdownThresholds(
        warn=0.05, halve=0.10, pause=0.15, kill=0.20, halt=0.25,
    )
    monitor = DrawdownMonitor(starting_bankroll_usd=25.0, thresholds=live_thresholds)
    monitor.update(30.0)
    action = monitor.update(20.0)  # 33% drawdown
    assert action == DrawdownAction.HALT
