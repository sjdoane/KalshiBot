"""V10-B Brier delta analyzer for resolved forecasts.

Joins forecasts (data/v10/v10b_forecasts.parquet) with resolutions
(data/v10/v10b_resolutions.parquet) and computes Brier delta with
95% bootstrap CI. Per-sport breakdown for LOCO sanity.

Per B3 methodology:
    SHIP:    Brier_delta >= 0.010 AND 95% bootstrap CI > 0
    PARTIAL: 0.005 <= Brier_delta < 0.010 AND 95% bootstrap CI > 0
    NULL:    Brier_delta < 0.005 OR CI includes zero

n >= 80 for verdict (per B2 Section 4.7). Below that, descriptive only.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd

FORECASTS_PATH = PROJECT_ROOT / "data" / "v10" / "v10b_forecasts.parquet"
RESOLUTIONS_PATH = PROJECT_ROOT / "data" / "v10" / "v10b_resolutions.parquet"

N_BOOTSTRAP = 10_000
GATE_SHIP = 0.010
GATE_PARTIAL = 0.005
N_MIN_VERDICT = 80


def brier(p: np.ndarray, y: np.ndarray) -> float:
    return float(np.mean((p - y) ** 2))


def bootstrap_delta_ci(p_market: np.ndarray, p_v10: np.ndarray, y: np.ndarray, n_iter: int = N_BOOTSTRAP) -> tuple[float, float, float]:
    """Returns (point_delta, ci_low, ci_high) where delta = Brier_market - Brier_v10."""
    rng = np.random.default_rng(seed=42)
    n = len(y)
    deltas = []
    for _ in range(n_iter):
        idx = rng.integers(0, n, n)
        bm = brier(p_market[idx], y[idx])
        bv = brier(p_v10[idx], y[idx])
        deltas.append(bm - bv)
    deltas = np.array(deltas)
    point = brier(p_market, y) - brier(p_v10, y)
    return point, float(np.percentile(deltas, 2.5)), float(np.percentile(deltas, 97.5))


def main() -> None:
    if not FORECASTS_PATH.exists():
        print(f"ERROR: forecasts parquet not found at {FORECASTS_PATH}")
        sys.exit(1)
    if not RESOLUTIONS_PATH.exists():
        print(f"ERROR: resolutions parquet not found at {RESOLUTIONS_PATH}")
        print("Run scripts/v10/poll_v10b_resolutions.py first.")
        sys.exit(1)

    df_f = pd.read_parquet(FORECASTS_PATH)
    df_r = pd.read_parquet(RESOLUTIONS_PATH)

    # Drop pre-existing outcome col in forecasts (placeholder); use resolutions outcome
    if "outcome" in df_f.columns:
        df_f = df_f.drop(columns=["outcome"])

    df = df_f.merge(df_r[["ticker", "outcome", "status", "result"]], on="ticker", how="left")
    df_resolved = df[df["outcome"].notna()].copy()
    df_resolved["outcome"] = df_resolved["outcome"].astype(int)

    n_resolved = len(df_resolved)
    n_total = len(df)
    print(f"Forecasts: {n_total}")
    print(f"Resolved: {n_resolved}")
    print(f"Open: {n_total - n_resolved}")

    if n_resolved == 0:
        print("\nNo resolutions yet. Re-run poll later.")
        sys.exit(0)

    # Extract arrays
    p_market = df_resolved["orderbook_mid"].values
    p_v10 = df_resolved["p_v10"].values
    y = df_resolved["outcome"].values

    # Overall Brier
    bm = brier(p_market, y)
    bv = brier(p_v10, y)
    delta = bm - bv

    print(f"\n=== OVERALL (n={n_resolved}) ===")
    print(f"Brier_market: {bm:.5f}")
    print(f"Brier_v10:    {bv:.5f}")
    print(f"Brier_delta:  {delta:+.5f}")

    if n_resolved >= 10:
        point, ci_low, ci_high = bootstrap_delta_ci(p_market, p_v10, y)
        print(f"Bootstrap 95% CI: [{ci_low:+.5f}, {ci_high:+.5f}]")

        if n_resolved >= N_MIN_VERDICT:
            if delta >= GATE_SHIP and ci_low > 0:
                verdict = "SHIP"
            elif delta >= GATE_PARTIAL and ci_low > 0:
                verdict = "PARTIAL"
            else:
                verdict = "NULL"
        else:
            verdict = f"DESCRIPTIVE (n={n_resolved} < {N_MIN_VERDICT})"
        print(f"Verdict: {verdict}")

    # Per-sport breakdown
    print(f"\n=== PER SPORT ===")
    for sport, sub in df_resolved.groupby("sport_group"):
        sn = len(sub)
        sbm = brier(sub["orderbook_mid"].values, sub["outcome"].values.astype(int))
        sbv = brier(sub["p_v10"].values, sub["outcome"].values.astype(int))
        sdelta = sbm - sbv
        print(f"  {sport:>8} (n={sn}): B_mkt={sbm:.4f} B_v10={sbv:.4f} delta={sdelta:+.4f}")

    # Vendor coverage on resolved subset
    print(f"\n=== VENDOR COVERAGE (resolved) ===")
    def get_vendors(row):
        vu = row.get("vendors_used")
        if isinstance(vu, str): return json.loads(vu) if vu else []
        if vu is None: return []
        return list(vu)
    df_resolved["n_vendors"] = df_resolved.apply(lambda r: len(get_vendors(r)), axis=1)
    print(df_resolved["n_vendors"].value_counts().sort_index())

    # Outcome split
    print(f"\n=== OUTCOMES ===")
    print(f"YES: {(y==1).sum()}, NO: {(y==0).sum()}")

    # Top signals (highest |p_v10 - mid|) on resolved subset
    df_resolved["signal_abs"] = (df_resolved["p_v10"] - df_resolved["orderbook_mid"]).abs()
    df_resolved["signed_delta"] = df_resolved["p_v10"] - df_resolved["orderbook_mid"]
    df_resolved["llm_correct"] = np.where(
        ((df_resolved["signed_delta"] > 0) & (df_resolved["outcome"] == 1))
        | ((df_resolved["signed_delta"] < 0) & (df_resolved["outcome"] == 0)),
        1, 0
    )
    print(f"\n=== TOP SIGNALS (|p_v10 - mid|, resolved only) ===")
    top = df_resolved.sort_values("signal_abs", ascending=False).head(15)
    for _, r in top.iterrows():
        correct = "OK" if r["llm_correct"] == 1 else "MISS"
        print(f"  {r['ticker'][:50]:50} mid={r['orderbook_mid']:.3f} p_v10={r['p_v10']:.3f} delta={r['signed_delta']:+.3f} y={int(r['outcome'])} {correct}")

    # When LLM disagrees by > 5c, who wins?
    df_resolved["disagree_5c"] = df_resolved["signal_abs"] > 0.05
    disagree = df_resolved[df_resolved["disagree_5c"]]
    if len(disagree):
        bm_d = brier(disagree["orderbook_mid"].values, disagree["outcome"].values.astype(int))
        bv_d = brier(disagree["p_v10"].values, disagree["outcome"].values.astype(int))
        win_rate = disagree["llm_correct"].mean()
        print(f"\n=== ON >5c DISAGREEMENT (n={len(disagree)}) ===")
        print(f"  LLM correct rate: {win_rate*100:.1f}% (vs 50% null)")
        print(f"  Brier_market: {bm_d:.4f}, Brier_v10: {bv_d:.4f}, delta: {bm_d-bv_d:+.4f}")


if __name__ == "__main__":
    main()
