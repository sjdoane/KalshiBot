"""v27 model + backtest per research/v27/02-methodology-lock.md (frozen constants).

Modes:
  --audit-0b   outcome-blind fire projection + A11 threshold decision (pre-lock)
  (default)    full post-lock run: H1 + control, then D1 in a separate ordered pass,
               gates, sensitivities. Requires the locking commit to exist.

Data: data/v26/markets_all.json + trades.jsonl (KXTSAW subset, deduped),
data/v27/tsa_vintages.json (first-published values, K1-validated settlement basis),
data/v27/bts_daily.json (sched/cancelled ground truth through 2026-05-31).
"""
from __future__ import annotations

import bisect
import json
import math
import os
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")
V26 = os.path.join("data", "v26")
V27 = os.path.join("data", "v27")

# ---- frozen lock constants ----
BAND = (0.05, 0.95)
HAIRCUT, HAIRCUT_MATCHED = 0.03, 0.01
BIND_LO, BIND_HI = "2024-12-01", "2026-05-31"   # BTS schedule coverage bound
BASE_WEEKS, BASE_MIN = 6, 4                       # same-weekday baseline
SCHED_CLAMP = (0.9, 1.1)
MIN_ERRS = 15
BUCKETS = [(3, 3), (4, 5), (6, 7)]   # E4: n_unpub is never below 3 at a legal fire
D1_BETAS = [0.3, 0.5, 1.0]           # E9: frozen grid; family death only if ALL fail
HOLIDAYS = [
    "2024-12-25", "2025-01-01", "2025-01-20", "2025-02-17", "2025-05-26",
    "2025-06-19", "2025-07-04", "2025-09-01", "2025-10-13", "2025-11-11",
    "2025-11-27", "2025-12-25", "2026-01-01", "2026-01-19", "2026-02-16",
    "2026-05-25", "2026-06-19",
]
HOLIDAY_PREV = {  # same holiday one year earlier
    "2025-11-27": "2024-11-28", "2025-12-25": "2024-12-25", "2026-01-01": "2025-01-01",
    "2026-01-19": "2025-01-20", "2026-02-16": "2025-02-17", "2026-05-25": "2025-05-26",
    "2026-06-19": "2025-06-19",
}


def taker_fee(p: float) -> float:
    if p > 1.0:
        raise ValueError(p)
    return math.ceil(7.0 * p * (1.0 - p) - 1e-12) / 100.0


def norm_strike(k: float) -> float:
    return k / 1_000_000.0 if k > 1000 else k


def week_days(close_time: str) -> list[date]:
    close_et = (datetime.strptime(close_time[:19], "%Y-%m-%dT%H:%M:%S")
                .replace(tzinfo=UTC).astimezone(ET))
    sunday = close_et.date()
    if sunday.weekday() != 6:
        sunday = sunday - timedelta(days=(sunday.weekday() - 6) % 7)
    return [sunday - timedelta(days=i) for i in range(6, -1, -1)]


def iso_week(close_time: str) -> str:
    d = date.fromisoformat(close_time[:10])
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


