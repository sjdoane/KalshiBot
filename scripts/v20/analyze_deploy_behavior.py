"""Measure v1's actual fill / capital-deployment behavior from live state.

Read-only. Parses data/live_trades/state.json + kill_state.json to answer:
  1. Is the binding constraint CAPITAL or ELIGIBLE-FILL AVAILABILITY?
     (how much of the bankroll is actually deployed at any time)
  2. What is the time-to-fill distribution for orders that DO fill?
     (informs the stale-bid TTL: a TTL below the bulk of fill times
      would cancel orders that would otherwise have filled)
  3. What is the age-at-cancel distribution for orders that never filled?
  4. Fill rate, per-prefix and per-side, old-config vs new-config.

Usage (Windows, kronos venv):
  C:\\Users\\SamJD\\.venvs\\... or the project .venv-kronos:
  .venv-kronos\\Scripts\\python.exe -m scripts.v20.analyze_deploy_behavior
"""

from __future__ import annotations

import json
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

STATE = Path("data/live_trades/state.json")
KILL = Path("data/live_trades/kill_state.json")

# The new-config (allowlist + step-in-front + NO arm + lifetime[0,21]) became
# live on the operator restart. Orders placed on/after this UTC date reflect
# the current strategy; earlier orders are the old broad-universe config.
NEW_CONFIG_CUTOFF = datetime(2026, 6, 2, 0, 0, tzinfo=timezone.utc)


def parse_ts(s: str | None) -> datetime | None:
    if not s:
        return None
    s = s.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def prefix_of(ticker: str) -> str:
    # series prefix is the chars before the first '-'
    return ticker.split("-", 1)[0] if ticker else "?"


def notional(o: dict) -> float:
    return (o.get("contracts") or 0) * (o.get("target_price_cents") or 0) / 100.0


def pct(parts: list[float]) -> str:
    if not parts:
        return "n=0"
    parts = sorted(parts)
    n = len(parts)

    def q(p: float) -> float:
        if n == 1:
            return parts[0]
        idx = p * (n - 1)
        lo = int(idx)
        hi = min(lo + 1, n - 1)
        return parts[lo] + (parts[hi] - parts[lo]) * (idx - lo)

    return (
        f"n={n} min={parts[0]:.2f} p25={q(0.25):.2f} median={q(0.5):.2f} "
        f"p75={q(0.75):.2f} p90={q(0.9):.2f} max={parts[-1]:.2f} "
        f"mean={statistics.mean(parts):.2f}"
    )


