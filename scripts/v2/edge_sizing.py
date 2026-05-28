"""Compute the minimum cross-platform arbitrage spread that is profitable at our scale.

Models a single-leg arb: BUY YES on platform A at price p_a, SELL the equivalent
NO exposure on platform B at price (1 - p_b). Risk-free payout = $1.00 - (p_a + p_b)
per pair of contracts, minus fees on both sides.

Kalshi fees: ceil(7 * p * (1-p)) cents per contract taker, ceil(1.75 * p * (1-p)) cents maker.
Polymarket sports taker: 0.3% on notional (gas effectively free via relayer).
Polymarket US (QCEX): unknown precise fee; rumored 0.01 to 0.04% per trade.

Outputs the minimum gross spread (Kalshi YES + Polymarket NO - $1.00) required to
break even, for several scales and price levels.

NOTE: This script does NOT touch live capital and does NOT place orders.
It is a worksheet that prints to stdout. No external calls.
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Scenario:
    contracts: int
    kalshi_price: float  # YES price on Kalshi
    poly_price: float  # YES price on Polymarket equivalent (1 - poly_no_price)
    kalshi_taker: bool = True
    poly_sports_rate: float = 0.003  # 0.3% offshore taker
    poly_us_rate: float = 0.0004  # 0.04% rumored upper bound for Polymarket US


def kalshi_fee_per_contract(price: float, taker: bool) -> float:
    """Kalshi per-contract fee in dollars."""
    rate = 0.07 if taker else 0.0175
    raw_cents = rate * price * (1 - price) * 100.0  # in cents
    return math.ceil(raw_cents) / 100.0


def evaluate(s: Scenario) -> dict:
    """Compute break-even economics. Assume YES-on-Kalshi + NO-on-Polymarket arb."""
    # If we buy YES at p_a on Kalshi and YES at p_b on Polymarket (i.e., NO at 1-p_b),
    # gross spread = (1.0 - p_a - (1 - p_b)) = p_b - p_a per contract pair? No - let
    # me restate. The classic arb: YES + NO costs sum to less than $1.00. We buy YES
    # on the cheaper platform for p_yes, and NO on the other for p_no. Total cost is
    # p_yes + p_no per pair, payout is guaranteed $1.00 either way.
    #
    # Treat kalshi_price as YES price we BUY on Kalshi, poly_price as YES price on
    # Polymarket - so we SELL YES (= buy NO at 1 - poly_price) on Polymarket. Cost:
    #   leg_a = kalshi_price                         # Kalshi YES cost per contract
    #   leg_b = 1.0 - poly_price                    # Polymarket NO cost per contract
    # gross_cost_per_pair = leg_a + leg_b
    # gross_pnl_per_pair = 1.00 - gross_cost_per_pair (RISK-FREE if matched)
    leg_a = s.kalshi_price
    leg_b = 1.0 - s.poly_price
    gross_pnl_per_pair = 1.0 - (leg_a + leg_b)

    # Fees: Kalshi per-contract by formula. Polymarket: rate * notional.
    kalshi_fee_per = kalshi_fee_per_contract(s.kalshi_price, s.kalshi_taker)
    poly_fee_per = s.poly_sports_rate * (1.0 - s.poly_price)  # NO notional = 1 - p
    poly_us_fee_per = s.poly_us_rate * (1.0 - s.poly_price)

    total_fee_offshore = kalshi_fee_per + poly_fee_per
    total_fee_us = kalshi_fee_per + poly_us_fee_per

    net_pnl_offshore = gross_pnl_per_pair - total_fee_offshore
    net_pnl_us = gross_pnl_per_pair - total_fee_us

    min_spread_to_breakeven_offshore = total_fee_offshore  # gross spread = fees
    min_spread_to_breakeven_us = total_fee_us

    return {
        "contracts": s.contracts,
        "kalshi_price": s.kalshi_price,
        "poly_price": s.poly_price,
        "gross_cost_per_pair": leg_a + leg_b,
        "gross_pnl_per_pair_cents": gross_pnl_per_pair * 100,
        "kalshi_fee_per_contract_cents": kalshi_fee_per * 100,
        "poly_offshore_fee_per_contract_cents": poly_fee_per * 100,
        "poly_us_fee_per_contract_cents": poly_us_fee_per * 100,
        "min_breakeven_spread_offshore_cents": min_spread_to_breakeven_offshore * 100,
        "min_breakeven_spread_us_cents": min_spread_to_breakeven_us * 100,
        "net_pnl_total_offshore_dollars": net_pnl_offshore * s.contracts,
        "net_pnl_total_us_dollars": net_pnl_us * s.contracts,
    }


def main() -> None:
    print("Cross-platform arbitrage break-even worksheet")
    print("Assumes single arbitrage opportunity capture; matched fills both legs.")
    print("Kalshi taker assumed (worst case); Polymarket offshore sports rate 0.3%.")
    print("=" * 86)

    # Three price levels x three sizes
    price_levels = [0.30, 0.50, 0.70]
    sizes = [1, 10, 100]

    for kp in price_levels:
        for n in sizes:
            # Probe minimum break-even: try poly_price = kp + epsilon until net > 0.
            # poly_price > kp means cross-platform mispricing where Polymarket has
            # higher YES price than Kalshi. The arb is: BUY YES on Kalshi, SELL YES
            # (= BUY NO) on Polymarket. The bigger the gap, the more profit.
            kalshi_fee_c = kalshi_fee_per_contract(kp, taker=True) * 100
            # find smallest poly_price > kp such that net pnl >= 0:
            for cents_gap in range(1, 30):
                pp = kp + cents_gap / 100.0
                if pp >= 1.0:
                    break
                s = Scenario(contracts=n, kalshi_price=kp, poly_price=pp)
                r = evaluate(s)
                if r["net_pnl_total_offshore_dollars"] >= 0:
                    break_even_gap = cents_gap
                    break
            else:
                break_even_gap = None

            print(f"price=$0.{int(kp*100):02d}  n={n:3d} contracts:")
            print(
                f"  Kalshi taker fee per: {kalshi_fee_c:.2f}c    "
                f"Poly offshore fee per (at p=0.{int(kp*100):02d}): "
                f"{0.003 * (1-kp) * 100:.3f}c"
            )
            if break_even_gap is not None:
                # Re-evaluate at break-even
                s = Scenario(contracts=n, kalshi_price=kp, poly_price=kp + break_even_gap/100)
                r = evaluate(s)
                print(
                    f"  Min profitable spread: {break_even_gap}c gross  "
                    f"-> net P&L total: ${r['net_pnl_total_offshore_dollars']:.4f}"
                )
            else:
                print("  No profitable spread under 30c gap.")
            print()

    # Headline: minimum spread at our typical $0.30 to $0.70 range
    print("=" * 86)
    print("Summary minimum profitable gross spreads (offshore Polymarket, Kalshi taker):")
    print(f"{'Price':<10}{'Kalshi fee':<14}{'Poly fee':<14}{'Min spread':<14}")
    for kp in price_levels:
        kfee = kalshi_fee_per_contract(kp, taker=True) * 100
        pfee = 0.003 * (1 - kp) * 100
        min_spread = kfee + pfee
        print(f"${kp:<9.2f}{kfee:<14.2f}{pfee:<14.3f}{min_spread:<14.2f}")

    print()
    print("Same with Kalshi MAKER (passive limit) fees:")
    print(f"{'Price':<10}{'Kalshi fee':<14}{'Poly fee':<14}{'Min spread':<14}")
    for kp in price_levels:
        kfee = kalshi_fee_per_contract(kp, taker=False) * 100
        pfee = 0.003 * (1 - kp) * 100
        min_spread = kfee + pfee
        print(f"${kp:<9.2f}{kfee:<14.2f}{pfee:<14.3f}{min_spread:<14.2f}")


if __name__ == "__main__":
    main()
