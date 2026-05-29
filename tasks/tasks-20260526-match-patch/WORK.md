# WORK

## Current State

- SPEC approved; implementation is authorized.
- Must not run `src.repl` or the full pipeline command.
- If database context is needed, use only `data/scisci_process.duckdb` read-only.
- Git usage remains read-only; do not stage/unstage.

## Plan

1. Wire `match_rule_version` through config and all matching steps.
2. Keep XLSX v1/v2 behavior in the existing DuckDB equality-key helper shape.
3. Add DOCX/SSN match-rule metadata payload entries.
4. Create/reuse the derived `ktp_author_details_unnest` resource inside the
   existing resource registration flow, with parquet footer rule-version
   metadata.
5. Point step 9 at the derived SSN key parquet and keep matching as DuckDB
   equality joins.
6. Patch step 10 review output to aggregate all available innerdict context,
   including partition 0 rows.
7. Update focused tests and run focused verification plus `pixi run pre-commit`.

## Doing Now

- Ready for user rerun/benchmark of `match_rule_version.ssn_hit = 2`.

## Done - Final Patch

- Cut config over to `match_rule_version` (`xlsx_name`, `docx_name`, `ssn_name`,
  `ssn_hit`) and removed the active `name_matching_rule_version` path.
- Centralized the new SSN hit audit column names and raw author-details column
  names in `src/helpers/vars.py`.
- Added the `ssn_author_matches_hit_selected` view: v1 aliases the existing
  nonzero-hit view exactly; v2 reduces only name keys with Tukey outliers to the
  max raw `works_count` outlier(s), while no-outlier name keys fall back to all
  nonzero-hit candidates.
- Updated step 9 downstream enrichment joins to consume the hit-selected SSN
  author-match view.
- Removed the legacy metadata-key fallback path per user direction; derived
  `ktp_author_details_unnest` parquet now expects the footer key
  `match_rule_version.ssn_name`. Any existing derived parquet carrying only the
  old footer key must be regenerated or replaced before reuse.
- Added focused tests for the new `match_rule_version` config shape, rejection
  of the stale `name_matching_rule_version` shape, SSN hit v1 alias behavior,
  SSN hit v2 Tukey max-work selection/ties, and no-outlier fallback to v1.
- Inspected `tmp/duckdb_ui_20260527T2115Z_export.csv`. It is grouped by
  `ktp.source_key`, not row-level candidate data, so it is useful for edge-case
  selection but not as a direct fixture for reconstructing candidate metrics.
- Added `src/helpers/ssn_hit_selection.py` to centralize SSN hit SQL factories:
  zero-hit count, nonzero-hit candidate view, v1/v2 hit-selected view, and
  selected-author-id view. `name_matching.py` remains focused on name-key SQL.
- Updated step 9 to call the SSN hit-selection helper instead of carrying the
  selection SQL inline.
- Added SSN hit tests for nonzero-hit filtering and for the v2 rule's key edge
  case: when a name key has Tukey outliers, choose max raw `works_count` only
  among outlier rows, not across all nonzero-hit candidates. The test uses a
  `Dabing Zhang` source key drawn from the exported edge-case results.
- Fixed the XLSX v1 payload test mypy issue by asserting the DuckDB `fetchone()`
  result is present before indexing it.
- Read the failed hit-rule-v2 REPL log at
  `data/diagnostics/20260529_154745_mode1_v2_ssn_hit_v2_fail/repl_session.log`
  against the previous v2/v1-hit log. The run matches through nonzero-hit
  aggregation, then v2 selection reduces 2,824 nonzero-hit rows to 312 selected
  rows across 304 name keys and 306 author IDs before failing in generated
  author-output SQL.
- Root cause of the failure: the injected v2 `ktp.ssn_hit_fallback_no_tukey_outlier`
  select-list alias is missing its closing quote before the next
  `ssnap.filename` provenance column.
