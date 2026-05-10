"""Abstract base class for vision LLM providers. Frozen contract."""
from __future__ import annotations

from abc import ABC, abstractmethod

from pixeldump.core.types import (
    Classification,
    CostEstimate,
    LibraryStats,
    NamingMode,
    PhotoInput,
)


class VisionProvider(ABC):
    """Abstract vision LLM provider. Implementations: ClaudeProvider, OllamaProvider."""

    name: str  # subclass sets this

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if provider is configured and reachable."""

    @abstractmethod
    def estimate_cost(self, num_photos: int) -> CostEstimate | None:
        """Return cost estimate, or None for local/free providers."""

    @abstractmethod
    def classify_cluster(self, photos: list[PhotoInput]) -> Classification:
        """Classify a sampled group of photos from one event cluster."""

    @abstractmethod
    def name_event(
        self,
        photos: list[PhotoInput],
        category: str,
        mode: NamingMode,
    ) -> str:
        """Generate a folder name (just the name part, no date prefix). Lowercase, snake_case, <=40 chars."""

    @abstractmethod
    def generate_roast(self, stats: LibraryStats) -> str:
        """Generate a multi-line roast of the user's photo library at completion."""
