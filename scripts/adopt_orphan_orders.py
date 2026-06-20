"""Adopt Kalshi resting orders into local state.json.

Use when the bot's `check_no_orphan_resting` preflight fails because
Kalshi has open orders the local state file doesn't track. This is
usually caused by:
- Concurrent bot processes clobbering each other's state writes
  (fixed in v6 with the single-instance lock, but historical orders
  may still be unreconciled)
- Manual state.json edits
- A restored state.json backup that's missing recent placements

What it does:
1. Reads all resting orders from Kalshi via /portfolio/orders.
2. For each that is NOT already in local state (resting, filled, or
   closed), creates a synthetic LiveOrder and adds it to state.resting.
3. Writes state.json.

After running, the bot will pass the orphan check on startup. The
adopted orders will be reconciled normally on the next scan loop.

Usage:
    uv run python -m scripts.adopt_orphan_orders             # adopt all
    uv run python -m scripts.adopt_orphan_orders --dry-run   # preview
    uv run python -m scripts.adopt_orphan_orders --cancel    # cancel orphans instead

Safe to run multiple times; already-known orders are skipped.
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
    LiveOrder,
    LiveOrderManager,
    LiveOrderStatus,
)


def _series_from_event(event_ticker: str) -> str:
    """Derive series_ticker from event_ticker by taking the prefix
    before the first '-'. E.g. 'KXMLBWINS-NYY-26-T90' -> 'KXMLBWINS'."""
    if not event_ticker:
        return ""
    head, _sep, _tail = event_ticker.partition("-")
    return head


def _adopt_one(record: dict, *, now_iso: str) -> tuple[str, LiveOrder]:
    """Build a synthetic LiveOrder from a Kalshi /portfolio/orders row.

    Kalshi schema (verified via live probe 2026-05-25):
      client_order_id, order_id, ticker, side, action, status, type,
      yes_price_dollars (str, e.g. "0.7900"),
      no_price_dollars (str, e.g. "0.2100"),
      initial_count_fp (str, e.g. "1.00"),
      remaining_count_fp (str, e.g. "1.00"),
      created_time (ISO), last_update_time (ISO), book_side, outcome_side.

    event_ticker and series_ticker are not present in this endpoint's
    response; we derive series from the ticker prefix and leave
    event_ticker empty (the scanner will reconcile on next loop).
    """
    coid = str(record.get("client_order_id") or record.get("intent_id") or record["order_id"])
    ticker = record.get("ticker", "")
    series_ticker = record.get("series_ticker") or _series_from_event(ticker)
    # Prefer the dollar-string field; tolerate older numeric forms.
    yes_price_raw = record.get("yes_price_dollars")
    if yes_price_raw is not None:
        try:
            yes_price_dollars = float(yes_price_raw)
        except (TypeError, ValueError):
            yes_price_dollars = 0.0
    else:
        # Fallback: 100 - no_price for YES side; or legacy yes_price in cents.
        no_price_raw = record.get("no_price_dollars")
        if no_price_raw is not None:
            try:
                yes_price_dollars = 1.0 - float(no_price_raw)
            except (TypeError, ValueError):
                yes_price_dollars = 0.0
        else:
            yes_price_dollars = float(record.get("yes_price") or 0) / 100.0
    target_price_cents = int(round(yes_price_dollars * 100))
    contracts_raw = (
        record.get("remaining_count_fp")
        or record.get("initial_count_fp")
        or record.get("count")
        or 1
    )
    try:
        contracts = max(1, int(float(contracts_raw)))
    except (TypeError, ValueError):
        contracts = 1
    side = (record.get("side") or record.get("outcome_side") or "yes").lower()
    placed_ts = (
        record.get("created_time")
        or record.get("created_at")
        or now_iso
    )
    market_mid = float(target_price_cents) / 100.0
    order = LiveOrder(
        intent_id=coid,
        ticker=ticker,
        series_ticker=series_ticker,
        event_ticker="",
        side=("yes" if side.startswith("y") else side),
        target_price_cents=target_price_cents,
        contracts=contracts,
        expected_net_edge=0.0,
        market_mid_at_placement=market_mid,
        placed_ts=placed_ts,
        status=LiveOrderStatus.LIVE_RESTING,
        order_id=str(record.get("order_id") or record.get("id") or ""),
        acked_ts=record.get("last_update_time") or record.get("acked_ts") or placed_ts,
    )
    return coid, order


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print what would be adopted; do not write state.json.",
    )
    parser.add_argument(
        "--cancel", action="store_true",
        help="Cancel orphan orders on Kalshi instead of adopting them. "
             "Releases the locked funds back to your cash balance.",
    )
    args = parser.parse_args()

    configure_logging(log_file=None)
    log = structlog.get_logger(__name__)
    settings = load_settings()

    with KalshiClient(settings) as client:
        lm = LiveOrderManager(client=client)
        try:
            kalshi_resting = list(
                client.paginate(
                    "/portfolio/orders", item_key="orders", limit=100,
                    status="resting", max_pages=10,
                ),
            )
        except Exception as exc:
            log.error("portfolio_orders_fetch_failed", error=str(exc))
            print(f"ERROR: cannot fetch /portfolio/orders: {exc}")
            return 1

        known_intent_ids = {
            o.intent_id for o in (
                list(lm.state.resting.values())
                + list(lm.state.filled.values())
                + list(lm.state.closed.values())
            )
        }
        known_order_ids = {
            o.order_id for o in (
                list(lm.state.resting.values())
                + list(lm.state.filled.values())
                + list(lm.state.closed.values())
            ) if o.order_id
        }

        orphans = []
        for r in kalshi_resting:
            coid = r.get("client_order_id")
            oid = r.get("order_id") or r.get("id")
            if coid and coid in known_intent_ids:
                continue
            if oid and oid in known_order_ids:
                continue
            orphans.append(r)

        print(f"Kalshi resting total:    {len(kalshi_resting)}")
        print(f"Already in state:        {len(kalshi_resting) - len(orphans)}")
        print(f"Orphans to handle:       {len(orphans)}")
        print()

        if not orphans:
            print("Nothing to do. State is consistent with Kalshi.")
            return 0

        if args.cancel:
            print("--cancel: cancelling orphan orders on Kalshi.")
            cancelled = 0
            for r in orphans:
                oid = r.get("order_id") or r.get("id")
                ticker = r.get("ticker", "?")
                if not oid:
                    print(f"  [skip] no order_id for {ticker}")
                    continue
                if args.dry_run:
                    print(f"  [dry-run] would cancel {ticker} (order_id={oid})")
                    continue
                try:
                    client.delete(f"/portfolio/events/orders/{oid}")
                    print(f"  cancelled {ticker} (order_id={oid})")
                    cancelled += 1
                except Exception as exc:
                    print(f"  FAILED to cancel {ticker}: {exc}")
            print(f"\nCancelled {cancelled} of {len(orphans)} orphan orders.")
            return 0

        # Default: adopt into state.resting
        now_iso = datetime.now(UTC).isoformat()
        adopted = []
        for r in orphans:
            coid, order = _adopt_one(r, now_iso=now_iso)
            adopted.append((coid, order))
            print(
                f"  adopt {order.ticker:42s}  "
                f"${order.target_price_cents/100:.2f} x{order.contracts}  "
                f"order_id={order.order_id}",
            )

        if args.dry_run:
            print(f"\n[dry-run] Would adopt {len(adopted)} orders. No file written.")
            return 0

        for coid, order in adopted:
            lm.state.resting[coid] = order
        lm._save()
        print(f"\nAdopted {len(adopted)} orders into state.resting. state.json updated.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
