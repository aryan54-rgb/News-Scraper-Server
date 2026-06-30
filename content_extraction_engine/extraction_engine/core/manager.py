"""
Extraction Manager.

The single entry point collectors call. Responsibilities:
  1. Run every registered extractor (each wrapped in safe_extract so a bug
     in one strategy can never take down the pipeline).
  2. Pick the best body-producing result.
  3. Layer metadata-only results (JSON-LD, OpenGraph) on top to fill any
     gaps the body-winning extractor left empty.
  4. Run final normalization passes (word count, reading time, dedupe).
  5. Attach a QualityReport diagnostic.
"""
from __future__ import annotations

from typing import List, Optional

from core import normalization as norm
from core.diagnostics import build_quality_report
from core.models import (
    ExtractionResult, ExtractionStrategy, NormalizedArticle, QualityReport, RawDocument,
)
from extractors.registry import ExtractorRegistry, default_registry

# Strategies capable of producing a usable article body (used to decide
# the "primary" result the rest of the fields get layered onto)
_BODY_STRATEGIES = {
    ExtractionStrategy.JSON_LD,
    ExtractionStrategy.ARTICLE_LIBRARY,
    ExtractionStrategy.READABILITY,
    ExtractionStrategy.DOM_HEURISTIC,
    ExtractionStrategy.FALLBACK,
}

_MIN_BODY_CHARS = 100


class ExtractionManager:
    def __init__(self, registry: Optional[ExtractorRegistry] = None) -> None:
        self.registry = registry or default_registry

    def extract(self, document: RawDocument) -> NormalizedArticle:
        extractors = self.registry.build()
        results: List[ExtractionResult] = []

        for extractor in extractors:
            result = extractor.safe_extract(document)
            results.append(result)

        primary = self._select_primary(results)
        article = primary.article if primary and primary.article else NormalizedArticle(url=document.url)

        self._merge_metadata(article, results, exclude=primary)
        self._finalize(article, document)

        attempted = [r.strategy.value for r in results]
        strategy_used = primary.strategy if primary else ExtractionStrategy.NONE
        confidence = primary.confidence if primary else 0.0

        article.quality = build_quality_report(
            article=article,
            strategy_used=strategy_used,
            strategies_attempted=attempted,
            extractor_confidence=confidence,
            original_html=document.decoded_text(),
        )
        return article

    # ------------------------------------------------------------------ #

    def _select_primary(self, results: List[ExtractionResult]) -> Optional[ExtractionResult]:
        """Pick the highest-confidence successful result that has a real
        body, in strategy-priority order as a tiebreaker."""
        body_candidates = [
            r for r in results
            if r.success and r.article and r.article.body_text
            and len(r.article.body_text) >= _MIN_BODY_CHARS
            and r.strategy in _BODY_STRATEGIES
        ]
        if body_candidates:
            return max(body_candidates, key=lambda r: r.confidence)

        # No strategy produced a real body -- fall back to whatever has the
        # highest confidence at all (e.g. OpenGraph metadata-only page)
        any_success = [r for r in results if r.success and r.article]
        if any_success:
            return max(any_success, key=lambda r: r.confidence)
        return None

    def _merge_metadata(
        self,
        article: NormalizedArticle,
        results: List[ExtractionResult],
        exclude: Optional[ExtractionResult],
    ) -> None:
        """Fill gaps in `article` using fields from other successful results,
        preferring JSON-LD, then OpenGraph, in that order."""
        priority_order = [ExtractionStrategy.JSON_LD, ExtractionStrategy.OPEN_GRAPH]
        donors = [
            r for r in results
            if r.success and r.article and r is not exclude
        ]
        donors.sort(key=lambda r: priority_order.index(r.strategy) if r.strategy in priority_order else 99)

        for donor in donors:
            d = donor.article
            if not article.title and d.title:
                article.title = d.title
            if not article.subtitle and d.subtitle:
                article.subtitle = d.subtitle
            if not article.summary and d.summary:
                article.summary = d.summary
            if not article.authors and d.authors:
                article.authors = d.authors
            if not article.published_at and d.published_at:
                article.published_at = d.published_at
            if not article.updated_at and d.updated_at:
                article.updated_at = d.updated_at
            if not article.language and d.language:
                article.language = d.language
            if not article.categories and d.categories:
                article.categories = d.categories
            if not article.tags and d.tags:
                article.tags = d.tags
            if not article.images and d.images:
                article.images = d.images
            if not article.videos and d.videos:
                article.videos = d.videos
            if not article.canonical_url and d.canonical_url:
                article.canonical_url = d.canonical_url
            if not article.meta_description and d.meta_description:
                article.meta_description = d.meta_description
            if not article.meta_keywords and d.meta_keywords:
                article.meta_keywords = d.meta_keywords
            if not article.json_ld and d.json_ld:
                article.json_ld = d.json_ld
            if d.open_graph.values and not article.open_graph.values:
                article.open_graph = d.open_graph
            if d.twitter_card.values and not article.twitter_card.values:
                article.twitter_card = d.twitter_card

    def _finalize(self, article: NormalizedArticle, document: RawDocument) -> None:
        article.url = norm.normalize_url(article.url, document.url) or article.url
        article.canonical_url = norm.normalize_url(article.canonical_url, document.url) or article.canonical_url

        if article.title:
            article.title = norm.normalize_whitespace(article.title)
        if article.subtitle:
            article.subtitle = norm.normalize_whitespace(article.subtitle)
        if article.summary:
            article.summary = norm.normalize_whitespace(article.summary)

        article.authors = norm.dedupe_preserve_order(article.authors)
        article.categories = norm.dedupe_preserve_order(article.categories)
        article.tags = norm.dedupe_preserve_order(article.tags)

        if article.paragraphs:
            article.paragraphs = norm.strip_empty_sections(
                norm.dedupe_paragraphs(article.paragraphs)
            )
            if not article.body_text:
                article.body_text = "\n\n".join(article.paragraphs)

        if article.body_text:
            article.body_text = norm.normalize_whitespace(article.body_text)

        article.word_count = norm.compute_word_count(article.body_text)
        article.reading_time_minutes = norm.compute_reading_time_minutes(article.word_count)

        for img in article.images:
            img.url = norm.resolve_image_url(img.url, document.url) or img.url
        for vid in article.videos:
            vid.url = norm.resolve_image_url(vid.url, document.url) or vid.url
