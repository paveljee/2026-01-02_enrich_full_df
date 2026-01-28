# RFC: CLI matcher refactor

- Timestamp (UTC): 2026-01-27T07:36:02Z
- Author: GPT-5.2-Codex

## Context
The CLI currently embeds CSV and DOCX name-matching logic directly in `cli.py`, using matcher-specific globals like `append_csv_matches`, `append_docx_matches`, `CsvNameMatchProcedure`, and `DocxNameMatchProcedure`. The user request is to extract matching logic into separate files for CSV and DOCX, encapsulate matcher-specific objects, and introduce a generic matcher interface that owns an `OuterDict` reference and appends `InnerDict` rows via `OuterDict` methods. The existing RFC on outer-dict refactor documents the prior step.

## Goals
- Move CSV matching logic into a dedicated module.
- Move DOCX matching logic into a dedicated module.
- Encapsulate matcher-specific procedures/appenders inside matcher classes rather than globals.
- Introduce a generic matcher interface for CSV/DOCX that:
  - Holds a reference to `OuterDict`.
  - Initializes and stores the relevant list of `InnerDict` entries in `OuterDict`.
  - Delegates to `OuterDict` for appending `InnerDict` entries by name key.
- Ensure `OuterDict` exposes an append method for name-keyed inner dicts.
- Vectorize operations on dataframes (avoid per-row iteration like `iterrows`).

## Planned Actions
1. Inspect `pkg_20251223_word_tables/src/cli.py` and existing model definitions to understand current matching flow.
2. Locate or introduce `OuterDict` methods for appending by name key; add if missing.
3. Create `pkg_20251223_word_tables/src/matchers/csv_matcher.py` to encapsulate CSV matching logic, including `CsvNameMatchProcedure` (or equivalent) and matching routines, and to expose a `CsvMatcher` implementing the new matcher interface.
4. Create `pkg_20251223_word_tables/src/matchers/docx_matcher.py` to encapsulate DOCX matching logic and expose a `DocxMatcher` implementing the new matcher interface.
5. Add a generic matcher interface (protocol/ABC) in a shared matcher module to ensure CSV/DOCX conform.
6. Update `cli.py` to use the new matcher classes and remove matcher-specific globals.
7. Ensure vectorized dataframe operations (e.g., merges/joins) replace any `iterrows` loops in matching logic.
8. Update imports and any related references.
9. Run relevant tests or note if none are available.
10. Add a detailed report in this RFC after changes.

## Report
- Created a matcher framework (`Matcher` protocol, `BaseMatcher`, and helper utilities) that stores the `OuterDict` reference, ensures inner lists exist, and appends `InnerDict` entries via the shared base append method.
- Extracted CSV name-matching into `csv_matcher.py` with a `CsvMatcher` that vectorizes matches using a merge on unified first/last name columns and encapsulates `CsvNameMatchProcedure` inside the module.
- Extracted DOCX name-matching into `docx_matcher.py` with a `DocxMatcher` that vectorizes matching using a cross-join and string containment checks, encapsulating `DocxNameMatchProcedure` and the cleaning helpers inside the module.
- Updated `cli.py` to use the new matcher classes and removed embedded matcher-specific globals and iterrows-based match loops.
- Extended `OuterDict` with append/ensure helpers to support matcher-owned inner-list pointers and appending by name-key string.
