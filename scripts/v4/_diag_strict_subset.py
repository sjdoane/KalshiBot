"""Sub-analysis: on the v1-STRICT eligible subset (price [0.70, 0.95], lifetime [30, 180]),
does the LLM forecaster help or hurt?"""
import pandas as pd
import numpy as np
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
df = pd.read_parquet(ROOT / "data" / "v4" / "llm_phase2_sample.parquet")
fc = pd.read_parquet(ROOT / "data" / "v4" / "llm_phase2_forecasts.parquet")
df = df.merge(fc[["ticker", "prob_yes"]], on="ticker", how="left")
df["outcome"] = df["outcome_favorite"].astype(int)

# v1 strict
strict = df[(df["favorite_price"] >= 0.70) & (df["favorite_price"] <= 0.95) &
            (df["lifetime_days"] >= 30) & (df["lifetime_days"] <= 180)].copy()
print(f"v1-strict eligible n={len(strict)}")
print(f"yes_rate={strict['outcome'].mean():.3f}")
print(f"mean favorite_price={strict['favorite_price'].mean():.3f}")
print()
# v1 P&L
def pnl_per_contract(price, outcome, slip=0.015):
    gross = outcome - price
    # Kalshi maker fee
    # Per kalshi_bot.analysis.metrics: 0.07 * yes_price * (1 - yes_price)
    fee_one_side = 0.07 * price * (1 - price)
    fee_round = 2 * fee_one_side
    return gross - fee_round - slip

strict["pnl_v1"] = strict.apply(lambda r: pnl_per_contract(r["favorite_price"], r["outcome"]), axis=1)
print(f"v1 mean P&L on strict subset: {strict['pnl_v1'].mean():+.4f}")
print(f"v1 std: {strict['pnl_v1'].std():.4f}")
print(f"v1 hit rate: {(strict['pnl_v1'] > 0).mean():.3f}")

# Brier
b_llm = float(((strict["prob_yes"] - strict["outcome"])**2).mean())
b_kalshi = float(((strict["favorite_price"] - strict["outcome"])**2).mean())
print(f"\nBrier LLM (strict): {b_llm:.4f}")
print(f"Brier Kalshi (strict): {b_kalshi:.4f}")
print(f"BSS (strict): {1 - b_llm/b_kalshi:+.3f}")

# LLM fade on strict
print("\n--- LLM fade-only on strict subset ---")
for thr in [0.10, 0.20, 0.30, 0.40, 0.50]:
    mask_keep = (strict["prob_yes"] >= strict["favorite_price"] - thr)
    kept = strict[mask_keep]
    skipped = strict[~mask_keep]
    if len(kept) > 0:
        kept_mean = kept["pnl_v1"].mean()
    else:
        kept_mean = float("nan")
    skipped_mean = skipped["pnl_v1"].mean() if len(skipped) > 0 else float("nan")
    print(f"  thr={thr:.2f}: kept n={len(kept)}, mean P&L={kept_mean:+.4f} | skipped n={len(skipped)}, would-have-been P&L mean={skipped_mean:+.4f}")

# Per-bucket P&L
print("\n--- Per-series P&L on strict subset ---")
for series, g in strict.groupby("series_ticker"):
    if len(g) >= 2:
        print(f"  {series:25s} n={len(g):3d}  yes_rate={g['outcome'].mean():.2f}  v1_pnl={g['pnl_v1'].mean():+.4f}  llm_brier={float(((g['prob_yes']-g['outcome'])**2).mean()):.3f}  kalshi_brier={float(((g['favorite_price']-g['outcome'])**2).mean()):.3f}")

# Time-trend check
print("\n--- Time-aligned: which markets had T-35 in the window? ---")
# T-35d = close_time - 35 days
strict["t35"] = pd.to_datetime(strict["close_time"]) - pd.Timedelta(days=35)
print(f"T-35d range on strict subset: {strict['t35'].min()} to {strict['t35'].max()}")
print(f"All t-35d after 2026-01-01? {(strict['t35'] > '2026-01-01').all()}")
print(f"All t-35d after Haiku training cutoff (Jan 2026)? Mostly NO. {(strict['t35'] > '2026-01-01').sum()} of {len(strict)}")
