"""Live progress dashboard rendered during a pipeline run.

This module intentionally uses Rich's ``Live`` + ``Progress`` + ``Layout`` rather
than a full-screen Textual app. That gives a visually rich progress experience
while staying simple, deterministic, and testable. A future wave can upgrade
this to a Textual reactive app without changing the public ``Dashboard`` API.
"""
from __future__ import annotations

from collections import deque
from collections.abc import Iterator
from contextlib import contextmanager

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.progress import Progress, TaskID
from rich.text import Text

from pixeldump.core.types import LibraryStats, Phase
from pixeldump.tui.receipt import print_receipt as _print_receipt
from pixeldump.tui.sass import SassEngine
from pixeldump.tui.widgets import (
    build_progress,
    phase_label,
    phase_label_plain,
    stats_panel,
)

_ACTIVITY_CAP = 10


class Dashboard:
    """Rich-Live based dashboard. Owns rendering; does not drive the pipeline.

    Usage::

        dash = Dashboard(console, sass)
        with dash.live():
            dash.set_phase(Phase.SCANNING)
            for i in range(total):
                dash.set_progress(i, total)
            dash.add_activity("\U0001f4f8 IMG_4021.jpg → 2024/event/")
            dash.update_stats(stats)
        dash.print_receipt(stats, run_id)

    A private ``_test_mode`` knob disables the Live display so tests can
    exercise state transitions without spinning a terminal.
    """

    def __init__(
        self,
        console: Console,
        sass: SassEngine,
        *,
        plain_phase_labels: bool = False,
        _test_mode: bool = False,
    ) -> None:
        self._console = console
        self._sass = sass
        self._plain_labels = plain_phase_labels
        self._test_mode = _test_mode

        self._phase: Phase = Phase.SETUP
        self._stats: LibraryStats = LibraryStats()
        self._activity: deque[str] = deque(maxlen=_ACTIVITY_CAP)
        self._ticker: str = ""
        self._completed: int = 0
        self._total: int = 0
        self._last_milestone: int = -1

        self._progress: Progress = build_progress()
        self._task_id: TaskID | None = None
        self._live: Live | None = None

    # -- layout -----------------------------------------------------------

    def _label_for(self, phase: Phase) -> str:
        return phase_label_plain(phase) if self._plain_labels else phase_label(phase)

    def _build_layout(self) -> Layout:
        layout = Layout(name="root")
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="body", ratio=1),
            Layout(name="footer", size=5),
        )
        layout["body"].split_row(
            Layout(name="activity", ratio=2),
            Layout(name="stats", ratio=1),
        )

        header_text = Text(self._label_for(self._phase), style="bold magenta")
        layout["header"].update(Panel(header_text, border_style="magenta"))

        if self._activity:
            activity_body = Text("\n".join(self._activity))
        else:
            activity_body = Text("(waiting for activity…)", style="dim")
        layout["activity"].update(
            Panel(activity_body, title="activity", border_style="cyan")
        )

        layout["stats"].update(stats_panel(self._stats, sass=self._sass))

        ticker = Text(self._ticker or "", style="italic dim")
        layout["footer"].split_column(
            Layout(self._progress, name="progress", size=3),
            Layout(ticker, name="ticker", size=2),
        )
        return layout

    def _refresh(self) -> None:
        if self._test_mode or self._live is None:
            return
        self._live.update(self._build_layout(), refresh=True)

    # -- lifecycle --------------------------------------------------------

    @contextmanager
    def live(self) -> Iterator[None]:
        """Context manager that activates the Live display (no-op in test mode)."""
        if self._test_mode:
            yield
            return

        self._task_id = self._progress.add_task(self._label_for(self._phase), total=None)
        with Live(
            self._build_layout(),
            console=self._console,
            refresh_per_second=8,
            transient=False,
        ) as live:
            self._live = live
            try:
                yield
            finally:
                self._live = None
                self._progress.stop()

    # -- mutators ---------------------------------------------------------

    def set_phase(self, phase: Phase) -> None:
        self._phase = phase
        if self._task_id is not None:
            self._progress.update(self._task_id, description=self._label_for(phase))
        self._refresh()

    def set_progress(self, completed: int, total: int) -> None:
        self._completed = completed
        self._total = total
        if self._task_id is not None:
            self._progress.update(self._task_id, completed=completed, total=total)

        if total > 0:
            percent = int(100 * completed / total)
            for milestone in (25, 50, 75, 90, 100):
                if percent >= milestone > self._last_milestone:
                    line = self._sass.milestone_line(milestone)
                    if line:
                        self._ticker = line
                    self._last_milestone = milestone
        self._refresh()

    def add_activity(self, line: str) -> None:
        self._activity.append(line)
        self._refresh()

    def update_stats(self, stats: LibraryStats) -> None:
        self._stats = stats
        self._refresh()

    # -- output -----------------------------------------------------------

    def print_receipt(self, stats: LibraryStats, run_id: str) -> None:
        """Print the post-run receipt panel."""
        _print_receipt(self._console, stats, run_id, self._sass)
