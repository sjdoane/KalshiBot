"""Exact state-price certificates for absence of v34 lattice arbitrage.

The numerical optimizer only proposes weights. A certificate has authority only
after every inequality is rechecked with exact rational arithmetic.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from fractions import Fraction
from typing import TYPE_CHECKING, Any

from scipy.optimize import linprog  # type: ignore[import-untyped]

if TYPE_CHECKING:
    from scripts.v34.derivatives_lattice import DisplayedLeg

MAX_LP_COEFFICIENTS = 1_000_000
MAX_CONSTRUCTION_DENOMINATOR = 1_000_000


class StatePriceCertificateError(ValueError):
    """Raised when certificate construction inputs are malformed."""


def _require_exact_int(value: object, name: str) -> int:
    if type(value) is not int:
        raise StatePriceCertificateError(f"{name} must be an exact integer")
    return value


def _state_count(legs: tuple[DisplayedLeg, ...]) -> int:
    if not legs:
        raise StatePriceCertificateError("at least one displayed leg is required")
    count = len(legs[0].payouts_cents)
    if count < 1 or any(len(leg.payouts_cents) != count for leg in legs):
        raise StatePriceCertificateError("all legs must share a nonempty atomic state space")
    return count


@dataclass(frozen=True, slots=True)
class StatePriceCertificate:
    """An exact probability vector and its leg-by-leg ask inequalities."""

    state_weights: tuple[Fraction, ...]
    expected_payout_cents_by_leg: tuple[Fraction, ...]
    slack_cents_by_leg: tuple[Fraction, ...]
    minimum_slack_cents: Fraction
    construction_denominator: int


def certificate_from_exact_weights(
    legs: tuple[DisplayedLeg, ...],
    state_weights: tuple[Fraction, ...],
    *,
    construction_denominator: int,
) -> StatePriceCertificate:
    """Build a certificate object from caller-supplied exact probability weights."""

    state_count = _state_count(legs)
    construction_denominator = _require_exact_int(
        construction_denominator, "construction_denominator"
    )
    if construction_denominator < 1:
        raise StatePriceCertificateError("construction_denominator must be positive")
    if len(state_weights) != state_count:
        raise StatePriceCertificateError("weight count must equal atomic state count")
    if any(type(weight) is not Fraction for weight in state_weights):
        raise StatePriceCertificateError("state weights must be exact Fractions")
    if any(weight < 0 for weight in state_weights) or sum(state_weights, Fraction(0)) != 1:
        raise StatePriceCertificateError("state weights must be nonnegative and sum to one")
    if any(construction_denominator % weight.denominator != 0 for weight in state_weights):
        raise StatePriceCertificateError(
            "construction_denominator must be a common multiple of weight denominators"
        )

    expected = tuple(
        sum(
            (
                weight * leg.payouts_cents[state_index]
                for state_index, weight in enumerate(state_weights)
            ),
            Fraction(0),
        )
        for leg in legs
    )
    slack = tuple(
        Fraction(leg.ask_cents) - value for leg, value in zip(legs, expected, strict=True)
    )
    if any(value < 0 for value in slack):
        raise StatePriceCertificateError("state weights violate an executable ask inequality")
    return StatePriceCertificate(
        state_weights=state_weights,
        expected_payout_cents_by_leg=expected,
        slack_cents_by_leg=slack,
        minimum_slack_cents=min(slack),
        construction_denominator=construction_denominator,
    )


def verify_state_price_certificate(
    legs: tuple[DisplayedLeg, ...], certificate: StatePriceCertificate
) -> bool:
    """Verify the complete no-arbitrage proof using exact rational arithmetic."""

    try:
        if (
            type(certificate.construction_denominator) is not int
            or certificate.construction_denominator < 1
        ):
            return False
        if any(type(value) is not Fraction for value in certificate.expected_payout_cents_by_leg):
            return False
        if any(type(value) is not Fraction for value in certificate.slack_cents_by_leg):
            return False
        if type(certificate.minimum_slack_cents) is not Fraction:
            return False
        rebuilt = certificate_from_exact_weights(
            legs,
            certificate.state_weights,
            construction_denominator=certificate.construction_denominator,
        )
    except (AttributeError, StatePriceCertificateError, TypeError, ValueError, ZeroDivisionError):
        return False
    if rebuilt != certificate:
        return False
    return all(slack >= 0 for slack in certificate.slack_cents_by_leg)


def _largest_remainder_weights(values: tuple[float, ...], denominator: int) -> tuple[Fraction, ...]:
    clipped = tuple(0.0 if -1e-12 <= value < 0.0 else value for value in values)
    if any(not math.isfinite(value) or value < 0 for value in clipped):
        raise StatePriceCertificateError("optimizer proposed an invalid probability")
    total = sum(clipped)
    if not math.isfinite(total) or total <= 0:
        raise StatePriceCertificateError("optimizer proposed zero probability mass")
    normalized = tuple(value / total for value in clipped)
    scaled = tuple(value * denominator for value in normalized)
    counts = [math.floor(value) for value in scaled]
    remaining = denominator - sum(counts)
    order = sorted(
        range(len(values)),
        key=lambda index: (scaled[index] - counts[index], -index),
        reverse=True,
    )
    for index in order[:remaining]:
        counts[index] += 1
    return tuple(Fraction(count, denominator) for count in counts)


def _denominator_schedule(max_denominator: int) -> tuple[int, ...]:
    values = [
        value for value in (100, 1_000, 10_000, 100_000, 1_000_000) if value <= max_denominator
    ]
    if max_denominator not in values:
        values.append(max_denominator)
    return tuple(sorted(set(values)))


def propose_exact_state_price_certificate(
    legs: tuple[DisplayedLeg, ...],
    *,
    max_denominator: int = 1_000_000,
) -> StatePriceCertificate | None:
    """Use a floating LP to propose, then exactly verify, a no-arbitrage certificate."""

    state_count = _state_count(legs)
    max_denominator = _require_exact_int(max_denominator, "max_denominator")
    if max_denominator < 1:
        raise StatePriceCertificateError("max_denominator must be positive")
    if max_denominator > MAX_CONSTRUCTION_DENOMINATOR:
        raise StatePriceCertificateError(
            f"max_denominator exceeds hard bound {MAX_CONSTRUCTION_DENOMINATOR}"
        )
    coefficient_count = len(legs) * (state_count + 1)
    if coefficient_count > MAX_LP_COEFFICIENTS:
        raise StatePriceCertificateError(
            f"LP has {coefficient_count} coefficients, above bound {MAX_LP_COEFFICIENTS}"
        )

    objective = [0.0] * state_count + [-1.0]
    upper_matrix = [[float(payout) for payout in leg.payouts_cents] + [1.0] for leg in legs]
    upper_bounds = [float(leg.ask_cents) for leg in legs]
    equality_matrix = [[1.0] * state_count + [0.0]]
    equality_bounds = [1.0]
    bounds = [(0.0, None)] * (state_count + 1)
    result: Any = linprog(
        c=objective,
        A_ub=upper_matrix,
        b_ub=upper_bounds,
        A_eq=equality_matrix,
        b_eq=equality_bounds,
        bounds=bounds,
        method="highs",
    )
    if not bool(result.success) or result.x is None:
        return None
    proposed = tuple(float(value) for value in result.x[:state_count])
    for denominator in _denominator_schedule(max_denominator):
        try:
            weights = _largest_remainder_weights(proposed, denominator)
            certificate = certificate_from_exact_weights(
                legs, weights, construction_denominator=denominator
            )
        except StatePriceCertificateError:
            continue
        if verify_state_price_certificate(legs, certificate):
            return certificate
    return None
