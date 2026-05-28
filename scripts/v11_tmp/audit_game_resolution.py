"""v11 A1 Becker audit. READ-ONLY. Tmp scratch script.

Counts settled markets, date ranges, and trade-time-of-day coverage
for the five game-resolution prefixes that v11's sportsbook line
movement hypothesis depends on.
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

    # First, confirm status field values for KX markets
    print("=== Status value distribution on KX markets ===")
    rows = con.execute(f"""
        SELECT status, COUNT(*) AS n
        FROM '{MARKETS.as_posix()}'
        WHERE ticker LIKE 'KX%'
        GROUP BY status
        ORDER BY n DESC
    """).fetchall()
    for status, n in rows:
        print(f"  {status}: {n}")
    print()

    results: dict[str, dict] = {}

    for prefix in PREFIXES:
        print(f"\n=== {prefix} ===")
        t0 = time.time()

        # Section 1+2+4: market counts and date range, all + post-cutoff
        sql_markets = f"""
        WITH m AS (
            SELECT ticker, close_time, status, result
            FROM '{MARKETS.as_posix()}'
            WHERE ticker LIKE '{prefix}%' AND status = 'finalized'
        )
        SELECT
            COUNT(*) AS n_settled,
            MIN(close_time) AS min_close,
            MAX(close_time) AS max_close,
            SUM(CASE WHEN close_time >= TIMESTAMP '{CUTOFF}' THEN 1 ELSE 0 END) AS n_settled_post_cutoff
        FROM m
        """
        m = con.execute(sql_markets).fetchone()
        n_settled, min_close, max_close, n_post = m
        print(f"  n_settled markets: {n_settled}")
        print(f"  close_time range: {min_close} to {max_close}")
        print(f"  n_settled post-{CUTOFF}: {n_post}")

        # Section 3: trade-window coverage on settled markets
        # For each settled market, check whether at least one trade
        # exists in each of the three windows relative to close_time.
        # Use the markets table for close_time, join trades on ticker.
        # Restrict to post-cutoff markets to keep the join manageable.
        # We'll also report all-time coverage for transparency.
        sql_coverage = f"""
        WITH m AS (
            SELECT ticker, close_time
            FROM '{MARKETS.as_posix()}'
            WHERE ticker LIKE '{prefix}%' AND status = 'finalized'
        ),
        m_post AS (
            SELECT ticker, close_time
            FROM m
            WHERE close_time >= TIMESTAMP '{CUTOFF}'
        ),
        trades_in_market AS (
            SELECT
                t.ticker,
                t.created_time,
                m.close_time,
                EXTRACT(EPOCH FROM (m.close_time - t.created_time)) AS secs_before_close
            FROM '{TRADES.as_posix()}' t
            INNER JOIN m_post m USING (ticker)
            WHERE t.created_time >= TIMESTAMP '{CUTOFF}'
              AND t.created_time <= m.close_time
              AND t.created_time >= m.close_time - INTERVAL '6 hours'
        ),
        per_market AS (
            SELECT
                m.ticker,
                MAX(CASE WHEN tim.secs_before_close BETWEEN 3*3600 AND 6*3600 THEN 1 ELSE 0 END) AS has_w6_3,
                MAX(CASE WHEN tim.secs_before_close BETWEEN 1*3600 AND 3*3600 THEN 1 ELSE 0 END) AS has_w3_1,
                MAX(CASE WHEN tim.secs_before_close BETWEEN 0 AND 1*3600 THEN 1 ELSE 0 END) AS has_w1_0
            FROM m_post m
            LEFT JOIN trades_in_market tim USING (ticker)
            GROUP BY m.ticker
        )
        SELECT
            COUNT(*) AS n_markets,
            SUM(has_w6_3) AS n_w6_3,
            SUM(has_w3_1) AS n_w3_1,
            SUM(has_w1_0) AS n_w1_0,
            SUM(CASE WHEN has_w6_3 = 1 AND has_w3_1 = 1 AND has_w1_0 = 1 THEN 1 ELSE 0 END) AS n_all_three
        FROM per_market
        """
        c = con.execute(sql_coverage).fetchone()
        n_markets, n_w6_3, n_w3_1, n_w1_0, n_all = c
        if n_markets:
            pct_6_3 = 100.0 * n_w6_3 / n_markets
            pct_3_1 = 100.0 * n_w3_1 / n_markets
            pct_1_0 = 100.0 * n_w1_0 / n_markets
            pct_all = 100.0 * n_all / n_markets
        else:
            pct_6_3 = pct_3_1 = pct_1_0 = pct_all = 0.0
        print(f"  [post-cutoff] {n_markets} markets, coverage:")
        print(f"    [T-6h, T-3h]: {n_w6_3} ({pct_6_3:.1f}%)")
        print(f"    [T-3h, T-1h]: {n_w3_1} ({pct_3_1:.1f}%)")
        print(f"    [T-1h, close]: {n_w1_0} ({pct_1_0:.1f}%)")
        print(f"    all three windows: {n_all} ({pct_all:.1f}%)")
        print(f"  query elapsed: {time.time() - t0:.1f}s")

        # Verdict
        if n_post >= 100 and pct_all >= 50:
            verdict = "FEASIBLE"
        elif n_post >= 50 or pct_all >= 30:
            verdict = "MARGINAL"
        else:
            verdict = "INFEASIBLE"
        print(f"  VERDICT: {verdict}")

        results[prefix] = {
            "n_settled_all_time": n_settled,
            "min_close": str(min_close) if min_close else None,
            "max_close": str(max_close) if max_close else None,
            "n_settled_post_cutoff": n_post,
            "n_post_for_coverage": n_markets,
            "n_w6_3": n_w6_3,
            "n_w3_1": n_w3_1,
            "n_w1_0": n_w1_0,
            "n_all_three": n_all,
            "pct_w6_3": round(pct_6_3, 1),
            "pct_w3_1": round(pct_3_1, 1),
            "pct_w1_0": round(pct_1_0, 1),
            "pct_all_three": round(pct_all, 1),
            "verdict": verdict,
        }

    # Cross-prefix synthesis
    total_post = sum(r["n_settled_post_cutoff"] for r in results.values())
    print(f"\n\n=== Cross-prefix synthesis ===")
    print(f"aggregate post-{CUTOFF} settled markets: {total_post}")
    for p, r in results.items():
        print(f"  {p}: {r['n_settled_post_cutoff']} settled, all-3-win coverage {r['pct_all_three']}%, verdict {r['verdict']}")

    # Dump JSON for the report writer
    out = REPO / "scripts" / "v11_tmp" / "audit_results.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w") as f:
        json.dump({"prefixes": results, "aggregate_post_cutoff": total_post, "cutoff": CUTOFF}, f, indent=2, default=str)
    print(f"\nResults JSON: {out}")


if __name__ == "__main__":
    main()
