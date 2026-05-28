"""V5-C2 supplementary orthogonality probe using FULL sample (no train/test split).

The default chronological 70/30 split puts 3 of 4 NOs in the test set, leaving
the train set with only 1 NO and a degenerate LogReg. This supplementary probe
fits LogReg on the FULL 200-row sample (with bootstrap), so the bootstrap
captures sampling variance over the 4 NOs.

This is NOT a holdout test (no OOS evaluation); it's a check on whether each
feature has a coefficient that is statistically different from zero conditional
on price.

Read as: "if the feature is collinear with price, the bootstrap CI of the coefficient
on X_resid should straddle zero". This is the original orthogonality protocol
(v3-B audit Section "Orthogonality check protocol") in its purest form.

Saves to data/v5/v5c_orthogonality_full_sample_report.json.

Run: uv run python -m scripts.v5.run_v5c_orthogonality_probe_full_sample
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.metrics import roc_auc_score

REPO_ROOT = Path(__file__).resolve().parents[2]

DATA_DIR = REPO_ROOT / "data" / "v5"
DATASET_PATH = DATA_DIR / "v5c_orthogonality_data.parquet"
REPORT_PATH = DATA_DIR / "v5c_orthogonality_full_sample_report.json"

FEATURE_COLS = [
    "f1_realized_vol_1h",
    "f2_vwap_dev_1h",
    "f3_spot_futures_basis",
    "f4_funding_rate_1h",
    "f6_active_addr_delta",
    "f7_dxy_24h_change",
    "f8_hashrate_24h_change",
]

PRICE_COL = "favorite_price"
OUTCOME_COL = "outcome"
BOOTSTRAP_N = 5000
SEED = 42
AUC_DELTA_THRESHOLD = 0.005
BRIER_IMPROVE_THRESHOLD = 0.005


def log(msg: str) -> None:
    print(f"[{pd.Timestamp.now(tz='UTC').isoformat()}] {msg}", flush=True)


def orthogonalize(df: pd.DataFrame, feat_col: str) -> np.ndarray:
    mask = df[feat_col].notna() & df[PRICE_COL].notna()
    sub = df.loc[mask]
    reg = LinearRegression().fit(sub[[PRICE_COL]], sub[feat_col])
    pred = reg.predict(sub[[PRICE_COL]])
    resid = sub[feat_col].to_numpy() - pred
    out = np.full(len(df), np.nan)
    out[mask.to_numpy().nonzero()[0]] = resid
    return out


def evaluate_feature_full(df: pd.DataFrame, feat_col: str) -> dict:
    work = df.dropna(subset=[feat_col, PRICE_COL, OUTCOME_COL]).copy()
    n = len(work)
    if n < 30:
        return {"feature": feat_col, "n": n, "decision": "drop_insufficient_n"}
    work["X_resid"] = orthogonalize(work, feat_col)
    n_no = int((work[OUTCOME_COL] == 0).sum())

    X_base = work[[PRICE_COL]].to_numpy()
    X_full = work[[PRICE_COL, "X_resid"]].to_numpy()
    y = work[OUTCOME_COL].to_numpy()
    base_model = LogisticRegression(C=10.0, max_iter=500).fit(X_base, y)
    base_pred = base_model.predict_proba(X_base)[:, 1]
    full_model = LogisticRegression(C=10.0, max_iter=500).fit(X_full, y)
    full_pred = full_model.predict_proba(X_full)[:, 1]
    base_brier = float(np.mean((base_pred - y) ** 2))
    full_brier = float(np.mean((full_pred - y) ** 2))
    try:
        base_auc = float(roc_auc_score(y, base_pred))
        full_auc = float(roc_auc_score(y, full_pred))
    except ValueError:
        base_auc = float("nan")
        full_auc = float("nan")

    rng = np.random.default_rng(SEED)
    coefs: list[float] = []
    n_skip = 0
    for _ in range(BOOTSTRAP_N):
        idx = rng.integers(0, n, size=n)
        Xb = X_full[idx]
        yb = y[idx]
        if len(np.unique(yb)) < 2:
            n_skip += 1
            continue
        try:
            m = LogisticRegression(C=10.0, max_iter=500).fit(Xb, yb)
            coefs.append(float(m.coef_[0, -1]))
        except Exception:
            n_skip += 1
            continue
    if not coefs:
        return {
            "feature": feat_col, "n": n, "n_no": n_no,
            "decision": "drop_all_resamples_failed",
        }
    coefs = np.array(coefs)
    coef_lo = float(np.percentile(coefs, 2.5))
    coef_hi = float(np.percentile(coefs, 97.5))
    coef_point = float(coefs.mean())

    ci_excludes_zero = coef_lo > 0 or coef_hi < 0
    auc_delta = full_auc - base_auc if not np.isnan(base_auc) else float("nan")
    brier_improve = base_brier - full_brier

    auc_passes = (not np.isnan(auc_delta)) and (auc_delta >= AUC_DELTA_THRESHOLD)
    brier_passes = brier_improve >= BRIER_IMPROVE_THRESHOLD
    retain = ci_excludes_zero and auc_passes and brier_passes

    return {
        "feature": feat_col,
        "n": n,
        "n_no": n_no,
        "n_bootstrap_resamples_used": len(coefs),
        "n_bootstrap_resamples_skipped": n_skip,
        "base_brier_insample": base_brier,
        "full_brier_insample": full_brier,
        "brier_improvement_insample": brier_improve,
        "base_auc_insample": base_auc,
        "full_auc_insample": full_auc,
        "auc_delta_insample": auc_delta,
        "coef_point": coef_point,
        "coef_ci_lower": coef_lo,
        "coef_ci_upper": coef_hi,
        "ci_excludes_zero": ci_excludes_zero,
        "auc_passes": auc_passes,
        "brier_passes": brier_passes,
        "retain": retain,
        "decision": "retain" if retain else "drop",
    }


def main() -> int:
    df = pd.read_parquet(DATASET_PATH)
    log(f"Loaded n={len(df)}, yes_rate={df[OUTCOME_COL].mean():.4f}")

    feat_reports = {}
    for c in FEATURE_COLS:
        r = evaluate_feature_full(df, c)
        feat_reports[c] = r
        log(
            f"  {c}: decision={r.get('decision')}, "
            f"n_used={r.get('n_bootstrap_resamples_used', 'na')}, "
            f"brier_improve_insample={r.get('brier_improvement_insample', float('nan')):.5f}, "
            f"auc_delta_insample={r.get('auc_delta_insample', float('nan')):.4f}, "
            f"coef_ci=[{r.get('coef_ci_lower', float('nan')):.4f}, {r.get('coef_ci_upper', float('nan')):.4f}]",
        )

    retained = [c for c, r in feat_reports.items() if r.get("retain")]
    log(f"Features retained (in-sample full-sample probe): {len(retained)}: {retained}")
    report = {
        "method": "FULL_SAMPLE_INSAMPLE_BOOTSTRAP",
        "note": (
            "This is the v3-B audit orthogonality protocol fit on the FULL n=200 "
            "sample. NOT a holdout test. Used because the chronological 70/30 split "
            "puts only 1 NO in train (degenerate LogReg). The bootstrap captures "
            "sampling variance over the 4 NOs."
        ),
        "n_total": int(len(df)),
        "yes_rate_total": float(df[OUTCOME_COL].mean()),
        "feature_reports": feat_reports,
        "features_retained": retained,
        "verdict": (
            "NULL_AT_ORTHOGONALITY_FULL_SAMPLE" if not retained
            else f"INSAMPLE_SIGNAL_{len(retained)}_FEATURES"
        ),
    }
    with open(REPORT_PATH, "w") as f:
        json.dump(report, f, indent=2, default=str)
    log(f"Wrote {REPORT_PATH}")
    log(f"VERDICT: {report['verdict']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
