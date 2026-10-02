# AI augment production — current workbook (2026-10-02)

## Operator-approved table-name shape — exact chat text

### Table names

In [vars.py](/home/moshi/2026-01-02_enrich_full_df/src/detours/detour_ai_augment/protected/src/backend/helpers/vars.py:61), I propose:

```python
RUN_OUTCOME_RECORDS_TABLE: Final = "run_outcome_records"
RUN_OUTCOME_RECORD_ID_COL: Final = "run_outcome_record_id"
RUN_OUTCOME_SERIALIZED_JSON_COL: Final = "serialized_json"
POST_COMMIT_VALIDATION_RETRY_BASELINES_TABLE: Final = (
    "post_commit_validation_retry_baselines"
)
POST_COMMIT_VALIDATION_EVIDENCE_AUDITS_TABLE: Final = (
    "post_commit_validation_evidence_audits"
)
```

I would remove the old constants, rename the related `CODEX_RETRY_*_COL` and `CODEX_EVIDENCE_*_COL` **Python identifiers** to `POST_COMMIT_VALIDATION_*_COL`, and update their uses in [Store](/home/moshi/2026-01-02_enrich_full_df/src/detours/detour_ai_augment/src/backend/helpers/data_models/ai_augment_backend_store.py:2411) and the existing backend tests. Physical column names, constraints, SQL behavior, replay lines, and architecture remain unchanged. Store’s `_next_codex_row_id` also allocates evidence-audit IDs; I propose the name-only correction `_next_projected_row_id`.

There would be **no legacy-name read or migration code**. An existing detour DB contains the old tables; normal resume does not rebuild a fully anchored DB. Cutover therefore requires the existing, explicitly confirmed `--new` replay from log/CAS.

`codex_output_rows` and `codex_output` should **both remain**. [The view](/home/moshi/2026-01-02_enrich_full_df/src/detours/detour_ai_augment/src/backend/helpers/data_models/ai_augment_backend_store.py:2527) filters the table to rows whose run-outcome body is non-null, orders them, and feeds `codex_innerdicts`. An accepted validation can exist in the table before `/completed` without appearing in the view. They each have one row in this completed artifact, which makes them look identical only at this stage.

The operator approved this table-name/associated-Python-name shape exactly as shown. It is implemented in backend vars, Store, and directly affected backend tests. Ruff on those four files, detour mypy (64 source files), and focused backend tests (322 passed, 2 skipped) pass; `git diff --check` passes.

## Operator manual workflow README refresh

Operator asked for a surgical refresh of `protected/tests/operator/README.md`. Its Backend example lacked the mandatory `--new`/`--resume` flag, and its run-outcome curl supplied only `NameKey`. Updated the example to use `--resume` for a known-clean DB, identify the quoted ETag from the final `410 /pull`, and send `Session-ID` plus completed-only `ETag` to the Unix-socket outcome endpoint. Documented 400/409 responses alongside 200/500. No production code, tests, architecture, replay log, or data changed; `git diff --check` passes. The separate dashboard replay mismatch remains under read-only investigation and has no authorized fix.
Operator caught a stale import in that README's `NameKey` shell snippet: `src.detours.detour_ai_augment.src.backend.api` does not exist, and `name_key_header` has been renamed. Corrected only that snippet to import and call `src.detours.detour_ai_augment.src.shared.name_key_header_value`. The exact shell snippet under the detour Pixi environment produced the expected canonical header; `git diff --check` passed.

## Manual HTTP coverage finding (read-only)

After operator confirmed `pre-commit-operator` passes: browser navigation to `GET /push` yields FastAPI-generated 405 in Uvicorn's access log but no replay-log line. Only `@app.post(PUSH_ROUTE)` and `@app.get(PULL_ROUTE)` enter `_prepared_http_request` and their API/Store authoritative append contours (`server.py:227-249`, `api.py:515-668`). `_BackendRequestMiddleware` admits/serializes all HTTP but performs no logging (`server.py:115-132`); FastAPI rejects `GET /push` before the POST endpoint, so Store never sees it. My prior promise that all incoming HTTP was logged was false. **Operator resolved the boundary decision:** only canonical `POST /push` and `GET /pull` are within replay recording scope; other methods/endpoints are unapproved/out of scope. No source edit for the 405 is needed.

## Current manual dashboard investigation (read-only; no code changes)

Operator's macOS manual `pixi run dashboard` trace: an earlier `GET /query` borrowed an available Backend and replaced the dashboard snapshot (307 researchers, 3 completed CodexInnerDicts). Later the IPC socket disappeared; an owned `ipc_only=True` Backend child refused startup in `_verify_log_projection` at replay line 5: `missing or unordered DB record`. The verifier checks each replay line against the ordered `replayed_http_request_log_records` rows; this error proves the fifth row is absent or its ordinal is wrong, but the trace alone cannot distinguish those cases or establish why they diverged. The empty stored anchor is not itself proof of an empty table. Query-only startup intentionally verifies rather than auto-replaying missing history; it exits before IPC ready. `query_ipc` replaces the cached dashboard snapshot only after a successful query, so old researcher cards can still display afterward. Do not touch production DB/log/CAS; any recovery must be separately reviewed and explicit.

The five queue actions shown are distinct from that query failure. `_ControlCentreController.__init__` sets `_queue_processing=False`; `start()` creates the worker but never enables processing. `_worker()` waits until the operator clicks `Start queue processing`; `queue()` and `rerun()` only append a queued Run and wake the worker, and cannot override that gate. The supplied trace contains no `Queue processing started` line and no queued→running event. `cancel()` of a queued Run removes its ID from persisted queue and records cancellation; subsequent rerun creates a new queued Run (visible in the trace). Thus the log supports a paused queue plus a separate log/DB divergence, not a proved dequeue or rerun-handler failure. The exact first researcher failure, prior Backend disappearance, and DB row-5 cause are not in the supplied trace. Operator clarified **NO code changes** for this investigation.

Focused existing tests run read-only against test fixtures: `test_queue_gate_holds_next_run_without_interrupting_active_run` and `test_restored_queue_stays_stopped_and_publish_skips_remote_and_journal_mutation` passed **2/2**; `test_mismatch_fails_without_any_healing[missing_row]` passed **1/1**. These confirm the intentional paused gate and fail-closed Store behavior in test fixtures; they do not diagnose the operator's on-disk line-5 cause. No production files, tests, or data were modified.

### Root cause exposed after queue processing was enabled

Operator's next macOS trace shows the first owned full Backend starting `--new` and failing at replay validation line 20: `researcher_resolution: configured namekey was not found`, then `Recorded validation does not match its replay inputs`. Dashboard `AiAugmentControlCentreContext.begin_backend_start()` chooses `("--new", "--yes")` for the first owned full child of each dashboard context; manual `--resume` does not re-evaluate historical validation. During `_apply_validation_record()`, Store recomputes `evaluate_commit()` and requires equality to the logged `PostCommitValidation`. Store `_validated_commit_inputs().draw_number()` currently calls `context.configured_ai_augment_singular_outerdict()`, which selects only the namekey of the **current Backend invocation**, and returns no draw if it differs from the **historical commit** namekey. The dashboard invocation was for Kenneth G Cassman; historical replay line 20 evidently refers to another namekey. This is a real replay-determinism defect: a historical validation must resolve its own namekey from the frozen startup blueprint tuple, not from today's configured namekey. Preserve by-reference blueprint identity and live selected-namekey validation; do not dodge the bug by changing dashboard's `--new` policy to `--resume`. No code change authorized yet.

Failed `--new` unlinks and recreates the detour DB, then commits each replayed line separately; failure at line 20 leaves the DB with only the preceding successfully projected prefix (likely lines 1–19). Operator's subsequent manual `--resume` verifies the full log against this partial DB and fails at line 20, exactly as reported. The replay log/CAS remain authoritative; the Store correctly refuses to treat a partial DB as current. A failed owned cycle also leaves the dashboard context's `_backend_cycle_failed=True`, preventing automatic same-process retries. Do not mutate production state or suggest another `--new` before the replay bug is corrected and preservation/recovery is reviewed. Operator's standing instruction for this investigation: **NO code changes**.

Operator requested a concrete code proposal, not implementation. Pending review: in `AiAugmentBackendContext`, extract the existing tuple lookup and ineligible-cohort check into `blueprint_for_namekey(namekey)` returning the original tuple member by reference; keep `configured_ai_augment_singular_outerdict()` using that method with its existing configured-namekey and suggestions behavior. In Store's `_validated_commit_inputs().draw_number()`, resolve `namekey` from the commit through `context.blueprint_for_namekey(namekey)` instead of `context.configured_ai_augment_singular_outerdict()`; preserve the lazy `(value, error)` result. No replay-log, projection, dashboard startup-policy, architecture.py, or source-DB changes. A focused regression must replay an accepted historical validation for A while B is the current configured namekey, then verify the logged validation/projected DB match; current tests cover only same-namekey replay. Exact snippets will be supplied in chat for approval.

## Current card/JSON formatting implementation (2026-10-02)

Latest operator `pre-commit.log` showed one real browser-test failure: `tests/control_centre/test_ui_e2e.py::test_completed_grid_row_uses_real_query_ipc` reached protected `operator/test_operator_e2e.py`'s old `prepare_content`/`fromstring` expectation. That rendered raw expected JSON as unprotected Markdown and dropped underscores; the actual code-delimited browser value correctly preserved them. The operator rejected both whole-card substring and `inner_text()` line-parsing proposals, then approved a real DOM field-value check. Implemented **only in the two existing test modules**: `capture_completed_researcher_card()` returns `(card_text, browser_run_outcome_response_body)` after Playwright locates the unique `strong > code` field label, checks its exact label text, locates the sibling `<code>` value, checks unique count, and captures its `inner_text()`. Both callers destructure; `validate_workflow_artifacts()` preserves card label-order checks and asserts the captured DOM value equals the reconstructed outcome's full `response_body`. Old expected-HTML conversion and its two imports are removed. No production/card-data change, no new class/helper.

The exact failed browser node was run locally after the edit, but this Linux host denies `socket.socket(AF_INET, SOCK_STREAM)` in `running_dashboard()` before reaching Playwright (`PermissionError: Operation not permitted`); JUnit `tmp/ai-augment-card-json-20261002/browser-field-value.xml`. This is a host barrier, **not** a pass or failure of the new browser assertion. The node collects, configured Ruff passes, `git diff --check` passes, and detour mypy passes 64 source files. The human operator must rerun the node on the production macOS/browser setup to close this verification gap. No workaround or source fix for the local socket restriction was made.

The operator discarded the former SQL-view/backtick-readback proposal. `codex_output_rows` and `codex_output` remain unchanged for this edit; raw session and run-outcome JSON remain parseable by Store. Operator-finalized `codex_parse.py` supplies `render_footnoted_submission_value`, `render_standardized_submission_value`, and backticked footnote-argument JSON. Only the necessary callers in `post_commit_validation.py` and existing `test_api.py` assertions were adjusted; do not edit the finalized module without targeted approval. A fixed single-backtick span in footnote arguments remains a known embedded-backtick edge, not authorized for change.

The operator-finalized `_markdown_json_value` in shared `src/helpers/cards.py` wraps values that parse as a JSON dict/list using a delimiter absent from the value; it leaves scalars and non-JSON untouched. The `build_cards` field loop uses it for ordinary values. A separately approved filename rule applies `_markdown_literal(str(val))` when the column is exactly `KTP_FILENAME_COL` or starts `ktp.` and ends `_filename`. The operator moved the predicate to `src/helpers/vars.py` as `IS_A_KTP_FILENAME_COLUMN`; `cards.py` imports it through the existing relative `.vars` import block. Preserve the signed-off helper docstring and field-loop notice verbatim. Existing `tests/test_cards.py` TXT/DOCX round-trip assertions cover exact and suffixed filename columns; the existing JSON assertion covers the object/array delimiters. No Store, view, replay, query, or innerdict edit belongs to this card-formatting contour.

After the vars relocation, the operator added a `hcr.filename` assertion to the existing card TXT/DOCX round-trip test; it verifies that the non-`ktp.` filename keeps its raw value. The first assertion briefly expected a code-delimited label too, but the operator corrected it to match the existing label rule. Focused card/renderer/standardized checks pass **11/11**; detour mypy passes 64 source files. The operator granted blanket approval for Ruff blank-line corrections; one E303 blank line was surgically removed from `codex_parse.py`. The configured Ruff scope (`src tests`) and `git diff --check` pass. The fresh feasible main suite passed **140, 3 skipped, 4 deselected** (`tmp/ai-augment-card-json-20261002/main-final.xml`); its three explicit environment-specific deselections are the previously approved ones recorded below, and the fourth is the real-API marker. An exploratory main-source mypy run **in the detour environment** reported **20 errors in 7 unchanged files** (first: `src/helpers/docx_parse.py:195`); this is not the operator's actual default-environment mypy task. Per the operator's instruction to stop at any failure, the fresh feasible detour run was interrupted at **341 passed, 2 skipped, 4 deselected** and cannot count as final coverage. No fix was made to those unrelated files. Diagnosis: the configured operator gate runs `mypy src tests` in the **default** Pixi environment and separately runs detour mypy against detour sources in `detour-ai-augment`. Only the detour environment installs `pandas-stubs` and `types-lxml` (`pyproject.toml:48-50`); those extra stubs caused the 20 diagnostics when main files were checked from that environment (19 pandas-related, one lxml-related). All seven files are unchanged from HEAD. The prior operator log records default-environment main mypy passing 68 files and detour mypy passing 64 files. The exploratory failure does not establish an operator-gate failure; the latest full detour run remains interrupted. No production fix is justified for these diagnostics. The operator subsequently ran the configured `pre-commit-operator` flow on the production machine: configured lint and earlier tests passed; the single browser failure above is the current review point. Do not rerun main mypy in the detour environment.

## Current authorized change: explicit `result()` inputs

Operator directed immediate surgical correction of `_evaluate_submission_for_commit` in protected `post_commit_validation.py`: its nested `result()` must declare every value it currently captures from the enclosing function (`commit_request_record` for its push reference/identity assertion, `stage`, `submission_payload`, `retry_projection`, `rollout_index`, `output_row`), and every call site must pass the current values explicitly. Preserve existing validation outcomes, logging, projection, and by-reference assertion. No other source refactor. Run directly affected focused tests and detour Ruff/mypy; report any unexpected failure before fixing.

Implemented the explicit keyword-only signature and six call-site updates in that module only. Detour mypy passes 64 source files; focused Ruff passes; `git diff --check` passes. Focused backend `test_api.py` + `test_http_interceptor.py` passed **322, 2 skipped in 500.07s** after this edit. The keyword-only `*` remains intentionally to enforce named arguments at every call site.

Read-only clarification: live `_validate_commit()` computes `(PostCommitValidation, _ValidationProjection)` and only identity-checks the projection; it appends the validation record. Replay invokes `evaluate_commit()` again and passes that second projection to `_project_validation()`. This is the intended log-before-DB path. The operator asked whether the live projection is otherwise unused: yes.

## Current proposal request — review only, no new source edits

The table renames above are approved and implemented; prior read-only OpenAlex/ROR, timestamp, evidence matching, and `codex_output` findings were reported. JSON backticks are proposal-only after approval withdrawal. The two affected values are `ktp.ai_augment_run_outcome_response_body` and `ktp.ai_augment_session_metadata`. `build_cards` remains a dumb renderer. `codex_output_rows` is populated with raw session summary at validation and raw outcome body at completion; Store parses the pending summary for session matching, Store reads the completed body for outcome lookup/comparison, and `CodexInnerDict.validate_codex_innerdict` parses the completed summary. A viable proposal must cover these reads and preserve raw replay-log/outcome-record JSON while making final flat card values display-ready. No new table/column name literals; use established vars.

Read-only findings: the three tables are referenced through globals in protected backend `vars.py`, Store SQL, and existing backend tests; rename their table globals and mechanically update all imports/uses, keeping physical columns and replay format unchanged. The `codex_output` view is not duplicate storage: it filters `codex_output_rows` on non-null completed outcome body and orders filename/fragment, then feeds `codex_innerdicts`; retain it. Existing detour DBs have old table names; normal resume/query does not rebuild a fully anchored DB, so the explicit confirmed `--new` log replay is required after this schema rename (no legacy fallback/migration). In the current completed artifact both output table and view have one row, masking their pre-outcome distinction.

Filename derivation in protected `post_commit_validation.py::_session_metadata`: `session_meta.payload.timestamp` is converted to `ZoneInfo(timezone_name)` and formatted to seconds; outer `session_meta.timestamp` is validated and retained for metadata, not the basename. User example `2026-09-19T12:37:52.903Z` yields the stated `12-37-52` filename only in UTC; with current operator config `America/Toronto` it yields `08-37-52`. The retained operator artifact uses payload `2026-10-02T09:12:20.439Z` → Toronto `05-12-20`, exactly its outcome SourceKey filename. Preserve timezone behavior; no timestamp code edit proposed.

OpenAlex/ROR: all 4 replay validations have empty `openalex_ror_records_ids`; the accepted submission's four education plus two academic-position institutions all specify `openalex_id="NR", ror="NR"`. `AcademicInstitution.validate_institution()` calls providers only for non-NR/NA IDs. Author OpenAlex ID is present but its model has no provider-lookup validator. This means the *current code* did not require an external provider request; it does not establish that external verification is conceptually unnecessary.

Evidence matching: configured `codex_match=2`, `sample_seed=42`. Exact acceptance is `excerpt` found as a case-sensitive contiguous substring of rollout `cite_text` **and** exact `candidate.url == evidence.url` (not whole-text equality, not live webpage text). If multiple such exact candidates exist, seeded `EVIDENCE_RANDOM.choice` selects one; randomization chooses provenance, not correctness. V2 near candidates also require URL equality but use normalized tokens and do not count as accepted exact evidence. Final artifact audit has 17/17 `v1_exact`, seven with multiple candidate rows; no near evidence was accepted.

Historical view-only proposal to add delimiters before materialization is superseded by the operator's current request for JSON detection inside shared `build_cards`. That shared helper is used by main pipeline as well as detour; its collateral formatting effect needs explicit review, not silent rollout.

## Fresh operator run: read-only review complete (2026-10-02)

The operator supplied `logs/from_operator/pre-commit.log`, `pre-commit-extra.log`, and `tmp/test.5ab4q1qs`. Both operator stages and the browser stage exited 0. The main test selection reports 174 passed/5 skipped/6 xfailed/1 xpassed (the XPASS is the already-labelled stale manual-best review note); the detour selection 756 passed/1 skipped/3 deselected; browser 9 passed; extra real-API 3 passed/1 xfailed, sudo 3 passed, and authenticated completed-workflow operator E2E 1 passed/2 skipped. Ruff and mypy passed. Read-only artifact audit: 20 replay lines match 20 projected HTTP rows by ordinal, ID, JSON envelope, and SHA-256; four validations (three rejected, one accepted), one completed outcome, one flat CodexInnerDict; five CAS blobs hash-match; the final outcome links the accepted 200 pull, push, commit, and validation, not the intervening BUSY 503 pull. The dashboard's one completed Run has the final validation/attempt UUID. The main DB symlink in the artifact was not opened.

