from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import time
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from scripts.v34 import (
    batch_head_ledger as batch,
)
from scripts.v34 import (
    feed_archive,
    head_ledger,
    policy,
)
from scripts.v34 import (
    feed_lifecycle as lifecycle,
)
from scripts.v34 import (
    feed_lineage as lineage,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

BASE = datetime(2026, 7, 19, tzinfo=UTC)
GAME_PKS = (824998, 824999)
SOURCE_HASHES = {
    source_name: hashlib.sha256((policy.REPOSITORY_ROOT / source_name).read_bytes()).hexdigest()
    for source_name in sorted(policy.REQUIRED_LAUNCH_SOURCES)
}
LAUNCH_BYTES = policy.canonical_json_bytes(
    {
        "created_at": BASE.isoformat(),
        "launch_nonce": "v34-batch-head-ledger-test-nonce",
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
    source_name: hashlib.sha256((policy.REPOSITORY_ROOT / source_name).read_bytes()).hexdigest()
    for source_name in sorted(policy.REQUIRED_QUEUE_LAUNCH_SOURCES)
}
QUEUE_LAUNCH_BYTES = policy.canonical_json_bytes(
    {
        "created_at": BASE.isoformat(),
        "launch_nonce": "v34-batch-head-ledger-queue-test-nonce",
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


def config(tmp_path: Path) -> head_ledger.HeadLedgerConfig:
    runtime_root = tmp_path / "runtime"
    custody_root = tmp_path / "custody"
    runtime_root.mkdir()
    custody_root.mkdir()
    return head_ledger.HeadLedgerConfig(
        runtime_root=runtime_root,
        custody_root=custody_root,
        feed_anchor=ANCHOR,
        queue_anchor=QUEUE_ANCHOR,
        created_at=BASE.isoformat(),
        custody_class="logical_read_only",
    )


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
    game_pk: int,
    prior: lifecycle.FeedGameState | None,
    completed: dict[str, object],
    *,
    observed_seconds: float,
    total: int,
) -> lifecycle.FeedTransition:
    return lifecycle.transition_game(
        prior,
        game_pk=game_pk,
        completed_plays=completed,
        official_current_total=total,
        abstract_state="Live",
        detailed_state="In Progress",
        observed_at=BASE + timedelta(seconds=observed_seconds),
        successful_poll_monotonic_ns=int(observed_seconds * lifecycle.NANOSECONDS_PER_SECOND),
        expected_prior_state_commitment_sha256=(
            None if prior is None else prior.state_commitment_sha256
        ),
    )


def baseline(game_pk: int) -> lifecycle.FeedTransition:
    return observe(
        game_pk,
        None,
        {"0": play(0, away=0, home=0, end_seconds=4)},
        observed_seconds=10,
        total=0,
    )


def transition(
    game_pk: int,
    prior: lifecycle.FeedGameState,
    *,
    observed_seconds: float = 20,
) -> lifecycle.FeedTransition:
    return observe(
        game_pk,
        prior,
        {"0": play(0, away=0, home=0, end_seconds=4)},
        observed_seconds=observed_seconds,
        total=0,
    )


def padded_transition(
    game_pk: int,
    prior: lifecycle.FeedGameState | None,
    *,
    observed_seconds: float,
) -> lifecycle.FeedTransition:
    completed_play = play(0, away=0, home=0, end_seconds=4)
    result = completed_play["result"]
    assert isinstance(result, dict)
    result["description"] = "x" * 40_000
    return observe(
        game_pk,
        prior,
        {"0": completed_play},
        observed_seconds=observed_seconds,
        total=0,
    )


def register(candidate: head_ledger.HeadLedgerConfig) -> batch.BatchLedgerSession:
    head_ledger.initialize_head_ledger(candidate)
    for offset, game_pk in enumerate(GAME_PKS, start=1):
        head_ledger.register_game(
            candidate,
            game_pk=game_pk,
            registered_at=(BASE + timedelta(seconds=offset)).isoformat(),
        )
    return batch.open_batch_session(candidate)


def requests(
    transitions: tuple[lifecycle.FeedTransition, ...],
    snapshots: dict[int, lineage.FeedLineageSnapshot],
) -> tuple[batch.BatchTransitionRequest, ...]:
    return tuple(
        batch.BatchTransitionRequest(
            transition=item,
            recorded_at=(BASE + timedelta(hours=1)).isoformat(),
            expected_snapshot=snapshots[item.state.game_pk],
        )
        for item in transitions
    )


def append(
    session: batch.BatchLedgerSession,
    transitions: tuple[lifecycle.FeedTransition, ...],
    snapshots: dict[int, lineage.FeedLineageSnapshot],
    *,
    fault_hook: Callable[[str], None] | None = None,
    source_generation_id: str = "batch-source-generation",
) -> batch.CommittedFeedBatch:
    pair = feed_archive.CoherentFeedPair(
        generation_id=source_generation_id,
        summary_bytes=policy.canonical_json_bytes(
            {
                **ANCHOR.provenance,
                "generation_id": source_generation_id,
                "marker": "batch-source",
            }
        ),
        feed_receipt_bytes=b"",
    )
    pair = replace(
        pair,
        feed_receipt_bytes=policy.canonical_json_bytes(
            {
                **ANCHOR.provenance,
                "generation_id": pair.generation_id,
                "summary_sha256": pair.summary_sha256,
            }
        ),
    )
    return batch.append_committed_batch(
        session,
        requests(transitions, snapshots),
        source_pair=pair,
        fault_hook=fault_hook,
    )


def test_two_games_use_one_prepare_and_one_commit(tmp_path: Path) -> None:
    candidate = config(tmp_path)
    session = register(candidate)
    snapshots = {game_pk: EMPTY_SNAPSHOT for game_pk in GAME_PKS}
    committed = append(
        session,
        tuple(baseline(game_pk) for game_pk in reversed(GAME_PKS)),
        snapshots,
    )
    assert [game_pk for game_pk, _ in committed.snapshots] == list(GAME_PKS)
    assert not committed.capital_eligible
    for control_root in (
        candidate.custody_control_root,
        candidate.primary_control_root,
    ):
        transactions = list((control_root / "batches").iterdir())
        assert len(transactions) == 1
        assert (transactions[0] / "prepare.json").is_file()
        assert len(list(transactions[0].glob("commit-*.json"))) == 1
    recovered = batch.recover_batch_chain(candidate)
    assert dict(recovered) == dict(committed.snapshots)


def test_mutation_during_settle_fails_before_append_returns(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = config(tmp_path)
    session = register(candidate)
    real_settle = session.mutation_guard.settle_expected

    def mutate_then_settle() -> None:
        transactions = tuple(
            candidate.custody_control_root.joinpath("batches").iterdir()
        )
        if not transactions:
            real_settle()
            return
        transaction = transactions[0]
        transaction.joinpath("prepare.json").write_bytes(b"corrupt")
        time.sleep(0.2)
        real_settle()

    monkeypatch.setattr(session.mutation_guard, "settle_expected", mutate_then_settle)
    with pytest.raises(
        batch.BatchHeadLedgerFatalError,
        match="post-settle batch transaction bytes differ",
    ):
        append(
            session,
            tuple(baseline(game_pk) for game_pk in GAME_PKS),
            {game_pk: EMPTY_SNAPSHOT for game_pk in GAME_PKS},
        )
    transaction_name = next(
        candidate.custody_control_root.joinpath("batches").iterdir()
    ).name
    custody_prepare = candidate.custody_control_root / "batches" / transaction_name / "prepare.json"
    primary_prepare = candidate.primary_control_root / "batches" / transaction_name / "prepare.json"
    assert custody_prepare.read_bytes() == b"corrupt"
    assert custody_prepare.read_bytes() != primary_prepare.read_bytes()
    assert session.batch_count == 0
    assert session.latest_batch_name is None


def test_two_committed_batches_extend_all_heads(tmp_path: Path) -> None:
    candidate = config(tmp_path)
    session = register(candidate)
    snapshots = {game_pk: EMPTY_SNAPSHOT for game_pk in GAME_PKS}
    first = append(
        session,
        tuple(baseline(game_pk) for game_pk in GAME_PKS),
        snapshots,
    )
    snapshots = dict(first.snapshots)
    second = append(
        session,
        tuple(transition(game_pk, snapshots[game_pk].game_states[0][1]) for game_pk in GAME_PKS),
        snapshots,
    )
    assert all(snapshot.event_count == 2 for _, snapshot in second.snapshots)
    assert dict(batch.recover_batch_chain(candidate)) == dict(second.snapshots)


def test_hot_append_never_enumerates_historical_batch_roots(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = config(tmp_path)
    session = register(candidate)
    snapshots = {game_pk: EMPTY_SNAPSHOT for game_pk in GAME_PKS}
    first = append(
        session,
        tuple(baseline(game_pk) for game_pk in GAME_PKS),
        snapshots,
    )
    snapshots = dict(first.snapshots)
    forbidden = {
        candidate.custody_control_root / "batches",
        candidate.primary_control_root / "batches",
    }
    real_directory_names = head_ledger._directory_names

    def reject_historical_scan(path: Path) -> set[str]:
        if path in forbidden:
            raise AssertionError("hot append enumerated historical batch inventory")
        return real_directory_names(path)

    monkeypatch.setattr(
        head_ledger,
        "_directory_names",
        reject_historical_scan,
    )
    second = append(
        session,
        tuple(
            transition(game_pk, snapshots[game_pk].game_states[0][1])
            for game_pk in GAME_PKS
        ),
        snapshots,
    )
    assert all(snapshot.event_count == 2 for _, snapshot in second.snapshots)


def test_alternating_single_game_batches_preserve_untouched_hot_state(
    tmp_path: Path,
) -> None:
    candidate = config(tmp_path)
    session = register(candidate)
    first = append(
        session,
        (baseline(GAME_PKS[0]),),
        {GAME_PKS[0]: EMPTY_SNAPSHOT},
    )
    first_snapshot = dict(first.snapshots)[GAME_PKS[0]]
    second = append(
        session,
        (baseline(GAME_PKS[1]),),
        {GAME_PKS[1]: EMPTY_SNAPSHOT},
        source_generation_id="second-single-game-source",
    )
    second_snapshot = dict(second.snapshots)[GAME_PKS[1]]
    third = append(
        session,
        (transition(GAME_PKS[0], first_snapshot.game_states[0][1]),),
        {GAME_PKS[0]: first_snapshot},
        source_generation_id="third-single-game-source",
    )
    assert dict(third.snapshots)[GAME_PKS[0]].event_count == 2
    assert dict(session.snapshots)[GAME_PKS[1]] == second_snapshot


def test_live_session_rejects_older_batch_mutation(tmp_path: Path) -> None:
    candidate = config(tmp_path)
    session = register(candidate)
    snapshots = {game_pk: EMPTY_SNAPSHOT for game_pk in GAME_PKS}
    first = append(
        session,
        tuple(baseline(game_pk) for game_pk in GAME_PKS),
        snapshots,
    )
    transaction = next(candidate.custody_control_root.joinpath("batches").iterdir())
    prepare = transaction / "prepare.json"
    prepare.write_bytes(prepare.read_bytes())
    time.sleep(0.2)
    with pytest.raises(
        batch.BatchHeadLedgerFatalError,
        match="unexpected custody mutation",
    ):
        append(
            session,
            tuple(
                transition(game_pk, dict(first.snapshots)[game_pk].game_states[0][1])
                for game_pk in GAME_PKS
            ),
            dict(first.snapshots),
        )


def test_live_session_rejects_historical_source_mutation(tmp_path: Path) -> None:
    candidate = config(tmp_path)
    session = register(candidate)
    first = append(
        session,
        tuple(baseline(game_pk) for game_pk in GAME_PKS),
        {game_pk: EMPTY_SNAPSHOT for game_pk in GAME_PKS},
    )
    archived_summary = next(
        candidate.custody_root.joinpath("source-archive").rglob("summary.json")
    )
    archived_summary.write_bytes(archived_summary.read_bytes())
    time.sleep(0.2)
    with pytest.raises(
        batch.BatchHeadLedgerFatalError,
        match="unexpected custody mutation",
    ):
        append(
            session,
            tuple(
                transition(game_pk, dict(first.snapshots)[game_pk].game_states[0][1])
                for game_pk in GAME_PKS
            ),
            dict(first.snapshots),
        )


@pytest.mark.skipif(sys.platform != "win32", reason="production writer exclusion is Windows-first")
def test_live_session_blocks_active_lineage_mutation(tmp_path: Path) -> None:
    candidate = config(tmp_path)
    session = register(candidate)
    first = append(
        session,
        tuple(baseline(game_pk) for game_pk in GAME_PKS),
        {game_pk: EMPTY_SNAPSHOT for game_pk in GAME_PKS},
    )
    active = (
        candidate.runtime_root
        / head_ledger.canonical_lineage_relative_path(GAME_PKS[0])
    )
    with pytest.raises(PermissionError):
        active.write_bytes(active.read_bytes())
    committed = append(
        session,
        tuple(
            transition(game_pk, dict(first.snapshots)[game_pk].game_states[0][1])
            for game_pk in GAME_PKS
        ),
        dict(first.snapshots),
    )
    assert all(snapshot.event_count == 2 for _, snapshot in committed.snapshots)


@pytest.mark.skipif(sys.platform != "win32", reason="production writer exclusion is Windows-first")
def test_expected_window_cannot_tamper_with_active_prefix(tmp_path: Path) -> None:
    candidate = config(tmp_path)
    session = register(candidate)
    first = append(
        session,
        (baseline(GAME_PKS[0]),),
        {GAME_PKS[0]: EMPTY_SNAPSHOT},
    )
    first_snapshot = dict(first.snapshots)[GAME_PKS[0]]
    second = append(
        session,
        (transition(GAME_PKS[0], first_snapshot.game_states[0][1]),),
        {GAME_PKS[0]: first_snapshot},
        source_generation_id="writer-exclusion-second",
    )
    second_snapshot = dict(second.snapshots)[GAME_PKS[0]]
    active = candidate.runtime_root / head_ledger.canonical_lineage_relative_path(
        GAME_PKS[0]
    )
    tamper_blocked = False

    def try_prefix_tamper(stage: str) -> None:
        nonlocal tamper_blocked
        if stage != "after_prepare":
            return
        retained = active.stat()
        try:
            with active.open("r+b") as handle:
                handle.seek(0)
                handle.write(b"[")
                handle.flush()
                os.fsync(handle.fileno())
            os.utime(active, ns=(retained.st_atime_ns, retained.st_mtime_ns))
        except PermissionError:
            tamper_blocked = True

    third = append(
        session,
        (
            transition(
                GAME_PKS[0],
                second_snapshot.game_states[0][1],
                observed_seconds=30,
            ),
        ),
        {GAME_PKS[0]: second_snapshot},
        fault_hook=try_prefix_tamper,
        source_generation_id="writer-exclusion-third",
    )
    assert tamper_blocked
    assert active.read_bytes().startswith(b"{")
    assert dict(batch.recover_batch_chain(candidate))[GAME_PKS[0]] == dict(
        third.snapshots
    )[GAME_PKS[0]]


def test_startup_second_audit_detects_concurrent_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = config(tmp_path)
    session = register(candidate)
    append(
        session,
        tuple(baseline(game_pk) for game_pk in GAME_PKS),
        {game_pk: EMPTY_SNAPSHOT for game_pk in GAME_PKS},
    )
    session.close()
    real_scan = batch._scan_chain_locked
    scan_count = 0

    def mutate_after_watched_scan(*args: object, **kwargs: object) -> batch.BatchChainState:
        nonlocal scan_count
        state = real_scan(*args, **kwargs)
        scan_count += 1
        if scan_count == 2:
            transaction = next(
                candidate.custody_control_root.joinpath("batches").iterdir()
            )
            prepare = transaction / "prepare.json"
            prepare.write_bytes(prepare.read_bytes())
            time.sleep(0.2)
        return state

    monkeypatch.setattr(batch, "_scan_chain_locked", mutate_after_watched_scan)
    with pytest.raises(
        batch.BatchHeadLedgerFatalError,
        match="startup watcher observed a mutation",
    ):
        batch.open_batch_session(candidate)


def test_new_registration_is_rejected_after_first_batch(tmp_path: Path) -> None:
    candidate = config(tmp_path)
    session = register(candidate)
    snapshots = {game_pk: EMPTY_SNAPSHOT for game_pk in GAME_PKS}
    append(
        session,
        tuple(baseline(game_pk) for game_pk in GAME_PKS),
        snapshots,
    )
    with pytest.raises(head_ledger.HeadLedgerFatalError, match="registry is frozen"):
        head_ledger.register_game(
            candidate,
            game_pk=825000,
            registered_at=(BASE + timedelta(days=1)).isoformat(),
        )


def test_batch_requires_one_coherent_source_generation(tmp_path: Path) -> None:
    candidate = config(tmp_path)
    session = register(candidate)
    snapshots = {game_pk: EMPTY_SNAPSHOT for game_pk in GAME_PKS}
    request_rows = requests(
        tuple(baseline(game_pk) for game_pk in GAME_PKS),
        snapshots,
    )
    mismatched = (
        request_rows[0],
        replace(
            request_rows[1],
            recorded_at=(BASE + timedelta(hours=2)).isoformat(),
        ),
    )
    with pytest.raises(batch.BatchHeadLedgerFatalError, match="coherent source"):
        source_pair = feed_archive.CoherentFeedPair(
            "unused",
            b"{}",
            b"{}",
        )
        batch.append_committed_batch(
            session,
            mismatched,
            source_pair=source_pair,
        )
    assert not list((candidate.custody_control_root / "batches").iterdir())


def test_oversized_batch_is_rejected_before_transaction_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = config(tmp_path)
    session = register(candidate)
    snapshots = {game_pk: EMPTY_SNAPSHOT for game_pk in GAME_PKS}

    def oversized_record(*args: object, **kwargs: object) -> bytes:
        return b"x" * (batch.MAX_BATCH_RECORD_BYTES + 1)

    monkeypatch.setattr(batch, "_prepare_record", oversized_record)
    with pytest.raises(batch.BatchHeadLedgerFatalError, match="byte limit"):
        append(
            session,
            tuple(baseline(game_pk) for game_pk in GAME_PKS),
            snapshots,
        )
    assert not list((candidate.custody_control_root / "batches").iterdir())
    assert not list((candidate.primary_control_root / "batches").iterdir())


def test_oversized_source_is_rejected_before_archive_or_transaction(
    tmp_path: Path,
) -> None:
    candidate = config(tmp_path)
    session = register(candidate)
    generation_id = "oversized-source"
    summary = policy.canonical_json_bytes(
        {
            **ANCHOR.provenance,
            "generation_id": generation_id,
            "padding": "x" * batch.storage_preflight.MAX_SOURCE_PERSISTED_BYTES,
        }
    )
    oversized = feed_archive.CoherentFeedPair(
        generation_id=generation_id,
        summary_bytes=summary,
        feed_receipt_bytes=policy.canonical_json_bytes(
            {
                **ANCHOR.provenance,
                "generation_id": generation_id,
                "summary_sha256": hashlib.sha256(summary).hexdigest(),
            }
        ),
    )
    with pytest.raises(batch.BatchHeadLedgerFatalError, match="source pair exceeds"):
        batch.append_committed_batch(
            session,
            requests(
                tuple(baseline(game_pk) for game_pk in GAME_PKS),
                {game_pk: EMPTY_SNAPSHOT for game_pk in GAME_PKS},
            ),
            source_pair=oversized,
        )
    assert not tuple((candidate.custody_root / "source-archive").iterdir())
    assert not tuple((candidate.custody_control_root / "batches").iterdir())


def test_production_prepare_cap_is_checked_before_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = config(tmp_path)
    session = register(candidate)
    monkeypatch.setattr(batch.storage_preflight, "MAX_BATCH_PREPARE_BYTES", 1)
    with pytest.raises(batch.BatchHeadLedgerFatalError, match="production payload cap"):
        append(
            session,
            tuple(baseline(game_pk) for game_pk in GAME_PKS),
            {game_pk: EMPTY_SNAPSHOT for game_pk in GAME_PKS},
        )
    assert not tuple((candidate.custody_root / "source-archive").iterdir())
    assert not tuple((candidate.custody_control_root / "batches").iterdir())
    assert not tuple((candidate.primary_control_root / "batches").iterdir())


def test_production_commit_cap_is_checked_before_prepare_or_lineage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = config(tmp_path)
    session = register(candidate)
    monkeypatch.setattr(batch.storage_preflight, "MAX_BATCH_COMMIT_BYTES", 1)
    with pytest.raises(batch.BatchHeadLedgerFatalError, match="COMMIT exceeds"):
        append(
            session,
            tuple(baseline(game_pk) for game_pk in GAME_PKS),
            {game_pk: EMPTY_SNAPSHOT for game_pk in GAME_PKS},
        )
    assert not tuple((candidate.custody_control_root / "batches").iterdir())
    assert not tuple((candidate.primary_control_root / "batches").iterdir())
    assert not tuple((candidate.custody_root / "source-archive").iterdir())
    assert all(
        not (
            candidate.runtime_root
            / head_ledger.canonical_lineage_relative_path(game_pk)
        ).exists()
        for game_pk in GAME_PKS
    )


def test_aggregate_rotation_replica_cap_precedes_second_prepare(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = config(tmp_path)
    session = register(candidate)
    first = append(
        session,
        tuple(baseline(game_pk) for game_pk in GAME_PKS),
        {game_pk: EMPTY_SNAPSHOT for game_pk in GAME_PKS},
    )
    snapshots = dict(first.snapshots)
    active_limit = 2 * max(snapshot.file_size for snapshot in snapshots.values()) - 1
    monkeypatch.setattr(lineage, "MAX_ACTIVE_SEGMENT_BYTES", active_limit)
    monkeypatch.setattr(
        batch.storage_preflight,
        "MAX_ROTATION_REPLICA_BYTES",
        0,
    )
    before = {
        game_pk: (
            candidate.runtime_root
            / head_ledger.canonical_lineage_relative_path(game_pk)
        ).read_bytes()
        for game_pk in GAME_PKS
    }
    with pytest.raises(
        batch.BatchHeadLedgerFatalError,
        match="lineage exceeds the production payload cap",
    ):
        append(
            session,
            tuple(
                transition(game_pk, snapshots[game_pk].game_states[0][1])
                for game_pk in GAME_PKS
            ),
            snapshots,
            source_generation_id="rotation-cap-rejected-source",
        )
    assert len(tuple((candidate.custody_control_root / "batches").iterdir())) == 1
    assert {
        game_pk: (
            candidate.runtime_root
            / head_ledger.canonical_lineage_relative_path(game_pk)
        ).read_bytes()
        for game_pk in GAME_PKS
    } == before
    assert {
        entry.name
        for entry in (candidate.custody_root / "source-archive").iterdir()
    } == {"batch-source-generation"}


def test_cycle_horizon_is_checked_before_source_archive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = config(tmp_path)
    session = register(candidate)
    monkeypatch.setattr(batch.storage_preflight, "MAX_CYCLES", 0)
    with pytest.raises(batch.BatchHeadLedgerFatalError, match="cycle horizon"):
        append(
            session,
            tuple(baseline(game_pk) for game_pk in GAME_PKS),
            {game_pk: EMPTY_SNAPSHOT for game_pk in GAME_PKS},
        )
    assert not tuple((candidate.custody_root / "source-archive").iterdir())
    assert not tuple((candidate.custody_control_root / "batches").iterdir())


def test_crash_after_prepare_resumes_every_game(tmp_path: Path) -> None:
    candidate = config(tmp_path)
    session = register(candidate)
    snapshots = {game_pk: EMPTY_SNAPSHOT for game_pk in GAME_PKS}

    def stop(stage: str) -> None:
        if stage == "after_prepare":
            raise RuntimeError("crash after batch prepare")

    with pytest.raises(RuntimeError, match="crash after batch prepare"):
        append(
            session,
            tuple(baseline(game_pk) for game_pk in GAME_PKS),
            snapshots,
            fault_hook=stop,
        )
    assert all(
        not (candidate.runtime_root / head_ledger.canonical_lineage_relative_path(game_pk)).exists()
        for game_pk in GAME_PKS
    )
    recovered = batch.recover_batch_chain(candidate)
    assert all(snapshot.event_count == 1 for _, snapshot in recovered)


def test_exact_orphan_source_is_accounted_and_adopted_after_restart(
    tmp_path: Path,
) -> None:
    candidate = config(tmp_path)
    session = register(candidate)

    def stop(stage: str) -> None:
        if stage == "after_source_archive":
            raise RuntimeError("crash after source archive")

    with pytest.raises(RuntimeError, match="crash after source archive"):
        append(
            session,
            tuple(baseline(game_pk) for game_pk in GAME_PKS),
            {game_pk: EMPTY_SNAPSHOT for game_pk in GAME_PKS},
            fault_hook=stop,
        )
    session.close()
    assert not tuple((candidate.custody_control_root / "batches").iterdir())
    reopened = batch.open_batch_session(candidate)
    try:
        assert reopened.state.unreferenced_source_bytes > 0
        assert len(reopened.state.unreferenced_source_paths) == 1
        committed = append(
            reopened,
            tuple(baseline(game_pk) for game_pk in GAME_PKS),
            {game_pk: EMPTY_SNAPSHOT for game_pk in GAME_PKS},
        )
        assert committed.commit_sha256
        assert reopened.state.unreferenced_source_bytes == 0
        assert reopened.state.unreferenced_source_paths == ()
    finally:
        reopened.close()


def test_source_archive_member_inventory_is_exact_on_restart(tmp_path: Path) -> None:
    candidate = config(tmp_path)
    session = register(candidate)
    append(
        session,
        tuple(baseline(game_pk) for game_pk in GAME_PKS),
        {game_pk: EMPTY_SNAPSHOT for game_pk in GAME_PKS},
    )
    session.close()
    archive_directory = next(
        path
        for path in (candidate.custody_root / "source-archive").rglob("*")
        if path.is_dir() and (path / "archive.receipt.json").is_file()
    )
    (archive_directory / "unexpected.bin").write_bytes(b"unexpected")
    with pytest.raises(
        batch.BatchHeadLedgerFatalError,
        match="source archive cannot be revalidated",
    ):
        batch.open_batch_session(candidate)


def test_crash_recovery_rechecks_storage_before_lineage_or_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = config(tmp_path)
    session = register(candidate)

    def stop(stage: str) -> None:
        if stage == "after_prepare":
            raise RuntimeError("crash after batch prepare")

    with pytest.raises(RuntimeError, match="crash after batch prepare"):
        append(
            session,
            tuple(baseline(game_pk) for game_pk in GAME_PKS),
            {game_pk: EMPTY_SNAPSHOT for game_pk in GAME_PKS},
            fault_hook=stop,
        )
    session.close()
    real_disk_usage = batch.storage_preflight.shutil.disk_usage

    def no_free_space(path: Path) -> object:
        return real_disk_usage(path)._replace(free=1)

    monkeypatch.setattr(
        batch.storage_preflight.shutil,
        "disk_usage",
        no_free_space,
    )
    with pytest.raises(
        batch.BatchHeadLedgerFatalError,
        match="recovery startup storage preflight failed",
    ):
        batch.recover_batch_chain(candidate)
    assert all(
        not (
            candidate.runtime_root
            / head_ledger.canonical_lineage_relative_path(game_pk)
        ).exists()
        for game_pk in GAME_PKS
    )
    transaction = next((candidate.custody_control_root / "batches").iterdir())
    assert not tuple(transaction.glob("commit-*.json"))


@pytest.mark.parametrize(
    ("limit_name", "message"),
    [
        ("MAX_LINEAGE_BATCH_BYTES", "fresh recovery admission"),
        ("MAX_BATCH_COMMIT_BYTES", "fresh recovery admission"),
    ],
)
def test_crash_recovery_rechecks_exact_payload_caps_before_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    limit_name: str,
    message: str,
) -> None:
    candidate = config(tmp_path)
    session = register(candidate)

    def stop(stage: str) -> None:
        if stage == "after_prepare":
            raise RuntimeError("crash after batch prepare")

    with pytest.raises(RuntimeError, match="crash after batch prepare"):
        append(
            session,
            tuple(baseline(game_pk) for game_pk in GAME_PKS),
            {game_pk: EMPTY_SNAPSHOT for game_pk in GAME_PKS},
            fault_hook=stop,
        )
    session.close()
    monkeypatch.setattr(batch.storage_preflight, limit_name, 0)
    with pytest.raises(batch.BatchHeadLedgerFatalError, match=message):
        batch.recover_batch_chain(candidate)
    assert all(
        not (
            candidate.runtime_root
            / head_ledger.canonical_lineage_relative_path(game_pk)
        ).exists()
        for game_pk in GAME_PKS
    )
    transaction = next((candidate.custody_control_root / "batches").iterdir())
    assert not tuple(transaction.glob("commit-*.json"))


def test_crash_recovery_cannot_cross_cycle_horizon(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = config(tmp_path)
    session = register(candidate)

    def stop(stage: str) -> None:
        if stage == "after_prepare":
            raise RuntimeError("crash after batch prepare")

    with pytest.raises(RuntimeError, match="crash after batch prepare"):
        append(
            session,
            tuple(baseline(game_pk) for game_pk in GAME_PKS),
            {game_pk: EMPTY_SNAPSHOT for game_pk in GAME_PKS},
            fault_hook=stop,
        )
    session.close()
    monkeypatch.setattr(batch.storage_preflight, "MAX_CYCLES", 0)
    with pytest.raises(
        batch.BatchHeadLedgerFatalError,
        match="recovery exceeds the frozen cycle horizon",
    ):
        batch.recover_batch_chain(candidate)
    assert all(
        not (
            candidate.runtime_root
            / head_ledger.canonical_lineage_relative_path(game_pk)
        ).exists()
        for game_pk in GAME_PKS
    )


def test_crash_recovery_rejects_changed_source_archive(tmp_path: Path) -> None:
    candidate = config(tmp_path)
    session = register(candidate)

    def stop(stage: str) -> None:
        if stage == "after_prepare":
            raise RuntimeError("crash after batch prepare")

    with pytest.raises(RuntimeError, match="crash after batch prepare"):
        append(
            session,
            tuple(baseline(game_pk) for game_pk in GAME_PKS),
            {game_pk: EMPTY_SNAPSHOT for game_pk in GAME_PKS},
            fault_hook=stop,
        )
    session.close()
    archived_summary = next(
        candidate.custody_root.joinpath("source-archive").rglob("summary.json")
    )
    archived_summary.write_bytes(b"corrupt")
    with pytest.raises(
        batch.BatchHeadLedgerFatalError,
        match="source archive differs",
    ):
        batch.recover_batch_chain(candidate)
    transaction = next(candidate.custody_control_root.joinpath("batches").iterdir())
    assert not tuple(transaction.glob("commit-*.json"))


def test_crash_after_one_operation_recovers_mixed_prefix(tmp_path: Path) -> None:
    candidate = config(tmp_path)
    session = register(candidate)
    snapshots = {game_pk: EMPTY_SNAPSHOT for game_pk in GAME_PKS}

    def stop(stage: str) -> None:
        if stage == "after_lineage_operation_1":
            raise RuntimeError("crash after one operation")

    with pytest.raises(RuntimeError, match="crash after one operation"):
        append(
            session,
            tuple(baseline(game_pk) for game_pk in GAME_PKS),
            snapshots,
            fault_hook=stop,
        )
    first_path = candidate.runtime_root / head_ledger.canonical_lineage_relative_path(GAME_PKS[0])
    second_path = candidate.runtime_root / head_ledger.canonical_lineage_relative_path(GAME_PKS[1])
    assert first_path.is_file()
    assert not second_path.exists()
    recovered = batch.recover_batch_chain(candidate)
    assert all(snapshot.event_count == 1 for _, snapshot in recovered)
    assert len(first_path.read_bytes().splitlines()) == 1


def test_commit_callback_reverifies_before_publication(tmp_path: Path) -> None:
    candidate = config(tmp_path)
    session = register(candidate)
    snapshots = {game_pk: EMPTY_SNAPSHOT for game_pk in GAME_PKS}

    def corrupt(stage: str) -> None:
        if stage != "after_lineage_batch":
            return
        path = candidate.runtime_root / head_ledger.canonical_lineage_relative_path(GAME_PKS[0])
        dict(session.hot_integrities)[GAME_PKS[0]].close()
        path.write_bytes(b"corrupt\n")

    with pytest.raises(batch.BatchHeadLedgerFatalError, match="feed lineage batch"):
        append(
            session,
            tuple(baseline(game_pk) for game_pk in GAME_PKS),
            snapshots,
            fault_hook=corrupt,
        )
    transaction = next((candidate.custody_control_root / "batches").iterdir())
    assert not list(transaction.glob("commit-*.json"))


def test_custody_prepare_survives_primary_publication_crash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = config(tmp_path)
    session = register(candidate)
    snapshots = {game_pk: EMPTY_SNAPSHOT for game_pk in GAME_PKS}
    original = head_ledger._write_exact
    stopped = False

    def stop_at_primary_prepare(path: Path, raw: bytes) -> None:
        nonlocal stopped
        if (
            not stopped
            and path.name == "prepare.json"
            and candidate.primary_control_root in path.parents
        ):
            stopped = True
            raise RuntimeError("crash before primary PREPARE")
        original(path, raw)

    monkeypatch.setattr(head_ledger, "_write_exact", stop_at_primary_prepare)
    with pytest.raises(RuntimeError, match="crash before primary PREPARE"):
        append(
            session,
            tuple(baseline(game_pk) for game_pk in GAME_PKS),
            snapshots,
        )
    monkeypatch.setattr(head_ledger, "_write_exact", original)
    recovered = batch.recover_batch_chain(candidate)
    assert all(snapshot.event_count == 1 for _, snapshot in recovered)


def test_custody_commit_survives_primary_publication_crash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = config(tmp_path)
    session = register(candidate)
    snapshots = {game_pk: EMPTY_SNAPSHOT for game_pk in GAME_PKS}
    original = head_ledger._write_exact
    stopped = False

    def stop_at_primary_commit(path: Path, raw: bytes) -> None:
        nonlocal stopped
        if (
            not stopped
            and path.name.startswith("commit-")
            and candidate.primary_control_root in path.parents
        ):
            stopped = True
            raise RuntimeError("crash before primary COMMIT")
        original(path, raw)

    monkeypatch.setattr(head_ledger, "_write_exact", stop_at_primary_commit)
    with pytest.raises(RuntimeError, match="crash before primary COMMIT"):
        append(
            session,
            tuple(baseline(game_pk) for game_pk in GAME_PKS),
            snapshots,
        )
    monkeypatch.setattr(head_ledger, "_write_exact", original)
    recovered = batch.recover_batch_chain(candidate)
    assert all(snapshot.event_count == 1 for _, snapshot in recovered)


def test_partial_lineage_after_prepare_is_terminal_and_not_truncated(
    tmp_path: Path,
) -> None:
    candidate = config(tmp_path)
    session = register(candidate)
    snapshots = {game_pk: EMPTY_SNAPSHOT for game_pk in GAME_PKS}

    def stop(stage: str) -> None:
        if stage == "after_prepare":
            raise RuntimeError("crash after PREPARE")

    with pytest.raises(RuntimeError, match="crash after PREPARE"):
        append(
            session,
            tuple(baseline(game_pk) for game_pk in GAME_PKS),
            snapshots,
            fault_hook=stop,
        )
    lineage_path = candidate.runtime_root / head_ledger.canonical_lineage_relative_path(GAME_PKS[0])
    partial = b"partial lineage bytes\n"
    lineage_path.write_bytes(partial)
    with pytest.raises(batch.BatchHeadLedgerFatalError, match="cannot reconcile"):
        batch.recover_batch_chain(candidate)
    assert lineage_path.read_bytes() == partial


def test_killed_process_releases_all_batch_and_lineage_locks(tmp_path: Path) -> None:
    candidate = config(tmp_path)
    register(candidate)
    code = "\n".join(
        (
            "import sys, time",
            "from contextlib import ExitStack",
            "from pathlib import Path",
            "from scripts.v34 import feed_lineage, head_ledger, policy",
            "anchor = policy.verify_feed_launch_manifest_bytes(bytes.fromhex(sys.argv[3]))",
            "queue_anchor = policy.verify_queue_launch_manifest_bytes(bytes.fromhex(sys.argv[4]))",
            "config = head_ledger.HeadLedgerConfig(runtime_root=Path(sys.argv[1]), custody_root=Path(sys.argv[2]), feed_anchor=anchor, queue_anchor=queue_anchor, created_at=sys.argv[5], custody_class='logical_read_only')",
            "with head_ledger._control_locks(config):",
            "    with ExitStack() as stack:",
            "        for game_pk in (824998, 824999):",
            "            guard = config.runtime_root / head_ledger.canonical_lineage_relative_path(game_pk)",
            "            stack.enter_context(feed_lineage._exclusive_append_lock(guard, trusted_root=config.runtime_root))",
            "        print('locked', flush=True)",
            "        time.sleep(600)",
        )
    )
    process = subprocess.Popen(  # noqa: S603
        [
            sys.executable,
            "-c",
            code,
            str(candidate.runtime_root),
            str(candidate.custody_root),
            LAUNCH_BYTES.hex(),
            QUEUE_LAUNCH_BYTES.hex(),
            candidate.created_at,
        ],
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
        opened = batch.open_batch_session(candidate)
        assert opened.state.next_batch_sequence == 1
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=10)


def test_normal_restart_uses_remaining_horizon_not_new_full_horizon(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = config(tmp_path)
    session = register(candidate)
    result = append(
        session,
        tuple(baseline(game_pk) for game_pk in GAME_PKS),
        {game_pk: EMPTY_SNAPSHOT for game_pk in GAME_PKS},
    )
    session.close()
    full = batch.storage_preflight.project_storage(
        runtime_root=candidate.runtime_root,
        custody_root=candidate.custody_root,
        runtime_completed_cycles=0,
        custody_completed_cycles=0,
        outstanding_rotation_bytes=0,
        additional_runtime_bytes=0,
        additional_custody_bytes=0,
    )[0]
    remaining = batch.storage_preflight.project_storage(
        runtime_root=candidate.runtime_root,
        custody_root=candidate.custody_root,
        runtime_completed_cycles=1,
        custody_completed_cycles=1,
        outstanding_rotation_bytes=sum(
            snapshot.file_size for _, snapshot in result.snapshots
        ),
        additional_runtime_bytes=0,
        additional_custody_bytes=0,
    )[0]
    assert remaining.required_free_bytes < full.required_free_bytes
    admitted_free = (
        remaining.required_free_bytes + full.required_free_bytes
    ) // 2
    real_disk_usage = batch.storage_preflight.shutil.disk_usage

    def remaining_only_space(path: Path) -> object:
        return real_disk_usage(path)._replace(free=admitted_free)

    monkeypatch.setattr(
        batch.storage_preflight.shutil,
        "disk_usage",
        remaining_only_space,
    )
    reopened = batch.open_batch_session(candidate)
    try:
        assert reopened.batch_count == 1
        assert reopened.state.prior_commit_sha256 == result.commit_sha256
    finally:
        reopened.close()


def test_committed_runtime_restores_rotated_batch_into_fresh_generation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = config(tmp_path)
    session = register(candidate)
    snapshots = {game_pk: EMPTY_SNAPSHOT for game_pk in GAME_PKS}
    first = append(
        session,
        tuple(baseline(game_pk) for game_pk in GAME_PKS),
        snapshots,
    )
    snapshots = dict(first.snapshots)
    active_limit = 2 * max(snapshot.file_size for snapshot in snapshots.values()) - 1
    monkeypatch.setattr(lineage, "MAX_ACTIVE_SEGMENT_BYTES", active_limit)
    second = append(
        session,
        tuple(transition(game_pk, snapshots[game_pk].game_states[0][1]) for game_pk in GAME_PKS),
        snapshots,
    )
    assert all(len(snapshot.sealed_segments) == 1 for _, snapshot in second.snapshots)
    actual_lineage_bytes = sum(
        path.stat().st_size
        for path in candidate.runtime_root.rglob("*.jsonl")
        if path.is_file()
    )
    accounted_lineage_bytes = sum(
        snapshot.file_size
        + 2 * sum(receipt.file_size for receipt in snapshot.sealed_segments)
        for _, snapshot in second.snapshots
    )
    assert actual_lineage_bytes == accounted_lineage_bytes
    assert actual_lineage_bytes <= 2 * (
        2 * batch.storage_preflight.MAX_LINEAGE_BATCH_BYTES
        + batch.storage_preflight.PER_CYCLE_ROTATION_METADATA_ALLOWANCE_BYTES
    )
    fresh_root = tmp_path / "restored-runtime"
    restored = batch.restore_runtime_from_custody(
        custody_root=candidate.custody_root,
        fresh_runtime_root=fresh_root,
        feed_anchor=ANCHOR,
        queue_anchor=QUEUE_ANCHOR,
        restored_at=(BASE + timedelta(days=1)).isoformat(),
    )
    assert fresh_root.is_dir()
    assert {
        game_pk: lineage.portable_head_from_snapshot(snapshot, game_pk=game_pk)
        for game_pk, snapshot in restored.snapshots
    } == {
        game_pk: lineage.portable_head_from_snapshot(snapshot, game_pk=game_pk)
        for game_pk, snapshot in second.snapshots
    }
    for control_root in (
        restored.config.custody_control_root,
        restored.config.primary_control_root,
    ):
        restore_records = list((control_root / "registry" / "restores").iterdir())
        assert len(restore_records) == 1
        assert restored.restore_record_sha256 in restore_records[0].name
    restored_session = batch.open_batch_session(restored.config)
    restored_snapshots = dict(restored.snapshots)
    third = append(
        restored_session,
        tuple(
            transition(
                game_pk,
                restored_snapshots[game_pk].game_states[0][1],
                observed_seconds=30,
            )
            for game_pk in GAME_PKS
        ),
        restored_snapshots,
    )
    assert all(snapshot.event_count == 3 for _, snapshot in third.snapshots)


@pytest.mark.skipif(os.name != "nt", reason="production sole-writer custody is Windows-first")
def test_rotation_handoff_denies_write_through_final_settle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = config(tmp_path)
    session = register(candidate)
    snapshots = {game_pk: EMPTY_SNAPSHOT for game_pk in GAME_PKS}
    first = append(
        session,
        tuple(baseline(game_pk) for game_pk in GAME_PKS),
        snapshots,
    )
    snapshots = dict(first.snapshots)
    active_limit = 2 * max(snapshot.file_size for snapshot in snapshots.values()) - 1
    monkeypatch.setattr(lineage, "MAX_ACTIVE_SEGMENT_BYTES", active_limit)
    real_settle = session.mutation_guard.settle_expected
    settle_calls = 0
    denied = False

    def attempt_sealed_source_write_then_settle() -> None:
        nonlocal denied, settle_calls
        settle_calls += 1
        if settle_calls == 2:
            hot_integrity = dict(session.hot_integrities)[GAME_PKS[0]]
            source_path = hot_integrity.pending_sealed_descriptors[0][0]
            original_stat = source_path.stat()
            try:
                with source_path.open("r+b") as handle:
                    handle.seek(0)
                    handle.write(b"[")
                    handle.flush()
                    os.fsync(handle.fileno())
                os.utime(
                    source_path,
                    ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns),
                )
            except PermissionError:
                denied = True
        real_settle()

    monkeypatch.setattr(
        session.mutation_guard,
        "settle_expected",
        attempt_sealed_source_write_then_settle,
    )
    second = append(
        session,
        tuple(
            transition(game_pk, snapshots[game_pk].game_states[0][1])
            for game_pk in GAME_PKS
        ),
        snapshots,
    )
    assert settle_calls == 2
    assert denied
    assert all(
        not hot_integrity.pending_sealed_descriptors
        for _game_pk, hot_integrity in session.hot_integrities
    )
    session.close()
    recovered = batch.recover_batch_chain(candidate)
    assert dict(recovered) == dict(second.snapshots)


def test_rotation_hot_path_does_not_enumerate_sealed_archive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = config(tmp_path)
    session = register(candidate)
    snapshots = {game_pk: EMPTY_SNAPSHOT for game_pk in GAME_PKS}
    first = append(
        session,
        tuple(baseline(game_pk) for game_pk in GAME_PKS),
        snapshots,
    )
    snapshots = dict(first.snapshots)
    active_limit = 2 * max(snapshot.file_size for snapshot in snapshots.values()) - 1
    monkeypatch.setattr(lineage, "MAX_ACTIVE_SEGMENT_BYTES", active_limit)
    real_iterdir = Path.iterdir

    def reject_sealed_archive_scan(path: Path) -> Iterator[Path]:
        if path.name == ".feed.jsonl.sealed":
            raise AssertionError("rotation enumerated historical sealed archive")
        return real_iterdir(path)

    monkeypatch.setattr(Path, "iterdir", reject_sealed_archive_scan)
    second = append(
        session,
        tuple(
            transition(game_pk, snapshots[game_pk].game_states[0][1])
            for game_pk in GAME_PKS
        ),
        snapshots,
    )
    assert all(len(snapshot.sealed_segments) == 1 for _, snapshot in second.snapshots)


def test_hot_path_stays_bounded_across_repeated_rotations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = config(tmp_path)
    session = register(candidate)
    monkeypatch.setattr(lineage, "MAX_ACTIVE_SEGMENT_BYTES", 64 * 1024)
    snapshots = {game_pk: EMPTY_SNAPSHOT for game_pk in GAME_PKS}
    durations: list[float] = []
    for cycle in range(12):
        transitions = tuple(
            padded_transition(
                game_pk,
                snapshots[game_pk].state_for(game_pk),
                observed_seconds=10.0 + cycle * 10.0,
            )
            for game_pk in GAME_PKS
        )
        started = time.perf_counter()
        committed = append(
            session,
            transitions,
            snapshots,
            source_generation_id=f"rotation-soak-source-{cycle}",
        )
        durations.append(time.perf_counter() - started)
        snapshots = dict(committed.snapshots)
    assert min(len(snapshot.sealed_segments) for snapshot in snapshots.values()) >= 5
    assert max(durations[1:]) < batch.storage_preflight.POLL_TARGET_SECONDS
    assert max(durations[-4:]) <= max(durations[1:5]) * 2


def test_hot_rotation_never_iterates_retained_receipt_history(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = config(tmp_path)
    session = register(candidate)
    monkeypatch.setattr(lineage, "MAX_ACTIVE_SEGMENT_BYTES", 64 * 1024)
    snapshots = {game_pk: EMPTY_SNAPSHOT for game_pk in GAME_PKS}
    for cycle in range(6):
        committed = append(
            session,
            tuple(
                padded_transition(
                    game_pk,
                    snapshots[game_pk].state_for(game_pk),
                    observed_seconds=10.0 + cycle * 10.0,
                )
                for game_pk in GAME_PKS
            ),
            snapshots,
            source_generation_id=f"persistent-history-source-{cycle}",
        )
        snapshots = dict(committed.snapshots)
    assert min(len(snapshot.sealed_segments) for snapshot in snapshots.values()) >= 2
    monkeypatch.setattr(
        lineage,
        "MAX_ACTIVE_SEGMENT_BYTES",
        min(snapshot.file_size for snapshot in snapshots.values()) + 1,
    )

    def reject_history_iteration(_history: object) -> Iterator[object]:
        raise AssertionError("hot rotation iterated retained receipt history")

    monkeypatch.setattr(
        lineage._PersistentHistory,
        "__iter__",
        reject_history_iteration,
    )
    committed = append(
        session,
        tuple(
            padded_transition(
                    game_pk,
                    snapshots[game_pk].state_for(game_pk),
                    observed_seconds=70.0,
            )
            for game_pk in GAME_PKS
        ),
        snapshots,
        source_generation_id="persistent-history-no-iteration",
    )
    assert all(
        "sealed_segments" not in lineage.portable_head_from_snapshot(
            snapshot,
            game_pk=game_pk,
        ).to_dict()
        for game_pk, snapshot in committed.snapshots
    )


def test_restore_storage_failure_precedes_runtime_replay(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = config(tmp_path)
    session = register(candidate)
    append(
        session,
        tuple(baseline(game_pk) for game_pk in GAME_PKS),
        {game_pk: EMPTY_SNAPSHOT for game_pk in GAME_PKS},
    )
    session.close()
    real_disk_usage = batch.storage_preflight.shutil.disk_usage

    def no_free_space(path: Path) -> object:
        return real_disk_usage(path)._replace(free=1)

    monkeypatch.setattr(
        batch.storage_preflight.shutil,
        "disk_usage",
        no_free_space,
    )
    fresh_root = tmp_path / "storage-rejected-runtime"
    with pytest.raises(
        batch.BatchHeadLedgerFatalError,
        match="runtime restore storage preflight failed",
    ):
        batch.restore_runtime_from_custody(
            custody_root=candidate.custody_root,
            fresh_runtime_root=fresh_root,
            feed_anchor=ANCHOR,
            queue_anchor=QUEUE_ANCHOR,
            restored_at=(BASE + timedelta(days=1)).isoformat(),
        )
    assert fresh_root.is_dir()
    assert not tuple(fresh_root.rglob("*.jsonl"))
    assert not (fresh_root / "control").exists()


def test_restore_record_prelink_temp_is_recovered_from_custody(
    tmp_path: Path,
) -> None:
    candidate = config(tmp_path)
    session = register(candidate)
    snapshots = {game_pk: EMPTY_SNAPSHOT for game_pk in GAME_PKS}
    append(
        session,
        tuple(baseline(game_pk) for game_pk in GAME_PKS),
        snapshots,
    )
    first = batch.restore_runtime_from_custody(
        custody_root=candidate.custody_root,
        fresh_runtime_root=tmp_path / "first-restored-runtime",
        feed_anchor=ANCHOR,
        queue_anchor=QUEUE_ANCHOR,
        restored_at=(BASE + timedelta(days=1)).isoformat(),
    )
    restore_root = candidate.custody_control_root / "registry" / "restores"
    record = next(restore_root.iterdir())
    raw = record.read_bytes()
    orphan = restore_root / f".{record.name}.v34tmp-{'0' * 32}.tmp"
    orphan.write_bytes(raw)
    record.unlink()
    second = batch.restore_runtime_from_custody(
        custody_root=candidate.custody_root,
        fresh_runtime_root=tmp_path / "second-restored-runtime",
        feed_anchor=ANCHOR,
        queue_anchor=QUEUE_ANCHOR,
        restored_at=(BASE + timedelta(days=2)).isoformat(),
    )
    assert first.restore_record_sha256 != second.restore_record_sha256
    assert record.read_bytes() == raw
    assert not orphan.exists()


def test_restore_record_unknown_batch_commit_is_terminal(tmp_path: Path) -> None:
    candidate = config(tmp_path)
    session = register(candidate)
    snapshots = {game_pk: EMPTY_SNAPSHOT for game_pk in GAME_PKS}
    append(
        session,
        tuple(baseline(game_pk) for game_pk in GAME_PKS),
        snapshots,
    )
    batch.restore_runtime_from_custody(
        custody_root=candidate.custody_root,
        fresh_runtime_root=tmp_path / "first-restored-runtime",
        feed_anchor=ANCHOR,
        queue_anchor=QUEUE_ANCHOR,
        restored_at=(BASE + timedelta(days=1)).isoformat(),
    )
    restore_root = candidate.custody_control_root / "registry" / "restores"
    record = next(restore_root.iterdir())
    parsed = batch._canonical_object(
        record.read_bytes(),
        field="test restore record",
    )
    parsed["committed_batch_sha256"] = "1" * 64
    tampered = policy.canonical_json_bytes(parsed)
    tampered_sha256 = hashlib.sha256(tampered).hexdigest()
    record.unlink()
    (restore_root / f"{1:012d}-{tampered_sha256}.json").write_bytes(tampered)
    with pytest.raises(
        batch.BatchHeadLedgerFatalError,
        match="unknown batch COMMIT",
    ):
        batch.restore_runtime_from_custody(
            custody_root=candidate.custody_root,
            fresh_runtime_root=tmp_path / "second-restored-runtime",
            feed_anchor=ANCHOR,
            queue_anchor=QUEUE_ANCHOR,
            restored_at=(BASE + timedelta(days=2)).isoformat(),
        )
