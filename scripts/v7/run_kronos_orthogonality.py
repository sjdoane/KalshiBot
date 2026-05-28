"""Run v6 Section 3 orthogonality test with kronos_p_yes as the candidate.

Per research/v7/03-kronos-methodology.md Section 6.

Pipeline:
1. Load data/v6/v6_master.parquet (the row-level target / mid).
2. Load data/v7/kronos_predictions.parquet (kronos_p_yes per ticker, horizon).
3. Join on (ticker, horizon_min) -> per-row dataset with outcome_yes,
   kalshi_mid_at_t, time_since_last_trade_at_t, kronos_p_yes.
4. Apply midband filter and chronological 60/25/15 split with 24h purge.
5. Baseline logit: outcome_yes ~ logit(kalshi_mid_at_t).
   Augmented logit: outcome_yes ~ logit(kalshi_mid_at_t + kronos_p_yes).
6. Compute Brier improvement on orthogonality holdout.
7. Cluster-bootstrap 5000 days (or n_days resamples) of the improvement.
8. Self-reference diagnostic: split by time_since_last_trade < 5 min.

Output:
- data/v7/kronos_orthogonality.json (per Section 15 of methodology).
- research/v7/05-kronos-results.md (markdown writeup; appended by separate step
  if needed).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

V6_MASTER = REPO_ROOT / "data" / "v6" / "v6_master.parquet"
KRONOS_PRED = REPO_ROOT / "data" / "v7" / "kronos_predictions.parquet"
COINBASE_V6 = REPO_ROOT / "data" / "v6" / "cache" / "coinbase_1m.parquet"
COINBASE_V7 = REPO_ROOT / "data" / "v7" / "cache" / "coinbase_1m_v7.parquet"
OUT_JSON = REPO_ROOT / "data" / "v7" / "kronos_orthogonality.json"
SEED = 42


def log(msg: str) -> None:
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] [orth] {msg}", flush=True)


def chronological_split(
    df: pd.DataFrame,
    train_frac: float = 0.60,
    orth_frac: float = 0.25,
    purge_hours: int = 24,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Same pattern as v6 scripts/v6/run_v6_orthogonality.chronological_split."""
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


def fit_brier_on_same_subset(
    train: pd.DataFrame,
    test: pd.DataFrame,
    aug_cols: list[str],
    base_cols: list[str],
) -> dict[str, Any]:
    """Like-for-like baseline vs augmented on the same dropna(aug_cols) subset.
    Mirror of v6 scripts/v6/run_v6_orthogonality.fit_brier_on_same_subset.
    """
    sub_train = train.dropna(subset=aug_cols + ["outcome_yes"]).copy()
    sub_test = test.dropna(subset=aug_cols + ["outcome_yes"]).copy()
    if (
        len(sub_train) < 20
        or sub_train["outcome_yes"].nunique() < 2
        or len(sub_test) < 5
    ):
        return {
            "brier_baseline": float("nan"),
            "brier_augmented": float("nan"),
            "improvement": float("nan"),
            "n_train": int(len(sub_train)),
            "n_test": int(len(sub_test)),
            "note": "insufficient data",
        }
    y_train = sub_train["outcome_yes"].astype(int).to_numpy()
    y_test = sub_test["outcome_yes"].astype(int).to_numpy()
    Xb_train = sub_train[base_cols].astype(float).to_numpy()
    Xb_test = sub_test[base_cols].astype(float).to_numpy()
    base_model = LogisticRegression(
        C=10.0, max_iter=500, random_state=SEED,
    ).fit(Xb_train, y_train)
    p_base = base_model.predict_proba(Xb_test)[:, 1]
    brier_base = brier_score_loss(y_test, p_base)

    Xa_train = sub_train[aug_cols].astype(float).to_numpy()
    Xa_test = sub_test[aug_cols].astype(float).to_numpy()
    aug_model = LogisticRegression(
        C=10.0, max_iter=500, random_state=SEED,
    ).fit(Xa_train, y_train)
    p_aug = aug_model.predict_proba(Xa_test)[:, 1]
    brier_aug = brier_score_loss(y_test, p_aug)
    return {
        "brier_baseline": float(brier_base),
        "brier_augmented": float(brier_aug),
        "improvement": float(brier_base - brier_aug),
        "n_train": int(len(sub_train)),
        "n_test": int(len(sub_test)),
        "p_base": p_base,
        "p_aug": p_aug,
        "y_test": y_test,
        "test_close_time": sub_test["close_time"].to_numpy(),
    }


