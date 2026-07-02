"""v27 verdict-critic diagnostics (04-verdict-critic.md evidence base).

POST-VERDICT INFERENCE AUDIT ONLY. These are not gate inputs and cannot rescue
the locked H1 NULL / D1 FAMILY-DEATH outcomes; they exist to adjudicate whether
the death is genuine or manufactured by implementation choices. Writes one JSON
to data/v27/verdict_critic_diag.json.

Computes, in ONE pass over the same funnel as tsa_backtest.evaluate:
  A. Reproduction check: joint-gated fire sets per mode must match shipped counts.
  B. Exact friction decomposition per mode (mean haircut+fee) -> frictionless means.
  C. Independent-gating counterfactual for D1 (mode fires when ITS OWN inputs are valid,
     regardless of other modes' E6/min-err validity) -> tests the joint-gating
     false-death vector. Cluster-bootstrap CI on the independent sets.
  D. Side/direction audit for H1 and control fires (trend-lag bias check).
  E. Signed walk-forward weekly error means per mode/bucket (baseline lag check).
  F. Disrupted-week (max_cancel>1000) split for D1 modes.
  G. H1 conditional-edge vs realized reconciliation on the shipped fire set.
"""
import json
import math
import os
import sys
from collections import defaultdict
from datetime import date, datetime

PROJ = r"C:\Users\SamJD\OneDrive\Desktop\AI Projects\Project Kalshi"
os.chdir(PROJ)
sys.path.insert(0, os.path.join(PROJ, "scripts", "v27"))
sys.path.insert(0, os.path.join(PROJ, "src"))
import tsa_backtest as tb  # noqa: E402
from kalshi_bot.analysis.bootstrap import cluster_bootstrap_mean_ci  # noqa: E402

UTC = tb.UTC
ET = tb.ET
THR = 0.08
MODES = ["h1", "control", "d1@0.3", "d1@0.5", "d1@1.0"]

data = tb.Data()
events = {m["event_ticker"]: m for m in data.markets.values()}
errors = tb.Errors(data, list(events.values()))

# ---- E. signed error means per mode/bucket (full history, descriptive) ----
err_stats = {}
agg = defaultdict(list)
for cd, md, bb, e in errors.rows:
    agg[(md, bb)].append(e)
for (md, bb), v in sorted(agg.items()):
    err_stats[f"{md}|{bb}"] = {
        "n": len(v),
        "mean": sum(v) / len(v),
        "min": min(v),
        "max": max(v),
    }

# ---- load trades identically ----
trades = []
seen = set()
with open(os.path.join("data", "v26", "trades.jsonl"), encoding="utf-8") as f:
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

joint_fires = {m: [] for m in MODES}
indep_fires = {m: [] for m in MODES}
taken_joint = {m: set() for m in MODES}
taken_indep = {m: set() for m in MODES}
# prints where a d1 mode was independently valid+would-fire but joint-invalid
lost_to_other_modes = {m: 0 for m in MODES}

