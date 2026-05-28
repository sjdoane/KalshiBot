"""Build joined MLB Kalshi + Stats API dataset for v2 research.

One row per KXMLBGAME market (one per game; favorite side only). Features
computed AS OF the day before the game (no look-ahead).

Run as:
    uv run python -m scripts.v2.build_mlb_dataset \
        --start 2025-03-01 --end 2026-03-24

Output: data/v2/joined_mlb_dataset.parquet

Methodology note (read research/v2/03-dataset-build.md for full context):

The brief specified a [-42d, -28d] trading window before market close.
For KXMLBGAME markets, observed lifetime is overwhelmingly < 1 day
(median 0.58 days), so that window does not exist. We pivoted to use
the PRE-GAME trading window: [open_time, game_start_utc]. The
favorite_price is the VWAP yes-price over that window only. Critical:
we do NOT include in-game trades because they discover the actual
outcome and would bias the favorite-identification toward the eventual
winner. The MLB Stats API gameDate field provides the game start time.

The lifetime [30, 180] filter from v1 was also dropped for the same
reason; if applied, the dataset would contain ~3 games. Per the brief:
"for MLB game markets, lifetime is typically shorter... most are <60
days". The actual reality is even tighter than the brief anticipated.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pandas as pd
import structlog

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from kalshi_bot.config import Settings  # noqa: E402
from kalshi_bot.data.kalshi_client import KalshiClient, KalshiHTTPError  # noqa: E402
from kalshi_bot.logging import configure_logging  # noqa: E402

OUT_DIR = REPO_ROOT / "data" / "v2"
OUT_PATH = OUT_DIR / "joined_mlb_dataset.parquet"
DROPPED_PATH = OUT_DIR / "joined_mlb_dataset_dropped.parquet"

TICKER_PREFIX = "KXMLBGAME-"
DATE_REGEX = re.compile(r"^(\d{2})([A-Z]{3})(\d{2})$")
MONTH_MAP = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}
# Pseudo-team codes that appear in playoff placeholder markets ("AL vs AL
# (Game 1) Winner?") before the matchup is set. We drop these.
PLACEHOLDER_TEAM_CODES = {"ALHS", "ALLS", "NLHS", "NLLS"}

# Kalshi-side abbreviation aliases that need normalization to match the MLB
# Stats API's `abbreviation` field. Discovered from no_mlb_match audit on
# the 2025 season: ARI used by Kalshi for some Arizona games where MLB uses
# AZ. Map all Kalshi-side variants to the MLB-side canonical.
TEAM_ABBREV_ALIASES = {
    "ARI": "AZ",  # Arizona Diamondbacks
}

# Strategy-B eligibility band (matches v1 favorite-maker gate)
FAVORITE_PRICE_LOW = 0.70
FAVORITE_PRICE_HIGH = 0.95

# Trading-window-mid is interpreted for game markets as "the day BEFORE
# the game's close_time, EOD UTC". We compute team features as of that
# instant using prior-season games only. No look-ahead.
FEATURES_CUTOFF_OFFSET_DAYS = 1

# Window for trade VWAP: from open_time to close_time - this many seconds
TRADE_WINDOW_END_OFFSET_SECONDS = 30 * 60  # 30 minutes before close

# Minimum trades during the VWAP window to keep the market
MIN_TRADES_IN_WINDOW = 5


def parse_ticker(ticker: str) -> dict[str, Any] | None:
    """Parse a KXMLBGAME ticker into date + away + home + contract team.

    Returns None on parse failure. Format observed:
        KXMLBGAME-{YYMMMDD}{AWAY}{HOME}[G1|G2|2]-{TEAM}
    where MMM is a 3-letter uppercase month code.
    """
    if not ticker.startswith(TICKER_PREFIX):
        return None
    rest = ticker[len(TICKER_PREFIX):]
    if "-" not in rest:
        return None
    pair_part, contract_team = rest.rsplit("-", 1)
    if len(pair_part) < 7:
        return None
    date_part = pair_part[:7]
    m = DATE_REGEX.match(date_part)
    if not m:
        return None
    yy, mon, dd = m.groups()
    mon_num = MONTH_MAP.get(mon)
    if mon_num is None:
        return None
    year = 2000 + int(yy)
    try:
        game_date = datetime(year, mon_num, int(dd), tzinfo=UTC).date()
    except ValueError:
        return None
    teams_dh = pair_part[7:]
    dh = None
    if teams_dh.endswith("G1"):
        dh, teams_dh = "G1", teams_dh[:-2]
    elif teams_dh.endswith("G2"):
        dh, teams_dh = "G2", teams_dh[:-2]
    elif teams_dh.endswith("2") and len(teams_dh) > 2:
        # Bare trailing 2 used for early-season doubleheaders. Only treat as
        # DH suffix if removing it still leaves enough chars for two team codes.
        dh, teams_dh = "2", teams_dh[:-1]
    if teams_dh.startswith(contract_team):
        away = contract_team
        home = teams_dh[len(contract_team):]
    elif teams_dh.endswith(contract_team):
        home = contract_team
        away = teams_dh[: -len(contract_team)]
    else:
        return None
    return {
        "game_date": game_date,
        "away": away,
        "home": home,
        "contract_team": contract_team,
        "dh_suffix": dh,
    }


def pull_kalshi_markets(client: KalshiClient, start_ts: int, end_ts: int,
                        log: structlog.BoundLogger) -> pd.DataFrame:
    """Pull all KXMLBGAME historical markets in the given timestamp window."""
    log.info("kalshi_pull_start", start_ts=start_ts, end_ts=end_ts)
    t0 = time.time()
    rows: list[dict[str, Any]] = []
    for m in client.paginate(
        "/historical/markets", item_key="markets", limit=100,
        series_ticker="KXMLBGAME", min_close_ts=start_ts, max_close_ts=end_ts,
    ):
        rows.append(m)
    log.info("kalshi_pull_done", rows=len(rows), seconds=round(time.time() - t0, 1))
    return pd.DataFrame(rows)


def pull_trades_for_market(client: KalshiClient, ticker: str,
                           open_ts: int, end_ts: int) -> list[dict[str, Any]]:
    """Pull trades for one ticker between open_ts and end_ts (unix seconds)."""
    try:
        return list(client.paginate(
            "/historical/trades", item_key="trades", limit=1000,
            ticker=ticker, min_ts=open_ts, max_ts=end_ts,
        ))
    except KalshiHTTPError:
        # 404 here would be surprising but we tolerate it; return empty
        return []


def vwap_from_trades(trades: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute VWAP, trade counts, and one-sided flow over a trade list."""
    if not trades:
        return {
            "vwap_yes": None, "n_trades": 0, "volume_fp": 0.0,
            "one_sided_flow_pct": None,
        }
    total_size = 0.0
    weighted_yes = 0.0
    yes_takers = 0
    no_takers = 0
    for t in trades:
        try:
            yes_price = float(t["yes_price_dollars"])
            size = float(t["count_fp"])
        except (KeyError, TypeError, ValueError):
            continue
        if size <= 0:
            continue
        weighted_yes += yes_price * size
        total_size += size
        side = (t.get("taker_side") or "").lower()
        if side == "yes":
            yes_takers += 1
        elif side == "no":
            no_takers += 1
    if total_size <= 0:
        return {
            "vwap_yes": None, "n_trades": len(trades), "volume_fp": 0.0,
            "one_sided_flow_pct": None,
        }
    total_takers = yes_takers + no_takers
    one_sided = (
        max(yes_takers, no_takers) / total_takers if total_takers > 0 else None
    )
    return {
        "vwap_yes": weighted_yes / total_size,
        "n_trades": len(trades),
        "volume_fp": total_size,
        "one_sided_flow_pct": one_sided,
    }


