from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from scripts.v34 import feed_lifecycle as lifecycle
from scripts.v34 import feed_lineage as lineage
from scripts.v34 import head_ledger as ledger
from scripts.v34 import policy

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

BASE = datetime(2026, 7, 19, tzinfo=UTC)
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
        "launch_nonce": "v34-head-ledger-test-nonce",
        "manifest_kind": "v34_feed_launch",
        "output_root": policy.FEED_OUTPUT_ROOT,
        "policy_sha256": policy.POLICY_CANONICAL_SHA256,
        "run_signature": policy.FEED_RUN_SIGNATURE,
        "schema_version": policy.FEED_SCHEMA_VERSION,
        "source_hashes": SOURCE_HASHES,
    }
)
ANCHOR = policy.verify_feed_launch_manifest_bytes(LAUNCH_BYTES)
QUEUE_SOURCE_HASHES = {
    source_name: hashlib.sha256(
        (policy.REPOSITORY_ROOT / source_name).read_bytes()
    ).hexdigest()
    for source_name in sorted(policy.REQUIRED_QUEUE_LAUNCH_SOURCES)
}
QUEUE_LAUNCH_BYTES = policy.canonical_json_bytes(
    {
        "created_at": BASE.isoformat(),
        "launch_nonce": "v34-head-ledger-queue-test-nonce",
        "manifest_kind": "v34_queue_launch",
        "output_root": policy.QUEUE_OUTPUT_ROOT,
        "policy_sha256": policy.POLICY_CANONICAL_SHA256,
        "run_signature": policy.QUEUE_RUN_SIGNATURE,
        "schema_version": policy.QUEUE_SCHEMA_VERSION,
        "source_hashes": QUEUE_SOURCE_HASHES,
    }
)
QUEUE_ANCHOR = policy.verify_queue_launch_manifest_bytes(QUEUE_LAUNCH_BYTES)
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
SOURCE_RECEIPT = hashlib.sha256(b"source receipt").hexdigest()
SOURCE_SUMMARY = hashlib.sha256(b"source summary").hexdigest()
SOURCE_ARCHIVE_RECEIPT = hashlib.sha256(b"source archive receipt").hexdigest()


def config(tmp_path: Path) -> ledger.HeadLedgerConfig:
    runtime_root = tmp_path / "runtime"
    custody_root = tmp_path / "custody"
    runtime_root.mkdir()
    custody_root.mkdir()
    return ledger.HeadLedgerConfig(
        runtime_root=runtime_root,
        custody_root=custody_root,
        feed_anchor=ANCHOR,
        queue_anchor=QUEUE_ANCHOR,
        created_at=BASE.isoformat(),
        custody_class="logical_read_only",
    )


def play(index: int, *, away: int, home: int, end_seconds: float) -> dict[str, object]:
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
    total: int,
) -> lifecycle.FeedTransition:
    return lifecycle.transition_game(
        prior,
        game_pk=GAME_PK,
        completed_plays=completed,
        official_current_total=total,
        abstract_state="Live",
        detailed_state="In Progress",
        observed_at=BASE + timedelta(seconds=observed_seconds),
        successful_poll_monotonic_ns=int(
            observed_seconds * lifecycle.NANOSECONDS_PER_SECOND
        ),
        expected_prior_state_commitment_sha256=(
            None if prior is None else prior.state_commitment_sha256
        ),
    )


