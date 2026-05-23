"""Isotonic calibration wrapper for the Phase 1.5 gate.

Isotonic regression learns a monotonic step function that maps raw market
prices to (estimated) true outcome probabilities. We fit on train markets
(market_price -> outcome) and score on disjoint test markets.

We pin sklearn's IsotonicRegression with `out_of_bounds="clip"` so test
values outside the training range get mapped to the nearest endpoint;
combined with `y_min=0.0` and `y_max=1.0` this keeps predictions in [0, 1].
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from sklearn.isotonic import IsotonicRegression

if TYPE_CHECKING:
    from collections.abc import Sequence


class IsotonicCalibrator:
    """Thin wrapper around sklearn.isotonic.IsotonicRegression.

    Use:
        cal = IsotonicCalibrator().fit(train_market_probs, train_outcomes)
        recalibrated = cal.predict(test_market_probs)
    """

    def __init__(self) -> None:
        self._model = IsotonicRegression(
            y_min=0.0,
            y_max=1.0,
            increasing=True,
            out_of_bounds="clip",
        )
        self._fitted = False

    def fit(
        self,
        market_probs: Sequence[float] | np.ndarray,
        outcomes: Sequence[int] | np.ndarray,
    ) -> IsotonicCalibrator:
        x = np.asarray(market_probs, dtype=float)
        y = np.asarray(outcomes, dtype=float)
        if x.shape != y.shape:
            raise ValueError(f"shape mismatch x={x.shape} y={y.shape}")
        if x.size < 50:
            # Isotonic on tiny samples produces a degenerate step function.
            # 50 is a low bar; production splits should have hundreds.
            raise ValueError(f"need at least 50 training rows, got {x.size}")
        self._model.fit(x, y)
        self._fitted = True
        return self

    def predict(self, market_probs: Sequence[float] | np.ndarray) -> np.ndarray:
        if not self._fitted:
            raise RuntimeError("IsotonicCalibrator: call fit() before predict()")
        x = np.asarray(market_probs, dtype=float)
        out = self._model.predict(x)
        return np.clip(out, 0.0, 1.0)
