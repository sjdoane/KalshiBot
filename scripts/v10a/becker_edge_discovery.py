"""Becker edge discovery: find (category, price band, side) cells with
post-Oct-2024 net excess return > 0 with CI excluding zero.

Memory-safe SQL-first design:
- Phase 1: SQL aggregate by category (group via Python post-pass).
- Phase 2: SQL aggregate by (group, role, side, price_band) including mean/variance
  for parametric CI. n_trades is typically large (>>100) so CLT is fine.
- Phase 3: For each passing cell, pull only that cell's individual trades (smaller),
  do LOCO bootstrap.
- Phase 4: Sanity checks: yes+no=100 invariance (filtered), domain coverage,
  top-3 LOO contribution.

Outputs in research/v10a/.
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
OUT_DIR.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(BECKER))
from src.analysis.kalshi.util.categories import CATEGORY_SQL, get_group  # noqa: E402


def bootstrap_ci(arr: np.ndarray, n_boot: int = 2000, alpha: float = 0.05, seed: int = 42) -> tuple[float, float, float]:
    """Block-friendly bootstrap. For large n (>50k), chunks the bootstrap to keep RAM bounded.

    Memory of naive impl is O(n_boot * n) ints, which is 7.5GB for n=470k, n_boot=2000.
    Chunked version uses O(chunk_size * n) ints per chunk; chunk_size=200 is ~750MB for that size.
    """
    rng = np.random.default_rng(seed)
    n = len(arr)
    if n < 5:
        return float(arr.mean()) if n > 0 else 0.0, float("nan"), float("nan")
    # For very large arrays, switch to parametric Wald (CLT is valid)
    if n > 200_000:
        m = float(arr.mean())
        se = float(arr.std(ddof=1) / np.sqrt(n))
        return m, m - 1.96 * se, m + 1.96 * se
    # Chunked bootstrap
    chunk = min(200, n_boot)
    means_chunks = []
    remaining = n_boot
    while remaining > 0:
        c = min(chunk, remaining)
        idx = rng.integers(0, n, size=(c, n))
        means_chunks.append(arr[idx].mean(axis=1))
        remaining -= c
    means = np.concatenate(means_chunks)
    return float(arr.mean()), float(np.quantile(means, alpha / 2)), float(np.quantile(means, 1 - alpha / 2))


def main():
    con = duckdb.connect(":memory:")
    con.execute("PRAGMA threads=8")
    con.execute("PRAGMA memory_limit='12GB'")

    cat_sql = CATEGORY_SQL.replace("event_ticker", "m.event_ticker")

    print("=== PHASE 1: category headline (post-Oct-2024, resolved markets) ===", flush=True)
    t0 = time.time()
    p1_q = f"""
        WITH resolved AS (
            SELECT ticker, event_ticker, result
            FROM '{MARKETS_DIR.as_posix()}/*.parquet'
            WHERE status = 'finalized' AND result IN ('yes','no')
        ),
        joined AS (
            SELECT
                t.taker_side,
                t.yes_price,
                t.no_price,
                t.count,
                m.result,
                {cat_sql} AS category
            FROM '{TRADES_DIR.as_posix()}/*.parquet' t
            INNER JOIN resolved m ON t.ticker = m.ticker
            WHERE t.created_time >= TIMESTAMP '2024-10-01'
              AND t.yes_price IS NOT NULL
              AND t.no_price IS NOT NULL
              AND t.yes_price + t.no_price = 100
              AND t.count > 0
        ),
        taker AS (
            SELECT category,
                AVG((CASE WHEN taker_side='yes' THEN yes_price ELSE no_price END)/100.0) AS avg_price,
                AVG(CASE WHEN taker_side=result THEN 1.0 ELSE 0.0 END) AS win_rate,
                AVG(
                    (CASE WHEN taker_side=result THEN 1.0 ELSE 0.0 END)
                    - (CASE WHEN taker_side='yes' THEN yes_price ELSE no_price END)/100.0
                ) AS excess,
                STDDEV(
                    (CASE WHEN taker_side=result THEN 1.0 ELSE 0.0 END)
                    - (CASE WHEN taker_side='yes' THEN yes_price ELSE no_price END)/100.0
                ) AS sd,
                COUNT(*) AS n,
                SUM(count) AS contracts
            FROM joined GROUP BY category
        ),
        maker AS (
            SELECT category,
                AVG((CASE WHEN taker_side='yes' THEN no_price ELSE yes_price END)/100.0) AS avg_price,
                AVG(CASE WHEN taker_side!=result THEN 1.0 ELSE 0.0 END) AS win_rate,
                AVG(
                    (CASE WHEN taker_side!=result THEN 1.0 ELSE 0.0 END)
                    - (CASE WHEN taker_side='yes' THEN no_price ELSE yes_price END)/100.0
                ) AS excess,
                STDDEV(
                    (CASE WHEN taker_side!=result THEN 1.0 ELSE 0.0 END)
                    - (CASE WHEN taker_side='yes' THEN no_price ELSE yes_price END)/100.0
                ) AS sd,
                COUNT(*) AS n,
                SUM(count) AS contracts
            FROM joined GROUP BY category
        )
        SELECT 'taker' AS role, * FROM taker
        UNION ALL
        SELECT 'maker' AS role, * FROM maker
    """
    p1_raw = con.execute(p1_q).df()
    print(f"  query took {time.time()-t0:.1f}s, {len(p1_raw)} category-role rows", flush=True)

    p1_raw["group"] = p1_raw["category"].apply(get_group)
    # Weighted aggregate by group
    agg_rows = []
    for (role, grp), g in p1_raw.groupby(["role", "group"], observed=True):
        n = g["n"].sum()
        if n == 0:
            continue
        # Weighted mean and pooled variance
        wmean = (g["excess"] * g["n"]).sum() / n
        # Pooled within-category variance: sum(n_i * (sd_i^2 + (mean_i - wmean)^2)) / n
        pooled_var = ((g["n"] * (g["sd"] ** 2 + (g["excess"] - wmean) ** 2)).sum()) / n
        sd = float(np.sqrt(pooled_var))
        se = sd / np.sqrt(n)
        wprice = (g["avg_price"] * g["n"]).sum() / n
        agg_rows.append(
            {
                "role": role,
                "group": grp,
                "n_trades": int(n),
                "contracts": int(g["contracts"].sum()),
                "avg_price": float(wprice),
                "excess_pp": float(wmean * 100),
                "sd_pp": sd * 100,
                "se_pp": se * 100,
                "ci_low_pp": float((wmean - 1.96 * se) * 100),
                "ci_high_pp": float((wmean + 1.96 * se) * 100),
            }
        )
    p1_group = pd.DataFrame(agg_rows)
    p1_pivot = p1_group.pivot(index="group", columns="role")
    p1_pivot.columns = [f"{role}_{col}" for col, role in p1_pivot.columns]
    p1_pivot = p1_pivot.reset_index().sort_values("maker_excess_pp", ascending=False)
    p1_pivot.to_csv(OUT_DIR / "05-phase1-category-headline.csv", index=False)
    print(p1_pivot.to_string(index=False), flush=True)

    eligible = p1_pivot[p1_pivot["maker_n_trades"].fillna(0) >= 5000].copy()
    top_groups = eligible.head(6)["group"].tolist()
    print(f"\n[phase2] top groups by maker_excess (n>=5000): {top_groups}", flush=True)

    print("\n=== PHASE 2: sub-cells by (group, role, side, price_band) ===", flush=True)
    # Build price-band CASE and side label inside SQL
    # Side from actor perspective:
    # - taker role: side = taker_side (yes or no)
    # - maker role: side = OPPOSITE of taker_side
    # Price (what actor paid per contract): same as Phase 1 logic.
    # Returns: gross excess + fee + net excess
    # Fee: taker = ceil(0.07*p*(1-p)*100)/100 dollars, maker = ceil(0.0175*p*(1-p)*100)/100

    # Build category-to-group mapping as a SQL CASE
    # (Avoid pulling category strings then re-aggregating: do it in SQL)
    # Simpler: pull category aggregate again, but we still need price_band groupby in SQL,
    # so we'll filter by category prefix in WHERE.
    # Build set of category prefixes for the top groups via SUBCATEGORY_PATTERNS
    from src.analysis.kalshi.util.categories import SUBCATEGORY_PATTERNS
    prefix_to_group = {}
    for pat, grp, _, _ in SUBCATEGORY_PATTERNS:
        prefix_to_group[pat] = grp
    selected_prefixes = [pat for pat, grp in prefix_to_group.items() if grp in top_groups]
    print(f"[phase2] {len(selected_prefixes)} category prefixes selected", flush=True)

    # Strategy: Phase 2 computes aggregates only (mean, var, n) per cell.
    # We'll match the joined trade's category to a group by doing a Python-side post-filter
    # on (price_band, role, side, category), then group-by-Python at the (group, role, side, band) level.

    t0 = time.time()
    p2_q = f"""
        WITH resolved AS (
            SELECT ticker, event_ticker, result
            FROM '{MARKETS_DIR.as_posix()}/*.parquet'
            WHERE status = 'finalized' AND result IN ('yes','no')
        ),
        joined AS (
            SELECT
                t.taker_side,
                t.yes_price,
                t.no_price,
                t.count,
                m.result,
                {cat_sql} AS category
            FROM '{TRADES_DIR.as_posix()}/*.parquet' t
            INNER JOIN resolved m ON t.ticker = m.ticker
            WHERE t.created_time >= TIMESTAMP '2024-10-01'
              AND t.yes_price IS NOT NULL
              AND t.no_price IS NOT NULL
              AND t.yes_price + t.no_price = 100
              AND t.count > 0
        ),
        -- TAKER perspective
        taker AS (
            SELECT
                category,
                taker_side AS side,
                (CASE WHEN taker_side='yes' THEN yes_price ELSE no_price END)/100.0 AS price,
                (CASE WHEN taker_side=result THEN 1.0 ELSE 0.0 END) AS won,
                count
            FROM joined
        ),
        -- MAKER perspective (the counterparty)
        maker AS (
            SELECT
                category,
                CASE WHEN taker_side='yes' THEN 'no' ELSE 'yes' END AS side,
                (CASE WHEN taker_side='yes' THEN no_price ELSE yes_price END)/100.0 AS price,
                (CASE WHEN taker_side!=result THEN 1.0 ELSE 0.0 END) AS won,
                count
            FROM joined
        ),
        combined AS (
            SELECT 'taker' AS role, category, side, price, won, count FROM taker
            UNION ALL
            SELECT 'maker' AS role, category, side, price, won, count FROM maker
        ),
        with_band AS (
            SELECT
                role, category, side, price, won, count,
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
                END AS fee,
                (won - price) AS gross_excess
            FROM combined
        )
        SELECT
            role, category, side, price_band,
            COUNT(*) AS n,
            SUM(count) AS contracts,
            AVG(price) AS avg_price,
            AVG(fee) AS avg_fee,
            AVG(gross_excess) AS gross_mean,
            STDDEV(gross_excess) AS gross_sd,
            AVG(gross_excess - fee) AS net_mean,
            STDDEV(gross_excess - fee) AS net_sd,
            AVG(won) AS win_rate
        FROM with_band
        GROUP BY role, category, side, price_band
    """
    p2_raw = con.execute(p2_q).df()
    print(f"  Phase 2 SQL took {time.time()-t0:.1f}s, {len(p2_raw)} (category,role,side,band) rows", flush=True)
    p2_raw["group"] = p2_raw["category"].apply(get_group)
    # Filter to top groups
    p2_raw = p2_raw[p2_raw["group"].isin(top_groups)].copy()

    # Aggregate to (group, role, side, price_band)
    rows = []
    for keys, g in p2_raw.groupby(["group", "role", "side", "price_band"], observed=True):
        n = g["n"].sum()
        if n == 0:
            continue
        # Weighted mean
        gross_mean = (g["gross_mean"] * g["n"]).sum() / n
        net_mean = (g["net_mean"] * g["n"]).sum() / n
        # Pooled within-category variance
        gross_var = ((g["n"] * (g["gross_sd"] ** 2 + (g["gross_mean"] - gross_mean) ** 2)).sum()) / n
        net_var = ((g["n"] * (g["net_sd"] ** 2 + (g["net_mean"] - net_mean) ** 2)).sum()) / n
        gross_se = float(np.sqrt(gross_var / n))
        net_se = float(np.sqrt(net_var / n))
        avg_price = (g["avg_price"] * g["n"]).sum() / n
        avg_fee = (g["avg_fee"] * g["n"]).sum() / n
        win_rate = (g["win_rate"] * g["n"]).sum() / n
        rows.append(
            {
                "group": keys[0],
                "role": keys[1],
                "side": keys[2],
                "price_band": keys[3],
                "n_trades": int(n),
                "n_contracts": int(g["contracts"].sum()),
                "avg_price": float(avg_price),
                "win_rate": float(win_rate),
                "avg_fee_per_contract": float(avg_fee),
                "gross_mean_pp": float(gross_mean * 100),
                "gross_ci_low_pp": float((gross_mean - 1.96 * gross_se) * 100),
                "gross_ci_high_pp": float((gross_mean + 1.96 * gross_se) * 100),
                "net_mean_pp": float(net_mean * 100),
                "net_se_pp": float(net_se * 100),
                "net_ci_low_pp": float((net_mean - 1.96 * net_se) * 100),
                "net_ci_high_pp": float((net_mean + 1.96 * net_se) * 100),
                # p-value approx (two-sided z)
                "z_net": float(net_mean / net_se) if net_se > 0 else float("nan"),
            }
        )
    cells = pd.DataFrame(rows).sort_values("net_mean_pp", ascending=False)
    cells.to_csv(OUT_DIR / "05-phase2-cells.csv", index=False)
    print(f"  {len(cells)} group-level cells", flush=True)
    print(cells.head(30).to_string(index=False), flush=True)

    # Multiple testing
    n_tested = len(cells)
    bonferroni_alpha = 0.05 / max(n_tested, 1)
    from scipy.stats import norm
    cells["p_two_sided"] = 2 * (1 - norm.cdf(np.abs(cells["z_net"].fillna(0))))
    cells["sig_bonferroni"] = cells["p_two_sided"] < bonferroni_alpha
    # BH FDR q=0.05
    sp = cells["p_two_sided"].sort_values().values
    m = len(sp)
    bh = (np.arange(1, m + 1) / m) * 0.05
    bh_pass = sp < bh
    k_max = 0
    for i, b in enumerate(bh_pass):
        if b:
            k_max = i + 1
    bh_cutoff = sp[k_max - 1] if k_max > 0 else -1.0
    cells["sig_fdr"] = cells["p_two_sided"] <= bh_cutoff
    cells.to_csv(OUT_DIR / "05-phase2-cells-with-mt.csv", index=False)

    # Promising: n>=100, net_ci_low_pp > 0
    promising = cells[(cells["n_trades"] >= 100) & (cells["net_ci_low_pp"] > 0)].copy()
    print(f"\n[phase2 gate] {len(promising)} cells: n>=100 AND net CI excludes zero", flush=True)
    print(f"[phase2 gate] {int(cells['sig_bonferroni'].sum())} cells pass Bonferroni (alpha={bonferroni_alpha:.5f})", flush=True)
    print(f"[phase2 gate] {int(cells['sig_fdr'].sum())} cells pass BH FDR q=0.05", flush=True)
    if not promising.empty:
        print(promising.to_string(index=False), flush=True)

    # PHASE 3: LOCO on each promising cell
    print("\n=== PHASE 3: LOCO on each promising cell ===", flush=True)
    # Build observed-category set per group from p2_raw (more robust than lookup table)
    observed_categories_by_group = (
        p2_raw.groupby("group")["category"].unique().to_dict()
    )

    # Pre-load all trades for the promising groups in ONE query so we don't re-scan
    # the 7214-parquet glob 59 times.
    promising_groups = list(promising["group"].unique())
    all_promising_cats = set()
    for g in promising_groups:
        all_promising_cats.update(observed_categories_by_group.get(g, []))
    cats_quoted_all = ",".join(f"'{p}'" for p in sorted(all_promising_cats))
    print(f"[phase3] pre-loading trades for {len(promising_groups)} groups, "
          f"{len(all_promising_cats)} categories", flush=True)
    t0 = time.time()
    preload_q = f"""
        WITH resolved AS (
            SELECT ticker, event_ticker, result
            FROM '{MARKETS_DIR.as_posix()}/*.parquet'
            WHERE status = 'finalized' AND result IN ('yes','no')
        )
        SELECT
            t.ticker,
            t.taker_side,
            t.yes_price,
            t.no_price,
            t.count,
            m.result,
            m.event_ticker,
            {cat_sql} AS category
        FROM '{TRADES_DIR.as_posix()}/*.parquet' t
        INNER JOIN resolved m ON t.ticker = m.ticker
        WHERE t.created_time >= TIMESTAMP '2024-10-01'
          AND t.yes_price IS NOT NULL
          AND t.no_price IS NOT NULL
          AND t.yes_price + t.no_price = 100
          AND t.count > 0
          AND {cat_sql} IN ({cats_quoted_all})
    """
    df_all = con.execute(preload_q).df()
    print(f"[phase3] pre-loaded {len(df_all):,} trades in {time.time()-t0:.1f}s, "
          f"memory ~{df_all.memory_usage(deep=True).sum()/1e6:.0f} MB", flush=True)
    df_all["group"] = df_all["category"].apply(get_group)
    df_all["series_prefix"] = df_all["ticker"].str.split("-").str[0]

    # Pre-compute taker and maker views of price, won, side, fee
    df_all["taker_price"] = np.where(df_all["taker_side"] == "yes", df_all["yes_price"], df_all["no_price"]) / 100.0
    df_all["taker_won"] = (df_all["taker_side"] == df_all["result"]).astype(float)
    df_all["taker_side_actor"] = df_all["taker_side"]
    df_all["maker_price"] = np.where(df_all["taker_side"] == "yes", df_all["no_price"], df_all["yes_price"]) / 100.0
    df_all["maker_won"] = (df_all["taker_side"] != df_all["result"]).astype(float)
    df_all["maker_side_actor"] = np.where(df_all["taker_side"] == "yes", "no", "yes")

    band_ranges = {
        "[0,0.05)": (0.0, 0.05),
        "[0.05,0.20)": (0.05, 0.20),
        "[0.20,0.40)": (0.20, 0.40),
        "[0.40,0.60)": (0.40, 0.60),
        "[0.60,0.80)": (0.60, 0.80),
        "[0.80,0.95)": (0.80, 0.95),
        "[0.95,1]": (0.95, 1.0001),
    }

    loco_results = []
    for _, cell in promising.iterrows():
        cell_group = cell["group"]
        role = cell["role"]
        side = cell["side"]
        band = cell["price_band"]
        lo, hi = band_ranges[band]

        if role == "taker":
            mask_role = (
                (df_all["group"] == cell_group)
                & (df_all["taker_side_actor"] == side)
                & (df_all["taker_price"] >= lo)
                & (df_all["taker_price"] < hi)
            )
            price_col, won_col = "taker_price", "taker_won"
        else:
            mask_role = (
                (df_all["group"] == cell_group)
                & (df_all["maker_side_actor"] == side)
                & (df_all["maker_price"] >= lo)
                & (df_all["maker_price"] < hi)
            )
            price_col, won_col = "maker_price", "maker_won"
        df_cell = df_all.loc[mask_role, ["ticker", "category", "event_ticker", "series_prefix",
                                          "count", price_col, won_col]].copy()
        df_cell.rename(columns={price_col: "price", won_col: "won"}, inplace=True)
        if df_cell.empty or len(df_cell) < 30:
            loco_results.append(
                {"cell": dict(cell), "loco": {"skipped": True, "reason": f"only {len(df_cell)} trades"}}
            )
            continue
        # Compute fee per role
        if role == "taker":
            df_cell["fee"] = np.ceil(0.07 * df_cell["price"] * (1.0 - df_cell["price"]) * 100.0) / 100.0
        else:
            df_cell["fee"] = np.ceil(0.0175 * df_cell["price"] * (1.0 - df_cell["price"]) * 100.0) / 100.0
        df_cell["net_excess"] = (df_cell["won"] - df_cell["price"]) - df_cell["fee"]

        # Find largest entity (most common series_prefix)
        counts = df_cell["series_prefix"].value_counts()
        largest = counts.index[0]
        share = float(counts.iloc[0] / len(df_cell))
        df_without = df_cell[df_cell["series_prefix"] != largest]
        if len(df_without) < 30:
            loco_results.append(
                {"cell": dict(cell), "loco": {"skipped": True, "largest_entity": largest, "entity_share": share}}
            )
            continue

        net_with = df_cell["net_excess"].to_numpy()
        net_without = df_without["net_excess"].to_numpy()
        m_w, lo_w, hi_w = bootstrap_ci(net_with, n_boot=2000)
        m_wo, lo_wo, hi_wo = bootstrap_ci(net_without, n_boot=2000)

        # Top-3 LOO concentration
        pnl_per_trade = (df_cell["net_excess"] * df_cell["count"]).to_numpy()
        abs_total = float(np.abs(pnl_per_trade).sum())
        top3_idx = np.argsort(np.abs(pnl_per_trade))[::-1][:3]
        top3_share = float(np.abs(pnl_per_trade[top3_idx]).sum() / abs_total) if abs_total > 0 else float("nan")

        # Domain coverage: share of each series prefix
        prefix_share = (counts / len(df_cell)).head(10).to_dict()
        prefix_share = {str(k): float(v) for k, v in prefix_share.items()}

        loco_results.append(
            {
                "cell": dict(cell),
                "loco": {
                    "largest_entity": str(largest),
                    "entity_share": share,
                    "n_with": int(len(df_cell)),
                    "n_without": int(len(df_without)),
                    "net_mean_pp_with": float(m_w * 100),
                    "net_ci_low_pp_with": float(lo_w * 100),
                    "net_ci_high_pp_with": float(hi_w * 100),
                    "net_mean_pp_without": float(m_wo * 100),
                    "net_ci_low_pp_without": float(lo_wo * 100),
                    "net_ci_high_pp_without": float(hi_wo * 100),
                    "pass_loco": bool(lo_wo > 0),
                },
                "top3_loo": {
                    "abs_total_pnl_dollars": abs_total,
                    "top3_share_of_abs_pnl": top3_share,
                },
                "domain_coverage_top10_prefix": prefix_share,
            }
        )

    with open(OUT_DIR / "05-phase3-loco.json", "w") as f:
        json.dump(loco_results, f, indent=2, default=str)
    print(f"\n[phase3] {len(loco_results)} cells tested via LOCO", flush=True)

    # Final survivors
    survivors = [r for r in loco_results if r["loco"].get("pass_loco")]
    print(f"[phase3 gate] {len(survivors)} cells PASS LOCO (CI low without largest entity > 0)", flush=True)
    for s in survivors[:20]:
        c = s["cell"]
        l = s["loco"]
        print(
            f"  {c['group']:14s} {c['role']:5s} {c['side']:3s} band={c['price_band']:<14s} "
            f"n={c['n_trades']:6d}  net_mean={c['net_mean_pp']:+.3f}pp  "
            f"net_CI=[{c['net_ci_low_pp']:+.3f},{c['net_ci_high_pp']:+.3f}]pp  "
            f"LOCO_without={l['net_mean_pp_without']:+.3f}pp  CI=[{l['net_ci_low_pp_without']:+.3f},{l['net_ci_high_pp_without']:+.3f}]"
        )

    summary = {
        "phase1_category_headline": p1_pivot.to_dict(orient="records"),
        "phase2_n_cells": n_tested,
        "phase2_bonferroni_alpha": float(bonferroni_alpha),
        "phase2_passing_count": int(len(promising)),
        "phase2_bonferroni_count": int(cells["sig_bonferroni"].sum()),
        "phase2_fdr_count": int(cells["sig_fdr"].sum()),
        "phase3_loco_pass_count": len(survivors),
        "survivors_summary": [
            {
                "group": s["cell"]["group"],
                "role": s["cell"]["role"],
                "side": s["cell"]["side"],
                "price_band": s["cell"]["price_band"],
                "n_trades": int(s["cell"]["n_trades"]),
                "avg_price": float(s["cell"]["avg_price"]),
                "net_mean_pp": float(s["cell"]["net_mean_pp"]),
                "net_ci_low_pp": float(s["cell"]["net_ci_low_pp"]),
                "net_ci_high_pp": float(s["cell"]["net_ci_high_pp"]),
                "loco_net_mean_pp_without": s["loco"]["net_mean_pp_without"],
                "loco_net_ci_low_pp_without": s["loco"]["net_ci_low_pp_without"],
                "largest_entity": s["loco"]["largest_entity"],
                "entity_share": s["loco"]["entity_share"],
                "top3_share_of_abs_pnl": s["top3_loo"]["top3_share_of_abs_pnl"],
                "p_two_sided": float(s["cell"]["p_two_sided"]),
                "sig_bonferroni": bool(s["cell"]["sig_bonferroni"]),
                "sig_fdr": bool(s["cell"]["sig_fdr"]),
            }
            for s in survivors
        ],
    }
    with open(OUT_DIR / "05-summary.json", "w") as f:
        json.dump(summary, f, indent=2, default=str)
    print(f"\n[done] wrote {OUT_DIR / '05-summary.json'}", flush=True)


if __name__ == "__main__":
    main()