- Added the SSN hit v2 follow-up to the AI interpretation: parse-safe metadata
  select-list injection, detailed Tukey/selection logging, production-SQL-based
  breakdowns, and plain step 9 logging plumbing without generic row-dict helper
  indirection.
- Fixed the v2 metadata select-list fragment by centralizing it in
  `ssn_hit_metadata_select_sql` and closing the fallback alias before downstream
  provenance columns.
- Added the narrow v2 candidate metric table SQL and breakdown SQL to
  `ssn_hit_selection.py`. The table exists only for `match_rule_version.ssn_hit = 2`;
  v1 remains the exact nonzero-hit view alias.
- Updated step 9 v2 logging to print Tukey bounds, candidate/outlier counts,
  selected/fallback counts, pruned-row counts, and selected-row multiplicity from
  production SQL results.
- Added focused SSN hit tests for v1 alias shape, v2 candidate metric setup,
  v2 selection breakdown counts, and parse-safe v2 audit-column injection before
  `ssnap.filename`.
- Verification passed: focused `tests/test_sciscinet_name_matching.py`, focused
  ruff/mypy on touched code, and full `pixi run pre-commit-repl` (80 passed, 2
  skipped).

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
- Re-read inherited prerequisites from
  `tasks/tasks-20260519-review-231/SPEC.md`, the updated match-patch human SPEC,
  and pertinent config/resource/matching/step 10 code before rewriting the
  match-patch AI interpretation.
- Updated `tasks/tasks-20260526-match-patch/SPEC.md` AI section to replace stale
  boolean-knob language with the `name_matching_rule_version` config shape,
  versioned XLSX/DOCX/SSN payload expectations, SSN precomputed author-details
  unnest parquet plan, SSN v2 punctuation-to-space equality rule, step 10
  all-innerdict review-display contract, and verification expectations.
- Clarified in the AI interpretation that `ktp_author_details_unnest` is a
  required derived runtime resource for step 9: absence from config triggers
  creation during step 01, not fallback to the old giant CTE, and registration
  must stay inside the existing resource flow rather than a parallel path.
- Corrected the AI interpretation so the SSN rule version for the derived
  author-details unnest parquet is file-level metadata or a tiny manifest, not a
  repeated column across the full expanded row set.
- Tightened the derived `ktp_author_details_unnest` parquet contract to the
  intended slim row shape: `ssnad.authorid` plus centralized `ktp.alt_name`, with
  larger author-details display payloads left out of the derived match-key file.
- Added `name_matching_rule_version` config validation with supported versions:
  XLSX v1/v2, DOCX v1, and SSN v1/v2.
- Rewired step 07 to use `name_matching_rule_version.xlsx` while leaving the
  existing XLSX helper behavior in place.
- Added DOCX match payload rule metadata (`ktp.docx_match_rule = v1`).
- Added SSN v1/v2 SQL normalization helpers. SSN v1 preserves the original
  `lower(unaccent(...))` equality shape; SSN v2 uses punctuation-to-space plus
  whitespace normalization on both derived author-name keys and KTP name keys.
- Started integrating `ktp_author_details_unnest` into `register_pipeline_resources`:
  configured resources are hash-checked and sidecar-version checked, otherwise
  the default derived parquet is reused or created during step 01 using the
  existing DuckDB connection.
- Updated step 09 to require the registered derived SSN unnest resource and to
  match `OUTERDICT_NAME_VIEW` keys against `ktp.alt_name` via equality joins,
  then join back to `author_details` for display fields.
- Updated step 10 review-context SQL to keep per-domain context as typed
  `VARCHAR[]` lists until final display merge, cast source values before list
  aggregation, merge generic provenance from XLSX/SSN/DOCX, keep `ff_author_id`
  SSN-only, and include a partition-0 review branch.
- Added focused coverage for derived SSN unnest resource creation/reuse and
  sidecar rule-version validation.
- Updated SciSciNet matching tests to use rule versions and DuckDB `unaccent`,
  covering v2 punctuation-to-space normalization and the dual original/
  punctuation-space author-key expansion.
