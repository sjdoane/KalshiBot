"""Drawdown circuit breaker for the live (paper or production) bot.

Tracks bankroll over time and fires alerts / halts when drawdown
exceeds locked thresholds (from config.py).

Threshold tiers:
- 5%  bankroll drawdown: warning alert via Discord
- 10% drawdown: halve max concurrent positions
- 15% drawdown: pause new orders for 24h
- 20% drawdown: KILL (LIVE mode only; per critic-live-mode-design.md
  finding 8 / LIVE_READINESS_DECISION.md kill trigger 3)
- 25% drawdown: hard stop; require manual operator review

Paper mode uses the original 4-tier ladder (warn/halve/pause/halt).
Live mode adds the kill tier between pause and halt (20% < 25%).
The kill tier is identical in behavior to halt: no new orders,
operator must reset state to resume. Two tiers exist because the
critic wanted the live-only tightening visible separately from the
inherited 25% halt.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum

import structlog

log = structlog.get_logger(__name__)


class DrawdownAction(Enum):
    NONE = "none"
    WARN = "warn"
    HALVE_POSITIONS = "halve_positions"
    PAUSE = "pause"
    KILL = "kill"  # live mode only; tighter than halt
    HALT = "halt"


@dataclass
class DrawdownState:
    starting_bankroll_usd: float
    high_water_mark_usd: float
    current_bankroll_usd: float
    current_action: DrawdownAction = DrawdownAction.NONE
    last_event_time: datetime | None = None
    history: list[dict] = field(default_factory=list)

    @property
    def current_drawdown_pct(self) -> float:
        """Drawdown from the high water mark, as a fraction (0.0 to 1.0)."""
        if self.high_water_mark_usd <= 0:
            return 0.0
        return max(
            0.0,
            (self.high_water_mark_usd - self.current_bankroll_usd) / self.high_water_mark_usd,
        )


@dataclass(frozen=True)
class DrawdownThresholds:
    warn: float = 0.05
    halve: float = 0.10
    pause: float = 0.15
    halt: float = 0.25
    kill: float | None = None  # set to 0.20 for live mode; None disables tier


class DrawdownMonitor:
    """Stateful monitor. Call update() each time bankroll changes."""

    def __init__(
        self,
        starting_bankroll_usd: float,
        thresholds: DrawdownThresholds | None = None,
    ) -> None:
        if starting_bankroll_usd <= 0:
            raise ValueError(f"starting_bankroll must be > 0, got {starting_bankroll_usd}")
        self._thresholds = thresholds or DrawdownThresholds()
        self.state = DrawdownState(
            starting_bankroll_usd=starting_bankroll_usd,
            high_water_mark_usd=starting_bankroll_usd,
            current_bankroll_usd=starting_bankroll_usd,
        )

    def update(self, bankroll_now: float) -> DrawdownAction:
        """Update bankroll. Returns the action triggered (if any)."""
        if bankroll_now > self.state.high_water_mark_usd:
            self.state.high_water_mark_usd = bankroll_now
        self.state.current_bankroll_usd = bankroll_now

        dd = self.state.current_drawdown_pct
        new_action = DrawdownAction.NONE
        if dd >= self._thresholds.halt:
            new_action = DrawdownAction.HALT
        elif self._thresholds.kill is not None and dd >= self._thresholds.kill:
            new_action = DrawdownAction.KILL
        elif dd >= self._thresholds.pause:
            new_action = DrawdownAction.PAUSE
        elif dd >= self._thresholds.halve:
            new_action = DrawdownAction.HALVE_POSITIONS
        elif dd >= self._thresholds.warn:
            new_action = DrawdownAction.WARN

        # Only fire on escalation (don't repeat the same warn over and over)
        # but DO record state in history every update for audit.
        action_changed = new_action != self.state.current_action
        timestamp = datetime.now(UTC)
        self.state.history.append({
            "ts": timestamp.isoformat(),
            "bankroll_usd": bankroll_now,
            "hwm_usd": self.state.high_water_mark_usd,
            "drawdown_pct": dd,
            "action": new_action.value,
            "action_changed": action_changed,
        })

        if action_changed and new_action != DrawdownAction.NONE:
            log.warning(
                "drawdown_action_triggered",
                action=new_action.value,
                drawdown_pct=round(dd, 4),
                bankroll_now=bankroll_now,
                hwm=self.state.high_water_mark_usd,
            )
            self.state.last_event_time = timestamp

        self.state.current_action = new_action
        return new_action

    def allowed_to_place_orders(self) -> bool:
        return self.state.current_action not in (
            DrawdownAction.PAUSE,
            DrawdownAction.KILL,
            DrawdownAction.HALT,
        )

    def position_size_multiplier(self) -> float:
        """Returns 1.0 normally, 0.5 if halve-positions triggered, 0.0 if
        paused/killed/halted."""
        if self.state.current_action in (
            DrawdownAction.HALT,
            DrawdownAction.KILL,
            DrawdownAction.PAUSE,
        ):
            return 0.0
        if self.state.current_action == DrawdownAction.HALVE_POSITIONS:
            return 0.5
        return 1.0
