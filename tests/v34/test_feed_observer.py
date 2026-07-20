from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import httpx
import psutil
import pytest
from scripts.v34 import (
    feed_archive,
    feed_lifecycle,
    feed_observer,
    observer_supervisor,
    policy,
    runtime_liveness,
)

BASE = datetime(2026, 7, 20, 21, 30, tzinfo=UTC)


def anchor() -> policy.FeedLaunchAnchor:
    source_hashes = {
        source_name: hashlib.sha256(
            (policy.REPOSITORY_ROOT / source_name).read_bytes()
        ).hexdigest()
        for source_name in sorted(policy.REQUIRED_LAUNCH_SOURCES)
    }
    source_hashes["scripts/v34/feed_observer.py"] = hashlib.sha256(
        (policy.REPOSITORY_ROOT / "scripts/v34/feed_observer.py").read_bytes()
    ).hexdigest()
    raw = policy.canonical_json_bytes(
        {
            "created_at": BASE.isoformat(),
            "launch_nonce": "v34-feed-observer-test",
            "manifest_kind": "v34_feed_launch",
            "output_root": policy.FEED_OUTPUT_ROOT,
            "policy_sha256": policy.POLICY_CANONICAL_SHA256,
            "run_signature": policy.FEED_RUN_SIGNATURE,
            "schema_version": policy.FEED_SCHEMA_VERSION,
            "source_hashes": source_hashes,
        }
    )
    return policy.verify_feed_launch_manifest_bytes(raw)


def queue_anchor() -> policy.QueueLaunchAnchor:
    source_hashes = {
        source_name: hashlib.sha256(
            (policy.REPOSITORY_ROOT / source_name).read_bytes()
        ).hexdigest()
        for source_name in sorted(policy.REQUIRED_QUEUE_LAUNCH_SOURCES)
    }
    raw = policy.canonical_json_bytes(
        {
            "created_at": BASE.isoformat(),
            "launch_nonce": "v34-queue-observer-test",
            "manifest_kind": "v34_queue_launch",
            "output_root": policy.QUEUE_OUTPUT_ROOT,
            "policy_sha256": policy.POLICY_CANONICAL_SHA256,
            "run_signature": policy.QUEUE_RUN_SIGNATURE,
            "schema_version": policy.QUEUE_SCHEMA_VERSION,
            "source_hashes": source_hashes,
        }
    )
    return policy.verify_queue_launch_manifest_bytes(raw)


def raw_play(
    index: int,
    *,
    away: int,
    home: int,
    complete: bool = True,
) -> dict[str, object]:
    return {
        "about": {
            "atBatIndex": index,
            "endTime": (BASE + timedelta(seconds=index + 1)).isoformat(),
            "hasReview": False,
            "isComplete": complete,
            "isScoringPlay": away + home > 0,
        },
        "result": {
            "awayScore": away,
            "description": f"play {index}",
            "event": "Single",
            "eventType": "single",
            "homeScore": home,
            "rbi": max(0, away + home),
        },
    }


def live_payload(
    *,
    game_pk: int = 824410,
    abstract: str = "Live",
    detailed: str = "In Progress",
    plays: list[dict[str, object]] | None = None,
    away: int = 0,
    home: int = 0,
) -> dict[str, object]:
    return {
        "gamePk": game_pk,
        "gameData": {
            "status": {
                "abstractGameState": abstract,
                "detailedState": detailed,
            }
        },
        "liveData": {
            "linescore": {
                "teams": {
                    "away": {"runs": away},
                    "home": {"runs": home},
                }
            },
            "plays": {"allPlays": [] if plays is None else plays},
        },
    }


