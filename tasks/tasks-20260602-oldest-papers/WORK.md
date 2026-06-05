## 2026-06-03

### context reviewed

- Read the task SPEC and linked setup/spec in `tasks/tasks-20260519-review-231/SPEC.md`.
- Reviewed current step-9 SSN enrichment in `src/steps/step_09_match_parquet.py`, card rendering in `src/helpers/cards.py`, step-10 card/subset behavior in `src/steps/step_10_build_cards.py`, resource registration in `src/helpers/resources.py`, config validation in `src/helpers/config.py`, schema/vars helpers, and nearby tests.
- Confirmed `config.repl.json` already has `files_config.papers` and `src/helpers/vars.py` already has `KTP_SSN_TOP_OLDEST_PAPERS_COL` plus `TOP_K_WORKS`.
- Noted implementation follow-up: the code still needs to include `papers` in required file keys and routine resource registration.

### completed

- Filled the AI-owned section of `SPEC.md` with the intended step-9 data semantics, implementation touchpoints, logging requirements, and focused test expectations.
- Amended the AI-owned SPEC section with explicit prerequisite rules and concrete evidence of linked-doc/repo review.
- Implemented papers resource registration and global vars in `src/helpers/vars.py` / `src/helpers/resources.py`.
- Wired step 9 to filter the papers parquet, log matched/dated coverage and top-oldest reduction diagnostics, and emit `ktp.ssn_top_oldest_papers` from effective hit-selected author rows.
- Added focused tests for papers resource validation/registration, card rendering of `ktp.ssn_top_oldest_papers`, and oldest-paper SQL ordering/truncation/null-date behavior.
- Renamed observed filename provenance columns from source namespaces into the KTP namespace (`ktp.hcr_filename`, `ktp.ssnad_filename`, `ktp.ssnp_filename`, etc.) and moved HCR row provenance from `hcr.row_number` to `ktp.hcr_row_number`.
- Renamed the corresponding globals in `src/helpers/vars.py` to `KTP_*_FILENAME_COL` / `KTP_HCR_ROW_NUMBER_COL`; retained explicit `KTP_HCR_FILENAME_COL_LEGACY` and `KTP_HCR_ROW_NUMBER_COL_LEGACY` constants only for CSV sample compatibility with older exported headers.
- Used repo-documented workaround `env -u CODEX_SANDBOX_NETWORK_DISABLED apply_patch` because plain `apply_patch` failed locally with the sandbox-helper loopback error.

### verification

- `pixi run pytest -q tests/test_step_09_match_parquet.py tests/test_cards.py tests/test_author_details_unnest_resource.py` passed (`8 passed, 1 skipped`).
- `pixi run pytest -q tests/test_step_10_build_cards.py` passed (`11 passed`).
- `pixi run python -m ruff check src/steps/step_09_match_parquet.py src/helpers/vars.py src/helpers/resources.py tests/test_step_09_match_parquet.py tests/test_cards.py tests/test_author_details_unnest_resource.py` passed.
- `pixi run python -m mypy src/steps/step_09_match_parquet.py src/helpers/vars.py src/helpers/resources.py tests/test_step_09_match_parquet.py tests/test_cards.py tests/test_author_details_unnest_resource.py` passed.
- `pixi run python -m ruff check src tests` passed after namespace rename.
- `pixi run python -m mypy src/helpers/vars.py src/helpers/resources.py src/steps/shared.py src/steps/step_02_load_xlsx.py src/steps/step_03_infer_names.py src/steps/step_04_add_economy_priority.py src/steps/step_05_sampling.py src/steps/step_07_match_xlsx.py src/steps/step_09_match_parquet.py src/steps/step_10_build_cards.py src/detours/detour_step4_breakdown.py src/detours/detour_mode0_econ_stats.py tests/test_step_09_match_parquet.py tests/test_cards.py tests/test_author_details_unnest_resource.py tests/test_step_10_build_cards.py tests/test_sciscinet_name_matching.py tests/test_csv_sample_validation.py tests/test_xlsx_name_matching.py tests/test_detours/test_detour_mode0_econ_stats.py tests/test_detours/test_detour_step4_breakdown.py` passed (`21 source files`).
- `pixi run pytest -q tests/test_step_09_match_parquet.py tests/test_cards.py tests/test_author_details_unnest_resource.py tests/test_step_10_build_cards.py tests/test_xlsx_name_matching.py tests/test_sciscinet_name_matching.py tests/test_csv_sample_validation.py tests/test_detours/test_detour_step4_breakdown.py` passed (`82 passed, 7 skipped, 6 xfailed, 1 xpassed`).
- `pixi run -e detour-mode0-econ-stats pytest -q tests/test_detours/test_detour_mode0_econ_stats.py` passed (`4 passed`, warnings from plotly/kaleido deprecations).
- A focused `src`/`tests` search found old `hcr.filename` / `hcr.row_number` labels only in `KTP_HCR_*_LEGACY` constants; historical task specs and chat logs still contain archival mentions.
- `src.repl` was not run.

