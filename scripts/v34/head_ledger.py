"""Custody-first immutable registry and head transactions for v34 feeds.

Kill criterion: no observer credit or capital is allowed if custody is not a
verified independent failure domain, the two control roots disagree, a game is
registered twice, or an open PREPARE cannot reconcile to exactly its prior or
planned portable head.
"""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import re
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Final, Literal, Never, cast

from scripts.v34 import feed_archive, feed_lineage, policy
from scripts.v34 import feed_lifecycle as lifecycle

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Mapping
    from typing import Any

SCHEMA_VERSION: Final = 1
GAME_PK_WIDTH: Final = 10
TRANSACTION_SEQUENCE_WIDTH: Final = 12
MAX_LEDGER_RECORD_BYTES: Final = 20 * 1024 * 1024
REGISTRY_MANIFEST_KEYS: Final = {
    "created_at",
    "custody_root",
    "custody_class",
    "custody_volume",
    "feed_launch_manifest_sha256",
    "kind",
    "lineage_layout",
    "policy_sha256",
    "queue_launch_manifest_sha256",
    "runtime_root",
    "runtime_volume",
    "run_signature",
    "schema_version",
}
REGISTRATION_KEYS: Final = {
    "feed_launch_manifest_sha256",
    "game_pk",
    "initial_head",
    "kind",
    "lineage_relative_path",
    "registered_at",
    "registry_manifest_sha256",
    "schema_version",
}
PREPARE_KEYS: Final = {
    "expected_new_sealed_receipt",
    "expected_post_head",
    "feed_launch_manifest_sha256",
    "game_pk",
    "game_registration_sha256",
    "kind",
    "planned_lineage_event",
    "planned_lineage_event_sha256",
    "planned_payload_sha256",
    "planned_rotation",
    "prior_commit_sha256",
    "prior_head",
    "registry_manifest_sha256",
    "schema_version",
    "source_archive_path",
    "source_archive_receipt_sha256",
    "source_feed_receipt_sha256",
    "source_feed_summary_sha256",
    "source_generation_id",
    "transaction_sequence",
}
COMMIT_KEYS: Final = {
    "committed_head",
    "feed_launch_manifest_sha256",
    "game_pk",
    "game_registration_sha256",
    "kind",
    "planned_lineage_event_sha256",
    "prepare_sha256",
    "prior_commit_sha256",
    "registry_manifest_sha256",
    "schema_version",
    "transaction_sequence",
}
PORTABLE_HEAD_KEYS: Final = {
    "active_file_sha256",
    "active_file_size",
    "active_first_event_sequence",
    "active_first_event_sha256",
    "active_first_prior_event_sha256",
    "active_lineage_path",
    "active_segment_index",
    "base_lineage_path",
    "event_count",
    "game_heads_sha256",
    "game_pk",
    "last_event_sha256",
    "sealed_segments_sha256",
    "state_commitment_sha256",
    "transition_sequence",
}
_REGISTRATION_NAME = re.compile(r"^(\d{10})-([0-9a-f]{64})\.json$")
_TRANSACTION_NAME = re.compile(r"^(\d{12})-([0-9a-f]{64})$")
_COMMIT_NAME = re.compile(r"^commit-([0-9a-f]{64})\.json$")
_INTERNAL_TEMP_NAME = re.compile(
    r"^\.(?P<final>.+)\.v34tmp-[0-9a-f]{32}\.tmp$"
)


class HeadLedgerFatalError(RuntimeError):
    """Registry, custody, transaction, or recovery truth is not exact."""


