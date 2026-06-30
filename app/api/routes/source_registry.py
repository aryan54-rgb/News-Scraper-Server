"""REST API routes for the Source Registry."""

from __future__ import annotations

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response, status

from app.source_registry.dependencies import get_source_registry_service
from app.source_registry.schemas import (
    SourceCreate,
    SourceGroupCreate,
    SourceGroupRead,
    SourceGroupUpdate,
    SourceListResponse,
    SourceRead,
    SourceTestResponse,
    SourceTypeCreate,
    SourceTypeRead,
    SourceTypeUpdate,
    SourceUpdate,
)
from app.source_registry.security import Principal, require_admin
from app.source_registry.service import SourceRegistryService

router = APIRouter(tags=["source-registry"])


@router.get(
    "/sources",
    response_model=SourceListResponse,
    summary="List monitored sources",
)
async def list_sources(
    service: Annotated[SourceRegistryService, Depends(get_source_registry_service)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
    search: str | None = None,
    name: str | None = None,
    country: str | None = None,
    language: str | None = None,
    type: str | None = Query(default=None, alias="type"),  # noqa: A002
    status: str | None = None,
    priority: int | None = Query(default=None, ge=1, le=10),
    tags: list[str] | None = Query(default=None),
    enabled: bool | None = None,
    group_id: uuid.UUID | None = None,
    sort_by: str | None = Query(default="created_at"),
    sort_direction: Literal["asc", "desc"] = "desc",
) -> SourceListResponse:
    criteria = {
        "search": search,
        "name": name,
        "country": country,
        "language": language,
        "source_type": type,
        "status": status,
        "priority": priority,
        "tags": tags,
        "enabled": enabled,
        "group_id": group_id,
    }
    page_result = await service.list_sources(
        page=page,
        page_size=page_size,
        criteria=criteria,
        sort_by=sort_by,
        sort_direction=sort_direction,
    )
    return SourceListResponse(
        items=list(page_result.items),
        total=page_result.total,
        page=page_result.page,
        page_size=page_result.page_size,
    )


@router.get("/sources/{source_id}", response_model=SourceRead, summary="Get a monitored source")
async def get_source(
    source_id: uuid.UUID,
    service: Annotated[SourceRegistryService, Depends(get_source_registry_service)],
) -> SourceRead:
    return await service.get_source(source_id)


@router.post(
    "/sources",
    response_model=SourceRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a monitored source",
)
async def create_source(
    payload: SourceCreate,
    service: Annotated[SourceRegistryService, Depends(get_source_registry_service)],
    _: Annotated[Principal, Depends(require_admin)],
) -> SourceRead:
    return await service.create_source(payload)


@router.put("/sources/{source_id}", response_model=SourceRead, summary="Update a monitored source")
async def update_source(
    source_id: uuid.UUID,
    payload: SourceUpdate,
    service: Annotated[SourceRegistryService, Depends(get_source_registry_service)],
    _: Annotated[Principal, Depends(require_admin)],
) -> SourceRead:
    return await service.update_source(source_id, payload)


@router.delete(
    "/sources/{source_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a monitored source",
)
async def delete_source(
    source_id: uuid.UUID,
    service: Annotated[SourceRegistryService, Depends(get_source_registry_service)],
    _: Annotated[Principal, Depends(require_admin)],
) -> Response:
    await service.delete_source(source_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/sources/{source_id}/enable", response_model=SourceRead, summary="Enable a source")
async def enable_source(
    source_id: uuid.UUID,
    service: Annotated[SourceRegistryService, Depends(get_source_registry_service)],
    _: Annotated[Principal, Depends(require_admin)],
) -> SourceRead:
    return await service.enable_source(source_id)


@router.post("/sources/{source_id}/disable", response_model=SourceRead, summary="Disable a source")
async def disable_source(
    source_id: uuid.UUID,
    service: Annotated[SourceRegistryService, Depends(get_source_registry_service)],
    _: Annotated[Principal, Depends(require_admin)],
) -> SourceRead:
    return await service.disable_source(source_id)


@router.post("/sources/{source_id}/test", response_model=SourceTestResponse, summary="Validate source configuration")
async def test_source(
    source_id: uuid.UUID,
    service: Annotated[SourceRegistryService, Depends(get_source_registry_service)],
    _: Annotated[Principal, Depends(require_admin)],
) -> SourceTestResponse:
    return await service.test_source(source_id)


@router.get("/source-types", response_model=list[SourceTypeRead], summary="List source types")
async def list_source_types(
    service: Annotated[SourceRegistryService, Depends(get_source_registry_service)],
) -> list[SourceTypeRead]:
    return await service.list_source_types()


@router.post(
    "/source-types",
    response_model=SourceTypeRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a source type",
)
async def create_source_type(
    payload: SourceTypeCreate,
    service: Annotated[SourceRegistryService, Depends(get_source_registry_service)],
    _: Annotated[Principal, Depends(require_admin)],
) -> SourceTypeRead:
    return await service.create_source_type(payload)


@router.put("/source-types/{source_type_id}", response_model=SourceTypeRead, summary="Update a source type")
async def update_source_type(
    source_type_id: uuid.UUID,
    payload: SourceTypeUpdate,
    service: Annotated[SourceRegistryService, Depends(get_source_registry_service)],
    _: Annotated[Principal, Depends(require_admin)],
) -> SourceTypeRead:
    return await service.update_source_type(source_type_id, payload)


@router.delete(
    "/source-types/{source_type_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a source type",
)
async def delete_source_type(
    source_type_id: uuid.UUID,
    service: Annotated[SourceRegistryService, Depends(get_source_registry_service)],
    _: Annotated[Principal, Depends(require_admin)],
) -> Response:
    await service.delete_source_type(source_type_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/source-types/defaults",
    response_model=list[SourceTypeRead],
    summary="Ensure default supported source types exist",
)
async def ensure_default_source_types(
    service: Annotated[SourceRegistryService, Depends(get_source_registry_service)],
    _: Annotated[Principal, Depends(require_admin)],
) -> list[SourceTypeRead]:
    return await service.ensure_default_source_types()


@router.get("/source-groups", response_model=list[SourceGroupRead], summary="List source groups")
async def list_source_groups(
    service: Annotated[SourceRegistryService, Depends(get_source_registry_service)],
) -> list[SourceGroupRead]:
    return await service.list_source_groups()


@router.post(
    "/source-groups",
    response_model=SourceGroupRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a source group",
)
async def create_source_group(
    payload: SourceGroupCreate,
    service: Annotated[SourceRegistryService, Depends(get_source_registry_service)],
    _: Annotated[Principal, Depends(require_admin)],
) -> SourceGroupRead:
    return await service.create_source_group(payload)


@router.put("/source-groups/{source_group_id}", response_model=SourceGroupRead, summary="Update a source group")
async def update_source_group(
    source_group_id: uuid.UUID,
    payload: SourceGroupUpdate,
    service: Annotated[SourceRegistryService, Depends(get_source_registry_service)],
    _: Annotated[Principal, Depends(require_admin)],
) -> SourceGroupRead:
    return await service.update_source_group(source_group_id, payload)


@router.delete(
    "/source-groups/{source_group_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a source group",
)
async def delete_source_group(
    source_group_id: uuid.UUID,
    service: Annotated[SourceRegistryService, Depends(get_source_registry_service)],
    _: Annotated[Principal, Depends(require_admin)],
) -> Response:
    await service.delete_source_group(source_group_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

