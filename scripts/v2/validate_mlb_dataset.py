"""Quick validation + spot-check script for the joined MLB dataset.

Run as:
    uv run python -m scripts.v2.validate_mlb_dataset

Reads data/v2/joined_mlb_dataset.parquet and prints:
- Row counts, date range, league summary
- Outcome rate (all, eligible)
- Sample of 5 random rows with the math we can manually verify
- Null counts per feature
- Calibration table (predicted vs realized) bucketed by favorite_price
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
DATASET = REPO_ROOT / "data" / "v2" / "joined_mlb_dataset.parquet"
DROPPED = REPO_ROOT / "data" / "v2" / "joined_mlb_dataset_dropped.parquet"


def main() -> int:
    df = pd.read_parquet(DATASET)
    print("=" * 60)
    print(f"Joined MLB dataset @ {DATASET}")
    print("=" * 60)
    print(f"Rows:                   {len(df)}")
    print(f"Columns:                {len(df.columns)}")
    print(f"Game date range:        {df['game_date'].min()} to {df['game_date'].max()}")
    print(f"Open-time range:        {df['open_time'].min()} to {df['open_time'].max()}")
    print(f"Outcome rate (all):     {df['outcome'].mean():.4f}")
    elig = df[df["is_strategy_b_eligible"]]
    print(f"Eligible rows:          {len(elig)}")
    if len(elig) > 0:
        print(f"Outcome rate (eligible): {elig['outcome'].mean():.4f}")
        print(f"Mean favorite_price (eligible): {elig['favorite_price'].mean():.4f}")
        edge = elig["outcome"].mean() - elig["favorite_price"].mean()
        print(f"Realized minus implied (pp):    {edge * 100:.2f}")

    # Dropped rows audit
    if DROPPED.exists():
        dropped = pd.read_parquet(DROPPED)
        print(f"\nDropped: {len(dropped)} rows")
        if "drop_reason" in dropped.columns:
            print(dropped["drop_reason"].value_counts())

    # Calibration table
    print("\n--- Calibration: outcome rate by favorite_price bucket (eligible) ---")
    if len(elig) > 0:
        buckets = [0.70, 0.75, 0.80, 0.85, 0.90, 0.95]
        elig = elig.copy()
        elig["price_bucket"] = pd.cut(elig["favorite_price"], buckets, include_lowest=True)
        table = elig.groupby("price_bucket", observed=True).agg(
            n=("outcome", "size"),
            outcome_rate=("outcome", "mean"),
            mean_price=("favorite_price", "mean"),
        )
        table["edge_pp"] = (table["outcome_rate"] - table["mean_price"]) * 100
        print(table.to_string())

    # 5 random spot-check rows
    print("\n--- 5 random spot-check rows ---")
    if len(df) >= 5:
        sample = df.sample(5, random_state=42)
        cols = [
            "ticker", "game_date", "favorite_team_abbrev", "underdog_team_abbrev",
            "is_favorite_home", "favorite_price", "vwap_n_trades_in_window",
            "outcome", "score_winning", "score_losing", "winning_team",
            "fav_win_pct", "dog_win_pct", "fav_pyth_wpct", "dog_pyth_wpct",
            "is_strategy_b_eligible",
        ]
        for _, row in sample.iterrows():
            print()
            print(f"ticker:          {row['ticker']}")
            print(f"game_date:       {row['game_date']}")
            print(f"favorite:        {row['favorite_team_abbrev']} (home={row['is_favorite_home']})")
            print(f"underdog:        {row['underdog_team_abbrev']}")
            print(f"favorite_price:  {row['favorite_price']:.4f}")
            print(f"vwap n_trades:   {row['vwap_n_trades_in_window']:.0f}")
            print(f"outcome:         {row['outcome']} ({row['winning_team']} won {row['score_winning']:.0f}-{row['score_losing']:.0f})")
            print(f"fav_win_pct:     {row['fav_win_pct']:.4f}")
            print(f"dog_win_pct:     {row['dog_win_pct']:.4f}")
            print(f"fav_pyth_wpct:   {row['fav_pyth_wpct']:.4f}")
            print(f"dog_pyth_wpct:   {row['dog_pyth_wpct']:.4f}")
            print(f"days_rest:       {row.get('days_rest')}")
            print(f"h2h_wpct (fav):  {row.get('h2h_wpct')} (n={row.get('h2h_n')})")
            print(f"eligible:        {row['is_strategy_b_eligible']}")

    # Null counts
    print("\n--- Null counts per feature ---")
    feat_cols = [
        "favorite_price", "vwap_n_trades_in_window", "one_sided_flow_pct",
        "fav_games_played", "fav_win_pct", "fav_pyth_wpct",
        "fav_run_diff_pg", "fav_recent_form_wpct", "fav_home_wpct",
        "fav_away_wpct", "fav_vs_500_wpct",
        "dog_games_played", "dog_win_pct", "dog_pyth_wpct",
        "dog_run_diff_pg", "dog_recent_form_wpct",
        "wpct_diff", "pyth_diff", "run_diff_diff",
        "h2h_wpct", "h2h_n", "days_rest", "is_home",
    ]
    for c in feat_cols:
        if c in df.columns:
            n_null = df[c].isna().sum()
            pct = n_null / len(df) * 100 if len(df) > 0 else 0
            print(f"  {c:30s} {n_null:6d}  ({pct:.1f}%)")

    # Bottom: schema dump
    print("\n--- Schema ---")
    for c, dt in df.dtypes.items():
        print(f"  {c:35s} {dt}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
