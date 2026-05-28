"""Run v6 orthogonality screen per phase-1.5-methodology.md Section 3.

Inputs: data/v6/v6_master.parquet
Outputs:
- data/v6/v6_orthogonality_results.json
- research/v6/06-orthogonality.md (markdown writeup)

Steps:
1. Load master parquet, split by chronological 60/25/15 with 24h purge.
2. Per-horizon: filter to midband [0.55, 0.80] (with widerband fallback per 3.4).
3. Compute pairwise correlation matrix, drop the lower-priority of any pair
   with |rho| > 0.85 (Section 3.3, priority list F1 > F2 > F4 > F6 > F7 > F5 > F8 > F9 > F3).
4. For each surviving feature, fit baseline (kalshi_mid only) and augmented
   (kalshi_mid + feature) logistic regression on train; compute Brier on the
   orthogonality holdout (= test slice). Improvement = baseline - augmented.
5. Funding-delta amendment: baseline for funding-delta includes funding-level.
6. Self-reference diagnostic (Section 3.5): split holdout by
   time_since_last_trade < 5 min vs >= 5 min; report F1 lift on each subset.
7. Sample-size guard (Section 3.4): if midband train YES/NO < 50 or test < 30,
   fall back to widerband; if widerband also fails, K1 NULL.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

DATA_DIR = REPO_ROOT / "data" / "v6"
RESEARCH_DIR = REPO_ROOT / "research" / "v6"
SEED = 42

PRIORITY_ORDER = [
    "kalshi_cvd",
    "kalshi_trade_count",
    "kalshi_price_drift",
    "coinbase_realized_vol",
    "coinbase_vwap_dev",
    "funding_rate_delta_4h_at_t",
    "dvol_delta_1h_at_t",
    "basis_delta_1h_at_t",
    "time_since_last_trade_at_t",
]

# A column matches a priority key if it starts with it (handles horizon suffix)
def priority_rank(col: str) -> int:
    for i, key in enumerate(PRIORITY_ORDER):
        if col.startswith(key):
            return i
    return 999


def log(msg: str) -> None:
    print(f"[orthogonality] {msg}", flush=True)


def chronological_split(
    df: pd.DataFrame,
    train_frac: float = 0.60,
    orth_frac: float = 0.25,
    purge_hours: int = 24,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Return (train, orth_holdout, final_holdout) with 24h purge buffers."""
    df = df.sort_values("close_time").reset_index(drop=True)
    n = len(df)
    train_end_idx = int(round(n * train_frac))
    orth_end_idx = int(round(n * (train_frac + orth_frac)))

    train_close_max = df.iloc[train_end_idx - 1]["close_time"]
    orth_close_max = df.iloc[orth_end_idx - 1]["close_time"]

    train = df.iloc[:train_end_idx].copy()
    # Purge: rows in train at or beyond train_close_max - 24h that overlap with orth?
    # Simpler: drop orth-holdout rows whose close_time < train_close_max + 24h.
    purge = pd.Timedelta(hours=purge_hours)
    orth = df.iloc[train_end_idx:orth_end_idx].copy()
    orth = orth[orth["close_time"] >= train_close_max + purge].copy()

    final = df.iloc[orth_end_idx:].copy()
    final = final[final["close_time"] >= orth_close_max + purge].copy()

    return train, orth, final


def get_horizon_feature_cols(horizon: int) -> list[str]:
    return [
        f"kalshi_cvd_{horizon}",
        f"kalshi_trade_count_{horizon}",
        f"kalshi_price_drift_{horizon}",
        f"coinbase_realized_vol_{horizon}",
        f"coinbase_vwap_dev_{horizon}",
        "time_since_last_trade_at_t",
        "funding_rate_level_at_t",
        "funding_rate_delta_4h_at_t",
        "dvol_delta_1h_at_t",
        "basis_delta_1h_at_t",
        "nan_pct_in_window",
    ]


