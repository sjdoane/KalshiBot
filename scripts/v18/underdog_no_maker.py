"""Underdog-NO maker probe (Becker, read-only).

The favorite-longshot bias is symmetric: if favorites are underpriced (v1 buys
YES at yes_px>=0.70 and earns ~+5-8%), then longshots are OVERPRICED, so buying
NO on an underdog market (yes_px<=0.30, i.e. no_px>=0.70) as a maker should earn
a symmetric edge. v1 currently MISSES these (it only trades yes_px>=0.70), so a
game framed as the underdog's YES is skipped. If the NO-side edge exists, it
roughly doubles v1's tradeable universe.

Pre-registered gate (mirror of the favorite analysis, locked before this run):
buy NO as maker at no_px in [0.70, 0.95], hold to settle. A prefix CONFIRMS the
symmetric edge if its OOS event-mean net P&L > 0 with a cluster-bootstrap CI
lower bound > 0 AND the train CI lower bound > 0 (persistent), n_events>=30. The
LOW no_px band [0.70,0.86) is the expected sweet spot (mirroring the favorite
finding). KILL/NULL if the NO-side OOS CI includes zero: the bias is asymmetric
(only the favorite side is exploitable) and v1's YES-only approach is complete.

Becker proxy: maker on the NO side = taker_side='yes' (the taker lifts YES, so
the maker is short YES = long NO). P&L of buying NO at no_px = (result=='no' ?
1-no_px : -no_px) - maker_fee(no_px).

  PYTHONPATH=src .venv-kronos\\Scripts\\python.exe scripts\\v18\\underdog_no_maker.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
MARKETS = (REPO / "prediction-market-analysis/data/kalshi/markets/*.parquet").as_posix()
TRADES = (REPO / "prediction-market-analysis/data/kalshi/trades/*.parquet").as_posix()
TRAIN = ("2024-11-01", "2025-09-01")
OOS = ("2025-09-01", "2025-11-25")
BAND_EDGES = [0.70, 0.78, 0.86, 0.95001]
BAND_LABELS = ["B1[.70,.78)", "B2[.78,.86)", "B3[.86,.95]"]
MIN_OOS_EVENTS = 30


def load(prefix: str, window: tuple[str, str]) -> pd.DataFrame:
    con = duckdb.connect()
    sql = f"""
    SELECT m.event_ticker AS event_ticker, t.no_price/100.0 AS no_px,
           CASE WHEN m.result='no' THEN 1.0 - t.no_price/100.0
                ELSE -t.no_price/100.0 END
             - 0.25*CEIL(0.07*(t.no_price/100.0)*(1.0-t.no_price/100.0)*100.0)/100.0
             AS net_pl
    FROM '{TRADES}' t JOIN '{MARKETS}' m ON t.ticker=m.ticker
    WHERE m.status='finalized' AND m.result IN ('yes','no')
      AND m.event_ticker LIKE '{prefix}%'
      AND t.taker_side='yes' AND t.no_price>=70 AND t.no_price<=95
      AND t.created_time >= DATE '{window[0]}' AND t.created_time < DATE '{window[1]}'
    """
    df = con.execute(sql).df()
    if len(df):
        df["band"] = pd.cut(df["no_px"], bins=BAND_EDGES, labels=BAND_LABELS, right=False)
    return df


def cluster(df: pd.DataFrame, n_boot: int = 2000, seed: int = 42) -> dict:
    if df is None or len(df) == 0:
        return {"n_trades": 0, "n_events": 0, "event_mean": None, "ci_lo": None, "ci_hi": None}
    per = df.groupby("event_ticker", observed=True)["net_pl"].mean().to_numpy()
    n = len(per)
    if n < 2:
        return {"n_trades": int(len(df)), "n_events": n,
                "event_mean": float(per[0]) if n == 1 else None, "ci_lo": None, "ci_hi": None}
    rng = np.random.default_rng(seed)
    boots = np.array([rng.choice(per, size=n, replace=True).mean() for _ in range(n_boot)])
    return {"n_trades": int(len(df)), "n_events": int(n), "event_mean": float(per.mean()),
            "ci_lo": float(np.percentile(boots, 2.5)), "ci_hi": float(np.percentile(boots, 97.5))}


def analyze(prefix: str) -> dict:
    tr, oo = load(prefix, TRAIN), load(prefix, OOS)
    base_tr, base_oo = cluster(tr), cluster(oo)
    print(f"\n===== {prefix} (BUY NO maker on underdog, no_px in [0.70,0.95]) =====")
    print(f"  train n_tr={len(tr)} oos n_tr={len(oo)}")
    if base_oo["event_mean"] is None:
        print("  insufficient data")
        return {"prefix": prefix, "insufficient": True}
    print(f"  baseline: TRAIN {base_tr['event_mean']:+.4f} (lo {base_tr['ci_lo']:+.4f}) n={base_tr['n_events']} | "
          f"OOS {base_oo['event_mean']:+.4f} CI[{base_oo['ci_lo']:+.4f},{base_oo['ci_hi']:+.4f}] n={base_oo['n_events']}")
    low_sel = lambda d: d[d["no_px"] < 0.86]  # noqa: E731
    cells = {"LOW[.70,.86)": {"train": cluster(low_sel(tr)), "oos": cluster(low_sel(oo))}}
    for b in BAND_LABELS:
        cells[b] = {"train": cluster(tr[tr["band"] == b]), "oos": cluster(oo[oo["band"] == b])}
    for name, c in cells.items():
        ct, co = c["train"], c["oos"]
        def fmt(x):
            return f"{x:>+8.4f}" if isinstance(x, float) else f"{'-':>8}"
        print(f"    {name:16} TR {fmt(ct['event_mean'])} (lo {fmt(ct['ci_lo'])}) n={ct['n_events']:>5}"
              f"  OOS {fmt(co['event_mean'])} (lo {fmt(co['ci_lo'])}) n={co['n_events']:>5}")
    base_ok = bool(base_oo["ci_lo"] is not None and base_oo["ci_lo"] > 0
                   and base_tr["ci_lo"] is not None and base_tr["ci_lo"] > 0
                   and base_oo["n_events"] >= MIN_OOS_EVENTS)
    low = cells["LOW[.70,.86)"]
    low_ok = bool(low["oos"]["ci_lo"] is not None and low["oos"]["ci_lo"] > 0
                  and low["train"]["ci_lo"] is not None and low["train"]["ci_lo"] > 0
                  and low["oos"]["n_events"] >= MIN_OOS_EVENTS)
    print(f"  NO-side baseline confirms symmetric edge: {base_ok} | LOW band confirms: {low_ok}")
    return {"prefix": prefix, "baseline": {"train": base_tr, "oos": base_oo},
            "cells": cells, "baseline_confirms": base_ok, "low_confirms": low_ok}


def main() -> int:
    prefixes = sys.argv[1:] or ["KXMLBGAME", "KXATPMATCH", "KXWTAMATCH"]
    results = {p: analyze(p) for p in prefixes}
    out = REPO / "research" / "v18" / "05-underdog-no-results.json"
    out.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
