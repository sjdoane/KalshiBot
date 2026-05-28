"""Quick category-level maker/taker excess return scan on Becker data.

Reproduces Becker's headline maker/taker gap analysis, restricted to post
October 2024 trades and resolved markets. Includes per-category Kalshi fee
estimate so the net excess return is what a retail trader would actually see.

Useful as a fast first pass before deeper sub-cell exploration.

Run via Becker .venv Python.
"""
from __future__ import annotations

import time
from pathlib import Path

import duckdb

REPO = Path(__file__).resolve().parents[2]
MARKETS = REPO / "prediction-market-analysis" / "data" / "kalshi" / "markets" / "*.parquet"
TRADES = REPO / "prediction-market-analysis" / "data" / "kalshi" / "trades" / "*.parquet"
OUTPUT_CSV = REPO / "research" / "v10a" / "becker-category-scan.csv"
CATEGORIES_PY = REPO / "prediction-market-analysis" / "src" / "analysis" / "kalshi" / "util" / "categories.py"

# Inline category extraction. Becker's actual util uses 568-entry pattern list;
# for a quick pass we use the regex prefix extract and map to high-level groups
# by simple rules. The agent's deeper pass will use the full Becker mapper.

GROUP_RULES = [
    ("NFL", "Sports"),
    ("NBA", "Sports"),
    ("MLB", "Sports"),
    ("NCAA", "Sports"),
    ("NHL", "Sports"),
    ("WNBA", "Sports"),
    ("ATP", "Sports"),
    ("WTA", "Sports"),
    ("UFC", "Sports"),
    ("BOXING", "Sports"),
    ("PGA", "Sports"),
    ("EPL", "Sports"),
    ("UCL", "Sports"),
    ("WC", "Sports"),
    ("F1", "Sports"),
    ("MARMAD", "Sports"),
    ("USOMENSINGLES", "Sports"),
    ("USOWOMEN", "Sports"),
    ("WMENSING", "Sports"),
    ("WWOMENSING", "Sports"),
    ("FOMENSING", "Sports"),
    ("FOWOMEN", "Sports"),
    ("MVENFL", "Sports"),
    ("MVENBA", "Sports"),
    ("MVE", "Esports"),
    ("LOL", "Esports"),
    ("CSGO", "Esports"),
    ("VALORANT", "Esports"),
    ("PRES", "Politics"),
    ("SENATE", "Politics"),
    ("HOUSE", "Politics"),
    ("GOV", "Politics"),
    ("TRUMP", "Politics"),
    ("BIDEN", "Politics"),
    ("CAB", "Politics"),
    ("POPVOTE", "Politics"),
    ("ELECTION", "Politics"),
    ("MAYOR", "Politics"),
    ("EC", "Politics"),
    ("VOTE", "Politics"),
    ("APRPOTUS", "Politics"),
    ("538APPROVE", "Politics"),
    ("BTC", "Crypto"),
    ("ETH", "Crypto"),
    ("DOGE", "Crypto"),
    ("SOL", "Crypto"),
    ("XRP", "Crypto"),
    ("COIN", "Crypto"),
    ("FED", "Finance"),
    ("CPI", "Finance"),
    ("PAYROLLS", "Finance"),
    ("U3", "Finance"),
    ("GDP", "Finance"),
    ("ACPI", "Finance"),
    ("INX", "Finance"),
    ("NASDAQ", "Finance"),
    ("TNOTE", "Finance"),
    ("USDJPY", "Finance"),
    ("EURUSD", "Finance"),
    ("WTI", "Finance"),
    ("GAS", "Finance"),
    ("PCECORE", "Finance"),
    ("RECSSNBER", "Finance"),
    ("TARIFF", "Finance"),
    ("PROLLS", "Finance"),
    ("RATECUT", "Finance"),
    ("HIGH", "Weather"),
    ("RAIN", "Weather"),
    ("SNOW", "Weather"),
    ("TORNADO", "Weather"),
    ("HURCAT", "Weather"),
    ("ARCTICICE", "Weather"),
    ("RT", "Entertainment"),
    ("OSCAR", "Entertainment"),
    ("GRAMMY", "Entertainment"),
    ("EMMY", "Entertainment"),
    ("SPOTIFY", "Entertainment"),
    ("NETFLIX", "Entertainment"),
    ("BILLBOARD", "Entertainment"),
    ("TOPARTIST", "Entertainment"),
    ("TOPSONG", "Entertainment"),
    ("TOPALBUM", "Entertainment"),
    ("APP", "Entertainment"),
    ("LLM", "ScienceTech"),
    ("AI", "ScienceTech"),
    ("SPACEX", "ScienceTech"),
    ("APPLE", "ScienceTech"),
    ("ALIENS", "ScienceTech"),
    ("NOBEL", "WorldEvents"),
    ("POPE", "WorldEvents"),
    ("EPSTEIN", "WorldEvents"),
    ("HEADLINE", "Media"),
    ("MENTION", "Media"),
    ("GOOGLESEARCH", "Media"),
    ("RANKLIST", "Media"),
    ("TSAW", "Other"),  # TSA passenger throughput, year-round
]


def group_case_sql() -> str:
    """Build a CASE expression mapping event_ticker prefix to high-level group."""
    cases = []
    for prefix, group in GROUP_RULES:
        cases.append(f"WHEN starts_with(prefix, '{prefix}') THEN '{group}'")
    return "CASE " + " ".join(cases) + " ELSE 'Unknown' END"


