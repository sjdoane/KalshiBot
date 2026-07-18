"""Exact bounded enumeration for the read-only v34 derivatives sidecar."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from functools import reduce
from itertools import combinations, product
from math import gcd
from operator import mul


class DerivativesLatticeError(ValueError):
    """Raised when a lattice input or claimed result is invalid."""


class EnumerationIncompleteError(DerivativesLatticeError):
    """Raised before enumeration when the declared exact bound is insufficient."""


def _require_exact_int(value: object, name: str) -> int:
    if type(value) is not int:
        raise DerivativesLatticeError(f"{name} must be an exact integer")
    return value


@dataclass(frozen=True, slots=True)
class DisplayedLeg:
    """One executable displayed side with payouts in exact integer cents."""

    market_ticker: str
    side: str
    ask_cents: int
    depth: int
    payouts_cents: tuple[int, ...]

    def __post_init__(self) -> None:
        if not self.market_ticker:
            raise DerivativesLatticeError("market_ticker cannot be empty")
        if self.side not in ("YES", "NO"):
            raise DerivativesLatticeError("side must be YES or NO")
        ask = _require_exact_int(self.ask_cents, "ask_cents")
        depth = _require_exact_int(self.depth, "depth")
        if not 1 <= ask <= 99:
            raise DerivativesLatticeError("ask_cents must be between 1 and 99")
        if depth < 1:
            raise DerivativesLatticeError("depth must be positive")
        if not self.payouts_cents:
            raise DerivativesLatticeError("each leg needs at least one atomic payout")
        for payout in self.payouts_cents:
            checked = _require_exact_int(payout, "payout")
            if not 0 <= checked <= 100:
                raise DerivativesLatticeError("ordinary payouts must be within 0 and 100 cents")


@dataclass(frozen=True, slots=True)
class RecipeEvaluation:
    """Exact arithmetic for five copies of one integer recipe."""

    primitive_quantities: tuple[int, ...]
    five_copy_quantities: tuple[int, ...]
    payoff_vector_cents: tuple[int, ...]
    minimum_payout_cents: int
    ask_cost_cents: int
    fee_cents_by_leg: tuple[int, ...]
    total_cost_cents: int
    guaranteed_profit_cents: int
    support: int
    edge_bps_numerator: int
    edge_bps_denominator: int

    @property
    def qualifies(self) -> bool:
        return (
            self.minimum_payout_cents > 0
            and self.guaranteed_profit_cents > 0
            and self.edge_bps_numerator >= 200 * self.edge_bps_denominator
        )


@dataclass(frozen=True, slots=True)
class V29PairExplanation:
    leg_indices: tuple[int, int]
    payoff_vector_cents: tuple[int, ...]
    minimum_payout_cents: int
    total_cost_cents: int
    guaranteed_profit_cents: int


@dataclass(frozen=True, slots=True)
class CandidateAudit:
    evaluation: RecipeEvaluation
    v29_pair_clear: bool
    support_greater_than_two: bool
    support_two_relation_clear: bool
    proper_subrecipe_clear: bool
    dominance_clear: bool
    support_two_relation_explanations: tuple[tuple[int, ...], ...]
    proper_subrecipes: tuple[tuple[int, ...], ...]
    dominating_recipes: tuple[tuple[int, ...], ...]

    @property
    def incremental(self) -> bool:
        return (
            self.evaluation.qualifies
            and self.v29_pair_clear
            and self.support_greater_than_two
            and self.support_two_relation_clear
            and self.proper_subrecipe_clear
            and self.dominance_clear
        )


@dataclass(frozen=True, slots=True)
class EnumerationResult:
    state_count: int
    recipe_count: int
    audit_comparison_upper_bound: int
    qualifying_primitive_recipes: tuple[RecipeEvaluation, ...]
    pair_explanations: tuple[V29PairExplanation, ...]
    audits: tuple[CandidateAudit, ...]
    incremental_candidates: tuple[RecipeEvaluation, ...]
    snapshot_representative: RecipeEvaluation | None


def standard_taker_fee_cents(quantity: int, ask_cents: int) -> int:
    """Return ceil(7*q*(a/100)*(1-a/100)) in exact integer cents."""

    quantity = _require_exact_int(quantity, "quantity")
    ask_cents = _require_exact_int(ask_cents, "ask_cents")
    if quantity < 0:
        raise DerivativesLatticeError("quantity cannot be negative")
    if not 1 <= ask_cents <= 99:
        raise DerivativesLatticeError("ask_cents must be between 1 and 99")
    if quantity == 0:
        return 0
    numerator = 7 * quantity * ask_cents * (100 - ask_cents)
    return (numerator + 9_999) // 10_000


def _validate_legs(legs: tuple[DisplayedLeg, ...]) -> int:
    if not legs:
        raise DerivativesLatticeError("at least one displayed leg is required")
    state_count = len(legs[0].payouts_cents)
    identities = [(leg.market_ticker, leg.side) for leg in legs]
    if len(identities) != len(set(identities)):
        raise DerivativesLatticeError("displayed leg identities must be unique")
    if any(len(leg.payouts_cents) != state_count for leg in legs):
        raise DerivativesLatticeError("all legs must use the same atomic cells")
    return state_count


def evaluate_five_copy_recipe(
    legs: tuple[DisplayedLeg, ...], recipe: tuple[int, ...]
) -> RecipeEvaluation:
    """Evaluate exact five-copy quantities for one integer recipe."""

    state_count = _validate_legs(legs)
    if len(recipe) != len(legs):
        raise DerivativesLatticeError("recipe length must equal leg count")
    checked_recipe = tuple(_require_exact_int(value, "recipe quantity") for value in recipe)
    if any(value < 0 for value in checked_recipe) or not any(checked_recipe):
        raise DerivativesLatticeError("recipe must contain nonnegative quantities and be nonzero")
    quantities = tuple(5 * value for value in checked_recipe)
    if any(quantity > leg.depth for quantity, leg in zip(quantities, legs, strict=True)):
        raise DerivativesLatticeError("five-copy recipe exceeds displayed depth")

    payoff_vector = tuple(
        sum(
            quantity * leg.payouts_cents[state_index]
            for quantity, leg in zip(quantities, legs, strict=True)
        )
        for state_index in range(state_count)
    )
    ask_cost = sum(quantity * leg.ask_cents for quantity, leg in zip(quantities, legs, strict=True))
    fees = tuple(
        standard_taker_fee_cents(quantity, leg.ask_cents)
        for quantity, leg in zip(quantities, legs, strict=True)
    )
    total_cost = ask_cost + sum(fees)
    minimum_payout = min(payoff_vector)
    profit = minimum_payout - total_cost
    return RecipeEvaluation(
        primitive_quantities=checked_recipe,
        five_copy_quantities=quantities,
        payoff_vector_cents=payoff_vector,
        minimum_payout_cents=minimum_payout,
        ask_cost_cents=ask_cost,
        fee_cents_by_leg=fees,
        total_cost_cents=total_cost,
        guaranteed_profit_cents=profit,
        support=sum(value > 0 for value in checked_recipe),
        edge_bps_numerator=profit * 10_000,
        edge_bps_denominator=minimum_payout,
    )


def independently_verify_evaluation(
    legs: tuple[DisplayedLeg, ...], claimed: RecipeEvaluation
) -> bool:
    """Recompute a claimed result without calling the primary evaluator."""

    state_count = _validate_legs(legs)
    recipe = claimed.primitive_quantities
    if len(recipe) != len(legs) or any(type(value) is not int or value < 0 for value in recipe):
        return False
    claimed_integer_tuples = (
        claimed.five_copy_quantities,
        claimed.payoff_vector_cents,
        claimed.fee_cents_by_leg,
    )
    claimed_integer_scalars = (
        claimed.minimum_payout_cents,
        claimed.ask_cost_cents,
        claimed.total_cost_cents,
        claimed.guaranteed_profit_cents,
        claimed.support,
        claimed.edge_bps_numerator,
        claimed.edge_bps_denominator,
    )
    if any(type(value) is not int for values in claimed_integer_tuples for value in values):
        return False
    if any(type(value) is not int for value in claimed_integer_scalars):
        return False
    if not any(recipe):
        return False
    if _recipe_gcd(recipe) != 1:
        return False
    quantities = tuple(value * 5 for value in recipe)
    if quantities != claimed.five_copy_quantities:
        return False
    if any(quantity > leg.depth for quantity, leg in zip(quantities, legs, strict=True)):
        return False

    payouts: list[int] = []
    for state_index in range(state_count):
        state_payout = 0
        for leg_index, leg in enumerate(legs):
            state_payout += quantities[leg_index] * leg.payouts_cents[state_index]
        payouts.append(state_payout)
    fees: list[int] = []
    ask_cost = 0
    for leg_index, leg in enumerate(legs):
        quantity = quantities[leg_index]
        ask_cost += quantity * leg.ask_cents
        numerator = 7 * quantity * leg.ask_cents * (100 - leg.ask_cents)
        quotient, remainder = divmod(numerator, 10_000)
        fees.append(quotient + (1 if remainder else 0))
    minimum_payout = min(payouts)
    total_cost = ask_cost + sum(fees)
    profit = minimum_payout - total_cost
    expected = (
        tuple(payouts),
        minimum_payout,
        ask_cost,
        tuple(fees),
        total_cost,
        profit,
        sum(value > 0 for value in recipe),
        profit * 10_000,
        minimum_payout,
    )
    actual = (
        claimed.payoff_vector_cents,
        claimed.minimum_payout_cents,
        claimed.ask_cost_cents,
        claimed.fee_cents_by_leg,
        claimed.total_cost_cents,
        claimed.guaranteed_profit_cents,
        claimed.support,
        claimed.edge_bps_numerator,
        claimed.edge_bps_denominator,
    )
    return actual == expected and claimed.qualifies


def _recipe_gcd(recipe: tuple[int, ...]) -> int:
    return reduce(gcd, (value for value in recipe if value > 0))


def _normalized_payoff(payoff: tuple[int, ...]) -> tuple[int, ...]:
    divisor = reduce(gcd, (value for value in payoff if value > 0), 0)
    if divisor == 0:
        return payoff
    return tuple(value // divisor for value in payoff)


def find_v29_pair_explanations(
    legs: tuple[DisplayedLeg, ...],
) -> tuple[V29PairExplanation, ...]:
    """Find positive one-copy, two-leg full-coverage explanations."""

    state_count = _validate_legs(legs)
    explanations: list[V29PairExplanation] = []
    for first, second in combinations(range(len(legs)), 2):
        left = legs[first]
        right = legs[second]
        payoff = tuple(
            left.payouts_cents[index] + right.payouts_cents[index] for index in range(state_count)
        )
        minimum = min(payoff)
        cost = (
            left.ask_cents
            + right.ask_cents
            + standard_taker_fee_cents(1, left.ask_cents)
            + standard_taker_fee_cents(1, right.ask_cents)
        )
        profit = minimum - cost
        if minimum >= 100 and profit > 0:
            explanations.append(
                V29PairExplanation(
                    leg_indices=(first, second),
                    payoff_vector_cents=payoff,
                    minimum_payout_cents=minimum,
                    total_cost_cents=cost,
                    guaranteed_profit_cents=profit,
                )
            )
    return tuple(explanations)


def _representative(candidates: tuple[RecipeEvaluation, ...]) -> RecipeEvaluation | None:
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda item: (
            item.guaranteed_profit_cents,
            Fraction(item.edge_bps_numerator, item.edge_bps_denominator),
            -item.support,
            tuple(-value for value in item.primitive_quantities),
        ),
    )


def enumerate_primitive_recipes(
    legs: tuple[DisplayedLeg, ...],
    *,
    max_recipe_states: int = 2_000_000,
    max_audit_comparisons: int = 10_000_000,
) -> EnumerationResult:
    """Enumerate the complete bounded recipe grid or fail before returning any result."""

    state_count = _validate_legs(legs)
    max_recipe_states = _require_exact_int(max_recipe_states, "max_recipe_states")
    max_audit_comparisons = _require_exact_int(max_audit_comparisons, "max_audit_comparisons")
    if max_recipe_states < 1:
        raise DerivativesLatticeError("max_recipe_states must be positive")
    if max_audit_comparisons < 1:
        raise DerivativesLatticeError("max_audit_comparisons must be positive")
    limits = tuple(leg.depth // 5 for leg in legs)
    recipe_count = reduce(mul, (limit + 1 for limit in limits), 1) - 1
    if recipe_count > max_recipe_states:
        raise EnumerationIncompleteError(
            f"exact recipe grid has {recipe_count} states, above bound {max_recipe_states}"
        )
    audit_comparison_upper_bound = 3 * recipe_count * recipe_count
    if audit_comparison_upper_bound > max_audit_comparisons:
        raise EnumerationIncompleteError(
            "exact irreducibility audit has "
            f"{audit_comparison_upper_bound} worst-case comparisons, above bound "
            f"{max_audit_comparisons}"
        )

    all_evaluations: dict[tuple[int, ...], RecipeEvaluation] = {}
    qualifying: list[RecipeEvaluation] = []
    for recipe in product(*(range(limit + 1) for limit in limits)):
        if not any(recipe):
            continue
        evaluation = evaluate_five_copy_recipe(legs, recipe)
        all_evaluations[recipe] = evaluation
        if _recipe_gcd(recipe) == 1 and evaluation.qualifies:
            if not independently_verify_evaluation(legs, evaluation):
                raise DerivativesLatticeError("independent arithmetic verification failed")
            qualifying.append(evaluation)

    pair_explanations = find_v29_pair_explanations(legs)
    audits: list[CandidateAudit] = []
    collapsed: dict[tuple[tuple[int, ...], int], RecipeEvaluation] = {}
    for candidate in qualifying:
        recipe = candidate.primitive_quantities
        normalized_candidate_payoff = _normalized_payoff(candidate.payoff_vector_cents)
        support_two_relation_explanations = tuple(
            sorted(
                other_recipe
                for other_recipe, other in all_evaluations.items()
                if other.support <= 2
                and other.qualifies
                and _normalized_payoff(other.payoff_vector_cents) == normalized_candidate_payoff
            )
        )
        proper_subrecipes = tuple(
            sorted(
                other_recipe
                for other_recipe, other in all_evaluations.items()
                if other_recipe != recipe
                and all(
                    other_value <= value
                    for other_value, value in zip(other_recipe, recipe, strict=True)
                )
                and other.qualifies
            )
        )
        dominators = tuple(
            sorted(
                other_recipe
                for other_recipe, other in all_evaluations.items()
                if other.support < candidate.support
                and other.total_cost_cents <= candidate.total_cost_cents
                and all(
                    other_payout >= candidate_payout
                    for other_payout, candidate_payout in zip(
                        other.payoff_vector_cents,
                        candidate.payoff_vector_cents,
                        strict=True,
                    )
                )
            )
        )
        audit = CandidateAudit(
            evaluation=candidate,
            v29_pair_clear=not pair_explanations,
            support_greater_than_two=candidate.support > 2,
            support_two_relation_clear=not support_two_relation_explanations,
            proper_subrecipe_clear=not proper_subrecipes,
            dominance_clear=not dominators,
            support_two_relation_explanations=support_two_relation_explanations,
            proper_subrecipes=proper_subrecipes,
            dominating_recipes=dominators,
        )
        audits.append(audit)
        collapse_key = (normalized_candidate_payoff, candidate.total_cost_cents)
        if audit.incremental:
            existing = collapsed.get(collapse_key)
            if existing is None or _representative((existing, candidate)) == candidate:
                collapsed[collapse_key] = candidate

    incremental_tuple = tuple(collapsed.values())
    return EnumerationResult(
        state_count=state_count,
        recipe_count=recipe_count,
        audit_comparison_upper_bound=audit_comparison_upper_bound,
        qualifying_primitive_recipes=tuple(qualifying),
        pair_explanations=pair_explanations,
        audits=tuple(audits),
        incremental_candidates=incremental_tuple,
        snapshot_representative=_representative(incremental_tuple),
    )
