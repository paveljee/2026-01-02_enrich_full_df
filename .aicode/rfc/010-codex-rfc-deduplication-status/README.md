# RFC 010: Deduplication Validation + Status Tracking

Timestamp: 2026-01-26T14:16:34Z

## Scope (Single Testable Unit)
Validate the user-provided `deduplicated.csv` and derive per-row status tracking (`MATCHED` vs `UNMATCHED`). All implementation lives under `./pkg_20260126_roadmap/`.

This RFC covers only deduplication validation and status derivation; it does not include enrichment joins.

## Required Source of Truth (Must Reuse)
- Deduplication logic and validation gates from the roadmap (`.aicode/rfc/ROADMAP.md`).
- Candidate format defined in RFC 009.

## Implementation Instructions (Must Follow)
1. **Load inputs**
   - Load `candidates.csv` (LONG format) and user-provided `deduplicated.csv`.
2. **Validation gates**
   - `deduplicated.csv` must be a subset of `candidates.csv` by `draw_number`.
   - Each `draw_number` can appear at most once in `deduplicated.csv`.
   - All `draw_number` values must exist in `merged_samples.csv`.
3. **Status tracking**
   - Produce a `draw_status` dataset containing every original `draw_number`:
     - `status` = `MATCHED` if the draw is in `deduplicated.csv`, else `UNMATCHED`.
     - `authorid` present only for `MATCHED` rows.

## Test Fixture Requirements
- Create fixture `candidates.csv` and `merged_samples.csv`.
- Include a fixture `deduplicated.csv` with:
  - A valid subset
  - A duplicate draw_number case
  - A draw_number that does not exist in merged samples (to trigger failure)

## Testing Requirements (Implement With This RFC)
### Unit Tests
- Validate the subset and uniqueness checks.
- Validate `draw_status` output for matched/unmatched rows.

### Integration Tests
- Full validation pipeline with fixture inputs, asserting failures for invalid cases.

### Regression Tests
- Freeze fixture inputs and compare `draw_status` output hash to a golden file.

## Output Location
All new implementation for the roadmap must live under:
- `./pkg_20260126_roadmap/`
