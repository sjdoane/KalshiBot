"""V10-A round 15b: Validate v1's strategy on Becker historical data.

v1 strategy:
- Buy YES on Kalshi sports as MAKER
- Price >= 0.70 (confident favorites)
- Lifetime [30d, 180d]
- W1 denylist: KXNFLWINS, KXNFLPLAYOFF, KXMLBPLAYOFFS

Tests v1's strategy on the full Becker post-Oct-2024 sports universe with
cluster bootstrap by event_ticker. This is the cleanest possible
validation since v1 is already live with $32 and the user wants to scale.

Reports:
- Overall maker net excess return on v1's regime
- Per-sport breakdown
- LOCO by sport
- Train (Nov 2024 to Sep 2025) / OOS (Sep 2025 to Nov 2025) chronological split
"""
from __future__ import annotations

import json
from pathlib import Path

import duckdb
import numpy as np

REPO = Path(__file__).resolve().parents[2]
MARKETS = REPO / "prediction-market-analysis" / "data" / "kalshi" / "markets" / "*.parquet"
TRADES = REPO / "prediction-market-analysis" / "data" / "kalshi" / "trades" / "*.parquet"

# Sports prefixes that v1 trades (excluding W1 denylist)
SPORTS_PREFIXES = [
    "KXNFLGAME", "KXNFLSPREAD", "KXNFLTOTAL",
    "KXNBAGAME", "KXNBASPREAD", "KXNBATOTAL", "KXNBAWINS",
    "KXMLBGAME", "KXMLBSPREAD", "KXMLBTOTAL", "KXMLBWINS",
    "KXNHLGAME", "KXNHLSPREAD",
    "KXNCAAFGAME", "KXNCAAFSPREAD", "KXNCAAFTOTAL", "KXNCAAFPLAYOFF",
    "KXNCAAMBGAME", "KXNCAAMBTOTAL", "KXNCAAMBSPREAD",
    "KXWNBAGAME",
    "KXATPMATCH", "KXWTAMATCH",
    "KXUFCFIGHT", "KXBOXING",
    "KXPGATOUR",
    "KXEPLGAME", "KXUCLGAME",
]
# W1 denylist (per v4-H finding)
DENYLIST = ["KXNFLWINS", "KXNFLPLAYOFF", "KXMLBPLAYOFFS"]


def maker_fee(px):
    return 0.25 * np.ceil(0.07 * px * (1.0 - px) * 100.0) / 100.0


