"""
Application configuration using Pydantic Settings v2.

All settings are loaded from environment variables with fallback defaults.
Settings are grouped by concern and composed into a root Settings object.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE_CONFIG = SettingsConfigDict(
    env_file=".env",
    env_file_encoding="utf-8",
    extra="ignore",
)


class AppSettings(BaseSettings):
    """Core application settings."""

    model_config = SettingsConfigDict(**ENV_FILE_CONFIG, env_prefix="APP_")

    name: str = "kumbh-monitor"
    version: str = "0.1.0"
    env: Literal["development", "staging", "production", "testing"] = "development"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    connect_external_services: bool = True
    cors_allow_credentials: bool = True

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_production(self) -> bool:
        return self.env == "production"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_testing(self) -> bool:
        return self.env == "testing"


class DatabaseSettings(BaseSettings):
    """PostgreSQL connection settings."""

    model_config = SettingsConfigDict(**ENV_FILE_CONFIG, env_prefix="DATABASE_")

    host: str = "localhost"
    port: int = 5432
    user: str = "kumbh"
    password: SecretStr = SecretStr("changeme_in_production")
    name: str = "kumbh_monitor"
    echo: bool = False
    pool_size: int = 20
    max_overflow: int = 10
    pool_timeout: int = 30
    pool_recycle: int = 1800

    @computed_field  # type: ignore[prop-decorator]
    @property
    def async_url(self) -> str:
        """Build the async PostgreSQL DSN for asyncpg."""
        password = self.password.get_secret_value()
        return (
            f"postgresql+asyncpg://{self.user}:{password}"
            f"@{self.host}:{self.port}/{self.name}"
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def sync_url(self) -> str:
        """Build a sync PostgreSQL DSN for Alembic migrations."""
        password = self.password.get_secret_value()
        return (
            f"postgresql+psycopg://{self.user}:{password}"
            f"@{self.host}:{self.port}/{self.name}"
        )


class RedisSettings(BaseSettings):
    """Redis connection settings."""

    model_config = SettingsConfigDict(**ENV_FILE_CONFIG, env_prefix="REDIS_")

    host: str = "localhost"
    port: int = 6379
    password: SecretStr | None = None
    db: int = 0
    max_connections: int = 50
    health_check_interval: int = 30

    @computed_field  # type: ignore[prop-decorator]
    @property
    def url(self) -> str:
        """Build Redis connection URL."""
        if self.password:
            password = self.password.get_secret_value()
            return f"redis://:{password}@{self.host}:{self.port}/{self.db}"
        return f"redis://{self.host}:{self.port}/{self.db}"


class SecuritySettings(BaseSettings):
    """Security-related settings."""

    model_config = SettingsConfigDict(**ENV_FILE_CONFIG, env_prefix="")

    secret_key: SecretStr = SecretStr("replace-with-a-real-secret-key-in-production")
    api_key_header: str = "X-API-Key"


class CORSSettings(BaseSettings):
    """CORS configuration."""

    model_config = SettingsConfigDict(**ENV_FILE_CONFIG, env_prefix="CORS_")

    origins: str = "http://localhost:3000,http://localhost:8000"

    @field_validator("origins", mode="before")
    @classmethod
    def normalize_origins(cls, value: str | list[str]) -> str:
        if isinstance(value, list):
            return ",".join(value)
        return value

    @computed_field  # type: ignore[prop-decorator]
    @property
    def origin_list(self) -> list[str]:
        """Parse comma-separated origins into a list."""
        return [origin.strip() for origin in self.origins.split(",") if origin.strip()]


class Settings(BaseSettings):
    """
    Root settings container that composes all sub-settings.

    Usage:
        from app.core.config import get_settings
        settings = get_settings()
        print(settings.app.name)
        print(settings.database.async_url)
    """

    app: AppSettings = Field(default_factory=AppSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)
    cors: CORSSettings = Field(default_factory=CORSSettings)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Returns a cached singleton Settings instance.

    The @lru_cache ensures settings are only loaded once from
    environment variables. Call get_settings.cache_clear() if
    you need to reload (e.g., in tests).
    """
    return Settings()
