"""Coherent v34 feed-pair reads and content-addressed queue archives."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import time
from contextlib import suppress
from ctypes import wintypes
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, cast
from uuid import uuid4

from scripts.v34 import policy
from scripts.v34.decision_commit import ArchivedFeedPair

if TYPE_CHECKING:
    from collections.abc import Callable

QUEUE_RUN_SIGNATURE: Final = policy.QUEUE_RUN_SIGNATURE
QUEUE_SCHEMA_VERSION: Final = policy.QUEUE_SCHEMA_VERSION
QUEUE_OUTPUT_ROOT: Final = (
    policy.REPOSITORY_ROOT / Path(policy.QUEUE_OUTPUT_ROOT)
)
QUEUE_ARCHIVE_ROOT: Final = QUEUE_OUTPUT_ROOT / "feed-archive"
SNAPSHOT_ATTEMPTS: Final = 8
SNAPSHOT_RETRY_SECONDS: Final = 0.05
SNAPSHOT_MAX_SECONDS: Final = 1.0
OWNERSHIP_RETRY_ATTEMPTS: Final = 20
OWNERSHIP_RETRY_SECONDS: Final = 0.01
MAX_ARCHIVED_PAIR_BYTES: Final = 2 * 1024 * 1024
_SAFE_GENERATION = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_ARCHIVE_RECEIPT_KEYS: Final = set(policy.FEED_PROVENANCE_KEYS) | {
    "archive_path",
    "archived_at",
    "feed_receipt_sha256",
    "generation_id",
    "queue_provenance",
    "summary_sha256",
}
_NAME_SURROGATE_BIT: Final = 0x20000000
_REDIRECT_REPARSE_TAGS: Final = {0xA0000003, 0xA000000C, 0x8000001B}


class CoherentSnapshotUnavailableError(RuntimeError):
    """No exact stable feed pair became visible inside the frozen budget."""


class ArchiveCollisionError(RuntimeError):
    """A content-addressed archive path contained different bytes."""


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _parse_canonical_object(raw: bytes, *, field: str) -> dict[str, object]:
    if type(raw) is not bytes:
        raise TypeError(f"{field} must be immutable bytes")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{field} JSON is invalid") from exc
    if not isinstance(parsed, dict):
        raise TypeError(f"{field} must be an object")
    row = cast("dict[str, object]", parsed)
    if raw != policy.canonical_json_bytes(row):
        raise ValueError(f"{field} is not canonical JSON")
    return row


def _validate_generation(value: object) -> str:
    if type(value) is not str or not _SAFE_GENERATION.fullmatch(value):
        raise ValueError("feed generation ID is not a safe canonical path segment")
    if value in {".", ".."} or ".." in value:
        raise ValueError("feed generation ID contains a traversal token")
    return value


@dataclass(frozen=True, slots=True)
class CoherentFeedPair:
    """Exact stable bytes read from the feed's summary publication pair."""

    generation_id: str
    summary_bytes: bytes
    feed_receipt_bytes: bytes

    @property
    def summary_sha256(self) -> str:
        return _sha256(self.summary_bytes)

    @property
    def feed_receipt_sha256(self) -> str:
        return _sha256(self.feed_receipt_bytes)

    def validate(self, anchor: policy.FeedLaunchAnchor) -> None:
        verified_anchor = policy.reverify_feed_launch_anchor(anchor)
        generation_id = _validate_generation(self.generation_id)
        summary = _parse_canonical_object(self.summary_bytes, field="feed summary")
        receipt = _parse_canonical_object(self.feed_receipt_bytes, field="feed summary receipt")
        summary_provenance = policy.validate_feed_artifact_provenance(
            summary, anchor=verified_anchor, field="feed summary"
        )
        receipt_provenance = policy.validate_feed_artifact_provenance(
            receipt, anchor=verified_anchor, field="feed summary receipt"
        )
        if summary_provenance != receipt_provenance:
            raise ValueError("feed pair provenance differs")
        if summary.get("generation_id") != generation_id:
            raise ValueError("feed summary generation mismatch")
        if receipt.get("generation_id") != generation_id:
            raise ValueError("feed receipt generation mismatch")
        if receipt.get("summary_sha256") != self.summary_sha256:
            raise ValueError("feed receipt summary hash mismatch")


