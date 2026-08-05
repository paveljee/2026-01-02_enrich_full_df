# Tighten API — planning workbook

## Status

- Reviewed the major human-contract revamp and updated only the AI-authored section of `SPEC.md`.
- Reflected the latest sample wording that links each footnote to its numbered raw web-run query, FCO timestamp, and exact result URL.
- Reflected the newer card sample's programmatic `AI-generated text` label, quoted values, footnote placement, and matching comment form.
- Clarified that each schema `pkey` placeholder means a primary key whose concrete column name is `id`.
- No production implementation is in progress. `test_api.py` is at the user-restored baseline.
- Git use remains read-only. All review commands use `pixi run`.
- `README.md`, `.env.example`, sample/ground-truth data, and main-pipeline code remain untouched.

## Context refreshed

- Re-read the prerequisite SPEC, current detour API/deployment/watcher/tests, and the July direct-web rollout plus its annotation/response.
- Reviewed `step_08_match_docx.py`, `docx_parse.py`, `duckdb_utils.py`, common innerdict/data models, `cards.py`, and step 10 card assembly.
- Reviewed `PipelineConfig.from_json()` and the sibling detour-DB derivation/isolation pattern in `detour_step4_breakdown.py` and its tests.
- Confirmed the configured source DuckDB is context only and must remain read-only; Codex relations persist in one separately derived detour DuckDB.

## Revised contract captured in SPEC

1. Preserve the existing fail-closed order: SCP rollout -> copy appendwatch report -> validate copied report -> index approved rollout -> Pydantic/SQL evidence validation -> accepted innerdict/card writes.
2. Support many `/pull`/`push` cycles in one cumulative rollout. The rollout filename can repeat; each archived physical line count demarcates the prefix used by one attempt.
3. Keep researcher identity in `ktp.source_key`/draw/name. Store the archive line count in `ktp.fragment` with fragment type `line_number`.
4. Derive one persistent sibling detour DuckDB from `config.db_file`; open the configured source DB read-only and serialize detour-DB writes.
5. Pre-index direct `function_call_output` -> unique `web_search_end` -> unique `function_call(name="run", namespace="web")` chains into the four human-specified normalized Codex tables.
6. Rename current labels to `DOCX_COLUMNS`, add ordered `AI_AUGMENT_COLUMNS`, and require every submitted excerpt to carry its exact result URL.
7. Validate exact excerpt uniqueness and exact URL equality with parameterized DuckDB queries over the current approved rollout prefix.
8. Append one accepted flat Codex row per filename/line-count fragment, then rematerialize cumulative `codex_innerdicts` under the common two-column JSONL contract.
9. Allow repeated `ktp.source_key` values: multiple accepted attempts for one researcher become multiple Codex sections, distinguished by fragment and explicit attempt ID.
10. Reuse the existing parser/materializer/card seams: detour-local `codex_parse.py`, step-08-style output/innerdict flow, and `build_cards()`/`write_cards_zip()` with Codex sections between xlsx and docx.

## Surgical implementation boundary

- Expected later edits: `api.py`, new detour-local `codex_parse.py`, focused tests, and minimum serving-task wiring for required `--config config.json`.
- Change deployment/provisioning only if the existing appendwatch implementation fails a concrete current requirement.
- Do not edit `README.md`, `.env.example`, `appendwatch.py`, main `vars.py`/`schema.py`, main pipeline, architecture assets, or sample data.
- Keep detour-owned paths, labels, table/view names, citation delimiters, bounds, context setting, and repeated numeric values as named `api.py` globals.
- Current hardcoded task remains; advancing `/pull` to a later task is explicitly out of scope.

## Planned verification

- Preserve copied-report and acquisition-order tests; add source-DB before/after immutability and deterministic detour-DB-path assertions.
- Assert exact normalized table columns/linkages, cumulative-prefix conflict handling, citation parsing, SQL parameterization, excerpt multiplicity behavior, and exact URL checks.
- Assert repeated-namekey output rows and common-innerdict JSONL ordering by rollout filename/line-count fragment/attempt ID.
- Assert footnote-to-query ordinal cross-references and web-run/FCO-time/URL wording, comments, xlsx -> Codex -> docx -> ssn card order, and both configured TXT and DOCX ZIP output.
- Reuse the existing E2E shape in `test_api.py` with fixed July excerpts/URLs and independent expected FC/FCO/call/ref identities; include one-character excerpt and URL mismatch rejection.
- Prior test results predate this redesign and are baseline history only; rerun focused and full detour suites after implementation.
