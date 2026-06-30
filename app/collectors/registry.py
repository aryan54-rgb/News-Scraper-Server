"""Collector plugin registry."""

from __future__ import annotations

from collections.abc import Iterable
from threading import RLock
from typing import TYPE_CHECKING

from app.collectors.exceptions import CollectorNotFoundError, CollectorRegistrationError

if TYPE_CHECKING:
    from app.collectors.base import Collector


class CollectorRegistry:
    """In-memory registry for collector classes."""

    def __init__(self) -> None:
        self._collectors: dict[str, type[Collector]] = {}
        self._lock = RLock()

    def register(self, collector_key: str, collector_cls: type[Collector]) -> type[Collector]:
        normalized_key = self._normalize_key(collector_key)
        with self._lock:
            existing = self._collectors.get(normalized_key)
            if existing is not None and existing is not collector_cls:
                raise CollectorRegistrationError(
                    f"Collector key '{normalized_key}' is already registered",
                    code="collector_registration_conflict",
                    details={
                        "collector_key": normalized_key,
                        "existing_collector": existing.__name__,
                        "new_collector": collector_cls.__name__,
                    },
                )
            self._collectors[normalized_key] = collector_cls
        return collector_cls

    def resolve(self, collector_key: str) -> type[Collector]:
        normalized_key = self._normalize_key(collector_key)
        try:
            return self._collectors[normalized_key]
        except KeyError as exc:
            raise CollectorNotFoundError(normalized_key) from exc

    def create(self, collector_key: str) -> Collector:
        return self.resolve(collector_key)()

    def keys(self) -> Iterable[str]:
        return tuple(sorted(self._collectors))

    def unregister(self, collector_key: str) -> None:
        normalized_key = self._normalize_key(collector_key)
        with self._lock:
            self._collectors.pop(normalized_key, None)

    def clear(self) -> None:
        with self._lock:
            self._collectors.clear()

    @staticmethod
    def _normalize_key(collector_key: str) -> str:
        normalized_key = collector_key.strip().lower()
        if not normalized_key:
            raise CollectorRegistrationError(
                "Collector key cannot be blank",
                code="collector_registration_invalid_key",
            )
        return normalized_key


collector_registry = CollectorRegistry()
