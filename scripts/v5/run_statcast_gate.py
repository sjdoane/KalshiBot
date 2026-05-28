"""V5-B2: Run the locked 6-criteria gate on the Statcast prop dataset.

Three gate evaluations:
    G1: v1-style flat-prior baseline (`v1_decision_fn` from gate.py).
    G2: Baseline LogReg (favorite_price only).
    G3: Tuned LogReg (favorite_price + orthogonality survivors).

Custom modification: the bootstrap_mean_ci call inside the gate runner
is monkey-patched to use a cluster-bootstrap-by-game-date variant. This
is necessary because the 60-day-window data has only ~60 distinct
game-dates; row-level bootstrap underestimates variance.

The monkey-patch leaves `kalshi_bot.analysis.bootstrap.bootstrap_mean_ci`
unchanged for OTHER callers; only the symbol imported into
`kalshi_bot_v2.gate` is replaced.

Outputs:
    data/v5/statcast_gate_results.json - full GateResult dicts for
    G1/G2/G3, plus calibration analysis, S1/S2/S3 sanity checks, and
    sportsbook-spread realism check.

Invoke with:
    uv run python -m scripts.v5.run_statcast_gate
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import structlog

# Patch BEFORE importing the gate so the gate sees the cluster-bootstrap
# version. The gate imports `bootstrap_mean_ci` from
# `kalshi_bot.analysis.bootstrap` into its module namespace; we override
# it by patching the gate's module-level name AFTER import.
from kalshi_bot.analysis.bootstrap import bootstrap_mean_ci as _row_bootstrap

import kalshi_bot_v2.gate as _gate_module
from kalshi_bot_v2.gate import (
    BOOTSTRAP_CI,
    BOOTSTRAP_N_RESAMPLES,
    BOOTSTRAP_SEED,
    HOLDOUT_FRAC,
    N_FOLDS,
    GateResult,
    realized_pnl_per_contract,
    v1_decision_fn,
)
from kalshi_bot_v5.statcast_features import get_feature_column_names
from kalshi_bot_v5.statcast_model import (
    EDGE_THRESHOLD,
    LOGREG_C,
    LOGREG_MAX_ITER,
    LOGREG_RANDOM_STATE,
    fit_model,
    make_anchored_decision_fn,
    make_trainer,
)

log = structlog.get_logger(__name__)

DATASET_PATH = Path("data/v5/prop_dataset.parquet")
ORTHOGONALITY_REPORT_PATH = Path("data/v5/v5b_orthogonality_report.json")
OUTPUT_JSON = Path("data/v5/statcast_gate_results.json")

# Calibration bin edges for ECE at 5 price buckets across [0, 1].
ECE_PRICE_BIN_EDGES = [0.0, 0.20, 0.40, 0.60, 0.80, 1.0]

# Sportsbook-spread realism: subtract this many dollars per trade as a
# proxy for the documented 5-10c bid-ask spread on illiquid prop
# markets. V5-B1 Section 5.2 referenced 5-10c; we use 5c as the floor.
SPORTSBOOK_SPREAD_DOLLARS = 0.05


def _make_cluster_bootstrap_fn(
    df: pd.DataFrame,
    *,
    cluster_col: str = "game_date_parsed",
) -> Any:
    """Build a bootstrap_mean_ci replacement that clusters realized
    P&L values by the provided cluster column.

    The gate calls `bootstrap_mean_ci(values, n_resamples, ci, rng_seed)`
    on a 1-D array of realized P&Ls. To do cluster-bootstrap, we need
    to know the cluster identifier for each value. The gate constructs
    its `values` array in-order by iterating `df.iterrows()` over the
    holdout slice, filtered to should_trade=True. We replicate that
    construction-order knowledge by accepting the original holdout df
    and the decision_fn at call time via closure.

    The returned function takes (values, n_resamples, ci, rng_seed) and
    returns (mean, ci_lower, ci_upper). The trick: it computes a row->
    cluster lookup from the holdout df at call time. The `values` array
    length must match the eligible holdout rows.
    """
    # This function is called by the gate AFTER it constructs the
    # eligible-realized-pnl array. We can't easily access the original
    # rows from inside the bootstrap call. Instead, the patched function
    # takes an extra "cluster_ids" attribute via closure, set just
    # before each gate.evaluate call.
    state: dict[str, Any] = {"cluster_ids": None}

    def patched_bootstrap_mean_ci(
        values: Any, *, n_resamples: int, ci: float, rng_seed: int,
    ) -> tuple[float, float, float]:
        arr = np.asarray(values, dtype=float)
        arr = arr[~np.isnan(arr)]
        n = arr.size
        if n == 0:
            raise ValueError("patched_bootstrap_mean_ci: empty input")
        # If the caller hasn't provided cluster ids (e.g. degenerate
        # path), fall back to row-level bootstrap.
        cluster_ids = state.get("cluster_ids")
        if cluster_ids is None or len(cluster_ids) != n:
            return _row_bootstrap(arr, n_resamples=n_resamples, ci=ci,
                                  rng_seed=rng_seed)
        rng = np.random.default_rng(rng_seed)
        unique_clusters = np.unique(np.asarray(cluster_ids))
        n_clusters = len(unique_clusters)
        if n_clusters < 3:
            return _row_bootstrap(arr, n_resamples=n_resamples, ci=ci,
                                  rng_seed=rng_seed)
        # Pre-bake cluster -> indices.
        cluster_arr = np.asarray(cluster_ids)
        cluster_to_idx = {c: np.flatnonzero(cluster_arr == c) for c in unique_clusters}
        means: list[float] = []
        for _ in range(n_resamples):
            sampled = rng.choice(unique_clusters, size=n_clusters, replace=True)
            idx = np.concatenate([cluster_to_idx[c] for c in sampled])
            if idx.size == 0:
                continue
            means.append(float(arr[idx].mean()))
        if len(means) < 100:
            return float(arr.mean()), float("nan"), float("nan")
        means_arr = np.asarray(means)
        alpha = (1.0 - ci) / 2.0
        lo = float(np.quantile(means_arr, alpha))
        hi = float(np.quantile(means_arr, 1.0 - alpha))
        return float(arr.mean()), lo, hi

    return patched_bootstrap_mean_ci, state


def _cluster_ids_for_eligible_holdout(
    test_df: pd.DataFrame, decision_fn: Any,
    cluster_col: str = "game_date_parsed",
) -> np.ndarray:
    """Replicate the gate's iteration order and produce per-row cluster
    ids for the rows that pass `should_trade`. This must match exactly
    what `_evaluate_rule_on_df` produces inside gate.py.

    Note: `_evaluate_rule_on_df` iterates `df.iterrows()` in dataset
    order. For the holdout we call _holdout_split first, so the
    `test_df` here is already sorted by close_time ASC.
    """
    ids: list = []
    for _, row in test_df.iterrows():
        row_dict = row.to_dict()
        should_trade, _ = decision_fn(row_dict)
        if not should_trade:
            continue
        ids.append(row_dict[cluster_col])
    return np.asarray(pd.to_datetime(ids).date) if len(ids) > 0 else np.asarray([], dtype=object)


def _holdout_split(df: pd.DataFrame, holdout_frac: float = HOLDOUT_FRAC) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Same as gate._holdout_split but reusable here."""
    df_sorted = df.sort_values("close_time").reset_index(drop=True)
    split_idx = int(len(df_sorted) * (1.0 - holdout_frac))
    return df_sorted.iloc[:split_idx], df_sorted.iloc[split_idx:]


