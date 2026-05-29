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
        [bot_name] free_cash=$X + in_positions=$Y = total=$Z | placed N (skip: ...)
        extra lines...

    `cash_usd` is the FREE CASH available for new orders, returned by
    Kalshi /portfolio/balance under field `balance`. This matches what
    the Kalshi web UI labels "Cash".

    `positions_usd` is the NOTIONAL VALUE of currently-filled positions,
    returned under field `portfolio_value`. Matches Kalshi UI "Positions".

    Pass None if the read failed (the function falls back to "?"
    placeholders so the heartbeat still goes out, signaling the bot is
    alive but its balance read failed).
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
        f"[{bot_name}] free_cash={_money(cash_usd)} + "
        f"in_positions={_money(positions_usd)} = total={_money(total)} "
        f"| placed {placed}{skip_str}"
    )
    if extra_lines:
        return main + "\n" + "\n".join(extra_lines)
    return main


def format_settlement_alert(
    *,
    bot_name: str,
    ticker: str,
    outcome: int | str | None,
    realized_pnl_usd: float,
    filled_count: int,
    entry_price: float | None,
    cumulative_pnl_usd: float,
    settled_count: int,
    winners: int,
    losers: int,
) -> str:
    """Build a per-settlement Discord alert with running totals.

    Each bot fires this once per resolved market (when reconcile_settlements
    detects a newly-settled position). The cumulative numbers come from
    LiveState.realized_pnl_total_usd (running total) and a fresh count
    of closed orders with non-None realized_pnl_usd.

    `outcome` is 1 (YES win), 0 (NO loss), -1 (void), or None for unknown.
    `entry_price` is the maker fill price in dollars; None if not tracked.
    """
    if outcome == 1 or str(outcome).lower() == "yes":
        outcome_str = "YES (win)"
        emoji = "WIN"
    elif outcome == 0 or str(outcome).lower() == "no":
        outcome_str = "NO (loss)"
        emoji = "LOSS"
    elif outcome == -1 or str(outcome).lower() == "void":
        outcome_str = "VOID"
        emoji = "VOID"
    else:
        outcome_str = "UNKNOWN"
        emoji = "??"
    entry_str = (
        f" @ ${entry_price:.2f}" if entry_price is not None else ""
    )
    def _signed_money(x: float) -> str:
        """Render -1.15 as '-$1.15' and 0.25 as '+$0.25'."""
        sign = "+" if x >= 0 else "-"
        return f"{sign}${abs(x):.2f}"
    lines = [
        f"[{bot_name}] {emoji} SETTLED {ticker}",
        f"  outcome={outcome_str} | {filled_count}c{entry_str} "
        f"| realized={_signed_money(realized_pnl_usd)}",
        f"  RUNNING TOTAL: {_signed_money(cumulative_pnl_usd)} "
        f"across {settled_count} settled ({winners}W / {losers}L)",
    ]
    return "\n".join(lines)
