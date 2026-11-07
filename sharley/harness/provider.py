"""The one interface every model adapter implements."""
from abc import ABC, abstractmethod
from typing import Literal

Tier = Literal["fast", "strong"]


class ProviderError(Exception):
    """A provider call failed (network, auth, quota, malformed response)."""


class ModelProvider(ABC):
    name: str
    model: str
    family: str  # model family, used for the verifier/implementer independence check
    cost_rank: int = 5  # lower = cheaper; the router prefers low ranks for fast-tier steps

    @abstractmethod
    def health(self) -> bool:
        """Cheap check that the provider is configured and reachable. Must not raise."""

    @abstractmethod
    def complete(self, system: str, user: str, *, images: list[bytes] | None = None) -> str:
        """Return raw text. Raise ProviderError on any failure."""
