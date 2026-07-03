"""Build data/v28/rt_vintages.json: as-of Tomatometer score paths for every
settled KXRT event, reconstructed from Wayback Machine snapshots.

Per event: CDX-list ALL statuscode-200 snapshots of rottentomatoes.com/m/<slug>
in [close_date - 75d, close_date + 3d] (no collapse), fetch each with the id_
raw-mode URL, parse the media-scorecard-json blob (JSON-LD aggregateRating as
fallback), keep rows [ts, score, review_count].

Resumable: rt_vintages.json is reloaded on start; already-fetched timestamps
(rows + permanent parse failures in failed_ts) are skipped.

Throttling: 2 workers max, global >= 0.55s spacing between request starts,
backoff 8s * attempt on errors. Do NOT raise worker count (Wayback blocked
this project at 6 workers before).

Parse recipe verified in research/v28/scout-rt-vintages.md.
"""

import json
import re
import threading
import time
import datetime as dt
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

ROOT = Path(r"C:\Users\SamJD\OneDrive\Desktop\AI Projects\Project Kalshi")
MARKETS = ROOT / "data" / "v28" / "markets_all.json"
OUT = ROOT / "data" / "v28" / "rt_vintages.json"
SLUG_MAP_OUT = ROOT / "data" / "v28" / "rt_slug_map.json"

CDX = "http://web.archive.org/cdx/search/cdx"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) research-script"}

WINDOW_BEFORE_DAYS = 75
WINDOW_AFTER_DAYS = 3
WORKERS = 2
MIN_SPACING_S = 0.55
MAX_ATTEMPTS = 4

# Full 43-event slug map.
# source "scout": verified in research/v28/scout-rt-vintages.md (reused verbatim).
# source "cdx": resolved in this session via scripts/v28/resolve_slugs.py
#   (Wayback CDX prefix search; winner = most 200-snapshots in the event window;
#   evidence in data/v28/rt_slug_candidates.json).
SLUGS = {
    # scout-verified (22 finalized events + KXRT-SEN)
    "KXRT-MIC": ("michael", "scout"),
    "KXRT-MOT": ("mother_mary", "scout"),
    "KXRT-ANI": ("animal_farm_2025", "scout"),
    "KXRT-DEV": ("the_devil_wears_prada_2", "scout"),
    "KXRT-BIL": ("billie_eilish_hit_me_hard_and_soft_the_tour_live_in_3d", "scout"),
    "KXRT-MOR": ("mortal_kombat_ii", "scout"),
    "KXRT-SHEE": ("the_sheep_detectives", "scout"),
    "KXRT-INT": ("in_the_grey", "scout"),
    "KXRT-OBS": ("obsession_2025", "scout"),
    "KXRT-STA": ("star_wars_the_mandalorian_and_grogu", "scout"),
    "KXRT-BAC": ("backrooms", "scout"),
    "KXRT-PRE": ("pressure_2026", "scout"),
    "KXRT-MAS": ("masters_of_the_universe_2026", "scout"),
    "KXRT-POW": ("power_ballad", "scout"),
    "KXRT-SCA": ("scary_movie_2026", "scout"),
    "KXRT-DIS": ("disclosure_day", "scout"),
    "KXRT-STO": ("stop_that_train", "scout"),
    "KXRT-DEA": ("the_death_of_robin_hood", "scout"),
    "KXRT-GIR": ("girls_like_girls", "scout"),
    "KXRT-TOY": ("toy_story_5", "scout"),
    "KXRT-JAC": ("jackass_best_and_last", "scout"),
    "KXRT-SUPE": ("supergirl_2026", "scout"),
    "KXRT-SEN": ("send_help", "scout"),
    # cdx-resolved (winner = most in-window snapshots; evidence in
    # data/v28/rt_slug_candidates.json; KXRT-LEE corrected by direct CDX probe:
    # lee_cronins_the_mummy 21 in-window vs the_mummy_2017 background noise)
    "KXRT-BRI": ("the_bride_2026", "cdx"),
    "KXRT-CRI": ("crime_101_2026", "cdx"),
    "KXRT-DRA": ("the_drama", "cdx"),
    "KXRT-FRO": ("forbidden_fruits_2026", "cdx"),
    "KXRT-HOP": ("hoppers", "cdx"),
    "KXRT-HOW": ("how_to_make_a_killing_2026", "cdx"),
    "KXRT-LEE": ("lee_cronins_the_mummy", "cdx"),
    "KXRT-MEL": ("melania", "cdx"),
    "KXRT-MER": ("mercy_2026", "cdx"),
    "KXRT-PRO": ("project_hail_mary", "cdx"),
    "KXRT-REA": ("ready_or_not_2_here_i_come", "cdx"),
    "KXRT-REM": ("reminders_of_him", "cdx"),
    "KXRT-SCR": ("scream_7", "cdx"),
    "KXRT-SHE": ("shelter_2026", "cdx"),
    "KXRT-STR": ("the_strangers_chapter_3", "cdx"),
    "KXRT-SUP": ("the_super_mario_galaxy_movie", "cdx"),
    "KXRT-WHI": ("whistle_2025", "cdx"),
    "KXRT-WIL": ("they_will_kill_you", "cdx"),
    "KXRT-WUT": ("wuthering_heights_2026", "cdx"),
    "KXRT-YOU": ("you_me_and_tuscany", "cdx"),
}

