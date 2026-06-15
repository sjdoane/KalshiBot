"""Tests for KillTriggerMonitor.

Each test exercises one trigger in isolation by constructing the
relevant settled-trade history and asserting the trip reason.
"""

from __future__ import annotations

import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from kalshi_bot.risk.kill_triggers import (
    KillReason,
    KillTriggerConfig,
    KillTriggerMonitor,
)


@pytest.fixture
def tmp_state_path() -> Path:
    with tempfile.TemporaryDirectory() as tmp:
        yield Path(tmp) / "kill_state.json"


def _ts(offset_days: int = 0) -> str:
    return (datetime.now(UTC) + timedelta(days=offset_days)).isoformat()


def test_initial_state_not_tripped(tmp_state_path: Path) -> None:
    m = KillTriggerMonitor(starting_bankroll_usd=25.0, state_path=tmp_state_path)
    assert m.allowed_to_place_orders() is True
    assert m.fill_rate() is None


def test_yes_rate_trips_at_below_threshold(tmp_state_path: Path) -> None:
    m = KillTriggerMonitor(starting_bankroll_usd=25.0, state_path=tmp_state_path)
    # 16 wins, 4 losses out of 20 = 80% YES rate, below 90% threshold.
    outcomes = [1] * 16 + [0] * 4
    reason: KillReason | None = None
    for i, o in enumerate(outcomes):
        pnl = 0.05 if o == 1 else -0.70
        reason = m.record_settlement(pnl_per_contract=pnl, outcome=o, settle_ts=_ts(i))
    assert reason == KillReason.YES_RATE_DROP
    assert m.allowed_to_place_orders() is False


def test_yes_rate_does_not_trip_before_window(tmp_state_path: Path) -> None:
    m = KillTriggerMonitor(starting_bankroll_usd=25.0, state_path=tmp_state_path)
    # 10 records, 70% YES rate; below threshold but window not reached.
    outcomes = [1] * 7 + [0] * 3
    for i, o in enumerate(outcomes):
        pnl = 0.05 if o == 1 else -0.70
        m.record_settlement(pnl_per_contract=pnl, outcome=o, settle_ts=_ts(i))
    assert m.allowed_to_place_orders() is True


def test_single_loss_dollar_fallback_trips(tmp_state_path: Path) -> None:
    """Before 20 winners, a single loss > 10% of bankroll trips."""
    m = KillTriggerMonitor(starting_bankroll_usd=25.0, state_path=tmp_state_path)
    # Record a loss of $3 with no winners; threshold is 10% * 25 = $2.50.
    reason = m.record_settlement(pnl_per_contract=-3.0, outcome=0, settle_ts=_ts(0))
    assert reason == KillReason.SINGLE_LOSS_DOLLAR


def test_single_loss_dollar_does_not_trip_under_threshold(tmp_state_path: Path) -> None:
    m = KillTriggerMonitor(starting_bankroll_usd=25.0, state_path=tmp_state_path)
    reason = m.record_settlement(pnl_per_contract=-2.0, outcome=0, settle_ts=_ts(0))
    assert reason is None


def test_single_loss_vs_winners_armed_after_20_winners(tmp_state_path: Path) -> None:
    m = KillTriggerMonitor(starting_bankroll_usd=25.0, state_path=tmp_state_path)
    # 20 winners at +$0.05 each. Winner mean = 0.05. 15x = 0.75.
    for i in range(20):
        m.record_settlement(pnl_per_contract=0.05, outcome=1, settle_ts=_ts(i))
    # Loss of $0.80 > 0.75 should trip the 15x-winners rule.
    reason = m.record_settlement(pnl_per_contract=-0.80, outcome=0, settle_ts=_ts(21))
    assert reason == KillReason.SINGLE_LOSS_VS_WINNERS


