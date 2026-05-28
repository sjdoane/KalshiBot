"""Sanity tests for the v2 gate. The modeling agent will add more
specific tests once the actual model is in place.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from kalshi_bot_v2.gate import (
    PASS_C6_V2_BEATS_V1_PP,
    evaluate,
    realized_pnl_per_contract,
    v1_decision_fn,
)


def _synthetic_df(n: int = 100, yes_rate: float = 0.95, seed: int = 1) -> pd.DataFrame:
    """Build a synthetic favorite-maker dataset for gate testing."""
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        "close_time": pd.date_range("2025-01-01", periods=n, freq="D", tz="UTC"),
        "favorite_price": rng.uniform(0.70, 0.95, size=n),
        "outcome": (rng.random(n) < yes_rate).astype(int),
    })


def test_realized_pnl_at_70c_yes_win() -> None:
    """YES win at 0.70: payoff 1.00, gross 0.30, round-trip fee 0.02,
    slippage 0.015 -> 0.265."""
    assert realized_pnl_per_contract(0.70, 1) == pytest.approx(0.265, abs=1e-6)


def test_realized_pnl_at_70c_no_loss() -> None:
    """NO at 0.70: payoff 0, gross -0.70, plus 0.02 fee + 0.015 slippage
    -> -0.735."""
    assert realized_pnl_per_contract(0.70, 0) == pytest.approx(-0.735, abs=1e-6)


def test_v1_decision_fn_trades_everything() -> None:
    """The v1 baseline used inside C6 trades every row in the eligible
    set unconditionally (returns True)."""
    decision, prob = v1_decision_fn({"favorite_price": 0.80, "outcome": 1})
    assert decision is True
    assert prob == 0.95


def test_evaluate_v1_baseline_on_synthetic_yields_positive_mean() -> None:
    """If yes_rate is 0.95, the v1 baseline should produce positive
    realized mean over a moderate sample."""
    df = _synthetic_df(n=200, yes_rate=0.95, seed=1)
    res = evaluate(df, v1_decision_fn, note="baseline_sanity")
    assert res.holdout_eligible_n > 0
    assert res.holdout_mean > 0
    # v2-vs-v1 delta is 0 when both decision fns are identical.
    assert res.criteria[f"C6_v2_beats_v1_by_>={int(PASS_C6_V2_BEATS_V1_PP*100)}pp"] is False


def test_evaluate_perfect_clairvoyance_beats_v1() -> None:
    """A 'cheating' decision fn that only trades known-YES rows should
    crush v1 baseline and pass C6."""
    df = _synthetic_df(n=200, yes_rate=0.92, seed=2)

    def clairvoyant(row: dict) -> tuple[bool, float]:
        return (row["outcome"] == 1, 1.0)

    res = evaluate(df, clairvoyant, note="clairvoyance_upper_bound")
    # All cleared trades have outcome=1 -> mean is positive
    assert res.holdout_mean > 0
    # v1 baseline trades everything so eats the NO outcomes
    assert res.holdout_mean - res.v1_holdout_mean >= PASS_C6_V2_BEATS_V1_PP
    assert res.criteria[f"C6_v2_beats_v1_by_>={int(PASS_C6_V2_BEATS_V1_PP*100)}pp"] is True


def test_evaluate_requires_columns() -> None:
    df = pd.DataFrame({"favorite_price": [0.70], "outcome": [1]})
    with pytest.raises(ValueError, match="missing columns"):
        evaluate(df, v1_decision_fn)


def test_evaluate_trainer_retrains_each_fold() -> None:
    """When a trainer is provided, the gate must call it per fold and
    use the fresh decision_fn for that fold's test slice. Without this
    refit, the 5-fold CV measures training-set fit (Round 5 critic
    finding)."""
    df = _synthetic_df(n=200, yes_rate=0.92, seed=3)
    train_calls: list[int] = []

    def trainer(train_df: pd.DataFrame) -> tuple:
        train_calls.append(len(train_df))

        def decision(row: dict) -> tuple[bool, float]:
            return (True, 0.95)

        return decision

    _ = evaluate(df, v1_decision_fn, trainer=trainer, note="trainer_refit")
    # trainer should be called once per fold (4 folds at default N_FOLDS=5)
    assert len(train_calls) == 4
    # Each fold's train prefix grows
    assert train_calls == sorted(train_calls)


def test_evaluate_warns_when_no_trainer_for_non_baseline() -> None:
    """If decision_fn is not v1_decision_fn AND no trainer is passed,
    GateResult.note must flag the leak risk so future readers don't
    rely on the contaminated 5-fold mean."""
    df = _synthetic_df(n=100, yes_rate=0.90, seed=4)

    def model_like(row: dict) -> tuple[bool, float]:
        return (row["favorite_price"] > 0.75, 0.95)

    res = evaluate(df, model_like, note="my_model")
    assert "LEAK-RISK" in res.note


def test_evaluate_no_leak_warning_for_v1_baseline() -> None:
    """v1 baseline doesn't train; no leak warning."""
    df = _synthetic_df(n=100, yes_rate=0.90, seed=5)
    res = evaluate(df, v1_decision_fn, note="v1_baseline")
    assert "LEAK-RISK" not in res.note