`openalex_ror_records_ids` is `[]` on all four validation replay bodies: no provider HTTP exchange occurred in this run. Store constructs this list from `ModelHttpInterceptor.record_ids`; the 20 replay lines contain none. In the accepted `StandardizedSubmission`, every education and academic-position institution has `openalex_id: "NR"` and `ror: "NR"`, so `AcademicInstitution.validate_institution()` takes neither provider-request branch. The researcher-author OpenAlex ID is real but its model has no provider-lookup validator.

**Presentation discrepancy requiring review, no code edit made:** The stored completed-outcome `response_body`/flat `ktp.ai_augment_run_outcome_response_body` contains JSON keys `pull_record_id`, `push_record_id`, etc. The operator's Playwright `card.inner_text()` instead shows `pullrecordid`, `pushrecordid`, etc. The exact visible value equals `lxml.html.fromstring(nicegui.elements.markdown.prepare_content(raw_body, extras="fenced-code-blocks tables")).text_content().strip()`, not the stored raw value: 21 underscores become one. `src/helpers/cards.py::build_cards` inserts `str(val)` unescaped into Markdown and `ui.py` passes it to NiceGUI Markdown. The operator E2E test compares against the same Markdown-transformed value, so passes despite this; the browser underscore test covers labels, not JSON values. TXT bytes preserve Markdown source; DOCX visual impact was not verified here. No source code changed during this review. Report this separately from the passing production/replay gates; a targeted rendering correction needs an approved shape.

## Approved follow-up, implemented and locally verified (2026-10-02)

1. **Integration-test docstring.** The test arose from the stale fixture that fabricated two accepted commits for one session. It now proves a real rejected→accepted retry can have two validation-request IDs and one queryable outcome. Its final assertion is narrower than its name suggests: it rejects **two dashboard Runs claiming the same session** after a second, 409 run-outcome record is logged; that second record is not in the query snapshot. I propose:

   ```python
   """Cover the same-session case lost with the stale two-accepted-commits fixture.

   A real Store retry creates two validation requests but one queryable
   completed outcome, linked to its Run by the final attempt ID. A second
   Run claiming that session, after a rejected outcome is logged, must
   fail the dashboard's duplicate-session check.
   """
   ```

2. **Retry-pull literals.** In [test_http_interceptor.py](/home/moshi/2026-01-02_enrich_full_df/src/detours/detour_ai_augment/tests/backend/test_http_interceptor.py:965), `HTTP_GET_METHOD`, `PULL_PATH`, and `HTTP_CONTENT_TYPE_HEADER` already exist in backend vars. The focused edit would be:

   ```python
   method=HTTP_GET_METHOD,
   path=PULL_PATH,
   response_code=HTTPStatus.OK,
   response_headers={HTTP_CONTENT_TYPE_HEADER: ContentType.MARKDOWN_UTF8},
   ```

   The protected integration test already uses the first two globals but still has a literal header key. `HTTP_CONTENT_TYPE_HEADER` is title-cased; Store’s content-type check is case-insensitive. I found no established newline global, so I would leave `"\n"` alone.

6. **Test names.** I agree both are misleading. For [test_ui.py](/home/moshi/2026-01-02_enrich_full_df/src/detours/detour_ai_augment/tests/control_centre/test_ui.py:2705), I propose `test_control_centre_run_history_keeps_failed_cancelled_and_completed_runs_distinct`. For the test at [line 2799](/home/moshi/2026-01-02_enrich_full_df/src/detours/detour_ai_augment/tests/control_centre/test_ui.py:2799), I propose `test_researcher_card_uses_linked_run_outcome_response_bodies_for_distinct_sessions`.

For **5**, keep `row_id=None` and `completed_attempt_id=None` on the no-history placeholder. Fix only the fake’s actual completed history row by giving it a stable, distinct synthetic attempt ID:

```python
# BrowserController.__init__
self._completed_attempt_id_by_run_id: dict[UUID, UUID] = {}

# Beside the pre-seeded completed Run setup
self._completed_attempt_id_by_run_id[completed_run_id] = uuid7()

# BrowserController._researcher_var_row_view
completed_attempt_id=self._completed_attempt_id_by_run_id.get(run_id),
```

Queued and cancelled fake Runs still show no completed attempt. The pre-seeded completed Run shows the same UUID across snapshots. This also addresses an existing browser assertion that currently expects a UUID in that history cell while the fake supplies `None` ([test_ui_e2e.py](/home/moshi/2026-01-02_enrich_full_df/src/detours/detour_ai_augment/tests/control_centre/test_ui_e2e.py:962)). The synthetic ID is only for this browser-layout fake; it does not claim to test the real ETag handoff.

Items 1, 2, 5, and 6 are operator-approved exactly as written and now applied to test source. The operator accepted explanations 3 and 4; no code change was requested for them. Focused affected selection passed **7/7** (`tmp/ai-augment-completed-attempt-20261002/approved-followup-focused.xml`); Ruff on the four affected test files, detour mypy (64 source files), and unstaged `git diff --check` passed. An in-process check of `BrowserController` confirmed the pre-seeded completed history row has the same UUIDv7 across snapshots and the no-history placeholder retains both `None` fields. The browser/Playwright case itself was not run on this Linux host; the completed-attempt-ID cell that was blank in the fake now receives the approved synthetic ID. The earlier 935-node whole-suite totals below predate these test-only edits and are not claimed as a post-edit full rerun.

## Approved replacement for stale dashboard history test — implemented and verified

Replace `tests/control_centre/test_ui.py::test_multiple_commits_for_same_session_remain_distinct_display_rows` surgically with one test of **three terminal dashboard Runs for the same NameKey, with three distinct session IDs**: one failed, one cancelled, one completed. Only the completed Run has one valid CodexInnerDict and one linked completed RunOutcomeResponseRecord from the query snapshot; its card `ktp.filename` and `ktp.fragment` come from that outcome's SourceKey, and its session metadata matches its session ID. Construct Runs through existing `queued_run`/`apply_run_event` and existing typed models, without a new helper or fabricated second completed output. Assert exactly one upper-grid row for this researcher/variable, selecting the latest completed Run; assert exactly three lower-history rows with distinct Run IDs and their respective failed/cancelled/completed statuses, with no duplicate row IDs. Preserve the test's frozen-view assertion if still applicable. The operator accepted this replacement shape.

**Approved operator correction:** The earlier proposal also said to assert/display a completed commit-request ID. That aspect is **withdrawn**: dashboard identity and linkage must use the validation-request UUID (`AgentRuntimeAttempt.record_id`) carried by the final `/pull` ETag and `/completed` request/response, not any commit ID. The exact ETag-to-Run/query contour below is approved for implementation. Do not implement this test replacement using the superseded commit-ID assertion.

### Separate protected dashboard integration test — implemented; focused test passed

The new `src/detours/detour_ai_augment/protected/tests/control_centre/test_ui_integration.py` test establishes both sides of the session cardinality rule using a real Store/replay/query contour and typed Run/attempt/outcome/query objects: **multiple RunOutcomeResponseRecords for the same session ID fail**, while **multiple distinct validation-request-record IDs (`AgentRuntimeAttempt.record_id`) within that same session do not themselves cause failure**. The allowed case has a rejected retry attempt and one final accepted attempt for one Run and one completed RunOutcomeResponseRecord; the view accepts it and matches by final validation UUID. A second rejected run-outcome response for the same session, attached to a second Run, triggers the explicit cardinality failure. No second accepted CodexInnerDict with duplicate session metadata, commit-ID substitution, or retry history row was fabricated. This test is distinct from the approved three-Run replacement above. Both focused tests passed on 2026-10-02.

**ETag-link audit:** Dashboard `_finalize_run` takes the 410 `/pull` ETag UUID, `RunOutcomeRequestRecord.outbound_http` sends it on `/completed`, and Store `_run_outcome_identity_error` requires it match the current validation UUID. Store's outcome body and typed `attempt` are checked against that UUID during replay/readback. But `_BackendDatabaseClient.record_run_outcome` returns only HTTP status after parsing the body; `_record_run_outcome` does not retain/verify its linked UUID and treats 400/409 as recorded before the Run terminal event. Later `_ResearcherView.from_snapshot` associates the query-derived outcome/final attempt to a Run by session ID, not by the sent ETag UUID. `Run.run_outcome_response_record` is never populated by dashboard source. The operator approved the surgical link below, not a broader failure-policy rewrite.

**Approved hard-grep correction:** `dashboard_query_snapshot.py` keys completed query objects by commit ID; `ui.py` uses that key and the commit-derived session to join Runs, sets row IDs/timestamps from commits, and displays commit IDs in both tables. Replace those dashboard uses with a persisted per-Run final attempt UUID from the 410 ETag, query outcome's typed `attempt.record_id`, and Run/outcome row identity. `run_outcome_event.py` also mentions commit IDs because its response body is the backend's shared authoritative codec; those provenance checks are not dashboard selection/display logic and must not be silently deleted. The unused `JOURNAL_COMMIT_REQUEST_RECORD_ID_MISSING` locale and dashboard-only commit column global can go after UI references are removed. Preserve the existing 400/409/500 outcome-status policy; verify a successful response's validation UUID against the Run's saved attempt ID.

### Exact approved production contour — implemented and verified locally

The operator approves the targeted architecture edit, naming the Run property **`completed_attempt_id`** with corresponding `UUID | None` type (superseding `attempt_id` and the earlier `validation_request_record_id`). This property is filled only for a completed Run from its final `/pull` ETag; add that short docstring in `RunProperty`. In `protected/src/architecture.py::ControlCentreComponent.RunProperty` and concrete `src/control_centre/dashboard/helpers/data_models/run_event.py::Run`:

```python
# RunProperty
@property
def completed_attempt_id(self) -> UUID | None:
    """Final /pull ETag, present only for a completed Run."""
    ...

# Run
completed_attempt_id: UUID | None = None
```

Persist the 410 ETag on the same Run before `/completed`; do not use `RunEvent.detail`, fabricate a RunOutcomeResponseRecord from a partial HTTP response, or add a fallback. The previously shown code shape, with the approved name, is:

```python
run.completed_attempt_id = validation_record_id
self._storage.save_runs(tuple(self._runs.values()))

# Query reconciliation
matched_run = runs_by_completed_attempt_id.get(outcome.attempt.record_id)
```

In `dashboard_query_snapshot.py`, remove commit-keyed `committed_by_id` and commit-derived query joins/checks. Validate/index only the final outcome-linked `attempt.record_id`; allow multiple retry-attempt IDs inside one outcome's typed graph, but reject multiple run outcomes for one session. In `ui.py`, replace the commit-keyed lookup and session-based Run join with `Run.completed_attempt_id == outcome.attempt.record_id`; session/namekey remain cross-checks. The lower table stays one row per Run or query-only outcome, not per retry attempt. Use `run.run_id` for matched Run row identity, `outcome.record_id` for query-only outcome identity, Run event/outcome time instead of commit UUID time, and a completed-attempt-ID column in place of the commit-ID column in both tables. Do not add/change card data for display. Keep shared backend response-codec commit provenance fields/checks unchanged. `_BackendDatabaseClient.record_run_outcome` must retain the parsed response validation UUID; on successful `/completed`, verify it equals the Run's saved `completed_attempt_id`. Do not silently alter current 400/409/500 handling.

Surgically adapted affected UI/operator assertions and implemented the approved three-Run replacement and separate protected integration test above; backend replay/commit provenance tests are preserved. The new integration and replacement tests passed **2/2**; the related outcome-client, lifecycle, card, and completed-query fixture selection passed **10/10**. Fresh full local verification completed on 2026-10-02: feasible detour **752 passed, 5 runtime-skipped, 4 deselected** (`tmp/ai-augment-completed-attempt-20261002/full-detour.xml`); repository-main **140 passed, 3 runtime-skipped, 4 deselected** (`full-main.xml`); optional other detours **12 passed, 3 deselected** (`full-optional.xml`); separately feasible browser-module subprocess fixture **1 passed** (`full-browser-fixture.xml`). Thus **935 collected**, **913 executed = 905 passed + 8 runtime-skipped**, and **22 not run** for the already-approved platform, data, sudo, real-API, operator, browser, and TASK exclusions. Per-test collection and JUnit evidence are in that same tmp directory; `not-run-nodes.txt` names all 22, with individual reasons in the final table below. Whole-source Ruff, detour mypy (**64 source files**), and unstaged `git diff --check` pass. No unexpected test failed. The Darwin/Lima/Chrome `pre-commit-operator` task remains for the human operator; do not claim it passed here.

**Current dashboard contract:** The lower table has one view per dashboard Run or query-only completed outcome, not one per validation attempt. `_ResearcherView.from_snapshot` matches a query-derived final attempt to a Run by `completed_attempt_id` and adds unmatched Runs (including failed/cancelled). The upper grid selects the latest view per researcher/variable. The query payload transports every linked validation inside a completed `CodexInnerDict`, but exposing retries as separate history rows is **not** in the approved scope. The stale same-session test has been replaced as approved above.

## Historical reference — earlier investigation and completed contours

Material below preserves prior approved code shapes and failure analyses. Its dated test counts and any old “pending” or “current” status refer to earlier checkpoints; **the 2026-10-02 status above is authoritative for this implementation**. Do not treat an older proposal-only paragraph as active authorization or an earlier exclusion/failure as a current test result.

### Earlier approved test correction and continuation
Operator-approved three **test-only** edits are applied: a new Store-invariant test in `src/detours/detour_ai_augment/protected/tests/backend/test_backend_store_integration.py`; removed xfail and repaired `test_outcome_finalizes_only_linked_commit_once`; repaired `test_initial_validation_is_lifecycle_scoped_and_replays_explicit_links` in `src/detours/detour_ai_augment/tests/backend/test_http_interceptor.py`. The new test's docstring contains the former xfail reason verbatim. All three focused tests passed; the subsequent approved narrow correction for `test_failed_validation_projection_does_not_advance_store_validation_state[True]` also passed focused `[False]`/`[True]`. The approved dashboard fixture correction below is applied; focused `[410-completed]` and `[503-failed]` cases both passed. Affected-file Ruff and `git diff --check` pass. The subsequent continuation stopped at **another dashboard test failure**: `test_multiple_commits_for_same_session_remain_distinct_display_rows`, after **24 passed, 1 failed** in 7.44s (`tmp/ai-augment-card-verification-20261001/detour-after-ui-fixture-repair.xml/log`). Its two completed innerdicts for the same namekey/session use fabricated `commit-{index}.docx` filenames and omit `ktp.fragment`, while both outcome SourceKeys derive from the same session ID. `CodexInnerDict.validate_codex_innerdict()` rejects the first. More importantly, Store's unique `(namekey, session_metadata)` accepted-output constraint prohibits two completed innerdicts for that same namekey/session in real production. Dashboard `_ResearcherView.from_snapshot` builds rows from `snapshot.attempts_by_namekey`, but that property currently lists only the final `outcome.attempt` from each completed CodexInnerDict, not preceding retry validations. Thus the same-session two-row expectation is not merely a stale fixture field: it is not currently realizable from a production query snapshot without changing dashboard derivation or the intended display contract. No such production change is authorized here. The nearby `test_card_record_ids_match_each_commit_and_researcher_session` also constructs two same-session completed innerdicts and may share the stale premise; not run yet. **No code change after this new failure.** Exact JUnit node ID matching confirms **283 remaining feasible nodes** at `tmp/ai-augment-card-verification-20261001/remaining-after-same-session-stop.txt`; 22 operator-approved exclusions remain uninvoked. Current distinct tally: **934 collected; 629 invoked = 622 passed, 6 skipped, 1 failed; 305 not invoked**. Stop for operator review of intended dashboard coverage before modifying or rerunning this test. No production, architecture, legacy, restart, or unrelated test changes. The new protected test reuses existing test fixtures/helper by import; no fixture behavior was modified.

### Approved dashboard fixture correction

In `src/detours/detour_ai_augment/tests/control_centre/test_ui.py::test_backend_acceptance_remains_running_until_codex_exits[410-completed]`, derive the card SourceKey fields from the already-created outcome's `SOURCE_KEY_HEADER`, using the existing `source_key_from_header_value` from `src.detours.detour_ai_augment.src.shared`. Add only that and `KTP_FRAGMENT_COL` to the existing imports; place the following after `outcome = run_outcome_response_record(...)`, then add only the two shown fields to its `InnerDict.from_mapping` literal. Leave the other branch, controller assertions, production code, and all other tests unchanged.

```python
assert outcome.response_headers is not None
filename, fragment = source_key_from_header_value(
    outcome.response_headers[SOURCE_KEY_HEADER]
)
# Existing session_metadata construction remains here.
innerdict=InnerDict.from_mapping(
    {
        KTP_NAMEKEY_COL: NAMEKEY.to_json_key(),
        KTP_FILENAME_COL: filename,
        KTP_FRAGMENT_COL: fragment,
        # Existing remaining mapping entries unchanged.
    },
    _CodexInnerDictProcedure(),
)
```

### Approved correction for the continuation failure

In `src/detours/detour_ai_augment/tests/backend/test_http_interceptor.py::test_failed_validation_projection_does_not_advance_store_validation_state`, change only the `has_initial` setup. This is the operator-approved code shape, with `retry_pull = ...` denoting **existing code unchanged**:

```python
if has_initial:
    store._validate_commit(commit(store, {}, payload))
    initial = store.current_replayed_record
    assert isinstance(initial, BackendValidationRequestRecord)
    assert (
        initial.validation_request_body.post_commit_validation.result
        is BackendLifecycle.REJECTED
    )
    assert (
        initial.validation_request_body.post_commit_validation.stage
        is BackendLifecycle.PYDANTIC_VALIDATION
    )
    retry_pull = store._append_authoritative_record(...)  # existing code unchanged
```

The `[False]` branch, injection, cursor/DB assertions, and other tests remain unchanged. **Applied exactly**; focused `[False]` and `[True]` cases both passed in 11.35s. Historical continuation checkpoint: 386 previously unreached feasible nodes stopped after 76 passed, 1 skipped, 1 failed in 23.73s (`tmp/ai-augment-card-verification-20261001/detour-after-projection-test-repair.xml/log`). The failed `test_backend_acceptance_remains_running_until_codex_exits[410-completed]` fixture omitted the two outcome SourceKey columns; the operator approved and agent applied only the targeted fixture correction above. The two parameter cases passed focused verification before the next continuation.

### Exact approved code contour

1. New test in the protected backend Store integration module. Deliberately bypass API admission and assert the second accepted validation for the same session fails loudly; retain the preexisting extra rollout line so the commits have distinct fragments. Preserve this function body, adding only module-local imports/fixture exposure required by its new location and the verbatim docstring.

