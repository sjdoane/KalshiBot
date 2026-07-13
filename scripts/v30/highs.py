"""v30 ARM E determination module: KXHIGH (daily-high temperature) determined-strike
capture. Kept OUT of live_pilot.py so the executor stays lean; this module owns the
weather feed, the strike parsing, and the monotone-lock determination. It places NO
orders and holds NO execution logic (live_pilot.py does the placement).

Mechanism: the intraday running MAX temperature at a station is monotone non-decreasing
through the local day, and the final settled daily high H satisfies H >= running_max and
can only rise. A market side is DECIDED (locked) only if it stays the outcome for EVERY
possible final H in [running_max, +inf). Backtest (68 days, 2,856 settled markets, 7
cities) showed 0 determination violations in 879 events at a +1F safety margin (6.5 pct
at 0F), so MARGIN_F = 1.0 is mandatory.

Feed: IEM ASOS one-minute/hourly obs (data=tmpf) for the station's local calendar day.
Determination is recomputed FRESH every run (anti-footgun: never cache a decided state
across runs; the per-process cache below lives only for the single 5-min executor tick).

Run standalone for a read-only decided-strike dump (NO orders):
  .venv/Scripts/python.exe scripts/v30/highs.py
"""
from __future__ import annotations

import csv
import io
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, "scripts/v29")

import arb_sentinel as ab  # noqa: E402

MARGIN_F = 1.0                 # +1F safety margin; mandatory (0F showed 6.5 pct violations)
MIN_OBS = 3                    # anti-footgun (b): < 3 obs so far -> feed-down for that city
ASOS = "https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py"
# IEM ASOS rate-limits rapid successive requests ("Too many requests ... slow down") and
# returns HTTP 429 even at 1.5s spacing. Space real fetches out and retry once on a 429/5xx
# with a longer backoff (fix 5a). At most 7 fetches per run (one per station, cached), so a
# clean run adds ~20s to a 5-min tick; a single retry adds the backoff on top.
REQUEST_SPACING_S = 3.0
RETRY_BACKOFF_S = 10.0         # one retry after this backoff on a 429/5xx (fix 5a)

# Series -> (ASOS station id, IANA tz). Station ids came from each series' NWS CLI
# issuedby param and match the v26 RAIN_PIL settlement stations one-for-one:
#   KXHIGHNY  -> NYC  (CLINYC, Central Park)      America/New_York
#   KXHIGHCHI -> MDW  (CLIMDW, Chicago Midway)    America/Chicago
#   KXHIGHMIA -> MIA  (CLIMIA)                    America/New_York
#   KXHIGHLAX -> LAX  (CLILAX)                    America/Los_Angeles
#   KXHIGHDEN -> DEN  (CLIDEN, Denver Intl)       America/Denver
#   KXHIGHAUS -> AUS  (CLIAUS, Austin-Bergstrom)  America/Chicago
#   KXHIGHPHIL-> PHL  (CLIPHL)                    America/New_York
# Do NOT change a station without re-checking the settling CLI issuer for that series.
STATIONS = {
    "KXHIGHNY":   ("NYC", "America/New_York"),
    "KXHIGHCHI":  ("MDW", "America/Chicago"),
    "KXHIGHMIA":  ("MIA", "America/New_York"),
    "KXHIGHLAX":  ("LAX", "America/Los_Angeles"),
    "KXHIGHDEN":  ("DEN", "America/Denver"),
    "KXHIGHAUS":  ("AUS", "America/Chicago"),
    "KXHIGHPHIL": ("PHL", "America/New_York"),
}
_STATION_TZ = {stn: tz for (stn, tz) in STATIONS.values()}

