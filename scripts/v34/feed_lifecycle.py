"""Pure fail-closed lifecycle for fresh v34 official MLB observations."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Final, Never, cast

from scripts.v34 import policy
from scripts.v34 import prefix_dependency as prefix

if TYPE_CHECKING:
    from collections.abc import Mapping

MAX_SUCCESSFUL_POLL_GAP_SECONDS: Final = 10.0
NANOSECONDS_PER_SECOND: Final = 1_000_000_000
MAX_SUCCESSFUL_POLL_GAP_NS: Final = int(
    MAX_SUCCESSFUL_POLL_GAP_SECONDS * NANOSECONDS_PER_SECOND
)

_locked_gap = policy.PRIMARY_POLICY["liveness_policy"][
    "feed_max_successful_poll_gap_seconds_per_live_game"
]
if _locked_gap != MAX_SUCCESSFUL_POLL_GAP_SECONDS:
    raise RuntimeError("Feed lifecycle gap differs from the reviewed policy")


class FeedTransitionFatalError(ValueError):
    """A frozen feed invariant failed and the prospective run must stop."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


@dataclass(frozen=True, slots=True)
class PendingTrigger:
    game_pk: int
    trigger_at_bat_index: int
    trigger_play_identity: str
    ordered_prefix_fingerprint: str
    pre_total: int
    post_total: int
    run_delta: int
    t_seen: str
    t_seen_monotonic_ns: int
    candidate_start: str
    candidate_start_monotonic_ns: int

    def to_dict(self) -> dict[str, object]:
        return cast("dict[str, object]", asdict(self))


@dataclass(frozen=True, slots=True)
class EligibleTrigger:
    basis: prefix.TriggerBasis
    t_seen_monotonic_ns: int
    eligible_monotonic_ns: int

    def to_dict(self) -> dict[str, object]:
        return {
            **self.basis.to_dict(),
            "t_seen_monotonic_ns": self.t_seen_monotonic_ns,
            "eligible_monotonic_ns": self.eligible_monotonic_ns,
        }


@dataclass(frozen=True, slots=True)
class FeedGameState:
    game_pk: int
    seen_completed_indices: tuple[int, ...]
    last_completed_plays_bytes: bytes
    last_official_current_total: int
    last_abstract_state: str
    last_detailed_state: str
    last_observed_at: str
    last_successful_poll_monotonic_ns: int
    pending: tuple[PendingTrigger, ...]
    eligible: tuple[EligibleTrigger, ...]
    transition_sequence: int
    prior_state_commitment_sha256: str | None
    state_commitment_sha256: str

    @property
    def last_completed_plays_sha256(self) -> str:
        return hashlib.sha256(self.last_completed_plays_bytes).hexdigest()


@dataclass(frozen=True, slots=True)
class FeedTransition:
    state: FeedGameState
    event_bytes: tuple[bytes, ...]

    @property
    def events(self) -> tuple[dict[str, object], ...]:
        rows: list[dict[str, object]] = []
        for raw in self.event_bytes:
            parsed = json.loads(raw)
            if not isinstance(parsed, dict):
                raise TypeError("Verified lifecycle event is not an object")
            rows.append(cast("dict[str, object]", parsed))
        return tuple(rows)


def _fatal(code: str, message: str, *, cause: Exception | None = None) -> Never:
    error = FeedTransitionFatalError(code, message)
    if cause is None:
        raise error
    raise error from cause


