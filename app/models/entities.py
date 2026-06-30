"""Entity registry and mention models."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Index, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ENUM, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, ModelBase
from app.database.enums import EntityTypeEnum

if TYPE_CHECKING:
    from app.models.documents import Article


class Entity(Base, ModelBase):
    """Canonical real-world actor, organization, place, or concept."""

    __tablename__ = "entity"
    __table_args__ = (
        UniqueConstraint("entity_type", "canonical_name", name="uq_entity_type_canonical_name"),
        Index("idx_entity_type", "entity_type"),
        Index("idx_entity_canonical_name_trgm", "canonical_name", postgresql_using="gin", postgresql_ops={"canonical_name": "gin_trgm_ops"}),
        Index("idx_entity_external_ids_gin", "external_ids", postgresql_using="gin"),
        Index("idx_entity_metadata_gin", "metadata", postgresql_using="gin"),
    )

    entity_type: Mapped[EntityTypeEnum] = mapped_column(
        ENUM(EntityTypeEnum, name="entity_type_enum", create_type=False),
        nullable=False,
    )
    canonical_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    external_ids: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    metadata_: Mapped[dict[str, object]] = mapped_column("metadata", JSONB, nullable=False, default=dict)

    aliases: Mapped[list[EntityAlias]] = relationship(
        back_populates="entity",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    mentions: Mapped[list[EntityMention]] = relationship(back_populates="entity", lazy="selectin")


class EntityAlias(Base, ModelBase):
    """Alternate text representation for an entity."""

    __tablename__ = "entity_alias"
    __table_args__ = (
        UniqueConstraint("entity_id", "alias", "language_code", name="uq_entity_alias_entity_alias_language"),
        Index("idx_entity_alias_entity_id", "entity_id"),
        Index("idx_entity_alias_alias_trgm", "alias", postgresql_using="gin", postgresql_ops={"alias": "gin_trgm_ops"}),
    )

    entity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("entity.id", ondelete="CASCADE"))
    alias: Mapped[str] = mapped_column(String(255), nullable=False)
    language_code: Mapped[str] = mapped_column(String(12), nullable=False, server_default="und")
    is_primary: Mapped[bool] = mapped_column(nullable=False, server_default="false")

    entity: Mapped[Entity] = relationship(back_populates="aliases", lazy="selectin")


class EntityMention(Base, ModelBase):
    """Occurrence of an entity in an article."""

    __tablename__ = "entity_mention"
    __table_args__ = (
        CheckConstraint("start_offset >= 0", name="entity_mention_start_nonnegative"),
        CheckConstraint("end_offset >= start_offset", name="entity_mention_offsets_ordered"),
        CheckConstraint(
            "confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 1)",
            name="entity_mention_confidence_range",
        ),
        Index("idx_entity_mention_article_id", "article_id"),
        Index("idx_entity_mention_entity_id", "entity_id"),
        Index("idx_entity_mention_text_trgm", "mention_text", postgresql_using="gin", postgresql_ops={"mention_text": "gin_trgm_ops"}),
    )

    article_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("article.id", ondelete="CASCADE"))
    entity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("entity.id", ondelete="RESTRICT"))
    mention_text: Mapped[str] = mapped_column(String(500), nullable=False)
    start_offset: Mapped[int] = mapped_column(nullable=False)
    end_offset: Mapped[int] = mapped_column(nullable=False)
    confidence_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    context: Mapped[str | None] = mapped_column(Text)

    article: Mapped[Article] = relationship(back_populates="entity_mentions", lazy="selectin")
    entity: Mapped[Entity] = relationship(back_populates="mentions", lazy="selectin")