def sample_size_ok(
    train: pd.DataFrame,
    test: pd.DataFrame,
    band_label: str,
) -> tuple[bool, dict[str, Any]]:
    """Section 3.4 guards."""
    train_yes = int((train["outcome_yes"] == 1).sum())
    train_no = int((train["outcome_yes"] == 0).sum())
    test_yes = int((test["outcome_yes"] == 1).sum())
    test_no = int((test["outcome_yes"] == 0).sum())
    ok = (
        train_yes >= 50 and train_no >= 50 and test_yes >= 30 and test_no >= 30
    )
    return ok, {
        "band": band_label,
        "train_yes": train_yes,
        "train_no": train_no,
        "test_yes": test_yes,
        "test_no": test_no,
        "ok": ok,
    }


def correlation_drops(df: pd.DataFrame, feat_cols: list[str]) -> list[dict[str, Any]]:
    """Section 3.3 pairwise correlation pre-screen."""
    sub = df[feat_cols].copy()
    sub = sub.dropna(how="all", axis=1)
    actual_cols = list(sub.columns)
    corr = sub.corr().abs()
    drops: list[dict[str, Any]] = []
    dropped_set: set[str] = set()
    # iterate over upper triangle pairs sorted by rho desc
    pairs: list[tuple[float, str, str]] = []
    for i, a in enumerate(actual_cols):
        for b in actual_cols[i + 1:]:
            r = corr.loc[a, b]
            if pd.notna(r) and r >= 0.85:
                pairs.append((float(r), a, b))
    pairs.sort(key=lambda x: -x[0])
    for r, a, b in pairs:
        if a in dropped_set or b in dropped_set:
            continue
        # drop the lower-priority one (higher rank index = lower priority)
        ra = priority_rank(a)
        rb = priority_rank(b)
        if ra <= rb:
            drop, keep = b, a
        else:
            drop, keep = a, b
        dropped_set.add(drop)
        drops.append({"dropped": drop, "kept": keep, "rho": r})
    return drops


def fit_brier_on_same_subset(
    train: pd.DataFrame,
    test: pd.DataFrame,
    aug_cols: list[str],
    base_cols: list[str],
) -> tuple[float, float, int, int]:
    """Fit baseline (base_cols) AND augmented (aug_cols) on the SAME sub-sample
    of rows that have ALL aug_cols non-NaN. This is the fair like-for-like
    comparison required by Section 3.1.

    Returns (brier_baseline, brier_augmented, n_train, n_test).
    """
    sub_train = train.dropna(subset=aug_cols + ["outcome_yes"]).copy()
    sub_test = test.dropna(subset=aug_cols + ["outcome_yes"]).copy()
    if (
        len(sub_train) < 20
        or len(np.unique(sub_train["outcome_yes"])) < 2
        or len(sub_test) < 5
    ):
        return float("nan"), float("nan"), len(sub_train), len(sub_test)
    y_train = sub_train["outcome_yes"].astype(int).to_numpy()
    y_test = sub_test["outcome_yes"].astype(int).to_numpy()

    # Baseline on same subset (using only base_cols of those rows)
    X_train_base = sub_train[base_cols].astype(float).to_numpy()
    X_test_base = sub_test[base_cols].astype(float).to_numpy()
    base_model = LogisticRegression(
        C=10.0, max_iter=500, random_state=SEED,
    ).fit(X_train_base, y_train)
    p_base = base_model.predict_proba(X_test_base)[:, 1]
    brier_base = brier_score_loss(y_test, p_base)

    # Augmented on same subset
    X_train_aug = sub_train[aug_cols].astype(float).to_numpy()
    X_test_aug = sub_test[aug_cols].astype(float).to_numpy()
    aug_model = LogisticRegression(
        C=10.0, max_iter=500, random_state=SEED,
    ).fit(X_train_aug, y_train)
    p_aug = aug_model.predict_proba(X_test_aug)[:, 1]
    brier_aug = brier_score_loss(y_test, p_aug)

    return float(brier_base), float(brier_aug), len(sub_train), len(sub_test)