def _kfold_splits(df: pd.DataFrame, n_folds: int = N_FOLDS):
    """Same as gate._kfold_splits but reusable here."""
    df_sorted = df.sort_values("close_time").reset_index(drop=True)
    n = len(df_sorted)
    fold_size = n // n_folds
    if fold_size < 5:
        return
    for fold in range(1, n_folds):
        train_end = fold * fold_size
        test_end = (fold + 1) * fold_size
        yield df_sorted.iloc[:train_end], df_sorted.iloc[train_end:test_end]


def evaluate_with_cluster_bootstrap(
    df: pd.DataFrame, decision_fn: Any, *,
    trainer: Any | None = None, note: str = "",
) -> GateResult:
    """Drop-in replacement for `gate.evaluate` that uses cluster-bootstrap
    by `game_date_parsed`. We replicate the gate logic locally so we
    can control the cluster-ids passed to the bootstrap helper.

    Mirrors `kalshi_bot_v2.gate.evaluate` step-for-step.
    """
    from kalshi_bot.analysis.metrics import kalshi_maker_fee_per_contract  # noqa: F401

    res = GateResult(note=note)

    train, test = _holdout_split(df)
    res.holdout_train_n = len(train)
    res.holdout_test_n = len(test)

    # Replicate gate._evaluate_rule_on_df with cluster-id collection.
    realized_v2_list: list[float] = []
    cluster_ids_v2: list = []
    for _, row in test.iterrows():
        row_dict = row.to_dict()
        should_trade, _ = decision_fn(row_dict)
        if not should_trade:
            continue
        price = float(row_dict["favorite_price"])
        outcome = int(row_dict["outcome"])
        realized_v2_list.append(realized_pnl_per_contract(price, outcome))
        cluster_ids_v2.append(row_dict.get("game_date_parsed"))
    realized_v2 = np.asarray(realized_v2_list, dtype=float)
    res.holdout_eligible_n = int(realized_v2.size)
    if realized_v2.size > 0:
        res.holdout_mean = float(realized_v2.mean())
        res.holdout_median = float(np.median(realized_v2))
        res.holdout_sd = float(realized_v2.std())
        res.holdout_hit_rate = float((realized_v2 > 0).mean())
        # Cluster-bootstrap CI.
        cluster_dates = pd.to_datetime(pd.Series(cluster_ids_v2)).dt.date.to_numpy()
        unique = np.unique(cluster_dates)
        if len(unique) >= 3:
            rng = np.random.default_rng(BOOTSTRAP_SEED)
            cluster_to_idx = {c: np.flatnonzero(cluster_dates == c) for c in unique}
            means = []
            for _ in range(BOOTSTRAP_N_RESAMPLES):
                sampled = rng.choice(unique, size=len(unique), replace=True)
                idx = np.concatenate([cluster_to_idx[c] for c in sampled])
                if idx.size == 0:
                    continue
                means.append(float(realized_v2[idx].mean()))
            if len(means) >= 100:
                alpha = (1.0 - BOOTSTRAP_CI) / 2.0
                res.holdout_ci_lower = float(np.quantile(means, alpha))
                res.holdout_ci_upper = float(np.quantile(means, 1.0 - alpha))

    # v1 baseline on the same holdout for C6 comparison.
    realized_v1_list: list[float] = []
    for _, row in test.iterrows():
        row_dict = row.to_dict()
        should_trade, _ = v1_decision_fn(row_dict)
        if not should_trade:
            continue
        price = float(row_dict["favorite_price"])
        outcome = int(row_dict["outcome"])
        realized_v1_list.append(realized_pnl_per_contract(price, outcome))
    realized_v1 = np.asarray(realized_v1_list, dtype=float)
    if realized_v1.size > 0:
        res.v1_holdout_mean = float(realized_v1.mean())

    # 5-fold walk-forward with per-fold retraining.
    all_realized: list[np.ndarray] = []
    all_cluster_ids: list = []
    fold_means: list[float] = []
    for fold_train, fold_test in _kfold_splits(df):
        fold_decision_fn = (
            trainer(fold_train) if trainer is not None else decision_fn
        )
        fold_realized: list[float] = []
        fold_clusters: list = []
        for _, row in fold_test.iterrows():
            row_dict = row.to_dict()
            should_trade, _ = fold_decision_fn(row_dict)
            if not should_trade:
                continue
            price = float(row_dict["favorite_price"])
            outcome = int(row_dict["outcome"])
            fold_realized.append(realized_pnl_per_contract(price, outcome))
            fold_clusters.append(row_dict.get("game_date_parsed"))
        fold_arr = np.asarray(fold_realized, dtype=float)
        all_realized.append(fold_arr)
        all_cluster_ids.extend(fold_clusters)
        fold_means.append(
            float(fold_arr.mean()) if fold_arr.size > 0 else float("nan"),
        )
    pooled = np.concatenate(all_realized) if all_realized else np.array([])
    res.folds_eligible_total = int(pooled.size)
    res.fold_means = fold_means
    if pooled.size > 0:
        res.folds_pooled_mean = float(pooled.mean())
        res.folds_pooled_median = float(np.median(pooled))
        # Cluster-bootstrap on the pooled folds.
        pooled_dates = pd.to_datetime(pd.Series(all_cluster_ids)).dt.date.to_numpy()
        unique = np.unique(pooled_dates)
        if len(unique) >= 3:
            rng = np.random.default_rng(BOOTSTRAP_SEED)
            cluster_to_idx = {c: np.flatnonzero(pooled_dates == c) for c in unique}
            means = []
            for _ in range(BOOTSTRAP_N_RESAMPLES):
                sampled = rng.choice(unique, size=len(unique), replace=True)
                idx = np.concatenate([cluster_to_idx[c] for c in sampled])
                if idx.size == 0:
                    continue
                means.append(float(pooled[idx].mean()))
            if len(means) >= 100:
                alpha = (1.0 - BOOTSTRAP_CI) / 2.0
                res.folds_pooled_ci_lower = float(np.quantile(means, alpha))
                res.folds_pooled_ci_upper = float(np.quantile(means, 1.0 - alpha))

    # Criteria evaluation (same as gate.py).
    PASS_C2 = 0.0
    PASS_C3 = 0.55
    PASS_C4 = 15
    PASS_C5 = 0.0
    PASS_C6 = 0.02
    v2_minus_v1 = (
        res.holdout_mean - res.v1_holdout_mean
        if not (np.isnan(res.holdout_mean) or np.isnan(res.v1_holdout_mean))
        else float("nan")
    )
    res.criteria = {
        "C1_holdout_mean_>_0": (
            not np.isnan(res.holdout_mean) and res.holdout_mean > 0.0
        ),
        "C2_holdout_bootstrap_ci_lower_>_0": (
            not np.isnan(res.holdout_ci_lower)
            and res.holdout_ci_lower > PASS_C2
        ),
        "C3_holdout_hit_rate_>_55pct": (
            not np.isnan(res.holdout_hit_rate)
            and res.holdout_hit_rate > PASS_C3
        ),
        f"C4_holdout_n_>=_{PASS_C4}": res.holdout_eligible_n >= PASS_C4,
        "C5_folds_pooled_mean_>_0": (
            not np.isnan(res.folds_pooled_mean)
            and res.folds_pooled_mean > PASS_C5
        ),
        f"C6_v2_beats_v1_by_>={int(PASS_C6*100)}pp": (
            not np.isnan(v2_minus_v1) and v2_minus_v1 >= PASS_C6
        ),
    }
    res.passes = all(res.criteria.values())
    log.info("cluster_gate_done", passes=res.passes, note=note,
             holdout_n=res.holdout_eligible_n,
             holdout_mean=res.holdout_mean,
             holdout_ci_lower=res.holdout_ci_lower,
             v1_baseline_mean=res.v1_holdout_mean,
             v2_minus_v1=v2_minus_v1)
    return res


