"""Core models for the Duplicate Detection Engine.

The engine is deliberately storage-agnostic: callers provide a registry that
can read recent candidates, and the detector returns an analysis object. It
never writes duplicate state back to a database.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional


class DuplicateStatus(str, Enum):
    NEW_DOCUMENT = "NEW_DOCUMENT"
    EXACT_DUPLICATE = "EXACT_DUPLICATE"
    NEAR_DUPLICATE = "NEAR_DUPLICATE"
    POSSIBLE_DUPLICATE = "POSSIBLE_DUPLICATE"


@dataclass(frozen=True)
class FingerprintSet:
    canonical_url: Optional[str] = None
    title: Optional[str] = None
    content: Optional[str] = None
    combined: Optional[str] = None
    algorithm: str = "sha256:v1"


@dataclass
class DuplicateScores:
    canonical_url: float = 0.0
    guid: float = 0.0
    title_similarity: float = 0.0
    content_similarity: float = 0.0
    publication_time: float = 0.0
    source_similarity: float = 0.0
    fingerprint: float = 0.0

    def to_dict(self) -> Dict[str, float]:
        return {
            "canonical_url": round(self.canonical_url, 4),
            "guid": round(self.guid, 4),
            "title_similarity": round(self.title_similarity, 4),
            "content_similarity": round(self.content_similarity, 4),
            "publication_time": round(self.publication_time, 4),
            "source_similarity": round(self.source_similarity, 4),
            "fingerprint": round(self.fingerprint, 4),
        }


@dataclass
class DuplicateAnalysis:
    status: DuplicateStatus
    matched_document_id: Optional[str] = None
    confidence: float = 0.0
    reasons: List[str] = field(default_factory=list)
    scores: DuplicateScores = field(default_factory=DuplicateScores)
    strategy_used: Optional[str] = None
    candidate_count: int = 0
    detection_time_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "matched_document_id": self.matched_document_id,
            "confidence": round(self.confidence, 4),
            "reasons": self.reasons,
            "scores": self.scores.to_dict(),
            "strategy_used": self.strategy_used,
            "candidate_count": self.candidate_count,
            "detection_time_ms": round(self.detection_time_ms, 2),
        }


@dataclass
class DuplicateCandidate:
    document_id: str
    article: Any
    source_id: Optional[str] = None
    source_name: Optional[str] = None
    source_domain: Optional[str] = None
    guid: Optional[str] = None
    fingerprints: Optional[FingerprintSet] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DuplicateDetectionConfig:
    exact_duplicate_threshold: float = 0.97
    near_duplicate_threshold: float = 0.86
    possible_duplicate_threshold: float = 0.68
    title_similarity_threshold: float = 0.9
    content_similarity_threshold: float = 0.82
    publication_window_hours: int = 72
    candidate_lookback_days: int = 14
    same_source_bonus: float = 0.05
    different_source_penalty: float = 0.04
    max_candidates: int = 500

    @property
    def publication_window(self) -> timedelta:
        return timedelta(hours=self.publication_window_hours)

    @property
    def candidate_lookback(self) -> timedelta:
        return timedelta(days=self.candidate_lookback_days)

    @classmethod
    def from_env(cls, prefix: str = "DEDUP_") -> "DuplicateDetectionConfig":
        config = cls()
        fields = {
            "exact_duplicate_threshold": float,
            "near_duplicate_threshold": float,
            "possible_duplicate_threshold": float,
            "title_similarity_threshold": float,
            "content_similarity_threshold": float,
            "publication_window_hours": int,
            "candidate_lookback_days": int,
            "same_source_bonus": float,
            "different_source_penalty": float,
            "max_candidates": int,
        }
        for field_name, caster in fields.items():
            env_name = f"{prefix}{field_name.upper()}"
            value = os.getenv(env_name)
            if value is None:
                continue
            setattr(config, field_name, caster(value))
        config.validate()
        return config

    def validate(self) -> None:
        thresholds = [
            self.exact_duplicate_threshold,
            self.near_duplicate_threshold,
            self.possible_duplicate_threshold,
            self.title_similarity_threshold,
            self.content_similarity_threshold,
        ]
        if any(value < 0 or value > 1 for value in thresholds):
            raise ValueError("Duplicate thresholds must be between 0.0 and 1.0")
        if not (
            self.exact_duplicate_threshold
            >= self.near_duplicate_threshold
            >= self.possible_duplicate_threshold
        ):
            raise ValueError("Thresholds must be ordered exact >= near >= possible")
        if self.publication_window_hours < 0 or self.candidate_lookback_days < 0:
            raise ValueError("Time windows must be non-negative")
        if self.max_candidates <= 0:
            raise ValueError("max_candidates must be positive")


@dataclass(frozen=True)
class CandidateQuery:
    canonical_url: Optional[str]
    guid: Optional[str]
    fingerprints: FingerprintSet
    published_after: Optional[datetime]
    max_candidates: int
