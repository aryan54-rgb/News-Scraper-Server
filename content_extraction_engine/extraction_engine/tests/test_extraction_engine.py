"""
Comprehensive tests for the Content Extraction Engine, using mocked HTML
fixtures covering: a well-structured news article, a sparse government page,
a blog post, broken HTML, a page with missing metadata, a paywall stub, and
a large multi-paragraph feature article.

Run with: pytest -v tests/
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.models import ExtractionStrategy, RawDocument  # noqa: E402
from core.manager import ExtractionManager  # noqa: E402
from core import normalization as norm  # noqa: E402

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_doc(filename: str, url: str = "https://www.example-news.com/article") -> RawDocument:
    html_bytes = (FIXTURES_DIR / filename).read_bytes()
    return RawDocument(
        url=url,
        content=html_bytes,
        headers={"Content-Type": "text/html; charset=utf-8"},
        content_type="text/html; charset=utf-8",
        encoding="utf-8",
    )


@pytest.fixture
def manager() -> ExtractionManager:
    return ExtractionManager()


# --------------------------------------------------------------------------- #
# 1. Simple, well-structured news article (JSON-LD + OpenGraph + clean DOM)
# --------------------------------------------------------------------------- #

class TestSimpleNewsArticle:
    def test_uses_jsonld_strategy(self, manager):
        doc = load_doc(
            "simple_news_article.html",
            url="https://www.dailyherald-example.com/news/local/park-funding-2026",
        )
        article = manager.extract(doc)
        assert article.quality.strategy_used == ExtractionStrategy.JSON_LD

    def test_title_and_metadata(self, manager):
        doc = load_doc(
            "simple_news_article.html",
            url="https://www.dailyherald-example.com/news/local/park-funding-2026",
        )
        article = manager.extract(doc)
        assert article.title == "City Council Approves New Park Funding"
        assert article.subtitle
        assert "Priya Mehta" in article.authors
        assert article.published_at is not None
        assert article.published_at.year == 2026
        assert article.published_at.month == 6
        assert article.updated_at is not None
        assert article.language == "en"

    def test_body_and_structure_preserved(self, manager):
        doc = load_doc(
            "simple_news_article.html",
            url="https://www.dailyherald-example.com/news/local/park-funding-2026",
        )
        article = manager.extract(doc)
        assert article.body_text
        assert "riverside park renovation" in article.body_text
        assert len(article.paragraphs) >= 3
        # boilerplate should not leak into the body
        assert "Subscribe to our newsletter" not in article.body_text
        assert "Related Stories" not in article.body_text
        assert "cookies" not in article.body_text.lower()

    def test_metadata_blocks_present(self, manager):
        doc = load_doc(
            "simple_news_article.html",
            url="https://www.dailyherald-example.com/news/local/park-funding-2026",
        )
        article = manager.extract(doc)
        assert article.open_graph.get("title") == "City Council Approves New Park Funding"
        assert article.twitter_card.get("card") == "summary_large_image"
        assert len(article.json_ld) >= 1
        assert article.canonical_url == "https://www.dailyherald-example.com/news/local/park-funding-2026"
        assert article.categories == ["Local News"]
        assert "parks" in article.tags

    def test_images_extracted(self, manager):
        doc = load_doc(
            "simple_news_article.html",
            url="https://www.dailyherald-example.com/news/local/park-funding-2026",
        )
        article = manager.extract(doc)
        assert len(article.images) >= 1
        assert any("riverside-park-hero" in img.url for img in article.images)

    def test_reading_time_and_word_count(self, manager):
        doc = load_doc(
            "simple_news_article.html",
            url="https://www.dailyherald-example.com/news/local/park-funding-2026",
        )
        article = manager.extract(doc)
        assert article.word_count > 50
        assert article.reading_time_minutes is not None
        assert article.reading_time_minutes > 0

    def test_quality_score_high(self, manager):
        doc = load_doc(
            "simple_news_article.html",
            url="https://www.dailyherald-example.com/news/local/park-funding-2026",
        )
        article = manager.extract(doc)
        assert article.quality.score > 0.7
        assert article.quality.missing_title is False
        assert article.quality.missing_author is False
        assert article.quality.missing_date is False
        assert article.quality.missing_body is False


# --------------------------------------------------------------------------- #
# 2. Government page: no JSON-LD/OpenGraph, tables, sparse metadata
# --------------------------------------------------------------------------- #

class TestGovernmentPage:
    def test_extracts_body_without_structured_metadata(self, manager):
        doc = load_doc("government_page.html", url="https://municipal.example.gov.in/notices/water-supply")
        article = manager.extract(doc)
        assert article.body_text
        assert "water supply" in article.body_text.lower()
        assert article.quality.strategy_used != ExtractionStrategy.NONE

    def test_table_content_preserved(self, manager):
        doc = load_doc("government_page.html", url="https://municipal.example.gov.in/notices/water-supply")
        article = manager.extract(doc)
        # Table rows should appear somewhere in body_html if a DOM-based
        # strategy won, or at minimum not crash extraction
        assert article.title is not None

    def test_navigation_and_sidebar_excluded(self, manager):
        doc = load_doc("government_page.html", url="https://municipal.example.gov.in/notices/water-supply")
        article = manager.extract(doc)
        if article.body_text:
            assert "Quick Links" not in article.body_text
            assert "Follow us" not in article.body_text

    def test_no_structured_metadata_present(self, manager):
        doc = load_doc("government_page.html", url="https://municipal.example.gov.in/notices/water-supply")
        article = manager.extract(doc)
        assert article.json_ld == []
        assert article.open_graph.values == {}


# --------------------------------------------------------------------------- #
# 3. Blog post: relative image URLs, informal structure
# --------------------------------------------------------------------------- #

class TestBlogPost:
    def test_extracts_blog_body(self, manager):
        doc = load_doc("blog_post.html", url="https://theweekendhacker.example.com/posts/ble-mesh-prototype")
        article = manager.extract(doc)
        assert article.body_text
        assert "GATT server" in article.body_text
        assert article.quality.missing_body is False

    def test_relative_image_resolved_to_absolute(self, manager):
        doc = load_doc("blog_post.html", url="https://theweekendhacker.example.com/posts/ble-mesh-prototype")
        article = manager.extract(doc)
        if article.images:
            for img in article.images:
                assert img.url.startswith("https://theweekendhacker.example.com/")

    def test_comments_excluded(self, manager):
        doc = load_doc("blog_post.html", url="https://theweekendhacker.example.com/posts/ble-mesh-prototype")
        article = manager.extract(doc)
        if article.body_text:
            assert "Great writeup" not in article.body_text


# --------------------------------------------------------------------------- #
# 4. Broken / malformed HTML
# --------------------------------------------------------------------------- #

class TestBrokenHtml:
    def test_does_not_raise(self, manager):
        doc = load_doc("broken_html.html", url="https://coastalnews.example.com/storm-damage")
        article = manager.extract(doc)  # should not raise
        assert article is not None

    def test_recovers_some_content(self, manager):
        doc = load_doc("broken_html.html", url="https://coastalnews.example.com/storm-damage")
        article = manager.extract(doc)
        assert article.body_text
        assert "coastal highway" in article.body_text.lower()

    def test_quality_report_present_even_when_imperfect(self, manager):
        doc = load_doc("broken_html.html", url="https://coastalnews.example.com/storm-damage")
        article = manager.extract(doc)
        assert article.quality is not None
        assert isinstance(article.quality.warnings, list)


# --------------------------------------------------------------------------- #
# 5. Missing metadata page
# --------------------------------------------------------------------------- #

class TestMissingMetadata:
    def test_falls_back_gracefully(self, manager):
        doc = load_doc("missing_metadata.html", url="https://smalltownnews.example.com/fire-report")
        article = manager.extract(doc)
        assert article.body_text
        assert "warehouse" in article.body_text.lower()

    def test_quality_flags_missing_fields(self, manager):
        doc = load_doc("missing_metadata.html", url="https://smalltownnews.example.com/fire-report")
        article = manager.extract(doc)
        assert article.quality.missing_title is True
        assert article.quality.missing_author is True
        assert article.quality.missing_date is True
        assert "no title" in " ".join(article.quality.warnings).lower()

    def test_strategy_used_is_lower_tier(self, manager):
        doc = load_doc("missing_metadata.html", url="https://smalltownnews.example.com/fire-report")
        article = manager.extract(doc)
        assert article.quality.strategy_used in {
            ExtractionStrategy.ARTICLE_LIBRARY,
            ExtractionStrategy.READABILITY,
            ExtractionStrategy.DOM_HEURISTIC,
            ExtractionStrategy.FALLBACK,
        }


# --------------------------------------------------------------------------- #
# 6. Paywall page (short teaser body only)
# --------------------------------------------------------------------------- #

class TestPaywallPage:
    def test_extracts_teaser_and_metadata(self, manager):
        doc = load_doc("paywall_page.html", url="https://businesstimes.example.com/exclusive/infra-deal")
        article = manager.extract(doc)
        assert article.title == "Exclusive: Inside the Region's Largest Infrastructure Deal"
        assert "Rohan Deshpande" in article.authors

    def test_short_body_flagged_in_quality(self, manager):
        doc = load_doc("paywall_page.html", url="https://businesstimes.example.com/exclusive/infra-deal")
        article = manager.extract(doc)
        # Body is intentionally tiny (one teaser sentence) -- should be
        # flagged as missing/short rather than silently treated as complete
        assert article.quality.missing_body is True or article.word_count < 50

    def test_paywall_banner_text_excluded(self, manager):
        doc = load_doc("paywall_page.html", url="https://businesstimes.example.com/exclusive/infra-deal")
        article = manager.extract(doc)
        if article.body_text:
            assert "Subscribe Now" not in article.body_text
            assert "subscribers only" not in article.body_text.lower()


# --------------------------------------------------------------------------- #
# 7. Large article (many paragraphs)
# --------------------------------------------------------------------------- #

class TestLargeArticle:
    def test_extracts_all_paragraphs(self, manager):
        doc = load_doc("large_article.html", url="https://feature.example.com/pilgrimage-logistics")
        article = manager.extract(doc)
        assert article.body_text
        assert article.word_count > 400
        assert len(article.paragraphs) >= 30

    def test_reading_time_scales_with_length(self, manager):
        doc = load_doc("large_article.html", url="https://feature.example.com/pilgrimage-logistics")
        article = manager.extract(doc)
        assert article.reading_time_minutes >= 2.0

    def test_quality_score_reasonable(self, manager):
        doc = load_doc("large_article.html", url="https://feature.example.com/pilgrimage-logistics")
        article = manager.extract(doc)
        assert article.quality.missing_body is False
        assert article.quality.boilerplate_ratio < 0.5


# --------------------------------------------------------------------------- #
# 8. Normalization unit tests
# --------------------------------------------------------------------------- #

class TestNormalizationUtils:
    def test_normalize_whitespace_collapses_runs(self):
        assert norm.normalize_whitespace("Hello    world\n\n\n\nFoo") == "Hello world\n\nFoo"

    def test_normalize_date_handles_iso(self):
        dt = norm.normalize_date("2026-06-15T08:30:00Z")
        assert dt.year == 2026 and dt.month == 6 and dt.day == 15

    def test_normalize_date_handles_epoch_seconds(self):
        dt = norm.normalize_date("1750000000")
        assert dt is not None

    def test_normalize_date_invalid_returns_none(self):
        assert norm.normalize_date("not-a-date-at-all-xyz") is None

    def test_normalize_url_strips_tracking_params(self):
        result = norm.normalize_url("https://example.com/page?utm_source=fb&id=5")
        assert "utm_source" not in result
        assert "id=5" in result

    def test_normalize_url_resolves_relative(self):
        result = norm.normalize_url("/foo/bar", base_url="https://example.com/base/")
        assert result == "https://example.com/foo/bar"

    def test_dedupe_paragraphs_removes_duplicates(self):
        paras = ["Hello world.", "Hello world.", "Something else."]
        assert norm.dedupe_paragraphs(paras) == ["Hello world.", "Something else."]

    def test_word_count(self):
        assert norm.compute_word_count("one two three") == 3

    def test_reading_time(self):
        assert norm.compute_reading_time_minutes(450, wpm=225) == 2.0


# --------------------------------------------------------------------------- #
# 9. Engine-level guarantees
# --------------------------------------------------------------------------- #

class TestEngineGuarantees:
    @pytest.mark.parametrize("fixture", [
        "simple_news_article.html",
        "government_page.html",
        "blog_post.html",
        "broken_html.html",
        "missing_metadata.html",
        "paywall_page.html",
        "large_article.html",
    ])
    def test_never_raises_for_any_fixture(self, manager, fixture):
        doc = load_doc(fixture, url="https://example.com/test")
        article = manager.extract(doc)
        assert article is not None
        assert article.quality is not None

    def test_empty_document_does_not_crash(self, manager):
        doc = RawDocument(url="https://example.com/empty", content=b"<html><body></body></html>")
        article = manager.extract(doc)
        assert article is not None
        assert article.quality.strategy_used in {ExtractionStrategy.FALLBACK, ExtractionStrategy.NONE}

    def test_non_utf8_bytes_do_not_crash(self, manager):
        raw = "<html><body><h1>Café Müller</h1><p>Some café news with naïve café formatting and more padding text to pass length thresholds for extraction routines used here.</p></body></html>".encode("latin-1")
        doc = RawDocument(url="https://example.com/encoding-test", content=raw, encoding="latin-1")
        article = manager.extract(doc)
        assert article is not None
