"""Cancel resting orders on Kalshi until total exposure fits under cash.

Use when the bot's resting maker bids have accumulated past your actual
cash balance (Kalshi does NOT lock cash on maker bids, so the bot can
stack more bids than it can pay for if they all fill). Symptom: bot
logs `skip_budget_exhausted` repeatedly, or `/portfolio/orders` shows
notional far exceeding `/portfolio/balance` cash.

Strategy: cancel oldest-first until projected exposure <= cash. Oldest
bids are most likely to be stale (not filling for a reason), so they
go first. Stop once we're under budget.

Usage:
    uv run python -m scripts.cancel_excess_resting             # default
    uv run python -m scripts.cancel_excess_resting --dry-run   # preview
    uv run python -m scripts.cancel_excess_resting --headroom 5  # leave
                                                                  # $5 free
    uv run python -m scripts.cancel_excess_resting --all       # cancel
                                                                  # every
                                                                  # resting
                                                                  # order
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime

import structlog

from kalshi_bot.config import load_settings
from kalshi_bot.data.kalshi_client import KalshiClient
from kalshi_bot.logging import configure_logging


def _resting_age_seconds(row: dict, now_ts: float) -> float:
    """Best-effort age computation from Kalshi /portfolio/orders row.

    `created_time` is the canonical placement timestamp. Fall back to
    epoch 0 (treat as oldest possible) if missing or unparseable.
    """
    ts = row.get("created_time") or row.get("created_at")
    if not ts:
        return float("inf")
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return float("inf")
    return now_ts - dt.timestamp()


def _row_notional_usd(row: dict) -> float:
    """Remaining-unfilled notional, in USD."""
    yes_price_raw = row.get("yes_price_dollars")
    if yes_price_raw is not None:
        try:
            price = float(yes_price_raw)
        except (TypeError, ValueError):
            price = 0.0
    else:
        no_raw = row.get("no_price_dollars")
        try:
            price = 1.0 - float(no_raw) if no_raw is not None else 0.0
        except (TypeError, ValueError):
            price = 0.0
    remaining = row.get("remaining_count_fp") or row.get("count") or 0
    try:
        n = float(remaining)
    except (TypeError, ValueError):
        n = 0.0
    return price * n


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview cancellations, do not call Kalshi DELETE.")
    parser.add_argument("--all", action="store_true",
                        help="Cancel every resting order, ignoring budget math.")
    parser.add_argument(
        "--headroom", type=float, default=0.0,
        help="Leave this much USD of headroom under cash. e.g. --headroom 5 "
             "stops cancelling once exposure <= cash - 5. Default 0.",
    )
    parser.add_argument(
        "--max-age-hours", type=float, default=None,
        help="Alternative mode: cancel orders older than this many hours, "
             "regardless of budget. Use 0 to cancel all.",
    )
    args = parser.parse_args()

    configure_logging(log_file=None)
    log = structlog.get_logger(__name__)
    settings = load_settings()

    with KalshiClient(settings) as client:
        bal = client.get("/portfolio/balance")
        cash_cents = int(bal.get("balance") or bal.get("portfolio_balance") or 0)
        pos_cents = int(bal.get("portfolio_value", 0) or 0)
        cash_usd = cash_cents / 100.0
        pos_usd = pos_cents / 100.0

        resting = list(
            client.paginate(
                "/portfolio/orders", item_key="orders", limit=100,
                status="resting", max_pages=10,
            ),
        )

        total_notional = sum(_row_notional_usd(r) for r in resting)
        print("Kalshi state:")
        print(f"  cash:               ${cash_usd:.2f}")
        print(f"  position notional:  ${pos_usd:.2f}")
        print(f"  total portfolio:    ${cash_usd + pos_usd:.2f}")
        print(f"  resting orders:     {len(resting)} bids")
        print(f"  resting notional:   ${total_notional:.2f}")
        print()
        if not resting:
            print("No resting orders to cancel.")
            return 0

        budget = cash_usd - max(0.0, args.headroom)
        over_by = total_notional - budget
        if not args.all and args.max_age_hours is None:
            print(f"Budget (cash - headroom): ${budget:.2f}")
            print(f"Over-committed by:        ${over_by:.2f}")
            if over_by <= 0:
                print("Already under budget. Nothing to cancel.")
                return 0

        # Sort by age, oldest first (most likely to be stale and not
        # filling).
        now_ts = datetime.now().timestamp()
        resting_sorted = sorted(
            resting, key=lambda r: -_resting_age_seconds(r, now_ts),
        )

        cancelled_count = 0
        cancelled_notional = 0.0
        for row in resting_sorted:
            if args.max_age_hours is not None:
                age_h = _resting_age_seconds(row, now_ts) / 3600.0
                if age_h < args.max_age_hours:
                    continue
            elif not args.all:
                # Budget mode: stop once we're under
                remaining_notional = total_notional - cancelled_notional
                if remaining_notional <= budget:
                    break

            order_id = row.get("order_id") or row.get("id")
            ticker = row.get("ticker", "?")
            notional = _row_notional_usd(row)
            age_s = _resting_age_seconds(row, now_ts)
            age_label = f"{age_s/3600:.1f}h" if age_s != float("inf") else "?"

            if not order_id:
                print(f"  [skip] no order_id for {ticker}")
                continue
            if args.dry_run:
                print(
                    f"  [dry-run] would cancel {ticker:40s} "
                    f"${notional:.2f} age={age_label}",
                )
                cancelled_count += 1
                cancelled_notional += notional
                continue
            try:
                client.delete(f"/portfolio/orders/{order_id}")
                print(
                    f"  cancelled {ticker:40s} ${notional:.2f} age={age_label}",
                )
                cancelled_count += 1
                cancelled_notional += notional
            except Exception as exc:  # noqa: BLE001
                print(f"  FAILED  {ticker:40s} {exc}")
                log.warning(
                    "cancel_failed",
                    ticker=ticker, order_id=order_id, error=str(exc),
                )

        remaining_after = total_notional - cancelled_notional
        print()
        verb = "Would cancel" if args.dry_run else "Cancelled"
        print(
            f"{verb} {cancelled_count} orders worth ${cancelled_notional:.2f}.",
        )
        print(
            f"Resting notional now: ${remaining_after:.2f} "
            f"(cash: ${cash_usd:.2f}, headroom: ${cash_usd - remaining_after:.2f}).",
        )
        if not args.dry_run and cancelled_count > 0:
            print()
            print("NEXT: re-run adopt_orphan_orders or restart_bot to refresh")
            print("the bot's local state with the new Kalshi truth.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
