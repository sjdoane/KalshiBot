"""Unified v4 filter module: Track A1 (Polymarket-fade) + Track A2
(Kalshi cross-market consistency).

Defensive overlay on v1: the filter can only REMOVE trades v1 would
have made, NEVER add new trades. This module exposes a single
`evaluate_market()` entrypoint that returns a `FilterDecision` capturing
the recommendation, reason, and supporting numbers.

Pre-registered thresholds per v4 master plan Section 6.4:
    FADE_THRESHOLD_CENTS = 7.0
        Between V3-C's measured mean Kalshi-minus-Polymarket of +9.2c
        at T-35d and the 5c sub-stack tradeable threshold from the
        Polymarket literature. Conservative: only fires on the upper
        half of historically observed divergences.

    MONOTONICITY_THRESHOLD_CENTS = 5.0
        Per V4-D's analysis of NFL win-total ladders. A 5c monotonicity
        violation is the minimum threshold below which last-trade
        noise on thin thresholds dominates real disagreement.

These thresholds are LOCKED at build time. Per the operator's hard
constraint: any threshold variant tried after the headline backtest
is a separate pre-registered test logged in iterations.md, not a
post-hoc tune.

Track A1 (Polymarket-fade-filter):
    Given a candidate Kalshi market at price p_k, if Polymarket has
    a matched counterpart at mid p_p, and p_k - p_p > FADE_THRESHOLD,
    skip the trade. Otherwise allow v1's normal logic to proceed.
    If no Polymarket match exists, this filter abstains.

Track A2 (Cross-market consistency):
    For threshold-ladder series (KXNFLWINS-{TEAM}-{YEAR}-T{k}, similar
    for KXNBAWINS, KXMLBWINS, KXNHLWINS, KXWNBAWINS), the prices of
    siblings in the same team-season should be monotonically
    NON-INCREASING in k (P(wins>=k) is decreasing in k). When the
    target ticker is on the OVER-priced side of a violation, skip.

Both filters compose: should_trade = NOT A1.fires AND NOT A2.fires.
The returned `FilterDecision.reason` records which sub-filter triggered.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import NamedTuple, Optional, Union


# Pre-registered thresholds. Do NOT modify without a new pre-registered
# test entry in research/v4/iterations.md.
FADE_THRESHOLD_CENTS_DEFAULT: float = 7.0
MONOTONICITY_THRESHOLD_CENTS_DEFAULT: float = 5.0

# Series prefixes that have a multi-threshold ladder structure suitable
# for Track A2 cross-market consistency. Extending this list to other
# series requires re-validation of the per-series ladder structure.
LADDER_SERIES_PREFIXES: frozenset[str] = frozenset({
    "KXNFLWINS",
    "KXNBAWINS",
    "KXMLBWINS",
    "KXNHLWINS",
    "KXWNBAWINS",
})


class FilterDecision(NamedTuple):
    """The verdict the filter delivers for a single candidate market.

    Attributes:
        should_trade: True if the filter passes the trade through to v1.
            False if v1 should skip this trade entirely.
        reason: One of
            "pass": no filter fired; v1 proceeds normally.
            "no_poly_match": Polymarket has no matched counterpart;
                Track A1 abstains. Track A2 may still have fired.
            "polymarket_fade": Track A1 fired (kalshi >> poly).
            "monotonicity_violation": Track A2 fired.
            "both": both A1 and A2 fired.
            "no_signal_partial": filter inputs available but no
                disagreement large enough to trigger either sub-filter.
        poly_mid: The Polymarket YES mid used for the A1 check, or None
            if no Polymarket match was available.
        kalshi_price: The Kalshi YES price we are evaluating.
        cross_market_implied: For A2, the implied price at this
            threshold derived from the team-season ladder, or None if
            the series has no ladder structure or fewer than 2 sibling
            thresholds are available.
        confidence: 0 to 1; 0 means filter is uncertain (no inputs);
            higher values reflect stronger filter conviction (larger
            divergence above threshold).
    """
    should_trade: bool
    reason: str
    poly_mid: Optional[float]
    kalshi_price: float
    cross_market_implied: Optional[float]
    confidence: float


def parse_ladder_ticker(ticker: str) -> Optional[tuple[str, int]]:
    """Parse a ladder ticker like KXNFLWINS-IND-25B-T8 into
    (ladder_key, threshold). Returns None if not a ladder ticker.

    ladder_key is the prefix excluding the -T<k> suffix, e.g.,
    'KXNFLWINS-IND-25B'. All siblings of the same team-season share
    this prefix.

    Threshold is the integer after the final '-T'.
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


def _resolve_poly_lookup(
    ticker: str,
    poly_lookup: Optional[Union[dict, Callable[[str], Optional[float]]]],
) -> Optional[float]:
    """Resolve poly_lookup to a mid for this ticker. Lookup may be:
        - None (no Polymarket data available)
        - a dict mapping ticker -> mid
        - a callable taking ticker and returning a mid or None

    Returns None when no Polymarket mid is resolved (the filter then
    treats Track A1 as inactive and abstains).
    """
    if poly_lookup is None:
        return None
    if callable(poly_lookup):
        try:
            mid = poly_lookup(ticker)
        except Exception:
            return None
        return float(mid) if mid is not None else None
    if isinstance(poly_lookup, dict):
        mid = poly_lookup.get(ticker)
        return float(mid) if mid is not None else None
    return None


