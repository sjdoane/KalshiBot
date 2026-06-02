"""One-shot: clear v1's tripped kill state and reset the fill-rate counters.

Use after the 2026-05-30 council decision demoted fill_rate_low from a hard
kill to a logged health metric. The cumulative placement counters
(attempts/filled) accumulated during the dormant-settlement era and include
still-resting bids, so they are reset to start a fresh window under the
trimmed universe. P&L / outcome / winner history is preserved (those feed the
drawdown + consecutive-loss kills, which stay armed).

Safe to run with the v1 bot stopped or running (it only touches
kill_state.json; the next loop reloads it). Dry-run prints the current state;
--i-mean-it writes.

PowerShell (run from the project root; the script self-adds src to the path;
forward slashes are valid in PowerShell paths):

    .venv-kronos/Scripts/python.exe -m scripts.reset_v1_kill
    .venv-kronos/Scripts/python.exe -m scripts.reset_v1_kill --i-mean-it
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BASE = Path("C:/Users/SamJD/OneDrive/Desktop/AI Projects/Project Kalshi")
sys.path.insert(0, str(BASE / "src"))

from kalshi_bot.risk.kill_triggers import KillTriggerMonitor  # noqa: E402

KILL_STATE = BASE / "data" / "live_trades" / "kill_state.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--i-mean-it", action="store_true")
    parser.add_argument(
        "--full-history", action="store_true",
        help="Also wipe the recent P&L / outcome / winner history (the YES-rate "
             "and rolling-mean trigger windows). Use ONLY when the strategy or "
             "universe changed (e.g. v1's 2026-06-01 move to the allowlist + "
             "moderate-favorite band + NO-underdog arm), so the kill triggers "
             "are not gated by settlements from the OLD broad universe. The "
             "drawdown kill (realized P&L) is unaffected.",
    )
    args = parser.parse_args()

    if not KILL_STATE.exists():
        print(f"No kill state at {KILL_STATE}; nothing to reset.")
        return 0

    kt = KillTriggerMonitor(starting_bankroll_usd=1.0, state_path=KILL_STATE)
    s = kt.state
    rate = (
        s.placement_filled_total / s.placement_attempts_total
        if s.placement_attempts_total else 0.0
    )
    print("BEFORE:")
    print(f"  tripped={s.tripped} reason={s.trip_reason} detail={s.trip_detail}")
    print(f"  fill counters: {s.placement_filled_total}/{s.placement_attempts_total} "
          f"({rate:.1%})")

    if not args.i_mean_it:
        extra = " + WIPE P&L/outcome/winner history" if args.full_history else ""
        print(f"\n[DRY RUN] Re-run with --i-mean-it to clear tripped + reset "
              f"fill counters{extra}.")
        return 0

    kt.clear(reset_fill_counters=True, reset_history=args.full_history)
    if args.full_history:
        print("\nCLEARED: tripped=False, fill counters 0/0, AND recent "
              "P&L/outcome/winner history wiped (fresh window for the new "
              "strategy). Drawdown kill (realized P&L) unaffected.")
    else:
        print("\nCLEARED: tripped=False, fill counters reset to 0/0. "
              "P&L/outcome/winner history preserved.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
