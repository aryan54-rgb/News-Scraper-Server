from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest

from app.collectors import RSSCollector, collector_registry
from app.collectors.exceptions import CollectorError, CollectorHTTPStatusError, SourceValidationError


@dataclass
class SourceTypeStub:
    collector_key: str = "rss"


@dataclass
class RSSSourceStub:
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    url: str = "https://example.com/feed.xml"
    source_type: SourceTypeStub = field(default_factory=SourceTypeStub)
    metadata_: dict[str, Any] = field(default_factory=dict)


RSS_FEED = b"""<?xml version="1.0" encoding="ISO-8859-1"?>
<rss version="2.0"
     xmlns:content="http://purl.org/rss/1.0/modules/content/"
     xmlns:media="http://search.yahoo.com/mrss/">
  <channel>
    <title>Example Feed</title>
    <description>Feed description</description>
    <language>en</language>
    <link>https://example.com/news/</link>
    <item>
      <guid>article-1</guid>
      <title>First Article</title>
      <link>/news/first#comments</link>
      <description>Short summary</description>
      <content:encoded><![CDATA[<p>Full content</p>]]></content:encoded>
      <author>editor@example.com</author>
      <category>traffic</category>
      <pubDate>Tue, 30 Jun 2026 10:15:00 GMT</pubDate>
      <enclosure url="/media/photo.jpg" type="image/jpeg" length="1234" />
      <media:content url="/media/video.mp4" type="video/mp4" fileSize="9876" />
    </item>
    <item>
      <guid>article-1</guid>
      <title>First Article Duplicate</title>
      <link>/news/first</link>
    </item>
    <item>
      <title>Missing GUID</title>
      <link>relative-second</link>
      <description>Fallback content</description>
      <pubDate>not a date</pubDate>
    </item>
  </channel>
</rss>
"""


ATOM_FEED = b"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xml:lang="en">
  <title>Atom Feed</title>
  <subtitle>Atom subtitle</subtitle>
  <link href="https://example.org/feed" />
  <entry>
    <id>tag:example.org,2026:1</id>
    <title>Atom Article</title>
    <link href="/atom/article" />
    <summary>Atom summary</summary>
    <content>Atom content</content>
    <author><name>Atom Author</name></author>
    <category term="official" />
    <published>2026-06-30T11:00:00Z</published>
    <updated>2026-06-30T12:00:00Z</updated>
    <link rel="enclosure" href="/audio.mp3" type="audio/mpeg" length="42" />
  </entry>
</feed>
"""


RDF_FEED = b"""<?xml version="1.0"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns="http://purl.org/rss/1.0/"
         xmlns:dc="http://purl.org/dc/elements/1.1/">
  <channel rdf:about="https://example.net/feed">
    <title>RDF Feed</title>
    <link>https://example.net/</link>
    <description>RDF description</description>
  </channel>
  <item rdf:about="https://example.net/items/1">
    <title>RDF Article</title>
    <link>/items/1</link>
    <description>RDF summary</description>
    <dc:creator>RDF Author</dc:creator>
    <dc:date>2026-06-30T09:00:00Z</dc:date>
  </item>
