from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest
from scripts.v34.derivatives_atomic import (
    AtomicLatticeError,
    BinaryContract,
    ExceptionalPayout,
    ThresholdPredicate,
    build_atomic_cells,
    contract_payout_vector,
)


def test_continuous_cells_include_tails_boundaries_and_open_intervals() -> None:
    predicates = (
        ThresholdPredicate(lower=Decimal("10"), lower_inclusive=False),
        ThresholdPredicate(upper=Decimal("20"), upper_inclusive=True),
    )
    cells = build_atomic_cells(predicates, domain="continuous")
    assert [cell.label for cell in cells] == [
        "(-inf,10)",
        "{10}",
        "(10,20)",
        "{20}",
        "(20,inf)",
    ]


def test_inclusive_and_exclusive_strikes_differ_only_at_singleton() -> None:
    greater = BinaryContract(
        ticker="GT",
        predicate=ThresholdPredicate(lower=Decimal("10"), lower_inclusive=False),
    )
    greater_equal = BinaryContract(
        ticker="GE",
        predicate=ThresholdPredicate(lower=Decimal("10"), lower_inclusive=True),
    )
    cells = build_atomic_cells((greater.predicate, greater_equal.predicate), domain="continuous")
    assert contract_payout_vector(greater, cells, "YES") == (0, 0, 100)
    assert contract_payout_vector(greater_equal, cells, "YES") == (0, 100, 100)


def test_yes_and_no_are_complements_on_ordinary_cells() -> None:
    contract = BinaryContract(
        ticker="BAND",
        predicate=ThresholdPredicate(
            lower=Decimal("10"),
            lower_inclusive=True,
            upper=Decimal("20"),
            upper_inclusive=False,
        ),
    )
    cells = build_atomic_cells((contract.predicate,), domain="continuous")
    yes = contract_payout_vector(contract, cells, "YES")
    no = contract_payout_vector(contract, cells, "NO")
    assert tuple(left + right for left, right in zip(yes, no, strict=True)) == (100,) * 5
    assert yes == (0, 100, 100, 0, 0)


def test_discrete_domain_enumerates_every_declared_value() -> None:
    contract = BinaryContract(
        ticker="INT",
        predicate=ThresholdPredicate(lower=Decimal(2), lower_inclusive=True),
    )
    cells = build_atomic_cells(
        (contract.predicate,), domain="discrete", discrete_values=(0, 1, 2, 3)
    )
    assert [cell.label for cell in cells] == ["{0}", "{1}", "{2}", "{3}"]
    assert contract_payout_vector(contract, cells, "YES") == (0, 0, 100, 100)


def test_exceptional_payouts_are_explicit_and_need_not_be_complements() -> None:
    contract = BinaryContract(
        ticker="VOID",
        predicate=ThresholdPredicate(lower=Decimal(10), lower_inclusive=True),
        exceptional_payouts=(ExceptionalPayout("cancel", 50, 50),),
    )
    cells = build_atomic_cells(
        (contract.predicate,), domain="continuous", exception_labels=("cancel",)
    )
    assert contract_payout_vector(contract, cells, "YES")[-1] == 50
    assert contract_payout_vector(contract, cells, "NO")[-1] == 50


def test_missing_exception_payout_fails_closed() -> None:
    contract = BinaryContract(
        ticker="MISSING",
        predicate=ThresholdPredicate(lower=Decimal(10)),
    )
    cells = build_atomic_cells(
        (contract.predicate,), domain="continuous", exception_labels=("cancel",)
    )
    with pytest.raises(AtomicLatticeError, match="exactly match"):
        contract_payout_vector(contract, cells, "YES")


@pytest.mark.parametrize("bad", [(1, 1), (2, 0, 1), (True, 1, 2)])
def test_discrete_values_must_be_exact_strictly_increasing_integers(
    bad: tuple[object, ...],
) -> None:
    predicate = ThresholdPredicate(lower=Decimal(1))
    with pytest.raises(AtomicLatticeError):
        build_atomic_cells((predicate,), domain="discrete", discrete_values=bad)  # type: ignore[arg-type]


def test_equal_boundary_requires_an_included_singleton() -> None:
    with pytest.raises(AtomicLatticeError, match="singleton"):
        ThresholdPredicate(lower=Decimal(10), upper=Decimal(10))


def test_float_boundary_is_rejected() -> None:
    with pytest.raises(AtomicLatticeError, match="Decimal"):
        ThresholdPredicate(lower=10.0)  # type: ignore[arg-type]


def test_contract_boundary_omitted_from_continuous_cells_is_rejected() -> None:
    included = ThresholdPredicate(lower=Decimal(10))
    omitted = BinaryContract("OMITTED", ThresholdPredicate(lower=Decimal(20)))
    cells = build_atomic_cells((included,), domain="continuous")
    with pytest.raises(AtomicLatticeError, match="omit"):
        contract_payout_vector(omitted, cells, "YES")


def test_adjacent_high_precision_boundaries_use_an_exact_open_interval() -> None:
    lower = Decimal("1.0000000000000000000000000000")
    upper = Decimal("1.0000000000000000000000000001")
    contract = BinaryContract("TIGHT", ThresholdPredicate(lower=lower))
    cells = build_atomic_cells(
        (contract.predicate, ThresholdPredicate(lower=upper)), domain="continuous"
    )
    assert cells[2].sample != cells[1].sample
    assert contract_payout_vector(contract, cells, "YES") == (0, 0, 100, 100, 100)


def test_large_boundary_tail_sample_remains_strictly_outside() -> None:
    contract = BinaryContract(
        "HUGE", ThresholdPredicate(lower=Decimal("1e100"), lower_inclusive=True)
    )
    cells = build_atomic_cells((contract.predicate,), domain="continuous")
    assert cells[0].sample < cells[1].sample
    assert contract_payout_vector(contract, cells, "YES") == (0, 100, 100)


@pytest.mark.parametrize("value", [Decimal("Infinity"), Decimal("-Infinity"), Decimal("NaN")])
def test_nonfinite_boundaries_are_rejected(value: Decimal) -> None:
    with pytest.raises(AtomicLatticeError, match="finite"):
        ThresholdPredicate(lower=value)


def test_duplicate_exception_state_under_a_distinct_cell_label_is_rejected() -> None:
    contract = BinaryContract(
        "EXCEPTION",
        ThresholdPredicate(lower=Decimal(10)),
        (ExceptionalPayout("cancel", 50, 50),),
    )
    cells = build_atomic_cells(
        (contract.predicate,), domain="continuous", exception_labels=("cancel",)
    )
    duplicate = replace(cells[-1], label="exception:cancel-copy")
    with pytest.raises(AtomicLatticeError, match="unique exception"):
        contract_payout_vector(contract, cells + (duplicate,), "YES")
