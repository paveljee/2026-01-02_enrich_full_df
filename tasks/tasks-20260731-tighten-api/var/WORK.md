# Tighten API: reopened — accepted-410 Dashboard finalization regression

## Explicit Backend audit credential and Lifecycle review completed

- Reread the authoritative cached Detour README in full, including the revised
  Lifecycle provisions for independent guest/host OpenAlex credentials,
  Dashboard-owned queue execution, and the shared host-held SSH credential.
- Removed the Backend's silent audit-identity default. The
  `FASTAPI_DETOUR_AIVM_IDENTITY_FILE` setting is now mandatory, and the manual,
  Dashboard, and operator Pixi launch contours each supply the provisioned
  `AIVM_KEY_DIR/id_ed25519` path explicitly.
- Control Centre finalizes a run only after Codex exits. It then refreshes the
  Backend-owned projection once and marks the run complete if that session has
  an accepted attempt; otherwise it marks the run failed. Backend remains alive
  until replaced by a later run or stopped with Control Centre. The one-shot
  refresh leaves a narrow acceptance/finalization race to call out separately.
- Added focused missing-identity coverage. The complete Backend module passed
  (**66 passed, 36 skipped**), and the full unprivileged Detour task passed
  (**154 passed, 49 skipped, 3 deselected**) followed by the expected no-key
  real-API skip. Repository Ruff and mypy over 98 source files, lock
  consistency, TOML parsing, and diff whitespace checks passed.

## Push sequencing and retry guidance completed

- The 2026-09-04 Gaoquan Shi manual run exposed two upstream UX gaps. A push
  submitted after a busy `503` but before a successful retry pull was persisted
  received a misleading `500`; the identical body was accepted after the pull.
  Treat this missing-current-pull state as `409 Conflict`, return
  `Location: /pull`, preserve workflow state, and log the exact operator-only
  reason. Busy remains `409`; missing session or failed state remains `500`.
- The same run reached 30/30 current exact rollout matches while two historical
  retry-contract violations remained. Retry output must state those as separate
  blocking counts, bullet the violations, avoid calling the submission accepted,
  and explain that a near-match correction must preserve prior normalized
  wording and URL. Keep public evidence provenance nonrevealing.
- Implemented the missing-current-pull conflict as an opaque `409` with
  `Location: /pull`, without mutating retry state. A persisted `200` pull then
  supplies the linkage for the identical push to receive `202`. Busy conflicts
  now carry the same polling location; missing-session and failed-state cases
  remain `500`.
- Retry output now separates the current exact-match count from independently
  blocking persisted violations, bullets each violation, and tells the caller
  to restore the prior normalized wording and URL after an over-broad near-item
  correction. The authoritative Lifecycle and OpenAPI response contract match.
- Hermetic regressions cover both production contours, the OpenAPI contract,
  and the preserved `500` cases. Focused tests passed (**6 passed**); the
  complete Backend module passed (**65 passed, 36 skipped**); and the non-root,
  non-operator, non-real-API
  detour suite passed (**153 passed, 45 skipped, 7 deselected**). Ruff and mypy
  passed for all touched Python files; unavailable optional DuckDB extensions,
  historical fixtures, and local sockets account for the environment skips.

## Lifecycle BDD executable-spec scoping in progress

- The authoritative README Lifecycle comprises six normative preamble
  invariants and 30 ordered lifecycle items. There is currently no pytest-bdd
  feature/module; the behavior is distributed across Backend, appendwatch,
  Control Centre unit/browser, and real operator tests.
- Coverage is strongest for Dashboard queue ownership, Backend push/commit/
  validation/replay, appendwatch integrity semantics, Unix-socket Dashboard
  IPC, and the non-interactive real operator happy path. Provisioning is
  strongly checked only when the operator chooses AIVM redeployment.
- Principal additions needed for statement-level coverage are explicit process
  locking, fsync/fatal-validation negatives, the immediate busy `GET /pull ->
  503` contract, push/configuration `500` opacity plus differentiated logs,
  one-profile confinement, Codex configuration (`agents.enabled = false`), and
  traceability for every README clause. Interactive Codex and discretionary
  LLM/Human actions can only be proven as supported/observed boundaries, not
  made deterministic.
