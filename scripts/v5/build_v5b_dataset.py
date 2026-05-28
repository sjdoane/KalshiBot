"""V5-B2: Build the joined prop dataset.

Reads:
- data/v5/kxmlbstatcount_inventory_enriched.parquet (V5-B1 cache)
- data/v5/statcast_2026_season_to_date.parquet (V5-B1 cache)

Writes:
- data/v5/prop_dataset.parquet

Invoke with:
    uv run python -m scripts.v5.build_v5b_dataset

This is a research-mode build. It does not touch v1's live-trading
codepath.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import structlog

from kalshi_bot_v5.statcast_features import (
    OUTPUT_PATH,
    PROP_SERIES,
    build_dataset,
    get_feature_column_names,
    load_kalshi_prop_markets,
    load_statcast,
)

log = structlog.get_logger(__name__)


SUMMARY_PATH = Path("data/v5/prop_dataset_summary.json")


def main() -> None:
    t0 = time.time()
    log.info("build_v5b_dataset_start")
    market_df = load_kalshi_prop_markets(list(PROP_SERIES), eligible_only=True)
    log.info("markets_loaded", n=len(market_df))
    statcast_df = load_statcast()
    log.info("statcast_loaded", n_pitches=len(statcast_df),
             date_min=str(statcast_df["game_date"].min()),
             date_max=str(statcast_df["game_date"].max()))

    joined = build_dataset(market_df, statcast_df, output_path=OUTPUT_PATH)
    t1 = time.time()

    # Summary stats.
    feat_cols = get_feature_column_names()
    feat_completeness = {}
    for col in feat_cols:
        if col in joined.columns:
            n_observed = int(joined[col].notna().sum())
            feat_completeness[col] = n_observed
    summary = {
        "n_rows": int(len(joined)),
        "n_yes": int(joined["outcome"].sum()),
        "n_no": int((joined["outcome"] == 0).sum()),
        "yes_rate": float(joined["outcome"].mean()),
        "n_distinct_players": int(joined["player"].nunique()),
        "n_distinct_player_game_pairs": int(
            joined.drop_duplicates(["player", "game_date_parsed"]).shape[0],
        ),
        "n_distinct_game_dates": int(joined["game_date_parsed"].nunique()),
        "n_series": int(joined["series"].nunique()),
        "series_counts": joined["series"].value_counts().to_dict(),
        "game_date_min": str(joined["game_date_parsed"].min()),
        "game_date_max": str(joined["game_date_parsed"].max()),
        "n_columns": int(len(joined.columns)),
        "n_feature_columns_with_any_data": int(
            sum(1 for v in feat_completeness.values() if v > 0),
        ),
        "feature_completeness": feat_completeness,
        "build_seconds": round(t1 - t0, 2),
    }
    SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2, default=str))
    log.info("build_v5b_dataset_done",
             wall_seconds=round(t1 - t0, 2),
             n_rows=summary["n_rows"])
    print(f"v5-b dataset built. wall={t1-t0:.1f}s, n={summary['n_rows']}")
    print(f"  series counts: {summary['series_counts']}")
    print(f"  yes rate: {summary['yes_rate']:.4f}")
    print(f"  distinct player-game pairs: {summary['n_distinct_player_game_pairs']}")
    print(f"  parquet: {OUTPUT_PATH}")
    print(f"  summary json: {SUMMARY_PATH}")


if __name__ == "__main__":
    main()