def pull_mlb_schedule(http: httpx.Client, start_date: str, end_date: str,
                      log: structlog.BoundLogger) -> pd.DataFrame:
    """Pull MLB schedule via Stats API for a range of dates."""
    log.info("mlb_pull_start", start=start_date, end=end_date)
    t0 = time.time()
    url = "https://statsapi.mlb.com/api/v1/schedule"
    params = {
        "sportId": 1,
        "startDate": start_date,
        "endDate": end_date,
        "gameType": "R,F,D,L,W",  # Regular + Wild Card + Division + LCS + WS
        "hydrate": "team,linescore",
    }
    r = http.get(url, params=params, timeout=120.0)
    r.raise_for_status()
    j = r.json()
    rows = []
    for d in j.get("dates", []):
        for g in d.get("games", []):
            home = g.get("teams", {}).get("home", {})
            away = g.get("teams", {}).get("away", {})
            home_team = home.get("team", {})
            away_team = away.get("team", {})
            rows.append({
                "game_pk": g.get("gamePk"),
                "game_date": d.get("date"),
                "game_type": g.get("gameType"),
                "status": g.get("status", {}).get("detailedState"),
                "double_header": g.get("doubleHeader"),
                "game_number": g.get("gameNumber"),
                "home_abbrev": home_team.get("abbreviation"),
                "home_id": home_team.get("id"),
                "home_name": home_team.get("name"),
                "home_score": home.get("score"),
                "home_is_winner": home.get("isWinner"),
                "away_abbrev": away_team.get("abbreviation"),
                "away_id": away_team.get("id"),
                "away_name": away_team.get("name"),
                "away_score": away.get("score"),
                "away_is_winner": away.get("isWinner"),
                "game_datetime_utc": g.get("gameDate"),
            })
    df = pd.DataFrame(rows)
    log.info("mlb_pull_done", rows=len(df), seconds=round(time.time() - t0, 1))
    return df


def match_game(kalshi_row: dict, mlb_df: pd.DataFrame) -> dict | None:
    """Find the MLB game matching a Kalshi market.

    Match keys: game_date, {home, away}, dh_suffix. Kalshi-side abbreviations
    are normalized via TEAM_ABBREV_ALIASES to align with MLB API's canonical
    `abbreviation` field (e.g., Kalshi "ARI" -> MLB "AZ").
    """
    parsed = kalshi_row["parsed"]
    if parsed is None:
        return None
    away = TEAM_ABBREV_ALIASES.get(parsed["away"], parsed["away"])
    home = TEAM_ABBREV_ALIASES.get(parsed["home"], parsed["home"])
    dh = parsed["dh_suffix"]
    target_date = parsed["game_date"]
    # MLB game_date is ISO YYYY-MM-DD as a string. Filter narrowly.
    date_str = target_date.strftime("%Y-%m-%d")
    cand = mlb_df[
        (mlb_df["game_date"] == date_str)
        & (mlb_df["home_abbrev"] == home)
        & (mlb_df["away_abbrev"] == away)
    ]
    if cand.empty:
        return None
    if dh in ("G1", None):
        target_game_number = 1
    elif dh in ("G2", "2"):
        target_game_number = 2
    else:
        target_game_number = 1
    # Pick the game with matching game_number; fall back to first
    matches = cand[cand["game_number"] == target_game_number]
    if matches.empty:
        matches = cand
    return matches.iloc[0].to_dict()


