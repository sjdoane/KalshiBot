"""V3-B2: Run the locked 6-criteria gate on the v3 dataset.

Three gate evaluations:
    G1: v1-style flat-prior baseline (always-trade).
    G2: price-only LogReg with should_trade = predicted_prob >= 0.70.
    G3: price + nfl_games_played_pre_t35d LogReg, same threshold.

For G2 and G3 we additionally compute calibration metrics (Brier, BSS
vs raw favorite_price, ECE at 5 price buckets), the S1/S2/S3 sanity
checks from the master plan, and a per-league sub-analysis.

Outputs:
    data/v3/gate_results.json  - full GateResult + calibration + S1/S2/S3
                                 + per-league diagnostics for all 3 runs.

This script does NOT mutate v1, v2, or any live-trading code path.
Invoke with: `uv run python -m scripts.v3.run_v3_gate`.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import structlog

from kalshi_bot_v2.gate import (
    BOOTSTRAP_CI,
    BOOTSTRAP_N_RESAMPLES,
    BOOTSTRAP_SEED,
    HOLDOUT_FRAC,
    N_FOLDS,
    GateResult,
    evaluate,
    realized_pnl_per_contract,
    v1_decision_fn,
)
from kalshi_bot_v3.model import (
    TRADE_PROB_THRESHOLD,
    fit_model,
    make_anchored_decision_fn,
    make_trainer,
    predict_proba_row,
)

log = structlog.get_logger(__name__)


DATASET_PATH = Path("data/v3/joined_v3_dataset.parquet")
OUTPUT_JSON = Path("data/v3/gate_results.json")
RESEARCH_DOC = Path("research/v3/06-model-results.md")


# Calibration bin edges for ECE at 5 price buckets, spanning v1's eligible
# YES band [0.70, 0.95]. Each bucket spans 5 cents. The boundaries are
# closed on the left, open on the right, except the last is closed on
# both ends.
ECE_PRICE_BIN_EDGES = [0.70, 0.75, 0.80, 0.85, 0.90, 0.95]

# Domain-match buckets for S3.
S3_LIFETIME_BIN_EDGES = [30, 60, 90, 120, 150, 180]  # closed left, open right, last closed both
S3_PRICE_BIN_EDGES = [0.70, 0.75, 0.80, 0.85, 0.90, 0.95]


def _holdout_split(df: pd.DataFrame, holdout_frac: float = HOLDOUT_FRAC) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Same split logic as gate._holdout_split, replicated locally so we
    can compute holdout-only diagnostics without re-running the gate.
    """
    df_sorted = df.sort_values("close_time").reset_index(drop=True)
    split_idx = int(len(df_sorted) * (1.0 - holdout_frac))
    return df_sorted.iloc[:split_idx], df_sorted.iloc[split_idx:]


def _serialize_gate_result(result: GateResult) -> dict[str, Any]:
    """Convert a GateResult (dataclass with np floats) into JSON-safe dict."""
    raw = dataclasses.asdict(result)
    out: dict[str, Any] = {}
    for k, v in raw.items():
        if isinstance(v, float):
            out[k] = None if np.isnan(v) else float(v)
        elif isinstance(v, list):
            out[k] = [None if (isinstance(x, float) and np.isnan(x)) else float(x) if isinstance(x, float) else x for x in v]
        elif isinstance(v, dict):
            out[k] = {kk: bool(vv) if isinstance(vv, np.bool_) else vv for kk, vv in v.items()}
        else:
            out[k] = v
    return out


def _brier(probs: np.ndarray, outcomes: np.ndarray) -> float:
    """Mean( (prob - outcome)^2 ). Lower is better. Returns NaN if empty."""
    if probs.size == 0:
        return float("nan")
    return float(np.mean((probs - outcomes) ** 2))


def _brier_skill_score(model_probs: np.ndarray, baseline_probs: np.ndarray, outcomes: np.ndarray) -> float:
    """Brier skill = 1 - (model_Brier / baseline_Brier). Positive means
    the model beats the baseline. NaN if baseline_Brier is zero or array
    is empty.
    """
    if outcomes.size == 0:
        return float("nan")
    model_b = _brier(model_probs, outcomes)
    base_b = _brier(baseline_probs, outcomes)
    if base_b == 0.0 or np.isnan(base_b):
        return float("nan")
    return float(1.0 - (model_b / base_b))


