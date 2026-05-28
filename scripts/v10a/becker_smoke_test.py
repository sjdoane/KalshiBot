"""Smoke test: count post-Oct-2024 resolved trades, verify schema."""
from __future__ import annotations
import sys
import time
from pathlib import Path

import duckdb

BASE = Path(r"C:/Users/SamJD/OneDrive/Desktop/AI Projects/Project Kalshi")
BECKER = BASE / "prediction-market-analysis"
TRADES_DIR = BECKER / "data" / "kalshi" / "trades"
MARKETS_DIR = BECKER / "data" / "kalshi" / "markets"

sys.path.insert(0, str(BECKER))

con = duckdb.connect(":memory:")
con.execute("PRAGMA threads=4")

print("[smoke] checking markets schema")
m_cols = con.execute(f"DESCRIBE SELECT * FROM '{MARKETS_DIR.as_posix()}/*.parquet' LIMIT 1").df()
print(m_cols.to_string(index=False))

print("[smoke] checking trades schema")
t_cols = con.execute(f"DESCRIBE SELECT * FROM '{TRADES_DIR.as_posix()}/*.parquet' LIMIT 1").df()
print(t_cols.to_string(index=False))

t0 = time.time()
print("[smoke] counting resolved markets")
n_resolved = con.execute(
    f"""SELECT COUNT(*) FROM '{MARKETS_DIR.as_posix()}/*.parquet'
        WHERE status = 'finalized' AND result IN ('yes', 'no')"""
).fetchone()[0]
print(f"  resolved markets: {n_resolved:,}  ({time.time()-t0:.1f}s)")

t0 = time.time()
print("[smoke] counting post-Oct-2024 trades on resolved markets")
n_trades = con.execute(
    f"""
    WITH resolved AS (
        SELECT ticker FROM '{MARKETS_DIR.as_posix()}/*.parquet'
        WHERE status = 'finalized' AND result IN ('yes', 'no')
    )
    SELECT COUNT(*) FROM '{TRADES_DIR.as_posix()}/*.parquet' t
    INNER JOIN resolved r ON t.ticker = r.ticker
    WHERE t.created_time >= TIMESTAMP '2024-10-01'
    """
).fetchone()[0]
print(f"  trades: {n_trades:,}  ({time.time()-t0:.1f}s)")

print("[smoke] sampling 10 trades for schema validation")
sample = con.execute(
    f"""
    SELECT trade_id, ticker, count, yes_price, no_price, taker_side, created_time
    FROM '{TRADES_DIR.as_posix()}/*.parquet'
    WHERE created_time >= TIMESTAMP '2024-10-01'
    LIMIT 10
    """
).df()
print(sample.to_string(index=False))
print(f"  yes+no sums: {(sample['yes_price'] + sample['no_price']).unique()}")
