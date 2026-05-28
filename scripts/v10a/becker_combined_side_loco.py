"""Combined-side LOCO: for each (group, role, price_band), compute the net excess
that a side-agnostic maker would achieve (averaging YES and NO fills), and run
LOCO on the largest series_prefix.

This addresses the F11-flavored selection: the within-band "side=no" cells looked
massive because of resolution-base-rate asymmetry. A real maker-quoting bot fills
on both sides as orderflow arrives; the effective edge is the COMBINED average.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

BASE = Path(r"C:/Users/SamJD/OneDrive/Desktop/AI Projects/Project Kalshi")
OUT_DIR = BASE / "research" / "v10a"
sys.path.insert(0, str(BASE / "prediction-market-analysis"))
from src.analysis.kalshi.util.categories import get_group  # noqa: E402

# Load the prefix-level aggregate from Phase 3
df_agg = pd.read_parquet(OUT_DIR / "05-phase3-prefix-agg.parquet")
df_agg["group"] = df_agg["category"].apply(get_group)

# Aggregate over (group, role, price_band, series_prefix), pooling both sides
print("Computing combined-side aggregate by (group, role, price_band, series_prefix)", flush=True)
rows = []
for (grp, role, band, prefix), g in df_agg.groupby(["group", "role", "price_band", "series_prefix"], observed=True):
    n = int(g["n"].sum())
    if n == 0:
        continue
    contracts = int(g["contracts"].sum())
    # Weighted net mean across sides
    net_mean = float((g["net_mean"] * g["n"]).sum() / n)
    # Pooled variance
    var = float(((g["n"] * (g["net_sd"] ** 2 + (g["net_mean"] - net_mean) ** 2)).sum()) / n)
    pnl = float(g["pnl_contrib"].sum())
    avg_price = float((g["avg_price"] * g["n"]).sum() / n)
    win = float((g["win_rate"] * g["n"]).sum() / n)
    rows.append({
        "group": grp, "role": role, "price_band": band, "series_prefix": prefix,
        "n": n, "contracts": contracts, "avg_price": avg_price, "win_rate": win,
        "net_mean": net_mean, "net_sd": float(np.sqrt(var)), "pnl_contrib": pnl,
    })
df_combined = pd.DataFrame(rows)

# Per-cell aggregation: (group, role, price_band)
print("Per-cell combined-side mean and LOCO", flush=True)
out = []
for (grp, role, band), g in df_combined.groupby(["group", "role", "price_band"]):
    g = g.sort_values("n", ascending=False)
    total_n = int(g["n"].sum())
    if total_n < 100:
        continue
    n_prefixes = len(g)
    largest_prefix = g.iloc[0]["series_prefix"]
    largest_n = int(g.iloc[0]["n"])
    largest_share = largest_n / total_n
    avg_price = float((g["avg_price"] * g["n"]).sum() / total_n)
    win = float((g["win_rate"] * g["n"]).sum() / total_n)
    # WITH all
    net_mean_with = (g["n"] * g["net_mean"]).sum() / total_n
    var_with = ((g["n"] * (g["net_sd"] ** 2 + (g["net_mean"] - net_mean_with) ** 2)).sum()) / total_n
    se_with = float(np.sqrt(var_with / total_n))
    # WITHOUT largest
    without = g.iloc[1:]
    n_without = int(without["n"].sum())
    if n_without < 30:
        continue
    net_mean_without = (without["n"] * without["net_mean"]).sum() / n_without
    var_without = ((without["n"] * (without["net_sd"] ** 2 + (without["net_mean"] - net_mean_without) ** 2)).sum()) / n_without
    se_without = float(np.sqrt(var_without / n_without))
    # Top-3 prefixes
    top3_idx = g["pnl_contrib"].abs().nlargest(3).index
    top3_prefixes = g.loc[top3_idx, "series_prefix"].tolist()
    abs_total = float(g["pnl_contrib"].abs().sum())
    top3_share = float(g.loc[top3_idx, "pnl_contrib"].abs().sum() / abs_total) if abs_total > 0 else float("nan")
    # Top 5 by n
    top5 = g.head(5)[["series_prefix", "n"]].copy()
    top5["share"] = top5["n"] / total_n
    domain_top5 = list(zip(top5["series_prefix"].tolist(), top5["share"].round(4).tolist()))
    out.append({
        "group": grp, "role": role, "price_band": band,
        "n_trades": total_n, "n_prefixes": n_prefixes,
        "avg_price": avg_price, "win_rate": win,
        "net_mean_pp": net_mean_with * 100,
        "net_se_pp": se_with * 100,
        "net_ci_low_pp": (net_mean_with - 1.96 * se_with) * 100,
        "net_ci_high_pp": (net_mean_with + 1.96 * se_with) * 100,
        "pass_gate": bool(net_mean_with - 1.96 * se_with > 0),
        "largest_prefix": str(largest_prefix),
        "largest_share": largest_share,
        "n_without": n_without,
        "net_mean_pp_without": net_mean_without * 100,
        "net_ci_low_pp_without": (net_mean_without - 1.96 * se_without) * 100,
        "net_ci_high_pp_without": (net_mean_without + 1.96 * se_without) * 100,
        "pass_loco": bool(net_mean_without - 1.96 * se_without > 0),
        "top3_prefixes": str(top3_prefixes),
        "top3_share_of_abs_pnl": top3_share,
        "domain_top5": str(domain_top5),
    })

df_out = pd.DataFrame(out).sort_values("net_mean_pp", ascending=False)
df_out.to_csv(OUT_DIR / "05-phase4-combined-side-loco.csv", index=False)

# Filter to passes BOTH gate AND loco AND positive direction
keepers = df_out[
    (df_out["net_ci_low_pp"] > 0)
    & (df_out["pass_loco"])
    & (df_out["top3_share_of_abs_pnl"] < 0.5)  # not concentrated in <=3 prefixes
].copy()
print(f"\nCombined-side cells passing all gates: {len(keepers)} of {len(df_out)}")
if not keepers.empty:
    print(keepers[
        ["group", "role", "price_band", "n_trades", "n_prefixes",
         "avg_price", "win_rate", "net_mean_pp", "net_ci_low_pp", "net_ci_high_pp",
         "largest_prefix", "largest_share",
         "net_mean_pp_without", "net_ci_low_pp_without",
         "top3_share_of_abs_pnl", "domain_top5"]
    ].to_string(index=False))

# Also show maker cells with CI_low > 0 even if don't pass concentration filter
maker_pass = df_out[(df_out["role"] == "maker") & (df_out["net_ci_low_pp"] > 0) & (df_out["pass_loco"])].copy()
print(f"\n--- ALL maker combined-side cells with CI>0 AND LOCO pass: {len(maker_pass)} ---")
print(maker_pass[
    ["group", "price_band", "n_trades", "n_prefixes",
     "avg_price", "win_rate", "net_mean_pp", "net_ci_low_pp",
     "largest_prefix", "largest_share",
     "net_mean_pp_without", "net_ci_low_pp_without",
     "top3_share_of_abs_pnl"]
].to_string(index=False))

summary = {
    "all_passers": maker_pass.to_dict(orient="records"),
    "concentration_passers": keepers.to_dict(orient="records"),
}
with open(OUT_DIR / "05-phase4-combined-loco.json", "w") as f:
    json.dump(summary, f, indent=2, default=str)
print(f"\nWrote {OUT_DIR/'05-phase4-combined-side-loco.csv'} and {OUT_DIR/'05-phase4-combined-loco.json'}")
