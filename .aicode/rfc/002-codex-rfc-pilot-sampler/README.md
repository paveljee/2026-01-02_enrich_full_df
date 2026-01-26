# RFC 002: Pilot XLSX Sampler (2025-12-23) Integration

Timestamp: 2026-01-26T14:16:34Z

## Scope (Single Testable Unit)
Implement the *pilot* XLSX sampler that selects explicit name/category triples from 2024 HCR XLSX data, producing a CSV compatible with the main sampler schema. All implementation lives under `./pkg_20260126_roadmap/`.

This RFC is ONLY about the pilot sampler logic (explicit name selection and schema reindexing). It excludes main sampling, CSV merging, DOCX enrichment, or downstream enrichment steps.

## Required Source of Truth (Must Reuse)
The 2025-12-23 pilot sampler logic is the authoritative source and **must be reused with minimal changes** (do not alter logic or comments unless strictly required for integration). Implementers **must fetch** the upstream file and preserve it verbatim:

- https://github.com/paveljee/research-integrity-ktp/blob/analysis/2025-12-23_pilot_sampler/analyses/2025-12-23_pilot_sampler/pilot_sampler.py
- Ground-truth pilot CSV output (review for expected ordering and schema):
  - https://github.com/paveljee/research-integrity-ktp/blob/analysis/2025-12-23_pilot_sampler/analyses/2025-12-23_pilot_sampler/pilot_sample_2025-07-24.csv

## Existing Local Schema Constraints
Pilot sampler output **must be schema-compatible** with the main sampler output. Use the column schema from:
- `./pkg_20251223_word_tables/tests/test_unify_names.py::hcr_row`

Key behaviors to preserve from `pilot_sampler.py`:
- Uses `MATCHING_COLS = ["hcr.first_name", "hcr.last_name", "hcr.category"]`.
- Reindexes the 2024 XLSX dataframe to match the column names of the full folder schema.
- Assigns `ktp.draw_number` with `pilot.` prefix (e.g., `pilot.1`).

## Implementation Instructions (Must Follow)
1. **Create the new project module** inside `./pkg_20260126_roadmap/`.
2. **Reuse the exact name/category triple logic** from the upstream `pilot_sampler.py` linked above:
   - Input is a list of `(first_name, last_name, category)` tuples.
   - Filter rows where these tuples match and maintain the input order.
3. **Preserve schema reindexing**:
   - Use folder XLSX schema to define column order, then reindex the 2024 XLSX data to match.
4. **Preserve draw number format**:
   - `ktp.draw_number` must be strings with `pilot.` prefix to match historical output.
5. **Preserve affiliation priority logic**:
   - Same priority logic as the main sampler if `affiliation_sort` is enabled.

## Data & Fixture Requirements for Tests
- Build fixture XLSX files representing:
  - One “folder schema” XLSX with all normalized columns.
  - One “2024” XLSX with the rows to be selected.
- Define name/category triples that map to fixture rows, including duplicates to emulate multi-category cases.

## Testing Requirements (Implement With This RFC)
### Unit Tests
- Verify name/category tuple matching returns rows in the exact order of the input triples.
- Verify schema reindexing matches the full folder schema columns.
- Verify draw numbers are prefixed with `pilot.` and are sequential.

### Integration Tests
- Use fixture XLSX files to generate a pilot CSV and confirm:
  - Output schema matches the main sampler schema.
  - Output row count equals the number of name/category triples provided.

### Regression Tests
- Use a fixture input and a known list of name/category triples to compare output CSV hash to a golden file.

## Output Location
All new implementation for the roadmap must live under:
- `./pkg_20260126_roadmap/`
