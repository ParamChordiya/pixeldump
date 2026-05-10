"""Click-based CLI tests."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner
from PIL import Image

from pixeldump.cli import main
from pixeldump.core.types import (
    Classification,
    LibraryStats,
    MoveOperation,
    RunManifest,
)
from pixeldump.providers.base import VisionProvider


def _make_jpg(p: Path) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (50, 50), (255, 0, 0)).save(p, "JPEG")


def _mock_provider(*, available: bool = True, name: str = "claude") -> MagicMock:
    p = MagicMock(spec=VisionProvider)
    p.name = name
    p.is_available.return_value = available
    p.classify_cluster.return_value = Classification(
        category="travel",
        subcategory="city_break",
        confidence=0.9,
        description="trip",
        notable=[],
    )
    p.name_event.return_value = "test_trip"
    p.estimate_cost.return_value = None
    return p


def test_cli_help_works() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "PixelDump" in result.output


def test_cli_run_quiet_no_wizard_with_mock_provider(tmp_path: Path) -> None:
    src = tmp_path / "src"
    _make_jpg(src / "a.jpg")
    _make_jpg(src / "b.jpg")

    runner = CliRunner()
    with patch("pixeldump.cli._instantiate_provider", return_value=_mock_provider()):
        result = runner.invoke(
            main,
            ["run", str(src), "--quiet", "--no-wizard", "--provider", "claude"],
        )
    assert result.exit_code == 0, result.output
    assert "done." in result.output


def test_cli_run_no_provider_available_exits_2(tmp_path: Path) -> None:
    src = tmp_path / "src"
    _make_jpg(src / "a.jpg")

    runner = CliRunner()
    with patch("pixeldump.cli._instantiate_provider", return_value=None):
        result = runner.invoke(
            main,
            ["run", str(src), "--quiet", "--no-wizard", "--provider", "claude"],
        )
    assert result.exit_code == 2


def test_cli_run_estimate_flag(tmp_path: Path) -> None:
    src = tmp_path / "src"
    _make_jpg(src / "a.jpg")
    _make_jpg(src / "b.jpg")

    runner = CliRunner()
    with patch("pixeldump.cli._instantiate_provider", return_value=_mock_provider()):
        result = runner.invoke(
            main,
            ["run", str(src), "--estimate", "--no-wizard", "--provider", "ollama"],
        )
    assert result.exit_code == 0, result.output
    assert "photos" in result.output


def test_cli_undo_with_yes_flag(tmp_path: Path) -> None:
    # Create a real source path location and a destination file to undo.
    src = tmp_path / "src" / "a.jpg"
    src.parent.mkdir(parents=True, exist_ok=True)
    dst = tmp_path / "out" / "2024" / "2024_03_trip" / "a.jpg"
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(b"hello")

    manifest = RunManifest(
        version="1.0",
        run_id="20260509_120000",
        provider="claude",
        naming_mode="chaotic",
        started_at=datetime(2026, 5, 9, 12, 0, 0),
        completed_at=datetime(2026, 5, 9, 12, 0, 30),
        operations=[
            MoveOperation(
                action="move",
                source=src,
                destination=dst,
                timestamp=datetime(2026, 5, 9, 12, 0, 15),
            )
        ],
        stats=LibraryStats(),
    )
    from pixeldump.utils.state import write_manifest

    out_path = write_manifest(tmp_path, manifest)

    runner = CliRunner()
    result = runner.invoke(main, ["undo", str(out_path), "--yes"])
    assert result.exit_code == 0, result.output
    assert src.exists(), "file should be moved back to source"
    assert not dst.exists(), "destination should now be empty"
    assert "undid 1" in result.output


def test_cli_config_print(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    cfg_path = tmp_path / "config.yaml"
    monkeypatch.setattr("pixeldump.cli.default_config_path", lambda: cfg_path)

    runner = CliRunner()
    result = runner.invoke(main, ["config"])
    assert result.exit_code == 0, result.output
    # Default config keys present.
    assert "provider:" in result.output
    assert "naming_mode:" in result.output


def test_cli_config_reset_with_confirm(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    cfg_path = tmp_path / "subdir" / "config.yaml"
    monkeypatch.setattr("pixeldump.cli.default_config_path", lambda: cfg_path)

    runner = CliRunner()
    # 'y' confirms the reset prompt.
    result = runner.invoke(main, ["config", "--reset"], input="y\n")
    assert result.exit_code == 0, result.output
    assert cfg_path.exists()
    text = cfg_path.read_text()
    assert "naming_mode" in text


def test_cli_status_no_manifests_dir(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["status", str(tmp_path)])
    assert result.exit_code == 0
    assert "no .pixeldump" in result.output or "no manifests" in result.output


def test_cli_status_with_manifest(tmp_path: Path) -> None:
    manifest = RunManifest(
        version="1.0",
        run_id="20260509_120000",
        provider="claude",
        naming_mode="chaotic",
        started_at=datetime(2026, 5, 9, 12, 0, 0),
        completed_at=datetime(2026, 5, 9, 12, 0, 30),
        operations=[],
        stats=LibraryStats(total_photos=42, sorted=40),
    )
    from pixeldump.utils.state import write_manifest

    write_manifest(tmp_path, manifest)
    runner = CliRunner()
    result = runner.invoke(main, ["status", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "20260509_120000" in result.output
    assert "claude" in result.output
