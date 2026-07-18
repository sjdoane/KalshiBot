"""Stable-generation queue decision commits with event-log recovery."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Final, cast
from uuid import uuid4

from scripts.v34 import policy

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence
    from pathlib import Path

RUN_SIGNATURE: Final = "prospective-queue-v34-20260718-lock1"
SCHEMA_VERSION: Final = 9
MAX_REPLACE_ATTEMPTS: Final = 8
END_PROOF_KEYS: Final = {
    "crossing_valid",
    "eligibility_valid",
    "eligible_at",
    "feed_generation_id",
    "feed_summary_sha256",
    "freshness_valid",
    "game_pk",
    "market_ticker",
    "ordered_prefix_fingerprint",
    "post_total",
    "pre_total",
    "run_delta",
    "threshold",
    "trigger_at_bat_index",
    "trigger_play_identity",
    "t_seen",
}
_TAIL_CACHE: dict[Path, tuple[int, int, str | None]] = {}
_VERIFIED_STATE_CACHE: dict[Path, tuple[int, int, dict[str, object]]] = {}


@dataclass(frozen=True)
class ArchivedFeedPair:
    generation_id: str
    summary_bytes: bytes
    feed_receipt_bytes: bytes
    archive_receipt_bytes: bytes

    @property
    def summary_sha256(self) -> str:
        return _sha256_bytes(self.summary_bytes)

    @property
    def feed_receipt_sha256(self) -> str:
        return _sha256_bytes(self.feed_receipt_bytes)

    @property
    def archive_receipt_sha256(self) -> str:
        return _sha256_bytes(self.archive_receipt_bytes)

    def validate(self, anchor: policy.FeedLaunchAnchor) -> None:
        if type(self.generation_id) is not str or not self.generation_id:
            raise ValueError("Feed generation ID is empty")
        if not all(
            type(value) is bytes
            for value in (
                self.summary_bytes,
                self.feed_receipt_bytes,
                self.archive_receipt_bytes,
            )
        ):
            raise TypeError("Archived feed pair members must be immutable bytes")
        try:
            summary = json.loads(self.summary_bytes)
            receipt = json.loads(self.feed_receipt_bytes)
            archive = json.loads(self.archive_receipt_bytes)
        except json.JSONDecodeError as exc:
            raise ValueError("Archived feed pair JSON is invalid") from exc
        if not all(isinstance(row, dict) for row in (summary, receipt, archive)):
            raise TypeError("Archived feed pair members must be objects")
        summary_row = cast("dict[str, object]", summary)
        receipt_row = cast("dict[str, object]", receipt)
        archive_row = cast("dict[str, object]", archive)
        for raw, row, field_name in (
            (self.summary_bytes, summary_row, "summary"),
            (self.feed_receipt_bytes, receipt_row, "feed_receipt"),
            (self.archive_receipt_bytes, archive_row, "archive_receipt"),
        ):
            if raw != policy.canonical_json_bytes(row):
                raise ValueError(f"Archived {field_name} is not canonical JSON")
        provenances = [
            policy.validate_feed_artifact_provenance(
                row,
                anchor=anchor,
                field=field_name,
            )
            for row, field_name in (
                (summary_row, "summary"),
                (receipt_row, "feed_receipt"),
                (archive_row, "archive_receipt"),
            )
        ]
        if any(row != anchor.provenance for row in provenances):
            raise ValueError("Archived feed pair launch provenance mismatch")
        if summary_row.get("generation_id") != self.generation_id:
            raise ValueError("Archived summary generation mismatch")
        expected_receipt = {
            "generation_id": self.generation_id,
            "summary_sha256": self.summary_sha256,
        }
        if any(receipt_row.get(key) != value for key, value in expected_receipt.items()):
            raise ValueError("Archived feed receipt binding mismatch")
        expected_archive = {
            **expected_receipt,
            "feed_receipt_sha256": self.feed_receipt_sha256,
        }
        if any(archive_row.get(key) != value for key, value in expected_archive.items()):
            raise ValueError("Archive receipt binding mismatch")


@dataclass(frozen=True)
class EndValidationProof:
    feed_generation_id: str
    feed_summary_sha256: str
    market_ticker: str
    threshold: str
    game_pk: int
    trigger_at_bat_index: int
    trigger_play_identity: str
    ordered_prefix_fingerprint: str
    pre_total: int
    post_total: int
    run_delta: int
    t_seen: str
    eligible_at: str
    crossing_valid: bool
    eligibility_valid: bool
    freshness_valid: bool

    def to_dict(self) -> dict[str, object]:
        return cast("dict[str, object]", self.__dict__.copy())


@dataclass(frozen=True)
class StagedDecision:
    decision_kind: str
    decision_key: str
    market_ticker: str
    threshold: str
    game_pk: int
    trigger_at_bat_index: int
    trigger_play_identity: str
    ordered_prefix_fingerprint: str
    pre_total: int
    post_total: int
    run_delta: int
    t_seen: str
    eligible_at: str
    mutations: tuple[dict[str, object], ...]
    evidence: dict[str, object]

    def validate(self) -> None:
        if self.decision_kind not in {"submit", "skip", "reconcile"}:
            raise ValueError("Unknown staged decision kind")
        if type(self.decision_key) is not str or not self.decision_key:
            raise ValueError("Staged decision key is empty")
        for field_name, value in (
            ("market_ticker", self.market_ticker),
            ("threshold", self.threshold),
            ("trigger_play_identity", self.trigger_play_identity),
            ("ordered_prefix_fingerprint", self.ordered_prefix_fingerprint),
        ):
            if type(value) is not str or not value:
                raise ValueError(f"Staged {field_name} is empty")
        game_pk = _exact_int(self.game_pk, field="staged.game_pk", minimum=1)
        trigger_index = _exact_int(
            self.trigger_at_bat_index,
            field="staged.trigger_at_bat_index",
        )
        pre_total = _exact_int(self.pre_total, field="staged.pre_total")
        post_total = _exact_int(self.post_total, field="staged.post_total")
        run_delta = _exact_int(
            self.run_delta,
            field="staged.run_delta",
            minimum=1,
        )
        if game_pk < 1 or trigger_index < 0:
            raise ValueError("Staged trigger coordinates are invalid")
        if post_total <= pre_total or run_delta != post_total - pre_total:
            raise ValueError("Staged trigger score arithmetic is invalid")
        t_seen = _parse_aware_time(self.t_seen, field="staged.t_seen")
        eligible_at = _parse_aware_time(
            self.eligible_at,
            field="staged.eligible_at",
        )
        if eligible_at <= t_seen:
            raise ValueError("Staged eligibility must follow first sighting")
        _validate_sha256(
            self.trigger_play_identity, field="staged.trigger_play_identity"
        )
        _validate_sha256(
            self.ordered_prefix_fingerprint,
            field="staged.ordered_prefix_fingerprint",
        )
        if not self.mutations:
            raise ValueError("Staged decision has no mutations")
        for mutation in self.mutations:
            _validate_mutation(mutation)
        policy.canonical_json_bytes(self.evidence)


def _utc_now() -> str:
    return datetime.now(tz=UTC).isoformat()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _exact_int(value: object, *, field: str, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ValueError(f"{field} must be an exact integer >= {minimum}")
    return value


def _parse_aware_time(value: object, *, field: str) -> datetime:
    if type(value) is not str:
        raise TypeError(f"{field} must be a string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must be timezone-aware")
    return parsed.astimezone(UTC)


def _event_payload_sha256(event: Mapping[str, object]) -> str:
    payload = {key: value for key, value in event.items() if key != "event_sha256"}
    return policy.canonical_sha256(payload)


def _validate_sha256(value: object, *, field: str, allow_none: bool = False) -> None:
    if allow_none and value is None:
        return
    if (
        type(value) is not str
        or len(value) != 64
        or any(c not in "0123456789abcdef" for c in value)
    ):
        raise ValueError(f"{field} must be lowercase SHA256")


def _validate_event(event: object, *, prior_sha256: str | None) -> dict[str, Any]:
    if not isinstance(event, dict):
        raise TypeError("Queue event must be an object")
    if event.get("run_signature") != RUN_SIGNATURE:
        raise ValueError("Queue event run signature mismatch")
    if event.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Queue event schema mismatch")
    if event.get("policy_sha256") != policy.POLICY_CANONICAL_SHA256:
        raise ValueError("Queue event policy hash mismatch")
    if event.get("prior_event_sha256") != prior_sha256:
        raise ValueError("Queue event chain mismatch")
    _validate_sha256(event.get("event_sha256"), field="event_sha256")
    _validate_sha256(
        event.get("resulting_semantic_state_sha256"),
        field="resulting_semantic_state_sha256",
    )
    if event["event_sha256"] != _event_payload_sha256(event):
        raise ValueError("Queue event payload hash mismatch")
    event_type = event.get("type")
    if event_type not in {"decision_commit", "feed_generation_advanced"}:
        raise ValueError("Unknown queue event type")
    if event_type == "decision_commit":
        proof = event.get("end_validation_proof")
        proof_sha256 = event.get("end_validation_proof_sha256")
        if not isinstance(proof, dict) or set(proof) != END_PROOF_KEYS:
            raise ValueError("Decision end-validation proof is malformed")
        _validate_sha256(
            proof_sha256,
            field="end_validation_proof_sha256",
        )
        if proof_sha256 != policy.canonical_sha256(proof):
            raise ValueError("Decision end-validation proof hash mismatch")
        _validate_end_proof_dict(proof)
        for field_name in (
            "eligible_at",
            "feed_generation_id",
            "feed_summary_sha256",
            "game_pk",
            "market_ticker",
            "ordered_prefix_fingerprint",
            "post_total",
            "pre_total",
            "run_delta",
            "threshold",
            "trigger_at_bat_index",
            "trigger_play_identity",
            "t_seen",
        ):
            if event.get(field_name) != proof.get(field_name):
                raise ValueError(
                    f"Decision event and proof disagree on {field_name}"
                )
    return cast("dict[str, Any]", event)


def _validate_end_proof_dict(proof: Mapping[str, object]) -> None:
    if set(proof) != END_PROOF_KEYS:
        raise ValueError("End-validation proof fields differ")
    for field_name in (
        "feed_generation_id",
        "market_ticker",
        "threshold",
        "t_seen",
        "eligible_at",
    ):
        if type(proof.get(field_name)) is not str or not proof[field_name]:
            raise ValueError(f"End-validation proof {field_name} is empty")
    for field_name in (
        "feed_summary_sha256",
        "trigger_play_identity",
        "ordered_prefix_fingerprint",
    ):
        _validate_sha256(proof.get(field_name), field=f"proof.{field_name}")
    game_pk = _exact_int(proof.get("game_pk"), field="proof.game_pk", minimum=1)
    trigger_index = _exact_int(
        proof.get("trigger_at_bat_index"),
        field="proof.trigger_at_bat_index",
    )
    pre_total = _exact_int(proof.get("pre_total"), field="proof.pre_total")
    post_total = _exact_int(proof.get("post_total"), field="proof.post_total")
    run_delta = _exact_int(
        proof.get("run_delta"),
        field="proof.run_delta",
        minimum=1,
    )
    if game_pk < 1 or trigger_index < 0:
        raise ValueError("End-validation proof trigger coordinates are invalid")
    if post_total <= pre_total or run_delta != post_total - pre_total:
        raise ValueError("End-validation proof score arithmetic is invalid")
    t_seen = _parse_aware_time(proof.get("t_seen"), field="proof.t_seen")
    eligible_at = _parse_aware_time(
        proof.get("eligible_at"),
        field="proof.eligible_at",
    )
    if eligible_at <= t_seen:
        raise ValueError("End-validation proof eligibility is invalid")
    for field_name in (
        "crossing_valid",
        "eligibility_valid",
        "freshness_valid",
    ):
        if proof.get(field_name) is not True:
            raise ValueError(f"End-validation proof {field_name} is not true")


def read_events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        _TAIL_CACHE.pop(path.resolve(), None)
        _VERIFIED_STATE_CACHE.pop(path.resolve(), None)
        return []
    rows: list[dict[str, Any]] = []
    prior: str | None = None
    state = _empty_state()
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.endswith("\n"):
                raise ValueError(f"Queue event line {line_number} lacks newline")
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Queue event line {line_number} is invalid") from exc
            event = _validate_event(parsed, prior_sha256=prior)
            _apply_event_to_state(state, event)
            if event["resulting_semantic_state_sha256"] != _semantic_state_sha256(
                state
            ):
                raise ValueError(
                    f"Queue event line {line_number} semantic state hash mismatch"
                )
            prior = cast("str", event["event_sha256"])
            state["last_event_sha256"] = prior
            state["semantic_state_sha256"] = event[
                "resulting_semantic_state_sha256"
            ]
            rows.append(event)
    stat = path.stat()
    _TAIL_CACHE[path.resolve()] = (stat.st_size, stat.st_mtime_ns, prior)
    _VERIFIED_STATE_CACHE[path.resolve()] = (
        stat.st_size,
        stat.st_mtime_ns,
        copy.deepcopy(state),
    )
    return rows


def _verified_prior_event_sha256(path: Path) -> str | None:
    if not path.exists():
        _TAIL_CACHE.pop(path.resolve(), None)
        return None
    stat = path.stat()
    cached = _TAIL_CACHE.get(path.resolve())
    if cached is not None and cached[:2] == (stat.st_size, stat.st_mtime_ns):
        return cached[2]
    events = read_events(path)
    return cast("str | None", events[-1]["event_sha256"] if events else None)


def _verified_prior_state(path: Path) -> dict[str, object]:
    resolved = path.resolve()
    if not path.exists():
        _TAIL_CACHE.pop(resolved, None)
        _VERIFIED_STATE_CACHE.pop(resolved, None)
        return _empty_state()
    stat = path.stat()
    cached = _VERIFIED_STATE_CACHE.get(resolved)
    if cached is not None and cached[:2] == (stat.st_size, stat.st_mtime_ns):
        return copy.deepcopy(cached[2])
    read_events(path)
    verified = _VERIFIED_STATE_CACHE.get(resolved)
    if verified is None:
        raise RuntimeError("Verified queue state cache was not populated")
    return copy.deepcopy(verified[2])


def _append_event(
    path: Path,
    event: dict[str, object],
    *,
    expected_prior_sha256: str | None,
) -> dict[str, object]:
    prior = _verified_prior_event_sha256(path)
    if prior != expected_prior_sha256:
        raise RuntimeError("Queue event tail changed before append")
    row = {
        **event,
        "event_id": uuid4().hex,
        "recorded_at": _utc_now(),
        "run_signature": RUN_SIGNATURE,
        "schema_version": SCHEMA_VERSION,
        "policy_sha256": policy.POLICY_CANONICAL_SHA256,
        "prior_event_sha256": prior,
    }
    row["event_sha256"] = _event_payload_sha256(row)
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(
        row, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )
    with path.open("a", encoding="utf-8", newline="") as handle:
        handle.write(encoded + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    stat = path.stat()
    _TAIL_CACHE[path.resolve()] = (
        stat.st_size,
        stat.st_mtime_ns,
        cast("str", row["event_sha256"]),
    )
    return row


def _validate_mutation(mutation: Mapping[str, object]) -> None:
    operation = mutation.get("operation")
    key = mutation.get("key")
    if operation not in {"upsert_order", "delete_order", "record_skip"}:
        raise ValueError("Unknown decision mutation")
    if type(key) is not str or not key:
        raise ValueError("Decision mutation key is empty")
    if operation == "upsert_order":
        value = mutation.get("value")
        if not isinstance(value, dict):
            raise TypeError("upsert_order mutation requires an object value")
        policy.canonical_json_bytes(value)
    elif "value" in mutation:
        raise ValueError("Non-upsert mutation cannot include value")


def _apply_event_to_state(
    state: dict[str, object], event: Mapping[str, Any]
) -> dict[str, object]:
    orders = state.get("orders")
    skips = state.get("skip_keys")
    if not isinstance(orders, dict) or not isinstance(skips, list):
        raise TypeError("Queue state collections are malformed")
    if event.get("type") == "decision_commit":
        mutations = event.get("mutations")
        if not isinstance(mutations, list):
            raise TypeError("Decision commit mutations must be a list")
        for raw in mutations:
            if not isinstance(raw, dict):
                raise TypeError("Decision mutation must be an object")
            _validate_mutation(raw)
            operation = raw["operation"]
            key = cast("str", raw["key"])
            if operation == "upsert_order":
                orders[key] = copy.deepcopy(raw["value"])
            elif operation == "delete_order":
                orders.pop(key, None)
            elif key not in skips:
                skips.append(key)
    return state


def _semantic_state_sha256(state: Mapping[str, object]) -> str:
    return policy.canonical_sha256(
        {
            "orders": state.get("orders"),
            "skip_keys": state.get("skip_keys"),
        }
    )


def _empty_state() -> dict[str, object]:
    state: dict[str, object] = {
        "run_signature": RUN_SIGNATURE,
        "schema_version": SCHEMA_VERSION,
        "policy_sha256": policy.POLICY_CANONICAL_SHA256,
        "last_event_sha256": None,
        "orders": {},
        "skip_keys": [],
    }
    state["semantic_state_sha256"] = _semantic_state_sha256(state)
    return state


def reduce_events(events: Sequence[Mapping[str, Any]]) -> dict[str, object]:
    """Derive the replaceable cache from the durable event source of truth."""
    state = _empty_state()
    for event in events:
        _apply_event_to_state(state, event)
        if event.get("resulting_semantic_state_sha256") != _semantic_state_sha256(
            state
        ):
            raise ValueError("Queue event semantic state hash mismatch")
        state["last_event_sha256"] = cast("str", event["event_sha256"])
        state["semantic_state_sha256"] = event["resulting_semantic_state_sha256"]
    return state


def _atomic_replace(temp: Path, target: Path) -> None:
    last: OSError | None = None
    for attempt in range(MAX_REPLACE_ATTEMPTS):
        try:
            temp.replace(target)
            return
        except PermissionError as exc:
            last = exc
            if attempt + 1 < MAX_REPLACE_ATTEMPTS:
                time.sleep(0.025 * (attempt + 1))
    assert last is not None
    raise last


def write_state_cache(path: Path, state: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + f".{uuid4().hex}.tmp")
    encoded = json.dumps(
        state,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    try:
        with temp.open("wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        _atomic_replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def rebuild_state_cache(event_path: Path, state_path: Path) -> dict[str, object]:
    state = reduce_events(read_events(event_path))
    write_state_cache(state_path, state)
    return state


def _event_with_semantic_state(
    prior_state: Mapping[str, object], event: dict[str, object]
) -> tuple[dict[str, object], dict[str, object]]:
    next_state = copy.deepcopy(dict(prior_state))
    _apply_event_to_state(next_state, event)
    semantic_sha256 = _semantic_state_sha256(next_state)
    event["resulting_semantic_state_sha256"] = semantic_sha256
    next_state["semantic_state_sha256"] = semantic_sha256
    return event, next_state


def _persist_verified_state_after_event(
    event_path: Path,
    state_path: Path,
    state: dict[str, object],
    event: Mapping[str, object],
) -> dict[str, object]:
    event_sha256 = event.get("event_sha256")
    _validate_sha256(event_sha256, field="event.event_sha256")
    if event.get("resulting_semantic_state_sha256") != _semantic_state_sha256(
        state
    ):
        raise ValueError("Appended event semantic state does not match")
    state["last_event_sha256"] = event_sha256
    state["semantic_state_sha256"] = event["resulting_semantic_state_sha256"]
    write_state_cache(state_path, state)
    stat = event_path.stat()
    _VERIFIED_STATE_CACHE[event_path.resolve()] = (
        stat.st_size,
        stat.st_mtime_ns,
        copy.deepcopy(state),
    )
    return state


def commit_staged_decision(
    *,
    event_path: Path,
    state_path: Path,
    expected_feed_launch: policy.FeedLaunchAnchor,
    start_pair: ArchivedFeedPair,
    end_pair: ArchivedFeedPair,
    staged: StagedDecision,
    revalidate_end: Callable[[ArchivedFeedPair, StagedDecision], EndValidationProof],
) -> dict[str, object]:
    """Commit exactly once only after a stable feed generation and revalidation."""
    if not isinstance(expected_feed_launch, policy.FeedLaunchAnchor):
        raise TypeError("Expected feed launch is not a verified anchor")
    start_pair.validate(expected_feed_launch)
    end_pair.validate(expected_feed_launch)
    staged.validate()
    prior_state = _verified_prior_state(event_path)
    prior_sha256 = cast("str | None", prior_state["last_event_sha256"])
    if (
        start_pair.generation_id != end_pair.generation_id
        or start_pair.summary_sha256 != end_pair.summary_sha256
    ):
        event_payload, next_state = _event_with_semantic_state(
            prior_state,
            {
                "type": "feed_generation_advanced",
                "start_generation_id": start_pair.generation_id,
                "start_summary_sha256": start_pair.summary_sha256,
                "start_archive_receipt_sha256": start_pair.archive_receipt_sha256,
                "end_generation_id": end_pair.generation_id,
                "end_summary_sha256": end_pair.summary_sha256,
                "end_archive_receipt_sha256": end_pair.archive_receipt_sha256,
                "discarded_decision_kind": staged.decision_kind,
                "discarded_decision_key": staged.decision_key,
            },
        )
        event = _append_event(
            event_path,
            event_payload,
            expected_prior_sha256=prior_sha256,
        )
        _persist_verified_state_after_event(
            event_path, state_path, next_state, event
        )
        return event

    frozen_mutations = copy.deepcopy(list(staged.mutations))
    frozen_evidence = copy.deepcopy(staged.evidence)
    frozen_staged = StagedDecision(
        decision_kind=staged.decision_kind,
        decision_key=staged.decision_key,
        market_ticker=staged.market_ticker,
        threshold=staged.threshold,
        game_pk=staged.game_pk,
        trigger_at_bat_index=staged.trigger_at_bat_index,
        trigger_play_identity=staged.trigger_play_identity,
        ordered_prefix_fingerprint=staged.ordered_prefix_fingerprint,
        pre_total=staged.pre_total,
        post_total=staged.post_total,
        run_delta=staged.run_delta,
        t_seen=staged.t_seen,
        eligible_at=staged.eligible_at,
        mutations=tuple(copy.deepcopy(frozen_mutations)),
        evidence=copy.deepcopy(frozen_evidence),
    )
    proof = revalidate_end(end_pair, frozen_staged)
    if not isinstance(proof, EndValidationProof):
        raise TypeError("End revalidation did not return EndValidationProof")
    proof_dict = proof.to_dict()
    _validate_end_proof_dict(proof_dict)
    expected_proof = {
        "feed_generation_id": end_pair.generation_id,
        "feed_summary_sha256": end_pair.summary_sha256,
        "market_ticker": frozen_staged.market_ticker,
        "threshold": frozen_staged.threshold,
        "game_pk": frozen_staged.game_pk,
        "trigger_at_bat_index": frozen_staged.trigger_at_bat_index,
        "trigger_play_identity": frozen_staged.trigger_play_identity,
        "ordered_prefix_fingerprint": frozen_staged.ordered_prefix_fingerprint,
        "pre_total": frozen_staged.pre_total,
        "post_total": frozen_staged.post_total,
        "run_delta": frozen_staged.run_delta,
        "t_seen": frozen_staged.t_seen,
        "eligible_at": frozen_staged.eligible_at,
    }
    if any(proof_dict.get(key) != value for key, value in expected_proof.items()):
        raise ValueError("End-validation proof does not bind the staged decision")
    proof_sha256 = policy.canonical_sha256(proof_dict)
    event_payload, next_state = _event_with_semantic_state(
        prior_state,
        {
            "type": "decision_commit",
            "decision_kind": frozen_staged.decision_kind,
            "decision_key": frozen_staged.decision_key,
            "feed_generation_id": end_pair.generation_id,
            "feed_summary_sha256": end_pair.summary_sha256,
            "start_archive_receipt_sha256": start_pair.archive_receipt_sha256,
            "end_archive_receipt_sha256": end_pair.archive_receipt_sha256,
            "market_ticker": frozen_staged.market_ticker,
            "threshold": frozen_staged.threshold,
            "game_pk": frozen_staged.game_pk,
            "trigger_at_bat_index": frozen_staged.trigger_at_bat_index,
            "trigger_play_identity": frozen_staged.trigger_play_identity,
            "ordered_prefix_fingerprint": frozen_staged.ordered_prefix_fingerprint,
            "pre_total": frozen_staged.pre_total,
            "post_total": frozen_staged.post_total,
            "run_delta": frozen_staged.run_delta,
            "t_seen": frozen_staged.t_seen,
            "eligible_at": frozen_staged.eligible_at,
            "end_validation_proof": proof_dict,
            "end_validation_proof_sha256": proof_sha256,
            "mutations": frozen_mutations,
            "evidence": frozen_evidence,
        },
    )
    event = _append_event(
        event_path,
        event_payload,
        expected_prior_sha256=prior_sha256,
    )
    _persist_verified_state_after_event(event_path, state_path, next_state, event)
    return event


def file_sha256(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())
