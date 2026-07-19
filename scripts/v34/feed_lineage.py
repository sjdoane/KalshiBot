"""Durable replayable lineage for v34 per-game feed lifecycle states."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from collections.abc import Sequence
from contextlib import ExitStack, contextmanager, suppress
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, Never, cast, overload
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


@dataclass(frozen=True, slots=True, eq=False)
class _PersistentHistory[HistoryValue](Sequence[HistoryValue]):
    prior: _PersistentHistory[HistoryValue] | None
    value: HistoryValue
    size: int

    def append(self, value: HistoryValue) -> _PersistentHistory[HistoryValue]:
        return _PersistentHistory(prior=self, value=value, size=self.size + 1)

    def __len__(self) -> int:
        return self.size

    def __iter__(self) -> Iterator[HistoryValue]:
        values: list[HistoryValue] = []
        node: _PersistentHistory[HistoryValue] | None = self
        while node is not None:
            values.append(node.value)
            node = node.prior
        yield from reversed(values)

    @overload
    def __getitem__(self, index: int) -> HistoryValue: ...

    @overload
    def __getitem__(self, index: slice) -> tuple[HistoryValue, ...]: ...

    def __getitem__(self, index: int | slice) -> HistoryValue | tuple[HistoryValue, ...]:
        if isinstance(index, slice):
            return tuple(self)[index]
        normalized = index + self.size if index < 0 else index
        if normalized < 0 or normalized >= self.size:
            raise IndexError(index)
        steps = self.size - normalized - 1
        node: _PersistentHistory[HistoryValue] | None = self
        for _unused in range(steps):
            assert node is not None
            node = node.prior
        assert node is not None
        return node.value

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Sequence) and len(self) == len(other) and all(
            left == right for left, right in zip(self, other, strict=True)
        )


def _persistent_history[HistoryValue](
    values: Sequence[HistoryValue],
) -> tuple[HistoryValue, ...] | _PersistentHistory[HistoryValue]:
    if isinstance(values, _PersistentHistory):
        return values
    node: _PersistentHistory[HistoryValue] | None = None
    for value in values:
        node = _PersistentHistory(
            prior=node,
            value=value,
            size=1 if node is None else node.size + 1,
        )
    return () if node is None else node


def _append_history[HistoryValue](
    values: Sequence[HistoryValue],
    value: HistoryValue,
) -> _PersistentHistory[HistoryValue]:
    retained = _persistent_history(values)
    if isinstance(retained, _PersistentHistory):
        return retained.append(value)
    return _PersistentHistory(prior=None, value=value, size=1)


def _persist_snapshot_history(snapshot: FeedLineageSnapshot) -> FeedLineageSnapshot:
    return replace(
        snapshot,
        sealed_segments=_persistent_history(snapshot.sealed_segments),
        sealed_identities=_persistent_history(snapshot.sealed_identities),
    )


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
    sealed_segments: tuple[FeedSegmentReceipt, ...] | _PersistentHistory[FeedSegmentReceipt]
    sealed_segments_sha256: str | None
    sealed_identities: tuple[FeedSealedIdentity, ...] | _PersistentHistory[FeedSealedIdentity]

    def state_for(self, game_pk: int) -> lifecycle.FeedGameState | None:
        game_pk = _exact_int(game_pk, field="game_pk", minimum=1)
        return dict(self.game_states).get(game_pk)


@dataclass(frozen=True, slots=True)
class FeedPortableHead:
    """A device-independent lineage head suitable for immutable custody."""

    game_pk: int
    event_count: int
    last_event_sha256: str | None
    transition_sequence: int
    state_commitment_sha256: str | None
    game_heads_sha256: str | None
    base_lineage_path: str | None
    active_lineage_path: str | None
    active_segment_index: int
    active_file_size: int
    active_file_sha256: str | None
    active_first_event_sequence: int | None
    active_first_prior_event_sha256: str | None
    active_first_event_sha256: str | None
    sealed_segments_sha256: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "active_file_sha256": self.active_file_sha256,
            "active_file_size": self.active_file_size,
            "active_first_event_sequence": self.active_first_event_sequence,
            "active_first_event_sha256": self.active_first_event_sha256,
            "active_first_prior_event_sha256": (
                self.active_first_prior_event_sha256
            ),
            "active_lineage_path": self.active_lineage_path,
            "active_segment_index": self.active_segment_index,
            "base_lineage_path": self.base_lineage_path,
            "event_count": self.event_count,
            "game_heads_sha256": self.game_heads_sha256,
            "game_pk": self.game_pk,
            "last_event_sha256": self.last_event_sha256,
            "sealed_segments_sha256": self.sealed_segments_sha256,
            "state_commitment_sha256": self.state_commitment_sha256,
            "transition_sequence": self.transition_sequence,
        }


@dataclass(frozen=True, slots=True)
class FeedAppendPlan:
    """Exact append bytes and portable heads frozen before lineage mutation."""

    game_pk: int
    recorded_at: str
    event_bytes: bytes
    payload: bytes
    event_sha256: str
    before_head: FeedPortableHead
    expected_post_head: FeedPortableHead
    should_rotate: bool
    expected_new_sealed_receipt: FeedSegmentReceipt | None


@dataclass(slots=True)
class _FeedHotIntegrity:
    """Process-local SHA state admitted only after one exhaustive replay."""

    head: FeedPortableHead
    active_hasher: Any
    active_descriptor: int | None
    active_path: Path | None
    pending_sealed_descriptors: tuple[tuple[Path, int], ...]

    def close(self) -> None:
        descriptor = self.active_descriptor
        self.active_descriptor = None
        self.active_path = None
        sealed_descriptors = self.pending_sealed_descriptors
        self.pending_sealed_descriptors = ()
        if descriptor is not None:
            os.close(descriptor)
        for _path, sealed_descriptor in sealed_descriptors:
            os.close(sealed_descriptor)


def _open_hot_descriptor(path: Path, *, create_new: bool) -> int:
    """Open the active segment while denying every second writer on Windows."""

    if os.name != "nt":
        flags = os.O_RDWR | getattr(os, "O_BINARY", 0)
        if create_new:
            flags |= os.O_CREAT | os.O_EXCL
        return os.open(path, flags, 0o600)
    import ctypes
    import msvcrt
    from ctypes import wintypes

    kernel32 = cast("Any", ctypes).WinDLL("kernel32", use_last_error=True)
    kernel32.CreateFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    kernel32.CreateFileW.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    handle = kernel32.CreateFileW(
        str(path),
        0x80000000 | 0x40000000,
        0x00000001,
        None,
        1 if create_new else 3,
        0x00000080,
        None,
    )
    invalid = ctypes.c_void_p(-1).value
    if not handle or int(handle) == invalid:
        raise FeedLineageFatalError("exclusive hot lineage descriptor cannot be opened") from ctypes.WinError(
            ctypes.get_last_error()
        )
    try:
        return msvcrt.open_osfhandle(
            int(handle),
            os.O_RDWR | getattr(os, "O_BINARY", 0),
        )
    except OSError:
        kernel32.CloseHandle(handle)
        raise


def _require_hot_descriptor_identity(
    descriptor: int,
    path: Path,
    *,
    device: int,
    inode: int,
    size: int,
    mtime_ns: int,
) -> None:
    descriptor_stat = os.fstat(descriptor)
    linked = _owned_lineage_stat(path)
    if linked is None or any(
        getattr(descriptor_stat, field) != expected
        or getattr(linked, field) != expected
        for field, expected in (
            ("st_dev", device),
            ("st_ino", inode),
            ("st_size", size),
            ("st_mtime_ns", mtime_ns),
        )
    ):
        _fatal("retained feed descriptor identity differs")


@dataclass(frozen=True, slots=True)
class FeedBatchInput:
    path: Path
    transition: lifecycle.FeedTransition
    recorded_at: str
    expected_snapshot: FeedLineageSnapshot | None
    hot_integrity: _FeedHotIntegrity | None = None


@dataclass(frozen=True, slots=True)
class FeedBatchPlan:
    inputs: tuple[FeedBatchInput, ...]
    plans: tuple[FeedAppendPlan, ...]


def portable_head_from_snapshot(
    snapshot: FeedLineageSnapshot,
    *,
    game_pk: int,
) -> FeedPortableHead:
    """Drop local file identities while retaining every replay commitment."""

    game_pk = _exact_int(game_pk, field="game_pk", minimum=1)
    if not isinstance(snapshot, FeedLineageSnapshot):
        _fatal("portable head requires a feed lineage snapshot")
    if snapshot.event_count == 0:
        if snapshot.game_states:
            _fatal("empty portable head unexpectedly contains a game state")
        return FeedPortableHead(
            game_pk=game_pk,
            event_count=0,
            last_event_sha256=None,
            transition_sequence=0,
            state_commitment_sha256=None,
            game_heads_sha256=None,
            base_lineage_path=None,
            active_lineage_path=None,
            active_segment_index=0,
            active_file_size=0,
            active_file_sha256=None,
            active_first_event_sequence=None,
            active_first_prior_event_sha256=None,
            active_first_event_sha256=None,
            sealed_segments_sha256=None,
        )
    state = snapshot.state_for(game_pk)
    if state is None or len(snapshot.game_states) != 1:
        _fatal("portable head game binding differs from the lineage snapshot")
    return FeedPortableHead(
        game_pk=game_pk,
        event_count=snapshot.event_count,
        last_event_sha256=snapshot.last_event_sha256,
        transition_sequence=state.transition_sequence,
        state_commitment_sha256=state.state_commitment_sha256,
        game_heads_sha256=snapshot.game_heads_sha256,
        base_lineage_path=snapshot.base_lineage_path,
        active_lineage_path=snapshot.lineage_path,
        active_segment_index=snapshot.active_segment_index,
        active_file_size=snapshot.file_size,
        active_file_sha256=snapshot.file_sha256,
        active_first_event_sequence=snapshot.active_first_event_sequence,
        active_first_prior_event_sha256=(
            snapshot.active_first_prior_event_sha256
        ),
        active_first_event_sha256=snapshot.active_first_event_sha256,
        sealed_segments_sha256=snapshot.sealed_segments_sha256,
    )


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


def _sealed_segments_sha256(receipts: Sequence[FeedSegmentReceipt]) -> str:
    digest = policy.canonical_sha256({"sealed_segment_chain": "v34"})
    for receipt in receipts:
        digest = _extend_sealed_segments_sha256(digest, receipt)
    return digest


def _extend_sealed_segments_sha256(
    prior_sha256: str,
    receipt: FeedSegmentReceipt,
) -> str:
    try:
        prior = policy.validate_sha256(
            prior_sha256,
            field="sealed_segment_chain.prior_sha256",
        )
    except (TypeError, ValueError) as exc:
        _fatal("sealed segment prior commitment is invalid", cause=exc)
    if not isinstance(receipt, FeedSegmentReceipt):
        _fatal("sealed segment chain receipt has the wrong type")
    return policy.canonical_sha256(
        {
            "prior_sealed_segments_sha256": prior,
            "sealed_segment": receipt.to_dict(),
        }
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
    receipts: Sequence[FeedSegmentReceipt],
    *,
    base_path: Path,
    trusted_root: Path,
    feed_anchor: policy.FeedLaunchAnchor,
) -> None:
    if not isinstance(receipts, (tuple, _PersistentHistory)):
        _fatal("sealed segment receipts are not immutable history")
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


def _validate_appended_segment_receipt(
    receipt: FeedSegmentReceipt,
    *,
    prior_receipt: FeedSegmentReceipt | None,
    base_path: Path,
    trusted_root: Path,
    feed_anchor: policy.FeedLaunchAnchor,
) -> None:
    expected_index = 1 if prior_receipt is None else prior_receipt.segment_index + 1
    prior_last_sequence = 0 if prior_receipt is None else prior_receipt.last_event_sequence
    prior_last_sha = None if prior_receipt is None else prior_receipt.last_event_sha256
    if not isinstance(receipt, FeedSegmentReceipt):
        _fatal("appended sealed segment receipt has the wrong type")
    if set(receipt.to_dict()) != SEGMENT_RECEIPT_KEYS:
        _fatal("appended sealed segment receipt keys differ")
    base_lineage_path = _lineage_relative_path(base_path, trusted_root=trusted_root)
    if receipt.base_lineage_path != base_lineage_path:
        _fatal("appended sealed segment base path differs")
    if receipt.segment_index != expected_index:
        _fatal("appended sealed segment index is not contiguous")
    expected_path = _segment_path(base_path, expected_index)
    if receipt.lineage_path != _lineage_relative_path(
        expected_path,
        trusted_root=trusted_root,
    ):
        _fatal("appended sealed segment lineage path differs")
    expected_archive_path = _lineage_relative_path(
        _segment_archive_path(
            base_path,
            segment_index=expected_index,
            file_sha256=receipt.file_sha256,
        ),
        trusted_root=trusted_root,
    )
    if receipt.archive_path != expected_archive_path:
        _fatal("appended sealed segment archive path differs")
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
        _fatal("appended sealed segment sequence is not contiguous")
    if last_sequence != first_sequence + event_count - 1:
        _fatal("appended sealed segment event count differs")
    if receipt.first_prior_event_sha256 != prior_last_sha:
        _fatal("appended sealed segment prior head differs")
    for field_name, value in (
        ("first_event_sha256", receipt.first_event_sha256),
        ("last_event_sha256", receipt.last_event_sha256),
        ("file_sha256", receipt.file_sha256),
    ):
        try:
            policy.validate_sha256(value, field=f"segment.{field_name}")
        except (TypeError, ValueError) as exc:
            _fatal(f"appended sealed segment {field_name} is invalid", cause=exc)
    if _exact_int(receipt.file_size, field="segment.file_size", minimum=1) > (
        MAX_ACTIVE_SEGMENT_BYTES
    ):
        _fatal("appended sealed segment exceeds the byte limit")
    if receipt.launch_manifest_sha256 != feed_anchor.manifest_sha256:
        _fatal("appended sealed segment launch provenance differs")


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
    sealed_receipts: Sequence[FeedSegmentReceipt],
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
    if not isinstance(snapshot.sealed_identities, (tuple, _PersistentHistory)) or len(
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
    source_descriptor: int | None = None,
) -> tuple[FeedSegmentReceipt, FeedSealedIdentity]:
    receipt = _receipt_from_active_snapshot(
        snapshot,
        base_path=base_path,
        trusted_root=trusted_root,
        feed_anchor=feed_anchor,
    )
    try:
        if source_descriptor is None:
            source_bytes = feed_archive._stable_owned_file_bytes(path)
        else:
            opened = os.fstat(source_descriptor)
            if opened.st_size > MAX_ACTIVE_SEGMENT_BYTES:
                _fatal("active segment exceeds the sealing byte bound")
            os.lseek(source_descriptor, 0, os.SEEK_SET)
            source_bytes = os.read(source_descriptor, opened.st_size + 1)
            closing = os.fstat(source_descriptor)
            if len(source_bytes) != opened.st_size or any(
                getattr(opened, field) != getattr(closing, field)
                for field in ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_nlink")
            ):
                _fatal("active segment changed during descriptor-bound sealing")
            os.lseek(source_descriptor, 0, os.SEEK_END)
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
        feed_archive._write_create_once_hot(archive_path, source_bytes)
        archive_bytes = feed_archive._stable_owned_file_bytes_bounded(
            archive_path,
            max_bytes=len(source_bytes),
            recover_internal_links=False,
        )
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
    if source_descriptor is None:
        _verify_all_sealed_copies((receipt,), (identity,), trusted_root=trusted_root)
    return receipt, identity


def _verify_all_sealed_copies(
    receipts: Sequence[FeedSegmentReceipt],
    identities: Sequence[FeedSealedIdentity],
    *,
    trusted_root: Path,
    retained_descriptors: Mapping[Path, int] | None = None,
    recover_internal_links: bool = True,
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
            source_descriptor = (
                None
                if retained_descriptors is None
                else retained_descriptors.get(source_path)
            )
            archive_descriptor = (
                None
                if retained_descriptors is None
                else retained_descriptors.get(archive_path)
            )
            if source_descriptor is None:
                source_bytes = feed_archive._stable_owned_file_bytes_bounded(
                    source_path,
                    max_bytes=receipt.file_size,
                    recover_internal_links=recover_internal_links,
                )
            else:
                source_bytes = _read_hot_descriptor_bytes(
                    source_descriptor,
                    source_path,
                    device=identity.source_device,
                    inode=identity.source_inode,
                    size=receipt.file_size,
                    mtime_ns=identity.source_mtime_ns,
                )
            if archive_descriptor is None:
                archive_bytes = feed_archive._stable_owned_file_bytes_bounded(
                    archive_path,
                    max_bytes=receipt.file_size,
                    recover_internal_links=recover_internal_links,
                )
            else:
                archive_bytes = _read_hot_descriptor_bytes(
                    archive_descriptor,
                    archive_path,
                    device=identity.archive_device,
                    inode=identity.archive_inode,
                    size=receipt.file_size,
                    mtime_ns=identity.archive_mtime_ns,
                )
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


def _read_hot_descriptor_bytes(
    descriptor: int,
    path: Path,
    *,
    device: int,
    inode: int,
    size: int,
    mtime_ns: int,
) -> bytes:
    _require_hot_descriptor_identity(
        descriptor,
        path,
        device=device,
        inode=inode,
        size=size,
        mtime_ns=mtime_ns,
    )
    if size > MAX_ACTIVE_SEGMENT_BYTES or os.lseek(descriptor, 0, os.SEEK_SET) != 0:
        _fatal("retained sealed descriptor exceeds its read bound")
    chunks: list[bytes] = []
    bytes_read = 0
    while bytes_read < size:
        chunk = os.read(descriptor, min(FILE_HASH_CHUNK_BYTES, size - bytes_read))
        if not chunk:
            _fatal("retained sealed descriptor ended before its exact size")
        chunks.append(chunk)
        bytes_read += len(chunk)
    if os.read(descriptor, 1):
        _fatal("retained sealed descriptor exceeds its exact size")
    _require_hot_descriptor_identity(
        descriptor,
        path,
        device=device,
        inode=inode,
        size=size,
        mtime_ns=mtime_ns,
    )
    return b"".join(chunks)


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
    expected_sealed_segment_count: int | None = None,
    expected_sealed_segments_sha256: str | None = None,
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
    expected_receipts = expected_sealed_segments
    _validate_segment_receipts(
        expected_receipts,
        base_path=path,
        trusted_root=trusted_root,
        feed_anchor=verified_anchor,
    )
    sealed_segment_count = (
        len(expected_receipts)
        if expected_sealed_segment_count is None
        else _exact_int(
            expected_sealed_segment_count,
            field="expected_sealed_segment_count",
        )
    )
    if expected_receipts and len(expected_receipts) != sealed_segment_count:
        _fatal("expected sealed receipt inventory count differs")
    if expected_count == 0 and sealed_segment_count != 0:
        _fatal("empty expected lineage cannot have sealed segments")
    active_segment_index = sealed_segment_count + 1
    active_path = _segment_path(path, active_segment_index)
    candidate = _owned_lineage_stat(active_path)
    if candidate is None:
        if expected_count != 0:
            _fatal("expected nonempty feed lineage is missing")
        if sealed_segment_count:
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
    replayed_receipts: list[FeedSegmentReceipt] = []
    sealed_segments_sha256 = _sealed_segments_sha256(())
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
        segment_sealed_sha256 = sealed_segments_sha256
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
        if segment_index <= sealed_segment_count:
            archive_path = _segment_archive_path(
                path,
                segment_index=segment_index,
                file_sha256=segment_file_sha256,
            )
            observed_receipt = FeedSegmentReceipt(
                base_lineage_path=base_lineage_path,
                lineage_path=segment_lineage_path,
                archive_path=_lineage_relative_path(
                    archive_path,
                    trusted_root=trusted_root,
                ),
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
            if expected_receipts and observed_receipt != expected_receipts[segment_index - 1]:
                _fatal("sealed segment replay differs from its exact receipt")
            _validate_appended_segment_receipt(
                observed_receipt,
                prior_receipt=(replayed_receipts[-1] if replayed_receipts else None),
                base_path=path,
                trusted_root=trusted_root,
                feed_anchor=verified_anchor,
            )
            replayed_receipts.append(observed_receipt)
            sealed_segments_sha256 = _extend_sealed_segments_sha256(
                sealed_segments_sha256,
                observed_receipt,
            )
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
    if (
        expected_sealed_segments_sha256 is not None
        and sealed_segments_sha256 != expected_sealed_segments_sha256
    ):
        _fatal("feed lineage sealed segment commitment differs from retained head")
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
        sealed_segments=tuple(replayed_receipts),
        sealed_segments_sha256=sealed_segments_sha256,
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
        tuple(replayed_receipts),
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


def _open_hot_integrity(
    base_path: Path,
    snapshot: FeedLineageSnapshot,
    *,
    game_pk: int,
    trusted_root: Path,
) -> _FeedHotIntegrity:
    """Capture resumable active-segment SHA state after exhaustive replay."""

    head = portable_head_from_snapshot(snapshot, game_pk=game_pk)
    hasher = hashlib.sha256()
    if snapshot.event_count == 0:
        if _owned_lineage_stat(base_path) is not None:
            _fatal("empty hot lineage unexpectedly exists")
        return _FeedHotIntegrity(
            head=head,
            active_hasher=hasher,
            active_descriptor=None,
            active_path=None,
            pending_sealed_descriptors=(),
        )
    active_path = trusted_root / Path(head.active_lineage_path or "")
    expected = _owned_lineage_stat(active_path)
    if expected is None or any(
        getattr(expected, field) != value
        for field, value in (
            ("st_dev", snapshot.file_device),
            ("st_ino", snapshot.file_inode),
            ("st_size", snapshot.file_size),
            ("st_mtime_ns", snapshot.file_mtime_ns),
        )
    ):
        _fatal("hot lineage identity differs after exhaustive replay")
    bytes_read = 0
    descriptor = _open_hot_descriptor(active_path, create_new=False)
    try:
        opened = os.fstat(descriptor)
        if any(
            getattr(opened, field) != getattr(expected, field)
            for field in ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_nlink")
        ):
            _fatal("hot lineage changed before SHA state capture")
        os.lseek(descriptor, 0, os.SEEK_SET)
        while True:
            chunk = os.read(descriptor, FILE_HASH_CHUNK_BYTES)
            if not chunk:
                break
            bytes_read += len(chunk)
            if bytes_read > MAX_ACTIVE_SEGMENT_BYTES:
                _fatal("hot lineage exceeds the active segment byte limit")
            hasher.update(chunk)
        closing = os.fstat(descriptor)
        current = _owned_lineage_stat(active_path)
        if current is None or bytes_read != expected.st_size or any(
            getattr(opened, field) != getattr(closing, field)
            or getattr(closing, field) != getattr(current, field)
            for field in ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_nlink")
        ):
            _fatal("hot lineage changed during SHA state capture")
        if hasher.hexdigest() != snapshot.file_sha256:
            _fatal("hot lineage SHA state differs from exhaustive replay")
        return _FeedHotIntegrity(
            head=head,
            active_hasher=hasher,
            active_descriptor=descriptor,
            active_path=active_path,
            pending_sealed_descriptors=(),
        )
    except Exception:
        os.close(descriptor)
        raise


def _verify_hot_integrity(
    base_path: Path,
    snapshot: FeedLineageSnapshot,
    hot_integrity: _FeedHotIntegrity,
    *,
    game_pk: int,
    trusted_root: Path,
) -> os.stat_result | None:
    """Verify bounded live state under a continuously watched runtime tree."""

    if not isinstance(hot_integrity, _FeedHotIntegrity):
        _fatal("feed hot integrity state has the wrong type")
    head = portable_head_from_snapshot(snapshot, game_pk=game_pk)
    if hot_integrity.head != head:
        _fatal("feed hot integrity head differs from the retained snapshot")
    try:
        retained_digest = hot_integrity.active_hasher.copy().hexdigest()
    except (AttributeError, TypeError, ValueError) as exc:
        _fatal("feed hot integrity SHA state is invalid", cause=exc)
    if retained_digest != head.active_file_sha256 and head.event_count != 0:
        _fatal("feed hot integrity digest differs from the retained snapshot")
    if head.event_count == 0:
        if retained_digest != hashlib.sha256().hexdigest():
            _fatal("empty feed hot integrity digest differs")
        if _owned_lineage_stat(base_path) is not None:
            _fatal("empty feed hot integrity path unexpectedly exists")
        if hot_integrity.active_descriptor is not None or hot_integrity.active_path is not None:
            _fatal("empty feed hot integrity unexpectedly owns a descriptor")
        if hot_integrity.pending_sealed_descriptors:
            _fatal("empty feed hot integrity unexpectedly owns sealed descriptors")
        return None
    active_path = trusted_root / Path(head.active_lineage_path or "")
    descriptor = hot_integrity.active_descriptor
    if descriptor is None or hot_integrity.active_path != active_path:
        _fatal("feed hot integrity active descriptor differs")
    descriptor_stat = os.fstat(descriptor)
    current = _owned_lineage_stat(active_path)
    if current is None or any(
        getattr(current, field) != value or getattr(descriptor_stat, field) != value
        for field, value in (
            ("st_dev", snapshot.file_device),
            ("st_ino", snapshot.file_inode),
            ("st_size", head.active_file_size),
            ("st_mtime_ns", snapshot.file_mtime_ns),
        )
    ):
        _fatal("feed hot integrity active identity differs")
    terminal = _read_bounded_terminal_event(
        active_path,
        file_size=head.active_file_size,
    )
    if _sha256(terminal) != head.last_event_sha256:
        _fatal("feed hot integrity terminal event differs")
    if snapshot.sealed_segments:
        if len(snapshot.sealed_identities) != len(snapshot.sealed_segments):
            _fatal("feed hot sealed identities do not align")
        receipt = snapshot.sealed_segments[-1]
        identity = snapshot.sealed_identities[-1]
        if hot_integrity.pending_sealed_descriptors:
            source_path = trusted_root / Path(receipt.lineage_path)
            archive_path = trusted_root / Path(receipt.archive_path)
            if tuple(
                path for path, _descriptor in hot_integrity.pending_sealed_descriptors
            ) != (source_path, archive_path):
                _fatal("feed hot pending sealed descriptor inventory differs")
            source_descriptor = hot_integrity.pending_sealed_descriptors[0][1]
            archive_descriptor = hot_integrity.pending_sealed_descriptors[1][1]
            _require_hot_descriptor_identity(
                source_descriptor,
                source_path,
                device=identity.source_device,
                inode=identity.source_inode,
                size=receipt.file_size,
                mtime_ns=identity.source_mtime_ns,
            )
            _require_hot_descriptor_identity(
                archive_descriptor,
                archive_path,
                device=identity.archive_device,
                inode=identity.archive_inode,
                size=receipt.file_size,
                mtime_ns=identity.archive_mtime_ns,
            )
        source = _owned_lineage_stat(trusted_root / Path(receipt.lineage_path))
        archive = _owned_lineage_stat(trusted_root / Path(receipt.archive_path))
        if source is None or archive is None or (
            source.st_dev,
            source.st_ino,
            source.st_size,
            source.st_mtime_ns,
        ) != (
            identity.source_device,
            identity.source_inode,
            receipt.file_size,
            identity.source_mtime_ns,
        ) or (
            archive.st_dev,
            archive.st_ino,
            archive.st_size,
            archive.st_mtime_ns,
        ) != (
            identity.archive_device,
            identity.archive_inode,
            receipt.file_size,
            identity.archive_mtime_ns,
        ):
            _fatal("feed hot integrity newest sealed identity differs")
    elif hot_integrity.pending_sealed_descriptors:
        _fatal("feed hot integrity owns unexpected sealed descriptors")
    return current


def _release_pending_sealed_descriptors(
    base_path: Path,
    snapshot: FeedLineageSnapshot,
    hot_integrity: _FeedHotIntegrity,
    *,
    game_pk: int,
    trusted_root: Path,
    require_pending: bool,
) -> None:
    """Close only this transaction's rotation handles after final settle."""

    _verify_hot_integrity(
        base_path,
        snapshot,
        hot_integrity,
        game_pk=game_pk,
        trusted_root=trusted_root,
    )
    pending = hot_integrity.pending_sealed_descriptors
    if bool(pending) != require_pending:
        _fatal("feed hot pending rotation state differs from the committed plan")
    if not pending:
        return
    if not snapshot.sealed_segments or not snapshot.sealed_identities:
        _fatal("feed hot pending rotation lacks a sealed receipt")
    receipt = snapshot.sealed_segments[-1]
    identity = snapshot.sealed_identities[-1]
    _verify_all_sealed_copies(
        (receipt,),
        (identity,),
        trusted_root=trusted_root,
        retained_descriptors=dict(pending),
    )
    hot_integrity.pending_sealed_descriptors = ()
    close_error: OSError | None = None
    for _path, descriptor in pending:
        try:
            os.close(descriptor)
        except OSError as exc:
            close_error = exc
    if close_error is not None:
        _fatal("feed hot pending rotation descriptor cannot close", cause=close_error)
    _verify_all_sealed_copies(
        (receipt,),
        (identity,),
        trusted_root=trusted_root,
        recover_internal_links=False,
    )
    _verify_hot_integrity(
        base_path,
        snapshot,
        hot_integrity,
        game_pk=game_pk,
        trusted_root=trusted_root,
    )


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