def _serialize_gate_result(result: GateResult) -> dict[str, Any]:
    raw = dataclasses.asdict(result)
    out: dict[str, Any] = {}
    for k, v in raw.items():
        if isinstance(v, float):
            out[k] = None if np.isnan(v) else float(v)
        elif isinstance(v, list):
            out[k] = [
                None if (isinstance(x, float) and np.isnan(x))
                else (float(x) if isinstance(x, float) else x)
                for x in v
            ]
        elif isinstance(v, dict):
            out[k] = {kk: bool(vv) if isinstance(vv, np.bool_) else vv for kk, vv in v.items()}
        else:
            out[k] = v
    return out


def _brier(probs: np.ndarray, outcomes: np.ndarray) -> float:
    if probs.size == 0:
        return float("nan")
    return float(np.mean((probs - outcomes) ** 2))


def _ece(probs: np.ndarray, outcomes: np.ndarray, bin_edges: list[float]) -> dict[str, Any]:
    if probs.size == 0:
        return {"ece": float("nan"), "bins": []}
    n_total = probs.size
    bins_out = []
    ece_val = 0.0
    for i in range(len(bin_edges) - 1):
        lo = bin_edges[i]
        hi = bin_edges[i + 1]
        if i == len(bin_edges) - 2:
            mask = (probs >= lo) & (probs <= hi)
        else:
            mask = (probs >= lo) & (probs < hi)
        n = int(mask.sum())
        if n == 0:
            bins_out.append({"lo": lo, "hi": hi, "n": 0, "mean_pred": None,
                             "mean_actual": None, "abs_gap": None})
            continue
        mean_pred = float(probs[mask].mean())
        mean_actual = float(outcomes[mask].mean())
        gap = abs(mean_pred - mean_actual)
        ece_val += (n / n_total) * gap
        bins_out.append({
            "lo": lo, "hi": hi, "n": n,
            "mean_pred": mean_pred, "mean_actual": mean_actual,
            "abs_gap": gap,
        })
    return {"ece": ece_val, "bins": bins_out}


