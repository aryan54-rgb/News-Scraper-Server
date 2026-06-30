"""
Redis client manager with async connection pooling.

Provides a singleton Redis connection pool that is initialized
during application startup and closed during shutdown.
"""

from __future__ import annotations

from redis.asyncio import ConnectionPool, Redis

from app.core.config import RedisSettings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Module-level singleton references
_pool: ConnectionPool | None = None
_client: Redis | None = None


async def init_redis(settings: RedisSettings) -> Redis:
    """
    Initialize the Redis connection pool and client.

    Called once during application startup (lifespan).
    """
    global _pool, _client  # noqa: PLW0603

    _pool = ConnectionPool.from_url(
        settings.url,
        max_connections=settings.max_connections,
        decode_responses=True,
        health_check_interval=settings.health_check_interval,
    )
    _client = Redis(connection_pool=_pool)

    # Verify connectivity
    try:
        await _client.ping()
        logger.info("redis_connected", host=settings.host, port=settings.port)
    except Exception:
        logger.error("redis_connection_failed", host=settings.host, port=settings.port)
        raise

    return _client


async def close_redis() -> None:
    """
    Close the Redis connection pool.

    Called once during application shutdown (lifespan).
    """
    global _pool, _client  # noqa: PLW0603

    if _client is not None:
        await _client.aclose()
        _client = None
        logger.info("redis_client_closed")

    if _pool is not None:
        await _pool.disconnect()
        _pool = None
        logger.info("redis_pool_disconnected")


def get_redis() -> Redis:
    """
    FastAPI dependency that returns the Redis client.

    Raises RuntimeError if called before init_redis().

    Usage:
        @router.get("/example")
        async def example(redis: Redis = Depends(get_redis)):
            await redis.set("key", "value")
    """
    if _client is None:
        raise RuntimeError(
            "Redis client is not initialized. "
            "Ensure init_redis() is called during app startup."
        )
    return _client


async def ping_redis() -> bool:
    """Return True when the initialized Redis client responds to PING."""
    if _client is None:
        return False

    try:
        return bool(await _client.ping())
    except Exception:
        logger.exception("redis_ping_failed")
        return False
