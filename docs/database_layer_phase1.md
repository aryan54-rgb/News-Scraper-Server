# Database Layer Phase 1

## Loading Strategy

All collection relationships use `lazy="selectin"` by default. This is async-friendly because it avoids implicit per-row lazy loads while still keeping initial entity queries reasonably small. Many-to-one relationships also use `selectin` when the related row is commonly needed for repository reads, such as `Article.source` or `Classification.taxonomy_node`.

The `RawDocument.article` and `Article.raw_document` one-to-one relationship uses `lazy="joined"` because lineage is core to article inspection and the cardinality is guaranteed by `uq_article_raw_document_id`.

Association rows such as `SourceGroupMembership` and `ArticleEvent` are modeled as first-class tables instead of bare secondary tables so confidence, audit fields, timestamps, soft-delete, and future metadata can be added without schema redesign.

## Index Rationale

Source indexes cover type/status/domain filters, active not-deleted lookups, and JSONB metadata containment. Source group and keyword group names use partial unique indexes so retired soft-deleted names do not block re-use.

Collection indexes are time-oriented: `source_id, fetched_at` and `collector_job_id, fetched_at` support fetch history queries, while status and content hash indexes support error dashboards and duplicate checks.

Document indexes target common retrieval paths: source plus publication time, standalone publication time, canonical URL uniqueness, full-text `search_vector` GIN search, trigram title search, and JSONB metadata filters.

Event indexes support active-event dashboards with `status, last_seen_at`, timeline queries with `started_at`, fuzzy title matching with trigram GIN, and JSONB metadata search.

Taxonomy indexes enforce one current version per taxonomy name, unique node codes per version, parent traversal, path lookup, fuzzy node-name search, and JSONB metadata filtering.

Classification indexes support article detail pages, taxonomy-node rollups, version/status reclassification queues, and JSONB model-output filters. Evidence payloads use GIN for structured support snippets and model annotations.

Entity indexes support canonical uniqueness by type, type filters, fuzzy name and alias resolution through trigram GIN, external ID containment, and article/entity mention joins.

Keyword indexes support group membership, fuzzy monitored-term lookup, priority filters, active not-deleted matching, hit lookups by article or keyword, and time-based hit feeds.

## Constraint And Delete Rules

Core records use UUID primary keys with `gen_random_uuid()`, timestamp fields, `deleted_at` soft-delete, row `version`, and audit actor columns. Lookup-like models still use UUIDs to satisfy the Phase 1 consistency requirement.

`CASCADE` is used for true dependent records: association rows, aliases, evidence, article events, and article-bound mentions or hits. `RESTRICT` protects lineage and canonical records such as sources, raw documents, taxonomy nodes, entities, and keywords. `SET NULL` is used where logs should survive missing optional execution context, such as `FetchLog.collector_job_id` and `RawDocument.fetch_log_id`.
