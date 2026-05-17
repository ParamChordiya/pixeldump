"""User config loading from YAML in the platformdirs config home."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import platformdirs
import yaml  # type: ignore[import-untyped]

DEFAULT_CONFIG: dict[str, Any] = {
    "provider": "auto",
    "claude_api_key": None,
    "ollama_host": "http://localhost:11434",
    "ollama_model": "gemma3",
    "naming_mode": "chaotic",
    "sass_level": 2,
    "burst_hours": 72,
    "batch_size": 5,
    "concurrency": 4,
    "default_dry_run": True,
}


def default_config_path() -> Path:
    """Return the user's platform-specific config file path."""
    return Path(platformdirs.user_config_dir("pixeldump", appauthor=False)) / "config.yaml"


def load_config(path: Path | None = None) -> dict[str, Any]:
    """Load YAML config from path (or default).

    Returns DEFAULT_CONFIG merged with whatever's in the file (file values win).
    Missing file returns a copy of DEFAULT_CONFIG.
    """
    target = path if path is not None else default_config_path()
    merged: dict[str, Any] = dict(DEFAULT_CONFIG)
    if not target.exists():
        return merged
    try:
        raw: Any = yaml.safe_load(target.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"Failed to parse config at {target}: {exc}") from exc
    if raw is None:
        return merged
    if not isinstance(raw, dict):
        raise ValueError(f"Config at {target} must be a mapping at the top level, got {type(raw).__name__}")
    merged.update(raw)
    return merged


def save_config(data: dict[str, Any], path: Path | None = None) -> None:
    """Persist YAML config to path (or default)."""
    target = path if path is not None else default_config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    text: str = yaml.safe_dump(data, sort_keys=True)
    target.write_text(text, encoding="utf-8")
    target.chmod(0o600)  # config may contain API keys — not world-readable