def _append_exact_payload_hot(
    path: Path,
    payload: bytes,
    *,
    before: os.stat_result | None,
    snapshot: FeedLineageSnapshot,
    hot_integrity: _FeedHotIntegrity,
    starts_new_segment: bool,
    verify_lock_ownership: Callable[[], None],
) -> tuple[os.stat_result, str, Any, int]:
    """Append through the sole writer descriptor retained by the live session."""

    hasher = (
        hashlib.sha256()
        if starts_new_segment
        else hot_integrity.active_hasher.copy()
    )
    if not starts_new_segment and snapshot.event_count > 0 and (
        hasher.hexdigest() != snapshot.file_sha256
    ):
        _fatal("hot append prefix digest differs from the retained snapshot")
    hasher.update(payload)
    verify_lock_ownership()
    descriptor: int
    opened_new_descriptor = False
    if before is None:
        descriptor = _open_hot_descriptor(path, create_new=True)
        opened_new_descriptor = True
        try:
            if os.write(descriptor, payload) != len(payload):
                _fatal("hot lineage initial append write was incomplete")
            os.fsync(descriptor)
            verify_lock_ownership()
            after_descriptor = os.fstat(descriptor)
            if (
                not stat.S_ISREG(after_descriptor.st_mode)
                or after_descriptor.st_nlink != 1
                or after_descriptor.st_size != len(payload)
            ):
                _fatal("hot lineage initial append identity or size changed")
        except Exception:
            os.close(descriptor)
            raise
    else:
        descriptor = hot_integrity.active_descriptor or -1
        if descriptor < 0 or hot_integrity.active_path != path:
            _fatal("hot lineage sole writer descriptor differs")
        opened = os.fstat(descriptor)
        if any(
            getattr(opened, field) != getattr(before, field)
            for field in (
                "st_dev",
                "st_ino",
                "st_size",
                "st_mtime_ns",
                "st_nlink",
            )
        ):
            _fatal("hot lineage changed before descriptor-bound append")
        if os.lseek(descriptor, 0, os.SEEK_END) != before.st_size:
            _fatal("hot lineage append offset differs from retained size")
        if os.write(descriptor, payload) != len(payload):
            _fatal("hot lineage append write was incomplete")
        os.fsync(descriptor)
        verify_lock_ownership()
        after_descriptor = os.fstat(descriptor)
        if (
            after_descriptor.st_dev != before.st_dev
            or after_descriptor.st_ino != before.st_ino
            or after_descriptor.st_nlink != 1
            or after_descriptor.st_size != before.st_size + len(payload)
        ):
            _fatal("hot lineage descriptor identity or append size changed")
    after = _owned_lineage_stat(path)
    if after is None or any(
        getattr(after_descriptor, field) != getattr(after, field)
        for field in ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_nlink")
    ):
        if opened_new_descriptor:
            os.close(descriptor)
        _fatal("hot lineage path differs from the appended descriptor")
    feed_archive._fsync_directory(path.parent)
    return after, hasher.hexdigest(), hasher, descriptor


