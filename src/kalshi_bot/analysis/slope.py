"""Logistic-regression slope fit for the Phase 2 gate.

Le 2026's calibration model decomposes market prices vs truth via:

    logit(truth_prob) = a + b * logit(market_prob)

where slope `b > 1` means market prices are compressed toward 0.5
(underconfident) and `b < 1` means market prices are too extreme
(overconfident). The Phase 2 gate (C1) requires the median per-partition
slope on small-trade VWAP >= 1.2 AND the per-partition lower-quartile
slope >= 1.0.

This module provides:
- `fit_logistic_slope(market_probs, outcomes)` -> (intercept, slope)
- `per_partition_slope_distribution(splits, df_resolver)` -> per-split slopes

Uses scikit-learn's LogisticRegression with effectively no regularization
(C=1e10) so the fit matches the MLE. Clips prices to [1e-6, 1 - 1e-6] to
keep logits finite.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from sklearn.linear_model import LogisticRegression

if TYPE_CHECKING:
    from collections.abc import Sequence

# Clip avoids inf in logit when a price arrives at exactly 0 or 1. The 1e-6
# bound rounds to 1e-6 prob, well below any tick on Kalshi (1c = 0.01).
_CLIP_EPS = 1e-6


def logit(p: np.ndarray | float) -> np.ndarray | float:
    """logit(p) = log(p / (1-p)) with clipping to avoid infinities.

    Accepts scalars or arrays. Returns same shape. Inputs are clipped to
    [_CLIP_EPS, 1 - _CLIP_EPS] before transformation.
    """
    arr = np.clip(np.asarray(p, dtype=float), _CLIP_EPS, 1.0 - _CLIP_EPS)
    return np.log(arr / (1.0 - arr))


def fit_logistic_slope(
    market_probs: Sequence[float] | np.ndarray,
    outcomes: Sequence[int] | np.ndarray,
) -> tuple[float, float]:
    """Fit `logit(P(y=1)) = a + b * logit(x)` and return (a, b).

    Inputs:
        market_probs: 1-D array of YES prices in [0, 1]
        outcomes: 1-D array of binary outcomes {0, 1}

    Returns:
        (intercept, slope) = (a, b)

    Raises:
        ValueError on shape mismatch, insufficient sample size, or
        all-one-class outcomes (logistic fit is degenerate there).

    Sample-size floor: requires >= 30 rows AND at least 5 each of y=0 and
    y=1. Below that, the fit is too noisy to interpret as a regime
    estimate; the caller should report missing slope rather than fit.
    """
    x_raw = np.asarray(market_probs, dtype=float)
    y = np.asarray(outcomes, dtype=int)
    if x_raw.shape != y.shape:
        raise ValueError(f"shape mismatch market_probs={x_raw.shape} outcomes={y.shape}")
    if x_raw.size < 30:
        raise ValueError(f"need at least 30 rows for slope fit, got {x_raw.size}")
    n_ones = int((y == 1).sum())
    n_zeros = int((y == 0).sum())
    if n_ones < 5 or n_zeros < 5:
        raise ValueError(
            f"need >= 5 each of y=0 and y=1 for slope fit; got "
            f"y=0:{n_zeros} y=1:{n_ones}"
        )

    x_logit = logit(x_raw).reshape(-1, 1)
    # C=1e10 effectively disables regularization so we recover the MLE.
    model = LogisticRegression(C=1e10, solver="lbfgs", max_iter=500)
    model.fit(x_logit, y)
    intercept = float(model.intercept_[0])
    slope = float(model.coef_[0, 0])
    return intercept, slope


def per_market_slopes(
    df,
    *,
    price_col: str,
    outcome_col: str,
    group_col: str,
    min_trades_per_group: int = 50,
) -> dict[str, float]:
    """Fit a slope per group (e.g., per series_ticker) and return a dict.

    Groups with fewer than `min_trades_per_group` rows are skipped. Groups
    where the slope fit fails (insufficient class balance, etc.) are also
    skipped. The returned dict maps group_id -> slope.

    This is used to produce the per-market slope distribution diagnostic
    (Section 6.5 of phase-2-methodology.md). Note that "per-market" here
    means "per-series" if the calibration is fit at the series level; the
    caller controls grouping via `group_col`.
    """
    if price_col not in df.columns or outcome_col not in df.columns:
        raise ValueError(f"DataFrame must contain '{price_col}' and '{outcome_col}'")
    if group_col not in df.columns:
        raise ValueError(f"DataFrame must contain '{group_col}'")

    results: dict[str, float] = {}
    for gid, gdf in df.groupby(group_col):
        if len(gdf) < min_trades_per_group:
            continue
        try:
            _, slope = fit_logistic_slope(gdf[price_col].to_numpy(), gdf[outcome_col].to_numpy())
        except ValueError:
            continue
        results[str(gid)] = slope
    return results


def slope_distribution_summary(slopes: dict[str, float] | Sequence[float]) -> dict[str, float]:
    """Summarize a collection of slopes: count, median, lower-quartile,
    upper-quartile.

    Returns dict with keys: n, median, q25, q75. Missing data returns NaN
    for the quartile summaries (count is always 0).
    """
    if isinstance(slopes, dict):
        values = np.array(list(slopes.values()), dtype=float)
    else:
        values = np.asarray(slopes, dtype=float)
    n = int(values.size)
    if n == 0:
        return {"n": 0, "median": float("nan"), "q25": float("nan"), "q75": float("nan")}
    return {
        "n": n,
        "median": float(np.median(values)),
        "q25": float(np.quantile(values, 0.25)),
        "q75": float(np.quantile(values, 0.75)),
    }
