"""Async RSS/Atom/RDF collector."""

from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urldefrag, urljoin, urlsplit, urlunsplit
from xml.etree import ElementTree

import httpx

from app.collectors.base import Collector
from app.collectors.exceptions import (
    CollectorError,
    CollectorHTTPStatusError,
    SourceValidationError,
)
from app.collectors.models import Attachment, CollectorHealth, CollectorHealthStatus, RawDocument
from app.core.logging import get_logger

logger = get_logger(__name__)

RSS_NAMESPACES = {
    "atom": "http://www.w3.org/2005/Atom",
    "content": "http://purl.org/rss/1.0/modules/content/",
    "dc": "http://purl.org/dc/elements/1.1/",
    "media": "http://search.yahoo.com/mrss/",
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "rss1": "http://purl.org/rss/1.0/",
}


@dataclass(frozen=True)
class RSSFeedEntry:
    guid: str | None
    title: str | None
    link: str
    canonical_url: str
    summary: str | None = None
    content: str | None = None
    author: str | None = None
    categories: list[str] = field(default_factory=list)
    published_at: datetime | None = None
    updated_at: datetime | None = None
    attachments: list[Attachment] = field(default_factory=list)
    raw_metadata: dict[str, Any] = field(default_factory=dict)
    fingerprints: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class RSSFeed:
    title: str | None
    description: str | None
    language: str | None
    url: str
    entries: list[RSSFeedEntry]
    raw_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RSSCollectedFeed:
    source_url: str
    final_url: str
    fetched_at: datetime
    http_status: int | None
    content_type: str | None
    response_headers: dict[str, str]
    request_headers: dict[str, str]
    content: bytes
    bytes_downloaded: int
    fetch_duration_ms: int
    not_modified: bool = False
    cache_fresh: bool = False


