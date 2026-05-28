"""V10-A round 15b sweep: run cluster-bootstrap gates across top candidate prefixes.

For each candidate prefix, compute:
- Trade-level (long-run portfolio expected): mean net P&L per trade, boot CI
- Cluster-level (per-event boot): mean of per-event mean P&L, boot CI on this
- Both at OOS window 2025-10-01 to 2025-11-25 (post-flip recent slice)

A prefix passes if cluster-level boot CI lower > 0 AND n_events >= 30.

Reports gross trade-weighted edge (the realized long-run expected P&L),
and the cluster-level p-value as the statistical-significance gate.
"""
from __future__ import annotations

import json
import math
import time
from pathlib import Path

import duckdb
import numpy as np

REPO = Path(__file__).resolve().parents[2]
MARKETS = REPO / "prediction-market-analysis" / "data" / "kalshi" / "markets" / "*.parquet"
TRADES = REPO / "prediction-market-analysis" / "data" / "kalshi" / "trades" / "*.parquet"

CANDIDATES = [
    # (prefix, px_lo, px_hi)
    ("KXEPLGAME", 0.30, 0.70),
    ("KXNCAAFSPREAD", 0.30, 0.70),
    ("KXNFLSPREAD", 0.30, 0.70),
    ("KXNFLGAME", 0.30, 0.70),
    ("KXMLBGAME", 0.30, 0.70),
    ("KXNBAGAME", 0.30, 0.70),
    ("KXNHLGAME", 0.30, 0.70),
    ("KXNCAAFGAME", 0.30, 0.70),
    ("KXNCAAMBGAME", 0.30, 0.70),
    ("KXMARMAD", 0.30, 0.70),
    ("KXUFCFIGHT", 0.30, 0.70),
    ("KXPGATOUR", 0.30, 0.70),
    ("KXATPMATCH", 0.30, 0.70),
    ("KXWTAMATCH", 0.30, 0.70),
    ("KXFEDDECISION", 0.30, 0.70),
    ("KXBTCD", 0.30, 0.70),
    ("KXETHD", 0.30, 0.70),
    ("KXBTC", 0.30, 0.70),
    ("KXHIGHNY", 0.30, 0.70),
    ("KXHIGHCHI", 0.30, 0.70),
    ("KXHIGHMIA", 0.30, 0.70),
    ("KXHIGHLAX", 0.30, 0.70),
    ("KXHIGHAUS", 0.30, 0.70),
    ("KXHIGHDEN", 0.30, 0.70),
    ("KXINXU", 0.30, 0.70),
    ("KXNFLTOTAL", 0.30, 0.70),
    ("KXUCLGAME", 0.30, 0.70),
    ("KXGOVSHUTLENGTH", 0.30, 0.70),
    ("KXNCAAFTOTAL", 0.30, 0.70),
    ("KXNBASPREAD", 0.30, 0.70),
    ("KXNBATOTAL", 0.30, 0.70),
    ("KXMLBTOTAL", 0.30, 0.70),
    ("KXMLBSPREAD", 0.30, 0.70),
    ("KXEURUSD", 0.30, 0.70),
    ("KXUSDJPY", 0.30, 0.70),
    ("KXCPI", 0.30, 0.70),
    ("PRES", 0.30, 0.70),
]


def maker_fee_per_contract(px):
    return 0.25 * np.ceil(0.07 * px * (1.0 - px) * 100.0) / 100.0


def get_df(prefix, px_lo, px_hi, start, end):
    con = duckdb.connect()
    sql = f"""
    WITH resolved AS (
        SELECT
            ticker, event_ticker, result,
            regexp_extract(event_ticker, '^([A-Z0-9]+)', 1) AS prefix_raw
        FROM '{MARKETS.as_posix()}'
        WHERE status = 'finalized' AND result IN ('yes', 'no')
    )
    SELECT
        m.event_ticker AS event_ticker,
        t.yes_price, t.no_price, t.taker_side, m.result, t.created_time,
        CASE WHEN t.taker_side = 'yes' THEN t.no_price ELSE t.yes_price END / 100.0 AS maker_px,
        CASE WHEN t.taker_side != m.result THEN 1.0 ELSE 0.0 END
            - (CASE WHEN t.taker_side = 'yes' THEN t.no_price ELSE t.yes_price END / 100.0) AS maker_gross
    FROM '{TRADES.as_posix()}' t
    INNER JOIN resolved m ON t.ticker = m.ticker
    WHERE m.prefix_raw = '{prefix}'
      AND t.created_time >= '{start}'
      AND t.created_time < '{end}'
      AND (CASE WHEN t.taker_side = 'yes' THEN t.no_price ELSE t.yes_price END) / 100.0 BETWEEN {px_lo} AND {px_hi}
    """
    df = con.execute(sql).df()
    if len(df) == 0:
        return df
    df["fee"] = maker_fee_per_contract(df["maker_px"].values)
    df["net"] = df["maker_gross"] - df["fee"]
    return df