```python
def test_second_same_session_acceptance_fails_loudly(
    backend_store: AiAugmentBackendStore,
    runtime: AiAugmentBackendContext,
) -> None:
    """Synthetic second same-session acceptance bypasses the API lifecycle and collides with unique session metadata before outcome-link assertions"""  # noqa: E501
    payload = valid_submission_body()
    with pytest.raises(RuntimeError, match="Backend Store failed"), (
        backend_store._writable(runtime)
    ):
        first = backend_store._validate_commit(
            commit(backend_store, payload, payload)
        )
        assert (
            first.validation_request_body.post_commit_validation.result
            is BackendLifecycle.ACCEPTED
        )
        second_commit_id = commit(
            backend_store, payload, payload,
            rollout_suffix=(
                b'{"type":"event_msg","timestamp":"2026-09-03T15:17:00Z",'
                b'"payload":{"type":"task_complete"}}\n'
            ),
        )
        with pytest.raises(
            ReplayInputMissing, match=Locale.ACCEPTED_IDENTITY_DUPLICATE
        ):
            backend_store._validate_commit(second_commit_id)
```

2. Remove the xfail. In `test_outcome_finalizes_only_linked_commit_once`, replace only the two-accepted loop with a Pydantic-rejected first commit, a linked 200 retry pull, and one accepted second commit. Preserve the completed outcome, later failed outcome, query round-trip, and unchanged-card assertions; add explicit completion link/200 and failed-outcome/409 assertions. No new helper.

```python
first = store._validate_commit(commit(store, {}, payload))
assert first.validation_request_body.post_commit_validation.result is BackendLifecycle.REJECTED
assert first.validation_request_body.post_commit_validation.stage is BackendLifecycle.PYDANTIC_VALIDATION

retry_pull = store._append_authoritative_record(persisted_http_record(
    record_id=uuid7(), method="GET", path="/pull", response_code=HTTPStatus.OK,
    response_headers={"content-type": ContentType.MARKDOWN_UTF8},
    response_body=(
        first.validation_request_body.post_commit_validation.detail
        or Locale.VALIDATION_ERROR_DETAIL
    ).rstrip() + "\n",
))
assert isinstance(retry_pull, PullResponseRecord)
assert retry_pull.validation_request_record is first

result = store._validate_commit(commit(store, payload, payload, retry_pull))
assert result.validation_request_body.post_commit_validation.result is BackendLifecycle.ACCEPTED
```

3. In `test_initial_validation_is_lifecycle_scoped_and_replays_explicit_links`, change only the first commit to invalid input and assert retryable Pydantic rejection; keep its existing retry-pull, byref, distinct-root, snapshot, outcome, and rebuild assertions; assert second validation is accepted.

```python
first = store._validate_commit(
    commit(store, {}, payload, session_id=session_id)
)
assert first.validation_request_body.post_commit_validation.result is BackendLifecycle.REJECTED
assert first.validation_request_body.post_commit_validation.stage is BackendLifecycle.PYDANTIC_VALIDATION
# Existing initial-reference assertions and 200 retry pull remain.
second = store._validate_commit(commit(
    store, payload, payload, retry_pull, session_id=session_id,
))
assert second.validation_request_body.post_commit_validation.result is BackendLifecycle.ACCEPTED
```

Previous checkpoint before this approval: 933 collected; 523 invoked = 516 passed, 5 skipped, 1 strict xfailed, 1 failed; 410 not invoked (388 not reached, 22 approved exclusions). The former strict xfail and second test failure are superseded by the 3/3 focused pass. Prior evidence: `tmp/ai-augment-card-verification-20261001/detour-continuation.log/xml`; individual not-run inventory: `tmp/ai-augment-card-verification-20261001/not-run-after-continuation.md`. Read-only `--resume` finding: API lifespan resets READY, ordinary Store opening verifies projected log/DB without restoring cursor; same-session restart behavior remains unreviewed and out of this test correction.

The four approved test/fixture edits are applied; no production edit was made in that step. Focused backend/card/live-replay tests passed **10/10 in 64.97s**; the subprocess-only completed-query fixture passed **1/1 in 20.49s**. Ruff on the configured `src tests` scope and detour mypy (63 source files) passed. The operator requested a fresh repetition of HEAD's approximately 934-node test inventory with a per-node accounting. The new run stopped at the first unexpected detour failure, as the operator instructed; no fix, test skip, or source change was made after that failure. Earlier 904/8/22 figures below are historical, not a current-tree result.

Fresh collection: **918** configured main/detour nodes plus **15** optional-other-detour nodes = **933** total. HEAD's 934 fell by one because three old placeholder-selector parameter cases became two explicit NR/NA card cases (plus name-only test renames). Main: **140 passed, 3 skipped, 4 deselected** (`tmp/ai-augment-card-verification-20261001/main.xml/log`). Optional other detours: **12 passed, 3 deselected** (`optional.xml/log`). The detour run (`detour.xml/log`) stopped at `tests/backend/test_http_interceptor.py::test_outcome_finalizes_only_linked_commit_once` after **361 passed, 2 skipped, 4 deselected, 1 failed** (511.29s). The separate completed-query fixture passed and counts as one more distinct passed node. Therefore across 933 collected nodes: **514 passed, 5 runtime-skipped, 1 failed, 413 not invoked**. `tmp/ai-augment-card-verification-20261001/not-run.md` lists every one of the 413 with an individual reason; 391 were not reached because of the stop, while 22 had the prior approved environment/operator/TASK exclusions. These are partial results, **not** whole-suite readiness.

Historical failure boundary, now covered by the new protected integration test: the old outcome test made two accepted commits for the same namekey and Codex session before either outcome, by calling `commit(..., rollout_suffix=...)` twice with the helper's default `session_id=UUID(OPERATOR_CAPTURED_SESSION_ID)`. The appended suffix changes rollout bytes but not `CodexRolloutRecord.session.summary_json`. The approved `codex_output_rows` `UNIQUE (ktp.namekey, ktp.ai_augment_session_metadata)` constraint rejects the second accepted validation at Store `_append_codex_output` (`ai_augment_backend_store.py:2498`); `ReplayInputMissing(Locale.ACCEPTED_IDENTITY_DUPLICATE)` occurs before outcome-link assertions. The new test asserts that Store invariant directly; the repaired outcome test uses a live-reachable rejected-then-accepted retry.

Read-only follow-up on whether the test's two acceptances are live-reachable: within one running backend, public `authoritative_push` sets `BACKEND_LIFECYCLE=BUSY` before accepted push processing; a second push gets 503 while BUSY. After Store persists/projects the accepted validation, `finish_push` calls `update_pull_state`, setting COMPLETED; subsequent `/pull` returns and durably logs 410, while `/push` is outside READY/RETRY and returns 500. The 410 is produced on a **later GET**, not inside the validation DB transaction. The failing test bypasses API admission and calls Store's private `_append_authoritative_record` to synthesize a fresh 200 pull, 202 push, and commit twice, then `_validate_commit` twice; it keeps the same helper-default session ID. Store's low-level append path does not enforce API lifecycle. Across a new `--resume` backend process, API lifespan resets lifecycle to READY and ordinary Store `_opened` verifies DB/log but does not reconstruct the cursor; a same-session new pull/push could therefore be attempted again. Whether that restart behavior is intended remains unreviewed; do not infer a proven public HTTP reproduction or change it within the current narrow scope.

## Governing boundaries
Read tasks/tasks-20260911-ai-augment-prod/src/TASK.md and this entire file after compaction. Do not consult former WORK or HUMANS. Use pixi run -e detour-ai-augment for Python/checks; never run src.repl or modify the main DB. Git is read-only for this agent: do not stage/unstage. Do not edit architecture.py without targeted approval, excluded BDD, or human-signed-off comments. Source and existing-test edits must be surgical; no old-record fallbacks, unauthorized wrappers, wholesale replacements, or unrelated cleanup. The one new Store-invariant test is specifically authorized in this turn. Earlier settled WORK contours were authorized and applied; the **current SourceKey/card-table/prefix contour is approved and under resumed verification after the 3/3 focused pass**. Preserve exact model shapes and docstrings, particularly CASCodexRolloutRecord. Stop and ask if a deviation from a reviewed boundary is needed.

Architecture.py governs models; README lifecycle is somewhat stale. Replay log is principal and detour DB is fully reconstructible from log/CAS; DOCX renders DB innerdicts. Store alone owns detour SQL and authoritative lifecycle records. Current replay contour: append/fsync, log readback, project in one DB transaction, reconstruct typed object from DB, compare value and byref links, then advance the one current_replayed_record cursor if applicable. BUSY 503 exchanges are logged but do not advance that cursor. On validation replay the cursor must be a BackendCommitRequestRecord; intervening provider HTTP or BUSY 503 log lines are permitted. Assert identity with is only for the same byref object, not across a fresh reconstruction. Post-commit validation gets a byref commit and Store-supplied inputs/reads; it does no SQL. Existing LazyResultFactory callbacks for validation are truly deferred and use (value, error) results; immediate HTTP-record lookup is instead Callable[[UUID], HttpRequestLogRecord].

## Current source and verification status
**Current SourceKey/card state; earlier internal-column shape superseded.** The retained artifact's accepted commit SourceKey ends at line 220 while `/completed` reports line 230; the old card displays 220. The operator approved the integrated contour below, including removing the earlier partial internal-column implementation. Source edits now implement the flat `codex_output_rows` schema, outcome-only card SourceKey, and storage-side standardized prefix; the focused tests passed after the approved fixture correction, but the full suite stopped at the new accepted-validation conflict above. The operator's rule is that `codex_output_rows` has **no internal-only columns**: its columns correspond to `codex_innerdicts` card data, with `ktp.namekey` as the outer grouping key. Card-facing `ktp.filename`, `ktp.fragment`, and `ktp.fragment_type` start NULL in the accepted-validation row and are filled **only** from the completed run-outcome response SourceKey. Commit SourceKey remains for appendwatch/rollout binding. No COALESCE, fallback, legacy schema path, architecture.py edit, or dashboard/DOCX card-value rewrite. README lifecycle wording is known-stale.

### Integrated SourceKey / flat output / prefix contour — approved; verification pending

Operator approved this exact contour for surgical implementation on 2026-10-01. Source and affected-test edits are partially implemented; verification stopped at the full-suite accepted-validation failure described above, pending operator review. No new table, class, public model, fallback, record format, or `architecture.py` change. Live projection and full replay use the same existing Store transaction; an existing secondary DB needs an explicit log/CAS rebuild. `codex_output_rows` retains **only** card columns plus `ktp.namekey` (outer grouping key). It may hold accepted-but-not-completed rows with NULL final SourceKey/body fields; only completed rows are materialized into `codex_innerdicts`. Do not confuse equal columns with equal row sets.

**Resolved historical focused-test stop, 2026-10-01:** The first node, `tests/backend/test_api.py::test_card_labels_stored_standardized_fields_without_mutating_source`, failed before reaching the prefix assertions. Its new test setup calls `StandardizedSubmission.model_validate(L_FEI_FEI_RETRY_FIXTURE.submission.model_dump(...))`; the pre-existing retry fixture is deliberately assembled with `model_construct`, and JSON revalidation hits strict enum inputs plus `OPENALEX_API_KEY`-dependent institution validation (62 errors). No test/source edit was made after observing the failure. The subsequently approved correction was: use the already typed fixture's `submission.model_copy(deep=True)` in the two adapted card tests, changing only the gender standardized value on that copy for the `NR`/`NA` cases, then resume the focused tests. This does not change production validation or mock it. Ruff on the six edited production/test files passes. Detour mypy initially had one unrelated error in previously approved `protected/tests/pytest_plugin.py:897`: `commit` was annotated as a base `HttpRequestLogRecord` and thus had no typed `commit_request_body`; the operator later approved and the agent applied the narrow fixture type assertion. Full tests/operator readiness are not claimed.

**Revised exact correction, approved and applied; focused verification passed:** In `tests/backend/test_api.py::test_card_labels_stored_standardized_fields_without_mutating_source`, replace only the two-line `StandardizedSubmission.model_validate(...model_dump(...))` setup with `submission = L_FEI_FEI_RETRY_FIXTURE.submission.model_copy(deep=True)`. The original passing test never revalidated a full submission; the new attempted revalidation failed before assertions, so this does not remove pre-existing input-validation coverage. In `test_card_preserves_standardized_placeholders`, copy the fixture likewise, but construct `GenderSubmission(value=submission.gender.value, web_search_excerpts=submission.gender.web_search_excerpts, standardized_value=placeholder)` and assign it to `submission.gender`. That **does** runtime-validate the newly supplied NR/NA value without validating unrelated fixture institutions or calling OpenAlex. Annotate `placeholder: NotReported | NotAvailableOrApplicable` using established aliases. Also adapt the **existing** `test_outcome_materializes_persisted_ids_identically_live_and_replay` to assert every standardized field in the completed query innerdict starts with `codex_parse.AI_GENERATED_TEXT_PREFIX` plus a space, and that `api.selected_card_outer_dict(singular_outerdict).get_inner_by_key(...)[...] is innerdict.innerdict`; its already present live/rebuild equality then covers the real Store→DB→query path and Codex byref selection. No new test, mock, or production change. Separately, for the pre-existing out-of-contour mypy/Ruff gate in `protected/tests/pytest_plugin.py`, add `BackendCommitRequestRecord` to the function-local commit_request import, add `assert isinstance(commit, BackendCommitRequestRecord)` immediately after Store's commit append/readback, and remove only `gone_pull = ` from the 410 append. Store's annotated append return type is generic `HttpRequestLogRecord`; its actual reconstructed commit should be the concrete class, as already asserted for pull and push in that same fixture. The operator authorized all these exact test/fixture edits in the current turn. Stop and report any new unexpected failure rather than silently fixing it.

1. In `protected/src/backend/helpers/vars.py`, remove the two `CODEX_OUTPUT_RUN_OUTCOME_*` constants and their physical columns, and remove the three lifecycle-ID columns from `CODEX_OUTPUT_SCHEMA`. Keep the `KTP_AI_AUGMENT_COMMIT_REQUEST_RECORD_ID_COL` *constant* only where dashboard's independent grid label still uses it; remove validation/outcome-ID constants if no consumer remains after test adaptation. Keep the final response-body and session-metadata card fields. Change only final SourceKey column nullability:

   ~~~python
   (KTP_NAMEKEY_COL, "VARCHAR NOT NULL"),
   (KTP_FILENAME_COL, "VARCHAR"),
   (KTP_FRAGMENT_COL, "BIGINT"),
   (KTP_FRAGMENT_TYPE_COL, "VARCHAR"),
   # Existing ordinary card fields, response body, session metadata,
   # nine narrative/standardized pairs, comments, footnotes: unchanged.
   ~~~

   Store `_create_codex_output_schema` uses those definitions with `UNIQUE (ktp.filename, ktp.fragment)` for the **final** SourceKey and `UNIQUE (ktp.namekey, ktp.ai_augment_session_metadata)` for one accepted row per exact session summary; both constraints use card columns, no hidden key. `CODEX_OUTPUT_VIEW` remains only a completed-row filter, **SELECT * with no column aliases/exclusions**:

   ~~~sql
   CREATE OR REPLACE VIEW codex_output AS
   SELECT * FROM codex_output_rows
   WHERE "ktp.ai_augment_run_outcome_response_body" IS NOT NULL
   ORDER BY "ktp.filename", "ktp.fragment";
   ~~~

   Production SQL interpolates established table/column constants via `duckdb_quote_identifier`, not these illustrative literal identifiers. `_materialize_innerdicts(source_relation=CODEX_OUTPUT_VIEW, table_name=CODEX_INNERDICT_TABLE)` remains. Each completed output-row column except `ktp.namekey` becomes exactly one flat innerdict key; the common materializer puts `ktp.namekey` in the outer table column. Do not create an extra projection with hidden fields.

2. In `post_commit_validation.py`, `_accepted_output_row` sets `KTP_FILENAME_COL`, `KTP_FRAGMENT_COL`, `KTP_FRAGMENT_TYPE_COL`, and `KTP_AI_AUGMENT_RUN_OUTCOME_RESPONSE_BODY_COL` to `None`; it does not use commit SourceKey for card identity and no longer accepts `commit_request_record`/`cas_codex_rollout_record` arguments used only to populate now-removed ID/SourceKey fields. Remove the three lifecycle-ID entries, the stale output-identity assertions, and `_DetourDbValidationReads.output_identity_exists` plus its invocation. In Store remove the corresponding lazy closure and `_codex_output_identity_exists`; keep Store's commit SourceKey **line-count check against the durable rollout** in `_validated_commit_inputs` and post-commit validation's commit SourceKey **basename binding** for appendwatch and rollout index. The premature accepted-commit filename/fragment duplicate check goes; the final completed SourceKey constraint now catches duplicates.

3. In the existing `render_codex_values`, the nine narrative fields already use `render_ai_value` and present comments already use `render_comment`; do not double-prefix them. Wrap only the nine standardized canonical JSON strings with existing `codex_parse.render_ai_standardized_value`, as in the exact snippet immediately below. Top-level `NR` and `NA` stay literal JSON string tokens inside `**AI-generated text**: "NR"` / `**AI-generated text**: "NA"`, never `None`, never hidden. Structured `NR`/`NA` members remain unchanged. Metadata, response-body JSON, footnotes and footnote arguments are not submitted AI prose and receive no prefix. `CODEX_OUTPUT_SCHEMA` standardized columns stay `VARCHAR NOT NULL`. Replace `selected_card_outer_dict`'s deep-copy/JSON-parse/mutation loop with the pure by-reference selector in the exact snippet below; delete the now-unused selector imports and `AI_AUGMENT_CARD_EMPTY_VALUE_PLACEHOLDERS` constant/import. Browser card, TXT, DOCX, and publish continue through the same `build_cards` path, without additional value rewrite. Do not change the shared formatter without separate review of its generic headings/null omission/newline formatting.