def _read_coherent_feed_pair(
    summary_path: Path,
    receipt_path: Path,
    *,
    anchor: policy.FeedLaunchAnchor,
    read_bytes: Callable[[Path], bytes],
    monotonic_ns: Callable[[], int],
    sleep: Callable[[float], None],
) -> CoherentFeedPair:
    verified_anchor = policy.reverify_feed_launch_anchor(anchor)
    start_ns = monotonic_ns()
    last_error: Exception | None = None
    for attempt in range(SNAPSHOT_ATTEMPTS):
        if (monotonic_ns() - start_ns) / 1_000_000_000 > SNAPSHOT_MAX_SECONDS:
            break
        try:
            receipt_before = read_bytes(receipt_path)
            summary_bytes = read_bytes(summary_path)
            receipt_after = read_bytes(receipt_path)
            if receipt_before != receipt_after:
                raise ValueError("feed receipt changed during coherent read")
            receipt = _parse_canonical_object(receipt_after, field="feed summary receipt")
            pair = CoherentFeedPair(
                generation_id=_validate_generation(receipt.get("generation_id")),
                summary_bytes=summary_bytes,
                feed_receipt_bytes=receipt_after,
            )
            pair.validate(verified_anchor)
            elapsed = (monotonic_ns() - start_ns) / 1_000_000_000
            if elapsed > SNAPSHOT_MAX_SECONDS:
                raise TimeoutError("coherent feed read exceeded one second")
            return pair
        except (OSError, TimeoutError, TypeError, ValueError) as exc:
            last_error = exc
        elapsed = (monotonic_ns() - start_ns) / 1_000_000_000
        if elapsed > SNAPSHOT_MAX_SECONDS or attempt + 1 == SNAPSHOT_ATTEMPTS:
            break
        sleep(SNAPSHOT_RETRY_SECONDS)
    raise CoherentSnapshotUnavailableError(
        "no coherent feed pair completed inside the frozen read budget"
    ) from last_error


def read_coherent_feed_pair(
    summary_path: Path,
    receipt_path: Path,
    *,
    anchor: policy.FeedLaunchAnchor,
) -> CoherentFeedPair:
    """Read the exact receipt-summary-receipt protocol under frozen limits."""

    return _read_coherent_feed_pair(
        summary_path,
        receipt_path,
        anchor=anchor,
        read_bytes=Path.read_bytes,
        monotonic_ns=time.monotonic_ns,
        sleep=time.sleep,
    )


def _lexical_absolute(path: Path) -> Path:
    return path.absolute()


def _assert_not_redirect(path: Path) -> None:
    if not os.path.lexists(path):
        return
    try:
        path_stat = os.lstat(path)
    except FileNotFoundError:
        return
    reparse_tag = getattr(path_stat, "st_reparse_tag", 0)
    is_junction = getattr(path, "is_junction", lambda: False)()
    if (
        path.is_symlink()
        or is_junction
        or reparse_tag in _REDIRECT_REPARSE_TAGS
        or bool(reparse_tag & _NAME_SURROGATE_BIT)
    ):
        raise ArchiveCollisionError(f"archive path redirects through a link: {path}")


def _assert_no_redirecting_components(base: Path, target: Path) -> None:
    base_absolute = _lexical_absolute(base)
    target_absolute = _lexical_absolute(target)
    try:
        relative = target_absolute.relative_to(base_absolute)
    except ValueError as exc:
        raise ArchiveCollisionError("archive path escapes its trusted root") from exc
    current = base_absolute
    _assert_not_redirect(current)
    for part in relative.parts:
        current /= part
        _assert_not_redirect(current)
        if os.path.lexists(current) and current != target_absolute and not current.is_dir():
            raise ArchiveCollisionError(f"archive ancestor is not a directory: {current}")
        # Windows directory mount points are name-surrogate reparse points and
        # are rejected above. Path.is_mount invokes a costly volume query there.
        if os.name != "nt" and current != base_absolute and current.is_mount():
            raise ArchiveCollisionError(f"archive path crosses a mounted directory: {current}")


