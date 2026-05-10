"""Tests for the event clusterer."""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from pixeldump.core.clusterer import (
    _centroid,
    _haversine_km,
    _make_cluster_id,
    cluster,
)
from pixeldump.core.types import GPSCoord, PhotoMetadata


def make_photo(
    date: datetime | None,
    gps: GPSCoord | None = None,
    path: str = "/fake.jpg",
) -> PhotoMetadata:
    return PhotoMetadata(
        path=Path(path),
        date_taken=date,
        gps=gps,
        camera_model=None,
        width=100,
        height=100,
        file_size=1000,
    )


# --- Basic cases ------------------------------------------------------------


def test_empty_input_returns_empty_list() -> None:
    assert cluster([]) == []


def test_single_photo_one_cluster() -> None:
    p = make_photo(datetime(2024, 3, 15, 10, 0))
    result = cluster([p])
    assert len(result) == 1
    assert result[0].photos == [p]
    assert result[0].date_start == datetime(2024, 3, 15, 10, 0)
    assert result[0].date_end == datetime(2024, 3, 15, 10, 0)
    assert result[0].gps_center is None


# --- Temporal clustering ----------------------------------------------------


def test_temporal_gap_splits_clusters() -> None:
    p1 = make_photo(datetime(2024, 3, 15, 12, 0), path="/a.jpg")
    p2 = make_photo(datetime(2024, 3, 20, 12, 0), path="/b.jpg")  # 5 days later
    result = cluster([p1, p2])
    assert len(result) == 2
    assert result[0].photos == [p1]
    assert result[1].photos == [p2]


def test_no_temporal_split_within_burst() -> None:
    base = datetime(2024, 3, 15, 0, 0)
    photos = [
        make_photo(base + timedelta(hours=h), path=f"/{h}.jpg")
        for h in (0, 12, 24, 48)
    ]
    result = cluster(photos)
    assert len(result) == 1
    assert len(result[0].photos) == 4


# --- No-date cluster --------------------------------------------------------


def test_no_date_photos_in_special_cluster() -> None:
    p1 = make_photo(None, path="/a.jpg")
    p2 = make_photo(None, path="/b.jpg")
    result = cluster([p1, p2])
    assert len(result) == 1
    assert result[0].cluster_id == "no_date"
    assert result[0].date_start == datetime.min
    assert result[0].date_end == datetime.min
    assert len(result[0].photos) == 2


def test_no_date_mixed_with_dated() -> None:
    p_dated = make_photo(datetime(2024, 3, 15, 12, 0), path="/dated.jpg")
    p_undated = make_photo(None, path="/undated.jpg")
    result = cluster([p_dated, p_undated])
    ids = {c.cluster_id for c in result}
    assert "no_date" in ids
    assert any(c.cluster_id != "no_date" for c in result)


# --- GPS sub-splitting ------------------------------------------------------


def test_gps_split_within_temporal_cluster() -> None:
    nyc = GPSCoord(lat=40.7128, lon=-74.0060)
    tokyo = GPSCoord(lat=35.6762, lon=139.6503)
    base = datetime(2024, 3, 15, 9, 0)
    photos = [
        make_photo(base, nyc, path="/nyc1.jpg"),
        make_photo(base + timedelta(minutes=10), nyc, path="/nyc2.jpg"),
        make_photo(base + timedelta(minutes=20), tokyo, path="/tk1.jpg"),
        make_photo(base + timedelta(minutes=30), tokyo, path="/tk2.jpg"),
    ]
    result = cluster(photos)
    assert len(result) == 2
    sizes = sorted(len(c.photos) for c in result)
    assert sizes == [2, 2]


def test_gps_no_split_when_close() -> None:
    base_coord = GPSCoord(lat=40.7128, lon=-74.0060)
    nearby = GPSCoord(lat=40.7228, lon=-74.0160)  # ~ 1.4 km away
    base = datetime(2024, 3, 15, 9, 0)
    photos = [
        make_photo(base + timedelta(minutes=i * 5), base_coord, path=f"/a{i}.jpg")
        for i in range(2)
    ] + [
        make_photo(base + timedelta(minutes=20 + i * 5), nearby, path=f"/b{i}.jpg")
        for i in range(2)
    ]
    result = cluster(photos)
    assert len(result) == 1
    assert len(result[0].photos) == 4


def test_gps_center_is_none_when_no_gps_photos() -> None:
    base = datetime(2024, 3, 15, 9, 0)
    photos = [
        make_photo(base + timedelta(minutes=i), path=f"/p{i}.jpg") for i in range(3)
    ]
    result = cluster(photos)
    assert len(result) == 1
    assert result[0].gps_center is None


def test_gps_center_is_centroid_of_gps_photos() -> None:
    a = GPSCoord(lat=40.0, lon=-74.0)
    b = GPSCoord(lat=40.2, lon=-74.2)
    base = datetime(2024, 3, 15, 9, 0)
    photos = [
        make_photo(base, a, path="/a.jpg"),
        make_photo(base + timedelta(minutes=5), b, path="/b.jpg"),
    ]
    result = cluster(photos)
    assert len(result) == 1
    assert result[0].gps_center is not None
    assert abs(result[0].gps_center.lat - 40.1) < 1e-9
    assert abs(result[0].gps_center.lon - -74.1) < 1e-9


