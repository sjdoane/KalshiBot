"""Pre-flight checklist for LIVE mode startup.

Critic-required (see research/critic-live-mode-design.md):
- WSL clock-skew check vs Kalshi response Date header.
- Balance >= 2x worst-case-loss * MAX_OPEN_POSITIONS.
- Programmatically enforce LIVE_READINESS_DECISION.md acceptance
  criteria (50+ paper fills, 3+ leagues, YES rate >= 0.90, mean
  realized >= +1pp, fill rate >= 0.40). Override only with
  `LIVE_OVERRIDE_GATE=true` plus a loud Discord alert.
- Sanity-check that live state has no orphan resting orders.

What this module does NOT do (deferred to follow-up, documented in
research/live-mode-design.md Section "What I am DEFERRING"):
- Fee schedule probe against a specific market.
- Write-scope probe via a no-op POST.

Each check is a small named function that returns a CheckResult.
The orchestrator (run_preflight) calls them in order and aborts on
the first failure.
"""

from __future__ import annotations

import email.utils
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import structlog

from kalshi_bot.data.sports import classify_league
from kalshi_bot.strategy.favorite_maker import FAVORITE_UPPER_CAP

if TYPE_CHECKING:
    from kalshi_bot.config import Settings
    from kalshi_bot.data.kalshi_client import KalshiClient
    from kalshi_bot.strategy.live_order_manager import LiveOrderManager
    from kalshi_bot.strategy.order_manager import PaperOrderManager

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    detail: str


class PreflightFailureError(Exception):
    """Raised by run_preflight on the first failed check."""

    def __init__(self, result: CheckResult) -> None:
        self.result = result
        super().__init__(f"preflight {result.name} failed: {result.detail}")


def check_live_enabled(settings: Settings) -> CheckResult:
    if not settings.LIVE_ENABLED:
        return CheckResult(
            "live_enabled", False,
            "LIVE_ENABLED is False in .env; refusing to enter LIVE mode",
        )
    return CheckResult("live_enabled", True, "LIVE_ENABLED=true")


def check_kalshi_env(settings: Settings, expected: str = "prod") -> CheckResult:
    if expected != settings.KALSHI_ENV:
        return CheckResult(
            "kalshi_env", False,
            f"KALSHI_ENV={settings.KALSHI_ENV} but expected {expected}",
        )
    return CheckResult("kalshi_env", True, f"KALSHI_ENV={expected}")


def check_capital_cap(settings: Settings) -> CheckResult:
    # 2026-06-16: the $100 ceiling was removed per operator. v1 sizes off the
    # live Kalshi balance, so this constant does not constrain live deployment;
    # this check is now informational (always passes) and only reports the value.
    return CheckResult(
        "capital_cap", True,
        f"CAPITAL_CAP_USD=${settings.CAPITAL_CAP_USD:.2f} (no ceiling; v1 sizes "
        f"off live balance)",
    )


def check_per_trade_size(settings: Settings) -> CheckResult:
    """Drop the max(1, ...) floor: require LIVE_PER_TRADE_USD to cover
    at least one contract at the worst-case price (FAVORITE_UPPER_CAP).
    Critic finding 7.
    """
    needed = FAVORITE_UPPER_CAP
    if needed > settings.LIVE_PER_TRADE_USD:
        return CheckResult(
            "per_trade_size", False,
            (
                f"LIVE_PER_TRADE_USD=${settings.LIVE_PER_TRADE_USD:.2f} < "
                f"${needed:.2f} (FAVORITE_UPPER_CAP). Cannot afford 1 "
                "contract at worst-case price; raise the value or skip "
                "LIVE mode."
            ),
        )
    return CheckResult(
        "per_trade_size", True,
        f"LIVE_PER_TRADE_USD=${settings.LIVE_PER_TRADE_USD:.2f}",
    )


