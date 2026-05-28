"""Live trading daily review.

Reads:
- data/live_trades/state.json (LiveOrderManager state)
- data/live_trades/kill_state.json (KillTriggerMonitor state)
- data/live_trades/heartbeat.txt (loop liveness)
- data/live_trades/logs/live.log (recent activity)

Prints a snapshot suitable for daily operator review:
- Bot liveness (heartbeat age)
- Open / resting / filled / closed counts
- Per-resting-order detail (ticker, price, age)
- Per-settled-order detail (last 10)
- Realized P&L total
- Kill-trigger metrics (yes_rate, fill_rate, rolling means, drawdown)
- Drawdown action
- Last 50 log lines

Usage: uv run python -m scripts.live_review [--full-log]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

STATE_DIR = Path("data/live_trades")
STATE_PATH = STATE_DIR / "state.json"
KILL_STATE_PATH = STATE_DIR / "kill_state.json"
HEARTBEAT_PATH = STATE_DIR / "heartbeat.txt"
LOG_PATH = STATE_DIR / "logs" / "live.log"


def _load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"WARN: failed to read {path}: {exc}")
        return None


def _human_age(iso_ts: str | None) -> str:
    if not iso_ts:
        return "never"
    try:
        t = datetime.fromisoformat(iso_ts)
    except ValueError:
        return f"<unparseable: {iso_ts}>"
    delta = datetime.now(UTC) - t
    seconds = int(delta.total_seconds())
    if seconds < 60:
        return f"{seconds}s ago"
    if seconds < 3600:
        return f"{seconds // 60}m ago"
    if seconds < 86400:
        return f"{seconds // 3600}h {(seconds % 3600) // 60}m ago"
    return f"{seconds // 86400}d {(seconds % 86400) // 3600}h ago"


def _mean(seq: list[float]) -> float:
    return sum(seq) / len(seq) if seq else 0.0


def print_section(title: str) -> None:
    print(f"\n=== {title} ===")


def review_heartbeat() -> None:
    print_section("Bot liveness")
    if not HEARTBEAT_PATH.exists():
        print("HEARTBEAT FILE MISSING. Bot may have never started, or "
              "shutdown without restart.")
        return
    iso = HEARTBEAT_PATH.read_text(encoding="utf-8").strip()
    age_str = _human_age(iso)
    print(f"  last heartbeat: {iso}  ({age_str})")
    try:
        t = datetime.fromisoformat(iso)
        seconds = (datetime.now(UTC) - t).total_seconds()
    except ValueError:
        seconds = float("inf")
    if seconds > 1800:
        print("  STATUS: STALE (no heartbeat in >30 min). Bot may have crashed.")
    elif seconds > 1200:
        print("  STATUS: WARN (heartbeat older than 20 min; cadence is 15 min)")
    else:
        print("  STATUS: ALIVE")


def review_state() -> None:
    print_section("LiveOrderManager state")
    s = _load_json(STATE_PATH)
    if s is None:
        print("  no state file yet (bot has not placed any orders)")
        return
    intents = s.get("intents") or {}
    resting = s.get("resting") or {}
    filled = s.get("filled") or {}
    closed = s.get("closed") or {}
    starting = float(s.get("starting_bankroll_usd", 0))
    realized = float(s.get("realized_pnl_total_usd", 0))
    bankroll = starting + realized
    print(f"  starting bankroll: ${starting:.2f}")
    print(f"  realized P&L:      ${realized:+.4f}")
    print(f"  current bankroll:  ${bankroll:.2f}")
    print(f"  intents (mid-POST): {len(intents)}")
    print(f"  resting (on book):  {len(resting)}")
    print(f"  filled (unsettled): {len(filled)}")
    print(f"  closed:             {len(closed)}")

    if resting:
        print("\n  Resting orders:")
        for o in resting.values():
            price = o.get("target_price_cents", 0)
            age = _human_age(o.get("placed_ts"))
            print(f"    {o.get('ticker', '?'):44s} {price}c x{o.get('contracts', 0)} "
                  f"placed {age}")

    if filled:
        print("\n  Filled (awaiting settlement):")
        for o in filled.values():
            fp = o.get("filled_price_cents", 0)
            fc = o.get("filled_count", 0)
            age = _human_age(o.get("filled_ts"))
            print(f"    {o.get('ticker', '?'):44s} filled {fc}@{fp}c {age}")

    if closed:
        settled = [o for o in closed.values()
                   if o.get("status") == "live_settled"]
        if settled:
            print("\n  Recent settlements (last 10):")
            settled.sort(key=lambda o: o.get("resolution_ts") or "", reverse=True)
            yes_count = sum(1 for o in settled if o.get("resolution_outcome") == 1)
            print(f"    yes_rate: {yes_count}/{len(settled)} = {yes_count/len(settled):.3f}")
            for o in settled[:10]:
                outcome = o.get("resolution_outcome")
                outcome_str = {1: "YES", 0: "NO", -1: "VOID"}.get(outcome, "?")
                pnl = o.get("realized_pnl_usd") or 0
                print(f"    {o.get('ticker', '?'):44s} {outcome_str:4s} "
                      f"pnl ${pnl:+.4f}")
        cancelled = [o for o in closed.values()
                     if o.get("status") == "live_cancelled"]
        if cancelled:
            print(f"\n  Cancelled orders: {len(cancelled)}")


def review_kill_triggers() -> None:
    print_section("Kill-trigger monitor")
    k = _load_json(KILL_STATE_PATH)
    if k is None:
        print("  no kill state yet (bot hasn't recorded any settlements/attempts)")
        return
    tripped = k.get("tripped", False)
    attempts = k.get("placement_attempts_total", 0)
    fills = k.get("placement_filled_total", 0)
    fill_rate = (fills / attempts) if attempts > 0 else None
    outcomes = k.get("recent_outcomes", [])
    pnls = k.get("recent_pnl_per_contract", [])
    winners = k.get("winner_pnl_per_contract", [])

    print(f"  TRIPPED: {tripped}")
    if tripped:
        print(f"    reason: {k.get('trip_reason')}")
        print(f"    detail: {k.get('trip_detail')}")
        print(f"    at:     {k.get('trip_ts')}")
    print(f"  placement_attempts_total: {attempts}")
    print(f"  placement_filled_total:   {fills}")
    if fill_rate is not None:
        print(f"  fill_rate:                {fill_rate:.3f}")
    else:
        print("  fill_rate:                n/a (no attempts)")
    print(f"  recent settlements: {len(outcomes)}")
    if outcomes:
        n = len(outcomes)
        last_20 = outcomes[-20:]
        last_10 = pnls[-10:]
        last_30 = pnls[-30:]
        print(f"  yes_rate (last {min(20, n)}): {sum(last_20)/len(last_20):.3f}")
        print(f"  rolling-10 mean P&L: {_mean(last_10):+.4f}/contract "
              f"({_mean(last_10)*100:+.2f}pp)")
        print(f"  rolling-30 mean P&L: {_mean(last_30):+.4f}/contract "
              f"({_mean(last_30)*100:+.2f}pp)")
    if winners:
        print(f"  winners so far: {len(winners)}; "
              f"mean P&L: {_mean(winners):+.4f}/contract")


def review_log_tail(n: int = 50) -> None:
    if n <= 0:
        return
    print_section(f"Log tail (last {n} lines)")
    if not LOG_PATH.exists():
        print(f"  log file not found at {LOG_PATH}")
        return
    try:
        with LOG_PATH.open("r", encoding="utf-8") as f:
            lines = f.readlines()
    except OSError as exc:
        print(f"  read failed: {exc}")
        return
    for line in lines[-n:]:
        print(f"  {line.rstrip()}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--full-log", action="store_true",
                        help="Print the entire current log file, not just the tail.")
    parser.add_argument("--lines", type=int, default=50,
                        help="Log tail line count (default 50).")
    args = parser.parse_args()

    print(f"Live review @ {datetime.now(UTC).isoformat()}")
    review_heartbeat()
    review_state()
    review_kill_triggers()
    review_log_tail(n=999999 if args.full_log else args.lines)
    return 0


if __name__ == "__main__":
    sys.exit(main())
