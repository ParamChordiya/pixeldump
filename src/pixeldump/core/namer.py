"""Turn classifications into Gen-Z-flavored folder names. Phase 5."""
from __future__ import annotations

import re
from collections.abc import Callable

from pixeldump.core.types import (
    Classification,
    EventCluster,
    FolderName,
    NamingMode,
    PhotoInput,
    PhotoMetadata,
)
from pixeldump.providers.base import VisionProvider

_UNTITLED = "untitled_event"
_ALLOWED_RE = re.compile(r"[^a-z0-9_]")
_UNDERSCORE_RUN_RE = re.compile(r"_+")
_WHITESPACE_RE = re.compile(r"\s+")
_MAX_NAME_LEN = 40


def _sample(cluster: EventCluster, n: int = 3) -> list[PhotoMetadata]:
    """Sample up to `n` photos from a cluster: first, middle, last.

    Local copy of the simple sampling algorithm to avoid a circular import
    with classifier.py.
    """
    photos = cluster.photos
    total = len(photos)
    if total == 0 or n <= 0:
        return []
    if total <= n:
        return list(photos)
    if n == 1:
        return [photos[0]]
    indices: list[int] = []
    for i in range(n):
        idx = round(i * (total - 1) / (n - 1))
        indices.append(idx)
    seen: set[int] = set()
    unique: list[int] = []
    for idx in indices:
        if idx not in seen:
            seen.add(idx)
            unique.append(idx)
    unique.sort()
    return [photos[i] for i in unique]


def name_cluster(
    cluster: EventCluster,
    classification: Classification,
    provider: VisionProvider,
    mode: NamingMode,
    to_input_fn: Callable[[PhotoMetadata], PhotoInput],
) -> FolderName:
    """Compose a FolderName for a single classified cluster."""
    # Special: no-date cluster routed to _review.
    if cluster.cluster_id == "no_date":
        return FolderName(name="no_date", date_prefix="_review")

    # Special: low-confidence routed to _review.
    if classification.confidence < 0.5:
        return FolderName(name="low_confidence", date_prefix="_review")

    # Special: screenshots land in {year}/screenshots/.
    if (
        classification.category == "documents"
        and classification.subcategory == "screenshot"
    ):
        return FolderName(
            name="screenshots",
            date_prefix=f"{cluster.date_start.year:04d}",
        )

    date_prefix = (
        f"{cluster.date_start.year:04d}_{cluster.date_start.month:02d}"
    )

    sampled = _sample(cluster, n=3)
    inputs = [to_input_fn(m) for m in sampled]
    raw = provider.name_event(inputs, classification.category, mode)

    sanitized = sanitize_name(raw)
    if sanitized == _UNTITLED:
        sanitized = sanitize_name(f"{classification.category}_event")

    return FolderName(name=sanitized, date_prefix=date_prefix)


def sanitize_name(name: str) -> str:
    """Lowercase, snake_case, strip emojis/special chars, clamp to 40 chars."""
    if not name:
        return _UNTITLED

    s = name.lower()
    # Replace whitespace runs with a single underscore first so word
    # boundaries are preserved before stripping disallowed characters.
    s = _WHITESPACE_RE.sub("_", s)
    # Strip everything that isn't ascii lowercase, digit, or underscore.
    s = _ALLOWED_RE.sub("", s)
    # Collapse repeated underscores.
    s = _UNDERSCORE_RUN_RE.sub("_", s)
    # Strip leading/trailing underscores.
    s = s.strip("_")
    # Clamp.
    if len(s) > _MAX_NAME_LEN:
        s = s[:_MAX_NAME_LEN].rstrip("_")

    if not s:
        return _UNTITLED
    return s
