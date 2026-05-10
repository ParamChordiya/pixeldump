"""Tests for pixeldump.core.namer."""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

from pixeldump.core.namer import name_cluster, sanitize_name
from pixeldump.core.types import (
    Classification,
    EventCluster,
    FolderName,
    NamingMode,
    PhotoInput,
    PhotoMetadata,
)
from pixeldump.providers.base import VisionProvider


def _make_photo(i: int) -> PhotoMetadata:
    return PhotoMetadata(
        path=Path(f"/tmp/photo_{i:04d}.jpg"),
        date_taken=datetime(2024, 3, 15, 12, 0, 0) + timedelta(minutes=i),
        gps=None,
        camera_model=None,
        width=4000,
        height=3000,
        file_size=1_000_000,
    )


def _make_cluster(
    cluster_id: str = "c1",
    count: int = 5,
    date_start: datetime | None = None,
) -> EventCluster:
    photos = [_make_photo(i) for i in range(count)]
    start = date_start or datetime(2024, 3, 15, 12, 0, 0)
    end = start + timedelta(minutes=max(0, count - 1))
    return EventCluster(
        cluster_id=cluster_id,
        photos=photos,
        date_start=start,
        date_end=end,
    )


def _to_input(m: PhotoMetadata) -> PhotoInput:
    return PhotoInput(
        metadata=m,
        thumbnail_bytes=b"fake",
        thumbnail_media_type="image/jpeg",
    )


def _classification(
    category: str = "travel",
    subcategory: str | None = "city_break",
    confidence: float = 0.9,
) -> Classification:
    return Classification(
        category=category,
        subcategory=subcategory,
        confidence=confidence,
        description="d",
        notable=[],
    )


# --- sanitize_name -------------------------------------------------------


def test_sanitize_lowercases_and_underscores() -> None:
    assert sanitize_name("Japan Trip") == "japan_trip"


def test_sanitize_strips_emojis() -> None:
    assert sanitize_name("ate good 🍕 in tokyo") == "ate_good_in_tokyo"


def test_sanitize_clamps_to_40_chars() -> None:
    long_name = "a" * 60
    result = sanitize_name(long_name)
    assert len(result) == 40
    assert result == "a" * 40


def test_sanitize_collapses_repeated_underscores() -> None:
    assert sanitize_name("a___b") == "a_b"


def test_sanitize_strips_leading_trailing_underscores() -> None:
    assert sanitize_name("__hello_world__") == "hello_world"


def test_sanitize_empty_returns_untitled() -> None:
    assert sanitize_name("") == "untitled_event"


def test_sanitize_only_emojis_returns_untitled() -> None:
    assert sanitize_name("🍕🎉🚀") == "untitled_event"


# --- name_cluster --------------------------------------------------------


def test_name_cluster_no_date_routed_to_review() -> None:
    cluster = _make_cluster(cluster_id="no_date", count=3)
    provider = MagicMock(spec=VisionProvider)
    classification = _classification()
    result = name_cluster(
        cluster, classification, provider, NamingMode.CHAOTIC, _to_input
    )
    assert result == FolderName(name="no_date", date_prefix="_review")
    provider.name_event.assert_not_called()


def test_name_cluster_low_confidence_routed_to_review() -> None:
    cluster = _make_cluster()
    provider = MagicMock(spec=VisionProvider)
    classification = _classification(confidence=0.3)
    result = name_cluster(
        cluster, classification, provider, NamingMode.CHAOTIC, _to_input
    )
    assert result == FolderName(name="low_confidence", date_prefix="_review")
    provider.name_event.assert_not_called()


def test_name_cluster_screenshot_routed_to_year_screenshots() -> None:
    cluster = _make_cluster(date_start=datetime(2024, 3, 15))
    provider = MagicMock(spec=VisionProvider)
    classification = _classification(
        category="documents",
        subcategory="screenshot",
        confidence=0.9,
    )
    result = name_cluster(
        cluster, classification, provider, NamingMode.CHAOTIC, _to_input
    )
    assert result == FolderName(name="screenshots", date_prefix="2024")
    provider.name_event.assert_not_called()


def test_name_cluster_normal_path() -> None:
    cluster = _make_cluster(date_start=datetime(2024, 3, 5))
    provider = MagicMock(spec=VisionProvider)
    provider.name_event.return_value = "Ate Good In Tokyo"
    classification = _classification(category="travel", confidence=0.9)
    result = name_cluster(
        cluster, classification, provider, NamingMode.CHAOTIC, _to_input
    )
    assert result.name == "ate_good_in_tokyo"
    assert result.date_prefix == "2024_03"


def test_name_cluster_empty_provider_response_falls_back() -> None:
    cluster = _make_cluster(date_start=datetime(2024, 3, 5))
    provider = MagicMock(spec=VisionProvider)
    provider.name_event.return_value = ""
    classification = _classification(category="travel", confidence=0.9)
    result = name_cluster(
        cluster, classification, provider, NamingMode.CHAOTIC, _to_input
    )
    assert result.name == "travel_event"
    assert result.date_prefix == "2024_03"


def test_name_cluster_all_emoji_provider_response_falls_back() -> None:
    cluster = _make_cluster(date_start=datetime(2024, 3, 5))
    provider = MagicMock(spec=VisionProvider)
    provider.name_event.return_value = "🍕🎉🚀"
    classification = _classification(category="social", confidence=0.9)
    result = name_cluster(
        cluster, classification, provider, NamingMode.CHAOTIC, _to_input
    )
    assert result.name == "social_event"


def test_name_cluster_calls_provider_with_correct_mode() -> None:
    cluster = _make_cluster(date_start=datetime(2024, 3, 5))
    provider = MagicMock(spec=VisionProvider)
    provider.name_event.return_value = "wild night"
    classification = _classification(category="social", confidence=0.9)
    name_cluster(
        cluster, classification, provider, NamingMode.UNHINGED, _to_input
    )
    args, _ = provider.name_event.call_args
    assert args[1] == "social"
    assert args[2] == NamingMode.UNHINGED