- Updated step 10 review tests to expect all available XLSX/SSN/DOCX provenance
  context, SSN-only `ff_author_id`, JSON-safe display casting, and non-empty
  partition-0/subset1 review output.
- Updated detour step-4 test fixtures so `author_details.parquet` is a tiny valid
  parquet (needed now that step 01 creates `ktp_author_details_unnest`) and the
  fixture World Bank workbook uses the current FY26 column.
- Updated the AI interpretation to require parquet footer key-value metadata for
  the derived `ktp_author_details_unnest` rule version, matching the human
  wording that the parquet itself bears the version.
- Moved the derived parquet metadata key constant
  `AUTHOR_DETAILS_UNNEST_RULE_VERSION_METADATA_KEY` into `vars.py` alongside
  `KTP_AUTHOR_DETAILS_UNNEST_KEY`.
- Removed the resource-local `_sql_string_literal`; resource paths and metadata
  values now use DuckDB parameters, with the remaining `KV_METADATA` key literal
  escaping centralized as `duckdb_string_literal` in `duckdb_utils.py`.
- Wired the latest first-run resource logging and step 09 parser findings into
  the AI interpretation: derived unnest creation must log live before the heavy
  DuckDB `COPY`, and step 9 must cleanly consume the derived parquet without
  stale CTE punctuation.
- Added a `log` hook through resource registration, used by step 01 to
  print the heavy `ktp_author_details_unnest` creation warning, output path, and
  active SciSciNet rule version before creation starts.
- Removed the stale comma after the step 09 `names` CTE so the derived-parquet
  equality-join query parses under DuckDB.
- Added focused coverage that first-run `ktp_author_details_unnest` creation
  emits the live heavy-operation progress messages.
- User reported step 9 now peaks around 8 GB instead of the earlier ~2 GB. The
  likely low-risk culprit is that the first author-name match materialization
  joins the 131.8M-row `ktp_author_details_unnest` back to full
  `author_details` immediately, carrying `display_name` and
  `display_name_alternatives` before nonzero-hit pruning even though those
  payloads are fetched again later from the filtered author_details table.
- Added AI-spec implementation guidance for the intended surgical step 9 RAM
  fix: keep `PARQUET_AUTHOR_MATCH_TABLE` narrow (`name_key`, KTP name fields,
  `ssnad.authorid`, and `ktp.ssnad_match`) and remove the early full
  `author_details` join from that first match query. Preserve the existing
  two-column `ktp_author_details_unnest` resource schema for now.
- Read-only/user-provided evidence for future optimization: the v1 unnest parquet
  has 131,843,627 author/name rows and 87,228,294 distinct `ktp.alt_name` values;
  source `tmp/sciscinet_author_details.parquet` has 100,418,971 rows, exact
  unique author IDs, and every authorid is `A` plus 10 digits. A future
  `strings`/`id_map` normalized lookup could use numeric `BIGINT` author IDs
  internally, but that is a separate benchmark/design path rather than the
  immediate patch.
- Reflected the priority decision in the AI spec: normalized DuckDB lookup,
  distinct string tables, sorted `sid` maps, and numeric author IDs are plausible
  second-generation optimizations, but the measured dedupe factor is moderate
  and none of those directly explains the 8 GB regression as clearly as the
  redundant early wide `author_details` join. Priority remains: first make the
  initial step 9 match table narrow, then re-measure, then benchmark broader
  resource-schema changes only if needed.
- Implemented the surgical step 9 RAM fix: the initial author-name match table
  now joins only KTP name keys to `ktp_author_details_unnest`, keeps narrow match
  fields, and defers full `author_details` display payloads to the existing
  post-pruning filtered author-details materialization.
- Read HEAD commit body and agreed with the noted minor issue: pure XLSX v1
  payloads should include `ktp.xlsx_match_rule = "v1"` for consistency with v2,
  DOCX, and SSN payload metadata.
