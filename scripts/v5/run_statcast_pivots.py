"""V5-B2 pivot exploration: pre-registered fallback variants.

Per brief Section 9, when the primary gate fails we try:
1. Wider take-margin (+5c instead of +2c)
2. Per-prop-type subset models (KS-only, HIT-only, HRR-only)
3. Mid-band-only training and trading (filter to favorite_price in [0.20, 0.80])

These are all pre-registered IF the main gate fails. The goal is to
document each pivot's outcome honestly, not to engineer a passing gate.

Outputs:
    data/v5/statcast_pivots_results.json
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import structlog
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from kalshi_bot_v2.gate import (
    BOOTSTRAP_CI,
    BOOTSTRAP_N_RESAMPLES,
    BOOTSTRAP_SEED,
    HOLDOUT_FRAC,
    GateResult,
    realized_pnl_per_contract,
    v1_decision_fn,
)
from scripts.v5.run_statcast_gate import (
    _holdout_split,
    _kfold_splits,
    _load_orthogonality_survivors,
    _serialize_gate_result,
    evaluate_with_cluster_bootstrap,
)

log = structlog.get_logger(__name__)

DATASET_PATH = Path("data/v5/prop_dataset.parquet")
OUTPUT_JSON = Path("data/v5/statcast_pivots_results.json")


def make_trainer_with_edge(features: list[str], edge_threshold: float):
    """Trainer factory accepting a configurable edge threshold."""

    def trainer(train_df):
        usable_mask = ~train_df[features].isna().any(axis=1)
        usable = train_df.loc[usable_mask]
        if len(usable) < 10:
            def never(_row): return False, 0.0
            return never
        x = usable[features].to_numpy(dtype=float)
        y = usable["outcome"].astype(int).to_numpy()
        if len(np.unique(y)) < 2:
            rate = float(y.mean())
            def constfn(row):
                try:
                    price = float(row.get("favorite_price", 0.5))
                except (TypeError, ValueError):
                    price = 0.5
                return rate > price + edge_threshold, rate
            return constfn
        scaler = StandardScaler()
        x_sc = scaler.fit_transform(x)
        model = LogisticRegression(C=1.0, max_iter=1000, random_state=42)
        model.fit(x_sc, y)

        def decision_fn(row):
            vec = []
            for c in features:
                v = row.get(c)
                if v is None or (isinstance(v, float) and np.isnan(v)):
                    return False, 0.0
                try:
                    vec.append(float(v))
                except (TypeError, ValueError):
                    return False, 0.0
            try:
                price = float(row["favorite_price"])
            except (TypeError, ValueError, KeyError):
                return False, 0.0
            x_row = np.asarray(vec, dtype=float).reshape(1, -1)
            x_sc_row = scaler.transform(x_row)
            prob = float(model.predict_proba(x_sc_row)[0, 1])
            return prob > price + edge_threshold, prob
        return decision_fn

    return trainer


def _fit_anchored(df_train: pd.DataFrame, features: list[str],
                  edge_threshold: float):
    """Fit a single anchored model on df_train and return (decision_fn, ok)."""
    usable_mask = ~df_train[features].isna().any(axis=1)
    usable = df_train.loc[usable_mask]
    if len(usable) < 10:
        def never(_row): return False, 0.0
        return never, False
    x = usable[features].to_numpy(dtype=float)
    y = usable["outcome"].astype(int).to_numpy()
    if len(np.unique(y)) < 2:
        def never(_row): return False, 0.0
        return never, False
    scaler = StandardScaler()
    x_sc = scaler.fit_transform(x)
    model = LogisticRegression(C=1.0, max_iter=1000, random_state=42)
    model.fit(x_sc, y)

    def decision_fn(row):
        vec = []
        for c in features:
            v = row.get(c)
            if v is None or (isinstance(v, float) and np.isnan(v)):
                return False, 0.0
            try:
                vec.append(float(v))
            except (TypeError, ValueError):
                return False, 0.0
        try:
            price = float(row["favorite_price"])
        except (TypeError, ValueError, KeyError):
            return False, 0.0
        x_row = np.asarray(vec, dtype=float).reshape(1, -1)
        x_sc_row = scaler.transform(x_row)
        prob = float(model.predict_proba(x_sc_row)[0, 1])
        return prob > price + edge_threshold, prob

    return decision_fn, True


def _run_variant(
    df: pd.DataFrame, features: list[str], *,
    edge_threshold: float, label: str,
) -> dict[str, Any]:
    train_70, _ = _holdout_split(df)
    decision_fn, ok = _fit_anchored(train_70, features, edge_threshold)
    if not ok:
        return {"label": label, "skipped": True, "reason": "degenerate train"}
    trainer = make_trainer_with_edge(features, edge_threshold)
    res = evaluate_with_cluster_bootstrap(
        df, decision_fn, trainer=trainer,
        note=f"{label} (edge={edge_threshold:+.3f}, features={features})",
    )
    return {"label": label, "skipped": False,
            "features": features,
            "edge_threshold": edge_threshold,
            "gate_result": _serialize_gate_result(res)}


def main() -> None:
    log.info("pivots_start")
    df = pd.read_parquet(DATASET_PATH)
    log.info("dataset_loaded", n=len(df))
    survivors = _load_orthogonality_survivors()
    log.info("orthogonality_survivors", n=len(survivors), features=survivors)

    variants: list[dict[str, Any]] = []

    # Pivot 1: wider take margin (+5c).
    variants.append(_run_variant(
        df, ["favorite_price"], edge_threshold=0.05,
        label="P1_price_only_edge_5c",
    ))
    if survivors:
        variants.append(_run_variant(
            df, ["favorite_price"] + survivors, edge_threshold=0.05,
            label="P1_price_plus_survivors_edge_5c",
        ))

    # Pivot 2: per-prop-type subset models.
    for series in ("KXMLBHIT", "KXMLBHR", "KXMLBHRR", "KXMLBKS"):
        df_sub = df[df["series"] == series].copy()
        if len(df_sub) < 100:
            continue
        # G2-equivalent for the subset.
        variants.append(_run_variant(
            df_sub, ["favorite_price"], edge_threshold=0.02,
            label=f"P2_{series}_only_price_edge_2c",
        ))
        # G3-equivalent if any compatible survivors.
        compat_survivors = (
            [s for s in survivors if s.startswith("pit")]
            if series == "KXMLBKS"
            else [s for s in survivors if s.startswith("bat")]
        )
        if compat_survivors:
            variants.append(_run_variant(
                df_sub, ["favorite_price"] + compat_survivors,
                edge_threshold=0.02,
                label=f"P2_{series}_only_price_plus_survivors_edge_2c",
            ))

    # Pivot 3: mid-band-only (filter price in [0.20, 0.80]).
    df_mid = df[(df["favorite_price"] >= 0.20) & (df["favorite_price"] <= 0.80)].copy()
    log.info("midband_subset", n=len(df_mid), by_series=df_mid["series"].value_counts().to_dict())
    if len(df_mid) >= 100:
        variants.append(_run_variant(
            df_mid, ["favorite_price"], edge_threshold=0.02,
            label="P3_midband_price_only_edge_2c",
        ))
        if survivors:
            variants.append(_run_variant(
                df_mid, ["favorite_price"] + survivors, edge_threshold=0.02,
                label="P3_midband_price_plus_survivors_edge_2c",
            ))

    payload = {
        "dataset_path": str(DATASET_PATH),
        "n_dataset": int(len(df)),
        "orthogonality_survivors": survivors,
        "variants": variants,
    }
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(payload, indent=2, default=str))
    log.info("pivots_done", n_variants=len(variants), path=str(OUTPUT_JSON))

    print("=" * 70)
    print("Pivot summary")
    print("=" * 70)
    for v in variants:
        if v.get("skipped"):
            print(f"\n{v['label']}: SKIPPED - {v.get('reason')}")
            continue
        r = v["gate_result"]
        print(f"\n{v['label']}:")
        print(f"  features:         {len(v['features'])} feats")
        print(f"  holdout_n:        {r['holdout_eligible_n']}")
        print(f"  holdout_mean:     {r['holdout_mean']}")
        print(f"  ci_lower:         {r['holdout_ci_lower']}")
        print(f"  hit_rate:         {r['holdout_hit_rate']}")
        print(f"  folds_pooled:     {r['folds_pooled_mean']}")
        print(f"  passes:           {r['passes']}")


if __name__ == "__main__":
    main()
