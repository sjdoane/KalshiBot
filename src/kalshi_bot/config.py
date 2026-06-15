"""Project configuration loaded from environment and .env.

Hard-coded constants here are the policy floor for the bot. CAPITAL_CAP_USD
is the single load-bearing safety constant referenced by the order gate.
"""

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime configuration. Values without defaults must be in .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Hard safety constants. Pre-trade gate refuses orders that would breach.
    # Operator-authorized capital ceiling is $100; the default value here is
    # the recommended $25 initial deployment per the post-Phase-1 critic.
    # The operator can raise the deployed value up to $100 in `.env` once a
    # strategy validates. Raising past $100 requires explicit operator
    # authorization AND a bump to the `le=` bound below.
    CAPITAL_CAP_USD: float = Field(default=25.0, ge=0.0, le=100.0)
    CAPITAL_ABSOLUTE_FLOOR_USD: float = 25.0
    PER_TRADE_USD: float = 2.0
    PER_MARKET_CAP_PCT: float = 0.10
    MAX_ORDERS_PER_DAY: int = 50
    MAX_OPEN_POSITIONS: int = 25

    # Drawdown circuit breakers (fraction of bankroll)
    DAILY_DD_HALT_PCT: float = 0.10
    WEEKLY_DD_HALT_PCT: float = 0.15
    TOTAL_DD_HALT_PCT: float = 0.25

    # LIVE mode safety. Default is OFF. Operator must edit .env to enable.
    # See research/live-mode-design.md and research/LIVE_READINESS_DECISION.md.
    LIVE_ENABLED: bool = False
    LIVE_OVERRIDE_GATE: bool = False  # bypass acceptance criteria; loud alert
    LIVE_PER_TRADE_USD: float = Field(default=0.95, gt=0.0, le=2.00)
    LIVE_MAX_OPEN_POSITIONS: int = 5
    LIVE_MAX_CLOCK_SKEW_MS: int = 2000

    # Kill triggers from LIVE_READINESS_DECISION.md acceptance criteria.
    # 2026-06-15: the favorite-won-rate check is now a NON-LATCHING,
    # AUTO-RECOVERING soft PAUSE (evaluate_soft_pause), not a latching kill, and
    # its floor is dropped 0.70 -> 0.55. The 0.70-over-20 floor tripped + LATCHED
    # on a normal-variance soft patch (65% over 20) and halted a positive
    # strategy until a manual reset (the 06-15 PM recurrence). The blended
    # favorite-won rate is ~0.80 with ~9pp SD on n=20, so 0.55 (~2.8 SD below)
    # only pauses on a genuine collapse, and it auto-resumes at >= 0.65. The
    # HARD latching kills (catastrophic single loss, 14-day-negative) plus the
    # 20% drawdown remain the EV/capital backstops. See research/v18/02 + 06 and
    # project_kalshi.md 2026-06-15.
    KILL_YES_RATE_MIN: float = 0.55        # soft-pause floor (favorite-won rate over the window)
    KILL_YES_RATE_RESUME_MIN: float = 0.65  # auto-resume when favorite-won rate recovers to this
    KILL_YES_RATE_WINDOW: int = 20
    KILL_ROLLING_MEAN_WINDOW: int = 10
    KILL_ROLLING_MEAN_DAYS_NEGATIVE: int = 14
    # KILL_ROLLING_30_MEAN_PP_MIN recalibrated 2026-06-13 from 0.5 to -3.0.
    # The 0.5pp floor sat INSIDE the strategy's normal live operating range and
    # false-tripped on 2026-06-13 at 0.43pp while the equity curve was rising
    # (24W/6L, rolling-30 since recovered to +0.97pp). The favorite-maker payoff
    # is asymmetric (wins ~+0.20/contract, losses ~-0.77, breakeven win ~79%),
    # so the rolling-30 mean is quantized in ~3.2pp steps by loss count: 6
    # losses/30 ~ +0.6pp, 7 ~ -2.6pp, 8 ~ -5.9pp. A floor just below zero still
    # trips on a single normal-variance unlucky night (7 losses). -3.0 fires
    # only on a genuinely degraded window (8+ losses/30, win rate below ~73%,
    # ~6pp under the ~80% norm) and still ahead of the 20% drawdown kill, so it
    # keeps its early-warning role. The HARD latching backstops are unchanged
    # and remain the real protection: catastrophic single-loss, 14-day-rolling
    # -10-negative, and the external 20% drawdown. (yes-rate is now ALSO a soft
    # auto-recovering pause, see KILL_YES_RATE_MIN above, not a latching kill.)
    # See project_kalshi.md 2026-06-13 / 06-15.
    # 2026-06-15: edge-compression is now a NON-LATCHING, AUTO-RECOVERING soft
    # PAUSE, not a latching kill. The latch was the recurring-false-halt root
    # cause: on this asymmetric-payoff strategy the rolling-30 mean swings ~3pp
    # per extra loss, so a normal unlucky cluster (8 losses/30) dipped below the
    # floor, LATCHED, and halted the bot until a manual reset even after the edge
    # recovered (false halts 06-13 at 0.43pp and 06-15 at -6.04pp, both with the
    # window healthy again hours later). Now the bot PAUSES new placement when
    # the trailing-30 mean < PP_MIN and AUTO-RESUMES when it recovers >=
    # RESUME_PP_MIN (hysteresis); maintenance/cancels keep running; no manual
    # reset. The hard capital kills (20% drawdown, catastrophic single loss,
    # 14-day-negative) are unchanged and remain the real backstops.
    KILL_ROLLING_30_MEAN_PP_MIN: float = -3.0   # soft-pause floor (pause below this)
    KILL_ROLLING_30_RESUME_PP_MIN: float = 0.0  # auto-resume when trailing-30 >= this
    KILL_DRAWDOWN_PCT: float = 0.20  # tighter than HALT (0.25); rolled into DrawdownMonitor
    KILL_LOSS_VS_WINNERS_RATIO: float = 15.0
    KILL_LOSS_VS_WINNERS_MIN_WINNERS: int = 20  # critic-added arming floor
    KILL_LOSS_DOLLAR_FALLBACK_PCT: float = 0.10  # fallback before 20 winners
    KILL_FILL_RATE_MIN: float = 0.30
    KILL_FILL_RATE_MIN_ATTEMPTS: int = 50

    # Acceptance criteria (programmatically enforced unless LIVE_OVERRIDE_GATE)
    ACCEPT_MIN_PAPER_FILLS: int = 50
    ACCEPT_MIN_LEAGUES: int = 3
    ACCEPT_MIN_YES_RATE: float = 0.90
    ACCEPT_MIN_MEAN_PNL_PP: float = 1.0
    ACCEPT_MIN_FILL_RATE: float = 0.40

    # Kalshi API
    KALSHI_ENV: Literal["demo", "prod"] = "demo"
    KALSHI_API_KEY_ID: str = ""
    KALSHI_PRIVATE_KEY_PATH: str = ""
    KALSHI_DEMO_API_KEY_ID: str = ""
    KALSHI_DEMO_PRIVATE_KEY_PATH: str = ""

    # Discord (Phase 4+)
    DISCORD_WEBHOOK_URL: str = ""

    @property
    def kalshi_base_url(self) -> str:
        if self.KALSHI_ENV == "prod":
            return "https://external-api.kalshi.com/trade-api/v2"
        return "https://external-api.demo.kalshi.co/trade-api/v2"

    @property
    def kalshi_ws_url(self) -> str:
        if self.KALSHI_ENV == "prod":
            return "wss://external-api-ws.kalshi.com/trade-api/ws/v2"
        return "wss://external-api-ws.demo.kalshi.co/trade-api/ws/v2"

    @property
    def active_key_id(self) -> str:
        return self.KALSHI_API_KEY_ID if self.KALSHI_ENV == "prod" else self.KALSHI_DEMO_API_KEY_ID

    @property
    def active_private_key_path(self) -> Path:
        p = (
            self.KALSHI_PRIVATE_KEY_PATH
            if self.KALSHI_ENV == "prod"
            else self.KALSHI_DEMO_PRIVATE_KEY_PATH
        )
        return Path(p) if p else Path()


def load_settings() -> Settings:
    return Settings()