- The former Lifecycle conflict around a root-credential `ssh-agent` and
  inherited `SSH_AUTH_SOCK` is reconciled: the documented and implemented
  contract uses one host-held key, pinned identity/known-hosts paths, and
  separate `ai` and restricted `aivm-audit` guest authorizations.
- Proposed shape: one Gherkin feature plus
  `tests/test_detour_ai_augment_bdd.py`, grouped into hermetic contract,
  Linux/root appendwatch, and macOS/AIVM operator scenarios. Reuse production
  entry points and extract/import existing test support rather than calling
  pytest test functions. A Pixi meta-task should run the same module in the
  environments/marker passes already required by `pre-commit-operator`.

## Guest audit principal implementation completed

- Human Operator authorized replacing the stale root-credential `ssh-agent`
  Lifecycle clause with the existing host-pinned AIVM key used through two
  guest authorizations: ordinary `ai` access for operating Codex and a new
  `aivm-audit` principal for Backend reads.
- Keep the private Ed25519 key exclusively at `AIVM_KEY_DIR`; no agent
  forwarding and no private-key copy into AIVM. The `ai` runtime receives only
  the public key and must remain unable to read appendwatch state.
- Preserve `APPENDWATCH_REPORT` in the Lima `--mount` control directory. The
  generic watcher continues to replace reports with mode `0600`; AIVM
  deployment opts into `0640` and an `aivm-audit` group so the report remains
  root-owned and read-only to that principal while `ai` remains denied. The
  source helper lives beside appendwatch under `src/control_centre/appendwatch`;
  its non-secret protected configuration is deployed beside the report in the
  same mounted control directory and selected only by a root-owned fixed
  dispatcher.
- The audit principal is restricted to a forced, root-owned read protocol for
  probing, uniquely locating/streaming rollout JSONL under
  `/home/ai/.codex/sessions`, and streaming the one fixed report; it receives
  no interactive shell, forwarding, write operation, or access to the rest of
  `/home/ai/.codex` (notably authentication material).
- Backend uses the audit principal and same pinned identity for startup
  readability probes, rollout discovery/copy, and exact report-byte capture.
  Control Centre continues to use `ai` for Codex execution and passes guest
  paths to Backend. Provision/deploy verification, hermetic protocol/Backend
  regressions, operator preflight, manual instructions, Pixi `serve`, and the
  authoritative Lifecycle wording moved together.
- `audit-read.json` is generated with mode `0600` beside the report under the
  mounted `.aivm-control/appendwatch` directory. The SSH entry point cannot
  select it: a root-owned dispatcher supplies that exact deployed path to the
  root-only helper.
- Verification passed for shell syntax, Ruff, mypy, the audit protocol,
  Backend/Control Centre regressions, appendwatch mode behavior, the captured
  accepted-push regression, and the complete AI-augment suite (**149 passed,
  49 skipped, 3 deselected**). A real deployment remains intentionally covered
  by the macOS/Lima operator contour.
- Final validation after relocating the configuration passed Ruff, mypy over
  98 source files, shell syntax, and the combined affected regression set
  (**121 passed, 41 skipped**).

## Configured namekey population diagnostics completed

- Backend startup now distinguishes a namekey absent from the complete source
  population from an exact source row that is ineligible. Exact ineligible
  rows report their derived ineligibility category instead of being collapsed
  into the former generic error.
- Exact namekey matching remains mandatory. When an unknown key differs from
  one or more source keys only by leading or trailing whitespace in the parsed
  first/last names, the not-found error offers the sorted full canonical
  namekey(s) as `did you mean` suggestions; it never substitutes one. Case,
  punctuation, internal whitespace, and Unicode remain untouched.
- This addresses the observed draw-120 source identity whose XLSX-derived
  first name is `"Gaoquan "`: supplying `"Gaoquan"` now points the Human
  Operator to the exact trailing-space key rather than calling it ineligible.
