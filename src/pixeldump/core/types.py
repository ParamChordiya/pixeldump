"""Frozen type contracts for PixelDump. Wave 2 agents depend on these signatures.

Do not modify any dataclass field, enum value, or class signature in this file
without coordinating with all downstream consumers.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path


class NamingMode(str, Enum):
    CORPORATE = "corporate"
    CHAOTIC = "chaotic"
    UNHINGED = "unhinged"


class ProviderName(str, Enum):
    CLAUDE = "claude"
    OLLAMA = "ollama"
    CLAUDE_CODE = "claude-code"
    AUTO = "auto"


class Phase(str, Enum):
    SETUP = "setup"
    SCANNING = "scanning"
    HASHING = "hashing"
    CLUSTERING = "clustering"
    CLASSIFYING = "classifying"
    MOVING = "moving"
    COMPLETE = "complete"


@dataclass(frozen=True, slots=True)
class GPSCoord:
    lat: float
    lon: float


@dataclass(slots=True)
class PhotoMetadata:
    path: Path                           # absolute path
    date_taken: datetime | None
    gps: GPSCoord | None
    camera_model: str | None
    width: int
    height: int
    file_size: int                       # bytes
    sha256: str | None = None            # populated by hasher
    phash: str | None = None             # populated by hasher
    is_video: bool = False


@dataclass(slots=True)
class PhotoInput:
    """A photo prepared for LLM consumption (thumbnail in memory)."""
    metadata: PhotoMetadata
    thumbnail_bytes: bytes               # JPEG-encoded, max 512px on longest side
    thumbnail_media_type: str = "image/jpeg"


@dataclass(slots=True)
class EventCluster:
    cluster_id: str                      # stable ID (e.g., "2024-03-15_a")
    photos: list[PhotoMetadata]
    date_start: datetime
    date_end: datetime
    gps_center: GPSCoord | None = None


@dataclass(slots=True)
class Classification:
    category: str                        # primary taxonomy key
    subcategory: str | None
    confidence: float                    # 0.0..1.0
    description: str
    notable: list[str] = field(default_factory=list)  # e.g., ["cat spotted in photo 3"]


@dataclass(slots=True)
class FolderName:
    name: str                            # e.g., "ate_good_in_tokyo" (no date prefix yet)
    date_prefix: str                     # e.g., "2024_03"

    @property
    def full(self) -> str:
        return f"{self.date_prefix}_{self.name}"


@dataclass(frozen=True, slots=True)
class CostEstimate:
    estimated_usd: float
    estimated_input_tokens: int
    estimated_output_tokens: int
    photo_count: int


@dataclass(slots=True)
class LibraryStats:
    total_photos: int = 0
    sorted: int = 0
    duplicates: int = 0
    screenshots: int = 0
    cats: int = 0
    food: int = 0
    selfies: int = 0
    needs_review: int = 0
    folders_created: int = 0
    elapsed_seconds: float = 0.0
    cost_usd: float = 0.0
    notable_findings: list[str] = field(default_factory=list)  # for the roast


@dataclass(slots=True)
class ScanResult:
    photos: list[PhotoMetadata]
    videos: list[PhotoMetadata]          # is_video=True
    skipped: list[Path]
    total_size_bytes: int
    format_breakdown: dict[str, int]     # {".jpg": 1234, ...}


@dataclass(slots=True)
class DuplicateGroup:
    """Group of duplicate photos. `kept` is the highest-resolution version."""
    kept: PhotoMetadata
    duplicates: list[PhotoMetadata]
    reason: str                          # "exact_duplicate" | "near_duplicate"
    max_hash_distance: int               # 0 for exact


@dataclass(slots=True)
class MoveOperation:
    action: str                          # "move"
    source: Path
    destination: Path
    timestamp: datetime
    classification: Classification | None = None
    reason: str | None = None            # e.g., "duplicate", "no_date", "low_confidence"


@dataclass(slots=True)
class RunManifest:
    version: str                         # "1.0"
    run_id: str                          # e.g., "20260509_143022"
    provider: str
    naming_mode: str
    started_at: datetime
    completed_at: datetime | None
    operations: list[MoveOperation] = field(default_factory=list)
    stats: LibraryStats = field(default_factory=LibraryStats)


@dataclass(slots=True)
class PipelineConfig:
    """Per-run config passed through the pipeline."""
    target_dir: Path
    provider: ProviderName
    naming_mode: NamingMode
    sass_level: int                      # 0..3
    burst_hours: int = 72
    batch_size: int = 5
    concurrency: int = 4
    include_videos: bool = False
    skip_duplicates: bool = False
    skip_clustering: bool = False
    output_dir: Path | None = None       # None means in-place
    dry_run: bool = True
    quiet: bool = False
