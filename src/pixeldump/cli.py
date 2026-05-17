"""Click-based CLI entry point for PixelDump."""
from __future__ import annotations

import contextlib
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

import click

from pixeldump.config import (
    DEFAULT_CONFIG,
    default_config_path,
    load_config,
    save_config,
)
from pixeldump.core.types import (
    LibraryStats,
    NamingMode,
    Phase,
    PipelineConfig,
    ProviderName,
)
from pixeldump.providers.base import VisionProvider

# ---------------------------------------------------------------------------
# Hooks adapters
# ---------------------------------------------------------------------------


class _DashboardHooks:
    """Adapter that maps Pipeline hook calls to a Dashboard."""

    def __init__(self, dash: Any) -> None:
        self._dash = dash

    def on_phase(self, phase: Phase) -> None:
        self._dash.set_phase(phase)

    def on_progress(self, completed: int, total: int) -> None:
        self._dash.set_progress(completed, total)

    def on_activity(self, line: str) -> None:
        self._dash.add_activity(line)

    def on_stats(self, stats: LibraryStats) -> None:
        self._dash.update_stats(stats)


class _QuietHooks:
    """Minimal text hooks for --quiet runs."""

    def on_phase(self, phase: Phase) -> None:
        click.echo(f"[{phase.value}]")

    def on_progress(self, completed: int, total: int) -> None:
        click.echo(f"  progress: {completed}/{total}")

    def on_activity(self, line: str) -> None:
        click.echo(f"  - {line}")

    def on_stats(self, stats: LibraryStats) -> None:
        # Don't spam: skip per-stat updates.
        pass


# ---------------------------------------------------------------------------
# Provider helpers
# ---------------------------------------------------------------------------


def _instantiate_provider(
    choice: str, config: dict[str, Any]
) -> VisionProvider | None:
    """Instantiate a provider, returning None if unavailable."""
    from pixeldump.providers.claude import ClaudeProvider
    from pixeldump.providers.claude_code import ClaudeCodeProvider
    from pixeldump.providers.ollama import OllamaProvider

    if choice == "claude-code":
        ccp = ClaudeCodeProvider()
        return ccp if ccp.is_available() else None

    if choice == "auto":
        # 1. Claude Code (no extra key needed) — preferred when available.
        ccp = ClaudeCodeProvider()
        if ccp.is_available():
            return ccp
        # 2. Direct Claude API if key is configured.
        api_key = os.environ.get("ANTHROPIC_API_KEY") or config.get("claude_api_key")
        if api_key:
            cp = ClaudeProvider(api_key=api_key)
            if cp.is_available():
                return cp
        # 3. Ollama as a last resort.
        op = OllamaProvider(
            host=config.get("ollama_host", "http://localhost:11434"),
            model=config.get("ollama_model", "gemma3"),
        )
        if op.is_available():
            return op
        return None

    if choice == "claude":
        api_key = os.environ.get("ANTHROPIC_API_KEY") or config.get("claude_api_key")
        cp = ClaudeProvider(api_key=api_key)
        return cp if cp.is_available() else None

    if choice == "ollama":
        op = OllamaProvider(
            host=config.get("ollama_host", "http://localhost:11434"),
            model=config.get("ollama_model", "gemma3"),
        )
        return op if op.is_available() else None

    return None


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------


@click.group(invoke_without_command=True)
@click.version_option(package_name="pixeldump")
@click.pass_context
def main(ctx: click.Context) -> None:
    """PixelDump: organize your camera roll with AI."""
    if ctx.invoked_subcommand is None:
        try:
            from rich.console import Console

            from pixeldump.tui.sass import SassEngine
            from pixeldump.tui.splash import render_splash

            console = Console()
            render_splash(console, SassEngine(level=2))
        except Exception:
            # If TUI isn't available for any reason, still print help.
            pass
        click.echo(ctx.get_help())


