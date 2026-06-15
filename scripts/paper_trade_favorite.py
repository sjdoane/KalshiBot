"""Strategy B trading runner: deep-favorite YES-maker on sports.

Default mode is PAPER (no live capital, simulated fills). LIVE mode
posts real Kalshi /portfolio/orders and requires:
- `LIVE_ENABLED=true` in `.env`
- A passing pre-flight checklist (see kalshi_bot.strategy.preflight)
- Operator interactive confirmation
- Either the LIVE_READINESS_DECISION.md acceptance criteria met OR
  `LIVE_OVERRIDE_GATE=true` in `.env` (with a loud Discord alert)

The bot:
1. Polls Kalshi for open sports markets in series matching our filters.
2. Identifies markets where YES bid (or mid) is in [0.70, 0.95].
3. PAPER: records simulated maker orders, reconciles via trade tape.
   LIVE:  POSTs limit-buy maker orders, reconciles via /portfolio/fills.
4. Settles at resolution and tracks realized P&L.
5. KillTriggerMonitor enforces the 6 acceptance-criteria triggers at
   runtime. Tripping halts new orders.

Usage:
    # PAPER (default; safe)
    uv run python -m scripts.paper_trade_favorite --cadence 900

    # LIVE (requires .env LIVE_ENABLED=true and confirmation prompt)
    uv run python -m scripts.paper_trade_favorite --mode live

    # LIVE-DEMO (demo URL; skips balance + acceptance checks)
    uv run python -m scripts.paper_trade_favorite --mode live-demo
"""

from __future__ import annotations

import argparse
import os
import signal
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import structlog

from kalshi_bot.alerts.discord import (
    format_loop_heartbeat,
    format_settlement_alert,
    post as send_discord,
)
from kalshi_bot.config import load_settings
from kalshi_bot.data.kalshi_client import KalshiClient
from kalshi_bot.logging import configure_logging
from kalshi_bot.risk.adverse_selection_monitor import AdverseSelectionConfig
from kalshi_bot.risk.drawdown import (
    DrawdownAction,
    DrawdownMonitor,
    DrawdownThresholds,
)
from kalshi_bot.risk.kill_triggers import KillTriggerConfig, KillTriggerMonitor
from kalshi_bot.strategy.favorite_maker import (
    FAVORITE_UPPER_CAP,
    FavoriteSideDecision,
    band_size_multiplier,
    compute_dynamic_max_concurrent,
    decide_favorite_side,
    expected_net_edge,
    is_eligible,
    step_in_front,
)
from kalshi_bot.strategy.live_order_manager import LiveOrderManager
from kalshi_bot.strategy.market_scanner import (
    DEFAULT_SERIES_DENYLIST,
    EXPANDED_SERIES_DENYLIST,
    PERSIST_SERIES_ALLOWLIST,
    ScannerConfig,
    scan,
)
from kalshi_bot.strategy.order_manager import PaperOrderManager
from kalshi_bot.strategy.preflight import PreflightFailureError, run_preflight

if TYPE_CHECKING:
    from kalshi_bot.strategy.pricing import MarketSnapshot

log = structlog.get_logger(__name__)

HEARTBEAT_PATH = Path("data/live_trades/heartbeat.txt")

# Sentinel for the dynamic / auto-scaling max_concurrent mode. When
# --max-concurrent is "auto", the bot derives the cap each loop from
# (cash_balance + open_positions_notional) / FAVORITE_UPPER_CAP. As
# wins/losses move the bankroll, the cap auto-adjusts. As positions
# resolve and free cash, capacity grows.
MAX_CONCURRENT_AUTO = "auto"


def _parse_max_concurrent_arg(value: str) -> int | str:
    """argparse type. Accepts the literal 'auto' (case-insensitive) or
    any positive integer. 'auto' triggers dynamic per-loop derivation
    from the current bankroll; an integer is used as a hard ceiling."""
    if isinstance(value, str) and value.strip().lower() == "auto":
        return MAX_CONCURRENT_AUTO
    try:
        n = int(value)
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError(
            f"max-concurrent must be a positive integer or 'auto', got {value!r}"
        ) from exc
    if n < 1:
        raise argparse.ArgumentTypeError(
            f"max-concurrent must be >= 1 (got {n})"
        )
    return n


def _sum_open_positions_value(orders) -> float:
    """Sum (target_price_cents / 100) * (contracts - filled_count) across orders.

    DEPRECATED for live-mode bankroll math. Kept for paper-mode use only.
    The live path now reads `portfolio_value` directly from Kalshi's
    /portfolio/balance response (filled-position notional in cents),
    because the previous implementation summed LOCAL state.resting which
    counted unfilled maker bids as positions and inflated bankroll by
    $40+ when the bot had many stale resting orders on the book
    (diagnosed 2026-05-25: state showed $69.32, reality was $31.30).
    """
    total = 0.0
    for o in orders:
        price_cents = getattr(o, "target_price_cents", None)
        if price_cents is None:
            price_cents = getattr(o, "filled_price_cents", None)
        contracts = getattr(o, "contracts", 0) or 0
        if price_cents is None:
            continue
        total += float(price_cents) / 100.0 * float(contracts)
    return total


def _read_kalshi_balance_and_positions(client: KalshiClient) -> tuple[float, float]:
    """Fetch (cash_usd, positions_value_usd) from Kalshi /portfolio/balance.

    Both come from Kalshi as the single source of truth. `balance` is
    free cash in cents, `portfolio_value` is filled-position notional
    in cents. Resting maker bids that have not filled are NOT included
    in either field (Kalshi does not lock cash on resting maker bids).
    Raises on transport / parse failure; callers decide fallback.
    """
    payload = client.get("/portfolio/balance")
    raw = payload.get("balance")
    if raw is None:
        raw = payload.get("portfolio_balance", 0)
    cash = float(int(raw)) / 100.0
    pos = float(int(payload.get("portfolio_value", 0) or 0)) / 100.0
    return cash, pos


def _resolve_max_concurrent_live(
    setting: int | str,
    lm: LiveOrderManager,
    client: KalshiClient,
) -> int:
    """Convert a setting (int or 'auto') to an int max_concurrent.

    For 'auto': fetch /portfolio/balance, use cash + portfolio_value
    (Kalshi's own filled-position notional) as the total bankroll, then
    derive floor(bankroll / FAVORITE_UPPER_CAP). On any fetch failure,
    fall back to 1 (place at most one new order this loop) and log a
    warning. Returns int.

    NOTE: previously summed local state.resting+filled which inflated
    bankroll by counting unfilled maker bids as positions. Now uses
    Kalshi's portfolio_value field which only counts actual filled
    contracts (changed 2026-05-25).
    """
    if setting != MAX_CONCURRENT_AUTO:
        return int(setting)
    try:
        cash_usd, pos_usd = _read_kalshi_balance_and_positions(client)
    except Exception as exc:
        log.warning("dynamic_max_concurrent_balance_read_failed", error=str(exc))
        return 1
    total = cash_usd + pos_usd
    return compute_dynamic_max_concurrent(total, per_trade_max_usd=FAVORITE_UPPER_CAP)


def _resolve_max_concurrent_paper(
    setting: int | str,
    om: PaperOrderManager,
) -> int:
    """Paper-mode counterpart. Uses om.current_paper_bankroll() as the
    total bankroll source (paper state already tracks realized P&L)."""
    if setting != MAX_CONCURRENT_AUTO:
        return int(setting)
    total = float(om.current_paper_bankroll())
    return compute_dynamic_max_concurrent(total, per_trade_max_usd=FAVORITE_UPPER_CAP)


# Sentinel for auto-read starting bankroll (from Kalshi /portfolio/balance
# plus open positions, at startup). Operator passes "--starting-bankroll
# auto" or omits the arg entirely (auto is the default). The bot
# persists the value to state.json so subsequent restarts maintain
# drawdown continuity; pass --rebaseline to force a fresh re-read
# (useful after deposits/withdrawals).
STARTING_BANKROLL_AUTO = "auto"


def _parse_starting_bankroll_arg(value: str) -> float | str:
    """argparse type. Accepts 'auto' (case-insensitive) or a positive
    float. 'auto' triggers reading from Kalshi /portfolio/balance at
    startup (live/live-demo) or falling back to persisted state value
    (paper)."""
    if isinstance(value, str) and value.strip().lower() == "auto":
        return STARTING_BANKROLL_AUTO
    try:
        v = float(value)
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError(
            f"starting-bankroll must be a positive float or 'auto', got {value!r}"
        ) from exc
    if v <= 0:
        raise argparse.ArgumentTypeError(
            f"starting-bankroll must be > 0 (got {v})"
        )
    return v


def _read_kalshi_total_bankroll_usd(
    client: KalshiClient,
    open_orders,  # noqa: ARG001  kept for backward-compat signature
) -> float:
    """Fetch Kalshi cash balance + Kalshi-reported filled-position
    notional from /portfolio/balance. Returns the total bankroll in USD.

    `open_orders` is accepted but IGNORED (kept for backward-compat
    signature). The old implementation summed local state.resting +
    state.filled as a proxy for positions, but resting maker bids on
    Kalshi do NOT lock cash and are NOT positions; that math inflated
    bankroll by $40+ when 60+ unfilled maker bids were sitting on the
    book (diagnosed 2026-05-25). Kalshi's `portfolio_value` field is
    the authoritative filled-position notional in cents.

    Raises if /portfolio/balance fails; caller decides fallback.
    """
    cash, positions = _read_kalshi_balance_and_positions(client)
    return cash + positions


