"""
Strategy 3: Article Extraction Library.

Wraps a battle-tested third-party extraction library (trafilatura) when it's
installed. These libraries encode years of accumulated heuristics across
thousands of real-world news templates and are usually more robust than a
from-scratch DOM heuristic, so we prefer them when available -- but the
engine must keep working if the dependency is absent (graceful degradation),
which is why this extractor self-disables via `success=False` rather than
raising an ImportError.
"""
from __future__ import annotations

from bs4 import BeautifulSoup

from core import metadata as meta_utils
from core import normalization as norm
from core.models import ExtractionResult, ExtractionStrategy, ImageAsset, NormalizedArticle, RawDocument
from extractors.base import BaseExtractor

try:
    import trafilatura
    from trafilatura.settings import use_config
    _HAS_TRAFILATURA = True
except ImportError:  # pragma: no cover - exercised only when dependency missing
    _HAS_TRAFILATURA = False


class ArticleLibraryExtractor(BaseExtractor):
    strategy = ExtractionStrategy.ARTICLE_LIBRARY

    def extract(self, document: RawDocument) -> ExtractionResult:
        if not _HAS_TRAFILATURA:
            return ExtractionResult(self.strategy, None, False, 0.0,
                                     error="trafilatura not installed")

        html = document.decoded_text()

        config = use_config()
        config.set("DEFAULT", "EXTRACTION_TIMEOUT", "10")

        result = trafilatura.bare_extraction(
            html,
            url=document.url,
            with_metadata=True,
            include_comments=False,
            include_tables=True,
            include_images=True,
            favor_precision=True,
            config=config,
        )

        if not result or not result.get("text"):
            return ExtractionResult(self.strategy, None, False, 0.0,
                                     error="trafilatura returned no text")

        soup = BeautifulSoup(html, "lxml")
        article = NormalizedArticle(url=document.url)

        article.title = result.get("title")
        article.body_text = norm.normalize_whitespace(result.get("text"))
        article.paragraphs = norm.dedupe_paragraphs(
            [p for p in (article.body_text or "").split("\n\n") if p.strip()]
        )
        article.summary = result.get("description")
        author = result.get("author")
        article.authors = [author.strip()] if author else []
        article.published_at = norm.normalize_date(result.get("date"))
        article.language = result.get("language") or meta_utils.extract_language(soup)
        article.categories = [result.get("category")] if result.get("category") else []
        tags = result.get("tags")
        article.tags = list(tags) if isinstance(tags, (list, tuple)) else (
            [tags] if tags else []
        )

        image_url = result.get("image")
        if image_url:
            resolved = norm.resolve_image_url(image_url, document.url)
            if resolved:
                article.images.append(ImageAsset(url=resolved, is_hero=True))

        article.canonical_url = norm.normalize_url(
            result.get("url") or document.url, document.url
        )

        word_count = norm.compute_word_count(article.body_text)
        confidence = 0.0
        if article.title:
            confidence += 0.2
        if word_count > 80:
            confidence += 0.5
        if article.authors:
            confidence += 0.1
        if article.published_at:
            confidence += 0.1

        success = word_count > 30
        return ExtractionResult(self.strategy, article, success, min(confidence, 1.0))
