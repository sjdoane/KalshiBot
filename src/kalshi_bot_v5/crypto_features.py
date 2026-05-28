"""V5-C2 crypto feature module.

Lightweight helpers for the orthogonality-probe -> conditional-gate pipeline.

The feature engineering is done in scripts/v5/build_v5c_orthogonality_dataset.py
to keep API throttling and caching close to the dataset construction. This
module provides the make_trainer factory consumed by the v2 locked gate:

    trainer = make_trainer(features)

    from kalshi_bot_v2.gate import evaluate
    result = evaluate(df, trainer(df), trainer=trainer, ...)

`features` is the list of column names that survived orthogonality. The
trainer returns a TradeDecisionFn that fits a fresh LogReg on each fold's
prefix and trades when predicted_prob > favorite_price + 0.02.

Trade rule: should_trade = predicted_prob > favorite_price + 0.02 (per V5-C2 brief).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

TRADE_EDGE_THRESHOLD = 0.02  # predicted_prob - favorite_price required to trade


def make_trainer(
    feature_cols: list[str],
    *,
    edge_threshold: float = TRADE_EDGE_THRESHOLD,
) -> Callable:
    """Return a `trainer` function compatible with v2 gate `trainer=` arg.

    The trainer fits a LogReg on (favorite_price + features) for each fold's
    chronological prefix and returns a TradeDecisionFn that compares the
    model's predicted_prob to favorite_price + threshold.
    """
    cols = ["favorite_price", *feature_cols]

    def trainer(fold_train: pd.DataFrame) -> Callable[[dict], tuple[bool, float]]:
        # Drop rows missing any feature
        sub = fold_train.dropna(subset=cols + ["outcome"])
        if len(sub) < 10 or len(np.unique(sub["outcome"])) < 2:
            # Fallback: trade nothing
            def fallback_fn(row: dict[str, Any]) -> tuple[bool, float]:
                return False, float(row.get("favorite_price", 0.0))

            return fallback_fn

        X = sub[cols].to_numpy()
        y = sub["outcome"].to_numpy()
        model = LogisticRegression(C=10.0, max_iter=500).fit(X, y)

        def decision_fn(row: dict[str, Any]) -> tuple[bool, float]:
            try:
                vec = np.array([[row[c] for c in cols]], dtype=float)
                if not np.isfinite(vec).all():
                    return False, float(row.get("favorite_price", 0.0))
                prob = float(model.predict_proba(vec)[0, 1])
            except (KeyError, TypeError, ValueError):
                return False, float(row.get("favorite_price", 0.0))
            price = float(row.get("favorite_price", 0.0))
            should = prob > price + edge_threshold
            return should, prob

        return decision_fn

    return trainer