def _fsync_directory(path: Path) -> None:
    if os.name != "nt":
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        return

    import ctypes

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
    kernel32.FlushFileBuffers.argtypes = [wintypes.HANDLE]
    kernel32.FlushFileBuffers.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    handle = kernel32.CreateFileW(
        str(path),
        0x40000000,
        0x00000001 | 0x00000002 | 0x00000004,
        None,
        3,
        0x02000000,
        None,
    )
    invalid_handle = ctypes.c_void_p(-1).value
    if handle == invalid_handle:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        if not kernel32.FlushFileBuffers(handle):
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        if not kernel32.CloseHandle(handle):
            raise ctypes.WinError(ctypes.get_last_error())


def _ensure_durable_directory(base: Path, target: Path) -> None:
    _assert_no_redirecting_components(base, target)
    base_absolute = _lexical_absolute(base)
    if not base_absolute.is_dir():
        raise ArchiveCollisionError("trusted archive root does not exist")
    current = base_absolute
    relative = _lexical_absolute(target).relative_to(base_absolute)
    for part in relative.parts:
        parent = current
        current /= part
        with suppress(FileExistsError):
            current.mkdir()
        _assert_not_redirect(current)
        if not current.is_dir():
            raise ArchiveCollisionError(f"archive path is not a directory: {current}")
        _fsync_directory(current)
        _fsync_directory(parent)
    _assert_no_redirecting_components(base, target)


def _stable_owned_file_bytes(path: Path) -> bytes:
    return _stable_owned_file_bytes_bounded(path, max_bytes=None)


def _stable_owned_file_bytes_bounded(
    path: Path,
    *,
    max_bytes: int | None,
    recover_internal_links: bool = True,
) -> bytes:
    if max_bytes is not None and (type(max_bytes) is not int or max_bytes < 0):
        raise ArchiveCollisionError("archive member read bound is invalid")
    before: os.stat_result | None = None
    for attempt in range(OWNERSHIP_RETRY_ATTEMPTS):
        internal_link_pending = (
            _recover_internal_temp_link(path) if recover_internal_links else False
        )
        _assert_not_redirect(path)
        try:
            candidate = path.stat(follow_symlinks=False)
        except FileNotFoundError as exc:
            raise ArchiveCollisionError(f"archive member is missing: {path}") from exc
        if not stat.S_ISREG(candidate.st_mode):
            raise ArchiveCollisionError(f"archive member is not a regular file: {path}")
        if candidate.st_nlink == 1:
            before = candidate
            break
        if not internal_link_pending and attempt + 1 >= 3:
            raise ArchiveCollisionError(f"archive member is not singly owned: {path}")
        if attempt + 1 < OWNERSHIP_RETRY_ATTEMPTS:
            time.sleep(OWNERSHIP_RETRY_SECONDS)
    if before is None:
        raise ArchiveCollisionError(f"archive member ownership did not stabilize: {path}")
    if max_bytes is not None and before.st_size > max_bytes:
        raise ArchiveCollisionError(f"archive member exceeds its read bound: {path}")
    with path.open("r+b") as handle:
        opened = os.fstat(handle.fileno())
        if any(
            getattr(before, field) != getattr(opened, field)
            for field in ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_nlink")
        ):
            raise ArchiveCollisionError(
                f"archive member changed before bounded read: {path}"
            )
        value = handle.read() if max_bytes is None else handle.read(max_bytes + 1)
        if max_bytes is not None and len(value) > max_bytes:
            raise ArchiveCollisionError(f"archive member exceeds its read bound: {path}")
        handle.flush()
        os.fsync(handle.fileno())
    after = path.stat(follow_symlinks=False)
    stable_fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_nlink")
    if any(getattr(before, field) != getattr(after, field) for field in stable_fields):
        raise ArchiveCollisionError(f"archive member changed during verification: {path}")
    if after.st_nlink != 1:
        raise ArchiveCollisionError(f"archive member gained another hard link: {path}")
    _fsync_directory(path.parent)
    return value


