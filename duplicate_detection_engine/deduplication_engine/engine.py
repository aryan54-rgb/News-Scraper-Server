"""Convenience re-export module for embedding the Duplicate Detection Engine."""
from . import (
    DuplicateAnalysis,
    DuplicateCandidate,
    DuplicateDetectionConfig,
    DuplicateDetector,
    DuplicateRegistry,
    DuplicateScores,
    DuplicateStatus,
    FingerprintGenerator,
    FingerprintSet,
    InMemoryDuplicateRegistry,
    SimilarityAlgorithm,
    SimilarityEngine,
)

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
