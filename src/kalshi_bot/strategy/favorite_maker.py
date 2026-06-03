"""Strategy B: Deep-Favorite YES Maker.

Pure heuristic strategy (no calibration model):
- Identify settled sports markets where YES price >= FAVORITE_THRESHOLD
  (default 0.70). At these prices, the market is pricing the YES side
  as a "moderate-to-heavy favorite" (70-99% implied probability).
- Empirically (from Round 4 sports dataset): these markets resolve YES
  at ~97% rate, meaning the market UNDERPRICES the favorite by several
  pp.
- Buy YES at the market price as maker. Hold to settlement.
- Realized P&L per contract = outcome - market_price - round_trip_fee -
  slippage.

Round 4 backtest:
- 70/30 chronological holdout, n=33 eligible test markets
- Mean realized P&L: +5.13pp
- Median: +1.15pp
- SD: 7.78pp
- Hit rate: 63.6% (positive P&L per trade)
- Bootstrap 95% CI: [+2.60pp, +7.99pp] - EXCLUDES ZERO

Literature support:
- Burgi favorite-longshot bias: favorites systematically underpriced,
  longshots overpriced. >=50c subpopulation maker +2.6% pre-fee per
  Burgi. Our >=70c slice gives stronger net edge consistent with this.
- Becker maker advantage post-2024 sign flip. +1.12% average maker
  return; targeted favorite slice exceeds.
- Whelan equilibrium: makers structurally advantaged.

This strategy is SIMPLER and more EMPIRICALLY validated than the
compression-maker Strategy A (which failed C6/C7 due to small sample).
No isotonic model required.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from kalshi_bot.analysis.metrics import kalshi_maker_fee_per_contract

# Locked parameters per Round 4 favorite_maker proposal, revised per
# Round 4 critic finding (lower empirical_yes_rate from 0.97 to 0.95,
# cap entries at YES <= 0.95 since 96-99c data is thin and break-even
# is too close at those prices).
FAVORITE_THRESHOLD = 0.70
FAVORITE_UPPER_CAP = 0.95
EMPIRICAL_YES_RATE_DEFAULT = 0.95  # was 0.97; conservative per critic
SLIPPAGE_ALLOWANCE = 0.015

# v18 finding (research/v18/02 + 06): the favorite-maker edge concentrates in
# the MODERATE-favorite band [0.70, 0.86) (~+8% net) and roughly halves in the
# heavy band [0.86, 0.95] (~+3-4%); validated cross-sport (MLB/ATP/WTA) on both
# the YES (favorite) and NO (underdog) sides. This boundary splits those bands.
FAVORITE_SWEET_UPPER = 0.86


@dataclass(frozen=True)
class FavoriteTradeDecision:
    side: str  # always "yes" for this strategy
    target_price: float  # market mid (we maker-buy YES at the bid)
    expected_net_edge: float  # expected per-contract net P&L


def is_eligible(yes_price: float, *,
                lower: float = FAVORITE_THRESHOLD,
                upper: float = FAVORITE_UPPER_CAP) -> bool:
    """Eligible: YES price in [lower, upper] band. Upper cap of 0.95 is
    per critic finding: 96-99c data is thin and break-even-after-fees
    is too close at those prices."""
    return lower <= yes_price <= upper


def round_trip_maker_fee(price: float) -> float:
    return 2.0 * kalshi_maker_fee_per_contract(price)


def expected_net_edge(yes_price: float,
                      *,
                      empirical_yes_rate: float = EMPIRICAL_YES_RATE_DEFAULT) -> float:
    """Expected per-contract net P&L assuming the empirical YES-resolution
    rate at this price band holds. Conservatively uses 0.95 per critic
    finding (was 0.97 originally; 97% was the 70-99c sample rate but
    margin-of-safety prefers 0.95)."""
    gross = empirical_yes_rate - yes_price
    fee = round_trip_maker_fee(yes_price)
    return gross - fee - SLIPPAGE_ALLOWANCE


def decide(yes_price: float) -> FavoriteTradeDecision | None:
    """Return a trade decision if eligible, else None."""
    if not is_eligible(yes_price):
        return None
    net = expected_net_edge(yes_price)
    if net <= 0:
        return None  # net negative at this exact price; skip
    return FavoriteTradeDecision(
        side="yes",
        target_price=yes_price,
        expected_net_edge=net,
    )


@dataclass(frozen=True)
class FavoriteSideDecision:
    """A decision to maker-buy the FAVORITE side of a market, whichever side it
    is framed on. side is "yes" (favorite is the YES side, the classic v1 case)
    or "no" (the market is framed as the underdog's YES, so the favorite is the
    NO side; v18 finding 06). target_price is the executable maker price we rest
    at on that side; fav_price == target_price (the favorite-side price used for
    the band/edge)."""

    side: str
    target_price: float
    fav_price: float
    expected_net_edge: float
    fav_ask: float = 1.0  # the favorite-side ASK (yes_ask for YES, 1-yes_bid for
    # NO); the step-in-front maker cap. Defaults to 1.0 (no cap) for back-compat.


def decide_favorite_side(
    yes_bid: float,
    yes_ask: float,
    *,
    lower: float = FAVORITE_THRESHOLD,
    upper: float = FAVORITE_UPPER_CAP,
    empirical_yes_rate: float = EMPIRICAL_YES_RATE_DEFAULT,
) -> FavoriteSideDecision | None:
    """Decide whether to maker-buy the favorite side of a market.

    The favorite-longshot bias is symmetric (v18 finding 06): favorites are
    underpriced on whichever side they are framed. For one binary market only ONE
    side can be the favorite (>= lower), since yes_bid <= yes_ask implies the YES
    bid and the NO bid (1 - yes_ask) cannot both be >= 0.70.

    - YES favorite: rest a YES maker bid at the best yes_bid, if yes_bid is in
      [lower, upper].
    - NO favorite (underdog-framed market): rest a NO maker bid at the best
      no_bid = 1 - yes_ask, if that is in [lower, upper].

    Returns the FavoriteSideDecision for the eligible side (net edge > 0), else
    None. expected_net_edge uses the same favorite-longshot formula for both
    sides (the bias is symmetric), keyed on the favorite-side price.
    """
    if lower <= yes_bid <= upper:
        net = expected_net_edge(yes_bid, empirical_yes_rate=empirical_yes_rate)
        if net > 0:
            return FavoriteSideDecision("yes", yes_bid, yes_bid, net, fav_ask=yes_ask)
        return None
    no_bid = round(1.0 - yes_ask, 4)
    no_ask = round(1.0 - yes_bid, 4)
    if lower <= no_bid <= upper:
        net = expected_net_edge(no_bid, empirical_yes_rate=empirical_yes_rate)
        if net > 0:
            return FavoriteSideDecision("no", no_bid, no_bid, net, fav_ask=no_ask)
    return None


def step_in_front(
    decision: FavoriteSideDecision,
    *,
    tick: float = 0.01,
    min_net_edge: float = 0.0,
    upper: float = FAVORITE_UPPER_CAP,
    empirical_yes_rate: float = EMPIRICAL_YES_RATE_DEFAULT,
) -> FavoriteSideDecision:
    """Return a decision that rests one `tick` IN FRONT of the best bid, to be
    the best bid so sellers fill v1 first (a fill-rate boost). The stepped price
    is on the favorite's OWN side (yes_price for a YES bid, no_price for a NO
    bid). It stays a MAKER (capped strictly below the favorite-side ask) and is
    re-checked for edge: if there is no room (spread <= tick), the stepped price
    would exceed the upper cap, or the stepped edge falls below min_net_edge,
    the ORIGINAL decision is returned unchanged (place at the best bid, not a
    worse price). Trades ~1 tick of the +5-8% edge for a large fill-rate gain.

    Maker safety relies on Kalshi prices being integer cents (yes_bid/yes_ask
    from the `*_dollars` fields are always multiples of 0.01), so the stepped
    2dp price compared against the side ask never lands above it via rounding.
    Note: stepping can move a bid from the LOW band [0.70,0.86) into the heavy
    band (e.g. 0.85 -> 0.86), so downstream band sizing keys on the stepped
    (post-step) price; this is intended (the bid IS at the heavy-band price now).
    """
    stepped = round(decision.fav_price + tick, 2)
    # Must stay strictly below the favorite-side ask to remain a maker, and
    # within the eligible favorite band.
    if stepped >= decision.fav_ask or stepped > upper:
        return decision
    net = expected_net_edge(stepped, empirical_yes_rate=empirical_yes_rate)
    if net < min_net_edge:
        return decision
    return FavoriteSideDecision(
        decision.side, stepped, stepped, net, fav_ask=decision.fav_ask
    )


def band_size_multiplier(
    fav_price: float, *, m_low: float = 1.3, m_high: float = 0.8
) -> float:
    """Return-on-stake size multiplier by favorite-price band (v18 finding): the
    LOW band [0.70, 0.86) carries roughly 2x the edge of the heavy band
    [0.86, 0.95], so size LOW bids larger and heavy bids smaller. Returns 0.0 for
    a price outside the eligible favorite band. Defaults are conservative
    (1.3 / 0.8); the caller may override from env. Since v1 is capital-idle, the
    larger LOW size does not crowd out the still-positive heavy fills."""
    if not is_eligible(fav_price):
        return 0.0
    return m_low if fav_price < FAVORITE_SWEET_UPPER else m_high


def realized_pnl_per_contract(
    yes_price: float, outcome: int,
    *, slippage: float = SLIPPAGE_ALLOWANCE,
) -> float:
    """Realized P&L for a single market we bought YES at as maker.
    outcome in {0, 1}."""
    if not is_eligible(yes_price):
        return 0.0
    gross = outcome - yes_price
    fee = round_trip_maker_fee(yes_price)
    return gross - fee - slippage


def realized_pnl_array(
    yes_prices: np.ndarray, outcomes: np.ndarray,
) -> np.ndarray:
    """Vectorized realized P&L for an array of (price, outcome) pairs.
    Markets failing eligibility are EXCLUDED (not zero-filled).
    Eligibility is [FAVORITE_THRESHOLD, FAVORITE_UPPER_CAP]."""
    yes_prices = np.asarray(yes_prices, dtype=float)
    outcomes = np.asarray(outcomes, dtype=int)
    mask = (yes_prices >= FAVORITE_THRESHOLD) & (yes_prices <= FAVORITE_UPPER_CAP)
    yp = yes_prices[mask]
    out = outcomes[mask]
    gross = out - yp
    fees = np.array([round_trip_maker_fee(float(p)) for p in yp])
    return gross - fees - SLIPPAGE_ALLOWANCE


def compute_dynamic_max_concurrent(
    total_bankroll_usd: float,
    *,
    per_trade_max_usd: float = FAVORITE_UPPER_CAP,
    floor: int = 1,
) -> int:
    """Derive max_concurrent from current total bankroll.

    Returns floor(total_bankroll / per_trade_max), clamped to >= `floor`.

    total_bankroll = cash_balance + open_positions_notional. As wins
    accumulate (bankroll grows) the cap rises; as losses occur (bankroll
    shrinks) it falls. The result is the largest number of simultaneous
    positions the bankroll can fund at worst-case price.

    Use `floor=0` to allow the cap to drop to zero (bot stops placing
    new orders entirely when bankroll < per_trade). Default `floor=1`
    keeps at least one slot eligible even when bankroll is very low,
    which matches v1's "place one contract per cycle" baseline.
    """
    if per_trade_max_usd <= 0:
        return floor
    raw = int(total_bankroll_usd / per_trade_max_usd)
    return max(floor, raw)
