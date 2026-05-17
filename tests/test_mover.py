"""Tests for pixeldump.core.mover and pixeldump.utils.state."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from pixeldump.core.mover import apply_moves, plan_moves
from pixeldump.core.types import (
    DuplicateGroup,
    EventCluster,
    FolderName,
    LibraryStats,
    MoveOperation,
    NamingMode,
    PhotoMetadata,
    PipelineConfig,
    ProviderName,
    RunManifest,
)
from pixeldump.utils.state import (
    load_manifest,
    state_dir,
    thumbnail_cache_path,
    write_manifest,
)


def _make_photo(path: Path, when: datetime | None = None) -> PhotoMetadata:
    return PhotoMetadata(
        path=path,
        date_taken=when or datetime(2024, 3, 15, 12, 0, 0),
        gps=None,
        camera_model=None,
        width=4032,
        height=3024,
        file_size=1234,
    )


def _make_config(target: Path, output: Path | None = None) -> PipelineConfig:
    return PipelineConfig(
        target_dir=target,
        provider=ProviderName.AUTO,
        naming_mode=NamingMode.CHAOTIC,
        sass_level=2,
        output_dir=output,
        dry_run=True,
    )


def _touch(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x")
    return path


def _make_cluster(cluster_id: str, photos: list[PhotoMetadata]) -> EventCluster:
    return EventCluster(
        cluster_id=cluster_id,
        photos=photos,
        date_start=datetime(2024, 3, 15),
        date_end=datetime(2024, 3, 16),
    )


# ---- plan_moves ----

def test_plan_moves_routes_clusters_to_year_subfolder(tmp_path: Path) -> None:
    src = tmp_path / "src"
    p1 = _touch(src / "IMG_4021.jpg")
    p2 = _touch(src / "IMG_4022.jpg")
    cluster = _make_cluster("c1", [_make_photo(p1), _make_photo(p2)])
    folder_names = {"c1": FolderName("japan_trip", "2024_03")}
    config = _make_config(target_dir := tmp_path / "out")
    target_dir.mkdir(parents=True, exist_ok=True)

    ops = plan_moves([cluster], folder_names, [], config)

    assert len(ops) == 2
    expected_dir = target_dir / "2024" / "2024_03" / "japan_trip"
    assert ops[0].destination == expected_dir / "IMG_4021.jpg"
    assert ops[1].destination == expected_dir / "IMG_4022.jpg"
    assert all(op.action == "move" for op in ops)
    assert all(op.reason is None for op in ops)


def test_plan_moves_routes_duplicates_to_review(tmp_path: Path) -> None:
    src = tmp_path / "src"
    kept = _make_photo(_touch(src / "kept.jpg"))
    d1 = _make_photo(_touch(src / "d1.jpg"))
    d2 = _make_photo(_touch(src / "d2.jpg"))
    group = DuplicateGroup(kept=kept, duplicates=[d1, d2], reason="exact_duplicate", max_hash_distance=0)
    config = _make_config(tmp_path / "out")

    ops = plan_moves([], {}, [group], config)

    assert len(ops) == 2
    review_dir = (tmp_path / "out") / "_review" / "duplicates"
    dests = {op.destination for op in ops}
    assert dests == {review_dir / "d1.jpg", review_dir / "d2.jpg"}
    assert all(op.reason == "exact_duplicate" for op in ops)


def test_plan_moves_does_not_double_move_kept_dup(tmp_path: Path) -> None:
    src = tmp_path / "src"
    kept_path = _touch(src / "kept.jpg")
    dup_path = _touch(src / "dup.jpg")
    kept = _make_photo(kept_path)
    dup = _make_photo(dup_path)
    cluster = _make_cluster("c1", [kept, dup])
    folder_names = {"c1": FolderName("japan_trip", "2024_03")}
    group = DuplicateGroup(kept=kept, duplicates=[dup], reason="exact_duplicate", max_hash_distance=0)
    config = _make_config(tmp_path / "out")

    ops = plan_moves([cluster], folder_names, [group], config)

    # 1 dup move + 1 cluster move (for kept) = 2 ops total. kept is NOT in duplicates.
    assert len(ops) == 2
    sources = {op.source for op in ops}
    assert sources == {kept_path, dup_path}
    # kept goes to event folder
    kept_op = next(op for op in ops if op.source == kept_path)
    assert kept_op.destination == (tmp_path / "out") / "2024" / "2024_03" / "japan_trip" / "kept.jpg"
    # dup goes to review
    dup_op = next(op for op in ops if op.source == dup_path)
    assert dup_op.destination == (tmp_path / "out") / "_review" / "duplicates" / "dup.jpg"


def test_plan_moves_low_confidence_routed_to_review(tmp_path: Path) -> None:
    src = tmp_path / "src"
    photo = _make_photo(_touch(src / "weird.jpg"))
    cluster = _make_cluster("c1", [photo])
    folder_names = {"c1": FolderName("low_confidence", "_review")}
    config = _make_config(tmp_path / "out")

    ops = plan_moves([cluster], folder_names, [], config)

    assert len(ops) == 1
    assert ops[0].destination == (tmp_path / "out") / "_review" / "low_confidence" / "weird.jpg"
    assert ops[0].reason == "low_confidence"


def test_plan_moves_no_date_routed_to_review(tmp_path: Path) -> None:
    src = tmp_path / "src"
    photo = _make_photo(_touch(src / "ancient.jpg"), when=datetime(1970, 1, 1))
    cluster = _make_cluster("no_date", [photo])
    folder_names = {"no_date": FolderName("no_date", "_review")}
    config = _make_config(tmp_path / "out")

    ops = plan_moves([cluster], folder_names, [], config)

    assert len(ops) == 1
    assert ops[0].destination == (tmp_path / "out") / "_review" / "no_date" / "ancient.jpg"
    assert ops[0].reason == "no_date"


def test_plan_moves_screenshot_year_path(tmp_path: Path) -> None:
    src = tmp_path / "src"
    photo = _make_photo(_touch(src / "IMG_5000.png"))
    cluster = _make_cluster("c1", [photo])
    folder_names = {"c1": FolderName("screenshots", "2024")}
    config = _make_config(tmp_path / "out")

    ops = plan_moves([cluster], folder_names, [], config)

    assert len(ops) == 1
    assert ops[0].destination == (tmp_path / "out") / "2024" / "screenshots" / "IMG_5000.png"


def test_plan_moves_filename_collision_appends_suffix(tmp_path: Path) -> None:
    src_a = tmp_path / "a"
    src_b = tmp_path / "b"
    p_a = _touch(src_a / "IMG_1.jpg")
    p_b = _touch(src_b / "IMG_1.jpg")
    cluster = _make_cluster("c1", [_make_photo(p_a), _make_photo(p_b)])
    folder_names = {"c1": FolderName("trip", "2024_03")}
    config = _make_config(tmp_path / "out")

    ops = plan_moves([cluster], folder_names, [], config)

    assert len(ops) == 2
    base = (tmp_path / "out") / "2024" / "2024_03" / "trip"
    assert ops[0].destination == base / "IMG_1.jpg"
    assert ops[1].destination == base / "IMG_1_1.jpg"


# ---- apply_moves ----

def _make_op(src: Path, dst: Path, reason: str | None = None) -> MoveOperation:
    return MoveOperation(
        action="move",
        source=src,
        destination=dst,
        timestamp=datetime.now(),
        classification=None,
        reason=reason,
    )


def test_apply_moves_dry_run_does_not_move(tmp_path: Path) -> None:
    src = _touch(tmp_path / "src" / "a.jpg")
    dst = tmp_path / "out" / "2024" / "2024_03_trip" / "a.jpg"
    op = _make_op(src, dst)

    manifest = apply_moves([op], dry_run=True)

    assert src.exists()
    assert not dst.exists()
    assert len(manifest.operations) == 1
    assert manifest.completed_at is not None


def test_apply_moves_real_move(tmp_path: Path) -> None:
    src = _touch(tmp_path / "src" / "a.jpg")
    dst = tmp_path / "out" / "2024" / "2024_03_trip" / "a.jpg"
    op = _make_op(src, dst)

    manifest = apply_moves([op], dry_run=False)

    assert not src.exists()
    assert dst.exists()
    assert len(manifest.operations) == 1


def test_apply_moves_skips_failed_move(tmp_path: Path) -> None:
    missing = tmp_path / "src" / "ghost.jpg"  # never created
    dst = tmp_path / "out" / "ghost.jpg"
    op = _make_op(missing, dst)

    manifest = apply_moves([op], dry_run=False)

    assert manifest.operations == []
    assert manifest.stats.total_photos == 0


def test_apply_moves_creates_destination_dirs(tmp_path: Path) -> None:
    src = _touch(tmp_path / "src" / "a.jpg")
    dst = tmp_path / "out" / "deeply" / "nested" / "a.jpg"
    op = _make_op(src, dst)

    apply_moves([op], dry_run=False)

    assert dst.exists()
    assert dst.parent.is_dir()


def test_apply_moves_stats_count_correctly(tmp_path: Path) -> None:
    ops: list[MoveOperation] = []
    # 5 normal
    for i in range(5):
        s = _touch(tmp_path / "src" / f"n{i}.jpg")
        ops.append(_make_op(s, tmp_path / "out" / "2024" / "2024_03_trip" / f"n{i}.jpg"))
    # 2 dupes
    for i in range(2):
        s = _touch(tmp_path / "src" / f"d{i}.jpg")
        ops.append(
            _make_op(
                s,
                tmp_path / "out" / "_review" / "duplicates" / f"d{i}.jpg",
                reason="exact_duplicate",
            )
        )
    # 1 low_confidence
    s = _touch(tmp_path / "src" / "lc.jpg")
    ops.append(
        _make_op(
            s,
            tmp_path / "out" / "_review" / "low_confidence" / "lc.jpg",
            reason="low_confidence",
        )
    )

    manifest = apply_moves(ops, dry_run=True)

    assert manifest.stats.total_photos == 8
    assert manifest.stats.sorted == 5
    assert manifest.stats.duplicates == 2
    assert manifest.stats.needs_review == 1
    assert manifest.stats.folders_created == 3


# ---- state ----

def test_state_dir_creates_subdirs(tmp_path: Path) -> None:
    base = state_dir(tmp_path)
    assert base == tmp_path / ".pixeldump"
    assert (base / "manifests").is_dir()
    assert (base / "runs").is_dir()
    assert (base / "thumbnails").is_dir()


def test_thumbnail_cache_path(tmp_path: Path) -> None:
    p = thumbnail_cache_path(tmp_path)
    assert p == tmp_path / ".pixeldump" / "thumbnails"


def test_write_and_load_manifest_roundtrip(tmp_path: Path) -> None:
    src = _touch(tmp_path / "src" / "a.jpg")
    dst = tmp_path / "out" / "2024" / "2024_03_trip" / "a.jpg"
    op = _make_op(src, dst, reason=None)
    manifest = RunManifest(
        version="1.0",
        run_id="20260509_120000",
        provider="claude",
        naming_mode="chaotic",
        started_at=datetime(2026, 5, 9, 12, 0, 0),
        completed_at=datetime(2026, 5, 9, 12, 0, 30),
        operations=[op],
        stats=LibraryStats(total_photos=1, sorted=1, folders_created=1, elapsed_seconds=30.0),
    )

    out_path = write_manifest(tmp_path, manifest)
    assert out_path.exists()
    assert out_path.name == "20260509_120000.json"

    loaded = load_manifest(out_path)
    assert loaded.version == manifest.version
    assert loaded.run_id == manifest.run_id
    assert loaded.provider == manifest.provider
    assert loaded.naming_mode == manifest.naming_mode
    assert loaded.started_at == manifest.started_at
    assert loaded.completed_at == manifest.completed_at
    assert len(loaded.operations) == 1
    assert loaded.operations[0].source == op.source
    assert loaded.operations[0].destination == op.destination
    assert loaded.operations[0].timestamp == op.timestamp
    assert loaded.operations[0].reason == op.reason
    assert loaded.stats.total_photos == 1
    assert loaded.stats.sorted == 1
    assert loaded.stats.elapsed_seconds == 30.0
