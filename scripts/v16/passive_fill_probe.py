"""v16 Phase 3: tiny live PASSIVE-FILL probe (TRIPLE-GATED, dry-run default).

The only honest test of whether the Kalshi lead-lag lag is HARVESTABLE by a
passive maker is to actually rest tiny non-marketable orders and observe real
fills (record-only snapshots manufacture phantom fills on winners; see
research/v16/01-methodology-lock.md, Gate B). This script does exactly that,
at the smallest possible size, behind hard safety gates.

SAFETY (a real order is placed ONLY when ALL THREE hold):
  1. --live is passed (default is DRY-RUN: prints intended orders, places none).
  2. --i-understand-this-places-real-orders is passed.
  3. The marker file data/v16/GATE_A_PASSED exists. Per the methodology lock,
     Phase 3 is DEFERRED until Gate A (does the lag exist) has passed at full
     MLB season. The operator creates this marker ONLY after that, by hand.
Plus: 1 contract per order, --max-orders cap (default 5), price clamped to
[1, 99]c, and only on fires whose game has NOT yet commenced.

It reuses LiveOrderManager with intent_id_prefix "16" (distinct from v1=11,
v14=14) and its OWN state file data/v16/passive_probe_state.json, so it can
never touch v1 or v14 capital or state.

Usage:
  # DRY RUN (safe; default): show what it would place
  .venv\\Scripts\\python.exe scripts\\v16\\passive_fill_probe.py
  # Reconcile fills/settlements and cancel stale probe orders
  .venv\\Scripts\\python.exe scripts\\v16\\passive_fill_probe.py --reconcile
  # LIVE (only after Gate A passes AND the marker file is created by hand):
  .venv\\Scripts\\python.exe scripts\\v16\\passive_fill_probe.py --live \\
      --i-understand-this-places-real-orders --max-orders 5
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

BASE = Path("C:/Users/SamJD/OneDrive/Desktop/AI Projects/Project Kalshi")
sys.path.insert(0, str(BASE / "src"))

load_dotenv(BASE / ".env")

from kalshi_bot.analysis.lead_lag_shadow import (  # noqa: E402
    parse_orderbook,
    passive_probe_limit_cents,
)
from kalshi_bot.config import Settings  # noqa: E402
from kalshi_bot.data.kalshi_client import KalshiClient  # noqa: E402
from kalshi_bot.strategy.live_order_manager import LiveOrderManager  # noqa: E402

DATA_DIR = BASE / "data" / "v16"
SHADOW_DIR = DATA_DIR / "shadow"
ENTRIES_PATH = SHADOW_DIR / "entries.parquet"
PROBE_STATE = DATA_DIR / "passive_probe_state.json"
PROBE_LOG = DATA_DIR / "passive_probe_log.jsonl"
GATE_A_PASSED = DATA_DIR / "GATE_A_PASSED"

SERIES = "KXMLBGAME"


def now_utc() -> datetime:
    return datetime.now(UTC)


def log_event(payload: dict) -> None:
    payload.setdefault("ts_utc", now_utc().isoformat())
    PROBE_LOG.parent.mkdir(parents=True, exist_ok=True)
    with PROBE_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, default=str) + "\n")


def read_book(kc: KalshiClient, ticker: str) -> dict:
    try:
        payload = kc.get(f"/markets/{ticker}/orderbook")
    except Exception as exc:  # noqa: BLE001
        return {"book_empty": True, "error": str(exc)}
    return parse_orderbook(payload)


def probed_tickers(om: LiveOrderManager) -> set[str]:
    """Every ticker this probe has already touched (any pool), so we never
    double-probe the same market."""
    out: set[str] = set()
    for pool in (om.state.intents, om.state.resting, om.state.filled, om.state.closed):
        for o in pool.values():
            out.add(o.ticker)
    return out


def candidate_fires(already: set[str], max_orders: int) -> list[dict]:
    """Logged fires (fired==True) with a ticker, whose game has NOT commenced,
    not already probed. Most recent first, capped at max_orders."""
    if not ENTRIES_PATH.exists():
        return []
    try:
        df = pd.read_parquet(ENTRIES_PATH)
    except Exception as exc:  # noqa: BLE001
        log_event({"event": "probe_entries_read_failed", "error": str(exc)})
        return []
    fires = df[df["fired"] == True]  # noqa: E712
    now = now_utc()
    rows: list[dict] = []
    for _idx, e in fires.sort_values("captured_ts", ascending=False).iterrows():
        ticker = e.get("ticker") or ""
        if not ticker or ticker in already:
            continue
        commence_ts = e.get("commence_ts") or ""
        if commence_ts:
            try:
                cdt = pd.Timestamp(commence_ts).tz_convert("UTC").to_pydatetime()
                if cdt <= now:
                    continue  # game already started; cannot passively pre-enter
            except Exception:  # noqa: BLE001
                continue
        rows.append(dict(e))
        if len(rows) >= max_orders:
            break
    return rows


def do_reconcile(om: LiveOrderManager, cancel_age_min: float) -> None:
    filled = om.reconcile_fills()
    settled = om.reconcile_settlements()
    cancelled = om.cancel_stale_resting(max_age_hours=cancel_age_min / 60.0)
    print(
        f"reconcile: fills_applied={len(filled)} settled={len(settled)} "
        f"stale_cancelled={len(cancelled)} "
        f"realized_pnl=${om.state.realized_pnl_total_usd:+.2f}"
    )
    log_event({
        "event": "probe_reconcile", "fills_applied": len(filled),
        "settled": len(settled), "stale_cancelled": len(cancelled),
        "realized_pnl_usd": om.state.realized_pnl_total_usd,
    })


def do_place(
    om: LiveOrderManager, kc: KalshiClient, *, live: bool,
    max_orders: int, min_spread: float,
) -> None:
    already = probed_tickers(om)
    candidates = candidate_fires(already, max_orders)
    if not candidates:
        print("no eligible candidate fires (none logged, all probed, or all commenced)")
        return
    placed = 0
    for e in candidates:
        ticker = e["ticker"]
        book = read_book(kc, ticker)
        limit_cents = passive_probe_limit_cents(book, min_spread=min_spread)
        if limit_cents is None:
            print(f"  SKIP {ticker}: no clean passive limit (book={book.get('book_empty')})")
            log_event({"event": "probe_skip", "ticker": ticker, "reason": "no_limit"})
            continue
        target_price = limit_cents / 100.0
        if not live:
            print(
                f"  DRY-RUN would place: {ticker} BUY YES 1c @ ${target_price:.2f} "
                f"(book yes_bid={book.get('yes_bid')} yes_ask={book.get('yes_ask')})"
            )
            log_event({
                "event": "probe_dry_run", "ticker": ticker,
                "target_price": target_price,
            })
            continue
        try:
            order = om.place_live_order(
                ticker=ticker, series_ticker=SERIES,
                event_ticker=ticker.rsplit("-", 1)[0],
                target_price=target_price, contracts=1,
                expected_net_edge=0.0, market_mid_at_placement=book.get("mid") or target_price,
            )
            placed += 1
            print(f"  PLACED {ticker} BUY YES 1c @ ${target_price:.2f} status={order.status.value}")
            log_event({
                "event": "probe_placed", "ticker": ticker,
                "target_price": target_price, "intent_id": order.intent_id,
                "order_id": order.order_id, "status": order.status.value,
            })
        except Exception as exc:  # noqa: BLE001
            print(f"  PLACE FAILED {ticker}: {type(exc).__name__}: {exc}")
            log_event({"event": "probe_place_failed", "ticker": ticker, "error": str(exc)})
    print(f"done: {placed} live order(s) placed; {len(candidates)} candidate(s) evaluated")


def main() -> int:
    ap = argparse.ArgumentParser(description="v16 Phase 3 passive-fill probe (dry-run default)")
    ap.add_argument("--live", action="store_true",
                    help="Place REAL 1-contract resting orders. Requires the other two gates.")
    ap.add_argument("--i-understand-this-places-real-orders", dest="i_understand",
                    action="store_true", help="Explicit acknowledgement gate.")
    ap.add_argument("--reconcile", action="store_true",
                    help="Reconcile fills/settlements and cancel stale probe orders, then exit.")
    ap.add_argument("--max-orders", type=int, default=5, help="Max orders to place (default 5).")
    ap.add_argument("--min-spread", type=float, default=0.02,
                    help="Min yes spread to rest passively (default 0.02 = 2c).")
    ap.add_argument("--cancel-age-min", type=float, default=180.0,
                    help="Cancel resting probe orders older than this (reconcile mode).")
    args = ap.parse_args()

    settings = Settings()
    with KalshiClient(settings) as kc:
        om = LiveOrderManager(kc, state_path=PROBE_STATE, intent_id_prefix="16")
        if args.reconcile:
            do_reconcile(om, args.cancel_age_min)
            return 0

        # Resolve the live gate. A real order requires ALL THREE conditions.
        live = False
        if args.live:
            if not args.i_understand:
                print("REFUSED: --live requires --i-understand-this-places-real-orders.")
                return 3
            if not GATE_A_PASSED.exists():
                print(
                    f"REFUSED: --live requires the Gate-A marker file to exist:\n"
                    f"  {GATE_A_PASSED}\n"
                    f"Per research/v16/01-methodology-lock.md, Phase 3 is deferred until "
                    f"Gate A passes at full MLB season. Create the marker by hand ONLY then."
                )
                return 3
            live = True
            print("=" * 70)
            print("LIVE MODE: placing REAL 1-contract resting orders on Kalshi.")
            print("=" * 70)
        else:
            print("DRY-RUN (default). No orders will be placed. Pass --live to go live.")

        do_place(om, kc, live=live, max_orders=args.max_orders, min_spread=args.min_spread)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
