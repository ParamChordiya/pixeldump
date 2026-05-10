"""Tests for pixeldump.core.hasher."""
from __future__ import annotations

import shutil
from pathlib import Path

from PIL import Image, ImageDraw

from pixeldump.core.hasher import (
    compute_phash,
    compute_sha256,
    find_duplicates,
    hash_all,
)
from pixeldump.core.types import PhotoMetadata

# ---------- helpers ----------

def _make_jpg(
    path: Path,
    size: tuple[int, int] = (200, 200),
    color: tuple[int, int, int] = (255, 0, 0),
    quality: int = 95,
) -> Path:
    img = Image.new("RGB", size, color)
    # Add a touch of structure so pHash isn't all-zeros on a flat color.
    for x in range(0, size[0], 10):
        for y in range(0, size[1], 10):
            img.putpixel((x, y), (0, 0, 0))
    img.save(path, "JPEG", quality=quality)
    return path


def _meta(path: Path, width: int = 200, height: int = 200, is_video: bool = False) -> PhotoMetadata:
    return PhotoMetadata(
        path=path,
        date_taken=None,
        gps=None,
        camera_model=None,
        width=width,
        height=height,
        file_size=path.stat().st_size,
        is_video=is_video,
    )


# ---------- compute_sha256 ----------

def test_compute_sha256_deterministic(tmp_path: Path) -> None:
    a = _make_jpg(tmp_path / "a.jpg")
    b = tmp_path / "b.jpg"
    shutil.copy(a, b)
    assert compute_sha256(a) == compute_sha256(b)
    assert len(compute_sha256(a)) == 64


def test_compute_sha256_different_content(tmp_path: Path) -> None:
    a = _make_jpg(tmp_path / "a.jpg", color=(255, 0, 0))
    b = _make_jpg(tmp_path / "b.jpg", color=(0, 255, 0))
    assert compute_sha256(a) != compute_sha256(b)


# ---------- compute_phash ----------

def test_compute_phash_returns_hex_string(tmp_path: Path) -> None:
    a = _make_jpg(tmp_path / "a.jpg")
    h = compute_phash(a)
    assert isinstance(h, str)
    assert len(h) > 0
    int(h, 16)  # parses as hex


# ---------- hash_all ----------

def test_hash_all_populates_fields(tmp_path: Path) -> None:
    a = _make_jpg(tmp_path / "a.jpg", color=(10, 20, 30))
    b = _make_jpg(tmp_path / "b.jpg", color=(200, 100, 50))
    photos = [_meta(a), _meta(b)]
    result = hash_all(photos)
    assert result is photos  # mutated in place
    for p in photos:
        assert p.sha256 is not None
        assert len(p.sha256) == 64
        assert p.phash is not None
        assert len(p.phash) > 0


def test_hash_all_skips_phash_for_videos(tmp_path: Path) -> None:
    # Use a JPEG file but mark it as a video so we exercise the skip logic
    # without needing a real video file.
    v = _make_jpg(tmp_path / "v.jpg")
    photo = _meta(v, is_video=True)
    hash_all([photo])
    assert photo.sha256 is not None
    assert photo.phash is None


# ---------- find_duplicates ----------

def test_find_duplicates_exact(tmp_path: Path) -> None:
    a = _make_jpg(tmp_path / "a.jpg", color=(50, 60, 70))
    b = tmp_path / "b.jpg"
    shutil.copy(a, b)
    c = _make_jpg(tmp_path / "c.jpg", color=(123, 200, 0))
    photos = [_meta(a), _meta(b), _meta(c)]
    hash_all(photos)
    groups = find_duplicates(photos)
    assert len(groups) == 1
    g = groups[0]
    assert g.reason == "exact_duplicate"
    assert g.max_hash_distance == 0
    assert len(g.duplicates) == 1
    members = {g.kept.path, *(d.path for d in g.duplicates)}
    assert members == {a, b}


