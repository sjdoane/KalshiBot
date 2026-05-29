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


def format_loop_heartbeat(
    *,
    bot_name: str,
    cash_usd: float | None,
    positions_usd: float | None,
    placed: int,
    skip_counts: dict[str, int] | None = None,
    extra_lines: list[str] | None = None,
) -> str:
    """Build a unified per-loop heartbeat Discord message used by BOTH
    the v1 and v14 bots so the operator sees identical structure.

    Format:
        [bot_name] $cash + $positions = $total | placed N (skip: k1=v1, k2=v2) | extra ...

    `cash_usd` and `positions_usd` are the LIVE Kalshi /portfolio/balance
    numbers, NOT persisted state. Pass None if the read failed (the
    function falls back to "?" placeholders so the heartbeat still goes
    out, signaling the bot is alive but its balance read failed).

    `skip_counts` is a flat dict of skip-reason -> count. Keys are short
    snake_case strings (e.g. "budget", "dedup", "denylist"). Zero counts
    are dropped to keep the line readable.

    `extra_lines` is a list of additional short status lines appended
    after the main heartbeat line.
    """
    def _money(x: float | None) -> str:
        return f"${x:.2f}" if x is not None else "$?.??"
    total = (
        (cash_usd or 0.0) + (positions_usd or 0.0)
        if cash_usd is not None and positions_usd is not None
        else None
    )
    skip_parts = []
    if skip_counts:
        for k in sorted(skip_counts):
            v = skip_counts[k]
            if v:
                skip_parts.append(f"{k}={v}")
    skip_str = (
        f" (skip: {', '.join(skip_parts)})" if skip_parts else ""
    )
    main = (
        f"[{bot_name}] {_money(cash_usd)} cash + {_money(positions_usd)} pos "
        f"= {_money(total)} | placed {placed}{skip_str}"
    )
    if extra_lines:
        return main + "\n" + "\n".join(extra_lines)
    return main
