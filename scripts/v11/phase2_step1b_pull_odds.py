"""Phase 2 Step 1b: pull the-odds-api historical h2h odds for the v11
Granger sample (Track 1, v3-Granger scope).

Strategy: deduplicate snapshot times across the Granger sample, pull
each unique (sport, snapshot_time) once, save raw responses. Matching
to Becker markets happens later in step 2.

Budget: 19,800 credits of 20,000 (200 buffer). Aborts early if
remaining credits fall below 1,500 (safety floor for the buffer plus a
sanity-check follow-up call).

Sample design per v3 lock amendment:
- 220 MLB validation events
- 200 NBA validation events
- 200 NFL validation events
- Per event: 3 target snapshots (T-6h, T-3h, T-1h relative to a game
  commence time estimate derived as close_time minus 3.5 hours, which
  approximates first-pitch-to-final-out for the typical MLB game; NBA
  and NFL game durations are shorter so the estimate is conservative).
- After deduplication by (sport, rounded snapshot time to 60 min), the
  actual call count is typically 50 to 80 percent of raw-event * 3.

Run via the Becker venv (has duckdb and httpx):

    prediction-market-analysis/.venv/Scripts/python.exe scripts/v11/phase2_step1b_pull_odds.py
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import duckdb
import httpx
import pandas as pd
from dotenv import load_dotenv


BASE = Path("C:/Users/SamJD/OneDrive/Desktop/AI Projects/Project Kalshi")
load_dotenv(BASE / ".env")

KEY = os.environ.get("THE_ODDS_API_KEY")
if not KEY:
    print("ERROR: THE_ODDS_API_KEY not set in .env", file=sys.stderr)
    raise SystemExit(2)


BECKER = BASE / "prediction-market-analysis" / "data" / "kalshi"
MARKETS_GLOB = str(BECKER / "markets" / "*.parquet").replace("\\", "/")
DATA_OUT = BASE / "data" / "v11"
DATA_OUT.mkdir(parents=True, exist_ok=True)
PULLS_DIR = DATA_OUT / "odds_pulls"
PULLS_DIR.mkdir(parents=True, exist_ok=True)

SPORT_TO_KEY = {
    "KXMLBGAME": "baseball_mlb",
    "KXNBAGAME": "basketball_nba",
    "KXNFLGAME": "americanfootball_nfl",
}
N_PER_SPORT = {
    "KXMLBGAME": 220,
    "KXNBAGAME": 200,
    "KXNFLGAME": 200,
}
PURGE_DAYS = 7
COMMENCE_ESTIMATE_OFFSET = pd.Timedelta(hours=3, minutes=30)
WINDOWS = [
    ("T-6h", pd.Timedelta(hours=6)),
    ("T-3h", pd.Timedelta(hours=3)),
    ("T-1h", pd.Timedelta(hours=1)),
]
CREDIT_FLOOR = 1500  # abort early if remaining drops below this


def per_sport_median_split(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["close_time"] = pd.to_datetime(df["close_time"], utc=True)
    df["split"] = "purged"
    for sport in SPORT_TO_KEY:
        sport_df = df[df["sport_prefix"] == sport]
        if sport_df.empty:
            continue
        med = sport_df["close_time"].median()
        purge_lo = med - pd.Timedelta(days=PURGE_DAYS / 2)
        purge_hi = med + pd.Timedelta(days=PURGE_DAYS / 2)
        is_sport = df["sport_prefix"] == sport
        df.loc[is_sport & (df["close_time"] < purge_lo), "split"] = "dev"
        df.loc[is_sport & (df["close_time"] >= purge_hi), "split"] = "val"
    return df


def pull_settled_universe(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    rows = []
    for sport in SPORT_TO_KEY:
        df = con.execute(
            f"""
            SELECT ticker, event_ticker, title, close_time,
                   result, '{sport}' as sport_prefix
            FROM '{MARKETS_GLOB}'
            WHERE ticker LIKE '{sport}-%'
              AND status = 'finalized'
              AND close_time >= TIMESTAMP '2024-10-01 00:00:00'
            ORDER BY close_time
            """
        ).df()
        rows.append(df)
    return pd.concat(rows, ignore_index=True)


def sample_validation_events(val: pd.DataFrame) -> pd.DataFrame:
    """For each sport, take a deterministic stratified sample by
    (event_ticker, year-month). Drops duplicate event_tickers (both YES
    and NO market sides resolve to the same game; only one needed).
    """
    samples: list[pd.DataFrame] = []
    for sport, n_target in N_PER_SPORT.items():
        sport_df = val[val["sport_prefix"] == sport].copy()
        sport_df["close_time"] = pd.to_datetime(sport_df["close_time"], utc=True)
        sport_df = sport_df.drop_duplicates(subset=["event_ticker"]).sort_values(
            ["event_ticker"]
        )
        if len(sport_df) <= n_target:
            samples.append(sport_df)
            continue
        sport_df["yymm"] = sport_df["close_time"].dt.strftime("%Y-%m")
        groups = sport_df.groupby("yymm")
        per_group = max(1, n_target // max(1, groups.ngroups))
        picked = (
            groups.apply(lambda g: g.head(per_group), include_groups=False)
            .reset_index(drop=True)
            .head(n_target)
        )
        # Re-attach yymm column if dropped
        samples.append(picked)
    out = pd.concat(samples, ignore_index=True)
    return out


def derive_snapshot_times(sample: pd.DataFrame) -> pd.DataFrame:
    """Per event, derive 3 target snapshot times relative to a game
    commence estimate. Returns one row per (event, window_label).
    """
    rows: list[dict] = []
    for r in sample.itertuples(index=False):
        commence_est = r.close_time - COMMENCE_ESTIMATE_OFFSET
        for label, delta in WINDOWS:
            target = commence_est - delta
            target_rounded = target.floor("h")
            rows.append(
                {
                    "ticker": r.ticker,
                    "event_ticker": r.event_ticker,
                    "sport_prefix": r.sport_prefix,
                    "close_time": r.close_time,
                    "commence_estimate": commence_est,
                    "window_label": label,
                    "target_snapshot_time": target_rounded,
                }
            )
    return pd.DataFrame(rows)


def unique_pulls(snapshots: pd.DataFrame) -> pd.DataFrame:
    """Deduplicate by (sport_prefix, target_snapshot_time)."""
    return (
        snapshots[["sport_prefix", "target_snapshot_time"]]
        .drop_duplicates()
        .sort_values(["sport_prefix", "target_snapshot_time"])
        .reset_index(drop=True)
    )


def pull_one(client: httpx.Client, sport_key: str, iso_time: str) -> dict:
    url = f"https://api.the-odds-api.com/v4/historical/sports/{sport_key}/odds"
    params = {
        "apiKey": KEY,
        "regions": "us",
        "markets": "h2h",
        "date": iso_time,
        "oddsFormat": "decimal",
    }
    r = client.get(url, params=params, timeout=30.0)
    r.raise_for_status()
    remaining = int(r.headers.get("x-requests-remaining", -1))
    used = int(r.headers.get("x-requests-used", -1))
    return {
        "body": r.json(),
        "remaining": remaining,
        "used": used,
    }


def pull_all(pulls: pd.DataFrame) -> tuple[int, int, list[dict]]:
    """Pull each unique snapshot, save raw to data/v11/odds_pulls/.
    Returns (n_pulls_made, final_remaining, log_records).
    """
    log: list[dict] = []
    with httpx.Client() as client:
        for i, row in enumerate(pulls.itertuples(index=False)):
            sport_key = SPORT_TO_KEY[row.sport_prefix]
            iso = pd.Timestamp(row.target_snapshot_time).isoformat()
            if iso.endswith("+00:00"):
                iso = iso.replace("+00:00", "Z")
            elif not iso.endswith("Z"):
                iso = iso + "Z"
            try:
                result = pull_one(client, sport_key, iso)
            except httpx.HTTPStatusError as exc:
                code = exc.response.status_code
                body_snip = exc.response.text[:200]
                log.append(
                    {
                        "i": i,
                        "sport": row.sport_prefix,
                        "iso": iso,
                        "status": "http_error",
                        "code": code,
                        "error": body_snip,
                    }
                )
                if code in (401, 422):
                    print(f"  FATAL HTTP {code} on call {i + 1}: {body_snip}")
                    break
                continue
            out_path = (
                PULLS_DIR
                / f"{row.sport_prefix}__{pd.Timestamp(row.target_snapshot_time).strftime('%Y%m%dT%H%M')}.json"
            )
            with out_path.open("w", encoding="utf-8") as f:
                json.dump(result["body"], f)
            n_games = len(result["body"].get("data", []))
            log.append(
                {
                    "i": i,
                    "sport": row.sport_prefix,
                    "iso": iso,
                    "status": "ok",
                    "n_games": n_games,
                    "remaining": result["remaining"],
                    "used_total": result["used"],
                }
            )
            if (i + 1) % 25 == 0:
                print(
                    f"  [{i + 1}/{len(pulls)}] sport={row.sport_prefix} "
                    f"snap={iso} games={n_games} remaining={result['remaining']}"
                )
            if result["remaining"] >= 0 and result["remaining"] < CREDIT_FLOOR:
                print(
                    f"  STOP: remaining credits {result['remaining']} below "
                    f"floor {CREDIT_FLOOR}"
                )
                break
            time.sleep(0.05)
    n_pulls = sum(1 for r in log if r["status"] == "ok")
    final_remaining = max((r.get("remaining", -1) for r in log), default=-1)
    return n_pulls, final_remaining, log


def main() -> int:
    con = duckdb.connect()
    print("Phase 2 Step 1b: pull historical odds for Granger sample")
    print("--- Pulling settled universe...")
    universe = pull_settled_universe(con)
    print(f"  Universe: {len(universe)} market rows (both sides)")

    print("--- Computing per-sport median split...")
    df = per_sport_median_split(universe)
    val = df[df["split"] == "val"].copy()
    print(f"  Validation rows (both sides): {len(val)}")
    print(
        f"  Validation events (unique): "
        f"{val['event_ticker'].nunique()}"
    )

    print("--- Sampling validation events stratified by month...")
    sample = sample_validation_events(val)
    print(
        f"  Sampled events: {len(sample)} "
        f"({dict(sample.groupby('sport_prefix').size().astype(int))})"
    )
    sample.to_parquet(DATA_OUT / "granger_sample_events.parquet", index=False)

    print("--- Deriving snapshot times...")
    snapshots = derive_snapshot_times(sample)
    snapshots.to_parquet(DATA_OUT / "granger_target_snapshots.parquet", index=False)
    pulls = unique_pulls(snapshots)
    print(
        f"  Unique snapshots after dedup: {len(pulls)} "
        f"({dict(pulls.groupby('sport_prefix').size().astype(int))})"
    )
    print(f"  Estimated credit cost: {len(pulls) * 10}")
    pulls.to_parquet(DATA_OUT / "granger_unique_pulls.parquet", index=False)

    print("--- Pulling the-odds-api historical...")
    n_made, final_remaining, log = pull_all(pulls)
    print(f"  Pulls made: {n_made} of {len(pulls)} planned")
    print(f"  Final remaining credits: {final_remaining}")
    pd.DataFrame(log).to_parquet(DATA_OUT / "granger_pull_log.parquet", index=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