- Focused configured-namekey coverage: **11 passed**. Complete unprivileged
  Detour task: **137 passed, 49 skipped, 3 deselected**, followed by the
  expected no-key real-API skip. Repository Ruff and mypy over all 96 source
  files, lock consistency, and diff whitespace checks passed.

## Configured namekey boundary normalization completed

- The main pipeline's canonical JSON string remains the sole internal
  `ktp.namekey` representation for cohort membership, database joins, and
  persistence. Backend startup now parses any equivalent valid JSON supplied
  through `FASTAPI_DETOUR_NAMEKEY` and immediately stores its canonical form,
  instead of requiring the Human Operator to reproduce Python's exact JSON
  whitespace and property order.
- The downstream `load_source_researcher` canonicality check remains as an
  internal invariant. Malformed, incomplete, blank, or control-character input
  remains rejected.
- Focused normalization coverage: **6 passed**. Complete unprivileged Detour
  task: **132 passed, 49 skipped, 3 deselected**, followed by the expected
  no-key real-API skip. Ruff, mypy, and diff whitespace checks passed.

## Current Human Operator evidence (2026-09-03)

- The real macOS/AIVM contour accepted the supplied 292-line Aziz Sheikh
  `Submission`, persisted the push and synthetic commit, projected the final
  output, and served the terminal `GET /pull -> 410 Gone`. The first 410 NDJSON
  line contains the accepted AI values and the optional second line contains
  ground truth.
- Backend private `/query` returned 200 repeatedly. The fresh Playwright page
  showed the accepted AI value and global counts `running 0 · complete 1`, so
  Backend-to-Dashboard database projection worked.
- The operator test failed at
  `row.locator('[col-id="status"]')`: the grid's `status` and `attempt_id`
  columns are far to the right and AG Grid column virtualization leaves them
  absent from the DOM until horizontally scrolled. This is a brittle test
  locator, not evidence that the row or accepted projection was missing.
- The subsequent `Control Centre stopped before the run completed` failure was
  teardown after the Playwright assertion aborted. At that instant the remote
  Codex/local SSH process was still alive, so the Control Centre had not yet
  journaled `CODEX_EXITED`, `PUSH_ACCEPTED`, and `COMPLETE`.

## Additional state-model gap exposed

- Before Codex exits, Backend can already expose an accepted attempt while the
  Dashboard-owned run is still `RUNNING`. `AttemptReconciler` currently sorts
  the later Backend attempt after the live run, causing summary/filter/grid
  status to say `complete` prematurely. This contradicts the intended operator
  contract recorded below: Dashboard completion must follow Codex exit and run
  finalization.
- Consequently, merely replacing the missing-cell locator with another way of
  reading the accepted attempt's `complete` value would preserve a false
  positive. The regression must control Codex exit and distinguish durable
  Backend acceptance/410 from completed Control Centre execution.

## Accepted-410 regression completed

1. Preserved the Human Operator's exact accepted 292-line Aziz Sheikh
   `POST /push` body as a tracked fixture. The captured terminal body contains
   production ground truth and was moved to ignored repository `tmp/`: its
   accepted-values line is reproduced exactly from the push's ten `value`
   fields, while its non-derivable ground-truth line is synthetic in tests.
2. Added an isolated Backend pull/reject/retry/accept/terminal contour using
   that exact push. Backend creates the private synthetic
   `POST http://invalid/commit`; the regression proves record-ID linkage,
   accepted projection, an exact dynamically constructed terminal 410,
   private Dashboard query response, and a nonempty researcher card. No
   external `/commit` is fabricated by the test.
3. Added controlled Control Centre coverage proving that durable Backend
   acceptance does not make a Dashboard-owned run complete while Codex is
   still alive. Reconciliation now keeps that run `running` until Codex exits,
   after which the journal ends `CODEX_EXITED`, `PUSH_ACCEPTED`, `COMPLETE` and
   the accepted Backend attempt becomes visible.
4. Added hermetic browser coverage for the stable, visible attempt-history and
   card controls. The real operator test now reads completion and accepted
   attempt ID there instead of depending on AG Grid's virtualized off-screen
   `status` and `attempt_id` cells.
5. The Human Operator's real contour remains the final macOS/Lima confirmation;
   it was not rerun in this Linux execution environment.

