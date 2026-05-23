"""Quick inspector for the just-pulled KXHIGH parquet files.

Reports row count, date range, unique strike count, and markets per day so
we can sanity-check that the corpus matches the Zerve study scale (~8,494
for KXHIGHNY) before running the gate.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from kalshi_bot.data.kxhigh import parse_occurrence_date

MARKETS_DIR = Path("data/raw/kalshi/markets")


def main() -> None:
    for parquet in sorted(MARKETS_DIR.glob("*.parquet")):
        df = pd.read_parquet(parquet)
        close = pd.to_datetime(df["close_time"], utc=True, format="ISO8601")
        # Historical-endpoint markets omit occurrence_datetime; derive the
        # date from event_ticker so the field is uniform across endpoints.
        df["occurrence_date"] = df["event_ticker"].apply(parse_occurrence_date)
        n_unparsed = df["occurrence_date"].isna().sum()

        print(f"\n=== {parquet.name} ===")
        print(f"  rows                 : {len(df)}")
        print(f"  earliest close_time  : {close.min()}")
        print(f"  latest close_time    : {close.max()}")
        print(
            f"  unique occurrence dates: {df['occurrence_date'].nunique()}"
            f" (unparsed event tickers: {n_unparsed})"
        )
        print(
            f"  unique floor_strike  : {df['floor_strike'].nunique()} "
            f"(min={df['floor_strike'].min()}, max={df['floor_strike'].max()})"
        )

        per_day = df.groupby("occurrence_date").size()
        print(
            f"  markets/day stats    : mean={per_day.mean():.2f} "
            f"median={per_day.median():.0f} min={per_day.min()} max={per_day.max()}"
        )

        result_counts = df["result"].value_counts(dropna=False)
        print(f"  result distribution  : {dict(result_counts)}")
        if n_unparsed:
            sample_bad = df.loc[df["occurrence_date"].isna(), "event_ticker"].head(3).tolist()
            print(f"  WARNING: unparseable event_ticker sample: {sample_bad}")


if __name__ == "__main__":
    main()
