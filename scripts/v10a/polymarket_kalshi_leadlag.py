"""Round 15c Track 2A: Polymarket vs Kalshi cross-venue lead-lag.

Compares hourly mid-price series for matched market pairs across the two
venues. Goal: determine whether Polymarket leads Kalshi (or vice versa)
on macro / crypto / sports parallels.

Method:
1. Pick a set of candidate Polymarket markets in the Becker overlap
   window (2024-11-01 to 2025-11-25) where the underlying question maps
   cleanly to a Kalshi event_ticker present in Becker.
2. Reconstruct hourly YES VWAP on both venues:
   - Polymarket: parse trades where USDC vs YES/NO token exchanged.
     JOIN to blocks/*.parquet for the timestamp (trades.timestamp is
     NULL in this dataset; block_number maps to a Polygon block time).
   - Kalshi: VWAP by hour from Becker trades (yes_price/100 in dollars).
3. Cross-correlation of first-differences at lags +/- 6 hours.
4. Verdict on direction (PM leads, Kalshi leads, or tie).

This script writes results to research/v10a/14-polymarket-cross-venue.json.

Run with: prediction-market-analysis/.venv/Scripts/python.exe
  scripts/v10a/polymarket_kalshi_leadlag.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import duckdb
import numpy as np

REPO = Path(__file__).resolve().parents[2]
PM = REPO / "prediction-market-analysis" / "data" / "polymarket"
KALSHI = REPO / "prediction-market-analysis" / "data" / "kalshi"
OUT_JSON = REPO / "research" / "v10a" / "14-polymarket-cross-venue.json"

# Curated parallel pairs that satisfy:
#  - Kalshi ticker is in Becker (Becker ends Nov 2025)
#  - Polymarket id has nonzero volume in the same closing month
#  - Same threshold and same period semantics ("max in month >= $X")
PAIRS = [
    # KXBTCMAXM-25SEP30 exists in Becker; Polymarket has "Will BTC reach $X in Sept?" markets
    {"label": "BTC_above_120k_sep2025", "kalshi_ticker": "KXBTCMAXM-25SEP30-119999.99",
     "pm_question_keywords": ["bitcoin", "reach", "120", "september", "sept"], "threshold_min": 119000, "threshold_max": 121000},
    {"label": "BTC_above_125k_sep2025", "kalshi_ticker": "KXBTCMAXM-25SEP30-124999.99",
     "pm_question_keywords": ["bitcoin", "reach", "125", "september", "sept"], "threshold_min": 124000, "threshold_max": 126000},
    {"label": "BTC_above_130k_sep2025", "kalshi_ticker": "KXBTCMAXM-25SEP30-129999.99",
     "pm_question_keywords": ["bitcoin", "reach", "130", "september", "sept"], "threshold_min": 129000, "threshold_max": 131000},
    # KXBTCMAXM-25OCT31 exists in Becker
    {"label": "BTC_above_130k_oct2025", "kalshi_ticker": "KXBTCMAXM-25OCT31-129999.99",
     "pm_question_keywords": ["bitcoin", "reach", "130", "october", "oct"], "threshold_min": 129000, "threshold_max": 131000},
    {"label": "BTC_above_135k_oct2025", "kalshi_ticker": "KXBTCMAXM-25OCT31-134999.99",
     "pm_question_keywords": ["bitcoin", "reach", "135", "october", "oct"], "threshold_min": 134000, "threshold_max": 136000},
    # KXBTCMAXM-AUG25-AUG01: Kalshi closes Aug 1, "max in Aug25 above $X" -> wait, the
    # close_time is 2025-08-01 so it's actually JULY's max. Pair with PM July markets.
    {"label": "BTC_above_120k_jul2025", "kalshi_ticker": "KXBTCMAXM-AUG25-AUG01-119999.99",
     "pm_question_keywords": ["bitcoin", "reach", "120", "july"], "threshold_min": 119000, "threshold_max": 121000},
    {"label": "BTC_above_125k_jul2025", "kalshi_ticker": "KXBTCMAXM-AUG25-AUG01-124999.99",
     "pm_question_keywords": ["bitcoin", "reach", "125", "july"], "threshold_min": 124000, "threshold_max": 126000},
]


def find_polymarket_match(con: duckdb.DuckDBPyConnection, pair: dict) -> dict | None:
    """Find a Polymarket market whose question matches the keywords and
    whose end_date falls in the appropriate month. Returns id, question,
    clob_token_ids, outcomes, end_date."""
    kws = pair["pm_question_keywords"]
    # All keywords must appear in the question (case-insensitive)
    where_parts = [f"LOWER(question) LIKE '%{k}%'" for k in kws]
    where_clause = " AND ".join(where_parts)
    sql = f"""
    SELECT id, question, clob_token_ids, outcomes, end_date, volume
    FROM '{PM}/markets/*.parquet'
    WHERE {where_clause}
      AND end_date >= '2024-11-01' AND end_date <= '2025-11-30'
      AND volume > 100000
    ORDER BY volume DESC
    LIMIT 1
    """
    row = con.execute(sql).fetchone()
    if not row:
        return None
    ids = json.loads(row[2])
    outcomes = json.loads(row[3])
    yes_idx = 0 if outcomes[0].lower() == "yes" else 1
    return {
        "pm_id": row[0],
        "pm_question": row[1],
        "yes_token": ids[yes_idx],
        "no_token": ids[1 - yes_idx],
        "pm_end_date": row[4],
        "pm_volume": row[5],
    }


def get_block_range(con: duckdb.DuckDBPyConnection, start_iso: str,
                    end_iso: str) -> tuple[int, int] | None:
    """Find min, max block_number whose timestamp falls in [start, end]."""
    sql = f"""
    SELECT MIN(block_number), MAX(block_number)
    FROM '{PM}/blocks/*.parquet'
    WHERE timestamp >= '{start_iso}Z' AND timestamp <= '{end_iso}Z'
    """
    row = con.execute(sql).fetchone()
    if not row or row[0] is None:
        return None
    return int(row[0]), int(row[1])


def polymarket_hourly_prices(
    con: duckdb.DuckDBPyConnection,
    yes_token_id: str, no_token_id: str,
    block_min: int, block_max: int,
) -> dict[int, float]:
    """Reconstruct hourly VWAP for the YES token via block_number join.

    YES side trades: maker_asset_id == YES_token (taker bought USDC,
    i.e. seller of YES) OR taker_asset_id == YES_token (buyer of YES).
    Same for NO with 1 - price flip.
    """
    # Pre-filter blocks by range to limit join
    sql = f"""
    WITH
    blk AS (
        SELECT block_number,
               CAST(EPOCH(timestamp::TIMESTAMP) / 3600 AS BIGINT) AS hour_bucket
        FROM '{PM}/blocks/*.parquet'
        WHERE block_number BETWEEN {block_min} AND {block_max}
    ),
    t AS (
        SELECT block_number, maker_asset_id, taker_asset_id,
               CAST(maker_amount AS DOUBLE) AS ma,
               CAST(taker_amount AS DOUBLE) AS ta
        FROM '{PM}/trades/*.parquet'
        WHERE block_number BETWEEN {block_min} AND {block_max}
          AND (maker_asset_id IN ('{yes_token_id}', '{no_token_id}')
               OR taker_asset_id IN ('{yes_token_id}', '{no_token_id}'))
    ),
    joined AS (
        SELECT
            blk.hour_bucket,
            CASE
                WHEN t.maker_asset_id = '{yes_token_id}'
                    THEN t.ta / NULLIF(t.ma, 0)
                WHEN t.taker_asset_id = '{yes_token_id}'
                    THEN t.ma / NULLIF(t.ta, 0)
                WHEN t.maker_asset_id = '{no_token_id}'
                    THEN 1.0 - t.ta / NULLIF(t.ma, 0)
                ELSE 1.0 - t.ma / NULLIF(t.ta, 0)
            END AS yes_price,
            CASE
                WHEN t.maker_asset_id IN ('{yes_token_id}', '{no_token_id}')
                    THEN t.ma
                ELSE t.ta
            END AS volume
        FROM t
        JOIN blk ON t.block_number = blk.block_number
    )
    SELECT hour_bucket,
           SUM(yes_price * volume) / NULLIF(SUM(volume), 0) AS vwap,
           SUM(volume) AS total_vol,
           COUNT(*) AS n_trades
    FROM joined
    WHERE yes_price BETWEEN 0.001 AND 0.999
    GROUP BY 1
    ORDER BY 1
    """
    df = con.execute(sql).fetchdf()
    return {int(r["hour_bucket"]): float(r["vwap"]) for _, r in df.iterrows()}


def kalshi_hourly_prices(
    con: duckdb.DuckDBPyConnection,
    ticker: str, start_iso: str, end_iso: str,
) -> dict[int, float]:
    df = con.execute(f"""
        SELECT
            CAST(EPOCH(created_time) / 3600 AS BIGINT) AS hour_bucket,
            SUM(CAST(yes_price AS DOUBLE) * CAST(count AS DOUBLE))
                / NULLIF(SUM(CAST(count AS DOUBLE)), 0) / 100.0 AS vwap,
            SUM(CAST(count AS DOUBLE)) AS total_vol
        FROM '{KALSHI}/trades/*.parquet'
        WHERE ticker = '{ticker}'
          AND created_time BETWEEN TIMESTAMPTZ '{start_iso}' AND TIMESTAMPTZ '{end_iso}'
        GROUP BY 1 ORDER BY 1
    """).fetchdf()
    return {int(r["hour_bucket"]): float(r["vwap"]) for _, r in df.iterrows()}


def cross_correlation(
    pm_series: dict[int, float], kalshi_series: dict[int, float],
    max_lag: int = 6,
) -> dict:
    """Positive lag: PM leads Kalshi (PM at t correlates with K at t+lag)."""
    hours = sorted(set(pm_series.keys()) & set(kalshi_series.keys()))
    if len(hours) < 10:
        return {"n_overlap": len(hours)}
    pm_arr = np.array([pm_series[h] for h in hours])
    k_arr = np.array([kalshi_series[h] for h in hours])
    pm_d = np.diff(pm_arr)
    k_d = np.diff(k_arr)
    n_d = len(pm_d)
    corr_by_lag: dict[int, float] = {}
    for lag in range(-max_lag, max_lag + 1):
        if lag >= 0:
            x = pm_d[: n_d - lag]
            y = k_d[lag:]
        else:
            x = pm_d[-lag:]
            y = k_d[: n_d + lag]
        if len(x) < 5 or np.std(x) == 0 or np.std(y) == 0:
            continue
        c = float(np.corrcoef(x, y)[0, 1])
        if not np.isnan(c):
            corr_by_lag[lag] = c
    if not corr_by_lag:
        return {"n_overlap": len(hours)}
    best_lag = max(corr_by_lag, key=lambda lag: abs(corr_by_lag[lag]))
    return {
        "n_overlap_hours": len(hours),
        "best_lag_hours": best_lag,
        "best_corr": corr_by_lag[best_lag],
        "corr_at_zero_lag": corr_by_lag.get(0),
        "corr_by_lag": corr_by_lag,
    }


def analyze_pair(con: duckdb.DuckDBPyConnection, pair: dict) -> dict:
    pm = find_polymarket_match(con, pair)
    if pm is None:
        return {**pair, "status": "NO_PM_MATCH"}
    end_date = pm["pm_end_date"]
    if isinstance(end_date, datetime):
        end_dt = end_date.replace(tzinfo=None)
    else:
        end_dt = datetime.fromisoformat(str(end_date).replace("Z", "+00:00")).replace(tzinfo=None)
    start_dt = end_dt - timedelta(days=45)
    end_iso = end_dt.isoformat()
    start_iso = start_dt.isoformat()

    blk = get_block_range(con, start_iso, end_iso)
    if blk is None:
        return {**pair, **pm, "status": "NO_BLOCK_RANGE"}
    pm_prices = polymarket_hourly_prices(con, pm["yes_token"], pm["no_token"],
                                          blk[0], blk[1])
    kalshi_prices = kalshi_hourly_prices(con, pair["kalshi_ticker"],
                                          start_iso, end_iso)
    if len(pm_prices) < 5 or len(kalshi_prices) < 5:
        return {**pair, **pm, "status": "INSUFFICIENT_DATA",
                "pm_hours": len(pm_prices), "kalshi_hours": len(kalshi_prices)}
    lead_lag = cross_correlation(pm_prices, kalshi_prices, max_lag=6)
    return {**pair, **pm, "status": "ANALYZED",
            "pm_hours": len(pm_prices), "kalshi_hours": len(kalshi_prices),
            "lead_lag": lead_lag}


def main():
    con = duckdb.connect()
    results = []
    for pair in PAIRS:
        try:
            r = analyze_pair(con, pair)
        except Exception as exc:
            print(f"[ERROR] {pair['label']}: {exc}", file=sys.stderr)
            r = {**pair, "status": "ERROR", "error": str(exc)}
        results.append(r)
        ll = r.get("lead_lag", {}) or {}
        print(
            f"[{r['status']:18}] {pair['label']:30}  "
            f"pm_h={r.get('pm_hours', 0):>4}  k_h={r.get('kalshi_hours', 0):>4}  "
            f"best_lag={ll.get('best_lag_hours', '-')!s:>3}  "
            f"corr={ll.get('best_corr')}"
        )
        if r.get("status") == "NO_PM_MATCH":
            continue
        if r.get("status") == "ANALYZED":
            print(f"        PM: {r.get('pm_question', '')[:80]}")
            print(f"        Kalshi: {pair['kalshi_ticker']}")

    valid = [r for r in results if r.get("status") == "ANALYZED"
             and r.get("lead_lag", {}).get("best_lag_hours") is not None]
    pm_leads = sum(1 for r in valid if r["lead_lag"]["best_lag_hours"] > 0)
    k_leads = sum(1 for r in valid if r["lead_lag"]["best_lag_hours"] < 0)
    ties = sum(1 for r in valid if r["lead_lag"]["best_lag_hours"] == 0)
    print()
    print(f"Analyzed pairs: {len(valid)} of {len(PAIRS)}")
    print(f"  Polymarket leads Kalshi (lag > 0): {pm_leads}")
    print(f"  Kalshi leads Polymarket (lag < 0): {k_leads}")
    print(f"  Tie (lag 0):                       {ties}")

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON, "w") as f:
        json.dump({"pairs": results, "summary": {
            "n_analyzed": len(valid), "pm_leads_kalshi": pm_leads,
            "kalshi_leads_pm": k_leads, "tie_at_lag_0": ties,
        }}, f, indent=2, default=str)
    print(f"\nSaved to {OUT_JSON}")


if __name__ == "__main__":
    main()
