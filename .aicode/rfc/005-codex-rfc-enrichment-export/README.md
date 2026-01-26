# RFC 005: Enrichment & Export

Timestamp: 2026-01-26T04:57:01Z

## Scope (Single Testable Unit)
Join matched rows to enrichment sources (parquet + JSONL) and export enriched outputs in multiple formats.

## Context
Enrichment runs only for MATCHED rows after deduplication. JSONL joins are deterministic by `authorid`.

## Implementation Details
- Join `draw_status` (MATCHED only) with:
  - `author_papers.parquet` → paper IDs
  - `hit_papers.parquet` → hit counts
  - `fields.parquet` → field metadata
  - JSONL files (e.g., `residence.jsonl`, `education.jsonl`) keyed by `authorid`
- Produce `enriched_final` with combined columns from CSV, DOCX, and enrichment sources.
- Export:
  - `enriched_final.csv`
  - RDF formats (`.trig`, `.nquads`, `.jsonld`)
  - Card outputs (`markdown-cards.zip`, `docx-cards.zip`)

## Validation Gates
- Ensure only MATCHED rows are included in `enriched_final`.
- Validate output row counts are ≤ original sample count.

## Testing (to be implemented with this RFC)
### Unit Tests
- JSONL join: verify unmatched rows do not receive JSONL fields.
- Export: verify output filenames and non-empty content for matched rows.

### Integration Tests
- End-to-end enrichment on fixture data covering parquet + JSONL joins.

### Regression Tests
- Snapshot a fixture `enriched_final.csv` and compare hashes for stability.
