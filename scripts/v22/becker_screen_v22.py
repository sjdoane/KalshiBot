"""v22 slate screen: P1 cold-start contrast, P2a toxicity, P3 affirmation tax.

Implements research/v22/00-methodology-lock.md v2 EXACTLY. The lock, the
category map (research/v22/category_map.json), and the fee table
(research/v22/fee_table.json) were all committed before this script ran.
Code review required BEFORE this script's output is read.

Fee table format (research/v22/fee_table.json):
  {"rows": [{"prefixes": ["KXINX", ...] or "ALL_OTHER",
             "start": "YYYY-MM-DD", "end": "YYYY-MM-DD",
             "maker_fee": "ceil_175" | "zero" | "ambiguous"}, ...]}
Per the lock H-4: trades matching an "ambiguous" row are run BOTH ways
(fee = 0 and fee = ceil(1.75*P*(1-P)) cents); K-P1 may PASS only if it
passes under both.

Run (Windows):
  & "C:\\Users\\SamJD\\OneDrive\\Desktop\\AI Projects\\Project Kalshi\\.venv-kronos\\Scripts\\python.exe" "C:\\Users\\SamJD\\OneDrive\\Desktop\\AI Projects\\Project Kalshi\\scripts\\v22\\becker_screen_v22.py"
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

BASE = Path(r"C:/Users/SamJD/OneDrive/Desktop/AI Projects/Project Kalshi")
BECKER = BASE / "prediction-market-analysis"
TRADES = (BECKER / "data" / "kalshi" / "trades").as_posix() + "/*.parquet"
MARKETS = (BECKER / "data" / "kalshi" / "markets").as_posix() + "/*.parquet"
MAP_PATH = BASE / "research" / "v22" / "category_map.json"
FEE_PATH = BASE / "research" / "v22" / "fee_table.json"
OUT_PATH = BASE / "research" / "v22" / "04-screen-results.json"

RNG_SEED = 42
N_RESAMPLES = 5000

# Locked cell edges (lock v2, critic C-1). TTE bands in days; price bands on
# the print's yes_price in dollars.
TTE_BANDS = [(3, 10), (10, 21), (21, 42), (42, 90), (90, 100000)]
PRICE_BANDS = [(0.03, 0.20), (0.20, 0.40), (0.40, 0.60), (0.60, 0.80), (0.80, 0.9701)]
MIN_AGED_TRADES = 50
MIN_AGED_EVENTS = 10
K_P1_MIN_EVENTS = 300

POP_FILTERS = """
      status = 'finalized' AND result IN ('yes','no')
      AND open_time >= TIMESTAMP '2024-11-01'
      AND close_time < TIMESTAMP '2025-11-01'
      AND close_time < TIMESTAMP '2028-01-01'