def check_clock_skew(
    client: KalshiClient,
    max_skew_ms: int,
    *,
    retries: int = 4,
    initial_backoff_s: float = 2.0,
) -> CheckResult:
    """Compare local time vs the Date header on a Kalshi response.

    Critic finding 2; addresses the WSL2 drift-after-suspend gotcha.

    Retries transient network failures (DNS getaddrinfo, connection
    reset, timeout) up to `retries` times with exponential backoff
    starting at `initial_backoff_s`. This avoids spurious preflight
    failures when the bot starts before the host's network/DNS is
    fully up (Task Scheduler-at-logon, after wake-from-sleep, etc.).

    Permanent failures (HTTP 4xx, malformed Date header) still fail
    on first attempt.
    """
    import time as _time

    server_date: str | None = None
    last_exc: Exception | None = None
    backoff = initial_backoff_s
    for attempt in range(1, retries + 1):
        try:
            server_date = client.get_response_date_header()
            break
        except Exception as exc:
            last_exc = exc
            # Heuristic: treat DNS / socket errors as transient.
            msg = str(exc).lower()
            transient = any(
                marker in msg for marker in (
                    "getaddrinfo", "name or service",
                    "connection refused", "timed out", "timeout",
                    "connection reset", "name resolution",
                    "temporary failure", "host", "errno 11001",
                )
            )
            if attempt >= retries or not transient:
                break
            log.info(
                "clock_skew_transient_retry",
                attempt=attempt, max_attempts=retries,
                backoff_s=backoff, error=msg,
            )
            _time.sleep(backoff)
            backoff *= 2.0
    if server_date is None:
        return CheckResult(
            "clock_skew", False,
            (
                f"unable to fetch Kalshi /exchange/status Date header "
                f"after {retries} attempts: {last_exc!s}"
            ),
        )
    if not server_date:
        return CheckResult(
            "clock_skew", False,
            "Kalshi response had no Date header; cannot verify clock",
        )
    try:
        server_dt = email.utils.parsedate_to_datetime(server_date)
    except (TypeError, ValueError) as exc:
        return CheckResult(
            "clock_skew", False,
            f"unable to parse Date header {server_date!r}: {exc!s}",
        )
    if server_dt.tzinfo is None:
        server_dt = server_dt.replace(tzinfo=UTC)
    local_now = datetime.now(UTC)
    delta_ms = abs((local_now - server_dt).total_seconds()) * 1000
    if delta_ms > max_skew_ms:
        return CheckResult(
            "clock_skew", False,
            (
                f"local clock differs from Kalshi by {delta_ms:.0f}ms "
                f"(> {max_skew_ms}ms). The bot runs under Windows: fix in an "
                "elevated PowerShell with `Set-Service W32Time -StartupType "
                "Automatic; Start-Service W32Time; w32tm /resync /force` "
                "(the Windows Time service is often stopped, which lets the "
                "clock drift). Under WSL2 instead use `sudo hwclock -s`."
            ),
        )
    return CheckResult(
        "clock_skew", True, f"skew {delta_ms:.0f}ms within {max_skew_ms}ms",
    )


def check_trading_active(client: KalshiClient) -> CheckResult:
    try:
        status = client.get("/exchange/status")
    except Exception as exc:
        return CheckResult(
            "trading_active", False, f"exchange/status fetch failed: {exc!s}",
        )
    if not status.get("trading_active"):
        return CheckResult(
            "trading_active", False,
            "Kalshi trading_active=false (exchange paused)",
        )
    return CheckResult("trading_active", True, "trading_active=true")


