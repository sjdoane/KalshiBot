"""Bounded Windows directory-change custody guard for a live batch session."""

from __future__ import annotations

import os
import threading
import time
from collections import deque
from contextlib import suppress
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import TYPE_CHECKING, Final

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import winapi as watchdog_winapi
from watchdog.observers.api import (
    DEFAULT_EMITTER_TIMEOUT,
    BaseObserver,
    EventEmitter,
    EventQueue,
    ObservedWatch,
)
from watchdog.observers.read_directory_changes import WindowsApiEmitter

if TYPE_CHECKING:
    from watchdog.observers.winapi import WinAPINativeEvent

MAX_PENDING_EVENTS: Final = 16_384
STARTUP_WAIT_SECONDS: Final = 1.0
SETTLE_QUIET_SECONDS: Final = 0.05
SETTLE_MAX_SECONDS: Final = 1.0
REQUIRED_WATCHDOG_VERSION: Final = "6.0.0"
ORIGINAL_NOTIFY_FLAGS: Final = watchdog_winapi.WATCHDOG_FILE_NOTIFY_FLAGS
REQUIRED_NOTIFY_FLAGS: Final = (
    ORIGINAL_NOTIFY_FLAGS & ~watchdog_winapi.FILE_NOTIFY_CHANGE_LAST_ACCESS
)


class BatchMutationGuardError(RuntimeError):
    """A watched batch tree changed outside the sole expected transaction."""


class _EmitterHealth:
    def __init__(self) -> None:
        self._overflow = False
        self._lock = threading.Lock()

    def mark_overflow(self) -> None:
        with self._lock:
            self._overflow = True

    def overflowed(self) -> bool:
        with self._lock:
            return self._overflow


class _OverflowAwareWindowsApiEmitter(WindowsApiEmitter):
    def __init__(
        self,
        event_queue: EventQueue,
        watch: ObservedWatch,
        *,
        health: _EmitterHealth,
        timeout: float = DEFAULT_EMITTER_TIMEOUT,
        event_filter: list[type[FileSystemEvent]] | None = None,
    ) -> None:
        super().__init__(
            event_queue,
            watch,
            timeout=timeout,
            event_filter=event_filter,
        )
        self._health = health

    def _read_events(self) -> list[WinAPINativeEvent]:
        events = super()._read_events()
        if not events and self.should_keep_running():
            self._health.mark_overflow()
            self.stop()
        return events


def _bound_emitter_class(health: _EmitterHealth) -> type[EventEmitter]:
    class BoundOverflowAwareWindowsApiEmitter(_OverflowAwareWindowsApiEmitter):
        def __init__(
            self,
            event_queue: EventQueue,
            watch: ObservedWatch,
            *,
            timeout: float = DEFAULT_EMITTER_TIMEOUT,
            event_filter: list[type[FileSystemEvent]] | None = None,
        ) -> None:
            super().__init__(
                event_queue,
                watch,
                health=health,
                timeout=timeout,
                event_filter=event_filter,
            )

    return BoundOverflowAwareWindowsApiEmitter


class _BoundedHandler(FileSystemEventHandler):
    def __init__(self, roots: tuple[Path, ...]) -> None:
        super().__init__()
        self._roots = roots
        self._events: deque[tuple[str, str, str | None]] = deque()
        self._overflow = False
        self._lock = threading.Lock()

    def on_any_event(self, event: FileSystemEvent) -> None:
        event_type = str(event.event_type)
        if event_type in {"opened", "closed", "closed_no_write"}:
            return
        source = os.path.normcase(os.path.abspath(str(event.src_path)))  # noqa: PTH100
        destination_value = getattr(event, "dest_path", None)
        destination = (
            None
            if destination_value in {None, ""}
            else os.path.normcase(  # noqa: PTH100
                os.path.abspath(str(destination_value))  # noqa: PTH100
            )
        )
        if Path(source).name.endswith(".v34append.lock") and (
            destination is None
            or Path(destination).name.endswith(".v34append.lock")
        ):
            return
        with self._lock:
            if len(self._events) >= MAX_PENDING_EVENTS:
                self._overflow = True
                return
            self._events.append((event_type, source, destination))

    def drain(self) -> tuple[bool, tuple[tuple[str, str, str | None], ...]]:
        with self._lock:
            overflow = self._overflow
            self._overflow = False
            events = tuple(self._events)
            self._events.clear()
        return overflow, events


