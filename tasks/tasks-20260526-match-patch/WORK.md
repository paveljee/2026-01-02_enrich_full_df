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

- Handoff after the XLSX v2 match-key rewrite; awaiting user-run pipeline
  validation because the inherited prerequisite forbids AI-run full pipeline
  commands.

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
- User reported that the first XLSX v2 implementation was a memory eater in the
  main pipeline. Root cause: v2 put recursive/token-sequence comparison inside
  the `JOIN ON`, preventing the cheap equality/blocking shape v1 had.
- Replaced XLSX v2 pairwise comparator with precomputed relational match keys:
  per-row compact/exact key family plus initial-expansion key family for first
  and last names, then equality joins on first and last match-key columns. V1
  SQL fragments remain unchanged. V2 base select is `SELECT DISTINCT` to remove
  duplicate key-path matches for the same source/target row.
- Added an XLSX test assertion that v2 uses key equality relations
  (`name_draw_keys` and `pop_name_keys`) rather than a pairwise recursive join
  predicate.
- Checked `sciscinet_match_strip_tokens=true` for accidental memory-shape
  regression. The SciSciNet change remains a surgical `trim(...)` wrapper around
  the existing DuckDB `lower(unaccent(...))` equality key expressions; it does
  not introduce recursive matching, lateral key expansion, or pairwise Python
  logic.
- Investigated user report that subset1 v2 produced an empty
  `10_build_cards_card_partition_review_df.csv` artifact. Root cause appears to
  be step 10 review-view filtering, not XLSX v2 matching: subset mode 1 selects
  only `subset1_ok` rows, `_partition_value(...)` labels those rows as
  `ktp.partition = 0` (`KTP_PARTITION_NO_RESOLUTION_VALUE`), and
  `_create_partition_review_view(...)` currently unions branches only for
  partition values 1, 2, and 4 (XLSX, SciSciNet, DOCX resolution buckets). Since
  `CARD_PARTITION_ARTIFACT_MODES` includes subset mode 1, the review CSV is
  emitted for subset1, but the view has no branch that can return its partition
  0 rows.
- Fixed a v2 XLSX regression found by user with `Adriano` / `Nunes-Nesi` versus
  HCR row first name `Adriano Nunes`. V2 now remains additive over original v1
  XLSX matching: in v2 mode, the helper precomputes both v2 token/fallback keys
  and original v1 first-token/last-name equality keys, tags matched rows as
  `ktp.xlsx_match_rule = "v2"` or `"v1"`, and step 07 keeps only the best rule
  path per source/HCR row, preferring `v2` over `v1`. The `use_v2=False` v1
  branch remains wired through the original v1 helper path.
- Tightened step 10 XLSX partition interpretation so a v2-mode row tagged with
  `ktp.xlsx_match_rule = "v1"` is treated as a present but non-exact XLSX match,
  sending the namekey to subset 2 as intended.

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
- After the XLSX v2 match-key rewrite,
  `pixi run pytest tests/test_xlsx_name_matching.py tests/test_docx_name_matching.py tests/test_sciscinet_name_matching.py tests/test_step_10_build_cards.py -q`
  passed: 26 passed.
- `pixi run python -m py_compile src/helpers/name_matching.py src/steps/step_07_match_xlsx.py tests/test_xlsx_name_matching.py`
  passed.
- `pixi run ruff` passed.
- `pixi run mypy` passed.
- Re-ran `pixi run pre-commit` after the XLSX v2 match-key rewrite; ruff and
  mypy passed, then full pytest reported 72 passed, 3 skipped, and 6 failed in
  the same unrelated detour areas: missing optional `plotly`/Kaleido support for
  `detour-mode0-econ-stats` and FY26 fixture expectations in
  `tests/test_detour_step4_breakdown.py`. Focused matching and step 10 tests
  passed within that run.
- Ran focused DuckDB plan probes for `sciscinet_match_strip_tokens=false` and
  `true` using the production helper SQL. Both plans used `HASH_JOIN`; neither
  plan contained nested-loop, blockwise nested-loop, or cross-product joins.
- Ran a skewed synthetic SciSciNet equality join with 500 names and 1,000,000
  author rows under `PRAGMA memory_limit='64MB'`. Both strip modes completed and
  returned 1,000,000 matches; elapsed times were roughly 0.36s without trim and
  0.40s with trim.
- `pixi run pytest tests/test_sciscinet_name_matching.py -q` passed: 3 passed.
- Ran a focused in-memory reproduction for subset1 review output: one
  `card_partitions` row with `ktp.partition = 0` plus matching XLSX/SciSciNet/DOCX
  output rows produced `partition rows: 1` and `review rows: 0`, confirming the
  empty-header CSV path without running the full pipeline.
- After the v2 XLSX additive-v1 fix,
  `pixi run pytest tests/test_xlsx_name_matching.py tests/test_step_10_build_cards.py -q`
  passed: 23 passed.
- `pixi run pytest tests/test_xlsx_name_matching.py tests/test_docx_name_matching.py tests/test_sciscinet_name_matching.py tests/test_step_10_build_cards.py -q`
  passed: 30 passed.
- `pixi run ruff` passed.
- `pixi run mypy` passed.