def _calibration_for_features(df: pd.DataFrame, features: list[str]) -> dict[str, Any]:
    train, test = _holdout_split(df)
    model, scaler, _ = fit_model(train, features)
    if model is None or scaler is None:
        return {"features": features, "trainable": False,
                "note": "degenerate train"}
    # Score holdout.
    probs_list: list[float] = []
    out_list: list[int] = []
    price_list: list[float] = []
    series_list: list[str] = []
    test = test.dropna(subset=features + ["favorite_price", "outcome"])
    if len(test) == 0:
        return {"features": features, "trainable": True,
                "holdout_n_complete": 0,
                "note": "no complete holdout rows"}
    x_test = test[features].to_numpy(dtype=float)
    x_test_sc = scaler.transform(x_test)
    probs = model.predict_proba(x_test_sc)[:, 1]
    out_arr = test["outcome"].to_numpy(dtype=int)
    price_arr = test["favorite_price"].to_numpy(dtype=float)
    series_arr = test["series"].to_numpy()
    model_b = _brier(probs, out_arr)
    price_b = _brier(price_arr, out_arr)
    bss = float("nan") if price_b in (0.0, float("nan")) else float(1.0 - model_b / price_b)
    ece_out = _ece(probs, out_arr, ECE_PRICE_BIN_EDGES)
    # Per-prop-type.
    per_series = {}
    for s in np.unique(series_arr):
        mask = series_arr == s
        if mask.sum() < 5:
            continue
        per_series[str(s)] = {
            "n": int(mask.sum()),
            "model_brier": _brier(probs[mask], out_arr[mask]),
            "price_brier": _brier(price_arr[mask], out_arr[mask]),
            "bss_vs_price": (None if _brier(price_arr[mask], out_arr[mask]) == 0
                             else float(1.0 - _brier(probs[mask], out_arr[mask])
                                         / _brier(price_arr[mask], out_arr[mask]))),
        }
    return {
        "features": features,
        "trainable": True,
        "holdout_n_complete": int(len(test)),
        "model_brier": float(model_b),
        "price_brier": float(price_b),
        "bss_vs_price": bss,
        "ece": ece_out["ece"],
        "ece_bins": ece_out["bins"],
        "per_series_brier": per_series,
    }


