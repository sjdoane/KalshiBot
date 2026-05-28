"""Track 2 entry point: produce shadow_filter_decisions.jsonl from
the existing v5 filter shadow log + v1 order state.

Operator usage:

    uv run python -m scripts.v11.join_filter_vs_v1

Reads data/live_trades/v5_filter_shadow_log.jsonl and
data/live_trades/state.json. Writes
data/live_trades/shadow/shadow_filter_decisions.jsonl (parent dir
auto-created). Output is overwritten on each run; the script is
on-demand, not a long-running daemon.
"""

from __future__ import annotations

import sys
from pathlib import Path

from kalshi_bot_v11.filter_v1_join import run_join


SHADOW_LOG_PATH = Path("data/live_trades/v5_filter_shadow_log.jsonl")
STATE_JSON_PATH = Path("data/live_trades/state.json")
OUTPUT_PATH = Path("data/live_trades/shadow/shadow_filter_decisions.jsonl")


def main() -> int:
    if not SHADOW_LOG_PATH.exists():
        print(f"ERROR: shadow log not found at {SHADOW_LOG_PATH}", file=sys.stderr)
        return 1
    if not STATE_JSON_PATH.exists():
        print(f"ERROR: v1 state.json not found at {STATE_JSON_PATH}", file=sys.stderr)
        return 1
    n_rows = run_join(SHADOW_LOG_PATH, STATE_JSON_PATH, OUTPUT_PATH)
    print(f"Wrote {n_rows} cross-table rows to {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
