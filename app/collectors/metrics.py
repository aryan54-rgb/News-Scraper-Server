"""Metrics hooks for collector execution."""

from __future__ import annotations

from collections import defaultdict
from typing import Protocol


class CollectorMetrics(Protocol):
    """Minimal metrics sink used by CollectorManager."""

    def record_duration(self, collector_key: str, duration_ms: int, *, success: bool) -> None: ...

    def increment_success(self, collector_key: str) -> None: ...

    def increment_failure(self, collector_key: str, error_code: str) -> None: ...

    def record_retry(self, collector_key: str, retry_count: int) -> None: ...

    def record_bytes_downloaded(self, collector_key: str, bytes_downloaded: int) -> None: ...

    def record_http_status(self, collector_key: str, http_status: int) -> None: ...


class NoOpCollectorMetrics:
    """Default metrics sink for tests and local execution."""

    def record_duration(self, collector_key: str, duration_ms: int, *, success: bool) -> None:
        return None

    def increment_success(self, collector_key: str) -> None:
        return None

    def increment_failure(self, collector_key: str, error_code: str) -> None:
        return None

    def record_retry(self, collector_key: str, retry_count: int) -> None:
        return None

    def record_bytes_downloaded(self, collector_key: str, bytes_downloaded: int) -> None:
        return None

    def record_http_status(self, collector_key: str, http_status: int) -> None:
        return None


class InMemoryCollectorMetrics:
    """Simple metrics implementation useful for unit tests."""

    def __init__(self) -> None:
        self.durations: list[tuple[str, int, bool]] = []
        self.successes: dict[str, int] = defaultdict(int)
        self.failures: dict[tuple[str, str], int] = defaultdict(int)
        self.retries: dict[str, int] = defaultdict(int)
        self.bytes_downloaded: dict[str, int] = defaultdict(int)
        self.http_statuses: list[tuple[str, int]] = []

    def record_duration(self, collector_key: str, duration_ms: int, *, success: bool) -> None:
        self.durations.append((collector_key, duration_ms, success))

    def increment_success(self, collector_key: str) -> None:
        self.successes[collector_key] += 1

    def increment_failure(self, collector_key: str, error_code: str) -> None:
        self.failures[(collector_key, error_code)] += 1

    def record_retry(self, collector_key: str, retry_count: int) -> None:
        self.retries[collector_key] += retry_count

    def record_bytes_downloaded(self, collector_key: str, bytes_downloaded: int) -> None:
        self.bytes_downloaded[collector_key] += bytes_downloaded

    def record_http_status(self, collector_key: str, http_status: int) -> None:
        self.http_statuses.append((collector_key, http_status))
