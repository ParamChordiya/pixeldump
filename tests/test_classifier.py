"""Tests for pixeldump.core.classifier."""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

from pixeldump.core.classifier import (
    classify_clusters,
    sample_photos_for_cluster,
)
from pixeldump.core.types import (
    Classification,
    EventCluster,
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


def _make_cluster(cluster_id: str, count: int) -> EventCluster:
    photos = [_make_photo(i) for i in range(count)]
    if photos:
        date_start = photos[0].date_taken
        date_end = photos[-1].date_taken
        assert date_start is not None
        assert date_end is not None
    else:
        date_start = datetime(2024, 3, 15)
        date_end = datetime(2024, 3, 15)
    return EventCluster(
        cluster_id=cluster_id,
        photos=photos,
        date_start=date_start,
        date_end=date_end,
    )


def _to_input(m: PhotoMetadata) -> PhotoInput:
    return PhotoInput(
        metadata=m,
        thumbnail_bytes=b"fake",
        thumbnail_media_type="image/jpeg",
    )


def test_sample_photos_returns_all_when_under_limit() -> None:
    cluster = _make_cluster("c1", 3)
    result = sample_photos_for_cluster(cluster, max_samples=5)
    assert len(result) == 3
    assert result == cluster.photos


def test_sample_photos_picks_first_middle_last() -> None:
    cluster = _make_cluster("c1", 10)
    result = sample_photos_for_cluster(cluster, max_samples=3)
    assert len(result) == 3
    assert result[0] is cluster.photos[0]
    assert result[-1] is cluster.photos[9]
    middle = cluster.photos.index(result[1])
    assert middle in (4, 5)


def test_sample_photos_returns_max_samples() -> None:
    cluster = _make_cluster("c1", 10)
    result = sample_photos_for_cluster(cluster, max_samples=5)
    assert len(result) == 5
    assert len({id(p) for p in result}) == 5


def test_sample_photos_no_date_cluster_takes_first_n() -> None:
    cluster = _make_cluster("no_date", 12)
    result = sample_photos_for_cluster(cluster, max_samples=4)
    assert result == cluster.photos[:4]


def test_sample_photos_returns_in_date_order() -> None:
    cluster = _make_cluster("c1", 8)
    result = sample_photos_for_cluster(cluster, max_samples=4)
    dates = [p.date_taken for p in result]
    assert dates == sorted(dates)  # type: ignore[type-var]


def test_classify_clusters_calls_provider_per_cluster() -> None:
    clusters = [_make_cluster(f"c{i}", 4) for i in range(3)]
    provider = MagicMock(spec=VisionProvider)
    provider.classify_cluster.return_value = Classification(
        category="travel",
        subcategory="city_break",
        confidence=0.9,
        description="x",
        notable=[],
    )
    result = classify_clusters(clusters, provider, _to_input, concurrency=1)
    assert provider.classify_cluster.call_count == 3
    assert set(result.keys()) == {"c0", "c1", "c2"}


def test_classify_clusters_falls_back_on_exception() -> None:
    clusters = [_make_cluster("c1", 4)]
    provider = MagicMock(spec=VisionProvider)
    provider.classify_cluster.side_effect = RuntimeError("boom")
    result = classify_clusters(clusters, provider, _to_input, concurrency=1)
    assert "c1" in result
    assert result["c1"].category == "uncategorized"
    assert result["c1"].confidence == 0.0
    assert result["c1"].description == "classifier error"


def test_classify_clusters_validates_taxonomy() -> None:
    clusters = [_make_cluster("c1", 4)]
    provider = MagicMock(spec=VisionProvider)
    provider.classify_cluster.return_value = Classification(
        category="not_a_real_category",
        subcategory="nope",
        confidence=0.95,
        description="oops",
        notable=[],
    )
    result = classify_clusters(clusters, provider, _to_input, concurrency=1)
    assert result["c1"].category == "uncategorized"
    assert result["c1"].confidence == 0.0


def test_classify_clusters_returns_dict_keyed_by_cluster_id() -> None:
    clusters = [
        _make_cluster("alpha", 3),
        _make_cluster("beta", 3),
    ]
    provider = MagicMock(spec=VisionProvider)
    provider.classify_cluster.return_value = Classification(
        category="everyday",
        subcategory="random",
        confidence=0.7,
        description="d",
        notable=[],
    )
    result = classify_clusters(clusters, provider, _to_input, concurrency=2)
    assert isinstance(result, dict)
    assert set(result.keys()) == {"alpha", "beta"}
    for v in result.values():
        assert isinstance(v, Classification)


def test_classify_clusters_passes_photo_inputs_to_provider() -> None:
    clusters = [_make_cluster("c1", 5)]
    provider = MagicMock(spec=VisionProvider)
    provider.classify_cluster.return_value = Classification(
        category="travel",
        subcategory=None,
        confidence=0.8,
        description="d",
        notable=[],
    )
    classify_clusters(clusters, provider, _to_input, batch_size=3, concurrency=1)
    args, _ = provider.classify_cluster.call_args
    sent_inputs = args[0]
    assert len(sent_inputs) == 3
    for pi in sent_inputs:
        assert isinstance(pi, PhotoInput)
        assert pi.thumbnail_bytes == b"fake"
