from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from contextlib import suppress
from dataclasses import replace
from pathlib import Path

import psutil
import pytest
from scripts.v34 import observer_supervisor, policy, runtime_liveness

LAUNCH_NONCE = "test-launch"
RUN_SIGNATURE = "test-run"
SOURCE_SHA256 = hashlib.sha256(
    (policy.REPOSITORY_ROOT / "scripts/v34/feed_observer.py").read_bytes()
).hexdigest()
POLICY_SHA256 = policy.POLICY_CANONICAL_SHA256


@pytest.fixture(autouse=True)
def _isolate_primary_policy_feed_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lock_root = tmp_path / "launch-locks"
    lock_root.mkdir()
    monkeypatch.setattr(
        observer_supervisor,
        "_locked_feed_lock_paths",
        lambda: (lock_root / ".prospective-feed-v34-lock1.lock",),
    )


def _terminal_custody(
    tmp_path: Path,
    heartbeat_path: Path,
) -> tuple[observer_supervisor.FeedTerminalCustodySpec, Path]:
    owned_lock_paths = observer_supervisor._locked_feed_lock_paths()
    owned_lock_roots = tuple(sorted({path.parent for path in owned_lock_paths}))
    ledger_custody = tmp_path / "fixture-ledger-custody"
    ledger_runtime = tmp_path / "fixture-ledger-runtime"
    ledger_custody.mkdir()
    ledger_runtime.mkdir()
    ledger_roots = {
        "custody_control": ledger_custody / "control",
        "custody_source": ledger_custody / "source-archive",
        "runtime_control": ledger_runtime / "control",
        "runtime_games": ledger_runtime / "games",
    }
    completion_receipt_path = tmp_path / "completion.receipt.json"
    stop_sentinel_path = tmp_path / "stop.json"
    terminal_manifest_path = tmp_path / "terminal-manifest.json"
    artifact_paths = {
        "completion_receipt": completion_receipt_path,
        "heartbeat": heartbeat_path,
        "public_receipt": tmp_path / "summary.receipt.json",
        "public_summary": tmp_path / "summary.json",
        "schedule_snapshot": tmp_path / "schedule.json",
        "stop_sentinel": stop_sentinel_path,
        "terminal_event_log": tmp_path / "terminal-event-log.json",
        "terminal_state": tmp_path / "terminal-state.json",
    }
    source_hashes = {
        source_name: hashlib.sha256(
            (policy.REPOSITORY_ROOT / source_name).read_bytes()
        ).hexdigest()
        for source_name in sorted(policy.REQUIRED_LAUNCH_SOURCES)
    }
    policy_hashes = {
        "feed_launch_manifest_sha256": "c" * 64,
        "primary_policy_sha256": POLICY_SHA256,
        "queue_launch_manifest_sha256": "d" * 64,
    }
    spec = observer_supervisor.FeedTerminalCustodySpec(
        terminal_manifest_path=terminal_manifest_path,
        completion_receipt_path=completion_receipt_path,
        stop_sentinel_path=stop_sentinel_path,
        artifact_paths=artifact_paths,
        ledger_roots=ledger_roots,
        expected_command_sha256="e" * 64,
        owned_lock_paths=owned_lock_paths,
        owned_lock_roots=owned_lock_roots,
        source_hashes=source_hashes,
        policy_hashes=policy_hashes,
    )
    spec_path = tmp_path / "terminal-custody-spec.json"
    spec_path.write_bytes(
        policy.canonical_json_bytes(
            {
                "artifact_paths": {
                    name: str(path) for name, path in artifact_paths.items()
                },
                "completion_receipt_path": str(completion_receipt_path),
                "expected_command_sha256": "e" * 64,
                "ledger_roots": {
                    name: str(path) for name, path in ledger_roots.items()
                },
                "owned_lock_paths": [str(path) for path in owned_lock_paths],
                "owned_lock_roots": [str(path) for path in owned_lock_roots],
                "policy_hashes": policy_hashes,
                "source_hashes": source_hashes,
                "stop_sentinel_path": str(stop_sentinel_path),
                "terminal_manifest_path": str(terminal_manifest_path),
            }
        )
    )
    return spec, spec_path


def _bind_custody_command(
    spec: observer_supervisor.FeedTerminalCustodySpec,
    spec_path: Path,
    command: tuple[str, ...],
) -> observer_supervisor.FeedTerminalCustodySpec:
    command_sha256 = policy.canonical_sha256(list(command))
    value = json.loads(spec_path.read_bytes())
    if not isinstance(value, dict):
        raise TypeError("terminal custody specification is not an object")
    value["expected_command_sha256"] = command_sha256
    spec_path.write_bytes(policy.canonical_json_bytes(value))
    return replace(spec, expected_command_sha256=command_sha256)


