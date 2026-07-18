from __future__ import annotations

from dataclasses import replace
from fractions import Fraction

import pytest
from scripts.v34.derivatives_certificate import (
    StatePriceCertificateError,
    certificate_from_exact_weights,
    propose_exact_state_price_certificate,
    verify_state_price_certificate,
)
from scripts.v34.derivatives_lattice import DisplayedLeg


def _partition(ask: int) -> tuple[DisplayedLeg, ...]:
    return (
        DisplayedLeg("A", "YES", ask, 5, (100, 0, 0)),
        DisplayedLeg("B", "YES", ask, 5, (0, 100, 0)),
        DisplayedLeg("C", "YES", ask, 5, (0, 0, 100)),
    )


def test_exact_state_prices_certify_a_nonarbitrage_partition() -> None:
    legs = _partition(40)
    certificate = propose_exact_state_price_certificate(legs)
    assert certificate is not None
    assert verify_state_price_certificate(legs, certificate) is True
    assert certificate.minimum_slack_cents >= 0
    assert sum(certificate.state_weights, Fraction(0)) == 1


def test_profitable_partition_has_no_state_price_certificate() -> None:
    assert propose_exact_state_price_certificate(_partition(30)) is None


def test_complement_spread_has_an_exact_certificate() -> None:
    legs = (
        DisplayedLeg("M", "YES", 60, 5, (0, 100)),
        DisplayedLeg("M", "NO", 50, 5, (100, 0)),
    )
    certificate = propose_exact_state_price_certificate(legs)
    assert certificate is not None
    assert verify_state_price_certificate(legs, certificate) is True
    assert certificate.expected_payout_cents_by_leg[0] <= 60
    assert certificate.expected_payout_cents_by_leg[1] <= 50


def test_certificate_proves_every_nonnegative_basket_is_not_fee_free_arbitrage() -> None:
    legs = _partition(40)
    certificate = propose_exact_state_price_certificate(legs)
    assert certificate is not None
    for quantities in ((1, 1, 1), (2, 3, 5), (0, 7, 1)):
        state_payouts = tuple(
            sum(
                quantity * leg.payouts_cents[state]
                for quantity, leg in zip(quantities, legs, strict=True)
            )
            for state in range(3)
        )
        ask_cost = sum(
            quantity * leg.ask_cents for quantity, leg in zip(quantities, legs, strict=True)
        )
        assert min(state_payouts) <= ask_cost


def test_exact_exceptional_state_can_carry_certificate_mass() -> None:
    legs = (
        DisplayedLeg("A", "YES", 70, 5, (0, 100, 50)),
        DisplayedLeg("A", "NO", 70, 5, (100, 0, 50)),
    )
    certificate = certificate_from_exact_weights(
        legs,
        (Fraction(0), Fraction(0), Fraction(1)),
        construction_denominator=1,
    )
    assert verify_state_price_certificate(legs, certificate) is True
    assert certificate.expected_payout_cents_by_leg == (50, 50)


def test_tampered_expected_value_or_slack_is_rejected() -> None:
    legs = _partition(40)
    certificate = propose_exact_state_price_certificate(legs)
    assert certificate is not None
    assert (
        verify_state_price_certificate(
            legs,
            replace(
                certificate,
                expected_payout_cents_by_leg=(Fraction(0),) * len(legs),
            ),
        )
        is False
    )
    assert (
        verify_state_price_certificate(
            legs,
            replace(certificate, minimum_slack_cents=certificate.minimum_slack_cents + 1),
        )
        is False
    )


def test_negative_or_nonunit_weights_are_rejected() -> None:
    legs = _partition(40)
    with pytest.raises(StatePriceCertificateError, match="sum to one"):
        certificate_from_exact_weights(
            legs,
            (Fraction(1), Fraction(1), Fraction(-1)),
            construction_denominator=1,
        )
    with pytest.raises(StatePriceCertificateError, match="sum to one"):
        certificate_from_exact_weights(
            legs,
            (Fraction(1, 4),) * 3,
            construction_denominator=4,
        )


def test_exact_weights_that_violate_an_ask_are_not_a_certificate() -> None:
    legs = _partition(30)
    with pytest.raises(StatePriceCertificateError, match="ask inequality"):
        certificate_from_exact_weights(
            legs,
            (Fraction(1, 3), Fraction(1, 3), Fraction(1, 3)),
            construction_denominator=3,
        )


def test_float_weights_and_boolean_denominators_are_rejected() -> None:
    legs = _partition(40)
    with pytest.raises(StatePriceCertificateError, match="Fractions"):
        certificate_from_exact_weights(
            legs,
            (0.25, 0.25, 0.5),  # type: ignore[arg-type]
            construction_denominator=4,
        )
    with pytest.raises(StatePriceCertificateError, match="exact integer"):
        propose_exact_state_price_certificate(legs, max_denominator=True)


def test_tampered_boolean_denominator_is_rejected_by_verifier() -> None:
    legs = _partition(40)
    certificate = propose_exact_state_price_certificate(legs)
    assert certificate is not None
    assert (
        verify_state_price_certificate(legs, replace(certificate, construction_denominator=True))
        is False
    )


def test_tampered_boolean_exact_fields_and_false_denominator_metadata_are_rejected() -> None:
    legs = _partition(40)
    certificate = propose_exact_state_price_certificate(legs)
    assert certificate is not None
    assert (
        verify_state_price_certificate(
            legs,
            replace(
                certificate,
                expected_payout_cents_by_leg=(True,) + certificate.expected_payout_cents_by_leg[1:],
            ),
        )
        is False
    )
    if any(weight.denominator > 1 for weight in certificate.state_weights):
        assert (
            verify_state_price_certificate(legs, replace(certificate, construction_denominator=1))
            is False
        )


def test_exact_constructor_rejects_false_common_denominator_metadata() -> None:
    legs = _partition(40)
    with pytest.raises(StatePriceCertificateError, match="common multiple"):
        certificate_from_exact_weights(
            legs,
            (Fraction(1, 3), Fraction(1, 3), Fraction(1, 3)),
            construction_denominator=1,
        )


def test_verifier_is_total_on_structurally_malformed_sequence_fields() -> None:
    legs = _partition(40)
    certificate = propose_exact_state_price_certificate(legs)
    assert certificate is not None
    assert (
        verify_state_price_certificate(
            legs,
            replace(certificate, state_weights=None),  # type: ignore[arg-type]
        )
        is False
    )
    assert (
        verify_state_price_certificate(
            legs,
            replace(certificate, slack_cents_by_leg=None),  # type: ignore[arg-type]
        )
        is False
    )


def test_proposal_denominator_has_a_hard_resource_bound() -> None:
    with pytest.raises(StatePriceCertificateError, match="hard bound"):
        propose_exact_state_price_certificate(_partition(40), max_denominator=1_000_001)
