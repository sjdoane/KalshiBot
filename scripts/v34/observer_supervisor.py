"""Direct-Popen Windows Job Object custodian for the v34 observer."""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import subprocess
import time
from ctypes import wintypes
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, Never, cast

import psutil

from scripts.v34 import feed_archive, feed_lineage, policy, runtime_liveness

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS: Final = 9
JOB_OBJECT_BASIC_ACCOUNTING_INFORMATION_CLASS: Final = 1
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE: Final = 0x00002000
PROCESS_SET_QUOTA: Final = 0x0100
PROCESS_TERMINATE: Final = 0x0001
PROCESS_QUERY_LIMITED_INFORMATION: Final = 0x1000
PROCESS_SYNCHRONIZE: Final = 0x00100000
PROCESS_SUSPEND_RESUME: Final = 0x0800
JOB_TERMINATE_EXIT_CODE: Final = 197


class SupervisorFatalError(RuntimeError):
    """The direct child, Windows containment, or liveness contract failed."""


def _fatal(message: str) -> Never:
    raise SupervisorFatalError(message)


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical_object(path: Path, *, field: str) -> tuple[dict[str, object], bytes]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SupervisorFatalError(f"{field} is unreadable or invalid") from exc
    if not isinstance(value, dict) or raw != policy.canonical_json_bytes(value):
        _fatal(f"{field} is not a canonical object")
    return cast("dict[str, object]", value), raw


def _require_utc(value: object, *, field: str) -> datetime:
    if type(value) is not str:
        _fatal(f"{field} is not an ISO8601 string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SupervisorFatalError(f"{field} is not ISO8601") from exc
    if parsed.tzinfo is None:
        _fatal(f"{field} is timezone-naive")
    return parsed.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class FeedTerminalCustodySpec:
    """Expected feed terminal artifacts and post-exit absence boundary."""

    terminal_manifest_path: Path
    completion_receipt_path: Path
    stop_sentinel_path: Path
    artifact_paths: Mapping[str, Path]
    ledger_roots: Mapping[str, Path]
    expected_command_sha256: str
    owned_lock_paths: tuple[Path, ...]
    owned_lock_roots: tuple[Path, ...]
    source_hashes: Mapping[str, str]
    policy_hashes: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class TerminalCustodyBindings:
    stop_sentinel_sha256: str
    terminal_generation_id: str
    terminal_summary_sha256: str
    terminal_event_log_sha256: str
    child_completion_receipt_sha256: str
    feed_terminal_artifact_manifest_sha256: str


@dataclass(slots=True)
class CustodianLockSet:
    """Create-once launch locks retained and verified for the child lifetime."""

    records: tuple[tuple[Path, bytes], ...]
    released: bool = False

    @classmethod
    def acquire(
        cls,
        paths: Sequence[Path],
        *,
        launch_nonce: str,
        command_sha256: str,
    ) -> CustodianLockSet:
        wrapper_pid = os.getpid()
        wrapper_creation_time = psutil.Process(wrapper_pid).create_time()
        created: list[tuple[Path, bytes]] = []
        try:
            for path in paths:
                raw = policy.canonical_json_bytes(
                    {
                        "command_sha256": command_sha256,
                        "launch_nonce": launch_nonce,
                        "wrapper_creation_time": wrapper_creation_time,
                        "wrapper_pid": wrapper_pid,
                    }
                )
                feed_archive._write_create_once(path, raw)
                created.append((path, raw))
        except Exception:
            for path, raw in reversed(created):
                if path.exists() and path.read_bytes() == raw:
                    path.unlink()
                    feed_archive._fsync_directory(path.parent)
            raise
        return cls(tuple(created))

    def require_owned(self) -> None:
        if self.released:
            _fatal("custodian launch locks were released before child exit")
        for path, expected in self.records:
            if not path.is_file() or path.read_bytes() != expected:
                _fatal(f"custodian launch lock ownership changed: {path.name}")

    def release_and_require_absent(self) -> None:
        if self.released:
            return
        self.require_owned()
        for path, expected in reversed(self.records):
            if path.read_bytes() != expected:
                _fatal(f"custodian launch lock changed before release: {path.name}")
            path.unlink()
            feed_archive._fsync_directory(path.parent)
        self.released = True
        for path, _expected in self.records:
            if path.exists():
                _fatal(f"custodian launch lock remains after release: {path.name}")

    def __enter__(self) -> CustodianLockSet:
        return self

    def __exit__(self, *_args: object) -> None:
        self.release_and_require_absent()


class _IoCounters(ctypes.Structure):
    _fields_ = [
        ("read_operation_count", ctypes.c_uint64),
        ("write_operation_count", ctypes.c_uint64),
        ("other_operation_count", ctypes.c_uint64),
        ("read_transfer_count", ctypes.c_uint64),
        ("write_transfer_count", ctypes.c_uint64),
        ("other_transfer_count", ctypes.c_uint64),
    ]


class _BasicLimitInformation(ctypes.Structure):
    _fields_ = [
        ("per_process_user_time_limit", ctypes.c_int64),
        ("per_job_user_time_limit", ctypes.c_int64),
        ("limit_flags", wintypes.DWORD),
        ("minimum_working_set_size", ctypes.c_size_t),
        ("maximum_working_set_size", ctypes.c_size_t),
        ("active_process_limit", wintypes.DWORD),
        ("affinity", ctypes.c_size_t),
        ("priority_class", wintypes.DWORD),
        ("scheduling_class", wintypes.DWORD),
    ]


class _ExtendedLimitInformation(ctypes.Structure):
    _fields_ = [
        ("basic_limit_information", _BasicLimitInformation),
        ("io_info", _IoCounters),
        ("process_memory_limit", ctypes.c_size_t),
        ("job_memory_limit", ctypes.c_size_t),
        ("peak_process_memory_used", ctypes.c_size_t),
        ("peak_job_memory_used", ctypes.c_size_t),
    ]


class _BasicAccountingInformation(ctypes.Structure):
    _fields_ = [
        ("total_user_time", ctypes.c_int64),
        ("total_kernel_time", ctypes.c_int64),
        ("this_period_total_user_time", ctypes.c_int64),
        ("this_period_total_kernel_time", ctypes.c_int64),
        ("total_page_fault_count", wintypes.DWORD),
        ("total_processes", wintypes.DWORD),
        ("active_processes", wintypes.DWORD),
        ("total_terminated_processes", wintypes.DWORD),
    ]


def _kernel32() -> Any:
    if os.name != "nt":
        _fatal("v34 production containment requires Windows")
    kernel32 = cast("Any", ctypes).WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.SetInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.LPVOID,
        wintypes.DWORD,
    ]
    kernel32.SetInformationJobObject.restype = wintypes.BOOL
    kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel32.TerminateJobObject.restype = wintypes.BOOL
    kernel32.QueryInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.LPVOID,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel32.QueryInformationJobObject.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    return kernel32


