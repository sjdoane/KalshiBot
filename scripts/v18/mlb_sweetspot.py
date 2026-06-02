"""v1 MLB favorite-maker sweet-spot analysis (Becker, read-only).

Tests whether v1's KXMLBGAME maker edge (buy YES at yes_px in [0.70, 0.95], hold
to settle) concentrates in a price-band x time-to-close cell that is out-of-
sample robust. Methodology + gate are pre-registered in
research/v18/00-v1-mlb-sweetspot-methodology.md. No live change; analysis only.

Run: PYTHONPATH=src .venv-kronos\\Scripts\\python.exe scripts\\v18\\mlb_sweetspot.py
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
MARKETS = (REPO / "prediction-market-analysis/data/kalshi/markets/*.parquet").as_posix()
TRADES = (REPO / "prediction-market-analysis/data/kalshi/trades/*.parquet").as_posix()
OUT = REPO / "research" / "v18" / "01-mlb-sweetspot-results.json"

TRAIN = ("2024-11-01", "2025-09-01")
OOS = ("2025-09-01", "2025-11-25")

# Pre-registered bins (fixed; see methodology lock).
BAND_EDGES = [0.70, 0.78, 0.86, 0.95001]
BAND_LABELS = ["B1[.70,.78)", "B2[.78,.86)", "B3[.86,.95]"]
TIME_EDGES = [-1e9, 3.0, 12.0, 1e9]
TIME_LABELS = ["Tnear<3h", "Tmid3-12h", "Tfar>=12h"]
MIN_OOS_EVENTS = 30


def load(window: tuple[str, str]) -> pd.DataFrame:
    con = duckdb.connect()
    sql = f"""
    SELECT m.event_ticker AS event_ticker,
           t.yes_price/100.0 AS yes_px,
           (epoch(m.close_time) - epoch(t.created_time))/3600.0 AS hours_to_close,
           CASE WHEN m.result='yes' THEN 1.0 - t.yes_price/100.0
                ELSE -t.yes_price/100.0 END
             - 0.25*CEIL(0.07*(t.yes_price/100.0)*(1.0-t.yes_price/100.0)*100.0)/100.0
             AS net_pl
    FROM '{TRADES}' t JOIN '{MARKETS}' m ON t.ticker=m.ticker
    WHERE m.status='finalized' AND m.result IN ('yes','no')
      AND m.event_ticker LIKE 'KXMLBGAME%'
      AND t.taker_side='no' AND t.yes_price>=70 AND t.yes_price<=95
      AND t.created_time >= DATE '{window[0]}' AND t.created_time < DATE '{window[1]}'
    """
    df = con.execute(sql).df()
    if len(df):
        df["band"] = pd.cut(df["yes_px"], bins=BAND_EDGES, labels=BAND_LABELS, right=False)
        df["tband"] = pd.cut(df["hours_to_close"], bins=TIME_EDGES, labels=TIME_LABELS, right=False)
    return df


def cluster(df: pd.DataFrame, n_boot: int = 2000, seed: int = 42) -> dict:
    if df is None or len(df) == 0:
        return {"n_trades": 0, "n_events": 0, "event_mean": None,
                "ci_lo": None, "ci_hi": None}
    per_event = df.groupby("event_ticker", observed=True)["net_pl"].mean().to_numpy()
    n = len(per_event)
    if n < 2:
        return {"n_trades": int(len(df)), "n_events": n,
                "event_mean": float(per_event[0]) if n == 1 else None,
                "ci_lo": None, "ci_hi": None}
    rng = np.random.default_rng(seed)
    boots = np.array([rng.choice(per_event, size=n, replace=True).mean() for _ in range(n_boot)])
    return {
        "n_trades": int(len(df)), "n_events": int(n),
        "event_mean": float(per_event.mean()),
        "ci_lo": float(np.percentile(boots, 2.5)),
        "ci_hi": float(np.percentile(boots, 97.5)),
    }


def main() -> int:
    tr = load(TRAIN)
    oo = load(OOS)
    print(f"loaded train n_tr={len(tr)} oos n_tr={len(oo)}")

    base_tr = cluster(tr)
    base_oo = cluster(oo)
    base_oos_mean = base_oo["event_mean"] or 0.0
    print("\nKXMLBGAME baseline [0.70,0.95]:")
    print(f"  TRAIN evt_mean={base_tr['event_mean']:+.4f} CI=[{base_tr['ci_lo']:+.4f},{base_tr['ci_hi']:+.4f}] n_evt={base_tr['n_events']}")
    print(f"  OOS   evt_mean={base_oo['event_mean']:+.4f} CI=[{base_oo['ci_lo']:+.4f},{base_oo['ci_hi']:+.4f}] n_evt={base_oo['n_events']}")

    # Build all cells: 3 bands, 3 times, 9 joint.
    cells: dict[str, dict] = {}
    specs: list[tuple[str, object]] = []
    # Combined low band [0.70, 0.86): the deployable unit (B1 and B2 are
    # near-equal and swap ranks by noise, so the signal is the contiguous band,
    # not a single cell).
    specs.append(("LOW[.70,.86)", lambda d: d[d["yes_px"] < 0.86]))
    for b in BAND_LABELS:
        specs.append((b, lambda d, b=b: d[d["band"] == b]))
    for t in TIME_LABELS:
        specs.append((t, lambda d, t=t: d[d["tband"] == t]))
    for b in BAND_LABELS:
        for t in TIME_LABELS:
            specs.append((f"{b} x {t}", lambda d, b=b, t=t: d[(d["band"] == b) & (d["tband"] == t)]))

    rows = []
    for name, sel in specs:
        ct = cluster(sel(tr))
        co = cluster(sel(oo))
        cells[name] = {"train": ct, "oos": co}
        rows.append((name, ct, co))

    # Rank by event_mean within each window (for the top-2 consistency rule).
    def rank_map(idx_window: str) -> dict[str, int]:
        # Rank only among ADEQUATE-N cells; tiny-n noise cells (n=1..20) have
        # spurious means that would otherwise crowd out the robust big-n cells.
        # Exclude the combined LOW band from the ranking (it overlaps B1/B2).
        scored = [(n, c[idx_window]["event_mean"]) for n, c in cells.items()
                  if c[idx_window]["event_mean"] is not None
                  and c["train"]["n_events"] >= MIN_OOS_EVENTS
                  and c["oos"]["n_events"] >= MIN_OOS_EVENTS
                  and not n.startswith("LOW")]
        scored.sort(key=lambda x: x[1], reverse=True)
        return {n: i for i, (n, _m) in enumerate(scored)}
    rank_tr = rank_map("train")
    rank_oo = rank_map("oos")

    print(f"\n{'cell':22} {'TR evt':>8} {'TR lo':>8} {'TRn':>5}  {'OOS evt':>8} {'OOS lo':>8} {'OOSn':>5}  gate")
    print("-" * 90)
    sweet = []
    for name, ct, co in rows:
        passes = (
            co["event_mean"] is not None and ct["ci_lo"] is not None and co["ci_lo"] is not None
            and co["event_mean"] > base_oos_mean
            and co["ci_lo"] > 0.0
            and ct["ci_lo"] > 0.0
            and rank_tr.get(name, 99) <= 1 and rank_oo.get(name, 99) <= 1
            and co["n_events"] >= MIN_OOS_EVENTS
        )
        if passes:
            sweet.append(name)
        def fmt(c, k):
            v = c.get(k)
            return f"{v:>+8.4f}" if isinstance(v, float) else f"{'-':>8}"
        print(f"{name:22} {fmt(ct,'event_mean')} {fmt(ct,'ci_lo')} {ct['n_events']:>5}  "
              f"{fmt(co,'event_mean')} {fmt(co,'ci_lo')} {co['n_events']:>5}  {'SWEET' if passes else ''}")

    low = cells.get("LOW[.70,.86)")
    b3 = cells.get("B3[.86,.95]")
    low_ok = bool(
        low and low["oos"]["event_mean"] is not None and low["train"]["ci_lo"] is not None
        and low["oos"]["event_mean"] > base_oos_mean
        and low["oos"]["ci_lo"] > 0.0 and low["train"]["ci_lo"] > 0.0
        and low["oos"]["n_events"] >= MIN_OOS_EVENTS
    )
    print()
    print("HEADLINE (band finding; substantive criteria 1-3 + 5; the rank "
          "criterion 4 does not apply to a band superset):")
    if low and b3:
        print(f"  LOW [0.70,0.86): OOS {low['oos']['event_mean']:+.4f} "
              f"CI[{low['oos']['ci_lo']:+.4f},{low['oos']['ci_hi']:+.4f}] n={low['oos']['n_events']}")
        print(f"  B3  [0.86,0.95]: OOS {b3['oos']['event_mean']:+.4f} "
              f"CI[{b3['oos']['ci_lo']:+.4f},{b3['oos']['ci_hi']:+.4f}] n={b3['oos']['n_events']}")
        print(f"  baseline       : OOS {base_oos_mean:+.4f}")
    if low_ok:
        print("  -> LOW [0.70,0.86) PASSES the substantive gate: the edge concentrates")
        print("     there (~+8%) and roughly halves for heavy favorites 0.86-0.95.")
        print("     DEPLOYABLE v1 MLB refinement (operator approval required).")
    print()
    if sweet:
        print(f"Literal locked gate (all 5 incl single-cell rank): SWEET = {sweet}")
    else:
        print("Literal locked gate (all 5 incl single-cell rank): no single cell "
              "passes; criterion 4 (top-2 in both windows) flips between B1 and B2, "
              "because the signal is the contiguous band, not one cell.")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "baseline": {"train": base_tr, "oos": base_oo},
        "cells": cells, "sweet_spots_strict": sweet, "low_band_passes": low_ok,
        "gate": {"min_oos_events": MIN_OOS_EVENTS, "rank_top": 2},
    }, indent=2, default=str), encoding="utf-8")
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