def _planned_active_file_sha256(
    path: Path,
    payload: bytes,
    *,
    before: os.stat_result | None,
    snapshot: FeedLineageSnapshot,
) -> str:
    """Hash the exact retained prefix plus payload without mutating the file."""

    if before is None:
        return _sha256(payload)
    hasher = hashlib.sha256()
    bytes_read = 0
    with path.open("rb") as handle:
        opened = os.fstat(handle.fileno())
        if any(
            getattr(opened, field) != getattr(before, field)
            for field in ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_nlink")
        ):
            _fatal("feed lineage changed before planned hash calculation")
        while True:
            chunk = handle.read(FILE_HASH_CHUNK_BYTES)
            if not chunk:
                break
            bytes_read += len(chunk)
            if bytes_read > MAX_LINEAGE_FILE_BYTES:
                _fatal("feed lineage exceeds the planned hash byte limit")
            hasher.update(chunk)
        closing = os.fstat(handle.fileno())
    if bytes_read != before.st_size or any(
        getattr(opened, field) != getattr(closing, field)
        for field in ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_nlink")
    ):
        _fatal("feed lineage changed during planned hash calculation")
    if hasher.hexdigest() != snapshot.file_sha256:
        _fatal("planned hash prefix differs from the retained snapshot")
    current = _owned_lineage_stat(path)
    if current is None or any(
        getattr(closing, field) != getattr(current, field)
        for field in ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_nlink")
    ):
        _fatal("feed lineage changed after planned hash calculation")
    hasher.update(payload)
    return hasher.hexdigest()


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
    expected_sealed_segment_count: int | None = None,
    expected_sealed_segments_sha256: str | None = None,
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
            expected_sealed_segment_count=expected_sealed_segment_count,
            expected_sealed_segments_sha256=expected_sealed_segments_sha256,
            trusted_root=trusted_root,
        )


