"""Exact atomic outcome cells for v34 derivative ladder arithmetic.

This module does not parse exchange prose. A later scanner must construct these
objects only after separately proving rule compatibility from archived bytes.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
from typing import Literal

Side = Literal["YES", "NO"]
DomainKind = Literal["continuous", "discrete"]
CellKind = Literal["left_tail", "point", "open_interval", "right_tail", "exception"]


class AtomicLatticeError(ValueError):
    """Raised when an exact atomic lattice cannot be constructed."""


def _require_exact_int(value: object, name: str) -> int:
    if type(value) is not int:
        raise AtomicLatticeError(f"{name} must be an exact integer")
    return value


def _decimal_text(value: Decimal) -> str:
    return format(value, "f")


@dataclass(frozen=True, slots=True)
class ThresholdPredicate:
    """A binary interval predicate over one exactly represented value."""

    lower: Decimal | None = None
    lower_inclusive: bool = False
    upper: Decimal | None = None
    upper_inclusive: bool = False

    def __post_init__(self) -> None:
        if self.lower is None and self.upper is None:
            raise AtomicLatticeError("a predicate needs at least one boundary")
        if self.lower is not None and type(self.lower) is not Decimal:
            raise AtomicLatticeError("lower must be Decimal")
        if self.upper is not None and type(self.upper) is not Decimal:
            raise AtomicLatticeError("upper must be Decimal")
        if self.lower is not None and not self.lower.is_finite():
            raise AtomicLatticeError("lower must be finite")
        if self.upper is not None and not self.upper.is_finite():
            raise AtomicLatticeError("upper must be finite")
        if type(self.lower_inclusive) is not bool or type(self.upper_inclusive) is not bool:
            raise AtomicLatticeError("inclusivity flags must be booleans")
        if self.lower is not None and self.upper is not None:
            if self.lower > self.upper:
                raise AtomicLatticeError("lower boundary exceeds upper boundary")
            if self.lower == self.upper and not (self.lower_inclusive and self.upper_inclusive):
                raise AtomicLatticeError("an equal-boundary predicate must include its singleton")

    def contains(self, value: Decimal) -> bool:
        if type(value) is not Decimal:
            raise AtomicLatticeError("predicate values must be Decimal")
        if not value.is_finite():
            raise AtomicLatticeError("predicate values must be finite")
        return self.contains_fraction(Fraction(value))

    def contains_fraction(self, value: Fraction) -> bool:
        """Evaluate against an exact rational without Decimal context rounding."""

        if type(value) is not Fraction:
            raise AtomicLatticeError("predicate values must be exact Fractions")
        lower = Fraction(self.lower) if self.lower is not None else None
        upper = Fraction(self.upper) if self.upper is not None else None
        if lower is not None and (value < lower or (value == lower and not self.lower_inclusive)):
            return False
        return not (
            upper is not None and (value > upper or (value == upper and not self.upper_inclusive))
        )


@dataclass(frozen=True, slots=True)
class AtomicCell:
    """One state on which every supplied threshold predicate is constant."""

    label: str
    kind: CellKind
    domain: DomainKind
    sample: Fraction | None
    exception_label: str | None = None

    def __post_init__(self) -> None:
        if not self.label:
            raise AtomicLatticeError("cell label cannot be empty")
        if self.domain not in ("continuous", "discrete"):
            raise AtomicLatticeError("cell domain must be continuous or discrete")
        if self.kind == "exception":
            if self.sample is not None or not self.exception_label:
                raise AtomicLatticeError("exception cells require only an exception label")
        elif type(self.sample) is not Fraction or self.exception_label is not None:
            raise AtomicLatticeError("ordinary cells require an exact Fraction sample")


@dataclass(frozen=True, slots=True)
class ExceptionalPayout:
    """Explicit cents payouts for one rule-defined exceptional state."""

    label: str
    yes_cents: int
    no_cents: int

    def __post_init__(self) -> None:
        if not self.label:
            raise AtomicLatticeError("exception label cannot be empty")
        yes_cents = _require_exact_int(self.yes_cents, "yes_cents")
        no_cents = _require_exact_int(self.no_cents, "no_cents")
        if not 0 <= yes_cents <= 100 or not 0 <= no_cents <= 100:
            raise AtomicLatticeError("exception payouts must be within 0 and 100 cents")


@dataclass(frozen=True, slots=True)
class BinaryContract:
    """A machine-verified predicate plus explicit exceptional payouts."""

    ticker: str
    predicate: ThresholdPredicate
    exceptional_payouts: tuple[ExceptionalPayout, ...] = ()

    def __post_init__(self) -> None:
        if not self.ticker:
            raise AtomicLatticeError("ticker cannot be empty")
        labels = [item.label for item in self.exceptional_payouts]
        if len(labels) != len(set(labels)):
            raise AtomicLatticeError("exception payout labels must be unique")


def build_atomic_cells(
    predicates: tuple[ThresholdPredicate, ...],
    *,
    domain: DomainKind,
    discrete_values: tuple[int, ...] = (),
    exception_labels: tuple[str, ...] = (),
) -> tuple[AtomicCell, ...]:
    """Construct the complete cells induced by exact threshold boundaries."""

    if not predicates:
        raise AtomicLatticeError("at least one predicate is required")
    if len(exception_labels) != len(set(exception_labels)) or any(
        not label for label in exception_labels
    ):
        raise AtomicLatticeError("exception labels must be nonempty and unique")

    cells: list[AtomicCell] = []
    if domain == "continuous":
        if discrete_values:
            raise AtomicLatticeError("continuous domains cannot declare discrete values")
        boundaries = sorted(
            {
                boundary
                for predicate in predicates
                for boundary in (predicate.lower, predicate.upper)
                if boundary is not None
            }
        )
        if not boundaries:
            raise AtomicLatticeError("continuous domains need at least one boundary")
        first = boundaries[0]
        first_fraction = Fraction(first)
        cells.append(
            AtomicCell(
                label=f"(-inf,{_decimal_text(first)})",
                kind="left_tail",
                domain=domain,
                sample=first_fraction - 1,
            )
        )
        for index, boundary in enumerate(boundaries):
            text = _decimal_text(boundary)
            cells.append(
                AtomicCell(
                    label=f"{{{text}}}",
                    kind="point",
                    domain=domain,
                    sample=Fraction(boundary),
                )
            )
            if index + 1 < len(boundaries):
                next_boundary = boundaries[index + 1]
                cells.append(
                    AtomicCell(
                        label=f"({text},{_decimal_text(next_boundary)})",
                        kind="open_interval",
                        domain=domain,
                        sample=(Fraction(boundary) + Fraction(next_boundary)) / 2,
                    )
                )
        last = boundaries[-1]
        cells.append(
            AtomicCell(
                label=f"({_decimal_text(last)},inf)",
                kind="right_tail",
                domain=domain,
                sample=Fraction(last) + 1,
            )
        )
    elif domain == "discrete":
        if not discrete_values:
            raise AtomicLatticeError("discrete domains require every possible integer value")
        checked = tuple(_require_exact_int(value, "discrete value") for value in discrete_values)
        if tuple(sorted(set(checked))) != checked:
            raise AtomicLatticeError("discrete values must be strictly increasing and unique")
        cells.extend(
            AtomicCell(label=f"{{{value}}}", kind="point", domain=domain, sample=Fraction(value))
            for value in checked
        )
    else:
        raise AtomicLatticeError(f"unsupported domain: {domain}")

    cells.extend(
        AtomicCell(
            label=f"exception:{label}",
            kind="exception",
            domain=domain,
            sample=None,
            exception_label=label,
        )
        for label in exception_labels
    )
    return tuple(cells)


def contract_payout_vector(
    contract: BinaryContract,
    cells: tuple[AtomicCell, ...],
    side: Side,
) -> tuple[int, ...]:
    """Evaluate one contract side on every exact atomic cell."""

    if side not in ("YES", "NO"):
        raise AtomicLatticeError("side must be YES or NO")
    if not cells:
        raise AtomicLatticeError("at least one atomic cell is required")
    if len({cell.label for cell in cells}) != len(cells):
        raise AtomicLatticeError("atomic cell labels must be unique")
    domains = {cell.domain for cell in cells}
    if len(domains) != 1:
        raise AtomicLatticeError("all atomic cells must share one domain")
    domain = next(iter(domains))
    ordinary_cells = tuple(cell for cell in cells if cell.kind != "exception")
    exception_cells = tuple(cell for cell in cells if cell.kind == "exception")
    if cells != ordinary_cells + exception_cells:
        raise AtomicLatticeError("exception cells must follow all ordinary cells")

    if domain == "continuous":
        point_boundaries = tuple(
            cell.sample
            for cell in ordinary_cells
            if cell.kind == "point" and cell.sample is not None
        )
        contract_boundaries = {
            Fraction(boundary)
            for boundary in (contract.predicate.lower, contract.predicate.upper)
            if boundary is not None
        }
        if not contract_boundaries.issubset(set(point_boundaries)):
            raise AtomicLatticeError("continuous cells omit a contract boundary")
        if not point_boundaries or tuple(sorted(set(point_boundaries))) != point_boundaries:
            raise AtomicLatticeError("continuous point boundaries must be increasing and unique")
        if len(ordinary_cells) != 2 * len(point_boundaries) + 1:
            raise AtomicLatticeError("continuous atomic cells are not canonically complete")
        left_tail = ordinary_cells[0]
        left_sample = left_tail.sample
        if (
            left_tail.kind != "left_tail"
            or left_sample is None
            or not left_sample < point_boundaries[0]
        ):
            raise AtomicLatticeError("continuous lattice has an invalid left tail")
        for index, boundary in enumerate(point_boundaries):
            point_cell = ordinary_cells[1 + 2 * index]
            if point_cell.kind != "point" or point_cell.sample != boundary:
                raise AtomicLatticeError("continuous lattice has an invalid boundary point")
            if index + 1 < len(point_boundaries):
                interval = ordinary_cells[2 + 2 * index]
                interval_sample = interval.sample
                if not (
                    interval.kind == "open_interval"
                    and interval_sample is not None
                    and boundary < interval_sample < point_boundaries[index + 1]
                ):
                    raise AtomicLatticeError("continuous lattice has an invalid open interval")
        right_tail = ordinary_cells[-1]
        right_sample = right_tail.sample
        if (
            right_tail.kind != "right_tail"
            or right_sample is None
            or not right_sample > point_boundaries[-1]
        ):
            raise AtomicLatticeError("continuous lattice has an invalid right tail")
    else:
        samples = tuple(cell.sample for cell in ordinary_cells)
        if any(
            cell.kind != "point" or sample is None
            for cell, sample in zip(ordinary_cells, samples, strict=True)
        ):
            raise AtomicLatticeError("discrete ordinary cells must all be points")
        exact_samples = tuple(sample for sample in samples if sample is not None)
        if any(sample.denominator != 1 for sample in exact_samples):
            raise AtomicLatticeError("discrete cell samples must be integers")
        if tuple(sorted(set(exact_samples))) != exact_samples:
            raise AtomicLatticeError("discrete cells must be strictly increasing and unique")
        if any(
            cell.label != f"{{{sample.numerator}}}"
            for cell, sample in zip(ordinary_cells, exact_samples, strict=True)
        ):
            raise AtomicLatticeError("discrete cell labels are not canonical")

    exception_map = {
        payout.label: payout.yes_cents if side == "YES" else payout.no_cents
        for payout in contract.exceptional_payouts
    }
    cell_exception_labels = {cell.exception_label for cell in exception_cells}
    if len(cell_exception_labels) != len(exception_cells):
        raise AtomicLatticeError("exception cells must have unique exception labels")
    if set(exception_map) != cell_exception_labels:
        raise AtomicLatticeError("exception payout labels must exactly match exception cells")

    payouts: list[int] = []
    for cell in cells:
        if cell.kind == "exception":
            if cell.exception_label is None:
                raise AtomicLatticeError("exception cell lost its label")
            payouts.append(exception_map[cell.exception_label])
            continue
        if cell.sample is None:
            raise AtomicLatticeError("ordinary cell lost its sample")
        yes_payout = 100 if contract.predicate.contains_fraction(cell.sample) else 0
        payouts.append(yes_payout if side == "YES" else 100 - yes_payout)
    return tuple(payouts)
