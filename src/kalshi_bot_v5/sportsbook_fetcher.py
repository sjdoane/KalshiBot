"""Sportsbook live-implied-probability fetcher for Track A shadow-mode.

Maps a Kalshi ticker to the-odds-api (sport_key, event_id), fetches the
h2h odds for the matching event, and returns the de-vigged median
implied probability across listed bookmakers. Designed to be called
from `src/kalshi_bot/strategy/shadow_filter.py` as a logging-only hook
on v1's main loop.

Hard contracts (critical for v1 safety):
- Never raises. Any failure returns None.
- Hard HTTP timeout (default 3.0s) on every external call.
- Per-loop credit budget: ceiling of 5 paid calls per scanner-loop
  iteration; reset between loops via `reset_loop_budget()`.
- Single retry on transient (HTTP 5xx, connection reset, timeout).
- Cache responses to `data/v5/runtime_cache/sportsbook_<date>.parquet`
  to avoid repeat fetches inside the same loop.

This module deliberately reuses V5-A2's matching logic by delegating to
the parsers and team-name lookup tables in
`scripts/v5/build_sportsbook_lookup.py`. We import them by path because
the build script is the canonical source for those tables; duplicating
would invite drift. If the script ever moves under `src/`, this import
can become a relative import.

Cost model (from V5-A1):
- /v4/sports/{sport_key}/events is FREE (0 credits).
- /v4/sports/{sport_key}/odds?eventIds=...&markets=h2h costs 1 credit
  per call (single event).
- v1's scanner cadence is 15 min with up to ~15 candidates; at our
  default 5-call budget per loop, monthly burn is ~5 * 4 * 24 * 30 =
  14,400 in pathological worst case but realistically ~150 calls/mo
  because only ~31% of candidates are MATCH-class (V5-A1 Section 3.5).

Pre-registered behavior (locked):
- Default timeout: 3.0s per HTTP call.
- Credit-budget ceiling per loop: 5 (configurable via
  `SHADOW_SPORTSBOOK_LOOP_BUDGET` env var; defaults to 5).
- Cache: data/v5/runtime_cache/sportsbook_<YYYYMMDD>.parquet.
"""

from __future__ import annotations

import importlib.util
import logging
import os
import time
import urllib.parse
from datetime import UTC, datetime
from pathlib import Path

log = logging.getLogger(__name__)

ODDS_API_BASE = "https://api.the-odds-api.com/v4"
RUNTIME_CACHE_DIR = Path("data/v5/runtime_cache")


# In-process per-loop budget. Caller is expected to call
# reset_loop_budget() at the top of each scanner-loop iteration; if
# they forget, the budget caps at LOOP_BUDGET_DEFAULT and stays there
# until reset (worst case: we abstain after exhausting budget).
LOOP_BUDGET_DEFAULT = 5
_credits_used_this_loop = 0


# In-process result cache: ticker -> (implied_or_None, cached_at_epoch).
_inprocess_cache: dict[str, tuple[float | None, float]] = {}
_INPROCESS_CACHE_TTL_SEC = 600.0  # 10 minutes


# Lazy-loaded handles to V5-A2's matching machinery. We resolve them on
# first use; if the build script is missing for any reason, the fetcher
# falls back to "no match" (returns None) cleanly.
_BUILD_SCRIPT_MODULE = None


def _load_build_script():
    """Lazy-load scripts/v5/build_sportsbook_lookup.py as a module.

    The build script lives outside the importable `src/` tree by design
    (it's a CLI). We load it via importlib.util so we can reuse its
    parsers, team-name lookup tables, and de-vig helpers without
    duplicating code.

    Returns the loaded module or None on any failure.
    """
    global _BUILD_SCRIPT_MODULE
    if _BUILD_SCRIPT_MODULE is not None:
        return _BUILD_SCRIPT_MODULE
    try:
        repo_root = Path(__file__).resolve().parents[2]
        script_path = repo_root / "scripts" / "v5" / "build_sportsbook_lookup.py"
        if not script_path.exists():
            return None
        spec = importlib.util.spec_from_file_location(
            "_v5_build_sportsbook_lookup", str(script_path),
        )
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _BUILD_SCRIPT_MODULE = module
        return module
    except Exception as exc:
        log.debug("sportsbook_fetcher_build_script_load_error", extra={"err": str(exc)})
        return None


