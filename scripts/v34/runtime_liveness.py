"""Durable monotonic heartbeat chain and frozen v34 liveness checks."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import time
from ctypes import wintypes
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Final, Never, cast

import psutil

from scripts.v34 import feed_archive, policy

MAX_CYCLE_NS: Final = 30_000_000_000
MAX_HEARTBEAT_AGE_NS: Final = 12_000_000_000
SUPERVISOR_CHECK_SECONDS: Final = 1.0
MAX_HEARTBEAT_BYTES: Final = 16 * 1024
MAX_HEARTBEAT_POLL_BYTES: Final = 1024 * 1024
CYCLE_START_PHASE: Final = "cycle_start"
CYCLE_COMPLETE_PHASE: Final = "cycle_complete"
PROGRESS_PHASE_PREFIX: Final = "progress:"
HEARTBEAT_KEYS: Final = {
    "child_creation_time",
    "child_pid",
    "cycle_started_monotonic_ns",
    "launch_nonce",
    "monotonic_ns",
    "phase",
    "policy_sha256",
    "prior_heartbeat_sha256",
    "run_signature",
    "sequence",
    "source_sha256",
    "wall_time_utc",
}
JOB_GATE_KEYS: Final = {
    "child_creation_time",
    "child_pid",
    "launch_nonce",
    "supervisor_pid",
}


class LivenessFatalError(RuntimeError):
    """The durable heartbeat chain or frozen monotonic budget differs."""


def _fatal(message: str) -> Never:
    raise LivenessFatalError(message)


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
        raise LivenessFatalError(f"{field} is not ISO8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        _fatal(f"{field} must be timezone-aware UTC")
    return value


def _phase(value: object) -> str:
    if type(value) is not str or not value or len(value.encode("utf-8")) > 64:
        _fatal("heartbeat phase is invalid")
    if value in {CYCLE_START_PHASE, CYCLE_COMPLETE_PHASE}:
        return value
    if not value.startswith(PROGRESS_PHASE_PREFIX):
        _fatal("heartbeat phase is outside the cycle state machine")
    label = value.removeprefix(PROGRESS_PHASE_PREFIX)
    if not label or any(not (character.isascii() and (character.isalnum() or character == "_")) for character in label):
        _fatal("heartbeat progress phase is invalid")
    return value


@dataclass(frozen=True, slots=True)
class Heartbeat:
    raw: bytes
    sha256: str
    sequence: int
    monotonic_ns: int
    cycle_started_monotonic_ns: int
    phase: str


@dataclass(frozen=True, slots=True)
class JobGate:
    child_pid: int
    child_creation_time: float
    supervisor_pid: int


def _current_process_is_in_job() -> bool:
    if os.name != "nt":
        _fatal("v34 production containment requires Windows")
    import ctypes

    kernel32 = cast("Any", ctypes).WinDLL("kernel32", use_last_error=True)
    kernel32.GetCurrentProcess.argtypes = []
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.IsProcessInJob.argtypes = [
        wintypes.HANDLE,
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.BOOL),
    ]
    kernel32.IsProcessInJob.restype = wintypes.BOOL
    in_job = wintypes.BOOL()
    if not kernel32.IsProcessInJob(
        kernel32.GetCurrentProcess(),
        None,
        ctypes.byref(in_job),
    ):
        raise LivenessFatalError("child job membership cannot be queried") from ctypes.WinError(
            ctypes.get_last_error()
        )
    return bool(in_job.value)


def wait_for_job_gate(
    path: Path,
    *,
    launch_nonce: str,
    max_wait_ns: int = MAX_HEARTBEAT_AGE_NS,
) -> JobGate:
    """Block all observer work until the direct supervisor proves containment."""

    max_wait_ns = _exact_int(max_wait_ns, field="job gate wait", minimum=1)
    started = time.monotonic_ns()
    while True:
        try:
            raw = path.read_bytes()
        except FileNotFoundError:
            raw = b""
        except OSError as exc:
            raise LivenessFatalError("job gate cannot be read") from exc
        if raw:
            if len(raw) > MAX_HEARTBEAT_BYTES:
                _fatal("job gate exceeds its byte bound")
            try:
                parsed = json.loads(raw)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise LivenessFatalError("job gate JSON is invalid") from exc
            if (
                not isinstance(parsed, dict)
                or set(parsed) != JOB_GATE_KEYS
                or raw != policy.canonical_json_bytes(parsed)
            ):
                _fatal("job gate is not an exact canonical record")
            row = cast("dict[str, object]", parsed)
            child_pid = _exact_int(row.get("child_pid"), field="job gate child PID", minimum=1)
            supervisor_pid = _exact_int(
                row.get("supervisor_pid"),
                field="job gate supervisor PID",
                minimum=1,
            )
            child_creation_time = row.get("child_creation_time")
            if (
                type(child_creation_time) is not float
                or child_creation_time <= 0
                or row.get("launch_nonce") != launch_nonce
                or child_pid != os.getpid()
            ):
                _fatal("job gate identity differs")
            actual_creation = psutil.Process(child_pid).create_time()
            if abs(actual_creation - child_creation_time) > 0.01:
                _fatal("job gate child creation time differs")
            if not _current_process_is_in_job():
                _fatal("observer child is not contained by a Windows Job Object")
            return JobGate(
                child_pid=child_pid,
                child_creation_time=child_creation_time,
                supervisor_pid=supervisor_pid,
            )
        if time.monotonic_ns() - started > max_wait_ns:
            _fatal("job gate did not arrive inside the frozen liveness budget")
        time.sleep(0.05)


def _parse_heartbeat(
    raw: bytes,
    *,
    expected_sequence: int,
    expected_prior_sha256: str | None,
    launch_nonce: str,
    run_signature: str,
    child_pid: int,
    child_creation_time: float,
    source_sha256: str,
    policy_sha256: str,
) -> Heartbeat:
    if type(raw) is not bytes or not raw or len(raw) > MAX_HEARTBEAT_BYTES:
        _fatal("heartbeat exceeds its byte bound")
    try:
        parsed = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LivenessFatalError("heartbeat JSON is invalid") from exc
    if (
        not isinstance(parsed, dict)
        or set(parsed) != HEARTBEAT_KEYS
        or raw != policy.canonical_json_bytes(parsed)
    ):
        _fatal("heartbeat is not an exact canonical record")
    row = cast("dict[str, object]", parsed)
    sequence = _exact_int(row.get("sequence"), field="heartbeat.sequence", minimum=1)
    monotonic_ns = _exact_int(
        row.get("monotonic_ns"),
        field="heartbeat.monotonic_ns",
        minimum=1,
    )
    cycle_started = _exact_int(
        row.get("cycle_started_monotonic_ns"),
        field="heartbeat.cycle_started_monotonic_ns",
        minimum=1,
    )
    phase = _phase(row.get("phase"))
    if (
        sequence != expected_sequence
        or row.get("prior_heartbeat_sha256") != expected_prior_sha256
        or row.get("launch_nonce") != launch_nonce
        or row.get("run_signature") != run_signature
        or row.get("child_pid") != child_pid
        or row.get("child_creation_time") != child_creation_time
        or row.get("source_sha256") != source_sha256
        or row.get("policy_sha256") != policy_sha256
    ):
        _fatal("heartbeat identity or chain differs")
    _utc(row.get("wall_time_utc"), field="heartbeat.wall_time_utc")
    if cycle_started > monotonic_ns:
        _fatal("heartbeat cycle start is after its progress time")
    return Heartbeat(
        raw=raw,
        sha256=_sha256(raw),
        sequence=sequence,
        monotonic_ns=monotonic_ns,
        cycle_started_monotonic_ns=cycle_started,
        phase=phase,
    )


def _require_cycle_transition(
    previous: Heartbeat | None,
    current: Heartbeat,
) -> None:
    if previous is None:
        if (
            current.phase != CYCLE_START_PHASE
            or current.cycle_started_monotonic_ns != current.monotonic_ns
        ):
            _fatal("heartbeat chain must begin with an exact cycle start")
        return
    if current.monotonic_ns < previous.monotonic_ns:
        _fatal("heartbeat monotonic clock regressed")
    if previous.phase == CYCLE_COMPLETE_PHASE:
        if (
            current.phase != CYCLE_START_PHASE
            or current.cycle_started_monotonic_ns != current.monotonic_ns
            or current.monotonic_ns < previous.monotonic_ns
        ):
            _fatal("a completed cycle must be followed by an exact cycle start")
        return
    if current.phase == CYCLE_START_PHASE:
        _fatal("heartbeat cannot reset a cycle before durable completion")
    if current.cycle_started_monotonic_ns != previous.cycle_started_monotonic_ns:
        _fatal("heartbeat cycle start changed before durable completion")


class HeartbeatPublisher:
    """Sole writer for one fsynced append-only heartbeat chain."""

    def __init__(
        self,
        path: Path,
        *,
        launch_nonce: str,
        run_signature: str,
        child_pid: int,
        child_creation_time: float,
        source_sha256: str,
        policy_sha256: str,
    ) -> None:
        if not isinstance(path, Path) or not path.parent.is_dir():
            _fatal("heartbeat parent directory is missing")
        for name, value in (
            ("launch nonce", launch_nonce),
            ("run signature", run_signature),
            ("source SHA256", source_sha256),
            ("policy SHA256", policy_sha256),
        ):
            if type(value) is not str or not value:
                _fatal(f"heartbeat {name} is empty")
        policy.validate_sha256(source_sha256, field="heartbeat.source_sha256")
        policy.validate_sha256(policy_sha256, field="heartbeat.policy_sha256")
        self.path = path
        self.launch_nonce = launch_nonce
        self.run_signature = run_signature
        self.child_pid = _exact_int(child_pid, field="heartbeat.child_pid", minimum=1)
        if type(child_creation_time) is not float or child_creation_time <= 0:
            _fatal("heartbeat child creation time is invalid")
        self.child_creation_time = child_creation_time
        self.source_sha256 = source_sha256
        self.policy_sha256 = policy_sha256
        self._sequence = 0
        self._prior_sha256: str | None = None
        self._last_monotonic_ns: int | None = None
        self._last_cycle_started_ns: int | None = None
        self._last_heartbeat: Heartbeat | None = None
        self._file_size = 0
        self._descriptor: int | None = None
        try:
            self._descriptor = os.open(
                path,
                os.O_CREAT | os.O_EXCL | os.O_RDWR | getattr(os, "O_BINARY", 0),
                0o600,
            )
        except OSError as exc:
            raise LivenessFatalError("heartbeat path is not fresh") from exc
        opened = os.fstat(self._descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
            or opened.st_size != 0
        ):
            os.close(self._descriptor)
            self._descriptor = None
            _fatal("fresh heartbeat descriptor identity differs")
        self._identity = (opened.st_dev, opened.st_ino)
        self._require_exact_file()
        feed_archive._fsync_directory(path.parent)

    def _require_exact_file(self) -> int:
        descriptor = self._descriptor
        if descriptor is None:
            _fatal("heartbeat publisher is closed")
        try:
            opened = os.fstat(descriptor)
            linked = self.path.lstat()
        except OSError as exc:
            raise LivenessFatalError("heartbeat identity cannot be read") from exc
        if (
            stat.S_ISLNK(linked.st_mode)
            or not stat.S_ISREG(opened.st_mode)
            or not stat.S_ISREG(linked.st_mode)
            or opened.st_nlink != 1
            or linked.st_nlink != 1
            or (opened.st_dev, opened.st_ino) != self._identity
            or (linked.st_dev, linked.st_ino) != self._identity
            or opened.st_size != self._file_size
            or linked.st_size != self._file_size
        ):
            _fatal("heartbeat path or descriptor identity differs")
        return descriptor

    def publish(
        self,
        phase: str,
        *,
        cycle_started_monotonic_ns: int,
        monotonic_ns: int | None = None,
        wall_time_utc: str | None = None,
    ) -> Heartbeat:
        now_ns = time.monotonic_ns() if monotonic_ns is None else monotonic_ns
        cycle_started = _exact_int(
            cycle_started_monotonic_ns,
            field="heartbeat.cycle_started_monotonic_ns",
            minimum=1,
        )
        now_ns = _exact_int(now_ns, field="heartbeat.monotonic_ns", minimum=1)
        if self._last_monotonic_ns is not None and now_ns < self._last_monotonic_ns:
            _fatal("heartbeat monotonic clock regressed")
        if (
            self._last_cycle_started_ns is not None
            and cycle_started < self._last_cycle_started_ns
        ):
            _fatal("heartbeat cycle start regressed")
        if now_ns - cycle_started > MAX_CYCLE_NS:
            _fatal("heartbeat cannot publish after the full cycle deadline")
        raw = policy.canonical_json_bytes(
            {
                "child_creation_time": self.child_creation_time,
                "child_pid": self.child_pid,
                "cycle_started_monotonic_ns": cycle_started,
                "launch_nonce": self.launch_nonce,
                "monotonic_ns": now_ns,
                "phase": phase,
                "policy_sha256": self.policy_sha256,
                "prior_heartbeat_sha256": self._prior_sha256,
                "run_signature": self.run_signature,
                "sequence": self._sequence + 1,
                "source_sha256": self.source_sha256,
                "wall_time_utc": (
                    datetime.now(tz=UTC).isoformat()
                    if wall_time_utc is None
                    else wall_time_utc
                ),
            }
        )
        heartbeat = _parse_heartbeat(
            raw,
            expected_sequence=self._sequence + 1,
            expected_prior_sha256=self._prior_sha256,
            launch_nonce=self.launch_nonce,
            run_signature=self.run_signature,
            child_pid=self.child_pid,
            child_creation_time=self.child_creation_time,
            source_sha256=self.source_sha256,
            policy_sha256=self.policy_sha256,
        )
        _require_cycle_transition(self._last_heartbeat, heartbeat)
        descriptor = self._require_exact_file()
        if os.lseek(descriptor, 0, os.SEEK_END) != self._file_size:
            _fatal("heartbeat append offset differs")
        payload = raw + b"\n"
        if os.write(descriptor, payload) != len(payload):
            _fatal("heartbeat append was incomplete")
        os.fsync(descriptor)
        self._file_size += len(payload)
        self._require_exact_file()
        self._sequence = heartbeat.sequence
        self._prior_sha256 = heartbeat.sha256
        self._last_monotonic_ns = heartbeat.monotonic_ns
        self._last_cycle_started_ns = heartbeat.cycle_started_monotonic_ns
        self._last_heartbeat = heartbeat
        return heartbeat

    def close(self) -> None:
        descriptor = self._descriptor
        if descriptor is None:
            return
        os.close(descriptor)
        self._descriptor = None

    def __enter__(self) -> HeartbeatPublisher:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()


class HeartbeatReader:
    """Incrementally verify each durable heartbeat exactly once."""

    def __init__(
        self,
        path: Path,
        *,
        launch_nonce: str,
        run_signature: str,
        child_pid: int,
        child_creation_time: float,
        source_sha256: str,
        policy_sha256: str,
    ) -> None:
        self.path = path
        self.launch_nonce = launch_nonce
        self.run_signature = run_signature
        self.child_pid = child_pid
        self.child_creation_time = child_creation_time
        self.source_sha256 = source_sha256
        self.policy_sha256 = policy_sha256
        self._offset = 0
        self._sequence = 0
        self._prior_sha256: str | None = None
        self.latest: Heartbeat | None = None
        self._identity: tuple[int, int] | None = None

    def _read_growth(self) -> bytes:
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
        try:
            descriptor = os.open(self.path, flags)
        except OSError as exc:
            raise LivenessFatalError("heartbeat path cannot be read") from exc
        try:
            opened = os.fstat(descriptor)
            linked = self.path.lstat()
            identity = (opened.st_dev, opened.st_ino)
            if self._identity is None:
                self._identity = identity
            remaining = opened.st_size - self._offset
            if (
                stat.S_ISLNK(linked.st_mode)
                or not stat.S_ISREG(opened.st_mode)
                or not stat.S_ISREG(linked.st_mode)
                or opened.st_nlink != 1
                or linked.st_nlink != 1
                or identity != self._identity
                or (linked.st_dev, linked.st_ino) != self._identity
                or linked.st_size != opened.st_size
                or remaining < 0
                or remaining > MAX_HEARTBEAT_POLL_BYTES
            ):
                _fatal("heartbeat reader identity or growth differs")
            if os.lseek(descriptor, self._offset, os.SEEK_SET) != self._offset:
                _fatal("heartbeat read offset differs")
            chunk = os.read(descriptor, remaining + 1)
            if len(chunk) != remaining:
                _fatal("heartbeat growth changed during read")
            final = os.fstat(descriptor)
            final_linked = self.path.lstat()
            if (
                (final.st_dev, final.st_ino) != self._identity
                or final.st_size != opened.st_size
                or stat.S_ISLNK(final_linked.st_mode)
                or (final_linked.st_dev, final_linked.st_ino) != self._identity
                or final_linked.st_size != opened.st_size
            ):
                _fatal("heartbeat changed during read")
            return chunk
        finally:
            os.close(descriptor)

    def poll(self) -> Heartbeat:
        chunk = self._read_growth()
        if chunk and not chunk.endswith(b"\n"):
            _fatal("heartbeat chain has a partial terminal record")
        for line in chunk.splitlines():
            heartbeat = _parse_heartbeat(
                line,
                expected_sequence=self._sequence + 1,
                expected_prior_sha256=self._prior_sha256,
                launch_nonce=self.launch_nonce,
                run_signature=self.run_signature,
                child_pid=self.child_pid,
                child_creation_time=self.child_creation_time,
                source_sha256=self.source_sha256,
                policy_sha256=self.policy_sha256,
            )
            _require_cycle_transition(self.latest, heartbeat)
            self.latest = heartbeat
            self._sequence = heartbeat.sequence
            self._prior_sha256 = heartbeat.sha256
            self._offset += len(line) + 1
        if self.latest is None:
            _fatal("heartbeat chain is empty")
        return self.latest

    def require_exact_initial_empty(self) -> None:
        """Admit only the publisher's fresh zero-byte file before heartbeat one."""

        if (
            self.latest is not None
            or self._offset != 0
            or self._sequence != 0
            or self._prior_sha256 is not None
        ):
            _fatal("heartbeat reader is not awaiting its first record")
        if self._read_growth():
            _fatal("initial heartbeat file is not empty")

    def require_live(self, *, monotonic_ns: int | None = None) -> Heartbeat:
        heartbeat = self.poll()
        now_ns = time.monotonic_ns() if monotonic_ns is None else monotonic_ns
        if now_ns < heartbeat.monotonic_ns:
            _fatal("supervisor monotonic clock precedes the child heartbeat")
        if now_ns - heartbeat.monotonic_ns > MAX_HEARTBEAT_AGE_NS:
            _fatal("progress heartbeat is stale")
        if now_ns - heartbeat.cycle_started_monotonic_ns > MAX_CYCLE_NS:
            _fatal("observer cycle exceeded the full deadline")
        return heartbeat