def _append_feed_transition_uncommitted(
    path: Path,
    transition: lifecycle.FeedTransition,
    *,
    feed_anchor: policy.FeedLaunchAnchor,
    recorded_at: Callable[[], str],
    expected_snapshot: FeedLineageSnapshot,
    before_apply: Callable[[FeedAppendPlan], None] | None = None,
    after_apply: (
        Callable[
            [FeedAppendPlan, FeedLineageSnapshot, Callable[[], None]],
            None,
        ]
        | None
    ) = None,
    trusted_root: Path = policy.REPOSITORY_ROOT,
) -> FeedLineageSnapshot:
    """Test-only raw append. Production must use the reviewed head ledger."""

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
            before_apply=before_apply,
            after_apply=after_apply,
            trusted_root=trusted_root,
            verify_lock_ownership=verify_lock,
        )


def append_prepared_feed_transition(
    path: Path,
    transition: lifecycle.FeedTransition,
    *,
    plan: FeedAppendPlan,
    feed_anchor: policy.FeedLaunchAnchor,
    expected_snapshot: FeedLineageSnapshot,
    after_apply: (
        Callable[
            [FeedAppendPlan, FeedLineageSnapshot, Callable[[], None]],
            None,
        ]
        | None
    ) = None,
    trusted_root: Path = policy.REPOSITORY_ROOT,
) -> FeedLineageSnapshot:
    """Execute only when a fresh plan exactly matches the durable PREPARE."""

    if not isinstance(plan, FeedAppendPlan):
        _fatal("prepared append requires a FeedAppendPlan")

    def require_exact_plan(candidate: FeedAppendPlan) -> None:
        if candidate != plan:
            _fatal("fresh append plan differs from the durable PREPARE")

    return _append_feed_transition_uncommitted(
        path,
        transition,
        feed_anchor=feed_anchor,
        recorded_at=lambda: plan.recorded_at,
        expected_snapshot=expected_snapshot,
        before_apply=require_exact_plan,
        after_apply=after_apply,
        trusted_root=trusted_root,
    )


