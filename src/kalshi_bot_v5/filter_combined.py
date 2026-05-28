"""Unified v5 filter module: Track A1 (Polymarket-fade) + Track A2
(Kalshi cross-market consistency) + Track A3 (Sportsbook-fade).

This module is the v5 extension of `src/kalshi_bot_v4/filter.py`. It
adds the sportsbook-fade rule as a third defensive overlay, runs all
three rules in OR-logic, and returns a `CombinedFilterDecision` with
the reason field indicating which rule fired (or which combination).

Defensive overlay semantics: the filter can REMOVE trades v1 would
have made, NEVER ADD new trades. The sportsbook-fade rule mirrors the
Polymarket-fade rule but uses the de-vigged median sportsbook
implied probability instead of Polymarket mid. If sportsbook lines
say Kalshi is over-priced by more than `fade_threshold_cents_book`,
skip the trade.

Pre-registered thresholds per V5-A2 master plan (locked before
backtest, no post-hoc tuning):

    FADE_THRESHOLD_CENTS_POLY_DEFAULT = 7.0
        Matches V4-E locked value. V3-C measured Kalshi-minus-Polymarket
        mean +9.21c on favorites; 7c is conservative.

    FADE_THRESHOLD_CENTS_BOOK_DEFAULT = 5.0
        V5-A1 measured Kalshi-minus-Sportsbook mean +1.70c on favorites
        (n=23). 5c is the smallest sensible fade threshold below which
        live mid noise dominates the signal. The book threshold is
        deliberately tighter than the Polymarket threshold because the
        institutional consensus shows smaller divergences (closer to
        truth).

    MONOTONICITY_THRESHOLD_CENTS_DEFAULT = 5.0
        Matches V4-E locked value.

Three sub-filters, OR-combined:

    Track A1 (Polymarket-fade):
        Given candidate at price p_k, if Polymarket has a matched
        counterpart at mid p_p and p_k - p_p > fade_poly_threshold,
        skip.

    Track A2 (Cross-market consistency):
        For ladder series (KXNFLWINS, KXNBAWINS, KXMLBWINS, KXNHLWINS,
        KXWNBAWINS), enforce monotonicity P(wins>=k) non-increasing in
        k. Skip when candidate is over-priced relative to a lower
        threshold sibling by > monotonicity_threshold.

    Track A3 (Sportsbook-fade):
        Given candidate at price p_k, if the-odds-api has a matched
        event with median de-vigged implied p_s, and p_k - p_s >
        fade_book_threshold, skip.

Combined decision: should_trade = NOT (A1 OR A2 OR A3).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import NamedTuple, Optional, Union


# Pre-registered thresholds. Do NOT modify without a new pre-registered
# test entry in research/v5/iterations.md.
FADE_THRESHOLD_CENTS_POLY_DEFAULT: float = 7.0
FADE_THRESHOLD_CENTS_BOOK_DEFAULT: float = 5.0
MONOTONICITY_THRESHOLD_CENTS_DEFAULT: float = 5.0

# Same set as v4 (extended here for explicitness).
LADDER_SERIES_PREFIXES: frozenset[str] = frozenset({
    "KXNFLWINS",
    "KXNBAWINS",
    "KXMLBWINS",
    "KXNHLWINS",
    "KXWNBAWINS",
})


class CombinedFilterDecision(NamedTuple):
    """The verdict the combined v5 filter delivers for one candidate.

    Attributes:
        should_trade: True if v1 should proceed; False if the filter
            removes the trade.
        reason: One of:
            "pass": no filter fired; v1 proceeds.
            "no_match": no filter input was available (no poly, no
                book, no ladder data).
            "polymarket_fade": A1 fired alone.
            "sportsbook_fade": A3 fired alone.
            "monotonicity_violation": A2 fired alone.
            "any_fade_rule_fires": multiple rules fired (>=2 of A1, A2,
                A3). The fired_rules field lists which.
            "no_poly_match": no Polymarket mid available; other rules
                did not fire.
            "no_book_match": no sportsbook implied available; other
                rules did not fire.
        poly_mid: Polymarket YES mid used for A1, or None.
        sportsbook_implied: De-vigged median sportsbook implied
            probability for A3, or None.
        kalshi_price: The candidate Kalshi YES mid.
        cross_market_implied: A2 implied (from ladder), or None.
        confidence: 0 to 1; reflects strongest sub-filter conviction.
        fired_rules: Tuple of rule labels that fired (subset of
            {"polymarket_fade", "sportsbook_fade",
            "monotonicity_violation"}). Empty tuple if none fired.
    """
    should_trade: bool
    reason: str
    poly_mid: Optional[float]
    sportsbook_implied: Optional[float]
    kalshi_price: float
    cross_market_implied: Optional[float]
    confidence: float
    fired_rules: tuple[str, ...]


def parse_ladder_ticker(ticker: str) -> Optional[tuple[str, int]]:
    """Parse a ladder ticker like KXNFLWINS-IND-25B-T8 into
    (ladder_key, threshold). Returns None if not a ladder ticker.
    Mirrors v4.
    """
    m = re.match(r"^(K[A-Z]+WINS-[A-Z0-9]+-[A-Z0-9]+)-T(\d+)$", ticker)
    if not m:
        return None
    return m.group(1), int(m.group(2))


def series_prefix_of(ticker: str) -> str:
    """First token of a Kalshi ticker; KXNFLWINS-IND-25B-T8 -> KXNFLWINS."""
    return ticker.split("-", 1)[0]


def is_ladder_series(series_prefix: str) -> bool:
    return series_prefix in LADDER_SERIES_PREFIXES


def _resolve_lookup(
    ticker: str,
    lookup: Optional[Union[dict, Callable[[str], Optional[float]]]],
) -> Optional[float]:
    """Resolve a lookup (dict or callable) to a price for this ticker."""
    if lookup is None:
        return None
    if callable(lookup):
        try:
            mid = lookup(ticker)
        except Exception:
            return None
        return float(mid) if mid is not None else None
    if isinstance(lookup, dict):
        mid = lookup.get(ticker)
        return float(mid) if mid is not None else None
    return None


def _evaluate_polymarket_fade(
    ticker: str,
    kalshi_price: float,
    poly_lookup: Optional[Union[dict, Callable]],
    fade_threshold_cents: float,
) -> tuple[bool, Optional[float], float]:
    """Track A1. Returns (fires, poly_mid, confidence)."""
    poly_mid = _resolve_lookup(ticker, poly_lookup)
    if poly_mid is None:
        return False, None, 0.0
    divergence_cents = (kalshi_price - poly_mid) * 100.0
    if divergence_cents > fade_threshold_cents:
        extra_cents = divergence_cents - fade_threshold_cents
        confidence = min(1.0, extra_cents / 18.0)
        return True, poly_mid, confidence
    return False, poly_mid, 0.0


def _evaluate_sportsbook_fade(
    ticker: str,
    kalshi_price: float,
    sportsbook_lookup: Optional[Union[dict, Callable]],
    fade_threshold_cents: float,
) -> tuple[bool, Optional[float], float]:
    """Track A3. Returns (fires, sportsbook_implied, confidence).

    Same structural logic as A1 but with a tighter threshold and a
    different reference price. The sportsbook implied probability is
    the de-vigged median across books (per V5-A1's methodology).
    """
    sportsbook_implied = _resolve_lookup(ticker, sportsbook_lookup)
    if sportsbook_implied is None:
        return False, None, 0.0
    divergence_cents = (kalshi_price - sportsbook_implied) * 100.0
    if divergence_cents > fade_threshold_cents:
        extra_cents = divergence_cents - fade_threshold_cents
        # Sportsbook divergences are SMALLER in magnitude (V5-A1 mean
        # +1.70c vs Polymarket +9.21c). Scale confidence to saturate at
        # +10c above threshold (versus +18c for Polymarket).
        confidence = min(1.0, extra_cents / 10.0)
        return True, sportsbook_implied, confidence
    return False, sportsbook_implied, 0.0


def _evaluate_cross_market(
    ticker: str,
    kalshi_price: float,
    cross_market_data: Optional[dict],
    monotonicity_threshold_cents: float,
) -> tuple[bool, Optional[float], float]:
    """Track A2. Mirrors v4 logic exactly.

    cross_market_data shape: { ladder_key: { threshold: price, ... } }
    e.g. { 'KXNFLWINS-IND-25B': {3: 0.96, 4: 0.86, 7: 0.37, 8: 0.77} }
    """
    if cross_market_data is None:
        return False, None, 0.0

    parsed = parse_ladder_ticker(ticker)
    if parsed is None:
        return False, None, 0.0
    ladder_key, threshold = parsed

    ladder = cross_market_data.get(ladder_key)
    if not ladder or len(ladder) < 2:
        return False, None, 0.0

    items = sorted(
        ((int(k), float(v)) for k, v in ladder.items() if v is not None),
        key=lambda kv: kv[0],
    )
    if len(items) < 2:
        return False, None, 0.0

    threshold_to_price = dict(items)
    siblings = {k: p for k, p in threshold_to_price.items() if k != threshold}
    if not siblings:
        return False, None, 0.0

    lower_siblings = [(k, p) for k, p in siblings.items() if k < threshold]
    lower_violation_max_gap = 0.0
    for _, lower_price in lower_siblings:
        gap_cents = (kalshi_price - lower_price) * 100.0
        if gap_cents > monotonicity_threshold_cents:
            lower_violation_max_gap = max(lower_violation_max_gap, gap_cents)

    upper_bound_implied: Optional[float] = None
    for _, p_lower in lower_siblings:
        if upper_bound_implied is None or p_lower < upper_bound_implied:
            upper_bound_implied = p_lower

    higher_siblings = [(k, p) for k, p in siblings.items() if k > threshold]
    lower_bound_implied: Optional[float] = None
    for _, p_higher in higher_siblings:
        if lower_bound_implied is None or p_higher > lower_bound_implied:
            lower_bound_implied = p_higher

    implied: Optional[float] = None
    if upper_bound_implied is not None and lower_bound_implied is not None:
        implied = (upper_bound_implied + lower_bound_implied) / 2.0
    elif upper_bound_implied is not None:
        implied = upper_bound_implied
    elif lower_bound_implied is not None:
        implied = lower_bound_implied

    if lower_violation_max_gap > monotonicity_threshold_cents:
        extra_cents = lower_violation_max_gap - monotonicity_threshold_cents
        confidence = min(1.0, extra_cents / 20.0)
        return True, implied, confidence

    return False, implied, 0.0


def evaluate_market_combined(
    ticker: str,
    kalshi_price: float,
    series_ticker: str,
    *,
    poly_lookup: Optional[Union[dict, Callable[[str], Optional[float]]]] = None,
    sportsbook_lookup: Optional[Union[dict, Callable[[str], Optional[float]]]] = None,
    cross_market_data: Optional[dict] = None,
    fade_threshold_cents_poly: float = FADE_THRESHOLD_CENTS_POLY_DEFAULT,
    fade_threshold_cents_book: float = FADE_THRESHOLD_CENTS_BOOK_DEFAULT,
    monotonicity_threshold_cents: float = MONOTONICITY_THRESHOLD_CENTS_DEFAULT,
) -> CombinedFilterDecision:
    """Apply Polymarket-fade + sportsbook-fade + cross-market consistency.

    Returns SKIP if ANY rule fires (OR-logic), with reason indicating
    which rule (or set of rules) fired.

    Args:
        ticker: Kalshi market ticker.
        kalshi_price: Current Kalshi YES mid (0 to 1).
        series_ticker: Team-level series ticker for context.
        poly_lookup: Optional dict or callable mapping ticker to
            Polymarket YES mid. None disables A1.
        sportsbook_lookup: Optional dict or callable mapping ticker to
            de-vigged median sportsbook implied probability. None
            disables A3.
        cross_market_data: Optional ladder data dict. None disables A2.
        fade_threshold_cents_poly: A1 threshold (default 7c, locked).
        fade_threshold_cents_book: A3 threshold (default 5c, locked).
        monotonicity_threshold_cents: A2 threshold (default 5c, locked).

    Returns:
        CombinedFilterDecision capturing whether to trade and why.
    """
    series_prefix = series_prefix_of(ticker)

    a1_fires, poly_mid, a1_conf = _evaluate_polymarket_fade(
        ticker, kalshi_price, poly_lookup, fade_threshold_cents_poly,
    )

    a3_fires, sportsbook_implied, a3_conf = _evaluate_sportsbook_fade(
        ticker, kalshi_price, sportsbook_lookup, fade_threshold_cents_book,
    )

    if is_ladder_series(series_prefix):
        a2_fires, cross_implied, a2_conf = _evaluate_cross_market(
            ticker, kalshi_price, cross_market_data, monotonicity_threshold_cents,
        )
    else:
        a2_fires, cross_implied, a2_conf = False, None, 0.0

    fired: list[str] = []
    if a1_fires:
        fired.append("polymarket_fade")
    if a3_fires:
        fired.append("sportsbook_fade")
    if a2_fires:
        fired.append("monotonicity_violation")

    if len(fired) >= 2:
        confidence = max(a1_conf, a3_conf, a2_conf)
        return CombinedFilterDecision(
            should_trade=False,
            reason="any_fade_rule_fires",
            poly_mid=poly_mid,
            sportsbook_implied=sportsbook_implied,
            kalshi_price=kalshi_price,
            cross_market_implied=cross_implied,
            confidence=confidence,
            fired_rules=tuple(fired),
        )
    if len(fired) == 1:
        # Single rule fired; reason matches the rule label.
        rule = fired[0]
        if rule == "polymarket_fade":
            confidence = a1_conf
        elif rule == "sportsbook_fade":
            confidence = a3_conf
        else:
            confidence = a2_conf
        return CombinedFilterDecision(
            should_trade=False,
            reason=rule,
            poly_mid=poly_mid,
            sportsbook_implied=sportsbook_implied,
            kalshi_price=kalshi_price,
            cross_market_implied=cross_implied,
            confidence=confidence,
            fired_rules=tuple(fired),
        )

    # No fire. Classify the reason according to which inputs were
    # actually available.
    poly_attempted = poly_lookup is not None
    book_attempted = sportsbook_lookup is not None
    has_any_input = (
        poly_mid is not None
        or sportsbook_implied is not None
        or cross_implied is not None
    )

    if not has_any_input and not poly_attempted and not book_attempted:
        # Filter was called with no data sources at all.
        reason = "no_match"
    elif has_any_input:
        # At least one rule had data but none disagreed enough.
        reason = "pass"
    elif poly_attempted and poly_mid is None and not book_attempted:
        reason = "no_poly_match"
    elif book_attempted and sportsbook_implied is None and not poly_attempted:
        reason = "no_book_match"
    elif poly_attempted and book_attempted and poly_mid is None and sportsbook_implied is None:
        # Both attempted, neither matched. Conservatively label no_match.
        reason = "no_match"
    elif poly_attempted and poly_mid is None:
        reason = "no_poly_match"
    elif book_attempted and sportsbook_implied is None:
        reason = "no_book_match"
    else:
        reason = "no_match"

    return CombinedFilterDecision(
        should_trade=True,
        reason=reason,
        poly_mid=poly_mid,
        sportsbook_implied=sportsbook_implied,
        kalshi_price=kalshi_price,
        cross_market_implied=cross_implied,
        confidence=0.0,
        fired_rules=tuple(),
    )
