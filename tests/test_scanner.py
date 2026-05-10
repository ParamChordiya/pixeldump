"""Tests for the scanner module."""
from __future__ import annotations

from pathlib import Path

from PIL import Image

from pixeldump.core.scanner import scan


def _make_jpg(path: Path, w: int = 100, h: int = 100, color: tuple[int, int, int] = (255, 0, 0)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (w, h), color=color)
    img.save(path, format="JPEG")


def _make_png(path: Path, w: int = 100, h: int = 100, color: tuple[int, int, int] = (0, 255, 0)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (w, h), color=color)
    img.save(path, format="PNG")


def test_scan_finds_jpgs(tmp_path: Path) -> None:
    _make_jpg(tmp_path / "a.jpg")
    _make_jpg(tmp_path / "b.jpg")
    _make_jpg(tmp_path / "sub" / "c.jpg")

    result = scan(tmp_path)

    assert len(result.photos) == 3
    paths = {p.path for p in result.photos}
    assert all(p.is_absolute() for p in paths)
    assert all(not p.is_video for p in result.photos)
    assert result.total_size_bytes > 0


def test_scan_skips_hidden_dirs(tmp_path: Path) -> None:
    _make_jpg(tmp_path / "visible.jpg")
    _make_jpg(tmp_path / ".hidden" / "secret.jpg")

    result = scan(tmp_path)

    assert len(result.photos) == 1
    assert result.photos[0].path.name == "visible.jpg"


def test_scan_skips_pixeldump_dir(tmp_path: Path) -> None:
    _make_jpg(tmp_path / "ok.jpg")
    _make_jpg(tmp_path / ".pixeldump" / "foo.jpg")
    _make_jpg(tmp_path / "_pixeldump_legacy" / "bar.jpg")
    _make_jpg(tmp_path / "_review" / "baz.jpg")
    _make_jpg(tmp_path / "_videos" / "qux.jpg")

    result = scan(tmp_path)

    assert len(result.photos) == 1
    assert result.photos[0].path.name == "ok.jpg"


def test_scan_videos_excluded_by_default(tmp_path: Path) -> None:
    _make_jpg(tmp_path / "photo.jpg")
    video = tmp_path / "movie.mp4"
    video.write_bytes(b"not really a video but has bytes")

    default_result = scan(tmp_path)
    assert len(default_result.photos) == 1
    assert len(default_result.videos) == 0

    with_videos = scan(tmp_path, include_videos=True)
    assert len(with_videos.photos) == 1
    assert len(with_videos.videos) == 1
    assert with_videos.videos[0].is_video is True
    assert with_videos.videos[0].width == 0
    assert with_videos.videos[0].height == 0


def test_scan_format_breakdown(tmp_path: Path) -> None:
    _make_jpg(tmp_path / "a.jpg")
    _make_jpg(tmp_path / "b.jpg")
    _make_png(tmp_path / "c.png")

    result = scan(tmp_path)

    assert result.format_breakdown.get(".jpg") == 2
    assert result.format_breakdown.get(".png") == 1


def test_scan_skips_zero_byte_files(tmp_path: Path) -> None:
    _make_jpg(tmp_path / "good.jpg")
    bad = tmp_path / "empty.jpg"
    bad.write_bytes(b"")

    result = scan(tmp_path)

    assert len(result.photos) == 1
    assert any(p.name == "empty.jpg" for p in result.skipped)


def test_scan_returns_absolute_paths(tmp_path: Path) -> None:
    _make_jpg(tmp_path / "x.jpg")
    result = scan(tmp_path)
    assert result.photos[0].path.is_absolute()
