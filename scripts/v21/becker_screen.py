"""v21 Candidate A Phase 1 screen (NON-INFERENTIAL, pre-registered).

Implements research/v21/00-methodology-lock.md sections 2.2-2.4 exactly. The
three cells and their gates were locked (v3) BEFORE this script existed; the
frozen prefix allowlists were committed before this script existed (lock L-1).

Per-trade pipeline (lock 2.2, methodology critic M-3): built directly from the
trades/markets parquets. Maker side = non-taker side; settlement from markets
`result` (finalized, yes/no only); maker fee ceil(0.0175*P*(1-P)*100)/100.

Population (lock 2.3): trade created_time inside the window AND market
close_time inside the SAME window AND market horizon
(close_time - market created_time) <= 60 days, uniform across BOTH windows
(methodology critic H-1). UTC pinned. Dropped long-horizon share is reported.

Gates per cell (lock 2.4):
  S-A1a: train combined-side net excess > 0, event-cluster bootstrap 95% CI
         excluding zero (n_resamples=5000, ci=0.95, rng_seed=42). RUNS FIRST.
  S-A1b: recency point >= 50% of train point AND recency point > 0.
  S-A1c: recency >= 200 distinct events AND >= 30 distinct allowlist prefixes.
  S-A1d: projected 45-day fills at 3% on recency in-band trade-print
         opportunity (market, day) pairs >= 30.
Diagnostics (report-only, locked): contract-weighted net excess;
series-prefix-clustered CI sensitivity.

Run (Windows):
  & "C:\\Users\\SamJD\\OneDrive\\Desktop\\AI Projects\\Project Kalshi\\.venv-kronos\\Scripts\\python.exe" "C:\\Users\\SamJD\\OneDrive\\Desktop\\AI Projects\\Project Kalshi\\scripts\\v21\\becker_screen.py"
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import duckdb
import numpy as np

BASE = Path(r"C:/Users/SamJD/OneDrive/Desktop/AI Projects/Project Kalshi")
BECKER = BASE / "prediction-market-analysis"
TRADES_DIR = BECKER / "data" / "kalshi" / "trades"
MARKETS_DIR = BECKER / "data" / "kalshi" / "markets"
ALLOWLIST_DIR = BASE / "research" / "v21" / "allowlists"
OUT_PATH = BASE / "research" / "v21" / "03-screen-results.json"

sys.path.insert(0, str(BASE / "src"))
from kalshi_bot.analysis.bootstrap import cluster_bootstrap_mean_ci  # noqa: E402

TRAIN = ("2024-11-01", "2025-09-01")
RECENCY = ("2025-09-01", "2025-11-25")
RECENCY_DAYS = 85  # 2025-09-01 to 2025-11-25
HORIZON_CAP_DAYS = 60
RNG_SEED = 42
N_RESAMPLES = 5000
CI = 0.95

# S-A1 thresholds (locked v3)
S_A1B_RATIO = 0.50
S_A1C_MIN_EVENTS = 200
S_A1C_MIN_PREFIXES = 30
S_A1D_FILL_RATE = 0.03
S_A1D_PROJECT_DAYS = 45
S_A1D_MIN_FILLS = 30

CELLS = [
    {"name": "media_040_060", "band": (0.40, 0.60)},
    {"name": "entertainment_040_060", "band": (0.40, 0.60)},
    {"name": "other_060_080", "band": (0.60, 0.80)},
]


def load_allowlist(name: str) -> list[str]:
    with open(ALLOWLIST_DIR / f"{name}.json", encoding="utf-8") as f:
        data = json.load(f)
    return [p["prefix"] for p in data["prefixes"]]


def pull_cell(con: duckdb.DuckDBPyConnection, prefixes: list[str], band: tuple[float, float],
              window: tuple[str, str]) -> tuple["object", float]:
    """Per-trade maker observations for one cell and window.

    Returns (DataFrame, dropped_long_horizon_share). Membership uses the SAME
    prefix definition as the freeze: regexp_extract(event_ticker, '^([A-Z0-9]+)', 1).
    ORDER BY trade_id (review H-1): the seeded cluster bootstrap consumes
    cluster first-appearance order, so the row order must be deterministic or
    rng_seed=42 does not pin one realization across reruns.
    """
    tz = con.execute("SELECT current_setting('TimeZone')").fetchone()[0]
    if tz != "UTC":
        raise RuntimeError(f"pull_cell requires session TimeZone=UTC, got {tz}")
    lo, hi = band
    quoted = ",".join(f"'{p}'" for p in prefixes)
    q = f"""
        WITH resolved AS (
            SELECT ticker, event_ticker, result, created_time AS m_created, close_time
            FROM '{MARKETS_DIR.as_posix()}/*.parquet'
            WHERE status = 'finalized' AND result IN ('yes','no')
        ),
        joined AS (
            SELECT
                t.trade_id,
                t.ticker,
                m.event_ticker,
                regexp_extract(m.event_ticker, '^([A-Z0-9]+)', 1) AS prefix,
                (CASE WHEN t.taker_side='yes' THEN t.no_price ELSE t.yes_price END)/100.0 AS maker_price,
                (CASE WHEN t.taker_side != m.result THEN 1.0 ELSE 0.0 END) AS maker_won,
                t.count AS contracts,
                CAST(t.created_time AS DATE) AS trade_date,
                m.close_time,
                m.m_created
            FROM '{TRADES_DIR.as_posix()}/*.parquet' t
            INNER JOIN resolved m ON t.ticker = m.ticker
            WHERE t.created_time >= TIMESTAMP '{window[0]}'
              AND t.created_time < TIMESTAMP '{window[1]}'
              AND t.yes_price IS NOT NULL
              AND t.no_price IS NOT NULL
              AND t.yes_price + t.no_price = 100
              AND t.count > 0
              AND t.taker_side IN ('yes','no')
              AND m.close_time >= TIMESTAMP '{window[0]}'
              AND m.close_time < TIMESTAMP '{window[1]}'
        )
        SELECT *,
            (close_time - m_created) <= INTERVAL {HORIZON_CAP_DAYS} DAYS AS horizon_ok
        FROM joined
        WHERE prefix IN ({quoted})
          AND maker_price >= {lo} AND maker_price < {hi}
        ORDER BY trade_id
    """
    df = con.execute(q).df()
    n_all = len(df)
    kept = df[df["horizon_ok"]].copy()
    dropped_share = float(1.0 - len(kept) / n_all) if n_all > 0 else 0.0
    fee = np.ceil(0.0175 * kept["maker_price"] * (1.0 - kept["maker_price"]) * 100.0) / 100.0
    kept["net_excess"] = kept["maker_won"] - kept["maker_price"] - fee
    return kept, dropped_share


def window_stats(df, label: str) -> dict:
    """Point estimates + locked CIs + diagnostics for one cell-window."""
    net = df["net_excess"].to_numpy()
    events = df["event_ticker"].to_numpy()
    prefixes = df["prefix"].to_numpy()
    contracts = df["contracts"].to_numpy(dtype=float)

    out: dict = {
        "window": label,
        "n_trades": int(len(df)),
        "n_events": int(df["event_ticker"].nunique()),
        "n_prefixes": int(df["prefix"].nunique()),
        "n_markets": int(df["ticker"].nunique()),
    }
    if len(df) == 0:
        return out

    t0 = time.time()
    mean, lo, hi, k = cluster_bootstrap_mean_ci(
        net, events, n_resamples=N_RESAMPLES, ci=CI, rng_seed=RNG_SEED,
    )
    out["net_pp"] = mean * 100
    out["event_ci_pp"] = [lo * 100, hi * 100]
    out["n_event_clusters"] = k

    pm, plo, phi, pk = cluster_bootstrap_mean_ci(
        net, prefixes, n_resamples=N_RESAMPLES, ci=CI, rng_seed=RNG_SEED,
    )
    out["prefix_ci_pp_sensitivity"] = [plo * 100, phi * 100]
    out["n_prefix_clusters"] = pk

    out["contract_weighted_net_pp"] = float(np.average(net, weights=contracts)) * 100
    out["bootstrap_seconds"] = round(time.time() - t0, 1)
    return out


def main() -> None:
    con = duckdb.connect(":memory:")
    con.execute("PRAGMA threads=8")
    con.execute("PRAGMA memory_limit='12GB'")
    con.execute("SET TimeZone='UTC'")

    results = []
    for cell in CELLS:
        name = cell["name"]
        prefixes = load_allowlist(name)
        print(f"\n=== CELL {name} ({len(prefixes)} allowlist prefixes) ===", flush=True)

        # S-A1a FIRST (lock: the cheapest kill, train window).
        t0 = time.time()
        train_df, train_dropped = pull_cell(con, prefixes, cell["band"], TRAIN)
        print(f"  train pull: {len(train_df):,} trades in {time.time()-t0:.1f}s "
              f"(long-horizon dropped share {train_dropped:.1%})", flush=True)
        train = window_stats(train_df, "train")
        s_a1a = bool(
            len(train_df) > 0
            and train["net_pp"] > 0
            and train["event_ci_pp"][0] > 0
        )
        print(f"  S-A1a train: net={train.get('net_pp', float('nan')):+.3f}pp "
              f"eventCI=[{train.get('event_ci_pp', [float('nan')]*2)[0]:+.3f},"
              f"{train.get('event_ci_pp', [float('nan')]*2)[1]:+.3f}] "
              f"k={train.get('n_event_clusters', 0)} -> {'PASS' if s_a1a else 'FAIL'}",
              flush=True)

        cell_out = {
            "cell": name,
            "n_allowlist_prefixes": len(prefixes),
            "train": train,
            "train_dropped_long_horizon_share": train_dropped,
            "S_A1a_pass": s_a1a,
        }

        # Remaining gates computed regardless (full pre-registered record),
        # but a cell is dropped on ANY failure.
        t0 = time.time()
        rec_df, rec_dropped = pull_cell(con, prefixes, cell["band"], RECENCY)
        print(f"  recency pull: {len(rec_df):,} trades in {time.time()-t0:.1f}s "
              f"(long-horizon dropped share {rec_dropped:.1%})", flush=True)
        rec = window_stats(rec_df, "recency")
        cell_out["recency"] = rec
        cell_out["recency_dropped_long_horizon_share"] = rec_dropped

        train_pp = train.get("net_pp")
        rec_pp = rec.get("net_pp")
        s_a1b = bool(
            train_pp is not None and rec_pp is not None
            and rec_pp > 0
            and (train_pp <= 0 or rec_pp >= S_A1B_RATIO * train_pp)
        )
        s_a1c = bool(
            rec.get("n_events", 0) >= S_A1C_MIN_EVENTS
            and rec.get("n_prefixes", 0) >= S_A1C_MIN_PREFIXES
        )
        # S-A1d: in-band trade-print opportunity (market, day) pairs in recency.
        opportunities = int(rec_df[["ticker", "trade_date"]].drop_duplicates().shape[0]) if len(rec_df) else 0
        opp_per_day = opportunities / RECENCY_DAYS
        projected_fills = opp_per_day * S_A1D_PROJECT_DAYS * S_A1D_FILL_RATE
        s_a1d = bool(projected_fills >= S_A1D_MIN_FILLS)

        cell_out.update({
            "S_A1b_pass": s_a1b,
            "S_A1c_pass": s_a1c,
            "S_A1d": {
                "opportunity_market_days": opportunities,
                "opportunities_per_day": opp_per_day,
                "projected_45d_fills_at_3pct": projected_fills,
            },
            "S_A1d_pass": s_a1d,
            "cell_survives": bool(s_a1a and s_a1b and s_a1c and s_a1d),
        })
        print(f"  S-A1b: rec={rec_pp if rec_pp is not None else float('nan'):+.3f}pp vs "
              f"train -> {'PASS' if s_a1b else 'FAIL'} | "
              f"S-A1c: events={rec.get('n_events', 0)} prefixes={rec.get('n_prefixes', 0)} "
              f"-> {'PASS' if s_a1c else 'FAIL'} | "
              f"S-A1d: proj_fills={projected_fills:.1f} -> {'PASS' if s_a1d else 'FAIL'}",
              flush=True)
        print(f"  CELL {'SURVIVES' if cell_out['cell_survives'] else 'KILLED'}", flush=True)
        results.append(cell_out)

    summary = {
        "lock": "research/v21/00-methodology-lock.md v3",
        "windows": {"train": TRAIN, "recency": RECENCY},
        "horizon_cap_days": HORIZON_CAP_DAYS,
        "ci_call": {"n_resamples": N_RESAMPLES, "ci": CI, "rng_seed": RNG_SEED},
        "cells": results,
        "survivors": [c["cell"] for c in results if c["cell_survives"]],
    }
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print(f"\n[done] survivors: {summary['survivors'] or 'NONE (Candidate A killed at Phase 1)'}")
    print(f"[done] wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