def _expected_calibration_error(
    probs: np.ndarray, outcomes: np.ndarray, bin_edges: list[float],
) -> dict[str, Any]:
    """ECE at the provided bin edges. Each bin contributes
    |mean_pred - mean_actual| weighted by bin n / total_n.

    Returns dict with `ece` (scalar), `bins` (list of per-bin diagnostics).
    """
    if probs.size == 0:
        return {"ece": float("nan"), "bins": []}
    bin_edges_arr = np.asarray(bin_edges, dtype=float)
    n_total = probs.size
    bins_out: list[dict[str, Any]] = []
    ece = 0.0
    for i in range(len(bin_edges_arr) - 1):
        lo = bin_edges_arr[i]
        hi = bin_edges_arr[i + 1]
        # Closed left, open right, except last bin is closed-closed.
        if i == len(bin_edges_arr) - 2:
            mask = (probs >= lo) & (probs <= hi)
        else:
            mask = (probs >= lo) & (probs < hi)
        n = int(mask.sum())
        if n == 0:
            mean_pred = float("nan")
            mean_actual = float("nan")
            gap = float("nan")
            weight = 0.0
        else:
            mean_pred = float(probs[mask].mean())
            mean_actual = float(outcomes[mask].mean())
            gap = abs(mean_pred - mean_actual)
            weight = n / n_total
            ece += weight * gap
        bins_out.append({
            "bin_lo": float(lo),
            "bin_hi": float(hi),
            "n": n,
            "mean_pred": None if np.isnan(mean_pred) else mean_pred,
            "mean_actual": None if np.isnan(mean_actual) else mean_actual,
            "abs_gap": None if np.isnan(gap) else gap,
            "weight": weight,
        })
    return {"ece": float(ece), "bins": bins_out}


def _build_holdout_calibration(
    df: pd.DataFrame, features: list[str],
) -> dict[str, Any]:
    """For a given feature set, fit on chronological 70% train, score the
    30% holdout, then compute Brier / Brier skill / ECE.

    Baseline for the Brier skill score is the raw favorite_price taken as
    the predicted probability. ECE uses the model's predicted probability
    bucketed by ECE_PRICE_BIN_EDGES (matching the price band).
    """
    train, test = _holdout_split(df)
    model, scaler, _ = fit_model(train, features)
    if model is None or scaler is None:
        return {
            "features": features,
            "trainable": False,
            "note": "training degenerate (n<5 usable or single-class y)",
            "holdout_n": int(len(test)),
            "holdout_n_feature_complete": 0,
            "model_brier": None,
            "price_brier": None,
            "brier_skill_score": None,
            "ece": None,
            "ece_bins": [],
        }
    # Score holdout
    model_probs_list: list[float] = []
    outcome_list: list[int] = []
    price_list: list[float] = []
    for _, row in test.iterrows():
        row_dict = row.to_dict()
        p = predict_proba_row(model, scaler, features, row_dict)
        if np.isnan(p):
            continue
        model_probs_list.append(p)
        outcome_list.append(int(row_dict["outcome"]))
        price_list.append(float(row_dict["favorite_price"]))
    model_probs = np.asarray(model_probs_list, dtype=float)
    outcomes = np.asarray(outcome_list, dtype=int)
    prices = np.asarray(price_list, dtype=float)
    model_b = _brier(model_probs, outcomes)
    price_b = _brier(prices, outcomes)
    bss = _brier_skill_score(model_probs, prices, outcomes)
    ece_out = _expected_calibration_error(model_probs, outcomes, ECE_PRICE_BIN_EDGES)
    return {
        "features": features,
        "trainable": True,
        "holdout_n": int(len(test)),
        "holdout_n_feature_complete": int(model_probs.size),
        "model_brier": float(model_b) if not np.isnan(model_b) else None,
        "price_brier": float(price_b) if not np.isnan(price_b) else None,
        "brier_skill_score": float(bss) if not np.isnan(bss) else None,
        "ece": ece_out["ece"],
        "ece_bins": ece_out["bins"],
    }


