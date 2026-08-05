# Tighten API — planning workbook

## Status

- Production investigation on 2026-08-05: the cumulative 252-line rollout
  archived by attempt
  `20260805T200957_806376Z_7d2bb339299a4a9cabe31bec77ca9f87`
  builds 15 eligible FC/FCO chains and 215 ref rows. Replaying the final eight
  evidence pairs against a fresh in-memory index gives five valid pairs and
  three exact-text failures: residence joined `Country of residence` and
  `Scotland` across separate numbered lines; age used one space before `|`
  where the source has two; education used ASCII `'` where the source has
  curly `’`. This is client-side normalization/retyping, not stale indexing or
  random duplicate selection. Validation stops at residence first.
- Private server diagnostics now log exact submitted excerpt/URL values for
  evidence failures and exact rejected input (or `<missing>`) for Pydantic
  failures. Logging uses repr-safe formatting so line breaks/control
  characters cannot create misleading log lines. The client 422 body now gives
  only universal verbatim-copy guidance; it still reveals no failed
  field/value, expected text, validation order, rollout/index state, or
  persistence mechanism.
- Latest rendering clarification: leave the current footnote context/Markdown
  behavior unchanged. In the human-readable footnote-arguments list only,
  search calls retain raw arguments. For `open`/`click`, each Codex turn-ref
  that resolves to one call-scoped row in the current rollout's DuckDB index
  is preserved and gains its own indexed URL in the same action object. An
  unresolved/ambiguous turn-ref, direct URL, or other non-turn value passes
  through unchanged. This is best-effort display enrichment, including for
  multi-item actions, and never uses the selected output's URL as a substitute.
  Raw `codex.fc_arguments` provenance remains unchanged in DuckDB.
- Render `ktp.ai_augment_comments` immediately after `ktp.ai_augment_links_`
  and before footnotes/arguments by keeping that order in the fresh detour
  output schema; no compatibility migration is added.
- Production finding on 2026-08-05: a normal search followed by `open` can
  place the same exact excerpt and URL in exactly two provenance rows, one
  `turn...search...` and one `turn...view...`. The latest approved policy
  allows every multiple match: filter by the submitted exact URL and randomly
  select one remaining row without action/ref preference. The retained
  `MultipleEvidenceMatches` path is visibly disabled by the named top-level
  `ALLOW_MULTIPLE_EVIDENCE_MATCHES = True` switch, not removed; its original
  test remains present and skipped.
- The accepted production TXT at
  `data/output/ai_augment_cards_20260805T182923_354844Z_d5ce3bb63b6b477c952728496a99748f/146_A_Sheikh.txt`
  records the pre-fix behavior: raw cite context rendered source
  Markdown/newlines and crossed its selected ref marker. The fix is complete at
  the rendering boundary: preserve raw DuckDB provenance, clamp to the
  excerpt's side of the selected marker, remove nested Codex citation markup
  while retaining visible label text, replace line breaks with spaces, and
  Markdown-escape the source context before applying only the intentional
  excerpt bold wrapper.
- Production finding on 2026-08-05: valid direct-web results may omit title,
  while an `Internal Error` result may omit domain and URL. The authoritative
  clarification is that only ref ID, ref URL, and cite text are required for an
  eligible ref; domain/snippet/title/thumbnail are optional provenance.
- The optional-metadata fix is complete: the typed model and regenerated
  DuckDB schema preserve nullable domain/snippet/title/thumbnail metadata and
  skip only no-URL refs. No compatibility path exists for the discarded strict
  detour DB.
- Reviewed the major human-contract revamp and updated only the AI-authored section of `SPEC.md`.
- Reflected the latest sample wording that links each footnote to its numbered raw web-run arguments, FCO timestamp, and exact result URL.
- Reflected the newer card sample's programmatic `AI-generated text` label, quoted values, footnote placement, and matching comment form.
- Clarified that each schema `pkey` placeholder means a primary key whose concrete column name is `id`.
- Latest implementation clarification: the eight non-comment push fields require evidence; comments is optional and accepts only its text value, without web excerpts.
- Production implementation is complete in `api.py`, new detour-local `codex_parse.py`, the required Pixi serving-task wiring, and focused `test_api.py` coverage.
- `test_api.py` retains the shared `prepare_real_sample_push` setup/flow for accepted and rejected real-rollout cases. Its July excerpts, URLs, and expected FC/FCO/call/ref identities are fixed independently of the production parser.
- Git use remains read-only. All review commands use `pixi run`.
- `README.md`, `.env.example`, sample/ground-truth data, and main-pipeline code remain untouched.

## Context refreshed

