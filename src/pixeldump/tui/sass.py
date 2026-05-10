"""Loads + selects sass lines from assets/sass_lines.json.

Provides ``SassEngine``, which serves themed sass strings based on a sass
``level`` (0..3) and run-time context. Level 0 silences nearly everything;
level 3 is maximally chaotic.
"""
from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any, Final

from pixeldump.core.types import LibraryStats

_SASS_PATH: Final[Path] = (
    Path(__file__).parent.parent / "assets" / "sass_lines.json"
)

_FALLBACK_DUPLICATE_LINE: Final[str] = (
    "you saved this 4 times. it's not that deep. \U0001f480"
)


class SassEngine:
    """Picks sass lines based on level + context. Level 0 returns empty strings."""

    def __init__(self, level: int = 2, seed: int | None = None) -> None:
        # level 0..3, clamp out-of-range
        self.level = max(0, min(3, level))
        self._rng = random.Random(seed)
        with _SASS_PATH.open() as f:
            self._data: dict[str, Any] = json.load(f)

    # -- internal helpers --------------------------------------------------

    def _categories(self) -> dict[str, list[str]]:
        cats = self._data.get("category_triggered", {})
        assert isinstance(cats, dict)
        return cats

    def _milestones(self) -> dict[str, str]:
        ms = self._data.get("milestones", {})
        assert isinstance(ms, dict)
        return ms

    def _idle(self) -> list[str]:
        items = self._data.get("idle", [])
        assert isinstance(items, list)
        return items

    def _taglines(self) -> list[str]:
        items = self._data.get("taglines", [])
        assert isinstance(items, list)
        return items

    def _pick(self, options: list[str]) -> str:
        if not options:
            return ""
        if self.level >= 3:
            # "Most absurd" - pick the longest line as a proxy for spiciest.
            return max(options, key=len)
        return self._rng.choice(options)

    # -- public API --------------------------------------------------------

    def category_line(self, key: str) -> str:
        """Return a sass line for a category trigger, or empty if level <= 1 or key unknown."""
        if self.level < 2:
            return ""
        options = self._categories().get(key)
        if not options:
            return ""
        return self._pick(options)

    def milestone_line(self, percent: int) -> str:
        """Return milestone sass at 25/50/75/90/100, or empty if level <= 0."""
        if self.level <= 0:
            return ""
        return self._milestones().get(str(percent), "")

    def idle_line(self) -> str:
        """Return a random idle/loading line, empty if level < 2."""
        if self.level < 2:
            return ""
        idle = self._idle()
        if not idle:
            return ""
        return self._pick(idle)

    def tagline(self) -> str:
        """Return a random tagline. Always non-empty (taglines are not silenced)."""
        taglines = self._taglines()
        if not taglines:
            return ""
        return self._rng.choice(taglines)

    def stats_findings(self, stats: LibraryStats) -> list[str]:
        """Build a list of context-aware sass strings based on stat counters."""
        if self.level <= 0:
            return []

        findings: list[str] = []
        cats = self._categories()

        def _line(key: str, fallback: str = "") -> str:
            options = cats.get(key)
            if not options:
                return fallback
            return self._pick(options)

        if stats.screenshots >= 50:
            line = _line("screenshot_overload")
            if line:
                findings.append(line)
        if stats.cats >= 1:
            line = _line("cat")
            if line:
                findings.append(line)
        if stats.duplicates >= 4:
            line = _line("duplicate_addiction") or _line("duplicates", _FALLBACK_DUPLICATE_LINE)
            findings.append(line)
        if stats.food >= 50:
            line = _line("food_overload") or _line("food")
            if line:
                findings.append(line)
        if stats.selfies >= 20:
            line = _line("selfie_overload") or _line("selfie")
            if line:
                findings.append(line)

        # Level 3: amplify with an extra idle-style line for flavor.
        if self.level >= 3 and findings:
            extra = self.idle_line()
            if extra:
                findings.append(extra)

        return findings
