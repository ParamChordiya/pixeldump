"""Tests for the image utility module."""
from __future__ import annotations

from datetime import datetime
from io import BytesIO
from pathlib import Path

from PIL import Image

from pixeldump.core.types import GPSCoord, PhotoMetadata
from pixeldump.utils.image import get_dimensions, make_thumbnail, to_photo_input


def _make_jpg(path: Path, w: int = 100, h: int = 100, color: tuple[int, int, int] = (255, 0, 0)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (w, h), color=color)
    img.save(path, format="JPEG")


def test_thumbnail_under_max_side(tmp_path: Path) -> None:
    p = tmp_path / "big.jpg"
    _make_jpg(p, w=2000, h=1500)
    thumb_bytes = make_thumbnail(p, max_side=512)

    with Image.open(BytesIO(thumb_bytes)) as img:
        w, h = img.size
        assert max(w, h) <= 512
        # Aspect ratio preserved within 1px tolerance.
        original_ratio = 2000 / 1500
        thumb_ratio = w / h
        assert abs(original_ratio - thumb_ratio) < 0.01


def test_thumbnail_returns_jpeg_bytes(tmp_path: Path) -> None:
    p = tmp_path / "img.jpg"
    _make_jpg(p, w=400, h=300)
    thumb_bytes = make_thumbnail(p)
    assert thumb_bytes.startswith(b"\xff\xd8\xff")


def test_thumbnail_handles_rgba_png(tmp_path: Path) -> None:
    p = tmp_path / "rgba.png"
    img = Image.new("RGBA", (300, 300), color=(255, 0, 0, 128))
    img.save(p, format="PNG")
    thumb_bytes = make_thumbnail(p)
    assert thumb_bytes.startswith(b"\xff\xd8\xff")


def test_get_dimensions_matches_pil(tmp_path: Path) -> None:
    p = tmp_path / "sized.jpg"
    _make_jpg(p, w=640, h=480)
    assert get_dimensions(p) == (640, 480)


def test_to_photo_input(tmp_path: Path) -> None:
    p = tmp_path / "x.jpg"
    _make_jpg(p, w=300, h=200)
    metadata = PhotoMetadata(
        path=p.resolve(),
        date_taken=datetime(2024, 1, 1),
        gps=GPSCoord(lat=0.0, lon=0.0),
        camera_model=None,
        width=300,
        height=200,
        file_size=p.stat().st_size,
    )
    photo_input = to_photo_input(metadata)
    assert photo_input.metadata is metadata
    assert photo_input.thumbnail_media_type == "image/jpeg"
    assert photo_input.thumbnail_bytes.startswith(b"\xff\xd8\xff")
