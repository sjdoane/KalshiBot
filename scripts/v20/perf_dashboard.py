"""v1 performance logger + self-contained HTML dashboard (research/v20).

READ-ONLY. Reads data/live_trades/state.json and writes two artifacts under
data/live_trades/ (both gitignored, regeneratable):
  - perf_log.csv         one row per POST-CHANGE settled bet (the audit log)
  - perf_dashboard.html  a single offline self-contained dashboard (no server,
                         no CDN, no matplotlib; inline SVG charts)

"Post-change" = bets PLACED at/after the cutoff (state.tally_since_ts if set,
else DEFAULT_CUTOFF), so old broad-universe bets and still-open positions placed
before the cutoff are excluded. W/L is SIDE-AWARE (a NO bet resolving NO is a
win), matching the live tally + the kill trigger. The bootstrap CI on mean
per-bet P&L is the "is the edge real yet" signal: it is only meaningful once it
excludes zero, which needs a much larger sample than a handful of bets.

Run (Windows):
  .venv-kronos/Scripts/python.exe -m scripts.v20.perf_dashboard
"""

from __future__ import annotations

import csv
import html
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

STATE = Path("data/live_trades/state.json")
CSV_OUT = Path("data/live_trades/perf_log.csv")
HTML_OUT = Path("data/live_trades/perf_dashboard.html")
DEFAULT_CUTOFF = "2026-06-02T17:00:00+00:00"  # when the validated-edge config went live
REPORTABLE_N = 30  # below this, the dashboard shows a "too small to report" banner

# Clean accent palette (skill-derived).
POS = "#2e9e5b"
NEG = "#c4453a"
INK = "#1f2430"
MUTED = "#6c7280"
GRID = "#e6e8ec"


def parse_iso(ts: object) -> datetime | None:
    if not ts:
        return None
    try:
        d = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    return d if d.tzinfo is not None else d.replace(tzinfo=timezone.utc)


def prefix_of(ticker: str) -> str:
    return ticker.split("-", 1)[0] if ticker else "?"


def won(side: str, outcome: int | None) -> bool:
    return (side == "yes" and outcome == 1) or (side == "no" and outcome == 0)


def wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    phat = k / n
    denom = 1 + z * z / n
    center = (phat + z * z / (2 * n)) / denom
    half = z * math.sqrt(phat * (1 - phat) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, center - half), min(1.0, center + half))


def bootstrap_mean_ci(pnls: list[float], n_boot: int = 10000) -> tuple[float, float, float]:
    """Return (mean, ci_lo, ci_hi) of the mean per-bet P&L via iid percentile
    bootstrap. iid (not event-clustered) is a simplification: bets on the same
    game-day are roughly independent across games, but treat the CI as
    indicative, not a formal verdict."""
    arr = np.asarray(pnls, dtype=float)
    if arr.size < 2:
        m = float(arr.mean()) if arr.size else 0.0
        return (m, m, m)
    rng = np.random.default_rng(12345)
    samples = rng.choice(arr, size=(n_boot, arr.size), replace=True).mean(axis=1)
    return float(arr.mean()), float(np.percentile(samples, 2.5)), float(np.percentile(samples, 97.5))


def money(x: float) -> str:
    return f"{'+' if x >= 0 else '-'}${abs(x):.2f}"


# ---------- inline SVG charts (offline, no deps) ----------

