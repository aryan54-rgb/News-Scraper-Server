"""Phase 1 repository contracts."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from app.repositories.base import Repository

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
        SourceType,
        TaxonomyNode,
        TaxonomyVersion,
    )


class SourceRepository(Repository["Source"], Protocol): ...


class SourceTypeRepository(Repository["SourceType"], Protocol): ...


class SourceGroupRepository(Repository["SourceGroup"], Protocol): ...


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
