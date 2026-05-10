"""Tests for pixeldump.config."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from pixeldump.config import (
    DEFAULT_CONFIG,
    default_config_path,
    load_config,
    save_config,
)


def test_load_default_config_when_no_file(tmp_path: Path) -> None:
    path = tmp_path / "nope" / "config.yaml"
    cfg = load_config(path)
    for key in DEFAULT_CONFIG:
        assert key in cfg
    assert cfg["provider"] == "auto"
    assert cfg["sass_level"] == 2


def test_save_then_load_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    payload = dict(DEFAULT_CONFIG)
    payload["provider"] = "claude"
    payload["sass_level"] = 3
    save_config(payload, path)

    loaded = load_config(path)
    assert loaded["provider"] == "claude"
    assert loaded["sass_level"] == 3


def test_load_merges_user_overrides(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump({"provider": "ollama", "sass_level": 0}), encoding="utf-8")

    cfg = load_config(path)

    # File values win
    assert cfg["provider"] == "ollama"
    assert cfg["sass_level"] == 0
    # Defaults persist for keys not in the file
    assert cfg["ollama_host"] == DEFAULT_CONFIG["ollama_host"]
    assert cfg["batch_size"] == DEFAULT_CONFIG["batch_size"]


def test_save_creates_parent_dirs(tmp_path: Path) -> None:
    path = tmp_path / "deeply" / "nested" / "config.yaml"
    save_config({"provider": "auto"}, path)
    assert path.exists()
    assert path.parent.is_dir()


def test_default_config_path_is_under_platformdirs() -> None:
    p = default_config_path()
    assert "pixeldump" in p.parts
    assert p.name == "config.yaml"


def test_load_invalid_yaml_raises(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    # Unclosed flow sequence is unambiguously invalid YAML.
    path.write_text("foo: [1, 2, 3\nbar: baz\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_config(path)


def test_load_non_mapping_yaml_raises(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text("- just\n- a\n- list\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_config(path)