def cluster_bootstrap_improvement(
    test_close_time: np.ndarray,
    p_base: np.ndarray,
    p_aug: np.ndarray,
    y: np.ndarray,
    n_iter: int = 5000,
    seed: int = SEED,
) -> dict[str, float]:
    """Cluster-bootstrap by close_time.date(). Returns mean, 2.5th, 97.5th of
    the bootstrap distribution of (Brier_base - Brier_aug).
    """
    if len(y) == 0:
        return {
            "mean": float("nan"),
            "p_2.5": float("nan"),
            "p_97.5": float("nan"),
        }
    dates = pd.to_datetime(test_close_time, utc=True).date
    df = pd.DataFrame({
        "date": dates, "p_base": p_base, "p_aug": p_aug, "y": y,
    })
    unique_dates = sorted(df["date"].unique())
    n_days = len(unique_dates)
    if n_days < 5:
        return {
            "mean": float(np.mean(p_base - p_aug)),
            "p_2.5": float("nan"),
            "p_97.5": float("nan"),
            "n_days": n_days,
        }
    rng = np.random.default_rng(seed)
    date_to_idx = {d: df[df["date"] == d].index.to_numpy() for d in unique_dates}
    improvements = np.empty(n_iter)
    for i in range(n_iter):
        sampled_dates = rng.choice(unique_dates, size=n_days, replace=True)
        idxs = np.concatenate([date_to_idx[d] for d in sampled_dates])
        b_base = brier_score_loss(df["y"].iloc[idxs], df["p_base"].iloc[idxs])
        b_aug = brier_score_loss(df["y"].iloc[idxs], df["p_aug"].iloc[idxs])
        improvements[i] = b_base - b_aug
    return {
        "mean": float(np.mean(improvements)),
        "p_2.5": float(np.percentile(improvements, 2.5)),
        "p_97.5": float(np.percentile(improvements, 97.5)),
        "n_days": int(n_days),
    }


