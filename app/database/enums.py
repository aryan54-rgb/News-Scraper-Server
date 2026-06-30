"""Database-backed enum values used by Phase 1 ORM models."""

from __future__ import annotations

from enum import StrEnum


class SourceTypeEnum(StrEnum):
    RSS = "rss"
    WEBSITE = "website"
    API = "api"
    SOCIAL = "social"
    GOVERNMENT = "government"
    WIRE = "wire"
    OTHER = "other"


class SourceStatusEnum(StrEnum):
    REGISTERED = "registered"
    ACTIVE = "active"
    DEGRADED = "degraded"
    SUSPENDED = "suspended"
    DEPRECATED = "deprecated"


class CollectorStatusEnum(StrEnum):
    CREATED = "created"
    SCHEDULED = "scheduled"
    RUNNING = "running"
    PAUSED = "paused"
    FAILED = "failed"
    ARCHIVED = "archived"


class ClassificationStatusEnum(StrEnum):
    PENDING = "pending"
    CLASSIFIED = "classified"
    VALIDATED = "validated"
    STALE = "stale"
    REJECTED = "rejected"


class EntityTypeEnum(StrEnum):
    PERSON = "person"
    ORGANIZATION = "organization"
    LOCATION = "location"
    GOVERNMENT = "government"
    FACILITY = "facility"
    EVENT = "event"
    OTHER = "other"


class EventStatusEnum(StrEnum):
    IDENTIFIED = "identified"
    ACTIVE = "active"
    CONCLUDED = "concluded"
    MERGED = "merged"
    ARCHIVED = "archived"


class KeywordPriorityEnum(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
