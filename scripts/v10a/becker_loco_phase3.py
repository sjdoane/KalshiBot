"""Phase 3 LOCO + sanity checks, single-scan version.

Strategy:
- Read all promising cells from Phase 2.
- One SQL query: for each (group, role, side, price_band, series_prefix), compute
  n, contracts, mean, sd, sum_pnl of net_excess. The cross-product of grouping keys
  is small enough to fit in memory.
- In Python: for each cell, identify largest series_prefix, compute LOCO mean and SE.

Outputs research/v10a/05-phase3-loco.csv + summary JSON.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

BASE = Path(r"C:/Users/SamJD/OneDrive/Desktop/AI Projects/Project Kalshi")
BECKER = BASE / "prediction-market-analysis"
TRADES_DIR = BECKER / "data" / "kalshi" / "trades"
MARKETS_DIR = BECKER / "data" / "kalshi" / "markets"
OUT_DIR = BASE / "research" / "v10a"

sys.path.insert(0, str(BECKER))
from src.analysis.kalshi.util.categories import CATEGORY_SQL, get_group  # noqa: E402

con = duckdb.connect(":memory:")
con.execute("PRAGMA threads=8")
con.execute("PRAGMA memory_limit='10GB'")
cat_sql = CATEGORY_SQL.replace("event_ticker", "m.event_ticker")

cells = pd.read_csv(OUT_DIR / "05-phase2-cells.csv")
promising = cells[(cells["n_trades"] >= 100) & (cells["net_ci_low_pp"] > 0)].copy()
top_groups = sorted(promising["group"].unique())
print(f"Promising cells: {len(promising)}, in groups: {top_groups}", flush=True)

# Build categories-per-group mapping
all_cats_q = f"""
    SELECT DISTINCT {cat_sql} AS category
    FROM '{MARKETS_DIR.as_posix()}/*.parquet' m
    WHERE status = 'finalized' AND result IN ('yes','no')
"""
all_cats = con.execute(all_cats_q).df()
all_cats["group"] = all_cats["category"].apply(get_group)
cats_in_top_groups = all_cats[all_cats["group"].isin(top_groups)]["category"].tolist()
cats_quoted = ",".join(f"'{c}'" for c in cats_in_top_groups)
print(f"Categories in top groups: {len(cats_in_top_groups)}", flush=True)

# ONE SQL: aggregate by (category, role, side, price_band, series_prefix)
t0 = time.time()
agg_q = f"""
    WITH resolved AS (
        SELECT ticker, event_ticker, result
        FROM '{MARKETS_DIR.as_posix()}/*.parquet'
        WHERE status='finalized' AND result IN ('yes','no')
    ),
    joined AS (
        SELECT
            t.ticker, t.taker_side, t.yes_price, t.no_price, t.count,
            m.result,
            {cat_sql} AS category
        FROM '{TRADES_DIR.as_posix()}/*.parquet' t
        INNER JOIN resolved m ON t.ticker = m.ticker
        WHERE t.created_time >= TIMESTAMP '2024-10-01'
          AND t.yes_price IS NOT NULL
          AND t.no_price IS NOT NULL
          AND t.yes_price + t.no_price = 100
          AND t.count > 0
          AND {cat_sql} IN ({cats_quoted})
    ),
    taker AS (
        SELECT
            ticker, category, count,
            taker_side AS side,
            (CASE WHEN taker_side='yes' THEN yes_price ELSE no_price END)/100.0 AS price,
            (CASE WHEN taker_side=result THEN 1.0 ELSE 0.0 END) AS won,
            'taker' AS role
        FROM joined
    ),
    maker AS (
        SELECT
            ticker, category, count,
            CASE WHEN taker_side='yes' THEN 'no' ELSE 'yes' END AS side,
            (CASE WHEN taker_side='yes' THEN no_price ELSE yes_price END)/100.0 AS price,
            (CASE WHEN taker_side!=result THEN 1.0 ELSE 0.0 END) AS won,
            'maker' AS role
        FROM joined
    ),
    combined AS (
        SELECT * FROM taker UNION ALL SELECT * FROM maker
    ),
    with_band AS (
        SELECT
            split_part(ticker, '-', 1) AS series_prefix,
            category, role, side,
            price, won, count,
            CASE
                WHEN price < 0.05 THEN '[0,0.05)'
                WHEN price < 0.20 THEN '[0.05,0.20)'
                WHEN price < 0.40 THEN '[0.20,0.40)'
                WHEN price < 0.60 THEN '[0.40,0.60)'
                WHEN price < 0.80 THEN '[0.60,0.80)'
                WHEN price < 0.95 THEN '[0.80,0.95)'
                ELSE '[0.95,1]'
            END AS price_band,
            CASE
                WHEN role='taker' THEN CEIL(0.07 * price * (1-price) * 100) / 100.0
                ELSE CEIL(0.0175 * price * (1-price) * 100) / 100.0
            END AS fee
        FROM combined
    )
    SELECT
        series_prefix, category, role, side, price_band,
        COUNT(*) AS n,
        SUM(count) AS contracts,
        AVG(won - price - fee) AS net_mean,
        STDDEV(won - price - fee) AS net_sd,
        AVG(won) AS win_rate,
        AVG(price) AS avg_price,
        SUM(count * (won - price - fee)) AS pnl_contrib
    FROM with_band
    GROUP BY series_prefix, category, role, side, price_band
