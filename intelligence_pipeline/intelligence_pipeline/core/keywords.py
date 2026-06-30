"""Grouped deterministic keyword matching."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Tuple

from .models import KeywordGroup
from .text import normalize_text


@dataclass
class KeywordMatch:
    group: str
    keyword: str
    weight: float


class KeywordMatcher:
    def __init__(self, groups: List[KeywordGroup]) -> None:
        self.groups = groups

    def match(self, text: str) -> List[KeywordMatch]:
        normalized = normalize_text(text)
        matches: List[KeywordMatch] = []
        seen: set[Tuple[str, str]] = set()
        for group in self.groups:
            for keyword in group.keywords:
                needle = normalize_text(keyword)
                if not needle:
                    continue
                pattern = r"(?<!\w)" + re.escape(needle) + r"(?!\w)"
                if re.search(pattern, normalized):
                    key = (group.name, needle)
                    if key in seen:
                        continue
                    seen.add(key)
                    matches.append(KeywordMatch(group.name, keyword, group.weight))
        return matches

    @staticmethod
    def grouped_scores(matches: List[KeywordMatch]) -> Dict[str, float]:
        scores: Dict[str, float] = {}
        for match in matches:
            scores[match.group] = max(scores.get(match.group, 0.0), match.weight)
        return scores
