"""Phase 2 sanity-inspector for the politics dataset.

Reports row counts, date range, distributions, and key sanity metrics so
the operator can confirm the dataset matches expectations BEFORE running
the gate. This is the analog of `inspect_markets.py` from Phase 1.

Run after `build_dataset.py` produces
`data/processed/politics_phase2_dataset.parquet`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from kalshi_bot.analysis.gate_phase2 import (
    LAST_TEST_END,
    MID_BAND_LOWER,
    MID_BAND_UPPER,
    PRICE_CONDITIONAL_NARROW,
    _eligibility_mask,
)

DATASET_PATH = Path("data/processed/politics_phase2_dataset.parquet")


def main() -> int:
    if not DATASET_PATH.exists():
        print(f"ERROR: dataset missing at {DATASET_PATH}")
        return 1

    df = pd.read_parquet(DATASET_PATH)
    df["market_open_time"] = pd.to_datetime(df["market_open_time"], utc=True)
    df["market_close_time"] = pd.to_datetime(df["market_close_time"], utc=True)
    print(f"=== Phase 2 Dataset Inspection ({DATASET_PATH}) ===\n")

    # Basic shape
    print(f"  total rows:                  {len(df)}")
    print(f"  unique series:               {df['series_ticker'].nunique()}")
    print(f"  unique events:               {df['event_ticker'].nunique()}")
    print(f"  date_min (close_time):       {df['market_close_time'].min()}")
    print(f"  date_max (close_time):       {df['market_close_time'].max()}")
    in_corpus = df["market_close_time"] <= LAST_TEST_END
    print(f"  rows in corpus (<= LAST):    {int(in_corpus.sum())}")
    out_of_time = (~in_corpus).sum()
    print(f"  rows past LAST_TEST_END:     {int(out_of_time)} (should be 0)")

    # Outcome distribution
    print()
    print(f"  outcome=1 rate:              {df['outcome'].mean():.4f}")
    print(f"  outcome counts:              YES={int((df['outcome']==1).sum())} "
          f"NO={int((df['outcome']==0).sum())}")

    # Federal-election composition
    print()
    print(f"  is_federal_election rate:    {df['is_federal_election_market'].mean():.4f}")

    # Volume / liquidity
    print()
    print(f"  median n_trades_in_window:        {int(df['n_trades_in_window'].median())}")
    print(f"  median n_small_trades_in_window:  {int(df['n_small_trades_in_window'].median())}")
    print(f"  pct markets with >=20 trades:     "
          f"{(df['n_trades_in_window'] >= 20).mean():.4f}")
    print(f"  pct markets with small-trade VWAP defined: "
          f"{df['mid_price_at_T_small'].notna().mean():.4f}")

    # Mid-price distribution
    print()
    p = df["mid_price_at_T_small"].dropna()
    print(f"  mid_small p05/p25/p50/p75/p95: "
          f"{p.quantile(0.05):.3f} / {p.quantile(0.25):.3f} / "
          f"{p.quantile(0.50):.3f} / {p.quantile(0.75):.3f} / {p.quantile(0.95):.3f}")
    in_lower = (p >= MID_BAND_LOWER[0]) & (p <= MID_BAND_LOWER[1])
    in_upper = (p >= MID_BAND_UPPER[0]) & (p <= MID_BAND_UPPER[1])
    print(f"  pct in mid-band [{MID_BAND_LOWER[0]:.2f}, {MID_BAND_LOWER[1]:.2f}]: "
          f"{in_lower.mean():.4f}")
    print(f"  pct in mid-band [{MID_BAND_UPPER[0]:.2f}, {MID_BAND_UPPER[1]:.2f}]: "
          f"{in_upper.mean():.4f}")
    print(f"  pct in narrow [{PRICE_CONDITIONAL_NARROW[0]:.2f}, {PRICE_CONDITIONAL_NARROW[1]:.2f}]: "
          f"{((p >= PRICE_CONDITIONAL_NARROW[0]) & (p <= PRICE_CONDITIONAL_NARROW[1])).mean():.4f}")

    # Eligibility analysis (apply Section 4 filters to whole dataset)
    prices = df["mid_price_at_T_small"].to_numpy()
    flow = df["one_sided_flow_pct"].to_numpy()
    eligible = _eligibility_mask(prices, flow)
    print()
    print(f"  total eligible (Section 4): {int(eligible.sum())} "
          f"({eligible.mean():.4f} of corpus)")

    # Year / monthly distribution
    df["year_month"] = df["market_close_time"].dt.to_period("M")
    monthly = df.groupby("year_month").size()
    print()
    print(f"  markets/month range:       min={monthly.min()} median={int(monthly.median())} "
          f"max={monthly.max()}")

    # Top 20 most-traded series for the manual top-50 audit
    print()
    series_volume = df.groupby("series_ticker")["n_trades_in_window"].sum().sort_values(ascending=False)
    print("  top 20 series by total in-window trades:")
    for series, n in series_volume.head(20).items():
        fed_count = int(df[df["series_ticker"] == series]["is_federal_election_market"].sum())
        total = int((df["series_ticker"] == series).sum())
        print(f"    {series:30s} n_trades_in_window={int(n):8d} "
              f"n_markets={total:4d} fed_tagged={fed_count}/{total}")

    # Lifetime distribution (for the lifetime-straddle filter expectation)
    lifetime = (df["market_close_time"] - df["market_open_time"]).dt.days
    print()
    print(f"  market lifetime (days) p05/p50/p95: "
          f"{lifetime.quantile(0.05):.1f} / {lifetime.quantile(0.50):.1f} / "
          f"{lifetime.quantile(0.95):.1f}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
