from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from scripts.v34 import decision_commit as commit
from scripts.v34 import policy
from scripts.v34 import prefix_dependency as prefix

BASE = datetime(2026, 7, 18, tzinfo=UTC)
SOURCE_HASHES = {
    source_name: hashlib.sha256(
        (policy.REPOSITORY_ROOT / source_name).read_bytes()
    ).hexdigest()
    for source_name in sorted(policy.REQUIRED_LAUNCH_SOURCES)
}
LAUNCH_MANIFEST_BYTES = policy.canonical_json_bytes(
    {
        "created_at": "2026-07-18T00:00:00+00:00",
        "launch_nonce": "v34-launch-test-nonce",
        "manifest_kind": "v34_feed_launch",
        "output_root": policy.FEED_OUTPUT_ROOT,
        "policy_sha256": policy.POLICY_CANONICAL_SHA256,
        "run_signature": policy.FEED_RUN_SIGNATURE,
        "schema_version": policy.FEED_SCHEMA_VERSION,
        "source_hashes": SOURCE_HASHES,
    }
)
LAUNCH_ANCHOR = policy.verify_feed_launch_manifest_bytes(LAUNCH_MANIFEST_BYTES)
PROVENANCE: dict[str, object] = LAUNCH_ANCHOR.provenance
QUEUE_SOURCE_HASHES = {
    source_name: hashlib.sha256(
        (policy.REPOSITORY_ROOT / source_name).read_bytes()
    ).hexdigest()
    for source_name in sorted(policy.REQUIRED_QUEUE_LAUNCH_SOURCES)
}
QUEUE_LAUNCH_MANIFEST_BYTES = policy.canonical_json_bytes(
    {
        "created_at": "2026-07-18T00:00:00+00:00",
        "launch_nonce": "v34-prefix-queue-test-nonce",
        "manifest_kind": "v34_queue_launch",
        "output_root": policy.QUEUE_OUTPUT_ROOT,
        "policy_sha256": policy.POLICY_CANONICAL_SHA256,
        "run_signature": policy.QUEUE_RUN_SIGNATURE,
        "schema_version": policy.QUEUE_SCHEMA_VERSION,
        "source_hashes": QUEUE_SOURCE_HASHES,
    }
)
QUEUE_LAUNCH_ANCHOR = policy.verify_queue_launch_manifest_bytes(
    QUEUE_LAUNCH_MANIFEST_BYTES
)
QUEUE_PROVENANCE: dict[str, object] = QUEUE_LAUNCH_ANCHOR.provenance


def archived_feed_pair(
    generation: str,
    state_bytes: bytes | None = None,
) -> commit.ArchivedFeedPair:
    summary: dict[str, object] = {
        **PROVENANCE,
        "generation_id": generation,
        "marker": "test",
    }
    if state_bytes is not None:
        state = json.loads(state_bytes)
        if not isinstance(state, dict):
            raise TypeError("Test game state must be an object")
        summary["game_states"] = {"824999": state}
    summary_bytes = policy.canonical_json_bytes(summary)
    feed_receipt_bytes = policy.canonical_json_bytes(
        {
            **PROVENANCE,
            "generation_id": generation,
            "summary_sha256": hashlib.sha256(summary_bytes).hexdigest(),
        }
    )
    archive_receipt_bytes = policy.canonical_json_bytes(
        {
            **PROVENANCE,
            "archive_id": f"archive-{generation}",
            "feed_receipt_sha256": hashlib.sha256(
                feed_receipt_bytes
            ).hexdigest(),
            "generation_id": generation,
            "queue_provenance": QUEUE_PROVENANCE,
            "summary_sha256": hashlib.sha256(summary_bytes).hexdigest(),
        }
    )
    return commit.ArchivedFeedPair(
        generation_id=generation,
        summary_bytes=summary_bytes,
        feed_receipt_bytes=feed_receipt_bytes,
        archive_receipt_bytes=archive_receipt_bytes,
    )


def play(
    index: int,
    *,
    away: int,
    home: int,
    end_seconds: int,
    complete: bool = True,
    has_review: bool = False,
    review: object = None,
) -> dict[str, object]:
    return {
        "about": {
            "atBatIndex": index,
            "endTime": (BASE + timedelta(seconds=end_seconds)).isoformat(),
            "hasReview": has_review,
            "isComplete": complete,
            "isScoringPlay": away + home > 0,
        },
        "result": {
            "awayScore": away,
            "description": f"play {index}",
            "event": "Single",
            "eventType": "single",
            "homeScore": home,
            "rbi": max(0, away + home),
        },
        "review_details": review,
    }