4. In Store `_apply_run_outcome_record`, after the existing record/reference checks, parse the **completed outcome response** SourceKey once for final filename and fragment; take fragment type from the parser-enforced `ROLLOUT_LINE_FRAGMENT_TYPE`. Remove its commit-vs-outcome filename comparison: the accepted commit basename remains an appendwatch/rollout binding, not a card identity rule. The already-reconstructed `outcome.attempt` is the accepted validation by reference; its commit ID and the existing `commit_validation_request_record_index` remain available for linkage verification. Locate the pending flat row using only *existing card columns*: fetch `ktp.ai_augment_session_metadata` for this namekey where response body is NULL, parse each with `CodexRolloutRecord.parse_summary_json`, and retain those whose `session_id` equals `outcome._codex_session_record().session_id`. Require **exactly one** match (zero or multiple is a loud `Locale.RUN_OUTCOME_PROJECTION_INCONSISTENT` error); the `(namekey, session_metadata)` uniqueness constraint makes the subsequent update singular. The concrete read/update contour is:

   ~~~python
   pending = self._execute(
       f"SELECT {duckdb_quote_identifier(KTP_AI_AUGMENT_SESSION_METADATA_COL)} "
       f"FROM {CODEX_OUTPUT_ROWS_TABLE} "
       f"WHERE {duckdb_quote_identifier(KTP_NAMEKEY_COL)} = ? "
       f"AND {duckdb_quote_identifier(KTP_AI_AUGMENT_RUN_OUTCOME_RESPONSE_BODY_COL)} IS NULL",
       [namekey.to_json_key()],
   ).fetchall()
   matches = tuple(
       metadata_json for (metadata_json,) in pending
       if UUID(CodexRolloutRecord.parse_summary_json(metadata_json)[CODEX_SESSION_ID_JSON_KEY])
       == session_id
   )
   if len(matches) != 1:
       raise ReplayInputMissing(Locale.RUN_OUTCOME_PROJECTION_INCONSISTENT)
   metadata_json = matches[0]
   updated_rows = self._execute(
       f"UPDATE {CODEX_OUTPUT_ROWS_TABLE} SET "
       f"{duckdb_quote_identifier(KTP_FILENAME_COL)} = ?, "
       f"{duckdb_quote_identifier(KTP_FRAGMENT_COL)} = ?, "
       f"{duckdb_quote_identifier(KTP_FRAGMENT_TYPE_COL)} = ?, "
       f"{duckdb_quote_identifier(KTP_AI_AUGMENT_RUN_OUTCOME_RESPONSE_BODY_COL)} = ? "
       f"WHERE {duckdb_quote_identifier(KTP_NAMEKEY_COL)} = ? "
       f"AND {duckdb_quote_identifier(KTP_AI_AUGMENT_SESSION_METADATA_COL)} = ? "
       f"AND {duckdb_quote_identifier(KTP_AI_AUGMENT_RUN_OUTCOME_RESPONSE_BODY_COL)} IS NULL "
       f"RETURNING {duckdb_quote_identifier(KTP_NAMEKEY_COL)}",
       [outcome_filename, outcome_fragment, ROLLOUT_LINE_FRAGMENT_TYPE,
        outcome.response_body, namekey.to_json_key(), metadata_json],
   ).fetchall()
   if len(updated_rows) != 1:
       raise ReplayInputMissing(Locale.RUN_OUTCOME_PROJECTION_INCONSISTENT)
   ~~~

   Continue inserting the **one** full `_RunOutcomeResponseRecordJson` snapshot into the unchanged two-column `codex_run_outcome_records(run_outcome_record_id PRIMARY KEY, serialized_json)` table, then refresh the completed-row view/materialized `codex_innerdicts`, all in the same replay projection transaction. An absent accepted-output table/row on a successful completed outcome and a duplicate final SourceKey are fatal, not ignored or repaired. Remove the old multi-row loop/ID updates and unprefixed internal-column writes. There is no commit-derived card SourceKey field to read or fall back to.

5. In Store `_codex_innerdicts`, stop joining the flat card back to `codex_output_rows` for an outcome ID or session metadata. The **existing** card field `ktp.ai_augment_run_outcome_response_body` is the exact serialized HTTP response body and already contains `run_outcome_record_id`; obtain it using `RunOutcomeResponseRecord._parse_response_body` and fetch the full snapshot by that ID from `codex_run_outcome_records`. Check the reconstructed outcome's `response_body` equals the card field, then construct the same `CodexInnerDict(InnerDict.from_mapping(...), outcome)` as today. Its **existing** validator checks the card's `ktp.ai_augment_session_metadata` session ID against the outcome and compares card filename/fragment to the outcome response SourceKey; do not duplicate those checks in Store. The replacement of the existing staging-row lookup is:

   ~~~python
   response_body = values[KTP_AI_AUGMENT_RUN_OUTCOME_RESPONSE_BODY_COL]
   if not isinstance(response_body, str):
       raise ReplayInputMissing(Locale.RUN_OUTCOME_PROJECTION_INCONSISTENT)
   outcome_record_id = RunOutcomeResponseRecord._parse_response_body(
       response_body
   ).run_outcome_record_id
   outcome_row = self._execute(
       f"SELECT {duckdb_quote_identifier(CODEX_RUN_OUTCOME_SERIALIZED_JSON_COL)} "
       f"FROM {CODEX_RUN_OUTCOME_RECORDS_TABLE} "
       f"WHERE {duckdb_quote_identifier(CODEX_RUN_OUTCOME_RECORD_ID_COL)} = ?",
       [str(outcome_record_id)],
   ).fetchone()
   if outcome_row is None:
       raise ReplayInputMissing(Locale.RUN_OUTCOME_PROJECTION_INCONSISTENT)
   outcome = _RunOutcomeResponseRecordJson.model_validate_json(
       outcome_row[0]
   ).to_run_outcome_response_record()
   if outcome.response_body != response_body:
       raise ReplayInputMissing(Locale.RUN_OUTCOME_PROJECTION_INCONSISTENT)
   codex_innerdicts.append(CodexInnerDict(
       innerdict=InnerDict.from_mapping(
           {KTP_NAMEKEY_COL: namekey_json, **values},
           _CodexInnerDictProcedure(),
       ),
       run_outcome_response_record=outcome,
   ))
   ~~~

   Keep the existing containing `try`/`except` handling and `CodexInnerDict` model validation. No DB read outside Store, dashboard reconstruction from replay fragments, new table, or new wire field.

6. **SourceKey checks retained vs removed:** The two authorities are commit request SourceKey for appendwatch/rollout binding and completed outcome response SourceKey for final card identity. Remove Store's early accepted-output duplicate lookup, post-validation card-identity assertions, and Store's commit-vs-outcome filename equality check. Preserve `RunOutcomeResponseRecord.validate_record`'s canonical outcome-header/rollout-line-count check, `CodexInnerDict.validate_codex_innerdict`'s DB-card-vs-outcome integrity check, and dashboard `_RunAttemptView.run_outcome_session_status`'s later appendwatch status check; these validate the two authorities and do **not** provide alternate card-field values. Validation request still copies/checks the commit headers. This explicit retention list is part of the proposal for operator approval; literal removal of every parser call would weaken these checks and is **not** silently assumed.

7. Surgically adapt only impacted existing tests: `tests/backend/test_api.py`'s direct output-row/materialization and standardized-card tests, `tests/backend/test_http_interceptor.py`'s live/replay outcome materialization assertions, affected `tests/control_centre/test_ui.py` card assertions, and the operator rendered-card SourceKey/prefix assertion if its expected content changes. Preserve test coverage and test bodies outside changed expectations; no new tests or wholesale replacement. Verify same logical flat columns in completed `codex_output_rows` and `codex_innerdicts`, literal `NR`/`NA` preservation, exact prefix once, outcome (not commit) line count, live/rebuild equivalence, and query/DOCX consumption from DB. Run focused affected tests, all feasible detour tests, Ruff/mypy, and ask operator to rerun `pixi run pre-commit-operator` on the production machine. No claim of operator readiness before those checks.

**Read-only standardized-card prefix finding, 2026-10-01:** The retained artifact's `codex_output_rows`, `codex_innerdicts`, and NiceGUI query snapshot hold nine standardized values as canonical JSON, without the Markdown label. This is the existing storage contract: `post_commit_validation.render_codex_values` writes `json.dumps(standardized_value)`. `selected_card_outer_dict` copies each innerdict and adds `codex_parse.render_ai_standardized_value(value)` to nonempty standardized strings only for display; dashboard `_BackendDatabaseClient.card` calls that function before `build_cards`, and DOCX uses the resulting Markdown. The retained query payload reproduced a generated Markdown card with all nine standardized fields prefixed and 19 total AI-generated markers, using `model_construct` solely to bypass the *new, untested SourceKey equality check* against this old artifact. Existing focused standardized-card unit test passed 1/1. The prefix was introduced 2026-09-13 by 3734a7f and moved intact with card-selection logic in 2026-09-28 dea2bf1; no evidence of its subsequent removal from the rendering path. The artifact contains no rendered-card screenshot/text, so actual browser display cannot be independently confirmed from these files. No code change for this investigation.

**Operator correction; proposal only, no code edit approved:** The display-time rewrite just described is unacceptable even if it generates the expected visible text. At Codex innerdict materialization, standardized values must acquire the same `**AI-generated text**:` prefix already applied to narrative values, so the accepted output row and `codex_innerdicts` contain final researcher-card text. No card/Markdown/browser/TXT/DOCX/publish layer may add, remove, substitute, or otherwise alter *Codex innerdict values* for display. Purge the display-only standardized-field JSON decoding, placeholder suppression, and prefix injection in `selected_card_outer_dict`; propose a pure selection of the existing innerdict references instead. Do not introduce a display-specific projection or fallback. The main DB's XLSX (2018), DOCX (317), and SSN (2044) innerdicts contain no `_standardized` fields, so the affected real fields are Codex's. **Operator decision:** `NR` and `NA` must always be preserved as values, never substituted with null/None or suppressed. The preceding agent proposal to store null for top-level `NR`/`NA` is rejected and superseded below. Existing tests would be adapted surgically only after the complete contour is approved. The broader grep/audit below is a required part of this edit, not optional follow-up. This proposal is **not approved or implemented**; SourceKey implementation remains paused.

**Concrete prefix proposal for operator review (not approved, no code edit):** In `post_commit_validation.render_codex_values`, replace only the standardized assignment; keep narrative rendering and canonical JSON spelling. The accepted `StandardizedValue` permits top-level `NR`/`NA` but not top-level JSON null. Serialize and prefix **every** accepted standardized value, including top-level `NR` and `NA`: their literal tokens remain intact as `"NR"`/`"NA"` inside canonical JSON, and the complete stored/card values become `**AI-generated text**: "NR"`/`**AI-generated text**: "NA"`. Nested `NR`/`NA` tokens likewise remain unchanged inside prefixed structured JSON. Do not make the standardized DB columns nullable or introduce a special missing-value path. Unlike today's display-only suppression, the card will visibly contain these two top-level values, as required by the operator's preservation rule.

**Exact AI-content scope for this proposal:** `AI_AUGMENT_COLUMNS` names nine narrative evidence fields plus optional comments. `render_codex_values` already applies `codex_parse.render_ai_value` to each narrative field and `codex_parse.render_comment` (which includes the prefix after its list marker) to a present comment. The nine `AI_AUGMENT_STANDARDIZED_COLUMNS` are the only submitted AI-content fields currently stored without the prefix; change their existing assignment below, without prefixing any already-prefixed field a second time. Do **not** indiscriminately prefix every `ktp.ai_augment_*`-named field: run-outcome response body and session metadata are structured JSON, while footnotes/footnote arguments are evidence/citation apparatus, not submitted AI prose. The operator's "all AI columns" instruction is thus interpreted as all AI-authored narrative/comment/standardized content, not machine-readable metadata or provenance fields; this exact boundary is for operator review before any source edit. A production-source `rg` for `NOT_REPORTED_VALUE|NOT_AVAILABLE_OR_APPLICABLE_VALUE|AI_AUGMENT_CARD_EMPTY_VALUE_PLACEHOLDERS|KTP_TABLE_1_EMPTY_VALUE_PLACEHOLDERS` and placeholder-to-`None` assignments found **one** explicit `NR`/`NA` suppression path: `selected_card_outer_dict` at `ai_augment_singular_outer_dict.py:219-232`. The other `None` cases found in these files represent absent optional data (e.g. comments), not an `NR`/`NA` conversion. Remove that loop/constant rather than replacing it with another suppression point. Shared `build_cards`' `pd.isna` omits actual nulls but does not omit the literal strings `NR` or `NA`.

~~~python
standardized_value = field_submission.model_dump(mode="json")[STANDARDIZED_VALUE_FIELD]
rendered[standardized_columns[column]] = codex_parse.render_ai_standardized_value(
    json.dumps(
        standardized_value,
        ensure_ascii=False,
        separators=COMPACT_JSON_SEPARATORS,
    )
)
~~~

`_accepted_output_row` already takes `render_codex_values`; `codex_output_rows` → `codex_output` → `codex_innerdicts` then carries these exact values. Do not add Store/query/dashboard/DOCX transformations. Replace `selected_card_outer_dict` with a selection that keeps the existing source order and each existing `InnerDict` instance by reference:

~~~python
def selected_card_outer_dict(
    singular_outerdict: AiAugmentSingularOuterDict,
) -> OuterDict:
    return OuterDict(data={
        singular_outerdict.namekey.to_json_key(): [
            *singular_outerdict.xlsx_innerdicts,
            *(item.innerdict for item in singular_outerdict.codex_innerdicts),
            *singular_outerdict.docx_innerdicts,
            *singular_outerdict.ssn_innerdicts,
        ],
    })
~~~

Remove only selector imports that become unused and the `AI_AUGMENT_CARD_EMPTY_VALUE_PLACEHOLDERS` constant (and its now-unused `KTP_TABLE_1_EMPTY_VALUE_PLACEHOLDERS` import), retaining the globally used standardized-column constants. Surgically adapt the existing standardized card tests: assert the selected `InnerDict` is the same instance, all standardized strings—including top-level `NR`/`NA`—are already prefixed in Codex innerdicts before selection and appear in the card, and no source data is changed while rendering. The existing synthetic tests inject raw standardized JSON (including an artificial top-level null) into XLSX; that test setup should instead exercise Codex's validated storage-side output, since XLSX has no such fields in real source data and the accepted standardized model does not admit top-level null. Shared `build_cards` still adds headings/introduction and omits genuinely null fields; that generic formatting was identified in the audit below and is **not** being silently characterized as zero display processing. No old-record fallback or architecture.py edit.

**Required comprehensive presentation audit, 2026-10-01 (read-only grep completed; no source edits):** Search the entire detour production source and the shared card formatter for all codex-innerdict/card presentation paths, including Markdown, browser, TXT, DOCX download, and `publish completed`. For every value-changing or display-only operation, report whether it changes a stored field, filters it, adds content, or merely supplies formatting; do not silently preserve any display-time *value* addition/removal. The searches used `rg` over detour `{src,protected/src}` for `selected_card_outer_dict|build_cards|render_docx_bytes|card_markdown|render_codex_values|render_ai_standardized_value|download_displayed_card|prepare_content|fromstring`, all `innerdict`/`card`/`markdown`/`docx`/`txt` references in dashboard modules, and `model_copy|deepcopy|json.loads|replace|strip|isna|excluded_cols` in the relevant source and shared `src/helpers/cards.py`. Findings:

- `protected/src/backend/helpers/data_models/post_commit_validation.py:1530-1553`: `render_codex_values` prefixes narrative text via `codex_parse.render_ai_value` but stores standardized values as raw canonical JSON. This is the proposed storage-side correction point; the operator has now rejected null substitution/suppression of `NR`/`NA`.
- `src/backend/helpers/data_models/ai_augment_singular_outer_dict.py:201-233`: `selected_card_outer_dict` deep-copies innerdicts, parses standardized JSON, turns JSON null/recognized placeholders into `None`, and prefixes other standardized values. This is the definite display-time value rewrite to remove within the proposed change.
- `src/control_centre/dashboard/ui.py:1059-1074` calls that selector then shared `build_cards`. `src/helpers/cards.py:51-122` adds card introduction/date, researcher/draw header, optional fun fact, filename heading, field labels, and Markdown spacing; it omits `excluded_cols` and `pd.isna` values, turns values into `str`, and doubles embedded newlines. Detour's `CARD_EXCLUDED_COLUMNS` (`protected/src/backend/helpers/vars.py:375`) suppresses filename/namekey/source-position fields as ordinary value lines (filename is separately a heading). Those are existing Markdown layout/structural-selection operations, **not changes to `InnerDict.data`**, but they affect visible layout and which structural fields appear as ordinary lines. The integrated proposal explicitly **retains** these existing generic formatting rules and changes only the Codex standardized-value rewrite; approval of the proposal includes this precise boundary. Do not edit shared `cards.py` or `CARD_EXCLUDED_COLUMNS` in this change.
- Browser card display at `ui.py:3244-3245` passes the generated Markdown directly to NiceGUI. TXT download at `ui.py:3305` encodes the same Markdown; DOCX download at `ui.py:890-891,3301-3302` and publish at `ui.py:3660-3665` pass it to `src/helpers/cards.py:143-148`, which writes the Markdown and invokes Pandoc with the reference DOCX. No additional field-value rewrite was found in these branches. No independent `prepare_content`/`lxml.fromstring` card path remains.
- The separate dashboard variable grid reads `CodexInnerDict.text` directly (`ui.py:580-583`) but `footnotes_for_researcher_var` and `footnote_arguments_for_researcher_var` (`ui.py:629-674`) select only matching numbered lines for a variable. This is a derived grid view, not the researcher card or its TXT/DOCX; keep it visible in the comprehensive audit rather than conflating it with card-value mutation.

**SourceKey revision requested, proposal only:** The operator requires card-facing `ktp.filename`/`ktp.fragment`/`ktp.fragment_type` to be NULL in the accepted validation-stage row and populated only from the completed run-outcome response SourceKey, alongside the already-NULL `ktp.ai_augment_run_outcome_response_body`. The in-progress separate internal outcome columns must be removed, not completed; **no staging-only columns may remain in `codex_output_rows`**. A prior suggestion to scan accepted commit headers to preserve `_codex_output_identity_exists` is withdrawn. That check currently compares accepted *commit* filename/line count and rejects a second accepted validation before run outcome, backed by an early UNIQUE constraint; it is not required for final card identity. The proposed final-card duplicate guard is the existing unique filename/fragment pair at completed-outcome update plus `AiAugmentSingularOuterDict` section validation. The existing three lifecycle-ID-only columns in `CODEX_OUTPUT_SCHEMA` are also nonconforming and need a separate, specific index/readback contour; their removal must not break completed-outcome linkage or query. This changes a duplicate-commit scenario from validation rejection to possible outcome-time conflict, so the complete surgical SQL/readback contour needs operator review before code edits. No code changes in response to this proposal request.

**Read-only SourceKey parsing audit:** Validation request headers are copied from the commit and checked for exact equality; no independent validation-header value parse exists. The commit header is parsed (1) by Store `_validated_commit_inputs` to compare line count with its durable `CodexRolloutRecord` and, currently, supply the premature accepted-output duplicate check; (2) by `post_commit_validation._evaluate_submission_for_commit` to obtain the expected rollout basename for appendwatch report validation and CAS rollout session metadata comparison, plus stale output-row assertions; (3) by Store `_apply_run_outcome_record` to compare commit filename with completed-outcome filename. The completed run-outcome response header is parsed (4) by `RunOutcomeResponseRecord.validate_record` to check canonical header and rollout line count; (5) by Store `_apply_run_outcome_record` to project final SourceKey; (6) by `CodexInnerDict.validate_codex_innerdict` to compare flat card fields with outcome; (7) by dashboard `_RunAttemptView.run_outcome_session_status` for line count and appendwatch path validation. Constructors/forwarders are separate: synthetic commit puts configured rollout basename and line count into SourceKey; validation copies commit request headers; Store constructs the outcome response SourceKey; outcome request rejects a client SourceKey. Thus the operator's thesis aligns with validation-header handling and intended card provenance but not with current commit-header validation: `CodexRolloutRecord` has hash/size/line_count only, not a filename, and post-commit validation presently obtains its expected basename from the commit header. No code changes; any move away from that use needs a concrete alternative durable filename source and replay/failure-order review.

