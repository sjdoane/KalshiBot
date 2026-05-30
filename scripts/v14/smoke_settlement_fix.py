"""One-shot real-data smoke test for the settlement-status fix.

Runs the fixed reconcile_settlements against an ISOLATED temp copy of the
live v14 state using the real Kalshi API. Does NOT touch the running bot's
state file. Read-only against Kalshi (GET /markets only).
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

BASE = Path("C:/Users/SamJD/OneDrive/Desktop/AI Projects/Project Kalshi")
sys.path.insert(0, str(BASE / "src"))

from kalshi_bot.config import Settings
from kalshi_bot.data.kalshi_client import KalshiClient
from kalshi_bot.strategy.live_order_manager import LiveOrderManager


def main() -> int:
    src = BASE / "data" / "v14" / "v14_state.json"
    tmp = Path(tempfile.gettempdir()) / "v14_state_smoke.json"
    shutil.copy(src, tmp)

    before = json.loads(src.read_text())
    print("BEFORE (live state, untouched):")
    print(
        f"  filled={len(before['filled'])}  closed={len(before['closed'])}  "
        f"realized_pnl=${before['realized_pnl_total_usd']:.2f}"
    )

    with KalshiClient(Settings()) as kc:
        mgr = LiveOrderManager(client=kc, state_path=tmp, intent_id_prefix="14")
        settled = mgr.reconcile_settlements()

    res_label = {1: "YES", 0: "NO", -1: "VOID"}
    print(f"\nreconcile_settlements() settled {len(settled)} orders:")
    for o in settled:
        print(
            f"  {o.ticker:40} {res_label[o.resolution_outcome]:>4}  "
            f"pnl=${o.realized_pnl_usd:+.4f}  res_ts={o.resolution_ts}"
        )

    print("\nAFTER (temp copy):")
    print(
        f"  filled={len(mgr.state.filled)}  closed={len(mgr.state.closed)}  "
        f"realized_pnl_total=${mgr.state.realized_pnl_total_usd:+.2f}"
    )

    after_live = json.loads(src.read_text())
    print(
        f"\nLive state untouched? filled={len(after_live['filled'])} (expect 10), "
        f"realized=${after_live['realized_pnl_total_usd']:.2f} (expect 0.00)"
    )
    tmp.unlink()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
