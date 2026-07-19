"""Direct-Popen Windows Job Object custodian for the v34 observer."""

from __future__ import annotations

import argparse
import ctypes
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

from scripts.v34 import feed_archive, policy, runtime_liveness

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


def _publish_receipt(
    path: Path,
    *,
    launch_nonce: str,
    child_pid: int,
    child_creation_time: float,
    command_sha256: str,
    outcome: str,
    reason: str | None,
    return_code: int | None,
) -> None:
    raw = policy.canonical_json_bytes(
        {
            "child_creation_time": child_creation_time,
            "child_pid": child_pid,
            "command_sha256": command_sha256,
            "launch_nonce": launch_nonce,
            "outcome": outcome,
            "reason": reason,
            "recorded_at": datetime.now(tz=UTC).isoformat(),
            "return_code": return_code,
            "supervisor_pid": os.getpid(),
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
    env: Mapping[str, str] | None = None,
) -> int:
    """Launch one gated child, contain it, and retain its real process handle."""

    if not command or any(type(part) is not str or not part for part in command):
        _fatal("observer command is empty or invalid")
    if not cwd.is_dir():
        _fatal("observer working directory is missing")
    command_bytes = policy.canonical_json_bytes(list(command))
    command_sha256 = policy.canonical_sha256(list(command))
    if command_bytes != policy.canonical_json_bytes(json.loads(command_bytes)):
        _fatal("observer command is not canonical")
    for path in (heartbeat_path, job_gate_path, receipt_path, stdout_path, stderr_path):
        if path.exists() or not path.parent.is_dir():
            _fatal("observer launch artifact is not fresh or its parent is missing")
    with (
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
                return_code = child.poll()
                if return_code is not None:
                    if job.active_processes() != 0:
                        job.terminate_and_require_empty()
                        _publish_receipt(
                            receipt_path,
                            launch_nonce=launch_nonce,
                            child_pid=child.pid,
                            child_creation_time=child_creation_time,
                            command_sha256=command_sha256,
                            outcome="descendant_survived_child",
                            reason="the contained job retained a process after child exit",
                            return_code=return_code,
                        )
                        return 6
                    if return_code == 0:
                        try:
                            terminal_heartbeat = reader.require_live()
                        except runtime_liveness.LivenessFatalError as exc:
                            _publish_receipt(
                                receipt_path,
                                launch_nonce=launch_nonce,
                                child_pid=child.pid,
                                child_creation_time=child_creation_time,
                                command_sha256=command_sha256,
                                outcome="invalid_terminal_heartbeat",
                                reason=str(exc),
                                return_code=return_code,
                            )
                            return 4
                        if (
                            terminal_heartbeat.phase
                            != runtime_liveness.CYCLE_COMPLETE_PHASE
                        ):
                            _publish_receipt(
                                receipt_path,
                                launch_nonce=launch_nonce,
                                child_pid=child.pid,
                                child_creation_time=child_creation_time,
                                command_sha256=command_sha256,
                                outcome="incomplete_terminal_cycle",
                                reason="successful child exit lacked cycle completion",
                                return_code=return_code,
                            )
                            return 4
                    _publish_receipt(
                        receipt_path,
                        launch_nonce=launch_nonce,
                        child_pid=child.pid,
                        child_creation_time=child_creation_time,
                        command_sha256=command_sha256,
                        outcome="child_exited",
                        reason=None,
                        return_code=return_code,
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
                    _publish_receipt(
                        receipt_path,
                        launch_nonce=launch_nonce,
                        child_pid=child.pid,
                        child_creation_time=child_creation_time,
                        command_sha256=command_sha256,
                        outcome="forced_kill",
                        reason=str(exc),
                        return_code=killed_return_code,
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
            raise


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
        )
    )


if __name__ == "__main__":
    main()
