"""Phase 1 / Agent V4-A: enumerate v1's full series-prefix universe.

Builds the master table of every distinct series-prefix v1 has touched
in production or backtest, with counts from three sources:

  - data/live_trades/state.json (v1 runtime, attempted orders)
  - data/processed/sports_dataset.parquet (v1 backtest universe)
  - data/v3/probe_inventory_all_markets.parquet (v3 broader inventory)

Output: data/v4/v1_universe_series_table.parquet
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_V4 = REPO_ROOT / "data" / "v4"
DATA_V4.mkdir(parents=True, exist_ok=True)

LIVE_STATE = REPO_ROOT / "data" / "live_trades" / "state.json"
V1_BACKTEST = REPO_ROOT / "data" / "processed" / "sports_dataset.parquet"
V3_INVENTORY = REPO_ROOT / "data" / "v3" / "probe_inventory_all_markets.parquet"

OUTPUT = DATA_V4 / "v1_universe_series_table.parquet"

# League / category mapping for known series prefixes.
# Built from rules_primary keywords in v1's market scanner.
LEAGUE_MAP: dict[str, str] = {
    "KXNFLWINS": "NFL",
    "KXNFLGAME": "NFL",
    "KXNFLPLAYOFF": "NFL",
    "KXNFLTRADE": "NFL",
    "KXNFLAFCNORTH": "NFL",
    "KXNFLAFCWEST": "NFL",
    "KXNFLAFCEAST": "NFL",
    "KXNFLAFCSOUTH": "NFL",
    "KXNFLNFCNORTH": "NFL",
    "KXNFLNFCWEST": "NFL",
    "KXNFLNFCEAST": "NFL",
    "KXNFLNFCSOUTH": "NFL",
    "KXNFLMVP": "NFL",
    "KXNFLDPOY": "NFL",
    "KXNFLOPOY": "NFL",
    "KXNFLDROY": "NFL",
    "KXNFLOROY": "NFL",
    "KXNFLCOACH": "NFL",
    "KXNFLNEXTHC": "NFL",
    "KXNFL": "NFL",
    "KXSTARTINGQBWEEK1": "NFL",
    "KXSTARTCLEBROWNS": "NFL",
    "KXNEXTTEAMNFL": "NFL",
    "KXNCAAF": "NCAA-FB",
    "KXNCAAFPLAYOFF": "NCAA-FB",
    "KXNCAAFGAME": "NCAA-FB",
    "KXNCAAFMVP": "NCAA-FB",
    "KXNCAAMBACHAMP": "NCAA-MB",
    "KXNCAAW": "NCAA-WB",
    "KXMLBWINS": "MLB",
    "KXMLBGAME": "MLB",
    "KXMLBPLAYOFFS": "MLB",
    "KXMLBPLAYOFF": "MLB",
    "KXMLB": "MLB",
    "KXMLBALEAST": "MLB",
    "KXMLBALCENT": "MLB",
    "KXMLBALWEST": "MLB",
    "KXMLBNLEAST": "MLB",
    "KXMLBNLCENT": "MLB",
    "KXMLBNLWEST": "MLB",
    "KXMLBALCY": "MLB",
    "KXMLBNLCY": "MLB",
    "KXMLBALMVP": "MLB",
    "KXMLBNLMVP": "MLB",
    "KXMLBALROTY": "MLB",
    "KXMLBNLROTY": "MLB",
    "KXMLBSTATCOUNT": "MLB",
    "KXMLBDIVWINNER": "MLB",
    "KXMLBAL": "MLB",
    "KXMLBNL": "MLB",
    "KXNBAWINS": "NBA",
    "KXNBAPLAYOFF": "NBA",
    "KXNBAPLAYOFFWINS": "NBA",
    "KXNBAMVP": "NBA",
    "KXNBADPOY": "NBA",
    "KXNBASIXTH": "NBA",
    "KXNBAMIMP": "NBA",
    "KXNBAROTY": "NBA",
    "KXNBAEAST": "NBA",
    "KXNBAWEST": "NBA",
    "KXNBAATLANTIC": "NBA",
    "KXNBACENTRAL": "NBA",
    "KXNBASOUTHEAST": "NBA",
    "KXNBANORTHWEST": "NBA",
    "KXNBAPACIFIC": "NBA",
    "KXNBASOUTHWEST": "NBA",
    "KXNBA": "NBA",
    "KXLEADERNBAAST": "NBA",
    "KXLEADERNBAPTS": "NBA",
    "KXLEADERNBAREB": "NBA",
    "KXCITYNBAEXPAND": "NBA",
    "KXWNBAWINS": "WNBA",
    "KXWNBAROTY": "WNBA",
    "KXWNBAMVP": "WNBA",
    "KXNHL": "NHL",
    "KXNHLPLAYOFF": "NHL",
    "KXNHLPRES": "NHL",
    "KXNHLATLANTIC": "NHL",
    "KXNHLMETROPOLITAN": "NHL",
    "KXNHLCENTRAL": "NHL",
    "KXNHLPACIFIC": "NHL",
    "KXNHLEAST": "NHL",
    "KXNHLWEST": "NHL",
    "KXNHLCONN": "NHL",
    "KXNHLVEZINA": "NHL",
    "KXNHLNORRIS": "NHL",
    "KXNHLHART": "NHL",
    "KXNEXTTEAMNHL": "NHL",
    "KXWCSQUAD": "Soccer-WC",
    "KXWCGAME": "Soccer-WC",
    "KXWCSTAGEOFELIM": "Soccer-WC",
    "KXMLSGAME": "MLS",
    "KXMLSPLAYOFFS": "MLS",
    "KXMLSCUP": "MLS",
    "KXUCLROUND": "UCL",
    "KXUCL": "UCL",
    "KXEPLGAME": "EPL",
    "KXEPL": "EPL",
    "KXLALIGA": "LaLiga",
    "KXBUNDESLIGA": "Bundesliga",
    "KXBUNDESLIGA1": "Bundesliga",
    "KXSERIEA": "SerieA",
    "KXLIGUE1": "Ligue1",
    "KXFACUP": "FA-Cup",
    "KXCOPADELREY": "CopaDelRey",
    "KXBALLONDOR": "Ballon-DOr",
    "KXIPLFINAL": "IPL-Cricket",
    "KXIPL": "IPL-Cricket",
    "KXFOMEN": "Formula-1",
    "KXFOWMEN": "Formula-1",
    "KXBOXING": "Boxing",
    "KXUFCFIGHT": "UFC-MMA",
    "KXUFC": "UFC-MMA",
    "KXCS2": "CS2-Esports",
    "KXVALORANT": "Valorant-Esports",
    "KXLOL": "LoL-Esports",
    "KXCHARCOUNTLOLWORLDS": "LoL-Esports",
    "KXATP": "Tennis-ATP",
    "KXATPGRANDSLAM": "Tennis-ATP",
    "KXWTAGRANDSLAM": "Tennis-WTA",
    "KXWTA": "Tennis-WTA",
    "KXPGA": "Golf-PGA",
    "KXLPGA": "Golf-LPGA",
    "KXTGL": "Golf-TGL",
    "KXTGLCHAMPION": "Golf-TGL",
    "KXMASTERS": "Golf-Majors",
    "KXOPEN": "Golf-Majors",
    "KXNEWCOACHNO": "Coach-Hiring",
    "KXCARDPRESENCEUFCWH": "UFC-MMA",
    "KXCHESSCANDIDATES": "Chess",
    "KXCHESSWORLDCHAMPION": "Chess",
    "KXSWIFTATTEND": "Entertainment",
}


def series_prefix(ticker: str) -> str:
    """Series-prefix = everything up to (but not including) the first hyphen."""
    return ticker.split("-", 1)[0]


def categorize(series: str) -> str:
    if series in LEAGUE_MAP:
        return LEAGUE_MAP[series]
    # heuristic fallback for series we haven't manually mapped
    if series.startswith("KXNFL"):
        return "NFL"
    if series.startswith("KXNCAAF"):
        return "NCAA-FB"
    if series.startswith("KXNCAAM"):
        return "NCAA-MB"
    if series.startswith("KXMLB"):
        return "MLB"
    if series.startswith("KXNBA"):
        return "NBA"
    if series.startswith("KXWNBA"):
        return "WNBA"
    if series.startswith("KXNHL"):
        return "NHL"
    if series.startswith("KXWC"):
        return "Soccer-WC"
    if series.startswith("KXMLS"):
        return "MLS"
    if series.startswith("KXUCL"):
        return "UCL"
    if series.startswith("KXEPL"):
        return "EPL"
    if series.startswith("KXUFC"):
        return "UFC-MMA"
    if series.startswith("KXATP") or series.startswith("KXWTA"):
        return "Tennis"
    if series.startswith("KXPGA") or series.startswith("KXLPGA") or series.startswith("KXMASTERS") or series.startswith("KXTGL"):
        return "Golf"
    if series.startswith("KXLOL") or series.startswith("KXCS") or series.startswith("KXVALORANT"):
        return "Esports"
    return "Other-Sports"


def count_live_state() -> Counter:
    """Count series-prefix occurrences across ALL state buckets."""
    with open(LIVE_STATE) as f:
        state = json.load(f)
    counts: Counter = Counter()
    for bucket in ("intents", "resting", "filled", "closed"):
        for order in state.get(bucket, {}).values():
            ticker = order.get("ticker")
            if ticker:
                counts[series_prefix(ticker)] += 1
    return counts


def count_live_filled_or_resting() -> Counter:
    """Count series-prefix among only orders v1 actually placed (acked)."""
    with open(LIVE_STATE) as f:
        state = json.load(f)
    counts: Counter = Counter()
    for bucket in ("resting", "filled"):
        for order in state.get(bucket, {}).values():
            ticker = order.get("ticker")
            if ticker:
                counts[series_prefix(ticker)] += 1
    return counts


def count_backtest() -> Counter:
    """All rows in v1's sports_dataset.parquet."""
    df = pd.read_parquet(V1_BACKTEST)
    counts: Counter = Counter()
    for ticker in df["ticker"]:
        counts[series_prefix(ticker)] += 1
    return counts


