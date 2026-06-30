"""
Extractor Interface.

Every concrete extraction strategy implements this abstract base class.
The Manager treats all extractors polymorphically -- it doesn't know or care
whether it's calling the JSON-LD extractor or the DOM heuristic extractor,
only that each returns an ExtractionResult.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from core.models import ExtractionResult, ExtractionStrategy, RawDocument


class BaseExtractor(ABC):
    """Common interface for all extraction strategies."""

    strategy: ExtractionStrategy = ExtractionStrategy.NONE

    @abstractmethod
    def extract(self, document: RawDocument) -> ExtractionResult:
        """Attempt to extract a NormalizedArticle from the raw document.

        Implementations must never raise -- catch internal errors and
        return ExtractionResult(success=False, error=...) instead, so the
        Manager can move on to the next strategy without a wrapped try/except
        at every call site.
        """
        raise NotImplementedError

    def safe_extract(self, document: RawDocument) -> ExtractionResult:
        """Wrapper that guarantees extract() never propagates an exception
        to the Manager, regardless of extractor implementation discipline."""
        try:
            return self.extract(document)
        except Exception as exc:  # noqa: BLE001 - intentional catch-all boundary
            return ExtractionResult(
                strategy=self.strategy,
                article=None,
                success=False,
                confidence=0.0,
                error=f"{type(exc).__name__}: {exc}",
            )
