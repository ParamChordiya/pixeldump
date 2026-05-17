"""Anthropic Claude vision provider."""
from __future__ import annotations

import base64
import json
import math
import os
import re
import time
from collections.abc import Callable
from typing import Any, TypeVar

import anthropic

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

# Pricing (USD per 1M tokens) for claude-sonnet-4-class models. Approximate.
_INPUT_USD_PER_MTOK: float = 3.0
_OUTPUT_USD_PER_MTOK: float = 15.0

# Per-call token budgets used for cost estimation.
_TOKENS_PER_THUMBNAIL: int = 250
_PROMPT_OVERHEAD_TOKENS: int = 250
_OUTPUT_TOKENS_PER_CALL: int = 200
_PHOTOS_PER_CLUSTER: int = 5

T = TypeVar("T")


def _strip_code_fence(text: str) -> str:
    """Strip ```json ... ``` or ``` ... ``` fencing if present."""
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    # Remove leading fence (with optional language tag) and trailing fence.
    lines = stripped.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _extract_json_object(text: str) -> str:
    """Best-effort: return the substring from the first '{' to its matching '}'."""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return text
    return text[start : end + 1]


_NAME_CLEAN_RE = re.compile(r"[^a-z0-9_]+")


def _sanitize_folder_name(raw: str, fallback: str) -> str:
    """Coerce model output into a clean snake_case folder name (<=40 chars)."""
    text = raw.strip().strip("`").strip()
    # Take the first non-empty line - models sometimes add explanations.
    for line in text.splitlines():
        if line.strip():
            text = line.strip()
            break
    # Strip surrounding quotes (single, double, smart).
    text = text.strip("\"'“”‘’")
    text = text.lower().replace(" ", "_").replace("-", "_")
    text = _NAME_CLEAN_RE.sub("", text)
    text = text.strip("_")
    text = re.sub(r"_+", "_", text)
    if not text:
        return fallback
    return text[:40].rstrip("_") or fallback


