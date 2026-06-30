"""
Diagnostics Layer.

Computes the extraction QualityReport attached to every NormalizedArticle:
flags missing fields, content length, boilerplate ratio, and an overall
0-1 confidence score blending field-completeness with the winning
extractor's self-reported confidence.
"""
from __future__ import annotations

from typing import List

from core.cleaning import estimate_boilerplate_ratio
from core.models import ExtractionStrategy, NormalizedArticle, QualityReport


def build_quality_report(
    article: NormalizedArticle,
    strategy_used: ExtractionStrategy,
    strategies_attempted: List[str],
    extractor_confidence: float,
    original_html: str,
) -> QualityReport:
    report = QualityReport()
    report.strategy_used = strategy_used
    report.strategies_attempted = strategies_attempted

    report.missing_title = not bool(article.title)
    report.missing_author = not bool(article.authors)
    report.missing_date = not bool(article.published_at)
    report.missing_body = not bool(article.body_text and len(article.body_text) > 100)

    report.content_length = len(article.body_text) if article.body_text else 0
    report.word_count = article.word_count

    report.boilerplate_ratio = estimate_boilerplate_ratio(
        original_html, report.content_length
    )

    report.warnings = _collect_warnings(report)
    report.score = _compute_score(report, extractor_confidence)
    return report


def _collect_warnings(report: QualityReport) -> List[str]:
    warnings = []
    if report.missing_title:
        warnings.append("Article has no title")
    if report.missing_author:
        warnings.append("Article has no identified author")
    if report.missing_date:
        warnings.append("Article has no published date")
    if report.missing_body:
        warnings.append("Article body is missing or too short (<100 chars)")
    if report.word_count > 0 and report.word_count < 50:
        warnings.append("Article body is unusually short (<50 words) -- possible paywall stub")
    if report.boilerplate_ratio > 0.85:
        warnings.append("High boilerplate ratio -- extraction may have captured mostly chrome")
    return warnings


def _compute_score(report: QualityReport, extractor_confidence: float) -> float:
    completeness = 0.0
    completeness += 0.0 if report.missing_title else 0.25
    completeness += 0.0 if report.missing_author else 0.15
    completeness += 0.0 if report.missing_date else 0.15
    completeness += 0.0 if report.missing_body else 0.35
    completeness += 0.10 if report.boilerplate_ratio < 0.5 else 0.0

    blended = 0.6 * completeness + 0.4 * extractor_confidence
    return max(0.0, min(blended, 1.0))
