"""Critic experiment: retrain the v2 model WITHOUT favorite_price and see if
any signal survives, or whether the model is essentially memorizing the market
price.

The headline +6.74pp v2-over-v1 result is computed against a v1 baseline that
trades every Strategy-B-eligible row at price >= 0.70. If we strip favorite_price
out of the feature set entirely, two things can happen:

1. Model still produces a useful ranking -> the team-strength + microstructure
   features add real signal beyond the market price.
2. Model collapses (no decision rule selects, or selected trades underperform)
   -> the model was effectively using favorite_price as the dominant ranker
   and the team-stat features were rounding noise.

We do NOT modify model.py production code. We monkey-patch the feature column
list locally to remove favorite_price, retrain on the same chronological split
the gate uses, and report holdout outcomes under the same hybrid decision rule.

Output: data/v2/critic_drop_price_result.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

# Defer model import until after we monkey-patch the feature list
from kalshi_bot_v2 import model as _model  # noqa: E402
from kalshi_bot_v2.gate import (  # noqa: E402
    HOLDOUT_FRAC,
    evaluate,
    v1_decision_fn,
)

DATA_DIR = REPO_ROOT / "data" / "v2"
DATASET_PATH = DATA_DIR / "joined_mlb_dataset.parquet"
OUT_PATH = DATA_DIR / "critic_drop_price_result.json"


def main() -> int:
    if not DATASET_PATH.exists():
        print(f"ERROR: dataset missing at {DATASET_PATH}", file=sys.stderr)
        return 1
    df = pd.read_parquet(DATASET_PATH)
    print(f"Loaded {len(df)} rows. Eligible: {int(df['is_strategy_b_eligible'].sum())}")

    # Strip favorite_price from the model's feature schema in this process only.
    original_features = list(_model.FEATURE_COLUMNS)
    print(f"Original FEATURE_COLUMNS includes favorite_price? {'favorite_price' in original_features}")
    _model.FEATURE_COLUMNS = [c for c in original_features if c != "favorite_price"]
    _model.ALL_MODEL_FEATURES = _model.FEATURE_COLUMNS + _model.INDICATOR_COLUMNS
    print(f"Patched FEATURE_COLUMNS now has {len(_model.FEATURE_COLUMNS)} features")
    print(f"Patched ALL_MODEL_FEATURES has {len(_model.ALL_MODEL_FEATURES)} cols")
    assert "favorite_price" not in _model.FEATURE_COLUMNS

    # Same chronological split as gate
    df_sorted = df.sort_values("close_time").reset_index(drop=True)
    split_idx = int(len(df_sorted) * (1.0 - HOLDOUT_FRAC))
    train_df = df_sorted.iloc[:split_idx].copy()
    eligible_df = df[df["is_strategy_b_eligible"]].copy()
    print(f"Train rows: {len(train_df)} | Eligible total: {len(eligible_df)}")

    # Train with same config as production (calibrate=False, no walk-forward scan)
    artifact = _model.train_with_threshold_search(
        train_df, val_frac=0.20, calibrate=False,
        use_walk_forward_for_scan=False,
    )
    print(f"  best edge: {artifact.edge_threshold:+.3f}")
    print(f"  best abs threshold: {artifact.threshold:.3f}")

    # Score the hybrid rule on the full eligible set, then run the gate
    decision_fn = _model.make_decision_fn(artifact, df, mode="hybrid")
    res_v2_nopx = evaluate(eligible_df, decision_fn, note="lgb_v2_hybrid_NO_PRICE")
    res_v1 = evaluate(eligible_df, v1_decision_fn, note="v1_baseline")

    print()
    print("=" * 60)
    print("V2 HYBRID WITHOUT favorite_price")
    print("=" * 60)
    print(f"  Holdout eligible n:       {res_v2_nopx.holdout_eligible_n}")
    print(f"  Holdout mean P&L:         {res_v2_nopx.holdout_mean:+.4f}")
    print(f"  Holdout hit rate:         {res_v2_nopx.holdout_hit_rate:.4f}")
    print(f"  Holdout 95% CI:           [{res_v2_nopx.holdout_ci_lower:+.4f}, {res_v2_nopx.holdout_ci_upper:+.4f}]")
    print(f"  Folds pooled mean:        {res_v2_nopx.folds_pooled_mean:+.4f}")
    print(f"  Folds pooled CI:          [{res_v2_nopx.folds_pooled_ci_lower:+.4f}, {res_v2_nopx.folds_pooled_ci_upper:+.4f}]")
    print(f"  Per-fold means:           {[f'{m:+.4f}' for m in res_v2_nopx.fold_means]}")
    print(f"  v1 holdout mean (C6):     {res_v2_nopx.v1_holdout_mean:+.4f}")
    print("  Criteria:")
    for k, v in res_v2_nopx.criteria.items():
        status = "PASS" if v else "FAIL"
        print(f"    {k}: {status}")
    print(f"  v2_no_price minus v1 holdout: {res_v2_nopx.holdout_mean - res_v2_nopx.v1_holdout_mean:+.4f}")

    # Compare to original v2 (with price) loaded from gate_v2_result.json
    with (DATA_DIR / "gate_v2_result.json").open("r", encoding="utf-8") as f:
        orig = json.load(f)
    orig_v2 = orig["v2_model_hybrid"]
    print()
    print("Original v2 (WITH favorite_price) holdout mean:", orig_v2["holdout_mean"])
    print("This experiment (NO favorite_price) holdout mean:", res_v2_nopx.holdout_mean)
    print("Delta (no_price - with_price):", res_v2_nopx.holdout_mean - orig_v2["holdout_mean"])

    out = {
        "experiment": "drop_favorite_price_from_features",
        "rationale": "test whether model adds signal beyond market price",
        "feature_count_used": len(_model.ALL_MODEL_FEATURES),
        "holdout_eligible_n": res_v2_nopx.holdout_eligible_n,
        "holdout_mean": res_v2_nopx.holdout_mean,
        "holdout_hit_rate": res_v2_nopx.holdout_hit_rate,
        "holdout_ci_lower": res_v2_nopx.holdout_ci_lower,
        "holdout_ci_upper": res_v2_nopx.holdout_ci_upper,
        "folds_pooled_mean": res_v2_nopx.folds_pooled_mean,
        "folds_pooled_ci_lower": res_v2_nopx.folds_pooled_ci_lower,
        "folds_pooled_ci_upper": res_v2_nopx.folds_pooled_ci_upper,
        "fold_means": res_v2_nopx.fold_means,
        "v1_holdout_mean": res_v2_nopx.v1_holdout_mean,
        "v2_minus_v1": res_v2_nopx.holdout_mean - res_v2_nopx.v1_holdout_mean
        if not (np.isnan(res_v2_nopx.holdout_mean) or np.isnan(res_v2_nopx.v1_holdout_mean))
        else None,
        "criteria": res_v2_nopx.criteria,
        "original_v2_with_price_holdout_mean": orig_v2["holdout_mean"],
        "delta_no_price_vs_with_price": res_v2_nopx.holdout_mean - orig_v2["holdout_mean"]
        if not np.isnan(res_v2_nopx.holdout_mean)
        else None,
        "best_edge_threshold": artifact.edge_threshold,
        "best_abs_threshold": artifact.threshold,
        "feature_names_used": _model.ALL_MODEL_FEATURES,
    }
    with OUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"\nSaved: {OUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