def _s1_drop_top_team(df: pd.DataFrame, decision_fn) -> dict[str, Any]:
    """S1: drop the most-frequent team from the HOLDOUT, recompute mean P&L.

    Per master plan: 'When the top single entity (team, candidate, etc.)
    is dropped from the holdout, the holdout mean must stay > 0.'
    """
    _, test = _holdout_split(df)
    # Find most-frequent team in the HOLDOUT (per master plan wording).
    top_team_counts = test["team"].value_counts()
    if top_team_counts.empty:
        return {
            "top_team": None,
            "top_team_n_in_holdout": 0,
            "remaining_holdout_n_eligible": 0,
            "remaining_holdout_mean": None,
            "passes": False,
            "note": "holdout has no team values",
        }
    top_team = str(top_team_counts.index[0])
    top_team_n = int(top_team_counts.iloc[0])
    test_remaining = test[test["team"] != top_team]
    # Apply decision_fn to remaining holdout
    realized: list[float] = []
    for _, row in test_remaining.iterrows():
        row_dict = row.to_dict()
        should_trade, _prob = decision_fn(row_dict)
        if not should_trade:
            continue
        price = float(row_dict["favorite_price"])
        outcome = int(row_dict["outcome"])
        realized.append(realized_pnl_per_contract(price, outcome))
    realized_arr = np.asarray(realized, dtype=float)
    if realized_arr.size == 0:
        return {
            "top_team": top_team,
            "top_team_n_in_holdout": top_team_n,
            "remaining_holdout_n_eligible": 0,
            "remaining_holdout_mean": None,
            "passes": False,
            "note": "no eligible trades after dropping top team",
        }
    mean_pnl = float(realized_arr.mean())
    return {
        "top_team": top_team,
        "top_team_n_in_holdout": top_team_n,
        "remaining_holdout_n_eligible": int(realized_arr.size),
        "remaining_holdout_mean": mean_pnl,
        "passes": bool(mean_pnl > 0),
        "note": "remaining-holdout mean P&L after dropping top team",
    }


def _s2_cv_oos_verification(df: pd.DataFrame) -> dict[str, Any]:
    """S2: for each fold of the 5-fold CV, log the train-cutoff and the
    test-window time range. Verify every test row is AFTER its fold's
    train cutoff.

    The fold split logic is replicated from `gate._kfold_splits`.
    """
    df_sorted = df.sort_values("close_time").reset_index(drop=True)
    n = len(df_sorted)
    fold_size = n // N_FOLDS
    folds_out: list[dict[str, Any]] = []
    if fold_size < 5:
        return {
            "n_folds_run": 0,
            "folds": [],
            "all_folds_clean": False,
            "note": "fold_size < 5; no folds run",
        }
    all_clean = True
    for fold in range(1, N_FOLDS):
        train_end = fold * fold_size
        test_end = (fold + 1) * fold_size
        fold_train = df_sorted.iloc[:train_end]
        fold_test = df_sorted.iloc[train_end:test_end]
        # Train cutoff = max close_time in fold_train. Verify every
        # fold_test close_time strictly > train cutoff.
        train_cutoff = fold_train["close_time"].max()
        test_min = fold_test["close_time"].min()
        test_max = fold_test["close_time"].max()
        # By chronological-slice construction, test_min should be > train_cutoff.
        # The strict-inequality check is the audit.
        clean = bool(test_min > train_cutoff)
        if not clean:
            all_clean = False
        folds_out.append({
            "fold_idx": fold,
            "train_n": int(len(fold_train)),
            "test_n": int(len(fold_test)),
            "train_cutoff": str(train_cutoff),
            "test_min": str(test_min),
            "test_max": str(test_max),
            "test_strictly_after_train_cutoff": clean,
        })
    return {
        "n_folds_run": len(folds_out),
        "folds": folds_out,
        "all_folds_clean": all_clean,
        "note": (
            "every fold's test slice is strictly chronologically after "
            "the fold's train cutoff"
            if all_clean
            else "AT LEAST ONE fold has overlap (this would indicate a gate bug)"
        ),
    }


def _s3_domain_match(df: pd.DataFrame) -> dict[str, Any]:
    """S3: holdout (series, lifetime_bucket, price_bucket) distribution.

    Per master plan: this is the domain-match check vs v1's actual
    trading universe. We report the v3 holdout distribution so a later
    critic can compare against v1's filled-orders log.
    """
    _, test = _holdout_split(df)
    if test.empty:
        return {"holdout_n": 0, "cells": [], "series_counts": {}}

    # Lifetime bucket (closed-closed for last cell to include 180d markets)
    def lifetime_bucket(ld: float) -> str | None:
        if pd.isna(ld):
            return None
        edges = S3_LIFETIME_BIN_EDGES
        for i in range(len(edges) - 1):
            lo = edges[i]
            hi = edges[i + 1]
            if i == len(edges) - 2:
                if lo <= ld <= hi:
                    return f"[{lo}, {hi}]"
            else:  # noqa: PLR5501
                if lo <= ld < hi:
                    return f"[{lo}, {hi})"
        return None

    def price_bucket(pr: float) -> str | None:
        if pd.isna(pr):
            return None
        edges = S3_PRICE_BIN_EDGES
        for i in range(len(edges) - 1):
            lo = edges[i]
            hi = edges[i + 1]
            if i == len(edges) - 2:
                if lo <= pr <= hi:
                    return f"[{lo:.2f}, {hi:.2f}]"
            else:  # noqa: PLR5501
                if lo <= pr < hi:
                    return f"[{lo:.2f}, {hi:.2f})"
        return None

    rows = []
    for _, r in test.iterrows():
        rows.append({
            "series": r.get("series_ticker", ""),
            "lifetime_bucket": lifetime_bucket(r.get("lifetime_days", float("nan"))),
            "price_bucket": price_bucket(r.get("favorite_price", float("nan"))),
        })
    bucket_df = pd.DataFrame(rows)
    grouped = bucket_df.groupby(
        ["series", "lifetime_bucket", "price_bucket"], dropna=False,
    ).size().reset_index(name="n")
    cells = []
    for _, row in grouped.iterrows():
        cells.append({
            "series": row["series"],
            "lifetime_bucket": row["lifetime_bucket"],
            "price_bucket": row["price_bucket"],
            "n": int(row["n"]),
        })
    series_counts = test["series_ticker"].value_counts().to_dict()
    return {
        "holdout_n": int(len(test)),
        "cells": cells,
        "series_counts": {k: int(v) for k, v in series_counts.items()},
    }


