# Tighten API — planning workbook

## Status

- 2026-08-07 approved specification step is complete; this step changed only
  the AI-authored SPEC and this workbook. The new Control Centre, dynamic
  sanction flow, workbook lifecycle, cohort loader, and tunnel behavior have
  not yet been implemented.
- The detour now has a dedicated `config_ai_augment.json`. Its
  `files_config["map_subset_0_to_batch"]` entry is required by the detour and
  must be loaded through `PipelineConfig.from_json()` plus the existing
  `register_resource()`/`RegisteredResource` seam with
  `ResourceGroup.KTP_PIPELINE_ARTIFACT`, `FragmentType.CSV_ROW`, and the
  configured SHA-256. Use the existing imported `DRAW_LABEL` and `BATCH_LABEL`
  for the CSV schema and reject missing columns or duplicate/conflicting draw
  rows. Keep this requirement detour-local: no edits to `PipelineConfig`, main
  required-file constants, or main resource loading.
- Cohort identity and every draw are owned only by common innerdict JSONL.
  The registered map may classify those innerdict-provided draws but may not
  supply or replace draws. `card_partitions` supplies only no-ground-truth
  eligibility flags joined by source key. Verified target invariants are 196
  ground-truth keys, 78 no-ground-truth keys, no overlap, and 274 total.
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
- Duplicate-evidence random selection uses a dedicated API RNG reseeded inside
  the serialized push from the required pipeline config's `sample_seed`.
  Combined with the explicit candidate-ID order and fixed submission
  traversal, this makes a repeated identical body over a hash-identical
  rollout select the same provenance rows regardless of prior push history,
  without mutating the process-global random generator.
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
- The earlier evidence-indexing implementation is complete in `api.py`, new
  detour-local `codex_parse.py`, Pixi serving-task wiring, and focused
  `test_api.py` coverage. The newly specified UI/control/cohort work remains
  pending implementation.
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
- Pre-revamp API serving enters through the module's required `--config`
  argument. Its old behavior leaves `/pull` available without a per-chat
  rollout; the approved control-sanction contract supersedes that behavior and
  requires both `/pull` and `/push` to fail closed when no run is sanctioned.
- The real July direct-web rollout is the sole E2E fixture. Do not derive submitted excerpts/URLs or expected FC/FCO/call/ref identities from the production parser. Never mention/use the discarded August rollout and never modify sample data.

## Revised contract captured in SPEC

1. Preserve the existing fail-closed order: SCP/publish rollout -> archive and
   publish the workbook without moving the integrity steps -> copy appendwatch
   report -> validate copied report -> index approved rollout -> Pydantic/SQL
   evidence validation -> accepted innerdict/card writes.
2. Support many `/pull`/`push` cycles in one cumulative rollout. The rollout filename can repeat; each archived physical line count demarcates the prefix used by one attempt.
3. Keep researcher identity in `ktp.source_key`/draw/name, sourced only from
   common innerdict records. Store the archive line count in `ktp.fragment`
   with fragment type `line_number`.
4. Derive one persistent sibling detour DuckDB from `config.db_file`; open the configured source DB read-only and serialize detour-DB writes.
5. Pre-index direct `function_call_output` -> unique `web_search_end` -> unique `function_call(name="run", namespace="web")` chains into the four human-specified normalized Codex tables.
6. Rename current labels to `DOCX_COLUMNS`, add ordered `AI_AUGMENT_COLUMNS`, and require every submitted excerpt to carry its exact result URL.
7. Validate exact excerpt presence and exact URL equality with parameterized DuckDB queries over the current approved rollout prefix, randomly selecting among multiple rows for that exact pair while the named allow-multiple switch is enabled.
8. Append one accepted flat Codex row per filename/line-count fragment, then rematerialize cumulative `codex_innerdicts` under the common two-column JSONL contract.
9. Allow repeated `ktp.source_key` values: multiple accepted attempts for one researcher become multiple Codex sections, distinguished by fragment and explicit attempt ID.
10. Reuse the existing parser/materializer/card seams: detour-local `codex_parse.py`, step-08-style output/innerdict flow, and `build_cards()`/`write_cards_zip()` with Codex sections between xlsx and docx.

## Approved Control Centre expansion (implementation pending)

- Implement the supplied `control_centre/ui.py` skeleton as one NiceGUI + AG
  Grid operator screen. It owns one serial Codex process, queue/cancel/rerun,
  UUID run IDs, source-key sanctions, backend lifetime, append-only UI journal,
  and idle reconciliation against accepted detour-DB rows. `api.py` remains the
  only detour-DB writer; UI detour reads stop while a sanctioned run can push.
