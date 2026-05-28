"""Smoke tests for v5-b statcast_model trainer."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from kalshi_bot_v5.statcast_model import (
    EDGE_THRESHOLD,
    fit_model,
    make_anchored_decision_fn,
    make_trainer,
    predict_proba_row,
)


def _build_synth_df(n: int = 100, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    price = rng.uniform(0.1, 0.9, size=n)
    # Outcome roughly tracks price with noise.
    rand = rng.uniform(0, 1, size=n)
    outcome = (rand < price).astype(int)
    return pd.DataFrame({
        "favorite_price": price,
        "outcome": outcome,
        "close_time": pd.date_range("2026-01-01", periods=n, freq="h"),
    })


def test_make_trainer_returns_callable() -> None:
    df = _build_synth_df(50)
    trainer = make_trainer(["favorite_price"])
    decision_fn = trainer(df)
    assert callable(decision_fn)
    # Decision on a clear-no-trade row.
    out = decision_fn({"favorite_price": 0.8})
    assert isinstance(out, tuple)
    assert len(out) == 2
    assert isinstance(out[0], bool)


def test_trainer_handles_degenerate_train() -> None:
    df = pd.DataFrame({
        "favorite_price": [0.5, 0.5, 0.5],
        "outcome": [0, 0, 0],
        "close_time": pd.date_range("2026-01-01", periods=3, freq="h"),
    })
    trainer = make_trainer(["favorite_price"])
    fn = trainer(df)
    # Single-class y -> constant_fn that returns False for normal prices.
    should_trade, _ = fn({"favorite_price": 0.5})
    assert should_trade is False


def test_decision_fn_edge_threshold() -> None:
    df = _build_synth_df(200, seed=1)
    trainer = make_trainer(["favorite_price"])
    fn = trainer(df)
    # The decision rule is `prob > price + 0.02`. With one feature
    # (price), LogReg should approximately predict prob ~ price, so
    # the should_trade should be False for most rows.
    n_trade = 0
    for _, row in df.iterrows():
        out = fn(row.to_dict())
        if out[0]:
            n_trade += 1
    # Sanity: not all rows should trade.
    assert n_trade < len(df)


def test_anchored_decision_fn() -> None:
    df = _build_synth_df(80)
    model, scaler, _ = fit_model(df, ["favorite_price"])
    assert model is not None
    assert scaler is not None
    fn = make_anchored_decision_fn(model, scaler, ["favorite_price"])
    out = fn({"favorite_price": 0.6})
    assert isinstance(out, tuple)
    should_trade, prob = out
    assert 0.0 <= prob <= 1.0
    assert isinstance(should_trade, (bool, np.bool_))


def test_predict_proba_row_handles_nan_feature() -> None:
    df = _build_synth_df(50)
    df["nan_feat"] = np.nan
    df.loc[:30, "nan_feat"] = 1.0  # some non-NaN to allow fit
    # Drop NaN before fit.
    df_fit = df.dropna(subset=["nan_feat"])
    model, scaler, _ = fit_model(df_fit, ["favorite_price", "nan_feat"])
    assert model is not None
    # Row with NaN feature should return NaN.
    p = predict_proba_row(model, scaler, ["favorite_price", "nan_feat"],
                          {"favorite_price": 0.5, "nan_feat": np.nan})
    assert np.isnan(p)


def test_edge_threshold_constant() -> None:
    """The EDGE_THRESHOLD constant must be 0.02 per the locked brief."""
    assert EDGE_THRESHOLD == 0.02
