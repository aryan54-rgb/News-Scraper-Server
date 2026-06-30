"""Deterministic relevance engine for pre-LLM filtering."""
from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timezone
from typing import Any, Optional

from .boolean_rules import BooleanRuleEngine
from .keywords import KeywordMatcher
from .models import RelevanceConfig, RelevanceDecision, RelevanceResult
from .text import article_publication_date, article_source, article_text, normalize_text

logger = logging.getLogger(__name__)


class ScoringEngine:
    def __init__(self, config: RelevanceConfig) -> None:
        self.config = config

    def score(
        self,
        *,
        keyword_score: float,
        rule_score: float,
        geography_score: float,
        source_score: float,
        publication_score: float,
    ) -> float:
        weighted = (
            self.config.keyword_weight * keyword_score
            + self.config.boolean_rule_weight * rule_score
            + self.config.geography_weight * geography_score
            + self.config.source_weight * source_score
            + self.config.publication_time_weight * publication_score
        )
        max_weight = (
            self.config.keyword_weight
            + self.config.boolean_rule_weight
            + self.config.geography_weight
            + self.config.source_weight
            + self.config.publication_time_weight
        )
        if max_weight <= 0:
            return 0.0
        return max(0.0, min(1.0, weighted / max_weight))


class RelevanceEngine:
    def __init__(self, config: Optional[RelevanceConfig] = None) -> None:
        self.config = config or RelevanceConfig.from_env()
        self.keyword_matcher = KeywordMatcher(self.config.keyword_groups)
        self.boolean_rule_engine = BooleanRuleEngine(self.config.boolean_rules)
        self.scoring_engine = ScoringEngine(self.config)

    def evaluate(self, article: Any) -> RelevanceResult:
        started = time.perf_counter()
        text = article_text(article)
        keyword_matches = self.keyword_matcher.match(text)
        rule_matches = self.boolean_rule_engine.evaluate(text)
        geography_matches = self._geography_matches(text)
        source_score = self._source_score(article)
        publication_score = self._publication_score(article)

        keyword_score = min(1.0, sum(self.keyword_matcher.grouped_scores(keyword_matches).values()) / 3.0)
        rule_score = min(1.0, sum(match.weight for match in rule_matches))
        geography_score = min(1.0, sum(weight for _, weight in geography_matches) / 2.0)
        score = self.scoring_engine.score(
            keyword_score=keyword_score,
            rule_score=rule_score,
            geography_score=geography_score,
            source_score=source_score,
            publication_score=publication_score,
        )

        reasons: list[str] = []
        if keyword_matches:
            reasons.append("matched configured keyword groups")
        if rule_matches:
            reasons.append("matched configured boolean rules")
        if geography_matches:
            reasons.append("matched priority geography")
        if source_score > 0:
            reasons.append("source priority contributed to score")
        if publication_score > 0:
            reasons.append("publication date is within configured window")
        if not reasons:
            reasons.append("no deterministic relevance signals matched")

        result = RelevanceResult(
            decision=RelevanceDecision.RELEVANT if score >= self.config.threshold else RelevanceDecision.IRRELEVANT,
            score=score,
            matched_keywords=[match.keyword for match in keyword_matches],
            matched_rules=[match.name for match in rule_matches],
            matched_entities=[],
            reasons=reasons,
            processing_time_ms=(time.perf_counter() - started) * 1000,
        )
        logger.info(
            "relevance_evaluated",
            extra={
                "decision": result.decision.value,
                "score": round(result.score, 4),
                "keyword_count": len(keyword_matches),
                "rule_count": len(rule_matches),
                "geography_count": len(geography_matches),
                "processing_time_ms": round(result.processing_time_ms, 2),
            },
        )
        return result

    def _geography_matches(self, text: str) -> list[tuple[str, float]]:
        matches: list[tuple[str, float]] = []
        for rule in self.config.geography_rules:
            if any(self._contains_phrase(text, alias) for alias in rule.aliases):
                matches.append((rule.name, rule.weight))
        return matches

    @staticmethod
    def _contains_phrase(text: str, phrase: str) -> bool:
        needle = normalize_text(phrase)
        if not needle:
            return False
        return bool(re.search(r"(?<!\w)" + re.escape(needle) + r"(?!\w)", text))

    def _source_score(self, article: Any) -> float:
        source = article_source(article)
        if not source:
            return 0.0
        return max(0.0, min(1.0, self.config.source_priorities.get(source, 0.0)))

    def _publication_score(self, article: Any) -> float:
        published_at = article_publication_date(article)
        if not published_at:
            return 0.5 if self.config.allow_historic_without_date else 0.0
        if published_at.tzinfo is None:
            published_at = published_at.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        age_days = max(0.0, (now - published_at).total_seconds() / 86400)
        if age_days > self.config.publication_window_days:
            return 0.0
        if self.config.publication_window_days <= 0:
            return 1.0
        return 1.0 - (age_days / self.config.publication_window_days)
