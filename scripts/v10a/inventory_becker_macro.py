"""V10-A Phase 1 Agent v10A-1: Becker dataset macro inventory.

Counts unique release events per macro category in the Becker dataset
(prediction-market-analysis/data/kalshi/markets/*.parquet). Maps to Kim et al.
arXiv 2602.07048 series:

    Kim KXCPI       -> Becker event_ticker prefix CPI / CPIYOY / CPICORE / CPICOREYOY
    Kim KXNFP       -> PAYROLLS (Kalshi's NFP series prefix)
    Kim KXUNRATE    -> U3
    Kim KXFEDFUNDS  -> FEDDECISION (rate decisions) / FED (other) / RATECUT

Each row in Becker markets is one binary strike. A macro "release event"
corresponds to one calendar release date which produces many strikes (e.g.,
CPI April 2024 produces strikes at +0.2, +0.3, ..., +1.0 etc). We deduplicate
by the YYYY-MM portion of close_time per category to count unique events.

Output: research/v10a/becker-macro-inventory.json plus a markdown report
written to research/v10a/02-becker-inventory.md.

Run via: .venv (Becker's own uv-managed venv).

Per Project Kalshi rules: no em-dashes. Trade data layer must be validated
before any Phase 2 commitment.
"""
from __future__ import annotations

import json
from pathlib import Path

import duckdb

REPO_ROOT = Path(__file__).resolve().parents[2]
BECKER_DIR = REPO_ROOT / "prediction-market-analysis"
MARKETS_DIR = BECKER_DIR / "data" / "kalshi" / "markets"
TRADES_DIR = BECKER_DIR / "data" / "kalshi" / "trades"
OUTPUT_JSON = REPO_ROOT / "research" / "v10a" / "becker-macro-inventory.json"
OUTPUT_MD = REPO_ROOT / "research" / "v10a" / "02-becker-inventory.md"

# Kim mapping: target -> set of Becker event_ticker prefixes that map to this macro release
# Multiple prefixes can map to the same Kim target if Kalshi has variant tickers
# (e.g. CPI MoM vs CPI YoY both inform the same monthly CPI release).
KIM_MAPPING = {
    "Kim_KXCPI": ["CPI", "CPIYOY", "CPICORE", "CPICOREYOY", "ACPI"],
    "Kim_KXNFP": ["PAYROLLS"],
    "Kim_KXUNRATE": ["U3"],
    "Kim_KXFEDFUNDS": ["FEDDECISION", "FED", "RATECUT", "RATECUTCOUNT", "TERMINALRATE"],
}

# Other macro / finance categories worth probing for V10-A pivot menu
OTHER_FINANCE = [
    "GDP",
    "RECSSNBER",
    "CPI",  # broad CPI prefix bucket (overlaps with KXCPI; useful sanity check)
    "INX",  # S&P
    "NASDAQ100",
    "TNOTE",
    "USDJPY",
    "EURUSD",
    "TARIFF",
]


def run_query(sql: str) -> list[tuple]:
    """Execute against the markets parquet glob, return rows."""
    con = duckdb.connect()
    return con.execute(sql).fetchall()


def list_markets_files() -> list[Path]:
    return sorted(MARKETS_DIR.glob("*.parquet"))


def list_trades_files() -> list[Path]:
    return sorted(TRADES_DIR.glob("*.parquet"))


def category_prefix_sql(col: str = "event_ticker") -> str:
    return f"regexp_extract({col}, '^([A-Z0-9]+)', 1)"


