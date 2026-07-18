from __future__ import annotations

from dataclasses import replace

import pytest
from scripts.v34.derivatives_lattice import (
    DerivativesLatticeError,
    DisplayedLeg,
    EnumerationIncompleteError,
    enumerate_primitive_recipes,
    evaluate_five_copy_recipe,
    independently_verify_evaluation,
    standard_taker_fee_cents,
)


def _partition_legs(*, ask: int = 30, depth: int = 5) -> tuple[DisplayedLeg, ...]:
    return (
        DisplayedLeg("A", "YES", ask, depth, (100, 0, 0)),
        DisplayedLeg("B", "YES", ask, depth, (0, 100, 0)),
        DisplayedLeg("C", "YES", ask, depth, (0, 0, 100)),
    )


def test_standard_fee_uses_exact_aggregate_ceiling() -> None:
    assert standard_taker_fee_cents(1, 30) == 2
    assert standard_taker_fee_cents(5, 30) == 8
    assert standard_taker_fee_cents(0, 30) == 0


def test_three_leg_partition_above_one_dollar_is_incremental() -> None:
    result = enumerate_primitive_recipes(_partition_legs())
    candidate = result.snapshot_representative
    assert result.recipe_count == 7
    assert result.pair_explanations == ()
    assert candidate is not None
    assert candidate.primitive_quantities == (1, 1, 1)
    assert candidate.total_cost_cents == 474
    assert candidate.minimum_payout_cents == 500
    assert candidate.guaranteed_profit_cents == 26
    assert candidate.qualifies is True
    assert independently_verify_evaluation(_partition_legs(), candidate) is True


def test_nonprofitable_monotonic_ladder_has_no_candidate() -> None:
    legs = (
        DisplayedLeg("GT10", "YES", 55, 5, (0, 0, 100, 100, 100)),
        DisplayedLeg("GT20", "NO", 55, 5, (100, 100, 100, 0, 0)),
        DisplayedLeg("MID", "YES", 20, 5, (0, 0, 100, 0, 0)),
    )
    result = enumerate_primitive_recipes(legs)
    assert result.incremental_candidates == ()


def test_insufficient_fifth_copy_depth_prevents_recipe_use() -> None:
    legs = _partition_legs(depth=4)
    result = enumerate_primitive_recipes(legs)
    assert result.recipe_count == 0
    assert result.qualifying_primitive_recipes == ()


def test_pair_explanation_prevents_incremental_lattice_claim() -> None:
    legs = (
        DisplayedLeg("LOW", "YES", 45, 5, (100, 0)),
        DisplayedLeg("HIGH", "YES", 45, 5, (0, 100)),
        DisplayedLeg("PAD", "YES", 1, 5, (0, 0)),
    )
    result = enumerate_primitive_recipes(legs)
    assert len(result.pair_explanations) == 1
    assert result.incremental_candidates == ()


def test_profitable_proper_subrecipe_rejects_padding() -> None:
    legs = _partition_legs() + (DisplayedLeg("PAD", "YES", 1, 5, (100, 100, 100)),)
    result = enumerate_primitive_recipes(legs)
    padded = next(
        audit for audit in result.audits if audit.evaluation.primitive_quantities == (1, 1, 1, 1)
    )
    assert padded.proper_subrecipe_clear is False
    assert (1, 1, 1, 0) in padded.proper_subrecipes
    assert padded.incremental is False


def test_lower_support_dominance_is_published() -> None:
    legs = _partition_legs() + (DisplayedLeg("DOM", "YES", 90, 5, (100, 100, 100)),)
    result = enumerate_primitive_recipes(legs)
    partition = next(
        audit for audit in result.audits if audit.evaluation.primitive_quantities == (1, 1, 1, 0)
    )
    assert partition.dominance_clear is False
    assert (0, 0, 0, 1) in partition.dominating_recipes


def test_unequal_quantity_support_two_payoff_relation_is_published_and_rejected() -> None:
    legs = _partition_legs() + (
        DisplayedLeg("PAIR_A", "YES", 68, 5, (100, 100, 0)),
        DisplayedLeg("PAIR_B", "YES", 12, 10, (0, 0, 50)),
    )
    result = enumerate_primitive_recipes(legs)
    three_leg = next(
        audit for audit in result.audits if audit.evaluation.primitive_quantities == (1, 1, 1, 0, 0)
    )
    assert result.pair_explanations == ()
    assert three_leg.dominance_clear is True
    assert three_leg.proper_subrecipe_clear is True
    assert three_leg.support_two_relation_clear is False
    assert (0, 0, 0, 1, 2) in three_leg.support_two_relation_explanations
    assert three_leg.incremental is False