def _publisher(
    path: Path,
    *,
    child_pid: int | None = None,
    child_creation_time: float | None = None,
) -> runtime_liveness.HeartbeatPublisher:
    pid = os.getpid() if child_pid is None else child_pid
    created = psutil.Process(pid).create_time() if child_creation_time is None else child_creation_time
    return runtime_liveness.HeartbeatPublisher(
        path,
        launch_nonce=LAUNCH_NONCE,
        run_signature=RUN_SIGNATURE,
        child_pid=pid,
        child_creation_time=created,
        source_sha256=SOURCE_SHA256,
        policy_sha256=POLICY_SHA256,
    )


def _reader(
    path: Path,
    *,
    child_pid: int | None = None,
    child_creation_time: float | None = None,
) -> runtime_liveness.HeartbeatReader:
    pid = os.getpid() if child_pid is None else child_pid
    created = psutil.Process(pid).create_time() if child_creation_time is None else child_creation_time
    return runtime_liveness.HeartbeatReader(
        path,
        launch_nonce=LAUNCH_NONCE,
        run_signature=RUN_SIGNATURE,
        child_pid=pid,
        child_creation_time=created,
        source_sha256=SOURCE_SHA256,
        policy_sha256=POLICY_SHA256,
    )


def test_heartbeat_chain_is_canonical_and_incremental(tmp_path: Path) -> None:
    path = tmp_path / "heartbeat.jsonl"
    start = 1_000_000_000_000
    with _publisher(path) as publisher:
        first = publisher.publish(
            "cycle_start",
            cycle_started_monotonic_ns=start,
            monotonic_ns=start,
        )
        second = publisher.publish(
            "progress:feed_persisted",
            cycle_started_monotonic_ns=start,
            monotonic_ns=start + 1,
        )
    reader = _reader(path)
    assert reader.poll() == second
    assert first.sequence == 1
    assert second.sequence == 2
    assert second.sha256 != first.sha256
    assert reader.poll() == second


def test_strict_heartbeat_age_boundary(tmp_path: Path) -> None:
    path = tmp_path / "heartbeat.jsonl"
    now = 1_000_000_000_000
    with _publisher(path) as publisher:
        publisher.publish(
            "cycle_start",
            cycle_started_monotonic_ns=now,
            monotonic_ns=now,
        )
    reader = _reader(path)
    assert (
        reader.require_live(
            monotonic_ns=now + runtime_liveness.MAX_HEARTBEAT_AGE_NS
        ).phase
        == "cycle_start"
    )
    with pytest.raises(runtime_liveness.LivenessFatalError, match="stale"):
        reader.require_live(
            monotonic_ns=now + runtime_liveness.MAX_HEARTBEAT_AGE_NS + 1
        )


def test_strict_cycle_deadline_boundary(tmp_path: Path) -> None:
    path = tmp_path / "heartbeat.jsonl"
    start = 1_000_000_000_000
    progress = start + 20_000_000_000
    with _publisher(path) as publisher:
        publisher.publish(
            "cycle_start",
            cycle_started_monotonic_ns=start,
            monotonic_ns=start,
        )
        publisher.publish(
            "progress:feed_fetch",
            cycle_started_monotonic_ns=start,
            monotonic_ns=progress,
        )
    reader = _reader(path)
    assert (
        reader.require_live(
            monotonic_ns=start + runtime_liveness.MAX_CYCLE_NS
        ).phase
        == "progress:feed_fetch"
    )
    with pytest.raises(runtime_liveness.LivenessFatalError, match="deadline"):
        reader.require_live(
            monotonic_ns=start + runtime_liveness.MAX_CYCLE_NS + 1
        )