def compute_team_features(games: pd.DataFrame, team: str, cutoff_date: dt.date,
                          season_start: dt.date) -> dict[str, Any]:
    """Compute team-level features as of cutoff_date (inclusive of games BEFORE
    cutoff; cutoff itself excluded to avoid look-ahead).

    games is the MLB schedule for the season (filtered to gameType R for these
    stats; postseason has its own dynamics but we use R only for the
    base-rate features).
    """
    # Filter to this team's games in [season_start, cutoff_date) that are Final
    mask = (
        ((games["home_abbrev"] == team) | (games["away_abbrev"] == team))
        & (games["status"] == "Final")
        & (games["game_date_obj"] >= season_start)
        & (games["game_date_obj"] < cutoff_date)
        & (games["game_type"] == "R")  # Regular season only for base rates
    )
    prior = games.loc[mask].sort_values("game_date_obj")
    n = len(prior)
    if n == 0:
        return {
            "games_played": 0,
            "wins": 0,
            "losses": 0,
            "win_pct": None,
            "runs_scored_per_game": None,
            "runs_allowed_per_game": None,
            "run_diff_per_game": None,
            "pyth_expected_wpct": None,
            "recent_form_wpct": None,
            "home_wpct": None,
            "away_wpct": None,
            "last_game_date": None,
        }
    wins = 0
    losses = 0
    rs_total = 0.0
    ra_total = 0.0
    home_w, home_n = 0, 0
    away_w, away_n = 0, 0
    last10_w, last10_n = 0, 0
    last_game_date = None
    # Walk through games in order, mark wins/losses for this team
    records: list[tuple[dt.date, bool, bool, float, float]] = []
    for _, g in prior.iterrows():
        is_home = g["home_abbrev"] == team
        team_score = g["home_score"] if is_home else g["away_score"]
        opp_score = g["away_score"] if is_home else g["home_score"]
        if team_score is None or opp_score is None:
            continue
        if pd.isna(team_score) or pd.isna(opp_score):
            continue
        team_score = float(team_score)
        opp_score = float(opp_score)
        won = team_score > opp_score
        if won:
            wins += 1
        else:
            losses += 1
        rs_total += team_score
        ra_total += opp_score
        if is_home:
            home_n += 1
            if won:
                home_w += 1
        else:
            away_n += 1
            if won:
                away_w += 1
        records.append((g["game_date_obj"], is_home, won, team_score, opp_score))
        last_game_date = g["game_date_obj"]
    games_played = wins + losses
    if games_played == 0:
        return {
            "games_played": 0,
            "wins": 0,
            "losses": 0,
            "win_pct": None,
            "runs_scored_per_game": None,
            "runs_allowed_per_game": None,
            "run_diff_per_game": None,
            "pyth_expected_wpct": None,
            "recent_form_wpct": None,
            "home_wpct": None,
            "away_wpct": None,
            "last_game_date": None,
        }
    win_pct = wins / games_played
    rs_pg = rs_total / games_played
    ra_pg = ra_total / games_played
    # Pythagorean expectation (James, 1.83 exponent)
    if rs_pg > 0 or ra_pg > 0:
        rs_p = rs_pg ** 1.83
        ra_p = ra_pg ** 1.83
        pyth = rs_p / (rs_p + ra_p) if (rs_p + ra_p) > 0 else None
    else:
        pyth = None
    # Recent form: last 10 games
    last_10 = records[-10:]
    if last_10:
        last10_w = sum(1 for r in last_10 if r[2])
        last10_n = len(last_10)
        recent_wpct = last10_w / last10_n
    else:
        recent_wpct = None
    home_wpct = (home_w / home_n) if home_n > 0 else None
    away_wpct = (away_w / away_n) if away_n > 0 else None
    return {
        "games_played": int(games_played),
        "wins": int(wins),
        "losses": int(losses),
        "win_pct": float(win_pct),
        "runs_scored_per_game": float(rs_pg),
        "runs_allowed_per_game": float(ra_pg),
        "run_diff_per_game": float(rs_pg - ra_pg),
        "pyth_expected_wpct": float(pyth) if pyth is not None else None,
        "recent_form_wpct": float(recent_wpct) if recent_wpct is not None else None,
        "home_wpct": float(home_wpct) if home_wpct is not None else None,
        "away_wpct": float(away_wpct) if away_wpct is not None else None,
        "last_game_date": last_game_date,
    }


def compute_h2h_wpct(games: pd.DataFrame, team_a: str, team_b: str,
                     cutoff_date: dt.date,
                     season_start: dt.date) -> tuple[float | None, int]:
    """Return (team_a's win pct vs team_b this season prior to cutoff, n_prior).

    Counts only games where both teams played each other. Regular season only.
    """
    mask = (
        (
            ((games["home_abbrev"] == team_a) & (games["away_abbrev"] == team_b))
            | ((games["home_abbrev"] == team_b) & (games["away_abbrev"] == team_a))
        )
        & (games["status"] == "Final")
        & (games["game_date_obj"] >= season_start)
        & (games["game_date_obj"] < cutoff_date)
        & (games["game_type"] == "R")
    )
    matchups = games.loc[mask]
    if matchups.empty:
        return None, 0
    wins_a = 0
    total = 0
    for _, g in matchups.iterrows():
        if g["home_score"] is None or g["away_score"] is None:
            continue
        if pd.isna(g["home_score"]) or pd.isna(g["away_score"]):
            continue
        if g["home_abbrev"] == team_a:
            won = g["home_score"] > g["away_score"]
        else:
            won = g["away_score"] > g["home_score"]
        if won:
            wins_a += 1
        total += 1
    if total == 0:
        return None, 0
    return wins_a / total, total