def _resolve_starting_bankroll_live(
    setting: float | str,
    lm: LiveOrderManager,
    client: KalshiClient,
    *,
    rebaseline: bool,
    log_main,
) -> float:
    """Resolve --starting-bankroll for live/live-demo mode.

    Explicit float -> use it.
    'auto' + live Kalshi read succeeds -> use the live total (cash + open
        positions value). Startup ALWAYS prefers live Kalshi over any
        persisted value, even without --rebaseline, so deposits/withdrawals
        made while the bot was down are reflected; Kalshi /portfolio/balance
        is the single source of truth. The persisted value is logged for diff
        visibility only. Drawdown continuity is intentionally sacrificed for
        operator-correct startup state (commit c0c3225). --rebaseline now only
        affects the no-persisted-value branch and the log messaging.
    'auto' + Kalshi read fails -> last-resort fallback to the persisted state
        value if present, else raise SystemExit with a clear message.
    """
    if setting != STARTING_BANKROLL_AUTO:
        return float(setting)
    persisted = float(getattr(lm.state, "starting_bankroll_usd", 0) or 0)

    # Always try to read live Kalshi at startup so we can auto-detect
    # deposits/withdrawals that happened while the bot was down.
    live_total: float = 0.0
    try:
        open_orders = (
            list(lm.state.resting.values()) + list(lm.state.filled.values())
        )
        live_total = _read_kalshi_total_bankroll_usd(client, open_orders)
    except Exception as exc:
        log_main.warning("startup_kalshi_balance_read_failed", error=str(exc))

    # Forced rebaseline (CLI flag) or no persisted state: prefer live.
    if rebaseline or persisted <= 0:
        if live_total > 0:
            log_main.info(
                "starting_bankroll_from_kalshi",
                value=live_total, rebaseline=rebaseline,
            )
            return live_total
        if persisted > 0:
            log_main.warning(
                "starting_bankroll_fallback_to_state", value=persisted,
            )
            return persisted
        raise SystemExit(
            "Cannot determine starting bankroll: --starting-bankroll auto "
            "failed to read Kalshi /portfolio/balance and no persisted "
            "value exists in state.json. Pass --starting-bankroll <amount> "
            "explicitly to override.",
        )

    # Both persisted and live available. Startup ALWAYS uses live Kalshi
    # so the bankroll value reflects current truth (operator may have
    # deposited or withdrawn while bot was down; Kalshi `/portfolio/balance`
    # is the single source of truth). The persisted value is logged for
    # diff visibility but not used. Drawdown continuity is sacrificed
    # in favor of operator-correct startup state.
    if live_total > 0:
        if abs(live_total - persisted) > 0.01:
            log_main.warning(
                "starting_bankroll_from_kalshi_overrides_persisted",
                persisted=round(persisted, 2),
                live=round(live_total, 2),
                diff_usd=round(live_total - persisted, 2),
            )
        else:
            log_main.info(
                "starting_bankroll_from_kalshi_matches_persisted",
                value=round(live_total, 2),
            )
        return live_total

    log_main.warning(
        "starting_bankroll_fallback_to_state_kalshi_unavailable",
        value=persisted,
    )
    return persisted


def _resolve_starting_bankroll_paper(
    setting: float | str,
    om: PaperOrderManager,
    *,
    rebaseline: bool,
    fallback: float = 25.0,
) -> float:
    """Paper-mode resolver. No Kalshi balance is read in paper mode
    (no live capital). 'auto' uses state.json value or `fallback`.
    """
    if setting != STARTING_BANKROLL_AUTO:
        return float(setting)
    persisted = float(getattr(om.state, "starting_bankroll_usd", 0) or 0)
    if persisted > 0 and not rebaseline:
        return persisted
    return fallback


LAST_SEEN_TOTAL_PATH = Path("data/live_trades/last_seen_total.txt")


def _read_last_seen_total() -> float:
    """Read previous-loop Kalshi total bankroll from sidecar file."""
    try:
        if LAST_SEEN_TOTAL_PATH.exists():
            return float(LAST_SEEN_TOTAL_PATH.read_text(encoding="utf-8").strip())
    except Exception:
        pass
    return 0.0


def _write_last_seen_total(value: float) -> None:
    """Persist current Kalshi total for next loop's bidirectional check."""
    try:
        LAST_SEEN_TOTAL_PATH.parent.mkdir(parents=True, exist_ok=True)
        LAST_SEEN_TOTAL_PATH.write_text(f"{value:.4f}\n", encoding="utf-8")
    except Exception:
        pass


def _auto_rebaseline_bidirectional(
    lm: LiveOrderManager,
    kt: KillTriggerMonitor,
    dd: DrawdownMonitor,
    client: KalshiClient,
    log_main,
    *,
    deposit_threshold: float = 1.20,
    withdrawal_threshold: float = 0.80,
) -> str | None:
    """Detect operator deposits OR withdrawals via single-loop balance jumps.

    Reads live Kalshi total (cash + portfolio_value) from /portfolio/balance.
    Compares against last-seen total (sidecar file). A sudden 20%+ jump in
    either direction is treated as operator intervention (deposit or
    withdrawal); realistic per-loop P&L on small contracts cannot move
    20% in 15 minutes.

    Rebaselines all three monitors (LiveOrderManager, KillTriggerMonitor,
    DrawdownMonitor) to the current total. Always updates the sidecar
    file so next loop has fresh comparison data.

    Returns the rebaseline reason ('deposit', 'withdrawal') or None.
    """
    try:
        cash, pos = _read_kalshi_balance_and_positions(client)
    except Exception:
        return None
    current_total = cash + pos
    prev_total = _read_last_seen_total()
    reason: str | None = None

    if prev_total > 0:
        if current_total >= prev_total * deposit_threshold:
            reason = "deposit"
        elif current_total <= prev_total * withdrawal_threshold:
            reason = "withdrawal"

    # Also handle first-run case: rebaseline if current materially
    # exceeds the persisted baseline (operator forgot to --rebaseline)
    if reason is None:
        baseline = float(getattr(lm.state, "starting_bankroll_usd", 0) or 0)
        if baseline > 0 and current_total >= baseline * 1.30:
            reason = "deposit_vs_baseline"

    if reason is not None:
        log_main.warning(
            "auto_rebaseline_detected",
            reason=reason,
            previous_total=round(prev_total, 2),
            previous_baseline=round(
                float(getattr(lm.state, "starting_bankroll_usd", 0) or 0), 2
            ),
            current_total=round(current_total, 2),
        )
        lm.state.starting_bankroll_usd = current_total
        try:
            lm._save()
        except Exception as exc:
            log_main.error("auto_rebaseline_lm_save_failed", error=str(exc))
        kt.state.starting_bankroll_usd = current_total
        try:
            kt._save()
        except Exception as exc:
            log_main.error("auto_rebaseline_kt_save_failed", error=str(exc))
        if hasattr(dd, "state"):
            dd.state.starting_bankroll_usd = current_total
            if hasattr(dd.state, "high_water_mark_usd"):
                dd.state.high_water_mark_usd = current_total
            if hasattr(dd.state, "current_bankroll_usd"):
                dd.state.current_bankroll_usd = current_total

    _write_last_seen_total(current_total)
    return reason


def _compute_v1_filled_exposure(lm: LiveOrderManager) -> float:
    """Sum of (filled_price * filled_count) across v1 filled positions."""
    total = 0.0
    for o in lm.state.filled.values():
        price_cents = (
            getattr(o, "filled_price_cents", None)
            or getattr(o, "target_price_cents", 0)
            or 0
        )
        count = (
            getattr(o, "filled_count", None)
            or getattr(o, "contracts", 0)
            or 0
        )
        total += float(price_cents) / 100.0 * float(count)
    return total


