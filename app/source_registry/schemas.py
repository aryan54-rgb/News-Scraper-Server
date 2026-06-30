"""Pydantic schemas for Source Registry APIs."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, field_validator, model_validator

from app.database.enums import SourceStatusEnum, SourceTypeEnum


class PublicSourceType(StrEnum):
    RSS_FEED = "rss_feed"
    NEWS_WEBSITE = "news_website"
    GOVERNMENT_PORTAL = "government_portal"
    X_ACCOUNT = "x_account"
    BLOG = "blog"


class HealthStatus(StrEnum):
    UNKNOWN = "unknown"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILING = "failing"
    DISABLED = "disabled"


class AuthenticationType(StrEnum):
    NONE = "none"
    API_KEY = "api_key"
    BEARER_TOKEN = "bearer_token"
    BASIC = "basic"
    OAUTH2 = "oauth2"


class KeywordMode(StrEnum):
    ANY = "any"
    ALL = "all"
    BOOLEAN = "boolean"


class SchedulingConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    refresh_interval_seconds: int = Field(default=900, ge=60, le=604800)
    cron_expression: str | None = Field(default=None, max_length=120)
    jitter_seconds: int = Field(default=0, ge=0, le=3600)
    timezone: str = Field(default="UTC", min_length=1, max_length=80)


class AuthenticationConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: AuthenticationType = AuthenticationType.NONE
    username: str | None = Field(default=None, max_length=255)
    secret_ref: str | None = Field(default=None, max_length=255)
    token_url: AnyHttpUrl | None = None
    scopes: list[str] = Field(default_factory=list, max_length=25)

    @model_validator(mode="after")
    def validate_authentication(self) -> "AuthenticationConfiguration":
        if self.type != AuthenticationType.NONE and not self.secret_ref:
            raise ValueError("secret_ref is required for authenticated sources")
        if self.type == AuthenticationType.BASIC and not self.username:
            raise ValueError("username is required for basic authentication")
        if self.type == AuthenticationType.OAUTH2 and self.token_url is None:
            raise ValueError("token_url is required for oauth2 authentication")
        return self


class HeaderConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    value: str = Field(min_length=1, max_length=1000)

    @field_validator("name")
    @classmethod
    def validate_header_name(cls, value: str) -> str:
        if any(char.isspace() for char in value) or ":" in value:
            raise ValueError("header names cannot contain whitespace or colons")
        return value


class RateLimitConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requests_per_minute: int = Field(default=30, ge=1, le=10000)
    burst: int = Field(default=5, ge=1, le=1000)


class RetryPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_attempts: int = Field(default=3, ge=0, le=10)
    backoff_seconds: int = Field(default=30, ge=0, le=3600)
    backoff_multiplier: float = Field(default=2.0, ge=1.0, le=10.0)
    retry_on_statuses: list[int] = Field(default_factory=lambda: [408, 429, 500, 502, 503, 504])


class KeywordConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    terms: list[str] = Field(default_factory=list, max_length=200)
    exclude_terms: list[str] = Field(default_factory=list, max_length=200)
    mode: KeywordMode = KeywordMode.ANY
    boolean_query: str | None = Field(default=None, max_length=1000)

    @field_validator("terms", "exclude_terms")
    @classmethod
    def validate_terms(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values if value.strip()]
        if len(normalized) != len(set(term.lower() for term in normalized)):
            raise ValueError("keywords must be unique within a list")
        return normalized

    @model_validator(mode="after")
    def validate_boolean_mode(self) -> "KeywordConfiguration":
        if self.mode == KeywordMode.BOOLEAN and not self.boolean_query:
            raise ValueError("boolean_query is required when keyword mode is boolean")
        return self


class HealthMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    last_successful_fetch: datetime | None = None
    last_failure: datetime | None = None
    consecutive_failures: int = Field(default=0, ge=0)
    average_response_time_ms: float | None = Field(default=None, ge=0)
    articles_collected: int = Field(default=0, ge=0)
    last_classification: datetime | None = None
    health_status: HealthStatus = HealthStatus.UNKNOWN
    success_rate: float | None = Field(default=None, ge=0, le=1)


class SourceMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    public_type: str | None = Field(default=None, max_length=80)
    country: str | None = Field(default=None, min_length=2, max_length=80)
    language: str | None = Field(default=None, min_length=2, max_length=20)
    enabled: bool = False
    priority: int = Field(default=5, ge=1, le=10)
    tags: list[str] = Field(default_factory=list, max_length=50)
    scheduling: SchedulingConfiguration = Field(default_factory=SchedulingConfiguration)
    authentication: AuthenticationConfiguration = Field(default_factory=AuthenticationConfiguration)
    headers: list[HeaderConfiguration] = Field(default_factory=list, max_length=50)
    rate_limit: RateLimitConfiguration = Field(default_factory=RateLimitConfiguration)
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)
    keywords: KeywordConfiguration = Field(default_factory=KeywordConfiguration)
    health: HealthMetrics = Field(default_factory=HealthMetrics)
    collector: dict[str, Any] = Field(default_factory=dict)

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, values: list[str]) -> list[str]:
        normalized = [value.strip().lower() for value in values if value.strip()]
        if len(normalized) != len(set(normalized)):
            raise ValueError("tags must be unique")
        return normalized


class SourceBase(BaseModel):
    name: str = Field(min_length=1, max_length=255, examples=["Prayagraj District News"])
    url: AnyHttpUrl = Field(examples=["https://example.gov.in/news/rss.xml"])
    source_type_id: uuid.UUID | None = None
    source_type: str | None = Field(
        default=None,
        description="Source type slug, name, code, or id.",
        examples=[PublicSourceType.RSS_FEED],
    )
    domain: str | None = Field(default=None, max_length=255)
    status: SourceStatusEnum = SourceStatusEnum.REGISTERED
    reliability_score: float | None = Field(default=None, ge=0, le=1)
    country: str | None = Field(default=None, examples=["IN"])
    language: str | None = Field(default=None, examples=["en"])
    enabled: bool = False
    priority: int = Field(default=5, ge=1, le=10)
    tags: list[str] = Field(default_factory=list)
    group_ids: list[uuid.UUID] = Field(default_factory=list)
    scheduling: SchedulingConfiguration = Field(default_factory=SchedulingConfiguration)
    authentication: AuthenticationConfiguration = Field(default_factory=AuthenticationConfiguration)
    headers: list[HeaderConfiguration] = Field(default_factory=list)
    rate_limit: RateLimitConfiguration = Field(default_factory=RateLimitConfiguration)
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)
    keywords: KeywordConfiguration = Field(default_factory=KeywordConfiguration)
    collector: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_source_type_reference(self) -> "SourceBase":
        if self.source_type_id is None and not self.source_type:
            raise ValueError("source_type or source_type_id is required")
        return self


class SourceCreate(SourceBase):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "name": "Prayagraj Official RSS",
                    "url": "https://prayagraj.nic.in/news/rss.xml",
                    "source_type": "rss_feed",
                    "country": "IN",
                    "language": "en",
                    "enabled": True,
                    "priority": 8,
                    "tags": ["official", "prayagraj"],
                    "scheduling": {"enabled": True, "refresh_interval_seconds": 900},
                    "authentication": {"type": "none"},
                    "rate_limit": {"requests_per_minute": 20, "burst": 3},
                    "retry_policy": {"max_attempts": 3, "backoff_seconds": 30, "backoff_multiplier": 2.0},
                    "keywords": {"terms": ["kumbh", "traffic"], "mode": "any"},
                }
            ]
        }
    )


class SourceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    url: AnyHttpUrl | None = None
    source_type_id: uuid.UUID | None = None
    source_type: str | None = None
    domain: str | None = Field(default=None, max_length=255)
    status: SourceStatusEnum | None = None
    reliability_score: float | None = Field(default=None, ge=0, le=1)
    country: str | None = None
    language: str | None = None
    enabled: bool | None = None
    priority: int | None = Field(default=None, ge=1, le=10)
    tags: list[str] | None = None
    group_ids: list[uuid.UUID] | None = None
    scheduling: SchedulingConfiguration | None = None
    authentication: AuthenticationConfiguration | None = None
    headers: list[HeaderConfiguration] | None = None
    rate_limit: RateLimitConfiguration | None = None
    retry_policy: RetryPolicy | None = None
    keywords: KeywordConfiguration | None = None
    collector: dict[str, Any] | None = None


class SourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    url: str | None
    domain: str | None
    status: SourceStatusEnum
    reliability_score: float | None
    source_type_id: uuid.UUID
    source_type: str
    source_type_name: str
    country: str | None
    language: str | None
    enabled: bool
    priority: int
    tags: list[str]
    group_ids: list[uuid.UUID]
    scheduling: SchedulingConfiguration
    authentication: AuthenticationConfiguration
    headers: list[HeaderConfiguration]
    rate_limit: RateLimitConfiguration
    retry_policy: RetryPolicy
    keywords: KeywordConfiguration
    health: HealthMetrics
    collector: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class SourceListResponse(BaseModel):
    items: list[SourceRead]
    total: int
    page: int
    page_size: int


class SourceTypeBase(BaseModel):
    slug: str = Field(min_length=2, max_length=80, pattern=r"^[a-z0-9][a-z0-9_:-]*$")
    code: SourceTypeEnum = SourceTypeEnum.OTHER
    name: str = Field(min_length=1, max_length=100)
    description: str | None = None
    collector_key: str | None = Field(default=None, max_length=120)
    capabilities: list[str] = Field(default_factory=list)
    config_schema: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True


class SourceTypeCreate(SourceTypeBase):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "slug": "telegram",
                    "code": "social",
                    "name": "Telegram Channel",
                    "description": "Telegram public channel monitored by a future social collector.",
                    "collector_key": "telegram",
                    "capabilities": ["social", "channel"],
                    "config_schema": {},
                    "is_active": True,
                }
            ]
        }
    )


class SourceTypeUpdate(BaseModel):
    slug: str | None = Field(default=None, min_length=2, max_length=80, pattern=r"^[a-z0-9][a-z0-9_:-]*$")
    code: SourceTypeEnum | None = None
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = None
    collector_key: str | None = Field(default=None, max_length=120)
    capabilities: list[str] | None = None
    config_schema: dict[str, Any] | None = None
    is_active: bool | None = None


class SourceTypeRead(SourceTypeBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class SourceGroupBase(BaseModel):
    name: str = Field(min_length=1, max_length=255, examples=["Official Government Sources"])
    description: str | None = None


class SourceGroupCreate(SourceGroupBase):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "name": "Official Government Sources",
                    "description": "Verified portals and feeds from government departments.",
                }
            ]
        }
    )


class SourceGroupUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None


class SourceGroupRead(SourceGroupBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_count: int = 0
    created_at: datetime
    updated_at: datetime


class SourceTestResponse(BaseModel):
    source_id: uuid.UUID
    status: Literal["valid"]
    collector_compatible: bool
    warnings: list[str] = Field(default_factory=list)