def bootstrap_mean_ci(arr, n_boot=1500, seed=42):
    n = len(arr)
    if n < 2:
        return float("nan"), float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    boot = []
    for _ in range(n_boot):
        sample = rng.choice(arr, size=n, replace=True)
        boot.append(sample.mean())
    return float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5)), float(np.mean(boot))


def main():
    start = "2025-10-01"  # OOS window in our data range
    end = "2025-11-25"
    print(f"Sweep: OOS window [{start}, {end}); cluster-bootstrap by event_ticker")
    print(f"All prices in [0.30, 0.70] maker band")
    print("=" * 130)
    print(f"{'prefix':22} {'n_tr':>8} {'mean_tr':>8} {'tr_lo':>8} {'tr_hi':>8}  "
          f"{'n_evt':>6} {'evt_mean':>9} {'evt_lo':>9} {'evt_hi':>9}  verdict")
    print("-" * 130)
    summary = []
    for prefix, lo, hi in CANDIDATES:
        df = get_df(prefix, lo, hi, start, end)
        if len(df) < 100:
            verdict = "INSUFFICIENT_N"
            row = {"prefix": prefix, "px_band": [lo, hi], "n_trades": len(df), "verdict": verdict}
            summary.append(row)
            print(f"{prefix:22} {len(df):>8}  INSUFFICIENT")
            continue
        # Trade-level
        tr_lo, tr_hi, _ = bootstrap_mean_ci(df["net"].to_numpy())
        tr_mean = float(df["net"].mean())
        # Cluster-level
        per_event = df.groupby("event_ticker")["net"].mean().to_numpy()
        n_events = len(per_event)
        evt_lo, evt_hi, _ = bootstrap_mean_ci(per_event)
        evt_mean = float(per_event.mean()) if n_events > 0 else float("nan")
        # Gate: cluster-level CI lower > 0 AND n_events >= 30
        gate_pass = (evt_lo > 0) and (n_events >= 30)
        if gate_pass:
            verdict = "PASS_RIGOROUS"
        elif tr_lo > 0 and n_events >= 10:
            verdict = "TRADE_LEVEL_ONLY"
        elif tr_lo > 0:
            verdict = "TRADE_LEVEL_THIN_N"
        else:
            verdict = "NULL"
        row = {
            "prefix": prefix, "px_band": [lo, hi],
            "n_trades": int(len(df)), "n_events": int(n_events),
            "tr_mean": tr_mean, "tr_lo": tr_lo, "tr_hi": tr_hi,
            "evt_mean": evt_mean, "evt_lo": evt_lo, "evt_hi": evt_hi,
            "verdict": verdict,
        }
        summary.append(row)
        print(
            f"{prefix:22} {len(df):>8} {tr_mean:>+8.4f} {tr_lo:>+8.4f} {tr_hi:>+8.4f}  "
            f"{n_events:>6} {evt_mean:>+9.4f} {evt_lo:>+9.4f} {evt_hi:>+9.4f}  {verdict}"
        )
    out = REPO / "research" / "v10a" / "06-cluster-sweep-results.json"
    with open(out, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\nSummary JSON: {out}")
    n_pass = sum(1 for r in summary if r.get("verdict") == "PASS_RIGOROUS")
    n_tr_only = sum(1 for r in summary if r.get("verdict") == "TRADE_LEVEL_ONLY")
    print(f"\nResults: {n_pass} prefixes PASS rigorous gate (cluster-CI > 0 AND n_events >= 30)")
    print(f"         {n_tr_only} prefixes pass trade-level only (cluster-CI may include zero)")


if __name__ == "__main__":
    main()
