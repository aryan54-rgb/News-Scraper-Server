"""SQLAlchemy repositories for the source registry."""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import Select, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sources import Source, SourceGroup, SourceGroupMembership, SourceType
from app.repositories.base import SortDirection
from app.repositories.sqlalchemy.base import SQLAlchemyRepository


class SQLAlchemySourceRepository(SQLAlchemyRepository[Source]):
    """Persistence adapter for source records."""

    searchable_fields = ("name", "domain", "url")

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Source)

    async def find_by_domain(
        self,
        domain: str,
        *,
        source_type_id: uuid.UUID | None = None,
    ) -> Source | None:
        statement = self._base_select().where(Source.domain == domain)
        if source_type_id is not None:
            statement = statement.where(Source.source_type_id == source_type_id)
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def find_by_url(self, url: str) -> Source | None:
        result = await self.session.execute(self._base_select().where(Source.url == url))
        return result.scalar_one_or_none()

    async def list_by_group(
        self,
        source_group_id: uuid.UUID,
        *,
        limit: int = 100,
        offset: int = 0,
        sort_by: str | None = None,
        sort_direction: SortDirection = "asc",
    ) -> Sequence[Source]:
        statement = (
            self._base_select()
            .join(SourceGroupMembership, SourceGroupMembership.source_id == Source.id)
            .where(SourceGroupMembership.source_group_id == source_group_id)
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(
            self._apply_sort(statement, sort_by=sort_by, sort_direction=sort_direction)
        )
        return result.scalars().all()

    def _apply_filters(
        self,
        statement: Select[tuple[Source]],
        criteria: Mapping[str, Any],
    ) -> Select[tuple[Source]]:
        source_type = criteria.get("source_type")
        source_type_id = criteria.get("source_type_id")
        group_id = criteria.get("group_id")
        tags = criteria.get("tags")
        remaining = {
            key: value
            for key, value in criteria.items()
            if key not in {"source_type", "source_type_id", "group_id", "tags"}
        }

        statement = super()._apply_filters(statement, remaining)
        if source_type_id is not None:
            statement = statement.where(Source.source_type_id == source_type_id)
        if source_type is not None:
            source_type_predicates: list[Any] = [
                SourceType.code == source_type,
                SourceType.slug == source_type,
                SourceType.name.ilike(f"%{source_type}%"),
            ]
            if isinstance(source_type, uuid.UUID):
                source_type_predicates.append(SourceType.id == source_type)
            else:
                try:
                    source_type_predicates.append(SourceType.id == uuid.UUID(str(source_type)))
                except ValueError:
                    pass
            statement = statement.join(SourceType, Source.source_type_id == SourceType.id).where(
                or_(*source_type_predicates)
            )
        if group_id is not None:
            statement = statement.join(
                SourceGroupMembership,
                SourceGroupMembership.source_id == Source.id,
            ).where(SourceGroupMembership.source_group_id == group_id)
        if tags:
            tag_values = tags if isinstance(tags, list) else [tags]
            statement = statement.where(Source.metadata_.contains({"tags": tag_values}))
        return statement


class SQLAlchemySourceTypeRepository(SQLAlchemyRepository[SourceType]):
    """Persistence adapter for source type lookup records."""

    searchable_fields = ("name", "description")

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, SourceType)

    async def find_by_code(self, code: str) -> SourceType | None:
        result = await self.session.execute(self._base_select().where(SourceType.code == code))
        return result.scalar_one_or_none()

    async def find_by_slug(self, slug: str) -> SourceType | None:
        result = await self.session.execute(self._base_select().where(SourceType.slug == slug))
        return result.scalar_one_or_none()


class SQLAlchemySourceGroupRepository(SQLAlchemyRepository[SourceGroup]):
    """Persistence adapter for source groups."""

    searchable_fields = ("name", "description")

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, SourceGroup)

    async def find_by_name(self, name: str) -> SourceGroup | None:
        result = await self.session.execute(self._base_select().where(SourceGroup.name == name))
        return result.scalar_one_or_none()

    async def add_source(self, source_id: uuid.UUID, source_group_id: uuid.UUID) -> SourceGroupMembership:
        existing = await self.find_membership(source_id, source_group_id)
        if existing is not None:
            return existing

        membership = SourceGroupMembership(source_id=source_id, source_group_id=source_group_id)
        self.session.add(membership)
        await self.session.flush()
        await self.session.refresh(membership)
        return membership

    async def remove_source(self, source_id: uuid.UUID, source_group_id: uuid.UUID) -> None:
        membership = await self.find_membership(source_id, source_group_id)
        if membership is None:
            return
        await self.session.delete(membership)
        await self.session.flush()

    async def find_membership(
        self,
        source_id: uuid.UUID,
        source_group_id: uuid.UUID,
    ) -> SourceGroupMembership | None:
        result = await self.session.execute(
            select(SourceGroupMembership).where(
                SourceGroupMembership.source_id == source_id,
                SourceGroupMembership.source_group_id == source_group_id,
            )
        )
        return result.scalar_one_or_none()
