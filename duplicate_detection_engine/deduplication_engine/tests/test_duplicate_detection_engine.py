from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from deduplication_engine.core.detector import DuplicateDetector  # noqa: E402
from deduplication_engine.core.fingerprints import FingerprintGenerator  # noqa: E402
from deduplication_engine.core.models import (  # noqa: E402
    DuplicateCandidate,
    DuplicateDetectionConfig,
    DuplicateStatus,
)
from deduplication_engine.core.normalization import normalize_canonical_url, normalize_title  # noqa: E402
from deduplication_engine.core.registry import InMemoryDuplicateRegistry  # noqa: E402
from deduplication_engine.core.similarity import SimilarityEngine  # noqa: E402


@dataclass
class Article:
    url: str
    canonical_url: str | None = None
    title: str | None = None
    subtitle: str | None = None
    authors: list[str] = field(default_factory=list)
    published_at: datetime | None = None
    body_text: str | None = None
    paragraphs: list[str] = field(default_factory=list)
    word_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    json_ld: list[dict[str, Any]] = field(default_factory=list)


BASE_TIME = datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc)


def article(
    *,
    url: str = "https://daily.example.com/news/crowd-plan",
    canonical_url: str | None = "https://daily.example.com/news/crowd-plan",
    title: str = "Officials Announce New Crowd Management Plan",
    body: str | None = None,
    source_id: str = "daily",
    published_at: datetime = BASE_TIME,
    guid: str | None = None,
) -> Article:
    body = body or (
        "City officials announced a new crowd management plan for the upcoming "
        "festival. The plan adds temporary holding areas, extra transport lanes, "
        "and real time monitoring teams at major intersections. Police said the "
        "changes are intended to reduce congestion during peak arrival hours."
    )
    metadata: dict[str, Any] = {"source_id": source_id}
    if guid:
        metadata["guid"] = guid
    return Article(
        url=url,
        canonical_url=canonical_url,
        title=title,
        published_at=published_at,
        body_text=body,
        paragraphs=body.split(". "),
        word_count=len(body.split()),
        metadata=metadata,
    )


def detector_with(candidates: list[DuplicateCandidate]) -> DuplicateDetector:
    return DuplicateDetector(
        InMemoryDuplicateRegistry(candidates),
        config=DuplicateDetectionConfig(
            exact_duplicate_threshold=0.97,
            near_duplicate_threshold=0.86,
            possible_duplicate_threshold=0.60,
        ),
    )


def candidate(document_id: str, existing: Article, source_id: str = "daily") -> DuplicateCandidate:
    return DuplicateCandidate(document_id=document_id, article=existing, source_id=source_id)


def test_same_canonical_url_is_exact_duplicate() -> None:
    existing = article(url="https://daily.example.com/news/crowd-plan?utm_source=rss")
    new = article(url="https://daily.example.com/news/crowd-plan?utm_campaign=social")

    analysis = detector_with([candidate("doc-1", existing)]).analyze(new)

    assert analysis.status == DuplicateStatus.EXACT_DUPLICATE
    assert analysis.matched_document_id == "doc-1"
    assert analysis.confidence == 1.0
    assert analysis.scores.canonical_url == 1.0


def test_guid_match_is_exact_duplicate_when_urls_differ() -> None:
    existing = article(url="https://feed.example.com/item/123", canonical_url=None, guid="wire-123")
    new = article(url="https://daily.example.com/a/456", canonical_url=None, guid="wire-123")

    analysis = detector_with([candidate("doc-guid", existing)]).analyze(new)

    assert analysis.status == DuplicateStatus.EXACT_DUPLICATE
    assert analysis.strategy_used == "guid"
    assert analysis.scores.guid == 1.0


def test_same_wire_article_from_different_source_is_near_duplicate() -> None:
    existing = article(source_id="wire-a")
    new = article(
        url="https://another.example.com/story/crowd-plan",
        canonical_url="https://another.example.com/story/crowd-plan",
        source_id="wire-b",
    )

    analysis = detector_with([candidate("doc-wire", existing, source_id="wire-a")]).analyze(new)

    assert analysis.status == DuplicateStatus.NEAR_DUPLICATE
    assert analysis.confidence >= 0.9
    assert "different source" in " ".join(analysis.reasons)


