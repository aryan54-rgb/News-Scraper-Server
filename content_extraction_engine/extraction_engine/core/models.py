"""
Core data models for the Content Extraction Engine.

These models are intentionally framework-agnostic (plain dataclasses) so the
engine can be embedded in any collector, worker, or pipeline without pulling
in ORM or web-framework dependencies.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


# --------------------------------------------------------------------------- #
# INPUT
# --------------------------------------------------------------------------- #

@dataclass
class RawDocument:
    """The raw output of a Collector fetch, before any extraction happens."""
    url: str
    content: bytes
    headers: Dict[str, str] = field(default_factory=dict)
    content_type: Optional[str] = None
    encoding: Optional[str] = None
    fetched_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def decoded_text(self) -> str:
        """Best-effort decode of raw bytes into a text string."""
        enc_candidates = []
        if self.encoding:
            enc_candidates.append(self.encoding)
        # sniff from content-type header e.g. "text/html; charset=ISO-8859-1"
        if self.content_type and "charset=" in self.content_type:
            enc_candidates.append(self.content_type.split("charset=")[-1].strip())
        enc_candidates.extend(["utf-8", "latin-1"])

        for enc in enc_candidates:
            try:
                return self.content.decode(enc, errors="strict")
            except (LookupError, UnicodeDecodeError):
                continue
        # last resort: replace undecodable bytes
        return self.content.decode("utf-8", errors="replace")


# --------------------------------------------------------------------------- #
# SUPPORTING STRUCTURES
# --------------------------------------------------------------------------- #

@dataclass
class ImageAsset:
    url: str
    caption: Optional[str] = None
    alt: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    is_hero: bool = False


@dataclass
class VideoAsset:
    url: str
    caption: Optional[str] = None
    thumbnail_url: Optional[str] = None
    provider: Optional[str] = None  # e.g. youtube, vimeo, self-hosted


@dataclass
class SocialMetadata:
    """Container for OpenGraph / Twitter Card key-value metadata."""
    values: Dict[str, str] = field(default_factory=dict)

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        return self.values.get(key, default)


# --------------------------------------------------------------------------- #
# QUALITY / DIAGNOSTICS
# --------------------------------------------------------------------------- #

class ExtractionStrategy(str, Enum):
    JSON_LD = "json_ld"
    OPEN_GRAPH = "open_graph"
    ARTICLE_LIBRARY = "article_library"
    READABILITY = "readability"
    DOM_HEURISTIC = "dom_heuristic"
    FALLBACK = "fallback"
    NONE = "none"


@dataclass
class QualityReport:
    strategy_used: ExtractionStrategy = ExtractionStrategy.NONE
    strategies_attempted: List[str] = field(default_factory=list)
    missing_title: bool = True
    missing_author: bool = True
    missing_date: bool = True
    missing_body: bool = True
    content_length: int = 0
    word_count: int = 0
    boilerplate_ratio: float = 0.0
    score: float = 0.0  # 0.0 - 1.0 overall confidence
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "strategy_used": self.strategy_used.value,
            "strategies_attempted": self.strategies_attempted,
            "missing_title": self.missing_title,
            "missing_author": self.missing_author,
            "missing_date": self.missing_date,
            "missing_body": self.missing_body,
            "content_length": self.content_length,
            "word_count": self.word_count,
            "boilerplate_ratio": round(self.boilerplate_ratio, 4),
            "score": round(self.score, 4),
            "warnings": self.warnings,
        }


# --------------------------------------------------------------------------- #
# OUTPUT
# --------------------------------------------------------------------------- #

@dataclass
class NormalizedArticle:
    url: str
    canonical_url: Optional[str] = None

    title: Optional[str] = None
    subtitle: Optional[str] = None
    summary: Optional[str] = None

    authors: List[str] = field(default_factory=list)
    published_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    language: Optional[str] = None

    body_html: Optional[str] = None
    body_text: Optional[str] = None
    paragraphs: List[str] = field(default_factory=list)

    categories: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)

    images: List[ImageAsset] = field(default_factory=list)
    videos: List[VideoAsset] = field(default_factory=list)

    open_graph: SocialMetadata = field(default_factory=SocialMetadata)
    twitter_card: SocialMetadata = field(default_factory=SocialMetadata)
    json_ld: List[Dict[str, Any]] = field(default_factory=list)

    meta_description: Optional[str] = None
    meta_keywords: List[str] = field(default_factory=list)

    reading_time_minutes: Optional[float] = None
    word_count: int = 0

    quality: QualityReport = field(default_factory=QualityReport)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "url": self.url,
            "canonical_url": self.canonical_url,
            "title": self.title,
            "subtitle": self.subtitle,
            "summary": self.summary,
            "authors": self.authors,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "language": self.language,
            "body_html": self.body_html,
            "body_text": self.body_text,
            "paragraphs": self.paragraphs,
            "categories": self.categories,
            "tags": self.tags,
            "images": [vars(i) for i in self.images],
            "videos": [vars(v) for v in self.videos],
            "open_graph": self.open_graph.values,
            "twitter_card": self.twitter_card.values,
            "json_ld": self.json_ld,
            "meta_description": self.meta_description,
            "meta_keywords": self.meta_keywords,
            "reading_time_minutes": self.reading_time_minutes,
            "word_count": self.word_count,
            "quality": self.quality.to_dict(),
        }


@dataclass
class ExtractionResult:
    """What each individual Extractor returns to the Manager."""
    strategy: ExtractionStrategy
    article: Optional[NormalizedArticle]
    success: bool
    confidence: float = 0.0  # 0.0 - 1.0, extractor's self-assessed confidence
    error: Optional[str] = None