**Operator SourceKey purpose refinement; review only, no source edit:** The operator agrees that commit-request SourceKey is needed for appendwatch/rollout binding and completed run-outcome response SourceKey is the sole source of final card `ktp.filename`/`ktp.fragment`/`ktp.fragment_type`; commit/validation headers must not populate card identity. The operator proposes purging every other SourceKey use surgically, without fallback/legacy support. The two *provenance purposes* are clear, but a literal two-parse-only rule is not yet safe: Store `_validated_commit_inputs` checks commit header line count against the durable rollout; `RunOutcomeResponseRecord.validate_record` checks outcome header canonicality/rollout line count even without card projection; Store `_apply_run_outcome_record` compares outcome and commit basenames; `CodexInnerDict.validate_codex_innerdict` checks DB card identity against the linked outcome; and dashboard `_RunAttemptView.run_outcome_session_status` checks the later appendwatch report against the outcome basename. These are integrity/status checks, not alternate card-data sources. The current accepted-output duplicate check and `_accepted_output_row`/post-validation card-identity assertions are the stale commit-derived uses to remove in the proposed card correction. Before editing other parse sites, resolve whether these independent checks are deliberately dropped or retained as checks without being alternate data sources. No source change was authorized by this clarification.

**Binding Codex output/innerdict schema rule and read-only audit:** Every `codex_output_rows` column must correspond to a final card field in `codex_innerdicts`, except `ktp.namekey`, which corresponds to the outer grouping key. No internal-only lifecycle IDs, intermediate SourceKey columns, or other staging columns in that table; it should be the direct flat source of Codex innerdict values, not a card-data relation with hidden columns filtered out by `codex_output`. Current code does **not** satisfy this: `CODEX_OUTPUT_SCHEMA` contains commit, validation, and outcome record-ID columns excluded by `_replace_codex_output_view`; the partially applied SourceKey edit adds two more internal columns and aliases them into the view. The common `materialize_innerdicts_from_rows_table` drops only `ktp.namekey` into the outer table key. Retained pre-edit artifact verifies 33 staging columns, 30 view columns, and 29 flat JSON keys; the three staging-only columns were those lifecycle IDs. XLSX/DOCX use their match views directly; SSN uses its legacy rows relation directly. In main DB, SSN's 50 source columns become 49 JSON keys plus namekey; XLSX/DOCX match views could not be `DESCRIBE`d here because the configured `unaccent` extension was not loaded, but their code calls the same materializer directly on those views. The exact relocation/removal of existing ID links and resulting direct materialization/readback is pending a surgical proposal; **do not implement by keeping a hidden view, adding a new internal column, or dropping a needed link without replacement**. No source change for this review.

**Read-only replay-link audit, 2026-10-01:** The operator asks whether absent pull `validation_request_record_id` and push `pull_response_record_id` are available when logging. They are: Store `_response_record_for_http` constructs the typed links from `_current_replayed_record` immediately before `_append_request`. However both model fields have `Field(exclude=True)`, and `_append_request` converts to the plain HTTP envelope via `HttpRequestLogRecord.model_validate_json(record.model_dump_json())`; the replay line omits these IDs. On replay, `_apply_durable_record` projects/reads the HTTP record from DB and calls the same `_response_record_for_http` against the sequential cursor, then `_remember_reconstructed_record` advances it. Live append compares the original and reconstructed typed objects and uses identity checks against the predecessor. Retry 200 pulls link to the preceding validation; initial 200 pulls link to None. 410 pulls do not attach a validation object (although their ETag carries validation UUID) or advance the cursor. Accepted pushes require the current 200 pull by model validation; rejected/BUSY pushes may have None and do not advance. The artifact's retry 200 pulls and 202 pushes have no explicit link IDs in their own log lines; the later commit request body carries pull/push IDs. No source change requested or made for this audit.

**Post-fixture Ruff follow-up needs authorization:** After the exact one-line approved fixture change, all 72 operator preflight tests pass, but Ruff now reports F841 at `protected/tests/pytest_plugin.py:869`: `gone_pull` is assigned and no longer read. The minimal mechanical correction is to remove only `gone_pull = `, leaving the Store append call and its effects unchanged. Do not apply this second edit without operator approval because the approval specified exactly one line. Both staged and unstaged `git diff --check` pass.

**Focused verification after targeted fixture approval:** The operator approved replacing only `pull_record_id=gone_pull.record_id` with `pull_record_id=commit.commit_request_body.pull_response_record.record_id` in `protected/tests/pytest_plugin.py:897`. The single line was changed and all **72/72** operator preflight tests now pass (74.42s). Whole-source Ruff, detour mypy (63 source files), TOML parsing, operator E2E collection (3 nodes), and unstaged `git diff --check` passed before that one-line fixture edit; the production operator E2E has not yet been rerun after the assertion edit.

**Current authorized follow-up (2026-10-01):** The operator authorized the exact surgical changes identified in the operator-log/stale-wording review. The operator E2E now compares outcome pull/push IDs to the accepted `commit_request_body` links, not the latest chronological 410 `/pull` and `/push`; only that obsolete search and two test messages changed. Two Locale strings now say `commit request record ID`. Two targeted architecture.py comment/docstring names now match the implemented classes/cursor; no protocol code changed. The operator separately directed the extra Pixi task's existing `grep -q "FAILED"` to search `logs/pre-commit-extra.log` instead of `logs/pre-commit.log`; only that filename changed. The grep's `-q`, `&&`, and echo semantics remain as authored. README lifecycle remains known-stale and unedited; no exact replacement prose was approved. The broader Pixi status-propagation concern remains diagnosed but unedited; the operator expressly asked only for the grep filename correction. Current verification and the focused preflight failure are recorded immediately above; the production operator E2E must be rerun before claiming it passes.

**Production-machine temp-space incident resolved by operator:** the initial `pre-commit` detour pytest invocation reported 475 passed, 1 skipped, 3 deselected, then 281 setup errors from pytest failing to create directories under `/tmp/pytest-of-anonymous/pytest-5`. The operator confirmed insufficient device space, freed space, and reports those tests then passed. No code or test-task change was made for this incident; no concern remains. Pytest's `_pytest.pathlib.make_numbered_dir` had masked the underlying `mkdir` errno in the initial traceback. A completed local feasible run retained ~918 MB in one pytest temp session, consistent with this diagnosis. This report does not independently establish that the full `pre-commit-operator` task passed; do not claim that without its final result.

**Operator log/artifact audit before approved corrections:** copied full `pixi run pre-commit-operator` logs are `logs/from_operator/pre-commit.log` and `pre-commit-extra.log`; retained E2E artifact is `tmp/test.h_zcehhk/`. The primary pre-commit child exited 0: default tests 174 passed/5 skipped/6 xfailed/1 xpassed, other detours passed, detour suite 756 passed/1 skipped/3 deselected, real-API smoke 1 passed, and all nine macOS-browser tests passed. Extra stage: 3 real-API passed/1 xfailed, 3 sudo passed; the authenticated operator test `test_completed_dashboard_backend_codex_workflow_renders_researcher_card` alone failed (two excluded operator cases skipped); its child log ends `Command exit status: 1`. The overall Pixi wrapper exit status cannot be inferred from these child logs; `pyproject.toml:318-378` has a separate status-propagation defect noted below. The E2E failure is `protected/tests/operator/test_operator_e2e.py:1241`: `run_outcome_snapshot.pull_record_id` is compared to the latest chronological `/pull` before `/completed`, which was a **410 probe**, not the accepted initiating **200 pull**. Retained replay log has 23 records, including five validation requests (four rejected, then one accepted); #17 `/pull` 200 → #18 `/push` 202 → #19 `/commit` → #20 `/validate` accepted → #21 and #22 `/pull` 410 → #23 `/completed` 200. Commit body and outcome response both link to #17/#18; #21/#22 share validation #20's ETag. Thus the observed ID mismatch is an E2E assertion error, not evidence of a bad outcome link. Surgical proposed correction for operator review: assert the outcome's pull/push IDs against `commit_request_body.pull_response_record.record_id` and `.push_response_record.record_id`, removing the latest-by-time `/pull`/`/push` search. The operator subsequently approved and the narrow assertion correction is applied. Assertions later in that function (CAS/report/card-text) were not executed by the failed run; Playwright did capture/display the card and enabled DOCX beforehand. Independent read-only artifact checks: all 23 replay IDs match 23 projected HTTP rows; all six CAS blobs hash to their names and all six commit/outcome rollout refs resolve with correct size; `codex_innerdicts` has one flat 29-field card whose outcome-body field exactly equals `/completed` response body and follows `ktp.last_name` before session metadata; `codex_run_outcome_records` has one full snapshot with five validations; NiceGUI storage has 307 query researchers, one Run, seven RunEvents ending `completed`, no queued Runs. This does not claim that the whole E2E will pass after the assertion is corrected.

**Independent operator-gate status-propagation concern, read-only:** `pyproject.toml:337,369` uses `grep -q "FAILED" ... && echo "grep: no FAILED"`, which is logically reversed: the success-looking message is reached only if a literal `FAILED` *is present*. The copied passing `pre-commit.log` has zero literal `FAILED`, so that grep would return 1. Both outer `bash -c` task bodies lack `set -e`/explicit status accumulation and run later commands after guest-stage failure; the final macOS `script -a` child status propagation is not established by these logs. Therefore the child logs are the evidence of success/failure, not a trustworthy implied overall Pixi status. Only the wrong grep file in the extra task was corrected on operator direction; other shell behavior is unchanged.

**Detour-wide stale-term grep audit (read-only):** definite live wording drift at `protected/tests/operator/test_operator_e2e.py:830` (`run/commit history`, while UI title is `Runs and outcomes`) and :860 (`commit record ID`, should name `commit request record ID` and preferably the specific history row); `protected/src/control_centre/dashboard/helpers/locale.py:86` and `protected/src/backend/helpers/locale.py:681` also abbreviate that architectural name to `commit record ID`. Authoritative-but-stale docstring at `protected/src/architecture.py:147` says `current_response_record` instead of the implemented `current_replayed_record`; its deliberately commented-out unused protocol at :534 says old `BackendValidationRecord`. The two exact wording corrections were subsequently approved and applied. `README.md:217,222` still describes a “current pull” and run-outcome projection as raw-HTTP-only, contrary to commit-bound pull provenance and current secondary outcome/card projections; README was already acknowledged as stale. `src/control_centre/dashboard/ui.py:1840` queue/run history and the browser fake's `_run_history_ids_by_namekey` are valid because they refer to actual dashboard Runs, not the “Runs and outcomes” panel. DB `commit_record_id` columns/globals are approved schema names, not stray model classes; paused BDD still contains an obsolete current-pull fixture reference but remains explicitly excluded. This original audit was read-only; the authorized follow-up edits are recorded above.

The working tree contains the approved push-admission implementation (exclusive HTTP gate, inlined API push decision, immediately reconstructed PushResponseRecord plus eventual promise, BUSY 503, narrow cursor invariant), the ID-based run-outcome response-body cleanup, and the secondary run-outcome/query readback codec. Preserve the operator's names current_replayed_record, session_id, captured_push_request_http_record, the_coroutine, stores_push_promise, and PUSH_PROCESSING_DESCRIPTION. The card's exact response-body JSON follows `ktp.last_name`; the unused commit-body staging field is removed. Serialization changes and surgical updates to existing tests are verified by the checks below.

The **final full Linux-feasible detour run after all approved rename/import edits** passed **751 tests, 5 skipped, 4 deselected in 1278.50s** (`tmp/ai-augment-rename-verification-20261001/final-feasible-detour.log/xml`). Full dashboard `test_ui.py` passed **206/206**, operator preflight **72/72**, and the separately feasible subprocess-only query fixture plus Store recovery integration passed **2/2** after the exact name/import edits; these are overlapping focused checks, not additional distinct detour tests except the subprocess-only fixture. After the operator's targeted direction, the two unused `StandardizedSubmission` and `Submission` imports in `protected/src/architecture.py` were moved verbatim into comments inside the unused `AttemptRecordProperty` block; no protocol code or existing comment was changed. Whole-source Ruff, detour mypy (**63 source files**), and unstaged `git diff --check` now pass. **Staged** `git diff --cached --check` separately reports two trailing-space lines in the human-staged detour README (lines 102, 125); this agent did not alter that unrelated file. The Pixi `pre-commit-operator` task does not itself call `git diff --check`, but the staged diff is not whitespace-clean. An additional repository-wide `mypy src tests` run in the detour environment reports 20 errors in seven unchanged main-pipeline files; this is not the operator task's default-environment mypy invocation and is outside the approved edit contour. The operator explicitly approved the targeted one-blank-line Ruff E305 fix in `src/helpers/architecture.py:108`; that exact formatting edit is applied. The corrected operator E2E assertion requires surname → exact run-outcome response body → session metadata and restores a rendered-body content check. Full pre-commit-operator requires Darwin/Lima/Chrome and cannot run here; do not call it passed.

Unrun here: one real-API and three authenticated/operator E2E tests; eight `test_ui_e2e.py` cases after the subprocess-only fixture case passed separately (one of the eight was attempted and failed at denied local socket creation); three sudo-marked appendwatch tests; and the deliberately excluded BDD module. The full operator test of completed-card rendering remains unexecuted. Current per-test evidence and the separately encountered optional-other-detour dependency failure are recorded below. Source files and WORK have preexisting staged edits; some existing tests and current WORK updates are unstaged. This agent did not stage or unstage anything, as TASK forbids that.

## Operator decisions on the three review points
1. `codex_innerdicts` contains only flat card innerdict JSONL, including the existing session metadata/rollout summary **and the run-outcome HTTP response body** as a JSON string. The response-body card field must immediately follow `ktp.last_name`. The obsolete commit-request-body staging/card field is removed: no remaining consumer needs it. Store the distinct full query-ready outcome snapshot once in `codex_run_outcome_records(run_outcome_record_id PRIMARY KEY, serialized_json)`; duplicate keys fail loudly, with no upsert or fallback. `codex_output_rows` remains the accepted-card staging table and links its one card row to the outcome ID.
2. Pull/push response JSON decoders accept optional predecessor references. Omitted and explicit `None` mean `None`; a supplied record is used by reference. No sentinel or omission check.
3. Purge the old `RunOutcomeResponseRecord` attempt-array serializer/deserializer, `seen` guard, and `SERIALIZED_ATTEMPT_LINEAGE_KEY` when the separate-table codec replaces that path. No legacy or fallback support, and no `seen` in the new codec.

## Approved card restoration, 2026-10-01 — implemented and verified
The operator corrected the placement: the response-body field follows **`KTP_LAST_NAME_COL`**, not the SourceKey columns, and precedes session metadata. The card contains the exact `RunOutcomeResponseRecord.response_body` string sent over HTTP, not `outcome.serialize()` (the full HTTP envelope) or the separate full query snapshot. The obsolete commit-request-body column has no consumer and is removed from the staging schema and accepted-output row, not merely hidden in the card. No new response-body class is authorized.

~~~python
# protected/src/backend/helpers/vars.py
KTP_AI_AUGMENT_RUN_OUTCOME_RESPONSE_BODY_COL = (
    f"{AI_AUGMENT_COLUMN_PREFIX}run_outcome_response_body"
)

# In CODEX_OUTPUT_SCHEMA, immediately after the surname:
(KTP_LAST_NAME_COL, "VARCHAR NOT NULL"),
(KTP_AI_AUGMENT_RUN_OUTCOME_RESPONSE_BODY_COL, "VARCHAR"),
(KTP_AI_AUGMENT_COMMIT_REQUEST_RECORD_ID_COL, "VARCHAR NOT NULL UNIQUE"),
~~~

~~~python
# ai_augment_backend_store.py, existing completed-outcome UPDATE:
f"{duckdb_quote_identifier(KTP_AI_AUGMENT_RUN_OUTCOME_RECORD_ID_COL)} = ?, "
f"{duckdb_quote_identifier(KTP_AI_AUGMENT_RUN_OUTCOME_RESPONSE_BODY_COL)} = ? "
# corresponding values:
str(outcome.record_id),
outcome.response_body,
~~~

`_replace_codex_output_view` already carries every non-internal schema column in order; `build_cards` renders that flat field without a new renderer. Retain the independent `codex_run_outcome_records` full graph snapshot for query. Remove `KTP_AI_AUGMENT_COMMIT_REQUEST_BODY_COL` from globals/schema, the accepted-output row, and the view's now-obsolete exclusion. Preserve commit request body in the authoritative record/replay log; only its redundant staging copy goes. Surgically adapt existing affected assertions; no new tests or fallback.

## Settled change contour — ID-only validation replay body
IMPLEMENTED AND VERIFIED. The existing _ValidationRequestBodyJson owns the JSON schema and parsing. No parallel validation-body JSON-key globals, manual json.loads/key-set checks, or LazyResultFactory for immediate UUID resolution. If a JSON-key constant proves unavoidable elsewhere, name it with _JSON_KEY. No detour architecture.py edit was made.

### 1. validation_request.py: wire representation and inverse
Keep ValidationRequestBody's architecture-defined Python fields as typed objects. The private JSON model is the exact wire schema for serialization and parsing.

~~~python
class _ValidationRequestBodyJson(FrozenStrictModel):
    commit_request_record_id: UUID
    post_commit_validation: PostCommitValidation
    initial_validation_request_record_id: UUID | None
    openalex_ror_records_ids: tuple[UUID, ...]
~~~

Replace only ValidationRequestBody.serialize's body; retain @model_serializer and its existing http_record creation.

~~~python
@model_serializer
def serialize(self) -> dict[str, object]:
    return _ValidationRequestBodyJson(
        commit_request_record_id=self.commit_request_record.record_id,
        post_commit_validation=self.post_commit_validation,
        initial_validation_request_record_id=(
            None if self.initial_validation_request_record is None
            else self.initial_validation_request_record.record_id
        ),
        openalex_ror_records_ids=tuple(
            record.record_id for record in self.openalex_ror_records
        ),
    ).model_dump(mode="json")
~~~

Add the inverse on ValidationRequestBody; Store passes exactly its commit/initial references and its existing projected-DB HTTP-record reader. Pydantic parses UUIDs, fields, and post_commit_validation. The method checks only semantic links and constructs architecture-defined objects; it does not import Store or run SQL.

