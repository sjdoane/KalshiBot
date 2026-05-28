"""V10-A round 15b: Distribution of live spreads per series.

For each candidate series, samples up to 50 currently-open markets and
reports the distribution of spreads. The goal: find spread regimes where
a retail maker quote could realistically be inside or at the inside.

For our purposes:
- 1c spread = MM saturated, retail can't compete
- 2 to 3c spread = MM thin, retail could be at the inside
- 4c+ spread = MM absent, retail has wide latitude
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from live_universe_probe import get
from live_spread_probe import parse_orderbook  # type: ignore

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "research" / "v10a" / "11-spread-distribution.json"

SERIES = [
    "KXBTCD",
    "KXBTC",
    "KXETHD",
    "KXATPMATCH",
    "KXWTAMATCH",
    "KXMLBGAME",
    "KXNBAGAME",
    "KXMLBTOTAL",
    "KXMLBSPREAD",
    "KXNBATOTAL",
    "KXNBASPREAD",
    "KXTSAW",
    "KXAPRPOTUS",
    "KX538APPROVE",
    "KXFEDDECISION",
    "KXITFMATCH",
    "KXITFWMATCH",
]


def get_all_open_with_volume(series: str, max_pages: int = 5) -> list[dict]:
    """Pull up to max_pages * 200 markets and filter to those with non-zero volume_24h."""
    tickers = []
    cursor = None
    for _ in range(max_pages):
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
        tickers.extend(ms)
        cursor = data.get("cursor")
        if not cursor:
            break
    return tickers


def main() -> None:
    print(f"Spread distribution probe @ {datetime.now(timezone.utc).isoformat()}")
    print("=" * 130)
    print(f"{'series':18} {'open':>5} {'wOB':>5} {'mid_0.3-0.7':>12}  {'spread distribution (cents)':40}")
    print("-" * 130)

    all_results = {}
    for series in SERIES:
        markets = get_all_open_with_volume(series, max_pages=3)
        n_open = len(markets)
        if not markets:
            print(f"{series:18} {0:>5}")
            continue

        # Sort by volume desc to focus on active markets
        markets.sort(key=lambda m: m.get("volume", 0), reverse=True)

        # Sample top 30 by volume
        sample = markets[:30]
        spreads = []
        mids = []
        in_band = 0
        for m in sample:
            try:
                ob = get(f'/markets/{m["ticker"]}/orderbook')
                parsed = parse_orderbook(ob)
                if parsed["mid"] is None:
                    continue
                spreads.append(parsed["spread"])
                mids.append(parsed["mid"])
                if 0.30 <= parsed["mid"] <= 0.70:
                    in_band += 1
            except Exception:
                continue
            time.sleep(0.05)

        if not spreads:
            print(f"{series:18} {n_open:>5}     0")
            continue

        # Distribution buckets (in cents)
        buckets = {"1c": 0, "2c": 0, "3c": 0, "4-6c": 0, "7-10c": 0, ">10c": 0}
        for s in spreads:
            sc = round(s * 100)
            if sc <= 1:
                buckets["1c"] += 1
            elif sc == 2:
                buckets["2c"] += 1
            elif sc == 3:
                buckets["3c"] += 1
            elif sc <= 6:
                buckets["4-6c"] += 1
            elif sc <= 10:
                buckets["7-10c"] += 1
            else:
                buckets[">10c"] += 1
        dist = ", ".join(f"{k}:{v}" for k, v in buckets.items() if v > 0)
        print(f"{series:18} {n_open:>5} {len(spreads):>5}  {in_band}/{len(mids)}({in_band/len(mids)*100:.0f}%)  {dist}")
        all_results[series] = {
            "n_open": n_open,
            "n_with_book": len(spreads),
            "n_in_band": in_band,
            "spread_buckets": buckets,
            "median_spread_cents": sorted(spreads)[len(spreads) // 2] * 100,
            "spreads_sample": [round(s*100, 1) for s in spreads[:20]],
        }

    with open(OUT, "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"\nResults saved to {OUT}")

    # Summary
    print("\n## Series with materially viable retail-maker spreads (any market >=3c spread):")
    for series, d in all_results.items():
        b = d.get("spread_buckets", {})
        n_3plus = b.get("3c", 0) + b.get("4-6c", 0) + b.get("7-10c", 0) + b.get(">10c", 0)
        pct_3plus = n_3plus / d["n_with_book"] * 100 if d["n_with_book"] > 0 else 0
        if n_3plus > 0:
            print(f"  {series:18}  3c+ spread in {n_3plus}/{d['n_with_book']} markets ({pct_3plus:.0f}%); "
                  f"n_open={d['n_open']}")


if __name__ == "__main__":
    main()