def evaluate_horizon(
    df: pd.DataFrame,
    horizon: int,
    band: str,
    do_bootstrap: bool = True,
    do_naive_baselines: bool = True,
) -> dict[str, Any]:
    """Evaluate orthogonality for one horizon.

    Returns dict with band_used, n_train, n_orth, point estimates, CI, and
    self-reference diagnostic. If do_naive_baselines, also compare against
    spot_minus_strike and naive_p_yes diagnostics (D-A in 05-kronos-results.md).
    """
    result: dict[str, Any] = {"horizon_min": horizon}
    band_filters = {
        "midband": (0.55, 0.80),
        "widerband": (0.55, 0.95),
    }
    sub = df[df["horizon_min"] == horizon].copy()
    result["n_total_join"] = int(len(sub))
    if len(sub) < 20:
        result["status"] = "INSUFFICIENT_DATA"
        return result

    train, orth, final = chronological_split(sub)
    result["split_full"] = {
        "n_train": int(len(train)),
        "n_orth": int(len(orth)),
        "n_final": int(len(final)),
        "train_close_max": str(train["close_time"].max()) if len(train) else None,
        "orth_close_max": str(orth["close_time"].max()) if len(orth) else None,
    }

    # Filter to band
    lo, hi = band_filters[band]
    train_b = train[
        (train["kalshi_mid_at_t"] >= lo) & (train["kalshi_mid_at_t"] <= hi)
    ].copy()
    orth_b = orth[
        (orth["kalshi_mid_at_t"] >= lo) & (orth["kalshi_mid_at_t"] <= hi)
    ].copy()
    final_b = final[
        (final["kalshi_mid_at_t"] >= lo) & (final["kalshi_mid_at_t"] <= hi)
    ].copy()
    result["band_used"] = band
    result["n_train_band"] = int(len(train_b))
    result["n_orth_band"] = int(len(orth_b))
    result["n_final_band"] = int(len(final_b))

    train_yes = int((train_b["outcome_yes"] == 1).sum())
    train_no = int((train_b["outcome_yes"] == 0).sum())
    orth_yes = int((orth_b["outcome_yes"] == 1).sum())
    orth_no = int((orth_b["outcome_yes"] == 0).sum())
    result["yes_no"] = {
        "train_yes": train_yes, "train_no": train_no,
        "orth_yes": orth_yes, "orth_no": orth_no,
    }
    if train_yes < 50 or train_no < 50 or orth_yes < 30 or orth_no < 30:
        result["status"] = "SAMPLE_SIZE_GUARD_FAIL"
        return result

    # Standard orthogonality test
    base_cols = ["kalshi_mid_at_t"]
    aug_cols = ["kalshi_mid_at_t", "kronos_p_yes"]
    eval_res = fit_brier_on_same_subset(train_b, orth_b, aug_cols, base_cols)
    result["brier_baseline"] = eval_res["brier_baseline"]
    result["brier_augmented"] = eval_res["brier_augmented"]
    result["improvement"] = eval_res["improvement"]
    result["n_train_used"] = eval_res["n_train"]
    result["n_test_used"] = eval_res["n_test"]
    result["pass_005"] = bool(
        eval_res["improvement"] >= 0.005
        if not np.isnan(eval_res["improvement"])
        else False,
    )
    log(f"  T-{horizon} {band}: brier_base={eval_res['brier_baseline']:.5f} "
        f"brier_aug={eval_res['brier_augmented']:.5f} "
        f"improvement={eval_res['improvement']:.5f} (n_test={eval_res['n_test']})")

    if do_bootstrap and "p_base" in eval_res:
        ci = cluster_bootstrap_improvement(
            eval_res["test_close_time"],
            eval_res["p_base"],
            eval_res["p_aug"],
            eval_res["y_test"],
            n_iter=5000,
            seed=SEED,
        )
        result["cluster_bootstrap_ci"] = ci
        log(f"  T-{horizon} CI: mean={ci['mean']:.5f} "
            f"[{ci['p_2.5']:.5f}, {ci['p_97.5']:.5f}] over n_days={ci.get('n_days')}")

    # ALSO evaluate on FINAL holdout (untouched) for honest reporting
    if len(final_b) >= 30:
        final_yes = int((final_b["outcome_yes"] == 1).sum())
        final_no = int((final_b["outcome_yes"] == 0).sum())
        if final_yes >= 5 and final_no >= 5:
            fres = fit_brier_on_same_subset(
                train_b, final_b, aug_cols, base_cols,
            )
            result["final_holdout"] = {
                "n_test": fres["n_test"],
                "brier_baseline": fres["brier_baseline"],
                "brier_augmented": fres["brier_augmented"],
                "improvement": fres["improvement"],
                "final_yes": final_yes,
                "final_no": final_no,
            }
            log(f"  T-{horizon} FINAL holdout: improvement={fres['improvement']:.5f} "
                f"(n_test={fres['n_test']})")

    # Self-reference diagnostic
    if "time_since_last_trade_at_t" in orth_b.columns:
        sub_diag: dict[str, Any] = {}
        for name, mask in (
            ("fresh", orth_b["time_since_last_trade_at_t"] < 5.0),
            ("stale", orth_b["time_since_last_trade_at_t"] >= 5.0),
        ):
            subset = orth_b[mask].copy()
            if len(subset) < 20:
                sub_diag[name] = {"n": len(subset), "note": "n_too_small"}
                continue
            sr = fit_brier_on_same_subset(
                train_b, subset, aug_cols, base_cols,
            )
            sub_diag[name] = {
                "n": int(sr["n_test"]),
                "improvement": sr["improvement"],
                "brier_base": sr["brier_baseline"],
                "brier_aug": sr["brier_augmented"],
            }
        result["self_reference"] = sub_diag
        log(f"  T-{horizon} self-ref: {sub_diag}")

    # Naive baselines: compare Kronos vs the simplest "current spot vs strike"
    # features. This is the D-A diagnostic mentioned in the results doc.
    if do_naive_baselines and "naive_p_yes" in train_b.columns:
        naive_results: dict[str, Any] = {}
        for ncol in ("naive_p_yes", "spot_minus_strike"):
            if ncol not in train_b.columns:
                continue
            n_aug = ["kalshi_mid_at_t", ncol]
            nres = fit_brier_on_same_subset(train_b, orth_b, n_aug, base_cols)
            naive_results[ncol] = {
                "improvement": nres["improvement"],
                "brier_baseline": nres["brier_baseline"],
                "brier_augmented": nres["brier_augmented"],
                "n_test": nres["n_test"],
            }
            log(f"  T-{horizon} {ncol}: improvement={nres['improvement']:.5f}")
        # Also: kronos OVER spot baseline (mid + naive_p_yes + kronos_p_yes vs mid + naive_p_yes)
        if "naive_p_yes" in train_b.columns:
            base2 = ["kalshi_mid_at_t", "naive_p_yes"]
            aug2 = ["kalshi_mid_at_t", "naive_p_yes", "kronos_p_yes"]
            kr_over_naive = fit_brier_on_same_subset(train_b, orth_b, aug2, base2)
            naive_results["kronos_over_naive"] = {
                "improvement": kr_over_naive["improvement"],
                "brier_baseline": kr_over_naive["brier_baseline"],
                "brier_augmented": kr_over_naive["brier_augmented"],
                "n_test": kr_over_naive["n_test"],
                "note": "augmented adds kronos_p_yes; baseline already has mid + naive_p_yes",
            }
            log(f"  T-{horizon} kronos_OVER_naive: improvement={kr_over_naive['improvement']:.5f}")
        result["naive_baselines"] = naive_results

    return result


