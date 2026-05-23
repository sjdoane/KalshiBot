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
