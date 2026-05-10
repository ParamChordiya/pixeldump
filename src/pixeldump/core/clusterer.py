"""Group photos into event clusters by time + (optionally) GPS. Phase 3."""
from __future__ import annotations

import math
from datetime import datetime, timedelta

from pixeldump.core.types import EventCluster, GPSCoord, PhotoMetadata

_EARTH_RADIUS_KM = 6371.0088
_LARGE_CLUSTER_THRESHOLD = 100
_DAY_SPLIT_MIN_SPAN = timedelta(hours=24)


def _haversine_km(a: GPSCoord, b: GPSCoord) -> float:
    """Great-circle distance in kilometers between two GPS coordinates."""
    lat1 = math.radians(a.lat)
    lat2 = math.radians(b.lat)
    dlat = lat2 - lat1
    dlon = math.radians(b.lon - a.lon)
    h = math.sin(dlat / 2.0) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2.0) ** 2
    return 2.0 * _EARTH_RADIUS_KM * math.asin(math.sqrt(h))


def _centroid(coords: list[GPSCoord]) -> GPSCoord | None:
    """Arithmetic mean of GPS coordinates. None for empty input."""
    if not coords:
        return None
    n = len(coords)
    lat = sum(c.lat for c in coords) / n
    lon = sum(c.lon for c in coords) / n
    return GPSCoord(lat=lat, lon=lon)


def _make_cluster_id(date_start: datetime, suffix_index: int) -> str:
    """Stable cluster ID like '2024-03-15_a', '2024-03-15_b', ... 'aa', 'ab', ..."""
    date_part = date_start.date().isoformat()
    suffix = _index_to_suffix(suffix_index)
    return f"{date_part}_{suffix}"


def _index_to_suffix(idx: int) -> str:
    """0 -> 'a', 1 -> 'b', ..., 25 -> 'z', 26 -> 'aa', 27 -> 'ab', ..."""
    if idx < 0:
        raise ValueError("suffix index must be non-negative")
    letters: list[str] = []
    n = idx
    while True:
        letters.append(chr(ord("a") + (n % 26)))
        n = n // 26 - 1
        if n < 0:
            break
    return "".join(reversed(letters))


def _temporal_split(
    sorted_photos: list[PhotoMetadata], burst_hours: int
) -> list[list[PhotoMetadata]]:
    """Split chronologically sorted photos by gaps exceeding burst_hours."""
    if not sorted_photos:
        return []
    threshold = timedelta(hours=burst_hours)
    groups: list[list[PhotoMetadata]] = [[sorted_photos[0]]]
    for prev, curr in zip(sorted_photos, sorted_photos[1:], strict=False):
        # date_taken is guaranteed non-None for clustering input here
        assert prev.date_taken is not None
        assert curr.date_taken is not None
        if curr.date_taken - prev.date_taken > threshold:
            groups.append([curr])
        else:
            groups[-1].append(curr)
    return groups


def _date_center(photos: list[PhotoMetadata]) -> datetime | None:
    """Return the midpoint datetime of a list of dated photos."""
    dates = [p.date_taken for p in photos if p.date_taken is not None]
    if not dates:
        return None
    start = min(dates)
    end = max(dates)
    return start + (end - start) / 2


def _gps_subsplit(
    photos: list[PhotoMetadata], gps_radius_km: float
) -> list[list[PhotoMetadata]]:
    """Sub-split a temporal cluster by GPS proximity (greedy)."""
    gps_photos = [p for p in photos if p.gps is not None]
    if not gps_photos:
        return [photos]

    # Greedy assignment of GPS-tagged photos to running centroids.
    sub_coords: list[list[GPSCoord]] = []
    sub_groups: list[list[PhotoMetadata]] = []

    for p in gps_photos:
        assert p.gps is not None
        placed = False
        for i, coords in enumerate(sub_coords):
            center = _centroid(coords)
            assert center is not None
            if _haversine_km(p.gps, center) <= gps_radius_km:
                sub_groups[i].append(p)
                sub_coords[i].append(p.gps)
                placed = True
                break
        if not placed:
            sub_groups.append([p])
            sub_coords.append([p.gps])

    # Assign GPS-less photos in this cluster to the temporally nearest sub-cluster.
    no_gps_photos = [p for p in photos if p.gps is None]
    centers: list[datetime | None] = [_date_center(g) for g in sub_groups]

    for p in no_gps_photos:
        if p.date_taken is None:
            # Shouldn't reach here (no_date go elsewhere) but stay safe.
            sub_groups[0].append(p)
            continue
        best_idx = 0
        best_delta: timedelta | None = None
        for i, c in enumerate(centers):
            if c is None:
                continue
            delta = abs(p.date_taken - c)
            if best_delta is None or delta < best_delta:
                best_delta = delta
                best_idx = i
        sub_groups[best_idx].append(p)

    # Sort each sub-group by date for determinism.
    for g in sub_groups:
        g.sort(key=lambda x: (x.date_taken or datetime.min, str(x.path)))

    return sub_groups


