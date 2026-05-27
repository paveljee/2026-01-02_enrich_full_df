# WORK

## Current State

- SPEC approved; implementation is authorized.
- Must not run `src.repl` or the full pipeline command.
- If database context is needed, use only `data/scisci_process.duckdb` read-only.
- Git usage remains read-only; do not stage/unstage.

## Plan

1. Add shared DuckDB-callable matching helpers for XLSX, SciSciNet, and DOCX.
2. Add config knobs with default `false` and set them in `config.repl.json`.
3. Wire XLSX and SciSciNet steps through the knobs while preserving v1 behavior.
4. Rework step 10 review view aggregation to show all available same-domain
   values per source key with newline/`-----` cell merging.
5. Add three dedicated pytest/DuckDB test files under `tests/`.
6. Run focused tests/lint where practical and record results.

## Doing Now

- Final verification and cleanup.

## Done

- Re-read `tasks/tasks-20260526-match-patch/SPEC.md` human text.
- Re-read inherited prerequisites in `tasks/tasks-20260519-review-231/SPEC.md`.
- Updated the AI section to include the `./WORK.md` workbook requirement and to
  restate the task contract cleanly.
- Updated the AI section again for the latest human SPEC changes: workbook notes
  allowance and separate XLSX/DOCX/SciSciNet test files.
- Re-read approved SPEC and inherited prerequisites before implementation.
- Re-inspected current XLSX, DOCX, SciSciNet, config, and test/tooling context.
- Human clarification during implementation: preserve the psyche of the original
  code and avoid redesign; v1/default matching must not regress.
- Human clarification during implementation: implement matching procedures in
  DuckDB query logic for performance; helpers should centralize SQL, not move
  matching into Python callbacks.
- Added SQL-only `src.helpers.name_matching` helpers for XLSX, SciSciNet, and
  DOCX matching. XLSX v1 emits the original SQL fragments; XLSX v2 emits inline
  DuckDB SQL without Python callbacks or macros.
- Wired `xlsx_match_name_tokens_v2` and `sciscinet_match_strip_tokens` config
  knobs, both defaulting to `false` in `config.repl.json`.
- Removed orphan Python XLSX token comparator code from `name_matching.py`.
- Updated DOCX and SciSciNet steps to use the shared matching helper while
  preserving existing default behavior.
- Updated step 10 review context to aggregate all available same-domain values
  per source key, newline-separated or `-----`-separated when any value is
  multiline.
- Added dedicated DuckDB pytest files:
  `tests/test_xlsx_name_matching.py`, `tests/test_docx_name_matching.py`, and
  `tests/test_sciscinet_name_matching.py`. Tests load `splink_udfs` and use
  DuckDB `unaccent`, matching production.
- Added step 10 review aggregation coverage in `tests/test_step_10_build_cards.py`.
- Fixed a step 10 review-view regression where DuckDB inferred JSON for
  `ktp.hcr_world_bank_economies` across `UNION ALL` branches, then attempted to
  cast newline-merged review context text back to JSON. Review-domain columns
  are now selected as `VARCHAR` display values, including primary-domain rows.
- Added regression coverage for JSON-typed XLSX context values in the partition
  review view.
- Compared `tmp/output-old/` and `tmp/output-new/` after user-provided rerun.
  File sets match exactly: 231 cards in each tree; 191 files differ by content.
  All changed card fields are `ktp.ssn_field_display_names_list`; across 2,403
  changed occurrences, old and new lists have identical multisets of values and
  differ only in ordering. No added/removed cards or changed match/review fields
  were found in the card text outputs.
- Root cause of output churn: `step_09_match_parquet.py` builds
  `ktp.ssn_field_display_names_list` with `LIST(DISTINCT ...)` and no
  `ORDER BY`, so DuckDB can emit nondeterministic list order when the plan
  changes. This appears to be output-order noise rather than a semantic match
  regression.
- Surgically patched `ktp.ssn_field_display_names_list` aggregation to order
  alphabetically by the field display value while preserving the same distinct
  fallback-to-field-id expression.

## Verification

- Previous AI-section readback completed before implementation approval.
- `pixi run pytest tests/test_xlsx_name_matching.py tests/test_docx_name_matching.py tests/test_sciscinet_name_matching.py tests/test_step_10_build_cards.py -q`
  passed: 24 passed.
- `pixi run ruff` passed.
- `pixi run pre-commit` ran; ruff and mypy passed, then the full test task
  failed in unrelated existing detour tests due missing optional
  `detour-mode0-econ-stats` plotting dependencies (`plotly`) and FY26 fixture
  expectations in `tests/test_detour_step4_breakdown.py`. The new focused
  matching and step 10 tests passed within that run.
- User reran `pixi run pytest tests/test_step_10_build_cards.py -q` after the
  JSON display-value fix: 7 passed.
- Local DuckDB smoke probe could not run in this shell after interruption due
  `_duckdb` import failure from the pixi environment; no pipeline command was
  attempted.
- After pixi was fixed, verified the ordered `LIST(DISTINCT ... ORDER BY ...)`
  DuckDB syntax with a focused in-memory query; output was deterministic:
  `[3, Alpha, Beta]` for fallback field id plus display-name values.
- `pixi run python -m py_compile src/steps/step_09_match_parquet.py` passed.
- `pixi run ruff` passed.
- Re-ran `pixi run pre-commit`; ruff and mypy passed, full pytest still failed
  only in existing detour tests due missing optional `plotly` for
  `detour-mode0-econ-stats` and FY26 fixture expectations in
  `tests/test_detour_step4_breakdown.py`. Focused matching and step 10 tests
  passed in that run.
