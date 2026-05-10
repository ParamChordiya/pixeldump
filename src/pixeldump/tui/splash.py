"""Animated splash screen on startup (non-blocking, no input wait)."""
from __future__ import annotations

from pathlib import Path
from typing import Final

from rich.align import Align
from rich.console import Console, Group
from rich.panel import Panel
from rich.text import Text

from pixeldump.tui.sass import SassEngine

_LOGO_PATH: Final[Path] = (
    Path(__file__).parent.parent / "assets" / "logo.txt"
)


def _gradient_logo(text: str) -> Text:
    """Render the logo with a magenta -> cyan gradient across rows."""
    lines = text.splitlines() or [text]
    palette = [
        "magenta",
        "bright_magenta",
        "bright_blue",
        "blue",
        "cyan",
        "bright_cyan",
    ]
    out = Text()
    n = max(1, len(lines))
    for i, line in enumerate(lines):
        # map row index to palette
        idx = min(len(palette) - 1, int(i / n * len(palette)))
        style = f"bold {palette[idx]}"
        out.append(line, style=style)
        if i != n - 1:
            out.append("\n")
    return out


def render_splash(console: Console, sass: SassEngine) -> None:
    """Print the ASCII logo + tagline to console (no animation, no input wait)."""
    try:
        logo_text = _LOGO_PATH.read_text()
    except OSError:
        logo_text = "PIXELDUMP"

    logo = _gradient_logo(logo_text)
    tagline = Text(sass.tagline(), style="italic dim")

    body = Group(Align.center(logo), Text(""), Align.center(tagline))
    panel = Panel(body, border_style="magenta", padding=(1, 2))
    console.print(panel)