def _resume_process(child_pid: int) -> None:
    kernel32 = _kernel32()
    process_handle = kernel32.OpenProcess(PROCESS_SUSPEND_RESUME, False, child_pid)
    if not process_handle:
        raise SupervisorFatalError("suspended observer handle cannot be opened") from ctypes.WinError(
            ctypes.get_last_error()
        )
    try:
        ntdll = cast("Any", ctypes).WinDLL("ntdll", use_last_error=True)
        ntdll.NtResumeProcess.argtypes = [wintypes.HANDLE]
        ntdll.NtResumeProcess.restype = wintypes.LONG
        status = int(ntdll.NtResumeProcess(process_handle))
        if status != 0:
            _fatal(f"suspended observer resume failed with NTSTATUS {status}")
    finally:
        kernel32.CloseHandle(process_handle)


@dataclass(slots=True)
class WindowsJob:
    """A kill-on-close job retained for the complete child lifetime."""

    handle: int | None

    @classmethod
    def create(cls) -> WindowsJob:
        kernel32 = _kernel32()
        handle = kernel32.CreateJobObjectW(None, None)
        if not handle:
            raise SupervisorFatalError("Windows Job Object creation failed") from ctypes.WinError(
                ctypes.get_last_error()
            )
        info = _ExtendedLimitInformation()
        info.basic_limit_information.limit_flags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not kernel32.SetInformationJobObject(
            handle,
            JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS,
            ctypes.byref(info),
            ctypes.sizeof(info),
        ):
            kernel32.CloseHandle(handle)
            raise SupervisorFatalError("Windows Job Object policy failed") from ctypes.WinError(
                ctypes.get_last_error()
            )
        return cls(handle=int(handle))

    def _exact_handle(self) -> int:
        if self.handle is None:
            _fatal("Windows Job Object is closed")
        return self.handle

    def assign(self, child: subprocess.Popen[bytes]) -> None:
        if child.poll() is not None:
            _fatal("observer child exited before Job Object assignment")
        process = psutil.Process(child.pid)
        if process.children(recursive=True):
            _fatal("observer child created a descendant before containment")
        kernel32 = _kernel32()
        rights = (
            PROCESS_SET_QUOTA
            | PROCESS_TERMINATE
            | PROCESS_QUERY_LIMITED_INFORMATION
            | PROCESS_SYNCHRONIZE
        )
        process_handle = kernel32.OpenProcess(rights, False, child.pid)
        if not process_handle:
            raise SupervisorFatalError("observer process handle cannot be opened") from ctypes.WinError(
                ctypes.get_last_error()
            )
        try:
            if not kernel32.AssignProcessToJobObject(
                self._exact_handle(),
                process_handle,
            ):
                raise SupervisorFatalError("observer Job Object assignment failed") from ctypes.WinError(
                    ctypes.get_last_error()
                )
        finally:
            kernel32.CloseHandle(process_handle)

    def active_processes(self) -> int:
        kernel32 = _kernel32()
        info = _BasicAccountingInformation()
        returned = wintypes.DWORD()
        if not kernel32.QueryInformationJobObject(
            self._exact_handle(),
            JOB_OBJECT_BASIC_ACCOUNTING_INFORMATION_CLASS,
            ctypes.byref(info),
            ctypes.sizeof(info),
            ctypes.byref(returned),
        ):
            raise SupervisorFatalError("Windows Job Object query failed") from ctypes.WinError(
                ctypes.get_last_error()
            )
        if returned.value not in {0, ctypes.sizeof(info)}:
            _fatal("Windows Job Object accounting size differs")
        return int(info.active_processes)

    def terminate_and_require_empty(self) -> None:
        kernel32 = _kernel32()
        if not kernel32.TerminateJobObject(
            self._exact_handle(),
            JOB_TERMINATE_EXIT_CODE,
        ):
            raise SupervisorFatalError("Windows Job Object termination failed") from ctypes.WinError(
                ctypes.get_last_error()
            )
        deadline = time.monotonic() + 5.0
        while self.active_processes() != 0:
            if time.monotonic() > deadline:
                _fatal("Windows Job Object retained a live process after termination")
            time.sleep(0.05)

    def close(self) -> None:
        handle = self.handle
        if handle is None:
            return
        self.handle = None
        if not _kernel32().CloseHandle(handle):
            raise SupervisorFatalError("Windows Job Object close failed") from ctypes.WinError(
                ctypes.get_last_error()
            )

    def __enter__(self) -> WindowsJob:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()


_FEED_TERMINAL_ARTIFACT_NAMES: Final = {
    "completion_receipt",
    "heartbeat",
    "public_receipt",
    "public_summary",
    "schedule_snapshot",
    "stop_sentinel",
    "terminal_event_log",
    "terminal_state",
}
_FEED_LEDGER_ROOT_NAMES: Final = {
    "custody_control",
    "custody_source",
    "runtime_control",
    "runtime_games",
}