## 2026-06-04

### completed

- Re-read the approved SPEC revision after the date/title/log-schema edits.
- Implemented the final oldest-paper payload with `ssnp.date`, `openalex.title`, and `ktp.ssnp_paperid_url`; no `ssnp.year` field, no year fallback, and no `SSNP_YEAR_COL` compatibility path remain in `src` or `tests`.
- Added the strict generic HTTP request log model/helper in `src/helpers/data_models/http_request_log.py` and reused `KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION = 1` for both OpenAlex author search and OpenAlex work-title logs.
- Added/reused the separate `openalex_paper_title_log` resource and included it in resource registration / downstream resource filename accounting.
- Added an earlier one-paper OpenAlex work-title lookup for `GET /works/{paperid}?select=title&per_page=1&api_key=...`; this is superseded by the 2026-06-05 batch/parquet SPEC revision and should not guide current implementation.
- Updated step 9 to fetch titles for distinct paper ids that survive either top-hit or top-oldest selection, then join titles into both `ktp.ssn_top_papers_hit_1pct` and `ktp.ssn_top_oldest_papers` without changing their rankings.
- Updated focused tests for date ordering, paperid tie-breaking, `TOP_K_WORKS` truncation, title-enriched JSON payloads, strict shared request-log schema, title-log resource registration, card rendering, and direct `PipelineResources` setup.

### verification

- `pixi run python -m ruff check src tests` passed.
- `pixi run pytest -q tests/test_step_09_match_parquet.py tests/test_cards.py tests/test_author_details_unnest_resource.py tests/test_sciscinet_name_matching.py tests/test_csv_sample_validation.py tests/test_step_10_build_cards.py` passed (`68 passed, 6 skipped, 6 xfailed, 1 xpassed`).
- `pixi run python -m mypy src/helpers/vars.py src/helpers/data_models/http_request_log.py src/helpers/data_models/__init__.py src/helpers/openalex.py src/helpers/resources.py src/steps/step_01_register_resources.py src/steps/step_09_match_parquet.py src/steps/step_10_build_cards.py tests/test_step_09_match_parquet.py tests/test_cards.py tests/test_author_details_unnest_resource.py tests/test_sciscinet_name_matching.py tests/test_csv_sample_validation.py` passed (`Success: no issues found in 13 source files`).
- `rg -n "SSNP_YEAR_COL|ssnp\\.year|KTP_API_LOG|api_log|OPENALEX_AUTHOR_SEARCH_LOG_SCHEMA_VERSION|OPENALEX_PAPER_TITLE_LOG_SCHEMA_VERSION|OPENALEX_LOG_SCHEMA_VERSION|openalex_ssnp_title" src tests tasks/tasks-20260602-oldest-papers/SPEC.md` only found the SPEC lines that explicitly prohibit `ssnp.year`/`SSNP_YEAR_COL`.
- `src.repl` was not run.

### follow-up fix

- Added one `TABLE/EFF` log line per OpenAlex work-title lookup, mirroring the per-check `OpenAlex author check ...` logging rather than only emitting the aggregate title summary.

