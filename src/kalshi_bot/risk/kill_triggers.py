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
6. Rolling-30 fills mean P&L (in pp) < KILL_ROLLING_30_MEAN_PP_MIN
   (default 0.5pp). Detects edge compression before outright
   negative. (Critic finding 4.)

On trip: tripped=True with a reason string. Operator must explicitly
clear state to resume (delete kill_state.json or set tripped=False
manually). The trigger persists across restarts.

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
    rolling_30_mean_pp_min: float = 0.5
    loss_vs_winners_ratio: float = 15.0
    loss_vs_winners_min_winners: int = 20
    loss_dollar_fallback_pct: float = 0.10
    fill_rate_min: float = 0.30
    fill_rate_min_attempts: int = 50
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

        # Trigger 6 (critic-added): rolling-30 mean below half-expected.
        if len(s.recent_pnl_per_contract) >= 30:
            rolling_30 = s.recent_pnl_per_contract[-30:]
            rolling_30_mean = sum(rolling_30) / len(rolling_30)
            rolling_30_mean_pp = rolling_30_mean * 100.0
            if rolling_30_mean_pp < c.rolling_30_mean_pp_min:
                self.state.trip_detail = (
                    f"rolling-30 mean {rolling_30_mean_pp:.2f}pp < "
                    f"{c.rolling_30_mean_pp_min}pp (edge compressed)"
                )
                return KillReason.ROLLING_30_EDGE_COMPRESSED

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

        # Trigger 5: fill rate.
        if s.placement_attempts_total >= c.fill_rate_min_attempts:
            fill_rate = s.placement_filled_total / s.placement_attempts_total
            if fill_rate < c.fill_rate_min:
                self.state.trip_detail = (
                    f"fill rate {fill_rate:.3f} < {c.fill_rate_min} "
                    f"after {s.placement_attempts_total} attempts"
                )
                return KillReason.FILL_RATE_LOW

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

    def clear(self) -> None:
        """Operator-only: clear the tripped state to resume trading."""
        self.state.tripped = False
        self.state.trip_reason = None
        self.state.trip_ts = None
        self.state.trip_detail = None
        self.state.rolling_mean_first_negative_ts = None
        self._save()

    def fill_rate(self) -> float | None:
        if self.state.placement_attempts_total == 0:
            return None
        return self.state.placement_filled_total / self.state.placement_attempts_total
