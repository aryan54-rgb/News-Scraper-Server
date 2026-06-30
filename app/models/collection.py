"""Collection scheduling and fetch lineage models."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ENUM, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, ModelBase
from app.database.enums import CollectorStatusEnum

if TYPE_CHECKING:
    from app.models.documents import RawDocument
    from app.models.sources import Source


class CollectorJob(Base, ModelBase):
    """Scheduled collection definition for a single source."""

    __tablename__ = "collector_job"
    __table_args__ = (
        UniqueConstraint("source_id", "name", name="uq_collector_job_source_name"),
        Index("idx_collector_job_source_id", "source_id"),
        Index("idx_collector_job_status_next_run", "status", "next_run_at"),
        Index("idx_collector_job_config_gin", "config", postgresql_using="gin"),
    )

    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("source.id", ondelete="RESTRICT"))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    job_type: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[CollectorStatusEnum] = mapped_column(
        ENUM(CollectorStatusEnum, name="collector_status_enum", create_type=False),
        nullable=False,
        server_default=CollectorStatusEnum.CREATED.value,
    )
    cron_expression: Mapped[str | None] = mapped_column(String(120))
    timezone: Mapped[str] = mapped_column(String(80), nullable=False, server_default="UTC")
    next_run_at: Mapped[datetime | None] = mapped_column()
    last_run_at: Mapped[datetime | None] = mapped_column()
    config: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)

    source: Mapped[Source] = relationship(back_populates="collector_jobs", lazy="selectin")
    fetch_logs: Mapped[list[FetchLog]] = relationship(back_populates="collector_job", lazy="selectin")


class FetchLog(Base, ModelBase):
    """Network fetch attempt and response metadata."""

    __tablename__ = "fetch_log"
    __table_args__ = (
        CheckConstraint("duration_ms IS NULL OR duration_ms >= 0", name="fetch_log_duration_nonnegative"),
        CheckConstraint("response_size_bytes IS NULL OR response_size_bytes >= 0", name="fetch_log_size_nonnegative"),
        Index("idx_fetch_log_source_fetched_at", "source_id", "fetched_at"),
        Index("idx_fetch_log_job_fetched_at", "collector_job_id", "fetched_at"),
        Index("idx_fetch_log_status_code", "status_code"),
        Index("idx_fetch_log_content_hash", "content_hash"),
    )

    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("source.id", ondelete="RESTRICT"))
    collector_job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("collector_job.id", ondelete="SET NULL")
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    status_code: Mapped[int | None] = mapped_column(Integer)
    content_hash: Mapped[str | None] = mapped_column(String(128))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    response_size_bytes: Mapped[int | None] = mapped_column(Integer)
    error_code: Mapped[str | None] = mapped_column(String(120))
    error_message: Mapped[str | None] = mapped_column(Text)
    fetched_at: Mapped[datetime] = mapped_column(nullable=False)

    source: Mapped[Source] = relationship(back_populates="fetch_logs", lazy="selectin")
    collector_job: Mapped[CollectorJob | None] = relationship(back_populates="fetch_logs", lazy="selectin")
    raw_documents: Mapped[list[RawDocument]] = relationship(back_populates="fetch_log", lazy="selectin")
