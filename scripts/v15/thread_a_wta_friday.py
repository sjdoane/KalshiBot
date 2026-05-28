"""v15 Round 20 Thread A: rigorously test KXWTAMATCH Friday day-of-week lift.

Pre-registered gates (research/v15/01-methodology-lock.md):
  A-G1: n_Friday events >= 100
  A-G2: Friday event-mean > non-Friday event-mean
  A-G3: Cluster bootstrap CI on (Friday minus non-Friday) excludes zero
  A-G4: A-G3 holds in BOTH train (Nov 2024 to Aug 2025) and OOS
        (Sep 2025 to Nov 2025) windows independently
  A-G5: Stratifying by inferred match round does NOT eliminate the
        Friday effect (note: if round cannot be inferred from Becker,
        this gate is recorded as INCONCLUSIVE rather than PASS or FAIL)

Source data: Becker prediction-market-analysis Kalshi parquets,
joined to v1 regime trades (BUY YES as MAKER at yes_price >= 0.70,
which in Becker corresponds to taker_side='no' AND yes_price >= 70).

Output:
  research/v15/02-thread-a-results.json
  research/v15/02-thread-a-results.md
"""
from __future__ import annotations

import json
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
MARKETS = REPO / "prediction-market-analysis" / "data" / "kalshi" / "markets" / "*.parquet"
TRADES = REPO / "prediction-market-analysis" / "data" / "kalshi" / "trades" / "*.parquet"
OUT_JSON = REPO / "research" / "v15" / "02-thread-a-results.json"
OUT_MD = REPO / "research" / "v15" / "02-thread-a-results.md"


def pull_wta_v1_regime(start: str, end: str) -> pd.DataFrame:
    """Pull WTA v1-regime trades in the time window. Returns df with:
        event_ticker, ticker, yes_px, taker_side, created_time,
        result, gross_pl, fee, net_pl, dow_et (0=Sun)
    """
    con = duckdb.connect()
    sql = f"""
    SELECT
        m.event_ticker AS event_ticker,
        m.ticker AS ticker,
        m.result AS result,
        t.yes_price / 100.0 AS yes_px,
        t.taker_side AS taker_side,
        t.created_time AS created_time,
        EXTRACT(dow FROM t.created_time AT TIME ZONE 'America/New_York') AS dow_et,
        CASE WHEN m.result = 'yes' THEN 1.0 - t.yes_price/100.0
             ELSE -t.yes_price/100.0 END AS gross_pl,
        0.25 * CEIL(0.07 * (t.yes_price/100.0) * (1.0 - t.yes_price/100.0) * 100.0) / 100.0 AS fee
    FROM '{TRADES.as_posix()}' t
    INNER JOIN '{MARKETS.as_posix()}' m ON t.ticker = m.ticker
    WHERE m.status = 'finalized'
      AND m.result IN ('yes', 'no')
      AND m.event_ticker LIKE 'KXWTAMATCH%'
      AND t.created_time >= '{start}' AND t.created_time < '{end}'
      AND t.taker_side = 'no'
      AND t.yes_price >= 70
    """
    df = con.execute(sql).df()
    if len(df):
        df["net_pl"] = df["gross_pl"] - df["fee"]
        df["dow_et"] = df["dow_et"].astype(int)
        df["is_friday"] = (df["dow_et"] == 5)
    return df


