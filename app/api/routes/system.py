"""System health and metadata endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from app.core.config import Settings
from app.core.redis import ping_redis
from app.database.session import ping_database

router = APIRouter(tags=["system"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "timestamp": datetime.now(UTC).isoformat(),
    }


@router.get("/version")
async def version(request: Request) -> dict[str, str]:
    settings: Settings = request.app.state.settings
    return {
        "name": settings.app.name,
        "version": settings.app.version,
        "environment": settings.app.env,
    }


@router.get("/ready")
async def ready(request: Request) -> JSONResponse:
    settings: Settings = request.app.state.settings
    checks: dict[str, Any] = {
        "database": await ping_database(),
        "redis": await ping_redis(),
    }
    is_ready = all(checks.values())

    if not settings.app.connect_external_services:
        checks["external_services"] = "disabled"
        is_ready = True

    return JSONResponse(
        status_code=status.HTTP_200_OK if is_ready else status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "status": "ready" if is_ready else "not_ready",
            "checks": checks,
            "timestamp": datetime.now(UTC).isoformat(),
        },
    )
