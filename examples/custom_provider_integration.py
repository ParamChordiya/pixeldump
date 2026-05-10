"""Show how to plug a custom LLM provider into PixelDump.

This file is the canonical "how do I add my own AI backend?" example.
``MockVisionProvider`` fulfils the full ``VisionProvider`` interface using
hard-coded responses so it works without any API key or network access.

Typical use-cases for a custom provider:

* Local models (Llama, Mistral, Phi) via a REST shim
* Proprietary internal APIs
* Deterministic mock for CI / unit-test pipelines (which is what this example is)

Usage::

    python examples/custom_provider_integration.py                  # ~/Pictures
    python examples/custom_provider_integration.py ~/Photos

The script scans the given directory, forms event clusters, classifies each
cluster using ``MockVisionProvider``, and prints the results.  Nothing is moved.
"""
from __future__ import annotations

import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table

from pixeldump.core.classifier import classify_clusters, sample_photos_for_cluster
from pixeldump.core.clusterer import cluster
from pixeldump.core.scanner import scan
from pixeldump.core.types import (
    Classification,
    CostEstimate,
    EventCluster,
    LibraryStats,
    NamingMode,
    PhotoInput,
    PhotoMetadata,
)
from pixeldump.providers.base import VisionProvider


# ---------------------------------------------------------------------------
# Custom provider implementation
# ---------------------------------------------------------------------------


class MockVisionProvider(VisionProvider):
    """Deterministic mock provider for demos, tests, and CI pipelines.

    Every cluster is labelled ``travel / city_break`` with 90 % confidence.
    Swap the return values here (or subclass again) to drive your own logic.
    """

    name = "mock"

    # -- Required abstract methods -------------------------------------------

    def is_available(self) -> bool:
        """Always available — no network or API key required."""
        return True

    def estimate_cost(self, num_photos: int) -> CostEstimate | None:
        """Free provider: return None to signal no cost estimate."""
        return None

    def classify_cluster(self, photos: list[PhotoInput]) -> Classification:
        """Return a fixed classification regardless of the photos supplied."""
        return Classification(
            category="travel",
            subcategory="city_break",
            confidence=0.9,
            description="mock classification — swap this for real LLM output",
            notable=[],
        )

    def name_event(
        self,
        photos: list[PhotoInput],
        category: str,
        mode: NamingMode,
    ) -> str:
        """Return a fixed event name regardless of mode or content."""
        return "mock_event_name"

    def generate_roast(self, stats: LibraryStats) -> str:
        """Return a fixed roast string."""
        return (
            "Your photo library is a chaotic masterpiece of missed focus and "
            "accidental selfies.  10/10 would not organise for you."
        )


# ---------------------------------------------------------------------------
# Helper: convert PhotoMetadata → PhotoInput without reading real files
# ---------------------------------------------------------------------------


def _to_photo_input(meta: PhotoMetadata) -> PhotoInput:
    """Produce a minimal PhotoInput with placeholder thumbnail bytes.

    In a real pipeline, ``pixeldump.utils.image.make_thumbnail`` would be
    called here to generate an actual JPEG thumbnail.  For this demo we use a
    1-byte placeholder so we do not need image files on disk.
    """
    return PhotoInput(
        metadata=meta,
        thumbnail_bytes=b"\xff",          # placeholder — not decoded by mock
        thumbnail_media_type="image/jpeg",
    )


# ---------------------------------------------------------------------------
# Main demo
# ---------------------------------------------------------------------------


def run(target: Path) -> None:
    """Scan *target*, cluster, classify with the mock provider, and summarise."""
    console = Console()

    if not target.exists():
        console.print(f"[bold red]Directory not found:[/] {target}")
        sys.exit(1)

    console.rule(f"[bold cyan]PixelDump — custom provider demo[/] — {target}")

    # Wire up the mock provider
    provider = MockVisionProvider()
    console.print(
        f"[green]Provider:[/] {provider.name!r}  |  "
        f"available={provider.is_available()}  |  "
        f"cost_estimate={provider.estimate_cost(100)}"
    )

    # Phase 1: scan
    with console.status("Scanning..."):
        scan_result = scan(target)

    total = len(scan_result.photos)
    if total == 0:
        console.print("[yellow]No photos found — nothing to classify.[/]")
        return

    console.print(f"[green]Scanned:[/] {total} photo(s)")

    # Phase 2: cluster (no hashing needed for classification)
    with console.status("Clustering..."):
        clusters: list[EventCluster] = cluster(scan_result.photos)

    console.print(f"[green]Clustered:[/] {len(clusters)} event cluster(s)")

    # Phase 3: classify with the custom provider
    with console.status("Classifying clusters..."):
        classifications = classify_clusters(
            clusters,
            provider,
            _to_photo_input,
            batch_size=5,
            concurrency=1,          # keep output deterministic in this demo
        )

    # Display results
    table = Table(
        title="[bold]Classification results[/]",
        show_header=True,
        header_style="bold magenta",
    )
    table.add_column("Cluster ID", style="cyan", no_wrap=True)
    table.add_column("Photos", justify="right")
    table.add_column("Category", style="green")
    table.add_column("Subcategory")
    table.add_column("Confidence", justify="right")
    table.add_column("Description")

    for c in sorted(clusters, key=lambda x: x.cluster_id):
        cls = classifications.get(c.cluster_id)
        if cls is None:
            continue
        table.add_row(
            c.cluster_id,
            str(len(c.photos)),
            cls.category,
            cls.subcategory or "—",
            f"{cls.confidence:.0%}",
            cls.description[:60] + ("…" if len(cls.description) > 60 else ""),
        )

    console.print(table)

    # Show the roast for fun
    console.rule("[bold]Roast[/]")
    # Build minimal LibraryStats for the roast
    stats = LibraryStats(
        total_photos=total,
        sorted=0,
        duplicates=0,
    )
    console.print(provider.generate_roast(stats))
    console.print()
    console.print(
        "[dim]Replace [bold]MockVisionProvider[/] with your own subclass to use "
        "a real LLM backend.  The only requirement is implementing the five "
        "abstract methods defined in [bold]pixeldump.providers.base.VisionProvider[/].[/dim]"
    )


if __name__ == "__main__":
    raw_path = sys.argv[1] if len(sys.argv) > 1 else "~/Pictures"
    run(Path(raw_path).expanduser().resolve())
