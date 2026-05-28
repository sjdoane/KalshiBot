"""Cancel-on-drift adverse selection monitor.

Round 15b addition (2026-05-27): live observation found mean post-fill
mid drift of -4.93pp across 15 still-open v1 fills (n=15), with 9 of 15
showing post-fill drift against the maker bid. This is the classic
favorite-maker adverse selection failure mode: a market moves before
the fill happens, and the maker fills near the worst price.

This module identifies resting orders that should be CANCELLED because
the live market mid has drifted materially against the resting bid
price. The actual cancellation is performed by the caller (the live
order manager / kill trigger loop). This module is pure logic with no
side effects, mirroring the kill_triggers.py and drawdown.py pattern.

Reference: research/v10a/TEST-AND-CONFIRM.md and
research/v10a/12-v1-validation.json.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AdverseSelectionConfig:
    """Drift thresholds for cancelling resting orders."""

    # If current_mid is more than this many cents BELOW the resting bid
    # for a YES order, cancel. Default 3 cents per Becker post-fill
    # drift distribution (95th percentile of acceptable drift).
    drift_against_bid_cents: float = 3.0
    # If current_mid is more than this many cents ABOVE the resting ask
    # for a NO order (we are selling YES, i.e., buying NO at 1 - ask),
    # cancel. Symmetric to drift_against_bid_cents.
    drift_against_ask_cents: float = 3.0
    # Minimum age in minutes before drift-based cancellation activates.
    # Newly placed orders should not be cancelled immediately on the
    # first poll (the market may briefly move and bounce back).
    min_order_age_minutes: int = 15


@dataclass(frozen=True)
class RestingOrderView:
    """Minimal view of a resting order needed for drift evaluation."""

    intent_id: str
    ticker: str
    side: str  # "yes" or "no"
    target_price_cents: int  # the price the maker bid at
    placed_ts: str  # ISO 8601 UTC


@dataclass(frozen=True)
class CancelRecommendation:
    """One cancellation recommendation; the live order manager actuates."""

    intent_id: str
    ticker: str
    side: str
    target_price_cents: int
    current_mid_cents: float
    drift_cents: float
    reason: str  # human readable


def evaluate_resting_orders(
    orders: list[RestingOrderView],
    current_mids_cents: dict[str, float],
    *,
    config: AdverseSelectionConfig,
    now_iso: str,
) -> list[CancelRecommendation]:
    """Return cancellation recommendations for orders that drifted too far.

    orders: list of RestingOrderView objects
    current_mids_cents: ticker -> current orderbook mid in CENTS (1-99).
        Tickers not in this dict are SKIPPED (no live mid available).
    config: AdverseSelectionConfig with thresholds
    now_iso: ISO 8601 UTC for computing order age

    Returns empty list if no orders are recommended for cancellation. The
    caller is responsible for actuating cancellations (this function has
    no side effects).
    """
    from datetime import datetime

    try:
        now = datetime.fromisoformat(now_iso.replace("Z", "+00:00"))
    except ValueError:
        return []

    recs: list[CancelRecommendation] = []
    for order in orders:
        if order.ticker not in current_mids_cents:
            continue
        current_mid = current_mids_cents[order.ticker]
        try:
            placed = datetime.fromisoformat(order.placed_ts.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            continue
        age_minutes = (now - placed).total_seconds() / 60.0
        if age_minutes < config.min_order_age_minutes:
            continue
        if order.side == "yes":
            # We bid YES at target_price_cents. Adverse drift = current
            # mid is BELOW our bid. drift = current_mid - target. If
            # drift is more negative than -threshold, cancel.
            drift = current_mid - order.target_price_cents
            if drift < -config.drift_against_bid_cents:
                recs.append(CancelRecommendation(
                    intent_id=order.intent_id,
                    ticker=order.ticker,
                    side=order.side,
                    target_price_cents=order.target_price_cents,
                    current_mid_cents=current_mid,
                    drift_cents=drift,
                    reason=(
                        f"YES bid at {order.target_price_cents}c; current mid "
                        f"{current_mid:.1f}c; drift {drift:+.1f}c exceeds "
                        f"-{config.drift_against_bid_cents}c threshold"
                    ),
                ))
        elif order.side == "no":
            # We "ask" YES at target_price_cents (equivalently bid NO at
            # 100 - target). Adverse drift = current mid is ABOVE our
            # ask. drift = current_mid - target. If drift > threshold,
            # cancel.
            drift = current_mid - order.target_price_cents
            if drift > config.drift_against_ask_cents:
                recs.append(CancelRecommendation(
                    intent_id=order.intent_id,
                    ticker=order.ticker,
                    side=order.side,
                    target_price_cents=order.target_price_cents,
                    current_mid_cents=current_mid,
                    drift_cents=drift,
                    reason=(
                        f"YES ask at {order.target_price_cents}c; current mid "
                        f"{current_mid:.1f}c; drift {drift:+.1f}c exceeds "
                        f"+{config.drift_against_ask_cents}c threshold"
                    ),
                ))
    return recs