def test_publisher_rejects_late_and_regressed_progress(tmp_path: Path) -> None:
    start = 1_000_000_000_000
    exact_path = tmp_path / "exact.jsonl"
    with _publisher(exact_path) as publisher:
        publisher.publish(
            "cycle_start",
            cycle_started_monotonic_ns=start,
            monotonic_ns=start,
        )
        publisher.publish(
            "cycle_complete",
            cycle_started_monotonic_ns=start,
            monotonic_ns=start + runtime_liveness.MAX_CYCLE_NS,
        )
        with pytest.raises(runtime_liveness.LivenessFatalError, match="regressed"):
            publisher.publish(
                "progress:regressed",
                cycle_started_monotonic_ns=start,
                monotonic_ns=start + runtime_liveness.MAX_CYCLE_NS - 1,
            )
    late_path = tmp_path / "late.jsonl"
    with (
        _publisher(late_path) as publisher,
        pytest.raises(runtime_liveness.LivenessFatalError, match="deadline"),
    ):
        publisher.publish(
            "cycle_start",
            cycle_started_monotonic_ns=start,
            monotonic_ns=start,
        )
        publisher.publish(
            "progress:late",
            cycle_started_monotonic_ns=start,
            monotonic_ns=start + runtime_liveness.MAX_CYCLE_NS + 1,
        )


def test_publisher_and_reader_reject_cycle_start_reset(tmp_path: Path) -> None:
    start = 1_000_000_000_000
    path = tmp_path / "heartbeat.jsonl"
    with _publisher(path) as publisher:
        publisher.publish(
            "cycle_start",
            cycle_started_monotonic_ns=start,
            monotonic_ns=start,
        )
        publisher.publish(
            "progress:fetch",
            cycle_started_monotonic_ns=start,
            monotonic_ns=start + 11_000_000_000,
        )
        with pytest.raises(runtime_liveness.LivenessFatalError, match="reset"):
            publisher.publish(
                "cycle_start",
                cycle_started_monotonic_ns=start + 22_000_000_000,
                monotonic_ns=start + 22_000_000_000,
            )

    lines = path.read_bytes().splitlines()
    forged = json.loads(lines[1])
    forged["phase"] = "cycle_start"
    forged["cycle_started_monotonic_ns"] = forged["monotonic_ns"]
    path.write_bytes(lines[0] + b"\n" + policy.canonical_json_bytes(forged) + b"\n")
    with pytest.raises(runtime_liveness.LivenessFatalError, match="reset"):
        _reader(path).poll()


def test_reader_rejects_chain_tamper_and_partial_record(tmp_path: Path) -> None:
    tampered_path = tmp_path / "tampered.jsonl"
    start = 1_000_000_000_000
    with _publisher(tampered_path) as publisher:
        publisher.publish(
            "cycle_start",
            cycle_started_monotonic_ns=start,
            monotonic_ns=start,
        )
        publisher.publish(
            "progress:two",
            cycle_started_monotonic_ns=start,
            monotonic_ns=start + 1,
        )
    lines = tampered_path.read_bytes().splitlines()
    second_row = json.loads(lines[1])
    second_row["prior_heartbeat_sha256"] = "0" * 64
    tampered_path.write_bytes(lines[0] + b"\n" + policy.canonical_json_bytes(second_row) + b"\n")
    with pytest.raises(runtime_liveness.LivenessFatalError, match="chain"):
        _reader(tampered_path).poll()

    partial_path = tmp_path / "partial.jsonl"
    with _publisher(partial_path) as publisher:
        publisher.publish(
            "cycle_start",
            cycle_started_monotonic_ns=start,
            monotonic_ns=start,
        )
    with partial_path.open("ab") as handle:
        handle.write(b"{")
    with pytest.raises(runtime_liveness.LivenessFatalError, match="partial"):
        _reader(partial_path).poll()


def test_publisher_rejects_hard_link_alias(tmp_path: Path) -> None:
    path = tmp_path / "heartbeat.jsonl"
    alias = tmp_path / "alias.jsonl"
    with _publisher(path) as publisher:
        os.link(path, alias)
        with pytest.raises(runtime_liveness.LivenessFatalError, match="identity"):
            publisher.publish(
                "cycle_start",
                cycle_started_monotonic_ns=1,
                monotonic_ns=1,
            )


def test_reader_rejects_path_replacement_between_polls(tmp_path: Path) -> None:
    path = tmp_path / "heartbeat.jsonl"
    moved = tmp_path / "moved.jsonl"
    with _publisher(path) as publisher:
        publisher.publish(
            "cycle_start",
            cycle_started_monotonic_ns=1,
            monotonic_ns=1,
        )
    reader = _reader(path)
    reader.poll()
    path.rename(moved)
    path.write_bytes(moved.read_bytes())
    with pytest.raises(runtime_liveness.LivenessFatalError, match="identity"):
        reader.poll()


