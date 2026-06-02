"""v19 Kalshi-internal overreaction / mean-reversion probe (Becker, read-only).

Tests whether a sharp short-window price move in a Kalshi sports market reverts
(a maker could fade the overshoot). Methodology + gate locked in
research/v19/00-methodology.md, with the methodology-critic revisions R1
(disjoint-sample Galton control), R2 (time-to-close), R3 (J-robustness) adopted
as binding.

Per market: bucket trades into T-min windows, compute per-bucket VWAP split into
DISJOINT odd/even trade halves. The binding fade is CROSS-SAMPLE: fire the signal
on half-A (jump_in_A = vwapA[b] - vwap[b-1]), take the entry from half-B
(entry = vwapB[b]), follow = vwap[b+1] - entry, fade = -sign(jump_in_A)*follow.
The NAIVE same-sample fade is reported alongside to expose Galton/bounce
artifacts (it should look "better" if the cross-sample edge is a phantom).

  PYTHONPATH=src .venv-kronos\\Scripts\\python.exe scripts\\v19\\overreaction_probe.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))
from kalshi_bot.analysis.bootstrap import cluster_bootstrap_mean_ci  # noqa: E402

MARKETS = (REPO / "prediction-market-analysis/data/kalshi/markets/*.parquet").as_posix()
TRADES = (REPO / "prediction-market-analysis/data/kalshi/trades/*.parquet").as_posix()
OUT = REPO / "research" / "v19" / "01-overreaction-results.json"

TRAIN = ("2024-11-01", "2025-09-01")
OOS = ("2025-09-01", "2025-11-25")
T_VALUES = [15, 30]          # bucket minutes
J_VALUES = [3, 5, 7, 10]     # jump thresholds, cents
K_TERMINAL = 2               # drop the last K buckets (settlement convergence)
MIN_BUCKET_TRADES = 4        # need >=2 per odd/even half for a stable VWAP
MID_TTC_MIN, MID_TTC_MAX = 60.0, 360.0  # "middle of market life" by minutes-to-close
PREFIXES = ["KXMLBGAME", "KXATPMATCH", "KXWTAMATCH"]


def rt_fee_cents(price_dollars: float) -> float:
    p = min(max(price_dollars, 0.0), 1.0)
    maker = 0.25 * np.ceil(0.07 * p * (1.0 - p) * 100.0) / 100.0
    return 2.0 * maker * 100.0


def load(prefix: str) -> pd.DataFrame:
    con = duckdb.connect()
    sql = f"""
    SELECT t.ticker AS ticker, t.yes_price AS yes_px, t.count AS vol,
           t.created_time AS ts, m.close_time AS close_time
    FROM '{TRADES}' t JOIN '{MARKETS}' m ON t.ticker=m.ticker
    WHERE m.status='finalized' AND m.result IN ('yes','no')
      AND m.event_ticker LIKE '{prefix}%'
      AND t.created_time >= DATE '{TRAIN[0]}' AND t.created_time < DATE '{OOS[1]}'
    """
    df = con.execute(sql).df()
    if len(df):
        df["ts"] = pd.to_datetime(df["ts"], utc=True)
        df["close_time"] = pd.to_datetime(df["close_time"], utc=True)
        df["vol"] = df["vol"].clip(lower=1.0)
    return df


def market_records(g: pd.DataFrame, t_min: int) -> list[dict]:
    g = g.sort_values("ts").reset_index(drop=True)
    g["tidx"] = np.arange(len(g))
    t0 = g["ts"].iloc[0]
    g["bucket"] = ((g["ts"] - t0).dt.total_seconds() // (t_min * 60)).astype(int)
    close = g["close_time"].iloc[0]
    stats: dict[int, dict] = {}
    for b, gb in g.groupby("bucket"):
        if len(gb) < MIN_BUCKET_TRADES:
            continue
        odd = gb[gb["tidx"] % 2 == 1]
        even = gb[gb["tidx"] % 2 == 0]
        if len(odd) == 0 or len(even) == 0:
            continue
        stats[int(b)] = {
            "vwap": float((gb["yes_px"] * gb["vol"]).sum() / gb["vol"].sum()),
            "vwapA": float((odd["yes_px"] * odd["vol"]).sum() / odd["vol"].sum()),
            "vwapB": float((even["yes_px"] * even["vol"]).sum() / even["vol"].sum()),
            "end": gb["ts"].max(),
        }
    if not stats:
        return []
    max_b = max(stats)
    out: list[dict] = []
    for b in sorted(stats):
        if b - 1 not in stats or b + 1 not in stats:
            continue
        if b > max_b - K_TERMINAL:  # drop terminal buckets
            continue
        s0, s1, s2 = stats[b - 1], stats[b], stats[b + 1]
        jump_a = s1["vwapA"] - s0["vwap"]
        jump_naive = s1["vwap"] - s0["vwap"]
        follow_cross = s2["vwap"] - s1["vwapB"]
        follow_naive = s2["vwap"] - s1["vwap"]
        fade_cross = -np.sign(jump_a) * follow_cross - rt_fee_cents(s1["vwapB"] / 100.0)
        fade_naive = -np.sign(jump_naive) * follow_naive - rt_fee_cents(s1["vwap"] / 100.0)
        ttc = (close - s1["end"]).total_seconds() / 60.0
        out.append({
            "game_day": s1["end"].date().isoformat(),
            "date": s1["end"],
            "ttc": ttc,
            "jump_a": abs(jump_a),
            "jump_naive": abs(jump_naive),
            "fade_cross": fade_cross,
            "fade_naive": fade_naive,
        })
    return out


def boot(values: list[float], clusters: list, seed: int = 0) -> dict:
    if len(values) < 2:
        return {"n": len(values), "mean": None, "lo": None, "hi": None, "nclusters": 0}
    mean, lo, hi, k = cluster_bootstrap_mean_ci(values, clusters, n_resamples=2000, rng_seed=seed)
    return {"n": len(values), "mean": mean, "lo": lo, "hi": hi, "nclusters": k}


def analyze(prefix: str) -> dict:
    df = load(prefix)
    print(f"\n===== {prefix} (trades={len(df)}) =====")
    if len(df) == 0:
        return {"prefix": prefix, "insufficient": True}
    res: dict = {"prefix": prefix, "by_T": {}}
    for t_min in T_VALUES:
        recs: list[dict] = []
        for _tk, g in df.groupby("ticker"):
            recs.extend(market_records(g, t_min))
        if not recs:
            continue
        r = pd.DataFrame(recs)
        r["win"] = r["date"].apply(lambda d, p=prefix: "oos" if d >= pd.Timestamp(OOS[0], tz="UTC") else "train")
        r["mid"] = (r["ttc"] >= MID_TTC_MIN) & (r["ttc"] <= MID_TTC_MAX)
        print(f"  T={t_min}min: {len(r)} interior buckets ; mid-window {int(r['mid'].sum())}")
        tj: dict = {}
        for j in J_VALUES:
            cell: dict = {}
            for window in ("train", "oos"):
                sub = r[(r["win"] == window) & r["mid"]]
                cross_fire = sub[sub["jump_a"] >= j]
                naive_fire = sub[sub["jump_naive"] >= j]
                cell[window] = {
                    "cross": boot(cross_fire["fade_cross"].tolist(), cross_fire["game_day"].tolist()),
                    "naive": boot(naive_fire["fade_naive"].tolist(), naive_fire["game_day"].tolist()),
                }
            tj[j] = cell
            co = cell["oos"]["cross"]
            na = cell["oos"]["naive"]
            cm = f"{co['mean']:+.2f}c [{co['lo']:+.2f},{co['hi']:+.2f}] n={co['n']}" if co["mean"] is not None else "n/a"
            nm = f"{na['mean']:+.2f}c" if na["mean"] is not None else "n/a"
            print(f"    J>={j}c mid OOS: CROSS {cm} | naive {nm}")
        res["by_T"][t_min] = tj
    return res


def gate(res: dict) -> tuple[bool, str]:
    """Binding gate: cross-sample OOS+train CI lower > 0 in the mid window,
    mean >= 1c, non-decreasing J5->J7, on BOTH T."""
    if res.get("insufficient"):
        return False, "insufficient data"
    for t_min in T_VALUES:
        tj = res.get("by_T", {}).get(t_min)
        if not tj:
            return False, f"no data at T={t_min}"
        j5 = tj.get(5, {})
        c_oos = j5.get("oos", {}).get("cross", {})
        c_tr = j5.get("train", {}).get("cross", {})
        if not c_oos.get("lo") or not c_tr.get("lo"):
            return False, f"T={t_min} J5 no CI"
        if not (c_oos["lo"] > 0 and c_tr["lo"] > 0):
            return False, f"T={t_min} J5 CI includes zero (OOS lo {c_oos['lo']}, train lo {c_tr['lo']})"
        if c_oos["mean"] < 1.0:
            return False, f"T={t_min} J5 OOS mean {c_oos['mean']:.2f}c < 1c floor"
        c7 = tj.get(7, {}).get("oos", {}).get("cross", {})
        if c7.get("mean") is None or c7["mean"] < c_oos["mean"] - 1e-9:
            return False, f"T={t_min} not non-decreasing J5->J7"
    return True, "all criteria pass on both T"


def main() -> int:
    results = {p: analyze(p) for p in PREFIXES}
    print("\n===== GATE (cross-sample, binding) =====")
    verdicts = {}
    for p, res in results.items():
        ok, why = gate(res)
        verdicts[p] = {"pass": ok, "why": why}
        print(f"  {p}: {'CONFIRM' if ok else 'NULL'} - {why}")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"results": results, "verdicts": verdicts}, indent=2, default=str),
                   encoding="utf-8")
    print(f"\nwrote {OUT}")
    if not any(v["pass"] for v in verdicts.values()):
        print("\nVERDICT: NULL. No prefix shows a cross-sample reversion edge that "
              "clears the gate. The apparent reversion (if any in the naive column) "
              "is Galton/bounce artifact, not a capturable overreaction.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