def compute_features_for_pair(games: pd.DataFrame, favorite: str, underdog: str,
                              favorite_is_home: bool, game_date: dt.date,
                              season_start: dt.date) -> dict[str, Any]:
    """Compute the full feature row for a (favorite, underdog) pair as of
    game_date - 1 day (so the cutoff excludes game_date itself).
    """
    cutoff = game_date  # cutoff is the game_date; all games WITH game_date_obj
                         # < cutoff are eligible. This is "as of the night before".
    fav_feat = compute_team_features(games, favorite, cutoff, season_start)
    dog_feat = compute_team_features(games, underdog, cutoff, season_start)
    h2h_wpct, h2h_n = compute_h2h_wpct(games, favorite, underdog, cutoff, season_start)
    # days_rest for favorite
    if fav_feat["last_game_date"] is not None:
        days_rest = (game_date - fav_feat["last_game_date"]).days
    else:
        days_rest = None
    # vs .500+ teams: compute "above .500 list" as of cutoff using all teams' wpct
    # For simplicity we compute fav's record vs teams whose own win pct at this
    # cutoff is >= 0.500.
    teams = pd.unique(pd.concat([games["home_abbrev"], games["away_abbrev"]]))
    # Build a quick wpct lookup for every team as of cutoff
    wpct_map: dict[str, float | None] = {}
    for t in teams:
        if not isinstance(t, str):
            continue
        feat_t = compute_team_features(games, t, cutoff, season_start)
        wpct_map[t] = feat_t["win_pct"]
    above_500 = {t for t, p in wpct_map.items() if p is not None and p >= 0.500}
    # Now fav's record vs above_500 teams
    mask = (
        ((games["home_abbrev"] == favorite) | (games["away_abbrev"] == favorite))
        & (games["status"] == "Final")
        & (games["game_date_obj"] >= season_start)
        & (games["game_date_obj"] < cutoff)
        & (games["game_type"] == "R")
    )
    prior = games.loc[mask]
    n_500 = 0
    w_500 = 0
    for _, g in prior.iterrows():
        opp = g["away_abbrev"] if g["home_abbrev"] == favorite else g["home_abbrev"]
        if opp not in above_500:
            continue
        is_home = g["home_abbrev"] == favorite
        ts = g["home_score"] if is_home else g["away_score"]
        os_ = g["away_score"] if is_home else g["home_score"]
        if ts is None or os_ is None:
            continue
        n_500 += 1
        if float(ts) > float(os_):
            w_500 += 1
    vs_500_wpct = (w_500 / n_500) if n_500 > 0 else None
    return {
        # Favorite team features
        "fav_games_played": fav_feat["games_played"],
        "fav_win_pct": fav_feat["win_pct"],
        "fav_runs_scored_pg": fav_feat["runs_scored_per_game"],
        "fav_runs_allowed_pg": fav_feat["runs_allowed_per_game"],
        "fav_run_diff_pg": fav_feat["run_diff_per_game"],
        "fav_pyth_wpct": fav_feat["pyth_expected_wpct"],
        "fav_recent_form_wpct": fav_feat["recent_form_wpct"],
        "fav_home_wpct": fav_feat["home_wpct"],
        "fav_away_wpct": fav_feat["away_wpct"],
        "fav_vs_500_wpct": vs_500_wpct,
        # Underdog features
        "dog_games_played": dog_feat["games_played"],
        "dog_win_pct": dog_feat["win_pct"],
        "dog_runs_scored_pg": dog_feat["runs_scored_per_game"],
        "dog_runs_allowed_pg": dog_feat["runs_allowed_per_game"],
        "dog_run_diff_pg": dog_feat["run_diff_per_game"],
        "dog_pyth_wpct": dog_feat["pyth_expected_wpct"],
        "dog_recent_form_wpct": dog_feat["recent_form_wpct"],
        # Differentials
        "wpct_diff": (
            (fav_feat["win_pct"] - dog_feat["win_pct"])
            if fav_feat["win_pct"] is not None and dog_feat["win_pct"] is not None
            else None
        ),
        "pyth_diff": (
            (fav_feat["pyth_expected_wpct"] - dog_feat["pyth_expected_wpct"])
            if fav_feat["pyth_expected_wpct"] is not None
            and dog_feat["pyth_expected_wpct"] is not None
            else None
        ),
        "run_diff_diff": (
            (fav_feat["run_diff_per_game"] - dog_feat["run_diff_per_game"])
            if fav_feat["run_diff_per_game"] is not None
            and dog_feat["run_diff_per_game"] is not None
            else None
        ),
        # Matchup features
        "is_home": bool(favorite_is_home),
        "h2h_wpct": h2h_wpct,
        "h2h_n": h2h_n,
        "days_rest": days_rest,
    }


