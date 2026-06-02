"""Generalized favorite-maker price-band analysis (Becker, read-only).

Same method as scripts/v18/mlb_sweetspot.py, parameterized by series prefix, to
test whether the v1 favorite-maker edge (buy YES maker at yes_px in [0.70,0.95],
hold to settle) concentrates in a price band on OTHER validated prefixes (e.g.
tennis KXATPMATCH / KXWTAMATCH). Methodology + gate as in
research/v18/00-v1-mlb-sweetspot-methodology.md. No live change; analysis only.

  PYTHONPATH=src .venv-kronos\\Scripts\\python.exe scripts\\v18\\band_analysis.py KXATPMATCH KXWTAMATCH
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
    SELECT m.event_ticker AS event_ticker, t.yes_price/100.0 AS yes_px,
           CASE WHEN m.result='yes' THEN 1.0 - t.yes_price/100.0
                ELSE -t.yes_price/100.0 END
             - 0.25*CEIL(0.07*(t.yes_price/100.0)*(1.0-t.yes_price/100.0)*100.0)/100.0
             AS net_pl
    FROM '{TRADES}' t JOIN '{MARKETS}' m ON t.ticker=m.ticker
    WHERE m.status='finalized' AND m.result IN ('yes','no')
      AND m.event_ticker LIKE '{prefix}%'
      AND t.taker_side='no' AND t.yes_price>=70 AND t.yes_price<=95
      AND t.created_time >= DATE '{window[0]}' AND t.created_time < DATE '{window[1]}'
    """
    df = con.execute(sql).df()
    if len(df):
        df["band"] = pd.cut(df["yes_px"], bins=BAND_EDGES, labels=BAND_LABELS, right=False)
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
    print(f"\n===== {prefix} =====  train n_tr={len(tr)} oos n_tr={len(oo)}")
    if base_oo["event_mean"] is None:
        print("  insufficient data")
        return {"prefix": prefix, "insufficient": True}
    print(f"  baseline [0.70,0.95]: TRAIN {base_tr['event_mean']:+.4f} "
          f"(lo {base_tr['ci_lo']:+.4f}) n={base_tr['n_events']} | "
          f"OOS {base_oo['event_mean']:+.4f} CI[{base_oo['ci_lo']:+.4f},{base_oo['ci_hi']:+.4f}] n={base_oo['n_events']}")
    cells = {}
    low_sel = lambda d: d[d["yes_px"] < 0.86]  # noqa: E731
    cells["LOW[.70,.86)"] = {"train": cluster(low_sel(tr)), "oos": cluster(low_sel(oo))}
    for b in BAND_LABELS:
        cells[b] = {"train": cluster(tr[tr["band"] == b]), "oos": cluster(oo[oo["band"] == b])}
    print(f"  {'cell':16} {'TR evt':>8} {'TR lo':>8} {'TRn':>5}  {'OOS evt':>8} {'OOS lo':>8} {'OOSn':>5}")
    for name, c in cells.items():
        ct, co = c["train"], c["oos"]
        def fmt(x):
            return f"{x:>+8.4f}" if isinstance(x, float) else f"{'-':>8}"
        print(f"  {name:16} {fmt(ct['event_mean'])} {fmt(ct['ci_lo'])} {ct['n_events']:>5}  "
              f"{fmt(co['event_mean'])} {fmt(co['ci_lo'])} {co['n_events']:>5}")
    low = cells["LOW[.70,.86)"]
    b3 = cells["B3[.86,.95]"]
    low_ok = bool(
        low["oos"]["event_mean"] is not None and low["train"]["ci_lo"] is not None
        and low["oos"]["event_mean"] > base_oo["event_mean"]
        and low["oos"]["ci_lo"] > 0.0 and low["train"]["ci_lo"] > 0.0
        and low["oos"]["n_events"] >= MIN_OOS_EVENTS
    )
    # Does the LOW>heavy band concentration hold (non-overlapping or LOW clearly above)?
    band_concentration = bool(
        low["oos"]["ci_lo"] is not None and b3["oos"]["ci_hi"] is not None
        and low["oos"]["ci_lo"] > b3["oos"]["ci_hi"]
    )
    print(f"  LOW passes substantive gate: {low_ok} | LOW-above-heavy (non-overlapping CIs): {band_concentration}")
    return {"prefix": prefix, "baseline": {"train": base_tr, "oos": base_oo},
            "cells": cells, "low_passes": low_ok, "band_concentration": band_concentration}


def main() -> int:
    prefixes = sys.argv[1:] or ["KXATPMATCH", "KXWTAMATCH"]
    results = {p: analyze(p) for p in prefixes}
    out = REPO / "research" / "v18" / "03-tennis-band-results.json"
    out.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