def _day_split_if_large(group: list[PhotoMetadata]) -> list[list[PhotoMetadata]]:
    """Split very large multi-day clusters by calendar day."""
    if len(group) < _LARGE_CLUSTER_THRESHOLD:
        return [group]
    dates = [p.date_taken for p in group if p.date_taken is not None]
    if len(dates) < 2:
        return [group]
    span = max(dates) - min(dates)
    if span <= _DAY_SPLIT_MIN_SPAN:
        return [group]

    by_day: dict[str, list[PhotoMetadata]] = {}
    for p in group:
        key = "no_date" if p.date_taken is None else p.date_taken.date().isoformat()
        by_day.setdefault(key, []).append(p)

    # Stable: order by day key (ISO sorts chronologically); 'no_date' sorts last alphabetically.
    return [by_day[k] for k in sorted(by_day.keys())]


def _build_event_cluster(
    photos: list[PhotoMetadata], cluster_id: str
) -> EventCluster:
    """Build an EventCluster from a list of photos (must be non-empty, all dated)."""
    ordered = sorted(
        photos, key=lambda p: (p.date_taken or datetime.min, str(p.path))
    )
    dated = [p.date_taken for p in ordered if p.date_taken is not None]
    date_start = min(dated)
    date_end = max(dated)
    gps_coords = [p.gps for p in ordered if p.gps is not None]
    gps_center = _centroid(gps_coords)
    return EventCluster(
        cluster_id=cluster_id,
        photos=ordered,
        date_start=date_start,
        date_end=date_end,
        gps_center=gps_center,
    )


def cluster(
    photos: list[PhotoMetadata],
    burst_hours: int = 72,
    gps_radius_km: float = 50.0,
) -> list[EventCluster]:
    """Cluster photos into events using time gaps and (when available) GPS proximity."""
    if not photos:
        return []

    dated = [p for p in photos if p.date_taken is not None]
    undated = [p for p in photos if p.date_taken is None]

    results: list[EventCluster] = []

    if dated:
        dated_sorted = sorted(
            dated, key=lambda p: (p.date_taken or datetime.min, str(p.path))
        )
        temporal_groups = _temporal_split(dated_sorted, burst_hours)

        # Apply GPS sub-splitting then day-splitting.
        all_groups: list[list[PhotoMetadata]] = []
        for tg in temporal_groups:
            for sg in _gps_subsplit(tg, gps_radius_km):
                all_groups.extend(_day_split_if_large(sg))

        # Build clusters with deterministic, chronological IDs.
        # Sort groups by their start time so IDs are in chronological order.
        all_groups_sorted = sorted(
            all_groups,
            key=lambda g: min(
                (p.date_taken for p in g if p.date_taken is not None),
                default=datetime.min,
            ),
        )

        per_day_count: dict[str, int] = {}
        for group in all_groups_sorted:
            tmp = _build_event_cluster(group, cluster_id="")
            day_key = tmp.date_start.date().isoformat()
            idx = per_day_count.get(day_key, 0)
            per_day_count[day_key] = idx + 1
            cluster_id = _make_cluster_id(tmp.date_start, idx)
            results.append(
                EventCluster(
                    cluster_id=cluster_id,
                    photos=tmp.photos,
                    date_start=tmp.date_start,
                    date_end=tmp.date_end,
                    gps_center=tmp.gps_center,
                )
            )

    if undated:
        gps_coords = [p.gps for p in undated if p.gps is not None]
        results.append(
            EventCluster(
                cluster_id="no_date",
                photos=list(undated),
                date_start=datetime.min,
                date_end=datetime.min,
                gps_center=_centroid(gps_coords),
            )
        )

    return results