SCORECARD_RE = re.compile(
    r'<script[^>]*id="media-scorecard-json"[^>]*>(.*?)</script>', re.S
)
JSONLD_RE = re.compile(
    r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', re.S
)

_rate_lock = threading.Lock()
_last_request = [0.0]
_counter_lock = threading.Lock()
_fetch_count = [0]
_t0 = time.time()


def throttle():
    with _rate_lock:
        wait = _last_request[0] + MIN_SPACING_S - time.time()
        if wait > 0:
            time.sleep(wait)
        _last_request[0] = time.time()


def bump_counter():
    with _counter_lock:
        _fetch_count[0] += 1
        n = _fetch_count[0]
    if n % 25 == 0:
        el = time.time() - _t0
        print(f"progress: {n} fetches, {el/60:.1f} min elapsed", flush=True)
    return n


def http_get(url, params=None, timeout=60):
    last_err = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        throttle()
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=timeout)
            if r.status_code == 200:
                return r
            last_err = f"HTTP {r.status_code}"
        except Exception as e:  # noqa: BLE001
            last_err = repr(e)
        if attempt < MAX_ATTEMPTS:
            time.sleep(8 * attempt)
    raise RuntimeError(f"failed after {MAX_ATTEMPTS} attempts: {last_err}")


def cdx_timestamps(slug, close_date):
    frm = (close_date - dt.timedelta(days=WINDOW_BEFORE_DAYS)).strftime("%Y%m%d")
    to = (close_date + dt.timedelta(days=WINDOW_AFTER_DAYS)).strftime("%Y%m%d")
    r = http_get(CDX, params={
        "url": f"rottentomatoes.com/m/{slug}",
        "output": "json",
        "fl": "timestamp",
        "filter": "statuscode:200",
        "from": frm,
        "to": to,
    })
    rows = r.json() if r.text.strip() else []
    ts = sorted({row[0] for row in rows[1:]}) if rows else []
    return ts


def parse_snapshot(html):
    """Return (score, review_count) or raise ValueError."""
    m = SCORECARD_RE.search(html)
    if m:
        try:
            d = json.loads(m.group(1))
            cs = d.get("criticsScore") or {}
            score = cs.get("score")
            count = cs.get("reviewCount")
            score = int(score) if score not in (None, "") else None
            count = int(count) if count not in (None, "") else None
            return score, count
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    for blob in JSONLD_RE.findall(html):
        try:
            d = json.loads(blob.strip())
        except json.JSONDecodeError:
            continue
        agg = d.get("aggregateRating") if isinstance(d, dict) else None
        if isinstance(agg, dict) and agg.get("name") == "Tomatometer":
            score = agg.get("ratingValue")
            count = agg.get("reviewCount")
            score = int(score) if score not in (None, "") else None
            count = int(count) if count not in (None, "") else None
            return score, count
    raise ValueError("no scorecard JSON or Tomatometer JSON-LD found")


def fetch_one(slug, ts):
    url = f"https://web.archive.org/web/{ts}id_/https://www.rottentomatoes.com/m/{slug}"
    r = http_get(url, timeout=90)
    return parse_snapshot(r.text)


def save(state):
    tmp = OUT.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=1), encoding="utf-8")
    tmp.replace(OUT)


