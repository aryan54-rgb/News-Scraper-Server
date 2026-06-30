"""Common collector data models."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CollectorHealthStatus(StrEnum):
    """Health status reported by collectors."""

    UNKNOWN = "unknown"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILING = "failing"


class Attachment(BaseModel):
    """A file-like resource discovered during collection."""

    model_config = ConfigDict(extra="forbid")

    url: str
    content_type: str | None = None
    filename: str | None = None
    size_bytes: int | None = Field(default=None, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RawDocument(BaseModel):
    """Normalized collector output consumed by downstream modules."""

    model_config = ConfigDict(extra="forbid")

    source_id: uuid.UUID
    original_url: str
    canonical_url: str
    title: str | None = None
    author: str | None = None
    publication_date: datetime | None = None
    raw_content: str | bytes | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    attachments: list[Attachment] = Field(default_factory=list)
    fetch_timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    http_status: int | None = Field(default=None, ge=100, le=599)
    content_type: str | None = None

    @field_validator("metadata", mode="before")
    @classmethod
    def ensure_metadata_dict(cls, value: Mapping[str, Any] | None) -> dict[str, Any]:
        return dict(value or {})

    @property
    def size_bytes(self) -> int:
        """Best-effort byte size for observability."""
        if self.raw_content is None:
            return 0
        if isinstance(self.raw_content, bytes):
            return len(self.raw_content)
        return len(self.raw_content.encode("utf-8"))


class CollectorHealth(BaseModel):
    """Health check result returned by a collector."""

    model_config = ConfigDict(extra="forbid")

    status: CollectorHealthStatus = CollectorHealthStatus.UNKNOWN
    message: str | None = None
    checked_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)


class RetryPolicy(BaseModel):
    """Retry behavior used by the collector manager."""

    model_config = ConfigDict(extra="forbid")

    max_attempts: int = Field(default=3, ge=1, le=10)
    backoff_seconds: float = Field(default=1.0, ge=0, le=3600)
    backoff_multiplier: float = Field(default=2.0, ge=1.0, le=10.0)
    retry_on_statuses: set[int] = Field(default_factory=lambda: {408, 429, 500, 502, 503, 504})


class CollectionResult(BaseModel):
    """Manager execution result and observability summary."""

    model_config = ConfigDict(extra="forbid")

    source_id: uuid.UUID
    collector_key: str
    documents: list[RawDocument]
    duration_ms: int
    retry_count: int
    bytes_downloaded: int
    http_statuses: list[int] = Field(default_factory=list)
    success: bool = True
