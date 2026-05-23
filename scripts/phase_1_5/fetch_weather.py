"""Optional Phase 1.5+ data: pull historical daily high for KXHIGH cities.

The Phase 1.5 gate doesn't need this (it's pure market-price calibration).
But if the gate passes, Phase 2 will use this to compute a "model
probability" of the daily high exceeding each strike, which is the actual
input to the EC-1 maker-quoting strategy.

Outputs:
    data/raw/weather/observed/<CITY>.parquet  - realized daily high F
    data/raw/weather/forecast/<CITY>.parquet  - forecast issued N hours
                                                 before each target date

Usage:
    uv run python -m scripts.phase_1_5.fetch_weather --start 2024-01-01 --end 2026-04-30
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

import httpx
import pandas as pd
import structlog

from kalshi_bot.data.weather import (
    CITIES,
    fetch_historical_forecast_ensemble,
    fetch_observed_daily_high,
)
from kalshi_bot.logging import configure_logging

OUTPUT_DIR = Path("data/raw/weather")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", required=True, help="YYYY-MM-DD inclusive")
    parser.add_argument("--end", required=True, help="YYYY-MM-DD inclusive")
    parser.add_argument(
        "--cities",
        action="append",
        choices=list(CITIES),
        help="Restrict to one or more cities. Repeatable; default = all 5.",
    )
    args = parser.parse_args()

    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    target = args.cities or list(CITIES)

    configure_logging()
    log = structlog.get_logger("fetch_weather")

    obs_dir = OUTPUT_DIR / "observed"
    fc_dir = OUTPUT_DIR / "forecast"
    obs_dir.mkdir(parents=True, exist_ok=True)
    fc_dir.mkdir(parents=True, exist_ok=True)

    with httpx.Client(timeout=60.0) as client:
        for city in target:
            try:
                observed = fetch_observed_daily_high(city, start, end, client=client)
            except Exception as exc:
                log.error("observed_fetch_failed", city=city, error=str(exc))
                continue
            obs_df = pd.DataFrame(
                {"date": list(observed), "observed_high_F": list(observed.values())}
            )
            obs_df.to_parquet(obs_dir / f"{city}.parquet", index=False)
            log.info("wrote_observed", city=city, n_days=len(observed))

            try:
                forecast = fetch_historical_forecast_ensemble(
                    city, start, end, client=client
                )
            except Exception as exc:
                log.error("forecast_fetch_failed", city=city, error=str(exc))
                continue
            rows = [
                {"date": d, "member": i, "forecast_high_F": v}
                for d, members in forecast.items()
                for i, v in enumerate(members)
            ]
            fc_df = pd.DataFrame(rows)
            fc_df.to_parquet(fc_dir / f"{city}.parquet", index=False)
            log.info("wrote_forecast", city=city, n_days=len(forecast))

    return 0


if __name__ == "__main__":
    sys.exit(main())