- Derive runnable researchers from common innerdict `name_key` values. Collect
  first/last names and every distinct draw from their JSONL records. Use the
  verified map only to classify those draws into release batches 1/5/6/7 for
  the 196 ground-truth keys; explicitly exclude Mercouri G. Kanatzidis. Derive
  the 78 augmentation keys from card-partition flags joined by source key.
- The UI control service binds only `127.0.0.1:8611`. It exposes strict current
  sanction and accepted-acknowledgement routes outside OpenAPI. The API binds
  `127.0.0.1:8612`; only 8612 is reverse-forwarded to AIVM. Production uses the
  control endpoint exclusively; `.env` rollout configuration remains only an
  isolated backend-test fallback when no control URL exists.
- Each request pins one control snapshot. A missing/invalid/unavailable
  sanction gives the same generic 503 for both `/pull` and `/push`. Acceptance
  consumes the sanction; notification failure cannot roll back authoritative
  accepted output or silently re-enable the run.
- Dynamic `/pull` emits the sanctioned key's xlsx/ssn context through common
  loaders, omits docx ground truth and prior Codex attempts, and appends one
  synthetic null-AI task row. Retries are allowed until one push is accepted.
- Persist one operator-editable host workbook across runs. Copy it to AIVM at
  backend initialization and immediately before each Codex execution; use the
  same full bytes in the AIVM file and prompt. Archive/publish the guest copy
  with every rollout attempt, but never treat workbook text as evidence.
- Ground-truth runs return normalized AI values plus mapped DOCX ground truth
  as two NDJSON lines. No-ground-truth runs return only normalized AI values.
  Both materialize accepted Codex rows/cards through the existing one-sibling-
  DuckDB and common loader/materializer/card seams.
- Required implementation verification covers map registration/hash failure,
  exact cohort invariants and contracted draws, dynamic pull/no ground-truth
  leak, queue/journal/reconciliation/workbook behavior, control snapshot and
  sanction consumption, loopback/tunnel restrictions, conditional response
  shape, and preservation of the existing July evidence E2E.

## Surgical implementation boundary followed

- Earlier evidence work edited only `api.py`, new detour-local
  `codex_parse.py`, focused `test_api.py`, AI-authored SPEC/WORK sections, and
  minimum Pixi serving-task wiring. The task now passes the dedicated
  `--config config_ai_augment.json` path.
- Deployment/provisioning and appendwatch code/tests required no changes after review.
- Did not edit `README.md`, `.env.example`, `appendwatch.py`, main `vars.py`/`schema.py`, main pipeline, architecture assets, or sample/ground-truth data.
- Keep detour-owned paths, labels, table/view names, citation delimiters, bounds, context setting, and repeated numeric values as named `api.py` globals.
- Existing production code still has the hardcoded task pending the approved
  Control Centre implementation; it must be replaced by sanctioned dynamic
  `/pull`, not retained as an out-of-scope behavior.

## Verification completed

- The root Pixi task completes with 73 passed and the retained legacy
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
- Focused API suite: 32 passed, 1 skipped. The real July E2E proves 9 FC, 9 FCO, 9 call, and 155 generic ref rows; exact fixed call/ref identities; five preserved thumbnails; output view/common innerdict/card content; two-line response; source-DB byte immutability; and exact accepted-stage order. It exercises TXT and DOCX ZIP selection/reference handling, stubbing only the external Pandoc process for DOCX bytes. Focused coverage includes active random duplicate selection, a file-backed close/reopen roundtrip proving identical config-seeded provenance selection for the same body and candidate rows, the retained/skipped strict multiple-match test, exact private failure-value logging, and copied-report missing/malformed/ambiguous rejection.
- The same July E2E proves normalized `codex.fc_arguments` remain raw while
  rendered open/click action objects preserve their turn-ref and add that
  input ref's call-scoped indexed URL. Renderer coverage also proves
  independent multi-item enrichment and unchanged pass-through for unresolved
  turn-refs and direct URL values.
- The same E2E setup proves a one-character excerpt change and exact-URL change both reject before source DB/ground truth, response, card, or authoritative innerdict writes.
- Complete non-root detour suite under the pyproject-required
  `APPENDWATCH_SCRIPT` environment: 69 passed, 4 skipped (the retained strict
  multiple-match test plus three root-only watcher cases). The root Pixi task
  runs the watcher cases and completes with 73 passed, 1 skipped. Unchanged
  appendwatch suite alone: 38 passed, 3 skipped without root.
- Independent July persistence smoke: 107 physical records; 9 FC, 9 FCO, 9 calls, 155 refs, 5 non-null thumbnails; a second persistence pass is idempotent.
- Read-only `git diff --check` reports only two trailing-space lines in the human-authored SPEC section (lines 123 and 176). They are intentionally untouched under the “AI never touches this” rule; cached diff check otherwise passes.
