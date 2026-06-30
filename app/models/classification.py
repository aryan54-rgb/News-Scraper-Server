"""Classification result models."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Index, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ENUM, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, ModelBase
from app.database.enums import ClassificationStatusEnum

if TYPE_CHECKING:
    from app.models.documents import Article
    from app.models.taxonomy import TaxonomyNode, TaxonomyVersion


class Classification(Base, ModelBase):
    """Taxonomy assignment for a normalized article."""

    __tablename__ = "classification"
    __table_args__ = (
        UniqueConstraint(
            "article_id",
            "taxonomy_node_id",
            "taxonomy_version_id",
            name="uq_classification_article_node_version",
        ),
        CheckConstraint("confidence_score >= 0 AND confidence_score <= 1", name="classification_confidence_range"),
        Index("idx_classification_article_id", "article_id"),
        Index("idx_classification_node_status", "taxonomy_node_id", "status"),
        Index("idx_classification_version_status", "taxonomy_version_id", "status"),
        Index("idx_classification_metadata_gin", "metadata", postgresql_using="gin"),
    )

    article_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("article.id", ondelete="CASCADE"))
    taxonomy_node_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("taxonomy_node.id", ondelete="RESTRICT"))
    taxonomy_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("taxonomy_version.id", ondelete="RESTRICT")
    )
    status: Mapped[ClassificationStatusEnum] = mapped_column(
        ENUM(ClassificationStatusEnum, name="classification_status_enum", create_type=False),
        nullable=False,
        server_default=ClassificationStatusEnum.PENDING.value,
    )
    confidence_score: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    classifier_name: Mapped[str | None] = mapped_column(String(180))
    rationale: Mapped[str | None] = mapped_column(Text)
    metadata_: Mapped[dict[str, object]] = mapped_column("metadata", JSONB, nullable=False, default=dict)

    article: Mapped[Article] = relationship(back_populates="classifications", lazy="selectin")
    taxonomy_node: Mapped[TaxonomyNode] = relationship(back_populates="classifications", lazy="selectin")
    taxonomy_version: Mapped[TaxonomyVersion] = relationship(back_populates="classifications", lazy="selectin")
    evidence_items: Mapped[list[ClassificationEvidence]] = relationship(
        back_populates="classification",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class ClassificationEvidence(Base, ModelBase):
    """Text span or structured support for a classification."""

    __tablename__ = "classification_evidence"
    __table_args__ = (
        CheckConstraint("start_offset IS NULL OR start_offset >= 0", name="classification_evidence_start_nonnegative"),
        CheckConstraint("end_offset IS NULL OR end_offset >= 0", name="classification_evidence_end_nonnegative"),
        Index("idx_classification_evidence_classification_id", "classification_id"),
        Index("idx_classification_evidence_payload_gin", "payload", postgresql_using="gin"),
    )

    classification_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("classification.id", ondelete="CASCADE")
    )
    quote: Mapped[str | None] = mapped_column(Text)
    start_offset: Mapped[int | None] = mapped_column()
    end_offset: Mapped[int | None] = mapped_column()
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)

    classification: Mapped[Classification] = relationship(back_populates="evidence_items", lazy="selectin")
