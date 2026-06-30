"""Duplicate Detection Engine public package."""
from .core.detector import DuplicateDetector
from .core.fingerprints import FingerprintGenerator
from .core.models import (
    DuplicateAnalysis,
    DuplicateCandidate,
    DuplicateDetectionConfig,
    DuplicateScores,
    DuplicateStatus,
    FingerprintSet,
)
from .core.registry import DuplicateRegistry, InMemoryDuplicateRegistry
from .core.similarity import SimilarityAlgorithm, SimilarityEngine

__all__ = [
    "DuplicateAnalysis",
    "DuplicateCandidate",
    "DuplicateDetectionConfig",
    "DuplicateDetector",
    "DuplicateRegistry",
    "DuplicateScores",
    "DuplicateStatus",
    "FingerprintGenerator",
    "FingerprintSet",
    "InMemoryDuplicateRegistry",
    "SimilarityAlgorithm",
    "SimilarityEngine",
]