def _read_bounded_archive_members(directory: Path) -> tuple[bytes, bytes, bytes]:
    remaining = MAX_ARCHIVED_PAIR_BYTES
    values: list[bytes] = []
    for name in (
        "summary.json",
        "summary.receipt.json",
        "archive.receipt.json",
    ):
        value = _stable_owned_file_bytes_bounded(
            directory / name,
            max_bytes=remaining,
        )
        values.append(value)
        remaining -= len(value)
    return values[0], values[1], values[2]


def _recover_internal_temp_link(path: Path) -> bool:
    if not os.path.lexists(path):
        return False
    _assert_not_redirect(path)
    try:
        final_stat = path.stat(follow_symlinks=False)
    except FileNotFoundError:
        return False
    prefix = f".{path.name}.v34tmp-"
    internal_link_pending = False
    for candidate in path.parent.iterdir():
        if not candidate.name.startswith(prefix) or not candidate.name.endswith(".tmp"):
            continue
        _assert_not_redirect(candidate)
        try:
            candidate_stat = candidate.stat(follow_symlinks=False)
        except FileNotFoundError:
            continue
        if (
            candidate_stat.st_dev == final_stat.st_dev
            and candidate_stat.st_ino == final_stat.st_ino
        ):
            try:
                candidate.unlink()
            except FileNotFoundError:
                continue
            except PermissionError:
                internal_link_pending = True
                continue
            else:
                _fsync_directory(path.parent)
    return internal_link_pending


def _unlink_internal_temp_with_retries(path: Path) -> None:
    last_error: PermissionError | None = None
    for attempt in range(OWNERSHIP_RETRY_ATTEMPTS):
        try:
            path.unlink()
        except FileNotFoundError:
            return
        except PermissionError as exc:
            last_error = exc
            if attempt + 1 < OWNERSHIP_RETRY_ATTEMPTS:
                time.sleep(OWNERSHIP_RETRY_SECONDS)
        else:
            _fsync_directory(path.parent)
            return
    assert last_error is not None
    raise last_error


def _matching_internal_temps(path: Path) -> tuple[Path, ...]:
    prefix = f".{path.name}.v34tmp-"

    def exact_name(candidate: Path) -> bool:
        if not candidate.name.startswith(prefix) or not candidate.name.endswith(".tmp"):
            return False
        nonce = candidate.name[len(prefix) : -len(".tmp")]
        return re.fullmatch(r"[0-9a-f]{32}", nonce) is not None

    return tuple(
        sorted(
            (
                candidate
                for candidate in path.parent.iterdir()
                if exact_name(candidate)
            ),
            key=lambda candidate: candidate.name,
        )
    )


def _recover_prelink_internal_temps(path: Path, value: bytes) -> None:
    """Publish or remove only exact durable temps for one known final value."""

    candidates = _matching_internal_temps(path)
    if not candidates:
        return
    stable_candidates: list[Path] = []
    for candidate in candidates:
        _assert_not_redirect(candidate)
        try:
            candidate_value = _stable_owned_file_bytes_bounded(
                candidate,
                max_bytes=len(value),
            )
        except ArchiveCollisionError as exc:
            if not os.path.lexists(candidate):
                continue
            if os.path.lexists(path) and _stable_owned_file_bytes_bounded(
                path,
                max_bytes=len(value),
            ) == value:
                continue
            raise ArchiveCollisionError(
                f"archive pre-link temp collision at {candidate}"
            ) from exc
        if candidate_value != value:
            raise ArchiveCollisionError(
                f"archive pre-link temp collision at {candidate}"
            )
        stable_candidates.append(candidate)
    if not stable_candidates:
        return
    if not os.path.lexists(path):
        try:
            os.link(stable_candidates[0], path, follow_symlinks=False)
            _fsync_directory(path.parent)
        except FileExistsError:
            pass
    if _stable_owned_file_bytes_bounded(path, max_bytes=len(value)) != value:
        raise ArchiveCollisionError(f"archive pre-link recovery differs at {path}")
    final_stat = path.stat(follow_symlinks=False)
    for candidate in stable_candidates:
        try:
            candidate_stat = candidate.stat(follow_symlinks=False)
        except FileNotFoundError:
            continue
        if candidate_stat.st_nlink not in {1, 2}:
            raise ArchiveCollisionError(
                f"archive pre-link temp ownership differs at {candidate}"
            )
        if candidate_stat.st_nlink == 2 and (
            candidate_stat.st_dev != final_stat.st_dev
            or candidate_stat.st_ino != final_stat.st_ino
        ):
            raise ArchiveCollisionError(
                f"archive pre-link temp link differs at {candidate}"
            )
        _unlink_internal_temp_with_retries(candidate)
    _fsync_directory(path.parent)


