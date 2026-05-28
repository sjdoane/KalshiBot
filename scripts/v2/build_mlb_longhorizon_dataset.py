"""Build joined LONG-HORIZON MLB Kalshi + MLB Stats API dataset for v2 research.

One row per team-favorite Kalshi market with team-level features computed
AS OF the v1 trading-window mid (close_time - 35 days). Mirrors v1's
[-42d, -28d] trading window: VWAP is computed over trades whose
created_time falls within [mid - 7d, mid + 7d] (equivalently
[close - 42d, close - 28d]).

This is the salvage-attempt rebuild per research/v2/06-critic.md Section 9
recommendation: train v2 model on v1's actual long-horizon market type
(season win totals, division winners, playoff qualifiers), not on game
markets where v1 doesn't trade.

Series included (team-favorite only; individual-player series excluded
and aggregated separately):
  - KXMLBWINS-{TEAM}-{YY}-T{N}  : season-win totals
  - KXMLB{AL,NL}{EAST,CENT,WEST}-{YY}-{TEAM}  : division winners
  - KXMLBPLAYOFFS-{YY}-{TEAM}  : playoff qualifiers

Excluded (individual or non-team-favorite):
  - KXMLBALMVP, KXMLBNLMVP, KXMLBALCY, KXMLBNLCY (individual awards)
  - KXMLBALROTY, KXMLBNLROTY (individual awards)
  - KXMLBWSMVP (individual)
  - KXMLBWORLD (country, not team)
  - KXMLBDIVWINNER (division, not team)

Run as:
    uv run python -m scripts.v2.build_mlb_longhorizon_dataset

Output: data/v2/joined_mlb_longhorizon_dataset.parquet
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

from kalshi_bot.analysis.metrics import kalshi_maker_fee_per_contract  # noqa: E402
from kalshi_bot.config import Settings  # noqa: E402
from kalshi_bot.data.kalshi_client import KalshiClient, KalshiHTTPError  # noqa: E402
from kalshi_bot.logging import configure_logging  # noqa: E402

OUT_DIR = REPO_ROOT / "data" / "v2"
OUT_PATH = OUT_DIR / "joined_mlb_longhorizon_dataset.parquet"
DROPPED_PATH = OUT_DIR / "joined_mlb_longhorizon_dropped.parquet"
META_PATH = OUT_DIR / "joined_mlb_longhorizon_meta.json"
INDIVIDUAL_PATH = OUT_DIR / "joined_mlb_longhorizon_individual.parquet"

SPORTS_MARKETS_DIR = REPO_ROOT / "data" / "sports" / "markets"
SPORTS_TRADES_DIR = REPO_ROOT / "data" / "sports" / "trades"

# v1's trading-window pattern: window_end = close - 28d, window_start =
# window_end - 14d. The window MID is close - 35d. So [-42d, -28d] is
# the trading-window cache for v1.
TRADING_WINDOW_END_OFFSET_DAYS = 28
TRADING_WINDOW_WIDTH_DAYS = 14
TRADING_WINDOW_MID_OFFSET_DAYS = TRADING_WINDOW_END_OFFSET_DAYS + (
    TRADING_WINDOW_WIDTH_DAYS // 2
)  # 35 days

# Strategy-B eligibility band, matching v1
FAVORITE_PRICE_LOW = 0.70
FAVORITE_PRICE_HIGH = 0.95

# v1 Round 7: max_lifetime_days=180
LIFETIME_MIN_DAYS = 30
LIFETIME_MAX_DAYS = 180

# Minimum number of trades in the window to keep the market
MIN_TRADES_IN_WINDOW = 5

# v1 favorite_maker.py:51 SLIPPAGE_ALLOWANCE
SLIPPAGE_ALLOWANCE = 0.015

# Series we ingest. Order: team-win totals, division winners, playoff
# qualifiers. The script also discovers KXMLBWINS-* from disk so that
# all 30 teams are picked up automatically.
DIVISION_SERIES = (
    "KXMLBALEAST",
    "KXMLBALCENT",
    "KXMLBALWEST",
    "KXMLBNLEAST",
    "KXMLBNLCENT",
    "KXMLBNLWEST",
)
PLAYOFFS_SERIES = ("KXMLBPLAYOFFS",)

# Series that are NOT team-favorite markets but are recorded for an
# audit-only "individual_markets" group (per task brief).
INDIVIDUAL_SERIES = (
    "KXMLBALMVP", "KXMLBNLMVP",
    "KXMLBALCY", "KXMLBNLCY",
    "KXMLBALROTY", "KXMLBNLROTY",
    "KXMLBWSMVP",
)

# Aliases for Kalshi-side team abbrevs that need normalization to match
# the MLB Stats API's canonical team.abbreviation.
TEAM_ABBREV_ALIASES = {
    "ARI": "AZ",  # Arizona Diamondbacks (per build_mlb_dataset.py)
    "NLW": None,  # Used by KXMLBDIVWINNER for divisions (skip)
}

# Ticker grammars.
WINS_RE = re.compile(r"^KXMLBWINS-([A-Z]{2,4})-(\d{2})-T(\d+)$")
DIVISION_RE = re.compile(
    r"^(KXMLBALEAST|KXMLBALCENT|KXMLBALWEST|"
    r"KXMLBNLEAST|KXMLBNLCENT|KXMLBNLWEST)"
    r"-(\d{2})-([A-Z]{2,4})$"
)
PLAYOFFS_RE = re.compile(r"^KXMLBPLAYOFFS-(\d{2})-([A-Z]{2,4})$")


def parse_team_ticker(ticker: str) -> dict[str, Any] | None:
    """Parse one of the long-horizon team-favorite tickers.

    Returns dict with keys: kind, team, year, [threshold for WINS].
    Returns None if the ticker doesn't match a supported grammar OR if
    the team is a non-team placeholder (e.g., NLW for KXMLBDIVWINNER).
    """
    m = WINS_RE.match(ticker)
    if m:
        team = m.group(1)
        return {
            "kind": "wins",
            "team": team,
            "year": 2000 + int(m.group(2)),
            "threshold": int(m.group(3)),
            "series": f"KXMLBWINS-{team}",
        }
    m = DIVISION_RE.match(ticker)
    if m:
        team = m.group(3)
        return {
            "kind": "division",
            "team": team,
            "year": 2000 + int(m.group(2)),
            "threshold": None,
            "series": m.group(1),
        }
    m = PLAYOFFS_RE.match(ticker)
    if m:
        team = m.group(2)
        return {
            "kind": "playoffs",
            "team": team,
            "year": 2000 + int(m.group(1)),
            "threshold": None,
            "series": "KXMLBPLAYOFFS",
        }
    return None


def load_markets_from_disk(series_tickers: list[str], log) -> pd.DataFrame:
    """Load cached market parquet files for the given series.

    Concatenates into a single DataFrame with a `series_ticker` column.
    """
    frames: list[pd.DataFrame] = []
    for s in series_tickers:
        p = SPORTS_MARKETS_DIR / f"{s}.parquet"
        if not p.exists():
            log.warning("series_missing", series=s)
            continue
        df = pd.read_parquet(p)
        df["series_ticker"] = s
        frames.append(df)
    if not frames:
        raise RuntimeError("no markets found on disk")
    return pd.concat(frames, ignore_index=True)


def load_trades_for_series(series_ticker: str) -> pd.DataFrame:
    """Load v1-cached trades for a series. Returns empty DataFrame if
    no cache exists."""
    p = SPORTS_TRADES_DIR / f"{series_ticker}.parquet"
    if not p.exists():
        return pd.DataFrame()
    return pd.read_parquet(p)


def pull_trades_for_market(
    client: KalshiClient, ticker: str, start_ts: int, end_ts: int
) -> list[dict[str, Any]]:
    """Pull trades for one ticker between start_ts and end_ts (Unix sec).
    """
    try:
        return list(
            client.paginate(
                "/historical/trades",
                item_key="trades",
                limit=1000,
                ticker=ticker,
                min_ts=start_ts,
                max_ts=end_ts,
            )
        )
    except KalshiHTTPError:
        return []


def vwap_and_flow(
    trades: pd.DataFrame, ticker: str, window_start: pd.Timestamp,
    window_end: pd.Timestamp,
) -> dict[str, Any]:
    """Compute VWAP, trade count, volume, one-sided flow pct for `ticker`
    over `[window_start, window_end]`."""
    if trades.empty:
        return _empty_vwap()
    sub = trades[trades["ticker"] == ticker].copy()
    if sub.empty:
        return _empty_vwap()
    # parse created_time
    sub["ts"] = pd.to_datetime(sub["created_time"], utc=True)
    sub = sub[(sub["ts"] >= window_start) & (sub["ts"] <= window_end)]
    if sub.empty:
        return _empty_vwap()
    # Parse trade attributes
    if "yes_price_dollars" in sub.columns:
        sub["yes_price"] = pd.to_numeric(sub["yes_price_dollars"], errors="coerce")
    elif "yes_price" in sub.columns:
        sub["yes_price"] = pd.to_numeric(sub["yes_price"], errors="coerce") / 100.0
    else:
        return _empty_vwap()
    if "count_fp" in sub.columns:
        sub["count"] = pd.to_numeric(sub["count_fp"], errors="coerce")
    elif "count" in sub.columns:
        sub["count"] = pd.to_numeric(sub["count"], errors="coerce")
    else:
        return _empty_vwap()
    sub = sub[sub["count"] > 0]
    sub = sub[sub["yes_price"].notna()]
    if sub.empty:
        return _empty_vwap()
    total_size = float(sub["count"].sum())
    if total_size <= 0:
        return _empty_vwap()
    vwap_all = float((sub["yes_price"] * sub["count"]).sum() / total_size)
    # Small-trade VWAP (<= 10 contracts), matching v1
    small = sub[sub["count"] <= 10]
    if small["count"].sum() > 0:
        vwap_small = float(
            (small["yes_price"] * small["count"]).sum() / small["count"].sum()
        )
    else:
        vwap_small = float("nan")
    # One-sided flow pct
    if "taker_side" in sub.columns:
        yes_takers = int((sub["taker_side"].astype(str).str.lower() == "yes").sum())
        no_takers = int((sub["taker_side"].astype(str).str.lower() == "no").sum())
        total = yes_takers + no_takers
        one_sided = (max(yes_takers, no_takers) / total) if total > 0 else None
    else:
        one_sided = None
    return {
        "vwap_yes": vwap_all,
        "vwap_yes_small": vwap_small,
        "n_trades": int(len(sub)),
        "volume_fp": total_size,
        "one_sided_flow_pct": one_sided,
    }


def _empty_vwap() -> dict[str, Any]:
    return {
        "vwap_yes": None,
        "vwap_yes_small": float("nan"),
        "n_trades": 0,
        "volume_fp": 0.0,
        "one_sided_flow_pct": None,
    }


def pull_mlb_schedule(
    http: httpx.Client, start_date: str, end_date: str, log
) -> pd.DataFrame:
    """Pull MLB schedule via Stats API."""
    log.info("mlb_pull_start", start=start_date, end=end_date)
    t0 = time.time()
    url = "https://statsapi.mlb.com/api/v1/schedule"
    params = {
        "sportId": 1,
        "startDate": start_date,
        "endDate": end_date,
        "gameType": "R,F,D,L,W",
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
                "game_number": g.get("gameNumber"),
                "home_abbrev": home_team.get("abbreviation"),
                "home_name": home_team.get("name"),
                "home_score": home.get("score"),
                "home_is_winner": home.get("isWinner"),
                "away_abbrev": away_team.get("abbreviation"),
                "away_name": away_team.get("name"),
                "away_score": away.get("score"),
                "away_is_winner": away.get("isWinner"),
                "game_datetime_utc": g.get("gameDate"),
            })
    df = pd.DataFrame(rows)
    log.info("mlb_pull_done", rows=len(df), seconds=round(time.time() - t0, 1))
    return df


def compute_team_features(
    games: pd.DataFrame, team: str, cutoff: dt.datetime, season_start: dt.date,
) -> dict[str, Any]:
    """Compute team-level features as of `cutoff` (datetime, UTC).

    Only games with game_datetime_utc < cutoff are eligible. Regular
    season only for base-rate features.
    """
    mask = (
        ((games["home_abbrev"] == team) | (games["away_abbrev"] == team))
        & (games["status"] == "Final")
        & (games["game_start_utc"] < cutoff)
        & (games["game_date_obj"] >= season_start)
        & (games["game_type"] == "R")
    )
    prior = games.loc[mask].sort_values("game_start_utc")
    if prior.empty:
        return _empty_team_features()
    wins = losses = 0
    rs_total = ra_total = 0.0
    home_w = home_n = 0
    away_w = away_n = 0
    last_30_w = last_30_n = 0
    cutoff_minus_30d = cutoff - timedelta(days=30)
    records: list[tuple[dt.datetime, bool]] = []
    last_game_dt = None
    for _, g in prior.iterrows():
        is_home = g["home_abbrev"] == team
        ts = g["home_score"] if is_home else g["away_score"]
        os_ = g["away_score"] if is_home else g["home_score"]
        if ts is None or os_ is None or pd.isna(ts) or pd.isna(os_):
            continue
        ts = float(ts)
        os_ = float(os_)
        won = ts > os_
        if won:
            wins += 1
        else:
            losses += 1
        rs_total += ts
        ra_total += os_
        gdt = g["game_start_utc"]
        if is_home:
            home_n += 1
            if won:
                home_w += 1
        else:
            away_n += 1
            if won:
                away_w += 1
        if gdt >= cutoff_minus_30d:
            last_30_n += 1
            if won:
                last_30_w += 1
        records.append((gdt, won))
        last_game_dt = gdt
    games_played = wins + losses
    if games_played == 0:
        return _empty_team_features()
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
    home_wpct = home_w / home_n if home_n > 0 else None
    away_wpct = away_w / away_n if away_n > 0 else None
    recent_wpct = last_30_w / last_30_n if last_30_n > 0 else None
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
        "last_game_dt": last_game_dt,
    }


def _empty_team_features() -> dict[str, Any]:
    return {
        "games_played": 0, "wins": 0, "losses": 0, "win_pct": None,
        "runs_scored_per_game": None, "runs_allowed_per_game": None,
        "run_diff_per_game": None, "pyth_expected_wpct": None,
        "recent_form_wpct": None, "home_wpct": None, "away_wpct": None,
        "last_game_dt": None,
    }


def compute_vs_500_wpct(
    games: pd.DataFrame, team: str, cutoff: dt.datetime, season_start: dt.date,
    wpct_map: dict[str, float | None],
) -> float | None:
    """Team's record vs teams whose own win_pct at cutoff is >= 0.500."""
    above_500 = {t for t, p in wpct_map.items() if p is not None and p >= 0.500}
    if not above_500:
        return None
    mask = (
        ((games["home_abbrev"] == team) | (games["away_abbrev"] == team))
        & (games["status"] == "Final")
        & (games["game_start_utc"] < cutoff)
        & (games["game_date_obj"] >= season_start)
        & (games["game_type"] == "R")
    )
    prior = games.loc[mask]
    n = w = 0
    for _, g in prior.iterrows():
        opp = g["away_abbrev"] if g["home_abbrev"] == team else g["home_abbrev"]
        if opp not in above_500:
            continue
        is_home = g["home_abbrev"] == team
        ts = g["home_score"] if is_home else g["away_score"]
        os_ = g["away_score"] if is_home else g["home_score"]
        if ts is None or os_ is None or pd.isna(ts) or pd.isna(os_):
            continue
        n += 1
        if float(ts) > float(os_):
            w += 1
    if n == 0:
        return None
    return w / n


