"""Tests for the single-instance lock on the live bot."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

import psutil
import pytest

from kalshi_bot.strategy.single_instance import (
    LockState,
    _is_lock_alive,
    _read_lock,
    acquire_live_lock,
    release_live_lock,
)


@pytest.fixture
def tmp_lock_paths(tmp_path: Path) -> tuple[Path, Path]:
    return tmp_path / "bot.lock", tmp_path / "bot.pid"


def test_acquire_lock_when_no_existing_lock(tmp_lock_paths) -> None:
    """First-time acquire writes both files; no SystemExit."""
    lock_path, pid_path = tmp_lock_paths
    acquire_live_lock(lock_path, pid_path)
    assert lock_path.exists()
    assert pid_path.exists()
    data = json.loads(lock_path.read_text())
    assert data["pid"] == os.getpid()
    assert int(pid_path.read_text()) == os.getpid()


def test_acquire_lock_when_stale_lock_present(tmp_lock_paths) -> None:
    """A lock file pointing at a dead PID should be overwritten,
    not block the new instance."""
    lock_path, pid_path = tmp_lock_paths
    # Write a lock with a definitely-dead PID (very high number).
    stale = {
        "pid": 999999,
        "process_name": "python.exe",
        "start_time_iso": datetime.now(UTC).isoformat(),
    }
    lock_path.write_text(json.dumps(stale))
    # Should NOT raise.
    acquire_live_lock(lock_path, pid_path)
    # Lock should now reference our PID.
    data = json.loads(lock_path.read_text())
    assert data["pid"] == os.getpid()


def test_acquire_lock_when_live_other_instance(tmp_lock_paths, monkeypatch) -> None:
    """If the lock points at a live python process (we use our own PID
    pretending to be 'another instance'), refuse to start."""
    lock_path, pid_path = tmp_lock_paths
    other_pid = os.getpid()  # we are alive, so we count as 'other'
    me = psutil.Process(other_pid)
    payload = {
        "pid": other_pid,
        "process_name": me.name(),
        "start_time_iso": datetime.fromtimestamp(me.create_time(), tz=UTC).isoformat(),
    }
    lock_path.write_text(json.dumps(payload))
    # We call acquire_live_lock pretending to be a NEW process (different PID).
    # Use a PID that definitely isn't ours; even though the lock holder
    # is our own PID, the new instance should still refuse.
    fake_new_pid = 12345
    with pytest.raises(SystemExit) as exc_info:
        acquire_live_lock(lock_path, pid_path, pid=fake_new_pid)
    assert "REFUSING TO START" in str(exc_info.value)


def test_acquire_lock_handles_pid_recycle(tmp_lock_paths) -> None:
    """If the lock file points at a PID that's been recycled into a
    non-python process (start_time doesn't match), the lock is stale."""
    lock_path, pid_path = tmp_lock_paths
    # Use a PID that exists but with a fake start time far in the past
    # so the start-time match check fails -> treated as stale.
    payload = {
        "pid": os.getpid(),  # alive
        "process_name": "python.exe",
        "start_time_iso": "2020-01-01T00:00:00+00:00",  # absurdly old
    }
    lock_path.write_text(json.dumps(payload))
    # Should treat as stale and NOT refuse.
    acquire_live_lock(lock_path, pid_path)


def test_acquire_lock_handles_legacy_plain_int_format(tmp_lock_paths) -> None:
    """Old bot.pid files were plain integers, no JSON. Reader must
    tolerate that format (treat as 'PID only, unverifiable')."""
    lock_path, pid_path = tmp_lock_paths
    lock_path.write_text("999999")  # plain int, dead PID
    # Should be treated as stale (PID 999999 doesn't exist).
    acquire_live_lock(lock_path, pid_path)


def test_release_lock_only_when_owned(tmp_lock_paths) -> None:
    """release_live_lock removes the files only if the lock PID
    matches us. If the lock was taken by someone else, leave it."""
    lock_path, pid_path = tmp_lock_paths
    foreign = {
        "pid": 99998,
        "process_name": "python.exe",
        "start_time_iso": datetime.now(UTC).isoformat(),
    }
    lock_path.write_text(json.dumps(foreign))
    pid_path.write_text("99998")
    # Try to release as ourselves (different PID).
    release_live_lock(lock_path, pid_path)
    # Files should still exist; we don't own the lock.
    assert lock_path.exists()
    assert pid_path.exists()


def test_release_lock_removes_when_owned(tmp_lock_paths) -> None:
    lock_path, pid_path = tmp_lock_paths
    acquire_live_lock(lock_path, pid_path)
    assert lock_path.exists()
    release_live_lock(lock_path, pid_path)
    assert not lock_path.exists()
    assert not pid_path.exists()


def test_read_lock_missing_file_returns_none(tmp_path: Path) -> None:
    assert _read_lock(tmp_path / "does_not_exist") is None


def test_read_lock_malformed_returns_none(tmp_path: Path) -> None:
    f = tmp_path / "bot.lock"
    f.write_text("{this is not valid JSON")
    # Falls through to int parse, also fails, returns None.
    assert _read_lock(f) is None


def test_is_lock_alive_dead_pid_returns_false() -> None:
    """A clearly-dead PID should not be reported as alive."""
    lock = LockState(pid=999999, process_name="python.exe", start_time_iso="")
    assert _is_lock_alive(lock) is False


def test_is_lock_alive_zero_pid_returns_false() -> None:
    lock = LockState(pid=0, process_name="python.exe", start_time_iso="")
    assert _is_lock_alive(lock) is False


def test_acquire_lock_creates_parent_directory(tmp_path: Path) -> None:
    """If the parent of the lock path doesn't exist, acquire creates it."""
    lock = tmp_path / "deep" / "nested" / "bot.lock"
    pid = tmp_path / "deep" / "nested" / "bot.pid"
    acquire_live_lock(lock, pid)
    assert lock.exists()
    assert pid.exists()