def get_v1_regime_trades(prefix: str, start: str, end: str):
    """Get all post-Oct-2024 trades where MAKER price is >= 0.70 (v1 regime is buying YES @ >= 0.70)."""
    con = duckdb.connect()
    # v1's MAKER side: places a bid to BUY YES at 0.70+
    # In Becker schema: if taker_side='no', maker is on YES side, maker_px = yes_price
    #                   if taker_side='yes', maker is on NO side, maker_px = no_price
    # v1 specifically targets MAKER at YES price >= 0.70
    # That means: only trades where taker_side='no' (maker on YES) AND yes_price >= 0.70
    sql = f"""
    SELECT
        m.event_ticker AS event_ticker,
        t.yes_price / 100.0 AS yes_px,
        t.no_price / 100.0 AS no_px,
        t.taker_side, m.result, t.created_time,
        -- v1's exact P&L: bought YES at yes_price, win if YES
        CASE WHEN m.result = 'yes' THEN 1.0 - t.yes_price/100.0 ELSE -t.yes_price/100.0 END AS gross_pl,
        0.25 * CEIL(0.07 * (t.yes_price/100.0) * (1.0 - t.yes_price/100.0) * 100.0) / 100.0 AS fee
    FROM '{TRADES.as_posix()}' t
    INNER JOIN '{MARKETS.as_posix()}' m ON t.ticker = m.ticker
    WHERE m.status='finalized' AND m.result IN ('yes', 'no')
      AND m.event_ticker LIKE '{prefix}%'
      AND t.created_time >= '{start}' AND t.created_time < '{end}'
      AND t.taker_side='no'  -- maker is on YES side
      AND t.yes_price >= 70  -- maker price >= 0.70
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
        return {"n_trades": len(df), "n_events": n_events, "event_mean": per_event[0] if n_events == 1 else None}
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
    print(f"V1 STRATEGY VALIDATION on Becker post Oct 2024")
    print(f"  Rule: BUY YES as MAKER at yes_price >= 0.70 on sports markets")
    print(f"  W1 denylist excluded: {DENYLIST}")
    print("=" * 130)
    print(f"{'prefix':22} {'TRAIN n_tr':>10} {'n_evt':>6} {'tr_mean':>9} {'evt_mean':>9} {'evt_lo':>9} "
          f"  {'OOS n_tr':>10} {'n_evt':>6} {'tr_mean':>9} {'evt_mean':>9} {'evt_lo':>9}  verdict")
    print("-" * 130)

    results = {}
    for prefix in SPORTS_PREFIXES:
        if prefix in DENYLIST:
            continue
        train = get_v1_regime_trades(prefix, "2024-11-01", "2025-09-01")
        oos = get_v1_regime_trades(prefix, "2025-09-01", "2025-11-25")
        ts = cluster_summary(train)
        os_ = cluster_summary(oos)
        if (ts.get("n_events", 0) >= 10 and os_.get("n_events", 0) >= 10):
            t_pass = ts.get("boot_ci_lo", -1) > 0
            o_pass = os_.get("boot_ci_lo", -1) > 0
            v = "PERSIST" if t_pass and o_pass else ("TRAIN_ONLY" if t_pass else ("OOS_ONLY" if o_pass else "NULL"))
        elif os_.get("n_events", 0) >= 10:
            v = "OOS_THIN_TRAIN" if os_.get("boot_ci_lo", -1) > 0 else "OOS_NULL"
        else:
            v = "INSUFFICIENT"
        results[prefix] = {"train": ts, "oos": os_, "verdict": v}
        if ts.get("n_events", 0) == 0 and os_.get("n_events", 0) == 0:
            continue
        def fmt(s, key):
            x = s.get(key)
            return f"{x:>+9.4f}" if isinstance(x, (int, float)) else f"{'-':>9}"
        print(f"{prefix:22} {ts.get('n_trades', 0):>10} {ts.get('n_events', 0):>6} {fmt(ts, 'trade_mean')} {fmt(ts, 'event_mean')} {fmt(ts, 'boot_ci_lo')}   "
              f"{os_.get('n_trades', 0):>10} {os_.get('n_events', 0):>6} {fmt(os_, 'trade_mean')} {fmt(os_, 'event_mean')} {fmt(os_, 'boot_ci_lo')}  {v}")

    # Combined v1 universe (all sports prefixes ex denylist)
    print()
    print("--- AGGREGATE v1 regime across all sports prefixes (ex W1 denylist) ---")
    all_train = []
    all_oos = []
    for prefix in SPORTS_PREFIXES:
        if prefix in DENYLIST:
            continue
        all_train.append(get_v1_regime_trades(prefix, "2024-11-01", "2025-09-01"))
        all_oos.append(get_v1_regime_trades(prefix, "2025-09-01", "2025-11-25"))
    import pandas as pd
    train_all = pd.concat([d for d in all_train if len(d) > 0], ignore_index=True) if any(len(d) for d in all_train) else pd.DataFrame()
    oos_all = pd.concat([d for d in all_oos if len(d) > 0], ignore_index=True) if any(len(d) for d in all_oos) else pd.DataFrame()
    ts = cluster_summary(train_all)
    os_ = cluster_summary(oos_all)
    print(f"TRAIN aggregate: n_tr={ts.get('n_trades')}, n_evt={ts.get('n_events')}, "
          f"trade_mean={ts.get('trade_mean', 0):+.4f}, evt_mean={ts.get('event_mean', 0):+.4f}, "
          f"CI=[{ts.get('boot_ci_lo', 0):+.4f}, {ts.get('boot_ci_hi', 0):+.4f}]")
    print(f"OOS aggregate:   n_tr={os_.get('n_trades')}, n_evt={os_.get('n_events')}, "
          f"trade_mean={os_.get('trade_mean', 0):+.4f}, evt_mean={os_.get('event_mean', 0):+.4f}, "
          f"CI=[{os_.get('boot_ci_lo', 0):+.4f}, {os_.get('boot_ci_hi', 0):+.4f}]")

    out = REPO / "research" / "v10a" / "12-v1-validation.json"
    with open(out, "w") as f:
        json.dump({"per_prefix": results, "aggregate_train": ts, "aggregate_oos": os_}, f, indent=2, default=str)
    print(f"\nSaved to {out}")


if __name__ == "__main__":
    main()