def discover_target_series() -> list[str]:
    """List all KXMLBWINS-* series found on disk, plus division +
    playoffs."""
    discovered = []
    for f in sorted(SPORTS_MARKETS_DIR.glob("KXMLBWINS-*.parquet")):
        discovered.append(f.stem)
    return discovered + list(DIVISION_SERIES) + list(PLAYOFFS_SERIES)


def main() -> int:
    configure_logging()
    log = structlog.get_logger("build_mlb_longhorizon")
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--season-start", default="2025-03-01",
        help="Date to start counting team-stat prior games (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--mlb-schedule-start", default="2025-03-01",
        help="MLB schedule pull start date",
    )
    parser.add_argument(
        "--mlb-schedule-end", default="2025-12-15",
        help="MLB schedule pull end date",
    )
    parser.add_argument(
        "--fetch-missing-trades", action="store_true", default=True,
        help="Pull trades from Kalshi for any market with no cached trades.",
    )
    parser.add_argument(
        "--no-fetch-missing-trades", dest="fetch_missing_trades",
        action="store_false",
    )
    parser.add_argument(
        "--smoke", action="store_true",
        help="Limit to first 50 markets for fast iteration.",
    )
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    settings = Settings()
    season_start = datetime.fromisoformat(args.season_start).date()

    print(f"Output: {OUT_PATH}")

    # --- 1) Discover and load markets ---
    target_series = discover_target_series()
    print(f"Target series: {len(target_series)}")
    individual_series = list(INDIVIDUAL_SERIES)
    all_series_to_load = target_series + individual_series
    markets_df = load_markets_from_disk(all_series_to_load, log)
    print(f"Loaded {len(markets_df)} market rows from disk")

    # Cast time columns
    markets_df["close_time"] = pd.to_datetime(
        markets_df["close_time"], utc=True, format="ISO8601"
    )
    markets_df["open_time"] = pd.to_datetime(
        markets_df["open_time"], utc=True, format="ISO8601"
    )
    markets_df["lifetime_days"] = (
        markets_df["close_time"] - markets_df["open_time"]
    ).dt.total_seconds() / 86400.0

    # Status filter (finalized only)
    pre_status = len(markets_df)
    markets_df = markets_df[
        markets_df["status"].astype(str).isin(["settled", "finalized"])
    ].copy()
    print(f"  after status filter: {len(markets_df)} (dropped {pre_status - len(markets_df)})")

    # Binary market filter
    if "market_type" in markets_df.columns:
        pre_binary = len(markets_df)
        markets_df = markets_df[markets_df["market_type"] == "binary"].copy()
        print(f"  after binary filter: {len(markets_df)} (dropped {pre_binary - len(markets_df)})")

    # Lifetime filter at build time: min only. Max is applied via the
    # is_eligible flag downstream (mirrors v1: build with min=30, gate
    # with max=180). This preserves division markets (~186d lifetime)
    # in the dataset for audit purposes.
    pre_life = len(markets_df)
    markets_df = markets_df[
        markets_df["lifetime_days"] >= LIFETIME_MIN_DAYS
    ].copy()
    print(f"  after lifetime >= {LIFETIME_MIN_DAYS}d filter: "
          f"{len(markets_df)} (dropped {pre_life - len(markets_df)})")

    if args.smoke:
        markets_df = markets_df.head(50).copy()
        print(f"  smoke: limited to {len(markets_df)} markets")

    # Parse tickers; route individual markets to their own bucket
    markets_df["parsed"] = markets_df["ticker"].apply(parse_team_ticker)
    team_mask = markets_df["parsed"].notna()
    team_markets = markets_df[team_mask].copy()
    individual_markets = markets_df[~team_mask].copy()
    individual_markets["reason"] = "non_team_or_unparsed"
    print(f"  team-favorite markets: {len(team_markets)}")
    print(f"  individual / unparsed markets: {len(individual_markets)}")

    # Extract team
    team_markets["favorite_team_abbrev"] = team_markets["parsed"].apply(
        lambda p: p["team"]
    )
    # Drop any market whose team is None per alias (e.g., placeholder)
    bad_team_mask = team_markets["favorite_team_abbrev"].isin(
        [k for k, v in TEAM_ABBREV_ALIASES.items() if v is None]
    )
    if bad_team_mask.any():
        print(f"  dropping {bad_team_mask.sum()} placeholder-team markets")
        individual_markets = pd.concat([
            individual_markets,
            team_markets[bad_team_mask].assign(reason="placeholder_team"),
        ], ignore_index=True)
        team_markets = team_markets[~bad_team_mask].copy()

    # Map team aliases (Kalshi-side -> MLB-side)
    team_markets["favorite_team_mlb"] = team_markets["favorite_team_abbrev"].apply(
        lambda t: TEAM_ABBREV_ALIASES.get(t, t)
    )
    # Tag market_tier based on what kind of series
    def _tier(p: dict) -> str:
        return {
            "wins": "single_name",  # one contract per (team, threshold)
            "division": "small_multi",  # ~5 teams per division
            "playoffs": "small_multi",  # 30 teams competing
        }[p["kind"]]
    team_markets["market_tier"] = team_markets["parsed"].apply(_tier)
    team_markets["market_kind"] = team_markets["parsed"].apply(lambda p: p["kind"])

    # --- 2) Pull MLB schedule ---
    print()
    with httpx.Client(headers={"User-Agent": "kalshi-v2-long/0.1"}) as http:
        mlb_df = pull_mlb_schedule(
            http, args.mlb_schedule_start, args.mlb_schedule_end, log
        )
    mlb_df["game_date_obj"] = pd.to_datetime(mlb_df["game_date"]).dt.date
    mlb_df["game_start_utc"] = pd.to_datetime(
        mlb_df["game_datetime_utc"], utc=True, errors="coerce"
    )
    mlb_df["home_score"] = pd.to_numeric(mlb_df["home_score"], errors="coerce")
    mlb_df["away_score"] = pd.to_numeric(mlb_df["away_score"], errors="coerce")
    print(f"MLB schedule rows: {len(mlb_df)}, "
          f"finals: {(mlb_df['status'] == 'Final').sum()}")

    # --- 3) Compute trading-window VWAPs from cached trades, falling
    # back to a fresh fetch when needed ---
    # Group trades by series for efficiency
    print("Computing VWAPs over [close-42d, close-28d] window...")
    trades_cache: dict[str, pd.DataFrame] = {}
    series_to_load = team_markets["series_ticker"].unique().tolist()
    for s in series_to_load:
        df = load_trades_for_series(s)
        trades_cache[s] = df

    # Per-market window computation
    vwap_results: list[dict[str, Any]] = []
    no_trades_count = 0
    fetched_count = 0
    with KalshiClient(settings) as client:
        for idx, (_, m) in enumerate(team_markets.iterrows()):
            close_t = m["close_time"]
            ws = close_t - pd.Timedelta(days=42)
            we = close_t - pd.Timedelta(days=28)
            tdf = trades_cache.get(m["series_ticker"], pd.DataFrame())
            stats = vwap_and_flow(tdf, m["ticker"], ws, we)
            # Cache miss? fetch fresh trades
            if stats["n_trades"] == 0 and args.fetch_missing_trades:
                fetched = pull_trades_for_market(
                    client, m["ticker"],
                    int(ws.timestamp()), int(we.timestamp()),
                )
                fetched_count += 1
                if fetched:
                    fdf = pd.DataFrame(fetched)
                    stats = vwap_and_flow(fdf, m["ticker"], ws, we)
            if stats["n_trades"] == 0:
                no_trades_count += 1
            vwap_results.append({
                "ticker": m["ticker"],
                "vwap_window_start": ws,
                "vwap_window_end": we,
                **stats,
            })
            if (idx + 1) % 50 == 0:
                print(f"  vwap: {idx+1}/{len(team_markets)}, "
                      f"no_trades_so_far={no_trades_count}, "
                      f"fetched={fetched_count}")
    vwap_df = pd.DataFrame(vwap_results)
    print(f"VWAP complete: {len(vwap_df)} markets, "
          f"{no_trades_count} with no trades in window, "
          f"{fetched_count} fetched fresh")

    team_markets = team_markets.merge(vwap_df, on="ticker", how="left")

    # --- 4) Compute outcome ---
    team_markets["outcome"] = team_markets["result"].map({"yes": 1, "no": 0})
    out_drop = team_markets["outcome"].isna()
    if out_drop.any():
        print(f"Dropping {out_drop.sum()} rows with unrecognized result")
        team_markets = team_markets[~out_drop].copy()
    team_markets["outcome"] = team_markets["outcome"].astype(int)

    # --- 5) Compute trading_window_mid and team features ---
    print()
    print("Computing team features AS OF trading_window_mid (close - 35d)...")
    feature_rows: list[dict[str, Any]] = []
    feat_cache: dict[tuple[str, pd.Timestamp], dict[str, Any]] = {}
    wpct_cache: dict[pd.Timestamp, dict[str, float | None]] = {}

    def cached_team_features(
        team: str, cutoff: pd.Timestamp
    ) -> dict[str, Any]:
        key = (team, cutoff)
        if key in feat_cache:
            return feat_cache[key]
        # round cutoff to nearest minute to limit cache cardinality
        cutoff_py = cutoff.to_pydatetime()
        out = compute_team_features(mlb_df, team, cutoff_py, season_start)
        feat_cache[key] = out
        return out

    def build_wpct_map(cutoff: pd.Timestamp) -> dict[str, float | None]:
        if cutoff in wpct_cache:
            return wpct_cache[cutoff]
        all_teams = pd.unique(
            pd.concat([mlb_df["home_abbrev"], mlb_df["away_abbrev"]])
        )
        out: dict[str, float | None] = {}
        for t in all_teams:
            if not isinstance(t, str):
                continue
            feat = cached_team_features(t, cutoff)
            out[t] = feat["win_pct"]
        wpct_cache[cutoff] = out
        return out

    for i, (_, m) in enumerate(team_markets.iterrows()):
        close_t = m["close_time"]
        mid = close_t - pd.Timedelta(days=TRADING_WINDOW_MID_OFFSET_DAYS)
        # Round mid to UTC midnight for cache efficiency
        mid_floor = mid.floor("h")
        team = m["favorite_team_mlb"]
        feat = cached_team_features(team, mid_floor)
        wpct_map = build_wpct_map(mid_floor)
        vs_500 = compute_vs_500_wpct(
            mlb_df, team, mid_floor.to_pydatetime(), season_start, wpct_map,
        )
        days_rest = None
        if feat["last_game_dt"] is not None:
            try:
                days_rest = int((mid_floor - feat["last_game_dt"]).total_seconds() / 86400)
            except TypeError:
                days_rest = None
        feature_rows.append({
            "ticker": m["ticker"],
            "trading_window_mid": mid_floor,
            "team_games_played": feat["games_played"],
            "team_wins": feat["wins"],
            "team_losses": feat["losses"],
            "team_win_pct": feat["win_pct"],
            "team_runs_scored_pg": feat["runs_scored_per_game"],
            "team_runs_allowed_pg": feat["runs_allowed_per_game"],
            "team_run_diff_pg": feat["run_diff_per_game"],
            "team_pyth_wpct": feat["pyth_expected_wpct"],
            "team_recent_form_wpct": feat["recent_form_wpct"],
            "team_home_wpct": feat["home_wpct"],
            "team_away_wpct": feat["away_wpct"],
            "team_vs_500_wpct": vs_500,
            "team_days_rest": days_rest,
        })
        if (i + 1) % 50 == 0:
            print(f"  features: {i+1}/{len(team_markets)}")

    feat_df = pd.DataFrame(feature_rows)
    team_markets = team_markets.merge(feat_df, on="ticker", how="left")

    # --- 6) Build final output schema ---
    out_rows: list[dict[str, Any]] = []
    drop_rows: list[dict[str, Any]] = []
    for _, m in team_markets.iterrows():
        # Required mid_price_at_T_small. We use vwap_yes_small first,
        # fall back to vwap_yes if small is NaN.
        vwap = m.get("vwap_yes_small")
        if vwap is None or (isinstance(vwap, float) and pd.isna(vwap)):
            vwap = m.get("vwap_yes")
        n_trades = m.get("n_trades", 0) or 0
        # Filter for min trades: require enough trades to trust the VWAP.
        if vwap is None or n_trades < MIN_TRADES_IN_WINDOW:
            drop_rows.append({
                "ticker": m["ticker"],
                "drop_reason": f"insufficient_trades_in_window (n={n_trades})",
                "series_ticker": m["series_ticker"],
            })
            continue
        out_rows.append({
            # v1 schema compatibility
            "ticker": m["ticker"],
            "series_ticker": m["series_ticker"],
            "event_ticker": m.get("event_ticker"),
            "market_open_time": m["open_time"],
            "market_close_time": m["close_time"],
            "settlement_ts": pd.to_datetime(
                m.get("settlement_ts"), utc=True, errors="coerce"
            ),
            "outcome": int(m["outcome"]),
            "mid_price_at_T_small": float(vwap),
            "mid_price_at_T_all": float(m.get("vwap_yes") or vwap),
            "league": "MLB",
            "market_tier": m["market_tier"],
            "lifetime_days": float(m["lifetime_days"]),
            # v2 extensions
            "favorite_team_abbrev": m["favorite_team_abbrev"],
            "favorite_team_mlb": m["favorite_team_mlb"],
            "market_kind": m["market_kind"],
            "trading_window_mid": m["trading_window_mid"],
            "vwap_n_trades_in_window": int(n_trades),
            "vwap_volume_in_window": float(m.get("volume_fp") or 0.0),
            "one_sided_flow_pct": (
                float(m["one_sided_flow_pct"])
                if m.get("one_sided_flow_pct") is not None
                else float("nan")
            ),
            # team features
            "team_games_played": m.get("team_games_played"),
            "team_wins": m.get("team_wins"),
            "team_losses": m.get("team_losses"),
            "team_win_pct": m.get("team_win_pct"),
            "team_runs_scored_pg": m.get("team_runs_scored_pg"),
            "team_runs_allowed_pg": m.get("team_runs_allowed_pg"),
            "team_run_diff_pg": m.get("team_run_diff_pg"),
            "team_pyth_wpct": m.get("team_pyth_wpct"),
            "team_recent_form_wpct": m.get("team_recent_form_wpct"),
            "team_home_wpct": m.get("team_home_wpct"),
            "team_away_wpct": m.get("team_away_wpct"),
            "team_vs_500_wpct": m.get("team_vs_500_wpct"),
            "team_days_rest": m.get("team_days_rest"),
        })

    df = pd.DataFrame(out_rows)
    print(f"\nFinal rows (after MIN_TRADES={MIN_TRADES_IN_WINDOW} filter): {len(df)}")
    print(f"Dropped: {len(drop_rows)}")

    # --- 7) Apply Strategy-B eligibility filter ---
    df["favorite_price"] = df["mid_price_at_T_small"]
    df["is_eligible"] = (
        (df["favorite_price"] >= FAVORITE_PRICE_LOW)
        & (df["favorite_price"] <= FAVORITE_PRICE_HIGH)
        & (df["lifetime_days"] >= LIFETIME_MIN_DAYS)
        & (df["lifetime_days"] <= LIFETIME_MAX_DAYS)
    )
    n_eligible = int(df["is_eligible"].sum())
    print(f"Strategy-B eligible (price in [{FAVORITE_PRICE_LOW}, "
          f"{FAVORITE_PRICE_HIGH}], lifetime [{LIFETIME_MIN_DAYS}, "
          f"{LIFETIME_MAX_DAYS}]): {n_eligible}")

    # --- 8) Save outputs ---
    df.to_parquet(OUT_PATH, index=False)
    if drop_rows:
        pd.DataFrame(drop_rows).to_parquet(DROPPED_PATH, index=False)
    if not individual_markets.empty:
        # Keep only the columns we can reliably serialize
        ind_out_cols = [c for c in [
            "ticker", "series_ticker", "event_ticker",
            "open_time", "close_time", "lifetime_days", "status",
            "result", "title", "yes_sub_title", "reason",
        ] if c in individual_markets.columns]
        individual_markets[ind_out_cols].to_parquet(INDIVIDUAL_PATH, index=False)
    print(f"Saved: {OUT_PATH}")
    print(f"Dropped audit: {DROPPED_PATH}")
    print(f"Individual-markets audit: {INDIVIDUAL_PATH}")

    # --- 9) Validation summary ---
    print()
    print("=" * 60)
    print("Validation summary")
    print("=" * 60)
    if len(df) == 0:
        print("EMPTY DATASET; not enough markets cleared the filters.")
        return 1

    print(f"Total rows:                 {len(df)}")
    print(f"Series ingested:            {df['series_ticker'].nunique()}")
    print(f"Date range:                 {df['market_close_time'].min()} to "
          f"{df['market_close_time'].max()}")
    print(f"Outcome rate (all):         {df['outcome'].mean():.3f}")
    if n_eligible > 0:
        elig = df[df["is_eligible"]]
        print(f"Eligible n:                 {n_eligible}")
        print(f"Eligible outcome rate:      {elig['outcome'].mean():.3f}")
        print(f"Eligible mean favorite_px:  {elig['favorite_price'].mean():.3f}")
        print(f"Eligible median lifetime_d: {elig['lifetime_days'].median():.1f}")
        # Realized implied vs realized gap
        implied = elig["favorite_price"].mean()
        realized = elig["outcome"].mean()
        print(f"Implied minus realized:     {(realized - implied)*100:.2f}pp")

    # v1-heuristic P&L
    print()
    print("v1-heuristic realized P&L (per Strategy B formula):")
    print(_summarize_v1_heuristic_pnl(df))

    # Spot-check 5 random eligible rows
    if n_eligible >= 5:
        cols = [
            "ticker", "favorite_team_abbrev", "favorite_price",
            "outcome", "lifetime_days", "team_games_played",
            "team_win_pct", "team_pyth_wpct",
        ]
        sample = df[df["is_eligible"]].sample(
            min(5, n_eligible), random_state=42
        )[cols]
        print()
        print("Sample 5 eligible rows:")
        print(sample.to_string(index=False))

    # Null counts on eligible
    if n_eligible > 0:
        check_cols = [
            "mid_price_at_T_small", "team_win_pct", "team_pyth_wpct",
            "team_run_diff_pg", "team_recent_form_wpct",
        ]
        print()
        print("Null counts (eligible rows only):")
        elig = df[df["is_eligible"]]
        for c in check_cols:
            n_null = int(elig[c].isna().sum())
            pct = n_null / len(elig) * 100
            print(f"  {c:30s} {n_null:4d}  ({pct:5.1f}%)")

    # Meta
    meta = {
        "timestamp": datetime.now(UTC).isoformat(),
        "args": vars(args),
        "total_rows": int(len(df)),
        "eligible_rows": int(n_eligible),
        "outcome_rate_all": float(df["outcome"].mean()) if len(df) else None,
        "outcome_rate_eligible": (
            float(df[df["is_eligible"]]["outcome"].mean()) if n_eligible else None
        ),
        "dropped_rows": int(len(drop_rows)),
        "individual_markets": int(len(individual_markets)),
        "series_ingested": sorted(df["series_ticker"].unique().tolist()),
        "trading_window_mid_offset_days": TRADING_WINDOW_MID_OFFSET_DAYS,
        "trading_window_width_days": TRADING_WINDOW_WIDTH_DAYS,
        "favorite_price_band": [FAVORITE_PRICE_LOW, FAVORITE_PRICE_HIGH],
        "lifetime_band_days": [LIFETIME_MIN_DAYS, LIFETIME_MAX_DAYS],
        "min_trades_in_window": MIN_TRADES_IN_WINDOW,
    }
    META_PATH.write_text(json.dumps(meta, indent=2, default=str), encoding="utf-8")
    print(f"\nMeta: {META_PATH}")
    return 0


