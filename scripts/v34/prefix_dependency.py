"""Frozen v34 ordered-prefix dependency and crossing reconstruction."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, cast

from scripts.v34 import policy

if TYPE_CHECKING:
    from collections.abc import Mapping

    from scripts.v34.decision_commit import ArchivedFeedPair

ABOUT_KEYS: Final = {
    "atBatIndex",
    "endTime",
    "hasReview",
    "isComplete",
    "isScoringPlay",
}
RESULT_KEYS: Final = {
    "awayScore",
    "description",
    "event",
    "eventType",
    "homeScore",
    "rbi",
}
TOP_LEVEL_KEYS: Final = {"about", "result", "review_details"}
DESCRIPTIVE_PATHS: Final = {
    "/about/isScoringPlay",
    "/result/description",
    "/result/event",
    "/result/eventType",
    "/result/rbi",
}
END_TIME_PATH: Final = "/about/endTime"
GUARD_SECONDS: Final = 60
ALLOWED_ABSTRACT_STATES: Final = {"Live", "Final"}
PROHIBITED_DETAIL_TOKENS: Final = ("suspend", "postpon")
ARCHIVED_GAME_STATE_KEYS: Final = {
    "abstract_state",
    "completed_plays",
    "detailed_state",
    "game_pk",
    "generation_id",
    "observed_at",
    "official_current_total",
} | set(policy.FEED_PROVENANCE_KEYS)
ARCHIVED_GAME_RECEIPT_KEYS: Final = {
    "archive_id",
    "feed_archive_receipt_sha256",
    "feed_summary_sha256",
    "game_pk",
    "generation_id",
    "observed_at",
    "state_sha256",
} | set(policy.FEED_PROVENANCE_KEYS)
ARCHIVED_OPPORTUNITY_KEYS: Final = {
    "eligible_at",
    "feed_archive_receipt_sha256",
    "feed_generation_id",
    "feed_summary_sha256",
    "game_pk",
    "market_ticker",
    "ordered_prefix_fingerprint",
    "post_total",
    "pre_total",
    "queue_provenance",
    "run_delta",
    "threshold",
    "trigger_at_bat_index",
    "trigger_play_identity",
    "t_seen",
} | set(policy.FEED_PROVENANCE_KEYS)
ARCHIVED_OPPORTUNITY_RECEIPT_KEYS: Final = {
    "archive_id",
    "feed_archive_receipt_sha256",
    "feed_generation_id",
    "feed_summary_sha256",
    "game_pk",
    "opportunity_sha256",
    "queue_provenance",
} | set(policy.FEED_PROVENANCE_KEYS)


@dataclass(frozen=True)
class TriggerBasis:
    game_pk: int
    trigger_at_bat_index: int
    trigger_play_identity: str
    ordered_prefix_fingerprint: str
    pre_total: int
    post_total: int
    run_delta: int
    t_seen: str
    eligible_at: str

    def to_dict(self) -> dict[str, object]:
        return cast("dict[str, object]", asdict(self))


@dataclass(frozen=True)
class PrefixSnapshot:
    prefix_fingerprint: str
    trigger_play_identity: str
    pre_total: int
    post_total: int
    run_delta: int
    candidate_start: datetime


@dataclass(frozen=True)
class ArchivedGameState:
    """Canonical game state plus the durable receipt that binds its bytes."""

    generation_id: str
    game_pk: int
    state_bytes: bytes
    archive_receipt_bytes: bytes

    @property
    def state_sha256(self) -> str:
        return hashlib.sha256(self.state_bytes).hexdigest()

    @property
    def archive_receipt_sha256(self) -> str:
        return hashlib.sha256(self.archive_receipt_bytes).hexdigest()

    def validate(
        self,
        feed_anchor: policy.FeedLaunchAnchor,
        queue_anchor: policy.QueueLaunchAnchor,
        parent_pair: ArchivedFeedPair,
    ) -> dict[str, Any]:
        parent_pair.validate(feed_anchor, queue_anchor)
        _exact_int(self.game_pk, field="archived.game_pk", minimum=1)
        if type(self.generation_id) is not str or not self.generation_id:
            raise ValueError("Archived generation ID is empty")
        if type(self.state_bytes) is not bytes or type(
            self.archive_receipt_bytes
        ) is not bytes:
            raise TypeError("Archived game-state members must be immutable bytes")
        try:
            state = json.loads(self.state_bytes)
            receipt = json.loads(self.archive_receipt_bytes)
        except json.JSONDecodeError as exc:
            raise ValueError("Archived game-state JSON is invalid") from exc
        if not isinstance(state, dict) or set(state) != ARCHIVED_GAME_STATE_KEYS:
            raise ValueError("Archived game-state keys differ")
        if not isinstance(receipt, dict) or set(receipt) != ARCHIVED_GAME_RECEIPT_KEYS:
            raise ValueError("Archived game-state receipt keys differ")
        if self.state_bytes != policy.canonical_json_bytes(state):
            raise ValueError("Archived game state is not canonical JSON")
        if self.archive_receipt_bytes != policy.canonical_json_bytes(receipt):
            raise ValueError("Archived game-state receipt is not canonical JSON")
        policy.validate_feed_artifact_provenance(
            state,
            anchor=feed_anchor,
            field="archived_state",
        )
        policy.validate_feed_artifact_provenance(
            receipt,
            anchor=feed_anchor,
            field="archived_state_receipt",
        )
        if state.get("generation_id") != self.generation_id:
            raise ValueError("Archived game-state generation mismatch")
        if state.get("game_pk") != self.game_pk:
            raise ValueError("Archived game-state game mismatch")
        if parent_pair.generation_id != self.generation_id:
            raise ValueError("Archived game-state parent generation mismatch")
        parent_summary = json.loads(parent_pair.summary_bytes)
        if not isinstance(parent_summary, dict):
            raise TypeError("Archived parent summary must be an object")
        parent_game_states = parent_summary.get("game_states")
        if not isinstance(parent_game_states, dict):
            raise ValueError("Archived parent summary has no game-state map")
        parent_state = parent_game_states.get(str(self.game_pk))
        if (
            not isinstance(parent_state, dict)
            or policy.canonical_json_bytes(parent_state) != self.state_bytes
        ):
            raise ValueError("Archived game state is not committed by parent summary")
        parse_aware_time(state.get("observed_at"), field="archived.observed_at")
        _exact_int(
            state.get("official_current_total"),
            field="archived.official_current_total",
        )
        if not isinstance(state.get("completed_plays"), dict):
            raise TypeError("Archived completed_plays must be an object")
        expected_receipt = {
            "feed_archive_receipt_sha256": parent_pair.archive_receipt_sha256,
            "feed_summary_sha256": parent_pair.summary_sha256,
            "generation_id": self.generation_id,
            "game_pk": self.game_pk,
            "observed_at": state["observed_at"],
            "state_sha256": self.state_sha256,
        }
        if any(receipt.get(key) != value for key, value in expected_receipt.items()):
            raise ValueError("Archived game-state receipt binding mismatch")
        return cast("dict[str, Any]", state)


@dataclass(frozen=True)
class ArchivedQueueOpportunity:
    """Canonical market crossing bound to one archived v34 feed generation."""

    opportunity_bytes: bytes
    archive_receipt_bytes: bytes

    @property
    def opportunity_sha256(self) -> str:
        return hashlib.sha256(self.opportunity_bytes).hexdigest()

    def validate(
        self,
        feed_anchor: policy.FeedLaunchAnchor,
        queue_anchor: policy.QueueLaunchAnchor,
    ) -> dict[str, Any]:
        if type(self.opportunity_bytes) is not bytes or type(
            self.archive_receipt_bytes
        ) is not bytes:
            raise TypeError("Archived opportunity members must be immutable bytes")
        try:
            opportunity = json.loads(self.opportunity_bytes)
            receipt = json.loads(self.archive_receipt_bytes)
        except json.JSONDecodeError as exc:
            raise ValueError("Archived opportunity JSON is invalid") from exc
        if not isinstance(opportunity, dict) or set(
            opportunity
        ) != ARCHIVED_OPPORTUNITY_KEYS:
            raise ValueError("Archived opportunity keys differ")
        if not isinstance(receipt, dict) or set(
            receipt
        ) != ARCHIVED_OPPORTUNITY_RECEIPT_KEYS:
            raise ValueError("Archived opportunity receipt keys differ")
        if self.opportunity_bytes != policy.canonical_json_bytes(opportunity):
            raise ValueError("Archived opportunity is not canonical JSON")
        if self.archive_receipt_bytes != policy.canonical_json_bytes(receipt):
            raise ValueError("Archived opportunity receipt is not canonical JSON")
        policy.validate_feed_artifact_provenance(
            opportunity,
            anchor=feed_anchor,
            field="archived_opportunity",
        )
        policy.validate_feed_artifact_provenance(
            receipt,
            anchor=feed_anchor,
            field="archived_opportunity_receipt",
        )
        for row, field in (
            (opportunity, "archived_opportunity.queue_provenance"),
            (receipt, "archived_opportunity_receipt.queue_provenance"),
        ):
            queue_provenance = row.get("queue_provenance")
            if not isinstance(queue_provenance, dict):
                raise TypeError(f"{field} is missing")
            policy.validate_queue_artifact_provenance(
                queue_provenance,
                anchor=queue_anchor,
                field=field,
            )
        game_pk = _exact_int(
            opportunity.get("game_pk"),
            field="opportunity.game_pk",
            minimum=1,
        )
        for field_name in (
            "feed_archive_receipt_sha256",
            "feed_summary_sha256",
            "ordered_prefix_fingerprint",
            "trigger_play_identity",
        ):
            policy.validate_sha256(
                opportunity.get(field_name),
                field=f"opportunity.{field_name}",
            )
        for field_name in (
            "feed_generation_id",
            "market_ticker",
            "threshold",
            "t_seen",
            "eligible_at",
        ):
            if (
                type(opportunity.get(field_name)) is not str
                or not opportunity[field_name]
            ):
                raise ValueError(f"Opportunity {field_name} is empty")
        trigger_index = _exact_int(
            opportunity.get("trigger_at_bat_index"),
            field="opportunity.trigger_at_bat_index",
        )
        pre_total = _exact_int(
            opportunity.get("pre_total"),
            field="opportunity.pre_total",
        )
        post_total = _exact_int(
            opportunity.get("post_total"),
            field="opportunity.post_total",
        )
        run_delta = _exact_int(
            opportunity.get("run_delta"),
            field="opportunity.run_delta",
            minimum=1,
        )
        if trigger_index < 0:
            raise ValueError("Opportunity trigger index is invalid")
        if post_total <= pre_total or run_delta != post_total - pre_total:
            raise ValueError("Opportunity score arithmetic is invalid")
        t_seen = parse_aware_time(
            opportunity.get("t_seen"),
            field="opportunity.t_seen",
        )
        eligible_at = parse_aware_time(
            opportunity.get("eligible_at"),
            field="opportunity.eligible_at",
        )
        if eligible_at <= t_seen:
            raise ValueError("Opportunity eligibility is invalid")
        expected_receipt = {
            "feed_archive_receipt_sha256": opportunity[
                "feed_archive_receipt_sha256"
            ],
            "feed_generation_id": opportunity["feed_generation_id"],
            "feed_summary_sha256": opportunity["feed_summary_sha256"],
            "game_pk": game_pk,
            "opportunity_sha256": self.opportunity_sha256,
        }
        if any(receipt.get(key) != value for key, value in expected_receipt.items()):
            raise ValueError("Archived opportunity receipt binding mismatch")
        return cast("dict[str, Any]", opportunity)


def _exact_int(value: object, *, field: str, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ValueError(f"{field} must be an exact integer >= {minimum}")
    return value


def parse_aware_time(value: object, *, field: str) -> datetime:
    if type(value) is not str:
        raise TypeError(f"{field} must be a string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must be timezone-aware")
    return parsed.astimezone(UTC)


def _validate_json_value(value: object, *, field: str) -> None:
    try:
        json.dumps(value, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be finite JSON") from exc


def validate_projection(value: object, *, expected_index: int) -> dict[str, Any]:
    """Validate the exact filtered projection used by the frozen prefix."""
    if not isinstance(value, dict) or set(value) != TOP_LEVEL_KEYS:
        raise ValueError("Completed play projection top-level keys differ")
    about = value.get("about")
    result = value.get("result")
    if not isinstance(about, dict) or set(about) != ABOUT_KEYS:
        raise ValueError("Completed play about keys differ")
    if not isinstance(result, dict) or set(result) != RESULT_KEYS:
        raise ValueError("Completed play result keys differ")
    if _exact_int(about.get("atBatIndex"), field="atBatIndex") != expected_index:
        raise ValueError("Completed play index differs from ordered prefix")
    if about.get("isComplete") is not True:
        raise ValueError("Prefix play is not complete")
    if type(about.get("hasReview")) is not bool:
        raise TypeError("hasReview must be an exact boolean")
    if type(about.get("isScoringPlay")) is not bool:
        raise TypeError("isScoringPlay must be an exact boolean")
    parse_aware_time(about.get("endTime"), field="endTime")
    for name in ("awayScore", "homeScore", "rbi"):
        _exact_int(result.get(name), field=name)
    for name in ("description", "event", "eventType"):
        if type(result.get(name)) is not str:
            raise TypeError(f"{name} must be a string")
    review = value.get("review_details")
    if review is not None and not isinstance(review, dict):
        raise TypeError("review_details must be null or an object")
    _validate_json_value(review, field="review_details")
    if about["hasReview"] is True and (
        not isinstance(review, dict) or type(review.get("isOverturned")) is not bool
    ):
        raise ValueError("Prefix review is ambiguous")
    return cast("dict[str, Any]", value)


def _play_fingerprint_row(projection: Mapping[str, Any]) -> dict[str, object]:
    about = cast("Mapping[str, Any]", projection["about"])
    result = cast("Mapping[str, Any]", projection["result"])
    return {
        "atBatIndex": about["atBatIndex"],
        "isComplete": about["isComplete"],
        "awayScore": result["awayScore"],
        "homeScore": result["homeScore"],
        "hasReview": about["hasReview"],
        "review_details": projection["review_details"],
    }


def _trigger_identity(
    *, game_pk: int, at_bat_index: int, pre_total: int, projection: Mapping[str, Any]
) -> str:
    result = cast("Mapping[str, Any]", projection["result"])
    away = cast("int", result["awayScore"])
    home = cast("int", result["homeScore"])
    post_total = away + home
    return policy.canonical_sha256(
        {
            "game_pk": game_pk,
            "atBatIndex": at_bat_index,
            "pre_total": pre_total,
            "post_total": post_total,
            "run_delta": post_total - pre_total,
            "awayScore": away,
            "homeScore": home,
        }
    )


def reconstruct_prefix(
    completed_plays: Mapping[str, object],
    *,
    game_pk: int,
    trigger_at_bat_index: int,
    t_seen: datetime,
    observed_at: datetime,
) -> PrefixSnapshot:
    """Reconstruct exactly indices 0..trigger and ignore only later suffix state."""
    _exact_int(game_pk, field="game_pk", minimum=1)
    _exact_int(trigger_at_bat_index, field="trigger_at_bat_index")
    if t_seen.tzinfo is None or observed_at.tzinfo is None:
        raise ValueError("Prefix timestamps must be timezone-aware")
    if observed_at < t_seen:
        raise ValueError("Prefix observation precedes first sighting")

    for raw_key in completed_plays:
        if type(raw_key) is not str:
            raise TypeError("Completed play key must be a canonical integer string")
        try:
            logical_index = int(raw_key)
        except ValueError as exc:
            raise ValueError("Completed play key is not an integer") from exc
        if logical_index < 0 or raw_key != str(logical_index):
            raise ValueError("Completed play key is not canonical")
        raw_projection = completed_plays[raw_key]
        if not isinstance(raw_projection, dict):
            raise TypeError("Completed play projection must be an object")
        raw_about = raw_projection.get("about")
        if not isinstance(raw_about, dict):
            raise TypeError("Completed play about must be an object")
        projected_index = _exact_int(
            raw_about.get("atBatIndex"),
            field="atBatIndex",
        )
        if (
            projected_index <= trigger_at_bat_index
            and projected_index != logical_index
        ):
            raise ValueError("Frozen prefix play identity is duplicated")

    projections: list[dict[str, Any]] = []
    prior_away = 0
    prior_home = 0
    latest_end = t_seen.astimezone(UTC)
    for index in range(trigger_at_bat_index + 1):
        key = str(index)
        if key not in completed_plays:
            raise ValueError(f"Prefix play missing: {index}")
        projection = validate_projection(completed_plays[key], expected_index=index)
        about = cast("Mapping[str, Any]", projection["about"])
        result = cast("Mapping[str, Any]", projection["result"])
        away = cast("int", result["awayScore"])
        home = cast("int", result["homeScore"])
        if away < prior_away or home < prior_home:
            raise ValueError("Prefix score path regressed")
        end_time = parse_aware_time(about["endTime"], field="endTime")
        if end_time > observed_at.astimezone(UTC):
            raise ValueError("Prefix endTime is in the future")
        latest_end = max(latest_end, end_time)
        prior_away = away
        prior_home = home
        projections.append(projection)

    trigger = projections[-1]
    trigger_result = cast("Mapping[str, Any]", trigger["result"])
    post_total = cast("int", trigger_result["awayScore"]) + cast(
        "int", trigger_result["homeScore"]
    )
    if trigger_at_bat_index == 0:
        pre_total = 0
    else:
        prior_result = cast("Mapping[str, Any]", projections[-2]["result"])
        pre_total = cast("int", prior_result["awayScore"]) + cast(
            "int", prior_result["homeScore"]
        )
    if post_total <= pre_total:
        raise ValueError("Trigger play does not strictly increase the score")
    rows = [_play_fingerprint_row(row) for row in projections]
    return PrefixSnapshot(
        prefix_fingerprint=policy.canonical_sha256(rows),
        trigger_play_identity=_trigger_identity(
            game_pk=game_pk,
            at_bat_index=trigger_at_bat_index,
            pre_total=pre_total,
            projection=trigger,
        ),
        pre_total=pre_total,
        post_total=post_total,
        run_delta=post_total - pre_total,
        candidate_start=max(t_seen.astimezone(UTC), latest_end),
    )


def build_trigger_basis(
    completed_plays: Mapping[str, object],
    *,
    game_pk: int,
    trigger_at_bat_index: int,
    t_seen: datetime,
    eligible_at: datetime,
) -> TriggerBasis:
    snapshot = reconstruct_prefix(
        completed_plays,
        game_pk=game_pk,
        trigger_at_bat_index=trigger_at_bat_index,
        t_seen=t_seen,
        observed_at=eligible_at,
    )
    if (eligible_at.astimezone(UTC) - snapshot.candidate_start).total_seconds() <= (
        GUARD_SECONDS
    ):
        raise ValueError("Immutable eligibility does not strictly pass the guard")
    return TriggerBasis(
        game_pk=game_pk,
        trigger_at_bat_index=trigger_at_bat_index,
        trigger_play_identity=snapshot.trigger_play_identity,
        ordered_prefix_fingerprint=snapshot.prefix_fingerprint,
        pre_total=snapshot.pre_total,
        post_total=snapshot.post_total,
        run_delta=snapshot.run_delta,
        t_seen=t_seen.astimezone(UTC).isoformat(),
        eligible_at=eligible_at.astimezone(UTC).isoformat(),
    )


def _validate_status(*, abstract_state: object, detailed_state: object) -> None:
    if abstract_state not in ALLOWED_ABSTRACT_STATES:
        raise ValueError("Game abstract state is prohibited")
    if type(detailed_state) is not str or not detailed_state:
        raise ValueError("Game detailed state is missing")
    lowered = detailed_state.casefold()
    if any(token in lowered for token in PROHIBITED_DETAIL_TOKENS):
        raise ValueError("Game detailed state is prohibited")


def revalidate_trigger_basis(
    basis: TriggerBasis,
    completed_plays: Mapping[str, object],
    *,
    official_current_total: object,
    abstract_state: object,
    detailed_state: object,
    observed_at: datetime,
) -> PrefixSnapshot:
    """Fail on every frozen prefix, crossing, timing, total, or status change."""
    _exact_int(basis.game_pk, field="basis.game_pk", minimum=1)
    _exact_int(
        basis.trigger_at_bat_index,
        field="basis.trigger_at_bat_index",
    )
    pre_total = _exact_int(basis.pre_total, field="basis.pre_total")
    post_total = _exact_int(basis.post_total, field="basis.post_total")
    run_delta = _exact_int(basis.run_delta, field="basis.run_delta", minimum=1)
    if post_total <= pre_total or run_delta != post_total - pre_total:
        raise ValueError("Frozen trigger basis score arithmetic is invalid")
    for field_name, value in (
        ("basis.trigger_play_identity", basis.trigger_play_identity),
        ("basis.ordered_prefix_fingerprint", basis.ordered_prefix_fingerprint),
    ):
        if (
            type(value) is not str
            or len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)
        ):
            raise ValueError(f"{field_name} must be lowercase SHA256")
    _validate_status(abstract_state=abstract_state, detailed_state=detailed_state)
    total = _exact_int(official_current_total, field="official_current_total")
    if total < basis.post_total:
        raise ValueError("Official current total fell below frozen post_total")
    t_seen = parse_aware_time(basis.t_seen, field="basis.t_seen")
    eligible_at = parse_aware_time(basis.eligible_at, field="basis.eligible_at")
    if observed_at.tzinfo is None:
        raise ValueError("Revalidation observation must be timezone-aware")
    if observed_at.astimezone(UTC) < eligible_at:
        raise ValueError("Revalidation observation precedes immutable eligibility")
    snapshot = reconstruct_prefix(
        completed_plays,
        game_pk=basis.game_pk,
        trigger_at_bat_index=basis.trigger_at_bat_index,
        t_seen=t_seen,
        observed_at=observed_at,
    )
    expected = (
        snapshot.prefix_fingerprint == basis.ordered_prefix_fingerprint
        and snapshot.trigger_play_identity == basis.trigger_play_identity
        and snapshot.pre_total == basis.pre_total
        and snapshot.post_total == basis.post_total
        and snapshot.run_delta == basis.run_delta
    )
    if not expected:
        raise ValueError("Frozen trigger prefix or identity changed")
    if (eligible_at - snapshot.candidate_start).total_seconds() <= GUARD_SECONDS:
        raise ValueError("Updated prefix timing breaks immutable eligibility")
    return snapshot


def parse_threshold(value: object) -> Decimal:
    try:
        threshold = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("Threshold is not decimal") from exc
    if not threshold.is_finite():
        raise ValueError("Threshold must be finite")
    return threshold


def crossing_holds(basis: TriggerBasis, threshold: object) -> bool:
    pre_total = _exact_int(basis.pre_total, field="basis.pre_total")
    post_total = _exact_int(basis.post_total, field="basis.post_total")
    strike = parse_threshold(threshold)
    return Decimal(pre_total) <= strike < Decimal(post_total)


def changed_json_pointers(before: object, after: object, path: str = "") -> set[str]:
    if type(before) is not type(after):
        return {path or "/"}
    if isinstance(before, dict) and isinstance(after, dict):
        result: set[str] = set()
        missing = object()
        for key in sorted(set(before) | set(after), key=str):
            token = str(key).replace("~", "~0").replace("/", "~1")
            child_path = f"{path}/{token}"
            old = before.get(key, missing)
            new = after.get(key, missing)
            if old is missing or new is missing:
                result.add(child_path)
            else:
                result.update(changed_json_pointers(old, new, child_path))
        return result
    if isinstance(before, list) and isinstance(after, list):
        if len(before) != len(after):
            return {path or "/"}
        result = set()
        for index, pair in enumerate(zip(before, after, strict=True)):
            result.update(changed_json_pointers(pair[0], pair[1], f"{path}/{index}"))
        return result
    return set() if before == after else {path or "/"}


def exact_end_time_exercise_credits(
    basis: TriggerBasis,
    *,
    revised_at_bat_index: int,
    before_feed_pair: ArchivedFeedPair,
    after_feed_pair: ArchivedFeedPair,
    before_archive: ArchivedGameState,
    after_archive: ArchivedGameState,
    opportunity_archive: ArchivedQueueOpportunity,
    expected_feed_launch: policy.FeedLaunchAnchor,
    expected_queue_launch: policy.QueueLaunchAnchor,
) -> bool:
    """Credit one exact, archived posteligibility in-prefix timing exercise."""
    try:
        revised_index = _exact_int(
            revised_at_bat_index,
            field="revised_at_bat_index",
        )
        if revised_index > basis.trigger_at_bat_index:
            return False
        if not isinstance(expected_feed_launch, policy.FeedLaunchAnchor):
            return False
        if not isinstance(expected_queue_launch, policy.QueueLaunchAnchor):
            return False
        before_feed_pair.validate(expected_feed_launch, expected_queue_launch)
        after_feed_pair.validate(expected_feed_launch, expected_queue_launch)
        before_state = before_archive.validate(
            expected_feed_launch,
            expected_queue_launch,
            before_feed_pair,
        )
        after_state = after_archive.validate(
            expected_feed_launch,
            expected_queue_launch,
            after_feed_pair,
        )
        opportunity = opportunity_archive.validate(
            expected_feed_launch,
            expected_queue_launch,
        )
        if before_archive.game_pk != basis.game_pk or after_archive.game_pk != basis.game_pk:
            return False
        if before_archive.generation_id == after_archive.generation_id:
            return False
        before_observed = parse_aware_time(
            before_state["observed_at"], field="before.observed_at"
        )
        after_observed = parse_aware_time(
            after_state["observed_at"], field="after.observed_at"
        )
        eligible_at = parse_aware_time(basis.eligible_at, field="basis.eligible_at")
        if before_observed != eligible_at or after_observed <= eligible_at:
            return False
        before_completed = cast("dict[str, object]", before_state["completed_plays"])
        after_completed = cast("dict[str, object]", after_state["completed_plays"])
        key = str(revised_index)
        if key not in before_completed or key not in after_completed:
            return False
        prefix_changes: set[str] = set()
        for index in range(basis.trigger_at_bat_index + 1):
            prefix_key = str(index)
            if prefix_key not in before_completed or prefix_key not in after_completed:
                return False
            before_projection = validate_projection(
                before_completed[prefix_key],
                expected_index=index,
            )
            after_projection = validate_projection(
                after_completed[prefix_key],
                expected_index=index,
            )
            for pointer in changed_json_pointers(
                before_projection, after_projection
            ):
                prefix_changes.add(f"/{index}{pointer}")
        expected_change = {f"/{revised_index}{END_TIME_PATH}"}
        if prefix_changes != expected_change:
            return False
        expected_opportunity = {
            "eligible_at": basis.eligible_at,
            "feed_archive_receipt_sha256": before_feed_pair.archive_receipt_sha256,
            "feed_generation_id": before_archive.generation_id,
            "feed_summary_sha256": before_feed_pair.summary_sha256,
            "game_pk": basis.game_pk,
            "ordered_prefix_fingerprint": basis.ordered_prefix_fingerprint,
            "post_total": basis.post_total,
            "pre_total": basis.pre_total,
            "run_delta": basis.run_delta,
            "trigger_at_bat_index": basis.trigger_at_bat_index,
            "trigger_play_identity": basis.trigger_play_identity,
            "t_seen": basis.t_seen,
        }
        if any(
            opportunity.get(field_name) != expected_value
            for field_name, expected_value in expected_opportunity.items()
        ):
            return False
        for archived_state, completed, observed in (
            (before_state, before_completed, before_observed),
            (after_state, after_completed, after_observed),
        ):
            revalidate_trigger_basis(
                basis,
                completed,
                official_current_total=archived_state["official_current_total"],
                abstract_state=archived_state["abstract_state"],
                detailed_state=archived_state["detailed_state"],
                observed_at=observed,
            )
        if not crossing_holds(basis, opportunity["threshold"]):
            return False
    except (TypeError, ValueError):
        return False
    return True


def source_sha256() -> str:
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
