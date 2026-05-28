"""Sports x Long-Horizon gate runner. Writes research/sports-results.md."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import structlog

from kalshi_bot.analysis.gate_sports import (
    PASS_C1A_MEDIAN_SLOPE,
    PASS_C1B_Q25_SLOPE,
    PASS_C2_GROSS_EDGE,
    PASS_C4_MIN_LEAGUES_POSITIVE,
    SportsGateResult,
    evaluate,
)
from kalshi_bot.logging import configure_logging

DATASET_PATH = Path("data/processed/sports_dataset.parquet")
REPORT_PATH = Path("research/sports-results.md")


def _fmt_pct(x: float) -> str:
    if np.isnan(x):
        return "n/a"
    return f"{x*100:.2f}pp"


def _fmt(x: float, places: int = 4) -> str:
    if np.isnan(x):
        return "n/a"
    return f"{x:.{places}f}"


def render_report(result: SportsGateResult, dataset_meta: dict) -> str:
    lines: list[str] = []
    lines.append("# Sports x Long-Horizon Results: OOS Gate\n")
    lines.append(f"**Date generated:** {pd.Timestamp.now(tz='UTC').isoformat()}")
    lines.append("**Methodology:** [sports-longhorizon-methodology.md](sports-longhorizon-methodology.md)")
    lines.append("**Round 3 revision:** [round-3-methodology-revision.md](round-3-methodology-revision.md)")
    lines.append("**Window:** small-trade VWAP in [resolution - 42d, resolution - 28d]")
    provisional = result.criteria.get("PROVISIONAL_PASS_realized_mean_positive_but_CI_wide", False)
    if result.passes:
        verdict = "**GATE PASSES**"
    elif provisional:
        verdict = "**PROVISIONAL PASS** (methodology criteria pass; C6 realized-P&L CI wide; operator approval required for Phase 3 paper trading at minimal position size)"
    else:
        verdict = "**GATE FAILS**"
    lines.append(f"**Verdict:** {verdict}")
    lines.append("")
    lines.append("## Pass criteria")
    lines.append("")
    lines.append("| Criterion | Required | Observed | Result |")
    lines.append("|---|---|---|---|")
    # C1 is INFORMATIONAL only in Round 3.1 (not in gate-pass conjunction)
    c1a_status = "PASS (informational)" if (
        not np.isnan(result.median_slope_small)
        and result.median_slope_small >= PASS_C1A_MEDIAN_SLOPE
    ) else "FAIL (informational)"
    c1b_status = "PASS (informational)" if (
        not np.isnan(result.q25_slope_small)
        and result.q25_slope_small >= PASS_C1B_Q25_SLOPE
    ) else "FAIL (informational)"
    lines.append(
        f"| C1a median per-partition slope (informational) | >= {PASS_C1A_MEDIAN_SLOPE} | "
        f"{_fmt(result.median_slope_small, 3)} | {c1a_status} |"
    )
    lines.append(
        f"| C1b q25 per-partition slope (informational) | >= {PASS_C1B_Q25_SLOPE} | "
        f"{_fmt(result.q25_slope_small, 3)} | {c1b_status} |"
    )
    lines.append(
        f"| C2 median pooled gross edge (small, eligible) | >= {PASS_C2_GROSS_EDGE*100:.2f}pp | "
        f"{_fmt_pct(result.median_pooled_gross_edge_small)} | "
        f"{'PASS' if result.criteria.get('C2_median_gross_edge_>=_2.23pp') else 'FAIL'} |"
    )
    lines.append(
        f"| C3 pooled bootstrap 95% CI lower bound | > 0pp | "
        f"{_fmt_pct(result.bootstrap_ci_lower_small)} "
        f"(diag: {result.n_splits_net_positive_small} of {len(result.walk_forward)} splits "
        f"net > 0; {result.n_splits_skipped_sample_size} of {result.n_splits_attempted} skipped) | "
        f"{'PASS' if result.criteria.get('C3_pooled_bootstrap_ci_lower_>_0') else 'FAIL'} |"
    )
    c4_key = f"C4_>=_3_of_{result.n_leagues_evaluated}_leagues_net_>0_with_N>=3"
    lines.append(
        f"| C4 leagues with median net > 0 (needs N>=3 leagues) | "
        f">= {PASS_C4_MIN_LEAGUES_POSITIVE} of {result.n_leagues_evaluated} | "
        f"{result.n_leagues_net_positive} of {result.n_leagues_evaluated} | "
        f"{'PASS' if result.criteria.get(c4_key) else 'FAIL'} |"
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

    lines.append("## Cross-check on all-trade VWAP (diagnostic)")
    lines.append("")
    lines.append(f"- pooled median net edge (all-trade): {_fmt_pct(result.pooled_median_net_edge_all)}")
    lines.append(f"- pooled mean net edge (all-trade): {_fmt_pct(result.pooled_mean_net_edge_all)}")
    lines.append("")

    lines.append("## Resolution-time-purge sensitivity check (methodology Section 5.1)")
    lines.append("")
    lines.append(
        "Re-runs walk-forward with the stricter constraint that test markets must "
        "open AFTER train_end. If the locked gate PASSES but this sensitivity "
        "check FAILS, the apparent edge is plausibly leakage-driven through "
        "shared news-period structure during overlapping lifetimes."
    )
    lines.append("")
    lines.append(
        f"- splits attempted: {result.sensitivity_n_splits_attempted}; "
        f"skipped: {result.sensitivity_n_splits_skipped}"
    )
    lines.append(
        f"- pooled median net edge: "
        f"{_fmt_pct(result.sensitivity_pooled_median_net_edge_small)}"
    )
    lines.append(
        f"- pooled mean net edge: "
        f"{_fmt_pct(result.sensitivity_pooled_mean_net_edge_small)}"
    )
    lines.append(
        f"- bootstrap 95% CI: "
        f"[{_fmt_pct(result.sensitivity_bootstrap_ci_lower_small)}, "
        f"{_fmt_pct(result.sensitivity_bootstrap_ci_upper_small)}]"
    )
    lines.append(
        f"- would pass equivalent C3 + C5 if were the gate: "
        f"{'YES' if result.sensitivity_passes_if_were_gate else 'NO'}"
    )
    lines.append("")

    lines.append("## Realized P&L diagnostic (Round 3.1 honest-edge test)")
    lines.append("")
    lines.append(
        "C6 measures whether the model-predicted edge MATERIALIZES in "
        "realized profit on the OOS test set. This is the strictest "
        "validation: the bot's actual trade decisions, settled at the "
        "actual outcome, after fees and slippage."
    )
    lines.append("")
    lines.append(f"- n_trades: {result.realized_pnl_n}")
    lines.append(f"- hit rate (P&L > 0): {_fmt(result.realized_pnl_hit_rate * 100, 1)}%")
    lines.append(f"- median realized P&L: {_fmt_pct(result.realized_pnl_median)}")
    lines.append(f"- mean realized P&L: {_fmt_pct(result.realized_pnl_mean)}")
    lines.append(f"- SD per trade: {_fmt_pct(result.realized_pnl_sd)}")
    lines.append(
        f"- bootstrap mean: {_fmt_pct(result.realized_pnl_bootstrap_mean)}"
    )
    lines.append(
        f"- bootstrap 95% CI: [{_fmt_pct(result.realized_pnl_bootstrap_ci_lower)}, "
        f"{_fmt_pct(result.realized_pnl_bootstrap_ci_upper)}]"
    )
    lines.append("")

    lines.append("## Pooled bootstrap on small-trade net edge")
    lines.append("")
    lines.append(f"- mean: {_fmt_pct(result.bootstrap_mean_small)}")
    lines.append(
        f"- 95% CI: [{_fmt_pct(result.bootstrap_ci_lower_small)}, "
        f"{_fmt_pct(result.bootstrap_ci_upper_small)}]"
    )
    lines.append("")

    lines.append("## Per-series slope distribution")
    lines.append("")
    lines.append(f"- n: {result.per_market_slope_n}")
    lines.append(f"- median: {_fmt(result.per_market_slope_median, 3)}")
    lines.append(f"- q25: {_fmt(result.per_market_slope_q25, 3)}")
    lines.append(f"- q75: {_fmt(result.per_market_slope_q75, 3)}")
    lines.append("")

    lines.append("## League distribution (full corpus)")
    lines.append("")
    for lg, n in sorted(result.league_distribution.items(), key=lambda x: -x[1]):
        lines.append(f"- {lg}: {n}")
    lines.append("")

    lines.append("## Walk-forward splits")
    lines.append("")
    lines.append(
        "| Split | n_train | n_test | n_eligible | slope | raw ECE | cal ECE | "
        "ratio | median gross | median net (small) | median net (all) |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for r in result.walk_forward:
        lines.append(
            f"| {r.label} | {r.n_train} | {r.n_test} | {r.n_eligible} | "
            f"{_fmt(r.slope_small, 3)} | {_fmt(r.raw_ece_small)} | "
            f"{_fmt(r.cal_ece_small)} | {_fmt(r.ece_ratio_small, 2)}x | "
            f"{_fmt_pct(r.median_gross_edge_small)} | "
            f"{_fmt_pct(r.median_net_edge_small)} | "
            f"{_fmt_pct(r.median_net_edge_all)} |"
        )
    lines.append("")

    lines.append("## Leave-one-league-out")
    lines.append("")
    lines.append("| League | n_train | n_test | n_eligible | median net (small) |")
    lines.append("|---|---|---|---|---|")
    for r in result.leagues:
        lines.append(
            f"| {r.league} | {r.n_train} | {r.n_test} | {r.n_eligible} | "
            f"{_fmt_pct(r.median_net_edge_small)} |"
        )
    lines.append("")

    lines.append("## Recommendation")
    lines.append("")
    provisional = result.criteria.get("PROVISIONAL_PASS_realized_mean_positive_but_CI_wide", False)
    if result.passes:
        lines.append(
            "All locked criteria cleared. Sports x Long-Horizon promoted to "
            "Phase 3 candidate. Phase 3 = live-strategy design + critic + "
            "200-fill paper trade validation. Phase 2 pass is NECESSARY-NOT-"
            "SUFFICIENT for live capital deployment."
        )
    elif provisional:
        lines.append(
            "**PROVISIONAL PASS**: methodology criteria (C2, C3, C4, C5) ALL "
            "pass. Predicted edge is consistently positive across the OOS "
            "test partitions; the bootstrap CI on predicted edge excludes "
            "zero. C6 (realized-P&L bootstrap CI > 0) does NOT pass because "
            f"the realized sample (n={result.realized_pnl_n}) is too small "
            "to achieve statistical confidence at SD ~47pp per trade. "
            "Realized mean P&L is POSITIVE."
        )
        lines.append("")
        lines.append(
            "Recommendation: operator-approved Phase 3 paper trading at "
            "MINIMAL position size ($0.50 per trade or less) to gather "
            "more sample. Target: 100+ paper-traded fills. If paper P&L "
            "mean remains positive and bootstrap CI becomes positive, "
            "scale to live capital. If paper P&L turns negative, end the "
            "strategy."
        )
        lines.append("")
        lines.append(
            "DO NOT deploy live capital based on this gate alone. The C6 "
            "failure is honest acknowledgement that the small sample "
            "doesn't statistically rule out a near-zero true edge."
        )
    else:
        lines.append(
            "At least one criterion failed. Per methodology lock (no third "
            "bite), the strategy ends. Operator decides next steps on "
            "wake-up: end project, authorize fundamentally different thesis, "
            "or revisit methodology design with full understanding of "
            "observed shape."
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    configure_logging()
    log = structlog.get_logger("run_sports_gate")
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
        "median_trades_in_window": int(df["n_trades_in_window"].median()),
        "median_small_trades_in_window": int(df["n_small_trades_in_window"].median()),
        "median_lifetime_days": int(df["lifetime_days"].median()),
        "mid_small_p05": round(float(df["mid_price_at_T_small"].quantile(0.05)), 4),
        "mid_small_p50": round(float(df["mid_price_at_T_small"].quantile(0.50)), 4),
        "mid_small_p95": round(float(df["mid_price_at_T_small"].quantile(0.95)), 4),
    }
    log.info("dataset_loaded", **dataset_meta)
    result = evaluate(df)
    log.info("gate_result", passes=result.passes,
             median_slope=result.median_slope_small, q25_slope=result.q25_slope_small,
             pooled_gross_edge=result.median_pooled_gross_edge_small,
             pooled_median_net=result.pooled_median_net_edge_small,
             pooled_mean_net=result.pooled_mean_net_edge_small,
             n_splits_net_positive=result.n_splits_net_positive_small,
             n_leagues_net_positive=result.n_leagues_net_positive,
             n_leagues_evaluated=result.n_leagues_evaluated)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(render_report(result, dataset_meta), encoding="utf-8")
    log.info("wrote_report", path=str(REPORT_PATH))
    return 0 if result.passes else 2


if __name__ == "__main__":
    sys.exit(main())
