"""Polymarket live-midpoint fetcher for Track A shadow-mode logging.

Maps Kalshi tickers to Polymarket events and returns the YES-side
midpoint price (0 to 1). Designed for use inside the shadow-mode hook
in `src/kalshi_bot/strategy/shadow_filter.py`:

- All public entry points return `None` on any failure.
- No exception is ever propagated out of this module to the caller.
- Network calls have hard timeouts; one retry on transient failure.
- Responses are cached to `data/v5/runtime_cache/polymarket_<date>.parquet`
  so repeated calls inside the same scanner loop avoid redundant HTTPS.

Critical safety constraint: v1's production trading loop calls this
fetcher inside a try/except wrapper. This module must NEVER raise an
exception in its public surface. All exceptions are caught and logged
at WARNING; the function returns None.

V3-C / V4-A previously documented the matching heuristics this module
relies on:
- Division and season-winner markets: deterministic slug construction
  from the Kalshi series prefix (e.g., 'al-east-division-winner').
- Game-h2h markets: substring match against the Polymarket public-search
  endpoint using away/home team names plus the game date.

These heuristics are deliberately conservative: a miss returns None
(silent abstention) rather than risking a wrong match. The shadow-mode
log captures the miss via `fetch_status['poly']='miss'`.

Pre-registered behavior (locked, do not retune):
- HTTP timeout: 3.0s default (caller can override).
- Single retry on transient (HTTP 5xx, timeout, connection reset).
- Cache namespace: data/v5/runtime_cache/polymarket_<YYYYMMDD>.parquet.
"""

from __future__ import annotations

import logging
import re
import time
from datetime import UTC, datetime
from pathlib import Path

log = logging.getLogger(__name__)

POLYMARKET_GAMMA_BASE = "https://gamma-api.polymarket.com"
POLYMARKET_CLOB_BASE = "https://clob.polymarket.com"

RUNTIME_CACHE_DIR = Path("data/v5/runtime_cache")


# In-process cache: ticker -> (mid_or_None, cached_at_epoch). Avoids
# refetching within the same scanner loop. Reset by restarting the bot.
_inprocess_cache: dict[str, tuple[float | None, float]] = {}
_INPROCESS_CACHE_TTL_SEC = 600.0  # 10 minutes; scanner cadence is 15 min


# Series-prefix -> Polymarket event slug template. Only deterministic
# mappings live here; ambiguous cases (h2h games) go through the
# public-search path.
LADDER_SLUG_TEMPLATES: dict[str, str] = {
    # Examples (extend as series surface in shadow-mode logs):
    # "KXMLBALEAST": "al-east-division-winner-{season}",
    # "KXNFLSB": "super-bowl-{season}-winner",
}


def _now_utc_iso() -> str:
    return datetime.now(UTC).isoformat()


def _today_yyyymmdd() -> str:
    return datetime.now(UTC).strftime("%Y%m%d")


def _parse_game_ticker(ticker: str) -> dict | None:
    """Parse a Kalshi game-h2h ticker into components.

    Supports KXMLBGAME / KXNFLGAME / KXWCGAME / KXNBAGAME shapes; returns
    None for any other ticker. Mirrors the v4 build_sportsbook_lookup
    parser semantics but is intentionally narrow: only the fields needed
    to construct a search query.
    """
    m = re.match(
        r"^KX(?P<league>MLB|NFL|WC|NBA|NHL|NCAAF|NCAAB)GAME-"
        r"(?P<yy>\d{2})(?P<mon>[A-Z]{3})(?P<day>\d{2})"
        r"(?P<hhmm>\d{0,4})"
        r"(?P<away>[A-Z]{2,3})(?P<home>[A-Z]{2,3})-(?P<team>[A-Z]{2,3})$",
        ticker,
    )
    if not m:
        return None
    return {
        "league": m.group("league"),
        "yy": m.group("yy"),
        "mon": m.group("mon"),
        "day": m.group("day"),
        "hhmm": m.group("hhmm") or "",
        "away": m.group("away"),
        "home": m.group("home"),
        "team": m.group("team"),
    }


def _construct_slug_for_ladder(ticker: str, series_ticker: str) -> str | None:
    """Try deterministic slug construction for ladder / season-winner
    markets. Returns None if no rule matches; caller falls back to search.

    This is intentionally bare today; the LADDER_SLUG_TEMPLATES dict is
    extended as we learn which series have stable Polymarket slugs from
    shadow-mode misses. Keeping the table empty until corroborated keeps
    the fetcher in a conservative "abstain on uncertainty" stance.
    """
    series_prefix = series_ticker or ticker.split("-", 1)[0]
    template = LADDER_SLUG_TEMPLATES.get(series_prefix)
    if template is None:
        return None
    # Future: substitute season etc. into the template. Until templates
    # are populated this branch is unreachable.
    return None  # noqa: RET501