for t in trades:
    m = data.markets.get(t["ticker"])
    if m is None or m.get("floor_strike") is None or m.get("strike_type") != "greater":
        continue
    p = float(t["yes_price_dollars"])
    if not (tb.BAND[0] <= p <= tb.BAND[1]):
        continue
    t_utc = datetime.strptime(t["created_time"][:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=UTC)
    t_et = t_utc.astimezone(ET)
    dk = (t["ticker"], t_et.date().isoformat())
    days = tb.week_days(m["close_time"])
    pub = [d for d in days if data.published_by_rule(d, t_et)]
    unpub = [d for d in days if not data.published_by_rule(d, t_et)]
    if any(data.val(d, t_utc) is None for d in pub):
        continue
    n_unpub = len(unpub)
    b = tb.bucket_of(n_unpub)
    if b is None or n_unpub == 0:
        continue
    close_d = date.fromisoformat(m["close_time"][:10])
    tot = sum(data.val(d, t_utc) for d in pub)
    k = tb.norm_strike(float(m["floor_strike"]))
    probs = {}
    valid = {}
    for mode in MODES:
        beta = float(mode.split("@")[1]) if mode.startswith("d1@") else 1.0
        core = "d1" if mode.startswith("d1@") else mode
        errs = errors.dist(mode, b, close_d)
        if len(errs) < tb.MIN_ERRS:
            valid[mode] = False
            continue
        preds = [data.pred_day(d, t_utc, core, beta) for d in unpub]
        if any(v is None for v in preds):
            valid[mode] = False
            continue
        avg_hat = (tot + sum(preds)) / 7.0 / 1e6
        pv = tb.p_above(avg_hat, k, errs)
        if pv is None:
            valid[mode] = False
            continue
        valid[mode] = True
        probs[mode] = pv
    all_valid = all(valid[mode] for mode in MODES)
    maxc = max((data.bts.get(d, {"cancelled": 0})["cancelled"] for d in days), default=0)
    for mode in MODES:
        if not valid[mode]:
            continue
        div = probs[mode] - p
        if abs(div) < THR:
            continue
        side = "yes" if div > 0 else "no"
        rec = {
            "cluster": m["event_ticker"], "month": m["close_time"][:7],
            "p_print": p, "side": side, "div": div, "result": m["result"],
            "max_cancel": maxc, "n_unpub": n_unpub, "p_model": probs[mode],
        }
        if all_valid and dk not in taken_joint[mode]:
            joint_fires[mode].append(rec)
            taken_joint[mode].add(dk)
        if dk not in taken_indep[mode]:
            indep_fires[mode].append(rec)
            taken_indep[mode].add(dk)
            if not all_valid:
                lost_to_other_modes[mode] += 1


def pnl_rows(fires, haircut):
    rows = []
    for f in fires:
        cost = (f["p_print"] if f["side"] == "yes" else 1 - f["p_print"]) + haircut
        fee = tb.taker_fee(cost) if haircut > 0 else 0.0
        win = 1.0 if f["result"] == f["side"] else 0.0
        rows.append({**f, "pnl": win - cost - fee, "fric": haircut + fee})
    return rows


def summarize(fires, label, ci=False):
    out = {"label": label, "n": len(fires), "n_clusters": len({f["cluster"] for f in fires})}
    if not fires:
        return out
    rows = pnl_rows(fires, tb.HAIRCUT)
    rows0 = pnl_rows(fires, 0.0)
    out["mean_net"] = sum(r["pnl"] for r in rows) / len(rows)
    out["mean_frictionless"] = sum(r["pnl"] for r in rows0) / len(rows0)
    out["mean_friction"] = sum(r["fric"] for r in rows) / len(rows)
    ny = sum(1 for f in fires if f["side"] == "yes")
    out["n_yes"] = ny
    out["n_no"] = len(fires) - ny
    yes_rows = [r for r in rows if r["side"] == "yes"]
    no_rows = [r for r in rows if r["side"] == "no"]
    if yes_rows:
        out["mean_net_yes"] = sum(r["pnl"] for r in yes_rows) / len(yes_rows)
    if no_rows:
        out["mean_net_no"] = sum(r["pnl"] for r in no_rows) / len(no_rows)
    dis = [r for r in rows if r["max_cancel"] > 1000]
    out["n_disrupted"] = len(dis)
    if dis:
        out["mean_net_disrupted"] = sum(r["pnl"] for r in dis) / len(dis)
        out["disrupted_clusters"] = len({r["cluster"] for r in dis})
    if ci:
        mean, lo, hi, n_c = cluster_bootstrap_mean_ci(
            [r["pnl"] for r in rows], [r["cluster"] for r in rows],
            n_resamples=10_000, rng_seed=27)
        out["ci_net"] = [lo, hi]
        mean0, lo0, hi0, _ = cluster_bootstrap_mean_ci(
            [r["pnl"] for r in rows0], [r["cluster"] for r in rows0],
            n_resamples=10_000, rng_seed=27)
        out["mean_frictionless_ci"] = [lo0, hi0]
    return out


result = {"reproduction": {m: len(joint_fires[m]) for m in MODES},
          "lost_to_other_modes_indep": lost_to_other_modes,
          "err_stats": err_stats}

for mode in MODES:
    result[f"joint_{mode}"] = summarize(joint_fires[mode], f"joint {mode}", ci=mode.startswith("d1") or mode == "h1")
    result[f"indep_{mode}"] = summarize(indep_fires[mode], f"indep {mode}", ci=mode.startswith("d1"))

# G. conditional edge vs realized on shipped H1 fire set
h1 = joint_fires["h1"]
edges = []
for f in h1:
    cost = (f["p_print"] if f["side"] == "yes" else 1 - f["p_print"]) + tb.HAIRCUT
    p_true = f["p_model"] if f["side"] == "yes" else 1 - f["p_model"]
    edges.append(p_true - cost - tb.taker_fee(cost))
result["h1_cond_edge_mean"] = sum(edges) / len(edges)

out_path = os.path.join("data", "v27", "verdict_critic_diag.json")
json.dump(result, open(out_path, "w", encoding="utf-8"), indent=1, default=str)
print(json.dumps(result["reproduction"], indent=1))
print("lost_to_other_modes:", lost_to_other_modes)
print("written:", out_path)
