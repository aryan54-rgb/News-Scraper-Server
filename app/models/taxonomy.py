"""Versioned taxonomy tree models."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, ModelBase

if TYPE_CHECKING:
    from app.models.classification import Classification


class TaxonomyVersion(Base, ModelBase):
    """Immutable taxonomy release used by classifications."""

    __tablename__ = "taxonomy_version"
    __table_args__ = (
        UniqueConstraint("name", "version_number", name="uq_taxonomy_version_name_number"),
        Index(
            "uq_taxonomy_version_current",
            "name",
            unique=True,
            postgresql_where=text("is_current = true AND deleted_at IS NULL"),
        ),
    )

    name: Mapped[str] = mapped_column(String(180), nullable=False)
    version_number: Mapped[int] = mapped_column(nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_current: Mapped[bool] = mapped_column(nullable=False, server_default="false")
    published_at: Mapped[datetime | None] = mapped_column()
    metadata_: Mapped[dict[str, object]] = mapped_column("metadata", JSONB, nullable=False, default=dict)

    nodes: Mapped[list[TaxonomyNode]] = relationship(back_populates="taxonomy_version", lazy="selectin")
    classifications: Mapped[list[Classification]] = relationship(
        back_populates="taxonomy_version",
        lazy="selectin",
    )


class TaxonomyNode(Base, ModelBase):
    """Single node in a versioned taxonomy tree."""

    __tablename__ = "taxonomy_node"
    __table_args__ = (
        UniqueConstraint("taxonomy_version_id", "code", name="uq_taxonomy_node_version_code"),
        CheckConstraint("depth >= 0", name="taxonomy_node_depth_nonnegative"),
        Index("idx_taxonomy_node_version_parent", "taxonomy_version_id", "parent_id"),
        Index("idx_taxonomy_node_path", "path"),
        Index("idx_taxonomy_node_name_trgm", "name", postgresql_using="gin", postgresql_ops={"name": "gin_trgm_ops"}),
        Index("idx_taxonomy_node_metadata_gin", "metadata", postgresql_using="gin"),
    )

    taxonomy_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("taxonomy_version.id", ondelete="RESTRICT")
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("taxonomy_node.id", ondelete="RESTRICT"))
    code: Mapped[str] = mapped_column(String(120), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    path: Mapped[str] = mapped_column(String(1000), nullable=False)
    depth: Mapped[int] = mapped_column(nullable=False, server_default="0")
    sort_order: Mapped[int] = mapped_column(nullable=False, server_default="0")
    metadata_: Mapped[dict[str, object]] = mapped_column("metadata", JSONB, nullable=False, default=dict)

    taxonomy_version: Mapped[TaxonomyVersion] = relationship(back_populates="nodes", lazy="selectin")
    parent: Mapped[TaxonomyNode | None] = relationship(
        remote_side="TaxonomyNode.id",
        back_populates="children",
        lazy="selectin",
    )
    children: Mapped[list[TaxonomyNode]] = relationship(back_populates="parent", lazy="selectin")
    classifications: Mapped[list[Classification]] = relationship(back_populates="taxonomy_node", lazy="selectin")