def plays() -> dict[str, object]:
    return {
        "0": play(0, away=0, home=0, end_seconds=4),
        "1": play(1, away=2, home=0, end_seconds=8),
    }


def basis() -> prefix.TriggerBasis:
    return prefix.build_trigger_basis(
        plays(),
        game_pk=824999,
        trigger_at_bat_index=1,
        t_seen=BASE + timedelta(seconds=10),
        eligible_at=BASE + timedelta(seconds=71),
    )


def archived_state(
    generation: str,
    current: dict[str, object],
    *,
    observed_seconds: int,
    total: int = 2,
    archive_id: str = "archive-a",
    provenance: dict[str, object] = PROVENANCE,
) -> prefix.ArchivedGameState:
    state = {
        **provenance,
        "abstract_state": "Live",
        "completed_plays": current,
        "detailed_state": "In Progress",
        "game_pk": 824999,
        "generation_id": generation,
        "observed_at": (BASE + timedelta(seconds=observed_seconds)).isoformat(),
        "official_current_total": total,
    }
    state_bytes = policy.canonical_json_bytes(state)
    parent_pair = archived_feed_pair(generation, state_bytes)
    receipt = {
        **provenance,
        "archive_id": archive_id,
        "feed_archive_receipt_sha256": parent_pair.archive_receipt_sha256,
        "feed_summary_sha256": parent_pair.summary_sha256,
        "game_pk": 824999,
        "generation_id": generation,
        "observed_at": state["observed_at"],
        "state_sha256": hashlib.sha256(state_bytes).hexdigest(),
    }
    return prefix.ArchivedGameState(
        generation_id=generation,
        game_pk=824999,
        state_bytes=state_bytes,
        archive_receipt_bytes=policy.canonical_json_bytes(receipt),
    )


def archived_opportunity(
    frozen: prefix.TriggerBasis,
    *,
    threshold: str = "1.5",
    market_ticker: str = "KXMLBTOTAL-TEST-1",
    generation: str = "generation-1",
    provenance: dict[str, object] = PROVENANCE,
    queue_provenance: dict[str, object] = QUEUE_PROVENANCE,
) -> prefix.ArchivedQueueOpportunity:
    parent_state = archived_state(
        generation,
        plays(),
        observed_seconds=71,
        provenance=provenance,
    )
    parent_pair = archived_feed_pair(generation, parent_state.state_bytes)
    opportunity = {
        **provenance,
        "eligible_at": frozen.eligible_at,
        "feed_archive_receipt_sha256": parent_pair.archive_receipt_sha256,
        "feed_generation_id": generation,
        "feed_summary_sha256": parent_pair.summary_sha256,
        "game_pk": frozen.game_pk,
        "market_ticker": market_ticker,
        "ordered_prefix_fingerprint": frozen.ordered_prefix_fingerprint,
        "post_total": frozen.post_total,
        "pre_total": frozen.pre_total,
        "queue_provenance": queue_provenance,
        "run_delta": frozen.run_delta,
        "threshold": threshold,
        "trigger_at_bat_index": frozen.trigger_at_bat_index,
        "trigger_play_identity": frozen.trigger_play_identity,
        "t_seen": frozen.t_seen,
    }
    opportunity_bytes = policy.canonical_json_bytes(opportunity)
    receipt = {
        **provenance,
        "archive_id": "opportunity-archive-a",
        "feed_archive_receipt_sha256": opportunity[
            "feed_archive_receipt_sha256"
        ],
        "feed_generation_id": generation,
        "feed_summary_sha256": opportunity["feed_summary_sha256"],
        "game_pk": frozen.game_pk,
        "opportunity_sha256": hashlib.sha256(opportunity_bytes).hexdigest(),
        "queue_provenance": queue_provenance,
    }
    return prefix.ArchivedQueueOpportunity(
        opportunity_bytes=opportunity_bytes,
        archive_receipt_bytes=policy.canonical_json_bytes(receipt),
    )


