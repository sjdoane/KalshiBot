"""v2 gate evaluator: same 5 criteria as Strategy B Round 4 plus the
v2-specific C6 (must beat v1 heuristic by at least 2pp).

This gate is model-agnostic. Caller passes:
- the dataset DataFrame (one row per market with outcome and price)
- a `trade_decision_fn(row) -> (should_trade: bool, predicted_yes_prob: float)`
  that encodes the model's decision rule. The gate handles the splits,
  realized P&L, bootstrap CI, etc.

This way Agent E (modeling) can swap models in/out without touching the
gate code, and we can compare model variants on identical evaluation.

Pass criteria (locked):
- C1: holdout realized mean P&L > 0
- C2: holdout realized bootstrap 95% CI lower > 0
- C3: holdout hit rate > 0.55
- C4: holdout eligible n >= 15
- C5: 5-fold pooled mean > 0
- C6: holdout mean exceeds v1 heuristic's holdout mean on the SAME
       data by at least 2pp (otherwise v2 model adds variance without
       gain and operator should keep v1)
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np
import structlog

from kalshi_bot.analysis.bootstrap import bootstrap_mean_ci
from kalshi_bot.analysis.metrics import kalshi_maker_fee_per_contract

if TYPE_CHECKING:
    import pandas as pd

log = structlog.get_logger(__name__)


# Pass criteria
HOLDOUT_FRAC = 0.30
PASS_C1_MEAN_POSITIVE = 0.0
PASS_C2_BOOTSTRAP_CI_LOWER = 0.0
PASS_C3_HIT_RATE = 0.55
PASS_C4_MIN_ELIGIBLE = 15
PASS_C5_FOLDS_MEAN_POSITIVE = 0.0
PASS_C6_V2_BEATS_V1_PP = 0.02  # v2 must beat v1 by 2 percentage points
N_FOLDS = 5
BOOTSTRAP_N_RESAMPLES = 5000
BOOTSTRAP_CI = 0.95
BOOTSTRAP_SEED = 42
SLIPPAGE_ALLOWANCE = 0.015


# A trade decision is (should_trade, predicted_yes_prob). When
# should_trade is False, the row is skipped (no capital deployed).
# When True, the caller buys YES at `price` and holds to settlement.
TradeDecisionFn = Callable[[dict], tuple[bool, float]]

# A trainer takes a chronological prefix of the dataset and returns a
# fresh decision function whose internal model was trained ONLY on that
# prefix. Required for the 5-fold CV in `evaluate()` to be genuinely
# out-of-sample (without it, folds 1..K-1 evaluate the model on rows
# that were inside its original training set; this was the Round 4
# critic finding that motivated the leak fix).
TrainerFn = Callable[["pd.DataFrame"], TradeDecisionFn]


@dataclass
class GateResult:
    """Results from running the gate on a single trade-decision rule.

    All P&L values are per-contract dollars net of round-trip maker
    fees + SLIPPAGE_ALLOWANCE. Bootstrap CIs use 5000 resamples,
    seed 42.
    """

    holdout_train_n: int = 0
    holdout_test_n: int = 0
    holdout_eligible_n: int = 0
    holdout_mean: float = float("nan")
    holdout_median: float = float("nan")
    holdout_sd: float = float("nan")
    holdout_hit_rate: float = float("nan")
    holdout_ci_lower: float = float("nan")
    holdout_ci_upper: float = float("nan")
    folds_eligible_total: int = 0
    folds_pooled_mean: float = float("nan")
    folds_pooled_median: float = float("nan")
    folds_pooled_ci_lower: float = float("nan")
    folds_pooled_ci_upper: float = float("nan")
    fold_means: list[float] = field(default_factory=list)
    v1_holdout_mean: float = float("nan")  # for C6 comparison
    criteria: dict[str, bool] = field(default_factory=dict)
    passes: bool = False
    note: str = ""


def realized_pnl_per_contract(
    yes_price: float, outcome: int, *,
    slippage: float = SLIPPAGE_ALLOWANCE,
) -> float:
    """Same P&L formula as v1: gross - round-trip maker fee - slippage."""
    gross = outcome - yes_price
    fee = 2.0 * kalshi_maker_fee_per_contract(yes_price)
    return gross - fee - slippage


def _evaluate_rule_on_df(
    df: pd.DataFrame,
    decision_fn: TradeDecisionFn,
    price_col: str = "favorite_price",
    outcome_col: str = "outcome",
) -> np.ndarray:
    """Apply decision_fn to each row; return realized P&L for rows
    where should_trade=True, in dataset order. Empty array if no row
    passes the decision rule.
    """
    realized: list[float] = []
    for _, row in df.iterrows():
        row_dict = row.to_dict()
        should_trade, _predicted_prob = decision_fn(row_dict)
        if not should_trade:
            continue
        price = float(row_dict[price_col])
        outcome = int(row_dict[outcome_col])
        realized.append(realized_pnl_per_contract(price, outcome))
    return np.asarray(realized, dtype=float)


def _holdout_split(df: pd.DataFrame, holdout_frac: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    df_sorted = df.sort_values("close_time").reset_index(drop=True)
    split_idx = int(len(df_sorted) * (1.0 - holdout_frac))
    return df_sorted.iloc[:split_idx], df_sorted.iloc[split_idx:]


def _kfold_splits(df: pd.DataFrame, n_folds: int):
    """Time-walk-forward folds. Yields (train, test) for each fold."""
    df_sorted = df.sort_values("close_time").reset_index(drop=True)
    n = len(df_sorted)
    fold_size = n // n_folds
    if fold_size < 5:
        return
    for fold in range(1, n_folds):
        train_end = fold * fold_size
        test_end = (fold + 1) * fold_size
        yield df_sorted.iloc[:train_end], df_sorted.iloc[train_end:test_end]


def v1_decision_fn(row: dict) -> tuple[bool, float]:
    """The v1 heuristic, used as the baseline for the C6 comparison.

    Trade every row whose price is in [0.70, 0.95] (the eligibility
    has already been applied at dataset-build time; this just trades
    unconditionally on the eligible set). Returns predicted prob
    = 0.95 (the v1 default).
    """
    return True, 0.95


def evaluate(
    df: pd.DataFrame,
    decision_fn: TradeDecisionFn,
    *,
    trainer: TrainerFn | None = None,
    price_col: str = "favorite_price",
    outcome_col: str = "outcome",
    time_col: str = "close_time",
    note: str = "",
) -> GateResult:
    """Run the 6-criteria gate on a model's trade-decision rule.

    Required df columns: outcome (0/1), price_col, time_col. Decision
    fn receives the row as a dict and returns (should_trade,
    predicted_yes_prob).

    `trainer` (optional but recommended for model-based decision_fns):
    if provided, the 5-fold CV will call trainer(fold_train_df) for each
    fold and evaluate the returned fresh decision_fn on that fold's
    test slice. This is the only way to make C5 genuinely OOS for a
    model that was originally fit on a chronological prefix. Without
    trainer, the same decision_fn is reused across all folds, which
    leaks training data into folds 1..K-1 (Round 5 critic finding).

    For deterministic baselines like v1_decision_fn that don't train,
    pass trainer=None (the default).
    """
    required = (outcome_col, price_col, time_col)
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"evaluate: input DataFrame missing columns: {missing}")
    # Normalize time column name to "close_time" for the helpers.
    if time_col != "close_time":
        df = df.rename(columns={time_col: "close_time"})

    res = GateResult(note=note)

    # Holdout split (primary gate)
    train, test = _holdout_split(df, HOLDOUT_FRAC)
    res.holdout_train_n = len(train)
    res.holdout_test_n = len(test)
    realized_v2 = _evaluate_rule_on_df(test, decision_fn, price_col, outcome_col)
    res.holdout_eligible_n = int(realized_v2.size)
    if realized_v2.size > 0:
        res.holdout_mean = float(realized_v2.mean())
        res.holdout_median = float(np.median(realized_v2))
        res.holdout_sd = float(realized_v2.std())
        res.holdout_hit_rate = float((realized_v2 > 0).mean())
        try:
            _, lo, hi = bootstrap_mean_ci(
                realized_v2, n_resamples=BOOTSTRAP_N_RESAMPLES,
                ci=BOOTSTRAP_CI, rng_seed=BOOTSTRAP_SEED,
            )
            res.holdout_ci_lower = float(lo)
            res.holdout_ci_upper = float(hi)
        except ValueError:
            pass

    # v1 baseline on the same holdout for C6 comparison.
    realized_v1 = _evaluate_rule_on_df(test, v1_decision_fn, price_col, outcome_col)
    if realized_v1.size > 0:
        res.v1_holdout_mean = float(realized_v1.mean())

    # 5-fold time-walk-forward. CRITICAL: if a trainer is provided,
    # retrain on each fold's prefix; otherwise reuse the passed
    # decision_fn (correct only for non-trained baselines like v1).
    all_realized: list[np.ndarray] = []
    fold_means: list[float] = []
    for fold_train, fold_test in _kfold_splits(df, N_FOLDS):
        fold_decision_fn = (
            trainer(fold_train) if trainer is not None else decision_fn
        )
        fold_realized = _evaluate_rule_on_df(
            fold_test, fold_decision_fn, price_col, outcome_col,
        )
        all_realized.append(fold_realized)
        fold_means.append(
            float(fold_realized.mean()) if fold_realized.size > 0 else float("nan"),
        )
    if trainer is None and decision_fn is not v1_decision_fn:
        res.note = (
            res.note + " | LEAK-RISK: trainer=None for non-baseline fn; "
            "5-fold CV reuses pre-trained decision_fn across folds."
        ).strip(" |")
    pooled = np.concatenate(all_realized) if all_realized else np.array([])
    res.folds_eligible_total = int(pooled.size)
    res.fold_means = fold_means
    if pooled.size > 0:
        res.folds_pooled_mean = float(pooled.mean())
        res.folds_pooled_median = float(np.median(pooled))
        try:
            _, lo, hi = bootstrap_mean_ci(
                pooled, n_resamples=BOOTSTRAP_N_RESAMPLES,
                ci=BOOTSTRAP_CI, rng_seed=BOOTSTRAP_SEED,
            )
            res.folds_pooled_ci_lower = float(lo)
            res.folds_pooled_ci_upper = float(hi)
        except ValueError:
            pass

    # Criteria evaluation
    v2_minus_v1 = (
        res.holdout_mean - res.v1_holdout_mean
        if not (np.isnan(res.holdout_mean) or np.isnan(res.v1_holdout_mean))
        else float("nan")
    )
    res.criteria = {
        "C1_holdout_mean_>_0": (
            not np.isnan(res.holdout_mean)
            and res.holdout_mean > PASS_C1_MEAN_POSITIVE
        ),
        "C2_holdout_bootstrap_ci_lower_>_0": (
            not np.isnan(res.holdout_ci_lower)
            and res.holdout_ci_lower > PASS_C2_BOOTSTRAP_CI_LOWER
        ),
        "C3_holdout_hit_rate_>_55pct": (
            not np.isnan(res.holdout_hit_rate)
            and res.holdout_hit_rate > PASS_C3_HIT_RATE
        ),
        f"C4_holdout_n_>=_{PASS_C4_MIN_ELIGIBLE}": (
            res.holdout_eligible_n >= PASS_C4_MIN_ELIGIBLE
        ),
        "C5_folds_pooled_mean_>_0": (
            not np.isnan(res.folds_pooled_mean)
            and res.folds_pooled_mean > PASS_C5_FOLDS_MEAN_POSITIVE
        ),
        f"C6_v2_beats_v1_by_>={int(PASS_C6_V2_BEATS_V1_PP*100)}pp": (
            not np.isnan(v2_minus_v1)
            and v2_minus_v1 >= PASS_C6_V2_BEATS_V1_PP
        ),
    }
    res.passes = all(res.criteria.values())
    log.info("v2_gate_done",
             passes=res.passes,
             holdout_n=res.holdout_eligible_n,
             holdout_mean=res.holdout_mean,
             holdout_ci_lower=res.holdout_ci_lower,
             v1_baseline_mean=res.v1_holdout_mean,
             v2_minus_v1=v2_minus_v1,
             note=note)
    return res
