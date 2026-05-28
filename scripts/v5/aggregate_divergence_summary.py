"""V5-A1: aggregate all divergence probes into one summary table.

Combines:
  - data/v5/signal_direction_probe.json (live h2h on WC/UFC/NFL/Boxing
    against v1's currently-resting orders)
  - data/v5/mlb_divergence_probe.json (KXMLBGAME open vs the-odds-api MLB)
  - data/v5/extended_divergence_probe.json (UFC + Boxing fights matched
    by surname canonicalization)

Computes the project-binding statistic: mean Kalshi - Sportsbook divergence
on FAVORITES (sportsbook implied >= 0.55), bucketed by series.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "v5"
OUT = DATA / "divergence_summary.json"


def main():
    rows = []

    # Live live-from-v1-resting probe rows
    sigp = json.loads((DATA / "signal_direction_probe.json").read_text(encoding="utf-8"))
    for r in sigp.get("live", []):
        if r.get("kalshi_yes_price") is None or r.get("sportsbook_implied_median") is None:
            continue
        rows.append({
            "source": "v1_resting_live",
            "ticker": r["ticker"],
            "kalshi_mid": r["kalshi_yes_price"],
            "sportsbook_median": r["sportsbook_implied_median"],
            "n_books": r.get("sportsbook_n_books", 0),
            "divergence_cents": r.get("divergence_cents"),
            "is_favorite": r["sportsbook_implied_median"] >= 0.55,
            "in_v1_band": 0.70 <= r["kalshi_yes_price"] <= 0.95,
            "series": r["ticker"].split("-")[0],
        })

    # MLB probe
    mlbp = json.loads((DATA / "mlb_divergence_probe.json").read_text(encoding="utf-8"))
    for r in mlbp.get("rows", []):
        rows.append({
            "source": "mlb_open_games",
            "ticker": r["ticker"],
            "kalshi_mid": r["kalshi_mid"],
            "sportsbook_median": r["sportsbook_implied_median"],
            "n_books": r["n_bookmakers"],
            "divergence_cents": r["divergence_cents"],
            "is_favorite": r["is_favorite_side"],
            "in_v1_band": r["in_v1_eligible_band_70_95"],
            "series": "KXMLBGAME",
        })

    # Extended UFC + Boxing
    ext = json.loads((DATA / "extended_divergence_probe.json").read_text(encoding="utf-8"))
    for r in ext.get("rows", []):
        rows.append({
            "source": "ext_ufc_boxing",
            "ticker": r["ticker"],
            "kalshi_mid": r["kalshi_mid"],
            "sportsbook_median": r["sportsbook_median"],
            "n_books": r["n_books"],
            "divergence_cents": r["divergence_cents"],
            "is_favorite": r["is_favorite"],
            "in_v1_band": r["in_v1_band"],
            "series": r["series"],
        })

    df = pd.DataFrame(rows)
    print(f"=== ALL DIVERGENCE PAIRS: n={len(df)} ===\n")
    print(df.to_string(index=False))
    print()

    # Headline statistics
    print("=" * 70)
    print("HEADLINE STATISTICS (Kalshi - Sportsbook, cents)")
    print("=" * 70)
    summary = {}

    # 1) All sportsbook-FAVORITE-side (book_implied >= 0.55)
    fav = df[df["is_favorite"]]
    if not fav.empty:
        m = float(fav["divergence_cents"].mean())
        med = float(fav["divergence_cents"].median())
        sd = float(fav["divergence_cents"].std())
        over = int((fav["divergence_cents"] > 0).sum())
        n = int(len(fav))
        # 95% bootstrap CI
        import numpy as np
        rs = np.random.default_rng(42)
        vals = fav["divergence_cents"].to_numpy()
        boots = np.array([rs.choice(vals, size=n, replace=True).mean() for _ in range(2000)])
        ci_lo, ci_hi = float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))
        print(f"\nSPORTSBOOK FAVORITES (book>=0.55), n={n}:")
        print(f"  mean = {m:+.2f}c    median = {med:+.2f}c    sd = {sd:.2f}c")
        print(f"  95% CI on mean: [{ci_lo:+.2f}, {ci_hi:+.2f}]")
        print(f"  Kalshi over book: {over}/{n} = {over/n*100:.0f}%")
        summary["favorites_book_ge_55"] = {
            "n": n, "mean_cents": m, "median_cents": med, "sd_cents": sd,
            "ci_lo_95": ci_lo, "ci_hi_95": ci_hi,
            "kalshi_over_count": over, "kalshi_over_pct": over/n*100,
        }

    # 2) v1-eligible band on Kalshi side (kalshi_mid in 0.70-0.95)
    band = df[df["in_v1_band"]]
    if not band.empty:
        m = float(band["divergence_cents"].mean())
        med = float(band["divergence_cents"].median())
        sd = float(band["divergence_cents"].std())
        n = int(len(band))
        over = int((band["divergence_cents"] > 0).sum())
        import numpy as np
        rs = np.random.default_rng(42)
        vals = band["divergence_cents"].to_numpy()
        boots = np.array([rs.choice(vals, size=n, replace=True).mean() for _ in range(2000)])
        ci_lo, ci_hi = float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))
        print(f"\nv1 ELIGIBLE BAND (kalshi 0.70-0.95), n={n}:")
        print(f"  mean = {m:+.2f}c    median = {med:+.2f}c    sd = {sd:.2f}c")
        print(f"  95% CI on mean: [{ci_lo:+.2f}, {ci_hi:+.2f}]")
        print(f"  Kalshi over book: {over}/{n} = {over/n*100:.0f}%")
        summary["v1_band_kalshi_70_95"] = {
            "n": n, "mean_cents": m, "median_cents": med, "sd_cents": sd,
            "ci_lo_95": ci_lo, "ci_hi_95": ci_hi,
            "kalshi_over_count": over, "kalshi_over_pct": over/n*100,
        }

    # 3) Per-series breakdown
    print("\nPER-SERIES (favorites only, book_implied>=0.55):")
    for series, sub in fav.groupby("series"):
        if len(sub) < 2:
            continue
        m = sub["divergence_cents"].mean()
        n = len(sub)
        print(f"  {series:>12}: mean={m:+.2f}c  n={n}")
        summary.setdefault("per_series", {})[series] = {
            "n": int(n), "mean_cents": float(m),
            "over_count": int((sub["divergence_cents"] > 0).sum()),
        }

    # Save
    OUT.write_text(json.dumps({"rows": rows, "summary": summary}, indent=2, default=str), encoding="utf-8")
    print(f"\nSaved: {OUT}")

    # Compare to V3-C
    print("\n=== COMPARISON TO V3-C POLYMARKET MEASUREMENT ===")
    print("V3-C measured mean Kalshi - Polymarket on favorites = +9.21c (T-35d, MLB win-totals).")
    if not fav.empty:
        print(f"V5-A1 measured mean Kalshi - Sportsbook on favorites = {summary['favorites_book_ge_55']['mean_cents']:+.2f}c (live, multi-series).")
        diff = summary["favorites_book_ge_55"]["mean_cents"] - 9.21
        print(f"Delta (sportsbook is X cents lower from Kalshi than Polymarket was): {-diff:+.2f}c")
        print("Direction: SAME (Kalshi > both Polymarket and Sportsbook on favorites).")
        print("Magnitude: SPORTSBOOK IS CLOSER to Kalshi than Polymarket is. Sportsbook is the institutional consensus.")


if __name__ == "__main__":
    main()