# Multiplier on (FAVORITE_UPPER_CAP * max_concurrent) to compute the
# minimum acceptable balance. Default was 2.0 per the live-mode critic
# (research/critic-live-mode-design.md, finding 2): "Balance >= 2x
# worst-case-loss * MAX_OPEN_POSITIONS." The 2x buffer protects against
# placement-race edge cases, partial fills, and slippage.
#
# Lowered to 1.0 on 2026-05-24 per explicit operator instruction
# ("willing to lose all $32"). At 1.0x the bot still requires balance
# to cover the worst-case max simultaneous exposure - it just removes
# the 2x safety buffer. The KILL trigger at 20% drawdown remains armed
# as the primary stop-loss.
#
# Override via env var BALANCE_PREFLIGHT_MULTIPLIER for testing or
# scenario tuning without code changes.
BALANCE_PREFLIGHT_MULTIPLIER_DEFAULT = 1.0

# Preflight funds at most this many NEW worst-case orders, regardless of
# max_concurrent. max_concurrent scales with TOTAL bankroll, but the bot only
# places a few orders per loop (eligible-fill availability) and the per-loop
# budget gate already prevents resting exposure > cash. Without this cap the
# startup balance requirement scaled with bankroll and blocked the bot's OWN
# restart once it had deployed cash into (multi-contract) positions: required
# 1.0 * 0.95 * (57 - 20) = $35.15 vs $34.09 cash. See research/v20.
PREFLIGHT_MAX_NEW_ORDERS = 8


def _balance_preflight_multiplier() -> float:
    """Read the multiplier from env if present, else fall back to default."""
    raw = os.environ.get("BALANCE_PREFLIGHT_MULTIPLIER")
    if raw is None:
        return BALANCE_PREFLIGHT_MULTIPLIER_DEFAULT
    try:
        val = float(raw)
        if val <= 0:
            return BALANCE_PREFLIGHT_MULTIPLIER_DEFAULT
        return val
    except (TypeError, ValueError):
        return BALANCE_PREFLIGHT_MULTIPLIER_DEFAULT


def check_balance(
    client: KalshiClient,
    settings: Settings,
    *,
    max_concurrent: int,
    currently_open: int = 0,
) -> CheckResult:
    """Require cash balance to cover the NEW orders the bot might place
    this run, i.e. balance >= multiplier * worst_case * (max_concurrent
    - currently_open).

    `currently_open` is the count of resting + filled positions already
    deployed (their cost is no longer in cash). Subtracting them from
    max_concurrent gives the number of NEW orders preflight must back.

    Default multiplier 1.0 (2026-05-24 operator-explicit risk acceptance);
    was 2.0 per the live-mode critic. Worst case loss per contract is
    FAVORITE_UPPER_CAP (0.95 default).
    """
    try:
        balance_payload = client.get("/portfolio/balance")
    except Exception as exc:
        return CheckResult(
            "balance", False,
            f"portfolio/balance fetch failed (auth or scope issue): {exc!s}",
        )
    # Kalshi historically returned balance in cents under "balance" key.
    raw_balance = balance_payload.get("balance")
    if raw_balance is None:
        raw_balance = balance_payload.get("portfolio_balance", 0)
    try:
        balance_cents = int(raw_balance)
    except (TypeError, ValueError):
        return CheckResult(
            "balance", False,
            f"portfolio/balance returned unparseable value {raw_balance!r}",
        )
    balance_usd = balance_cents / 100.0
    multiplier = _balance_preflight_multiplier()
    new_orders_capacity = max(0, max_concurrent - currently_open)
    # Fund only a realistic startup burst, capped, not every free slot (which
    # scales with total bankroll and blocked the bot's own restart once cash was
    # deployed into positions). The per-loop budget gate is the real cap.
    funded_capacity = min(new_orders_capacity, PREFLIGHT_MAX_NEW_ORDERS)
    required = multiplier * FAVORITE_UPPER_CAP * funded_capacity
    if balance_usd < required:
        return CheckResult(
            "balance", False,
            (
                f"balance ${balance_usd:.2f} < required ${required:.2f} "
                f"({multiplier} * {FAVORITE_UPPER_CAP} * {funded_capacity}; "
                f"capped at {PREFLIGHT_MAX_NEW_ORDERS} of {new_orders_capacity} free slots)"
            ),
        )
    return CheckResult(
        "balance", True,
        f"balance ${balance_usd:.2f} >= ${required:.2f} "
        f"({funded_capacity} funded of {new_orders_capacity} free slots)",
    )


