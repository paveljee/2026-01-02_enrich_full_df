# RFC 003: Candidate Generation (LONG Format)

Timestamp: 2026-01-26T04:57:01Z

## Scope (Single Testable Unit)
Generate author candidates in LONG format by fuzzy matching CSV names against SciSciNet author records.

## Context
Candidates are produced before manual deduplication. Each `draw_number` can have multiple candidate rows ranked by similarity.

## Implementation Details
- Join `csv_with_docx` against `author_details.parquet` on fuzzy name containment.
- Compute candidate ranking using a similarity metric and `ROW_NUMBER()` over `draw_number`.
- Limit results to a configurable maximum (e.g., top 10 candidates per `draw_number`).
- Export `candidates.csv` in LONG format with columns:
  - `draw_number`, `csv_first_name`, `csv_last_name`, `authorid`, `display_name`, `match_confidence`, `candidate_rank`.

## Validation Gates
- Ensure `candidates.csv` contains only `draw_number` values from `merged_samples.csv`.
- Ensure each `draw_number` has at least one candidate or explicitly log zero-candidate cases.

## Testing (to be implemented with this RFC)
### Unit Tests
- Ranking: verify candidate ranks are assigned in descending similarity order.
- Output schema: confirm required columns and LONG format shape.

### Integration Tests
- End-to-end generation on a fixture set with multiple candidates per draw number; verify output row counts and ranks.

### Regression Tests
- Snapshot a fixture `candidates.csv` and compare hashes for deterministic results.
