from __future__ import annotations

import hashlib
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from typing import TYPE_CHECKING

import pytest
from scripts.v34 import feed_archive as archive
from scripts.v34 import policy

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

SOURCE_HASHES = {
    source_name: hashlib.sha256((policy.REPOSITORY_ROOT / source_name).read_bytes()).hexdigest()
    for source_name in sorted(policy.REQUIRED_LAUNCH_SOURCES)
}
LAUNCH_BYTES = policy.canonical_json_bytes(
    {
        "created_at": "2026-07-18T00:00:00+00:00",
        "launch_nonce": "v34-feed-archive-test",
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
        "created_at": "2026-07-18T00:00:00+00:00",
        "launch_nonce": "v34-queue-archive-test",
        "manifest_kind": "v34_queue_launch",
        "output_root": policy.QUEUE_OUTPUT_ROOT,
        "policy_sha256": policy.POLICY_CANONICAL_SHA256,
        "run_signature": policy.QUEUE_RUN_SIGNATURE,
        "schema_version": policy.QUEUE_SCHEMA_VERSION,
        "source_hashes": QUEUE_SOURCE_HASHES,
    }
)
QUEUE_ANCHOR = policy.verify_queue_launch_manifest_bytes(QUEUE_LAUNCH_BYTES)


def coherent_pair(generation_id: str = "generation-1") -> archive.CoherentFeedPair:
    summary = policy.canonical_json_bytes(
        {**ANCHOR.provenance, "generation_id": generation_id, "marker": "a"}
    )
    receipt = policy.canonical_json_bytes(
        {
            **ANCHOR.provenance,
            "generation_id": generation_id,
            "summary_sha256": hashlib.sha256(summary).hexdigest(),
        }
    )
    return archive.CoherentFeedPair(generation_id, summary, receipt)


def archive_pair(
    tmp_path: Path,
    pair: archive.CoherentFeedPair | None = None,
    *,
    recorded_at: Callable[[], str] | None = None,
) -> archive.ArchivedFeedPair:
    selected_pair = coherent_pair() if pair is None else pair
    if recorded_at is None:
        return archive._archive_coherent_feed_pair_at_root(
            selected_pair,
            feed_anchor=ANCHOR,
            queue_anchor=QUEUE_ANCHOR,
            archive_root=tmp_path / "feed-archive",
            trusted_root=tmp_path,
        )
    return archive._archive_coherent_feed_pair_at_root(
        selected_pair,
        feed_anchor=ANCHOR,
        queue_anchor=QUEUE_ANCHOR,
        archive_root=tmp_path / "feed-archive",
        trusted_root=tmp_path,
        recorded_at=recorded_at,
    )


def test_coherent_pair_validates_exact_provenance_and_binding() -> None:
    coherent_pair().validate(ANCHOR)


def test_torn_receipt_retries_then_returns_stable_pair(tmp_path: Path) -> None:
    pair = coherent_pair()
    newer_receipt = pair.feed_receipt_bytes
    older_receipt = policy.canonical_json_bytes(
        {
            **ANCHOR.provenance,
            "generation_id": "older-generation",
            "summary_sha256": "0" * 64,
        }
    )
    receipt_path = tmp_path / "receipt.json"
    summary_path = tmp_path / "summary.json"
    receipt_reads = iter((older_receipt, newer_receipt, newer_receipt, newer_receipt))

    def reader(path: Path) -> bytes:
        if path == summary_path:
            return pair.summary_bytes
        return next(receipt_reads)

    clock = iter((0, 1_000_000, 2_000_000, 3_000_000, 4_000_000, 5_000_000))
    result = archive._read_coherent_feed_pair(
        summary_path,
        receipt_path,
        anchor=ANCHOR,
        read_bytes=reader,
        monotonic_ns=lambda: next(clock),
        sleep=lambda _: None,
    )
    assert result == pair


def test_read_budget_exhaustion_fails_without_returning_partial_pair(tmp_path: Path) -> None:
    pair = coherent_pair()
    clock = iter((0, 2_000_000_000, 2_000_000_001))

    def reader(path: Path) -> bytes:
        return pair.summary_bytes if path.name == "summary.json" else pair.feed_receipt_bytes

    with pytest.raises(archive.CoherentSnapshotUnavailableError, match="frozen read budget"):
        archive._read_coherent_feed_pair(
            tmp_path / "summary.json",
            tmp_path / "receipt.json",
            anchor=ANCHOR,
            read_bytes=reader,
            monotonic_ns=lambda: next(clock),
            sleep=lambda _: None,
        )


