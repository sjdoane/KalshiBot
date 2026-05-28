"""V10-A round 15b: analyze v1's live trades for fill rate + adverse selection.

For each filled order in v1's state.json:
- Compute fill timing (place_ts to fill_ts)
- Pull CURRENT live orderbook mid for the ticker (if still open)
- Compare fill_price to current mid: if mid < fill_price for YES buy, that's
  adverse selection (we filled high, market moved down)
- Tag by prefix and check against the persistent vs OOS-NULL prefix list

For closed (cancelled) orders, compute how long they waited before cancel.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from live_universe_probe import get
from live_spread_probe import parse_orderbook

REPO = Path(__file__).resolve().parents[2]
STATE = REPO / "data" / "live_trades" / "state.json"

PERSIST_PREFIXES = {"KXMLBGAME", "KXATPMATCH", "KXNFLGAME", "KXNCAAFGAME", "KXWTAMATCH"}
DENYLIST_PREFIXES = {
    "KXNFLSPREAD", "KXNFLTOTAL", "KXMLBSPREAD", "KXMLBTOTAL",
    "KXNHLSPREAD", "KXNCAAFSPREAD", "KXNCAAFTOTAL",
    "KXNCAAMBTOTAL", "KXNCAAMBSPREAD", "KXEPLGAME", "KXUCLGAME",
    "KXMLBWINS", "KXNFLWINS", "KXNFLPLAYOFF", "KXMLBPLAYOFFS",
}


def prefix_of(ticker: str) -> str:
    return ticker.split("-")[0] if "-" in ticker else ticker


def parse_ts(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def main():
    state = json.load(open(STATE))
    filled = state["filled"]
    closed = state["closed"]
    resting = state["resting"]

    print(f"V1 live analysis @ {datetime.now(timezone.utc).isoformat()}")
    print(f"Starting bankroll: ${state['starting_bankroll_usd']:.2f}")
    print(f"Realized P&L: ${state['realized_pnl_total_usd']:.2f}")
    print(f"Counts: intents={len(state['intents'])}, resting={len(resting)}, filled={len(filled)}, closed={len(closed)}")
    print()

    # Prefix distribution of filled and resting
    print("=" * 90)
    print("PREFIX DISTRIBUTION (filled and resting)")
    print("=" * 90)
    filled_by_prefix = defaultdict(int)
    resting_by_prefix = defaultdict(int)
    closed_by_prefix = defaultdict(int)
    for v in filled.values():
        filled_by_prefix[prefix_of(v["ticker"])] += 1
    for v in resting.values():
        resting_by_prefix[prefix_of(v["ticker"])] += 1
    for v in closed.values():
        closed_by_prefix[prefix_of(v["ticker"])] += 1
    all_prefixes = sorted(set(filled_by_prefix) | set(resting_by_prefix) | set(closed_by_prefix))
    print(f"{'prefix':32}  {'filled':>7} {'resting':>8} {'closed':>7}  bucket")
    for p in all_prefixes:
        bucket = "PERSIST" if p in PERSIST_PREFIXES else ("DENYLIST" if p in DENYLIST_PREFIXES else "OTHER")
        print(f"{p:32}  {filled_by_prefix[p]:>7} {resting_by_prefix[p]:>8} {closed_by_prefix[p]:>7}  {bucket}")

    # Bucket tallies
    print()
    print("=" * 90)
    print("BUCKET SUMMARY (filled vs PERSIST/DENYLIST/OTHER)")
    print("=" * 90)
    persist_filled = sum(c for p, c in filled_by_prefix.items() if p in PERSIST_PREFIXES)
    deny_filled = sum(c for p, c in filled_by_prefix.items() if p in DENYLIST_PREFIXES)
    other_filled = sum(c for p, c in filled_by_prefix.items() if p not in PERSIST_PREFIXES and p not in DENYLIST_PREFIXES)
    persist_rest = sum(c for p, c in resting_by_prefix.items() if p in PERSIST_PREFIXES)
    deny_rest = sum(c for p, c in resting_by_prefix.items() if p in DENYLIST_PREFIXES)
    other_rest = sum(c for p, c in resting_by_prefix.items() if p not in PERSIST_PREFIXES and p not in DENYLIST_PREFIXES)
    print(f"  PERSIST   filled={persist_filled}  resting={persist_rest}  (good)")
    print(f"  DENYLIST  filled={deny_filled}  resting={deny_rest}  (bleeding -- ADD TO DENYLIST)")
    print(f"  OTHER     filled={other_filled}  resting={other_rest}  (untested)")

    # Fill timing distribution
    print()
    print("=" * 90)
    print("FILL TIMING (placement to fill)")
    print("=" * 90)
    fill_durations = []
    for v in filled.values():
        try:
            placed = parse_ts(v["placed_ts"])
            filled_t = parse_ts(v["filled_ts"])
            hrs = (filled_t - placed).total_seconds() / 3600
            fill_durations.append((v["ticker"], hrs, v.get("market_mid_at_placement", 0), v.get("filled_price_cents", 0) / 100))
        except Exception:
            pass
    fill_durations.sort(key=lambda x: x[1])
    if fill_durations:
        print(f"{'ticker':50}  {'hrs':>8}  {'mid@place':>10}  {'fill_px':>9}")
        for tk, hrs, mid, px in fill_durations:
            print(f"{tk[:50]:50}  {hrs:>8.2f}  {mid:>10.3f}  {px:>9.2f}")
        avg_h = sum(x[1] for x in fill_durations) / len(fill_durations)
        med_h = sorted(x[1] for x in fill_durations)[len(fill_durations) // 2]
        print(f"  Mean hrs to fill: {avg_h:.2f}")
        print(f"  Median hrs to fill: {med_h:.2f}")

    # Settled fills: per-fill realized P&L (Round 15c addition).
    # Once any of v1's fills settle (LIVE_SETTLED status, in state.closed
    # with realized_pnl_usd set), summarize per-fill P&L grouped by prefix.
    print()
    print("=" * 90)
    print("PER-FILL REALIZED P&L (settled only, Round 15c)")
    print("=" * 90)
    settled_rows = []
    for v in closed.values():
        if v.get("status") != "live_settled":
            continue
        rp = v.get("realized_pnl_usd")
        if rp is None:
            continue
        settled_rows.append({
            "ticker": v.get("ticker", ""),
            "prefix": prefix_of(v.get("ticker", "")),
            "filled_count": int(v.get("filled_count", 0) or 0),
            "filled_price": (v.get("filled_price_cents") or 0) / 100.0,
            "outcome": v.get("resolution_outcome"),
            "pnl_usd": float(rp),
        })
    if not settled_rows:
        print("  (no settled fills yet; come back after live markets resolve)")
    else:
        print(f"{'ticker':50}  {'cnt':>4}  {'fillpx':>6}  {'out':>3}  {'pnl_usd':>9}  prefix")
        for r in sorted(settled_rows, key=lambda x: x["pnl_usd"]):
            out = r["outcome"] if r["outcome"] is not None else "-"
            print(
                f"{r['ticker'][:50]:50}  {r['filled_count']:>4}  "
                f"{r['filled_price']:>6.2f}  {out!s:>3}  "
                f"{r['pnl_usd']:>+9.4f}  {r['prefix']}"
            )

        total_pnl = sum(r["pnl_usd"] for r in settled_rows)
        n_win = sum(1 for r in settled_rows if r["pnl_usd"] > 0)
        n_loss = sum(1 for r in settled_rows if r["pnl_usd"] < 0)
        mean_pnl = total_pnl / len(settled_rows)
        print()
        print(f"  n_settled = {len(settled_rows)}, winners {n_win}, losers {n_loss}")
        print(f"  total realized P&L: ${total_pnl:+.4f}")
        print(f"  mean per-fill P&L:  ${mean_pnl:+.4f}")

        # Per-prefix breakdown
        per_prefix = defaultdict(list)
        for r in settled_rows:
            per_prefix[r["prefix"]].append(r["pnl_usd"])
        print()
        print(f"{'prefix':32}  {'n':>4}  {'mean$':>9}  {'total$':>9}  bucket")
        for pfx in sorted(per_prefix):
            ps = per_prefix[pfx]
            bucket = (
                "PERSIST" if pfx in PERSIST_PREFIXES
                else ("DENYLIST" if pfx in DENYLIST_PREFIXES else "OTHER")
            )
            print(
                f"{pfx:32}  {len(ps):>4}  "
                f"{sum(ps)/len(ps):>+9.4f}  {sum(ps):>+9.4f}  {bucket}"
            )

    # Adverse selection check: pull CURRENT mid for filled tickers (if still open)
    print()
    print("=" * 90)
    print("ADVERSE SELECTION CHECK: fill_price vs current_mid for filled markets still open")
    print("=" * 90)
    adverse_data = []
    for v in filled.values():
        ticker = v["ticker"]
        fill_px = v.get("filled_price_cents", 0) / 100.0
        place_mid = v.get("market_mid_at_placement", 0)
        side = v.get("side", "yes")
        try:
            ob = get(f"/markets/{ticker}/orderbook")
            parsed = parse_orderbook(ob)
            cur_mid = parsed.get("mid")
            if cur_mid is None:
                continue
            # If we BOUGHT YES at fill_px and current mid is BELOW fill_px, adverse selection
            adverse_pp = (cur_mid - fill_px) * 100
            adverse_data.append({"ticker": ticker, "fill_px": fill_px, "place_mid": place_mid, "cur_mid": cur_mid, "adverse_pp": adverse_pp})
        except Exception:
            pass
    if adverse_data:
        print(f"{'ticker':50}  {'fill':>5}  {'place_mid':>9}  {'cur_mid':>7}  {'adverse(pp)':>11}")
        for d in sorted(adverse_data, key=lambda x: x["adverse_pp"]):
            print(f"{d['ticker'][:50]:50}  {d['fill_px']:>5.2f}  {d['place_mid']:>9.3f}  {d['cur_mid']:>7.3f}  {d['adverse_pp']:>+11.2f}")
        mean_adverse = sum(d["adverse_pp"] for d in adverse_data) / len(adverse_data)
        n_pos = sum(1 for d in adverse_data if d["adverse_pp"] > 0)
        n_neg = sum(1 for d in adverse_data if d["adverse_pp"] < 0)
        print(f"\nMean post-fill mid move: {mean_adverse:+.2f} pp")
        print(f"  Favorable (mid > fill): {n_pos}/{len(adverse_data)}")
        print(f"  Adverse (mid < fill):   {n_neg}/{len(adverse_data)}")
    else:
        print("  (no current orderbooks available for filled markets)")


if __name__ == "__main__":
    main()
