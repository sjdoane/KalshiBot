"""Bootstrap confidence intervals for the Phase 2 gate diagnostics.

The Phase 2 methodology adds a pooled-mean diagnostic (Section 6.4): take
all per-trade net edges across all walk-forward test partitions, compute a
bootstrap CI on the mean. This is a higher-power complement to the
per-split count criterion (C3). Used as DIAGNOSTIC, not as a gate, so the
methodology stays kill-on-fail at the locked criteria.

Two helpers:
- `bootstrap_mean_ci(values, n_resamples, ci)` -> (mean, lower, upper)
- `bootstrap_per_split_mean_ci(per_split_means, n_per_split)` -> weighted
  pooled CI when per-split sample sizes differ
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from collections.abc import Sequence


def bootstrap_mean_ci(
    values: Sequence[float] | np.ndarray,
    *,
    n_resamples: int = 5000,
    ci: float = 0.95,
    rng_seed: int | None = None,
) -> tuple[float, float, float]:
    """Compute (mean, lower_bound, upper_bound) via nonparametric bootstrap.

    Inputs:
        values: 1-D array of observations (e.g., per-trade net edges).
        n_resamples: number of bootstrap resamples. 5000 is the methodology
            default per Section 6.4.
        ci: confidence level (default 0.95).
        rng_seed: pass an int for reproducibility; None uses a fresh RNG.

    Returns:
        (sample_mean, lower_quantile, upper_quantile)

    Raises:
        ValueError if values is empty or contains all NaN.

    Methodology note: this is an unstratified, per-observation bootstrap.
    It does NOT account for walk-forward correlation between partitions.
    The methodology critic flagged this as a known limitation; the pooled-
    mean diagnostic is informational only.
    """
    arr = np.asarray(values, dtype=float)
    arr = arr[~np.isnan(arr)]
    n = arr.size
    if n == 0:
        raise ValueError("bootstrap_mean_ci: empty input")
    if not (0.0 < ci < 1.0):
        raise ValueError(f"bootstrap_mean_ci: ci must be in (0, 1), got {ci}")
    if n_resamples < 100:
        raise ValueError(f"bootstrap_mean_ci: need n_resamples >= 100, got {n_resamples}")

    rng = np.random.default_rng(rng_seed)
    # Vectorized resampling: sample (n_resamples, n) indices then take means
    # along the columns. Memory ~ n_resamples * n * 8 bytes; for 5000 * 17000
    # ~ 680MB which is too large. Iterate in batches for safety.
    batch_size = max(1, min(n_resamples, max(1, 10_000_000 // max(n, 1))))
    means_list: list[np.ndarray] = []
    remaining = n_resamples
    while remaining > 0:
        b = min(batch_size, remaining)
        idx = rng.integers(0, n, size=(b, n))
        means_list.append(arr[idx].mean(axis=1))
        remaining -= b
    means = np.concatenate(means_list)

    alpha = (1.0 - ci) / 2.0
    lower = float(np.quantile(means, alpha))
    upper = float(np.quantile(means, 1.0 - alpha))
    sample_mean = float(arr.mean())
    return sample_mean, lower, upper
