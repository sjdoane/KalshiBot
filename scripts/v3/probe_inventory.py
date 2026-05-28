"""v3 historical-market inventory probe.

For every sports series with possible v1 overlap, count the markets that
clear v1's eligibility filter:
  - YES price at T-35d in [0.70, 0.95] (VWAP of trades in
    [close - 36d, close - 34d], matching v1's trading-window method)
  - Market lifetime (close_time - open_time) in [30d, 180d]
  - Status = finalized, result in {yes, no}
  - Sport category (implicitly: series is sports)

Output: data/v3/probe_inventory_summary.parquet (per-series rollup),
data/v3/probe_<series>.parquet (per-market eligibility per series),
plus a console summary the orchestrator can paste into the markdown.

Run as: uv run python -m scripts.v3.probe_inventory

This script is READ-ONLY. It hits the Kalshi /historical/trades endpoint
only when a series' eligible market has no usable trades cached in
data/sports/trades. Polite throttle: < 10 req/sec.

It does NOT modify v1 (src/kalshi_bot/, scripts/, tests/, data/ outside
data/v3/), nor .env.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from kalshi_bot.config import Settings  # noqa: E402
from kalshi_bot.data.kalshi_client import (  # noqa: E402
    KalshiClient,
    KalshiHTTPError,
)

MARKETS_DIR = REPO_ROOT / "data" / "sports" / "markets"
TRADES_DIR = REPO_ROOT / "data" / "sports" / "trades"
OUT_DIR = REPO_ROOT / "data" / "v3"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# v1's eligibility filter (from src/kalshi_bot/strategy/favorite_maker.py
# and research/favorite-maker-results.md, Round 7).
FAVORITE_PRICE_LOW = 0.70
FAVORITE_PRICE_HIGH = 0.95
LIFETIME_MIN_DAYS = 30
LIFETIME_MAX_DAYS = 180

# Trading-window mid: close - 35d. VWAP over trades in [mid-1d, mid+1d]
# (i.e. [close-36d, close-34d]). The brief specifies +/- 1d (a 2-day
# window) per the spec; scripts/v2/build_mlb_longhorizon_dataset.py uses
# +/- 7d (the v1 trading window). For an inventory probe the narrower
# +/- 1d window the brief asks for produces the *price at T-35d*; the
# wider window the v1 strategy actually trades in is what matters for
# v1 actually buying. We compute BOTH so the next agent can pick.
T35_WINDOW_HALF_DAYS = 1
WIDE_WINDOW_HALF_DAYS = 7

# Series the master plan brief explicitly named, plus their actual
# Kalshi naming where it differs.
#
# Brief asked for: KXMLBWINS, KXMLBALEAST, KXMLBPLAYOFFS, KXMLBALMVP,
# KXMLBNLEAST, KXMLBNLMVP, KXNBAWINS, KXNBAFINALS, KXNBAMVP, KXNFLWINS,
# KXNFLSB, KXNFLMVP, KXNHLWINS, KXNHLSC, KXNHLMVP, NCAA equivalents.
#
# Naming map (verified against data/sports/markets):
#   KXNBAWINS -> KXNBAWINS                  (the win-record series)
#   KXNBAFINALS -> KXNBA                    (championship parent series)
#   KXNBAMVP -> KXNBAFINMVP                 (Finals MVP)
#   KXNFLWINS -> KXNFLWINS-{TEAM}            (per-team)
#   KXNFLSB -> KXNFLAFCCHAMP, KXNFLNFCCHAMP (conf champs; Super Bowl is
#                                            implied via these; SB
#                                            itself is short-horizon
#                                            game market)
#   KXNFLMVP -> KXNFLMVP
#   KXNHLWINS -> (no per-team WINS series exists; use KXNHLPRES for
#                president's trophy proxy, and KXNHLPLAYOFF for playoff
#                qualifier)
#   KXNHLSC -> KXNHL                        (Stanley Cup)
#   KXNHLMVP -> not found in cache
#   NCAA -> KXNCAAF (CFP champ), KXNCAAFPLAYOFF (CFP qualifier),
#           KXNCAAFB10, KXNCAAFB12, KXNCAAFSEC, KXNCAAFACC (conf
#           champions), KXNCAAMBNAISMITH (player of year),
#           KXNCAAMBACHAMP (MB conf champion bucket).

SERIES_GROUPS: dict[str, list[str]] = {
    "mlb_team_wins": [f"KXMLBWINS-{t}" for t in [
        "ATH", "ATL", "AZ", "BAL", "BOS", "CHC", "CIN", "CLE", "COL",
        "CWS", "DET", "HOU", "KC", "LAA", "LAD", "MIA", "MIL", "MIN",
        "NYM", "NYY", "PHI", "PIT", "SD", "SEA", "SF", "STL", "TB",
        "TEX", "TOR", "WSH",
    ]],
    "mlb_division": [
        "KXMLBALEAST", "KXMLBALCENT", "KXMLBALWEST",
        "KXMLBNLEAST", "KXMLBNLCENT", "KXMLBNLWEST",
        "KXMLBAL", "KXMLBNL",
    ],
    "mlb_playoffs": ["KXMLBPLAYOFFS"],
    "mlb_championship": ["KXMLB"],
    "mlb_awards": [
        "KXMLBALMVP", "KXMLBNLMVP", "KXMLBALCY", "KXMLBNLCY",
        "KXMLBALROTY", "KXMLBNLROTY",
    ],
    "mlb_world_classic": ["KXMLBWORLD"],
    "nba_championship": ["KXNBA"],
    "nba_conference": ["KXNBAEAST", "KXNBAWEST"],
    "nba_division": [
        "KXNBAATLANTIC", "KXNBACENTRAL", "KXNBANORTHWEST",
        "KXNBAPACIFIC", "KXNBASOUTHEAST", "KXNBASOUTHWEST",
    ],
    "nba_playoffs": ["KXNBAPLAYOFF"],
    "nba_finals_mvp": ["KXNBAFINMVP"],
    "nba_wins": ["KXNBAWINS"],
    "nba_awards": ["KXNBAROY", "KXNBADPOY", "KXNBAMIMP", "KXNBASIXTH"],
    "nfl_conf_champ": ["KXNFLAFCCHAMP", "KXNFLNFCCHAMP"],
    "nfl_division": [
        "KXNFLAFCEAST", "KXNFLAFCNORTH", "KXNFLAFCSOUTH", "KXNFLAFCWEST",
        "KXNFLNFCEAST", "KXNFLNFCNORTH", "KXNFLNFCSOUTH", "KXNFLNFCWEST",
    ],
    "nfl_playoffs": ["KXNFLPLAYOFF"],
    "nfl_team_wins": [f"KXNFLWINS-{t}" for t in [
        "ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE", "DAL",
        "DEN", "DET", "GB", "HOU", "IND", "JAC", "KC", "LA", "LAC",
        "LV", "MIA", "MIN", "NE", "NO", "NYG", "NYJ", "PHI", "PIT",
        "SEA", "SF", "TB", "TEN", "WAS",
    ]],
    "nfl_mvp": ["KXNFLMVP"],
    "nhl_stanley_cup": ["KXNHL"],
    "nhl_pres_trophy": ["KXNHLPRES"],
    "nhl_playoff_qual": ["KXNHLPLAYOFF"],
    "nhl_conf": ["KXNHLEAST", "KXNHLWEST"],
    "nhl_division": [
        "KXNHLATLANTIC", "KXNHLCENTRAL", "KXNHLMETROPOLITAN",
        "KXNHLPACIFIC",
    ],
    "ncaaf_champ": ["KXNCAAF"],
    "ncaaf_playoff_qual": ["KXNCAAFPLAYOFF"],
    "ncaaf_finalist": ["KXNCAAFFINALIST"],
    "ncaaf_undefeated": ["KXNCAAFUNDEFEATED"],
    "ncaaf_conf": [
        "KXNCAAFACC", "KXNCAAFB10", "KXNCAAFB12", "KXNCAAFCS",
        "KXNCAAFSEC",
    ],
    "ncaab_champ_award": ["KXNCAAMBNAISMITH"],
    "ncaab_conf_champ": [
        "KXNCAAMBACC", "KXNCAAMBBIG10", "KXNCAAMBBIG12",
        "KXNCAAMBBIGEAST", "KXNCAAMBSEC", "KXNCAAMBACHAMP",
    ],
}


def load_markets(series_ticker: str) -> pd.DataFrame:
    p = MARKETS_DIR / f"{series_ticker}.parquet"
    if not p.exists():
        return pd.DataFrame()
    df = pd.read_parquet(p)
    if df.empty:
        return df
    df["series_ticker"] = series_ticker
    return df


def load_trades(series_ticker: str) -> pd.DataFrame:
    p = TRADES_DIR / f"{series_ticker}.parquet"
    if not p.exists():
        return pd.DataFrame()
    return pd.read_parquet(p)


def extract_entity(ticker: str, series_ticker: str) -> str:
    """Best-effort entity (team/candidate) extraction from ticker.

    The brief asks for single-entity concentration (the v2 COL-as-
    opponent check). The naming convention varies:
      KXMLBWINS-NYY-25-T90 -> NYY
      KXMLBALEAST-25-NYY  -> NYY
      KXNFLAFCCHAMP-25-PIT -> PIT
      KXNBA-26-POR        -> POR
      KXNBAFINMVP-25-NJOK -> NJOK (player initials code)
      KXMLB-25-WAS        -> WAS
    """
    # Strip series prefix (and team-suffix for per-team WINS series)
    base = ticker
    if series_ticker.startswith("KXMLBWINS-") or series_ticker.startswith(
        "KXNFLWINS-"
    ):
        # KXMLBWINS-{TEAM}-{YY}-T{N} -> entity = the team (already in
        # series); the threshold is the within-series variation. The
        # *team* is the entity for concentration purposes.
        parts = series_ticker.split("-", 1)
        if len(parts) == 2:
            return parts[1]
    parts = base.split("-")
    if len(parts) >= 3:
        # Last segment is usually the entity for league-wide series
        return parts[-1]
    return "?"


def vwap_at_t35(trades: pd.DataFrame, close_time: pd.Timestamp,
                half_days: float = 1.0) -> dict[str, Any]:
    """VWAP of trades within [close - 35d - half, close - 35d + half].

    Returns vwap, n_trades, has_data.
    """
    if trades.empty or "created_time" not in trades.columns:
        return {"vwap": None, "n_trades": 0, "has_data": False}
    sub = trades.copy()
    sub["ts"] = pd.to_datetime(sub["created_time"], utc=True)
    mid = close_time - pd.Timedelta(days=35)
    ws = mid - pd.Timedelta(days=half_days)
    we = mid + pd.Timedelta(days=half_days)
    sub = sub[(sub["ts"] >= ws) & (sub["ts"] <= we)]
    if sub.empty:
        return {"vwap": None, "n_trades": 0, "has_data": False}
    # yes_price (dollars) and count parsing
    if "yes_price_dollars" in sub.columns:
        sub["price"] = pd.to_numeric(sub["yes_price_dollars"], errors="coerce")
    elif "yes_price" in sub.columns:
        sub["price"] = pd.to_numeric(sub["yes_price"], errors="coerce") / 100.0
    else:
        return {"vwap": None, "n_trades": int(len(sub)), "has_data": False}
    if "count_fp" in sub.columns:
        sub["q"] = pd.to_numeric(sub["count_fp"], errors="coerce")
    elif "count" in sub.columns:
        sub["q"] = pd.to_numeric(sub["count"], errors="coerce")
    else:
        return {"vwap": None, "n_trades": int(len(sub)), "has_data": False}
    sub = sub[(sub["q"] > 0) & sub["price"].notna()]
    if sub.empty:
        return {"vwap": None, "n_trades": 0, "has_data": False}
    tot_q = float(sub["q"].sum())
    vwap = float((sub["price"] * sub["q"]).sum() / tot_q)
    return {"vwap": vwap, "n_trades": int(len(sub)), "has_data": True}


def fetch_trades_for_market(
    client: KalshiClient, ticker: str, close_time: pd.Timestamp,
    half_days: float = 7.0,
) -> pd.DataFrame:
    """Pull the trade window from the Kalshi /historical/trades endpoint.

    Window: [close - 35 - half, close - 35 + half]. Returns DataFrame or
    empty.
    """
    mid = close_time - pd.Timedelta(days=35)
    ws = mid - pd.Timedelta(days=half_days)
    we = mid + pd.Timedelta(days=half_days)
    try:
        rows = list(client.paginate(
            "/historical/trades",
            item_key="trades",
            limit=1000,
            ticker=ticker,
            min_ts=int(ws.timestamp()),
            max_ts=int(we.timestamp()),
        ))
    except KalshiHTTPError:
        return pd.DataFrame()
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


def process_series(
    series_ticker: str, group: str, client: KalshiClient | None,
    cutoff_ts: pd.Timestamp | None, do_fetch: bool,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Run the eligibility filter on one series. Returns (per-market
    df, summary dict)."""
    markets = load_markets(series_ticker)
    if markets.empty:
        return pd.DataFrame(), {
            "series_ticker": series_ticker, "group": group,
            "total_markets": 0, "eligible_n": 0, "missing": True,
        }
    # Type/cast time columns
    markets["close_time"] = pd.to_datetime(
        markets["close_time"], utc=True, format="ISO8601", errors="coerce",
    )
    markets["open_time"] = pd.to_datetime(
        markets["open_time"], utc=True, format="ISO8601", errors="coerce",
    )
    markets["lifetime_days"] = (
        (markets["close_time"] - markets["open_time"]).dt.total_seconds()
        / 86400.0
    )
    # Coarse filters: finalized status + binary result
    pre = len(markets)
    markets = markets[
        markets["status"].astype(str).isin(["finalized", "settled"])
    ].copy()
    n_after_status = len(markets)
    if "market_type" in markets.columns:
        markets = markets[markets["market_type"] == "binary"].copy()
    n_after_binary = len(markets)
    if "result" not in markets.columns:
        return pd.DataFrame(), {
            "series_ticker": series_ticker, "group": group,
            "total_markets": pre, "eligible_n": 0,
            "note": "no result column",
        }
    markets = markets[markets["result"].isin(["yes", "no"])].copy()
    n_after_result = len(markets)
    # Lifetime filter
    markets["lifetime_ok"] = (
        (markets["lifetime_days"] >= LIFETIME_MIN_DAYS)
        & (markets["lifetime_days"] <= LIFETIME_MAX_DAYS)
    )
    n_lifetime_ok = int(markets["lifetime_ok"].sum())
    # Now compute price at T-35d via trades
    trades = load_trades(series_ticker)
    rows: list[dict[str, Any]] = []
    fetched_count = 0
    for _, m in markets.iterrows():
        ticker = m["ticker"]
        close_t = m["close_time"]
        if pd.isna(close_t):
            continue
        # Narrow window (the brief's T-35d definition)
        narrow = vwap_at_t35(
            trades[trades["ticker"] == ticker] if not trades.empty
            else trades, close_t, half_days=T35_WINDOW_HALF_DAYS,
        )
        # Wide window (v1's actual trading window mid)
        wide = vwap_at_t35(
            trades[trades["ticker"] == ticker] if not trades.empty
            else trades, close_t, half_days=WIDE_WINDOW_HALF_DAYS,
        )
        # Fetch if both windows are empty and we have a client
        if (not wide["has_data"]) and do_fetch and client is not None:
            fetched = fetch_trades_for_market(client, ticker, close_t,
                                              half_days=WIDE_WINDOW_HALF_DAYS)
            fetched_count += 1
            if not fetched.empty:
                narrow = vwap_at_t35(fetched, close_t,
                                     half_days=T35_WINDOW_HALF_DAYS)
                wide = vwap_at_t35(fetched, close_t,
                                   half_days=WIDE_WINDOW_HALF_DAYS)
            # Polite throttle
            time.sleep(0.12)
        rows.append({
            "ticker": ticker,
            "series_ticker": series_ticker,
            "group": group,
            "open_time": m["open_time"],
            "close_time": close_t,
            "lifetime_days": float(m["lifetime_days"]),
            "lifetime_ok": bool(m["lifetime_ok"]),
            "result": m["result"],
            "outcome": 1 if m["result"] == "yes" else 0,
            "vwap_t35_narrow": narrow["vwap"],
            "vwap_t35_narrow_n": narrow["n_trades"],
            "vwap_t35_wide": wide["vwap"],
            "vwap_t35_wide_n": wide["n_trades"],
            "entity": extract_entity(ticker, series_ticker),
        })
    df = pd.DataFrame(rows)
    if df.empty:
        return df, {
            "series_ticker": series_ticker, "group": group,
            "total_markets": pre, "n_after_status": n_after_status,
            "n_after_binary": n_after_binary,
            "n_after_result": n_after_result,
            "n_lifetime_ok": n_lifetime_ok, "eligible_n": 0,
            "fetched_count": fetched_count,
        }
    # Eligibility
    df["price"] = df["vwap_t35_narrow"].fillna(df["vwap_t35_wide"])
    df["eligible_narrow"] = (
        df["lifetime_ok"]
        & df["vwap_t35_narrow"].notna()
        & (df["vwap_t35_narrow"] >= FAVORITE_PRICE_LOW)
        & (df["vwap_t35_narrow"] <= FAVORITE_PRICE_HIGH)
    )
    df["eligible_wide"] = (
        df["lifetime_ok"]
        & df["vwap_t35_wide"].notna()
        & (df["vwap_t35_wide"] >= FAVORITE_PRICE_LOW)
        & (df["vwap_t35_wide"] <= FAVORITE_PRICE_HIGH)
    )
    # Pre / post cutoff
    if cutoff_ts is not None:
        df["pre_cutoff"] = df["close_time"] < cutoff_ts
    else:
        df["pre_cutoff"] = None
    summary = {
        "series_ticker": series_ticker,
        "group": group,
        "total_markets": int(pre),
        "n_after_status": int(n_after_status),
        "n_after_binary": int(n_after_binary),
        "n_after_result": int(n_after_result),
        "n_lifetime_ok": int(n_lifetime_ok),
        "n_with_t35_price_narrow": int(df["vwap_t35_narrow"].notna().sum()),
        "n_with_t35_price_wide": int(df["vwap_t35_wide"].notna().sum()),
        "eligible_n_narrow": int(df["eligible_narrow"].sum()),
        "eligible_n_wide": int(df["eligible_wide"].sum()),
        "earliest_close": df["close_time"].min(),
        "latest_close": df["close_time"].max(),
        "mean_lifetime_eligible_wide": float(
            df.loc[df["eligible_wide"], "lifetime_days"].mean()
        ) if int(df["eligible_wide"].sum()) > 0 else None,
        "mean_price_eligible_wide": float(
            df.loc[df["eligible_wide"], "vwap_t35_wide"].mean()
        ) if int(df["eligible_wide"].sum()) > 0 else None,
        "eligible_yes_rate_wide": float(
            df.loc[df["eligible_wide"], "outcome"].mean()
        ) if int(df["eligible_wide"].sum()) > 0 else None,
        "fetched_count": fetched_count,
    }
    return df, summary


