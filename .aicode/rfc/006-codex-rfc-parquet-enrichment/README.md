# RFC 006: Parquet Enrichment (SciSciNet)

Timestamp: 2026-01-26T14:16:34Z

## Scope (Single Testable Unit)
Implement enrichment joins between matched CSV/DOCX data and SciSciNet parquet datasets using DuckDB, reusing the logic from `repl.py`. All implementation lives under `./pkg_20260126_roadmap/`.

This RFC covers only parquet enrichment and does not include JSONL joins or RDF exports.

## Required Source of Truth (Must Reuse)
The enrichment REPL in `repl.py` is the canonical reference and must be reused with minimal changes:

- `./repl.py`
  - `PipelineManager` (DuckDB connection, memory limit, splink_udfs install)
  - `FILES_CONFIG` (input path+sha256 expectations)
  - Pipeline flow for verification and enrichment

Supplemental schema references (for test fixtures):
- https://github.com/paveljee/research-integrity-ktp/blob/v0.1.0-pilot.1751566592/test_run_outputs/test_run_report.md
- (Optional helper scripts; not ground truth):
  - https://github.com/paveljee/research-integrity-ktp/blob/v0.1.0-pilot.1751566592/create_dummy_parquets.py
  - https://github.com/paveljee/research-integrity-ktp/blob/v0.1.0-pilot.1751566592/fix_dummy_data.py

## Implementation Instructions (Must Follow)
1. **DuckDB configuration**
   - Reuse connection settings from `PipelineManager` (memory limit and splink_udfs install).
2. **Join strategy**
   - Join matched rows (from `draw_status` / `csv_with_docx`) to parquets by `authorid` and `paperid` as in `repl.py`.
3. **Input validation**
   - Validate parquet files using SHA256 checks (as done in `repl.py`).
   - Abort if any file is missing or checksum mismatched.
4. **Output schema**
   - Produce an enriched dataframe that includes:
     - original CSV/DOCX fields
     - `authorid`
     - paper IDs, hit counts, and field metadata

## Test Fixture Requirements
- Create small parquet fixtures for:
  - author details (authorid + display_name)
  - author→paper mapping
  - hit papers
  - fields
- Align fixture schema with the fields described in `test_run_report.md`.

## Testing Requirements (Implement With This RFC)
### Unit Tests
- Verify file hashing logic detects mismatches.
- Verify DuckDB joins produce expected column sets for a single author.

### Integration Tests
- End-to-end enrichment with fixture parquets and a small matched CSV to confirm:
  - All expected joins are applied.
  - Output rows match expected counts.

### Regression Tests
- Freeze fixtures and compare enriched output CSV hash to a golden file.

## Output Location
All new implementation for the roadmap must live under:
- `./pkg_20260126_roadmap/`
