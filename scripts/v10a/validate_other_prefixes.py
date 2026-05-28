"""V10-A round 15b: Validate v1's strategy on OTHER prefixes v1 has been firing on.

Tests prefixes that v1 has actually filled / has resting orders on, but were
NOT included in the original validate_v1_strategy.py PERSIST set. Goal: identify
which to allow (PERSIST), deny (NULL/TRAIN_ONLY), or shadow-only (INSUFFICIENT).

Same regime as v1: buy YES as MAKER at yes_price >= 0.70 on Becker post-Oct-2024.
"""
from __future__ import annotations

import json
from pathlib import Path

import duckdb
import numpy as np

REPO = Path(__file__).resolve().parents[2]
MARKETS = REPO / "prediction-market-analysis" / "data" / "kalshi" / "markets" / "*.parquet"
TRADES = REPO / "prediction-market-analysis" / "data" / "kalshi" / "trades" / "*.parquet"

# OTHER prefixes v1 has fired / rested on (not in the original validate_v1_strategy.py)
OTHER_PREFIXES = [
    "KXNBAPLAYOFFWINS",
    "KXWCGAME",
    "KXUFCFIGHT",
    "KXIPLFINALS",
    "KXWCSTAGEOFELIM",
    "KXFOMEN",
    "KXBOXING",
    "KXNHLDRAFTPICK",
    "KXCS2",
    "KXWNBAWINS",
    "KXUFCOCCUR",
    "KXOWGRRANK",
    "KXPLAYWC",
    "KXNCAAFTOPAPRANK",
    "KXNEXTTEAMNBA",
    "KXNEXTTEAMNFL",
    "KXNEXTTEAMNHL",
    "KXSTARTINGQBWEEK1",
    "KXNFLPLAYOFF",  # W1 denylist (sanity)
    "KXNHLSERIESSPREAD",
    "KXWCSQUAD",
    "KXNBAPOLOSE",
    "KXUCLTOTAL",
    "KXNFLWINS",  # W1 denylist (sanity)
]


def get_v1_regime_trades(prefix: str, start: str, end: str):
    con = duckdb.connect()
    sql = f"""
    SELECT
        m.event_ticker AS event_ticker,
        t.yes_price / 100.0 AS yes_px,
        t.no_price / 100.0 AS no_px,
        t.taker_side, m.result, t.created_time,
        CASE WHEN m.result = 'yes' THEN 1.0 - t.yes_price/100.0 ELSE -t.yes_price/100.0 END AS gross_pl,
        0.25 * CEIL(0.07 * (t.yes_price/100.0) * (1.0 - t.yes_price/100.0) * 100.0) / 100.0 AS fee
    FROM '{TRADES.as_posix()}' t
    INNER JOIN '{MARKETS.as_posix()}' m ON t.ticker = m.ticker
    WHERE m.status='finalized' AND m.result IN ('yes', 'no')
      AND m.event_ticker LIKE '{prefix}%'
      AND t.created_time >= '{start}' AND t.created_time < '{end}'
      AND t.taker_side='no'
      AND t.yes_price >= 70
    """
    df = con.execute(sql).df()
    if len(df) == 0:
        return df
    df["net_pl"] = df["gross_pl"] - df["fee"]
    return df


def cluster_summary(df, n_boot=2000, seed=42):
    if len(df) == 0:
        return {"n_trades": 0, "n_events": 0}
    per_event = df.groupby("event_ticker")["net_pl"].mean().to_numpy()
    n_events = len(per_event)
    if n_events < 2:
        return {"n_trades": len(df), "n_events": n_events, "event_mean": float(per_event[0]) if n_events == 1 else None}
    rng = np.random.default_rng(seed)
    boots = [rng.choice(per_event, size=n_events, replace=True).mean() for _ in range(n_boot)]
    return {
        "n_trades": int(len(df)),
        "n_events": int(n_events),
        "trade_mean": float(df["net_pl"].mean()),
        "event_mean": float(per_event.mean()),
        "boot_ci_lo": float(np.percentile(boots, 2.5)),
        "boot_ci_hi": float(np.percentile(boots, 97.5)),
        "win_rate": float((df["net_pl"] > 0).mean()),
    }


def main():
    print(f"V1 STRATEGY VALIDATION on OTHER prefixes (post Oct 2024)")
    print(f"  Rule: BUY YES as MAKER at yes_price >= 0.70")
    print("=" * 150)
    print(f"{'prefix':22} {'TRAIN n_tr':>10} {'n_evt':>6} {'evt_mean':>9} {'ci_lo':>9} {'ci_hi':>9}  "
          f"{'OOS n_tr':>10} {'n_evt':>6} {'evt_mean':>9} {'ci_lo':>9} {'ci_hi':>9}  verdict")
    print("-" * 150)

    results = {}
    for prefix in OTHER_PREFIXES:
        train = get_v1_regime_trades(prefix, "2024-11-01", "2025-09-01")
        oos = get_v1_regime_trades(prefix, "2025-09-01", "2025-11-25")
        ts = cluster_summary(train)
        os_ = cluster_summary(oos)
        train_evt = ts.get("n_events", 0)
        oos_evt = os_.get("n_events", 0)
        if train_evt >= 10 and oos_evt >= 10:
            t_evt_mean = ts.get("event_mean", 0) or 0
            o_evt_mean = os_.get("event_mean", 0) or 0
            t_pass = ts.get("boot_ci_lo", -1) > 0 and t_evt_mean > 0
            o_pass = os_.get("boot_ci_lo", -1) > 0 and o_evt_mean > 0
            if t_pass and o_pass:
                v = "PERSIST"
            elif t_pass:
                v = "TRAIN_ONLY"
            elif o_pass:
                v = "OOS_ONLY"
            else:
                v = "NULL"
        else:
            v = "INSUFFICIENT"
        results[prefix] = {"train": ts, "oos": os_, "verdict": v}
        def fmt(s, key):
            x = s.get(key)
            return f"{x:>+9.4f}" if isinstance(x, (int, float)) else f"{'-':>9}"
        print(f"{prefix:22} {ts.get('n_trades', 0):>10} {ts.get('n_events', 0):>6} {fmt(ts, 'event_mean')} {fmt(ts, 'boot_ci_lo')} {fmt(ts, 'boot_ci_hi')}  "
              f"{os_.get('n_trades', 0):>10} {os_.get('n_events', 0):>6} {fmt(os_, 'event_mean')} {fmt(os_, 'boot_ci_lo')} {fmt(os_, 'boot_ci_hi')}  {v}")

    out = REPO / "research" / "v10a" / "13-other-prefix-test.json"
    with open(out, "w") as f:
        json.dump({"per_prefix": results}, f, indent=2, default=str)
    print(f"\nSaved to {out}")


if __name__ == "__main__":
    main()
