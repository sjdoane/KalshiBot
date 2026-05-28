"""v3 trainer + decision_fn factory.

Compatible with `kalshi_bot_v2.gate.TrainerFn`: a `make_trainer(features)`
returns a `trainer(train_df) -> decision_fn` that fits a fresh
`LogisticRegression` on `train_df[features]` against `outcome`, then
returns a decision_fn whose internal model is anchored to that fit.

The decision rule mirrors v1's eligibility threshold: trade YES when the
model's predicted probability is at least 0.70 (the same lower bound
v1 uses on the raw favorite_price field). This keeps v3's decision rule
domain-comparable to v1's flat-prior baseline.

Key design choices:

1. `class_weight=None`. The training portion has 4 NO outcomes out of
   102; class-weighting would amplify those few rows into a near-
   memorizing classifier. The brief locks `class_weight=None`.
2. `C=1.0`. The brief locks this; no hyperparameter tuning is permitted
   because we are testing a null hypothesis, not searching for a winner.
3. Standardization is applied per-fold inside the trainer (fit on train
   only). For LogReg this affects coefficient magnitudes and the
   convergence path but not the eventual predicted probabilities at the
   solution; we standardize for numeric stability.
4. The decision_fn is `(should_trade, prob)` where `should_trade =
   prob >= 0.70`. The `prob` returned is the model's predicted
   probability, NOT a fixed 0.95 like the v1 baseline.

This module is research-mode only. Nothing imports it into the
live-trading v1 codepath.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

if TYPE_CHECKING:
    from collections.abc import Callable

    import pandas as pd


# v1 eligibility threshold on the underlying price. We reuse the same 0.70
# floor on the model's predicted probability so the rule "trade only when
# the informed estimate of YES is at least 70%" is comparable to v1's
# "trade only when the market price implies at least 70%."
TRADE_PROB_THRESHOLD: float = 0.70

# Locked LogReg hyperparameters per the brief. Do NOT tune these to make
# the gate pass.
LOGREG_C: float = 1.0
LOGREG_MAX_ITER: int = 1000
LOGREG_RANDOM_STATE: int = 42


def make_trainer(features: list[str]) -> Callable[[pd.DataFrame], Callable[[dict], tuple[bool, float]]]:
    """Return a trainer that fits LogReg on the given feature columns.

    The trainer signature matches `kalshi_bot_v2.gate.TrainerFn`. When the
    gate's 5-fold walk-forward CV calls `trainer(fold_train_df)`, a fresh
    `LogisticRegression` is fit on that fold's chronological prefix only.
    The returned decision_fn then evaluates each test-fold row using that
    fold-trained model. This is the leak-free CV pattern the v2 critic
    demanded after Round 5.

    Args:
        features: list of column names to use as features. Must all be
            present in the train_df with no NaN values.

    Returns:
        A `trainer(train_df) -> decision_fn(row_dict) -> (should_trade, prob)`.
    """
    feature_cols = list(features)

    def trainer(train_df: pd.DataFrame) -> Callable[[dict], tuple[bool, float]]:
        # Drop rows with NaN in any required feature column. The v3
        # dataset has NaN team-stat features for non-NFL/MLB leagues;
        # locked behavior is to drop them at training time so the gate
        # is run on the feature-complete subset. The doc records this n.
        usable_mask = ~train_df[feature_cols].isna().any(axis=1)
        usable = train_df.loc[usable_mask]
        if len(usable) < 5:
            # Degenerate: too few rows to fit. Decision: trade nothing.
            def degenerate_fn(row: dict) -> tuple[bool, float]:
                return False, 0.0
            return degenerate_fn

        x_train = usable[feature_cols].to_numpy(dtype=float)
        y_train = usable["outcome"].astype(int).to_numpy()

        # If the training labels are all one class, LogReg.fit raises.
        # The decision_fn falls back to a "trade everything at empirical
        # rate" rule, which is what a max-likelihood model would predict
        # for a constant-y train set.
        if len(np.unique(y_train)) < 2:
            empirical_rate = float(y_train.mean())
            def constant_fn(row: dict) -> tuple[bool, float]:
                return empirical_rate >= TRADE_PROB_THRESHOLD, empirical_rate
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
            # If any feature is missing on the inference side, abstain.
            row_vec: list[float] = []
            for col in feature_cols:
                val = row.get(col)
                if val is None or (isinstance(val, float) and np.isnan(val)):
                    return False, 0.0
                row_vec.append(float(val))
            x_row = np.asarray(row_vec, dtype=float).reshape(1, -1)
            x_row_scaled = scaler.transform(x_row)
            prob_yes = float(model.predict_proba(x_row_scaled)[0, 1])
            return prob_yes >= TRADE_PROB_THRESHOLD, prob_yes

        return decision_fn

    return trainer


def fit_model(
    train_df: pd.DataFrame, features: list[str],
) -> tuple[LogisticRegression | None, StandardScaler | None, list[str]]:
    """Helper that fits LogReg + scaler on `train_df[features]` and
    returns the artifacts. Used by the gate runner to produce the
    holdout decision_fn (a single anchored model trained on the full
    chronological train portion) AND by the calibration analysis to
    extract probabilities on the holdout.

    Returns (model, scaler, used_features). If training is degenerate
    (single-class y or <5 usable rows), returns (None, None, features).
    """
    usable_mask = ~train_df[features].isna().any(axis=1)
    usable = train_df.loc[usable_mask]
    if len(usable) < 5:
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
    """Score one row with a previously-fit model + scaler. Returns NaN
    if any feature is missing on the row.
    """
    row_vec: list[float] = []
    for col in features:
        val = row.get(col)
        if val is None or (isinstance(val, float) and np.isnan(val)):
            return float("nan")
        row_vec.append(float(val))
    x_row = np.asarray(row_vec, dtype=float).reshape(1, -1)
    x_row_scaled = scaler.transform(x_row)
    return float(model.predict_proba(x_row_scaled)[0, 1])


def make_anchored_decision_fn(
    model: LogisticRegression, scaler: StandardScaler, features: list[str],
) -> Callable[[dict], tuple[bool, float]]:
    """Wrap a fit model + scaler into a gate-compatible decision_fn that
    does NOT retrain. Used for the gate's primary holdout pass (the
    holdout split is fully out of sample with respect to the train fit).
    """
    feature_cols = list(features)

    def decision_fn(row: dict) -> tuple[bool, float]:
        prob_yes = predict_proba_row(model, scaler, feature_cols, row)
        if np.isnan(prob_yes):
            return False, 0.0
        return prob_yes >= TRADE_PROB_THRESHOLD, prob_yes

    return decision_fn