"""


def load_map() -> dict:
    with open(MAP_PATH, encoding="utf-8") as f:
        return json.load(f)["map"]


def load_fee_rows() -> list[dict]:
    """Load + validate (review M-6: a typo'd status must fail loudly, not
    silently degrade to the ambiguous dual-run)."""
    with open(FEE_PATH, encoding="utf-8") as f:
        rows = json.load(f)["rows"]
    for r in rows:
        if r["maker_fee"] not in {"ceil_175", "zero", "ambiguous"}:
            raise ValueError(f"fee_table: bad maker_fee {r['maker_fee']!r}")
        if r["prefixes"] != "ALL_OTHER" and not (
            isinstance(r["prefixes"], list) and all(isinstance(p, str) for p in r["prefixes"])
        ):
            raise ValueError(f"fee_table: bad prefixes {r['prefixes']!r}")
        if not pd.Timestamp(r["start"]) < pd.Timestamp(r["end"]):
            raise ValueError(f"fee_table: start >= end in {r}")
    return rows


def fee_status_for(prefix: str, ts: pd.Timestamp, fee_rows: list[dict]) -> str:
    """'ceil_175' | 'zero' | 'ambiguous' for one (prefix, trade time)."""
    fallback = None
    for row in fee_rows:
        start = pd.Timestamp(row["start"], tz="UTC")
        end = pd.Timestamp(row["end"], tz="UTC")
        if not (start <= ts < end):
            continue
        if row["prefixes"] == "ALL_OTHER":
            fallback = row["maker_fee"]
        elif prefix in row["prefixes"]:
            return row["maker_fee"]
    return fallback if fallback is not None else "ambiguous"


def ceil_fee(p: np.ndarray) -> np.ndarray:
    """Era maker fee, dollars: ceil(1.75 * P * (1-P)) cents per contract."""
    return np.ceil(1.75 * p * (1.0 - p)) / 100.0


def band_index(values: np.ndarray, bands: list[tuple]) -> np.ndarray:
    """Index of the band containing each value; -1 if none."""
    out = np.full(len(values), -1, dtype=int)
    for i, (lo, hi) in enumerate(bands):
        out[np.where((values >= lo) & (values < hi))] = i
    return out


def pull_p1(con) -> pd.DataFrame:
    """All qualifying P1 prints (cold + aged) with per-trade fields."""
    q = f"""
        WITH mk AS (
            SELECT ticker, event_ticker, result, open_time, close_time
            FROM '{MARKETS}'
            WHERE {POP_FILTERS}
              AND (close_time - open_time) >= INTERVAL 10 DAYS
        )
        SELECT
            t.trade_id,
            t.ticker,
            m.event_ticker,
            m.open_time AS m_open,
            regexp_extract(m.event_ticker, '^([A-Z0-9]+)', 1) AS prefix,
            t.yes_price / 100.0 AS yes_price,
            (CASE WHEN t.taker_side='yes' THEN t.no_price ELSE t.yes_price END)/100.0 AS maker_price,
            (CASE WHEN t.taker_side != m.result THEN 1.0 ELSE 0.0 END) AS maker_won,
            t.count AS contracts,
            t.created_time,
            epoch(t.created_time - m.open_time) / 3600.0 AS age_h,
            epoch(m.close_time - t.created_time) / 86400.0 AS tte_d
        FROM '{TRADES}' t
        INNER JOIN mk m ON t.ticker = m.ticker
        WHERE t.created_time < m.close_time
          AND t.yes_price >= 3 AND t.yes_price <= 97
          AND t.yes_price + t.no_price = 100
          AND t.count > 0
          AND t.taker_side IN ('yes','no')
          AND m.event_ticker NOT LIKE 'KXMVE%'
          AND (
                epoch(t.created_time - m.open_time) < 6*3600
             OR (epoch(t.created_time - m.open_time) > 3*86400
                 AND epoch(m.close_time - t.created_time) > 3*86400)
          )
        ORDER BY t.trade_id
    """
    return con.execute(q).df()


def attach_cells(df: pd.DataFrame, cat_map: dict, fee_rows: list[dict]) -> pd.DataFrame:
    """Group, graveyard, cell index, era fee status, per-trade gross excess."""
    meta = df["prefix"].map(lambda p: cat_map.get(p, {"group": "unknown", "graveyard": False}))
    df["group"] = [m["group"] for m in meta]
    df["graveyard"] = [bool(m["graveyard"]) for m in meta]
    df["tte_band"] = band_index(df["tte_d"].to_numpy(), TTE_BANDS)
    df["price_band"] = band_index(df["yes_price"].to_numpy(), PRICE_BANDS)
    df["is_cold"] = df["age_h"] < 6.0
    df["gross"] = df["maker_won"] - df["maker_price"]
    df["fee_era"] = ceil_fee(df["maker_price"].to_numpy())
    # Fee status at DAY granularity (review C-1/H-3: fee-document dates can
    # fall mid-month; day-level cache is exact at document-date resolution).
    days = df["created_time"].dt.floor("D")
    cache: dict = {}
    statuses = []
    for prefix, day in zip(df["prefix"], days):
        k = (prefix, day)
        if k not in cache:
            cache[k] = fee_status_for(prefix, day, fee_rows)
        statuses.append(cache[k])
    df["fee_status"] = statuses
    return df


def p1_estimate(df: pd.DataFrame, fee_mode: str) -> dict:
    """Point estimate + joint two-sample event-cluster bootstrap for one fee
    mode. fee_mode in {'table_low','table_high'}: ambiguous trades get fee=0
    in 'table_low' and ceil fee in 'table_high'; 'zero' rows always 0;
    'ceil_175' rows always ceil. K-P1 must pass under BOTH modes.
    """
    d = df[~df["graveyard"] & (df["group"] != "unknown")
           & (df["tte_band"] >= 0) & (df["price_band"] >= 0)].copy()
    amb_fee = 0.0 if fee_mode == "table_low" else 1.0
    fee = np.where(
        d["fee_status"] == "ceil_175", d["fee_era"],
        np.where(d["fee_status"] == "zero", 0.0, d["fee_era"] * amb_fee),
    )
    d["e"] = d["gross"] - fee
    d["cell"] = list(zip(d["group"], d["tte_band"], d["price_band"]))

    cold = d[d["is_cold"]]
    aged = d[~d["is_cold"] & (d["tte_d"] > 3.0) & (d["age_h"] > 72.0)]

    # Per (cell, event) aged aggregates for LOEO comparators. Plain dicts
    # throughout (review C-2: pandas treats tuple cell keys as multi-level
    # indexers; .loc lookups crash or, worse, get_level_values membership
    # silently returns False and zeroes the bootstrap arrays).
    ag = aged.groupby(["cell", "event_ticker"], observed=True)["e"].agg(["sum", "count"])
    ag_d: dict = {}
    cell_tot_d: dict = {}
    for key, s, n in zip(ag.index, ag["sum"].to_numpy(), ag["count"].to_numpy()):
        ag_d[key] = (float(s), int(n))
        cell = key[0]
        S, N, K = cell_tot_d.get(cell, (0.0, 0, 0))
        cell_tot_d[cell] = (S + float(s), N + int(n), K + 1)

    # Point estimate with LOEO + validity.
    cold_lists = cold.groupby(["cell", "event_ticker"], observed=True)["e"].agg(list)
    included = []
    excluded_trades = 0
    excluded_events: set = set()
    excluded_by_group: dict = {}
    for (cell, ev), e_vals in cold_lists.items():
        tot = cell_tot_d.get(cell)
        if tot is not None:
            S, N, K = tot
            if (cell, ev) in ag_d:
                s_e, n_e = ag_d[(cell, ev)]
                S, N, K = S - s_e, N - n_e, K - 1
        if tot is None or N < MIN_AGED_TRADES or K < MIN_AGED_EVENTS:
            excluded_trades += len(e_vals)
            excluded_events.add(ev)
            excluded_by_group[cell[0]] = excluded_by_group.get(cell[0], 0) + len(e_vals)
            continue
        a_c = S / N
        for e_val in e_vals:
            included.append((ev, e_val - a_c))
    if not included:
        return {"fee_mode": fee_mode, "error": "no included cold fills"}
    inc = pd.DataFrame(included, columns=["event_ticker", "v"])
    point = float(inc["v"].mean())
    n_events_included = int(inc["event_ticker"].nunique())

    # Joint bootstrap: resample events from the UNION of cold+aged events;
    # recompute comparators (validity inside the resample, LOEO by excluding
    # all copies of the cold trade's own event) and the pooled cold mean.
    cold_ev = cold.groupby(["cell", "event_ticker"], observed=True)["e"].agg(["sum", "count"])
    cold_d = {k: (float(s), int(n)) for k, s, n in
              zip(cold_ev.index, cold_ev["sum"].to_numpy(), cold_ev["count"].to_numpy())}
    all_events = pd.Index(sorted(set(cold["event_ticker"]) | set(aged["event_ticker"])))
    ev_pos = {e: i for i, e in enumerate(all_events)}
    n_ev = len(all_events)

    # Dense per-cell arrays indexed by event position, built from the dicts
    # (review C-2: never use get_level_values membership on tuple cells).
    cells = sorted({k[0] for k in ag_d} | {k[0] for k in cold_d}, key=str)
    cell_arrays = {
        c: (np.zeros(n_ev), np.zeros(n_ev), np.zeros(n_ev), np.zeros(n_ev))
        for c in cells
    }
    for (cell, ev), (s, n) in ag_d.items():
        a_s, a_n, _, _ = cell_arrays[cell]
        i = ev_pos[ev]
        a_s[i] = s; a_n[i] = n
    for (cell, ev), (s, n) in cold_d.items():
        _, _, c_s, c_n = cell_arrays[cell]
        i = ev_pos[ev]
        c_s[i] = s; c_n[i] = n

    rng = np.random.default_rng(RNG_SEED)
    means = np.empty(N_RESAMPLES)
    t0 = time.time()
    for b in range(N_RESAMPLES):
        mult = np.bincount(rng.integers(0, n_ev, size=n_ev), minlength=n_ev).astype(float)
        num = 0.0
        den = 0.0
        for c, (a_s, a_n, c_s, c_n) in cell_arrays.items():
            S = float(np.dot(mult, a_s)); N = float(np.dot(mult, a_n))
            K = int(np.count_nonzero((mult > 0) & (a_n > 0)))
            sel = np.where((mult > 0) & (c_n > 0))[0]
            if len(sel) == 0:
                continue
            for i in sel:
                S_i = S - mult[i] * a_s[i]
                N_i = N - mult[i] * a_n[i]
                K_i = K - (1 if a_n[i] > 0 else 0)
                if N_i < MIN_AGED_TRADES or K_i < MIN_AGED_EVENTS:
                    continue
                a_c = S_i / N_i
                w = mult[i] * c_n[i]
                num += mult[i] * c_s[i] - w * a_c
                den += w
        means[b] = num / den if den > 0 else np.nan
    means = means[~np.isnan(means)]
    lo, hi = float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))

    # Cluster-level stats for the probe power formula (critic C-2).
    ev_means = inc.groupby("event_ticker")["v"].mean()
    return {
        "fee_mode": fee_mode,
        "point_pp": point * 100,
        "ci_pp": [lo * 100, hi * 100],
        "n_cold_included": int(len(inc)),
        "n_cold_excluded_unmatched": int(excluded_trades),
        "n_events_excluded_unmatched": int(len(excluded_events)),
        "excluded_by_group": excluded_by_group,
        "n_events_included": n_events_included,
        "n_resamples_valid": int(len(means)),
        "bootstrap_seconds": round(time.time() - t0, 1),
        "cluster_var_pp2": float(ev_means.var(ddof=1)) * 10000,
        "mde_pp": float(1.96 * ev_means.std(ddof=1) / np.sqrt(len(ev_means))) * 100,
        "mde_definition": "1.96*SE (just-significant at ~50pct power)",
    }


def p1_diagnostics(df: pd.DataFrame) -> dict:
    """Report-only: 2025-only split, paired within-market diagnostic,
    composition tables (compact)."""
    d = df[~df["graveyard"] & (df["group"] != "unknown")
           & (df["tte_band"] >= 0) & (df["price_band"] >= 0)].copy()
    fee = np.where(d["fee_status"] == "ceil_175", d["fee_era"],
                   np.where(d["fee_status"] == "zero", 0.0, 0.0))
    d["e"] = d["gross"] - fee
    out: dict = {}
    # Per-group cold counts (composition).
    out["cold_counts_by_group"] = (
        d[d["is_cold"]].groupby("group", observed=True)["e"].size().to_dict()
    )
    # Within-market paired diagnostic (H-2): markets with both classes.
    cold_m = d[d["is_cold"]].groupby("event_ticker")["e"].mean()
    aged_m = d[~d["is_cold"] & (d["tte_d"] > 3.0) & (d["age_h"] > 72.0)].groupby("event_ticker")["e"].mean()
    both = cold_m.index.intersection(aged_m.index)
    if len(both) >= 10:
        paired = (cold_m[both] - aged_m[both])
        out["paired_within_event"] = {
            "n_events": int(len(both)),
            "mean_pp": float(paired.mean()) * 100,
            "se_pp": float(paired.std(ddof=1) / np.sqrt(len(paired))) * 100,
        }
    return out


def run_p2a(con, cat_map: dict) -> dict:
    """Oriented trailing-imbalance halves (report-only)."""
    q = f"""
        WITH mk AS (
            SELECT ticker, event_ticker, result FROM '{MARKETS}' WHERE {POP_FILTERS}
        ),
        tr AS (
            SELECT
                t.ticker, m.event_ticker, m.result,
                regexp_extract(m.event_ticker, '^([A-Z0-9]+)', 1) AS prefix,
                t.taker_side, t.count, t.created_time,
                (CASE WHEN t.taker_side='yes' THEN t.no_price ELSE t.yes_price END)/100.0 AS maker_price,
                (CASE WHEN t.taker_side != m.result THEN 1.0 ELSE 0.0 END) AS maker_won,
                (CASE WHEN t.taker_side='yes' THEN t.count ELSE -t.count END) AS signed
            FROM '{TRADES}' t INNER JOIN mk m ON t.ticker = m.ticker
            WHERE t.yes_price >= 3 AND t.yes_price <= 97
              AND t.yes_price + t.no_price = 100 AND t.count > 0
              AND t.taker_side IN ('yes','no')
              AND m.event_ticker NOT LIKE 'KXMVE%'
        ),
        win AS (
            -- Peers-exclusive (review H-4): RANGE ... CURRENT ROW includes
            -- same-timestamp peers; subtract the peer window so 'prior' is
            -- strictly-before-t per lock M-2. The 60-minute lower bound is
            -- inclusive (RANGE semantics; pre-registered convention).
            SELECT *,
                SUM(signed) OVER w - SUM(signed) OVER pk AS net_prior,
                COUNT(*) OVER w - COUNT(*) OVER pk AS n_prior
            FROM tr
            WINDOW w AS (
                PARTITION BY ticker ORDER BY created_time
                RANGE BETWEEN INTERVAL 60 MINUTES PRECEDING AND CURRENT ROW
            ),
            pk AS (
                PARTITION BY ticker ORDER BY created_time
                RANGE BETWEEN CURRENT ROW AND CURRENT ROW
            )
        )
        SELECT event_ticker, prefix, maker_price, maker_won,
            (CASE WHEN taker_side='yes' THEN net_prior ELSE -net_prior END) AS oriented
        FROM win
        WHERE n_prior >= 5
    """
    d = con.execute(q).df()
    meta = d["prefix"].map(lambda p: cat_map.get(p, {"group": "unknown"}))
    d["group"] = [m["group"] for m in meta]
    d["e"] = d["maker_won"] - d["maker_price"]  # GROSS (fee-free; stated)
    out = {"_conventions": {
        "metric": "gross maker excess (fee-free; fee largely cancels in the half contrast)",
        "tie_rule": "<= median half",
        "min_group_prints": 2000, "min_half_prints": 500,
    }, "_skipped_groups": []}
    for g, sub in d.groupby("group", observed=True):
        if len(sub) < 2000:
            out["_skipped_groups"].append([str(g), int(len(sub))])
            continue
        med = sub["oriented"].median()
        lo_half = sub[sub["oriented"] <= med]
        hi_half = sub[sub["oriented"] > med]
        if len(lo_half) < 500 or len(hi_half) < 500:
            out["_skipped_groups"].append([str(g), int(len(sub))])
            continue
        out[g] = {
            "n": [int(len(lo_half)), int(len(hi_half))],
            "mean_pp": [float(lo_half["e"].mean()) * 100, float(hi_half["e"].mean()) * 100],
            "events": [int(lo_half["event_ticker"].nunique()), int(hi_half["event_ticker"].nunique())],
        }
    return out


def run_p3(con, cat_map: dict) -> dict:
    """One-leg-per-event longshot calibration (kill-gated)."""
    from scipy.stats import binom
    q = f"""
        WITH mk AS (
            SELECT ticker, event_ticker, result, open_time, close_time
            FROM '{MARKETS}' WHERE {POP_FILTERS}
        ),
        legs AS (
            SELECT m.event_ticker,
                regexp_extract(m.event_ticker, '^([A-Z0-9]+)', 1) AS prefix,
                t.ticker, m.result,
                MIN(m.open_time) AS open_time,
                SUM(t.count) AS vol,
                COUNT(*) AS n_prints,
                SUM(t.yes_price/100.0 * t.count) / SUM(t.count) AS impl_p
            FROM '{TRADES}' t INNER JOIN mk m ON t.ticker = m.ticker
            WHERE t.created_time < m.close_time
              AND t.yes_price >= 3 AND t.yes_price <= 8
              AND t.yes_price + t.no_price = 100 AND t.count > 0
              AND t.taker_side IN ('yes','no')
              AND m.event_ticker NOT LIKE 'KXMVE%'
            GROUP BY m.event_ticker, prefix, t.ticker, m.result
        ),
        ranked AS (
            SELECT *, ROW_NUMBER() OVER (
                PARTITION BY event_ticker
                ORDER BY vol DESC, n_prints DESC, ticker ASC
            ) AS rk FROM legs
        )
        SELECT event_ticker, prefix, ticker, result, open_time, vol, impl_p
        FROM ranked WHERE rk = 1
        ORDER BY event_ticker
    """
    d = con.execute(q).df()
    meta = d["prefix"].map(lambda p: cat_map.get(p, {"group": "unknown", "graveyard": False}))
    d["group"] = [m["group"] for m in meta]
    d["graveyard"] = [bool(m["graveyard"]) for m in meta]
    d = d[~d["graveyard"] & (d["group"] != "unknown")]
    n = len(d)
    if n == 0:
        return {"error": "empty"}
    yes_count = int((d["result"] == "yes").sum())
    p_bar = float(d["impl_p"].mean())
    p_onesided = float(binom.cdf(yes_count, n, p_bar))
    # NO-side excess per event (report + cluster sensitivity by prefix).
    d["no_excess"] = np.where(d["result"] == "no", d["impl_p"], d["impl_p"] - 1.0)
    fee = ceil_fee(1.0 - d["impl_p"].to_numpy())
    d["no_excess_net"] = d["no_excess"] - fee
    # Mandatory decay split (Whelan; K-P3 requires 2025 edge >= +1pp).
    early = d[d["open_time"] < pd.Timestamp("2025-01-01", tz="UTC")]
    late = d[d["open_time"] >= pd.Timestamp("2025-01-01", tz="UTC")]
    # Lock-mandated CIs (review H-5): event-cluster bootstrap (here each
    # event contributes one observation, so this is a per-event bootstrap)
    # plus the series-prefix-clustered sensitivity with its write-up
    # consequence if it includes zero.
    import sys as _sys
    _sys.path.insert(0, str(BASE / "src"))
    from kalshi_bot.analysis.bootstrap import cluster_bootstrap_mean_ci
    vals = d["no_excess_net"].to_numpy()
    _, ev_lo, ev_hi, _ = cluster_bootstrap_mean_ci(
        vals, d["event_ticker"].to_numpy(), n_resamples=5000, ci=0.95, rng_seed=42)
    _, px_lo, px_hi, px_k = cluster_bootstrap_mean_ci(
        vals, d["prefix"].to_numpy(), n_resamples=5000, ci=0.95, rng_seed=42)
    prefix_tbl = d.groupby("prefix")["no_excess_net"].agg(["mean", "size"]).nlargest(8, "size")
    return {
        "n_events": n,
        "yes_count": yes_count,
        "p_bar": p_bar,
        "realized_yes_rate": yes_count / n,
        "binom_p_onesided_lower": p_onesided,
        "no_excess_net_pp": float(d["no_excess_net"].mean()) * 100,
        "event_ci_pp": [ev_lo * 100, ev_hi * 100],
        "prefix_ci_pp_sensitivity": [px_lo * 100, px_hi * 100],
        "n_prefix_clusters": int(px_k),
        "decay_split_pp": {
            "2024Q4": [float(early["no_excess_net"].mean()) * 100 if len(early) else None, int(len(early))],
            "2025": [float(late["no_excess_net"].mean()) * 100 if len(late) else None, int(len(late))],
        },
        "by_prefix_top": {str(k): [float(v["mean"]) * 100, int(v["size"])]
                          for k, v in prefix_tbl.iterrows()},
        "fee_note": "flat era ceil fee on every leg (documented conservative bound; review M-3)",
    }


def main() -> None:
    con = duckdb.connect(":memory:")
    con.execute("PRAGMA threads=8")
    con.execute("PRAGMA memory_limit='12GB'")
    con.execute("SET TimeZone='UTC'")
    cat_map = load_map()
    fee_rows = load_fee_rows()

    print("=== P1: pull ===", flush=True)
    t0 = time.time()
    df = pull_p1(con)
    print(f"  {len(df):,} prints in {time.time()-t0:.0f}s", flush=True)
    df = attach_cells(df, cat_map, fee_rows)

    # Mandatory after-close dropped-share report (lock population rule;
    # review M-1): same population WITHOUT the created_time < close_time cut.
    drop_q = f"""
        WITH mk AS (
            SELECT ticker, close_time FROM '{MARKETS}'
            WHERE {POP_FILTERS} AND (close_time - open_time) >= INTERVAL 10 DAYS
        )
        SELECT
            SUM(CASE WHEN t.created_time >= m.close_time THEN 1 ELSE 0 END) AS dropped,
            COUNT(*) AS total
        FROM '{TRADES}' t INNER JOIN mk m ON t.ticker = m.ticker
        WHERE t.yes_price >= 3 AND t.yes_price <= 97
          AND t.yes_price + t.no_price = 100 AND t.count > 0
          AND t.taker_side IN ('yes','no')
    """
    dropped, total = con.execute(drop_q).fetchone()
    results: dict = {
        "lock": "research/v22/00-methodology-lock.md v2",
        "after_close_dropped_share": float(dropped) / float(total) if total else 0.0,
    }
    print(f"  after-close dropped share: {results['after_close_dropped_share']:.4%}", flush=True)
    for mode in ("table_low", "table_high"):
        print(f"=== P1 estimate ({mode}) ===", flush=True)
        r = p1_estimate(df, mode)
        results[f"p1_{mode}"] = r
        print(f"  {json.dumps({k: v for k, v in r.items() if k != 'fee_mode'})}", flush=True)
    # 2025-only split (critic M-6; review H-2): split on MARKET open_time
    # (the premium is a property of the listing; keeps cold and aged from
    # the same vintage inside each cell; matches P3's split). Run under both
    # fee modes; the probe power formula uses the SMALLER effect.
    df_2025 = df[df["m_open"] >= pd.Timestamp("2025-01-01", tz="UTC")]
    for mode in ("table_low", "table_high"):
        r = p1_estimate(df_2025, mode)
        results[f"p1_2025_only_{mode}"] = r
        print(f"  2025-only ({mode}): "
              f"{json.dumps({k: v for k, v in r.items() if k != 'fee_mode'})}", flush=True)
    # Locked required-N for the live probe (lock section 2; conservative =
    # smaller effect across fee modes, cluster variance from the same run).
    eff = []
    for mode in ("table_low", "table_high"):
        r = results[f"p1_2025_only_{mode}"]
        if "error" not in r and r["point_pp"] > 0:
            eff.append((r["point_pp"], r["cluster_var_pp2"]))
    if eff:
        e_min, var = min(eff, key=lambda x: x[0])
        results["probe_required_N"] = int(np.ceil(
            (1.96 + 0.8416) ** 2 * var / (0.5 * e_min) ** 2
        ))
    else:
        results["probe_required_N"] = None  # 2025-only effect <= 0: Whelan guard
    print(f"  probe_required_N: {results['probe_required_N']}", flush=True)
    results["p1_diagnostics"] = p1_diagnostics(df)

    k1_low = results["p1_table_low"]
    k1_high = results["p1_table_high"]
    k_p1 = bool(
        "error" not in k1_low and "error" not in k1_high
        and k1_low["point_pp"] > 0 and k1_low["ci_pp"][0] > 0
        and k1_high["point_pp"] > 0 and k1_high["ci_pp"][0] > 0
        and min(k1_low["n_events_included"], k1_high["n_events_included"]) >= K_P1_MIN_EVENTS
    )
    results["K_P1_pass"] = k_p1
    print(f"=== K-P1: {'PASS' if k_p1 else 'KILL'} ===", flush=True)

    print("=== P2a (report-only) ===", flush=True)
    results["p2a"] = run_p2a(con, cat_map)
    print(f"  groups: {list(results['p2a'].keys())}", flush=True)

    print("=== P3 ===", flush=True)
    p3 = run_p3(con, cat_map)
    results["p3"] = p3
    if "error" not in p3:
        late_pp = p3["decay_split_pp"]["2025"][0]
        k_p3 = bool(
            p3["no_excess_net_pp"] > 2.0
            and p3["binom_p_onesided_lower"] <= 0.05
            and late_pp is not None and late_pp >= 1.0
        )
        results["K_P3_pass"] = k_p3
        print(f"  n={p3['n_events']} yes_rate={p3['realized_yes_rate']:.4f} "
              f"vs p_bar={p3['p_bar']:.4f} binom_p={p3['binom_p_onesided_lower']:.2e} "
              f"no_excess_net={p3['no_excess_net_pp']:+.2f}pp "
              f"2025={late_pp if late_pp is None else round(late_pp, 2)}pp -> "
              f"{'PASS' if k_p3 else 'KILL'}", flush=True)

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"[done] wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