## Verification and disposition

- Focused accepted-push and reconciliation regressions: **2 passed**.
- Complete Backend module: **49 passed, 36 skipped**; complete Control Centre
  unit module: **13 passed**.
- Complete unprivileged Detour task: **126 passed, 49 skipped, 3 deselected**;
  the separate real-API check skipped because `OPENALEX_API_KEY` is unavailable.
  Browser tests that require local sockets also skip in this restricted
  environment.
- Repository Ruff and mypy checks passed over all 96 source files; diff
  whitespace checks passed.
- The full standard `pixi run pre-commit` was attempted. Its root-test stage
  stopped at **102 passed, 34 failed, 4 skipped** because this environment could
  neither download nor load the configured DuckDB `splink_udfs`/`httpfs`
  extensions. The HTTP request-log tests all passed, and the complete Detour
  task was run separately and passed as recorded above.

## Visible operator Codex-auth prompt completed

- Production macOS operator feedback showed Codex auth status correctly
  returned unavailable, then pytest hid the non-newline `input(prompt)` text
  while waiting indefinitely for the Human Operator; the prompt appeared only
  when Ctrl+C unwound capture.
- The auth question now goes through the existing newline-terminated, flushed
  operator-log path before bare stdin is read. Hermetic preflight coverage
  requires the question to be emitted before input is consumed.
- Verification: focused auth tests **3 passed**; complete unprivileged Detour
  task **124 passed, 48 skipped, 3 deselected**, followed by the expected
  no-key real-API skip; official Ruff/mypy over 96 files and diff whitespace
  checks passed.

## Operator-topology preflight deduplication completed

- The standalone topology test proves more than the shared preflight (it
  resolves the deployed Lima mount/report and requires a readable, nonempty
  report), but the completed workflow necessarily exercises this contour again
  through Backend startup, commit capture, and appendwatch validation.
- The standalone topology diagnostic is now `excluded_from_suites`. Its report
  resolution/readability assertions live in one helper invoked first by both
  downstream workflow tests, preserving fail-fast behavior without a second
  default operator test or AIVM redeploy.
- Marker audit selects exactly the two standalone excluded diagnostics and
  exactly one default operator completion test. Hermetic auth preflight tests
  **3 passed**; complete unprivileged Detour task **124 passed, 48 skipped, 3
  deselected**, followed by the expected no-key real-API skip; official
  Ruff/mypy over 96 files and diff whitespace checks passed.

## Pytest-root path cleanup completed

- Removed every numeric `Path(__file__).parents[...]` traversal from the Detour
  tests. Session fixtures now expose `repository_root` from
  `pytestconfig.rootpath` and its derived `detour_root`.
- Root-dependent helpers and subprocess launchers receive the resolved root
  explicitly. Backend's numerous fixture paths are grouped in a typed
  `BackendTestPaths` fixture; appendwatch resolves its importable module when
  no explicit script environment variable is supplied.
- The standalone browser server remains root-independent; only its test
  launcher receives the repository root as subprocess `cwd`.
- Verification: all **175 tests collected**; focused shared-root/preflight/
  appendwatch checks **5 passed**; complete unprivileged Detour task **124
  passed, 48 skipped, 3 deselected**, followed by the expected no-key real-API
  skip; the sudo-marker contour selected exactly three tests and skipped them
  without root. Official Ruff/mypy over 96 files, `pixi lock --check`, diff
  whitespace, and removal-of-parent-traversal audits passed.

## Nested Detour test tree reviewed and adapted

- Preserved the Human Operator's readability split into `backend/`,
  `control_centre/`, and `operator/` test directories.
- Updated every moved test's repository/detour-root derivation, the Control
  Centre browser-test subprocess module, and the two hard-coded Pixi task node
  paths for the Backend real-API and operator contours.
- Replaced `item.keywords`/`request.node.keywords` marker detection with actual
  `get_closest_marker()` checks. This is required because the `operator/`
  directory name itself appears in pytest keywords; it had caused the three
  unmarked hermetic operator-preflight tests to be skipped and treated as real
  operator tests.
