"""One-shot smoke test for the Discord webhook configured in .env.

Sends a single Project Kalshi heartbeat message; exits 0 on success and
non-zero with a clear error on failure. Useful both as an immediate
sanity check after wiring DISCORD_WEBHOOK_URL and as a heartbeat we can
schedule pre-live to keep the channel alive.

Usage:
    uv run python -m scripts.test_discord
"""

from __future__ import annotations

import sys

import structlog

from kalshi_bot.alerts.discord import DiscordAlertError, post
from kalshi_bot.config import load_settings
from kalshi_bot.logging import configure_logging


def main() -> int:
    configure_logging()
    log = structlog.get_logger("test_discord")
    settings = load_settings()
    if not settings.DISCORD_WEBHOOK_URL:
        log.error("webhook_not_configured")
        print("FAIL: DISCORD_WEBHOOK_URL is empty in .env", file=sys.stderr)
        return 1
    try:
        post(
            settings.DISCORD_WEBHOOK_URL,
            "Project Kalshi: Discord webhook smoke test - "
            "you should only see this if .env is wired correctly.",
        )
    except (DiscordAlertError, ValueError) as exc:
        log.error("send_failed", error=str(exc))
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print("OK: Discord message sent. Check your channel.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
