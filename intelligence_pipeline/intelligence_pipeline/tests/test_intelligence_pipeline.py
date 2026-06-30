from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from intelligence_pipeline import (  # noqa: E402
    BooleanRule,
    BooleanRuleEngine,
    ClassificationConfig,
    ClassificationEngine,
    ClassificationSkipped,
    ClassificationTimeoutError,
    ClassificationValidationError,
    IntelligencePipeline,
    KeywordGroup,
    KeywordMatcher,
    PromptBuilder,
    PromptTemplateError,
    RelevanceConfig,
    RelevanceDecision,
    RelevanceEngine,
    ResponseValidator,
    TaxonomyConfig,
)
from intelligence_pipeline.core.models import ModelUsage, PromptBundle  # noqa: E402
from intelligence_pipeline.core.openrouter import LLMResponse  # noqa: E402


@dataclass
class Article:
    title: str
    body_text: str
    subtitle: str | None = None
    summary: str | None = None
    authors: list[str] = field(default_factory=list)
    published_at: datetime | None = None
    categories: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class FakeClient:
    def __init__(self, responses: list[Any]) -> None:
        self.responses = responses
        self.calls: list[tuple[PromptBundle, str]] = []

    def complete(self, prompt: PromptBundle, model: str) -> LLMResponse:
        self.calls.append((prompt, model))
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return LLMResponse(
            content=response,
            model=model,
            latency_ms=12.5,
            usage=ModelUsage(prompt_tokens=10, completion_tokens=20, total_tokens=30),
        )


def relevant_article() -> Article:
    return Article(
        title="Nashik administration announces Kumbh crowd plan",
        subtitle="Police and health teams prepare traffic diversions near Ramkund",
        body_text=(
            "The Nashik administration announced a Kumbh crowd management plan. "
            "Police will deploy teams near Ramkund and health camp workers will "
            "coordinate emergency response along the Godavari river."
        ),
        published_at=datetime.now(timezone.utc) - timedelta(days=1),
        categories=["Local"],
        tags=["Kumbh", "Traffic"],
        metadata={"source_id": "gov.example"},
    )


def irrelevant_article() -> Article:
    return Article(
        title="Crypto movie release gets new trailer",
        body_text="A film studio released a movie trailer about cryptocurrency markets.",
        published_at=datetime.now(timezone.utc) - timedelta(days=1),
    )


def valid_payload(**overrides: Any) -> str:
    payload: dict[str, Any] = {
        "theme": ["crowd_management", "public_safety"],
        "genre": ["news_report"],
        "event_type": ["preparedness"],
        "stakeholders": [
            {"name": "Nashik administration", "type": "government", "role": "announced plan"},
            {"name": "Police", "type": "police", "role": "deployment"},
        ],
        "geography": ["nashik", "ramkund", "godavari"],
        "outcomes": ["announcement", "deployment"],
        "evidence_snippets": ["announced a Kumbh crowd management plan"],
        "confidence": 0.91,
        "rationale": "Article describes official preparedness measures.",
    }
    payload.update(overrides)
    return json.dumps(payload)


def relevance_config() -> RelevanceConfig:
    return RelevanceConfig(
        threshold=0.45,
        source_priorities={"gov.example": 1.0},
        keyword_groups=[
            KeywordGroup("core", ["kumbh", "simhastha", "ramkund", "godavari"]),
            KeywordGroup("operations", ["crowd", "traffic", "health camp", "emergency"]),
        ],
        boolean_rules=[
            BooleanRule("kumbh_nashik", "(Kumbh OR Simhastha) AND (Nashik OR Trimbakeshwar) NOT Crypto")
        ],
    )


def classification_engine(client: FakeClient, max_retries: int = 1) -> ClassificationEngine:
    return ClassificationEngine(
        config=ClassificationConfig(
            openrouter_api_key="test-key",
            model="primary-model",
            fallback_models=["fallback-model"],
            max_retries=max_retries,
        ),
        taxonomy=TaxonomyConfig(),
        client=client,
    )


def test_keyword_matching_uses_configured_groups() -> None:
    matcher = KeywordMatcher([KeywordGroup("festival", ["Kumbh", "Health Camp"])])

    matches = matcher.match("A kumbh health camp opened near the river.")

    assert [match.keyword for match in matches] == ["Kumbh", "Health Camp"]


def test_boolean_rule_evaluator_supports_and_or_not() -> None:
    engine = BooleanRuleEngine([
        BooleanRule("focus", "(Kumbh OR Simhastha) AND (Nashik OR Trimbakeshwar) NOT Crypto")
    ])

    assert engine.evaluate("Kumbh preparations in Nashik")
    assert not engine.evaluate("Kumbh crypto conference in Nashik")


def test_relevance_engine_marks_relevant_article() -> None:
    result = RelevanceEngine(relevance_config()).evaluate(relevant_article())

    assert result.decision == RelevanceDecision.RELEVANT
    assert result.score >= 0.45
    assert "kumbh" in result.matched_keywords
    assert "kumbh_nashik" in result.matched_rules