def svg_equity_curve(cum: list[float], width: int = 720, height: int = 300) -> str:
    """cum = cumulative P&L after each settled bet (chronological)."""
    pad_l, pad_r, pad_t, pad_b = 54, 18, 18, 28
    if not cum:
        return '<div class="empty">no settled bets yet</div>'
    series = [0.0] + cum  # start at zero
    n = len(series)
    lo = min(0.0, min(series))
    hi = max(0.0, max(series))
    if hi == lo:
        hi = lo + 1.0
    span = hi - lo
    pw = width - pad_l - pad_r
    ph = height - pad_t - pad_b

    def x(i: int) -> float:
        return pad_l + (pw * i / (n - 1) if n > 1 else 0)

    def y(v: float) -> float:
        return pad_t + ph * (1 - (v - lo) / span)

    pts = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(series))
    zero_y = y(0.0)
    end_color = POS if series[-1] >= 0 else NEG
    # y-axis labels at hi, 0, lo
    labels = []
    for v in sorted({hi, 0.0, lo}, reverse=True):
        labels.append(
            f'<text x="{pad_l - 8}" y="{y(v) + 4:.1f}" text-anchor="end" '
            f'class="axis">{money(v)}</text>'
            f'<line x1="{pad_l}" y1="{y(v):.1f}" x2="{width - pad_r}" y2="{y(v):.1f}" '
            f'class="grid"/>'
        )
    return (
        f'<svg viewBox="0 0 {width} {height}" class="chart" role="img">'
        f'{"".join(labels)}'
        f'<line x1="{pad_l}" y1="{zero_y:.1f}" x2="{width - pad_r}" y2="{zero_y:.1f}" class="zero"/>'
        f'<polyline points="{pts}" fill="none" stroke="{end_color}" stroke-width="2.5"/>'
        f'<circle cx="{x(n - 1):.1f}" cy="{y(series[-1]):.1f}" r="4" fill="{end_color}"/>'
        f'<text x="{pad_l}" y="{height - 8}" class="axis">bet 1</text>'
        f'<text x="{width - pad_r}" y="{height - 8}" text-anchor="end" class="axis">bet {n - 1}</text>'
        f'</svg>'
    )


def svg_prefix_bars(rows: list[tuple[str, float]], width: int = 720) -> str:
    """rows = [(label, net_pnl), ...]."""
    if not rows:
        return '<div class="empty">no settled bets yet</div>'
    bar_h, gap, pad_l, pad_r, pad_t = 26, 14, 110, 60, 10
    height = pad_t + len(rows) * (bar_h + gap)
    vmax = max((abs(v) for _, v in rows), default=1.0) or 1.0
    pw = width - pad_l - pad_r
    mid = pad_l + pw / 2
    out = [f'<svg viewBox="0 0 {width} {height}" class="chart" role="img">']
    out.append(f'<line x1="{mid}" y1="{pad_t}" x2="{mid}" y2="{height}" class="zero"/>')
    for i, (label, v) in enumerate(rows):
        cy = pad_t + i * (bar_h + gap)
        w = (abs(v) / vmax) * (pw / 2)
        color = POS if v >= 0 else NEG
        bx = mid if v >= 0 else mid - w
        out.append(
            f'<text x="{pad_l - 10}" y="{cy + bar_h / 2 + 4:.1f}" text-anchor="end" '
            f'class="axis lbl">{html.escape(label)}</text>'
            f'<rect x="{bx:.1f}" y="{cy:.1f}" width="{w:.1f}" height="{bar_h}" '
            f'rx="3" fill="{color}"/>'
            f'<text x="{(mid + w + 6) if v >= 0 else (mid - w - 6):.1f}" '
            f'y="{cy + bar_h / 2 + 4:.1f}" text-anchor="{"start" if v >= 0 else "end"}" '
            f'class="axis val">{money(v)}</text>'
        )
    out.append("</svg>")
    return "".join(out)


