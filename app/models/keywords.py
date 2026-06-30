"""Keyword configuration and hit models."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Index, Numeric, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import ENUM, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, ModelBase
from app.database.enums import KeywordPriorityEnum

if TYPE_CHECKING:
    from app.models.documents import Article


class KeywordGroup(Base, ModelBase):
    """Logical group of monitored keywords."""

    __tablename__ = "keyword_group"
    __table_args__ = (
        Index(
            "uq_keyword_group_name_not_deleted",
            "name",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    metadata_: Mapped[dict[str, object]] = mapped_column("metadata", JSONB, nullable=False, default=dict)

    keywords: Mapped[list[Keyword]] = relationship(back_populates="group", lazy="selectin")


class Keyword(Base, ModelBase):
    """Tracked keyword, phrase, or expression."""

    __tablename__ = "keyword"
    __table_args__ = (
        UniqueConstraint("keyword_group_id", "term", "language_code", name="uq_keyword_group_term_language"),
        Index("idx_keyword_group_id", "keyword_group_id"),
        Index("idx_keyword_term_trgm", "term", postgresql_using="gin", postgresql_ops={"term": "gin_trgm_ops"}),
        Index("idx_keyword_priority", "priority"),
        Index("idx_keyword_active_not_deleted", "is_active", postgresql_where=text("deleted_at IS NULL")),
        Index("idx_keyword_metadata_gin", "metadata", postgresql_using="gin"),
    )

    keyword_group_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("keyword_group.id", ondelete="RESTRICT"))
    term: Mapped[str] = mapped_column(String(255), nullable=False)
    match_type: Mapped[str] = mapped_column(String(40), nullable=False, server_default="exact")
    language_code: Mapped[str] = mapped_column(String(12), nullable=False, server_default="und")
    priority: Mapped[KeywordPriorityEnum] = mapped_column(
        ENUM(KeywordPriorityEnum, name="keyword_priority_enum", create_type=False),
        nullable=False,
        server_default=KeywordPriorityEnum.MEDIUM.value,
    )
    is_active: Mapped[bool] = mapped_column(nullable=False, server_default="true")
    metadata_: Mapped[dict[str, object]] = mapped_column("metadata", JSONB, nullable=False, default=dict)

    group: Mapped[KeywordGroup] = relationship(back_populates="keywords", lazy="selectin")
    hits: Mapped[list[KeywordHit]] = relationship(back_populates="keyword", lazy="selectin")


class KeywordHit(Base, ModelBase):
    """Article occurrence of a configured keyword."""

    __tablename__ = "keyword_hit"
    __table_args__ = (
        CheckConstraint("start_offset IS NULL OR start_offset >= 0", name="keyword_hit_start_nonnegative"),
        CheckConstraint("end_offset IS NULL OR end_offset >= start_offset", name="keyword_hit_offsets_ordered"),
        CheckConstraint(
            "confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 1)",
            name="keyword_hit_confidence_range",
        ),
        Index("idx_keyword_hit_article_id", "article_id"),
        Index("idx_keyword_hit_keyword_id", "keyword_id"),
        Index("idx_keyword_hit_created_at", "created_at"),
    )

    article_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("article.id", ondelete="CASCADE"))
    keyword_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("keyword.id", ondelete="RESTRICT"))
    matched_text: Mapped[str] = mapped_column(String(500), nullable=False)
    start_offset: Mapped[int | None] = mapped_column()
    end_offset: Mapped[int | None] = mapped_column()
    confidence_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))

    article: Mapped[Article] = relationship(back_populates="keyword_hits", lazy="selectin")
    keyword: Mapped[Keyword] = relationship(back_populates="hits", lazy="selectin")
