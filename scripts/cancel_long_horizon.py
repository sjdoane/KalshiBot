"""Cancel resting orders with total market lifetime above a threshold.

One-shot cleanup aligned with the max_lifetime_days filter added in
research/time-scale-analysis.md. Queries each resting order's market,
computes lifetime, and DELETEs the order via Kalshi /portfolio/orders.

Usage:
    uv run python -m scripts.cancel_long_horizon --threshold-days 180
    uv run python -m scripts.cancel_long_horizon --threshold-days 180 --dry-run

Refuses to run without an explicit confirmation flag to avoid
accidental cancellations.
"""

from __future__ import annotations

import argparse
import sys

import pandas as pd
import structlog

from kalshi_bot.config import load_settings
from kalshi_bot.data.kalshi_client import KalshiClient
from kalshi_bot.logging import configure_logging
from kalshi_bot.strategy.live_order_manager import (
    LiveOrderManager,
    LiveOrderStatus,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--threshold-days", type=float, default=180.0,
                        help="Lifetime cap in days. Orders with total "
                             "market lifetime (open_to_close) above this "
                             "are cancelled.")
    parser.add_argument("--dry-run", action="store_true",
                        help="List what would be cancelled, do not call DELETE.")
    parser.add_argument("--i-mean-it", action="store_true",
                        help="Required for live cancellation. Without this, "
                             "the script will refuse to run unless --dry-run.")
    args = parser.parse_args()

    if not args.dry_run and not args.i_mean_it:
        print("ERROR: pass --dry-run to preview, or --i-mean-it to actually "
              "cancel. Refusing to proceed.")
        return 1

    configure_logging()
    log = structlog.get_logger("cancel_long_horizon")
    settings = load_settings()

    with KalshiClient(settings) as client:
        lm = LiveOrderManager(client=client)
        if not lm.state.resting:
            print("No resting orders. Nothing to do.")
            return 0

        to_cancel = []
        for intent_id, order in lm.state.resting.items():
            try:
                m = client.get(f"/markets/{order.ticker}").get("market", {})
                open_t = pd.Timestamp(m.get("open_time"))
                close_t = pd.Timestamp(m.get("close_time"))
                lifetime = (close_t - open_t).total_seconds() / 86400.0
            except Exception as exc:
                log.warning("market_fetch_failed", ticker=order.ticker,
                            error=str(exc))
                continue
            if lifetime > args.threshold_days:
                to_cancel.append((intent_id, order, lifetime))

        if not to_cancel:
            print(f"No resting orders exceed {args.threshold_days}d lifetime.")
            return 0

        print(f"\nFound {len(to_cancel)} resting order(s) over "
              f"{args.threshold_days}d lifetime:")
        for _intent_id, order, lifetime in to_cancel:
            print(f"  {order.ticker:45} lifetime={lifetime:.1f}d "
                  f"order_id={order.order_id}")

        if args.dry_run:
            print("\n[DRY RUN] No orders cancelled.")
            return 0

        print(f"\nCancelling {len(to_cancel)} orders...")
        cancelled = 0
        from datetime import UTC, datetime
        for intent_id, order, _lifetime in to_cancel:
            if not order.order_id:
                continue
            try:
                client.delete(f"/portfolio/orders/{order.order_id}")
            except Exception as exc:
                log.error("cancel_failed", intent_id=intent_id,
                          order_id=order.order_id, error=str(exc))
                continue
            order.status = LiveOrderStatus.LIVE_CANCELLED
            order.cancelled_ts = datetime.now(UTC).isoformat()
            lm.state.closed[intent_id] = order
            del lm.state.resting[intent_id]
            cancelled += 1
            print(f"  cancelled {order.ticker}")

        lm._save()  # noqa: SLF001
        print(f"\nCancelled {cancelled} of {len(to_cancel)} orders. "
              f"{len(lm.state.resting)} remain resting.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
