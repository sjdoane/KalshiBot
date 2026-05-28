"""V10-A round 15b Phase 2: EPL maker backtest with cluster-bootstrap.

Proper version of the KXEPLGAME maker backtest:

- Train: 2025-05-01 to 2025-10-01 (5 months)
- OOS: 2025-10-01 to 2025-11-25 (2 months)
- Effective sample = GAMES not trades (cluster-bootstrap by event_ticker)
- Gates apply to game-level CI not trade-level

The trade-level analysis is the "headline" P&L number, but the
statistical-test sample size is the game count to avoid the
multi-strike-per-event independence violation flagged by the v10a
methodology critic (IMPORTANT-1).
"""
from __future__ import annotations

import json
import math
import time
from pathlib import Path

import duckdb
import numpy as np

REPO = Path(__file__).resolve().parents[2]
MARKETS = REPO / "prediction-market-analysis" / "data" / "kalshi" / "markets" / "*.parquet"
TRADES = REPO / "prediction-market-analysis" / "data" / "kalshi" / "trades" / "*.parquet"


def maker_fee_per_contract(px: float) -> float:
    return 0.25 * math.ceil(0.07 * px * (1.0 - px) * 100.0) / 100.0


def get_trades(prefix: str, px_lo: float, px_hi: float, start_date: str, end_date: str):
    con = duckdb.connect()
    sql = f"""
    WITH resolved AS (
        SELECT
            ticker, event_ticker, result, close_time,
            regexp_extract(event_ticker, '^([A-Z0-9]+)', 1) AS prefix_raw
        FROM '{MARKETS.as_posix()}'
        WHERE status = 'finalized' AND result IN ('yes', 'no')
    )
    SELECT
        t.ticker, t.yes_price, t.no_price, t.count, t.taker_side, t.created_time,
        m.event_ticker, m.result, m.close_time,
        CASE WHEN t.taker_side = 'yes' THEN t.no_price ELSE t.yes_price END / 100.0 AS maker_px,
        CASE WHEN t.taker_side != m.result THEN 1.0 ELSE 0.0 END AS maker_won,
        CASE WHEN t.taker_side != m.result THEN 1.0 ELSE 0.0 END
            - (CASE WHEN t.taker_side = 'yes' THEN t.no_price ELSE t.yes_price END / 100.0) AS maker_gross
    FROM '{TRADES.as_posix()}' t
    INNER JOIN resolved m ON t.ticker = m.ticker
    WHERE m.prefix_raw = '{prefix}'
      AND t.created_time >= '{start_date}'
      AND t.created_time < '{end_date}'
      AND (CASE WHEN t.taker_side = 'yes' THEN t.no_price ELSE t.yes_price END) / 100.0 BETWEEN {px_lo} AND {px_hi}
    """
    df = con.execute(sql).df()
    df["fee"] = df["maker_px"].apply(maker_fee_per_contract)
    df["net"] = df["maker_gross"] - df["fee"]
    return df


def trade_level_summary(df) -> dict:
    if len(df) == 0:
        return {"n_trades": 0}
    n = len(df)
    rng = np.random.default_rng(42)
    arr = df["net"].to_numpy()
    boot = [rng.choice(arr, size=n, replace=True).mean() for _ in range(2000)]
    return {
        "n_trades": n,
        "mean_net": float(arr.mean()),
        "sd_net": float(arr.std(ddof=1)),
        "boot_ci_lo": float(np.percentile(boot, 2.5)),
        "boot_ci_hi": float(np.percentile(boot, 97.5)),
        "mean_px": float(df["maker_px"].mean()),
        "win_rate": float(df["maker_won"].mean()),
    }


