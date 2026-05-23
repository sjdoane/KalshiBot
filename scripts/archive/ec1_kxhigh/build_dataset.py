"""Phase 1.5 step 3: build data/processed/kxhigh_dataset.parquet.

Reads the per-series raw market and trade parquets, joins them, computes
VWAP in the locked methodology window, filters to binary outcomes with
in-window trades, and writes a single combined parquet for the gate.
"""

from __future__ import annotations

import sys

import structlog

from kalshi_bot.analysis.dataset import build_full_dataset, write_dataset
from kalshi_bot.logging import configure_logging


def main() -> int:
    configure_logging()
    log = structlog.get_logger("build_dataset")
    df = build_full_dataset()
    if df.empty:
        log.error("empty_dataset")
        return 1
    out = write_dataset(df)
    by_city = df.groupby("city").size().to_dict()
    log.info(
        "wrote_dataset",
        path=str(out),
        rows=len(df),
        by_city=by_city,
        date_min=str(df["occurrence_date"].min()),
        date_max=str(df["occurrence_date"].max()),
        mid_q05=float(df["mid_price_at_T"].quantile(0.05)),
        mid_q50=float(df["mid_price_at_T"].quantile(0.50)),
        mid_q95=float(df["mid_price_at_T"].quantile(0.95)),
        outcome_rate=float(df["outcome"].mean()),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
