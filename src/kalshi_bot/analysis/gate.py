"""Phase 1.5 gate: walk-forward + leave-one-city-out evaluation of isotonic
recalibration vs raw market prices.

The five pass criteria below are LOCKED in research/phase-1.5-methodology.md
section 5 and are NOT to be tuned after seeing results.

Returns a dataclass `GateResult` with all numerical findings. The caller
decides how to render them (Markdown report, console table, etc.).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from kalshi_bot.analysis.calibration import IsotonicCalibrator
from kalshi_bot.analysis.metrics import (
    expected_calibration_error,
    kalshi_maker_fee_per_contract,
    per_trade_gross_edge,
)
from kalshi_bot.analysis.train_test_split import (
    apply_split,
    leave_one_city_out,
    make_walk_forward_splits,
)

# Locked methodology parameters
WALK_FORWARD_TRAIN_DAYS = 180
WALK_FORWARD_TEST_DAYS = 30
WALK_FORWARD_PURGE_DAYS = 7
WALK_FORWARD_STEP_DAYS = 30
FIRST_TRAIN_START = pd.Timestamp("2024-01-01", tz="UTC")
LAST_TEST_END = pd.Timestamp("2026-04-30", tz="UTC")

MIN_TRAIN_SIZE = 200   # below this, skip the split (isotonic needs sample)
MIN_TEST_SIZE = 50

SHOULDER_LOWER = (0.15, 0.40)
SHOULDER_UPPER = (0.60, 0.85)

# Pass thresholds
PASS_MEDIAN_ECE_RATIO = 5.0
PASS_MIN_ECE_RATIO_STABILITY = 3.0
PASS_MIN_SPLITS_ABOVE_STABILITY = 4
PASS_MIN_SHOULDER_GROSS_EDGE = 0.02
PASS_MIN_LOCO_POSITIVE = 3


@dataclass
class SplitResult:
    label: str
    n_train: int
    n_test: int
    raw_ece: float
    cal_ece: float
    ece_ratio: float
    median_shoulder_gross_edge: float
    median_shoulder_net_edge: float
    n_shoulder: int


@dataclass
class LocoResult:
    city: str
    n_train: int
    n_test: int
    raw_ece: float
    cal_ece: float
    ece_ratio: float


@dataclass
class GateResult:
    walk_forward: list[SplitResult] = field(default_factory=list)
    loco: list[LocoResult] = field(default_factory=list)
    median_ece_ratio: float = float("nan")
    n_splits_above_stability: int = 0
    median_shoulder_gross_edge: float = float("nan")
    median_shoulder_net_edge: float = float("nan")
    loco_positive_cities: int = 0
    loco_worst_negative_drift: float = 0.0
    criteria: dict[str, bool] = field(default_factory=dict)
    passes: bool = False


def _shoulder_mask(prices: pd.Series) -> pd.Series:
    return (
        ((prices >= SHOULDER_LOWER[0]) & (prices <= SHOULDER_LOWER[1]))
        | ((prices >= SHOULDER_UPPER[0]) & (prices <= SHOULDER_UPPER[1]))
    )


def _split_metrics(train: pd.DataFrame, test: pd.DataFrame, label: str) -> SplitResult | None:
    if len(train) < MIN_TRAIN_SIZE or len(test) < MIN_TEST_SIZE:
        return None

    cal = IsotonicCalibrator().fit(train["mid_price_at_T"], train["outcome"])
    raw_test = test["mid_price_at_T"].to_numpy(dtype=float)
    y_test = test["outcome"].to_numpy(dtype=float)
    cal_test = cal.predict(raw_test)

    raw_ece = expected_calibration_error(raw_test, y_test)
    cal_ece = expected_calibration_error(cal_test, y_test)
    ratio = raw_ece / max(cal_ece, 1e-12)

    edge = per_trade_gross_edge(cal_test, raw_test)
    shoulder = _shoulder_mask(test["mid_price_at_T"]).to_numpy()

    # Fee-adjusted edge: subtract round-trip maker fee per side.
    fees_per_contract = np.array(
        [2 * kalshi_maker_fee_per_contract(float(p)) for p in raw_test]
    )
    net_edge = edge - fees_per_contract

    if shoulder.any():
        median_gross = float(np.median(edge[shoulder]))
        median_net = float(np.median(net_edge[shoulder]))
        n_shoulder = int(shoulder.sum())
    else:
        median_gross = float("nan")
        median_net = float("nan")
        n_shoulder = 0

    return SplitResult(
        label=label,
        n_train=len(train),
        n_test=len(test),
        raw_ece=float(raw_ece),
        cal_ece=float(cal_ece),
        ece_ratio=float(ratio),
        median_shoulder_gross_edge=median_gross,
        median_shoulder_net_edge=median_net,
        n_shoulder=n_shoulder,
    )


def run_walk_forward(df: pd.DataFrame) -> list[SplitResult]:
    splits = make_walk_forward_splits(
        first_train_start=FIRST_TRAIN_START,
        last_test_end=LAST_TEST_END,
        train_window=pd.Timedelta(days=WALK_FORWARD_TRAIN_DAYS),
        test_window=pd.Timedelta(days=WALK_FORWARD_TEST_DAYS),
        purge=pd.Timedelta(days=WALK_FORWARD_PURGE_DAYS),
        step=pd.Timedelta(days=WALK_FORWARD_STEP_DAYS),
    )
    results: list[SplitResult] = []
    for split in splits:
        train, test = apply_split(df, split)
        r = _split_metrics(train, test, label=split.label)
        if r is not None:
            results.append(r)
    return results


def run_loco(df: pd.DataFrame) -> list[LocoResult]:
    results: list[LocoResult] = []
    for city in sorted(df["city"].dropna().unique()):
        train, test = leave_one_city_out(df, city)
        if len(train) < MIN_TRAIN_SIZE or len(test) < MIN_TEST_SIZE:
            continue
        cal = IsotonicCalibrator().fit(train["mid_price_at_T"], train["outcome"])
        raw_ece = expected_calibration_error(test["mid_price_at_T"], test["outcome"])
        cal_ece = expected_calibration_error(
            cal.predict(test["mid_price_at_T"]), test["outcome"]
        )
        results.append(
            LocoResult(
                city=city,
                n_train=len(train),
                n_test=len(test),
                raw_ece=float(raw_ece),
                cal_ece=float(cal_ece),
                ece_ratio=float(raw_ece / max(cal_ece, 1e-12)),
            )
        )
    return results


def evaluate(df: pd.DataFrame) -> GateResult:
    wf = run_walk_forward(df)
    loco = run_loco(df)

    res = GateResult(walk_forward=wf, loco=loco)
    if wf:
        ratios = np.array([r.ece_ratio for r in wf])
        res.median_ece_ratio = float(np.median(ratios))
        res.n_splits_above_stability = int(
            (ratios >= PASS_MIN_ECE_RATIO_STABILITY).sum()
        )
        gross_edges = np.array(
            [r.median_shoulder_gross_edge for r in wf if not np.isnan(r.median_shoulder_gross_edge)]
        )
        net_edges = np.array(
            [r.median_shoulder_net_edge for r in wf if not np.isnan(r.median_shoulder_net_edge)]
        )
        res.median_shoulder_gross_edge = float(np.median(gross_edges)) if len(gross_edges) else float("nan")
        res.median_shoulder_net_edge = float(np.median(net_edges)) if len(net_edges) else float("nan")

    if loco:
        loco_ratios = np.array([r.ece_ratio for r in loco])
        res.loco_positive_cities = int((loco_ratios > 1.0).sum())
        # Worst negative drift = largest worsening (ratio < 1 means worse OOS)
        res.loco_worst_negative_drift = float(1.0 - loco_ratios.min()) if len(loco_ratios) else 0.0

    res.criteria = {
        "C1_median_ECE_ratio_>=_5x": res.median_ece_ratio >= PASS_MEDIAN_ECE_RATIO,
        "C2_median_shoulder_gross_edge_>=_2pp": res.median_shoulder_gross_edge
        >= PASS_MIN_SHOULDER_GROSS_EDGE,
        "C3_at_least_4_splits_with_>=_3x": res.n_splits_above_stability
        >= PASS_MIN_SPLITS_ABOVE_STABILITY,
        "C4_LOCO_positive_in_>=_3_of_5": res.loco_positive_cities >= PASS_MIN_LOCO_POSITIVE,
        "C5_shoulder_net_edge_positive": (res.median_shoulder_net_edge or 0.0) > 0,
    }
    res.passes = all(res.criteria.values())
    return res
