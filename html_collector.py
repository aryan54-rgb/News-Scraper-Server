"""
Generic HTML / News Site Collector
===================================

A fetch-only collector built on top of a small "Collector Framework". It
downloads raw bytes + response metadata for a list of URLs. It does NOT
decode HTML, parse it, extract articles, fingerprint/dedupe, or run any
AI/NLP — those are downstream concerns.

Pipeline shape
--------------
    Collector  -->  RawFetchResult  -->  Normalizer  -->  RawDocument

`RawFetchResult` is the literal output of one HTTP fetch (bytes + raw
transport metadata). `Normalizer` is a separate, reusable component that
turns a `RawFetchResult` into a `RawDocument` (normalized URL, parsed
header metadata, etc). Every future collector (RSS, government sites,
PDFs, ...) can fetch however it wants and reuse the same `Normalizer`,
so normalization logic isn't duplicated per collector.

Decoding bytes -> text is explicitly NOT done here. `RawDocument.content`
is raw bytes; `RawDocument.declared_encoding` is whatever the server
claimed (from the Content-Type header), and it's up to the extraction
module to do real charset sniffing (e.g. via cchardet/charset-normalizer)
before decoding. This also means non-text content (PDFs, images) can
flow through the same abstraction without special-casing.

Features
--------
- Async HTTP via aiohttp.
- Global AND per-host concurrency limits.
- robots.txt awareness, configurable, cached per host (TTL-based; swap
  in a Redis-backed cache later by implementing the same interface).
- User-Agent rotation (round-robin or random).
- Redirect handling with full redirect-chain capture and a max-hop limit.
- Conditional GET (ETag / Last-Modified), 304-aware.
- Content-Type allow/deny filtering, checked from headers BEFORE the
  body is downloaded, so large disallowed payloads (video, zip, images)
  are never pulled over the wire.
- URL normalization (trailing slash, tracking-param stripping) handled
  by the Normalizer, not the fetcher.
- Metrics counters suitable for a dashboard.
- Returns `RawDocument` objects. No parsing, no extraction, no AI.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
import urllib.robotparser as robotparser
from dataclasses import dataclass, field
from typing import Iterable, Optional, Protocol
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

import aiohttp

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# Collector Framework primitives
# --------------------------------------------------------------------------

@dataclass
class RawFetchResult:
    """The literal, untouched output of one HTTP fetch attempt."""

    requested_url: str
    final_url: str                 # after redirects
    status: int
    content: Optional[bytes]       # raw response body; None on error/304/filtered
    headers: dict                  # response headers, lower-cased keys
    redirect_chain: list           # intermediate URLs, in order
    fetched_at: float
    elapsed_ms: float
    user_agent: str
    http_version: Optional[str] = None
    remote_ip: Optional[str] = None
    not_modified: bool = False
    filtered_reason: Optional[str] = None   # e.g. "content_type_not_allowed", "blocked_by_robots_txt"
    error: Optional[str] = None


@dataclass
class RawDocument:
    """Normalized fetch result. content is RAW BYTES — no decoding here."""

    url: str                       # normalized final URL
    requested_url: str
    status: int
    content: Optional[bytes]
    declared_encoding: Optional[str]   # from Content-Type header, if present; NOT used to decode
    content_type: Optional[str]
    content_length: Optional[int]
    headers: dict
    fetched_at: float
    redirect_chain: list
    redirect_count: int
    elapsed_ms: float
    user_agent: str

    # HTTP / transport metadata
    http_version: Optional[str] = None
    remote_ip: Optional[str] = None
    transfer_encoding: Optional[str] = None
    server: Optional[str] = None
    cache_control: Optional[str] = None
    expires: Optional[str] = None
    age: Optional[str] = None

    not_modified: bool = False
    filtered_reason: Optional[str] = None
    error: Optional[str] = None


class BaseCollector(Protocol):
    """Minimal Collector Framework contract."""

    async def collect(self, urls: Iterable[str]) -> list[RawDocument]:
        ...


# --------------------------------------------------------------------------
# Normalizer (separate, reusable component — not collector-specific)
# --------------------------------------------------------------------------

# Common tracking params stripped during normalization.
_TRACKING_PARAM_PREFIXES = ("utm_",)
_TRACKING_PARAMS = {
    "fbclid", "gclid", "msclkid", "mc_cid", "mc_eid", "igshid", "ref", "ref_src",
}


def normalize_url(url: str) -> str:
    """Strip default ports, trailing slash on bare paths, and tracking params."""
    parts = urlsplit(url)

    path = parts.path
    if path == "/":
        path = ""
    elif path.endswith("/") and len(path) > 1:
        path = path.rstrip("/")

    query_pairs = [
        (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k.lower() not in _TRACKING_PARAMS
        and not any(k.lower().startswith(p) for p in _TRACKING_PARAM_PREFIXES)
    ]
    query_pairs.sort()
    query = urlencode(query_pairs)

    netloc = parts.netloc
    if netloc.endswith(":80") and parts.scheme == "http":
        netloc = netloc[: -len(":80")]
    elif netloc.endswith(":443") and parts.scheme == "https":
        netloc = netloc[: -len(":443")]

    return urlunsplit((parts.scheme, netloc, path, query, ""))


class Normalizer:
    """Converts RawFetchResult -> RawDocument. Shared across all collectors."""

    def normalize(self, fetch: RawFetchResult) -> RawDocument:
        headers = fetch.headers or {}
        content_type_header = headers.get("content-type")
        declared_encoding = None
        content_type = content_type_header
        if content_type_header and "charset=" in content_type_header:
            content_type, _, charset_part = content_type_header.partition(";")
            content_type = content_type.strip()
            declared_encoding = charset_part.split("charset=", 1)[-1].strip().strip('"').strip("'")

        content_length = None
        if headers.get("content-length"):
            try:
                content_length = int(headers["content-length"])
            except ValueError:
                content_length = None
        elif fetch.content is not None:
            content_length = len(fetch.content)

        return RawDocument(
            url=normalize_url(fetch.final_url),
            requested_url=fetch.requested_url,
            status=fetch.status,
            content=fetch.content,
            declared_encoding=declared_encoding,
            content_type=content_type,
            content_length=content_length,
            headers=headers,
            fetched_at=fetch.fetched_at,
            redirect_chain=fetch.redirect_chain,
            redirect_count=len(fetch.redirect_chain),
            elapsed_ms=fetch.elapsed_ms,
            user_agent=fetch.user_agent,
            http_version=fetch.http_version,
            remote_ip=fetch.remote_ip,
            transfer_encoding=headers.get("transfer-encoding"),
            server=headers.get("server"),
            cache_control=headers.get("cache-control"),
            expires=headers.get("expires"),
            age=headers.get("age"),
            not_modified=fetch.not_modified,
            filtered_reason=fetch.filtered_reason,
            error=fetch.error,
        )


# --------------------------------------------------------------------------
# Conditional GET cache store (pluggable — default is in-memory)
# --------------------------------------------------------------------------

class ConditionalGetCache(Protocol):
    async def get(self, url: str) -> Optional[dict]:
        ...

    async def set(self, url: str, etag: Optional[str], last_modified: Optional[str]) -> None:
        ...


class InMemoryConditionalGetCache:
    """Default cache. Swap for a Redis-backed implementation in production
    if conditional-GET state needs to survive across process restarts /
    be shared across multiple collector workers."""

    def __init__(self) -> None:
        self._store: dict[str, dict] = {}

    async def get(self, url: str) -> Optional[dict]:
        return self._store.get(url)

    async def set(self, url: str, etag: Optional[str], last_modified: Optional[str]) -> None:
        if etag or last_modified:
            self._store[url] = {"etag": etag, "last_modified": last_modified}


# --------------------------------------------------------------------------
# Metrics
# --------------------------------------------------------------------------

@dataclass
class CollectorMetrics:
    documents_collected: int = 0
    bytes_downloaded: int = 0
    redirect_count: int = 0
    not_modified_count: int = 0
    retry_count: int = 0
    robots_blocked_count: int = 0
    content_type_filtered_count: int = 0
    error_count: int = 0
    total_latency_ms: float = 0.0

    @property
    def average_latency_ms(self) -> float:
        if self.documents_collected == 0:
            return 0.0
        return self.total_latency_ms / self.documents_collected

    def record(self, doc: RawDocument) -> None:
        self.documents_collected += 1
        self.total_latency_ms += doc.elapsed_ms
        self.redirect_count += doc.redirect_count
        if doc.not_modified:
            self.not_modified_count += 1
        if doc.filtered_reason == "content_type_not_allowed":
            self.content_type_filtered_count += 1
        if doc.filtered_reason == "blocked_by_robots_txt":
            self.robots_blocked_count += 1
        if doc.content:
            self.bytes_downloaded += len(doc.content)
        if doc.error:
            self.error_count += 1

    def as_dict(self) -> dict:
        return {
            "documents_collected": self.documents_collected,
            "bytes_downloaded": self.bytes_downloaded,
            "average_latency_ms": round(self.average_latency_ms, 2),
            "redirect_count": self.redirect_count,
            "304_count": self.not_modified_count,
            "retry_count": self.retry_count,
            "robots_blocked": self.robots_blocked_count,
            "content_type_filtered": self.content_type_filtered_count,
            "error_count": self.error_count,
        }


# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------

@dataclass
class CollectorConfig:
    user_agents: list[str] = field(default_factory=lambda: [
        "Mozilla/5.0 (compatible; GenericNewsCollector/1.0; +https://example.com/bot)"
    ])
    ua_rotation_strategy: str = "round_robin"   # "round_robin" | "random"

    respect_robots_txt: bool = True
    robots_cache_ttl_seconds: int = 3600

    max_concurrency: int = 10
    max_concurrency_per_host: int = 2
    request_timeout_seconds: float = 20.0
    max_redirects: int = 10

    enable_conditional_get: bool = True
    conditional_get_cache: Optional[ConditionalGetCache] = None

    retry_attempts: int = 2
    retry_backoff_seconds: float = 1.5

    allowed_content_types: tuple = ("text/html", "application/xhtml+xml")
    enforce_content_type_filter: bool = True

    extra_headers: dict = field(default_factory=dict)


# --------------------------------------------------------------------------
# robots.txt handling
# --------------------------------------------------------------------------

class RobotsChecker:
    """Fetches and caches robots.txt per host, configurable on/off.
    Note: in-memory only for now; swap for Redis when running multiple
    collector workers that should share robots.txt state."""

    def __init__(self, session: aiohttp.ClientSession, enabled: bool, ttl: int):
        self._session = session
        self._enabled = enabled
        self._ttl = ttl
        self._cache: dict[str, tuple[robotparser.RobotFileParser, float]] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def is_allowed(self, url: str, user_agent: str) -> bool:
        if not self._enabled:
            return True

        parts = urlsplit(url)
        origin = urlunsplit((parts.scheme, parts.netloc, "", "", ""))
        robots_url = origin + "/robots.txt"

        lock = self._locks.setdefault(origin, asyncio.Lock())
        async with lock:
            cached = self._cache.get(origin)
            now = time.monotonic()
            if cached is None or (now - cached[1]) > self._ttl:
                rp = robotparser.RobotFileParser()
                rp.set_url(robots_url)
                try:
                    async with self._session.get(
                        robots_url, timeout=aiohttp.ClientTimeout(total=10)
                    ) as resp:
                        if resp.status == 200:
                            text = (await resp.read()).decode("utf-8", errors="replace")
                            rp.parse(text.splitlines())
                        else:
                            rp.parse([])  # no robots.txt => allow all
                except Exception as exc:
                    logger.debug("robots.txt fetch failed for %s: %s", origin, exc)
                    rp.parse([])
                self._cache[origin] = (rp, now)
                cached = self._cache[origin]

        rp = cached[0]
        try:
            return rp.can_fetch(user_agent, url)
        except Exception:
            return True


# --------------------------------------------------------------------------
# User-Agent rotation
# --------------------------------------------------------------------------

class UserAgentRotator:
    def __init__(self, agents: list[str], strategy: str = "round_robin"):
        if not agents:
            raise ValueError("At least one user agent must be configured")
        self._agents = agents
        self._strategy = strategy
        self._idx = 0
        self._lock = asyncio.Lock()

    async def next(self) -> str:
        if self._strategy == "random":
            return random.choice(self._agents)
        async with self._lock:
            ua = self._agents[self._idx % len(self._agents)]
            self._idx += 1
            return ua


# --------------------------------------------------------------------------
# Per-host concurrency limiter
# --------------------------------------------------------------------------

class PerHostSemaphorePool:
    def __init__(self, limit_per_host: int):
        self._limit = limit_per_host
        self._semaphores: dict[str, asyncio.Semaphore] = {}

    def for_host(self, host: str) -> asyncio.Semaphore:
        sem = self._semaphores.get(host)
        if sem is None:
            sem = asyncio.Semaphore(self._limit)
            self._semaphores[host] = sem
        return sem


# --------------------------------------------------------------------------
# The collector
# --------------------------------------------------------------------------

class HtmlCollector:
    """Generic async collector: downloads raw bytes + metadata only."""

    def __init__(self, config: Optional[CollectorConfig] = None):
        self.config = config or CollectorConfig()
        self._ua_rotator = UserAgentRotator(
            self.config.user_agents, self.config.ua_rotation_strategy
        )
        self._cache = self.config.conditional_get_cache or InMemoryConditionalGetCache()
        self._host_pool = PerHostSemaphorePool(self.config.max_concurrency_per_host)
        self._normalizer = Normalizer()
        self.metrics = CollectorMetrics()
        self._robots: Optional[RobotsChecker] = None  # created lazily, needs a session

    async def collect(self, urls: Iterable[str]) -> list[RawDocument]:
        urls = list(urls)
        results: list[Optional[RawDocument]] = [None] * len(urls)
        global_sem = asyncio.Semaphore(self.config.max_concurrency)

        timeout = aiohttp.ClientTimeout(total=self.config.request_timeout_seconds)
        connector = aiohttp.TCPConnector(limit=self.config.max_concurrency)

        async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
            self._robots = RobotsChecker(
                session,
                enabled=self.config.respect_robots_txt,
                ttl=self.config.robots_cache_ttl_seconds,
            )

            async def worker(i: int, url: str) -> None:
                host = urlsplit(url).netloc
                host_sem = self._host_pool.for_host(host)
                async with global_sem, host_sem:
                    fetch = await self._fetch_one(session, url)
                    doc = self._normalizer.normalize(fetch)
                    self.metrics.record(doc)
                    results[i] = doc

            await asyncio.gather(*(worker(i, u) for i, u in enumerate(urls)))

        return [r for r in results if r is not None]

    async def _fetch_one(self, session: aiohttp.ClientSession, url: str) -> RawFetchResult:
        user_agent = await self._ua_rotator.next()

        allowed = await self._robots.is_allowed(url, user_agent)
        if not allowed:
            return RawFetchResult(
                requested_url=url,
                final_url=url,
                status=0,
                content=None,
                headers={},
                redirect_chain=[],
                fetched_at=time.time(),
                elapsed_ms=0.0,
                user_agent=user_agent,
                filtered_reason="blocked_by_robots_txt",
            )

        headers = dict(self.config.extra_headers)
        headers["User-Agent"] = user_agent

        if self.config.enable_conditional_get:
            cached = await self._cache.get(url)
            if cached:
                if cached.get("etag"):
                    headers["If-None-Match"] = cached["etag"]
                if cached.get("last_modified"):
                    headers["If-Modified-Since"] = cached["last_modified"]

        attempt = 0
        last_exc: Optional[Exception] = None
        while attempt <= self.config.retry_attempts:
            start = time.monotonic()
            try:
                async with session.get(
                    url,
                    headers=headers,
                    allow_redirects=True,
                    max_redirects=self.config.max_redirects,
                ) as resp:
                    elapsed_ms = (time.monotonic() - start) * 1000
                    redirect_chain = [str(h.url) for h in resp.history]
                    resp_headers = {k.lower(): v for k, v in resp.headers.items()}
                    remote_ip = None
                    try:
                        conn_info = resp.connection
                        if conn_info and conn_info.transport:
                            peer = conn_info.transport.get_extra_info("peername")
                            if peer:
                                remote_ip = peer[0]
                    except Exception:
                        pass
                    http_version = f"{resp.version.major}.{resp.version.minor}" if resp.version else None

                    if resp.status == 304:
                        return RawFetchResult(
                            requested_url=url,
                            final_url=str(resp.url),
                            status=304,
                            content=None,
                            headers=resp_headers,
                            redirect_chain=redirect_chain,
                            fetched_at=time.time(),
                            elapsed_ms=elapsed_ms,
                            user_agent=user_agent,
                            http_version=http_version,
                            remote_ip=remote_ip,
                            not_modified=True,
                        )

                    # Content-Type filtering BEFORE reading the body.
                    content_type_header = resp_headers.get("content-type", "")
                    base_content_type = content_type_header.split(";")[0].strip().lower()
                    if (
                        self.config.enforce_content_type_filter
                        and base_content_type
                        and base_content_type not in self.config.allowed_content_types
                    ):
                        resp.close()
                        return RawFetchResult(
                            requested_url=url,
                            final_url=str(resp.url),
                            status=resp.status,
                            content=None,
                            headers=resp_headers,
                            redirect_chain=redirect_chain,
                            fetched_at=time.time(),
                            elapsed_ms=elapsed_ms,
                            user_agent=user_agent,
                            http_version=http_version,
                            remote_ip=remote_ip,
                            filtered_reason="content_type_not_allowed",
                        )

                    content = await resp.read()

                    if self.config.enable_conditional_get and resp.status == 200:
                        await self._cache.set(
                            url,
                            resp_headers.get("etag"),
                            resp_headers.get("last-modified"),
                        )

                    return RawFetchResult(
                        requested_url=url,
                        final_url=str(resp.url),
                        status=resp.status,
                        content=content,
                        headers=resp_headers,
                        redirect_chain=redirect_chain,
                        fetched_at=time.time(),
                        elapsed_ms=elapsed_ms,
                        user_agent=user_agent,
                        http_version=http_version,
                        remote_ip=remote_ip,
                    )

            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                last_exc = exc
                attempt += 1
                self.metrics.retry_count += 1
                if attempt <= self.config.retry_attempts:
                    await asyncio.sleep(self.config.retry_backoff_seconds * attempt)
                    continue
                break

        return RawFetchResult(
            requested_url=url,
            final_url=url,
            status=0,
            content=None,
            headers={},
            redirect_chain=[],
            fetched_at=time.time(),
            elapsed_ms=0.0,
            user_agent=user_agent,
            error=str(last_exc) if last_exc else "unknown_error",
        )


# --------------------------------------------------------------------------
# Example
# --------------------------------------------------------------------------

async def _demo() -> None:
    logging.basicConfig(level=logging.INFO)
    config = CollectorConfig(
        user_agents=[
            "Mozilla/5.0 (compatible; NewsCollector/1.0; +https://example.com/bot)",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) NewsCollector/1.0",
        ],
        ua_rotation_strategy="round_robin",
        respect_robots_txt=True,
        max_concurrency=5,
        max_concurrency_per_host=2,
    )
    collector = HtmlCollector(config)
    docs = await collector.collect([
        "https://example.com/",
        "https://example.com/news?utm_source=test",
    ])
    for d in docs:
        print(d.url, d.status, d.not_modified, d.content_type, len(d.content or b""), d.error)
    print(collector.metrics.as_dict())


if __name__ == "__main__":
    asyncio.run(_demo())