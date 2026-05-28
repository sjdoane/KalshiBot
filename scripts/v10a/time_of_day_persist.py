"""Round 15c Track 2D: Time-of-day stratification on PERSIST prefixes.

For each of v1's 5 Becker-validated PERSIST prefixes (KXMLBGAME,
KXATPMATCH, KXNFLGAME, KXNCAAFGAME, KXWTAMATCH), stratify
post-Oct-2024 maker-at-yes_price-greater-than-or-equal-70 trades by
hour-of-day (US Eastern Time) and report per-cell event-level mean
maker net P&L with cluster bootstrap CI.

Hypothesis: retail volume concentrates in evening US hours (7 to 11pm
ET); higher retail mispricing -> higher maker edge. If a specific
window shows materially higher edge than overall, v1 could be
restricted to that window.

Output: research/v10a/16-time-of-day-analysis.{md,json}
"""
from __future__ import annotations

import json
from pathlib import Path

import duckdb
import numpy as np

REPO = Path(__file__).resolve().parents[2]
MARKETS = REPO / "prediction-market-analysis" / "data" / "kalshi" / "markets" / "*.parquet"
TRADES = REPO / "prediction-market-analysis" / "data" / "kalshi" / "trades" / "*.parquet"
OUT_JSON = REPO / "research" / "v10a" / "16-time-of-day-analysis.json"
OUT_MD = REPO / "research" / "v10a" / "16-time-of-day-analysis.md"

PERSIST_PREFIXES = [
    "KXMLBGAME", "KXATPMATCH", "KXNFLGAME", "KXNCAAFGAME", "KXWTAMATCH",
]


def get_v1_regime_trades_with_hour(prefix: str) -> "duckdb.DuckDBPyRelation":
    """Pull v1-regime trades with US Eastern hour-of-day and day-of-week.

    Returns a DataFrame with: event_ticker, hour_et (0-23), dow_et (0-6),
    yes_px, net_pl.
    """
    con = duckdb.connect()
    sql = f"""
    SELECT
        m.event_ticker AS event_ticker,
        EXTRACT(hour FROM t.created_time AT TIME ZONE 'America/New_York') AS hour_et,
        EXTRACT(dow FROM t.created_time AT TIME ZONE 'America/New_York') AS dow_et,
        t.yes_price / 100.0 AS yes_px,
        CASE WHEN m.result = 'yes' THEN 1.0 - t.yes_price/100.0
             ELSE -t.yes_price/100.0 END AS gross_pl,
        0.25 * CEIL(0.07 * (t.yes_price/100.0) * (1.0 - t.yes_price/100.0) * 100.0) / 100.0 AS fee
    FROM '{TRADES.as_posix()}' t
    INNER JOIN '{MARKETS.as_posix()}' m ON t.ticker = m.ticker
    WHERE m.status='finalized' AND m.result IN ('yes','no')
      AND m.event_ticker LIKE '{prefix}%'
      AND t.created_time >= '2024-11-01' AND t.created_time < '2025-11-25'
      AND t.taker_side='no'
      AND t.yes_price >= 70
    """
    df = con.execute(sql).df()
    if len(df) == 0:
        return df
    df["net_pl"] = df["gross_pl"] - df["fee"]
    df["hour_et"] = df["hour_et"].astype(int)
    df["dow_et"] = df["dow_et"].astype(int)
    return df


def cluster_bootstrap(per_event: np.ndarray, n_boot: int = 1000,
                      seed: int = 42) -> dict:
    """Cluster bootstrap by event_ticker. per_event must already be the
    per-event means. Returns mean and 95% CI."""
    if len(per_event) == 0:
        return {"n": 0}
    if len(per_event) < 2:
        return {"n": 1, "event_mean": float(per_event[0])}
    rng = np.random.default_rng(seed)
    boots = [rng.choice(per_event, size=len(per_event), replace=True).mean()
             for _ in range(n_boot)]
    return {
        "n": int(len(per_event)),
        "event_mean": float(per_event.mean()),
        "ci_lo": float(np.percentile(boots, 2.5)),
        "ci_hi": float(np.percentile(boots, 97.5)),
    }


def analyze_hour_bands(df) -> list[dict]:
    """For each contiguous 3-hour band (0-2, 3-5, ..., 21-23), compute
    event-level cluster-bootstrap stats. Plus a few common windows."""
    bands = [
        ("00-02_ET", (0, 2)), ("03-05_ET", (3, 5)),
        ("06-08_ET", (6, 8)), ("09-11_ET", (9, 11)),
        ("12-14_ET", (12, 14)), ("15-17_ET", (15, 17)),
        ("18-20_ET", (18, 20)), ("21-23_ET", (21, 23)),
        ("evening_19-23_ET", (19, 23)),
        ("daytime_09-18_ET", (9, 18)),
        ("late_night_00-05_ET", (0, 5)),
    ]
    out = []
    for label, (lo, hi) in bands:
        sub = df[(df["hour_et"] >= lo) & (df["hour_et"] <= hi)]
        if len(sub) == 0:
            out.append({"band": label, "lo": lo, "hi": hi,
                       "n_trades": 0, "n_events": 0})
            continue
        per_event = sub.groupby("event_ticker")["net_pl"].mean().to_numpy()
        stats = cluster_bootstrap(per_event)
        out.append({
            "band": label, "lo": lo, "hi": hi,
            "n_trades": int(len(sub)),
            **stats,
        })
    return out