def per_event_pnl_by_friday(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Returns (per_event_pnl_friday, per_event_pnl_nonfriday)."""
    if not len(df):
        return np.array([]), np.array([])
    # An event is either a Friday event (majority of its trades on Fri)
    # or a non-Friday event. Cluster level is the event, so each event
    # contributes ONE point: its event-mean net P&L. We assign event to
    # Friday/non-Friday by the day on which the MAJORITY of its trades fired.
    per_event = (
        df.groupby("event_ticker")
        .agg(event_mean=("net_pl", "mean"),
             friday_share=("is_friday", "mean"))
    )
    fri = per_event.loc[per_event["friday_share"] >= 0.5, "event_mean"].to_numpy()
    nfri = per_event.loc[per_event["friday_share"] < 0.5, "event_mean"].to_numpy()
    return fri, nfri


def cluster_bootstrap_diff(fri: np.ndarray, nfri: np.ndarray,
                            n_boot: int = 2000, seed: int = 42) -> dict:
    """Cluster-bootstrap CI on (mean_friday - mean_nonfriday).

    Each event is a cluster (one point). We resample each group with
    replacement n_boot times and compute the difference.
    """
    if len(fri) == 0 or len(nfri) == 0:
        return {"n_friday": int(len(fri)), "n_nonfriday": int(len(nfri))}
    rng = np.random.default_rng(seed)
    diffs = []
    for _ in range(n_boot):
        f = rng.choice(fri, size=len(fri), replace=True).mean()
        n = rng.choice(nfri, size=len(nfri), replace=True).mean()
        diffs.append(f - n)
    diffs = np.array(diffs)
    return {
        "n_friday": int(len(fri)),
        "n_nonfriday": int(len(nfri)),
        "mean_friday": float(fri.mean()),
        "mean_nonfriday": float(nfri.mean()),
        "diff_point": float(fri.mean() - nfri.mean()),
        "diff_ci_lo": float(np.percentile(diffs, 2.5)),
        "diff_ci_hi": float(np.percentile(diffs, 97.5)),
    }


def evaluate_window(label: str, start: str, end: str) -> dict:
    df = pull_wta_v1_regime(start, end)
    fri, nfri = per_event_pnl_by_friday(df)
    stats = cluster_bootstrap_diff(fri, nfri)
    stats["label"] = label
    stats["window"] = f"{start} to {end}"
    return stats


def main():
    # Full Becker post-Oct-2024 window
    full = evaluate_window("full_post_oct_2024", "2024-11-01", "2025-11-25")
    train = evaluate_window("train_nov2024_aug2025", "2024-11-01", "2025-09-01")
    oos = evaluate_window("oos_sep2025_nov2025", "2025-09-01", "2025-11-25")

    print("=== Thread A: WTA Friday vs non-Friday ===")
    for s in [full, train, oos]:
        print(f"\n{s['label']}: window {s['window']}")
        print(f"  n_friday={s.get('n_friday', 0)}, n_nonfriday={s.get('n_nonfriday', 0)}")
        if "diff_point" in s:
            print(
                f"  Friday mean = {s['mean_friday']:+.4f}, "
                f"non-Friday mean = {s['mean_nonfriday']:+.4f}"
            )
            print(
                f"  Diff = {s['diff_point']:+.4f}, "
                f"CI = [{s['diff_ci_lo']:+.4f}, {s['diff_ci_hi']:+.4f}]"
            )

    # Evaluate the gates
    g1_full_n = full.get("n_friday", 0)
    g2_full = full.get("diff_point", 0) > 0
    g3_full = full.get("diff_ci_lo", -1) > 0
    g3_train = train.get("diff_ci_lo", -1) > 0
    g3_oos = oos.get("diff_ci_lo", -1) > 0

    gates = {
        "A-G1 (n_Friday >= 100, full window)": (g1_full_n >= 100,
                                                  f"n_Friday = {g1_full_n}"),
        "A-G2 (Friday > non-Friday point estimate)": (
            g2_full, f"diff = {full.get('diff_point', 0):+.4f}",
        ),
        "A-G3 (CI excludes zero, full window)": (
            g3_full,
            f"CI = [{full.get('diff_ci_lo', 0):+.4f}, "
            f"{full.get('diff_ci_hi', 0):+.4f}]",
        ),
        "A-G4-train (CI excludes zero, train window)": (
            g3_train,
            f"CI = [{train.get('diff_ci_lo', 0):+.4f}, "
            f"{train.get('diff_ci_hi', 0):+.4f}]",
        ),
        "A-G4-oos (CI excludes zero, OOS window)": (
            g3_oos,
            f"CI = [{oos.get('diff_ci_lo', 0):+.4f}, "
            f"{oos.get('diff_ci_hi', 0):+.4f}]",
        ),
        "A-G5 (round confound stratification)": (
            None, "INCONCLUSIVE: Becker schema lacks tournament round metadata",
        ),
    }

    print("\n=== Gate verdict ===")
    pass_count = 0
    fail_count = 0
    inconclusive_count = 0
    for name, (passed, detail) in gates.items():
        if passed is True:
            marker = "PASS"
            pass_count += 1
        elif passed is False:
            marker = "FAIL"
            fail_count += 1
        else:
            marker = "INCONCLUSIVE"
            inconclusive_count += 1
        print(f"  [{marker}] {name}: {detail}")

    # Verdict tree
    if pass_count >= 5:
        verdict = "SHIP-CANDIDATE"
    elif pass_count >= 4:
        verdict = "SHADOW-CANDIDATE"
    elif pass_count >= 3:
        verdict = "MARGINAL"
    else:
        verdict = "NULL"
    print(f"\nVerdict: {verdict} ({pass_count} pass, {fail_count} fail, "
          f"{inconclusive_count} inconclusive)")

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "full": full, "train": train, "oos": oos,
        "gates": {
            k: {"pass": v[0], "detail": v[1]} for k, v in gates.items()
        },
        "verdict": verdict,
        "n_pass": pass_count, "n_fail": fail_count,
        "n_inconclusive": inconclusive_count,
    }
    with open(OUT_JSON, "w") as f:
        json.dump(payload, f, indent=2, default=str)
    print(f"\nSaved {OUT_JSON}")


if __name__ == "__main__":
    main()