def test_reader_rejects_oversized_growth_before_read(tmp_path: Path) -> None:
    path = tmp_path / "heartbeat.jsonl"
    path.write_bytes(b"x" * (runtime_liveness.MAX_HEARTBEAT_POLL_BYTES + 1))
    with pytest.raises(runtime_liveness.LivenessFatalError, match="growth"):
        _reader(path).poll()


def _wait_for_pid(path: Path) -> int:
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        if path.exists():
            return int(path.read_text(encoding="utf-8"))
        time.sleep(0.05)
    raise AssertionError("child did not publish descendant PID")


def _wait_absent(pid: int) -> None:
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        if not psutil.pid_exists(pid):
            return
        time.sleep(0.05)
    raise AssertionError(f"PID {pid} survived")


def _launch_terminal_fixture(
    tmp_path: Path,
    *,
    mode: str,
) -> tuple[int, dict[str, object]]:
    heartbeat_path = tmp_path / "heartbeat.jsonl"
    job_gate_path = tmp_path / "job-gate.json"
    receipt_path = tmp_path / "supervisor-receipt.json"
    stdout_path = tmp_path / "child.stdout.log"
    stderr_path = tmp_path / "child.stderr.log"
    terminal_custody, terminal_spec_path = _terminal_custody(
        tmp_path,
        heartbeat_path,
    )
    command = (
        str(Path(sys.base_prefix) / "python.exe"),
        str(Path("tests/v34/supervisor_child_fixture.py").resolve()),
        str(job_gate_path),
        str(heartbeat_path),
        str(terminal_spec_path),
        LAUNCH_NONCE,
        RUN_SIGNATURE,
        SOURCE_SHA256,
        POLICY_SHA256,
        mode,
    )
    terminal_custody = _bind_custody_command(
        terminal_custody,
        terminal_spec_path,
        command,
    )
    child_env = dict(os.environ)
    child_env["PYTHONPATH"] = os.pathsep.join(
        (str(Path.cwd()), str(Path(sys.prefix) / "Lib" / "site-packages"))
    )
    result = observer_supervisor.launch_and_supervise(
        command=command,
        cwd=Path.cwd(),
        heartbeat_path=heartbeat_path,
        job_gate_path=job_gate_path,
        receipt_path=receipt_path,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        launch_nonce=LAUNCH_NONCE,
        run_signature=RUN_SIGNATURE,
        source_sha256=SOURCE_SHA256,
        policy_sha256=POLICY_SHA256,
        terminal_custody=terminal_custody,
        env=child_env,
    )
    receipt = json.loads(receipt_path.read_bytes())
    if not isinstance(receipt, dict):
        raise TypeError("supervisor receipt is not an object")
    return result, receipt


@pytest.mark.skipif(sys.platform != "win32", reason="production supervisor is Windows-first")
@pytest.mark.parametrize(
    "mode, expected_result, expected_outcome, reason_fragment",
    [
        ("clean", 0, "child_exited", None),
        ("missing_manifest", 4, "invalid_terminal_custody", "unreadable"),
        ("tamper_after_manifest", 4, "invalid_terminal_custody", "differs from disk"),
        ("other_lock_coexists", 0, "child_exited", None),
        ("remaining_descendant", 6, "descendant_survived_child", "retained a process"),
        ("crash_after_receipt", 3, "child_exited", None),
    ],
)
def test_supervisor_terminal_custody_fault_matrix(
    tmp_path: Path,
    mode: str,
    expected_result: int,
    expected_outcome: str,
    reason_fragment: str | None,
) -> None:
    result, receipt = _launch_terminal_fixture(tmp_path, mode=mode)
    assert result == expected_result
    assert receipt["outcome"] == expected_outcome
    if reason_fragment is not None:
        assert reason_fragment in str(receipt["reason"])
    if mode == "clean":
        assert receipt["actual_os_exit_code"] == 0
        assert receipt["terminal_generation_id"] == "g00000001"
        assert receipt["child_completion_receipt_sha256"]
        assert receipt["feed_terminal_artifact_manifest_sha256"]
    if mode == "crash_after_receipt":
        assert receipt["actual_os_exit_code"] == 7
        assert receipt["child_completion_receipt_sha256"] is None


def test_terminal_custody_rejects_exact_owned_lock_remaining(tmp_path: Path) -> None:
    heartbeat_path = tmp_path / "heartbeat.jsonl"
    spec, _spec_path = _terminal_custody(tmp_path, heartbeat_path)
    spec.owned_lock_paths[0].write_bytes(b"still-owned")
    with pytest.raises(observer_supervisor.SupervisorFatalError, match="lock remains"):
        observer_supervisor._require_owned_locks_absent(spec)