def test_economically_equivalent_recipes_collapse_across_distinct_legs() -> None:
    first = _partition_legs()
    second = tuple(replace(leg, market_ticker=f"{leg.market_ticker}2") for leg in _partition_legs())
    result = enumerate_primitive_recipes(first + second)
    equivalent_audits = [
        audit
        for audit in result.audits
        if audit.incremental
        and audit.evaluation.payoff_vector_cents == (500, 500, 500)
        and audit.evaluation.total_cost_cents == 474
    ]
    equivalent_candidates = [
        candidate
        for candidate in result.incremental_candidates
        if candidate.payoff_vector_cents == (500, 500, 500) and candidate.total_cost_cents == 474
    ]
    assert len(equivalent_audits) > 1
    assert len(equivalent_candidates) == 1


def test_edge_threshold_is_enforced_during_complete_enumeration() -> None:
    passing_partition = _partition_legs()
    low_edge_guarantee = DisplayedLeg("LOWEDGE", "YES", 98, 5, (100, 100, 100))
    result = enumerate_primitive_recipes(passing_partition + (low_edge_guarantee,))
    low_edge = evaluate_five_copy_recipe(passing_partition + (low_edge_guarantee,), (0, 0, 0, 1))
    assert low_edge.guaranteed_profit_cents > 0
    assert low_edge.qualifies is False
    assert any(
        item.primitive_quantities == (1, 1, 1, 0) for item in result.qualifying_primitive_recipes
    )


def test_nonprimitive_multiples_are_not_reported_as_recipes() -> None:
    legs = tuple(replace(leg, depth=10) for leg in _partition_legs())
    result = enumerate_primitive_recipes(legs)
    assert all(
        item.primitive_quantities != (2, 2, 2) for item in result.qualifying_primitive_recipes
    )


def test_enumeration_bound_fails_before_partial_results() -> None:
    legs = tuple(replace(leg, depth=500) for leg in _partition_legs())
    with pytest.raises(EnumerationIncompleteError, match="above bound"):
        enumerate_primitive_recipes(legs, max_recipe_states=100)


def test_irreducibility_work_bound_fails_before_quadratic_audit() -> None:
    legs = tuple(DisplayedLeg(f"LEG{index}", "YES", 99, 5, (100,)) for index in range(11))
    with pytest.raises(EnumerationIncompleteError, match="irreducibility audit"):
        enumerate_primitive_recipes(legs)


def test_bool_and_float_numeric_aliases_are_rejected() -> None:
    with pytest.raises(DerivativesLatticeError, match="exact integer"):
        standard_taker_fee_cents(True, 30)
    with pytest.raises(DerivativesLatticeError, match="exact integer"):
        DisplayedLeg("BAD", "YES", 30.0, 5, (100,))  # type: ignore[arg-type]


def test_duplicate_displayed_leg_identity_is_rejected() -> None:
    legs = (
        DisplayedLeg("SAME", "YES", 30, 5, (100, 0)),
        DisplayedLeg("SAME", "YES", 40, 5, (0, 100)),
    )
    with pytest.raises(DerivativesLatticeError, match="identities"):
        enumerate_primitive_recipes(legs)


def test_independent_verifier_rejects_tampered_arithmetic() -> None:
    legs = _partition_legs()
    evaluation = evaluate_five_copy_recipe(legs, (1, 1, 1))
    tampered = replace(evaluation, total_cost_cents=evaluation.total_cost_cents - 1)
    assert independently_verify_evaluation(legs, tampered) is False


def test_independent_verifier_rejects_nonprimitive_recipe() -> None:
    legs = tuple(replace(leg, depth=10) for leg in _partition_legs())
    evaluation = evaluate_five_copy_recipe(legs, (2, 2, 2))
    assert independently_verify_evaluation(legs, evaluation) is False


def test_independent_verifier_rejects_bool_integer_aliases() -> None:
    legs = _partition_legs()
    evaluation = evaluate_five_copy_recipe(legs, (1, 1, 1))
    assert independently_verify_evaluation(legs, replace(evaluation, support=True)) is False
    assert (
        independently_verify_evaluation(legs, replace(evaluation, fee_cents_by_leg=(True, 8, 8)))
        is False
    )


def test_mismatched_atomic_cell_counts_are_rejected() -> None:
    legs = (
        DisplayedLeg("A", "YES", 30, 5, (100, 0)),
        DisplayedLeg("B", "YES", 30, 5, (0, 100, 0)),
    )
    with pytest.raises(DerivativesLatticeError, match="same atomic cells"):
        enumerate_primitive_recipes(legs)
