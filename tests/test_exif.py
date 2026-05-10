"""Tests for the exif utility module."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PIL import Image

from pixeldump.utils.exif import read_camera_model, read_date_taken, read_gps


def _make_jpg(path: Path, w: int = 100, h: int = 100, color: tuple[int, int, int] = (255, 0, 0)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (w, h), color=color)
    img.save(path, format="JPEG")


def _make_jpg_with_exif(
    path: Path,
    *,
    datetime_str: str | None = None,
    make: str | None = None,
    model: str | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (100, 100), color=(0, 0, 255))
    exif = img.getexif()
    if datetime_str is not None:
        exif[36867] = datetime_str  # DateTimeOriginal
        exif[306] = datetime_str    # DateTime
    if make is not None:
        exif[271] = make
    if model is not None:
        exif[272] = model
    img.save(path, format="JPEG", exif=exif)


def test_read_date_from_jpg_with_exif(tmp_path: Path) -> None:
    p = tmp_path / "with_date.jpg"
    _make_jpg_with_exif(p, datetime_str="2024:03:15 14:30:00")
    result = read_date_taken(p)
    assert result == datetime(2024, 3, 15, 14, 30, 0)


def test_read_date_missing_returns_none(tmp_path: Path) -> None:
    p = tmp_path / "plain.jpg"
    _make_jpg(p)
    assert read_date_taken(p) is None


def test_read_date_nonexistent_returns_none(tmp_path: Path) -> None:
    assert read_date_taken(tmp_path / "does_not_exist.jpg") is None


def test_read_gps_missing_returns_none(tmp_path: Path) -> None:
    p = tmp_path / "plain.jpg"
    _make_jpg(p)
    assert read_gps(p) is None


def test_read_gps_with_exif_but_no_gps_returns_none(tmp_path: Path) -> None:
    p = tmp_path / "with_date.jpg"
    _make_jpg_with_exif(p, datetime_str="2024:03:15 14:30:00")
    assert read_gps(p) is None


def test_read_camera_model_missing_returns_none(tmp_path: Path) -> None:
    p = tmp_path / "plain.jpg"
    _make_jpg(p)
    assert read_camera_model(p) is None


def test_read_camera_model_with_exif(tmp_path: Path) -> None:
    p = tmp_path / "with_camera.jpg"
    _make_jpg_with_exif(p, make="Canon", model="EOS R5")
    result = read_camera_model(p)
    assert result == "Canon EOS R5"


def test_read_camera_model_only_model(tmp_path: Path) -> None:
    p = tmp_path / "model_only.jpg"
    _make_jpg_with_exif(p, model="Pixel 7")
    result = read_camera_model(p)
    assert result == "Pixel 7"
