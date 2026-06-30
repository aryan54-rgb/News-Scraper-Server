"""Protocol interfaces for intelligence pipeline components."""
from __future__ import annotations

from typing import Any, Protocol

from .models import ClassificationResult, IntelligencePipelineResult, RelevanceResult


class RelevanceEngineProtocol(Protocol):
    def evaluate(self, article: Any) -> RelevanceResult:
        ...


class ClassificationEngineProtocol(Protocol):
    def classify(self, article: Any, relevance: RelevanceResult | None = None) -> ClassificationResult:
        ...


class IntelligencePipelineProtocol(Protocol):
    def process(self, article: Any) -> IntelligencePipelineResult:
        ...
