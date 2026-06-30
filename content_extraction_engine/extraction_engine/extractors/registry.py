"""
Extractor Registry.

Decouples "which extractors exist and in what order" from the Manager's
orchestration logic, so collectors/tests can register custom or
site-specific extractors without touching engine internals.
"""
from __future__ import annotations

from typing import List, Type

from extractors.article_library_extractor import ArticleLibraryExtractor
from extractors.base import BaseExtractor
from extractors.dom_heuristic_extractor import DomHeuristicExtractor
from extractors.fallback_extractor import FallbackExtractor
from extractors.jsonld_extractor import JsonLdExtractor
from extractors.opengraph_extractor import OpenGraphExtractor
from extractors.readability_extractor import ReadabilityExtractor


class ExtractorRegistry:
    """Holds the ordered list of extractor classes the Manager will try.

    Order matters: it reflects the documented strategy priority
    (JSON-LD -> OpenGraph -> Article library -> Readability -> DOM heuristic
    -> Fallback). Register custom extractors with `register()` to insert
    site-specific overrides ahead of the generic strategies.
    """

    def __init__(self) -> None:
        self._extractor_classes: List[Type[BaseExtractor]] = [
            JsonLdExtractor,
            OpenGraphExtractor,
            ArticleLibraryExtractor,
            ReadabilityExtractor,
            DomHeuristicExtractor,
            FallbackExtractor,
        ]

    def register(self, extractor_cls: Type[BaseExtractor], position: int = 0) -> None:
        """Insert a custom extractor class at the given priority position
        (0 = highest priority, tried first)."""
        self._extractor_classes.insert(position, extractor_cls)

    def unregister(self, extractor_cls: Type[BaseExtractor]) -> None:
        self._extractor_classes = [
            c for c in self._extractor_classes if c is not extractor_cls
        ]

    def build(self) -> List[BaseExtractor]:
        """Instantiate fresh extractor objects in priority order."""
        return [cls() for cls in self._extractor_classes]


default_registry = ExtractorRegistry()
