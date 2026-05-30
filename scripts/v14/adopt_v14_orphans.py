"""One-shot: adopt v14 orphan orders from Kalshi into v14 local state.

Context: a 2026-05-29 multi-daemon race (since guarded by a single-instance
lock) placed real prefix-"14" orders that never made it into
data/v14/v14_state.json. They filled and their games resolved, so v14's
realized P&L and exposure are incomplete. This script pulls
/portfolio/orders, finds prefix-"14" EXECUTED orders not in local state, and
adopts them into state.filled so the bot's normal reconcile_settlements()
settles them and books their P&L exactly once.

Design locked by council + verifier (research/v14/06-settlement-status-bugfix.md
follow-up):
- Dry-run by default; --i-mean-it required to write.
- Prefix-guarded to "14"; only ever touches data/v14/v14_state.json.
- Dedups on client_order_id AND order_id across ALL pools (idempotent: a
  second run finds nothing).
- Adopts into `filled` with NO P&L set; reconcile_settlements() stays the
  SINGLE writer of realized_pnl_total_usd (prevents double-count).
- Seeds processed_fill_ids with the adopted orders' fills so a later
  reconcile_fills() can never re-apply them.
- Projects post-settle realized P&L and whether the drawdown /
  consecutive-loss kills will trip BEFORE writing, so the operator deploys
  with eyes open (a v14 self-kill on first loop is the safety net working).

The v14 bot MUST be stopped before running with --i-mean-it (concurrent
writer race). After adopting, restart v14; its next loop settles them.

    PYTHONPATH=src .venv-kronos/Scripts/python.exe -m scripts.v14.adopt_v14_orphans
    PYTHONPATH=src .venv-kronos/Scripts/python.exe -m scripts.v14.adopt_v14_orphans --i-mean-it
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

PREFIX = "14"
V14_STATE_PATH = BASE / "data" / "v14" / "v14_state.json"
V1_STATE_PATH = BASE / "data" / "live_trades" / "state.json"
SERIES = "KXMLBGAME"
SERIES_TICKER_PREFIX = "KXMLBGAME-"  # v14 trades ONLY this series
V14_BANKROLL_FRACTION = 0.40
V14_DRAWDOWN_KILL_FRACTION = 0.20
CONSECUTIVE_LOSS_KILL = 5


def reconstruct_filled_order(rec: dict, now_iso: str) -> LiveOrder:
    """Build a LIVE_FILLED LiveOrder from a /portfolio/orders executed row.

    Units: yes_price_dollars is a dollar string ("0.4200"); fill_count_fp is
    a fixed-point string ("2.00"). filled_price_cents is integer cents.
    """
    coid = str(rec.get("client_order_id"))
    ticker = str(rec.get("ticker") or "")
    yes_price_dollars = float(rec.get("yes_price_dollars") or 0.0)
    price_cents = int(round(yes_price_dollars * 100))
    # Kalshi prices are 1..99c. A 0 or out-of-range value means missing/bad
    # data; never adopt it (a 0-cent entry would book a phantom +$1/contract
    # win at settlement). Caller skips on ValueError.
    if not (1 <= price_cents <= 99):
        raise ValueError(
            f"non-physical price {price_cents}c for {ticker} (coid {coid}); "
            f"refusing to adopt",
        )
    count_raw = rec.get("fill_count_fp") or rec.get("initial_count_fp") or 0
    contracts = max(1, int(round(float(count_raw))))
    placed_ts = str(rec.get("created_time") or now_iso)
    event_ticker = ticker.rsplit("-", 1)[0] if "-" in ticker else ticker
    return LiveOrder(
        intent_id=coid,
        ticker=ticker,
        series_ticker=SERIES,
        event_ticker=event_ticker,
        side="yes",
        target_price_cents=price_cents,
        contracts=contracts,
        expected_net_edge=0.0,
        market_mid_at_placement=price_cents / 100.0,
        placed_ts=placed_ts,
        status=LiveOrderStatus.LIVE_FILLED,
        order_id=str(rec.get("order_id") or ""),
        acked_ts=str(rec.get("created_time") or now_iso),
        filled_ts=str(rec.get("last_update_time") or rec.get("created_time") or now_iso),
        filled_price_cents=price_cents,
        filled_count=contracts,
    )


def _market_outcome(kc: KalshiClient, ticker: str) -> tuple[str, int | None]:
    """Return (status, outcome) where outcome is 1/0/-1 or None if not
    terminal. Mirrors reconcile_settlements' terminal-status logic."""
    try:
        m = kc.get(f"/markets/{ticker}").get("market", {}) or {}
    except Exception:
        return "fetch_error", None
    status = (m.get("status") or "").lower()
    if status not in ("finalized", "settled"):
        return status, None
    result = (m.get("result") or "").strip().lower()
    if result == "yes":
        return status, 1
    if result == "no":
        return status, 0
    return status, -1


