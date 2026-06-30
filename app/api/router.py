"""Top-level API router."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.routes.source_registry import router as source_registry_router
from app.api.routes.system import router as system_router

api_router = APIRouter()
api_router.include_router(system_router)
api_router.include_router(source_registry_router)
