"""One-shot: reconcile local state.json against Kalshi as source of truth.

For each LIVE_RESTING order in our local state:
- If Kalshi /portfolio/orders has it resting: no change.
- If Kalshi has it filled: move to state.filled with filled_count set.
- If Kalshi has nothing (cancelled / unknown): move to state.closed.

Also pull /portfolio/positions to detect filled orders missed by the
fill-parsing bug (filled_count=0 stuck in PARTIAL).

Designed to be safe-by-default: dry-run prints diffs without writing.
Requires --i-mean-it to actually modify state.json.

Bot MUST be stopped before running this; otherwise the bot's next save
overwrites our changes (concurrent-writer race).
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime

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
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--i-mean-it", action="store_true")
    args = parser.parse_args()

    if not args.dry_run and not args.i_mean_it:
        print("Pass --dry-run to preview, or --i-mean-it to write. Refusing.")
        return 1

    configure_logging()
    log = structlog.get_logger("fix_state")
    settings = load_settings()

    with KalshiClient(settings) as client:
        lm = LiveOrderManager(client=client)
        print(f"Local state.resting: {len(lm.state.resting)}")
        print(f"Local state.filled:  {len(lm.state.filled)}")
        print()

        # Pull Kalshi truth
        kalshi_resting_raw = list(client.paginate(
            "/portfolio/orders", item_key="orders", limit=200,
            status="resting", max_pages=10,
        ))
        kalshi_resting_by_coid = {
            r.get("client_order_id"): r for r in kalshi_resting_raw
            if r.get("client_order_id")
        }
        kalshi_resting_by_order_id = {
            (r.get("order_id") or r.get("id")): r for r in kalshi_resting_raw
        }

        positions = client.get("/portfolio/positions").get("market_positions", [])
        positions_by_ticker = {
            p.get("ticker"): p for p in positions if int(float(p.get("position_fp", 0) or 0)) > 0
        }
        print(f"Kalshi resting:      {len(kalshi_resting_raw)}")
        print(f"Kalshi positions held (position_fp>0): {len(positions_by_ticker)}")
        for t, p in positions_by_ticker.items():
            print(f"  {t}: position_fp={p.get('position_fp')} exposure=${p.get('market_exposure_dollars')}")
        print()

        actions = []
        for intent_id, order in lm.state.resting.items():
            kr = kalshi_resting_by_coid.get(intent_id)
            if kr is None and order.order_id:
                kr = kalshi_resting_by_order_id.get(order.order_id)
            if kr is not None:
                # Still resting on Kalshi - no action.
                continue
            # Not resting on Kalshi. Check if we have a position.
            pos = positions_by_ticker.get(order.ticker)
            if pos is not None:
                actions.append(("FILL", intent_id, order, pos))
            else:
                actions.append(("CANCEL", intent_id, order, None))

        if not actions:
            print("Local state matches Kalshi. Nothing to do.")
            return 0

        print(f"Planned changes: {len(actions)}")
        for kind, _intent_id, order, pos in actions:
            if kind == "FILL":
                pf = int(float(pos.get("position_fp", 1) or 1))
                exp = float(pos.get("market_exposure_dollars", 0) or 0)
                px_cents = int(round((exp / max(pf, 1)) * 100)) if pf > 0 else order.target_price_cents
                print(f"  FILL    {order.ticker:45} position_fp={pf} "
                      f"avg_price={px_cents}c")
            else:
                print(f"  CANCEL  {order.ticker:45} order_id={order.order_id}")

        if args.dry_run:
            print("\n[DRY RUN] No changes written.")
            return 0

        now_iso = datetime.now(UTC).isoformat()
        for kind, intent_id, order, pos in actions:
            if kind == "FILL":
                pf = int(float(pos.get("position_fp", 1) or 1))
                exp = float(pos.get("market_exposure_dollars", 0) or 0)
                px_cents = int(round((exp / max(pf, 1)) * 100)) if pf > 0 else order.target_price_cents
                order.filled_count = pf
                order.filled_price_cents = px_cents
                order.filled_ts = now_iso
                order.status = LiveOrderStatus.LIVE_FILLED
                lm.state.filled[intent_id] = order
                del lm.state.resting[intent_id]
                log.info("state_fix_filled", ticker=order.ticker, count=pf,
                         price_cents=px_cents)
            else:
                order.status = LiveOrderStatus.LIVE_CANCELLED
                order.cancelled_ts = now_iso
                lm.state.closed[intent_id] = order
                del lm.state.resting[intent_id]
                log.info("state_fix_cancelled", ticker=order.ticker,
                         order_id=order.order_id)
        lm._save()  # noqa: SLF001
        print(f"\nApplied {len(actions)} changes. "
              f"resting={len(lm.state.resting)} "
              f"filled={len(lm.state.filled)} "
              f"closed={len(lm.state.closed)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
