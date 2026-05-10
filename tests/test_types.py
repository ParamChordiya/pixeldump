"""Smoke test: instantiate every public type. Proves the contract compiles."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from pixeldump.core.types import (
    Classification,
    CostEstimate,
    DuplicateGroup,
    EventCluster,
    FolderName,
    GPSCoord,
    LibraryStats,
    MoveOperation,
    NamingMode,
    Phase,
    PhotoInput,
    PhotoMetadata,
    PipelineConfig,
    ProviderName,
    RunManifest,
    ScanResult,
)
from pixeldump.providers.base import VisionProvider


def test_enums() -> None:
    assert NamingMode.CHAOTIC.value == "chaotic"
    assert ProviderName.AUTO.value == "auto"
    assert Phase.SETUP.value == "setup"


def test_gps_coord_frozen() -> None:
    g = GPSCoord(lat=37.7, lon=-122.4)
    assert g.lat == 37.7


def test_photo_metadata_defaults() -> None:
    p = PhotoMetadata(
        path=Path("/tmp/x.jpg"),
        date_taken=None,
        gps=None,
        camera_model=None,
        width=100,
        height=100,
        file_size=1024,
    )
    assert p.sha256 is None
    assert p.phash is None
    assert p.is_video is False


def test_photo_input() -> None:
    meta = PhotoMetadata(
        path=Path("/tmp/x.jpg"),
        date_taken=None,
        gps=None,
        camera_model=None,
        width=10,
        height=10,
        file_size=1,
    )
    pi = PhotoInput(metadata=meta, thumbnail_bytes=b"\xff\xd8\xff")
    assert pi.thumbnail_media_type == "image/jpeg"


def test_event_cluster() -> None:
    now = datetime(2024, 3, 15, 12, 0)
    c = EventCluster(cluster_id="2024-03-15_a", photos=[], date_start=now, date_end=now)
    assert c.gps_center is None


def test_classification_default_notable() -> None:
    cl = Classification(
        category="travel",
        subcategory="beach_trip",
        confidence=0.9,
        description="beach vibes",
    )
    assert cl.notable == []


def test_folder_name_full() -> None:
    f = FolderName(name="ate_good_in_tokyo", date_prefix="2024_03")
    assert f.full == "2024_03_ate_good_in_tokyo"


def test_cost_estimate_frozen() -> None:
    ce = CostEstimate(
        estimated_usd=1.23,
        estimated_input_tokens=100,
        estimated_output_tokens=50,
        photo_count=10,
    )
    assert ce.estimated_usd == 1.23


def test_library_stats_defaults() -> None:
    s = LibraryStats()
    assert s.total_photos == 0
    assert s.notable_findings == []


def test_scan_result() -> None:
    sr = ScanResult(
        photos=[], videos=[], skipped=[], total_size_bytes=0, format_breakdown={}
    )
    assert sr.format_breakdown == {}


def test_duplicate_group() -> None:
    meta = PhotoMetadata(
        path=Path("/x.jpg"),
        date_taken=None,
        gps=None,
        camera_model=None,
        width=1,
        height=1,
        file_size=1,
    )
    dg = DuplicateGroup(kept=meta, duplicates=[], reason="exact_duplicate", max_hash_distance=0)
    assert dg.reason == "exact_duplicate"


def test_move_operation() -> None:
    op = MoveOperation(
        action="move",
        source=Path("/a.jpg"),
        destination=Path("/b.jpg"),
        timestamp=datetime.now(),
    )
    assert op.classification is None
    assert op.reason is None


def test_run_manifest_defaults() -> None:
    rm = RunManifest(
        version="1.0",
        run_id="20260509_143022",
        provider="claude",
        naming_mode="chaotic",
        started_at=datetime.now(),
        completed_at=None,
    )
    assert rm.operations == []
    assert isinstance(rm.stats, LibraryStats)


def test_pipeline_config_defaults() -> None:
    pc = PipelineConfig(
        target_dir=Path("/x"),
        provider=ProviderName.AUTO,
        naming_mode=NamingMode.CHAOTIC,
        sass_level=2,
    )
    assert pc.burst_hours == 72
    assert pc.batch_size == 5
    assert pc.dry_run is True
    assert pc.output_dir is None


def test_vision_provider_is_abstract() -> None:
    # Cannot instantiate ABC directly.
    try:
        VisionProvider()  # type: ignore[abstract]
    except TypeError:
        return
    raise AssertionError("VisionProvider should be abstract")
