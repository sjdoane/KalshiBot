"""V5-C2 orthogonality probe.

For each candidate feature X:
1. Sample X (already in v5c_orthogonality_data.parquet) at T-1h (open_time) before close.
2. Fit OLS(X ~ favorite_price) on the FULL sample; take residual X_resid.
3. Chronological 70/30 split.
4. Fit LogReg(outcome ~ favorite_price + X_resid) on train.
5. Bootstrap (5000 resamples, seed 42) the coefficient on X_resid.
6. Compare AUC and Brier of model-with-X vs baseline (price-only LogReg) on holdout.
7. Retain X if 95% CI excludes zero AND AUC delta >= 0.005 AND Brier improvement >= 0.005.

Also measures Coinbase-vs-BRTI tracking error at market close.

Saves to data/v5/v5c_orthogonality_report.json.

Run: uv run python -m scripts.v5.run_v5c_orthogonality_probe
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
sys.path.insert(0, str(REPO_ROOT / "src"))

DATA_DIR = REPO_ROOT / "data" / "v5"
DATASET_PATH = DATA_DIR / "v5c_orthogonality_data.parquet"
REPORT_PATH = DATA_DIR / "v5c_orthogonality_report.json"

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
TRAIN_FRAC = 0.7
BOOTSTRAP_N = 5000
BOOTSTRAP_SEED = 42
AUC_DELTA_THRESHOLD = 0.005
BRIER_IMPROVE_THRESHOLD = 0.005


def log(msg: str) -> None:
    print(f"[{pd.Timestamp.now(tz='UTC').isoformat()}] {msg}", flush=True)


def measure_tracking_error(df: pd.DataFrame) -> dict:
    """Coinbase BTC-USD spot at market close vs back-computed BRTI bracket.

    The bracket is (max yes_threshold, min no_threshold). BRTI is in that
    range. Take the midpoint as the BRTI estimate. Tracking error =
    coinbase_at_close - brti_estimate, normalized by brti_estimate.
    """
    sub = df.dropna(subset=["brti_estimate", "coinbase_at_close"]).copy()
    if sub.empty:
        return {"n": 0, "note": "no rows with BRTI bracket + Coinbase close"}
    sub["tracking_err_dollars"] = sub["coinbase_at_close"] - sub["brti_estimate"]
    sub["tracking_err_pct"] = sub["tracking_err_dollars"] / sub["brti_estimate"]
    summary = {
        "n": int(len(sub)),
        "mean_err_dollars": float(sub["tracking_err_dollars"].mean()),
        "median_err_dollars": float(sub["tracking_err_dollars"].median()),
        "abs_mean_err_dollars": float(sub["tracking_err_dollars"].abs().mean()),
        "mean_err_pct": float(sub["tracking_err_pct"].mean()),
        "abs_mean_err_pct": float(sub["tracking_err_pct"].abs().mean()),
        "p95_abs_err_pct": float(sub["tracking_err_pct"].abs().quantile(0.95)),
        "p99_abs_err_pct": float(sub["tracking_err_pct"].abs().quantile(0.99)),
        "note": (
            "BRTI bracket from sibling thresholds: max(yes) < BRTI < min(no). "
            "Estimate = bracket midpoint. Bracket precision = $100 (KXBTCD strike spacing). "
            "Reported tracking_err_pct lower bound = bracket precision / spot."
        ),
    }
    return summary


def bootstrap_coef_ci(
    X_train: np.ndarray,
    y_train: np.ndarray,
    n_resamples: int = BOOTSTRAP_N,
    seed: int = BOOTSTRAP_SEED,
    ci: float = 0.95,
) -> tuple[float, float, float]:
    """Bootstrap CI on the X_resid (last column) coefficient of LogReg.

    Returns (point, lo, hi).
    """
    rng = np.random.default_rng(seed)
    n = len(y_train)
    coefs: list[float] = []
    for _ in range(n_resamples):
        idx = rng.integers(0, n, size=n)
        Xb = X_train[idx]
        yb = y_train[idx]
        if len(np.unique(yb)) < 2:
            continue  # single-class bootstrap; skip
        try:
            m = LogisticRegression(C=10.0, max_iter=500)
            m.fit(Xb, yb)
            coefs.append(float(m.coef_[0, -1]))
        except Exception:
            continue
    if not coefs:
        return float("nan"), float("nan"), float("nan")
    arr = np.array(coefs)
    lo = float(np.percentile(arr, (1 - ci) / 2 * 100))
    hi = float(np.percentile(arr, (1 + ci) / 2 * 100))
    point = float(arr.mean())
    return point, lo, hi


def orthogonalize(df: pd.DataFrame, feat_col: str) -> np.ndarray:
    """Residual of OLS(X ~ favorite_price) on the FULL sample. Standardize
    price input to avoid coef scale weirdness.
    """
    mask = df[feat_col].notna() & df[PRICE_COL].notna()
    sub = df.loc[mask]
    X = sub[[PRICE_COL]].to_numpy()
    y = sub[feat_col].to_numpy()
    reg = LinearRegression().fit(X, y)
    pred = reg.predict(X)
    resid = y - pred
    out = np.full(len(df), np.nan)
    out[mask.to_numpy().nonzero()[0]] = resid
    return out


def evaluate_feature(df: pd.DataFrame, feat_col: str) -> dict:
    """Run the orthogonality probe for one feature."""
    work = df.dropna(subset=[feat_col, PRICE_COL, OUTCOME_COL]).copy()
    work = work.sort_values("close_time").reset_index(drop=True)
    n_total = len(work)
    if n_total < 30:
        return {
            "feature": feat_col,
            "n": n_total,
            "decision": "drop_insufficient_n",
        }

    work["X_resid"] = orthogonalize(work, feat_col)

    split_idx = int(n_total * TRAIN_FRAC)
    train = work.iloc[:split_idx]
    test = work.iloc[split_idx:]

    n_no_train = int((train[OUTCOME_COL] == 0).sum())
    n_no_test = int((test[OUTCOME_COL] == 0).sum())
    if n_no_train < 2 or len(np.unique(train[OUTCOME_COL])) < 2:
        return {
            "feature": feat_col,
            "n": n_total,
            "n_train": int(len(train)),
            "n_test": int(len(test)),
            "n_no_train": n_no_train,
            "decision": "drop_train_single_class",
        }

    # Baseline: price only
    X_train_base = train[[PRICE_COL]].to_numpy()
    X_test_base = test[[PRICE_COL]].to_numpy()
    y_train = train[OUTCOME_COL].to_numpy()
    y_test = test[OUTCOME_COL].to_numpy()
    base_model = LogisticRegression(C=10.0, max_iter=500).fit(X_train_base, y_train)
    base_pred_test = base_model.predict_proba(X_test_base)[:, 1]
    base_brier = float(np.mean((base_pred_test - y_test) ** 2))
    try:
        base_auc = float(roc_auc_score(y_test, base_pred_test)) if len(np.unique(y_test)) > 1 else float("nan")
    except ValueError:
        base_auc = float("nan")

    # With feature
    X_train_full = train[[PRICE_COL, "X_resid"]].to_numpy()
    X_test_full = test[[PRICE_COL, "X_resid"]].to_numpy()
    full_model = LogisticRegression(C=10.0, max_iter=500).fit(X_train_full, y_train)
    full_pred_test = full_model.predict_proba(X_test_full)[:, 1]
    full_brier = float(np.mean((full_pred_test - y_test) ** 2))
    try:
        full_auc = float(roc_auc_score(y_test, full_pred_test)) if len(np.unique(y_test)) > 1 else float("nan")
    except ValueError:
        full_auc = float("nan")

    # Bootstrap CI on the X_resid coefficient
    coef_point, coef_lo, coef_hi = bootstrap_coef_ci(X_train_full, y_train)

    auc_delta = (full_auc - base_auc) if not np.isnan(base_auc) else float("nan")
    brier_improve = (base_brier - full_brier)  # positive = full model is better

    ci_excludes_zero = (not np.isnan(coef_lo)) and (coef_lo > 0 or coef_hi < 0)
    auc_passes = (not np.isnan(auc_delta)) and (auc_delta >= AUC_DELTA_THRESHOLD)
    brier_passes = brier_improve >= BRIER_IMPROVE_THRESHOLD

    retain = ci_excludes_zero and auc_passes and brier_passes

    return {
        "feature": feat_col,
        "n": n_total,
        "n_train": int(len(train)),
        "n_test": int(len(test)),
        "n_no_train": n_no_train,
        "n_no_test": n_no_test,
        "base_brier": base_brier,
        "full_brier": full_brier,
        "brier_improvement": brier_improve,
        "base_auc": base_auc,
        "full_auc": full_auc,
        "auc_delta": auc_delta,
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
    if not DATASET_PATH.exists():
        log(f"ERROR: dataset not found at {DATASET_PATH}; run build_v5c_orthogonality_dataset first")
        return 1
    df = pd.read_parquet(DATASET_PATH)
    log(f"Loaded dataset: n={len(df)}")
    log(f"Feature coverage:")
    for c in FEATURE_COLS:
        log(f"  {c}: n_non_null={int(df[c].notna().sum())}")

    # Tracking error analysis
    te = measure_tracking_error(df)
    log(f"Tracking error: {te}")

    # Per-feature orthogonality
    log("Running orthogonality probe per feature ...")
    feat_reports = {}
    for c in FEATURE_COLS:
        r = evaluate_feature(df, c)
        feat_reports[c] = r
        log(
            f"  {c}: decision={r.get('decision')}, "
            f"brier_improve={r.get('brier_improvement', float('nan')):.5f}, "
            f"auc_delta={r.get('auc_delta', float('nan')):.4f}, "
            f"coef_ci=[{r.get('coef_ci_lower', float('nan')):.4f}, {r.get('coef_ci_upper', float('nan')):.4f}]",
        )

    retained = [c for c, r in feat_reports.items() if r.get("retain")]
    log(f"Features retained: {len(retained)}: {retained}")

    # Calibration summary on holdout, baseline only
    work = df.dropna(subset=[PRICE_COL, OUTCOME_COL]).sort_values("close_time")
    split = int(len(work) * TRAIN_FRAC)
    test = work.iloc[split:]
    baseline_brier_naive = float(np.mean((test[PRICE_COL] - test[OUTCOME_COL]) ** 2))

    report = {
        "dataset_path": str(DATASET_PATH),
        "n_total": int(len(df)),
        "yes_rate_total": float(df[OUTCOME_COL].mean()),
        "date_range": [str(df["close_time"].min()), str(df["close_time"].max())],
        "feature_coverage": {c: int(df[c].notna().sum()) for c in FEATURE_COLS},
        "tracking_error": te,
        "feature_reports": feat_reports,
        "features_retained": retained,
        "verdict": (
            "NULL_AT_ORTHOGONALITY" if not retained
            else f"PROCEED_WITH_{len(retained)}_FEATURES"
        ),
        "thresholds": {
            "AUC_DELTA": AUC_DELTA_THRESHOLD,
            "BRIER_IMPROVE": BRIER_IMPROVE_THRESHOLD,
            "BOOTSTRAP_N": BOOTSTRAP_N,
            "BOOTSTRAP_SEED": BOOTSTRAP_SEED,
            "TRAIN_FRAC": TRAIN_FRAC,
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
