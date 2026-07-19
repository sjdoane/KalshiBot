"""Frozen 24-hour storage and per-cycle payload gates for v34."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Final

POLL_TARGET_SECONDS: Final = 3
MAX_HORIZON_SECONDS: Final = 24 * 60 * 60
MAX_CYCLES: Final = MAX_HORIZON_SECONDS // POLL_TARGET_SECONDS

MAX_SOURCE_PERSISTED_BYTES: Final = 2 * 1024 * 1024
MAX_BATCH_PREPARE_BYTES: Final = 2 * 1024 * 1024
MAX_BATCH_COMMIT_BYTES: Final = 512 * 1024
MAX_LINEAGE_BATCH_BYTES: Final = 1 * 1024 * 1024
MAX_ROTATION_REPLICA_BYTES: Final = 512 * 1024 * 1024
PER_CYCLE_METADATA_ALLOWANCE_BYTES: Final = 128 * 1024
MAX_ROTATIONS_PER_CYCLE: Final = 64
MAX_ACTIVE_LINEAGE_BYTES_PER_GAME: Final = 32 * 1024 * 1024
MAX_OUTSTANDING_ROTATION_LIABILITY_BYTES: Final = (
    MAX_ROTATIONS_PER_CYCLE * MAX_ACTIVE_LINEAGE_BYTES_PER_GAME
)
PER_ROTATION_METADATA_ALLOWANCE_BYTES: Final = 16 * 1024
PER_CYCLE_ROTATION_METADATA_ALLOWANCE_BYTES: Final = (
    MAX_ROTATIONS_PER_CYCLE * PER_ROTATION_METADATA_ALLOWANCE_BYTES
)

SAFETY_FACTOR_NUMERATOR: Final = 3
SAFETY_FACTOR_DENOMINATOR: Final = 2
MINIMUM_FREE_RESERVE_BYTES: Final = 20 * 1024 * 1024 * 1024


class StoragePreflightError(RuntimeError):
    """The frozen run cannot fit or one cycle exceeds its cadence budget."""


@dataclass(frozen=True, slots=True)
class VolumeProjection:
    volume_device: int
    roots: tuple[str, ...]
    remaining_cycles: int
    projected_bytes: int
    required_free_bytes: int
    observed_free_bytes: int


def _scaled_projection(raw_bytes: int) -> int:
    return (
        raw_bytes * SAFETY_FACTOR_NUMERATOR + SAFETY_FACTOR_DENOMINATOR - 1
    ) // SAFETY_FACTOR_DENOMINATOR


def _root_projection_bytes(
    *,
    custody: bool,
    runtime_remaining_cycles: int,
    custody_remaining_cycles: int,
    outstanding_rotation_bytes: int,
    additional_runtime_bytes: int,
    additional_custody_bytes: int,
) -> int:
    if custody:
        remaining_cycles = custody_remaining_cycles
        per_cycle = (
            MAX_SOURCE_PERSISTED_BYTES
            + MAX_BATCH_PREPARE_BYTES
            + MAX_BATCH_COMMIT_BYTES
            + PER_CYCLE_METADATA_ALLOWANCE_BYTES // 2
        )
    else:
        remaining_cycles = runtime_remaining_cycles
        per_cycle = (
            MAX_BATCH_PREPARE_BYTES
            + MAX_BATCH_COMMIT_BYTES
            + 2 * MAX_LINEAGE_BATCH_BYTES
            + PER_CYCLE_ROTATION_METADATA_ALLOWANCE_BYTES
            + PER_CYCLE_METADATA_ALLOWANCE_BYTES // 2
        )
    return per_cycle * remaining_cycles + (
        additional_custody_bytes
        if custody
        else outstanding_rotation_bytes + additional_runtime_bytes
    )


def _volume_observation(root: Path) -> tuple[Path, int, int]:
    resolved = root.resolve(strict=True)
    return resolved, resolved.stat().st_dev, shutil.disk_usage(resolved).free


def project_storage(
    *,
    runtime_root: Path,
    custody_root: Path,
    runtime_completed_cycles: int,
    custody_completed_cycles: int,
    outstanding_rotation_bytes: int,
    additional_runtime_bytes: int,
    additional_custody_bytes: int,
) -> tuple[VolumeProjection, ...]:
    for name, completed_cycles in (
        ("runtime", runtime_completed_cycles),
        ("custody", custody_completed_cycles),
    ):
        if (
            type(completed_cycles) is not int
            or not 0 <= completed_cycles <= MAX_CYCLES
        ):
            raise StoragePreflightError(
                f"{name} completed cycle count is outside the frozen horizon"
            )
    runtime_remaining_cycles = MAX_CYCLES - runtime_completed_cycles
    custody_remaining_cycles = MAX_CYCLES - custody_completed_cycles
    if type(outstanding_rotation_bytes) is not int or outstanding_rotation_bytes < 0:
        raise StoragePreflightError("outstanding rotation byte count is invalid")
    if type(additional_runtime_bytes) is not int or additional_runtime_bytes < 0:
        raise StoragePreflightError("additional runtime byte count is invalid")
    if type(additional_custody_bytes) is not int or additional_custody_bytes < 0:
        raise StoragePreflightError("additional custody byte count is invalid")
    roots = ((runtime_root, False), (custody_root, True))
    grouped: dict[int, list[tuple[Path, int, int]]] = {}
    for root, custody in roots:
        if not isinstance(root, Path) or not root.is_dir():
            raise StoragePreflightError("storage preflight root is not an existing directory")
        resolved, device, free_bytes = _volume_observation(root)
        grouped.setdefault(device, []).append(
            (
                resolved,
                _root_projection_bytes(
                    custody=custody,
                    runtime_remaining_cycles=runtime_remaining_cycles,
                    custody_remaining_cycles=custody_remaining_cycles,
                    outstanding_rotation_bytes=outstanding_rotation_bytes,
                    additional_runtime_bytes=additional_runtime_bytes,
                    additional_custody_bytes=additional_custody_bytes,
                ),
                free_bytes,
            )
        )
    projections: list[VolumeProjection] = []
    for device, rows in sorted(grouped.items()):
        raw_projection = sum(row[1] for row in rows)
        required_free = _scaled_projection(raw_projection) + MINIMUM_FREE_RESERVE_BYTES
        observed_free = min(row[2] for row in rows)
        projections.append(
            VolumeProjection(
                volume_device=device,
                roots=tuple(sorted(str(row[0]) for row in rows)),
                remaining_cycles=max(
                    runtime_remaining_cycles,
                    custody_remaining_cycles,
                ),
                projected_bytes=raw_projection,
                required_free_bytes=required_free,
                observed_free_bytes=observed_free,
            )
        )
    return tuple(projections)


def require_storage_preflight(
    *,
    runtime_root: Path,
    custody_root: Path,
    runtime_completed_cycles: int,
    custody_completed_cycles: int,
    outstanding_rotation_bytes: int,
    additional_runtime_bytes: int,
    additional_custody_bytes: int,
) -> tuple[VolumeProjection, ...]:
    projections = project_storage(
        runtime_root=runtime_root,
        custody_root=custody_root,
        runtime_completed_cycles=runtime_completed_cycles,
        custody_completed_cycles=custody_completed_cycles,
        outstanding_rotation_bytes=outstanding_rotation_bytes,
        additional_runtime_bytes=additional_runtime_bytes,
        additional_custody_bytes=additional_custody_bytes,
    )
    for projection in projections:
        if projection.observed_free_bytes < projection.required_free_bytes:
            raise StoragePreflightError(
                "storage volume lacks the frozen 24-hour projection and reserve"
            )
    return projections


def require_cycle_payload(
    *,
    source_persisted_bytes: int | None = None,
    prepare_bytes: int | None = None,
    commit_bytes: int | None = None,
    lineage_bytes: int | None = None,
    rotation_replica_bytes: int | None = None,
) -> None:
    limits = (
        ("source", source_persisted_bytes, MAX_SOURCE_PERSISTED_BYTES),
        ("PREPARE", prepare_bytes, MAX_BATCH_PREPARE_BYTES),
        ("COMMIT", commit_bytes, MAX_BATCH_COMMIT_BYTES),
        ("lineage", lineage_bytes, MAX_LINEAGE_BATCH_BYTES),
        (
            "rotation replica",
            rotation_replica_bytes,
            MAX_ROTATION_REPLICA_BYTES,
        ),
    )
    for name, value, limit in limits:
        if value is None:
            continue
        if type(value) is not int or value < 0:
            raise StoragePreflightError(f"{name} payload byte count is invalid")
        if value > limit:
            raise StoragePreflightError(
                f"{name} payload exceeds the frozen cadence and storage cap"
            )
