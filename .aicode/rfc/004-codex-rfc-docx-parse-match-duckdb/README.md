# RFC 004: DOCX Parsing + DuckDB Name Matching

Timestamp: 2026-01-26T14:16:34Z

## Scope (Single Testable Unit)
Implement DOCX parsing and deterministic CSV↔DOCX row matching inside DuckDB, preserving the exact matching semantics in `pkg_20251223_word_tables`. All implementation lives under `./pkg_20260126_roadmap/`.

This RFC covers only DOCX parsing, matching, and the creation of a `csv_with_docx` dataset. It does not cover card generation (see RFC 005) or enrichment.

## Required Source of Truth (Must Reuse)
The matching logic must reuse the semantics from the existing Python implementation:

- `./pkg_20251223_word_tables/src/name_utils.py`
  - `unify_first_last`
  - `match_csv_docx_names` (exact “contains” semantics, no lowercasing)
- `./pkg_20251223_word_tables/src/cli.py`
  - `parse_docx_standard`
  - `get_cell_text_with_format`
- `./pkg_20251223_word_tables/src/_vars.py`
  - `RIGHT_NAME_COL = "Researcher/author"` (this is the DOCX column used for matching)

## Implementation Instructions (Must Follow)
1. **DOCX parsing**
   - Reuse `parse_docx_standard` to read DOCX tables and convert to a single dataframe.
   - Preserve formatted text extraction (`get_cell_text_with_format`) for all non-header cells.
   - Combine all tables from all DOCX files into a single `docx_df`.
2. **Name unification**
   - Apply `unify_first_last` to each CSV row to generate `ktp.first_name` and `ktp.last_name` values.
3. **DuckDB matching (ported from `match_csv_docx_names`)**
   - The match criteria is **contains** for both first and last names on `RIGHT_NAME_COL`.
   - Matching is **case-sensitive** in the current implementation (no `.lower()` conversion).
   - Each CSV row must match **exactly one** DOCX row. Zero or multiple matches are failures.
4. **Output dataset**
   - Join CSV rows to DOCX rows using the matched index.
   - Preserve the DOCX table header normalization from `cli.py` (`ktp.table_1_*` prefix and underscore normalization).

## Test Fixture Requirements
- Create fixture DOCX files with a table that includes a header row using `RIGHT_NAME_COL` (`Researcher/author`).
- Include at least:
  - A row with a unique match (first+last name contained).
  - A row with no match.
  - A row with multiple possible matches (to validate failure path).

## Testing Requirements (Implement With This RFC)
### Unit Tests
- Validate that DOCX parsing preserves formatted text for non-header rows.
- Validate that DuckDB matching reproduces the exact behavior of `match_csv_docx_names`.

### Integration Tests
- Combine fixture CSV data (with unified names) and fixture DOCX data to produce `csv_with_docx` and confirm:
  - All CSV rows are preserved.
  - All DOCX fields are joined correctly.

### Regression Tests
- Freeze a fixture DOCX + CSV input and compare the resulting joined dataset hash to a golden file.

## Output Location
All new implementation for the roadmap must live under:
- `./pkg_20260126_roadmap/`
