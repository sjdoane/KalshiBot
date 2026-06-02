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
    # KILL_YES_RATE_MIN recalibrated 2026-06-01 from 0.90 to 0.70 for v1's new
    # strategy: it now concentrates on MODERATE favorites [0.70,0.86) (true win
    # ~85%, not the ~95% of the old heavy-favorite mix) plus the symmetric
    # NO-underdog arm, so the blended favorite-won rate is ~0.85. A 0.90 floor
    # would trip on the NORMAL win rate; 0.70 gives ~2 SD margin (n=20) while
    # still catching a real breakdown (favorites winning below the ~0.79 price
    # they are bought at = the edge is gone). The drawdown + consecutive-loss
    # kills remain the EV backstops. See research/v18/02 + 06.
    KILL_YES_RATE_MIN: float = 0.70
    KILL_YES_RATE_WINDOW: int = 20
    KILL_ROLLING_MEAN_WINDOW: int = 10
    KILL_ROLLING_MEAN_DAYS_NEGATIVE: int = 14
    KILL_ROLLING_30_MEAN_PP_MIN: float = 0.5  # critic-added 6th trigger
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