def _per_league_subset(df: pd.DataFrame, league: str) -> pd.DataFrame:
    return df[df["league"] == league].copy()


def _run_g1(df: pd.DataFrame, label: str) -> dict[str, Any]:
    """G1: v1-style flat-prior baseline. Pass v1_decision_fn directly.

    The C6 reference number is v3's holdout mean against v1's holdout
    mean ON THE SAME DATA. When the decision_fn IS v1_decision_fn, v3
    minus v1 is identically zero by construction; we still run the gate
    so the criteria table has a complete G1 row for reference.
    """
    result = evaluate(df, v1_decision_fn, trainer=None, note=label)
    return _serialize_gate_result(result)


def _run_logreg_gate(
    df: pd.DataFrame, features: list[str], label: str,
) -> tuple[dict[str, Any], Any]:
    """Run the gate on a price-based LogReg. Holdout uses an anchored
    model fit on the chronological train portion. CV uses the trainer
    factory so each fold's model is fit on that fold's prefix only.

    Returns (serialized_result_dict, anchored_decision_fn). The
    anchored_decision_fn is reused for S1.
    """
    train, _test = _holdout_split(df)
    model, scaler, _ = fit_model(train, features)
    if model is None or scaler is None:
        # Degenerate train: build a never-trade decision_fn so the gate
        # records zero eligible trades, n=0, mean=NaN, all C1..C6 False.
        def never_trade(row: dict) -> tuple[bool, float]:
            return False, 0.0
        result = evaluate(df, never_trade, trainer=make_trainer(features), note=label)
        return _serialize_gate_result(result), never_trade
    anchored = make_anchored_decision_fn(model, scaler, features)
    result = evaluate(df, anchored, trainer=make_trainer(features), note=label)
    return _serialize_gate_result(result), anchored


def _run_full_analysis(df: pd.DataFrame, label_prefix: str) -> dict[str, Any]:
    """Run G1/G2/G3 + calibration + S1/S2/S3 on a given dataset slice.

    label_prefix is appended to the gate note so multi-slice runs (full,
    NFL-only, MLB-only) are distinguishable in the persisted JSON.
    """
    out: dict[str, Any] = {"n_rows": int(len(df))}

    # G1
    g1_note = f"{label_prefix} | G1 v1-style flat-prior baseline"
    out["G1_v1_baseline"] = _run_g1(df, g1_note)

    # G2
    g2_features = ["favorite_price"]
    g2_note = f"{label_prefix} | G2 LogReg(favorite_price), threshold prob>=0.70"
    g2_result, g2_decision_fn = _run_logreg_gate(df, g2_features, g2_note)
    out["G2_logreg_price"] = g2_result
    # G2 calibration
    out["G2_calibration"] = _build_holdout_calibration(df, g2_features)

    # G3
    g3_features = ["favorite_price", "nfl_games_played_pre_t35d"]
    g3_note = f"{label_prefix} | G3 LogReg(favorite_price + nfl_games_played), threshold prob>=0.70"
    g3_result, g3_decision_fn = _run_logreg_gate(df, g3_features, g3_note)
    out["G3_logreg_price_plus_league"] = g3_result
    # G3 calibration
    out["G3_calibration"] = _build_holdout_calibration(df, g3_features)

    # Sanity checks (run on G2 by default, also on G3 for completeness).
    # S1 is per-decision-fn (since it asks: with THIS rule, what is the
    # remaining-holdout P&L when the top team is dropped?).
    out["S1_G2_drop_top_team"] = _s1_drop_top_team(df, g2_decision_fn)
    out["S1_G3_drop_top_team"] = _s1_drop_top_team(df, g3_decision_fn)
    out["S1_v1_drop_top_team"] = _s1_drop_top_team(df, v1_decision_fn)

    # S2 is per-dataset (it audits the fold splitter, not the model).
    out["S2_cv_oos_verification"] = _s2_cv_oos_verification(df)

    # S3 is per-dataset.
    out["S3_domain_match"] = _s3_domain_match(df)

    return out


