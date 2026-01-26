# RFC 002: DOCX Reconstruction Matching

Timestamp: 2026-01-26T04:57:01Z

## Scope (Single Testable Unit)
Reconstruct the 1:1 mapping between merged sample CSV rows and DOCX table rows using deterministic fuzzy name matching.

## Context
DOCX matching is essential and must run before candidate generation. It must succeed 100% or abort the pipeline.

## Implementation Details
- Parse all DOCX tables into a single `docx_parsed` dataset with `docx_row_id` and `combined_name`.
- Implement fuzzy matching logic:
  - For each CSV row, find DOCX rows where `combined_name` contains both `csv.first_name` and `csv.last_name` (case-insensitive).
  - Require exactly one match per `draw_number`; otherwise, stop the pipeline and report failures.
- Persist `csv_with_docx` for downstream phases.
- Validate that distinct `draw_number` and distinct `docx_row_id` both equal the total sample count (e.g., 310 rows).

## Validation Gates
- `docx_validation` must be empty before proceeding.
- Abort if any `draw_number` has zero or multiple matches.

## Testing (to be implemented with this RFC)
### Unit Tests
- Match scoring: verify rows only match when both first and last names are contained.
- Validation: ensure non-unique matches trigger errors.

### Integration Tests
- Parse multiple DOCX files and reconstruct mapping for a small fixture set, confirming `csv_with_docx` preserves all CSV rows.

### Regression Tests
- Snapshot a known CSV/DOCX fixture pair and assert deterministic 1:1 mapping results.