def v1_per_bid_contracts(
    target_price: float,
    *,
    v1_cap_total: float | None,
    per_bid_fraction: float,
    fallback_usd: float,
) -> int:
    """Dynamic per-bid contract count (2026-05-30 council).

    When a fraction cap is active, the per-bid budget is
    per_bid_fraction * v1_cap_total (v1's live bankroll slice), so each bid
    auto-scales as the operator deposits/withdraws, mirroring v14. With no
    fraction cap, falls back to the legacy fixed dollar. Floors at 1 contract
    so a sub-1 budget still places the minimum (helps fill rate); the
    aggregate budget gate caps total exposure separately.
    """
    if v1_cap_total is not None:
        budget = per_bid_fraction * v1_cap_total
    else:
        budget = fallback_usd
    return max(1, int(budget // target_price))


def resolve_v1_cap_and_cash(
    *,
    cash_usd: float,
    pos_usd: float,
    bankroll_fraction: float,
    v1_filled_exposure: float,
) -> tuple[float, float]:
    """Return (v1_cap_total, effective_cash_usd) for the live loop.

    v1_cap_total = bankroll_fraction * (cash + open-positions notional). Per-bid
    sizing (v1_per_bid_contracts) scales off this, so each bid tracks the live
    balance on deposits/withdrawals (the 2026-05-30 council design). The cap is
    computed for EVERY fraction, INCLUDING 1.0: v1 is the only bot since v14 was
    removed (2026-06-01), so its slice is the whole bankroll.

    BUGFIX (research/v20): previously the cap was only computed for a partial
    slice (bankroll_fraction < 1.0). When v1 went to 1.0 the cap stayed None and
    per-bid sizing silently fell back to the fixed LIVE_PER_TRADE_USD, pinning
    every order to 1 contract regardless of V1_PER_BID_FRACTION.

    The effective-cash RESTRICTION (do not let v1 spend more than its slice
    minus what it already holds) applies only to a PARTIAL slice. At
    fraction == 1.0 v1 may use all cash, so effective_cash == cash_usd and the
    budget gate is unchanged from the prior 100%-bankroll path.
    """
    total_bankroll = cash_usd + pos_usd
    v1_cap_total = bankroll_fraction * total_bankroll
    if bankroll_fraction < 1.0:
        v1_headroom_for_new = max(0.0, v1_cap_total - v1_filled_exposure)
        return v1_cap_total, min(cash_usd, v1_headroom_for_new)
    return v1_cap_total, cash_usd


def event_identity(ticker: str, event_ticker: str) -> str:
    """Stable event-level identity for dedup.

    Prefer the explicit event_ticker; fall back to the ticker minus its final
    outcome segment. Never returns the empty string for a non-empty ticker, so
    dedup never collapses every empty-event_ticker order onto one key.

    research/v20 C1: the allowlist prefixes are all head-to-head (2-outcome)
    markets. The two sibling outcome tickers of one event are the SAME
    directional bet (YES on the favorite == NO on the underdog), so the
    NO-underdog arm would otherwise rest a bid on BOTH and double the position
    on a single event. Deduping at the event level keeps it to one favorite bet
    per event.
    """
    if event_ticker:
        return event_ticker
    return ticker.rsplit("-", 1)[0] if "-" in ticker else ticker


def write_heartbeat() -> None:
    """Best-effort heartbeat file write for an external watchdog."""
    try:
        HEARTBEAT_PATH.parent.mkdir(parents=True, exist_ok=True)
        HEARTBEAT_PATH.write_text(datetime.now(UTC).isoformat(), encoding="utf-8")
    except OSError:
        log.warning("heartbeat_write_failed", path=str(HEARTBEAT_PATH))


def expected_net_edge_for_favorite(yes_price: float, *,
                                   empirical_yes_rate: float = 0.95) -> float:
    """Compatibility shim: delegates to favorite_maker.expected_net_edge.

    Kept for the existing tests that import this symbol. The Round 5
    critic flagged a 0.97-vs-0.95 inconsistency between this script and
    favorite_maker.py; this shim now uses 0.95 to match the module
    default. New code should call `favorite_maker.expected_net_edge`
    directly.
    """
    return expected_net_edge(yes_price, empirical_yes_rate=empirical_yes_rate)


def one_loop_favorite_paper(
    client: KalshiClient,
    scanner_cfg: ScannerConfig,
    om: PaperOrderManager,
    dd: DrawdownMonitor,
    *,
    contracts_per_fill: int,
    max_concurrent: int | str,
    min_net_edge: float,
    discord_url: str | None,
) -> None:
    """One scan + place + reconcile cycle for PAPER mode.

    max_concurrent may be either a positive int (fixed cap) or the
    literal 'auto' to re-derive from current bankroll each loop.
    """
    max_concurrent = _resolve_max_concurrent_paper(max_concurrent, om)
    bankroll = om.current_paper_bankroll()
    dd_action = dd.update(bankroll)
    if dd_action == DrawdownAction.HALT:
        log.error("drawdown_halt_paper", bankroll=bankroll)
        if discord_url:
            send_discord(
                discord_url,
                content=(
                    f"HALT favorite: dd "
                    f"{dd.state.current_drawdown_pct*100:.1f}%"
                ),
            )
        return
    if not dd.allowed_to_place_orders():
        log.warning("paused_for_drawdown_paper", action=dd_action.value)
        return

    candidates = scan(client, scanner_cfg)
    if not candidates:
        log.info("no_candidates_this_loop_favorite")
        return

    # Reconcile + settle on every market scanned (cheap).
    for _raw, snap in candidates:
        try:
            recent = list(client.paginate(
                "/markets/trades", item_key="trades", limit=100,
                ticker=snap.ticker, max_pages=2,
            ))
        except Exception as exc:
            log.warning("trades_fetch_failed", ticker=snap.ticker, error=str(exc))
            continue
        filled = om.reconcile_fills(snap.ticker, recent)
        for f in filled:
            if discord_url:
                send_discord(
                    discord_url,
                    content=(
                        f"PAPER FILL fav {f.ticker} "
                        f"YES {f.contracts}@{f.filled_price:.4f}"
                    ),
                )

    n_open = len(om.state.open_orders)
    slots_left = max(0, max_concurrent - n_open)
    if slots_left <= 0:
        return

    sized = max(1, int(contracts_per_fill * dd.position_size_multiplier()))
    # v5 Track A filter hook (W1+W2 follow-on; gated by two env flags):
    #   SHADOW_MODE_ENABLED=true  -> append decision to JSONL log; no
    #                                effect on v1 trades.
    #   LIVE_FILTER_ENABLED=true  -> SKIP this candidate when the filter
    #                                says fade. v1 behavior IS changed.
    # Both default off; both can be combined. Reset the per-loop
    # sportsbook-fetcher credit budget so the within-loop ceiling is
    # honored regardless of any previous loop's consumption.
    try:
        from kalshi_bot_v5.sportsbook_fetcher import reset_loop_budget
        reset_loop_budget()
    except Exception:
        pass
    from kalshi_bot.strategy.shadow_filter import (
        is_live_filter_enabled,
        shadow_evaluate,
    )
    _live_filter_on = is_live_filter_enabled()
    scored: list[tuple[float, MarketSnapshot, float]] = []
    for _raw, snap in candidates:
        target_price = snap.yes_bid
        # Run the v5 filter (logs if SHADOW_MODE_ENABLED). Catch every
        # Exception for v1-safety; shadow_evaluate already catches
        # internally but defense-in-depth keeps the contract explicit.
        _decision = None
        try:  # noqa: SIM105
            _decision = shadow_evaluate(snap, target_price)
        except Exception:  # noqa: BLE001
            pass
        # Active filter overlay: skip this candidate if BOTH
        # (a) LIVE_FILTER_ENABLED is set, AND
        # (b) the filter returned a decision with should_trade=False.
        # When the filter abstains (fetchers miss / no rule fires /
        # decision is None), v1 falls through to its normal eligibility
        # logic. This is the safe failure mode.
        if (
            _live_filter_on
            and _decision is not None
            and not _decision.should_trade
        ):
            log.info(
                "v5_filter_skip",
                ticker=snap.ticker,
                reason=getattr(_decision, "reason", "?"),
                fired_rules=list(getattr(_decision, "fired_rules", ())),
                kalshi_price=target_price,
                poly_mid=getattr(_decision, "poly_mid", None),
                sportsbook_implied=getattr(_decision, "sportsbook_implied", None),
            )
            continue
        if not is_eligible(target_price):
            continue
        net = expected_net_edge(target_price)
        if net < min_net_edge:
            continue
        scored.append((net, snap, target_price))

    scored.sort(key=lambda x: -x[0])
    n_placed = 0
    # Same slot-iteration fix as live mode: iterate full sorted list,
    # break after n_placed reaches slots_left. Slicing scored[:slots_left]
    # before the already_known check used to silently drop slots.
    for net, snap, target_price in scored:
        if n_placed >= slots_left:
            break
        if any(o.ticker == snap.ticker for o in om.state.open_orders.values()):
            continue
        order = om.place_paper_order(
            ticker=snap.ticker,
            series_ticker=snap.series_ticker,
            event_ticker=snap.event_ticker,
            side="yes",
            target_price=target_price,
            contracts=sized,
            expected_net_edge=net,
            recalibrated_prob=0.95,
            market_mid_at_placement=(snap.yes_bid + snap.yes_ask) / 2.0,
        )
        n_placed += 1
        log.info("paper_favorite_order_placed",
                 ticker=order.ticker, target_price=target_price,
                 expected_net_edge=net, contracts=sized)
    if n_placed > 0 and discord_url:
        send_discord(
            discord_url,
            content=f"PAPER FAV placed {n_placed}; bankroll ${bankroll:.2f}",
        )


def one_loop_favorite_live(
    client: KalshiClient,
    scanner_cfg: ScannerConfig,
    lm: LiveOrderManager,
    kt: KillTriggerMonitor,
    dd: DrawdownMonitor,
    *,
    per_trade_usd: float,
    max_concurrent: int | str,
    min_net_edge: float,
    discord_url: str | None,
    adverse_selection_cfg: AdverseSelectionConfig | None = None,
    enable_no_underdog: bool = False,
    band_sizing: bool = False,
    step_in_front_enabled: bool = False,
) -> None:
    """One scan + place + reconcile cycle for LIVE mode.

    enable_no_underdog (v18 finding 06): also maker-buy the NO side on
    underdog-framed markets (the favorite is the NO side). Default off preserves
    the classic YES-only behavior. band_sizing (v18 finding 02/04): weight each
    bid's contract count by the favorite-price band (LOW [0.70,0.86) larger,
    heavy smaller), via band_size_multiplier; default off.

    max_concurrent may be either a positive int (fixed cap) or the
    literal 'auto' to re-derive from (cash_balance + open_positions_
    notional) each loop. Auto resolves before any other gate check.
    """
    write_heartbeat()
    # Read LIVE Kalshi balance ONCE at the top of the loop so the Discord
    # heartbeat (sent in finally) always reflects current Kalshi truth,
    # not persisted-state bankroll. Pass cached values down into the
    # budget gate so the same numbers drive decisions and Discord.
    try:
        live_cash_usd, live_pos_usd = _read_kalshi_balance_and_positions(client)
    except Exception as exc:  # noqa: BLE001
        log.warning("loop_balance_read_failed", error=str(exc))
        live_cash_usd, live_pos_usd = None, None

    skip_counts: dict[str, int] = {}
    n_placed = 0
    # Sizing state, initialized before the heartbeat closure so it can read
    # them at any loop-exit point. v1_cap_total gets its live value in the
    # bankroll-fraction block below; stays None under no fraction cap.
    v1_cap_total: float | None = None
    v1_per_bid_fraction = float(os.environ.get("V1_PER_BID_FRACTION", "0.03"))

    def _emit_v1_heartbeat(reason: str) -> None:
        """Post a per-loop Discord heartbeat using LIVE Kalshi balance.

        Called from every loop-exit point so the operator always sees
        the bot's current state and the most recent decision summary.
        Safe-no-op if discord_url is falsy or the post fails.
        """
        if not discord_url:
            return
        try:
            extra = []
            # Running realized total restricted to bets placed at/after the
            # optional tally cutoff (research/v20); None = all-time.
            hb_pnl, _hb_w, _hb_l, _hb_v, _hb_n = lm.realized_summary_since(
                lm.state.tally_since_ts
            )
            extra.append(
                f"resting={len(lm.state.resting)} "
                f"filled={len(lm.state.filled)} "
                f"closed={len(lm.state.closed)} "
                f"realized_pnl_usd={hb_pnl:+.2f}"
            )
            # Fill-rate health metric (demoted from a kill; shown so it is
            # never hidden again) + dynamic per-bid sizing tracking the
            # operator's live bankroll.
            fr = kt.fill_rate()
            if fr is not None:
                extra.append(
                    f"fill_rate={fr:.0%} "
                    f"({kt.state.placement_filled_total}/"
                    f"{kt.state.placement_attempts_total}; metric only, no kill)"
                )
            if v1_cap_total is not None:
                per_bid = v1_per_bid_fraction * v1_cap_total
                extra.append(
                    f"per_bid=~${per_bid:.2f} "
                    f"({v1_per_bid_fraction:.0%} of ${v1_cap_total:.2f} v1 cap; "
                    f"scales with your balance)"
                )
            extra.append(f"loop_exit: {reason}")
            send_discord(
                discord_url,
                content=format_loop_heartbeat(
                    bot_name="v1",
                    cash_usd=live_cash_usd,
                    positions_usd=live_pos_usd,
                    placed=n_placed,
                    skip_counts=skip_counts,
                    extra_lines=extra,
                ),
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("v1_heartbeat_post_failed", error=str(exc))

    max_concurrent = _resolve_max_concurrent_live(max_concurrent, lm, client)
    log.info("max_concurrent_resolved", value=max_concurrent)

    # Auto-rebaseline on detected operator deposit OR withdrawal
    # (Kalshi total moved >= 20% from last seen in either direction).
    rebaseline_reason = _auto_rebaseline_bidirectional(lm, kt, dd, client, log)
    if rebaseline_reason and discord_url:
        send_discord(
            discord_url,
            content=(
                f"LIVE FAV auto-rebaseline ({rebaseline_reason}); "
                f"new starting_bankroll=${lm.state.starting_bankroll_usd:.2f}"
            ),
        )

    bankroll = lm.current_live_bankroll()
    dd_action = dd.update(bankroll)
    if dd_action in (
        DrawdownAction.HALT, DrawdownAction.KILL, DrawdownAction.PAUSE,
    ):
        log.error("drawdown_blocks_live", action=dd_action.value,
                  bankroll=bankroll)
        if discord_url:
            send_discord(
                discord_url,
                content=(
                    f"LIVE FAV drawdown {dd_action.value}: "
                    f"{dd.state.current_drawdown_pct*100:.1f}%"
                ),
            )

    if kt.state.tripped:
        log.error("kill_trigger_active", reason=kt.state.trip_reason,
                  detail=kt.state.trip_detail)
        # Still reconcile fills + settlements so state stays current; just
        # refuse new placements.

    # Reconcile resting intents (lost-ack recovery), then verify each
    # locally-resting order is still resting on Kalshi (catches external
    # cancellations and any missed fills), then poll fills and
    # settlements.
    lm.reconcile_intents()
    reconciled = lm.reconcile_resting()
    for r in reconciled:
        if r.status.value == "live_filled":
            kt.record_fill()
            log.info("live_resting_to_filled", intent_id=r.intent_id,
                     ticker=r.ticker)
            if discord_url:
                send_discord(
                    discord_url,
                    content=(
                        f"LIVE RECONCILED FILL {r.ticker} "
                        f"(detected via resting-order check)"
                    ),
                )
        else:
            log.info("live_resting_to_cancelled", intent_id=r.intent_id,
                     ticker=r.ticker)
    new_fills = lm.reconcile_fills()
    for fill in new_fills:
        kt.record_fill()
        log.info("live_fill_recorded", intent_id=fill.intent_id,
                 ticker=fill.ticker)
        if discord_url:
            price = (fill.filled_price_cents or 0) / 100.0
            send_discord(
                discord_url,
                content=(
                    f"LIVE FILL fav {fill.ticker} "
                    f"YES {fill.filled_count}@{price:.2f}"
                ),
            )
    settled = lm.reconcile_settlements()
    # 1) Kill-trigger recording: per-order, OUTSIDE any Discord try/except so
    #    a webhook failure can never skip a kill check. Voids
    #    (resolution_outcome == -1) are skipped: a refund-to-entry void is not
    #    a directional loss, and recording outcome -1 would drag the YES-rate
    #    trigger's sum negative (a false-kill hazard). The void's capital
    #    release + P&L are already booked by reconcile_settlements.
    kill_reason = None
    for s in settled:
        if s.resolution_outcome == -1:
            continue
        pnl_per_contract = (s.realized_pnl_usd or 0.0) / max(s.filled_count, 1)
        # The YES-rate kill trigger really measures "the favorite WON". For a
        # YES order the favorite won iff the market resolved YES (outcome 1); for
        # a NO order (v18 underdog arm) iff it resolved NO (outcome 0). Pass the
        # side-aware favorite_won so a winning NO order is not miscounted as a
        # loss (which would falsely drag the rate down). Identical to the old
        # behavior for YES orders (no regression).
        favorite_won = 1 if (
            (s.side == "yes" and s.resolution_outcome == 1)
            or (s.side == "no" and s.resolution_outcome == 0)
        ) else 0
        r = kt.record_settlement(
            pnl_per_contract=pnl_per_contract,
            outcome=favorite_won,
            settle_ts=s.resolution_ts or datetime.now(UTC).isoformat(),
        )
        if r is not None:
            kill_reason = r
    # 2) Discord: ONE message per settle pass, not one per order (the first
    #    loop after a settlement fix back-settles many at once). Voids tallied
    #    separately so winners + losers + voids == count.
    if settled and discord_url:
        try:
            def _wlv(orders: list) -> tuple[int, int, int]:
                # SIDE-AWARE win/loss (matches the kill's favorite_won and
                # LiveOrderManager.realized_summary_since): a bet wins iff the
                # side we bought won (YES bet -> outcome 1, NO bet -> outcome 0),
                # so the NO-underdog arm is not inverted. Voids are -1; W + L + V
                # == count (every settled order resolves 1/0/-1).
                w = sum(
                    1 for o in orders
                    if (o.side == "yes" and o.resolution_outcome == 1)
                    or (o.side == "no" and o.resolution_outcome == 0)
                )
                v = sum(1 for o in orders if o.resolution_outcome == -1)
                lo = sum(1 for o in orders if o.resolution_outcome in (0, 1)) - w
                return w, lo, v

            # Running tally for the display, restricted to bets PLACED at/after
            # the optional cutoff (research/v20 tally reset) so a strategy or
            # universe change can be judged without old bets. None = all-time.
            tally_pnl, winners, losers, voids, tally_count = (
                lm.realized_summary_since(lm.state.tally_since_ts)
            )
            tally_label = "since reset" if lm.state.tally_since_ts else "all-time"
            if len(settled) == 1:
                s = settled[0]
                send_discord(
                    discord_url,
                    content=format_settlement_alert(
                        bot_name="v1",
                        ticker=s.ticker,
                        outcome=s.resolution_outcome,
                        realized_pnl_usd=float(s.realized_pnl_usd or 0.0),
                        filled_count=int(s.filled_count or 0),
                        entry_price=(
                            (s.filled_price_cents or 0) / 100.0
                            if s.filled_price_cents else None
                        ),
                        cumulative_pnl_usd=float(tally_pnl),
                        settled_count=tally_count,
                        winners=winners,
                        losers=losers,
                        side=s.side,
                    ),
                )
            else:
                res_label = {1: "YES", 0: "NO", -1: "VOID"}
                batch_pnl = sum(float(s.realized_pnl_usd or 0.0) for s in settled)
                b_w, b_l, b_v = _wlv(settled)
                lines = [
                    f"v1 SETTLED {len(settled)} orders (batch back-settle): "
                    f"{b_w}W / {b_l}L / {b_v}V",
                    f"batch P&L ${batch_pnl:+.2f}; realized total "
                    f"${tally_pnl:+.2f} "
                    f"({winners}W/{losers}L/{voids}V of {tally_count} {tally_label})",
                ]
                for s in settled[:10]:
                    res = res_label.get(s.resolution_outcome, "?")
                    lines.append(
                        f"  {s.ticker} {res} {s.filled_count}c @ "
                        f"${(s.filled_price_cents or 0) / 100:.2f} -> "
                        f"${float(s.realized_pnl_usd or 0):+.2f}"
                    )
                send_discord(discord_url, content="\n".join(lines))
        except Exception as exc:  # noqa: BLE001
            log.warning("v1_settlement_alert_failed", error=str(exc))
    if kill_reason and discord_url:
        send_discord(
            discord_url,
            content=(
                f"KILL TRIGGER tripped: {kill_reason.value} "
                f"({kt.state.trip_detail})"
            ),
        )

    # Stuck-position detection (alert-only): a long-horizon position past its
    # own close_time that never reached a terminal status. v1 does NOT
    # auto-void (operator-tracked season-long bets); it flags once for review.
    # Runs every loop, even when killed, so detection stays current.
    try:
        stuck = lm.flag_stuck_past_close(
            min_hours_past_close=float(
                os.environ.get("V1_STUCK_HOURS_PAST_CLOSE", "48")
            ),
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("v1_stuck_flag_failed", error=str(exc))
        stuck = []
    for o in stuck:
        locked = (o.filled_price_cents or 0) * (o.filled_count or 0) / 100.0
        log.warning("v1_stuck_position", ticker=o.ticker, locked_usd=locked)
        if discord_url:
            send_discord(
                discord_url,
                content=(
                    f"v1 STUCK POSITION {o.ticker}: past its close date and "
                    f"not resolved on Kalshi. ${locked:.2f} held. v1 is NOT "
                    f"auto-voiding; check the market and reconcile manually. "
                    f"(One-time alert.)"
                ),
            )

    # Order maintenance runs EVERY loop, even when KILLED. Cancelling
    # unfilled resting bids carries no position and locks no cash, so it is
    # always safe and risk-reducing; a killed bot should keep its book clean
    # rather than freeze. Only NEW PLACEMENT (further below) is gated by the
    # kill / drawdown state. Diagnosed 2026-05-30: a tripped fill-rate kill
    # early-returned BEFORE these sweeps, so overnight v1 placed nothing AND
    # cancelled nothing.

    # 1. Cancel resting bids on now-denylisted series (no longer traded).
    try:
        cancelled_deny = lm.cancel_resting_by_series(scanner_cfg.series_denylist)
        if cancelled_deny and discord_url:
            send_discord(
                discord_url,
                content=(
                    f"LIVE FAV denylist sweep: cancelled {len(cancelled_deny)} "
                    f"resting bids on denylisted series"
                ),
            )
    except Exception as exc:  # noqa: BLE001
        log.warning("denylist_sweep_failed", error=str(exc))

    # 2. Stale-bid sweep: cancel maker bids that have been sitting on the
    # book longer than the configured TTL (default 5 days). Kalshi does NOT
    # lock cash on resting maker bids, so unfilled bids would otherwise
    # accumulate against the bot's local budget. Failures are non-fatal.
    try:
        ttl_hours = float(os.environ.get("STALE_BID_TTL_HOURS", "120"))
        if ttl_hours > 0:
            cancelled_stale = lm.cancel_stale_resting(max_age_hours=ttl_hours)
            if cancelled_stale and discord_url:
                send_discord(
                    discord_url,
                    content=(
                        f"LIVE FAV stale-bid sweep: cancelled "
                        f"{len(cancelled_stale)} bids older than "
                        f"{ttl_hours:.0f}h"
                    ),
                )
    except Exception as exc:  # noqa: BLE001
        log.warning("stale_bid_sweep_failed", error=str(exc))

    # 3. Adverse-selection cancel-on-drift (opt-in via --cancel-on-drift):
    # cancel resting bids whose market has drifted materially since placement.
    if adverse_selection_cfg is not None:
        try:
            cancelled_drift = lm.reconcile_adverse_selection(
                config=adverse_selection_cfg,
            )
            if cancelled_drift and discord_url:
                send_discord(
                    discord_url,
                    content=(
                        f"LIVE FAV cancel-on-drift: cancelled "
                        f"{len(cancelled_drift)} bids; threshold "
                        f"{adverse_selection_cfg.drift_against_bid_cents:.1f}c, "
                        f"min_age "
                        f"{adverse_selection_cfg.min_order_age_minutes}m"
                    ),
                )
        except Exception as exc:  # noqa: BLE001
            log.warning("adverse_selection_sweep_failed", error=str(exc))

    # NEW PLACEMENT is gated by the hard kill, the auto-recovering soft pause,
    # or the drawdown state (maintenance above already ran). The soft pause is
    # re-evaluated every loop and clears itself when the edge recovers, so a
    # transient unlucky cluster never leaves the bot halted awaiting a manual
    # reset (the recurring 2026-06-13 / 06-15 false halts).
    was_soft_paused = kt.state.soft_paused
    soft_pause_reason = kt.evaluate_soft_pause()
    if discord_url and kt.state.soft_paused != was_soft_paused:
        if kt.state.soft_paused:
            send_discord(
                discord_url,
                content=(
                    f"LIVE FAV SOFT-PAUSE: {soft_pause_reason}. New placement "
                    f"paused; maintenance + cancels keep running. AUTO-RESUMES "
                    f"when the trailing-30 edge recovers. No manual reset needed."
                ),
            )
        else:
            send_discord(
                discord_url,
                content=(
                    "LIVE FAV soft-pause CLEARED: trailing-30 edge recovered; "
                    "new placement resumed automatically."
                ),
            )
    if (
        kt.state.tripped
        or soft_pause_reason is not None
        or not dd.allowed_to_place_orders()
    ):
        if kt.state.tripped:
            hb = "kill_or_drawdown"
        elif soft_pause_reason is not None:
            hb = "soft_pause_edge_compression"
        else:
            hb = "drawdown_pause"
        _emit_v1_heartbeat(hb)
        return

    candidates = scan(client, scanner_cfg)
    if not candidates:
        log.info("no_candidates_this_loop_live")
        _emit_v1_heartbeat("no_candidates")
        return

    n_open = lm.open_order_count()
    slots_left = max(0, max_concurrent - n_open)
    if slots_left <= 0:
        skip_counts["all_slots_full"] = n_open
        _emit_v1_heartbeat(f"slots_full(open={n_open}, cap={max_concurrent})")
        return

    # Budget check setup: re-use the live Kalshi balance read at the top
    # of the loop. On the top-of-loop read failure we fall back to the
    # local LiveOrderManager bankroll (the safer half: we'd rather skip
    # a loop than over-commit).
    if live_cash_usd is not None and live_pos_usd is not None:
        cash_usd, pos_usd = live_cash_usd, live_pos_usd
    else:
        cash_usd = lm.current_live_bankroll()
        pos_usd = 0.0
    current_resting_exposure = lm.total_resting_exposure_usd()

    # Dynamic 60/40 split: if --bankroll-fraction is set (< 1.0), cap
    # v1's spendable cash at fraction * (cash + positions) minus v1's
    # already-deployed filled exposure. Resting exposure is enforced
    # naturally via the budget gate (current_resting + new_order > cap).
    bankroll_fraction = float(os.environ.get("V1_BANKROLL_FRACTION", "1.0"))
    # v1's live bankroll slice, recomputed each loop so per-bid sizing
    # auto-scales on deposits/withdrawals (2026-05-30 council). Computed for
    # EVERY fraction including 1.0 (v1 is the only bot since v14 was removed).
    # research/v20: a 1.0 fraction previously left v1_cap_total None, so per-bid
    # sizing fell back to the fixed LIVE_PER_TRADE_USD and pinned every order to
    # 1 contract regardless of V1_PER_BID_FRACTION. The effective-cash
    # restriction only applies for a partial slice; at 1.0 the budget gate uses
    # full cash, so its behavior is unchanged.
    total_bankroll = cash_usd + pos_usd
    v1_filled_exposure = _compute_v1_filled_exposure(lm)
    v1_cap_total, effective_cash_usd = resolve_v1_cap_and_cash(
        cash_usd=cash_usd,
        pos_usd=pos_usd,
        bankroll_fraction=bankroll_fraction,
        v1_filled_exposure=v1_filled_exposure,
    )
    log.info(
        "v1_bankroll_fraction_cap",
        fraction=bankroll_fraction,
        total_bankroll=round(total_bankroll, 2),
        v1_cap_total=round(v1_cap_total, 2),
        v1_filled_exposure=round(v1_filled_exposure, 2),
        actual_kalshi_cash=round(cash_usd, 2),
        effective_cash=round(effective_cash_usd, 2),
    )
    cash_usd = effective_cash_usd

    log.info(
        "budget_snapshot",
        cash_usd=round(cash_usd, 2),
        resting_exposure_usd=round(current_resting_exposure, 2),
        headroom_usd=round(cash_usd - current_resting_exposure, 2),
    )

    # Shadow-mode v5 filter logging (W1+W2 follow-on; opt-in via
    # SHADOW_MODE_ENABLED env). DOES NOT affect v1's trade decision;
    # logs only. Reset the per-loop sportsbook-fetcher credit budget so
    # the within-loop ceiling is honored regardless of any previous
    # loop's consumption.
    try:
        from kalshi_bot_v5.sportsbook_fetcher import reset_loop_budget
        reset_loop_budget()
    except Exception:
        pass
    from kalshi_bot.strategy.shadow_filter import (
        is_live_filter_enabled,
        shadow_evaluate,
    )
    _live_filter_on = is_live_filter_enabled()
    step_tick = float(os.environ.get("V1_STEP_TICK_CENTS", "1")) / 100.0
    band_m_low = float(os.environ.get("V1_BAND_M_LOW", "1.3"))
    band_m_high = float(os.environ.get("V1_BAND_M_HIGH", "0.8"))
    scored: list[tuple[float, MarketSnapshot, FavoriteSideDecision]] = []
    for _raw, snap in candidates:
        # Decide which SIDE is the favorite and the executable maker bid for it.
        # YES-favorite: rest a YES bid at yes_bid. NO-favorite (underdog-framed):
        # rest a NO bid at no_bid = 1 - yes_ask (v18 finding 06). The NO arm is
        # only honored when enable_no_underdog is set; otherwise NO-side
        # decisions are skipped, preserving the classic YES-only v1.
        fav = decide_favorite_side(snap.yes_bid, snap.yes_ask)
        if fav is None:
            skip_counts["price_band"] = skip_counts.get("price_band", 0) + 1
            continue
        if fav.side == "no" and not enable_no_underdog:
            skip_counts["no_arm_disabled"] = skip_counts.get("no_arm_disabled", 0) + 1
            continue
        # The v5 fade filter is a YES-favorite overlay; apply to YES side only.
        if fav.side == "yes":
            _decision = None
            try:  # noqa: SIM105
                _decision = shadow_evaluate(snap, fav.target_price)
            except Exception:  # noqa: BLE001
                pass
            if (
                _live_filter_on
                and _decision is not None
                and not _decision.should_trade
            ):
                log.info(
                    "v5_filter_skip_live",
                    ticker=snap.ticker,
                    reason=getattr(_decision, "reason", "?"),
                    fired_rules=list(getattr(_decision, "fired_rules", ())),
                    kalshi_price=fav.target_price,
                    poly_mid=getattr(_decision, "poly_mid", None),
                    sportsbook_implied=getattr(_decision, "sportsbook_implied", None),
                )
                skip_counts["v5_filter"] = skip_counts.get("v5_filter", 0) + 1
                continue
        # Step one tick IN FRONT of the best bid so v1 is the best bid and
        # sellers fill it first (fill-rate boost). Stays a maker (capped below
        # the ask) and re-checks the edge; falls back to the best bid if there
        # is no room or the stepped edge drops below min_net_edge.
        if step_in_front_enabled:
            fav = step_in_front(fav, tick=step_tick, min_net_edge=min_net_edge)
        if fav.expected_net_edge < min_net_edge:
            skip_counts["low_edge"] = skip_counts.get("low_edge", 0) + 1
            continue
        scored.append((fav.expected_net_edge, snap, fav))

    scored.sort(key=lambda x: -x[0])
    # Iterate the full sorted list; break once we have placed slots_left
    # new orders. Previously sliced scored[:slots_left] BEFORE the
    # already_known check, which silently dropped slots when the top
    # candidates were already on the book.
    for net, snap, fav in scored:
        if n_placed >= slots_left:
            break
        # Dedup at the EVENT level, not just the exact ticker: for head-to-head
        # markets (all allowlist prefixes) the two sibling outcome tickers are
        # the same directional bet, so the NO-underdog arm would otherwise hold
        # both and double the position on one event (research/v20 C1). One
        # favorite bet per event.
        snap_event = event_identity(snap.ticker, snap.event_ticker)
        already_known = any(
            event_identity(o.ticker, o.event_ticker) == snap_event
            for bucket in (lm.state.resting, lm.state.filled, lm.state.intents)
            for o in bucket.values()
        )
        if already_known:
            skip_counts["dedup"] = skip_counts.get("dedup", 0) + 1
            continue
        # Dynamic per-bid budget (2026-05-30 council): scale each bid with the
        # live bankroll like v14. Base on v1_cap_total (v1's full bankroll slice
        # at fraction 1.0, derived from the live balance), NOT the headroom-
        # shrunk cash_usd, so we never double-cap; the budget gate below still
        # caps AGGREGATE resting exposure. Priced on the bid's OWN side (yes_bid
        # for a yes bid, no_bid for a no bid).
        #
        # v18 return-on-stake band sizing: weight the bid by the favorite-price
        # band (LOW [0.70,0.86) larger, heavy smaller). research/v20 H2: fold
        # the multiplier into the budget BEFORE the floor-divide, so it actually
        # changes the contract count; applying it after the floor (round(n*mult))
        # was inert at small bankroll where n is 1. floor 1 keeps a valid bid.
        effective_fraction = v1_per_bid_fraction
        if band_sizing:
            effective_fraction *= band_size_multiplier(
                fav.fav_price, m_low=band_m_low, m_high=band_m_high
            )
        contracts = v1_per_bid_contracts(
            fav.target_price,
            v1_cap_total=v1_cap_total,
            per_bid_fraction=effective_fraction,
            fallback_usd=per_trade_usd,
        )
        # Budget gate: total resting exposure (this order + everything
        # already on the book) must not exceed live Kalshi cash. If
        # every resting bid filled, we need cash to cover them. Kalshi
        # does not enforce this for maker bids; we do.
        new_order_cost = fav.target_price * contracts
        projected_exposure = current_resting_exposure + new_order_cost
        if projected_exposure > cash_usd:
            log.info(
                "skip_budget_exhausted",
                ticker=snap.ticker,
                new_order_cost=round(new_order_cost, 2),
                current_resting_exposure=round(current_resting_exposure, 2),
                projected_exposure=round(projected_exposure, 2),
                cash_usd=round(cash_usd, 2),
            )
            skip_counts["budget"] = skip_counts.get("budget", 0) + 1
            continue
        kt.record_attempt()
        # Side-appropriate mid for diagnostics: NO mid = 1 - yes mid.
        yes_mid = (snap.yes_bid + snap.yes_ask) / 2.0
        order = lm.place_live_order(
            ticker=snap.ticker,
            series_ticker=snap.series_ticker,
            event_ticker=snap.event_ticker,
            target_price=fav.target_price,
            contracts=contracts,
            expected_net_edge=net,
            market_mid_at_placement=(yes_mid if fav.side == "yes" else 1.0 - yes_mid),
            side=fav.side,
        )
        current_resting_exposure = projected_exposure
        n_placed += 1
        log.info("live_favorite_order_placed",
                 intent_id=order.intent_id, status=order.status.value,
                 ticker=order.ticker, side=fav.side,
                 target_price=fav.target_price, fav_price=fav.fav_price,
                 contracts=contracts)
    _emit_v1_heartbeat(
        f"loop_end (n_placed={n_placed}, candidates={len(candidates)})"
    )


def _install_signal_handlers(
    lm: LiveOrderManager | None, discord_url: str | None,
) -> None:
    """SIGINT/SIGTERM handler: best-effort cancel-all of live resting
    orders, release single-instance lock, then exit. Paper mode also
    installs a no-op handler so the bot exits cleanly on Ctrl-C.
    """
    def _handler(signum, _frame) -> None:  # noqa: ANN001
        log.warning("signal_received", signum=signum)
        if lm is not None:
            try:
                cancelled = lm.cancel_all_resting()
                log.info("live_cancel_on_exit", cancelled=len(cancelled))
                if discord_url:
                    send_discord(
                        discord_url,
                        content=(
                            f"LIVE FAV exiting; cancelled {len(cancelled)} "
                            "resting orders"
                        ),
                    )
            except Exception as exc:
                log.error("cancel_on_exit_failed", error=str(exc))
        # Release single-instance lock so the next bot can launch.
        # Only releases if we own the lock; safe to call always.
        try:
            from kalshi_bot.strategy.single_instance import release_live_lock
            release_live_lock()
        except Exception:
            pass
        sys.exit(0)

    signal.signal(signal.SIGINT, _handler)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _handler)


def _confirm_live(bankroll: float, per_trade: float) -> bool:
    expected = (
        f"I authorize live trading at ${bankroll:.2f} bankroll, "
        f"${per_trade:.2f}/trade"
    )
    print(f"\nType exactly the following line to proceed with LIVE mode:\n  {expected}")
    answer = sys.stdin.readline().rstrip("\n")
    return answer == expected


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode", choices=["paper", "live", "live-demo"], default="paper",
        help="Execution mode. paper (default) simulates fills against the "
             "trade tape. live posts real Kalshi orders (requires "
             "LIVE_ENABLED=true). live-demo posts to the demo URL.",
    )
    parser.add_argument("--cadence", type=int, default=900,
                        help="Seconds between loops. Default 900 = 15 min.")
    parser.add_argument(
        "--max-concurrent", type=_parse_max_concurrent_arg, default=5,
        help="Concurrent positions cap. Pass a positive integer for a "
             "fixed cap, or 'auto' to derive each loop from "
             "(cash_balance + open_positions_notional) / "
             "FAVORITE_UPPER_CAP. Default 5.",
    )
    parser.add_argument("--contracts-per-fill", type=int, default=1,
                        help="Paper mode only.")
    parser.add_argument("--min-net-edge", type=float, default=0.02,
                        help="Minimum predicted net edge per contract.")
    parser.add_argument(
        "--starting-bankroll", type=_parse_starting_bankroll_arg, default="auto",
        help="Starting bankroll. 'auto' (default) reads Kalshi cash + "
             "open positions value at startup and persists to state. "
             "Explicit numeric value overrides. State persists across "
             "restarts so drawdown calc stays meaningful; use "
             "--rebaseline to force re-read after deposits/withdrawals.",
    )
    parser.add_argument(
        "--rebaseline", action="store_true",
        help="Force re-reading the starting bankroll from Kalshi balance, "
             "overwriting any persisted value in state.json. Use after "
             "depositing or withdrawing funds.",
    )
    # Default 0 (was 30, recalibrated 2026-06-02). The validated v18 edge is on
    # GAME-RESULT markets (KXMLBGAME, ATP/WTA matches), which open only days
    # before the event so their open-to-close lifetime is ~6 to 16 days. A 30d
    # floor EXCLUDED every one of them and left v1 resting bids only on
    # long-lifetime season FUTURES (e.g. Sept NFL games, lifetime ~120d) that
    # have no live trading until close to the event, which is the root cause of
    # v1's near-zero fill rate. See research/v19/03-fill-rate-diagnosis.md.
    parser.add_argument("--min-lifetime-days", type=int, default=0)
    parser.add_argument(
        "--max-lifetime-days", type=int, default=180,
        help="Upper bound on market lifetime (open_time to close_time) in "
             "days. Default 180 per research/time-scale-analysis.md: edge "
             "is clean and capital-efficient at sub-180d, noisy and "
             "fat-tailed above. Pass 0 to disable the cap.",
    )
    parser.add_argument("--once", action="store_true",
                        help="Run a single loop and exit (for testing).")
    parser.add_argument(
        "--yes-i-authorize", action="store_true",
        help="Bypass the interactive operator-confirmation prompt for "
             "background invocations. Pre-flight + LIVE_ENABLED gate "
             "still apply. Use only when starting the bot in a "
             "non-interactive session.",
    )
    parser.add_argument(
        "--log-file", type=str, default=None,
        help="Optional path for daily-rotating log file. Defaults to "
             "data/live_trades/logs/live.log in LIVE/LIVE-DEMO mode and "
             "no file logging in PAPER mode.",
    )
    # Round 15b safety filters. Default OFF to preserve existing live
    # behavior. Operator opts in once the new behavior is validated.
    parser.add_argument(
        "--allowlist", action="store_true",
        help="Restrict scanner to PERSIST_SERIES_ALLOWLIST (the 5 prefixes "
             "with Round 15b train+OOS cluster-bootstrap-validated edge: "
             "KXMLBGAME, KXATPMATCH, KXNFLGAME, KXNCAAFGAME, KXWTAMATCH). "
             "See research/v10a/TEST-AND-CONFIRM.md.",
    )
    parser.add_argument(
        "--expanded-denylist", action="store_true",
        help="Use EXPANDED_SERIES_DENYLIST (adds 12 OOS_NULL prefixes "
             "from Round 15b Becker validation: NFL/MLB/NHL/NCAA "
             "spreads/totals/wins plus EPL/UCL game lines).",
    )
    parser.add_argument(
        "--min-minutes-to-close", type=int, default=0,
        help="Pre-close cutoff in minutes. Markets closing sooner are "
             "skipped to avoid the adverse-selection window where MMs "
             "tighten quotes and orderflow becomes information-rich. "
             "Default 0 disables the filter. Recommended: 60 per the "
             "Round 15b live observation of -4.93pp mean post-fill mid "
             "drift on 15 still-open v1 fills.",
    )
    # Round 15c cancel-on-drift wiring. Default off; opt-in flag turns on
    # the adverse_selection_monitor reconcile call inside the live loop.
    # When enabled, the bot pulls the live orderbook mid for each resting
    # ticker and cancels orders whose mid has drifted past the threshold.
    # Live mode only (paper mode does not place real orders to cancel).
    parser.add_argument(
        "--cancel-on-drift", action="store_true",
        help="LIVE only. Enable adverse-selection cancel-on-drift sweep "
             "each loop. Pulls the live orderbook mid for every resting "
             "order and cancels orders whose mid has drifted by more "
             "than --drift-threshold-cents AGAINST the resting bid. Off "
             "by default. See research/v10a/18-cancel-on-drift-wiring.md.",
    )
    parser.add_argument(
        "--drift-threshold-cents", type=float, default=3.0,
        help="Cents of adverse drift required to cancel a resting order. "
             "Default 3 per Becker post-fill drift distribution "
             "(95th percentile of acceptable drift). Used only when "
             "--cancel-on-drift is set.",
    )
    parser.add_argument(
        "--drift-min-age-minutes", type=int, default=15,
        help="Minimum order age in minutes before drift-based cancellation "
             "activates. Default 15 (a freshly placed order may briefly "
             "see drift that bounces back). Used only when "
             "--cancel-on-drift is set.",
    )
    # v18 (2026-06-01) edge enhancements. Default OFF so the classic
    # YES-favorite v1 behavior is unchanged until the operator opts in.
    parser.add_argument(
        "--enable-no-underdog", action="store_true",
        help="Also maker-buy the NO side on underdog-framed markets (the "
             "favorite is the NO side). v18 finding 06: the favorite-longshot "
             "bias is symmetric, so buying NO on moderate underdogs (no_px in "
             "[0.70,0.86)) earns the same edge v1 gets on favorites, on markets "
             "v1 currently skips. Roughly doubles the eligible universe. Also "
             "widens the scanner band to pass underdog markets.",
    )
    parser.add_argument(
        "--band-sizing", action="store_true",
        help="Weight each bid's contract count by the favorite-price band "
             "(LOW [0.70,0.86) larger, heavy [0.86,0.95] smaller) per v18 "
             "findings 02/04. Multipliers env-tunable: V1_BAND_M_LOW (1.3), "
             "V1_BAND_M_HIGH (0.8). Off by default.",
    )
    parser.add_argument(
        "--step-in-front", action="store_true",
        help="Rest each maker bid one tick IN FRONT of the best bid (become the "
             "best bid so sellers fill v1 first), capped below the ask so it "
             "stays a maker and re-checked for edge. Trades ~1c of the +5-8%% "
             "edge for a large fill-rate gain. Tick env-tunable: "
             "V1_STEP_TICK_CENTS (1). Off by default. See research/v19/03.",
    )
    args = parser.parse_args()

    if args.log_file is not None:
        log_file_path: Path | None = Path(args.log_file)
    elif args.mode in ("live", "live-demo"):
        log_file_path = Path("data/live_trades/logs/live.log")
    else:
        log_file_path = None
    configure_logging(log_file=log_file_path)
    log_main = structlog.get_logger("paper_trade_favorite")
    settings = load_settings()
    discord_url = settings.DISCORD_WEBHOOK_URL or None

    om = PaperOrderManager()
    # Resolve --starting-bankroll for paper mode. Live-mode resolution
    # is deferred until we have a KalshiClient (so 'auto' can read
    # /portfolio/balance). For paper, no live read is appropriate.
    paper_starting = _resolve_starting_bankroll_paper(
        args.starting_bankroll, om, rebaseline=args.rebaseline,
    )
    if om.state.starting_bankroll_usd != paper_starting:
        om.state.starting_bankroll_usd = paper_starting

    max_lifetime = args.max_lifetime_days if args.max_lifetime_days > 0 else None
    series_denylist = (
        EXPANDED_SERIES_DENYLIST if args.expanded_denylist else DEFAULT_SERIES_DENYLIST
    )
    series_allowlist = PERSIST_SERIES_ALLOWLIST if args.allowlist else None
    min_minutes_to_close = (
        args.min_minutes_to_close if args.min_minutes_to_close > 0 else None
    )
    # Scanner mid bands. Classic v1: only favorite-framed markets (mid in
    # [0.70,0.95]). With --enable-no-underdog, also pass underdog-framed markets
    # (mid in [0.05,0.30], where the favorite is the NO side); the strategy then
    # picks the favorite side per market. The dead zone (0.30,0.70) stays
    # excluded (no clear favorite).
    if args.enable_no_underdog:
        mid_band_lower = (0.05, 0.30)
        mid_band_upper = (0.70, 0.95)
    else:
        mid_band_lower = (0.70, 0.95)
        mid_band_upper = (0.70, 0.95)
    scanner_cfg = ScannerConfig(
        category="Sports",
        min_lifetime_days=args.min_lifetime_days,
        max_lifetime_days=max_lifetime,
        mid_band_lower=mid_band_lower,
        mid_band_upper=mid_band_upper,
        series_denylist=series_denylist,
        series_allowlist=series_allowlist,
        min_minutes_to_close=min_minutes_to_close,
    )
    log_main_init = structlog.get_logger("paper_trade_favorite")
    log_main_init.info(
        "scanner_config_round_15b",
        allowlist_enabled=args.allowlist,
        allowlist_size=len(series_allowlist) if series_allowlist else 0,
        expanded_denylist=args.expanded_denylist,
        denylist_size=len(series_denylist),
        min_minutes_to_close=min_minutes_to_close,
    )

    adverse_selection_cfg: AdverseSelectionConfig | None = None
    if args.cancel_on_drift:
        adverse_selection_cfg = AdverseSelectionConfig(
            drift_against_bid_cents=float(args.drift_threshold_cents),
            drift_against_ask_cents=float(args.drift_threshold_cents),
            min_order_age_minutes=int(args.drift_min_age_minutes),
        )
        log_main_init.info(
            "cancel_on_drift_enabled",
            drift_threshold_cents=adverse_selection_cfg.drift_against_bid_cents,
            min_order_age_minutes=adverse_selection_cfg.min_order_age_minutes,
        )

    if args.mode == "paper":
        dd = DrawdownMonitor(starting_bankroll_usd=om.current_paper_bankroll())
        _install_signal_handlers(None, discord_url)
        if args.once:
            with KalshiClient(settings) as client:
                one_loop_favorite_paper(
                    client, scanner_cfg, om, dd,
                    contracts_per_fill=args.contracts_per_fill,
                    max_concurrent=args.max_concurrent,
                    min_net_edge=args.min_net_edge,
                    discord_url=discord_url,
                )
            return 0
        if discord_url:
            send_discord(
                discord_url,
                content=(
                    f"PAPER FAVORITE STARTED cadence={args.cadence}s "
                    f"max_concurrent={args.max_concurrent}"
                ),
            )
        with KalshiClient(settings) as client:
            while True:
                try:
                    one_loop_favorite_paper(
                        client, scanner_cfg, om, dd,
                        contracts_per_fill=args.contracts_per_fill,
                        max_concurrent=args.max_concurrent,
                        min_net_edge=args.min_net_edge,
                        discord_url=discord_url,
                    )
                except Exception as exc:
                    log_main.error("paper_loop_failed", error=str(exc))
                    if discord_url:
                        send_discord(
                            discord_url,
                            content=f"PAPER FAV LOOP FAILED: {exc!s}",
                        )
                time.sleep(args.cadence)
        return 0

    # LIVE or LIVE-DEMO path.
    expected_env = "prod" if args.mode == "live" else "demo"
    skip_balance = args.mode == "live-demo"
    skip_acceptance = args.mode == "live-demo"

    # SINGLE-INSTANCE LOCK: refuse to launch if another bot process is
    # alive. This is the last line of defense against the supervisor-
    # spawns-twice bug. raises SystemExit with a clear message if a
    # live PID is found in data/live_trades/bot.pid.
    from kalshi_bot.strategy.single_instance import (
        acquire_live_lock,
        release_live_lock,
    )
    acquire_live_lock()

    with KalshiClient(settings) as client:
        # intent_id_prefix '11' tags every v1-placed order's client_order_id
        # with '11' as the first 2 hex chars. Operator can identify v1
        # ownership purely from the Kalshi order_id, even with no state.json.
        lm = LiveOrderManager(client=client, intent_id_prefix="11")
        # Resolve --starting-bankroll for live/live-demo mode. 'auto'
        # reads Kalshi cash + open positions value (unless state already
        # has a persisted value and --rebaseline was not passed).
        live_starting = _resolve_starting_bankroll_live(
            args.starting_bankroll, lm, client,
            rebaseline=args.rebaseline, log_main=log_main,
        )
        if lm.state.starting_bankroll_usd != live_starting:
            lm.state.starting_bankroll_usd = live_starting
        log_main.info(
            "live_starting_bankroll_resolved",
            value=live_starting,
            source=("explicit" if args.starting_bankroll != STARTING_BANKROLL_AUTO else "auto"),
            rebaseline=args.rebaseline,
        )
        kt_cfg = KillTriggerConfig(
            yes_rate_min=settings.KILL_YES_RATE_MIN,
            yes_rate_window=settings.KILL_YES_RATE_WINDOW,
            rolling_mean_window=settings.KILL_ROLLING_MEAN_WINDOW,
            rolling_mean_days_negative=settings.KILL_ROLLING_MEAN_DAYS_NEGATIVE,
            rolling_30_mean_pp_min=settings.KILL_ROLLING_30_MEAN_PP_MIN,
            rolling_30_resume_pp_min=settings.KILL_ROLLING_30_RESUME_PP_MIN,
            loss_vs_winners_ratio=settings.KILL_LOSS_VS_WINNERS_RATIO,
            loss_vs_winners_min_winners=settings.KILL_LOSS_VS_WINNERS_MIN_WINNERS,
            loss_dollar_fallback_pct=settings.KILL_LOSS_DOLLAR_FALLBACK_PCT,
            fill_rate_min=settings.KILL_FILL_RATE_MIN,
            fill_rate_min_attempts=settings.KILL_FILL_RATE_MIN_ATTEMPTS,
        )
        kt = KillTriggerMonitor(
            starting_bankroll_usd=live_starting, config=kt_cfg,
        )
        live_thresholds = DrawdownThresholds(
            warn=0.05, halve=0.10, pause=0.15,
            kill=settings.KILL_DRAWDOWN_PCT, halt=settings.TOTAL_DD_HALT_PCT,
        )
        dd = DrawdownMonitor(
            starting_bankroll_usd=lm.current_live_bankroll(),
            thresholds=live_thresholds,
        )
        # Resolve the max-concurrent setting for the preflight check. If
        # 'auto', derive it from current bankroll; the preflight uses the
        # resolved int with `currently_open` subtracted so it only sizes
        # against the cash needed for NEW orders.
        preflight_max_concurrent = _resolve_max_concurrent_live(
            args.max_concurrent, lm, client,
        )
        preflight_currently_open = lm.open_order_count()
        log_main.info(
            "preflight_max_concurrent",
            requested=args.max_concurrent,
            resolved=preflight_max_concurrent,
            currently_open=preflight_currently_open,
        )
        try:
            results = run_preflight(
                settings=settings, client=client, paper=om, live=lm,
                expected_env=expected_env,
                max_concurrent=preflight_max_concurrent,
                currently_open=preflight_currently_open,
                skip_acceptance=skip_acceptance,
                skip_balance=skip_balance,
            )
        except PreflightFailureError as failure:
            log_main.error("preflight_failed",
                           name=failure.result.name,
                           detail=failure.result.detail)
            print(f"\nPRE-FLIGHT FAILED ({failure.result.name}): "
                  f"{failure.result.detail}")
            if discord_url:
                send_discord(
                    discord_url,
                    content=(
                        f"LIVE FAV PREFLIGHT FAILED ({failure.result.name}): "
                        f"{failure.result.detail}"
                    ),
                )
            return 2
        for r in results:
            log_main.info("preflight_check", name=r.name, detail=r.detail)

        # Log-only: override + bypass are noisy as Discord messages,
        # especially during crash loops. Operator already knows these
        # are on because they configured .env that way. Log them so the
        # state is recoverable, but don't spam Discord.
        if settings.LIVE_OVERRIDE_GATE:
            log_main.warning(
                "live_override_gate_active",
                detail="LIVE_OVERRIDE_GATE=true bypasses acceptance criteria",
            )

        bankroll = lm.current_live_bankroll()
        if (
            not args.once
            and not args.yes_i_authorize
            and not _confirm_live(bankroll, settings.LIVE_PER_TRADE_USD)
        ):
            log_main.error("live_confirmation_declined")
            return 3
        if args.yes_i_authorize and not args.once:
            log_main.warning(
                "live_interactive_prompt_bypassed",
                bankroll=bankroll,
                per_trade=settings.LIVE_PER_TRADE_USD,
            )

        _install_signal_handlers(lm, discord_url)
        # Single STARTED line matches v14's terser style. Includes the
        # only info the operator cares about at boot: bankroll, per-trade,
        # max-concurrent, and whether the override gate is active.
        if discord_url:
            override_tag = " override=ON" if settings.LIVE_OVERRIDE_GATE else ""
            send_discord(
                discord_url,
                content=(
                    f"[v1] STARTED ({args.mode}) bankroll=${bankroll:.2f} "
                    f"per_trade=${settings.LIVE_PER_TRADE_USD:.2f} "
                    f"max_concurrent={args.max_concurrent}{override_tag}"
                ),
            )

        if args.once:
            one_loop_favorite_live(
                client, scanner_cfg, lm, kt, dd,
                per_trade_usd=settings.LIVE_PER_TRADE_USD,
                max_concurrent=args.max_concurrent,
                min_net_edge=args.min_net_edge,
                discord_url=discord_url,
                adverse_selection_cfg=adverse_selection_cfg,
                enable_no_underdog=args.enable_no_underdog,
                band_sizing=args.band_sizing,
                step_in_front_enabled=args.step_in_front,
            )
            return 0

        while True:
            try:
                one_loop_favorite_live(
                    client, scanner_cfg, lm, kt, dd,
                    per_trade_usd=settings.LIVE_PER_TRADE_USD,
                    max_concurrent=args.max_concurrent,
                    min_net_edge=args.min_net_edge,
                    discord_url=discord_url,
                    adverse_selection_cfg=adverse_selection_cfg,
                    enable_no_underdog=args.enable_no_underdog,
                    band_sizing=args.band_sizing,
                    step_in_front_enabled=args.step_in_front,
                )
            except Exception as exc:
                log_main.error("live_loop_failed", error=str(exc))
                if discord_url:
                    send_discord(
                        discord_url,
                        content=f"LIVE FAV LOOP FAILED: {exc!s}",
                    )
            time.sleep(args.cadence)


if __name__ == "__main__":
    sys.exit(main())
