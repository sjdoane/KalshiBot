"""One-shot: backfill each v1 LiveOrder's fee_cost_usd from Kalshi's ACTUAL
/portfolio/fills fee_cost, then recompute realized P&L for settled (closed)
orders and reset realized_pnl_total_usd. Corrects the old modeled maker fee,
which over-deducted ~3-4x (verified 2026-06-13: the model charged ~2c/contract
round-trip where Kalshi charges ~0.4-0.7c). After this, the Discord settlement
notifications (per-bet realized AND the running total, which recomputes from
closed orders via realized_summary_since) show correct P&L, and any currently
OPEN positions settle with the correct fee.

RUN WITH THE BOT STOPPED (it rewrites state.json each loop). Dry-run by default;
--i-mean-it writes. Refuses if bot.lock is present unless --force.

NOTE: the rolling-30 kill window (kill_state.json recent_pnl_per_contract) is
SEPARATE and not touched here; it self-corrects as new correctly-fee'd fills
settle (and the floor was recalibrated 2026-06-13).

PowerShell (project root):
  PYTHONPATH=src .venv-kronos/Scripts/python.exe -m scripts.backfill_v1_fees
  PYTHONPATH=src .venv-kronos/Scripts/python.exe -m scripts.backfill_v1_fees --i-mean-it
"""

from __future__ import annotations

import argparse
import collections
import time
from pathlib import Path

from kalshi_bot.config import load_settings
from kalshi_bot.data.kalshi_client import KalshiClient
from kalshi_bot.strategy.live_order_manager import LiveOrderManager

BASE = Path("C:/Users/SamJD/OneDrive/Desktop/AI Projects/Project Kalshi")
STATE = BASE / "data" / "live_trades" / "state.json"
LOCK = BASE / "data" / "live_trades" / "bot.lock"
LOOKBACK_DAYS = 90


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--i-mean-it", action="store_true")
    ap.add_argument("--force", action="store_true",
                    help="run even if bot.lock is present (NOT recommended)")
    args = ap.parse_args()

    if LOCK.exists() and not args.force:
        print(f"REFUSING: {LOCK} present (bot may be running, which races on "
              f"state.json). Stop the bot first, or pass --force.")
        return 2

    s = load_settings()
    min_ts = int(time.time()) - LOOKBACK_DAYS * 86400
    with KalshiClient(s) as c:
        fills = list(c.paginate(
            "/portfolio/fills", item_key="fills", limit=200,
            min_ts=min_ts, max_pages=50,
        ))
        fee_by_order: dict[str, float] = collections.defaultdict(float)
        for f in fills:
            oid = f.get("order_id")
            if not oid:
                continue
            try:
                fee_by_order[oid] += float(f.get("fee_cost") or 0.0)
            except (TypeError, ValueError):
                pass
        print(f"fetched {len(fills)} fills over {LOOKBACK_DAYS}d "
              f"covering {len(fee_by_order)} order_ids")

        mgr = LiveOrderManager(client=c, state_path=STATE)
        before_total = mgr.state.realized_pnl_total_usd

        # 1) Set fee_cost_usd from the actual fees on every order we can match.
        fee_updated = 0
        buckets = (mgr.state.filled, mgr.state.closed,
                   mgr.state.resting, mgr.state.intents)
        for bucket in buckets:
            for o in bucket.values():
                if o.order_id and o.order_id in fee_by_order:
                    new_fee = round(fee_by_order[o.order_id], 6)
                    if abs(new_fee - o.fee_cost_usd) > 1e-9:
                        o.fee_cost_usd = new_fee
                        fee_updated += 1

        # 2) Recompute realized P&L for every SETTLED closed order and re-sum
        #    the all-time accumulator from those records.
        new_total = 0.0
        recomputed = 0
        biggest = []  # (delta, ticker) for the largest corrections
        for o in mgr.state.closed.values():
            if o.realized_pnl_usd is None or o.resolution_outcome is None:
                continue  # cancelled / never settled: no P&L
            old = o.realized_pnl_usd
            o.realized_pnl_usd = mgr._compute_realized_pnl(o, o.resolution_outcome)
            new_total += o.realized_pnl_usd
            recomputed += 1
            biggest.append((o.realized_pnl_usd - old, o.ticker))

        print(f"\norders with fee_cost set from real fills: {fee_updated}")
        print(f"settled orders recomputed: {recomputed}")
        print(f"realized_pnl_total_usd: {before_total:+.4f} -> {new_total:+.4f} "
              f"(delta {new_total - before_total:+.4f})")
        biggest.sort(key=lambda t: -abs(t[0]))
        if biggest:
            print("\nlargest per-bet corrections (new minus old):")
            for delta, tk in biggest[:8]:
                print(f"  {delta:+.4f}  {tk}")

        if args.i_mean_it:
            mgr.state.realized_pnl_total_usd = new_total
            mgr._save()
            print("\nWROTE state.json (fee_cost_usd backfilled, realized P&L "
                  "recomputed, accumulator reset).")
        else:
            print("\n[DRY RUN] re-run with --i-mean-it to write.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
