"""Diagnostic: inspect forecast distribution and per-series patterns."""
import pandas as pd
import numpy as np
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
df = pd.read_parquet(ROOT / "data" / "v4" / "llm_phase2_forecasts.parquet")
print("shape:", df.shape)

# Where LLM thinks YES is unlikely (prob_yes < 0.30) and Kalshi at >0.70
fade_candidates = df[df["prob_yes"] < df["favorite_price"] - 0.30]
print()
print("Strong-fade candidates (LLM < Kalshi by 0.30+):")
print(fade_candidates[["ticker", "prob_yes", "favorite_price", "outcome"]].to_string())
print("  yes rate in strong-fade:", fade_candidates["outcome"].mean(), "n=", len(fade_candidates))

# Per series breakdown
print()
print("Per-series Brier vs Kalshi:")
for series, g in df.groupby("series_ticker"):
    if len(g) >= 5:
        b_llm = float(((g["prob_yes"] - g["outcome"])**2).mean())
        b_kalshi = float(((g["favorite_price"] - g["outcome"])**2).mean())
        yr = g["outcome"].mean()
        print(f"  {series:25s} n={len(g):3d} yes_rate={yr:.2f} Brier_LLM={b_llm:.3f} Brier_Kalshi={b_kalshi:.3f} diff={b_kalshi - b_llm:+.3f}")

# Calibration buckets
print()
print("Calibration by LLM prob bucket:")
df["llm_bucket"] = pd.cut(df["prob_yes"], bins=[0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0])
for bk, g in df.groupby("llm_bucket", observed=True):
    if len(g) >= 3:
        print(f"  {bk}: n={len(g)} mean_llm={g['prob_yes'].mean():.3f} yes_rate={g['outcome'].mean():.3f}")

# Try Platt-style scaling: rescale to push LLM probs toward 1.0 (extremize)
print()
print("Platt scaling: p_new = sigmoid(logit(p) * scale + bias):")
p = df["prob_yes"].clip(0.001, 0.999).to_numpy()
y = df["outcome"].to_numpy()
logit = np.log(p / (1 - p))
for bias in [0.0, 0.5, 1.0, 1.5, 2.0]:
    for scale in [0.5, 1.0, 1.5]:
        scaled = 1.0 / (1.0 + np.exp(-(logit * scale + bias)))
        b = float(((scaled - y)**2).mean())
        print(f"  bias={bias:.1f} scale={scale:.1f}: mean={scaled.mean():.3f} Brier={b:.4f}")

# Shift up by constant offset
print()
print("Mean shift up by offset:")
for offset in [0.0, 0.1, 0.2, 0.3, 0.4, 0.5]:
    p2 = np.clip(p + offset, 0.001, 0.999)
    b = float(((p2 - y)**2).mean())
    print(f"  offset=+{offset:.1f}: mean={p2.mean():.3f} Brier={b:.4f}")

# Per-series, would a fade-only strategy with LLM_prob < 0.40 work?
print()
print("Strong-fade outcomes by series (LLM<0.40, would skip v1 buy):")
strong_fade_all = df[df["prob_yes"] < 0.40]
print(f"  Total strong-fade: n={len(strong_fade_all)}, would-skip-yes_rate={strong_fade_all['outcome'].mean():.3f}")
print(f"  Without LLM intervention, these would be v1 trades at avg price {strong_fade_all['favorite_price'].mean():.3f}")
print(f"  Their realized P&L if v1 had taken them (gross, no fees): ")
g = strong_fade_all
realized = g["outcome"] - g["favorite_price"]
print(f"    mean={realized.mean():+.4f}  n_pos={(realized>0).sum()}/{len(g)}")

# Reverse logic: when LLM agrees (prob_yes >= price), should v1 trade?
print()
print("Take-when-LLM-agrees (prob_yes >= favorite_price):")
agree = df[df["prob_yes"] >= df["favorite_price"]]
print(f"  n={len(agree)}, yes_rate={agree['outcome'].mean()}")
