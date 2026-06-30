"""Abstract collector contracts and self-registration support."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar

from app.collectors.models import CollectorHealth, RawDocument


class Collector(ABC):
    """Base interface for pluggable source collectors.

    Concrete collectors can self-register by declaring a collector key:

        class RSSCollector(Collector, collector_key="rss"):
            ...

    The manager resolves that key from the Source Registry's source type.
    """

    collector_key: ClassVar[str | None] = None

    def __init_subclass__(cls, *, collector_key: str | None = None, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if collector_key is None:
            return
        from app.collectors.registry import collector_registry

        cls.collector_key = collector_key
        collector_registry.register(collector_key, cls)

    @abstractmethod
    async def validate_source(self, source: Any) -> None:
        """Validate that the source configuration can be collected."""

    @abstractmethod
    async def collect(self, source: Any) -> Any:
        """Collect source-specific payloads without writing to storage."""

    @abstractmethod
    async def normalize(self, source: Any, collected: Any) -> list[RawDocument]:
        """Convert collected payloads into normalized raw documents."""

    @abstractmethod
    async def health_check(self, source: Any) -> CollectorHealth:
        """Return a collector-specific health signal for the source."""
