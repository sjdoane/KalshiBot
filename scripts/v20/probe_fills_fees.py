"""READ-ONLY: dump recent Kalshi /portfolio/fills with their ACTUAL fee field
so we can compare the real maker fee Kalshi charges per series against the bot's
model (metrics.kalshi_maker_fee_per_contract, applied 2x in
LiveOrderManager._compute_realized_pnl). GET only; safe alongside the live bot.

Goal: confirm the 2026 live maker-fee schedule for v1's series (KXATPMATCH,
KXWTAMATCH, KXMLBGAME, KXNFLGAME, KXNCAAFGAME) so realized-P&L / Discord
notifications can be corrected at the source.

Run: PYTHONPATH=src .venv-kronos/Scripts/python.exe -m scripts.v20.probe_fills_fees
"""

from __future__ import annotations

import collections
import json
import time

from kalshi_bot.config import load_settings
from kalshi_bot.data.kalshi_client import KalshiClient

LOOKBACK_DAYS = 10


def _series(ticker: str) -> str:
    return ticker.split("-", 1)[0] if ticker else "?"


def main() -> None:
    s = load_settings()
    min_ts = int(time.time()) - LOOKBACK_DAYS * 86400
    with KalshiClient(s) as c:
        fills = list(c.paginate(
            "/portfolio/fills", item_key="fills", limit=200,
            min_ts=min_ts, max_pages=20,
        ))
    print(f"=== fetched {len(fills)} fills over last {LOOKBACK_DAYS}d ===")
    if not fills:
        return

    # Discover the real field names (esp. the fee field) on the first fill.
    print("\n=== raw keys on first fill ===")
    print(sorted(fills[0].keys()))
    print("\n=== first fill raw JSON ===")
    print(json.dumps(fills[0], indent=2, default=str))

    # Detect any fee-like field present.
    fee_keys = sorted({k for f in fills for k in f.keys() if "fee" in k.lower()})
    print(f"\n=== fee-like fields present across fills: {fee_keys} ===")

    # Aggregate by series: count, summed contracts, summed actual fee (cents),
    # and what the BOT MODEL would charge (2x maker fee per contract).
    from kalshi_bot.analysis.metrics import kalshi_maker_fee_per_contract

    agg = collections.defaultdict(lambda: {"fills": 0, "contracts": 0,
                                           "real_fee_c": 0.0, "model_fee_c": 0.0})
    for f in fills:
        series = _series(f.get("ticker", ""))
        cnt_raw = f.get("count_fp", f.get("count"))
        try:
            cnt = int(round(float(cnt_raw))) if cnt_raw is not None else 0
        except (TypeError, ValueError):
            cnt = 0
        # actual fee: try common field names; Kalshi reports cents (int).
        real_fee = None
        for k in ("fee_cost", "fee", "fees", "maker_fee", "taker_fee"):
            if f.get(k) is not None:
                try:
                    real_fee = float(f[k])
                except (TypeError, ValueError):
                    real_fee = None
                if real_fee is not None:
                    break
        # price for the model
        px_raw = f.get("yes_price_dollars")
        try:
            px = float(px_raw) if px_raw is not None else (float(f.get("yes_price", 0)) / 100.0)
        except (TypeError, ValueError):
            px = 0.0
        model_fee_per = 2.0 * kalshi_maker_fee_per_contract(px) * 100.0  # cents
        a = agg[series]
        a["fills"] += 1
        a["contracts"] += cnt
        if real_fee is not None:
            a["real_fee_c"] += real_fee
        a["model_fee_c"] += model_fee_per * cnt

    print("\n=== per-series: ACTUAL fee vs BOT MODEL (cents) ===")
    print(f"{'series':16} {'fills':>5} {'contracts':>9} {'real_fee_c':>11} {'model_fee_c':>12}")
    for series in sorted(agg):
        a = agg[series]
        print(f"{series:16} {a['fills']:>5} {a['contracts']:>9} "
              f"{a['real_fee_c']:>11.2f} {a['model_fee_c']:>12.2f}")


if __name__ == "__main__":
    main()
