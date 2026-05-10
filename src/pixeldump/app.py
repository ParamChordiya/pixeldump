"""High-level pipeline orchestrator.

Wires scanner -> hasher -> clusterer -> classifier -> namer -> mover and
emits hooks for an optional UI layer.
"""
from __future__ import annotations

from datetime import datetime
from typing import Protocol

from pixeldump.core import (
    classifier as classifier_mod,
)
from pixeldump.core import (
    clusterer as clusterer_mod,
)
from pixeldump.core import (
    hasher as hasher_mod,
)
from pixeldump.core import (
    mover as mover_mod,
)
from pixeldump.core import (
    namer as namer_mod,
)
from pixeldump.core import (
    scanner as scanner_mod,
)
from pixeldump.core.types import (
    Classification,
    EventCluster,
    FolderName,
    LibraryStats,
    Phase,
    PipelineConfig,
    RunManifest,
)
from pixeldump.providers.base import VisionProvider
from pixeldump.utils import image as image_utils


class PipelineHooks(Protocol):
    """Optional callbacks the orchestrator fires for UI updates. All optional."""

    def on_phase(self, phase: Phase) -> None: ...
    def on_progress(self, completed: int, total: int) -> None: ...
    def on_activity(self, line: str) -> None: ...
    def on_stats(self, stats: LibraryStats) -> None: ...


class _NoopHooks:
    """Default hooks that do nothing — used when running headless."""

    def on_phase(self, phase: Phase) -> None:
        pass

    def on_progress(self, completed: int, total: int) -> None:
        pass

    def on_activity(self, line: str) -> None:
        pass

    def on_stats(self, stats: LibraryStats) -> None:
        pass


class Pipeline:
    """Coordinates the full PixelDump pipeline for a single run."""

    def __init__(
        self,
        config: PipelineConfig,
        provider: VisionProvider,
        hooks: PipelineHooks | None = None,
    ) -> None:
        self.config = config
        self.provider = provider
        self.hooks: PipelineHooks = hooks or _NoopHooks()
        self._stats = LibraryStats()
        self._started_at: datetime | None = None

    def stats(self) -> LibraryStats:
        """Return current rolling stats."""
        return self._stats

    def run(self) -> RunManifest:
        """Execute all phases and return a manifest.

        The manifest is NOT persisted here — the caller (CLI) is responsible
        for calling ``utils.state.write_manifest`` after.
        """
        # 1. Setup
        self.hooks.on_phase(Phase.SETUP)
        self._started_at = datetime.now()
        if not self.provider.is_available():
            raise RuntimeError("provider not available")

        # 2. Scan
        self.hooks.on_phase(Phase.SCANNING)
        scan = scanner_mod.scan(
            self.config.target_dir, include_videos=self.config.include_videos
        )
        self._stats.total_photos = len(scan.photos)
        self.hooks.on_stats(self._stats)
        self.hooks.on_activity(f"scanned {len(scan.photos)} photos")

        # 3. Hash + duplicates
        self.hooks.on_phase(Phase.HASHING)
        dup_groups = []
        if not self.config.skip_duplicates:
            hasher_mod.hash_all(scan.photos, concurrency=self.config.concurrency)
            dup_groups = hasher_mod.find_duplicates(scan.photos)
            self._stats.duplicates = sum(len(g.duplicates) for g in dup_groups)
            self.hooks.on_stats(self._stats)
            self.hooks.on_activity(f"found {self._stats.duplicates} duplicates")

        # 4. Cluster
        self.hooks.on_phase(Phase.CLUSTERING)
        clusters: list[EventCluster]
        if not self.config.skip_clustering:
            clusters = clusterer_mod.cluster(
                scan.photos, burst_hours=self.config.burst_hours
            )
        else:
            # Degenerate case: all photos in one mega-cluster.
            if scan.photos:
                dated = [p.date_taken for p in scan.photos if p.date_taken is not None]
                ds = min(dated) if dated else datetime.min
                de = max(dated) if dated else datetime.min
                clusters = [
                    EventCluster(
                        cluster_id="_no_cluster",
                        photos=list(scan.photos),
                        date_start=ds,
                        date_end=de,
                        gps_center=None,
                    )
                ]
            else:
                clusters = []
        self.hooks.on_activity(f"built {len(clusters)} cluster(s)")

        # 5. Classify
        self.hooks.on_phase(Phase.CLASSIFYING)
        classifications: dict[str, Classification] = classifier_mod.classify_clusters(
            clusters,
            self.provider,
            image_utils.to_photo_input,
            batch_size=self.config.batch_size,
            concurrency=self.config.concurrency,
        )
        self.hooks.on_progress(len(clusters), max(len(clusters), 1))
        for cluster_id, cls in classifications.items():
            self.hooks.on_activity(
                f"\U0001f4f8 cluster {cluster_id} -> {cls.category}"
            )

        # 6. Name
        folder_names: dict[str, FolderName] = {}
        for cluster in clusters:
            cls_for_cluster: Classification | None = classifications.get(
                cluster.cluster_id
            )
            if cls_for_cluster is None:
                continue
            folder_names[cluster.cluster_id] = namer_mod.name_cluster(
                cluster,
                cls_for_cluster,
                self.provider,
                self.config.naming_mode,
                image_utils.to_photo_input,
            )

        # 7. Plan + apply moves
        self.hooks.on_phase(Phase.MOVING)
        operations = mover_mod.plan_moves(
            clusters, folder_names, dup_groups, self.config
        )
        manifest = mover_mod.apply_moves(operations, dry_run=self.config.dry_run)
        manifest.provider = self.provider.name
        manifest.naming_mode = self.config.naming_mode.value

        # 8. Stats finalization
        # Copy mover-derived stats into the rolling stats.
        self._stats.sorted = manifest.stats.sorted
        self._stats.needs_review = manifest.stats.needs_review
        self._stats.folders_created = manifest.stats.folders_created
        if manifest.stats.duplicates:
            self._stats.duplicates = manifest.stats.duplicates

        # Per-cluster category counters.
        screenshots = 0
        food = 0
        selfies = 0
        cats = 0
        notable_findings: list[str] = []
        for cluster in clusters:
            cls_stat: Classification | None = classifications.get(cluster.cluster_id)
            if cls_stat is None:
                continue
            n_photos = len(cluster.photos)
            if cls_stat.subcategory == "screenshot":
                screenshots += n_photos
            if cls_stat.subcategory == "food":
                food += n_photos
            if cls_stat.subcategory in {"selfie", "mirror_selfie"}:
                selfies += n_photos
            if cls_stat.subcategory in {"cat", "pet"}:
                cats += n_photos
            for n in cls_stat.notable:
                if "cat" in n.lower():
                    cats += 1
                notable_findings.append(n)
        self._stats.screenshots = screenshots
        self._stats.food = food
        self._stats.selfies = selfies
        self._stats.cats = cats
        if notable_findings:
            self._stats.notable_findings = notable_findings[:20]

        # Elapsed.
        self._stats.elapsed_seconds = (datetime.now() - self._started_at).total_seconds()

        # Cost (Claude only).
        try:
            cost = self.provider.estimate_cost(self._stats.total_photos)
        except Exception:
            cost = None
        if cost is not None:
            self._stats.cost_usd = cost.estimated_usd

        # Mirror final stats into the manifest as well.
        manifest.stats = self._stats

        # 9. Done.
        self.hooks.on_phase(Phase.COMPLETE)
        self.hooks.on_stats(self._stats)
        return manifest
