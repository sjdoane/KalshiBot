"""v28 backtest per research/v28/02-methodology-lock.md incl. AMENDMENTS v2.

Modes:
  --audit    pre-lock section 0: 0-W withdrawal audit, 0-S settlement-read audit
             (|diff| stats only), 0-B/0-E outcome-blind fire projection + evaluability.
  (default)  post-lock: H-A binding run + D' (realized-arrival bound) + gates.

Frozen constants are lock constants. Data: data/v28/{markets_all.json, trades.jsonl,
rt_vintages.json, rt_slug_map.json}.
"""
from __future__ import annotations

import bisect
import json
import math
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
UTC = timezone.utc
V28 = os.path.join("data", "v28")

CAP_MULT = 2.0
MIN_PRIORS = 12
PRIOR_D_TOL = 2          # priors need a proven row within [d-2, d+2] days-to-close
READ_MARGIN = 1.0        # settlement-read margin in display points (0-S may raise)
HAIRCUT, HAIRCUT_MATCHED = 0.03, 0.01
YES_MAX_P, NO_MIN_P = 0.955, 0.045
FLOOR_FIRES, FLOOR_CLUSTERS = 15, 8
W_DECREASE_REVIEWS = 3   # 0-W thresholds (amendments block)
W_RATE = 0.03


def taker_fee(p: float) -> float:
    if p > 1.0:
        raise ValueError(p)
    return math.ceil(7.0 * p * (1.0 - p) - 1e-12) / 100.0


def ts_to_dt(ts: str) -> datetime:
    return datetime.strptime(ts[:14], "%Y%m%d%H%M%S").replace(tzinfo=UTC)


class Data:
    def __init__(self):
        self.markets = json.load(open(os.path.join(V28, "markets_all.json"), encoding="utf-8"))
        vint = json.load(open(os.path.join(V28, "rt_vintages.json"), encoding="utf-8"))
        self.paths: dict[str, list[tuple[datetime, int, int]]] = {}
        self.slug: dict[str, str] = {}
        self.close: dict[str, datetime] = {}
        for ev, e in vint.items():
            rows = [(ts_to_dt(r[0]), r[1], r[2]) for r in e.get("rows", [])
                    if r[1] is not None and r[2] is not None and r[2] > 0]
            rows.sort()
            self.paths[ev] = rows
            self.slug[ev] = e.get("slug") or ev
            self.close[ev] = datetime.fromisoformat(e["close_time"].replace("Z", "+00:00"))

    def state_at(self, ev: str, t: datetime):
        rows = self.paths.get(ev) or []
        lo, hi = 0, len(rows)
        while lo < hi:
            mid = (lo + hi) // 2
            if rows[mid][0] <= t:
                lo = mid + 1
            else:
                hi = mid
        return rows[lo - 1] if lo else None

    def final_state(self, ev: str):
        rows = self.paths.get(ev) or []
        return rows[-1] if rows else None

    def read_state(self, ev: str):
        """First row AT/AFTER the settlement read; None if the archive ends before
        the read (then no bound can be validated for this event and it leaves the
        binding set: the 0-S coverage rule)."""
        close = self.close.get(ev)
        for row in self.paths.get(ev) or []:
            if row[0] >= close:
                return row
        return None

    def settle_dt(self, ev: str) -> datetime | None:
        return self.close.get(ev)


def l_interval(s: int, n: int) -> tuple[int, int]:
    lo = max(0, math.ceil((s - 0.5) * n / 100.0 - 1e-9))
    hi = min(n, math.floor((s + 0.5) * n / 100.0 + 1e-9))
    if lo > hi:
        lo = hi = max(0, min(n, round(s * n / 100.0)))
    return lo, hi


def prior_ratios(data: Data, print_dt: datetime, d_days: int):
    """Arrival ratios from movies settled at or before print_dt (E4d), each with a
    proven row within [d-2, d+2] days-to-close."""
    out = []
    for ev, close in data.close.items():
        if close > print_dt:
            continue
        fin = data.final_state(ev)
        if fin is None:
            continue
        best = None
        for row in data.paths[ev]:
            dd = (close - row[0]).total_seconds() / 86400.0
            if d_days - PRIOR_D_TOL <= dd <= d_days + PRIOR_D_TOL:
                if best is None or abs(dd - d_days) < abs(best[0] - d_days):
                    best = (dd, row)
        if best is None:
            continue
        _, row = best
        n_row, n_fin = row[2], fin[2]
        if n_row > 0:
            out.append(max(0.0, (n_fin - n_row) / n_row))
    return out


def bounds(s: int, n: int, a: int, k: float):
    lo_l, hi_l = l_interval(s, n)
    low = 100.0 * lo_l / (n + a) if n + a > 0 else 0.0
    high = 100.0 * (hi_l + a) / (n + a) if n + a > 0 else 100.0
    yes_decided = low > k + READ_MARGIN
    no_decided = high < k - READ_MARGIN
    return low, high, yes_decided, no_decided


