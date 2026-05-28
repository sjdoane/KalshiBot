"""V5-C2 pivot midband orthogonality probe.

Same as run_v5c_orthogonality_probe.py but reads
v5c_pivot_midband_data.parquet (price band [0.55, 0.80]).

Run: uv run python -m scripts.v5.run_v5c_pivot_midband_probe
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "v5"))

from scripts.v5 import run_v5c_orthogonality_probe as probe_base

DATA_DIR = REPO_ROOT / "data" / "v5"
DATASET_PATH = DATA_DIR / "v5c_pivot_midband_data.parquet"
REPORT_PATH = DATA_DIR / "v5c_pivot_midband_report.json"


def log(msg: str) -> None:
    print(f"[{pd.Timestamp.now(tz='UTC').isoformat()}] {msg}", flush=True)


def main() -> int:
    if not DATASET_PATH.exists():
        log(f"ERROR: dataset not found at {DATASET_PATH}")
        return 1
    df = pd.read_parquet(DATASET_PATH)
    log(f"Loaded midband [0.55, 0.80] dataset: n={len(df)}, yes_rate={df['outcome'].mean():.4f}")
    log(f"NOs total: {(df['outcome']==0).sum()}")
    df_sorted = df.sort_values("close_time")
    split = int(len(df_sorted) * probe_base.TRAIN_FRAC)
    log(
        f"Train: n={split}, NOs={(df_sorted.iloc[:split]['outcome']==0).sum()}; "
        f"Test: n={len(df_sorted)-split}, NOs={(df_sorted.iloc[split:]['outcome']==0).sum()}",
    )

    te = probe_base.measure_tracking_error(df)
    log(f"Tracking error: {te}")

    log("Running orthogonality probe per feature ...")
    feat_reports = {}
    for c in probe_base.FEATURE_COLS:
        r = probe_base.evaluate_feature(df, c)
        feat_reports[c] = r
        log(
            f"  {c}: decision={r.get('decision')}, "
            f"n_no_train={r.get('n_no_train', 'na')}, "
            f"brier_improve={r.get('brier_improvement', float('nan')):.5f}, "
            f"auc_delta={r.get('auc_delta', float('nan')):.4f}, "
            f"coef_ci=[{r.get('coef_ci_lower', float('nan')):.4f}, {r.get('coef_ci_upper', float('nan')):.4f}]",
        )

    retained = [c for c, r in feat_reports.items() if r.get("retain")]
    log(f"Features retained: {len(retained)}: {retained}")

    work = df.dropna(subset=["favorite_price", "outcome"]).sort_values("close_time")
    split = int(len(work) * probe_base.TRAIN_FRAC)
    test = work.iloc[split:]
    baseline_brier_naive = float(np.mean((test["favorite_price"] - test["outcome"]) ** 2))

    report = {
        "dataset_path": str(DATASET_PATH),
        "pivot": "midband [0.55, 0.80]",
        "n_total": int(len(df)),
        "yes_rate_total": float(df["outcome"].mean()),
        "date_range": [str(df["close_time"].min()), str(df["close_time"].max())],
        "feature_coverage": {c: int(df[c].notna().sum()) for c in probe_base.FEATURE_COLS},
        "tracking_error": te,
        "feature_reports": feat_reports,
        "features_retained": retained,
        "verdict": (
            "NULL_AT_ORTHOGONALITY_MIDBAND" if not retained
            else f"PROCEED_WITH_{len(retained)}_FEATURES_MIDBAND"
        ),
        "thresholds": {
            "AUC_DELTA": probe_base.AUC_DELTA_THRESHOLD,
            "BRIER_IMPROVE": probe_base.BRIER_IMPROVE_THRESHOLD,
            "BOOTSTRAP_N": probe_base.BOOTSTRAP_N,
            "BOOTSTRAP_SEED": probe_base.BOOTSTRAP_SEED,
            "TRAIN_FRAC": probe_base.TRAIN_FRAC,
        },
        "baseline_naive_price_brier_holdout": baseline_brier_naive,
    }
    with open(REPORT_PATH, "w") as f:
        json.dump(report, f, indent=2, default=str)
    log(f"Wrote {REPORT_PATH}")
    log(f"VERDICT: {report['verdict']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