def exercise_credit(
    frozen: prefix.TriggerBasis,
    *,
    revised_at_bat_index: int,
    before_archive: prefix.ArchivedGameState,
    after_archive: prefix.ArchivedGameState,
    opportunity_archive: prefix.ArchivedQueueOpportunity,
    expected_feed_launch: policy.FeedLaunchAnchor = LAUNCH_ANCHOR,
    expected_queue_launch: policy.QueueLaunchAnchor = QUEUE_LAUNCH_ANCHOR,
    before_feed_pair: commit.ArchivedFeedPair | None = None,
    after_feed_pair: commit.ArchivedFeedPair | None = None,
) -> bool:
    return prefix.exact_end_time_exercise_credits(
        frozen,
        revised_at_bat_index=revised_at_bat_index,
        before_feed_pair=before_feed_pair
        or archived_feed_pair(
            before_archive.generation_id,
            before_archive.state_bytes,
        ),
        after_feed_pair=after_feed_pair
        or archived_feed_pair(
            after_archive.generation_id,
            after_archive.state_bytes,
        ),
        before_archive=before_archive,
        after_archive=after_archive,
        opportunity_archive=opportunity_archive,
        expected_feed_launch=expected_feed_launch,
        expected_queue_launch=expected_queue_launch,
    )


def revalidate(
    frozen: prefix.TriggerBasis,
    current: dict[str, object],
    *,
    total: int = 2,
    observed_seconds: int = 100,
) -> prefix.PrefixSnapshot:
    return prefix.revalidate_trigger_basis(
        frozen,
        current,
        official_current_total=total,
        abstract_state="Live",
        detailed_state="In Progress",
        observed_at=BASE + timedelta(seconds=observed_seconds),
    )


def test_policy_hash_is_the_reviewed_schema_two_lock() -> None:
    assert policy.PRIMARY_POLICY["schema_version"] == 2
    assert (
        policy.POLICY_CANONICAL_SHA256
        == "6c85a6a901fd0f4c0eb639869b0f43bf438e24c5ea1f7739827e81c6361b80d0"
    )


def test_build_and_revalidate_exact_prefix() -> None:
    frozen = basis()
    assert frozen.pre_total == 0
    assert frozen.post_total == 2
    assert frozen.run_delta == 2
    snapshot = revalidate(frozen, plays())
    assert snapshot.prefix_fingerprint == frozen.ordered_prefix_fingerprint


def test_later_suffix_change_does_not_taint_an_exact_prefix() -> None:
    current = plays()
    current["2"] = play(
        2, away=2, home=0, end_seconds=80, complete=False, has_review=True
    )
    assert revalidate(basis(), current).post_total == 2


def test_masked_regression_in_earlier_prefix_play_is_fatal() -> None:
    current = plays()
    current["0"] = play(0, away=1, home=0, end_seconds=4)
    with pytest.raises(ValueError, match="prefix or identity changed"):
        revalidate(basis(), current, total=8)


def test_component_score_regression_is_fatal_even_if_total_increases() -> None:
    current = {
        "0": play(0, away=1, home=0, end_seconds=4),
        "1": play(1, away=0, home=2, end_seconds=8),
    }
    with pytest.raises(ValueError, match="score path regressed"):
        prefix.reconstruct_prefix(
            current,
            game_pk=824999,
            trigger_at_bat_index=1,
            t_seen=BASE + timedelta(seconds=10),
            observed_at=BASE + timedelta(seconds=100),
        )


def test_score_redistribution_with_same_trigger_post_total_is_fatal() -> None:
    current = plays()
    current["0"] = play(0, away=0, home=1, end_seconds=4)
    current["1"] = play(1, away=1, home=1, end_seconds=8)
    with pytest.raises(ValueError, match="prefix or identity changed"):
        revalidate(basis(), current, total=9)


def test_missing_reordered_and_transient_incomplete_prefix_are_fatal() -> None:
    missing = plays()
    del missing["0"]
    with pytest.raises(ValueError, match="missing"):
        revalidate(basis(), missing)

    reordered = plays()
    reordered["0"] = play(1, away=0, home=0, end_seconds=4)
    with pytest.raises(ValueError, match="identity is duplicated"):
        revalidate(basis(), reordered)

    incomplete = plays()
    incomplete["1"] = play(1, away=2, home=0, end_seconds=8, complete=False)
    with pytest.raises(ValueError, match="not complete"):
        revalidate(basis(), incomplete)

    duplicate_alias = plays()
    duplicate_alias["01"] = copy.deepcopy(duplicate_alias["1"])
    with pytest.raises(ValueError, match="not canonical"):
        revalidate(basis(), duplicate_alias)

    duplicate_suffix = plays()
    duplicate_suffix["2"] = play(1, away=2, home=0, end_seconds=20)
    with pytest.raises(ValueError, match="identity is duplicated"):
        revalidate(basis(), duplicate_suffix)


