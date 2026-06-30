"""Repository interfaces for database-backed persistence.

These are contracts only. Concrete implementations belong in a later phase.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Generic, Protocol, TypeVar

ModelT = TypeVar("ModelT")


@dataclass(frozen=True)
class Page(Generic[ModelT]):
    """Paginated result envelope returned by repository interfaces."""

    items: Sequence[ModelT]
    total: int
    page: int
    page_size: int


class Repository(Protocol, Generic[ModelT]):
    """Async CRUD/search contract shared by all Phase 1 repositories."""

    async def create(self, entity: ModelT) -> ModelT:
        """Persist a new entity."""
        ...

    async def update(self, entity: ModelT) -> ModelT:
        """Persist changes to an existing entity."""
        ...

    async def delete(self, entity_id: uuid.UUID) -> None:
        """Soft-delete an entity by identifier."""
        ...

    async def find_by_id(self, entity_id: uuid.UUID) -> ModelT | None:
        """Return an entity by identifier."""
        ...

    async def search(self, criteria: Mapping[str, Any]) -> Sequence[ModelT]:
        """Return entities matching structured search criteria."""
        ...

    async def list(self, *, limit: int = 100, offset: int = 0) -> Sequence[ModelT]:
        """Return a bounded ordered list of entities."""
        ...

    async def paginate(self, *, page: int = 1, page_size: int = 50) -> Page[ModelT]:
        """Return a counted page of entities."""
        ...
