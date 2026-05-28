"""Tests for logistic slope fit used by the Phase 2 gate."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from kalshi_bot.analysis.slope import (
    fit_logistic_slope,
    logit,
    per_market_slopes,
    slope_distribution_summary,
)


def _generate_compressed_synthetic(
    n: int, true_slope: float, rng_seed: int
) -> tuple[np.ndarray, np.ndarray]:
    """Generate (market_prob, outcome) where true generative model has the
    given slope and zero intercept: logit(P(y=1)) = true_slope * logit(market_prob).
    Market probs drawn uniformly from [0.1, 0.9] to avoid boundary issues.
    """
    rng = np.random.default_rng(rng_seed)
    market_probs = rng.uniform(0.1, 0.9, size=n)
    true_logit = true_slope * logit(market_probs)
    true_prob = 1.0 / (1.0 + np.exp(-true_logit))
    outcomes = (rng.uniform(0.0, 1.0, size=n) < true_prob).astype(int)
    return market_probs, outcomes


def test_logit_basic_values() -> None:
    """logit(0.5) == 0; logit(0.75) > 0; logit(0.25) < 0; symmetric."""
    assert logit(0.5) == pytest.approx(0.0, abs=1e-10)
    assert logit(0.75) == pytest.approx(np.log(3), abs=1e-10)
    assert logit(0.25) == pytest.approx(-np.log(3), abs=1e-10)


def test_logit_clips_zero_and_one() -> None:
    """Exact 0 and 1 should not produce inf; they get clipped to bounds."""
    out = logit(np.array([0.0, 1.0]))
    assert np.isfinite(out).all()


def test_logit_vectorized() -> None:
    """logit accepts and returns arrays."""
    arr = np.array([0.1, 0.3, 0.5, 0.7, 0.9])
    out = logit(arr)
    assert out.shape == arr.shape
    assert out[2] == pytest.approx(0.0, abs=1e-10)


def test_fit_logistic_slope_recovers_true_slope_for_compressed_regime() -> None:
    """With synthetic data drawn from a slope=1.5 generative model and
    n=2000 samples, the fit should recover slope close to 1.5 (within ~5%).
    This is the regime the Phase 2 strategy targets."""
    market, y = _generate_compressed_synthetic(n=2000, true_slope=1.5, rng_seed=42)
    _intercept, slope = fit_logistic_slope(market, y)
    assert slope == pytest.approx(1.5, rel=0.1)


def test_fit_logistic_slope_recovers_calibrated_regime() -> None:
    """With slope=1.0 (well-calibrated) data, the fit should also recover 1.0."""
    market, y = _generate_compressed_synthetic(n=2000, true_slope=1.0, rng_seed=42)
    _intercept, slope = fit_logistic_slope(market, y)
    assert slope == pytest.approx(1.0, rel=0.1)


def test_fit_logistic_slope_recovers_overconfident_regime() -> None:
    """With slope=0.7 (overconfident) data, the fit should recover ~0.7."""
    market, y = _generate_compressed_synthetic(n=2000, true_slope=0.7, rng_seed=42)
    _intercept, slope = fit_logistic_slope(market, y)
    assert slope == pytest.approx(0.7, rel=0.15)


def test_fit_logistic_slope_rejects_shape_mismatch() -> None:
    with pytest.raises(ValueError, match="shape mismatch"):
        fit_logistic_slope(np.array([0.3, 0.5]), np.array([0, 1, 0]))


def test_fit_logistic_slope_requires_min_sample_size() -> None:
    with pytest.raises(ValueError, match="at least 30"):
        fit_logistic_slope(np.array([0.3, 0.5, 0.7]), np.array([0, 1, 0]))


def test_fit_logistic_slope_requires_class_balance() -> None:
    """All-zeros or all-ones outcomes cannot be fit."""
    market = np.linspace(0.1, 0.9, 50)
    all_ones = np.ones(50, dtype=int)
    with pytest.raises(ValueError, match="y=0"):
        fit_logistic_slope(market, all_ones)
    all_zeros = np.zeros(50, dtype=int)
    with pytest.raises(ValueError, match="y=1"):
        fit_logistic_slope(market, all_zeros)


def test_per_market_slopes_skips_small_groups() -> None:
    """Groups with fewer than min_trades_per_group rows are skipped."""
    rng = np.random.default_rng(7)
    big_series_market = rng.uniform(0.1, 0.9, size=100)
    big_series_y = (rng.uniform(size=100) < big_series_market).astype(int)
    small_series_market = rng.uniform(0.1, 0.9, size=10)
    small_series_y = (rng.uniform(size=10) < small_series_market).astype(int)

    df = pd.DataFrame(
        {
            "price": np.concatenate([big_series_market, small_series_market]),
            "outcome": np.concatenate([big_series_y, small_series_y]),
            "series": ["BIG"] * 100 + ["SMALL"] * 10,
        }
    )
    slopes = per_market_slopes(
        df, price_col="price", outcome_col="outcome", group_col="series",
        min_trades_per_group=50,
    )
    assert "BIG" in slopes
    assert "SMALL" not in slopes


def test_per_market_slopes_requires_columns() -> None:
    df = pd.DataFrame({"x": [1.0], "y": [1]})
    with pytest.raises(ValueError, match="price"):
        per_market_slopes(df, price_col="price", outcome_col="y", group_col="x")
    with pytest.raises(ValueError, match="'series'"):
        per_market_slopes(df, price_col="x", outcome_col="y", group_col="series")


def test_slope_distribution_summary_basic() -> None:
    slopes = {"a": 1.0, "b": 1.5, "c": 2.0, "d": 0.8}
    summary = slope_distribution_summary(slopes)
    assert summary["n"] == 4
    assert summary["median"] == pytest.approx(1.25)
    assert summary["q25"] == pytest.approx(0.95)
    assert summary["q75"] == pytest.approx(1.625)


def test_slope_distribution_summary_empty() -> None:
    summary = slope_distribution_summary({})
    assert summary["n"] == 0
    assert np.isnan(summary["median"])
    assert np.isnan(summary["q25"])


def test_slope_distribution_summary_accepts_sequence() -> None:
    """Can pass a list, not just dict."""
    summary = slope_distribution_summary([1.0, 2.0, 3.0])
    assert summary["n"] == 3
    assert summary["median"] == pytest.approx(2.0)