def _locked_feed_lock_paths() -> tuple[Path, ...]:
    freshness = policy.PRIMARY_POLICY.get("freshness_policy")
    if not isinstance(freshness, dict):
        _fatal("primary policy freshness section is missing")
    relative = freshness.get("feed_lock")
    if type(relative) is not str or not relative:
        _fatal("primary policy feed lock path is missing")
    path = (policy.REPOSITORY_ROOT / relative).resolve()
    try:
        path.relative_to(policy.REPOSITORY_ROOT.resolve())
    except ValueError as exc:
        raise SupervisorFatalError("primary policy feed lock escapes repository") from exc
    return (path,)


def _validate_hash_map(value: Mapping[str, str], *, field: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for name, digest in value.items():
        if type(name) is not str or not name:
            _fatal(f"{field} contains an invalid name")
        try:
            policy.validate_sha256(digest, field=f"{field}[{name}]")
        except (TypeError, ValueError) as exc:
            raise SupervisorFatalError(f"{field} contains an invalid hash") from exc
        result[name] = digest
    if not result:
        _fatal(f"{field} is empty")
    return result


def _validate_terminal_spec(spec: FeedTerminalCustodySpec) -> None:
    if not isinstance(spec, FeedTerminalCustodySpec):
        _fatal("feed terminal custody specification is missing")
    if set(spec.artifact_paths) != _FEED_TERMINAL_ARTIFACT_NAMES:
        _fatal("feed terminal custody artifact population differs")
    if set(spec.ledger_roots) != _FEED_LEDGER_ROOT_NAMES:
        _fatal("feed terminal custody ledger root population differs")
    try:
        policy.validate_sha256(
            spec.expected_command_sha256,
            field="custody.expected_command_sha256",
        )
    except (TypeError, ValueError) as exc:
        raise SupervisorFatalError("expected observer command hash is invalid") from exc
    if spec.artifact_paths.get("completion_receipt") != spec.completion_receipt_path:
        _fatal("feed completion receipt path differs inside custody specification")
    if spec.artifact_paths.get("stop_sentinel") != spec.stop_sentinel_path:
        _fatal("feed stop sentinel path differs inside custody specification")
    if tuple(spec.owned_lock_paths) != _locked_feed_lock_paths():
        _fatal("feed terminal custody lock paths differ from primary policy")
    if set(spec.owned_lock_roots) != {path.parent for path in spec.owned_lock_paths}:
        _fatal("feed terminal custody lock roots differ from primary policy")
    if not spec.owned_lock_paths or not spec.owned_lock_roots:
        _fatal("feed terminal custody lock boundary is empty")
    validated_source_hashes = _validate_hash_map(
        spec.source_hashes,
        field="custody.source_hashes",
    )
    if not policy.REQUIRED_LAUNCH_SOURCES.issubset(validated_source_hashes):
        _fatal("feed terminal custody required source hashes are missing")
    for source_name, expected_sha256 in validated_source_hashes.items():
        source_path = (policy.REPOSITORY_ROOT / source_name).resolve()
        try:
            source_path.relative_to(policy.REPOSITORY_ROOT.resolve())
        except ValueError as exc:
            raise SupervisorFatalError("terminal custody source escapes repository") from exc
        if not source_path.is_file() or _sha256(source_path.read_bytes()) != expected_sha256:
            _fatal(f"terminal custody source bytes differ: {source_name}")
    if set(spec.policy_hashes) != {
        "feed_launch_manifest_sha256",
        "primary_policy_sha256",
        "queue_launch_manifest_sha256",
    }:
        _fatal("feed terminal custody policy hash population differs")
    _validate_hash_map(spec.policy_hashes, field="custody.policy_hashes")
    launch_outputs = {
        spec.terminal_manifest_path,
        *spec.artifact_paths.values(),
    }
    for path in launch_outputs:
        if path.exists() or not path.parent.is_dir():
            _fatal("feed terminal custody output is not fresh or parent is missing")
    for root in spec.owned_lock_roots:
        if not root.is_dir():
            _fatal("feed terminal custody lock root is missing")
    for path in spec.owned_lock_paths:
        if path.exists():
            _fatal("feed terminal custody lock exists before launch")
    for root in spec.ledger_roots.values():
        if root.exists() and not root.is_dir():
            _fatal("feed terminal custody ledger root is not a directory")
        if not root.exists() and not root.parent.is_dir():
            _fatal("feed terminal custody ledger root parent is missing")


def _require_child_absent(child_pid: int, child_creation_time: float) -> None:
    try:
        process = psutil.Process(child_pid)
        actual_creation_time = process.create_time()
    except psutil.NoSuchProcess:
        return
    if actual_creation_time == child_creation_time:
        _fatal("observer child remains after direct-handle exit")


def _require_owned_locks_absent(spec: FeedTerminalCustodySpec) -> None:
    for path in spec.owned_lock_paths:
        if path.exists():
            _fatal(f"owned observer lock remains after exit: {path.name}")


def _require_internal_append_locks_released(spec: FeedTerminalCustodySpec) -> None:
    if os.name != "nt":
        _fatal("internal append lock proof requires Windows")
    import msvcrt

    for root in spec.ledger_roots.values():
        if not root.is_dir():
            _fatal("terminal ledger root is missing after child exit")
        for path in root.rglob("*.v34append.lock"):
            if not path.is_file() or path.stat().st_size != 0:
                _fatal(f"internal append lock is not released: {path.name}")
            with path.open("r+b", buffering=0) as handle:
                try:
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                except OSError as exc:
                    raise SupervisorFatalError(
                        f"internal append lock is still held: {path.name}"
                    ) from exc
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            if path.stat().st_size != 0:
                _fatal(f"internal append lock probe changed its marker: {path.name}")


def _ledger_inventory(spec: FeedTerminalCustodySpec) -> list[dict[str, object]]:
    inventory: list[dict[str, object]] = []
    for label, root in spec.ledger_roots.items():
        if not root.is_dir():
            _fatal(f"terminal ledger root is missing: {label}")
        for path in sorted(
            item
            for item in root.rglob("*")
            if item.is_file() and not item.name.endswith(".v34append.lock")
        ):
            raw = path.read_bytes()
            inventory.append(
                {
                    "root": label,
                    "relative_path": path.relative_to(root).as_posix(),
                    "sha256": _sha256(raw),
                    "size": len(raw),
                }
            )
    if not inventory:
        _fatal("terminal ledger inventory is empty")
    return inventory


def _validated_artifact_binding(
    value: object,
    *,
    expected_path: Path,
    field: str,
) -> str:
    if not isinstance(value, dict) or set(value) != {"path", "sha256", "size"}:
        _fatal(f"{field} binding keys differ")
    if value.get("path") != str(expected_path.resolve()):
        _fatal(f"{field} path differs")
    if not expected_path.is_file():
        _fatal(f"{field} file is missing")
    raw = expected_path.read_bytes()
    digest = _sha256(raw)
    if value.get("sha256") != digest or value.get("size") != len(raw):
        _fatal(f"{field} binding differs from disk")
    return digest


def _validate_feed_terminal_custody(
    spec: FeedTerminalCustodySpec,
    *,
    launch_nonce: str,
    run_signature: str,
    child_pid: int,
    child_creation_time: float,
) -> TerminalCustodyBindings:
    _require_child_absent(child_pid, child_creation_time)
    _require_owned_locks_absent(spec)
    _require_internal_append_locks_released(spec)
    manifest, manifest_raw = _canonical_object(
        spec.terminal_manifest_path,
        field="feed terminal artifact manifest",
    )
    required_manifest_keys = {
        "artifacts",
        "batch_count",
        "created_at",
        "kind",
        "latest_batch_commit_sha256",
        "latest_batch_name",
        "launch_nonce",
        "outcome",
        "policy_hashes",
        "registry_manifest_sha256",
        "run_signature",
        "source_hashes",
        "stop_sentinel_sha256",
        "terminal_event_log_sha256",
        "terminal_generation_id",
        "terminal_state_sha256",
        "terminal_summary_sha256",
    }
    if set(manifest) != required_manifest_keys:
        _fatal("feed terminal artifact manifest keys differ")
    if (
        manifest.get("kind") != "v34_feed_terminal_artifact_manifest"
        or manifest.get("launch_nonce") != launch_nonce
        or manifest.get("run_signature") != run_signature
        or manifest.get("source_hashes") != dict(spec.source_hashes)
        or manifest.get("policy_hashes") != dict(spec.policy_hashes)
    ):
        _fatal("feed terminal artifact manifest provenance differs")
    batch_count = manifest.get("batch_count")
    latest_batch_name = manifest.get("latest_batch_name")
    latest_batch_commit_sha256 = manifest.get("latest_batch_commit_sha256")
    registry_manifest_sha256 = manifest.get("registry_manifest_sha256")
    if type(batch_count) is not int or batch_count < 1:
        _fatal("feed terminal artifact manifest batch count is invalid")
    if type(latest_batch_name) is not str or not latest_batch_name:
        _fatal("feed terminal artifact manifest latest batch is invalid")
    for value, field in (
        (latest_batch_commit_sha256, "latest_batch_commit_sha256"),
        (registry_manifest_sha256, "registry_manifest_sha256"),
    ):
        try:
            policy.validate_sha256(value, field=field)
        except (TypeError, ValueError) as exc:
            raise SupervisorFatalError(f"feed terminal {field} is invalid") from exc
    _require_utc(manifest.get("created_at"), field="terminal.created_at")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict) or set(artifacts) != set(spec.artifact_paths):
        _fatal("feed terminal artifact manifest population differs")
    artifact_hashes = {
        name: _validated_artifact_binding(
            artifacts[name],
            expected_path=path,
            field=f"terminal.artifacts[{name}]",
        )
        for name, path in spec.artifact_paths.items()
    }
    completion, completion_raw = _canonical_object(
        spec.completion_receipt_path,
        field="feed child completion receipt",
    )
    completion_keys = {
        "batch_count",
        "capital_eligible",
        "completed_at",
        "last_feed_generation_id",
        "last_feed_summary_sha256",
        "launch_nonce",
        "outcome",
        "run_signature",
        "stop_sentinel_sha256",
        "terminal_event_log_sha256",
        "terminal_state_sha256",
    }
    if set(completion) != completion_keys:
        _fatal("feed child completion receipt keys differ")
    _require_utc(completion.get("completed_at"), field="completion.completed_at")
    generation_id = manifest.get("terminal_generation_id")
    summary_sha256 = manifest.get("terminal_summary_sha256")
    event_log_sha256 = manifest.get("terminal_event_log_sha256")
    state_sha256 = manifest.get("terminal_state_sha256")
    stop_sha256 = manifest.get("stop_sentinel_sha256")
    if type(generation_id) is not str or not generation_id:
        _fatal("feed terminal generation is absent")
    for value, field in (
        (summary_sha256, "terminal_summary_sha256"),
        (event_log_sha256, "terminal_event_log_sha256"),
        (state_sha256, "terminal_state_sha256"),
        (stop_sha256, "stop_sentinel_sha256"),
    ):
        try:
            policy.validate_sha256(value, field=field)
        except (TypeError, ValueError) as exc:
            raise SupervisorFatalError(f"feed {field} is invalid") from exc
    if (
        completion.get("launch_nonce") != launch_nonce
        or completion.get("run_signature") != run_signature
        or completion.get("capital_eligible") is not False
        or completion.get("batch_count") != manifest.get("batch_count")
        or completion.get("outcome") != manifest.get("outcome")
        or completion.get("last_feed_generation_id") != generation_id
        or completion.get("last_feed_summary_sha256") != summary_sha256
        or completion.get("terminal_event_log_sha256") != event_log_sha256
        or completion.get("terminal_state_sha256") != state_sha256
        or completion.get("stop_sentinel_sha256") != stop_sha256
    ):
        _fatal("feed child completion receipt differs from terminal manifest")
    if (
        artifact_hashes["completion_receipt"] != _sha256(completion_raw)
        or artifact_hashes["terminal_event_log"] != event_log_sha256
        or artifact_hashes["terminal_state"] != state_sha256
        or artifact_hashes["stop_sentinel"] != stop_sha256
        or artifact_hashes["public_summary"] != summary_sha256
    ):
        _fatal("feed terminal artifact hashes differ across custody records")
    public_receipt, _receipt_raw = _canonical_object(
        spec.artifact_paths["public_receipt"],
        field="feed terminal public receipt",
    )
    expected_receipt_keys = set(policy.FEED_PROVENANCE_KEYS) | {
        "generation_id",
        "summary_sha256",
    }
    if (
        set(public_receipt) != expected_receipt_keys
        or public_receipt.get("launch_manifest_sha256")
        != spec.policy_hashes["feed_launch_manifest_sha256"]
        or public_receipt.get("policy_sha256")
        != spec.policy_hashes["primary_policy_sha256"]
        or public_receipt.get("generation_id") != generation_id
        or public_receipt.get("summary_sha256") != summary_sha256
        or public_receipt.get("launch_nonce") != launch_nonce
        or public_receipt.get("run_signature") != run_signature
        or public_receipt.get("source_hashes") != dict(spec.source_hashes)
    ):
        _fatal("feed terminal public receipt differs from terminal generation")
    public_summary, _summary_raw = _canonical_object(
        spec.artifact_paths["public_summary"],
        field="feed terminal public summary",
    )
    expected_summary_keys = set(policy.FEED_PROVENANCE_KEYS) | {
        "cycle_observed_at",
        "game_states",
        "generation_id",
        "kind",
        "lifecycle_states",
    }
    summary_game_states = public_summary.get("game_states")
    summary_lifecycle_states = public_summary.get("lifecycle_states")
    if (
        set(public_summary) != expected_summary_keys
        or public_summary.get("kind") != "v34_feed_generation"
        or public_summary.get("launch_manifest_sha256")
        != spec.policy_hashes["feed_launch_manifest_sha256"]
        or public_summary.get("policy_sha256")
        != spec.policy_hashes["primary_policy_sha256"]
        or public_summary.get("generation_id") != generation_id
        or public_summary.get("launch_nonce") != launch_nonce
        or public_summary.get("run_signature") != run_signature
        or public_summary.get("source_hashes") != dict(spec.source_hashes)
        or not isinstance(summary_game_states, dict)
        or not summary_game_states
        or not isinstance(summary_lifecycle_states, dict)
        or set(summary_game_states) != set(summary_lifecycle_states)
    ):
        _fatal("feed terminal public summary provenance differs")
    _require_utc(
        public_summary.get("cycle_observed_at"),
        field="public_summary.cycle_observed_at",
    )
    assert isinstance(summary_game_states, dict)
    assert isinstance(summary_lifecycle_states, dict)
    for game_key in sorted(summary_game_states):
        archived_game = summary_game_states[game_key]
        serialized_state = summary_lifecycle_states[game_key]
        if not isinstance(archived_game, dict) or not isinstance(serialized_state, dict):
            _fatal("feed terminal public game or lifecycle state is malformed")
        try:
            game_pk = int(game_key)
            state = feed_lineage.deserialize_game_state(
                policy.canonical_json_bytes(serialized_state)
            )
        except (TypeError, ValueError, feed_lineage.FeedLineageFatalError) as exc:
            raise SupervisorFatalError("feed terminal lifecycle state is invalid") from exc
        expected_archived_keys = set(policy.FEED_PROVENANCE_KEYS) | {
            "abstract_state",
            "completed_plays",
            "detailed_state",
            "game_pk",
            "generation_id",
            "observed_at",
            "official_current_total",
        }
        if (
            set(archived_game) != expected_archived_keys
            or game_pk <= 0
            or game_key != str(game_pk)
            or state.game_pk != game_pk
            or archived_game.get("game_pk") != game_pk
            or archived_game.get("generation_id") != generation_id
            or archived_game.get("launch_nonce") != launch_nonce
            or archived_game.get("launch_manifest_sha256")
            != spec.policy_hashes["feed_launch_manifest_sha256"]
            or archived_game.get("policy_sha256")
            != spec.policy_hashes["primary_policy_sha256"]
            or archived_game.get("run_signature") != run_signature
            or archived_game.get("schema_version") != policy.FEED_SCHEMA_VERSION
            or archived_game.get("source_hashes") != dict(spec.source_hashes)
            or archived_game.get("completed_plays")
            != json.loads(state.last_completed_plays_bytes)
            or archived_game.get("official_current_total")
            != state.last_official_current_total
            or archived_game.get("abstract_state") != state.last_abstract_state
            or archived_game.get("detailed_state") != state.last_detailed_state
            or archived_game.get("observed_at") != state.last_observed_at
        ):
            _fatal("feed terminal archived game differs from lifecycle state")
    stop_sentinel, _stop_raw = _canonical_object(
        spec.stop_sentinel_path,
        field="feed stop sentinel",
    )
    terminal_outcome = manifest.get("outcome")
    stop_reason = stop_sentinel.get("reason")
    expected_stop_reason = (
        terminal_outcome.removeprefix("stopped:")
        if type(terminal_outcome) is str and terminal_outcome.startswith("stopped:")
        else terminal_outcome
    )
    if (
        set(stop_sentinel) != {"launch_nonce", "reason", "requested_at"}
        or stop_sentinel.get("launch_nonce") != launch_nonce
        or type(terminal_outcome) is not str
        or not (
            terminal_outcome in {"hard_stop", "slate_final"}
            or terminal_outcome.startswith("stopped:")
        )
        or type(stop_reason) is not str
        or not stop_reason
        or stop_reason != expected_stop_reason
    ):
        _fatal("feed stop sentinel fields or outcome differ")
    _require_utc(stop_sentinel.get("requested_at"), field="stop.requested_at")
    terminal_event_log, _event_raw = _canonical_object(
        spec.artifact_paths["terminal_event_log"],
        field="feed terminal event log",
    )
    expected_event_keys = set(policy.FEED_PROVENANCE_KEYS) | {
        "batch_count",
        "inventory",
        "kind",
        "latest_batch_commit_sha256",
        "latest_batch_name",
        "registry_manifest_sha256",
    }
    expected_inventory = _ledger_inventory(spec)
    event_inventory = terminal_event_log.get("inventory")
    if (
        set(terminal_event_log) != expected_event_keys
        or terminal_event_log.get("kind") != "v34_feed_terminal_event_log"
        or terminal_event_log.get("launch_manifest_sha256")
        != spec.policy_hashes["feed_launch_manifest_sha256"]
        or terminal_event_log.get("policy_sha256")
        != spec.policy_hashes["primary_policy_sha256"]
        or terminal_event_log.get("launch_nonce") != launch_nonce
        or terminal_event_log.get("run_signature") != run_signature
        or terminal_event_log.get("source_hashes") != dict(spec.source_hashes)
        or terminal_event_log.get("batch_count") != manifest.get("batch_count")
        or terminal_event_log.get("latest_batch_name")
        != manifest.get("latest_batch_name")
        or terminal_event_log.get("latest_batch_commit_sha256")
        != manifest.get("latest_batch_commit_sha256")
        or terminal_event_log.get("registry_manifest_sha256")
        != registry_manifest_sha256
        or event_inventory != expected_inventory
        or not any(
            isinstance(item, dict)
            and item.get("sha256") == latest_batch_commit_sha256
            for item in expected_inventory
        )
        or not any(
            isinstance(item, dict)
            and item.get("sha256") == registry_manifest_sha256
            for item in expected_inventory
        )
    ):
        _fatal("feed terminal event log provenance or head differs")
    terminal_state, _state_raw = _canonical_object(
        spec.artifact_paths["terminal_state"],
        field="feed terminal state",
    )
    expected_state_keys = set(policy.FEED_PROVENANCE_KEYS) | {
        "game_states",
        "kind",
        "terminal_generation_id",
        "terminal_summary_sha256",
    }
    terminal_game_states = terminal_state.get("game_states")
    if (
        set(terminal_state) != expected_state_keys
        or terminal_state.get("kind") != "v34_feed_terminal_state"
        or terminal_state.get("launch_manifest_sha256")
        != spec.policy_hashes["feed_launch_manifest_sha256"]
        or terminal_state.get("policy_sha256")
        != spec.policy_hashes["primary_policy_sha256"]
        or terminal_state.get("launch_nonce") != launch_nonce
        or terminal_state.get("run_signature") != run_signature
        or terminal_state.get("source_hashes") != dict(spec.source_hashes)
        or terminal_state.get("terminal_generation_id") != generation_id
        or terminal_state.get("terminal_summary_sha256") != summary_sha256
        or not isinstance(terminal_game_states, dict)
        or terminal_game_states != summary_lifecycle_states
        or any(not isinstance(value, dict) for value in terminal_game_states.values())
    ):
        _fatal("feed terminal state provenance or generation differs")
    return TerminalCustodyBindings(
        stop_sentinel_sha256=stop_sha256,
        terminal_generation_id=generation_id,
        terminal_summary_sha256=summary_sha256,
        terminal_event_log_sha256=event_log_sha256,
        child_completion_receipt_sha256=_sha256(completion_raw),
        feed_terminal_artifact_manifest_sha256=_sha256(manifest_raw),
    )