def _write_create_once(path: Path, value: bytes) -> None:
    if type(value) is not bytes:
        raise TypeError("archive members must be immutable bytes")
    _recover_prelink_internal_temps(path, value)
    _recover_internal_temp_link(path)
    if os.path.lexists(path):
        if _stable_owned_file_bytes_bounded(path, max_bytes=len(value)) != value:
            raise ArchiveCollisionError(f"archive collision at {path}")
        return
    temp = path.parent / f".{path.name}.v34tmp-{uuid4().hex}.tmp"
    linked = False
    try:
        with temp.open("xb") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temp, path, follow_symlinks=False)
            linked = True
            _fsync_directory(path.parent)
        except FileExistsError:
            _recover_internal_temp_link(path)
            if _stable_owned_file_bytes_bounded(path, max_bytes=len(value)) != value:
                raise ArchiveCollisionError(f"archive collision at {path}") from None
    finally:
        if os.path.lexists(temp):
            _assert_not_redirect(temp)
            _unlink_internal_temp_with_retries(temp)
    if linked:
        _recover_internal_temp_link(path)
    if _stable_owned_file_bytes_bounded(path, max_bytes=len(value)) != value:
        raise ArchiveCollisionError(f"archive collision at {path}")


def _write_create_once_hot(path: Path, value: bytes) -> None:
    """Create one known fresh member without enumerating its growing parent."""

    if type(value) is not bytes:
        raise TypeError("archive members must be immutable bytes")
    if os.path.lexists(path):
        if (
            _stable_owned_file_bytes_bounded(
                path,
                max_bytes=len(value),
                recover_internal_links=False,
            )
            != value
        ):
            raise ArchiveCollisionError(f"archive collision at {path}")
        return
    temp = path.parent / f".{path.name}.v34tmp-{uuid4().hex}.tmp"
    linked = False
    try:
        with temp.open("xb") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temp, path, follow_symlinks=False)
            linked = True
            _fsync_directory(path.parent)
        except FileExistsError:
            if (
                _stable_owned_file_bytes_bounded(
                    path,
                    max_bytes=len(value),
                    recover_internal_links=False,
                )
                != value
            ):
                raise ArchiveCollisionError(f"archive collision at {path}") from None
    finally:
        if os.path.lexists(temp):
            _assert_not_redirect(temp)
            _unlink_internal_temp_with_retries(temp)
    if not linked and not os.path.lexists(path):
        raise ArchiveCollisionError(f"archive publication disappeared at {path}")
    if (
        _stable_owned_file_bytes_bounded(
            path,
            max_bytes=len(value),
            recover_internal_links=False,
        )
        != value
    ):
        raise ArchiveCollisionError(f"archive collision at {path}")


def _utc_now() -> str:
    return datetime.now(tz=UTC).isoformat()


