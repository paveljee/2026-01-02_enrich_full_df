# SSN innerdict schema workbook

## Constraints

- Preserve the human-authored `SPEC.md` section.
- Never run or import `src.repl`; never mutate the supplied database.
- Do not use Git.
- Preserve `name_key` / `innerdicts` column labels for this task.
- Keep changes surgical; do not refactor `OuterDict`, source-key ownership, or
  unrelated DuckDB behavior.
- Declare the common innerdict table contract and source relations visibly in
  `schema.py`; retain the existing `name_key` / `innerdicts` labels.

## Execution sequence

1. Mechanically move the current wide SSN relation and every current consumer
   to `PARQUET_LEGACY_ROWS_INNERDICT_TABLE`, preserving behavior.
2. Materialize a new, initially unconsumed `PARQUET_INNERDICT_TABLE` with the
   existing two-column JSONL contract used by XLSX and DOCX.
3. Rebind only true innerdict consumers to the new table. Keep flat relational
   consumers on the legacy table or `PARQUET_OUTPUT_VIEW`.
4. Remove `append_innerdicts_from_rows_table`; adjust focused tests and verify.
5. Consolidate the existing XLSX/DOCX/SSN JSONL materialization pattern after
   explicitly stabilizing bounded SSN hit sums as `BIGINT`.

## Status

- Completed: re-read both spec sections, the linked prerequisite, and relevant
  step-9/resume/detour consumers.
- Completed: phase 1 mechanical legacy-table rename. All former wide consumers
  now use `PARQUET_LEGACY_ROWS_INNERDICT_TABLE`; the new constant is free.
- Completed: phase 2 creation of the two-column SSN JSONL table from the ordered
  legacy rows through the common group/drop/JSONL writer.
- Completed: phase 3 consumer rebinding. Fresh step-9 and resume hydration use
  `append_innerdicts_from_jsonlines_table` with `PARQUET_INNERDICT_TABLE`;
  flat output and detours remain on the legacy relation/output view.
- Completed: removed the now-unreferenced `append_innerdicts_from_rows_table`.
- Completed: declared the common two-column schema and the three ordered source
  relations in `schema.py`.
- Completed: added `materialize_innerdicts_from_rows_table` as the single
  pandas group/drop/JSONL writer used by steps 7, 8, and 9.
- Completed: cast both bounded `ktp.ssn_sum_hit_1pct` aggregates to `BIGINT`
  through a documented SSN SQL helper. The shared writer rejects any future
  `HUGEINT` source column rather than silently widening it through pandas.
- Completed: focused and repository validation.

## Consumer classification

- New JSONL table: fresh step-9 `OuterDict` hydration and resume hydration.
- Legacy rows/output view: `PARQUET_OUTPUT_VIEW` and flat detour analytics.
- Step-10 review remains on `PARQUET_OUTPUT_VIEW`.

## Findings

- Root cause of the integer regression: DuckDB promotes `SUM(INTEGER)` to
  `HUGEINT`; pandas then exposed the non-null value as `float64` (`1186.0`).
  Read-only type comparison found no second conversion in the scalar SSN
  payload. Casting this bounded aggregate result to `BIGINT` restores integer
  semantics, allowing all three sources to use the same pandas writer and its
  explicit missing-value-to-`null` normalization.
- Draw-label follow-up completed: `PARQUET_LEGACY_ROWS_INNERDICT_TABLE` retains
  `ktp.draw_number`, so the SSN JSONL payload and fresh/resumed `OuterDict`
  retain it. `PARQUET_OUTPUT_VIEW` now uses that existing value for sorting and
  projection; its redundant `source_draw` CTE/join and final draw exclusion
  were removed. The Step 9 output and Step 10 partition/review artifacts thus
  expose exactly one `ktp.draw_number`, with no suffixed duplicate.
- No other downstream adaptation is required: cards and partition state
  already recognize `ktp.draw_number`, partition review reads it from the
  partition table, resume uses the same JSONL loader, and detours either select
  named SSN columns or ignore unrelated extras. Cards will now also render the
  draw field inside each SSN innerdict body, in addition to using it in the
  card header; this is an expected visible consequence unless `DRAW_LABEL` is

## Verification

- Shared-writer tests: 6 passed across all three declared source/target
  contracts, covering exact schema, ordered hydration, JSON string
  preservation, SQL `NULL` to JSON `null`, empty inputs, the `HUGEINT` guard,
  and `1186` remaining an integer.
- Existing focused pipeline tests: 83 passed, 1 skipped, 4 deselected,
  6 xfailed, 1 xpassed. Final innerdict/init/step-9/step-10 gate: 21 passed.
- Read-only whole-table parity: the pandas writer reproduced all 304 source
  keys / 2,044 records with zero differences after normalizing only
  `ktp.ssn_sum_hit_1pct` from integral float to integer. No other payload value
  or serialization changed.
- Detours from the preceding phases remain verified: mode 0 passed 4/4 in its
  optional pixi environment and mode 3 passed 6/6 in the default environment.
- Ruff passed for every touched Python file. Repository mypy passed with no
  issues in 67 source files.
- Repository suite excluding live `real_api`: 139 passed, 3 skipped,
  4 deselected, 6 xfailed, 1 xpassed. Its sole failure is the unrelated,
  already-known missing external Linux ARM64 `splink_udfs` binary.
- The supplied database was opened read-only and was not mutated. `src.repl`
  was neither run nor imported. No Git command was used.