def main() -> None:
    state = json.loads(STATE.read_text(encoding="utf-8"))
    kill = json.loads(KILL.read_text(encoding="utf-8"))

    bankroll = kill.get("starting_bankroll_usd", 0.0)
    now = max(
        (
            parse_ts(o.get("last_updated_ts") or kill.get("last_updated_ts"))
            for o in [kill]
        ),
        default=None,
    ) or datetime.now(timezone.utc)

    resting = state.get("resting", {})
    filled = state.get("filled", {})
    closed = state.get("closed", {})

    print("=" * 72)
    print("v1 CAPITAL-DEPLOYMENT + FILL-BEHAVIOR ANALYSIS")
    print(f"bankroll (kill_state.starting_bankroll_usd) = ${bankroll:.2f}")
    print(f"state 'now' anchor = {now.isoformat()}")
    print("=" * 72)

    # ---- 1. CURRENT DEPLOYMENT (the capital-vs-availability question) ----
    resting_notional = sum(notional(o) for o in resting.values())
    resting_contracts = sum((o.get("contracts") or 0) for o in resting.values())

    # truly-open filled positions = filled and not yet resolved
    open_filled = {
        k: o
        for k, o in filled.items()
        if o.get("resolution_outcome") is None
    }
    open_notional = sum(notional(o) for o in open_filled.values())
    open_contracts = sum((o.get("contracts") or 0) for o in open_filled.values())

    deployed = resting_notional + open_notional
    print("\n--- 1. CURRENT DEPLOYMENT ---")
    print(f"resting orders:        {len(resting):>4}  contracts={resting_contracts:>4}  ${resting_notional:7.2f}")
    print(f"open filled positions: {len(open_filled):>4}  contracts={open_contracts:>4}  ${open_notional:7.2f}")
    print(f"TOTAL DEPLOYED:                              ${deployed:7.2f}")
    if bankroll:
        print(f"DEPLOYED / BANKROLL  = {100*deployed/bankroll:5.1f}%   (idle = {100*(1-deployed/bankroll):4.1f}%)")
    print(f"resting / bankroll   = {100*resting_notional/bankroll:5.1f}%" if bankroll else "")

    # per-bid size actually used (contracts per order)
    all_orders = list(resting.values()) + list(filled.values()) + list(closed.values())
    contract_sizes = Counter((o.get("contracts") or 0) for o in all_orders)
    print(f"\nper-order contract sizes (all-time): {dict(sorted(contract_sizes.items()))}")
    recent_orders = [o for o in all_orders if (parse_ts(o.get("placed_ts")) or now) >= NEW_CONFIG_CUTOFF]
    recent_sizes = Counter((o.get("contracts") or 0) for o in recent_orders)
    print(f"per-order contract sizes (new-config, since {NEW_CONFIG_CUTOFF.date()}): {dict(sorted(recent_sizes.items()))}")

    # ---- 2. FILL TIMING (the stale-TTL question) ----
    def fill_hours(o: dict) -> float | None:
        p, f = parse_ts(o.get("placed_ts")), parse_ts(o.get("filled_ts"))
        if p and f:
            return (f - p).total_seconds() / 3600.0
        return None

    fill_times_all = [h for o in filled.values() if (h := fill_hours(o)) is not None]
    fill_times_new = [
        h
        for o in filled.values()
        if (h := fill_hours(o)) is not None
        and (parse_ts(o.get("placed_ts")) or now) >= NEW_CONFIG_CUTOFF
    ]
    print("\n--- 2. TIME-TO-FILL for orders that FILLED (hours) ---")
    print(f"all-time:    {pct(fill_times_all)}")
    print(f"new-config:  {pct(fill_times_new)}")
    # how many fills would a TTL of X hours have pre-empted?
    for ttl in (1, 2, 3, 4, 6, 12):
        n_after = sum(1 for h in fill_times_all if h > ttl)
        share = 100 * n_after / len(fill_times_all) if fill_times_all else 0
        print(f"  fills that took > {ttl:>2}h: {n_after:>3} / {len(fill_times_all)} ({share:4.1f}%)  <- a {ttl}h TTL would have cancelled these before they filled")

    # ---- 3. AGE-AT-CANCEL for never-filled orders ----
    def cancel_age_hours(o: dict) -> float | None:
        p, c = parse_ts(o.get("placed_ts")), parse_ts(o.get("cancelled_ts"))
        if p and c and not o.get("filled_count"):
            return (c - p).total_seconds() / 3600.0
        return None

    cancel_ages = [h for o in closed.values() if (h := cancel_age_hours(o)) is not None]
    print("\n--- 3. AGE-AT-CANCEL for never-filled cancelled orders (hours) ---")
    print(f"{pct(cancel_ages)}")

    # ---- 4. FILL RATE + breakdowns ----
    n_filled = len(filled)
    n_cancelled_unfilled = sum(1 for o in closed.values() if not o.get("filled_count"))
    denom = n_filled + n_cancelled_unfilled
    print("\n--- 4. FILL RATE (filled / (filled + never-filled-cancelled)) ---")
    print(f"all-time: {n_filled} / {denom} = {100*n_filled/denom:.1f}%" if denom else "n/a")

    # new-config fill rate
    def is_new(o: dict) -> bool:
        return (parse_ts(o.get("placed_ts")) or now) >= NEW_CONFIG_CUTOFF

    nf_new = sum(1 for o in filled.values() if is_new(o))
    nc_new = sum(1 for o in closed.values() if is_new(o) and not o.get("filled_count"))
    rest_new = sum(1 for o in resting.values() if is_new(o))
    print(f"new-config: filled={nf_new}, never-filled-cancelled={nc_new}, still-resting={rest_new}")

    # per-prefix (new-config orders only, all states)
    print("\n--- per-prefix (new-config orders, all states) ---")
    per_prefix = defaultdict(lambda: Counter())
    for bucket, label in ((resting, "resting"), (filled, "filled"), (closed, "closed/canc")):
        for o in bucket.values():
            if is_new(o):
                per_prefix[prefix_of(o.get("ticker", ""))][label] += 1
    for pfx, c in sorted(per_prefix.items()):
        print(f"  {pfx:28} {dict(c)}")

    # per-side (new-config)
    print("\n--- per-side (new-config orders, all states) ---")
    per_side = Counter(o.get("side") for o in all_orders if is_new(o))
    print(f"  {dict(per_side)}")

    # expected_net_edge distribution on new-config orders (sanity: are bids
    # being placed at the validated +5-8% net edge, or at higher implied edges?)
    edges = [o.get("expected_net_edge") for o in all_orders if is_new(o) and o.get("expected_net_edge") is not None]
    if edges:
        print("\n--- expected_net_edge on new-config orders (fraction of $1) ---")
        print(f"  {pct([100*e for e in edges])}  (in cents/contract)")

    # price band distribution on new-config orders (LOW [0.70,0.86) vs heavy)
    print("\n--- favorite-side price band (new-config, by market_mid_at_placement) ---")
    bands = Counter()
    for o in all_orders:
        if not is_new(o):
            continue
        mid = o.get("market_mid_at_placement")
        if mid is None:
            continue
        # favorite-side price: for NO orders the favorite side is the underdog framed; use target price as proxy
        band = "LOW[.70,.86)" if 0.70 <= mid < 0.86 else ("heavy[.86,.95]" if 0.86 <= mid <= 0.95 else f"other({mid:.2f})")
        bands[band] += 1
    print(f"  {dict(bands)}")


if __name__ == "__main__":
    main()