def _validate_archive_receipt(
    raw: bytes,
    *,
    pair: CoherentFeedPair,
    directory: Path,
    feed_anchor: policy.FeedLaunchAnchor,
    queue_anchor: policy.QueueLaunchAnchor,
) -> None:
    receipt = _parse_canonical_object(raw, field="archive receipt")
    if set(receipt) != _ARCHIVE_RECEIPT_KEYS:
        raise ArchiveCollisionError("archive receipt fields differ from the frozen schema")
    policy.validate_feed_artifact_provenance(
        receipt,
        anchor=feed_anchor,
        field="archive receipt",
    )
    queue_provenance = receipt.get("queue_provenance")
    if not isinstance(queue_provenance, dict):
        raise ArchiveCollisionError("archive receipt queue provenance is missing")
    policy.validate_queue_artifact_provenance(
        queue_provenance,
        anchor=queue_anchor,
        field="archive receipt queue provenance",
    )
    expected = {
        "archive_path": str(directory.resolve()),
        "feed_receipt_sha256": pair.feed_receipt_sha256,
        "generation_id": pair.generation_id,
        "summary_sha256": pair.summary_sha256,
    }
    if any(receipt.get(key) != value for key, value in expected.items()):
        raise ArchiveCollisionError("archive receipt binding differs at content address")
    archived_at = receipt.get("archived_at")
    if type(archived_at) is not str:
        raise ArchiveCollisionError("archive receipt time is not a string")
    parsed_time = datetime.fromisoformat(archived_at.replace("Z", "+00:00"))
    if parsed_time.tzinfo is None:
        raise ArchiveCollisionError("archive receipt time is timezone-naive")
    if parsed_time.utcoffset() != timedelta(0):
        raise ArchiveCollisionError("archive receipt time is not UTC")


def archive_coherent_feed_pair(
    pair: CoherentFeedPair,
    *,
    feed_anchor: policy.FeedLaunchAnchor,
    queue_anchor: policy.QueueLaunchAnchor,
    recorded_at: Callable[[], str] = _utc_now,
) -> ArchivedFeedPair:
    """Archive one coherent pair before any public-market decision."""

    expected_root = policy.REPOSITORY_ROOT / Path(policy.QUEUE_OUTPUT_ROOT) / "feed-archive"
    if expected_root != QUEUE_ARCHIVE_ROOT:
        raise ArchiveCollisionError("queue archive root differs from the frozen path")
    return _archive_coherent_feed_pair_at_root(
        pair,
        feed_anchor=feed_anchor,
        queue_anchor=queue_anchor,
        archive_root=QUEUE_ARCHIVE_ROOT,
        trusted_root=policy.REPOSITORY_ROOT,
        recorded_at=recorded_at,
    )


def revalidate_archived_feed_pair(
    archived: ArchivedFeedPair,
    *,
    feed_anchor: policy.FeedLaunchAnchor,
    queue_anchor: policy.QueueLaunchAnchor,
    trusted_root: Path,
) -> ArchivedFeedPair:
    """Reopen every archive member and revalidate its exact on-disk binding."""

    if not isinstance(archived, ArchivedFeedPair):
        raise TypeError("archived source must be an ArchivedFeedPair")
    verified_feed_anchor = policy.reverify_feed_launch_anchor(feed_anchor)
    verified_queue_anchor = policy.reverify_queue_launch_anchor(queue_anchor)
    archived.validate(verified_feed_anchor, verified_queue_anchor)
    receipt = _parse_canonical_object(
        archived.archive_receipt_bytes,
        field="archive receipt",
    )
    archive_path = receipt.get("archive_path")
    if type(archive_path) is not str or not archive_path:
        raise ArchiveCollisionError("archive receipt path is missing")
    directory = Path(archive_path)
    _assert_no_redirecting_components(trusted_root, directory)
    if {entry.name for entry in directory.iterdir()} != {
        "archive.receipt.json",
        "summary.json",
        "summary.receipt.json",
    }:
        raise ArchiveCollisionError("archived source member inventory differs")
    pair = CoherentFeedPair(
        generation_id=archived.generation_id,
        summary_bytes=archived.summary_bytes,
        feed_receipt_bytes=archived.feed_receipt_bytes,
    )
    _validate_archive_receipt(
        archived.archive_receipt_bytes,
        pair=pair,
        directory=directory,
        feed_anchor=verified_feed_anchor,
        queue_anchor=verified_queue_anchor,
    )
    summary_bytes, feed_receipt_bytes, archive_receipt_bytes = (
        _read_bounded_archive_members(directory)
    )
    observed = ArchivedFeedPair(
        generation_id=archived.generation_id,
        summary_bytes=summary_bytes,
        feed_receipt_bytes=feed_receipt_bytes,
        archive_receipt_bytes=archive_receipt_bytes,
    )
    if observed != archived:
        raise ArchiveCollisionError("archived source differs from its on-disk members")
    observed.validate(verified_feed_anchor, verified_queue_anchor)
    _assert_no_redirecting_components(trusted_root, directory)
    return observed


