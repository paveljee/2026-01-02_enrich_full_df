# RFC: OuterDict refactor for CLI matching

- Timestamp (UTC): 2026-01-27T01:20:00Z
- Author: GPT-5.2-Codex

## Context
The CLI currently merges CSV and DOCX data with a one-to-one join on matched indices, which prevents multiple DOCX matches and mixes dataset logic directly into card creation. This RFC introduces a more explicit data model based on OuterDict (name key -> list of InnerDict rows) to support one-to-many matching and dataset extensibility.

## Goals
- Define Pydantic models for NameKey, InnerDict, and OuterDict.
- Refactor `cli.py` to build an `OuterDict` keyed by JSON-serialized name pairs.
- Implement dataset matching procedures that can append multiple matched rows to each key.
- Update card building to render one card per outer key and one section per inner dict.
- Introduce per-dataset origin tracking via `ktp.filename` for CSV and DOCX rows.

## Planned Changes
1. Add Pydantic dependency to project config.
2. Create data model definitions (NameKey, InnerDict, OuterDict) and a matching-procedure interface.
3. Extend `_vars.py` with a shared `KTP_FILENAME_COL` constant.
4. Update `cli.py` to:
   - Build an empty OuterDict from unified unique name pairs.
   - Add a CSV matching procedure (exact first/last matches) that appends rows to each key.
   - Update DOCX matching to allow multiple matches and append each matched row.
   - Create dataset-specific `ktp.filename` columns for origin tracking.
   - Build cards using the new model (one card per key, inner dicts as sections).

## Files Impacted
- `pkg_20251223_word_tables/src/cli.py`
- `pkg_20251223_word_tables/src/_vars.py`
- `pkg_20251223_word_tables/src/` (new model module)
- `pyproject.toml`
- `requirements.txt`

## Testing Plan
- Run existing tests if available (`pytest`).
- If no tests are feasible, note lack of coverage.

## Report
- Implemented Pydantic data models for NameKey, InnerDict, and OuterDict, including JSON key serialization and matching procedure validation.
- Refactored CLI processing to build an OuterDict from unique name pairs, append CSV and DOCX matches as InnerDict entries, and render cards by iterating inner dicts with dataset-origin headings.
- Added `ktp.filename` tracking to both CSV and DOCX datasets and normalized DOCX headers before appending matches.
- Updated project dependencies to include Pydantic and documented the new data-model expectations in the refactor.
