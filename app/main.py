"""FastAPI application factory and lifecycle wiring."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.middleware import ErrorHandlingMiddleware, RequestIDMiddleware
from app.api.router import api_router
from app.core.config import Settings, get_settings
from app.core.logging import get_logger, setup_logging
from app.core.redis import close_redis, init_redis
from app.database.session import close_database, init_database

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings

    if settings.app.connect_external_services:
        await init_database(settings.database)
        await init_redis(settings.redis)
    else:
        logger.info("external_services_skipped", environment=settings.app.env)

    yield

    if settings.app.connect_external_services:
        await close_redis()
        await close_database()


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = settings or get_settings()
    setup_logging(
        log_level=settings.app.log_level,
        json_output=settings.app.is_production,
    )

    app = FastAPI(
        title=settings.app.name,
        version=settings.app.version,
        debug=settings.app.debug,
        lifespan=lifespan,
        docs_url=None if settings.app.is_production else "/docs",
        redoc_url=None if settings.app.is_production else "/redoc",
        openapi_url=None if settings.app.is_production else "/openapi.json",
    )
    app.state.settings = settings

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors.origin_list,
        allow_credentials=settings.app.cors_allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(ErrorHandlingMiddleware)
    app.add_middleware(RequestIDMiddleware)
    app.include_router(api_router)

    return app


app = create_app()