def plan_archived_feed_pair(
    pair: CoherentFeedPair,
    *,
    feed_anchor: policy.FeedLaunchAnchor,
    queue_anchor: policy.QueueLaunchAnchor,
    archive_root: Path,
    trusted_root: Path,
    archived_at: str,
) -> ArchivedFeedPair:
    """Construct or read the exact archive bytes before any publication."""

    verified_feed_anchor = policy.reverify_feed_launch_anchor(feed_anchor)
    verified_queue_anchor = policy.reverify_queue_launch_anchor(queue_anchor)
    pair.validate(verified_feed_anchor)
    directory = archive_root / pair.generation_id / pair.summary_sha256
    _assert_no_redirecting_components(trusted_root, directory)
    archive_receipt_path = directory / "archive.receipt.json"
    if os.path.lexists(archive_receipt_path):
        summary_bytes, feed_receipt_bytes, archive_receipt_bytes = (
            _read_bounded_archive_members(directory)
        )
        observed = ArchivedFeedPair(
            generation_id=pair.generation_id,
            summary_bytes=summary_bytes,
            feed_receipt_bytes=feed_receipt_bytes,
            archive_receipt_bytes=archive_receipt_bytes,
        )
        _validate_archive_receipt(
            observed.archive_receipt_bytes,
            pair=pair,
            directory=directory,
            feed_anchor=verified_feed_anchor,
            queue_anchor=verified_queue_anchor,
        )
        if (
            observed.summary_bytes != pair.summary_bytes
            or observed.feed_receipt_bytes != pair.feed_receipt_bytes
        ):
            raise ArchiveCollisionError("existing archive differs from the planned pair")
        return revalidate_archived_feed_pair(
            observed,
            feed_anchor=verified_feed_anchor,
            queue_anchor=verified_queue_anchor,
            trusted_root=trusted_root,
        )
    if type(archived_at) is not str or len(archived_at.encode("utf-8")) > 64:
        raise TypeError("archive recorded_at must be a bounded string")
    parsed_time = datetime.fromisoformat(archived_at.replace("Z", "+00:00"))
    if parsed_time.tzinfo is None:
        raise ValueError("archive recorded_at must be timezone-aware")
    if parsed_time.utcoffset() != timedelta(0):
        raise ValueError("archive recorded_at must be UTC")
    planned = ArchivedFeedPair(
        generation_id=pair.generation_id,
        summary_bytes=pair.summary_bytes,
        feed_receipt_bytes=pair.feed_receipt_bytes,
        archive_receipt_bytes=policy.canonical_json_bytes(
            {
                **verified_feed_anchor.provenance,
                "archive_path": str(directory.resolve()),
                "archived_at": archived_at,
                "feed_receipt_sha256": pair.feed_receipt_sha256,
                "generation_id": pair.generation_id,
                "queue_provenance": verified_queue_anchor.provenance,
                "summary_sha256": pair.summary_sha256,
            }
        ),
    )
    planned.validate(verified_feed_anchor, verified_queue_anchor)
    if (
        len(planned.summary_bytes)
        + len(planned.feed_receipt_bytes)
        + len(planned.archive_receipt_bytes)
        > MAX_ARCHIVED_PAIR_BYTES
    ):
        raise ArchiveCollisionError("planned archive exceeds the aggregate byte cap")
    _validate_archive_receipt(
        planned.archive_receipt_bytes,
        pair=pair,
        directory=directory,
        feed_anchor=verified_feed_anchor,
        queue_anchor=verified_queue_anchor,
    )
    return planned


