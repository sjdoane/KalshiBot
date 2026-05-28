"""v6 Agent C: analyze the microstructure probe output.

Reads data/v6/kxbtcd_sample_trades.parquet and
data/v6/kxbtcd_live_orderbook_snapshot.parquet and prints tables for
the writeup.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]


def main() -> int:
    trades = pd.read_parquet(REPO / "data" / "v6" / "kxbtcd_sample_trades.parquet")
    trades["created_time"] = pd.to_datetime(trades["created_time"], utc=True)
    trades["_sample_close_time"] = pd.to_datetime(
        trades["_sample_close_time"], utc=True,
    )
    trades["yes_price"] = pd.to_numeric(trades["yes_price_dollars"], errors="coerce")
    trades["count"] = pd.to_numeric(trades["count_fp"], errors="coerce")
    trades["minutes_to_close"] = (
        (trades["_sample_close_time"] - trades["created_time"]).dt.total_seconds() / 60.0
    )

    print("=" * 78)
    print("Q1: TRADE-COUNT DISTRIBUTION PER CONTRACT BY WINDOW x BAND")
    print("=" * 78)
    print(f"Sample: {trades['_sample_ticker'].nunique()} contracts, "
          f"{len(trades)} trades total (T-60 to T+5 raw)")
    print(f"Post-flip range: "
          f"{trades['_sample_close_time'].min()} -> "
          f"{trades['_sample_close_time'].max()}")
    print()

    # Filter to trades AT or BEFORE close (drop post-close prints).
    pre = trades[trades["minutes_to_close"] >= 0].copy()
    print(f"Trades before close: {len(pre)} ({len(pre)/len(trades):.0%} of pull)")
    print()

    # Per-contract trade counts at multiple windows.
    contracts = pre.groupby(["_sample_ticker", "_sample_band"]).size().rename("n_60")
    contracts = contracts.reset_index()
    for w in [30, 15, 5]:
        sub = pre[pre["minutes_to_close"] <= w]
        cnt = sub.groupby("_sample_ticker").size().rename(f"n_{w}")
        contracts = contracts.merge(cnt, left_on="_sample_ticker", right_index=True, how="left")
    for col in ["n_30", "n_15", "n_5"]:
        contracts[col] = contracts[col].fillna(0).astype(int)

    bands_order = ["extreme-low", "low-mid", "midband", "narrow", "extreme-high"]

    def pct(s, q):
        return float(np.percentile(s, q)) if len(s) > 0 else float("nan")

    def fmt_row(name, n, s):
        if len(s) == 0:
            return f"  {name:<14} n_contracts={n:>3}  (no trades in window)"
        return (
            f"  {name:<14} n_contracts={n:>3}  "
            f"mean={s.mean():>6.1f}  median={pct(s,50):>5.1f}  "
            f"p25={pct(s,25):>5.1f}  p75={pct(s,75):>5.1f}  p90={pct(s,90):>6.1f}"
        )

    print("Trade counts per contract in last N minutes (incl. zero-trade contracts):")
    for w in [60, 30, 15, 5]:
        col = f"n_{w}" if w != 60 else "n_60"
        if col == "n_60":
            # construct from groupby; pre n_60 in contracts may differ if some
            # contracts had zero pre-close trades. Use contracts['n_60'].
            pass
        print(f"\n  Window: last {w} min")
        for band in bands_order:
            sub = contracts[contracts["_sample_band"] == band]
            print(fmt_row(band, len(sub), sub[col]))
        print(fmt_row("ALL", len(contracts), contracts[col]))

    print()
    print("=" * 78)
    print("Q5: COMPARISON TO V1 SPORTS (Le 2026 median 76 trades / market lifetime)")
    print("=" * 78)
    s_5 = contracts["n_5"]
    print(f"KXBTCD median trades in LAST 5 MIN ONLY = {s_5.median():.1f}")
    print(f"KXBTCD mean trades in last 5 min       = {s_5.mean():.1f}")
    s_30 = contracts["n_30"]
    print(f"KXBTCD median trades in last 30 min    = {s_30.median():.1f}")
    s_60 = contracts["n_60"]
    print(f"KXBTCD median trades in last 60 min    = {s_60.median():.1f}")
    print(f"v1 sports median per ENTIRE LIFETIME   = 76")
    print(f"==> Even in 5 min only, KXBTCD median trade count "
          f"{'EXCEEDS' if s_5.median() > 76 else 'is below'} sports lifetime median.")

    # ===== Q2: spread distribution from live snapshot =====
    print()
    print("=" * 78)
    print("Q2/Q3: SPREAD AND TOP-OF-BOOK DEPTH FROM LIVE SNAPSHOT")
    print("=" * 78)
    live_path = REPO / "data" / "v6" / "kxbtcd_live_orderbook_snapshot.parquet"
    live = pd.read_parquet(live_path)
    for col in ["yes_bid_dollars", "yes_ask_dollars", "no_bid_dollars",
                "no_ask_dollars", "last_price_dollars",
                "yes_bid_size_fp", "yes_ask_size_fp",
                "volume_fp", "volume_24h_fp", "open_interest_fp"]:
        live[col] = pd.to_numeric(live[col], errors="coerce")
    live["spread"] = live["yes_ask_dollars"] - live["yes_bid_dollars"]
    # Mid (use yes side; mid undefined if no quote on a side)
    live["mid"] = (live["yes_bid_dollars"] + live["yes_ask_dollars"]) / 2.0
    # If only no side quoted, fall back to 1 - no_mid
    no_mid_fallback = 1.0 - (live["no_bid_dollars"] + live["no_ask_dollars"]) / 2.0
    live["mid"] = live["mid"].where(live["yes_bid_dollars"] > 0, no_mid_fallback)

    print(f"Snapshot: n={len(live)} live KXBTCD markets, "
          f"event_tickers={live['event_ticker'].nunique()}")
    print(f"Snapshot time approx: NOW (probe ran 2026-05-25)")
    print()

    # Quoted both sides?
    quoted = live[(live["yes_bid_dollars"] > 0) | (live["no_bid_dollars"] > 0)].copy()
    fully_quoted = live[
        (live["yes_bid_dollars"] > 0) & (live["yes_ask_dollars"] < 1.0)
    ].copy()
    print(f"  markets with at least one quote: {len(quoted)}/{len(live)}")
    print(f"  markets with both yes bid AND ask < $1: {len(fully_quoted)}/{len(live)}")
    print()

    # Spread distribution across all live markets that have a meaningful mid
    bands = {
        "extreme-low": (0.05, 0.20),
        "low-mid": (0.20, 0.55),
        "midband": (0.55, 0.80),
        "narrow": (0.70, 0.95),
        "extreme-high": (0.80, 0.95),
    }
    print("Spread (yes_ask - yes_bid) distribution by mid-price band, live snapshot:")
    print(f"  {'band':<14} n  mean   median  p25   p75   p90")
    for name, (lo, hi) in bands.items():
        sub = fully_quoted[(fully_quoted["mid"] >= lo) & (fully_quoted["mid"] <= hi)]
        if len(sub) == 0:
            print(f"  {name:<14} n=0")
            continue
        s = sub["spread"]
        print(
            f"  {name:<14} n={len(sub):>2}  "
            f"mean={s.mean():.3f}  median={s.median():.3f}  "
            f"p25={s.quantile(0.25):.3f}  p75={s.quantile(0.75):.3f}  "
            f"p90={s.quantile(0.90):.3f}"
        )
    print()

    # Depth
    print("Top-of-book size (yes_bid_size_fp + yes_ask_size_fp), live snapshot:")
    print(f"  {'band':<14} n  median_bid_sz  median_ask_sz")
    for name, (lo, hi) in bands.items():
        sub = fully_quoted[(fully_quoted["mid"] >= lo) & (fully_quoted["mid"] <= hi)]
        if len(sub) == 0:
            continue
        print(
            f"  {name:<14} n={len(sub):>2}  "
            f"median_bid={sub['yes_bid_size_fp'].median():.0f}  "
            f"median_ask={sub['yes_ask_size_fp'].median():.0f}"
        )
    print()
    # Print live snapshot for completeness
    print("Snapshot rows with both-sided quotes (head 20):")
    print(fully_quoted[[
        "ticker", "yes_bid_dollars", "yes_ask_dollars", "spread",
        "yes_bid_size_fp", "yes_ask_size_fp", "volume_fp", "volume_24h_fp",
    ]].head(20).to_string())

    # ===== Q4: maker fill simulation =====
    print()
    print("=" * 78)
    print("Q4: MAKER FILL RATE ESTIMATE (place bid at mid - 2c at T-5min, "
          "fill if any subsequent trade prints <= bid)")
    print("=" * 78)
    print()
    print("Approximation: we proxy 'mid at T-5min' with the VWAP of trades")
    print("printing in the [T-6, T-5] window (1 min before our hypothetical")
    print("entry). If no trade in that window, drop the contract (no signal).")
    print("Then count it as a FILL if any trade in T-5 to T-0 prints at")
    print("yes_price <= proxy_mid - 0.02. This OVERESTIMATES fill rate")
    print("because real maker would need to be at the BEST bid, not anywhere")
    print("below it, but it's a useful upper bound.")
    print()
    pre = trades[trades["minutes_to_close"] >= 0].copy()

    rows: list[dict] = []
    for ticker, g in pre.groupby("_sample_ticker"):
        band = g["_sample_band"].iloc[0]
        ref = g[(g["minutes_to_close"] >= 5) & (g["minutes_to_close"] <= 6)]
        if len(ref) == 0:
            continue
        vwap = (ref["yes_price"] * ref["count"]).sum() / ref["count"].sum()
        target_bid = round(vwap - 0.02, 2)
        if target_bid < 0.01:
            continue
        post = g[g["minutes_to_close"] < 5]
        if len(post) == 0:
            rows.append({"ticker": ticker, "band": band, "ref_mid": vwap,
                         "target_bid": target_bid, "n_post": 0, "filled": False})
            continue
        filled = (post["yes_price"] <= target_bid).any()
        rows.append({
            "ticker": ticker, "band": band, "ref_mid": vwap,
            "target_bid": target_bid, "n_post": len(post), "filled": bool(filled),
        })

    sim = pd.DataFrame(rows)
    if len(sim) == 0:
        print("  no contracts had a T-6..T-5 reference print; cannot simulate")
    else:
        print(f"  Eligible contracts (had ref print): {len(sim)}")
        overall = sim["filled"].mean()
        print(f"  Overall fill rate at mid-2c: {overall:.0%}")
        print()
        print(f"  Fill rate by band:")
        for band in bands_order:
            sub = sim[sim["band"] == band]
            if len(sub) == 0:
                print(f"    {band:<14} n=0")
                continue
            fr = sub["filled"].mean()
            print(f"    {band:<14} n={len(sub):>3}  fill_rate={fr:.0%}")
        print()
        print("  Ref-mid distribution:")
        for band in bands_order:
            sub = sim[sim["band"] == band]
            if len(sub) == 0:
                continue
            print(f"    {band:<14} ref_mid median={sub['ref_mid'].median():.2f} "
                  f"target_bid median={sub['target_bid'].median():.2f}")

    # ===== Q6: post-flip check =====
    print()
    print("=" * 78)
    print("Q6: POST-FLIP DATA CHECK")
    print("=" * 78)
    full = pd.read_parquet(REPO / "data" / "v5" / "crypto_full_KXBTCD.parquet")
    flip = pd.Timestamp("2024-10-01", tz="UTC")
    n_pre = (full["close_time"] < flip).sum()
    n_post = (full["close_time"] >= flip).sum()
    print(f"  Pre-Oct-2024 KXBTCD contracts:  {n_pre:,}")
    print(f"  Post-Oct-2024 KXBTCD contracts: {n_post:,}")
    print(f"  Earliest contract: {full['close_time'].min()}")
    print(f"  Latest contract:   {full['close_time'].max()}")
    print()
    print(f"  Trade probe sample close_time range: "
          f"{trades['_sample_close_time'].min()} -> "
          f"{trades['_sample_close_time'].max()}")
    print(f"  Pct of probe trades post-flip: "
          f"{((trades['_sample_close_time']>=flip).sum() / len(trades)):.0%}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