def _publish_receipt(
    path: Path,
    *,
    launch_nonce: str,
    run_signature: str,
    child_pid: int,
    child_creation_time: float,
    command_sha256: str,
    outcome: str,
    reason: str | None,
    return_code: int | None,
    source_hashes: Mapping[str, str],
    policy_hashes: Mapping[str, str],
    terminal: TerminalCustodyBindings | None = None,
) -> None:
    wrapper_pid = os.getpid()
    wrapper_creation_time = psutil.Process(wrapper_pid).create_time()
    raw = policy.canonical_json_bytes(
        {
            "actual_os_exit_code": return_code,
            "child_completion_receipt_sha256": (
                None if terminal is None else terminal.child_completion_receipt_sha256
            ),
            "child_creation_time": child_creation_time,
            "child_pid": child_pid,
            "command_sha256": command_sha256,
            "feed_terminal_artifact_manifest_sha256": (
                None
                if terminal is None
                else terminal.feed_terminal_artifact_manifest_sha256
            ),
            "launch_nonce": launch_nonce,
            "outcome": outcome,
            "policy_hashes": dict(policy_hashes),
            "reason": reason,
            "recorded_at": datetime.now(tz=UTC).isoformat(),
            "return_code": return_code,
            "run_signature": run_signature,
            "source_hashes": dict(source_hashes),
            "stop_sentinel_sha256": (
                None if terminal is None else terminal.stop_sentinel_sha256
            ),
            "supervisor_pid": wrapper_pid,
            "terminal_event_log_sha256": (
                None if terminal is None else terminal.terminal_event_log_sha256
            ),
            "terminal_generation_id": (
                None if terminal is None else terminal.terminal_generation_id
            ),
            "terminal_summary_sha256": (
                None if terminal is None else terminal.terminal_summary_sha256
            ),
            "wrapper_creation_time": wrapper_creation_time,
            "wrapper_pid": wrapper_pid,
        }
    )
    feed_archive._write_create_once(path, raw)


