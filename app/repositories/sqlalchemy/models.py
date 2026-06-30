"""Concrete SQLAlchemy repositories for Phase 1 ORM models."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

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
    TaxonomyNode,
    TaxonomyVersion,
)
from app.repositories.sqlalchemy.base import SQLAlchemyRepository


class SQLAlchemyCollectorJobRepository(SQLAlchemyRepository[CollectorJob]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, CollectorJob)


class SQLAlchemyFetchLogRepository(SQLAlchemyRepository[FetchLog]):
    searchable_fields = ("url", "error_code", "error_message")

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, FetchLog)


class SQLAlchemyRawDocumentRepository(SQLAlchemyRepository[RawDocument]):
    searchable_fields = ("uri", "content_hash", "content_type")

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, RawDocument)


class SQLAlchemyArticleRepository(SQLAlchemyRepository[Article]):
    searchable_fields = ("title", "summary", "content_plain", "canonical_url")

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Article)


class SQLAlchemyEventRepository(SQLAlchemyRepository[Event]):
    searchable_fields = ("title", "description")

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Event)


class SQLAlchemyArticleEventRepository(SQLAlchemyRepository[ArticleEvent]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, ArticleEvent)


class SQLAlchemyTaxonomyNodeRepository(SQLAlchemyRepository[TaxonomyNode]):
    searchable_fields = ("code", "name", "description", "path")

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, TaxonomyNode)


class SQLAlchemyTaxonomyVersionRepository(SQLAlchemyRepository[TaxonomyVersion]):
    searchable_fields = ("name", "version")

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, TaxonomyVersion)


class SQLAlchemyClassificationRepository(SQLAlchemyRepository[Classification]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Classification)


class SQLAlchemyClassificationEvidenceRepository(SQLAlchemyRepository[ClassificationEvidence]):
    searchable_fields = ("quote",)

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, ClassificationEvidence)


class SQLAlchemyEntityRepository(SQLAlchemyRepository[Entity]):
    searchable_fields = ("canonical_name", "description")

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Entity)


class SQLAlchemyEntityAliasRepository(SQLAlchemyRepository[EntityAlias]):
    searchable_fields = ("alias",)

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, EntityAlias)


class SQLAlchemyEntityMentionRepository(SQLAlchemyRepository[EntityMention]):
    searchable_fields = ("mention_text", "context")

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, EntityMention)


class SQLAlchemyKeywordRepository(SQLAlchemyRepository[Keyword]):
    searchable_fields = ("term", "match_type")

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Keyword)


class SQLAlchemyKeywordGroupRepository(SQLAlchemyRepository[KeywordGroup]):
    searchable_fields = ("name", "description")

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, KeywordGroup)


class SQLAlchemyKeywordHitRepository(SQLAlchemyRepository[KeywordHit]):
    searchable_fields = ("matched_text",)

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, KeywordHit)
