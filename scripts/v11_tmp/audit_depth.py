"""v11 A1 supplementary: trade depth per window per prefix.

Coverage said "is there >=1 trade?" but for line-movement modeling we
need many trades per market in the window. Probe median + p25 + p75
of trades-per-market-per-window for the post-cutoff markets.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import duckdb

REPO = Path(__file__).resolve().parents[2]
MARKETS = REPO / "prediction-market-analysis" / "data" / "kalshi" / "markets" / "*.parquet"
TRADES = REPO / "prediction-market-analysis" / "data" / "kalshi" / "trades" / "*.parquet"

PREFIXES = ["KXNFLGAME", "KXMLBGAME", "KXNBAGAME", "KXBOXING", "KXUFCFIGHT"]
CUTOFF = "2024-10-01"


def main() -> None:
    con = duckdb.connect()
    con.execute("PRAGMA threads=4")

    depth = {}

    for prefix in PREFIXES:
        print(f"\n=== {prefix} ===")
        t0 = time.time()

        sql = f"""
        WITH m AS (
            SELECT ticker, close_time
            FROM '{MARKETS.as_posix()}'
            WHERE ticker LIKE '{prefix}%'
              AND status = 'finalized'
              AND close_time >= TIMESTAMP '{CUTOFF}'
        ),
        per_market AS (
            SELECT
                m.ticker,
                COUNT(CASE WHEN EXTRACT(EPOCH FROM (m.close_time - t.created_time)) BETWEEN 3*3600 AND 6*3600 THEN 1 END) AS n_w6_3,
                COUNT(CASE WHEN EXTRACT(EPOCH FROM (m.close_time - t.created_time)) BETWEEN 1*3600 AND 3*3600 THEN 1 END) AS n_w3_1,
                COUNT(CASE WHEN EXTRACT(EPOCH FROM (m.close_time - t.created_time)) BETWEEN 0 AND 1*3600 THEN 1 END) AS n_w1_0
            FROM m
            LEFT JOIN '{TRADES.as_posix()}' t
                ON t.ticker = m.ticker
                AND t.created_time >= m.close_time - INTERVAL '6 hours'
                AND t.created_time <= m.close_time
            GROUP BY m.ticker
        )
        SELECT
            quantile_cont(n_w6_3, 0.25) AS p25_w6_3,
            quantile_cont(n_w6_3, 0.50) AS med_w6_3,
            quantile_cont(n_w6_3, 0.75) AS p75_w6_3,
            quantile_cont(n_w3_1, 0.25) AS p25_w3_1,
            quantile_cont(n_w3_1, 0.50) AS med_w3_1,
            quantile_cont(n_w3_1, 0.75) AS p75_w3_1,
            quantile_cont(n_w1_0, 0.25) AS p25_w1_0,
            quantile_cont(n_w1_0, 0.50) AS med_w1_0,
            quantile_cont(n_w1_0, 0.75) AS p75_w1_0
        FROM per_market
        """
        r = con.execute(sql).fetchone()
        p25_63, med_63, p75_63, p25_31, med_31, p75_31, p25_10, med_10, p75_10 = r
        print(f"  trades per market per window (p25/median/p75):")
        print(f"    [T-6h, T-3h]: {p25_63:.0f} / {med_63:.0f} / {p75_63:.0f}")
        print(f"    [T-3h, T-1h]: {p25_31:.0f} / {med_31:.0f} / {p75_31:.0f}")
        print(f"    [T-1h, close]: {p25_10:.0f} / {med_10:.0f} / {p75_10:.0f}")
        print(f"  elapsed: {time.time() - t0:.1f}s")

        depth[prefix] = {
            "w6_3": [int(p25_63 or 0), int(med_63 or 0), int(p75_63 or 0)],
            "w3_1": [int(p25_31 or 0), int(med_31 or 0), int(p75_31 or 0)],
            "w1_0": [int(p25_10 or 0), int(med_10 or 0), int(p75_10 or 0)],
        }

    out = REPO / "scripts" / "v11_tmp" / "depth_results.json"
    with out.open("w") as f:
        json.dump(depth, f, indent=2)
    print(f"\nDepth JSON: {out}")


if __name__ == "__main__":
    main()
