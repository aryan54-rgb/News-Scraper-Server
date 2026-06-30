"""Duplicate detector orchestration."""
from __future__ import annotations

import logging
import time
from datetime import timezone
from typing import Any, Optional

from .fingerprints import FingerprintGenerator
from .models import (
    CandidateQuery,
    DuplicateAnalysis,
    DuplicateCandidate,
    DuplicateDetectionConfig,
    DuplicateScores,
    DuplicateStatus,
)
from .normalization import (
    article_url,
    extract_guid,
    normalize_content,
    normalize_title,
    source_identity,
)
from .registry import DuplicateRegistry
from .similarity import SimilarityEngine

logger = logging.getLogger(__name__)


class DuplicateDetector:
    def __init__(
        self,
        registry: DuplicateRegistry,
        *,
        config: Optional[DuplicateDetectionConfig] = None,
        fingerprint_generator: Optional[FingerprintGenerator] = None,
        similarity_engine: Optional[SimilarityEngine] = None,
    ) -> None:
        self.registry = registry
        self.config = config or DuplicateDetectionConfig.from_env()
        self.fingerprint_generator = fingerprint_generator or FingerprintGenerator()
        self.similarity_engine = similarity_engine or SimilarityEngine()

    def analyze(self, article: Any) -> DuplicateAnalysis:
        started = time.perf_counter()
        fingerprints = self.fingerprint_generator.generate(article)
        canonical_url = article_url(article)
        guid = extract_guid(article)
        query = CandidateQuery(
            canonical_url=canonical_url,
            guid=guid,
            fingerprints=fingerprints,
            published_after=self._published_after(article),
            max_candidates=self.config.max_candidates,
        )
        candidates = list(self.registry.find_candidates(query))

        best = DuplicateAnalysis(
            status=DuplicateStatus.NEW_DOCUMENT,
            confidence=0.0,
            reasons=["no duplicate candidate exceeded configured thresholds"],
            candidate_count=len(candidates),
        )

        for candidate in candidates:
            candidate_fingerprints = candidate.fingerprints or self.fingerprint_generator.generate(
                candidate.article
            )
            exact = self._evaluate_exact(
                article,
                candidate,
                canonical_url,
                guid,
                fingerprints,
                candidate_fingerprints,
            )
            if exact:
                best = exact
                break

            analysis = self._score_candidate(article, candidate, fingerprints, candidate_fingerprints)
            if analysis.confidence > best.confidence:
                best = analysis

        best.candidate_count = len(candidates)
        best.detection_time_ms = (time.perf_counter() - started) * 1000
        logger.info(
            "duplicate_detection_completed",
            extra={
                "detection_time_ms": round(best.detection_time_ms, 2),
                "strategy_used": best.strategy_used,
                "match_confidence": round(best.confidence, 4),
                "scores": best.scores.to_dict(),
                "candidate_count": len(candidates),
                "status": best.status.value,
            },
        )
        return best

    def _evaluate_exact(
        self,
        article: Any,
        candidate: DuplicateCandidate,
        canonical_url: Optional[str],
        guid: Optional[str],
        fingerprints: Any,
        candidate_fingerprints: Any,
    ) -> Optional[DuplicateAnalysis]:
        candidate_url = article_url(candidate.article)
        if canonical_url and candidate_url and canonical_url == candidate_url:
            return DuplicateAnalysis(
                status=DuplicateStatus.EXACT_DUPLICATE,
                matched_document_id=candidate.document_id,
                confidence=1.0,
                reasons=["canonical URL matched an existing document"],
                scores=DuplicateScores(canonical_url=1.0),
                strategy_used="canonical_url",
            )

        candidate_guid = candidate.guid or extract_guid(candidate.article)
        if guid and candidate_guid and guid == candidate_guid:
            return DuplicateAnalysis(
                status=DuplicateStatus.EXACT_DUPLICATE,
                matched_document_id=candidate.document_id,
                confidence=0.99,
                reasons=["GUID matched an existing document"],
                scores=DuplicateScores(guid=1.0),
                strategy_used="guid",
            )

        if fingerprints.content and fingerprints.content == candidate_fingerprints.content:
            same_source = self._same_source(article, candidate)
            return DuplicateAnalysis(
                status=DuplicateStatus.EXACT_DUPLICATE if same_source else DuplicateStatus.NEAR_DUPLICATE,
                matched_document_id=candidate.document_id,
                confidence=0.98 if same_source else 0.94,
                reasons=[
                    "content fingerprint matched exactly"
                    if same_source
                    else "content fingerprint matched exactly across different sources"
                ],
                scores=DuplicateScores(fingerprint=1.0, content_similarity=1.0),
                strategy_used="content_fingerprint",
            )
        return None

    def _score_candidate(
        self,
        article: Any,
        candidate: DuplicateCandidate,
        fingerprints: Any,
        candidate_fingerprints: Any,
    ) -> DuplicateAnalysis:
        title_left = normalize_title(getattr(article, "title", None))
        title_right = normalize_title(getattr(candidate.article, "title", None))
        content_left = normalize_content(
            getattr(article, "body_text", None) or getattr(article, "content_plain", None),
            getattr(article, "paragraphs", None),
        )
        content_right = normalize_content(
            getattr(candidate.article, "body_text", None)
            or getattr(candidate.article, "content_plain", None),
            getattr(candidate.article, "paragraphs", None),
        )
        title_similarity = self.similarity_engine.title_similarity(title_left, title_right)
        content_similarity = self.similarity_engine.content_similarity(content_left, content_right)
        publication_time = self._publication_time_score(article, candidate.article)
        source_similarity = 1.0 if self._same_source(article, candidate) else 0.65
        fingerprint_score = self._fingerprint_score(fingerprints, candidate_fingerprints)

        confidence = (
            0.12 * title_similarity
            + 0.58 * content_similarity
            + 0.12 * publication_time
            + 0.08 * source_similarity
            + 0.10 * fingerprint_score
        )
        confidence += self.config.same_source_bonus if source_similarity == 1.0 else 0.0
        confidence -= self.config.different_source_penalty if source_similarity < 1.0 else 0.0
        confidence = max(0.0, min(1.0, confidence))

        scores = DuplicateScores(
            title_similarity=title_similarity,
            content_similarity=content_similarity,
            publication_time=publication_time,
            source_similarity=source_similarity,
            fingerprint=fingerprint_score,
        )
        reasons = self._reasons(scores)
        status = self._status_for(confidence, scores)
        return DuplicateAnalysis(
            status=status,
            matched_document_id=candidate.document_id if status != DuplicateStatus.NEW_DOCUMENT else None,
            confidence=confidence if status != DuplicateStatus.NEW_DOCUMENT else 0.0,
            reasons=reasons if status != DuplicateStatus.NEW_DOCUMENT else [
                "candidate did not exceed configured thresholds"
            ],
            scores=scores,
            strategy_used="similarity_scoring",
        )

    def _status_for(self, confidence: float, scores: DuplicateScores) -> DuplicateStatus:
        if (
            confidence >= self.config.exact_duplicate_threshold
            and scores.content_similarity >= 0.97
            and scores.title_similarity >= 0.95
            and scores.source_similarity >= 1.0
        ):
            return DuplicateStatus.EXACT_DUPLICATE
        if (
            confidence >= self.config.near_duplicate_threshold
            or scores.content_similarity >= self.config.content_similarity_threshold
            and scores.title_similarity >= self.config.title_similarity_threshold
        ):
            return DuplicateStatus.NEAR_DUPLICATE
        if confidence >= self.config.possible_duplicate_threshold:
            return DuplicateStatus.POSSIBLE_DUPLICATE
        return DuplicateStatus.NEW_DOCUMENT

    def _reasons(self, scores: DuplicateScores) -> list[str]:
        reasons: list[str] = []
        if scores.title_similarity >= self.config.title_similarity_threshold:
            reasons.append("normalized title similarity exceeded threshold")
        if scores.content_similarity >= self.config.content_similarity_threshold:
            reasons.append("cleaned content similarity exceeded threshold")
        if scores.publication_time > 0:
            reasons.append("publication times were within configured proximity window")
        if scores.source_similarity < 1.0:
            reasons.append("match came from a different source")
        if not reasons:
            reasons.append("weak similarity across duplicate signals")
        return reasons

    def _publication_time_score(self, left: Any, right: Any) -> float:
        left_dt = getattr(left, "published_at", None)
        right_dt = getattr(right, "published_at", None)
        if not left_dt or not right_dt:
            return 0.0
        if left_dt.tzinfo is None:
            left_dt = left_dt.replace(tzinfo=timezone.utc)
        if right_dt.tzinfo is None:
            right_dt = right_dt.replace(tzinfo=timezone.utc)
        delta = abs(left_dt - right_dt)
        window = self.config.publication_window
        if window.total_seconds() <= 0 or delta > window:
            return 0.0
        return 1.0 - (delta.total_seconds() / window.total_seconds())

    def _published_after(self, article: Any) -> Optional[Any]:
        published_at = getattr(article, "published_at", None)
        if not published_at:
            return None
        return published_at - self.config.candidate_lookback

    @staticmethod
    def _fingerprint_score(left: Any, right: Any) -> float:
        if left.combined and left.combined == right.combined:
            return 1.0
        if left.title and left.title == right.title:
            return 0.45
        return 0.0

    @staticmethod
    def _same_source(article: Any, candidate: DuplicateCandidate) -> bool:
        left = source_identity(article)
        right = source_identity(candidate) or source_identity(candidate.article)
        return bool(left and right and left == right)
