"""Sanity check: per category group, what fraction of resolved markets settle YES vs NO?

If World Events markets overwhelmingly resolve NO (e.g., "will X happen by date Y" types),
then post-resolution trade samples will show NO buyers winning more on average.
This is not a forward-deployable signal; it's a base-rate artifact of the question framing.
"""
from __future__ import annotations
import sys
from pathlib import Path

import duckdb

BASE = Path(r"C:/Users/SamJD/OneDrive/Desktop/AI Projects/Project Kalshi")
BECKER = BASE / "prediction-market-analysis"
TRADES_DIR = BECKER / "data" / "kalshi" / "trades"
MARKETS_DIR = BECKER / "data" / "kalshi" / "markets"

sys.path.insert(0, str(BECKER))
from src.analysis.kalshi.util.categories import CATEGORY_SQL, get_group

con = duckdb.connect(":memory:")
con.execute("PRAGMA threads=4")

# Restrict to markets that had any post-Oct-2024 trades
q = f"""
    WITH active_markets AS (
        SELECT DISTINCT m.ticker, m.event_ticker, m.result
        FROM '{MARKETS_DIR.as_posix()}/*.parquet' m
        WHERE m.status = 'finalized' AND m.result IN ('yes','no')
          AND m.ticker IN (
              SELECT DISTINCT ticker FROM '{TRADES_DIR.as_posix()}/*.parquet'
              WHERE created_time >= TIMESTAMP '2024-10-01'
          )
    )
    SELECT
        {CATEGORY_SQL.replace("event_ticker", "event_ticker")} AS category,
        COUNT(*) AS n_markets,
        SUM(CASE WHEN result = 'yes' THEN 1 ELSE 0 END) AS n_yes,
        SUM(CASE WHEN result = 'no' THEN 1 ELSE 0 END) AS n_no,
        AVG(CASE WHEN result = 'yes' THEN 1.0 ELSE 0.0 END) AS yes_frac
    FROM active_markets
    GROUP BY category
"""
df = con.execute(q).df()
df["group"] = df["category"].apply(get_group)

# Aggregate by group
agg = df.groupby("group", as_index=False).agg(
    n_markets=("n_markets", "sum"),
    n_yes=("n_yes", "sum"),
    n_no=("n_no", "sum"),
)
agg["yes_frac"] = agg["n_yes"] / agg["n_markets"]
agg = agg.sort_values("yes_frac")
print("Resolution balance by group (post-Oct-2024 trades on resolved markets):")
print(agg.to_string(index=False))
agg.to_csv(BASE / "research" / "v10a" / "05-resolution-balance-by-group.csv", index=False)

# Also breakdown by category for top NO-heavy categories
no_heavy = df[df["yes_frac"] < 0.35].sort_values("n_markets", ascending=False).head(30)
print("\nTop 30 NO-heavy categories (yes_frac < 0.35):")
print(no_heavy[["category", "group", "n_markets", "yes_frac"]].to_string(index=False))
