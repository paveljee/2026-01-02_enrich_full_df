# SSN innerdict schema and source-key JSON workbook

## Constraints

- Specification only; no application implementation in this task.
- Preserve the human section of `SPEC.md`.
- Never run or import `src.repl`. Git use is read-only; do not stage or unstage.
- The only inspected data artifact was
  `data/scisci_process.duckdb`, opened with `read_only=True`.
- Code/config/tests were inspected read-only. No other `data/` or `.aicode/`
  artifacts were consulted.

## Status

- Completed: re-read the updated human section after the added DuckDB JSON
  requirement and re-read the linked prerequisite.
- Completed: traced fresh-run and resume paths through steps 6-10,
  `OuterDict`, innerdict persistence helpers, output views, and both current
  detours.
- Completed: inspected the supplied database schemas and cardinalities
  read-only. Loaded `splink_udfs` before evaluating output views.
- Completed: wrote the minimal coherent implementation and acceptance contract
  into the AI section of `SPEC.md`.

## Read-only baseline

| relation | current shape | current count |
|---|---|---:|
| `outerdict_stub` | `name_key`, `innerdicts` | 307 keys |
| `xlsx_innerdicts` | `name_key`, `innerdicts` | 307 keys / 2,018 JSONL records |
| `docx_innerdicts` | `name_key`, `innerdicts` | 307 keys / 317 JSONL records |
| `ssn_innerdicts` | wide, 304 distinct `ktp.source_key` values | 2,044 rows |
| `ssn_parquet_output` | wide view | 2,044 rows |

All 307 outerdict keys are valid JSON with non-null first and last names.
Current XLSX and DOCX JSONL record totals equal their flat output-view row
counts. Current SSN table and output-view row totals also agree.

## Settled contract

- `xlsx_innerdicts`, `docx_innerdicts`, and `ssn_innerdicts` each become the
  same exact two-column JSONL store:
  `ktp.source_key`, `ktp.innerdicts`.
- Preserve an internal materialized wide SSN row relation and keep
  `ssn_parquet_output` wide. Aggregate only the public innerdict store; do not
  force downstream SQL to repeatedly unpack it.
- Use one writer and one loader for all three stores. Fresh execution and
  resume must hydrate equivalent outerdicts.
- DuckDB alone converts names to source-key JSON and source-key JSON back to
  names. Python carries the produced key opaquely.
- The DuckDB-only boundary does not encompass unrelated match/config/log/body
  JSON.
- Treat the change as new-build-only. No old-schema migration or dual-read
  compatibility is in scope.

## Impact map for the executor

- Constants/schema: `src/helpers/vars.py`, `src/helpers/schema.py`.
- Source-key ownership/in-memory identity:
  `src/helpers/data_models/outer_dict.py`,
  `src/steps/step_06_build_outerdict_stub.py`,
  `src/helpers/init_pipeline.py`, and keyed step-10 paths.
- Shared innerdict persistence:
  `src/helpers/duckdb_utils.py` and steps 7-9.
- Flat consumers: `ssn_parquet_output`, step-10 review SQL,
  `detour_mode0_econ_stats.py`, and `detour_mode3_pgf_stats.py`.
- Tests/fixtures: outerdict, init/resume, steps 6-10, and both detours. Test
  source keys must also be DuckDB-produced.

## Verification

- `src.repl` was not run or imported.
- View checks used `LOAD splink_udfs` before querying
  `xlsx_output`, `docx_output`, or `ssn_parquet_output`.
- No source, fixture, database, or application file was modified; only this
  task's Markdown specification/workbook were edited.
- No application test suite was run because this task only scopes the later
  implementation.