## 2026-06-05

### context reviewed

- Re-read the full current `SPEC.md`, including the revised human section that replaces per-paper title requests with batched OpenAlex `/works?filter=openalex_id:...|...&select=id,title&per_page=100` requests.
- Re-read linked prerequisites in `tasks/tasks-20260519-review-231/SPEC.md` and relevant context in `tasks/tasks-20260526-match-patch/SPEC.md`; `src.repl` was not run and no `data/` artifacts were inspected.
- Reviewed current Step 9 top-work/top-oldest CTEs, OpenAlex helper code, HTTP request-log model, resource registration, author-details unnest parquet metadata pattern, config keys, and focused tests.

### completed

- Revised the AI-owned SPEC section to reflect the new title-cache architecture: JSONL remains an append-only request/response log, while reusable title lookup must happen from a registered OpenAlex paper-title parquet with footer metadata containing the title JSONL hash.
- Specified that title IDs are the distinct union of already top-K-reduced top-work IDs and already top-K-reduced top-oldest IDs, so title requests must not cover every selected author paper.
- Specified batch-only OpenAlex title fetching in chunks of at most 100 IDs, parquet rebuild from JSONL after missing-title batches, and Step 9 title joins from parquet only.
- Added expected logging and tests for parquet reuse/rebuild, JSONL hash metadata, batch requests, missing IDs, and unchanged top-work/oldest ranking semantics.

### implementation completed

- Implemented the CQRS title path from the approved SPEC:
  JSONL remains the strict append-only OpenAlex HTTP request log, and the
  registered OpenAlex paper-title parquet is the Step 9 read model.
- Added the OpenAlex paper-title parquet resource to `PipelineResources`
  and resource registration. Registration creates the parquet from the
  title JSONL when missing, validates footer metadata against the
  configured title-log SHA-256 when present, and raises on mismatch.
- Kept OpenAlex title parsing, batch fetching, JSONL-to-parquet rebuild,
  and parquet metadata validation under `src/helpers/openalex.py`.
- Step 9 now derives needed title IDs only from the union of already
  top-K-reduced top-hit papers and already top-K-reduced oldest papers,
  queries the registered parquet for coverage, fetches only missing IDs in
  `/works` batches, appends one JSONL record per batch, rebuilds the
  parquet, and then joins titles from parquet only.
- Step 9 repl logging now separates query-side read-model/hash/coverage
  messages from command-side OpenAlex batch fetch/appended-record/status
  messages. It logs aggregate title counts rather than one line per
  paper-title lookup.
- Updated the title parquet schema to use global vars for `ssnp.paperid`,
  `openalex.title`, and `ktp.openalex_received_at_unix_usec`; the final
  card payloads still contain only the SPEC-requested date/title/URL
  fields.
- Added shared local file hashing in `src/helpers/files.py` and reused it
  from resource registration, OpenAlex title read-model hashing, Step 9
  title-log hash logging, and the local-file branch of
  `RegisteredResource._compute_hash()`.
- Removed stale singleton/per-paper OpenAlex title lookup code paths and
  stale title-cache helper naming. Existing configured resource hashes,
  including a deliberate `"??"`, remain authoritative and may fail until
  the correct hash is supplied.
- Updated focused tests for batch OpenAlex title queries, strict shared
  HTTP request-log redaction, title parquet schema/metadata/rebuild,
  stale JSONL-hash rejection, needed-ID reduction semantics, and manual
  `PipelineResources` fixtures.

### verification

