"""Event resolution models."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Index, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ENUM, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, ModelBase
from app.database.enums import EventStatusEnum

if TYPE_CHECKING:
    from app.models.documents import Article


class Event(Base, ModelBase):
    """Real-world occurrence compiled from one or more articles."""

    __tablename__ = "event"
    __table_args__ = (
        CheckConstraint("severity BETWEEN 1 AND 5", name="event_severity_range"),
        Index("idx_event_status_last_seen", "status", "last_seen_at"),
        Index("idx_event_started_at", "started_at"),
        Index("idx_event_title_trgm", "title", postgresql_using="gin", postgresql_ops={"title": "gin_trgm_ops"}),
        Index("idx_event_metadata_gin", "metadata", postgresql_using="gin"),
    )

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[EventStatusEnum] = mapped_column(
        ENUM(EventStatusEnum, name="event_status_enum", create_type=False),
        nullable=False,
        server_default=EventStatusEnum.IDENTIFIED.value,
    )
    severity: Mapped[int] = mapped_column(nullable=False, server_default="1")
    confidence_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    started_at: Mapped[datetime | None] = mapped_column()
    ended_at: Mapped[datetime | None] = mapped_column()
    last_seen_at: Mapped[datetime | None] = mapped_column()
    metadata_: Mapped[dict[str, object]] = mapped_column("metadata", JSONB, nullable=False, default=dict)

    article_events: Mapped[list[ArticleEvent]] = relationship(back_populates="event", lazy="selectin")


class ArticleEvent(Base, ModelBase):
    """Association row linking articles to events with confidence evidence."""

    __tablename__ = "article_event"
    __table_args__ = (
        UniqueConstraint("article_id", "event_id", name="uq_article_event_pair"),
        CheckConstraint(
            "confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 1)",
            name="article_event_confidence_range",
        ),
        Index("idx_article_event_article_id", "article_id"),
        Index("idx_article_event_event_id", "event_id"),
    )

    article_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("article.id", ondelete="CASCADE"))
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("event.id", ondelete="CASCADE"))
    confidence_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    linked_at: Mapped[datetime] = mapped_column(nullable=False)

    article: Mapped[Article] = relationship(back_populates="article_events", lazy="selectin")
    event: Mapped[Event] = relationship(back_populates="article_events", lazy="selectin")
