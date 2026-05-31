"""Gate A / Gate B evaluation core for the v16 lead-lag shadow study.

Pure and network-free. The locked gate definitions live in
research/v16/01-methodology-lock.md; this module turns per-fire records into
the binding statistics and the season verdict. The IO (loading the shadow
parquet, fetching per-ticker settlements) lives in scripts/v16/evaluate_gates.py.

Gate A (lag exists): per fire, CLV = executable exit at close (yes_bid at
close_time-2min) minus executable entry at T0 (yes_ask). Mid is banned on both
legs. Require mean CLV > 0 with a NIGHT-cluster bootstrap CI excluding zero AND
a WEEK-cluster CI that does not oppose it.

Gate B (harvestable at executable price, marketable-only): a fire is "fillable"
iff at T0 the executable yes_ask is at or below the sportsbook-implied level
(Kalshi was lagging cheap) AND there is depth for the size. P&L is booked at the
stale yes_ask paid, held to settlement, net of the Kalshi taker fee. Require
mean P&L over fillable fires > 0 with a night-cluster CI excluding zero.
Resting-maker fills are NOT in this gate (uncomputable unbiased record-only).
"""

from __future__ import annotations

from dataclasses import dataclass

from kalshi_bot.analysis.bootstrap import cluster_bootstrap_mean_ci
from kalshi_bot.analysis.metrics import kalshi_taker_fee_per_contract

# Full MLB regular season target per the methodology lock. Below this, a CI
# straddling zero is UNDERPOWERED, not a verdict.
MIN_NIGHTS_FOR_VERDICT = 120


def clv_dollars(entry_yes_ask: float | None, close_yes_bid: float | None) -> float | None:
    """Gate A closing-line value per fire, in dollars: executable exit
    (close yes_bid) minus executable entry (T0 yes_ask). None if either
    executable leg is missing (empty / unread book), so the fire is excluded
    rather than scored on a guessed price."""
    if entry_yes_ask is None or close_yes_bid is None:
        return None
    return float(close_yes_bid) - float(entry_yes_ask)


def is_fillable_marketable(
    entry_yes_ask: float | None,
    target_implied: float | None,
    depth: float | None,
    *,
    size: float = 1.0,
) -> bool:
    """Gate B marketable-fill condition: the executable yes_ask at T0 is at or
    below our willingness-to-pay (the sportsbook-implied level), so a marketable
    bid crosses the stale ask, AND there is depth for the size. This isolates
    the fires where Kalshi was genuinely lagging cheap (ask below the sharp
    line). Returns False on any missing leg."""
    if entry_yes_ask is None or target_implied is None or depth is None:
        return False
    return float(entry_yes_ask) <= float(target_implied) and float(depth) >= size


def marketable_settlement_pnl(
    entry_yes_ask: float | None, outcome: int | None
) -> float | None:
    """Gate B per-fire settlement P&L (dollars) for a marketable fill at the
    stale yes_ask, held to settlement, net of the Kalshi taker fee. outcome
    1 = the bet side won (ticker resolved yes), 0 = lost. None if missing."""
    if entry_yes_ask is None or outcome is None:
        return None
    p = float(entry_yes_ask)
    payoff = (1.0 - p) if int(outcome) == 1 else -p
    fee = kalshi_taker_fee_per_contract(p)
    return payoff - fee


@dataclass(frozen=True)
class GateResult:
    name: str
    n_obs: int
    n_nights: int
    mean: float
    night_ci_lower: float
    night_ci_upper: float
    week_ci_lower: float
    week_ci_upper: float
    night_excludes_zero: bool
    week_supports: bool
    passed: bool


