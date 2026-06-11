"""v21 G-C0 verdict evaluator (pre-registered counting procedure).

Committed BEFORE any scheduled gate scan has run, so the count has zero
post-hoc flexibility. Implements lock v3.1 section 3.3 counting exactly:

- counts ONLY records with run_kind == "scheduled" AND the v3.1 schema
  marker (n_families_split_multi_underlier present); probe runs and any
  pre-v3.1 record are excluded
- skips status == "failed" records (lock v3.2: a network-failed slot
  collected nothing and does not consume the budget; it is logged for
  coverage transparency only)
- caps at the FIRST 21 such records by ts_utc (the pre-registered scan
  budget; later scans, if the task is left running, do not count). Per
  lock v3.2 the collection window extends until 21 successful scans
  accumulate, HARD CAP 2026-06-23 (day 14); at the cap the verdict is
  final on however many scans ran
- a lock instance = a candidate with confirmed == true
- distinctness = one count per (event, ticker_lo, ticker_hi) per
  scan_date_pt (Pacific calendar date)
- G-C0 PASS requires >= 3 distinct locks, each of which must ALSO pass a
  MANUAL title check (both legs are nested thresholds on the same
  underlying quantity); the script prints what to check and fetches live
  titles with --fetch-titles. The manual check can only DEMOTE the
  verdict (PASS-pending-manual -> FAIL), never promote it.

KILL on FAIL: Candidate C is NULL, v21 closes, unregister the task:
  Unregister-ScheduledTask -TaskName KalshiC0LadderScan -Confirm:$false

Run (Windows):
  & "C:\\Users\\SamJD\\OneDrive\\Desktop\\AI Projects\\Project Kalshi\\.venv-kronos\\Scripts\\python.exe" "C:\\Users\\SamJD\\OneDrive\\Desktop\\AI Projects\\Project Kalshi\\scripts\\v21\\evaluate_g_c0.py" [--fetch-titles]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

BASE = Path(r"C:/Users/SamJD/OneDrive/Desktop/AI Projects/Project Kalshi")
LOG_PATH = BASE / "research" / "v21" / "c0_scan_log.jsonl"
SCAN_BUDGET = 21
GATE_MIN_DISTINCT = 3


def load_gate_records() -> list[dict]:
    records = []
    with open(LOG_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if rec.get("run_kind") != "scheduled":
                continue
            if rec.get("status") == "failed":
                continue  # v3.2: network-failed slot; logged, not a scan
            if "n_families_split_multi_underlier" not in rec:
                continue  # pre-v3.1 schema; the identification rule differed
            records.append(rec)
    records.sort(key=lambda r: r["ts_utc"])
    return records[:SCAN_BUDGET]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch-titles", action="store_true",
                    help="pull live market titles for the manual nested-threshold check")
    args = ap.parse_args()

    records = load_gate_records()
    print(f"[g-c0] {len(records)} of {SCAN_BUDGET} budgeted scheduled scans in the log")
    if records:
        print(f"[g-c0] first {records[0]['ts_utc']}  last {records[-1]['ts_utc']}")
    by_date: dict[str, int] = {}
    for r in records:
        by_date[r["scan_date_pt"]] = by_date.get(r["scan_date_pt"], 0) + 1
    for d in sorted(by_date):
        print(f"  {d}: {by_date[d]} scans")
    nets = [r.get("best_net_margin_observed") for r in records if r.get("best_net_margin_observed") is not None]
    if nets:
        print(f"[g-c0] best-net-per-scan distribution: min {min(nets)} max {max(nets)} "
              f"(near-miss context for the write-up)")

    distinct: dict[tuple[str, str, str, str], dict] = {}
    for r in records:
        for c in r.get("candidates", []):
            if not c.get("confirmed"):
                continue
            key = (c["event"], c["ticker_lo"], c["ticker_hi"], r["scan_date_pt"])
            if key not in distinct or c["confirm"]["net_cents"] > distinct[key]["confirm"]["net_cents"]:
                distinct[key] = c

    print(f"\n[g-c0] {len(distinct)} DISTINCT confirmed locks "
          f"(threshold: >= {GATE_MIN_DISTINCT})")

    titles: dict[str, str] = {}
    if args.fetch_titles and distinct:
        os.chdir(BASE)
        sys.path.insert(0, str(BASE / "src"))
        from kalshi_bot.config import Settings
        from kalshi_bot.data.kalshi_client import KalshiClient
        with KalshiClient(Settings()) as kc:
            for key in distinct:
                for t in (key[1], key[2]):
                    if t not in titles:
                        try:
                            m = kc.get(f"/markets/{t}").get("market", {})
                            titles[t] = f"{m.get('title', '?')} | {m.get('yes_sub_title', '?')}"
                        except Exception as exc:
                            titles[t] = f"<fetch failed: {exc}>"

    for key, c in sorted(distinct.items(), key=lambda kv: kv[0][3]):
        ev, lo, hi, day = key
        print(f"\n  {day}  {ev}")
        print(f"    LOWER  {lo}  (strike {c['strike_lo']})  {titles.get(lo, '')}")
        print(f"    HIGHER {hi}  (strike {c['strike_hi']})  {titles.get(hi, '')}")
        print(f"    confirm net ${c['confirm']['net']:.4f} ({c['confirm']['net_cents']}c), "
              f"depths {c['confirm']['yes_ask_lo_depth']}/{c['confirm']['no_ask_hi_depth']}")
        print("    MANUAL CHECK: same underlying quantity, nested thresholds? "
              "If NO for any lock, it does not count.")

    provisional = " (PROVISIONAL: scan budget incomplete)" if len(records) < SCAN_BUDGET else ""
    if len(records) < SCAN_BUDGET:
        print(f"\n[g-c0] NOTE: only {len(records)}/{SCAN_BUDGET} scans have run; "
              f"the verdict is final when the budget completes or at the v3.2 hard "
              f"cap 2026-06-23, whichever comes first.")
    if len(distinct) >= GATE_MIN_DISTINCT:
        print(f"\n[g-c0] VERDICT{provisional}: PASS-PENDING-MANUAL "
              f"({len(distinct)} >= {GATE_MIN_DISTINCT}). Each lock above must survive "
              f"the manual title check; demote any that fail and re-evaluate the count.")
    else:
        print(f"\n[g-c0] VERDICT{provisional}: FAIL ({len(distinct)} < {GATE_MIN_DISTINCT}). "
              f"If final: Candidate C is NULL; v21 closes. Unregister KalshiC0LadderScan.")


if __name__ == "__main__":
    main()
