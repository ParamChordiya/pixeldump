"""Classify event clusters via a VisionProvider. Phase 4."""
from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from pixeldump.core.taxonomy import is_valid_category
from pixeldump.core.types import (
    Classification,
    EventCluster,
    PhotoInput,
    PhotoMetadata,
)
from pixeldump.providers.base import VisionProvider


def classify_clusters(
    clusters: list[EventCluster],
    provider: VisionProvider,
    to_input_fn: Callable[[PhotoMetadata], PhotoInput],
    batch_size: int = 5,
    concurrency: int = 4,
) -> dict[str, Classification]:
    """Classify each cluster (keyed by cluster_id) using the given provider.

    Runs cluster classifications concurrently via a thread pool (provider calls
    are I/O-bound). Per-cluster failures fall back to an `uncategorized`
    Classification so one bad cluster does not sink the whole run.
    """

    def _classify_one(cluster: EventCluster) -> tuple[str, Classification]:
        try:
            sampled = sample_photos_for_cluster(cluster, max_samples=batch_size)
            inputs = [to_input_fn(m) for m in sampled]
            classification = provider.classify_cluster(inputs)
            if not is_valid_category(classification.category):
                classification = Classification(
                    category="uncategorized",
                    subcategory=classification.subcategory,
                    confidence=0.0,
                    description=classification.description,
                    notable=classification.notable,
                )
            return cluster.cluster_id, classification
        except Exception:
            fallback = Classification(
                category="uncategorized",
                subcategory=None,
                confidence=0.0,
                description="classifier error",
                notable=[],
            )
            return cluster.cluster_id, fallback

    results: dict[str, Classification] = {}
    if not clusters:
        return results

    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        for cluster_id, classification in pool.map(_classify_one, clusters):
            results[cluster_id] = classification
    return results


def sample_photos_for_cluster(
    cluster: EventCluster,
    max_samples: int = 5,
) -> list[PhotoMetadata]:
    """Pick representative photos from a cluster for LLM input.

    - If the cluster has <= max_samples photos, return all of them.
    - Otherwise, pick first, last, middle, plus evenly-spaced photos in between
      (deduplicated, preserving date_taken order).
    - For the special `no_date` cluster, just return the first `max_samples` photos.
    """
    photos = cluster.photos
    n = len(photos)
    if n == 0 or max_samples <= 0:
        return []

    if cluster.cluster_id == "no_date":
        return list(photos[:max_samples])

    if n <= max_samples:
        return list(photos)

    # Pick max_samples evenly-spaced indices over [0, n-1], guaranteeing 0 and n-1.
    if max_samples == 1:
        chosen_indices = [0]
    else:
        chosen_indices = []
        for i in range(max_samples):
            idx = round(i * (n - 1) / (max_samples - 1))
            chosen_indices.append(idx)

    # Dedupe while preserving order
    seen: set[int] = set()
    unique_indices: list[int] = []
    for idx in chosen_indices:
        if idx not in seen:
            seen.add(idx)
            unique_indices.append(idx)

    unique_indices.sort()
    return [photos[i] for i in unique_indices]
