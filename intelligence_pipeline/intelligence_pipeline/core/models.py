"""Shared models and configuration for the intelligence pipeline."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


class RelevanceDecision(str, Enum):
    RELEVANT = "RELEVANT"
    IRRELEVANT = "IRRELEVANT"


@dataclass
class RelevanceResult:
    decision: RelevanceDecision
    score: float
    matched_keywords: List[str] = field(default_factory=list)
    matched_rules: List[str] = field(default_factory=list)
    matched_entities: List[str] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)
    processing_time_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision": self.decision.value,
            "score": round(self.score, 4),
            "matched_keywords": self.matched_keywords,
            "matched_rules": self.matched_rules,
            "matched_entities": self.matched_entities,
            "reason": self.reasons,
            "processing_time_ms": round(self.processing_time_ms, 2),
        }


@dataclass(frozen=True)
class KeywordGroup:
    name: str
    keywords: List[str]
    weight: float = 1.0


@dataclass(frozen=True)
class BooleanRule:
    name: str
    expression: str
    weight: float = 1.0


@dataclass(frozen=True)
class GeographyRule:
    name: str
    aliases: List[str]
    weight: float = 1.0


@dataclass
class RelevanceConfig:
    threshold: float = 0.55
    keyword_weight: float = 0.35
    boolean_rule_weight: float = 0.25
    geography_weight: float = 0.18
    source_weight: float = 0.12
    publication_time_weight: float = 0.10
    publication_window_days: int = 30
    allow_historic_without_date: bool = True
    source_priorities: Dict[str, float] = field(default_factory=dict)
    keyword_groups: List[KeywordGroup] = field(default_factory=lambda: [
        KeywordGroup("core_kumbh", ["simhastha", "kumbh", "godavari", "ramkund", "akhada", "pilgrim"]),
        KeywordGroup("operations", ["crowd", "traffic", "health camp", "emergency", "disaster"]),
        KeywordGroup("institutions", ["administration", "police", "temple", "river", "festival"]),
    ])
    boolean_rules: List[BooleanRule] = field(default_factory=lambda: [
        BooleanRule(
            "kumbh_nashik_focus",
            "(Kumbh OR Simhastha) AND (Nashik OR Trimbakeshwar) NOT (Crypto) NOT (Movie)",
            1.0,
        ),
    ])
    geography_rules: List[GeographyRule] = field(default_factory=lambda: [
        GeographyRule("nashik", ["nashik", "nasik"], 1.0),
        GeographyRule("trimbakeshwar", ["trimbakeshwar", "tryambakeshwar"], 1.0),
        GeographyRule("godavari", ["godavari", "ramkund"], 0.8),
    ])

    @classmethod
    def from_env(cls, prefix: str = "INTEL_RELEVANCE_") -> "RelevanceConfig":
        config_path = os.getenv(f"{prefix}CONFIG_PATH")
        config = cls.from_json_file(config_path) if config_path else cls()
        for field_name, caster in {
            "threshold": float,
            "keyword_weight": float,
            "boolean_rule_weight": float,
            "geography_weight": float,
            "source_weight": float,
            "publication_time_weight": float,
            "publication_window_days": int,
            "allow_historic_without_date": lambda v: v.lower() in {"1", "true", "yes"},
        }.items():
            value = os.getenv(f"{prefix}{field_name.upper()}")
            if value is not None:
                setattr(config, field_name, caster(value))
        config.validate()
        return config

    @classmethod
    def from_json_file(cls, path: str | os.PathLike[str]) -> "RelevanceConfig":
        with Path(path).open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        return cls.from_mapping(data)

    @classmethod
    def from_mapping(cls, data: Dict[str, Any]) -> "RelevanceConfig":
        payload = dict(data)
        if "keyword_groups" in payload:
            payload["keyword_groups"] = [KeywordGroup(**item) for item in payload["keyword_groups"]]
        if "boolean_rules" in payload:
            payload["boolean_rules"] = [BooleanRule(**item) for item in payload["boolean_rules"]]
        if "geography_rules" in payload:
            payload["geography_rules"] = [GeographyRule(**item) for item in payload["geography_rules"]]
        config = cls(**payload)
        config.validate()
        return config

    def validate(self) -> None:
        if not 0 <= self.threshold <= 1:
            raise ValueError("Relevance threshold must be between 0.0 and 1.0")
        weights = [
            self.keyword_weight,
            self.boolean_rule_weight,
            self.geography_weight,
            self.source_weight,
            self.publication_time_weight,
        ]
        if any(weight < 0 for weight in weights):
            raise ValueError("Relevance weights must be non-negative")
        if self.publication_window_days < 0:
            raise ValueError("publication_window_days must be non-negative")


@dataclass(frozen=True)
class TaxonomyConfig:
    version: str = "kumbh-intelligence-v1"
    themes: List[str] = field(default_factory=lambda: [
        "crowd_management",
        "traffic_transport",
        "public_health",
        "public_safety",
        "administration",
        "religious_activity",
        "infrastructure",
        "environment",
    ])
    genres: List[str] = field(default_factory=lambda: [
        "news_report",
        "government_notice",
        "advisory",
        "analysis",
        "feature",
    ])
    event_types: List[str] = field(default_factory=lambda: [
        "announcement",
        "incident",
        "preparedness",
        "service_update",
        "policy_decision",
        "public_advisory",
    ])
    stakeholder_types: List[str] = field(default_factory=lambda: [
        "government",
        "police",
        "health",
        "religious_body",
        "transport",
        "public",
        "other",
    ])
    geographies: List[str] = field(default_factory=lambda: [
        "nashik",
        "trimbakeshwar",
        "godavari",
        "ramkund",
        "maharashtra",
        "other",
    ])
    outcomes: List[str] = field(default_factory=lambda: [
        "announcement",
        "deployment",
        "restriction",
        "funding",
        "advisory",
        "service_change",
        "risk_report",
    ])


@dataclass
class ClassificationConfig:
    openrouter_api_key: Optional[str] = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    model: str = "openrouter/auto"
    fallback_models: List[str] = field(default_factory=list)
    timeout_seconds: float = 30.0
    max_retries: int = 2
    retry_backoff_seconds: float = 0.0
    temperature: float = 0.0
    max_tokens: int = 1200
    prompt_version: str = "classification-v1"
    app_name: Optional[str] = None
    site_url: Optional[str] = None

    @classmethod
    def from_env(cls, prefix: str = "OPENROUTER_") -> "ClassificationConfig":
        config_path = os.getenv("INTEL_CLASSIFICATION_CONFIG_PATH") or os.getenv(f"{prefix}CONFIG_PATH")
        config = cls.from_json_file(config_path) if config_path else cls()
        if os.getenv(f"{prefix}API_KEY") is not None:
            config.openrouter_api_key = os.getenv(f"{prefix}API_KEY")
        if os.getenv(f"{prefix}BASE_URL") is not None:
            config.openrouter_base_url = os.getenv(f"{prefix}BASE_URL", config.openrouter_base_url)
        if os.getenv(f"{prefix}MODEL") is not None:
            config.model = os.getenv(f"{prefix}MODEL", config.model)
        if os.getenv(f"{prefix}APP_NAME") is not None:
            config.app_name = os.getenv(f"{prefix}APP_NAME")
        if os.getenv(f"{prefix}SITE_URL") is not None:
            config.site_url = os.getenv(f"{prefix}SITE_URL")
        fallbacks = os.getenv(f"{prefix}FALLBACK_MODELS")
        if fallbacks:
            config.fallback_models = [item.strip() for item in fallbacks.split(",") if item.strip()]
        for field_name, caster in {
            "timeout_seconds": float,
            "max_retries": int,
            "retry_backoff_seconds": float,
            "temperature": float,
            "max_tokens": int,
        }.items():
            value = os.getenv(f"{prefix}{field_name.upper()}")
            if value is not None:
                setattr(config, field_name, caster(value))
        prompt_version = os.getenv("INTEL_PROMPT_VERSION")
        if prompt_version:
            config.prompt_version = prompt_version
        config.validate()
        return config

    @classmethod
    def from_json_file(cls, path: str | os.PathLike[str]) -> "ClassificationConfig":
        with Path(path).open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        return cls.from_mapping(data)

    @classmethod
    def from_mapping(cls, data: Dict[str, Any]) -> "ClassificationConfig":
        config = cls(**dict(data))
        config.validate()
        return config

    def validate(self) -> None:
        if self.max_retries < 0:
            raise ValueError("max_retries must be non-negative")
        if self.retry_backoff_seconds < 0:
            raise ValueError("retry_backoff_seconds must be non-negative")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if not 0 <= self.temperature <= 2:
            raise ValueError("temperature must be between 0 and 2")


@dataclass
class PromptBundle:
    version: str
    system_prompt: str
    user_prompt: str


@dataclass
class ModelUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass
class ClassificationObservability:
    model: str
    latency_ms: float = 0.0
    tokens: ModelUsage = field(default_factory=ModelUsage)
    retries: int = 0
    prompt_version: str = ""
    response_size_bytes: int = 0
    validation_failures: List[str] = field(default_factory=list)
    processing_time_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model": self.model,
            "latency_ms": round(self.latency_ms, 2),
            "tokens": vars(self.tokens),
            "retries": self.retries,
            "prompt_version": self.prompt_version,
            "response_size_bytes": self.response_size_bytes,
            "validation_failures": self.validation_failures,
            "processing_time_ms": round(self.processing_time_ms, 2),
        }


@dataclass
class ClassificationResult:
    theme: List[str]
    genre: List[str]
    event_type: List[str]
    stakeholders: List[Dict[str, Any]]
    geography: List[str]
    outcomes: List[str]
    evidence_snippets: List[str]
    confidence: float
    rationale: Optional[str] = None
    observability: Optional[ClassificationObservability] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "theme": self.theme,
            "genre": self.genre,
            "event_type": self.event_type,
            "stakeholders": self.stakeholders,
            "geography": self.geography,
            "outcomes": self.outcomes,
            "evidence_snippets": self.evidence_snippets,
            "confidence": round(self.confidence, 4),
            "rationale": self.rationale,
            "observability": self.observability.to_dict() if self.observability else None,
        }


@dataclass
class IntelligencePipelineResult:
    relevance: RelevanceResult
    classification: Optional[ClassificationResult] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "relevance": self.relevance.to_dict(),
            "classification": self.classification.to_dict() if self.classification else None,
        }
