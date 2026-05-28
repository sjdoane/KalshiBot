"""V5-B1: probe pybaseball Statcast download (sample week of late-season 2024).

Measures:
- Wall time for 1 week of pitch-by-pitch data
- Row count, on-disk size, columns available
- Projects to full 2024 season (~7 months) and full archive 2015-2024

Run: uv run python -m scripts.v5.probe_pybaseball_sample
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

OUT_DIR = REPO_ROOT / "data" / "v5"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Late-season 2024: Sept 22-29 (1 week, regular season tail)
START_DATE = "2024-09-22"
END_DATE = "2024-09-29"


def main() -> None:
    import pybaseball as pyb
    pyb.cache.enable()  # uses ~/pybaseball_cache by default

    print(f"pybaseball version: {pyb.__version__}")
    print(f"Sample window: {START_DATE} -> {END_DATE}")

    out: dict = {
        "pybaseball_version": pyb.__version__,
        "window_start": START_DATE,
        "window_end": END_DATE,
    }

    start = time.time()
    df = pyb.statcast(start_dt=START_DATE, end_dt=END_DATE)
    wall = time.time() - start

    out.update({
        "wall_seconds": wall,
        "n_rows": int(len(df)),
        "n_cols": int(df.shape[1]),
        "columns": list(df.columns),
    })

    # Sample size
    sample_csv_path = OUT_DIR / "statcast_sample_2024w39.csv.gz"
    df.to_csv(sample_csv_path, index=False, compression="gzip")
    csv_size = sample_csv_path.stat().st_size

    sample_parquet_path = OUT_DIR / "statcast_sample_2024w39.parquet"
    df.to_parquet(sample_parquet_path)
    parquet_size = sample_parquet_path.stat().st_size

    out.update({
        "csv_gz_bytes": int(csv_size),
        "csv_gz_mb": round(csv_size / 1024 / 1024, 2),
        "parquet_bytes": int(parquet_size),
        "parquet_mb": round(parquet_size / 1024 / 1024, 2),
    })

    # Projections to full season + archive
    days = 7
    season_days = 7 * 30  # roughly 7 months
    archive_days = 10 * season_days  # 10 seasons
    out["projections"] = {
        "sample_days": days,
        "rows_per_day": round(len(df) / days, 0),
        "full_2024_season_rows_est": round(len(df) / days * season_days, 0),
        "full_2024_season_parquet_mb_est": round(parquet_size / days * season_days / 1024 / 1024, 1),
        "archive_2015_2024_rows_est": round(len(df) / days * archive_days, 0),
        "archive_2015_2024_parquet_mb_est": round(parquet_size / days * archive_days / 1024 / 1024, 1),
        "archive_2015_2024_parquet_gb_est": round(parquet_size / days * archive_days / 1024 / 1024 / 1024, 2),
        "extrapolated_download_seconds_full_season": round(wall / days * season_days, 0),
        "extrapolated_download_seconds_archive": round(wall / days * archive_days, 0),
    }

    out_summary = OUT_DIR / "pybaseball_sample_summary.json"
    out_summary.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nWrote {out_summary}")
    print(json.dumps({k: v for k, v in out.items() if k != "columns"}, indent=2, default=str))
    print(f"\nColumn count: {len(out['columns'])}")
    print(f"First 30 cols: {out['columns'][:30]}")


if __name__ == "__main__":
    main()
