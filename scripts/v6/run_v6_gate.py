"""Run v6 model training + gate evaluation.

Inputs:
- data/v6/v6_master.parquet
- data/v6/v6_orthogonality_results.json (must have midband features that passed)

Outputs:
- data/v6/v6_gate_results.json
- data/v6/v6_run_manifest.json
- research/v6/07-model-results.md
- research/v6/08-gate-results.md

Per phase-1.5-methodology.md Sections 5, 6, 7, 8.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from kalshi_bot_v6.v6_model import (  # noqa: E402
    cluster_bootstrap_pnl,
    expected_calibration_error,
    fit_lightgbm,
    fit_logreg_with_cv,
    predict_proba,
    rule_a_pnl_per_contract,
    rule_b_expected_pnl_per_contract,
)

DATA_DIR = REPO_ROOT / "data" / "v6"
RESEARCH_DIR = REPO_ROOT / "research" / "v6"
SEED = 42


def log(msg: str) -> None:
    print(f"[gate] {msg}", flush=True)


def chronological_split(
    df: pd.DataFrame,
    train_frac: float = 0.60,
    orth_frac: float = 0.25,
    purge_hours: int = 24,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    df = df.sort_values("close_time").reset_index(drop=True)
    n = len(df)
    train_end_idx = int(round(n * train_frac))
    orth_end_idx = int(round(n * (train_frac + orth_frac)))
    train_close_max = df.iloc[train_end_idx - 1]["close_time"]
    orth_close_max = df.iloc[orth_end_idx - 1]["close_time"]
    purge = pd.Timedelta(hours=purge_hours)
    train = df.iloc[:train_end_idx].copy()
    orth = df.iloc[train_end_idx:orth_end_idx].copy()
    orth = orth[orth["close_time"] >= train_close_max + purge].copy()
    final = df.iloc[orth_end_idx:].copy()
    final = final[final["close_time"] >= orth_close_max + purge].copy()
    return train, orth, final


def main() -> int:
    master_path = DATA_DIR / "v6_master.parquet"
    ortho_path = DATA_DIR / "v6_orthogonality_results.json"
    if not master_path.exists():
        log(f"missing {master_path}")
        return 1
    if not ortho_path.exists():
        log(f"missing {ortho_path}; run run_v6_orthogonality first")
        return 1
    df = pd.read_parquet(master_path)
    with open(ortho_path) as f:
        ortho = json.load(f)
    log(f"loaded master n={len(df)}; ortho verdict={ortho.get('k1_verdict')}")

    # Pick best horizon: max passed features on midband
    horizon_choice = None
    best_n_passed = -1
    for h_key, hr in ortho.get("by_horizon", {}).items():
        if not isinstance(hr, dict):
            continue
        if hr.get("band_used") != "midband":
            continue
        n_passed = int(hr.get("n_passed", 0))
        if n_passed > best_n_passed:
            best_n_passed = n_passed
            horizon_choice = int(h_key)
    if horizon_choice is None or best_n_passed <= 0:
        log("K1 NULL: no midband passes; writing NULL gate result")
        # Compose K1 NULL manifest with what we have
        all_midband = df[
            (df["kalshi_mid_at_t"] >= 0.55) & (df["kalshi_mid_at_t"] <= 0.80)
        ]
        manifest = {
            "run_timestamp": pd.Timestamp.now(tz="UTC").isoformat(),
            "verdict": "NULL",
            "kill_reason_if_null": "K1",
            "note": (
                "No features cleared +0.005 Brier improvement on midband "
                "holdout (per Section 3.1). Model not trained."
            ),
            "split": {
                "midband_n_total": int(len(all_midband)),
            },
            "midband_definition": [0.55, 0.80],
            "ortho_summary": {
                "k1_verdict": ortho.get("k1_verdict"),
                "midband_passes": ortho.get("midband_passes"),
                "widerband_passes": ortho.get("widerband_passes"),
                "by_horizon": {
                    h: {
                        "band_used": hr.get("band_used"),
                        "n_passed": hr.get("n_passed"),
                        "passed_features": hr.get("passed_features"),
                    }
                    for h, hr in ortho.get("by_horizon", {}).items()
                    if isinstance(hr, dict)
                },
            },
            "gate": {
                "C1_pass": False,
            },
        }
        with open(DATA_DIR / "v6_gate_results.json", "w") as f:
            json.dump(manifest, f, indent=2, default=str)
        with open(DATA_DIR / "v6_run_manifest.json", "w") as f:
            json.dump(manifest, f, indent=2, default=str)
        log(f"wrote {DATA_DIR / 'v6_gate_results.json'}")
        log(f"wrote {DATA_DIR / 'v6_run_manifest.json'}")
        return 0

    log(f"horizon chosen: T-{horizon_choice} with {best_n_passed} passed features")
    h = horizon_choice
    sub = df[df["horizon_min"] == h].copy()
    train, orth, final = chronological_split(sub)
    train_mid = train[
        (train["kalshi_mid_at_t"] >= 0.55) & (train["kalshi_mid_at_t"] <= 0.80)
    ].copy()
    orth_mid = orth[
        (orth["kalshi_mid_at_t"] >= 0.55) & (orth["kalshi_mid_at_t"] <= 0.80)
    ].copy()
    final_mid = final[
        (final["kalshi_mid_at_t"] >= 0.55) & (final["kalshi_mid_at_t"] <= 0.80)
    ].copy()

    surviving_features = ortho["by_horizon"][str(h)]["passed_features"]
    log(f"surviving features (excluding F4 if flagged): {surviving_features}")
    # Filter out F4 (kalshi_price_drift) per K1b regardless of pass status
    surviving_features = [
        f for f in surviving_features if not f.startswith("kalshi_price_drift")
    ]
    log(f"after K1b drop: {surviving_features}")

    feature_cols = ["kalshi_mid_at_t"] + surviving_features

    # Train M1 (LogReg) with TS-CV on C
    logreg, logreg_meta = fit_logreg_with_cv(train_mid, feature_cols)
    if logreg is None:
        log(f"M1 fit failed: {logreg_meta}")
        verdict = {"verdict": "NULL", "kill_reason": "K1", "note": "M1 fit failed"}
        with open(DATA_DIR / "v6_gate_results.json", "w") as f:
            json.dump(verdict, f, indent=2)
        return 0

    # Train M2 (LightGBM)
    lgbm, lgbm_meta = fit_lightgbm(train_mid, feature_cols)

    # Evaluate on orth_mid
    def predict(model: Any, dfsub: pd.DataFrame) -> tuple[np.ndarray, pd.DataFrame]:
        s = dfsub.dropna(subset=feature_cols + ["outcome_yes"]).copy()
        if len(s) == 0:
            return np.array([]), s
        X = s[feature_cols].astype(float).to_numpy()
        return predict_proba(model, X), s

    def brier_skill_score(probs: np.ndarray, y: np.ndarray, train_y: np.ndarray) -> float:
        if len(probs) == 0:
            return float("nan")
        b_model = brier_score_loss(y, probs)
        # baseline: constant predict at train_mean
        baseline_p = train_y.mean()
        b_base = brier_score_loss(y, np.full_like(probs, baseline_p))
        if b_base <= 0:
            return float("nan")
        return 1.0 - b_model / b_base

    train_y = train_mid["outcome_yes"].astype(int).to_numpy()

    logreg_probs, logreg_sub = predict(logreg, orth_mid)
    if len(logreg_sub):
        logreg_y_orth = logreg_sub["outcome_yes"].astype(int).to_numpy()
        logreg_bss_orth = brier_skill_score(logreg_probs, logreg_y_orth, train_y)
    else:
        logreg_bss_orth = float("nan")

    if lgbm is not None:
        lgbm_probs, lgbm_sub = predict(lgbm, orth_mid)
        if len(lgbm_sub):
            lgbm_y_orth = lgbm_sub["outcome_yes"].astype(int).to_numpy()
            lgbm_bss_orth = brier_skill_score(lgbm_probs, lgbm_y_orth, train_y)
        else:
            lgbm_bss_orth = float("nan")
    else:
        lgbm_bss_orth = float("nan")

    log(f"BSS on orth holdout - M1 (LogReg): {logreg_bss_orth:.4f}")
    log(f"BSS on orth holdout - M2 (LGBM):   {lgbm_bss_orth:.4f}")

    use_lgbm = (
        lgbm is not None
        and not np.isnan(lgbm_bss_orth)
        and (np.isnan(logreg_bss_orth) or lgbm_bss_orth > logreg_bss_orth)
    )
    selected = "M2_LightGBM" if use_lgbm else "M1_LogReg"
    selected_model = lgbm if use_lgbm else logreg
    log(f"selected model: {selected}")

    # ECE check + isotonic calibration if needed
    sel_probs_orth, sel_sub_orth = predict(selected_model, orth_mid)
    sel_y_orth = sel_sub_orth["outcome_yes"].astype(int).to_numpy() if len(sel_sub_orth) else np.array([])
    ece = expected_calibration_error(sel_probs_orth, sel_y_orth) if len(sel_y_orth) else float("nan")
    log(f"selected model ECE on orth: {ece:.4f}")
    calibrator = None
    if not np.isnan(ece) and ece > 0.05 and len(sel_y_orth) >= 30:
        from sklearn.isotonic import IsotonicRegression
        calibrator = IsotonicRegression(out_of_bounds="clip").fit(
            sel_probs_orth, sel_y_orth,
        )
        log("  applied isotonic calibration on orth slice")

    # FINAL holdout
    sel_probs_final, sel_sub_final = predict(selected_model, final_mid)
    if calibrator is not None and len(sel_probs_final):
        sel_probs_final = calibrator.predict(sel_probs_final)
    sel_y_final = (
        sel_sub_final["outcome_yes"].astype(int).to_numpy()
        if len(sel_sub_final) else np.array([])
    )
    sel_mid_final = (
        sel_sub_final["kalshi_mid_at_t"].astype(float).to_numpy()
        if len(sel_sub_final) else np.array([])
    )
    sel_close_final = (
        sel_sub_final["close_time"].dt.date.to_numpy()
        if len(sel_sub_final) else np.array([])
    )

    # C2: BSS on final holdout
    bss_final = (
        brier_skill_score(sel_probs_final, sel_y_final, train_y)
        if len(sel_y_final) else float("nan")
    )
    log(f"C2: BSS_final = {bss_final:.4f}")

    # C4: distribution of |model_prob - kalshi_mid|
    if len(sel_probs_final):
        abs_diff = np.abs(sel_probs_final - sel_mid_final)
        c4_share = float((abs_diff >= 0.03).mean())
    else:
        abs_diff = np.array([])
        c4_share = float("nan")
    log(f"C4: share of holdout with |model_prob - mid| >= 0.03 = {c4_share:.4f}")

    # Rule A and Rule B evaluation on final holdout
    rule_a_pnls = []
    rule_a_sides = []
    rule_a_clusters = []
    rule_b_pnls = []
    rule_b_sides = []
    rule_b_clusters = []
    for prob, mid, outcome, cluster in zip(
        sel_probs_final, sel_mid_final, sel_y_final, sel_close_final,
    ):
        side_a, pnl_a = rule_a_pnl_per_contract(float(prob), float(mid), int(outcome))
        if side_a != "none":
            rule_a_pnls.append(pnl_a)
            rule_a_sides.append(side_a)
            rule_a_clusters.append(cluster)
        side_b, pnl_b = rule_b_expected_pnl_per_contract(float(prob), float(mid), int(outcome))
        if side_b != "none":
            rule_b_pnls.append(pnl_b)
            rule_b_sides.append(side_b)
            rule_b_clusters.append(cluster)

    rule_a_pnls = np.array(rule_a_pnls)
    rule_a_clusters = np.array(rule_a_clusters)
    rule_b_pnls = np.array(rule_b_pnls)
    rule_b_clusters = np.array(rule_b_clusters)

    # C3a, C3b
    boot_a = cluster_bootstrap_pnl(rule_a_pnls, rule_a_clusters)
    boot_b = cluster_bootstrap_pnl(rule_b_pnls, rule_b_clusters)
    log(f"C3a rule A: {boot_a}")
    log(f"C3b rule B: {boot_b}")

    # C4b fire-count floor
    n_final = len(sel_probs_final)
    floor = min(200, max(1, n_final // 100))
    c4b_a_ok = boot_a["n_fires"] >= floor
    c4b_b_ok = boot_b["n_fires"] >= floor
    log(f"C4b floor={floor}; rule A fires={boot_a['n_fires']} ok={c4b_a_ok}")
    log(f"C4b floor={floor}; rule B fires={boot_b['n_fires']} ok={c4b_b_ok}")

    # C5 spread sensitivity
    def rule_a_at_spread(spread_c: float) -> dict[str, Any]:
        pnls = []
        clusters = []
        for prob, mid, outcome, cluster in zip(
            sel_probs_final, sel_mid_final, sel_y_final, sel_close_final,
        ):
            side, pnl = rule_a_pnl_per_contract(
                float(prob), float(mid), int(outcome), spread_c=spread_c,
            )
            if side != "none":
                pnls.append(pnl)
                clusters.append(cluster)
        return cluster_bootstrap_pnl(np.array(pnls), np.array(clusters))

    c5_3c = rule_a_at_spread(0.03)
    c5_4c = rule_a_at_spread(0.04)
    log(f"C5 spread 3c: {c5_3c}")
    log(f"C5 spread 4c: {c5_4c}")

    # Compose gate verdict
    c1_pass = best_n_passed >= 1
    c2_pass = (not np.isnan(bss_final)) and bss_final >= 0.01
    c3a_pass = (
        c4b_a_ok and not np.isnan(boot_a["ci_low"]) and boot_a["ci_low"] > 0.0
    )
    c3b_pass = (
        c4b_b_ok and not np.isnan(boot_b["ci_low"]) and boot_b["ci_low"] > 0.0
    )
    c4_pass = (not np.isnan(c4_share)) and c4_share >= 0.05
    c5_pass = (
        not np.isnan(c5_3c["ci_low"])
        and c5_3c["ci_low"] > -1.0
        and (np.isnan(c5_4c["mean_cents"]) or c5_4c["mean_cents"] > 0.0)
    )

    # Kill condition resolution
    if not c1_pass:
        verdict = "NULL"
        kill = "K1"
    elif not c2_pass:
        verdict = "NULL"
        kill = "K2"
    elif c4b_a_ok or c4b_b_ok:
        # at least one rule had enough fires
        if not c3a_pass and not c3b_pass:
            verdict = "NULL"
            kill = "K3a"
        elif c3a_pass and c3b_pass:
            verdict = "SHIP" if c5_pass else "PARTIAL"
            kill = None if c5_pass else "K5"
        else:
            verdict = "PARTIAL"
            kill = "K3b"
    else:
        verdict = "NULL"
        kill = "K6"

    log(f"Gate verdict: {verdict} (kill={kill})")

    # Manifest
    manifest = {
        "run_timestamp": pd.Timestamp.now(tz="UTC").isoformat(),
        "split": {
            "train_n": int(len(train_mid)),
            "orth_n": int(len(orth_mid)),
            "final_n": int(len(final_mid)),
        },
        "midband_definition": [0.55, 0.80],
        "features": {
            "surviving": surviving_features,
            "feature_cols": feature_cols,
        },
        "model": {
            "class": selected,
            "logreg_C": logreg_meta.get("C") if isinstance(logreg_meta, dict) else None,
            "logreg_bss_orth": logreg_bss_orth,
            "lgbm_bss_orth": lgbm_bss_orth,
            "selected_bss_orth": (
                lgbm_bss_orth if use_lgbm else logreg_bss_orth
            ),
            "selected_bss_final": bss_final,
            "ece_orth": ece,
            "calibrated": calibrator is not None,
        },
        "gate": {
            "C1_pass": c1_pass,
            "C2_pass": c2_pass,
            "C3a": boot_a,
            "C3a_pass": c3a_pass,
            "C3b": boot_b,
            "C3b_pass": c3b_pass,
            "C4_share": c4_share,
            "C4_pass": c4_pass,
            "C4b_floor": floor,
            "C4b_a_ok": c4b_a_ok,
            "C4b_b_ok": c4b_b_ok,
            "C5_3c": c5_3c,
            "C5_4c": c5_4c,
            "C5_pass": c5_pass,
        },
        "verdict": verdict,
        "kill_reason_if_null": kill,
    }
    with open(DATA_DIR / "v6_run_manifest.json", "w") as f:
        json.dump(manifest, f, indent=2, default=str)
    log(f"wrote {DATA_DIR / 'v6_run_manifest.json'}")
    with open(DATA_DIR / "v6_gate_results.json", "w") as f:
        json.dump(manifest, f, indent=2, default=str)
    log(f"wrote {DATA_DIR / 'v6_gate_results.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