def test_unknown_projection_field_is_fatal() -> None:
    current = plays()
    changed = copy.deepcopy(current["1"])
    assert isinstance(changed, dict)
    changed["unknown"] = True
    current["1"] = changed
    with pytest.raises(ValueError, match="top-level keys differ"):
        revalidate(basis(), current)


def test_review_change_is_fatal_even_when_score_is_unchanged() -> None:
    current = plays()
    current["0"] = play(
        0,
        away=0,
        home=0,
        end_seconds=4,
        has_review=True,
        review={"isOverturned": False},
    )
    with pytest.raises(ValueError, match="prefix or identity changed"):
        revalidate(basis(), current)


def test_current_total_floor_and_status_are_fatal() -> None:
    with pytest.raises(ValueError, match="below frozen"):
        revalidate(basis(), plays(), total=1)
    with pytest.raises(ValueError, match="abstract"):
        prefix.revalidate_trigger_basis(
            basis(),
            plays(),
            official_current_total=2,
            abstract_state="Preview",
            detailed_state="Scheduled",
            observed_at=BASE + timedelta(seconds=100),
        )


def test_revalidation_cannot_precede_immutable_eligibility() -> None:
    with pytest.raises(ValueError, match="precedes immutable eligibility"):
        revalidate(basis(), plays(), observed_seconds=70)
    with pytest.raises(ValueError, match="detailed"):
        prefix.revalidate_trigger_basis(
            basis(),
            plays(),
            official_current_total=2,
            abstract_state="Live",
            detailed_state="Game Suspended",
            observed_at=BASE + timedelta(seconds=100),
        )


def test_crossing_reconstruction_is_exact() -> None:
    frozen = basis()
    assert prefix.crossing_holds(frozen, "0")
    assert prefix.crossing_holds(frozen, "1.5")
    assert not prefix.crossing_holds(frozen, "2")
    assert not prefix.crossing_holds(frozen, "-0.5")


def test_posteligibility_in_prefix_endtime_only_exercise_credits() -> None:
    frozen = basis()
    before = plays()
    current = plays()
    after = play(1, away=2, home=0, end_seconds=9)
    current["1"] = after
    assert exercise_credit(
        frozen,
        revised_at_bat_index=1,
        before_archive=archived_state(
            "generation-1", before, observed_seconds=71
        ),
        after_archive=archived_state(
            "generation-2", current, observed_seconds=100
        ),
        opportunity_archive=archived_opportunity(frozen),
        expected_feed_launch=LAUNCH_ANCHOR,
    )


def test_preeligibility_suffix_mixed_and_unbound_revision_do_not_credit() -> None:
    frozen = basis()
    before = plays()
    current = plays()
    selected_after = play(1, away=2, home=0, end_seconds=9)
    current["1"] = selected_after
    before_too_early = archived_state(
        "generation-1", before, observed_seconds=70
    )
    after_archive = archived_state(
        "generation-2", current, observed_seconds=100
    )
    assert not exercise_credit(
        frozen,
        revised_at_bat_index=1,
        before_archive=before_too_early,
        after_archive=after_archive,
        opportunity_archive=archived_opportunity(frozen),
        expected_feed_launch=LAUNCH_ANCHOR,
    )
    valid_before = archived_state(
        "generation-1", before, observed_seconds=71
    )
    assert not exercise_credit(
        frozen,
        revised_at_bat_index=2,
        before_archive=valid_before,
        after_archive=after_archive,
        opportunity_archive=archived_opportunity(frozen),
        expected_feed_launch=LAUNCH_ANCHOR,
    )
    mixed = copy.deepcopy(selected_after)
    assert isinstance(mixed, dict)
    result = mixed["result"]
    assert isinstance(result, dict)
    result["description"] = "edited"
    assert not exercise_credit(
        frozen,
        revised_at_bat_index=1,
        before_archive=valid_before,
        after_archive=archived_state(
            "generation-2", {**plays(), "1": mixed}, observed_seconds=100
        ),
        opportunity_archive=archived_opportunity(frozen),
        expected_feed_launch=LAUNCH_ANCHOR,
    )
    invalid_before = replace(valid_before, archive_receipt_bytes=b"{}")
    assert not exercise_credit(
        frozen,
        revised_at_bat_index=1,
        before_archive=invalid_before,
        after_archive=after_archive,
        opportunity_archive=archived_opportunity(frozen),
        expected_feed_launch=LAUNCH_ANCHOR,
    )
    assert not exercise_credit(
        frozen,
        revised_at_bat_index=1,
        before_archive=valid_before,
        after_archive=after_archive,
        opportunity_archive=archived_opportunity(frozen, threshold="2"),
        expected_feed_launch=LAUNCH_ANCHOR,
    )


