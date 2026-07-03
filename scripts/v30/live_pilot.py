"""v30 LIVE PILOT EXECUTOR (real money; charter research/v30/00-live-pilot-charter.md;
money-path review research/v30/01-money-path-review.md: all C/H/M findings fixed).

ARM A: locked dutch books, both legs IOC, uneven fills unwound and verified.
ARM B: RT envelope-bound decided side at cost <= 0.94, IOC, hold to settlement.
LIVE only when data/v30/LIVE_ARMED exists; data/v30/STOP halts; every order is
intent-logged BEFORE the POST, cost-accounted in cents, Discord-alerted. All price
math in INTEGER CENTS parsed from exact-cent quote strings (H2). Overlap lock (M1),
tolerant jsonl reads (M3), naked-leg retry at run start (C3).
self_trade_prevention_type "taker_at_cross" verified against v1's working body (M2).

Remove: Unregister-ScheduledTask -TaskName KalshiV30LivePilot
Run: .venv/Scripts/python.exe scripts/v30/live_pilot.py [--dry]
"""
from __future__ import annotations

import json
import math
import os
import sys
import time
import uuid
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, "src")
sys.path.insert(0, "scripts/v28")
sys.path.insert(0, "scripts/v29")

from kalshi_bot.config import Settings  # noqa: E402
from kalshi_bot.data.kalshi_client import KalshiClient  # noqa: E402

import live_rt_read as rt  # noqa: E402
import arb_sentinel as ab  # noqa: E402

ET = ZoneInfo("America/New_York")
V30 = os.path.join("data", "v30")
ORDERS = os.path.join(V30, "orders.jsonl")
LEDGER = os.path.join(V30, "positions.jsonl")
STOP = os.path.join(V30, "STOP")
ARMED = os.path.join(V30, "LIVE_ARMED")
LOCK = os.path.join(V30, "run.lock")
EXPIRY = date(2026, 9, 1)

ALLOC_FRAC = 0.25              # expansion addendum 2026-07-03 (was 0.15)
ARM_A_BASKET_CAP_C = 4000      # cents
ARM_A_DAILY_BASKETS = 2
ARM_B_FIRE_CAP_C = 3000
ARM_B_MAX_CONCURRENT = 3
ARM_B_MAX_COST_C = 94
DAILY_CAP_C = 12000            # expansion addendum (was 6000)
REST_MAX_ORDERS = 4            # arms C/D: max resting orders per arm
REST_MAX_NOTIONAL_C = 3000     # per resting order
REST_RT_MAX_BID_C = 95         # arm C price cap
REST_TSA_MAX_BID_C = 97        # arm D price cap


def now_et_date() -> str:
    return datetime.now(ET).date().isoformat()