def iter_prints():
    seen = set()
    with open(os.path.join(V28, "trades.jsonl"), encoding="utf-8") as f:
        for line in f:
            t = json.loads(line)
            k5 = (t["ticker"], t["created_time"], t["yes_price_dollars"],
                  t.get("count_fp"), t.get("taker_side"))
            if k5 in seen:
                continue
            seen.add(k5)
            yield t


def evaluate(data: Data, mode: str):
    """mode: 'ha' (A_cap bound) or 'dprime' (realized arrivals). Outcome-blind:
    only bound arithmetic + prints; results joined later by pnl()."""
    fires = []
    taken = set()
    n = defaultdict(int)
    trades = sorted(iter_prints(), key=lambda t: t["created_time"])
    for t in trades:
        m = data.markets.get(t["ticker"])
        if m is None or m.get("strike_type") != "greater" or m.get("floor_strike") is None:
            continue
        ev = m["event_ticker"]
        if ev not in data.paths or not data.paths[ev]:
            n["no_vintage"] += 1
            continue
        p = float(t["yes_price_dollars"])
        t_dt = datetime.strptime(t["created_time"][:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=UTC)
        n["prints"] += 1
        st = data.state_at(ev, t_dt)
        if st is None:
            n["uneval"] += 1
            continue
        row_dt, s, cnt = st
        close = data.settle_dt(ev)
        d_days = max(1, math.ceil((close - row_dt).total_seconds() / 86400.0))
        if mode == "ha":
            ratios = prior_ratios(data, t_dt, d_days)
            if len(ratios) < MIN_PRIORS:
                n["few_priors"] += 1
                continue
            a = math.ceil(CAP_MULT * max(ratios) * cnt)
        else:
            fin = data.read_state(ev)
            if fin is None:
                n["no_read_row"] += 1
                continue
            a = max(0, fin[2] - cnt)
        k = float(m["floor_strike"])
        low, high, yes_dec, no_dec = bounds(s, cnt, a, k)
        side = None
        if yes_dec and p <= YES_MAX_P:
            side = "yes"
        elif no_dec and p >= NO_MIN_P:
            side = "no"
        if side is None:
            if yes_dec or no_dec:
                n["decided_unexecutable"] += 1
            continue
        dk = (t["ticker"], t_dt.astimezone(ET).date().isoformat())
        if dk in taken:
            continue
        taken.add(dk)
        fires.append({
            "ticker": t["ticker"], "event": ev, "cluster": data.slug[ev],
            "month": m["close_time"][:7], "p_print": p, "side": side,
            "matched": (t.get("taker_side") or "").lower() == side,
            "s": s, "n": cnt, "a": a, "k": k, "low": low, "high": high,
            "d_days": d_days, "row_age_h": (t_dt - row_dt).total_seconds() / 3600.0,
            "result": m["result"], "close": m["close_time"],
        })
        n["fired"] += 1
    return fires, dict(n)


def pnl(fires, data, haircut=HAIRCUT, matched_only=False):
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
        [r["pnl"] for r in rows], [r[key] for r in rows], n_resamples=10_000, rng_seed=28)
    return {"mean": mean, "lo": lo, "hi": hi, "n_fires": len(rows), "n_clusters": n_c}


def loco_ci(rows):
    by = defaultdict(float)
    for r in rows:
        by[r["cluster"]] += r["pnl"]
    if not by:
        return None, None
    best = max(by, key=by.get)
    return best, ci_of([r for r in rows if r["cluster"] != best])


def gates(rows, label):
    out = {"binding": ci_of(rows)}
    b = out["binding"]
    out["power_ok"] = bool(b and b["n_fires"] >= FLOOR_FIRES and b["n_clusters"] >= FLOOR_CLUSTERS)
    out["ci_ok"] = bool(out["power_ok"] and b["lo"] > 0)
    best, l = loco_ci(rows)
    out["loco_drop"], out["loco"] = best, l
    out["month_block"] = ci_of(rows, key="month")
    if not out["power_ok"]:
        v = "UNDERPOWERED-NULL" if rows else "NO-FIRES NULL"
    elif not out["ci_ok"]:
        v = "NULL"
    elif l and l["lo"] <= 0:
        v = "MARGINAL"
    elif out["month_block"] and out["month_block"]["lo"] <= 0:
        v = "FRAGILE-PASS"
    else:
        v = "PASS (FEASIBILITY-NOT-SAFETY; $0 live read first, always)"
    out["verdict"] = v
    print(f"{label}: {v} | {b}")
    return out


