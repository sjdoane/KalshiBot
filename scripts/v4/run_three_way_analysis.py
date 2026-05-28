"""V4-G2 three-way Phase 4 analysis.

Per V4-H finding (research/v4/09-v1-stress-test.md), v1 is FRAGILE on:
- KXNFLWINS
- KXNFLPLAYOFF
- KXMLBPLAYOFFS

So the meaningful Phase 4 comparison is not "LLM vs v1 raw" but
three scenarios:

  scenario_a (v1 raw):
      Trade every strict-eligible row.
  scenario_b (v1 + V4-H denylist):
      Skip the 3 fragile series. Trade everything else.
  scenario_c (v1 + V4-H denylist + LLM-fade):
      Skip the 3 fragile series. THEN apply the fade-only band-gated
      LLM filter on the residual (skip when LLM disagrees on prices in
      [0.70, 0.85]).

For each scenario:
- mean P&L
- bootstrap 95% CI
- hit rate
- n_trades

Inputs:
- data/v4/llm_phase4_sample.parquet (sample, n=200)
- data/v4/llm_phase4_forecasts.parquet (Prompt C forecasts on those 200)

Output:
- data/v4/llm_phase4_three_way_results.json

Read-only.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from kalshi_bot_v2.gate import realized_pnl_per_contract  # noqa: E402
from kalshi_bot.analysis.bootstrap import bootstrap_mean_ci  # noqa: E402

SAMPLE_PATH = PROJECT_ROOT / "data" / "v4" / "llm_phase4_sample.parquet"
FORECASTS_PATH = PROJECT_ROOT / "data" / "v4" / "llm_phase4_forecasts.parquet"
OUT_PATH = PROJECT_ROOT / "data" / "v4" / "llm_phase4_three_way_results.json"

# Per research/v4/09-v1-stress-test.md, these series are FRAGILE for v1.
V4H_DENYLIST_PREFIXES = ("KXNFLWINS", "KXNFLPLAYOFF", "KXMLBPLAYOFFS")

# Locked LLM-fade gate parameters per V4-F's best fade variant.
FADE_PRICE_LOW = 0.70
FADE_PRICE_HIGH = 0.85
FADE_THRESHOLD = 0.10  # llm_prob < kalshi_price - FADE_THRESHOLD => skip


def is_denylisted(series_ticker: str) -> bool:
    """Return True if the series matches any V4-H denylisted prefix."""
    s = str(series_ticker)
    for p in V4H_DENYLIST_PREFIXES:
        if s.startswith(p):
            return True
    return False


def llm_should_fade(price: float, llm_prob: float) -> bool:
    """V4-F fade-only band-gated rule."""
    if FADE_PRICE_LOW <= price <= FADE_PRICE_HIGH and llm_prob < price - FADE_THRESHOLD:
        return True
    return False


def pnl_stats(realized: np.ndarray, label: str) -> dict:
    """Bootstrap mean/CI plus descriptive stats."""
    if realized.size == 0:
        return {
            "label": label,
            "n_trades": 0,
            "mean_pnl": None,
            "ci_lower": None,
            "ci_upper": None,
            "hit_rate": None,
            "median_pnl": None,
            "sd_pnl": None,
        }
    try:
        m, lo, hi = bootstrap_mean_ci(realized, n_resamples=5000, ci=0.95, rng_seed=42)
    except ValueError:
        m, lo, hi = float(realized.mean()), float("nan"), float("nan")
    return {
        "label": label,
        "n_trades": int(realized.size),
        "mean_pnl": float(realized.mean()),
        "ci_lower": float(lo) if not np.isnan(lo) else None,
        "ci_upper": float(hi) if not np.isnan(hi) else None,
        "hit_rate": float((realized > 0).mean()),
        "median_pnl": float(np.median(realized)),
        "sd_pnl": float(realized.std()),
    }


def scenario_pnls(df: pd.DataFrame, skip_mask: pd.Series, label: str) -> tuple[np.ndarray, dict]:
    """Compute realized P&L for the rows NOT skipped."""
    keep = df[~skip_mask].copy()
    realized = np.array([
        realized_pnl_per_contract(float(r["favorite_price"]), int(r["outcome_favorite"]))
        for _, r in keep.iterrows()
    ], dtype=float)
    stats = pnl_stats(realized, label)
    stats["n_skipped"] = int(skip_mask.sum())
    stats["n_input"] = int(len(df))
    return realized, stats


def per_series_breakdown(df: pd.DataFrame, label: str) -> dict:
    out = {}
    for series, sub in df.groupby("series_ticker"):
        realized = np.array([
            realized_pnl_per_contract(float(r["favorite_price"]), int(r["outcome_favorite"]))
            for _, r in sub.iterrows()
        ], dtype=float)
        if realized.size == 0:
            continue
        out[str(series)] = {
            "n": int(realized.size),
            "yes_rate": float(sub["outcome_favorite"].mean()),
            "mean_pnl": float(realized.mean()),
            "mean_price": float(sub["favorite_price"].mean()),
        }
    return out


def main() -> None:
    df = pd.read_parquet(SAMPLE_PATH)
    forecasts = pd.read_parquet(FORECASTS_PATH)

    # Merge LLM probs onto the sample
    df = df.merge(
        forecasts[["ticker", "prob_yes"]].rename(columns={"prob_yes": "llm_prob_yes"}),
        on="ticker", how="left",
    )
    n_missing_forecast = int(df["llm_prob_yes"].isna().sum())
    if n_missing_forecast > 0:
        print(f"WARNING: {n_missing_forecast} markets missing LLM forecasts; defaulting to llm_prob_yes=0.5 (no-fade).")
        df["llm_prob_yes"] = df["llm_prob_yes"].fillna(0.5)

    df = df.sort_values("close_time").reset_index(drop=True)
    print(f"Sample n={len(df)}")
    print(f"Yes rate: {df['outcome_favorite'].mean():.3f}")
    print(f"Denylisted-series rows: {df['series_ticker'].apply(is_denylisted).sum()} / {len(df)}")

    results: dict = {
        "sample_n": int(len(df)),
        "yes_rate_favorite": float(df["outcome_favorite"].mean()),
        "denylist_prefixes": list(V4H_DENYLIST_PREFIXES),
        "fade_params": {
            "price_low": FADE_PRICE_LOW,
            "price_high": FADE_PRICE_HIGH,
            "threshold": FADE_THRESHOLD,
        },
    }

    # --- Full-sample scenarios ---
    print("\n=== Scenario A: v1 raw (trade every strict-eligible row) ===")
    skip_a = pd.Series([False] * len(df))
    realized_a, stats_a = scenario_pnls(df, skip_a, "v1_raw")
    results["scenario_A_v1_raw"] = stats_a
    print(f"  n={stats_a['n_trades']}, mean={stats_a['mean_pnl']:.4f}, "
          f"CI=[{stats_a['ci_lower']:.4f}, {stats_a['ci_upper']:.4f}], hit_rate={stats_a['hit_rate']:.3f}")

    print("\n=== Scenario B: v1 + V4-H denylist ===")
    skip_b = df["series_ticker"].apply(is_denylisted)
    realized_b, stats_b = scenario_pnls(df, skip_b, "v1_plus_denylist")
    results["scenario_B_v1_plus_denylist"] = stats_b
    print(f"  n={stats_b['n_trades']} (skipped {stats_b['n_skipped']}), mean={stats_b['mean_pnl']:.4f}, "
          f"CI=[{stats_b['ci_lower']:.4f}, {stats_b['ci_upper']:.4f}], hit_rate={stats_b['hit_rate']:.3f}")

    print("\n=== Scenario C: v1 + V4-H denylist + LLM-fade ===")
    fade_skip = df.apply(
        lambda r: llm_should_fade(float(r["favorite_price"]), float(r["llm_prob_yes"])),
        axis=1,
    )
    skip_c = skip_b | fade_skip
    realized_c, stats_c = scenario_pnls(df, skip_c, "v1_plus_denylist_plus_llm_fade")
    stats_c["n_skipped_denylist"] = int(skip_b.sum())
    stats_c["n_skipped_fade_additional"] = int((fade_skip & ~skip_b).sum())
    results["scenario_C_v1_plus_denylist_plus_llm_fade"] = stats_c
    print(f"  n={stats_c['n_trades']} "
          f"(skip_denylist={stats_c['n_skipped_denylist']}, skip_fade={stats_c['n_skipped_fade_additional']}), "
          f"mean={stats_c['mean_pnl']:.4f}, CI=[{stats_c['ci_lower']:.4f}, {stats_c['ci_upper']:.4f}], "
          f"hit_rate={stats_c['hit_rate']:.3f}")

    # --- Additional scenario: LLM-fade-only on full sample (no denylist) ---
    print("\n=== Scenario D: v1 + LLM-fade (no denylist) ===")
    skip_d = fade_skip
    realized_d, stats_d = scenario_pnls(df, skip_d, "v1_plus_llm_fade_no_denylist")
    results["scenario_D_v1_plus_llm_fade_no_denylist"] = stats_d
    print(f"  n={stats_d['n_trades']} (skipped {stats_d['n_skipped']}), mean={stats_d['mean_pnl']:.4f}, "
          f"CI=[{stats_d['ci_lower']:.4f}, {stats_d['ci_upper']:.4f}], hit_rate={stats_d['hit_rate']:.3f}")

    # --- Differential measurements ---
    print("\n=== Differential measurements ===")

    # Difference: B - A (does denylist add value vs raw?)
    if stats_a["mean_pnl"] is not None and stats_b["mean_pnl"] is not None:
        diff_ba = stats_b["mean_pnl"] - stats_a["mean_pnl"]
        results["diff_B_minus_A_pp"] = float(diff_ba)
        print(f"  B - A (denylist effect on mean P&L): {diff_ba:+.4f}")

    # Difference: C - B (does LLM-fade add value on top of denylist?)
    if stats_b["mean_pnl"] is not None and stats_c["mean_pnl"] is not None:
        diff_cb = stats_c["mean_pnl"] - stats_b["mean_pnl"]
        results["diff_C_minus_B_pp"] = float(diff_cb)
        print(f"  C - B (LLM-fade effect on top of denylist): {diff_cb:+.4f}")

    # Per-series within sample
    print("\n=== Per-series P&L (sanity) ===")
    series_block = per_series_breakdown(df, "all")
    # Group into denylisted vs not
    deny_series = {k: v for k, v in series_block.items() if is_denylisted(k)}
    keep_series = {k: v for k, v in series_block.items() if not is_denylisted(k)}
    results["per_series_pnl_denylisted"] = deny_series
    results["per_series_pnl_kept"] = keep_series

    # Aggregate denylisted
    deny_mask = df["series_ticker"].apply(is_denylisted)
    deny_df = df[deny_mask]
    if len(deny_df) > 0:
        deny_realized = np.array([
            realized_pnl_per_contract(float(r["favorite_price"]), int(r["outcome_favorite"]))
            for _, r in deny_df.iterrows()
        ], dtype=float)
        results["denylisted_aggregate"] = pnl_stats(deny_realized, "denylisted_only")
        print(f"  Denylisted aggregate: n={len(deny_realized)}, mean={deny_realized.mean():+.4f}")

    # --- Save ---
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(results, indent=2, default=str))
    print(f"\nResults written to {OUT_PATH}")


if __name__ == "__main__":
    main()
