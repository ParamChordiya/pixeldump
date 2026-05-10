"""Demonstrate the PixelDump pipeline in a read-only dry-run.

This script shows how to drive PixelDump programmatically — no CLI, no TUI,
no API key required.  It runs the first three pipeline phases (scan, hash,
cluster) and then prints a rich summary table so you can see what PixelDump
*would* do before committing to a real organise run.

Usage::

    python examples/basic_dry_run.py                # defaults to ~/Pictures
    python examples/basic_dry_run.py ~/Photos
    python examples/basic_dry_run.py /Volumes/DCIM

The script is intentionally self-contained: it imports only from the standard
library, ``rich``, and ``pixeldump`` itself, so it works out of the box once
the package is installed (``pip install -e .``).
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.table import Table

from pixeldump.core.clusterer import cluster
from pixeldump.core.hasher import find_duplicates, hash_all
from pixeldump.core.scanner import scan


def _format_bytes(n: int) -> str:
    """Return a human-readable byte count (B / KB / MB / GB)."""
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n //= 1024
    return f"{n:.1f} TB"


def _date_range(clusters: list) -> str:  # type: ignore[type-arg]
    """Return 'YYYY-MM-DD → YYYY-MM-DD' spanning all dated clusters."""
    starts: list[datetime] = [c.date_start for c in clusters if c.date_start != datetime.min]
    ends: list[datetime] = [c.date_end for c in clusters if c.date_end != datetime.min]
    if not starts:
        return "unknown"
    return f"{min(starts).date()} → {max(ends).date()}"


def run(target: Path) -> None:
    """Run scan → hash → cluster on *target* and print a summary table."""
    console = Console()

    if not target.exists():
        console.print(f"[bold red]Directory not found:[/] {target}")
        sys.exit(1)

    console.rule(f"[bold cyan]PixelDump dry-run[/] — {target}")

    # ---- Phase 1: Scan ------------------------------------------------------
    with console.status("Scanning for photos..."):
        scan_result = scan(target)

    total_photos = len(scan_result.photos)
    total_videos = len(scan_result.videos)
    skipped = len(scan_result.skipped)

    if total_photos == 0:
        console.print("[yellow]No photos found.[/]  Check that the path contains JPEG, PNG, HEIC, or similar files.")
        return

    console.print(
        f"[green]Scan complete:[/] {total_photos} photos, "
        f"{total_videos} videos, {skipped} skipped — "
        f"{_format_bytes(scan_result.total_size_bytes)} total"
    )

    # ---- Phase 2: Hash ------------------------------------------------------
    with console.status(f"Hashing {total_photos} photos (SHA-256 + pHash)..."):
        hash_all(scan_result.photos)

    duplicate_groups = find_duplicates(scan_result.photos)
    duplicate_count = sum(len(g.duplicates) for g in duplicate_groups)

    console.print(
        f"[green]Hashing complete:[/] {len(duplicate_groups)} duplicate group(s), "
        f"{duplicate_count} redundant file(s)"
    )

    # ---- Phase 3: Cluster ---------------------------------------------------
    with console.status("Clustering by time and GPS..."):
        clusters = cluster(scan_result.photos)

    console.print(f"[green]Clustering complete:[/] {len(clusters)} event cluster(s)")

    # ---- Summary table ------------------------------------------------------
    table = Table(
        title="[bold]PixelDump dry-run summary[/]",
        show_header=True,
        header_style="bold magenta",
    )
    table.add_column("Metric", style="cyan", no_wrap=True)
    table.add_column("Value", style="white")

    table.add_row("Target directory", str(target))
    table.add_row("Total photos scanned", str(total_photos))
    table.add_row("Skipped files", str(skipped))
    table.add_row("Duplicate files found", str(duplicate_count))
    table.add_row("Duplicate groups", str(len(duplicate_groups)))
    table.add_row("Event clusters formed", str(len(clusters)))
    table.add_row("Date range", _date_range(clusters))
    table.add_row("Total size on disk", _format_bytes(scan_result.total_size_bytes))

    # Per-format breakdown
    for ext, count in sorted(scan_result.format_breakdown.items()):
        table.add_row(f"  {ext} files", str(count))

    console.print(table)
    console.print(
        "\n[dim]This was a dry-run — nothing was moved or modified.\n"
        "To classify and organise, use [bold]pixeldump run[/] or see "
        "[bold]examples/custom_provider_integration.py[/].[/dim]"
    )


if __name__ == "__main__":
    raw_path = sys.argv[1] if len(sys.argv) > 1 else "~/Pictures"
    run(Path(raw_path).expanduser().resolve())
