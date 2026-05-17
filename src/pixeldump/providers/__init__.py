"""Vision provider implementations. See `base.VisionProvider`."""
from __future__ import annotations

from pixeldump.providers.base import VisionProvider

__all__ = ["VisionProvider"]

# Concrete providers are imported lazily in cli.py / app.py to avoid pulling
# in optional heavy dependencies (anthropic, httpx) at import time.
# Available: ClaudeProvider, OllamaProvider, ClaudeCodeProvider
