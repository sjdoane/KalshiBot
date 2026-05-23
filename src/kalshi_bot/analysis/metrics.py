"""Calibration and edge metrics used by the Phase 1.5 gate.

All functions take numpy arrays of probabilities in [0, 1] and binary
outcomes in {0, 1}. They are intentionally framework-light so they can run
on the analysis dataframe with `df.apply` or vectorized across splits.

The headline metric is ECE (Expected Calibration Error). Pass criterion in
research-document.md section 8 is a >= 5x ECE improvement out-of-sample.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from collections.abc import Sequence


def _as_float_array(arr: Sequence[float] | np.ndarray) -> np.ndarray:
    out = np.asarray(arr, dtype=float)
    if out.ndim != 1:
        raise ValueError(f"expected 1-d array, got shape {out.shape}")
    return out


def expected_calibration_error(
    probs: Sequence[float] | np.ndarray,
    outcomes: Sequence[int] | np.ndarray,
    *,
    n_bins: int = 10,
) -> float:
    """Standard ECE on uniform bins over [0, 1].

    Formula: sum_b (|B_b| / N) * |mean_pred_b - mean_outcome_b|

    Equal-width binning is the conventional choice; equal-mass binning is
    alternative but harder to compare across runs because bin edges move.
    We use equal-width for reproducibility.
    """
    p = _as_float_array(probs)
    y = _as_float_array(outcomes)
    if p.shape != y.shape:
        raise ValueError(f"shape mismatch probs={p.shape} outcomes={y.shape}")
    n = p.size
    if n == 0:
        return 0.0

    edges = np.linspace(0.0, 1.0, n_bins + 1)
    bin_idx = np.digitize(p, edges[1:-1], right=False)
    ece = 0.0
    for b in range(n_bins):
        mask = bin_idx == b
        count = int(mask.sum())
        if count == 0:
            continue
        bin_pred = p[mask].mean()
        bin_acc = y[mask].mean()
        ece += (count / n) * abs(bin_pred - bin_acc)
    return float(ece)


def reliability_diagram(
    probs: Sequence[float] | np.ndarray,
    outcomes: Sequence[int] | np.ndarray,
    *,
    n_bins: int = 10,
) -> dict[str, np.ndarray]:
    """Per-bin reliability data: count, mean prediction, mean outcome.

    Returns a dict with arrays of length n_bins. Empty bins get NaN for
    mean_pred and mean_outcome to keep alignment.
    """
    p = _as_float_array(probs)
    y = _as_float_array(outcomes)
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    bin_idx = np.digitize(p, edges[1:-1], right=False)

    counts = np.zeros(n_bins, dtype=int)
    mean_pred = np.full(n_bins, np.nan)
    mean_outcome = np.full(n_bins, np.nan)
    for b in range(n_bins):
        mask = bin_idx == b
        if mask.any():
            counts[b] = int(mask.sum())
            mean_pred[b] = p[mask].mean()
            mean_outcome[b] = y[mask].mean()
    return {
        "bin_lower": edges[:-1],
        "bin_upper": edges[1:],
        "count": counts,
        "mean_pred": mean_pred,
        "mean_outcome": mean_outcome,
    }


def brier_score(
    probs: Sequence[float] | np.ndarray,
    outcomes: Sequence[int] | np.ndarray,
) -> float:
    """Mean squared error between forecast probability and binary outcome."""
    p = _as_float_array(probs)
    y = _as_float_array(outcomes)
    return float(np.mean((p - y) ** 2))


def per_trade_gross_edge(
    model_probs: Sequence[float] | np.ndarray,
    market_probs: Sequence[float] | np.ndarray,
) -> np.ndarray:
    """Per-trade gross expected edge (no fees) under the buy-cheaper rule.

    Suppose we observe market YES price P_m and a model probability P_model.
    If P_model > P_m, we buy YES at P_m: gross EV per $1 staked is
        P_model * (1 - P_m) - (1 - P_model) * P_m
        = P_model - P_m
    Symmetrically for P_model < P_m we buy NO and the EV is P_m - P_model.
    The absolute value is the gross edge per dollar of notional.

    Returns an array of |P_model - P_m| values. Callers filter to shoulder
    strikes or above-threshold rows before averaging.
    """
    m = _as_float_array(model_probs)
    k = _as_float_array(market_probs)
    if m.shape != k.shape:
        raise ValueError(f"shape mismatch model={m.shape} market={k.shape}")
    return np.abs(m - k)


def hit_rate(
    model_probs: Sequence[float] | np.ndarray,
    market_probs: Sequence[float] | np.ndarray,
    outcomes: Sequence[int] | np.ndarray,
    *,
    edge_threshold: float = 0.0,
) -> float:
    """Directional hit rate under the buy-cheaper rule.

    For each row where |model - market| > edge_threshold, we trade in the
    direction the model favors. Outcome counts as a hit if the favored side
    won. Returns fraction of hits out of trades taken; returns NaN if no
    trades clear the threshold.
    """
    m = _as_float_array(model_probs)
    k = _as_float_array(market_probs)
    y = _as_float_array(outcomes)
    edge = m - k  # positive: buy YES; negative: buy NO
    trade_mask = np.abs(edge) > edge_threshold
    if not trade_mask.any():
        return float("nan")
    buy_yes = edge[trade_mask] > 0
    wins = np.where(buy_yes, y[trade_mask] == 1, y[trade_mask] == 0)
    return float(wins.mean())


def kalshi_taker_fee_per_contract(price: float, *, contracts: int = 1) -> float:
    """Verified-from-research fee formula: ceil(0.07 * C * P * (1-P)) cents."""
    cents = np.ceil(7.0 * contracts * price * (1.0 - price))
    return float(cents / 100.0)


def kalshi_maker_fee_per_contract(price: float, *, contracts: int = 1) -> float:
    """Maker fee is 25% of taker."""
    cents = np.ceil(1.75 * contracts * price * (1.0 - price))
    return float(cents / 100.0)
