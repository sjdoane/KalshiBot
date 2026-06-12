"""Acceptance harness for becker_screen_v22.p1_estimate (review C-2).

Hand-computable fixture:
- Cell A = (g1, band0, band0): 12 aged events x 5 trades, every aged e = 0.1.
  Cold: event E1 (which also has 5 aged fills in cell A) with 2 cold fills
  e = 0.3 -> LOEO comparator (6.0 - 0.5)/(60 - 5) = 0.1, K = 11, N = 55,
  v = 0.2 each. Cold: event ENEW (no aged fills) 1 fill e = 0.3 ->
  comparator 0.1 (full cell), v = 0.2.
- Cell B = (g1, band1, band0): only 10 aged trades from 2 events -> INVALID
  (< 50 trades, < 10 events); its 1 cold fill must be EXCLUDED.
Expected: point = +20.00pp on 3 included cold fills (2 events), 1 excluded;
all v identical -> every bootstrap resample mean = 0.2 -> CI = [20, 20].
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from becker_screen_v22 import p1_estimate  # noqa: E402


def mk_row(ev, e, cold, tte_band=0, group="g1"):
    return {
        "event_ticker": ev, "group": group, "graveyard": False,
        "tte_band": tte_band, "price_band": 0,
        "is_cold": cold, "age_h": 1.0 if cold else 100.0,
        "tte_d": 50.0, "gross": e, "fee_era": 0.01, "fee_status": "zero",
    }


def main() -> None:
    rows = []
    # Cell A aged: 12 events x 5 trades, e = 0.1.
    for i in range(12):
        rows += [mk_row(f"E{i+1}", 0.1, cold=False) for _ in range(5)]
    # Cell A cold: E1 (2 fills) + ENEW (1 fill), e = 0.3.
    rows += [mk_row("E1", 0.3, cold=True)] * 2
    rows += [mk_row("ENEW", 0.3, cold=True)]
    # Cell B (tte_band 1): invalid comparator (10 aged trades, 2 events).
    for i in range(2):
        rows += [mk_row(f"B{i+1}", 0.1, cold=False, tte_band=1) for _ in range(5)]
    rows += [mk_row("BCOLD", 0.5, cold=True, tte_band=1)]

    df = pd.DataFrame(rows)
    r = p1_estimate(df, "table_low")
    assert "error" not in r, r
    ok_point = abs(r["point_pp"] - 20.0) < 1e-9
    ok_ci = abs(r["ci_pp"][0] - 20.0) < 1e-9 and abs(r["ci_pp"][1] - 20.0) < 1e-9
    ok_counts = (r["n_cold_included"] == 3 and r["n_events_included"] == 2
                 and r["n_cold_excluded_unmatched"] == 1)
    print(f"point={r['point_pp']:.6f}pp ci={r['ci_pp']} "
          f"inc={r['n_cold_included']} ev={r['n_events_included']} "
          f"exc={r['n_cold_excluded_unmatched']}")
    if ok_point and ok_ci and ok_counts:
        print("SYNTHETIC HARNESS: PASS")
    else:
        print(f"SYNTHETIC HARNESS: FAIL (point={ok_point} ci={ok_ci} counts={ok_counts})")
        sys.exit(1)


if __name__ == "__main__":
    main()
