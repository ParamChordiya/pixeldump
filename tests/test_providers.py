"""Tests for ClaudeProvider and OllamaProvider. No real network calls."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from pixeldump.core.taxonomy import is_valid_category
from pixeldump.core.types import (
    Classification,
    CostEstimate,
    GPSCoord,
    LibraryStats,
    NamingMode,
    PhotoInput,
    PhotoMetadata,
)
from pixeldump.providers._prompts import _time_of_day, build_cluster_metadata_context
from pixeldump.providers.claude import ClaudeProvider
from pixeldump.providers.claude_code import (
    ClaudeCodeProvider,
    _parse_classification,
    _sanitize_name,
)
from pixeldump.providers.ollama import OllamaProvider

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_photos() -> list[PhotoInput]:
    metadata = PhotoMetadata(
        path=Path("/tmp/fake.jpg"),
        date_taken=datetime(2026, 5, 9, 12, 0, 0),
        gps=None,
        camera_model="Test Cam",
        width=4032,
        height=3024,
        file_size=1234,
    )
    # tiny stand-in JPEG-ish bytes; providers only base64-encode them.
    photo = PhotoInput(metadata=metadata, thumbnail_bytes=b"\xff\xd8\xff\xd9")
    return [photo, photo, photo]


@pytest.fixture
def fake_stats() -> LibraryStats:
    return LibraryStats(
        total_photos=2500,
        sorted=2400,
        duplicates=80,
        screenshots=350,
        cats=42,
        food=60,
        selfies=120,
        needs_review=20,
        folders_created=35,
        elapsed_seconds=187.5,
    )


@pytest.fixture
def mock_anthropic_client() -> Any:
    """Mock the anthropic.Anthropic client; patches at module path used by claude.py."""
    with patch("pixeldump.providers.claude.anthropic.Anthropic") as ctor:
        instance = MagicMock()
        ctor.return_value = instance
        yield instance


@pytest.fixture
def mock_ollama_client() -> Any:
    """Mock ollama.Client; patches at module path used by ollama.py."""
    with patch("pixeldump.providers.ollama.ollama.Client") as ctor:
        instance = MagicMock()
        ctor.return_value = instance
        yield instance


def _anthropic_response(text: str) -> Any:
    block = MagicMock()
    block.text = text
    resp = MagicMock()
    resp.content = [block]
    return resp


def _ollama_response(text: str) -> dict[str, Any]:
    return {"message": {"role": "assistant", "content": text}}


# ---------------------------------------------------------------------------
# ClaudeProvider
# ---------------------------------------------------------------------------


def test_claude_no_api_key_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    provider = ClaudeProvider(api_key=None)
    assert provider.is_available() is False


def test_claude_estimate_cost_positive() -> None:
    provider = ClaudeProvider(api_key="sk-test")
    estimate = provider.estimate_cost(1000)
    assert isinstance(estimate, CostEstimate)
    assert estimate.photo_count == 1000
    assert estimate.estimated_input_tokens > 0
    assert estimate.estimated_output_tokens > 0
    assert estimate.estimated_usd > 0


def test_claude_estimate_cost_zero_photos() -> None:
    provider = ClaudeProvider(api_key="sk-test")
    estimate = provider.estimate_cost(0)
    assert estimate is not None
    assert estimate.estimated_usd == 0.0
    assert estimate.photo_count == 0


def test_claude_classify_cluster_falls_back_on_invalid_category(
    mock_anthropic_client: Any, fake_photos: list[PhotoInput]
) -> None:
    # Model returns a category outside the taxonomy.
    payload = (
        '{"category": "underwater_basket_weaving", "subcategory": null, '
        '"confidence": 0.9, "description": "weaving baskets", "notable": []}'
    )
    mock_anthropic_client.messages.create.return_value = _anthropic_response(payload)

    provider = ClaudeProvider(api_key="sk-test")
    result = provider.classify_cluster(fake_photos)

    assert isinstance(result, Classification)
    assert result.category == "uncategorized"
    assert is_valid_category(result.category)
    assert 0.0 <= result.confidence <= 1.0


def test_claude_classify_cluster_handles_code_fences(
    mock_anthropic_client: Any, fake_photos: list[PhotoInput]
) -> None:
    fenced = (
        "```json\n"
        '{"category": "travel", "subcategory": "international", '
        '"confidence": 0.8, "description": "trip", "notable": ["beach"]}\n'
        "```"
    )
    mock_anthropic_client.messages.create.return_value = _anthropic_response(fenced)

    provider = ClaudeProvider(api_key="sk-test")
    result = provider.classify_cluster(fake_photos)

    assert result.category == "travel"
    assert result.subcategory == "international"
    assert result.notable == ["beach"]


def test_claude_classify_cluster_handles_garbage(
    mock_anthropic_client: Any, fake_photos: list[PhotoInput]
) -> None:
    mock_anthropic_client.messages.create.return_value = _anthropic_response(
        "this is not json at all lol"
    )

    provider = ClaudeProvider(api_key="sk-test")
    result = provider.classify_cluster(fake_photos)

    assert result.category == "uncategorized"
    assert result.confidence == 0.0
    assert result.description == "<parse error>"


def test_claude_name_event_sanitizes_output(
    mock_anthropic_client: Any, fake_photos: list[PhotoInput]
) -> None:
    mock_anthropic_client.messages.create.return_value = _anthropic_response(
        '"Ate Good In Tokyo!!"'
    )

    provider = ClaudeProvider(api_key="sk-test")
    name = provider.name_event(fake_photos, "travel", NamingMode.CHAOTIC)

    assert name == "ate_good_in_tokyo"
    assert len(name) <= 40


def test_claude_name_event_falls_back_on_empty(
    mock_anthropic_client: Any, fake_photos: list[PhotoInput]
) -> None:
    mock_anthropic_client.messages.create.return_value = _anthropic_response("")

    provider = ClaudeProvider(api_key="sk-test")
    name = provider.name_event(fake_photos, "travel", NamingMode.CORPORATE)

    assert name == "travel_event"


def test_claude_generate_roast_caps_at_600(
    mock_anthropic_client: Any, fake_stats: LibraryStats
) -> None:
    long_text = "ok " * 1000  # well over 600 chars
    mock_anthropic_client.messages.create.return_value = _anthropic_response(long_text)

    provider = ClaudeProvider(api_key="sk-test")
    roast = provider.generate_roast(fake_stats)

    assert len(roast) <= 600
    assert roast


# ---------------------------------------------------------------------------
# OllamaProvider
# ---------------------------------------------------------------------------


def test_ollama_unreachable_is_unavailable() -> None:
    # Use port 1 (privileged, will refuse) so even a real attempt fails fast.
    provider = OllamaProvider(host="http://127.0.0.1:1", model="gemma3")
    # Replace the client with one whose list() always raises.
    bad = MagicMock()
    bad.list.side_effect = ConnectionError("boom")
    provider._client = bad  # noqa: SLF001 - intentional override for test
    assert provider.is_available() is False


def test_ollama_estimate_cost_is_none() -> None:
    provider = OllamaProvider(host="http://127.0.0.1:1", model="gemma3")
    assert provider.estimate_cost(0) is None
    assert provider.estimate_cost(10_000) is None


def test_ollama_classify_cluster_invalid_json_falls_back(
    mock_ollama_client: Any, fake_photos: list[PhotoInput]
) -> None:
    mock_ollama_client.chat.return_value = _ollama_response("definitely not json {[}")

    provider = OllamaProvider(host="http://localhost:11434", model="gemma3")
    # Skip the availability probe by pre-priming the cache.
    provider._available_cache = True  # noqa: SLF001
    result = provider.classify_cluster(fake_photos)

    assert isinstance(result, Classification)
    assert result.category == "uncategorized"
    assert is_valid_category(result.category)
    assert result.confidence == 0.0


def test_ollama_classify_cluster_invalid_category_falls_back(
    mock_ollama_client: Any, fake_photos: list[PhotoInput]
) -> None:
    mock_ollama_client.chat.return_value = _ollama_response(
        '{"category": "alien_abduction", "subcategory": null, '
        '"confidence": 0.99, "description": "ufos", "notable": []}'
    )

    provider = OllamaProvider(host="http://localhost:11434", model="gemma3")
    provider._available_cache = True  # noqa: SLF001
    result = provider.classify_cluster(fake_photos)

    assert result.category == "uncategorized"
    assert is_valid_category(result.category)


def test_ollama_classify_cluster_valid(
    mock_ollama_client: Any, fake_photos: list[PhotoInput]
) -> None:
    mock_ollama_client.chat.return_value = _ollama_response(
        '{"category": "everyday", "subcategory": "cat", '
        '"confidence": 1.5, "description": "cat", "notable": ["meow"]}'
    )

    provider = OllamaProvider(host="http://localhost:11434", model="gemma3")
    provider._available_cache = True  # noqa: SLF001
    result = provider.classify_cluster(fake_photos)

    assert result.category == "everyday"
    assert result.subcategory == "cat"
    # Confidence clamped to <=1.0.
    assert result.confidence == 1.0
    assert result.notable == ["meow"]


def test_ollama_name_event_sanitizes(
    mock_ollama_client: Any, fake_photos: list[PhotoInput]
) -> None:
    mock_ollama_client.chat.return_value = _ollama_response(
        "Here is a great name: PROOF I Went Outside Once!"
    )

    provider = OllamaProvider(host="http://localhost:11434", model="gemma3")
    provider._available_cache = True  # noqa: SLF001
    name = provider.name_event(fake_photos, "everyday", NamingMode.UNHINGED)

    # First non-empty line gets sanitized; should still be snake_case.
    assert name == name.lower()
    assert " " not in name
    assert len(name) <= 40
    assert name  # non-empty


def test_ollama_chat_failure_returns_safe_classification(
    mock_ollama_client: Any, fake_photos: list[PhotoInput]
) -> None:
    mock_ollama_client.chat.side_effect = TimeoutError("ollama is napping")

    provider = OllamaProvider(host="http://localhost:11434", model="gemma3")
    provider._available_cache = True  # noqa: SLF001
    result = provider.classify_cluster(fake_photos)

    assert result.category == "uncategorized"
    assert result.confidence == 0.0


def test_ollama_chat_failure_returns_fallback_name(
    mock_ollama_client: Any, fake_photos: list[PhotoInput]
) -> None:
    mock_ollama_client.chat.side_effect = TimeoutError("nope")

    provider = OllamaProvider(host="http://localhost:11434", model="gemma3")
    provider._available_cache = True  # noqa: SLF001
    name = provider.name_event(fake_photos, "social", NamingMode.CORPORATE)

    assert name == "social_event"


def test_ollama_is_available_when_model_listed(mock_ollama_client: Any) -> None:
    # Build a fake list response resembling the SDK's ListResponse.
    model_entry = MagicMock()
    model_entry.model = "gemma3:latest"
    listing = MagicMock()
    listing.models = [model_entry]
    mock_ollama_client.list.return_value = listing

    provider = OllamaProvider(host="http://localhost:11434", model="gemma3")
    assert provider.is_available() is True


def test_ollama_falls_back_to_available_model(mock_ollama_client: Any) -> None:
    # gemma3 missing, but llava present.
    entry = MagicMock()
    entry.model = "llava:latest"
    listing = MagicMock()
    listing.models = [entry]
    mock_ollama_client.list.return_value = listing

    provider = OllamaProvider(host="http://localhost:11434", model="gemma3")
    assert provider.is_available() is True
    assert provider.model == "llava"


# ---------------------------------------------------------------------------
# ClaudeCodeProvider
# ---------------------------------------------------------------------------


def test_claude_code_unavailable_when_cli_missing() -> None:
    with patch("pixeldump.providers.claude_code.shutil.which", return_value=None):
        provider = ClaudeCodeProvider()
        assert provider.is_available() is False


def test_claude_code_unavailable_when_version_fails() -> None:
    with (
        patch("pixeldump.providers.claude_code.shutil.which", return_value="/usr/bin/claude"),
        patch("pixeldump.providers.claude_code.subprocess.run") as mock_run,
    ):
        mock_run.return_value = MagicMock(returncode=1)
        provider = ClaudeCodeProvider()
        assert provider.is_available() is False


def test_claude_code_available_when_version_succeeds() -> None:
    with (
        patch("pixeldump.providers.claude_code.shutil.which", return_value="/usr/bin/claude"),
        patch("pixeldump.providers.claude_code.subprocess.run") as mock_run,
    ):
        mock_run.return_value = MagicMock(returncode=0)
        provider = ClaudeCodeProvider()
        assert provider.is_available() is True


def test_claude_code_caches_availability() -> None:
    with (
        patch("pixeldump.providers.claude_code.shutil.which", return_value="/usr/bin/claude"),
        patch("pixeldump.providers.claude_code.subprocess.run") as mock_run,
    ):
        mock_run.return_value = MagicMock(returncode=0)
        provider = ClaudeCodeProvider()
        provider.is_available()
        provider.is_available()
        assert mock_run.call_count == 1


def test_claude_code_call_raises_when_cli_none() -> None:
    provider = ClaudeCodeProvider()
    provider._cli = None  # noqa: SLF001
    with pytest.raises(RuntimeError):
        provider._call("sys", "user")  # noqa: SLF001


def test_claude_code_parse_classification_valid() -> None:
    payload = (
        '{"category": "travel", "subcategory": "international", '
        '"confidence": 0.85, "description": "trip abroad", "notable": ["beach"]}'
    )
    result = _parse_classification(payload)
    assert isinstance(result, Classification)
    assert result.category == "travel"
    assert result.subcategory == "international"
    assert result.confidence == 0.85
    assert result.notable == ["beach"]


def test_claude_code_parse_classification_empty() -> None:
    result = _parse_classification("")
    assert result.category == "uncategorized"
    assert result.confidence == 0.0


def test_claude_code_parse_classification_invalid_json() -> None:
    result = _parse_classification("not json at all lol }{")
    assert result.category == "uncategorized"


def test_claude_code_sanitize_name_basic() -> None:
    assert _sanitize_name("Ate Good In Tokyo!!", "fallback") == "ate_good_in_tokyo"


def test_claude_code_sanitize_name_empty_returns_fallback() -> None:
    assert _sanitize_name("", "my_fallback") == "my_fallback"


def test_claude_code_sanitize_name_clamps_to_40() -> None:
    long_input = "a" * 60 + " extra words here"
    result = _sanitize_name(long_input, "fallback")
    assert len(result) <= 40


# ---------------------------------------------------------------------------
# build_cluster_metadata_context / _time_of_day
# ---------------------------------------------------------------------------


def _make_photo_input(
    filename: str = "IMG_001.jpg",
    gps: GPSCoord | None = None,
    camera_model: str | None = "iPhone 15",
    date_taken: datetime | None = datetime(2024, 6, 15, 14, 30, 0),
) -> PhotoInput:
    meta = PhotoMetadata(
        path=Path(f"/tmp/{filename}"),
        date_taken=date_taken,
        gps=gps,
        camera_model=camera_model,
        width=4032,
        height=3024,
        file_size=2_000_000,
    )
    return PhotoInput(metadata=meta, thumbnail_bytes=b"\xff\xd8\xff\xd9")


def test_metadata_context_empty_list_returns_empty_string() -> None:
    assert build_cluster_metadata_context([]) == ""


def test_metadata_context_includes_filename() -> None:
    photo = _make_photo_input(filename="IMG_9999.jpg")
    result = build_cluster_metadata_context([photo])
    assert "IMG_9999.jpg" in result


def test_metadata_context_includes_gps() -> None:
    photo = _make_photo_input(gps=GPSCoord(35.6762, 139.6503))
    result = build_cluster_metadata_context([photo])
    assert "35.67620" in result
    assert "139.65030" in result


def test_metadata_context_no_gps_says_none() -> None:
    photo = _make_photo_input(gps=None)
    result = build_cluster_metadata_context([photo])
    assert "none" in result.lower()


def test_metadata_context_includes_camera_model() -> None:
    photo = _make_photo_input(camera_model="iPhone 15 Pro")
    result = build_cluster_metadata_context([photo])
    assert "iPhone 15 Pro" in result


def test_metadata_context_cluster_summary_centroid() -> None:
    p1 = _make_photo_input(gps=GPSCoord(35.6762, 139.6503))
    p2 = _make_photo_input(gps=GPSCoord(35.6800, 139.6600))
    result = build_cluster_metadata_context([p1, p2])
    assert "location centroid" in result


def test_time_of_day_early_morning() -> None:
    assert _time_of_day(6) == "early morning"


def test_time_of_day_evening() -> None:
    assert _time_of_day(19) == "evening"


def test_time_of_day_night() -> None:
    assert _time_of_day(23) == "night"


def test_time_of_day_morning() -> None:
    assert _time_of_day(10) == "morning"
