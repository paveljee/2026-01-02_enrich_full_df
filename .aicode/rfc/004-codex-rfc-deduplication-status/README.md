# RFC 004: Deduplication Validation & Status Tracking

Timestamp: 2026-01-26T04:57:01Z

## Scope (Single Testable Unit)
Validate the user-provided `deduplicated.csv` and derive per-draw status tracking for MATCHED vs UNMATCHED rows.

## Context
Deduplication collapses LONG-format candidates to at most one row per `draw_number`. Status tracking must preserve unmatched rows.

## Implementation Details
- Load `deduplicated.csv` and verify:
  - It is a strict subset of `candidates.csv`.
  - `draw_number` appears at most once (unique draw constraint).
  - All `draw_number` values come from `merged_samples.csv`.
- Derive `draw_status` table with columns:
  - `draw_number`, `status` (MATCHED/UNMATCHED), `authorid` (nullable).
- Use `draw_status` to gate enrichment (only MATCHED rows proceed).

## Validation Gates
- Fail if `deduplicated.csv` contains non-unique `draw_number` values.
- Fail if any `draw_number` is outside the original sample set.

## Testing (to be implemented with this RFC)
### Unit Tests
- Validate that duplicates in `deduplicated.csv` raise errors.
- Validate `draw_status` correctly classifies matched vs unmatched rows.

### Integration Tests
- Validate deduplication against a fixture `candidates.csv` and `merged_samples.csv`.

### Regression Tests
- Snapshot a fixture dedupe set and assert stable `draw_status` output.
