"""Real subprocess fixture for v34 terminal custody tests."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from scripts.v34 import (
    feed_archive,
    feed_lifecycle,
    feed_lineage,
    policy,
    runtime_liveness,
)


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _write(path: Path, value: dict[str, object]) -> bytes:
    raw = policy.canonical_json_bytes(value)
    feed_archive._write_create_once(path, raw)
    return raw


def _binding(path: Path) -> dict[str, object]:
    raw = path.read_bytes()
    return {
        "path": str(path.resolve()),
        "sha256": _sha256(raw),
        "size": len(raw),
    }


def _write_terminal_chain(
    spec_path: Path,
    *,
    launch_nonce: str,
    run_signature: str,
    mode: str,
) -> None:
    spec_value = json.loads(spec_path.read_bytes())
    if not isinstance(spec_value, dict):
        raise TypeError("fixture terminal specification is invalid")
    artifact_value = spec_value["artifact_paths"]
    if not isinstance(artifact_value, dict):
        raise TypeError("fixture artifact paths are invalid")
    artifacts = {
        cast("str", name): Path(cast("str", path))
        for name, path in artifact_value.items()
    }
    policy_hashes = spec_value["policy_hashes"]
    if not isinstance(policy_hashes, dict):
        raise TypeError("fixture policy hashes are invalid")
    provenance = {
        "launch_manifest_sha256": policy_hashes["feed_launch_manifest_sha256"],
        "launch_nonce": launch_nonce,
        "policy_sha256": policy_hashes["primary_policy_sha256"],
        "run_signature": run_signature,
        "schema_version": policy.FEED_SCHEMA_VERSION,
        "source_hashes": spec_value["source_hashes"],
    }
    generation_id = "g00000001"
    observed_at = datetime.now(tz=UTC)
    lifecycle_state = feed_lifecycle.transition_game(
        None,
        game_pk=1,
        completed_plays={},
        official_current_total=0,
        abstract_state="Final",
        detailed_state="Final",
        observed_at=observed_at,
        successful_poll_monotonic_ns=1,
        expected_prior_state_commitment_sha256=None,
    ).state
    serialized_state_value = json.loads(feed_lineage.serialize_game_state(lifecycle_state))
    game_state = {
        **provenance,
        "abstract_state": "Final",
        "completed_plays": {},
        "detailed_state": "Final",
        "game_pk": 1,
        "generation_id": generation_id,
        "observed_at": lifecycle_state.last_observed_at,
        "official_current_total": 0,
    }
    summary_raw = _write(
        artifacts["public_summary"],
        {
            **provenance,
            "cycle_observed_at": observed_at.isoformat(),
            "game_states": {"1": game_state},
            "generation_id": generation_id,
            "kind": "v34_feed_generation",
            "lifecycle_states": {"1": serialized_state_value},
        },
    )
    summary_sha256 = _sha256(summary_raw)
    _write(
        artifacts["public_receipt"],
        {
            **provenance,
            "generation_id": generation_id,
            "summary_sha256": summary_sha256,
        },
    )
    _write(artifacts["schedule_snapshot"], {"kind": "fixture_schedule"})
    ledger_root_value = spec_value["ledger_roots"]
    if not isinstance(ledger_root_value, dict):
        raise TypeError("fixture ledger roots are invalid")
    ledger_roots = {
        cast("str", name): Path(cast("str", path))
        for name, path in ledger_root_value.items()
    }
    for root in ledger_roots.values():
        root.mkdir()
    registry_raw = _write(
        ledger_roots["custody_control"] / "registry.json",
        {"kind": "fixture_registry"},
    )
    commit_raw = _write(
        ledger_roots["custody_control"] / "commit.json",
        {"kind": "fixture_commit"},
    )
    registry_sha256 = _sha256(registry_raw)
    commit_sha256 = _sha256(commit_raw)
    inventory: list[dict[str, object]] = []
    for label, root in ledger_roots.items():
        for path in sorted(item for item in root.rglob("*") if item.is_file()):
            raw = path.read_bytes()
            inventory.append(
                {
                    "relative_path": path.relative_to(root).as_posix(),
                    "root": label,
                    "sha256": _sha256(raw),
                    "size": len(raw),
                }
            )
    event_raw = _write(
        artifacts["terminal_event_log"],
        {
            **provenance,
            "batch_count": 1,
            "inventory": inventory,
            "kind": "v34_feed_terminal_event_log",
            "latest_batch_commit_sha256": commit_sha256,
            "latest_batch_name": "batch-00000001",
            "registry_manifest_sha256": registry_sha256,
        },
    )
    state_raw = _write(
        artifacts["terminal_state"],
        {
            **provenance,
            "game_states": {"1": serialized_state_value},
            "kind": "v34_feed_terminal_state",
            "terminal_generation_id": generation_id,
            "terminal_summary_sha256": summary_sha256,
        },
    )
    stop_raw = _write(
        artifacts["stop_sentinel"],
        {
            "launch_nonce": launch_nonce,
            "reason": "slate_final",
            "requested_at": datetime.now(tz=UTC).isoformat(),
        },
    )
    event_sha256 = _sha256(event_raw)
    state_sha256 = _sha256(state_raw)
    stop_sha256 = _sha256(stop_raw)
    completion_raw = _write(
        artifacts["completion_receipt"],
        {
            "batch_count": 1,
            "capital_eligible": False,
            "completed_at": datetime.now(tz=UTC).isoformat(),
            "last_feed_generation_id": generation_id,
            "last_feed_summary_sha256": summary_sha256,
            "launch_nonce": launch_nonce,
            "outcome": "slate_final",
            "run_signature": run_signature,
            "stop_sentinel_sha256": stop_sha256,
            "terminal_event_log_sha256": event_sha256,
            "terminal_state_sha256": state_sha256,
        },
    )
    if mode == "crash_after_receipt":
        os._exit(7)
    manifest = {
        "artifacts": {name: _binding(path) for name, path in artifacts.items()},
        "batch_count": 1,
        "created_at": datetime.now(tz=UTC).isoformat(),
        "kind": "v34_feed_terminal_artifact_manifest",
        "latest_batch_commit_sha256": commit_sha256,
        "latest_batch_name": "batch-00000001",
        "launch_nonce": launch_nonce,
        "outcome": "slate_final",
        "policy_hashes": spec_value["policy_hashes"],
        "registry_manifest_sha256": registry_sha256,
        "run_signature": run_signature,
        "source_hashes": spec_value["source_hashes"],
        "stop_sentinel_sha256": stop_sha256,
        "terminal_event_log_sha256": event_sha256,
        "terminal_generation_id": generation_id,
        "terminal_state_sha256": state_sha256,
        "terminal_summary_sha256": summary_sha256,
    }
    if mode != "missing_manifest":
        _write(Path(cast("str", spec_value["terminal_manifest_path"])), manifest)
    if mode == "tamper_after_manifest":
        artifacts["terminal_event_log"].write_bytes(b"tampered")
    if mode == "other_lock_coexists":
        lock_roots = spec_value["owned_lock_roots"]
        if not isinstance(lock_roots, list) or not lock_roots:
            raise TypeError("fixture lock roots are invalid")
        (Path(cast("str", lock_roots[0])) / "unexpected.lock").write_bytes(b"lock")
    if mode == "remaining_descendant":
        subprocess.Popen(
            [sys.executable, "-c", "import time;time.sleep(60)"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    if _sha256(completion_raw) != _binding(artifacts["completion_receipt"])["sha256"]:
        raise RuntimeError("fixture completion receipt changed")


def main() -> None:
    if len(sys.argv) != 9:
        raise ValueError("fixture argument count differs")
    gate_path = Path(sys.argv[1])
    heartbeat_path = Path(sys.argv[2])
    spec_path = Path(sys.argv[3])
    launch_nonce = sys.argv[4]
    run_signature = sys.argv[5]
    source_sha256 = sys.argv[6]
    policy_sha256 = sys.argv[7]
    mode = sys.argv[8]
    gate = runtime_liveness.wait_for_job_gate(gate_path, launch_nonce=launch_nonce)
    if mode == "clean_delayed":
        time.sleep(2.5)
    started = time.monotonic_ns()
    publisher = runtime_liveness.HeartbeatPublisher(
        heartbeat_path,
        launch_nonce=launch_nonce,
        run_signature=run_signature,
        child_pid=gate.child_pid,
        child_creation_time=gate.child_creation_time,
        source_sha256=source_sha256,
        policy_sha256=policy_sha256,
    )
    publisher.publish(
        runtime_liveness.CYCLE_START_PHASE,
        cycle_started_monotonic_ns=started,
        monotonic_ns=started,
    )
    publisher.publish(
        runtime_liveness.CYCLE_COMPLETE_PHASE,
        cycle_started_monotonic_ns=started,
    )
    publisher.close()
    _write_terminal_chain(
        spec_path,
        launch_nonce=launch_nonce,
        run_signature=run_signature,
        mode=mode,
    )


if __name__ == "__main__":
    main()