@main.command()
@click.argument(
    "target", type=click.Path(exists=True, file_okay=False, path_type=Path)
)
@click.option(
    "--provider",
    "provider_choice",
    type=click.Choice(["claude", "ollama", "claude-code", "auto"]),
    default=None,
)
@click.option(
    "--mode",
    "naming_mode",
    type=click.Choice(["corporate", "chaotic", "unhinged"]),
    default=None,
)
@click.option("--sass", "sass_level", type=click.IntRange(0, 3), default=None)
@click.option("--burst-hours", type=int, default=None)
@click.option("--batch-size", type=int, default=None)
@click.option("--concurrency", type=int, default=None)
@click.option("--include-videos/--no-videos", default=False)
@click.option("--skip-duplicates", is_flag=True, default=False)
@click.option("--skip-clustering", is_flag=True, default=False)
@click.option(
    "--output", "output_dir", type=click.Path(path_type=Path), default=None
)
@click.option(
    "--dry-run/--apply",
    "dry_run",
    default=None,
    help="Default: dry-run on first run.",
)
@click.option("--quiet", is_flag=True, default=False)
@click.option(
    "--no-wizard",
    is_flag=True,
    default=False,
    help="Skip the interactive wizard.",
)
@click.option(
    "--estimate",
    is_flag=True,
    default=False,
    help="Print cost estimate and exit.",
)
def run(
    target: Path,
    provider_choice: str | None,
    naming_mode: str | None,
    sass_level: int | None,
    burst_hours: int | None,
    batch_size: int | None,
    concurrency: int | None,
    include_videos: bool,
    skip_duplicates: bool,
    skip_clustering: bool,
    output_dir: Path | None,
    dry_run: bool | None,
    quiet: bool,
    no_wizard: bool,
    estimate: bool,
) -> None:
    """Sort photos in TARGET directory."""
    config = load_config()

    # Merge: CLI option wins, else config value, else default.
    chosen_provider = provider_choice or config.get("provider", "auto")
    chosen_mode = naming_mode or config.get("naming_mode", "chaotic")
    chosen_sass = sass_level if sass_level is not None else int(
        config.get("sass_level", 2)
    )
    chosen_burst = (
        burst_hours if burst_hours is not None else int(config.get("burst_hours", 72))
    )
    chosen_batch = (
        batch_size if batch_size is not None else int(config.get("batch_size", 5))
    )
    chosen_concurrency = (
        concurrency if concurrency is not None else int(config.get("concurrency", 4))
    )
    chosen_dry_run = (
        dry_run if dry_run is not None else bool(config.get("default_dry_run", True))
    )

    # Resolve provider.
    provider = _instantiate_provider(chosen_provider, config)
    if provider is None:
        click.echo(
            "no provider available. set ANTHROPIC_API_KEY for claude, or "
            "install + start ollama (then `pixeldump setup`).",
            err=True,
        )
        sys.exit(2)

    # --estimate: scan, estimate, exit.
    if estimate:
        from pixeldump.core import scanner as scanner_mod

        scan_result = scanner_mod.scan(target, include_videos=include_videos)
        n = len(scan_result.photos)
        cost = provider.estimate_cost(n)
        if cost is None:
            click.echo(
                f"{n} photos. estimated cost: free (local provider: {provider.name})."
            )
        else:
            click.echo(
                f"{n} photos. estimated cost: ${cost.estimated_usd:.4f} "
                f"(provider: {provider.name})"
            )
        return

    # Resolve config (wizard or direct).
    use_wizard = (not no_wizard) and (not quiet) and sys.stdin.isatty()
    pipeline_config: PipelineConfig
    if use_wizard:
        try:
            from rich.console import Console

            from pixeldump.tui.sass import SassEngine
            from pixeldump.tui.wizard import run_wizard

            console = Console()
            sass_engine = SassEngine(level=chosen_sass)
            pipeline_config = run_wizard(
                target,
                console=console,
                sass=sass_engine,
                available_providers=[provider.name],
            )
            # Wizard sets some fields but leaves output/burst/etc. defaults — fill in.
            pipeline_config.burst_hours = chosen_burst
            pipeline_config.batch_size = chosen_batch
            pipeline_config.concurrency = chosen_concurrency
            pipeline_config.include_videos = include_videos
            pipeline_config.skip_duplicates = skip_duplicates
            pipeline_config.skip_clustering = skip_clustering
            pipeline_config.output_dir = output_dir
            pipeline_config.quiet = quiet
        except KeyboardInterrupt:
            click.echo("wizard cancelled.", err=True)
            sys.exit(1)
    else:
        pipeline_config = PipelineConfig(
            target_dir=target,
            provider=ProviderName(chosen_provider),
            naming_mode=NamingMode(chosen_mode),
            sass_level=chosen_sass,
            burst_hours=chosen_burst,
            batch_size=chosen_batch,
            concurrency=chosen_concurrency,
            include_videos=include_videos,
            skip_duplicates=skip_duplicates,
            skip_clustering=skip_clustering,
            output_dir=output_dir,
            dry_run=chosen_dry_run,
            quiet=quiet,
        )

    # Run.
    from pixeldump.app import Pipeline
    from pixeldump.utils.state import write_manifest

    if quiet:
        pipeline = Pipeline(pipeline_config, provider, hooks=_QuietHooks())
        try:
            manifest = pipeline.run()
        except Exception as exc:
            click.echo(f"pipeline failed: {exc}", err=True)
            sys.exit(1)
        with contextlib.suppress(Exception):
            write_manifest(target, manifest)
        stats = manifest.stats
        click.echo(
            f"done. sorted={stats.sorted} duplicates={stats.duplicates} "
            f"review={stats.needs_review} folders={stats.folders_created}"
        )
        return

    # Dashboard mode.
    from rich.console import Console

    from pixeldump.tui.dashboard import Dashboard
    from pixeldump.tui.receipt import print_receipt
    from pixeldump.tui.sass import SassEngine

    console = Console()
    sass_engine = SassEngine(level=chosen_sass)
    dash = Dashboard(console, sass_engine)
    pipeline = Pipeline(pipeline_config, provider, hooks=_DashboardHooks(dash))
    try:
        with dash.live():
            manifest = pipeline.run()
    except Exception as exc:
        click.echo(f"pipeline failed: {exc}", err=True)
        sys.exit(1)
    with contextlib.suppress(Exception):
        write_manifest(target, manifest)
    print_receipt(console, manifest.stats, manifest.run_id, sass_engine)