def _reconcile_prepared_feed_transition(
    path: Path,
    transition: lifecycle.FeedTransition,
    *,
    plan: FeedAppendPlan,
    feed_anchor: policy.FeedLaunchAnchor,
    after_apply: Callable[
        [FeedAppendPlan, FeedLineageSnapshot, Callable[[], None]],
        None,
    ],
    trusted_root: Path = policy.REPOSITORY_ROOT,
) -> FeedLineageSnapshot:
    """Resolve one durable PREPARE while retaining the lineage lock."""

    if not isinstance(plan, FeedAppendPlan):
        _fatal("prepared reconciliation requires a FeedAppendPlan")

    def replay_head(head: FeedPortableHead) -> FeedLineageSnapshot:
        snapshot = _replay_feed_lineage_locked(
            path,
            feed_anchor=feed_anchor,
            expected_event_count=head.event_count,
            expected_last_event_sha256=head.last_event_sha256,
            expected_sealed_segment_count=max(head.active_segment_index - 1, 0),
            expected_sealed_segments_sha256=head.sealed_segments_sha256,
            trusted_root=trusted_root,
        )
        if portable_head_from_snapshot(snapshot, game_pk=plan.game_pk) != head:
            _fatal("prepared reconciliation replay differs from its portable head")
        return snapshot

    with _exclusive_append_lock(path, trusted_root=trusted_root) as verify_lock:
        try:
            prior_snapshot = replay_head(plan.before_head)
        except FeedLineageFatalError:
            prior_snapshot = None
        try:
            post_snapshot = replay_head(plan.expected_post_head)
        except FeedLineageFatalError:
            post_snapshot = None
        if (prior_snapshot is None) == (post_snapshot is None):
            _fatal("durable PREPARE does not match exactly one candidate head")
        if prior_snapshot is not None:

            def require_exact_plan(candidate: FeedAppendPlan) -> None:
                if candidate != plan:
                    _fatal("fresh append plan differs from the durable PREPARE")

            return _append_feed_transition_locked(
                path,
                transition,
                feed_anchor=feed_anchor,
                recorded_at=lambda: plan.recorded_at,
                expected_snapshot=prior_snapshot,
                before_apply=require_exact_plan,
                after_apply=after_apply,
                trusted_root=trusted_root,
                verify_lock_ownership=verify_lock,
            )
        assert post_snapshot is not None

        def reverify_post() -> None:
            replay_head(plan.expected_post_head)

        after_apply(plan, post_snapshot, reverify_post)
        reverify_post()
        return post_snapshot


