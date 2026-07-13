"""v28 stage-1 $0 LIVE READ (read-only; self-expires 2026-09-01).

Every run (scheduled 30 min):
1. Pull open KXRT markets (quotes, strikes).
2. For each open event, resolve/cache the live RT slug (candidate list, verified by a
   successful scorecard parse), fetch the LIVE page (verified unblocked), and append
   the state (score, reviewCount) to data/v28/live_rt_states.jsonl: the self-archived
   as-of series the historical world lacked.
3. Compute the LIVE bound at the frozen read rule:
   L in [ceil((s-0.5)N/100), floor((s+0.5)N/100)];
   A_live = max(5, ceil(2.0 * arrivals_last_24h * hours_remaining / 24));
   decided YES if 100*L_lo/(N+A) > K + 1.0; decided NO if 100*(L_hi+A)/(N+A) < K - 1.0.
4. Log EVERY decided strike with its live quotes; flag decided_in_band when the
   decided side is executable (YES ask <= 0.955; NO with yes_bid >= 0.045).

READ GATE (pre-committed in research/v28/05-FINAL-VERDICT.md): at least one
decided_in_band row by 2026-08-31 opens the single v27-A3 shadow; zero across >= 6
movie closes = family death. This script never places orders.

Remove: Unregister-ScheduledTask -TaskName KalshiV28RTRead
Run: .venv/Scripts/python.exe scripts/v28/live_rt_read.py
"""
from __future__ import annotations

import json
import math
import os
import re
import sys
import time
import urllib.request
from datetime import date, datetime, timedelta, timezone