def reset_loop_budget(budget: int | None = None) -> None:
    """Reset the per-loop credit counter. Caller invokes once per
    scanner-loop iteration before any fetch.

    Args:
        budget: Optional override for the loop ceiling. None uses the
            default (env var SHADOW_SPORTSBOOK_LOOP_BUDGET or 5).
    """
    global _credits_used_this_loop, LOOP_BUDGET_DEFAULT
    _credits_used_this_loop = 0
    if budget is not None and budget >= 0:
        LOOP_BUDGET_DEFAULT = budget
    else:
        env_val = os.environ.get("SHADOW_SPORTSBOOK_LOOP_BUDGET")
        if env_val:
            try:
                parsed = int(env_val)
                if parsed >= 0:
                    LOOP_BUDGET_DEFAULT = parsed
            except ValueError:
                pass


def loop_budget_remaining() -> int:
    return max(0, LOOP_BUDGET_DEFAULT - _credits_used_this_loop)


def _now_utc_iso() -> str:
    return datetime.now(UTC).isoformat()


def _today_yyyymmdd() -> str:
    return datetime.now(UTC).strftime("%Y%m%d")


def _default_http_get(url: str, *, timeout: float) -> tuple[dict | None, int, dict]:
    """Minimal HTTPS GET that returns (json_or_none, status, headers).

    Never raises.
    """
    try:
        import httpx
    except ImportError:
        log.warning("sportsbook_fetcher_httpx_missing")
        return None, 0, {}
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            resp = client.get(url, headers={"User-Agent": "project-kalshi-v5-shadow"})
            status = resp.status_code
            hdrs = {k.lower(): v for k, v in resp.headers.items()}
            if status != 200:
                return None, status, hdrs
            try:
                return resp.json(), status, hdrs
            except ValueError:
                return None, status, hdrs
    except Exception as exc:
        log.debug("sportsbook_http_get_error", extra={"url": url, "err": str(exc)})
        return None, 0, {}


