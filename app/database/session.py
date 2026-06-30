"""
Async SQLAlchemy session management.

Provides:
- Async engine creation with connection pooling
- Async session factory
- FastAPI dependency for request-scoped sessions
- Startup/shutdown lifecycle functions
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import DatabaseSettings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Module-level singleton references
_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


async def init_database(settings: DatabaseSettings) -> AsyncEngine:
    """
    Create the async engine and session factory.

    Called once during application startup (lifespan).
    """
    global _engine, _session_factory  # noqa: PLW0603

    _engine = create_async_engine(
        settings.async_url,
        echo=settings.echo,
        pool_size=settings.pool_size,
        max_overflow=settings.max_overflow,
        pool_timeout=settings.pool_timeout,
        pool_recycle=settings.pool_recycle,
        pool_pre_ping=True,
    )

    _session_factory = async_sessionmaker(
        bind=_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    # Verify connectivity
    try:
        async with _engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info(
            "database_connected",
            host=settings.host,
            port=settings.port,
            database=settings.name,
        )
    except Exception:
        logger.error(
            "database_connection_failed",
            host=settings.host,
            port=settings.port,
            database=settings.name,
        )
        raise

    return _engine


async def close_database() -> None:
    """
    Dispose the engine and close all connections.

    Called once during application shutdown (lifespan).
    """
    global _engine, _session_factory  # noqa: PLW0603

    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
        logger.info("database_disconnected")


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that yields a request-scoped async session.

    The session is automatically committed on success and
    rolled back on exception.

    Usage:
        @router.get("/example")
        async def example(session: AsyncSession = Depends(get_session)):
            result = await session.execute(select(Source))
    """
    if _session_factory is None:
        raise RuntimeError(
            "Database session factory is not initialized. "
            "Ensure init_database() is called during app startup."
        )

    async with _session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def get_engine() -> AsyncEngine:
    """
    Returns the async engine. Used by Alembic and health checks.
    """
    if _engine is None:
        raise RuntimeError(
            "Database engine is not initialized. "
            "Ensure init_database() is called during app startup."
        )
    return _engine


async def ping_database() -> bool:
    """Return True when the initialized engine can execute a simple query."""
    if _engine is None:
        return False

    try:
        async with _engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        logger.exception("database_ping_failed")
        return False

    return True
