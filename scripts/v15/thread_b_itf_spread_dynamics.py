"""v15 Round 20 Thread B: ITF orderbook spread vs time-to-close.

Pre-registered gates (research/v15/01-methodology-lock.md):
  B-G1: n_orderbook_snapshots >= 1000 across ITF prefixes
  B-G2: OLS slope of spread on time-to-close is negative (spread
        widens as close approaches; slope on minutes_to_close < 0)
  B-G3: Median spread in last-30-min window > median spread overall
        by at least 2c (0.02 dollars)
  B-G4: Cluster bootstrap CI on (last-30-min mean spread minus
        overall mean spread) excludes zero with positive lower bound

Source data: data/v10a/itf_orderbook_log.parquet (17 snapshots, 268
tickers covering KXITFMATCH and KXITFWMATCH).

Output:
  research/v15/03-thread-b-results.json
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
OB_PATH = REPO / "data" / "v10a" / "itf_orderbook_log.parquet"
OUT_JSON = REPO / "research" / "v15" / "03-thread-b-results.json"


def load_and_compute_ttc():
    ob = pd.read_parquet(OB_PATH)
    ob["ts_utc"] = pd.to_datetime(ob["ts_utc"], utc=True)
    ob["close_time"] = pd.to_datetime(ob["close_time"], utc=True,
                                       errors="coerce")
    ob = ob.dropna(subset=["close_time"])
    ob["minutes_to_close"] = (
        (ob["close_time"] - ob["ts_utc"]).dt.total_seconds() / 60.0
    )
    # Only keep rows where the market is still open (minutes_to_close > 0)
    # AND has a defined spread (yes_bid and yes_ask present from parser).
    ob = ob[(ob["minutes_to_close"] > 0) & (ob["spread"].notna())]
    return ob


def ols_slope(x: np.ndarray, y: np.ndarray) -> dict:
    """Simple OLS y = a + b*x. Returns slope, intercept, r2."""
    if len(x) < 5:
        return {"slope": None, "intercept": None, "r2": None}
    a, b = np.polyfit(x, y, 1)  # a is slope, b is intercept
    y_pred = a * x + b
    ss_res = ((y - y_pred) ** 2).sum()
    ss_tot = ((y - y.mean()) ** 2).sum()
    r2 = float(1 - ss_res / ss_tot) if ss_tot > 0 else None
    return {"slope": float(a), "intercept": float(b), "r2": r2}


def cluster_bootstrap_diff_spread(
    overall: pd.DataFrame, near_close: pd.DataFrame,
    n_boot: int = 1000, seed: int = 42,
) -> dict:
    """Bootstrap CI on (near_close mean spread - overall mean spread)
    by sampling tickers with replacement."""
    overall_per_ticker = overall.groupby("ticker")["spread"].mean()
    near_per_ticker = near_close.groupby("ticker")["spread"].mean()
    rng = np.random.default_rng(seed)
    diffs = []
    overall_tickers = overall_per_ticker.index.to_numpy()
    near_tickers = near_per_ticker.index.to_numpy()
    if len(overall_tickers) < 2 or len(near_tickers) < 2:
        return {"diff_point": None}
    for _ in range(n_boot):
        o_sample = rng.choice(overall_tickers, size=len(overall_tickers),
                               replace=True)
        n_sample = rng.choice(near_tickers, size=len(near_tickers),
                               replace=True)
        o_mean = overall_per_ticker.loc[o_sample].mean()
        n_mean = near_per_ticker.loc[n_sample].mean()
        diffs.append(n_mean - o_mean)
    diffs = np.array(diffs)
    return {
        "n_overall_tickers": int(len(overall_tickers)),
        "n_near_close_tickers": int(len(near_tickers)),
        "mean_spread_overall": float(overall_per_ticker.mean()),
        "mean_spread_near_close": float(near_per_ticker.mean()),
        "diff_point": float(near_per_ticker.mean() - overall_per_ticker.mean()),
        "diff_ci_lo": float(np.percentile(diffs, 2.5)),
        "diff_ci_hi": float(np.percentile(diffs, 97.5)),
    }


def main():
    ob = load_and_compute_ttc()
    print(f"Total snapshots with positive TTC + spread: {len(ob)}")
    print(f"Unique tickers: {ob['ticker'].nunique()}")
    print(f"Prefix breakdown:")
    print(ob.groupby("prefix").size())
    print()

    # B-G1
    g1_pass = len(ob) >= 1000

    # B-G2: OLS slope of spread on minutes_to_close
    slope_full = ols_slope(
        ob["minutes_to_close"].to_numpy(),
        ob["spread"].to_numpy(),
    )
    print(f"OLS spread vs minutes_to_close (all ITF): "
          f"slope={slope_full.get('slope')}, "
          f"intercept={slope_full.get('intercept')}, "
          f"r2={slope_full.get('r2')}")

    # Per-prefix slopes too
    slopes_by_prefix = {}
    for prefix, sub in ob.groupby("prefix"):
        s = ols_slope(sub["minutes_to_close"].to_numpy(),
                      sub["spread"].to_numpy())
        slopes_by_prefix[prefix] = s
        print(f"  {prefix} slope={s.get('slope')}, r2={s.get('r2')}")

    # B-G2 pass condition: full-sample slope is negative (more TTC -> smaller
    # spread; equivalently, less TTC -> larger spread, i.e. spreads widen
    # near close).
    g2_pass = (slope_full.get("slope") is not None
               and slope_full["slope"] < 0)

    # B-G3 / B-G4: compare last 30-min vs overall
    near = ob[ob["minutes_to_close"] <= 30]
    print(f"\nLast-30-min subset: n_rows={len(near)}, "
          f"unique tickers={near['ticker'].nunique()}")
    g3_diff = float(near["spread"].median() - ob["spread"].median())
    g3_pass = g3_diff >= 0.02
    print(f"Median spread overall: {ob['spread'].median():.4f}")
    print(f"Median spread last-30-min: {near['spread'].median():.4f}")
    print(f"Difference: {g3_diff:+.4f} (G3 needs >= 0.02 to PASS)")

    bs = cluster_bootstrap_diff_spread(ob, near)
    print(f"\nBootstrap diff (last-30-min mean - overall mean), "
          f"clustered by ticker:")
    if bs.get("diff_point") is None:
        print("  insufficient data")
        g4_pass = False
    else:
        print(f"  diff = {bs['diff_point']:+.4f}, "
              f"CI = [{bs['diff_ci_lo']:+.4f}, {bs['diff_ci_hi']:+.4f}]")
        g4_pass = bs.get("diff_ci_lo", -1) > 0

    gates = {
        "B-G1 (n_snapshots >= 1000)": (g1_pass, f"n = {len(ob)}"),
        "B-G2 (OLS slope negative)": (
            g2_pass, f"slope = {slope_full.get('slope')}",
        ),
        "B-G3 (median diff >= 2c)": (
            g3_pass, f"diff = {g3_diff:+.4f}",
        ),
        "B-G4 (CI lower > 0)": (
            g4_pass,
            f"diff CI lo = {bs.get('diff_ci_lo')}",
        ),
    }

    print("\n=== Gate verdict ===")
    pass_count = 0
    fail_count = 0
    for name, (passed, detail) in gates.items():
        marker = "PASS" if passed else "FAIL"
        print(f"  [{marker}] {name}: {detail}")
        if passed:
            pass_count += 1
        else:
            fail_count += 1

    if pass_count == 4:
        verdict = "SHADOW-CANDIDATE (refine ITF maker quote timing)"
    elif pass_count == 3:
        verdict = "MARGINAL"
    else:
        verdict = "NULL"
    print(f"\nVerdict: {verdict} ({pass_count} pass / {fail_count} fail)")

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "n_rows": int(len(ob)),
        "n_tickers": int(ob["ticker"].nunique()),
        "ols_full": slope_full,
        "ols_by_prefix": slopes_by_prefix,
        "near_30min_summary": {
            "n_rows": int(len(near)),
            "n_tickers": int(near["ticker"].nunique()),
            "median_spread_overall": float(ob["spread"].median()),
            "median_spread_near_close": float(near["spread"].median()),
            "median_diff": g3_diff,
        },
        "bootstrap_diff": bs,
        "gates": {
            k: {"pass": v[0], "detail": v[1]} for k, v in gates.items()
        },
        "verdict": verdict,
        "n_pass": pass_count,
        "n_fail": fail_count,
    }
    with open(OUT_JSON, "w") as f:
        json.dump(payload, f, indent=2, default=str)
    print(f"\nSaved {OUT_JSON}")


if __name__ == "__main__":
    main()