def _persist_cache_row(
    ticker: str,
    implied: float | None,
    series_ticker: str,
    n_books: int,
) -> None:
    """Append one row to today's runtime cache parquet. Best-effort."""
    try:
        import pandas as pd
        RUNTIME_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path = RUNTIME_CACHE_DIR / f"sportsbook_{_today_yyyymmdd()}.parquet"
        row = {
            "ticker": ticker,
            "series_ticker": series_ticker,
            "sportsbook_implied": implied,
            "n_books": n_books,
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
        log.debug("sportsbook_cache_persist_error", extra={"err": str(exc)})


def _find_event_id(
    sport_key: str,
    target_home_name: str,
    target_away_name: str,
    *,
    timeout: float,
    http_get,
) -> str | None:
    """Hit the FREE /events endpoint to find the matching event_id by
    team-name pair. Returns None on miss; never raises.
    """
    api_key = os.environ.get("THE_ODDS_API_KEY", "")
    if not api_key:
        log.debug("sportsbook_fetcher_no_api_key")
        return None
    url = (
        f"{ODDS_API_BASE}/sports/{sport_key}/events"
        f"?apiKey={urllib.parse.quote(api_key)}"
    )
    body, status, _hdrs = http_get(url, timeout=timeout)
    if status != 200 or not isinstance(body, list):
        return None
    home_lower = (target_home_name or "").lower()
    away_lower = (target_away_name or "").lower()
    if not home_lower or not away_lower:
        return None
    for ev in body:
        if not isinstance(ev, dict):
            continue
        ev_home = (ev.get("home_team") or "").lower()
        ev_away = (ev.get("away_team") or "").lower()
        if ev_home == home_lower and ev_away == away_lower:
            return ev.get("id")
        if ev_home == away_lower and ev_away == home_lower:
            return ev.get("id")
    return None


def _fetch_odds_for_event(
    sport_key: str,
    event_id: str,
    *,
    timeout: float,
    http_get,
) -> dict | None:
    """Hit /v4/sports/{sport_key}/odds?eventIds=... (1 credit).

    Returns the first matching event dict on success, None otherwise.
    Caller MUST have already checked the loop budget.
    """
    api_key = os.environ.get("THE_ODDS_API_KEY", "")
    if not api_key:
        return None
    url = (
        f"{ODDS_API_BASE}/sports/{sport_key}/odds"
        f"?apiKey={urllib.parse.quote(api_key)}"
        f"&eventIds={urllib.parse.quote(event_id)}"
        f"&regions=us&markets=h2h&oddsFormat=decimal"
    )
    body, status, hdrs = http_get(url, timeout=timeout)
    if status != 200:
        return None
    # the-odds-api returns a list of events even when filtered by id.
    if isinstance(body, list):
        for ev in body:
            if isinstance(ev, dict) and ev.get("id") == event_id:
                return ev
        if body and isinstance(body[0], dict):
            return body[0]
    if isinstance(body, dict):
        return body
    return None


def _extract_implied(
    event: dict,
    target_team_name: str,
    build_mod,
) -> tuple[float | None, int]:
    """De-vig median implied probability for target_team across books.

    Delegates to the build script's extract_implied_for_team helper if
    available, falling back to a local implementation. Returns
    (implied_or_None, n_books).
    """
    if build_mod is not None and hasattr(build_mod, "extract_implied_for_team"):
        try:
            median, per_book = build_mod.extract_implied_for_team(
                event, target_team_name,
            )
            return median, len(per_book or [])
        except Exception as exc:
            log.debug("sportsbook_extract_via_build_error", extra={"err": str(exc)})
    # Local fallback (kept minimal because the build script is the
    # canonical implementation; this branch only protects against
    # ImportError in unusual environments).
    per_book: list[float] = []
    for bm in event.get("bookmakers") or []:
        for market in bm.get("markets") or []:
            if market.get("key") != "h2h":
                continue
            outcomes = market.get("outcomes") or []
            if len(outcomes) not in (2, 3):
                continue
            try:
                ps = [1.0 / float(o.get("price", 0) or 0) for o in outcomes]
            except (TypeError, ValueError, ZeroDivisionError):
                continue
            s = sum(ps)
            if s <= 0:
                continue
            ps_dv = [p / s for p in ps]
            names = [o.get("name", "") for o in outcomes]
            for nm, p in zip(names, ps_dv, strict=False):
                if nm == target_team_name or target_team_name.lower() in nm.lower():
                    per_book.append(p)
                    break
    if not per_book:
        return None, 0
    sorted_book = sorted(per_book)
    n = len(sorted_book)
    median = (
        sorted_book[n // 2]
        if n % 2 == 1
        else (sorted_book[n // 2 - 1] + sorted_book[n // 2]) / 2.0
    )
    return median, n


def fetch_sportsbook_implied(
    ticker: str,
    series_ticker: str,
    *,
    timeout: float = 3.0,
    _http_get=None,
) -> float | None:
    """Fetch the sportsbook de-vigged median implied probability for
    the matching event.

    Returns the implied probability in [0.0, 1.0] on success, or None
    on any failure (no match, network error, budget exhausted, parse
    error). NEVER raises.

    Args:
        ticker: Kalshi market ticker.
        series_ticker: Kalshi series ticker (e.g., 'KXMLBGAME').
        timeout: Per-HTTP-request timeout in seconds. Default 3.0s.
        _http_get: Optional injectable HTTP callable for tests. Defaults
            to a small httpx wrapper. Signature:
            `_http_get(url, *, timeout) -> (json_or_none, status, headers)`.

    Behavior:
        1. In-process TTL cache short-circuits repeats.
        2. Loads V5-A2's parsers from scripts/v5/build_sportsbook_lookup.py.
        3. Parses ticker into team codes + date; if parser unsupported,
           returns None.
        4. Resolves team codes to full team names via V5-A2's lookup
           tables.
        5. Calls FREE /events to find the event_id (no credit cost).
        6. If event found AND credit budget not exhausted, calls
           /odds?eventIds=... (1 credit) and computes the de-vigged
           median implied probability for the target team.
        7. Caches result. Increments credit counter only when a paid
           call was issued successfully.
    """
    global _credits_used_this_loop
    try:
        # In-process cache short-circuit.
        cache_hit = _inprocess_cache.get(ticker)
        now_epoch = time.time()
        if cache_hit is not None:
            cached_impl, cached_at = cache_hit
            if (now_epoch - cached_at) < _INPROCESS_CACHE_TTL_SEC:
                return cached_impl

        http_get = _http_get if _http_get is not None else _default_http_get
        build_mod = _load_build_script()
        if build_mod is None:
            # Cannot match without the lookup tables; abstain.
            _inprocess_cache[ticker] = (None, now_epoch)
            _persist_cache_row(ticker, None, series_ticker, 0)
            return None

        # 1) Map series to sport_key and parser.
        series_to_sportkey = getattr(build_mod, "SERIES_TO_SPORTKEY", {})
        series_parsers = getattr(build_mod, "SERIES_PARSERS", {})
        series_prefix = series_ticker or ticker.split("-", 1)[0]
        sport_key = series_to_sportkey.get(series_prefix)
        parser = series_parsers.get(series_prefix)
        if sport_key is None or parser is None:
            _inprocess_cache[ticker] = (None, now_epoch)
            _persist_cache_row(ticker, None, series_ticker, 0)
            return None

        # 2) Parse ticker.
        parsed = parser(ticker)
        if parsed is None:
            _inprocess_cache[ticker] = (None, now_epoch)
            _persist_cache_row(ticker, None, series_ticker, 0)
            return None

        # 3) Resolve target team name + opposing team name.
        kalshi_to_team_name = getattr(build_mod, "kalshi_to_team_name", None)
        if kalshi_to_team_name is None:
            _inprocess_cache[ticker] = (None, now_epoch)
            _persist_cache_row(ticker, None, series_ticker, 0)
            return None
        target_team_name = kalshi_to_team_name(parsed)
        if target_team_name is None:
            _inprocess_cache[ticker] = (None, now_epoch)
            _persist_cache_row(ticker, None, series_ticker, 0)
            return None

        # Resolve home/away names for event_id lookup. For game-h2h series
        # the parsed dict carries home_code/away_code; we resolve via the
        # league table.
        mlb_teams = getattr(build_mod, "MLB_TEAMS", {})
        nfl_teams = getattr(build_mod, "NFL_TEAMS", {})
        wc_countries = getattr(build_mod, "WC_COUNTRIES", {})
        if parsed.get("series") == "KXMLBGAME":
            home_full = mlb_teams.get(parsed.get("home_code", ""))
            away_full = mlb_teams.get(parsed.get("away_code", ""))
        elif parsed.get("series") == "KXNFLGAME":
            home_full = nfl_teams.get(parsed.get("home_code", ""))
            away_full = nfl_teams.get(parsed.get("away_code", ""))
        elif parsed.get("series") == "KXWCGAME":
            home_full = wc_countries.get(parsed.get("home_code", ""))
            away_full = wc_countries.get(parsed.get("away_code", ""))
        else:
            # UFC / Boxing: no deterministic home/away mapping; fall back
            # to fetching the cached lookup if any. For shadow-mode v1
            # we cleanly abstain.
            _inprocess_cache[ticker] = (None, now_epoch)
            _persist_cache_row(ticker, None, series_ticker, 0)
            return None
        if not home_full or not away_full:
            _inprocess_cache[ticker] = (None, now_epoch)
            _persist_cache_row(ticker, None, series_ticker, 0)
            return None

        # 4) FREE /events call to find event_id.
        event_id = _find_event_id(
            sport_key, home_full, away_full,
            timeout=timeout, http_get=http_get,
        )
        if event_id is None:
            # One retry on transient failure.
            time.sleep(0.2)
            event_id = _find_event_id(
                sport_key, home_full, away_full,
                timeout=timeout, http_get=http_get,
            )
        if event_id is None:
            _inprocess_cache[ticker] = (None, now_epoch)
            _persist_cache_row(ticker, None, series_ticker, 0)
            return None

        # 5) Credit budget check. If exhausted, abstain (return None).
        if _credits_used_this_loop >= LOOP_BUDGET_DEFAULT:
            log.debug(
                "sportsbook_fetcher_budget_exhausted",
                extra={"used": _credits_used_this_loop, "ticker": ticker},
            )
            _inprocess_cache[ticker] = (None, now_epoch)
            _persist_cache_row(ticker, None, series_ticker, 0)
            return None

        # 6) PAID /odds?eventIds=... call.
        event = _fetch_odds_for_event(
            sport_key, event_id,
            timeout=timeout, http_get=http_get,
        )
        # We increment the counter regardless of success because the
        # call was issued and a credit was consumed; one retry follows
        # only when no credits were consumed (no HTTP success indicator).
        _credits_used_this_loop += 1
        if event is None:
            _inprocess_cache[ticker] = (None, now_epoch)
            _persist_cache_row(ticker, None, series_ticker, 0)
            return None

        # 7) Extract de-vigged median.
        implied, n_books = _extract_implied(event, target_team_name, build_mod)
        if implied is None or n_books == 0:
            _inprocess_cache[ticker] = (None, now_epoch)
            _persist_cache_row(ticker, None, series_ticker, n_books)
            return None
        if implied < 0.0 or implied > 1.0:
            _inprocess_cache[ticker] = (None, now_epoch)
            _persist_cache_row(ticker, None, series_ticker, n_books)
            return None

        _inprocess_cache[ticker] = (implied, now_epoch)
        _persist_cache_row(ticker, implied, series_ticker, n_books)
        return implied
    except Exception as exc:
        # Last line of defense.
        log.warning("sportsbook_fetcher_unexpected", exc_info=exc)
        return None
