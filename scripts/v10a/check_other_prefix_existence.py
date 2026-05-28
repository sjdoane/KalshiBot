"""Check whether OTHER prefixes have ANY data in Becker post-Oct-2024,
regardless of regime filter, to disambiguate INSUFFICIENT from MISSING."""
from __future__ import annotations
from pathlib import Path
import duckdb

REPO = Path(__file__).resolve().parents[2]
MARKETS = REPO / "prediction-market-analysis" / "data" / "kalshi" / "markets" / "*.parquet"
TRADES = REPO / "prediction-market-analysis" / "data" / "kalshi" / "trades" / "*.parquet"

PREFIXES = [
    "KXNBAPLAYOFFWINS", "KXWCGAME", "KXUFCFIGHT", "KXIPLFINALS", "KXWCSTAGEOFELIM",
    "KXFOMEN", "KXBOXING", "KXNHLDRAFTPICK", "KXCS2", "KXWNBAWINS", "KXUFCOCCUR",
    "KXOWGRRANK", "KXPLAYWC", "KXNCAAFTOPAPRANK", "KXNEXTTEAMNBA", "KXNEXTTEAMNFL",
    "KXNEXTTEAMNHL", "KXSTARTINGQBWEEK1", "KXNFLPLAYOFF", "KXNHLSERIESSPREAD",
    "KXWCSQUAD", "KXNBAPOLOSE", "KXUCLTOTAL", "KXNFLWINS",
]

con = duckdb.connect()
print(f"{'prefix':22} {'tot_mkt':>10} {'fin_mkt':>10} {'tot_tr_post':>14}")
print("-" * 65)
for prefix in PREFIXES:
    sql = f"""
    SELECT
      COUNT(DISTINCT m.event_ticker) AS n_events,
      COUNT(DISTINCT CASE WHEN m.status='finalized' AND m.result IN ('yes','no') THEN m.event_ticker END) AS n_fin_events,
      COUNT(t.created_time) AS n_trades
    FROM '{MARKETS.as_posix()}' m
    LEFT JOIN '{TRADES.as_posix()}' t ON t.ticker = m.ticker AND t.created_time >= '2024-11-01'
    WHERE m.event_ticker LIKE '{prefix}%'
    """
    row = con.execute(sql).fetchone()
    print(f"{prefix:22} {row[0]:>10} {row[1]:>10} {row[2]:>14}")