def _s1_drop_top_players(df: pd.DataFrame, decision_fn: Any) -> dict[str, Any]:
    """S1: drop the top-N most-frequent players from the holdout
    and verify the mean stays positive. We test N in {1, 5, 10}.
    """
    _, test = _holdout_split(df)
    top = test["player"].value_counts()
    results = []
    for n_drop in (1, 5, 10):
        if len(top) < n_drop:
            results.append({
                "n_drop": n_drop, "skipped": True,
                "note": f"fewer than {n_drop} distinct players in holdout",
            })
            continue
        top_players = top.head(n_drop).index.tolist()
        remaining = test[~test["player"].isin(top_players)]
        realized = []
        for _, row in remaining.iterrows():
            row_dict = row.to_dict()
            should_trade, _ = decision_fn(row_dict)
            if not should_trade:
                continue
            price = float(row_dict["favorite_price"])
            outcome = int(row_dict["outcome"])
            realized.append(realized_pnl_per_contract(price, outcome))
        arr = np.asarray(realized, dtype=float)
        results.append({
            "n_drop": n_drop,
            "top_players": top_players,
            "remaining_eligible_n": int(arr.size),
            "remaining_mean": float(arr.mean()) if arr.size > 0 else None,
            "passes": bool(arr.size > 0 and arr.mean() > 0),
        })
    return {"per_n_drop": results}


