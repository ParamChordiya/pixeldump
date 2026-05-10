"""Pipeline orchestrator end-to-end tests with a mocked VisionProvider."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PIL import Image

from pixeldump.app import Pipeline
from pixeldump.core.types import (
    Classification,
    NamingMode,
    Phase,
    PipelineConfig,
    ProviderName,
    RunManifest,
)
from pixeldump.providers.base import VisionProvider


def _make_jpg(p: Path, w: int = 100, h: int = 100, color: tuple[int, int, int] = (255, 0, 0)) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (w, h), color).save(p, "JPEG")


def _build_provider(
    *, available: bool = True, classification: Classification | None = None,
    name_event: str = "test_event",
) -> MagicMock:
    """Build a MagicMock provider that satisfies VisionProvider's surface."""
    cls = classification or Classification(
        category="travel",
        subcategory="city_break",
        confidence=0.9,
        description="a trip",
        notable=[],
    )
    provider = MagicMock(spec=VisionProvider)
    provider.name = "claude"
    provider.is_available.return_value = available
    provider.classify_cluster.return_value = cls
    provider.name_event.return_value = name_event
    provider.estimate_cost.return_value = None
    return provider


def _build_config(
    target: Path,
    *,
    dry_run: bool = True,
    skip_duplicates: bool = False,
    skip_clustering: bool = False,
) -> PipelineConfig:
    return PipelineConfig(
        target_dir=target,
        provider=ProviderName.CLAUDE,
        naming_mode=NamingMode.CHAOTIC,
        sass_level=0,
        burst_hours=72,
        batch_size=5,
        concurrency=2,
        include_videos=False,
        skip_duplicates=skip_duplicates,
        skip_clustering=skip_clustering,
        output_dir=None,
        dry_run=dry_run,
        quiet=True,
    )


def test_pipeline_runs_end_to_end_dry_run(tmp_path: Path) -> None:
    src = tmp_path / "src"
    for i in range(4):
        _make_jpg(src / f"IMG_{i}.jpg", color=(i * 50, 0, 0))

    provider = _build_provider()
    config = _build_config(src, dry_run=True)
    pipeline = Pipeline(config, provider)

    manifest = pipeline.run()

    assert isinstance(manifest, RunManifest)
    assert len(manifest.operations) > 0
    assert manifest.provider == "claude"
    assert manifest.naming_mode == "chaotic"
    # Dry-run: source files unchanged.
    for i in range(4):
        assert (src / f"IMG_{i}.jpg").exists()


def test_pipeline_calls_hooks_in_order(tmp_path: Path) -> None:
    src = tmp_path / "src"
    for i in range(2):
        _make_jpg(src / f"IMG_{i}.jpg")

    phases_seen: list[Phase] = []

    class Recorder:
        def on_phase(self, phase: Phase) -> None:
            phases_seen.append(phase)

        def on_progress(self, completed: int, total: int) -> None:
            pass

        def on_activity(self, line: str) -> None:
            pass

        def on_stats(self, stats: object) -> None:
            pass

    provider = _build_provider()
    config = _build_config(src, dry_run=True)
    pipeline = Pipeline(config, provider, hooks=Recorder())
    pipeline.run()

    assert phases_seen == [
        Phase.SETUP,
        Phase.SCANNING,
        Phase.HASHING,
        Phase.CLUSTERING,
        Phase.CLASSIFYING,
        Phase.MOVING,
        Phase.COMPLETE,
    ]


def test_pipeline_apply_actually_moves_files(tmp_path: Path) -> None:
    src = tmp_path / "src"
    for i in range(3):
        _make_jpg(src / f"IMG_{i}.jpg", color=(i * 80, 0, 0))

    provider = _build_provider()
    config = _build_config(src, dry_run=False)
    pipeline = Pipeline(config, provider)
    manifest = pipeline.run()

    # Files should no longer exist at their original location.
    for i in range(3):
        original = src / f"IMG_{i}.jpg"
        if original.exists():
            # If still there, it must mean a move was skipped — fail loudly.
            pytest.fail(f"file {original} was not moved")
    # Each operation's destination should exist.
    for op in manifest.operations:
        assert op.destination.exists(), f"destination missing: {op.destination}"


def test_pipeline_skip_duplicates_skips_hash_phase_work(tmp_path: Path) -> None:
    src = tmp_path / "src"
    # Make two truly identical files: this would normally trigger a duplicate.
    _make_jpg(src / "a.jpg")
    _make_jpg(src / "b.jpg")
    # Force them identical at byte level.
    (src / "b.jpg").write_bytes((src / "a.jpg").read_bytes())

    provider = _build_provider()
    config = _build_config(src, dry_run=True, skip_duplicates=True)
    pipeline = Pipeline(config, provider)
    manifest = pipeline.run()

    # No move op should have a duplicate-related reason.
    duplicate_reasons = {"exact_duplicate", "near_duplicate"}
    assert all(
        op.reason not in duplicate_reasons for op in manifest.operations
    ), "skip_duplicates=True should not produce dup ops"
    # And the rolling stats should not have counted duplicates.
    assert pipeline.stats().duplicates == 0


def test_pipeline_provider_unavailable_raises(tmp_path: Path) -> None:
    src = tmp_path / "src"
    _make_jpg(src / "x.jpg")

    provider = _build_provider(available=False)
    config = _build_config(src, dry_run=True)
    pipeline = Pipeline(config, provider)

    with pytest.raises(RuntimeError, match="provider not available"):
        pipeline.run()


def test_pipeline_uses_provider_for_naming(tmp_path: Path) -> None:
    """Smoke check: provider.classify_cluster + name_event get exercised."""
    src = tmp_path / "src"
    for i in range(2):
        _make_jpg(src / f"IMG_{i}.jpg")

    provider = _build_provider()
    config = _build_config(src, dry_run=True)
    pipeline = Pipeline(config, provider)
    manifest = pipeline.run()

    assert provider.classify_cluster.called
    assert provider.name_event.called
    assert manifest.run_id  # non-empty
    assert manifest.started_at <= datetime.now()