- `pixi run python -m ruff check src/helpers/files.py src/helpers/data_models/source_key.py src/helpers/data_models/http_request_log.py src/helpers/openalex.py src/helpers/resources.py src/steps/step_09_match_parquet.py tests/test_source_key.py tests/test_utils.py tests/test_http_request_log.py tests/test_sciscinet_name_matching.py tests/test_author_details_unnest_resource.py tests/test_step_09_match_parquet.py tests/test_csv_sample_validation.py` passed.
- `pixi run python -m mypy src/helpers/files.py src/helpers/data_models/source_key.py src/helpers/data_models/http_request_log.py src/helpers/openalex.py src/helpers/resources.py src/steps/step_09_match_parquet.py tests/test_source_key.py tests/test_utils.py tests/test_http_request_log.py tests/test_sciscinet_name_matching.py tests/test_author_details_unnest_resource.py tests/test_step_09_match_parquet.py tests/test_csv_sample_validation.py` passed (`Success: no issues found in 13 source files`).
- `pixi run pytest tests/test_source_key.py tests/test_utils.py tests/test_http_request_log.py tests/test_sciscinet_name_matching.py::test_openalex_work_titles_batch_query_preserves_work_id_filter tests/test_sciscinet_name_matching.py::test_openalex_work_titles_batch_appends_response_and_parses_titles tests/test_sciscinet_name_matching.py::test_parse_openalex_work_titles_response_handles_missing_or_malformed_results tests/test_author_details_unnest_resource.py tests/test_step_09_match_parquet.py tests/test_csv_sample_validation.py` passed (`43 passed, 1 skipped`).
- `git diff --check` passed.
- Stale-reference search found no remaining singleton title lookup names
  such as `check_openalex_work_title`, `openalex_work_title_query`, or
  `OpenAlexWorkTitleResult` in `src/helpers`, `src/steps`, or focused
  tests.
- `src.repl` was not run.

### current bug investigation

- Re-read the current task SPEC and linked prerequisite/match-patch SPECs after
  the Step 9 resume/title-parquet failures. `src.repl` was not run. The actual
  pipeline DB was inspected only as explicitly requested, using
  `data/scisci_process.duckdb` read-only.
- Current `data/pipeline_state.json` marks steps `01` through
  `09_match_parquet` complete, so resume initializes Step 10 by hydrating
  `context.outer_dict` before Step 10 itself runs.
- Current DB shape:
  - `ssn_author_output`: 2,044 rows, has `ktp.source_key`, lacks `name_key`,
    and lacks enriched top-paper/top-institution/field-display columns.
  - `ssn_innerdicts`: 2,044 rows, has `ktp.source_key`, lacks `name_key`, and
    has `ktp.ssn_top_papers_hit_1pct`, `ktp.ssn_top_oldest_papers`,
    `ktp.ssn_top_institutions`, and `ktp.ssn_field_display_names_list`.
  - `ssn_parquet_output`: view over the enriched Step 9 output, with the same
    relevant shape as `ssn_innerdicts`.
- Step 10 uses `context.outer_dict` for subset evaluation and card content. It
  uses `PARQUET_OUTPUT_VIEW` only for the partition-review artifact. Therefore
  resume should rebuild `context.outer_dict` from the same relation that
  straight-through Step 9 appended: `PARQUET_INNERDICT_TABLE` with
  `key_column=KTP_SOURCE_KEY_COL`. `PARQUET_AUTHOR_OUTPUT_TABLE` is now an
  intermediate author-level base table, not the canonical Step 9 innerdict
  resume source.
- Historical check: before commit `802ed04`, Step 9 selected
  `m.name_key AS name_key`; `802ed04` changed this to
  `m.name_key AS "{KTP_SOURCE_KEY_COL}"` and changed the live Step 9 append to
  use `key_column=KTP_SOURCE_KEY_COL`. The resume hydration path in
  `src/helpers/init_pipeline.py` stayed pointed at `PARQUET_AUTHOR_OUTPUT_TABLE`
  with the default `name_key`, which explains the current resume crash after
  Step 9.
- Current title read-model check: `data/output/openalex_paper_titles.parquet`
  has 16,622 rows and zero non-null `openalex.title` values. The old JSONL
  records used `select=title`, so OpenAlex returned title-only result objects
  without ids; that cannot safely map titles to requested paper IDs because
  response order is unreliable.
- The current human SPEC now requires `select=id,title` and explicit matching of
  request IDs to response IDs. Rebuild logic must map titles by `results[*].id`,
  keep a NULL-title row for requested IDs not returned, and decode titles to
  normal UTF-8 strings in the parquet while leaving JSONL response bodies as
  OpenAlex returned them.