def baseline() -> lifecycle.FeedTransition:
    return observe(
        None,
        {"0": play(0, away=0, home=0, end_seconds=4)},
        observed_seconds=10,
        total=0,
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


def register(candidate: ledger.HeadLedgerConfig) -> ledger.GameRegistration:
    ledger.initialize_head_ledger(candidate)
    return ledger.register_game(
        candidate,
        game_pk=GAME_PK,
        registered_at=(BASE + timedelta(seconds=1)).isoformat(),
    )


def append(
    candidate: ledger.HeadLedgerConfig,
    transition: lifecycle.FeedTransition,
    expected_snapshot: lineage.FeedLineageSnapshot,
    *,
    fault_hook: Callable[[str], None] | None = None,
) -> ledger.CommittedFeedTransition:
    return ledger._append_single_committed_transition_for_test(
        candidate,
        transition,
        recorded_at=lambda: (BASE + timedelta(hours=1)).isoformat(),
        expected_snapshot=expected_snapshot,
        source_archive_path=str(candidate.runtime_root / "source-archive"),
        source_archive_receipt_sha256=SOURCE_ARCHIVE_RECEIPT,
        source_feed_receipt_sha256=SOURCE_RECEIPT,
        source_feed_summary_sha256=SOURCE_SUMMARY,
        source_generation_id="head-ledger-test-generation",
        fault_hook=fault_hook,
    )


def test_manifest_and_registration_are_exactly_mirrored(tmp_path: Path) -> None:
    candidate = config(tmp_path)
    manifest_sha256 = ledger.initialize_head_ledger(candidate)
    registration = register(candidate)
    assert registration.lineage_relative_path == "games/0000824999/feed.jsonl"
    assert registration.initial_head.event_count == 0
    assert not candidate.capital_eligible
    custody_manifest = (
        candidate.custody_control_root
        / "registry"
        / f"manifest-{manifest_sha256}.json"
    )
    primary_manifest = (
        candidate.primary_control_root
        / "registry"
        / f"manifest-{manifest_sha256}.json"
    )
    assert custody_manifest.read_bytes() == primary_manifest.read_bytes()
    custody_registrations = list(
        (candidate.custody_control_root / "registry" / "games").iterdir()
    )
    primary_registrations = list(
        (candidate.primary_control_root / "registry" / "games").iterdir()
    )
    assert [item.name for item in custody_registrations] == [
        item.name for item in primary_registrations
    ]
    assert custody_registrations[0].read_bytes() == primary_registrations[0].read_bytes()


def test_primary_only_manifest_is_terminal_and_does_not_recreate_custody(
    tmp_path: Path,
) -> None:
    candidate = config(tmp_path)
    manifest_sha256 = ledger.initialize_head_ledger(candidate)
    custody_manifest = (
        candidate.custody_control_root
        / "registry"
        / f"manifest-{manifest_sha256}.json"
    )
    custody_manifest.unlink()
    with pytest.raises(
        ledger.HeadLedgerFatalError,
        match="without custody authority",
    ):
        ledger.initialize_head_ledger(candidate)
    assert not custody_manifest.exists()


def test_missing_both_manifests_with_history_is_terminal(tmp_path: Path) -> None:
    candidate = config(tmp_path)
    manifest_sha256 = ledger.initialize_head_ledger(candidate)
    register(candidate)
    for control_root in (
        candidate.custody_control_root,
        candidate.primary_control_root,
    ):
        (control_root / "registry" / f"manifest-{manifest_sha256}.json").unlink()
    with pytest.raises(ledger.HeadLedgerFatalError, match="history exists"):
        ledger.initialize_head_ledger(candidate)


def test_unregistered_game_cannot_append(tmp_path: Path) -> None:
    candidate = config(tmp_path)
    ledger.initialize_head_ledger(candidate)
    with pytest.raises(ledger.HeadLedgerFatalError, match="not registered"):
        append(candidate, baseline(), EMPTY_SNAPSHOT)
    assert not (candidate.runtime_root / "games" / "0000824999").exists()


def test_baseline_and_transition_commit_before_recovery_credit(tmp_path: Path) -> None:
    candidate = config(tmp_path)
    register(candidate)
    first = append(candidate, baseline(), EMPTY_SNAPSHOT)
    assert first.snapshot.event_count == 1
    assert not first.capital_eligible
    recovered_first = ledger.recover_game(candidate, game_pk=GAME_PK)
    assert recovered_first == first.snapshot
    second = append(candidate, trigger(first.snapshot.game_states[0][1]), first.snapshot)
    assert second.snapshot.event_count == 2
    recovered_second = ledger.recover_game(candidate, game_pk=GAME_PK)
    assert recovered_second == second.snapshot
    for control_root in (
        candidate.custody_control_root,
        candidate.primary_control_root,
    ):
        transactions = list(
            (control_root / "transactions" / "0000824999").iterdir()
        )
        assert len(transactions) == 2
        assert all((item / "prepare.json").is_file() for item in transactions)
        assert all(len(list(item.glob("commit-*.json"))) == 1 for item in transactions)


def test_crash_after_prepare_resumes_exact_event(tmp_path: Path) -> None:
    candidate = config(tmp_path)
    register(candidate)

    def stop(stage: str) -> None:
        if stage == "after_prepare":
            raise RuntimeError("crash after prepare")

    with pytest.raises(RuntimeError, match="crash after prepare"):
        append(candidate, baseline(), EMPTY_SNAPSHOT, fault_hook=stop)
    lineage_path = candidate.runtime_root / ledger.canonical_lineage_relative_path(GAME_PK)
    assert not lineage_path.exists()
    recovered = ledger.recover_game(candidate, game_pk=GAME_PK)
    assert recovered.event_count == 1
    assert lineage_path.is_file()


def test_crash_after_lineage_append_commits_without_duplicate(tmp_path: Path) -> None:
    candidate = config(tmp_path)
    register(candidate)

    def stop(stage: str) -> None:
        if stage == "after_lineage_append":
            raise RuntimeError("crash after lineage append")

    with pytest.raises(RuntimeError, match="crash after lineage append"):
        append(candidate, baseline(), EMPTY_SNAPSHOT, fault_hook=stop)
    lineage_path = candidate.runtime_root / ledger.canonical_lineage_relative_path(GAME_PK)
    before = lineage_path.read_bytes()
    recovered = ledger.recover_game(candidate, game_pk=GAME_PK)
    assert recovered.event_count == 1
    assert lineage_path.read_bytes() == before
    assert len(before.splitlines()) == 1


def test_partial_append_is_terminal_and_never_truncated(tmp_path: Path) -> None:
    candidate = config(tmp_path)
    register(candidate)

    def stop(stage: str) -> None:
        if stage == "after_prepare":
            raise RuntimeError("crash after prepare")

    with pytest.raises(RuntimeError):
        append(candidate, baseline(), EMPTY_SNAPSHOT, fault_hook=stop)
    transaction = next(
        (candidate.custody_control_root / "transactions" / "0000824999").iterdir()
    )
    prepare = json.loads((transaction / "prepare.json").read_bytes())
    event_bytes = policy.canonical_json_bytes(prepare["planned_lineage_event"])
    lineage_path = candidate.runtime_root / ledger.canonical_lineage_relative_path(GAME_PK)
    lineage_path.write_bytes(event_bytes[: len(event_bytes) // 2])
    partial = lineage_path.read_bytes()
    with pytest.raises(ledger.HeadLedgerFatalError, match="exactly one candidate"):
        ledger.recover_game(candidate, game_pk=GAME_PK)
    assert lineage_path.read_bytes() == partial


def test_custody_commit_repairs_a_missing_primary_mirror(tmp_path: Path) -> None:
    candidate = config(tmp_path)
    register(candidate)
    committed = append(candidate, baseline(), EMPTY_SNAPSHOT)
    primary_transaction = next(
        (candidate.primary_control_root / "transactions" / "0000824999").iterdir()
    )
    primary_commit = next(primary_transaction.glob("commit-*.json"))
    primary_commit.unlink()
    recovered = ledger.recover_game(candidate, game_pk=GAME_PK)
    assert recovered == committed.snapshot
    assert len(list(primary_transaction.glob("commit-*.json"))) == 1


def test_custody_prelink_temps_recover_manifest_registration_and_transaction(
    tmp_path: Path,
) -> None:
    candidate = config(tmp_path)
    manifest_sha256 = ledger.initialize_head_ledger(candidate)
    registration = register(candidate)
    committed = append(candidate, baseline(), EMPTY_SNAPSHOT)
    custody_manifest = (
        candidate.custody_control_root
        / "registry"
        / f"manifest-{manifest_sha256}.json"
    )
    custody_registration = next(
        (candidate.custody_control_root / "registry" / "games").iterdir()
    )
    custody_transaction = next(
        (candidate.custody_control_root / "transactions" / "0000824999").iterdir()
    )
    records = [
        custody_manifest,
        custody_registration,
        custody_transaction / "prepare.json",
        next(custody_transaction.glob("commit-*.json")),
    ]
    orphan_paths = []
    for index, record in enumerate(records):
        raw = record.read_bytes()
        orphan = record.parent / (
            f".{record.name}.v34tmp-{index:032x}.tmp"
        )
        orphan.write_bytes(raw)
        record.unlink()
        orphan_paths.append(orphan)
    assert ledger.initialize_head_ledger(candidate) == manifest_sha256
    assert (
        ledger.register_game(
            candidate,
            game_pk=GAME_PK,
            registered_at=(BASE + timedelta(days=1)).isoformat(),
        )
        == registration
    )
    assert ledger.recover_game(candidate, game_pk=GAME_PK) == committed.snapshot
    assert all(record.is_file() for record in records)
    assert all(not orphan.exists() for orphan in orphan_paths)


def test_generic_ledger_postlink_temp_is_adopted(tmp_path: Path) -> None:
    candidate = config(tmp_path)
    register(candidate)
    committed = append(candidate, baseline(), EMPTY_SNAPSHOT)
    custody_transaction = next(
        (candidate.custody_control_root / "transactions" / "0000824999").iterdir()
    )
    prepare = custody_transaction / "prepare.json"
    orphan = prepare.parent / f".{prepare.name}.v34tmp-{'0' * 32}.tmp"
    os.link(prepare, orphan)
    assert prepare.stat().st_nlink == 2
    assert ledger.recover_game(candidate, game_pk=GAME_PK) == committed.snapshot
    assert prepare.stat().st_nlink == 1
    assert not orphan.exists()


def test_new_registration_is_rejected_after_first_transaction(tmp_path: Path) -> None:
    candidate = config(tmp_path)
    register(candidate)
    append(candidate, baseline(), EMPTY_SNAPSHOT)
    with pytest.raises(ledger.HeadLedgerFatalError, match="registry is frozen"):
        ledger.register_game(
            candidate,
            game_pk=GAME_PK + 1,
            registered_at=(BASE + timedelta(days=1)).isoformat(),
        )


def test_primary_only_commit_is_terminal(tmp_path: Path) -> None:
    candidate = config(tmp_path)
    register(candidate)
    append(candidate, baseline(), EMPTY_SNAPSHOT)
    custody_transaction = next(
        (candidate.custody_control_root / "transactions" / "0000824999").iterdir()
    )
    custody_commit = next(custody_transaction.glob("commit-*.json"))
    custody_commit.unlink()
    with pytest.raises(
        ledger.HeadLedgerFatalError,
        match="primary transaction record exists without custody authority",
    ):
        ledger.recover_game(candidate, game_pk=GAME_PK)


def test_independent_mode_rejects_same_physical_disk(tmp_path: Path) -> None:
    logical = config(tmp_path)
    independent = ledger.HeadLedgerConfig(
        runtime_root=logical.runtime_root,
        custody_root=logical.custody_root,
        feed_anchor=logical.feed_anchor,
        queue_anchor=logical.queue_anchor,
        created_at=logical.created_at,
        custody_class="independent_device",
    )
    with pytest.raises(
        ledger.HeadLedgerFatalError,
        match="disjoint physical disk",
    ):
        ledger.initialize_head_ledger(independent)


def test_missing_primary_registration_is_repaired_from_custody(
    tmp_path: Path,
) -> None:
    candidate = config(tmp_path)
    registration = register(candidate)
    primary_record = next(
        (candidate.primary_control_root / "registry" / "games").iterdir()
    )
    primary_record.unlink()
    recovered = ledger.register_game(
        candidate,
        game_pk=GAME_PK,
        registered_at=(BASE + timedelta(days=1)).isoformat(),
    )
    assert recovered == registration
    assert len(
        list((candidate.primary_control_root / "registry" / "games").iterdir())
    ) == 1


def test_duplicate_game_registration_is_terminal(tmp_path: Path) -> None:
    candidate = config(tmp_path)
    register(candidate)
    manifest_sha256 = ledger.registry_manifest_sha256(candidate)
    duplicate_raw = ledger._registration_record(
        candidate,
        game_pk=GAME_PK,
        registered_at=(BASE + timedelta(days=1)).isoformat(),
        manifest_sha256=manifest_sha256,
    )
    duplicate_sha256 = hashlib.sha256(duplicate_raw).hexdigest()
    duplicate_name = f"0000824999-{duplicate_sha256}.json"
    for control_root in (
        candidate.custody_control_root,
        candidate.primary_control_root,
    ):
        ledger._write_exact(
            control_root / "registry" / "games" / duplicate_name,
            duplicate_raw,
        )
    with pytest.raises(ledger.HeadLedgerFatalError, match="duplicate game_pk"):
        ledger.recover_game(candidate, game_pk=GAME_PK)


def test_empty_unpublished_transaction_container_is_recovered(
    tmp_path: Path,
) -> None:
    candidate = config(tmp_path)
    register(candidate)
    empty_name = f"{'1':0>12}-{'0' * 64}"
    for root in (
        candidate.custody_control_root,
        candidate.primary_control_root,
    ):
        game_directory = root / "transactions" / "0000824999"
        game_directory.mkdir()
        (game_directory / empty_name).mkdir()
    committed = append(candidate, baseline(), EMPTY_SNAPSHOT)
    assert committed.snapshot.event_count == 1
    for root in (
        candidate.custody_control_root,
        candidate.primary_control_root,
    ):
        assert not (
            root / "transactions" / "0000824999" / empty_name
        ).exists()


def test_runtime_root_inside_sync_directory_is_rejected(tmp_path: Path) -> None:
    sync_root = tmp_path / "OneDrive" / "runtime"
    custody_root = tmp_path / "custody"
    sync_root.mkdir(parents=True)
    custody_root.mkdir()
    candidate = ledger.HeadLedgerConfig(
        runtime_root=sync_root,
        custody_root=custody_root,
        feed_anchor=ANCHOR,
        queue_anchor=QUEUE_ANCHOR,
        created_at=BASE.isoformat(),
        custody_class="logical_read_only",
    )
    with pytest.raises(ledger.HeadLedgerFatalError, match="sync directory"):
        ledger.initialize_head_ledger(candidate)


def test_runtime_and_custody_roots_may_not_overlap(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    custody_root = runtime_root / "custody"
    custody_root.mkdir(parents=True)
    candidate = ledger.HeadLedgerConfig(
        runtime_root=runtime_root,
        custody_root=custody_root,
        feed_anchor=ANCHOR,
        queue_anchor=QUEUE_ANCHOR,
        created_at=BASE.isoformat(),
        custody_class="logical_read_only",
    )
    with pytest.raises(ledger.HeadLedgerFatalError, match="overlap"):
        ledger.initialize_head_ledger(candidate)


def test_rotated_transaction_commits_the_prepared_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = config(tmp_path)
    register(candidate)
    first = append(candidate, baseline(), EMPTY_SNAPSHOT)
    monkeypatch.setattr(
        lineage,
        "MAX_ACTIVE_SEGMENT_BYTES",
        first.snapshot.file_size * 2,
    )
    second = append(candidate, trigger(first.snapshot.game_states[0][1]), first.snapshot)
    assert second.snapshot.active_segment_index == 2
    assert len(second.snapshot.sealed_segments) == 1
    recovered = ledger.recover_game(candidate, game_pk=GAME_PK)
    assert recovered == second.snapshot
