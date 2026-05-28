"""Cross-platform single-instance lock for the live bot.

Refuses to start if another bot process is alive. The PID file at
data/live_trades/bot.pid records (pid, process_name, start_time_iso).
On startup the lock checks whether that PID is still alive and whether
it's actually a python/uv process started near the recorded time. If
yes, the new instance refuses to start. If the PID is dead or recycled
into an unrelated process, the lock is treated as stale and overwritten.

This is the LAST line of defense against the supervisor-launches-twice
bug. Even if Task Scheduler, the supervisor script, and restart_bot.ps1
all fail to prevent a double-launch, this check ensures only one bot
process ever places real orders.

Usage:
    from kalshi_bot.strategy.single_instance import acquire_live_lock

    # In main() before any trading logic:
    acquire_live_lock()  # raises SystemExit if another bot is running
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import psutil
import structlog

log = structlog.get_logger(__name__)

# Default paths; can be overridden for tests.
# bot.lock is the authoritative single-instance lock (JSON payload).
# bot.pid is a plain-int companion file used by existing readers
# (run_live_bot.ps1, restart_bot.ps1, dashboard.py). Both written
# together; only bot.lock is checked for ownership / mutex.
DEFAULT_LOCK_PATH = Path("data/live_trades/bot.lock")
DEFAULT_PID_PATH = Path("data/live_trades/bot.pid")

# Process names that count as "the bot" when verifying a held lock.
# python.exe is the obvious one; uv.exe is the wrapper. We accept
# either to be safe; in practice the lock holder is python.
_BOT_PROCESS_NAMES = frozenset({
    "python.exe", "python", "uv.exe", "uv",
})

# Tolerance for matching the recorded start time against the live
# process's actual start time. If the PID was recycled into an
# unrelated process, its create_time will not match.
_START_TIME_MATCH_TOLERANCE_S = 2.0


@dataclass(frozen=True)
class LockState:
    """Parsed contents of the PID file."""
    pid: int
    process_name: str
    start_time_iso: str


def _read_lock(path: Path) -> LockState | None:
    """Read and parse the PID file. Returns None on any failure
    (missing file, malformed, partial write)."""
    try:
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            return None
        # Two formats supported: legacy plain-int PID, or JSON dict.
        # Note: json.loads("12345") yields the int 12345, so we must
        # explicitly check for a dict before treating it as JSON-shaped.
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = None
        if isinstance(data, dict):
            return LockState(
                pid=int(data.get("pid", 0)),
                process_name=str(data.get("process_name", "")),
                start_time_iso=str(data.get("start_time_iso", "")),
            )
        # Legacy plain-int format (or JSON that parsed to a bare int).
        try:
            return LockState(pid=int(text), process_name="", start_time_iso="")
        except (TypeError, ValueError):
            return None
    except OSError:
        return None


def _is_lock_alive(lock: LockState) -> bool:
    """True if the recorded PID points to a still-running process that
    matches the recorded process_name and start_time. False if PID is
    dead, recycled, or unverifiable."""
    if lock.pid <= 0:
        return False
    try:
        proc = psutil.Process(lock.pid)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False
    try:
        name = proc.name().lower()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False
    if name not in _BOT_PROCESS_NAMES:
        # PID was recycled into something unrelated.
        return False
    if lock.start_time_iso:
        try:
            recorded = datetime.fromisoformat(lock.start_time_iso)
            actual = datetime.fromtimestamp(proc.create_time(), tz=UTC)
            delta = abs((actual - recorded).total_seconds())
            if delta > _START_TIME_MATCH_TOLERANCE_S:
                # PID was recycled into an unrelated process that
                # happens to be python.
                return False
        except (ValueError, psutil.NoSuchProcess, psutil.AccessDenied):
            # If we can't verify start time, fall through to "alive"
            # which errs on the side of refusing to launch.
            pass
    return True


def acquire_live_lock(
    lock_path: Path = DEFAULT_LOCK_PATH,
    pid_path: Path = DEFAULT_PID_PATH,
    *,
    pid: int | None = None,
) -> None:
    """Acquire the single-instance lock.

    Raises SystemExit if another bot process is currently alive.
    Otherwise writes a fresh lock file (JSON) with this process's PID,
    name, and start time, AND a companion plain-int pid file for
    legacy readers (run_live_bot.ps1, restart_bot.ps1, dashboard.py).

    Args:
        lock_path: JSON lock file location. Default data/live_trades/bot.lock.
        pid_path: Plain-int companion. Default data/live_trades/bot.pid.
        pid: Override the PID written (for tests). Defaults to os.getpid().
    """
    if pid is None:
        pid = os.getpid()
    existing = _read_lock(lock_path)
    if existing is not None and _is_lock_alive(existing):
        raise SystemExit(
            f"REFUSING TO START: another bot instance is already running "
            f"(PID {existing.pid}, name={existing.process_name}, "
            f"started {existing.start_time_iso}). "
            f"Stop it first or wait for it to exit."
        )
    # Take ownership.
    try:
        me = psutil.Process(pid)
        start_dt = datetime.fromtimestamp(me.create_time(), tz=UTC).isoformat()
        process_name = me.name()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        start_dt = datetime.now(UTC).isoformat()
        process_name = "python"
    payload = json.dumps({
        "pid": pid,
        "process_name": process_name,
        "start_time_iso": start_dt,
    })
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(payload, encoding="utf-8")
    # Companion plain-int file for existing readers. Same atomicity
    # caveats; both files are appended sequentially without locking.
    pid_path.parent.mkdir(parents=True, exist_ok=True)
    pid_path.write_text(str(pid), encoding="utf-8")
    log.info("live_lock_acquired", pid=pid, lock_path=str(lock_path))


def release_live_lock(
    lock_path: Path = DEFAULT_LOCK_PATH,
    pid_path: Path = DEFAULT_PID_PATH,
    *,
    pid: int | None = None,
) -> None:
    """Release the lock by removing both the JSON lock file and the
    plain-int companion, but only if we own them.

    Owning means the lock file's recorded PID matches the current
    process. This prevents a second instance from accidentally
    deleting another bot's lock if the SystemExit on acquire_live_lock
    was somehow caught or bypassed.
    """
    if pid is None:
        pid = os.getpid()
    existing = _read_lock(lock_path)
    if existing is None or existing.pid != pid:
        return
    for p in (lock_path, pid_path):
        try:
            p.unlink()
        except OSError:
            pass