def test_slightly_edited_wire_copy_is_near_duplicate() -> None:
    existing = article(source_id="wire-a")
    edited_body = (
        "City officials announced a crowd management plan for the upcoming "
        "festival. The revised plan adds temporary holding areas, extra transport "
        "lanes, and live monitoring teams at key intersections. Police said the "
        "changes should reduce congestion during peak arrival hours."
    )
    new = article(
        url="https://another.example.com/story/edited-crowd-plan",
        canonical_url="https://another.example.com/story/edited-crowd-plan",
        title="Officials announce new crowd-management plan!",
        body=edited_body,
        source_id="wire-b",
        published_at=BASE_TIME + timedelta(hours=2),
    )

    analysis = detector_with([candidate("doc-edited", existing, source_id="wire-a")]).analyze(new)

    assert analysis.status == DuplicateStatus.NEAR_DUPLICATE
    assert analysis.scores.title_similarity >= 0.9
    assert analysis.scores.content_similarity >= 0.8


def test_completely_different_article_is_new_document() -> None:
    existing = article()
    different = article(
        url="https://daily.example.com/news/weather",
        canonical_url="https://daily.example.com/news/weather",
        title="Monsoon Forecast Updated for Northern Districts",
        body=(
            "Meteorologists issued a new monsoon forecast for northern districts. "
            "The advisory describes rainfall totals, reservoir levels, and crop "
            "planning guidance for farmers over the next week."
        ),
    )

    analysis = detector_with([candidate("doc-old", existing)]).analyze(different)

    assert analysis.status == DuplicateStatus.NEW_DOCUMENT
    assert analysis.matched_document_id is None
    assert analysis.confidence == 0.0


def test_updated_version_of_same_story_is_possible_duplicate() -> None:
    existing = article(
        body=(
            "Officials announced an initial crowd plan for the festival. The plan "
            "mentions traffic diversions, volunteer teams, and control rooms."
        )
    )
    updated = article(
        url="https://daily.example.com/news/crowd-plan-update",
        canonical_url="https://daily.example.com/news/crowd-plan-update",
        title="Officials Announce Updated Crowd Management Plan",
        body=(
            "Officials announced an updated crowd management plan for the festival. "
            "The plan adds new transport lanes, revised traffic diversions, extra "
            "volunteer teams, and control rooms after a safety review."
        ),
        published_at=BASE_TIME + timedelta(hours=20),
    )

    analysis = detector_with([candidate("doc-version", existing)]).analyze(updated)

    assert analysis.status == DuplicateStatus.POSSIBLE_DUPLICATE
    assert analysis.confidence >= 0.6
    assert analysis.confidence < 0.86


def test_normalization_ignores_punctuation_case_whitespace_and_tracking_params() -> None:
    assert normalize_title(" Officials--Announce   Plan! ") == "officials announce plan"
    assert normalize_canonical_url(
        "HTTPS://Example.COM/story/?utm_source=rss&id=5#comments"
    ) == "https://example.com/story?id=5"


def test_fingerprints_are_deterministic() -> None:
    generator = FingerprintGenerator()
    first = generator.generate(article())
    second = generator.generate(article())

    assert first == second
    assert first.content is not None
    assert first.combined is not None


def test_similarity_engine_allows_algorithm_replacement() -> None:
    class AlwaysHalf:
        name = "always_half"

        def compare(self, left: str, right: str) -> float:
            return 0.5

    engine = SimilarityEngine(title_algorithm=AlwaysHalf(), content_algorithm=AlwaysHalf())

    assert engine.title_similarity("a", "b") == 0.5
    assert engine.content_similarity("a", "b") == 0.5


def test_configuration_can_be_loaded_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEDUP_NEAR_DUPLICATE_THRESHOLD", "0.8")
    monkeypatch.setenv("DEDUP_PUBLICATION_WINDOW_HOURS", "24")

    config = DuplicateDetectionConfig.from_env()

    assert config.near_duplicate_threshold == 0.8
    assert config.publication_window_hours == 24
