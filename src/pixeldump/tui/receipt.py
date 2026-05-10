"""End-of-run receipt: prints stat panel, sass findings, and optional roast."""
from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from pixeldump.core.types import LibraryStats
from pixeldump.tui.sass import SassEngine
from pixeldump.tui.widgets import receipt_panel

__all__ = ["print_receipt", "receipt_panel"]


def print_receipt(
    console: Console,
    stats: LibraryStats,
    run_id: str,
    sass: SassEngine,
    roast: str | None = None,
) -> None:
    """Print the receipt panel, sass findings, and optional roast."""
    console.print(receipt_panel(stats, run_id, sass=sass))

    for line in sass.stats_findings(stats):
        console.print(Text(f"• {line}", style="italic dim"))

    if roast is not None:
        console.print(
            Panel(
                Text(roast, style="italic"),
                title="\U0001f525 the roast",
                border_style="bright_red",
            )
        )
    else:
        console.print(Text("(LLM-generated roast placeholder)", style="dim"))