def _exact_int(value: object, *, field: str, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        _fatal("invalid_integer", f"{field} must be an exact integer >= {minimum}")
    return value


def _utc(value: datetime, *, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        _fatal("invalid_time", f"{field} must be timezone-aware")
    return value.astimezone(UTC)


def _parse_time(value: object, *, field: str) -> datetime:
    if type(value) is not str:
        _fatal("invalid_time", f"{field} must be a string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        _fatal("invalid_time", f"{field} is not ISO8601", cause=exc)
    if parsed.tzinfo is None:
        _fatal("invalid_time", f"{field} must be timezone-aware")
    return parsed.astimezone(UTC)


def _validate_status(abstract_state: object, detailed_state: object) -> tuple[str, str]:
    if abstract_state not in prefix.ALLOWED_ABSTRACT_STATES:
        _fatal("prohibited_status", "abstract game state is not Live or Final")
    if type(detailed_state) is not str or not detailed_state:
        _fatal("prohibited_status", "detailed game state is missing")
    lowered = detailed_state.casefold()
    if any(token in lowered for token in prefix.PROHIBITED_DETAIL_TOKENS):
        _fatal("prohibited_status", "detailed game state is suspended or postponed")
    return abstract_state, detailed_state


def _validated_plays(value: Mapping[str, object]) -> dict[str, dict[str, Any]]:
    if not isinstance(value, dict):
        _fatal("malformed_plays", "completed plays must be an object")
    for raw_key in value:
        if type(raw_key) is not str:
            _fatal("malformed_plays", "completed play key is not a string")
        try:
            logical = int(raw_key)
        except ValueError as exc:
            _fatal("malformed_plays", "completed play key is not integer", cause=exc)
        if logical < 0 or raw_key != str(logical):
            _fatal("malformed_plays", "completed play key is not canonical")
    try:
        canonical = policy.canonical_json_bytes(value)
    except (TypeError, ValueError) as exc:
        _fatal("malformed_plays", "completed plays are not canonical JSON", cause=exc)
    parsed = json.loads(canonical)
    if not isinstance(parsed, dict):
        _fatal("malformed_plays", "completed plays are not an object")
    keys: list[int] = []
    for raw_key in parsed:
        if type(raw_key) is not str:
            _fatal("malformed_plays", "completed play key is not a string")
        try:
            logical = int(raw_key)
        except ValueError as exc:
            _fatal("malformed_plays", "completed play key is not integer", cause=exc)
        if logical < 0 or raw_key != str(logical):
            _fatal("malformed_plays", "completed play key is not canonical")
        keys.append(logical)
    ordered = sorted(keys)
    if ordered != list(range(len(ordered))):
        _fatal("missing_completed_play", "completed plays are not contiguous from zero")
    result: dict[str, dict[str, Any]] = {}
    prior_away = 0
    prior_home = 0
    for index in ordered:
        try:
            projection = prefix.validate_projection(
                parsed[str(index)],
                expected_index=index,
            )
        except (TypeError, ValueError) as exc:
            _fatal("malformed_projection", f"play {index} is invalid", cause=exc)
        play_result = projection["result"]
        if not isinstance(play_result, dict):
            _fatal("malformed_projection", f"play {index} result is invalid")
        away = _exact_int(play_result.get("awayScore"), field="awayScore")
        home = _exact_int(play_result.get("homeScore"), field="homeScore")
        if away < prior_away or home < prior_home:
            _fatal("score_path_regression", f"play {index} regresses a team score")
        prior_away = away
        prior_home = home
        result[str(index)] = projection
    return result


def _validate_completed_end_times(
    plays: Mapping[str, Mapping[str, Any]],
    *,
    observed_at: datetime,
) -> None:
    for index in range(len(plays)):
        about = plays[str(index)]["about"]
        if not isinstance(about, dict):
            _fatal("malformed_projection", f"play {index} about is invalid")
        end_time = _parse_time(about.get("endTime"), field=f"play {index}.endTime")
        if end_time > observed_at:
            _fatal(
                "future_completed_play",
                f"play {index} endTime follows the observation",
            )


def _maximum_completed_total(plays: Mapping[str, Mapping[str, Any]]) -> int:
    if not plays:
        return 0
    final = plays[str(len(plays) - 1)]["result"]
    if not isinstance(final, dict):
        _fatal("malformed_projection", "final completed result is invalid")
    return _exact_int(final.get("awayScore"), field="awayScore") + _exact_int(
        final.get("homeScore"), field="homeScore"
    )


def _event(event_type: str, **fields: object) -> bytes:
    return policy.canonical_json_bytes({"type": event_type, **fields})


def _timedelta_ns(later: datetime, earlier: datetime) -> int:
    delta = later - earlier
    if delta.total_seconds() < 0:
        _fatal("invalid_time", "monotonic mapping received a negative wall delta")
    return (
        delta.days * 86_400 * NANOSECONDS_PER_SECOND
        + delta.seconds * NANOSECONDS_PER_SECOND
        + delta.microseconds * 1_000
    )


def _candidate_start_monotonic_ns(
    *,
    t_seen: datetime,
    t_seen_monotonic_ns: int,
    candidate_start: datetime,
) -> int:
    return t_seen_monotonic_ns + _timedelta_ns(candidate_start, t_seen)


def _state_commitment_payload(
    *,
    game_pk: int,
    seen_completed_indices: tuple[int, ...],
    last_completed_plays_bytes: bytes,
    last_official_current_total: int,
    last_abstract_state: str,
    last_detailed_state: str,
    last_observed_at: str,
    last_successful_poll_monotonic_ns: int,
    pending: tuple[PendingTrigger, ...],
    eligible: tuple[EligibleTrigger, ...],
    transition_sequence: int,
    prior_state_commitment_sha256: str | None,
) -> dict[str, object]:
    return {
        "game_pk": game_pk,
        "seen_completed_indices": list(seen_completed_indices),
        "last_completed_plays_sha256": hashlib.sha256(
            last_completed_plays_bytes
        ).hexdigest(),
        "last_official_current_total": last_official_current_total,
        "last_abstract_state": last_abstract_state,
        "last_detailed_state": last_detailed_state,
        "last_observed_at": last_observed_at,
        "last_successful_poll_monotonic_ns": last_successful_poll_monotonic_ns,
        "pending": [row.to_dict() for row in pending],
        "eligible": [row.to_dict() for row in eligible],
        "transition_sequence": transition_sequence,
        "prior_state_commitment_sha256": prior_state_commitment_sha256,
    }


def _make_state(
    *,
    game_pk: int,
    seen_completed_indices: tuple[int, ...],
    last_completed_plays_bytes: bytes,
    last_official_current_total: int,
    last_abstract_state: str,
    last_detailed_state: str,
    last_observed_at: str,
    last_successful_poll_monotonic_ns: int,
    pending: tuple[PendingTrigger, ...],
    eligible: tuple[EligibleTrigger, ...],
    transition_sequence: int,
    prior_state_commitment_sha256: str | None,
) -> FeedGameState:
    payload = _state_commitment_payload(
        game_pk=game_pk,
        seen_completed_indices=seen_completed_indices,
        last_completed_plays_bytes=last_completed_plays_bytes,
        last_official_current_total=last_official_current_total,
        last_abstract_state=last_abstract_state,
        last_detailed_state=last_detailed_state,
        last_observed_at=last_observed_at,
        last_successful_poll_monotonic_ns=last_successful_poll_monotonic_ns,
        pending=pending,
        eligible=eligible,
        transition_sequence=transition_sequence,
        prior_state_commitment_sha256=prior_state_commitment_sha256,
    )
    return FeedGameState(
        game_pk=game_pk,
        seen_completed_indices=seen_completed_indices,
        last_completed_plays_bytes=last_completed_plays_bytes,
        last_official_current_total=last_official_current_total,
        last_abstract_state=last_abstract_state,
        last_detailed_state=last_detailed_state,
        last_observed_at=last_observed_at,
        last_successful_poll_monotonic_ns=last_successful_poll_monotonic_ns,
        pending=pending,
        eligible=eligible,
        transition_sequence=transition_sequence,
        prior_state_commitment_sha256=prior_state_commitment_sha256,
        state_commitment_sha256=policy.canonical_sha256(payload),
    )


def _pending_from_snapshot(
    *,
    game_pk: int,
    trigger_index: int,
    t_seen: datetime,
    t_seen_monotonic_ns: int,
    snapshot: prefix.PrefixSnapshot,
) -> PendingTrigger:
    return PendingTrigger(
        game_pk=game_pk,
        trigger_at_bat_index=trigger_index,
        trigger_play_identity=snapshot.trigger_play_identity,
        ordered_prefix_fingerprint=snapshot.prefix_fingerprint,
        pre_total=snapshot.pre_total,
        post_total=snapshot.post_total,
        run_delta=snapshot.run_delta,
        t_seen=t_seen.isoformat(),
        t_seen_monotonic_ns=t_seen_monotonic_ns,
        candidate_start=snapshot.candidate_start.isoformat(),
        candidate_start_monotonic_ns=_candidate_start_monotonic_ns(
            t_seen=t_seen,
            t_seen_monotonic_ns=t_seen_monotonic_ns,
            candidate_start=snapshot.candidate_start,
        ),
    )


def _pending_matches_snapshot(
    pending: PendingTrigger,
    snapshot: prefix.PrefixSnapshot,
) -> bool:
    return (
        pending.trigger_play_identity == snapshot.trigger_play_identity
        and pending.ordered_prefix_fingerprint == snapshot.prefix_fingerprint
        and pending.pre_total == snapshot.pre_total
        and pending.post_total == snapshot.post_total
        and pending.run_delta == snapshot.run_delta
    )


def _validate_prior_state(state: FeedGameState) -> dict[str, dict[str, Any]]:
    if not isinstance(state, FeedGameState):
        _fatal("invalid_prior_state", "prior state has the wrong type")
    if type(state.pending) is not tuple or type(state.eligible) is not tuple:
        _fatal("invalid_prior_state", "prior trigger collections are not immutable tuples")
    if any(not isinstance(row, PendingTrigger) for row in state.pending) or any(
        not isinstance(row, EligibleTrigger) for row in state.eligible
    ):
        _fatal("invalid_prior_state", "prior trigger collection member is invalid")
    transition_sequence = _exact_int(
        state.transition_sequence,
        field="state.transition_sequence",
        minimum=1,
    )
    if transition_sequence == 1:
        if state.prior_state_commitment_sha256 is not None:
            _fatal("invalid_prior_state", "baseline state has a prior commitment")
    else:
        try:
            policy.validate_sha256(
                state.prior_state_commitment_sha256,
                field="state.prior_state_commitment_sha256",
            )
        except (TypeError, ValueError) as exc:
            _fatal("invalid_prior_state", "prior commitment is invalid", cause=exc)
    try:
        policy.validate_sha256(
            state.state_commitment_sha256,
            field="state.state_commitment_sha256",
        )
        expected_commitment = policy.canonical_sha256(
            _state_commitment_payload(
                game_pk=state.game_pk,
                seen_completed_indices=state.seen_completed_indices,
                last_completed_plays_bytes=state.last_completed_plays_bytes,
                last_official_current_total=state.last_official_current_total,
                last_abstract_state=state.last_abstract_state,
                last_detailed_state=state.last_detailed_state,
                last_observed_at=state.last_observed_at,
                last_successful_poll_monotonic_ns=(
                    state.last_successful_poll_monotonic_ns
                ),
                pending=state.pending,
                eligible=state.eligible,
                transition_sequence=transition_sequence,
                prior_state_commitment_sha256=(
                    state.prior_state_commitment_sha256
                ),
            )
        )
    except (AttributeError, TypeError, ValueError) as exc:
        _fatal("invalid_prior_state", "state commitment cannot be rebuilt", cause=exc)
    if expected_commitment != state.state_commitment_sha256:
        _fatal("invalid_prior_state", "state commitment differs from its contents")
    game_pk = _exact_int(state.game_pk, field="state.game_pk", minimum=1)
    observed_at = _parse_time(state.last_observed_at, field="state.last_observed_at")
    _exact_int(
        state.last_successful_poll_monotonic_ns,
        field="state.last_successful_poll_monotonic_ns",
    )
    abstract_state, detailed_state = _validate_status(
        state.last_abstract_state,
        state.last_detailed_state,
    )
    if type(state.last_completed_plays_bytes) is not bytes:
        _fatal("invalid_prior_state", "prior completed plays are not immutable bytes")
    try:
        raw_plays = json.loads(state.last_completed_plays_bytes)
    except json.JSONDecodeError as exc:
        _fatal("invalid_prior_state", "prior completed plays JSON is invalid", cause=exc)
    try:
        canonical_prior = policy.canonical_json_bytes(raw_plays)
    except (TypeError, ValueError) as exc:
        _fatal("invalid_prior_state", "prior completed plays are invalid", cause=exc)
    if state.last_completed_plays_bytes != canonical_prior:
        _fatal("invalid_prior_state", "prior completed plays are not canonical")
    plays = _validated_plays(cast("Mapping[str, object]", raw_plays))
    _validate_completed_end_times(plays, observed_at=observed_at)
    current_indices = tuple(range(len(plays)))
    if (
        type(state.seen_completed_indices) is not tuple
        or any(type(index) is not int for index in state.seen_completed_indices)
        or state.seen_completed_indices
        != tuple(range(len(state.seen_completed_indices)))
        or not set(current_indices).issubset(state.seen_completed_indices)
    ):
        _fatal(
            "invalid_prior_state",
            "prior seen indices do not contain the archived completed prefix",
        )
    official_total = _exact_int(
        state.last_official_current_total,
        field="state.last_official_current_total",
    )
    completed_total = _maximum_completed_total(plays)
    if official_total < completed_total:
        _fatal("invalid_prior_state", "prior official total is below completed plays")
    if abstract_state == "Final" and official_total != completed_total:
        _fatal(
            "invalid_prior_state",
            "prior Final total differs from the completed-play maximum",
        )

    pending_indices: set[int] = set()
    for pending in state.pending:
        if _exact_int(pending.game_pk, field="pending.game_pk", minimum=1) != game_pk:
            _fatal("invalid_prior_state", "pending trigger game binding is invalid")
        index = _exact_int(
            pending.trigger_at_bat_index,
            field="pending.trigger_at_bat_index",
        )
        if index in pending_indices or index not in current_indices:
            _fatal("invalid_prior_state", "pending trigger index is invalid or duplicated")
        pending_indices.add(index)
        for field_name, value, minimum in (
            ("pending.pre_total", pending.pre_total, 0),
            ("pending.post_total", pending.post_total, 0),
            ("pending.run_delta", pending.run_delta, 1),
            ("pending.t_seen_monotonic_ns", pending.t_seen_monotonic_ns, 0),
            (
                "pending.candidate_start_monotonic_ns",
                pending.candidate_start_monotonic_ns,
                0,
            ),
        ):
            _exact_int(value, field=field_name, minimum=minimum)
        for hash_field, hash_value in (
            ("pending.trigger_play_identity", pending.trigger_play_identity),
            (
                "pending.ordered_prefix_fingerprint",
                pending.ordered_prefix_fingerprint,
            ),
        ):
            try:
                policy.validate_sha256(hash_value, field=hash_field)
            except (TypeError, ValueError) as exc:
                _fatal("invalid_prior_state", f"{hash_field} is invalid", cause=exc)
        t_seen = _parse_time(pending.t_seen, field="pending.t_seen")
        try:
            snapshot = prefix.reconstruct_prefix(
                plays,
                game_pk=game_pk,
                trigger_at_bat_index=index,
                t_seen=t_seen,
                observed_at=observed_at,
            )
        except (TypeError, ValueError) as exc:
            _fatal("invalid_prior_state", "pending trigger cannot be rebuilt", cause=exc)
        if not _pending_matches_snapshot(pending, snapshot):
            _fatal("invalid_prior_state", "pending trigger basis differs from prior plays")
        if _parse_time(pending.candidate_start, field="pending.candidate_start") != (
            snapshot.candidate_start
        ):
            _fatal("invalid_prior_state", "pending candidate start differs from prior plays")
        expected_candidate_monotonic_ns = _candidate_start_monotonic_ns(
            t_seen=t_seen,
            t_seen_monotonic_ns=pending.t_seen_monotonic_ns,
            candidate_start=snapshot.candidate_start,
        )
        if pending.candidate_start_monotonic_ns != expected_candidate_monotonic_ns:
            _fatal(
                "invalid_prior_state",
                "pending monotonic candidate start differs from prior plays",
            )
        if pending.t_seen_monotonic_ns > state.last_successful_poll_monotonic_ns:
            _fatal("invalid_prior_state", "pending first sighting is in the future")
        if (
            state.last_successful_poll_monotonic_ns
            - pending.candidate_start_monotonic_ns
            > prefix.GUARD_SECONDS * NANOSECONDS_PER_SECOND
            and (observed_at - snapshot.candidate_start).total_seconds()
            > prefix.GUARD_SECONDS
        ):
            _fatal("invalid_prior_state", "overdue pending trigger was not promoted")

    eligible_indices: set[int] = set()
    for eligible in state.eligible:
        basis = eligible.basis
        if not isinstance(basis, prefix.TriggerBasis) or basis.game_pk != game_pk:
            _fatal("invalid_prior_state", "eligible trigger game binding is invalid")
        index = _exact_int(
            basis.trigger_at_bat_index,
            field="basis.trigger_at_bat_index",
        )
        if (
            index in eligible_indices
            or index in pending_indices
            or index not in current_indices
        ):
            _fatal(
                "invalid_prior_state",
                "eligible trigger index is invalid or duplicated",
            )
        eligible_indices.add(index)
        t_seen_monotonic_ns = _exact_int(
            eligible.t_seen_monotonic_ns,
            field="eligible.t_seen_monotonic_ns",
        )
        eligible_monotonic_ns = _exact_int(
            eligible.eligible_monotonic_ns,
            field="eligible.eligible_monotonic_ns",
        )
        if not (
            t_seen_monotonic_ns
            < eligible_monotonic_ns
            <= state.last_successful_poll_monotonic_ns
        ):
            _fatal("invalid_prior_state", "eligible monotonic timing is invalid")
        try:
            snapshot = prefix.revalidate_trigger_basis(
                basis,
                plays,
                official_current_total=official_total,
                abstract_state=abstract_state,
                detailed_state=detailed_state,
                observed_at=observed_at,
            )
        except (TypeError, ValueError) as exc:
            _fatal("invalid_prior_state", "eligible trigger cannot be rebuilt", cause=exc)
        basis_t_seen = _parse_time(basis.t_seen, field="basis.t_seen")
        mapped_candidate_ns = _candidate_start_monotonic_ns(
            t_seen=basis_t_seen,
            t_seen_monotonic_ns=t_seen_monotonic_ns,
            candidate_start=snapshot.candidate_start,
        )
        if (
            eligible_monotonic_ns - mapped_candidate_ns
            <= prefix.GUARD_SECONDS * NANOSECONDS_PER_SECOND
        ):
            _fatal("invalid_prior_state", "eligible monotonic guard is invalid")
    return plays


def transition_game(
    prior: FeedGameState | None,
    *,
    game_pk: int,
    completed_plays: Mapping[str, object],
    official_current_total: int,
    abstract_state: str,
    detailed_state: str,
    observed_at: datetime,
    successful_poll_monotonic_ns: int,
    expected_prior_state_commitment_sha256: str | None,
) -> FeedTransition:
    """Apply one observation against an externally retained prior commitment."""

    game_pk = _exact_int(game_pk, field="game_pk", minimum=1)
    observed = _utc(observed_at, field="observed_at")
    poll_monotonic_ns = _exact_int(
        successful_poll_monotonic_ns,
        field="successful_poll_monotonic_ns",
    )
    abstract, detailed = _validate_status(abstract_state, detailed_state)
    plays = _validated_plays(completed_plays)
    _validate_completed_end_times(plays, observed_at=observed)
    official_total = _exact_int(
        official_current_total,
        field="official_current_total",
    )
    completed_total = _maximum_completed_total(plays)
    if official_total < completed_total:
        _fatal("official_total_regression", "official total is below completed plays")
    if abstract == "Final" and official_total != completed_total:
        _fatal(
            "incomplete_final_projection",
            "Final total differs from the completed-play maximum",
        )
    plays_bytes = policy.canonical_json_bytes(plays)

    if prior is None:
        if expected_prior_state_commitment_sha256 is not None:
            _fatal(
                "prior_commitment_mismatch",
                "a baseline cannot consume an existing prior commitment",
            )
        state = _make_state(
            game_pk=game_pk,
            seen_completed_indices=tuple(range(len(plays))),
            last_completed_plays_bytes=plays_bytes,
            last_official_current_total=official_total,
            last_abstract_state=abstract,
            last_detailed_state=detailed,
            last_observed_at=observed.isoformat(),
            last_successful_poll_monotonic_ns=poll_monotonic_ns,
            pending=(),
            eligible=(),
            transition_sequence=1,
            prior_state_commitment_sha256=None,
        )
        return FeedTransition(
            state=state,
            event_bytes=(
                _event(
                    "game_baseline",
                    game_pk=game_pk,
                    observed_at=observed.isoformat(),
                    successful_poll_monotonic_ns=poll_monotonic_ns,
                    completed_play_count=len(plays),
                    official_current_total=official_total,
                    completed_plays_sha256=state.last_completed_plays_sha256,
                    state_commitment_sha256=state.state_commitment_sha256,
                ),
            ),
        )

    try:
        policy.validate_sha256(
            expected_prior_state_commitment_sha256,
            field="expected_prior_state_commitment_sha256",
        )
    except (TypeError, ValueError) as exc:
        _fatal("prior_commitment_mismatch", "expected prior commitment is invalid", cause=exc)
    if expected_prior_state_commitment_sha256 != prior.state_commitment_sha256:
        _fatal(
            "prior_commitment_mismatch",
            "prior state differs from the externally retained commitment",
        )
    prior_plays = _validate_prior_state(prior)
    if prior.game_pk != game_pk:
        _fatal("game_binding_changed", "observation game differs from prior state")
    prior_observed = _parse_time(prior.last_observed_at, field="prior.last_observed_at")
    if observed <= prior_observed:
        _fatal("nonmonotonic_observation", "observation time did not advance")
    prior_poll_monotonic_ns = prior.last_successful_poll_monotonic_ns
    if poll_monotonic_ns <= prior_poll_monotonic_ns:
        _fatal("nonmonotonic_poll_clock", "successful poll monotonic clock did not advance")
    gap_monotonic_ns = poll_monotonic_ns - prior_poll_monotonic_ns
    if gap_monotonic_ns > MAX_SUCCESSFUL_POLL_GAP_NS:
        _fatal(
            "successful_poll_gap",
            f"successful poll gap is {gap_monotonic_ns} monotonic nanoseconds",
        )
    if official_total < prior.last_official_current_total:
        _fatal("official_total_regression", "official total regressed")
    seen_indices = set(prior.seen_completed_indices)
    prior_current_indices = set(range(len(prior_plays)))
    current_indices = set(range(len(plays)))
    removed_indices = sorted(prior_current_indices - current_indices)
    bound_trigger_indices = [
        *[row.trigger_at_bat_index for row in prior.pending],
        *[row.basis.trigger_at_bat_index for row in prior.eligible],
    ]
    for removed_index in removed_indices:
        if any(removed_index <= trigger_index for trigger_index in bound_trigger_indices):
            _fatal(
                "completed_play_removed",
                "a play inside a bound trigger prefix disappeared",
            )

    events: list[bytes] = []
    changed_paths: set[str] = set()
    for removed_index in removed_indices:
        events.append(
            _event(
                "completed_suffix_play_disappeared",
                game_pk=game_pk,
                at_bat_index=removed_index,
                observed_at=observed.isoformat(),
                prior_play_sha256=policy.canonical_sha256(
                    prior_plays[str(removed_index)]
                ),
            )
        )
    reappeared_indices = sorted(
        (current_indices & seen_indices) - prior_current_indices
    )
    for reappeared_index in reappeared_indices:
        events.append(
            _event(
                "completed_suffix_play_reappeared",
                game_pk=game_pk,
                at_bat_index=reappeared_index,
                observed_at=observed.isoformat(),
                current_play_sha256=policy.canonical_sha256(
                    plays[str(reappeared_index)]
                ),
            )
        )
    for index in sorted(prior_current_indices & current_indices):
        before = prior_plays[str(index)]
        after = plays[str(index)]
        if before == after:
            continue
        local_paths = prefix.changed_json_pointers(before, after)
        absolute_paths = sorted(f"/{index}{path}" for path in local_paths)
        changed_paths.update(absolute_paths)
        events.append(
            _event(
                "completed_play_revision",
                game_pk=game_pk,
                at_bat_index=index,
                observed_at=observed.isoformat(),
                changed_paths=absolute_paths,
                before_sha256=policy.canonical_sha256(before),
                after_sha256=policy.canonical_sha256(after),
            )
        )

    eligible: list[EligibleTrigger] = []
    for prior_eligible in sorted(
        prior.eligible,
        key=lambda row: row.basis.trigger_at_bat_index,
    ):
        basis = prior_eligible.basis
        try:
            snapshot = prefix.revalidate_trigger_basis(
                basis,
                plays,
                official_current_total=official_total,
                abstract_state=abstract,
                detailed_state=detailed,
                observed_at=observed,
            )
        except (TypeError, ValueError) as exc:
            _fatal(
                "eligible_prefix_invalid",
                f"eligible trigger {basis.trigger_at_bat_index} failed revalidation",
                cause=exc,
            )
        basis_t_seen = _parse_time(basis.t_seen, field="basis.t_seen")
        mapped_candidate_ns = _candidate_start_monotonic_ns(
            t_seen=basis_t_seen,
            t_seen_monotonic_ns=prior_eligible.t_seen_monotonic_ns,
            candidate_start=snapshot.candidate_start,
        )
        if (
            prior_eligible.eligible_monotonic_ns - mapped_candidate_ns
            <= prefix.GUARD_SECONDS * NANOSECONDS_PER_SECOND
        ):
            _fatal(
                "eligible_prefix_invalid",
                f"eligible trigger {basis.trigger_at_bat_index} breaks monotonic guard",
            )
        eligible.append(prior_eligible)
        events.append(
            _event(
                "eligible_trigger_revalidated",
                **prior_eligible.to_dict(),
                observed_at=observed.isoformat(),
            )
        )
        prefix_changes = {
            path
            for path in changed_paths
            if int(path.split("/", 2)[1]) <= basis.trigger_at_bat_index
        }
        if len(prefix_changes) == 1:
            only = next(iter(prefix_changes))
            if only.endswith(prefix.END_TIME_PATH):
                changed_index = int(only.split("/", 2)[1])
                before_about = prior_plays[str(changed_index)]["about"]
                after_about = plays[str(changed_index)]["about"]
                if not isinstance(before_about, dict) or not isinstance(
                    after_about, dict
                ):
                    _fatal(
                        "malformed_projection",
                        f"play {changed_index} about is invalid",
                    )
                before_end = _parse_time(
                    before_about.get("endTime"),
                    field=f"prior play {changed_index}.endTime",
                )
                after_end = _parse_time(
                    after_about.get("endTime"),
                    field=f"current play {changed_index}.endTime",
                )
                event_type = (
                    "eligible_prefix_end_time_only_observed"
                    if before_end != after_end
                    else "eligible_prefix_end_time_representation_only_noncredit"
                )
                events.append(
                    _event(
                        event_type,
                        **prior_eligible.to_dict(),
                        observed_at=observed.isoformat(),
                        changed_path=only,
                        before_end_time=before_end.isoformat(),
                        after_end_time=after_end.isoformat(),
                    )
                )

    pending: list[PendingTrigger] = []
    for prior_pending in sorted(
        prior.pending,
        key=lambda row: row.trigger_at_bat_index,
    ):
        t_seen = _parse_time(prior_pending.t_seen, field="pending.t_seen")
        try:
            snapshot = prefix.reconstruct_prefix(
                plays,
                game_pk=game_pk,
                trigger_at_bat_index=prior_pending.trigger_at_bat_index,
                t_seen=t_seen,
                observed_at=observed,
            )
        except (TypeError, ValueError) as exc:
            _fatal(
                "pending_prefix_invalid",
                f"pending trigger {prior_pending.trigger_at_bat_index} is invalid",
                cause=exc,
            )
        if not _pending_matches_snapshot(prior_pending, snapshot):
            _fatal(
                "pending_prefix_changed",
                f"pending trigger {prior_pending.trigger_at_bat_index} changed identity",
            )
        updated = _pending_from_snapshot(
            game_pk=game_pk,
            trigger_index=prior_pending.trigger_at_bat_index,
            t_seen=t_seen,
            t_seen_monotonic_ns=prior_pending.t_seen_monotonic_ns,
            snapshot=snapshot,
        )
        if (
            poll_monotonic_ns - updated.candidate_start_monotonic_ns
            > prefix.GUARD_SECONDS * NANOSECONDS_PER_SECOND
            and (observed - snapshot.candidate_start).total_seconds()
            > prefix.GUARD_SECONDS
        ):
            try:
                basis = prefix.build_trigger_basis(
                    plays,
                    game_pk=game_pk,
                    trigger_at_bat_index=prior_pending.trigger_at_bat_index,
                    t_seen=t_seen,
                    eligible_at=observed,
                )
            except (TypeError, ValueError) as exc:
                _fatal("eligibility_rebuild_failed", "eligible basis rebuild failed", cause=exc)
            eligible_trigger = EligibleTrigger(
                basis=basis,
                t_seen_monotonic_ns=prior_pending.t_seen_monotonic_ns,
                eligible_monotonic_ns=poll_monotonic_ns,
            )
            eligible.append(eligible_trigger)
            events.append(
                _event(
                    "trigger_became_eligible",
                    **eligible_trigger.to_dict(),
                    observed_at=observed.isoformat(),
                )
            )
        else:
            pending.append(updated)
            events.append(
                _event(
                    "pending_trigger_revalidated",
                    **updated.to_dict(),
                    observed_at=observed.isoformat(),
                )
            )

    new_indices = sorted(current_indices - seen_indices)
    for index in new_indices:
        play_result = plays[str(index)]["result"]
        if not isinstance(play_result, dict):
            _fatal("malformed_projection", f"play {index} result is invalid")
        post_total = _exact_int(play_result.get("awayScore"), field="awayScore") + (
            _exact_int(play_result.get("homeScore"), field="homeScore")
        )
        if index == 0:
            pre_total = 0
        else:
            prior_result = plays[str(index - 1)]["result"]
            if not isinstance(prior_result, dict):
                _fatal("malformed_projection", f"play {index - 1} result is invalid")
            pre_total = _exact_int(
                prior_result.get("awayScore"), field="awayScore"
            ) + _exact_int(prior_result.get("homeScore"), field="homeScore")
        if post_total <= pre_total:
            continue
        play_about = plays[str(index)]["about"]
        if not isinstance(play_about, dict):
            _fatal("malformed_projection", f"play {index} about is invalid")
        end_time = _parse_time(
            play_about.get("endTime"),
            field=f"play {index}.endTime",
        )
        stale_reasons: list[str] = []
        if (
            end_time <= prior_observed
            and post_total <= prior.last_official_current_total
        ):
            stale_reasons.append(
                "predates_prior_observation_and_prior_total_already_reflects_score"
            )
        if stale_reasons:
            events.append(
                _event(
                    "stale_scoring_play_first_seen_noncredit",
                    game_pk=game_pk,
                    at_bat_index=index,
                    observed_at=observed.isoformat(),
                    prior_observed_at=prior_observed.isoformat(),
                    end_time=end_time.isoformat(),
                    pre_total=pre_total,
                    post_total=post_total,
                    prior_official_current_total=(
                        prior.last_official_current_total
                    ),
                    reasons=stale_reasons,
                )
            )
            continue
        try:
            snapshot = prefix.reconstruct_prefix(
                plays,
                game_pk=game_pk,
                trigger_at_bat_index=index,
                t_seen=observed,
                observed_at=observed,
            )
        except (TypeError, ValueError) as exc:
            _fatal("new_trigger_invalid", f"new trigger {index} is invalid", cause=exc)
        candidate = _pending_from_snapshot(
            game_pk=game_pk,
            trigger_index=index,
            t_seen=observed,
            t_seen_monotonic_ns=poll_monotonic_ns,
            snapshot=snapshot,
        )
        pending.append(candidate)
        events.append(
            _event(
                "run_increase_observed",
                **candidate.to_dict(),
                observed_at=observed.isoformat(),
            )
        )

    eligible.sort(key=lambda row: row.basis.trigger_at_bat_index)
    pending.sort(key=lambda row: row.trigger_at_bat_index)
    state = _make_state(
        game_pk=game_pk,
        seen_completed_indices=tuple(
            range(max(seen_indices | current_indices, default=-1) + 1)
        ),
        last_completed_plays_bytes=plays_bytes,
        last_official_current_total=official_total,
        last_abstract_state=abstract,
        last_detailed_state=detailed,
        last_observed_at=observed.isoformat(),
        last_successful_poll_monotonic_ns=poll_monotonic_ns,
        pending=tuple(pending),
        eligible=tuple(eligible),
        transition_sequence=prior.transition_sequence + 1,
        prior_state_commitment_sha256=prior.state_commitment_sha256,
    )
    events.append(
        _event(
            "poll_validated",
            game_pk=game_pk,
            observed_at=observed.isoformat(),
            successful_poll_monotonic_ns=poll_monotonic_ns,
            gap_monotonic_ns=gap_monotonic_ns,
            official_current_total=official_total,
            completed_plays_sha256=state.last_completed_plays_sha256,
            pending_trigger_count=len(pending),
            eligible_trigger_count=len(eligible),
            abstract_state=abstract,
            detailed_state=detailed,
            transition_sequence=state.transition_sequence,
            prior_state_commitment_sha256=state.prior_state_commitment_sha256,
            state_commitment_sha256=state.state_commitment_sha256,
        )
    )
    _validate_prior_state(state)
    return FeedTransition(state=state, event_bytes=tuple(events))