def evaluate_gate(
    name: str,
    values: list[float | None],
    night_ids: list,
    week_ids: list,
    *,
    n_resamples: int = 5000,
    rng_seed: int = 0,
) -> GateResult | None:
    """Compute a gate's night-cluster and week-cluster bootstrap CIs.

    None values (and their cluster ids) are dropped first, so callers can pass
    the raw per-fire series. Returns None when no usable observation remains
    (caller treats that as "no data yet"). A gate PASSES when the night-cluster
    CI lower bound is > 0 AND the week-cluster CI is not entirely below zero
    (does not oppose the night result), per the methodology lock.
    """
    vals: list[float] = []
    nights: list = []
    weeks: list = []
    for v, n, w in zip(values, night_ids, week_ids, strict=True):
        if v is None:
            continue
        vals.append(float(v))
        nights.append(n)
        weeks.append(w)
    if not vals:
        return None
    mean, n_lo, n_hi, n_nights = cluster_bootstrap_mean_ci(
        vals, nights, n_resamples=n_resamples, rng_seed=rng_seed
    )
    # Distinct seed for the week bootstrap so the two cluster streams are
    # independent (they are different estimators over the same observations).
    _, w_lo, w_hi, _ = cluster_bootstrap_mean_ci(
        vals, weeks, n_resamples=n_resamples, rng_seed=rng_seed + 1
    )
    night_excludes_zero = n_lo > 0.0
    # "Does not oppose": the week CI is not entirely below zero.
    week_supports = w_hi > 0.0
    return GateResult(
        name=name, n_obs=len(vals), n_nights=n_nights, mean=mean,
        night_ci_lower=n_lo, night_ci_upper=n_hi,
        week_ci_lower=w_lo, week_ci_upper=w_hi,
        night_excludes_zero=night_excludes_zero, week_supports=week_supports,
        passed=night_excludes_zero and week_supports,
    )


def season_verdict(
    gate_a: GateResult | None,
    gate_b: GateResult | None,
    *,
    min_nights: int = MIN_NIGHTS_FOR_VERDICT,
) -> tuple[str, str]:
    """Return (verdict_code, human_recommendation) per the locked methodology.

    Codes:
      NO_DATA               - Gate A has no usable fires yet.
      UNDERPOWERED          - fewer than min_nights independent nights; keep
                              collecting, no binding verdict.
      KILL_NO_LAG           - full sample, Gate A night CI upper <= 0: no lag at
                              executable prices; lead-lag thesis DEAD, no rebuild.
      CONTINUE_ONE_SEASON   - full sample, Gate A sign-correct but CI straddles
                              zero: underpowered-continue for one more season.
      LAG_NOT_HARVESTABLE   - Gate A passes but Gate B fails: lag is real but not
                              capturable at executable prices; kill the
                              HARVESTABLE thesis permanently.
      HARVESTABLE_CONFIRMED - both gates pass: proceed to the Phase 3 tiny live
                              resting-order confirmation (create GATE_A_PASSED).
    """
    if gate_a is None:
        return "NO_DATA", "No usable fires with both an entry and a close leg yet."
    if gate_a.n_nights < min_nights:
        return (
            "UNDERPOWERED",
            f"Only {gate_a.n_nights} of {min_nights} nights collected. Keep the "
            f"logger running; a CI straddling zero now is underpowered, not a verdict.",
        )
    if gate_a.night_ci_upper <= 0.0:
        return (
            "KILL_NO_LAG",
            "Gate A night CI upper bound <= 0 at full season: the closing "
            "executable price is at or below the entry, so no lag exists at "
            "executable prices. Lead-lag thesis DEAD; do not build the rebuild.",
        )
    if not gate_a.passed:
        return (
            "CONTINUE_ONE_SEASON",
            "Gate A is sign-correct but its CI straddles zero at full season. "
            "This is the only result that earns a second season of collection.",
        )
    if gate_b is None or not gate_b.passed:
        return (
            "LAG_NOT_HARVESTABLE",
            "Gate A passes (the lag is real) but Gate B fails: the lag is not "
            "capturable at executable prices after fees. Kill the harvestable "
            "thesis; do not deploy capital.",
        )
    return (
        "HARVESTABLE_CONFIRMED",
        "Both gates pass. Proceed to the Phase 3 tiny live resting-order "
        "confirmation (create data/v16/GATE_A_PASSED, then run passive_fill_probe).",
    )
