from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import threading
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import pytest
from scripts.v34 import feed_lifecycle as lifecycle
from scripts.v34 import feed_lineage as lineage
from scripts.v34 import policy

if TYPE_CHECKING:
    from pathlib import Path

BASE = datetime(2026, 7, 18, tzinfo=UTC)
GAME_PK = 824999
SOURCE_HASHES = {
    source_name: hashlib.sha256(
        (policy.REPOSITORY_ROOT / source_name).read_bytes()
    ).hexdigest()
    for source_name in sorted(policy.REQUIRED_LAUNCH_SOURCES)
}
LAUNCH_BYTES = policy.canonical_json_bytes(
    {
        "created_at": BASE.isoformat(),
        "launch_nonce": "v34-feed-lineage-test-nonce",
        "manifest_kind": "v34_feed_launch",
        "output_root": policy.FEED_OUTPUT_ROOT,
        "policy_sha256": policy.POLICY_CANONICAL_SHA256,
        "run_signature": policy.FEED_RUN_SIGNATURE,
        "schema_version": policy.FEED_SCHEMA_VERSION,
        "source_hashes": SOURCE_HASHES,
    }
)
ANCHOR = policy.verify_feed_launch_manifest_bytes(LAUNCH_BYTES)
EMPTY_SNAPSHOT = lineage.FeedLineageSnapshot(
    event_count=0,
    last_event_sha256=None,
    game_states=(),
    file_size=0,
    file_device=None,
    file_inode=None,
    file_mtime_ns=None,
    lineage_path=None,
    game_heads_sha256=None,
    file_sha256=None,
    base_lineage_path=None,
    active_segment_index=0,
    active_first_event_sequence=None,
    active_first_prior_event_sha256=None,
    active_first_event_sha256=None,
    sealed_segments=(),
    sealed_segments_sha256=None,
    sealed_identities=(),
)
HEADS: dict[Path, lineage.FeedLineageSnapshot] = {}


