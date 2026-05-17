"""Local Ollama vision provider (e.g. gemma3, llava, llama3.2-vision)."""
from __future__ import annotations

import json
import logging
import re
from typing import Any

import ollama

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

logger = logging.getLogger(__name__)

# Ordered fallback chain: try the requested model first, then these.
_FALLBACK_MODELS: tuple[str, ...] = ("gemma3", "llava", "llama3.2-vision")
_DEFAULT_TIMEOUT_SECONDS: float = 120.0
_PHOTOS_PER_CLUSTER: int = 5


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


_NAME_CLEAN_RE = re.compile(r"[^a-z0-9_]+")


def _sanitize_folder_name(raw: str, fallback: str) -> str:
    text = raw.strip().strip("`").strip()
    for line in text.splitlines():
        if line.strip():
            text = line.strip()
            break
    text = text.strip("\"'“”‘’")
    text = text.lower().replace(" ", "_").replace("-", "_")
    text = _NAME_CLEAN_RE.sub("", text)
    text = text.strip("_")
    text = re.sub(r"_+", "_", text)
    if not text:
        return fallback
    return text[:40].rstrip("_") or fallback


class OllamaProvider(VisionProvider):
    """Vision provider backed by a locally running Ollama server.

    Default model is ``gemma3``. If the requested model is missing,
    ``is_available`` will fall back through ``gemma3 -> llava -> llama3.2-vision``,
    using whichever is installed locally.
    """

    name = "ollama"

    def __init__(self, host: str = "http://localhost:11434", model: str = "gemma3") -> None:
        self.host: str = host
        self.model: str = model
        # ollama.Client doesn't make a network call here.
        self._client: ollama.Client = ollama.Client(host=host, timeout=_DEFAULT_TIMEOUT_SECONDS)
        self._available_cache: bool | None = None

    # --- availability -------------------------------------------------------

    def is_available(self) -> bool:
        if self._available_cache is not None:
            return self._available_cache
        try:
            listing = self._client.list()
        except Exception:  # noqa: BLE001 - any connection error means unavailable.
            self._available_cache = False
            return False

        installed = _installed_model_names(listing)
        if _model_present(self.model, installed):
            self._available_cache = True
            return True

        # Try fallbacks in order; switch to whichever is present.
        for candidate in _FALLBACK_MODELS:
            if candidate == self.model:
                continue
            if _model_present(candidate, installed):
                logger.info(
                    "Ollama model %r not installed; falling back to %r.",
                    self.model,
                    candidate,
                )
                self.model = candidate
                self._available_cache = True
                return True

        self._available_cache = False
        return False

    # --- cost ---------------------------------------------------------------

    def estimate_cost(self, num_photos: int) -> CostEstimate | None:
        # Local inference - no monetary cost.
        del num_photos
        return None

    # --- main ops -----------------------------------------------------------

    def classify_cluster(self, photos: list[PhotoInput]) -> Classification:
        sampled = photos[:_PHOTOS_PER_CLUSTER]
        images = [photo.thumbnail_bytes for photo in sampled]
        metadata_ctx = build_cluster_metadata_context(sampled)
        messages = [
            {"role": "system", "content": CLASSIFY_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"{metadata_ctx}\n\nUsing the metadata above and the images, classify this cluster. JSON only.",
                "images": images,
            },
        ]
        try:
            resp = self._client.chat(
                model=self.model,
                messages=messages,
                format="json",
            )
        except Exception:  # noqa: BLE001
            # format="json" unsupported by this model/version — retry without it.
            try:
                resp = self._client.chat(model=self.model, messages=messages)
            except Exception:  # noqa: BLE001
                return _parse_error_classification()

        text = _extract_response_text(resp)
        return _parse_classification(text)

    def name_event(
        self,
        photos: list[PhotoInput],
        category: str,
        mode: NamingMode,
    ) -> str:
        fallback = f"{category}_event"
        sampled = photos[:3]
        images = [photo.thumbnail_bytes for photo in sampled]
        meta_ctx = build_cluster_metadata_context(sampled)
        try:
            resp = self._client.chat(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": build_name_prompt(category, mode, meta_ctx),
                        "images": images,
                    },
                ],
            )
        except Exception:  # noqa: BLE001
            return fallback
        return _sanitize_folder_name(_extract_response_text(resp), fallback)

    def generate_roast(self, stats: LibraryStats) -> str:
        try:
            resp = self._client.chat(
                model=self.model,
                messages=[
                    {"role": "user", "content": build_roast_prompt(stats)},
                ],
            )
        except Exception:  # noqa: BLE001
            return "(roast unavailable: ollama is offline - touch grass instead)"
        text = _extract_response_text(resp).strip()
        return text[:600] if text else "(no roast generated - your library is too well-behaved)"


def _installed_model_names(listing: Any) -> set[str]:
    """Pull the set of installed model names from a ListResponse-like object."""
    names: set[str] = set()
    models = getattr(listing, "models", None)
    if models is None and isinstance(listing, dict):
        models = listing.get("models")
    if not models:
        return names
    for entry in models:
        # New SDK: object with .model attribute. Older/dict: 'model' or 'name' key.
        candidate = getattr(entry, "model", None)
        if candidate is None and isinstance(entry, dict):
            candidate = entry.get("model") or entry.get("name")
        if isinstance(candidate, str) and candidate:
            names.add(candidate)
    return names


def _model_present(model: str, installed: set[str]) -> bool:
    """Return True if `model` is in the installed set, ignoring trailing :tag."""
    if model in installed:
        return True
    base = model.split(":", 1)[0]
    return any(name == model or name.split(":", 1)[0] == base for name in installed)


def _extract_response_text(resp: Any) -> str:
    """Pull text content from an ollama ChatResponse (SDK object or dict)."""
    message = getattr(resp, "message", None)
    if message is None and isinstance(resp, dict):
        message = resp.get("message")
    if message is None:
        return ""
    content = getattr(message, "content", None)
    if content is None and isinstance(message, dict):
        content = message.get("content")
    return content if isinstance(content, str) else ""


def _parse_error_classification() -> Classification:
    return Classification(
        category="uncategorized",
        subcategory=None,
        confidence=0.0,
        description="<parse error>",
        notable=[],
    )


def _parse_classification(text: str) -> Classification:
    if not text:
        return _parse_error_classification()
    cleaned = _strip_code_fence(text)
    cleaned = _extract_json_object(cleaned)
    try:
        data = json.loads(cleaned)
    except (json.JSONDecodeError, ValueError):
        return _parse_error_classification()
    if not isinstance(data, dict):
        return _parse_error_classification()
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
