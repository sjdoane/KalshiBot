"""Free up Kalshi cash from v1 to make room for v14.

Cancels v1's lowest-edge resting orders until the projected freed cash
reaches the requested target. Default target = $13 (the v14 capital cap
plus a small buffer).

Usage:
    PYTHONPATH=src .venv-kronos/Scripts/python.exe scripts/v14/free_v1_cash.py [target_usd]

Run manually ONCE before launching the v14 daemon for the first time.
The script:
1. Reads v1 state.json (data/live_trades/state.json) and lists resting orders
2. Sorts by `expected_net_edge` ascending (cancel the WORST trades first)
3. For each, calls Kalshi DELETE /portfolio/events/orders/{order_id} (V2)
4. Stops when cumulative freed cash >= target
5. Updates v1 state.json to mark the cancelled orders

Operator safety:
- Prints a dry-run summary first; requires confirmation to proceed
- Never cancels MORE than the target; can stop early
- Uses the existing KalshiClient and v1 LiveOrderManager
"""

from __future__ import annotations

import sys
from pathlib import Path

BASE = Path("C:/Users/SamJD/OneDrive/Desktop/AI Projects/Project Kalshi")
sys.path.insert(0, str(BASE / "src"))

from kalshi_bot.config import Settings
from kalshi_bot.data.kalshi_client import KalshiClient
from kalshi_bot.strategy.live_order_manager import LiveOrderManager


V1_STATE_PATH = BASE / "data" / "live_trades" / "state.json"


def main() -> int:
    target_usd = float(sys.argv[1]) if len(sys.argv) > 1 else 13.0
    print(f"Target freed cash: ${target_usd:.2f}", flush=True)

    settings = Settings()
    with KalshiClient(settings) as kc:
        om = LiveOrderManager(kc, state_path=V1_STATE_PATH)
        resting = list(om.state.resting.values())
        if not resting:
            print("No resting orders to cancel.", flush=True)
            return 0
        # Sort ascending by expected_net_edge (worst edges first)
        resting.sort(key=lambda o: o.expected_net_edge or 0.0)

        print(f"v1 has {len(resting)} resting orders.", flush=True)
        print("\nDry-run plan (cancel these to free up cash):", flush=True)
        running = 0.0
        plan: list = []
        for o in resting:
            cost = (o.target_price_cents or 0) * (o.contracts or 0) / 100.0
            running += cost
            plan.append((o, cost))
            print(
                f"  {o.ticker:50s} edge={o.expected_net_edge:+.3f} "
                f"price={(o.target_price_cents or 0) / 100:.2f} "
                f"cost=${cost:.2f}  cumulative=${running:.2f}",
                flush=True,
            )
            if running >= target_usd:
                break

        print(f"\nPlan total freed: ${running:.2f}", flush=True)
        print(f"\nProceed with cancellation? Type 'YES CANCEL' to confirm: ", end="", flush=True)
        confirm = input().strip()
        if confirm != "YES CANCEL":
            print("Aborted.", flush=True)
            return 0

        cancelled_count = 0
        cancelled_cash = 0.0
        for o, cost in plan:
            if not o.order_id:
                print(f"  {o.ticker}: no order_id; skip", flush=True)
                continue
            try:
                kc.delete(f"/portfolio/events/orders/{o.order_id}")
                # Mark in state
                from kalshi_bot.strategy.live_order_manager import LiveOrderStatus
                o.status = LiveOrderStatus.LIVE_CANCELLED
                o.cancelled_ts = __import__("datetime").datetime.now(
                    __import__("datetime").timezone.utc
                ).isoformat()
                # Move from resting to closed pool
                if o.intent_id in om.state.resting:
                    del om.state.resting[o.intent_id]
                om.state.closed[o.intent_id] = o
                cancelled_count += 1
                cancelled_cash += cost
                print(
                    f"  CANCELLED {o.ticker} (${cost:.2f}); total freed ${cancelled_cash:.2f}",
                    flush=True,
                )
            except Exception as e:
                print(f"  FAILED {o.ticker}: {type(e).__name__}: {e}", flush=True)
        om._save()
        print(
            f"\nDone. Cancelled {cancelled_count} orders; freed ${cancelled_cash:.2f}.",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