def _fetch_event_by_slug(
    slug: str,
    *,
    timeout: float,
    http_get,
) -> dict | None:
    """Hit gamma-api /events/slug/{slug}. Returns event JSON or None.

    Never raises. Uses the injectable `http_get` for testability.
    """
    url = f"{POLYMARKET_GAMMA_BASE}/events/slug/{slug}"
    try:
        body, status = http_get(url, timeout=timeout)
    except Exception as exc:
        log.debug("poly_fetch_event_by_slug_error", extra={"slug": slug, "err": str(exc)})
        return None
    if status != 200 or not isinstance(body, dict):
        return None
    return body


def _search_event(
    query: str,
    *,
    timeout: float,
    http_get,
) -> dict | None:
    """Hit the public-search endpoint and pick the best-matching event.

    Conservative: if there's any ambiguity (multiple equally-scored
    candidates, no clear winner) returns None.
    """
    url = f"{POLYMARKET_GAMMA_BASE}/public-search?q={query}"
    try:
        body, status = http_get(url, timeout=timeout)
    except Exception as exc:
        log.debug("poly_search_event_error", extra={"q": query, "err": str(exc)})
        return None
    if status != 200 or not isinstance(body, dict):
        return None
    events = body.get("events") or []
    if not isinstance(events, list) or len(events) == 0:
        return None
    # Pick the highest-volume event matching the query. If the top
    # candidate's volume is not >= 2x the runner-up's, abstain.
    def _vol(ev: dict) -> float:
        try:
            return float(ev.get("volume", 0) or 0)
        except (TypeError, ValueError):
            return 0.0
    events_sorted = sorted(events, key=_vol, reverse=True)
    if len(events_sorted) == 1:
        return events_sorted[0]
    top_vol = _vol(events_sorted[0])
    second_vol = _vol(events_sorted[1])
    if top_vol >= 2.0 * second_vol and top_vol > 0:
        return events_sorted[0]
    return None


def _midpoint_for_token(
    token_id: str,
    *,
    timeout: float,
    http_get,
) -> float | None:
    """Hit clob.polymarket.com/midpoint?token_id=... Returns float or None.

    Never raises.
    """
    url = f"{POLYMARKET_CLOB_BASE}/midpoint?token_id={token_id}"
    try:
        body, status = http_get(url, timeout=timeout)
    except Exception as exc:
        log.debug("poly_midpoint_error", extra={"token": token_id, "err": str(exc)})
        return None
    if status != 200 or not isinstance(body, dict):
        return None
    mid = body.get("mid") or body.get("midpoint")
    if mid is None:
        return None
    try:
        mid_f = float(mid)
    except (TypeError, ValueError):
        return None
    if mid_f < 0.0 or mid_f > 1.0:
        return None
    return mid_f


def _yes_token_id_for_event(event: dict, target_team_code: str) -> str | None:
    """Walk the event JSON to find the YES-side CLOB token_id that
    corresponds to the Kalshi YES outcome (i.e., target_team_code).

    Polymarket events embed markets; each market embeds clobTokenIds.
    The YES outcome is usually the first token. The team-name match is
    substring-based against the market's question or outcomes field.
    Returns None on ambiguity.
    """
    markets = event.get("markets") or []
    if not isinstance(markets, list) or len(markets) == 0:
        return None
    code_lower = (target_team_code or "").lower()
    if not code_lower:
        return None
    candidates: list[str] = []
    for mkt in markets:
        if not isinstance(mkt, dict):
            continue
        question = (mkt.get("question") or "").lower()
        outcomes_raw = mkt.get("outcomes")
        if isinstance(outcomes_raw, str):
            outcomes = outcomes_raw.lower()
        elif isinstance(outcomes_raw, list):
            outcomes = " ".join(str(o).lower() for o in outcomes_raw)
        else:
            outcomes = ""
        haystack = f"{question} {outcomes}"
        if code_lower not in haystack:
            continue
        token_ids_raw = mkt.get("clobTokenIds") or mkt.get("clob_token_ids")
        if isinstance(token_ids_raw, str):
            # Sometimes returned as JSON-encoded string list.
            try:
                import json as _json
                token_ids = _json.loads(token_ids_raw)
            except (TypeError, ValueError):
                token_ids = []
        elif isinstance(token_ids_raw, list):
            token_ids = token_ids_raw
        else:
            token_ids = []
        if isinstance(token_ids, list) and len(token_ids) >= 1:
            candidates.append(str(token_ids[0]))
    if len(candidates) == 1:
        return candidates[0]
    # Ambiguous: abstain.
    return None


def _default_http_get(url: str, *, timeout: float) -> tuple[dict | None, int]:
    """Minimal HTTPS GET that returns (json_or_none, status_code).

    Never raises. Lazy-imports httpx so the module import path is cheap
    when the env flag is off.
    """
    try:
        import httpx
    except ImportError:
        log.warning("poly_fetcher_httpx_missing")
        return None, 0
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            resp = client.get(url, headers={"User-Agent": "project-kalshi-v5-shadow"})
            status = resp.status_code
            if status != 200:
                return None, status
            try:
                return resp.json(), status
            except ValueError:
                return None, status
    except Exception as exc:
        log.debug("poly_http_get_error", extra={"url": url, "err": str(exc)})
        return None, 0