def main() -> int:
    if not STATE.exists():
        print(f"No state at {STATE}")
        return 1
    raw = json.loads(STATE.read_text(encoding="utf-8"))
    cutoff_iso = raw.get("tally_since_ts") or DEFAULT_CUTOFF
    cutoff = parse_iso(cutoff_iso)
    closed = raw.get("closed", {})
    filled = raw.get("filled", {})

    # Post-cutoff settled bets, chronological by settle time.
    settled = []
    for o in closed.values():
        if o.get("realized_pnl_usd") is None:
            continue
        placed = parse_iso(o.get("placed_ts"))
        if placed is None or (cutoff is not None and placed < cutoff):
            continue
        settle = parse_iso(o.get("resolution_ts")) or parse_iso(o.get("filled_ts")) or placed
        settled.append({
            "placed": placed, "settle": settle, "ticker": o.get("ticker", ""),
            "prefix": prefix_of(o.get("ticker", "")), "side": o.get("side", ""),
            "outcome": o.get("resolution_outcome"),
            "contracts": o.get("filled_count") or o.get("contracts") or 0,
            "entry_cents": o.get("filled_price_cents") or o.get("target_price_cents") or 0,
            "pnl": float(o["realized_pnl_usd"]),
        })
    settled.sort(key=lambda r: r["settle"] or r["placed"])

    # Open (unsettled) post-cutoff positions.
    open_pos = []
    for o in filled.values():
        placed = parse_iso(o.get("placed_ts"))
        if placed is None or (cutoff is not None and placed < cutoff):
            continue
        cents = o.get("filled_price_cents") or o.get("target_price_cents") or 0
        cnt = o.get("filled_count") or o.get("contracts") or 0
        open_pos.append({
            "ticker": o.get("ticker", ""), "side": o.get("side", ""),
            "contracts": cnt, "entry_cents": cents, "cost": cents / 100.0 * cnt,
        })

    # Metrics.
    pnls = [r["pnl"] for r in settled]
    net = sum(pnls)
    n = len(settled)
    wins = sum(1 for r in settled if r["outcome"] != -1 and won(r["side"], r["outcome"]))
    voids = sum(1 for r in settled if r["outcome"] == -1)
    losses = n - wins - voids
    decided = wins + losses
    win_rate = wins / decided if decided else 0.0
    wlo, whi = wilson_ci(wins, decided)
    win_pnls = [p for p in pnls if p > 0]
    loss_pnls = [p for p in pnls if p < 0]
    avg_win = sum(win_pnls) / len(win_pnls) if win_pnls else 0.0
    avg_loss = sum(loss_pnls) / len(loss_pnls) if loss_pnls else 0.0
    profit_factor = (sum(win_pnls) / abs(sum(loss_pnls))) if loss_pnls else float("inf")
    mean_pb, ci_lo, ci_hi = bootstrap_mean_ci(pnls)
    edge_real = n >= 2 and ci_lo > 0

    # Per-prefix.
    by_prefix: dict[str, dict] = {}
    for r in settled:
        d = by_prefix.setdefault(r["prefix"], {"n": 0, "w": 0, "l": 0, "v": 0, "net": 0.0})
        d["n"] += 1
        d["net"] += r["pnl"]
        if r["outcome"] == -1:
            d["v"] += 1
        elif won(r["side"], r["outcome"]):
            d["w"] += 1
        else:
            d["l"] += 1
    prefix_rows = sorted(by_prefix.items(), key=lambda kv: -kv[1]["net"])

    # All-time contrast.
    all_settled = [o for o in closed.values() if o.get("realized_pnl_usd") is not None]
    all_net = sum(float(o["realized_pnl_usd"]) for o in all_settled)

    cum, run = [], 0.0
    for r in settled:
        run += r["pnl"]
        cum.append(run)
    open_cost = sum(p["cost"] for p in open_pos)

    # ----- CSV -----
    CSV_OUT.parent.mkdir(parents=True, exist_ok=True)
    res_label = {1: "YES", 0: "NO", -1: "VOID"}
    with CSV_OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["settle_ts", "placed_ts", "ticker", "prefix", "side",
                    "market_outcome", "result", "contracts", "entry_cents",
                    "realized_pnl_usd", "cumulative_pnl_usd"])
        c = 0.0
        for r in settled:
            c += r["pnl"]
            result = "VOID" if r["outcome"] == -1 else ("WIN" if won(r["side"], r["outcome"]) else "LOSS")
            w.writerow([
                (r["settle"].isoformat() if r["settle"] else ""),
                (r["placed"].isoformat() if r["placed"] else ""),
                r["ticker"], r["prefix"], r["side"], res_label.get(r["outcome"], "?"),
                result, r["contracts"], r["entry_cents"], f"{r['pnl']:.2f}", f"{c:.2f}",
            ])

    # ----- HTML -----
    now = datetime.now(timezone.utc)
    pf_str = "inf" if profit_factor == float("inf") else f"{profit_factor:.2f}"
    edge_txt = ("YES, CI excludes 0" if edge_real
                else f"not yet (need n &gt;= ~{REPORTABLE_N}+)")
    edge_color = POS if edge_real else MUTED
    net_color = POS if net >= 0 else NEG

    cards = [
        ("Net realized P&amp;L (post-change)", money(net), net_color,
         f"all-time incl. old bets: {money(all_net)} ({len(all_settled)})"),
        ("Settled bets", str(n), INK, f"open (unrealized): {len(open_pos)}"),
        ("Record (side-aware)", f"{wins}W / {losses}L" + (f" / {voids}V" if voids else ""),
         INK, f"win rate {win_rate*100:.0f}% (95% CI {wlo*100:.0f}-{whi*100:.0f}%)"),
        ("Edge real yet?", edge_txt, edge_color,
         f"mean/bet {money(mean_pb)} (CI {money(ci_lo)} to {money(ci_hi)})"),
        ("Avg win / avg loss", f"{money(avg_win)} / {money(avg_loss)}", INK,
         f"profit factor {pf_str}"),
        ("Open exposure", money(open_cost), INK, f"{len(open_pos)} positions at risk"),
    ]
    card_html = "".join(
        f'<div class="card"><div class="card-label">{lab}</div>'
        f'<div class="card-value" style="color:{col}">{val}</div>'
        f'<div class="card-sub">{sub}</div></div>'
        for lab, val, col, sub in cards
    )

    prefix_table = "".join(
        f'<tr><td>{html.escape(k)}</td><td>{d["n"]}</td>'
        f'<td>{d["w"]}/{d["l"]}{("/" + str(d["v"])) if d["v"] else ""}</td>'
        f'<td>{(d["w"]/(d["w"]+d["l"])*100) if (d["w"]+d["l"]) else 0:.0f}%</td>'
        f'<td style="color:{POS if d["net"]>=0 else NEG}">{money(d["net"])}</td></tr>'
        for k, d in prefix_rows
    ) or '<tr><td colspan="5" class="empty">none</td></tr>'

    bet_rows = "".join(
        f'<tr><td>{(r["settle"].strftime("%m-%d %H:%M") if r["settle"] else "")}</td>'
        f'<td class="mono">{html.escape(r["ticker"])}</td>'
        f'<td>{r["side"].upper()}</td>'
        f'<td>{"VOID" if r["outcome"]==-1 else ("WIN" if won(r["side"], r["outcome"]) else "LOSS")}</td>'
        f'<td>{r["contracts"]}</td><td>{r["entry_cents"]}c</td>'
        f'<td style="color:{POS if r["pnl"]>=0 else NEG}">{money(r["pnl"])}</td></tr>'
        for r in reversed(settled)
    ) or '<tr><td colspan="7" class="empty">no settled bets yet</td></tr>'

    banner = ""
    if n < REPORTABLE_N:
        banner = (
            f'<div class="banner">SAMPLE TOO SMALL TO REPORT: n={n} settled. '
            f'A {money(net)} result on {n} bets is within noise; the edge is not '
            f'confirmed until the bootstrap CI on mean per-bet P&amp;L excludes zero '
            f'(needs ~{REPORTABLE_N}+ bets). Keep collecting before reporting.</div>'
        )

    doc = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Kalshi v1 Performance</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
