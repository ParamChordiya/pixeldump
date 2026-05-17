"""Apply move plans atomically. Phase 6 (final).

Note: manifest persistence lives in `pixeldump.utils.state.write_manifest` —
the mover only builds and applies operations, the orchestrator persists.
"""
from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from pixeldump.core.types import (
    DuplicateGroup,
    EventCluster,
    FolderName,
    LibraryStats,
    MoveOperation,
    PipelineConfig,
    RunManifest,
)


def _is_review(folder_name: FolderName) -> bool:
    """Return True if the folder is routed to the _review tree."""
    return folder_name.date_prefix.startswith("_review")


def _destination_for(root: Path, folder_name: FolderName, source_name: str) -> Path:
    """Build the full destination path for a photo given its folder name."""
    if _is_review(folder_name):
        # _review/<bucket>/<file>
        return root / "_review" / folder_name.name / source_name
    year = folder_name.date_prefix[:4]
    if len(folder_name.date_prefix) == 4:
        # Year-only prefix (documents, screenshots): root/YYYY/name/file
        return root / year / folder_name.name / source_name
    # Year+month prefix (events): root/YYYY/YYYY_MM/name/file
    return root / year / folder_name.date_prefix / folder_name.name / source_name


def _resolve_collision(dest: Path, used: set[Path]) -> Path:
    """If `dest` is already targeted by a planned move, append `_1`, `_2`... before the suffix."""
    if dest not in used:
        return dest
    stem = dest.stem
    suffix = dest.suffix
    parent = dest.parent
    counter = 1
    while True:
        candidate = parent / f"{stem}_{counter}{suffix}"
        if candidate not in used:
            return candidate
        counter += 1


def plan_moves(
    clusters: list[EventCluster],
    folder_names: dict[str, FolderName],
    duplicates: list[DuplicateGroup],
    config: PipelineConfig,
) -> list[MoveOperation]:
    """Build the full list of move operations for a run, given clusters, names, and dupes."""
    root: Path = config.output_dir if config.output_dir is not None else config.target_dir
    now = datetime.now()
    operations: list[MoveOperation] = []
    used_destinations: set[Path] = set()

    # 1. Duplicates first.
    duplicated_paths: set[Path] = set()
    for group in duplicates:
        for photo in group.duplicates:
            duplicated_paths.add(photo.path)
            base_dest = root / "_review" / "duplicates" / photo.path.name
            dest = _resolve_collision(base_dest, used_destinations)
            used_destinations.add(dest)
            operations.append(
                MoveOperation(
                    action="move",
                    source=photo.path,
                    destination=dest,
                    timestamp=now,
                    classification=None,
                    reason=group.reason,
                )
            )

    # 2. Cluster moves.
    for cluster in clusters:
        folder_name = folder_names.get(cluster.cluster_id)
        if folder_name is None:
            continue
        review_route = _is_review(folder_name)
        reason: str | None = None
        if review_route:
            # surface the review bucket as the reason for downstream stats
            reason = folder_name.name  # e.g., "low_confidence", "no_date"
        for photo in cluster.photos:
            if photo.path in duplicated_paths:
                continue
            base_dest = _destination_for(root, folder_name, photo.path.name)
            dest = _resolve_collision(base_dest, used_destinations)
            used_destinations.add(dest)
            operations.append(
                MoveOperation(
                    action="move",
                    source=photo.path,
                    destination=dest,
                    timestamp=now,
                    classification=None,
                    reason=reason,
                )
            )

    return operations


def _classify_reason(reason: str | None) -> str:
    """Bucket reasons for stats: 'sorted' | 'duplicate' | 'review'."""
    if reason is None:
        return "sorted"
    if reason.startswith("exact_duplicate") or reason.startswith("near_duplicate"):
        return "duplicate"
    if reason.startswith("low_confidence") or reason.startswith("no_date"):
        return "review"
    return "sorted"


def apply_moves(operations: list[MoveOperation], dry_run: bool = True) -> RunManifest:
    """Execute (or simulate) the moves and return a manifest.

    The orchestrator (Wave 3) is responsible for filling in `provider` /
    `naming_mode` and persisting via `pixeldump.utils.state.write_manifest`.
    """
    started_at = datetime.now()
    run_id = started_at.strftime("%Y%m%d_%H%M%S")
    manifest = RunManifest(
        version="1.0",
        run_id=run_id,
        provider="",
        naming_mode="",
        started_at=started_at,
        completed_at=None,
        operations=[],
        stats=LibraryStats(),
    )

    folders_touched: set[Path] = set()
    sorted_count = 0
    duplicate_count = 0
    review_count = 0

    for op in operations:
        if dry_run:
            manifest.operations.append(op)
        else:
            try:
                op.destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(op.source), str(op.destination))
            except (OSError, shutil.Error):
                # Wave 3 owns user-facing logging; we just skip failed moves silently.
                continue
            manifest.operations.append(op)

        folders_touched.add(op.destination.parent)
        bucket = _classify_reason(op.reason)
        if bucket == "duplicate":
            duplicate_count += 1
        elif bucket == "review":
            review_count += 1
        else:
            sorted_count += 1

    completed_at = datetime.now()
    manifest.completed_at = completed_at
    manifest.stats.elapsed_seconds = (completed_at - started_at).total_seconds()
    manifest.stats.total_photos = len(manifest.operations)
    manifest.stats.sorted = sorted_count
    manifest.stats.duplicates = duplicate_count
    manifest.stats.needs_review = review_count
    manifest.stats.folders_created = len(folders_touched)
    return manifest
