"""End-to-end relevance plus classification pipeline."""
from __future__ import annotations

from typing import Any, Optional

from .classification import ClassificationEngine
from .models import IntelligencePipelineResult, RelevanceDecision
from .relevance import RelevanceEngine


class IntelligencePipeline:
    def __init__(
        self,
        *,
        relevance_engine: Optional[RelevanceEngine] = None,
        classification_engine: Optional[ClassificationEngine] = None,
    ) -> None:
        self.relevance_engine = relevance_engine or RelevanceEngine()
        self.classification_engine = classification_engine or ClassificationEngine()

    def process(self, article: Any) -> IntelligencePipelineResult:
        relevance = self.relevance_engine.evaluate(article)
        if relevance.decision != RelevanceDecision.RELEVANT:
            return IntelligencePipelineResult(relevance=relevance)
        classification = self.classification_engine.classify(article, relevance)
        return IntelligencePipelineResult(relevance=relevance, classification=classification)