def main() -> None:
    t0 = time.time()
    con = duckdb.connect()

    # Build the full query: maker and taker excess returns by group,
    # restricted to post Oct 2024 resolved markets, with mean fee per trade.
    case_expr = group_case_sql()

    sql = f"""
    WITH resolved AS (
        SELECT
            ticker,
            event_ticker,
            result,
            regexp_extract(event_ticker, '^([A-Z0-9]+)', 1) AS prefix
        FROM '{MARKETS.as_posix()}'
        WHERE status = 'finalized' AND result IN ('yes', 'no')
    ),
    grouped AS (
        SELECT
            ticker, event_ticker, result, prefix,
            ({case_expr.replace("prefix", "prefix")}) AS group_name
        FROM resolved
    ),
    joined AS (
        SELECT
            t.ticker,
            t.yes_price,
            t.no_price,
            t.count,
            t.taker_side,
            t.created_time,
            m.result,
            m.group_name
        FROM '{TRADES.as_posix()}' t
        INNER JOIN grouped m ON t.ticker = m.ticker
        WHERE t.created_time >= '2024-10-01'
    ),
    taker_excess AS (
        SELECT
            group_name,
            -- Taker pays yes_price if taker_side=yes, no_price if taker_side=no
            -- Wins if taker_side equals result
            CASE WHEN taker_side = 'yes' THEN yes_price ELSE no_price END / 100.0 AS px,
            CASE WHEN taker_side = result THEN 1.0 ELSE 0.0 END AS won,
            count
        FROM joined
    ),
    maker_excess AS (
        SELECT
            group_name,
            -- Maker gets the opposite side
            CASE WHEN taker_side = 'yes' THEN no_price ELSE yes_price END / 100.0 AS px,
            CASE WHEN taker_side != result THEN 1.0 ELSE 0.0 END AS won,
            count
        FROM joined
    ),
    taker_stats AS (
        SELECT
            group_name,
            COUNT(*) AS n_trades,
            AVG(px) AS mean_px,
            AVG(won - px) AS gross_excess,
            -- Approx Kalshi taker fee per contract at this trade's price
            AVG(ceil(0.07 * px * (1.0 - px) * 100.0) / 100.0) AS mean_fee_per_contract,
            STDDEV_SAMP(won - px) AS sd_excess
        FROM taker_excess
        GROUP BY group_name
    ),
    maker_stats AS (
        SELECT
            group_name,
            COUNT(*) AS n_trades,
            AVG(px) AS mean_px,
            AVG(won - px) AS gross_excess,
            -- Maker fee is 25% of taker fee
            AVG(0.25 * ceil(0.07 * px * (1.0 - px) * 100.0) / 100.0) AS mean_fee_per_contract,
            STDDEV_SAMP(won - px) AS sd_excess
        FROM maker_excess
        GROUP BY group_name
    )
    SELECT
        COALESCE(t.group_name, m.group_name) AS group_name,
        t.n_trades AS taker_n,
        t.mean_px AS taker_mean_px,
        t.gross_excess * 100 AS taker_gross_pct,
        -- Fee is already in dollars per contract, par = $1, so subtract directly
        (t.gross_excess - t.mean_fee_per_contract) * 100 AS taker_net_pct,
        t.sd_excess,
        m.n_trades AS maker_n,
        m.mean_px AS maker_mean_px,
        m.gross_excess * 100 AS maker_gross_pct,
        (m.gross_excess - m.mean_fee_per_contract) * 100 AS maker_net_pct,
        m.sd_excess,
        -- Approx CI on net (1.96 * SD / sqrt(n), with SD on gross excess)
        1.96 * t.sd_excess / sqrt(t.n_trades) * 100 AS taker_ci_half,
        1.96 * m.sd_excess / sqrt(m.n_trades) * 100 AS maker_ci_half
    FROM taker_stats t
    FULL OUTER JOIN maker_stats m USING(group_name)
    ORDER BY (t.gross_excess + m.gross_excess) DESC
    """

    print("Running category scan (post Oct 2024, resolved markets)...")
    df = con.execute(sql).df()
    elapsed = time.time() - t0
    print(f"Query took {elapsed:.1f}s")
    print()
    print("Maker/Taker mean excess returns by category (post Oct 2024)")
    print("=" * 110)
    print(f"{'group':14} {'tk_n':>9} {'tk_px':>6} {'tk_gross':>9} {'tk_net':>8} {'tk_ci+/-':>9} "
          f"{'mk_n':>9} {'mk_px':>6} {'mk_gross':>9} {'mk_net':>8} {'mk_ci+/-':>9}")
    print("-" * 130)
    for _, row in df.iterrows():
        if (row.get("taker_n") or 0) < 1000 and (row.get("maker_n") or 0) < 1000:
            continue  # skip thin groups
        print(
            f"{(row['group_name'] or 'NA'):14} "
            f"{int(row['taker_n'] or 0):>9} {row['taker_mean_px'] or 0:>6.3f} "
            f"{row['taker_gross_pct'] or 0:>+9.3f} {row['taker_net_pct'] or 0:>+8.3f} {row['taker_ci_half'] or 0:>+9.3f} "
            f"{int(row['maker_n'] or 0):>9} {row['maker_mean_px'] or 0:>6.3f} "
            f"{row['maker_gross_pct'] or 0:>+9.3f} {row['maker_net_pct'] or 0:>+8.3f} {row['maker_ci_half'] or 0:>+9.3f}"
        )

    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_CSV, index=False)
    print(f"\nFull table saved to {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
