"""Thin Discord webhook client for daily P&L summaries and live alerts.

Phase 4+ uses this. We keep it dead simple: one function that posts a
content payload to the configured webhook URL with a sensible timeout
and retries on transient failures.

Webhook URL lives in .env as DISCORD_WEBHOOK_URL; the helper raises
ValueError if it is missing so the bot fails loudly rather than silently
swallowing alerts.
"""

from __future__ import annotations

import httpx
import structlog
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

log = structlog.get_logger(__name__)


class DiscordAlertError(Exception):
    """Raised when Discord refuses the payload (4xx) or times out repeatedly."""


@retry(
    retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    stop=stop_after_attempt(4),
    reraise=True,
)
def post(webhook_url: str, content: str, *, username: str = "Project Kalshi") -> None:
    """POST a markdown-ish content message to the Discord webhook.

    Discord supports up to 2000 chars in `content`; we truncate beyond
    that with an ellipsis so a single fat alert doesn't lose the head.
    """
    if not webhook_url:
        raise ValueError("DISCORD_WEBHOOK_URL is not set; cannot send alert")
    body = content if len(content) <= 1990 else content[:1985] + "\n..."
    with httpx.Client(timeout=10.0) as client:
        response = client.post(
            webhook_url,
            json={"content": body, "username": username},
        )
    if response.status_code >= 400:
        raise DiscordAlertError(f"Discord {response.status_code}: {response.text[:200]}")
    log.info("discord_sent", bytes=len(body), status=response.status_code)