def _s2_cv_oos(df: pd.DataFrame) -> dict[str, Any]:
    df_sorted = df.sort_values("close_time").reset_index(drop=True)
    n = len(df_sorted)
    fold_size = n // N_FOLDS
    if fold_size < 5:
        return {"folds": [], "all_folds_clean": False, "note": "fold_size<5"}
    out = []
    all_clean = True
    for fold in range(1, N_FOLDS):
        train_end = fold * fold_size
        test_end = (fold + 1) * fold_size
        ft = df_sorted.iloc[:train_end]
        fe = df_sorted.iloc[train_end:test_end]
        train_cutoff = ft["close_time"].max()
        test_min = fe["close_time"].min()
        test_max = fe["close_time"].max()
        clean = bool(test_min > train_cutoff)
        if not clean:
            all_clean = False
        out.append({
            "fold": fold,
            "train_n": int(len(ft)),
            "test_n": int(len(fe)),
            "train_cutoff": str(train_cutoff),
            "test_min": str(test_min),
            "test_max": str(test_max),
            "test_strictly_after_train_cutoff": clean,
        })
    return {"folds": out, "all_folds_clean": all_clean}


def _s3_per_prop_type(df: pd.DataFrame, decision_fn: Any) -> dict[str, Any]:
    """S3: contribution per prop type on the holdout."""
    _, test = _holdout_split(df)
    per_series: dict[str, dict[str, Any]] = {}
    for s, grp in test.groupby("series"):
        realized = []
        for _, row in grp.iterrows():
            row_dict = row.to_dict()
            should_trade, _ = decision_fn(row_dict)
            if not should_trade:
                continue
            price = float(row_dict["favorite_price"])
            outcome = int(row_dict["outcome"])
            realized.append(realized_pnl_per_contract(price, outcome))
        arr = np.asarray(realized, dtype=float)
        per_series[str(s)] = {
            "holdout_n_eligible": int(arr.size),
            "mean": float(arr.mean()) if arr.size > 0 else None,
            "hit_rate": float((arr > 0).mean()) if arr.size > 0 else None,
        }
    return per_series