def test_endtime_exercise_requires_one_change_across_the_whole_prefix() -> None:
    frozen = basis()
    before = plays()
    selected_after = play(1, away=2, home=0, end_seconds=9)
    descriptive = plays()
    descriptive["1"] = selected_after
    changed_zero = copy.deepcopy(descriptive["0"])
    assert isinstance(changed_zero, dict)
    result = changed_zero["result"]
    assert isinstance(result, dict)
    result["description"] = "another frozen-prefix change"
    descriptive["0"] = changed_zero
    for after_state in (
        descriptive,
        {
            "0": play(0, away=0, home=0, end_seconds=5),
            "1": selected_after,
        },
    ):
        assert not exercise_credit(
            frozen,
            revised_at_bat_index=1,
            before_archive=archived_state(
                "generation-1", before, observed_seconds=71
            ),
            after_archive=archived_state(
                "generation-2", after_state, observed_seconds=100
            ),
            opportunity_archive=archived_opportunity(frozen),
            expected_feed_launch=LAUNCH_ANCHOR,
        )


def test_exercise_rejects_foreign_noncanonical_and_unmatched_evidence() -> None:
    frozen = basis()
    before = plays()
    current = plays()
    current["1"] = play(1, away=2, home=0, end_seconds=9)
    after_archive = archived_state(
        "generation-2", current, observed_seconds=100
    )
    foreign = {
        **PROVENANCE,
        "run_signature": "prospective-v33-20260718-lock2",
    }
    foreign_before = archived_state(
        "generation-1", before, observed_seconds=71, provenance=foreign
    )
    valid_before = archived_state(
        "generation-1", before, observed_seconds=71
    )
    noncanonical_before = replace(
        valid_before,
        state_bytes=valid_before.state_bytes + b" ",
    )
    for invalid_before in (foreign_before, noncanonical_before):
        assert not exercise_credit(
            frozen,
            revised_at_bat_index=1,
            before_archive=invalid_before,
            after_archive=after_archive,
            opportunity_archive=archived_opportunity(frozen),
            expected_feed_launch=LAUNCH_ANCHOR,
        )
    assert not exercise_credit(
        frozen,
        revised_at_bat_index=1,
        before_archive=valid_before,
        after_archive=after_archive,
        opportunity_archive=archived_opportunity(
            frozen, generation="generation-unmatched"
        ),
        expected_feed_launch=LAUNCH_ANCHOR,
    )
    assert not exercise_credit(
        frozen,
        revised_at_bat_index=1,
        before_archive=valid_before,
        after_archive=after_archive,
        opportunity_archive=archived_opportunity(frozen),
        expected_feed_launch=LAUNCH_ANCHOR,
        before_feed_pair=archived_feed_pair("generation-wrong-parent"),
    )
    foreign_queue = {
        **QUEUE_PROVENANCE,
        "launch_nonce": "foreign-queue-launch",
    }
    assert not exercise_credit(
        frozen,
        revised_at_bat_index=1,
        before_archive=valid_before,
        after_archive=after_archive,
        opportunity_archive=archived_opportunity(
            frozen,
            queue_provenance=foreign_queue,
        ),
        expected_feed_launch=LAUNCH_ANCHOR,
    )
    label_only_pair = archived_feed_pair("generation-1")
    label_only_receipt = json.loads(valid_before.archive_receipt_bytes)
    label_only_receipt["feed_summary_sha256"] = label_only_pair.summary_sha256
    label_only_receipt[
        "feed_archive_receipt_sha256"
    ] = label_only_pair.archive_receipt_sha256
    label_only_state = replace(
        valid_before,
        archive_receipt_bytes=policy.canonical_json_bytes(label_only_receipt),
    )
    assert not exercise_credit(
        frozen,
        revised_at_bat_index=1,
        before_archive=label_only_state,
        after_archive=after_archive,
        opportunity_archive=archived_opportunity(frozen),
        expected_feed_launch=LAUNCH_ANCHOR,
        before_feed_pair=label_only_pair,
    )