def cluster_level_summary(df) -> dict:
    """Cluster-bootstrap by event_ticker. Effective sample = n_events."""
    if len(df) == 0:
        return {"n_events": 0}
    # Per-event mean net P&L
    per_event = df.groupby("event_ticker").agg(
        mean_net=("net", "mean"),
        n_trades=("net", "size"),
        mean_px=("maker_px", "mean"),
        win_rate=("maker_won", "mean"),
    ).reset_index()
    n_events = len(per_event)
    rng = np.random.default_rng(42)
    arr = per_event["mean_net"].to_numpy()
    n_boot = 2000
    boot = []
    for _ in range(n_boot):
        sample_events = rng.choice(arr, size=n_events, replace=True)
        boot.append(sample_events.mean())
    return {
        "n_events": int(n_events),
        "event_mean_net": float(arr.mean()),
        "event_sd_net": float(arr.std(ddof=1)) if n_events > 1 else float("nan"),
        "boot_ci_lo": float(np.percentile(boot, 2.5)),
        "boot_ci_hi": float(np.percentile(boot, 97.5)),
        "median_n_trades_per_event": int(per_event["n_trades"].median()),
        "mean_px_per_event": float(per_event["mean_px"].mean()),
        "win_rate_per_event": float(per_event["win_rate"].mean()),
    }


def main() -> None:
    prefix = "KXEPLGAME"
    px_lo, px_hi = 0.30, 0.70
    splits = [
        ("2025-05-01", "2025-10-01", "2025-11-25"),  # main split
        ("2025-05-01", "2025-09-01", "2025-11-25"),  # earlier split
    ]
    results = {}
    for start, split, end in splits:
        print(f"\n{'=' * 60}")
        print(f"Train: [{start}, {split}); OOS: [{split}, {end})")
        print('=' * 60)
        train_df = get_trades(prefix, px_lo, px_hi, start, split)
        oos_df = get_trades(prefix, px_lo, px_hi, split, end)

        train_tr = trade_level_summary(train_df)
        train_cl = cluster_level_summary(train_df)
        oos_tr = trade_level_summary(oos_df)
        oos_cl = cluster_level_summary(oos_df)

        print(f"\nTrain trade-level: n={train_tr.get('n_trades')}, "
              f"mean={train_tr.get('mean_net'):+.5f}, CI=[{train_tr.get('boot_ci_lo'):+.5f}, {train_tr.get('boot_ci_hi'):+.5f}]")
        print(f"Train cluster-level: n_events={train_cl.get('n_events')}, "
              f"event_mean={train_cl.get('event_mean_net'):+.5f}, CI=[{train_cl.get('boot_ci_lo'):+.5f}, {train_cl.get('boot_ci_hi'):+.5f}]")
        print(f"OOS trade-level: n={oos_tr.get('n_trades')}, "
              f"mean={oos_tr.get('mean_net'):+.5f}, CI=[{oos_tr.get('boot_ci_lo'):+.5f}, {oos_tr.get('boot_ci_hi'):+.5f}]")
        print(f"OOS cluster-level: n_events={oos_cl.get('n_events')}, "
              f"event_mean={oos_cl.get('event_mean_net'):+.5f}, CI=[{oos_cl.get('boot_ci_lo'):+.5f}, {oos_cl.get('boot_ci_hi'):+.5f}]")

        # Gate decision: cluster-level CI lower > 0 is the binding gate
        gate_cluster = oos_cl.get("boot_ci_lo", -1) > 0
        gate_n_events = oos_cl.get("n_events", 0) >= 30
        print(f"\nGate cluster-CI (OOS event-level boot CI lower > 0): {'PASS' if gate_cluster else 'FAIL'}")
        print(f"Gate n_events (OOS event count >= 30): {'PASS' if gate_n_events else 'FAIL'}")
        verdict = "PASS" if (gate_cluster and gate_n_events) else "NULL_or_PARTIAL"
        print(f"Verdict: {verdict}")
        results[split] = {
            "train_trade": train_tr, "train_cluster": train_cl,
            "oos_trade": oos_tr, "oos_cluster": oos_cl,
            "verdict": verdict,
        }

    out_path = REPO / "data" / "v10a" / "backtest_epl_clustered.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nFull JSON saved to {out_path}")


if __name__ == "__main__":
    main()
