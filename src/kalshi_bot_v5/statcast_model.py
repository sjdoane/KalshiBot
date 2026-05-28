"""V5-B2 LogisticRegression trainer for the Statcast prop model.

API matches `kalshi_bot_v2.gate.TrainerFn` so the locked C1-C6 gate
can swap models in/out without modification.

Decision rule (locked, no tuning):
    should_trade = predicted_prob > favorite_price + LLM_ADVANTAGE_C
where LLM_ADVANTAGE_C = 0.02 (require 2c advantage before trading;
avoids triggering on tiny edges per the brief).

Locked hyperparameters:
- LOGREG_C = 1.0
- class_weight = None
- max_iter = 1000
- random_state = 42
- StandardScaler fit per-fold on train only

NaN-handling: if any feature is NaN for a row, abstain (no trade).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

if TYPE_CHECKING:
    from collections.abc import Callable

    import pandas as pd


# Trade-margin advantage required over the market price.
EDGE_THRESHOLD: float = 0.02

# Locked hyperparameters from the brief.
LOGREG_C: float = 1.0
LOGREG_MAX_ITER: int = 1000
LOGREG_RANDOM_STATE: int = 42


def make_trainer(features: list[str]) -> Callable[[pd.DataFrame], Callable[[dict], tuple[bool, float]]]:
    """Return a `trainer(train_df) -> decision_fn` factory.

    The gate's 5-fold walk-forward CV calls `trainer(fold_train_df)`
    for each fold, ensuring fold-test is OOS w.r.t. the fold-train
    fitted model. This is the v2-critic-Round-5 fix carried through.

    The decision rule: predicted_prob_of_yes > favorite_price + 0.02.

    Args:
        features: column names to use as features. The trainer drops
            rows with NaN in any of them at training time.
    """
    feature_cols = list(features)

    def trainer(train_df: pd.DataFrame) -> Callable[[dict], tuple[bool, float]]:
        usable_mask = ~train_df[feature_cols].isna().any(axis=1)
        usable = train_df.loc[usable_mask]
        if len(usable) < 10:
            def degenerate_fn(_row: dict) -> tuple[bool, float]:
                return False, 0.0
            return degenerate_fn

        x_train = usable[feature_cols].to_numpy(dtype=float)
        y_train = usable["outcome"].astype(int).to_numpy()

        if len(np.unique(y_train)) < 2:
            empirical_rate = float(y_train.mean())
            def constant_fn(row: dict) -> tuple[bool, float]:
                try:
                    price = float(row.get("favorite_price", 0.5))
                except (TypeError, ValueError):
                    price = 0.5
                return (empirical_rate > price + EDGE_THRESHOLD, empirical_rate)
            return constant_fn

        scaler = StandardScaler()
        x_train_scaled = scaler.fit_transform(x_train)
        model = LogisticRegression(
            C=LOGREG_C,
            class_weight=None,
            max_iter=LOGREG_MAX_ITER,
            random_state=LOGREG_RANDOM_STATE,
        )
        model.fit(x_train_scaled, y_train)

        def decision_fn(row: dict) -> tuple[bool, float]:
            row_vec: list[float] = []
            for col in feature_cols:
                val = row.get(col)
                if val is None or (isinstance(val, float) and np.isnan(val)):
                    return False, 0.0
                try:
                    row_vec.append(float(val))
                except (TypeError, ValueError):
                    return False, 0.0
            try:
                price = float(row["favorite_price"])
            except (TypeError, ValueError, KeyError):
                return False, 0.0
            x_row = np.asarray(row_vec, dtype=float).reshape(1, -1)
            x_row_scaled = scaler.transform(x_row)
            prob_yes = float(model.predict_proba(x_row_scaled)[0, 1])
            should_trade = prob_yes > (price + EDGE_THRESHOLD)
            return should_trade, prob_yes

        return decision_fn

    return trainer


def fit_model(
    train_df: pd.DataFrame, features: list[str],
) -> tuple[LogisticRegression | None, StandardScaler | None, list[str]]:
    """Helper to fit LogReg + StandardScaler outside the trainer factory.

    Used by the holdout pass in the gate runner (single anchored model
    on the chronological 70% train portion) and by the calibration
    analysis.

    Returns (model, scaler, used_features). On degenerate input
    (<10 usable rows or single-class y) returns (None, None, features).
    """
    usable_mask = ~train_df[features].isna().any(axis=1)
    usable = train_df.loc[usable_mask]
    if len(usable) < 10:
        return None, None, features
    x_train = usable[features].to_numpy(dtype=float)
    y_train = usable["outcome"].astype(int).to_numpy()
    if len(np.unique(y_train)) < 2:
        return None, None, features
    scaler = StandardScaler()
    x_train_scaled = scaler.fit_transform(x_train)
    model = LogisticRegression(
        C=LOGREG_C,
        class_weight=None,
        max_iter=LOGREG_MAX_ITER,
        random_state=LOGREG_RANDOM_STATE,
    )
    model.fit(x_train_scaled, y_train)
    return model, scaler, features


def predict_proba_row(
    model: LogisticRegression, scaler: StandardScaler,
    features: list[str], row: dict,
) -> float:
    """Score a single row. Returns NaN if any feature is missing."""
    row_vec: list[float] = []
    for col in features:
        val = row.get(col)
        if val is None or (isinstance(val, float) and np.isnan(val)):
            return float("nan")
        try:
            row_vec.append(float(val))
        except (TypeError, ValueError):
            return float("nan")
    x_row = np.asarray(row_vec, dtype=float).reshape(1, -1)
    x_row_scaled = scaler.transform(x_row)
    return float(model.predict_proba(x_row_scaled)[0, 1])


def make_anchored_decision_fn(
    model: LogisticRegression, scaler: StandardScaler, features: list[str],
) -> Callable[[dict], tuple[bool, float]]:
    """Wrap a pre-fit model + scaler into a decision_fn that does NOT
    retrain. Used for the gate's primary holdout pass.
    """
    feature_cols = list(features)

    def decision_fn(row: dict) -> tuple[bool, float]:
        prob_yes = predict_proba_row(model, scaler, feature_cols, row)
        if np.isnan(prob_yes):
            return False, 0.0
        try:
            price = float(row["favorite_price"])
        except (TypeError, ValueError, KeyError):
            return False, 0.0
        return prob_yes > (price + EDGE_THRESHOLD), prob_yes

    return decision_fn