@dataclass(frozen=True)
class AcceptanceMetrics:
    settled_count: int
    leagues: frozenset[str]
    yes_rate: float
    mean_pnl_pp: float
    fill_rate: float | None


def compute_acceptance_metrics(paper: PaperOrderManager) -> AcceptanceMetrics:
    """Read paper state and compute the 5 acceptance metrics from
    LIVE_READINESS_DECISION.md.

    fill_rate may be None when placement_attempts_total is 0 (legacy
    state files don't carry this field).
    """
    settled = list(paper.state.closed_orders.values())
    n = len(settled)
    leagues: set[str] = set()
    for o in settled:
        for src in (o.series_ticker, o.event_ticker, o.ticker):
            tag = classify_league(src)
            if tag is not None:
                leagues.add(tag)
                break
    if n > 0:
        yes_rate = sum(1 for o in settled if o.resolution_outcome == 1) / n
        # Per-contract pp = realized_pnl / contracts * 100
        mean_pnl_pp = (
            sum(
                (o.realized_pnl_usd or 0) / max(o.contracts, 1)
                for o in settled
            )
            / n
        ) * 100.0
    else:
        yes_rate = 0.0
        mean_pnl_pp = 0.0
    attempts = paper.state.placement_attempts_total
    fill_count = len(settled) + len(paper.state.filled_orders)
    fill_rate = (fill_count / attempts) if attempts > 0 else None
    return AcceptanceMetrics(
        settled_count=n,
        leagues=frozenset(leagues),
        yes_rate=yes_rate,
        mean_pnl_pp=mean_pnl_pp,
        fill_rate=fill_rate,
    )


def check_acceptance_criteria(
    paper: PaperOrderManager,
    settings: Settings,
) -> CheckResult:
    """Programmatically enforce LIVE_READINESS_DECISION.md acceptance.

    Override path: set LIVE_OVERRIDE_GATE=true in .env. The check still
    runs but failures become warnings (callers must Discord-alert).
    """
    metrics = compute_acceptance_metrics(paper)
    failures: list[str] = []
    if metrics.settled_count < settings.ACCEPT_MIN_PAPER_FILLS:
        failures.append(
            f"settled paper fills {metrics.settled_count} < "
            f"{settings.ACCEPT_MIN_PAPER_FILLS}",
        )
    if len(metrics.leagues) < settings.ACCEPT_MIN_LEAGUES:
        failures.append(
            f"leagues represented {sorted(metrics.leagues)} "
            f"({len(metrics.leagues)}) < {settings.ACCEPT_MIN_LEAGUES}",
        )
    if metrics.yes_rate < settings.ACCEPT_MIN_YES_RATE:
        failures.append(
            f"YES rate {metrics.yes_rate:.3f} < {settings.ACCEPT_MIN_YES_RATE}",
        )
    if metrics.mean_pnl_pp < settings.ACCEPT_MIN_MEAN_PNL_PP:
        failures.append(
            f"mean realized {metrics.mean_pnl_pp:.2f}pp < "
            f"{settings.ACCEPT_MIN_MEAN_PNL_PP}pp",
        )
    if (
        metrics.fill_rate is not None
        and metrics.fill_rate < settings.ACCEPT_MIN_FILL_RATE
    ):
        failures.append(
            f"fill rate {metrics.fill_rate:.3f} < {settings.ACCEPT_MIN_FILL_RATE}",
        )
    if metrics.fill_rate is None and metrics.settled_count > 0:
        failures.append(
            "fill rate cannot be computed (paper state has no "
            "placement_attempts_total); run paper trading with the "
            "current code revision to gather the metric",
        )
    if not failures:
        return CheckResult(
            "acceptance_criteria", True,
            (
                f"settled={metrics.settled_count}, "
                f"leagues={sorted(metrics.leagues)}, "
                f"yes_rate={metrics.yes_rate:.3f}, "
                f"mean_pnl_pp={metrics.mean_pnl_pp:.2f}, "
                f"fill_rate={metrics.fill_rate}"
            ),
        )
    summary = "; ".join(failures)
    if settings.LIVE_OVERRIDE_GATE:
        return CheckResult(
            "acceptance_criteria", True,
            f"OVERRIDE ENABLED (acceptance failed: {summary})",
        )
    return CheckResult("acceptance_criteria", False, summary)