def test_exercise_rejects_boolean_aliases_in_archived_opportunity() -> None:
    frozen = basis()
    before = plays()
    current = plays()
    current["1"] = play(1, away=2, home=0, end_seconds=9)
    valid = archived_opportunity(frozen)
    opportunity = json.loads(valid.opportunity_bytes)
    receipt = json.loads(valid.archive_receipt_bytes)
    opportunity["pre_total"] = False
    opportunity["trigger_at_bat_index"] = True
    opportunity_bytes = policy.canonical_json_bytes(opportunity)
    receipt["opportunity_sha256"] = hashlib.sha256(
        opportunity_bytes
    ).hexdigest()
    malformed = prefix.ArchivedQueueOpportunity(
        opportunity_bytes=opportunity_bytes,
        archive_receipt_bytes=policy.canonical_json_bytes(receipt),
    )
    assert not exercise_credit(
        frozen,
        revised_at_bat_index=1,
        before_archive=archived_state(
            "generation-1", before, observed_seconds=71
        ),
        after_archive=archived_state(
            "generation-2", current, observed_seconds=100
        ),
        opportunity_archive=malformed,
        expected_feed_launch=LAUNCH_ANCHOR,
    )


def test_endtime_revision_that_breaks_immutable_guard_is_fatal_and_not_credited() -> None:
    frozen = basis()
    before = plays()
    current = plays()
    after = play(1, away=2, home=0, end_seconds=12)
    current["1"] = after
    with pytest.raises(ValueError, match="breaks immutable"):
        revalidate(frozen, current)
    assert not exercise_credit(
        frozen,
        revised_at_bat_index=1,
        before_archive=archived_state(
            "generation-1", before, observed_seconds=71
        ),
        after_archive=archived_state(
            "generation-2", current, observed_seconds=100
        ),
        opportunity_archive=archived_opportunity(frozen),
        expected_feed_launch=LAUNCH_ANCHOR,
    )


def test_future_endtime_and_ambiguous_review_are_rejected() -> None:
    current = plays()
    current["1"] = play(1, away=2, home=0, end_seconds=120)
    with pytest.raises(ValueError, match="future"):
        revalidate(basis(), current, observed_seconds=100)
    ambiguous = plays()
    ambiguous["0"] = play(
        0, away=0, home=0, end_seconds=4, has_review=True, review={}
    )
    with pytest.raises(ValueError, match="ambiguous"):
        prefix.build_trigger_basis(
            ambiguous,
            game_pk=824999,
            trigger_at_bat_index=1,
            t_seen=BASE + timedelta(seconds=10),
            eligible_at=BASE + timedelta(seconds=71),
        )


def test_changed_pointer_encoding_and_exact_type_rules() -> None:
    assert prefix.changed_json_pointers(
        {"a/b": {"~x": 1}}, {"a/b": {"~x": 2}}
    ) == {"/a~1b/~0x"}
    invalid: dict[str, Any] = plays()
    invalid_play = copy.deepcopy(invalid["0"])
    assert isinstance(invalid_play, dict)
    invalid_about = invalid_play["about"]
    assert isinstance(invalid_about, dict)
    invalid_about["atBatIndex"] = True
    invalid["0"] = invalid_play
    with pytest.raises(ValueError, match="exact integer"):
        prefix.build_trigger_basis(
            invalid,
            game_pk=824999,
            trigger_at_bat_index=1,
            t_seen=BASE + timedelta(seconds=10),
            eligible_at=BASE + timedelta(seconds=71),
        )

    malformed_basis = replace(
        basis(),
        pre_total=False,
        post_total=True,
        run_delta=True,
    )
    with pytest.raises(ValueError, match="exact integer"):
        revalidate(malformed_basis, plays())