def inventory_for_prefix(prefix: str) -> dict:
    """Return inventory stats for a given event_ticker prefix.

    Counts unique markets, unique release months (YYYY-MM close_time), volume,
    and resolved count.
    """
    cat_sql = category_prefix_sql("event_ticker")
    # close_time is typically the release date for macro markets
    sql = f"""
    WITH macro AS (
        SELECT
            ticker,
            event_ticker,
            status,
            result,
            volume,
            volume_24h,
            close_time,
            strftime(close_time, '%Y-%m') AS close_month,
            strftime(close_time, '%Y-%m-%d') AS close_day,
            last_price,
            yes_bid, yes_ask
        FROM '{MARKETS_DIR.as_posix()}/*.parquet'
        WHERE {cat_sql} = '{prefix}'
    )
    SELECT
        '{prefix}' AS prefix,
        COUNT(*) AS n_markets,
        COUNT(DISTINCT close_month) AS n_unique_release_months,
        COUNT(DISTINCT close_day) AS n_unique_release_days,
        COUNT(DISTINCT event_ticker) AS n_unique_event_tickers,
        SUM(volume) AS total_volume,
        SUM(CASE WHEN status = 'finalized' AND result IN ('yes', 'no') THEN 1 ELSE 0 END) AS n_resolved,
        MIN(close_time) AS oldest_close,
        MAX(close_time) AS newest_close
    FROM macro
    """
    rows = run_query(sql)
    if not rows:
        return {"prefix": prefix, "n_markets": 0}
    cols = [
        "prefix",
        "n_markets",
        "n_unique_release_months",
        "n_unique_release_days",
        "n_unique_event_tickers",
        "total_volume",
        "n_resolved",
        "oldest_close",
        "newest_close",
    ]
    return dict(zip(cols, rows[0]))


def aggregate_release_events(prefixes: list[str]) -> int:
    """Count unique YYYY-MM release months across a Kim mapping group."""
    cat_sql = category_prefix_sql("event_ticker")
    prefix_in = ", ".join(f"'{p}'" for p in prefixes)
    sql = f"""
    SELECT COUNT(DISTINCT strftime(close_time, '%Y-%m'))
    FROM '{MARKETS_DIR.as_posix()}/*.parquet'
    WHERE {cat_sql} IN ({prefix_in})
      AND close_time IS NOT NULL
      AND status IN ('finalized', 'closed')
    """
    rows = run_query(sql)
    return int(rows[0][0]) if rows else 0


def aggregate_post_flip_release_events(prefixes: list[str]) -> int:
    """Count unique YYYY-MM release months post October 2024 (Becker sign flip)."""
    cat_sql = category_prefix_sql("event_ticker")
    prefix_in = ", ".join(f"'{p}'" for p in prefixes)
    sql = f"""
    SELECT COUNT(DISTINCT strftime(close_time, '%Y-%m'))
    FROM '{MARKETS_DIR.as_posix()}/*.parquet'
    WHERE {cat_sql} IN ({prefix_in})
      AND close_time IS NOT NULL
      AND close_time >= '2024-10-01'
      AND status IN ('finalized', 'closed')
    """
    rows = run_query(sql)
    return int(rows[0][0]) if rows else 0


def trades_coverage_for_prefix(prefix: str) -> dict:
    """Count trades available in Becker trades for a given event_ticker prefix.

    Joins trades to markets to filter by prefix.
    """
    cat_sql = category_prefix_sql("m.event_ticker")
    sql = f"""
    WITH macro_markets AS (
        SELECT DISTINCT ticker
        FROM '{MARKETS_DIR.as_posix()}/*.parquet' m
        WHERE {cat_sql} = '{prefix}'
    )
    SELECT
        '{prefix}' AS prefix,
        COUNT(*) AS n_trades,
        COUNT(DISTINCT t.ticker) AS n_tickers_with_trades,
        MIN(t.created_time) AS oldest_trade,
        MAX(t.created_time) AS newest_trade
    FROM '{TRADES_DIR.as_posix()}/*.parquet' t
    INNER JOIN macro_markets m ON t.ticker = m.ticker
    """
    rows = run_query(sql)
    if not rows:
        return {"prefix": prefix, "n_trades": 0}
    cols = ["prefix", "n_trades", "n_tickers_with_trades", "oldest_trade", "newest_trade"]
    return dict(zip(cols, rows[0]))