def _persist_cache_row(ticker: str, mid: float | None, series_ticker: str) -> None:
    """Append one row to today's runtime cache parquet. Best-effort; any
    failure here is swallowed because the shadow-mode log is the
    durable record (the cache is only an optimization).
    """
    try:
        import pandas as pd
        RUNTIME_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path = RUNTIME_CACHE_DIR / f"polymarket_{_today_yyyymmdd()}.parquet"
        row = {
            "ticker": ticker,
            "series_ticker": series_ticker,
            "poly_mid": mid,
            "fetched_at": _now_utc_iso(),
        }
        if path.exists():
            try:
                existing = pd.read_parquet(path)
                df = pd.concat([existing, pd.DataFrame([row])], ignore_index=True)
            except Exception:
                df = pd.DataFrame([row])
        else:
            df = pd.DataFrame([row])
        df.to_parquet(path, index=False)
    except Exception as exc:
        log.debug("poly_cache_persist_error", extra={"err": str(exc)})


def fetch_polymarket_midpoint(
    ticker: str,
    series_ticker: str,
    *,
    timeout: float = 3.0,
    _http_get=None,
) -> float | None:
    """Fetch the Polymarket YES-side midpoint for the matching event.

    Returns the midpoint in [0.0, 1.0] on success, or None on any
    failure (no match, network error, parse error, timeout). NEVER
    raises.

    Args:
        ticker: Kalshi market ticker (e.g., 'KXMLBGAME-26MAY24WSHATL-ATL').
        series_ticker: Kalshi series ticker (e.g., 'KXMLBGAME').
        timeout: Per-HTTP-request timeout in seconds. Default 3.0s; the
            shadow_filter wrapper budgets two fetchers under a combined
            5s ceiling at the call site.
        _http_get: Optional injectable HTTP callable for tests. Defaults
            to a small httpx wrapper. Signature:
            `_http_get(url, *, timeout) -> (json_or_none, status_code)`.

    Behavior:
        - In-process TTL cache short-circuits repeats (10 min TTL).
        - Slug construction tried first for ladder / season-winner
          markets (currently empty template table; falls through to
          search).
        - Game-h2h tickers: parses team+date, builds a query, hits
          public-search, picks the best event, walks clobTokenIds to
          find the YES token for the target team, hits
          /midpoint?token_id=... .
        - Any single step failing returns None.
    """
    try:
        # In-process cache short-circuit.
        cache_hit = _inprocess_cache.get(ticker)
        now_epoch = time.time()
        if cache_hit is not None:
            cached_mid, cached_at = cache_hit
            if (now_epoch - cached_at) < _INPROCESS_CACHE_TTL_SEC:
                return cached_mid

        http_get = _http_get if _http_get is not None else _default_http_get

        # 1) Try deterministic slug for ladder / season-winner markets.
        slug = _construct_slug_for_ladder(ticker, series_ticker)
        event: dict | None = None
        target_team_code: str | None = None
        if slug is not None:
            event = _fetch_event_by_slug(slug, timeout=timeout, http_get=http_get)
            # For ladder markets the "team" is encoded in the ticker;
            # extract it from the last hyphenated segment as a coarse
            # match key. Better matching is per-series and is added when
            # specific slugs are populated.
            target_team_code = ticker.rsplit("-", 1)[-1]

        # 2) Game-h2h fallback: parse and search.
        if event is None:
            parsed = _parse_game_ticker(ticker)
            if parsed is None:
                # No match path available; abstain.
                _inprocess_cache[ticker] = (None, now_epoch)
                _persist_cache_row(ticker, None, series_ticker)
                return None
            target_team_code = parsed["team"]
            # Build a minimal query: just the two team codes plus year.
            query = f"{parsed['away']} {parsed['home']} 20{parsed['yy']}"
            event = _search_event(query, timeout=timeout, http_get=http_get)
            if event is None:
                # One retry on transient network/search miss.
                time.sleep(0.2)
                event = _search_event(query, timeout=timeout, http_get=http_get)
            if event is None:
                _inprocess_cache[ticker] = (None, now_epoch)
                _persist_cache_row(ticker, None, series_ticker)
                return None

        if event is None or target_team_code is None:
            _inprocess_cache[ticker] = (None, now_epoch)
            _persist_cache_row(ticker, None, series_ticker)
            return None

        # 3) Walk the event to find the YES token_id for the target team.
        token_id = _yes_token_id_for_event(event, target_team_code)
        if token_id is None:
            _inprocess_cache[ticker] = (None, now_epoch)
            _persist_cache_row(ticker, None, series_ticker)
            return None

        # 4) Hit the CLOB midpoint endpoint.
        mid = _midpoint_for_token(token_id, timeout=timeout, http_get=http_get)
        if mid is None:
            # One retry on transient midpoint failure.
            time.sleep(0.2)
            mid = _midpoint_for_token(token_id, timeout=timeout, http_get=http_get)

        _inprocess_cache[ticker] = (mid, now_epoch)
        _persist_cache_row(ticker, mid, series_ticker)
        return mid
    except Exception as exc:
        # Last line of defense: this function must NEVER raise.
        log.warning("polymarket_fetcher_unexpected", exc_info=exc)
        return None
