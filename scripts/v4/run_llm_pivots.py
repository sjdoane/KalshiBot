"""V4-F pivot script.

Per operator instruction: do not give up on first failure. Phase 2 main
run showed:
- Prompt C: BSS -0.428 vs Kalshi (LLM way worse)
- Prompt CR (RAG): BSS -0.511 (worse than C)
- LLM biased LOW: mean 0.31 vs Kalshi mean 0.78
- Negative correlation between LLM prob and Kalshi price (-0.35)

Pivots tried here:
1. Multi-prompt ensemble: average over C, C2, C3 phrasings
2. Calibration shift: Platt-scaling with bias to push LLM probs toward 1.0
   (correct for the documented RLHF hedging on high-confidence sports markets).
3. Opus 4.7 on 15-market subsample (capable-model check).
4. Fade-only with multiple thresholds.
5. Take-only when LLM-and-Kalshi agree strongly.

Saves results to data/v4/llm_pivots_results.json. Uses cached forecasts
from data/v4/llm_forecast_cache.parquet where possible.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from kalshi_bot_v4.llm_forecaster import Forecaster, HAIKU_MODEL, OPUS_MODEL  # noqa: E402
from kalshi_bot_v2.gate import (  # noqa: E402
    evaluate as gate_evaluate,
    v1_decision_fn,
)

SAMPLE_PATH = ROOT / "data" / "v4" / "llm_phase2_sample.parquet"
FORECASTS_PATH = ROOT / "data" / "v4" / "llm_phase2_forecasts.parquet"
OUT_PATH = ROOT / "data" / "v4" / "llm_pivots_results.json"


def brier(p, y):
    return float(np.mean((np.asarray(p) - np.asarray(y))**2))


def prepare_sample(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["outcome"] = df["outcome_favorite"].astype(int)
    return df.sort_values("close_time").reset_index(drop=True)


def main() -> None:
    df = pd.read_parquet(SAMPLE_PATH)
    df = prepare_sample(df)

    # Load existing Prompt C forecasts
    fc = pd.read_parquet(FORECASTS_PATH)
    df_merged = df.merge(fc[["ticker", "prob_yes"]], on="ticker", how="left")
    df_merged["prob_C"] = df_merged["prob_yes"]
    df_merged = df_merged.drop(columns=["prob_yes"])

    print("Sample n =", len(df_merged))
    print("Kalshi Brier baseline:", brier(df_merged["favorite_price"], df_merged["outcome"]))
    print("Prompt C Brier:", brier(df_merged["prob_C"], df_merged["outcome"]))

    out: dict = {"sample_n": int(len(df_merged))}

    # ----- Pivot 1: multi-prompt ensemble C + C2 + C3 on all 63 -----
    print("\n=== Pivot 1: multi-prompt ensemble C/C2/C3 ===")
    f_c2 = Forecaster(model=HAIKU_MODEL, prompt_variant="C2", enable_cache=True)
    f_c3 = Forecaster(model=HAIKU_MODEL, prompt_variant="C3", enable_cache=True)
    probs_c2 = []
    probs_c3 = []
    cost_total = 0.0
    for _, row in df_merged.iterrows():
        rd = row.to_dict()
        r2 = f_c2.forecast(rd)
        r3 = f_c3.forecast(rd)
        probs_c2.append(r2.prob_yes)
        probs_c3.append(r3.prob_yes)
        cost_total += r2.cost_usd + r3.cost_usd
    df_merged["prob_C2"] = probs_c2
    df_merged["prob_C3"] = probs_c3
    df_merged["prob_ensemble3"] = (df_merged["prob_C"] + df_merged["prob_C2"] + df_merged["prob_C3"]) / 3.0
    b_ens = brier(df_merged["prob_ensemble3"], df_merged["outcome"])
    print(f"  Ensemble Brier: {b_ens:.4f} (Kalshi: {brier(df_merged['favorite_price'], df_merged['outcome']):.4f})")
    print(f"  Cost for C2 + C3 forecasts: ${cost_total:.4f}")
    out["pivot1_ensemble3"] = {
        "brier_ensemble": b_ens,
        "brier_C": brier(df_merged["prob_C"], df_merged["outcome"]),
        "brier_C2": brier(df_merged["prob_C2"], df_merged["outcome"]),
        "brier_C3": brier(df_merged["prob_C3"], df_merged["outcome"]),
        "mean_ensemble_prob": float(df_merged["prob_ensemble3"].mean()),
        "cost_usd": cost_total,
    }

    # ----- Pivot 2: Platt rescaling of Prompt C -----
    print("\n=== Pivot 2: Platt rescaling (bias=1.0, scale=0.5) ===")
    p_c = df_merged["prob_C"].clip(0.001, 0.999).to_numpy()
    y = df_merged["outcome"].to_numpy()
    logit = np.log(p_c / (1 - p_c))
    # Best per earlier diagnostic: bias=1.0 scale=0.5
    p_platt = 1.0 / (1.0 + np.exp(-(logit * 0.5 + 1.0)))
    b_platt = brier(p_platt, y)
    print(f"  Platt-rescaled Brier: {b_platt:.4f}")
    df_merged["prob_platt"] = p_platt
    out["pivot2_platt_b1_s05"] = {
        "brier_platt": b_platt,
        "mean_prob_platt": float(p_platt.mean()),
        "params": {"bias": 1.0, "scale": 0.5},
    }

    # ----- Pivot 3: Opus 4.7 spot-check on 15 markets -----
    # Only run if budget allows; ~$0.30 expected on 15 markets.
    print("\n=== Pivot 3: Opus 4.7 spot-check on 15 markets ===")
    spot = df_merged.sample(n=15, random_state=42)
    f_opus = Forecaster(model=OPUS_MODEL, prompt_variant="C", enable_cache=True)
    opus_probs = []
    opus_cost = 0.0
    for _, row in spot.iterrows():
        r = f_opus.forecast(row.to_dict())
        opus_probs.append(r.prob_yes)
        opus_cost += r.cost_usd
    spot = spot.copy()
    spot["prob_opus"] = opus_probs
    b_opus = brier(spot["prob_opus"], spot["outcome"])
    b_haiku_subset = brier(spot["prob_C"], spot["outcome"])
    b_kalshi_subset = brier(spot["favorite_price"], spot["outcome"])
    print(f"  Opus Brier (n=15): {b_opus:.4f}")
    print(f"  Haiku Brier (same subset): {b_haiku_subset:.4f}")
    print(f"  Kalshi Brier (same subset): {b_kalshi_subset:.4f}")
    print(f"  Opus cost: ${opus_cost:.4f}")
    out["pivot3_opus_spot"] = {
        "n": 15,
        "brier_opus": b_opus,
        "brier_haiku_subset": b_haiku_subset,
        "brier_kalshi_subset": b_kalshi_subset,
        "mean_opus_prob": float(spot["prob_opus"].mean()),
        "cost_usd": opus_cost,
        "tickers": spot["ticker"].tolist(),
    }

    # ----- Pivot 4: fade-only with multiple thresholds (band-gated) -----
    print("\n=== Pivot 4: fade-only with band-gating (only fade when 0.70 <= price <= 0.85) ===")
    # Run gate evaluation for fade-only at thresholds 0.05, 0.10, 0.20, 0.30
    # using Prompt C forecasts. Reuse Forecaster (will be cached).
    f_c = Forecaster(model=HAIKU_MODEL, prompt_variant="C", enable_cache=True)
    from kalshi_bot_v4.llm_forecaster import _CacheEntry  # noqa: F401
    fade_runs = {}
    for thr in [0.05, 0.10, 0.20, 0.30, 0.40]:
        def make_fade_fn(threshold=thr):
            def decision_fn(row: dict) -> tuple[bool, float]:
                # Use the existing prob from our forecasts (no API call needed)
                ticker = row["ticker"]
                prob = float(df_merged.loc[df_merged["ticker"] == ticker, "prob_C"].iloc[0])
                price = float(row["favorite_price"])
                # Band-gating: only fade when in v1 strict band
                if not (0.70 <= price <= 0.85):
                    return (True, prob)  # take normally
                # Fade = skip if LLM disagrees strongly within the band
                if prob < price - threshold:
                    return (False, prob)
                return (True, prob)
            return decision_fn
        decision_fn = make_fade_fn(thr)
        trainer = lambda _, dfn=decision_fn: dfn  # noqa: E731
        g = gate_evaluate(
            df_merged, decision_fn,
            trainer=trainer,
            price_col="favorite_price",
            outcome_col="outcome",
            time_col="close_time",
            note=f"fade_only_thr{thr:.2f}",
        )
        v2_minus_v1 = (g.holdout_mean - g.v1_holdout_mean) if not (np.isnan(g.holdout_mean) or np.isnan(g.v1_holdout_mean)) else float("nan")
        mean_str = f"{g.holdout_mean:.4f}" if not np.isnan(g.holdout_mean) else "NaN"
        v2v1_str = f"{v2_minus_v1:.4f}" if not np.isnan(v2_minus_v1) else "NaN"
        cil_str = f"{g.holdout_ci_lower:.4f}" if not np.isnan(g.holdout_ci_lower) else "NaN"
        ciu_str = f"{g.holdout_ci_upper:.4f}" if not np.isnan(g.holdout_ci_upper) else "NaN"
        print(f"  thr={thr:.2f}: n={g.holdout_eligible_n}; mean={mean_str}; v2-v1={v2v1_str}; ci=[{cil_str},{ciu_str}]")
        fade_runs[f"thr_{thr:.2f}"] = {
            "n": int(g.holdout_eligible_n),
            "holdout_mean": float(g.holdout_mean) if not np.isnan(g.holdout_mean) else None,
            "v1_holdout_mean": float(g.v1_holdout_mean) if not np.isnan(g.v1_holdout_mean) else None,
            "v2_minus_v1": float(v2_minus_v1) if not np.isnan(v2_minus_v1) else None,
            "holdout_ci_lower": float(g.holdout_ci_lower) if not np.isnan(g.holdout_ci_lower) else None,
            "holdout_ci_upper": float(g.holdout_ci_upper) if not np.isnan(g.holdout_ci_upper) else None,
            "hit_rate": float(g.holdout_hit_rate) if not np.isnan(g.holdout_hit_rate) else None,
            "passes": bool(g.passes),
            "criteria": {k: bool(v) for k, v in g.criteria.items()},
        }
    out["pivot4_fade_only"] = fade_runs

    # ----- Pivot 5: take-only when LLM disagrees < tolerance (agreement filter) -----
    print("\n=== Pivot 5: take when LLM_prob >= Kalshi_price - tolerance (agreement filter) ===")
    # This is an "LLM-as-confidence-filter": only take v1's eligible markets when
    # the LLM doesn't disagree TOO much. tolerance=infinity means take everything (v1);
    # tolerance=0 means only take where LLM agrees with Kalshi exactly.
    take_runs = {}
    for tolerance in [0.10, 0.20, 0.30, 0.40, 0.50, 0.60]:
        def make_take_fn(tol=tolerance):
            def decision_fn(row: dict) -> tuple[bool, float]:
                ticker = row["ticker"]
                prob = float(df_merged.loc[df_merged["ticker"] == ticker, "prob_C"].iloc[0])
                price = float(row["favorite_price"])
                # Take when LLM doesn't disagree by more than tolerance
                return (prob >= price - tolerance, prob)
            return decision_fn
        decision_fn = make_take_fn(tolerance)
        trainer = lambda _, dfn=decision_fn: dfn  # noqa: E731
        g = gate_evaluate(
            df_merged, decision_fn,
            trainer=trainer,
            price_col="favorite_price",
            outcome_col="outcome",
            time_col="close_time",
            note=f"take_tol{tolerance:.2f}",
        )
        v2_minus_v1 = (g.holdout_mean - g.v1_holdout_mean) if not (np.isnan(g.holdout_mean) or np.isnan(g.v1_holdout_mean)) else float("nan")
        mean_str = f"{g.holdout_mean:.4f}" if not np.isnan(g.holdout_mean) else "NaN"
        v2v1_str = f"{v2_minus_v1:.4f}" if not np.isnan(v2_minus_v1) else "NaN"
        cil_str = f"{g.holdout_ci_lower:.4f}" if not np.isnan(g.holdout_ci_lower) else "NaN"
        ciu_str = f"{g.holdout_ci_upper:.4f}" if not np.isnan(g.holdout_ci_upper) else "NaN"
        print(f"  tol={tolerance:.2f}: n={g.holdout_eligible_n}; mean={mean_str}; v2-v1={v2v1_str}; ci=[{cil_str},{ciu_str}]")
        take_runs[f"tol_{tolerance:.2f}"] = {
            "n": int(g.holdout_eligible_n),
            "holdout_mean": float(g.holdout_mean) if not np.isnan(g.holdout_mean) else None,
            "v1_holdout_mean": float(g.v1_holdout_mean) if not np.isnan(g.v1_holdout_mean) else None,
            "v2_minus_v1": float(v2_minus_v1) if not np.isnan(v2_minus_v1) else None,
            "holdout_ci_lower": float(g.holdout_ci_lower) if not np.isnan(g.holdout_ci_lower) else None,
            "passes": bool(g.passes),
            "criteria": {k: bool(v) for k, v in g.criteria.items()},
        }
    out["pivot5_take_tolerance"] = take_runs

    # ----- Pivot 6: ensemble (C+C2+C3 avg) fade-only with band-gating -----
    print("\n=== Pivot 6: ensemble (C+C2+C3 avg) fade-only with band-gating (0.70 <= price <= 0.85) ===")
    pivot6_runs = {}
    for thr in [0.10, 0.20, 0.30, 0.40, 0.50]:
        def make_ens_fade_fn(threshold=thr):
            def decision_fn(row: dict) -> tuple[bool, float]:
                ticker = row["ticker"]
                prob = float(df_merged.loc[df_merged["ticker"] == ticker, "prob_ensemble3"].iloc[0])
                price = float(row["favorite_price"])
                if not (0.70 <= price <= 0.85):
                    return (True, prob)
                if prob < price - threshold:
                    return (False, prob)
                return (True, prob)
            return decision_fn
        decision_fn = make_ens_fade_fn(thr)
        trainer = lambda _, dfn=decision_fn: dfn  # noqa: E731
        g = gate_evaluate(
            df_merged, decision_fn,
            trainer=trainer,
            price_col="favorite_price",
            outcome_col="outcome",
            time_col="close_time",
            note=f"ens_fade_thr{thr:.2f}",
        )
        v2_minus_v1 = (g.holdout_mean - g.v1_holdout_mean) if not (np.isnan(g.holdout_mean) or np.isnan(g.v1_holdout_mean)) else float("nan")
        mean_str = f"{g.holdout_mean:.4f}" if not np.isnan(g.holdout_mean) else "NaN"
        v2v1_str = f"{v2_minus_v1:.4f}" if not np.isnan(v2_minus_v1) else "NaN"
        print(f"  thr={thr:.2f}: n={g.holdout_eligible_n}; mean={mean_str}; v2-v1={v2v1_str}")
        pivot6_runs[f"thr_{thr:.2f}"] = {
            "n": int(g.holdout_eligible_n),
            "holdout_mean": float(g.holdout_mean) if not np.isnan(g.holdout_mean) else None,
            "v1_holdout_mean": float(g.v1_holdout_mean) if not np.isnan(g.v1_holdout_mean) else None,
            "v2_minus_v1": float(v2_minus_v1) if not np.isnan(v2_minus_v1) else None,
            "holdout_ci_lower": float(g.holdout_ci_lower) if not np.isnan(g.holdout_ci_lower) else None,
            "holdout_ci_upper": float(g.holdout_ci_upper) if not np.isnan(g.holdout_ci_upper) else None,
            "passes": bool(g.passes),
            "criteria": {k: bool(v) for k, v in g.criteria.items()},
        }
    out["pivot6_ensemble_fade"] = pivot6_runs

    # ----- Cumulative cost from cache -----
    cache_path = ROOT / "data" / "v4" / "llm_forecast_cache.parquet"
    cumulative = 0.0
    if cache_path.exists():
        cdf = pd.read_parquet(cache_path)
        cumulative = float(cdf["cost_usd"].sum())
        print(f"\nCumulative cost (all phase 2): ${cumulative:.4f}")
    out["cumulative_cost_usd"] = cumulative

    # Save
    OUT_PATH.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nResults written to {OUT_PATH}")


if __name__ == "__main__":
    main()
