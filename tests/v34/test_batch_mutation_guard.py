from __future__ import annotations

import os
import time
from importlib.metadata import version

import pytest
from scripts.v34 import batch_mutation_guard as guard_module
from watchdog.observers import winapi as watchdog_winapi

if os.name != "nt":
    pytest.skip("Windows custody watcher only", allow_module_level=True)


def guard(tmp_path: pytest.TempPathFactory) -> guard_module.BatchMutationGuard:
    roots = tuple(tmp_path.mktemp(name) for name in ("custody", "primary", "source"))
    return guard_module.BatchMutationGuard(roots)


def test_expected_publication_then_quiet_external_change_fails(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    candidate = guard(tmp_path_factory)
    expected = candidate._roots[0] / "000000000001-test"
    candidate.expect((expected,))
    expected.mkdir()
    (expected / "prepare.json").write_bytes(b"prepare")
    candidate.settle_expected()
    (expected / "prepare.json").write_bytes(b"changed")
    time.sleep(0.2)
    with pytest.raises(
        guard_module.BatchMutationGuardError,
        match="unexpected batch tree",
    ):
        candidate.require_quiet()
    candidate.close()


def test_revalidation_read_is_quiet_and_last_access_is_not_subscribed(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    candidate = guard(tmp_path_factory)
    expected = candidate._roots[0] / "000000000001-test"
    candidate.expect((expected,))
    expected.mkdir()
    record = expected / "prepare.json"
    record.write_bytes(b"prepare")
    candidate.settle_expected()
    assert record.read_bytes() == b"prepare"
    time.sleep(0.2)
    candidate.require_quiet()
    assert (
        watchdog_winapi.WATCHDOG_FILE_NOTIFY_FLAGS
        & watchdog_winapi.FILE_NOTIFY_CHANGE_LAST_ACCESS
        == 0
    )
    candidate.close()


def test_runtime_watchdog_version_is_exactly_frozen() -> None:
    assert version("watchdog") == guard_module.REQUIRED_WATCHDOG_VERSION


def test_dead_emitter_is_terminal(tmp_path_factory: pytest.TempPathFactory) -> None:
    candidate = guard(tmp_path_factory)
    emitter = next(iter(candidate._observer.emitters))
    emitter.stop()
    emitter.join(timeout=1.0)
    with pytest.raises(
        guard_module.BatchMutationGuardError,
        match="not alive",
    ):
        candidate.require_quiet()
    candidate.close()


def test_kernel_overflow_signal_is_terminal(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    candidate = guard(tmp_path_factory)
    candidate._health.mark_overflow()
    with pytest.raises(
        guard_module.BatchMutationGuardError,
        match="kernel notification buffer overflowed",
    ):
        candidate.require_quiet()
    candidate.close()


def test_python_event_buffer_overflow_is_terminal(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    candidate = guard(tmp_path_factory)
    candidate._handler._overflow = True
    with pytest.raises(
        guard_module.BatchMutationGuardError,
        match="event buffer overflowed",
    ):
        candidate.require_quiet()
    candidate.close()