- Verification: all **175 tests collected**; default preflight selection **3
  passed**; `-m operator --no-redeploy --collect-only` selected exactly the
  three real E2Es and deselected the three hermetic preflight tests; complete
  unprivileged Detour task **124 passed, 48 skipped, 3 deselected**, followed by
  the expected no-key real-API skip; Ruff/mypy over 96 files, lock consistency,
  import/root assertions, and diff whitespace checks passed.

## UUIDv7, IPC naming, and operator Codex authentication completed

- Control Centre queue/run identifiers now use stdlib `uuid7()` instead of
  `uuid4()`; focused coverage requires the produced run ID to be UUID version 7.
- Renamed Backend `dashboard_ipc.py` to `ipc.py`, renamed its corresponding
  test module to `test_ipc.py`, and updated Backend/test imports without changing
  the IPC implementation.
- Added a `requires_codex_auth` marker only to the two operator workflow tests.
  Their AIVM preflight now runs guest `codex login status`; an existing login is
  reused, while a missing login prompts the Human Operator to run live
  `codex login --device-auth` as the `ai` user and verifies status again before
  allowing the expensive E2E to start. The topology-only test remains
  independent of Codex authentication.
- Added hermetic preflight tests for existing authentication, successful
  prompted device authentication plus recheck, and refused authentication
  failing fast.
- Verification: focused tests **7 passed, 1 skipped**; complete unprivileged
  Detour task **124 passed, 48 skipped, 3 deselected**, followed by the expected
  no-key real-API skip; Ruff and mypy over 96 files, `pixi lock --check`, and
  diff whitespace checks passed. The real device-auth/operator contour remains
  for the Human Operator's macOS/AIVM run.

## Operator completion contour completed

- The operator Pixi task now passes the repository `.env` OpenAlex key into
  pytest for host-side AIVM redeployment. Runtime preflight still independently
  reads and verifies the provisioned guest key.
- README Workflow re-audit confirms that a persisted terminal `GET /pull ->
  410 Gone` is not the final runtime boundary: the rollout continues until the
  AI Agent Runtime actually encounters that response and stops.
- Preserved the existing full-workflow test as `excluded_from_suites`; it
  is skipped by default and can be selected explicitly with its node ID plus
  `-m operator --run-excluded-from-suites`.
- Added the default completion contour. It reuses the checkpoint's complete
  queue/pull/push/commit/replay and artifact assertions, then waits for the
  Control Centre grid to project `complete`, which follows Codex process exit.
- A fresh Playwright session verifies the accepted attempt ID, attempt history,
  rerun action, enabled card action, and nonempty rendered researcher card. The
  test emits the full visible card text captured from the DOM between explicit
  delimiters and reports queue-to-final-Playwright elapsed time.
- Extended hermetic Control Centre coverage to require `CODEX_EXITED` directly
  before `COMPLETE` and verify the projected exit code/final status.
- Verification: targeted Control Centre modules **12 passed, 5 skipped**;
  full unprivileged Detour task **121 passed, 48 skipped, 3 deselected** with
  the expected no-key real-API skip; Ruff and mypy over 95 files, `pixi lock
  --check`, and cached/uncached diff whitespace checks passed. The production
  macOS/AIVM completion contour remains for the Human Operator to execute.

## Operator shutdown observability completed

- Clarify and expose both shutdown layers: Control Centre's graceful ownership
  of Backend and the active recorded Codex run, followed by the operator
  harness's host-descendant fallback cleanup.
- Add PID/role/command logs for the Control Centre and every snapshotted local
  descendant, plus run/session/local-SSH/remote-PID logs for Codex cancellation.
- Preserve the fact that Lima/AIVM is not stopped and Playwright is closed by a
  separate browser-finally path.
- Added an exact unit test for recorded remote-Codex/local-SSH cancellation
  logs. Control Centre tests **12 passed**; full non-root detour task **121
  passed, 47 skipped, 3 deselected**, followed by the expected real-API skip;
  Ruff and mypy over 95 files passed.

## Latest operator E2E failure resolved

- The macOS operator contour now starts Backend and its short Unix socket, but
  every readiness `GET /pull` returns 500 with an incomplete-ASGI-response log.
