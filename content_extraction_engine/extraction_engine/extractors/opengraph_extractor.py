"""
Strategy 2: OpenGraph / Twitter Card Extraction.

Provides reliable metadata (title, hero image, description, type) from
og:* and twitter:* meta tags. This rarely yields a full article body, so its
primary role is metadata -- the Manager merges it underneath JSON-LD and
on top of whatever body-producing strategy succeeds.
"""
from __future__ import annotations

from bs4 import BeautifulSoup

from core import metadata as meta_utils
from core import normalization as norm
from core.models import (
    ExtractionResult, ExtractionStrategy, ImageAsset, NormalizedArticle,
    RawDocument, SocialMetadata, VideoAsset,
)
from extractors.base import BaseExtractor


class OpenGraphExtractor(BaseExtractor):
    strategy = ExtractionStrategy.OPEN_GRAPH

    def extract(self, document: RawDocument) -> ExtractionResult:
        html = document.decoded_text()
        soup = BeautifulSoup(html, "lxml")

        og = meta_utils.extract_open_graph(soup)
        tw = meta_utils.extract_twitter_card(soup)

        if not og and not tw:
            return ExtractionResult(self.strategy, None, False, 0.0,
                                     error="no OpenGraph or Twitter Card tags found")

        article = NormalizedArticle(url=document.url)
        article.open_graph = SocialMetadata(values=og)
        article.twitter_card = SocialMetadata(values=tw)

        article.title = og.get("title") or tw.get("title")
        article.summary = og.get("description") or tw.get("description")
        article.canonical_url = norm.normalize_url(og.get("url"), document.url)
        article.meta_description = meta_utils.extract_meta_description(soup)
        article.meta_keywords = meta_utils.extract_meta_keywords(soup)
        article.language = meta_utils.extract_language(soup)

        published = og.get("article:published_time") or og.get("published_time")
        modified = og.get("article:modified_time") or og.get("modified_time")
        article.published_at = norm.normalize_date(published)
        article.updated_at = norm.normalize_date(modified)

        author = og.get("article:author")
        if author:
            article.authors = [author.strip()]

        section = og.get("article:section")
        if section:
            article.categories = [section.strip()]
        og_tag = og.get("article:tag")
        if og_tag:
            article.tags = [t.strip() for t in og_tag.split(",") if t.strip()]

        image_url = og.get("image") or og.get("image:secure_url") or tw.get("image")
        if image_url:
            resolved = norm.resolve_image_url(image_url, document.url)
            if resolved:
                article.images.append(ImageAsset(
                    url=resolved,
                    is_hero=True,
                    width=self._safe_int(og.get("image:width")),
                    height=self._safe_int(og.get("image:height")),
                ))

        if og.get("type") == "video" or tw.get("card") == "player":
            video_url = og.get("video") or og.get("video:url") or tw.get("player")
            if video_url:
                resolved = norm.resolve_image_url(video_url, document.url)
                article.videos.append(VideoAsset(
                    url=resolved,
                    thumbnail_url=norm.resolve_image_url(image_url, document.url) if image_url else None,
                ))

        confidence = 0.0
        if article.title:
            confidence += 0.3
        if article.images:
            confidence += 0.2
        if article.summary:
            confidence += 0.2
        # OpenGraph never produces a body -> capped confidence
        success = bool(article.title or article.summary or article.images)
        return ExtractionResult(self.strategy, article, success, confidence)

    @staticmethod
    def _safe_int(value):
        try:
            return int(value) if value is not None else None
        except (ValueError, TypeError):
            return None
