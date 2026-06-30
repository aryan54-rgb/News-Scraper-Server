"""Phase 1 repository contracts."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import TYPE_CHECKING, Protocol

from app.repositories.base import Repository, SortDirection

if TYPE_CHECKING:
    from app.models import (
        Article,
        ArticleEvent,
        Classification,
        ClassificationEvidence,
        CollectorJob,
        Entity,
        EntityAlias,
        EntityMention,
        Event,
        FetchLog,
        Keyword,
        KeywordGroup,
        KeywordHit,
        RawDocument,
        Source,
        SourceGroup,
        SourceGroupMembership,
        SourceType,
        TaxonomyNode,
        TaxonomyVersion,
    )


class SourceRepository(Repository["Source"], Protocol):
    async def find_by_domain(
        self,
        domain: str,
        *,
        source_type_id: uuid.UUID | None = None,
    ) -> "Source" | None:
        """Return a source by domain, optionally scoped to a source type."""
        ...

    async def find_by_url(self, url: str) -> "Source" | None:
        """Return a source by canonical URL."""
        ...

    async def list_by_group(
        self,
        source_group_id: uuid.UUID,
        *,
        limit: int = 100,
        offset: int = 0,
        sort_by: str | None = None,
        sort_direction: SortDirection = "asc",
    ) -> Sequence["Source"]:
        """Return sources attached to a source group."""
        ...


class SourceTypeRepository(Repository["SourceType"], Protocol):
    async def find_by_code(self, code: str) -> "SourceType" | None:
        """Return a source type by enum code."""
        ...

    async def find_by_slug(self, slug: str) -> "SourceType" | None:
        """Return a source type by public slug."""
        ...


class SourceGroupRepository(Repository["SourceGroup"], Protocol):
    async def find_by_name(self, name: str) -> "SourceGroup" | None:
        """Return a source group by name."""
        ...

    async def add_source(
        self,
        source_id: uuid.UUID,
        source_group_id: uuid.UUID,
    ) -> "SourceGroupMembership":
        """Attach a source to a group."""
        ...

    async def remove_source(self, source_id: uuid.UUID, source_group_id: uuid.UUID) -> None:
        """Remove a source from a group."""
        ...

    async def find_membership(
        self,
        source_id: uuid.UUID,
        source_group_id: uuid.UUID,
    ) -> "SourceGroupMembership" | None:
        """Return a source-group membership row."""
        ...


class CollectorJobRepository(Repository["CollectorJob"], Protocol): ...


class FetchLogRepository(Repository["FetchLog"], Protocol): ...


class RawDocumentRepository(Repository["RawDocument"], Protocol): ...


class ArticleRepository(Repository["Article"], Protocol): ...


class EventRepository(Repository["Event"], Protocol): ...


class ArticleEventRepository(Repository["ArticleEvent"], Protocol): ...


class TaxonomyNodeRepository(Repository["TaxonomyNode"], Protocol): ...


class TaxonomyVersionRepository(Repository["TaxonomyVersion"], Protocol): ...


class ClassificationRepository(Repository["Classification"], Protocol): ...


class ClassificationEvidenceRepository(Repository["ClassificationEvidence"], Protocol): ...


class EntityRepository(Repository["Entity"], Protocol): ...


class EntityAliasRepository(Repository["EntityAlias"], Protocol): ...


class EntityMentionRepository(Repository["EntityMention"], Protocol): ...


class KeywordRepository(Repository["Keyword"], Protocol): ...


class KeywordGroupRepository(Repository["KeywordGroup"], Protocol): ...


class KeywordHitRepository(Repository["KeywordHit"], Protocol): ...