def add_naive_features(
    j: pd.DataFrame,
    coinbase: pd.DataFrame,
) -> pd.DataFrame:
    """Add naive_p_yes (Normal-CDF using current Coinbase spot at t and Kronos sigma)
    and spot_minus_strike (raw spot - strike) for the spot-baseline diagnostic.
    """
    import math
    from scipy.stats import norm
    from kalshi_bot_v7.kronos_features import parse_strike

    # build spot lookup: for each unique t, find last coinbase close <= t
    out = j.copy()
    naive_ps: list[float] = []
    spot_minus_strikes: list[float] = []
    for _, row in out.iterrows():
        t = pd.Timestamp(row["t"])
        try:
            strike = parse_strike(row["ticker"])
        except ValueError:
            naive_ps.append(float("nan"))
            spot_minus_strikes.append(float("nan"))
            continue
        sigma = row.get("kronos_sigma_close", float("nan"))
        mask = coinbase["time"] <= t
        if mask.sum() == 0:
            naive_ps.append(float("nan"))
            spot_minus_strikes.append(float("nan"))
            continue
        spot = float(coinbase.loc[mask, "close"].iloc[-1])
        spot_minus_strikes.append(spot - strike)
        if not (sigma == sigma) or sigma <= 0 or spot <= 0 or strike <= 0:
            naive_ps.append(float("nan"))
            continue
        z = (math.log(strike) - math.log(spot)) / sigma
        p = float(np.clip(1.0 - norm.cdf(z), 1e-3, 1.0 - 1e-3))
        naive_ps.append(p)
    out["naive_p_yes"] = naive_ps
    out["spot_minus_strike"] = spot_minus_strikes
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bands", nargs="+", default=["midband"],
                        help="Bands to evaluate")
    parser.add_argument("--horizons", type=int, nargs="+", default=[30, 15])
    parser.add_argument("--no-bootstrap", action="store_true",
                        help="Skip cluster bootstrap")
    args = parser.parse_args()

    if not KRONOS_PRED.exists():
        log(f"missing {KRONOS_PRED}; run scripts.v7.run_kronos first")
        return 1
    master = pd.read_parquet(V6_MASTER)
    preds = pd.read_parquet(KRONOS_PRED)
    log(f"master: {len(master)}, kronos_preds: {len(preds)}")

    # Filter to ok-status predictions
    preds_ok = preds[preds["status"] == "ok"].copy()
    log(f"  ok preds: {len(preds_ok)}")

    # Join
    joined = master.merge(
        preds_ok[[
            "ticker", "horizon_min", "kronos_p_yes",
            "kronos_mean_close", "kronos_sigma_close",
        ]],
        on=["ticker", "horizon_min"], how="inner",
    )
    log(f"  joined: {len(joined)}")

    # Load Coinbase 1m (v6 + v7 union) for naive baselines
    cb_v6 = pd.read_parquet(COINBASE_V6)
    cb_v6["time"] = pd.to_datetime(cb_v6["time"], utc=True)
    if COINBASE_V7.exists():
        cb_v7 = pd.read_parquet(COINBASE_V7)
        cb_v7["time"] = pd.to_datetime(cb_v7["time"], utc=True)
        coinbase = pd.concat([cb_v6, cb_v7], ignore_index=True)
        coinbase = (
            coinbase.drop_duplicates("time").sort_values("time").reset_index(drop=True)
        )
    else:
        coinbase = cb_v6
    log(f"  coinbase union: {len(coinbase)} bars")
    joined = add_naive_features(joined, coinbase)
    log(f"  added naive_p_yes ({joined['naive_p_yes'].notna().sum()} non-NaN) and "
        f"spot_minus_strike ({joined['spot_minus_strike'].notna().sum()} non-NaN)")

    all_results: dict[str, Any] = {
        "run_timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "kronos_model": "NeoQuasar/Kronos-base",
        "tokenizer": "NeoQuasar/Kronos-Tokenizer-base",
        "n_master": int(len(master)),
        "n_kronos_pred": int(len(preds)),
        "n_kronos_ok": int(len(preds_ok)),
        "n_joined": int(len(joined)),
        "by_band_horizon": {},
    }

    for band in args.bands:
        all_results["by_band_horizon"][band] = {}
        for h in args.horizons:
            res = evaluate_horizon(
                joined, h, band, do_bootstrap=not args.no_bootstrap,
            )
            all_results["by_band_horizon"][band][str(h)] = res

    # Overall verdict
    midband_pass: list[tuple[str, int]] = []
    widerband_pass: list[tuple[str, int]] = []
    for band, bres in all_results["by_band_horizon"].items():
        for h, hres in bres.items():
            if hres.get("pass_005"):
                if band == "midband":
                    midband_pass.append((band, int(h)))
                else:
                    widerband_pass.append((band, int(h)))
    all_results["midband_passes"] = midband_pass
    all_results["widerband_passes"] = widerband_pass
    if midband_pass:
        all_results["verdict"] = "PASS_MIDBAND"
    elif widerband_pass:
        all_results["verdict"] = "PASS_WIDERBAND_ONLY"
    else:
        all_results["verdict"] = "NULL_KA_NO_FEATURES_PASS"
    log(f"verdict: {all_results['verdict']}")

    OUT_JSON.write_text(json.dumps(all_results, indent=2, default=str))
    log(f"wrote {OUT_JSON}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
