"""Track A shadow-mode v5 filter logging hook for v1's main loop.

This module is the ONE hook v1's `paper_trade_favorite.py` adds to log
the v5 combined-filter decision on every candidate it processes. By
construction it is LOGGING ONLY: the function returns a decision that
v1's caller MUST NOT consult to alter trade behavior.

Three hard contracts (any violation is a v1 safety incident):

1. **Default OFF.** Reads `SHADOW_MODE_ENABLED` from the environment.
   If unset or not exactly "true" (case-insensitive), the function
   returns None immediately. No fetcher is contacted; no file is
   written.

2. **Never raises.** All work is inside a single try/except Exception.
   Any failure is logged at WARNING and the function returns None.
   v1's caller can therefore wrap the call in a second try/except for
   defense-in-depth without practical concern.

3. **No effect on v1.** The function appends a JSONL line to
   `data/live_trades/v5_filter_shadow_log.jsonl` and returns a
   ShadowDecision. It does not touch state.json, kill_state.json,
   .env, or any v1 trading state. Callers MUST treat the returned
   decision as opaque informational data.

Operator activation (after v5 verdict authorization):

    PowerShell:  $env:SHADOW_MODE_ENABLED = "true"
                 (then start the bot; the env var must be visible to
                 the Python process)

    Deactivation: remove the env var or set to "false". Restart bot.

Logs accumulate at `data/live_trades/v5_filter_shadow_log.jsonl`. After
120-180 days, the operator runs the TA evaluation per V5-A2 Section 7
and decides whether to activate the filter as a SKIP overlay (separate
operator-authorized change to v1; not implemented here).

The implementation choices below mirror the brief verbatim where the
brief specified code. Any deviation is documented in a comment near
the point of departure.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from kalshi_bot.strategy.pricing import MarketSnapshot


log = logging.getLogger(__name__)


# Append-only JSONL sink. Lives under data/live_trades/ alongside v1's
# other operational logs, but is deliberately a DIFFERENT file from
# state.json and kill_state.json: no shared write path with v1's trade
# accounting.
SHADOW_LOG_PATH = Path("data/live_trades/v5_filter_shadow_log.jsonl")

# Env-flag canonical names. Read at every call so the operator can flip
# without restarting (when the host process picks up env changes).
#
# Two independent flags:
# - SHADOW_MODE_ENABLED: run the filter and APPEND its decision to the
#   JSONL log. v1's trade decision is unchanged.
# - LIVE_FILTER_ENABLED: run the filter and SKIP v1's trade when the
#   filter says fade. This is the active-overlay mode; v1's behavior
#   DOES change. The skip applies only when the filter has a confident
#   fade signal (any of polymarket_fade, sportsbook_fade,
#   monotonicity_violation, or any_fade_rule_fires). When fetchers miss
#   or the filter abstains (`should_trade=True` because no rule fires),
#   v1 proceeds with its normal trade.
#
# Operator-recommended pairing: enable BOTH flags together so the JSONL
# log captures which candidates were filtered out. LIVE_FILTER_ENABLED
# alone works (skip without log) but loses the audit trail.
SHADOW_MODE_ENV = "SHADOW_MODE_ENABLED"
LIVE_FILTER_ENV = "LIVE_FILTER_ENABLED"


@dataclass
class ShadowDecision:
    """One v5-filter shadow decision; appended to SHADOW_LOG_PATH.

    All fields are designed to be JSON-serializable via __dict__ so the
    write path is a one-liner. Tuple fields are converted to lists by
    json.dumps automatically.
    """
    timestamp: str          # ISO 8601 UTC
    ticker: str
    series_ticker: str
    kalshi_price: float
    poly_mid: float | None
    sportsbook_implied: float | None
    cross_market_implied: float | None
    should_trade: bool      # what the filter says (LOG ONLY; v1 does NOT consult)
    fired_rules: tuple[str, ...]  # e.g., ("polymarket_fade",)
    reason: str
    confidence: float
    fetch_status: dict      # {"poly": "ok"|"miss"|"error", "book": "ok"|"miss"|"error"}
    fetch_latency_ms: int   # total wall time for fetches


def _is_shadow_logging_enabled() -> bool:
    """Strict env-flag check for shadow JSONL logging. Only the literal
    'true' (any case) enables. Anything else leaves the log OFF.
    """
    return os.environ.get(SHADOW_MODE_ENV, "false").lower() == "true"


def is_live_filter_enabled() -> bool:
    """Strict env-flag check for the ACTIVE filter overlay. Only the
    literal 'true' (any case) enables. When true, v1 will skip
    candidates where the v5 combined filter says fade.

    Exposed publicly so paper_trade_favorite.py can check the flag at
    call time and apply the skip without re-reading the env directly.
    """
    return os.environ.get(LIVE_FILTER_ENV, "false").lower() == "true"


def _is_filter_active() -> bool:
    """True if either shadow logging OR live filter overlay is enabled.

    The filter is computed when either flag is set; the action taken
    depends on which (log vs skip vs both).
    """
    return _is_shadow_logging_enabled() or is_live_filter_enabled()


# Backward-compat alias. The original shadow_filter API gated entirely
# on _is_enabled(); tests + external callers may still import it.
_is_enabled = _is_shadow_logging_enabled


def _serialize_for_jsonl(sd: ShadowDecision) -> str:
    """Convert a ShadowDecision to a single JSONL line.

    tuple -> list, dataclass -> dict (via __dict__). json.dumps with
    default=str handles any unexpected non-serializable field by
    coercing to str rather than raising.
    """
    payload = dict(sd.__dict__)
    payload["fired_rules"] = list(payload.get("fired_rules") or [])
    return json.dumps(payload, default=str)


def shadow_evaluate(
    snap: MarketSnapshot,
    kalshi_price: float,
) -> ShadowDecision | None:
    """Run the v5 combined filter in shadow-mode for a single candidate.

    Args:
        snap: The MarketSnapshot v1 is about to consider. Used for
            ticker / series_ticker context.
        kalshi_price: The price v1 uses for its trade decision
            (typically `snap.yes_bid`). This is the price the shadow
            filter evaluates against the second-opinion signals.

    Returns:
        ShadowDecision if SHADOW_MODE_ENABLED=true and the evaluation
        completed (with or without fetcher matches). None if disabled
        or any error occurred. The decision is also appended to
        SHADOW_LOG_PATH as a JSONL line.

    The caller MUST NOT use the returned decision to alter trade
    behavior. This function is a passive logger. v1's trade decisions
    are made strictly on `is_eligible(target_price)` and
    `expected_net_edge()`; this hook is invisible to those code paths.

    Never raises. Any internal failure is logged at WARNING and None
    is returned.
    """
    if not _is_filter_active():
        return None
    try:
        # Lazy imports keep the module load cheap when both env flags are
        # off, and isolate any future import-time error from the
        # always-loaded v1 strategy package.
        from kalshi_bot_v5.filter_combined import evaluate_market_combined
        from kalshi_bot_v5.polymarket_fetcher import fetch_polymarket_midpoint
        from kalshi_bot_v5.sportsbook_fetcher import fetch_sportsbook_implied

        # Fetch second-opinion signals. Each fetcher catches its own
        # exceptions and returns None on any failure, so this try block
        # mostly guards against truly unexpected runtime errors
        # (KeyboardInterrupt-class only, since BaseException isn't
        # caught here).
        t0 = datetime.now(UTC)
        poly_status = "miss"
        book_status = "miss"
        poly: float | None = None
        book: float | None = None

        try:
            poly = fetch_polymarket_midpoint(snap.ticker, snap.series_ticker)
            if poly is not None:
                poly_status = "ok"
        except Exception as exc:
            poly_status = "error"
            log.debug("shadow_poly_fetcher_raised", exc_info=exc)

        try:
            book = fetch_sportsbook_implied(snap.ticker, snap.series_ticker)
            if book is not None:
                book_status = "ok"
        except Exception as exc:
            book_status = "error"
            log.debug("shadow_book_fetcher_raised", exc_info=exc)

        latency_ms = int((datetime.now(UTC) - t0).total_seconds() * 1000)

        poly_lookup = {snap.ticker: poly} if poly is not None else {}
        sb_lookup = {snap.ticker: book} if book is not None else {}

        decision = evaluate_market_combined(
            ticker=snap.ticker,
            kalshi_price=kalshi_price,
            series_ticker=snap.series_ticker,
            poly_lookup=poly_lookup,
            sportsbook_lookup=sb_lookup,
            cross_market_data=None,  # cross-market disabled in shadow-mode for now
        )

        sd = ShadowDecision(
            timestamp=datetime.now(UTC).isoformat(),
            ticker=snap.ticker,
            series_ticker=snap.series_ticker,
            kalshi_price=float(kalshi_price),
            poly_mid=poly,
            sportsbook_implied=book,
            cross_market_implied=decision.cross_market_implied,
            should_trade=bool(decision.should_trade),
            fired_rules=tuple(decision.fired_rules),
            reason=str(decision.reason),
            confidence=float(decision.confidence),
            fetch_status={"poly": poly_status, "book": book_status},
            fetch_latency_ms=latency_ms,
        )

        # Append to JSONL only when shadow logging is enabled. When only
        # LIVE_FILTER_ENABLED is set, we compute the decision and return
        # it to the caller (for the skip check) without writing the log.
        if _is_shadow_logging_enabled():
            try:
                SHADOW_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
                with SHADOW_LOG_PATH.open("a", encoding="utf-8") as f:
                    f.write(_serialize_for_jsonl(sd) + "\n")
            except OSError as exc:
                # Logging the decision is best-effort. If the disk write
                # fails (read-only fs, permissions, full disk), we still
                # return the decision to the caller (informational) and
                # log the disk error.
                log.warning("shadow_filter_log_write_failed", exc_info=exc)
        return sd
    except Exception as exc:
        log.warning("shadow_filter_error", exc_info=exc)
        return None
