"""Collector manager for dynamic execution, retries, and observability."""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from app.collectors.exceptions import (
    CollectionFailedError,
    CollectorError,
    CollectorHTTPStatusError,
    CollectorNotFoundError,
    CollectorTimeoutError,
)
from app.collectors.metrics import CollectorMetrics, NoOpCollectorMetrics
from app.collectors.models import CollectionResult, RawDocument, RetryPolicy
from app.collectors.registry import CollectorRegistry, collector_registry
from app.core.logging import get_logger
from app.source_registry.schemas import SourceMetadata

logger = get_logger(__name__)

SleepCallable = Callable[[float], Awaitable[None]]


class CollectorManager:
    """Resolve collectors by key and execute collection with operational guardrails."""

    def __init__(
        self,
        *,
        registry: CollectorRegistry = collector_registry,
        metrics: CollectorMetrics | None = None,
        default_timeout_seconds: float = 30.0,
        default_retry_policy: RetryPolicy | None = None,
        sleep: SleepCallable = asyncio.sleep,
    ) -> None:
        self.registry = registry
        self.metrics = metrics or NoOpCollectorMetrics()
        self.default_timeout_seconds = default_timeout_seconds
        self.default_retry_policy = default_retry_policy or RetryPolicy()
        self.sleep = sleep

    async def collect(self, source: Any) -> CollectionResult:
        """Collect and normalize documents from a source registry record."""
        source_id = self._source_id(source)
        collector_key = self._collector_key(source)
        collector = self.registry.create(collector_key)
        retry_policy = self._retry_policy(source)
        timeout_seconds = self._timeout_seconds(source)
        attempts = retry_policy.max_attempts
        started = time.perf_counter()
        retry_count = 0
        actual_attempts = 0
        last_error: BaseException | None = None

        logger.info(
            "collector_collection_started",
            source_id=str(source_id),
            collector_key=collector_key,
            max_attempts=attempts,
            timeout_seconds=timeout_seconds,
        )

        for attempt in range(1, attempts + 1):
            actual_attempts = attempt
            try:
                documents = await asyncio.wait_for(
                    self._run_collector(collector, source),
                    timeout=timeout_seconds,
                )
                result = self._build_result(
                    source_id=source_id,
                    collector_key=collector_key,
                    documents=documents,
                    started=started,
                    retry_count=retry_count,
                    success=True,
                )
                self._emit_success_metrics(result)
                logger.info(
                    "collector_collection_succeeded",
                    source_id=str(source_id),
                    collector_key=collector_key,
                    document_count=len(documents),
                    duration_ms=result.duration_ms,
                    retry_count=retry_count,
                    bytes_downloaded=result.bytes_downloaded,
                    http_statuses=result.http_statuses,
                )
                return result
            except TimeoutError:
                last_error = CollectorTimeoutError(timeout_seconds)
            except CollectorHTTPStatusError as exc:
                last_error = exc
                if exc.http_status not in retry_policy.retry_on_statuses:
                    break
            except CollectorError as exc:
                last_error = exc
                if not exc.retryable:
                    break
            except Exception as exc:
                last_error = exc
                break

            if attempt < attempts:
                retry_count += 1
                backoff = self._backoff_seconds(retry_policy, retry_count)
                logger.warning(
                    "collector_collection_retrying",
                    source_id=str(source_id),
                    collector_key=collector_key,
                    attempt=attempt,
                    next_attempt=attempt + 1,
                    retry_count=retry_count,
                    backoff_seconds=backoff,
                    **self._error_context(last_error),
                )
                self.metrics.record_retry(collector_key, 1)
                await self.sleep(backoff)

        failure = self._failure(
            collector_key=collector_key,
            attempts=actual_attempts,
            cause=last_error or CollectorError("Collection failed", code="collection_failed"),
        )
        duration_ms = self._duration_ms(started)
        self.metrics.record_duration(collector_key, duration_ms, success=False)
        self.metrics.increment_failure(collector_key, failure.code)
        logger.error(
            "collector_collection_failed",
            source_id=str(source_id),
            collector_key=collector_key,
            duration_ms=duration_ms,
            retry_count=retry_count,
            **failure.report(),
        )
        raise failure

    async def health_check(self, source: Any) -> Any:
        """Run only the selected collector's health check."""
        collector_key = self._collector_key(source)
        collector = self.registry.create(collector_key)
        return await asyncio.wait_for(collector.health_check(source), timeout=self._timeout_seconds(source))

    async def _run_collector(self, collector: Any, source: Any) -> list[RawDocument]:
        await collector.validate_source(source)
        collected = await collector.collect(source)
        documents = await collector.normalize(source, collected)
        return documents

    def _build_result(
        self,
        *,
        source_id: uuid.UUID,
        collector_key: str,
        documents: list[RawDocument],
        started: float,
        retry_count: int,
        success: bool,
    ) -> CollectionResult:
        return CollectionResult(
            source_id=source_id,
            collector_key=collector_key,
            documents=documents,
            duration_ms=self._duration_ms(started),
            retry_count=retry_count,
            bytes_downloaded=sum(document.size_bytes for document in documents),
            http_statuses=[
                document.http_status for document in documents if document.http_status is not None
            ],
            success=success,
        )

    def _emit_success_metrics(self, result: CollectionResult) -> None:
        self.metrics.record_duration(result.collector_key, result.duration_ms, success=True)
        self.metrics.increment_success(result.collector_key)
        self.metrics.record_bytes_downloaded(result.collector_key, result.bytes_downloaded)
        for http_status in result.http_statuses:
            self.metrics.record_http_status(result.collector_key, http_status)

    def _collector_key(self, source: Any) -> str:
        source_type = getattr(source, "source_type", None)
        collector_key = getattr(source_type, "collector_key", None)
        if collector_key is None and isinstance(source, dict):
            collector_key = source.get("collector_key")
        if collector_key is None:
            raise CollectorNotFoundError("missing")
        return str(collector_key).strip().lower()

    def _source_id(self, source: Any) -> uuid.UUID:
        source_id = getattr(source, "id", None)
        if source_id is None and isinstance(source, dict):
            source_id = source.get("id")
        if isinstance(source_id, uuid.UUID):
            return source_id
        return uuid.UUID(str(source_id))

    def _metadata(self, source: Any) -> SourceMetadata:
        raw_metadata = getattr(source, "metadata_", None)
        if raw_metadata is None and isinstance(source, dict):
            raw_metadata = source.get("metadata", {})
        return SourceMetadata.model_validate(raw_metadata or {})

    def _retry_policy(self, source: Any) -> RetryPolicy:
        metadata = self._metadata(source)
        policy = metadata.retry_policy
        max_attempts = max(1, policy.max_attempts)
        return RetryPolicy(
            max_attempts=max_attempts,
            backoff_seconds=policy.backoff_seconds,
            backoff_multiplier=policy.backoff_multiplier,
            retry_on_statuses=set(policy.retry_on_statuses),
        )

    def _timeout_seconds(self, source: Any) -> float:
        metadata = self._metadata(source)
        configured = metadata.collector.get("timeout_seconds")
        if configured is None:
            return self.default_timeout_seconds
        return float(configured)

    @staticmethod
    def _backoff_seconds(retry_policy: RetryPolicy, retry_count: int) -> float:
        return retry_policy.backoff_seconds * (
            retry_policy.backoff_multiplier ** max(0, retry_count - 1)
        )

    @staticmethod
    def _duration_ms(started: float) -> int:
        return int((time.perf_counter() - started) * 1000)

    @staticmethod
    def _failure(
        *,
        collector_key: str,
        attempts: int,
        cause: BaseException,
    ) -> CollectionFailedError:
        return CollectionFailedError(
            "Collector failed after retry policy was exhausted",
            collector_key=collector_key,
            attempts=attempts,
            cause=cause,
        )

    @staticmethod
    def _error_context(error: BaseException | None) -> dict[str, Any]:
        if isinstance(error, CollectorError):
            return error.report()
        if error is None:
            return {}
        return {"error_code": type(error).__name__, "error_message": str(error)}