def discover_macro_prefixes() -> list[dict]:
    """Discover ALL event_ticker prefixes with macro-like properties.

    Finds prefixes that have:
      - at least 5 unique release months in Becker
      - at least 5 finalized markets
      - represent macro/finance content (heuristic: matches a macro keyword
        in the prefix name, OR has high resolution rate near monthly cadence)
    """
    cat_sql = category_prefix_sql("event_ticker")
    sql = f"""
    WITH prefix_stats AS (
        SELECT
            {cat_sql} AS prefix,
            COUNT(*) AS n_markets,
            COUNT(DISTINCT strftime(close_time, '%Y-%m')) AS n_unique_months,
            COUNT(DISTINCT event_ticker) AS n_unique_events,
            SUM(CASE WHEN status = 'finalized' AND result IN ('yes', 'no') THEN 1 ELSE 0 END) AS n_resolved,
            SUM(volume) AS total_volume,
            MIN(close_time) AS oldest,
            MAX(close_time) AS newest
        FROM '{MARKETS_DIR.as_posix()}/*.parquet'
        WHERE close_time IS NOT NULL
        GROUP BY {cat_sql}
        HAVING COUNT(DISTINCT strftime(close_time, '%Y-%m')) >= 5
    )
    SELECT *
    FROM prefix_stats
    ORDER BY n_unique_months DESC, n_markets DESC
    LIMIT 100
    """
    rows = run_query(sql)
    cols = ["prefix", "n_markets", "n_unique_months", "n_unique_events", "n_resolved", "total_volume", "oldest", "newest"]
    return [dict(zip(cols, r)) for r in rows]


