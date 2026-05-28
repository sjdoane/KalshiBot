"""Phase 2a: pull NFL T-24h, T-18h, T-12h sportsbook snapshots.

Per v12 lock Section 9. Reuses v11 NFL events (granger_sample_events.parquet)
plus the existing odds_pulls directory. Pulls only the snapshot times
not already on disk.

Cost: ~90 NFL events * 3 windows = up to 270 raw snapshot calls, minus
deduplication (many snapshot hours overlap across same-day games). Real
unique pulls typically 50 to 150 = 500 to 1,500 credits of 14,740
remaining.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import httpx
import pandas as pd
from dotenv import load_dotenv


BASE = Path("C:/Users/SamJD/OneDrive/Desktop/AI Projects/Project Kalshi")
load_dotenv(BASE / ".env")
KEY = os.environ.get("THE_ODDS_API_KEY")
if not KEY:
    print("ERROR: THE_ODDS_API_KEY not set in .env", file=sys.stderr)
    raise SystemExit(2)

DATA = BASE / "data" / "v11"
PULLS = DATA / "odds_pulls"
SAMPLE_PATH = DATA / "granger_sample_events.parquet"

SPORT_KEY = "americanfootball_nfl"
COMMENCE_OFFSET = pd.Timedelta(hours=3, minutes=30)
NEW_WINDOWS = [
    ("T-24h", pd.Timedelta(hours=24)),
    ("T-18h", pd.Timedelta(hours=18)),
    ("T-12h", pd.Timedelta(hours=12)),
]
CREDIT_FLOOR = 1000


def derive_unique_snapshots(nfl_events: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    for r in nfl_events.itertuples(index=False):
        commence_est = r.close_time - COMMENCE_OFFSET
        for label, delta in NEW_WINDOWS:
            target = commence_est - delta
            target_rounded = target.floor("h")
            rows.append(
                {
                    "ticker": r.ticker,
                    "commence_estimate": commence_est,
                    "window_label": label,
                    "target_snapshot_time": target_rounded,
                }
            )
    snapshots = pd.DataFrame(rows)
    return (
        snapshots[["target_snapshot_time"]]
        .drop_duplicates()
        .sort_values("target_snapshot_time")
        .reset_index(drop=True)
    )


def existing_pulls() -> set[pd.Timestamp]:
    existing: set[pd.Timestamp] = set()
    for p in PULLS.glob("KXNFLGAME__*.json"):
        ts_str = p.stem.split("__")[1]
        ts = pd.Timestamp(ts_str).tz_localize("UTC")
        existing.add(ts)
    return existing


def pull_one(client: httpx.Client, iso_time: str) -> dict:
    url = f"https://api.the-odds-api.com/v4/historical/sports/{SPORT_KEY}/odds"
    params = {
        "apiKey": KEY,
        "regions": "us",
        "markets": "h2h",
        "date": iso_time,
        "oddsFormat": "decimal",
    }
    r = client.get(url, params=params, timeout=30.0)
    r.raise_for_status()
    return {
        "body": r.json(),
        "remaining": int(r.headers.get("x-requests-remaining", -1)),
        "used": int(r.headers.get("x-requests-used", -1)),
    }


def main() -> int:
    sample = pd.read_parquet(SAMPLE_PATH)
    nfl = sample[sample["sport_prefix"] == "KXNFLGAME"].copy()
    nfl["close_time"] = pd.to_datetime(nfl["close_time"], utc=True)
    print(f"NFL events in v11 sample: {len(nfl)}")

    snapshots = derive_unique_snapshots(nfl)
    snapshots["target_snapshot_time"] = pd.to_datetime(
        snapshots["target_snapshot_time"], utc=True
    )
    existing = existing_pulls()
    print(f"Existing NFL pulls on disk: {len(existing)}")
    to_pull = snapshots[~snapshots["target_snapshot_time"].isin(existing)]
    print(f"New unique snapshots to pull: {len(to_pull)}")
    print(f"Estimated credit cost: {len(to_pull) * 10}")

    if len(to_pull) == 0:
        print("Nothing to pull.")
        return 0

    log: list[dict] = []
    with httpx.Client() as client:
        for i, row in enumerate(to_pull.itertuples(index=False)):
            iso = pd.Timestamp(row.target_snapshot_time).isoformat()
            if iso.endswith("+00:00"):
                iso = iso.replace("+00:00", "Z")
            try:
                result = pull_one(client, iso)
            except httpx.HTTPStatusError as exc:
                log.append(
                    {
                        "i": i,
                        "iso": iso,
                        "status": "http_error",
                        "code": exc.response.status_code,
                    }
                )
                if exc.response.status_code in (401, 422):
                    print(f"  FATAL HTTP {exc.response.status_code}")
                    break
                continue
            out_path = (
                PULLS
                / f"KXNFLGAME__{pd.Timestamp(row.target_snapshot_time).strftime('%Y%m%dT%H%M')}.json"
            )
            with out_path.open("w", encoding="utf-8") as f:
                json.dump(result["body"], f)
            n_games = len(result["body"].get("data", []))
            log.append(
                {
                    "i": i,
                    "iso": iso,
                    "status": "ok",
                    "n_games": n_games,
                    "remaining": result["remaining"],
                }
            )
            if (i + 1) % 20 == 0:
                print(
                    f"  [{i + 1}/{len(to_pull)}] snap={iso} games={n_games} "
                    f"remaining={result['remaining']}"
                )
            if result["remaining"] >= 0 and result["remaining"] < CREDIT_FLOOR:
                print(
                    f"  STOP: remaining credits {result['remaining']} "
                    f"below floor {CREDIT_FLOOR}"
                )
                break
            time.sleep(0.05)
    n_ok = sum(1 for r in log if r["status"] == "ok")
    print(f"Pulls made: {n_ok} of {len(to_pull)} planned")
    last_remaining = next(
        (r.get("remaining") for r in reversed(log) if r.get("remaining", -1) >= 0),
        None,
    )
    print(f"Final remaining credits: {last_remaining}")
    pd.DataFrame(log).to_parquet(
        BASE / "data" / "v12" / "nfl_extended_pull_log.parquet", index=False
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