def test_schedule_freezes_only_games_inside_exact_horizon() -> None:
    payload = {
        "dates": [
            {
                "games": [
                    {"gamePk": 1, "gameDate": (BASE - timedelta(seconds=1)).isoformat()},
                    {"gamePk": 2, "gameDate": BASE.isoformat()},
                    {
                        "gamePk": 3,
                        "gameDate": (BASE + timedelta(hours=23)).isoformat(),
                    },
                    {
                        "gamePk": 4,
                        "gameDate": (BASE + timedelta(hours=24)).isoformat(),
                    },
                ]
            }
        ]
    }
    result = feed_observer.parse_schedule(
        payload,
        launch_at=BASE,
        hard_stop_at=BASE + timedelta(hours=24),
    )
    assert [row.game_pk for row in result] == [2, 3]


def test_schedule_rejects_duplicate_game_time_drift() -> None:
    payload = {
        "dates": [
            {
                "games": [
                    {"gamePk": 2, "gameDate": BASE.isoformat()},
                    {
                        "gamePk": 2,
                        "gameDate": (BASE + timedelta(minutes=1)).isoformat(),
                    },
                ]
            }
        ]
    }
    with pytest.raises(feed_observer.FeedObserverFatalError, match="duplicates"):
        feed_observer.parse_schedule(
            payload,
            launch_at=BASE,
            hard_stop_at=BASE + timedelta(hours=24),
        )


def test_projection_uses_only_exact_completed_play_fields() -> None:
    extra = raw_play(0, away=1, home=0)
    extra["about"] = {**extra["about"], "inning": 1}  # type: ignore[dict-item]
    extra["result"] = {**extra["result"], "isOut": False}  # type: ignore[dict-item]
    incomplete = raw_play(1, away=1, home=0, complete=False)
    projected = feed_observer.project_live_feed(
        live_payload(plays=[extra, incomplete], away=1),
        game_pk=824410,
        observed_at=BASE + timedelta(minutes=2),
        successful_poll_monotonic_ns=10_000_000_000,
    )
    assert projected is not None
    assert list(projected.completed_plays) == ["0"]
    play = projected.completed_plays["0"]
    assert isinstance(play, dict)
    assert set(play) == {"about", "result", "review_details"}
    assert set(play["about"]) == {
        "atBatIndex",
        "endTime",
        "hasReview",
        "isComplete",
        "isScoringPlay",
    }
    assert set(play["result"]) == {
        "awayScore",
        "description",
        "event",
        "eventType",
        "homeScore",
        "rbi",
    }


def test_projection_rejects_gap_and_prohibited_status() -> None:
    with pytest.raises(feed_observer.FeedObserverFatalError, match="noncontiguous"):
        feed_observer.project_live_feed(
            live_payload(plays=[raw_play(1, away=0, home=0)]),
            game_pk=824410,
            observed_at=BASE + timedelta(minutes=2),
            successful_poll_monotonic_ns=10_000_000_000,
        )
    with pytest.raises(feed_observer.FeedObserverFatalError, match="prohibited"):
        feed_observer.project_live_feed(
            live_payload(abstract="Preview", detailed="Postponed"),
            game_pk=824410,
            observed_at=BASE + timedelta(minutes=2),
            successful_poll_monotonic_ns=10_000_000_000,
        )


def test_bounded_get_uses_exactly_one_retry_before_success() -> None:
    calls = 0
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(503, request=request)
        return httpx.Response(200, json={"ok": True}, request=request)

    async def run() -> tuple[dict[str, object], bytes]:
        async def record_sleep(seconds: float) -> None:
            sleeps.append(seconds)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await feed_observer.bounded_get_json(
                client,
                "https://example.test/feed",
                sleep=record_sleep,
            )

    result, raw = asyncio.run(run())
    assert result == {"ok": True}
    assert json.loads(raw) == {"ok": True}
    assert calls == 2
    assert sleeps == [feed_observer.HTTP_RETRY_SECONDS]


