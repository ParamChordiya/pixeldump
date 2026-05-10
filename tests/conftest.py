"""Shared pytest fixtures for PixelDump tests.

Centralises the image-creation and domain-object factory helpers that were
previously duplicated as module-level functions across the test suite.  Each
fixture that returns a callable follows the *factory fixture* pattern: the
fixture itself is injected, and the test calls it to produce objects.

Filesystem fixtures (``make_jpg``, ``make_png``, ``photo_dir``) accept or use
``tmp_path`` so that every file lands inside pytest's temporary directory and is
cleaned up automatically after each test.
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import pytest
from PIL import Image

from pixeldump.core.types import (
    EventCluster,
    GPSCoord,
    NamingMode,
    PhotoMetadata,
    PipelineConfig,
    ProviderName,
)

# ---------------------------------------------------------------------------
# Image-file factories
# ---------------------------------------------------------------------------


@pytest.fixture()
def make_jpg(tmp_path: Path) -> Callable[..., Path]:
    """Factory fixture — returns a callable that creates a JPEG on disk.

    Signature::

        make_jpg(
            path: Path,
            w: int = 100,
            h: int = 100,
            color: tuple[int, int, int] = (255, 0, 0),
            quality: int = 95,
        ) -> Path

    The callable creates any missing parent directories and returns ``path``.
    """

    def _factory(
        path: Path,
        w: int = 100,
        h: int = 100,
        color: tuple[int, int, int] = (255, 0, 0),
        quality: int = 95,
    ) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        img = Image.new("RGB", (w, h), color=color)
        img.save(path, format="JPEG", quality=quality)
        return path

    return _factory


@pytest.fixture()
def make_png(tmp_path: Path) -> Callable[..., Path]:
    """Factory fixture — returns a callable that creates a PNG on disk.

    Signature::

        make_png(
            path: Path,
            w: int = 100,
            h: int = 100,
            color: tuple[int, int, int] = (0, 255, 0),
            quality: int = 95,
        ) -> Path

    The callable creates any missing parent directories and returns ``path``.
    """

    def _factory(
        path: Path,
        w: int = 100,
        h: int = 100,
        color: tuple[int, int, int] = (0, 255, 0),
        quality: int = 95,
    ) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        img = Image.new("RGB", (w, h), color=color)
        # PNG does not support the quality parameter; accepted and silently ignored
        # so callers can use a uniform interface.
        img.save(path, format="PNG")
        return path

    return _factory


# ---------------------------------------------------------------------------
# Domain-object factories
# ---------------------------------------------------------------------------


@pytest.fixture()
def make_photo_meta() -> Callable[..., PhotoMetadata]:
    """Factory fixture — returns a callable that constructs a ``PhotoMetadata``.

    Signature::

        make_photo_meta(
            path: Path,
            *,
            date_taken: datetime | None = datetime(2024, 6, 15, 12, 0, 0),
            gps: GPSCoord | None = None,
            width: int = 100,
            height: int = 100,
            file_size: int = 1000,
            is_video: bool = False,
        ) -> PhotoMetadata

    ``sha256`` and ``phash`` are left as ``None`` (populated by the hasher).
    """

    def _factory(
        path: Path,
        *,
        date_taken: datetime | None = datetime(2024, 6, 15, 12, 0, 0),
        gps: GPSCoord | None = None,
        width: int = 100,
        height: int = 100,
        file_size: int = 1000,
        is_video: bool = False,
    ) -> PhotoMetadata:
        return PhotoMetadata(
            path=path,
            date_taken=date_taken,
            gps=gps,
            camera_model=None,
            width=width,
            height=height,
            file_size=file_size,
            sha256=None,
            phash=None,
            is_video=is_video,
        )

    return _factory


@pytest.fixture()
def make_cluster() -> Callable[..., EventCluster]:
    """Factory fixture — returns a callable that constructs an ``EventCluster``.

    Signature::

        make_cluster(
            cluster_id: str,
            photos: list[PhotoMetadata],
            *,
            date_start: datetime | None = None,
            date_end: datetime | None = None,
        ) -> EventCluster

    ``date_start`` defaults to the minimum ``date_taken`` across *photos* (or
    ``datetime(2024, 6, 15)`` when no photo carries a date).  ``date_end``
    defaults to the maximum.
    """

    def _factory(
        cluster_id: str,
        photos: list[PhotoMetadata],
        *,
        date_start: datetime | None = None,
        date_end: datetime | None = None,
    ) -> EventCluster:
        _fallback = datetime(2024, 6, 15)
        dated = [p.date_taken for p in photos if p.date_taken is not None]
        resolved_start: datetime = date_start if date_start is not None else (min(dated) if dated else _fallback)
        resolved_end: datetime = date_end if date_end is not None else (max(dated) if dated else _fallback)
        return EventCluster(
            cluster_id=cluster_id,
            photos=list(photos),
            date_start=resolved_start,
            date_end=resolved_end,
            gps_center=None,
        )

    return _factory


# ---------------------------------------------------------------------------
# Convenience directory fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def photo_dir(tmp_path: Path) -> Path:
    """Return a ``tmp_path`` sub-directory pre-populated with three 100×100 JPEGs.

    Files created:
    - ``red.jpg``   — solid red   (255,   0,   0)
    - ``green.jpg`` — solid green (  0, 255,   0)
    - ``blue.jpg``  — solid blue  (  0,   0, 255)
    """
    d = tmp_path / "photos"
    d.mkdir()
    for name, color in [
        ("red.jpg", (255, 0, 0)),
        ("green.jpg", (0, 255, 0)),
        ("blue.jpg", (0, 0, 255)),
    ]:
        img = Image.new("RGB", (100, 100), color=color)
        img.save(d / name, format="JPEG")
    return d


# ---------------------------------------------------------------------------
# Pipeline-config factory
# ---------------------------------------------------------------------------


@pytest.fixture()
def pipeline_config(tmp_path: Path) -> Callable[..., PipelineConfig]:
    """Factory fixture — returns a callable that constructs a ``PipelineConfig``.

    Signature::

        pipeline_config(
            target: Path | None = None,
            output: Path | None = None,
            dry_run: bool = True,
        ) -> PipelineConfig

    Defaults: ``provider=ProviderName.AUTO``, ``naming_mode=NamingMode.CHAOTIC``,
    ``sass_level=2``.  ``target`` falls back to ``tmp_path / "target"`` and is
    created if it does not exist; ``output`` falls back to ``tmp_path / "output"``.
    """

    def _factory(
        target: Path | None = None,
        output: Path | None = None,
        dry_run: bool = True,
    ) -> PipelineConfig:
        resolved_target = target if target is not None else tmp_path / "target"
        resolved_target.mkdir(parents=True, exist_ok=True)
        resolved_output = output if output is not None else tmp_path / "output"
        return PipelineConfig(
            target_dir=resolved_target,
            provider=ProviderName.AUTO,
            naming_mode=NamingMode.CHAOTIC,
            sass_level=2,
            output_dir=resolved_output,
            dry_run=dry_run,
        )

    return _factory
