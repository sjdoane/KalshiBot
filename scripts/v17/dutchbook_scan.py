"""Kalshi dutch-book / no-arbitrage scan (read-only).

Sweeps every OPEN, mutually-exclusive Kalshi event group for a risk-free lock:
- UNDERROUND: buy YES on all outcomes when the asks sum below 1.
- OVERROUND: buy NO on all outcomes (profit = (N-1) - sum(no_ask)).

Both are computed net of the per-leg Kalshi taker fee and require a top-of-book
quote on EVERY leg (an incomplete basket cannot be locked). Reports candidates
with their margin, leg count, minimum bindable depth, days-to-resolution, and
risk-free annualized return. Places NO orders.

Pre-registered candidate gate (locked before this run): a candidate is a
mutually-exclusive, all-active event whose underround OR overround net margin is
> +$0.01 per basket AND whose minimum top-of-book depth is >= 1 contract on
every needed leg. UNDERROUND candidates additionally require MANUAL
exhaustiveness verification (the listed outcomes must cover every possibility);
OVERROUND is robust to a missing outcome. KILL/NULL if zero candidates: the
dutch-book edge does not exist on current open Kalshi events. Any candidate
still needs a depth-aware multi-leg execution check (prices/size move during an
N-leg fill) before risking capital.

  PYTHONPATH=src .venv-kronos\\Scripts\\python.exe scripts\\v17\\dutchbook_scan.py
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

BASE = Path("C:/Users/SamJD/OneDrive/Desktop/AI Projects/Project Kalshi")
sys.path.insert(0, str(BASE / "src"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(BASE / ".env")

from kalshi_bot.analysis.dutchbook import (  # noqa: E402
    analyze_group,
    annualized_return,
    parse_market_quote,
)
from kalshi_bot.config import Settings  # noqa: E402
from kalshi_bot.data.kalshi_client import KalshiClient  # noqa: E402

MIN_NET = 0.01  # dollars per basket, after all-leg fees
MIN_DEPTH = 1.0  # contracts at top of book on every needed leg
OUT_DIR = BASE / "data" / "v17"
OUT_DIR.mkdir(parents=True, exist_ok=True)
REPORT_PATH = OUT_DIR / "dutchbook_scan.json"


def iter_events(kc: KalshiClient):
    cursor = ""
    for _ in range(80):
        params: dict = {"status": "open", "with_nested_markets": "true", "limit": 200}
        if cursor:
            params["cursor"] = cursor
        resp = kc.get("/events", **params)
        events = resp.get("events", []) or []
        yield from events
        cursor = resp.get("cursor") or ""
        if not cursor or not events:
            break


def days_to_close(markets: list[dict], now: datetime) -> float | None:
    times: list[datetime] = []
    for m in markets:
        cs = m.get("close_time") or m.get("expiration_time") or ""
        if not cs:
            continue
        try:
            dt = datetime.fromisoformat(str(cs).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            continue
        times.append(dt)
    if not times:
        return None
    return (max(times) - now).total_seconds() / 86400.0


def main() -> int:
    now = datetime.now(UTC)
    settings = Settings()
    n_events = 0
    n_mutex = 0
    n_complete = 0  # all-active with at least one computable lock
    candidates: list[dict] = []
    with KalshiClient(settings) as kc:
        for e in iter_events(kc):
            n_events += 1
            if not e.get("mutually_exclusive"):
                continue
            markets = e.get("markets", []) or []
            if len(markets) < 2:
                continue
            # Require every leg tradeable (active); a settled/closed leg breaks
            # both the basket and exhaustiveness.
            if not all((m.get("status") or "").lower() == "active" for m in markets):
                continue
            n_mutex += 1
            quotes = [parse_market_quote(m) for m in markets]
            res = analyze_group(quotes)
            if res["underround"] is None and res["overround"] is None:
                continue
            n_complete += 1
            dtc = days_to_close(markets, now)
            for kind in ("underround", "overround"):
                lock = res[kind]
                if lock is None:
                    continue
                if lock["net_margin"] <= MIN_NET or lock["min_depth"] < MIN_DEPTH:
                    continue
                ann = (
                    annualized_return(lock["net_margin"], lock["cost"], dtc)
                    if dtc is not None else None
                )
                candidates.append({
                    "event_ticker": e.get("event_ticker"),
                    "title": (e.get("title") or "")[:80],
                    "kind": kind,
                    "n_outcomes": res["n"],
                    "net_margin": lock["net_margin"],
                    "gross_margin": lock["gross_margin"],
                    "total_fee": lock["total_fee"],
                    "cost": lock["cost"],
                    "min_depth": lock["min_depth"],
                    "days_to_close": round(dtc, 1) if dtc is not None else None,
                    "annualized_return": round(ann, 4) if ann is not None else None,
                    "needs_exhaustiveness_check": kind == "underround",
                })

    candidates.sort(key=lambda c: c["net_margin"], reverse=True)
    report = {
        "scanned_ts": now.isoformat(),
        "n_events": n_events, "n_mutually_exclusive_all_active": n_mutex,
        "n_with_computable_lock": n_complete, "n_candidates": len(candidates),
        "gate": {"min_net_margin": MIN_NET, "min_depth": MIN_DEPTH},
        "candidates": candidates,
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    print(f"events scanned: {n_events}")
    print(f"mutually-exclusive + all-active (>=2 legs): {n_mutex}")
    print(f"  with a computable lock (full book on all legs): {n_complete}")
    # An UNDERROUND lock is only plausibly real if the listed outcomes cover
    # the probability space (basket cost near 1). A low cost means the group is
    # non-exhaustive: buying it cheaply is a longshot bet, not a lock. We treat
    # cost >= COVERAGE_FLOOR as "plausibly exhaustive" (still needs a manual
    # rules check); below that it is a non-exhaustive phantom.
    coverage_floor = 0.90
    overround = [c for c in candidates if c["kind"] == "overround"]
    under = [c for c in candidates if c["kind"] == "underround"]
    under_covered = [c for c in under if c["cost"] >= coverage_floor]
    under_phantom = [c for c in under if c["cost"] < coverage_floor]
    print(f"CANDIDATES (net > ${MIN_NET}, depth >= {MIN_DEPTH}): {len(candidates)}")
    print(
        f"  overround (robust): {len(overround)} | underround cost>={coverage_floor} "
        f"(plausibly exhaustive): {len(under_covered)} | underround low-coverage "
        f"phantom: {len(under_phantom)}"
    )
    for c in candidates[:25]:
        flag = " [VERIFY-EXHAUSTIVE]" if c["needs_exhaustiveness_check"] else ""
        ann = f"{c['annualized_return']:+.1%}" if c["annualized_return"] is not None else "n/a"
        cov = "" if c["kind"] == "overround" else (
            " PHANTOM(low-coverage)" if c["cost"] < coverage_floor else " cost~1"
        )
        print(
            f"  {c['kind']:10s} {c['event_ticker']:24s} N={c['n_outcomes']:>3} "
            f"net=${c['net_margin']:+.3f} cost=${c['cost']:.3f} depth={c['min_depth']:.0f} "
            f"days={c['days_to_close']} ann={ann}{flag}{cov}"
        )
    report["n_overround"] = len(overround)
    report["n_underround_covered"] = len(under_covered)
    report["n_underround_phantom"] = len(under_phantom)
    REPORT_PATH.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"\nwrote {REPORT_PATH}")
    if not overround and not under_covered:
        print(
            "\nVERDICT: NULL for risk-free arb. Zero overround (buy-all-NO) locks, "
            "and every underround signal is a non-exhaustive phantom (cost far "
            "below 1). Market makers arb the genuinely-exhaustive groups to ~1."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
