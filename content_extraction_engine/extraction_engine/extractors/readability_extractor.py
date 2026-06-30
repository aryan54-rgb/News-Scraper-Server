"""
Strategy 4: Readability Algorithm.

A from-scratch implementation of the classic Arc90/Readability scoring
approach: every candidate block-level container is scored based on text
density, comma count, paragraph count, and tag/class name weighting; the
highest-scoring container is treated as the article body.

This differs from the simpler DOM heuristic extractor (Strategy 5) in that
it does iterative score propagation to parent/grandparent nodes and applies
negative weighting for link-dense and boilerplate-flavored containers,
matching the behavior of the original Readability.js algorithm.
"""
from __future__ import annotations

import re
from typing import List, Optional, Tuple

from bs4 import BeautifulSoup, Tag

from core import metadata as meta_utils
from core import normalization as norm
from core.cleaning import clean_for_extraction, html_fragment_to_text
from core.models import ExtractionResult, ExtractionStrategy, ImageAsset, NormalizedArticle, RawDocument
from extractors.base import BaseExtractor

_POSITIVE_RE = re.compile(
    r"article|body|content|entry|main|page|post|text|blog|story", re.I
)
_NEGATIVE_RE = re.compile(
    r"comment|combx|community|disqus|extra|foot|header|menu|remark|rss|"
    r"shoutbox|sidebar|sponsor|ad-break|agegate|pagination|pager|popup|tweet|"
    r"twitter|share|related|widget", re.I
)
_CANDIDATE_TAGS = {"p", "div", "section", "article", "td", "pre"}


class ReadabilityExtractor(BaseExtractor):
    strategy = ExtractionStrategy.READABILITY

    def extract(self, document: RawDocument) -> ExtractionResult:
        html = document.decoded_text()
        soup = clean_for_extraction(html)
        body = soup.find("body") or soup

        scores = self._score_nodes(body)
        if not scores:
            return ExtractionResult(self.strategy, None, False, 0.0, error="no scorable nodes")

        best_node, best_score = max(scores, key=lambda pair: pair[1])
        if best_score <= 0:
            return ExtractionResult(self.strategy, None, False, 0.0, error="no positively scored node")

        text = html_fragment_to_text(best_node)
        text = norm.normalize_whitespace(text)
        if not text or len(text) < 150:
            return ExtractionResult(self.strategy, None, False, 0.0, error="winning node too short")

        article = NormalizedArticle(url=document.url)
        article.body_html = str(best_node)
        article.body_text = text
        article.paragraphs = norm.dedupe_paragraphs([p for p in text.split("\n\n") if p.strip()])

        title_tag = soup.find("h1") or soup.find("title")
        article.title = norm.normalize_whitespace(title_tag.get_text()) if title_tag else None
        article.language = meta_utils.extract_language(soup)

        for img in best_node.find_all("img"):
            src = img.get("src") or img.get("data-src")
            if not src:
                continue
            resolved = norm.resolve_image_url(src, document.url)
            if resolved:
                caption = None
                fig = img.find_parent("figure")
                if fig:
                    cap_tag = fig.find("figcaption")
                    if cap_tag:
                        caption = norm.normalize_whitespace(cap_tag.get_text())
                article.images.append(ImageAsset(
                    url=resolved, alt=img.get("alt"), caption=caption
                ))

        word_count = norm.compute_word_count(text)
        confidence = 0.0
        if article.title:
            confidence += 0.15
        if word_count > 150:
            confidence += 0.55
        confidence += min(best_score / 100.0, 0.3)

        success = word_count >= 80
        return ExtractionResult(self.strategy, article, success, min(confidence, 1.0))

    # ----------------------------------------------------------------- #
    # Scoring internals
    # ----------------------------------------------------------------- #

    def _class_id_weight(self, tag: Tag) -> int:
        sig = " ".join(tag.get("class", []) or []) + " " + (tag.get("id") or "")
        weight = 0
        if _POSITIVE_RE.search(sig):
            weight += 25
        if _NEGATIVE_RE.search(sig):
            weight -= 25
        return weight

    def _score_nodes(self, body: Tag) -> List[Tuple[Tag, float]]:
        candidates = {}

        for p in body.find_all(list(_CANDIDATE_TAGS)):
            text = p.get_text(" ", strip=True)
            if len(text) < 25:
                continue

            score = 1.0
            score += text.count(",")
            score += min(len(text) // 100, 3)

            parent = p.parent
            grandparent = parent.parent if parent else None

            for node, divisor in ((parent, 1), (grandparent, 2)):
                if node is None or not isinstance(node, Tag):
                    continue
                if node not in candidates:
                    candidates[node] = self._class_id_weight(node)
                candidates[node] += score / divisor

        scored = []
        for node, score in candidates.items():
            link_density = self._link_density(node)
            adjusted = score * (1 - link_density)
            scored.append((node, adjusted))
        return scored

    @staticmethod
    def _link_density(node: Tag) -> float:
        text_len = len(node.get_text(strip=True))
        if text_len == 0:
            return 0.0
        link_len = sum(len(a.get_text(strip=True)) for a in node.find_all("a"))
        return min(link_len / text_len, 1.0)
