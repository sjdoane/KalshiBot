"""One-shot: set v1's display tally cutoff so the Discord running-total and the
heartbeat count ONLY bets PLACED at/after a cutoff timestamp (default: now UTC).

Use after a strategy/universe change (e.g. the v20 allowlist + sizing) so the
"RUNNING TOTAL ... settled (W/L)" reflects only the new config, not old
broad-universe bets (and not any pre-tagging / other-bot leftovers, which are
all placed before the cutoff). It is DISPLAY-ONLY:
  - does NOT touch realized_pnl_total_usd (the all-time accumulator that feeds
    current_live_bankroll), the open positions, exposure, or settlement;
  - does NOT touch the kill triggers (use scripts.reset_v1_kill for those).
Keyed on placed_ts, so old still-open positions are excluded from the new tally
even when they settle later.

Run with the v1 bot STOPPED (it rewrites state.json each loop and would either
overwrite this or race the write). Dry-run prints the effect; --i-mean-it writes
(after backing up state.json to state.json.bak). Optional --since ISO sets the
cutoff (default now UTC); e.g. to include the last day's allowlist fills pass
  --since 2026-06-02T17:00:00+00:00

PowerShell (project root):
    .venv-kronos/Scripts/python.exe -m scripts.reset_v1_tally
    .venv-kronos/Scripts/python.exe -m scripts.reset_v1_tally --i-mean-it
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

BASE = Path("C:/Users/SamJD/OneDrive/Desktop/AI Projects/Project Kalshi")
STATE = BASE / "data" / "live_trades" / "state.json"


def _parse_iso(ts: object) -> datetime | None:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _summary(closed: dict, cutoff: datetime | None) -> tuple[float, int, int, int, int]:
    """(realized, winners, losers, voids, count) over settled closed orders,
    filtered to placed_ts >= cutoff when cutoff is set. SIDE-AWARE W/L (a NO bet
    resolving NO is a win), mirroring LiveOrderManager.realized_summary_since so
    this preview matches what the bot will display."""
    total = 0.0
    w = lo = v = 0
    for o in closed.values():
        if o.get("realized_pnl_usd") is None:
            continue
        if cutoff is not None:
            p = _parse_iso(o.get("placed_ts"))
            if p is None or p < cutoff:
                continue
        total += float(o["realized_pnl_usd"])
        oc = o.get("resolution_outcome")
        side = o.get("side")
        if oc == -1:
            v += 1
        elif (side == "yes" and oc == 1) or (side == "no" and oc == 0):
            w += 1
        elif oc in (0, 1):
            lo += 1
    return total, w, lo, v, w + lo + v


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--i-mean-it", action="store_true")
    ap.add_argument(
        "--force", action="store_true",
        help="Write even if bot.lock is present. Use ONLY if you are sure the "
             "bot is stopped (e.g. a stale lock from a crash).",
    )
    ap.add_argument(
        "--since", default=None,
        help="ISO cutoff (default: now UTC). Bets placed before this are "
             "excluded from the displayed tally.",
    )
    args = ap.parse_args()

    if not STATE.exists():
        print(f"No state at {STATE}; nothing to do.")
        return 0

    raw = json.loads(STATE.read_text(encoding="utf-8"))
    closed = raw.get("closed", {})
    cutoff_iso = args.since or datetime.now(timezone.utc).isoformat()
    cutoff = _parse_iso(cutoff_iso)
    if cutoff is None:
        print(f"Bad --since value: {args.since!r}")
        return 2

    all_t, aw, al, av, an = _summary(closed, None)
    new_t, nw, nl, nv, nn = _summary(closed, cutoff)
    print("BEFORE (all settled bets in the closed bucket):")
    print(f"  realized=${all_t:+.2f}   {aw}W / {al}L / {av}V  of {an}")
    print(f"  current tally_since_ts = {raw.get('tally_since_ts')}")
    print(f"\nNEW cutoff = {cutoff_iso}")
    print(f"  tally after cutoff: realized=${new_t:+.2f}   {nw}W / {nl}L / {nv}V  of {nn}")
    print(f"  (drops {an - nn} settled bets placed before the cutoff)")
    print("  still-open bets placed before the cutoff are also excluded when they later settle.")

    if not args.i_mean_it:
        print("\n[DRY RUN] Re-run with --i-mean-it to write tally_since_ts (state.json backed up first).")
        return 0

    # Guard: if the bot holds its single-instance lock it is (or was) running and
    # will overwrite state.json (and this cutoff) on its next loop, silently
    # no-opping the reset. Refuse unless the operator confirms it is stopped.
    lock = STATE.with_name("bot.lock")
    if lock.exists() and not args.force:
        print("\nREFUSING: data/live_trades/bot.lock is present, so the v1 bot may be RUNNING.")
        print("It would overwrite this reset on its next loop. Stop it first:")
        print("  Stop-ScheduledTask -TaskName KalshiLiveBot")
        print("then re-run. Pass --force only if you are sure the bot is stopped (stale lock).")
        return 1

    backup = STATE.with_name("state.json.bak")
    backup.write_text(json.dumps(raw, indent=2, default=str), encoding="utf-8")
    raw["tally_since_ts"] = cutoff_iso
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(raw, indent=2, default=str), encoding="utf-8")
    tmp.replace(STATE)
    print(f"\nWROTE tally_since_ts={cutoff_iso}  (backup: {backup.name}).")
    print("Running-total tally now counts only bets placed at/after the cutoff.")
    print("realized_pnl_total_usd, open positions, exposure, and kills are UNCHANGED.")
    print("Run with the bot STOPPED; restart to pick it up.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