def evaluate_feature(
    train: pd.DataFrame,
    test: pd.DataFrame,
    feature_col: str,
    baseline_extra_cols: list[str] | None = None,
) -> dict[str, Any]:
    """Compute Brier improvement from adding `feature_col` to baseline.

    Both models are fit on the SAME row-subset (drop-NaN on aug_cols), which
    is the like-for-like comparison required by Section 3.1.
    """
    base_cols = ["kalshi_mid_at_t"]
    if baseline_extra_cols:
        base_cols += baseline_extra_cols
    aug_cols = base_cols + [feature_col]
    brier_base, brier_aug, n_train, n_test = fit_brier_on_same_subset(
        train, test, aug_cols, base_cols,
    )
    if np.isnan(brier_base) or np.isnan(brier_aug):
        improvement = float("nan")
    else:
        improvement = brier_base - brier_aug
    return {
        "feature": feature_col,
        "baseline_cols": base_cols,
        "augmented_cols": aug_cols,
        "brier_baseline": brier_base,
        "brier_augmented": brier_aug,
        "brier_improvement": improvement,
        "n_train": int(n_train),
        "n_test": int(n_test),
        "pass_005": (
            (improvement >= 0.005) if not np.isnan(improvement) else False
        ),
    }


def self_reference_diagnostic(
    train: pd.DataFrame,
    test: pd.DataFrame,
    feature_col: str,
) -> dict[str, Any]:
    """Section 3.5 self-reference diagnostic for F1 (kalshi_cvd_*).

    Split test by time_since_last_trade < 5min vs >= 5min; compute lift each.
    """
    if "time_since_last_trade_at_t" not in test.columns:
        return {"error": "no time_since_last_trade column"}
    stale = test["time_since_last_trade_at_t"] >= 5.0
    test_stale = test[stale]
    test_fresh = test[~stale]
    result: dict[str, Any] = {
        "n_stale": int(len(test_stale)),
        "n_fresh": int(len(test_fresh)),
    }
    for name, sub in (("stale", test_stale), ("fresh", test_fresh)):
        if len(sub) < 20:
            result[name] = {"n": len(sub), "lift": None, "note": "n too small"}
            continue
        ev = evaluate_feature(train, sub, feature_col)
        result[name] = {
            "n": len(sub),
            "brier_base": ev["brier_baseline"],
            "brier_aug": ev["brier_augmented"],
            "lift": ev["brier_improvement"],
        }
    return result


