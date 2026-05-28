"""V10-A round 15b: Live spread + depth probe across all candidate prefixes.

For each candidate prefix, finds the top N traded open markets (by volume),
pulls orderbook depth, and reports:

- Median spread in cents at the at-the-money strike
- Median orderbook depth on each side
- Whether a retail maker quote at midprice could realistically get
  ahead of the existing queue

The realistic edge per fill = (Becker historical maker edge) - (cost of
crossing spread for fill OR cost of waiting at back of queue).
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from live_universe_probe import get  # reuse auth + get

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "research" / "v10a" / "10-live-spread-probe.md"

CANDIDATES = [
    ("KXBTCD", "Bitcoin daily"),
    ("KXBTC", "Bitcoin range monthly/yearly"),
    ("KXETHD", "Ethereum daily"),
    ("KXATPMATCH", "ATP tennis matches"),
    ("KXWTAMATCH", "WTA tennis matches"),
    ("KXMLBGAME", "MLB games (currently in season)"),
    ("KXNBAGAME", "NBA games (playoffs)"),
    ("KXNHLGAME", "NHL games"),
    ("KXTSAW", "TSA passenger counts (Media)"),
    ("KXAPRPOTUS", "POTUS approval (Media)"),
    ("KXITFMATCH", "ITF men tennis"),
    ("KXITFWMATCH", "ITF women tennis"),
    ("KXHYPE15M", "Hype 15-min crypto (NEW post-Becker)"),
    ("KXBTC15M", "Bitcoin 15-min (NEW post-Becker)"),
]


def get_active_tickers(series: str, limit: int = 50) -> list[dict]:
    """Find currently-open markets with status active and order by close_time."""
    tickers = []
    cursor = None
    while True:
        params = {"status": "open", "series_ticker": series, "limit": 200}
        if cursor:
            params["cursor"] = cursor
        try:
            data = get("/markets", params=params)
        except Exception:
            break
        ms = data.get("markets", [])
        if not ms:
            break
        for m in ms:
            tickers.append(m)
        cursor = data.get("cursor")
        if not cursor or len(tickers) >= limit:
            break
    return tickers[:limit]


def parse_orderbook(ob: dict) -> dict:
    """Extract yes_bid, yes_ask, depths from orderbook response."""
    obfp = ob.get("orderbook_fp", {})
    yes_levels = obfp.get("yes_dollars", []) or []
    no_levels = obfp.get("no_dollars", []) or []
    # On Kalshi: the "yes" orderbook contains orders to BUY YES (resting bids on YES side)
    # and the "no" orderbook contains orders to BUY NO (resting bids on NO side).
    # yes_bid = max price in yes_dollars (highest bid on YES)
    # yes_ask = 1 - max price in no_dollars (lowest ask on YES = 100 - highest NO bid)
    yes_bid = 0.0
    yes_ask = 1.0
    yes_depth_at_bid = 0.0
    no_depth_at_bid = 0.0
    yes_depth_total = 0.0
    no_depth_total = 0.0
    if yes_levels:
        prices = [float(p) for p, _ in yes_levels]
        yes_bid = max(prices)
        for p, sz in yes_levels:
            yes_depth_total += float(sz)
            if float(p) == yes_bid:
                yes_depth_at_bid += float(sz)
    if no_levels:
        prices = [float(p) for p, _ in no_levels]
        no_bid = max(prices)
        yes_ask = 1.0 - no_bid
        for p, sz in no_levels:
            no_depth_total += float(sz)
            if float(p) == no_bid:
                no_depth_at_bid += float(sz)
    spread = yes_ask - yes_bid
    mid = (yes_bid + yes_ask) / 2.0 if yes_levels and no_levels else None
    return {
        "yes_bid": yes_bid,
        "yes_ask": yes_ask,
        "spread": spread,
        "mid": mid,
        "yes_depth_at_bid": yes_depth_at_bid,
        "no_depth_at_bid": no_depth_at_bid,
        "yes_depth_total": yes_depth_total,
        "no_depth_total": no_depth_total,
    }


def probe_series(series: str, description: str) -> dict:
    """Probe a series: get active tickers, sample 10 with depth, summarize."""
    tickers = get_active_tickers(series, limit=200)
    if not tickers:
        return {"series": series, "n_open": 0}
    # Filter to markets closing within next 30 days
    now = datetime.now(timezone.utc)
    candidates = []
    for t in tickers:
        ct = t.get("close_time")
        if not ct:
            continue
        try:
            dt = datetime.fromisoformat(ct.replace("Z", "+00:00"))
        except Exception:
            continue
        days = (dt - now).total_seconds() / 86400.0
        if days < 0 or days > 60:
            continue
        candidates.append({"ticker": t["ticker"], "close_time": ct, "days_to_close": days})

    if not candidates:
        return {"series": series, "n_open": len(tickers), "n_in_window": 0}

    # Sample 15 candidates (random or sorted by days_to_close ascending - more active)
    candidates.sort(key=lambda x: x["days_to_close"])
    sample = candidates[:15]
    spreads = []
    bids = []
    asks = []
    mids = []
    depths = []
    for c in sample:
        try:
            ob = get(f'/markets/{c["ticker"]}/orderbook')
            parsed = parse_orderbook(ob)
            if parsed["mid"] is None:
                continue
            spreads.append(parsed["spread"])
            bids.append(parsed["yes_bid"])
            asks.append(parsed["yes_ask"])
            mids.append(parsed["mid"])
            depths.append(parsed["yes_depth_at_bid"] + parsed["no_depth_at_bid"])
        except Exception:
            continue
        time.sleep(0.05)  # rate-limit politeness

    if not spreads:
        return {"series": series, "n_open": len(tickers), "n_in_window": len(candidates),
                "n_sampled": 0, "n_with_book": 0, "description": description}

    return {
        "series": series,
        "description": description,
        "n_open": len(tickers),
        "n_in_window": len(candidates),
        "n_sampled": len(sample),
        "n_with_book": len(spreads),
        "median_spread_cents": sorted(spreads)[len(spreads) // 2] * 100,
        "min_spread_cents": min(spreads) * 100,
        "max_spread_cents": max(spreads) * 100,
        "median_mid": sorted(mids)[len(mids) // 2],
        "median_depth_at_top_levels": sorted(depths)[len(depths) // 2],
        "fraction_in_band_0_3_to_0_7": sum(1 for m in mids if 0.30 <= m <= 0.70) / len(mids),
    }


def main() -> None:
    print(f"Live spread + depth probe @ {datetime.now(timezone.utc).isoformat()}")
    print("=" * 130)
    print(f"{'series':18} {'open':>5} {'wnd':>5} {'samp':>5} {'wBk':>5} {'spread_c':>10} {'mid':>6} {'inBand':>7} {'depth':>10}  description")
    print("-" * 140)
    results = []
    for series, desc in CANDIDATES:
        r = probe_series(series, desc)
        results.append(r)
        if r.get("n_with_book", 0) == 0:
            print(f"{series:18} {r.get('n_open', 0):>5} {r.get('n_in_window', 0):>5} {r.get('n_sampled', 0):>5}    0   {'-':>10} {'-':>6} {'-':>7} {'-':>10}  {desc}")
        else:
            print(
                f"{series:18} {r['n_open']:>5} {r['n_in_window']:>5} {r['n_sampled']:>5} {r['n_with_book']:>5} "
                f"{r['median_spread_cents']:>10.1f} {r['median_mid']:>6.3f} "
                f"{r['fraction_in_band_0_3_to_0_7']*100:>7.0f}% {r['median_depth_at_top_levels']:>10.0f}  {desc}"
            )

    with open(OUT, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nSaved to {OUT}")

    print("\nQuick interpretation:")
    print(" - spread_c = median spread in cents (1c is tight = MMs already there)")
    print(" - mid = median yes mid price")
    print(" - inBand = % of sampled markets with mid in [0.30, 0.70] (our maker band)")
    print(" - depth = median total contracts at the top bid level on both sides")
    print(" - For a retail maker to capture edge: spread >= 3c AND inBand > 50% AND realistic chance to get to top of queue")


if __name__ == "__main__":
    main()