- After the latest compaction, re-read the complete current SPEC and the complete prerequisite `tasks/tasks-20260519-review-231/SPEC.md` before continuing.
- Re-read current detour API/parser, deployment/provisioning, appendwatch seams, and the user-restored `test_api.py` baseline; appendwatch/deployment already implement the protected root-run service contract and need no edit absent a failing focused test.
- Re-read `step_08_match_docx.py`, relevant `docx_parse.py`, `duckdb_utils.py`, common innerdict/data models/procedures, pipeline initialization loaders, `cards.py`, and step 10 card assembly.
- Re-read `PipelineConfig.from_json()`, `PipelineManager`, `repl_runtime.run_step()`, and the sibling detour-DB derivation/isolation pattern in `detour_step4_breakdown.py`.
- Confirmed the configured source DuckDB is context only and must remain read-only; Codex relations persist in one separately derived detour DuckDB.

## Repository DB/materialization conventions confirmed

- Do **not** use `PipelineManager` for the configured source DB: `connect_db()` opens read/write, sets a memory limit, and loads extensions. Read-only detours instead call `duckdb.connect(path, read_only=True)` and close in `finally`; this is the correct source-DB seam here.
- Derive exactly one persistent sibling DB per detour with the existing `<source-stem>__detour_<detour-id><suffix>` helper shape. It is cumulative across attempts; never create an attempt-local DB and never detourize/copy the source pipeline DB.
- The API route is the orchestration owner, analogous to `repl_runtime.run_step()`: it starts/commits/rolls back serialized detour write transactions. Helpers called inside that boundary should not silently own unrelated write transactions.
- Provenance indexing may commit its own serialized transaction before body validation, as the SPEC explicitly permits rejected attempts to retain appendwatch-approved normalized provenance. Accepted output-row insertion and cumulative `codex_innerdicts` rematerialization must share one later transaction.
- Follow step 08's SQL-first relation flow and `materialize_innerdicts_from_rows_table()`. The authoritative innerdict table must retain the exact common two-column schema: `name_key VARCHAR`, `innerdicts VARCHAR` containing ordered JSONL. The flat source relation must include `ktp.source_key`, contain no HUGEINT columns, and expose deterministic row order before materialization.
- Load card innerdicts through `append_innerdicts_from_jsonlines_table()` and matching procedures in pipeline order: xlsx, Codex, docx, ssn. Reuse `build_cards()` and `write_cards_zip()` unchanged.
- Import repository-owned source relation constants (`OUTERDICT_NAME_VIEW`, `SAMPLES_WITH_NAMES_VIEW`, and existing innerdict table constants) from `schema.py`; do not use relation-name string literals or add detour names to main `schema.py`/`vars.py`.
- Keep the detour writer lock across provenance persistence, evidence lookups, and accepted-output work so a later cumulative prefix cannot enter during current-prefix validation.

## Current implementation map and audit findings

- `api.py` currently has strict Pydantic models for each evidence item/field, a standalone optional evidence-free comments model, explicit eight-field submission aliases, typed compact session metadata, and typed `text_result` metadata.
- Citation delimiters are named Unicode escapes at the top of `api.py`; detour labels/table names/bounds/context constants are centralized there.
- Current rollout code reconstructs session filename, accepts only direct `response_item/function_call(name=run, namespace=web)` chains, links unique earlier FC + web-search-end + cited FCO, and builds four normalized row sets.
- Latest human contract uses generic `codex_turn_ref` provenance for search/open/click refs; preserve optional web-result `thumbnail_url` in its ninth column named exactly `codex.ref_thumbnail_url`. It remains provenance-only.
- Current DB code creates the four requested normalized relations with stable `id` primary keys/sequences, inserts or byte-compares cumulative IDs transactionally, performs parameterized exact-substring + exact-URL evidence queries with random selection among duplicate exact pairs, and has a flat accepted output backing table/view plus common innerdict materialization.
- Current card assembly uses the common loaders and intended xlsx -> Codex -> docx -> ssn ordering. Current source connection is read-only and the detour connection is separate/read-write.
- DB audit corrections are complete: source relations use imported schema constants; persisted call and `(call_id, ref_id)` keys must be a subset of the current prefix; and temporary/real-fixture tests cover JSON/TIMESTAMPTZ round trips, idempotency, exact schemas, and source-DB immutability.
- Accepted-write ordering now performs output-row insertion and cumulative innerdict materialization before loading ground truth/rendering, while keeping the accepted transaction rollback-capable until ground truth, card ZIP, and response writes all succeed. Any failure removes response/ZIP and rolls back the authoritative row.
- Serving now enters through the API module's required `--config` argument; the Pixi feature task passes its required config path to that entry point. Startup fails for missing/invalid pipeline config while missing per-chat rollout configuration leaves only `/push` disabled.
- The real July direct-web rollout is the sole E2E fixture. Do not derive submitted excerpts/URLs or expected FC/FCO/call/ref identities from the production parser. Never mention/use the discarded August rollout and never modify sample data.

## Revised contract captured in SPEC