def _shape_image(size: tuple[int, int] = (256, 256)) -> Image.Image:
    """Stable, smooth-looking image for which pHash is invariant under quality/resize."""
    img = Image.new("RGB", size, (255, 255, 255))
    d = ImageDraw.Draw(img)
    w, h = size
    d.ellipse((w * 0.2, h * 0.2, w * 0.8, h * 0.8), fill=(255, 0, 0))
    d.rectangle((w * 0.1, h * 0.1, w * 0.4, h * 0.4), fill=(0, 100, 200))
    d.ellipse((w * 0.6, h * 0.1, w * 0.95, h * 0.45), fill=(0, 200, 50))
    return img


def test_find_duplicates_near(tmp_path: Path) -> None:
    # Same image, different JPEG quality => different bytes, similar pHash.
    img = _shape_image()
    a = tmp_path / "a.jpg"
    b = tmp_path / "b.jpg"
    img.save(a, "JPEG", quality=95)
    img.save(b, "JPEG", quality=60)
    photos = [_meta(a, 256, 256), _meta(b, 256, 256)]
    hash_all(photos)
    # sanity: bytes differ
    assert photos[0].sha256 != photos[1].sha256
    groups = find_duplicates(photos)
    assert len(groups) == 1
    g = groups[0]
    assert g.reason == "near_duplicate"
    assert len(g.duplicates) == 1


def test_find_duplicates_kept_is_highest_res(tmp_path: Path) -> None:
    big_path = tmp_path / "big.jpg"
    small_path = tmp_path / "small.jpg"
    # Same shape image at two resolutions; pHash invariant under resize.
    big_img = _shape_image((2000, 2000))
    big_img.save(big_path, "JPEG", quality=95)
    big_img.resize((500, 500)).save(small_path, "JPEG", quality=95)

    big = PhotoMetadata(
        path=big_path,
        date_taken=None,
        gps=None,
        camera_model=None,
        width=2000,
        height=2000,
        file_size=big_path.stat().st_size,
    )
    small = PhotoMetadata(
        path=small_path,
        date_taken=None,
        gps=None,
        camera_model=None,
        width=500,
        height=500,
        file_size=small_path.stat().st_size,
    )
    photos = [small, big]
    hash_all(photos)
    groups = find_duplicates(photos)
    assert len(groups) == 1
    assert groups[0].kept.path == big_path
    assert [d.path for d in groups[0].duplicates] == [small_path]


def test_find_duplicates_no_dupes(tmp_path: Path) -> None:
    # Build three structurally distinct images so pHashes are far apart.
    paths = []
    size = 128
    for i, seed in enumerate([1, 2, 3]):
        buf = bytearray(size * size * 3)
        idx = 0
        for y in range(size):
            for x in range(size):
                buf[idx] = (x * seed * 7 + y * 3) % 256
                buf[idx + 1] = (y * seed * 11 + x * 5) % 256
                buf[idx + 2] = (x * y * seed) % 256
                idx += 3
        img = Image.frombytes("RGB", (size, size), bytes(buf))
        p = tmp_path / f"img{i}.jpg"
        img.save(p, "JPEG", quality=95)
        paths.append(p)
    photos = [_meta(p, size, size) for p in paths]
    hash_all(photos)
    groups = find_duplicates(photos)
    assert groups == []


def test_find_duplicates_handles_none_phash(tmp_path: Path) -> None:
    a = _make_jpg(tmp_path / "a.jpg", color=(10, 20, 30))
    b = _make_jpg(tmp_path / "b.jpg", color=(200, 100, 50))
    pa = _meta(a)
    pb = _meta(b)
    hash_all([pa, pb])
    # Wipe one phash to simulate a hash failure / video.
    pa.phash = None
    # Should not crash.
    groups = find_duplicates([pa, pb])
    # No exact match (different colors), and pa has no phash so no near group.
    assert groups == []
