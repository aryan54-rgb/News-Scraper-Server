"""Pluggable similarity algorithms for duplicate detection."""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from typing import Protocol

_TOKEN_RE = re.compile(r"\b\w+\b", re.UNICODE)


class SimilarityAlgorithm(Protocol):
    name: str

    def compare(self, left: str, right: str) -> float:
        ...


class SequenceSimilarity:
    name = "sequence_matcher"

    def compare(self, left: str, right: str) -> float:
        if not left or not right:
            return 0.0
        return difflib.SequenceMatcher(None, left, right, autojunk=False).ratio()


class TokenJaccardSimilarity:
    name = "token_jaccard"

    def compare(self, left: str, right: str) -> float:
        left_tokens = set(_TOKEN_RE.findall(left))
        right_tokens = set(_TOKEN_RE.findall(right))
        if not left_tokens or not right_tokens:
            return 0.0
        return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


class HybridContentSimilarity:
    name = "hybrid_sequence_token"

    def __init__(self) -> None:
        self.sequence = SequenceSimilarity()
        self.tokens = TokenJaccardSimilarity()

    def compare(self, left: str, right: str) -> float:
        token_score = self.tokens.compare(left, right)
        sequence_score = self.sequence.compare(left, right)
        return (0.55 * token_score) + (0.45 * sequence_score)


@dataclass
class SimilarityEngine:
    title_algorithm: SimilarityAlgorithm = field(default_factory=SequenceSimilarity)
    content_algorithm: SimilarityAlgorithm = field(default_factory=HybridContentSimilarity)

    def title_similarity(self, left: str, right: str) -> float:
        return self._bounded(self.title_algorithm.compare(left, right))

    def content_similarity(self, left: str, right: str) -> float:
        return self._bounded(self.content_algorithm.compare(left, right))

    @staticmethod
    def _bounded(value: float) -> float:
        return max(0.0, min(1.0, value))
