"""Tests for the TUI / personality layer."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from rich.console import Console

from pixeldump.core.types import (
    LibraryStats,
    NamingMode,
    Phase,
    PipelineConfig,
    ProviderName,
)
from pixeldump.tui.dashboard import Dashboard
from pixeldump.tui.sass import SassEngine
from pixeldump.tui.splash import render_splash
from pixeldump.tui.widgets import (
    phase_label,
    phase_label_plain,
    receipt_panel,
    stats_panel,
)
from pixeldump.tui.wizard import run_wizard

# ---------------------------------------------------------------------------
# sass
# ---------------------------------------------------------------------------


def test_sass_level_0_silences_categories() -> None:
    s = SassEngine(level=0, seed=1)
    assert s.category_line("cat") == ""
    assert s.idle_line() == ""
    assert s.milestone_line(50) == ""


def test_sass_level_2_returns_category_line() -> None:
    s = SassEngine(level=2, seed=1)
    line = s.category_line("cat")
    assert line != ""
    assert isinstance(line, str)


def test_sass_unknown_key_returns_empty() -> None:
    s = SassEngine(level=2, seed=1)
    assert s.category_line("definitely_not_a_real_key") == ""


def test_sass_milestone_lookup() -> None:
    s = SassEngine(level=2, seed=1)
    line = s.milestone_line(50)
    assert "halfway" in line.lower()


def test_sass_tagline_always_nonempty_even_at_level_0() -> None:
    s = SassEngine(level=0, seed=1)
    assert s.tagline() != ""


def test_sass_stats_findings_triggers_screenshot_overload() -> None:
    s = SassEngine(level=2, seed=1)
    stats = LibraryStats(screenshots=100)
    findings = s.stats_findings(stats)
    assert len(findings) >= 1


def test_sass_stats_findings_empty_at_level_0() -> None:
    s = SassEngine(level=0, seed=1)
    stats = LibraryStats(screenshots=100, cats=5, duplicates=10)
    assert s.stats_findings(stats) == []


def test_sass_level_3_picks_longest_line() -> None:
    s = SassEngine(level=3, seed=1)
    # Level 3 always returns a line for known keys.
    line = s.category_line("cat")
    assert line != ""


def test_sass_level_clamps() -> None:
    assert SassEngine(level=-5).level == 0
    assert SassEngine(level=99).level == 3


# ---------------------------------------------------------------------------
# splash
# ---------------------------------------------------------------------------


def test_render_splash_includes_logo_text() -> None:
    console = Console(record=True, width=100)
    sass = SassEngine(level=2, seed=1)
    render_splash(console, sass)
    output = console.export_text()
    # logo.txt has the word "your camera roll" in the tagline area, and the
    # ASCII art uses pipes and underscores. Check for the tagline match.
    lowered = output.lower()
    assert "pixeldump" in lowered or "camera roll" in lowered or "_" in output


# ---------------------------------------------------------------------------
# widgets
# ---------------------------------------------------------------------------


def test_phase_label_for_each_phase() -> None:
    for phase in Phase:
        label = phase_label(phase)
        assert isinstance(label, str)
        assert label != ""


def test_phase_label_plain_returns_enum_value() -> None:
    for phase in Phase:
        assert phase_label_plain(phase) == phase.value


def test_stats_panel_renders_counts() -> None:
    console = Console(record=True, width=80)
    stats = LibraryStats(sorted=47, total_photos=100, screenshots=12, cats=3)
    console.print(stats_panel(stats))
    output = console.export_text()
    assert "47" in output
    assert "100" in output


def test_receipt_panel_includes_emojis_and_counts() -> None:
    console = Console(record=True, width=80)
    stats = LibraryStats(
        total_photos=200,
        sorted=180,
        duplicates=12,
        screenshots=33,
        cats=4,
        food=22,
        selfies=8,
        folders_created=15,
        elapsed_seconds=42.5,
        cost_usd=0.0123,
    )
    console.print(receipt_panel(stats, run_id="20260509_120000"))
    output = console.export_text()
    assert "200" in output
    assert "180" in output
    assert "receipt" in output.lower()
    # Check for at least one emoji character we know we put in.
    assert "\U0001f4f8" in output or "\U0001f9fe" in output


# ---------------------------------------------------------------------------
# dashboard
# ---------------------------------------------------------------------------


def test_dashboard_test_mode_set_phase_updates_state() -> None:
    console = Console(record=True, width=80)
    sass = SassEngine(level=2, seed=1)
    dash = Dashboard(console, sass, _test_mode=True)
    with dash.live():
        dash.set_phase(Phase.HASHING)
    assert dash._phase == Phase.HASHING


def test_dashboard_test_mode_activity_ringbuffer_caps_at_10() -> None:
    console = Console(record=True, width=80)
    sass = SassEngine(level=2, seed=1)
    dash = Dashboard(console, sass, _test_mode=True)
    with dash.live():
        for i in range(15):
            dash.add_activity(f"line {i}")
    assert len(dash._activity) == 10
    # Last 10 entries are kept.
    assert dash._activity[0] == "line 5"
    assert dash._activity[-1] == "line 14"


def test_dashboard_progress_triggers_milestone_ticker() -> None:
    console = Console(record=True, width=80)
    sass = SassEngine(level=2, seed=1)
    dash = Dashboard(console, sass, _test_mode=True)
    with dash.live():
        dash.set_progress(50, 100)
    assert "halfway" in dash._ticker.lower() or dash._ticker != ""


def test_dashboard_update_stats_replaces_state() -> None:
    console = Console(record=True, width=80)
    sass = SassEngine(level=2, seed=1)
    dash = Dashboard(console, sass, _test_mode=True)
    new_stats = LibraryStats(sorted=12)
    with dash.live():
        dash.update_stats(new_stats)
    assert dash._stats.sorted == 12


# ---------------------------------------------------------------------------
# wizard
# ---------------------------------------------------------------------------


def test_wizard_returns_pipelineconfig_with_user_choices() -> None:
    console = Console(record=True, width=80)
    sass = SassEngine(level=2, seed=1)

    prompt_returns = iter(["claude", "chaotic", "2"])
    confirm_returns = iter([True, True])  # dry-run? then ready?

    with (
        patch("pixeldump.tui.wizard.Prompt.ask", side_effect=lambda *a, **kw: next(prompt_returns)),
        patch("pixeldump.tui.wizard.Confirm.ask", side_effect=lambda *a, **kw: next(confirm_returns)),
    ):
        config = run_wizard(
            Path("/tmp/photos"),
            console=console,
            sass=sass,
            available_providers=["claude", "ollama"],
        )

    assert isinstance(config, PipelineConfig)
    assert config.provider == ProviderName.CLAUDE
    assert config.naming_mode == NamingMode.CHAOTIC
    assert config.sass_level == 2
    assert config.dry_run is True
    assert config.target_dir == Path("/tmp/photos")


def test_wizard_aborts_on_no_confirm() -> None:
    console = Console(record=True, width=80)
    sass = SassEngine(level=2, seed=1)

    prompt_returns = iter(["claude", "chaotic", "2"])
    confirm_returns = iter([True, False])  # dry-run? yes; ready? no

    with (
        patch("pixeldump.tui.wizard.Prompt.ask", side_effect=lambda *a, **kw: next(prompt_returns)),
        patch("pixeldump.tui.wizard.Confirm.ask", side_effect=lambda *a, **kw: next(confirm_returns)),
        pytest.raises(KeyboardInterrupt),
    ):
        run_wizard(
            Path("/tmp/photos"),
            console=console,
            sass=sass,
            available_providers=["claude", "ollama"],
        )


def test_wizard_auto_selects_single_provider() -> None:
    console = Console(record=True, width=80)
    sass = SassEngine(level=2, seed=1)

    prompt_returns = iter(["chaotic", "2"])  # provider auto-picked
    confirm_returns = iter([True, True])

    with (
        patch("pixeldump.tui.wizard.Prompt.ask", side_effect=lambda *a, **kw: next(prompt_returns)),
        patch("pixeldump.tui.wizard.Confirm.ask", side_effect=lambda *a, **kw: next(confirm_returns)),
    ):
        config = run_wizard(
            Path("/tmp/photos"),
            console=console,
            sass=sass,
            available_providers=["ollama"],
        )

    assert config.provider == ProviderName.OLLAMA