def test_archive_is_content_addressed_valid_and_idempotent(
    tmp_path: Path,
) -> None:
    pair = coherent_pair()
    first = archive_pair(
        tmp_path, pair, recorded_at=lambda: "2026-07-18T00:00:00+00:00"
    )
    second = archive_pair(
        tmp_path, pair, recorded_at=lambda: "2026-07-18T01:00:00+00:00"
    )
    expected = tmp_path / "feed-archive" / pair.generation_id / pair.summary_sha256
    assert first == second
    assert first.archive_receipt_bytes == (expected / "archive.receipt.json").read_bytes()
    assert (expected / "summary.json").read_bytes() == pair.summary_bytes
    assert (expected / "summary.receipt.json").read_bytes() == pair.feed_receipt_bytes
    first.validate(ANCHOR, QUEUE_ANCHOR)


def test_existing_different_summary_bytes_are_a_fatal_collision(
    tmp_path: Path,
) -> None:
    pair = coherent_pair()
    directory = tmp_path / "feed-archive" / pair.generation_id / pair.summary_sha256
    directory.mkdir(parents=True)
    (directory / "summary.json").write_bytes(b"different")
    with pytest.raises(archive.ArchiveCollisionError, match="collision"):
        archive_pair(tmp_path, pair)


@pytest.mark.parametrize("generation", ["../escape", "two..dots", ".", "bad/slash", ""])
def test_generation_id_cannot_escape_content_addressed_root(generation: str) -> None:
    with pytest.raises(ValueError, match="generation ID"):
        coherent_pair(generation).validate(ANCHOR)


def test_forged_launch_anchor_is_reverified_before_read_or_archive(tmp_path: Path) -> None:
    pair = coherent_pair()
    forged = replace(ANCHOR, provenance_bytes=b"{}")
    with pytest.raises(ValueError, match="derivation mismatch"):
        pair.validate(forged)


def test_noncanonical_summary_and_wrong_receipt_hash_fail() -> None:
    pair = coherent_pair()
    with pytest.raises(ValueError, match="canonical"):
        replace(pair, summary_bytes=pair.summary_bytes + b" ").validate(ANCHOR)
    receipt = policy.canonical_json_bytes(
        {
            **ANCHOR.provenance,
            "generation_id": pair.generation_id,
            "summary_sha256": "0" * 64,
        }
    )
    with pytest.raises(ValueError, match="hash mismatch"):
        replace(pair, feed_receipt_bytes=receipt).validate(ANCHOR)