~~~python
@classmethod
def from_serialized_json(
    cls,
    value: str,
    *,
    commit_request_record: BackendCommitRequestRecord,
    initial_validation_request_record: BackendValidationRequestRecord | None,
    resolve_http_record: Callable[[UUID], HttpRequestLogRecord],
) -> Self:
    parsed = _ValidationRequestBodyJson.model_validate_json(value)
    if parsed.commit_request_record_id != commit_request_record.record_id:
        raise ValueError(Locale.VALIDATION_COMMIT_LINK_INVALID)
    if parsed.initial_validation_request_record_id != (
        None if initial_validation_request_record is None
        else initial_validation_request_record.record_id
    ):
        raise ValueError(Locale.VALIDATION_INITIAL_LINK_INVALID)
    return cls(
        commit_request_record=commit_request_record,
        post_commit_validation=parsed.post_commit_validation,
        initial_validation_request_record=initial_validation_request_record,
        openalex_ror_records=tuple(
            resolve_http_record(record_id)
            for record_id in parsed.openalex_ror_records_ids
        ),
    )
~~~

Existing ValidationRequestBody.validate_body still checks retry lineage and duplicate/non-v7 provider IDs. BackendValidationRequestRecord.validate_record retains its HTTP-contour checks and compares the Pydantic-parsed request body with the typed body's serialized view; it no longer parses full embedded HTTP envelopes.

~~~python
parsed = _ValidationRequestBodyJson.model_validate_json(self.request_body)
initial = self.validation_request_body.initial_validation_request_record
if (
    parsed.model_dump(mode="json") != self.validation_request_body.serialize()
    or self.request_headers
    != self.validation_request_body.commit_request_record.request_headers
    or (initial is not None and initial.record_id == self.record_id)
):
    raise ValueError(Locale.VALIDATION_BODY_MISMATCH)
~~~

### 2. ai_augment_backend_store.py: replay and checks
In _apply_durable_record's /validate branch, retain the hard typed-cursor requirement, log-readback/DB projection, and attempt insertion. Replace its manual JSON decoding and body construction with:

~~~python
commit_ref = self._current_replayed_record
if not isinstance(commit_ref, BackendCommitRequestRecord):
    raise ValueError(Locale.REPLAY_VALIDATION_COMMIT_MISMATCH)
if record.request_body is None:
    raise ValueError(Locale.VALIDATION_BODY_MISSING)
initial_ref = self._initial_validation_for_commit(commit_ref)
body = ValidationRequestBody.from_serialized_json(
    record.request_body,
    commit_request_record=commit_ref,
    initial_validation_request_record=initial_ref,
    resolve_http_record=self._http_record,
)
self._apply_validation_record(
    record,
    body=body,
    commit_ref=commit_ref,
    initial_ref=initial_ref,
)
validation = BackendValidationRequestRecord.from_http_request_log_record(
    record,
    validation_request_body=body,
)
assert validation.validation_request_body is body
self._insert_validation_request_record_id(validation)
reconstructed = validation
~~~

The operator identified the immediate post-construction `body` identity assertions as redundant: `ValidationRequestBody` had just been given those exact references. Remove the two analogous live-construction assertions too. Keep `_apply_validation_record`'s argument-boundary checks and Store's `_assert_lifecycle_links` checks after reconstruction; those verify boundaries rather than restating constructor arguments.

In _apply_validation_record, remove the parsed argument and only checks of now-absent embedded commit/pull/push/initial HTTP envelopes. Keep its cursor-is-commit assertion, projected commit/initial UUID and ordinal checks, request-header checks, the existing provider _http_record_with_ordinal check (earlier than validation, complete, equals the body-resolved record), ModelHttpInterceptor.from_records, evaluate_commit call, observed-vs-recomputed validation and provider-ID comparisons, and _project_validation. Do not change failure ordering unnecessarily. Provider records are separate earlier replay-log lines and are fetched from the projected detour DB via Store._http_record, not copied inside /validate. Store's shared append/readback/project/reconstruct/compare/cursor contour remains unchanged.

### 3. Other consumers of the old embedded validation envelopes
RunOutcomeResponseRecord.from_serialized_json now handles only its replay-log HTTP record and a caller-provided attempt byref; it no longer walks embedded validation envelopes. Store's cursor holds only the latest lifecycle record, **not every historical outcome's refs**. For query, Store._codex_innerdicts gets each historical outcome's complete secondary snapshot from projected detour DB, constructs typed CodexInnerDict and AiAugmentSingularOuterDict, and serializes a **fully self-contained query payload**. The dashboard parses it using _QueryResponseBodyJson → _AiAugmentSingularOuterDictJson → _CodexInnerDictJson and reconstructs its typed graph from that payload, with no Store/DB access. The query-only payload includes full pull, push, commit, validation, and provider HTTP envelopes; the principal /validate and /completed replay-log lines remain ID-based/lean. The query-only serialized-record schema lives at the existing CodexInnerDict JSON handoff, not inside RunOutcomeResponseRecord.serialize (whose record-level semantics are the replay-log HTTP line). Section 7 specifies the private JSON fields; no competing architecture class.

Current query call path: Store.query_response_record calls QueryResponseRecord.from_query_request with Store.ai_augment_singular_outerdicts(); that reads the projected codex_innerdicts table. IPC reconstructs QueryResponseRecord from its HTTP envelope. The dashboard receives the query response body and calls DashboardQuerySnapshot.from_serialized_json → QueryResponseRecord.outerdicts_from_response_body. QueryResponseRecord.from_serialized_json is **not currently the dashboard body parser**. Store's live append and full log rebuild project/read back each record, so DB is the proper historical source; no full replay-log replay per query. But projected HTTP rows/secondary rows do not automatically preserve typed Python refs for all earlier outcomes. Store must reconstruct historical objects from DB before serializing a complete query payload; the dashboard cannot receive Store's Python object identities across the socket. Avoid the invented name lineage in any proposed model/class: describe existing validation/pull/push/commit objects and their query-only serialized HTTP envelopes directly. Any proposal to pass Store refs into QueryResponseRecord.from_serialized_json must distinguish a Store-side construction call from the dashboard's independent body deserialization and must not make the latter depend on Store.

Read-only code audit: _http_record_with_ordinal(UUID) returns a projected **base** HttpRequestLogRecord; _backend_commit_request_record(record) only verifies/returns the **current cursor** commit, not an arbitrary historical one. _replay_durable_record invokes the projection transaction and must not be rerun by a read-only query. Store does not have an existing arbitrary-ID typed readback function to invoke as-is; the secondary snapshot design below avoids needing one. QueryResponseRecord.from_query_request constructs the backend response; its from_serialized_json is a decoder, not a serializer. The dashboard can only reconstruct from the fully serialized query response body, not receive Store's Python references.

Query reconstruction boundary: at _apply_run_outcome_record, Store already has the reconstructed RunOutcomeResponseRecord and its attempt→commit→push→pull→prior-validation graph. A complete secondary JSON snapshot of that graph must be projected once into **codex_run_outcome_records**, with exactly two columns: run_outcome_record_id (primary key) and serialized_json. Insert plainly: any key conflict fails the projection transaction and the detour loudly; no upsert, ignore, overwrite, or fallback. The **full graph snapshot** must not be in codex_output_rows or codex_innerdicts; the separate compact HTTP response body **does** belong in the flat card innerdict. Rebuilding from log must regenerate both. Section 7 defines the private JSON-only graph codec; its former same-column storage/readback proposal is withdrawn. Store combines card rows and snapshot records when constructing CodexInnerDict for query; the dashboard reconstructs from the complete query body without Store. Record-level serialize/from_serialized_json retain their distinct replay-log meanings.

### 4. Four-method AiAugmentHttpRequestLogRecord audit
Explicitly declare http_request_log_record, from_http_request_log_record, serialize, and from_serialized_json on every subclass, including RequestRecord, ResponseRecord, PullRequestRecord, PullResponseRecord, PushRequestRecord, PushResponseRecord, BackendCommitRequestRecord, BackendValidationRequestRecord, RunOutcomeRequestRecord, RunOutcomeResponseRecord, QueryRequestRecord, and QueryResponseRecord. AgentRuntimeAttempt is an alias of BackendValidationRequestRecord, not another class. A method body containing only pass is invalid; plain subclasses use explicit super() delegation where it truly works, e.g.:

~~~python
@property
def http_request_log_record(self) -> HttpRequestLogRecord:
    return super().http_request_log_record

@classmethod
def from_serialized_json(cls, *, value: str) -> Self:
    return super().from_serialized_json(value=value)

def serialize(self) -> dict[str, object]:
    return super().serialize()
~~~

The complete plain-record delegation pattern also includes:

~~~python
@classmethod
def from_http_request_log_record(
    cls, *, http_request_log_record: HttpRequestLogRecord,
) -> Self:
    return super().from_http_request_log_record(
        http_request_log_record=http_request_log_record,
    )
~~~

Use this only when no excluded byref field must be supplied. Pull/push response, commit, validation, run outcome response, and query response use child-specific reconstruction. serialize/from_serialized_json represent the replay-log serialized HTTP record, not a secondary graph; the separate JSON-only outcome codec carries the query graph. QueryRequestRecord/QueryResponseRecord are ephemeral, but still participate in the method audit.

The operator's exact decisions for the response codecs and old-path removal are summarized above. Store still supplies its owned references on authoritative replay; accepted pushes still require a valid pull.

### 5. Record-class audit and implementation requirements
The operator authorizes **redefining the existing four AiAugmentHttpRequestLogRecord methods in a subclass whenever justified**, visibly and specifically; do not add a separate thin adapter method. A bogus super() forwarding override on a reference-bearing record is not acceptable. Optional pull/push decoder references default to `None` per the settled decision above; the approved item-3 methods supply the concrete commit/validation/outcome decoder signatures. Store's authoritative DB-readback path uses `from_http_request_log_record` with its owned references, not an unnecessary serialize/decode round trip. The Store branch in section 2 is a body-first contour; BackendValidationRequestRecord.from_serialized_json is separately usable with supplied references. The secondary JSON codec and separate-table SQL are implemented as described in section 7.

AgentRuntimeAttempt is **an alias** of BackendValidationRequestRecord, not another Record class. Excluded byref fields are reconstructed from Store-supplied references for replay; full historical graphs use the separate JSON-only query codec. There is no attempt default_factory.

### 6. Verification
Existing tests/fixtures were adapted surgically to ID-only validation JSON and the restored card field; no tests were wholesale removed, excluded BDD was untouched, and there is no old-record fallback. The one later operator-requested recovery integration test is documented below. The final full feasible detour suite, operator preflight, Ruff, and mypy pass as recorded above. The human operator's full pre-commit-operator task remains to run on Darwin/Lima/Chrome.

### 7. Secondary query JSON codec — separate two-column storage settled
Store already has the fully linked outcome object while projecting `/completed`. The two private JSON-only models below encode and decode it. Their storage is **codex_run_outcome_records(run_outcome_record_id PRIMARY KEY, serialized_json)**, one snapshot per outcome record ID; a duplicate key is a fatal detour projection error, never an upsert/ignore. The former proposal to put the snapshot in codex_output_rows and materialize it into codex_innerdicts is withdrawn. Store serializes its DB-readback reconstructed RunOutcomeResponseRecord with its byref attempt graph through `_RunOutcomeResponseRecordJson.from_run_outcome_response_record(outcome).model_dump_json()`, not through the lean record-level `outcome.serialize()`. Rebuilding DuckDB from the replay log must regenerate the table using that same projection. The existing outcome ID in codex_output_rows links card rows to the snapshot for query.

**Implemented and verified pieces:** Store's outcome projection and `_codex_innerdicts`, the concrete pull/push/commit/validation/outcome constructors, the CodexInnerDict JSON handoff, `QueryResponseRecord.from_query_request`, and the complete typed secondary JSON representation of the referenced validation records. No full commit/provider envelopes are embedded in the principal validation body.

Two private **JSON-only** models in `codex_innerdict.py`—not new lifecycle records:

~~~python
class _CodexInnerDictValidationJson(FrozenStrictModel):
    pull_response_http_record: HttpRequestLogRecord
    push_response_http_record: HttpRequestLogRecord
    commit_request_http_record: HttpRequestLogRecord
    validation_request_http_record: HttpRequestLogRecord
    openalex_ror_records: tuple[HttpRequestLogRecord, ...]

    @classmethod
    def from_validation_request_record(
        cls, validation: BackendValidationRequestRecord,
    ) -> Self:
        body = validation.validation_request_body
        commit = body.commit_request_record
        pull = commit.commit_request_body.pull_response_record
        push = commit.commit_request_body.push_response_record
        return cls(
            pull_response_http_record=pull.http_request_log_record,
            push_response_http_record=push.http_request_log_record,
            commit_request_http_record=commit.http_request_log_record,
            validation_request_http_record=validation.http_request_log_record,
            openalex_ror_records=body.openalex_ror_records,
        )

    def to_validation_request_record(
        self,
        *,
        prior_validation_request_record: BackendValidationRequestRecord | None,
        initial_validation_request_record: BackendValidationRequestRecord | None,
    ) -> BackendValidationRequestRecord:
        pull = PullResponseRecord.from_http_request_log_record(
            http_request_log_record=self.pull_response_http_record,
            validation_request_record=prior_validation_request_record,
        )
        push = PushResponseRecord.from_http_request_log_record(
            http_request_log_record=self.push_response_http_record,
            pull_response_record=pull,
        )
        commit_refs: dict[UUID, PullResponseRecord | PushResponseRecord] = {
            pull.record_id: pull,
            push.record_id: push,
        }
        commit = BackendCommitRequestRecord.from_http_request_log_record(
            self.commit_request_http_record,
            resolve_http_record=commit_refs.__getitem__,
        )

        request_body = self.validation_request_http_record.request_body
        assert request_body is not None
        provider_records = {
            record.record_id: record for record in self.openalex_ror_records
        }
        body = ValidationRequestBody.from_serialized_json(
            request_body,
            commit_request_record=commit,
            initial_validation_request_record=initial_validation_request_record,
            resolve_http_record=provider_records.__getitem__,
        )
        validation = BackendValidationRequestRecord.from_http_request_log_record(
            self.validation_request_http_record,
            validation_request_body=body,
        )
        assert pull.validation_request_record is prior_validation_request_record
        assert push.pull_response_record is pull
        assert commit.commit_request_body.pull_response_record is pull
        assert commit.commit_request_body.push_response_record is push
        assert body.commit_request_record is commit
        assert body.initial_validation_request_record is initial_validation_request_record
        return validation
~~~

The other JSON model holds the completed outcome envelope and those validations in chronological order:

~~~python
class _RunOutcomeResponseRecordJson(FrozenStrictModel):
    run_outcome_response_http_record: HttpRequestLogRecord
    validation_requests: tuple[_CodexInnerDictValidationJson, ...]

    @classmethod
    def from_run_outcome_response_record(
        cls, outcome: RunOutcomeResponseRecord,
    ) -> Self:
        validations: list[_CodexInnerDictValidationJson] = []
        validation = outcome.attempt
        while validation is not None:
            validations.append(
                _CodexInnerDictValidationJson.from_validation_request_record(
                    validation
                )
            )
            pull = (
                validation.validation_request_body.commit_request_record
                .commit_request_body.pull_response_record
            )
            validation = pull.validation_request_record
        return cls(
            run_outcome_response_http_record=outcome.http_request_log_record,
            validation_requests=tuple(reversed(validations)),
        )

    def to_run_outcome_response_record(self) -> RunOutcomeResponseRecord:
        prior: BackendValidationRequestRecord | None = None
        initial: BackendValidationRequestRecord | None = None
        for serialized in self.validation_requests:
            validation = serialized.to_validation_request_record(
                prior_validation_request_record=prior,
                initial_validation_request_record=initial,
            )
            if initial is None:
                initial = validation
            prior = validation
        outcome = RunOutcomeResponseRecord.from_http_request_log_record(
            self.run_outcome_response_http_record,
            attempt=prior,
        )
        if outcome._body().validation_record_id != (
            None if prior is None else prior.record_id
        ):
            raise ValueError(Locale.RUN_OUTCOME_ATTEMPT_LINK_INVALID)
        assert outcome.attempt is prior
        return outcome
~~~

The two-column table shape and codec source are settled; exact SQL write/read wiring is mechanical implementation work. Current `CODEX_OUTPUT_SCHEMA` makes commit_request_record_id unique, and `/completed` selects by that ID, so a completed outcome can match **at most one** staged output row and produce at most one card innerdict. The existing `fetchall()`/loop does not imply multiple rows; the agent's earlier claim that one outcome could produce multiple card rows was incorrect. Insert one snapshot for the matched completed outcome. The old same-column write/read snippets are withdrawn. Decode `serialized_json` from the new table with `_RunOutcomeResponseRecordJson.model_validate_json(run_outcome_json).to_run_outcome_response_record()`.

The CodexInnerDict JSON handoff changes **only the outcome snapshot field**. Do not introduce another procedure-restoration validator, serializer, or JSON format: `CodexInnerDict.innerdict` is already an `InnerDict` object; its existing `from_serialized` uses `InnerDict.from_mapping(serialized.innerdict, _CodexInnerDictProcedure())`, and its existing `_CodexInnerDictJson.from_codex_innerdict` takes `value.innerdict.data` for the JSON wire. The private JSON-only field's mapping is a wire value, not the authoritative innerdict object. This existing conversion is already implemented and must be preserved.

~~~python
# In the existing _CodexInnerDictJson, retain its innerdict field and
# value.innerdict.data constructor argument. Replace only its outcome field:
run_outcome_response_record_json: _RunOutcomeResponseRecordJson

# Replace only the outcome constructor argument:
run_outcome_response_record_json=(
    _RunOutcomeResponseRecordJson.from_run_outcome_response_record(
        value.run_outcome_response_record
    )
)

# In CodexInnerDict.from_serialized:
run_outcome_response_record = (
    serialized.run_outcome_response_record_json.to_run_outcome_response_record()
)
innerdict = InnerDict.from_mapping(
    serialized.innerdict, _CodexInnerDictProcedure(),
)  # existing typed reconstruction, unchanged
~~~

`_AiAugmentSingularOuterDictJson` and `_QueryResponseBodyJson` then carry that complete nested representation using their existing path. **No new `QueryResponseRecord` factory is needed on the backend**: `from_query_request(...)` already accepts Store's fully reconstructed outerdicts and serializes the response. The dashboard's existing body parser reconstructs the same graph from JSON without Store access.

Full graph copies belong only in the **separate secondary DuckDB table and query representation**, while `/validate` and `/completed` replay-log lines stay lean. `codex_innerdicts` remains card-only, including its session metadata summary and the new compact run-outcome response-body JSON field. `RunOutcomeResponseRecord.serialize/from_serialized_json` must mean the record's replay-log JSON. No old-record fallback or dual-format handling.


## Operator-retained exact items 1–3

The operator directed that items 1 and 2 be recorded exactly, and explicitly approved item 3 within the exact supplied shape. These snippets supersede the corresponding gaps above. Source implementation and feasible local verification are complete.

**1. Outcome link.**

```python
if outcome._body().validation_record_id != (
    None if prior is None else prior.record_id
):
    raise ValueError(Locale.RUN_OUTCOME_ATTEMPT_LINK_INVALID)
```