def test_bounded_get_rejects_oversized_payload_after_two_attempts() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            headers={"content-length": str(feed_observer.MAX_HTTP_RESPONSE_BYTES + 1)},
            content=b"{}",
            request=request,
        )

    async def run() -> None:
        async def no_sleep(_seconds: float) -> None:
            return None

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await feed_observer.bounded_get_json(
                client,
                "https://example.test/feed",
                sleep=no_sleep,
            )

    with pytest.raises(feed_observer.FeedObserverFatalError, match="exhausted"):
        asyncio.run(run())
    assert calls == feed_observer.HTTP_ATTEMPTS


def test_source_pair_and_publication_round_trip(tmp_path: Path) -> None:
    launch = anchor()
    projected = feed_observer.project_live_feed(
        live_payload(plays=[raw_play(0, away=1, home=0)], away=1),
        game_pk=824410,
        observed_at=BASE + timedelta(minutes=2),
        successful_poll_monotonic_ns=10_000_000_000,
    )
    assert projected is not None
    state = feed_lifecycle.transition_game(
        None,
        game_pk=projected.game_pk,
        completed_plays=projected.completed_plays,
        official_current_total=projected.official_current_total,
        abstract_state=projected.abstract_state,
        detailed_state=projected.detailed_state,
        observed_at=datetime.fromisoformat(projected.observed_at),
        successful_poll_monotonic_ns=projected.successful_poll_monotonic_ns,
        expected_prior_state_commitment_sha256=None,
    ).state
    pair = feed_observer.build_source_pair(
        (projected,),
        lifecycle_states={projected.game_pk: state},
        anchor=launch,
        generation_id="g00000001",
        cycle_observed_at=(BASE + timedelta(minutes=2)).isoformat(),
    )
    summary = json.loads(pair.summary_bytes)
    assert summary["game_states"]["824410"]["completed_plays"]["0"]["result"][
        "awayScore"
    ] == 1
    assert summary["lifecycle_states"]["824410"]["state_commitment_sha256"]
    public = tmp_path / "public"
    public.mkdir()
    feed_observer.publish_public_pair(
        pair,
        anchor=launch,
        public_root=public,
        trusted_root=tmp_path,
    )
    assert (
        feed_archive.read_coherent_feed_pair(
            public / feed_observer.PUBLIC_SUMMARY_NAME,
            public / feed_observer.PUBLIC_RECEIPT_NAME,
            anchor=launch,
        )
        == pair
    )


def test_preview_projection_is_not_a_lifecycle_observation() -> None:
    assert (
        feed_observer.project_live_feed(
            live_payload(abstract="Preview", detailed="Scheduled"),
            game_pk=824410,
            observed_at=BASE,
            successful_poll_monotonic_ns=1,
        )
        is None
    )


def test_projection_rejects_mismatched_game_pk() -> None:
    with pytest.raises(feed_observer.FeedObserverFatalError, match="gamePk differs"):
        feed_observer.project_live_feed(
            live_payload(game_pk=999999),
            game_pk=824410,
            observed_at=BASE,
            successful_poll_monotonic_ns=1,
        )


@pytest.mark.parametrize(
    "plays, message",
    [
        ([raw_play(0, away=0, home=0), raw_play(0, away=0, home=0)], "duplicate"),
        ([raw_play(1, away=0, home=0), raw_play(0, away=0, home=0)], "reordered"),
        (
            [
                raw_play(0, away=0, home=0, complete=False),
                raw_play(1, away=0, home=0),
            ],
            "follows an incomplete",
        ),
    ],
)
def test_projection_rejects_duplicate_reordered_or_completed_after_tail(
    plays: list[dict[str, object]],
    message: str,
) -> None:
    with pytest.raises(feed_observer.FeedObserverFatalError, match=message):
        feed_observer.project_live_feed(
            live_payload(plays=plays),
            game_pk=824410,
            observed_at=BASE,
            successful_poll_monotonic_ns=1,
        )


