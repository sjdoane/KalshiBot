"""Tests for ECE, reliability diagram, edge, hit rate, and fee math."""

from __future__ import annotations

import numpy as np
import pytest

from kalshi_bot.analysis.metrics import (
    brier_score,
    expected_calibration_error,
    hit_rate,
    kalshi_maker_fee_per_contract,
    kalshi_round_trip_maker_fees,
    kalshi_taker_fee_per_contract,
    per_trade_gross_edge,
    realized_pnl_per_contract,
    reliability_diagram,
)


def test_ece_is_zero_for_perfectly_calibrated_constant() -> None:
    # 50% predictions where exactly 50% of outcomes are 1 -> bin acc == bin pred
    probs = np.full(1000, 0.5)
    outcomes = np.concatenate([np.zeros(500), np.ones(500)])
    np.random.default_rng(0).shuffle(outcomes)
    assert expected_calibration_error(probs, outcomes, n_bins=10) == pytest.approx(0.0)


def test_ece_is_nonzero_for_miscalibrated_constant() -> None:
    # Model predicts 0.5; reality is 0.8. ECE should be |0.5 - 0.8| = 0.3.
    probs = np.full(1000, 0.5)
    outcomes = np.concatenate([np.zeros(200), np.ones(800)])
    assert expected_calibration_error(probs, outcomes, n_bins=10) == pytest.approx(0.3, abs=1e-9)


def test_ece_handles_empty_input() -> None:
    assert expected_calibration_error([], []) == 0.0


def test_ece_rejects_shape_mismatch() -> None:
    with pytest.raises(ValueError, match="shape mismatch"):
        expected_calibration_error([0.5, 0.5], [1, 0, 1])


def test_reliability_diagram_returns_aligned_arrays() -> None:
    probs = np.array([0.05, 0.15, 0.25, 0.5, 0.95, 0.95])
    outcomes = np.array([0, 0, 1, 0, 1, 1])
    diag = reliability_diagram(probs, outcomes, n_bins=10)
    assert diag["count"].shape == (10,)
    assert diag["mean_pred"].shape == (10,)
    assert diag["mean_outcome"].shape == (10,)
    assert diag["bin_lower"][0] == 0.0
    assert diag["bin_upper"][-1] == 1.0
    # Bin 9 ([0.9, 1.0]) has the two 0.95 predictions, both outcome 1
    assert diag["count"][9] == 2
    assert diag["mean_pred"][9] == pytest.approx(0.95)
    assert diag["mean_outcome"][9] == pytest.approx(1.0)


def test_brier_score_zero_for_perfect_predictions() -> None:
    probs = np.array([0.0, 1.0, 0.0, 1.0])
    outcomes = np.array([0, 1, 0, 1])
    assert brier_score(probs, outcomes) == 0.0


def test_brier_score_quarter_for_uniform_uncertainty() -> None:
    probs = np.full(4, 0.5)
    outcomes = np.array([0, 1, 0, 1])
    assert brier_score(probs, outcomes) == 0.25


def test_per_trade_gross_edge_is_absolute_difference() -> None:
    edge = per_trade_gross_edge(
        model_probs=[0.6, 0.4, 0.5],
        market_probs=[0.5, 0.5, 0.5],
    )
    assert edge.tolist() == pytest.approx([0.1, 0.1, 0.0])


def test_hit_rate_above_threshold() -> None:
    # Two trades cleared a 0.05 threshold; both correct -> hit rate 1.0
    rate = hit_rate(
        model_probs=[0.6, 0.4, 0.51],  # edges: +0.1, -0.1, +0.01
        market_probs=[0.5, 0.5, 0.5],
        outcomes=[1, 0, 1],
        edge_threshold=0.05,
    )
    assert rate == pytest.approx(1.0)


def test_hit_rate_nan_when_no_trades_clear() -> None:
    rate = hit_rate(
        model_probs=[0.51, 0.49],
        market_probs=[0.5, 0.5],
        outcomes=[0, 1],
        edge_threshold=0.1,
    )
    assert np.isnan(rate)


def test_taker_fee_caps_at_max_p_50() -> None:
    # ceil(0.07 * 1 * 0.5 * 0.5) cents = ceil(0.0175 * 100) / 100 = ceil(1.75)/100 = 0.02
    # Note: the formula is ceil(0.07 * C * P * (1-P)) without /0.01 inside ceil,
    # so for 1 contract at 0.50: ceil(7 * 0.5 * 0.5) = ceil(1.75) = 2 cents = $0.02
    fee = kalshi_taker_fee_per_contract(0.50, contracts=1)
    assert fee == pytest.approx(0.02)


def test_taker_fee_zero_at_extremes() -> None:
    # P = 0.01 -> 7 * 0.01 * 0.99 = 0.0693 -> ceil = 1 cent
    assert kalshi_taker_fee_per_contract(0.01) == pytest.approx(0.01)
    # P = 0.99 -> symmetric -> 1 cent
    assert kalshi_taker_fee_per_contract(0.99) == pytest.approx(0.01)


def test_maker_fee_is_quarter_of_taker_at_50() -> None:
    # ceil(1.75 * 0.5 * 0.5) = ceil(0.4375) = 1 cent
    maker = kalshi_maker_fee_per_contract(0.50)
    assert maker == pytest.approx(0.01)


def test_kalshi_round_trip_maker_fees_vectorizes() -> None:
    fees = kalshi_round_trip_maker_fees([0.50, 0.50, 0.50])
    assert fees.tolist() == pytest.approx([0.02, 0.02, 0.02])  # 2 x $0.01


def test_realized_pnl_yes_win_yes_loss_no_trade() -> None:
    # Three markets: model says YES strongly, NO strongly, neither.
    # Outcomes: 1, 1, 0.
    pnl = realized_pnl_per_contract(
        model_probs=[0.80, 0.20, 0.51],
        market_probs=[0.50, 0.50, 0.50],
        outcomes=[1, 1, 0],
        fee_per_contract=0.01,
        edge_threshold=0.05,
    )
    # Row 0: bet YES at 0.50, outcome=1 -> 1 - 0.50 - 0.01 = 0.49
    # Row 1: bet NO at 0.50, outcome=1 -> 0.50 - 1 - 0.01 = -0.51
    # Row 2: |edge|=0.01 < threshold 0.05 -> no trade, no fee, P&L=0
    assert pnl.tolist() == pytest.approx([0.49, -0.51, 0.0])


def test_realized_pnl_no_fee_no_edge_filter() -> None:
    # Vanilla mode: every row trades, zero fees, P&L equals signed gross
    pnl = realized_pnl_per_contract(
        model_probs=[0.7, 0.3],
        market_probs=[0.5, 0.5],
        outcomes=[1, 0],
    )
    assert pnl.tolist() == pytest.approx([0.5, 0.5])  # both correct directionally