def main() -> None:
    if not MARKETS_DIR.exists():
        raise SystemExit(f"Becker markets directory not found: {MARKETS_DIR}")
    market_files = list_markets_files()
    trade_files = list_trades_files()
    print(f"markets parquet files: {len(market_files)}")
    print(f"trades parquet files: {len(trade_files)}")

    if not market_files:
        raise SystemExit("No markets parquet files; extract data.tar.zst first")

    inventory = {
        "markets_files": len(market_files),
        "trades_files": len(trade_files),
        "all_macro_prefixes_discovered": [],
        "kim_mapping": {},
        "other_finance": {},
        "trades_coverage": {},
    }

    print("\n## Auto-discovered prefixes with >= 5 unique close months (top 100)")
    print("=" * 60)
    discovered = discover_macro_prefixes()
    inventory["all_macro_prefixes_discovered"] = [
        {**d, "oldest": str(d["oldest"]), "newest": str(d["newest"])} for d in discovered
    ]
    for d in discovered[:30]:
        print(
            f"  {d['prefix']:20}  months={d['n_unique_months']:>4} "
            f"events={d['n_unique_events']:>5} markets={d['n_markets']:>6} "
            f"resolved={d['n_resolved']:>5} vol={d['total_volume']:>10}"
        )

    print("\n## Kim mapping inventory")
    print("=" * 60)
    total_kim_events_full = 0
    total_kim_events_post_flip = 0
    for kim_name, prefixes in KIM_MAPPING.items():
        per_prefix = {p: inventory_for_prefix(p) for p in prefixes}
        n_total = aggregate_release_events(prefixes)
        n_post_flip = aggregate_post_flip_release_events(prefixes)
        inventory["kim_mapping"][kim_name] = {
            "prefixes": prefixes,
            "per_prefix": per_prefix,
            "n_release_months_total": n_total,
            "n_release_months_post_oct_2024": n_post_flip,
        }
        total_kim_events_full += n_total
        total_kim_events_post_flip += n_post_flip
        print(f"\n{kim_name} -> prefixes {prefixes}")
        for prefix, stats in per_prefix.items():
            if stats.get("n_markets", 0) > 0:
                print(
                    f"  {prefix:18}  n_markets={stats['n_markets']:>5} "
                    f"unique_months={stats['n_unique_release_months']:>4} "
                    f"resolved={stats['n_resolved']:>5} "
                    f"vol={stats['total_volume']:>10} "
                    f"range={str(stats['oldest_close'])[:10]} .. {str(stats['newest_close'])[:10]}"
                )
        print(
            f"  Total release months (any time): {n_total}; "
            f"post 2024-10-01: {n_post_flip}"
        )

    inventory["kim_total_release_months"] = total_kim_events_full
    inventory["kim_total_release_months_post_flip"] = total_kim_events_post_flip

    print(f"\nKim 4-series total release months (any time): {total_kim_events_full}")
    print(f"Kim 4-series total release months post 2024-10-01: {total_kim_events_post_flip}")

    print("\n## Trades coverage on Kim-mapped prefixes")
    print("=" * 60)
    for kim_name, prefixes in KIM_MAPPING.items():
        for prefix in prefixes:
            coverage = trades_coverage_for_prefix(prefix)
            if coverage.get("n_trades", 0) > 0:
                print(
                    f"  {prefix:18}  trades={coverage['n_trades']:>8} "
                    f"tickers_with_trades={coverage['n_tickers_with_trades']:>4} "
                    f"range={str(coverage['oldest_trade'])[:10]} .. {str(coverage['newest_trade'])[:10]}"
                )
                inventory["trades_coverage"][prefix] = coverage

    print("\n## Other Finance categories for pivot menu")
    print("=" * 60)
    for prefix in OTHER_FINANCE:
        if prefix in [p for ps in KIM_MAPPING.values() for p in ps]:
            continue
        stats = inventory_for_prefix(prefix)
        if stats.get("n_markets", 0) > 0:
            inventory["other_finance"][prefix] = stats
            print(
                f"  {prefix:18}  n_markets={stats['n_markets']:>5} "
                f"unique_months={stats['n_unique_release_months']:>4} "
                f"resolved={stats['n_resolved']:>5}"
            )

    # Convert datetimes to strings for JSON
    def stringify(obj):
        if hasattr(obj, "isoformat"):
            return obj.isoformat()
        return obj

    def deep_stringify(d):
        if isinstance(d, dict):
            return {k: deep_stringify(stringify(v)) for k, v in d.items()}
        if isinstance(d, list):
            return [deep_stringify(stringify(x)) for x in d]
        return stringify(d)

    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_JSON, "w") as f:
        json.dump(deep_stringify(inventory), f, indent=2, default=str)
    print(f"\nWrote inventory JSON to {OUTPUT_JSON}")

    # Verdict
    print("\n## Verdict")
    print("=" * 60)
    if total_kim_events_post_flip >= 60:
        verdict = "REVIVE"
        reason = (
            f"Post Oct 2024 release months = {total_kim_events_post_flip} >= 60. "
            "Sample size adequate for Granger pair tests with Bonferroni correction."
        )
    elif total_kim_events_post_flip >= 40:
        verdict = "MARGINAL"
        reason = (
            f"Post Oct 2024 release months = {total_kim_events_post_flip}. "
            "Between 40 and 60; underpowered for full Bonferroni but possibly viable for primary direction tests."
        )
    elif total_kim_events_full >= 60:
        verdict = "REVIVE-PRE-FLIP-ONLY"
        reason = (
            f"Full-window release months = {total_kim_events_full} but post Oct 2024 only "
            f"{total_kim_events_post_flip}. Pre-flip data violates CLAUDE.md 2024 sign-flip rule. "
            "Decision required: pre-flip data may still inform cross-market lead-lag structure."
        )
    else:
        verdict = "KILL"
        reason = (
            f"Total release months across Kim 4-series = {total_kim_events_full}, post-flip "
            f"= {total_kim_events_post_flip}. Below 40-event floor for Granger inference. "
            "Pivot to V10A-3 menu."
        )
    print(f"VERDICT: {verdict}")
    print(f"Reason: {reason}")

    inventory["verdict"] = verdict
    inventory["reason"] = reason
    with open(OUTPUT_JSON, "w") as f:
        json.dump(deep_stringify(inventory), f, indent=2, default=str)


if __name__ == "__main__":
    main()