def _sportsbook_spread_realism(df: pd.DataFrame, decision_fn: Any,
                               *, spread_dollars: float = SPORTSBOOK_SPREAD_DOLLARS,
                               ) -> dict[str, Any]:
    """Subtract a 5c effective spread from every winning trade's edge
    and re-check C1 (mean still > 0?).
    """
    _, test = _holdout_split(df)
    realized = []
    for _, row in test.iterrows():
        row_dict = row.to_dict()
        should_trade, _ = decision_fn(row_dict)
        if not should_trade:
            continue
        price = float(row_dict["favorite_price"])
        outcome = int(row_dict["outcome"])
        pnl = realized_pnl_per_contract(price, outcome)
        # Subtract spread proxy.
        pnl_after_spread = pnl - spread_dollars
        realized.append(pnl_after_spread)
    arr = np.asarray(realized, dtype=float)
    return {
        "spread_subtracted_per_trade_dollars": spread_dollars,
        "holdout_eligible_n": int(arr.size),
        "post_spread_mean": float(arr.mean()) if arr.size > 0 else None,
        "post_spread_hit_rate": float((arr > 0).mean()) if arr.size > 0 else None,
        "c1_post_spread_passes": bool(arr.size > 0 and arr.mean() > 0),
    }


def _load_orthogonality_survivors() -> list[str]:
    """Read the orthogonality report and return retained features.

    If the report is absent, returns an empty list (G3 then collapses
    to "favorite_price only" which is identical to G2 and gives a null
    finding).
    """
    if not ORTHOGONALITY_REPORT_PATH.exists():
        log.warning("orthogonality_report_missing",
                    path=str(ORTHOGONALITY_REPORT_PATH))
        return []
    with ORTHOGONALITY_REPORT_PATH.open("r") as f:
        report = json.load(f)
    return list(report.get("retained_features", []))