class _FeedPlanCapturedError(RuntimeError):
    pass


def _capture_feed_plan_locked(
    item: FeedBatchInput,
    *,
    feed_anchor: policy.FeedLaunchAnchor,
    trusted_root: Path,
    verify_lock_ownership: Callable[[], None],
) -> FeedAppendPlan:
    if item.expected_snapshot is None:
        _fatal("fresh feed batch input is missing its expected snapshot")
    captured: list[FeedAppendPlan] = []

    def capture(plan: FeedAppendPlan) -> None:
        captured.append(plan)
        raise _FeedPlanCapturedError

    with suppress(_FeedPlanCapturedError):
        _append_feed_transition_locked(
            item.path,
            item.transition,
            feed_anchor=feed_anchor,
            recorded_at=lambda: item.recorded_at,
            expected_snapshot=item.expected_snapshot,
            before_apply=capture,
            after_apply=None,
            trusted_root=trusted_root,
            verify_lock_ownership=verify_lock_ownership,
            hot_integrity=item.hot_integrity,
        )
    if len(captured) != 1:
        _fatal("batch planning did not capture exactly one feed plan")
    return captured[0]


def _replay_portable_head_locked(
    path: Path,
    head: FeedPortableHead,
    *,
    feed_anchor: policy.FeedLaunchAnchor,
    trusted_root: Path,
) -> FeedLineageSnapshot:
    snapshot = _replay_feed_lineage_locked(
        path,
        feed_anchor=feed_anchor,
        expected_event_count=head.event_count,
        expected_last_event_sha256=head.last_event_sha256,
        expected_sealed_segment_count=max(head.active_segment_index - 1, 0),
        expected_sealed_segments_sha256=head.sealed_segments_sha256,
        trusted_root=trusted_root,
    )
    if portable_head_from_snapshot(snapshot, game_pk=head.game_pk) != head:
        _fatal("batch replay differs from its portable head")
    return snapshot


def _validate_batch_inputs(
    inputs: tuple[FeedBatchInput, ...],
    *,
    require_snapshots: bool,
) -> tuple[FeedBatchInput, ...]:
    if type(inputs) is not tuple or not inputs:
        _fatal("feed batch inputs must be a nonempty immutable tuple")
    if len(inputs) > 64:
        _fatal("feed batch exceeds the maximum game count")
    for item in inputs:
        if (
            not isinstance(item, FeedBatchInput)
            or not isinstance(item.path, Path)
            or not isinstance(item.transition, lifecycle.FeedTransition)
            or (
                item.expected_snapshot is not None
                and not isinstance(item.expected_snapshot, FeedLineageSnapshot)
            )
            or (
                item.hot_integrity is not None
                and not isinstance(item.hot_integrity, _FeedHotIntegrity)
            )
        ):
            _fatal("feed batch input has the wrong type")
        if require_snapshots and item.expected_snapshot is None:
            _fatal("fresh feed batch input is missing its expected snapshot")
        _parse_utc(item.recorded_at, field="batch.recorded_at")
    ordered = tuple(sorted(inputs, key=lambda item: item.transition.state.game_pk))
    game_pks = [item.transition.state.game_pk for item in ordered]
    paths = [_lexical_path_key(item.path) for item in ordered]
    if len(game_pks) != len(set(game_pks)) or len(paths) != len(set(paths)):
        _fatal("feed batch contains a duplicate game or lineage path")
    return ordered


def _lexical_path_key(path: Path) -> str:
    return os.path.normcase(str(path.absolute()))


def _apply_feed_transition_batch(
    inputs: tuple[FeedBatchInput, ...],
    *,
    feed_anchor: policy.FeedLaunchAnchor,
    before_batch: Callable[[FeedBatchPlan], None],
    after_batch: Callable[
        [FeedBatchPlan, tuple[FeedLineageSnapshot, ...], Callable[[], None]],
        None,
    ],
    operation_applied: Callable[[int], None] | None = None,
    trusted_root: Path = policy.REPOSITORY_ROOT,
) -> tuple[FeedLineageSnapshot, ...]:
    """Apply one exact all-game batch under every per-lineage lock."""

    ordered = _validate_batch_inputs(inputs, require_snapshots=True)
    with ExitStack() as stack:
        verifiers = [
            stack.enter_context(
                _exclusive_append_lock(item.path, trusted_root=trusted_root)
            )
            for item in ordered
        ]
        plans = tuple(
            _capture_feed_plan_locked(
                item,
                feed_anchor=feed_anchor,
                trusted_root=trusted_root,
                verify_lock_ownership=verify,
            )
            for item, verify in zip(ordered, verifiers, strict=True)
        )
        batch_plan = FeedBatchPlan(inputs=ordered, plans=plans)
        before_batch(batch_plan)
        snapshots: list[FeedLineageSnapshot] = []
        for operation_index, (item, expected_plan, verify) in enumerate(
            zip(ordered, plans, verifiers, strict=True),
            start=1,
        ):
            assert item.expected_snapshot is not None

            def require_exact_plan(
                candidate: FeedAppendPlan,
                *,
                frozen: FeedAppendPlan = expected_plan,
            ) -> None:
                if candidate != frozen:
                    _fatal("feed batch plan changed after durable PREPARE")

            def frozen_recorded_at(value: str = item.recorded_at) -> str:
                return value

            snapshots.append(
                _append_feed_transition_locked(
                    item.path,
                    item.transition,
                    feed_anchor=feed_anchor,
                    recorded_at=frozen_recorded_at,
                    expected_snapshot=item.expected_snapshot,
                    before_apply=require_exact_plan,
                    after_apply=None,
                    trusted_root=trusted_root,
                    verify_lock_ownership=verify,
                    hot_integrity=item.hot_integrity,
                )
            )
            if operation_applied is not None:
                operation_applied(operation_index)
        frozen_snapshots = tuple(snapshots)

        def reverify_all() -> None:
            for item, plan, snapshot in zip(
                ordered,
                plans,
                frozen_snapshots,
                strict=True,
            ):
                if item.hot_integrity is None:
                    _replay_portable_head_locked(
                        item.path,
                        plan.expected_post_head,
                        feed_anchor=feed_anchor,
                        trusted_root=trusted_root,
                    )
                else:
                    _verify_hot_integrity(
                        item.path,
                        snapshot,
                        item.hot_integrity,
                        game_pk=plan.game_pk,
                        trusted_root=trusted_root,
                    )

        after_batch(batch_plan, frozen_snapshots, reverify_all)
        reverify_all()
        return frozen_snapshots


