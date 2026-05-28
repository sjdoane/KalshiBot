"""v7 Angle C: TabPFN v2 swap utilities for v6 and v5-B datasets.

Per `research/v7/04-tabpfn-methodology.md`. This module exposes a small set of
helpers used by `scripts/v7/run_tabpfn.py` so the swap logic stays unit-testable
even though no unit tests are required for the C4 diagnostic milestone.

Models compared
- TabPFN v2 (`tabpfn.TabPFNClassifier`, default hyperparameters).
- LightGBM (`lightgbm.LGBMClassifier`) with v6 M2 locked hyperparameters
  (max_depth=4, num_leaves=15, learning_rate=0.05, n_estimators=200) and
  early stopping on a 10 percent chronological val slice of train, patience 20.

Both fits use random_state=42 and the same train / orth-holdout split per
dataset.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss


SEED = 42

# v6 M2 locked LightGBM hyperparameters (from phase-1.5-methodology.md Section 5).
LGBM_PARAMS = {
    "max_depth": 4,
    "num_leaves": 15,
    "learning_rate": 0.05,
    "n_estimators": 200,
    "objective": "binary",
    "random_state": SEED,
    "verbose": -1,
}

# v6 candidate feature universe for the midband T-30 dataset. Matches v6
# orthogonality report Section 3 (Horizon T-30 min).
V6_T30_FEATURES = [
    "kalshi_cvd_30",
    "kalshi_trade_count_30",
    "coinbase_realized_vol_30",
    "coinbase_vwap_dev_30",
    "time_since_last_trade_at_t",
    "funding_rate_delta_4h_at_t",
    "dvol_delta_1h_at_t",
    "basis_delta_1h_at_t",
]

# v5-B orthogonality survivors (volume / PA-count proxies). Matches
# `research/v5/05-statcast-model.md` Section 2.2.
V5B_SURVIVOR_FEATURES = [
    "bat30_n_pitches",
    "bat30_n_pa",
    "bat7_n_pitches",
    "bat7_n_pa",
    "bat14_n_pitches",
    "bat14_n_pa",
    "batstd_n_pitches",
    "batstd_n_pa",
]


@dataclass
class SplitView:
    """Holds a chronological train / orthogonality / final split for one dataset.

    Attributes
    - df_train, df_orth, df_final: chronologically ordered subsets.
    - feature_cols: feature columns (excluding the price baseline).
    - mid_col: name of the price baseline column.
    - cluster_col: column used for cluster-bootstrap (whole-day cluster id).
    - target_col: outcome column name (binary 0/1).
    """

    df_train: pd.DataFrame
    df_orth: pd.DataFrame
    df_final: pd.DataFrame
    feature_cols: list[str]
    mid_col: str
    cluster_col: str
    target_col: str


def chronological_split(
    df: pd.DataFrame,
    time_col: str,
    train_frac: float = 0.60,
    orth_frac: float = 0.25,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Sort by `time_col` ascending then split 60 / 25 / 15 by row count.

    No purge buffer is applied at the row level here. The 24-hour purge is
    enforced by the caller as part of the dataset preparation (drop rows whose
    cluster is within 24h of a boundary).
    """
    sorted_df = df.sort_values(time_col).reset_index(drop=True)
    n = len(sorted_df)
    n_train = int(round(n * train_frac))
    n_orth = int(round(n * orth_frac))
    df_train = sorted_df.iloc[:n_train].copy()
    df_orth = sorted_df.iloc[n_train : n_train + n_orth].copy()
    df_final = sorted_df.iloc[n_train + n_orth :].copy()
    return df_train, df_orth, df_final