def audit(data: Data):
    print("=== 0-W withdrawal/monotonicity audit ===")
    n_pairs = n_dec = 0
    for ev, rows in data.paths.items():
        for i in range(1, len(rows)):
            n_pairs += 1
            if rows[i][2] < rows[i - 1][2] - W_DECREASE_REVIEWS:
                n_dec += 1
                print(f"  DECREASE {ev}: {rows[i-1][2]} -> {rows[i][2]} at {rows[i][0]:%Y-%m-%d}")
    rate = n_dec / max(n_pairs, 1)
    print(f"pairs={n_pairs} decreases>{W_DECREASE_REVIEWS}={n_dec} rate={rate:.3%} (kill line {W_RATE:.0%})")

    print("=== 0-S settlement-read audit (BOUND-COVERAGE form; booleans/diffs only) ===")
    # The read must lie inside [low - READ_MARGIN, high + READ_MARGIN] where the bound
    # is computed at the NEAREST PRE-CLOSE row with A = realized arrivals to the final
    # row (staleness is the bound's job via A; the margin covers read-vs-page
    # divergence only, e.g. the MOR case).
    n_cov = n_tot = 0
    worst = 0.0
    by_ev = defaultdict(list)
    for tk, m in data.markets.items():
        by_ev[m["event_ticker"]].append(m)
    for ev, ms in sorted(by_ev.items()):
        close = data.settle_dt(ev)
        st = data.state_at(ev, close)
        fin = data.read_state(ev)
        ev_val = None
        for m in ms:
            try:
                ev_val = float(m.get("expiration_value"))
                break
            except (TypeError, ValueError):
                continue
        if st is None or fin is None or ev_val is None:
            continue
        a = max(0, fin[2] - st[2])
        lo_l, hi_l = l_interval(st[1], st[2])
        low = 100.0 * lo_l / (st[2] + a)
        high = 100.0 * (hi_l + a) / (st[2] + a)
        n_tot += 1
        viol = max(low - READ_MARGIN - ev_val, ev_val - high - READ_MARGIN, 0.0)
        if viol == 0.0:
            n_cov += 1
        else:
            worst = max(worst, viol)
            print(f"  COVERAGE VIOLATION {ev}: read outside bound by {viol:.2f} pts")
    print(f"bound coverage: {n_cov}/{n_tot} at READ_MARGIN {READ_MARGIN}; worst excess {worst:.2f}")
    print("VERDICT: " + ("MARGIN OK" if n_cov == n_tot else f"RAISE MARGIN BY {worst:.2f}"))

    print("=== 0-B/0-E outcome-blind fire projection ===")
    for mode in ("ha", "dprime"):
        fires, funnel = evaluate(data, mode)
        cl = {f["cluster"] for f in fires}
        print(f"{mode}: fires={len(fires)} clusters={len(cl)} funnel={funnel}")
        ev_rate = 1.0 - funnel.get("uneval", 0) / max(funnel.get("prints", 1), 1)
        print(f"  evaluability={ev_rate:.1%} (0-E line 30%)  floors {FLOOR_FIRES}/{FLOOR_CLUSTERS}: "
              + ("REACHABLE" if len(fires) >= FLOOR_FIRES and len(cl) >= FLOOR_CLUSTERS else "NOT REACHED"))
    json.dump({"note": "0-B run; see stdout in session log"},
              open(os.path.join(V28, "audit_0b_done.json"), "w", encoding="utf-8"))


def full(data: Data):
    res = {}
    ha_fires, ha_funnel = evaluate(data, "ha")
    res["ha_funnel"] = ha_funnel
    rows = pnl(ha_fires, data)
    res["ha"] = gates(rows, "H-A")
    res["ha"]["reported_matched"] = ci_of(pnl(ha_fires, data, haircut=HAIRCUT_MATCHED, matched_only=True))
    json.dump(res, open(os.path.join(V28, "backtest_results_ha.json"), "w", encoding="utf-8"), indent=1, default=str)
    dp_fires, dp_funnel = evaluate(data, "dprime")
    res["dprime_funnel"] = dp_funnel
    drows = pnl(dp_fires, data)
    res["dprime"] = gates(drows, "D'")
    dp = res["dprime"]
    dp_pass = dp["verdict"].startswith("PASS")
    ha_v = res["ha"]["verdict"]
    if ha_v.startswith("PASS") or ha_v in ("MARGINAL", "FRAGILE-PASS"):
        route = "stage-1 $0 live read (H-A live), then shadow per v27 A3 protocol"
    elif dp_pass:
        route = "shadow testing H-A LIVE (D' bound passed; estimator-width diagnosis)"
    else:
        route = "FAMILY DEATH (H-A dead and the realized-arrival bound empty)"
    res["routing"] = route
    json.dump(res, open(os.path.join(V28, "backtest_results.json"), "w", encoding="utf-8"), indent=1, default=str)
    print("ROUTING:", route)


if __name__ == "__main__":
    d = Data()
    if "--audit" in sys.argv:
        audit(d)
    else:
        full(d)