@pytest.mark.skipif(sys.platform != "win32", reason="production supervisor is Windows-first")
def test_supervisor_kills_real_process_tree_on_stale_heartbeat(tmp_path: Path) -> None:
    descendant_path = tmp_path / "descendant.pid"
    heartbeat_path = tmp_path / "heartbeat.jsonl"
    job_gate_path = tmp_path / "job-gate.json"
    receipt_path = tmp_path / "supervisor-receipt.json"
    stdout_path = tmp_path / "child.stdout.log"
    stderr_path = tmp_path / "child.stderr.log"
    terminal_custody, terminal_spec_path = _terminal_custody(
        tmp_path,
        heartbeat_path,
    )
    child_code = (
        "import pathlib,subprocess,sys,time;"
        "from scripts.v34 import runtime_liveness as r;"
        "gate=r.wait_for_job_gate(pathlib.Path(sys.argv[1]),launch_nonce=sys.argv[5]);"
        "p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)']);"
        "pathlib.Path(sys.argv[3]).write_text(str(p.pid),encoding='utf-8');"
        "stale=time.monotonic_ns()-r.MAX_HEARTBEAT_AGE_NS-1;"
        "publisher=r.HeartbeatPublisher(pathlib.Path(sys.argv[2]),"
        "launch_nonce=sys.argv[5],run_signature=sys.argv[6],"
        "child_pid=gate.child_pid,child_creation_time=gate.child_creation_time,"
        "source_sha256=sys.argv[7],policy_sha256=sys.argv[8]);"
        "publisher.publish('cycle_start',cycle_started_monotonic_ns=stale,"
        "monotonic_ns=stale);publisher.close();"
        "time.sleep(60)"
    )
    command = (
        str(Path(sys.base_prefix) / "python.exe"),
        "-c",
        child_code,
        str(job_gate_path),
        str(heartbeat_path),
        str(descendant_path),
        "unused",
        LAUNCH_NONCE,
        RUN_SIGNATURE,
        SOURCE_SHA256,
        POLICY_SHA256,
    )
    terminal_custody = _bind_custody_command(
        terminal_custody,
        terminal_spec_path,
        command,
    )
    child_env = dict(os.environ)
    child_env["PYTHONPATH"] = os.pathsep.join(
        (str(Path.cwd()), str(Path(sys.prefix) / "Lib" / "site-packages"))
    )
    try:
        result = observer_supervisor.launch_and_supervise(
            command=command,
            cwd=Path.cwd(),
            heartbeat_path=heartbeat_path,
            job_gate_path=job_gate_path,
            receipt_path=receipt_path,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            launch_nonce=LAUNCH_NONCE,
            run_signature=RUN_SIGNATURE,
            source_sha256=SOURCE_SHA256,
            policy_sha256=POLICY_SHA256,
            terminal_custody=terminal_custody,
            env=child_env,
        )
        assert result == 4
        gate = json.loads(job_gate_path.read_bytes())
        child_pid = gate["child_pid"]
        descendant_pid = _wait_for_pid(descendant_path)
        _wait_absent(child_pid)
        _wait_absent(descendant_pid)
        receipt = json.loads(receipt_path.read_bytes())
        assert receipt["outcome"] == "forced_kill"
        assert receipt["child_pid"] == child_pid
        assert receipt["reason"] == "progress heartbeat is stale"
    finally:
        for path in (job_gate_path, descendant_path):
            if not path.exists():
                continue
            value = json.loads(path.read_bytes()) if path == job_gate_path else int(path.read_text())
            pid = value["child_pid"] if isinstance(value, dict) else value
            with suppress(psutil.NoSuchProcess):
                psutil.Process(pid).kill()


