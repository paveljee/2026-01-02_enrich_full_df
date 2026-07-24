# SSN innerdict schema workbook

## Constraints

- Preserve the human-authored `SPEC.md` section.
- Never run or import `src.repl`; never mutate the supplied database.
- Do not use Git.
- Preserve `name_key` / `innerdicts` column labels for this task.
- Keep changes surgical; do not refactor `OuterDict`, source-key ownership, or
  shared DuckDB helpers beyond removing the obsolete row loader at the end.

## Execution sequence

1. Mechanically move the current wide SSN relation and every current consumer
   to `PARQUET_LEGACY_ROWS_INNERDICT_TABLE`, preserving behavior.
2. Materialize a new, initially unconsumed `PARQUET_INNERDICT_TABLE` with the
   existing two-column JSONL contract used by XLSX and DOCX.
3. Rebind only true innerdict consumers to the new table. Keep flat relational
   consumers on the legacy table or `PARQUET_OUTPUT_VIEW`.
4. Remove `append_innerdicts_from_rows_table`; adjust focused tests and verify.

## Status

- Completed: re-read both spec sections, the linked prerequisite, and relevant
  step-9/resume/detour consumers.
- Completed: phase 1 mechanical legacy-table rename. All former wide consumers
  now use `PARQUET_LEGACY_ROWS_INNERDICT_TABLE`; the new constant is free.
- Completed: phase 2 creation of the two-column SSN JSONL table, inline in step
  9 using the same group/drop/JSONL/register/create pattern as steps 7 and 8.
- Completed: phase 3 consumer rebinding. Fresh step-9 and resume hydration use
  `append_innerdicts_from_jsonlines_table` with `PARQUET_INNERDICT_TABLE`;
  flat output and detours remain on the legacy relation/output view.
- Completed: removed the now-unreferenced `append_innerdicts_from_rows_table`.
- Completed: focused and repository validation.

## Consumer classification

- New JSONL table: fresh step-9 `OuterDict` hydration and resume hydration.
- Legacy rows/output view: `PARQUET_OUTPUT_VIEW` and flat detour analytics.
- Step-10 review remains on `PARQUET_OUTPUT_VIEW`.

## Findings

- DuckDB nullable floats become pandas `NaN`; step 9 normalizes pandas missing
  values to Python `None` before JSONL serialization so SQL `NULL` remains JSON
  `null`. DuckDB JSON-typed cells arrive as strings and remain strings.

## Verification

- Phase 1 narrow tests: 9 passed. Two mode-0 tests were blocked only because
  the default environment lacks optional Plotly/Kaleido; rerun those in the
  `detour-mode0-econ-stats` pixi environment.
- Phase 2/3 focused tests: 10 passed.
- Detours: mode 0 passed 4/4 in its optional pixi environment; mode 3 passed
  6/6 in the default environment. Read-only assertions remained intact.
- Ruff: passed for all touched Python files.
- mypy: passed for all touched Python files.
- Repository suite excluding live `real_api`: 133 passed, 3 skipped, 4
  deselected, 6 xfailed, 1 xpassed. One unrelated environment failure remains:
  the configured `splink_udfs` Linux ARM64 binary is absent at the expected
  external path.
- Supplied database was opened read-only only to confirm the former wide SSN
  type profile; it was not mutated.
- `src.repl` was neither run nor imported. No Git command was used.
