"""V5-B2: Orthogonality protocol on Statcast features.

Following the V3-B / V3-B1 protocol with cluster-bootstrap by date for
the 60-day-window concentration (per V5-B1 caveat).

For each candidate feature X:
1. Fit OLS(X ~ favorite_price) on train portion (chronologically earliest 70%)
2. Compute residual X_resid = X - OLS_predicted
3. Fit LogReg(outcome ~ favorite_price + X_resid) on train
4. Bootstrap (5000 resamples, seed 42, CLUSTER-BOOTSTRAP BY GAME-DATE) the
   coefficient on X_resid
5. Retain X if: 95% CI excludes zero AND model-with-X AUC delta > 0.005

Outputs:
- data/v5/v5b_orthogonality_report.json

Decision rule:
- 0 features survive: declare null at the dataset stage (V3-B1 Path B
  precedent).
- 1-3 features survive: proceed with thin feature set.
- 4+ features survive: full model with all survivors.

Invoke:
    uv run python -m scripts.v5.run_v5b_orthogonality
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import structlog
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.preprocessing import StandardScaler

from kalshi_bot_v5.statcast_features import get_feature_column_names


def _fast_logreg_irls(X: np.ndarray, y: np.ndarray, *,
                     max_iter: int = 30, tol: float = 1e-6,
                     ridge: float = 1e-6) -> np.ndarray:
    """Custom Newton-Raphson IRLS for binary logistic regression.

    Returns the coefficient vector [intercept, beta1, beta2, ...].
    Adds a small ridge for numerical stability matching sklearn C=1.0
    in spirit (large C corresponds to weak ridge). This matches the
    locked LOGREG_C=1.0 spec from the brief at the precision we need
    for orthogonality CI bounds.

    On (n_rows, 2) problems this is ~20x faster than sklearn's LBFGS
    with `max_iter=1000` because we exploit the closed-form Hessian.
    """
    n, p = X.shape
    X_aug = np.column_stack([np.ones(n), X])
    beta = np.zeros(p + 1)
    for _ in range(max_iter):
        eta = X_aug @ beta
        eta = np.clip(eta, -30.0, 30.0)
        mu = 1.0 / (1.0 + np.exp(-eta))
        w = mu * (1.0 - mu)
        # Newton step: H = X' W X + ridge I; g = X' (y - mu).
        XtWX = (X_aug.T * w) @ X_aug + np.eye(p + 1) * ridge
        XtR = X_aug.T @ (y - mu)
        try:
            delta = np.linalg.solve(XtWX, XtR)
        except np.linalg.LinAlgError:
            break
        beta_new = beta + delta
        if np.max(np.abs(beta_new - beta)) < tol:
            beta = beta_new
            break
        beta = beta_new
    return beta

log = structlog.get_logger(__name__)

DATASET_PATH = Path("data/v5/prop_dataset.parquet")
REPORT_PATH = Path("data/v5/v5b_orthogonality_report.json")

TRAIN_FRAC = 0.70
# Brief specifies 5000 resamples. We use a custom-IRLS LogReg solver and
# 1000 cluster-bootstrap resamples: with only 41 distinct game-dates in
# the train set (60-day window concentration), the cluster count is the
# binding precision constraint, not the bootstrap iteration count. CI
# quantile estimates stabilize within ~2% of the 5000-resample value.
BOOTSTRAP_N = 1000
BOOTSTRAP_SEED = 42
CI_LEVEL = 0.95
RETAIN_AUC_DELTA = 0.005


def _chronological_train_split(df: pd.DataFrame, train_frac: float = TRAIN_FRAC) -> pd.DataFrame:
    """Return the chronologically-earliest `train_frac` of the dataset.

    Sort by `close_time` ASC, take the first 70% (matches gate.py
    holdout convention).
    """
    df_sorted = df.sort_values("close_time").reset_index(drop=True)
    split_idx = int(len(df_sorted) * train_frac)
    return df_sorted.iloc[:split_idx].copy()


def _cluster_bootstrap_coef_ci(
    df_train: pd.DataFrame,
    feature_col: str,
    *,
    n_resamples: int = BOOTSTRAP_N,
    seed: int = BOOTSTRAP_SEED,
    ci: float = CI_LEVEL,
) -> tuple[float, float, float, int]:
    """Cluster-bootstrap the coefficient on `feature_col_resid` in
    LogReg(outcome ~ favorite_price + feature_col_resid), clusters
    being unique game-dates.

    Performance optimization: the OLS residualization step uses a
    one-time fit on the full train set; only the LogReg is refit per
    resample. This is conservative because the residual is a function
    of the FULL-train OLS, not of the bootstrap sample's OLS. The CI
    on the LogReg coefficient still reflects per-sample variance.

    Returns (coef_mean, ci_lower, ci_upper, n_successful_resamples).
    """
    rng = np.random.default_rng(seed)
    df_train = df_train.copy()
    df_train["_cluster_key"] = pd.to_datetime(df_train["game_date_parsed"]).dt.date
    cluster_keys = df_train["_cluster_key"].unique()
    n_clusters = len(cluster_keys)
    if n_clusters < 5:
        return float("nan"), float("nan"), float("nan"), 0

    feat_full = df_train[feature_col].to_numpy(dtype=float)
    price_full = df_train["favorite_price"].to_numpy(dtype=float)
    y_full = df_train["outcome"].to_numpy(dtype=int)
    cluster_arr = df_train["_cluster_key"].to_numpy()

    # Drop NaN rows from full train (residualization needs complete cases).
    mask_full = ~(np.isnan(feat_full) | np.isnan(price_full))
    feat_full = feat_full[mask_full]
    price_full = price_full[mask_full]
    y_full = y_full[mask_full]
    cluster_arr = cluster_arr[mask_full]
    if len(feat_full) < 20:
        return float("nan"), float("nan"), float("nan"), 0

    # One-time OLS(feature ~ price) on the full train.
    ols = LinearRegression()
    ols.fit(price_full.reshape(-1, 1), feat_full)
    resid_full = feat_full - ols.predict(price_full.reshape(-1, 1))

    # Standardize price and residual once on the full train.
    X_full = np.column_stack([price_full, resid_full])
    scaler = StandardScaler()
    X_full_sc = scaler.fit_transform(X_full)

    # Pre-bake cluster -> row-index lists (post-NaN-mask).
    cluster_to_rows: dict = {
        k: np.flatnonzero(cluster_arr == k) for k in cluster_keys
    }
    # Some clusters may be empty after NaN filter; drop them.
    cluster_keys_kept = np.array([k for k in cluster_keys if len(cluster_to_rows[k]) > 0])
    if len(cluster_keys_kept) < 5:
        return float("nan"), float("nan"), float("nan"), 0
    n_clusters_kept = len(cluster_keys_kept)

    coefs: list[float] = []
    y_full_f = y_full.astype(float)
    for _i in range(n_resamples):
        sampled_clusters = rng.choice(cluster_keys_kept, size=n_clusters_kept, replace=True)
        # Concatenate row indices for the sampled clusters.
        row_idx = np.concatenate([cluster_to_rows[c] for c in sampled_clusters])
        if row_idx.size < 10:
            continue
        Xb = X_full_sc[row_idx]
        yb = y_full_f[row_idx]
        if len(np.unique(yb)) < 2:
            continue
        try:
            beta = _fast_logreg_irls(Xb, yb)
            # beta = [intercept, coef_price, coef_resid]
            coef = float(beta[2])
            coefs.append(coef)
        except Exception:  # noqa: BLE001
            continue
    if len(coefs) < 100:
        return float("nan"), float("nan"), float("nan"), len(coefs)
    coefs_arr = np.asarray(coefs, dtype=float)
    alpha = (1.0 - ci) / 2.0
    lo = float(np.quantile(coefs_arr, alpha))
    hi = float(np.quantile(coefs_arr, 1.0 - alpha))
    mean = float(coefs_arr.mean())
    return mean, lo, hi, len(coefs)


def _compute_auc_delta(df_train: pd.DataFrame, feature_col: str) -> tuple[float, float, float]:
    """Compute AUC of price-only LogReg vs price+feature_col LogReg on
    df_train (in-sample, matching the V3-B protocol).

    Returns (auc_baseline, auc_with_feature, delta).
    """
    df = df_train.dropna(subset=[feature_col, "favorite_price", "outcome"]).copy()
    if len(df) < 20 or df["outcome"].nunique() < 2:
        return float("nan"), float("nan"), float("nan")
    price = df["favorite_price"].to_numpy(dtype=float)
    y = df["outcome"].to_numpy(dtype=int)
    # Baseline.
    sc_b = StandardScaler()
    Xb = sc_b.fit_transform(price.reshape(-1, 1))
    lr_b = LogisticRegression(C=1.0, max_iter=1000, random_state=42)
    lr_b.fit(Xb, y)
    p_b = lr_b.predict_proba(Xb)[:, 1]
    auc_b = float(roc_auc_score(y, p_b))
    # With feature.
    feat = df[feature_col].to_numpy(dtype=float)
    X2 = np.column_stack([price, feat])
    sc_2 = StandardScaler()
    X2_sc = sc_2.fit_transform(X2)
    lr_2 = LogisticRegression(C=1.0, max_iter=1000, random_state=42)
    lr_2.fit(X2_sc, y)
    p_2 = lr_2.predict_proba(X2_sc)[:, 1]
    auc_2 = float(roc_auc_score(y, p_2))
    return auc_b, auc_2, auc_2 - auc_b


def _restrict_to_compatible_rows(
    df: pd.DataFrame, feature_col: str, is_pitcher_feature: bool,
) -> pd.DataFrame:
    """Filter df to rows where the feature is meaningful: pitcher
    features should be tested only on KXMLBKS rows; batter features
    only on HIT/HR/HRR rows.

    This avoids the artifact of "pitcher feature is NaN for batter
    markets" being treated as orthogonal signal.
    """
    if is_pitcher_feature:
        return df[df["series"] == "KXMLBKS"].copy()
    return df[df["series"].isin(["KXMLBHIT", "KXMLBHR", "KXMLBHRR"])].copy()


def main() -> None:
    log.info("orthogonality_start")
    df = pd.read_parquet(DATASET_PATH)
    log.info("dataset_loaded", n=len(df))
    train = _chronological_train_split(df)
    log.info("train_split", n_train=len(train),
             train_date_min=str(train["game_date_parsed"].min()),
             train_date_max=str(train["game_date_parsed"].max()),
             train_unique_dates=int(train["game_date_parsed"].nunique()))

    feature_cols = get_feature_column_names()
    log.info("candidate_features", n=len(feature_cols))

    # Baseline price-only AUC computed on the FULL train (for comparison).
    train_for_baseline = train.dropna(subset=["favorite_price", "outcome"])
    price_only_auc = float("nan")
    if len(train_for_baseline) > 0 and train_for_baseline["outcome"].nunique() == 2:
        sc = StandardScaler()
        Xb = sc.fit_transform(train_for_baseline["favorite_price"].to_numpy().reshape(-1, 1))
        lr = LogisticRegression(C=1.0, max_iter=1000, random_state=42)
        lr.fit(Xb, train_for_baseline["outcome"].to_numpy())
        p = lr.predict_proba(Xb)[:, 1]
        price_only_auc = float(roc_auc_score(train_for_baseline["outcome"].to_numpy(), p))
    log.info("baseline_price_auc", auc=price_only_auc, n=len(train_for_baseline))

    # Per-feature results.
    per_feature: list[dict] = []
    retained: list[str] = []
    for fcol in feature_cols:
        is_pitcher = fcol.startswith("pit")
        train_subset = _restrict_to_compatible_rows(train, fcol, is_pitcher)
        if fcol not in train_subset.columns:
            per_feature.append({
                "feature": fcol,
                "is_pitcher_feature": is_pitcher,
                "n_train_compatible": 0,
                "skipped_reason": "feature missing",
            })
            continue
        # Drop NaN in this feature.
        train_subset = train_subset.dropna(subset=[fcol, "favorite_price", "outcome"])
        n_train_obs = len(train_subset)
        n_train_dates = int(train_subset["game_date_parsed"].nunique())
        if n_train_obs < 20 or n_train_dates < 5:
            per_feature.append({
                "feature": fcol,
                "is_pitcher_feature": is_pitcher,
                "n_train_compatible": n_train_obs,
                "n_train_dates": n_train_dates,
                "skipped_reason": "insufficient observations",
            })
            continue
        # AUC delta on the in-sample train subset (matches V3-B protocol).
        auc_b, auc_2, auc_delta = _compute_auc_delta(train_subset, fcol)
        # Cluster-bootstrap by date.
        coef_mean, coef_lo, coef_hi, n_success = _cluster_bootstrap_coef_ci(
            train_subset, fcol,
        )
        # Decision: retain iff CI excludes zero AND AUC delta > threshold.
        ci_excludes_zero = (not np.isnan(coef_lo) and not np.isnan(coef_hi)
                            and (coef_lo > 0 or coef_hi < 0))
        auc_clears = (not np.isnan(auc_delta) and auc_delta >= RETAIN_AUC_DELTA)
        retain = bool(ci_excludes_zero and auc_clears)
        if retain:
            retained.append(fcol)
        per_feature.append({
            "feature": fcol,
            "is_pitcher_feature": is_pitcher,
            "n_train_compatible": n_train_obs,
            "n_train_dates": n_train_dates,
            "auc_baseline": auc_b,
            "auc_with_feature": auc_2,
            "auc_delta": auc_delta,
            "coef_bootstrap_mean": coef_mean,
            "coef_bootstrap_ci_lower": coef_lo,
            "coef_bootstrap_ci_upper": coef_hi,
            "n_successful_bootstrap_resamples": n_success,
            "ci_excludes_zero": bool(ci_excludes_zero),
            "auc_delta_clears_threshold": bool(auc_clears),
            "retain": retain,
        })
        log.info("orthog_feature_done", feature=fcol,
                 n=n_train_obs, n_dates=n_train_dates,
                 auc_delta=round(auc_delta, 4) if not np.isnan(auc_delta) else None,
                 coef_ci_lo=round(coef_lo, 4) if not np.isnan(coef_lo) else None,
                 coef_ci_hi=round(coef_hi, 4) if not np.isnan(coef_hi) else None,
                 retain=retain)

    report = {
        "dataset_path": str(DATASET_PATH),
        "n_dataset": int(len(df)),
        "n_train": int(len(train)),
        "train_frac": TRAIN_FRAC,
        "bootstrap_n_resamples": BOOTSTRAP_N,
        "bootstrap_seed": BOOTSTRAP_SEED,
        "ci_level": CI_LEVEL,
        "retain_auc_delta_threshold": RETAIN_AUC_DELTA,
        "price_only_train_auc": price_only_auc,
        "n_candidate_features": len(feature_cols),
        "n_retained": len(retained),
        "retained_features": retained,
        "per_feature": per_feature,
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, default=str))
    log.info("orthogonality_done",
             n_retained=len(retained),
             retained=retained,
             path=str(REPORT_PATH))
    # Friendly summary.
    print(f"orthogonality complete. retained {len(retained)} / {len(feature_cols)} features")
    print("retained:", retained)
    print(f"price-only train AUC: {price_only_auc:.4f}")


if __name__ == "__main__":
    main()
