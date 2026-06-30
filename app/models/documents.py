"""Raw and normalized document models."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, ModelBase

if TYPE_CHECKING:
    from app.models.classification import Classification
    from app.models.collection import FetchLog
    from app.models.entities import EntityMention
    from app.models.events import ArticleEvent
    from app.models.keywords import KeywordHit
    from app.models.sources import Source


class RawDocument(Base, ModelBase):
    """Immutable captured payload with complete collection lineage."""

    __tablename__ = "raw_document"
    __table_args__ = (
        UniqueConstraint("content_hash", name="uq_raw_document_content_hash"),
        Index("idx_raw_document_source_received_at", "source_id", "received_at"),
        Index("idx_raw_document_fetch_log_id", "fetch_log_id"),
        Index("idx_raw_document_metadata_gin", "metadata", postgresql_using="gin"),
    )

    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("source.id", ondelete="RESTRICT"))
    fetch_log_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("fetch_log.id", ondelete="SET NULL"))
    uri: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(120))
    storage_url: Mapped[str | None] = mapped_column(Text)
    inline_content: Mapped[str | None] = mapped_column(Text)
    received_at: Mapped[datetime] = mapped_column(nullable=False)
    metadata_: Mapped[dict[str, object]] = mapped_column("metadata", JSONB, nullable=False, default=dict)

    source: Mapped[Source] = relationship(back_populates="raw_documents", lazy="selectin")
    fetch_log: Mapped[FetchLog | None] = relationship(back_populates="raw_documents", lazy="selectin")
    article: Mapped[Article | None] = relationship(
        back_populates="raw_document",
        uselist=False,
        lazy="joined",
    )


class Article(Base, ModelBase):
    """Normalized article extracted from a raw document."""

    __tablename__ = "article"
    __table_args__ = (
        UniqueConstraint("raw_document_id", name="uq_article_raw_document_id"),
        UniqueConstraint("canonical_url", name="uq_article_canonical_url"),
        Index("idx_article_source_published_at", "source_id", "published_at"),
        Index("idx_article_published_at", "published_at"),
        Index("idx_article_title_trgm", "title", postgresql_using="gin", postgresql_ops={"title": "gin_trgm_ops"}),
        Index("idx_article_search_vector_gin", "search_vector", postgresql_using="gin"),
        Index("idx_article_metadata_gin", "metadata", postgresql_using="gin"),
    )

    raw_document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("raw_document.id", ondelete="RESTRICT"))
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("source.id", ondelete="RESTRICT"))
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    content_plain: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_url: Mapped[str] = mapped_column(Text, nullable=False)
    language_code: Mapped[str] = mapped_column(String(12), nullable=False, server_default="und")
    published_at: Mapped[datetime | None] = mapped_column()
    extracted_at: Mapped[datetime] = mapped_column(nullable=False)
    word_count: Mapped[int | None] = mapped_column(Integer)
    search_vector: Mapped[str | None] = mapped_column(TSVECTOR)
    metadata_: Mapped[dict[str, object]] = mapped_column("metadata", JSONB, nullable=False, default=dict)

    __table_args__ = __table_args__ + (
        CheckConstraint("word_count IS NULL OR word_count >= 0", name="article_word_count_nonnegative"),
    )

    raw_document: Mapped[RawDocument] = relationship(back_populates="article", lazy="joined")
    source: Mapped[Source] = relationship(back_populates="articles", lazy="selectin")
    article_events: Mapped[list[ArticleEvent]] = relationship(back_populates="article", lazy="selectin")
    classifications: Mapped[list[Classification]] = relationship(back_populates="article", lazy="selectin")
    entity_mentions: Mapped[list[EntityMention]] = relationship(back_populates="article", lazy="selectin")
    keyword_hits: Mapped[list[KeywordHit]] = relationship(back_populates="article", lazy="selectin")