</rdf:RDF>
"""


@pytest.mark.asyncio
async def test_rss_collector_registers_itself() -> None:
    assert collector_registry.resolve("rss") is RSSCollector


@pytest.mark.asyncio
async def test_collects_and_normalizes_rss_items_with_metadata() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                headers={
                    "content-type": "application/rss+xml; charset=ISO-8859-1",
                    "etag": '"abc"',
                    "last-modified": "Tue, 30 Jun 2026 10:00:00 GMT",
                    "cache-control": "max-age=300",
                },
                content=RSS_FEED,
                request=request,
            )
        ),
        follow_redirects=True,
    ) as client:
        source = RSSSourceStub()
        collector = RSSCollector(client=client)

        collected = await collector.collect(source)
        documents = await collector.normalize(source, collected)

    assert len(documents) == 2
    first = documents[0]
    assert first.source_id == source.id
    assert first.original_url == "https://example.com/news/first#comments"
    assert first.canonical_url == "https://example.com/news/first"
    assert first.title == "First Article"
    assert first.author == "editor@example.com"
    assert first.raw_content == "<p>Full content</p>"
    assert first.publication_date is not None
    assert first.metadata["feed"]["title"] == "Example Feed"
    assert first.metadata["categories"] == ["traffic"]
    assert first.metadata["fingerprints"]["guid"]
    assert first.metadata["fingerprints"]["canonical_url"]
    assert first.metadata["http"]["etag"] == '"abc"'
    assert first.attachments[0].url == "https://example.com/media/photo.jpg"
    assert first.attachments[1].content_type == "video/mp4"

    second = documents[1]
    assert second.title == "Missing GUID"
    assert second.canonical_url == "https://example.com/news/relative-second"
    assert second.publication_date is None
    assert second.metadata["fingerprints"]["title"]


@pytest.mark.asyncio
async def test_atom_feed_and_redirects_are_supported() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == "https://example.org/feed":
            return httpx.Response(301, headers={"location": "https://cdn.example.org/feed"}, request=request)
        return httpx.Response(200, content=ATOM_FEED, request=request)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        follow_redirects=True,
    ) as client:
        source = RSSSourceStub(url="https://example.org/feed")
        collector = RSSCollector(client=client)

        collected = await collector.collect(source)
        documents = await collector.normalize(source, collected)

    assert collected.final_url == "https://cdn.example.org/feed"
    assert len(documents) == 1
    assert documents[0].title == "Atom Article"
    assert documents[0].author == "Atom Author"
    assert documents[0].metadata["feed"]["language"] == "en"
    assert documents[0].metadata["updated_at"] == "2026-06-30T12:00:00+00:00"
    assert documents[0].attachments[0].url == "https://example.org/audio.mp3"


@pytest.mark.asyncio
async def test_rdf_feed_is_supported_where_possible() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=RDF_FEED, request=request)
        ),
    ) as client:
        source = RSSSourceStub(url="https://example.net/feed")
        collector = RSSCollector(client=client)

        collected = await collector.collect(source)
        documents = await collector.normalize(source, collected)

    assert len(documents) == 1
    assert documents[0].title == "RDF Article"
    assert documents[0].canonical_url == "https://example.net/items/1"
    assert documents[0].author == "RDF Author"


@pytest.mark.asyncio
async def test_conditional_get_headers_and_304_return_no_documents() -> None:
    captured_headers: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_headers["if-none-match"] = request.headers["if-none-match"]
        captured_headers["if-modified-since"] = request.headers["if-modified-since"]
        return httpx.Response(304, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        source = RSSSourceStub(
            metadata_={
                "collector": {
                    "etag": '"previous"',
                    "last_modified": "Tue, 30 Jun 2026 09:00:00 GMT",
                }
            }
        )
        collector = RSSCollector(client=client)

        collected = await collector.collect(source)
        documents = await collector.normalize(source, collected)

    assert captured_headers == {
        "if-none-match": '"previous"',
        "if-modified-since": "Tue, 30 Jun 2026 09:00:00 GMT",
    }
    assert collected.not_modified is True
    assert documents == []


@pytest.mark.asyncio
async def test_invalid_xml_empty_feed_and_http_failures_are_structured() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=b"<rss>", request=request)
        )
    ) as client:
        source = RSSSourceStub()
        collector = RSSCollector(client=client)
        collected = await collector.collect(source)
        with pytest.raises(CollectorError) as exc_info:
            await collector.normalize(source, collected)
        assert exc_info.value.code == "rss_invalid_xml"

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=b"   ", request=request)
        )
    ) as client:
        source = RSSSourceStub()
        collector = RSSCollector(client=client)
        collected = await collector.collect(source)
        with pytest.raises(CollectorError) as exc_info:
            await collector.normalize(source, collected)
        assert exc_info.value.code == "rss_empty_feed"

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(503, request=request))
    ) as client:
        collector = RSSCollector(client=client)
        with pytest.raises(CollectorHTTPStatusError) as exc_info:
            await collector.collect(RSSSourceStub())
        assert exc_info.value.http_status == 503
        assert exc_info.value.retryable is True


@pytest.mark.asyncio
async def test_source_validation_rejects_non_http_urls() -> None:
    collector = RSSCollector()

    with pytest.raises(SourceValidationError):
        await collector.validate_source(RSSSourceStub(url="ftp://example.com/feed"))
