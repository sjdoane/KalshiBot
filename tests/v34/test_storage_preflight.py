from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from scripts.v34 import storage_preflight as storage

if TYPE_CHECKING:
    from pathlib import Path


def test_real_ntfs_volume_passes_full_horizon_projection(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    custody = tmp_path / "custody"
    runtime.mkdir()
    custody.mkdir()
    projections = storage.require_storage_preflight(
        runtime_root=runtime,
        custody_root=custody,
        runtime_completed_cycles=0,
        custody_completed_cycles=0,
        outstanding_rotation_bytes=0,
        additional_runtime_bytes=0,
        additional_custody_bytes=0,
    )
    assert len(projections) == 1
    projection = projections[0]
    assert projection.remaining_cycles == 28_800
    assert projection.observed_free_bytes >= projection.required_free_bytes
    assert projection.required_free_bytes > 440 * 1024 * 1024 * 1024


def test_insufficient_real_volume_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = tmp_path / "runtime"
    custody = tmp_path / "custody"
    runtime.mkdir()
    custody.mkdir()
    real_disk_usage = storage.shutil.disk_usage

    def no_free_space(path: Path) -> object:
        usage = real_disk_usage(path)
        return usage._replace(free=1)

    monkeypatch.setattr(storage.shutil, "disk_usage", no_free_space)
    with pytest.raises(storage.StoragePreflightError, match="lacks"):
        storage.require_storage_preflight(
            runtime_root=runtime,
            custody_root=custody,
            runtime_completed_cycles=0,
            custody_completed_cycles=0,
            outstanding_rotation_bytes=0,
            additional_runtime_bytes=0,
            additional_custody_bytes=0,
        )


@pytest.mark.parametrize(
    ("field", "limit"),
    [
        ("source_persisted_bytes", storage.MAX_SOURCE_PERSISTED_BYTES),
        ("prepare_bytes", storage.MAX_BATCH_PREPARE_BYTES),
        ("commit_bytes", storage.MAX_BATCH_COMMIT_BYTES),
        ("lineage_bytes", storage.MAX_LINEAGE_BATCH_BYTES),
        ("rotation_replica_bytes", storage.MAX_ROTATION_REPLICA_BYTES),
    ],
)
def test_each_cycle_payload_cap_is_exact(field: str, limit: int) -> None:
    storage.require_cycle_payload(**{field: limit})
    with pytest.raises(storage.StoragePreflightError, match="exceeds"):
        storage.require_cycle_payload(**{field: limit + 1})


def test_cycle_count_cannot_exceed_frozen_horizon(tmp_path: Path) -> None:
    with pytest.raises(storage.StoragePreflightError, match="outside"):
        storage.project_storage(
            runtime_root=tmp_path,
            custody_root=tmp_path,
            runtime_completed_cycles=storage.MAX_CYCLES + 1,
            custody_completed_cycles=0,
            outstanding_rotation_bytes=0,
            additional_runtime_bytes=0,
            additional_custody_bytes=0,
        )


def test_late_restore_charges_full_runtime_but_only_remaining_custody(
    tmp_path: Path,
) -> None:
    runtime = tmp_path / "runtime"
    custody = tmp_path / "custody"
    runtime.mkdir()
    custody.mkdir()
    full = storage.project_storage(
        runtime_root=runtime,
        custody_root=custody,
        runtime_completed_cycles=0,
        custody_completed_cycles=0,
        outstanding_rotation_bytes=0,
        additional_runtime_bytes=0,
        additional_custody_bytes=0,
    )[0]
    late_restore = storage.project_storage(
        runtime_root=runtime,
        custody_root=custody,
        runtime_completed_cycles=0,
        custody_completed_cycles=storage.MAX_CYCLES - 1,
        outstanding_rotation_bytes=0,
        additional_runtime_bytes=0,
        additional_custody_bytes=0,
    )[0]
    assert late_restore.required_free_bytes < full.required_free_bytes
    assert late_restore.remaining_cycles == storage.MAX_CYCLES


def test_same_volume_projection_sums_each_root_once(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    custody = tmp_path / "custody"
    runtime.mkdir()
    custody.mkdir()
    completed = 17
    outstanding = 123_456
    additional = 654_321
    projection = storage.project_storage(
        runtime_root=runtime,
        custody_root=custody,
        runtime_completed_cycles=completed,
        custody_completed_cycles=completed,
        outstanding_rotation_bytes=outstanding,
        additional_runtime_bytes=additional,
        additional_custody_bytes=0,
    )[0]
    remaining = storage.MAX_CYCLES - completed
    expected_raw = storage._root_projection_bytes(
        custody=False,
        runtime_remaining_cycles=remaining,
        custody_remaining_cycles=remaining,
        outstanding_rotation_bytes=outstanding,
        additional_runtime_bytes=additional,
        additional_custody_bytes=0,
    ) + storage._root_projection_bytes(
        custody=True,
        runtime_remaining_cycles=remaining,
        custody_remaining_cycles=remaining,
        outstanding_rotation_bytes=outstanding,
        additional_runtime_bytes=additional,
        additional_custody_bytes=0,
    )
    assert projection.projected_bytes == expected_raw
    assert projection.required_free_bytes == (
        storage._scaled_projection(expected_raw)
        + storage.MINIMUM_FREE_RESERVE_BYTES
    )


def test_distinct_volumes_are_projected_independently(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = tmp_path / "runtime"
    custody = tmp_path / "custody"
    runtime.mkdir()
    custody.mkdir()
    free = 10**15

    def synthetic_volume(path: Path) -> tuple[Path, int, int]:
        resolved = path.resolve(strict=True)
        return resolved, 1 if resolved == runtime.resolve() else 2, free

    monkeypatch.setattr(storage, "_volume_observation", synthetic_volume)
    projections = storage.project_storage(
        runtime_root=runtime,
        custody_root=custody,
        runtime_completed_cycles=0,
        custody_completed_cycles=0,
        outstanding_rotation_bytes=0,
        additional_runtime_bytes=0,
        additional_custody_bytes=0,
    )
    assert len(projections) == 2
    projected_by_root = {
        projection.roots[0]: projection.projected_bytes
        for projection in projections
    }
    assert projected_by_root[str(runtime.resolve())] == storage._root_projection_bytes(
        custody=False,
        runtime_remaining_cycles=storage.MAX_CYCLES,
        custody_remaining_cycles=storage.MAX_CYCLES,
        outstanding_rotation_bytes=0,
        additional_runtime_bytes=0,
        additional_custody_bytes=0,
    )
    assert projected_by_root[str(custody.resolve())] == storage._root_projection_bytes(
        custody=True,
        runtime_remaining_cycles=storage.MAX_CYCLES,
        custody_remaining_cycles=storage.MAX_CYCLES,
        outstanding_rotation_bytes=0,
        additional_runtime_bytes=0,
        additional_custody_bytes=0,
    )