def play(
    index: int,
    *,
    away: int,
    home: int,
    end_seconds: float,
) -> dict[str, object]:
    return {
        "about": {
            "atBatIndex": index,
            "endTime": (BASE + timedelta(seconds=end_seconds)).isoformat(),
            "hasReview": False,
            "isComplete": True,
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
        "review_details": None,
    }


def observe(
    prior: lifecycle.FeedGameState | None,
    completed: dict[str, object],
    *,
    observed_seconds: float,
    monotonic_seconds: float | None = None,
    total: int,
    game_pk: int = GAME_PK,
) -> lifecycle.FeedTransition:
    if monotonic_seconds is None:
        monotonic_seconds = observed_seconds
    return lifecycle.transition_game(
        prior,
        game_pk=game_pk,
        completed_plays=completed,
        official_current_total=total,
        abstract_state="Live",
        detailed_state="In Progress",
        observed_at=BASE + timedelta(seconds=observed_seconds),
        successful_poll_monotonic_ns=int(
            monotonic_seconds * lifecycle.NANOSECONDS_PER_SECOND
        ),
        expected_prior_state_commitment_sha256=(
            None if prior is None else prior.state_commitment_sha256
        ),
    )


def baseline(*, game_pk: int = GAME_PK) -> lifecycle.FeedTransition:
    return observe(
        None,
        {"0": play(0, away=0, home=0, end_seconds=4)},
        observed_seconds=10,
        total=0,
        game_pk=game_pk,
    )


def trigger(prior: lifecycle.FeedGameState) -> lifecycle.FeedTransition:
    return observe(
        prior,
        {
            "0": play(0, away=0, home=0, end_seconds=4),
            "1": play(1, away=2, home=0, end_seconds=18),
        },
        observed_seconds=20,
        total=2,
    )


def recorded_at() -> str:
    return (BASE + timedelta(hours=1)).isoformat()


def append(
    path: Path,
    transition: lifecycle.FeedTransition,
) -> lineage.FeedLineageSnapshot:
    expected_snapshot = HEADS.get(path, EMPTY_SNAPSHOT)
    snapshot = lineage.append_feed_transition(
        path,
        transition,
        feed_anchor=ANCHOR,
        recorded_at=recorded_at,
        expected_snapshot=expected_snapshot,
        trusted_root=path.parent,
    )
    HEADS[path] = snapshot
    return snapshot


def replay(path: Path) -> lineage.FeedLineageSnapshot:
    expected_snapshot = HEADS.get(path, EMPTY_SNAPSHOT)
    return lineage.replay_feed_lineage(
        path,
        feed_anchor=ANCHOR,
        expected_event_count=expected_snapshot.event_count,
        expected_last_event_sha256=expected_snapshot.last_event_sha256,
        expected_sealed_segments=expected_snapshot.sealed_segments,
        trusted_root=path.parent,
    )


def test_state_roundtrip_for_baseline_pending_and_eligible() -> None:
    initial = baseline()
    pending = trigger(initial.state)
    current = pending.state
    completed = json.loads(current.last_completed_plays_bytes)
    for seconds in (30, 40, 50, 60, 70, 80, 81):
        current = observe(
            current,
            completed,
            observed_seconds=seconds,
            total=2,
        ).state
    assert len(current.eligible) == 1
    for state in (initial.state, pending.state, current):
        raw = lineage.serialize_game_state(state)
        assert raw == policy.canonical_json_bytes(json.loads(raw))
        assert lineage.deserialize_game_state(raw) == state


def test_append_replay_and_per_game_path_binding(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    first = baseline()
    snapshot = append(path, first)
    assert snapshot.event_count == 1
    assert snapshot.state_for(GAME_PK) == first.state

    second = trigger(first.state)
    snapshot = append(path, second)
    assert snapshot.event_count == 2
    assert snapshot.state_for(GAME_PK) == second.state
    assert replay(path) == snapshot
    assert path.read_bytes().endswith(b"\n")

    other_path = tmp_path / "other.jsonl"
    other = baseline(game_pk=825000)
    other_snapshot = append(other_path, other)
    assert other_snapshot.state_for(825000) == other.state
    assert replay(other_path) == other_snapshot

    before = path.read_bytes()
    with pytest.raises(
        lineage.FeedLineageFatalError,
        match="already bound to another game",
    ):
        append(path, baseline(game_pk=825001))
    assert path.read_bytes() == before


def test_append_every_poll_produces_one_contiguous_external_head(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    initial = baseline()
    append(path, initial)
    pending = trigger(initial.state)
    append(path, pending)
    current = pending.state
    completed = json.loads(current.last_completed_plays_bytes)
    for seconds in (30, 40, 50, 60, 70, 80, 81):
        result = observe(
            current,
            completed,
            observed_seconds=seconds,
            total=2,
        )
        snapshot = append(path, result)
        current = result.state
        assert snapshot.state_for(GAME_PK) == current
    assert current.transition_sequence == 9
    assert len(current.eligible) == 1


def test_append_fast_path_does_not_replay_the_full_log(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "events.jsonl"
    initial = baseline()
    append(path, initial)

    def forbidden_replay(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("normal append must not replay the full lineage")

    monkeypatch.setattr(lineage, "replay_feed_lineage", forbidden_replay)
    snapshot = append(path, trigger(initial.state))
    assert snapshot.event_count == 2


def test_forged_retained_game_state_map_is_rejected_before_append(
    tmp_path: Path,
) -> None:
    path = tmp_path / "events.jsonl"
    snapshot = append(path, baseline())
    before = path.read_bytes()
    candidate = baseline(game_pk=825000)

    omitted_with_original_commitment = replace(snapshot, game_states=())
    with pytest.raises(
        lineage.FeedLineageFatalError,
        match="game states differ from their commitment",
    ):
        lineage.append_feed_transition(
            path,
            candidate,
            feed_anchor=ANCHOR,
            recorded_at=recorded_at,
            expected_snapshot=omitted_with_original_commitment,
            trusted_root=tmp_path,
        )
    assert path.read_bytes() == before

    omitted_with_recomputed_commitment = replace(
        snapshot,
        game_states=(),
        game_heads_sha256=lineage._game_heads_sha256({}),
    )
    with pytest.raises(
        lineage.FeedLineageFatalError,
        match="game heads differ from the terminal event",
    ):
        lineage.append_feed_transition(
            path,
            candidate,
            feed_anchor=ANCHOR,
            recorded_at=recorded_at,
            expected_snapshot=omitted_with_recomputed_commitment,
            trusted_root=tmp_path,
        )
    assert path.read_bytes() == before


def test_earlier_prefix_corruption_with_restored_metadata_is_rejected(
    tmp_path: Path,
) -> None:
    path = tmp_path / "events.jsonl"
    first = baseline()
    append(path, first)
    snapshot = append(path, trigger(first.state))
    original_stat = path.stat()
    corrupted = bytearray(path.read_bytes())
    corrupted[0] = ord("[")
    path.write_bytes(corrupted)
    os.utime(
        path,
        ns=(original_stat.st_atime_ns, snapshot.file_mtime_ns),
    )
    corrupted_bytes = path.read_bytes()

    with pytest.raises(
        lineage.FeedLineageFatalError,
        match="(active first event hash|final retained hash) differs",
    ):
        lineage.append_feed_transition(
            path,
            baseline(game_pk=825000),
            feed_anchor=ANCHOR,
            recorded_at=recorded_at,
            expected_snapshot=snapshot,
            trusted_root=tmp_path,
        )
    assert path.read_bytes() == corrupted_bytes


def test_recorded_at_callback_cannot_corrupt_verified_prefix(
    tmp_path: Path,
) -> None:
    path = tmp_path / "events.jsonl"
    initial = baseline()
    snapshot = append(path, initial)
    original_stat = path.stat()

    def corrupting_recorded_at() -> str:
        corrupted = bytearray(path.read_bytes())
        corrupted[0] = ord("[")
        path.write_bytes(corrupted)
        os.utime(
            path,
            ns=(original_stat.st_atime_ns, snapshot.file_mtime_ns),
        )
        return recorded_at()

    with pytest.raises(
        lineage.FeedLineageFatalError,
        match="(active first event hash|final retained hash) differs",
    ):
        lineage.append_feed_transition(
            path,
            trigger(initial.state),
            feed_anchor=ANCHOR,
            recorded_at=corrupting_recorded_at,
            expected_snapshot=snapshot,
            trusted_root=tmp_path,
        )
    assert path.read_bytes().count(b"\n") == 1


def test_ancestry_is_rechecked_after_recorded_at_callback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "events.jsonl"
    initial = baseline()
    snapshot = append(path, initial)
    before = path.read_bytes()
    callback_returned = False
    original_check = lineage.feed_archive._assert_no_redirecting_components

    def checked_after_callback(base: Path, target: Path) -> None:
        if callback_returned and target == path:
            raise lineage.feed_archive.ArchiveCollisionError(
                "simulated ancestor replacement"
            )
        original_check(base, target)

    def ancestry_replacing_recorded_at() -> str:
        nonlocal callback_returned
        callback_returned = True
        return recorded_at()

    monkeypatch.setattr(
        lineage.feed_archive,
        "_assert_no_redirecting_components",
        checked_after_callback,
    )
    with pytest.raises(
        lineage.FeedLineageFatalError,
        match="ancestry is not trusted",
    ):
        lineage.append_feed_transition(
            path,
            trigger(initial.state),
            feed_anchor=ANCHOR,
            recorded_at=ancestry_replacing_recorded_at,
            expected_snapshot=snapshot,
            trusted_root=tmp_path,
        )
    assert path.read_bytes() == before


def test_forged_retained_count_is_bound_to_terminal_event_before_append(
    tmp_path: Path,
) -> None:
    path = tmp_path / "events.jsonl"
    initial = baseline()
    snapshot = append(path, initial)
    before = path.read_bytes()
    forged = replace(snapshot, event_count=100)

    with pytest.raises(
        lineage.FeedLineageFatalError,
        match="count differs from the terminal event",
    ):
        lineage.append_feed_transition(
            path,
            trigger(initial.state),
            feed_anchor=ANCHOR,
            recorded_at=recorded_at,
            expected_snapshot=forged,
            trusted_root=tmp_path,
        )
    assert path.read_bytes() == before


def test_copied_lineage_with_rebuilt_metadata_cannot_change_path_binding(
    tmp_path: Path,
) -> None:
    original = tmp_path / "original.jsonl"
    copied = tmp_path / "copied.jsonl"
    initial = baseline()
    snapshot = append(original, initial)
    copied.write_bytes(original.read_bytes())
    copied_stat = copied.stat()
    forged = replace(
        snapshot,
        file_device=copied_stat.st_dev,
        file_inode=copied_stat.st_ino,
        file_mtime_ns=copied_stat.st_mtime_ns,
        lineage_path=copied.name,
        base_lineage_path=copied.name,
        file_sha256=hashlib.sha256(copied.read_bytes()).hexdigest(),
    )
    before = copied.read_bytes()

    with pytest.raises(
        lineage.FeedLineageFatalError,
        match="(base path differs|path differs from the terminal event)",
    ):
        lineage.append_feed_transition(
            copied,
            trigger(initial.state),
            feed_anchor=ANCHOR,
            recorded_at=recorded_at,
            expected_snapshot=forged,
            trusted_root=tmp_path,
        )
    assert copied.read_bytes() == before


def test_valid_snapshot_cannot_cross_launch_anchors(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    initial = baseline()
    snapshot = append(path, initial)
    other_manifest: dict[str, Any] = json.loads(LAUNCH_BYTES)
    other_manifest["launch_nonce"] = "v34-feed-lineage-other-test-nonce"
    other_anchor = policy.verify_feed_launch_manifest_bytes(
        policy.canonical_json_bytes(other_manifest)
    )
    before = path.read_bytes()

    with pytest.raises(
        lineage.FeedLineageFatalError,
        match="launch provenance differs",
    ):
        lineage.append_feed_transition(
            path,
            trigger(initial.state),
            feed_anchor=other_anchor,
            recorded_at=recorded_at,
            expected_snapshot=snapshot,
            trusted_root=tmp_path,
        )
    assert path.read_bytes() == before


@pytest.mark.parametrize("field_name", ["game_pk", "transition_sequence"])
def test_fast_terminal_exact_integers_reject_float_aliases(
    tmp_path: Path,
    field_name: str,
) -> None:
    path = tmp_path / "events.jsonl"
    initial = baseline()
    snapshot = append(path, initial)
    row: dict[str, Any] = json.loads(path.read_bytes())
    row[field_name] = float(row[field_name])
    raw = policy.canonical_json_bytes(row)
    path.write_bytes(raw + b"\n")
    changed = path.stat()
    forged = replace(
        snapshot,
        last_event_sha256=hashlib.sha256(raw).hexdigest(),
        file_size=changed.st_size,
        file_device=changed.st_dev,
        file_inode=changed.st_ino,
        file_mtime_ns=changed.st_mtime_ns,
        file_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        active_first_event_sha256=hashlib.sha256(raw).hexdigest(),
    )
    before = path.read_bytes()

    with pytest.raises(
        lineage.FeedLineageFatalError,
        match=f"retained terminal {field_name} must be an exact integer",
    ):
        lineage.append_feed_transition(
            path,
            trigger(initial.state),
            feed_anchor=ANCHOR,
            recorded_at=recorded_at,
            expected_snapshot=forged,
            trusted_root=tmp_path,
        )
    assert path.read_bytes() == before


def test_fast_terminal_state_bytes_hash_is_revalidated(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    initial = baseline()
    snapshot = append(path, initial)
    row: dict[str, Any] = json.loads(path.read_bytes())
    row["state_bytes_sha256"] = "0" * 64
    raw = policy.canonical_json_bytes(row)
    path.write_bytes(raw + b"\n")
    changed = path.stat()
    forged = replace(
        snapshot,
        last_event_sha256=hashlib.sha256(raw).hexdigest(),
        file_size=changed.st_size,
        file_device=changed.st_dev,
        file_inode=changed.st_ino,
        file_mtime_ns=changed.st_mtime_ns,
        file_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        active_first_event_sha256=hashlib.sha256(raw).hexdigest(),
    )
    before = path.read_bytes()

    with pytest.raises(
        lineage.FeedLineageFatalError,
        match="state bytes hash differs",
    ):
        lineage.append_feed_transition(
            path,
            trigger(initial.state),
            feed_anchor=ANCHOR,
            recorded_at=recorded_at,
            expected_snapshot=forged,
            trusted_root=tmp_path,
        )
    assert path.read_bytes() == before


def test_second_baseline_for_existing_game_is_rejected_before_append(
    tmp_path: Path,
) -> None:
    path = tmp_path / "events.jsonl"
    first = baseline()
    append(path, first)
    before = path.read_bytes()
    second_baseline = observe(
        None,
        {"0": play(0, away=0, home=0, end_seconds=4)},
        observed_seconds=20,
        total=0,
    )
    with pytest.raises(
        lineage.FeedLineageFatalError,
        match="transition does not extend the durable game head",
    ):
        append(path, second_baseline)
    assert path.read_bytes() == before


def test_forged_skipped_transition_is_rejected_before_append(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    initial = baseline()
    append(path, initial)
    pending = trigger(initial.state)
    current = pending.state
    completed = json.loads(current.last_completed_plays_bytes)
    last_result = pending
    for seconds in (30, 40, 50, 60, 70, 80, 81):
        last_result = observe(
            current,
            completed,
            observed_seconds=seconds,
            total=2,
        )
        current = last_result.state
    forged = lifecycle._make_state(
        game_pk=current.game_pk,
        seen_completed_indices=current.seen_completed_indices,
        last_completed_plays_bytes=current.last_completed_plays_bytes,
        last_official_current_total=current.last_official_current_total,
        last_abstract_state=current.last_abstract_state,
        last_detailed_state=current.last_detailed_state,
        last_observed_at=current.last_observed_at,
        last_successful_poll_monotonic_ns=(
            current.last_successful_poll_monotonic_ns
        ),
        pending=current.pending,
        eligible=current.eligible,
        transition_sequence=2,
        prior_state_commitment_sha256=initial.state.state_commitment_sha256,
    )
    candidate = lifecycle.FeedTransition(
        state=forged,
        event_bytes=last_result.event_bytes,
    )
    before = path.read_bytes()
    with pytest.raises(
        lineage.FeedLineageFatalError,
        match="transition cannot be recomputed",
    ):
        append(path, candidate)
    assert path.read_bytes() == before


def test_partial_terminal_event_is_fatal_and_never_truncated(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    append(path, baseline())
    path.write_bytes(path.read_bytes() + b'{"partial":')
    corrupted = path.read_bytes()
    with pytest.raises(
        lineage.FeedLineageFatalError,
        match="partial terminal event",
    ):
        replay(path)
    assert path.read_bytes() == corrupted


def test_valid_prefix_rollback_and_deletion_fail_against_external_head(
    tmp_path: Path,
) -> None:
    path = tmp_path / "events.jsonl"
    initial = baseline()
    append(path, initial)
    append(path, trigger(initial.state))
    lines = path.read_bytes().splitlines(keepends=True)
    path.write_bytes(lines[0])
    truncated = path.read_bytes()
    with pytest.raises(
        lineage.FeedLineageFatalError,
        match="independently retained head",
    ):
        replay(path)
    with pytest.raises(lineage.FeedLineageFatalError):
        append(
            path,
            observe(
                initial.state,
                {"0": play(0, away=0, home=0, end_seconds=4)},
                observed_seconds=20,
                total=0,
            ),
        )
    assert path.read_bytes() == truncated

    path.unlink()
    with pytest.raises(
        lineage.FeedLineageFatalError,
        match="expected nonempty feed lineage is missing",
    ):
        replay(path)


def test_existing_empty_lineage_cannot_be_treated_as_prelaunch_absence(
    tmp_path: Path,
) -> None:
    path = tmp_path / "events.jsonl"
    path.write_bytes(b"")
    with pytest.raises(
        lineage.FeedLineageFatalError,
        match="segment is missing or empty",
    ):
        lineage.replay_feed_lineage(
            path,
            feed_anchor=ANCHOR,
            expected_event_count=0,
            expected_last_event_sha256=None,
            trusted_root=tmp_path,
        )


def test_event_limit_is_checked_before_durable_append(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "events.jsonl"
    initial = baseline()
    append(path, initial)
    before = path.read_bytes()
    monkeypatch.setattr(lineage, "MAX_LINEAGE_EVENTS", 1)
    with pytest.raises(
        lineage.FeedLineageFatalError,
        match="already at the event limit",
    ):
        append(path, trigger(initial.state))
    assert path.read_bytes() == before


def test_active_segment_rotates_before_byte_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "events.jsonl"
    initial = baseline()
    snapshot = append(path, initial)
    first_segment_bytes = path.read_bytes()
    monkeypatch.setattr(
        lineage,
        "MAX_ACTIVE_SEGMENT_BYTES",
        snapshot.file_size * 2,
    )
    rotated = append(path, trigger(initial.state))
    assert rotated.active_segment_index == 2
    assert len(rotated.sealed_segments) == 1
    assert path.read_bytes() == first_segment_bytes
    active_path = lineage._segment_path(path, 2)
    assert active_path.is_file()
    archive_path = tmp_path / rotated.sealed_segments[0].archive_path
    assert archive_path.read_bytes() == first_segment_bytes
    assert replay(path) == rotated


def test_rotation_retry_adopts_only_exact_prepublished_replica(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "events.jsonl"
    initial = baseline()
    first = append(path, initial)
    monkeypatch.setattr(
        lineage,
        "MAX_ACTIVE_SEGMENT_BYTES",
        first.file_size * 2,
    )
    original_append = lineage._append_exact_payload

    def injected_failure(*_args: object, **_kwargs: object) -> None:
        raise OSError("injected append failure after segment sealing")

    monkeypatch.setattr(lineage, "_append_exact_payload", injected_failure)
    with pytest.raises(OSError, match="injected append failure"):
        append(path, trigger(initial.state))
    assert HEADS[path] == first
    assert not lineage._segment_path(path, 2).exists()
    assert (tmp_path / f".{path.name}.sealed").is_dir()

    monkeypatch.setattr(lineage, "_append_exact_payload", original_append)
    recovered = append(path, trigger(initial.state))
    assert recovered.active_segment_index == 2
    assert len(recovered.sealed_segments) == 1
    assert replay(path) == recovered


@pytest.mark.parametrize("crash_phase", ["before_link", "after_link"])
def test_rotation_recovers_exact_create_once_crash_temp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    crash_phase: str,
) -> None:
    path = tmp_path / "events.jsonl"
    initial = baseline()
    first = append(path, initial)
    receipt = lineage._receipt_from_active_snapshot(
        first,
        base_path=path,
        trusted_root=tmp_path,
        feed_anchor=ANCHOR,
    )
    archive_path = tmp_path / receipt.archive_path
    archive_path.parent.mkdir()
    temp_path = archive_path.parent / (
        f".{archive_path.name}.v34tmp-{'a' * 32}.tmp"
    )
    if crash_phase == "before_link":
        temp_path.write_bytes(path.read_bytes())
    else:
        archive_path.write_bytes(path.read_bytes())
        os.link(archive_path, temp_path)
    monkeypatch.setattr(
        lineage,
        "MAX_ACTIVE_SEGMENT_BYTES",
        first.file_size * 2,
    )

    recovered = append(path, trigger(initial.state))

    assert recovered.active_segment_index == 2
    assert not temp_path.exists()
    assert archive_path.read_bytes() == path.read_bytes()
    assert replay(path) == recovered


def test_exact_pending_archive_forces_rotation_for_smaller_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def described_trigger(
        prior: lifecycle.FeedGameState,
        description: str,
    ) -> lifecycle.FeedTransition:
        scoring_play = play(1, away=2, home=0, end_seconds=18)
        result = scoring_play["result"]
        assert isinstance(result, dict)
        result["description"] = description
        return observe(
            prior,
            {"0": play(0, away=0, home=0, end_seconds=4), "1": scoring_play},
            observed_seconds=20,
            total=2,
        )

    small_path = tmp_path / "small000.jsonl"
    small_initial = baseline()
    append(small_path, small_initial)
    append(small_path, described_trigger(small_initial.state, "small"))
    small_event_size = len(small_path.read_bytes().splitlines()[1])

    large_path = tmp_path / "large000.jsonl"
    large_initial = baseline()
    append(large_path, large_initial)
    append(large_path, described_trigger(large_initial.state, "x" * 2_000))
    large_event_size = len(large_path.read_bytes().splitlines()[1])
    assert large_event_size > small_event_size

    target = tmp_path / "target00.jsonl"
    target_initial = baseline()
    target_first = append(target, target_initial)
    limit = target_first.file_size + small_event_size + 1
    monkeypatch.setattr(lineage, "MAX_ACTIVE_SEGMENT_BYTES", limit)
    original_append = lineage._append_exact_payload

    def injected_failure(*_args: object, **_kwargs: object) -> None:
        raise OSError("injected append failure after large rotation seal")

    monkeypatch.setattr(lineage, "_append_exact_payload", injected_failure)
    with pytest.raises(OSError, match="injected append failure"):
        append(target, described_trigger(target_initial.state, "x" * 2_000))
    pending_receipt = lineage._receipt_from_active_snapshot(
        target_first,
        base_path=target,
        trusted_root=tmp_path,
        feed_anchor=ANCHOR,
    )
    assert (tmp_path / pending_receipt.archive_path).is_file()

    monkeypatch.setattr(lineage, "_append_exact_payload", original_append)
    recovered = append(target, described_trigger(target_initial.state, "small"))

    assert target_first.file_size + small_event_size + 1 <= limit
    assert recovered.active_segment_index == 2
    assert replay(target) == recovered


def test_rotation_rejects_archive_mutated_after_publication_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "events.jsonl"
    initial = baseline()
    first = append(path, initial)
    monkeypatch.setattr(
        lineage,
        "MAX_ACTIVE_SEGMENT_BYTES",
        first.file_size * 2,
    )
    original_read = lineage.feed_archive._stable_owned_file_bytes
    archive_reads = 0

    def corrupt_after_second_archive_read(candidate: Path) -> bytes:
        nonlocal archive_reads
        value = original_read(candidate)
        if candidate.parent.name == f".{path.name}.sealed":
            archive_reads += 1
            if archive_reads == 2:
                changed = bytearray(value)
                changed[0] = ord("[")
                candidate.write_bytes(changed)
        return value

    monkeypatch.setattr(
        lineage.feed_archive,
        "_stable_owned_file_bytes",
        corrupt_after_second_archive_read,
    )
    with pytest.raises(lineage.FeedLineageFatalError):
        append(path, trigger(initial.state))
    assert archive_reads >= 2


def test_rotated_event_size_is_rechecked_before_sealing_or_append(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pre_path = tmp_path / "plain00.jsonl"
    initial = baseline()
    append(pre_path, initial)
    append(pre_path, trigger(initial.state))
    pre_rotation_size = len(pre_path.read_bytes().splitlines()[1])

    rotated_path = tmp_path / "rotate0.jsonl"
    rotated_initial = baseline()
    rotated_first = append(rotated_path, rotated_initial)
    monkeypatch.setattr(
        lineage,
        "MAX_ACTIVE_SEGMENT_BYTES",
        rotated_first.file_size * 2,
    )
    rotated = append(rotated_path, trigger(rotated_initial.state))
    rotated_event_size = len(
        lineage._segment_path(rotated_path, 2).read_bytes().removesuffix(b"\n")
    )
    assert rotated_event_size > pre_rotation_size
    assert rotated.active_segment_index == 2

    target = tmp_path / "target0.jsonl"
    target_initial = baseline()
    target_first = append(target, target_initial)
    monkeypatch.setattr(
        lineage,
        "MAX_ACTIVE_SEGMENT_BYTES",
        target_first.file_size * 2,
    )
    monkeypatch.setattr(lineage, "MAX_LINEAGE_EVENT_BYTES", pre_rotation_size)
    before = target.read_bytes()
    with pytest.raises(
        lineage.FeedLineageFatalError,
        match="rotated feed lineage event exceeds the byte limit",
    ):
        append(target, trigger(target_initial.state))
    assert target.read_bytes() == before
    assert not lineage._segment_path(target, 2).exists()
    assert not (tmp_path / f".{target.name}.sealed").exists()


@pytest.mark.parametrize("extra_kind", ["future_segment", "archive_directory"])
def test_empty_snapshot_rejects_preexisting_inventory(
    tmp_path: Path,
    extra_kind: str,
) -> None:
    path = tmp_path / "events.jsonl"
    if extra_kind == "future_segment":
        lineage._segment_path(path, 2).write_bytes(b"extra\n")
    else:
        (tmp_path / f".{path.name}.sealed").mkdir()
    with pytest.raises(
        lineage.FeedLineageFatalError,
        match="empty expected lineage inventory is not absent",
    ):
        lineage.append_feed_transition(
            path,
            baseline(),
            feed_anchor=ANCHOR,
            recorded_at=recorded_at,
            expected_snapshot=EMPTY_SNAPSHOT,
            trusted_root=tmp_path,
        )
    assert not path.exists()


def test_empty_snapshot_rejects_forged_runtime_identity(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    forged = replace(
        EMPTY_SNAPSHOT,
        sealed_identities=(
            lineage.FeedSealedIdentity(
                segment_index=1,
                source_device=1,
                source_inode=1,
                source_mtime_ns=1,
                archive_device=1,
                archive_inode=1,
                archive_mtime_ns=1,
            ),
        ),
    )
    with pytest.raises(
        lineage.FeedLineageFatalError,
        match="empty retained snapshot fields differ",
    ):
        lineage.append_feed_transition(
            path,
            baseline(),
            feed_anchor=ANCHOR,
            recorded_at=recorded_at,
            expected_snapshot=forged,
            trusted_root=tmp_path,
        )
    assert not path.exists()


def test_literal_glob_metacharacters_in_base_name_survive_rotation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "events[1].jsonl"
    initial = baseline()
    first = append(path, initial)
    monkeypatch.setattr(
        lineage,
        "MAX_ACTIVE_SEGMENT_BYTES",
        first.file_size * 2,
    )
    rotated = append(path, trigger(initial.state))
    assert rotated.active_segment_index == 2
    assert replay(path) == rotated


def test_multiple_rotations_preserve_global_chain_and_exact_restart(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "events.jsonl"
    initial = baseline()
    first = append(path, initial)
    monkeypatch.setattr(
        lineage,
        "MAX_ACTIVE_SEGMENT_BYTES",
        first.file_size * 2,
    )
    pending = trigger(initial.state)
    snapshot = append(path, pending)
    current = pending.state
    completed = json.loads(current.last_completed_plays_bytes)
    for seconds in (30, 40, 50, 60, 70, 80, 81):
        result = observe(
            current,
            completed,
            observed_seconds=seconds,
            total=2,
        )
        snapshot = append(path, result)
        current = result.state
    assert snapshot.active_segment_index >= 3
    assert len(snapshot.sealed_segments) == snapshot.active_segment_index - 1
    prior_last_sha: str | None = None
    prior_last_sequence = 0
    for receipt in snapshot.sealed_segments:
        assert receipt.first_event_sequence == prior_last_sequence + 1
        assert receipt.first_prior_event_sha256 == prior_last_sha
        source = tmp_path / receipt.lineage_path
        archive = tmp_path / receipt.archive_path
        assert source.read_bytes() == archive.read_bytes()
        prior_last_sha = receipt.last_event_sha256
        prior_last_sequence = receipt.last_event_sequence
    assert replay(path) == snapshot


def test_missing_or_extra_segment_inventory_is_fatal_before_append(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "events.jsonl"
    initial = baseline()
    first = append(path, initial)
    monkeypatch.setattr(
        lineage,
        "MAX_ACTIVE_SEGMENT_BYTES",
        first.file_size * 2,
    )
    snapshot = append(path, trigger(initial.state))
    active_path = lineage._segment_path(path, snapshot.active_segment_index)
    before = active_path.read_bytes()
    extra = lineage._segment_path(path, snapshot.active_segment_index + 1)
    extra.write_bytes(b"extra\n")
    with pytest.raises(
        lineage.FeedLineageFatalError,
        match="segment inventory differs",
    ):
        append(
            path,
            observe(
                snapshot.state_for(GAME_PK),
                json.loads(snapshot.state_for(GAME_PK).last_completed_plays_bytes),
                observed_seconds=30,
                total=2,
            ),
        )
    assert active_path.read_bytes() == before
    extra.unlink()

    archive = tmp_path / snapshot.sealed_segments[0].archive_path
    archive.unlink()
    with pytest.raises(
        lineage.FeedLineageFatalError,
        match="(sealed archive inventory differs|replica cannot be read)",
    ):
        replay(path)


@pytest.mark.parametrize("copy_name", ["source", "archive"])
def test_full_restart_detects_corruption_in_either_sealed_copy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    copy_name: str,
) -> None:
    path = tmp_path / "events.jsonl"
    initial = baseline()
    first = append(path, initial)
    monkeypatch.setattr(
        lineage,
        "MAX_ACTIVE_SEGMENT_BYTES",
        first.file_size * 2,
    )
    snapshot = append(path, trigger(initial.state))
    receipt = snapshot.sealed_segments[0]
    target = tmp_path / (
        receipt.lineage_path if copy_name == "source" else receipt.archive_path
    )
    changed = bytearray(target.read_bytes())
    changed[0] = ord("[")
    target.write_bytes(changed)
    with pytest.raises(lineage.FeedLineageFatalError):
        replay(path)


@pytest.mark.parametrize("copy_name", ["source", "archive"])
def test_fast_append_rejects_mutated_sealed_copy_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    copy_name: str,
) -> None:
    path = tmp_path / "events.jsonl"
    initial = baseline()
    first = append(path, initial)
    monkeypatch.setattr(
        lineage,
        "MAX_ACTIVE_SEGMENT_BYTES",
        first.file_size * 2,
    )
    snapshot = append(path, trigger(initial.state))
    receipt = snapshot.sealed_segments[0]
    target = tmp_path / (
        receipt.lineage_path if copy_name == "source" else receipt.archive_path
    )
    changed = bytearray(target.read_bytes())
    changed[0] = ord("[")
    target.write_bytes(changed)
    active_path = lineage._segment_path(path, snapshot.active_segment_index)
    active_before = active_path.read_bytes()
    current = snapshot.state_for(GAME_PK)
    assert current is not None
    with pytest.raises(
        lineage.FeedLineageFatalError,
        match="retained identity differs",
    ):
        append(
            path,
            observe(
                current,
                json.loads(current.last_completed_plays_bytes),
                observed_seconds=30,
                total=2,
            ),
        )
    assert active_path.read_bytes() == active_before


def test_full_restart_rebuilds_runtime_identity_after_exact_portable_restore(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "events.jsonl"
    initial = baseline()
    first = append(path, initial)
    monkeypatch.setattr(
        lineage,
        "MAX_ACTIVE_SEGMENT_BYTES",
        first.file_size * 2,
    )
    snapshot = append(path, trigger(initial.state))
    receipt = snapshot.sealed_segments[0]
    original_identities = snapshot.sealed_identities
    for relative_path in (receipt.lineage_path, receipt.archive_path):
        target = tmp_path / relative_path
        replacement = target.with_name(f"{target.name}.replacement")
        replacement.write_bytes(target.read_bytes())
        replacement.replace(target)

    restored = replay(path)

    assert restored.sealed_segments == snapshot.sealed_segments
    assert restored.sealed_segments_sha256 == snapshot.sealed_segments_sha256
    assert restored.sealed_identities != original_identities
    assert replace(snapshot, sealed_identities=restored.sealed_identities) == restored


def test_active_segment_bound_includes_many_eligible_triggers(
    tmp_path: Path,
) -> None:
    path = tmp_path / "large-game.jsonl"
    initial = baseline()
    append(path, initial)
    away_score = 0
    completed: dict[str, object] = {}
    for index in range(80):
        if index % 4 == 3:
            away_score += 1
        completed[str(index)] = play(
            index,
            away=away_score,
            home=0,
            end_seconds=10.0 + (index + 1) / 10,
        )
    current = observe(
        initial.state,
        completed,
        observed_seconds=20,
        total=20,
    )
    append(path, current)
    for seconds in (30, 40, 50, 60, 70, 80, 81):
        current = observe(
            current.state,
            completed,
            observed_seconds=seconds,
            total=20,
        )
        append(path, current)
    assert len(current.state.eligible) == 20
    before = HEADS[path]
    late_poll = observe(
        current.state,
        completed,
        observed_seconds=90,
        total=20,
    )
    after = append(path, late_poll)
    late_poll_bytes = after.file_size - before.file_size
    assert lineage.MAX_ACTIVE_SEGMENT_BYTES // late_poll_bytes >= 600


def test_oversized_line_is_rejected_with_a_bounded_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "events.jsonl"
    path.write_bytes(b"x" * 66)
    monkeypatch.setattr(lineage, "MAX_LINEAGE_EVENT_BYTES", 64)
    with pytest.raises(
        lineage.FeedLineageFatalError,
        match="exceeds the byte limit",
    ):
        lineage.replay_feed_lineage(
            path,
            feed_anchor=ANCHOR,
            expected_event_count=1,
            expected_last_event_sha256="0" * 64,
            trusted_root=tmp_path,
        )


def test_recomputed_outer_state_hash_cannot_hide_inner_state_mutation(
    tmp_path: Path,
) -> None:
    path = tmp_path / "events.jsonl"
    append(path, baseline())
    row: dict[str, Any] = json.loads(path.read_bytes())
    row["state"]["last_official_current_total"] = 1
    state_bytes = policy.canonical_json_bytes(row["state"])
    row["state_bytes_sha256"] = hashlib.sha256(state_bytes).hexdigest()
    path.write_bytes(policy.canonical_json_bytes(row) + b"\n")
    with pytest.raises(
        lineage.FeedLineageFatalError,
        match="game state reconstruction failed",
    ):
        replay(path)


@pytest.mark.parametrize(
    "field_name",
    [
        "event_sequence",
        "prior_lineage_event_sha256",
        "state_commitment_sha256",
    ],
)
def test_lineage_chain_and_binding_mutations_are_fatal(
    tmp_path: Path,
    field_name: str,
) -> None:
    path = tmp_path / f"{field_name}.jsonl"
    initial = baseline()
    append(path, initial)
    append(path, trigger(initial.state))
    lines = path.read_bytes().splitlines()
    second: dict[str, Any] = json.loads(lines[1])
    if field_name == "event_sequence":
        second[field_name] = 7
    elif field_name == "prior_lineage_event_sha256":
        second[field_name] = "0" * 64
    else:
        second[field_name] = "f" * 64
    path.write_bytes(lines[0] + b"\n" + policy.canonical_json_bytes(second) + b"\n")
    with pytest.raises(lineage.FeedLineageFatalError):
        replay(path)


def test_lifecycle_event_mutation_is_fatal_even_when_outer_event_is_canonical(
    tmp_path: Path,
) -> None:
    path = tmp_path / "events.jsonl"
    initial = baseline()
    append(path, initial)
    append(path, trigger(initial.state))
    lines = path.read_bytes().splitlines()
    second: dict[str, Any] = json.loads(lines[1])
    second["lifecycle_events"][0]["post_total"] = 99
    path.write_bytes(lines[0] + b"\n" + policy.canonical_json_bytes(second) + b"\n")
    with pytest.raises(
        lineage.FeedLineageFatalError,
        match="lifecycle event hash differs",
    ):
        replay(path)


def test_foreign_launch_provenance_is_fatal(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    append(path, baseline())
    row: dict[str, Any] = json.loads(path.read_bytes())
    row["launch_nonce"] = "foreign-launch"
    path.write_bytes(policy.canonical_json_bytes(row) + b"\n")
    with pytest.raises(
        lineage.FeedLineageFatalError,
        match="launch provenance differs",
    ):
        replay(path)


@pytest.mark.parametrize("field_name", ["game_pk", "transition_sequence"])
def test_outer_boolean_or_float_integer_alias_is_fatal(
    tmp_path: Path,
    field_name: str,
) -> None:
    path = tmp_path / f"{field_name}.jsonl"
    append(path, baseline())
    row: dict[str, Any] = json.loads(path.read_bytes())
    row[field_name] = float(row[field_name])
    raw = policy.canonical_json_bytes(row)
    path.write_bytes(raw + b"\n")
    with pytest.raises(
        lineage.FeedLineageFatalError,
        match=f"lineage.{field_name} must be an exact integer",
    ):
        lineage.replay_feed_lineage(
            path,
            feed_anchor=ANCHOR,
            expected_event_count=1,
            expected_last_event_sha256=hashlib.sha256(raw).hexdigest(),
            trusted_root=tmp_path,
        )


def test_copied_log_cannot_fork_under_a_second_path(tmp_path: Path) -> None:
    original = tmp_path / "original.jsonl"
    copied = tmp_path / "copied.jsonl"
    snapshot = append(original, baseline())
    copied.write_bytes(original.read_bytes())
    with pytest.raises(
        lineage.FeedLineageFatalError,
        match="path binding differs",
    ):
        lineage.replay_feed_lineage(
            copied,
            feed_anchor=ANCHOR,
            expected_event_count=snapshot.event_count,
            expected_last_event_sha256=snapshot.last_event_sha256,
            trusted_root=tmp_path,
        )
    with pytest.raises(
        lineage.FeedLineageFatalError,
        match="retained snapshot (base )?lineage path differs",
    ):
        lineage.append_feed_transition(
            copied,
            baseline(game_pk=825000),
            feed_anchor=ANCHOR,
            recorded_at=recorded_at,
            expected_snapshot=snapshot,
            trusted_root=tmp_path,
        )


def test_forged_second_game_baseline_is_rejected_during_full_replay(
    tmp_path: Path,
) -> None:
    path = tmp_path / "first.jsonl"
    other_path = tmp_path / "other.jsonl"
    first = baseline()
    second = baseline(game_pk=825000)
    append(path, first)
    append(other_path, second)
    first_raw = path.read_bytes().removesuffix(b"\n")
    second_row: dict[str, Any] = json.loads(other_path.read_bytes())
    second_row["event_sequence"] = 2
    second_row["base_lineage_path"] = path.name
    second_row["lineage_path"] = path.name
    second_row["prior_lineage_event_sha256"] = hashlib.sha256(first_raw).hexdigest()
    second_row["game_heads_sha256"] = lineage._game_heads_sha256(
        {
            first.state.game_pk: first.state,
            second.state.game_pk: second.state,
        }
    )
    second_raw = policy.canonical_json_bytes(second_row)
    path.write_bytes(first_raw + b"\n" + second_raw + b"\n")

    with pytest.raises(
        lineage.FeedLineageFatalError,
        match="already bound to another game",
    ):
        lineage.replay_feed_lineage(
            path,
            feed_anchor=ANCHOR,
            expected_event_count=2,
            expected_last_event_sha256=hashlib.sha256(second_raw).hexdigest(),
            trusted_root=tmp_path,
        )


def test_non_utc_recorded_time_is_rejected_before_append(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    with pytest.raises(
        lineage.FeedLineageFatalError,
        match="timezone-aware UTC",
    ):
        lineage.append_feed_transition(
            path,
            baseline(),
            feed_anchor=ANCHOR,
            recorded_at=lambda: "2026-07-18T01:00:00-07:00",
            expected_snapshot=EMPTY_SNAPSHOT,
            trusted_root=tmp_path,
        )
    assert not path.exists()


def test_hard_linked_lineage_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    append(path, baseline())
    alias = tmp_path / "alias.jsonl"
    os.link(path, alias)
    with pytest.raises(
        lineage.FeedLineageFatalError,
        match="not singly owned",
    ):
        replay(path)


def test_exclusive_append_lock_prevents_same_head_concurrent_corruption(
    tmp_path: Path,
) -> None:
    path = tmp_path / "events.jsonl"
    first = baseline()
    head = append(path, first)
    candidate_a = trigger(first.state)
    candidate_b = observe(
        first.state,
        {"0": play(0, away=0, home=0, end_seconds=4)},
        observed_seconds=20,
        total=0,
    )
    lock_held = threading.Event()
    release = threading.Event()
    thread_errors: list[BaseException] = []
    thread_results: list[lineage.FeedLineageSnapshot] = []

    def slow_recorded_at() -> str:
        lock_held.set()
        if not release.wait(timeout=5):
            raise TimeoutError("test append lock was not released")
        return recorded_at()

    def first_writer() -> None:
        try:
            thread_results.append(lineage.append_feed_transition(
                path,
                candidate_a,
                feed_anchor=ANCHOR,
                recorded_at=slow_recorded_at,
                expected_snapshot=head,
                trusted_root=tmp_path,
            ))
        except BaseException as exc:
            thread_errors.append(exc)

    worker = threading.Thread(target=first_writer)
    worker.start()
    assert lock_held.wait(timeout=5)
    with pytest.raises(
        lineage.FeedLineageFatalError,
        match="append lock is already held",
    ):
        lineage.append_feed_transition(
            path,
            candidate_b,
            feed_anchor=ANCHOR,
            recorded_at=recorded_at,
            expected_snapshot=head,
            trusted_root=tmp_path,
        )
    release.set()
    worker.join(timeout=5)
    assert not worker.is_alive()
    assert thread_errors == []
    assert len(thread_results) == 1
    lines = path.read_bytes().splitlines()
    assert len(lines) == 2
    HEADS[path] = thread_results[0]
    assert replay(path).state_for(GAME_PK) == candidate_a.state
    assert replay(path).state_for(GAME_PK) != candidate_b.state


def test_append_lock_tampering_is_rejected_before_lineage_mutation(
    tmp_path: Path,
) -> None:
    path = tmp_path / "events.jsonl"
    lock_path = path.parent / f".{path.name}.v34append.lock"

    def tampering_recorded_at() -> str:
        lock_path.write_bytes(b"tampered")
        return recorded_at()

    with pytest.raises(
        lineage.FeedLineageFatalError,
        match="append lock (ownership|bytes) changed",
    ):
        lineage.append_feed_transition(
            path,
            baseline(),
            feed_anchor=ANCHOR,
            recorded_at=tampering_recorded_at,
            expected_snapshot=EMPTY_SNAPSHOT,
            trusted_root=tmp_path,
        )
    assert not path.exists()
    assert lock_path.read_bytes() in {b"", b"tampered"}
    lock_path.unlink()


def test_stale_append_lock_marker_is_recovered(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    lock_path = path.parent / f".{path.name}.v34append.lock"
    lock_path.write_bytes(b"stale process marker")

    snapshot = append(path, baseline())

    assert snapshot.event_count == 1
    assert lock_path.is_file()
    assert lock_path.read_bytes() == b""


def test_killed_process_releases_append_lock(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    code = "\n".join(
        (
            "import sys, time",
            "from pathlib import Path",
            "from scripts.v34.feed_lineage import _exclusive_append_lock",
            "path = Path(sys.argv[1])",
            "root = Path(sys.argv[2])",
            "with _exclusive_append_lock(path, trusted_root=root):",
            "    print('locked', flush=True)",
            "    time.sleep(600)",
        )
    )
    process = subprocess.Popen(  # noqa: S603
        [sys.executable, "-c", code, str(path), str(tmp_path)],
        cwd=policy.REPOSITORY_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert process.stdout is not None
        assert process.stdout.readline().strip() == "locked"
        process.kill()
        assert process.wait(timeout=10) != 0
        with lineage._exclusive_append_lock(path, trusted_root=tmp_path):
            pass
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=10)


def test_replay_cannot_recover_temp_while_writer_holds_lock(
    tmp_path: Path,
) -> None:
    path = tmp_path / "events.jsonl"
    initial = baseline()
    snapshot = append(path, initial)
    receipt = lineage._receipt_from_active_snapshot(
        snapshot,
        base_path=path,
        trusted_root=tmp_path,
        feed_anchor=ANCHOR,
    )
    archive_path = tmp_path / receipt.archive_path
    archive_path.parent.mkdir()
    temp_path = archive_path.parent / (
        f".{archive_path.name}.v34tmp-{'b' * 32}.tmp"
    )
    temp_path.write_bytes(path.read_bytes())
    lock_held = threading.Event()
    release = threading.Event()
    thread_errors: list[BaseException] = []

    def hold_writer_lock() -> None:
        try:
            with lineage._exclusive_append_lock(path, trusted_root=tmp_path):
                lock_held.set()
                if not release.wait(timeout=10):
                    raise TimeoutError("test writer lock was not released")
        except BaseException as exc:
            thread_errors.append(exc)

    worker = threading.Thread(target=hold_writer_lock)
    worker.start()
    assert lock_held.wait(timeout=5)
    try:
        with pytest.raises(
            lineage.FeedLineageFatalError,
            match="append lock is already held",
        ):
            replay(path)
        assert temp_path.is_file()
    finally:
        release.set()
        worker.join(timeout=10)
    assert not worker.is_alive()
    assert thread_errors == []
    assert replay(path) == snapshot
    assert not temp_path.exists()


@pytest.mark.parametrize(
    "mutation",
    ["active_prefix", "extra_archive", "extra_segment"],
)
def test_postwrite_closing_pass_rejects_mutation_and_extra_inventory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    path = tmp_path / "events.jsonl"
    initial = baseline()
    append(path, initial)
    original_append = lineage._append_exact_payload

    def mutate_after_append(*args: object, **kwargs: object) -> tuple[os.stat_result, str]:
        result = original_append(*args, **kwargs)
        after, _file_sha256 = result
        if mutation == "active_prefix":
            changed = bytearray(path.read_bytes())
            changed[0] = ord("[")
            path.write_bytes(changed)
            os.utime(path, ns=(after.st_atime_ns, after.st_mtime_ns))
        elif mutation == "extra_archive":
            archive_dir = tmp_path / f".{path.name}.sealed"
            archive_dir.mkdir()
            (archive_dir / "rogue.jsonl").write_bytes(b"rogue\n")
        else:
            lineage._segment_path(path, 2).write_bytes(b"rogue\n")
        return result

    monkeypatch.setattr(lineage, "_append_exact_payload", mutate_after_append)
    with pytest.raises(lineage.FeedLineageFatalError):
        append(path, trigger(initial.state))


def test_second_closing_pass_ends_with_full_active_hash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "events.jsonl"
    initial = baseline()
    first = append(path, initial)
    monkeypatch.setattr(
        lineage,
        "MAX_ACTIVE_SEGMENT_BYTES",
        first.file_size * 2,
    )
    original_terminal = lineage._read_bounded_terminal_event
    terminal_reads = 0

    def corrupt_during_second_closing_pass(
        candidate: Path,
        *,
        file_size: int,
    ) -> bytes:
        nonlocal terminal_reads
        raw = original_terminal(candidate, file_size=file_size)
        terminal_reads += 1
        if terminal_reads == 3:
            before = candidate.stat()
            changed = bytearray(candidate.read_bytes())
            changed[0] = ord("[")
            candidate.write_bytes(changed)
            os.utime(candidate, ns=(before.st_atime_ns, before.st_mtime_ns))
        return raw

    monkeypatch.setattr(
        lineage,
        "_read_bounded_terminal_event",
        corrupt_during_second_closing_pass,
    )
    with pytest.raises(
        lineage.FeedLineageFatalError,
        match="final retained hash differs",
    ):
        append(path, trigger(initial.state))
    assert terminal_reads == 3


def test_full_restart_rechecks_active_after_sealed_verification(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "events.jsonl"
    initial = baseline()
    first = append(path, initial)
    monkeypatch.setattr(
        lineage,
        "MAX_ACTIVE_SEGMENT_BYTES",
        first.file_size * 2,
    )
    snapshot = append(path, trigger(initial.state))
    active_path = lineage._segment_path(path, snapshot.active_segment_index)
    original_verify = lineage._verify_all_sealed_copies

    def mutate_active_after_sealed_check(*args: object, **kwargs: object) -> None:
        original_verify(*args, **kwargs)
        before = active_path.stat()
        changed = bytearray(active_path.read_bytes())
        changed[0] = ord("[")
        active_path.write_bytes(changed)
        os.utime(active_path, ns=(before.st_atime_ns, before.st_mtime_ns))

    monkeypatch.setattr(
        lineage,
        "_verify_all_sealed_copies",
        mutate_active_after_sealed_check,
    )
    with pytest.raises(lineage.FeedLineageFatalError):
        replay(path)


def test_full_restart_rechecks_sealed_identity_after_final_active_hash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "events.jsonl"
    initial = baseline()
    first = append(path, initial)
    monkeypatch.setattr(
        lineage,
        "MAX_ACTIVE_SEGMENT_BYTES",
        first.file_size * 2,
    )
    snapshot = append(path, trigger(initial.state))
    archive_path = tmp_path / snapshot.sealed_segments[0].archive_path
    original_hash = lineage._hash_owned_lineage

    def mutate_archive_after_active_hash(
        candidate: Path,
        *,
        expected_stat: os.stat_result,
    ) -> str:
        result = original_hash(candidate, expected_stat=expected_stat)
        changed = bytearray(archive_path.read_bytes())
        changed[0] = ord("[")
        archive_path.write_bytes(changed)
        return result

    monkeypatch.setattr(lineage, "_hash_owned_lineage", mutate_archive_after_active_hash)
    with pytest.raises(
        lineage.FeedLineageFatalError,
        match="sealed segment archive retained identity differs",
    ):
        replay(path)
