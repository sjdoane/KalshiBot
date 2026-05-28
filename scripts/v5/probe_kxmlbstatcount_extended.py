"""V5-B1: extended analysis of the prop inventory.

Reads data/v5/kxmlbstatcount_inventory.parquet and produces:
- Per-series per-player-game dedup count
- Threshold (floor_strike) distribution
- Single-player concentration analysis
- Cluster-by-date analysis
- Cleaned subset for orthogonality check downstream (10 random markets)

Run: uv run python -m scripts.v5.probe_kxmlbstatcount_extended
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

DATA_DIR = REPO_ROOT / "data" / "v5"


def extract_player(s: str | None) -> str | None:
    if pd.isna(s) or s is None:
        return None
    return str(s).split(":")[0].strip()


def extract_game_date(ticker: str) -> str | None:
    """Parse the date prefix from a prop ticker.

    Tickers look like KXMLBHIT-26APR291510MIALAD-...; the second segment
    is YY MON DD HHMM TEAM TEAM (1510 is the start time HHMM).
    """
    if not isinstance(ticker, str):
        return None
    m = re.match(r"^KXMLB[A-Z]+-(\d{2})([A-Z]{3})(\d{2})(\d{4})", ticker)
    if not m:
        return None
    yy, mon, dd, _hhmm = m.groups()
    return f"20{yy}-{mon}-{dd}"


def main() -> None:
    in_path = DATA_DIR / "kxmlbstatcount_inventory.parquet"
    df = pd.read_parquet(in_path)
    print(f"Loaded {in_path}  shape={df.shape}")

    df["player"] = df["yes_sub_title"].apply(extract_player)
    df["game_date"] = df["ticker"].apply(extract_game_date)
    df["close_time_dt"] = pd.to_datetime(df["close_time"], format="mixed", errors="coerce", utc=True)
    df["open_time_dt"] = pd.to_datetime(df["open_time"], format="mixed", errors="coerce", utc=True)

    # Per series detailed stats
    per_series = {}
    for series in sorted(df["_series_prefix"].unique()):
        sdf = df[df["_series_prefix"] == series].copy()
        n_total = len(sdf)
        binary = sdf[sdf["result"].isin(["yes", "no"])]
        n_binary = len(binary)
        n_yes = int((binary["result"] == "yes").sum())
        n_no = int((binary["result"] == "no").sum())

        # Per-player-game-threshold (dedup independent unit)
        per_pgs = sdf.groupby(["player", "event_ticker", "floor_strike"], dropna=False).size()
        n_pgs = len(per_pgs)
        # Per-player-game (collapse the ladder)
        per_pg = sdf.groupby(["player", "event_ticker"], dropna=False).size()
        n_pg = len(per_pg)

        # Player concentration
        top_players = sdf["player"].value_counts().head(10).to_dict()
        top_share = sdf["player"].value_counts(normalize=True).head(10).to_dict()

        # Top 5 share
        top5_share_pct = float(sdf["player"].value_counts(normalize=True).head(5).sum() * 100)
        top_player_share_pct = float(sdf["player"].value_counts(normalize=True).iloc[0] * 100) if len(sdf) else 0.0

        # Game-date clustering
        n_dates = int(sdf["game_date"].nunique())

        per_series[series] = {
            "n_total": int(n_total),
            "n_binary": int(n_binary),
            "n_yes": n_yes,
            "n_no": n_no,
            "yes_rate": n_yes / max(n_binary, 1),
            "n_distinct_player_event_threshold": int(n_pgs),
            "n_distinct_player_event": int(n_pg),
            "n_distinct_players": int(sdf["player"].nunique()),
            "n_distinct_events": int(sdf["event_ticker"].nunique()),
            "n_distinct_game_dates": n_dates,
            "top_player": list(top_players.keys())[0] if top_players else None,
            "top_player_share_pct": top_player_share_pct,
            "top5_share_pct": top5_share_pct,
            "floor_strike_unique": sorted(set(pd.to_numeric(sdf["floor_strike"], errors="coerce").dropna().tolist())),
        }

    out_summary = DATA_DIR / "kxmlbstatcount_extended_summary.json"
    out_summary.write_text(json.dumps(per_series, indent=2, default=str))
    print(f"Wrote {out_summary}")

    # Save enriched parquet with extracted columns
    out_enriched = DATA_DIR / "kxmlbstatcount_inventory_enriched.parquet"
    df.to_parquet(out_enriched)
    print(f"Wrote {out_enriched}  shape={df.shape}")

    # Pretty print
    print("\n=== Per-series summary ===")
    for series, stats in per_series.items():
        print(f"\n{series}:")
        for k, v in stats.items():
            print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