def main() -> int:
    settings = Settings()
    # Hit /historical/cutoff once to get the timeline divider
    cutoff_ts = None
    try:
        with KalshiClient(settings) as client:
            cutoff_resp = client.get("/historical/cutoff")
            print(f"/historical/cutoff -> {cutoff_resp}")
            # Response: {"cutoff_ts": <unix_seconds>} usually
            for k, v in (cutoff_resp or {}).items():
                if "cutoff" in k.lower() or k.lower() == "ts":
                    try:
                        cutoff_ts = pd.to_datetime(int(v), unit="s", utc=True)
                        break
                    except (ValueError, TypeError):
                        try:
                            cutoff_ts = pd.to_datetime(v, utc=True)
                            break
                        except (ValueError, TypeError):
                            pass
            print(f"parsed cutoff: {cutoff_ts}")
    except Exception as e:  # noqa: BLE001
        print(f"cutoff lookup failed: {e}")

    do_fetch = True  # let it fetch trades when local cache is empty

    all_market_rows: list[pd.DataFrame] = []
    summaries: list[dict[str, Any]] = []
    with KalshiClient(settings) as client:
        for group, series_list in SERIES_GROUPS.items():
            for s in series_list:
                t0 = time.time()
                df, summ = process_series(
                    s, group, client, cutoff_ts, do_fetch,
                )
                elapsed = time.time() - t0
                print(
                    f"  {group:25s} {s:32s} total={summ.get('total_markets', 0):5d} "
                    f"lifetime_ok={summ.get('n_lifetime_ok', 0):4d} "
                    f"with_t35={summ.get('n_with_t35_price_wide', 0):4d} "
                    f"elig_w={summ.get('eligible_n_wide', 0):4d} "
                    f"elig_n={summ.get('eligible_n_narrow', 0):4d} "
                    f"fetched={summ.get('fetched_count', 0):3d} "
                    f"({elapsed:.1f}s)"
                )
                if not df.empty:
                    all_market_rows.append(df)
                    out_p = OUT_DIR / f"probe_{s}.parquet"
                    df.to_parquet(out_p, index=False)
                summaries.append(summ)

    summary_df = pd.DataFrame(summaries)
    summary_p = OUT_DIR / "probe_inventory_summary.parquet"
    summary_df.to_parquet(summary_p, index=False)
    print(f"\nSeries summary saved to {summary_p}")

    all_df: pd.DataFrame = pd.DataFrame()
    if all_market_rows:
        all_df = pd.concat(all_market_rows, ignore_index=True)
        all_df.to_parquet(OUT_DIR / "probe_inventory_all_markets.parquet",
                          index=False)
        print(f"All markets saved to {OUT_DIR / 'probe_inventory_all_markets.parquet'}")

    # Aggregate
    print()
    print("=" * 72)
    print("AGGREGATE")
    print("=" * 72)
    if all_df.empty:
        print("No data.")
        return 1

    elig = all_df[all_df["eligible_wide"]]
    elig_narrow = all_df[all_df["eligible_narrow"]]
    print(f"Total markets considered:     {len(all_df)}")
    print(f"Eligible (wide T-35 +/-7d):   {len(elig)}")
    print(f"Eligible (narrow T-35 +/-1d): {len(elig_narrow)}")
    print(f"Cutoff (parsed):              {cutoff_ts}")
    if cutoff_ts is not None and not elig.empty:
        pre = int((elig["close_time"] < cutoff_ts).sum())
        post = int((elig["close_time"] >= cutoff_ts).sum())
        print(f"  Eligible pre-cutoff:        {pre}")
        print(f"  Eligible post-cutoff:       {post}")

    # Per-group
    print()
    print("Eligible by group (wide window):")
    print(elig.groupby("group").size().sort_values(ascending=False).to_string())

    # Single-entity concentration
    print()
    print("Top single-entity counts in eligible (wide):")
    print(elig.groupby("entity").size().sort_values(ascending=False).head(15).to_string())

    # Lifetime histogram in 30-day buckets
    print()
    print("Lifetime histogram (eligible wide, 30-day buckets):")
    if not elig.empty:
        bucket = (elig["lifetime_days"] // 30).astype(int)
        for b, c in bucket.value_counts().sort_index().items():
            print(f"  [{b*30:3d}, {(b+1)*30:3d}) days: {c}")

    # Time concentration
    print()
    print("Eligible close-time by year (wide):")
    if not elig.empty:
        years = elig["close_time"].dt.year
        for y, c in years.value_counts().sort_index().items():
            print(f"  {y}: {c}")

    # Persist summary JSON
    meta = {
        "timestamp": pd.Timestamp.utcnow().isoformat(),
        "filter": {
            "favorite_price_band": [FAVORITE_PRICE_LOW, FAVORITE_PRICE_HIGH],
            "lifetime_band_days": [LIFETIME_MIN_DAYS, LIFETIME_MAX_DAYS],
            "t35_window_half_days_narrow": T35_WINDOW_HALF_DAYS,
            "t35_window_half_days_wide": WIDE_WINDOW_HALF_DAYS,
        },
        "kalshi_cutoff": (
            cutoff_ts.isoformat() if cutoff_ts is not None else None
        ),
        "total_markets_considered": int(len(all_df)),
        "eligible_n_wide": int(len(elig)),
        "eligible_n_narrow": int(len(elig_narrow)),
        "n_series_groups": len(SERIES_GROUPS),
    }
    (OUT_DIR / "probe_inventory_meta.json").write_text(
        json.dumps(meta, indent=2, default=str), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