@main.command()
@click.argument(
    "manifest", type=click.Path(exists=True, dir_okay=False, path_type=Path)
)
@click.option("--yes", "-y", is_flag=True, default=False)
def undo(manifest: Path, yes: bool) -> None:
    """Undo a previous run using its manifest."""
    from pixeldump.utils.state import load_manifest

    try:
        run_manifest = load_manifest(manifest)
    except Exception as exc:  # noqa: BLE001
        click.echo(f"failed to load manifest: {exc}", err=True)
        sys.exit(1)

    if not yes and not click.confirm(
        f"undo {len(run_manifest.operations)} operations from "
        f"run {run_manifest.run_id}?",
        default=False,
    ):
        click.echo("aborted.")
        return

    success = 0
    failed = 0
    for op in reversed(run_manifest.operations):
        try:
            if not op.destination.exists():
                failed += 1
                continue
            op.source.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(op.destination), str(op.source))
            success += 1
        except Exception as exc:  # noqa: BLE001
            click.echo(f"failed to undo {op.destination}: {exc}", err=True)
            failed += 1
    click.echo(f"undid {success} ops; {failed} failed/skipped.")


@main.command()
@click.option("--reset", is_flag=True, default=False)
def config(reset: bool) -> None:
    """Show or reset the user config."""
    import yaml  # type: ignore[import-untyped]

    path = default_config_path()
    if reset:
        if not click.confirm(
            f"reset config at {path} to defaults?", default=False
        ):
            click.echo("aborted.")
            return
        save_config(dict(DEFAULT_CONFIG), path)
        click.echo(f"wrote defaults to {path}.")
        return

    if not path.exists():
        click.echo("(no config yet, using defaults)")
        click.echo(yaml.safe_dump(dict(DEFAULT_CONFIG), sort_keys=True))
        return
    data = load_config(path)
    click.echo(yaml.safe_dump(data, sort_keys=True))


