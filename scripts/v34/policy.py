"""Load and verify the independently reviewed v34 policy lock."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, cast

if TYPE_CHECKING:
    from collections.abc import Mapping

POLICY_PATH: Final = (
    Path(__file__).resolve().parents[2]
    / "research"
    / "v34"
    / "01-primary-policy-lock.json"
)
REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[2]
EXPECTED_CANONICAL_SHA256: Final = (
    "6c85a6a901fd0f4c0eb639869b0f43bf438e24c5ea1f7739827e81c6361b80d0"
)
FEED_RUN_SIGNATURE: Final = "prospective-v34-20260718-lock1"
FEED_SCHEMA_VERSION: Final = 8
FEED_OUTPUT_ROOT: Final = "data/v34/prospective-v34-20260718-lock1"
QUEUE_RUN_SIGNATURE: Final = "prospective-queue-v34-20260718-lock1"
QUEUE_SCHEMA_VERSION: Final = 9
QUEUE_OUTPUT_ROOT: Final = "data/v34/prospective-queue-v34-20260718-lock1"
FEED_PROVENANCE_KEYS: Final = (
    "launch_manifest_sha256",
    "launch_nonce",
    "policy_sha256",
    "run_signature",
    "schema_version",
    "source_hashes",
)
QUEUE_PROVENANCE_KEYS: Final = FEED_PROVENANCE_KEYS
FEED_LAUNCH_MANIFEST_KEYS: Final = {
    "created_at",
    "launch_nonce",
    "manifest_kind",
    "output_root",
    "policy_sha256",
    "run_signature",
    "schema_version",
    "source_hashes",
}
REQUIRED_LAUNCH_SOURCES: Final = {
    "scripts/v34/decision_commit.py",
    "scripts/v34/feed_archive.py",
    "scripts/v34/feed_lifecycle.py",
    "scripts/v34/policy.py",
    "scripts/v34/prefix_dependency.py",
}
QUEUE_LAUNCH_MANIFEST_KEYS: Final = FEED_LAUNCH_MANIFEST_KEYS
REQUIRED_QUEUE_LAUNCH_SOURCES: Final = {
    "scripts/v34/decision_commit.py",
    "scripts/v34/feed_archive.py",
    "scripts/v34/policy.py",
    "scripts/v34/prefix_dependency.py",
}


@dataclass(frozen=True)
class FeedLaunchAnchor:
    """Verified canonical launch manifest and its derived provenance."""

    manifest_bytes: bytes
    manifest_sha256: str
    provenance_bytes: bytes

    @property
    def provenance(self) -> dict[str, object]:
        parsed = json.loads(self.provenance_bytes)
        if not isinstance(parsed, dict):
            raise TypeError("Verified launch provenance is not an object")
        return cast("dict[str, object]", parsed)


@dataclass(frozen=True)
class QueueLaunchAnchor:
    """Verified canonical queue launch manifest and derived provenance."""

    manifest_bytes: bytes
    manifest_sha256: str
    provenance_bytes: bytes

    @property
    def provenance(self) -> dict[str, object]:
        parsed = json.loads(self.provenance_bytes)
        if not isinstance(parsed, dict):
            raise TypeError("Verified queue launch provenance is not an object")
        return cast("dict[str, object]", parsed)


def canonical_json_bytes(value: object) -> bytes:
    """Return the exact canonical JSON encoding used by the policy review."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def validate_sha256(value: object, *, field: str) -> str:
    if (
        type(value) is not str
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{field} must be lowercase SHA256")
    return value


def validated_feed_provenance(
    value: Mapping[str, object], *, field: str
) -> dict[str, object]:
    """Return the exact v34 launch provenance or fail closed."""
    if value.get("run_signature") != FEED_RUN_SIGNATURE:
        raise ValueError(f"{field} run signature mismatch")
    if value.get("schema_version") != FEED_SCHEMA_VERSION:
        raise ValueError(f"{field} schema mismatch")
    if value.get("policy_sha256") != EXPECTED_CANONICAL_SHA256:
        raise ValueError(f"{field} policy hash mismatch")
    launch_nonce = value.get("launch_nonce")
    if type(launch_nonce) is not str or not launch_nonce:
        raise ValueError(f"{field} launch nonce is empty")
    validate_sha256(
        value.get("launch_manifest_sha256"),
        field=f"{field}.launch_manifest_sha256",
    )
    source_hashes = value.get("source_hashes")
    if not isinstance(source_hashes, dict) or not source_hashes:
        raise ValueError(f"{field} source hashes are missing")
    for source_name, source_sha256 in source_hashes.items():
        if type(source_name) is not str or not source_name:
            raise ValueError(f"{field} source hash name is empty")
        validate_sha256(
            source_sha256,
            field=f"{field}.source_hashes[{source_name}]",
        )
    return {
        key: value[key]
        for key in FEED_PROVENANCE_KEYS
    }


def validated_queue_provenance(
    value: Mapping[str, object], *, field: str
) -> dict[str, object]:
    """Return exact v34 queue launch provenance or fail closed."""
    if set(value) != set(QUEUE_PROVENANCE_KEYS):
        raise ValueError(f"{field} queue provenance keys differ")
    if value.get("run_signature") != QUEUE_RUN_SIGNATURE:
        raise ValueError(f"{field} queue run signature mismatch")
    if value.get("schema_version") != QUEUE_SCHEMA_VERSION:
        raise ValueError(f"{field} queue schema mismatch")
    if value.get("policy_sha256") != EXPECTED_CANONICAL_SHA256:
        raise ValueError(f"{field} queue policy hash mismatch")
    launch_nonce = value.get("launch_nonce")
    if type(launch_nonce) is not str or not launch_nonce:
        raise ValueError(f"{field} queue launch nonce is empty")
    validate_sha256(
        value.get("launch_manifest_sha256"),
        field=f"{field}.launch_manifest_sha256",
    )
    source_hashes = value.get("source_hashes")
    if not isinstance(source_hashes, dict) or not REQUIRED_QUEUE_LAUNCH_SOURCES.issubset(
        source_hashes
    ):
        raise ValueError(f"{field} queue source hashes are missing")
    for source_name, source_sha256 in source_hashes.items():
        if type(source_name) is not str or not source_name:
            raise ValueError(f"{field} queue source hash name is empty")
        validate_sha256(
            source_sha256,
            field=f"{field}.source_hashes[{source_name}]",
        )
    return {key: value[key] for key in QUEUE_PROVENANCE_KEYS}


def verify_feed_launch_manifest_bytes(raw: bytes) -> FeedLaunchAnchor:
    """Anchor a v34 run to canonical manifest bytes and current source bytes."""
    if type(raw) is not bytes:
        raise TypeError("Feed launch manifest must be immutable bytes")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("Feed launch manifest JSON is invalid") from exc
    if not isinstance(parsed, dict) or set(parsed) != FEED_LAUNCH_MANIFEST_KEYS:
        raise ValueError("Feed launch manifest keys differ")
    if raw != canonical_json_bytes(parsed):
        raise ValueError("Feed launch manifest is not canonical JSON")
    if parsed.get("manifest_kind") != "v34_feed_launch":
        raise ValueError("Feed launch manifest kind mismatch")
    if parsed.get("run_signature") != FEED_RUN_SIGNATURE:
        raise ValueError("Feed launch manifest run signature mismatch")
    if parsed.get("schema_version") != FEED_SCHEMA_VERSION:
        raise ValueError("Feed launch manifest schema mismatch")
    if parsed.get("policy_sha256") != EXPECTED_CANONICAL_SHA256:
        raise ValueError("Feed launch manifest policy hash mismatch")
    launch_nonce = parsed.get("launch_nonce")
    if type(launch_nonce) is not str or not launch_nonce:
        raise ValueError("Feed launch manifest nonce is empty")
    created_at = parsed.get("created_at")
    if type(created_at) is not str:
        raise TypeError("Feed launch manifest created_at must be a string")
    created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    if created.tzinfo is None:
        raise ValueError("Feed launch manifest created_at is timezone-naive")
    output_root = parsed.get("output_root")
    if output_root != FEED_OUTPUT_ROOT:
        raise ValueError("Feed launch manifest output root is not fresh v34")
    source_hashes = parsed.get("source_hashes")
    if not isinstance(source_hashes, dict) or not REQUIRED_LAUNCH_SOURCES.issubset(
        source_hashes
    ):
        raise ValueError("Feed launch manifest required source hashes are missing")
    for source_name, claimed_sha256 in source_hashes.items():
        if type(source_name) is not str or not source_name:
            raise ValueError("Feed launch manifest source name is empty")
        validate_sha256(
            claimed_sha256,
            field=f"launch.source_hashes[{source_name}]",
        )
        source_path = (REPOSITORY_ROOT / source_name).resolve()
        try:
            source_path.relative_to(REPOSITORY_ROOT)
        except ValueError as exc:
            raise ValueError("Feed launch manifest source escapes repository") from exc
        if not source_path.is_file():
            raise ValueError(f"Feed launch source is missing: {source_name}")
        actual_sha256 = hashlib.sha256(source_path.read_bytes()).hexdigest()
        if claimed_sha256 != actual_sha256:
            raise ValueError(f"Feed launch source hash mismatch: {source_name}")
    manifest_sha256 = hashlib.sha256(raw).hexdigest()
    provenance = {
        "launch_manifest_sha256": manifest_sha256,
        "launch_nonce": launch_nonce,
        "policy_sha256": EXPECTED_CANONICAL_SHA256,
        "run_signature": FEED_RUN_SIGNATURE,
        "schema_version": FEED_SCHEMA_VERSION,
        "source_hashes": source_hashes,
    }
    return FeedLaunchAnchor(
        manifest_bytes=raw,
        manifest_sha256=manifest_sha256,
        provenance_bytes=canonical_json_bytes(provenance),
    )


def reverify_feed_launch_anchor(anchor: FeedLaunchAnchor) -> FeedLaunchAnchor:
    """Re-derive every anchor field so direct construction cannot bypass checks."""
    if not isinstance(anchor, FeedLaunchAnchor):
        raise TypeError("Expected feed launch is not a FeedLaunchAnchor")
    verified = verify_feed_launch_manifest_bytes(anchor.manifest_bytes)
    if (
        anchor.manifest_sha256 != verified.manifest_sha256
        or anchor.provenance_bytes != verified.provenance_bytes
    ):
        raise ValueError("Feed launch anchor derivation mismatch")
    return verified


def verify_queue_launch_manifest_bytes(raw: bytes) -> QueueLaunchAnchor:
    """Anchor a queue run to canonical manifest bytes and current source bytes."""
    if type(raw) is not bytes:
        raise TypeError("Queue launch manifest must be immutable bytes")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("Queue launch manifest JSON is invalid") from exc
    if not isinstance(parsed, dict) or set(parsed) != QUEUE_LAUNCH_MANIFEST_KEYS:
        raise ValueError("Queue launch manifest keys differ")
    if raw != canonical_json_bytes(parsed):
        raise ValueError("Queue launch manifest is not canonical JSON")
    if parsed.get("manifest_kind") != "v34_queue_launch":
        raise ValueError("Queue launch manifest kind mismatch")
    if parsed.get("run_signature") != QUEUE_RUN_SIGNATURE:
        raise ValueError("Queue launch manifest run signature mismatch")
    if parsed.get("schema_version") != QUEUE_SCHEMA_VERSION:
        raise ValueError("Queue launch manifest schema mismatch")
    if parsed.get("policy_sha256") != EXPECTED_CANONICAL_SHA256:
        raise ValueError("Queue launch manifest policy hash mismatch")
    launch_nonce = parsed.get("launch_nonce")
    if type(launch_nonce) is not str or not launch_nonce:
        raise ValueError("Queue launch manifest nonce is empty")
    created_at = parsed.get("created_at")
    if type(created_at) is not str:
        raise TypeError("Queue launch manifest created_at must be a string")
    created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    if created.tzinfo is None:
        raise ValueError("Queue launch manifest created_at is timezone-naive")
    if parsed.get("output_root") != QUEUE_OUTPUT_ROOT:
        raise ValueError("Queue launch manifest output root is not fresh v34")
    source_hashes = parsed.get("source_hashes")
    if not isinstance(source_hashes, dict) or not REQUIRED_QUEUE_LAUNCH_SOURCES.issubset(
        source_hashes
    ):
        raise ValueError("Queue launch manifest required source hashes are missing")
    for source_name, claimed_sha256 in source_hashes.items():
        if type(source_name) is not str or not source_name:
            raise ValueError("Queue launch manifest source name is empty")
        validate_sha256(
            claimed_sha256,
            field=f"queue_launch.source_hashes[{source_name}]",
        )
        source_path = (REPOSITORY_ROOT / source_name).resolve()
        try:
            source_path.relative_to(REPOSITORY_ROOT)
        except ValueError as exc:
            raise ValueError("Queue launch source escapes repository") from exc
        if not source_path.is_file():
            raise ValueError(f"Queue launch source is missing: {source_name}")
        actual_sha256 = hashlib.sha256(source_path.read_bytes()).hexdigest()
        if claimed_sha256 != actual_sha256:
            raise ValueError(f"Queue launch source hash mismatch: {source_name}")
    manifest_sha256 = hashlib.sha256(raw).hexdigest()
    provenance = {
        "launch_manifest_sha256": manifest_sha256,
        "launch_nonce": launch_nonce,
        "policy_sha256": EXPECTED_CANONICAL_SHA256,
        "run_signature": QUEUE_RUN_SIGNATURE,
        "schema_version": QUEUE_SCHEMA_VERSION,
        "source_hashes": source_hashes,
    }
    return QueueLaunchAnchor(
        manifest_bytes=raw,
        manifest_sha256=manifest_sha256,
        provenance_bytes=canonical_json_bytes(provenance),
    )


def reverify_queue_launch_anchor(anchor: QueueLaunchAnchor) -> QueueLaunchAnchor:
    """Re-derive every queue anchor field before it authorizes custody."""
    if not isinstance(anchor, QueueLaunchAnchor):
        raise TypeError("Expected queue launch is not a QueueLaunchAnchor")
    verified = verify_queue_launch_manifest_bytes(anchor.manifest_bytes)
    if (
        anchor.manifest_sha256 != verified.manifest_sha256
        or anchor.provenance_bytes != verified.provenance_bytes
    ):
        raise ValueError("Queue launch anchor derivation mismatch")
    return verified


def validate_feed_artifact_provenance(
    value: Mapping[str, object],
    *,
    anchor: FeedLaunchAnchor,
    field: str,
) -> dict[str, object]:
    verified_anchor = reverify_feed_launch_anchor(anchor)
    actual = validated_feed_provenance(value, field=field)
    if actual != verified_anchor.provenance:
        raise ValueError(f"{field} launch provenance mismatch")
    return actual


def validate_queue_artifact_provenance(
    value: Mapping[str, object],
    *,
    anchor: QueueLaunchAnchor,
    field: str,
) -> dict[str, object]:
    verified_anchor = reverify_queue_launch_anchor(anchor)
    actual = validated_queue_provenance(value, field=field)
    if actual != verified_anchor.provenance:
        raise ValueError(f"{field} queue launch provenance mismatch")
    return actual


def load_verified_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    raw = path.read_bytes()
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise TypeError("V34 primary policy must be a JSON object")
    if parsed.get("schema_version") != 2:
        raise ValueError("V34 primary policy schema mismatch")
    actual = canonical_sha256(parsed)
    if actual != EXPECTED_CANONICAL_SHA256:
        raise ValueError(f"V34 primary policy hash mismatch: {actual}")
    return cast("dict[str, Any]", parsed)


PRIMARY_POLICY: Final = load_verified_policy()
POLICY_CANONICAL_SHA256: Final = EXPECTED_CANONICAL_SHA256
