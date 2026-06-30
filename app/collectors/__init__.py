"""Collector framework public API."""

from app.collectors.base import Collector
from app.collectors.exceptions import (
    CollectionFailedError,
    CollectorError,
    CollectorHTTPStatusError,
    CollectorNotFoundError,
    CollectorRegistrationError,
    CollectorTimeoutError,
    SourceValidationError,
)
from app.collectors.manager import CollectorManager
from app.collectors.metrics import CollectorMetrics, InMemoryCollectorMetrics, NoOpCollectorMetrics
from app.collectors.models import (
    Attachment,
    CollectionResult,
    CollectorHealth,
    CollectorHealthStatus,
    RawDocument,
    RetryPolicy,
)
from app.collectors.registry import CollectorRegistry, collector_registry

__all__ = [
    "Attachment",
    "CollectionFailedError",
    "CollectionResult",
    "Collector",
    "CollectorError",
    "CollectorHTTPStatusError",
    "CollectorHealth",
    "CollectorHealthStatus",
    "CollectorManager",
    "CollectorMetrics",
    "CollectorNotFoundError",
    "CollectorRegistrationError",
    "CollectorRegistry",
    "CollectorTimeoutError",
    "InMemoryCollectorMetrics",
    "NoOpCollectorMetrics",
    "RawDocument",
    "RetryPolicy",
    "SourceValidationError",
    "collector_registry",
]
