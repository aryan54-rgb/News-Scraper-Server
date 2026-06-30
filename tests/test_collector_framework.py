from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pytest

from app.collectors import (
    CollectionFailedError,
    Collector,
    CollectorHealth,
    CollectorHealthStatus,
    CollectorHTTPStatusError,
    CollectorManager,
    CollectorRegistry,
    InMemoryCollectorMetrics,
    RawDocument,
    SourceValidationError,
)


@dataclass
class SourceTypeStub:
    collector_key: str


@dataclass
class SourceStub:
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    url: str = "https://example.com/feed"
    source_type: SourceTypeStub = field(default_factory=lambda: SourceTypeStub("mock"))
    metadata_: dict[str, Any] = field(
        default_factory=lambda: {
            "retry_policy": {
                "max_attempts": 3,
                "backoff_seconds": 0,
                "backoff_multiplier": 1,
                "retry_on_statuses": [500, 503],
            },
            "collector": {"timeout_seconds": 1},
        }
    )


class SuccessfulCollector(Collector):
    async def validate_source(self, source: SourceStub) -> None:
        if not source.url:
            raise SourceValidationError("missing url")

    async def collect(self, source: SourceStub) -> list[dict[str, str]]:
        return [{"url": source.url, "title": "Collected"}]

    async def normalize(
        self,
        source: SourceStub,
        collected: list[dict[str, str]],
    ) -> list[RawDocument]:
        return [
            RawDocument(
                source_id=source.id,
                original_url=item["url"],
                canonical_url=item["url"],
                title=item["title"],
                author="Unit Test",
                publication_date=datetime(2026, 6, 30, tzinfo=UTC),
                raw_content="hello world",
                metadata={"collector": "mock"},
                attachments=[],
                fetch_timestamp=datetime(2026, 6, 30, tzinfo=UTC),
                http_status=200,
                content_type="text/html",
            )
            for item in collected
        ]

    async def health_check(self, source: SourceStub) -> CollectorHealth:
        return CollectorHealth(status=CollectorHealthStatus.HEALTHY)


class FlakyCollector(SuccessfulCollector):
    attempts = 0

    async def collect(self, source: SourceStub) -> list[dict[str, str]]:
        type(self).attempts += 1
        if type(self).attempts == 1:
            raise CollectorHTTPStatusError(503)
        return await super().collect(source)


class ValidationFailureCollector(SuccessfulCollector):
    async def validate_source(self, source: SourceStub) -> None:
        raise SourceValidationError("invalid source")


class TimeoutCollector(SuccessfulCollector):
    async def collect(self, source: SourceStub) -> list[dict[str, str]]:
        await asyncio.sleep(1)
        return []


async def no_sleep(seconds: float) -> None:
    return None


@pytest.fixture
def registry() -> CollectorRegistry:
    registry = CollectorRegistry()
    registry.register("mock", SuccessfulCollector)
    return registry


@pytest.mark.asyncio
async def test_collector_manager_returns_normalized_documents(registry: CollectorRegistry) -> None:
    metrics = InMemoryCollectorMetrics()
    source = SourceStub()
    manager = CollectorManager(registry=registry, metrics=metrics, sleep=no_sleep)

    result = await manager.collect(source)

    assert result.source_id == source.id
    assert result.collector_key == "mock"
    assert result.success is True
    assert result.retry_count == 0
    assert result.bytes_downloaded == len("hello world")
    assert result.http_statuses == [200]
    assert result.documents[0].title == "Collected"
    assert metrics.successes["mock"] == 1
    assert metrics.http_statuses == [("mock", 200)]


@pytest.mark.asyncio
async def test_registry_supports_collector_self_registration() -> None:
    registry = CollectorRegistry()

    class SelfRegisteredCollector(SuccessfulCollector, collector_key="self_registered"):
        pass

    from app.collectors.registry import collector_registry

    try:
        assert collector_registry.resolve("self_registered") is SelfRegisteredCollector
    finally:
        collector_registry.unregister("self_registered")

    registry.register("self_registered", SelfRegisteredCollector)
    manager = CollectorManager(registry=registry, sleep=no_sleep)
    source = SourceStub(source_type=SourceTypeStub("self_registered"))

    result = await manager.collect(source)

    assert result.collector_key == "self_registered"
    assert len(result.documents) == 1


@pytest.mark.asyncio
async def test_manager_retries_retryable_collector_errors() -> None:
    FlakyCollector.attempts = 0
    registry = CollectorRegistry()
    registry.register("flaky", FlakyCollector)
    metrics = InMemoryCollectorMetrics()
    source = SourceStub(source_type=SourceTypeStub("flaky"))
    manager = CollectorManager(registry=registry, metrics=metrics, sleep=no_sleep)

    result = await manager.collect(source)

    assert result.retry_count == 1
    assert FlakyCollector.attempts == 2
    assert metrics.retries["flaky"] == 1


@pytest.mark.asyncio
async def test_manager_wraps_non_retryable_validation_failure() -> None:
    registry = CollectorRegistry()
    registry.register("invalid", ValidationFailureCollector)
    source = SourceStub(source_type=SourceTypeStub("invalid"))
    manager = CollectorManager(registry=registry, sleep=no_sleep)

    with pytest.raises(CollectionFailedError) as exc_info:
        await manager.collect(source)

    assert exc_info.value.code == "collection_failed"
    assert exc_info.value.details["attempts"] == 1
    assert exc_info.value.details["cause"]["error_code"] == "source_validation_failed"


@pytest.mark.asyncio
async def test_manager_enforces_collection_timeout() -> None:
    registry = CollectorRegistry()
    registry.register("timeout", TimeoutCollector)
    source = SourceStub(
        source_type=SourceTypeStub("timeout"),
        metadata_={
            "retry_policy": {
                "max_attempts": 1,
                "backoff_seconds": 0,
                "backoff_multiplier": 1,
                "retry_on_statuses": [500],
            },
            "collector": {"timeout_seconds": 0.01},
        },
    )
    manager = CollectorManager(registry=registry, sleep=no_sleep)

    with pytest.raises(CollectionFailedError) as exc_info:
        await manager.collect(source)

    assert exc_info.value.details["cause"]["error_code"] == "collector_timeout"


@pytest.mark.asyncio
async def test_health_check_resolves_selected_collector(registry: CollectorRegistry) -> None:
    manager = CollectorManager(registry=registry, sleep=no_sleep)

    health = await manager.health_check(SourceStub())

    assert health.status == CollectorHealthStatus.HEALTHY
