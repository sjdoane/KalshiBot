"""V5-A1: enumerate v1's post-denylist trading universe.

Inputs:
  - data/live_trades/state.json (currently-resting + filled + closed orders)
  - data/v3/probe_inventory_all_markets.parquet (broader v3 inventory)
  - data/v4/v1_universe_series_table.parquet (V4-A reference table)
  - src/kalshi_bot/strategy/market_scanner.py DEFAULT_SERIES_DENYLIST

Outputs:
  - data/v5/v1_post_denylist_universe.parquet (per-series weights, with
    denylisted rows flagged).
  - data/v5/v1_post_denylist_universe_summary.json (top-line counts).

The "weight" of a series = how many v1 live attempted orders it has.
We also carry v3 inventory counts so we can sense the broader universe.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from kalshi_bot.strategy.market_scanner import (
    DEFAULT_SERIES_DENYLIST,
    extract_series_prefix,
)

ROOT = Path(__file__).resolve().parents[2]
LIVE_STATE = ROOT / "data" / "live_trades" / "state.json"
V4_TABLE = ROOT / "data" / "v4" / "v1_universe_series_table.parquet"
V3_INVENTORY = ROOT / "data" / "v3" / "probe_inventory_all_markets.parquet"

OUT_DIR = ROOT / "data" / "v5"
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_PARQUET = OUT_DIR / "v1_post_denylist_universe.parquet"
OUT_SUMMARY = OUT_DIR / "v1_post_denylist_universe_summary.json"


def load_live_orders() -> list[dict]:
    """Return one dict per v1 live order across intents/resting/filled/closed."""
    sj = json.loads(LIVE_STATE.read_text(encoding="utf-8"))
    rows: list[dict] = []
    for bucket in ("intents", "resting", "filled", "closed"):
        for _id, order in sj.get(bucket, {}).items():
            ticker = order.get("ticker", "")
            rows.append({
                "bucket": bucket,
                "ticker": ticker,
                "series_prefix": extract_series_prefix(ticker),
            })
    return rows


def main() -> None:
    live = load_live_orders()
    live_df = pd.DataFrame(live)
    # Per-series live counts
    series_live = (
        live_df.groupby("series_prefix")
        .agg(
            v1_live_all_orders=("bucket", "size"),
            v1_live_acked_orders=(
                "bucket",
                lambda s: int(((s == "resting") | (s == "filled") | (s == "closed")).sum()),
            ),
        )
        .reset_index()
    )

    # v3 inventory. NOTE: v3 stored series_ticker as the per-team form
    # (e.g. 'KXNFLWINS-NE'). For coverage purposes the canonical series-
    # prefix is the bare ticker prefix (first dash-segment), which is
    # also what the v1 scanner denylist matches against.
    inv = pd.read_parquet(V3_INVENTORY)
    inv["series_prefix"] = inv["ticker"].apply(lambda t: extract_series_prefix(t))

    # The v3 inventory already has the strict v1-eligible flag in
    # `eligible_narrow` (v1's actual [0.70, 0.95] band) and the looser
    # `eligible_wide`. Use eligible_narrow for the binding count; report
    # eligible_wide alongside as a sensitivity check.
    eligible_narrow = inv.get("eligible_narrow", pd.Series(False, index=inv.index))
    eligible_wide = inv.get("eligible_wide", pd.Series(False, index=inv.index))
    inv_summary = (
        inv.assign(_narrow=eligible_narrow, _wide=eligible_wide)
        .groupby("series_prefix")
        .agg(
            v3_inventory_all=("ticker", "size"),
            v3_inventory_eligible=("_narrow", "sum"),
            v3_inventory_eligible_wide=("_wide", "sum"),
        )
        .reset_index()
    )
    inv_summary["v3_inventory_eligible"] = inv_summary["v3_inventory_eligible"].astype(int)
    inv_summary["v3_inventory_eligible_wide"] = (
        inv_summary["v3_inventory_eligible_wide"].astype(int)
    )

    merged = series_live.merge(inv_summary, on="series_prefix", how="outer").fillna(0)
    for col in (
        "v1_live_all_orders",
        "v1_live_acked_orders",
        "v3_inventory_all",
        "v3_inventory_eligible",
        "v3_inventory_eligible_wide",
    ):
        merged[col] = merged[col].astype(int)

    merged["denylisted"] = merged["series_prefix"].isin(DEFAULT_SERIES_DENYLIST)
    merged = merged.sort_values(
        by=["v1_live_all_orders", "v3_inventory_eligible"], ascending=False
    ).reset_index(drop=True)

    # Pull league from V4-A reference where available
    try:
        v4 = pd.read_parquet(V4_TABLE)[["series_prefix", "league"]]
        merged = merged.merge(v4, on="series_prefix", how="left")
    except Exception:
        merged["league"] = ""
    merged["league"] = merged["league"].fillna("")

    merged.to_parquet(OUT_PARQUET, index=False)

    # Summary
    post = merged[~merged["denylisted"]]
    denylisted_universe = merged[merged["denylisted"]]
    summary = {
        "total_series_prefixes_all": int(len(merged)),
        "denylisted_series": sorted(DEFAULT_SERIES_DENYLIST),
        "denylisted_inventory_eligible_total": int(
            denylisted_universe["v3_inventory_eligible"].sum()
        ),
        "denylisted_live_orders_total": int(
            denylisted_universe["v1_live_all_orders"].sum()
        ),
        "post_denylist_series_count": int(len(post)),
        "post_denylist_live_orders_total": int(post["v1_live_all_orders"].sum()),
        "post_denylist_live_acked_total": int(post["v1_live_acked_orders"].sum()),
        "post_denylist_inventory_eligible_total": int(
            post["v3_inventory_eligible"].sum()
        ),
        "top_15_post_denylist_by_live": post.head(15)[
            [
                "series_prefix",
                "league",
                "v1_live_all_orders",
                "v1_live_acked_orders",
                "v3_inventory_eligible",
            ]
        ].to_dict(orient="records"),
    }
    OUT_SUMMARY.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print("post-denylist universe written to:")
    print(" ", OUT_PARQUET)
    print(" ", OUT_SUMMARY)
    print()
    print("summary:")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
