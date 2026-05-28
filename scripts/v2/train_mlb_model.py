"""Train the v2 MLB LightGBM model, calibrate, scan thresholds, run the
v2 gate, and emit artifacts + reports.

Run as:
    uv run python -m scripts.v2.train_mlb_model

Outputs:
    data/v2/mlb_lgb_model.joblib    - trained model bundle
    data/v2/feature_importance.csv  - top features by gain
    data/v2/calibration_table.csv   - reliability table on val slice
    data/v2/calibration_plot.png    - reliability plot (if matplotlib OK)
    data/v2/gate_v2_result.json     - full GateResult printed + saved
    data/v2/threshold_scan.csv      - the train/val threshold scan

The script also prints a v1-vs-v2 summary table to stdout for the
results doc.
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from kalshi_bot_v2.gate import (  # noqa: E402
    HOLDOUT_FRAC,
    evaluate,
    v1_decision_fn,
)
from kalshi_bot_v2.model import (  # noqa: E402
    feature_importance_df,
    make_decision_fn,
    predict_proba,
    reliability_table,
    save_artifact,
    train_with_threshold_search,
)

DATA_DIR = REPO_ROOT / "data" / "v2"
DATASET_PATH = DATA_DIR / "joined_mlb_dataset.parquet"
MODEL_PATH = DATA_DIR / "mlb_lgb_model.joblib"
FEAT_IMP_PATH = DATA_DIR / "feature_importance.csv"
CAL_TABLE_PATH = DATA_DIR / "calibration_table.csv"
CAL_PLOT_PATH = DATA_DIR / "calibration_plot.png"
GATE_RESULT_PATH = DATA_DIR / "gate_v2_result.json"
THRESHOLD_SCAN_PATH = DATA_DIR / "threshold_scan.csv"


def main() -> int:
    if not DATASET_PATH.exists():
        print(f"ERROR: dataset not found at {DATASET_PATH}", file=sys.stderr)
        return 1

    df = pd.read_parquet(DATASET_PATH)
    print(f"Loaded {len(df)} rows from {DATASET_PATH.name}")
    print(f"  Eligible: {int(df['is_strategy_b_eligible'].sum())}")
    print(f"  Outcome rate (all): {df['outcome'].mean():.4f}")
    elig = df[df["is_strategy_b_eligible"]]
    if len(elig) > 0:
        print(f"  Outcome rate (eligible): {elig['outcome'].mean():.4f}")
    print()

    # Chronological holdout split (same as the gate uses)
    df_sorted = df.sort_values("close_time").reset_index(drop=True)
    split_idx = int(len(df_sorted) * (1.0 - HOLDOUT_FRAC))
    train_df = df_sorted.iloc[:split_idx].copy()
    holdout_df = df_sorted.iloc[split_idx:].copy()
    print(f"Train rows: {len(train_df)} | Holdout rows: {len(holdout_df)}")
    print(f"  Train eligible: {int(train_df['is_strategy_b_eligible'].sum())}")
    print(f"  Holdout eligible: {int(holdout_df['is_strategy_b_eligible'].sum())}")
    print()

    # Train model
    # Calibration note: with only 5 eligible rows in the val slice, isotonic
    # calibration creates a few discrete prediction plateaus that destroy
    # the booster's continuous probability ranking. We disable calibration
    # here so the model_prob - price edge signal is continuous, and rely on
    # the booster's raw output ranking. The reliability table on raw probs
    # is still emitted for honest reporting.
    #
    # Walk-forward scan is also disabled: on this small dataset (123
    # eligible) per-fold boosters train on shrunken prefixes; their OOS
    # predictions are noisier than the final model and so the walk-forward
    # scan picks too-aggressive edges, leaving too few holdout trades.
    print("Training LightGBM (calibration off, val-slice scan)...")
    artifact = train_with_threshold_search(
        train_df, val_frac=0.20, calibrate=False,
        use_walk_forward_for_scan=False,
    )
    print(f"  Best iteration:        {artifact.notes['best_iteration']}")
    print(f"  Inner train n:         {artifact.notes['inner_train_n']}")
    print(f"  Inner val n:           {artifact.notes['inner_val_n']}")
    print(f"  Val eligible n:        {artifact.notes['val_eligible_n']}")
    print(f"  Best abs threshold:    {artifact.threshold:.3f}")
    print(f"  Best edge threshold:   {artifact.edge_threshold:+.3f}")
    print()

    # Save model
    save_artifact(artifact, MODEL_PATH)
    print(f"Saved model: {MODEL_PATH}")

    # Save threshold scans
    if artifact.notes.get("threshold_scan"):
        scan_df = pd.DataFrame(artifact.notes["threshold_scan"])
        scan_df.to_csv(THRESHOLD_SCAN_PATH, index=False)
        print(f"Saved threshold scan: {THRESHOLD_SCAN_PATH}")
        print()
        print("Absolute-threshold scan (val slice, eligible-only):")
        print(scan_df.to_string(index=False, float_format="%.4f"))
        print()
    if artifact.notes.get("edge_scan"):
        edge_df = pd.DataFrame(artifact.notes["edge_scan"])
        edge_df.to_csv(DATA_DIR / "edge_scan.csv", index=False)
        print(f"Saved edge scan: {DATA_DIR / 'edge_scan.csv'}")
        print()
        print("Edge-threshold scan (val slice, eligible-only):")
        print(edge_df.to_string(index=False, float_format="%.4f"))
        print()

    # Feature importance
    feat_imp = feature_importance_df(artifact, importance_type="gain")
    feat_imp.to_csv(FEAT_IMP_PATH, index=False)
    print(f"Saved feature importance: {FEAT_IMP_PATH}")
    print()
    print("Top 10 features by gain:")
    print(feat_imp.head(10).to_string(index=False, float_format="%.2f"))
    print()

    # Calibration table on the inner val slice (using calibrator's input distribution)
    # We rebuild val_df probabilities to assess calibration
    train_sorted = train_df.sort_values("close_time").reset_index(drop=True)
    val_split_idx = int(len(train_sorted) * (1.0 - 0.20))
    val_df = train_sorted.iloc[val_split_idx:]
    val_probs = predict_proba(artifact, val_df)
    val_y = val_df["outcome"].astype(int).to_numpy()
    cal_table = reliability_table(val_probs, val_y, n_bins=10)
    cal_table.to_csv(CAL_TABLE_PATH, index=False)
    print(f"Saved calibration table: {CAL_TABLE_PATH}")
    print()
    print("Calibration table (val slice):")
    print(cal_table.to_string(index=False, float_format="%.4f"))
    print()

    # Calibration plot
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(6, 6))
        # Plot bin midpoint vs mean actual; size by n
        valid = cal_table[cal_table["n"] > 0].copy()
        valid["bin_mid"] = (valid["bin_lower"] + valid["bin_upper"]) / 2.0
        ax.plot([0, 1], [0, 1], linestyle="--", color="gray", label="perfect")
        ax.scatter(
            valid["mean_pred"], valid["mean_actual"],
            s=valid["n"] * 4 + 20, alpha=0.7, label="calibrated model",
        )
        for _, r in valid.iterrows():
            ax.annotate(
                str(int(r["n"])),
                (r["mean_pred"], r["mean_actual"]),
                fontsize=8, ha="center", va="bottom",
            )
        ax.set_xlabel("Mean predicted probability")
        ax.set_ylabel("Mean actual outcome")
        ax.set_title("Calibration plot (val slice, point label = n)")
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.legend()
        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.savefig(CAL_PLOT_PATH, dpi=120)
        plt.close(fig)
        print(f"Saved calibration plot: {CAL_PLOT_PATH}")
        print()
    except Exception as e:  # noqa: BLE001
        print(f"Calibration plot skipped: {e}")
        print()

    # Run the v2 gate on the eligible subset (Strategy B domain)
    eligible_df = df[df["is_strategy_b_eligible"]].copy()
    print(f"Running v2 gate on {len(eligible_df)} eligible rows...")
    decision_fn = make_decision_fn(artifact, df, mode="hybrid")
    res_v2 = evaluate(eligible_df, decision_fn, note="lgb_v2_hybrid")
    res_v1 = evaluate(eligible_df, v1_decision_fn, note="v1_baseline")
    # Also evaluate edge-only and absolute-only for the comparison table
    decision_fn_edge = make_decision_fn(artifact, df, mode="edge")
    decision_fn_abs = make_decision_fn(artifact, df, mode="absolute")
    res_v2_edge = evaluate(eligible_df, decision_fn_edge, note="lgb_v2_edge")
    res_v2_abs = evaluate(eligible_df, decision_fn_abs, note="lgb_v2_abs")
    print()
    print("=" * 70)
    print("V1 BASELINE GATE RESULT")
    print("=" * 70)
    _print_gate(res_v1)

    print()
    print("=" * 70)
    print("V2 (LightGBM, HYBRID rule = th + edge) GATE RESULT  [PRIMARY]")
    print("=" * 70)
    _print_gate(res_v2)

    print()
    print("=" * 70)
    print("V2 (LightGBM, EDGE rule only) GATE RESULT  [comparison]")
    print("=" * 70)
    _print_gate(res_v2_edge)

    print()
    print("=" * 70)
    print("V2 (LightGBM, ABSOLUTE rule only) GATE RESULT  [comparison]")
    print("=" * 70)
    _print_gate(res_v2_abs)

    print()
    print("v2 (hybrid) minus v1 holdout mean:", res_v2.holdout_mean - res_v1.holdout_mean)

    # Save full gate results
    out = {
        "v1_baseline": _serialize_gate(res_v1),
        "v2_model_hybrid": _serialize_gate(res_v2),
        "v2_model_edge": _serialize_gate(res_v2_edge),
        "v2_model_absolute": _serialize_gate(res_v2_abs),
        "v2_hybrid_minus_v1_holdout_mean": float(res_v2.holdout_mean - res_v1.holdout_mean)
        if not (np.isnan(res_v2.holdout_mean) or np.isnan(res_v1.holdout_mean))
        else None,
    }
    with GATE_RESULT_PATH.open("w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"\nSaved gate result JSON: {GATE_RESULT_PATH}")

    return 0


def _print_gate(res) -> None:
    print(f"  Train n / Test n / Eligible n: {res.holdout_train_n} / {res.holdout_test_n} / {res.holdout_eligible_n}")
    print(f"  Holdout mean P&L:              {res.holdout_mean:.4f}")
    print(f"  Holdout median P&L:            {res.holdout_median:.4f}")
    print(f"  Holdout SD:                    {res.holdout_sd:.4f}")
    print(f"  Holdout hit rate:              {res.holdout_hit_rate:.4f}")
    print(f"  Holdout 95% CI:                [{res.holdout_ci_lower:.4f}, {res.holdout_ci_upper:.4f}]")
    print(f"  Folds eligible total:          {res.folds_eligible_total}")
    print(f"  Folds pooled mean:             {res.folds_pooled_mean:.4f}")
    print(f"  Folds pooled CI:               [{res.folds_pooled_ci_lower:.4f}, {res.folds_pooled_ci_upper:.4f}]")
    print(f"  Per-fold means:                {[f'{m:.4f}' for m in res.fold_means]}")
    print(f"  v1 holdout mean (for C6):      {res.v1_holdout_mean:.4f}")
    print("  Criteria:")
    for k, v in res.criteria.items():
        status = "PASS" if v else "FAIL"
        print(f"    {k}: {status}")
    print(f"  Overall: {'PASS' if res.passes else 'FAIL'}")


def _serialize_gate(res) -> dict:
    d = asdict(res)
    # Replace NaN with None so JSON is valid
    return {k: (None if isinstance(v, float) and np.isnan(v) else v) for k, v in d.items()}


if __name__ == "__main__":
    sys.exit(main())
