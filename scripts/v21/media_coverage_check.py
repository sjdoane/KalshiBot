"""v21 Candidate A (Media) Phase-1.5 live-coverage check. READ-ONLY.

The forward shadow re-screen (research/v21/05-media-forward-shadow-lock.md) can
only clear the pre-registered S-A1c floor (>= 200 distinct events AND >= 30
distinct allowlist prefixes) if the frozen Media allowlist still has a live,
DIVERSE 2026 universe. The allowlist (50 prefixes) was frozen on the Becker
window (through 2025-11) and is heavy with 2024-election-cycle mention/ranking
series that may no longer list.

This checks, fast, how much of the Media universe is alive RIGHT NOW: for each
allowlist prefix it queries /markets?series_ticker=PREFIX&status=open (no 2M
-market paginate needed) and counts open + mid-band [0.40,0.60) markets. It then
states whether the >= 30-prefix diversity floor is even reachable (max reachable
prefixes = the number with any in-band flow), the dominant single criterion of
forward viability.

Run (Windows, from the project root):
  .venv-kronos/Scripts/python.exe scripts/v21/media_coverage_check.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

BASE = Path(r"C:/Users/SamJD/OneDrive/Desktop/AI Projects/Project Kalshi")
sys.path.insert(0, str(BASE / "src"))

from kalshi_bot.config import Settings  # noqa: E402
from kalshi_bot.data.kalshi_client import KalshiClient  # noqa: E402

ALLOWLIST_PATH = BASE / "research" / "v21" / "allowlists" / "media_040_060.json"
BAND_LO, BAND_HI = 0.40, 0.60
S_A1C_MIN_EVENTS = 200      # locked floor (becker_screen.py)
S_A1C_MIN_PREFIXES = 30     # locked diversity floor


def in_band(m: dict) -> bool:
    for k in ("yes_ask_dollars", "yes_bid_dollars"):
        v = m.get(k)
        if v is not None:
            try:
                if BAND_LO <= float(v) < BAND_HI:
                    return True
            except (TypeError, ValueError):
                pass
    return False


def main() -> int:
    prefixes = [p["prefix"] for p in json.loads(ALLOWLIST_PATH.read_text(encoding="utf-8"))["prefixes"]]
    settings = Settings()
    alive = inband_prefixes = tot_open = tot_inband = 0
    inband_events: set[str] = set()
    live_rows: list[tuple[str, int, int]] = []
    with KalshiClient(settings) as kc:
        for pfx in prefixes:
            try:
                r = kc.get("/markets", series_ticker=pfx, status="open", limit=1000)
                ms = r.get("markets", []) if isinstance(r, dict) else []
            except Exception as exc:
                print(f"  {pfx:34} ERROR {exc!r}")
                continue
            ib = [m for m in ms if in_band(m)]
            if ms:
                alive += 1
            if ib:
                inband_prefixes += 1
            tot_open += len(ms)
            tot_inband += len(ib)
            for m in ib:
                inband_events.add(m.get("event_ticker", ""))
            if ms:
                live_rows.append((pfx, len(ms), len(ib)))

    print("=== Media live coverage ===")
    print(f"allowlist prefixes: {len(prefixes)} | alive (>0 open): {alive} | "
          f"with in-band flow: {inband_prefixes}")
    print(f"open Media markets: {tot_open} | in-band [0.40,0.60) now: {tot_inband} | "
          f"distinct in-band events now: {len(inband_events)}")
    for pfx, o, ib in sorted(live_rows, key=lambda r: -r[2]):
        if ib:
            print(f"  {pfx:34} open={o:4} in-band={ib}")
    # The >= 30-prefix diversity floor is the binding, time-independent gate:
    # only prefixes with in-band flow can ever contribute an in-band event.
    reachable = inband_prefixes >= S_A1C_MIN_PREFIXES
    print(f"\nS-A1c diversity floor (>= {S_A1C_MIN_PREFIXES} prefixes): "
          f"max reachable = {inband_prefixes} -> "
          f"{'REACHABLE' if reachable else 'UNREACHABLE (forward re-screen not viable)'}")
    print(f"S-A1c event floor (>= {S_A1C_MIN_EVENTS} events): needs sustained flow "
          f"across many prefixes; current in-band breadth is {inband_prefixes} prefixes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
