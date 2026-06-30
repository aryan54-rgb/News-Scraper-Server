"""
Strategy 1: JSON-LD Extraction.

Many modern news CMSs (WordPress + Yoast, Drupal, custom React sites) embed
a complete schema.org NewsArticle/Article/BlogPosting block. When present and
well-formed, this is the highest-fidelity, lowest-risk source of structured
metadata (title, authors, dates, images, categories) -- so it's tried first.

Body text from JSON-LD's `articleBody` is rare but used when present;
otherwise this extractor supplies metadata only and lets the manager merge
it with a later body-producing strategy.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup

from core import metadata as meta_utils
from core import normalization as norm
from core.models import (
    ExtractionResult, ExtractionStrategy, ImageAsset, NormalizedArticle, RawDocument,
)
from extractors.base import BaseExtractor

_ARTICLE_TYPES = ["NewsArticle", "Article", "BlogPosting", "Report", "AnalysisNewsArticle",
                   "ReviewNewsArticle", "OpinionNewsArticle"]


class JsonLdExtractor(BaseExtractor):
    strategy = ExtractionStrategy.JSON_LD

    def extract(self, document: RawDocument) -> ExtractionResult:
        html = document.decoded_text()
        soup = BeautifulSoup(html, "lxml")
        blocks = meta_utils.extract_json_ld(soup)

        if not blocks:
            return ExtractionResult(self.strategy, None, False, 0.0, error="no JSON-LD blocks found")

        block = meta_utils.find_jsonld_by_type(blocks, _ARTICLE_TYPES)
        if block is None:
            return ExtractionResult(self.strategy, None, False, 0.0,
                                     error="no Article-typed JSON-LD block found")

        article = NormalizedArticle(url=document.url)
        article.json_ld = blocks

        article.title = self._clean_str(block.get("headline") or block.get("name"))
        article.subtitle = self._clean_str(block.get("alternativeHeadline"))
        article.summary = self._clean_str(block.get("description"))
        article.authors = norm.dedupe_preserve_order(
            meta_utils.jsonld_authors(block.get("author"))
        )
        article.published_at = norm.normalize_date(block.get("datePublished"))
        article.updated_at = norm.normalize_date(block.get("dateModified"))
        article.language = self._clean_str(block.get("inLanguage")) or meta_utils.extract_language(soup)

        body_text = block.get("articleBody")
        if body_text:
            body_text = norm.normalize_whitespace(body_text)
            article.body_text = body_text
            article.paragraphs = norm.dedupe_paragraphs(
                [p for p in body_text.split("\n\n") if p.strip()]
            )

        article.categories = self._as_list(block.get("articleSection"))
        article.tags = self._as_list(block.get("keywords"))

        image_data = block.get("image")
        for img_url in self._image_urls(image_data):
            resolved = norm.resolve_image_url(img_url, document.url)
            if resolved:
                article.images.append(ImageAsset(url=resolved, is_hero=True))

        publisher = block.get("publisher")
        if isinstance(publisher, dict) and not article.authors:
            pub_name = publisher.get("name")
            if pub_name:
                article.authors = [str(pub_name).strip()]

        main_entity = block.get("mainEntityOfPage")
        if isinstance(main_entity, str):
            article.canonical_url = main_entity
        elif isinstance(main_entity, dict):
            article.canonical_url = main_entity.get("@id")
        article.canonical_url = norm.normalize_url(article.canonical_url, document.url)

        has_body = bool(article.body_text)
        has_title = bool(article.title)
        confidence = 0.0
        if has_title:
            confidence += 0.4
        if has_body:
            confidence += 0.4
        if article.authors:
            confidence += 0.1
        if article.published_at:
            confidence += 0.1

        success = has_title  # metadata-only success is still useful to the manager
        return ExtractionResult(self.strategy, article, success, confidence)

    @staticmethod
    def _clean_str(value: Any) -> Optional[str]:
        if value is None:
            return None
        text = norm.normalize_whitespace(str(value))
        return text or None

    @staticmethod
    def _as_list(value: Any) -> List[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return norm.dedupe_preserve_order([str(v).strip() for v in value if str(v).strip()])
        if isinstance(value, str):
            parts = [p.strip() for p in value.split(",")]
            return norm.dedupe_preserve_order([p for p in parts if p])
        return []

    @staticmethod
    def _image_urls(image_data: Any) -> List[str]:
        if image_data is None:
            return []
        if isinstance(image_data, str):
            return [image_data]
        if isinstance(image_data, dict):
            url = image_data.get("url")
            return [url] if url else []
        if isinstance(image_data, list):
            urls = []
            for item in image_data:
                if isinstance(item, str):
                    urls.append(item)
                elif isinstance(item, dict) and item.get("url"):
                    urls.append(item["url"])
            return urls
        return []
