"""Resolve RT slugs for settled KXRT events not covered by the scout map.

Method (mirrors research/v28/scout-rt-vintages.md): Wayback CDX prefix search on
rottentomatoes.com/m/<fragment> to enumerate candidate slugs, then count
statuscode-200 snapshots inside the event window [close-75d, close+3d].
The candidate with the most in-window snapshots wins.

Output: data/v28/rt_slug_candidates.json (evidence per event).
"""

import json
import re
import time
import datetime as dt
from pathlib import Path

import requests

ROOT = Path(r"C:\Users\SamJD\OneDrive\Desktop\AI Projects\Project Kalshi")
OUT = ROOT / "data" / "v28" / "rt_slug_candidates.json"

CDX = "http://web.archive.org/cdx/search/cdx"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) research-script"}

# event -> (close date ISO, list of CDX prefix fragments to try)
UNKNOWN = {
    "KXRT-MER": ("2026-01-26", ["mercy"]),
    "KXRT-SHE": ("2026-02-02", ["shelter"]),
    "KXRT-MEL": ("2026-02-02", ["melania"]),
    "KXRT-STR": ("2026-02-09", ["the_strangers_chapter", "strangers_chapter"]),
    "KXRT-WHI": ("2026-02-09", ["whistle"]),
    "KXRT-CRI": ("2026-02-16", ["crime_101"]),
    "KXRT-WUT": ("2026-02-16", ["wuthering_heights"]),
    "KXRT-HOW": ("2026-02-23", ["how_to_make_a_killing"]),
    "KXRT-SCR": ("2026-03-02", ["scream_7", "scream_vii"]),
    "KXRT-BRI": ("2026-03-09", ["the_bride", "bride"]),
    "KXRT-HOP": ("2026-03-09", ["hoppers"]),
    "KXRT-REM": ("2026-03-16", ["reminders_of_him"]),
    "KXRT-REA": ("2026-03-23", ["ready_or_not"]),
    "KXRT-PRO": ("2026-03-23", ["project_hail_mary"]),
    "KXRT-WIL": ("2026-03-30", ["they_will_kill_you"]),
    "KXRT-FRO": ("2026-03-30", ["forbidden_fruits"]),
    "KXRT-SUP": ("2026-04-06", ["the_super_mario", "super_mario"]),
    "KXRT-DRA": ("2026-04-06", ["the_drama", "drama"]),
    "KXRT-YOU": ("2026-04-13", ["you_me", "tuscany"]),
    "KXRT-LEE": ("2026-04-20", ["the_mummy", "mummy"]),
}

SLUG_RE = re.compile(r"^https?://(?:www\.)?rottentomatoes\.com/m/([A-Za-z0-9_]+)/?$")


def cdx_get(params, tries=4):
    for attempt in range(1, tries + 1):
        try:
            r = requests.get(CDX, params=params, headers=HEADERS, timeout=60)
            if r.status_code == 200:
                return r.json() if r.text.strip() else []
            raise RuntimeError(f"HTTP {r.status_code}")
        except Exception as e:  # noqa: BLE001
            if attempt == tries:
                raise
            wait = 8 * attempt
            print(f"    CDX retry {attempt} after error {e}; sleep {wait}s", flush=True)
            time.sleep(wait)
    return []


def candidates_for_fragment(frag):
    rows = cdx_get({
        "url": f"rottentomatoes.com/m/{frag}",
        "matchType": "prefix",
        "collapse": "urlkey",
        "output": "json",
        "fl": "original",
        "from": "2025",
        "to": "2026",
        "limit": "500",
    })
    slugs = set()
    for row in rows[1:] if rows else []:
        m = SLUG_RE.match(row[0])
        if m:
            slugs.add(m.group(1).lower())
    return slugs


def count_in_window(slug, close_date):
    close = dt.date.fromisoformat(close_date)
    frm = (close - dt.timedelta(days=75)).strftime("%Y%m%d")
    to = (close + dt.timedelta(days=3)).strftime("%Y%m%d")
    rows = cdx_get({
        "url": f"rottentomatoes.com/m/{slug}",
        "output": "json",
        "fl": "timestamp",
        "filter": "statuscode:200",
        "from": frm,
        "to": to,
    })
    ts = [r[0] for r in rows[1:]] if rows else []
    return len(ts), (ts[0] if ts else None), (ts[-1] if ts else None)


def main():
    results = {}
    if OUT.exists():
        try:
            results = json.loads(OUT.read_text(encoding="utf-8"))
            print(f"resuming: {len(results)} events already done", flush=True)
        except json.JSONDecodeError:
            results = {}
    for ev, (close, frags) in UNKNOWN.items():
        if ev in results and results[ev].get("candidates"):
            continue
        print(f"== {ev} (close {close})", flush=True)
        slugs = set()
        for frag in frags:
            found = candidates_for_fragment(frag)
            print(f"  fragment '{frag}': {len(found)} candidates", flush=True)
            slugs |= found
            time.sleep(1.0)
        evidence = []
        for slug in sorted(slugs):
            n, first, last = count_in_window(slug, close)
            if n > 0:
                print(f"    {slug}: {n} snaps in window ({first}..{last})", flush=True)
                evidence.append({"slug": slug, "n_window": n, "first": first, "last": last})
            time.sleep(1.0)
        evidence.sort(key=lambda x: -x["n_window"])
        results[ev] = {"close": close, "candidates": evidence}
        OUT.write_text(json.dumps(results, indent=1), encoding="utf-8")
    print("done", flush=True)


if __name__ == "__main__":
    main()