def apply_purge_24h(
    df_train: pd.DataFrame,
    df_orth: pd.DataFrame,
    df_final: pd.DataFrame,
    time_col: str,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Drop orth rows whose `time_col` is within 24h of train's max; drop final
    rows whose `time_col` is within 24h of orth's max. Matches the exact purge
    convention in v6 `scripts/v6/run_v6_orthogonality.py` (drop the LATER slice,
    not the earlier one, to keep train as large as possible).
    """
    purge = pd.Timedelta(hours=24)
    if len(df_train) and len(df_orth):
        train_close_max = df_train[time_col].max()
        df_orth = df_orth.loc[df_orth[time_col] >= train_close_max + purge].copy()
    if len(df_orth) and len(df_final):
        orth_close_max = df_orth[time_col].max()
        df_final = df_final.loc[df_final[time_col] >= orth_close_max + purge].copy()
    return df_train, df_orth, df_final


def drop_na_rows(
    df: pd.DataFrame, cols: list[str],
) -> pd.DataFrame:
    """Drop rows with NaN in any of the given columns."""
    return df.dropna(subset=cols).copy()


def fit_logreg_on_mid(
    df_train: pd.DataFrame, mid_col: str, target_col: str,
) -> LogisticRegression | None:
    """Fit a univariate logistic regression on `mid` only. Returns None on
    single-class training data.
    """
    sub = df_train.dropna(subset=[mid_col, target_col]).copy()
    if sub.empty:
        return None
    X = sub[[mid_col]].astype(float).to_numpy()
    y = sub[target_col].astype(int).to_numpy()
    if len(np.unique(y)) < 2:
        return None
    return LogisticRegression(
        C=10.0, max_iter=500, random_state=SEED,
    ).fit(X, y)


def predict_logreg(model: LogisticRegression, X: np.ndarray) -> np.ndarray:
    return model.predict_proba(X)[:, 1]


def fit_lightgbm(
    df_train: pd.DataFrame,
    feature_cols: list[str],
    target_col: str,
    val_frac: float = 0.10,
) -> tuple[Any, dict[str, Any]]:
    """Fit LightGBM with v6 M2 hyperparameters and early stopping on a
    chronological val slice. Returns (model, meta).
    """
    try:
        import lightgbm as lgb
    except ImportError:
        return None, {"error": "lightgbm not available"}
    sub = df_train.dropna(subset=feature_cols + [target_col]).copy()
    if len(sub) < 50:
        return None, {"error": "insufficient_data", "n": len(sub)}
    X = sub[feature_cols].astype(float).to_numpy()
    y = sub[target_col].astype(int).to_numpy()
    if len(np.unique(y)) < 2:
        return None, {"error": "single_class"}
    n_val = max(10, int(round(len(sub) * val_frac)))
    n_tr = len(sub) - n_val
    if n_tr < 20:
        return None, {"error": "train_too_small_after_val_split"}
    X_tr, X_val = X[:n_tr], X[n_tr:]
    y_tr, y_val = y[:n_tr], y[n_tr:]
    if len(np.unique(y_tr)) < 2 or len(np.unique(y_val)) < 2:
        # fall back to no early stopping if val slice ended up single-class
        model = lgb.LGBMClassifier(**LGBM_PARAMS).fit(X, y)
        return model, {"best_iter": int(model.n_estimators), "no_early_stop": True}
    model = lgb.LGBMClassifier(**LGBM_PARAMS)
    model.fit(
        X_tr, y_tr,
        eval_set=[(X_val, y_val)],
        eval_metric="binary_logloss",
        callbacks=[lgb.early_stopping(20, verbose=False)],
    )
    return model, {"best_iter": int(model.best_iteration_ or model.n_estimators)}


def fit_tabpfn(
    df_train: pd.DataFrame,
    feature_cols: list[str],
    target_col: str,
) -> tuple[Any, dict[str, Any]]:
    """Fit TabPFN v2 with default hyperparameters. CPU is fine at our scale.

    `ignore_pretraining_limits=True` lets TabPFN run on row / column counts
    near the practical limit without raising. v2's hard limit is ~10k rows;
    we honor that by subsampling upstream (see `run_tabpfn.py`).
    """
    try:
        from tabpfn import TabPFNClassifier
    except ImportError as exc:
        return None, {"error": f"tabpfn_import_failed: {exc}"}
    sub = df_train.dropna(subset=feature_cols + [target_col]).copy()
    if len(sub) < 10:
        return None, {"error": "insufficient_data", "n": len(sub)}
    X = sub[feature_cols].astype(float).to_numpy()
    y = sub[target_col].astype(int).to_numpy()
    if len(np.unique(y)) < 2:
        return None, {"error": "single_class"}
    model = TabPFNClassifier(
        random_state=SEED, ignore_pretraining_limits=True,
    )
    model.fit(X, y)
    return model, {"n_train": int(len(sub)), "n_features": int(X.shape[1])}


def predict_proba_safe(model: Any, X: np.ndarray) -> np.ndarray:
    """Return predict_proba positive-class column or NaN array if model is None."""
    if model is None:
        return np.full(X.shape[0], np.nan)
    return model.predict_proba(X)[:, 1]


def brier(y_true: np.ndarray, y_prob: np.ndarray) -> float:
    if len(y_true) == 0:
        return float("nan")
    mask = ~np.isnan(y_prob)
    if mask.sum() == 0:
        return float("nan")
    return float(brier_score_loss(y_true[mask], y_prob[mask]))


def cluster_bootstrap_brier_delta(
    y_true: np.ndarray,
    p_a: np.ndarray,
    p_b: np.ndarray,
    cluster_ids: np.ndarray,
    n_iter: int = 5000,
    seed: int = SEED,
) -> dict[str, float]:
    """Cluster-bootstrap on the Brier delta B(p_b) - B(p_a).

    Positive return means model A beats model B (lower Brier is better for A).
    For TabPFN-vs-LightGBM as `(p_a, p_b) = (tabpfn, lgbm)`, the delta returned
    is `Brier_LGBM - Brier_TabPFN`; positive means TabPFN is the better model.
    """
    rng = np.random.default_rng(seed)
    valid_mask = ~np.isnan(p_a) & ~np.isnan(p_b)
    y = y_true[valid_mask]
    a = p_a[valid_mask]
    b = p_b[valid_mask]
    c = cluster_ids[valid_mask]
    if len(y) == 0:
        return {
            "delta_point": float("nan"),
            "ci_low": float("nan"),
            "ci_high": float("nan"),
            "n_clusters": 0,
            "n_obs": 0,
        }
    unique = np.unique(c)
    cluster_to_idx: dict[Any, np.ndarray] = {
        cluster: np.flatnonzero(c == cluster) for cluster in unique
    }
    deltas = np.empty(n_iter, dtype=float)
    for i in range(n_iter):
        sampled = rng.choice(unique, size=len(unique), replace=True)
        idx = np.concatenate([cluster_to_idx[cluster] for cluster in sampled])
        deltas[i] = (
            brier_score_loss(y[idx], b[idx])
            - brier_score_loss(y[idx], a[idx])
        )
    point = float(
        brier_score_loss(y, b) - brier_score_loss(y, a),
    )
    return {
        "delta_point": point,
        "ci_low": float(np.percentile(deltas, 2.5)),
        "ci_high": float(np.percentile(deltas, 97.5)),
        "n_clusters": int(len(unique)),
        "n_obs": int(len(y)),
    }
