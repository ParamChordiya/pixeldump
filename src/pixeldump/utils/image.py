"""Image loading + thumbnail generation (handles HEIC via pillow-heif)."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps

from pixeldump.core.types import PhotoInput, PhotoMetadata


def get_dimensions(path: Path) -> tuple[int, int]:
    """Return (width, height) for the image at `path`."""
    with Image.open(path) as img:
        width, height = img.size
        return width, height


def make_thumbnail(path: Path, max_side: int = 512) -> bytes:
    """Read image, downscale to max_side longest edge, return JPEG bytes."""
    with Image.open(path) as img:
        # Apply EXIF orientation first.
        oriented = ImageOps.exif_transpose(img)
        if oriented is None:
            oriented = img
        # Convert to RGB (handles RGBA, P, L, etc.) for JPEG output.
        if oriented.mode != "RGB":
            oriented = oriented.convert("RGB")
        oriented.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
        buffer = BytesIO()
        oriented.save(buffer, format="JPEG", quality=80)
        return buffer.getvalue()


def to_photo_input(metadata: PhotoMetadata, max_side: int = 512) -> PhotoInput:
    """Build a PhotoInput (with thumbnail bytes) from a PhotoMetadata."""
    thumb = make_thumbnail(metadata.path, max_side)
    return PhotoInput(
        metadata=metadata,
        thumbnail_bytes=thumb,
        thumbnail_media_type="image/jpeg",
    )