def _publish_job_gate(
    path: Path,
    *,
    launch_nonce: str,
    child_pid: int,
    child_creation_time: float,
) -> None:
    feed_archive._write_create_once(
        path,
        policy.canonical_json_bytes(
            {
                "child_creation_time": child_creation_time,
                "child_pid": child_pid,
                "launch_nonce": launch_nonce,
                "supervisor_pid": os.getpid(),
            }
        ),
    )


def launch_and_supervise(
    *,
    command: Sequence[str],
    cwd: Path,
    heartbeat_path: Path,
    job_gate_path: Path,
    receipt_path: Path,
    stdout_path: Path,
    stderr_path: Path,
    launch_nonce: str,
    run_signature: str,
    source_sha256: str,
    policy_sha256: str,
    terminal_custody: FeedTerminalCustodySpec,
    env: Mapping[str, str] | None = None,
) -> int:
    """Launch one gated child, contain it, and retain its real process handle."""

    if not command or any(type(part) is not str or not part for part in command):
        _fatal("observer command is empty or invalid")
    if not cwd.is_dir():
        _fatal("observer working directory is missing")
    _validate_terminal_spec(terminal_custody)
    if (
        source_sha256
        != terminal_custody.source_hashes.get("scripts/v34/feed_observer.py")
        or policy_sha256
        != terminal_custody.policy_hashes.get("primary_policy_sha256")
    ):
        _fatal("liveness hashes differ from keyed terminal custody provenance")
    command_bytes = policy.canonical_json_bytes(list(command))
    command_sha256 = policy.canonical_sha256(list(command))
    if command_bytes != policy.canonical_json_bytes(json.loads(command_bytes)):
        _fatal("observer command is not canonical")
    if command_sha256 != terminal_custody.expected_command_sha256:
        _fatal("observer command differs from precommitted terminal custody command")
    for path in (heartbeat_path, job_gate_path, receipt_path, stdout_path, stderr_path):
        if path.exists() or not path.parent.is_dir():
            _fatal("observer launch artifact is not fresh or its parent is missing")
    custodian_locks = CustodianLockSet.acquire(
        terminal_custody.owned_lock_paths,
        launch_nonce=launch_nonce,
        command_sha256=command_sha256,
    )
    with (
        custodian_locks,
        WindowsJob.create() as job,
        stdout_path.open("xb", buffering=0) as stdout_handle,
        stderr_path.open("xb", buffering=0) as stderr_handle,
    ):
        child = subprocess.Popen(
            list(command),
            cwd=cwd,
            env=None if env is None else dict(env),
            stdin=subprocess.DEVNULL,
            stdout=stdout_handle,
            stderr=stderr_handle,
            creationflags=(
                getattr(subprocess, "CREATE_NO_WINDOW", 0)
                | getattr(subprocess, "CREATE_SUSPENDED", 0x00000004)
            ),
        )
        child_creation_time = psutil.Process(child.pid).create_time()
        assigned = False
        try:
            job.assign(child)
            assigned = True
            _publish_job_gate(
                job_gate_path,
                launch_nonce=launch_nonce,
                child_pid=child.pid,
                child_creation_time=child_creation_time,
            )
            gate_published_ns = time.monotonic_ns()
            _resume_process(child.pid)
            reader = runtime_liveness.HeartbeatReader(
                heartbeat_path,
                launch_nonce=launch_nonce,
                run_signature=run_signature,
                child_pid=child.pid,
                child_creation_time=child_creation_time,
                source_sha256=source_sha256,
                policy_sha256=policy_sha256,
            )
            while True:
                custodian_locks.require_owned()
                return_code = child.poll()
                if return_code is not None:
                    if job.active_processes() != 0:
                        job.terminate_and_require_empty()
                        custodian_locks.release_and_require_absent()
                        _publish_receipt(
                            receipt_path,
                            launch_nonce=launch_nonce,
                            run_signature=run_signature,
                            child_pid=child.pid,
                            child_creation_time=child_creation_time,
                            command_sha256=command_sha256,
                            outcome="descendant_survived_child",
                            reason="the contained job retained a process after child exit",
                            return_code=return_code,
                            source_hashes=terminal_custody.source_hashes,
                            policy_hashes=terminal_custody.policy_hashes,
                        )
                        return 6
                    custodian_locks.release_and_require_absent()
                    if return_code == 0:
                        try:
                            terminal_heartbeat = reader.require_live()
                        except runtime_liveness.LivenessFatalError as exc:
                            _publish_receipt(
                                receipt_path,
                                launch_nonce=launch_nonce,
                                run_signature=run_signature,
                                child_pid=child.pid,
                                child_creation_time=child_creation_time,
                                command_sha256=command_sha256,
                                outcome="invalid_terminal_heartbeat",
                                reason=str(exc),
                                return_code=return_code,
                                source_hashes=terminal_custody.source_hashes,
                                policy_hashes=terminal_custody.policy_hashes,
                            )
                            return 4
                        if (
                            terminal_heartbeat.phase
                            != runtime_liveness.CYCLE_COMPLETE_PHASE
                        ):
                            _publish_receipt(
                                receipt_path,
                                launch_nonce=launch_nonce,
                                run_signature=run_signature,
                                child_pid=child.pid,
                                child_creation_time=child_creation_time,
                                command_sha256=command_sha256,
                                outcome="incomplete_terminal_cycle",
                                reason="successful child exit lacked cycle completion",
                                return_code=return_code,
                                source_hashes=terminal_custody.source_hashes,
                                policy_hashes=terminal_custody.policy_hashes,
                            )
                            return 4
                        try:
                            terminal_bindings = _validate_feed_terminal_custody(
                                terminal_custody,
                                launch_nonce=launch_nonce,
                                run_signature=run_signature,
                                child_pid=child.pid,
                                child_creation_time=child_creation_time,
                            )
                        except SupervisorFatalError as exc:
                            _publish_receipt(
                                receipt_path,
                                launch_nonce=launch_nonce,
                                run_signature=run_signature,
                                child_pid=child.pid,
                                child_creation_time=child_creation_time,
                                command_sha256=command_sha256,
                                outcome="invalid_terminal_custody",
                                reason=str(exc),
                                return_code=return_code,
                                source_hashes=terminal_custody.source_hashes,
                                policy_hashes=terminal_custody.policy_hashes,
                            )
                            return 4
                    else:
                        terminal_bindings = None
                    _publish_receipt(
                        receipt_path,
                        launch_nonce=launch_nonce,
                        run_signature=run_signature,
                        child_pid=child.pid,
                        child_creation_time=child_creation_time,
                        command_sha256=command_sha256,
                        outcome="child_exited",
                        reason=None,
                        return_code=return_code,
                        source_hashes=terminal_custody.source_hashes,
                        policy_hashes=terminal_custody.policy_hashes,
                        terminal=terminal_bindings,
                    )
                    return 0 if return_code == 0 else 3
                try:
                    reader.require_live()
                except runtime_liveness.LivenessFatalError as exc:
                    if (
                        reader.latest is None
                        and time.monotonic_ns() - gate_published_ns
                        <= runtime_liveness.MAX_HEARTBEAT_AGE_NS
                    ):
                        if not heartbeat_path.exists():
                            time.sleep(runtime_liveness.SUPERVISOR_CHECK_SECONDS)
                            continue
                        try:
                            reader.require_exact_initial_empty()
                        except runtime_liveness.LivenessFatalError:
                            pass
                        else:
                            time.sleep(runtime_liveness.SUPERVISOR_CHECK_SECONDS)
                            continue
                    job.terminate_and_require_empty()
                    killed_return_code = child.wait(timeout=5.0)
                    custodian_locks.release_and_require_absent()
                    _publish_receipt(
                        receipt_path,
                        launch_nonce=launch_nonce,
                        run_signature=run_signature,
                        child_pid=child.pid,
                        child_creation_time=child_creation_time,
                        command_sha256=command_sha256,
                        outcome="forced_kill",
                        reason=str(exc),
                        return_code=killed_return_code,
                        source_hashes=terminal_custody.source_hashes,
                        policy_hashes=terminal_custody.policy_hashes,
                    )
                    return 4
                time.sleep(runtime_liveness.SUPERVISOR_CHECK_SECONDS)
        except Exception:
            if child.poll() is None:
                if assigned:
                    job.terminate_and_require_empty()
                else:
                    child.kill()
                child.wait(timeout=5.0)
            custodian_locks.release_and_require_absent()
            raise


