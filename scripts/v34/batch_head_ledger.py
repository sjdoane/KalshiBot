"""One custody PREPARE and COMMIT for every v34 all-game feed poll.

This is the production cadence path. The older per-game wrapper remains only as
a transaction reference test and may not be used by an observer launch.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final, Never, cast

from scripts.v34 import (
    batch_mutation_guard,
    feed_archive,
    feed_lineage,
    head_ledger,
    policy,
    storage_preflight,
)
from scripts.v34 import feed_lifecycle as lifecycle
from scripts.v34.decision_commit import ArchivedFeedPair

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from typing import Literal

SCHEMA_VERSION: Final = 1
BATCH_SEQUENCE_WIDTH: Final = 12
MAX_BATCH_OPERATIONS: Final = 64
MAX_BATCH_RECORD_BYTES: Final = head_ledger.MAX_LEDGER_RECORD_BYTES
BATCH_PREPARE_KEYS: Final = {
    "batch_sequence",
    "feed_launch_manifest_sha256",
    "kind",
    "operations",
    "prior_batch_commit_sha256",
    "registry_manifest_sha256",
    "schema_version",
}
BATCH_COMMIT_KEYS: Final = {
    "batch_sequence",
    "committed_heads",
    "feed_launch_manifest_sha256",
    "kind",
    "prepare_sha256",
    "prior_batch_commit_sha256",
    "registry_manifest_sha256",
    "schema_version",
}
RUNTIME_RESTORE_KEYS: Final = {
    "committed_batch_sha256",
    "feed_launch_manifest_sha256",
    "heads",
    "kind",
    "prior_restore_sha256",
    "registry_manifest_sha256",
    "restore_sequence",
    "restored_at",
    "restored_runtime_root",
    "restored_runtime_volume",
    "schema_version",
}
_BATCH_DIRECTORY_NAME = re.compile(r"^(\d{12})-([0-9a-f]{64})$")
_BATCH_COMMIT_NAME = re.compile(r"^commit-([0-9a-f]{64})\.json$")
_RESTORE_NAME = re.compile(r"^(\d{12})-([0-9a-f]{64})\.json$")


class BatchHeadLedgerFatalError(RuntimeError):
    """The global batch chain, lineage heads, or custody mirrors differ."""


def _fatal(message: str, *, cause: Exception | None = None) -> Never:
    error = BatchHeadLedgerFatalError(message)
    if cause is None:
        raise error
    raise error from cause


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _digest(value: object, *, field: str, optional: bool = False) -> str | None:
    if optional and value is None:
        return None
    try:
        return policy.validate_sha256(value, field=field)
    except (TypeError, ValueError) as exc:
        _fatal(f"{field} is not lowercase SHA256", cause=exc)


def _exact_int(value: object, *, field: str, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        _fatal(f"{field} must be an exact integer at least {minimum}")
    return value


def _canonical_object(raw: bytes, *, field: str) -> dict[str, object]:
    if type(raw) is not bytes or len(raw) > MAX_BATCH_RECORD_BYTES:
        _fatal(f"{field} exceeds the batch record byte limit")
    try:
        parsed = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        _fatal(f"{field} is not JSON", cause=exc)
    if not isinstance(parsed, dict) or raw != policy.canonical_json_bytes(parsed):
        _fatal(f"{field} is not a canonical JSON object")
    return cast("dict[str, object]", parsed)


@dataclass(frozen=True, slots=True)
class BatchTransitionRequest:
    transition: lifecycle.FeedTransition
    recorded_at: str
    expected_snapshot: feed_lineage.FeedLineageSnapshot


@dataclass(frozen=True, slots=True)
class ArchiveSourceBinding:
    generation_id: str
    summary_sha256: str
    feed_receipt_sha256: str
    archive_receipt_sha256: str
    archive_path: str


@dataclass(frozen=True, slots=True)
class BatchPrepare:
    record_sha256: str
    raw: bytes
    batch_sequence: int
    prior_commit_sha256: str | None
    feed_plan: feed_lineage.FeedBatchPlan
    source_binding: ArchiveSourceBinding


@dataclass(frozen=True, slots=True)
class BatchChainState:
    heads: tuple[tuple[int, feed_lineage.FeedPortableHead], ...]
    prior_commit_sha256: str | None
    next_batch_sequence: int
    open_prepare: BatchPrepare | None
    unreferenced_source_paths: tuple[str, ...]
    unreferenced_source_bytes: int

    def head_for(self, game_pk: int) -> feed_lineage.FeedPortableHead | None:
        return dict(self.heads).get(game_pk)


@dataclass(frozen=True, slots=True)
class CommittedFeedBatch:
    snapshots: tuple[tuple[int, feed_lineage.FeedLineageSnapshot], ...]
    prepare_sha256: str
    commit_sha256: str
    capital_eligible: bool = False


@dataclass(slots=True)
class BatchLedgerSession:
    config: head_ledger.HeadLedgerConfig
    manifest_sha256: str
    registrations: tuple[tuple[int, head_ledger.GameRegistration], ...]
    state: BatchChainState
    batch_count: int
    latest_batch_name: str | None
    mutation_guard: batch_mutation_guard.BatchMutationGuard
    snapshots: tuple[tuple[int, feed_lineage.FeedLineageSnapshot], ...]
    hot_integrities: tuple[tuple[int, feed_lineage._FeedHotIntegrity], ...]

    def close(self) -> None:
        self.mutation_guard.close()
        for _game_pk, hot_integrity in self.hot_integrities:
            hot_integrity.close()

    def __enter__(self) -> BatchLedgerSession:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def __del__(self) -> None:
        with suppress(Exception):
            self.close()


@dataclass(frozen=True, slots=True)
class RestoredRuntime:
    config: head_ledger.HeadLedgerConfig
    snapshots: tuple[tuple[int, feed_lineage.FeedLineageSnapshot], ...]
    restore_record_sha256: str


def _batches_root(control_root: Path) -> Path:
    return control_root / "batches"


def _source_archive_root(config: head_ledger.HeadLedgerConfig) -> Path:
    return config.custody_root / "source-archive"


def _ensure_batch_layout(config: head_ledger.HeadLedgerConfig) -> None:
    if (
        feed_archive.MAX_ARCHIVED_PAIR_BYTES
        != storage_preflight.MAX_SOURCE_PERSISTED_BYTES
    ):
        _fatal("source archive read and persistence caps differ")
    head_ledger.validate_config(config)
    for control_root in (
        config.custody_control_root,
        config.primary_control_root,
    ):
        trusted_root = (
            config.custody_root
            if control_root == config.custody_control_root
            else config.runtime_root
        )
        try:
            feed_archive._ensure_durable_directory(
                trusted_root,
                _batches_root(control_root),
            )
        except (OSError, ValueError, feed_archive.ArchiveCollisionError) as exc:
            _fatal("batch ledger directory is not durable", cause=exc)
    try:
        feed_archive._ensure_durable_directory(
            config.custody_root,
            _source_archive_root(config),
        )
    except (OSError, ValueError, feed_archive.ArchiveCollisionError) as exc:
        _fatal("batch source archive directory is not durable", cause=exc)


def _verify_control_root_inventory(config: head_ledger.HeadLedgerConfig) -> None:
    expected = {
        ".ledger.guard.v34append.lock",
        "batches",
        "registry",
        "transactions",
    }
    for control_root in (
        config.custody_control_root,
        config.primary_control_root,
    ):
        if head_ledger._directory_names(control_root) != expected:
            _fatal("batch control root inventory differs")


def _read_only_custody_batch_names(
    config: head_ledger.HeadLedgerConfig,
) -> set[str]:
    custody_root = _batches_root(config.custody_control_root)
    custody_names = head_ledger._directory_names(custody_root)
    if any(_BATCH_DIRECTORY_NAME.fullmatch(name) is None for name in custody_names):
        _fatal("startup custody batch inventory contains an unknown entry")
    return custody_names


def _read_only_startup_storage_inputs(
    config: head_ledger.HeadLedgerConfig,
) -> tuple[int, int]:
    custody_root = _batches_root(config.custody_control_root)
    primary_root = _batches_root(config.primary_control_root)
    custody_names = _read_only_custody_batch_names(config)
    missing_primary_bytes = 0
    for name in custody_names:
        custody_transaction = custody_root / name
        primary_transaction = primary_root / name
        feed_archive._assert_not_redirect(custody_transaction)
        if not custody_transaction.is_dir():
            _fatal("startup custody batch transaction is not a directory")
        custody_files = head_ledger._directory_names(custody_transaction)
        primary_files = (
            head_ledger._directory_names(primary_transaction)
            if primary_transaction.is_dir()
            else set()
        )
        for filename in custody_files - primary_files:
            source = custody_transaction / filename
            feed_archive._assert_not_redirect(source)
            try:
                source_stat = source.stat(follow_symlinks=False)
            except FileNotFoundError as exc:
                _fatal("startup custody batch member disappeared", cause=exc)
            if not source.is_file():
                _fatal("startup custody batch member is not a file")
            missing_primary_bytes += source_stat.st_size
    return len(custody_names), missing_primary_bytes


def _replay_all_heads(
    config: head_ledger.HeadLedgerConfig,
    state: BatchChainState,
) -> tuple[tuple[int, feed_lineage.FeedLineageSnapshot], ...]:
    return tuple(
        (
            game_pk,
            head_ledger._replay_portable_head(config, head),
        )
        for game_pk, head in state.heads
    )


def _batch_directory(
    control_root: Path,
    *,
    sequence: int,
    prepare_sha256: str,
) -> Path:
    return _batches_root(control_root) / (
        f"{sequence:0{BATCH_SEQUENCE_WIDTH}d}-{prepare_sha256}"
    )


def _operation_record(
    config: head_ledger.HeadLedgerConfig,
    *,
    manifest_sha256: str,
    registration: head_ledger.GameRegistration,
    plan: feed_lineage.FeedAppendPlan,
    prior_batch_commit_sha256: str | None,
    request: BatchTransitionRequest,
    source_archive: ArchivedFeedPair,
) -> dict[str, object]:
    archive_receipt = _canonical_object(
        source_archive.archive_receipt_bytes,
        field="source archive receipt",
    )
    archive_path = archive_receipt.get("archive_path")
    if type(archive_path) is not str:
        _fatal("source archive receipt path is missing")
    raw = head_ledger._prepare_record(
        config,
        manifest_sha256=manifest_sha256,
        registration=registration,
        plan=plan,
        prior_commit_sha256=prior_batch_commit_sha256,
        source_archive_path=archive_path,
        source_archive_receipt_sha256=source_archive.archive_receipt_sha256,
        source_feed_receipt_sha256=source_archive.feed_receipt_sha256,
        source_feed_summary_sha256=source_archive.summary_sha256,
        source_generation_id=source_archive.generation_id,
    )
    return _canonical_object(raw, field="batch operation")


def _prepare_record(
    config: head_ledger.HeadLedgerConfig,
    *,
    manifest_sha256: str,
    sequence: int,
    prior_commit_sha256: str | None,
    operations: tuple[dict[str, object], ...],
) -> bytes:
    return policy.canonical_json_bytes(
        {
            "batch_sequence": sequence,
            "feed_launch_manifest_sha256": config.feed_anchor.manifest_sha256,
            "kind": "v34_batch_prepare",
            "operations": list(operations),
            "prior_batch_commit_sha256": prior_commit_sha256,
            "registry_manifest_sha256": manifest_sha256,
            "schema_version": SCHEMA_VERSION,
        }
    )


def _parse_prepare(
    raw: bytes,
    *,
    config: head_ledger.HeadLedgerConfig,
    manifest_sha256: str,
    registrations: Mapping[int, head_ledger.GameRegistration],
) -> BatchPrepare:
    parsed = _canonical_object(raw, field="batch PREPARE")
    if set(parsed) != BATCH_PREPARE_KEYS:
        _fatal("batch PREPARE keys differ")
    if (
        parsed.get("kind") != "v34_batch_prepare"
        or parsed.get("schema_version") != SCHEMA_VERSION
        or parsed.get("feed_launch_manifest_sha256")
        != config.feed_anchor.manifest_sha256
        or parsed.get("registry_manifest_sha256") != manifest_sha256
    ):
        _fatal("batch PREPARE provenance differs")
    sequence = _exact_int(
        parsed.get("batch_sequence"),
        field="batch_prepare.batch_sequence",
        minimum=1,
    )
    prior_commit = _digest(
        parsed.get("prior_batch_commit_sha256"),
        field="batch_prepare.prior_batch_commit_sha256",
        optional=True,
    )
    operation_values = parsed.get("operations")
    if (
        not isinstance(operation_values, list)
        or not operation_values
        or len(operation_values) > MAX_BATCH_OPERATIONS
    ):
        _fatal("batch PREPARE operation count differs")
    items: list[feed_lineage.FeedBatchInput] = []
    plans: list[feed_lineage.FeedAppendPlan] = []
    source_bindings: list[ArchiveSourceBinding] = []
    for value in operation_values:
        if not isinstance(value, dict):
            _fatal("batch PREPARE operation is not an object")
        game_pk = _exact_int(value.get("game_pk"), field="operation.game_pk", minimum=1)
        registration = registrations.get(game_pk)
        if registration is None:
            _fatal("batch PREPARE operation game is not registered")
        operation_raw = policy.canonical_json_bytes(value)
        operation = head_ledger._parse_prepare(
            operation_raw,
            config=config,
            manifest_sha256=manifest_sha256,
            registration=registration,
        )
        if operation.record.get("prior_commit_sha256") != prior_commit:
            _fatal("batch operation prior commit differs from the batch chain")
        source_archive_path = operation.record.get("source_archive_path")
        source_generation_id = operation.record.get("source_generation_id")
        assert isinstance(source_archive_path, str)
        assert isinstance(source_generation_id, str)
        source_bindings.append(
            ArchiveSourceBinding(
                generation_id=source_generation_id,
                summary_sha256=cast(
                    "str",
                    operation.record.get("source_feed_summary_sha256"),
                ),
                feed_receipt_sha256=cast(
                    "str",
                    operation.record.get("source_feed_receipt_sha256"),
                ),
                archive_receipt_sha256=cast(
                    "str",
                    operation.record.get("source_archive_receipt_sha256"),
                ),
                archive_path=source_archive_path,
            )
        )
        items.append(
            feed_lineage.FeedBatchInput(
                path=config.runtime_root / registration.lineage_relative_path,
                transition=operation.transition,
                recorded_at=operation.plan.recorded_at,
                expected_snapshot=None,
            )
        )
        plans.append(operation.plan)
    ordered_pairs = sorted(
        zip(items, plans, strict=True),
        key=lambda pair: pair[1].game_pk,
    )
    if [plan.game_pk for _, plan in ordered_pairs] != [plan.game_pk for plan in plans]:
        _fatal("batch PREPARE operations are not sorted by game_pk")
    if len({plan.game_pk for plan in plans}) != len(plans):
        _fatal("batch PREPARE contains a duplicate game")
    if len(set(source_bindings)) != 1:
        _fatal("batch PREPARE operations do not share one source archive")
    return BatchPrepare(
        record_sha256=_sha256(raw),
        raw=raw,
        batch_sequence=sequence,
        prior_commit_sha256=prior_commit,
        feed_plan=feed_lineage.FeedBatchPlan(
            inputs=tuple(items),
            plans=tuple(plans),
        ),
        source_binding=source_bindings[0],
    )


def _result_heads(
    current: Mapping[int, feed_lineage.FeedPortableHead],
    prepare: BatchPrepare,
) -> tuple[tuple[int, feed_lineage.FeedPortableHead], ...]:
    result = dict(current)
    for plan in prepare.feed_plan.plans:
        if result.get(plan.game_pk) != plan.before_head:
            _fatal("batch operation prior head differs from the global chain")
        result[plan.game_pk] = plan.expected_post_head
    return tuple(sorted(result.items()))


def _commit_record(
    config: head_ledger.HeadLedgerConfig,
    *,
    manifest_sha256: str,
    prepare: BatchPrepare,
    committed_heads: tuple[tuple[int, feed_lineage.FeedPortableHead], ...],
) -> bytes:
    return policy.canonical_json_bytes(
        {
            "batch_sequence": prepare.batch_sequence,
            "committed_heads": [head.to_dict() for _, head in committed_heads],
            "feed_launch_manifest_sha256": config.feed_anchor.manifest_sha256,
            "kind": "v34_batch_commit",
            "prepare_sha256": prepare.record_sha256,
            "prior_batch_commit_sha256": prepare.prior_commit_sha256,
            "registry_manifest_sha256": manifest_sha256,
            "schema_version": SCHEMA_VERSION,
        }
    )


def _parse_commit(
    raw: bytes,
    *,
    config: head_ledger.HeadLedgerConfig,
    manifest_sha256: str,
    registrations: Mapping[int, head_ledger.GameRegistration],
    prepare: BatchPrepare,
    expected_heads: tuple[tuple[int, feed_lineage.FeedPortableHead], ...],
) -> str:
    parsed = _canonical_object(raw, field="batch COMMIT")
    if set(parsed) != BATCH_COMMIT_KEYS:
        _fatal("batch COMMIT keys differ")
    if (
        parsed.get("kind") != "v34_batch_commit"
        or parsed.get("schema_version") != SCHEMA_VERSION
        or parsed.get("feed_launch_manifest_sha256")
        != config.feed_anchor.manifest_sha256
        or parsed.get("registry_manifest_sha256") != manifest_sha256
        or parsed.get("batch_sequence") != prepare.batch_sequence
        or parsed.get("prepare_sha256") != prepare.record_sha256
        or parsed.get("prior_batch_commit_sha256") != prepare.prior_commit_sha256
    ):
        _fatal("batch COMMIT provenance or chain differs")
    head_values = parsed.get("committed_heads")
    if not isinstance(head_values, list) or len(head_values) != len(registrations):
        _fatal("batch COMMIT head registry size differs")
    parsed_heads: list[tuple[int, feed_lineage.FeedPortableHead]] = []
    for value in head_values:
        if not isinstance(value, dict):
            _fatal("batch COMMIT head is not an object")
        game_pk = _exact_int(value.get("game_pk"), field="commit_head.game_pk", minimum=1)
        if game_pk not in registrations:
            _fatal("batch COMMIT contains an unregistered game")
        parsed_heads.append(
            (
                game_pk,
                head_ledger._head_from_dict(value, expected_game_pk=game_pk),
            )
        )
    if parsed_heads != sorted(parsed_heads) or len(dict(parsed_heads)) != len(parsed_heads):
        _fatal("batch COMMIT heads are duplicated or unsorted")
    if tuple(parsed_heads) != expected_heads:
        _fatal("batch COMMIT heads differ from its PREPARE")
    return _sha256(raw)


def _ensure_batch_transaction_directories(
    config: head_ledger.HeadLedgerConfig,
    *,
    sequence: int,
    prepare_sha256: str,
) -> tuple[Path, Path]:
    custody = _batch_directory(
        config.custody_control_root,
        sequence=sequence,
        prepare_sha256=prepare_sha256,
    )
    primary = _batch_directory(
        config.primary_control_root,
        sequence=sequence,
        prepare_sha256=prepare_sha256,
    )
    try:
        feed_archive._ensure_durable_directory(config.custody_root, custody)
        feed_archive._ensure_durable_directory(config.runtime_root, primary)
    except (OSError, ValueError, feed_archive.ArchiveCollisionError) as exc:
        _fatal("batch transaction directory is not durable", cause=exc)
    return custody, primary


def _validate_transaction_temp(
    directory_name: str,
    final_name: str,
    raw: bytes,
) -> None:
    match = _BATCH_DIRECTORY_NAME.fullmatch(directory_name)
    if match is None:
        _fatal("batch transaction directory name is not canonical")
    parsed = _canonical_object(raw, field="batch publication temp")
    if final_name == "prepare.json":
        if _sha256(raw) != match.group(2) or parsed.get("kind") != "v34_batch_prepare":
            _fatal("batch PREPARE temp differs from its directory")
        return
    commit_match = _BATCH_COMMIT_NAME.fullmatch(final_name)
    if (
        commit_match is None
        or _sha256(raw) != commit_match.group(1)
        or parsed.get("kind") != "v34_batch_commit"
    ):
        _fatal("batch COMMIT temp differs from its filename")


def _mirror_batch_directory_locked(
    config: head_ledger.HeadLedgerConfig,
    *,
    name: str,
) -> None:
    custody = _batches_root(config.custody_control_root) / name
    primary = _batches_root(config.primary_control_root) / name
    if not custody.is_dir():
        _fatal("custody batch transaction is not a directory")
    if not primary.exists():
        try:
            feed_archive._ensure_durable_directory(config.runtime_root, primary)
        except (OSError, ValueError, feed_archive.ArchiveCollisionError) as exc:
            _fatal("batch transaction mirror directory recovery failed", cause=exc)
    if not primary.is_dir():
        _fatal("primary batch transaction is not a directory")

    def validate_custody(final_name: str, raw: bytes) -> None:
        _validate_transaction_temp(name, final_name, raw)

    head_ledger._recover_directory_prelink_temps(custody, validate=validate_custody)

    def validate_primary(final_name: str, raw: bytes) -> None:
        validate_custody(final_name, raw)
        custody_path = custody / final_name
        if not custody_path.is_file() or head_ledger._read_exact(custody_path) != raw:
            _fatal("primary batch temp has no custody authority")

    head_ledger._recover_directory_prelink_temps(primary, validate=validate_primary)
    custody_files = head_ledger._directory_names(custody)
    primary_files = head_ledger._directory_names(primary)
    commits = {name for name in custody_files if _BATCH_COMMIT_NAME.fullmatch(name)}
    if len(commits) > 1 or custody_files != {"prepare.json"} | commits:
        _fatal("custody batch transaction file inventory differs")
    if primary_files - custody_files:
        _fatal("primary batch record exists without custody authority")
    for missing in sorted(custody_files - primary_files):
        head_ledger._write_exact(primary / missing, head_ledger._read_exact(custody / missing))
    if head_ledger._directory_names(primary) != custody_files:
        _fatal("batch transaction mirror recovery did not converge")
    for filename in custody_files:
        if head_ledger._read_exact(custody / filename) != head_ledger._read_exact(
            primary / filename
        ):
            _fatal("batch transaction differs across custody roots")


def _revalidate_source_binding(
    config: head_ledger.HeadLedgerConfig,
    binding: ArchiveSourceBinding,
) -> ArchivedFeedPair:
    directory = Path(binding.archive_path)
    try:
        feed_archive._assert_no_redirecting_components(
            config.custody_root,
            directory,
        )
        summary_bytes, feed_receipt_bytes, archive_receipt_bytes = (
            feed_archive._read_bounded_archive_members(directory)
        )
        archived = ArchivedFeedPair(
            generation_id=binding.generation_id,
            summary_bytes=summary_bytes,
            feed_receipt_bytes=feed_receipt_bytes,
            archive_receipt_bytes=archive_receipt_bytes,
        )
        if (
            archived.summary_sha256 != binding.summary_sha256
            or archived.feed_receipt_sha256 != binding.feed_receipt_sha256
            or archived.archive_receipt_sha256 != binding.archive_receipt_sha256
        ):
            _fatal("batch source archive differs from its PREPARE binding")
        return feed_archive.revalidate_archived_feed_pair(
            archived,
            feed_anchor=config.feed_anchor,
            queue_anchor=config.queue_anchor,
            trusted_root=config.custody_root,
        )
    except (OSError, TypeError, ValueError, feed_archive.ArchiveCollisionError) as exc:
        _fatal("batch source archive cannot be revalidated from custody", cause=exc)


def _verify_source_archive_inventory(
    config: head_ledger.HeadLedgerConfig,
    *,
    referenced_directories: set[Path],
) -> tuple[tuple[str, ...], int]:
    root = _source_archive_root(config)
    actual_directories: dict[Path, int] = {}
    for generation_directory in tuple(root.iterdir()):
        try:
            feed_archive._assert_no_redirecting_components(
                config.custody_root,
                generation_directory,
            )
        except (OSError, ValueError, feed_archive.ArchiveCollisionError) as exc:
            _fatal("source archive generation ancestry differs", cause=exc)
        if not generation_directory.is_dir():
            _fatal("source archive root contains a non-directory member")
        for archive_directory in tuple(generation_directory.iterdir()):
            try:
                feed_archive._assert_no_redirecting_components(
                    config.custody_root,
                    archive_directory,
                )
            except (OSError, ValueError, feed_archive.ArchiveCollisionError) as exc:
                _fatal("source archive content ancestry differs", cause=exc)
            if not archive_directory.is_dir():
                _fatal("source archive generation contains a non-directory member")
            try:
                summary_bytes, feed_receipt_bytes, archive_receipt_bytes = (
                    feed_archive._read_bounded_archive_members(archive_directory)
                )
                archived = ArchivedFeedPair(
                    generation_id=generation_directory.name,
                    summary_bytes=summary_bytes,
                    feed_receipt_bytes=feed_receipt_bytes,
                    archive_receipt_bytes=archive_receipt_bytes,
                )
                validated = feed_archive.revalidate_archived_feed_pair(
                    archived,
                    feed_anchor=config.feed_anchor,
                    queue_anchor=config.queue_anchor,
                    trusted_root=config.custody_root,
                )
                if archive_directory.name != validated.summary_sha256:
                    _fatal("source archive content-addressed directory differs")
                source_bytes = (
                    len(validated.summary_bytes)
                    + len(validated.feed_receipt_bytes)
                    + len(validated.archive_receipt_bytes)
                )
                storage_preflight.require_cycle_payload(
                    source_persisted_bytes=source_bytes
                )
            except (
                OSError,
                TypeError,
                ValueError,
                feed_archive.ArchiveCollisionError,
                storage_preflight.StoragePreflightError,
            ) as exc:
                _fatal("source archive inventory member is invalid", cause=exc)
            actual_directories[archive_directory.resolve(strict=True)] = source_bytes
    resolved_references = {
        directory.resolve(strict=True) for directory in referenced_directories
    }
    if not resolved_references <= set(actual_directories):
        _fatal("batch chain references a source outside the exact archive inventory")
    unreferenced = tuple(
        sorted(str(path) for path in set(actual_directories) - resolved_references)
    )
    return unreferenced, sum(actual_directories[Path(path)] for path in unreferenced)


def _scan_chain_locked(
    config: head_ledger.HeadLedgerConfig,
    *,
    manifest_sha256: str,
    registrations: Mapping[int, head_ledger.GameRegistration],
    committed_callback: (
        Callable[
            [
                BatchPrepare,
                str,
                tuple[tuple[int, feed_lineage.FeedPortableHead], ...],
            ],
            None,
        ]
        | None
    ) = None,
) -> BatchChainState:
    _ensure_batch_layout(config)
    _verify_control_root_inventory(config)
    custody_root = _batches_root(config.custody_control_root)
    primary_root = _batches_root(config.primary_control_root)
    custody_names = head_ledger._directory_names(custody_root)
    primary_names = head_ledger._directory_names(primary_root)
    if any(_BATCH_DIRECTORY_NAME.fullmatch(name) is None for name in custody_names):
        _fatal("custody batch inventory contains an unknown entry")
    if any(_BATCH_DIRECTORY_NAME.fullmatch(name) is None for name in primary_names):
        _fatal("primary batch inventory contains an unknown entry")
    for name in sorted(custody_names | primary_names):
        custody = custody_root / name
        primary = primary_root / name
        custody_empty = custody.is_dir() and not any(custody.iterdir())
        primary_empty = primary.is_dir() and not any(primary.iterdir())
        if not custody.exists() and primary_empty:
            _fatal("primary empty batch transaction has no custody authority")
        if custody_empty and (not primary.exists() or primary_empty):
            if primary_empty:
                head_ledger._remove_empty_transaction_container(
                    primary,
                    trusted_root=config.runtime_root,
                )
            head_ledger._remove_empty_transaction_container(
                custody,
                trusted_root=config.custody_root,
            )
    custody_names = head_ledger._directory_names(custody_root)
    primary_names = head_ledger._directory_names(primary_root)
    if primary_names - custody_names:
        _fatal("primary batch transaction exists without custody authority")
    for name in sorted(custody_names - primary_names):
        _mirror_batch_directory_locked(config, name=name)
    if head_ledger._directory_names(primary_root) != custody_names:
        _fatal("batch directory mirrors did not converge")
    heads = {
        game_pk: registration.initial_head
        for game_pk, registration in registrations.items()
    }
    prior_commit_sha256: str | None = None
    open_prepare: BatchPrepare | None = None
    referenced_source_directories: set[Path] = set()
    expected_sequence = 1
    ordered_names = sorted(custody_names)
    for position, name in enumerate(ordered_names):
        match = _BATCH_DIRECTORY_NAME.fullmatch(name)
        assert match is not None
        sequence = int(match.group(1))
        if sequence != expected_sequence:
            _fatal("batch transaction sequence has a gap or duplicate")
        _mirror_batch_directory_locked(config, name=name)
        transaction = custody_root / name
        prepare_raw = head_ledger._read_exact(transaction / "prepare.json")
        if _sha256(prepare_raw) != match.group(2):
            _fatal("batch PREPARE directory hash differs")
        prepare = _parse_prepare(
            prepare_raw,
            config=config,
            manifest_sha256=manifest_sha256,
            registrations=registrations,
        )
        _revalidate_source_binding(config, prepare.source_binding)
        referenced_source_directories.add(Path(prepare.source_binding.archive_path))
        if prepare.batch_sequence != sequence:
            _fatal("batch PREPARE directory sequence differs")
        if prepare.prior_commit_sha256 != prior_commit_sha256:
            _fatal("batch PREPARE prior commit differs from the chain")
        expected_heads = _result_heads(heads, prepare)
        files = head_ledger._directory_names(transaction)
        commits = sorted(name for name in files if _BATCH_COMMIT_NAME.fullmatch(name))
        if not commits:
            if position != len(ordered_names) - 1 or open_prepare is not None:
                _fatal("open batch PREPARE is not the sole chain tail")
            open_prepare = prepare
        else:
            commit_name = commits[0]
            commit_match = _BATCH_COMMIT_NAME.fullmatch(commit_name)
            assert commit_match is not None
            commit_raw = head_ledger._read_exact(transaction / commit_name)
            commit_sha256 = _parse_commit(
                commit_raw,
                config=config,
                manifest_sha256=manifest_sha256,
                registrations=registrations,
                prepare=prepare,
                expected_heads=expected_heads,
            )
            if commit_sha256 != commit_match.group(1):
                _fatal("batch COMMIT filename hash differs")
            prior_commit_sha256 = commit_sha256
            heads = dict(expected_heads)
            if committed_callback is not None:
                committed_callback(prepare, commit_sha256, expected_heads)
        expected_sequence += 1
    unreferenced_source_paths, unreferenced_source_bytes = (
        _verify_source_archive_inventory(
            config,
            referenced_directories=referenced_source_directories,
        )
    )
    return BatchChainState(
        heads=tuple(sorted(heads.items())),
        prior_commit_sha256=prior_commit_sha256,
        next_batch_sequence=expected_sequence,
        open_prepare=open_prepare,
        unreferenced_source_paths=unreferenced_source_paths,
        unreferenced_source_bytes=unreferenced_source_bytes,
    )


def open_batch_session(
    config: head_ledger.HeadLedgerConfig,
    *,
    _restoring_fresh_runtime: bool = False,
) -> BatchLedgerSession:
    """Perform the full startup audit and retain only verified incremental heads."""

    with head_ledger._control_locks(config):
        if _restoring_fresh_runtime and config.manifest_runtime_root is None:
            _fatal("fresh-runtime restore mode requires a restored config")
        _ensure_batch_layout(config)
        custody_batch_count, missing_primary_bytes = _read_only_startup_storage_inputs(
            config
        )
        if custody_batch_count > storage_preflight.MAX_CYCLES:
            _fatal("batch session startup exceeds the frozen cycle horizon")
        try:
            storage_preflight.require_storage_preflight(
                runtime_root=config.runtime_root,
                custody_root=config.custody_root,
                runtime_completed_cycles=custody_batch_count,
                custody_completed_cycles=custody_batch_count,
                outstanding_rotation_bytes=0,
                additional_runtime_bytes=missing_primary_bytes,
                additional_custody_bytes=0,
            )
        except storage_preflight.StoragePreflightError as exc:
            _fatal("batch session startup storage preflight failed", cause=exc)
        manifest_sha256 = head_ledger._verify_manifest_locked(config)
        registrations = head_ledger._scan_registrations_locked(
            config,
            manifest_sha256=manifest_sha256,
        )
        state = _scan_chain_locked(
            config,
            manifest_sha256=manifest_sha256,
            registrations=registrations,
        )
        if state.open_prepare is not None:
            _fatal("batch session cannot open with an unresolved PREPARE")
        snapshots = (
            ()
            if _restoring_fresh_runtime
            else _replay_all_heads(config, state)
        )
        names = tuple(
            sorted(
                head_ledger._directory_names(
                    _batches_root(config.custody_control_root)
                )
            )
        )
        try:
            storage_preflight.require_storage_preflight(
                runtime_root=config.runtime_root,
                custody_root=config.custody_root,
                runtime_completed_cycles=len(names),
                custody_completed_cycles=len(names),
                outstanding_rotation_bytes=sum(
                    head.active_file_size for _, head in state.heads
                ),
                additional_runtime_bytes=0,
                additional_custody_bytes=state.unreferenced_source_bytes,
            )
        except storage_preflight.StoragePreflightError as exc:
            _fatal("batch session storage preflight failed", cause=exc)
        try:
            watched_roots: tuple[Path, ...] = (
                _batches_root(config.custody_control_root),
                _batches_root(config.primary_control_root),
                _source_archive_root(config),
            )
            if not _restoring_fresh_runtime:
                watched_roots = (*watched_roots, config.runtime_root / "games")
            mutation_guard = batch_mutation_guard.BatchMutationGuard(watched_roots)
        except batch_mutation_guard.BatchMutationGuardError as exc:
            _fatal("batch session mutation guard did not open", cause=exc)
        try:
            mutation_guard.require_quiet()
            audited_manifest_sha256 = head_ledger._verify_manifest_locked(config)
            audited_registrations = head_ledger._scan_registrations_locked(
                config,
                manifest_sha256=audited_manifest_sha256,
            )
            audited_state = _scan_chain_locked(
                config,
                manifest_sha256=audited_manifest_sha256,
                registrations=audited_registrations,
            )
            audited_snapshots = (
                ()
                if _restoring_fresh_runtime
                else _replay_all_heads(config, audited_state)
            )
            mutation_guard.require_quiet()
        except batch_mutation_guard.BatchMutationGuardError as exc:
            mutation_guard.close()
            _fatal("batch session startup watcher observed a mutation", cause=exc)
        if (
            audited_manifest_sha256 != manifest_sha256
            or audited_registrations != registrations
            or audited_state != state
            or audited_snapshots != snapshots
        ):
            mutation_guard.close()
            _fatal("batch session startup audits differ")
        retained_snapshots = tuple(
            (game_pk, feed_lineage._persist_snapshot_history(snapshot))
            for game_pk, snapshot in audited_snapshots
        )
        hot_integrities = tuple(
            (
                game_pk,
                feed_lineage._open_hot_integrity(
                    config.runtime_root
                    / registrations[game_pk].lineage_relative_path,
                    snapshot,
                    game_pk=game_pk,
                    trusted_root=config.runtime_root,
                ),
            )
            for game_pk, snapshot in retained_snapshots
        )
        try:
            mutation_guard.require_quiet()
        except batch_mutation_guard.BatchMutationGuardError as exc:
            mutation_guard.close()
            _fatal("batch session hot integrity capture observed a mutation", cause=exc)
        return BatchLedgerSession(
            config=config,
            manifest_sha256=manifest_sha256,
            registrations=tuple(sorted(registrations.items())),
            state=state,
            batch_count=len(names),
            latest_batch_name=names[-1] if names else None,
            mutation_guard=mutation_guard,
            snapshots=retained_snapshots,
            hot_integrities=hot_integrities,
        )


def _validate_session_locked(
    session: BatchLedgerSession,
) -> tuple[
    head_ledger.HeadLedgerConfig,
    dict[int, head_ledger.GameRegistration],
    BatchChainState,
]:
    if not isinstance(session, BatchLedgerSession):
        _fatal("append requires a verified BatchLedgerSession")
    try:
        session.mutation_guard.check_and_clear()
    except batch_mutation_guard.BatchMutationGuardError as exc:
        _fatal("batch session observed an unexpected custody mutation", cause=exc)
    config = session.config
    _ensure_batch_layout(config)
    manifest_sha256 = head_ledger._verify_manifest_locked(config)
    if manifest_sha256 != session.manifest_sha256:
        _fatal("batch session registry manifest changed")
    registrations = head_ledger._scan_registrations_locked(
        config,
        manifest_sha256=manifest_sha256,
    )
    if tuple(sorted(registrations.items())) != session.registrations:
        _fatal("batch session game registry changed")
    _verify_control_root_inventory(config)
    state = session.state
    if state.open_prepare is not None:
        _fatal("batch session retained an unresolved PREPARE")
    if state.next_batch_sequence != session.batch_count + 1:
        _fatal("batch session retained sequence count differs")
    if session.latest_batch_name is not None:
        latest_name = session.latest_batch_name
        latest_match = _BATCH_DIRECTORY_NAME.fullmatch(latest_name)
        assert latest_match is not None
        if int(latest_match.group(1)) != state.next_batch_sequence - 1:
            _fatal("batch session latest sequence differs")
        _mirror_batch_directory_locked(config, name=latest_name)
        transaction = _batches_root(config.custody_control_root) / latest_name
        prepare_raw = head_ledger._read_exact(transaction / "prepare.json")
        if _sha256(prepare_raw) != latest_match.group(2):
            _fatal("batch session latest PREPARE differs")
        commit_files = sorted(transaction.glob("commit-*.json"))
        if len(commit_files) != 1:
            _fatal("batch session latest COMMIT inventory differs")
        if _sha256(head_ledger._read_exact(commit_files[0])) != state.prior_commit_sha256:
            _fatal("batch session latest COMMIT head differs")
    elif state.next_batch_sequence != 1 or state.prior_commit_sha256 is not None:
        _fatal("empty batch session state differs")
    return config, registrations, state


def _publish_prepare_locked(
    config: head_ledger.HeadLedgerConfig,
    *,
    manifest_sha256: str,
    registrations: Mapping[int, head_ledger.GameRegistration],
    raw: bytes,
) -> BatchPrepare:
    prepare = _parse_prepare(
        raw,
        config=config,
        manifest_sha256=manifest_sha256,
        registrations=registrations,
    )
    custody, primary = _ensure_batch_transaction_directories(
        config,
        sequence=prepare.batch_sequence,
        prepare_sha256=prepare.record_sha256,
    )
    head_ledger._write_exact(custody / "prepare.json", raw)
    head_ledger._write_exact(primary / "prepare.json", raw)
    if (
        head_ledger._read_exact(custody / "prepare.json") != raw
        or head_ledger._read_exact(primary / "prepare.json") != raw
    ):
        _fatal("batch PREPARE differs across custody roots")
    return prepare


def _publish_commit_locked(
    config: head_ledger.HeadLedgerConfig,
    *,
    manifest_sha256: str,
    registrations: Mapping[int, head_ledger.GameRegistration],
    prepare: BatchPrepare,
    committed_heads: tuple[tuple[int, feed_lineage.FeedPortableHead], ...],
) -> str:
    raw = _commit_record(
        config,
        manifest_sha256=manifest_sha256,
        prepare=prepare,
        committed_heads=committed_heads,
    )
    try:
        storage_preflight.require_cycle_payload(commit_bytes=len(raw))
    except storage_preflight.StoragePreflightError as exc:
        _fatal("batch COMMIT exceeds the production payload cap", cause=exc)
    digest = _sha256(raw)
    custody = _batch_directory(
        config.custody_control_root,
        sequence=prepare.batch_sequence,
        prepare_sha256=prepare.record_sha256,
    )
    primary = _batch_directory(
        config.primary_control_root,
        sequence=prepare.batch_sequence,
        prepare_sha256=prepare.record_sha256,
    )
    filename = f"commit-{digest}.json"
    head_ledger._write_exact(custody / filename, raw)
    head_ledger._write_exact(primary / filename, raw)
    if (
        head_ledger._read_exact(custody / filename) != raw
        or head_ledger._read_exact(primary / filename) != raw
    ):
        _fatal("batch COMMIT differs across custody roots")
    _parse_commit(
        raw,
        config=config,
        manifest_sha256=manifest_sha256,
        registrations=registrations,
        prepare=prepare,
        expected_heads=committed_heads,
    )
    return digest


def _verify_committed_publication_locked(
    config: head_ledger.HeadLedgerConfig,
    *,
    manifest_sha256: str,
    registrations: Mapping[int, head_ledger.GameRegistration],
    prepare: BatchPrepare,
    committed_heads: tuple[tuple[int, feed_lineage.FeedPortableHead], ...],
    commit_sha256: str,
) -> None:
    """Reread the exact closed transaction after the watcher expectation ends."""

    transaction_name = (
        f"{prepare.batch_sequence:0{BATCH_SEQUENCE_WIDTH}d}-{prepare.record_sha256}"
    )
    expected_commit_raw = _commit_record(
        config,
        manifest_sha256=manifest_sha256,
        prepare=prepare,
        committed_heads=committed_heads,
    )
    if _sha256(expected_commit_raw) != commit_sha256:
        _fatal("post-settle batch COMMIT digest differs")
    commit_name = f"commit-{commit_sha256}.json"
    expected_inventory = {"prepare.json", commit_name}
    observed: list[tuple[bytes, bytes]] = []
    for control_root in (
        config.custody_control_root,
        config.primary_control_root,
    ):
        transaction = _batches_root(control_root) / transaction_name
        if head_ledger._directory_names(transaction) != expected_inventory:
            _fatal("post-settle batch transaction inventory differs")
        prepare_raw = head_ledger._read_exact(transaction / "prepare.json")
        commit_raw = head_ledger._read_exact(transaction / commit_name)
        if prepare_raw != prepare.raw or commit_raw != expected_commit_raw:
            _fatal("post-settle batch transaction bytes differ")
        observed.append((prepare_raw, commit_raw))
    if observed[0] != observed[1]:
        _fatal("post-settle batch transaction mirrors differ")
    parsed_prepare = _parse_prepare(
        observed[0][0],
        config=config,
        manifest_sha256=manifest_sha256,
        registrations=registrations,
    )
    if parsed_prepare != prepare:
        _fatal("post-settle batch PREPARE semantics differ")
    if (
        _parse_commit(
            observed[0][1],
            config=config,
            manifest_sha256=manifest_sha256,
            registrations=registrations,
            prepare=prepare,
            expected_heads=committed_heads,
        )
        != commit_sha256
    ):
        _fatal("post-settle batch COMMIT semantics differ")
    _revalidate_source_binding(config, prepare.source_binding)


def append_committed_batch(
    session: BatchLedgerSession,
    requests: tuple[BatchTransitionRequest, ...],
    *,
    source_pair: feed_archive.CoherentFeedPair,
    fault_hook: Callable[[str], None] | None = None,
) -> CommittedFeedBatch:
    """Commit every successful game transition with two custody publications."""

    if type(requests) is not tuple or not requests or len(requests) > MAX_BATCH_OPERATIONS:
        _fatal("batch requests must be a bounded nonempty tuple")
    for request in requests:
        if (
            not isinstance(request, BatchTransitionRequest)
            or not isinstance(request.transition, lifecycle.FeedTransition)
            or not isinstance(
                request.expected_snapshot,
                feed_lineage.FeedLineageSnapshot,
            )
        ):
            _fatal("batch request has the wrong type")
        head_ledger._utc(request.recorded_at, field="batch_request.recorded_at")
    if len({request.recorded_at for request in requests}) != 1:
        _fatal("batch requests do not share one coherent source generation")
    if not isinstance(source_pair, feed_archive.CoherentFeedPair):
        _fatal("batch source pair has the wrong type")
    ordered_requests = tuple(
        sorted(requests, key=lambda item: item.transition.state.game_pk)
    )
    game_pks = [request.transition.state.game_pk for request in ordered_requests]
    if len(game_pks) != len(set(game_pks)):
        _fatal("batch requests contain a duplicate game")
    if not isinstance(session, BatchLedgerSession):
        _fatal("production batch append requires a verified session")
    config = session.config
    with head_ledger._control_locks(config):
        config, registrations, state = _validate_session_locked(session)
        if session.batch_count >= storage_preflight.MAX_CYCLES:
            _fatal("batch session exhausted the frozen 24-hour cycle horizon")
        try:
            storage_preflight.require_storage_preflight(
                runtime_root=config.runtime_root,
                custody_root=config.custody_root,
                runtime_completed_cycles=session.batch_count,
                custody_completed_cycles=session.batch_count,
                outstanding_rotation_bytes=sum(
                    head.active_file_size for _, head in state.heads
                ),
                additional_runtime_bytes=0,
                additional_custody_bytes=state.unreferenced_source_bytes,
            )
        except storage_preflight.StoragePreflightError as exc:
            _fatal("batch append storage preflight failed", cause=exc)
        source_directory = (
            _source_archive_root(config)
            / source_pair.generation_id
            / source_pair.summary_sha256
        )
        if (
            len(source_pair.summary_bytes) + len(source_pair.feed_receipt_bytes)
            > storage_preflight.MAX_SOURCE_PERSISTED_BYTES
        ):
            _fatal("batch source pair exceeds the production payload cap")
        try:
            planned_source_archive = feed_archive.plan_archived_feed_pair(
                source_pair,
                feed_anchor=config.feed_anchor,
                queue_anchor=config.queue_anchor,
                archive_root=_source_archive_root(config),
                trusted_root=config.custody_root,
                archived_at=ordered_requests[0].recorded_at,
            )
        except (
            OSError,
            TypeError,
            ValueError,
            feed_archive.ArchiveCollisionError,
        ) as exc:
            _fatal("batch source archive cannot be planned exactly", cause=exc)
        try:
            storage_preflight.require_cycle_payload(
                source_persisted_bytes=(
                    len(planned_source_archive.summary_bytes)
                    + len(planned_source_archive.feed_receipt_bytes)
                    + len(planned_source_archive.archive_receipt_bytes)
                )
            )
        except storage_preflight.StoragePreflightError as exc:
            _fatal("batch source pair exceeds the production payload cap", cause=exc)
        manifest_sha256 = session.manifest_sha256
        request_by_game = {
            request.transition.state.game_pk: request
            for request in ordered_requests
        }
        retained_snapshots = dict(session.snapshots)
        hot_integrities = dict(session.hot_integrities)
        inputs: list[feed_lineage.FeedBatchInput] = []
        for game_pk, request in sorted(request_by_game.items()):
            registration = registrations.get(game_pk)
            if registration is None:
                _fatal("batch request game is not registered")
            retained = feed_lineage.portable_head_from_snapshot(
                request.expected_snapshot,
                game_pk=game_pk,
            )
            if retained != state.head_for(game_pk):
                _fatal("batch caller snapshot differs from the committed head")
            if retained_snapshots.get(game_pk) != request.expected_snapshot:
                _fatal("batch caller snapshot differs from the live hot session")
            hot_integrity = hot_integrities.get(game_pk)
            if hot_integrity is None:
                _fatal("batch live hot integrity state is missing")
            inputs.append(
                feed_lineage.FeedBatchInput(
                    path=config.runtime_root / registration.lineage_relative_path,
                    transition=request.transition,
                    recorded_at=request.recorded_at,
                    expected_snapshot=request.expected_snapshot,
                    hot_integrity=hot_integrity,
                )
            )
        prepared: list[BatchPrepare] = []
        committed: list[str] = []
        verified_source_archives: list[ArchivedFeedPair] = []

        def publish_prepare(batch_plan: feed_lineage.FeedBatchPlan) -> None:
            try:
                storage_preflight.require_cycle_payload(
                    lineage_bytes=sum(
                        len(plan.event_bytes) + 1 for plan in batch_plan.plans
                    ),
                    rotation_replica_bytes=sum(
                        receipt.file_size
                        for plan in batch_plan.plans
                        if (receipt := plan.expected_new_sealed_receipt) is not None
                    ),
                )
            except storage_preflight.StoragePreflightError as exc:
                _fatal("batch lineage exceeds the production payload cap", cause=exc)
            operations = tuple(
                _operation_record(
                    config,
                    manifest_sha256=manifest_sha256,
                    registration=registrations[plan.game_pk],
                    plan=plan,
                    prior_batch_commit_sha256=state.prior_commit_sha256,
                    request=request_by_game[plan.game_pk],
                    source_archive=planned_source_archive,
                )
                for plan in batch_plan.plans
            )
            raw = _prepare_record(
                config,
                manifest_sha256=manifest_sha256,
                sequence=state.next_batch_sequence,
                prior_commit_sha256=state.prior_commit_sha256,
                operations=operations,
            )
            if len(raw) > MAX_BATCH_RECORD_BYTES:
                _fatal("batch PREPARE exceeds the batch record byte limit")
            try:
                storage_preflight.require_cycle_payload(prepare_bytes=len(raw))
            except storage_preflight.StoragePreflightError as exc:
                _fatal("batch PREPARE exceeds the production payload cap", cause=exc)
            prepared_candidate = _parse_prepare(
                raw,
                config=config,
                manifest_sha256=manifest_sha256,
                registrations=registrations,
            )
            candidate_heads = _result_heads(dict(state.heads), prepared_candidate)
            candidate_commit_raw = _commit_record(
                config,
                manifest_sha256=manifest_sha256,
                prepare=prepared_candidate,
                committed_heads=candidate_heads,
            )
            try:
                storage_preflight.require_cycle_payload(
                    commit_bytes=len(candidate_commit_raw)
                )
            except storage_preflight.StoragePreflightError as exc:
                _fatal("batch COMMIT exceeds the production payload cap", cause=exc)
            pending_name = (
                f"{state.next_batch_sequence:0{BATCH_SEQUENCE_WIDTH}d}-"
                f"{_sha256(raw)}"
            )
            try:
                session.mutation_guard.expect((source_directory,))
                verified_source_archive = (
                    feed_archive._archive_coherent_feed_pair_at_root(
                        source_pair,
                        feed_anchor=config.feed_anchor,
                        queue_anchor=config.queue_anchor,
                        archive_root=_source_archive_root(config),
                        trusted_root=config.custody_root,
                        recorded_at=lambda: ordered_requests[0].recorded_at,
                        planned_archive=planned_source_archive,
                    )
                )
                session.mutation_guard.settle_expected()
                verified_source_archive = feed_archive.revalidate_archived_feed_pair(
                    verified_source_archive,
                    feed_anchor=config.feed_anchor,
                    queue_anchor=config.queue_anchor,
                    trusted_root=config.custody_root,
                )
                if verified_source_archive != planned_source_archive:
                    _fatal("published source archive differs from its exact plan")
                verified_source_archives.append(verified_source_archive)
                if fault_hook is not None:
                    fault_hook("after_source_archive")
                lineage_paths: set[Path] = set()
                for plan in batch_plan.plans:
                    for relative_path in (
                        plan.before_head.active_lineage_path,
                        plan.expected_post_head.active_lineage_path,
                    ):
                        if relative_path is not None:
                            lineage_paths.add(config.runtime_root / relative_path)
                    receipt = plan.expected_new_sealed_receipt
                    if receipt is not None:
                        lineage_paths.add(config.runtime_root / receipt.archive_path)
                session.mutation_guard.expect(
                    (
                        _batches_root(config.custody_control_root) / pending_name,
                        _batches_root(config.primary_control_root) / pending_name,
                        *tuple(sorted(lineage_paths, key=str)),
                    )
                )
            except (
                OSError,
                TypeError,
                ValueError,
                batch_mutation_guard.BatchMutationGuardError,
                feed_archive.ArchiveCollisionError,
            ) as exc:
                _fatal("batch mutation guard rejected PREPARE", cause=exc)
            prepared.append(
                _publish_prepare_locked(
                    config,
                    manifest_sha256=manifest_sha256,
                    registrations=registrations,
                    raw=raw,
                )
            )
            if prepared[0] != prepared_candidate:
                _fatal("published batch PREPARE differs from its sized candidate")
            if prepared[0].feed_plan.plans != batch_plan.plans:
                _fatal("published batch PREPARE differs from the frozen plans")
            if fault_hook is not None:
                fault_hook("after_prepare")

        def publish_commit(
            batch_plan: feed_lineage.FeedBatchPlan,
            snapshots: tuple[feed_lineage.FeedLineageSnapshot, ...],
            reverify: Callable[[], None],
        ) -> None:
            if len(prepared) != 1 or prepared[0].feed_plan.plans != batch_plan.plans:
                _fatal("batch append differs from its sole PREPARE")
            if fault_hook is not None:
                fault_hook("after_lineage_batch")
            reverify()
            try:
                if len(verified_source_archives) != 1:
                    _fatal("batch source archive was not published exactly once")
                feed_archive.revalidate_archived_feed_pair(
                    verified_source_archives[0],
                    feed_anchor=config.feed_anchor,
                    queue_anchor=config.queue_anchor,
                    trusted_root=config.custody_root,
                )
            except (
                OSError,
                TypeError,
                ValueError,
                feed_archive.ArchiveCollisionError,
            ) as exc:
                _fatal("batch source archive changed before COMMIT", cause=exc)
            committed_heads = _result_heads(dict(state.heads), prepared[0])
            snapshot_heads = {
                plan.game_pk: feed_lineage.portable_head_from_snapshot(
                    snapshot,
                    game_pk=plan.game_pk,
                )
                for plan, snapshot in zip(
                    batch_plan.plans,
                    snapshots,
                    strict=True,
                )
            }
            if any(
                snapshot_heads.get(plan.game_pk) != plan.expected_post_head
                for plan in batch_plan.plans
            ):
                _fatal("batch lineage results differ from the PREPARE")
            committed.append(
                _publish_commit_locked(
                    config,
                    manifest_sha256=manifest_sha256,
                    registrations=registrations,
                    prepare=prepared[0],
                    committed_heads=committed_heads,
                )
            )

        def operation_applied(operation_index: int) -> None:
            if fault_hook is not None:
                fault_hook(f"after_lineage_operation_{operation_index}")

        try:
            snapshots = feed_lineage._apply_feed_transition_batch(
                tuple(inputs),
                feed_anchor=config.feed_anchor,
                before_batch=publish_prepare,
                after_batch=publish_commit,
                operation_applied=operation_applied,
                trusted_root=config.runtime_root,
            )
        except feed_lineage.FeedLineageFatalError as exc:
            _fatal("feed lineage batch failed", cause=exc)
        if len(prepared) != 1 or len(committed) != 1:
            _fatal("batch did not publish exactly one PREPARE and COMMIT")
        committed_heads = _result_heads(dict(state.heads), prepared[0])
        new_name = (
            f"{prepared[0].batch_sequence:0{BATCH_SEQUENCE_WIDTH}d}-"
            f"{prepared[0].record_sha256}"
        )
        _mirror_batch_directory_locked(config, name=new_name)
        try:
            session.mutation_guard.settle_expected()
        except batch_mutation_guard.BatchMutationGuardError as exc:
            _fatal("batch mutation guard rejected committed custody", cause=exc)
        for plan, snapshot in zip(
            prepared[0].feed_plan.plans,
            snapshots,
            strict=True,
        ):
            hot_integrity = hot_integrities[plan.game_pk]
            feed_lineage._release_pending_sealed_descriptors(
                config.runtime_root
                / registrations[plan.game_pk].lineage_relative_path,
                snapshot,
                hot_integrity,
                game_pk=plan.game_pk,
                trusted_root=config.runtime_root,
                require_pending=plan.should_rotate,
            )
        for plan, snapshot in zip(
            prepared[0].feed_plan.plans,
            snapshots,
            strict=True,
        ):
            hot_integrity = hot_integrities[plan.game_pk]
            feed_lineage._verify_hot_integrity(
                config.runtime_root
                / registrations[plan.game_pk].lineage_relative_path,
                snapshot,
                hot_integrity,
                game_pk=plan.game_pk,
                trusted_root=config.runtime_root,
            )
        _verify_committed_publication_locked(
            config,
            manifest_sha256=manifest_sha256,
            registrations=registrations,
            prepare=prepared[0],
            committed_heads=committed_heads,
            commit_sha256=committed[0],
        )
        remaining_unreferenced_sources = set(state.unreferenced_source_paths)
        resolved_source_directory = str(source_directory.resolve(strict=True))
        unreferenced_source_bytes = state.unreferenced_source_bytes
        if resolved_source_directory in remaining_unreferenced_sources:
            remaining_unreferenced_sources.remove(resolved_source_directory)
            unreferenced_source_bytes -= (
                len(verified_source_archives[0].summary_bytes)
                + len(verified_source_archives[0].feed_receipt_bytes)
                + len(verified_source_archives[0].archive_receipt_bytes)
            )
        if unreferenced_source_bytes < 0:
            _fatal("unreferenced source archive accounting underflowed")
        session.state = BatchChainState(
            heads=committed_heads,
            prior_commit_sha256=committed[0],
            next_batch_sequence=state.next_batch_sequence + 1,
            open_prepare=None,
            unreferenced_source_paths=tuple(sorted(remaining_unreferenced_sources)),
            unreferenced_source_bytes=unreferenced_source_bytes,
        )
        session.batch_count += 1
        session.latest_batch_name = new_name
        updated_snapshots = dict(retained_snapshots)
        updated_snapshots.update(
            (plan.game_pk, snapshot)
            for plan, snapshot in zip(
                prepared[0].feed_plan.plans,
                snapshots,
                strict=True,
            )
        )
        session.snapshots = tuple(sorted(updated_snapshots.items()))
        result = tuple(
            (plan.game_pk, snapshot)
            for plan, snapshot in zip(
                prepared[0].feed_plan.plans,
                snapshots,
                strict=True,
            )
        )
        return CommittedFeedBatch(
            snapshots=result,
            prepare_sha256=prepared[0].record_sha256,
            commit_sha256=committed[0],
        )


def recover_batch_chain(
    config: head_ledger.HeadLedgerConfig,
) -> tuple[tuple[int, feed_lineage.FeedLineageSnapshot], ...]:
    """Recover the sole open all-game PREPARE or verify committed heads."""

    with head_ledger._control_locks(config):
        _ensure_batch_layout(config)
        custody_batch_count, missing_primary_bytes = _read_only_startup_storage_inputs(
            config
        )
        if custody_batch_count > storage_preflight.MAX_CYCLES:
            _fatal("batch recovery exceeds the frozen cycle horizon")
        try:
            storage_preflight.require_storage_preflight(
                runtime_root=config.runtime_root,
                custody_root=config.custody_root,
                runtime_completed_cycles=max(custody_batch_count - 1, 0),
                custody_completed_cycles=max(custody_batch_count - 1, 0),
                outstanding_rotation_bytes=0,
                additional_runtime_bytes=missing_primary_bytes,
                additional_custody_bytes=0,
            )
        except storage_preflight.StoragePreflightError as exc:
            _fatal("batch recovery startup storage preflight failed", cause=exc)
        manifest_sha256 = head_ledger._verify_manifest_locked(config)
        registrations = head_ledger._scan_registrations_locked(
            config,
            manifest_sha256=manifest_sha256,
        )
        state = _scan_chain_locked(
            config,
            manifest_sha256=manifest_sha256,
            registrations=registrations,
        )
        prepare = state.open_prepare
        if prepare is None:
            return tuple(
                (
                    game_pk,
                    head_ledger._replay_portable_head(config, head),
                )
                for game_pk, head in state.heads
            )
        if prepare.batch_sequence > storage_preflight.MAX_CYCLES:
            _fatal("open batch PREPARE exceeds the frozen cycle horizon")
        archived_source = _revalidate_source_binding(config, prepare.source_binding)
        expected_heads = _result_heads(dict(state.heads), prepare)
        candidate_commit_raw = _commit_record(
            config,
            manifest_sha256=manifest_sha256,
            prepare=prepare,
            committed_heads=expected_heads,
        )
        try:
            storage_preflight.require_cycle_payload(
                source_persisted_bytes=(
                    len(archived_source.summary_bytes)
                    + len(archived_source.feed_receipt_bytes)
                    + len(archived_source.archive_receipt_bytes)
                ),
                prepare_bytes=len(prepare.raw),
                commit_bytes=len(candidate_commit_raw),
                lineage_bytes=sum(
                    len(plan.event_bytes) + 1 for plan in prepare.feed_plan.plans
                ),
                rotation_replica_bytes=sum(
                    receipt.file_size
                    for plan in prepare.feed_plan.plans
                    if (receipt := plan.expected_new_sealed_receipt) is not None
                ),
            )
            storage_preflight.require_storage_preflight(
                runtime_root=config.runtime_root,
                custody_root=config.custody_root,
                runtime_completed_cycles=prepare.batch_sequence - 1,
                custody_completed_cycles=prepare.batch_sequence - 1,
                outstanding_rotation_bytes=sum(
                    head.active_file_size for _, head in state.heads
                ),
                additional_runtime_bytes=0,
                additional_custody_bytes=state.unreferenced_source_bytes,
            )
        except storage_preflight.StoragePreflightError as exc:
            _fatal("open batch PREPARE fails fresh recovery admission", cause=exc)
        committed: list[str] = []

        def publish_recovery_commit(
            batch_plan: feed_lineage.FeedBatchPlan,
            snapshots: tuple[feed_lineage.FeedLineageSnapshot, ...],
            reverify: Callable[[], None],
        ) -> None:
            if batch_plan.plans != prepare.feed_plan.plans:
                _fatal("recovery plans differ from the batch PREPARE")
            reverify()
            for plan, snapshot in zip(batch_plan.plans, snapshots, strict=True):
                if feed_lineage.portable_head_from_snapshot(
                    snapshot,
                    game_pk=plan.game_pk,
                ) != plan.expected_post_head:
                    _fatal("recovered batch lineage differs from PREPARE")
            committed.append(
                _publish_commit_locked(
                    config,
                    manifest_sha256=manifest_sha256,
                    registrations=registrations,
                    prepare=prepare,
                    committed_heads=expected_heads,
                )
            )

        try:
            reconciled_snapshots = feed_lineage._reconcile_feed_transition_batch(
                prepare.feed_plan,
                feed_anchor=config.feed_anchor,
                after_batch=publish_recovery_commit,
                trusted_root=config.runtime_root,
            )
        except feed_lineage.FeedLineageFatalError as exc:
            _fatal("open batch PREPARE cannot reconcile exactly", cause=exc)
        if len(committed) != 1:
            _fatal("batch recovery did not publish exactly one COMMIT")
        return tuple(
            (plan.game_pk, snapshot)
            for plan, snapshot in zip(
                prepare.feed_plan.plans,
                reconciled_snapshots,
                strict=True,
            )
        )


def _volume_binding_from_value(value: object) -> head_ledger.VolumeBinding:
    if not isinstance(value, dict) or set(value) != {
        "filesystem",
        "physical_disk_numbers",
        "volume_root",
        "volume_serial",
    }:
        _fatal("runtime volume binding fields differ")
    filesystem = value.get("filesystem")
    volume_root = value.get("volume_root")
    disks = value.get("physical_disk_numbers")
    if (
        type(filesystem) is not str
        or not filesystem
        or type(volume_root) is not str
        or not volume_root
        or not isinstance(disks, list)
        or not disks
    ):
        _fatal("runtime volume binding values differ")
    disk_numbers = tuple(
        _exact_int(item, field="runtime_volume.disk_number") for item in disks
    )
    if disk_numbers != tuple(sorted(set(disk_numbers))):
        _fatal("runtime volume disk numbers are duplicated or unsorted")
    return head_ledger.VolumeBinding(
        filesystem=filesystem,
        volume_root=volume_root,
        volume_serial=_exact_int(
            value.get("volume_serial"),
            field="runtime_volume.volume_serial",
        ),
        physical_disk_numbers=disk_numbers,
    )


def _restore_config_from_custody(
    *,
    custody_root: Path,
    fresh_runtime_root: Path,
    feed_anchor: policy.FeedLaunchAnchor,
    queue_anchor: policy.QueueLaunchAnchor,
) -> head_ledger.HeadLedgerConfig:
    if not custody_root.is_dir() or not fresh_runtime_root.parent.is_dir():
        _fatal("restore roots must have existing parent storage")
    if os.path.lexists(fresh_runtime_root):
        _fatal("runtime restore target must be fresh and absent")
    head_ledger._assert_root_ancestry(custody_root, allow_sync_root=True)
    head_ledger._assert_root_ancestry(
        fresh_runtime_root.parent,
        allow_sync_root=False,
    )
    control_root = custody_root / "control"
    if not control_root.is_dir():
        _fatal("custody control root is missing")
    guard = control_root / "ledger.guard"
    with feed_lineage._exclusive_append_lock(guard, trusted_root=custody_root):
        registry = control_root / "registry"
        names = head_ledger._directory_names(registry)
        manifest_names = sorted(name for name in names if name.startswith("manifest-"))
        if len(manifest_names) != 1 or names - {
            "games",
            "restores",
            manifest_names[0],
        }:
            _fatal("custody registry manifest inventory differs during restore")
        manifest_raw = head_ledger._read_exact(registry / manifest_names[0])
        manifest = head_ledger._canonical_object(
            manifest_raw,
            field="restore registry manifest",
        )
        if (
            set(manifest) != head_ledger.REGISTRY_MANIFEST_KEYS
            or manifest.get("kind") != "v34_head_registry_manifest"
            or manifest.get("schema_version") != head_ledger.SCHEMA_VERSION
            or manifest.get("feed_launch_manifest_sha256")
            != feed_anchor.manifest_sha256
            or manifest.get("queue_launch_manifest_sha256")
            != queue_anchor.manifest_sha256
        ):
            _fatal("restore registry manifest provenance differs")
        custody_class = manifest.get("custody_class")
        if custody_class not in {"logical_read_only", "independent_device"}:
            _fatal("restore registry custody class differs")
        old_runtime_root = manifest.get("runtime_root")
        if type(old_runtime_root) is not str or not old_runtime_root:
            _fatal("restore registry runtime root differs")
        config = head_ledger.HeadLedgerConfig(
            runtime_root=fresh_runtime_root,
            custody_root=custody_root,
            feed_anchor=feed_anchor,
            queue_anchor=queue_anchor,
            created_at=head_ledger._utc(
                manifest.get("created_at"),
                field="restore_manifest.created_at",
            ),
            custody_class=cast(
                "Literal['logical_read_only', 'independent_device']",
                custody_class,
            ),
            manifest_runtime_root=Path(old_runtime_root),
            manifest_runtime_binding=_volume_binding_from_value(
                manifest.get("runtime_volume")
            ),
        )
    try:
        feed_archive._ensure_durable_directory(
            fresh_runtime_root.parent,
            fresh_runtime_root,
        )
    except (OSError, ValueError, feed_archive.ArchiveCollisionError) as exc:
        _fatal("fresh runtime root creation failed", cause=exc)
    if head_ledger._manifest_bytes(config) != manifest_raw:
        _fatal("fresh runtime config does not reproduce the custody manifest")
    return config


def _reconstruct_lineage_files(
    session: BatchLedgerSession,
) -> None:
    config = session.config
    registrations = dict(session.registrations)
    for registration in registrations.values():
        game_directory = (
            config.runtime_root / registration.lineage_relative_path
        ).parent
        try:
            feed_archive._ensure_durable_directory(config.runtime_root, game_directory)
        except (OSError, ValueError, feed_archive.ArchiveCollisionError) as exc:
            _fatal("custody restore game directory is not durable", cause=exc)

    def apply_committed_prepare(
        prepare: BatchPrepare,
        _commit_sha256: str,
        expected_heads: tuple[tuple[int, feed_lineage.FeedPortableHead], ...],
    ) -> None:
        committed: list[tuple[feed_lineage.FeedLineageSnapshot, ...]] = []

        def finish_batch(
            _plan: feed_lineage.FeedBatchPlan,
            snapshots: tuple[feed_lineage.FeedLineageSnapshot, ...],
            reverify: Callable[[], None],
        ) -> None:
            reverify()
            committed.append(snapshots)

        try:
            snapshots = feed_lineage._reconcile_feed_transition_batch(
                prepare.feed_plan,
                feed_anchor=config.feed_anchor,
                after_batch=finish_batch,
                trusted_root=config.runtime_root,
            )
        except feed_lineage.FeedLineageFatalError as exc:
            _fatal("custody restore lineage reconciliation failed", cause=exc)
        if len(committed) != 1 or committed[0] != snapshots:
            _fatal("custody restore did not close one committed batch")
        restored_heads = dict(expected_heads)
        for plan, snapshot in zip(prepare.feed_plan.plans, snapshots, strict=True):
            if (
                feed_lineage.portable_head_from_snapshot(
                    snapshot,
                    game_pk=plan.game_pk,
                )
                != restored_heads[plan.game_pk]
            ):
                _fatal("custody restore lineage differs from the committed head")

    with head_ledger._control_locks(config):
        restored_state = _scan_chain_locked(
            config,
            manifest_sha256=session.manifest_sha256,
            registrations=registrations,
            committed_callback=apply_committed_prepare,
        )
    if restored_state != session.state:
        _fatal("custody restore scan differs from the opened batch session")


def _committed_head_history(
    session: BatchLedgerSession,
) -> dict[str | None, tuple[tuple[int, feed_lineage.FeedPortableHead], ...]]:
    registrations = dict(session.registrations)
    heads = tuple(
        sorted(
            (game_pk, registration.initial_head)
            for game_pk, registration in registrations.items()
        )
    )
    history: dict[
        str | None,
        tuple[tuple[int, feed_lineage.FeedPortableHead], ...],
    ] = {None: heads}
    def retain_commit(
        _prepare: BatchPrepare,
        commit_sha256: str,
        committed_heads: tuple[tuple[int, feed_lineage.FeedPortableHead], ...],
    ) -> None:
        if commit_sha256 in history:
            _fatal("runtime restore history COMMIT digest is duplicated")
        history[commit_sha256] = committed_heads

    scanned = _scan_chain_locked(
        session.config,
        manifest_sha256=session.manifest_sha256,
        registrations=registrations,
        committed_callback=retain_commit,
    )
    if scanned != session.state:
        _fatal("runtime restore history differs from the batch session")
    return history


def _validate_restore_temp(final_name: str, raw: bytes) -> None:
    match = _RESTORE_NAME.fullmatch(final_name)
    parsed = _canonical_object(raw, field="runtime restore publication temp")
    if (
        match is None
        or _sha256(raw) != match.group(2)
        or parsed.get("kind") != "v34_runtime_restored"
    ):
        _fatal("runtime restore publication temp differs from its final name")


def _parse_restore_record(
    raw: bytes,
    *,
    session: BatchLedgerSession,
    expected_sequence: int,
    expected_prior_sha256: str | None,
    committed_history: Mapping[
        str | None,
        tuple[tuple[int, feed_lineage.FeedPortableHead], ...],
    ],
) -> None:
    parsed = _canonical_object(raw, field="runtime restore record")
    if set(parsed) != RUNTIME_RESTORE_KEYS:
        _fatal("runtime restore record keys differ")
    if (
        parsed.get("kind") != "v34_runtime_restored"
        or parsed.get("schema_version") != SCHEMA_VERSION
        or parsed.get("restore_sequence") != expected_sequence
        or parsed.get("prior_restore_sha256") != expected_prior_sha256
        or parsed.get("registry_manifest_sha256") != session.manifest_sha256
        or parsed.get("feed_launch_manifest_sha256")
        != session.config.feed_anchor.manifest_sha256
    ):
        _fatal("runtime restore record chain or provenance differs")
    committed_batch_sha256 = _digest(
        parsed.get("committed_batch_sha256"),
        field="runtime_restore.committed_batch_sha256",
        optional=True,
    )
    expected_heads = committed_history.get(committed_batch_sha256)
    if expected_heads is None and committed_batch_sha256 not in committed_history:
        _fatal("runtime restore record names an unknown batch COMMIT")
    head_values = parsed.get("heads")
    if not isinstance(head_values, list) or len(head_values) != len(
        session.registrations
    ):
        _fatal("runtime restore head registry size differs")
    registrations = dict(session.registrations)
    parsed_heads: list[tuple[int, feed_lineage.FeedPortableHead]] = []
    for value in head_values:
        if not isinstance(value, dict):
            _fatal("runtime restore head is not an object")
        game_pk = _exact_int(
            value.get("game_pk"),
            field="runtime_restore.head.game_pk",
            minimum=1,
        )
        if game_pk not in registrations:
            _fatal("runtime restore head names an unregistered game")
        parsed_heads.append(
            (
                game_pk,
                head_ledger._head_from_dict(value, expected_game_pk=game_pk),
            )
        )
    if (
        parsed_heads != sorted(parsed_heads)
        or len(dict(parsed_heads)) != len(parsed_heads)
        or tuple(parsed_heads) != expected_heads
    ):
        _fatal("runtime restore heads differ from the named batch COMMIT")
    head_ledger._utc(parsed.get("restored_at"), field="runtime_restore.restored_at")
    restored_root = parsed.get("restored_runtime_root")
    if (
        type(restored_root) is not str
        or not restored_root
        or not Path(restored_root).is_absolute()
    ):
        _fatal("runtime restore root is not an absolute path")
    _volume_binding_from_value(parsed.get("restored_runtime_volume"))


def _publish_restore_record(
    session: BatchLedgerSession,
    *,
    snapshots: tuple[tuple[int, feed_lineage.FeedLineageSnapshot], ...],
    restored_at: str,
) -> str:
    config = session.config
    with head_ledger._control_locks(config):
        manifest_sha256 = head_ledger._verify_manifest_locked(config)
        custody = config.custody_control_root / "registry" / "restores"
        primary = config.primary_control_root / "registry" / "restores"
        head_ledger._recover_directory_prelink_temps(
            custody,
            validate=_validate_restore_temp,
        )

        def validate_primary_temp(final_name: str, raw: bytes) -> None:
            _validate_restore_temp(final_name, raw)
            custody_path = custody / final_name
            if (
                not custody_path.is_file()
                or head_ledger._read_exact(custody_path) != raw
            ):
                _fatal("primary restore temp has no custody authority")

        head_ledger._recover_directory_prelink_temps(
            primary,
            validate=validate_primary_temp,
        )
        custody_names = head_ledger._directory_names(custody)
        primary_names = head_ledger._directory_names(primary)
        if any(_RESTORE_NAME.fullmatch(name) is None for name in custody_names):
            _fatal("custody restore record inventory differs")
        if primary_names - custody_names:
            _fatal("primary restore record exists without custody authority")
        for missing in sorted(custody_names - primary_names):
            head_ledger._write_exact(
                primary / missing,
                head_ledger._read_exact(custody / missing),
            )
        prior_sha256: str | None = None
        expected_sequence = 1
        committed_history = _committed_head_history(session)
        for name in sorted(custody_names):
            match = _RESTORE_NAME.fullmatch(name)
            assert match is not None
            if int(match.group(1)) != expected_sequence:
                _fatal("runtime restore record sequence has a gap")
            raw = head_ledger._read_exact(custody / name)
            if _sha256(raw) != match.group(2):
                _fatal("runtime restore record filename hash differs")
            _parse_restore_record(
                raw,
                session=session,
                expected_sequence=expected_sequence,
                expected_prior_sha256=prior_sha256,
                committed_history=committed_history,
            )
            if head_ledger._read_exact(primary / name) != raw:
                _fatal("runtime restore record differs across custody roots")
            prior_sha256 = _sha256(raw)
            expected_sequence += 1
        runtime_binding = head_ledger.volume_binding(config.runtime_root)
        record = policy.canonical_json_bytes(
            {
                "committed_batch_sha256": session.state.prior_commit_sha256,
                "feed_launch_manifest_sha256": config.feed_anchor.manifest_sha256,
                "heads": [
                    feed_lineage.portable_head_from_snapshot(
                        snapshot,
                        game_pk=game_pk,
                    ).to_dict()
                    for game_pk, snapshot in snapshots
                ],
                "kind": "v34_runtime_restored",
                "prior_restore_sha256": prior_sha256,
                "registry_manifest_sha256": manifest_sha256,
                "restore_sequence": expected_sequence,
                "restored_at": head_ledger._utc(
                    restored_at,
                    field="runtime_restore.restored_at",
                ),
                "restored_runtime_root": str(config.runtime_root.absolute()),
                "restored_runtime_volume": {
                    "filesystem": runtime_binding.filesystem,
                    "physical_disk_numbers": list(
                        runtime_binding.physical_disk_numbers
                    ),
                    "volume_root": runtime_binding.volume_root,
                    "volume_serial": runtime_binding.volume_serial,
                },
                "schema_version": SCHEMA_VERSION,
            }
        )
        digest = _sha256(record)
        filename = f"{expected_sequence:012d}-{digest}.json"
        head_ledger._write_exact(custody / filename, record)
        head_ledger._write_exact(primary / filename, record)
        if (
            head_ledger._read_exact(custody / filename) != record
            or head_ledger._read_exact(primary / filename) != record
        ):
            _fatal("runtime restore record differs after publication")
        return digest


def restore_runtime_from_custody(
    *,
    custody_root: Path,
    fresh_runtime_root: Path,
    feed_anchor: policy.FeedLaunchAnchor,
    queue_anchor: policy.QueueLaunchAnchor,
    restored_at: str,
) -> RestoredRuntime:
    """Rebuild every committed lineage into a fresh runtime generation."""

    config = _restore_config_from_custody(
        custody_root=custody_root,
        fresh_runtime_root=fresh_runtime_root,
        feed_anchor=feed_anchor,
        queue_anchor=queue_anchor,
    )
    try:
        storage_preflight.require_storage_preflight(
            runtime_root=config.runtime_root,
            custody_root=config.custody_root,
            runtime_completed_cycles=0,
            custody_completed_cycles=len(_read_only_custody_batch_names(config)),
            outstanding_rotation_bytes=0,
            additional_runtime_bytes=0,
            additional_custody_bytes=0,
        )
    except storage_preflight.StoragePreflightError as exc:
        _fatal("runtime restore storage preflight failed", cause=exc)
    head_ledger.initialize_head_ledger(config)
    session = open_batch_session(config, _restoring_fresh_runtime=True)
    _reconstruct_lineage_files(session)
    snapshots = recover_batch_chain(config)
    if tuple(
        sorted(
            (
                game_pk,
                feed_lineage.portable_head_from_snapshot(
                    snapshot,
                    game_pk=game_pk,
                ),
            )
            for game_pk, snapshot in snapshots
        )
    ) != session.state.heads:
        _fatal("restored runtime replay differs from custody heads")
    restore_sha256 = _publish_restore_record(
        session,
        snapshots=snapshots,
        restored_at=restored_at,
    )
    return RestoredRuntime(
        config=config,
        snapshots=snapshots,
        restore_record_sha256=restore_sha256,
    )