def main() -> None:
    log.info("v3_gate_runner_start", dataset_path=str(DATASET_PATH))
    df = pd.read_parquet(DATASET_PATH)
    log.info("dataset_loaded", n_rows=len(df))

    # The locked gate runs on the full n=147 dataset. The decision_fn
    # contract for v3 model: when a feature is NaN on a row, abstain
    # (no trade). G2 features (favorite_price only) have zero NaN, so
    # the full n=147 is trade-eligible. G3 adds nfl_games_played which
    # is also zero NaN. So no rows are dropped for either G2 or G3.
    full_analysis = _run_full_analysis(df, label_prefix="FULL_n147")

    # Per-league diagnostics: NFL-only and MLB-only sub-analysis.
    # These are reported for diagnostic purposes only per the brief.
    nfl_df = _per_league_subset(df, "NFL")
    mlb_df = _per_league_subset(df, "MLB")

    nfl_analysis = _run_full_analysis(nfl_df, label_prefix="NFL_ONLY_n104")
    # MLB-only sub-analysis: 16 rows, only ~5 in chronological 30% holdout.
    # The gate will likely fail C4 (n >= 15) on the MLB-only holdout, but
    # we still run for completeness.
    mlb_analysis = _run_full_analysis(mlb_df, label_prefix="MLB_ONLY_n16")

    payload = {
        "dataset_path": str(DATASET_PATH),
        "dataset_n": int(len(df)),
        "holdout_frac": HOLDOUT_FRAC,
        "n_folds": N_FOLDS,
        "trade_prob_threshold": TRADE_PROB_THRESHOLD,
        "bootstrap_n_resamples": BOOTSTRAP_N_RESAMPLES,
        "bootstrap_ci": BOOTSTRAP_CI,
        "bootstrap_seed": BOOTSTRAP_SEED,
        "full_analysis": full_analysis,
        "nfl_only_analysis": nfl_analysis,
        "mlb_only_analysis": mlb_analysis,
    }

    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_JSON.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)
    log.info("v3_gate_results_written", path=str(OUTPUT_JSON))

    # Friendly stdout summary
    print(f"v3 gate run complete. Results written to {OUTPUT_JSON}")
    print()
    print("=" * 70)
    print("FULL n=147 SUMMARY")
    print("=" * 70)
    for key in ("G1_v1_baseline", "G2_logreg_price", "G3_logreg_price_plus_league"):
        r = full_analysis[key]
        print(f"\n{key}:")
        print(f"  holdout_eligible_n: {r['holdout_eligible_n']}")
        print(f"  holdout_mean:       {r['holdout_mean']}")
        print(f"  holdout_ci_lower:   {r['holdout_ci_lower']}")
        print(f"  holdout_hit_rate:   {r['holdout_hit_rate']}")
        print(f"  folds_pooled_mean:  {r['folds_pooled_mean']}")
        print(f"  v1_holdout_mean:    {r['v1_holdout_mean']}")
        print(f"  passes:             {r['passes']}")
        print(f"  criteria:           {r['criteria']}")
    print()
    print("Calibration (FULL n=147):")
    for key in ("G2_calibration", "G3_calibration"):
        c = full_analysis[key]
        print(f"  {key}: brier={c['model_brier']} bss_vs_price={c['brier_skill_score']} ece={c['ece']}")
    print()
    print("S1 (drop top team from holdout):")
    for key in ("S1_v1_drop_top_team", "S1_G2_drop_top_team", "S1_G3_drop_top_team"):
        s = full_analysis[key]
        print(f"  {key}: top={s['top_team']} n_remaining={s['remaining_holdout_n_eligible']} mean={s['remaining_holdout_mean']} passes={s['passes']}")
    print()
    print(f"S2 (CV OOS verification): all_folds_clean={full_analysis['S2_cv_oos_verification']['all_folds_clean']}")
    print()
    print(f"S3 (domain match): holdout_n={full_analysis['S3_domain_match']['holdout_n']} unique_series={list(full_analysis['S3_domain_match']['series_counts'].keys())}")


if __name__ == "__main__":
    main()