def test_previously_observed_game_cannot_regress_to_preview() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=live_payload(abstract="Preview", detailed="Scheduled"),
            request=request,
        )

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await feed_observer.fetch_projected_games(
                client,
                (feed_observer.ScheduledGame(824410, BASE.isoformat()),),
                prior_observed_game_pks=frozenset({824410}),
            )

    with pytest.raises(feed_observer.FeedObserverFatalError, match="regressed"):
        asyncio.run(run())


def test_bounded_get_enforces_hard_total_attempt_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.05)
        return httpx.Response(200, json={"too": "late"}, request=request)

    async def run() -> None:
        async def no_sleep(_seconds: float) -> None:
            return None

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await feed_observer.bounded_get_json(
                client,
                "https://example.test/slow",
                sleep=no_sleep,
            )

    monkeypatch.setattr(feed_observer, "HTTP_TIMEOUT_SECONDS", 0.01)
    with pytest.raises(feed_observer.FeedObserverFatalError, match="exhausted"):
        asyncio.run(run())
    assert calls == feed_observer.HTTP_ATTEMPTS


def test_run_observer_full_pipeline_seals_terminal_chain(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_root = tmp_path / "runtime"
    custody_root = tmp_path / "custody"
    public_root = custody_root / "public"
    for path in (runtime_root, custody_root, public_root):
        path.mkdir()
    feed_launch = anchor()
    queue_launch = queue_anchor()
    feed_manifest = tmp_path / "feed-launch.json"
    queue_manifest = tmp_path / "queue-launch.json"
    feed_manifest.write_bytes(feed_launch.manifest_bytes)
    queue_manifest.write_bytes(queue_launch.manifest_bytes)
    source_sha256 = hashlib.sha256(
        (policy.REPOSITORY_ROOT / "scripts/v34/feed_observer.py").read_bytes()
    ).hexdigest()
    config = feed_observer.ObserverConfig(
        runtime_root=runtime_root,
        custody_root=custody_root,
        feed_launch_manifest=feed_manifest,
        queue_launch_manifest=queue_manifest,
        heartbeat_path=custody_root / "heartbeat.jsonl",
        job_gate_path=custody_root / "job-gate.json",
        stop_sentinel=custody_root / "stop.json",
        public_root=public_root,
        schedule_snapshot_path=custody_root / "schedule.json",
        completion_receipt_path=custody_root / "completion.receipt.json",
        terminal_manifest_path=custody_root / "terminal-manifest.json",
        terminal_event_log_path=custody_root / "terminal-event-log.json",
        terminal_state_path=custody_root / "terminal-state.json",
        launch_nonce="v34-feed-observer-test",
        source_sha256=source_sha256,
        created_at=BASE.isoformat(),
        hard_stop_at=(BASE + timedelta(hours=1)).isoformat(),
        schedule_start=BASE.astimezone(feed_observer.MLB_SCHEDULE_TIMEZONE).date(),
        schedule_end=(BASE + timedelta(hours=1)).astimezone(
            feed_observer.MLB_SCHEDULE_TIMEZONE
        ).date(),
    )
    events: list[str] = []

    def fake_gate(path: Path, *, launch_nonce: str) -> runtime_liveness.JobGate:
        assert path == config.job_gate_path
        assert launch_nonce == config.launch_nonce
        events.append("job_gate")
        return runtime_liveness.JobGate(
            child_pid=os.getpid(),
            child_creation_time=psutil.Process().create_time(),
            supervisor_pid=os.getpid(),
        )

    async def handler(request: httpx.Request) -> httpx.Response:
        assert events and events[0] == "job_gate"
        if request.url.path.endswith("/schedule"):
            return httpx.Response(
                200,
                json={
                    "dates": [
                        {
                            "games": [
                                {
                                    "gamePk": 824410,
                                    "gameDate": (BASE + timedelta(minutes=1)).isoformat(),
                                }
                            ]
                        }
                    ]
                },
                request=request,
            )
        return httpx.Response(
            200,
            json=live_payload(abstract="Final", detailed="Final"),
            request=request,
        )

    original_publish = feed_observer.publish_public_pair

    def checked_publish(
        pair: feed_archive.CoherentFeedPair,
        *,
        anchor: policy.FeedLaunchAnchor,
        public_root: Path,
        trusted_root: Path,
    ) -> None:
        commit_files = tuple(
            (custody_root / "control" / "batches").rglob("commit-*.json")
        )
        assert commit_files
        events.append("public_after_commit")
        original_publish(
            pair,
            anchor=anchor,
            public_root=public_root,
            trusted_root=trusted_root,
        )

    monkeypatch.setattr(runtime_liveness, "wait_for_job_gate", fake_gate)
    monkeypatch.setattr(feed_observer, "POLL_TARGET_SECONDS", 0.01)
    monkeypatch.setattr(feed_observer, "FINAL_SETTLE_SECONDS", 0.0)
    monkeypatch.setattr(feed_observer, "publish_public_pair", checked_publish)
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        assert feed_observer.run_observer(config, client=client) == 0
    finally:
        asyncio.run(client.aclose())
    assert events[0] == "job_gate"
    assert events.count("public_after_commit") >= 1
    schedule = json.loads(config.schedule_snapshot_path.read_bytes())
    assert schedule["query_start_date"] == config.schedule_start.isoformat()
    assert schedule["raw_payload_base64"]
    terminal = json.loads(config.terminal_manifest_path.read_bytes())
    assert terminal["terminal_generation_id"]
    assert terminal["terminal_summary_sha256"]
    assert terminal["terminal_event_log_sha256"]
    assert terminal["artifacts"]["completion_receipt"]["sha256"]
    assert config.stop_sentinel.is_file()


@pytest.mark.skipif(sys.platform != "win32", reason="production supervisor is Windows-first")
def test_real_observer_runs_end_to_end_through_real_supervisor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_root = tmp_path / "runtime"
    custody_root = tmp_path / "custody"
    public_root = custody_root / "public"
    lock_root = tmp_path / "launch-locks"
    for path in (runtime_root, custody_root, public_root, lock_root):
        path.mkdir()
    base_feed_launch = anchor()
    feed_launch_value = json.loads(base_feed_launch.manifest_bytes)
    feed_launch_value["source_hashes"][
        "tests/v34/feed_observer_supervised_fixture.py"
    ] = hashlib.sha256(
        (policy.REPOSITORY_ROOT / "tests/v34/feed_observer_supervised_fixture.py").read_bytes()
    ).hexdigest()
    feed_launch = policy.verify_feed_launch_manifest_bytes(
        policy.canonical_json_bytes(feed_launch_value)
    )
    queue_launch = queue_anchor()
    feed_manifest = tmp_path / "feed-launch.json"
    queue_manifest = tmp_path / "queue-launch.json"
    feed_manifest.write_bytes(feed_launch.manifest_bytes)
    queue_manifest.write_bytes(queue_launch.manifest_bytes)
    source_sha256 = hashlib.sha256(
        (policy.REPOSITORY_ROOT / "scripts/v34/feed_observer.py").read_bytes()
    ).hexdigest()
    heartbeat_path = custody_root / "heartbeat.jsonl"
    job_gate_path = custody_root / "job-gate.json"
    stop_sentinel = custody_root / "stop.json"
    completion_receipt = custody_root / "completion.receipt.json"
    terminal_manifest = custody_root / "terminal-manifest.json"
    terminal_event_log = custody_root / "terminal-event-log.json"
    terminal_state = custody_root / "terminal-state.json"
    schedule_snapshot = custody_root / "schedule.json"
    feed_lock = lock_root / ".prospective-feed-v34-lock1.lock"
    monkeypatch.setattr(
        observer_supervisor,
        "_locked_feed_lock_paths",
        lambda: (feed_lock,),
    )
    artifact_paths = {
        "completion_receipt": completion_receipt,
        "heartbeat": heartbeat_path,
        "public_receipt": public_root / feed_observer.PUBLIC_RECEIPT_NAME,
        "public_summary": public_root / feed_observer.PUBLIC_SUMMARY_NAME,
        "schedule_snapshot": schedule_snapshot,
        "stop_sentinel": stop_sentinel,
        "terminal_event_log": terminal_event_log,
        "terminal_state": terminal_state,
    }
    ledger_roots = {
        "custody_control": custody_root / "control",
        "custody_source": custody_root / "source-archive",
        "runtime_control": runtime_root / "control",
        "runtime_games": runtime_root / "games",
    }
    policy_hashes = {
        "feed_launch_manifest_sha256": feed_launch.manifest_sha256,
        "primary_policy_sha256": policy.POLICY_CANONICAL_SHA256,
        "queue_launch_manifest_sha256": queue_launch.manifest_sha256,
    }
    source_hashes = cast("dict[str, str]", feed_launch.provenance["source_hashes"])
    custody_spec = observer_supervisor.FeedTerminalCustodySpec(
        terminal_manifest_path=terminal_manifest,
        completion_receipt_path=completion_receipt,
        stop_sentinel_path=stop_sentinel,
        artifact_paths=artifact_paths,
        ledger_roots=ledger_roots,
        expected_command_sha256="e" * 64,
        owned_lock_paths=(feed_lock,),
        owned_lock_roots=(lock_root,),
        source_hashes=source_hashes,
        policy_hashes=policy_hashes,
    )
    config_path = tmp_path / "observer-config.json"
    config_path.write_bytes(
        policy.canonical_json_bytes(
            {
                "completion_receipt_path": str(completion_receipt),
                "created_at": BASE.isoformat(),
                "custody_root": str(custody_root),
                "feed_launch_manifest": str(feed_manifest),
                "hard_stop_at": (BASE + timedelta(hours=1)).isoformat(),
                "heartbeat_path": str(heartbeat_path),
                "job_gate_path": str(job_gate_path),
                "launch_nonce": "v34-feed-observer-test",
                "public_root": str(public_root),
                "queue_launch_manifest": str(queue_manifest),
                "runtime_root": str(runtime_root),
                "schedule_end": BASE.astimezone(
                    feed_observer.MLB_SCHEDULE_TIMEZONE
                ).date().isoformat(),
                "schedule_snapshot_path": str(schedule_snapshot),
                "schedule_start": BASE.astimezone(
                    feed_observer.MLB_SCHEDULE_TIMEZONE
                ).date().isoformat(),
                "source_sha256": source_sha256,
                "stop_sentinel": str(stop_sentinel),
                "terminal_event_log_path": str(terminal_event_log),
                "terminal_manifest_path": str(terminal_manifest),
                "terminal_state_path": str(terminal_state),
            }
        )
    )
    stdout_path = tmp_path / "observer.stdout.log"
    stderr_path = tmp_path / "observer.stderr.log"
    supervisor_receipt = tmp_path / "supervisor-receipt.json"
    command = (
        str(Path(sys.base_prefix) / "python.exe"),
        str(Path("tests/v34/feed_observer_supervised_fixture.py").resolve()),
        str(config_path),
    )
    custody_spec = replace(
        custody_spec,
        expected_command_sha256=policy.canonical_sha256(list(command)),
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
        receipt_path=supervisor_receipt,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        launch_nonce="v34-feed-observer-test",
        run_signature=policy.FEED_RUN_SIGNATURE,
        source_sha256=source_sha256,
        policy_sha256=policy.POLICY_CANONICAL_SHA256,
        terminal_custody=custody_spec,
        env=child_env,
    )
    assert result == 0, stderr_path.read_text(encoding="utf-8")
    receipt = json.loads(supervisor_receipt.read_bytes())
    assert receipt["outcome"] == "child_exited"
    assert receipt["actual_os_exit_code"] == 0
    assert receipt["terminal_generation_id"]
    assert not feed_lock.exists()
