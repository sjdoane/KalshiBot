"""Dutch-book / no-arbitrage analysis for Kalshi mutually-exclusive event groups.

Pure, network-free core. A Kalshi event flagged `mutually_exclusive` is a set of
binary markets where exactly one outcome resolves YES. Two risk-free locks are
possible when the book is mispriced:

- UNDERROUND (buy all YES): if you can buy YES on EVERY outcome and the asks sum
  below 1, you pay sum(asks) < 1 and are guaranteed $1 (the one winner). This
  requires the group to be collectively EXHAUSTIVE; if an unlisted outcome can
  win, this lock is NOT safe.
- OVERROUND (buy all NO): buy NO on every outcome. Exactly one resolves YES (its
  NO pays 0); the other N-1 pay $1. Profit = (N-1) - sum(no_ask). This lock is
  ROBUST to a non-exhaustive group: an unlisted winner just makes all N of your
  NOs pay, which only increases profit. So overround is the safer signal.

Both lock capital until the event resolves, so the annualized return (computed
by the caller from days-to-close) matters more than the raw margin.

Fees: Kalshi charges a per-contract taker fee on EVERY leg, so an N-outcome lock
pays N fees. The verified fee formula is kalshi_taker_fee_per_contract.
"""

from __future__ import annotations

from kalshi_bot.analysis.metrics import kalshi_taker_fee_per_contract


def _f(v: object) -> float | None:
    """Parse a Kalshi *_dollars / *_size_fp value to float, or None."""
    if v is None:
        return None
    try:
        fv = float(v)
    except (TypeError, ValueError):
        return None
    return fv


def parse_market_quote(m: dict) -> dict:
    """Extract the executable top-of-book quote for one market.

    Returns a dict with yes_bid, yes_ask, no_ask (dollars; None if absent or
    non-positive) and yes_ask_size, no_ask_size (contracts at the top; 0.0 if
    absent). A price of 0 means "no quote on that side" and is treated as None,
    so an incomplete leg is never silently counted as a free fill.
    """
    yes_bid = _f(m.get("yes_bid_dollars"))
    yes_ask = _f(m.get("yes_ask_dollars"))
    no_ask = _f(m.get("no_ask_dollars"))
    yes_ask_size = _f(m.get("yes_ask_size_fp")) or 0.0
    no_ask_size = _f(m.get("no_ask_size_fp")) or 0.0
    return {
        "ticker": m.get("ticker", ""),
        "status": m.get("status", ""),
        "yes_bid": yes_bid if (yes_bid and yes_bid > 0) else None,
        "yes_ask": yes_ask if (yes_ask and yes_ask > 0) else None,
        "no_ask": no_ask if (no_ask and no_ask > 0) else None,
        "yes_ask_size": yes_ask_size,
        "no_ask_size": no_ask_size,
    }


def analyze_group(quotes: list[dict]) -> dict:
    """Compute the underround and overround locks for one event group.

    `quotes` is a list of parse_market_quote dicts (one per outcome). A lock is
    only computable when EVERY leg has the needed quote (you cannot complete the
    basket otherwise); a missing leg yields lock=None for that direction.

    Returns {n, underround, overround} where each lock (or None) is a dict:
      cost          dollars to put on the basket (one contract per leg)
      gross_margin  guaranteed payout minus cost, before fees
      total_fee     sum of per-leg taker fees
      net_margin    gross_margin - total_fee (the risk-free profit per basket)
      min_depth     smallest top-of-book size across legs (bindable size)
    """
    n = len(quotes)
    result: dict = {"n": n, "underround": None, "overround": None}
    if n < 2:
        return result

    # Underround: buy all YES (requires exhaustiveness; flagged by the caller).
    yes_asks = [q["yes_ask"] for q in quotes]
    if all(a is not None for a in yes_asks):
        cost = float(sum(yes_asks))  # type: ignore[arg-type]
        total_fee = float(sum(kalshi_taker_fee_per_contract(a) for a in yes_asks))  # type: ignore[arg-type]
        gross = 1.0 - cost
        result["underround"] = {
            "cost": round(cost, 4),
            "gross_margin": round(gross, 4),
            "total_fee": round(total_fee, 4),
            "net_margin": round(gross - total_fee, 4),
            "min_depth": min(q["yes_ask_size"] for q in quotes),
        }

    # Overround: buy all NO (robust to a non-exhaustive group).
    no_asks = [q["no_ask"] for q in quotes]
    if all(a is not None for a in no_asks):
        cost = float(sum(no_asks))  # type: ignore[arg-type]
        total_fee = float(sum(kalshi_taker_fee_per_contract(a) for a in no_asks))  # type: ignore[arg-type]
        gross = float(n - 1) - cost
        result["overround"] = {
            "cost": round(cost, 4),
            "gross_margin": round(gross, 4),
            "total_fee": round(total_fee, 4),
            "net_margin": round(gross - total_fee, 4),
            "min_depth": min(q["no_ask_size"] for q in quotes),
        }
    return result


def annualized_return(net_margin: float, cost: float, days_to_close: float) -> float | None:
    """Risk-free annualized return of a lock: (net / cost) scaled to a year.

    Capital is locked until resolution, so a small margin on a months-out event
    is a poor use of capital. Returns None when cost <= 0 or days <= 0 (cannot
    annualize), so the caller does not divide by zero."""
    if cost <= 0 or days_to_close <= 0:
        return None
    return (net_margin / cost) * (365.0 / days_to_close)
