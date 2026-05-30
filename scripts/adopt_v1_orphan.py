"""One-shot: adopt a specific lost v1 order from Kalshi into v1 local state.

Unlike the v14 orphan adopter (which auto-detects by client_order_id prefix
"14" + KXMLBGAME series), v1 orphans are PRE-tagging-era raw-uuid orders that
cannot be attributed to v1 vs a manual operator position by inspection alone.
So this tool adopts ONLY an order the operator NAMES by client_order_id prefix
(operator-authorized), never auto-detects. Default target is the confirmed
lost v1 order KXUFCOCCUR-26CMCGMHOL (coid 342f2cb1...), operator-confirmed
2026-05-30.

Safety (same model as adopt_v14_orphans):
- Dry-run by default; --i-mean-it required to write.
- Adopts into v1 state.filled with NO P&L; reconcile_settlements stays the
  single writer of realized_pnl_total_usd.
- Dedups on client_order_id AND order_id across BOTH v1 and v14 pools (never
  adopt something v14 owns or v1 already tracks).
- Rejects a non-1..99c price.
- Seeds processed_fill_ids from the order's fills.
- The v1 bot MUST be stopped before --i-mean-it (concurrent-writer race).

    PYTHONPATH=src .venv-kronos/Scripts/python.exe -m scripts.adopt_v1_orphan
    PYTHONPATH=src .venv-kronos/Scripts/python.exe -m scripts.adopt_v1_orphan --i-mean-it
    PYTHONPATH=src .venv-kronos/Scripts/python.exe -m scripts.adopt_v1_orphan --coid <prefix>
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

BASE = Path("C:/Users/SamJD/OneDrive/Desktop/AI Projects/Project Kalshi")
sys.path.insert(0, str(BASE / "src"))

from kalshi_bot.config import Settings
from kalshi_bot.data.kalshi_client import KalshiClient
from kalshi_bot.strategy.live_order_manager import (
    LiveOrder,
    LiveOrderManager,
    LiveOrderStatus,
)

V1_STATE_PATH = BASE / "data" / "live_trades" / "state.json"
V14_STATE_PATH = BASE / "data" / "v14" / "v14_state.json"
DEFAULT_COID_PREFIX = "342f2cb1"  # operator-confirmed lost v1 UFC order


def _series_from_ticker(ticker: str) -> str:
    head, _, _ = ticker.partition("-")
    return head


def reconstruct_v1_filled_order(rec: dict, now_iso: str) -> LiveOrder:
    """Build a LIVE_FILLED LiveOrder from a /portfolio/orders executed row.

    Series is derived from the ticker prefix (v1 trades many series), unlike
    the v14 adopter which hardcodes KXMLBGAME.
    """
    coid = str(rec.get("client_order_id"))
    ticker = str(rec.get("ticker") or "")
    yes_price_dollars = float(rec.get("yes_price_dollars") or 0.0)
    price_cents = int(round(yes_price_dollars * 100))
    if not (1 <= price_cents <= 99):
        raise ValueError(
            f"non-physical price {price_cents}c for {ticker} (coid {coid}); "
            f"refusing to adopt",
        )
    count_raw = rec.get("fill_count_fp") or rec.get("initial_count_fp") or 0
    contracts = max(1, int(round(float(count_raw))))
    event_ticker = ticker.rsplit("-", 1)[0] if "-" in ticker else ticker
    return LiveOrder(
        intent_id=coid,
        ticker=ticker,
        series_ticker=_series_from_ticker(ticker),
        event_ticker=event_ticker,
        side="yes",
        target_price_cents=price_cents,
        contracts=contracts,
        expected_net_edge=0.0,
        market_mid_at_placement=price_cents / 100.0,
        placed_ts=str(rec.get("created_time") or now_iso),
        status=LiveOrderStatus.LIVE_FILLED,
        order_id=str(rec.get("order_id") or ""),
        acked_ts=str(rec.get("created_time") or now_iso),
        filled_ts=str(rec.get("last_update_time") or rec.get("created_time") or now_iso),
        filled_price_cents=price_cents,
        filled_count=contracts,
    )


def _tracked_ids(path: Path) -> tuple[set[str], set[str]]:
    import json
    coids: set[str] = set()
    oids: set[str] = set()
    if not path.exists():
        return coids, oids
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return coids, oids
    for pool in ("intents", "resting", "filled", "closed"):
        for iid, rec in (raw.get(pool) or {}).items():
            coids.add(iid)
            if rec.get("order_id"):
                oids.add(rec["order_id"])
    return coids, oids


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--coid", default=DEFAULT_COID_PREFIX,
                        help="client_order_id prefix of the order to adopt.")
    parser.add_argument("--i-mean-it", action="store_true",
                        help="Write state.json. Default is dry-run.")
    args = parser.parse_args()
    now = datetime.now(UTC)
    now_iso = now.isoformat()

    with KalshiClient(Settings()) as kc:
        mgr = LiveOrderManager(kc, state_path=V1_STATE_PATH)  # v1 default prefix

        v1_coids, v1_oids = _tracked_ids(V1_STATE_PATH)
        v14_coids, v14_oids = _tracked_ids(V14_STATE_PATH)

        executed = list(kc.paginate(
            "/portfolio/orders", item_key="orders", limit=200,
            status="executed", max_pages=10,
        ))
        match = [
            o for o in executed
            if (o.get("client_order_id") or "").startswith(args.coid)
        ]
        if not match:
            print(f"No executed order with client_order_id prefix '{args.coid}'.")
            return 1

        adopt: list[LiveOrder] = []
        for rec in match:
            coid = rec.get("client_order_id") or ""
            oid = rec.get("order_id") or ""
            if coid in v1_coids or oid in v1_oids:
                print(f"SKIP {rec.get('ticker')}: already tracked by v1.")
                continue
            if coid in v14_coids or oid in v14_oids:
                print(f"SKIP {rec.get('ticker')}: owned by v14, not adopting into v1.")
                continue
            try:
                order = reconstruct_v1_filled_order(rec, now_iso)
            except ValueError as exc:
                print(f"SKIP (bad data): {exc}")
                continue
            adopt.append(order)

        if not adopt:
            print("Nothing to adopt.")
            return 0

        print(f"Will adopt {len(adopt)} order(s) into v1 state.filled:")
        for o in adopt:
            m = kc.get(f"/markets/{o.ticker}").get("market", {}) or {}
            print(f"  {o.ticker:42} YES {o.filled_count}c @ {o.filled_price_cents}c "
                  f"(series {o.series_ticker}); market status={m.get('status')} "
                  f"close={m.get('close_time')}")
        print("\nThese adopt with NO P&L; reconcile_settlements books P&L when "
              "the market resolves (active ones settle later, not on restart).")

        if not args.i_mean_it:
            print("\n[DRY RUN] No state written. Re-run with --i-mean-it to adopt.")
            print("The v1 bot MUST be stopped before writing.")
            return 0

        # Seed processed_fill_ids from the adopted orders' fills.
        oids = {o.order_id for o in adopt if o.order_id}
        look_back = int((now - timedelta(days=30)).timestamp())
        seeded = 0
        try:
            fills = list(kc.paginate(
                "/portfolio/fills", item_key="fills", limit=200,
                min_ts=look_back, max_pages=10,
            ))
            for f in fills:
                if f.get("order_id") in oids:
                    fid = f.get("trade_id") or f.get("fill_id") or f.get("id")
                    if fid and fid not in mgr.state.processed_fill_ids:
                        mgr.state.processed_fill_ids.append(fid)
                        seeded += 1
        except Exception as exc:
            print(f"WARNING: could not seed processed_fill_ids: {exc}")

        for o in adopt:
            mgr.state.filled[o.intent_id] = o
        mgr._save()
        print(f"\nAdopted {len(adopt)} order(s) into v1 state.filled; "
              f"seeded {seeded} fill ids. Restart v1 to resume tracking.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