- Patched XLSX v1 payload generation to emit the rule key. Step 10 exactness now
  distinguishes scalar-last-name pure v1 payloads from list-shaped v1 fallback
  payloads produced inside XLSX v2 mode, preserving the existing behavior that
  v2-mode v1 fallback rows are non-exact for partitioning.
- Re-read the updated human SPEC and the referenced task-local DuckDB UI query
  `tasks/tasks-20260526-match-patch/context/duckdb_ui_20260527T2115Z.sql`.
  The query is useful for Tukey outlier definitions and the three SSN hit
  metrics, but the human prose supersedes its ranking/tie-breaker behavior.
- Updated the AI interpretation for the final patch: config is now
  `match_rule_version` with `xlsx_name`, `docx_name`, `ssn_name`, and `ssn_hit`;
  `name_matching_rule_version` is stale; the unnest parquet rule metadata should
  refer to `match_rule_version.ssn_name`; and SSN hit v2 should filter nonzero
  candidates to Tukey outliers, then keep max raw `works_count` outliers per
  name key, preserving max-work ties for subset 2 review.
- Clarified in the AI interpretation that the referenced SQL's secondary
  ordering by hit/citation metrics should not be copied, that no-outlier SSN hit
  v2 groups fall back to v1 by retaining all nonzero-hit candidates, and that
  downstream step 9 should consume one effective author-match view after hit
  selection.

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
- `pixi install` was needed once because the default Pixi environment directory
  was missing locally; after that, `pixi run python --version` reported Python
  3.14.3.
- `pixi run python -m py_compile src/helpers/config.py src/helpers/name_matching.py src/helpers/resources.py src/helpers/init.py src/steps/step_01_register_resources.py src/steps/step_07_match_xlsx.py src/steps/step_08_match_docx.py src/steps/step_09_match_parquet.py src/steps/step_10_build_cards.py`
  passed.
- `pixi run pytest tests/test_xlsx_name_matching.py tests/test_docx_name_matching.py tests/test_sciscinet_name_matching.py tests/test_author_details_unnest_resource.py tests/test_step_10_build_cards.py -q`
  passed: 34 passed.
- `pixi run pytest tests/test_detour_step4_breakdown.py -q` passed: 4 passed,
  1 skipped.
- `pixi run ruff` passed.
- `pixi run mypy` passed.
- Re-ran `pixi run pre-commit`; ruff and mypy passed, full pytest reported
  84 passed, 3 skipped, and 2 failed. The remaining failures are the existing
  default-environment optional dependency issue in
  `tests/test_detour_mode0_econ_stats.py`: `plotly`/Kaleido are only available
  through the `detour-mode0-econ-stats` Pixi environment.
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
- Latest post-implementation focused run:
  `pixi run pytest tests/test_xlsx_name_matching.py tests/test_docx_name_matching.py tests/test_sciscinet_name_matching.py tests/test_author_details_unnest_resource.py tests/test_step_10_build_cards.py -q`
  passed: 34 passed.
- Latest detour step-4 fixture run:
  `pixi run pytest tests/test_detour_step4_breakdown.py -q` passed: 4 passed,
  1 skipped.
- Latest `pixi run pre-commit`: ruff and mypy passed; full pytest reported
  84 passed, 3 skipped, and 2 failed only in
  `tests/test_detour_mode0_econ_stats.py` because the default Pixi environment
  does not include the optional Plotly/Kaleido dependencies for SVG output.
- Latest syntax check:
  `pixi run python -m py_compile src/helpers/resources.py src/steps/step_01_register_resources.py src/steps/step_09_match_parquet.py tests/test_author_details_unnest_resource.py`
  passed.
- Latest focused run:
  `pixi run pytest tests/test_author_details_unnest_resource.py tests/test_xlsx_name_matching.py tests/test_docx_name_matching.py tests/test_sciscinet_name_matching.py tests/test_step_10_build_cards.py -q`
  passed: 34 passed.
