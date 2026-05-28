"""V4-C LLM pilot analysis.

Reads data/v4/llm_pilot_results*.parquet, computes Brier scores, BSS vs Kalshi
price baseline, price-anchoring measurement, cutoff-leak diagnostic, and cost
projections. Prints the verdict-relevant numbers.

Usage:
    uv run python -m scripts.v4.llm_pilot_analyze
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def brier(probs: pd.Series, outcomes: pd.Series) -> float:
    return float(((probs - outcomes) ** 2).mean())


def bss(brier_target: float, brier_ref: float) -> float:
    if brier_ref == 0:
        return float("nan")
    return float(1 - brier_target / brier_ref)


def per_bucket(df: pd.DataFrame, prob_col: str) -> dict:
    out = {}
    for bucket, g in df.groupby("cutoff_bucket"):
        if g[prob_col].notna().sum() == 0:
            continue
        b = brier(g[prob_col], g["outcome"])
        out[str(bucket)] = {"n": int(len(g)), "brier": b, "yes_rate": float(g["outcome"].mean())}
    return out


def main() -> None:
    sample = pd.read_parquet(PROJECT_ROOT / "data" / "v4" / "llm_pilot_sample.parquet")
    results_primary = pd.read_parquet(PROJECT_ROOT / "data" / "v4" / "llm_pilot_results.parquet")

    # Also load any pivots / opus runs.
    optional_paths = {
        "opus": PROJECT_ROOT / "data" / "v4" / "llm_pilot_results_opus.parquet",
        "pivot_CD": PROJECT_ROOT / "data" / "v4" / "llm_pilot_results_pivotCD.parquet",
        "ensemble": PROJECT_ROOT / "data" / "v4" / "llm_pilot_results_ensemble.parquet",
    }
    extra = {}
    for name, p in optional_paths.items():
        if p.exists():
            extra[name] = pd.read_parquet(p)

    print("=" * 70)
    print(f"Sample n={len(sample)}")
    print(f"Bucket counts: {sample['cutoff_bucket'].value_counts().to_dict()}")
    print(f"Sample yes-rate: {sample['outcome'].mean():.3f}")
    print()

    # Kalshi raw baseline: Brier of using favorite_price directly.
    sample_brier_raw = brier(sample["favorite_price"], sample["outcome"])
    print(f"Baseline: Brier(Kalshi raw price) = {sample_brier_raw:.4f}")

    # Per-bucket raw baseline.
    print("\nPer-bucket Kalshi raw Brier:")
    for bucket, g in sample.groupby("cutoff_bucket"):
        b = brier(g["favorite_price"], g["outcome"])
        print(f"  {bucket}: n={len(g)} | brier={b:.4f} | yes_rate={g['outcome'].mean():.3f}")
    print()

    # Haiku analysis.
    print("=" * 70)
    print("HAIKU 4.5 (primary run)")
    print("=" * 70)
    haiku = results_primary[results_primary["model"] == "claude-haiku-4-5"]
    haiku_a = haiku[haiku["variant"] == "A"].copy()
    haiku_b = haiku[haiku["variant"] == "B"].copy()
    print(f"n_A: {len(haiku_a)}, n_B: {len(haiku_b)}")

    # Sanity: probs should be in [0,1]
    print(f"Haiku-A prob range: [{haiku_a['llm_prob'].min():.3f}, {haiku_a['llm_prob'].max():.3f}], mean={haiku_a['llm_prob'].mean():.3f}")
    print(f"Haiku-B prob range: [{haiku_b['llm_prob'].min():.3f}, {haiku_b['llm_prob'].max():.3f}], mean={haiku_b['llm_prob'].mean():.3f}")

    brier_haiku_a = brier(haiku_a["llm_prob"], haiku_a["outcome"])
    brier_haiku_b = brier(haiku_b["llm_prob"], haiku_b["outcome"])
    print(f"\nBrier(Haiku-A) = {brier_haiku_a:.4f}")
    print(f"Brier(Haiku-B) = {brier_haiku_b:.4f}")
    print(f"BSS(Haiku-A vs Kalshi raw) = {bss(brier_haiku_a, sample_brier_raw):+.4f}")
    print(f"BSS(Haiku-B vs Kalshi raw) = {bss(brier_haiku_b, sample_brier_raw):+.4f}")

    # Per-bucket Haiku-A and Haiku-B.
    print("\nPer-bucket Haiku Brier:")
    for bucket in ("pre_llm_cutoff", "post_llm_in_archive", "post_kalshi_cutoff"):
        gA = haiku_a[haiku_a["cutoff_bucket"] == bucket]
        gB = haiku_b[haiku_b["cutoff_bucket"] == bucket]
        if len(gA) == 0:
            continue
        bA = brier(gA["llm_prob"], gA["outcome"])
        bB = brier(gB["llm_prob"], gB["outcome"])
        bK = brier(gA["kalshi_price"], gA["outcome"])
        print(
            f"  {bucket}: n={len(gA)} | "
            f"yes_rate={gA['outcome'].mean():.3f} | "
            f"Brier(K)={bK:.4f} | Brier(A)={bA:.4f} | Brier(B)={bB:.4f} | "
            f"BSS_A={bss(bA, bK):+.3f} | BSS_B={bss(bB, bK):+.3f}"
        )

    # Cutoff-leak: compare pre vs post bucket Brier.
    pre = haiku[haiku["cutoff_bucket"] == "pre_llm_cutoff"]
    post = haiku[haiku["cutoff_bucket"].isin(["post_llm_in_archive", "post_kalshi_cutoff"])]
    pre_A = pre[pre["variant"] == "A"]
    post_A = post[post["variant"] == "A"]
    if len(pre_A) > 0 and len(post_A) > 0:
        leak_A = brier(post_A["llm_prob"], post_A["outcome"]) - brier(pre_A["llm_prob"], pre_A["outcome"])
        print(f"\nCutoff-leak diagnostic (Haiku-A, post - pre Brier): {leak_A:+.4f}")
        print(f"  Pre  Brier: {brier(pre_A['llm_prob'], pre_A['outcome']):.4f} (n={len(pre_A)})")
        print(f"  Post Brier: {brier(post_A['llm_prob'], post_A['outcome']):.4f} (n={len(post_A)})")
        print(f"  Interpretation: positive value means Haiku is WORSE on post-cutoff (consistent with cutoff-leak)")

    # Price-anchoring measurement.
    # Join A and B by ticker; measure abs(prob_A - prob_B) and abs(prob_A - kalshi_price) vs abs(prob_B - kalshi_price).
    pair = haiku_a[["ticker", "llm_prob", "kalshi_price", "outcome"]].rename(columns={"llm_prob": "prob_A"})
    pair = pair.merge(haiku_b[["ticker", "llm_prob"]].rename(columns={"llm_prob": "prob_B"}), on="ticker")
    print(f"\nPrice-anchoring (Haiku, n={len(pair)}):")
    print(f"  mean |prob_A - prob_B|:        {(pair['prob_A'] - pair['prob_B']).abs().mean():.4f}")
    print(f"  mean (prob_A - prob_B):        {(pair['prob_A'] - pair['prob_B']).mean():+.4f}")
    print(f"  mean |prob_A - kalshi_price|:  {(pair['prob_A'] - pair['kalshi_price']).abs().mean():.4f}")
    print(f"  mean |prob_B - kalshi_price|:  {(pair['prob_B'] - pair['kalshi_price']).abs().mean():.4f}")
    print(f"  correlation(prob_A, kalshi):   {pair['prob_A'].corr(pair['kalshi_price']):.3f}")
    print(f"  correlation(prob_B, kalshi):   {pair['prob_B'].corr(pair['kalshi_price']):.3f}")

    # Cost projection.
    haiku_cost = results_primary[results_primary["model"] == "claude-haiku-4-5"]["cost_usd"].sum()
    haiku_n_calls = len(results_primary[results_primary["model"] == "claude-haiku-4-5"])
    haiku_per_call = haiku_cost / max(1, haiku_n_calls)
    print("\nCost projection (Haiku):")
    print(f"  cost per call:        ${haiku_per_call:.5f}")
    print(f"  cost per 100 calls:   ${haiku_per_call * 100:.3f}")
    print(f"  cost per 1000 calls:  ${haiku_per_call * 1000:.2f}")
    # Full v4 eval projection: 147 markets x 1 forecast (A only) x 1 model = 147 calls.
    print(f"  full v4 eval (147 x 1 prompt = 147 calls): ${haiku_per_call * 147:.3f}")
    print(f"  full v4 eval (147 x 2 prompts = 294 calls): ${haiku_per_call * 294:.3f}")

    # Opus analysis.
    if "opus" in extra:
        print("\n" + "=" * 70)
        print("OPUS 4.7 (spot-check, n=5)")
        print("=" * 70)
        opus = extra["opus"]
        opus_a = opus[opus["variant"] == "A"].copy()
        opus_b = opus[opus["variant"] == "B"].copy()
        print(f"n_A: {len(opus_a)}, n_B: {len(opus_b)}")
        if len(opus_a) >= 1:
            brier_opus_a = brier(opus_a["llm_prob"], opus_a["outcome"])
            brier_opus_b = brier(opus_b["llm_prob"], opus_b["outcome"])
            brier_kalshi_opus = brier(opus_a["kalshi_price"], opus_a["outcome"])
            print(f"Brier(Opus-A) = {brier_opus_a:.4f}")
            print(f"Brier(Opus-B) = {brier_opus_b:.4f}")
            print(f"Brier(Kalshi raw, opus subset) = {brier_kalshi_opus:.4f}")
            print(f"BSS(Opus-A vs Kalshi raw) = {bss(brier_opus_a, brier_kalshi_opus):+.4f}")
            print(f"BSS(Opus-B vs Kalshi raw) = {bss(brier_opus_b, brier_kalshi_opus):+.4f}")
            print("Per-bucket Opus Brier (small n):")
            for bucket in ("pre_llm_cutoff", "post_llm_in_archive", "post_kalshi_cutoff"):
                gA = opus_a[opus_a["cutoff_bucket"] == bucket]
                gB = opus_b[opus_b["cutoff_bucket"] == bucket]
                if len(gA) == 0:
                    continue
                bA = brier(gA["llm_prob"], gA["outcome"])
                bB = brier(gB["llm_prob"], gB["outcome"])
                bK = brier(gA["kalshi_price"], gA["outcome"])
                print(
                    f"  {bucket}: n={len(gA)} | yes_rate={gA['outcome'].mean():.3f} | "
                    f"Brier(K)={bK:.4f} | Brier(A)={bA:.4f} | Brier(B)={bB:.4f}"
                )

        opus_cost = opus["cost_usd"].sum()
        opus_per_call = opus_cost / max(1, len(opus))
        print("\nCost projection (Opus):")
        print(f"  cost per call:        ${opus_per_call:.4f}")
        print(f"  cost per 100 calls:   ${opus_per_call * 100:.2f}")
        print(f"  cost per 1000 calls:  ${opus_per_call * 1000:.2f}")
        print(f"  full v4 eval (147 x 1 prompt = 147 calls Opus): ${opus_per_call * 147:.2f}")

        # Compare Opus vs Haiku where they overlap.
        overlap = opus_a.merge(haiku_a, on="ticker", suffixes=("_opus", "_haiku"))
        if len(overlap) > 0:
            print(f"\nOpus vs Haiku on overlapping tickers (n={len(overlap)}):")
            print(f"  Brier(Haiku-A, overlap)={brier(overlap['llm_prob_haiku'], overlap['outcome_haiku']):.4f}")
            print(f"  Brier(Opus-A,  overlap)={brier(overlap['llm_prob_opus'], overlap['outcome_opus']):.4f}")
            print(f"  Brier(Kalshi,  overlap)={brier(overlap['kalshi_price_haiku'], overlap['outcome_haiku']):.4f}")

    # Print pivots if present.
    for name in ("pivot_CD", "ensemble"):
        if name not in extra:
            continue
        print(f"\n" + "=" * 70)
        print(f"{name.upper()} pivot")
        print("=" * 70)
        ex = extra[name]
        for variant in sorted(ex["variant"].dropna().unique()):
            g = ex[ex["variant"] == variant]
            if g["llm_prob"].notna().sum() == 0:
                continue
            bP = brier(g["llm_prob"], g["outcome"])
            bK = brier(g["kalshi_price"], g["outcome"])
            print(f"  variant={variant} | n={len(g)} | Brier(LLM)={bP:.4f} | Brier(K)={bK:.4f} | BSS={bss(bP, bK):+.4f}")
            for bucket in ("pre_llm_cutoff", "post_llm_in_archive", "post_kalshi_cutoff"):
                gB = g[g["cutoff_bucket"] == bucket]
                if len(gB) == 0:
                    continue
                bPB = brier(gB["llm_prob"], gB["outcome"])
                bKB = brier(gB["kalshi_price"], gB["outcome"])
                print(f"    {bucket}: n={len(gB)} | Brier(LLM)={bPB:.4f} | Brier(K)={bKB:.4f} | BSS={bss(bPB, bKB):+.3f}")


if __name__ == "__main__":
    main()