def main() -> int:
    out_dir = DATA_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    research_dir = RESEARCH_DIR
    research_dir.mkdir(parents=True, exist_ok=True)

    master_path = DATA_DIR / "v6_master.parquet"
    if not master_path.exists():
        log(f"missing {master_path}")
        return 1
    df = pd.read_parquet(master_path)
    log(f"loaded {len(df)} rows from {master_path.name}")

    results: dict[str, Any] = {
        "n_rows_total": int(len(df)),
        "by_horizon": {},
    }

    for h in (30, 15):
        log(f"=== horizon T-{h} ===")
        sub = df[df["horizon_min"] == h].copy()
        log(f"  n rows: {len(sub)}")
        if len(sub) < 20:
            results["by_horizon"][h] = {"status": "INSUFFICIENT_DATA", "n": len(sub)}
            continue

        train, orth, final = chronological_split(sub)
        log(
            f"  split: train={len(train)} orth={len(orth)} final={len(final)}",
        )

        # determine midband / widerband
        def band_filter(d: pd.DataFrame, lo: float, hi: float) -> pd.DataFrame:
            return d[(d["kalshi_mid_at_t"] >= lo) & (d["kalshi_mid_at_t"] <= hi)].copy()

        train_mid = band_filter(train, 0.55, 0.80)
        orth_mid = band_filter(orth, 0.55, 0.80)
        train_wide = band_filter(train, 0.20, 0.80)
        orth_wide = band_filter(orth, 0.20, 0.80)

        mid_ok, mid_size = sample_size_ok(train_mid, orth_mid, "midband")
        log(f"  midband sample sizes: {mid_size}")

        use_band = "midband"
        train_eval = train_mid
        orth_eval = orth_mid
        if not mid_ok:
            wide_ok, wide_size = sample_size_ok(train_wide, orth_wide, "widerband")
            log(f"  widerband sample sizes: {wide_size}")
            if wide_ok:
                use_band = "widerband"
                train_eval = train_wide
                orth_eval = orth_wide
            else:
                log("  K1 NULL: midband AND widerband both fail sample-size guard")
                results["by_horizon"][h] = {
                    "status": "K1_NULL_INSUFFICIENT_SAMPLE",
                    "midband_size": mid_size,
                    "widerband_size": wide_size,
                }
                continue

        results["by_horizon"][h] = {
            "band_used": use_band,
            "n_train": int(len(train_eval)),
            "n_orth": int(len(orth_eval)),
        }

        # F4 K1b guard: count of contracts where drift is non-NaN
        if f"kalshi_price_drift_{h}" in train_eval.columns:
            drift_col = f"kalshi_price_drift_{h}"
            n_drift = int(train_eval[drift_col].notna().sum())
            results["by_horizon"][h]["n_drift_defined_train"] = n_drift
            log(f"  F4 drift defined in train: {n_drift} / {len(train_eval)}")

        # Correlation pre-screen
        feat_cols = get_horizon_feature_cols(h)
        # drop columns that are all-NaN in the train slice
        feat_cols = [
            c for c in feat_cols
            if c in train_eval.columns and train_eval[c].notna().sum() >= 10
        ]
        drops = correlation_drops(train_eval, feat_cols)
        kept_cols = [c for c in feat_cols if c not in {d["dropped"] for d in drops}]
        log(f"  correlation drops: {drops}")
        log(f"  features after corr screen: {kept_cols}")
        results["by_horizon"][h]["correlation_drops"] = drops
        results["by_horizon"][h]["features_post_corr"] = kept_cols

        # nan_pct_in_window is an audit-only column, not a feature
        if "nan_pct_in_window" in kept_cols:
            kept_cols.remove("nan_pct_in_window")
        # funding_rate_level_at_t is a baseline component for funding-delta, not a primary
        primary_features = [c for c in kept_cols if c != "funding_rate_level_at_t"]

        # Orthogonality evaluations
        per_feature: list[dict[str, Any]] = []
        for c in primary_features:
            if c == "funding_rate_delta_4h_at_t":
                # Section 3.2 amendment: baseline includes funding_rate_level_at_t
                extra = (
                    ["funding_rate_level_at_t"]
                    if "funding_rate_level_at_t" in train_eval.columns
                    and train_eval["funding_rate_level_at_t"].notna().sum() >= 10
                    else []
                )
                ev = evaluate_feature(train_eval, orth_eval, c, extra)
            else:
                ev = evaluate_feature(train_eval, orth_eval, c)
            per_feature.append(ev)
            log(
                f"  feat={c}: brier_base={ev['brier_baseline']:.5f} "
                f"brier_aug={ev['brier_augmented']:.5f} "
                f"improve={ev['brier_improvement']:.5f} "
                f"pass={ev['pass_005']} (n_test={ev['n_test']})",
            )

        results["by_horizon"][h]["per_feature"] = per_feature
        passed = [r for r in per_feature if r["pass_005"]]
        results["by_horizon"][h]["n_passed"] = len(passed)
        results["by_horizon"][h]["passed_features"] = [r["feature"] for r in passed]

        # Self-reference diagnostic for F1 (kalshi_cvd)
        cvd_col = f"kalshi_cvd_{h}"
        if cvd_col in train_eval.columns:
            diag = self_reference_diagnostic(train_eval, orth_eval, cvd_col)
            results["by_horizon"][h]["f1_self_reference_diagnostic"] = diag
            log(f"  F1 self-reference: {diag}")

    # Overall K1 check: any feature pass on any horizon midband?
    midband_passes = []
    widerband_passes = []
    for h, hr in results["by_horizon"].items():
        if not isinstance(hr, dict) or "passed_features" not in hr:
            continue
        if hr.get("band_used") == "midband":
            midband_passes.extend(
                [(h, f) for f in hr["passed_features"]],
            )
        elif hr.get("band_used") == "widerband":
            widerband_passes.extend(
                [(h, f) for f in hr["passed_features"]],
            )
    results["midband_passes"] = midband_passes
    results["widerband_passes"] = widerband_passes

    if midband_passes:
        results["k1_verdict"] = "PASS_MIDBAND"
    elif widerband_passes:
        results["k1_verdict"] = "WIDERBAND_ONLY_LIKELY_TAIL_ASYMMETRY_NULL"
    else:
        results["k1_verdict"] = "K1_NULL_NO_FEATURES_PASS"

    log(f"K1 verdict: {results['k1_verdict']}")

    out_path = DATA_DIR / "v6_orthogonality_results.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    log(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