_MONTHS = {"JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
           "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12}
_EVENT_DATE_RE = re.compile(r"-(\d{2})([A-Z]{3})(\d{2})$")

# Per-process cache keyed (station, iso-date). Fresh executor process each 5-min run
# clears it; a fresh fetch each run is fine. Caches None (feed-down) too so one failed
# fetch is not retried within the same run.
_MAX_CACHE: dict[tuple[str, str], float | None] = {}

# Stations whose IEM feed is down/short THIS run (fix 5b: a single city's persistent feed
# failure marks ONLY that city feed-down; healthy cities proceed). Repopulated from scratch
# at the top of every decided_strikes() call. Consulted by is_bound_checkable() so a
# feed-down city's resting orders are LEFT alone (not cancelled on absence).
_FEED_DOWN_STATIONS: set[str] = set()


def event_local_date(event_ticker: str | None) -> date | None:
    """KXHIGHNY-26JUL13 -> date(2026, 7, 13). The event date in the ticker IS the
    station-local calendar day the high is measured over."""
    if not event_ticker:
        return None
    m = _EVENT_DATE_RE.search(event_ticker)
    if not m:
        return None
    yy, mmm, dd = m.groups()
    mo = _MONTHS.get(mmm)
    if mo is None:
        return None
    try:
        return date(2000 + int(yy), mo, int(dd))
    except ValueError:
        return None


_MARKET_DATE_RE = re.compile(r"-(\d{2})([A-Z]{3})(\d{2})(?:-|$)")


def market_event_date(ticker: str | None) -> date | None:
    """Event day parsed from a MARKET ticker (KXHIGHNY-26JUL13-B72.5 -> date(2026,7,13)).
    Same encoding as event_local_date but not anchored at end, so a strike suffix is fine."""
    if not ticker:
        return None
    m = _MARKET_DATE_RE.search(ticker)
    if not m:
        return None
    yy, mmm, dd = m.groups()
    mo = _MONTHS.get(mmm)
    if mo is None:
        return None
    try:
        return date(2000 + int(yy), mo, int(dd))
    except ValueError:
        return None


def is_bound_checkable(ticker: str | None) -> bool:
    """fix 3 / fix 5b: a resting ARM E order may be bound-weakened (cancelled on absence
    from the decided set) ONLY when its market's station feed is healthy THIS run AND its
    event day is the station-local today. Returns False (leave the rest alone) for:
      - a prior-day (or future) ticker: day rollover drops it from the today-only decided
        set, but the close-passed/settled cleanup, not the bound check, retires it;
      - a station currently in _FEED_DOWN_STATIONS: its absence is a feed blip, not a
        genuine un-decide, so its rests keep resting until the feed returns.
    Only a TODAY market on a HEALTHY feed that is genuinely no longer in the decided set is
    bound-weakened. Unknown series -> False (never cancel from here; fail safe)."""
    series = (ticker or "").split("-")[0]
    ent = STATIONS.get(series)
    if ent is None:
        return False
    station, tz = ent
    if station in _FEED_DOWN_STATIONS:
        return False
    ed = market_event_date(ticker)
    return ed is not None and ed == datetime.now(ZoneInfo(tz)).date()


def fetch_running_max(station: str, local_date: date) -> float | None:
    """Running max temperature (F) at an ASOS station over its local calendar day so
    far. None on any fetch error OR when fewer than MIN_OBS usable obs exist yet
    (anti-footgun b: treat a too-thin feed as down for that city). Cached per
    (station, date) in-process only."""
    key = (station, local_date.isoformat())
    if key in _MAX_CACHE:
        return _MAX_CACHE[key]
    val = _fetch_running_max_uncached(station, local_date)
    _MAX_CACHE[key] = val
    return val


def _fetch_running_max_uncached(station: str, local_date: date) -> float | None:
    tz = _STATION_TZ.get(station)
    if tz is None:
        return None
    # report_type=3 (routine hourly METAR) + 4 (specials): the same obs the NWS CLI daily
    # high settles on. Skipping the 5-minute MADIS stream also avoids stations (MIA, PHL)
    # whose high-resolution temp is all-M while their hourly METAR carries real values.
    url = (f"{ASOS}?station={station}&data=tmpf"
           f"&year1={local_date.year}&month1={local_date.month}&day1={local_date.day}"
           f"&year2={local_date.year}&month2={local_date.month}&day2={local_date.day}"
           f"&tz={tz}&format=onlycomma&missing=M&trace=T&latlon=no"
           f"&report_type=3&report_type=4")
    # fix 5a: one retry with a longer backoff on a 429/5xx (IEM rate-limit / transient
    # server error). A 429/5xx raises HTTPError and NEVER yields a partial body, so a
    # rate-limited fetch can never mint a bogus (lower) running max; it fails to None.
    text = None
    for attempt in range(2):
        try:
            time.sleep(REQUEST_SPACING_S)   # be polite to IEM (rate-limit avoidance)
            req = urllib.request.Request(url, headers=ab.UA)
            with urllib.request.urlopen(req, timeout=15) as r:  # short timeout; fail -> None
                text = r.read().decode("utf-8", errors="replace")
            break
        except urllib.error.HTTPError as e:  # retry once on 429/5xx, else give up (None)
            if attempt == 0 and (e.code == 429 or 500 <= e.code < 600):
                time.sleep(RETRY_BACKOFF_S)
                continue
            return None
        except Exception:  # noqa: BLE001  (any other fetch error -> feed-down for this city)
            return None
    if text is None:
        return None
    temps: list[float] = []
    for row in csv.DictReader(io.StringIO(text)):
        v = (row.get("tmpf") or "").strip()
        if v in ("", "M", "T"):            # missing / trace markers
            continue
        try:
            temps.append(float(v))
        except ValueError:
            continue
    if len(temps) < MIN_OBS:
        return None
    return max(temps)


def decided_side(market: dict, running_max: float | None) -> str | None:
    """The market side LOCKED by the monotone running max, or None. The final daily high
    H is monotone non-decreasing with H >= running_max and can only rise, so a side is
    locked only if it holds for EVERY H in [running_max, +inf):
      - upper-bounded YES interval (hi finite: '<K', 'K1-K2' band): once running_max
        >= hi + MARGIN, H exceeds the band/cap -> outcome is NO, and a higher max keeps
        it NO. LOCKED NO.
      - open-ended-up YES interval (hi == +inf: '>K' / '>=K'): once running_max
        >= lo + MARGIN, H is already past the floor -> YES, and a higher max keeps it
        YES. LOCKED YES.
    Everything else could be unlocked by a higher max later -> None. A band or a '<K'
    can NEVER be locked YES by the max alone, and a '>K' can never be locked NO."""
    if running_max is None:
        return None
    iv = ab.yes_interval(market)         # (lo, hi) on the daily-high axis; ab.NEG/ab.POS open
    if iv is None:
        return None
    lo, hi = iv
    if hi != ab.POS and running_max >= hi + MARGIN_F:
        return "no"
    if hi == ab.POS and lo != ab.NEG and running_max >= lo + MARGIN_F:
        return "yes"
    return None


def _cents(x) -> int | None:
    v = ab.fnum(x)
    return None if v is None else int(round(v * 100))


def decided_strikes():
    """(market, side, yes_bid_c, yes_ask_c, running_max) for open KXHIGH strikes LOCKED by
    the live running max, restricted to markets whose station-local event day is TODAY (the
    max is still accumulating; a past/ended or future day never qualifies). Determination is
    recomputed FRESH here every call.

    fix 5b (per-city degrade): a station whose Kalshi market fetch fails OR whose IEM feed is
    down/short (< MIN_OBS after the one retry) is recorded in _FEED_DOWN_STATIONS and its
    markets are simply skipped this run; healthy cities still contribute their decided
    strikes. A feed-down city's resting orders are NOT cancelled on absence: is_bound_checkable()
    returns False for that station so the caller leaves its rests alone until the feed
    returns (same leave-resting semantics as a prior-day ticker, fix 3). Returns [] when
    feeds are up and nothing is decided (or every today-city is feed-down)."""
    _FEED_DOWN_STATIONS.clear()
    out = []
    for series, (station, tz) in STATIONS.items():
        try:
            payload = ab.get_json(
                f"{ab.BASE}/markets?series_ticker={series}&status=open&limit=200")
            mkts = payload.get("markets") or []
        except Exception:  # noqa: BLE001
            _FEED_DOWN_STATIONS.add(station)   # Kalshi miss: skip city, keep its rests
            continue
        today = datetime.now(ZoneInfo(tz)).date()
        today_mkts = [m for m in mkts if event_local_date(m.get("event_ticker")) == today]
        if not today_mkts:
            continue                  # future days not started; ended days drop out (cancelled)
        rmax = fetch_running_max(station, today)
        if rmax is None:
            _FEED_DOWN_STATIONS.add(station)   # anti-footgun (b) / feed error: skip city only
            continue
        for m in today_mkts:
            side = decided_side(m, rmax)
            if side is None:
                continue
            out.append((m, side, _cents(m.get("yes_bid_dollars")) or 0,
                        _cents(m.get("yes_ask_dollars")) or 100, rmax))
    return out


if __name__ == "__main__":
    # Read-only dump for manual verification. Places NO orders.
    dec = decided_strikes()
    if _FEED_DOWN_STATIONS:
        print(f"feed-down cities this run (rests left alone): {sorted(_FEED_DOWN_STATIONS)}")
    if not dec:
        print("no decided KXHIGH strikes right now")
    else:
        for m, side, bid_c, ask_c, rmax in dec:
            print(f"{m['ticker']:<26} DECIDED {side.upper():<3} "
                  f"running_max={rmax:.0f}F  yes_bid={bid_c}c yes_ask={ask_c}c  "
                  f"{m.get('title', '')}")
