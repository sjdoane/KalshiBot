"""Fresh read-only MLB feed observer for the frozen V34 prospective run."""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Final, Never, cast
from uuid import uuid4
from zoneinfo import ZoneInfo

import httpx

from scripts.v34 import (
    batch_head_ledger,
    feed_archive,
    feed_lifecycle,
    feed_lineage,
    head_ledger,
    policy,
    prefix_dependency,
    runtime_liveness,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Mapping, Sequence

SCHEDULE_URL: Final = "https://statsapi.mlb.com/api/v1/schedule"
LIVE_FEED_URL: Final = "https://statsapi.mlb.com/api/v1.1/game/{game_pk}/feed/live"
HTTP_ATTEMPTS: Final = 2
HTTP_TIMEOUT_SECONDS: Final = 5.0
HTTP_RETRY_SECONDS: Final = 0.25
POLL_TARGET_SECONDS: Final = 3.0
MAX_HTTP_RESPONSE_BYTES: Final = 8 * 1024 * 1024
MAX_CONCURRENT_FEEDS: Final = 32
FINAL_SETTLE_SECONDS: Final = 60.0
MAX_HORIZON_SECONDS: Final = 24 * 60 * 60
MLB_SCHEDULE_TIMEZONE: Final = ZoneInfo("America/New_York")
PUBLIC_SUMMARY_NAME: Final = "summary.json"
PUBLIC_RECEIPT_NAME: Final = "summary.receipt.json"
COMPLETION_RECEIPT_NAME: Final = "completion.receipt.json"
TERMINAL_MANIFEST_NAME: Final = "terminal-artifact-manifest.json"
TERMINAL_EVENT_LOG_NAME: Final = "terminal-event-log.json"
TERMINAL_STATE_NAME: Final = "terminal-state.json"
PROHIBITED_DETAIL_TOKENS: Final = ("suspend", "postpon")


class FeedObserverFatalError(RuntimeError):
    """The frozen feed observer cannot continue or earn prospective credit."""


def _fatal(message: str, *, cause: Exception | None = None) -> Never:
    if cause is None:
        raise FeedObserverFatalError(message)
    raise FeedObserverFatalError(message) from cause


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _utc(value: object, *, field: str) -> datetime:
    if type(value) is not str:
        _fatal(f"{field} must be an ISO8601 string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        _fatal(f"{field} is not ISO8601", cause=exc)
    if parsed.tzinfo is None:
        _fatal(f"{field} must be timezone-aware")
    return parsed.astimezone(UTC)


def _exact_int(value: object, *, field: str, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        _fatal(f"{field} must be an exact integer at least {minimum}")
    return value


def _canonical_object(raw: bytes, *, field: str) -> dict[str, object]:
    try:
        parsed = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        _fatal(f"{field} is not valid JSON", cause=exc)
    if not isinstance(parsed, dict) or raw != policy.canonical_json_bytes(parsed):
        _fatal(f"{field} is not a canonical object")
    return cast("dict[str, object]", parsed)


@dataclass(frozen=True, slots=True)
class ScheduledGame:
    game_pk: int
    scheduled_at: str


@dataclass(frozen=True, slots=True)
class ProjectedGame:
    game_pk: int
    completed_plays: dict[str, object]
    official_current_total: int
    abstract_state: str
    detailed_state: str
    observed_at: str
    successful_poll_monotonic_ns: int

    def archived_state(self, anchor: policy.FeedLaunchAnchor, generation_id: str) -> dict[str, object]:
        return {
            **anchor.provenance,
            "abstract_state": self.abstract_state,
            "completed_plays": self.completed_plays,
            "detailed_state": self.detailed_state,
            "game_pk": self.game_pk,
            "generation_id": generation_id,
            "observed_at": self.observed_at,
            "official_current_total": self.official_current_total,
        }


@dataclass(frozen=True, slots=True)
class ObserverConfig:
    runtime_root: Path
    custody_root: Path
    feed_launch_manifest: Path
    queue_launch_manifest: Path
    heartbeat_path: Path
    job_gate_path: Path
    stop_sentinel: Path
    public_root: Path
    schedule_snapshot_path: Path
    completion_receipt_path: Path
    terminal_manifest_path: Path
    terminal_event_log_path: Path
    terminal_state_path: Path
    launch_nonce: str
    source_sha256: str
    created_at: str
    hard_stop_at: str
    schedule_start: date
    schedule_end: date


async def _bounded_response_bytes(response: httpx.Response) -> bytes:
    content_length = response.headers.get("content-length")
    if content_length is not None:
        try:
            claimed = int(content_length)
        except ValueError as exc:
            _fatal("HTTP Content-Length is malformed", cause=exc)
        if claimed < 0 or claimed > MAX_HTTP_RESPONSE_BYTES:
            _fatal("HTTP response exceeds its frozen byte bound")
    value = bytearray()
    async for chunk in response.aiter_bytes():
        value.extend(chunk)
        if len(value) > MAX_HTTP_RESPONSE_BYTES:
            _fatal("HTTP response exceeds its frozen byte bound")
    return bytes(value)


async def bounded_get_json(
    client: httpx.AsyncClient,
    url: str,
    *,
    params: Mapping[str, str | int | float | bool | None] | None = None,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> tuple[dict[str, object], bytes]:
    """GET one official payload using the exact two-attempt frozen policy."""

    if not isinstance(client, httpx.AsyncClient) or type(url) is not str or not url:
        _fatal("bounded HTTP request arguments are invalid")
    last_error: Exception | None = None
    for attempt in range(HTTP_ATTEMPTS):
        try:
            async with asyncio.timeout(HTTP_TIMEOUT_SECONDS):
                async with client.stream(
                    "GET",
                    url,
                    params=params,
                    timeout=None,
                ) as response:
                    response.raise_for_status()
                    raw = await _bounded_response_bytes(response)
            parsed = json.loads(raw)
            if not isinstance(parsed, dict):
                _fatal("official HTTP payload is not an object")
            return cast("dict[str, object]", parsed), raw
        except (
            TimeoutError,
            httpx.HTTPError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            FeedObserverFatalError,
        ) as exc:
            last_error = exc
        if attempt + 1 < HTTP_ATTEMPTS:
            await sleep(HTTP_RETRY_SECONDS)
    assert last_error is not None
    _fatal("official HTTP request exhausted its frozen attempts", cause=last_error)


def parse_schedule(
    payload: Mapping[str, object],
    *,
    launch_at: datetime,
    hard_stop_at: datetime,
) -> tuple[ScheduledGame, ...]:
    """Freeze every MLB game scheduled inside the exact observer horizon."""

    dates = payload.get("dates")
    if not isinstance(dates, list):
        _fatal("MLB schedule dates are missing")
    games: dict[int, ScheduledGame] = {}
    for date_row in dates:
        if not isinstance(date_row, dict):
            _fatal("MLB schedule date row is malformed")
        values = date_row.get("games")
        if not isinstance(values, list):
            _fatal("MLB schedule game list is malformed")
        for raw_game in values:
            if not isinstance(raw_game, dict):
                _fatal("MLB schedule game row is malformed")
            game_pk = _exact_int(raw_game.get("gamePk"), field="schedule.gamePk", minimum=1)
            scheduled = _utc(raw_game.get("gameDate"), field="schedule.gameDate")
            if scheduled < launch_at or scheduled >= hard_stop_at:
                continue
            candidate = ScheduledGame(game_pk=game_pk, scheduled_at=scheduled.isoformat())
            existing = games.get(game_pk)
            if existing is not None and existing != candidate:
                _fatal("MLB schedule duplicates a game with different time")
            games[game_pk] = candidate
    if not games:
        _fatal("MLB schedule has no game inside the frozen observer horizon")
    return tuple(sorted(games.values(), key=lambda row: (row.scheduled_at, row.game_pk)))


async def fetch_schedule(
    client: httpx.AsyncClient,
    config: ObserverConfig,
) -> tuple[tuple[ScheduledGame, ...], bytes]:
    payload, raw_payload = await bounded_get_json(
        client,
        SCHEDULE_URL,
        params={
            "endDate": config.schedule_end.isoformat(),
            "hydrate": "team",
            "sportId": 1,
            "startDate": config.schedule_start.isoformat(),
        },
    )
    games = parse_schedule(
        payload,
        launch_at=_utc(config.created_at, field="observer.created_at"),
        hard_stop_at=_utc(config.hard_stop_at, field="observer.hard_stop_at"),
    )
    frozen = policy.canonical_json_bytes(
        {
            "fetched_at": datetime.now(tz=UTC).isoformat(),
            "games": [
                {"game_pk": row.game_pk, "scheduled_at": row.scheduled_at}
                for row in games
            ],
            "kind": "v34_frozen_mlb_schedule",
            "launch_nonce": config.launch_nonce,
            "horizon_hard_stop_at": _utc(
                config.hard_stop_at,
                field="observer.hard_stop_at",
            ).isoformat(),
            "horizon_start_at": _utc(
                config.created_at,
                field="observer.created_at",
            ).isoformat(),
            "query_end_date": config.schedule_end.isoformat(),
            "query_start_date": config.schedule_start.isoformat(),
            "raw_payload_base64": base64.b64encode(raw_payload).decode("ascii"),
            "raw_payload_sha256": _sha256(raw_payload),
            "run_signature": policy.FEED_RUN_SIGNATURE,
        }
    )
    return games, frozen


def project_live_feed(
    payload: Mapping[str, object],
    *,
    game_pk: int,
    observed_at: datetime,
    successful_poll_monotonic_ns: int,
) -> ProjectedGame | None:
    """Build only the independently frozen V34 projection from official data."""

    game_pk = _exact_int(game_pk, field="game_pk", minimum=1)
    if payload.get("gamePk") != game_pk or type(payload.get("gamePk")) is not int:
        _fatal("official live feed gamePk differs from the requested game")
    if observed_at.tzinfo is None:
        _fatal("feed observation time must be timezone-aware")
    observed = observed_at.astimezone(UTC)
    poll_ns = _exact_int(
        successful_poll_monotonic_ns,
        field="successful_poll_monotonic_ns",
        minimum=1,
    )
    game_data = payload.get("gameData")
    live_data = payload.get("liveData")
    if not isinstance(game_data, dict) or not isinstance(live_data, dict):
        _fatal("official live feed root is malformed")
    status = game_data.get("status")
    if not isinstance(status, dict):
        _fatal("official live feed status is missing")
    abstract = status.get("abstractGameState")
    detailed = status.get("detailedState")
    if type(abstract) is not str or type(detailed) is not str or not detailed:
        _fatal("official live feed status values are malformed")
    lowered = detailed.casefold()
    if any(token in lowered for token in PROHIBITED_DETAIL_TOKENS):
        _fatal("official live feed entered a prohibited status")
    if abstract not in prefix_dependency.ALLOWED_ABSTRACT_STATES:
        return None

    plays_root = live_data.get("plays")
    linescore = live_data.get("linescore")
    if not isinstance(plays_root, dict) or not isinstance(linescore, dict):
        _fatal("official live feed play or linescore root is malformed")
    raw_plays = plays_root.get("allPlays")
    if not isinstance(raw_plays, list):
        _fatal("official live feed allPlays is missing")
    completed: dict[str, object] = {}
    seen_indices: set[int] = set()
    expected_completed_index = 0
    saw_incomplete = False
    for raw_play in raw_plays:
        if not isinstance(raw_play, dict):
            _fatal("official live feed play is malformed")
        about = raw_play.get("about")
        result = raw_play.get("result")
        if not isinstance(about, dict) or not isinstance(result, dict):
            _fatal("official live feed play projection roots are malformed")
        index = _exact_int(about.get("atBatIndex"), field="play.atBatIndex")
        if index in seen_indices:
            _fatal("official play sequence contains a duplicate atBatIndex")
        seen_indices.add(index)
        if about.get("isComplete") is not True:
            saw_incomplete = True
            continue
        if saw_incomplete:
            _fatal("official completed play follows an incomplete play")
        if index != expected_completed_index:
            _fatal("official completed plays are reordered or noncontiguous")
        expected_completed_index += 1
        projection = {
            "about": {
                "atBatIndex": index,
                "endTime": about.get("endTime"),
                "hasReview": about.get("hasReview"),
                "isComplete": about.get("isComplete"),
                "isScoringPlay": about.get("isScoringPlay"),
            },
            "result": {
                "awayScore": result.get("awayScore"),
                "description": result.get("description"),
                "event": result.get("event"),
                "eventType": result.get("eventType"),
                "homeScore": result.get("homeScore"),
                "rbi": result.get("rbi"),
            },
            "review_details": raw_play.get("reviewDetails"),
        }
        try:
            completed[str(index)] = prefix_dependency.validate_projection(
                projection,
                expected_index=index,
            )
        except (TypeError, ValueError) as exc:
            _fatal(f"official play {index} does not match the frozen projection", cause=exc)
    teams = linescore.get("teams")
    if not isinstance(teams, dict):
        _fatal("official linescore teams are missing")
    away = teams.get("away")
    home = teams.get("home")
    if not isinstance(away, dict) or not isinstance(home, dict):
        _fatal("official linescore team rows are malformed")
    away_runs = _exact_int(away.get("runs"), field="linescore.away.runs")
    home_runs = _exact_int(home.get("runs"), field="linescore.home.runs")
    return ProjectedGame(
        game_pk=game_pk,
        completed_plays=completed,
        official_current_total=away_runs + home_runs,
        abstract_state=abstract,
        detailed_state=detailed,
        observed_at=observed.isoformat(),
        successful_poll_monotonic_ns=poll_ns,
    )


async def fetch_projected_games(
    client: httpx.AsyncClient,
    games: Sequence[ScheduledGame],
    *,
    prior_observed_game_pks: frozenset[int] = frozenset(),
    wall_now: Callable[[], datetime] = lambda: datetime.now(tz=UTC),
    monotonic_ns: Callable[[], int] = time.monotonic_ns,
) -> tuple[ProjectedGame, ...]:
    """Fetch one complete official generation with bounded parallelism."""

    if not games or len(games) > batch_head_ledger.MAX_BATCH_OPERATIONS:
        _fatal("observer game population is empty or exceeds the batch bound")

    semaphore = asyncio.Semaphore(min(MAX_CONCURRENT_FEEDS, len(games)))

    async def fetch_one(
        row: ScheduledGame,
    ) -> tuple[ScheduledGame, dict[str, object], int]:
        async with semaphore:
            payload, _raw = await bounded_get_json(
                client,
                LIVE_FEED_URL.format(game_pk=row.game_pk),
            )
        return row, payload, monotonic_ns()

    results: dict[int, tuple[dict[str, object], int]] = {}
    try:
        fetched = await asyncio.gather(*(fetch_one(game) for game in games))
    except Exception as exc:
        if isinstance(exc, FeedObserverFatalError):
            raise
        _fatal("parallel official feed fetch failed", cause=exc)
    for row, payload, success_ns in fetched:
        if row.game_pk in results:
            _fatal("parallel feed fetch returned a duplicate game")
        results[row.game_pk] = (payload, success_ns)
    if set(results) != {game.game_pk for game in games}:
        _fatal("parallel official feed generation is incomplete")
    observed = wall_now().astimezone(UTC)
    projected: list[ProjectedGame] = []
    for game in games:
        payload, success_ns = results[game.game_pk]
        candidate = project_live_feed(
            payload,
            game_pk=game.game_pk,
            observed_at=observed,
            successful_poll_monotonic_ns=success_ns,
        )
        if candidate is None:
            if game.game_pk in prior_observed_game_pks:
                _fatal("previously observed game regressed outside Live or Final")
            continue
        projected.append(candidate)
    return tuple(sorted(projected, key=lambda row: row.game_pk))


def build_source_pair(
    projected: Sequence[ProjectedGame],
    *,
    lifecycle_states: Mapping[int, feed_lifecycle.FeedGameState],
    anchor: policy.FeedLaunchAnchor,
    generation_id: str,
    cycle_observed_at: str,
) -> feed_archive.CoherentFeedPair:
    if not projected:
        _fatal("a source pair requires at least one Live or Final game")
    if len({row.game_pk for row in projected}) != len(projected):
        _fatal("a source pair contains a duplicate game")
    if set(lifecycle_states) != {row.game_pk for row in projected}:
        _fatal("source pair lifecycle-state population differs")
    serialized_states: dict[str, object] = {}
    for row in projected:
        state = lifecycle_states[row.game_pk]
        try:
            serialized = json.loads(feed_lineage.serialize_game_state(state))
        except (TypeError, ValueError, feed_lineage.FeedLineageFatalError) as exc:
            _fatal("source pair lifecycle state is invalid", cause=exc)
        if (
            not isinstance(serialized, dict)
            or state.last_completed_plays_bytes
            != policy.canonical_json_bytes(row.completed_plays)
            or state.last_official_current_total != row.official_current_total
            or state.last_abstract_state != row.abstract_state
            or state.last_detailed_state != row.detailed_state
            or state.last_observed_at != row.observed_at
            or state.last_successful_poll_monotonic_ns
            != row.successful_poll_monotonic_ns
        ):
            _fatal("source pair lifecycle state differs from its official projection")
        serialized_states[str(row.game_pk)] = serialized
    summary_bytes = policy.canonical_json_bytes(
        {
            **anchor.provenance,
            "cycle_observed_at": _utc(
                cycle_observed_at,
                field="cycle_observed_at",
            ).isoformat(),
            "game_states": {
                str(row.game_pk): row.archived_state(anchor, generation_id)
                for row in sorted(projected, key=lambda item: item.game_pk)
            },
            "generation_id": generation_id,
            "kind": "v34_feed_generation",
            "lifecycle_states": serialized_states,
        }
    )
    receipt_bytes = policy.canonical_json_bytes(
        {
            **anchor.provenance,
            "generation_id": generation_id,
            "summary_sha256": _sha256(summary_bytes),
        }
    )
    pair = feed_archive.CoherentFeedPair(
        generation_id=generation_id,
        summary_bytes=summary_bytes,
        feed_receipt_bytes=receipt_bytes,
    )
    pair.validate(anchor)
    return pair


def _atomic_replace_bytes(path: Path, raw: bytes, *, trusted_root: Path) -> None:
    feed_archive._assert_no_redirecting_components(trusted_root, path)
    if not path.parent.is_dir():
        _fatal("atomic publication parent is missing")
    temp = path.parent / f".{path.name}.v34tmp-{uuid4().hex}.tmp"
    try:
        with temp.open("xb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        temp.replace(path)
        feed_archive._fsync_directory(path.parent)
    except OSError as exc:
        _fatal(f"atomic publication failed for {path.name}", cause=exc)
    finally:
        if temp.exists():
            temp.unlink()
    if path.read_bytes() != raw:
        _fatal(f"atomic publication differs on disk for {path.name}")
    feed_archive._assert_no_redirecting_components(trusted_root, path)


def publish_public_pair(
    pair: feed_archive.CoherentFeedPair,
    *,
    anchor: policy.FeedLaunchAnchor,
    public_root: Path,
    trusted_root: Path,
) -> None:
    """Publish summary then receipt only after the source batch COMMIT exists."""

    pair.validate(anchor)
    _atomic_replace_bytes(
        public_root / PUBLIC_SUMMARY_NAME,
        pair.summary_bytes,
        trusted_root=trusted_root,
    )
    _atomic_replace_bytes(
        public_root / PUBLIC_RECEIPT_NAME,
        pair.feed_receipt_bytes,
        trusted_root=trusted_root,
    )
    observed = feed_archive.read_coherent_feed_pair(
        public_root / PUBLIC_SUMMARY_NAME,
        public_root / PUBLIC_RECEIPT_NAME,
        anchor=anchor,
    )
    if observed != pair:
        _fatal("public feed pair differs from the committed generation")


def _source_requests(
    projected: Sequence[ProjectedGame],
    *,
    session: batch_head_ledger.BatchLedgerSession,
    recorded_at: str,
) -> tuple[batch_head_ledger.BatchTransitionRequest, ...]:
    snapshots = dict(session.snapshots)
    requests: list[batch_head_ledger.BatchTransitionRequest] = []
    for row in sorted(projected, key=lambda item: item.game_pk):
        snapshot = snapshots.get(row.game_pk)
        if snapshot is None:
            _fatal("registered game has no retained empty snapshot")
        prior = snapshot.state_for(row.game_pk)
        transition = feed_lifecycle.transition_game(
            prior,
            game_pk=row.game_pk,
            completed_plays=row.completed_plays,
            official_current_total=row.official_current_total,
            abstract_state=row.abstract_state,
            detailed_state=row.detailed_state,
            observed_at=_utc(row.observed_at, field="projected.observed_at"),
            successful_poll_monotonic_ns=row.successful_poll_monotonic_ns,
            expected_prior_state_commitment_sha256=(
                None if prior is None else prior.state_commitment_sha256
            ),
        )
        requests.append(
            batch_head_ledger.BatchTransitionRequest(
                transition=transition,
                recorded_at=recorded_at,
                expected_snapshot=snapshot,
            )
        )
    return tuple(requests)


def _stop_reason(path: Path, *, launch_nonce: str) -> str | None:
    if not path.exists():
        return None
    row = _canonical_object(path.read_bytes(), field="feed stop sentinel")
    if set(row) != {"launch_nonce", "reason", "requested_at"}:
        _fatal("feed stop sentinel keys differ")
    if row.get("launch_nonce") != launch_nonce:
        _fatal("feed stop sentinel launch nonce differs")
    _utc(row.get("requested_at"), field="stop.requested_at")
    reason = row.get("reason")
    if type(reason) is not str or not reason or len(reason.encode("utf-8")) > 256:
        _fatal("feed stop sentinel reason is invalid")
    return reason


def _file_binding(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    raw = path.read_bytes()
    return {"path": str(path.resolve()), "sha256": _sha256(raw), "size": len(raw)}


def _required_file_binding(path: Path) -> dict[str, object]:
    binding = _file_binding(path)
    if binding is None:
        _fatal(f"required terminal artifact is missing: {path.name}")
    return binding


def _ensure_stop_sentinel(config: ObserverConfig, *, outcome: str) -> str:
    if not config.stop_sentinel.exists():
        feed_archive._write_create_once(
            config.stop_sentinel,
            policy.canonical_json_bytes(
                {
                    "launch_nonce": config.launch_nonce,
                    "reason": outcome,
                    "requested_at": datetime.now(tz=UTC).isoformat(),
                }
            ),
        )
    _stop_reason(config.stop_sentinel, launch_nonce=config.launch_nonce)
    return _sha256(config.stop_sentinel.read_bytes())


def _terminal_ledger_inventory(
    config: ObserverConfig,
) -> tuple[dict[str, object], ...]:
    inventory: list[dict[str, object]] = []
    roots = (
        ("custody_control", config.custody_root / "control", config.custody_root),
        ("custody_source", config.custody_root / "source-archive", config.custody_root),
        ("runtime_control", config.runtime_root / "control", config.runtime_root),
        ("runtime_games", config.runtime_root / "games", config.runtime_root),
    )
    for label, root, trusted_root in roots:
        if not root.is_dir():
            _fatal(f"terminal ledger root is missing: {label}")
        for path in sorted(
            item
            for item in root.rglob("*")
            if item.is_file() and not item.name.endswith(".v34append.lock")
        ):
            feed_archive._assert_no_redirecting_components(trusted_root, path)
            raw = path.read_bytes()
            inventory.append(
                {
                    "root": label,
                    "relative_path": path.relative_to(root).as_posix(),
                    "sha256": _sha256(raw),
                    "size": len(raw),
                }
            )
    if not inventory:
        _fatal("terminal ledger inventory is empty")
    return tuple(inventory)


def _complete_run(
    publisher: runtime_liveness.HeartbeatPublisher,
    *,
    config: ObserverConfig,
    cycle_started_ns: int,
    outcome: str,
    session: batch_head_ledger.BatchLedgerSession,
    last_pair: feed_archive.CoherentFeedPair | None,
    feed_anchor: policy.FeedLaunchAnchor,
    queue_anchor: policy.QueueLaunchAnchor,
) -> None:
    stop_sentinel_sha256 = _ensure_stop_sentinel(config, outcome=outcome)
    terminal_event_log = policy.canonical_json_bytes(
        {
            **feed_anchor.provenance,
            "batch_count": session.batch_count,
            "inventory": _terminal_ledger_inventory(config),
            "kind": "v34_feed_terminal_event_log",
            "latest_batch_commit_sha256": session.state.prior_commit_sha256,
            "latest_batch_name": session.latest_batch_name,
            "registry_manifest_sha256": session.manifest_sha256,
        }
    )
    feed_archive._write_create_once(
        config.terminal_event_log_path,
        terminal_event_log,
    )
    terminal_game_states: dict[str, object] = {}
    for game_pk, snapshot in sorted(session.snapshots):
        state = snapshot.state_for(game_pk)
        terminal_game_states[str(game_pk)] = (
            None if state is None else json.loads(feed_lineage.serialize_game_state(state))
        )
    terminal_state = policy.canonical_json_bytes(
        {
            **feed_anchor.provenance,
            "game_states": terminal_game_states,
            "kind": "v34_feed_terminal_state",
            "terminal_generation_id": (
                None if last_pair is None else last_pair.generation_id
            ),
            "terminal_summary_sha256": (
                None if last_pair is None else last_pair.summary_sha256
            ),
        }
    )
    feed_archive._write_create_once(config.terminal_state_path, terminal_state)
    receipt = policy.canonical_json_bytes(
        {
            "batch_count": session.batch_count,
            "capital_eligible": False,
            "completed_at": datetime.now(tz=UTC).isoformat(),
            "last_feed_generation_id": None if last_pair is None else last_pair.generation_id,
            "last_feed_summary_sha256": None if last_pair is None else last_pair.summary_sha256,
            "launch_nonce": config.launch_nonce,
            "outcome": outcome,
            "run_signature": policy.FEED_RUN_SIGNATURE,
            "stop_sentinel_sha256": stop_sentinel_sha256,
            "terminal_event_log_sha256": _sha256(terminal_event_log),
            "terminal_state_sha256": _sha256(terminal_state),
        }
    )
    feed_archive._write_create_once(config.completion_receipt_path, receipt)
    publisher.publish(
        "progress:completion_intent",
        cycle_started_monotonic_ns=cycle_started_ns,
    )
    publisher.publish(
        runtime_liveness.CYCLE_COMPLETE_PHASE,
        cycle_started_monotonic_ns=cycle_started_ns,
    )
    publisher.close()
    terminal = policy.canonical_json_bytes(
        {
            "artifacts": {
                "completion_receipt": _required_file_binding(
                    config.completion_receipt_path
                ),
                "heartbeat": _required_file_binding(config.heartbeat_path),
                "public_receipt": _required_file_binding(
                    config.public_root / PUBLIC_RECEIPT_NAME
                ),
                "public_summary": _required_file_binding(
                    config.public_root / PUBLIC_SUMMARY_NAME
                ),
                "schedule_snapshot": _required_file_binding(
                    config.schedule_snapshot_path
                ),
                "stop_sentinel": _required_file_binding(config.stop_sentinel),
                "terminal_event_log": _required_file_binding(
                    config.terminal_event_log_path
                ),
                "terminal_state": _required_file_binding(config.terminal_state_path),
            },
            "batch_count": session.batch_count,
            "created_at": datetime.now(tz=UTC).isoformat(),
            "kind": "v34_feed_terminal_artifact_manifest",
            "latest_batch_name": session.latest_batch_name,
            "latest_batch_commit_sha256": session.state.prior_commit_sha256,
            "launch_nonce": config.launch_nonce,
            "outcome": outcome,
            "policy_hashes": {
                "feed_launch_manifest_sha256": feed_anchor.manifest_sha256,
                "primary_policy_sha256": policy.POLICY_CANONICAL_SHA256,
                "queue_launch_manifest_sha256": queue_anchor.manifest_sha256,
            },
            "registry_manifest_sha256": session.manifest_sha256,
            "run_signature": policy.FEED_RUN_SIGNATURE,
            "source_hashes": feed_anchor.provenance["source_hashes"],
            "stop_sentinel_sha256": stop_sentinel_sha256,
            "terminal_event_log_sha256": _sha256(terminal_event_log),
            "terminal_generation_id": (
                None if last_pair is None else last_pair.generation_id
            ),
            "terminal_state_sha256": _sha256(terminal_state),
            "terminal_summary_sha256": (
                None if last_pair is None else last_pair.summary_sha256
            ),
        }
    )
    feed_archive._write_create_once(config.terminal_manifest_path, terminal)


def _validate_config(config: ObserverConfig) -> tuple[policy.FeedLaunchAnchor, policy.QueueLaunchAnchor]:
    if not isinstance(config, ObserverConfig):
        _fatal("observer config has the wrong type")
    if type(config.launch_nonce) is not str or not config.launch_nonce:
        _fatal("observer launch nonce is empty")
    policy.validate_sha256(config.source_sha256, field="observer.source_sha256")
    created = _utc(config.created_at, field="observer.created_at")
    hard_stop = _utc(config.hard_stop_at, field="observer.hard_stop_at")
    duration = (hard_stop - created).total_seconds()
    if duration <= 0 or duration > MAX_HORIZON_SECONDS:
        _fatal("observer horizon is outside the frozen 24-hour maximum")
    expected_schedule_start = created.astimezone(MLB_SCHEDULE_TIMEZONE).date()
    expected_schedule_end = (hard_stop - timedelta(microseconds=1)).astimezone(
        MLB_SCHEDULE_TIMEZONE
    ).date()
    if (
        config.schedule_start != expected_schedule_start
        or config.schedule_end != expected_schedule_end
    ):
        _fatal("observer schedule dates do not cover the exact frozen horizon")
    feed_anchor = policy.verify_feed_launch_manifest_bytes(
        config.feed_launch_manifest.read_bytes()
    )
    queue_anchor = policy.verify_queue_launch_manifest_bytes(
        config.queue_launch_manifest.read_bytes()
    )
    if feed_anchor.provenance.get("launch_nonce") != config.launch_nonce:
        _fatal("observer launch nonce differs from feed manifest")
    actual_source_sha256 = _sha256(Path(__file__).resolve().read_bytes())
    feed_source_hashes = feed_anchor.provenance.get("source_hashes")
    if (
        config.source_sha256 != actual_source_sha256
        or not isinstance(feed_source_hashes, dict)
        or feed_source_hashes.get("scripts/v34/feed_observer.py")
        != actual_source_sha256
    ):
        _fatal("observer source hash differs from its bytes or launch manifest")
    manifest = _canonical_object(
        config.feed_launch_manifest.read_bytes(),
        field="feed launch manifest",
    )
    if _utc(manifest.get("created_at"), field="launch.created_at") != created:
        _fatal("observer creation time differs from feed manifest")
    for root in (config.runtime_root, config.custody_root, config.public_root):
        if not root.is_dir():
            _fatal("observer storage root is missing")
    fresh_paths = (
        config.schedule_snapshot_path,
        config.completion_receipt_path,
        config.terminal_manifest_path,
        config.terminal_event_log_path,
        config.terminal_state_path,
        config.stop_sentinel,
        config.public_root / PUBLIC_SUMMARY_NAME,
        config.public_root / PUBLIC_RECEIPT_NAME,
    )
    for path in fresh_paths:
        feed_archive._assert_no_redirecting_components(config.custody_root, path)
        if path.exists() or not path.parent.is_dir():
            _fatal("observer output path is not fresh or its parent is missing")
    return feed_anchor, queue_anchor


async def _run_observer_async(
    config: ObserverConfig,
    *,
    client: httpx.AsyncClient | None = None,
) -> int:
    """Run the wholly fresh observer until all games settle or the hard stop."""

    gate = runtime_liveness.wait_for_job_gate(
        config.job_gate_path,
        launch_nonce=config.launch_nonce,
    )
    feed_anchor, queue_anchor = _validate_config(config)
    own_client = client is None
    http = httpx.AsyncClient(
        headers={"Accept": "application/json", "User-Agent": "KalshiV34Observer/1.0"},
        follow_redirects=False,
    ) if client is None else client
    publisher = runtime_liveness.HeartbeatPublisher(
        config.heartbeat_path,
        launch_nonce=config.launch_nonce,
        run_signature=policy.FEED_RUN_SIGNATURE,
        child_pid=gate.child_pid,
        child_creation_time=gate.child_creation_time,
        source_sha256=config.source_sha256,
        policy_sha256=policy.POLICY_CANONICAL_SHA256,
    )
    session: batch_head_ledger.BatchLedgerSession | None = None
    try:
        initialization_ns = time.monotonic_ns()
        publisher.publish(
            runtime_liveness.CYCLE_START_PHASE,
            cycle_started_monotonic_ns=initialization_ns,
            monotonic_ns=initialization_ns,
        )
        games, schedule_snapshot = await fetch_schedule(http, config)
        feed_archive._write_create_once(
            config.schedule_snapshot_path,
            schedule_snapshot,
        )
        publisher.publish(
            "progress:schedule_frozen",
            cycle_started_monotonic_ns=initialization_ns,
        )
        ledger_config = head_ledger.HeadLedgerConfig(
            runtime_root=config.runtime_root,
            custody_root=config.custody_root,
            feed_anchor=feed_anchor,
            queue_anchor=queue_anchor,
            created_at=config.created_at,
            custody_class="logical_read_only",
        )
        head_ledger.initialize_head_ledger(ledger_config)
        for game in games:
            head_ledger.register_game(
                ledger_config,
                game_pk=game.game_pk,
                registered_at=datetime.now(tz=UTC).isoformat(),
            )
            publisher.publish(
                "progress:game_registered",
                cycle_started_monotonic_ns=initialization_ns,
            )
        session = batch_head_ledger.open_batch_session(ledger_config)
        publisher.publish(
            "progress:registry_frozen",
            cycle_started_monotonic_ns=initialization_ns,
        )
        publisher.publish(
            runtime_liveness.CYCLE_COMPLETE_PHASE,
            cycle_started_monotonic_ns=initialization_ns,
        )

        hard_stop = _utc(config.hard_stop_at, field="observer.hard_stop_at")
        wall_remaining_ns = max(
            0,
            int((hard_stop - datetime.now(tz=UTC)).total_seconds() * 1_000_000_000),
        )
        monotonic_hard_stop_ns = time.monotonic_ns() + wall_remaining_ns
        final_since_ns: int | None = None
        last_pair: feed_archive.CoherentFeedPair | None = None
        next_cycle_ns = time.monotonic_ns()
        while True:
            now_ns = time.monotonic_ns()
            if now_ns < next_cycle_ns:
                await asyncio.sleep((next_cycle_ns - now_ns) / 1_000_000_000)
            cycle_started_ns = time.monotonic_ns()
            next_cycle_ns = cycle_started_ns + int(POLL_TARGET_SECONDS * 1_000_000_000)
            publisher.publish(
                runtime_liveness.CYCLE_START_PHASE,
                cycle_started_monotonic_ns=cycle_started_ns,
                monotonic_ns=cycle_started_ns,
            )
            stop_reason = _stop_reason(config.stop_sentinel, launch_nonce=config.launch_nonce)
            wall_now = datetime.now(tz=UTC)
            if stop_reason is not None:
                _complete_run(
                    publisher,
                    config=config,
                    cycle_started_ns=cycle_started_ns,
                    outcome=f"stopped:{stop_reason}",
                    session=session,
                    last_pair=last_pair,
                    feed_anchor=feed_anchor,
                    queue_anchor=queue_anchor,
                )
                return 0
            if wall_now >= hard_stop or cycle_started_ns >= monotonic_hard_stop_ns:
                _complete_run(
                    publisher,
                    config=config,
                    cycle_started_ns=cycle_started_ns,
                    outcome="hard_stop",
                    session=session,
                    last_pair=last_pair,
                    feed_anchor=feed_anchor,
                    queue_anchor=queue_anchor,
                )
                return 0

            prior_observed_game_pks = frozenset(
                game_pk
                for game_pk, snapshot in session.snapshots
                if snapshot.state_for(game_pk) is not None
            )
            projected = await fetch_projected_games(
                http,
                games,
                prior_observed_game_pks=prior_observed_game_pks,
            )
            publisher.publish(
                "progress:official_generation_fetched",
                cycle_started_monotonic_ns=cycle_started_ns,
            )
            if projected:
                recorded_at = datetime.now(tz=UTC).isoformat()
                generation_id = f"g{session.batch_count + 1:08d}"
                requests = _source_requests(
                    projected,
                    session=session,
                    recorded_at=recorded_at,
                )
                pair = build_source_pair(
                    projected,
                    lifecycle_states={
                        request.transition.state.game_pk: request.transition.state
                        for request in requests
                    },
                    anchor=feed_anchor,
                    generation_id=generation_id,
                    cycle_observed_at=recorded_at,
                )
                committed = batch_head_ledger.append_committed_batch(
                    session,
                    requests,
                    source_pair=pair,
                )
                if committed.capital_eligible:
                    _fatal("logical observer unexpectedly became capital eligible")
                publisher.publish(
                    "progress:batch_committed",
                    cycle_started_monotonic_ns=cycle_started_ns,
                )
                publish_public_pair(
                    pair,
                    anchor=feed_anchor,
                    public_root=config.public_root,
                    trusted_root=config.custody_root,
                )
                last_pair = pair
                publisher.publish(
                    "progress:public_pair_published",
                    cycle_started_monotonic_ns=cycle_started_ns,
                )

            all_final = len(projected) == len(games) and all(
                row.abstract_state == "Final" for row in projected
            )
            if all_final:
                if final_since_ns is None:
                    final_since_ns = cycle_started_ns
            else:
                final_since_ns = None
            if (
                final_since_ns is not None
                and cycle_started_ns - final_since_ns
                > int(FINAL_SETTLE_SECONDS * 1_000_000_000)
            ):
                _complete_run(
                    publisher,
                    config=config,
                    cycle_started_ns=cycle_started_ns,
                    outcome="slate_final",
                    session=session,
                    last_pair=last_pair,
                    feed_anchor=feed_anchor,
                    queue_anchor=queue_anchor,
                )
                return 0
            publisher.publish(
                runtime_liveness.CYCLE_COMPLETE_PHASE,
                cycle_started_monotonic_ns=cycle_started_ns,
            )
    finally:
        publisher.close()
        if session is not None:
            session.close()
        if own_client:
            await http.aclose()


def run_observer(
    config: ObserverConfig,
    *,
    client: httpx.AsyncClient | None = None,
) -> int:
    """Run the async observer under one hard-deadline event loop."""

    return asyncio.run(_run_observer_async(config, client=client))


def _config_from_args(args: argparse.Namespace) -> ObserverConfig:
    return ObserverConfig(
        runtime_root=args.runtime_root,
        custody_root=args.custody_root,
        feed_launch_manifest=args.feed_launch_manifest,
        queue_launch_manifest=args.queue_launch_manifest,
        heartbeat_path=args.heartbeat_path,
        job_gate_path=args.job_gate_path,
        stop_sentinel=args.stop_sentinel,
        public_root=args.public_root,
        schedule_snapshot_path=args.schedule_snapshot_path,
        completion_receipt_path=args.completion_receipt_path,
        terminal_manifest_path=args.terminal_manifest_path,
        terminal_event_log_path=args.terminal_event_log_path,
        terminal_state_path=args.terminal_state_path,
        launch_nonce=args.launch_nonce,
        source_sha256=args.source_sha256,
        created_at=args.created_at,
        hard_stop_at=args.hard_stop_at,
        schedule_start=date.fromisoformat(args.schedule_start),
        schedule_end=date.fromisoformat(args.schedule_end),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--custody-root", type=Path, required=True)
    parser.add_argument("--feed-launch-manifest", type=Path, required=True)
    parser.add_argument("--queue-launch-manifest", type=Path, required=True)
    parser.add_argument("--heartbeat-path", type=Path, required=True)
    parser.add_argument("--job-gate-path", type=Path, required=True)
    parser.add_argument("--stop-sentinel", type=Path, required=True)
    parser.add_argument("--public-root", type=Path, required=True)
    parser.add_argument("--schedule-snapshot-path", type=Path, required=True)
    parser.add_argument("--completion-receipt-path", type=Path, required=True)
    parser.add_argument("--terminal-manifest-path", type=Path, required=True)
    parser.add_argument("--terminal-event-log-path", type=Path, required=True)
    parser.add_argument("--terminal-state-path", type=Path, required=True)
    parser.add_argument("--launch-nonce", required=True)
    parser.add_argument("--source-sha256", required=True)
    parser.add_argument("--created-at", required=True)
    parser.add_argument("--hard-stop-at", required=True)
    parser.add_argument("--schedule-start", required=True)
    parser.add_argument("--schedule-end", required=True)
    args = parser.parse_args()
    try:
        result = run_observer(_config_from_args(args))
    except Exception as exc:
        print(f"V34 feed observer fatal: {exc}", file=sys.stderr, flush=True)
        raise SystemExit(2) from exc
    raise SystemExit(result)


if __name__ == "__main__":
    main()
