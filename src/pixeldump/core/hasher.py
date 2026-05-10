"""Compute SHA-256 + perceptual hashes and detect duplicate groups. Phase 2."""
from __future__ import annotations

import hashlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import imagehash
import pillow_heif
from PIL import Image

from pixeldump.core.types import DuplicateGroup, PhotoMetadata

# Register HEIC/HEIF support for Pillow at import time.
pillow_heif.register_heif_opener()

_CHUNK_SIZE = 64 * 1024


def compute_sha256(path: Path) -> str:
    """Hex-encoded SHA-256 of the file at `path`."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(_CHUNK_SIZE)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def compute_phash(path: Path) -> str:
    """Hex-encoded perceptual hash (pHash) of the image at `path`."""
    with Image.open(path) as img:
        return str(imagehash.phash(img))


def hash_all(photos: list[PhotoMetadata], concurrency: int = 4) -> list[PhotoMetadata]:
    """Populate sha256 + phash on each photo. Returns the same list, mutated."""

    # Thread pool: Pillow releases the GIL during decode and hashlib does so on
    # large reads, so threads avoid the pickling cost a process pool would
    # impose on PhotoMetadata mutation.
    def _hash_one(photo: PhotoMetadata) -> None:
        try:
            photo.sha256 = compute_sha256(photo.path)
        except Exception:
            photo.sha256 = None
        if photo.is_video:
            # phash needs a decodable still image; leave None for videos.
            return
        try:
            photo.phash = compute_phash(photo.path)
        except Exception:
            photo.phash = None

    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        list(pool.map(_hash_one, photos))

    return photos


def _pick_kept(photos: list[PhotoMetadata]) -> PhotoMetadata:
    """Highest resolution; tiebreak file_size desc, then path lexicographic asc."""
    # Sort: (-resolution, -file_size, path_str). First element wins.
    return sorted(
        photos,
        key=lambda p: (-(p.width * p.height), -p.file_size, str(p.path)),
    )[0]


def find_duplicates(
    photos: list[PhotoMetadata],
    near_duplicate_threshold: int = 5,
) -> list[DuplicateGroup]:
    """Group exact + near-duplicate photos. `near_duplicate_threshold` is max pHash Hamming distance."""
    groups: list[DuplicateGroup] = []
    in_exact_group: set[int] = set()  # ids of PhotoMetadata already grouped exactly

    # --- Pass 1: exact (sha256) ---
    by_sha: dict[str, list[PhotoMetadata]] = {}
    for photo in photos:
        if photo.sha256 is None:
            continue
        by_sha.setdefault(photo.sha256, []).append(photo)

    for bucket in by_sha.values():
        if len(bucket) < 2:
            continue
        kept = _pick_kept(bucket)
        dupes = [p for p in bucket if p is not kept]
        groups.append(
            DuplicateGroup(
                kept=kept,
                duplicates=dupes,
                reason="exact_duplicate",
                max_hash_distance=0,
            )
        )
        for p in bucket:
            in_exact_group.add(id(p))

    # --- Pass 2: near (phash) ---
    # TODO: BK-tree for libraries >5k photos
    candidates: list[PhotoMetadata] = [
        p for p in photos if id(p) not in in_exact_group and p.phash is not None
    ]

    n = len(candidates)
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    # Pre-decode hashes once. (candidates filter guarantees phash is not None,
    # but mypy can't narrow through the comprehension.)
    hashes = [imagehash.hex_to_hash(p.phash) for p in candidates]  # type: ignore[arg-type]

    # Track max distance observed within each connected pair.
    pair_distances: dict[tuple[int, int], int] = {}
    for i in range(n):
        for j in range(i + 1, n):
            dist = int(hashes[i] - hashes[j])
            if dist <= near_duplicate_threshold:
                union(i, j)
                pair_distances[(i, j)] = dist

    clusters: dict[int, list[int]] = {}
    for i in range(n):
        clusters.setdefault(find(i), []).append(i)

    for indices in clusters.values():
        if len(indices) < 2:
            continue
        members = [candidates[i] for i in indices]
        kept = _pick_kept(members)
        dupes = [p for p in members if p is not kept]
        # Max distance within this cluster (across edges connecting its members).
        idx_set = set(indices)
        max_dist = 0
        for (i, j), d in pair_distances.items():
            if i in idx_set and j in idx_set and d > max_dist:
                max_dist = d
        groups.append(
            DuplicateGroup(
                kept=kept,
                duplicates=dupes,
                reason="near_duplicate",
                max_hash_distance=max_dist,
            )
        )

    return groups