def test_single_loss_vs_winners_does_not_trip_under_15x(tmp_state_path: Path) -> None:
    m = KillTriggerMonitor(starting_bankroll_usd=25.0, state_path=tmp_state_path)
    for i in range(20):
        m.record_settlement(pnl_per_contract=0.05, outcome=1, settle_ts=_ts(i))
    # Loss of $0.50 < 15 * 0.05 = 0.75
    reason = m.record_settlement(pnl_per_contract=-0.50, outcome=0, settle_ts=_ts(21))
    assert reason is None


def test_fill_rate_does_not_trip_under_min_attempts(tmp_state_path: Path) -> None:
    m = KillTriggerMonitor(starting_bankroll_usd=25.0, state_path=tmp_state_path)
    # 40 attempts, 10 fills (25% rate); below threshold but under 50 min attempts.
    for _ in range(40):
        m.record_attempt()
    for _ in range(10):
        m.record_fill()
    # Record a settlement to drive the trigger check.
    reason = m.record_settlement(pnl_per_contract=0.05, outcome=1, settle_ts=_ts(0))
    assert reason is None
    assert m.allowed_to_place_orders() is True


def test_fill_rate_demoted_does_not_trip_by_default(tmp_state_path: Path) -> None:
    # 2026-05-30 council: fill_rate is a logged health metric, not a kill, by
    # default. A low fill rate must NOT halt trading.
    m = KillTriggerMonitor(starting_bankroll_usd=25.0, state_path=tmp_state_path)
    for _ in range(50):
        m.record_attempt()
    for _ in range(10):  # 20% fill rate, below the 0.30 floor
        m.record_fill()
    reason = m.record_settlement(pnl_per_contract=0.05, outcome=1, settle_ts=_ts(0))
    assert reason is None
    assert not m.state.tripped


def test_fill_rate_still_trips_when_kill_explicitly_enabled(tmp_state_path: Path) -> None:
    from kalshi_bot.risk.kill_triggers import KillTriggerConfig
    m = KillTriggerMonitor(
        starting_bankroll_usd=25.0, state_path=tmp_state_path,
        config=KillTriggerConfig(fill_rate_kill=True),
    )
    for _ in range(50):
        m.record_attempt()
    for _ in range(10):  # 20% fill rate
        m.record_fill()
    reason = m.record_settlement(pnl_per_contract=0.05, outcome=1, settle_ts=_ts(0))
    assert reason == KillReason.FILL_RATE_LOW


def test_clear_reset_fill_counters(tmp_state_path: Path) -> None:
    m = KillTriggerMonitor(starting_bankroll_usd=25.0, state_path=tmp_state_path)
    for _ in range(50):
        m.record_attempt()
    for _ in range(10):
        m.record_fill()
    m.record_settlement(pnl_per_contract=0.05, outcome=1, settle_ts=_ts(0))
    m.clear(reset_fill_counters=True)
    assert m.state.placement_attempts_total == 0
    assert m.state.placement_filled_total == 0
    assert not m.state.tripped
    assert len(m.state.recent_outcomes) == 1  # P&L/outcome history preserved


def test_edge_compression_is_soft_auto_recovering_pause(tmp_state_path: Path) -> None:
    """Edge compression is a NON-LATCHING, auto-recovering PAUSE with hysteresis,
    not a latching kill. Regression for the recurring 2026-06-13 / 06-15 false
    halts: a compressed trailing-30 must pause then auto-resume, never latch."""
    cfg = KillTriggerConfig(rolling_30_mean_pp_min=-3.0, rolling_30_resume_pp_min=0.0)
    m = KillTriggerMonitor(starting_bankroll_usd=25.0, state_path=tmp_state_path, config=cfg)
    # Below the pause floor (mean -4pp): soft pause engages; hard kill does NOT.
    m.state.recent_pnl_per_contract = [-0.04] * 30
    assert m.evaluate_soft_pause() is not None
    assert m.state.soft_paused is True
    assert m.state.tripped is False
    assert m.allowed_to_place_orders() is True
    # Hysteresis: recovered into the band [-3, 0) (mean -1pp) -> still paused.
    m.state.recent_pnl_per_contract = [-0.01] * 30
    assert m.evaluate_soft_pause() is not None
    assert m.state.soft_paused is True
    # Recovered to/above the resume floor (mean +1pp) -> AUTO-resumes, no reset.
    m.state.recent_pnl_per_contract = [0.01] * 30
    assert m.evaluate_soft_pause() is None
    assert m.state.soft_paused is False


