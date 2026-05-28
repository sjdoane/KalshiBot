"""Phase 1 / Agent V4-A: compute v1-universe-weighted Polymarket coverage.

Combines:
  - data/v4/v1_universe_series_table.parquet (per-series counts in 3 sources)
  - data/v4/series_coverage_fraction.parquet (per-series MATCH/PARTIAL/NO MATCH + fraction)
  - data/v4/live_orders_classified.parquet (direct labels for v1's current live tickers)

Outputs the headline TA1 metric: weighted match rate on v1's actual live
attempted-orders distribution. This is the binding number for go/pivot.

Three views computed:
  (a) Weighted by v1 LIVE attempted-orders (the most binding measure)
  (b) Weighted by v1 BACKTEST eligible markets
  (c) Weighted by v3 broader inventory eligible markets
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_V4 = REPO_ROOT / "data" / "v4"


def compute_weighted(universe: pd.DataFrame, coverage: pd.DataFrame, weight_col: str) -> dict:
    df = universe.merge(coverage, on="series_prefix", how="left")
    df["coverage_class"] = df["coverage_class"].fillna("NO MATCH")
    df["matched_fraction"] = df["matched_fraction"].fillna(0.0)
    df[weight_col] = df[weight_col].fillna(0).astype(float)
    df["matched_count"] = df[weight_col] * df["matched_fraction"]
    total = df[weight_col].sum()
    matched = df["matched_count"].sum()
    matched_match_only = (df[df["coverage_class"] == "MATCH"][weight_col] * 1.0).sum()
    matched_partial = (df[df["coverage_class"] == "PARTIAL"][weight_col] * df[df["coverage_class"] == "PARTIAL"]["matched_fraction"]).sum()
    return {
        "weight_col": weight_col,
        "total_markets": int(total),
        "weighted_matched": float(matched),
        "match_rate": (matched / total) if total > 0 else 0.0,
        "matched_full_only": float(matched_match_only),
        "matched_partial_contrib": float(matched_partial),
        "match_only_rate": (matched_match_only / total) if total > 0 else 0.0,
    }


def main() -> None:
    universe = pd.read_parquet(DATA_V4 / "v1_universe_series_table.parquet")
    coverage = pd.read_parquet(DATA_V4 / "series_coverage_fraction.parquet")

    # View A: v1 live attempted orders
    A = compute_weighted(universe, coverage, "v1_live_all_orders")
    # View A2: v1 live acked orders
    A2 = compute_weighted(universe, coverage, "v1_live_acked_orders")
    # View B: v1 backtest eligible
    B = compute_weighted(universe, coverage, "v1_backtest_eligible")
    # View C: v3 broader inventory eligible
    C = compute_weighted(universe, coverage, "v3_inventory_eligible")

    print()
    for name, res in [("v1 LIVE attempted orders", A), ("v1 LIVE acked orders", A2),
                      ("v1 BACKTEST eligible", B), ("v3 INVENTORY eligible", C)]:
        print(f"\n=== Weighted by {name} ===")
        print(f"  total markets in this universe : {res['total_markets']}")
        print(f"  weighted matched               : {res['weighted_matched']:.1f}")
        print(f"  match rate (incl PARTIAL frac) : {res['match_rate']:.1%}")
        print(f"  matched full only              : {res['matched_full_only']:.0f}")
        print(f"  matched partial contrib        : {res['matched_partial_contrib']:.1f}")
        print(f"  MATCH-only rate (strict)       : {res['match_only_rate']:.1%}")

    # Also compute the ABSOLUTE live-orders binding coverage from the manual classification
    cls = pd.read_parquet(DATA_V4 / "live_orders_classified.parquet")
    n = len(cls)
    confirmed = (cls["match_status"] == "CONFIRMED").sum()
    partial = (cls["match_status"] == "PARTIAL").sum()
    event_future = (cls["match_status"] == "EVENT_FUTURE").sum()
    no_match = (cls["match_status"] == "NO MATCH").sum()
    print()
    print("=== ABSOLUTE manual-audit classification of v1 LIVE distinct tickers (n=25) ===")
    print(f"  CONFIRMED (filter can act now)    : {confirmed}")
    print(f"  PARTIAL (event match, threshold/side differs): {partial}")
    print(f"  EVENT_FUTURE (will list later)    : {event_future}")
    print(f"  NO MATCH (structural absence)     : {no_match}")
    print(f"  total                             : {n}")
    print()
    # The binding TA1 metric: today, on v1's current live universe, how many
    # markets does the Polymarket-fade-filter have a live price-comparable
    # counterpart for? Conservative count: CONFIRMED + 50% of PARTIAL.
    actionable_now_rate = (confirmed + 0.5 * partial) / n
    print(f"  binding TA1 (CONFIRMED + 50% PARTIAL) / n = {actionable_now_rate:.1%}")
    # Optimistic: include EVENT_FUTURE at 75% (they'll list later)
    optimistic = (confirmed + 0.7 * partial + 0.75 * event_future) / n
    print(f"  optimistic (incl EVENT_FUTURE @ 0.75): {optimistic:.1%}")


if __name__ == "__main__":
    main()
