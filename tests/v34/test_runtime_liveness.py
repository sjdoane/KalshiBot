from __future__ import annotations

import json
import os
import sys
import time
from contextlib import suppress
from pathlib import Path

import psutil
import pytest
from scripts.v34 import observer_supervisor, policy, runtime_liveness

LAUNCH_NONCE = "test-launch"
RUN_SIGNATURE = "test-run"
SOURCE_SHA256 = "a" * 64
POLICY_SHA256 = "b" * 64


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


@pytest.mark.skipif(sys.platform != "win32", reason="production supervisor is Windows-first")
def test_supervisor_kills_real_process_tree_on_stale_heartbeat(tmp_path: Path) -> None:
    descendant_path = tmp_path / "descendant.pid"
    heartbeat_path = tmp_path / "heartbeat.jsonl"
    job_gate_path = tmp_path / "job-gate.json"
    receipt_path = tmp_path / "supervisor-receipt.json"
    stdout_path = tmp_path / "child.stdout.log"
    stderr_path = tmp_path / "child.stderr.log"
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
    child_code = (
        "import pathlib,sys,time;"
        "from scripts.v34 import runtime_liveness as r;"
        "gate=r.wait_for_job_gate(pathlib.Path(sys.argv[1]),launch_nonce=sys.argv[3]);"
        "publisher=r.HeartbeatPublisher(pathlib.Path(sys.argv[2]),"
        "launch_nonce=sys.argv[3],run_signature=sys.argv[4],"
        "child_pid=gate.child_pid,child_creation_time=gate.child_creation_time,"
        "source_sha256=sys.argv[5],policy_sha256=sys.argv[6]);"
        "time.sleep(2.5);"
        "started=time.monotonic_ns();"
        "publisher.publish('cycle_start',cycle_started_monotonic_ns=started,"
        "monotonic_ns=started);"
        "publisher.publish('cycle_complete',cycle_started_monotonic_ns=started);"
        "time.sleep(1.5);publisher.close()"
    )
    command = (
        str(Path(sys.base_prefix) / "python.exe"),
        "-c",
        child_code,
        str(job_gate_path),
        str(heartbeat_path),
        LAUNCH_NONCE,
        RUN_SIGNATURE,
        SOURCE_SHA256,
        POLICY_SHA256,
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
        env=child_env,
    )
    returned_at = time.perf_counter()
    assert result == 4
    assert delay_finished_at > 0
    assert returned_at - delay_finished_at < 0.15
    receipt = json.loads(receipt_path.read_bytes())
    assert receipt["outcome"] == "forced_kill"