def main() -> int:
    configure_logging()
    log = structlog.get_logger("build_mlb_dataset")
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2025-03-01",
                        help="Start date for Kalshi market close range (YYYY-MM-DD)")
    parser.add_argument("--end", default="2026-03-24",
                        help="End date for Kalshi market close range (YYYY-MM-DD)")
    parser.add_argument("--season-start", default="2025-03-01",
                        help="Date to start counting team-stat prior games (YYYY-MM-DD)")
    parser.add_argument("--limit-markets", type=int, default=None,
                        help="Cap the number of unique games processed (for smoke runs)")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    settings = Settings()
    start_dt = datetime.fromisoformat(args.start).replace(tzinfo=UTC)
    end_dt = datetime.fromisoformat(args.end).replace(tzinfo=UTC)
    start_ts = int(start_dt.timestamp())
    end_ts = int(end_dt.timestamp())
    season_start = datetime.fromisoformat(args.season_start).date()

    print(f"Building MLB dataset for close window {args.start} to {args.end}")
    print(f"Season-start for prior features: {args.season_start}")
    print(f"Output: {OUT_PATH}")

    # --- 1) Pull Kalshi historical markets ---
    with KalshiClient(settings) as client:
        markets_df = pull_kalshi_markets(client, start_ts, end_ts, log)

        print(f"Pulled {len(markets_df)} Kalshi markets")

        # Parse tickers
        markets_df["parsed"] = markets_df["ticker"].apply(parse_ticker)
        markets_df["parsed_ok"] = markets_df["parsed"].notna()
        parse_fail = markets_df[~markets_df["parsed_ok"]]
        if len(parse_fail) > 0:
            print(f"WARN: {len(parse_fail)} tickers failed to parse:")
            for t in parse_fail["ticker"].head(10):
                print(f"  {t}")
        markets_df = markets_df[markets_df["parsed_ok"]].copy()

        # Drop placeholder/pseudo markets (ALHS, ALLS, NLHS, NLLS)
        markets_df["away_abbrev"] = markets_df["parsed"].apply(lambda p: p["away"])
        markets_df["home_abbrev"] = markets_df["parsed"].apply(lambda p: p["home"])
        markets_df["game_date_obj"] = markets_df["parsed"].apply(lambda p: p["game_date"])
        markets_df["dh_suffix"] = markets_df["parsed"].apply(lambda p: p["dh_suffix"])
        markets_df["contract_team"] = markets_df["parsed"].apply(lambda p: p["contract_team"])
        is_placeholder = (
            markets_df["home_abbrev"].isin(PLACEHOLDER_TEAM_CODES)
            | markets_df["away_abbrev"].isin(PLACEHOLDER_TEAM_CODES)
        )
        if is_placeholder.sum() > 0:
            print(f"Dropping {is_placeholder.sum()} placeholder LCS markets")
        markets_df = markets_df[~is_placeholder].copy()

        # Cast time columns
        markets_df["open_time"] = pd.to_datetime(
            markets_df["open_time"], utc=True, format="ISO8601"
        )
        markets_df["close_time"] = pd.to_datetime(
            markets_df["close_time"], utc=True, format="ISO8601"
        )
        markets_df["last_price_dollars"] = pd.to_numeric(
            markets_df["last_price_dollars"]
        )

        # --- 2) Pull MLB schedule FIRST so we can use gameDate to bound the
        # trade window upper bound, preventing in-game prices from leaking
        # the eventual outcome into our "pre-game" favorite_price.
        print()
        with httpx.Client(headers={"User-Agent": "kalshi-v2-build/0.1"}) as http:
            last_game_date = markets_df["game_date_obj"].max()
            mlb_end_str = (last_game_date + timedelta(days=7)).strftime("%Y-%m-%d")
            mlb_df = pull_mlb_schedule(http, args.season_start, mlb_end_str, log)

        # Parse MLB game_date to date object and game_datetime_utc to datetime
        mlb_df["game_date_obj"] = pd.to_datetime(mlb_df["game_date"]).dt.date
        mlb_df["game_start_utc"] = pd.to_datetime(
            mlb_df["game_datetime_utc"], utc=True, errors="coerce"
        )
        # Coerce scores to nullable numerics
        mlb_df["home_score"] = pd.to_numeric(mlb_df["home_score"], errors="coerce")
        mlb_df["away_score"] = pd.to_numeric(mlb_df["away_score"], errors="coerce")

        # Build event_ticker -> {home_side_ticker, away_side_ticker} pairs
        grouped = markets_df.groupby("event_ticker")
        print(f"Unique event_tickers (games): {len(grouped)}")

        if args.limit_markets is not None:
            event_keys = list(grouped.groups.keys())[: args.limit_markets]
        else:
            event_keys = list(grouped.groups.keys())
        print(f"Will process {len(event_keys)} games")

        # --- 3) For each game: match MLB game FIRST to get game_start_utc, then
        # pull trades in the [open_time, game_start_utc] PRE-GAME window. ---
        per_game_rows: list[dict[str, Any]] = []
        no_mlb_match = 0
        no_game_start = 0
        for i, ev in enumerate(event_keys):
            sub = grouped.get_group(ev)
            if len(sub) != 2:
                # Some events may have only one side (rare); skip
                continue
            sub = sub.sort_values("contract_team")
            row_a = sub.iloc[0]
            row_b = sub.iloc[1]
            # Pick the contract on the HOME team's side as our reference
            home_team = row_a["home_abbrev"]
            ref_row = row_a if row_a["contract_team"] == home_team else row_b
            other_row = row_b if ref_row is row_a else row_a
            # MATCH MLB GAME to get the actual game start time
            mlb_game = match_game({"parsed": ref_row["parsed"]}, mlb_df)
            if mlb_game is None:
                no_mlb_match += 1
                per_game_rows.append({
                    "event_ticker": ev,
                    "parsed": ref_row["parsed"],
                    "drop_reason": "no_mlb_match",
                    "ref_row": ref_row.to_dict(),
                    "other_row": other_row.to_dict(),
                })
                continue
            game_start_utc = mlb_game.get("game_start_utc")
            if game_start_utc is None or pd.isna(game_start_utc):
                no_game_start += 1
                per_game_rows.append({
                    "event_ticker": ev,
                    "parsed": ref_row["parsed"],
                    "drop_reason": "no_game_start_utc",
                    "ref_row": ref_row.to_dict(),
                    "other_row": other_row.to_dict(),
                })
                continue
            # Trade window: [open_time, game_start_utc], PRE-GAME only.
            open_ts_i = int(ref_row["open_time"].timestamp())
            close_ts_i = int(ref_row["close_time"].timestamp())
            game_start_ts = int(game_start_utc.timestamp())
            # Defensive: if open_time is AFTER game start, the market opened
            # during/after the game (very rare). Skip those.
            if open_ts_i >= game_start_ts:
                per_game_rows.append({
                    "event_ticker": ev,
                    "parsed": ref_row["parsed"],
                    "drop_reason": "open_after_game_start",
                    "ref_row": ref_row.to_dict(),
                    "other_row": other_row.to_dict(),
                })
                continue
            # Pull trades on both contract sides, pre-game only
            ref_trades = pull_trades_for_market(
                client, ref_row["ticker"], open_ts_i, game_start_ts
            )
            other_trades = pull_trades_for_market(
                client, other_row["ticker"], open_ts_i, game_start_ts
            )
            ref_vwap = vwap_from_trades(ref_trades)
            other_vwap = vwap_from_trades(other_trades)
            # Determine favorite by VWAP
            ref_p = ref_vwap["vwap_yes"]
            other_p = other_vwap["vwap_yes"]
            if ref_p is None and other_p is None:
                # No PRE-GAME trades on either side; skip
                per_game_rows.append({
                    "event_ticker": ev,
                    "parsed": ref_row["parsed"],
                    "drop_reason": "no_pregame_trades_either_side",
                    "ref_row": ref_row.to_dict(),
                    "other_row": other_row.to_dict(),
                })
                continue
            if ref_p is None:
                ref_p = 1.0 - other_p if other_p is not None else None
            if other_p is None:
                other_p = 1.0 - ref_p if ref_p is not None else None
            # Favorite = side with higher VWAP
            if ref_p >= other_p:
                fav_row, fav_vwap = ref_row, ref_vwap
                dog_row, dog_vwap = other_row, other_vwap
                favorite_price = ref_p
            else:
                fav_row, fav_vwap = other_row, other_vwap
                dog_row, dog_vwap = ref_row, ref_vwap
                favorite_price = other_p
            per_game_rows.append({
                "event_ticker": ev,
                "fav_row": fav_row.to_dict(),
                "dog_row": dog_row.to_dict(),
                "fav_vwap_stats": fav_vwap,
                "dog_vwap_stats": dog_vwap,
                "favorite_price": float(favorite_price),
                "open_ts": open_ts_i,
                "close_ts": close_ts_i,
                "game_start_ts": game_start_ts,
                "mlb_game": mlb_game,
                "drop_reason": None,
            })
            if (i + 1) % 50 == 0:
                print(f"  processed {i+1}/{len(event_keys)} games")

        if no_mlb_match > 0:
            print(f"  {no_mlb_match} markets had no MLB match")
        if no_game_start > 0:
            print(f"  {no_game_start} markets had no game_start_utc")

    # --- 4) Resolve outcomes for matched rows ---
    matched_rows = []
    drop_rows: list[dict[str, Any]] = []
    for entry in per_game_rows:
        if entry.get("drop_reason") is not None:
            drop_rows.append({
                "ticker": entry.get("ref_row", {}).get("ticker"),
                "drop_reason": entry["drop_reason"],
                "game_date": entry["parsed"]["game_date"].isoformat() if entry.get("parsed") else None,
                "home": entry["parsed"]["home"] if entry.get("parsed") else None,
                "away": entry["parsed"]["away"] if entry.get("parsed") else None,
                "dh": entry["parsed"]["dh_suffix"] if entry.get("parsed") else None,
            })
            continue
        fav_row = entry["fav_row"]
        parsed = fav_row["parsed"]
        mlb_game = entry["mlb_game"]
        # Skip postponed or non-final games
        if mlb_game["status"] != "Final":
            drop_rows.append({
                "ticker": fav_row["ticker"],
                "drop_reason": f"status={mlb_game['status']}",
            })
            continue
        favorite_team = fav_row["contract_team"]
        is_favorite_home = favorite_team == parsed["home"]
        underdog_team = parsed["away"] if is_favorite_home else parsed["home"]
        # Determine outcome: did favorite team win?
        if is_favorite_home:
            won = bool(mlb_game.get("home_is_winner"))
        else:
            won = bool(mlb_game.get("away_is_winner"))
        if won:
            score_winning = mlb_game["home_score"] if is_favorite_home else mlb_game["away_score"]
            score_losing = mlb_game["away_score"] if is_favorite_home else mlb_game["home_score"]
            winning_team = favorite_team
            losing_team = underdog_team
        else:
            score_winning = mlb_game["away_score"] if is_favorite_home else mlb_game["home_score"]
            score_losing = mlb_game["home_score"] if is_favorite_home else mlb_game["away_score"]
            winning_team = underdog_team
            losing_team = favorite_team
        matched_rows.append({
            "ticker": fav_row["ticker"],
            "event_ticker": entry["event_ticker"],
            "series_ticker": "KXMLBGAME",
            "open_time": fav_row["open_time"],
            "close_time": fav_row["close_time"],
            "settlement_ts": pd.to_datetime(
                fav_row.get("settlement_ts"), utc=True, errors="coerce"
            ),
            "settlement_value_dollars": pd.to_numeric(
                fav_row.get("settlement_value_dollars"), errors="coerce"
            ),
            "result_yes_no": fav_row.get("result"),
            "last_price_dollars_settlement": pd.to_numeric(
                fav_row["last_price_dollars"], errors="coerce"
            ),
            "volume_fp_market_lifetime": pd.to_numeric(
                fav_row["volume_fp"], errors="coerce"
            ),
            "liquidity_dollars": pd.to_numeric(
                fav_row["liquidity_dollars"], errors="coerce"
            ),
            # Trading-window stats
            "favorite_price": entry["favorite_price"],
            "underdog_price": (1.0 - entry["favorite_price"])
            if entry["favorite_price"] is not None
            else None,
            "vwap_n_trades_in_window": entry["fav_vwap_stats"]["n_trades"],
            "vwap_volume_fp_in_window": entry["fav_vwap_stats"]["volume_fp"],
            "one_sided_flow_pct": entry["fav_vwap_stats"]["one_sided_flow_pct"],
            # Matchup
            "favorite_team_abbrev": favorite_team,
            "underdog_team_abbrev": underdog_team,
            "home_abbrev": parsed["home"],
            "away_abbrev": parsed["away"],
            "is_favorite_home": is_favorite_home,
            "dh_suffix": parsed["dh_suffix"] or "",
            "game_date": parsed["game_date"],
            "game_pk": mlb_game["game_pk"],
            # Outcome
            "outcome": int(won),
            "winning_team": winning_team,
            "losing_team": losing_team,
            "score_winning": float(score_winning) if score_winning is not None else None,
            "score_losing": float(score_losing) if score_losing is not None else None,
            # Market metadata
            "lifetime_days": (
                (fav_row["close_time"] - fav_row["open_time"]).total_seconds() / 86400.0
            ),
            "days_to_game": (
                (fav_row["close_time"] - fav_row["open_time"]).total_seconds() / 86400.0
            ),
        })

    print(f"Matched: {len(matched_rows)}, Dropped: {len(drop_rows)}")

    # --- 5) Compute team features for matched rows ---
    print("Computing team features (this takes a couple of minutes for the .500 lookup)...")
    full_rows: list[dict[str, Any]] = []
    # Cache compute_team_features per (team, cutoff) to avoid re-computing the
    # same team's running stats for every game on the same date.
    team_feature_cache: dict[tuple[str, dt.date], dict[str, Any]] = {}

    def cached_team_features(team: str, cutoff: dt.date) -> dict[str, Any]:
        key = (team, cutoff)
        if key in team_feature_cache:
            return team_feature_cache[key]
        out = compute_team_features(mlb_df, team, cutoff, season_start)
        team_feature_cache[key] = out
        return out

    # Cache wpct_map per (game_date) to speed up vs_500 computation
    wpct_cache: dict[dt.date, dict[str, float | None]] = {}

    def build_wpct_cache(cutoff: dt.date) -> dict[str, float | None]:
        if cutoff in wpct_cache:
            return wpct_cache[cutoff]
        teams = pd.unique(pd.concat([mlb_df["home_abbrev"], mlb_df["away_abbrev"]]))
        out: dict[str, float | None] = {}
        for t in teams:
            if not isinstance(t, str):
                continue
            feat_t = cached_team_features(t, cutoff)
            out[t] = feat_t["win_pct"]
        wpct_cache[cutoff] = out
        return out

    for i, mr in enumerate(matched_rows):
        cutoff = mr["game_date"]
        wpct_map = build_wpct_cache(cutoff)
        above_500 = {t for t, p in wpct_map.items() if p is not None and p >= 0.500}
        # Apply team alias before looking up MLB stats (e.g., Kalshi ARI -> MLB AZ)
        fav_kalshi = mr["favorite_team_abbrev"]
        dog_kalshi = mr["underdog_team_abbrev"]
        fav = TEAM_ABBREV_ALIASES.get(fav_kalshi, fav_kalshi)
        dog = TEAM_ABBREV_ALIASES.get(dog_kalshi, dog_kalshi)
        # Manual compute (uses cache to avoid re-computing per (team, cutoff))
        fav_feat = cached_team_features(fav, cutoff)
        dog_feat = cached_team_features(dog, cutoff)
        h2h_wpct, h2h_n = compute_h2h_wpct(mlb_df, fav, dog, cutoff, season_start)
        # Days rest
        if fav_feat["last_game_date"] is not None:
            days_rest = (cutoff - fav_feat["last_game_date"]).days
        else:
            days_rest = None
        # vs .500+ for favorite
        mask = (
            ((mlb_df["home_abbrev"] == fav) | (mlb_df["away_abbrev"] == fav))
            & (mlb_df["status"] == "Final")
            & (mlb_df["game_date_obj"] >= season_start)
            & (mlb_df["game_date_obj"] < cutoff)
            & (mlb_df["game_type"] == "R")
        )
        prior = mlb_df.loc[mask]
        n_500 = 0
        w_500 = 0
        for _, g in prior.iterrows():
            opp = g["away_abbrev"] if g["home_abbrev"] == fav else g["home_abbrev"]
            if opp not in above_500:
                continue
            is_home = g["home_abbrev"] == fav
            ts = g["home_score"] if is_home else g["away_score"]
            os_ = g["away_score"] if is_home else g["home_score"]
            if ts is None or os_ is None or pd.isna(ts) or pd.isna(os_):
                continue
            n_500 += 1
            if float(ts) > float(os_):
                w_500 += 1
        vs_500_wpct = (w_500 / n_500) if n_500 > 0 else None

        # Compose final row
        row = dict(mr)
        row.update({
            "fav_games_played": fav_feat["games_played"],
            "fav_win_pct": fav_feat["win_pct"],
            "fav_runs_scored_pg": fav_feat["runs_scored_per_game"],
            "fav_runs_allowed_pg": fav_feat["runs_allowed_per_game"],
            "fav_run_diff_pg": fav_feat["run_diff_per_game"],
            "fav_pyth_wpct": fav_feat["pyth_expected_wpct"],
            "fav_recent_form_wpct": fav_feat["recent_form_wpct"],
            "fav_home_wpct": fav_feat["home_wpct"],
            "fav_away_wpct": fav_feat["away_wpct"],
            "fav_vs_500_wpct": vs_500_wpct,
            "dog_games_played": dog_feat["games_played"],
            "dog_win_pct": dog_feat["win_pct"],
            "dog_runs_scored_pg": dog_feat["runs_scored_per_game"],
            "dog_runs_allowed_pg": dog_feat["runs_allowed_per_game"],
            "dog_run_diff_pg": dog_feat["run_diff_per_game"],
            "dog_pyth_wpct": dog_feat["pyth_expected_wpct"],
            "dog_recent_form_wpct": dog_feat["recent_form_wpct"],
            "wpct_diff": (
                (fav_feat["win_pct"] - dog_feat["win_pct"])
                if fav_feat["win_pct"] is not None and dog_feat["win_pct"] is not None
                else None
            ),
            "pyth_diff": (
                (fav_feat["pyth_expected_wpct"] - dog_feat["pyth_expected_wpct"])
                if fav_feat["pyth_expected_wpct"] is not None
                and dog_feat["pyth_expected_wpct"] is not None
                else None
            ),
            "run_diff_diff": (
                (fav_feat["run_diff_per_game"] - dog_feat["run_diff_per_game"])
                if fav_feat["run_diff_per_game"] is not None
                and dog_feat["run_diff_per_game"] is not None
                else None
            ),
            "is_home": bool(mr["is_favorite_home"]),
            "h2h_wpct": h2h_wpct,
            "h2h_n": int(h2h_n),
            "days_rest": days_rest,
        })
        full_rows.append(row)
        if (i + 1) % 200 == 0:
            print(f"  features computed: {i+1}/{len(matched_rows)}")

    df = pd.DataFrame(full_rows)
    print(f"Pre-filter rows: {len(df)}")

    # --- 6) Apply Strategy-B eligibility filter ---
    if "favorite_price" in df.columns:
        eligible_mask = (
            (df["favorite_price"] >= FAVORITE_PRICE_LOW)
            & (df["favorite_price"] <= FAVORITE_PRICE_HIGH)
            & (df["vwap_n_trades_in_window"] >= MIN_TRADES_IN_WINDOW)
        )
        df["is_strategy_b_eligible"] = eligible_mask
    print(f"Strategy-B eligible (price in [{FAVORITE_PRICE_LOW}, {FAVORITE_PRICE_HIGH}], "
          f"n_trades >= {MIN_TRADES_IN_WINDOW}): {int(df['is_strategy_b_eligible'].sum())}")

    # Save full dataset (eligible flag preserved) and a dropped-rows audit
    df.to_parquet(OUT_PATH, index=False)
    if drop_rows:
        pd.DataFrame(drop_rows).to_parquet(DROPPED_PATH, index=False)
    print(f"Saved: {OUT_PATH}")
    print(f"Dropped audit: {DROPPED_PATH} ({len(drop_rows)} rows)")

    # --- 7) Validation summary ---
    print()
    print("=" * 60)
    print("Validation summary")
    print("=" * 60)
    if len(df) > 0:
        print(f"Total rows:                 {len(df)}")
        print(f"Date range:                 {df['game_date'].min()} to {df['game_date'].max()}")
        print(f"Outcome rate (all):         {df['outcome'].mean():.3f}")
        elig = df[df["is_strategy_b_eligible"]]
        print(f"Strategy-B eligible n:      {len(elig)}")
        if len(elig) > 0:
            print(f"Strategy-B outcome rate:    {elig['outcome'].mean():.3f}")
            print(f"Median favorite_price:      {elig['favorite_price'].median():.3f}")
            print(f"Median vwap n_trades:       {elig['vwap_n_trades_in_window'].median():.0f}")
            print(f"Median fav_games_played:    {elig['fav_games_played'].median():.0f}")
        # 5 random sample rows
        if len(df) >= 5:
            print()
            print("Sample 5 rows:")
            cols = [
                "ticker", "favorite_team_abbrev", "underdog_team_abbrev",
                "favorite_price", "score_winning", "score_losing", "outcome",
                "fav_win_pct", "dog_win_pct", "is_strategy_b_eligible",
            ]
            sample = df.sample(min(5, len(df)), random_state=42)[cols]
            print(sample.to_string(index=False))
        # NaN check on feature columns
        feat_cols = [
            "favorite_price", "fav_win_pct", "fav_pyth_wpct", "fav_run_diff_pg",
            "dog_win_pct", "dog_pyth_wpct", "dog_run_diff_pg",
            "wpct_diff", "pyth_diff", "run_diff_diff",
        ]
        print()
        print("Null counts per feature (all rows):")
        for c in feat_cols:
            if c in df.columns:
                print(f"  {c:30s} {df[c].isna().sum()}")

    # Save run metadata as sidecar JSON
    meta = {
        "timestamp": datetime.now(UTC).isoformat(),
        "args": vars(args),
        "rows": len(df),
        "eligible_rows": int(df["is_strategy_b_eligible"].sum()) if "is_strategy_b_eligible" in df.columns else 0,
        "outcome_rate_all": float(df["outcome"].mean()) if len(df) > 0 else None,
        "outcome_rate_eligible": (
            float(df[df["is_strategy_b_eligible"]]["outcome"].mean())
            if "is_strategy_b_eligible" in df.columns
            and df["is_strategy_b_eligible"].sum() > 0
            else None
        ),
        "dropped_rows": len(drop_rows),
        "out_path": str(OUT_PATH),
    }
    meta_path = OUT_DIR / "joined_mlb_dataset_meta.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, default=str)
    print(f"\nMetadata: {meta_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
