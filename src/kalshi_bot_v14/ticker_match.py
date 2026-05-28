"""v14 ticker matching: sportsbook game -> Kalshi ticker.

Critical safety module. v14 daemon places real orders on real Kalshi
tickers; a wrong match means we trade the wrong team's market. This
module queries Kalshi /markets directly and matches by (date, team
abbreviation pair), returning the verified ticker for the side we want.

Behavior contract:
- Returns None on ANY ambiguity. Daemon SKIPS the fire on None.
- Never constructs a ticker without confirming Kalshi has it open.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path  # noqa: F401

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts" / "v11"))
from team_maps import MLB_MAP, split_team_abbrs


# Inverse map: full team name -> ALL valid ticker abbreviations.
# Kalshi has changed conventions over time (e.g., OAK vs ATH for the
# Athletics; ARI vs AZ for the Diamondbacks). Match must try all.
_MLB_ALL_ABBRS: dict[str, list[str]] = {}
for abbr, name in MLB_MAP.items():
    _MLB_ALL_ABBRS.setdefault(name, []).append(abbr)


def team_to_abbrs(team_full_name: str) -> list[str]:
    """Return all valid Kalshi ticker abbreviations for the team."""
    return list(_MLB_ALL_ABBRS.get(team_full_name, []))


def team_to_abbr(team_full_name: str) -> str | None:
    """Return the primary (first listed) abbreviation. Use team_to_abbrs
    for full matching.
    """
    abbrs = _MLB_ALL_ABBRS.get(team_full_name, [])
    return abbrs[0] if abbrs else None


def _parse_ticker_teams(ticker: str) -> tuple[str, str, str] | None:
    """Parse a KXMLBGAME ticker into (team1_abbr, team2_abbr, winner_abbr).

    Two formats observed:
    - Historical (Becker): KXMLBGAME-{YYMMMDD}{TEAM1}{TEAM2}-{WINNER}
      example: KXMLBGAME-25JUL12ARILAA-LAA
    - Current Kalshi: KXMLBGAME-{YYMMMDD}{HHMM}{TEAM1}{TEAM2}-{WINNER}
      example: KXMLBGAME-26MAY301610MILHOU-MIL

    The HHMM is 4 digits inserted after the date. Detect by checking
    whether the first 4 chars after the date are digits.
    """
    prefix = "KXMLBGAME-"
    if not ticker.startswith(prefix):
        return None
    rest = ticker[len(prefix):]
    if "-" not in rest:
        return None
    before_dash, winner = rest.rsplit("-", 1)
    if len(before_dash) < 7:
        return None
    after_date = before_dash[7:]
    # Strip 4-digit HHMM time prefix if present
    if len(after_date) >= 4 and after_date[:4].isdigit():
        teams_str = after_date[4:]
    else:
        teams_str = after_date
    split = split_team_abbrs(teams_str, "KXMLBGAME")
    if split is None:
        return None
    return split[0], split[1], winner


def _ticker_target_datetime(ticker: str, et_offset_hours: int = -4) -> datetime | None:
    """Reconstruct the ticker's commence-time approximate UTC datetime.

    Kalshi tickers embed local ET date+time as `{YYMMMDD}{HHMM}`. We
    convert to UTC by adding 4 hours (EDT) or 5 hours (EST). MLB
    regular season is mostly EDT (March-November); we default to EDT
    here. The caller compares against commence_dt with a tolerance.
    """
    prefix = "KXMLBGAME-"
    if not ticker.startswith(prefix):
        return None
    rest = ticker[len(prefix):]
    if "-" not in rest:
        return None
    before_dash, _ = rest.rsplit("-", 1)
    if len(before_dash) < 11:
        return None
    yy, mmm, dd = before_dash[0:2], before_dash[2:5], before_dash[5:7]
    if not before_dash[7:11].isdigit():
        return None
    hh, mn = before_dash[7:9], before_dash[9:11]
    months = {
        "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
        "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
    }
    if mmm not in months:
        return None
    try:
        local_dt = datetime(2000 + int(yy), months[mmm], int(dd), int(hh), int(mn))
    except ValueError:
        return None
    # ET to UTC: add 4 (EDT) hours
    return (local_dt - timedelta(hours=et_offset_hours)).replace(tzinfo=timezone.utc)


def find_kalshi_ticker_for_side(
    kalshi_open_markets: list[dict],
    home_team: str,
    away_team: str,
    commence_dt: datetime,
    take_home_side: bool,
    *,
    time_tolerance_minutes: int = 90,
) -> str | None:
    """Find the exact Kalshi ticker to BUY YES on, given the sportsbook game.

    Disambiguates by commence-time proximity when the same teams play on
    consecutive days. Returns the matching ticker whose embedded
    timestamp is closest to commence_dt within `time_tolerance_minutes`.

    Returns None if zero candidates match within tolerance.
    """
    home_abbrs = team_to_abbrs(home_team)
    away_abbrs = team_to_abbrs(away_team)
    if not home_abbrs or not away_abbrs:
        return None

    tolerance = timedelta(minutes=time_tolerance_minutes)
    best: tuple[timedelta, str] | None = None

    for m in kalshi_open_markets:
        ticker = m.get("ticker", "")
        if not ticker.startswith("KXMLBGAME-"):
            continue
        parsed = _parse_ticker_teams(ticker)
        if parsed is None:
            continue
        t1, t2, winner = parsed
        pair_ok = (
            (t1 in home_abbrs and t2 in away_abbrs)
            or (t2 in home_abbrs and t1 in away_abbrs)
        )
        if not pair_ok:
            continue
        if take_home_side:
            if winner not in home_abbrs:
                continue
        else:
            if winner not in away_abbrs:
                continue
        # Compute embedded ticker time and check tolerance
        target_utc = _ticker_target_datetime(ticker)
        if target_utc is None:
            # Old-format ticker without HHMM; can't disambiguate, skip
            continue
        diff = abs(target_utc - commence_dt)
        if diff > tolerance:
            continue
        if best is None or diff < best[0]:
            best = (diff, ticker)

    return best[1] if best else None
