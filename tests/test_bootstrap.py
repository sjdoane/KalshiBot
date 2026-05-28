"""Tests for the bootstrap CI helper used by the Phase 2 gate diagnostic."""

from __future__ import annotations

import numpy as np
import pytest

from kalshi_bot.analysis.bootstrap import bootstrap_mean_ci


def test_bootstrap_mean_ci_recovers_sample_mean_exactly() -> None:
    values = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    mean, _lower, _upper = bootstrap_mean_ci(values, n_resamples=200, rng_seed=42)
    assert mean == pytest.approx(3.0)


def test_bootstrap_mean_ci_brackets_sample_mean() -> None:
    """The 95% CI brackets the sample mean (the bootstrap is centered on it).
    For a moderately large sample, the CI width is roughly 2 * 1.96 * SE."""
    rng = np.random.default_rng(42)
    values = rng.normal(loc=0.05, scale=0.3, size=10_000)
    mean, lower, upper = bootstrap_mean_ci(values, n_resamples=2000, rng_seed=7)
    assert mean == pytest.approx(values.mean())
    assert lower <= mean <= upper
    # SE should be ~0.3 / sqrt(10000) = 0.003; CI half-width ~ 0.006.
    half_width = (upper - lower) / 2.0
    assert 0.001 < half_width < 0.02


def test_bootstrap_mean_ci_returns_lower_le_upper() -> None:
    values = np.linspace(-1.0, 1.0, 100)
    _mean, lower, upper = bootstrap_mean_ci(values, n_resamples=500, rng_seed=1)
    assert lower <= upper


def test_bootstrap_mean_ci_handles_nan_input() -> None:
    """NaN values are filtered before bootstrap."""
    values = np.array([1.0, np.nan, 2.0, np.nan, 3.0])
    mean, _lower, _upper = bootstrap_mean_ci(values, n_resamples=500, rng_seed=1)
    assert mean == pytest.approx(2.0)


def test_bootstrap_mean_ci_rejects_empty() -> None:
    with pytest.raises(ValueError, match="empty"):
        bootstrap_mean_ci(np.array([]))


def test_bootstrap_mean_ci_rejects_all_nan() -> None:
    with pytest.raises(ValueError, match="empty"):
        bootstrap_mean_ci(np.array([np.nan, np.nan]))


def test_bootstrap_mean_ci_rejects_invalid_ci_level() -> None:
    with pytest.raises(ValueError, match="ci must be"):
        bootstrap_mean_ci(np.array([1.0]), ci=0.0)
    with pytest.raises(ValueError, match="ci must be"):
        bootstrap_mean_ci(np.array([1.0]), ci=1.0)


def test_bootstrap_mean_ci_rejects_too_few_resamples() -> None:
    with pytest.raises(ValueError, match="n_resamples"):
        bootstrap_mean_ci(np.array([1.0, 2.0]), n_resamples=10)


def test_bootstrap_mean_ci_seed_reproducibility() -> None:
    values = np.random.default_rng(0).normal(size=500)
    a = bootstrap_mean_ci(values, n_resamples=500, rng_seed=123)
    b = bootstrap_mean_ci(values, n_resamples=500, rng_seed=123)
    assert a == b


def test_bootstrap_mean_ci_negative_mean_negative_ci() -> None:
    """A clearly negative sample produces a CI strictly below 0 most of the time."""
    rng = np.random.default_rng(11)
    values = rng.normal(loc=-0.05, scale=0.1, size=2000)
    _mean, _lower, upper = bootstrap_mean_ci(values, n_resamples=2000, rng_seed=11)
    # Upper bound should be negative for this signal-strong case
    assert upper < 0.0
