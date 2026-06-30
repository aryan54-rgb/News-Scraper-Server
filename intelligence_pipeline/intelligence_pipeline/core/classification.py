"""LLM-backed classification orchestration with strict validation."""
from __future__ import annotations

import logging
import time
from typing import Any, Optional

from .models import (
    ClassificationConfig,
    ClassificationObservability,
    ClassificationResult,
    RelevanceDecision,
    RelevanceResult,
    TaxonomyConfig,
)
from .openrouter import ClassificationClient, ClassificationClientError, OpenRouterClient
from .prompt import PromptBuilder
from .validation import ClassificationValidationError, ResponseValidator

logger = logging.getLogger(__name__)


class ClassificationSkipped(RuntimeError):
    pass


class ClassificationEngine:
    def __init__(
        self,
        *,
        config: Optional[ClassificationConfig] = None,
        taxonomy: Optional[TaxonomyConfig] = None,
        client: Optional[ClassificationClient] = None,
        prompt_builder: Optional[PromptBuilder] = None,
        validator: Optional[ResponseValidator] = None,
    ) -> None:
        self.config = config or ClassificationConfig.from_env()
        self.taxonomy = taxonomy or TaxonomyConfig()
        self.prompt_builder = prompt_builder or PromptBuilder(self.taxonomy, self.config.prompt_version)
        self.validator = validator or ResponseValidator(self.taxonomy)
        self.client = client or OpenRouterClient(self.config)

    def classify(self, article: Any, relevance: Optional[RelevanceResult] = None) -> ClassificationResult:
        if relevance and relevance.decision != RelevanceDecision.RELEVANT:
            raise ClassificationSkipped("Irrelevant articles are not classified")

        started = time.perf_counter()
        prompt = self.prompt_builder.build(article)
        models = [self.config.model, *self.config.fallback_models]
        validation_failures: list[str] = []
        retries = 0
        last_error: Optional[BaseException] = None

        for model_index, model in enumerate(models):
            for attempt in range(self.config.max_retries + 1):
                if attempt:
                    retries += 1
                try:
                    response = self.client.complete(prompt, model)
                    result = self.validator.validate_json(response.content)
                    result.observability = ClassificationObservability(
                        model=response.model,
                        latency_ms=response.latency_ms,
                        tokens=response.usage,
                        retries=retries,
                        prompt_version=prompt.version,
                        response_size_bytes=len(response.content.encode("utf-8")),
                        validation_failures=validation_failures,
                        processing_time_ms=(time.perf_counter() - started) * 1000,
                    )
                    logger.info(
                        "classification_completed",
                        extra=result.observability.to_dict(),
                    )
                    return result
                except ClassificationValidationError as exc:
                    validation_failures.append(str(exc))
                    last_error = exc
                except ClassificationClientError as exc:
                    last_error = exc
                is_last_attempt = (
                    model_index == len(models) - 1 and attempt == self.config.max_retries
                )
                if self.config.retry_backoff_seconds > 0 and not is_last_attempt:
                    time.sleep(self.config.retry_backoff_seconds)

        processing_time_ms = (time.perf_counter() - started) * 1000
        logger.warning(
            "classification_failed",
            extra={
                "model": models[-1] if models else self.config.model,
                "retries": retries,
                "prompt_version": prompt.version,
                "validation_failures": validation_failures,
                "processing_time_ms": round(processing_time_ms, 2),
                "error": str(last_error) if last_error else "unknown",
            },
        )
        if last_error:
            raise last_error
        raise ClassificationClientError("Classification failed without a specific error")