- Root cause: `AuthoritativeHttpMiddleware` replayed the consumed request once,
  then fabricated `http.disconnect`. Starlette `StreamingResponse` interpreted
  that as a real client disconnect and canceled `/pull` before its final body
  frame.
- Patched request replay to delegate to the original ASGI `receive` after the
  buffered body. Added an exact streaming-response regression test.
- Split readiness into a retrying OpenAPI-startup phase followed by definitive
  pull and Unix-IPC probes. Once Uvicorn is up, a pull/IPC failure now fails
  immediately instead of generating hundreds of retries for 30 seconds.
- Operator replay progress now reports response-shape transitions and periodic
  heartbeats, suppressing runs of identical record-count messages.
- Added upstream coverage for both the streaming response and immediate
  post-startup pull failure behavior.
- Verification passed: focused regressions **2 passed**; complete Backend and
  Control Centre modules **59 passed, 36 skipped**; full non-root detour task
  **120 passed, 47 skipped, 3 deselected**, followed by the expected real-API
  skip because `OPENALEX_API_KEY` is unavailable; Ruff and mypy over 95 files,
  `pixi lock --check`, and cached-diff whitespace checks all passed. The real
  macOS/AIVM operator contour remains for the Human Operator to rerun.

## Objective and disposition

Aligned `src/detours/detour_ai_augment/src` and its tests with the latest
authoritative README. The post-pull re-audit reopened TASK because Backend did
not synchronize replay before every detour-DuckDB access and Dashboard DB reads
used a hidden token-authenticated FastAPI route instead of the required
host-private Flask/Unix-socket IPC. Both gaps are resolved.

## Completed implementation

- Backend owns one persistent detour-DuckDB connection. Startup, replay append,
  projected-outcome reads and Dashboard reads all pass through one locked
  synchronization boundary that projects every unprojected replay record in
  append order. Synchronization/recording failures fail Backend loudly.
- Removed hidden `GET /_control/pull`, its bearer-style token and Backend-owned
  Dashboard event models. Public FastAPI exposes only `/pull` and `/push`.
- Added a separate Flask query application served on a mode-0600 Unix-domain
  socket. Query failure calls `os._exit(1)`; startup/shutdown clean up the
  server, socket, persistent DB connection and replay lock.
- Dashboard uses an unauthenticated AF_UNIX HTTP client for Backend-owned
  SELECT results. Backend readiness now proves both public pull and private
  database IPC. Dashboard queue/run events remain NiceGUI-storage-only models.
- Added Flask 3.1.2 to the detour feature and refreshed `pixi.lock` (Flask,
  Werkzeug and Blinker present; `pixi lock --check` passes).
- Kept the default web-search-language factory inline, with an explicit
  `cast(list[TargetWebSearchQueryLanguage], ...)` to satisfy invariant-list
  typing without an extra named helper.
- The operator contour uses a per-run socket and asserts socket type, 0600 mode
  and shutdown cleanup on the production host.
- Corrected the Control Centre repository-root parent index so its supervised
  Backend starts from the repository and can import the `src` package on the
  production macOS contour.
- Operator AIVM reachability, guest-key and appendwatch probes now have
  ten-second bounds and streamed preflight status. The full-workflow contour
  emits step/heartbeat/record-count progress and fails immediately when the
  Control Centre records a failed run.
- Operator teardown isolates the Control Centre from the terminal's Ctrl+C,
  then stops it explicitly, reaps surviving local descendants, verifies both
  service ports were released, and closes Playwright in a `finally` block.
- Operator dashboard IPC now uses a unique short mode-0700 directory beneath
  `/tmp`, keeping its socket address below Darwin's AF_UNIX path capacity while
  preserving the normal-shutdown socket-removal assertion and failure/Ctrl+C
  cleanup.
- Registered `needs_sudo` in the detour conftest and applied it only to the
  three real appendwatch EACCES tests. The existing root task runs every test
  carrying that marker from the whole detour test directory; a sibling task
  runs the remaining aggregate suite and real-API contour unprivileged.
