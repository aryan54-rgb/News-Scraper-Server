"""Interfaces for future data collectors."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Collector(ABC):
    """Base interface for all future source collectors."""

    source_name: str

    @abstractmethod
    async def collect(self) -> list[Any]:
        """Collect raw items from an external source."""
