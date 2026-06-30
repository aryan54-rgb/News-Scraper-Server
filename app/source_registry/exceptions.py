"""Domain exceptions for source registry workflows."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from fastapi import Request, status
from fastapi.responses import JSONResponse


@dataclass(slots=True)
class SourceRegistryError(Exception):
    """Base exception carrying an API-safe validation payload."""

    message: str
    code: str = "source_registry_error"
    details: dict[str, Any] = field(default_factory=dict)


class SourceNotFoundError(SourceRegistryError):
    def __init__(self, source_id: object) -> None:
        super().__init__("Source not found", "source_not_found", {"source_id": str(source_id)})


class SourceTypeNotFoundError(SourceRegistryError):
    def __init__(self, source_type: object) -> None:
        super().__init__("Source type not found", "source_type_not_found", {"source_type": str(source_type)})


class SourceGroupNotFoundError(SourceRegistryError):
    def __init__(self, source_group_id: object) -> None:
        super().__init__(
            "Source group not found",
            "source_group_not_found",
            {"source_group_id": str(source_group_id)},
        )


class DuplicateSourceError(SourceRegistryError):
    def __init__(self, field: str, value: str) -> None:
        super().__init__(
            "A source with this value already exists",
            "duplicate_source",
            {"field": field, "value": value},
        )


class InvalidSourceConfigurationError(SourceRegistryError):
    def __init__(self, details: dict[str, Any]) -> None:
        super().__init__("Invalid source configuration", "invalid_source_configuration", details)


async def source_registry_exception_handler(
    request: Request,
    exc: SourceRegistryError,
) -> JSONResponse:
    """Translate domain exceptions into consistent API responses."""
    status_code = status.HTTP_400_BAD_REQUEST
    if exc.code.endswith("_not_found"):
        status_code = status.HTTP_404_NOT_FOUND
    elif exc.code.startswith("duplicate_"):
        status_code = status.HTTP_409_CONFLICT
    return JSONResponse(
        status_code=status_code,
        content={
            "detail": exc.message,
            "code": exc.code,
            "details": exc.details,
            "request_id": getattr(request.state, "request_id", None),
        },
    )
