"""Read-only candidate registry interface for duplicate detection."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Protocol, Sequence

from .models import CandidateQuery, DuplicateCandidate


class DuplicateRegistry(Protocol):
    def find_candidates(self, query: CandidateQuery) -> Sequence[DuplicateCandidate]:
        """Return recent candidate documents without mutating storage."""
        ...


@dataclass
class InMemoryDuplicateRegistry:
    candidates: List[DuplicateCandidate] = field(default_factory=list)

    def find_candidates(self, query: CandidateQuery) -> Sequence[DuplicateCandidate]:
        matched: List[DuplicateCandidate] = []
        for candidate in self.candidates:
            article = candidate.article
            published_at = getattr(article, "published_at", None)
            if query.published_after and published_at and published_at < query.published_after:
                continue
            matched.append(candidate)
            if len(matched) >= query.max_candidates:
                break
        return matched
