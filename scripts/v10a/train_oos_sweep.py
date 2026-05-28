"""V10-A round 15b: train/OOS sweep with cluster bootstrap on top candidates.

Train: 2024-11-01 to 2025-09-01 (10 months post-flip)
OOS:   2025-09-01 to 2025-11-25 (3 months OOS)

For each candidate prefix, computes train and OOS cluster-bootstrap CIs.
Edge is REAL if both train and OOS cluster-CIs exclude zero.

This is a real OOS test of edge persistence. Candidates passing this gate are
ready for Phase 3 critic.
"""
from __future__ import annotations

import json
from pathlib import Path

import duckdb
import numpy as np

REPO = Path(__file__).resolve().parents[2]
MARKETS = REPO / "prediction-market-analysis" / "data" / "kalshi" / "markets" / "*.parquet"
TRADES = REPO / "prediction-market-analysis" / "data" / "kalshi" / "trades" / "*.parquet"

CANDIDATES = [
    "KXNCAAMBGAME",
    "KXNCAAFGAME",
    "KXMLBTOTAL",
    "KXNFLGAME",
    "KXWTAMATCH",
    "KXNBAGAME",
    "KXATPMATCH",
    "KXETHD",
    "KXNBATOTAL",
    "KXNCAAFTOTAL",
    "KXBTC",
    "KXNCAAFSPREAD",
    "KXBTCD",
]

PX_LO, PX_HI = 0.30, 0.70
TRAIN_START, SPLIT_DATE, END_DATE = "2024-11-01", "2025-09-01", "2025-11-25"


def maker_fee_per_contract(px):
    return 0.25 * np.ceil(0.07 * px * (1.0 - px) * 100.0) / 100.0


def get_df(prefix, start, end):
    con = duckdb.connect()
    sql = f"""
    WITH resolved AS (
        SELECT
            ticker, event_ticker, result,
            regexp_extract(event_ticker, '^([A-Z0-9]+)', 1) AS prefix_raw
        FROM '{MARKETS.as_posix()}'
        WHERE status = 'finalized' AND result IN ('yes', 'no')
    )
    SELECT
        m.event_ticker AS event_ticker,
        CASE WHEN t.taker_side = 'yes' THEN t.no_price ELSE t.yes_price END / 100.0 AS maker_px,
        CASE WHEN t.taker_side != m.result THEN 1.0 ELSE 0.0 END
            - (CASE WHEN t.taker_side = 'yes' THEN t.no_price ELSE t.yes_price END / 100.0) AS maker_gross
    FROM '{TRADES.as_posix()}' t
    INNER JOIN resolved m ON t.ticker = m.ticker
    WHERE m.prefix_raw = '{prefix}'
      AND t.created_time >= '{start}'
      AND t.created_time < '{end}'
      AND (CASE WHEN t.taker_side = 'yes' THEN t.no_price ELSE t.yes_price END) / 100.0 BETWEEN {PX_LO} AND {PX_HI}
    """
    df = con.execute(sql).df()
    if len(df) == 0:
        return df
    df["fee"] = maker_fee_per_contract(df["maker_px"].values)
    df["net"] = df["maker_gross"] - df["fee"]
    return df


def cluster_stats(df, n_boot=2000, seed=42):
    if len(df) == 0:
        return {"n_trades": 0, "n_events": 0}
    per_event = df.groupby("event_ticker")["net"].mean().to_numpy()
    n_events = len(per_event)
    if n_events < 2:
        return {"n_trades": len(df), "n_events": n_events}
    rng = np.random.default_rng(seed)
    boots = [rng.choice(per_event, size=n_events, replace=True).mean() for _ in range(n_boot)]
    trade_mean = float(df["net"].mean())
    event_mean = float(per_event.mean())
    return {
        "n_trades": int(len(df)),
        "n_events": int(n_events),
        "trade_mean_net": trade_mean,
        "event_mean_net": event_mean,
        "event_boot_lo": float(np.percentile(boots, 2.5)),
        "event_boot_hi": float(np.percentile(boots, 97.5)),
        "event_sd": float(per_event.std(ddof=1)),
    }


def main():
    print(f"Train: [{TRAIN_START}, {SPLIT_DATE});  OOS: [{SPLIT_DATE}, {END_DATE})")
    print(f"Px band: [{PX_LO}, {PX_HI}] maker side")
    print("=" * 140)
    print(f"{'prefix':18} {'TRAIN n_tr':>10} {'n_evt':>6} {'evt_mean':>9} {'evt_lo':>9} {'evt_hi':>9}   "
          f"{'OOS n_tr':>10} {'n_evt':>6} {'evt_mean':>9} {'evt_lo':>9} {'evt_hi':>9}  verdict")
    print("-" * 140)
    results = []
    for prefix in CANDIDATES:
        train_df = get_df(prefix, TRAIN_START, SPLIT_DATE)
        oos_df = get_df(prefix, SPLIT_DATE, END_DATE)
        train_s = cluster_stats(train_df)
        oos_s = cluster_stats(oos_df)
        # Verdict logic
        if oos_s.get("n_events", 0) < 30:
            verdict = "OOS_INSUFFICIENT_N"
        elif train_s.get("n_events", 0) < 30:
            verdict = "TRAIN_INSUFFICIENT_N"
        else:
            train_pass = train_s.get("event_boot_lo", -1) > 0
            oos_pass = oos_s.get("event_boot_lo", -1) > 0
            if train_pass and oos_pass:
                verdict = "PERSISTENT_EDGE"
            elif train_pass and not oos_pass:
                verdict = "TRAIN_ONLY_NULL_OOS"
            elif oos_pass and not train_pass:
                verdict = "OOS_ONLY_RANDOM"
            else:
                verdict = "NEITHER_PASSES"
        results.append({"prefix": prefix, "train": train_s, "oos": oos_s, "verdict": verdict})
        train_str = (f"{train_s.get('n_trades', 0):>10} {train_s.get('n_events', 0):>6} "
                     f"{train_s.get('event_mean_net', 0):>+9.4f} "
                     f"{train_s.get('event_boot_lo', 0):>+9.4f} {train_s.get('event_boot_hi', 0):>+9.4f}")
        oos_str = (f"{oos_s.get('n_trades', 0):>10} {oos_s.get('n_events', 0):>6} "
                   f"{oos_s.get('event_mean_net', 0):>+9.4f} "
                   f"{oos_s.get('event_boot_lo', 0):>+9.4f} {oos_s.get('event_boot_hi', 0):>+9.4f}")
        print(f"{prefix:18} {train_str}   {oos_str}  {verdict}")

    out = REPO / "research" / "v10a" / "07-train-oos-sweep.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nResults JSON: {out}")
    n_persist = sum(1 for r in results if r["verdict"] == "PERSISTENT_EDGE")
    print(f"\n{n_persist} candidates show PERSISTENT EDGE (train AND OOS cluster-CIs exclude zero)")


if __name__ == "__main__":
    main()