def test_rolling_30_does_not_latch_a_hard_kill(tmp_state_path: Path) -> None:
    """A compressed trailing-30 window must NOT produce a latching KillReason
    from the settlement path (it is the soft pause now, not Trigger 6)."""
    cfg = KillTriggerConfig(rolling_30_mean_pp_min=-3.0, rolling_30_resume_pp_min=0.0)
    m = KillTriggerMonitor(starting_bankroll_usd=25.0, state_path=tmp_state_path, config=cfg)
    # Healthy outcomes (yes-rate fine) + a slightly-compressed window; the
    # removed Trigger 6 must not fire, and the last fill is a small win so the
    # catastrophic single-loss trigger cannot fire either.
    m.state.recent_outcomes = [1] * 30
    m.state.winner_pnl_per_contract = [0.20] * 25
    m.state.recent_pnl_per_contract = [-0.04] * 29
    reason = m.record_settlement(pnl_per_contract=0.20, outcome=1, settle_ts=_ts(0))
    assert reason != KillReason.ROLLING_30_EDGE_COMPRESSED
    assert not m.state.tripped


def test_soft_pause_persists_and_clears_through_state(tmp_state_path: Path) -> None:
    """soft_paused round-trips through save/load and clear() resets it."""
    cfg = KillTriggerConfig(rolling_30_mean_pp_min=-3.0, rolling_30_resume_pp_min=0.0)
    m = KillTriggerMonitor(starting_bankroll_usd=25.0, state_path=tmp_state_path, config=cfg)
    m.state.recent_pnl_per_contract = [-0.04] * 30
    m.evaluate_soft_pause()
    assert m.state.soft_paused is True
    reloaded = KillTriggerMonitor(starting_bankroll_usd=25.0, state_path=tmp_state_path, config=cfg)
    assert reloaded.state.soft_paused is True
    reloaded.clear()
    assert reloaded.state.soft_paused is False


def test_rolling_mean_negative_14d_trips(tmp_state_path: Path) -> None:
    """Rolling-10 mean stays negative across 14+ calendar days -> trip.

    Need >= 10 entries (so rolling-10 is computable) AND span between
    first-negative-ts and latest settle >= 14 days. Use 18 records at
    2-day spacing to stay BELOW the YES rate window (20) so that
    trigger doesn't fire first. With losses of -0.001 the rolling-30
    compression trigger also can't fire (< 30 records).
    """
    m = KillTriggerMonitor(starting_bankroll_usd=25.0, state_path=tmp_state_path)
    reason: KillReason | None = None
    for i in range(18):
        reason = m.record_settlement(
            pnl_per_contract=-0.001, outcome=0, settle_ts=_ts(i * 2),
        )
    assert reason == KillReason.ROLLING_MEAN_NEGATIVE_2W


def test_rolling_mean_recovers_before_14d_does_not_trip(tmp_state_path: Path) -> None:
    """If rolling-10 mean turns positive again, the timer resets."""
    m = KillTriggerMonitor(starting_bankroll_usd=25.0, state_path=tmp_state_path)
    # 10 small losses; rolling-10 mean is negative.
    for i in range(10):
        m.record_settlement(pnl_per_contract=-0.005, outcome=0, settle_ts=_ts(i))
    assert m.state.rolling_mean_first_negative_ts is not None
    # 3 wins large enough to push the rolling-10 mean positive.
    # At record 13: window = 7 losses (-0.035) + 3 wins (+0.060) = 0.025 / 10
    # = 0.0025 > 0. Total records = 13, below YES rate window of 20.
    for i in range(10, 13):
        m.record_settlement(pnl_per_contract=0.020, outcome=1, settle_ts=_ts(i))
    assert m.allowed_to_place_orders() is True
    assert m.state.rolling_mean_first_negative_ts is None


