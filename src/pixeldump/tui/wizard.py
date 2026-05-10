"""Interactive setup wizard.

A non-blocking, prompt-based wizard built on ``rich.prompt``. It walks the user
through provider, naming mode, sass level, and dry-run vs. apply, and returns a
:class:`pixeldump.core.types.PipelineConfig`.
"""
from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

from pixeldump.core.types import NamingMode, PipelineConfig, ProviderName
from pixeldump.tui.sass import SassEngine

_NAMING_EXAMPLES: dict[str, str] = {
    "corporate": "2024_03_paris_trip",
    "chaotic": "2024_03_ate_good_in_paris",
    "unhinged": "2024_03_paris_was_a_FEVER_DREAM",
}

_SASS_DESCRIPTIONS: dict[str, str] = {
    "0": "silent — just the work, no commentary",
    "1": "mild — only milestones",
    "2": "default — full Gen-Z flavor (recommended)",
    "3": "unhinged — maximum chaos",
}


def _pick_provider(
    console: Console, available: list[str]
) -> ProviderName:
    if len(available) == 1:
        only = available[0]
        console.print(f"[dim]only [bold]{only}[/bold] is available — auto-selecting.[/dim]")
        return ProviderName(only)

    table = Table(show_header=False, box=None)
    for name in available:
        table.add_row(f"[cyan]{name}[/cyan]")
    console.print(Panel(table, title="providers", border_style="cyan"))

    choice = Prompt.ask(
        "pick a provider",
        choices=available,
        default=available[0],
    )
    return ProviderName(choice)


def _pick_naming_mode(console: Console) -> NamingMode:
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("mode")
    table.add_column("example")
    for mode, example in _NAMING_EXAMPLES.items():
        table.add_row(mode, example)
    console.print(Panel(table, title="naming mode", border_style="magenta"))

    choice = Prompt.ask(
        "pick a naming mode",
        choices=list(_NAMING_EXAMPLES.keys()),
        default=NamingMode.CHAOTIC.value,
    )
    return NamingMode(choice)


def _pick_sass_level(console: Console) -> int:
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("level")
    table.add_column("vibe")
    for lvl, desc in _SASS_DESCRIPTIONS.items():
        table.add_row(lvl, desc)
    console.print(Panel(table, title="sass level", border_style="magenta"))

    choice = Prompt.ask(
        "pick a sass level",
        choices=list(_SASS_DESCRIPTIONS.keys()),
        default="2",
    )
    return int(choice)


def _pick_dry_run(console: Console) -> bool:
    return Confirm.ask(
        "dry-run? (recommended on first runs — nothing will be moved)",
        default=True,
    )


def _show_summary(
    console: Console,
    *,
    target_dir: Path,
    provider: ProviderName,
    naming_mode: NamingMode,
    sass_level: int,
    dry_run: bool,
) -> None:
    table = Table.grid(padding=(0, 2))
    table.add_column(style="bold")
    table.add_column()
    table.add_row("target", str(target_dir))
    table.add_row("provider", provider.value)
    table.add_row("naming", naming_mode.value)
    table.add_row("sass level", str(sass_level))
    table.add_row("mode", "dry-run" if dry_run else "APPLY (will move files)")
    console.print(Panel(table, title="ready to dump?", border_style="bright_magenta"))


def run_wizard(
    target_dir: Path,
    *,
    console: Console | None = None,
    sass: SassEngine | None = None,
    available_providers: list[str] | None = None,
) -> PipelineConfig:
    """Walk the user through provider/mode/sass/dry-run. Return a PipelineConfig."""
    console = console or Console()
    if sass is None:
        sass = SassEngine(level=2)
    providers = available_providers or ["claude", "ollama"]

    provider = _pick_provider(console, providers)
    naming_mode = _pick_naming_mode(console)
    sass_level = _pick_sass_level(console)
    dry_run = _pick_dry_run(console)

    _show_summary(
        console,
        target_dir=target_dir,
        provider=provider,
        naming_mode=naming_mode,
        sass_level=sass_level,
        dry_run=dry_run,
    )

    if not Confirm.ask("ready?", default=True):
        raise KeyboardInterrupt("wizard cancelled by user")

    return PipelineConfig(
        target_dir=target_dir,
        provider=provider,
        naming_mode=naming_mode,
        sass_level=sass_level,
        dry_run=dry_run,
    )
