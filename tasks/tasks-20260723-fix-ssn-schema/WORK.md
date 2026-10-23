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
- Completed: incorporated the added human requirements: SSN innerdicts retain
  draw numbers, and Step 10 partition/review artifacts include mode 0.
- Completed: aligned visible draw-number ordering across XLSX, DOCX, and SSN;
  Step 9 creates `ktp.draw_number` after `ktp.fragment_type` in the
  author-output source table, so enriched, legacy, output, and JSONL rows carry
  it forward without downstream reshuffling. The Step 10 review relation
  declares the same order.
- Completed: Step 10 now materializes selected-key rows from each existing
  output view once into temporary DuckDB tables, then runs the existing review
  aggregation against those physical inputs.
- Completed: materialized the ranked review result in
  `card_partition_review_rows`; `card_partition_review` remains the same thin,
  ordered public view. Temporary source tables are dropped afterward.
- Pending: human-run verification of the Step 10 staging change.

## Consumer classification

- New JSONL table: fresh step-9 `OuterDict` hydration and resume hydration.
- Legacy rows/output view: `PARQUET_OUTPUT_VIEW` and flat detour analytics.
- Step-10 partition review continues to consume `xlsx_output`,
  `ssn_parquet_output`, and `docx_output`. Selected rows are staged once in
  temporary DuckDB tables, and a persistent derived rows table backs the
  public ordered review view.

## Step 10 bounded review design

- Input: selected `card_partitions` rows and the existing XLSX, SSN, and DOCX
  output views.
- Materialization: join each output view to `card_partitions` once and store
  the selected rows in a temporary DuckDB table before building the next one.
- Aggregation: run the existing context CTEs, seven review branches,
  placeholders, multiline merging, and ranking against those physical tables;
  their established semantics remain unchanged.
- Persistence: materialize `card_partition_review_rows` as the ranked derived
  read model; keep `card_partition_review` as the same public ordered view.
- Removed cost: the review query no longer repeatedly expands and recomputes
  the three output-view plans while producing its context and result branches.

## Findings

- Root cause of the integer regression: DuckDB promotes `SUM(INTEGER)` to
  `HUGEINT`; pandas then exposed the non-null value as `float64` (`1186.0`).
  Read-only type comparison found no second conversion in the scalar SSN
  payload. Casting this bounded aggregate result to `BIGINT` restores integer
  semantics, allowing all three sources to use the same pandas writer and its
  explicit missing-value-to-`null` normalization.
- Draw-label follow-up completed: `PARQUET_LEGACY_ROWS_INNERDICT_TABLE` retains
  `ktp.draw_number`, so the SSN JSONL payload and fresh/resumed `OuterDict`
  retain it. Step 9 obtains one source draw while creating
  `PARQUET_AUTHOR_OUTPUT_TABLE`, positions it after `ktp.fragment_type`, and
  carries that value forward for row ordering and `PARQUET_OUTPUT_VIEW`. The
  Step 9 output and Step 10 partition/review artifacts thus expose exactly one
  unsuffixed `ktp.draw_number` in the same position.
- No other downstream adaptation is required: cards and partition state
  already recognize `ktp.draw_number`, partition review reads it from the
  partition table, resume uses the same JSONL loader, and detours either select
  named SSN columns or ignore unrelated extras. Cards will now also render the
  draw field inside each SSN innerdict body, in addition to using it in the
  card header; this is an expected visible consequence unless `DRAW_LABEL` is
  explicitly added to the card body exclusion set.
- Mode-0 partition artifacts enabled: `CARD_PARTITION_ARTIFACT_MODES` now
  includes mode 0. The existing mode-0 selection already contains all source
  keys, so the common partition path emits resolution buckets for subset-2
  rows and the no-resolution sentinel for subset-1 rows, ordered after the
  resolution queue. Modes 3 and 4 remain unchanged. Focused verification is
  pending the human-run Step 10 test command.

## Verification

The results below predate the Step 10 output-view staging change. Per the human
instruction, the AI will not run tests; updated verification is pending the
human-run gate.

- Shared-writer tests: 6 passed across all three declared source/target
  contracts, covering exact schema, ordered hydration, JSON string
  preservation, SQL `NULL` to JSON `null`, empty inputs, the `HUGEINT` guard,
  `1186` remaining an integer, and `ktp.draw_number` surviving hydration.
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
