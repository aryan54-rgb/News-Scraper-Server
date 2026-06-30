"""Application service for dynamic source management."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy.exc import IntegrityError

from app.database.enums import SourceStatusEnum, SourceTypeEnum
from app.models.sources import Source, SourceGroup, SourceType
from app.repositories.base import Page, SortDirection
from app.repositories.interfaces import SourceGroupRepository, SourceRepository, SourceTypeRepository
from app.source_registry.exceptions import (
    DuplicateSourceError,
    SourceGroupNotFoundError,
    SourceNotFoundError,
    SourceRegistryError,
    SourceTypeNotFoundError,
)
from app.source_registry.schemas import (
    HealthStatus,
    HealthMetrics,
    SourceCreate,
    SourceGroupCreate,
    SourceGroupRead,
    SourceGroupUpdate,
    SourceMetadata,
    SourceRead,
    SourceTestResponse,
    SourceTypeCreate,
    SourceTypeRead,
    SourceTypeUpdate,
    SourceUpdate,
)
from app.source_registry.validation import (
    normalize_domain,
    validate_collector_compatibility,
    validate_source_url,
)


DEFAULT_SOURCE_TYPES: tuple[SourceTypeCreate, ...] = (
    SourceTypeCreate(
        slug="rss_feed",
        code=SourceTypeEnum.RSS,
        name="RSS Feed",
        description="RSS or Atom feed monitored by feed collectors.",
        collector_key="rss",
        capabilities=["rss", "feed"],
    ),
    SourceTypeCreate(
        slug="news_website",
        code=SourceTypeEnum.WEBSITE,
        name="News Website",
        description="News website monitored by web collectors.",
        collector_key="website",
        capabilities=["html", "website"],
    ),
    SourceTypeCreate(
        slug="government_portal",
        code=SourceTypeEnum.GOVERNMENT,
        name="Government Portal",
        description="Official government portal or bulletin endpoint.",
        collector_key="government",
        capabilities=["government", "html", "api"],
    ),
    SourceTypeCreate(
        slug="x_account",
        code=SourceTypeEnum.SOCIAL,
        name="X Account",
        description="X account or timeline configured for social collectors.",
        collector_key="x",
        capabilities=["social", "x"],
    ),
    SourceTypeCreate(
        slug="blog",
        code=SourceTypeEnum.WEBSITE,
        name="Blog",
        description="Blog or editorial feed monitored by web or feed collectors.",
        collector_key="blog",
        capabilities=["html", "rss", "website"],
    ),
)


class SourceRegistryService:
    """Coordinate validation, persistence, and response mapping for sources."""

    def __init__(
        self,
        sources: SourceRepository,
        source_types: SourceTypeRepository,
        source_groups: SourceGroupRepository,
    ) -> None:
        self.sources = sources
        self.source_types = source_types
        self.source_groups = source_groups

    async def list_sources(
        self,
        *,
        page: int,
        page_size: int,
        criteria: dict[str, Any],
        sort_by: str | None,
        sort_direction: SortDirection,
    ) -> Page[SourceRead]:
        result = await self.sources.paginate(
            page=page,
            page_size=page_size,
            criteria=criteria,
            sort_by=sort_by,
            sort_direction=sort_direction,
        )
        return Page(
            items=[self._source_to_read(source) for source in result.items],
            total=result.total,
            page=result.page,
            page_size=result.page_size,
        )

    async def get_source(self, source_id: uuid.UUID) -> SourceRead:
        source = await self._require_source(source_id)
        return self._source_to_read(source)

    async def create_source(self, payload: SourceCreate) -> SourceRead:
        source_type = await self._resolve_source_type(payload.source_type_id, payload.source_type)
        metadata = self._metadata_from_payload(payload)
        url = str(payload.url)
        validate_source_url(url)
        await self._ensure_unique_url(url)

        domain = normalize_domain(url, payload.domain)
        await self._ensure_unique_domain(domain, source_type.id)
        validate_collector_compatibility(
            type_code=source_type.code,
            source_type_slug=source_type.slug,
            capabilities=source_type.capabilities,
            metadata=metadata,
        )

        source = Source(
            source_type_id=source_type.id,
            name=payload.name,
            url=url,
            domain=domain,
            status=payload.status,
            reliability_score=self._decimal(payload.reliability_score),
            metadata_=metadata.model_dump(mode="json"),
        )
        source = await self.sources.create(source)
        await self._replace_groups(source.id, payload.group_ids)
        source = await self._require_source(source.id)
        return self._source_to_read(source)

    async def update_source(self, source_id: uuid.UUID, payload: SourceUpdate) -> SourceRead:
        source = await self._require_source(source_id)
        source_type = source.source_type
        if payload.source_type_id is not None or payload.source_type is not None:
            source_type = await self._resolve_source_type(payload.source_type_id, payload.source_type)
            source.source_type_id = source_type.id

        metadata = self._metadata_from_source(source)
        self._apply_source_update(source, metadata, payload)
        if source.url is not None:
            validate_source_url(source.url)
            existing = await self.sources.find_by_url(source.url)
            if existing is not None and existing.id != source.id:
                raise DuplicateSourceError("url", source.url)
            source.domain = normalize_domain(source.url, source.domain)
            await self._ensure_unique_domain(source.domain, source_type.id, excluding_source_id=source.id)

        validate_collector_compatibility(
            type_code=source_type.code,
            source_type_slug=source_type.slug,
            capabilities=source_type.capabilities,
            metadata=metadata,
        )
        source.metadata_ = metadata.model_dump(mode="json")
        source = await self.sources.update(source)
        if payload.group_ids is not None:
            await self._replace_groups(source.id, payload.group_ids)
            source = await self._require_source(source.id)
        return self._source_to_read(source)

    async def delete_source(self, source_id: uuid.UUID) -> None:
        await self._require_source(source_id)
        await self.sources.delete(source_id)

    async def enable_source(self, source_id: uuid.UUID) -> SourceRead:
        source = await self._require_source(source_id)
        metadata = self._metadata_from_source(source)
        metadata.enabled = True
        source.status = SourceStatusEnum.ACTIVE
        source.metadata_ = metadata.model_dump(mode="json")
        return self._source_to_read(await self.sources.update(source))

    async def disable_source(self, source_id: uuid.UUID) -> SourceRead:
        source = await self._require_source(source_id)
        metadata = self._metadata_from_source(source)
        metadata.enabled = False
        metadata.health.health_status = HealthStatus.DISABLED
        source.status = SourceStatusEnum.SUSPENDED
        source.metadata_ = metadata.model_dump(mode="json")
        return self._source_to_read(await self.sources.update(source))

    async def test_source(self, source_id: uuid.UUID) -> SourceTestResponse:
        source = await self._require_source(source_id)
        metadata = self._metadata_from_source(source)
        warnings = validate_collector_compatibility(
            type_code=source.source_type.code,
            source_type_slug=source.source_type.slug,
            capabilities=source.source_type.capabilities,
            metadata=metadata,
        )
        return SourceTestResponse(
            source_id=source.id,
            status="valid",
            collector_compatible=True,
            warnings=warnings,
        )

    async def list_source_types(self) -> list[SourceTypeRead]:
        return [self._source_type_to_read(item) for item in await self.source_types.list(sort_by="name")]

    async def create_source_type(self, payload: SourceTypeCreate) -> SourceTypeRead:
        source_type = SourceType(**payload.model_dump(mode="json"))
        try:
            return self._source_type_to_read(await self.source_types.create(source_type))
        except IntegrityError as exc:
            raise SourceRegistryError("Source type already exists", "duplicate_source_type") from exc

    async def update_source_type(
        self,
        source_type_id: uuid.UUID,
        payload: SourceTypeUpdate,
    ) -> SourceTypeRead:
        source_type = await self.source_types.find_by_id(source_type_id)
        if source_type is None:
            raise SourceTypeNotFoundError(source_type_id)
        for key, value in payload.model_dump(exclude_unset=True, mode="json").items():
            setattr(source_type, key, value)
        return self._source_type_to_read(await self.source_types.update(source_type))

    async def delete_source_type(self, source_type_id: uuid.UUID) -> None:
        source_type = await self.source_types.find_by_id(source_type_id)
        if source_type is None:
            raise SourceTypeNotFoundError(source_type_id)
        await self.source_types.delete(source_type_id)

    async def ensure_default_source_types(self) -> list[SourceTypeRead]:
        created_or_existing: list[SourceTypeRead] = []
        for payload in DEFAULT_SOURCE_TYPES:
            existing = await self.source_types.find_by_slug(payload.slug)
            if existing is None:
                existing = await self.source_types.create(SourceType(**payload.model_dump(mode="json")))
            created_or_existing.append(self._source_type_to_read(existing))
        return created_or_existing

    async def list_source_groups(self) -> list[SourceGroupRead]:
        return [self._source_group_to_read(item) for item in await self.source_groups.list(sort_by="name")]

    async def create_source_group(self, payload: SourceGroupCreate) -> SourceGroupRead:
        group = SourceGroup(**payload.model_dump())
        try:
            return self._source_group_to_read(await self.source_groups.create(group))
        except IntegrityError as exc:
            raise SourceRegistryError("Source group already exists", "duplicate_source_group") from exc

    async def update_source_group(
        self,
        source_group_id: uuid.UUID,
        payload: SourceGroupUpdate,
    ) -> SourceGroupRead:
        group = await self.source_groups.find_by_id(source_group_id)
        if group is None:
            raise SourceGroupNotFoundError(source_group_id)
        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(group, key, value)
        return self._source_group_to_read(await self.source_groups.update(group))

    async def delete_source_group(self, source_group_id: uuid.UUID) -> None:
        group = await self.source_groups.find_by_id(source_group_id)
        if group is None:
            raise SourceGroupNotFoundError(source_group_id)
        await self.source_groups.delete(source_group_id)

    async def _require_source(self, source_id: uuid.UUID) -> Source:
        source = await self.sources.find_by_id(source_id)
        if source is None:
            raise SourceNotFoundError(source_id)
        return source

    async def _resolve_source_type(
        self,
        source_type_id: uuid.UUID | None,
        source_type_ref: str | None,
    ) -> SourceType:
        if source_type_id is not None:
            source_type = await self.source_types.find_by_id(source_type_id)
            if source_type is None:
                raise SourceTypeNotFoundError(source_type_id)
            return source_type
        if source_type_ref is None:
            raise SourceTypeNotFoundError("missing")
        source_type = await self.source_types.find_by_slug(source_type_ref)
        if source_type is not None:
            return source_type
        try:
            source_type = await self.source_types.find_by_id(uuid.UUID(source_type_ref))
        except ValueError:
            source_type = None
        if source_type is not None:
            return source_type
        matches = await self.source_types.search({"name": source_type_ref}, limit=2)
        if matches:
            return matches[0]
        raise SourceTypeNotFoundError(source_type_ref)

    async def _ensure_unique_url(
        self,
        url: str,
        *,
        excluding_source_id: uuid.UUID | None = None,
    ) -> None:
        existing = await self.sources.find_by_url(url)
        if existing is not None and existing.id != excluding_source_id:
            raise DuplicateSourceError("url", url)

    async def _ensure_unique_domain(
        self,
        domain: str,
        source_type_id: uuid.UUID,
        *,
        excluding_source_id: uuid.UUID | None = None,
    ) -> None:
        existing = await self.sources.find_by_domain(domain, source_type_id=source_type_id)
        if existing is not None and existing.id != excluding_source_id:
            raise DuplicateSourceError("domain", domain)

    async def _replace_groups(self, source_id: uuid.UUID, group_ids: list[uuid.UUID]) -> None:
        for group_id in group_ids:
            if await self.source_groups.find_by_id(group_id) is None:
                raise SourceGroupNotFoundError(group_id)

        source = await self._require_source(source_id)
        current = {membership.source_group_id for membership in source.group_memberships}
        desired = set(group_ids)
        for group_id in current - desired:
            await self.source_groups.remove_source(source_id, group_id)
        for group_id in desired - current:
            await self.source_groups.add_source(source_id, group_id)

    def _metadata_from_payload(self, payload: SourceCreate) -> SourceMetadata:
        return SourceMetadata(
            public_type=payload.source_type,
            country=payload.country,
            language=payload.language,
            enabled=payload.enabled,
            priority=payload.priority,
            tags=payload.tags,
            scheduling=payload.scheduling,
            authentication=payload.authentication,
            headers=payload.headers,
            rate_limit=payload.rate_limit,
            retry_policy=payload.retry_policy,
            keywords=payload.keywords,
            collector=payload.collector,
        )

    def _metadata_from_source(self, source: Source) -> SourceMetadata:
        return SourceMetadata.model_validate(source.metadata_ or {})

    def _apply_source_update(
        self,
        source: Source,
        metadata: SourceMetadata,
        payload: SourceUpdate,
    ) -> None:
        update = payload.model_dump(exclude_unset=True)
        source_fields = {"name", "url", "domain", "status"}
        for field in source_fields:
            if field in update:
                setattr(source, field, str(update[field]) if field == "url" else update[field])
        if payload.reliability_score is not None:
            source.reliability_score = self._decimal(payload.reliability_score)

        metadata_mapping = {
            "country": "country",
            "language": "language",
            "enabled": "enabled",
            "priority": "priority",
            "tags": "tags",
            "scheduling": "scheduling",
            "authentication": "authentication",
            "headers": "headers",
            "rate_limit": "rate_limit",
            "retry_policy": "retry_policy",
            "keywords": "keywords",
            "collector": "collector",
        }
        for payload_field, metadata_field in metadata_mapping.items():
            if payload_field in update:
                setattr(metadata, metadata_field, getattr(payload, payload_field))
        if payload.source_type is not None:
            metadata.public_type = payload.source_type

    def _source_to_read(self, source: Source) -> SourceRead:
        metadata = self._metadata_from_source(source)
        return SourceRead(
            id=source.id,
            name=source.name,
            url=source.url,
            domain=source.domain,
            status=source.status,
            reliability_score=float(source.reliability_score) if source.reliability_score is not None else None,
            source_type_id=source.source_type_id,
            source_type=source.source_type.slug,
            source_type_name=source.source_type.name,
            country=metadata.country,
            language=metadata.language,
            enabled=metadata.enabled,
            priority=metadata.priority,
            tags=metadata.tags,
            group_ids=[membership.source_group_id for membership in source.group_memberships],
            scheduling=metadata.scheduling,
            authentication=metadata.authentication,
            headers=metadata.headers,
            rate_limit=metadata.rate_limit,
            retry_policy=metadata.retry_policy,
            keywords=metadata.keywords,
            health=metadata.health or HealthMetrics(),
            collector=metadata.collector,
            created_at=source.created_at,
            updated_at=source.updated_at,
        )

    def _source_type_to_read(self, source_type: SourceType) -> SourceTypeRead:
        return SourceTypeRead.model_validate(source_type)

    def _source_group_to_read(self, source_group: SourceGroup) -> SourceGroupRead:
        return SourceGroupRead(
            id=source_group.id,
            name=source_group.name,
            description=source_group.description,
            source_count=len(source_group.source_memberships),
            created_at=source_group.created_at,
            updated_at=source_group.updated_at,
        )

    @staticmethod
    def _decimal(value: float | None) -> Decimal | None:
        if value is None:
            return None
        return Decimal(str(value))