def count_backtest_v1_eligible() -> Counter:
    """v1-eligible rows: lifetime 30-180d, mid_price_at_T_small in [0.70, 0.95]."""
    df = pd.read_parquet(V1_BACKTEST)
    elig = df[
        (df["lifetime_days"] >= 30)
        & (df["lifetime_days"] <= 180)
        & (df["mid_price_at_T_small"] >= 0.70)
        & (df["mid_price_at_T_small"] <= 0.95)
    ]
    counts: Counter = Counter()
    for ticker in elig["ticker"]:
        counts[series_prefix(ticker)] += 1
    return counts


def count_v3_inventory() -> Counter:
    """All rows in v3 probe inventory."""
    df = pd.read_parquet(V3_INVENTORY)
    counts: Counter = Counter()
    for ticker in df["ticker"]:
        counts[series_prefix(ticker)] += 1
    return counts


def count_v3_inventory_eligible() -> Counter:
    """v3 inventory rows passing eligibility flags."""
    df = pd.read_parquet(V3_INVENTORY)
    elig = df[df["eligible_narrow"] | df["eligible_wide"]]
    counts: Counter = Counter()
    for ticker in elig["ticker"]:
        counts[series_prefix(ticker)] += 1
    return counts


def main() -> None:
    live_all = count_live_state()
    live_filled_resting = count_live_filled_or_resting()
    backtest_all = count_backtest()
    backtest_elig = count_backtest_v1_eligible()
    v3_all = count_v3_inventory()
    v3_elig = count_v3_inventory_eligible()

    all_series = set(live_all) | set(backtest_all) | set(v3_all)

    rows = []
    for s in sorted(all_series):
        rows.append({
            "series_prefix": s,
            "league": categorize(s),
            "v1_live_all_orders": live_all.get(s, 0),
            "v1_live_acked_orders": live_filled_resting.get(s, 0),
            "v1_backtest_all": backtest_all.get(s, 0),
            "v1_backtest_eligible": backtest_elig.get(s, 0),
            "v3_inventory_all": v3_all.get(s, 0),
            "v3_inventory_eligible": v3_elig.get(s, 0),
        })

    df = pd.DataFrame(rows)
    df = df.sort_values(
        ["v1_live_all_orders", "v1_backtest_eligible", "v3_inventory_eligible"],
        ascending=[False, False, False],
    )
    df.to_parquet(OUTPUT, index=False)

    print(f"Wrote {len(df)} series-prefixes to {OUTPUT}")
    print()
    print("Top 30 by v1-live + v1-backtest + v3-inventory:")
    print(df.head(30).to_string(index=False))
    print()
    print(f"v1-live distinct series: {sum(1 for r in rows if r['v1_live_all_orders'] > 0)}")
    print(f"v1-backtest distinct series: {sum(1 for r in rows if r['v1_backtest_all'] > 0)}")
    print(f"v3-inventory distinct series: {sum(1 for r in rows if r['v3_inventory_all'] > 0)}")
    print(f"Union: {len(df)}")


if __name__ == "__main__":
    main()
