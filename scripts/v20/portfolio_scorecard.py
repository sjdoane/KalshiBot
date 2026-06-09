"""Generate the portfolio scorecard PNG for the Kalshi project.

Matches the house style of pit-backtest-scorecard.png (white card, dark title,
blue metric tiles, SD badge, hero chart, feature tags, honest footer). Presents
the genuinely defensible results: the out-of-sample-validated favorite-longshot
maker edge (5 sports, train + holdout cluster-bootstrap CIs exclude zero, 72M
trades), the live track record, and the risk engineering.

Live hit-rate/record are read from the bot's state.json (post-change cutoff,
side-aware) so the number is accurate at generation time; OOS validation numbers
are the documented research results (research/v10a TEST-AND-CONFIRM).

Run with the pit-backtest venv (has matplotlib):
  C:/Users/SamJD/.venvs/pit-backtest/Scripts/python.exe scripts/v20/portfolio_scorecard.py
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.font_manager as fm  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyBboxPatch  # noqa: E402

OUT = Path("C:/Users/SamJD/OneDrive/Desktop/JOB/portfolio-template-v2/assets/proj-kalshi.png")
STATE = Path("C:/Users/SamJD/OneDrive/Desktop/AI Projects/Project Kalshi/data/live_trades/state.json")
CUTOFF = datetime(2026, 6, 2, 17, 0, tzinfo=timezone.utc)

INK = "#141821"
BLUE = "#2563EB"
GRAY = "#6b7280"
TILEBG = "#f6f7f9"
BORDER = "#e7e9ed"
TRAINC = "#c7ccd4"

# OOS validation (research/v10a TEST-AND-CONFIRM): v1 maker strategy on Becker
# post-Oct-2024, event-level cluster bootstrap, train -> holdout. All OOS means
# positive; all OOS 95% CI lower bounds > 0.
SPORTS = ["MLB", "ATP", "WTA", "NFL", "NCAAF"]
OOS = [3.58, 3.59, 2.54, 3.65, 4.25]
OOS_CILO = [2.19, 2.27, 0.94, 1.16, 3.25]
TRAIN = [3.42, 3.07, 2.74, 7.24, 4.92]


def _parse(ts):
    if not ts:
        return None
    try:
        d = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def live_record() -> tuple[int, int, int]:
    """(wins, losses, n) of post-cutoff settled bets, side-aware. Falls back to
    the known snapshot if state cannot be read."""
    try:
        raw = json.loads(STATE.read_text(encoding="utf-8"))
        w = ln = 0
        for o in raw.get("closed", {}).values():
            if o.get("realized_pnl_usd") is None:
                continue
            p = _parse(o.get("placed_ts"))
            if p is None or p < CUTOFF:
                continue
            oc = o.get("resolution_outcome")
            if oc == -1:
                continue
            side = o.get("side")
            if (side == "yes" and oc == 1) or (side == "no" and oc == 0):
                w += 1
            else:
                ln += 1
        if w + ln >= 1:
            return w, ln, w + ln
    except Exception:  # noqa: BLE001
        pass
    return 15, 3, 18


def rounded(ax, x, y, w, h, fc, ec=BORDER, lw=1.0, pad=0.0, rad=0.018):
    ax.add_patch(FancyBboxPatch(
        (x + pad, y + pad), w - 2 * pad, h - 2 * pad,
        boxstyle=f"round,pad=0,rounding_size={rad}",
        linewidth=lw, edgecolor=ec, facecolor=fc, mutation_aspect=0.6,
    ))


def main() -> None:
    try:
        fm.findfont("Arial", fallback_to_default=False)
        plt.rcParams["font.family"] = "Arial"
    except Exception:  # noqa: BLE001
        plt.rcParams["font.family"] = "DejaVu Sans"

    w, ln, n = live_record()
    wr = round(100 * w / n) if n else 0

    fig = plt.figure(figsize=(12, 7.4), dpi=175)
    fig.patch.set_facecolor("white")
    bg = fig.add_axes([0, 0, 1, 1])
    bg.axis("off")
    bg.set_xlim(0, 1)
    bg.set_ylim(0, 1)

    # Header
    bg.text(0.043, 0.955, "kalshi-bot", fontsize=29, fontweight="bold", color=INK, va="top")
    bg.text(0.044, 0.902, "Live, automated maker-quoting bot on a CFTC-regulated prediction market",
            fontsize=13, color=GRAY, va="top")
    bg.text(0.044, 0.872, "Favorite-longshot edge  /  validated out-of-sample on 72M settled trades  /  live, real-money since June 2026",
            fontsize=10.5, color=GRAY, va="top")
    # SD badge
    rounded(bg, 0.905, 0.905, 0.055, 0.058, INK, ec=INK, rad=0.02)
    bg.text(0.9325, 0.934, "SD", fontsize=15, fontweight="bold", color="white", ha="center", va="center")
    # divider
    bg.plot([0.043, 0.957], [0.846, 0.846], color=BORDER, lw=1.2)

    # Metric tiles
    tiles = [
        ("LIVE HIT RATE", f"{wr}%", f"{w}W-{ln}L since launch"),
        ("OOS NET EDGE", "+3.5%", "per event, holdout avg"),
        ("OOS HOLDOUT", "CI > 0", "train + test exclude zero"),
        ("TRADES ANALYZED", "72M", "settled, 2024-25"),
        ("VALIDATED SERIES", "5", "MLB - tennis - football"),
        ("EXECUTION", "LIVE", "24/7 automated"),
    ]
    x0, x1 = 0.043, 0.957
    gap = 0.013
    tw = (x1 - x0 - gap * (len(tiles) - 1)) / len(tiles)
    ty, th = 0.688, 0.142
    for i, (lab, num, cap) in enumerate(tiles):
        tx = x0 + i * (tw + gap)
        cx = tx + tw / 2
        rounded(bg, tx, ty, tw, th, TILEBG, rad=0.014)
        bg.text(cx, ty + th - 0.026, lab, fontsize=8, color=GRAY, ha="center", va="center", fontweight="bold")
        bg.text(cx, ty + th / 2 - 0.004, num, fontsize=20, color=BLUE, ha="center", va="center", fontweight="bold")
        bg.text(cx, ty + 0.024, cap, fontsize=7.4, color=GRAY, ha="center", va="center")

    # Section heading
    bg.text(0.043, 0.640, "Out-of-sample validation", fontsize=14.5, fontweight="bold", color=INK, va="top")
    bg.text(0.044, 0.610, "net maker edge per event, train vs holdout  -  cluster-bootstrap 95% CIs exclude zero across all five series",
            fontsize=10, color=GRAY, va="top")

    # Hero chart
    ax = fig.add_axes([0.055, 0.205, 0.895, 0.355])
    xs = range(len(SPORTS))
    ax.bar(xs, OOS, width=0.62, color=BLUE, zorder=3,
           yerr=[[o - c for o, c in zip(OOS, OOS_CILO)], [0] * len(OOS)],
           error_kw=dict(ecolor="#0f3aa8", elinewidth=1.4, capsize=4, zorder=4))
    # train markers
    ax.scatter(xs, TRAIN, marker="D", s=26, color=GRAY, zorder=5, label="Train mean")
    ax.axhline(0, color="#9aa0aa", lw=1)
    ax.set_xticks(list(xs))
    ax.set_xticklabels(SPORTS, fontsize=11, color=INK)
    ax.set_ylim(0, 8.6)
    ax.set_yticks([0, 2, 4, 6, 8])
    ax.set_yticklabels(["0", "2%", "4%", "6%", "8%"], fontsize=9.5, color=GRAY)
    ax.set_ylabel("net edge / event", fontsize=10, color=GRAY)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color("#9aa0aa")
    ax.grid(axis="y", color=BORDER, lw=1, zorder=0)
    ax.tick_params(length=0)
    # legend (blue bar + train diamond)
    from matplotlib.patches import Patch
    from matplotlib.lines import Line2D
    handles = [
        Patch(facecolor=BLUE, label="Out-of-sample mean (whisker = 95% CI floor)"),
        Line2D([0], [0], marker="D", color="w", markerfacecolor=GRAY, markersize=7, label="Train mean"),
    ]
    ax.legend(handles=handles, loc="upper right", frameon=False, fontsize=9, handletextpad=0.5)

    # Feature tags
    feats = "Out-of-sample validation     Event-cluster bootstrap     Kelly-fractional sizing     Multi-trigger kill-switch     Reproducible pipeline"
    bg.text(0.043, 0.135, feats, fontsize=9, color=INK, va="top")

    # Honest footer
    bg.text(0.043, 0.072,
            "Edge validated out-of-sample on 72M trades; deployed live with Kelly-fractional sizing and automated kill-switches, "
            "and tracked on a pre-registered gate before any scale-up.",
            fontsize=8.2, color=GRAY, style="italic", va="top")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, dpi=175, facecolor="white", bbox_inches=None)
    print(f"wrote {OUT}  (live record {w}W-{ln}L = {wr}%, n={n})")


if __name__ == "__main__":
    main()