def _load_state_ids(path: Path) -> tuple[set[str], set[str]]:
    """Return (client_order_ids, order_ids) tracked in another bot's state.

    Used for cross-bot dedup: a PRE-tagging-era v1 order has a raw uuid that
    can coincidentally start with "14" (verified: KXNBAPLAYOFFWINS-26OKC-11,
    coid 14ea6db7..., is a v1 order). Adopting it into v14 would steal a live
    v1 position, so any order tracked by v1 is excluded.
    """
    import json
    coids: set[str] = set()
    oids: set[str] = set()
    if not path.exists():
        return coids, oids
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return coids, oids
    for pool_name in ("intents", "resting", "filled", "closed"):
        for iid, rec in (raw.get(pool_name) or {}).items():
            coids.add(iid)
            oid = rec.get("order_id")
            if oid:
                oids.add(oid)
    return coids, oids


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--i-mean-it", action="store_true",
                        help="Write state.json. Default is dry-run.")
    args = parser.parse_args()
    write = args.i_mean_it

    now = datetime.now(UTC)
    now_iso = now.isoformat()

    with KalshiClient(Settings()) as kc:
        mgr = LiveOrderManager(
            kc, state_path=V14_STATE_PATH, intent_id_prefix=PREFIX,
        )

        known_intent_ids = set()
        known_order_ids = set()
        for pool in (mgr.state.intents, mgr.state.resting,
                     mgr.state.filled, mgr.state.closed):
            for o in pool.values():
                known_intent_ids.add(o.intent_id)
                if o.order_id:
                    known_order_ids.add(o.order_id)

        # Cross-bot dedup: never adopt anything v1 already tracks.
        v1_coids, v1_oids = _load_state_ids(V1_STATE_PATH)

        executed = list(kc.paginate(
            "/portfolio/orders", item_key="orders", limit=200,
            status="executed", max_pages=10,
        ))
        orphans = []
        excluded_non_mlb = 0
        excluded_v1 = 0
        for rec in executed:
            coid = rec.get("client_order_id") or ""
            oid = rec.get("order_id") or ""
            ticker = rec.get("ticker") or ""
            if not coid.startswith(PREFIX):
                continue
            # Already tracked by v14.
            if coid in known_intent_ids or (oid and oid in known_order_ids):
                continue
            # Series guard: v14 trades ONLY KXMLBGAME. Anything else with a
            # "14"-leading coid is a pre-tagging-era raw-uuid collision.
            if not ticker.startswith(SERIES_TICKER_PREFIX):
                excluded_non_mlb += 1
                continue
            # Cross-bot guard: skip anything v1 owns (covers a colliding
            # pre-tagging v1 KXMLBGAME order).
            if coid in v1_coids or (oid and oid in v1_oids):
                excluded_v1 += 1
                continue
            orphans.append(rec)

        if excluded_non_mlb or excluded_v1:
            print(f"excluded {excluded_non_mlb} non-MLB + {excluded_v1} v1-owned "
                  f"prefix-collision orders")

        print(f"prefix-{PREFIX} executed on Kalshi : "
              f"{sum(1 for r in executed if (r.get('client_order_id') or '').startswith(PREFIX))}")
        print(f"already tracked in v14 state       : {len(known_intent_ids)}")
        print(f"ORPHANS to adopt                   : {len(orphans)}")
        print()
        if not orphans:
            print("Nothing to adopt. v14 state is consistent with Kalshi.")
            return 0

        # Reconstruct + project P&L (read-only).
        adopted: list[LiveOrder] = []
        projected_rows: list[tuple[LiveOrder, str, int | None, float | None]] = []
        for rec in orphans:
            try:
                order = reconstruct_filled_order(rec, now_iso)
            except ValueError as exc:
                print(f"  SKIP (bad data): {exc}")
                continue
            adopted.append(order)
            status, outcome = _market_outcome(kc, order.ticker)
            pnl = (mgr._compute_realized_pnl(order, outcome)
                   if outcome is not None else None)
            projected_rows.append((order, status, outcome, pnl))

        res_label = {1: "YES", 0: "NO", -1: "VOID", None: "(pending)"}
        print(f"{'ticker':40} {'px':>5} {'ct':>3} {'status':>10} {'res':>9} {'proj P&L':>9}")
        orphan_pnl = 0.0
        for order, status, outcome, pnl in projected_rows:
            if pnl is not None:
                orphan_pnl += pnl
            print(f"{order.ticker:40} {order.filled_price_cents/100:>5.2f} "
                  f"{order.filled_count:>3} {status:>10} {res_label[outcome]:>9} "
                  f"{('$%+.2f' % pnl) if pnl is not None else '(pending)':>9}")

        # Project tracked filled orders that will ALSO settle on restart.
        tracked_pnl = 0.0
        tracked_pending = 0
        for o in mgr.state.filled.values():
            status, outcome = _market_outcome(kc, o.ticker)
            if outcome is None:
                tracked_pending += 1
                continue
            tracked_pnl += mgr._compute_realized_pnl(o, outcome)

        current = mgr.state.realized_pnl_total_usd
        projected_total = current + tracked_pnl + orphan_pnl

        # Drawdown kill projection (needs live bankroll).
        bal = kc.get("/portfolio/balance")
        bal_cents = bal.get("balance")
        if bal_cents is None:
            bal_cents = bal.get("portfolio_balance", 0)
        cash = float(int(bal_cents or 0)) / 100.0
        posv = float(int(bal.get("portfolio_value") or 0)) / 100.0
        v14_cap = V14_BANKROLL_FRACTION * (cash + posv)
        ddown_threshold = -V14_DRAWDOWN_KILL_FRACTION * v14_cap

        print()
        print("KILL PROJECTION (after restart settles tracked + adopted):")
        print(f"  current realized_pnl_total      : ${current:+.2f}")
        print(f"  tracked filled will add         : ${tracked_pnl:+.2f} "
              f"({tracked_pending} still pending)")
        print(f"  adopted orphans will add        : ${orphan_pnl:+.2f}")
        print(f"  PROJECTED realized_pnl_total    : ${projected_total:+.2f}")
        print(f"  v14 cap (0.40*bankroll)         : ${v14_cap:.2f}")
        print(f"  drawdown threshold (-20%)       : ${ddown_threshold:+.2f}")
        trips = projected_total <= ddown_threshold
        print(f"  >>> DRAWDOWN KILL WILL TRIP      : {'YES' if trips else 'no'}")
        print()

        if not write:
            print("[DRY RUN] No state written. Re-run with --i-mean-it to adopt.")
            print("Make sure the v14 bot is STOPPED before writing.")
            return 0

        # Seed processed_fill_ids from the adopted orders' fills.
        orphan_oids = {o.order_id for o in adopted if o.order_id}
        look_back = int((now - timedelta(days=7)).timestamp())
        seeded = 0
        try:
            fills = list(kc.paginate(
                "/portfolio/fills", item_key="fills", limit=200,
                min_ts=look_back, max_pages=10,
            ))
            for f in fills:
                if f.get("order_id") in orphan_oids:
                    fid = f.get("trade_id") or f.get("fill_id") or f.get("id")
                    if fid and fid not in mgr.state.processed_fill_ids:
                        mgr.state.processed_fill_ids.append(fid)
                        seeded += 1
        except Exception as exc:
            print(f"WARNING: could not seed processed_fill_ids: {exc}")

        for order in adopted:
            mgr.state.filled[order.intent_id] = order
        mgr._save()
        print(f"Adopted {len(adopted)} orphan orders into state.filled; "
              f"seeded {seeded} fill ids.")
        print("They have NO P&L yet; restart v14 and its reconcile_settlements "
              "will settle them once and book P&L.")
        print(f"Expect projected realized_pnl_total near ${projected_total:+.2f} "
              f"after restart"
              f"{'; the drawdown kill will arm.' if trips else '.'}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