BASE = "https://api.elections.kalshi.com/trade-api/v2"
V28 = os.path.join("data", "v28")
STATES = os.path.join(V28, "live_rt_states.jsonl")
LOG = os.path.join(V28, "live_rt_read_log.jsonl")
CACHE = os.path.join(V28, "live_slug_cache.json")
EXPIRY = date(2026, 9, 1)
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) research", "Accept": "*/*"}
SCORECARD_RE = re.compile(r'<script[^>]*id="media-scorecard-json"[^>]*>(.*?)</script>', re.S)
READ_MARGIN = 1.0
A_FLOOR = 5
CAP_MULT = 2.0
# Cross-movie MAX arrival ratio (arrivals to read / count now) by remaining days,
# monotone envelope, computed 2026-07-03 from the banked 43-event vintage layer
# (data/v28/rt_vintages.json). The live cap must dominate this envelope: a decided
# claim at long horizon requires enormous slack, by construction.
ENV_RATIO = {1: 0.5, 2: 0.667, 3: 1.5, 4: 3.382, 5: 3.382, 6: 5.364, 7: 5.364,
             8: 5.364, 9: 7.095, 10: 7.095, 11: 7.294, 12: 7.294, 13: 7.294, 14: 7.294}
YES_MAX_ASK = 0.955
NO_MIN_BID = 0.045

CANDIDATES = {
    "KXRT-MIN": ["minions_and_monsters", "minions_3", "despicable_me_minions_and_monsters"],
    "KXRT-INV": ["the_invite_2026", "the_invite"],
    "KXRT-YOUN": ["young_washington"],
    "KXRT-EVI": ["evil_dead_burn", "evil_dead_burn_2026", "evil_dead_2026"],
    "KXRT-ODY": ["the_odyssey_2026", "the_odyssey", "the_odyssey_movie", "odyssey_2026"],
    "KXRT-MOA": ["moana_2026", "moana_live_action", "moana"],
    "KXRT-SPI": ["spider_man_brand_new_day"],
    "KXRT-AVE": ["avengers_doomsday"],
    "KXRT-DUNE": ["dune_part_three"],
}

# Known-wrong bare slugs per event: the bare "moana" page is the 2016 animated film
# (score 87, count 15, static for days), NOT the 2026 live-action remake KXRT-MOA
# tracks. Never cache or accept a blocklisted slug for its event (defect-2 fix); the
# live-action candidates (moana_2026 / moana_live_action) are still tried.
SLUG_BLOCKLIST = {"KXRT-MOA": {"moana"}}


def get(url: str, timeout: int = 45) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def log_row(fp: str, row: dict) -> None:
    row["logged_utc"] = datetime.now(timezone.utc).isoformat()
    with open(fp, "a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def parse_live(slug: str):
    html = get(f"https://www.rottentomatoes.com/m/{slug}", timeout=60).decode("utf-8", "replace")
    m = SCORECARD_RE.search(html)
    if not m:
        return None
    d = json.loads(m.group(1))
    cs = d.get("criticsScore") or {}
    s, n = cs.get("score"), cs.get("reviewCount")
    if s in (None, "") or n in (None, ""):
        return None
    return int(s), int(n)


def resolve_slug(ev: str, cache: dict, force: bool = False):
    """Resolve the live RT slug for an event. force=True re-attempts the FULL candidate
    list even when a slug is cached, preferring an earlier-listed candidate that now
    parses (defect-2 (ii)). A blocklisted cached slug is invalidated and re-resolved."""
    blocked = SLUG_BLOCKLIST.get(ev, set())
    cached = cache.get(ev)
    if cached is not None and cached in blocked:
        # invalidate a known-wrong cached slug and force full re-resolution (defect-2)
        cache.pop(ev, None)
        json.dump(cache, open(CACHE, "w", encoding="utf-8"))
        cached = None
    if cached is not None and not force:
        return cached
    for slug in CANDIDATES.get(ev, []):
        if slug in blocked:
            continue
        try:
            st = parse_live(slug)
        except Exception:  # noqa: BLE001
            st = None
        if st is not None:
            cache[ev] = slug
            json.dump(cache, open(CACHE, "w", encoding="utf-8"))
            return slug
        time.sleep(1.0)
    if cached is not None:
        return cached  # re-resolution found nothing better; keep the prior slug
    log_row(LOG, {"kind": "slug_unresolved", "event": ev})
    return None


def feed_stale(ev: str, s: int, n: int, hours_left: float) -> bool:
    """Defect-2 (i): True when this event's (score, count) has been unchanged across
    polls spanning >= 24h while count < 50 and the market still has > 48h to close. A
    frozen low-count feed on a still-live market is the wrong-movie / dead-page
    signature (e.g. KXRT-MOA stuck at the 2016 animated page: 87 / 15)."""
    if n >= 50 or hours_left <= 48.0:
        return False
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    run_start = None
    try:
        with open(STATES, encoding="utf-8") as f:
            for line in f:
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if r.get("event") != ev:
                    continue
                if r.get("score") == s and r.get("count") == n:
                    lu = r.get("logged_utc", "")
                    if run_start is None or lu < run_start:
                        run_start = lu
                else:
                    run_start = None  # a differing reading resets the unchanged span
    except FileNotFoundError:
        return False
    return run_start is not None and run_start <= cutoff


def reresolve_due(ev: str) -> bool:
    """Defect-2 (ii): True if the full candidate list has not been re-attempted for ev
    in >= 12h, so re-resolution runs at least every 12h even without a stale flag."""
    if not os.path.exists(LOG):
        return True
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=12)).isoformat()
    last = None
    try:
        with open(LOG, encoding="utf-8") as f:
            for line in f:
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if r.get("kind") == "slug_reresolve" and r.get("event") == ev:
                    lu = r.get("logged_utc", "")
                    if last is None or lu > last:
                        last = lu
    except FileNotFoundError:
        return True
    return last is None or last <= cutoff


def arrivals_24h(ev: str, n_now: int) -> int:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    best = None
    try:
        with open(STATES, encoding="utf-8") as f:
            for line in f:
                r = json.loads(line)
                if r.get("event") == ev and r["logged_utc"] >= cutoff:
                    if best is None or r["logged_utc"] < best[0]:
                        best = (r["logged_utc"], r["count"])
    except FileNotFoundError:
        pass
    return max(0, n_now - best[1]) if best else 0


def l_interval(s: int, n: int):
    lo = max(0, math.ceil((s - 0.5) * n / 100.0 - 1e-9))
    hi = min(n, math.floor((s + 0.5) * n / 100.0 + 1e-9))
    if lo > hi:
        lo = hi = max(0, min(n, round(s * n / 100.0)))
    return lo, hi


def main() -> int:
    if date.today() > EXPIRY:
        return 0
    os.makedirs(V28, exist_ok=True)
    cache = json.load(open(CACHE, encoding="utf-8")) if os.path.exists(CACHE) else {}
    try:
        mkts = json.loads(get(f"{BASE}/markets?series_ticker=KXRT&status=open&limit=200"))["markets"]
    except Exception as e:  # noqa: BLE001
        log_row(LOG, {"kind": "error", "where": "kalshi", "err": str(e)})
        return 0
    by_ev = {}
    for m in mkts:
        by_ev.setdefault(m["event_ticker"], []).append(m)
    log_row(LOG, {"kind": "heartbeat", "open_events": sorted(by_ev)})
    for ev, ms in sorted(by_ev.items()):
        slug = resolve_slug(ev, cache)
        if slug is None:
            continue
        try:
            st = parse_live(slug)
        except Exception as e:  # noqa: BLE001
            log_row(LOG, {"kind": "error", "where": f"rt:{slug}", "err": str(e)})
            continue
        if st is None:
            log_row(LOG, {"kind": "no_scorecard", "event": ev, "slug": slug})
            continue
        s, n = st
        close = datetime.fromisoformat(ms[0]["close_time"].replace("Z", "+00:00"))
        hours_left = max(0.0, (close - datetime.now(timezone.utc)).total_seconds() / 3600.0)
        stale = feed_stale(ev, s, n, hours_left)
        # defect-2 (ii): re-attempt the FULL candidate list when the feed looks stale,
        # or at least every 12h, preferring an earlier-listed candidate that now parses
        if stale or reresolve_due(ev):
            log_row(LOG, {"kind": "slug_reresolve", "event": ev, "prev_slug": slug,
                          "stale": stale})
            new_slug = resolve_slug(ev, cache, force=True)
            if new_slug is not None and new_slug != slug:
                try:
                    st2 = parse_live(new_slug)
                except Exception:  # noqa: BLE001
                    st2 = None
                if st2 is not None:
                    slug, (s, n) = new_slug, st2
                    stale = feed_stale(ev, s, n, hours_left)
        log_row(STATES, {"event": ev, "slug": slug, "score": s, "count": n,
                         "stale_feed": stale})
        if n <= 0 or hours_left <= 0:
            continue
        d = min(14, max(1, math.ceil(hours_left / 24.0)))
        a = max(A_FLOOR,
                math.ceil(CAP_MULT * ENV_RATIO[d] * n),
                math.ceil(CAP_MULT * arrivals_24h(ev, n) * hours_left / 24.0))
        lo_l, hi_l = l_interval(s, n)
        low = 100.0 * lo_l / (n + a)
        high = 100.0 * (hi_l + a) / (n + a)
        for m in ms:
            k = m.get("floor_strike")
            if k is None or m.get("strike_type") != "greater":
                continue
            k = float(k)
            side = None
            if low > k + READ_MARGIN:
                side = "yes"
            elif high < k - READ_MARGIN:
                side = "no"
            if side is None:
                continue
            ask = float(m.get("yes_ask_dollars") or 1.0)
            bid = float(m.get("yes_bid_dollars") or 0.0)
            in_band = (side == "yes" and ask <= YES_MAX_ASK) or (side == "no" and bid >= NO_MIN_BID)
            log_row(LOG, {
                "kind": "decided_in_band" if in_band else "decided",
                "ticker": m["ticker"], "event": ev, "side": side, "score": s, "count": n,
                "a_live": a, "low": round(low, 2), "high": round(high, 2), "strike": k,
                "yes_bid": bid, "yes_ask": ask, "ask_size": m.get("yes_ask_size_fp"),
                "bid_size": m.get("yes_bid_size_fp"), "hours_left": round(hours_left, 1),
            })
    return 0


if __name__ == "__main__":
    sys.exit(main())
