"""v21 Candidate C Phase C0: zero-build ladder monotonicity spot-scan.

Implements research/v21/00-methodology-lock.md section 3.3 exactly. READ-ONLY:
this script NEVER places orders. It scans live open Kalshi markets for
cumulative-ladder monotonicity locks and appends one JSON line per run to
research/v21/c0_scan_log.jsonl.

Ladder identification (locked, structured fields ONLY):
- legs grouped by (event_ticker, ticker family = ticker.rsplit('-', 1)[0],
  alpha prefix of the strike token); the family sub-key prevents
  cross-underlier false pairs when one event carries two different ladders
  (code review H-1), and the strike-token alpha prefix separates
  TEAM-CODED ladders that share a family: day-1 probe found spread markets
  like KXWNBASPREAD-...-CHI6 vs -IND9, where 'CHI wins by >6' and 'IND wins
  by >9' are near-mutually-exclusive, NOT nested; 14 of 15 probe 'locks'
  were this false pattern. 'CHI6'->'CHI' and 'IND9'->'IND' split; 'T6.75'
  and 'T7.00' share 'T' and stay one ladder. Ticker structure only, never
  subtitle text.
- strike_type must be in {greater, greater_or_equal}; range brackets
  (between), less-type, custom/functional, missing floor_strike, and any
  leg with a non-None cap_strike are hard-excluded (methodology critic C-3:
  range families are mutually exclusive, NOT nested; misreading them
  manufactures phantom locks)
- all legs in a ladder must share ONE strike_type (mixing > and >= breaks
  the nesting order for integer underlyings); ordered by floor_strike;
  ladders with duplicate floor_strikes are skipped as ambiguous

G-C0 distinctness is bucketed on the PACIFIC calendar date (scan_date_pt in
the record), not the UTC date: the 20:00 PT scan lands on the next UTC day
and would otherwise double-count one persistent evening lock.

The lock on a violation: buy YES(lower strike) at yes_ask and NO(higher
strike) at no_ask. Every outcome pays >= $1; cost = yes_ask_lo + no_ask_hi;
gross margin = 1 - cost; net = gross - 2 taker fees. Net is evaluated in
INTEGER CENTS (>= 1 cent): the day-1 probe 'confirmed' a basket on a 2e-18
floating-point residue of an economically-zero margin. A candidate (net >=
1c from the paginated sweep) only COUNTS toward G-C0 after a back-to-back
orderbook confirm read on BOTH legs (anti-F4: paginated quotes are
non-simultaneous) with net >= 1c and bindable depth >= 1 on both legs at
the orderbook prices.

G-C0 (build gate): >= 3 DISTINCT confirmed locks across 21 scheduled scans
(09:00/14:00/20:00 PT x 7 days). Distinct = one count per (event, lower leg,
higher leg) per calendar day, computed at analysis time from the log.

Run kinds: --scheduled tags a run as one of the 21 gate scans; default is
"probe" (field verification / smoke), excluded from G-C0 counting.

Run (Windows):
  & "C:\\Users\\SamJD\\OneDrive\\Desktop\\AI Projects\\Project Kalshi\\.venv-kronos\\Scripts\\python.exe" "C:\\Users\\SamJD\\OneDrive\\Desktop\\AI Projects\\Project Kalshi\\scripts\\v21\\c0_ladder_spotscan.py" [--scheduled]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

BASE = Path(r"C:/Users/SamJD/OneDrive/Desktop/AI Projects/Project Kalshi")
sys.path.insert(0, str(BASE / "src"))
os.chdir(BASE)  # Settings() reads .env from the project root

from kalshi_bot.analysis.dutchbook import annualized_return, parse_market_quote  # noqa: E402
from kalshi_bot.analysis.metrics import kalshi_taker_fee_per_contract  # noqa: E402
from kalshi_bot.config import Settings  # noqa: E402
from kalshi_bot.data.kalshi_client import KalshiClient  # noqa: E402

LOG_PATH = BASE / "research" / "v21" / "c0_scan_log.jsonl"
STRIKE_WHITELIST = {"greater", "greater_or_equal"}
FIELD_CHECK = [
    "strike_type", "floor_strike", "cap_strike", "yes_bid_dollars",
    "yes_ask_dollars", "no_ask_dollars", "yes_ask_size_fp", "no_ask_size_fp",
]


def best_exec_from_orderbook(payload: dict) -> dict:
    """Executable taker prices + depth from one /markets/{t}/orderbook payload.

    Kalshi's book is unified: the YES ask is made by the best NO bid
    (yes_ask = 1 - best_no_bid, depth = that bid's size) and vice versa.
    Returns dollars; None price when the needed side is empty.
    """
    ob = payload.get("orderbook_fp", {}) or {}
    yes_levels = ob.get("yes_dollars", []) or []
    no_levels = ob.get("no_dollars", []) or []
    out: dict = {"yes_ask": None, "yes_ask_depth": 0.0, "no_ask": None, "no_ask_depth": 0.0}
    if no_levels:
        p, sz = max(no_levels, key=lambda lv: float(lv[0]))
        out["yes_ask"] = 1.0 - float(p)
        out["yes_ask_depth"] = float(sz)
    if yes_levels:
        p, sz = max(yes_levels, key=lambda lv: float(lv[0]))
        out["no_ask"] = 1.0 - float(p)
        out["no_ask_depth"] = float(sz)
    # Hard sanity bound (review M-1): a units/shape surprise must yield a
    # missing side (confirmed=False), never a fake hugely-positive lock.
    for side in ("yes_ask", "no_ask"):
        if out[side] is not None and not (0.0 < out[side] < 1.0):
            out[side] = None
    return out


def pair_net(yes_ask_lo: float, no_ask_hi: float) -> tuple[float, float, int]:
    """(gross, net, net_cents) margin for one lock basket.

    net_cents is the decision value: real money is cent-quantized, and the
    float residue of e.g. 0.02 - 0.01 - 0.01 is 2e-18, which must not pass
    a `> 0` gate (day-1 probe finding).
    """
    cost = yes_ask_lo + no_ask_hi
    gross = 1.0 - cost
    net = gross - kalshi_taker_fee_per_contract(yes_ask_lo) - kalshi_taker_fee_per_contract(no_ask_hi)
    return gross, net, int(round(net * 100))


def strike_alpha_prefix(ticker: str) -> str:
    """Leading non-digit characters of the strike token (last dash segment).

    'KXWNBASPREAD-26JUN11CHIIND-CHI6' -> 'CHI'; '...-T6.75' -> 'T'. Different
    prefixes within one family are different underliers (e.g. each team's
    margin), which are NOT nested against each other."""
    token = ticker.rsplit("-", 1)[-1]
    out = []
    for ch in token:
        if ch.isdigit() or ch == ".":
            break
        out.append(ch)
    return "".join(out)


def days_to_close(m: dict, now: datetime) -> float | None:
    ct = m.get("close_time")
    if not ct:
        return None
    try:
        dt = datetime.fromisoformat(str(ct).replace("Z", "+00:00"))
    except ValueError:
        return None
    return max((dt - now).total_seconds() / 86400.0, 0.0)


def run_scan(run_kind: str) -> dict:
    """One full scan attempt. Raises on network failure; the caller retries
    within the slot window (lock v3.2: wifi-loss resilience)."""
    now = datetime.now(timezone.utc)

    settings = Settings()
    with KalshiClient(settings) as kc:
        markets = list(kc.paginate("/markets", item_key="markets", limit=1000, status="open"))

        # Day-1 field verification (lock 3.3): which structured fields the live
        # payload actually carries. Logged on every run for free.
        field_counts = {f: sum(1 for m in markets if m.get(f) not in (None, "")) for f in FIELD_CHECK}
        strike_type_values: dict[str, int] = {}
        for m in markets:
            st = str(m.get("strike_type") or "")
            strike_type_values[st] = strike_type_values.get(st, 0) + 1

        # Ladder identification, structured fields only. Sub-key by ticker
        # family (review H-1): one event can carry TWO different ladders on
        # different underliers; a cross-underlier "adjacent pair" is NOT
        # nested and would be a false lock. True ladder legs share the
        # ticker prefix and differ only in the strike segment.
        by_ladder: dict[tuple[str, str, str], list[dict]] = {}
        for m in markets:
            st = m.get("strike_type")
            if st not in STRIKE_WHITELIST or m.get("floor_strike") is None:
                continue
            if m.get("cap_strike") is not None:
                continue  # range leg in disguise; never nested
            ev = m.get("event_ticker", "")
            ticker = str(m.get("ticker", ""))
            family = ticker.rsplit("-", 1)[0]
            underlier = strike_alpha_prefix(ticker)
            by_ladder.setdefault((ev, family, underlier), []).append(m)

        families_per_event: dict[str, set[str]] = {}
        underliers_per_family: dict[tuple[str, str], set[str]] = {}
        for (ev, family, underlier) in by_ladder:
            families_per_event.setdefault(ev, set()).add(family)
            underliers_per_family.setdefault((ev, family), set()).add(underlier)
        n_events_split_multi_prefix = sum(1 for fams in families_per_event.values() if len(fams) > 1)
        n_families_split_multi_underlier = sum(1 for us in underliers_per_family.values() if len(us) > 1)

        n_ladders = 0
        n_pairs = 0
        n_skipped_mixed = 0
        n_skipped_dup = 0
        candidates = []
        best_net = None  # near-miss tracking for the NULL write-up
        for (ev, family, underlier), legs in by_ladder.items():
            if not ev or len(legs) < 2:
                continue
            if len({leg["strike_type"] for leg in legs}) != 1:
                n_skipped_mixed += 1
                continue
            try:
                legs = sorted(legs, key=lambda x: float(x["floor_strike"]))
            except (TypeError, ValueError):
                continue
            strikes = [float(x["floor_strike"]) for x in legs]
            if len(set(strikes)) != len(strikes):
                n_skipped_dup += 1
                continue
            n_ladders += 1
            for lo, hi in zip(legs, legs[1:]):
                n_pairs += 1
                q_lo = parse_market_quote(lo)
                q_hi = parse_market_quote(hi)
                if q_lo["yes_ask"] is None or q_hi["no_ask"] is None:
                    continue
                gross, net, net_cents = pair_net(q_lo["yes_ask"], q_hi["no_ask"])
                if best_net is None or net > best_net:
                    best_net = net
                if net_cents < 1:
                    continue
                candidates.append({
                    "event": ev,
                    "family": family,
                    "underlier": underlier,
                    "ticker_lo": lo["ticker"],
                    "ticker_hi": hi["ticker"],
                    "strike_lo": float(lo["floor_strike"]),
                    "strike_hi": float(hi["floor_strike"]),
                    "sweep_yes_ask_lo": q_lo["yes_ask"],
                    "sweep_no_ask_hi": q_hi["no_ask"],
                    "sweep_gross": round(gross, 4),
                    "sweep_net": round(net, 4),
                })

        # Confirm read (anti-F4): back-to-back orderbook pulls on both legs of
        # every sweep candidate; only confirmed locks count toward G-C0.
        confirmed = []
        for c in candidates:
            # Review M-2: a confirm-read failure on one candidate must not
            # lose the whole run record (only 21 gate scans exist).
            try:
                ob_lo = best_exec_from_orderbook(kc.get(f"/markets/{c['ticker_lo']}/orderbook"))
                ob_hi = best_exec_from_orderbook(kc.get(f"/markets/{c['ticker_hi']}/orderbook"))
            except Exception as exc:
                c["confirmed"] = False
                c["confirm_error"] = repr(exc)
                continue
            c["confirm"] = {
                "yes_ask_lo": ob_lo["yes_ask"], "yes_ask_lo_depth": ob_lo["yes_ask_depth"],
                "no_ask_hi": ob_hi["no_ask"], "no_ask_hi_depth": ob_hi["no_ask_depth"],
            }
            if ob_lo["yes_ask"] is None or ob_hi["no_ask"] is None:
                c["confirmed"] = False
                continue
            gross, net, net_cents = pair_net(ob_lo["yes_ask"], ob_hi["no_ask"])
            c["confirm"]["gross"] = round(gross, 4)
            c["confirm"]["net"] = round(net, 4)
            c["confirm"]["net_cents"] = net_cents
            ok = net_cents >= 1 and ob_lo["yes_ask_depth"] >= 1 and ob_hi["no_ask_depth"] >= 1
            c["confirmed"] = bool(ok)
            if ok:
                lo_m = next(m for m in markets if m["ticker"] == c["ticker_lo"])
                hi_m = next(m for m in markets if m["ticker"] == c["ticker_hi"])
                dtc = [d for d in (days_to_close(lo_m, now), days_to_close(hi_m, now)) if d is not None]
                cost = ob_lo["yes_ask"] + ob_hi["no_ask"]
                c["annualized_diag"] = annualized_return(net, cost, max(dtc)) if dtc else None
                confirmed.append(c)

    record = {
        "ts_utc": now.isoformat(),
        "scan_date_pt": now.astimezone(ZoneInfo("America/Los_Angeles")).date().isoformat(),
        "run_kind": run_kind,
        "n_open_markets": len(markets),
        "field_counts": field_counts,
        "strike_type_values": strike_type_values,
        "n_ladders": n_ladders,
        "n_events_split_multi_prefix": n_events_split_multi_prefix,
        "n_families_split_multi_underlier": n_families_split_multi_underlier,
        "n_adjacent_pairs": n_pairs,
        "n_skipped_mixed_strike_type": n_skipped_mixed,
        "n_skipped_duplicate_strikes": n_skipped_dup,
        "best_net_margin_observed": round(best_net, 4) if best_net is not None else None,
        "n_sweep_candidates": len(candidates),
        "n_confirmed_locks": len(confirmed),
        "candidates": candidates,
    }
    if markets and field_counts.get("yes_ask_dollars", 0) == 0:
        print("[c0] WARNING: yes_ask_dollars absent from ALL open markets; "
              "every pair was skipped. The payload schema changed; the scan is blind.")
    print(f"[c0 {run_kind}] {len(markets):,} open markets | {n_ladders} ladders "
          f"({n_events_split_multi_prefix} multi-family events, "
          f"{n_families_split_multi_underlier} multi-underlier families) | "
          f"{n_pairs} adjacent pairs | best net {record['best_net_margin_observed']} | "
          f"{len(candidates)} sweep candidates | {len(confirmed)} CONFIRMED locks")
    for c in confirmed:
        print(f"  CONFIRMED {c['event']}: {c['ticker_lo']} / {c['ticker_hi']} "
              f"net=${c['confirm']['net']:.4f}")
    return record


def append_record(record: dict) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record) + "\n"
    for attempt in range(3):  # review L-3: OneDrive can hold transient locks
        try:
            with open(LOG_PATH, "a", encoding="utf-8") as f:
                f.write(line)
            return
        except PermissionError:
            if attempt == 2:
                raise
            time.sleep(1.0)


# Lock v3.2 wifi resilience: keep retrying transient network failures for up
# to 30 minutes within the slot (worst case 30 min retry + ~25 min scan fits
# the task's 60-minute execution limit), then log an explicit FAILURE record
# so coverage accounting sees the missed slot. Failure records never count
# toward the 21-scan budget (the evaluator skips status=failed).
RETRY_WINDOW_SECONDS = 1800
RETRY_SLEEP_SECONDS = 120


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scheduled", action="store_true",
                    help="tag this run as one of the 21 pre-registered G-C0 scans")
    args = ap.parse_args()
    run_kind = "scheduled" if args.scheduled else "probe"

    deadline = time.monotonic() + RETRY_WINDOW_SECONDS
    attempt = 0
    while True:
        attempt += 1
        try:
            record = run_scan(run_kind)
            break
        except Exception as exc:
            if time.monotonic() >= deadline:
                now = datetime.now(timezone.utc)
                record = {
                    "ts_utc": now.isoformat(),
                    "scan_date_pt": now.astimezone(ZoneInfo("America/Los_Angeles")).date().isoformat(),
                    "run_kind": run_kind,
                    "status": "failed",
                    "attempts": attempt,
                    "error": repr(exc),
                }
                print(f"[c0 {run_kind}] FAILED after {attempt} attempts: {exc!r}")
                break
            print(f"[c0 {run_kind}] attempt {attempt} failed ({exc!r}); "
                  f"retrying in {RETRY_SLEEP_SECONDS}s")
            time.sleep(RETRY_SLEEP_SECONDS)

    append_record(record)
    print(f"[c0] appended to {LOG_PATH}")


if __name__ == "__main__":
    main()