class Data:
    def __init__(self):
        self.markets = {t: m for t, m in json.load(
            open(os.path.join(V26, "markets_all.json"), encoding="utf-8")).items()
            if t.startswith("KXTSAW") and m.get("result") in ("yes", "no")
            and BIND_LO <= m["close_time"][:10] <= BIND_HI + "T23"}
        self.vint = {}
        for k, r in json.load(open(os.path.join(V27, "tsa_vintages.json"), encoding="utf-8")).items():
            self.vint[date.fromisoformat(k)] = (
                r["first_value"],
                datetime.strptime(r["first_seen"][:14], "%Y%m%d%H%M%S").replace(tzinfo=UTC),
            )
        self.bts = {date.fromisoformat(k): v for k, v in json.load(
            open(os.path.join(V27, "bts_daily.json"), encoding="utf-8")).items()}
        self.hol_window: dict[date, date] = {}
        for h in HOLIDAYS:
            hd = date.fromisoformat(h)
            for off in (-1, 0, 1):
                self.hol_window[hd + timedelta(days=off)] = hd

    def val(self, d: date, asof: datetime | None = None) -> float | None:
        r = self.vint.get(d)
        if r is None:
            return None
        if asof is not None and r[1] > asof:
            return None
        return float(r[0])

    def published_by_rule(self, d: date, t_et: datetime) -> bool:
        pub = d + timedelta(days=1)
        while pub.weekday() >= 5:
            pub += timedelta(days=1)
        return t_et > datetime(pub.year, pub.month, pub.day, 12, 0, tzinfo=ET)

    def baseline(self, d: date, asof: datetime) -> float | None:
        vals = []
        u = d - timedelta(days=7)
        for _ in range(BASE_WEEKS):
            v = self.val(u, asof)
            if v is not None:
                vals.append(v)
            u -= timedelta(days=7)
        if len(vals) < BASE_MIN:
            return None
        vals.sort()
        n = len(vals)
        return (vals[n // 2] if n % 2 else 0.5 * (vals[n // 2 - 1] + vals[n // 2]))

    def sched_ratio(self, d: date) -> float | None:
        b = self.bts.get(d)
        if b is None:
            return None
        hist = []
        u = d - timedelta(days=7)
        for _ in range(BASE_WEEKS):
            h = self.bts.get(u)
            if h is not None:
                hist.append(h["sched"])
            u -= timedelta(days=7)
        if len(hist) < BASE_MIN:
            return None
        hist.sort()
        n = len(hist)
        med = hist[n // 2] if n % 2 else 0.5 * (hist[n // 2 - 1] + hist[n // 2])
        return max(SCHED_CLAMP[0], min(SCHED_CLAMP[1], b["sched"] / med))

    def hol_factor(self, d: date, asof: datetime) -> float | None:
        """E1/E2: inside a holiday window with no prior-year factor = NO FIRE (None),
        never a silent 1.0. Ratio formula frozen: prior-year same-offset vintage value
        over its own 6-week same-weekday baseline."""
        hd = self.hol_window.get(d)
        if hd is None:
            return 1.0
        prev = HOLIDAY_PREV.get(str(hd))
        if prev is None:
            return None
        pd = date.fromisoformat(prev) + (d - hd)
        v = self.val(pd, asof)
        base = self.baseline(pd, asof)
        if v is None or base is None or base <= 0:
            return None
        return v / base

    def pred_day(self, d: date, asof: datetime, mode: str, beta: float = 1.0) -> float | None:
        base = self.baseline(d, asof)
        if base is None:
            return None
        hf = self.hol_factor(d, asof)
        if hf is None:
            return None
        f = base * hf
        if mode in ("h1", "d1"):
            sr = self.sched_ratio(d)
            if sr is None:
                return None
            f *= sr
        if mode == "d1":
            b = self.bts.get(d)
            if b is None or b["sched"] <= 0:
                return None
            f *= ((b["sched"] - b["cancelled"]) / b["sched"]) ** beta
        return f


def p_above(point: float, k: float, errs: list[float]) -> float | None:
    """E6 support rule: NO FIRE (None) when the needed error lies outside the
    observed support; interpolation only, never extrapolated tails."""
    n = len(errs)
    need = k - point
    if need < errs[0] or need > errs[-1]:
        return None
    i = bisect.bisect_right(errs, need)
    if i == 0:
        return 1.0 - 0.5 / n
    if i == n:
        return 0.5 / n
    lo, hi = errs[i - 1], errs[i]
    frac = (need - lo) / (hi - lo) if hi > lo else 0.0
    return max(min(1.0 - (i - 1 + frac + 0.5) / n, 1.0 - 0.5 / n), 0.5 / n)


def bucket_of(n_unpub: int):
    for lo, hi in BUCKETS:
        if lo <= n_unpub <= hi:
            return (lo, hi)
    return None


class Errors:
    """Walk-forward weekly-average error distributions per mode and bucket."""

    def __init__(self, data: Data, events: list[dict]):
        self.rows = []  # (close_date, mode, bucket, err)
        for m in events:
            days = week_days(m["close_time"])
            actual = [data.val(d) for d in days]
            if any(v is None for v in actual):
                continue
            actual_avg = sum(actual) / 7.0 / 1e6
            for n_unpub in range(0, 8):
                pub = days[:7 - n_unpub]
                unpub = days[7 - n_unpub:]
                # historical as-of: noon ET on the first day AFTER the last published
                ref_day = (pub[-1] + timedelta(days=1)) if pub else days[0]
                asof = datetime(ref_day.year, ref_day.month, ref_day.day, 17, 0, tzinfo=UTC)
                modes = ["h1", "control"] + [f"d1@{b}" for b in D1_BETAS]
                for mode in modes:
                    beta = float(mode.split("@")[1]) if mode.startswith("d1@") else 1.0
                    core = "d1" if mode.startswith("d1@") else mode
                    tot = 0.0
                    ok = True
                    for d in pub:
                        v = data.val(d)
                        tot += v if v is not None else 0
                        ok = ok and v is not None
                    for d in unpub:
                        pv = data.pred_day(d, asof, core, beta)
                        if pv is None:
                            ok = False
                            break
                        tot += pv
                    if not ok:
                        continue
                    b = bucket_of(n_unpub)
                    if b is None:
                        continue
                    self.rows.append((date.fromisoformat(m["close_time"][:10]), mode, b, actual_avg - tot / 7.0 / 1e6))

    def dist(self, mode: str, b, before: date) -> list[float]:
        return sorted(e for cd, md, bb, e in self.rows if md == mode and bb == b and cd < before)


def evaluate(data: Data, threshold: float, signal_mode: str, verbose=False):
    """signal_mode: h1 | control | d1 (fires on that mode's P). Returns fires."""
    events = {}
    for t, m in data.markets.items():
        events[m["event_ticker"]] = m
    errors = Errors(data, list(events.values()))
    trades = []
    seen = set()
    with open(os.path.join(V26, "trades.jsonl"), encoding="utf-8") as f:
        for line in f:
            if '"KXTSAW"' not in line:
                continue
            t = json.loads(line)
            k5 = (t["ticker"], t["created_time"], t["yes_price_dollars"], t.get("count_fp"), t.get("taker_side"))
            if k5 in seen:
                continue
            seen.add(k5)
            trades.append(t)
    trades.sort(key=lambda t: t["created_time"])
    fires = []
    taken = set()
    n = defaultdict(int)
    for t in trades:
        m = data.markets.get(t["ticker"])
        if m is None or m.get("floor_strike") is None or m.get("strike_type") != "greater":
            continue
        p = float(t["yes_price_dollars"])
        if not (BAND[0] <= p <= BAND[1]):
            continue
        n["band"] += 1
        t_utc = datetime.strptime(t["created_time"][:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=UTC)
        t_et = t_utc.astimezone(ET)
        dk = (t["ticker"], t_et.date().isoformat())
        if dk in taken:
            continue
        days = week_days(m["close_time"])
        pub = [d for d in days if data.published_by_rule(d, t_et)]
        unpub = [d for d in days if not data.published_by_rule(d, t_et)]
        # evaluability (A7): every required published day snapshot-proven at print time
        if any(data.val(d, t_utc) is None for d in pub):
            n["uneval"] += 1
            continue
        n_unpub = len(unpub)
        b = bucket_of(n_unpub)
        if b is None or n_unpub == 0:
            n["nopub"] += 1
            continue
        close_d = date.fromisoformat(m["close_time"][:10])
        probs = {}
        ok = True
        modes = ["h1", "control"] + [f"d1@{bb}" for bb in D1_BETAS]
        for mode in modes:
            beta = float(mode.split("@")[1]) if mode.startswith("d1@") else 1.0
            core = "d1" if mode.startswith("d1@") else mode
            errs = errors.dist(mode, b, close_d)
            if len(errs) < MIN_ERRS:
                ok = False
                break
            tot = sum(data.val(d, t_utc) for d in pub)
            preds = [data.pred_day(d, t_utc, core, beta) for d in unpub]
            if any(v is None for v in preds):
                ok = False
                break
            avg_hat = (tot + sum(preds)) / 7.0 / 1e6
            pv = p_above(avg_hat, norm_strike(float(m["floor_strike"])), errs)
            if pv is None:
                ok = False  # E6 support rule: outside observed error support = NO FIRE
                break
            probs[mode] = pv
        if not ok:
            n["errs"] += 1
            continue
        div = probs[signal_mode] - p
        if abs(div) < threshold:
            continue
        side = "yes" if div > 0 else "no"
        fires.append({
            "ticker": t["ticker"], "event": m["event_ticker"],
            "cluster": m["event_ticker"],  # E14: one event = one Mon-Sun ET week
            "month": m["close_time"][:7], "p_print": p, "side": side,
            "matched": (t.get("taker_side") or "").lower() == side,
            "probs": probs, "div": div, "n_unpub": n_unpub, "result": m["result"],
            "et_dow": t_et.weekday(), "close": m["close_time"],
            "max_cancel": max((data.bts.get(d, {"cancelled": 0})["cancelled"] for d in days), default=0),
        })
        taken.add(dk)
        n["fired"] += 1
        if verbose and n["fired"] % 50 == 0:
            print(f"fires {n['fired']}", flush=True)
    return fires, dict(n)


def pnl(fires, haircut=HAIRCUT, matched_only=False):
    rows = []
    for f in fires:
        if matched_only and not f["matched"]:
            continue
        cost = (f["p_print"] if f["side"] == "yes" else 1 - f["p_print"]) + haircut
        if cost > 1.0:
            raise AssertionError(f)
        rows.append({**f, "pnl": (1.0 if f["result"] == f["side"] else 0.0) - cost - taker_fee(cost)})
    return rows


def ci_of(rows, key="cluster"):
    if not rows:
        return None
    sys.path.insert(0, "src")
    from kalshi_bot.analysis.bootstrap import cluster_bootstrap_mean_ci
    mean, lo, hi, n_c = cluster_bootstrap_mean_ci(
        [r["pnl"] for r in rows], [r[key] for r in rows], n_resamples=10_000, rng_seed=27)
    return {"mean": mean, "lo": lo, "hi": hi, "n_fires": len(rows), "n_clusters": n_c}


def loco_ci(rows):
    by = defaultdict(float)
    for r in rows:
        by[r["cluster"]] += r["pnl"]
    if not by:
        return None, None
    best = max(by, key=by.get)
    return best, ci_of([r for r in rows if r["cluster"] != best])


def audit_0b():
    data = Data()
    out = {}
    fires, funnel = evaluate(data, 0.08, "h1", verbose=True)
    print("funnel:", funnel)
    for thr in (0.08, 0.12):
        sel = [f for f in fires if abs(f["div"]) >= thr]
        cl = {f["cluster"] for f in sel}
        edges = []
        for f in sel:
            cost = (f["p_print"] if f["side"] == "yes" else 1 - f["p_print"]) + HAIRCUT
            p_true = f["probs"]["h1"] if f["side"] == "yes" else 1 - f["probs"]["h1"]
            edges.append(p_true - cost - taker_fee(cost))
        me = sum(edges) / len(edges) if edges else float("nan")
        sub5 = sum(1 for e in edges if e < 0.05) / len(edges) if edges else float("nan")
        print(f"H1 thr {thr}: fires={len(sel)} clusters={len(cl)} mean_cond_edge={me:.4f} sub5pp_frac={sub5:.2f}")
        out[str(thr)] = {"fires": len(sel), "clusters": len(cl), "edge": me, "sub5pp": sub5}
    decision = 0.08 if out["0.08"]["edge"] >= 0.08 else 0.12
    # E13 closure demo: max cost at the band edge under the chosen threshold
    max_p = BAND[1]
    print(f"E13 closure: max p_exec = {max_p + HAIRCUT:.2f}, all-in <= {max_p + HAIRCUT + taker_fee(max_p + HAIRCUT):.3f} < 1.00")
    # E7 recompute: per-CLUSTER evaluability under LOCK band and rules
    ev_clusters = {f["cluster"] for f in fires}
    all_events = {m["event_ticker"] for m in data.markets.values()}
    cov = len(ev_clusters) / len(all_events)
    print(f"E7 cluster coverage: {len(ev_clusters)}/{len(all_events)} events with >=1 evaluable fire-candidate = {cov:.1%}")
    # D1 projection per beta (inference-input swap only)
    d1_proj = {}
    for beta in D1_BETAS:
        d1f, _ = evaluate(data, decision, f"d1@{beta}")
        d1c = {f["cluster"] for f in d1f}
        d1_proj[str(beta)] = {"fires": len(d1f), "clusters": len(d1c)}
        print(f"D1@{beta} at {decision}: fires={len(d1f)} clusters={len(d1c)} (floors 20/8)")
    print(f"A11 DECISION: threshold {decision}")
    json.dump({"decision": decision, "h1_proj": out, "d1_proj": d1_proj,
               "e7_cluster_coverage": cov},
              open(os.path.join(V27, "audit_0b_decision.json"), "w", encoding="utf-8"))


def full_run():
    dec = json.load(open(os.path.join(V27, "audit_0b_decision.json"), encoding="utf-8"))
    thr = dec["decision"]
    data = Data()
    res = {"threshold": thr}
    h1_fires, funnel = evaluate(data, thr, "h1")
    res["funnel"] = funnel
    rows = pnl(h1_fires)
    res["h1"] = {"binding": ci_of(rows)}
    ctrl_fires, _ = evaluate(data, thr, "control")
    crows = pnl(ctrl_fires)
    res["h1"]["control"] = ci_of(crows)
    b = res["h1"]["binding"]
    res["h1"]["power_ok"] = bool(b and b["n_fires"] >= 40 and b["n_clusters"] >= 30)
    res["h1"]["ci_ok"] = bool(res["h1"]["power_ok"] and b["lo"] > 0)
    cc = res["h1"]["control"]
    ctrl_clears = bool(cc and cc["n_fires"] >= 40 and cc["n_clusters"] >= 30 and cc["lo"] > 0)
    best, l = loco_ci(rows)
    res["h1"]["loco_drop"], res["h1"]["loco"] = best, l
    res["h1"]["month_block"] = ci_of(rows, key="month")
    res["h1"]["reported_matched"] = ci_of(pnl(h1_fires, haircut=HAIRCUT_MATCHED, matched_only=True))
    disrupted = [r for r in rows if r["max_cancel"] > 1000]
    res["h1"]["sens_disrupted_5c"] = ci_of(pnl([f for f in h1_fires if f["max_cancel"] > 1000], haircut=0.05))
    res["h1"]["n_disrupted_fires"] = len(disrupted)
    if not res["h1"]["power_ok"]:
        v = "UNDERPOWERED-NULL" if rows else "NO-FIRES NULL"
    elif not res["h1"]["ci_ok"]:
        v = "NULL"
    elif ctrl_clears:
        v = "NULL (control clears: seasonality, not aviation info)"
    elif l and l["lo"] <= 0:
        v = "MARGINAL"
    elif res["h1"]["month_block"] and res["h1"]["month_block"]["lo"] <= 0:
        v = "FRAGILE-PASS"
    else:
        v = "PASS (unbankable without live read per A8; stage-1 $0 read + shadow route)"
    res["h1"]["verdict"] = v

    # D1 pass, ordered AFTER H1 results are complete (A4): write intermediate first
    json.dump(res, open(os.path.join(V27, "backtest_results_h1.json"), "w", encoding="utf-8"), indent=1, default=str)
    res["d1"] = {}
    any_pass = False
    for beta in D1_BETAS:
        d1_fires, _ = evaluate(data, thr, f"d1@{beta}")
        drows = pnl(d1_fires)
        d1ci = ci_of(drows)
        r = {"binding": d1ci}
        r["power_ok"] = bool(d1ci and d1ci["n_fires"] >= 20 and d1ci["n_clusters"] >= 8)
        r["gate"] = bool(r["power_ok"] and d1ci["lo"] > 0 and d1ci["mean"] >= 0.08)
        dbest, dl = loco_ci(drows)
        r["loco_drop"], r["loco"] = dbest, dl
        r["month_block"] = ci_of(drows, key="month")
        r["pass"] = bool(r["gate"] and dl and dl["lo"] > 0
                         and r["month_block"] and r["month_block"]["lo"] > 0)
        any_pass = any_pass or r["pass"]
        res["d1"][f"beta_{beta}"] = r
    res["d1"]["verdict"] = ("SHADOW-JUSTIFIED (at least one frozen beta clears)" if any_pass
                            else "FAMILY-DEATH (all three frozen betas fail the bound)")
    json.dump(res, open(os.path.join(V27, "backtest_results.json"), "w", encoding="utf-8"), indent=1, default=str)
    print(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    if "--audit-0b" in sys.argv:
        audit_0b()
    else:
        full_run()