def log(fp: str, row: dict) -> None:
    row["logged_utc"] = datetime.now(timezone.utc).isoformat()
    with open(fp, "a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def rows(fp: str):
    if not os.path.exists(fp):
        return []
    out = []
    with open(fp, encoding="utf-8") as f:
        for line in f:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # M3
    return out


def discord(msg: str) -> None:
    try:
        from kalshi_bot.alerts import discord as dc
        s = Settings()
        url = getattr(s, "discord_webhook_url", None)
        if url:
            dc.post(str(url), msg, username="v30 live pilot")
    except Exception:  # noqa: BLE001
        pass


def cents(x) -> int | None:
    try:
        return int(round(float(x) * 100))
    except (TypeError, ValueError):
        return None


def place_ioc(cli, ticker: str, buy_side: str, yes_cents: int, count: int,
              tag: str, cost_c: int, dry: bool) -> dict:
    """buy_side 'yes' -> V2 bid; 'no' -> V2 ask at YES-equivalent. cost_c = cents the
    buyer pays PER CONTRACT for their side (C1 accounting). Intent logged BEFORE the
    POST (C2); ambiguous failures logged reconcile_needed."""
    yes_cents = max(1, min(99, int(yes_cents)))
    body = {
        "ticker": ticker, "side": "bid" if buy_side == "yes" else "ask",
        "count": str(int(count)), "price": f"{yes_cents / 100:.2f}",
        "time_in_force": "immediate_or_cancel",
        "self_trade_prevention_type": "taker_at_cross",
        "client_order_id": "30" + uuid.uuid4().hex[:22],
    }
    intent = {"kind": "order_intent", "tag": tag, "body": body, "dry": dry,
              "cost_per_contract_c": cost_c, "et_date": now_et_date()}
    log(ORDERS, intent)
    if dry:
        return {"dry": True, "fill_count": 0}
    try:
        ack = cli.post("/portfolio/events/orders", json=body)
    except Exception as e:  # noqa: BLE001
        log(ORDERS, {"kind": "reconcile_needed", "tag": tag,
                     "client_order_id": body["client_order_id"],
                     "err": str(e)[:300], "et_date": now_et_date()})
        discord(f"v30 {tag} POST FAILED for {ticker}: reconcile_needed logged")
        return {"error": True, "fill_count": 0}
    log(ORDERS, {"kind": "order_ack", "tag": tag, "body": body, "ack": ack,
                 "cost_per_contract_c": cost_c, "et_date": now_et_date()})
    discord(f"v30 {tag}: {ticker} {buy_side} x{count} @ {yes_cents}c "
            f"-> filled {ack.get('fill_count')}")
    return ack


def fill_count(ack) -> int:
    try:
        return int(float(ack.get("fill_count") or 0))
    except (TypeError, ValueError):
        return 0


def spent_today_cents() -> int:
    tot = 0
    for r in rows(ORDERS):
        if (r.get("kind") == "order_ack" and r.get("et_date") == now_et_date()
                and r.get("tag") != "armA_unwind"):
            tot += fill_count(r.get("ack") or {}) * int(r.get("cost_per_contract_c") or 0)
    # CD3: resting fills discovered at reconcile enter the daily cap too
    for r in rows(LEDGER):
        if r.get("kind") == "rest_filled" and r.get("et_date") == now_et_date():
            tot += int(r.get("count") or 0) * int(r.get("bid_c") or 0)
    return tot


def unwind_leg(cli, ticker: str, held_side: str, count: int, dry: bool) -> int:
    """Exit a held position IOC at the current touch. Returns contracts EXITED (B1)."""
    try:
        mk = ab.get_json(f"{ab.BASE}/markets/{ticker}").get("market") or {}
    except Exception as e:  # noqa: BLE001
        log(ORDERS, {"kind": "error", "where": f"unwind_fetch:{ticker}",
                     "err": str(e)[:200], "et_date": now_et_date()})
        return 0
    if held_side == "yes":
        bid_c = cents(mk.get("yes_bid_dollars"))
        if not bid_c or bid_c < 1:
            return 0
        # sell YES = buy NO at NO-cost (100 - bid): yes-equivalent price = bid
        ack = place_ioc(cli, ticker, "no", bid_c, count, "armA_unwind",
                        100 - bid_c, dry)
    else:
        ask_c = cents(mk.get("yes_ask_dollars"))
        if not ask_c or ask_c > 99:
            return 0
        ack = place_ioc(cli, ticker, "yes", ask_c, count, "armA_unwind", ask_c, dry)
    return count if dry else min(count, fill_count(ack))


def retry_naked(cli, dry: bool) -> None:
    naked: dict[str, int] = {}
    side_of: dict[str, str] = {}
    for r in rows(LEDGER):
        if r.get("kind") == "armA_naked":
            naked[r["ticker"]] = naked.get(r["ticker"], 0) + int(r.get("count") or 0)
            side_of[r["ticker"]] = r["held_side"]
        elif r.get("kind") == "armA_naked_resolved":
            naked[r.get("ticker", "")] = naked.get(r.get("ticker", ""), 0) - int(r.get("count") or 0)
    for tk, remaining in naked.items():
        if remaining <= 0 or tk not in side_of:
            continue
        exited = unwind_leg(cli, tk, side_of[tk], remaining, dry)
        if exited > 0:
            log(LEDGER, {"kind": "armA_naked_resolved", "ticker": tk,
                         "count": exited, "et_date": now_et_date()})
            discord(f"v30 naked leg {tk}: exited {exited}, remaining {remaining - exited}")


def unresolved_reconciles() -> list[str]:
    """B2: client_order_ids with a reconcile_needed row and no reconcile_resolved."""
    pend: set[str] = set()
    for r in rows(ORDERS):
        if r.get("kind") == "reconcile_needed":
            pend.add(r.get("client_order_id") or "")
        elif r.get("kind") == "reconcile_resolved":
            pend.discard(r.get("client_order_id") or "")
    pend.discard("")
    return sorted(pend)


def arm_a(cli, bal_c: int, dry: bool) -> None:
    ackd = [r for r in rows(ORDERS) if r.get("kind") == "order_ack"
            and r.get("tag") == "armA_leg1" and r.get("et_date") == now_et_date()]
    if len(ackd) >= ARM_A_DAILY_BASKETS:
        return
    for ser in ab.CALM_SERIES:
        try:
            r = ab.get_json(f"{ab.BASE}/markets?series_ticker={ser}&status=open&limit=200")
        except Exception:  # noqa: BLE001
            continue
        byev = {}
        for m in r.get("markets") or []:
            byev.setdefault(m.get("event_ticker"), []).append(m)
        coeff = 0.035 if ser.startswith(("KXINX", "KXNASDAQ100")) else 0.07
        for ev, ems in byev.items():
            for a in ab.scan_event(ems, coeff):
                if a["edge"] < 0.02 or a["size"] < 1:
                    continue
                legs = []
                for leg in (a["leg1"], a["leg2"]):
                    side, rest = leg.split(" ", 1)
                    tk, px = rest.rsplit("@", 1)
                    c = cents(px)
                    if c is None or not (1 <= c <= 99):
                        legs = None
                        break
                    legs.append((side.lower(), tk, c))
                if not legs:
                    continue
                per_ct_c = sum(c for _, _, c in legs)
                cap_c = min(int(ALLOC_FRAC * bal_c), ARM_A_BASKET_CAP_C,
                            DAILY_CAP_C - spent_today_cents())
                n = int(min(a["size"], cap_c // max(per_ct_c, 1)))
                if n < 1:
                    continue
                log(ORDERS, {"kind": "armA_trigger", "series": ser, "event": ev,
                             "edge": a["edge"], "n": n, "arb": a,
                             "et_date": now_et_date()})
                acks = []
                for i, (bside, tk, c) in enumerate(legs):
                    yes_c = c if bside == "yes" else 100 - c
                    acks.append(place_ioc(cli, tk, bside, yes_c, n,
                                          f"armA_leg{i + 1}", c, dry))
                f1, f2 = fill_count(acks[0]), fill_count(acks[1])
                if any(a.get("error") for a in acks) and not dry:
                    # B2: an ambiguous leg means fills are UNKNOWN; do NOT auto-unwind
                    # the healthy leg against a possibly-filled errored leg. The
                    # unmatched reconcile_needed row already halts all future orders.
                    discord(f"v30 armA AMBIGUOUS LEG on {ev}: orders halted pending reconcile")
                elif f1 != f2 and not dry:
                    idx, excess = (0, f1 - f2) if f1 > f2 else (1, f2 - f1)
                    bside, tk, _ = legs[idx]
                    exited = unwind_leg(cli, tk, bside, excess, dry)
                    if exited < excess:
                        log(LEDGER, {"kind": "armA_naked", "ticker": tk,
                                     "held_side": bside, "count": excess - exited,
                                     "et_date": now_et_date()})
                        discord(f"v30 NAKED LEG {tk} x{excess - exited}: retry queued")
                if min(f1, f2) > 0:
                    log(LEDGER, {"kind": "armA_basket", "event": ev, "n": min(f1, f2),
                                 "edge": a["edge"], "et_date": now_et_date()})
                return  # one basket attempt per run


def arm_b(cli, bal_c: int, dry: bool) -> None:
    live_opens = [r for r in rows(LEDGER)
                  if r.get("kind") == "armB_open" and not r.get("dry")
                  and int(r.get("n") or 0) > 0]
    fired = {r["ticker"] for r in live_opens}
    # concurrency from REAL open positions in the ledger minus settled markets (H1)
    open_now = 0
    for r in live_opens:
        try:
            mk = ab.get_json(f"{ab.BASE}/markets/{r['ticker']}").get("market") or {}
            if mk.get("status") not in ("settled", "finalized"):
                open_now += 1
        except Exception:  # noqa: BLE001
            open_now += 1  # unknown counts as open (conservative)
    if open_now >= ARM_B_MAX_CONCURRENT:
        return
    try:
        mkts = ab.get_json(f"{ab.BASE}/markets?series_ticker=KXRT&status=open&limit=200")["markets"]
    except Exception:  # noqa: BLE001
        return
    byev = {}
    for m in mkts:
        byev.setdefault(m["event_ticker"], []).append(m)
    cache = json.load(open(rt.CACHE, encoding="utf-8")) if os.path.exists(rt.CACHE) else {}
    for ev, ms in sorted(byev.items()):
        slug = cache.get(ev)
        if slug is None:
            continue
        try:
            st = rt.parse_live(slug)
        except Exception:  # noqa: BLE001
            continue
        if st is None:
            continue
        s, n = st
        close = datetime.fromisoformat(ms[0]["close_time"].replace("Z", "+00:00"))
        hours_left = max(0.0, (close - datetime.now(timezone.utc)).total_seconds() / 3600.0)
        if n <= 0 or hours_left <= 0:
            continue
        d = min(14, max(1, math.ceil(hours_left / 24.0)))
        a_cap = max(rt.A_FLOOR, math.ceil(rt.CAP_MULT * rt.ENV_RATIO[d] * n),
                    math.ceil(rt.CAP_MULT * rt.arrivals_24h(ev, n) * hours_left / 24.0))
        lo_l, hi_l = rt.l_interval(s, n)
        low = 100.0 * lo_l / (n + a_cap)
        high = 100.0 * (hi_l + a_cap) / (n + a_cap)
        for m in ms:
            if m.get("floor_strike") is None or m.get("strike_type") != "greater":
                continue
            if m["ticker"] in fired:
                continue
            k = float(m["floor_strike"])
            ask_c = cents(m.get("yes_ask_dollars"))
            bid_c = cents(m.get("yes_bid_dollars"))
            side = cost_c = size = None
            if (low > k + rt.READ_MARGIN and ask_c and 1 <= ask_c <= ARM_B_MAX_COST_C):
                side, cost_c = "yes", ask_c
                size = ab.fnum(m.get("yes_ask_size_fp")) or 0.0
            elif (high < k - rt.READ_MARGIN and bid_c and bid_c >= 100 - ARM_B_MAX_COST_C
                  and bid_c <= 99):
                side, cost_c = "no", 100 - bid_c
                size = ab.fnum(m.get("yes_bid_size_fp")) or 0.0
            if side is None:
                continue
            cap_c = min(int(ALLOC_FRAC * bal_c), ARM_B_FIRE_CAP_C,
                        DAILY_CAP_C - spent_today_cents())
            nct = int(min(size, cap_c // max(cost_c, 1)))
            if nct < 1:
                continue
            log(ORDERS, {"kind": "armB_trigger", "ticker": m["ticker"], "side": side,
                         "score": s, "count": n, "a_cap": a_cap, "low": round(low, 2),
                         "high": round(high, 2), "strike": k, "cost_c": cost_c,
                         "n": nct, "et_date": now_et_date()})
            yes_c = cost_c if side == "yes" else 100 - cost_c
            ack = place_ioc(cli, m["ticker"], side, yes_c, nct, "armB", cost_c, dry)
            got = fill_count(ack)
            if got > 0:
                log(LEDGER, {"kind": "armB_open", "ticker": m["ticker"], "side": side,
                             "cost_c": cost_c, "n": got, "dry": dry,
                             "et_date": now_et_date()})
            return  # one fire attempt per run


def rt_decided_strikes():
    """(market, side, bid_c, ask_c) for KXRT strikes decided by the live envelope
    bound. Returns None if the FEED is down (CD4: caller must then skip
    bound-weakening cancels), [] if feeds are up and nothing is decided."""
    out = []
    try:
        mkts = ab.get_json(f"{ab.BASE}/markets?series_ticker=KXRT&status=open&limit=200")["markets"]
    except Exception:  # noqa: BLE001
        return None
    feed_ok = False
    byev = {}
    for m in mkts:
        byev.setdefault(m["event_ticker"], []).append(m)
    cache = json.load(open(rt.CACHE, encoding="utf-8")) if os.path.exists(rt.CACHE) else {}
    for ev, ms in sorted(byev.items()):
        slug = cache.get(ev)
        if slug is None:
            continue
        try:
            st = rt.parse_live(slug)
        except Exception:  # noqa: BLE001
            continue
        if st is None:
            continue
        feed_ok = True
        s, n = st
        close = datetime.fromisoformat(ms[0]["close_time"].replace("Z", "+00:00"))
        hours_left = max(0.0, (close - datetime.now(timezone.utc)).total_seconds() / 3600.0)
        if n <= 0 or hours_left <= 0:
            continue
        d = min(14, max(1, math.ceil(hours_left / 24.0)))
        a_cap = max(rt.A_FLOOR, math.ceil(rt.CAP_MULT * rt.ENV_RATIO[d] * n),
                    math.ceil(rt.CAP_MULT * rt.arrivals_24h(ev, n) * hours_left / 24.0))
        lo_l, hi_l = rt.l_interval(s, n)
        low = 100.0 * lo_l / (n + a_cap)
        high = 100.0 * (hi_l + a_cap) / (n + a_cap)
        for m in ms:
            if m.get("floor_strike") is None or m.get("strike_type") != "greater":
                continue
            k = float(m["floor_strike"])
            if low > k + rt.READ_MARGIN:
                side = "yes"
            elif high < k - rt.READ_MARGIN:
                side = "no"
            else:
                continue
            out.append((m, side, cents(m.get("yes_bid_dollars")) or 0,
                        cents(m.get("yes_ask_dollars")) or 100))
    return out if feed_ok else None


def tsa_decided_strikes():
    """(market, side, bid_c, ask_c) for KXTSAW strikes decided by the v26 bound.
    None = feed down (CD4); [] = nothing decided."""
    out = []
    sys.path.insert(0, "scripts/v26")
    try:
        import live_certainty_monitor as cm
        live = cm.tsa_page_values()
        if not live:
            return None
        hist = {date.fromisoformat(k): v for k, v in json.load(
            open(os.path.join("data", "v26", "tsa_daily.json"), encoding="utf-8")).items()}
        hist.update(live)
        mkts = ab.get_json(f"{ab.BASE}/markets?series_ticker=KXTSAW&status=open&limit=200")["markets"]
    except Exception:  # noqa: BLE001
        return None
    from datetime import timedelta
    for m in mkts:
        k = m.get("floor_strike")
        if k is None or m.get("strike_type") != "greater":
            continue
        k = float(k)
        if k <= 1000:
            k *= 1_000_000.0
        close_utc = datetime.strptime(m["close_time"][:10], "%Y-%m-%d").date()
        sunday = close_utc - timedelta(days=1)
        days = [sunday - timedelta(days=i) for i in range(6, -1, -1)]
        pub = [live[dd] for dd in days if dd in live]
        unpub = [dd for dd in days if dd not in live]
        los, his = [], []
        ok = bool(pub)
        for dd in unpub:
            same = [v for h, v in hist.items()
                    if h.weekday() == dd.weekday() and 0 < (dd - h).days <= 730]
            if len(same) < 20:
                ok = False
                break
            los.append(min(same) * 0.85)
            his.append(max(same) * 1.15)
        if not ok:
            continue
        lo_avg = (sum(pub) + sum(los)) / 7.0
        hi_avg = (sum(pub) + sum(his)) / 7.0
        # 0.5 percent revision tolerance on the published component (the documented
        # TSA revision hazard; prevents near-boundary fires like a bare lo_avg > k)
        if lo_avg * 0.995 > k:
            side = "yes"
        elif hi_avg * 1.005 < k:
            side = "no"
        else:
            continue
        out.append((m, side, cents(m.get("yes_bid_dollars")) or 0,
                    cents(m.get("yes_ask_dollars")) or 100))
    return out


def rest_rows():
    open_by_coid = {}
    for r in rows(LEDGER):
        if r.get("kind") == "rest_open":
            open_by_coid[r["client_order_id"]] = r
        elif r.get("kind") in ("rest_closed", "rest_filled"):
            open_by_coid.pop(r.get("client_order_id"), None)
    return open_by_coid


def reconcile_and_place_rests(cli, arm: str, decided, max_bid_c: int,
                              bal_c: int, dry: bool) -> None:
    """Arms C/D: cancel bids whose bound broke; place new bids on decided strikes.
    decided is None when the FEED is down (CD4): fill detection still runs, but no
    bound-weakening cancels and no new placements."""
    feed_down = decided is None
    decided_by_tk = {} if feed_down else {
        m["ticker"]: (side, bid_c, ask_c) for m, side, bid_c, ask_c in decided}
    tracked = {c: r for c, r in rest_rows().items() if r.get("arm") == arm}
    for coid, r in tracked.items():
        tk = r["ticker"]
        n0 = int(r.get("n") or 0)
        still = decided_by_tk.get(tk)
        bound_ok = feed_down or (still is not None and still[0] == r["side"])
        try:
            lst = cli.get("/portfolio/orders", ticker=tk)
            mine = next((o for o in (lst.get("orders") or [])
                         if o.get("client_order_id") == coid), None)
        except Exception as e:  # noqa: BLE001
            log(ORDERS, {"kind": "error", "where": f"rest_lookup:{tk}",
                         "err": str(e)[:200], "et_date": now_et_date()})
            continue
        # probe-verified listing schema (2026-07-03): status lowercase incl.
        # "resting"; counts are *_fp strings (remaining_count_fp, fill_count_fp)
        status = str((mine or {}).get("status", "gone")).lower()

        def fpint(obj, *keys):
            for kk in keys:
                v = obj.get(kk) if obj else None
                if v is not None:
                    try:
                        return int(float(v))
                    except (TypeError, ValueError):
                        continue
            return None

        rem = fpint(mine, "remaining_count_fp", "remaining_count")
        fil = fpint(mine, "fill_count_fp", "fill_count")
        if mine is not None and (status in ("filled", "executed") or rem == 0):
            filled = fil if fil is not None else (n0 if rem is None else max(0, n0 - rem))
            log(LEDGER, {"kind": "rest_filled", "client_order_id": coid, "ticker": tk,
                         "arm": arm, "count": filled, "bid_c": r["bid_c"],
                         "et_date": now_et_date()})
            discord(f"v30 {arm} RESTING FILLED: {tk} {r['side']} x{filled} @ {r['bid_c']}c")
            continue
        if mine is None:
            # listing lags ~6s after create (probe-verified); grace-period young rows
            try:
                age_s = (datetime.now(timezone.utc) - datetime.fromisoformat(
                    r.get("logged_utc", ""))).total_seconds()
            except (ValueError, TypeError):
                age_s = 1e9
            if age_s < 20 * 60:
                continue  # keep tracking; re-check next run
            log(LEDGER, {"kind": "rest_closed", "client_order_id": coid, "ticker": tk,
                         "arm": arm, "reason": "gone", "count_unknown": True,
                         "n": n0, "bid_c": r["bid_c"], "et_date": now_et_date()})
            discord(f"v30 {arm} rest GONE (fills unknown, review): {tk}")
            continue
        if not bound_ok and not dry:  # CD5: no live mutations in dry mode
            try:
                ackd = cli.delete(f"/portfolio/events/orders/{mine.get('order_id')}")
                reduced = None
                try:
                    reduced = int(float(ackd.get("reduced_by")))
                except (TypeError, ValueError, AttributeError):
                    pass
                filled_before_cancel = (n0 - reduced) if reduced is not None else None
                log(LEDGER, {"kind": "rest_closed", "client_order_id": coid,
                             "ticker": tk, "arm": arm, "reason": "bound_weakened",
                             "count": filled_before_cancel, "bid_c": r["bid_c"],
                             "n": n0, "et_date": now_et_date()})
                if filled_before_cancel:
                    log(LEDGER, {"kind": "rest_filled", "client_order_id": coid,
                                 "ticker": tk, "arm": arm,
                                 "count": filled_before_cancel, "bid_c": r["bid_c"],
                                 "note": "filled_then_cancelled",
                                 "et_date": now_et_date()})
                    discord(f"v30 {arm} FILLED-THEN-CANCELLED {tk} "
                            f"x{filled_before_cancel} (bound broke): REVIEW")
                else:
                    discord(f"v30 {arm} CANCELLED (bound weakened): {tk}")
            except Exception as e:  # noqa: BLE001
                log(ORDERS, {"kind": "error", "where": f"rest_cancel:{tk}",
                             "err": str(e)[:200], "et_date": now_et_date()})
    if feed_down:
        return  # no placements on a down feed; dry placements continue (intent-only)
    # place new
    tracked = {c: r for c, r in rest_rows().items() if r.get("arm") == arm}
    have_tk = {r["ticker"] for r in tracked.values()}
    if len(tracked) >= REST_MAX_ORDERS:
        return
    armb_tickers = {r["ticker"] for r in rows(LEDGER)
                    if r.get("kind") == "armB_open" and not r.get("dry")}
    for m, side, bid_c, ask_c in decided:
        tk = m["ticker"]
        if tk in have_tk or tk in armb_tickers:  # no same-ticker stacking with arm B
            continue
        # our bid on the DECIDED side, priced inside the spread, capped
        if side == "yes":
            cost_c = min(max_bid_c, max(bid_c + 1, 1), max(ask_c - 1, 1))
            if cost_c > max_bid_c or cost_c >= ask_c:
                continue
            yes_c = cost_c
        else:
            no_bid_c = 100 - ask_c          # best NO bid = 100 - yes ask
            no_ask_c = 100 - bid_c
            cost_c = min(max_bid_c, max(no_bid_c + 1, 1), max(no_ask_c - 1, 1))
            if cost_c > max_bid_c or cost_c >= no_ask_c:
                continue
            yes_c = 100 - cost_c
        resting_notional_c = sum(int(r.get("bid_c") or 0) * int(r.get("n") or 0)
                                 for r in tracked.values())
        cap_c = min(int(ALLOC_FRAC * bal_c) - resting_notional_c, REST_MAX_NOTIONAL_C,
                    DAILY_CAP_C - spent_today_cents())
        n = cap_c // max(cost_c, 1)
        if n < 1:
            continue
        n = min(n, 25)
        body = {
            "ticker": tk, "side": "bid" if side == "yes" else "ask",
            "count": str(int(n)), "price": f"{yes_c / 100:.2f}",
            "time_in_force": "good_till_canceled",
            "self_trade_prevention_type": "taker_at_cross",
            "client_order_id": "30" + uuid.uuid4().hex[:22],
        }
        log(ORDERS, {"kind": "order_intent", "tag": f"{arm}_rest", "body": body,
                     "dry": dry, "cost_per_contract_c": cost_c,
                     "et_date": now_et_date()})
        if dry:
            continue
        try:
            ack = cli.post("/portfolio/events/orders", json=body)
        except Exception as e:  # noqa: BLE001
            log(ORDERS, {"kind": "reconcile_needed", "tag": f"{arm}_rest",
                         "client_order_id": body["client_order_id"],
                         "err": str(e)[:300], "et_date": now_et_date()})
            discord(f"v30 {arm} REST POST FAILED {tk}: reconcile_needed")
            return
        log(ORDERS, {"kind": "order_ack", "tag": f"{arm}_rest", "body": body,
                     "ack": ack, "cost_per_contract_c": cost_c,
                     "et_date": now_et_date()})
        log(LEDGER, {"kind": "rest_open", "client_order_id": body["client_order_id"],
                     "order_id": ack.get("order_id"), "ticker": tk, "arm": arm,
                     "side": side, "bid_c": cost_c, "n": n, "et_date": now_et_date()})
        discord(f"v30 {arm} RESTING: {tk} {side} bid {cost_c}c x{n}")
        return  # one new rest per arm per run


def main() -> int:
    if date.today() > EXPIRY:
        return 0
    os.makedirs(V30, exist_ok=True)
    if os.path.exists(STOP):
        return 0
    # M1 overlap lock
    if os.path.exists(LOCK):
        try:
            age = time.time() - float(open(LOCK, encoding="utf-8").read().strip())
        except (ValueError, OSError):
            age = 1e9
        if age < 9 * 60:
            return 0
    with open(LOCK, "w", encoding="utf-8") as f:
        f.write(str(time.time()))
    try:
        dry = ("--dry" in sys.argv) or not os.path.exists(ARMED)
        spent_c = spent_today_cents()
        if spent_c >= DAILY_CAP_C:
            log(ORDERS, {"kind": "cap_halt", "spent_c": spent_c, "et_date": now_et_date()})
            return 0
        s = Settings()
        with KalshiClient(s) as cli:
            try:
                bal_c = int(float(cli.get("/portfolio/balance").get("balance") or 0))
            except Exception as e:  # noqa: BLE001
                log(ORDERS, {"kind": "error", "where": "balance", "err": str(e)[:200],
                             "et_date": now_et_date()})
                return 0
            log(ORDERS, {"kind": "heartbeat", "balance_c": bal_c, "dry": dry,
                         "spent_c": spent_c, "et_date": now_et_date()})
            pend = unresolved_reconciles()
            if pend:
                # B2 fail-closed: no new orders while any ambiguous order is unresolved
                log(ORDERS, {"kind": "reconcile_halt", "pending": pend,
                             "et_date": now_et_date()})
                discord(f"v30 HALTED: {len(pend)} unresolved reconcile(s); "
                        "resolve and append reconcile_resolved rows to resume")
                return 0
            if not dry:
                retry_naked(cli, dry)
            # addendum global cap: committed exposure must stay under 90 pct of balance
            committed_c = 0
            for r in rows(LEDGER):
                if r.get("kind") == "armB_open" and not r.get("dry"):
                    committed_c += int(r.get("cost_c") or 0) * int(r.get("n") or 0)
            for r in rest_rows().values():
                committed_c += int(r.get("bid_c") or 0) * int(r.get("n") or 0)
            if committed_c > int(0.9 * bal_c):
                log(ORDERS, {"kind": "global_cap_halt", "committed_c": committed_c,
                             "balance_c": bal_c, "et_date": now_et_date()})
            else:
                arm_a(cli, bal_c, dry)
                arm_b(cli, bal_c, dry)
                # arms C/D (expansion addendum): maker bids on decided outcomes
                rt_dec = rt_decided_strikes()
                reconcile_and_place_rests(cli, "armC", rt_dec, REST_RT_MAX_BID_C, bal_c, dry)
                tsa_dec = tsa_decided_strikes()
                reconcile_and_place_rests(cli, "armD", tsa_dec, REST_TSA_MAX_BID_C, bal_c, dry)
    finally:
        try:
            os.remove(LOCK)
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
