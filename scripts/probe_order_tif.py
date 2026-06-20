"""One-shot probe: find the Kalshi-accepted time_in_force value for resting
limit orders. Tries each candidate, reports which Kalshi accepts.

The probe sends BUY YES at 1 cent on a known-deep-out-of-money market
(price band [0.70, 0.95] but the bid is at $0.01) so Kalshi rejects for
the WRONG reason (invalid_parameters about TimeInForce, or accepted)
but never fills.

Usage: uv run python -m scripts.probe_order_tif
"""

from __future__ import annotations

import sys
import uuid

import structlog

from kalshi_bot.config import load_settings
from kalshi_bot.data.kalshi_client import KalshiClient, KalshiHTTPError
from kalshi_bot.logging import configure_logging


def main() -> int:
    configure_logging()
    log = structlog.get_logger("probe_tif")
    settings = load_settings()

    # We need a real ticker that's open. Pull one from /markets.
    with KalshiClient(settings) as client:
        log.info("probe_start")
        # Get one open sports market.
        ticker_to_use = None
        for s in client.paginate(
            "/series", item_key="series", limit=50,
            category="Sports", max_pages=1,
        ):
            series = s.get("ticker") or s.get("series_ticker")
            if not series:
                continue
            try:
                for m in client.paginate(
                    "/markets", item_key="markets", limit=10,
                    status="open", series_ticker=series, max_pages=1,
                ):
                    t = m.get("ticker")
                    if t:
                        ticker_to_use = t
                        break
            except Exception:
                continue
            if ticker_to_use:
                break
        if not ticker_to_use:
            log.error("no_open_market_found")
            return 1
        log.info("probe_market", ticker=ticker_to_use)

        # Each variant: tries one body shape, captures the error.
        candidates = [
            ("eod_only", {"time_in_force": "EOD"}),
            ("ioc_only", {"time_in_force": "IOC"}),
            ("fok_only", {"time_in_force": "FOK"}),
            ("immediate_or_cancel", {"time_in_force": "immediate_or_cancel"}),
            ("good_till_canceled", {"time_in_force": "good_till_canceled"}),
            ("good_til_canceled", {"time_in_force": "good_til_canceled"}),
            ("good_til_cancelled", {"time_in_force": "good_til_cancelled"}),
            ("end_of_day_snake", {"time_in_force": "end_of_day"}),
            ("none_no_expiry", {}),
            ("future_expiration_ts_seconds",
             {"expiration_ts": 2147483600}),  # 2038-ish in seconds
        ]
        for name, extra in candidates:
            body = {
                "action": "buy", "side": "yes", "ticker": ticker_to_use,
                "type": "limit", "count": 1, "yes_price": 1,  # 1 cent: won't fill
                "client_order_id": uuid.uuid4().hex,
                **extra,
            }
            try:
                response = client.post("/portfolio/orders", json=body)
                log.info("ACCEPTED", variant=name, body_extra=extra,
                         response_status=(response.get("order") or {}).get("status"))
                # If accepted, cancel it immediately so we don't sit on the book.
                order_id = (response.get("order") or {}).get("order_id")
                if order_id:
                    try:
                        client.delete(f"/portfolio/events/orders/{order_id}")
                        log.info("cancelled_probe_order", order_id=order_id)
                    except Exception as exc:
                        log.error("cancel_failed",
                                  order_id=order_id, error=str(exc))
            except KalshiHTTPError as exc:
                log.warning("REJECTED", variant=name, body_extra=extra,
                            status=exc.status, body=exc.body[:300])
            except Exception as exc:
                log.error("ERROR", variant=name, error=str(exc))
    return 0


if __name__ == "__main__":
    sys.exit(main())