def _summarize_v1_heuristic_pnl(df: pd.DataFrame) -> str:
    """Compute v1's Strategy B realized P&L formula on the eligible subset.

    realized_per_contract = outcome - favorite_price - round_trip_fee - SLIPPAGE
    """
    elig = df[df["is_eligible"]].copy()
    if elig.empty:
        return "  (no eligible rows)"
    prices = elig["favorite_price"].to_numpy()
    outcomes = elig["outcome"].astype(int).to_numpy()
    # round-trip maker fees
    fees = [2 * kalshi_maker_fee_per_contract(float(p)) for p in prices]
    gross = outcomes - prices
    realized = gross - fees - SLIPPAGE_ALLOWANCE
    import numpy as np  # local to keep top-level imports clean
    mean_pp = float(realized.mean()) * 100
    median_pp = float(np.median(realized)) * 100
    hit_rate = float((realized > 0).mean()) * 100
    n = len(realized)
    sd_pp = float(realized.std()) * 100
    return (
        f"  n=                {n}\n"
        f"  mean P&L:         {mean_pp:+.2f}pp\n"
        f"  median P&L:       {median_pp:+.2f}pp\n"
        f"  SD per trade:     {sd_pp:.2f}pp\n"
        f"  hit rate (>0):    {hit_rate:.1f}%\n"
    )


if __name__ == "__main__":
    sys.exit(main())