**2. Validation self-reference.**

```python
or (initial is not None and initial.record_id == self.record_id)
```



**3. Record methods.**

```python
# BackendCommitRequestRecord
@classmethod
def from_serialized_json(
    cls,
    *,
    value: str,
    resolve_http_record: Callable[
        [UUID], PullResponseRecord | PushResponseRecord
    ] | None = None,
) -> Self:
    if resolve_http_record is None:
        raise ValueError(Locale.COMMIT_REFERENCES_REQUIRED)
    return cls.from_http_request_log_record(
        HttpRequestLogRecord.model_validate_json(value),
        resolve_http_record=resolve_http_record,
    )

def serialize(self) -> dict[str, object]:
    return self.http_request_log_record.model_dump(mode="json")
```

```python
# BackendValidationRequestRecord
@classmethod
def from_serialized_json(
    cls,
    *,
    value: str,
    commit_request_record: BackendCommitRequestRecord | None = None,
    initial_validation_request_record: BackendValidationRequestRecord | None = None,
    resolve_http_record: Callable[[UUID], HttpRequestLogRecord] | None = None,
) -> Self:
    if commit_request_record is None:
        raise ValueError(Locale.VALIDATION_COMMIT_LINK_INVALID)
    if resolve_http_record is None:
        raise ValueError(Locale.VALIDATION_HTTP_REFERENCES_INVALID)
    record = HttpRequestLogRecord.model_validate_json(value)
    if record.request_body is None:
        raise ValueError(Locale.VALIDATION_BODY_MISSING)
    body = ValidationRequestBody.from_serialized_json(
        record.request_body,
        commit_request_record=commit_request_record,
        initial_validation_request_record=initial_validation_request_record,
        resolve_http_record=resolve_http_record,
    )
    return cls.from_http_request_log_record(
        record, validation_request_body=body,
    )

def serialize(self) -> dict[str, object]:
    return self.http_request_log_record.model_dump(mode="json")
```

```python
# RunOutcomeResponseRecord
@classmethod
def from_serialized_json(
    cls, *, value: str, attempt: AgentRuntimeAttempt | None = None,
) -> Self:
    outcome = cls.from_http_request_log_record(
        HttpRequestLogRecord.model_validate_json(value),
        attempt=attempt,
    )
    if outcome._body().validation_record_id != (
        None if attempt is None else attempt.record_id
    ):
        raise ValueError(Locale.RUN_OUTCOME_ATTEMPT_LINK_INVALID)
    return outcome

def serialize(self) -> dict[str, object]:
    return self.http_request_log_record.model_dump(mode="json")
```

## Settled items 4–5 — implemented and verified

### 4. Keep the persisted researcher-card innerdict plain and card-only

Operator clarification: `CODEX_INNERDICT_TABLE` has the same plain-innerdict meaning as XLSX/DOCX innerdict tables: its JSONL contains flat researcher-card key/value data, the existing `KTP_AI_AUGMENT_SESSION_METADATA_COL`, and the compact `KTP_AI_AUGMENT_RUN_OUTCOME_RESPONSE_BODY_COL` JSON string. The full run-outcome graph snapshot needed for query construction belongs in **codex_run_outcome_records(run_outcome_record_id PRIMARY KEY, serialized_json)**, not in the innerdict table or repeated in each output row. Store joins that separate table for query. XLSX/DOCX and Codex innerdict tables share the two-column `(KTP_NAMEKEY_COL, KTP_INNERDICT_JSONLINES_COL)` schema. Section 7's same-column graph-storage snippets and the previous filter-on-read item 4 are withdrawn. Points 2 and 3 are settled above; no copied legacy cycle guard.

### 5. Preserve the architecture's two-field CodexInnerDict

`CodexInnerDict` remains exactly `innerdict: InnerDict` plus `run_outcome_response_record: RunOutcomeResponseRecord`. In the private JSON-only wire model, the corresponding field is `run_outcome_response_record_json: _RunOutcomeResponseRecordJson`; `run_outcome_json` names the stored/read snapshot value. Its `innerdict` mapping is only the serialized image of `InnerDict.data`; the authoritative model and existing procedure-restoration path stay typed. No `attempt` field is added to CodexInnerDict, QueryResponseRecord, or any outerdict: only RunOutcomeResponseRecord owns `attempt` beside `run_outcome_request_record`.

~~~python
class _CodexInnerDictJson(FrozenStrictModel):
    innerdict: dict[str, Any]
    run_outcome_response_record_json: _RunOutcomeResponseRecordJson

    @classmethod
    def from_codex_innerdict(cls, value: CodexInnerDict) -> Self:
        return cls(
            innerdict=value.innerdict.data,
            run_outcome_response_record_json=(
                _RunOutcomeResponseRecordJson.from_run_outcome_response_record(
                    value.run_outcome_response_record
                )
            ),
        )

# In CodexInnerDict.from_serialized:
return cls(
    innerdict=InnerDict.from_mapping(
        serialized.innerdict, _CodexInnerDictProcedure(),
    ),
    run_outcome_response_record=(
        serialized.run_outcome_response_record_json.to_run_outcome_response_record()
    ),
)
~~~

The existing session metadata summary **remains card data**, and the run-outcome response body is restored as card data. `CodexInnerDict.validate_codex_innerdict` must continue to check its `KTP_AI_AUGMENT_SESSION_METADATA_COL` against the outcome session ID. Store additionally reads staging metadata from `codex_output_rows` and the outcome snapshot from `codex_run_outcome_records`, verifying the same session link. Exact readback SQL is implementation detail:

~~~python
session_id = outcome._codex_session_record().session_id
if session_id is None or session_id != outcome.run_outcome_request_record.session_id:
    raise ValueError(Locale.INNERDICT_OUTCOME_MISMATCH)
summary = CodexRolloutRecord.parse_summary_json(
    self._required_text(KTP_AI_AUGMENT_SESSION_METADATA_COL)
)
if UUID(summary[CODEX_SESSION_ID_JSON_KEY]) != session_id:
    raise ValueError(Locale.INNERDICT_OUTCOME_MISMATCH)
~~~

Items 4–5 are implemented and verified by the local checks above. Section 7's JSON-only snapshot construction/reconstruction and separate-table boundary govern the implementation.

## Implemented surgical rename: commit/validation-request index

Operator selected `commit_validation_request_record_index` for the existing secondary commit→validation ID lookup. Its rows are not `AttemptProperty` objects: `AgentRuntimeAttempt` aliases `BackendValidationRequestRecord`, while the table holds only IDs. The implemented two-plain-column shape is:

```sql
CREATE TABLE commit_validation_request_record_index (
    commit_request_record_id VARCHAR PRIMARY KEY,
    validation_request_record_id VARCHAR NOT NULL
);
```

Confine edits to the table/column/DDL constants in `protected/src/backend/helpers/vars.py`, Store's insert and reads/check (including direct ID select in completed outcome), affected API constant reexports, and existing tests that inspect the table or monkeypatch the insert. Remove the one-field `attempt_record` JSON and its JSON key; no old-schema fallback or implicit migration. Keep the `/validate` replay line, typed attempt, replay order, other detour tables, and architecture.py unchanged. Existing DBs require the established explicit replay-log/CAS rebuild. No new tests; verify surgically adapted tests, Ruff, mypy, diff check.

Implemented. Operator clarified that `attempt_record` is not an implementation concept; use `validation_request_record_id`, not `attempt_id` (retry audit already uses `attempt_id` for commit ID). Backend-focused tests: 14 passed; detour mypy and targeted Ruff passed. The operator preflight had 71 passed and one 30-second subprocess timeout while run concurrently with backend tests; the timed-out case passed alone in 16 seconds. The full feasible detour suite then passed serially without concurrent load: 750 passed, 5 skipped, 4 deselected. Query review finding, not part of this rename: `codex_innerdicts` already carries session metadata; `_codex_innerdicts` redundantly reads it from `codex_output_rows` as a cross-projection check. No edit to that path without separate review.

## Current read-only detour DB audit

The operator requested an atom-by-atom verification of their table-flow narrative and a complete count/audit of every detour DB table. Static source inventory: **11 persistent user tables** when all lifecycle stages have occurred (`replayed_http_request_log_records`, `commit_validation_request_record_index`, `codex_fc`, `codex_fco`, `codex_calls`, `codex_turn_ref`, `codex_retry_baselines`, `codex_evidence_attempts`, `codex_output_rows`, `codex_run_outcome_records`, `codex_innerdicts`). There are **two views** (`codex_output`, plus `codex_turn_ref_normalized` only for match version 2); the normalized view is created but has no production reader in the detour source. The shared materializer briefly creates and drops `codex_innerdicts_frame`, which is not a persistent table. Relation creation is lazy: empty rebuild has two tables, first accepted push makes ten, first completed accepted outcome makes eleven. The separate sample inference proxy's `pricing_daily` and `requests` are SQLite tables in another DB and are excluded. This is a code-defined inventory, not a physical DB-file introspection. Audit findings: startup log projection verifies ordinal/row-count/hash coverage, not every projected UUID/JSON envelope; `codex_output_rows` is populated for accepted validations, keyed by commit ID plus unique filename/fragment, not every accepted HTTP push/validation; `codex_innerdicts` contains only completed-card flat data, grouped by namekey; `codex_run_outcome_records` stores a full typed outcome/attempt graph projection for historical query readback, not a copy of the flat output or a replay input. All are secondary to log/CAS, though operationally used. Rebuild also constructs Context from current config and a read-only main source DB, so log+CAS alone have not been shown sufficient under source/config drift. Do not change schema/query/verification paths without separate approval; this request is review only.

Implemented rename: `detour_http_records` → `replayed_http_request_log_records`. The operator directly instructed implementation on 2026-10-01; schema and replay behavior were unchanged. Source check: both live append and rebuild parse the log line as `HttpRequestLogRecord` before DB insert; `_apply_durable_record` inserts and reads it back inside a transaction, so a failure there rolls that transaction back. But `_replay_durable_record`'s envelope-value comparison runs **after** that transaction commits; live append's stronger same-type/original-object comparison also runs after commit, whereas rebuild has no original typed object to compare. Any failure poisons that Store instance; it does not necessarily terminate the OS process or undo the durable log, and a post-commit comparison failure need not remove the DB row. The new name is descriptive of successfully projected rows, but it does not imply atomic certification by the postcommit check.

Recovery RCA: the agent's earlier categorical statement that explicit `--new` is always required after a failed live append was too strong. Manual backend CLI requires either `--new` or `--resume` and asks for confirmation unless `--yes`; `--new` additionally prompts for nonempty-log replay unless `--yes`. These are selected-mode confirmations, not a failure-triggered rebuild prompt. `--resume` constructs a fresh Store and verifies log/DB ordinal coverage and hashes, not the previous instance's `_failure` or every projected UUID/payload. If an appended line lacked a committed DB row, resume fails coverage verification and `--new` is needed. If failure occurred after a row committed and log/DB coverage and downstream query checks pass, Store `--resume` may succeed despite the prior Store failure. **Normal manual CLI startup first checks the configured full-file replay-log SHA; the unchanged pin rejects an appended log before Store opens.** After repinning the config hash (or using the explicit `--danger-no-verify-hash` CLI option), Store resume can accept the postcommit-failed row. Dashboard checks resources at its own startup, passes `--danger-no-verify-hash` to child processes, starts its first child with `--new --yes`, uses `--resume --yes` only after a clean cycle, and refuses restart in the same context after a failed cycle; a new Dashboard context starts with `--new --yes`. No production recovery-policy edit made.

Current authorized work: keep **one** real recovery test in the operator-specified **new file** `src/detours/detour_ai_augment/protected/tests/backend/test_backend_store_integration.py`, using the shared function-scoped `startup_files` fixture's `tmp_path` dummy config/source population/replay log/CAS/detour DB and production `server.configure_runtime` plus `initialize_backend_store`. No monkeypatching production. Force a failure at Store's *post-commit typed-record comparison* using an existing typed `ResponseRecord` on a non-public provider route; check the durable JSONL line, committed DB row, raw-line hash, old anchor, poisoned same Store, **actual manual `server.main` CLI `--resume --yes` subprocess refusal on the stale pin**, Dashboard-style hash-bypass Store resume, and repinned-hash Store resume. The subprocess receives the fixture's TMPDIR/NameKey environment and asserts its process-lock file exists inside `tmp_path`, not the shared system temp path. This test is the direct empirical answer to the operator's recovery question and complements the existing pre-commit readback-failure test. No production recovery-policy or schema changes in this experiment. The operator will explicitly declare when the integration test is done.

Integration test remains under operator review. The operator separately and explicitly instructed the table rename, so the earlier wait requirement no longer applies to that rename. A generic typed provider `ResponseRecord` triggers Store's real postcommit type-mismatch failure; durable log and projected row remain, row hash matches, and DuckDB anchor is still the empty prefix. The revised test explicitly verifies same-Store reads fail, the actual manual CLI subprocess refuses the changed log with an unchanged pin before Store opens, a new config-loaded Store with hash-on-init disabled resumes and appends `/pull`, and normal hash-verifying Store startup resumes after repinning **only the temporary config**. This type-mismatch trigger is intentionally artificial (production provider capture passes a base `HttpRequestLogRecord`); the test demonstrates the structural recovery gap, not a claimed ordinary provider incident. The fixture originally bootstrapped via `backend_store_lifecycle`, which transiently opened/created a shared system-temp process-lock file; operator directed removing that cross-test side effect for all consumers. Its initial empty-log rebuild now uses production `initialize_backend_store` directly, leaving subprocess startup tests' real lock behavior intact. The actual CLI proof and temp lock-path assertion pass in focused pytest (1 passed, 14.07s); focused Ruff, mypy and diff check pass. No production recovery-policy or schema edits during this investigation.

Operator moved `startup_files`, `StartupFiles`, and `source_population` into `protected/tests/fixtures/pytest_fixtures.py`. The moved fixture module is now self-contained (including its own `ROOT` and `STARTUP_NAMEKEY`) and registered from both detour test-tree `conftest.py` files. Consumers in `test_ui.py`, `test_ui_e2e.py`, `test_api.py`, `test_operator_e2e_preflight.py`, and the new integration test point to the shared fixture/helper. The new integration test explicitly checks that the **same Store** refuses a second read after the postcommit failure. Affected-file Ruff and mypy pass after the move. Full post-move run of **all 119 fixture/helper consumers** finished in 476.37s: **118 passed, 1 failed**. The sole failure was `test_completed_grid_row_uses_real_query_ipc`, after successful completed-query fixture setup, at `operator.running_dashboard -> _assert_ports_available -> socket.socket(AF_INET, SOCK_STREAM)`: this execution environment returned `PermissionError(1, Operation not permitted)`. No production or fixture assertion failed in that case; browser/ports cannot be exercised here. A pre-move run was interrupted when the operator moved the fixture; its 36 passes are superseded by the post-move run. The integration test remains under review; the operator's direct rename instruction supersedes the old rename deferral.

**Rename verification and operator readiness:** The physical table name was changed from `detour_http_records` to `replayed_http_request_log_records` in Store DDL/queries/anchor handling and affected existing tests/fixture; schema, replay behavior, and `AUTHORITATIVE_RECORDS_TABLE` constant name are unchanged. The rename-focused run passed **101 tests, 64 deselected** in 364.71s; the final full feasible run below supersedes it. Collection files in `tmp/ai-augment-rename-verification-20261001/` show **919** tests in configured main/detour/backend/operator suites plus **15** optional `tests/test_detours` tests excluded from ordinary discovery (total **934** within these sources; paused BDD and sample deploy are excluded). The first repository-main run used `pytest -q -x -m 'not real_api and not slow' tests` with per-test JUnit XML and stopped after **20 passed, 1 skipped, 1 deselected, 1 unexpected failure**. Failed node: `tests/test_duckdb_extensions.py::test_config_accepts_duckdb_extension_repo_and_platform_bins`; this Linux AMD64 environment reports platform key `linux_amd64`, whereas the configured `splink_udfs` binaries list only `linux_arm64` and `osx_arm64`. Evidence: `main.log` and `main.xml`. A second run with that test deselected stopped after **21 passed, 2 skipped, 2 deselected, 1 failure** at `tests/test_duckdb_extensions.py::test_load_duckdb_extension_from_config_path_uses_repo_or_binary`: it monkeypatches platform to `linux_arm64` but the configured absolute binary path `/Volumes/home/aicode/.duckdb/extensions/v1.5.1/linux_arm64/splink_udfs.duckdb_extension` does not exist here. Evidence: `main-after-skip.log` and `main-after-skip.xml`. The operator explicitly authorized skipping both named tests; the third platform-bound failure and authorizations are below. The final per-test inventory follows the completed checks. BDD remains excluded wholesale.

Third run with those two tests deselected stopped at `tests/test_sciscinet_name_matching.py::test_manual_best_reviewed_fixture_expectation_coverage`: its hard-coded `/Volumes/home/aicode/2026-01-02_enrich_full_df/data/test_data/sciscinet_name_matching/duckdb_ui_20260601T1750Z_export_edit_done_namekey_edit.xlsx` path is absent here. Outcome **86 passed, 2 skipped, 3 deselected, 1 failed**. Evidence: `tmp/ai-augment-rename-verification-20261001/main-after-two-skips.log` and `main-after-two-skips.xml`. The operator authorized skipping this exact test; resume with all three named tests deselected.

Fourth main-suite run with those three exact exclusions passed **140, 3 runtime-skipped, 4 deselected** (the fourth deselection is the real-API marker); evidence `main-after-three-skips.log/xml`. Full feasible detour backend/dashboard/preflight run was started with JUnit evidence `detour-feasible.xml` and `-x`. The operator explicitly waived attempts for the configured **operator, sudo, real-API, and macOS-browser** categories; these still require a per-test not-run listing, but no attempt is needed for each. Other excluded tests still need individual evidence/reason. Any unexpected failure stops the run before a fix.

The feasible detour run stopped at an unexpected failure after **655 passed, 5 runtime-skipped, 4 deselected, 1 failed** in 1045.05s. Failed node: `src/detours/detour_ai_augment/protected/tests/backend/test_appendwatch.py::test_standalone_watcher_fixtures_do_not_import_dashboard`. Its `watcher_fixture_process` child pytest run failed the `ImportAudit.pytest_runtest_call` assertion at `protected/tests/pytest_plugin.py:570-578`; the traceback does not identify which of the three import-audit assertions failed. Evidence: `tmp/ai-augment-rename-verification-20261001/detour-feasible.log` and `detour-feasible.xml`. Initially stopped without a fix or exclusion; the subsequent isolated rerun and diagnosis are recorded below.