def _reconcile_feed_transition_batch(
    batch_plan: FeedBatchPlan,
    *,
    feed_anchor: policy.FeedLaunchAnchor,
    after_batch: Callable[
        [FeedBatchPlan, tuple[FeedLineageSnapshot, ...], Callable[[], None]],
        None,
    ],
    trusted_root: Path = policy.REPOSITORY_ROOT,
) -> tuple[FeedLineageSnapshot, ...]:
    """Complete every operation in one durable batch PREPARE."""

    ordered = _validate_batch_inputs(
        batch_plan.inputs,
        require_snapshots=False,
    )
    if ordered != batch_plan.inputs or len(batch_plan.plans) != len(ordered):
        _fatal("durable feed batch plan ordering differs")
    with ExitStack() as stack:
        verifiers = [
            stack.enter_context(
                _exclusive_append_lock(item.path, trusted_root=trusted_root)
            )
            for item in ordered
        ]
        snapshots: list[FeedLineageSnapshot] = []
        for item, plan, verify in zip(
            ordered,
            batch_plan.plans,
            verifiers,
            strict=True,
        ):
            try:
                prior = _replay_portable_head_locked(
                    item.path,
                    plan.before_head,
                    feed_anchor=feed_anchor,
                    trusted_root=trusted_root,
                )
            except FeedLineageFatalError:
                prior = None
            try:
                post = _replay_portable_head_locked(
                    item.path,
                    plan.expected_post_head,
                    feed_anchor=feed_anchor,
                    trusted_root=trusted_root,
                )
            except FeedLineageFatalError:
                post = None
            if (prior is None) == (post is None):
                _fatal("batch PREPARE operation does not match exactly one head")
            if prior is not None:

                def require_exact_plan(
                    candidate: FeedAppendPlan,
                    *,
                    frozen: FeedAppendPlan = plan,
                ) -> None:
                    if candidate != frozen:
                        _fatal("recovered feed batch plan differs from PREPARE")

                def frozen_recorded_at(value: str = item.recorded_at) -> str:
                    return value

                post = _append_feed_transition_locked(
                    item.path,
                    item.transition,
                    feed_anchor=feed_anchor,
                    recorded_at=frozen_recorded_at,
                    expected_snapshot=prior,
                    before_apply=require_exact_plan,
                    after_apply=None,
                    trusted_root=trusted_root,
                    verify_lock_ownership=verify,
                )
            assert post is not None
            snapshots.append(post)
        frozen_snapshots = tuple(snapshots)

        def reverify_all() -> None:
            for item, plan in zip(
                ordered,
                batch_plan.plans,
                strict=True,
            ):
                _replay_portable_head_locked(
                    item.path,
                    plan.expected_post_head,
                    feed_anchor=feed_anchor,
                    trusted_root=trusted_root,
                )

        after_batch(batch_plan, frozen_snapshots, reverify_all)
        reverify_all()
        return frozen_snapshots