def check_no_orphan_resting(
    client: KalshiClient,
    live: LiveOrderManager,
) -> CheckResult:
    """List Kalshi resting orders. Any unknown to our state is an orphan
    and aborts startup so the operator can reconcile manually."""
    try:
        kalshi_resting = list(
            client.paginate(
                "/portfolio/orders", item_key="orders", limit=100,
                status="resting", max_pages=10,
            ),
        )
    except Exception as exc:
        return CheckResult(
            "no_orphan_resting", False,
            f"unable to list portfolio/orders: {exc!s}",
        )
    known_intent_ids = {o.intent_id for o in live.state.resting.values()}
    known_order_ids = {
        o.order_id for o in live.state.resting.values() if o.order_id
    }
    orphans = []
    for r in kalshi_resting:
        coid = r.get("client_order_id")
        oid = r.get("order_id") or r.get("id")
        if coid in known_intent_ids:
            continue
        if oid and oid in known_order_ids:
            continue
        orphans.append({"order_id": oid, "client_order_id": coid,
                        "ticker": r.get("ticker")})
    if orphans:
        return CheckResult(
            "no_orphan_resting", False,
            f"{len(orphans)} orphan resting order(s) on Kalshi: {orphans!r}",
        )
    return CheckResult(
        "no_orphan_resting", True,
        f"{len(kalshi_resting)} resting order(s); all known to local state",
    )


def run_preflight(
    *,
    settings: Settings,
    client: KalshiClient,
    paper: PaperOrderManager,
    live: LiveOrderManager,
    expected_env: str = "prod",
    max_concurrent: int | None = None,
    currently_open: int = 0,
    skip_acceptance: bool = False,
    skip_balance: bool = False,
) -> list[CheckResult]:
    """Execute the pre-flight checklist. Returns the list of results.

    Raises PreflightFailureError on the first failure. The caller can catch
    and surface to operator; on success returns the full list for
    logging.

    skip_acceptance / skip_balance are used by `--mode live-demo` where
    real-money checks don't apply.

    `currently_open` is the count of resting + filled positions already
    deployed; subtracted from max_concurrent in the balance check so the
    preflight only requires cash for NEW orders. Pass 0 if unknown
    (the caller can derive from `live.open_order_count()`).
    """
    if max_concurrent is None:
        max_concurrent = settings.LIVE_MAX_OPEN_POSITIONS

    results: list[CheckResult] = []

    def _add(r: CheckResult) -> None:
        results.append(r)
        if not r.passed:
            raise PreflightFailureError(r)

    _add(check_live_enabled(settings))
    _add(check_kalshi_env(settings, expected=expected_env))
    _add(check_capital_cap(settings))
    _add(check_per_trade_size(settings))
    _add(check_clock_skew(client, settings.LIVE_MAX_CLOCK_SKEW_MS))
    _add(check_trading_active(client))
    if not skip_balance:
        _add(check_balance(
            client, settings,
            max_concurrent=max_concurrent,
            currently_open=currently_open,
        ))
    if not skip_acceptance:
        _add(check_acceptance_criteria(paper, settings))
    _add(check_no_orphan_resting(client, live))
    return results
