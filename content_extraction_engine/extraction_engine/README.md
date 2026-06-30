# Content Extraction Engine

Converts raw fetched HTML documents (`RawDocument`) into clean, structured
`NormalizedArticle` objects. Designed to sit downstream of the Collector
Framework / HTML Collector and be reusable by every collector in the
pipeline.

**Scope**: extraction only. No AI, no classification, no entity extraction,
no duplicate detection, no database writes — those are separate stages.

## Architecture

```
engine.py                      <- public entry point (re-exports everything below)
core/
  models.py                    <- RawDocument, NormalizedArticle, ExtractionResult, QualityReport
  normalization.py             <- unicode/whitespace/date/URL normalization
  cleaning.py                  <- boilerplate removal (nav/ads/footers/comments/...)
  metadata.py                  <- OpenGraph / Twitter Card / JSON-LD parsing helpers
  diagnostics.py                <- quality scoring / QualityReport builder
  manager.py                   <- ExtractionManager: orchestrates strategies + merges results
extractors/
  base.py                      <- BaseExtractor interface (safe_extract wrapper)
  jsonld_extractor.py          <- Strategy 1: schema.org JSON-LD
  opengraph_extractor.py       <- Strategy 2: OpenGraph / Twitter Card meta tags
  article_library_extractor.py <- Strategy 3: trafilatura (graceful no-op if not installed)
  readability_extractor.py     <- Strategy 4: from-scratch Arc90-style scoring algorithm
  dom_heuristic_extractor.py   <- Strategy 5: semantic-tag / class-hint candidate search
  fallback_extractor.py        <- Strategy 6: guaranteed last resort (all <p> tags)
  registry.py                  <- ExtractorRegistry: pluggable strategy ordering
tests/
  fixtures/*.html              <- mocked HTML: news article, gov page, blog, broken HTML,
                                   missing metadata, paywall stub, large article
  test_extraction_engine.py    <- 44 tests covering every strategy + edge case
```

## Extraction strategy order

1. **JSON-LD** — schema.org `NewsArticle`/`Article`/`BlogPosting` blocks. Highest
   fidelity when present; supplies metadata even when `articleBody` is absent.
2. **OpenGraph / Twitter Card** — `og:*`, `article:*`, `twitter:*` meta tags.
   Metadata-only; never produces a body.
3. **Article extraction library** — wraps `trafilatura` when installed; the
   extractor self-disables (returns `success=False`) if the dependency is
   missing, so the engine degrades gracefully rather than crashing.
4. **Readability algorithm** — a from-scratch implementation of the classic
   Arc90/Readability.js scoring approach (text density, comma count, link
   density, class/id weighting, parent/grandparent score propagation).
5. **DOM heuristic** — faster fallback: looks for `<article>`, `<main>`,
   `[role=main]`, `[itemprop=articleBody]`, and common CMS class names
   (`.article-body`, `.post-content`, `.entry-content`, ...), picks whichever
   candidate has the highest paragraph-text density.
6. **Fallback** — guaranteed to return *something*: every `<p>` tag on the
   cleaned page, plus `<h1>`/`<title>`. Lowest confidence by design.

The `ExtractionManager` runs every strategy (each wrapped so internal
exceptions can never propagate), picks the highest-confidence result that
produced a real body (≥100 chars), then **layers metadata from JSON-LD and
OpenGraph on top** to fill any gaps (e.g. DOM-heuristic body + JSON-LD
author/date/images).

## Cleaning

`core/cleaning.py` removes navigation, headers, footers, ads, sidebars,
related-article widgets, comments, cookie banners, newsletter popups, and
social-share widgets via a combination of hard tag removal (`<nav>`,
`<script>`, `<form>`, ...) and id/class/role pattern matching
(`nav`, `sidebar`, `cookie`, `newsletter`, `disqus`, `related-stories`, ...).
Paragraphs, headings, lists, blockquotes, tables, and captions are preserved.

## Normalization

`core/normalization.py` handles: NFC unicode normalization + control-char
stripping, whitespace collapsing, date parsing (ISO 8601, epoch
seconds/millis, free-form via `dateutil`) into aware UTC datetimes, URL
normalization (relative→absolute resolution, tracking-param stripping,
trailing-slash/scheme/host normalization), image URL resolution (query
strings preserved, since CDNs encode sizing/signing info there), paragraph
deduplication, empty-section stripping, word count, and reading time.

## Quality diagnostics

Every `NormalizedArticle.quality` is a `QualityReport` with: which strategy
won, which strategies were attempted, missing-title/author/date/body flags,
content length, word count, boilerplate ratio (vs. the original raw HTML),
human-readable warnings, and a blended 0–1 confidence score (60% field
completeness + 40% the winning extractor's self-reported confidence).

## Usage

```python
from engine import ExtractionManager
from core.models import RawDocument

doc = RawDocument(
    url="https://example.com/news/some-article",
    content=raw_html_bytes,          # bytes as fetched by the Collector
    headers={"Content-Type": "text/html; charset=utf-8"},
    content_type="text/html; charset=utf-8",
)

article = ExtractionManager().extract(doc)

print(article.title)
print(article.authors)
print(article.published_at)
print(article.word_count, article.reading_time_minutes)
print(article.quality.score, article.quality.warnings)

# JSON-serializable form for queueing / storage by a downstream stage
payload = article.to_dict()
```

### Registering a custom/site-specific extractor

```python
from extractors.registry import ExtractorRegistry
from extractors.base import BaseExtractor

class MySiteExtractor(BaseExtractor):
    strategy = ...  # add a new ExtractionStrategy value if needed
    def extract(self, document):
        ...

registry = ExtractorRegistry()
registry.register(MySiteExtractor, position=0)  # tried before JSON-LD
manager = ExtractionManager(registry=registry)
```

## Running the tests

```bash
pip install -r requirements.txt
pytest tests/ -v
```

44 tests across 7 mocked HTML fixtures (simple news article, government
page, blog post, broken/malformed HTML, missing metadata, paywall stub,
large 40-paragraph article) plus normalization unit tests and engine-level
"never raises" guarantees.

## Out of scope (intentionally not implemented)

AI/LLM usage, content classification, entity extraction, duplicate
detection, relevance filtering, and database writes. This module's only
job is producing `NormalizedArticle` objects.