@pytest.mark.skipif(sys.platform != "win32", reason="production supervisor is Windows-first")
def test_supervisor_allows_exact_empty_file_before_first_heartbeat(
    tmp_path: Path,
) -> None:
    heartbeat_path = tmp_path / "heartbeat.jsonl"
    job_gate_path = tmp_path / "job-gate.json"
    receipt_path = tmp_path / "supervisor-receipt.json"
    stdout_path = tmp_path / "child.stdout.log"
    stderr_path = tmp_path / "child.stderr.log"
    terminal_custody, terminal_spec_path = _terminal_custody(
        tmp_path,
        heartbeat_path,
    )
    command = (
        str(Path(sys.base_prefix) / "python.exe"),
        str(Path("tests/v34/supervisor_child_fixture.py").resolve()),
        str(job_gate_path),
        str(heartbeat_path),
        str(terminal_spec_path),
        LAUNCH_NONCE,
        RUN_SIGNATURE,
        SOURCE_SHA256,
        POLICY_SHA256,
        "clean_delayed",
    )
    terminal_custody = _bind_custody_command(
        terminal_custody,
        terminal_spec_path,
        command,
    )
    child_env = dict(os.environ)
    child_env["PYTHONPATH"] = os.pathsep.join(
        (str(Path.cwd()), str(Path(sys.prefix) / "Lib" / "site-packages"))
    )
    result = observer_supervisor.launch_and_supervise(
        command=command,
        cwd=Path.cwd(),
        heartbeat_path=heartbeat_path,
        job_gate_path=job_gate_path,
        receipt_path=receipt_path,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        launch_nonce=LAUNCH_NONCE,
        run_signature=RUN_SIGNATURE,
        source_sha256=SOURCE_SHA256,
        policy_sha256=POLICY_SHA256,
        terminal_custody=terminal_custody,
        env=child_env,
    )
    assert result == 0
    receipt = json.loads(receipt_path.read_bytes())
    assert receipt["outcome"] == "child_exited"
    reader = runtime_liveness.HeartbeatReader(
        heartbeat_path,
        launch_nonce=LAUNCH_NONCE,
        run_signature=RUN_SIGNATURE,
        child_pid=receipt["child_pid"],
        child_creation_time=receipt["child_creation_time"],
        source_sha256=SOURCE_SHA256,
        policy_sha256=POLICY_SHA256,
    )
    assert reader.require_live().phase == runtime_liveness.CYCLE_COMPLETE_PHASE


@pytest.mark.skipif(sys.platform != "win32", reason="production supervisor is Windows-first")
def test_initial_grace_does_not_restart_after_resume_delay(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    heartbeat_path = tmp_path / "heartbeat.jsonl"
    job_gate_path = tmp_path / "job-gate.json"
    receipt_path = tmp_path / "supervisor-receipt.json"
    stdout_path = tmp_path / "child.stdout.log"
    stderr_path = tmp_path / "child.stderr.log"
    terminal_custody, terminal_spec_path = _terminal_custody(
        tmp_path,
        heartbeat_path,
    )
    child_code = (
        "import pathlib,sys,time;"
        "from scripts.v34 import runtime_liveness as r;"
        "r.wait_for_job_gate(pathlib.Path(sys.argv[1]),launch_nonce=sys.argv[2]);"
        "time.sleep(60)"
    )
    command = (
        str(Path(sys.base_prefix) / "python.exe"),
        "-c",
        child_code,
        str(job_gate_path),
        LAUNCH_NONCE,
    )
    terminal_custody = _bind_custody_command(
        terminal_custody,
        terminal_spec_path,
        command,
    )
    child_env = dict(os.environ)
    child_env["PYTHONPATH"] = os.pathsep.join(
        (str(Path.cwd()), str(Path(sys.prefix) / "Lib" / "site-packages"))
    )
    original_resume = observer_supervisor._resume_process
    delay_finished_at = 0.0

    def resume_then_delay(pid: int) -> None:
        nonlocal delay_finished_at
        original_resume(pid)
        time.sleep(0.5)
        delay_finished_at = time.perf_counter()

    monkeypatch.setattr(observer_supervisor, "_resume_process", resume_then_delay)
    monkeypatch.setattr(runtime_liveness, "MAX_HEARTBEAT_AGE_NS", 200_000_000)
    monkeypatch.setattr(runtime_liveness, "SUPERVISOR_CHECK_SECONDS", 0.01)
    result = observer_supervisor.launch_and_supervise(
        command=command,
        cwd=Path.cwd(),
        heartbeat_path=heartbeat_path,
        job_gate_path=job_gate_path,
        receipt_path=receipt_path,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        launch_nonce=LAUNCH_NONCE,
        run_signature=RUN_SIGNATURE,
        source_sha256=SOURCE_SHA256,
        policy_sha256=POLICY_SHA256,
        terminal_custody=terminal_custody,
        env=child_env,
    )
    returned_at = time.perf_counter()
    assert result == 4
    assert delay_finished_at > 0
    assert returned_at - delay_finished_at < 0.15
    receipt = json.loads(receipt_path.read_bytes())
    assert receipt["outcome"] == "forced_kill"
