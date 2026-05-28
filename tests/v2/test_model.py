"""Sanity tests for the v2 MLB model."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from kalshi_bot_v2.model import (
    ALL_MODEL_FEATURES,
    DEFAULT_EDGE,
    DEFAULT_THRESHOLD,
    FEATURE_COLUMNS,
    INDICATOR_COLUMNS,
    feature_importance_df,
    featurize,
    load_artifact,
    make_decision_fn,
    predict_proba,
    reliability_table,
    save_artifact,
    train_with_threshold_search,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DATASET_PATH = REPO_ROOT / "data" / "v2" / "joined_mlb_dataset.parquet"
MODEL_PATH = REPO_ROOT / "data" / "v2" / "mlb_lgb_model.joblib"


def _synthetic_row(**overrides) -> dict:
    """Build a single synthetic dataset row with all required feature
    columns populated to defaults; overrides override.
    """
    base = {
        "ticker": "KXMLBGAME-25APR16XYZAB-XYZ",
        "favorite_price": 0.75,
        "wpct_diff": 0.10,
        "pyth_diff": 0.10,
        "run_diff_diff": 0.50,
        "fav_win_pct": 0.60,
        "fav_pyth_wpct": 0.60,
        "fav_recent_form_wpct": 0.60,
        "fav_run_diff_pg": 0.50,
        "fav_runs_scored_pg": 4.5,
        "fav_runs_allowed_pg": 4.0,
        "fav_home_wpct": 0.60,
        "fav_away_wpct": 0.55,
        "fav_vs_500_wpct": 0.55,
        "fav_games_played": 80,
        "dog_win_pct": 0.50,
        "dog_pyth_wpct": 0.50,
        "dog_recent_form_wpct": 0.50,
        "dog_run_diff_pg": 0.0,
        "dog_runs_scored_pg": 4.0,
        "dog_runs_allowed_pg": 4.0,
        "dog_games_played": 80,
        "is_favorite_home": True,
        "is_home": True,
        "h2h_wpct": 0.50,
        "h2h_n": 4,
        "days_rest": 1,
        "vwap_n_trades_in_window": 20,
        "vwap_volume_fp_in_window": 100.0,
        "one_sided_flow_pct": 0.55,
    }
    base.update(overrides)
    return base


def test_feature_columns_well_defined() -> None:
    """The feature columns list should be non-empty, unique, and the
    indicator-columns set should not overlap with raw feature columns.
    """
    assert len(FEATURE_COLUMNS) > 5
    assert len(set(FEATURE_COLUMNS)) == len(FEATURE_COLUMNS)
    assert set(INDICATOR_COLUMNS).isdisjoint(set(FEATURE_COLUMNS))
    assert "favorite_price" in FEATURE_COLUMNS
    assert ALL_MODEL_FEATURES == FEATURE_COLUMNS + INDICATOR_COLUMNS


def test_featurize_handles_full_row() -> None:
    """featurize should turn a fully-populated row into a feature DataFrame
    with no NaN in the indicator columns and the expected column order.
    """
    row = _synthetic_row()
    df = pd.DataFrame([row])
    feat = featurize(df)
    assert feat.shape == (1, len(ALL_MODEL_FEATURES))
    assert list(feat.columns) == ALL_MODEL_FEATURES
    # Indicators should all be 0 when their source columns are populated
    assert feat["h2h_wpct_missing"].iloc[0] == 0
    assert feat["fav_vs_500_wpct_missing"].iloc[0] == 0
    assert feat["one_sided_flow_pct_missing"].iloc[0] == 0


def test_featurize_marks_missing_with_indicator() -> None:
    """When a nullable column is NaN, the corresponding indicator column
    should be 1.
    """
    row = _synthetic_row(h2h_wpct=np.nan, fav_vs_500_wpct=np.nan)
    df = pd.DataFrame([row])
    feat = featurize(df)
    assert feat["h2h_wpct_missing"].iloc[0] == 1
    assert feat["fav_vs_500_wpct_missing"].iloc[0] == 1
    assert feat["one_sided_flow_pct_missing"].iloc[0] == 0


def test_featurize_casts_boolean_to_numeric() -> None:
    """LightGBM does not accept boolean columns directly; featurize should
    cast them to int.
    """
    row = _synthetic_row(is_favorite_home=True, is_home=False)
    df = pd.DataFrame([row])
    feat = featurize(df)
    assert pd.api.types.is_numeric_dtype(feat["is_favorite_home"])
    assert feat["is_favorite_home"].iloc[0] == 1
    assert feat["is_home"].iloc[0] == 0


def test_featurize_missing_column_raises() -> None:
    """featurize should raise ValueError if a required column is missing."""
    df = pd.DataFrame([{"foo": 1}])
    with pytest.raises(ValueError, match="missing column"):
        featurize(df)


def test_reliability_table_shape() -> None:
    """reliability_table should produce one row per bin with the expected
    columns.
    """
    probs = np.array([0.1, 0.2, 0.5, 0.6, 0.9])
    outcomes = np.array([0, 0, 1, 1, 1])
    table = reliability_table(probs, outcomes, n_bins=10)
    assert len(table) == 10
    assert list(table.columns) == ["bin_lower", "bin_upper", "n", "mean_pred", "mean_actual"]
    # First and last bins should reflect single rows there
    assert table.loc[1, "n"] == 1  # 0.1 in [0.1, 0.2) -> wait, 0.1 is exactly 0.1 boundary
    # Just check totals match
    assert table["n"].sum() == 5


@pytest.mark.skipif(not DATASET_PATH.exists(), reason="dataset not built")
def test_train_and_predict_on_real_dataset() -> None:
    """End-to-end: train a model on the real dataset, predict on it,
    verify shapes and ranges.
    """
    df = pd.read_parquet(DATASET_PATH)
    df_sorted = df.sort_values("close_time").reset_index(drop=True)
    # Use first 70% as train to mirror the gate split
    split_idx = int(len(df_sorted) * 0.70)
    train_df = df_sorted.iloc[:split_idx]
    artifact = train_with_threshold_search(
        train_df, val_frac=0.20, calibrate=False,
        use_walk_forward_for_scan=False,
    )
    assert artifact.booster is not None
    assert artifact.feature_names == ALL_MODEL_FEATURES
    # threshold and edge should be sensible
    assert 0.0 <= artifact.threshold <= 1.0
    assert -0.5 <= artifact.edge_threshold <= 0.5
    # Predict on the full dataset (train + holdout) without errors
    probs = predict_proba(artifact, df_sorted)
    assert probs.shape == (len(df_sorted),)
    assert ((probs >= 0.0) & (probs <= 1.0)).all()


@pytest.mark.skipif(not MODEL_PATH.exists(), reason="model not trained")
def test_load_artifact_and_decision_fn() -> None:
    """Load a saved model and exercise the decision function on a single
    row in each mode.
    """
    artifact = load_artifact(MODEL_PATH)
    assert artifact.booster is not None

    # Build a tiny dataframe with one row to feed the decision_fn
    row = _synthetic_row()
    df = pd.DataFrame([row])
    df["close_time"] = pd.Timestamp("2025-09-15", tz="UTC")
    df["outcome"] = 1

    for mode in ("hybrid", "edge", "absolute"):
        decision_fn = make_decision_fn(artifact, df, mode=mode)
        should_trade, prob = decision_fn(row)
        assert isinstance(should_trade, (bool, np.bool_))
        assert 0.0 <= prob <= 1.0


def test_save_and_load_round_trip(tmp_path: Path) -> None:
    """Save a freshly-trained tiny model and reload it; predictions should
    match within floating-point tolerance.
    """
    # Build a tiny synthetic train dataframe with all required columns.
    rng = np.random.default_rng(seed=0)
    rows = [
        _synthetic_row(
            favorite_price=float(0.55 + 0.20 * rng.random()),
            wpct_diff=float(0.3 * (rng.random() - 0.5)),
        )
        for _ in range(120)
    ]
    df = pd.DataFrame(rows)
    df["close_time"] = pd.date_range("2025-04-01", periods=len(df), freq="D", tz="UTC")
    df["outcome"] = (rng.random(len(df)) < 0.6).astype(int)
    df["is_strategy_b_eligible"] = (df["favorite_price"] >= 0.70).astype(bool)
    df["ticker"] = [f"KXTEST{i}" for i in range(len(df))]

    artifact = train_with_threshold_search(
        df, val_frac=0.20, calibrate=False,
        use_walk_forward_for_scan=False,
    )

    out_path = tmp_path / "tiny_model.joblib"
    save_artifact(artifact, out_path)
    reloaded = load_artifact(out_path)

    probs_orig = predict_proba(artifact, df)
    probs_reload = predict_proba(reloaded, df)
    np.testing.assert_allclose(probs_orig, probs_reload, atol=1e-9)
    assert reloaded.threshold == artifact.threshold
    assert reloaded.edge_threshold == artifact.edge_threshold


def test_feature_importance_returns_sorted_df() -> None:
    """After training a tiny model, feature_importance_df should return a
    DataFrame sorted by gain descending.
    """
    rng = np.random.default_rng(seed=1)
    rows = []
    for _ in range(120):
        rows.append(_synthetic_row(
            favorite_price=float(0.55 + 0.20 * rng.random()),
            wpct_diff=float(0.3 * (rng.random() - 0.5)),
        ))
    df = pd.DataFrame(rows)
    df["close_time"] = pd.date_range("2025-04-01", periods=len(df), freq="D", tz="UTC")
    df["outcome"] = (rng.random(len(df)) < 0.6).astype(int)
    df["is_strategy_b_eligible"] = True
    df["ticker"] = [f"KXTEST{i}" for i in range(len(df))]
    artifact = train_with_threshold_search(
        df, val_frac=0.20, calibrate=False,
        use_walk_forward_for_scan=False,
    )
    imp = feature_importance_df(artifact, importance_type="gain")
    assert {"feature", "importance_gain"} <= set(imp.columns)
    # Sorted descending
    vals = imp["importance_gain"].to_numpy()
    assert all(vals[i] >= vals[i + 1] for i in range(len(vals) - 1))


def test_default_threshold_and_edge_are_sensible() -> None:
    """The domain-motivated defaults should match the Strategy B band."""
    assert 0.5 <= DEFAULT_THRESHOLD <= 0.95
    assert -0.30 <= DEFAULT_EDGE <= 0.0