background:#f4f5f7;color:{INK};line-height:1.5;padding:20px}}
.wrap{{max-width:1100px;margin:0 auto}}
header{{background:{INK};color:#fff;padding:18px 22px;border-radius:10px;margin-bottom:16px}}
header h1{{font-size:19px;font-weight:650}}
header .meta{{font-size:12px;color:#aeb4c0;margin-top:3px}}
.banner{{background:#fff4e5;border:1px solid #f0c27a;color:#7a4a00;padding:12px 16px;
border-radius:8px;margin-bottom:16px;font-size:13px}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px;margin-bottom:16px}}
.card{{background:#fff;border-radius:10px;padding:16px 18px;box-shadow:0 1px 3px rgba(0,0,0,.07)}}
.card-label{{font-size:12px;color:{MUTED};text-transform:uppercase;letter-spacing:.4px}}
.card-value{{font-size:26px;font-weight:700;margin:5px 0 3px}}
.card-sub{{font-size:12px;color:{MUTED}}}
.row{{display:grid;grid-template-columns:1.6fr 1fr;gap:16px;margin-bottom:16px}}
@media(max-width:820px){{.row{{grid-template-columns:1fr}}}}
.panel{{background:#fff;border-radius:10px;padding:16px 18px;box-shadow:0 1px 3px rgba(0,0,0,.07)}}
.panel h3{{font-size:13px;font-weight:650;margin-bottom:12px;color:{INK}}}
.chart{{width:100%;height:auto}}
.axis{{font-size:11px;fill:{MUTED}}}
.lbl{{font-weight:600;fill:{INK}}}
.grid{{stroke:{GRID};stroke-width:1}}
.zero{{stroke:#b8bdc7;stroke-width:1;stroke-dasharray:3 3}}
.empty{{color:{MUTED};font-size:13px;padding:20px 0;text-align:center}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
th{{text-align:left;padding:8px 10px;border-bottom:2px solid #e2e5ea;color:{MUTED};
font-size:11px;text-transform:uppercase;letter-spacing:.4px}}
td{{padding:7px 10px;border-bottom:1px solid #f0f1f3}}
.mono{{font-family:ui-monospace,Consolas,monospace;font-size:12px}}
.scroll{{max-height:360px;overflow-y:auto}}
footer{{font-size:11px;color:{MUTED};margin-top:8px;padding:0 4px}}
</style></head>
<body><div class="wrap">
<header><h1>Kalshi v1 Performance (post-change)</h1>
<div class="meta">since {html.escape(cutoff_iso)} &nbsp;|&nbsp; generated {now.strftime('%Y-%m-%d %H:%M')} UTC
&nbsp;|&nbsp; read-only from state.json &nbsp;|&nbsp; side-aware W/L</div></header>
{banner}
<div class="cards">{card_html}</div>
<div class="row">
<div class="panel"><h3>Cumulative realized P&amp;L</h3>{svg_equity_curve(cum)}</div>
<div class="panel"><h3>Net P&amp;L by series</h3>{svg_prefix_bars([(k, d["net"]) for k, d in prefix_rows])}</div>
</div>
<div class="row">
<div class="panel"><h3>By series</h3>
<table><thead><tr><th>Series</th><th>N</th><th>W/L</th><th>Win%</th><th>Net</th></tr></thead>
<tbody>{prefix_table}</tbody></table></div>
<div class="panel"><h3>Open positions ({len(open_pos)})</h3>
<table><thead><tr><th>Ticker</th><th>Side</th><th>Ct</th><th>Entry</th></tr></thead><tbody>{
        "".join(f'<tr><td class="mono">{html.escape(p["ticker"])}</td><td>{p["side"].upper()}</td>'
                f'<td>{p["contracts"]}</td><td>{p["entry_cents"]}c</td></tr>' for p in open_pos)
        or '<tr><td colspan="4" class="empty">none</td></tr>'
}</tbody></table></div>
</div>
<div class="panel"><h3>Settled bets ({n})</h3><div class="scroll">
<table><thead><tr><th>Settled</th><th>Ticker</th><th>Side</th><th>Result</th>
<th>Ct</th><th>Entry</th><th>P&amp;L</th></tr></thead><tbody>{bet_rows}</tbody></table></div></div>
<footer>Win/loss is side-aware (a NO bet resolving NO is a win). CI is an iid
percentile bootstrap on mean per-bet P&amp;L (indicative, not event-clustered).
P&amp;L is realized only; open positions are excluded until they settle. Old
pre-cutoff bets are excluded. Regenerate: .venv-kronos/Scripts/python.exe -m
scripts.v20.perf_dashboard</footer>
</div></body></html>"""

    HTML_OUT.write_text(doc, encoding="utf-8")
    print(f"settled(post-change)={n}  net={money(net)}  record={wins}W/{losses}L"
          + (f"/{voids}V" if voids else "")
          + f"  mean/bet={money(mean_pb)} CI[{money(ci_lo)},{money(ci_hi)}]"
          + f"  edge_real={edge_real}")
    print(f"wrote {CSV_OUT}")
    print(f"wrote {HTML_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