class ClaudeProvider(VisionProvider):
    """Vision provider backed by the Anthropic API."""

    name = "claude"

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "claude-sonnet-4-20250514",
    ) -> None:
        resolved_key = api_key if api_key is not None else os.environ.get("ANTHROPIC_API_KEY")
        self._api_key: str | None = resolved_key
        self.model: str = model
        self._client: anthropic.Anthropic | None = (
            anthropic.Anthropic(api_key=resolved_key) if resolved_key else None
        )
        self._available_cache: bool | None = None

    # --- availability -------------------------------------------------------

    def is_available(self) -> bool:
        """Return True iff API key is set AND a cheap probe call succeeds."""
        if self._available_cache is not None:
            return self._available_cache
        if self._client is None or not self._api_key:
            self._available_cache = False
            return False
        try:
            # Cheap probe: 1-token completion. Any successful response is enough.
            self._client.messages.create(
                model=self.model,
                max_tokens=1,
                messages=[{"role": "user", "content": "hi"}],
            )
            self._available_cache = True
        except (anthropic.APIError, Exception):
            self._available_cache = False
        return self._available_cache

    # --- cost ---------------------------------------------------------------

    def estimate_cost(self, num_photos: int) -> CostEstimate | None:
        if num_photos <= 0:
            return CostEstimate(
                estimated_usd=0.0,
                estimated_input_tokens=0,
                estimated_output_tokens=0,
                photo_count=0,
            )
        clusters = max(1, math.ceil(num_photos / _PHOTOS_PER_CLUSTER))
        # Two calls per cluster: classify + name.
        calls = clusters * 2
        input_per_call = (
            _PHOTOS_PER_CLUSTER * _TOKENS_PER_THUMBNAIL + _PROMPT_OVERHEAD_TOKENS
        )
        total_input = calls * input_per_call
        total_output = calls * _OUTPUT_TOKENS_PER_CALL
        usd = (
            total_input / 1_000_000 * _INPUT_USD_PER_MTOK
            + total_output / 1_000_000 * _OUTPUT_USD_PER_MTOK
        )
        return CostEstimate(
            estimated_usd=round(usd, 4),
            estimated_input_tokens=total_input,
            estimated_output_tokens=total_output,
            photo_count=num_photos,
        )

    # --- main ops -----------------------------------------------------------

    def classify_cluster(self, photos: list[PhotoInput]) -> Classification:
        client = self._require_client()
        sampled = photos[:_PHOTOS_PER_CLUSTER]
        content_blocks: list[dict[str, Any]] = []
        metadata_text = build_cluster_metadata_context(sampled)
        if metadata_text:
            content_blocks.append({"type": "text", "text": metadata_text})
        for photo in sampled:
            content_blocks.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": photo.thumbnail_media_type,
                        "data": base64.b64encode(photo.thumbnail_bytes).decode("ascii"),
                    },
                }
            )
        content_blocks.append(
            {
                "type": "text",
                "text": "Using the metadata above and the images, classify this cluster. Respond with only the JSON object.",
            }
        )
        try:
            resp = self._call_with_retry(
                lambda: client.messages.create(
                    model=self.model,
                    max_tokens=400,
                    system=CLASSIFY_SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": content_blocks}],  # type: ignore[typeddict-item]
                )
            )
        except anthropic.APIError:
            return _parse_error_classification()

        text = _extract_text(resp)
        return _parse_classification(text)

    def name_event(
        self,
        photos: list[PhotoInput],
        category: str,
        mode: NamingMode,
    ) -> str:
        client = self._require_client()
        fallback = f"{category}_event"
        content_blocks: list[dict[str, Any]] = []
        for photo in photos[:3]:
            content_blocks.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": photo.thumbnail_media_type,
                        "data": base64.b64encode(photo.thumbnail_bytes).decode("ascii"),
                    },
                }
            )
        meta_ctx = build_cluster_metadata_context(photos[:3])
        content_blocks.append({"type": "text", "text": build_name_prompt(category, mode, meta_ctx)})
        try:
            resp = self._call_with_retry(
                lambda: client.messages.create(
                    model=self.model,
                    max_tokens=400,
                    messages=[{"role": "user", "content": content_blocks}],  # type: ignore[typeddict-item]
                )
            )
        except anthropic.APIError:
            return fallback
        return _sanitize_folder_name(_extract_text(resp), fallback)

    def generate_roast(self, stats: LibraryStats) -> str:
        client = self._require_client()
        try:
            resp = self._call_with_retry(
                lambda: client.messages.create(
                    model=self.model,
                    max_tokens=600,
                    messages=[
                        {"role": "user", "content": build_roast_prompt(stats)},
                    ],
                )
            )
        except anthropic.APIError:
            return "(roast unavailable: api error - the vibes are off)"
        text = _extract_text(resp).strip()
        return text[:600] if text else "(no roast generated - your library is too well-behaved)"

    # --- helpers ------------------------------------------------------------

    def _require_client(self) -> anthropic.Anthropic:
        if self._client is None:
            raise RuntimeError(
                "ClaudeProvider has no API key configured. "
                "Pass api_key=... or set ANTHROPIC_API_KEY."
            )
        return self._client

    def _call_with_retry(self, fn: Callable[[], T]) -> T:
        """Retry on RateLimitError with 1s/2s/4s backoff. Other errors fail fast."""
        delays = (1.0, 2.0, 4.0)
        for attempt, delay in enumerate(delays):
            try:
                return fn()
            except anthropic.RateLimitError:
                if attempt == len(delays) - 1:
                    raise
                time.sleep(delay)
        return fn()  # pragma: no cover - unreachable, loop always returns or raises


def _extract_text(resp: Any) -> str:
    """Pull the concatenated text from a messages.create response."""
    parts: list[str] = []
    content = getattr(resp, "content", None)
    if not content:
        return ""
    for block in content:
        text = getattr(block, "text", None)
        if isinstance(text, str):
            parts.append(text)
        elif isinstance(block, dict) and isinstance(block.get("text"), str):
            parts.append(block["text"])
    return "".join(parts)


def _parse_error_classification() -> Classification:
    return Classification(
        category="uncategorized",
        subcategory=None,
        confidence=0.0,
        description="<api error>",
        notable=[],
    )


def _parse_classification(text: str) -> Classification:
    """Parse JSON classification text defensively. Never raises."""
    if not text:
        return Classification(
            category="uncategorized",
            subcategory=None,
            confidence=0.0,
            description="<parse error>",
            notable=[],
        )
    cleaned = _strip_code_fence(text)
    cleaned = _extract_json_object(cleaned)
    try:
        data = json.loads(cleaned)
    except (json.JSONDecodeError, ValueError):
        return Classification(
            category="uncategorized",
            subcategory=None,
            confidence=0.0,
            description="<parse error>",
            notable=[],
        )
    if not isinstance(data, dict):
        return Classification(
            category="uncategorized",
            subcategory=None,
            confidence=0.0,
            description="<parse error>",
            notable=[],
        )
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
    notable: list[str] = []
    if isinstance(raw_notable, list):
        notable = [str(item) for item in raw_notable if isinstance(item, (str, int, float))]
    return Classification(
        category=category,
        subcategory=subcategory,
        confidence=confidence,
        description=description,
        notable=notable,
    )
