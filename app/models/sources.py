"""Source registry models."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Index, Numeric, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import ENUM, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, ModelBase
from app.database.enums import SourceStatusEnum, SourceTypeEnum

if TYPE_CHECKING:
    from app.models.collection import CollectorJob, FetchLog
    from app.models.documents import Article, RawDocument


class SourceType(Base, ModelBase):
    """Lookup row for source categories, backed by a PostgreSQL enum code."""

    __tablename__ = "source_type"
    __table_args__ = (
        UniqueConstraint("code", name="uq_source_type_code"),
        UniqueConstraint("name", name="uq_source_type_name"),
    )

    code: Mapped[SourceTypeEnum] = mapped_column(
        ENUM(SourceTypeEnum, name="source_type_enum", create_type=False),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    sources: Mapped[list[Source]] = relationship(back_populates="source_type", lazy="selectin")


class SourceGroupMembership(Base, ModelBase):
    """Association table connecting sources to groups."""

    __tablename__ = "source_group_membership"
    __table_args__ = (
        UniqueConstraint("source_id", "source_group_id", name="uq_source_group_membership_pair"),
        Index("idx_source_group_membership_source_id", "source_id"),
        Index("idx_source_group_membership_group_id", "source_group_id"),
    )

    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("source.id", ondelete="CASCADE"))
    source_group_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("source_group.id", ondelete="CASCADE")
    )

    source: Mapped[Source] = relationship(back_populates="group_memberships", lazy="selectin")
    group: Mapped[SourceGroup] = relationship(back_populates="source_memberships", lazy="selectin")


class Source(Base, ModelBase):
    """External publisher, feed, API, or platform monitored by the system."""

    __tablename__ = "source"
    __table_args__ = (
        CheckConstraint(
            "reliability_score IS NULL OR (reliability_score >= 0 AND reliability_score <= 1)",
            name="source_reliability_score_range",
        ),
        UniqueConstraint("domain", "source_type_id", name="uq_source_domain_type"),
        Index("idx_source_source_type_id", "source_type_id"),
        Index("idx_source_domain", "domain"),
        Index("idx_source_status", "status"),
        Index("idx_source_active_not_deleted", "status", postgresql_where=text("deleted_at IS NULL")),
        Index("idx_source_metadata_gin", "metadata", postgresql_using="gin"),
    )

    source_type_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("source_type.id", ondelete="RESTRICT"))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str | None] = mapped_column(Text)
    domain: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[SourceStatusEnum] = mapped_column(
        ENUM(SourceStatusEnum, name="source_status_enum", create_type=False),
        nullable=False,
        server_default=SourceStatusEnum.REGISTERED.value,
    )
    reliability_score: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))
    metadata_: Mapped[dict[str, object]] = mapped_column("metadata", JSONB, nullable=False, default=dict)

    source_type: Mapped[SourceType] = relationship(back_populates="sources", lazy="selectin")
    group_memberships: Mapped[list[SourceGroupMembership]] = relationship(
        back_populates="source",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    groups: Mapped[list[SourceGroup]] = relationship(
        secondary="source_group_membership",
        back_populates="sources",
        viewonly=True,
        lazy="selectin",
    )
    collector_jobs: Mapped[list[CollectorJob]] = relationship(back_populates="source", lazy="selectin")
    fetch_logs: Mapped[list[FetchLog]] = relationship(back_populates="source", lazy="selectin")
    raw_documents: Mapped[list[RawDocument]] = relationship(back_populates="source", lazy="selectin")
    articles: Mapped[list[Article]] = relationship(back_populates="source", lazy="selectin")


class SourceGroup(Base, ModelBase):
    """Logical source grouping for monitoring and filtering."""

    __tablename__ = "source_group"
    __table_args__ = (
        Index(
            "uq_source_group_name_not_deleted",
            "name",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    source_memberships: Mapped[list[SourceGroupMembership]] = relationship(
        back_populates="group",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    sources: Mapped[list[Source]] = relationship(
        secondary="source_group_membership",
        back_populates="groups",
        viewonly=True,
        lazy="selectin",
    )