### fixes completed

- Changed resume hydration to append parquet innerdicts from
  `PARQUET_INNERDICT_TABLE` using `key_column=KTP_SOURCE_KEY_COL`, preserving
  the straight-through Step 9 -> Step 10 behavior.
- Fixed OpenAlex paper-title batch query/rebuild logic to use
  `select=id,title`, map titles by returned OpenAlex id, rebuild the title
  parquet with populated `openalex.title`, and keep missing/unreturned IDs as
  NULL-title rows.
- Updated focused tests around resume hydration source and OpenAlex title
  response-order independence.

### implementation follow-up

- Updated resume hydration in `src/helpers/init_pipeline.py` to read completed
  parquet matches from `PARQUET_INNERDICT_TABLE` using `KTP_SOURCE_KEY_COL`,
  matching the live Step 9 append path and avoiding the intermediate
  `PARQUET_AUTHOR_OUTPUT_TABLE`.
- Updated OpenAlex work-title batch query construction and strict JSONL-record
  validation to require `select=id,title`; the query/log keeps the comma literal
  so it matches the SPEC shape.
- Left title parsing id-based: titles are mapped only by returned OpenAlex work
  id, never by response order. Missing/unreturned ids remain NULL-title rows in
  the rebuilt parquet.
- Added `tests/test_init_pipeline.py` to cover resume hydration from enriched
  `ssn_innerdicts` with `ktp.source_key`, and updated OpenAlex focused tests to
  prove response-order independence and missing-id handling.
- Updated the HTTP request-log test to reflect the signed-off JSONL behavior:
  records may be ASCII-escaped on disk, while parsed records still round-trip
  Unicode response bodies and the title parquet stores decoded strings.
- Updated the step-4 detour test fixture for the renamed `init_pipeline` module
  and for the strict OpenAlex title JSONL resource, and dropped the temporary
  title read-model staging table after parquet writes so detour/main DB snapshots
  stay aligned.

### follow-up verification

- `pixi run pytest -q tests/test_init_pipeline.py tests/test_sciscinet_name_matching.py::test_openalex_work_titles_batch_query_preserves_work_id_filter tests/test_sciscinet_name_matching.py::test_openalex_work_titles_batch_appends_response_and_parses_titles tests/test_sciscinet_name_matching.py::test_parse_openalex_work_titles_response_handles_missing_or_malformed_results tests/test_author_details_unnest_resource.py::test_openalex_paper_title_parquet_rebuilds_strict_batch_log tests/test_author_details_unnest_resource.py::test_openalex_paper_title_parquet_rejects_stale_log_hash` passed (`6 passed`).
- `pixi run pytest -q tests/test_detours/test_detour_step4_breakdown.py tests/test_init_pipeline.py tests/test_http_request_log.py tests/test_sciscinet_name_matching.py tests/test_author_details_unnest_resource.py tests/test_step_09_match_parquet.py tests/test_cards.py tests/test_step_10_build_cards.py` passed (`79 passed, 6 skipped, 6 xfailed, 1 xpassed`).
- `pixi run python -m ruff check src/helpers/init_pipeline.py src/helpers/openalex.py src/helpers/resources.py src/repl.py src/helpers/__init__.py src/detours/detour_step4_breakdown.py tests/test_init_pipeline.py tests/test_http_request_log.py tests/test_sciscinet_name_matching.py tests/test_author_details_unnest_resource.py tests/test_detours/test_detour_step4_breakdown.py` passed.
- `pixi run python -m mypy src/helpers/init_pipeline.py src/helpers/openalex.py src/helpers/resources.py src/repl.py src/helpers/__init__.py src/detours/detour_step4_breakdown.py tests/test_init_pipeline.py tests/test_http_request_log.py tests/test_sciscinet_name_matching.py tests/test_author_details_unnest_resource.py tests/test_detours/test_detour_step4_breakdown.py` passed (`Success: no issues found in 11 source files`).