# --- Cluster IDs ------------------------------------------------------------


def test_cluster_ids_unique_and_sorted() -> None:
    photos = [
        make_photo(datetime(2024, 3, 15, 12, 0), path="/a.jpg"),
        make_photo(datetime(2024, 3, 25, 12, 0), path="/b.jpg"),  # > 72h gap
        make_photo(datetime(2024, 4, 5, 12, 0), path="/c.jpg"),  # > 72h gap
    ]
    result = cluster(photos)
    ids = [c.cluster_id for c in result]
    assert len(ids) == len(set(ids))
    assert ids == sorted(ids)


def test_cluster_ids_same_day_get_letter_suffix() -> None:
    # Two clusters on the same calendar day via distinct GPS locations.
    nyc = GPSCoord(lat=40.7128, lon=-74.0060)
    tokyo = GPSCoord(lat=35.6762, lon=139.6503)
    day = datetime(2024, 3, 15, 9, 0)
    photos = [
        make_photo(day, nyc, path="/nyc.jpg"),
        make_photo(day + timedelta(minutes=15), tokyo, path="/tk.jpg"),
    ]
    result = cluster(photos)
    assert len(result) == 2
    ids = sorted(c.cluster_id for c in result)
    assert ids == ["2024-03-15_a", "2024-03-15_b"]


# --- Day-split for large multi-day clusters --------------------------------


def test_large_multiday_cluster_splits_by_day() -> None:
    base = datetime(2024, 3, 15, 0, 0)
    # 120 photos over 3 days: ~36 minutes each. No GPS, no >72h gaps.
    photos = [
        make_photo(base + timedelta(minutes=36 * i), path=f"/p{i}.jpg")
        for i in range(120)
    ]
    result = cluster(photos)
    # 36 min * 120 = 4320 min = 72 hours. Spread across 3 calendar days.
    assert len(result) == 3
    total = sum(len(c.photos) for c in result)
    assert total == 120


def test_large_cluster_under_24h_does_not_day_split() -> None:
    base = datetime(2024, 3, 15, 0, 0)
    # 120 photos packed into 12 hours.
    photos = [
        make_photo(base + timedelta(minutes=6 * i), path=f"/p{i}.jpg")
        for i in range(120)
    ]
    result = cluster(photos)
    assert len(result) == 1
    assert len(result[0].photos) == 120


def test_small_multiday_cluster_does_not_day_split() -> None:
    base = datetime(2024, 3, 15, 0, 0)
    # 10 photos spread over 2 days; under the 100-photo threshold.
    photos = [
        make_photo(base + timedelta(hours=4 * i), path=f"/p{i}.jpg")
        for i in range(10)
    ]
    result = cluster(photos)
    assert len(result) == 1


# --- Helpers ----------------------------------------------------------------


def test_haversine_known_distance() -> None:
    nyc = GPSCoord(lat=40.7128, lon=-74.0060)
    lax = GPSCoord(lat=33.9416, lon=-118.4085)
    d = _haversine_km(nyc, lax)
    assert abs(d - 3936) / 3936 < 0.01


def test_haversine_zero_for_same_point() -> None:
    a = GPSCoord(lat=10.0, lon=20.0)
    assert _haversine_km(a, a) == 0.0


def test_centroid_arithmetic_mean() -> None:
    coords = [
        GPSCoord(lat=0.0, lon=0.0),
        GPSCoord(lat=2.0, lon=4.0),
        GPSCoord(lat=4.0, lon=8.0),
    ]
    c = _centroid(coords)
    assert c is not None
    assert abs(c.lat - 2.0) < 1e-9
    assert abs(c.lon - 4.0) < 1e-9


def test_centroid_empty_returns_none() -> None:
    assert _centroid([]) is None


def test_make_cluster_id_letters() -> None:
    d = datetime(2024, 3, 15, 9, 0)
    assert _make_cluster_id(d, 0) == "2024-03-15_a"
    assert _make_cluster_id(d, 1) == "2024-03-15_b"
    assert _make_cluster_id(d, 25) == "2024-03-15_z"
    assert _make_cluster_id(d, 26) == "2024-03-15_aa"
    assert _make_cluster_id(d, 27) == "2024-03-15_ab"


# --- Sorting within clusters ------------------------------------------------


def test_photos_within_cluster_sorted_by_date() -> None:
    base = datetime(2024, 3, 15, 9, 0)
    p_late = make_photo(base + timedelta(hours=2), path="/late.jpg")
    p_early = make_photo(base, path="/early.jpg")
    p_mid = make_photo(base + timedelta(hours=1), path="/mid.jpg")
    result = cluster([p_late, p_early, p_mid])
    assert len(result) == 1
    assert result[0].photos == [p_early, p_mid, p_late]


def test_identical_timestamps_same_cluster() -> None:
    t = datetime(2024, 3, 15, 9, 0)
    photos = [make_photo(t, path=f"/p{i}.jpg") for i in range(3)]
    result = cluster(photos)
    assert len(result) == 1
    assert len(result[0].photos) == 3
