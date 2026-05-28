"""v7 Angle C runner: TabPFN v2 vs LightGBM on v6 and v5-B datasets.

Per `research/v7/04-tabpfn-methodology.md`. Writes:
- `data/v7/tabpfn_v6_predictions.parquet`
- `data/v7/tabpfn_v5b_predictions.parquet`
- `data/v7/tabpfn_orthogonality.json`

Run via `uv run python -m scripts.v7.run_tabpfn`.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from kalshi_bot_v7.tabpfn_swap import (  # noqa: E402
    SEED,
    V5B_SURVIVOR_FEATURES,
    V6_T30_FEATURES,
    apply_purge_24h,
    brier,
    chronological_split,
    cluster_bootstrap_brier_delta,
    drop_na_rows,
    fit_lightgbm,
    fit_logreg_on_mid,
    fit_tabpfn,
    predict_logreg,
    predict_proba_safe,
)

DATA_V6 = REPO_ROOT / "data" / "v6" / "v6_master.parquet"
DATA_V5B = REPO_ROOT / "data" / "v5" / "prop_dataset.parquet"
OUT_DIR = REPO_ROOT / "data" / "v7"
OUT_PRED_V6 = OUT_DIR / "tabpfn_v6_predictions.parquet"
OUT_PRED_V5B = OUT_DIR / "tabpfn_v5b_predictions.parquet"
OUT_JSON = OUT_DIR / "tabpfn_orthogonality.json"


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def load_v6_t30_full() -> pd.DataFrame:
    """Load v6 master parquet, filter to T-30 ONLY (the full horizon-30 sample).
    Midband filter is applied to TRAIN and ORTH HOLDOUT separately after the
    chronological split, to match v6's exact protocol (run_v6_orthogonality.py
    lines 296 to 320: split first by close_time, then band-filter each slice).
    """
    df = pd.read_parquet(DATA_V6)
    df = df[df["horizon_min"] == 30].copy()
    df = df.dropna(subset=["outcome_yes", "kalshi_mid_at_t", "t", "close_time"]).copy()
    df["cluster_day"] = pd.to_datetime(df["t"], utc=True).dt.date.astype(str)
    return df


def filter_midband(df: pd.DataFrame, lo: float = 0.55, hi: float = 0.80) -> pd.DataFrame:
    return df[
        (df["kalshi_mid_at_t"] >= lo) & (df["kalshi_mid_at_t"] <= hi)
    ].copy()


def load_v5b_subsample(n_target: int = 10000) -> pd.DataFrame:
    """Load v5-B prop dataset, stratified random subsample to n=10k, sorted
    chronologically. The stratification preserves the outcome class ratio.
    """
    df = pd.read_parquet(DATA_V5B)
    keep_cols = (
        ["ticker", "outcome", "favorite_price", "game_date_parsed"]
        + V5B_SURVIVOR_FEATURES
    )
    df = df[keep_cols].copy()
    df = df.dropna(subset=["outcome", "favorite_price", "game_date_parsed"]).copy()
    df = df.dropna(subset=V5B_SURVIVOR_FEATURES).copy()
    # stratified subsample
    rng = np.random.default_rng(SEED)
    parts = []
    for outcome, group in df.groupby("outcome"):
        target = int(round(len(group) / len(df) * n_target))
        idx = rng.choice(group.index.to_numpy(), size=min(target, len(group)), replace=False)
        parts.append(group.loc[idx])
    sub = pd.concat(parts).copy()
    # If rounding ended up short by a few, top up randomly without replacement.
    if len(sub) < n_target:
        remaining = df.drop(index=sub.index)
        top_up = rng.choice(
            remaining.index.to_numpy(),
            size=min(n_target - len(sub), len(remaining)),
            replace=False,
        )
        sub = pd.concat([sub, remaining.loc[top_up]])
    sub = sub.sort_values("game_date_parsed").reset_index(drop=True)
    sub["cluster_day"] = pd.to_datetime(sub["game_date_parsed"]).dt.date.astype(str)
    return sub


def run_split(
    df: pd.DataFrame,
    feature_cols: list[str],
    mid_col: str,
    target_col: str,
    time_col: str,
    label: str,
    post_split_band: tuple[float, float] | None = None,
) -> dict[str, Any]:
    """Run TabPFN and LightGBM on a single dataset and report all metrics.

    If `post_split_band` is provided, apply a mid-price band filter AFTER the
    chronological split but BEFORE NaN drop. Mirrors v6's protocol where the
    chronological split is taken on the per-horizon sample and the midband
    filter is then applied to each slice (see run_v6_orthogonality.py).
    """
    df_tr, df_or, df_fi = chronological_split(df, time_col)
    df_tr, df_or, df_fi = apply_purge_24h(df_tr, df_or, df_fi, time_col)
    if post_split_band is not None:
        lo, hi = post_split_band
        df_tr = df_tr[
            (df_tr[mid_col] >= lo) & (df_tr[mid_col] <= hi)
        ].copy()
        df_or = df_or[
            (df_or[mid_col] >= lo) & (df_or[mid_col] <= hi)
        ].copy()
        df_fi = df_fi[
            (df_fi[mid_col] >= lo) & (df_fi[mid_col] <= hi)
        ].copy()
    df_tr = drop_na_rows(df_tr, feature_cols + [mid_col, target_col])
    df_or = drop_na_rows(df_or, feature_cols + [mid_col, target_col])

    out: dict[str, Any] = {
        "label": label,
        "n_train": int(len(df_tr)),
        "n_orth_holdout": int(len(df_or)),
        "n_final_holdout": int(len(df_fi)),
        "feature_cols": feature_cols,
        "mid_col": mid_col,
        "time_col": time_col,
    }

    if len(df_or) < 10 or len(df_tr) < 50:
        out["error"] = "splits_too_small"
        return out

    y_orth = df_or[target_col].astype(int).to_numpy()
    mid_orth = df_or[mid_col].astype(float).to_numpy()

    # Baseline 1: logit on mid only (the literal v6 Section 3.1 protocol).
    logit = fit_logreg_on_mid(df_tr, mid_col, target_col)
    p_mid = predict_logreg(
        logit, df_or[[mid_col]].astype(float).to_numpy(),
    )
    out["brier_baseline_mid_only_logit"] = brier(y_orth, p_mid)

    # Baseline 2: identity (predict = mid). Per v6 Phase 3 critic D3, the
    # logit-on-mid baseline is structurally broken when train and orth holdout
    # have different YES rates: the logit overfits to train mean. The identity
    # baseline (predict = mid) is the apples-to-apples lift comparison v6's
    # FINAL-VERDICT says is the correct one.
    out["brier_baseline_identity"] = brier(y_orth, mid_orth)
    out["d3_logit_vs_identity_gap"] = (
        out["brier_baseline_mid_only_logit"] - out["brier_baseline_identity"]
    )

    # LightGBM on (mid, features)
    X_tr_lgbm_cols = [mid_col] + feature_cols
    t0 = time.perf_counter()
    lgbm_model, lgbm_meta = fit_lightgbm(df_tr, X_tr_lgbm_cols, target_col)
    out["lgbm_fit_seconds"] = time.perf_counter() - t0
    out["lgbm_meta"] = lgbm_meta
    p_lgbm = predict_proba_safe(
        lgbm_model, df_or[X_tr_lgbm_cols].astype(float).to_numpy(),
    )
    out["brier_lgbm_mid_plus_features"] = brier(y_orth, p_lgbm)

    # TabPFN on (mid, features)
    X_tr_tabpfn_cols = [mid_col] + feature_cols
    t0 = time.perf_counter()
    tabpfn_model, tabpfn_meta = fit_tabpfn(df_tr, X_tr_tabpfn_cols, target_col)
    out["tabpfn_fit_seconds"] = time.perf_counter() - t0
    out["tabpfn_meta"] = tabpfn_meta

    t0 = time.perf_counter()
    p_tabpfn = predict_proba_safe(
        tabpfn_model, df_or[X_tr_tabpfn_cols].astype(float).to_numpy(),
    )
    out["tabpfn_predict_seconds"] = time.perf_counter() - t0
    out["brier_tabpfn_mid_plus_features"] = brier(y_orth, p_tabpfn)

    # Brier improvements: reported against BOTH baselines.
    out["lift_lgbm_vs_logit_baseline"] = (
        out["brier_baseline_mid_only_logit"] - out["brier_lgbm_mid_plus_features"]
    )
    out["lift_tabpfn_vs_logit_baseline"] = (
        out["brier_baseline_mid_only_logit"] - out["brier_tabpfn_mid_plus_features"]
    )
    # The CANONICAL lifts per v6 Phase 3 critic D3 finding.
    out["lift_lgbm_vs_identity"] = (
        out["brier_baseline_identity"] - out["brier_lgbm_mid_plus_features"]
    )
    out["lift_tabpfn_vs_identity"] = (
        out["brier_baseline_identity"] - out["brier_tabpfn_mid_plus_features"]
    )
    # Backward-compatible alias used by pass_fail_summary (canonical = identity).
    out["lift_lgbm_vs_mid"] = out["lift_lgbm_vs_identity"]
    out["lift_tabpfn_vs_mid"] = out["lift_tabpfn_vs_identity"]

    # Cluster-bootstrap on TabPFN - LightGBM delta.
    cluster_arr = df_or["cluster_day"].to_numpy()
    out["bootstrap_tabpfn_minus_lgbm"] = cluster_bootstrap_brier_delta(
        y_orth,
        p_a=p_tabpfn,
        p_b=p_lgbm,
        cluster_ids=cluster_arr,
        n_iter=5000,
        seed=SEED,
    )

    # Cache holdout-prediction frame.
    pred_df = df_or[[mid_col, target_col, time_col]].copy()
    pred_df["tabpfn_prob"] = p_tabpfn
    pred_df["lgbm_prob"] = p_lgbm
    pred_df["mid_only_prob"] = p_mid
    pred_df["cluster_day"] = df_or["cluster_day"].to_numpy()
    pred_df["split"] = "orth_holdout"
    out["_pred_df"] = pred_df

    return out


def v6_self_reference_diagnostic(
    df_or: pd.DataFrame,
    p_tabpfn: np.ndarray,
    p_mid: np.ndarray,
    target_col: str,
) -> dict[str, Any]:
    """v6 Section 3.5 stale-vs-fresh split. Reports TabPFN lift on each subset."""
    y = df_or[target_col].astype(int).to_numpy()
    tslt = df_or["time_since_last_trade_at_t"].to_numpy()
    fresh_mask = tslt < 5.0
    stale_mask = ~fresh_mask
    out: dict[str, Any] = {}
    for name, mask in (("stale", stale_mask), ("fresh", fresh_mask)):
        n = int(mask.sum())
        if n < 5:
            out[name] = {"n": n, "lift_tabpfn": float("nan")}
            continue
        b_base = brier(y[mask], p_mid[mask])
        b_tabpfn = brier(y[mask], p_tabpfn[mask])
        out[name] = {"n": n, "lift_tabpfn": b_base - b_tabpfn}
    return out


def pass_fail_summary(headline: dict[str, Any]) -> dict[str, Any]:
    """Apply pre-registered pass thresholds from methodology Section 6.

    C1 uses the v6 D3-corrected identity baseline (predict = mid), NOT the
    raw logit-on-mid output. This matches what v6's FINAL-VERDICT documented
    as the correct apples-to-apples lift measurement.
    """
    v6 = headline.get("v6_midband_t30", {})
    v5b = headline.get("v5b_10k", {})
    # CANONICAL (identity baseline): the only honest reading per v6 D3.
    c1_v6_canonical = v6.get("lift_tabpfn_vs_identity", float("nan"))
    c1_v5b_canonical = v5b.get("lift_tabpfn_vs_identity", float("nan"))
    # FLATTERED (logit-on-mid baseline): would be the literal Section 3.1
    # reading; we report it but do NOT count it as a pass.
    c1_v6_flattered = v6.get("lift_tabpfn_vs_logit_baseline", float("nan"))
    c1_v5b_flattered = v5b.get("lift_tabpfn_vs_logit_baseline", float("nan"))
    c2_v6 = (
        v6.get("brier_lgbm_mid_plus_features", float("nan"))
        - v6.get("brier_tabpfn_mid_plus_features", float("nan"))
    )
    c2_v5b = (
        v5b.get("brier_lgbm_mid_plus_features", float("nan"))
        - v5b.get("brier_tabpfn_mid_plus_features", float("nan"))
    )
    th1 = 0.005
    th2 = 0.003
    passes = {
        "C1_v6_midband_t30_>=_+0.005_lift_over_mid_identity": c1_v6_canonical >= th1,
        "C1_v5b_>=_+0.005_lift_over_mid_identity": c1_v5b_canonical >= th1,
        "C2_v6_midband_t30_>=_+0.003_tabpfn_minus_lgbm": c2_v6 >= th2,
        "C2_v5b_>=_+0.003_tabpfn_minus_lgbm": c2_v5b >= th2,
    }
    n_pass = int(sum(bool(v) for v in passes.values()))
    # The honest decision rule: for v7 Angle C to declare a v6/v5-B salvage,
    # TabPFN must (a) beat the canonical identity baseline by >= +0.005 AND
    # (b) beat LightGBM by >= +0.003 on the SAME dataset. C1 alone is not
    # sufficient because LightGBM might pass it too (v5-B case). C2 alone is
    # not sufficient because both models might be worse than mid (v6 case).
    v6_real_win = (
        passes["C1_v6_midband_t30_>=_+0.005_lift_over_mid_identity"]
        and passes["C2_v6_midband_t30_>=_+0.003_tabpfn_minus_lgbm"]
    )
    v5b_real_win = (
        passes["C1_v5b_>=_+0.005_lift_over_mid_identity"]
        and passes["C2_v5b_>=_+0.003_tabpfn_minus_lgbm"]
    )
    if v6_real_win and v5b_real_win:
        verdict = "PASS"
    elif v6_real_win or v5b_real_win:
        verdict = "PARTIAL"
    else:
        verdict = "NULL"
    return {
        "thresholds": {
            "v6_lift_vs_identity": th1, "lgbm_delta": th2,
        },
        "values_canonical_identity_baseline": {
            "lift_tabpfn_vs_identity_v6": c1_v6_canonical,
            "lift_tabpfn_vs_identity_v5b": c1_v5b_canonical,
            "tabpfn_minus_lgbm_v6": c2_v6,
            "tabpfn_minus_lgbm_v5b": c2_v5b,
        },
        "values_flattered_logit_baseline_d3_warning": {
            "lift_tabpfn_vs_logit_baseline_v6": c1_v6_flattered,
            "lift_tabpfn_vs_logit_baseline_v5b": c1_v5b_flattered,
        },
        "passes": passes,
        "n_pass": n_pass,
        "verdict": verdict,
        "note": (
            "C1 baseline is IDENTITY (predict=mid) per v6 D3 critic finding. "
            "The logit-on-mid baseline that v6 Section 3.1 originally specified "
            "is structurally broken under train/orth regime shift. Reporting "
            "both for transparency."
        ),
    }


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    manifest: dict[str, Any] = {
        "run_timestamp": pd.Timestamp.utcnow().isoformat(),
        "seed": SEED,
        "files": {
            "v6_master_sha256_16": file_hash(DATA_V6),
            "v5b_prop_dataset_sha256_16": file_hash(DATA_V5B),
        },
        "env": {},
    }
    try:
        import tabpfn
        manifest["env"]["tabpfn_version"] = tabpfn.__version__
    except (ImportError, AttributeError):
        manifest["env"]["tabpfn_version"] = "unknown"
    try:
        import torch
        manifest["env"]["torch_version"] = torch.__version__
        manifest["env"]["cuda_available"] = bool(torch.cuda.is_available())
    except ImportError:
        manifest["env"]["torch_version"] = "missing"
        manifest["env"]["cuda_available"] = False
    try:
        import lightgbm
        manifest["env"]["lightgbm_version"] = lightgbm.__version__
    except ImportError:
        manifest["env"]["lightgbm_version"] = "missing"

    # Dataset A: v6 midband T-30. Split on close_time over the full T-30 sample
    # then apply the midband filter to each slice, matching v6 protocol.
    print("[v7-C] Loading v6 master at T-30 (full horizon)...")
    df_v6 = load_v6_t30_full()
    print(f"[v7-C] v6 T-30 full: n={len(df_v6)}")

    print("[v7-C] Running v6 split (post-split midband)...")
    res_v6 = run_split(
        df_v6,
        feature_cols=V6_T30_FEATURES,
        mid_col="kalshi_mid_at_t",
        target_col="outcome_yes",
        time_col="close_time",
        label="v6_midband_t30",
        post_split_band=(0.55, 0.80),
    )

    # v6 self-reference diagnostic.
    pred_df_v6 = res_v6.pop("_pred_df", None)
    if pred_df_v6 is not None and "time_since_last_trade_at_t" in df_v6.columns:
        # Merge on close_time + ticker style identity (close_time is unique in
        # the v6 master at row level for KXBTCD per construction). We use
        # close_time + kalshi_mid_at_t as the composite key to defend against
        # ties.
        pred_df_v6_indexed = pred_df_v6.merge(
            df_v6[["close_time", "kalshi_mid_at_t", "time_since_last_trade_at_t"]],
            on=["close_time", "kalshi_mid_at_t"],
            how="left",
        )
        pred_df_v6_indexed = pred_df_v6_indexed.drop_duplicates(
            subset=["close_time", "kalshi_mid_at_t", "outcome_yes"],
        )
        res_v6["self_reference_diagnostic"] = v6_self_reference_diagnostic(
            pred_df_v6_indexed.assign(
                outcome_yes=pred_df_v6_indexed["outcome_yes"].astype(int),
            ),
            p_tabpfn=pred_df_v6_indexed["tabpfn_prob"].to_numpy(),
            p_mid=pred_df_v6_indexed["mid_only_prob"].to_numpy(),
            target_col="outcome_yes",
        )

    if pred_df_v6 is not None:
        pred_df_v6.to_parquet(OUT_PRED_V6, index=False)

    # Dataset B: v5-B 10k subsample.
    print("[v7-C] Loading v5-B prop dataset 10k subsample...")
    df_v5b = load_v5b_subsample(10000)
    print(f"[v7-C] v5-B subsample n={len(df_v5b)}")
    print("[v7-C] Running v5-B split...")
    res_v5b = run_split(
        df_v5b,
        feature_cols=V5B_SURVIVOR_FEATURES,
        mid_col="favorite_price",
        target_col="outcome",
        time_col="game_date_parsed",
        label="v5b_10k",
    )
    pred_df_v5b = res_v5b.pop("_pred_df", None)
    if pred_df_v5b is not None:
        pred_df_v5b.to_parquet(OUT_PRED_V5B, index=False)

    headline = {
        "v6_midband_t30": res_v6,
        "v5b_10k": res_v5b,
    }
    headline["pass_fail"] = pass_fail_summary(headline)

    output = {
        "manifest": manifest,
        "results": headline,
    }
    with OUT_JSON.open("w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"[v7-C] Wrote {OUT_JSON}")
    print(json.dumps(headline["pass_fail"], indent=2, default=str))


if __name__ == "__main__":
    main()