def main() -> None:
    log.info("statcast_gate_runner_start", dataset_path=str(DATASET_PATH))
    df = pd.read_parquet(DATASET_PATH)
    log.info("dataset_loaded", n_rows=len(df))

    # Load orthogonality survivors.
    survivors = _load_orthogonality_survivors()
    log.info("orthogonality_survivors", n=len(survivors), features=survivors)

    # G1: v1-style flat-prior baseline.
    log.info("g1_running")
    g1_result = evaluate_with_cluster_bootstrap(
        df, v1_decision_fn, trainer=None,
        note="G1 v1-style flat-prior (always-trade)",
    )

    # G2: baseline LogReg (favorite_price only).
    log.info("g2_running")
    g2_features = ["favorite_price"]
    train_70, _ = _holdout_split(df)
    g2_model, g2_scaler, _ = fit_model(train_70, g2_features)
    if g2_model is None:
        def never(_row: dict) -> tuple[bool, float]:
            return False, 0.0
        g2_decision_fn = never
    else:
        g2_decision_fn = make_anchored_decision_fn(g2_model, g2_scaler, g2_features)
    g2_result = evaluate_with_cluster_bootstrap(
        df, g2_decision_fn, trainer=make_trainer(g2_features),
        note="G2 LogReg(favorite_price), prob>price+0.02",
    )
    g2_cal = _calibration_for_features(df, g2_features)

    # G3: tuned LogReg (price + survivors).
    if len(survivors) == 0:
        log.warning("g3_skipped_no_survivors")
        g3_features = g2_features  # collapses to G2
        g3_result = g2_result
        g3_decision_fn = g2_decision_fn
        g3_cal = g2_cal
        g3_note = "G3 SKIPPED (0 orthogonality survivors)"
    else:
        g3_features = ["favorite_price"] + survivors
        g3_model, g3_scaler, _ = fit_model(train_70, g3_features)
        if g3_model is None:
            def never2(_row: dict) -> tuple[bool, float]:
                return False, 0.0
            g3_decision_fn = never2
        else:
            g3_decision_fn = make_anchored_decision_fn(g3_model, g3_scaler, g3_features)
        g3_result = evaluate_with_cluster_bootstrap(
            df, g3_decision_fn, trainer=make_trainer(g3_features),
            note=f"G3 LogReg(price + {len(survivors)} survivors), prob>price+0.02",
        )
        g3_cal = _calibration_for_features(df, g3_features)
        g3_note = "G3 RAN"

    # Sanity checks.
    log.info("sanity_checks")
    s1_g2 = _s1_drop_top_players(df, g2_decision_fn)
    s1_g3 = _s1_drop_top_players(df, g3_decision_fn)
    s1_v1 = _s1_drop_top_players(df, v1_decision_fn)
    s2 = _s2_cv_oos(df)
    s3_g2 = _s3_per_prop_type(df, g2_decision_fn)
    s3_g3 = _s3_per_prop_type(df, g3_decision_fn)
    s3_v1 = _s3_per_prop_type(df, v1_decision_fn)

    # Sportsbook-spread realism.
    spread_g2 = _sportsbook_spread_realism(df, g2_decision_fn)
    spread_g3 = _sportsbook_spread_realism(df, g3_decision_fn)
    spread_v1 = _sportsbook_spread_realism(df, v1_decision_fn)

    payload = {
        "dataset_path": str(DATASET_PATH),
        "dataset_n": int(len(df)),
        "holdout_frac": HOLDOUT_FRAC,
        "n_folds": N_FOLDS,
        "trade_rule": f"prob > price + {EDGE_THRESHOLD}",
        "logreg_C": LOGREG_C,
        "logreg_max_iter": LOGREG_MAX_ITER,
        "logreg_random_state": LOGREG_RANDOM_STATE,
        "bootstrap_n_resamples": BOOTSTRAP_N_RESAMPLES,
        "bootstrap_ci": BOOTSTRAP_CI,
        "bootstrap_seed": BOOTSTRAP_SEED,
        "bootstrap_mode": "cluster_by_game_date",
        "orthogonality_survivors": survivors,
        "g1_v1_baseline": _serialize_gate_result(g1_result),
        "g2_logreg_price_only": _serialize_gate_result(g2_result),
        "g3_logreg_price_plus_survivors": _serialize_gate_result(g3_result),
        "g3_note": g3_note,
        "g2_calibration": g2_cal,
        "g3_calibration": g3_cal,
        "s1_drop_top_players": {
            "G2": s1_g2, "G3": s1_g3, "v1": s1_v1,
        },
        "s2_cv_oos_verification": s2,
        "s3_per_prop_type": {
            "G2": s3_g2, "G3": s3_g3, "v1": s3_v1,
        },
        "sportsbook_spread_realism": {
            "G2": spread_g2, "G3": spread_g3, "v1": spread_v1,
        },
    }

    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(payload, indent=2, default=str))
    log.info("statcast_gate_results_written", path=str(OUTPUT_JSON))

    print(f"v5-b gate complete. Results: {OUTPUT_JSON}")
    print()
    print("=" * 70)
    print("Gate summary")
    print("=" * 70)
    for key, r in [("G1 v1", payload["g1_v1_baseline"]),
                   ("G2 price", payload["g2_logreg_price_only"]),
                   ("G3 price+survivors", payload["g3_logreg_price_plus_survivors"])]:
        print(f"\n{key}:")
        print(f"  holdout_n:        {r['holdout_eligible_n']}")
        print(f"  holdout_mean:     {r['holdout_mean']}")
        print(f"  holdout_ci_lower: {r['holdout_ci_lower']}")
        print(f"  hit_rate:         {r['holdout_hit_rate']}")
        print(f"  folds_pooled:     {r['folds_pooled_mean']}")
        print(f"  v1_baseline:      {r['v1_holdout_mean']}")
        print(f"  passes:           {r['passes']}")
        print(f"  criteria:         {r['criteria']}")
    print()
    print(f"survivors: {survivors}")


if __name__ == "__main__":
    main()
