"""v6 model training and decision-rule evaluation.

Per phase-1.5-methodology.md Section 5 + 6.

M1: Logistic regression with L2 reg, C tuned by 5-fold time-series CV.
M2: LightGBM (max_depth=4, num_leaves=15, lr=0.05, n_iter<=200, early stop).

Decision rules:
- Rule A: +2c-take rule (taker, fill at ask, range 0.20-0.85)
- Rule B: maker-quote rule (15% effective fill rate, range 0.30-0.85)
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from typing import Any

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss

try:
    import lightgbm as lgb
    HAS_LGB = True
except ImportError:
    HAS_LGB = False


SEED = 42


def time_series_cv_folds(n: int, k: int = 5) -> list[tuple[np.ndarray, np.ndarray]]:
    """Expanding-window CV folds (no shuffle). Returns list of (train_idx, val_idx)."""
    folds = []
    fold_size = n // (k + 1)
    if fold_size < 5:
        return folds
    for i in range(1, k + 1):
        train_end = fold_size * i
        val_end = fold_size * (i + 1)
        train_idx = np.arange(0, train_end)
        val_idx = np.arange(train_end, val_end)
        folds.append((train_idx, val_idx))
    return folds


def fit_logreg_with_cv(
    train: pd.DataFrame,
    feature_cols: list[str],
    target_col: str = "outcome_yes",
    C_candidates: Iterable[float] = (0.01, 0.1, 1.0, 10.0, 100.0),
) -> tuple[LogisticRegression, dict[str, Any]]:
    """Fit LogReg with 5-fold time-series CV on C."""
    sub = train.dropna(subset=feature_cols + [target_col]).copy()
    X = sub[feature_cols].astype(float).to_numpy()
    y = sub[target_col].astype(int).to_numpy()
    if len(np.unique(y)) < 2:
        return None, {"error": "single-class"}
    n = len(sub)
    folds = time_series_cv_folds(n, k=5)
    if not folds:
        # fallback: fit on full
        model = LogisticRegression(C=10.0, max_iter=500, random_state=SEED).fit(X, y)
        return model, {"C": 10.0, "n_folds": 0}

    scores = {}
    for C in C_candidates:
        fold_briers = []
        for tr_idx, va_idx in folds:
            if len(np.unique(y[tr_idx])) < 2:
                continue
            m = LogisticRegression(C=C, max_iter=500, random_state=SEED).fit(
                X[tr_idx], y[tr_idx],
            )
            p = m.predict_proba(X[va_idx])[:, 1]
            fold_briers.append(brier_score_loss(y[va_idx], p))
        if fold_briers:
            scores[C] = float(np.mean(fold_briers))
    if not scores:
        model = LogisticRegression(C=10.0, max_iter=500, random_state=SEED).fit(X, y)
        return model, {"C": 10.0, "n_folds": 0, "scores": {}}

    best_C = min(scores, key=scores.get)
    model = LogisticRegression(C=best_C, max_iter=500, random_state=SEED).fit(X, y)
    return model, {"C": best_C, "cv_scores": scores}


def fit_lightgbm(
    train: pd.DataFrame,
    feature_cols: list[str],
    target_col: str = "outcome_yes",
    val_frac: float = 0.10,
) -> tuple[Any, dict[str, Any]]:
    """Fit LightGBM with early stopping on a 10% chronological val slice."""
    if not HAS_LGB:
        return None, {"error": "lightgbm not available"}
    sub = train.dropna(subset=feature_cols + [target_col]).copy()
    if len(sub) < 50 or len(np.unique(sub[target_col])) < 2:
        return None, {"error": "insufficient data"}
    X = sub[feature_cols].astype(float).to_numpy()
    y = sub[target_col].astype(int).to_numpy()
    n_val = max(10, int(round(len(sub) * val_frac)))
    n_tr = len(sub) - n_val
    X_tr, X_val = X[:n_tr], X[n_tr:]
    y_tr, y_val = y[:n_tr], y[n_tr:]
    if len(np.unique(y_tr)) < 2 or len(np.unique(y_val)) < 2:
        return None, {"error": "single-class slice"}
    model = lgb.LGBMClassifier(
        max_depth=4,
        num_leaves=15,
        learning_rate=0.05,
        n_estimators=200,
        random_state=SEED,
        objective="binary",
        verbose=-1,
    )
    model.fit(
        X_tr, y_tr,
        eval_set=[(X_val, y_val)],
        eval_metric="binary_logloss",
        callbacks=[lgb.early_stopping(20, verbose=False)],
    )
    return model, {"best_iter": int(model.best_iteration_ or model.n_estimators)}


def predict_proba(model: Any, X: np.ndarray) -> np.ndarray:
    return model.predict_proba(X)[:, 1]


def calibrate_isotonic(
    cal_probs: np.ndarray,
    cal_y: np.ndarray,
) -> IsotonicRegression:
    iso = IsotonicRegression(out_of_bounds="clip").fit(cal_probs, cal_y)
    return iso


def expected_calibration_error(
    probs: np.ndarray,
    y: np.ndarray,
    bins: int = 10,
) -> float:
    if len(probs) == 0:
        return float("nan")
    edges = np.linspace(0.0, 1.0, bins + 1)
    ece = 0.0
    n = len(probs)
    for i in range(bins):
        lo, hi = edges[i], edges[i + 1]
        mask = (probs >= lo) & (probs < hi if i < bins - 1 else probs <= hi)
        if mask.sum() == 0:
            continue
        bin_prob = probs[mask].mean()
        bin_truth = y[mask].mean()
        ece += (mask.sum() / n) * abs(bin_prob - bin_truth)
    return float(ece)


# ---------------------------------------------------------------------------
# Fees and decision rules
# ---------------------------------------------------------------------------

def kalshi_fee_cents(
    contracts: int,
    price: float,
    taker: bool,
) -> float:
    """Per Kalshi published fee formula (per-side):
    - Taker: ceil(0.07 * C * P * (1 - P) * 100 cents) per side
    - Maker: ceil(0.0175 * C * P * (1 - P) * 100 cents) per side

    contracts in #, price in [0, 1].
    Returns fee in CENTS.
    """
    rate = 0.07 if taker else 0.0175
    raw = rate * contracts * price * (1.0 - price) * 100.0
    return math.ceil(raw)


def rule_a_pnl_per_contract(
    model_prob: float,
    mid: float,
    outcome_yes: int,
    spread_c: float = 0.02,
) -> tuple[str, float]:
    """Rule A: +2c-take rule. Returns (side, pnl_in_cents) or ('none', 0.0).

    side in {'yes', 'no', 'none'}. pnl is in cents.
    Fee uses contracts=1 (per-contract P&L).
    """
    yes_ask = mid + spread_c / 2.0
    yes_bid = mid - spread_c / 2.0
    # symmetry between yes_ask and no_ask
    no_ask = 1.0 - yes_bid
    if (
        model_prob >= yes_ask + 0.02
        and 0.20 <= yes_ask <= 0.85
    ):
        # BUY YES at yes_ask
        gross = (1.0 - yes_ask) if outcome_yes == 1 else -yes_ask
        fee_cents = kalshi_fee_cents(1, yes_ask, taker=True)
        pnl_c = gross * 100.0 - fee_cents
        return "yes", pnl_c
    if (
        (1.0 - model_prob) >= no_ask + 0.02
        and 0.20 <= no_ask <= 0.85
    ):
        # BUY NO at no_ask
        gross = (1.0 - no_ask) if outcome_yes == 0 else -no_ask
        fee_cents = kalshi_fee_cents(1, no_ask, taker=True)
        pnl_c = gross * 100.0 - fee_cents
        return "no", pnl_c
    return "none", 0.0


def rule_b_expected_pnl_per_contract(
    model_prob: float,
    mid: float,
    outcome_yes: int,
    spread_c: float = 0.02,
    fill_rate: float = 0.15,
) -> tuple[str, float]:
    """Rule B: maker-quote rule with 15% effective fill rate.

    BUY YES if model_prob - mid >= 0.04 AND 0.30 <= mid <= 0.85.
    Quote at mid - 0.01 (better than current bid by 1c).
    BUY NO if (1-model_prob) - (1-mid) >= 0.04 AND 0.30 <= (1-mid) <= 0.85.
    Quote at (1-mid) - 0.01.

    Returns expected per-fired-contract pnl, accounting for fill_rate.
    """
    yes_quote = mid - 0.01
    no_quote = (1.0 - mid) - 0.01
    if (
        (model_prob - mid) >= 0.04
        and 0.30 <= mid <= 0.85
    ):
        if yes_quote <= 0.0 or yes_quote >= 1.0:
            return "none", 0.0
        gross = (1.0 - yes_quote) if outcome_yes == 1 else -yes_quote
        fee_cents = kalshi_fee_cents(1, yes_quote, taker=False)
        cond_pnl_c = gross * 100.0 - fee_cents
        return "yes", fill_rate * cond_pnl_c
    if (
        ((1.0 - model_prob) - (1.0 - mid)) >= 0.04
        and 0.30 <= (1.0 - mid) <= 0.85
    ):
        if no_quote <= 0.0 or no_quote >= 1.0:
            return "none", 0.0
        gross = (1.0 - no_quote) if outcome_yes == 0 else -no_quote
        fee_cents = kalshi_fee_cents(1, no_quote, taker=False)
        cond_pnl_c = gross * 100.0 - fee_cents
        return "no", fill_rate * cond_pnl_c
    return "none", 0.0


def cluster_bootstrap_pnl(
    pnls: np.ndarray,
    cluster_ids: np.ndarray,
    n_iter: int = 5000,
    seed: int = SEED,
) -> dict[str, float]:
    """Cluster-bootstrap (whole-day resample) of per-contract P&L.

    Returns dict with point estimate (mean), 2.5th, 97.5th percentiles.
    """
    if len(pnls) == 0:
        return {
            "mean_cents": float("nan"),
            "ci_low": float("nan"),
            "ci_high": float("nan"),
            "n_fires": 0,
            "n_clusters": 0,
        }
    rng = np.random.default_rng(seed)
    unique_clusters = np.unique(cluster_ids)
    n_c = len(unique_clusters)
    # Group pnls by cluster
    cluster_pnls: dict[Any, np.ndarray] = {}
    for c in unique_clusters:
        cluster_pnls[c] = pnls[cluster_ids == c]
    means = []
    for _ in range(n_iter):
        sampled = rng.choice(unique_clusters, size=n_c, replace=True)
        all_pnls = np.concatenate([cluster_pnls[c] for c in sampled])
        means.append(all_pnls.mean())
    means = np.array(means)
    return {
        "mean_cents": float(pnls.mean()),
        "ci_low": float(np.percentile(means, 2.5)),
        "ci_high": float(np.percentile(means, 97.5)),
        "n_fires": int(len(pnls)),
        "n_clusters": int(n_c),
    }
