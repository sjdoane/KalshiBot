"""Phase 2 step 4: run the Politics x H gate, write phase-2-results.md.

Reads data/processed/politics_phase2_dataset.parquet, evaluates per the
locked methodology in [phase-2-methodology.md](research/phase-2-methodology.md),
and writes research/phase-2-results.md with the per-split tables and the
PASS / KILL verdict.

Per the no-third-bite rule: if any locked criterion fails, the report
records FAIL and the project ends (no parameter tuning).
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import structlog

from kalshi_bot.analysis.gate_phase2 import (
    PASS_C1A_MEDIAN_SLOPE,
    PASS_C1B_Q25_SLOPE,
    PASS_C2_GROSS_EDGE,
    PASS_C3_MIN_SPLITS_NET_POSITIVE,
    PASS_C4_MIN_EVENT_WINDOWS_POSITIVE,
    Phase2GateResult,
    evaluate,
)
from kalshi_bot.logging import configure_logging

DATASET_PATH = Path("data/processed/politics_phase2_dataset.parquet")
REPORT_PATH = Path("research/phase-2-results.md")


def _fmt_pct(x: float) -> str:
    if np.isnan(x):
        return "n/a"
    return f"{x*100:.2f}pp"


def _fmt(x: float, places: int = 4) -> str:
    if np.isnan(x):
        return "n/a"
    return f"{x:.{places}f}"


def render_report(result: Phase2GateResult, dataset_meta: dict) -> str:
    lines: list[str] = []
    lines.append("# Phase 2 Results: Politics x H Maker-Quote OOS Gate\n")
    lines.append(f"**Date generated:** {pd.Timestamp.now(tz='UTC').isoformat()}")
    lines.append("**Methodology:** [phase-2-methodology.md](phase-2-methodology.md)")
    lines.append("**Proposal:** [phase-2-proposal.md](phase-2-proposal.md)")
    lines.append("**Critic reports:** [plan](critic-plan-phase-2.md), [methodology](critic-methodology-phase-2.md)")
    lines.append("**Window:** small-trade VWAP in [resolution - 35d, resolution - 28d]")
    lines.append("**Verdict:** " + ("**GATE PASSES**" if result.passes else "**GATE FAILS**"))
    lines.append("")

    lines.append("## Pass criteria")
    lines.append("")
    lines.append("| Criterion | Required | Observed | Result |")
    lines.append("|---|---|---|---|")
    lines.append(
        f"| C1a median per-partition slope (small-trade) | >= {PASS_C1A_MEDIAN_SLOPE} | "
        f"{_fmt(result.median_slope_small, 3)} | "
        f"{'PASS' if result.criteria.get('C1a_median_slope_>=_1.2') else 'FAIL'} |"
    )
    lines.append(
        f"| C1b q25 per-partition slope (small-trade) | >= {PASS_C1B_Q25_SLOPE} | "
        f"{_fmt(result.q25_slope_small, 3)} | "
        f"{'PASS' if result.criteria.get('C1b_q25_slope_>=_1.0') else 'FAIL'} |"
    )
    lines.append(
        f"| C2 median pooled gross edge (small, eligible) | >= {PASS_C2_GROSS_EDGE*100:.2f}pp | "
        f"{_fmt_pct(result.median_pooled_gross_edge_small)} | "
        f"{'PASS' if result.criteria.get('C2_median_gross_edge_>=_2.04pp') else 'FAIL'} |"
    )
    lines.append(
        f"| C3 walk-forward splits with median net > 0 | >= {PASS_C3_MIN_SPLITS_NET_POSITIVE} | "
        f"{result.n_splits_net_positive_small} of {len(result.walk_forward)} "
        f"(skipped {result.n_splits_skipped_sample_size} of "
        f"{result.n_splits_attempted}) | "
        f"{'PASS' if result.criteria.get('C3_>=_10_splits_net_>0') else 'FAIL'} |"
    )
    lines.append(
        f"| C4 event windows with median net > 0 | >= {PASS_C4_MIN_EVENT_WINDOWS_POSITIVE} of 4 | "
        f"{result.n_event_windows_net_positive} of {len(result.event_windows)} | "
        f"{'PASS' if result.criteria.get('C4_>=_3_of_4_event_windows_net_>0') else 'FAIL'} |"
    )
    pooled_median = _fmt_pct(result.pooled_median_net_edge_small)
    pooled_mean = _fmt_pct(result.pooled_mean_net_edge_small)
    lines.append(
        f"| C5 pooled median AND mean net edge (small) | both > 0pp | "
        f"median={pooled_median} mean={pooled_mean} | "
        f"{'PASS' if result.criteria.get('C5_pooled_median_AND_mean_net_>_0') else 'FAIL'} |"
    )
    lines.append("")

    lines.append("## Dataset")
    lines.append("")
    for k, v in dataset_meta.items():
        lines.append(f"- {k}: {v}")
    lines.append("")

    lines.append("## Cross-check on all-trade VWAP (diagnostic only)")
    lines.append("")
    lines.append(
        f"- pooled median net edge (all-trade): "
        f"{_fmt_pct(result.pooled_median_net_edge_all)}"
    )
    lines.append(
        f"- pooled mean net edge (all-trade): "
        f"{_fmt_pct(result.pooled_mean_net_edge_all)}"
    )
    lines.append(
        "If small-trade C5 fails but all-trade C5 passes, the strategy is NOT "
        "retail-tradable per phase-2-methodology Section 7 C5."
    )
    lines.append("")

    lines.append("## Pooled bootstrap on small-trade net edge (diagnostic)")
    lines.append("")
    lines.append(
        f"- mean: {_fmt_pct(result.bootstrap_mean_small)}"
    )
    lines.append(
        f"- 95% CI: [{_fmt_pct(result.bootstrap_ci_lower_small)}, "
        f"{_fmt_pct(result.bootstrap_ci_upper_small)}]"
    )
    lines.append(
        "Diagnostic. Higher statistical power than per-split count (C3). "
        "Does not affect the gate verdict."
    )
    lines.append("")

    lines.append("## Per-series slope distribution (Section 6.5 diagnostic)")
    lines.append("")
    lines.append(
        f"- pooled per-series slope count: {result.per_market_slope_n}"
    )
    lines.append(
        f"- median: {_fmt(result.per_market_slope_median, 3)}"
    )
    lines.append(
        f"- q25: {_fmt(result.per_market_slope_q25, 3)}"
    )
    lines.append(
        f"- q75: {_fmt(result.per_market_slope_q75, 3)}"
    )
    lines.append(
        "Distribution of per-series logistic-regression slopes (one slope per "
        "series with >= 50 test-partition markets). Diagnostic only; not a "
        "gate. Per Section 7.1, the per-series distribution validates that "
        "C1's per-partition slope is not pulled up by a few outlier series."
    )
    lines.append("")

    lines.append("## Election composition diagnostic")
    lines.append("")
    lines.append(f"- corpus federal-election market rate: {_fmt(result.pct_federal_election_corpus, 3)}")
    lines.append(f"- election-dominated splits (test > 50% federal): {result.n_election_dominated_splits}")
    lines.append(
        f"- median net edge on election-dominated splits: "
        f"{_fmt_pct(result.median_net_edge_election_dominated)}"
    )
    lines.append(
        f"- median net edge on non-election splits: "
        f"{_fmt_pct(result.median_net_edge_non_election)}"
    )
    lines.append("")

    lines.append("## Walk-forward splits")
    lines.append("")
    lines.append(
        "| Split | n_train | n_test | n_eligible | slope | raw ECE | cal ECE | "
        "ratio | median gross | median net (small) | median net (all) | "
        "pct federal |"
    )
    lines.append(
        "|---|---|---|---|---|---|---|---|---|---|---|---|"
    )
    for r in result.walk_forward:
        lines.append(
            f"| {r.label} | {r.n_train} | {r.n_test} | {r.n_eligible} | "
            f"{_fmt(r.slope_small, 3)} | {_fmt(r.raw_ece_small)} | "
            f"{_fmt(r.cal_ece_small)} | {_fmt(r.ece_ratio_small, 2)}x | "
            f"{_fmt_pct(r.median_gross_edge_small)} | "
            f"{_fmt_pct(r.median_net_edge_small)} | "
            f"{_fmt_pct(r.median_net_edge_all)} | "
            f"{_fmt(r.pct_federal_election_test, 3)} |"
        )
    lines.append("")

    lines.append("## Leave-one-event-window-out")
    lines.append("")
    lines.append("| Window | n_train | n_test | n_eligible | median net (small) |")
    lines.append("|---|---|---|---|---|")
    for r in result.event_windows:
        lines.append(
            f"| {r.label} ({r.window_start.date()} to {r.window_end.date()}) | "
            f"{r.n_train} | {r.n_test} | {r.n_eligible} | "
            f"{_fmt_pct(r.median_net_edge_small)} |"
        )
    lines.append("")

    lines.append("## Recommendation")
    lines.append("")
    if result.passes:
        lines.append(
            "All five locked criteria cleared. Politics x H promoted from "
            "hypothesis to Phase 3 candidate. Per phase-2-methodology Section 10, "
            "Phase 3 = live-strategy design + critic pass + 200-fill paper trade "
            "validation (especially fill-rate measurement, which the backtest "
            "could not test). Phase 2 pass is NECESSARY-NOT-SUFFICIENT for live "
            "capital."
        )
    else:
        lines.append(
            "At least one pass criterion was not met. Per the methodology lock-in "
            "(no third bite, no post-data criterion tuning), the strategy ends "
            "here. Politics x H is not a tradable hypothesis at this scale and "
            "infrastructure given the locked methodology. The engineering "
            "artifacts remain as reference. Operator may authorize a pivot to "
            "Sports x Long-Horizon (the runner-up from the proposal) or end the "
            "project."
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    configure_logging()
    log = structlog.get_logger("run_gate_phase2")

    if not DATASET_PATH.exists():
        log.error("dataset_missing", path=str(DATASET_PATH))
        return 1

    df = pd.read_parquet(DATASET_PATH)
    df["market_open_time"] = pd.to_datetime(df["market_open_time"], utc=True)
    df["market_close_time"] = pd.to_datetime(df["market_close_time"], utc=True)

    dataset_meta = {
        "rows": len(df),
        "unique_series": int(df["series_ticker"].nunique()),
        "date_min": str(df["market_close_time"].min()),
        "date_max": str(df["market_close_time"].max()),
        "outcome_rate": round(float(df["outcome"].mean()), 4),
        "fed_election_rate": round(float(df["is_federal_election_market"].mean()), 4),
        "median_trades_in_window": int(df["n_trades_in_window"].median()),
        "median_small_trades_in_window": int(df["n_small_trades_in_window"].median()),
        "mid_small_p05": round(float(df["mid_price_at_T_small"].quantile(0.05)), 4),
        "mid_small_p50": round(float(df["mid_price_at_T_small"].quantile(0.50)), 4),
        "mid_small_p95": round(float(df["mid_price_at_T_small"].quantile(0.95)), 4),
    }
    log.info("dataset_loaded", **dataset_meta)

    result = evaluate(df)
    log.info(
        "gate_result",
        passes=result.passes,
        median_slope=result.median_slope_small,
        q25_slope=result.q25_slope_small,
        pooled_gross_edge=result.median_pooled_gross_edge_small,
        pooled_median_net=result.pooled_median_net_edge_small,
        pooled_mean_net=result.pooled_mean_net_edge_small,
        n_splits_net_positive=result.n_splits_net_positive_small,
        n_event_windows_net_positive=result.n_event_windows_net_positive,
    )

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(render_report(result, dataset_meta), encoding="utf-8")
    log.info("wrote_report", path=str(REPORT_PATH))

    return 0 if result.passes else 2


if __name__ == "__main__":
    sys.exit(main())