"""
print("Running grouped aggregation...", flush=True)
df_agg = con.execute(agg_q).df()
print(f"Aggregation done in {time.time()-t0:.1f}s, {len(df_agg):,} rows", flush=True)
df_agg["group"] = df_agg["category"].apply(get_group)

# Save the aggregate for later analysis
df_agg.to_parquet(OUT_DIR / "05-phase3-prefix-agg.parquet")

# Per-cell LOCO
print("Running per-cell LOCO + twin-cell control...", flush=True)
loco_rows = []
for _, cell in promising.iterrows():
    cell_group = cell["group"]
    role = cell["role"]
    side = cell["side"]
    band = cell["price_band"]
    cell_rows = df_agg[
        (df_agg["group"] == cell_group)
        & (df_agg["role"] == role)
        & (df_agg["side"] == side)
        & (df_agg["price_band"] == band)
    ].copy()
    if cell_rows.empty:
        loco_rows.append({**cell.to_dict(), "loco_skipped": "empty_after_match"})
        continue
    # Aggregate by series_prefix only
    by_prefix = (
        cell_rows.groupby("series_prefix", as_index=False)
        .apply(
            lambda g: pd.Series({
                "n": int(g["n"].sum()),
                "contracts": int(g["contracts"].sum()),
                "net_mean": float((g["net_mean"] * g["n"]).sum() / max(g["n"].sum(), 1)),
                # Pooled variance across categories within this prefix
                "net_var": float(
                    ((g["n"] * (g["net_sd"] ** 2 + (g["net_mean"] - (g["net_mean"] * g["n"]).sum() / max(g["n"].sum(), 1)) ** 2)).sum())
                    / max(g["n"].sum(), 1)
                ),
                "pnl_contrib": float(g["pnl_contrib"].sum()),
            }),
            include_groups=False,
        )
        .reset_index(drop=False)
    )
    by_prefix["net_sd"] = np.sqrt(by_prefix["net_var"])
    by_prefix = by_prefix.sort_values("n", ascending=False)
    total_n = int(by_prefix["n"].sum())
    if total_n < 30:
        loco_rows.append({**cell.to_dict(), "loco_skipped": f"total_n={total_n}"})
        continue
    largest = by_prefix.iloc[0]
    largest_prefix = largest["series_prefix"]
    largest_share = float(largest["n"] / total_n)
    # WITH all
    net_mean_with = (by_prefix["n"] * by_prefix["net_mean"]).sum() / total_n
    var_with = ((by_prefix["n"] * (by_prefix["net_sd"] ** 2 + (by_prefix["net_mean"] - net_mean_with) ** 2)).sum()) / total_n
    se_with = float(np.sqrt(var_with / total_n))
    # WITHOUT largest
    without = by_prefix.iloc[1:]
    n_without = int(without["n"].sum())
    if n_without < 30:
        loco_rows.append({
            **cell.to_dict(),
            "loco_skipped": f"n_without={n_without}",
            "largest_prefix": str(largest_prefix),
            "largest_share": largest_share,
        })
        continue
    net_mean_without = (without["n"] * without["net_mean"]).sum() / n_without
    var_without = ((without["n"] * (without["net_sd"] ** 2 + (without["net_mean"] - net_mean_without) ** 2)).sum()) / n_without
    se_without = float(np.sqrt(var_without / n_without))

    # Top-3 series prefixes by abs pnl_contrib
    top3 = by_prefix.reindex(by_prefix["pnl_contrib"].abs().nlargest(3).index)
    abs_total = float(by_prefix["pnl_contrib"].abs().sum())
    top3_share = float(top3["pnl_contrib"].abs().sum() / abs_total) if abs_total > 0 else float("nan")
    top3_prefixes = top3["series_prefix"].tolist()

    # Twin cell (opposite side) at the (group, role, band)
    twin_side = "yes" if side == "no" else "no"
    twin = cells[
        (cells["group"] == cell_group)
        & (cells["role"] == role)
        & (cells["side"] == twin_side)
        & (cells["price_band"] == band)
    ]
    twin_net_mean = float(twin["net_mean_pp"].iloc[0]) if len(twin) > 0 else float("nan")
    twin_n = int(twin["n_trades"].iloc[0]) if len(twin) > 0 else 0

    # Top 5 prefixes for domain coverage
    top5_dom = by_prefix.head(5)[["series_prefix", "n"]].copy()
    top5_dom["share"] = top5_dom["n"] / total_n
    domain_top5 = list(zip(top5_dom["series_prefix"].tolist(), top5_dom["share"].round(4).tolist()))

    loco_rows.append({
        **cell.to_dict(),
        "largest_prefix": str(largest_prefix),
        "largest_share": largest_share,
        "n_with": total_n,
        "net_mean_pp_with": net_mean_with * 100,
        "net_ci_low_pp_with": (net_mean_with - 1.96 * se_with) * 100,
        "net_ci_high_pp_with": (net_mean_with + 1.96 * se_with) * 100,
        "n_without": n_without,
        "net_mean_pp_without": net_mean_without * 100,
        "net_ci_low_pp_without": (net_mean_without - 1.96 * se_without) * 100,
        "net_ci_high_pp_without": (net_mean_without + 1.96 * se_without) * 100,
        "pass_loco": bool(net_mean_without - 1.96 * se_without > 0),
        "top3_prefixes": str(top3_prefixes),
        "top3_share_of_abs_pnl": top3_share,
        "twin_side": twin_side,
        "twin_n_trades": twin_n,
        "twin_net_mean_pp": twin_net_mean,
        "domain_top5": str(domain_top5),
    })

print(f"LOCO loop done", flush=True)
loco_df = pd.DataFrame(loco_rows)
loco_df.to_csv(OUT_DIR / "05-phase3-loco.csv", index=False)

survivors = loco_df[loco_df.get("pass_loco", False) == True]  # noqa: E712
print(f"\nSurvivors (LOCO pass net CI > 0): {len(survivors)}")
if not survivors.empty:
    print(
        survivors[
            ["group", "role", "side", "price_band", "n_trades", "avg_price",
             "net_mean_pp", "largest_prefix", "largest_share",
             "net_mean_pp_without", "net_ci_low_pp_without",
             "twin_net_mean_pp", "top3_share_of_abs_pnl"]
        ].to_string(index=False)
    )

# Diagnostic: sum side=NO + side=YES net_mean for each (group, role, band)
print("\n=== Side-symmetry diagnostic (NO + YES sums to ~maker headline excess) ===")
diag = cells.groupby(["group", "role", "price_band"]).agg(
    n_yes=("n_trades", lambda x: x[cells.loc[x.index, "side"] == "yes"].sum() if any(cells.loc[x.index, "side"] == "yes") else 0),
    n_no=("n_trades", lambda x: x[cells.loc[x.index, "side"] == "no"].sum() if any(cells.loc[x.index, "side"] == "no") else 0),
).reset_index()
# Easier: pivot
pv = cells.pivot_table(index=["group", "role", "price_band"], columns="side",
                       values=["n_trades", "net_mean_pp", "win_rate", "avg_price"]).reset_index()
pv.columns = ["_".join(map(str, c)).rstrip("_") for c in pv.columns]
# Weighted average over sides
def weighted_combined(row):
    n_yes = row.get("n_trades_yes", 0) or 0
    n_no = row.get("n_trades_no", 0) or 0
    if n_yes + n_no == 0:
        return float("nan")
    m_yes = row.get("net_mean_pp_yes", 0) or 0
    m_no = row.get("net_mean_pp_no", 0) or 0
    return (n_yes * m_yes + n_no * m_no) / (n_yes + n_no)
pv["combined_net_mean_pp"] = pv.apply(weighted_combined, axis=1)
pv.to_csv(OUT_DIR / "05-side-symmetry-by-band.csv", index=False)
print(pv[["group", "role", "price_band", "n_trades_yes", "n_trades_no",
          "net_mean_pp_yes", "net_mean_pp_no", "combined_net_mean_pp"]].to_string(index=False))

summary = {
    "n_promising_in": int(len(promising)),
    "n_survivors_loco": int(len(survivors)),
    "survivors": survivors.head(50).to_dict(orient="records") if not survivors.empty else [],
}
with open(OUT_DIR / "05-phase3-summary.json", "w") as f:
    json.dump(summary, f, indent=2, default=str)
print(f"\nWrote {OUT_DIR / '05-phase3-loco.csv'}, {OUT_DIR / '05-phase3-summary.json'}, {OUT_DIR / '05-side-symmetry-by-band.csv'}")