def _fatal(message: str, *, cause: Exception | None = None) -> Never:
    error = HeadLedgerFatalError(message)
    if cause is None:
        raise error
    raise error from cause


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _exact_int(value: object, *, field: str, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        _fatal(f"{field} must be an exact integer at least {minimum}")
    return value


def _utc(value: object, *, field: str) -> str:
    if type(value) is not str:
        _fatal(f"{field} must be a string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        _fatal(f"{field} is not ISO-8601", cause=exc)
    if parsed.tzinfo is None:
        _fatal(f"{field} is timezone-naive")
    return value


def _digest(value: object, *, field: str, optional: bool = False) -> str | None:
    if optional and value is None:
        return None
    try:
        return policy.validate_sha256(value, field=field)
    except (TypeError, ValueError) as exc:
        _fatal(f"{field} is not lowercase SHA256", cause=exc)


def _canonical_object(raw: bytes, *, field: str) -> dict[str, object]:
    if type(raw) is not bytes or len(raw) > MAX_LEDGER_RECORD_BYTES:
        _fatal(f"{field} exceeds the ledger record byte limit")
    try:
        parsed = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        _fatal(f"{field} is not JSON", cause=exc)
    if not isinstance(parsed, dict) or raw != policy.canonical_json_bytes(parsed):
        _fatal(f"{field} is not a canonical JSON object")
    return cast("dict[str, object]", parsed)


def canonical_game_component(game_pk: int) -> str:
    game_pk = _exact_int(game_pk, field="game_pk", minimum=1)
    if game_pk >= 10**GAME_PK_WIDTH:
        _fatal("game_pk exceeds the canonical path width")
    return f"{game_pk:0{GAME_PK_WIDTH}d}"


def canonical_lineage_relative_path(game_pk: int) -> str:
    return f"games/{canonical_game_component(game_pk)}/feed.jsonl"


@dataclass(frozen=True, slots=True)
class VolumeBinding:
    filesystem: str
    volume_root: str
    volume_serial: int
    physical_disk_numbers: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class HeadLedgerConfig:
    runtime_root: Path
    custody_root: Path
    feed_anchor: policy.FeedLaunchAnchor
    queue_anchor: policy.QueueLaunchAnchor
    created_at: str
    custody_class: Literal["logical_read_only", "independent_device"]
    manifest_runtime_root: Path | None = None
    manifest_runtime_binding: VolumeBinding | None = None

    @property
    def primary_control_root(self) -> Path:
        return self.runtime_root / "control"

    @property
    def custody_control_root(self) -> Path:
        return self.custody_root / "control"

    @property
    def capital_eligible(self) -> bool:
        """This in-process writer never proves independent capital custody."""

        return False


@dataclass(frozen=True, slots=True)
class GameRegistration:
    game_pk: int
    record_sha256: str
    lineage_relative_path: str
    initial_head: feed_lineage.FeedPortableHead


@dataclass(frozen=True, slots=True)
class OpenPrepare:
    record_sha256: str
    raw: bytes
    record: dict[str, object]
    plan: feed_lineage.FeedAppendPlan
    transition: lifecycle.FeedTransition


@dataclass(frozen=True, slots=True)
class GameLedgerState:
    registration: GameRegistration
    head: feed_lineage.FeedPortableHead
    prior_commit_sha256: str | None
    open_prepare: OpenPrepare | None


@dataclass(frozen=True, slots=True)
class CommittedFeedTransition:
    snapshot: feed_lineage.FeedLineageSnapshot
    prepare_sha256: str
    commit_sha256: str
    capital_eligible: bool


def _windows_volume_binding(path: Path) -> VolumeBinding:
    from ctypes import wintypes

    kernel32 = cast("Any", ctypes.WinDLL("kernel32", use_last_error=True))
    volume_path = ctypes.create_unicode_buffer(1024)
    get_volume_path = kernel32.GetVolumePathNameW
    get_volume_path.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD]
    get_volume_path.restype = wintypes.BOOL
    if not get_volume_path(str(path), volume_path, len(volume_path)):
        raise ctypes.WinError(ctypes.get_last_error())
    volume_name = ctypes.create_unicode_buffer(1024)
    get_volume_name = kernel32.GetVolumeNameForVolumeMountPointW
    get_volume_name.argtypes = [
        wintypes.LPCWSTR,
        wintypes.LPWSTR,
        wintypes.DWORD,
    ]
    get_volume_name.restype = wintypes.BOOL
    if not get_volume_name(volume_path.value, volume_name, len(volume_name)):
        raise ctypes.WinError(ctypes.get_last_error())
    filesystem = ctypes.create_unicode_buffer(64)
    serial = wintypes.DWORD()
    maximum_component = wintypes.DWORD()
    flags = wintypes.DWORD()
    get_volume_information = kernel32.GetVolumeInformationW
    get_volume_information.argtypes = [
        wintypes.LPCWSTR,
        wintypes.LPWSTR,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
        ctypes.POINTER(wintypes.DWORD),
        ctypes.POINTER(wintypes.DWORD),
        wintypes.LPWSTR,
        wintypes.DWORD,
    ]
    get_volume_information.restype = wintypes.BOOL
    if not get_volume_information(
        volume_path.value,
        None,
        0,
        ctypes.byref(serial),
        ctypes.byref(maximum_component),
        ctypes.byref(flags),
        filesystem,
        len(filesystem),
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    drive = volume_path.value.rstrip("\\")
    if len(drive) != 2 or drive[1] != ":":
        _fatal("ledger roots must be on a local drive volume")
    create_file = kernel32.CreateFileW
    create_file.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    create_file.restype = wintypes.HANDLE
    handle = create_file(
        f"\\\\.\\{drive}",
        0,
        0x00000001 | 0x00000002,
        None,
        3,
        0,
        None,
    )
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    buffer = ctypes.create_string_buffer(4096)
    returned = wintypes.DWORD()
    device_io = kernel32.DeviceIoControl
    device_io.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
        wintypes.LPVOID,
    ]
    device_io.restype = wintypes.BOOL
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = [wintypes.HANDLE]
    close_handle.restype = wintypes.BOOL
    try:
        if not device_io(
            handle,
            0x00560000,
            None,
            0,
            buffer,
            len(buffer),
            ctypes.byref(returned),
            None,
        ):
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        if not close_handle(handle):
            raise ctypes.WinError(ctypes.get_last_error())

    class DiskExtent(ctypes.Structure):
        _fields_ = [
            ("disk_number", wintypes.DWORD),
            ("starting_offset", ctypes.c_longlong),
            ("extent_length", ctypes.c_longlong),
        ]

    class VolumeDiskExtents(ctypes.Structure):
        _fields_ = [
            ("number_of_disk_extents", wintypes.DWORD),
            ("disk_extents", DiskExtent * 1),
        ]

    count = ctypes.cast(buffer, ctypes.POINTER(wintypes.DWORD)).contents.value
    if count < 1 or count > 128:
        _fatal("volume returned an invalid physical disk extent count")
    offset = VolumeDiskExtents.disk_extents.offset
    extent_size = ctypes.sizeof(DiskExtent)
    if offset + count * extent_size > returned.value:
        _fatal("volume disk extents response is truncated")
    disk_numbers = tuple(
        sorted(
            {
                DiskExtent.from_buffer_copy(
                    buffer.raw[offset + index * extent_size :]
                ).disk_number
                for index in range(count)
            }
        )
    )
    return VolumeBinding(
        filesystem=filesystem.value,
        volume_root=volume_name.value,
        volume_serial=serial.value,
        physical_disk_numbers=disk_numbers,
    )


def volume_binding(path: Path) -> VolumeBinding:
    if not isinstance(path, Path) or not path.is_dir():
        _fatal("volume binding requires an existing directory")
    if os.name == "nt":
        try:
            return _windows_volume_binding(path)
        except OSError as exc:
            _fatal("Windows volume binding failed", cause=exc)
    return VolumeBinding(
        filesystem="unknown",
        volume_root=path.anchor,
        volume_serial=path.stat().st_dev,
        physical_disk_numbers=(path.stat().st_dev,),
    )


def _absolute(path: Path) -> Path:
    return path.absolute()


def _is_within(path: Path, ancestor: Path) -> bool:
    try:
        _absolute(path).relative_to(_absolute(ancestor))
    except ValueError:
        return False
    return True


def _assert_root_ancestry(path: Path, *, allow_sync_root: bool) -> None:
    if not isinstance(path, Path) or not path.is_dir():
        _fatal("ledger root must be an existing directory")
    current = Path(path.anchor)
    try:
        feed_archive._assert_not_redirect(current)
        for part in _absolute(path).parts[1:]:
            current /= part
            feed_archive._assert_not_redirect(current)
    except (OSError, feed_archive.ArchiveCollisionError) as exc:
        _fatal("ledger root ancestry redirects through a reparse point", cause=exc)
    if not allow_sync_root and any(
        "onedrive" in part.casefold() or "dropbox" in part.casefold()
        for part in _absolute(path).parts
    ):
        _fatal("active runtime root is inside a sync directory")


def validate_config(config: HeadLedgerConfig) -> tuple[VolumeBinding, VolumeBinding]:
    if not isinstance(config, HeadLedgerConfig):
        _fatal("head ledger config has the wrong type")
    verified_anchor = policy.reverify_feed_launch_anchor(config.feed_anchor)
    if verified_anchor != config.feed_anchor:
        _fatal("head ledger feed anchor differs after reverification")
    verified_queue_anchor = policy.reverify_queue_launch_anchor(config.queue_anchor)
    if verified_queue_anchor != config.queue_anchor:
        _fatal("head ledger queue anchor differs after reverification")
    _utc(config.created_at, field="ledger.created_at")
    if config.custody_class not in {"logical_read_only", "independent_device"}:
        _fatal("head ledger custody class is invalid")
    if (config.manifest_runtime_root is None) != (
        config.manifest_runtime_binding is None
    ):
        _fatal("restored config manifest runtime identity is incomplete")
    if config.manifest_runtime_root is not None and (
        not isinstance(config.manifest_runtime_root, Path)
        or not isinstance(config.manifest_runtime_binding, VolumeBinding)
    ):
        _fatal("restored config manifest runtime identity has the wrong type")
    _assert_root_ancestry(config.runtime_root, allow_sync_root=False)
    _assert_root_ancestry(
        config.custody_root,
        allow_sync_root=config.custody_class == "logical_read_only",
    )
    if (
        _is_within(config.runtime_root, config.custody_root)
        or _is_within(config.custody_root, config.runtime_root)
    ):
        _fatal("runtime and custody roots overlap")
    runtime_binding = volume_binding(config.runtime_root)
    custody_binding = volume_binding(config.custody_root)
    if os.name == "nt" and runtime_binding.filesystem.casefold() != "ntfs":
        _fatal("active runtime root is not NTFS")
    if os.name == "nt" and custody_binding.filesystem.casefold() != "ntfs":
        _fatal("custody root is not NTFS")
    if config.custody_class == "independent_device" and set(
        runtime_binding.physical_disk_numbers
    ) & set(custody_binding.physical_disk_numbers):
        _fatal("custody does not use a disjoint physical disk")
    return runtime_binding, custody_binding


def _manifest_bytes(config: HeadLedgerConfig) -> bytes:
    runtime_binding, custody_binding = validate_config(config)
    manifest_runtime_root = config.manifest_runtime_root or config.runtime_root
    manifest_runtime_binding = config.manifest_runtime_binding or runtime_binding

    def binding_value(binding: VolumeBinding) -> dict[str, object]:
        return {
            "filesystem": binding.filesystem,
            "physical_disk_numbers": list(binding.physical_disk_numbers),
            "volume_root": binding.volume_root,
            "volume_serial": binding.volume_serial,
        }

    return policy.canonical_json_bytes(
        {
            "created_at": _utc(config.created_at, field="ledger.created_at"),
            "custody_class": config.custody_class,
            "custody_root": str(_absolute(config.custody_root)),
            "custody_volume": binding_value(custody_binding),
            "feed_launch_manifest_sha256": config.feed_anchor.manifest_sha256,
            "kind": "v34_head_registry_manifest",
            "lineage_layout": "games/{game_pk_10d}/feed.jsonl",
            "policy_sha256": policy.POLICY_CANONICAL_SHA256,
            "queue_launch_manifest_sha256": config.queue_anchor.manifest_sha256,
            "runtime_root": str(_absolute(manifest_runtime_root)),
            "runtime_volume": binding_value(manifest_runtime_binding),
            "run_signature": policy.FEED_RUN_SIGNATURE,
            "schema_version": SCHEMA_VERSION,
        }
    )


def registry_manifest_sha256(config: HeadLedgerConfig) -> str:
    validate_config(config)
    return _sha256(_manifest_bytes(config))


def _ensure_control_layout(config: HeadLedgerConfig) -> None:
    validate_config(config)
    for root in (config.custody_control_root, config.primary_control_root):
        trusted = config.custody_root if root == config.custody_control_root else config.runtime_root
        try:
            feed_archive._ensure_durable_directory(trusted, root)
            feed_archive._ensure_durable_directory(trusted, root / "registry")
            feed_archive._ensure_durable_directory(trusted, root / "registry" / "games")
            feed_archive._ensure_durable_directory(
                trusted,
                root / "registry" / "restores",
            )
            feed_archive._ensure_durable_directory(trusted, root / "transactions")
        except (OSError, ValueError, feed_archive.ArchiveCollisionError) as exc:
            _fatal("head ledger control layout is not durable", cause=exc)
    try:
        feed_archive._ensure_durable_directory(
            config.runtime_root,
            config.runtime_root / "games",
        )
    except (OSError, ValueError, feed_archive.ArchiveCollisionError) as exc:
        _fatal("head ledger runtime game root is not durable", cause=exc)


@contextmanager
def _control_locks(config: HeadLedgerConfig) -> Iterator[None]:
    _ensure_control_layout(config)
    custody_guard = config.custody_control_root / "ledger.guard"
    primary_guard = config.primary_control_root / "ledger.guard"
    with feed_lineage._exclusive_append_lock(
        custody_guard,
        trusted_root=config.custody_root,
    ), feed_lineage._exclusive_append_lock(
        primary_guard,
        trusted_root=config.runtime_root,
    ):
        yield


def _manifest_path(control_root: Path, manifest_sha256: str) -> Path:
    return control_root / "registry" / f"manifest-{manifest_sha256}.json"


def _write_exact(path: Path, raw: bytes) -> None:
    try:
        feed_archive._write_create_once(path, raw)
    except (OSError, ValueError, feed_archive.ArchiveCollisionError) as exc:
        _fatal(f"immutable ledger publication failed at {path.name}", cause=exc)


def _read_exact(path: Path) -> bytes:
    try:
        raw = feed_archive._stable_owned_file_bytes(path)
    except (OSError, ValueError, feed_archive.ArchiveCollisionError) as exc:
        _fatal(f"immutable ledger record is not stable at {path.name}", cause=exc)
    if len(raw) > MAX_LEDGER_RECORD_BYTES:
        _fatal("immutable ledger record exceeds the byte limit")
    return raw


def _recover_directory_prelink_temps(
    directory: Path,
    *,
    validate: Callable[[str, bytes], None],
) -> None:
    """Recover only exact content-addressed records while control locks are held."""

    for item in sorted(directory.iterdir(), key=lambda candidate: candidate.name):
        match = _INTERNAL_TEMP_NAME.fullmatch(item.name)
        if match is None:
            continue
        final_name = match.group("final")
        final_path = directory / final_name
        if os.path.lexists(final_path):
            feed_archive._recover_internal_temp_link(final_path)
            raw = _read_exact(final_path)
        else:
            raw = _read_exact(item)
        validate(final_name, raw)
        _write_exact(final_path, raw)


def _verify_manifest_locked(config: HeadLedgerConfig) -> str:
    raw = _manifest_bytes(config)
    digest = _sha256(raw)
    custody_path = _manifest_path(config.custody_control_root, digest)
    primary_path = _manifest_path(config.primary_control_root, digest)
    custody_registry = config.custody_control_root / "registry"
    primary_registry = config.primary_control_root / "registry"

    def validate_manifest_temp(final_name: str, candidate: bytes) -> None:
        if final_name != custody_path.name or candidate != raw:
            _fatal("registry manifest temp differs from the expected manifest")

    _recover_directory_prelink_temps(
        custody_registry,
        validate=validate_manifest_temp,
    )

    def validate_primary_manifest_temp(final_name: str, candidate: bytes) -> None:
        validate_manifest_temp(final_name, candidate)
        if not custody_path.is_file() or _read_exact(custody_path) != candidate:
            _fatal("primary registry manifest temp has no custody authority")

    _recover_directory_prelink_temps(
        primary_registry,
        validate=validate_primary_manifest_temp,
    )
    custody_all = _directory_names(custody_registry)
    primary_all = _directory_names(primary_registry)
    custody_inventory = custody_all - {"games", "restores"}
    primary_inventory = primary_all - {"games", "restores"}
    if not (custody_registry / "games").is_dir() or not (
        primary_registry / "games"
    ).is_dir():
        _fatal("registry game inventory directory is missing")
    if not (custody_registry / "restores").is_dir() or not (
        primary_registry / "restores"
    ).is_dir():
        _fatal("registry restore inventory directory is missing")
    if any(not name.startswith("manifest-") for name in custody_inventory):
        _fatal("custody registry inventory contains an unknown entry")
    if any(not name.startswith("manifest-") for name in primary_inventory):
        _fatal("primary registry inventory contains an unknown entry")
    expected = {custody_path.name}
    if custody_inventory - expected or primary_inventory - expected:
        _fatal("registry contains an alternate manifest")
    custody_exists = os.path.lexists(custody_path)
    primary_exists = os.path.lexists(primary_path)
    if primary_exists and not custody_exists:
        _fatal("primary registry manifest exists without custody authority")
    if not custody_exists:
        custody_history = bool(
            _directory_names(custody_registry / "games")
            or _directory_names(custody_registry / "restores")
            or _directory_names(config.custody_control_root / "transactions")
            or (
                (config.custody_control_root / "batches").exists()
                and _directory_names(config.custody_control_root / "batches")
            )
        )
        primary_history = bool(
            _directory_names(primary_registry / "games")
            or _directory_names(primary_registry / "restores")
            or _directory_names(config.primary_control_root / "transactions")
            or (
                (config.primary_control_root / "batches").exists()
                and _directory_names(config.primary_control_root / "batches")
            )
        )
        if custody_history or primary_history:
            _fatal("registry manifest is missing while ledger history exists")
        _write_exact(custody_path, raw)
    elif _read_exact(custody_path) != raw:
        _fatal("custody registry manifest differs from the expected manifest")
    if not primary_exists:
        _write_exact(primary_path, raw)
    if _read_exact(custody_path) != raw or _read_exact(primary_path) != raw:
        _fatal("registry manifest differs across custody roots")
    parsed = _canonical_object(raw, field="registry manifest")
    if set(parsed) != REGISTRY_MANIFEST_KEYS:
        _fatal("registry manifest keys differ")
    return digest


def initialize_head_ledger(config: HeadLedgerConfig) -> str:
    """Create and verify the immutable launch registry manifest."""

    with _control_locks(config):
        return _verify_manifest_locked(config)


def _receipt_from_dict(value: object) -> feed_lineage.FeedSegmentReceipt:
    if not isinstance(value, dict) or set(value) != feed_lineage.SEGMENT_RECEIPT_KEYS:
        _fatal("portable head sealed segment keys differ")
    receipt = feed_lineage.FeedSegmentReceipt(
        base_lineage_path=cast("str", value.get("base_lineage_path")),
        lineage_path=cast("str", value.get("lineage_path")),
        archive_path=cast("str", value.get("archive_path")),
        segment_index=_exact_int(
            value.get("segment_index"), field="segment.segment_index", minimum=1
        ),
        first_event_sequence=_exact_int(
            value.get("first_event_sequence"),
            field="segment.first_event_sequence",
            minimum=1,
        ),
        last_event_sequence=_exact_int(
            value.get("last_event_sequence"),
            field="segment.last_event_sequence",
            minimum=1,
        ),
        event_count=_exact_int(
            value.get("event_count"), field="segment.event_count", minimum=1
        ),
        first_prior_event_sha256=_digest(
            value.get("first_prior_event_sha256"),
            field="segment.first_prior_event_sha256",
            optional=True,
        ),
        first_event_sha256=cast(
            "str", _digest(value.get("first_event_sha256"), field="segment.first_event_sha256")
        ),
        last_event_sha256=cast(
            "str", _digest(value.get("last_event_sha256"), field="segment.last_event_sha256")
        ),
        file_size=_exact_int(value.get("file_size"), field="segment.file_size", minimum=1),
        file_sha256=cast(
            "str", _digest(value.get("file_sha256"), field="segment.file_sha256")
        ),
        launch_manifest_sha256=cast(
            "str",
            _digest(
                value.get("launch_manifest_sha256"),
                field="segment.launch_manifest_sha256",
            ),
        ),
    )
    if receipt.to_dict() != value:
        _fatal("portable head sealed segment values differ")
    return receipt


def _head_from_dict(value: object, *, expected_game_pk: int) -> feed_lineage.FeedPortableHead:
    if not isinstance(value, dict) or set(value) != PORTABLE_HEAD_KEYS:
        _fatal("portable head keys differ")
    game_pk = _exact_int(value.get("game_pk"), field="head.game_pk", minimum=1)
    if game_pk != expected_game_pk:
        _fatal("portable head game binding differs")
    count = _exact_int(value.get("event_count"), field="head.event_count")
    transition_sequence = _exact_int(
        value.get("transition_sequence"), field="head.transition_sequence"
    )
    active_segment_index = _exact_int(
        value.get("active_segment_index"), field="head.active_segment_index"
    )
    active_file_size = _exact_int(
        value.get("active_file_size"), field="head.active_file_size"
    )
    def optional_string(field: str) -> str | None:
        candidate = value.get(field)
        if candidate is not None and type(candidate) is not str:
            _fatal(f"head.{field} must be a string or null")
        return candidate

    head = feed_lineage.FeedPortableHead(
        game_pk=game_pk,
        event_count=count,
        last_event_sha256=_digest(
            value.get("last_event_sha256"), field="head.last_event_sha256", optional=True
        ),
        transition_sequence=transition_sequence,
        state_commitment_sha256=_digest(
            value.get("state_commitment_sha256"),
            field="head.state_commitment_sha256",
            optional=True,
        ),
        game_heads_sha256=_digest(
            value.get("game_heads_sha256"), field="head.game_heads_sha256", optional=True
        ),
        base_lineage_path=optional_string("base_lineage_path"),
        active_lineage_path=optional_string("active_lineage_path"),
        active_segment_index=active_segment_index,
        active_file_size=active_file_size,
        active_file_sha256=_digest(
            value.get("active_file_sha256"), field="head.active_file_sha256", optional=True
        ),
        active_first_event_sequence=(
            None
            if value.get("active_first_event_sequence") is None
            else _exact_int(
                value.get("active_first_event_sequence"),
                field="head.active_first_event_sequence",
                minimum=1,
            )
        ),
        active_first_prior_event_sha256=_digest(
            value.get("active_first_prior_event_sha256"),
            field="head.active_first_prior_event_sha256",
            optional=True,
        ),
        active_first_event_sha256=_digest(
            value.get("active_first_event_sha256"),
            field="head.active_first_event_sha256",
            optional=True,
        ),
        sealed_segments_sha256=_digest(
            value.get("sealed_segments_sha256"),
            field="head.sealed_segments_sha256",
            optional=True,
        ),
    )
    if head.to_dict() != value:
        _fatal("portable head values are not canonical")
    if count == 0:
        expected = feed_lineage.portable_head_from_snapshot(
            feed_lineage.FeedLineageSnapshot(
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
            ),
            game_pk=game_pk,
        )
        if head != expected:
            _fatal("empty portable head fields differ")
    elif (
        transition_sequence < 1
        or active_segment_index < 1
        or active_file_size < 1
        or head.last_event_sha256 is None
        or head.state_commitment_sha256 is None
        or head.game_heads_sha256 is None
        or head.base_lineage_path != canonical_lineage_relative_path(game_pk)
        or head.active_lineage_path is None
        or head.active_file_sha256 is None
        or head.active_first_event_sequence is None
        or head.active_first_event_sha256 is None
        or head.sealed_segments_sha256 is None
    ):
        _fatal("nonempty portable head fields differ")
    return head


def _registration_directory(control_root: Path) -> Path:
    return control_root / "registry" / "games"


def _registration_record(
    config: HeadLedgerConfig,
    *,
    game_pk: int,
    registered_at: str,
    manifest_sha256: str,
) -> bytes:
    empty_snapshot = feed_lineage.FeedLineageSnapshot(
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
    initial_head = feed_lineage.portable_head_from_snapshot(
        empty_snapshot,
        game_pk=game_pk,
    )
    return policy.canonical_json_bytes(
        {
            "feed_launch_manifest_sha256": config.feed_anchor.manifest_sha256,
            "game_pk": game_pk,
            "initial_head": initial_head.to_dict(),
            "kind": "v34_game_registration",
            "lineage_relative_path": canonical_lineage_relative_path(game_pk),
            "registered_at": _utc(registered_at, field="registered_at"),
            "registry_manifest_sha256": manifest_sha256,
            "schema_version": SCHEMA_VERSION,
        }
    )


def _parse_registration(
    raw: bytes,
    *,
    filename: str,
    config: HeadLedgerConfig,
    manifest_sha256: str,
) -> GameRegistration:
    parsed = _canonical_object(raw, field="game registration")
    if set(parsed) != REGISTRATION_KEYS:
        _fatal("game registration keys differ")
    if (
        parsed.get("kind") != "v34_game_registration"
        or parsed.get("schema_version") != SCHEMA_VERSION
        or parsed.get("feed_launch_manifest_sha256")
        != config.feed_anchor.manifest_sha256
        or parsed.get("registry_manifest_sha256") != manifest_sha256
    ):
        _fatal("game registration provenance differs")
    game_pk = _exact_int(parsed.get("game_pk"), field="registration.game_pk", minimum=1)
    _utc(parsed.get("registered_at"), field="registration.registered_at")
    relative_path = parsed.get("lineage_relative_path")
    if relative_path != canonical_lineage_relative_path(game_pk):
        _fatal("game registration lineage path is not canonical")
    digest = _sha256(raw)
    expected_name = f"{canonical_game_component(game_pk)}-{digest}.json"
    if filename != expected_name:
        _fatal("game registration filename differs from its content")
    initial_head = _head_from_dict(
        parsed.get("initial_head"),
        expected_game_pk=game_pk,
    )
    if initial_head.event_count != 0:
        _fatal("game registration initial head is not empty")
    return GameRegistration(
        game_pk=game_pk,
        record_sha256=digest,
        lineage_relative_path=relative_path,
        initial_head=initial_head,
    )


def _directory_names(path: Path) -> set[str]:
    try:
        return {item.name for item in path.iterdir()}
    except OSError as exc:
        _fatal(f"ledger directory inventory failed at {path.name}", cause=exc)


def _scan_registrations_locked(
    config: HeadLedgerConfig,
    *,
    manifest_sha256: str,
) -> dict[int, GameRegistration]:
    custody_directory = _registration_directory(config.custody_control_root)
    primary_directory = _registration_directory(config.primary_control_root)

    def validate_custody_temp(final_name: str, raw: bytes) -> None:
        _parse_registration(
            raw,
            filename=final_name,
            config=config,
            manifest_sha256=manifest_sha256,
        )

    _recover_directory_prelink_temps(
        custody_directory,
        validate=validate_custody_temp,
    )

    def validate_primary_temp(final_name: str, raw: bytes) -> None:
        validate_custody_temp(final_name, raw)
        custody_path = custody_directory / final_name
        if not custody_path.is_file() or _read_exact(custody_path) != raw:
            _fatal("primary registration temp has no custody authority")

    _recover_directory_prelink_temps(
        primary_directory,
        validate=validate_primary_temp,
    )
    custody_names = _directory_names(custody_directory)
    primary_names = _directory_names(primary_directory)
    if any(_REGISTRATION_NAME.fullmatch(name) is None for name in custody_names):
        _fatal("custody registration inventory contains an unknown entry")
    if any(_REGISTRATION_NAME.fullmatch(name) is None for name in primary_names):
        _fatal("primary registration inventory contains an unknown entry")
    if primary_names - custody_names:
        _fatal("primary registration exists without custody authority")
    for missing_name in sorted(custody_names - primary_names):
        raw = _read_exact(custody_directory / missing_name)
        _parse_registration(
            raw,
            filename=missing_name,
            config=config,
            manifest_sha256=manifest_sha256,
        )
        _write_exact(primary_directory / missing_name, raw)
    if _directory_names(primary_directory) != custody_names:
        _fatal("registration mirror recovery did not converge")
    registrations: dict[int, GameRegistration] = {}
    paths: set[str] = set()
    for name in sorted(custody_names):
        custody_raw = _read_exact(custody_directory / name)
        primary_raw = _read_exact(primary_directory / name)
        if custody_raw != primary_raw:
            _fatal("game registration differs across custody roots")
        registration = _parse_registration(
            custody_raw,
            filename=name,
            config=config,
            manifest_sha256=manifest_sha256,
        )
        if registration.game_pk in registrations:
            _fatal("game registry contains a duplicate game_pk")
        if registration.lineage_relative_path in paths:
            _fatal("game registry contains a duplicate lineage path")
        registrations[registration.game_pk] = registration
        paths.add(registration.lineage_relative_path)
    return registrations


def register_game(
    config: HeadLedgerConfig,
    *,
    game_pk: int,
    registered_at: str,
) -> GameRegistration:
    """Durably bind one game to one deterministic path before baseline."""

    game_pk = _exact_int(game_pk, field="game_pk", minimum=1)
    with _control_locks(config):
        manifest_sha256 = _verify_manifest_locked(config)
        registrations = _scan_registrations_locked(
            config,
            manifest_sha256=manifest_sha256,
        )
        existing = registrations.get(game_pk)
        if existing is not None:
            runtime_game_directory = (
                config.runtime_root / existing.lineage_relative_path
            ).parent
            if runtime_game_directory.exists() and not runtime_game_directory.is_dir():
                _fatal("registered runtime game path is not a directory")
            if not runtime_game_directory.exists():
                try:
                    feed_archive._ensure_durable_directory(
                        config.runtime_root,
                        runtime_game_directory,
                    )
                except (
                    OSError,
                    ValueError,
                    feed_archive.ArchiveCollisionError,
                ) as exc:
                    _fatal(
                        "registered runtime game directory recovery failed",
                        cause=exc,
                    )
            return existing
        for control_root in (
            config.custody_control_root,
            config.primary_control_root,
        ):
            batches = control_root / "batches"
            if batches.exists() and _directory_names(batches):
                _fatal("game registry is frozen after the first batch PREPARE")
            transactions = control_root / "transactions"
            for game_directory_name in _directory_names(transactions):
                game_directory = transactions / game_directory_name
                if not game_directory.is_dir() or _directory_names(game_directory):
                    _fatal("game registry is frozen after the first transaction")
        relative_path = canonical_lineage_relative_path(game_pk)
        runtime_game_directory = (config.runtime_root / relative_path).parent
        if os.path.lexists(runtime_game_directory):
            _fatal("unregistered game already has a runtime directory")
        raw = _registration_record(
            config,
            game_pk=game_pk,
            registered_at=registered_at,
            manifest_sha256=manifest_sha256,
        )
        digest = _sha256(raw)
        filename = f"{canonical_game_component(game_pk)}-{digest}.json"
        custody_path = _registration_directory(config.custody_control_root) / filename
        primary_path = _registration_directory(config.primary_control_root) / filename
        _write_exact(custody_path, raw)
        _write_exact(primary_path, raw)
        if _read_exact(custody_path) != _read_exact(primary_path):
            _fatal("new game registration differs across custody roots")
        try:
            feed_archive._ensure_durable_directory(
                config.runtime_root,
                runtime_game_directory,
            )
        except (OSError, ValueError, feed_archive.ArchiveCollisionError) as exc:
            _fatal("registered runtime game directory is not durable", cause=exc)
        refreshed = _scan_registrations_locked(
            config,
            manifest_sha256=manifest_sha256,
        )
        if set(refreshed) != {*registrations, game_pk}:
            _fatal("game registry changed during registration")
        return refreshed[game_pk]


def _transaction_game_directory(control_root: Path, game_pk: int) -> Path:
    return control_root / "transactions" / canonical_game_component(game_pk)


def _ensure_transaction_directories(config: HeadLedgerConfig, game_pk: int) -> None:
    for root in (config.custody_control_root, config.primary_control_root):
        trusted = config.custody_root if root == config.custody_control_root else config.runtime_root
        try:
            feed_archive._ensure_durable_directory(
                trusted,
                _transaction_game_directory(root, game_pk),
            )
        except (OSError, ValueError, feed_archive.ArchiveCollisionError) as exc:
            _fatal("game transaction directory is not durable", cause=exc)


def _verify_transaction_game_inventory(
    config: HeadLedgerConfig,
    registrations: Mapping[int, GameRegistration],
) -> None:
    allowed = {canonical_game_component(game_pk) for game_pk in registrations}
    custody_names = _directory_names(config.custody_control_root / "transactions")
    primary_names = _directory_names(config.primary_control_root / "transactions")
    if custody_names - allowed or primary_names - allowed:
        _fatal("transaction inventory contains an unregistered game")
    if primary_names - custody_names:
        _fatal("primary transaction game exists without custody authority")
    for name in sorted(custody_names - primary_names):
        try:
            feed_archive._ensure_durable_directory(
                config.runtime_root,
                config.primary_control_root / "transactions" / name,
            )
        except (OSError, ValueError, feed_archive.ArchiveCollisionError) as exc:
            _fatal("transaction game mirror recovery failed", cause=exc)
    primary_names = _directory_names(config.primary_control_root / "transactions")
    for name in custody_names | primary_names:
        if not (
            (config.custody_control_root / "transactions" / name).is_dir()
            and (config.primary_control_root / "transactions" / name).is_dir()
        ):
            _fatal("transaction game inventory differs across custody roots")


def _prepare_record(
    config: HeadLedgerConfig,
    *,
    manifest_sha256: str,
    registration: GameRegistration,
    plan: feed_lineage.FeedAppendPlan,
    prior_commit_sha256: str | None,
    source_archive_path: str,
    source_archive_receipt_sha256: str,
    source_feed_receipt_sha256: str,
    source_feed_summary_sha256: str,
    source_generation_id: str,
) -> bytes:
    _digest(
        source_archive_receipt_sha256,
        field="source_archive_receipt_sha256",
    )
    _digest(source_feed_receipt_sha256, field="source_feed_receipt_sha256")
    _digest(source_feed_summary_sha256, field="source_feed_summary_sha256")
    if (
        type(source_archive_path) is not str
        or not Path(source_archive_path).is_absolute()
    ):
        _fatal("source archive path must be absolute")
    if type(source_generation_id) is not str or not source_generation_id:
        _fatal("source generation ID is empty")
    event = _canonical_object(plan.event_bytes, field="planned lineage event")
    return policy.canonical_json_bytes(
        {
            "expected_new_sealed_receipt": (
                None
                if plan.expected_new_sealed_receipt is None
                else plan.expected_new_sealed_receipt.to_dict()
            ),
            "expected_post_head": plan.expected_post_head.to_dict(),
            "feed_launch_manifest_sha256": config.feed_anchor.manifest_sha256,
            "game_pk": plan.game_pk,
            "game_registration_sha256": registration.record_sha256,
            "kind": "v34_head_prepare",
            "planned_lineage_event": event,
            "planned_lineage_event_sha256": plan.event_sha256,
            "planned_payload_sha256": _sha256(plan.payload),
            "planned_rotation": plan.should_rotate,
            "prior_commit_sha256": prior_commit_sha256,
            "prior_head": plan.before_head.to_dict(),
            "registry_manifest_sha256": manifest_sha256,
            "schema_version": SCHEMA_VERSION,
            "source_archive_path": source_archive_path,
            "source_archive_receipt_sha256": source_archive_receipt_sha256,
            "source_feed_receipt_sha256": source_feed_receipt_sha256,
            "source_feed_summary_sha256": source_feed_summary_sha256,
            "source_generation_id": source_generation_id,
            "transaction_sequence": plan.expected_post_head.event_count,
        }
    )


def _parse_prepare(
    raw: bytes,
    *,
    config: HeadLedgerConfig,
    manifest_sha256: str,
    registration: GameRegistration,
) -> OpenPrepare:
    parsed = _canonical_object(raw, field="head PREPARE")
    if set(parsed) != PREPARE_KEYS:
        _fatal("head PREPARE keys differ")
    if (
        parsed.get("kind") != "v34_head_prepare"
        or parsed.get("schema_version") != SCHEMA_VERSION
        or parsed.get("registry_manifest_sha256") != manifest_sha256
        or parsed.get("game_registration_sha256") != registration.record_sha256
        or parsed.get("feed_launch_manifest_sha256")
        != config.feed_anchor.manifest_sha256
    ):
        _fatal("head PREPARE provenance differs")
    game_pk = _exact_int(parsed.get("game_pk"), field="prepare.game_pk", minimum=1)
    if game_pk != registration.game_pk:
        _fatal("head PREPARE game binding differs")
    sequence = _exact_int(
        parsed.get("transaction_sequence"),
        field="prepare.transaction_sequence",
        minimum=1,
    )
    before_head = _head_from_dict(parsed.get("prior_head"), expected_game_pk=game_pk)
    post_head = _head_from_dict(
        parsed.get("expected_post_head"),
        expected_game_pk=game_pk,
    )
    if post_head.event_count != sequence or before_head.event_count + 1 != sequence:
        _fatal("head PREPARE sequence does not extend its prior head")
    prior_commit = _digest(
        parsed.get("prior_commit_sha256"),
        field="prepare.prior_commit_sha256",
        optional=True,
    )
    _digest(
        parsed.get("source_archive_receipt_sha256"),
        field="prepare.source_archive_receipt_sha256",
    )
    _digest(
        parsed.get("source_feed_receipt_sha256"),
        field="prepare.source_feed_receipt_sha256",
    )
    _digest(
        parsed.get("source_feed_summary_sha256"),
        field="prepare.source_feed_summary_sha256",
    )
    source_archive_path = parsed.get("source_archive_path")
    if (
        type(source_archive_path) is not str
        or not Path(source_archive_path).is_absolute()
    ):
        _fatal("head PREPARE source archive path is invalid")
    source_generation_id = parsed.get("source_generation_id")
    if type(source_generation_id) is not str or not source_generation_id:
        _fatal("head PREPARE source generation ID is invalid")
    event_value = parsed.get("planned_lineage_event")
    if not isinstance(event_value, dict):
        _fatal("head PREPARE planned event is not an object")
    event_bytes = policy.canonical_json_bytes(event_value)
    event_sha256 = _sha256(event_bytes)
    if event_sha256 != parsed.get("planned_lineage_event_sha256"):
        _fatal("head PREPARE planned event hash differs")
    payload = event_bytes + b"\n"
    if _sha256(payload) != parsed.get("planned_payload_sha256"):
        _fatal("head PREPARE planned payload hash differs")
    state_value = event_value.get("state")
    lifecycle_values = event_value.get("lifecycle_events")
    if not isinstance(state_value, dict) or not isinstance(lifecycle_values, list):
        _fatal("head PREPARE event state or lifecycle events differ")
    state = feed_lineage.deserialize_game_state(
        policy.canonical_json_bytes(state_value)
    )
    event_parts: list[bytes] = []
    for item in lifecycle_values:
        if not isinstance(item, dict):
            _fatal("head PREPARE lifecycle event is not an object")
        event_parts.append(policy.canonical_json_bytes(item))
    transition = lifecycle.FeedTransition(state=state, event_bytes=tuple(event_parts))
    rotation = parsed.get("planned_rotation")
    if type(rotation) is not bool:
        _fatal("head PREPARE rotation flag is not boolean")
    receipt_value = parsed.get("expected_new_sealed_receipt")
    receipt = None if receipt_value is None else _receipt_from_dict(receipt_value)
    if rotation != (receipt is not None):
        _fatal("head PREPARE rotation receipt differs from its flag")
    recorded_at = event_value.get("recorded_at")
    plan = feed_lineage.FeedAppendPlan(
        game_pk=game_pk,
        recorded_at=_utc(recorded_at, field="prepare.event.recorded_at"),
        event_bytes=event_bytes,
        payload=payload,
        event_sha256=event_sha256,
        before_head=before_head,
        expected_post_head=post_head,
        should_rotate=rotation,
        expected_new_sealed_receipt=receipt,
    )
    if transition.state.game_pk != game_pk:
        _fatal("head PREPARE state game binding differs")
    if event_value.get("event_sequence") != sequence:
        _fatal("head PREPARE event sequence differs")
    if event_value.get("game_pk") != game_pk:
        _fatal("head PREPARE event game differs")
    if parsed.get("prior_commit_sha256") != prior_commit:
        _fatal("head PREPARE prior commit is not canonical")
    return OpenPrepare(
        record_sha256=_sha256(raw),
        raw=raw,
        record=parsed,
        plan=plan,
        transition=transition,
    )


def _commit_record(
    config: HeadLedgerConfig,
    *,
    manifest_sha256: str,
    registration: GameRegistration,
    prepare: OpenPrepare,
) -> bytes:
    prior_commit = prepare.record.get("prior_commit_sha256")
    return policy.canonical_json_bytes(
        {
            "committed_head": prepare.plan.expected_post_head.to_dict(),
            "feed_launch_manifest_sha256": config.feed_anchor.manifest_sha256,
            "game_pk": registration.game_pk,
            "game_registration_sha256": registration.record_sha256,
            "kind": "v34_head_commit",
            "planned_lineage_event_sha256": prepare.plan.event_sha256,
            "prepare_sha256": prepare.record_sha256,
            "prior_commit_sha256": prior_commit,
            "registry_manifest_sha256": manifest_sha256,
            "schema_version": SCHEMA_VERSION,
            "transaction_sequence": prepare.plan.expected_post_head.event_count,
        }
    )


def _parse_commit(
    raw: bytes,
    *,
    config: HeadLedgerConfig,
    manifest_sha256: str,
    registration: GameRegistration,
    prepare: OpenPrepare,
) -> tuple[str, feed_lineage.FeedPortableHead]:
    parsed = _canonical_object(raw, field="head COMMIT")
    if set(parsed) != COMMIT_KEYS:
        _fatal("head COMMIT keys differ")
    if (
        parsed.get("kind") != "v34_head_commit"
        or parsed.get("schema_version") != SCHEMA_VERSION
        or parsed.get("registry_manifest_sha256") != manifest_sha256
        or parsed.get("game_registration_sha256") != registration.record_sha256
        or parsed.get("feed_launch_manifest_sha256")
        != config.feed_anchor.manifest_sha256
        or parsed.get("game_pk") != registration.game_pk
        or parsed.get("transaction_sequence")
        != prepare.plan.expected_post_head.event_count
        or parsed.get("prepare_sha256") != prepare.record_sha256
        or parsed.get("prior_commit_sha256")
        != prepare.record.get("prior_commit_sha256")
        or parsed.get("planned_lineage_event_sha256") != prepare.plan.event_sha256
    ):
        _fatal("head COMMIT provenance or chain differs")
    committed = _head_from_dict(
        parsed.get("committed_head"),
        expected_game_pk=registration.game_pk,
    )
    if committed != prepare.plan.expected_post_head:
        _fatal("head COMMIT differs from the prepared post head")
    return _sha256(raw), committed


def _transaction_directory(
    control_root: Path,
    *,
    game_pk: int,
    sequence: int,
    prepare_sha256: str,
) -> Path:
    return _transaction_game_directory(control_root, game_pk) / (
        f"{sequence:0{TRANSACTION_SEQUENCE_WIDTH}d}-{prepare_sha256}"
    )


def _mirror_transaction_directory_locked(
    config: HeadLedgerConfig,
    *,
    name: str,
    game_pk: int,
) -> None:
    custody = _transaction_game_directory(config.custody_control_root, game_pk) / name
    primary = _transaction_game_directory(config.primary_control_root, game_pk) / name
    if not custody.is_dir():
        _fatal("custody transaction entry is not a directory")
    if not primary.exists():
        try:
            feed_archive._ensure_durable_directory(config.runtime_root, primary)
        except (OSError, ValueError, feed_archive.ArchiveCollisionError) as exc:
            _fatal("transaction directory mirror recovery failed", cause=exc)
    if not primary.is_dir():
        _fatal("primary transaction entry is not a directory")
    transaction_match = _TRANSACTION_NAME.fullmatch(name)
    if transaction_match is None:
        _fatal("transaction directory name is not canonical")
    expected_prepare_sha256 = transaction_match.group(2)

    def validate_custody_temp(final_name: str, raw: bytes) -> None:
        parsed = _canonical_object(raw, field="transaction publication temp")
        if final_name == "prepare.json":
            if (
                _sha256(raw) != expected_prepare_sha256
                or parsed.get("kind") != "v34_head_prepare"
            ):
                _fatal("transaction PREPARE temp differs from its directory")
            return
        commit_match = _COMMIT_NAME.fullmatch(final_name)
        if (
            commit_match is None
            or _sha256(raw) != commit_match.group(1)
            or parsed.get("kind") != "v34_head_commit"
        ):
            _fatal("transaction COMMIT temp differs from its filename")

    _recover_directory_prelink_temps(custody, validate=validate_custody_temp)

    def validate_primary_temp(final_name: str, raw: bytes) -> None:
        validate_custody_temp(final_name, raw)
        custody_path = custody / final_name
        if not custody_path.is_file() or _read_exact(custody_path) != raw:
            _fatal("primary transaction temp has no custody authority")

    _recover_directory_prelink_temps(primary, validate=validate_primary_temp)
    custody_files = _directory_names(custody)
    primary_files = _directory_names(primary)
    valid_custody = {"prepare.json"}
    commits = {item for item in custody_files if _COMMIT_NAME.fullmatch(item)}
    if len(commits) > 1 or custody_files != valid_custody | commits:
        _fatal("custody transaction file inventory differs")
    if primary_files - custody_files:
        _fatal("primary transaction record exists without custody authority")
    for missing in sorted(custody_files - primary_files):
        _write_exact(primary / missing, _read_exact(custody / missing))
    if _directory_names(primary) != custody_files:
        _fatal("transaction record mirror recovery did not converge")
    for filename in custody_files:
        if _read_exact(custody / filename) != _read_exact(primary / filename):
            _fatal("transaction record differs across custody roots")


def _remove_empty_transaction_container(path: Path, *, trusted_root: Path) -> None:
    try:
        feed_archive._assert_no_redirecting_components(trusted_root, path)
        if not path.is_dir() or any(path.iterdir()):
            _fatal("unpublished transaction container is not exactly empty")
        path.rmdir()
        feed_archive._fsync_directory(path.parent)
    except (OSError, ValueError, feed_archive.ArchiveCollisionError) as exc:
        _fatal("empty transaction container recovery failed", cause=exc)


def _scan_game_ledger_locked(
    config: HeadLedgerConfig,
    *,
    manifest_sha256: str,
    registration: GameRegistration,
) -> GameLedgerState:
    custody_game = _transaction_game_directory(
        config.custody_control_root,
        registration.game_pk,
    )
    primary_game = _transaction_game_directory(
        config.primary_control_root,
        registration.game_pk,
    )
    if not custody_game.exists() and not primary_game.exists():
        return GameLedgerState(
            registration=registration,
            head=registration.initial_head,
            prior_commit_sha256=None,
            open_prepare=None,
        )
    if primary_game.exists() and not custody_game.exists():
        _fatal("primary transaction chain exists without custody authority")
    _ensure_transaction_directories(config, registration.game_pk)
    custody_names = _directory_names(custody_game)
    primary_names = _directory_names(primary_game)
    if any(_TRANSACTION_NAME.fullmatch(name) is None for name in custody_names):
        _fatal("custody transaction inventory contains an unknown entry")
    if any(_TRANSACTION_NAME.fullmatch(name) is None for name in primary_names):
        _fatal("primary transaction inventory contains an unknown entry")
    for name in sorted(custody_names | primary_names):
        custody_path = custody_game / name
        primary_path = primary_game / name
        custody_empty = custody_path.is_dir() and not any(custody_path.iterdir())
        primary_empty = primary_path.is_dir() and not any(primary_path.iterdir())
        if not custody_path.exists() and primary_empty:
            _fatal("primary empty transaction exists without custody authority")
        if custody_empty and (not primary_path.exists() or primary_empty):
            if primary_empty:
                _remove_empty_transaction_container(
                    primary_path,
                    trusted_root=config.runtime_root,
                )
            _remove_empty_transaction_container(
                custody_path,
                trusted_root=config.custody_root,
            )
    custody_names = _directory_names(custody_game)
    primary_names = _directory_names(primary_game)
    if primary_names - custody_names:
        _fatal("primary transaction exists without custody authority")
    for name in sorted(custody_names - primary_names):
        _mirror_transaction_directory_locked(
            config,
            name=name,
            game_pk=registration.game_pk,
        )
    if _directory_names(primary_game) != custody_names:
        _fatal("transaction directory mirrors did not converge")
    current_head = registration.initial_head
    prior_commit_sha256: str | None = None
    open_prepare: OpenPrepare | None = None
    expected_sequence = 1
    ordered_names = sorted(custody_names)
    for position, name in enumerate(ordered_names):
        match = _TRANSACTION_NAME.fullmatch(name)
        assert match is not None
        sequence = int(match.group(1))
        name_prepare_sha256 = match.group(2)
        if sequence != expected_sequence:
            _fatal("head transaction sequence has a gap or duplicate")
        _mirror_transaction_directory_locked(
            config,
            name=name,
            game_pk=registration.game_pk,
        )
        custody_transaction = custody_game / name
        prepare_raw = _read_exact(custody_transaction / "prepare.json")
        if _sha256(prepare_raw) != name_prepare_sha256:
            _fatal("head PREPARE directory hash differs")
        prepare = _parse_prepare(
            prepare_raw,
            config=config,
            manifest_sha256=manifest_sha256,
            registration=registration,
        )
        if prepare.plan.expected_post_head.event_count != sequence:
            _fatal("head PREPARE directory sequence differs")
        if prepare.plan.before_head != current_head:
            _fatal("head PREPARE prior portable head differs from the chain")
        if prepare.record.get("prior_commit_sha256") != prior_commit_sha256:
            _fatal("head PREPARE prior commit differs from the chain")
        files = _directory_names(custody_transaction)
        commit_names = sorted(item for item in files if _COMMIT_NAME.fullmatch(item))
        if not commit_names:
            if position != len(ordered_names) - 1 or open_prepare is not None:
                _fatal("an incomplete PREPARE is not the sole chain tail")
            open_prepare = prepare
        else:
            commit_name = commit_names[0]
            commit_match = _COMMIT_NAME.fullmatch(commit_name)
            assert commit_match is not None
            commit_raw = _read_exact(custody_transaction / commit_name)
            commit_sha256, current_head = _parse_commit(
                commit_raw,
                config=config,
                manifest_sha256=manifest_sha256,
                registration=registration,
                prepare=prepare,
            )
            if commit_sha256 != commit_match.group(1):
                _fatal("head COMMIT filename hash differs")
            prior_commit_sha256 = commit_sha256
        expected_sequence += 1
    return GameLedgerState(
        registration=registration,
        head=current_head,
        prior_commit_sha256=prior_commit_sha256,
        open_prepare=open_prepare,
    )


def _publish_prepare_locked(
    config: HeadLedgerConfig,
    *,
    manifest_sha256: str,
    registration: GameRegistration,
    raw: bytes,
) -> OpenPrepare:
    prepare = _parse_prepare(
        raw,
        config=config,
        manifest_sha256=manifest_sha256,
        registration=registration,
    )
    sequence = prepare.plan.expected_post_head.event_count
    _ensure_transaction_directories(config, registration.game_pk)
    custody_directory = _transaction_directory(
        config.custody_control_root,
        game_pk=registration.game_pk,
        sequence=sequence,
        prepare_sha256=prepare.record_sha256,
    )
    primary_directory = _transaction_directory(
        config.primary_control_root,
        game_pk=registration.game_pk,
        sequence=sequence,
        prepare_sha256=prepare.record_sha256,
    )
    try:
        feed_archive._ensure_durable_directory(config.custody_root, custody_directory)
        feed_archive._ensure_durable_directory(config.runtime_root, primary_directory)
    except (OSError, ValueError, feed_archive.ArchiveCollisionError) as exc:
        _fatal("head PREPARE transaction directory is not durable", cause=exc)
    custody_path = custody_directory / "prepare.json"
    primary_path = primary_directory / "prepare.json"
    _write_exact(custody_path, raw)
    _write_exact(primary_path, raw)
    if _read_exact(custody_path) != raw or _read_exact(primary_path) != raw:
        _fatal("head PREPARE differs across custody roots")
    return prepare


def _publish_commit_locked(
    config: HeadLedgerConfig,
    *,
    manifest_sha256: str,
    registration: GameRegistration,
    prepare: OpenPrepare,
) -> tuple[str, bytes]:
    raw = _commit_record(
        config,
        manifest_sha256=manifest_sha256,
        registration=registration,
        prepare=prepare,
    )
    digest = _sha256(raw)
    sequence = prepare.plan.expected_post_head.event_count
    custody_directory = _transaction_directory(
        config.custody_control_root,
        game_pk=registration.game_pk,
        sequence=sequence,
        prepare_sha256=prepare.record_sha256,
    )
    primary_directory = _transaction_directory(
        config.primary_control_root,
        game_pk=registration.game_pk,
        sequence=sequence,
        prepare_sha256=prepare.record_sha256,
    )
    filename = f"commit-{digest}.json"
    custody_path = custody_directory / filename
    primary_path = primary_directory / filename
    _write_exact(custody_path, raw)
    _write_exact(primary_path, raw)
    if _read_exact(custody_path) != raw or _read_exact(primary_path) != raw:
        _fatal("head COMMIT differs across custody roots")
    _parse_commit(
        raw,
        config=config,
        manifest_sha256=manifest_sha256,
        registration=registration,
        prepare=prepare,
    )
    return digest, raw


def _lineage_path(config: HeadLedgerConfig, game_pk: int) -> Path:
    return config.runtime_root / canonical_lineage_relative_path(game_pk)


def _replay_portable_head(
    config: HeadLedgerConfig,
    head: feed_lineage.FeedPortableHead,
) -> feed_lineage.FeedLineageSnapshot:
    path = _lineage_path(config, head.game_pk)
    if not path.parent.is_dir():
        _fatal("registered runtime game directory is missing")
    snapshot = feed_lineage.replay_feed_lineage(
        path,
        feed_anchor=config.feed_anchor,
        expected_event_count=head.event_count,
        expected_last_event_sha256=head.last_event_sha256,
        expected_sealed_segment_count=max(head.active_segment_index - 1, 0),
        expected_sealed_segments_sha256=head.sealed_segments_sha256,
        trusted_root=config.runtime_root,
    )
    if feed_lineage.portable_head_from_snapshot(
        snapshot,
        game_pk=head.game_pk,
    ) != head:
        _fatal("lineage replay differs from the immutable portable head")
    return snapshot


def _append_single_committed_transition_for_test(
    config: HeadLedgerConfig,
    transition: lifecycle.FeedTransition,
    *,
    recorded_at: Callable[[], str],
    expected_snapshot: feed_lineage.FeedLineageSnapshot,
    source_archive_path: str,
    source_archive_receipt_sha256: str,
    source_feed_receipt_sha256: str,
    source_feed_summary_sha256: str,
    source_generation_id: str,
    fault_hook: Callable[[str], None] | None = None,
) -> CommittedFeedTransition:
    """Exercise one-game PREPARE and COMMIT outside the production cadence path."""

    if not isinstance(transition, lifecycle.FeedTransition):
        _fatal("head transaction requires a FeedTransition")
    game_pk = transition.state.game_pk
    with _control_locks(config):
        manifest_sha256 = _verify_manifest_locked(config)
        registrations = _scan_registrations_locked(
            config,
            manifest_sha256=manifest_sha256,
        )
        _verify_transaction_game_inventory(config, registrations)
        registration = registrations.get(game_pk)
        if registration is None:
            _fatal("head transaction game is not registered")
        state = _scan_game_ledger_locked(
            config,
            manifest_sha256=manifest_sha256,
            registration=registration,
        )
        if state.open_prepare is not None:
            _fatal("head transaction has an unresolved prior PREPARE")
        retained_head = feed_lineage.portable_head_from_snapshot(
            expected_snapshot,
            game_pk=game_pk,
        )
        if retained_head != state.head:
            _fatal("caller snapshot differs from the committed head ledger")
        prepared: list[OpenPrepare] = []
        committed: list[str] = []

        def publish_prepare(plan: feed_lineage.FeedAppendPlan) -> None:
            if plan.before_head != state.head:
                _fatal("append plan does not extend the committed head")
            raw = _prepare_record(
                config,
                manifest_sha256=manifest_sha256,
                registration=registration,
                plan=plan,
                prior_commit_sha256=state.prior_commit_sha256,
                source_archive_path=source_archive_path,
                source_archive_receipt_sha256=source_archive_receipt_sha256,
                source_feed_receipt_sha256=source_feed_receipt_sha256,
                source_feed_summary_sha256=source_feed_summary_sha256,
                source_generation_id=source_generation_id,
            )
            prepared.append(
                _publish_prepare_locked(
                    config,
                    manifest_sha256=manifest_sha256,
                    registration=registration,
                    raw=raw,
                )
            )
            if fault_hook is not None:
                fault_hook("after_prepare")

        def publish_commit(
            plan: feed_lineage.FeedAppendPlan,
            candidate_snapshot: feed_lineage.FeedLineageSnapshot,
            reverify: Callable[[], None],
        ) -> None:
            if len(prepared) != 1 or prepared[0].plan != plan:
                _fatal("lineage append does not match its sole PREPARE")
            if fault_hook is not None:
                fault_hook("after_lineage_append")
            reverify()
            candidate_head = feed_lineage.portable_head_from_snapshot(
                candidate_snapshot,
                game_pk=game_pk,
            )
            if candidate_head != plan.expected_post_head:
                _fatal("lineage append differs from the prepared post head")
            commit_sha256, _commit_raw = _publish_commit_locked(
                config,
                manifest_sha256=manifest_sha256,
                registration=registration,
                prepare=prepared[0],
            )
            committed.append(commit_sha256)

        snapshot = feed_lineage._append_feed_transition_uncommitted(
            _lineage_path(config, game_pk),
            transition,
            feed_anchor=config.feed_anchor,
            recorded_at=recorded_at,
            expected_snapshot=expected_snapshot,
            before_apply=publish_prepare,
            after_apply=publish_commit,
            trusted_root=config.runtime_root,
        )
        if len(prepared) != 1 or len(committed) != 1:
            _fatal("lineage append did not publish one PREPARE and COMMIT")
        prepare = prepared[0]
        actual_head = feed_lineage.portable_head_from_snapshot(
            snapshot,
            game_pk=game_pk,
        )
        if actual_head != prepare.plan.expected_post_head:
            _fatal("lineage append differs from the prepared post head")
        commit_sha256 = committed[0]
        refreshed = _scan_game_ledger_locked(
            config,
            manifest_sha256=manifest_sha256,
            registration=registration,
        )
        if (
            refreshed.open_prepare is not None
            or refreshed.head != actual_head
            or refreshed.prior_commit_sha256 != commit_sha256
        ):
            _fatal("committed head ledger did not converge after append")
        return CommittedFeedTransition(
            snapshot=snapshot,
            prepare_sha256=prepare.record_sha256,
            commit_sha256=commit_sha256,
            capital_eligible=config.capital_eligible,
        )


def _try_replay(
    config: HeadLedgerConfig,
    head: feed_lineage.FeedPortableHead,
) -> feed_lineage.FeedLineageSnapshot | None:
    try:
        return _replay_portable_head(config, head)
    except (feed_lineage.FeedLineageFatalError, HeadLedgerFatalError):
        return None


def recover_game(
    config: HeadLedgerConfig,
    *,
    game_pk: int,
) -> feed_lineage.FeedLineageSnapshot:
    """Reconcile one chain tail to exactly its prior or prepared post head."""

    game_pk = _exact_int(game_pk, field="game_pk", minimum=1)
    with _control_locks(config):
        manifest_sha256 = _verify_manifest_locked(config)
        registrations = _scan_registrations_locked(
            config,
            manifest_sha256=manifest_sha256,
        )
        _verify_transaction_game_inventory(config, registrations)
        registration = registrations.get(game_pk)
        if registration is None:
            _fatal("recovery game is not registered")
        state = _scan_game_ledger_locked(
            config,
            manifest_sha256=manifest_sha256,
            registration=registration,
        )
        prepare = state.open_prepare
        if prepare is None:
            return _replay_portable_head(config, state.head)
        committed: list[str] = []

        def publish_recovery_commit(
            plan: feed_lineage.FeedAppendPlan,
            candidate_snapshot: feed_lineage.FeedLineageSnapshot,
            reverify: Callable[[], None],
        ) -> None:
            if plan != prepare.plan:
                _fatal("recovery plan differs from the custody PREPARE")
            reverify()
            candidate_head = feed_lineage.portable_head_from_snapshot(
                candidate_snapshot,
                game_pk=game_pk,
            )
            if candidate_head != prepare.plan.expected_post_head:
                _fatal("recovery candidate differs from the prepared post head")
            commit_sha256, _commit_raw = _publish_commit_locked(
                config,
                manifest_sha256=manifest_sha256,
                registration=registration,
                prepare=prepare,
            )
            committed.append(commit_sha256)

        try:
            snapshot = feed_lineage._reconcile_prepared_feed_transition(
                _lineage_path(config, game_pk),
                prepare.transition,
                plan=prepare.plan,
                feed_anchor=config.feed_anchor,
                after_apply=publish_recovery_commit,
                trusted_root=config.runtime_root,
            )
        except feed_lineage.FeedLineageFatalError as exc:
            _fatal("open PREPARE cannot reconcile to exactly one candidate head", cause=exc)
        if len(committed) != 1:
            _fatal("recovery did not publish exactly one COMMIT")
        actual_head = feed_lineage.portable_head_from_snapshot(
            snapshot,
            game_pk=game_pk,
        )
        if actual_head != prepare.plan.expected_post_head:
            _fatal("recovered lineage differs from the prepared post head")
        commit_sha256 = committed[0]
        refreshed = _scan_game_ledger_locked(
            config,
            manifest_sha256=manifest_sha256,
            registration=registration,
        )
        if (
            refreshed.open_prepare is not None
            or refreshed.head != actual_head
            or refreshed.prior_commit_sha256 != commit_sha256
        ):
            _fatal("recovered head ledger did not converge")
        return snapshot
