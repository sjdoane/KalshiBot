"""READ-ONLY: v1 realized-return analytics off the (fee-corrected) state.json.

Reports, for the full settled history and for the current allowlist strategy:
total realized P&L, mean per-bet P&L with a bootstrap 95% CI (the "edge real
yet" signal), side-aware win rate, and mean per-contract edge (pp) with CI;
plus a per-series breakdown. Bootstrap is per-bet (rng seed 42); note bets in a
single night/event can be correlated, so the CI is a lower bound on true width.

Run: PYTHONPATH=src .venv-kronos/Scripts/python.exe -m scripts.v20.v1_return_analytics
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import numpy as np

STATE = Path("C:/Users/SamJD/OneDrive/Desktop/AI Projects/Project Kalshi"
             "/data/live_trades/state.json")
ALLOWLIST = ("KXMLBGAME", "KXATPMATCH", "KXWTAMATCH", "KXNFLGAME", "KXNCAAFGAME")


def boot_ci(x: list[float], b: int = 10000, seed: int = 42) -> tuple[float, float]:
    a = np.asarray(x, dtype=float)
    if len(a) < 2:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(a), size=(b, len(a)))
    means = a[idx].mean(axis=1)
    lo, hi = np.percentile(means, [2.5, 97.5])
    return float(lo), float(hi)


def _won(o: dict) -> bool:
    oc = o["resolution_outcome"]
    return (o["side"] == "yes" and oc == 1) or (o["side"] == "no" and oc == 0)


def summarize(label: str, orders: list[dict]) -> None:
    if not orders:
        print(f"\n[{label}] no settled bets")
        return
    pnl = [o["realized_pnl_usd"] for o in orders]
    per_c = [o["realized_pnl_usd"] / o["filled_count"] * 100.0
             for o in orders if o["filled_count"]]
    wins = sum(1 for o in orders if o["resolution_outcome"] != -1 and _won(o))
    losses = sum(1 for o in orders if o["resolution_outcome"] != -1 and not _won(o))
    voids = sum(1 for o in orders if o["resolution_outcome"] == -1)
    n = len(orders)
    total = sum(pnl)
    mean = total / n
    lo, hi = boot_ci(pnl)
    clo, chi = boot_ci(per_c)
    wr = wins / (wins + losses) if (wins + losses) else float("nan")
    contracts = sum(o["filled_count"] for o in orders)
    print(f"\n=== {label} ===")
    print(f"  settled bets   : {n}  ({wins}W / {losses}L / {voids}V, "
          f"win rate {wr:.1%}), {contracts} contracts")
    print(f"  total realized : ${total:+.2f}")
    print(f"  mean per bet   : ${mean:+.4f}   95% CI [${lo:+.4f}, ${hi:+.4f}]"
          f"   {'EXCLUDES 0 (signal)' if lo > 0 else 'INCLUDES 0 (noise)'}")
    print(f"  mean per contr : {np.mean(per_c):+.2f}pp  95% CI "
          f"[{clo:+.2f}, {chi:+.2f}]pp")
    avg_win = np.mean([o['realized_pnl_usd'] for o in orders
                       if o['resolution_outcome'] != -1 and _won(o)]) if wins else 0.0
    avg_loss = np.mean([o['realized_pnl_usd'] for o in orders
                        if o['resolution_outcome'] != -1 and not _won(o)]) if losses else 0.0
    print(f"  avg win ${avg_win:+.3f} | avg loss ${avg_loss:+.3f} | "
          f"breakeven win rate {(-avg_loss / (avg_win - avg_loss)):.1%}"
          if (wins and losses) else "")


def main() -> int:
    state = json.loads(STATE.read_text(encoding="utf-8"))
    settled = [o for o in state["closed"].values()
               if o.get("realized_pnl_usd") is not None
               and o.get("resolution_outcome") is not None
               and o.get("filled_count")]

    summarize("ALL-TIME (every settled v1 bet)", settled)

    allow = [o for o in settled
             if any(o["ticker"].startswith(p) for p in ALLOWLIST)]
    summarize("CURRENT STRATEGY (allowlist series only)", allow)

    legacy = [o for o in settled
              if not any(o["ticker"].startswith(p) for p in ALLOWLIST)]
    summarize("LEGACY (non-allowlist broad-universe)", legacy)

    # Per-series breakdown (allowlist series).
    by_series: dict[str, list[dict]] = defaultdict(list)
    for o in settled:
        by_series[o["ticker"].split("-", 1)[0]].append(o)
    print("\n=== per-series (settled) ===")
    print(f"{'series':16} {'n':>4} {'W':>4} {'L':>4} {'total$':>9} "
          f"{'mean$/bet':>10} {'pp/contract':>12}")
    for s in sorted(by_series, key=lambda k: -sum(o["realized_pnl_usd"]
                                                  for o in by_series[k])):
        os_ = by_series[s]
        w = sum(1 for o in os_ if o["resolution_outcome"] != -1 and _won(o))
        lo_ = sum(1 for o in os_ if o["resolution_outcome"] != -1 and not _won(o))
        tot = sum(o["realized_pnl_usd"] for o in os_)
        mb = tot / len(os_)
        pc = np.mean([o["realized_pnl_usd"] / o["filled_count"] * 100.0
                      for o in os_ if o["filled_count"]])
        print(f"{s:16} {len(os_):>4} {w:>4} {lo_:>4} {tot:>+9.2f} "
              f"{mb:>+10.4f} {pc:>+11.2f}pp")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
