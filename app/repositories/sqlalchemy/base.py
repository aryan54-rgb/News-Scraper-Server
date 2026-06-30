"""Generic async SQLAlchemy repository implementation."""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, Generic, TypeVar, cast

from sqlalchemy import Select, and_, asc, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.repositories.base import Page, SortDirection

ModelT = TypeVar("ModelT")


class SQLAlchemyRepository(Generic[ModelT]):
    """Reusable CRUD, filtering, sorting, search, and pagination adapter."""

    searchable_fields: tuple[str, ...] = ("name", "title", "canonical_name", "term")
    default_sort: str = "created_at"

    def __init__(self, session: AsyncSession, model: type[ModelT]) -> None:
        self.session = session
        self.model = model

    async def create(self, entity: ModelT) -> ModelT:
        self.session.add(entity)
        await self.session.flush()
        await self.session.refresh(entity)
        return entity

    async def update(self, entity: ModelT) -> ModelT:
        self.session.add(entity)
        await self.session.flush()
        await self.session.refresh(entity)
        return entity

    async def delete(self, entity_id: uuid.UUID) -> None:
        entity = await self.find_by_id(entity_id)
        if entity is None:
            return

        if hasattr(entity, "deleted_at"):
            setattr(entity, "deleted_at", datetime.now(UTC))
            self.session.add(entity)
        else:
            await self.session.delete(entity)
        await self.session.flush()

    async def find_by_id(self, entity_id: uuid.UUID) -> ModelT | None:
        statement = self._base_select().where(self._column("id") == entity_id)
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def search(
        self,
        criteria: Mapping[str, Any],
        *,
        sort_by: str | None = None,
        sort_direction: SortDirection = "asc",
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[ModelT]:
        statement = self._apply_sort(
            self._apply_filters(self._base_select(), criteria),
            sort_by=sort_by,
            sort_direction=sort_direction,
        ).limit(limit).offset(offset)
        result = await self.session.execute(statement)
        return result.scalars().all()

    async def list(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        sort_by: str | None = None,
        sort_direction: SortDirection = "asc",
    ) -> Sequence[ModelT]:
        statement = self._apply_sort(
            self._base_select(),
            sort_by=sort_by,
            sort_direction=sort_direction,
        ).limit(limit).offset(offset)
        result = await self.session.execute(statement)
        return result.scalars().all()

    async def paginate(
        self,
        *,
        page: int = 1,
        page_size: int = 50,
        criteria: Mapping[str, Any] | None = None,
        sort_by: str | None = None,
        sort_direction: SortDirection = "asc",
    ) -> Page[ModelT]:
        page = max(page, 1)
        page_size = max(page_size, 1)
        offset = (page - 1) * page_size
        filtered = self._apply_filters(self._base_select(), criteria or {})
        count_statement = select(func.count()).select_from(filtered.order_by(None).subquery())
        total = await self.session.scalar(count_statement)
        items_statement = self._apply_sort(
            filtered,
            sort_by=sort_by,
            sort_direction=sort_direction,
        ).limit(page_size).offset(offset)
        result = await self.session.execute(items_statement)
        return Page(
            items=result.scalars().all(),
            total=total or 0,
            page=page,
            page_size=page_size,
        )

    def _base_select(self) -> Select[tuple[ModelT]]:
        statement = select(self.model)
        if self._has_column("deleted_at"):
            statement = statement.where(self._column("deleted_at").is_(None))
        return statement

    def _apply_filters(
        self,
        statement: Select[tuple[ModelT]],
        criteria: Mapping[str, Any],
    ) -> Select[tuple[ModelT]]:
        predicates: list[Any] = []

        for key, value in criteria.items():
            if value is None:
                continue
            if key in {"q", "query", "search"}:
                predicates.append(self._text_search_predicate(str(value)))
            elif key == "name":
                predicates.append(self._name_predicate(str(value)))
            elif key == "source_type":
                predicates.append(self._source_type_predicate(value))
            elif key == "enabled":
                predicates.append(self._enabled_predicate(value))
            elif key == "tags":
                predicates.append(self._tags_predicate(value))
            elif key in {"country", "language"}:
                predicates.append(self._metadata_or_column_predicate(key, value))
            elif self._has_column(key):
                predicates.append(self._column(key) == value)
            elif self._has_metadata():
                predicates.append(self._metadata_value(key) == str(value))

        return statement.where(and_(*predicates)) if predicates else statement

    def _apply_sort(
        self,
        statement: Select[tuple[ModelT]],
        *,
        sort_by: str | None,
        sort_direction: SortDirection,
    ) -> Select[tuple[ModelT]]:
        sort_field = sort_by or self.default_sort
        if not self._has_column(sort_field):
            sort_field = "id"
        sort_column = self._column(sort_field)
        order = desc(sort_column) if sort_direction == "desc" else asc(sort_column)
        return statement.order_by(order)

    def _text_search_predicate(self, value: str) -> Any:
        fields = [
            self._column(field).ilike(f"%{value}%")
            for field in self.searchable_fields
            if self._has_column(field)
        ]
        return or_(*fields) if fields else self._false_predicate()

    def _name_predicate(self, value: str) -> Any:
        if self._has_column("name"):
            return self._column("name").ilike(f"%{value}%")
        if self._has_column("title"):
            return self._column("title").ilike(f"%{value}%")
        if self._has_column("canonical_name"):
            return self._column("canonical_name").ilike(f"%{value}%")
        if self._has_column("term"):
            return self._column("term").ilike(f"%{value}%")
        return self._false_predicate()

    def _source_type_predicate(self, value: Any) -> Any:
        if self._has_column("source_type_id"):
            return self._column("source_type_id") == value
        if self._has_column("code"):
            return self._column("code") == value
        return self._metadata_or_column_predicate("source_type", value)

    def _enabled_predicate(self, value: Any) -> Any:
        if self._has_column("is_enabled"):
            return self._column("is_enabled").is_(bool(value))
        if self._has_column("is_active"):
            return self._column("is_active").is_(bool(value))
        return self._metadata_value("enabled") == str(value).lower()

    def _tags_predicate(self, value: Any) -> Any:
        if not self._has_metadata():
            return self._false_predicate()
        tags = value if isinstance(value, list) else [value]
        return self._column("metadata_").contains({"tags": tags})

    def _metadata_or_column_predicate(self, key: str, value: Any) -> Any:
        if self._has_column(key):
            return self._column(key) == value
        if self._has_column(f"{key}_code"):
            return self._column(f"{key}_code") == value
        return self._metadata_value(key) == str(value)

    def _metadata_value(self, key: str) -> Any:
        if not self._has_metadata():
            return self._false_predicate()
        return self._column("metadata_")[key].astext

    def _false_predicate(self) -> Any:
        return self._column("id").is_(None)

    def _has_metadata(self) -> bool:
        return self._has_column("metadata_")

    def _has_column(self, name: str) -> bool:
        return isinstance(getattr(self.model, name, None), InstrumentedAttribute)

    def _column(self, name: str) -> InstrumentedAttribute[Any]:
        return cast(InstrumentedAttribute[Any], getattr(self.model, name))