def test_state_persists_across_instances(tmp_state_path: Path) -> None:
    m1 = KillTriggerMonitor(starting_bankroll_usd=25.0, state_path=tmp_state_path)
    m1.record_attempt()
    m1.record_attempt()
    m1.record_fill()
    m2 = KillTriggerMonitor(starting_bankroll_usd=25.0, state_path=tmp_state_path)
    assert m2.state.placement_attempts_total == 2
    assert m2.state.placement_filled_total == 1


def test_tripped_state_persists(tmp_state_path: Path) -> None:
    m1 = KillTriggerMonitor(starting_bankroll_usd=25.0, state_path=tmp_state_path)
    m1.record_settlement(pnl_per_contract=-3.0, outcome=0, settle_ts=_ts(0))
    assert m1.state.tripped is True
    m2 = KillTriggerMonitor(starting_bankroll_usd=25.0, state_path=tmp_state_path)
    assert m2.state.tripped is True
    assert m2.allowed_to_place_orders() is False


def test_clear_resumes_trading(tmp_state_path: Path) -> None:
    m = KillTriggerMonitor(starting_bankroll_usd=25.0, state_path=tmp_state_path)
    m.record_settlement(pnl_per_contract=-3.0, outcome=0, settle_ts=_ts(0))
    assert m.state.tripped is True
    m.clear()
    assert m.allowed_to_place_orders() is True


def test_tripped_state_ignores_new_records(tmp_state_path: Path) -> None:
    """After tripping, further attempts/fills don't update counters."""
    m = KillTriggerMonitor(starting_bankroll_usd=25.0, state_path=tmp_state_path)
    m.record_settlement(pnl_per_contract=-3.0, outcome=0, settle_ts=_ts(0))
    attempts_at_trip = m.state.placement_attempts_total
    m.record_attempt()
    m.record_fill()
    assert m.state.placement_attempts_total == attempts_at_trip


def test_fill_rate_returns_none_when_no_attempts(tmp_state_path: Path) -> None:
    m = KillTriggerMonitor(starting_bankroll_usd=25.0, state_path=tmp_state_path)
    assert m.fill_rate() is None


def test_fill_rate_computes_correctly(tmp_state_path: Path) -> None:
    m = KillTriggerMonitor(starting_bankroll_usd=25.0, state_path=tmp_state_path)
    for _ in range(10):
        m.record_attempt()
    for _ in range(4):
        m.record_fill()
    assert m.fill_rate() == pytest.approx(0.4, abs=1e-6)


def test_rejects_zero_starting_bankroll(tmp_state_path: Path) -> None:
    with pytest.raises(ValueError, match="must be"):
        KillTriggerMonitor(starting_bankroll_usd=0.0, state_path=tmp_state_path)


def test_clear_reset_history_wipes_outcome_window(tmp_state_path: Path) -> None:
    """clear(reset_history=True) empties the YES-rate / rolling-mean windows so a
    universe change is not gated by old settlements; clear() alone preserves them.
    """
    m = KillTriggerMonitor(starting_bankroll_usd=25.0, state_path=tmp_state_path)
    # 20 settlements at a 60% win rate trips the default 0.90 yes-rate floor.
    for i in range(20):
        m.record_settlement(pnl_per_contract=(0.1 if i % 5 else -0.7),
                            outcome=(1 if i % 5 else 0), settle_ts=_ts(i))
    assert len(m.state.recent_outcomes) == 20
    # Plain clear keeps the history (so it would re-trip).
    m.clear(reset_fill_counters=True)
    assert m.state.tripped is False
    assert len(m.state.recent_outcomes) == 20
    # Full-history clear wipes the windows.
    m.clear(reset_fill_counters=True, reset_history=True)
    assert m.state.recent_outcomes == []
    assert m.state.recent_pnl_per_contract == []
    assert m.state.winner_pnl_per_contract == []
    assert m.state.tripped is False
