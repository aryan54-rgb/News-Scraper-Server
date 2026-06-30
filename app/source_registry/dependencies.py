"""FastAPI dependency providers for the Source Registry."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_session
from app.repositories.sqlalchemy import (
    SQLAlchemySourceGroupRepository,
    SQLAlchemySourceRepository,
    SQLAlchemySourceTypeRepository,
)
from app.source_registry.service import SourceRegistryService


async def get_source_registry_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SourceRegistryService:
    return SourceRegistryService(
        sources=SQLAlchemySourceRepository(session),
        source_types=SQLAlchemySourceTypeRepository(session),
        source_groups=SQLAlchemySourceGroupRepository(session),
    )