1. Preserve the existing fail-closed order: SCP rollout -> copy appendwatch report -> validate copied report -> index approved rollout -> Pydantic/SQL evidence validation -> accepted innerdict/card writes.
2. Support many `/pull`/`push` cycles in one cumulative rollout. The rollout filename can repeat; each archived physical line count demarcates the prefix used by one attempt.
3. Keep researcher identity in `ktp.source_key`/draw/name. Store the archive line count in `ktp.fragment` with fragment type `line_number`.
4. Derive one persistent sibling detour DuckDB from `config.db_file`; open the configured source DB read-only and serialize detour-DB writes.
5. Pre-index direct `function_call_output` -> unique `web_search_end` -> unique `function_call(name="run", namespace="web")` chains into the four human-specified normalized Codex tables.
6. Rename current labels to `DOCX_COLUMNS`, add ordered `AI_AUGMENT_COLUMNS`, and require every submitted excerpt to carry its exact result URL.
7. Validate exact excerpt presence and exact URL equality with parameterized DuckDB queries over the current approved rollout prefix, randomly selecting among multiple rows for that exact pair while the named allow-multiple switch is enabled.
8. Append one accepted flat Codex row per filename/line-count fragment, then rematerialize cumulative `codex_innerdicts` under the common two-column JSONL contract.
9. Allow repeated `ktp.source_key` values: multiple accepted attempts for one researcher become multiple Codex sections, distinguished by fragment and explicit attempt ID.
10. Reuse the existing parser/materializer/card seams: detour-local `codex_parse.py`, step-08-style output/innerdict flow, and `build_cards()`/`write_cards_zip()` with Codex sections between xlsx and docx.

## Surgical implementation boundary followed

- Edited only `api.py`, new detour-local `codex_parse.py`, focused `test_api.py`, the AI-authored SPEC/WORK sections, and minimum Pixi serving-task wiring for required `--config config.json`.
- Deployment/provisioning and appendwatch code/tests required no changes after review.
- Did not edit `README.md`, `.env.example`, `appendwatch.py`, main `vars.py`/`schema.py`, main pipeline, architecture assets, or sample/ground-truth data.
- Keep detour-owned paths, labels, table/view names, citation delimiters, bounds, context setting, and repeated numeric values as named `api.py` globals.
- Current hardcoded task remains; advancing `/pull` to a later task is explicitly out of scope.

## Verification completed

- The root Pixi task completes with 72 passed and the retained legacy
  multiple-match rejection test skipped under the active allow-multiple
  policy. Its visible argparse usage line is expected stderr from the negative
  missing-`--config` assertion under `-s`.
- A current-code preview from the production `182923` rollout's
  `turn15search2` provenance is one line, escapes source Markdown punctuation,
  retains the bold evidence text, and contains neither a ref ID nor Codex
  citation markup. The production `175705` finding supplied the concrete
  duplicate search/view case now covered by random exact-pair selection.
- The production archive from attempt
  `20260805T172641_452048Z_ed2407134c944ca08199ac5322303f69` indexes both
  title-less URL-bearing refs and skips only the cited no-URL internal-error
  ref.
- `ruff check` passes for `api.py`, `codex_parse.py`, and `test_api.py`.
- Focused API suite: 31 passed, 1 skipped. The real July E2E proves 9 FC, 9 FCO, 9 call, and 155 generic ref rows; exact fixed call/ref identities; five preserved thumbnails; output view/common innerdict/card content; two-line response; source-DB byte immutability; and exact accepted-stage order. It exercises TXT and DOCX ZIP selection/reference handling, stubbing only the external Pandoc process for DOCX bytes. Focused coverage includes active random duplicate selection, the retained/skipped strict multiple-match test, exact private failure-value logging, and copied-report missing/malformed/ambiguous rejection.
- The same July E2E proves normalized `codex.fc_arguments` remain raw while
  rendered open/click action objects preserve their turn-ref and add that
  input ref's call-scoped indexed URL. Renderer coverage also proves
  independent multi-item enrichment and unchanged pass-through for unresolved
  turn-refs and direct URL values.
- The same E2E setup proves a one-character excerpt change and exact-URL change both reject before source DB/ground truth, response, card, or authoritative innerdict writes.
- Complete non-root detour suite under the pyproject-required
  `APPENDWATCH_SCRIPT` environment: 69 passed, 4 skipped (the retained strict
  multiple-match test plus three root-only watcher cases). The root Pixi task
  runs the watcher cases and completes with 72 passed, 1 skipped. Unchanged
  appendwatch suite alone: 38 passed, 3 skipped without root.
- Independent July persistence smoke: 107 physical records; 9 FC, 9 FCO, 9 calls, 155 refs, 5 non-null thumbnails; a second persistence pass is idempotent.
- Read-only `git diff --check` reports only two trailing-space lines in the human-authored SPEC section (lines 123 and 176). They are intentionally untouched under the “AI never touches this” rule; cached diff check otherwise passes.