@main.command()
def setup() -> None:
    """Re-run the provider setup wizard."""
    from pixeldump.providers.claude import ClaudeProvider
    from pixeldump.providers.claude_code import ClaudeCodeProvider
    from pixeldump.providers.ollama import OllamaProvider

    cfg = load_config()

    # ── 1. Probe all providers and show their status ─────────────────────────
    click.echo("\nchecking available providers...\n")

    ccp = ClaudeCodeProvider()
    cc_ok = ccp.is_available()
    click.echo(
        f"  claude-code  {'✓ detected (no API key needed)' if cc_ok else '✗ not found — install Claude Code: https://claude.ai/code'}"
    )

    api_key = os.environ.get("ANTHROPIC_API_KEY") or cfg.get("claude_api_key")
    claude_ok = bool(api_key)
    click.echo(
        f"  claude       {'✓ API key found' if claude_ok else '✗ no API key configured'}"
    )

    op = OllamaProvider(
        host=cfg.get("ollama_host", "http://localhost:11434"),
        model=cfg.get("ollama_model", "gemma3"),
    )
    ollama_ok = op.is_available()
    click.echo(
        f"  ollama       {'✓ running' if ollama_ok else '✗ not reachable'}"
    )

    click.echo()

    # ── 2. Pick default provider first ───────────────────────────────────────
    all_providers = ["claude-code", "claude", "ollama", "auto"]
    current_default = cfg.get("provider", "auto")

    default_provider = click.prompt(
        "default provider",
        type=click.Choice(all_providers),
        default=current_default if current_default in all_providers else "auto",
    )
    cfg["provider"] = default_provider

    # ── 3. Configure credentials only if the chosen provider needs them ──────
    if default_provider == "claude-code":
        click.echo("claude-code: no credentials needed. ✓")

    if default_provider in {"claude", "auto"} and not claude_ok:
        if click.confirm("configure anthropic API key?", default=True):
            new_key = click.prompt(
                "anthropic API key", hide_input=True, default="", show_default=False
            )
            if new_key:
                cp = ClaudeProvider(api_key=new_key)
                if cp.is_available():
                    cfg["claude_api_key"] = new_key
                    click.echo("claude: ok.")
                else:
                    click.echo("claude: not reachable; key NOT saved.", err=True)
            else:
                click.echo("claude: skipped.")

    if default_provider in {"ollama", "auto"} and not ollama_ok:
        if click.confirm("configure ollama?", default=False):
            host = click.prompt("ollama host", default="http://localhost:11434")
            model = click.prompt("ollama model", default="gemma3")
            op2 = OllamaProvider(host=host, model=model)
            if op2.is_available():
                cfg["ollama_host"] = host
                cfg["ollama_model"] = model
                click.echo("ollama: ok.")
            else:
                click.echo("ollama: not reachable; settings NOT saved.", err=True)

    save_config(cfg)
    click.echo(f"\nsaved. default provider: {default_provider}.")
    click.echo(f"config: {default_config_path()}")


@main.command()
@click.argument(
    "target", type=click.Path(exists=True, file_okay=False, path_type=Path)
)
def status(target: Path) -> None:
    """Show the latest manifest for TARGET."""
    manifests_dir = target / ".pixeldump" / "manifests"
    if not manifests_dir.is_dir():
        click.echo(f"no .pixeldump/manifests directory in {target}.")
        return
    candidates = sorted(manifests_dir.glob("*.json"))
    if not candidates:
        click.echo("no manifests found.")
        return
    latest = candidates[-1]
    click.echo(f"latest manifest: {latest}")
    try:
        data = json.loads(latest.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        click.echo(f"failed to read manifest: {exc}", err=True)
        return
    stats = data.get("stats") or {}
    click.echo(f"  run_id: {data.get('run_id')}")
    click.echo(f"  provider: {data.get('provider')}")
    click.echo(f"  naming_mode: {data.get('naming_mode')}")
    click.echo(f"  started_at: {data.get('started_at')}")
    click.echo(f"  completed_at: {data.get('completed_at')}")
    click.echo(f"  total: {stats.get('total_photos', 0)}")
    click.echo(f"  sorted: {stats.get('sorted', 0)}")
    click.echo(f"  duplicates: {stats.get('duplicates', 0)}")
    click.echo(f"  needs_review: {stats.get('needs_review', 0)}")
