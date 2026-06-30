"""
Content Extraction Engine -- public package entry point.

Usage:
    from engine import ExtractionManager
    from core.models import RawDocument

    doc = RawDocument(url="https://example.com/article", content=html_bytes)
    article = ExtractionManager().extract(doc)
    print(article.to_dict())
"""
from core.manager import ExtractionManager
from core.models import (
    ExtractionResult,
    ExtractionStrategy,
    ImageAsset,
    NormalizedArticle,
    QualityReport,
    RawDocument,
    SocialMetadata,
    VideoAsset,
)
from extractors.registry import ExtractorRegistry, default_registry

__all__ = [
    "ExtractionManager",
    "ExtractionResult",
    "ExtractionStrategy",
    "ImageAsset",
    "NormalizedArticle",
    "QualityReport",
    "RawDocument",
    "SocialMetadata",
    "VideoAsset",
    "ExtractorRegistry",
    "default_registry",
]
