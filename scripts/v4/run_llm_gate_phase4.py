"""V4-G Phase 4 gate runner (corrected WINDOW_START).

Reruns V4-F's LLM gate evaluation at the corrected Anthropic Haiku 4.5
cutoff (Jul 2025, with Aug 2025 buffer). Sample size n=200 strict
v1-eligible markets (vs V4-F's n=19 strict).

Reuses:
- src/kalshi_bot_v4/llm_forecaster.py (Forecaster, Prompt C, cache)
- src/kalshi_bot_v2/gate.py (locked C1-C6 gate from v2)

Outputs:
- data/v4/llm_phase4_forecasts.parquet (per-market LLM forecasts)
- data/v4/llm_phase4_gate_results.json (full gate + calibration + sanity)

Critic-flagged: this is the leak-free fair comparison of LLM-vs-v1 on
v1's actual domain (strict band [0.70, 0.95] x [30, 180]d), which V4-F
could not run because its assumed cutoff (Jan 2026) collapsed the sample
to n=19.

Read-only on Kalshi side. Anthropic SDK only.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from kalshi_bot_v2.gate import (  # noqa: E402
    GateResult,
    TradeDecisionFn,
    evaluate as gate_evaluate,
    v1_decision_fn,
)
from kalshi_bot_v4.llm_forecaster import (  # noqa: E402
    Forecaster,
    HAIKU_MODEL,
)

SAMPLE_PATH = PROJECT_ROOT / "data" / "v4" / "llm_phase4_sample.parquet"
PILOT_PATH = PROJECT_ROOT / "data" / "v4" / "llm_pilot_sample.parquet"
RESULTS_PATH = PROJECT_ROOT / "data" / "v4" / "llm_phase4_gate_results.json"
FORECASTS_PATH = PROJECT_ROOT / "data" / "v4" / "llm_phase4_forecasts.parquet"

V4_BUDGET_USD = 10.0  # Phase 4 brief cap


def brier(probs: np.ndarray, outcomes: np.ndarray) -> float:
    return float(np.mean((probs - outcomes) ** 2))


def bss(probs_model: np.ndarray, probs_baseline: np.ndarray, outcomes: np.ndarray) -> float:
    bm = brier(probs_model, outcomes)
    bb = brier(probs_baseline, outcomes)
    return float(1.0 - bm / bb) if bb > 0 else float("nan")


def ece(probs: np.ndarray, outcomes: np.ndarray, n_bins: int = 10) -> float:
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    inds = np.digitize(probs, bins) - 1
    total = len(probs)
    e = 0.0
    for b in range(n_bins):
        mask = inds == b
        n_b = int(mask.sum())
        if n_b == 0:
            continue
        avg_p = float(probs[mask].mean())
        avg_y = float(outcomes[mask].mean())
        e += (n_b / total) * abs(avg_p - avg_y)
    return float(e)


def bootstrap_brier_diff_ci(
    probs_model: np.ndarray,
    probs_baseline: np.ndarray,
    outcomes: np.ndarray,
    n_resamples: int = 5000,
    seed: int = 42,
) -> tuple[float, float, float]:
    rng = np.random.default_rng(seed)
    n = len(outcomes)
    diffs = []
    for _ in range(n_resamples):
        idx = rng.integers(0, n, size=n)
        bm = float(np.mean((probs_model[idx] - outcomes[idx]) ** 2))
        bb = float(np.mean((probs_baseline[idx] - outcomes[idx]) ** 2))
        diffs.append(bb - bm)
    arr = np.array(diffs)
    return float(np.mean(arr)), float(np.quantile(arr, 0.025)), float(np.quantile(arr, 0.975))


def make_llm_decision_fn(
    forecaster: Forecaster,
    threshold_margin: float = 0.0,
    fade_only: bool = False,
    fade_threshold: float = 0.10,
    price_low: float = 0.70,
    price_high: float = 0.85,
):
    def llm_decision_fn(row: dict) -> tuple[bool, float]:
        result = forecaster.forecast(row)
        prob = result.prob_yes
        favorite_price = float(row.get("favorite_price", 0.0))
        if fade_only:
            if price_low <= favorite_price <= price_high and prob < favorite_price - fade_threshold:
                return (False, prob)
            return (True, prob)
        return (prob > favorite_price + threshold_margin, prob)
    return llm_decision_fn


def llm_trainer_factory(forecaster: Forecaster, threshold_margin: float = 0.0):
    """Stateless trainer (LLM is fixed across folds).

    Cutoff discipline is upheld by sample design: all rows close after
    the LLM's training cutoff (Jul 2025 + buffer = Aug 2025 WINDOW_START).
    """
    def llm_trainer(fold_train_df: pd.DataFrame) -> TradeDecisionFn:
        return make_llm_decision_fn(forecaster, threshold_margin=threshold_margin)
    return llm_trainer


def prepare_sample(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["outcome"] = df["outcome_favorite"].astype(int)
    df = df.sort_values("close_time").reset_index(drop=True)
    return df


def run_g1(df: pd.DataFrame) -> GateResult:
    return gate_evaluate(
        df, v1_decision_fn,
        trainer=None,
        price_col="favorite_price",
        outcome_col="outcome",
        time_col="close_time",
        note="G1_v1_baseline_phase4",
    )


def run_g2(df: pd.DataFrame, forecaster: Forecaster, threshold_margin: float = 0.0) -> GateResult:
    decision_fn = make_llm_decision_fn(forecaster, threshold_margin=threshold_margin)
    trainer = llm_trainer_factory(forecaster, threshold_margin=threshold_margin)
    note = f"G2_llm_{forecaster.prompt_variant}_margin{threshold_margin:.2f}_phase4"
    return gate_evaluate(
        df, decision_fn,
        trainer=trainer,
        price_col="favorite_price",
        outcome_col="outcome",
        time_col="close_time",
        note=note,
    )


def run_forecasts_all(df: pd.DataFrame, forecaster: Forecaster, label: str) -> pd.DataFrame:
    records = []
    total_cost = 0.0
    for i, (_, row) in enumerate(df.iterrows(), 1):
        result = forecaster.forecast(row.to_dict())
        records.append({
            "ticker": result.ticker,
            "prob_yes": result.prob_yes,
            "outcome": int(row["outcome"]),
            "favorite_price": float(row["favorite_price"]),
            "series_ticker": row["series_ticker"],
            "lifetime_days": float(row["lifetime_days"]),
            "close_time": row["close_time"],
            "model": result.model_name,
            "prompt_variant": result.prompt_variant,
            "cost_usd": result.cost_usd,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "latency_ms": result.latency_ms,
            "rationale": result.rationale,
        })
        total_cost += result.cost_usd
        if i % 25 == 0 or i == len(df):
            print(f"  [{label}: {i}/{len(df)}] cumulative cost ${total_cost:.4f}")
    return pd.DataFrame(records)


def calibration_block(forecasts_df: pd.DataFrame) -> dict:
    probs_llm = forecasts_df["prob_yes"].to_numpy(dtype=float)
    probs_kalshi = forecasts_df["favorite_price"].to_numpy(dtype=float)
    outcomes = forecasts_df["outcome"].to_numpy(dtype=int)
    b_llm = brier(probs_llm, outcomes)
    b_kalshi = brier(probs_kalshi, outcomes)
    bss_v = bss(probs_llm, probs_kalshi, outcomes)
    ece_llm = ece(probs_llm, outcomes)
    ece_kalshi = ece(probs_kalshi, outcomes)
    diff_mean, ci_lo, ci_hi = bootstrap_brier_diff_ci(probs_llm, probs_kalshi, outcomes)
    return {
        "n": int(len(forecasts_df)),
        "brier_llm": b_llm,
        "brier_kalshi_baseline": b_kalshi,
        "bss_vs_kalshi": bss_v,
        "ece_llm": ece_llm,
        "ece_kalshi": ece_kalshi,
        "brier_diff_kalshi_minus_llm": diff_mean,
        "brier_diff_ci_lower": ci_lo,
        "brier_diff_ci_upper": ci_hi,
        "yes_rate": float(outcomes.mean()),
        "mean_llm_prob": float(probs_llm.mean()),
        "mean_kalshi_price": float(probs_kalshi.mean()),
        "corr_llm_kalshi": float(np.corrcoef(probs_llm, probs_kalshi)[0, 1]) if len(probs_llm) > 1 else float("nan"),
    }


def per_series_brier(forecasts_df: pd.DataFrame, min_n: int = 5) -> dict:
    """Per-series Brier comparison."""
    out = {}
    for series, sub in forecasts_df.groupby("series_ticker"):
        if len(sub) < min_n:
            continue
        probs_llm = sub["prob_yes"].to_numpy(dtype=float)
        probs_k = sub["favorite_price"].to_numpy(dtype=float)
        ys = sub["outcome"].to_numpy(dtype=int)
        out[str(series)] = {
            "n": int(len(sub)),
            "yes_rate": float(ys.mean()),
            "brier_llm": brier(probs_llm, ys),
            "brier_kalshi": brier(probs_k, ys),
            "mean_llm_prob": float(probs_llm.mean()),
            "mean_kalshi_price": float(probs_k.mean()),
        }
    return out


def per_bucket_calibration(forecasts_df: pd.DataFrame) -> list:
    """LLM calibration by LLM prob bucket."""
    df = forecasts_df.copy()
    bins = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0001]
    df["bucket"] = pd.cut(df["prob_yes"], bins=bins, include_lowest=True, right=False)
    out = []
    for b, sub in df.groupby("bucket"):
        out.append({
            "bucket": str(b),
            "n": int(len(sub)),
            "mean_llm_prob": float(sub["prob_yes"].mean()) if len(sub) > 0 else None,
            "actual_yes_rate": float(sub["outcome"].mean()) if len(sub) > 0 else None,
        })
    return out


def lifetime_price_breakdown(forecasts_df: pd.DataFrame) -> dict:
    """Brier per (lifetime_bucket, price_bucket)."""
    df = forecasts_df.copy()
    df["lifetime_bucket"] = pd.cut(
        df["lifetime_days"], bins=[0, 60, 90, 120, 180, 365],
        labels=["30-60d", "60-90d", "90-120d", "120-180d", "180-365d"],
    )
    df["price_bucket"] = pd.cut(
        df["favorite_price"], bins=[0.55, 0.70, 0.80, 0.90, 1.0],
        labels=["55-70c", "70-80c", "80-90c", "90-95c"],
    )
    out: dict = {}
    for (lt, pr), sub in df.groupby(["lifetime_bucket", "price_bucket"]):
        key = f"{lt}|{pr}"
        if len(sub) < 3:
            continue
        out[key] = {
            "n": int(len(sub)),
            "yes_rate": float(sub["outcome"].mean()),
            "brier_llm": brier(sub["prob_yes"].to_numpy(), sub["outcome"].to_numpy(int)),
            "brier_kalshi": brier(sub["favorite_price"].to_numpy(), sub["outcome"].to_numpy(int)),
            "mean_llm_prob": float(sub["prob_yes"].mean()),
            "mean_kalshi": float(sub["favorite_price"].mean()),
        }
    return out


# --- Sanity tests (subset reuse of V4-F's S-B1, S-B2, S-B3) ---


def run_sb1_cutoff_leak(
    forecaster_full: Forecaster,
    forecaster_anon: Forecaster,
    n_test: int = 10,
) -> dict:
    """Pre-cutoff sample from V4-C pilot; compares full vs anon prompt."""
    pilot_df = pd.read_parquet(PILOT_PATH)
    pre = pilot_df[pilot_df["cutoff_bucket"] == "pre_llm_cutoff"].copy()
    pre = pre.sample(n=min(n_test, len(pre)), random_state=42)
    records = []
    for _, row in pre.iterrows():
        r1 = forecaster_full.forecast(row.to_dict())
        r2 = forecaster_anon.forecast(row.to_dict())
        records.append({
            "ticker": row["ticker"],
            "outcome": int(row["outcome"]),
            "favorite_price": float(row["favorite_price"]),
            "prob_full": r1.prob_yes,
            "prob_anon": r2.prob_yes,
            "diff": r1.prob_yes - r2.prob_yes,
        })
    rec_df = pd.DataFrame(records)
    return {
        "n": int(len(rec_df)),
        "mean_abs_diff": float(rec_df["diff"].abs().mean()),
        "brier_full_pre": brier(rec_df["prob_full"].to_numpy(), rec_df["outcome"].to_numpy()),
        "brier_anon_pre": brier(rec_df["prob_anon"].to_numpy(), rec_df["outcome"].to_numpy()),
        "records": rec_df.to_dict(orient="records"),
    }


def run_sb2_price_anchor(
    forecaster_noprice: Forecaster,
    forecaster_withprice: Forecaster,
    df: pd.DataFrame,
    n_test: int = 10,
) -> dict:
    sub = df.sample(n=min(n_test, len(df)), random_state=42).copy()
    records = []
    for _, row in sub.iterrows():
        rd = row.to_dict()
        r_noprice = forecaster_noprice.forecast(rd)
        r_withprice = forecaster_withprice.forecast(rd)
        records.append({
            "ticker": row["ticker"],
            "outcome": int(row["outcome"]),
            "favorite_price": float(row["favorite_price"]),
            "prob_noprice": r_noprice.prob_yes,
            "prob_withprice": r_withprice.prob_yes,
            "diff": r_withprice.prob_yes - r_noprice.prob_yes,
        })
    rec_df = pd.DataFrame(records)
    probs_np = rec_df["prob_noprice"].to_numpy()
    probs_wp = rec_df["prob_withprice"].to_numpy()
    prices = rec_df["favorite_price"].to_numpy()
    return {
        "n": int(len(rec_df)),
        "corr_noprice_price": float(np.corrcoef(probs_np, prices)[0, 1]) if len(probs_np) > 1 else float("nan"),
        "corr_withprice_price": float(np.corrcoef(probs_wp, prices)[0, 1]) if len(probs_wp) > 1 else float("nan"),
        "mean_diff_wp_minus_np": float(rec_df["diff"].mean()),
        "records": rec_df.to_dict(orient="records"),
    }


def run_sb3_prompt_sensitivity(
    forecaster_c: Forecaster,
    forecaster_c2: Forecaster,
    forecaster_c3: Forecaster,
    df: pd.DataFrame,
    n_test: int = 5,
) -> dict:
    sub = df.sample(n=min(n_test, len(df)), random_state=42).copy()
    records = []
    for _, row in sub.iterrows():
        rd = row.to_dict()
        p_c = forecaster_c.forecast(rd).prob_yes
        p_c2 = forecaster_c2.forecast(rd).prob_yes
        p_c3 = forecaster_c3.forecast(rd).prob_yes
        records.append({
            "ticker": row["ticker"],
            "outcome": int(row["outcome"]),
            "favorite_price": float(row["favorite_price"]),
            "prob_C": p_c,
            "prob_C2": p_c2,
            "prob_C3": p_c3,
            "std_across_variants": float(np.std([p_c, p_c2, p_c3])),
            "range": float(max(p_c, p_c2, p_c3) - min(p_c, p_c2, p_c3)),
        })
    rec_df = pd.DataFrame(records)
    return {
        "n": int(len(rec_df)),
        "mean_std_across_variants": float(rec_df["std_across_variants"].mean()),
        "mean_range": float(rec_df["range"].mean()),
        "records": rec_df.to_dict(orient="records"),
    }


def gate_result_to_dict(g: GateResult) -> dict:
    return {
        "note": g.note,
        "passes": bool(g.passes),
        "criteria": {k: bool(v) for k, v in g.criteria.items()},
        "holdout_train_n": int(g.holdout_train_n),
        "holdout_test_n": int(g.holdout_test_n),
        "holdout_eligible_n": int(g.holdout_eligible_n),
        "holdout_mean": float(g.holdout_mean) if not np.isnan(g.holdout_mean) else None,
        "holdout_median": float(g.holdout_median) if not np.isnan(g.holdout_median) else None,
        "holdout_sd": float(g.holdout_sd) if not np.isnan(g.holdout_sd) else None,
        "holdout_hit_rate": float(g.holdout_hit_rate) if not np.isnan(g.holdout_hit_rate) else None,
        "holdout_ci_lower": float(g.holdout_ci_lower) if not np.isnan(g.holdout_ci_lower) else None,
        "holdout_ci_upper": float(g.holdout_ci_upper) if not np.isnan(g.holdout_ci_upper) else None,
        "v1_holdout_mean": float(g.v1_holdout_mean) if not np.isnan(g.v1_holdout_mean) else None,
        "folds_eligible_total": int(g.folds_eligible_total),
        "folds_pooled_mean": float(g.folds_pooled_mean) if not np.isnan(g.folds_pooled_mean) else None,
        "folds_pooled_ci_lower": float(g.folds_pooled_ci_lower) if not np.isnan(g.folds_pooled_ci_lower) else None,
        "folds_pooled_ci_upper": float(g.folds_pooled_ci_upper) if not np.isnan(g.folds_pooled_ci_upper) else None,
        "fold_means": [float(m) if not np.isnan(m) else None for m in g.fold_means],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-g3", action="store_true", help="Skip Prompt CR (Wikipedia RAG)")
    parser.add_argument("--skip-sanity", action="store_true", help="Skip S-B1/S-B2/S-B3")
    parser.add_argument("--budget-usd", type=float, default=V4_BUDGET_USD)
    parser.add_argument("--margin-grid", nargs="*", type=float, default=[0.0, 0.05, 0.10])
    args = parser.parse_args()

    df = pd.read_parquet(SAMPLE_PATH)
    df = prepare_sample(df)
    print(f"Phase 4 sample n={len(df)}")
    print(f"Yes rate: {df['outcome'].mean():.3f}")
    print(f"Favorite price range: [{df['favorite_price'].min():.3f}, {df['favorite_price'].max():.3f}]")
    print(f"Lifetime range: [{df['lifetime_days'].min():.0f}, {df['lifetime_days'].max():.0f}]")
    print()

    results: dict = {
        "sample_n": int(len(df)),
        "sample_yes_rate": float(df["outcome"].mean()),
        "sample_mean_price": float(df["favorite_price"].mean()),
        "window_start": "2025-08-01 (Aug 2025 buffer past Anthropic Haiku 4.5 Jul 2025 training cutoff)",
        "window_end": "2026-03-25",
        "cutoff_source": "https://platform.claude.com/docs/en/about-claude/models/overview",
    }

    print("=== G1: v1 baseline ===")
    g1 = run_g1(df)
    print(f"  passes={g1.passes}; holdout_mean={g1.holdout_mean:.4f}; n_eligible={g1.holdout_eligible_n}")
    results["G1"] = gate_result_to_dict(g1)

    forecaster_c = Forecaster(model=HAIKU_MODEL, prompt_variant="C", enable_cache=True)

    print("\n=== Running Prompt C forecasts ===")
    forecasts_c = run_forecasts_all(df, forecaster_c, "PromptC")
    forecasts_c.to_parquet(FORECASTS_PATH, index=False)
    total_cost_c = float(forecasts_c["cost_usd"].sum())
    print(f"  Total cost for Prompt C (this run): ${total_cost_c:.4f}")

    cal_c = calibration_block(forecasts_c)
    results["calibration_promptC"] = cal_c
    print(f"  Brier LLM: {cal_c['brier_llm']:.4f}  Kalshi: {cal_c['brier_kalshi_baseline']:.4f}  BSS: {cal_c['bss_vs_kalshi']:+.3f}")
    print(f"  ECE LLM: {cal_c['ece_llm']:.4f}  ECE Kalshi: {cal_c['ece_kalshi']:.4f}")
    print(f"  Brier diff (Kalshi - LLM): {cal_c['brier_diff_kalshi_minus_llm']:+.4f} "
          f"[{cal_c['brier_diff_ci_lower']:+.4f}, {cal_c['brier_diff_ci_upper']:+.4f}]")
    print(f"  Mean LLM prob: {cal_c['mean_llm_prob']:.3f}  Mean Kalshi: {cal_c['mean_kalshi_price']:.3f}  Corr: {cal_c['corr_llm_kalshi']:.3f}")

    results["per_series_brier"] = per_series_brier(forecasts_c, min_n=5)
    results["per_bucket_calibration"] = per_bucket_calibration(forecasts_c)
    results["lifetime_price_breakdown"] = lifetime_price_breakdown(forecasts_c)

    print("\n=== G2: LLM Prompt C, margin sweep ===")
    g2_runs: dict = {}
    for margin in args.margin_grid:
        print(f"  margin={margin:.2f} ...")
        g2 = run_g2(df, forecaster_c, threshold_margin=margin)
        print(f"    passes={g2.passes}; n={g2.holdout_eligible_n}; mean={g2.holdout_mean:.4f}; "
              f"v1_baseline={g2.v1_holdout_mean:.4f}; v2_minus_v1={(g2.holdout_mean - g2.v1_holdout_mean):.4f}")
        g2_runs[f"margin_{margin:.2f}"] = gate_result_to_dict(g2)
    results["G2"] = g2_runs

    print("\n=== G2-fade: LLM Prompt C fade-only filter (band [0.70, 0.85]) ===")
    fade_fn = make_llm_decision_fn(forecaster_c, fade_only=True, fade_threshold=0.10,
                                    price_low=0.70, price_high=0.85)
    g2_fade = gate_evaluate(
        df, fade_fn,
        trainer=lambda _: fade_fn,
        price_col="favorite_price",
        outcome_col="outcome",
        time_col="close_time",
        note="G2_llm_fade_only_phase4",
    )
    print(f"  fade-only: passes={g2_fade.passes}; n={g2_fade.holdout_eligible_n}; mean={g2_fade.holdout_mean:.4f}; "
          f"v2_minus_v1={(g2_fade.holdout_mean - g2_fade.v1_holdout_mean):.4f}")
    results["G2_fade"] = gate_result_to_dict(g2_fade)

    if not args.skip_g3:
        print("\n=== G3: LLM Prompt CR (Wikipedia retrieval) ===")
        forecaster_cr = Forecaster(model=HAIKU_MODEL, prompt_variant="CR", enable_cache=True)
        forecasts_cr = run_forecasts_all(df, forecaster_cr, "PromptCR")
        cal_cr = calibration_block(forecasts_cr)
        results["calibration_promptCR"] = cal_cr
        total_cost_cr = float(forecasts_cr["cost_usd"].sum())
        print(f"  Total cost for Prompt CR (this run): ${total_cost_cr:.4f}")
        print(f"  Brier LLM: {cal_cr['brier_llm']:.4f}  Kalshi: {cal_cr['brier_kalshi_baseline']:.4f}  BSS: {cal_cr['bss_vs_kalshi']:+.3f}")
        g3_runs: dict = {}
        for margin in args.margin_grid:
            g3 = run_g2(df, forecaster_cr, threshold_margin=margin)
            print(f"    margin={margin:.2f}: passes={g3.passes}; n={g3.holdout_eligible_n}; mean={g3.holdout_mean:.4f}; "
                  f"v2_minus_v1={(g3.holdout_mean - g3.v1_holdout_mean):.4f}")
            g3_runs[f"margin_{margin:.2f}"] = gate_result_to_dict(g3)
        results["G3"] = g3_runs

    if not args.skip_sanity:
        print("\n=== S-B1: cutoff-leak (full vs anon on pre-cutoff sample) ===")
        forecaster_anon = Forecaster(model=HAIKU_MODEL, prompt_variant="ANON", enable_cache=True)
        sb1 = run_sb1_cutoff_leak(forecaster_c, forecaster_anon, n_test=10)
        results["SB1"] = sb1
        print(f"  mean_abs_diff: {sb1['mean_abs_diff']:.4f}")
        print(f"  brier_full_pre: {sb1['brier_full_pre']:.4f}  brier_anon_pre: {sb1['brier_anon_pre']:.4f}")

        print("\n=== S-B2: price-anchor (no-price vs with-price on subset) ===")
        forecaster_wp = Forecaster(model=HAIKU_MODEL, prompt_variant="WP", enable_cache=True)
        sb2 = run_sb2_price_anchor(forecaster_c, forecaster_wp, df, n_test=10)
        results["SB2"] = sb2
        print(f"  corr(no-price, price): {sb2['corr_noprice_price']:.3f}")
        print(f"  corr(with-price, price): {sb2['corr_withprice_price']:.3f}")

        print("\n=== S-B3: prompt sensitivity (C vs C2 vs C3) ===")
        forecaster_c2 = Forecaster(model=HAIKU_MODEL, prompt_variant="C2", enable_cache=True)
        forecaster_c3 = Forecaster(model=HAIKU_MODEL, prompt_variant="C3", enable_cache=True)
        sb3 = run_sb3_prompt_sensitivity(forecaster_c, forecaster_c2, forecaster_c3, df, n_test=5)
        results["SB3"] = sb3
        print(f"  mean_std_across_variants: {sb3['mean_std_across_variants']:.4f}")
        print(f"  mean_range: {sb3['mean_range']:.4f}")

    # Cumulative cost across cache
    cache_path = PROJECT_ROOT / "data" / "v4" / "llm_forecast_cache.parquet"
    if cache_path.exists():
        cache_df = pd.read_parquet(cache_path)
        cumulative_cost = float(cache_df["cost_usd"].sum())
        print(f"\n=== Cumulative API spend (all V4 phases): ${cumulative_cost:.4f} ===")
        results["cumulative_api_cost_usd_cache_total"] = cumulative_cost

    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(results, indent=2, default=str))
    print(f"\nResults written to {RESULTS_PATH}")
    print(f"Forecast data written to {FORECASTS_PATH}")


if __name__ == "__main__":
    main()
