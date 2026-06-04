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
- Added OpenAlex work-title lookup for `GET /works/{paperid}?select=title&per_page=1&api_key=...`, with redacted JSONL cache matching before network and appended response metadata after network.
- Updated step 9 to fetch titles for distinct paper ids that survive either top-hit or top-oldest selection, then join titles into both `ktp.ssn_top_papers_hit_1pct` and `ktp.ssn_top_oldest_papers` without changing their rankings.
- Updated focused tests for date ordering, paperid tie-breaking, `TOP_K_WORKS` truncation, title-enriched JSON payloads, strict shared request-log schema, title-log resource registration, card rendering, and direct `PipelineResources` setup.

### verification

- `pixi run python -m ruff check src tests` passed.
- `pixi run pytest -q tests/test_step_09_match_parquet.py tests/test_cards.py tests/test_author_details_unnest_resource.py tests/test_sciscinet_name_matching.py tests/test_csv_sample_validation.py tests/test_step_10_build_cards.py` passed (`68 passed, 6 skipped, 6 xfailed, 1 xpassed`).
- `pixi run python -m mypy src/helpers/vars.py src/helpers/data_models/http_request_log.py src/helpers/data_models/__init__.py src/helpers/openalex.py src/helpers/resources.py src/steps/step_01_register_resources.py src/steps/step_09_match_parquet.py src/steps/step_10_build_cards.py tests/test_step_09_match_parquet.py tests/test_cards.py tests/test_author_details_unnest_resource.py tests/test_sciscinet_name_matching.py tests/test_csv_sample_validation.py` passed (`Success: no issues found in 13 source files`).
- `rg -n "SSNP_YEAR_COL|ssnp\\.year|KTP_API_LOG|api_log|OPENALEX_AUTHOR_SEARCH_LOG_SCHEMA_VERSION|OPENALEX_PAPER_TITLE_LOG_SCHEMA_VERSION|OPENALEX_LOG_SCHEMA_VERSION|openalex_ssnp_title" src tests tasks/tasks-20260602-oldest-papers/SPEC.md` only found the SPEC lines that explicitly prohibit `ssnp.year`/`SSNP_YEAR_COL`.
- `src.repl` was not run.