def test_relevance_engine_filters_irrelevant_article() -> None:
    result = RelevanceEngine(relevance_config()).evaluate(irrelevant_article())

    assert result.decision == RelevanceDecision.IRRELEVANT
    assert result.score < 0.45


def test_classification_engine_returns_validated_result() -> None:
    client = FakeClient([valid_payload()])
    engine = classification_engine(client)

    result = engine.classify(relevant_article())

    assert result.theme == ["crowd_management", "public_safety"]
    assert result.confidence == 0.91
    assert result.observability is not None
    assert result.observability.model == "primary-model"
    assert result.observability.tokens.total_tokens == 30


def test_classification_retries_malformed_json() -> None:
    client = FakeClient(["{not-json", valid_payload()])
    engine = classification_engine(client, max_retries=1)

    result = engine.classify(relevant_article())

    assert result.theme == ["crowd_management", "public_safety"]
    assert len(client.calls) == 2
    assert result.observability is not None
    assert result.observability.retries == 1
    assert result.observability.validation_failures


def test_classification_retries_timeout() -> None:
    client = FakeClient([ClassificationTimeoutError("timeout"), valid_payload()])
    engine = classification_engine(client, max_retries=1)

    result = engine.classify(relevant_article())

    assert result.genre == ["news_report"]
    assert len(client.calls) == 2


def test_classification_uses_fallback_model_after_primary_attempts_fail() -> None:
    client = FakeClient(["{bad", "{bad again", valid_payload()])
    engine = classification_engine(client, max_retries=1)

    result = engine.classify(relevant_article())

    assert result.observability is not None
    assert result.observability.model == "fallback-model"
    assert len(client.calls) == 3


def test_validator_rejects_unknown_taxonomy_values() -> None:
    validator = ResponseValidator(TaxonomyConfig())

    with pytest.raises(ClassificationValidationError):
        validator.validate_json(valid_payload(theme=["hallucinated_theme"]))


def test_validator_rejects_hallucinated_fields() -> None:
    validator = ResponseValidator(TaxonomyConfig())

    with pytest.raises(ClassificationValidationError):
        validator.validate_json(valid_payload(extra_field="nope"))


def test_classification_skips_irrelevant_articles() -> None:
    engine = classification_engine(FakeClient([valid_payload()]))
    relevance = RelevanceEngine(relevance_config()).evaluate(irrelevant_article())

    with pytest.raises(ClassificationSkipped):
        engine.classify(irrelevant_article(), relevance)


def test_relevance_config_loads_expandable_dictionaries_from_file(tmp_path: Path) -> None:
    config_path = tmp_path / "relevance.json"
    config_path.write_text(
        json.dumps(
            {
                "threshold": 0.1,
                "keyword_groups": [{"name": "custom", "keywords": ["Akhada"], "weight": 1.0}],
                "boolean_rules": [{"name": "custom_rule", "expression": "Akhada AND Nashik"}],
                "geography_rules": [{"name": "custom_geo", "aliases": ["Nashik"], "weight": 1.0}],
            }
        ),
        encoding="utf-8",
    )

    config = RelevanceConfig.from_json_file(config_path)
    result = RelevanceEngine(config).evaluate(
        Article(title="Akhada preparations", body_text="Akhada leaders met officials in Nashik.")
    )

    assert result.decision == RelevanceDecision.RELEVANT
    assert result.matched_rules == ["custom_rule"]


def test_relevance_supports_normalized_article_source_and_publication_aliases() -> None:
    @dataclass
    class MinimalNormalizedArticle:
        title: str
        body: str
        source: dict[str, str]
        publication_date: str

    config = relevance_config()
    article = MinimalNormalizedArticle(
        title="Kumbh plan in Nashik",
        body="Police crowd preparations for the Kumbh near Ramkund.",
        source={"id": "gov.example"},
        publication_date=datetime.now(timezone.utc).isoformat(),
    )

    result = RelevanceEngine(config).evaluate(article)

    assert result.decision == RelevanceDecision.RELEVANT
    assert "source priority contributed to score" in result.reasons


def test_prompt_builder_rejects_unknown_prompt_versions() -> None:
    builder = PromptBuilder(TaxonomyConfig(), prompt_version="missing-version")

    with pytest.raises(PromptTemplateError):
        builder.build(relevant_article())


def test_pipeline_does_not_classify_irrelevant_article() -> None:
    fake_client = FakeClient([valid_payload()])
    pipeline = IntelligencePipeline(
        relevance_engine=RelevanceEngine(relevance_config()),
        classification_engine=classification_engine(fake_client),
    )

    result = pipeline.process(irrelevant_article())

    assert result.classification is None
    assert fake_client.calls == []


def test_pipeline_classifies_relevant_article() -> None:
    fake_client = FakeClient([valid_payload()])
    pipeline = IntelligencePipeline(
        relevance_engine=RelevanceEngine(relevance_config()),
        classification_engine=classification_engine(fake_client),
    )

    result = pipeline.process(relevant_article())

    assert result.relevance.decision == RelevanceDecision.RELEVANT
    assert result.classification is not None
