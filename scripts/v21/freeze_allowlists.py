"""v21 allowlist freeze (pre-screen, structural fields ONLY).

Per research/v21/00-methodology-lock.md section 2.1 (plan critic H3/H4,
methodology critic H-4/L-1): for each pre-registered Candidate A cell, freeze
an explicit series-prefix allowlist BEFORE the screen script exists or runs.

Freeze rule (locked): allowlist = top prefixes by in-band maker trade count
covering >= 80% of the cell's band trade count, OR the top 30 prefixes by band
trade count, WHICHEVER SET IS LARGER.

Structural fields only: trades (taker_side, yes_price, no_price, count,
created_time) + markets (ticker, event_ticker). NO status, NO result, NO
outcome-bearing column is read. The "category" is the leading alphanumeric
prefix of event_ticker (CATEGORY_SQL), mapped to a group via get_group, which
is how Round 15b defined the cells.

Window: 2024-11-01 to 2025-11-25 UTC (full post-sign-flip Becker coverage;
session TimeZone pinned to UTC so the freeze is machine-independent). The
allowlist defines cell MEMBERSHIP; the screen's train/recency windows are
applied downstream by the screen script.

Population note (review M1): because the script is outcome-blind it cannot
filter to resolved markets, so the ranking population includes trades on
unresolved/voided/open markets. That is the blind-by-construction direction;
do not misread a resolved-only cross-check as a discrepancy.

Run (Windows):
  & "C:\\Users\\SamJD\\OneDrive\\Desktop\\AI Projects\\Project Kalshi\\.venv-kronos\\Scripts\\python.exe" "C:\\Users\\SamJD\\OneDrive\\Desktop\\AI Projects\\Project Kalshi\\scripts\\v21\\freeze_allowlists.py"
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import duckdb

BASE = Path(r"C:/Users/SamJD/OneDrive/Desktop/AI Projects/Project Kalshi")
BECKER = BASE / "prediction-market-analysis"
TRADES_DIR = BECKER / "data" / "kalshi" / "trades"
MARKETS_DIR = BECKER / "data" / "kalshi" / "markets"
OUT_DIR = BASE / "research" / "v21" / "allowlists"
OUT_DIR.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(BECKER))
from src.analysis.kalshi.util.categories import CATEGORY_SQL, get_group  # noqa: E402

WINDOW_START = "2024-11-01"
WINDOW_END = "2025-11-25"

# The three pre-registered Round 15b cells (lock section 2.1). Band is on the
# MAKER entry price (combined-side: the non-taker side of each print).
CELLS = [
    {"name": "media_040_060", "group": "Media", "band": (0.40, 0.60)},
    {"name": "entertainment_040_060", "group": "Entertainment", "band": (0.40, 0.60)},
    {"name": "other_060_080", "group": "Other", "band": (0.60, 0.80)},
]

COVERAGE_TARGET = 0.80
TOP_N_FLOOR = 30


def main() -> None:
    con = duckdb.connect(":memory:")
    con.execute("PRAGMA threads=8")
    con.execute("PRAGMA memory_limit='12GB'")
    con.execute("SET TimeZone='UTC'")

    cat_sql = CATEGORY_SQL.replace("event_ticker", "m.event_ticker")

    # One scan: per-(category, band) maker trade counts. Structural columns only.
    t0 = time.time()
    q = f"""
        WITH mk AS (
            SELECT ticker, event_ticker
            FROM '{MARKETS_DIR.as_posix()}/*.parquet'
        ),
        joined AS (
            SELECT
                (CASE WHEN t.taker_side='yes' THEN t.no_price ELSE t.yes_price END)/100.0 AS maker_price,
                t.count AS contracts,
                {cat_sql} AS category
            FROM '{TRADES_DIR.as_posix()}/*.parquet' t
            INNER JOIN mk m ON t.ticker = m.ticker
            WHERE t.created_time >= TIMESTAMP '{WINDOW_START}'
              AND t.created_time < TIMESTAMP '{WINDOW_END}'
              AND t.yes_price IS NOT NULL
              AND t.no_price IS NOT NULL
              AND t.yes_price + t.no_price = 100
              AND t.count > 0
        )
        SELECT
            category,
            CASE
                WHEN maker_price >= 0.40 AND maker_price < 0.60 THEN '[0.40,0.60)'
                WHEN maker_price >= 0.60 AND maker_price < 0.80 THEN '[0.60,0.80)'
                ELSE NULL
            END AS band,
            COUNT(*) AS n_trades,
            SUM(contracts) AS n_contracts
        FROM joined
        WHERE maker_price >= 0.40 AND maker_price < 0.80
        GROUP BY category, band
    """
    df = con.execute(q).df()
    print(f"[freeze] scan took {time.time()-t0:.1f}s, {len(df)} (category, band) rows", flush=True)

    df = df[df["band"].notna()].copy()
    # 'independent' is the CATEGORY_SQL sentinel for unparseable event tickers;
    # it is unmatchable by any real live series (review L3).
    df = df[df["category"] != "independent"].copy()
    df["group"] = df["category"].apply(get_group)

    band_labels = {(0.40, 0.60): "[0.40,0.60)", (0.60, 0.80): "[0.60,0.80)"}

    for cell in CELLS:
        label = band_labels[cell["band"]]
        sub = df[(df["group"] == cell["group"]) & (df["band"] == label)].copy()
        # Deterministic order (review H1): stable sort, alphabetical tiebreak,
        # so a rerun reproduces the committed artifact byte-for-byte.
        sub = sub.sort_values(
            ["n_trades", "category"], ascending=[False, True], kind="mergesort"
        ).reset_index(drop=True)
        total = int(sub["n_trades"].sum())
        if total == 0:
            print(f"[freeze] WARNING: cell {cell['name']} has zero band trades", flush=True)

        # Set 1: smallest top-k covering >= 80% of band trade count.
        cum = sub["n_trades"].cumsum()
        k_cov = int((cum < COVERAGE_TARGET * total).sum()) + 1 if total > 0 else 0
        k_cov = min(k_cov, len(sub))
        # Set 2: top 30 by band trade count.
        k_floor = min(TOP_N_FLOOR, len(sub))
        # Locked rule: whichever set is LARGER.
        k = max(k_cov, k_floor)
        chosen = sub.head(k)
        coverage = float(chosen["n_trades"].sum() / total) if total > 0 else 0.0

        out = {
            "cell": cell["name"],
            "group": cell["group"],
            "band": label,
            "window": [WINDOW_START, WINDOW_END],
            "window_timezone": "UTC",
            "prefix_definition": "regexp_extract(event_ticker, '^([A-Z0-9]+)', 1)",
            "population": "all markets regardless of status/result (outcome-blind)",
            "rule": (
                f"max(top-k covering >= {COVERAGE_TARGET:.0%} of band trade count, "
                f"top {TOP_N_FLOOR} by band trade count); structural fields only; "
                f"ties broken alphabetically (stable sort)"
            ),
            "k_coverage": k_cov,
            "k_floor": k_floor,
            "n_prefixes": int(len(chosen)),
            "n_prefixes_total_in_cell": int(len(sub)),
            "total_band_trades": total,
            "coverage_of_band_trades": coverage,
            "prefixes": [
                {
                    "prefix": str(r.category),
                    "n_trades": int(r.n_trades),
                    "n_contracts": int(r.n_contracts),
                }
                for r in chosen.itertuples()
            ],
        }
        path = OUT_DIR / f"{cell['name']}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2)
        print(
            f"[freeze] {cell['name']}: {len(chosen)} prefixes "
            f"(k_cov={k_cov}, k_floor={k_floor}), coverage {coverage:.1%} "
            f"of {total:,} band trades -> {path}",
            flush=True,
        )


if __name__ == "__main__":
    main()
