"""Durable replayable lineage for v34 per-game feed lifecycle states."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, Never, cast
from uuid import uuid4

from scripts.v34 import feed_archive, policy
from scripts.v34 import feed_lifecycle as lifecycle
from scripts.v34 import prefix_dependency as prefix

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Mapping

MAX_LINEAGE_EVENTS: Final = 1_000_000
MAX_LINEAGE_EVENT_BYTES: Final = 16 * 1024 * 1024
MAX_ACTIVE_SEGMENT_BYTES: Final = 32 * 1024 * 1024
MAX_LINEAGE_FILE_BYTES: Final = MAX_ACTIVE_SEGMENT_BYTES
FILE_HASH_CHUNK_BYTES: Final = 1024 * 1024
STATE_KEYS: Final = {
    "eligible",
    "game_pk",
    "last_abstract_state",
    "last_completed_plays",
    "last_detailed_state",
    "last_observed_at",
    "last_official_current_total",
    "last_successful_poll_monotonic_ns",
    "pending",
    "prior_state_commitment_sha256",
    "seen_completed_indices",
    "state_commitment_sha256",
    "transition_sequence",
}
PENDING_KEYS: Final = {
    "candidate_start",
    "candidate_start_monotonic_ns",
    "game_pk",
    "ordered_prefix_fingerprint",
    "post_total",
    "pre_total",
    "run_delta",
    "t_seen",
    "t_seen_monotonic_ns",
    "trigger_at_bat_index",
    "trigger_play_identity",
}
BASIS_KEYS: Final = {
    "eligible_at",
    "game_pk",
    "ordered_prefix_fingerprint",
    "post_total",
    "pre_total",
    "run_delta",
    "t_seen",
    "trigger_at_bat_index",
    "trigger_play_identity",
}
ELIGIBLE_KEYS: Final = BASIS_KEYS | {
    "eligible_monotonic_ns",
    "t_seen_monotonic_ns",
}
LINEAGE_EVENT_KEYS: Final = set(policy.FEED_PROVENANCE_KEYS) | {
    "base_lineage_path",
    "event_sequence",
    "event_type",
    "game_pk",
    "game_heads_sha256",
    "lifecycle_event_sha256s",
    "lifecycle_events",
    "lineage_path",
    "prior_lineage_event_sha256",
    "recorded_at",
    "sealed_segments_sha256",
    "segment_index",
    "state",
    "state_bytes_sha256",
    "state_commitment_sha256",
    "transition_sequence",
}
SEGMENT_RECEIPT_KEYS: Final = {
    "archive_path",
    "base_lineage_path",
    "event_count",
    "file_sha256",
    "file_size",
    "first_event_sequence",
    "first_event_sha256",
    "first_prior_event_sha256",
    "last_event_sequence",
    "last_event_sha256",
    "launch_manifest_sha256",
    "lineage_path",
    "segment_index",
}


class FeedLineageFatalError(RuntimeError):
    """The append-only lineage is missing, corrupt, forked, or inconsistent."""


def _owned_lineage_stat(path: Path) -> os.stat_result | None:
    if not os.path.lexists(path):
        return None
    candidate = path.stat(follow_symlinks=False)
    if not stat.S_ISREG(candidate.st_mode):
        _fatal("feed lineage path is not a regular owned file")
    if candidate.st_nlink != 1:
        _fatal("feed lineage file is not singly owned")
    return candidate


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _fatal(message: str, *, cause: Exception | None = None) -> Never:
    error = FeedLineageFatalError(message)
    if cause is None:
        raise error
    raise error from cause


def _exact_int(value: object, *, field: str, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        _fatal(f"{field} must be an exact integer >= {minimum}")
    return value


def _parse_canonical_object(raw: bytes, *, field: str) -> dict[str, object]:
    if type(raw) is not bytes:
        _fatal(f"{field} must be immutable bytes")
    try:
        parsed = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        _fatal(f"{field} JSON is invalid", cause=exc)
    if not isinstance(parsed, dict):
        _fatal(f"{field} must be an object")
    row = cast("dict[str, object]", parsed)
    try:
        canonical = policy.canonical_json_bytes(row)
    except (TypeError, ValueError) as exc:
        _fatal(f"{field} is not finite canonical JSON", cause=exc)
    if canonical != raw:
        _fatal(f"{field} is not canonical JSON")
    return row


def _parse_utc(value: object, *, field: str) -> datetime:
    if type(value) is not str:
        _fatal(f"{field} must be a string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        _fatal(f"{field} is not ISO8601", cause=exc)
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        _fatal(f"{field} must be timezone-aware UTC")
    return parsed


def serialize_game_state(state: lifecycle.FeedGameState) -> bytes:
    """Return the exact restart bytes for one already validated game state."""

    try:
        lifecycle._validate_prior_state(state)
        completed = json.loads(state.last_completed_plays_bytes)
    except (TypeError, ValueError) as exc:
        _fatal("game state is invalid", cause=exc)
    if not isinstance(completed, dict):
        _fatal("game state completed plays are not an object")
    return policy.canonical_json_bytes(
        {
            "eligible": [row.to_dict() for row in state.eligible],
            "game_pk": state.game_pk,
            "last_abstract_state": state.last_abstract_state,
            "last_completed_plays": completed,
            "last_detailed_state": state.last_detailed_state,
            "last_observed_at": state.last_observed_at,
            "last_official_current_total": state.last_official_current_total,
            "last_successful_poll_monotonic_ns": (
                state.last_successful_poll_monotonic_ns
            ),
            "pending": [row.to_dict() for row in state.pending],
            "prior_state_commitment_sha256": (
                state.prior_state_commitment_sha256
            ),
            "seen_completed_indices": list(state.seen_completed_indices),
            "state_commitment_sha256": state.state_commitment_sha256,
            "transition_sequence": state.transition_sequence,
        }
    )


def deserialize_game_state(raw: bytes) -> lifecycle.FeedGameState:
    """Rebuild one state only after every exact field and commitment validates."""

    row = _parse_canonical_object(raw, field="game state")
    if set(row) != STATE_KEYS:
        _fatal("game state keys differ")
    pending_rows = row.get("pending")
    eligible_rows = row.get("eligible")
    seen_rows = row.get("seen_completed_indices")
    completed = row.get("last_completed_plays")
    if not isinstance(pending_rows, list) or not isinstance(eligible_rows, list):
        _fatal("game state trigger collections are not lists")
    if not isinstance(seen_rows, list) or not isinstance(completed, dict):
        _fatal("game state completed prefix fields are malformed")

    pending: list[lifecycle.PendingTrigger] = []
    for pending_row in pending_rows:
        if not isinstance(pending_row, dict) or set(pending_row) != PENDING_KEYS:
            _fatal("pending trigger keys differ")
        try:
            pending.append(lifecycle.PendingTrigger(**pending_row))
        except TypeError as exc:
            _fatal("pending trigger cannot be constructed", cause=exc)

    eligible: list[lifecycle.EligibleTrigger] = []
    for eligible_row in eligible_rows:
        if not isinstance(eligible_row, dict) or set(eligible_row) != ELIGIBLE_KEYS:
            _fatal("eligible trigger keys differ")
        basis_values = {key: eligible_row[key] for key in BASIS_KEYS}
        try:
            basis = prefix.TriggerBasis(**basis_values)
            eligible.append(
                lifecycle.EligibleTrigger(
                    basis=basis,
                    t_seen_monotonic_ns=eligible_row["t_seen_monotonic_ns"],
                    eligible_monotonic_ns=eligible_row["eligible_monotonic_ns"],
                )
            )
        except TypeError as exc:
            _fatal("eligible trigger cannot be constructed", cause=exc)

    try:
        state_values = cast("dict[str, Any]", row)
        state = lifecycle.FeedGameState(
            game_pk=state_values["game_pk"],
            seen_completed_indices=tuple(seen_rows),
            last_completed_plays_bytes=policy.canonical_json_bytes(completed),
            last_official_current_total=state_values["last_official_current_total"],
            last_abstract_state=state_values["last_abstract_state"],
            last_detailed_state=state_values["last_detailed_state"],
            last_observed_at=state_values["last_observed_at"],
            last_successful_poll_monotonic_ns=state_values[
                "last_successful_poll_monotonic_ns"
            ],
            pending=tuple(pending),
            eligible=tuple(eligible),
            transition_sequence=state_values["transition_sequence"],
            prior_state_commitment_sha256=state_values[
                "prior_state_commitment_sha256"
            ],
            state_commitment_sha256=state_values["state_commitment_sha256"],
        )
        lifecycle._validate_prior_state(state)
    except (TypeError, ValueError) as exc:
        _fatal("game state reconstruction failed", cause=exc)
    return state


@dataclass(frozen=True, slots=True)
class FeedSegmentReceipt:
    base_lineage_path: str
    lineage_path: str
    archive_path: str
    segment_index: int
    first_event_sequence: int
    last_event_sequence: int
    event_count: int
    first_prior_event_sha256: str | None
    first_event_sha256: str
    last_event_sha256: str
    file_size: int
    file_sha256: str
    launch_manifest_sha256: str

    def to_dict(self) -> dict[str, object]:
        return {
            "archive_path": self.archive_path,
            "base_lineage_path": self.base_lineage_path,
            "event_count": self.event_count,
            "file_sha256": self.file_sha256,
            "file_size": self.file_size,
            "first_event_sequence": self.first_event_sequence,
            "first_event_sha256": self.first_event_sha256,
            "first_prior_event_sha256": self.first_prior_event_sha256,
            "last_event_sequence": self.last_event_sequence,
            "last_event_sha256": self.last_event_sha256,
            "launch_manifest_sha256": self.launch_manifest_sha256,
            "lineage_path": self.lineage_path,
            "segment_index": self.segment_index,
        }


@dataclass(frozen=True, slots=True)
class FeedSealedIdentity:
    segment_index: int
    source_device: int
    source_inode: int
    source_mtime_ns: int
    archive_device: int
    archive_inode: int
    archive_mtime_ns: int


@dataclass(frozen=True, slots=True)
class FeedLineageSnapshot:
    event_count: int
    last_event_sha256: str | None
    game_states: tuple[tuple[int, lifecycle.FeedGameState], ...]
    file_size: int
    file_device: int | None
    file_inode: int | None
    file_mtime_ns: int | None
    lineage_path: str | None
    game_heads_sha256: str | None
    file_sha256: str | None
    base_lineage_path: str | None
    active_segment_index: int
    active_first_event_sequence: int | None
    active_first_prior_event_sha256: str | None
    active_first_event_sha256: str | None
    sealed_segments: tuple[FeedSegmentReceipt, ...]
    sealed_segments_sha256: str | None
    sealed_identities: tuple[FeedSealedIdentity, ...]

    def state_for(self, game_pk: int) -> lifecycle.FeedGameState | None:
        game_pk = _exact_int(game_pk, field="game_pk", minimum=1)
        return dict(self.game_states).get(game_pk)


def _game_heads_sha256(
    states: Mapping[int, lifecycle.FeedGameState],
) -> str:
    return policy.canonical_sha256(
        {
            "game_heads": [
                {
                    "game_pk": game_pk,
                    "state_commitment_sha256": state.state_commitment_sha256,
                    "transition_sequence": state.transition_sequence,
                }
                for game_pk, state in sorted(states.items())
            ]
        }
    )


def _sealed_segments_sha256(receipts: tuple[FeedSegmentReceipt, ...]) -> str:
    return policy.canonical_sha256(
        {"sealed_segments": [receipt.to_dict() for receipt in receipts]}
    )


def _segment_path(base_path: Path, segment_index: int) -> Path:
    index = _exact_int(segment_index, field="segment_index", minimum=1)
    if index == 1:
        return base_path
    return base_path.with_name(
        f"{base_path.stem}.segment-{index:06d}{base_path.suffix}"
    )


def _segment_archive_path(
    base_path: Path,
    *,
    segment_index: int,
    file_sha256: str,
) -> Path:
    try:
        digest = policy.validate_sha256(file_sha256, field="segment.file_sha256")
    except (TypeError, ValueError) as exc:
        _fatal("segment archive digest is invalid", cause=exc)
    return (
        base_path.parent
        / f".{base_path.name}.sealed"
        / f"segment-{segment_index:06d}-{digest}.jsonl"
    )


def _matching_segment_paths(base_path: Path) -> set[Path]:
    prefix = f"{base_path.stem}.segment-"
    suffix = base_path.suffix
    return {
        entry
        for entry in base_path.parent.iterdir()
        if entry.name.startswith(prefix) and entry.name.endswith(suffix)
    }


def _assert_empty_lineage_inventory_absent(base_path: Path) -> None:
    archive_dir = base_path.parent / f".{base_path.name}.sealed"
    if (
        os.path.lexists(base_path)
        or _matching_segment_paths(base_path)
        or os.path.lexists(archive_dir)
    ):
        _fatal("empty expected lineage inventory is not absent")


def _validate_segment_receipts(
    receipts: tuple[FeedSegmentReceipt, ...],
    *,
    base_path: Path,
    trusted_root: Path,
    feed_anchor: policy.FeedLaunchAnchor,
) -> None:
    if type(receipts) is not tuple:
        _fatal("sealed segment receipts are not an immutable tuple")
    base_lineage_path = _lineage_relative_path(base_path, trusted_root=trusted_root)
    prior_last_sequence = 0
    prior_last_sha: str | None = None
    for expected_index, receipt in enumerate(receipts, start=1):
        if not isinstance(receipt, FeedSegmentReceipt):
            _fatal("sealed segment receipt has the wrong type")
        if set(receipt.to_dict()) != SEGMENT_RECEIPT_KEYS:
            _fatal("sealed segment receipt keys differ")
        if receipt.base_lineage_path != base_lineage_path:
            _fatal("sealed segment receipt base path differs")
        if _exact_int(
            receipt.segment_index,
            field="segment.segment_index",
            minimum=1,
        ) != expected_index:
            _fatal("sealed segment receipt indexes are not contiguous")
        expected_path = _segment_path(base_path, expected_index)
        expected_lineage_path = _lineage_relative_path(
            expected_path,
            trusted_root=trusted_root,
        )
        if receipt.lineage_path != expected_lineage_path:
            _fatal("sealed segment receipt lineage path differs")
        expected_archive_path = _lineage_relative_path(
            _segment_archive_path(
                base_path,
                segment_index=expected_index,
                file_sha256=receipt.file_sha256,
            ),
            trusted_root=trusted_root,
        )
        if receipt.archive_path != expected_archive_path:
            _fatal("sealed segment receipt archive path differs")
        first_sequence = _exact_int(
            receipt.first_event_sequence,
            field="segment.first_event_sequence",
            minimum=1,
        )
        last_sequence = _exact_int(
            receipt.last_event_sequence,
            field="segment.last_event_sequence",
            minimum=1,
        )
        event_count = _exact_int(
            receipt.event_count,
            field="segment.event_count",
            minimum=1,
        )
        if first_sequence != prior_last_sequence + 1:
            _fatal("sealed segment global sequences are not contiguous")
        if last_sequence != first_sequence + event_count - 1:
            _fatal("sealed segment event count differs from its sequence range")
        if receipt.first_prior_event_sha256 != prior_last_sha:
            _fatal("sealed segment first prior head differs")
        for field_name, value in (
            ("first_event_sha256", receipt.first_event_sha256),
            ("last_event_sha256", receipt.last_event_sha256),
            ("file_sha256", receipt.file_sha256),
        ):
            try:
                policy.validate_sha256(value, field=f"segment.{field_name}")
            except (TypeError, ValueError) as exc:
                _fatal(f"sealed segment {field_name} is invalid", cause=exc)
        if _exact_int(receipt.file_size, field="segment.file_size", minimum=1) > (
            MAX_ACTIVE_SEGMENT_BYTES
        ):
            _fatal("sealed segment exceeds the active segment byte limit")
        if receipt.launch_manifest_sha256 != feed_anchor.manifest_sha256:
            _fatal("sealed segment launch provenance differs")
        prior_last_sequence = last_sequence
        prior_last_sha = receipt.last_event_sha256


def _receipt_from_active_snapshot(
    snapshot: FeedLineageSnapshot,
    *,
    base_path: Path,
    trusted_root: Path,
    feed_anchor: policy.FeedLaunchAnchor,
) -> FeedSegmentReceipt:
    if (
        snapshot.event_count <= 0
        or snapshot.active_segment_index <= 0
        or snapshot.active_first_event_sequence is None
        or snapshot.active_first_event_sha256 is None
        or snapshot.last_event_sha256 is None
        or snapshot.file_sha256 is None
        or snapshot.file_device is None
        or snapshot.file_inode is None
        or snapshot.file_mtime_ns is None
        or snapshot.lineage_path is None
        or snapshot.base_lineage_path is None
    ):
        _fatal("active snapshot cannot produce a sealed segment receipt")
    archive_path = _segment_archive_path(
        base_path,
        segment_index=snapshot.active_segment_index,
        file_sha256=snapshot.file_sha256,
    )
    return FeedSegmentReceipt(
        base_lineage_path=snapshot.base_lineage_path,
        lineage_path=snapshot.lineage_path,
        archive_path=_lineage_relative_path(archive_path, trusted_root=trusted_root),
        segment_index=snapshot.active_segment_index,
        first_event_sequence=snapshot.active_first_event_sequence,
        last_event_sequence=snapshot.event_count,
        event_count=snapshot.event_count - snapshot.active_first_event_sequence + 1,
        first_prior_event_sha256=snapshot.active_first_prior_event_sha256,
        first_event_sha256=snapshot.active_first_event_sha256,
        last_event_sha256=snapshot.last_event_sha256,
        file_size=snapshot.file_size,
        file_sha256=snapshot.file_sha256,
        launch_manifest_sha256=feed_anchor.manifest_sha256,
    )


def _recover_segment_archive_temps(
    archive_dir: Path,
    *,
    sealed_receipts: tuple[FeedSegmentReceipt, ...],
    pending_receipt: FeedSegmentReceipt,
    active_path: Path,
    trusted_root: Path,
) -> None:
    if not archive_dir.is_dir():
        return
    receipt_by_final = {
        trusted_root / Path(receipt.archive_path): receipt
        for receipt in (*sealed_receipts, pending_receipt)
    }
    for final_path in receipt_by_final:
        try:
            feed_archive._recover_internal_temp_link(final_path)
        except (OSError, ValueError, feed_archive.ArchiveCollisionError) as exc:
            _fatal("sealed segment linked-temp recovery failed", cause=exc)

    active_bytes: bytes | None = None
    for candidate in tuple(archive_dir.iterdir()):
        matched: tuple[Path, FeedSegmentReceipt] | None = None
        for final_path, receipt in receipt_by_final.items():
            prefix = f".{final_path.name}.v34tmp-"
            if not candidate.name.startswith(prefix) or not candidate.name.endswith(
                ".tmp"
            ):
                continue
            nonce = candidate.name[len(prefix) : -len(".tmp")]
            if len(nonce) != 32 or any(
                character not in "0123456789abcdef" for character in nonce
            ):
                continue
            matched = final_path, receipt
            break
        if matched is None:
            continue
        final_path, receipt = matched
        try:
            feed_archive._assert_no_redirecting_components(trusted_root, candidate)
            candidate_bytes = feed_archive._stable_owned_file_bytes(candidate)
        except (OSError, ValueError, feed_archive.ArchiveCollisionError) as exc:
            _fatal("sealed segment orphan temp cannot be verified", cause=exc)
        if (
            len(candidate_bytes) != receipt.file_size
            or _sha256(candidate_bytes) != receipt.file_sha256
        ):
            _fatal("sealed segment orphan temp differs from its receipt")
        if os.path.lexists(final_path):
            try:
                final_bytes = feed_archive._stable_owned_file_bytes(final_path)
            except (OSError, ValueError, feed_archive.ArchiveCollisionError) as exc:
                _fatal("sealed segment final cannot verify its orphan temp", cause=exc)
            if final_bytes != candidate_bytes:
                _fatal("sealed segment orphan temp differs from its final member")
        else:
            if final_path != trusted_root / Path(pending_receipt.archive_path):
                _fatal("sealed historical archive final is missing during temp recovery")
            if active_bytes is None:
                try:
                    active_bytes = feed_archive._stable_owned_file_bytes(active_path)
                except (OSError, ValueError, feed_archive.ArchiveCollisionError) as exc:
                    _fatal("active segment cannot verify its orphan temp", cause=exc)
            if active_bytes != candidate_bytes:
                _fatal("pending archive orphan temp differs from the active segment")
        try:
            candidate.unlink()
            feed_archive._fsync_directory(archive_dir)
        except OSError as exc:
            _fatal("verified sealed segment orphan temp cannot be removed", cause=exc)


def _verify_segment_inventory(
    snapshot: FeedLineageSnapshot,
    *,
    base_path: Path,
    active_path: Path,
    trusted_root: Path,
    feed_anchor: policy.FeedLaunchAnchor,
) -> bool:
    if type(snapshot.sealed_identities) is not tuple or len(
        snapshot.sealed_identities
    ) != len(snapshot.sealed_segments):
        _fatal("sealed segment runtime identities do not align with receipts")
    identities: dict[int, FeedSealedIdentity] = {}
    for expected_index, identity in enumerate(snapshot.sealed_identities, start=1):
        if not isinstance(identity, FeedSealedIdentity):
            _fatal("sealed segment runtime identity has the wrong type")
        if _exact_int(
            identity.segment_index,
            field="sealed_identity.segment_index",
            minimum=1,
        ) != expected_index:
            _fatal("sealed segment runtime identity indexes are not contiguous")
        for field_name, value in (
            ("source_device", identity.source_device),
            ("source_inode", identity.source_inode),
            ("source_mtime_ns", identity.source_mtime_ns),
            ("archive_device", identity.archive_device),
            ("archive_inode", identity.archive_inode),
            ("archive_mtime_ns", identity.archive_mtime_ns),
        ):
            _exact_int(value, field=f"sealed_identity.{field_name}")
        identities[expected_index] = identity
    expected_sources = {
        _segment_path(base_path, receipt.segment_index)
        for receipt in snapshot.sealed_segments
    }
    expected_sources.add(active_path)
    actual_sources = {base_path} if os.path.lexists(base_path) else set()
    actual_sources.update(_matching_segment_paths(base_path))
    if actual_sources != expected_sources:
        _fatal("feed lineage segment inventory differs")
    expected_archives = {
        trusted_root / Path(receipt.archive_path)
        for receipt in snapshot.sealed_segments
    }
    archive_dir = base_path.parent / f".{base_path.name}.sealed"
    pending_receipt = _receipt_from_active_snapshot(
        snapshot,
        base_path=base_path,
        trusted_root=trusted_root,
        feed_anchor=feed_anchor,
    )
    pending_archive = trusted_root / Path(pending_receipt.archive_path)
    if os.path.lexists(archive_dir):
        if not archive_dir.is_dir():
            _fatal("sealed archive inventory path is not a directory")
        try:
            feed_archive._assert_no_redirecting_components(
                trusted_root,
                archive_dir,
            )
        except (OSError, ValueError, feed_archive.ArchiveCollisionError) as exc:
            _fatal("sealed archive directory ancestry is not trusted", cause=exc)
    _recover_segment_archive_temps(
        archive_dir,
        sealed_receipts=snapshot.sealed_segments,
        pending_receipt=pending_receipt,
        active_path=active_path,
        trusted_root=trusted_root,
    )
    actual_archives = set(archive_dir.iterdir()) if archive_dir.is_dir() else set()
    pending_rotation = actual_archives == expected_archives | {pending_archive}
    if actual_archives != expected_archives and not pending_rotation:
        _fatal("feed lineage sealed archive inventory differs")
    for receipt in snapshot.sealed_segments:
        identity = identities[receipt.segment_index]
        source_path = trusted_root / Path(receipt.lineage_path)
        archive_path = trusted_root / Path(receipt.archive_path)
        for candidate, field_name in (
            (source_path, "source"),
            (archive_path, "archive"),
        ):
            try:
                feed_archive._assert_no_redirecting_components(
                    trusted_root,
                    candidate,
                )
            except (OSError, ValueError, feed_archive.ArchiveCollisionError) as exc:
                _fatal(f"sealed segment {field_name} ancestry is not trusted", cause=exc)
            candidate_stat = _owned_lineage_stat(candidate)
            if candidate_stat is None or candidate_stat.st_size != receipt.file_size:
                _fatal(f"sealed segment {field_name} identity or size differs")
            expected_identity = (
                (
                    identity.source_device,
                    identity.source_inode,
                    identity.source_mtime_ns,
                )
                if field_name == "source"
                else (
                    identity.archive_device,
                    identity.archive_inode,
                    identity.archive_mtime_ns,
                )
            )
            if (
                candidate_stat.st_dev,
                candidate_stat.st_ino,
                candidate_stat.st_mtime_ns,
            ) != expected_identity:
                _fatal(f"sealed segment {field_name} retained identity differs")
    if pending_rotation:
        try:
            pending_bytes = feed_archive._stable_owned_file_bytes(pending_archive)
            active_bytes = feed_archive._stable_owned_file_bytes(active_path)
        except (OSError, ValueError, feed_archive.ArchiveCollisionError) as exc:
            _fatal("pending rotation replica cannot be read", cause=exc)
        if (
            pending_bytes != active_bytes
            or len(active_bytes) != pending_receipt.file_size
            or _sha256(active_bytes) != pending_receipt.file_sha256
        ):
            _fatal("pending rotation replica differs from the retained active segment")
    return pending_rotation


def _seal_active_segment(
    path: Path,
    snapshot: FeedLineageSnapshot,
    *,
    base_path: Path,
    trusted_root: Path,
    feed_anchor: policy.FeedLaunchAnchor,
) -> tuple[FeedSegmentReceipt, FeedSealedIdentity]:
    receipt = _receipt_from_active_snapshot(
        snapshot,
        base_path=base_path,
        trusted_root=trusted_root,
        feed_anchor=feed_anchor,
    )
    try:
        source_bytes = feed_archive._stable_owned_file_bytes(path)
    except (OSError, ValueError, feed_archive.ArchiveCollisionError) as exc:
        _fatal("active segment cannot be read for sealing", cause=exc)
    if (
        len(source_bytes) != receipt.file_size
        or _sha256(source_bytes) != receipt.file_sha256
    ):
        _fatal("active segment bytes differ before sealing")
    archive_path = trusted_root / Path(receipt.archive_path)
    try:
        feed_archive._ensure_durable_directory(trusted_root, archive_path.parent)
        feed_archive._write_create_once(archive_path, source_bytes)
        archive_bytes = feed_archive._stable_owned_file_bytes(archive_path)
    except (OSError, ValueError, feed_archive.ArchiveCollisionError) as exc:
        _fatal("sealed segment replica publication failed", cause=exc)
    if archive_bytes != source_bytes:
        _fatal("sealed segment replica bytes differ")
    source_stat = _owned_lineage_stat(path)
    archive_stat = _owned_lineage_stat(archive_path)
    if source_stat is None or archive_stat is None:
        _fatal("sealed segment identity disappeared after publication")
    if (
        source_stat.st_dev != snapshot.file_device
        or source_stat.st_ino != snapshot.file_inode
        or source_stat.st_mtime_ns != snapshot.file_mtime_ns
    ):
        _fatal("sealed source identity changed during publication")
    feed_archive._fsync_directory(path.parent)
    identity = FeedSealedIdentity(
        segment_index=receipt.segment_index,
        source_device=source_stat.st_dev,
        source_inode=source_stat.st_ino,
        source_mtime_ns=source_stat.st_mtime_ns,
        archive_device=archive_stat.st_dev,
        archive_inode=archive_stat.st_ino,
        archive_mtime_ns=archive_stat.st_mtime_ns,
    )
    _verify_all_sealed_copies((receipt,), (identity,), trusted_root=trusted_root)
    return receipt, identity


def _verify_all_sealed_copies(
    receipts: tuple[FeedSegmentReceipt, ...],
    identities: tuple[FeedSealedIdentity, ...],
    *,
    trusted_root: Path,
) -> None:
    if len(receipts) != len(identities):
        _fatal("sealed segment final identities do not align with receipts")
    observations: list[tuple[Path, os.stat_result]] = []
    for receipt, identity in zip(receipts, identities, strict=True):
        if receipt.segment_index != identity.segment_index:
            _fatal("sealed segment final identity index differs")
        source_path = trusted_root / Path(receipt.lineage_path)
        archive_path = trusted_root / Path(receipt.archive_path)
        try:
            source_bytes = feed_archive._stable_owned_file_bytes(source_path)
            archive_bytes = feed_archive._stable_owned_file_bytes(archive_path)
        except (OSError, ValueError, feed_archive.ArchiveCollisionError) as exc:
            _fatal("sealed segment final verification cannot read a copy", cause=exc)
        if (
            source_bytes != archive_bytes
            or len(source_bytes) != receipt.file_size
            or _sha256(source_bytes) != receipt.file_sha256
        ):
            _fatal("sealed segment final content verification differs")
        source_stat = _owned_lineage_stat(source_path)
        archive_stat = _owned_lineage_stat(archive_path)
        if source_stat is None or archive_stat is None:
            _fatal("sealed segment copy disappeared during final verification")
        if (
            source_stat.st_dev,
            source_stat.st_ino,
            source_stat.st_mtime_ns,
        ) != (
            identity.source_device,
            identity.source_inode,
            identity.source_mtime_ns,
        ) or (
            archive_stat.st_dev,
            archive_stat.st_ino,
            archive_stat.st_mtime_ns,
        ) != (
            identity.archive_device,
            identity.archive_inode,
            identity.archive_mtime_ns,
        ):
            _fatal("sealed segment final retained identity differs")
        observations.extend(
            ((source_path, source_stat), (archive_path, archive_stat))
        )
    for candidate, observed in observations:
        current = _owned_lineage_stat(candidate)
        if current is None or any(
            getattr(observed, field) != getattr(current, field)
            for field in ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_nlink")
        ):
            _fatal("sealed segment changed after final content verification")


def _hash_owned_lineage(
    path: Path,
    *,
    expected_stat: os.stat_result,
) -> str:
    """Hash every durable byte while proving one stable owned file was read."""

    hasher = hashlib.sha256()
    bytes_read = 0
    with path.open("rb") as handle:
        before = os.fstat(handle.fileno())
        if any(
            getattr(before, field) != getattr(expected_stat, field)
            for field in ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_nlink")
        ):
            _fatal("feed lineage changed before full-file hashing")
        while True:
            chunk = handle.read(FILE_HASH_CHUNK_BYTES)
            if not chunk:
                break
            bytes_read += len(chunk)
            if bytes_read > MAX_LINEAGE_FILE_BYTES:
                _fatal("feed lineage exceeds the file byte limit")
            hasher.update(chunk)
        after = os.fstat(handle.fileno())
    if bytes_read != expected_stat.st_size or any(
        getattr(before, field) != getattr(after, field)
        for field in ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_nlink")
    ):
        _fatal("feed lineage changed during full-file hashing")
    current = _owned_lineage_stat(path)
    if current is None or any(
        getattr(after, field) != getattr(current, field)
        for field in ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_nlink")
    ):
        _fatal("feed lineage changed after full-file hashing")
    return hasher.hexdigest()


def _validate_lifecycle_events(
    value: object,
    claimed_hashes: object,
    *,
    state: lifecycle.FeedGameState,
    baseline: bool,
) -> tuple[bytes, ...]:
    if not isinstance(value, list) or not isinstance(claimed_hashes, list):
        _fatal("lineage lifecycle event collections are malformed")
    if len(value) != len(claimed_hashes) or not value:
        _fatal("lineage lifecycle event hashes do not align")
    event_bytes: list[bytes] = []
    for index, event in enumerate(value):
        if not isinstance(event, dict):
            _fatal("lineage lifecycle event is not an object")
        try:
            raw = policy.canonical_json_bytes(event)
        except (TypeError, ValueError) as exc:
            _fatal("lineage lifecycle event is invalid JSON", cause=exc)
        claimed = claimed_hashes[index]
        try:
            policy.validate_sha256(claimed, field="lifecycle_event_sha256")
        except (TypeError, ValueError) as exc:
            _fatal("lineage lifecycle event hash is invalid", cause=exc)
        if _sha256(raw) != claimed:
            _fatal("lineage lifecycle event hash differs")
        if event.get("game_pk") != state.game_pk:
            _fatal("lineage lifecycle event game differs")
        event_bytes.append(raw)
    if baseline:
        if len(value) != 1 or value[0].get("type") != "game_baseline":
            _fatal("baseline lineage does not contain exactly one baseline event")
    else:
        if value[-1].get("type") != "poll_validated":
            _fatal("transition lineage does not end in poll_validated")
    terminal = value[-1]
    if terminal.get("state_commitment_sha256") != state.state_commitment_sha256:
        _fatal("lineage lifecycle terminal event does not bind state commitment")
    if terminal.get("transition_sequence") != state.transition_sequence:
        _fatal("lineage lifecycle terminal event sequence differs")
    if (
        terminal.get("successful_poll_monotonic_ns")
        != state.last_successful_poll_monotonic_ns
    ):
        _fatal("lineage lifecycle terminal monotonic clock differs")
    return tuple(event_bytes)


def _require_deterministic_transition(
    state: lifecycle.FeedGameState,
    event_bytes: tuple[bytes, ...],
    *,
    prior_state: lifecycle.FeedGameState | None,
) -> None:
    completed = json.loads(state.last_completed_plays_bytes)
    if not isinstance(completed, dict):
        _fatal("lineage state completed plays are not an object")
    try:
        recomputed = lifecycle.transition_game(
            prior_state,
            game_pk=state.game_pk,
            completed_plays=cast("Mapping[str, object]", completed),
            official_current_total=state.last_official_current_total,
            abstract_state=state.last_abstract_state,
            detailed_state=state.last_detailed_state,
            observed_at=datetime.fromisoformat(state.last_observed_at),
            successful_poll_monotonic_ns=(
                state.last_successful_poll_monotonic_ns
            ),
            expected_prior_state_commitment_sha256=(
                None
                if prior_state is None
                else prior_state.state_commitment_sha256
            ),
        )
    except (TypeError, ValueError) as exc:
        _fatal("lineage transition cannot be recomputed", cause=exc)
    if recomputed.state != state or recomputed.event_bytes != event_bytes:
        _fatal("lineage transition differs from deterministic recomputation")


def _validate_lineage_event(
    raw: bytes,
    *,
    expected_sequence: int,
    expected_prior_sha256: str | None,
    prior_states: Mapping[int, lifecycle.FeedGameState],
    feed_anchor: policy.FeedLaunchAnchor,
    expected_base_lineage_path: str,
    expected_lineage_path: str,
    expected_segment_index: int,
    expected_sealed_segments_sha256: str,
) -> tuple[lifecycle.FeedGameState, str]:
    row = _parse_canonical_object(raw, field="feed lineage event")
    if set(row) != LINEAGE_EVENT_KEYS:
        _fatal("feed lineage event keys differ")
    provenance = policy.validated_feed_provenance(row, field="feed lineage event")
    if provenance != feed_anchor.provenance:
        _fatal("feed lineage event launch provenance differs")
    if row.get("base_lineage_path") != expected_base_lineage_path:
        _fatal("feed lineage event base path binding differs")
    if row.get("lineage_path") != expected_lineage_path:
        _fatal("feed lineage event path binding differs")
    if _exact_int(
        row.get("segment_index"),
        field="lineage.segment_index",
        minimum=1,
    ) != expected_segment_index:
        _fatal("feed lineage event segment index differs")
    if row.get("sealed_segments_sha256") != expected_sealed_segments_sha256:
        _fatal("feed lineage sealed segment commitment differs")
    if _exact_int(row.get("event_sequence"), field="event_sequence", minimum=1) != (
        expected_sequence
    ):
        _fatal("feed lineage event sequence is not contiguous")
    prior_hash = row.get("prior_lineage_event_sha256")
    if prior_hash != expected_prior_sha256:
        _fatal("feed lineage prior event hash differs")
    if prior_hash is not None:
        try:
            policy.validate_sha256(prior_hash, field="prior_lineage_event_sha256")
        except (TypeError, ValueError) as exc:
            _fatal("feed lineage prior hash is invalid", cause=exc)
    _parse_utc(row.get("recorded_at"), field="lineage.recorded_at")
    state_value = row.get("state")
    if not isinstance(state_value, dict):
        _fatal("feed lineage state is not an object")
    state_bytes = policy.canonical_json_bytes(state_value)
    claimed_state_sha = row.get("state_bytes_sha256")
    try:
        policy.validate_sha256(claimed_state_sha, field="state_bytes_sha256")
    except (TypeError, ValueError) as exc:
        _fatal("feed lineage state hash is invalid", cause=exc)
    if _sha256(state_bytes) != claimed_state_sha:
        _fatal("feed lineage state bytes hash differs")
    state = deserialize_game_state(state_bytes)
    outer_game_pk = _exact_int(
        row.get("game_pk"),
        field="lineage.game_pk",
        minimum=1,
    )
    outer_transition_sequence = _exact_int(
        row.get("transition_sequence"),
        field="lineage.transition_sequence",
        minimum=1,
    )
    if outer_game_pk != state.game_pk:
        _fatal("feed lineage game differs from state")
    if outer_transition_sequence != state.transition_sequence:
        _fatal("feed lineage transition sequence differs from state")
    if row.get("state_commitment_sha256") != state.state_commitment_sha256:
        _fatal("feed lineage commitment differs from state")

    prior_state = prior_states.get(state.game_pk)
    event_type = row.get("event_type")
    if prior_state is None:
        if prior_states:
            _fatal("feed lineage path is already bound to another game")
        baseline = True
        if event_type != "game_baseline" or state.transition_sequence != 1:
            _fatal("first game lineage event is not its sole baseline")
        if state.prior_state_commitment_sha256 is not None:
            _fatal("baseline state unexpectedly has a prior state")
    else:
        baseline = False
        if event_type != "game_transition":
            _fatal("existing game received a second baseline")
        if state.transition_sequence != prior_state.transition_sequence + 1:
            _fatal("game transition sequence is not contiguous")
        if (
            state.prior_state_commitment_sha256
            != prior_state.state_commitment_sha256
        ):
            _fatal("game transition prior commitment differs")
    resulting_states = dict(prior_states)
    resulting_states[state.game_pk] = state
    expected_game_heads_sha256 = _game_heads_sha256(resulting_states)
    if row.get("game_heads_sha256") != expected_game_heads_sha256:
        _fatal("feed lineage game-head map commitment differs")
    lifecycle_event_bytes = _validate_lifecycle_events(
        row.get("lifecycle_events"),
        row.get("lifecycle_event_sha256s"),
        state=state,
        baseline=baseline,
    )
    _require_deterministic_transition(
        state,
        lifecycle_event_bytes,
        prior_state=prior_state,
    )
    return state, _sha256(raw)


def _lineage_relative_path(path: Path, *, trusted_root: Path) -> str:
    try:
        relative = path.absolute().relative_to(trusted_root.absolute())
    except ValueError as exc:
        _fatal("feed lineage path escapes its trusted root", cause=exc)
    value = relative.as_posix()
    if not value or value == "." or ".." in relative.parts:
        _fatal("feed lineage relative path is invalid")
    return value


def _assert_trusted_lineage_paths(
    path: Path,
    *,
    trusted_root: Path,
) -> None:
    lock_path = path.parent / f".{path.name}.v34append.lock"
    try:
        feed_archive._assert_no_redirecting_components(trusted_root, path)
        feed_archive._assert_no_redirecting_components(trusted_root, lock_path)
    except (OSError, ValueError, feed_archive.ArchiveCollisionError) as exc:
        _fatal("feed lineage or append-lock ancestry is not trusted", cause=exc)


def _replay_feed_lineage_locked(
    path: Path,
    *,
    feed_anchor: policy.FeedLaunchAnchor,
    expected_event_count: int,
    expected_last_event_sha256: str | None,
    expected_sealed_segments: tuple[FeedSegmentReceipt, ...] = (),
    trusted_root: Path = policy.REPOSITORY_ROOT,
) -> FeedLineageSnapshot:
    """Replay the complete durable log or fail without accepting a prefix."""

    verified_anchor = policy.reverify_feed_launch_anchor(feed_anchor)
    expected_count = _exact_int(
        expected_event_count,
        field="expected_event_count",
    )
    if expected_count == 0:
        if expected_last_event_sha256 is not None:
            _fatal("empty expected lineage cannot have a head hash")
    else:
        try:
            policy.validate_sha256(
                expected_last_event_sha256,
                field="expected_last_event_sha256",
            )
        except (TypeError, ValueError) as exc:
            _fatal("expected lineage head hash is invalid", cause=exc)
    if not isinstance(path, Path) or not isinstance(trusted_root, Path):
        _fatal("feed lineage path and trusted root must be Paths")
    _assert_trusted_lineage_paths(path, trusted_root=trusted_root)
    base_lineage_path = _lineage_relative_path(path, trusted_root=trusted_root)
    sealed_segments = expected_sealed_segments
    _validate_segment_receipts(
        sealed_segments,
        base_path=path,
        trusted_root=trusted_root,
        feed_anchor=verified_anchor,
    )
    active_segment_index = len(sealed_segments) + 1
    active_path = _segment_path(path, active_segment_index)
    candidate = _owned_lineage_stat(active_path)
    if candidate is None:
        if expected_count != 0:
            _fatal("expected nonempty feed lineage is missing")
        if sealed_segments:
            _fatal("empty expected lineage cannot have sealed segments")
        _assert_empty_lineage_inventory_absent(path)
        return FeedLineageSnapshot(
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
    prior_sha: str | None = None
    states: dict[int, lifecycle.FeedGameState] = {}
    count = 0
    active_first_event_sequence: int | None = None
    active_first_prior_event_sha256: str | None = None
    active_first_event_sha256: str | None = None
    active_bytes_read = 0
    active_file_sha256: str | None = None
    active_after: os.stat_result | None = None
    replayed_identities: list[FeedSealedIdentity] = []
    for segment_index in range(1, active_segment_index + 1):
        segment_path = _segment_path(path, segment_index)
        segment_candidate = _owned_lineage_stat(segment_path)
        if segment_candidate is None or segment_candidate.st_size == 0:
            _fatal("feed lineage segment is missing or empty")
        if segment_candidate.st_size > MAX_ACTIVE_SEGMENT_BYTES:
            _fatal("feed lineage segment exceeds the byte limit")
        try:
            feed_archive._assert_no_redirecting_components(
                trusted_root,
                segment_path,
            )
        except (OSError, ValueError, feed_archive.ArchiveCollisionError) as exc:
            _fatal("feed lineage segment ancestry is not trusted", cause=exc)
        segment_lineage_path = _lineage_relative_path(
            segment_path,
            trusted_root=trusted_root,
        )
        prior_receipts = sealed_segments[: segment_index - 1]
        segment_sealed_sha256 = _sealed_segments_sha256(prior_receipts)
        segment_first_sequence = count + 1
        segment_first_prior = prior_sha
        segment_first_sha: str | None = None
        segment_event_count = 0
        segment_bytes_read = 0
        segment_hasher = hashlib.sha256()
        with segment_path.open("rb") as handle:
            while True:
                line = handle.readline(MAX_LINEAGE_EVENT_BYTES + 2)
                if not line:
                    break
                segment_bytes_read += len(line)
                segment_hasher.update(line)
                count += 1
                segment_event_count += 1
                if count > MAX_LINEAGE_EVENTS:
                    _fatal("feed lineage exceeds the event limit")
                if len(line) > MAX_LINEAGE_EVENT_BYTES + 1:
                    _fatal("feed lineage event exceeds the byte limit")
                if not line.endswith(b"\n"):
                    _fatal("feed lineage has a partial terminal event")
                raw = line[:-1]
                if not raw:
                    _fatal("feed lineage contains an empty event")
                if segment_event_count == 1:
                    segment_first_sha = _sha256(raw)
                state, prior_sha = _validate_lineage_event(
                    raw,
                    expected_sequence=count,
                    expected_prior_sha256=prior_sha,
                    prior_states=states,
                    feed_anchor=verified_anchor,
                    expected_base_lineage_path=base_lineage_path,
                    expected_lineage_path=segment_lineage_path,
                    expected_segment_index=segment_index,
                    expected_sealed_segments_sha256=segment_sealed_sha256,
                )
                states[state.game_pk] = state
        segment_after = _owned_lineage_stat(segment_path)
        if segment_after is None or any(
            getattr(segment_candidate, field) != getattr(segment_after, field)
            for field in ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_nlink")
        ):
            _fatal("feed lineage segment changed during replay")
        if segment_bytes_read != segment_candidate.st_size:
            _fatal("feed lineage segment replay did not consume the complete file")
        if segment_event_count == 0 or segment_first_sha is None or prior_sha is None:
            _fatal("feed lineage segment contained no complete event")
        segment_file_sha256 = segment_hasher.hexdigest()
        if segment_index <= len(sealed_segments):
            receipt = sealed_segments[segment_index - 1]
            observed_receipt = FeedSegmentReceipt(
                base_lineage_path=base_lineage_path,
                lineage_path=segment_lineage_path,
                archive_path=receipt.archive_path,
                segment_index=segment_index,
                first_event_sequence=segment_first_sequence,
                last_event_sequence=count,
                event_count=segment_event_count,
                first_prior_event_sha256=segment_first_prior,
                first_event_sha256=segment_first_sha,
                last_event_sha256=prior_sha,
                file_size=segment_bytes_read,
                file_sha256=segment_file_sha256,
                launch_manifest_sha256=verified_anchor.manifest_sha256,
            )
            if observed_receipt != receipt:
                _fatal("sealed segment replay differs from its exact receipt")
            archive_path = trusted_root / Path(receipt.archive_path)
            try:
                archive_bytes = feed_archive._stable_owned_file_bytes(archive_path)
                source_bytes = feed_archive._stable_owned_file_bytes(segment_path)
            except (OSError, ValueError, feed_archive.ArchiveCollisionError) as exc:
                _fatal("sealed segment replica cannot be read", cause=exc)
            if archive_bytes != source_bytes:
                _fatal("sealed segment replica differs from its source")
            source_after = _owned_lineage_stat(segment_path)
            archive_after = _owned_lineage_stat(archive_path)
            if source_after is None or archive_after is None:
                _fatal("sealed segment identity disappeared during replay")
            if any(
                getattr(segment_after, field) != getattr(source_after, field)
                for field in ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_nlink")
            ):
                _fatal("sealed segment source changed during replica verification")
            replayed_identities.append(
                FeedSealedIdentity(
                    segment_index=segment_index,
                    source_device=source_after.st_dev,
                    source_inode=source_after.st_ino,
                    source_mtime_ns=source_after.st_mtime_ns,
                    archive_device=archive_after.st_dev,
                    archive_inode=archive_after.st_ino,
                    archive_mtime_ns=archive_after.st_mtime_ns,
                )
            )
        else:
            active_first_event_sequence = segment_first_sequence
            active_first_prior_event_sha256 = segment_first_prior
            active_first_event_sha256 = segment_first_sha
            active_bytes_read = segment_bytes_read
            active_file_sha256 = segment_file_sha256
            active_after = segment_after
    if count != expected_count or prior_sha != expected_last_event_sha256:
        _fatal("feed lineage differs from the independently retained head")
    if active_after is None or active_file_sha256 is None:
        _fatal("feed lineage active segment replay is incomplete")
    active_lineage_path = _lineage_relative_path(
        active_path,
        trusted_root=trusted_root,
    )
    snapshot = FeedLineageSnapshot(
        event_count=count,
        last_event_sha256=prior_sha,
        game_states=tuple(sorted(states.items())),
        file_size=active_bytes_read,
        file_device=active_after.st_dev,
        file_inode=active_after.st_ino,
        file_mtime_ns=active_after.st_mtime_ns,
        lineage_path=active_lineage_path,
        game_heads_sha256=_game_heads_sha256(states),
        file_sha256=active_file_sha256,
        base_lineage_path=base_lineage_path,
        active_segment_index=active_segment_index,
        active_first_event_sequence=active_first_event_sequence,
        active_first_prior_event_sha256=active_first_prior_event_sha256,
        active_first_event_sha256=active_first_event_sha256,
        sealed_segments=sealed_segments,
        sealed_segments_sha256=_sealed_segments_sha256(sealed_segments),
        sealed_identities=tuple(replayed_identities),
    )
    _verify_segment_inventory(
        snapshot,
        base_path=path,
        active_path=active_path,
        trusted_root=trusted_root,
        feed_anchor=verified_anchor,
    )
    _verify_all_sealed_copies(
        sealed_segments,
        snapshot.sealed_identities,
        trusted_root=trusted_root,
    )
    _verify_retained_snapshot(
        active_path,
        snapshot,
        feed_anchor=verified_anchor,
        base_path=path,
        trusted_root=trusted_root,
        expected_lineage_path=active_lineage_path,
        expected_segment_index=active_segment_index,
    )
    return snapshot


def _read_bounded_terminal_event(path: Path, *, file_size: int) -> bytes:
    read_size = min(file_size, MAX_LINEAGE_EVENT_BYTES + 1)
    with path.open("rb") as handle:
        handle.seek(file_size - read_size)
        chunk = handle.read(read_size)
    if len(chunk) != read_size or not chunk.endswith(b"\n"):
        _fatal("feed lineage terminal event is missing or partial")
    without_terminal_newline = chunk[:-1]
    prior_newline = without_terminal_newline.rfind(b"\n")
    raw = without_terminal_newline[prior_newline + 1 :]
    if not raw or len(raw) > MAX_LINEAGE_EVENT_BYTES:
        _fatal("feed lineage terminal event exceeds the byte limit")
    return raw


def _read_bounded_first_event(path: Path) -> bytes:
    with path.open("rb") as handle:
        line = handle.readline(MAX_LINEAGE_EVENT_BYTES + 2)
    if len(line) > MAX_LINEAGE_EVENT_BYTES + 1:
        _fatal("feed lineage first event exceeds the byte limit")
    if not line.endswith(b"\n") or not line[:-1]:
        _fatal("feed lineage first event is missing or partial")
    return line[:-1]


def _verify_retained_snapshot(
    path: Path,
    snapshot: FeedLineageSnapshot,
    *,
    feed_anchor: policy.FeedLaunchAnchor,
    base_path: Path,
    trusted_root: Path,
    expected_lineage_path: str,
    expected_segment_index: int,
) -> tuple[os.stat_result | None, bool]:
    if not isinstance(snapshot, FeedLineageSnapshot):
        _fatal("expected feed lineage snapshot has the wrong type")
    count = _exact_int(snapshot.event_count, field="snapshot.event_count")
    if type(snapshot.game_states) is not tuple:
        _fatal("snapshot game states are not an immutable tuple")
    game_pks: list[int] = []
    for item in snapshot.game_states:
        if type(item) is not tuple or len(item) != 2:
            _fatal("snapshot game-state entry is malformed")
        game_pk = _exact_int(item[0], field="snapshot.game_pk", minimum=1)
        if not isinstance(item[1], lifecycle.FeedGameState) or item[1].game_pk != game_pk:
            _fatal("snapshot game-state binding differs")
        try:
            lifecycle._validate_prior_state(item[1])
        except (TypeError, ValueError) as exc:
            _fatal("snapshot game state is invalid", cause=exc)
        game_pks.append(game_pk)
    if game_pks != sorted(set(game_pks)):
        _fatal("snapshot game-state entries are duplicated or unsorted")
    if len(game_pks) > 1:
        _fatal("retained lineage snapshot contains more than one game")

    current = _owned_lineage_stat(path)
    if count == 0:
        if (
            snapshot.last_event_sha256 is not None
            or snapshot.file_size != 0
            or snapshot.file_device is not None
            or snapshot.file_inode is not None
            or snapshot.file_mtime_ns is not None
            or snapshot.lineage_path is not None
            or snapshot.game_heads_sha256 is not None
            or snapshot.file_sha256 is not None
            or snapshot.game_states
            or snapshot.base_lineage_path is not None
            or snapshot.active_segment_index != 0
            or snapshot.active_first_event_sequence is not None
            or snapshot.active_first_prior_event_sha256 is not None
            or snapshot.active_first_event_sha256 is not None
            or snapshot.sealed_segments
            or snapshot.sealed_segments_sha256 is not None
            or snapshot.sealed_identities
        ):
            _fatal("empty retained snapshot fields differ")
        if current is not None:
            _fatal("empty retained snapshot requires an absent lineage path")
        _assert_empty_lineage_inventory_absent(base_path)
        return None, False


    expected_base_lineage_path = _lineage_relative_path(
        base_path,
        trusted_root=trusted_root,
    )
    if snapshot.base_lineage_path != expected_base_lineage_path:
        _fatal("retained snapshot base lineage path differs")
    if snapshot.active_segment_index != expected_segment_index:
        _fatal("retained snapshot active segment index differs")
    _validate_segment_receipts(
        snapshot.sealed_segments,
        base_path=base_path,
        trusted_root=trusted_root,
        feed_anchor=feed_anchor,
    )
    expected_sealed_segments_sha256 = _sealed_segments_sha256(
        snapshot.sealed_segments
    )
    if snapshot.sealed_segments_sha256 != expected_sealed_segments_sha256:
        _fatal("retained snapshot sealed segment commitment differs")
    if expected_segment_index != len(snapshot.sealed_segments) + 1:
        _fatal("retained snapshot active segment does not follow sealed inventory")
    pending_rotation = _verify_segment_inventory(
        snapshot,
        base_path=base_path,
        active_path=path,
        trusted_root=trusted_root,
        feed_anchor=feed_anchor,
    )
    first_sequence = _exact_int(
        snapshot.active_first_event_sequence,
        field="snapshot.active_first_event_sequence",
        minimum=1,
    )
    if first_sequence > count:
        _fatal("retained snapshot active first sequence exceeds its head")
    expected_first_sequence = (
        1
        if not snapshot.sealed_segments
        else snapshot.sealed_segments[-1].last_event_sequence + 1
    )
    expected_first_prior = (
        None
        if not snapshot.sealed_segments
        else snapshot.sealed_segments[-1].last_event_sha256
    )
    if first_sequence != expected_first_sequence:
        _fatal("retained snapshot active first sequence differs")
    if snapshot.active_first_prior_event_sha256 != expected_first_prior:
        _fatal("retained snapshot active first prior head differs")
    try:
        policy.validate_sha256(
            snapshot.active_first_event_sha256,
            field="snapshot.active_first_event_sha256",
        )
    except (TypeError, ValueError) as exc:
        _fatal("retained snapshot active first event hash is invalid", cause=exc)

    try:
        policy.validate_sha256(
            snapshot.last_event_sha256,
            field="snapshot.last_event_sha256",
        )
    except (TypeError, ValueError) as exc:
        _fatal("retained snapshot head hash is invalid", cause=exc)
    if snapshot.lineage_path != expected_lineage_path:
        _fatal("retained snapshot lineage path differs")
    try:
        policy.validate_sha256(
            snapshot.game_heads_sha256,
            field="snapshot.game_heads_sha256",
        )
    except (TypeError, ValueError) as exc:
        _fatal("retained snapshot game-head commitment is invalid", cause=exc)
    states = dict(snapshot.game_states)
    if _game_heads_sha256(states) != snapshot.game_heads_sha256:
        _fatal("retained snapshot game states differ from their commitment")
    try:
        policy.validate_sha256(
            snapshot.file_sha256,
            field="snapshot.file_sha256",
        )
    except (TypeError, ValueError) as exc:
        _fatal("retained snapshot full-file hash is invalid", cause=exc)
    size = _exact_int(snapshot.file_size, field="snapshot.file_size", minimum=1)
    device = _exact_int(snapshot.file_device, field="snapshot.file_device")
    inode = _exact_int(snapshot.file_inode, field="snapshot.file_inode")
    mtime_ns = _exact_int(
        snapshot.file_mtime_ns,
        field="snapshot.file_mtime_ns",
    )
    if current is None:
        _fatal("retained nonempty feed lineage is missing")
    if (
        current.st_dev != device
        or current.st_ino != inode
        or current.st_size != size
        or current.st_mtime_ns != mtime_ns
    ):
        _fatal("feed lineage differs from the retained file identity")
    first_event = _read_bounded_first_event(path)
    if _sha256(first_event) != snapshot.active_first_event_sha256:
        _fatal("retained snapshot active first event hash differs")
    first_row = _parse_canonical_object(
        first_event,
        field="retained active first lineage event",
    )
    if set(first_row) != LINEAGE_EVENT_KEYS:
        _fatal("retained active first lineage event keys differ")
    try:
        first_provenance = policy.validated_feed_provenance(
            first_row,
            field="retained active first lineage event",
        )
    except (TypeError, ValueError) as exc:
        _fatal("retained active first lineage provenance is invalid", cause=exc)
    if first_provenance != feed_anchor.provenance:
        _fatal("retained active first lineage launch provenance differs")
    if _exact_int(
        first_row.get("event_sequence"),
        field="retained active first event_sequence",
        minimum=1,
    ) != first_sequence:
        _fatal("retained active first global sequence differs")
    if (
        first_row.get("prior_lineage_event_sha256")
        != snapshot.active_first_prior_event_sha256
    ):
        _fatal("retained active first prior global head differs")
    if first_row.get("base_lineage_path") != expected_base_lineage_path:
        _fatal("retained active first base path differs")
    if first_row.get("lineage_path") != expected_lineage_path:
        _fatal("retained active first lineage path differs")
    if _exact_int(
        first_row.get("segment_index"),
        field="retained active first segment_index",
        minimum=1,
    ) != expected_segment_index:
        _fatal("retained active first segment index differs")
    if (
        first_row.get("sealed_segments_sha256")
        != expected_sealed_segments_sha256
    ):
        _fatal("retained active first sealed segment commitment differs")
    terminal = _read_bounded_terminal_event(path, file_size=size)
    if _sha256(terminal) != snapshot.last_event_sha256:
        _fatal("feed lineage terminal hash differs from the retained head")
    terminal_row = _parse_canonical_object(
        terminal,
        field="retained terminal lineage event",
    )
    if set(terminal_row) != LINEAGE_EVENT_KEYS:
        _fatal("retained terminal lineage event keys differ")
    try:
        terminal_provenance = policy.validated_feed_provenance(
            terminal_row,
            field="retained terminal lineage event",
        )
    except (TypeError, ValueError) as exc:
        _fatal("retained terminal lineage provenance is invalid", cause=exc)
    if terminal_provenance != feed_anchor.provenance:
        _fatal("retained terminal lineage launch provenance differs")
    if _exact_int(
        terminal_row.get("event_sequence"),
        field="retained terminal event_sequence",
        minimum=1,
    ) != count:
        _fatal("retained snapshot count differs from the terminal event")
    if terminal_row.get("lineage_path") != expected_lineage_path:
        _fatal("retained snapshot path differs from the terminal event")
    if terminal_row.get("base_lineage_path") != expected_base_lineage_path:
        _fatal("retained snapshot base path differs from the terminal event")
    if _exact_int(
        terminal_row.get("segment_index"),
        field="retained terminal segment_index",
        minimum=1,
    ) != expected_segment_index:
        _fatal("retained snapshot segment differs from the terminal event")
    if (
        terminal_row.get("sealed_segments_sha256")
        != expected_sealed_segments_sha256
    ):
        _fatal("retained snapshot sealed segments differ from the terminal event")
    if terminal_row.get("game_heads_sha256") != snapshot.game_heads_sha256:
        _fatal("retained snapshot game heads differ from the terminal event")
    terminal_state_value = terminal_row.get("state")
    if not isinstance(terminal_state_value, dict):
        _fatal("retained terminal lineage state is not an object")
    terminal_state_bytes = policy.canonical_json_bytes(terminal_state_value)
    try:
        policy.validate_sha256(
            terminal_row.get("state_bytes_sha256"),
            field="retained terminal state_bytes_sha256",
        )
    except (TypeError, ValueError) as exc:
        _fatal("retained terminal state bytes hash is invalid", cause=exc)
    if _sha256(terminal_state_bytes) != terminal_row.get("state_bytes_sha256"):
        _fatal("retained terminal state bytes hash differs")
    terminal_state = deserialize_game_state(terminal_state_bytes)
    if len(snapshot.game_states) != 1 or snapshot.game_states[0][1] != terminal_state:
        _fatal("retained snapshot state differs from the terminal event")
    if _exact_int(
        terminal_row.get("game_pk"),
        field="retained terminal game_pk",
        minimum=1,
    ) != terminal_state.game_pk:
        _fatal("retained terminal game differs from its state")
    if _exact_int(
        terminal_row.get("transition_sequence"),
        field="retained terminal transition_sequence",
        minimum=1,
    ) != terminal_state.transition_sequence:
        _fatal("retained terminal transition sequence differs from its state")
    if (
        terminal_row.get("state_commitment_sha256")
        != terminal_state.state_commitment_sha256
    ):
        _fatal("retained terminal commitment differs from its state")
    closing = _owned_lineage_stat(path)
    if closing is None or any(
        getattr(current, field) != getattr(closing, field)
        for field in ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_nlink")
    ):
        _fatal("feed lineage changed before the final retained hash")
    if _hash_owned_lineage(path, expected_stat=closing) != snapshot.file_sha256:
        _fatal("feed lineage final retained hash differs")
    closing_pending_rotation = _verify_segment_inventory(
        snapshot,
        base_path=base_path,
        active_path=path,
        trusted_root=trusted_root,
        feed_anchor=feed_anchor,
    )
    if closing_pending_rotation != pending_rotation:
        _fatal("feed lineage pending rotation state changed during verification")
    final_active = _owned_lineage_stat(path)
    if final_active is None or any(
        getattr(closing, field) != getattr(final_active, field)
        for field in ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_nlink")
    ):
        _fatal("feed lineage active identity changed after custody verification")
    return final_active, pending_rotation


def _verify_append_lock_ownership(
    lock_path: Path,
    descriptor: int,
    *,
    lock_stat: os.stat_result,
    lock_bytes: bytes,
) -> None:
    try:
        path_stat = lock_path.stat(follow_symlinks=False)
    except FileNotFoundError as exc:
        _fatal("feed lineage append lock disappeared", cause=exc)
    descriptor_stat = os.fstat(descriptor)
    if (
        not stat.S_ISREG(path_stat.st_mode)
        or path_stat.st_nlink != 1
        or path_stat.st_dev != lock_stat.st_dev
        or path_stat.st_ino != lock_stat.st_ino
        or descriptor_stat.st_dev != lock_stat.st_dev
        or descriptor_stat.st_ino != lock_stat.st_ino
        or descriptor_stat.st_size != len(lock_bytes)
    ):
        _fatal("feed lineage append lock ownership changed")
    os.lseek(descriptor, 0, os.SEEK_SET)
    if os.read(descriptor, len(lock_bytes) + 1) != lock_bytes:
        _fatal("feed lineage append lock bytes changed")


def _append_exact_payload(
    path: Path,
    payload: bytes,
    *,
    before: os.stat_result | None,
    snapshot: FeedLineageSnapshot,
    verify_lock_ownership: Callable[[], None],
) -> tuple[os.stat_result, str]:
    """Append through the descriptor that rehashes the exact retained prefix."""

    hasher = hashlib.sha256()
    if before is None:
        verify_lock_ownership()
        with path.open("xb") as handle:
            if handle.write(payload) != len(payload):
                _fatal("feed lineage initial append write was incomplete")
            handle.flush()
            os.fsync(handle.fileno())
            verify_lock_ownership()
            after_descriptor = os.fstat(handle.fileno())
            if (
                not stat.S_ISREG(after_descriptor.st_mode)
                or after_descriptor.st_nlink != 1
                or after_descriptor.st_size != len(payload)
            ):
                _fatal("feed lineage initial append identity or size changed")
        hasher.update(payload)
    else:
        bytes_read = 0
        with path.open("r+b") as handle:
            opened = os.fstat(handle.fileno())
            if any(
                getattr(opened, field) != getattr(before, field)
                for field in ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_nlink")
            ):
                _fatal("feed lineage changed before descriptor-bound append")
            while True:
                chunk = handle.read(FILE_HASH_CHUNK_BYTES)
                if not chunk:
                    break
                bytes_read += len(chunk)
                if bytes_read > MAX_LINEAGE_FILE_BYTES:
                    _fatal("feed lineage exceeds the file byte limit")
                hasher.update(chunk)
            rehashed = os.fstat(handle.fileno())
            if bytes_read != before.st_size or any(
                getattr(opened, field) != getattr(rehashed, field)
                for field in ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_nlink")
            ):
                _fatal("feed lineage changed during descriptor-bound rehash")
            if hasher.hexdigest() != snapshot.file_sha256:
                _fatal("descriptor-bound prefix differs from the retained snapshot")
            current = _owned_lineage_stat(path)
            if current is None or any(
                getattr(rehashed, field) != getattr(current, field)
                for field in ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_nlink")
            ):
                _fatal("feed lineage changed before descriptor-bound mutation")
            verify_lock_ownership()
            if handle.seek(0, os.SEEK_END) != before.st_size:
                _fatal("feed lineage append offset differs from the retained size")
            if handle.write(payload) != len(payload):
                _fatal("feed lineage append write was incomplete")
            handle.flush()
            os.fsync(handle.fileno())
            verify_lock_ownership()
            after_descriptor = os.fstat(handle.fileno())
            if (
                after_descriptor.st_dev != before.st_dev
                or after_descriptor.st_ino != before.st_ino
                or after_descriptor.st_nlink != 1
                or after_descriptor.st_size != before.st_size + len(payload)
            ):
                _fatal("feed lineage descriptor identity or append size changed")
        hasher.update(payload)
    after = _owned_lineage_stat(path)
    if after is None or any(
        getattr(after_descriptor, field) != getattr(after, field)
        for field in ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_nlink")
    ):
        _fatal("feed lineage path differs from the appended descriptor")
    feed_archive._fsync_directory(path.parent)
    return after, hasher.hexdigest()


def _acquire_os_append_lock(descriptor: int) -> None:
    os.lseek(descriptor, 0, os.SEEK_SET)
    try:
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            lock_api = cast("Any", fcntl)
            lock_api.flock(descriptor, lock_api.LOCK_EX | lock_api.LOCK_NB)
    except OSError as exc:
        _fatal("feed lineage append lock is already held", cause=exc)


def _release_os_append_lock(descriptor: int) -> None:
    os.lseek(descriptor, 0, os.SEEK_SET)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        lock_api = cast("Any", fcntl)
        lock_api.flock(descriptor, lock_api.LOCK_UN)


@contextmanager
def _exclusive_append_lock(
    path: Path,
    *,
    trusted_root: Path,
) -> Iterator[Callable[[], None]]:
    lock_path = path.parent / f".{path.name}.v34append.lock"
    _assert_trusted_lineage_paths(path, trusted_root=trusted_root)
    flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_BINARY", 0)
    try:
        descriptor = os.open(lock_path, flags, 0o600)
    except OSError as exc:
        _fatal("feed lineage append lock cannot be opened", cause=exc)
    try:
        _acquire_os_append_lock(descriptor)
    except BaseException:
        os.close(descriptor)
        raise
    lock_bytes = policy.canonical_json_bytes(
        {
            "lineage_path": str(path.absolute()),
            "ownership_nonce": uuid4().hex,
            "process_id": os.getpid(),
        }
    )
    ownership_valid = False
    try:
        opened_stat = os.fstat(descriptor)
        path_stat = lock_path.stat(follow_symlinks=False)
        if (
            not stat.S_ISREG(opened_stat.st_mode)
            or opened_stat.st_nlink != 1
            or path_stat.st_dev != opened_stat.st_dev
            or path_stat.st_ino != opened_stat.st_ino
        ):
            _fatal("feed lineage append lock is not a singly owned regular file")
        os.ftruncate(descriptor, 0)
        os.lseek(descriptor, 0, os.SEEK_SET)
        if os.write(descriptor, lock_bytes) != len(lock_bytes):
            _fatal("feed lineage append lock write was incomplete")
        os.fsync(descriptor)
        lock_stat = os.fstat(descriptor)
        if not stat.S_ISREG(lock_stat.st_mode) or lock_stat.st_nlink != 1:
            _fatal("feed lineage append lock is not a singly owned regular file")
        feed_archive._fsync_directory(path.parent)
        def verify_ownership() -> None:
            _verify_append_lock_ownership(
                lock_path,
                descriptor,
                lock_stat=lock_stat,
                lock_bytes=lock_bytes,
            )

        verify_ownership()
        try:
            yield verify_ownership
        finally:
            verify_ownership()
            ownership_valid = True
    finally:
        try:
            if ownership_valid:
                os.ftruncate(descriptor, 0)
                os.fsync(descriptor)
        finally:
            try:
                _release_os_append_lock(descriptor)
            finally:
                os.close(descriptor)
        feed_archive._fsync_directory(path.parent)


def replay_feed_lineage(
    path: Path,
    *,
    feed_anchor: policy.FeedLaunchAnchor,
    expected_event_count: int,
    expected_last_event_sha256: str | None,
    expected_sealed_segments: tuple[FeedSegmentReceipt, ...] = (),
    trusted_root: Path = policy.REPOSITORY_ROOT,
) -> FeedLineageSnapshot:
    """Replay under the same OS-released lock used by append and recovery."""

    if (
        not isinstance(path, Path)
        or not isinstance(trusted_root, Path)
        or not path.parent.is_dir()
    ):
        _fatal("feed lineage replay parent directory must already exist")
    with _exclusive_append_lock(path, trusted_root=trusted_root):
        return _replay_feed_lineage_locked(
            path,
            feed_anchor=feed_anchor,
            expected_event_count=expected_event_count,
            expected_last_event_sha256=expected_last_event_sha256,
            expected_sealed_segments=expected_sealed_segments,
            trusted_root=trusted_root,
        )


def append_feed_transition(
    path: Path,
    transition: lifecycle.FeedTransition,
    *,
    feed_anchor: policy.FeedLaunchAnchor,
    recorded_at: Callable[[], str],
    expected_snapshot: FeedLineageSnapshot,
    trusted_root: Path = policy.REPOSITORY_ROOT,
) -> FeedLineageSnapshot:
    """Append one transition after verifying the complete per-game prefix."""

    if (
        not isinstance(path, Path)
        or not isinstance(trusted_root, Path)
        or not path.parent.is_dir()
    ):
        _fatal("feed lineage parent directory must already exist")
    with _exclusive_append_lock(path, trusted_root=trusted_root) as verify_lock:
        return _append_feed_transition_locked(
            path,
            transition,
            feed_anchor=feed_anchor,
            recorded_at=recorded_at,
            expected_snapshot=expected_snapshot,
            trusted_root=trusted_root,
            verify_lock_ownership=verify_lock,
        )


def _append_feed_transition_locked(
    path: Path,
    transition: lifecycle.FeedTransition,
    *,
    feed_anchor: policy.FeedLaunchAnchor,
    recorded_at: Callable[[], str],
    expected_snapshot: FeedLineageSnapshot,
    trusted_root: Path,
    verify_lock_ownership: Callable[[], None],
) -> FeedLineageSnapshot:
    """Append while the exclusive adjacent lock is continuously owned."""

    verified_anchor = policy.reverify_feed_launch_anchor(feed_anchor)
    if (
        not isinstance(path, Path)
        or not isinstance(trusted_root, Path)
        or not path.parent.is_dir()
    ):
        _fatal("feed lineage parent directory must already exist")
    base_path = path
    _assert_trusted_lineage_paths(base_path, trusted_root=trusted_root)
    if not isinstance(transition, lifecycle.FeedTransition):
        _fatal("feed lineage append requires a FeedTransition")
    state_bytes = serialize_game_state(transition.state)
    if len(state_bytes) > MAX_LINEAGE_EVENT_BYTES:
        _fatal("feed lineage state exceeds the byte limit")
    recorded = recorded_at()
    _parse_utc(recorded, field="lineage.recorded_at")
    snapshot = expected_snapshot
    active_segment_index = (
        snapshot.active_segment_index
        if snapshot.active_segment_index > 0
        else 1
    )
    active_path = _segment_path(base_path, active_segment_index)
    _assert_trusted_lineage_paths(base_path, trusted_root=trusted_root)
    try:
        feed_archive._assert_no_redirecting_components(trusted_root, active_path)
    except (OSError, ValueError, feed_archive.ArchiveCollisionError) as exc:
        _fatal("active feed lineage segment ancestry is not trusted", cause=exc)
    base_lineage_path = _lineage_relative_path(
        base_path,
        trusted_root=trusted_root,
    )
    lineage_path = _lineage_relative_path(
        active_path,
        trusted_root=trusted_root,
    )
    before, pending_rotation = _verify_retained_snapshot(
        active_path,
        snapshot,
        feed_anchor=verified_anchor,
        base_path=base_path,
        trusted_root=trusted_root,
        expected_lineage_path=lineage_path,
        expected_segment_index=active_segment_index,
    )
    if snapshot.event_count >= MAX_LINEAGE_EVENTS:
        _fatal("feed lineage is already at the event limit")
    prior_state = snapshot.state_for(transition.state.game_pk)
    if prior_state is None:
        if snapshot.game_states:
            _fatal("feed lineage path is already bound to another game")
        if transition.state.transition_sequence != 1:
            _fatal("new game transition is not a baseline")
        event_type = "game_baseline"
    else:
        if (
            transition.state.transition_sequence
            != prior_state.transition_sequence + 1
            or transition.state.prior_state_commitment_sha256
            != prior_state.state_commitment_sha256
        ):
            _fatal("transition does not extend the durable game head")
        event_type = "game_transition"
    _require_deterministic_transition(
        transition.state,
        transition.event_bytes,
        prior_state=prior_state,
    )
    lifecycle_events = [json.loads(raw) for raw in transition.event_bytes]
    next_states = dict(snapshot.game_states)
    next_states[transition.state.game_pk] = transition.state
    game_heads_sha256 = _game_heads_sha256(next_states)
    sealed_segments = snapshot.sealed_segments
    sealed_segments_sha256 = _sealed_segments_sha256(sealed_segments)
    sealed_identities = snapshot.sealed_identities

    def build_event_bytes() -> bytes:
        return policy.canonical_json_bytes(
            {
                **verified_anchor.provenance,
                "base_lineage_path": base_lineage_path,
                "event_sequence": snapshot.event_count + 1,
                "event_type": event_type,
                "game_pk": transition.state.game_pk,
                "game_heads_sha256": game_heads_sha256,
                "lifecycle_event_sha256s": [
                    _sha256(raw) for raw in transition.event_bytes
                ],
                "lifecycle_events": lifecycle_events,
                "lineage_path": lineage_path,
                "prior_lineage_event_sha256": snapshot.last_event_sha256,
                "recorded_at": recorded,
                "sealed_segments_sha256": sealed_segments_sha256,
                "segment_index": active_segment_index,
                "state": json.loads(state_bytes),
                "state_bytes_sha256": _sha256(state_bytes),
                "state_commitment_sha256": (
                    transition.state.state_commitment_sha256
                ),
                "transition_sequence": transition.state.transition_sequence,
            }
        )

    event_bytes = build_event_bytes()
    if len(event_bytes) > MAX_LINEAGE_EVENT_BYTES:
        _fatal("feed lineage event exceeds the byte limit")
    if len(event_bytes) + 1 > MAX_ACTIVE_SEGMENT_BYTES:
        _fatal("feed lineage event exceeds the active segment byte limit")
    rotated = False
    newly_sealed_receipts: tuple[FeedSegmentReceipt, ...] = ()
    newly_sealed_identities: tuple[FeedSealedIdentity, ...] = ()
    should_rotate = pending_rotation or (
        snapshot.event_count > 0
        and snapshot.file_size + len(event_bytes) + 1 > MAX_ACTIVE_SEGMENT_BYTES
    )
    if should_rotate:
        unpublished_receipt = _receipt_from_active_snapshot(
            snapshot,
            base_path=base_path,
            trusted_root=trusted_root,
            feed_anchor=verified_anchor,
        )
        sealed_segments = (*snapshot.sealed_segments, unpublished_receipt)
        _validate_segment_receipts(
            sealed_segments,
            base_path=base_path,
            trusted_root=trusted_root,
            feed_anchor=verified_anchor,
        )
        sealed_segments_sha256 = _sealed_segments_sha256(sealed_segments)
        active_segment_index += 1
        active_path = _segment_path(base_path, active_segment_index)
        if os.path.lexists(active_path):
            _fatal("next feed lineage segment already exists before rotation")
        try:
            feed_archive._assert_no_redirecting_components(
                trusted_root,
                active_path,
            )
        except (OSError, ValueError, feed_archive.ArchiveCollisionError) as exc:
            _fatal("next feed lineage segment ancestry is not trusted", cause=exc)
        lineage_path = _lineage_relative_path(
            active_path,
            trusted_root=trusted_root,
        )
        preflight_event_bytes = build_event_bytes()
        if len(preflight_event_bytes) > MAX_LINEAGE_EVENT_BYTES:
            _fatal("rotated feed lineage event exceeds the byte limit")
        if len(preflight_event_bytes) + 1 > MAX_ACTIVE_SEGMENT_BYTES:
            _fatal("rotated event exceeds the active segment byte limit")
        sealed_receipt, sealed_identity = _seal_active_segment(
            _segment_path(base_path, unpublished_receipt.segment_index),
            snapshot,
            base_path=base_path,
            trusted_root=trusted_root,
            feed_anchor=verified_anchor,
        )
        if sealed_receipt != unpublished_receipt:
            _fatal("published receipt differs from its exact rotation preflight")
        sealed_segments = (*snapshot.sealed_segments, sealed_receipt)
        sealed_identities = (*snapshot.sealed_identities, sealed_identity)
        newly_sealed_receipts = (sealed_receipt,)
        newly_sealed_identities = (sealed_identity,)
        _validate_segment_receipts(
            sealed_segments,
            base_path=base_path,
            trusted_root=trusted_root,
            feed_anchor=verified_anchor,
        )
        sealed_segments_sha256 = _sealed_segments_sha256(sealed_segments)
        event_bytes = build_event_bytes()
        if len(event_bytes) > len(preflight_event_bytes):
            _fatal("published receipt exceeded the rotated event size preflight")
        before = None
        rotated = True
    prior_states = dict(snapshot.game_states)
    validated_state, validated_event_sha = _validate_lineage_event(
        event_bytes,
        expected_sequence=snapshot.event_count + 1,
        expected_prior_sha256=snapshot.last_event_sha256,
        prior_states=prior_states,
        feed_anchor=verified_anchor,
        expected_base_lineage_path=base_lineage_path,
        expected_lineage_path=lineage_path,
        expected_segment_index=active_segment_index,
        expected_sealed_segments_sha256=sealed_segments_sha256,
    )
    if validated_state != transition.state:
        _fatal("locally validated lineage event state differs")
    payload = event_bytes + b"\n"
    _assert_trusted_lineage_paths(base_path, trusted_root=trusted_root)
    after, after_file_sha256 = _append_exact_payload(
        active_path,
        payload,
        before=before,
        snapshot=snapshot,
        verify_lock_ownership=verify_lock_ownership,
    )
    _assert_trusted_lineage_paths(base_path, trusted_root=trusted_root)
    terminal = _read_bounded_terminal_event(active_path, file_size=after.st_size)
    if terminal != event_bytes:
        _fatal("feed lineage terminal event differs after append")
    candidate_snapshot = FeedLineageSnapshot(
        event_count=snapshot.event_count + 1,
        last_event_sha256=validated_event_sha,
        game_states=tuple(sorted(next_states.items())),
        file_size=after.st_size,
        file_device=after.st_dev,
        file_inode=after.st_ino,
        file_mtime_ns=after.st_mtime_ns,
        lineage_path=lineage_path,
        game_heads_sha256=game_heads_sha256,
        file_sha256=after_file_sha256,
        base_lineage_path=base_lineage_path,
        active_segment_index=active_segment_index,
        active_first_event_sequence=(
            snapshot.event_count + 1
            if rotated
            else snapshot.active_first_event_sequence
            if snapshot.event_count > 0
            else 1
        ),
        active_first_prior_event_sha256=(
            snapshot.last_event_sha256
            if rotated
            else snapshot.active_first_prior_event_sha256
            if snapshot.event_count > 0
            else None
        ),
        active_first_event_sha256=(
            validated_event_sha
            if rotated
            else snapshot.active_first_event_sha256
            if snapshot.event_count > 0
            else validated_event_sha
        ),
        sealed_segments=sealed_segments,
        sealed_segments_sha256=sealed_segments_sha256,
        sealed_identities=sealed_identities,
    )
    _verify_retained_snapshot(
        active_path,
        candidate_snapshot,
        feed_anchor=verified_anchor,
        base_path=base_path,
        trusted_root=trusted_root,
        expected_lineage_path=lineage_path,
        expected_segment_index=active_segment_index,
    )
    if newly_sealed_receipts:
        _verify_all_sealed_copies(
            newly_sealed_receipts,
            newly_sealed_identities,
            trusted_root=trusted_root,
        )
        _verify_retained_snapshot(
            active_path,
            candidate_snapshot,
            feed_anchor=verified_anchor,
            base_path=base_path,
            trusted_root=trusted_root,
            expected_lineage_path=lineage_path,
            expected_segment_index=active_segment_index,
        )
    return candidate_snapshot
