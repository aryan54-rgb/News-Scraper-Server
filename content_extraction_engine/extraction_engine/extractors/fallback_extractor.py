"""
Strategy 6: Fallback Extraction.

The last resort. When every smarter strategy fails (broken HTML, paywalled
stub pages, exotic templates), this extractor guarantees the pipeline still
returns *something* usable: every <p> tag on the page, concatenated, plus
whatever <title>/<h1> can be found. It deliberately has the lowest
confidence score of all strategies so the Manager only picks it when nothing
else produced a body.
"""
from __future__ import annotations

from core import metadata as meta_utils
from core import normalization as norm
from core.cleaning import clean_for_extraction
from core.models import ExtractionResult, ExtractionStrategy, NormalizedArticle, RawDocument
from extractors.base import BaseExtractor


class FallbackExtractor(BaseExtractor):
    strategy = ExtractionStrategy.FALLBACK

    def extract(self, document: RawDocument) -> ExtractionResult:
        html = document.decoded_text()
        soup = clean_for_extraction(html)

        paragraphs = [
            norm.normalize_whitespace(p.get_text(" ", strip=True))
            for p in soup.find_all("p")
        ]
        paragraphs = [p for p in paragraphs if p and len(p) > 10]
        paragraphs = norm.dedupe_paragraphs(paragraphs)

        article = NormalizedArticle(url=document.url)
        article.paragraphs = paragraphs
        article.body_text = "\n\n".join(paragraphs) if paragraphs else None

        title_tag = soup.find("h1") or soup.find("title")
        article.title = norm.normalize_whitespace(title_tag.get_text()) if title_tag else None
        article.meta_description = meta_utils.extract_meta_description(soup)
        article.language = meta_utils.extract_language(soup)

        word_count = norm.compute_word_count(article.body_text)
        # Fallback always "succeeds" if we found at least a title or one paragraph,
        # since the Manager relies on it as the unconditional last resort.
        success = bool(article.title or paragraphs)
        confidence = 0.05 if success else 0.0  # intentionally near-zero
        return ExtractionResult(self.strategy, article, success, confidence,
                                 error=None if success else "no title or paragraphs found")
