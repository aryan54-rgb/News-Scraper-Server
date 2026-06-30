"""Interfaces for future background workers."""

from __future__ import annotations

from abc import ABC, abstractmethod


class Worker(ABC):
    """Base class for background workers."""

    name: str

    @abstractmethod
    async def start(self) -> None:
        """Start the worker runtime."""

    @abstractmethod
    async def stop(self) -> None:
        """Stop the worker and release resources."""