def test_archive_recorded_at_must_be_timezone_aware(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        archive_pair(
            tmp_path, recorded_at=lambda: "2026-07-18T00:00:00"
        )


def test_existing_archive_receipt_with_wrong_path_is_a_collision(
    tmp_path: Path,
) -> None:
    pair = coherent_pair()
    archived = archive_pair(
        tmp_path, pair, recorded_at=lambda: "2026-07-18T00:00:00+00:00"
    )
    receipt = archive._parse_canonical_object(
        archived.archive_receipt_bytes, field="archive receipt"
    )
    receipt["archive_path"] = str(tmp_path / "wrong")
    receipt_path = (
        tmp_path
        / "feed-archive"
        / pair.generation_id
        / pair.summary_sha256
        / "archive.receipt.json"
    )
    receipt_path.write_bytes(policy.canonical_json_bytes(receipt))
    with pytest.raises(archive.ArchiveCollisionError, match="binding differs"):
        archive_pair(tmp_path, pair)


def test_archive_receipt_binds_fresh_queue_launch(tmp_path: Path) -> None:
    archived = archive_pair(tmp_path)
    receipt = archive._parse_canonical_object(
        archived.archive_receipt_bytes,
        field="archive receipt",
    )
    assert receipt["queue_provenance"] == QUEUE_ANCHOR.provenance
    foreign = dict(QUEUE_ANCHOR.provenance)
    foreign["launch_nonce"] = "foreign-queue-launch"
    receipt["queue_provenance"] = foreign
    forged = replace(
        archived,
        archive_receipt_bytes=policy.canonical_json_bytes(receipt),
    )
    with pytest.raises(ValueError, match="queue launch provenance mismatch"):
        forged.validate(ANCHOR, QUEUE_ANCHOR)


def test_every_new_directory_name_is_fsynced(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    synced: list[Path] = []
    monkeypatch.setattr(archive, "_fsync_directory", synced.append)
    pair = coherent_pair()
    archive_pair(tmp_path, pair)
    root = tmp_path / "feed-archive"
    generation = root / pair.generation_id
    content = generation / pair.summary_sha256
    assert root in synced
    assert generation in synced
    assert content in synced
    assert tmp_path in synced


def test_existing_directory_chain_is_adopted_with_parent_fsync(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive_root = tmp_path / "feed-archive"
    archive_root.mkdir()
    synced: list[Path] = []
    monkeypatch.setattr(archive, "_fsync_directory", synced.append)
    archive._ensure_durable_directory(tmp_path, archive_root)
    assert archive_root in synced
    assert tmp_path in synced


def test_archive_receipt_is_reread_from_disk_before_return(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = archive._write_create_once

    def corrupt_after_write(path: Path, value: bytes) -> None:
        original(path, value)
        if path.name == "archive.receipt.json":
            path.write_bytes(b"{}")

    monkeypatch.setattr(archive, "_write_create_once", corrupt_after_write)
    with pytest.raises(archive.ArchiveCollisionError, match="fields differ"):
        archive_pair(tmp_path)


def test_final_receipt_reread_cannot_change_after_schema_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = archive._validate_archive_receipt
    calls = 0

    def mutate_after_validation(
        raw: bytes,
        **kwargs: object,
    ) -> None:
        nonlocal calls
        original(raw, **kwargs)
        calls += 1
        if calls != 1:
            return
        receipt = archive._parse_canonical_object(raw, field="archive receipt")
        receipt["archive_path"] = str(tmp_path / "forged-path")
        receipt_path = (
            tmp_path
            / "feed-archive"
            / "generation-1"
            / coherent_pair().summary_sha256
            / "archive.receipt.json"
        )
        receipt_path.write_bytes(
            policy.canonical_json_bytes(receipt)
        )

    monkeypatch.setattr(archive, "_validate_archive_receipt", mutate_after_validation)
    with pytest.raises(archive.ArchiveCollisionError, match="changed after schema"):
        archive_pair(tmp_path)


def test_existing_member_with_external_hard_link_is_rejected(tmp_path: Path) -> None:
    pair = coherent_pair()
    archive_pair(tmp_path, pair)
    summary_path = (
        tmp_path
        / "feed-archive"
        / pair.generation_id
        / pair.summary_sha256
        / "summary.json"
    )
    outside_link = tmp_path / "outside-summary-link.json"
    os.link(summary_path, outside_link)
    with pytest.raises(archive.ArchiveCollisionError, match="singly owned"):
        archive_pair(tmp_path, pair)


def test_internal_temp_hard_link_is_recovered_before_validation(
    tmp_path: Path,
) -> None:
    directory = tmp_path / "archive"
    directory.mkdir()
    target = directory / "summary.json"
    value = b"stable"
    target.write_bytes(value)
    leftover = directory / ".summary.json.v34tmp-crash.tmp"
    os.link(target, leftover)
    archive._write_create_once(target, value)
    assert not leftover.exists()
    assert target.stat().st_nlink == 1


def test_simultaneous_identical_archives_adopt_one_durable_receipt(
    tmp_path: Path,
) -> None:
    for index in range(12):
        pair = coherent_pair(f"concurrent-generation-{index}")

        def run(
            timestamp: str,
            selected_pair: archive.CoherentFeedPair,
        ) -> archive.ArchivedFeedPair:
            return archive_pair(
                tmp_path,
                selected_pair,
                recorded_at=lambda: timestamp,
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(run, "2026-07-18T00:00:00+00:00", pair)
            second = executor.submit(run, "2026-07-18T00:00:01+00:00", pair)
            first_result = first.result()
            second_result = second.result()
        assert first_result == second_result


def test_failed_link_never_leaves_a_partial_final_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "member.json"

    def fail_link(*args: object, **kwargs: object) -> None:
        raise OSError("simulated crash before final link")

    monkeypatch.setattr(archive.os, "link", fail_link)
    with pytest.raises(OSError, match="simulated crash"):
        archive._write_create_once(target, b"complete bytes")
    assert not target.exists()
    assert list(tmp_path.iterdir()) == []


def test_symlinked_archive_ancestor_is_rejected(tmp_path: Path) -> None:
    actual = tmp_path / "actual"
    actual.mkdir()
    link = tmp_path / "redirect"
    try:
        link.symlink_to(actual, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlink creation is unavailable")
    with pytest.raises(archive.ArchiveCollisionError, match="redirects"):
        archive._archive_coherent_feed_pair_at_root(
            coherent_pair(),
            feed_anchor=ANCHOR,
            queue_anchor=QUEUE_ANCHOR,
            archive_root=link / "feed-archive",
            trusted_root=tmp_path,
        )


def test_windows_junction_signal_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    junction = tmp_path / "junction"
    junction.mkdir()
    path_type = type(junction)
    original = path_type.is_junction

    def fake_is_junction(self: Path) -> bool:
        return self == junction or original(self)

    monkeypatch.setattr(path_type, "is_junction", fake_is_junction)
    with pytest.raises(archive.ArchiveCollisionError, match="redirects"):
        archive._assert_no_redirecting_components(tmp_path, junction / "child")


def test_non_utc_archive_time_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="must be UTC"):
        archive_pair(
            tmp_path,
            recorded_at=lambda: "2026-07-18T01:00:00+01:00",
        )