class RSSCollector(Collector, collector_key="rss"):
    """Collect RSS, Atom, and RDF feed entries as normalized raw documents."""

    default_user_agent = "KumbhMonitor RSSCollector/1.0"
    default_accept = (
        "application/rss+xml, application/atom+xml, application/xml, "
        "text/xml;q=0.9, */*;q=0.8"
    )

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    async def validate_source(self, source: Any) -> None:
        source_url = self._source_url(source)
        parsed = urlsplit(source_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise SourceValidationError(
                "RSS sources require an absolute HTTP(S) URL",
                details={"url": source_url},
            )

    async def collect(self, source: Any) -> RSSCollectedFeed:
        source_url = self._source_url(source)
        fetched_at = datetime.now(UTC)
        if self._cache_is_fresh(source, fetched_at):
            logger.info("rss_feed_cache_fresh", source_id=str(self._source_id(source)), url=source_url)
            return RSSCollectedFeed(
                source_url=source_url,
                final_url=source_url,
                fetched_at=fetched_at,
                http_status=304,
                content_type=None,
                response_headers={},
                request_headers={},
                content=b"",
                bytes_downloaded=0,
                fetch_duration_ms=0,
                not_modified=True,
                cache_fresh=True,
            )

        request_headers = self._request_headers(source)
        started = time.perf_counter()
        try:
            if self._client is not None:
                response = await self._client.get(source_url, headers=request_headers)
            else:
                async with self._new_client(source) as client:
                    response = await client.get(source_url, headers=request_headers)
        except httpx.TooManyRedirects as exc:
            raise CollectorError(
                "RSS feed redirect loop detected",
                code="rss_redirect_loop",
                retryable=False,
                details={"url": source_url},
            ) from exc
        except httpx.TimeoutException as exc:
            raise CollectorError(
                "RSS feed request timed out",
                code="rss_timeout",
                retryable=True,
                details={"url": source_url},
            ) from exc
        except httpx.HTTPError as exc:
            raise CollectorError(
                "RSS feed request failed",
                code="rss_http_error",
                retryable=True,
                details={"url": source_url, "error": str(exc)},
            ) from exc

        duration_ms = int((time.perf_counter() - started) * 1000)
        body = response.content
        logger.info(
            "rss_feed_fetched",
            source_id=str(self._source_id(source)),
            url=source_url,
            final_url=str(response.url),
            duration_ms=duration_ms,
            http_status=response.status_code,
            bytes_downloaded=len(body),
        )

        if response.status_code == 304:
            return RSSCollectedFeed(
                source_url=source_url,
                final_url=str(response.url),
                fetched_at=fetched_at,
                http_status=response.status_code,
                content_type=response.headers.get("content-type"),
                response_headers=dict(response.headers),
                request_headers=request_headers,
                content=b"",
                bytes_downloaded=0,
                fetch_duration_ms=duration_ms,
                not_modified=True,
            )

        if response.status_code >= 400:
            raise CollectorHTTPStatusError(
                response.status_code,
                retryable=response.status_code in {408, 429} or response.status_code >= 500,
            )

        return RSSCollectedFeed(
            source_url=source_url,
            final_url=str(response.url),
            fetched_at=fetched_at,
            http_status=response.status_code,
            content_type=response.headers.get("content-type"),
            response_headers=dict(response.headers),
            request_headers=request_headers,
            content=body,
            bytes_downloaded=len(body),
            fetch_duration_ms=duration_ms,
        )

    async def normalize(self, source: Any, collected: RSSCollectedFeed) -> list[RawDocument]:
        if collected.not_modified:
            logger.info(
                "rss_feed_unchanged",
                source_id=str(self._source_id(source)),
                url=collected.source_url,
                http_status=collected.http_status,
                cache_fresh=collected.cache_fresh,
            )
            return []

        started = time.perf_counter()
        feed = parse_rss_feed(collected.content, collected.final_url)
        parse_duration_ms = int((time.perf_counter() - started) * 1000)
        documents = [
            self._to_raw_document(source, collected, feed, entry)
            for entry in deduplicate_entries(feed.entries)
        ]
        logger.info(
            "rss_feed_parsed",
            source_id=str(self._source_id(source)),
            url=collected.source_url,
            feed_url=feed.url,
            entry_count=len(feed.entries),
            items_returned=len(documents),
            parse_duration_ms=parse_duration_ms,
        )
        return documents

    async def health_check(self, source: Any) -> CollectorHealth:
        try:
            await self.validate_source(source)
            collected = await self.collect(source)
        except CollectorError as exc:
            return CollectorHealth(
                status=CollectorHealthStatus.FAILING if not exc.retryable else CollectorHealthStatus.DEGRADED,
                message=exc.message,
                metadata=exc.report(),
            )
        return CollectorHealth(
            status=CollectorHealthStatus.HEALTHY,
            message="RSS feed reachable",
            metadata={
                "http_status": collected.http_status,
                "final_url": collected.final_url,
                "bytes_downloaded": collected.bytes_downloaded,
            },
        )

    def _to_raw_document(
        self,
        source: Any,
        collected: RSSCollectedFeed,
        feed: RSSFeed,
        entry: RSSFeedEntry,
    ) -> RawDocument:
        content = entry.content or entry.summary or entry.title
        return RawDocument(
            source_id=self._source_id(source),
            original_url=entry.link,
            canonical_url=entry.canonical_url,
            title=entry.title,
            author=entry.author,
            publication_date=entry.published_at,
            raw_content=content,
            metadata={
                "collector": "rss",
                "feed": {
                    "title": feed.title,
                    "description": feed.description,
                    "language": feed.language,
                    "url": feed.url,
                    "metadata": feed.raw_metadata,
                },
                "entry": entry.raw_metadata,
                "summary": entry.summary,
                "updated_at": entry.updated_at.isoformat() if entry.updated_at else None,
                "categories": entry.categories,
                "fingerprints": entry.fingerprints,
                "http": self._http_metadata(collected),
            },
            attachments=entry.attachments,
            fetch_timestamp=collected.fetched_at,
            http_status=collected.http_status,
            content_type=collected.content_type,
        )

    def _new_client(self, source: Any) -> httpx.AsyncClient:
        collector_config = self._collector_config(source)
        timeout = float(collector_config.get("request_timeout_seconds", 20.0))
        max_redirects = int(collector_config.get("max_redirects", 10))
        return httpx.AsyncClient(
            follow_redirects=True,
            max_redirects=max_redirects,
            timeout=httpx.Timeout(timeout),
            headers={"User-Agent": self.default_user_agent, "Accept": self.default_accept},
        )

    def _request_headers(self, source: Any) -> dict[str, str]:
        headers: dict[str, str] = {
            "User-Agent": self.default_user_agent,
            "Accept": self.default_accept,
            "Accept-Encoding": "gzip, deflate, br",
        }
        raw_metadata = self._raw_metadata(source)
        for header in raw_metadata.get("headers", []) or []:
            if isinstance(header, dict) and header.get("name") and header.get("value"):
                headers[str(header["name"])] = str(header["value"])

        collector_config = self._collector_config(source)
        http_state = (
            collector_config.get("http", {})
            if isinstance(collector_config.get("http"), dict)
            else {}
        )
        etag = collector_config.get("etag") or http_state.get("etag")
        last_modified = collector_config.get("last_modified") or http_state.get("last_modified")
        if etag:
            headers["If-None-Match"] = str(etag)
        if last_modified:
            headers["If-Modified-Since"] = str(last_modified)
        return headers

    def _cache_is_fresh(self, source: Any, now: datetime) -> bool:
        collector_config = self._collector_config(source)
        expires_at = collector_config.get("cache_expires_at")
        if not expires_at:
            return False
        parsed = parse_datetime(str(expires_at))
        return parsed is not None and parsed > now

    def _http_metadata(self, collected: RSSCollectedFeed) -> dict[str, Any]:
        headers = collected.response_headers
        return {
            "status": collected.http_status,
            "content_type": collected.content_type,
            "final_url": collected.final_url,
            "etag": headers.get("etag"),
            "last_modified": headers.get("last-modified"),
            "cache_control": headers.get("cache-control"),
            "expires": headers.get("expires"),
            "bytes_downloaded": collected.bytes_downloaded,
            "fetch_duration_ms": collected.fetch_duration_ms,
            "request_headers": {
                key: value
                for key, value in collected.request_headers.items()
                if key.lower() in {"if-none-match", "if-modified-since"}
            },
        }

    @staticmethod
    def _source_url(source: Any) -> str:
        url = source.get("url") if isinstance(source, dict) else getattr(source, "url", None)
        if not url:
            raise SourceValidationError("RSS source is missing a URL")
        return str(url)

    @staticmethod
    def _source_id(source: Any) -> uuid.UUID:
        source_id = source.get("id") if isinstance(source, dict) else getattr(source, "id", None)
        return source_id if isinstance(source_id, uuid.UUID) else uuid.UUID(str(source_id))

    @staticmethod
    def _raw_metadata(source: Any) -> dict[str, Any]:
        metadata = (
            source.get("metadata", {})
            if isinstance(source, dict)
            else getattr(source, "metadata_", {})
        )
        return dict(metadata or {})

    def _collector_config(self, source: Any) -> dict[str, Any]:
        collector_config = self._raw_metadata(source).get("collector", {})
        return dict(collector_config or {}) if isinstance(collector_config, dict) else {}


def parse_rss_feed(content: bytes, feed_url: str) -> RSSFeed:
    if not content.strip():
        raise CollectorError("RSS feed is empty", code="rss_empty_feed", retryable=False)
    try:
        root = ElementTree.fromstring(content)
    except ElementTree.ParseError as exc:
        raise CollectorError(
            "RSS feed XML is invalid",
            code="rss_invalid_xml",
            retryable=False,
            details={"error": str(exc), "feed_url": feed_url},
        ) from exc

    root_name = _local_name(root.tag)
    if root_name == "rss":
        return _parse_rss2(root, feed_url)
    if root_name == "feed":
        return _parse_atom(root, feed_url)
    if root_name == "RDF":
        return _parse_rdf(root, feed_url)
    raise CollectorError(
        "Unsupported RSS feed format",
        code="rss_unsupported_format",
        retryable=False,
        details={"root": root.tag, "feed_url": feed_url},
    )


def deduplicate_entries(entries: list[RSSFeedEntry]) -> list[RSSFeedEntry]:
    seen: set[str] = set()
    unique_entries: list[RSSFeedEntry] = []
    for entry in entries:
        key = entry.fingerprints.get("guid") or entry.fingerprints.get("canonical_url")
        key = key or entry.fingerprints.get("title") or entry.fingerprints.get("content")
        if key in seen:
            continue
        seen.add(key)
        unique_entries.append(entry)
    return unique_entries


def _parse_rss2(root: ElementTree.Element, feed_url: str) -> RSSFeed:
    channel = root.find("channel")
    if channel is None:
        raise CollectorError("RSS feed is missing a channel", code="rss_invalid_feed", retryable=False)
    base_url = _first_text(channel, "link") or feed_url
    entries = [_entry_from_rss_item(item, base_url) for item in channel.findall("item")]
    return RSSFeed(
        title=_first_text(channel, "title"),
        description=_first_text(channel, "description"),
        language=_first_text(channel, "language"),
        url=base_url,
        entries=entries,
        raw_metadata={"format": "rss2"},
    )


def _parse_atom(root: ElementTree.Element, feed_url: str) -> RSSFeed:
    base_url = _atom_link(root, feed_url) or feed_url
    entries = [_entry_from_atom(entry, base_url) for entry in _children(root, "entry")]
    return RSSFeed(
        title=_child_text(root, "title"),
        description=_child_text(root, "subtitle"),
        language=root.attrib.get("{http://www.w3.org/XML/1998/namespace}lang"),
        url=base_url,
        entries=entries,
        raw_metadata={"format": "atom", "id": _child_text(root, "id")},
    )


def _parse_rdf(root: ElementTree.Element, feed_url: str) -> RSSFeed:
    channel = _first_child(root, "channel")
    base_url = _child_text(channel, "link") if channel is not None else feed_url
    base_url = base_url or feed_url
    entries = [_entry_from_rdf_item(item, base_url) for item in _children(root, "item")]
    return RSSFeed(
        title=_child_text(channel, "title") if channel is not None else None,
        description=_child_text(channel, "description") if channel is not None else None,
        language=_child_text(channel, "language") if channel is not None else None,
        url=base_url,
        entries=entries,
        raw_metadata={"format": "rdf"},
    )


def _entry_from_rss_item(item: ElementTree.Element, base_url: str) -> RSSFeedEntry:
    title = _first_text(item, "title")
    link = _absolute_url(_first_text(item, "link") or _first_text(item, "guid") or "", base_url)
    guid = _first_text(item, "guid")
    summary = _first_text(item, "description")
    content = _first_text(item, "encoded")
    author = _first_text(item, "author") or _first_text(item, "creator")
    categories = [_text(child) for child in _children(item, "category") if _text(child)]
    published = parse_datetime(_first_text(item, "pubDate") or _first_text(item, "date"))
    updated = parse_datetime(_first_text(item, "updated"))
    attachments = _rss_attachments(item, base_url)
    return _finalize_entry(
        guid=guid,
        title=title,
        link=link,
        summary=summary,
        content=content,
        author=author,
        categories=categories,
        published=published,
        updated=updated,
        attachments=attachments,
        raw_metadata={"source_format": "rss2", "guid_is_permalink": item.findtext("guid") == link},
    )


def _entry_from_atom(entry: ElementTree.Element, base_url: str) -> RSSFeedEntry:
    link = _atom_link(entry, base_url) or _child_text(entry, "id") or ""
    link = _absolute_url(link, base_url)
    author = None
    author_element = _first_child(entry, "author")
    if author_element is not None:
        author = _child_text(author_element, "name") or _text(author_element)
    categories = [
        child.attrib.get("term") or child.attrib.get("label") or ""
        for child in _children(entry, "category")
    ]
    categories = [category for category in categories if category]
    return _finalize_entry(
        guid=_child_text(entry, "id"),
        title=_child_text(entry, "title"),
        link=link,
        summary=_child_text(entry, "summary"),
        content=_child_text(entry, "content"),
        author=author,
        categories=categories,
        published=parse_datetime(_child_text(entry, "published")),
        updated=parse_datetime(_child_text(entry, "updated")),
        attachments=_atom_attachments(entry, base_url),
        raw_metadata={"source_format": "atom"},
    )


def _entry_from_rdf_item(item: ElementTree.Element, base_url: str) -> RSSFeedEntry:
    link = _absolute_url(
        _child_text(item, "link") or item.attrib.get(f"{{{RSS_NAMESPACES['rdf']}}}about") or "",
        base_url,
    )
    return _finalize_entry(
        guid=item.attrib.get(f"{{{RSS_NAMESPACES['rdf']}}}about"),
        title=_child_text(item, "title"),
        link=link,
        summary=_child_text(item, "description"),
        content=_child_text(item, "encoded"),
        author=_child_text(item, "creator"),
        categories=[_text(child) for child in _children(item, "subject") if _text(child)],
        published=parse_datetime(_child_text(item, "date")),
        updated=None,
        attachments=[],
        raw_metadata={"source_format": "rdf"},
    )


def _finalize_entry(
    *,
    guid: str | None,
    title: str | None,
    link: str,
    summary: str | None,
    content: str | None,
    author: str | None,
    categories: list[str],
    published: datetime | None,
    updated: datetime | None,
    attachments: list[Attachment],
    raw_metadata: dict[str, Any],
) -> RSSFeedEntry:
    canonical_url = canonicalize_url(link) if link else canonicalize_url(guid or "")
    body = content or summary or title or ""
    fingerprints = {
        "guid": stable_hash(guid) if guid else "",
        "canonical_url": stable_hash(canonical_url) if canonical_url else "",
        "title": stable_hash(title) if title else "",
        "content": stable_hash(body) if body else "",
    }
    fingerprints = {key: value for key, value in fingerprints.items() if value}
    if not link:
        link = canonical_url or guid or ""
    return RSSFeedEntry(
        guid=guid,
        title=title,
        link=link,
        canonical_url=canonical_url or link,
        summary=summary,
        content=content,
        author=author,
        categories=categories,
        published_at=published,
        updated_at=updated,
        attachments=attachments,
        raw_metadata={**raw_metadata, "guid": guid},
        fingerprints=fingerprints,
    )


def _rss_attachments(item: ElementTree.Element, base_url: str) -> list[Attachment]:
    attachments: list[Attachment] = []
    for enclosure in _children(item, "enclosure"):
        url = enclosure.attrib.get("url")
        if not url:
            continue
        attachments.append(
            Attachment(
                url=_absolute_url(url, base_url),
                content_type=enclosure.attrib.get("type"),
                size_bytes=_int_or_none(enclosure.attrib.get("length")),
                metadata={"source": "enclosure"},
            )
        )
    for media in _children(item, "content"):
        url = media.attrib.get("url")
        if url:
            attachments.append(
                Attachment(
                    url=_absolute_url(url, base_url),
                    content_type=media.attrib.get("type") or media.attrib.get("medium"),
                    size_bytes=_int_or_none(media.attrib.get("fileSize")),
                    metadata={"source": "media:content"},
                )
            )
    return attachments


def _atom_attachments(entry: ElementTree.Element, base_url: str) -> list[Attachment]:
    attachments: list[Attachment] = []
    for link in _children(entry, "link"):
        rel = link.attrib.get("rel", "alternate")
        href = link.attrib.get("href")
        if rel != "enclosure" or not href:
            continue
        attachments.append(
            Attachment(
                url=_absolute_url(href, base_url),
                content_type=link.attrib.get("type"),
                size_bytes=_int_or_none(link.attrib.get("length")),
                metadata={"source": "atom:link", "rel": rel},
            )
        )
    return attachments


def canonicalize_url(url: str) -> str:
    if not url:
        return ""
    defragged, _fragment = urldefrag(url.strip())
    parsed = urlsplit(defragged)
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    path = parsed.path or "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    return urlunsplit((scheme, netloc, path, parsed.query, ""))


def stable_hash(value: str | None) -> str:
    normalized = " ".join((value or "").split()).strip().lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    candidate = value.strip()
    if not candidate:
        return None
    try:
        parsed = parsedate_to_datetime(candidate)
    except (TypeError, ValueError, IndexError):
        parsed = None
    if parsed is None:
        try:
            parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _atom_link(element: ElementTree.Element, base_url: str) -> str | None:
    links = _children(element, "link")
    alternate = next((link for link in links if link.attrib.get("rel", "alternate") == "alternate"), None)
    selected = alternate or next(iter(links), None)
    if selected is None:
        return None
    href = selected.attrib.get("href")
    return _absolute_url(href, base_url) if href else None


def _absolute_url(url: str, base_url: str) -> str:
    return urljoin(base_url, url.strip())


def _first_text(element: ElementTree.Element, local_name: str) -> str | None:
    child = _first_child(element, local_name)
    return _text(child) if child is not None else None


def _child_text(element: ElementTree.Element | None, local_name: str) -> str | None:
    if element is None:
        return None
    child = _first_child(element, local_name)
    return _text(child) if child is not None else None


def _first_child(element: ElementTree.Element, local_name: str) -> ElementTree.Element | None:
    return next(iter(_children(element, local_name)), None)


def _children(element: ElementTree.Element, local_name: str) -> list[ElementTree.Element]:
    return [child for child in list(element) if _local_name(child.tag) == local_name]


def _text(element: ElementTree.Element | None) -> str | None:
    if element is None:
        return None
    value = "".join(element.itertext()).strip()
    return value or None


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _int_or_none(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None
