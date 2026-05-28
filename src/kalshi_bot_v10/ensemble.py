"""V10-B market-AI ensemble formula.

Per B2 Section 3 (AIA MarketLiquid formula, verbatim):
    p_v10 = 0.67 * orderbook_mid + 0.33 * p_llm_ensemble

The 0.67/0.33 weight is LOCKED. No post-hoc adjustment is permitted.
(B2 Section 8, rule 2: "No post-hoc weight tuning.")

The weight is also hardcoded here and accepts no command-line override.
"""

from __future__ import annotations


_W_MARKET: float = 0.67  # locked per B2 Section 3 / AIA MarketLiquid simplex regression


def compute_p_v10(
    orderbook_mid: float,
    p_llm: float,
    w_market: float = _W_MARKET,
) -> float:
    """Compute the V10-B ensemble probability.

    Args:
        orderbook_mid: Kalshi orderbook mid at forecast time (0 to 1).
        p_llm:         Mean Platt-scaled LLM ensemble output (0 to 1).
        w_market:      Market weight. Hard-coded to 0.67; parameter exists
                       for testing only. Never pass a different value in
                       production -- the methodology is locked.

    Returns:
        p_v10 in [0, 1].
    """
    if w_market != _W_MARKET:
        # Guard: warn if caller attempts to deviate from locked weight.
        # Does NOT raise; secondary-metric runs at other weights are permitted
        # informationally (B2 Section 6) but must not change the verdict.
        import warnings
        warnings.warn(
            f"w_market={w_market} deviates from locked value {_W_MARKET}."
            " This result is informational only and cannot change the verdict.",
            stacklevel=2,
        )

    w_llm = 1.0 - w_market
    return w_market * orderbook_mid + w_llm * p_llm