def _evaluate_polymarket_fade(
    ticker: str,
    kalshi_price: float,
    poly_lookup: Optional[Union[dict, Callable]],
    fade_threshold_cents: float,
) -> tuple[bool, Optional[float], float]:
    """Run Track A1. Returns (fires, poly_mid, confidence).

    fires=True means Track A1 would have skipped the trade.
    poly_mid is the Polymarket YES mid if available.
    confidence is the magnitude above threshold (capped at 1.0).
    """
    poly_mid = _resolve_poly_lookup(ticker, poly_lookup)
    if poly_mid is None:
        return False, None, 0.0
    divergence_cents = (kalshi_price - poly_mid) * 100.0
    if divergence_cents > fade_threshold_cents:
        # Confidence scales with how far above threshold; full at +25c
        # of divergence (i.e., very strong over-pricing signal).
        extra_cents = divergence_cents - fade_threshold_cents
        confidence = min(1.0, extra_cents / 18.0)
        return True, poly_mid, confidence
    return False, poly_mid, 0.0


def _evaluate_cross_market(
    ticker: str,
    kalshi_price: float,
    cross_market_data: Optional[dict],
    monotonicity_threshold_cents: float,
) -> tuple[bool, Optional[float], float]:
    """Run Track A2. Returns (fires, cross_market_implied, confidence).

    Logic: parse the target ticker as a ladder member. Look up the
    immediately-lower (T_{k-1}, ..., T_{k-N}) and immediately-higher
    (T_{k+1}, ...) siblings in the same team-season. Their prices
    should be monotonically non-increasing in threshold.

    Violation cases that trigger SKIP for the candidate ticker:
        (a) A lower-threshold sibling has price < kalshi_price by more
            than monotonicity_threshold_cents. Then EITHER the lower
            sibling is under-priced OR the candidate (higher
            threshold) is over-priced. Conservatively assume the
            candidate is over-priced.
        (b) The target's implied price from a monotone-decreasing fit
            on its siblings differs from kalshi_price by more than
            monotonicity_threshold_cents AND kalshi_price is HIGHER
            than the implied. Then candidate is over-priced relative
            to the curve.

    Otherwise: passes.

    cross_market_data shape: { ladder_key: { threshold: price, ... },
                               ... }
    e.g. { 'KXNFLWINS-IND-25B': {3: 0.96, 4: 0.86, 5: 0.86, 7: 0.37,
                                  8: 0.77, 9: 0.73, 10: 0.84} }
    Only the same-team-season siblings are referenced.

    cross_market_implied is the monotonic-isotonic-derived implied
    price at this threshold (the maximum of (prices at k' >= k); since
    P(>=k) >= P(>=k') for k'>k by monotonicity).
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

    # Normalize ladder values to (threshold, price) sorted asc by threshold.
    items = sorted(
        ((int(k), float(v)) for k, v in ladder.items() if v is not None),
        key=lambda kv: kv[0],
    )
    if len(items) < 2:
        return False, None, 0.0

    threshold_to_price = dict(items)
    # Drop the candidate's own threshold from the comparator set; we
    # are checking whether SIBLINGS imply a different price than the
    # candidate's posted mid.
    siblings = {k: p for k, p in threshold_to_price.items() if k != threshold}
    if not siblings:
        return False, None, 0.0

    # Direct violation check (a): any lower threshold whose price is
    # LESS THAN candidate by more than threshold? That is the inverted
    # case where a higher-k market is more expensive than a lower-k
    # market - structurally impossible if both are calibrated.
    lower_siblings = [(k, p) for k, p in siblings.items() if k < threshold]
    lower_violation_max_gap = 0.0
    for _, lower_price in lower_siblings:
        gap_cents = (kalshi_price - lower_price) * 100.0
        if gap_cents > monotonicity_threshold_cents:
            lower_violation_max_gap = max(lower_violation_max_gap, gap_cents)

    # Implied-from-siblings: for any candidate threshold k, by
    # monotonicity P(wins >= k) is bounded above by min(P(wins >= k')
    # for all k' < k) and bounded below by max(P(wins >= k') for all
    # k' > k). The non-trivial implied bound is the upper-bound from
    # lower-thresholds; the lower-bound from higher-thresholds is
    # mostly informational.
    upper_bound_implied: Optional[float] = None
    for k_lower, p_lower in lower_siblings:
        if upper_bound_implied is None or p_lower < upper_bound_implied:
            upper_bound_implied = p_lower

    higher_siblings = [(k, p) for k, p in siblings.items() if k > threshold]
    lower_bound_implied: Optional[float] = None
    for _, p_higher in higher_siblings:
        if lower_bound_implied is None or p_higher > lower_bound_implied:
            lower_bound_implied = p_higher

    # Build a single "implied" estimate: middle of the bounds where both
    # exist, else the available bound. This is used for reporting; the
    # fire decision is based on the strict bound violation.
    implied: Optional[float] = None
    if upper_bound_implied is not None and lower_bound_implied is not None:
        implied = (upper_bound_implied + lower_bound_implied) / 2.0
    elif upper_bound_implied is not None:
        implied = upper_bound_implied
    elif lower_bound_implied is not None:
        implied = lower_bound_implied

    # Fire condition: the candidate is HIGHER than the upper-bound
    # (from lower-threshold siblings) by more than the threshold. This
    # is the same condition as "exists a lower-threshold sibling at
    # price < kalshi_price - threshold" which is captured by
    # lower_violation_max_gap. We use the gap value for confidence.
    if lower_violation_max_gap > monotonicity_threshold_cents:
        # Confidence scales with gap above threshold (saturates at +25c).
        extra_cents = lower_violation_max_gap - monotonicity_threshold_cents
        confidence = min(1.0, extra_cents / 20.0)
        return True, implied, confidence

    # Lower-bound check: if the candidate is LOWER than the
    # lower-bound (from higher-threshold siblings) by more than the
    # threshold, the candidate is UNDER-priced. This is informationally
    # useful but does NOT fire a skip - the filter is a defensive
    # overlay and only acts on over-pricing signals. v1 can choose to
    # buy under-priced YES; we never add a buy that v1 wouldn't make.
    return False, implied, 0.0


def evaluate_market(
    ticker: str,
    kalshi_price: float,
    series_ticker: str,
    *,
    poly_lookup: Optional[Union[dict, Callable[[str], Optional[float]]]] = None,
    cross_market_data: Optional[dict] = None,
    fade_threshold_cents: float = FADE_THRESHOLD_CENTS_DEFAULT,
    monotonicity_threshold_cents: float = MONOTONICITY_THRESHOLD_CENTS_DEFAULT,
) -> FilterDecision:
    """Apply Track A1 + Track A2 to a single candidate market.

    Args:
        ticker: Kalshi market ticker, e.g. KXNFLWINS-IND-25B-T8.
        kalshi_price: Current Kalshi YES mid (or favorite_price). 0 to 1.
        series_ticker: The team-level series ticker (e.g.,
            KXNFLWINS-IND). Used for context; the ladder is matched
            via the parsed ticker prefix.
        poly_lookup: Optional dict or callable mapping ticker to
            Polymarket YES mid. None means Track A1 is inactive.
        cross_market_data: Optional dict mapping ladder_key (e.g.,
            'KXNFLWINS-IND-25B') to {threshold: price, ...}. None means
            Track A2 is inactive.
        fade_threshold_cents: Track A1 threshold in cents. Default 7c.
        monotonicity_threshold_cents: Track A2 threshold in cents.
            Default 5c.

    Returns:
        FilterDecision capturing whether to trade and why.
    """
    series_prefix = series_prefix_of(ticker)

    # Track A1
    a1_fires, poly_mid, a1_conf = _evaluate_polymarket_fade(
        ticker, kalshi_price, poly_lookup, fade_threshold_cents,
    )

    # Track A2 (only relevant for ladder series; for non-ladder series
    # the helper returns no-fire by parse failure)
    if is_ladder_series(series_prefix):
        a2_fires, cross_implied, a2_conf = _evaluate_cross_market(
            ticker, kalshi_price, cross_market_data, monotonicity_threshold_cents,
        )
    else:
        a2_fires, cross_implied, a2_conf = False, None, 0.0

    if a1_fires and a2_fires:
        return FilterDecision(
            should_trade=False,
            reason="both",
            poly_mid=poly_mid,
            kalshi_price=kalshi_price,
            cross_market_implied=cross_implied,
            confidence=max(a1_conf, a2_conf),
        )
    if a1_fires:
        return FilterDecision(
            should_trade=False,
            reason="polymarket_fade",
            poly_mid=poly_mid,
            kalshi_price=kalshi_price,
            cross_market_implied=cross_implied,
            confidence=a1_conf,
        )
    if a2_fires:
        return FilterDecision(
            should_trade=False,
            reason="monotonicity_violation",
            poly_mid=poly_mid,
            kalshi_price=kalshi_price,
            cross_market_implied=cross_implied,
            confidence=a2_conf,
        )

    # No fire. Distinguish:
    #   - poly_lookup was None (not attempted)
    #   - poly_lookup was provided but had no match for this ticker
    #   - both filters had inputs and neither disagreed enough
    poly_attempted = poly_lookup is not None
    if not poly_attempted and cross_implied is None:
        reason = "no_match"
    elif poly_mid is None and cross_implied is None:
        # poly_lookup was attempted but returned None; no ladder data
        reason = "no_poly_match"
    elif poly_mid is None:
        reason = "no_poly_match"
    else:
        reason = "pass"
    return FilterDecision(
        should_trade=True,
        reason=reason,
        poly_mid=poly_mid,
        kalshi_price=kalshi_price,
        cross_market_implied=cross_implied,
        confidence=0.0,
    )