def main():
    markets = json.loads(MARKETS.read_text(encoding="utf-8"))
    events = {}
    for m in markets.values():
        events[m["event_ticker"]] = m["close_time"]
    print(f"{len(events)} settled events in markets_all.json", flush=True)

    missing = sorted(set(events) - set(SLUGS))
    if missing:
        print(f"WARNING: no slug for events: {missing}", flush=True)

    # write the full slug map
    slug_map = {
        ev: {"slug": SLUGS[ev][0], "source": SLUGS[ev][1], "close_time": events[ev]}
        for ev in sorted(events) if ev in SLUGS
    }
    SLUG_MAP_OUT.write_text(json.dumps(slug_map, indent=1), encoding="utf-8")

    state = {}
    if OUT.exists():
        state = json.loads(OUT.read_text(encoding="utf-8"))
        print(f"resuming: {len(state)} events already in {OUT.name}", flush=True)

    total_parse_fail = 0
    total_fetch_fail = 0

    for ev in sorted(events, key=lambda e: events[e]):
        if ev not in SLUGS:
            continue
        slug = SLUGS[ev][0]
        close_time = events[ev]
        close_date = dt.datetime.fromisoformat(close_time.replace("Z", "+00:00")).date()

        entry = state.setdefault(ev, {
            "slug": slug, "close_time": close_time, "rows": [], "failed_ts": [],
        })
        done_ts = {r[0] for r in entry["rows"]} | set(entry["failed_ts"])

        try:
            all_ts = cdx_timestamps(slug, close_date)
        except Exception as e:  # noqa: BLE001
            print(f"{ev}: CDX FAILED ({e}); skipping event this pass", flush=True)
            continue
        entry["n_cdx"] = len(all_ts)
        todo = [ts for ts in all_ts if ts not in done_ts]
        print(f"{ev} ({slug}): {len(all_ts)} snapshots in window, {len(todo)} to fetch",
              flush=True)

        pending = 0
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            futs = {pool.submit(fetch_one, slug, ts): ts for ts in todo}
            for fut in as_completed(futs):
                ts = futs[fut]
                bump_counter()
                try:
                    score, count = fut.result()
                    entry["rows"].append([ts, score, count])
                except ValueError as e:
                    entry["failed_ts"].append(ts)
                    total_parse_fail += 1
                    print(f"  {ev} {ts}: parse failure ({e})", flush=True)
                except Exception as e:  # noqa: BLE001
                    # transient fetch failure: do NOT mark permanent, retry next run
                    total_fetch_fail += 1
                    print(f"  {ev} {ts}: fetch failure ({e})", flush=True)
                pending += 1
                if pending % 25 == 0:
                    entry["rows"].sort(key=lambda r: r[0])
                    save(state)
        entry["rows"].sort(key=lambda r: r[0])
        entry["failed_ts"].sort()
        save(state)
        print(f"{ev}: done, {len(entry['rows'])} rows, "
              f"{len(entry['failed_ts'])} parse-fails", flush=True)

    # summary
    print("\n=== SUMMARY ===", flush=True)
    n_rows = sum(len(v["rows"]) for v in state.values())
    print(f"events: {len(state)}/{len(events)}; total rows: {n_rows}; "
          f"parse fails: {total_parse_fail}; fetch fails this pass: {total_fetch_fail}",
          flush=True)
    counts = sorted(len(v["rows"]) for v in state.values())
    if counts:
        def q(p):
            i = max(0, min(len(counts) - 1, round(p * (len(counts) - 1))))
            return counts[i]
        print(f"per-event row counts: min={counts[0]} q25={q(0.25)} "
              f"median={q(0.5)} q75={q(0.75)} max={counts[-1]}", flush=True)
    for ev, v in sorted(state.items()):
        close = dt.datetime.fromisoformat(v["close_time"].replace("Z", "+00:00"))
        lo = (close - dt.timedelta(days=21)).strftime("%Y%m%d%H%M%S")
        hi = close.strftime("%Y%m%d%H%M%S")
        n21 = sum(1 for r in v["rows"] if lo <= r[0] <= hi)
        flag = "  <-- THIN final-21d" if n21 < 5 else ""
        print(f"  {ev}: {len(v['rows'])} rows, {n21} in final 21d before close{flag}",
              flush=True)


if __name__ == "__main__":
    main()