- Latest `pixi run pre-commit-repl` passed: ruff passed, mypy passed, and full
  default pytest passed with 72 passed and 2 skipped.
- Step 9 narrow-match-table patch syntax check:
  `pixi run python -m py_compile src/steps/step_09_match_parquet.py` passed.
- Step 9 narrow-match-table patch focused run:
  `pixi run pytest tests/test_author_details_unnest_resource.py tests/test_xlsx_name_matching.py tests/test_docx_name_matching.py tests/test_sciscinet_name_matching.py tests/test_step_10_build_cards.py -q`
  passed: 34 passed.
- Step 9 narrow-match-table patch `pixi run pre-commit-repl` passed: ruff
  passed, mypy passed, and full default pytest passed with 72 passed and 2
  skipped.
- XLSX v1 rule-payload patch syntax check:
  `pixi run python -m py_compile src/helpers/name_matching.py src/steps/step_10_build_cards.py tests/test_xlsx_name_matching.py tests/test_step_10_build_cards.py`
  passed.
- XLSX v1 rule-payload patch focused retry:
  `pixi run pytest tests/test_xlsx_name_matching.py tests/test_step_10_build_cards.py -q`
  passed: 26 passed. The first direct focused attempt hit a transient Pixi
  `_duckdb` import failure before collection, but the same tests passed in this
  retry and inside `pre-commit-repl`.
- XLSX v1 rule-payload patch `pixi run pre-commit-repl` passed: ruff passed,
  mypy passed, and full default pytest passed with 74 passed and 2 skipped.
- Final match-patch syntax check:
  `pixi run python -m py_compile src/helpers/config.py src/helpers/vars.py src/helpers/resources.py src/helpers/schema.py src/steps/step_07_match_xlsx.py src/steps/step_09_match_parquet.py tests/test_author_details_unnest_resource.py tests/test_sciscinet_name_matching.py`
  passed.
- Final match-patch focused run:
  `pixi run pytest tests/test_xlsx_name_matching.py tests/test_docx_name_matching.py tests/test_sciscinet_name_matching.py tests/test_author_details_unnest_resource.py tests/test_step_10_build_cards.py -q`
  passed: 39 passed.
- Final match-patch `pixi run pre-commit-repl` passed: ruff passed, mypy passed,
  and full default pytest passed with 77 passed and 2 skipped.
- SSN hit-selection helper split syntax check:
  `pixi run python -m py_compile src/helpers/name_matching.py src/helpers/ssn_hit_selection.py src/steps/step_09_match_parquet.py tests/test_sciscinet_name_matching.py`
  passed.
- SSN hit-selection helper split focused run:
  `pixi run pytest tests/test_sciscinet_name_matching.py -q` passed: 8 passed.
- SSN hit-selection helper split targeted lint:
  `pixi run python -m ruff check src/helpers/ssn_hit_selection.py src/steps/step_09_match_parquet.py tests/test_sciscinet_name_matching.py`
  passed.
- SSN hit-selection helper split focused suite:
  `pixi run pytest tests/test_xlsx_name_matching.py tests/test_docx_name_matching.py tests/test_sciscinet_name_matching.py tests/test_author_details_unnest_resource.py tests/test_step_10_build_cards.py -q`
  passed: 41 passed.
- Latest `pixi run pre-commit-repl` passed: ruff passed, mypy passed, and full
  default pytest passed with 79 passed and 2 skipped.
- XLSX payload typing fix checks:
  `pixi run python -m mypy tests/test_xlsx_name_matching.py`,
  `pixi run python -m ruff check tests/test_xlsx_name_matching.py`, and
  `pixi run pytest tests/test_xlsx_name_matching.py -q` all passed; pytest
  reported 15 passed.
- Latest `pixi run pre-commit-repl` after the XLSX payload typing fix passed:
  ruff passed, mypy over `src tests` passed, and full default pytest passed with
  79 passed and 2 skipped.
