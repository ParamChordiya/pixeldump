"""Reusable Rich renderables for the dashboard / receipt.

All functions are pure (no IO) and return Rich renderables.
"""
from __future__ import annotations

from rich import box
from rich.align import Align
from rich.console import Group
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    TaskProgressColumn,
    TextColumn,
    TimeRemainingColumn,
)
from rich.table import Table
from rich.text import Text

from pixeldump.core.types import LibraryStats, Phase
from pixeldump.tui.sass import SassEngine

_PHASE_LABELS: dict[Phase, str] = {
    Phase.SETUP: "Setting up the chaos ⚙️",
    Phase.SCANNING: "Scanning your photo dump \U0001f4f8",
    Phase.HASHING: "Detecting your copy-paste addiction \U0001f480",
    Phase.CLUSTERING: "Grouping your eras \U0001f4c5",
    Phase.CLASSIFYING: "Asking the AI nicely \U0001f9e0",
    Phase.MOVING: "Moving photos with care \U0001f4e6",
    Phase.COMPLETE: "We did it \U0001fae0",
}


def phase_label(phase: Phase) -> str:
    """Map Phase to a Gen-Z-flavored label."""
    return _PHASE_LABELS.get(phase, phase.value)


def phase_label_plain(phase: Phase) -> str:
    """Map Phase to its plain enum value for sass-level-0 mode."""
    return phase.value


def stats_panel(stats: LibraryStats, *, sass: SassEngine | None = None) -> Panel:
    """Build a Rich Panel with the running stats (the 'tea' panel)."""
    table = Table.grid(expand=True, padding=(0, 2))
    table.add_column(justify="left", ratio=1)
    table.add_column(justify="right", ratio=1)

    rows: list[tuple[str, str]] = [
        ("\U0001f4f8 sorted", str(stats.sorted)),
        ("\U0001f4cb total", str(stats.total_photos)),
        ("♻️ duplicates", str(stats.duplicates)),
        ("\U0001f4f1 screenshots", str(stats.screenshots)),
        ("\U0001f431 cats", str(stats.cats)),
        ("\U0001f35c food", str(stats.food)),
        ("\U0001f933 selfies", str(stats.selfies)),
        ("\U0001f4c1 folders", str(stats.folders_created)),
    ]
    for label, value in rows:
        table.add_row(Text(label, style="bold"), Text(value, style="cyan"))

    # Speed + cost row at the bottom
    speed = 0.0
    if stats.elapsed_seconds > 0 and stats.sorted > 0:
        speed = stats.sorted / stats.elapsed_seconds
    table.add_row(
        Text("⚡ speed", style="bold"),
        Text(f"{speed:.1f}/s", style="green"),
    )
    table.add_row(
        Text("\U0001f4b8 cost", style="bold"),
        Text(f"${stats.cost_usd:.4f}", style="yellow"),
    )

    title = "the tea ☕" if sass is None or sass.level >= 2 else "stats"
    return Panel(table, title=title, border_style="cyan", box=box.ROUNDED)


def build_progress(*, transient: bool = False) -> Progress:
    """Construct a Rich Progress with description, bar, percent, ETA."""
    return Progress(
        TextColumn("[bold cyan]{task.description}", justify="left"),
        BarColumn(bar_width=None, style="magenta", complete_style="bright_magenta"),
        TaskProgressColumn(),
        TextColumn("•"),
        TimeRemainingColumn(),
        transient=transient,
        expand=True,
    )


def receipt_panel(
    stats: LibraryStats, run_id: str, sass: SassEngine | None = None
) -> Panel:
    """The big ASCII-art-style receipt panel. Multi-line, capped at 50 chars wide."""
    lines: list[str] = []
    lines.append("pixeldump™ receipt")
    lines.append(f"run: {run_id}")
    lines.append("-" * 44)
    lines.append(f"\U0001f4f8 total photos      {stats.total_photos:>10}")
    lines.append(f"✅ sorted            {stats.sorted:>10}")
    lines.append(f"♻️  duplicates        {stats.duplicates:>10}")
    lines.append(f"\U0001f4f1 screenshots       {stats.screenshots:>10}")
    lines.append(f"\U0001f431 cats              {stats.cats:>10}")
    lines.append(f"\U0001f35c food              {stats.food:>10}")
    lines.append(f"\U0001f933 selfies           {stats.selfies:>10}")
    lines.append(f"\U0001f4c1 folders created   {stats.folders_created:>10}")
    lines.append(f"\U0001f440 needs review      {stats.needs_review:>10}")
    lines.append("-" * 44)
    lines.append(f"⏱️  elapsed   {stats.elapsed_seconds:>10.1f}s")
    lines.append(f"\U0001f4b8 cost      ${stats.cost_usd:>10.4f}")
    lines.append("-" * 44)

    body = Text("\n".join(lines), style="bold")
    aligned = Align.left(body)
    title = "\U0001f9fe receipt"
    return Panel(
        aligned,
        title=title,
        border_style="bright_magenta",
        box=box.HEAVY,
        width=50,
        padding=(1, 2),
    )


# Backwards-compat aliases (legacy class-style stubs are no longer used by the
# CLI agent, but keep functional helpers grouped together for discovery).
__all__ = [
    "build_progress",
    "phase_label",
    "phase_label_plain",
    "receipt_panel",
    "stats_panel",
]


# Suppress unused-import warning for Group: re-exported for future composition.
_ = Group
