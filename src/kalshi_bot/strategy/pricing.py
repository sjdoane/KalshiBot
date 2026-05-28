"""Maker-quote pricing for the live (paper or production) bot.

Given a market snapshot (price, orderbook, calibration model), decide:
- Is the market a candidate to quote on?
- What's the recalibrated truth estimate?
- What's the expected net edge per contract?
- Which side (YES maker or NO maker)?

This module is category-agnostic. The caller passes a fitted isotonic
calibrator and a configured filter. Phase 2 / sports gate code lives
upstream.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from kalshi_bot.analysis.metrics import kalshi_maker_fee_per_contract


@dataclass(frozen=True)
class MarketSnapshot:
    """Minimum fields needed to price a market live."""

    ticker: str
    event_ticker: str
    series_ticker: str
    yes_bid: float  # in dollars, e.g. 0.32
    yes_ask: float
    last_price: float
    volume: float
    open_time: str
    close_time: str
    title: str = ""


@dataclass(frozen=True)
class QuoteDecision:
    """Output of pricing.decide(): what to do with this market."""

    side: str  # "yes" or "no" (which side to buy as maker)
    target_price: float  # the price at which to post the maker bid
    recalibrated_prob: float  # model's truth estimate for YES
    market_mid: float  # the observed mid (bid+ask)/2
    expected_net_edge: float  # expected $ net per contract after fees + slippage
    rationale: str = ""


# Slippage allowance matches the methodology (Phase 2 + Sports). Round-
# trip maker fee model lives in metrics.py.
DEFAULT_SLIPPAGE = 0.015


def market_mid(snapshot: MarketSnapshot) -> float | None:
    """Mid price from the current orderbook. Returns None if quotes are
    missing or degenerate."""
    if snapshot.yes_bid <= 0 or snapshot.yes_ask <= 0:
        return None
    if snapshot.yes_ask <= snapshot.yes_bid:
        return None
    return (snapshot.yes_bid + snapshot.yes_ask) / 2.0


def round_trip_maker_fee(price: float) -> float:
    """Round-trip maker fee per contract at a given price."""
    return 2.0 * kalshi_maker_fee_per_contract(price)


def expected_net_edge_per_contract(
    market_price: float,
    recalibrated_prob: float,
    *,
    side: str,
    slippage: float = DEFAULT_SLIPPAGE,
) -> float:
    """Expected net P&L per contract for a maker on `side` at `market_price`.

    - side = "yes": maker buys YES contract at market_price. EV per
      contract = recalibrated_prob - market_price.
    - side = "no": maker buys NO contract at (1 - market_price). EV per
      contract = (1 - recalibrated_prob) - (1 - market_price) =
      market_price - recalibrated_prob.

    Gross EV becomes net after deducting round-trip maker fee and
    slippage allowance.
    """
    if side not in ("yes", "no"):
        raise ValueError(f"side must be 'yes' or 'no', got {side!r}")
    gross = recalibrated_prob - market_price if side == "yes" else market_price - recalibrated_prob
    fee = round_trip_maker_fee(market_price)
    return gross - fee - slippage


def decide(
    snapshot: MarketSnapshot,
    recalibrated_prob: float,
    *,
    min_net_edge: float = 0.005,
    slippage: float = DEFAULT_SLIPPAGE,
    tick_size: float = 0.01,
) -> QuoteDecision | None:
    """Return a QuoteDecision if this market should be quoted, else None.

    Strategy: post a maker bid one tick INSIDE the best opposite quote.
    If recalibrated > market_mid: maker buys YES. Posts a bid at
    yes_bid + tick (one tick above the current best bid, but capped
    below the recalibrated value minus fee + slippage buffer).
    Symmetric for NO.

    Returns None if expected net edge is below `min_net_edge` or if the
    orderbook is degenerate.
    """
    mid = market_mid(snapshot)
    if mid is None:
        return None

    if recalibrated_prob > mid:
        side = "yes"
        # Post a YES bid one tick above current best YES bid
        target_price = round(snapshot.yes_bid + tick_size, 4)
        # Cap target to avoid paying more than recalibrated value minus buffer
        cap = recalibrated_prob - round_trip_maker_fee(target_price) - slippage
        target_price = min(target_price, cap)
    else:
        side = "no"
        # NO bid is equivalent to selling YES; post one tick below best ask
        target_price = round(snapshot.yes_ask - tick_size, 4)
        cap = recalibrated_prob + round_trip_maker_fee(target_price) + slippage
        target_price = max(target_price, cap)

    target_price = max(0.01, min(0.99, target_price))

    net = expected_net_edge_per_contract(
        target_price, recalibrated_prob, side=side, slippage=slippage,
    )
    if net < min_net_edge:
        return None

    rationale = (
        f"side={side} mid={mid:.4f} recal={recalibrated_prob:.4f} "
        f"target={target_price:.4f} net={net*100:.2f}pp"
    )
    return QuoteDecision(
        side=side,
        target_price=target_price,
        recalibrated_prob=recalibrated_prob,
        market_mid=mid,
        expected_net_edge=net,
        rationale=rationale,
    )


def isotonic_recalibrate(
    market_price: float, calibrator
) -> float:
    """Wrap calibrator.predict for a single price. Returns NaN-safe scalar."""
    out = calibrator.predict(np.array([market_price], dtype=float))
    return float(out[0])
