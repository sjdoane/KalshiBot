"""v2 MLB favorite-win model: LightGBM binary classifier with isotonic
calibration on top.

The model predicts P(favorite wins) given pre-game matchup features. It is
trained on ALL rows of the joined MLB dataset (not just the
Strategy-B-eligible 0.70-0.95 price band) so it learns a true probability
function across all price levels; the gate then applies the model on the
eligible subset only.

Decision rule: trade YES on the favorite if predicted_prob >= THRESHOLD.
The right THRESHOLD is set by `train_with_threshold_search` to maximize
realized P&L on a TRAIN-only validation slice (no peeking at the gate's
holdout).

This module is research-mode only. Nothing imports back into
`kalshi_bot/*` live-trading code.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import joblib
import lightgbm as lgb
import numpy as np
import structlog
from sklearn.isotonic import IsotonicRegression

if TYPE_CHECKING:
    from pathlib import Path

    import pandas as pd

log = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Feature schema
# ---------------------------------------------------------------------------
# Selected for: low null rate on eligible rows, no look-ahead (computed AS OF
# the day before the game per dataset Section 6), and mechanical relevance to
# game outcome prediction.
#
# Includes favorite_price because that IS the market's own probability
# estimate; the model has to learn when its own estimate diverges from the
# price. Without favorite_price the model has no information about which
# trades the strategy is selecting.

FEATURE_COLUMNS: list[str] = [
    # Market price (the consensus probability)
    "favorite_price",
    # Team strength differentials (favorite - underdog)
    "wpct_diff",
    "pyth_diff",
    "run_diff_diff",
    # Favorite team strength
    "fav_win_pct",
    "fav_pyth_wpct",
    "fav_recent_form_wpct",
    "fav_run_diff_pg",
    "fav_runs_scored_pg",
    "fav_runs_allowed_pg",
    "fav_home_wpct",
    "fav_away_wpct",
    "fav_vs_500_wpct",
    "fav_games_played",
    # Underdog team strength
    "dog_win_pct",
    "dog_pyth_wpct",
    "dog_recent_form_wpct",
    "dog_run_diff_pg",
    "dog_runs_scored_pg",
    "dog_runs_allowed_pg",
    "dog_games_played",
    # Matchup context
    "is_favorite_home",
    "is_home",
    "h2h_wpct",
    "h2h_n",
    "days_rest",
    # Microstructure
    "vwap_n_trades_in_window",
    "vwap_volume_fp_in_window",
    "one_sided_flow_pct",
]

# Indicator columns added for missing-value awareness; LightGBM handles NaN
# natively but adding the indicator helps when missingness itself is
# informative (e.g. h2h_n == 0 means no prior matchup).
INDICATOR_COLUMNS: list[str] = [
    "h2h_wpct_missing",
    "fav_vs_500_wpct_missing",
    "one_sided_flow_pct_missing",
]

ALL_MODEL_FEATURES: list[str] = FEATURE_COLUMNS + INDICATOR_COLUMNS

TARGET_COLUMN: str = "outcome"

# Hyperparameters chosen for small-sample regime (~1500 training rows;
# only ~90 of which are price-eligible). Modest depth and regularization
# to avoid overfitting while preserving signal resolution. Bagging is
# enabled (bagging_fraction=0.85) as an additional regularizer; the seed
# pins make the bagged sequence reproducible across runs.
LGBM_PARAMS: dict[str, Any] = {
    "objective": "binary",
    "metric": "binary_logloss",
    "learning_rate": 0.05,
    "n_estimators": 300,
    "max_depth": 4,
    "num_leaves": 15,
    "min_data_in_leaf": 20,
    "min_split_gain": 0.0,
    "feature_fraction": 0.85,
    "bagging_fraction": 0.85,
    "bagging_freq": 1,
    "lambda_l2": 1.0,
    "verbose": -1,
    "random_state": 42,
    "force_row_wise": True,
    "n_jobs": 1,
    "seed": 42,
    "feature_fraction_seed": 42,
    "bagging_seed": 42,
    "data_random_seed": 42,
}

# Decision thresholds: model_prob - favorite_price >= eps. Trade only when
# the model thinks the favorite is MORE likely to win than the market price
# suggests, plus an absolute model_prob floor that mirrors the Strategy B
# eligibility lower bound. The hybrid rule is more robust than either
# threshold alone when the val sample is too small for reliable scanning.
EDGE_GRID: list[float] = [-0.10, -0.05, -0.02, 0.0, 0.02, 0.05, 0.10]
THRESHOLD_GRID: list[float] = [0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.88, 0.90, 0.92, 0.94, 0.96, 0.98]

# Default decision rule for small-val-sample regime: model_prob >= 0.70 AND
# (model_prob - price) >= -0.10. Both numbers are motivated by domain logic:
# the 0.70 floor mirrors the Strategy B eligibility lower bound (we are
# trading favorites priced 0.70+, so requiring the model to also think
# favorite is at least 70% likely is internally consistent). The -0.10
# edge is permissive: we accept trades where the model disagrees with the
# price by up to 10pp, requiring only that the model does not STRONGLY
# disagree with the price. Neither value is chosen by holdout-fitting; both
# are chosen before holdout is evaluated. The val-slice scan can override
# these defaults when the scan has enough rows to be reliable.
DEFAULT_THRESHOLD: float = 0.70
DEFAULT_EDGE: float = -0.10


def featurize(df: pd.DataFrame) -> pd.DataFrame:
    """Build the model feature matrix from a raw joined MLB DataFrame.

    Adds indicator columns for the three features that can be null and
    casts boolean columns to numeric so LightGBM can ingest them.
    """
    import pandas as pd

    out_cols: dict[str, pd.Series] = {}
    for col in FEATURE_COLUMNS:
        if col not in df.columns:
            raise ValueError(f"featurize: missing column {col!r}")
        series = df[col]
        if series.dtype == bool:
            series = series.astype(int)
        out_cols[col] = series
    # Missing-value indicators
    out_cols["h2h_wpct_missing"] = df["h2h_wpct"].isna().astype(int)
    out_cols["fav_vs_500_wpct_missing"] = df["fav_vs_500_wpct"].isna().astype(int)
    out_cols["one_sided_flow_pct_missing"] = df["one_sided_flow_pct"].isna().astype(int)
    feat = pd.DataFrame(out_cols, index=df.index)
    # Ensure column order matches ALL_MODEL_FEATURES
    return feat[ALL_MODEL_FEATURES]


@dataclass
class ModelArtifact:
    """Bundle of LightGBM booster + isotonic calibrator + best edge threshold.

    The decision rule is: trade if (predicted_prob - favorite_price) >= edge.
    Edge is set by walk-forward validation on train_df; gate evaluates on
    holdout.
    """

    booster: lgb.Booster
    calibrator: IsotonicRegression | None
    threshold: float  # legacy: absolute prob threshold; kept for inspection
    edge_threshold: float  # primary: prob - price threshold
    feature_names: list[str]
    notes: dict[str, Any]


def _kalshi_pnl_per_contract(yes_price: float, outcome: int) -> float:
    """Mirror of `kalshi_bot_v2.gate.realized_pnl_per_contract` for use
    inside the threshold scan; cannot import the gate here to avoid a
    circular dep. The gate's official formula is used at evaluation time.
    """
    from kalshi_bot.analysis.metrics import kalshi_maker_fee_per_contract

    gross = outcome - yes_price
    fee = 2.0 * kalshi_maker_fee_per_contract(yes_price)
    slippage = 0.015
    return gross - fee - slippage


def _expected_pnl_for_threshold(
    probs: np.ndarray, prices: np.ndarray, outcomes: np.ndarray,
    threshold: float,
) -> tuple[float, int]:
    """For a given absolute threshold, compute mean realized P&L over the
    trades that pass `probs >= threshold`. Returns (mean_pnl, n_trades).
    n_trades=0 -> NaN.
    """
    mask = probs >= threshold
    n = int(mask.sum())
    if n == 0:
        return float("nan"), 0
    pnls = np.array(
        [_kalshi_pnl_per_contract(float(p), int(y))
         for p, y in zip(prices[mask], outcomes[mask], strict=False)]
    )
    return float(pnls.mean()), n


def _expected_pnl_for_edge(
    probs: np.ndarray, prices: np.ndarray, outcomes: np.ndarray,
    edge: float,
) -> tuple[float, int]:
    """For a given edge threshold (model_prob - price >= edge), compute
    mean realized P&L over the trades that pass.
    """
    mask = (probs - prices) >= edge
    n = int(mask.sum())
    if n == 0:
        return float("nan"), 0
    pnls = np.array(
        [_kalshi_pnl_per_contract(float(p), int(y))
         for p, y in zip(prices[mask], outcomes[mask], strict=False)]
    )
    return float(pnls.mean()), n


def _walk_forward_oos_predictions(
    train_df: pd.DataFrame, n_folds: int = 4, calibrate: bool = True,
) -> tuple[np.ndarray, np.ndarray]:
    """Generate out-of-sample predictions on train_df via time-walk-forward
    folds. Each fold trains on the chronological prefix and predicts on the
    next chunk; the predictions are concatenated into one OOS series the
    same length as train_df (with the first fold's rows getting NaN since
    they were used purely for the initial training set).

    Returns (oos_probs, valid_mask) where valid_mask marks rows that have
    OOS predictions (the first fold of rows is excluded).
    """
    train_df = train_df.sort_values("close_time").reset_index(drop=True)
    n = len(train_df)
    fold_size = n // n_folds
    if fold_size < 5:
        raise ValueError(
            f"_walk_forward_oos_predictions: fold_size too small ({fold_size})",
        )
    oos_probs = np.full(n, np.nan)
    valid_mask = np.zeros(n, dtype=bool)
    for fold in range(1, n_folds):
        tr_end = fold * fold_size
        te_end = (fold + 1) * fold_size if fold < n_folds - 1 else n
        tr_idx = np.arange(0, tr_end)
        te_idx = np.arange(tr_end, te_end)
        tr_df = train_df.iloc[tr_idx]
        te_df = train_df.iloc[te_idx]
        x_tr = featurize(tr_df)
        y_tr = tr_df[TARGET_COLUMN].astype(int).to_numpy()
        x_te = featurize(te_df)
        train_set = lgb.Dataset(x_tr, label=y_tr, free_raw_data=False)
        params = dict(LGBM_PARAMS)
        n_rounds = int(params.pop("n_estimators"))
        booster = lgb.train(params, train_set, num_boost_round=n_rounds)
        te_probs = booster.predict(x_te)
        # Optionally calibrate on a held-out tail of tr_df
        if calibrate and len(tr_df) >= 100:
            # Use last 20% of tr as inner-val for calibration
            cal_split = int(len(tr_df) * 0.8)
            cal_df = tr_df.iloc[cal_split:]
            cal_x = featurize(cal_df)
            cal_y = cal_df[TARGET_COLUMN].astype(int).to_numpy()
            cal_raw = booster.predict(cal_x)
            try:
                cal = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip")
                cal.fit(cal_raw, cal_y)
                te_probs = cal.predict(te_probs)
            except Exception:  # noqa: BLE001
                pass  # raw probs OK as a fallback
        oos_probs[te_idx] = te_probs
        valid_mask[te_idx] = True
    return oos_probs, valid_mask


def train_with_threshold_search(
    train_df: pd.DataFrame,
    *,
    val_frac: float = 0.20,
    calibrate: bool = True,
    rng_seed: int = 42,
    use_walk_forward_for_scan: bool = True,
) -> ModelArtifact:
    """Train LightGBM + (optional) isotonic calibrator + scan thresholds.

    Args:
        train_df: TRAIN portion of the dataset (chronological prefix
            of the full dataset; do NOT include holdout rows).
        val_frac: fraction of train_df held out for calibration +
            threshold-selection; the booster is trained on the rest.
        calibrate: if True, fit isotonic regression on the val slice to
            calibrate raw LGB probabilities.
        rng_seed: numpy seed for reproducible val split.
        use_walk_forward_for_scan: if True, scan thresholds against
            walk-forward OOS predictions across train_df (more robust on
            small samples; gives the scan a larger eligible-row pool).

    Returns:
        ModelArtifact with booster, calibrator, best threshold, and
        scan notes for the results doc.
    """
    if len(train_df) < 50:
        raise ValueError(
            f"train_with_threshold_search: too few train rows ({len(train_df)})"
        )

    # Sort chronologically so the val slice is the tail of train (purer
    # walk-forward, no future leak into calibration)
    train_df = train_df.sort_values("close_time").reset_index(drop=True)
    n = len(train_df)
    val_split_idx = int(n * (1.0 - val_frac))
    inner_train = train_df.iloc[:val_split_idx]
    inner_val = train_df.iloc[val_split_idx:]

    # Build features
    x_train = featurize(inner_train)
    y_train = inner_train[TARGET_COLUMN].astype(int).to_numpy()
    x_val = featurize(inner_val)
    y_val = inner_val[TARGET_COLUMN].astype(int).to_numpy()

    log.info(
        "model_train_start",
        train_n=len(inner_train),
        val_n=len(inner_val),
        n_features=x_train.shape[1],
    )

    # Train booster with early stopping on val
    train_set = lgb.Dataset(x_train, label=y_train, free_raw_data=False)
    val_set = lgb.Dataset(x_val, label=y_val, reference=train_set, free_raw_data=False)
    params = dict(LGBM_PARAMS)
    n_rounds = int(params.pop("n_estimators"))
    booster = lgb.train(
        params,
        train_set,
        num_boost_round=n_rounds,
        valid_sets=[val_set],
        valid_names=["val"],
        callbacks=[
            lgb.early_stopping(stopping_rounds=30, verbose=False),
            lgb.log_evaluation(period=0),
        ],
    )

    val_raw_probs = booster.predict(x_val, num_iteration=booster.best_iteration)

    # Isotonic calibration
    calibrator: IsotonicRegression | None = None
    if calibrate:
        calibrator = IsotonicRegression(
            y_min=0.0, y_max=1.0, out_of_bounds="clip",
        )
        calibrator.fit(val_raw_probs, y_val)
        val_cal_probs = calibrator.predict(val_raw_probs)
    else:
        val_cal_probs = val_raw_probs

    # Threshold scan: prefer walk-forward OOS predictions on train_df for
    # a larger eligible-row sample, fall back to the val-slice scan if
    # walk-forward is disabled or fails.
    val_eligible = inner_val["is_strategy_b_eligible"].to_numpy().astype(bool)
    val_prices = inner_val["favorite_price"].to_numpy()
    val_outcomes = y_val

    if use_walk_forward_for_scan:
        try:
            wf_probs, wf_valid = _walk_forward_oos_predictions(
                train_df, n_folds=4, calibrate=calibrate,
            )
            # Only use the walk-forward predictions where they exist AND
            # the row is Strategy-B-eligible
            train_eligible = train_df["is_strategy_b_eligible"].to_numpy().astype(bool)
            train_prices = train_df["favorite_price"].to_numpy()
            train_outcomes = train_df[TARGET_COLUMN].astype(int).to_numpy()
            scan_mask = wf_valid & train_eligible
            val_probs_for_scan = wf_probs[scan_mask]
            val_prices_eligible = train_prices[scan_mask]
            val_outcomes_eligible = train_outcomes[scan_mask]
            log.info(
                "walk_forward_scan_pool",
                pool_n=int(scan_mask.sum()),
                outcome_rate=float(val_outcomes_eligible.mean())
                if val_outcomes_eligible.size > 0 else float("nan"),
            )
        except Exception as e:  # noqa: BLE001
            log.warning("walk_forward_failed", error=str(e))
            val_probs_for_scan = val_cal_probs[val_eligible]
            val_prices_eligible = val_prices[val_eligible]
            val_outcomes_eligible = val_outcomes[val_eligible]
    else:
        val_probs_for_scan = val_cal_probs[val_eligible]
        val_prices_eligible = val_prices[val_eligible]
        val_outcomes_eligible = val_outcomes[val_eligible]

    scan_results: list[dict[str, Any]] = []
    edge_scan_results: list[dict[str, Any]] = []
    # Require at least 15 eligible val rows for the scan results to be
    # statistically meaningful enough to override the domain-motivated
    # defaults. With fewer than 15, we fall back to defaults to avoid
    # accepting noisy threshold picks.
    min_val_for_scan_override = 15
    if val_probs_for_scan.size < min_val_for_scan_override:
        log.warning(
            "val_scan_too_small_using_defaults",
            val_n=int(val_probs_for_scan.size),
            min_required=min_val_for_scan_override,
        )
        best_threshold = DEFAULT_THRESHOLD
        best_edge = DEFAULT_EDGE
        # Populate scan results for reporting even when defaults win
        for t in THRESHOLD_GRID:
            mean_pnl, n_trades = _expected_pnl_for_threshold(
                val_probs_for_scan, val_prices_eligible, val_outcomes_eligible, t,
            )
            scan_results.append({
                "threshold": float(t),
                "n_trades": int(n_trades),
                "mean_pnl": float(mean_pnl) if not np.isnan(mean_pnl) else float("nan"),
            })
        for eps in EDGE_GRID:
            mean_pnl, n_trades = _expected_pnl_for_edge(
                val_probs_for_scan, val_prices_eligible, val_outcomes_eligible, eps,
            )
            edge_scan_results.append({
                "edge": float(eps),
                "n_trades": int(n_trades),
                "mean_pnl": float(mean_pnl) if not np.isnan(mean_pnl) else float("nan"),
            })
    elif val_probs_for_scan.size == 0:
        log.warning("threshold_scan_no_eligible_val", val_n=len(inner_val))
        best_threshold = DEFAULT_THRESHOLD
        best_edge = DEFAULT_EDGE
    else:
        # Absolute-threshold scan (legacy / informational)
        for t in THRESHOLD_GRID:
            mean_pnl, n_trades = _expected_pnl_for_threshold(
                val_probs_for_scan, val_prices_eligible, val_outcomes_eligible, t,
            )
            scan_results.append({
                "threshold": float(t),
                "n_trades": int(n_trades),
                "mean_pnl": float(mean_pnl) if not np.isnan(mean_pnl) else float("nan"),
            })
        # For absolute-threshold candidates, require at least 5 trades for
        # statistical meaning (since the WF pool can be larger).
        min_n_for_candidate = max(
            5, int(0.05 * len(val_probs_for_scan)),
        )
        candidates = [
            r for r in scan_results
            if r["n_trades"] >= min_n_for_candidate and not np.isnan(r["mean_pnl"])
        ]
        if candidates:
            best = max(candidates, key=lambda r: r["mean_pnl"])
            best_threshold = best["threshold"]
        else:
            log.warning("threshold_scan_no_candidates", scan=scan_results)
            best_threshold = DEFAULT_THRESHOLD
        # Edge-threshold scan (primary decision rule)
        for eps in EDGE_GRID:
            mean_pnl, n_trades = _expected_pnl_for_edge(
                val_probs_for_scan, val_prices_eligible, val_outcomes_eligible, eps,
            )
            edge_scan_results.append({
                "edge": float(eps),
                "n_trades": int(n_trades),
                "mean_pnl": float(mean_pnl) if not np.isnan(mean_pnl) else float("nan"),
            })
        min_n_for_edge = max(5, int(0.05 * len(val_probs_for_scan)))
        edge_candidates = [
            r for r in edge_scan_results
            if r["n_trades"] >= min_n_for_edge and not np.isnan(r["mean_pnl"])
        ]
        if edge_candidates:
            # Tie-breaker: among candidates with statistically meaningful
            # n_trades, pick the highest-mean-pnl edge. If multiple
            # edges tie, prefer the LARGER edge (less permissive) for
            # better expected selectivity.
            best_edge_row = max(
                edge_candidates,
                key=lambda r: (r["mean_pnl"], r["edge"]),
            )
            best_edge = best_edge_row["edge"]
        else:
            log.warning("edge_scan_no_candidates", scan=edge_scan_results)
            best_edge = DEFAULT_EDGE

    # Retrain on the FULL train_df (inner_train + inner_val) with same
    # best_iteration so we use all training data for the final model.
    x_full = featurize(train_df)
    y_full = train_df[TARGET_COLUMN].astype(int).to_numpy()
    final_train_set = lgb.Dataset(x_full, label=y_full, free_raw_data=False)
    final_n_rounds = booster.best_iteration if booster.best_iteration else n_rounds
    final_booster = lgb.train(
        params,
        final_train_set,
        num_boost_round=final_n_rounds,
    )

    log.info(
        "model_train_done",
        best_iteration=booster.best_iteration,
        best_threshold=best_threshold,
        best_edge=best_edge,
        val_eligible_n=int(val_eligible.sum()),
    )

    return ModelArtifact(
        booster=final_booster,
        calibrator=calibrator,
        threshold=float(best_threshold),
        edge_threshold=float(best_edge),
        feature_names=ALL_MODEL_FEATURES,
        notes={
            "best_iteration": int(booster.best_iteration) if booster.best_iteration else final_n_rounds,
            "inner_train_n": len(inner_train),
            "inner_val_n": len(inner_val),
            "val_eligible_n": int(val_eligible.sum()),
            "threshold_scan": scan_results,
            "edge_scan": edge_scan_results,
            "lgbm_params": LGBM_PARAMS,
        },
    )


def predict_proba(artifact: ModelArtifact, df: pd.DataFrame) -> np.ndarray:
    """Predict calibrated P(favorite wins) for each row of df.

    Returns a 1-d numpy array of probabilities aligned with df rows.
    """
    x = featurize(df)
    raw = artifact.booster.predict(x)
    if artifact.calibrator is not None:
        return artifact.calibrator.predict(raw)
    return raw


def make_decision_fn(artifact: ModelArtifact, df: pd.DataFrame, *,
                     mode: str = "hybrid"):
    """Wrap a trained artifact + the full dataset into a gate-compatible
    decision_fn `(row_dict) -> (should_trade, predicted_yes_prob)`.

    Modes:
        "hybrid"   - trade if (model_prob >= threshold) AND
                     (model_prob - favorite_price) >= edge_threshold
        "edge"     - trade if (model_prob - favorite_price) >= edge_threshold
        "absolute" - trade if model_prob >= threshold

    The hybrid mode is the primary recommended mode; it combines an
    absolute-confidence floor (the model is at least 70% sure) with a
    direction check (the model is not strongly contradicting the price).

    Since the gate calls decision_fn row-by-row, we precompute predictions
    indexed by ticker so the row lookup is O(1).
    """
    probs = predict_proba(artifact, df)
    prob_by_ticker = dict(zip(df["ticker"].to_numpy(), probs, strict=False))
    threshold = artifact.threshold
    edge = artifact.edge_threshold

    if mode not in {"hybrid", "edge", "absolute"}:
        raise ValueError(f"make_decision_fn: unknown mode {mode!r}")

    def decision_fn(row: dict) -> tuple[bool, float]:
        ticker = row.get("ticker")
        if ticker not in prob_by_ticker:
            return False, 0.0
        prob = float(prob_by_ticker[ticker])
        price = float(row.get("favorite_price", 0.0))
        if mode == "hybrid":
            return (prob >= threshold) and ((prob - price) >= edge), prob
        if mode == "edge":
            return (prob - price) >= edge, prob
        return prob >= threshold, prob

    return decision_fn


def save_artifact(artifact: ModelArtifact, path: Path) -> None:
    """Persist a ModelArtifact to disk. LightGBM Booster is serialized
    via its native model_to_string; the calibrator and metadata pickled
    around it.
    """
    payload = {
        "booster_str": artifact.booster.model_to_string(),
        "calibrator": artifact.calibrator,
        "threshold": artifact.threshold,
        "edge_threshold": artifact.edge_threshold,
        "feature_names": artifact.feature_names,
        "notes": artifact.notes,
    }
    joblib.dump(payload, path)


def load_artifact(path: Path) -> ModelArtifact:
    """Reload a saved ModelArtifact from disk."""
    payload = joblib.load(path)
    booster = lgb.Booster(model_str=payload["booster_str"])
    return ModelArtifact(
        booster=booster,
        calibrator=payload["calibrator"],
        threshold=float(payload["threshold"]),
        edge_threshold=float(payload.get("edge_threshold", 0.0)),
        feature_names=payload["feature_names"],
        notes=payload.get("notes", {}),
    )


def feature_importance_df(artifact: ModelArtifact, importance_type: str = "gain") -> pd.DataFrame:
    """Return a sorted DataFrame of feature_name + importance (gain by default)."""
    import pandas as pd

    importances = artifact.booster.feature_importance(importance_type=importance_type)
    return pd.DataFrame({
        "feature": artifact.feature_names,
        f"importance_{importance_type}": importances,
    }).sort_values(f"importance_{importance_type}", ascending=False).reset_index(drop=True)


def reliability_table(
    probs: np.ndarray, outcomes: np.ndarray, *, n_bins: int = 10,
) -> pd.DataFrame:
    """Build a reliability table for calibration assessment.

    Each row: bin_lower, bin_upper, n, mean_pred, mean_actual.
    """
    import pandas as pd

    p = np.asarray(probs, dtype=float)
    y = np.asarray(outcomes, dtype=float)
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    bin_idx = np.digitize(p, edges, right=False) - 1
    bin_idx = np.clip(bin_idx, 0, n_bins - 1)
    rows = []
    for b in range(n_bins):
        mask = bin_idx == b
        n = int(mask.sum())
        if n == 0:
            mean_pred = float("nan")
            mean_actual = float("nan")
        else:
            mean_pred = float(p[mask].mean())
            mean_actual = float(y[mask].mean())
        rows.append({
            "bin_lower": float(edges[b]),
            "bin_upper": float(edges[b + 1]),
            "n": n,
            "mean_pred": mean_pred,
            "mean_actual": mean_actual,
        })
    return pd.DataFrame(rows)