def _append_feed_transition_locked(
    path: Path,
    transition: lifecycle.FeedTransition,
    *,
    feed_anchor: policy.FeedLaunchAnchor,
    recorded_at: Callable[[], str],
    expected_snapshot: FeedLineageSnapshot,
    before_apply: Callable[[FeedAppendPlan], None] | None,
    after_apply: (
        Callable[
            [FeedAppendPlan, FeedLineageSnapshot, Callable[[], None]],
            None,
        ]
        | None
    ),
    trusted_root: Path,
    verify_lock_ownership: Callable[[], None],
    hot_integrity: _FeedHotIntegrity | None = None,
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
    if hot_integrity is None:
        before, pending_rotation = _verify_retained_snapshot(
            active_path,
            snapshot,
            feed_anchor=verified_anchor,
            base_path=base_path,
            trusted_root=trusted_root,
            expected_lineage_path=lineage_path,
            expected_segment_index=active_segment_index,
        )
    else:
        before = _verify_hot_integrity(
            base_path,
            snapshot,
            hot_integrity,
            game_pk=transition.state.game_pk,
            trusted_root=trusted_root,
        )
        pending_rotation = False
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
    if snapshot.event_count == 0:
        sealed_segments_sha256 = _sealed_segments_sha256(())
    else:
        retained_sealed_sha256 = snapshot.sealed_segments_sha256
        if retained_sealed_sha256 is None:
            _fatal("active snapshot lacks its sealed segment commitment")
        sealed_segments_sha256 = retained_sealed_sha256
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

    unrotated_event_bytes = build_event_bytes()
    if len(unrotated_event_bytes) > MAX_LINEAGE_EVENT_BYTES:
        _fatal("feed lineage event exceeds the byte limit")
    if len(unrotated_event_bytes) + 1 > MAX_ACTIVE_SEGMENT_BYTES:
        _fatal("feed lineage event exceeds the active segment byte limit")
    newly_sealed_receipts: tuple[FeedSegmentReceipt, ...] = ()
    newly_sealed_identities: tuple[FeedSealedIdentity, ...] = ()
    unpublished_receipt: FeedSegmentReceipt | None = None
    retained_active_path = active_path
    retained_lineage_path = lineage_path
    retained_segment_index = active_segment_index
    should_rotate = pending_rotation or (
        snapshot.event_count > 0
        and snapshot.file_size + len(unrotated_event_bytes) + 1
        > MAX_ACTIVE_SEGMENT_BYTES
    )
    if should_rotate:
        unpublished_receipt = _receipt_from_active_snapshot(
            snapshot,
            base_path=base_path,
            trusted_root=trusted_root,
            feed_anchor=verified_anchor,
        )
        sealed_segments = _append_history(
            snapshot.sealed_segments,
            unpublished_receipt,
        )
        _validate_appended_segment_receipt(
            unpublished_receipt,
            prior_receipt=(
                snapshot.sealed_segments[-1]
                if snapshot.sealed_segments
                else None
            ),
            base_path=base_path,
            trusted_root=trusted_root,
            feed_anchor=verified_anchor,
        )
        sealed_segments_sha256 = _extend_sealed_segments_sha256(
            sealed_segments_sha256,
            unpublished_receipt,
        )
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
        event_bytes = build_event_bytes()
        if len(event_bytes) > MAX_LINEAGE_EVENT_BYTES:
            _fatal("rotated feed lineage event exceeds the byte limit")
        if len(event_bytes) + 1 > MAX_ACTIVE_SEGMENT_BYTES:
            _fatal("rotated event exceeds the active segment byte limit")
    else:
        event_bytes = unrotated_event_bytes
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
    if hot_integrity is None:
        planned_file_sha256 = _planned_active_file_sha256(
            active_path,
            payload,
            before=None if should_rotate else before,
            snapshot=snapshot,
        )
    else:
        planned_hasher = (
            hashlib.sha256()
            if should_rotate
            else hot_integrity.active_hasher.copy()
        )
        planned_hasher.update(payload)
        planned_file_sha256 = planned_hasher.hexdigest()
    active_first_event_sequence = (
        snapshot.event_count + 1
        if should_rotate
        else snapshot.active_first_event_sequence
        if snapshot.event_count > 0
        else 1
    )
    active_first_prior_event_sha256 = (
        snapshot.last_event_sha256
        if should_rotate
        else snapshot.active_first_prior_event_sha256
        if snapshot.event_count > 0
        else None
    )
    active_first_event_sha256 = (
        validated_event_sha
        if should_rotate
        else snapshot.active_first_event_sha256
        if snapshot.event_count > 0
        else validated_event_sha
    )
    expected_post_head = FeedPortableHead(
        game_pk=transition.state.game_pk,
        event_count=snapshot.event_count + 1,
        last_event_sha256=validated_event_sha,
        transition_sequence=transition.state.transition_sequence,
        state_commitment_sha256=transition.state.state_commitment_sha256,
        game_heads_sha256=game_heads_sha256,
        base_lineage_path=base_lineage_path,
        active_lineage_path=lineage_path,
        active_segment_index=active_segment_index,
        active_file_size=(
            len(payload) if should_rotate else snapshot.file_size + len(payload)
        ),
        active_file_sha256=planned_file_sha256,
        active_first_event_sequence=active_first_event_sequence,
        active_first_prior_event_sha256=active_first_prior_event_sha256,
        active_first_event_sha256=active_first_event_sha256,
        sealed_segments_sha256=sealed_segments_sha256,
    )
    plan = FeedAppendPlan(
        game_pk=transition.state.game_pk,
        recorded_at=recorded,
        event_bytes=event_bytes,
        payload=payload,
        event_sha256=validated_event_sha,
        before_head=portable_head_from_snapshot(
            snapshot,
            game_pk=transition.state.game_pk,
        ),
        expected_post_head=expected_post_head,
        should_rotate=should_rotate,
        expected_new_sealed_receipt=unpublished_receipt,
    )
    if before_apply is not None:
        before_apply(plan)
        if hot_integrity is None:
            before, closing_pending_rotation = _verify_retained_snapshot(
                retained_active_path,
                snapshot,
                feed_anchor=verified_anchor,
                base_path=base_path,
                trusted_root=trusted_root,
                expected_lineage_path=retained_lineage_path,
                expected_segment_index=retained_segment_index,
            )
        else:
            before = _verify_hot_integrity(
                base_path,
                snapshot,
                hot_integrity,
                game_pk=transition.state.game_pk,
                trusted_root=trusted_root,
            )
            closing_pending_rotation = False
        if closing_pending_rotation != pending_rotation:
            _fatal("feed lineage rotation state changed during prepare custody")
        if should_rotate and os.path.lexists(active_path):
            _fatal("next feed lineage segment appeared during prepare custody")
    if should_rotate:
        assert unpublished_receipt is not None
        sealed_receipt, sealed_identity = _seal_active_segment(
            retained_active_path,
            snapshot,
            base_path=base_path,
            trusted_root=trusted_root,
            feed_anchor=verified_anchor,
            source_descriptor=(
                None if hot_integrity is None else hot_integrity.active_descriptor
            ),
        )
        if sealed_receipt != unpublished_receipt:
            _fatal("published receipt differs from its exact rotation plan")
        sealed_identities = _append_history(
            snapshot.sealed_identities,
            sealed_identity,
        )
        newly_sealed_receipts = (sealed_receipt,)
        newly_sealed_identities = (sealed_identity,)
        before = None
    _assert_trusted_lineage_paths(base_path, trusted_root=trusted_root)
    adopted_hasher: Any | None = None
    adopted_descriptor: int | None = None
    if hot_integrity is None:
        after, after_file_sha256 = _append_exact_payload(
            active_path,
            payload,
            before=before,
            snapshot=snapshot,
            verify_lock_ownership=verify_lock_ownership,
        )
    else:
        (
            after,
            after_file_sha256,
            adopted_hasher,
            adopted_descriptor,
        ) = _append_exact_payload_hot(
            active_path,
            payload,
            before=before,
            snapshot=snapshot,
            hot_integrity=hot_integrity,
            starts_new_segment=should_rotate,
            verify_lock_ownership=verify_lock_ownership,
        )
    _assert_trusted_lineage_paths(base_path, trusted_root=trusted_root)
    terminal = _read_bounded_terminal_event(active_path, file_size=after.st_size)
    if terminal != event_bytes:
        _fatal("feed lineage terminal event differs after append")
    if after.st_size != expected_post_head.active_file_size:
        _fatal("feed lineage appended size differs from the frozen plan")
    if after_file_sha256 != expected_post_head.active_file_sha256:
        _fatal("feed lineage appended hash differs from the frozen plan")
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
        active_first_event_sequence=active_first_event_sequence,
        active_first_prior_event_sha256=active_first_prior_event_sha256,
        active_first_event_sha256=active_first_event_sha256,
        sealed_segments=sealed_segments,
        sealed_segments_sha256=sealed_segments_sha256,
        sealed_identities=sealed_identities,
    )
    if portable_head_from_snapshot(
        candidate_snapshot,
        game_pk=transition.state.game_pk,
    ) != expected_post_head:
        _fatal("feed lineage portable post head differs from the frozen plan")
    if hot_integrity is not None:
        if adopted_hasher is None or adopted_descriptor is None:
            _fatal("feed hot integrity did not retain the appended writer state")
        prior_descriptor = hot_integrity.active_descriptor
        if should_rotate:
            if (
                prior_descriptor is None
                or prior_descriptor == adopted_descriptor
                or hot_integrity.active_path != retained_active_path
                or hot_integrity.pending_sealed_descriptors
                or len(newly_sealed_receipts) != 1
                or len(newly_sealed_identities) != 1
            ):
                os.close(adopted_descriptor)
                _fatal("feed hot rotation descriptor handoff differs")
            sealed_receipt = newly_sealed_receipts[0]
            sealed_identity = newly_sealed_identities[0]
            source_path = trusted_root / Path(sealed_receipt.lineage_path)
            archive_path = trusted_root / Path(sealed_receipt.archive_path)
            try:
                _require_hot_descriptor_identity(
                    prior_descriptor,
                    source_path,
                    device=sealed_identity.source_device,
                    inode=sealed_identity.source_inode,
                    size=sealed_receipt.file_size,
                    mtime_ns=sealed_identity.source_mtime_ns,
                )
                archive_descriptor = _open_hot_descriptor(
                    archive_path,
                    create_new=False,
                )
                try:
                    _require_hot_descriptor_identity(
                        archive_descriptor,
                        archive_path,
                        device=sealed_identity.archive_device,
                        inode=sealed_identity.archive_inode,
                        size=sealed_receipt.file_size,
                        mtime_ns=sealed_identity.archive_mtime_ns,
                    )
                except Exception:
                    os.close(archive_descriptor)
                    raise
            except Exception:
                os.close(adopted_descriptor)
                raise
            hot_integrity.pending_sealed_descriptors = (
                (source_path, prior_descriptor),
                (archive_path, archive_descriptor),
            )
        elif prior_descriptor is None and snapshot.event_count == 0:
            pass
        elif prior_descriptor != adopted_descriptor:
            os.close(adopted_descriptor)
            _fatal("feed hot append changed its active descriptor")
        hot_integrity.head = expected_post_head
        hot_integrity.active_hasher = adopted_hasher
        hot_integrity.active_descriptor = adopted_descriptor
        hot_integrity.active_path = active_path

    def reverify_candidate() -> None:
        if hot_integrity is None:
            _verify_retained_snapshot(
                active_path,
                candidate_snapshot,
                feed_anchor=verified_anchor,
                base_path=base_path,
                trusted_root=trusted_root,
                expected_lineage_path=lineage_path,
                expected_segment_index=active_segment_index,
            )
        else:
            _verify_hot_integrity(
                base_path,
                candidate_snapshot,
                hot_integrity,
                game_pk=transition.state.game_pk,
                trusted_root=trusted_root,
            )
        if newly_sealed_receipts:
            _verify_all_sealed_copies(
                newly_sealed_receipts,
                newly_sealed_identities,
                trusted_root=trusted_root,
                retained_descriptors=(
                    None
                    if hot_integrity is None
                    else dict(hot_integrity.pending_sealed_descriptors)
                ),
            )
            if hot_integrity is None:
                _verify_retained_snapshot(
                    active_path,
                    candidate_snapshot,
                    feed_anchor=verified_anchor,
                    base_path=base_path,
                    trusted_root=trusted_root,
                    expected_lineage_path=lineage_path,
                    expected_segment_index=active_segment_index,
                )
            else:
                _verify_hot_integrity(
                    base_path,
                    candidate_snapshot,
                    hot_integrity,
                    game_pk=transition.state.game_pk,
                    trusted_root=trusted_root,
                )

    reverify_candidate()
    if after_apply is not None:
        after_apply(plan, candidate_snapshot, reverify_candidate)
        reverify_candidate()
    return candidate_snapshot