Operator authorized a read-only investigation of that particular failure, and separately requested use of `AUTHORITATIVE_RECORDS_TABLE` from vars instead of a literal in `backend_startup_process`; that exact function-local import/query edit is made, Ruff passes, and it does **not** address the import audit. Isolated rerun reproduced the failure (`watcher-isolated.log/xml`). Read-only child diagnostic (`watcher-import-diagnostic.log`) found `isolated_lima_configuration=False`, no NiceGUI modules, and `fastapi_loaded=True`. Cause: `protected/tests/conftest.py` now registers `fixtures.pytest_fixtures`; importing that fixture module eagerly imports both backend `server` and `ai_augment_backend_store`, each of which loads FastAPI. Importing only backend vars does not. Therefore the child pytest process has FastAPI in `sys.modules` before watcher test execution, violating the deliberate no-FastAPI assertion. This is a deterministic test-fixture import-isolation regression, not a Linux platform/resource failure or appendwatch functional failure. The operator subsequently approved the narrow import move, recorded below.

The operator approved moving those two backend imports from module top-level into `startup_files()` in `protected/tests/fixtures/pytest_fixtures.py`, with no other fixture change. Applied exactly. The isolated watcher test now passes **1/1 in 5.42s**; evidence `tmp/ai-augment-rename-verification-20261001/watcher-after-fix.log/xml`. The 95 previously unexecuted feasible detour nodes passed **95/95 in 57.57s** (`detour-remaining.log/xml`). A separate fixture-closure inventory found **97** tests using `startup_files`: **95 locally feasible**, **2 in exempted macOS-browser `test_ui_e2e.py`**. The focused run of all 95 locally feasible fixture users passed **95/95 in 444.19s** (`startup-fixture-focused.log/xml`); node lists are `startup-fixture-all-nodes.txt` and `startup-fixture-feasible-nodes.txt` in the same evidence directory. Thus all selected feasible detour nodes are accounted for across the original and continuation runs: **751 passed, 5 runtime-skipped, 4 marker-deselected**; the fixture-focused run separately verifies every locally feasible user after the import move.

**Optional-detour inventory, 2026-10-01:** A separately collected `tests/test_detours` run stopped at `tests/test_detours/test_detour_mode0_econ_stats.py::test_detour_contract_and_mode0_econ_stats_readonly`: `src/detours/detour_mode0_econ_stats.py:689` requires Plotly/Kaleido from the optional `detour-mode0-econ-stats` environment, unavailable in the required detour-ai-augment environment (`optional-detours.log/xml`). After the operator authorized skipping that exact test, `test_detour_module_entrypoint` failed at the same child-process import (`optional-detours-after-skip.log/xml`); the operator authorized skipping that specific test too. With those two and the TASK-excluded slow main-pipeline test deselected, **12/12 passed, 3 deselected in 20.78s** (`optional-detours-after-two-skips.log/xml`). Ten renamed-table SQL E501 errors were corrected with `AUTHORITATIVE_RECORDS_TABLE` and line wrapping; full Ruff now passes (`ruff-after-fix.log`). The 11 fixture-move mypy import errors found at that time (`mypy-detour.log`) were later resolved by the four approved direct imports; mypy now passes 63 source files. The final post-edit detour run and per-test inventory are below. Do not modify the other detour's code.

## Current authorized attempt-naming audit (2026-10-01)
Operator first directed `codex_retry_baselines.attempt_id` → `commit_record_id`, then explicitly directed a grep of all `attempt` uses against architecture's narrow `AttemptProperty` (`AgentRuntimeAttempt` aliases `BackendValidationRequestRecord`) and appropriate renames wherever the referent is not that object. Initial grep inventory: `tmp/ai-augment-rename-verification-20261001/attempt-audit.txt` (409 matches, including tests/prose). The only authoritative `attempt` objects are validation request records and the `RunOutcomeResponseRecord.attempt` reference to one; those refs are preserved. No architecture.py edit or legacy migration/fallback.

Implemented and verified: both `codex_retry_baselines` and the evidence-assessment audit table now call their commit-ID column `commit_record_id`; the audit table is named `codex_evidence_audits` (existing global `CODEX_EVIDENCE_AUDIT_TABLE`), since it did not contain `AttemptProperty` objects. `CODEX_RETRY_COMMIT_RECORD_ID_COL` is the single column global; the inaccurate `CODEX_RETRY_ATTEMPT_ID_COL` is gone. Store DDL/insert/read and test SQL use the new names. Baseline DTO/reads, `_EvidenceAssessmentAudit`, commit-derived `commit_request_timestamp`, retry evaluation/projection helper names, and synthetic test-helper seed names follow their actual referents. The appendwatch temp filename's placeholder now names the commit ID; its emitted filename value is unchanged. Dashboard CodexInnerDict footnote args no longer say `attempt`. The UI history panel is **“Runs and outcomes”** with `RUN_OUTCOME_HISTORY_*` names per the exact approved contour below; it includes dashboard Runs, some without a commit. Natural-language verbs and the negative check for an absent legacy `attempts` JSON key remain; they are not model references. Active `attempt` refs in outcome/query/UI remain typed `AgentRuntimeAttempt`/`BackendValidationRequestRecord`. The operator separately instructed the remaining `test_ui.py` hardcoded `COMMENT ON TABLE replayed_http_request_log_records IS NULL` use the existing table global; done.

The historical focused retry run passed **7, 1 skipped, 273 deselected** (`tmp/ai-augment-rename-verification-20261001/attempt-rename-retry.log/xml`); the final full feasible run supersedes it for current test status. The 11 fixture-import mypy errors were resolved by the four approved direct imports; detour mypy passes. Stop and report any *new* unexpected test failure before fixing it, per operator instruction. The operator flagged two misleading phrases: `RUN_OUTCOME_PROJECTION_INCONSISTENT` now says “Run-outcome projection is inconsistent” (dropping only “validation”), and unused `ACCEPTED_SESSION_DUPLICATE` was removed rather than reworded to an invented “session outcomes” concept. Source search found no consumer of that constant.

Operator approved renaming the test-only `commit_record_seed` to `synthetic_record_id_seed`: the helper hashes this synthetic input into both push and commit-request IDs; it does not come from pipeline config. Also approved backend-side local `_validate_commit(...)` result `attempt` → `validation_request_record`, preserving architecture-defined `RunOutcomeResponseRecord.attempt` and `AgentRuntimeAttempt`. Both exact renames are applied. The dashboard `test_ui.py` file passed **206/206 in 529.60s** immediately before these two separate renames (`attempt-rename-ui.log/xml`). The focused backend/HTTP-interceptor/operator-preflight selection after them passed **171, 1 skipped, 225 deselected in 404.60s** (`approved-seed-and-validation-name.log/xml`). Ruff and `git diff --check` pass.

Audit correction: `Locale.ATTEMPT_DATABASE_INCONSISTENT` is live, used by `DashboardQuerySnapshot.validate_records()` and `_ResearcherView.from_snapshot`/`_RunCommitView.backend_lifecycle`; an earlier commentary incorrectly called it unused after searching the wrong term. It was not removed or renamed. Its message “validated attempt database state is inconsistent” conflates several query/run checks and remains pending review.

The operator approved and the agent applied exactly these direct-import corrections: `StartupFiles`/`STARTUP_NAMEKEY` from `protected.tests.fixtures.pytest_fixtures` in `test_ui_e2e.py` and operator preflight; `STARTUP_NAMEKEY` from there in `pytest_plugin.py`; direct protected backend `api` import for the lock-path constant in `test_backend_store_integration.py`. `pixi run -e detour-ai-augment mypy-detour-ai-augment` now passes all 63 source files.

Collection after the first naming edits found **919** configured main/detour test nodes (`collection-after-naming.txt`); separate optional detour collection has 15, for 934 across those sources. Later approved UI renames changed two node names but not the count; the current names are recorded in the inventory below. The 772 detour nodes comprise 756 in the feasible selection plus 16 outside it (three sudo appendwatch, one real-API, three operator E2E, nine `test_ui_e2e.py` browser-module nodes). The nine browser-module nodes include the subprocess-only fixture check that passed separately and one real-query IPC case attempted earlier but blocked by denied local socket creation. The 143 main selected nodes are evidenced by `main-after-three-skips.xml`; optional 12/15 by `optional-detours-after-two-skips.xml`.
The subprocess-only `test_completed_query_fixture_has_current_queryable_history` within the browser module was separately rerun after naming and passed **1/1 in 15.19s** (`completed-query-fixture-after-naming.log/xml`); it does not require a browser. Thus the browser-module exclusion is eight remaining nodes, one of which was attempted earlier and failed at denied local socket creation.
The real recovery integration test `test_resume_after_committed_row_and_postcommit_failure` was also rerun after naming and passed **1/1 in 7.91s** (`backend-store-integration-after-naming.log/xml`).

The operator approved the exact `_RunCommit*` naming-only contour below. `_RunCommitView` combines an optional dashboard Run and optional query-derived AgentRuntimeAttempt/accepted CodexInnerDict/RunOutcomeResponseRecord, keyed by session where possible; commit ID is only a display/join key. `_RunCommitVarView` is the per-researcher-variable flattened UI state and also supports a no-run READY placeholder. The history merges query-completed records and dashboard runs, deduplicates matched sessions, and its current state feeds the main grid. Preserve real commit ID, attempt, run, outcome field names, and test fake's actual run-ID collection. No model behavior or query/replay representation change is authorized.

| Current | Approved replacement |
|---|---|
| `_RunCommitView` | `_RunAttemptView` |
| `validate_run_or_commit` | `validate_run_or_attempt` |
| `_RunCommitVarView` | `_ResearcherVarRowView` |
| `run_commit_views` / `latest_run_commit_view` | `run_attempt_views` / `latest_run_attempt_view` |
| `run_commit_var_views` / `latest_run_commit_var_view` | `researcher_var_row_views` / `current_researcher_var_row_view` |
| `run_commit_view` / `run_commit_var_view` locals | `run_attempt_view` / `researcher_var_row_view` |
| `to_var_view` | `to_researcher_var_row_view` |
| `accepted: CodexInnerDict | None` | `codex_innerdict: CodexInnerDict | None` |
| `GRID_RUN_COMMIT_TIMESTAMP_FIELD = "run_commit_timestamp"` | `GRID_TIMESTAMP_FIELD = "timestamp"` |
| `RUN_COMMIT_VIEW_EMPTY` | `RUN_ATTEMPT_VIEW_EMPTY`, saying `Run` or `AgentRuntimeAttempt` is required |

Panel: label **“Runs and outcomes”**; `RUN_HISTORY_*`/`run_history_*` → `RUN_OUTCOME_HISTORY_*`/`run_outcome_history_*`; `run_commit_detail_rows` → `run_outcome_history_rows`; HTML test IDs → `run-outcome-history-*`. Only directly affected tests adapt. The approved four direct-import corrections for mypy were applied before this naming change and verified afterward.

Implementation of this exact naming contour is complete. The only remaining `run_history` identifier in detour Python is the browser test fake's genuine collection of Run IDs. The approved four direct-import corrections are also complete. Detour mypy passes **63/63 source files**; whole-source Ruff and unstaged `git diff --check` pass after the targeted architecture-import move recorded in current status. Post-edit focused runs passed: dashboard `test_ui.py` **206/206 in 467.29s** (`approved-run-outcome-names-ui.log/xml`), operator preflight **72/72 in 55.25s** (`approved-run-outcome-names-preflight.log/xml`), Store recovery integration plus subprocess-only completed-query fixture **2/2 in 21.67s** (`approved-imports-feasible.log/xml`). The final full feasible detour run then passed **751, 5 runtime-skipped, 4 marker-deselected in 1278.50s** (`final-feasible-detour.log/xml`). No operator/browser/sudo/real-API case is claimed as passed.

## Final per-test evidence and operator handoff

Scope counted: configured main/detour/backend/operator collection **919** (`collection-after-naming.txt`) plus optional other-detour collection **15** (`collection-optional-detours.txt`), total **934**. Paused BDD and sample deploy modules are excluded by repository/task configuration and are not part of this denominator. Across those 934: **904 distinct passed** (751 final feasible detour + one browser-module subprocess-only fixture in `approved-imports-feasible.xml` + 140 repository-main + 12 optional other-detour), **8 runtime-skipped** in final JUnit, **22 without a passing run here**. Of the 22, **6 were attempted and blocked by environment/platform requirements** and **16 were not attempted** under operator instructions or TASK. Focused overlapping reruns are not double-counted. No test failed in the final feasible run. `pre-commit-operator` itself requires Darwin/Lima/Chrome (`pyproject.toml:347-378`) and was not run on this Linux host.

All evidence paths below are relative to `tmp/ai-augment-rename-verification-20261001/`. The JUnit XML files identify individual executed testcases; collection files establish the individually excluded nodes. Group prefixes save repetition: `D=src/detours/detour_ai_augment`, `R=tests`. The three operator E2E and seven remaining macOS-browser nodes were not attempted here by the operator's explicit waiver. The real-query IPC browser case *was* attempted during fixture verification and stopped at `socket.socket(AF_INET, SOCK_STREAM)` with `PermissionError(1)`; no assertion of production behavior was reached.

**Five runtime skips in `final-feasible-detour.xml` (individual `<testcase><skipped>` reasons):**

| Test node relative to D | Reason |
|---|---|
| `tests/backend/test_api.py::test_historical_haanen_retry_preserves_verified_evidence_roundtrip` | Optional historical rollout fixtures absent. |
| `tests/backend/test_api.py::test_multiple_sql_matches_report_the_exact_excerpt` | Multiple evidence matches currently allowed. |
| `tests/backend/test_ipc.py::test_dashboard_client_queries_real_mode_0600_unix_socket` | Unix sockets denied (`Operation not permitted`). |
| `protected/tests/backend/test_appendwatch.py::test_inspect_flags_nonregular_substitution_without_blocking[socket-path was replaced by a non-regular file]` | Unix sockets denied. |
| `protected/tests/backend/test_appendwatch.py::test_cli_detects_delayed_directory_fifo_symlink_and_socket_substitutions` | Unix sockets denied. |

**Three runtime skips in `main-after-three-skips.xml`:**

| Test node relative to R | Reason |
|---|---|
| `test_csv_sample_validation.py::test_csv_rows_match_samples` | Sample data absent. |
| `test_duckdb_extensions.py::test_configured_duckdb_extension_binary_loads_unaccent` | Platform-specific splink_udfs binary absent. |
| `test_sciscinet_name_matching.py::test_manual_best_reviewed_fixture_outputs_select_expected_author_ids[manual_best_reviewed_fixture_missing]` | Hard-coded macOS author-review fixture files absent. |

**22 not passed here; each node is present in the collection evidence named above:**

| Test node | Reason / attempted evidence |
|---|---|
| `R/test_duckdb_extensions.py::test_config_accepts_duckdb_extension_repo_and_platform_bins` | Attempted; Linux AMD64 not in configured splink_udfs platforms (`main.xml`, `main.log`); specific skip approved. |
| `R/test_duckdb_extensions.py::test_load_duckdb_extension_from_config_path_uses_repo_or_binary` | Attempted; configured `/Volumes/.../linux_arm64` binary absent (`main-after-skip.xml/log`); specific skip approved. |
| `R/test_sciscinet_name_matching.py::test_manual_best_reviewed_fixture_expectation_coverage` | Attempted; hard-coded macOS XLSX fixture absent (`main-after-two-skips.xml/log`); specific skip approved. |
| `R/test_sciscinet_name_matching.py::test_real_api_openalex_identifies_known_false_confident_ssn_picks[NOTSET]` | Real-API marker; operator waived attempt. |
| `R/test_detours/test_detour_mode0_econ_stats.py::test_detour_contract_and_mode0_econ_stats_readonly` | Attempted; optional Plotly/Kaleido env absent (`optional-detours.xml/log`); specific skip approved. |
| `R/test_detours/test_detour_mode0_econ_stats.py::test_detour_module_entrypoint` | Attempted; child process needs same optional env (`optional-detours-after-skip.xml/log`); specific skip approved. |
| `R/test_detours/test_detour_step4_breakdown.py::test_slow_real_config_pre_deviation_full_equivalence` | Real main-pipeline resources prohibited by TASK; not attempted. |
| `D/protected/tests/backend/test_appendwatch.py::test_cli_static_eacces_is_scoped_and_recovered_files_fail_closed` | needs_sudo; operator waived attempt. |
| `D/protected/tests/backend/test_appendwatch.py::test_cli_dynamic_eacces_existing_watch_is_detected_and_scoped` | needs_sudo; operator waived attempt. |
| `D/protected/tests/backend/test_appendwatch.py::test_cli_shutdown_reconcile_marks_files_from_unwatched_root_interval` | needs_sudo; operator waived attempt. |
| `D/protected/tests/backend/test_pydantic_to_paste.py::test_academic_institution_round_trips_against_real_apis` | real_api marker; operator waived attempt. |
| `D/protected/tests/operator/test_operator_e2e.py::test_existing_aivm_exposes_the_persisted_appendwatch_topology` | Human/operator E2E; operator waived attempt here. |
| `D/protected/tests/operator/test_operator_e2e.py::test_complete_dashboard_backend_codex_commit_and_replay_workflow` | Human/operator E2E; operator waived attempt here. |
| `D/protected/tests/operator/test_operator_e2e.py::test_completed_dashboard_backend_codex_workflow_renders_researcher_card` | Human/operator E2E; operator waived attempt here. |
| `D/tests/control_centre/test_ui_e2e.py::test_completed_grid_row_uses_real_query_ipc` | Attempted during fixture-user run; local `AF_INET` socket creation raised `PermissionError(1)` before production assertion; browser/Lima required. |
| `D/tests/control_centre/test_ui_e2e.py::test_underscore_field_labels_render_literally_in_researcher_card` | macOS browser; waived. |
| `D/tests/control_centre/test_ui_e2e.py::test_main_grid_and_researcher_card_use_compact_line_spacing` | macOS browser; waived. |
| `D/tests/control_centre/test_ui_e2e.py::test_selected_researcher_row_is_highlighted` | macOS browser; waived. |
| `D/tests/control_centre/test_ui_e2e.py::test_researcher_selection_and_run_outcome_history_are_idempotent` | macOS browser; waived. |
| `D/tests/control_centre/test_ui_e2e.py::test_completed_researcher_metadata_is_available_in_visible_run_outcome_history` | macOS browser; waived. |
| `D/tests/control_centre/test_ui_e2e.py::test_displayed_researcher_card_downloads_as_docx` | macOS browser; waived. |
| `D/tests/control_centre/test_ui_e2e.py::test_control_centre_browser_contract` | macOS browser; waived. |

The separately executed `D/tests/control_centre/test_ui_e2e.py::test_completed_query_fixture_has_current_queryable_history` **passed** (`approved-imports-feasible.xml`) and is already counted among the 904, not among the 22. The recovery integration test also passed there but is already included in the final 751. Operator handoff: run `pixi run pre-commit-operator` on Darwin with configured Lima and Chrome. The staged README has two unrelated trailing-space lines (`README.md:102,125`); `git diff --cached --check` fails, though this is not a step in the Pixi operator task. No edit to that human-staged README was authorized within the strict rename scope.
