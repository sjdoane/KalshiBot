"""v14 Live Deployment Alerter for the MLB-night sportsbook lead-lag strategy.

Operator usage (recommended):

  PYTHONPATH=src .venv-kronos/Scripts/python.exe scripts/v14/live_alerter.py

When run, the script:
1. Pulls today's MLB games from the-odds-api (current snapshot AND a
   snapshot from approximately 3 hours ago via the historical endpoint).
2. For each game commencing in the next 1 to 3 hours (i.e., we are
   currently in the game's T-3h to T-1h execution window):
   - Computes delta_sportsbook = (current implied prob, home team) MINUS
     (3h-ago implied prob, home team), averaged across available bookmakers.
   - If `|delta_sportsbook| >= 0.006` (v14 X_THRESHOLD), fires an ALERT.
3. Matches the the-odds-api game to a Kalshi ticker via the v11 team_maps
   module. Prints alert with side (YES if delta > 0, NO if < 0), the
   Kalshi ticker, recommended max execution price.
4. Logs every fire to `data/v14/live_alerts.jsonl` with deduplication
   (same ticker + same trading day = no re-alert).

OPERATOR MANUAL STEP: place the order on Kalshi web UI within the next
60 minutes. Recommended limit BUY at the suggested max price.

Pre-registered kill conditions (operator-enforced):
- Drawdown > 20% of initial capital
- 5 consecutive losing trades
- 8 weeks of trial without verdict

Credit cost per run: ~30 the-odds-api credits per run (1 current + 1
historical snapshot for MLB). At 13,500 credits remaining, this is
sustainable for 450 runs (~daily for a season).
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pandas as pd
from dotenv import load_dotenv

sys.stdout.reconfigure(line_buffering=True)

BASE = Path("C:/Users/SamJD/OneDrive/Desktop/AI Projects/Project Kalshi")
load_dotenv(BASE / ".env")
sys.path.insert(0, str(BASE / "scripts" / "v11"))
from team_maps import MLB_MAP

KEY = os.environ.get("THE_ODDS_API_KEY")
if not KEY:
    print("ERROR: THE_ODDS_API_KEY not set in .env", file=sys.stderr)
    raise SystemExit(2)

DATA_V14 = BASE / "data" / "v14"
DATA_V14.mkdir(parents=True, exist_ok=True)
ALERTS_LOG = DATA_V14 / "live_alerts.jsonl"

# v14-locked parameters
X_THRESHOLD = 0.006  # 60 basis points (75th pct |delta_sb| MLB-night)
HAIRCUT = 0.0007  # from v13 Phase 2b
SPORT_KEY = "baseball_mlb"
LOOKBACK_HOURS = 3  # T-6h to T-3h sportsbook movement window
EXEC_WINDOW_MIN_H = 1.0  # only act in T-1h to T-3h pre-commence
EXEC_WINDOW_MAX_H = 3.0


# Build inverse MLB map: full team name to ticker abbreviation
MLB_TEAM_TO_ABBR: dict[str, str] = {}
for abbr, name in MLB_MAP.items():
    # First definition wins (some teams have multiple abbreviations; primary wins)
    if name not in MLB_TEAM_TO_ABBR:
        MLB_TEAM_TO_ABBR[name] = abbr


def fetch_current_odds(client: httpx.Client) -> dict:
    url = f"https://api.the-odds-api.com/v4/sports/{SPORT_KEY}/odds"
    params = {"apiKey": KEY, "regions": "us", "markets": "h2h", "oddsFormat": "decimal"}
    r = client.get(url, params=params, timeout=30.0)
    r.raise_for_status()
    return {
        "data": r.json(),
        "remaining": int(r.headers.get("x-requests-remaining", -1)),
    }


def fetch_historical_odds(client: httpx.Client, iso_time: str) -> dict:
    url = f"https://api.the-odds-api.com/v4/historical/sports/{SPORT_KEY}/odds"
    params = {
        "apiKey": KEY, "regions": "us", "markets": "h2h",
        "date": iso_time, "oddsFormat": "decimal",
    }
    r = client.get(url, params=params, timeout=30.0)
    r.raise_for_status()
    body = r.json()
    return {
        "body": body,
        "remaining": int(r.headers.get("x-requests-remaining", -1)),
    }


def normalize_two_way(p_h: float, p_a: float) -> tuple[float, float]:
    s = p_h + p_a
    if s <= 0:
        return float("nan"), float("nan")
    return p_h / s, p_a / s


def per_game_home_implied(game: dict) -> float | None:
    """Median of normalized home implied prob across bookmakers."""
    home = game.get("home_team")
    away = game.get("away_team")
    bks = game.get("bookmakers", []) or []
    home_imps: list[float] = []
    for bk in bks:
        for mk in bk.get("markets", []):
            if mk.get("key") != "h2h":
                continue
            outs = mk.get("outcomes", []) or []
            if len(outs) != 2:
                continue
            p_h = None
            p_a = None
            for o in outs:
                if o.get("name") == home:
                    p_h = 1.0 / float(o.get("price", 1e-9))
                elif o.get("name") == away:
                    p_a = 1.0 / float(o.get("price", 1e-9))
            if p_h is None or p_a is None:
                continue
            ph_n, _ = normalize_two_way(p_h, p_a)
            if ph_n > 0:
                home_imps.append(ph_n)
    if not home_imps:
        return None
    return float(pd.Series(home_imps).median())


def kalshi_ticker_from_game(game: dict) -> str | None:
    """Build the Kalshi ticker prefix for a game; returns the YES side
    ticker for the HOME team (operator can flip to NO if our side is away).

    Format: KXMLBGAME-{YY}{MMM}{DD}{TEAM1}{TEAM2}-{WINNER_ABBR}
    Convention from v11: TEAM1+TEAM2 are concatenated; order is alphabetical
    or based on Becker's convention. For the alerter we PRINT the team names
    and let the operator find the exact ticker on Kalshi (which is safer than
    auto-constructing a ticker that may not match Kalshi's exact convention).
    """
    home = game.get("home_team")
    away = game.get("away_team")
    home_abbr = MLB_TEAM_TO_ABBR.get(home, "?")
    away_abbr = MLB_TEAM_TO_ABBR.get(away, "?")
    commence = pd.Timestamp(game.get("commence_time")).tz_convert("UTC")
    yymmdd = commence.strftime("%y%b%d").upper()
    # Becker convention sometimes lists team1 first; we cannot determine order
    # from the API alone. Return BOTH possible prefixes for the operator to
    # match.
    p1 = f"KXMLBGAME-{yymmdd}{home_abbr}{away_abbr}"
    p2 = f"KXMLBGAME-{yymmdd}{away_abbr}{home_abbr}"
    return f"{p1}* OR {p2}*"


def already_alerted(game_id: str) -> bool:
    if not ALERTS_LOG.exists():
        return False
    today_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with ALERTS_LOG.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                row = json.loads(line)
            except Exception:
                continue
            if row.get("game_id") == game_id and row.get("trading_day") == today_iso:
                return True
    return False


def log_alert(row: dict) -> None:
    ALERTS_LOG.parent.mkdir(parents=True, exist_ok=True)
    with ALERTS_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, default=str) + "\n")


def main() -> int:
    now = datetime.now(timezone.utc)
    historical_target = now - timedelta(hours=LOOKBACK_HOURS)
    iso_hist = historical_target.strftime("%Y-%m-%dT%H:00:00Z")
    print(f"v14 Live Alerter (now UTC: {now.isoformat()})", flush=True)
    print(f"  Looking up sportsbook delta from {iso_hist} to now", flush=True)
    print(f"  X_THRESHOLD: {X_THRESHOLD:.4f} ({X_THRESHOLD * 10000:.0f} bps)", flush=True)
    print(f"  Execution window: T-{EXEC_WINDOW_MAX_H}h to T-{EXEC_WINDOW_MIN_H}h before commence", flush=True)

    with httpx.Client() as client:
        cur = fetch_current_odds(client)
        print(f"  Current snapshot games: {len(cur['data'])}; credits remaining: {cur['remaining']}", flush=True)
        hist = fetch_historical_odds(client, iso_hist)
        hist_games = hist["body"].get("data", [])
        print(f"  Historical snapshot games: {len(hist_games)}; credits remaining: {hist['remaining']}", flush=True)

    # Index historical games by id
    hist_by_id: dict[str, dict] = {g.get("id"): g for g in hist_games if g.get("id")}

    fires = []
    skipped_window = 0
    skipped_no_historical = 0
    skipped_dedup = 0
    for g in cur["data"]:
        gid = g.get("id")
        commence_str = g.get("commence_time")
        if not commence_str or not gid:
            continue
        commence = pd.Timestamp(commence_str).tz_convert("UTC").to_pydatetime()
        hours_to_commence = (commence - now).total_seconds() / 3600.0
        # Only act on games in the T-1h to T-3h pre-commence window
        if not (EXEC_WINDOW_MIN_H <= hours_to_commence <= EXEC_WINDOW_MAX_H):
            skipped_window += 1
            continue
        hist_g = hist_by_id.get(gid)
        if hist_g is None:
            skipped_no_historical += 1
            continue
        if already_alerted(gid):
            skipped_dedup += 1
            continue
        p_cur = per_game_home_implied(g)
        p_hist = per_game_home_implied(hist_g)
        if p_cur is None or p_hist is None:
            continue
        delta_sb_home = p_cur - p_hist
        if abs(delta_sb_home) < X_THRESHOLD:
            continue
        # Build alert
        side_home = "yes" if delta_sb_home > 0 else "no"
        # If side_home is YES, take HOME side YES contract; if NO, the home side losing means take AWAY side YES (or HOME NO).
        # For Kalshi: a market for "Home wins" with side=YES means buy YES on home market.
        # A "NO" alert means home is losing, so we BUY YES on the away-side market OR BUY NO on the home-side market.
        # We recommend BUY NO on home market for simplicity (one-sided trade).
        ticker_hint = kalshi_ticker_from_game(g)
        # Recommended exec price proxy: use current home implied as ~ mid
        if side_home == "yes":
            suggested_max = p_cur + HAIRCUT + 0.005  # mid + haircut + 0.5c safety
            kalshi_action = f"BUY YES on HOME ({g.get('home_team')}) at <= {suggested_max:.3f}"
        else:
            suggested_max = (1.0 - p_cur) + HAIRCUT + 0.005
            kalshi_action = f"BUY YES on AWAY ({g.get('away_team')}) at <= {suggested_max:.3f}"
        alert = {
            "alert_ts_utc": now.isoformat(),
            "trading_day": now.strftime("%Y-%m-%d"),
            "game_id": gid,
            "home_team": g.get("home_team"),
            "away_team": g.get("away_team"),
            "commence_time": commence_str,
            "hours_to_commence": round(hours_to_commence, 2),
            "p_home_current": round(p_cur, 4),
            "p_home_3h_ago": round(p_hist, 4),
            "delta_sportsbook_home": round(delta_sb_home, 4),
            "side_to_take": side_home.upper(),
            "kalshi_action": kalshi_action,
            "suggested_max_price": round(suggested_max, 4),
            "kalshi_ticker_hint": ticker_hint,
        }
        log_alert(alert)
        fires.append(alert)

    print(f"\n=== Alerter summary ===", flush=True)
    print(f"  Games skipped (outside T-1h/T-3h window): {skipped_window}", flush=True)
    print(f"  Games skipped (no historical match): {skipped_no_historical}", flush=True)
    print(f"  Games skipped (already alerted today): {skipped_dedup}", flush=True)
    print(f"  Fires: {len(fires)}", flush=True)
    if not fires:
        print("  No fires right now. Re-run in 30-60 minutes for next eligible game.", flush=True)
        return 0
    print(f"\n=== ALERTS ({len(fires)}) ===", flush=True)
    for a in fires:
        print(f"\n  {a['home_team']} vs {a['away_team']}", flush=True)
        print(f"    commence: {a['commence_time']} ({a['hours_to_commence']}h away)", flush=True)
        print(f"    sportsbook (home): {a['p_home_3h_ago']:.3f} -> {a['p_home_current']:.3f} (delta {a['delta_sportsbook_home']:+.4f})", flush=True)
        print(f"    ACTION: {a['kalshi_action']}", flush=True)
        print(f"    Kalshi ticker hint: {a['kalshi_ticker_hint']}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
