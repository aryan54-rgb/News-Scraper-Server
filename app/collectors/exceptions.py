"""Structured exceptions for collector framework failures."""

from __future__ import annotations

from typing import Any


class CollectorError(Exception):
    """Base collector exception with structured reporting fields."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "collector_error",
        retryable: bool = False,
        http_status: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.retryable = retryable
        self.http_status = http_status
        self.details = details or {}

    def report(self) -> dict[str, Any]:
        """Return a log/metrics-friendly failure payload."""
        return {
            "error_code": self.code,
            "error_message": self.message,
            "retryable": self.retryable,
            "http_status": self.http_status,
            "details": self.details,
        }


class CollectorRegistrationError(CollectorError):
    """Raised when collector registration is invalid."""


class CollectorNotFoundError(CollectorError):
    """Raised when no collector is registered for a key."""

    def __init__(self, collector_key: str) -> None:
        super().__init__(
            f"No collector registered for key '{collector_key}'",
            code="collector_not_found",
            retryable=False,
            details={"collector_key": collector_key},
        )


class SourceValidationError(CollectorError):
    """Raised when a source cannot be collected by the selected collector."""

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            message,
            code="source_validation_failed",
            retryable=False,
            details=details,
        )


class CollectorTimeoutError(CollectorError):
    """Raised when collection exceeds its configured timeout."""

    def __init__(self, timeout_seconds: float) -> None:
        super().__init__(
            f"Collector timed out after {timeout_seconds} seconds",
            code="collector_timeout",
            retryable=True,
            details={"timeout_seconds": timeout_seconds},
        )


class CollectorHTTPStatusError(CollectorError):
    """Raised by collectors for retryable or terminal HTTP responses."""

    def __init__(self, http_status: int, message: str | None = None, *, retryable: bool = True) -> None:
        super().__init__(
            message or f"Collector received HTTP {http_status}",
            code="collector_http_status",
            retryable=retryable,
            http_status=http_status,
        )


class CollectionFailedError(CollectorError):
    """Raised after the manager exhausts retry attempts."""

    def __init__(
        self,
        message: str,
        *,
        collector_key: str,
        attempts: int,
        cause: BaseException,
    ) -> None:
        details: dict[str, Any] = {"collector_key": collector_key, "attempts": attempts}
        if isinstance(cause, CollectorError):
            details["cause"] = cause.report()
            http_status = cause.http_status
        else:
            details["cause"] = {"error_message": str(cause), "error_type": type(cause).__name__}
            http_status = None
        super().__init__(
            message,
            code="collection_failed",
            retryable=False,
            http_status=http_status,
            details=details,
        )
