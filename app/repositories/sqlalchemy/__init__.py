"""SQLAlchemy repository adapters."""

from app.repositories.sqlalchemy.base import SQLAlchemyRepository
from app.repositories.sqlalchemy.models import (
    SQLAlchemyArticleEventRepository,
    SQLAlchemyArticleRepository,
    SQLAlchemyClassificationEvidenceRepository,
    SQLAlchemyClassificationRepository,
    SQLAlchemyCollectorJobRepository,
    SQLAlchemyEntityAliasRepository,
    SQLAlchemyEntityMentionRepository,
    SQLAlchemyEntityRepository,
    SQLAlchemyEventRepository,
    SQLAlchemyFetchLogRepository,
    SQLAlchemyKeywordGroupRepository,
    SQLAlchemyKeywordHitRepository,
    SQLAlchemyKeywordRepository,
    SQLAlchemyRawDocumentRepository,
    SQLAlchemyTaxonomyNodeRepository,
    SQLAlchemyTaxonomyVersionRepository,
)
from app.repositories.sqlalchemy.sources import (
    SQLAlchemySourceGroupRepository,
    SQLAlchemySourceRepository,
    SQLAlchemySourceTypeRepository,
)

__all__ = [
    "SQLAlchemyArticleEventRepository",
    "SQLAlchemyArticleRepository",
    "SQLAlchemyClassificationEvidenceRepository",
    "SQLAlchemyClassificationRepository",
    "SQLAlchemyCollectorJobRepository",
    "SQLAlchemyEntityAliasRepository",
    "SQLAlchemyEntityMentionRepository",
    "SQLAlchemyEntityRepository",
    "SQLAlchemyEventRepository",
    "SQLAlchemyFetchLogRepository",
    "SQLAlchemyKeywordGroupRepository",
    "SQLAlchemyKeywordHitRepository",
    "SQLAlchemyKeywordRepository",
    "SQLAlchemyRawDocumentRepository",
    "SQLAlchemyRepository",
    "SQLAlchemySourceGroupRepository",
    "SQLAlchemySourceRepository",
    "SQLAlchemySourceTypeRepository",
    "SQLAlchemyTaxonomyNodeRepository",
    "SQLAlchemyTaxonomyVersionRepository",
]
