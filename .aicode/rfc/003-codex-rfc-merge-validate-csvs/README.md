# RFC 003: Merge & Validate Sample CSVs

Timestamp: 2026-01-26T14:16:34Z

## Scope (Single Testable Unit)
Implement CSV validation and merge logic for sample outputs (main + pilot samplers) into a single dataset. All implementation lives under `./pkg_20260126_roadmap/`.

This RFC is ONLY about validating CSV headers and concatenating CSVs; it does not include DOCX enrichment, candidate generation, or downstream enrichment.

## Required Source of Truth (Must Reuse)
The CSV validation and merging logic is already implemented in `pkg_20251223_word_tables/src/cli.py`. That logic must be reused with minimal changes:

- Local reference: `./pkg_20251223_word_tables/src/cli.py`
  - `find_files_by_extension`
  - `validate_csv_headers`
  - CSV concatenation logic in `process_documents`

## Implementation Instructions (Must Follow)
1. **Create a merge module** under `./pkg_20260126_roadmap/` that:
   - Scans a directory for `*.csv` (with optional recursion).
   - Validates that all CSVs share identical headers (use `validate_csv_headers` logic).
   - Concatenates CSVs into a single dataframe in a deterministic order (sorted filenames).
2. **Preserve schema compatibility**:
   - The merged output must maintain the schema defined by the sampler outputs and `test_unify_names.py::hcr_row`.
3. **Preserve draw-number integrity**:
   - Ensure `ktp.draw_number` values are retained exactly from source files (no reindexing).
4. **Output**:
   - Write a single merged CSV (e.g., `merged_samples.csv`) to a deterministic location inside `./pkg_20260126_roadmap/`.

## Data & Fixture Requirements for Tests
- Create fixture CSVs using the same schema as the sampler outputs.
- Include at least one CSV with a header mismatch to validate the failure path.

## Testing Requirements (Implement With This RFC)
### Unit Tests
- Validate that `validate_csv_headers` returns `False` for mismatched headers.
- Validate that file scanning respects recursion and extension filtering.

### Integration Tests
- Provide multiple fixture CSVs with correct headers and confirm:
  - The merged CSV contains all rows in deterministic file order.
  - The schema matches the sampler schema.

### Regression Tests
- Fix a fixture set and compare merged CSV output hash to a golden file.

## Output Location
All new implementation for the roadmap must live under:
- `./pkg_20260126_roadmap/`
