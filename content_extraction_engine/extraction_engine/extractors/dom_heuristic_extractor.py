"""
Strategy 5: DOM Heuristic Extraction.

A simpler, faster heuristic than the full Readability scoring pass: look for
semantic containers first (<article>, <main>, [role=main], common CMS class
names like .article-body/.post-content/.entry-content), and pick whichever
candidate has the highest paragraph-text density. This catches well-marked-up
modern sites quickly without the cost of scoring every node in the tree, and
acts as a second opinion when the Readability pass picks a low-confidence
node (e.g. on sparse government/gov.in style pages).
"""
from __future__ import annotations

from typing import List, Optional

from bs4 import Tag

from core import metadata as meta_utils
from core import normalization as norm
from core.cleaning import clean_for_extraction, html_fragment_to_text
from core.models import ExtractionResult, ExtractionStrategy, ImageAsset, NormalizedArticle, RawDocument
from extractors.base import BaseExtractor

_SEMANTIC_SELECTORS = [
    {"name": "article"},
    {"name": "main"},
    {"attrs": {"role": "main"}},
    {"attrs": {"itemprop": "articleBody"}},
]
_CLASS_HINTS = [
    "article-body", "article-content", "post-content", "entry-content",
    "story-body", "story-content", "content-body", "page-content",
    "main-content", "articleBody", "post-body", "blog-post", "single-content",
]


class DomHeuristicExtractor(BaseExtractor):
    strategy = ExtractionStrategy.DOM_HEURISTIC

    def extract(self, document: RawDocument) -> ExtractionResult:
        html = document.decoded_text()
        soup = clean_for_extraction(html)
        body = soup.find("body") or soup

        candidates = self._find_candidates(body)
        if not candidates:
            return ExtractionResult(self.strategy, None, False, 0.0,
                                     error="no semantic candidate containers found")

        best_node, best_len = max(
            ((node, self._paragraph_text_len(node)) for node in candidates),
            key=lambda pair: pair[1],
        )
        if best_len < 150:
            return ExtractionResult(self.strategy, None, False, 0.0,
                                     error="best candidate too short")

        text = norm.normalize_whitespace(html_fragment_to_text(best_node))
        article = NormalizedArticle(url=document.url)
        article.body_html = str(best_node)
        article.body_text = text
        article.paragraphs = norm.dedupe_paragraphs([p for p in text.split("\n\n") if p.strip()])

        title_tag = soup.find("h1")
        article.title = norm.normalize_whitespace(title_tag.get_text()) if title_tag else None
        article.language = meta_utils.extract_language(soup)

        for img in best_node.find_all("img"):
            src = img.get("src") or img.get("data-src")
            if not src:
                continue
            resolved = norm.resolve_image_url(src, document.url)
            if resolved:
                article.images.append(ImageAsset(url=resolved, alt=img.get("alt")))

        word_count = norm.compute_word_count(text)
        confidence = 0.0
        if article.title:
            confidence += 0.1
        if word_count > 150:
            confidence += 0.4
        if best_node.name in ("article", "main"):
            confidence += 0.2

        success = word_count >= 60
        return ExtractionResult(self.strategy, article, success, min(confidence, 1.0))

    def _find_candidates(self, body: Tag) -> List[Tag]:
        found: List[Tag] = []
        for selector in _SEMANTIC_SELECTORS:
            if "name" in selector:
                found.extend(body.find_all(selector["name"]))
            else:
                found.extend(body.find_all(attrs=selector["attrs"]))

        for hint in _CLASS_HINTS:
            found.extend(body.find_all(class_=lambda c, h=hint: c and h.lower() in " ".join(c).lower()))
            found.extend(body.find_all(id=lambda i, h=hint: i and h.lower() in i.lower()))

        # de-dupe while preserving order, drop nodes nested inside another candidate
        unique = []
        seen_ids = set()
        for node in found:
            if id(node) in seen_ids:
                continue
            seen_ids.add(id(node))
            unique.append(node)
        return unique

    @staticmethod
    def _paragraph_text_len(node: Tag) -> int:
        paragraphs = node.find_all(["p", "li"])
        return sum(len(p.get_text(strip=True)) for p in paragraphs) or len(node.get_text(strip=True))
