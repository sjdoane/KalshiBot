"""Tests for the isotonic calibrator wrapper."""

from __future__ import annotations

import numpy as np
import pytest

from kalshi_bot.analysis.calibration import IsotonicCalibrator
from kalshi_bot.analysis.metrics import expected_calibration_error


def test_calibrator_refuses_to_predict_before_fit() -> None:
    cal = IsotonicCalibrator()
    with pytest.raises(RuntimeError, match="call fit"):
        cal.predict([0.5])


def test_calibrator_refuses_tiny_training_set() -> None:
    with pytest.raises(ValueError, match="at least 50"):
        IsotonicCalibrator().fit([0.5] * 10, [1] * 10)


def test_calibrator_outputs_clip_to_unit_interval() -> None:
    rng = np.random.default_rng(0)
    # 1000 samples where market probability equals true probability (well calibrated)
    p = rng.uniform(0.0, 1.0, size=1000)
    y = (rng.uniform(0.0, 1.0, size=1000) < p).astype(int)
    cal = IsotonicCalibrator().fit(p, y)
    preds = cal.predict(np.linspace(-0.5, 1.5, 200))
    assert (preds >= 0.0).all()
    assert (preds <= 1.0).all()


def test_calibrator_improves_in_sample_ece_on_systematically_biased_input() -> None:
    """If market probabilities are biased (always 0.1 too high), isotonic
    should pull them back. This is the in-sample fit case Zerve reported."""
    rng = np.random.default_rng(42)
    true_p = rng.uniform(0.05, 0.95, size=2000)
    market_p = np.clip(true_p + 0.1, 0.0, 1.0)
    outcomes = (rng.uniform(0.0, 1.0, size=2000) < true_p).astype(int)

    raw_ece = expected_calibration_error(market_p, outcomes, n_bins=10)
    cal = IsotonicCalibrator().fit(market_p, outcomes)
    cal_ece = expected_calibration_error(cal.predict(market_p), outcomes, n_bins=10)

    # The biased input has substantial ECE; isotonic should cut it materially
    assert raw_ece > 0.05
    assert cal_ece < raw_ece * 0.5


def test_calibrator_does_not_improve_out_of_sample_on_random_market() -> None:
    """Critical guard: if there is no real edge, the calibrator should not
    invent one out-of-sample. We construct a perfectly random market
    (outcomes are coin flips, prices are random) and verify ECE does not
    materially improve on a held-out partition.

    This is the exact failure mode the Phase 1.5 gate is designed to catch:
    in-sample improvement that does NOT survive an honest train/test split.
    """
    rng = np.random.default_rng(7)
    n = 4000
    market_p = rng.uniform(0.05, 0.95, size=n)
    outcomes = rng.binomial(1, 0.5, size=n)  # no relationship to market_p

    train_p = market_p[: n // 2]
    train_y = outcomes[: n // 2]
    test_p = market_p[n // 2 :]
    test_y = outcomes[n // 2 :]

    cal = IsotonicCalibrator().fit(train_p, train_y)

    raw_test_ece = expected_calibration_error(test_p, test_y, n_bins=10)
    cal_test_ece = expected_calibration_error(cal.predict(test_p), test_y, n_bins=10)

    # On pure noise, isotonic should not produce a >= 5x improvement
    # (the Phase 1.5 pass bar). It typically yields a small change in either
    # direction; we assert it's NOT a 5x improvement.
    assert cal_test_ece > raw_test_ece / 5.0, (
        f"isotonic falsely improved 5x on noise: raw={raw_test_ece:.4f} "
        f"calibrated={cal_test_ece:.4f}. Train/test split may be leaky."
    )