class BatchMutationGuard:
    """Watch both batch mirrors and allow changes only in one pending batch."""

    def __init__(self, roots: tuple[Path, ...]) -> None:
        if os.name != "nt":
            raise BatchMutationGuardError(
                "production batch mutation guard requires Windows"
            )
        try:
            installed_watchdog_version = version("watchdog")
        except PackageNotFoundError as exc:
            raise BatchMutationGuardError("watchdog is not installed") from exc
        if installed_watchdog_version != REQUIRED_WATCHDOG_VERSION:
            raise BatchMutationGuardError(
                "watchdog runtime version differs from the frozen dependency"
            )
        if watchdog_winapi.WATCHDOG_FILE_NOTIFY_FLAGS not in {
            ORIGINAL_NOTIFY_FLAGS,
            REQUIRED_NOTIFY_FLAGS,
        }:
            raise BatchMutationGuardError(
                "watchdog Windows notification mask was changed externally"
            )
        watchdog_winapi.WATCHDOG_FILE_NOTIFY_FLAGS = REQUIRED_NOTIFY_FLAGS
        canonical_roots = tuple(root.resolve(strict=True) for root in roots)
        if len(canonical_roots) < 2 or len(set(canonical_roots)) != len(
            canonical_roots
        ):
            raise BatchMutationGuardError("batch mutation guard roots alias")
        self._roots = canonical_roots
        self._handler = _BoundedHandler(canonical_roots)
        self._health = _EmitterHealth()
        self._observer = BaseObserver(_bound_emitter_class(self._health))
        self._expected_paths: tuple[Path, ...] | None = None
        self._closed = False
        for root in canonical_roots:
            self._observer.schedule(self._handler, str(root), recursive=True)
        try:
            self._observer.start()
        except Exception as exc:
            self._stop_threads()
            self._closed = True
            raise BatchMutationGuardError(
                "batch mutation guard observer failed during startup"
            ) from exc
        deadline = time.monotonic() + STARTUP_WAIT_SECONDS
        while not self._observer.is_alive():
            if time.monotonic() >= deadline:
                self.close()
                raise BatchMutationGuardError("batch mutation guard did not start")
            time.sleep(0.01)
        self._assert_alive()
        self._drain_and_validate()

    def _stop_threads(self) -> None:
        emitters = tuple(self._observer.emitters)
        for emitter in emitters:
            emitter.stop()
        for emitter in emitters:
            with suppress(RuntimeError):
                emitter.join(timeout=5.0)
        if self._observer.is_alive():
            self._observer.stop()
            self._observer.join(timeout=5.0)

    def _path_is_expected(self, raw_path: str) -> bool:
        path = Path(raw_path)
        for root in self._roots:
            try:
                relative = path.relative_to(root)
            except ValueError:
                continue
            if relative == Path():
                return self._expected_paths is not None
            if self._expected_paths is None:
                return False
            return any(
                path == expected
                or expected in path.parents
                or path in expected.parents
                or (
                    path.parent == expected.parent
                    and path.name.startswith(f".{expected.name}.v34tmp-")
                    and path.name.endswith(".tmp")
                )
                for expected in self._expected_paths
            )
        return False

    def _assert_alive(self) -> None:
        if watchdog_winapi.WATCHDOG_FILE_NOTIFY_FLAGS != REQUIRED_NOTIFY_FLAGS:
            raise BatchMutationGuardError(
                "watchdog Windows notification mask changed during custody"
            )
        emitters = tuple(self._observer.emitters)
        if (
            self._closed
            or not self._observer.is_alive()
            or len(emitters) != len(self._roots)
            or any(not emitter.is_alive() for emitter in emitters)
        ):
            raise BatchMutationGuardError("batch mutation guard is not alive")
        if self._health.overflowed():
            raise BatchMutationGuardError(
                "batch mutation kernel notification buffer overflowed"
            )

    def _drain_and_validate(self) -> int:
        self._assert_alive()
        overflow, events = self._handler.drain()
        if overflow:
            raise BatchMutationGuardError("batch mutation event buffer overflowed")
        for event_type, source, destination in events:
            if not self._path_is_expected(source) or (
                destination is not None and not self._path_is_expected(destination)
            ):
                raise BatchMutationGuardError(
                    f"unexpected batch tree {event_type} at {source}"
                )
        return len(events)

    def check_and_clear(self) -> None:
        """Validate delayed prior events, then require a quiet tree."""

        self._drain_and_validate()
        self._expected_paths = None
        self._drain_and_validate()

    def require_quiet(self) -> None:
        """Require a live watcher and one bounded event-free interval."""

        if self._expected_paths is not None:
            raise BatchMutationGuardError("batch mutation expectation is active")
        deadline = time.monotonic() + SETTLE_MAX_SECONDS
        quiet_started = time.monotonic()
        while True:
            observed = self._drain_and_validate()
            now = time.monotonic()
            if observed:
                quiet_started = now
            if now - quiet_started >= SETTLE_QUIET_SECONDS:
                return
            if now >= deadline:
                raise BatchMutationGuardError("batch mutation events did not quiet")
            time.sleep(0.01)

    def expect(self, expected_paths: tuple[Path, ...]) -> None:
        if self._expected_paths is not None:
            raise BatchMutationGuardError("batch mutation expectation is already active")
        if type(expected_paths) is not tuple or not expected_paths:
            raise BatchMutationGuardError("batch mutation expectation is invalid")
        canonical_paths = tuple(
            expected.resolve(strict=False) for expected in expected_paths
        )
        if len(set(canonical_paths)) != len(canonical_paths):
            raise BatchMutationGuardError("batch mutation expectation is duplicated")
        for expected in canonical_paths:
            containing_roots = tuple(
                root for root in self._roots if root in expected.parents
            )
            if len(containing_roots) != 1:
                raise BatchMutationGuardError(
                    "batch mutation expectation is outside one watched root"
                )
        self._drain_and_validate()
        self._expected_paths = canonical_paths

    def settle_expected(self) -> None:
        """Drain expected events through one bounded quiet interval."""

        if self._expected_paths is None:
            raise BatchMutationGuardError("batch mutation expectation is absent")
        deadline = time.monotonic() + SETTLE_MAX_SECONDS
        quiet_started = time.monotonic()
        while True:
            observed = self._drain_and_validate()
            now = time.monotonic()
            if observed:
                quiet_started = now
            if now - quiet_started >= SETTLE_QUIET_SECONDS:
                self._expected_paths = None
                self._drain_and_validate()
                return
            if now >= deadline:
                raise BatchMutationGuardError("batch mutation events did not settle")
            time.sleep(0.01)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._stop_threads()

    def __enter__(self) -> BatchMutationGuard:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def __del__(self) -> None:
        with suppress(Exception):
            self.close()
