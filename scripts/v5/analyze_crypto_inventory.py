"""Analyze the crypto inventory probe results.

Produces a per-series breakdown showing settlement-cadence buckets,
v1-eligibility, yes-rate distribution, and concentration metrics for
the V5-C1 deliverable.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA = REPO_ROOT / "data" / "v5"


def cadence_bucket(median_hours: float | None) -> str:
    if median_hours is None or pd.isna(median_hours):
        return "unknown"
    if median_hours < 1:
        return "sub_hour"
    if median_hours < 6:
        return "hourly"
    if median_hours < 30:
        return "daily"
    if median_hours < 180:
        return "weekly"
    if median_hours < 800:
        return "monthly"
    if median_hours < 3500:
        return "quarterly"
    return "long_horizon"


def main() -> int:
    summary = pd.read_parquet(DATA / "crypto_inventory_summary.parquet")
    markets = pd.read_parquet(DATA / "crypto_inventory.parquet")
    print("Loaded summary:", summary.shape, flush=True)
    print("Loaded markets:", markets.shape, flush=True)

    # Filter to series with at least 1 market
    hit = summary[summary["n_total"] > 0].copy()
    print(f"\nSeries with data: {len(hit)}", flush=True)
    hit["cadence"] = hit["median_lifetime_hours"].apply(cadence_bucket)

    # Top 30 by n_total
    print("\nTop 30 series by total markets:", flush=True)
    top = hit.nlargest(30, "n_total")[[
        "series_ticker", "n_total", "n_finalized", "n_v1_eligible_band",
        "median_lifetime_hours", "mean_last_price", "yes_rate",
        "v1_eligible_yes_rate", "cadence",
    ]]
    print(top.to_string(index=False), flush=True)

    # Cadence aggregation
    print("\nCadence buckets (across series):", flush=True)
    cad = hit.groupby("cadence").agg(
        n_series=("series_ticker", "count"),
        n_markets_total=("n_total", "sum"),
        n_v1_eligible=("n_v1_eligible_band", "sum"),
        mean_yes_rate=("yes_rate", "mean"),
        mean_v1_yes_rate=("v1_eligible_yes_rate", "mean"),
    ).reset_index().sort_values("n_markets_total", ascending=False)
    print(cad.to_string(index=False), flush=True)

    # Within the markets table: BTC/ETH/SOL splits
    print("\nMarkets by asset prefix (substring match):", flush=True)
    for prefix, label in [
        ("KXBTC", "BTC"),
        ("KXETH", "ETH"),
        ("KXSOL", "SOL"),
        ("KXDOGE", "DOGE"),
        ("KXXRP", "XRP"),
        ("KXHYPE", "HYPE"),
        ("KXBNB", "BNB"),
        ("KXAVAX", "AVAX"),
        ("KXADA", "ADA"),
        ("KXLINK", "LINK"),
        ("KXLTC", "LTC"),
        ("KXFDV", "FDV"),
    ]:
        sub = markets[markets["series_ticker"].str.startswith(prefix)]
        if sub.empty:
            continue
        n_total = len(sub)
        v1_mask = (
            sub["last_price"].between(0.70, 0.95, inclusive="both")
            & sub["status"].isin(["finalized", "settled"])
            & sub["result"].isin(["yes", "no"])
        )
        n_v1 = int(v1_mask.sum())
        if n_v1 > 0:
            v1_yes_rate = float((sub.loc[v1_mask, "result"] == "yes").mean())
        else:
            v1_yes_rate = None
        print(
            f"  {label:6s} prefix={prefix:8s} n={n_total:7d} "
            f"v1_band={n_v1:5d} v1_yes_rate={v1_yes_rate}",
            flush=True,
        )

    # Settlement-frequency analysis: largest series + lifetime breakdown
    print("\nDetailed look at largest single-series:", flush=True)
    for s in hit.nlargest(15, "n_total")["series_ticker"]:
        sub = markets[markets["series_ticker"] == s]
        n = len(sub)
        if n == 0:
            continue
        lifetime = (
            (pd.to_datetime(sub["close_time"], utc=True)
             - pd.to_datetime(sub["open_time"], utc=True))
            .dt.total_seconds() / 3600
        )
        print(
            f"  {s:24s} n={n:6d} life_h: mean={lifetime.mean():.2f} "
            f"med={lifetime.median():.2f} p10={lifetime.quantile(0.1):.2f} "
            f"p90={lifetime.quantile(0.9):.2f}",
            flush=True,
        )

    # v1-eligible band per series (only those with >=5)
    print("\nSeries with n_v1_eligible_band >= 5:", flush=True)
    v1 = hit[hit["n_v1_eligible_band"] >= 5].sort_values(
        "n_v1_eligible_band", ascending=False
    )
    print(
        v1[[
            "series_ticker", "n_total", "n_v1_eligible_band",
            "v1_eligible_yes_rate", "median_lifetime_hours",
            "mean_last_price", "cadence",
        ]].to_string(index=False),
        flush=True,
    )

    # Close-time distribution (yearly) and settlement-frequency note
    print("\nTotal market closes per year:", flush=True)
    if "close_time" in markets.columns:
        years = pd.to_datetime(markets["close_time"], utc=True).dt.year
        for y, c in years.value_counts().sort_index().items():
            print(f"  {y}: {c}", flush=True)

    # Achievable n at different filters
    print("\n=== Achievable n at different cuts ===", flush=True)
    finalized = markets[markets["status"].isin(["finalized", "settled"])]
    print(f"Finalized total: {len(finalized)}", flush=True)
    fmtd = finalized[finalized["result"].isin(["yes", "no"])]
    print(f"With binary result: {len(fmtd)}", flush=True)
    # BTC daily only
    btc_d = fmtd[fmtd["series_ticker"].isin(["KXBTCD", "KXBTC"])]
    print(f"KXBTCD + KXBTC: {len(btc_d)}", flush=True)
    # ETH daily/hourly
    eth_dh = fmtd[fmtd["series_ticker"].isin(["KXETHD", "KXETHH"])]
    print(f"KXETHD + KXETHH: {len(eth_dh)}", flush=True)
    # v1-eligible price band
    v1_band = fmtd[fmtd["last_price"].between(0.70, 0.95, inclusive="both")]
    print(f"v1-band (0.70-0.95): {len(v1_band)}", flush=True)
    # v1-eligible band, daily cadence only
    closes = pd.to_datetime(v1_band["close_time"], utc=True)
    opens = pd.to_datetime(v1_band["open_time"], utc=True)
    lifetimes = (closes - opens).dt.total_seconds() / 3600
    daily_band = v1_band[(lifetimes >= 6) & (lifetimes < 30)]
    print(f"v1-band + daily cadence: {len(daily_band)}", flush=True)
    weekly_band = v1_band[(lifetimes >= 30) & (lifetimes < 180)]
    print(f"v1-band + weekly cadence: {len(weekly_band)}", flush=True)
    monthly_band = v1_band[(lifetimes >= 180) & (lifetimes < 800)]
    print(f"v1-band + monthly cadence: {len(monthly_band)}", flush=True)

    # Single-year achievable
    closes_2025 = closes[closes.dt.year == 2025]
    closes_2026 = closes[closes.dt.year == 2026]
    print(f"v1-band 2025 closes: {len(closes_2025)}", flush=True)
    print(f"v1-band 2026 closes: {len(closes_2026)}", flush=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
