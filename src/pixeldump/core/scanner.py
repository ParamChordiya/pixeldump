"""File discovery + EXIF extraction. Phase 1 of the pipeline."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from pixeldump.core.types import PhotoMetadata, ScanResult
from pixeldump.utils import exif as exif_utils
from pixeldump.utils import image as image_utils

SUPPORTED_IMAGE_EXTS: frozenset[str] = frozenset({
    ".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp", ".gif",
    ".tiff", ".tif", ".bmp", ".raw", ".cr2", ".cr3", ".nef",
    ".arw", ".dng", ".orf", ".rw2",
})
SUPPORTED_VIDEO_EXTS: frozenset[str] = frozenset({".mp4", ".mov", ".avi", ".mkv"})

_EXCLUDED_DIR_NAMES: frozenset[str] = frozenset({".pixeldump", "_review", "_videos"})


def _is_excluded_path(rel_path: Path) -> bool:
    """Return True if any part of the relative path should cause the file to be skipped."""
    for part in rel_path.parts:
        # Hidden files/dirs (any path component starting with ".").
        if part.startswith("."):
            return True
        if part in _EXCLUDED_DIR_NAMES:
            return True
        if part.startswith("_pixeldump"):
            return True
        if part in {"_review", "_videos"}:
            return True
    return False


def scan(target_dir: Path, include_videos: bool = False) -> ScanResult:
    """Recursively scan target_dir for image/video files and extract metadata."""
    photos: list[PhotoMetadata] = []
    videos: list[PhotoMetadata] = []
    skipped: list[Path] = []
    total_size_bytes = 0
    format_breakdown: dict[str, int] = {}

    target_dir = target_dir.resolve()

    for path in target_dir.rglob("*"):
        if not path.is_file():
            continue

        # Compute path relative to target for exclusion checks.
        try:
            rel = path.relative_to(target_dir)
        except ValueError:
            rel = Path(path.name)

        if _is_excluded_path(rel):
            continue

        suffix = path.suffix.lower()
        is_image = suffix in SUPPORTED_IMAGE_EXTS
        is_video = suffix in SUPPORTED_VIDEO_EXTS

        if not is_image and not is_video:
            continue

        try:
            stat_result = path.stat()
            file_size = stat_result.st_size
        except OSError:
            skipped.append(path.resolve())
            continue

        if file_size <= 0:
            skipped.append(path.resolve())
            continue

        abs_path = path.resolve()

        if is_video:
            if not include_videos:
                continue
            mtime_dt: datetime | None
            try:
                mtime_dt = datetime.fromtimestamp(stat_result.st_mtime)
            except (OSError, ValueError, OverflowError):
                mtime_dt = None
            videos.append(
                PhotoMetadata(
                    path=abs_path,
                    date_taken=mtime_dt,
                    gps=None,
                    camera_model=None,
                    width=0,
                    height=0,
                    file_size=file_size,
                    is_video=True,
                )
            )
            total_size_bytes += file_size
            format_breakdown[suffix] = format_breakdown.get(suffix, 0) + 1
            continue

        # Image branch.
        try:
            width, height = image_utils.get_dimensions(path)
        except Exception:
            skipped.append(abs_path)
            continue

        try:
            date_taken = exif_utils.read_date_taken(path)
        except Exception:
            date_taken = None

        if date_taken is None:
            try:
                date_taken = datetime.fromtimestamp(stat_result.st_mtime)
            except (OSError, ValueError, OverflowError):
                date_taken = None

        try:
            gps = exif_utils.read_gps(path)
        except Exception:
            gps = None

        try:
            camera_model = exif_utils.read_camera_model(path)
        except Exception:
            camera_model = None

        photos.append(
            PhotoMetadata(
                path=abs_path,
                date_taken=date_taken,
                gps=gps,
                camera_model=camera_model,
                width=width,
                height=height,
                file_size=file_size,
                is_video=False,
            )
        )
        total_size_bytes += file_size
        format_breakdown[suffix] = format_breakdown.get(suffix, 0) + 1

    return ScanResult(
        photos=photos,
        videos=videos,
        skipped=skipped,
        total_size_bytes=total_size_bytes,
        format_breakdown=format_breakdown,
    )