def analyze_dow(df) -> list[dict]:
    """Per day-of-week cluster bootstrap. dow 0=Sun ... 6=Sat (Postgres)."""
    names = {0: "Sun", 1: "Mon", 2: "Tue", 3: "Wed", 4: "Thu",
             5: "Fri", 6: "Sat"}
    out = []
    for d in range(7):
        sub = df[df["dow_et"] == d]
        if len(sub) == 0:
            out.append({"dow": d, "name": names[d], "n_trades": 0, "n_events": 0})
            continue
        per_event = sub.groupby("event_ticker")["net_pl"].mean().to_numpy()
        stats = cluster_bootstrap(per_event)
        out.append({"dow": d, "name": names[d], "n_trades": int(len(sub)), **stats})
    return out


def main():
    results: dict = {}
    for prefix in PERSIST_PREFIXES:
        print(f"=== {prefix} ===")
        df = get_v1_regime_trades_with_hour(prefix)
        if len(df) == 0:
            print("  (no trades)")
            continue
        per_event_overall = df.groupby("event_ticker")["net_pl"].mean().to_numpy()
        overall = cluster_bootstrap(per_event_overall)
        bands = analyze_hour_bands(df)
        dows = analyze_dow(df)
        results[prefix] = {
            "overall": overall,
            "by_hour_band": bands,
            "by_dow": dows,
        }
        print(
            f"  overall: n_evt={overall.get('n')}, "
            f"evt_mean={overall.get('event_mean', 0):+.4f}, "
            f"CI=[{overall.get('ci_lo', 0):+.4f}, {overall.get('ci_hi', 0):+.4f}]"
        )
        print(f"  {'band':22}  {'n_tr':>6} {'n_evt':>6} {'evt_mean':>9} {'ci_lo':>9} {'ci_hi':>9}")
        for b in bands:
            n = b.get('n', 0)
            if n == 0:
                print(f"  {b['band']:22}  {b.get('n_trades', 0):>6} {n:>6}  (no data)")
                continue
            print(
                f"  {b['band']:22}  {b.get('n_trades', 0):>6} {n:>6} "
                f"{b.get('event_mean', 0):>+9.4f} "
                f"{b.get('ci_lo', 0):>+9.4f} "
                f"{b.get('ci_hi', 0):>+9.4f}"
            )

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nSaved JSON to {OUT_JSON}")

    # Also write a brief markdown summary of band findings
    lines = ["# Round 15c Track 2D: Time-of-day analysis on PERSIST prefixes",
             "",
             "Method: for each of the 5 Becker-validated PERSIST prefixes,",
             "stratify post-Oct-2024 maker trades (at yes_price >= 0.70) by",
             "hour-of-day (US Eastern) and day-of-week. Per-cell event-level",
             "cluster bootstrap CI (n=1000 resamples). Goal: identify time",
             "windows with materially higher edge than the prefix overall.",
             "",
             "## Per-prefix hour-band results",
             ""]
    for prefix in PERSIST_PREFIXES:
        if prefix not in results:
            continue
        r = results[prefix]
        ov = r["overall"]
        lines.append(f"### {prefix}")
        lines.append("")
        lines.append(f"Overall: n_events={ov.get('n')}, event_mean="
                    f"{ov.get('event_mean', 0):+.4f}, "
                    f"CI=[{ov.get('ci_lo', 0):+.4f}, {ov.get('ci_hi', 0):+.4f}]")
        lines.append("")
        lines.append("| Band (ET) | n_trades | n_events | event_mean | CI lower | CI upper |")
        lines.append("|---|---|---|---|---|---|")
        for b in r["by_hour_band"]:
            n = b.get('n', 0)
            if n == 0:
                lines.append(f"| {b['band']} | {b.get('n_trades', 0)} | 0 | -- | -- | -- |")
                continue
            lines.append(
                f"| {b['band']} | {b.get('n_trades', 0)} | {n} | "
                f"{b.get('event_mean', 0):+.4f} | "
                f"{b.get('ci_lo', 0):+.4f} | {b.get('ci_hi', 0):+.4f} |"
            )
        lines.append("")
        lines.append("Day-of-week (ET):")
        lines.append("")
        lines.append("| DOW | n_trades | n_events | event_mean | CI lower | CI upper |")
        lines.append("|---|---|---|---|---|---|")
        for d in r["by_dow"]:
            n = d.get('n', 0)
            if n == 0:
                lines.append(f"| {d['name']} | {d.get('n_trades', 0)} | 0 | -- | -- | -- |")
                continue
            lines.append(
                f"| {d['name']} | {d.get('n_trades', 0)} | {n} | "
                f"{d.get('event_mean', 0):+.4f} | "
                f"{d.get('ci_lo', 0):+.4f} | {d.get('ci_hi', 0):+.4f} |"
            )
        lines.append("")
    with open(OUT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Saved MD to {OUT_MD}")


if __name__ == "__main__":
    main()