def _archive_coherent_feed_pair_at_root(
    pair: CoherentFeedPair,
    *,
    feed_anchor: policy.FeedLaunchAnchor,
    queue_anchor: policy.QueueLaunchAnchor,
    archive_root: Path,
    trusted_root: Path,
    recorded_at: Callable[[], str] = _utc_now,
    planned_archive: ArchivedFeedPair | None = None,
) -> ArchivedFeedPair:
    """Testable archive implementation with an explicit trusted root."""

    verified_feed_anchor = policy.reverify_feed_launch_anchor(feed_anchor)
    verified_queue_anchor = policy.reverify_queue_launch_anchor(queue_anchor)
    pair.validate(verified_feed_anchor)
    if planned_archive is None:
        planned_archive = plan_archived_feed_pair(
            pair,
            feed_anchor=verified_feed_anchor,
            queue_anchor=verified_queue_anchor,
            archive_root=archive_root,
            trusted_root=trusted_root,
            archived_at=recorded_at(),
        )
    elif (
        not isinstance(planned_archive, ArchivedFeedPair)
        or planned_archive.generation_id != pair.generation_id
        or planned_archive.summary_bytes != pair.summary_bytes
        or planned_archive.feed_receipt_bytes != pair.feed_receipt_bytes
    ):
        raise ArchiveCollisionError("planned archive differs from the feed pair")
    if (
        len(planned_archive.summary_bytes)
        + len(planned_archive.feed_receipt_bytes)
        + len(planned_archive.archive_receipt_bytes)
        > MAX_ARCHIVED_PAIR_BYTES
    ):
        raise ArchiveCollisionError("planned archive exceeds the aggregate byte cap")
    _ensure_durable_directory(trusted_root, archive_root)
    generation_directory = archive_root / pair.generation_id
    _ensure_durable_directory(trusted_root, generation_directory)
    directory = generation_directory / pair.summary_sha256
    _ensure_durable_directory(trusted_root, directory)
    _assert_no_redirecting_components(trusted_root, directory)
    summary_path = directory / "summary.json"
    feed_receipt_path = directory / "summary.receipt.json"
    archive_receipt_path = directory / "archive.receipt.json"
    _write_create_once(summary_path, pair.summary_bytes)
    _write_create_once(feed_receipt_path, pair.feed_receipt_bytes)

    if os.path.lexists(archive_receipt_path):
        archive_receipt_bytes = _stable_owned_file_bytes_bounded(
            archive_receipt_path,
            max_bytes=MAX_ARCHIVED_PAIR_BYTES,
        )
    else:
        try:
            _write_create_once(
                archive_receipt_path,
                planned_archive.archive_receipt_bytes,
            )
        except ArchiveCollisionError:
            archive_receipt_bytes = _stable_owned_file_bytes_bounded(
                archive_receipt_path,
                max_bytes=MAX_ARCHIVED_PAIR_BYTES,
            )
            _validate_archive_receipt(
                archive_receipt_bytes,
                pair=pair,
                directory=directory,
                feed_anchor=verified_feed_anchor,
                queue_anchor=verified_queue_anchor,
            )
        archive_receipt_bytes = _stable_owned_file_bytes_bounded(
            archive_receipt_path,
            max_bytes=MAX_ARCHIVED_PAIR_BYTES,
        )

    _validate_archive_receipt(
        archive_receipt_bytes,
        pair=pair,
        directory=directory,
        feed_anchor=verified_feed_anchor,
        queue_anchor=verified_queue_anchor,
    )
    validated_archive_receipt_bytes = archive_receipt_bytes

    summary_bytes, feed_receipt_bytes, archive_receipt_bytes = (
        _read_bounded_archive_members(directory)
    )
    if summary_bytes != pair.summary_bytes or feed_receipt_bytes != pair.feed_receipt_bytes:
        raise ArchiveCollisionError("archived feed bytes changed after create-once write")
    if archive_receipt_bytes != validated_archive_receipt_bytes:
        raise ArchiveCollisionError("archive receipt changed after schema validation")
    _validate_archive_receipt(
        archive_receipt_bytes,
        pair=pair,
        directory=directory,
        feed_anchor=verified_feed_anchor,
        queue_anchor=verified_queue_anchor,
    )
    _assert_no_redirecting_components(trusted_root, directory)
    _fsync_directory(directory)
    archived = ArchivedFeedPair(
        generation_id=pair.generation_id,
        summary_bytes=summary_bytes,
        feed_receipt_bytes=feed_receipt_bytes,
        archive_receipt_bytes=archive_receipt_bytes,
    )
    archived.validate(verified_feed_anchor, verified_queue_anchor)
    return archived