- Rechecked the full synthetic commit contract. `coerce_schema_v1` is an input
  migration flag and is always excluded from serialization after validation,
  exactly matching README; schema 1 (`1` and `"1"`) and explicit v1 coercion
  remain intact.
- Schema 1.1 now permits nullable `response_headers` and `duration_usec`. The
  unsent synthetic commit serializes both as null, completed public exchanges
  still require both values, and schema 1 preserves its non-null contract.
- Rechecked outcome classification: Pydantic and evidence-against-rollout
  failures produce Markdown retry; rollout-index/integrity and appendwatch
  failures remain opaque 500s.
- Preserved human-signed comments and user staging. No stage/unstage command
  was used; no main-pipeline behavior outside the HTTP schema contract changed.

## Added regression coverage

- Persistent connection identity and synchronization of newly appended replay
  before every Dashboard SELECT.
- Absence of Dashboard query and `/_control` from public FastAPI.
- Unauthenticated AF_UNIX Dashboard request.
- Separate Flask app response, fatal query failure, real UDS round trip/mode/
  cleanup, and refusal to overwrite a non-socket path.
- Exact synthetic commit JSON contour and schema-1.1 serialization.
- Explicit no-flag v1/v1.1 round trips and consumed coercion-flag round trip.
- Native v1.1 null response-metadata round trips and v1 rejection for both
  legacy schema-version spellings, with and without requested coercion.
- Evidence Markdown versus rollout-index/appendwatch 500 classification.
- Operator production-host Unix-socket assertions.
- Exact three-test `needs_sudo` selection and unprivileged aggregate-suite
  exclusion.
- Dashboard repository-root resolution and failed-run log emission used by the
  operator fail-fast contour.

## Verification

- `pixi run -e detour-ai-augment lint`: passed (Ruff; mypy over 95 files).
- Flask IPC module: **3 passed, 1 skipped**. Only the real bind round trip is
  skipped because this managed Linux sandbox denies AF_UNIX `bind(2)` with
  `EPERM`; Flask behavior and failure handling pass hermetically, while the
  operator test retains the real production-host round trip/assertions.
- Complete non-root detour suite excluding `needs_sudo`: **116 passed, 47
  skipped, 3 deselected**; the isolated marker contour selected exactly three
  tests and skipped them without root.
- Explicit detour real-API test: skipped because `OPENALEX_API_KEY` is absent.
- `pixi lock --check`: passed.
- `git diff --check`: passed.
- Final schema refinements: HTTP schema tests **28 passed**; Backend API tests
  **47 passed, 36 skipped**; complete detour suite **116 passed, 50 skipped**;
  lint passed again.
- Sudo-task split: `pixi lock --check`, Pixi task-graph dry run, Ruff and mypy
  over 95 files all passed.
- Operator hardening: complete non-root detour task **118 passed, 47 skipped,
  3 deselected**; its explicit real-API follow-up skipped because the key is
  absent. Repo-wide Ruff and mypy passed. In the managed Linux environment,
  the operator entry point reported missing `limactl` during preflight before
  entering the first test; the full production contour remains host-only.

The official `pixi run -e detour-ai-augment pre-commit` was invoked but Pixi
still cannot resolve cross-feature task `test-detour-mode0-econ-stats` from the
AI-augment environment. Its contour was therefore executed manually:

- repo lint: passed;
- main tests: **100 passed, 4 skipped, 34 failed**; failures require unavailable
  network/`splink_udfs`, except one host-only `/Volumes/...` fixture;
- main real-API contour: **1 skipped, 137 deselected** (API key absent);
- mode-3 detour: **6 passed**;
- step-4 detour: **4 failed, 1 skipped**, all from unavailable `splink_udfs`;
- mode-0 detour: **2 passed, 2 failed**, both because managed sandboxing blocks
  Kaleido/Chromium `shutdown(2)`;
- the root marker contour cannot enter `sudo` under the container's
  no-new-privileges flag; its exact three-test selection is verified, and the
  remaining aggregate suite passed unprivileged as above.

These are task-graph/execution-environment limitations, not failures in the
AI-augment implementation. TASK is complete pending the normal human-operated
operator E2E on its provisioned macOS/AIVM environment.
