"""Runtime kill triggers for LIVE mode trading.

Enforces the 6 acceptance-criteria-derived triggers from
LIVE_READINESS_DECISION.md and the critic-added 6th (rolling-30 mean
below half-expected edge):

1. YES rate over last KILL_YES_RATE_WINDOW fills < KILL_YES_RATE_MIN.
2. 10-trade rolling mean P&L stays negative for
   KILL_ROLLING_MEAN_DAYS_NEGATIVE consecutive days.
3. Drawdown is owned by DrawdownMonitor (kill tier at 20%); this
   module does NOT duplicate that check, per critic finding 8.
4. Any single loss exceeds KILL_LOSS_VS_WINNERS_RATIO * winning_mean,
   but ONLY after >= KILL_LOSS_VS_WINNERS_MIN_WINNERS winners exist.
   Before that, use a fixed-dollar fallback: single_loss >
   KILL_LOSS_DOLLAR_FALLBACK_PCT * starting_bankroll.
5. Fill rate (filled / attempted) < KILL_FILL_RATE_MIN after
   KILL_FILL_RATE_MIN_ATTEMPTS attempts.
6. Rolling-30 fills mean P&L (in pp): edge compression. As of 2026-06-15
   this is NO LONGER a latching kill but a non-latching, AUTO-RECOVERING
   soft PAUSE (evaluate_soft_pause): it pauses NEW placement while the
   trailing-30 mean < KILL_ROLLING_30_MEAN_PP_MIN and auto-resumes once it
   recovers >= KILL_ROLLING_30_RESUME_PP_MIN (hysteresis), with no manual
   reset. This fixed the recurring false halts (06-13, 06-15) where a normal
   unlucky cluster latched the kill and stranded a healthy strategy.

Triggers 1, 2, 4 (and the external 20% drawdown) are HARD latching kills:
on trip, tripped=True with a reason string and the operator must explicitly
clear state to resume (reset_v1_kill, or delete kill_state.json); they
persist across restarts. Trigger 6 (edge compression) latches NOTHING and
self-clears. Trigger 5 (fill rate) is a logged metric by default.

State is persisted to data/live_trades/kill_state.json.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from pathlib import Path

import structlog

log = structlog.get_logger(__name__)


class KillReason(Enum):
    YES_RATE_DROP = "yes_rate_drop"
    ROLLING_MEAN_NEGATIVE_2W = "rolling_mean_negative_2w"
    SINGLE_LOSS_VS_WINNERS = "single_loss_vs_winners"
    SINGLE_LOSS_DOLLAR = "single_loss_dollar"
    FILL_RATE_LOW = "fill_rate_low"
    ROLLING_30_EDGE_COMPRESSED = "rolling_30_edge_compressed"


@dataclass
class KillTriggerState:
    """Persisted state. Lists are oldest-first; we cap at 200 entries."""

    starting_bankroll_usd: float = 25.0
    recent_pnl_per_contract: list[float] = field(default_factory=list)
    recent_outcomes: list[int] = field(default_factory=list)
    recent_settle_timestamps: list[str] = field(default_factory=list)
    placement_attempts_total: int = 0
    placement_filled_total: int = 0
    winner_pnl_per_contract: list[float] = field(default_factory=list)
    rolling_mean_first_negative_ts: str | None = None
    tripped: bool = False
    soft_paused: bool = False              # non-latching edge-compression pause (auto-recovers)
    trip_reason: str | None = None
    trip_ts: str | None = None
    trip_detail: str | None = None
    last_updated_ts: str = ""


@dataclass(frozen=True)
class KillTriggerConfig:
    yes_rate_min: float = 0.90
    yes_rate_window: int = 20
    rolling_mean_window: int = 10
    rolling_mean_days_negative: int = 14
    # Edge-compression is a SOFT, auto-recovering PAUSE (not a latching kill):
    # rolling_30_mean_pp_min is the pause floor, rolling_30_resume_pp_min the
    # (higher) auto-resume floor. See evaluate_soft_pause + config.py + the
    # 2026-06-15 recurring-false-halt fix. Live values come from config.py.
    rolling_30_mean_pp_min: float = -3.0
    rolling_30_resume_pp_min: float = 0.0
    loss_vs_winners_ratio: float = 15.0
    loss_vs_winners_min_winners: int = 20
    loss_dollar_fallback_pct: float = 0.10
    fill_rate_min: float = 0.30
    fill_rate_min_attempts: int = 50
    # Fill rate is a liquidity-matching diagnostic, not an EV signal: a
    # patient deep-favorite maker is inherently low-fill, and the counters
    # also include still-resting bids (pending, not failed). Per the
    # 2026-05-30 council it is DEMOTED to a logged health metric by default;
    # the EV-relevant kills (drawdown, consecutive-loss, edge) remain. Set
    # True only to restore the hard kill.
    fill_rate_kill: bool = False
    max_history_entries: int = 200


class KillTriggerMonitor:
    """Track runtime acceptance metrics and trip on any breach.

    Concurrency: not thread-safe. Single-process invocation only.

    Persistence: JSON at data/live_trades/kill_state.json (or whatever
    state_path is passed). Atomic writes via tempfile + rename, same
    pattern as PaperOrderManager.
    """

    def __init__(
        self,
        starting_bankroll_usd: float,
        state_path: Path | None = None,
        config: KillTriggerConfig | None = None,
    ) -> None:
        if starting_bankroll_usd <= 0:
            raise ValueError(
                f"starting_bankroll must be > 0, got {starting_bankroll_usd}",
            )
        self.state_path = state_path or Path("data/live_trades/kill_state.json")
        self.config = config or KillTriggerConfig()
        self.state = self._load(default_bankroll=starting_bankroll_usd)

    def _load(self, *, default_bankroll: float) -> KillTriggerState:
        if not self.state_path.exists():
            return KillTriggerState(starting_bankroll_usd=default_bankroll)
        try:
            raw = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            log.error("kill_state_corrupted", error=str(exc),
                      path=str(self.state_path))
            raise
        return KillTriggerState(
            starting_bankroll_usd=raw.get("starting_bankroll_usd", default_bankroll),
            recent_pnl_per_contract=list(raw.get("recent_pnl_per_contract", [])),
            recent_outcomes=list(raw.get("recent_outcomes", [])),
            recent_settle_timestamps=list(raw.get("recent_settle_timestamps", [])),
            placement_attempts_total=raw.get("placement_attempts_total", 0),
            placement_filled_total=raw.get("placement_filled_total", 0),
            winner_pnl_per_contract=list(raw.get("winner_pnl_per_contract", [])),
            rolling_mean_first_negative_ts=raw.get("rolling_mean_first_negative_ts"),
            tripped=raw.get("tripped", False),
            soft_paused=raw.get("soft_paused", False),
            trip_reason=raw.get("trip_reason"),
            trip_ts=raw.get("trip_ts"),
            trip_detail=raw.get("trip_detail"),
            last_updated_ts=raw.get("last_updated_ts", ""),
        )

    def _save(self) -> None:
        payload = asdict(self.state)
        payload["last_updated_ts"] = datetime.now(UTC).isoformat()
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        tmp.replace(self.state_path)

    def record_attempt(self) -> None:
        if self.state.tripped:
            return
        self.state.placement_attempts_total += 1
        self._save()

    def record_fill(self) -> None:
        if self.state.tripped:
            return
        self.state.placement_filled_total += 1
        self._save()

    def record_settlement(
        self,
        *,
        pnl_per_contract: float,
        outcome: int,
        settle_ts: str | None = None,
    ) -> KillReason | None:
        """Record a settled trade. Returns a KillReason if a trigger fires."""
        ts = settle_ts or datetime.now(UTC).isoformat()
        cap = self.config.max_history_entries
        self.state.recent_pnl_per_contract.append(pnl_per_contract)
        self.state.recent_outcomes.append(int(outcome))
        self.state.recent_settle_timestamps.append(ts)
        if outcome == 1:
            self.state.winner_pnl_per_contract.append(pnl_per_contract)
            if len(self.state.winner_pnl_per_contract) > cap:
                self.state.winner_pnl_per_contract = self.state.winner_pnl_per_contract[-cap:]
        if len(self.state.recent_pnl_per_contract) > cap:
            self.state.recent_pnl_per_contract = self.state.recent_pnl_per_contract[-cap:]
            self.state.recent_outcomes = self.state.recent_outcomes[-cap:]
            self.state.recent_settle_timestamps = self.state.recent_settle_timestamps[-cap:]
        reason = self._check_triggers(latest_settle_ts=ts)
        if reason is not None:
            self._trip(reason)
        else:
            self._save()
        return reason

    def _check_triggers(self, *, latest_settle_ts: str) -> KillReason | None:
        c = self.config
        s = self.state

        # Trigger 1: YES rate over last N fills.
        if len(s.recent_outcomes) >= c.yes_rate_window:
            window = s.recent_outcomes[-c.yes_rate_window:]
            yes_rate = sum(window) / len(window)
            if yes_rate < c.yes_rate_min:
                self.state.trip_detail = (
                    f"YES rate {yes_rate:.3f} < {c.yes_rate_min} "
                    f"over last {c.yes_rate_window} fills"
                )
                return KillReason.YES_RATE_DROP

        # Trigger 6 (rolling-30 edge compression) is NO LONGER a latching kill.
        # It is a non-latching, AUTO-RECOVERING soft pause, evaluated each loop
        # by evaluate_soft_pause(): on this asymmetric-payoff strategy the
        # rolling-30 mean swings ~3pp per extra loss, so a normal unlucky
        # cluster (8 losses/30) drove it below any fixed floor, LATCHED the kill,
        # and halted the bot until a manual reset even after the edge recovered
        # (the recurring 2026-06-13 / 06-15 false halts). The capital backstops
        # below (catastrophic single loss, 14-day-negative, plus the external
        # 20% drawdown kill) remain HARD latching kills.

        # Trigger 2: rolling-10 mean stays negative for N days.
        if len(s.recent_pnl_per_contract) >= c.rolling_mean_window:
            rolling_10 = s.recent_pnl_per_contract[-c.rolling_mean_window:]
            rolling_10_mean = sum(rolling_10) / len(rolling_10)
            if rolling_10_mean < 0:
                if s.rolling_mean_first_negative_ts is None:
                    s.rolling_mean_first_negative_ts = latest_settle_ts
                else:
                    try:
                        t0 = datetime.fromisoformat(s.rolling_mean_first_negative_ts)
                        t1 = datetime.fromisoformat(latest_settle_ts)
                        elapsed = t1 - t0
                        if elapsed >= timedelta(days=c.rolling_mean_days_negative):
                            self.state.trip_detail = (
                                f"rolling-10 mean negative for "
                                f"{elapsed.days}d (>= {c.rolling_mean_days_negative}d)"
                            )
                            return KillReason.ROLLING_MEAN_NEGATIVE_2W
                    except ValueError:
                        # malformed timestamp; reset the timer to avoid false trips
                        s.rolling_mean_first_negative_ts = latest_settle_ts
            else:
                # Mean recovered; clear the timer.
                s.rolling_mean_first_negative_ts = None

        # Trigger 4: catastrophic single loss.
        latest_pnl = s.recent_pnl_per_contract[-1] if s.recent_pnl_per_contract else 0.0
        if latest_pnl < 0:
            if len(s.winner_pnl_per_contract) >= c.loss_vs_winners_min_winners:
                winner_mean = (
                    sum(s.winner_pnl_per_contract) / len(s.winner_pnl_per_contract)
                )
                threshold = c.loss_vs_winners_ratio * winner_mean
                if abs(latest_pnl) > threshold:
                    self.state.trip_detail = (
                        f"single loss {abs(latest_pnl):.4f} > "
                        f"{c.loss_vs_winners_ratio} * winner_mean "
                        f"({winner_mean:.4f}) = {threshold:.4f}"
                    )
                    return KillReason.SINGLE_LOSS_VS_WINNERS
            else:
                # Fallback: fixed-dollar threshold before enough winners.
                dollar_threshold = c.loss_dollar_fallback_pct * s.starting_bankroll_usd
                if abs(latest_pnl) > dollar_threshold:
                    self.state.trip_detail = (
                        f"single loss {abs(latest_pnl):.4f} > "
                        f"{c.loss_dollar_fallback_pct} * bankroll "
                        f"= {dollar_threshold:.4f} "
                        f"(only {len(s.winner_pnl_per_contract)} winners; "
                        f"15x-winners trigger not yet armed)"
                    )
                    return KillReason.SINGLE_LOSS_DOLLAR

        # Trigger 5: fill rate. Demoted to a logged health metric by default
        # (c.fill_rate_kill). It only HALTS trading when explicitly re-enabled;
        # otherwise a low fill rate is logged for the heartbeat and does not
        # trip, because it is a liquidity diagnostic, not an EV failure.
        if s.placement_attempts_total >= c.fill_rate_min_attempts:
            fill_rate = s.placement_filled_total / s.placement_attempts_total
            if fill_rate < c.fill_rate_min:
                detail = (
                    f"fill rate {fill_rate:.3f} < {c.fill_rate_min} "
                    f"after {s.placement_attempts_total} attempts"
                )
                if c.fill_rate_kill:
                    self.state.trip_detail = detail
                    return KillReason.FILL_RATE_LOW
                log.info("fill_rate_low_metric", detail=detail)

        return None

    def _trip(self, reason: KillReason) -> None:
        self.state.tripped = True
        self.state.trip_reason = reason.value
        self.state.trip_ts = datetime.now(UTC).isoformat()
        log.critical(
            "kill_trigger_tripped",
            reason=reason.value,
            detail=self.state.trip_detail,
            ts=self.state.trip_ts,
        )
        self._save()

    def allowed_to_place_orders(self) -> bool:
        return not self.state.tripped

    def evaluate_soft_pause(self) -> str | None:
        """Non-latching, AUTO-RECOVERING edge-compression pause (call each loop).

        Distinct from the hard latching kills: pauses NEW placement while the
        trailing-30 mean is below the pause floor, and auto-resumes once it
        recovers to the (higher) resume floor. Hysteresis (resume floor above
        pause floor) prevents flapping. Persists `soft_paused` so the pause
        survives loop iterations and restarts but clears itself with no manual
        intervention. Returns a reason string while paused, else None. The hard
        capital kills are untouched and remain the real backstops.
        """
        c = self.config
        s = self.state
        if len(s.recent_pnl_per_contract) < 30:
            if s.soft_paused:
                s.soft_paused = False
                self._save()
            return None
        mean_pp = (sum(s.recent_pnl_per_contract[-30:]) / 30.0) * 100.0
        if s.soft_paused:
            if mean_pp >= c.rolling_30_resume_pp_min:
                s.soft_paused = False
                self._save()
                log.info("soft_pause_cleared", rolling_30_mean_pp=round(mean_pp, 2),
                         resume_pp=c.rolling_30_resume_pp_min)
                return None
            return (
                f"rolling-30 mean {mean_pp:.2f}pp < resume "
                f"{c.rolling_30_resume_pp_min}pp (soft pause, auto-resumes when "
                f"the edge recovers)"
            )
        if mean_pp < c.rolling_30_mean_pp_min:
            s.soft_paused = True
            self._save()
            log.warning("soft_pause_engaged", rolling_30_mean_pp=round(mean_pp, 2),
                        pause_pp=c.rolling_30_mean_pp_min,
                        resume_pp=c.rolling_30_resume_pp_min)
            return (
                f"rolling-30 mean {mean_pp:.2f}pp < {c.rolling_30_mean_pp_min}pp "
                f"(soft pause, auto-resumes >= {c.rolling_30_resume_pp_min}pp)"
            )
        return None

    def clear(
        self, *, reset_fill_counters: bool = False, reset_history: bool = False
    ) -> None:
        """Operator-only: clear the tripped state to resume trading.

        Mutates the loaded state in place. By default preserves the P&L /
        outcome / winner history that feeds the other triggers. With
        reset_fill_counters=True, also zeroes the cumulative placement counters
        so the fill-rate metric starts a fresh window.

        With reset_history=True, ALSO empties the recent P&L / outcome / winner
        / timestamp history. Use ONLY when the strategy or universe has
        materially changed (e.g. v1's 2026-06-01 move to the validated allowlist
        + the moderate-favorite band + the NO-underdog arm), so that the
        YES-rate and rolling-mean triggers are no longer gated by settlements
        from the OLD broad universe (which had a structurally different win
        rate). The drawdown kill (on realized P&L total, held in the order
        manager) is unaffected and remains the catastrophic backstop.
        """
        self.state.tripped = False
        self.state.soft_paused = False
        self.state.trip_reason = None
        self.state.trip_ts = None
        self.state.trip_detail = None
        self.state.rolling_mean_first_negative_ts = None
        if reset_fill_counters:
            self.state.placement_attempts_total = 0
            self.state.placement_filled_total = 0
        if reset_history:
            self.state.recent_pnl_per_contract = []
            self.state.recent_outcomes = []
            self.state.recent_settle_timestamps = []
            self.state.winner_pnl_per_contract = []
        self._save()

    def fill_rate(self) -> float | None:
        if self.state.placement_attempts_total == 0:
            return None
        return self.state.placement_filled_total / self.state.placement_attempts_total
