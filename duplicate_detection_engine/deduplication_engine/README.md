# Duplicate Detection Engine

Determines whether a newly extracted article is a new document or a duplicate
of a recently collected article.

The engine is read-only. It does not write to the database, merge records,
classify content, extract entities, call AI models, or resolve events.

## Strategy Order

1. Canonical URL match
2. GUID match
3. Deterministic content fingerprint
4. Normalized title similarity
5. Cleaned content similarity
6. Publication time proximity
7. Source-aware confidence adjustment

Exact URL and GUID matches return immediately. Exact content fingerprints from
the same source are exact duplicates; exact content from different sources is a
high-confidence near duplicate so syndicated wire coverage remains observable.

## Usage

```python
from deduplication_engine import (
    DuplicateCandidate,
    DuplicateDetector,
    InMemoryDuplicateRegistry,
)

registry = InMemoryDuplicateRegistry([
    DuplicateCandidate(document_id="existing-1", article=existing_article),
])

analysis = DuplicateDetector(registry).analyze(new_article)
print(analysis.to_dict())
```

Production callers should implement `DuplicateRegistry.find_candidates()` using
their own read-only repository/query layer.
