"""Phase 1.5 step 4: run the calibration gate, write the results report.

Reads data/processed/kxhigh_dataset.parquet, evaluates per the locked
methodology, and writes research/phase-1.5-results.md with the numerical
findings plus a clean PASS/KILL verdict.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import structlog

from kalshi_bot.analysis.gate import GateResult, evaluate
from kalshi_bot.logging import configure_logging

DATASET_PATH = Path("data/processed/kxhigh_dataset.parquet")
REPORT_PATH = Path("research/phase-1.5-results.md")


def render_report(result: GateResult, dataset_meta: dict) -> str:
    lines: list[str] = []
    lines.append("# Phase 1.5 Results: Zerve Out-of-Sample Replication\n")
    lines.append(f"**Date generated:** {pd.Timestamp.utcnow().isoformat()}Z")
    lines.append("**Methodology:** [phase-1.5-methodology.md](phase-1.5-methodology.md)")
    lines.append("**Verdict:** " + ("**GATE PASSES**" if result.passes else "**GATE FAILS**"))
    lines.append("")
    lines.append("## Pass criteria")
    lines.append("")
    lines.append("| Criterion | Required | Observed | Result |")
    lines.append("|---|---|---|---|")
    lines.append(
        f"| C1 median OOS ECE improvement | >= 5x | "
        f"{result.median_ece_ratio:.2f}x | "
        f"{'PASS' if result.criteria.get('C1_median_ECE_ratio_>=_5x') else 'FAIL'} |"
    )
    lines.append(
        f"| C2 median shoulder gross edge | >= 2pp | "
        f"{result.median_shoulder_gross_edge*100:.2f}pp | "
        f"{'PASS' if result.criteria.get('C2_median_shoulder_gross_edge_>=_2pp') else 'FAIL'} |"
    )
    lines.append(
        f"| C3 at least 4 splits with >= 3x | >= 4 | "
        f"{result.n_splits_above_stability} | "
        f"{'PASS' if result.criteria.get('C3_at_least_4_splits_with_>=_3x') else 'FAIL'} |"
    )
    lines.append(
        f"| C4 leave-one-city-out positive | >= 3 of 5 | "
        f"{result.loco_positive_cities} of {len(result.loco)} | "
        f"{'PASS' if result.criteria.get('C4_LOCO_positive_in_>=_3_of_5') else 'FAIL'} |"
    )
    lines.append(
        f"| C5 shoulder net edge (after fees) | > 0 | "
        f"{result.median_shoulder_net_edge*100:.2f}pp | "
        f"{'PASS' if result.criteria.get('C5_shoulder_net_edge_positive') else 'FAIL'} |"
    )
    lines.append("")

    lines.append("## Dataset")
    lines.append("")
    for k, v in dataset_meta.items():
        lines.append(f"- {k}: {v}")
    lines.append("")

    lines.append("## Walk-forward splits")
    lines.append("")
    lines.append("| Split | n_train | n_test | raw ECE | cal ECE | ratio | shoulder edge | net edge |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for r in result.walk_forward:
        lines.append(
            f"| {r.label} | {r.n_train} | {r.n_test} | "
            f"{r.raw_ece:.4f} | {r.cal_ece:.4f} | {r.ece_ratio:.2f}x | "
            f"{r.median_shoulder_gross_edge*100:.2f}pp | "
            f"{r.median_shoulder_net_edge*100:.2f}pp |"
        )
    lines.append("")

    lines.append("## Leave-one-city-out")
    lines.append("")
    lines.append("| Held-out city | n_train | n_test | raw ECE | cal ECE | ratio |")
    lines.append("|---|---|---|---|---|---|")
    for r in result.loco:
        lines.append(
            f"| {r.city} | {r.n_train} | {r.n_test} | "
            f"{r.raw_ece:.4f} | {r.cal_ece:.4f} | {r.ece_ratio:.2f}x |"
        )
    lines.append("")

    lines.append("## Recommendation")
    lines.append("")
    if result.passes:
        lines.append(
            "All five locked criteria cleared. EC-1 (KXHIGH weather maker-quoting) "
            "is promoted from hypothesis to candidate. Phase 2 strategy design may "
            "proceed under the constraints in research-document.md section 8 ($25 "
            "initial live cap, 200-fill go/no-go gate, wind-down mode, CPA + "
            "attorney consults before live capital)."
        )
    else:
        lines.append(
            "At least one pass criterion was not met. Per the methodology lock-in "
            "(no post-data criterion tuning), the project ends here. EC-1 is not a "
            "tradable hypothesis at this scale and infrastructure. The engineering "
            "artifacts remain in the repo as a reference implementation."
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    configure_logging()
    log = structlog.get_logger("run_gate")

    if not DATASET_PATH.exists():
        log.error("dataset_missing", path=str(DATASET_PATH))
        return 1

    df = pd.read_parquet(DATASET_PATH)
    df["market_open_time"] = pd.to_datetime(df["market_open_time"], utc=True)
    df["market_close_time"] = pd.to_datetime(df["market_close_time"], utc=True)

    dataset_meta = {
        "rows": len(df),
        "cities": sorted(df["city"].dropna().unique().tolist()),
        "date_min": str(df["occurrence_date"].min()),
        "date_max": str(df["occurrence_date"].max()),
        "outcome_rate": round(float(df["outcome"].mean()), 4),
        "mid_price_p05": round(float(df["mid_price_at_T"].quantile(0.05)), 4),
        "mid_price_p50": round(float(df["mid_price_at_T"].quantile(0.50)), 4),
        "mid_price_p95": round(float(df["mid_price_at_T"].quantile(0.95)), 4),
    }
    log.info("dataset_loaded", **dataset_meta)

    result = evaluate(df)
    log.info(
        "gate_result",
        passes=result.passes,
        median_ece_ratio=result.median_ece_ratio,
        median_shoulder_gross_edge=result.median_shoulder_gross_edge,
        n_splits_above_3x=result.n_splits_above_stability,
        loco_positive=result.loco_positive_cities,
    )

    REPORT_PATH.write_text(render_report(result, dataset_meta), encoding="utf-8")
    log.info("wrote_report", path=str(REPORT_PATH))

    return 0 if result.passes else 2  # exit 2 = gate fail (not an error)


if __name__ == "__main__":
    sys.exit(main())
