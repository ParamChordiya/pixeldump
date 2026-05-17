"""Claude Code CLI provider — no API key required.

Delegates vision calls to the local `claude` CLI, reusing the user's
existing Claude Code authenticated session. No ANTHROPIC_API_KEY or
Ollama installation needed; just `claude --version` must succeed.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from pixeldump.core.taxonomy import is_valid_category
from pixeldump.core.types import (
    Classification,
    CostEstimate,
    LibraryStats,
    NamingMode,
    PhotoInput,
)
from pixeldump.providers._prompts import (
    CLASSIFY_SYSTEM_PROMPT,
    build_cluster_metadata_context,
    build_name_prompt,
    build_roast_prompt,
)
from pixeldump.providers.base import VisionProvider

_NAME_CLEAN_RE = re.compile(r"[^a-z0-9_]+")


class ClaudeCodeProvider(VisionProvider):
    """Vision provider that delegates to the local ``claude`` CLI.

    Piggybacks on the authenticated Claude Code session so the user
    never has to enter a separate API key. Each call spawns a subprocess;
    expect slightly higher latency than the direct API provider.

    Requirements:
      - ``claude`` binary on PATH (install from https://claude.ai/code)
      - An active Claude Code login (``claude --version`` must exit 0)
    """

    name = "claude-code"

    def __init__(self, timeout: int = 120) -> None:
        self._timeout = timeout
        self._cli: str | None = shutil.which("claude")

    # ── availability ─────────────────────────────────────────────────────────

    def is_available(self) -> bool:
        """Return True if the ``claude`` CLI is installed and responsive."""
        if self._cli is None:
            return False
        try:
            result = subprocess.run(
                [self._cli, "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, OSError):
            return False

    # ── cost ─────────────────────────────────────────────────────────────────

    def estimate_cost(self, num_photos: int) -> CostEstimate | None:
        # Free — all usage runs inside the user's existing Claude Code plan.
        return None

    # ── main ops ─────────────────────────────────────────────────────────────

    def classify_cluster(self, photos: list[PhotoInput]) -> Classification:
        with tempfile.TemporaryDirectory(prefix="pixeldump_") as tmpdir:
            image_paths = _write_thumbnails(Path(tmpdir), photos)
            metadata_ctx = build_cluster_metadata_context(photos)
            user_msg = (
                f"{metadata_ctx}\n\n"
                "Read each image file listed below, then classify the cluster "
                "using the metadata above AND the visuals. "
                "Respond with ONLY the JSON object.\n\n"
                "Image files:\n" + "\n".join(f"- {p}" for p in image_paths)
            )
            raw = self._call(CLASSIFY_SYSTEM_PROMPT, user_msg)
        return _parse_classification(raw)

    def name_event(
        self,
        photos: list[PhotoInput],
        category: str,
        mode: NamingMode,
    ) -> str:
        fallback = f"{category}_event"
        sampled = photos[:3]
        with tempfile.TemporaryDirectory(prefix="pixeldump_") as tmpdir:
            image_paths = _write_thumbnails(Path(tmpdir), sampled)
            meta_ctx = build_cluster_metadata_context(sampled)
            user_msg = (
                build_name_prompt(category, mode, meta_ctx)
                + "\n\nImage files:\n"
                + "\n".join(f"- {p}" for p in image_paths)
            )
            raw = self._call("", user_msg).strip()
        return _sanitize_name(raw, fallback)

    def generate_roast(self, stats: LibraryStats) -> str:
        raw = self._call("", build_roast_prompt(stats)).strip()
        return raw[:600] if raw else "(roast unavailable — claude-code did not respond)"

    # ── internals ─────────────────────────────────────────────────────────────

    def _call(self, system: str, user: str) -> str:
        """Run ``claude -p`` non-interactively and return the raw text response.

        System and user content are combined into a single prompt string
        because the CLI does not expose a separate --system-prompt flag.
        The Read tool is explicitly allowed so Claude can open the temp
        thumbnail files without interactive permission prompts.
        """
        assert self._cli is not None  # guarded by is_available()
        prompt = f"{system}\n\n{user}".strip() if system else user
        try:
            result = subprocess.run(
                [self._cli, "-p", prompt, "--allowedTools", "Read"],
                capture_output=True,
                text=True,
                timeout=self._timeout,
            )
        except (subprocess.TimeoutExpired, OSError):
            return ""
        if result.returncode != 0:
            return ""
        return result.stdout.strip()


# ── helpers ───────────────────────────────────────────────────────────────────


def _write_thumbnails(tmpdir: Path, photos: list[PhotoInput]) -> list[Path]:
    """Write photo thumbnails to *tmpdir* and return their paths."""
    paths: list[Path] = []
    for i, photo in enumerate(photos):
        p = tmpdir / f"photo_{i:02d}.jpg"
        p.write_bytes(photo.thumbnail_bytes)
        paths.append(p)
    return paths


def _strip_code_fence(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _extract_json_object(text: str) -> str:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return text
    return text[start : end + 1]


def _parse_classification(text: str) -> Classification:
    """Parse a JSON classification response defensively. Never raises."""
    _error = Classification(
        category="uncategorized",
        subcategory=None,
        confidence=0.0,
        description="<parse error>",
        notable=[],
    )
    if not text:
        return _error
    cleaned = _extract_json_object(_strip_code_fence(text))
    try:
        data = json.loads(cleaned)
    except (json.JSONDecodeError, ValueError):
        return _error
    if not isinstance(data, dict):
        return _error

    category = str(data.get("category", "uncategorized"))
    if not is_valid_category(category):
        category = "uncategorized"

    raw_sub = data.get("subcategory")
    subcategory: str | None = str(raw_sub) if isinstance(raw_sub, str) and raw_sub else None

    try:
        confidence = float(data.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    description = str(data.get("description", "")).strip()
    raw_notable = data.get("notable", [])
    notable: list[str] = (
        [str(x) for x in raw_notable if isinstance(x, (str, int, float))]
        if isinstance(raw_notable, list)
        else []
    )
    return Classification(
        category=category,
        subcategory=subcategory,
        confidence=confidence,
        description=description,
        notable=notable,
    )


def _sanitize_name(raw: str, fallback: str) -> str:
    """Coerce model output into a clean snake_case folder name (≤40 chars)."""
    text = raw.strip().strip("`")
    for line in text.splitlines():
        if line.strip():
            text = line.strip()
            break
    text = text.strip("\"'")
    text = text.lower().replace(" ", "_").replace("-", "_")
    text = _NAME_CLEAN_RE.sub("", text)
    text = re.sub(r"_+", "_", text).strip("_")
    if not text:
        return fallback
    return text[:40].rstrip("_") or fallback
