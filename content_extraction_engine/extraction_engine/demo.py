"""Quick manual demo: run the engine against a fixture and print results."""
from pathlib import Path

from core.models import RawDocument
from core.manager import ExtractionManager

FIXTURE = Path(__file__).parent / "tests" / "fixtures" / "simple_news_article.html"

if __name__ == "__main__":
    doc = RawDocument(
        url="https://www.dailyherald-example.com/news/local/park-funding-2026",
        content=FIXTURE.read_bytes(),
        content_type="text/html; charset=utf-8",
    )
    article = ExtractionManager().extract(doc)

    print("Title:        ", article.title)
    print("Authors:      ", article.authors)
    print("Published:    ", article.published_at)
    print("Categories:   ", article.categories)
    print("Tags:         ", article.tags)
    print("Word count:   ", article.word_count)
    print("Reading time: ", article.reading_time_minutes, "min")
    print("Strategy used:", article.quality.strategy_used.value)
    print("Quality score:", article.quality.score)
    print("Warnings:     ", article.quality.warnings)
    print()
    print("--- Body preview ---")
    print((article.body_text or "")[:300], "...")