def _terminal_spec_from_path(path: Path) -> FeedTerminalCustodySpec:
    value, _raw = _canonical_object(path, field="feed terminal custody specification")
    expected_keys = {
        "artifact_paths",
        "completion_receipt_path",
        "expected_command_sha256",
        "ledger_roots",
        "owned_lock_paths",
        "owned_lock_roots",
        "policy_hashes",
        "source_hashes",
        "stop_sentinel_path",
        "terminal_manifest_path",
    }
    if set(value) != expected_keys:
        _fatal("feed terminal custody specification keys differ")
    artifact_paths = value.get("artifact_paths")
    ledger_roots = value.get("ledger_roots")
    source_hashes = value.get("source_hashes")
    policy_hashes = value.get("policy_hashes")
    owned_lock_paths = value.get("owned_lock_paths")
    owned_lock_roots = value.get("owned_lock_roots")
    if (
        not isinstance(artifact_paths, dict)
        or not all(type(key) is str and type(item) is str for key, item in artifact_paths.items())
        or not isinstance(ledger_roots, dict)
        or not all(type(key) is str and type(item) is str for key, item in ledger_roots.items())
        or not isinstance(source_hashes, dict)
        or not all(type(key) is str and type(item) is str for key, item in source_hashes.items())
        or not isinstance(policy_hashes, dict)
        or not all(type(key) is str and type(item) is str for key, item in policy_hashes.items())
        or not isinstance(owned_lock_paths, list)
        or not all(type(item) is str for item in owned_lock_paths)
        or not isinstance(owned_lock_roots, list)
        or not all(type(item) is str for item in owned_lock_roots)
    ):
        _fatal("feed terminal custody specification values differ")
    scalar_paths = {
        name: value.get(name)
        for name in (
            "terminal_manifest_path",
            "completion_receipt_path",
            "stop_sentinel_path",
        )
    }
    if not all(type(item) is str for item in scalar_paths.values()):
        _fatal("feed terminal custody scalar paths differ")
    expected_command_sha256 = value.get("expected_command_sha256")
    if type(expected_command_sha256) is not str:
        _fatal("feed terminal custody expected command hash differs")
    return FeedTerminalCustodySpec(
        terminal_manifest_path=Path(cast("str", scalar_paths["terminal_manifest_path"])),
        completion_receipt_path=Path(
            cast("str", scalar_paths["completion_receipt_path"])
        ),
        stop_sentinel_path=Path(cast("str", scalar_paths["stop_sentinel_path"])),
        artifact_paths={
            cast("str", key): Path(cast("str", item))
            for key, item in artifact_paths.items()
        },
        expected_command_sha256=expected_command_sha256,
        ledger_roots={
            cast("str", key): Path(cast("str", item))
            for key, item in ledger_roots.items()
        },
        owned_lock_paths=tuple(Path(cast("str", item)) for item in owned_lock_paths),
        owned_lock_roots=tuple(Path(cast("str", item)) for item in owned_lock_roots),
        source_hashes={
            cast("str", key): cast("str", item)
            for key, item in source_hashes.items()
        },
        policy_hashes={
            cast("str", key): cast("str", item)
            for key, item in policy_hashes.items()
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--command-json", type=Path, required=True)
    parser.add_argument("--cwd", type=Path, required=True)
    parser.add_argument("--heartbeat-path", type=Path, required=True)
    parser.add_argument("--job-gate-path", type=Path, required=True)
    parser.add_argument("--receipt-path", type=Path, required=True)
    parser.add_argument("--stdout-path", type=Path, required=True)
    parser.add_argument("--stderr-path", type=Path, required=True)
    parser.add_argument("--launch-nonce", required=True)
    parser.add_argument("--run-signature", required=True)
    parser.add_argument("--source-sha256", required=True)
    parser.add_argument("--policy-sha256", required=True)
    parser.add_argument("--terminal-custody-json", type=Path, required=True)
    args = parser.parse_args()
    command_value = json.loads(args.command_json.read_bytes())
    if not isinstance(command_value, list) or not all(
        type(part) is str for part in command_value
    ):
        _fatal("observer command JSON is invalid")
    raise SystemExit(
        launch_and_supervise(
            command=cast("list[str]", command_value),
            cwd=args.cwd,
            heartbeat_path=args.heartbeat_path,
            job_gate_path=args.job_gate_path,
            receipt_path=args.receipt_path,
            stdout_path=args.stdout_path,
            stderr_path=args.stderr_path,
            launch_nonce=args.launch_nonce,
            run_signature=args.run_signature,
            source_sha256=args.source_sha256,
            policy_sha256=args.policy_sha256,
            terminal_custody=_terminal_spec_from_path(args.terminal_custody_json),
        )
    )


if __name__ == "__main__":
    main()
