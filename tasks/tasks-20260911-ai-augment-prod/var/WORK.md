# AI augment production-preparation workbook

## Handoff reading order

For current work, read `TASK.md`, then **Hard constraints**, **Current state**,
**Current authorized implementation contract (2026-09-14)**, and its
**Current handoff status** below. The agreed contract is preserved verbatim.
All explicitly labelled historical sections record prior investigation only;
they grant no authority for further changes.

## Objective

Work with the Human Operator to prepare the AI-augmentation detour for
production, using its `README.md` lifecycle as the authoritative contract.
Current concrete issue: hand off the partially completed, narrowly authorized
Backend-store/CAS/runtime-composition and IPC-query ownership refactor. Before
more implementation, the next executor must resolve with the Human Operator
the newly identified projection-boundary problem described under **Current
handoff status**; no redesign has yet been authorized.

## Hard constraints

- Run commands through `pixi run -e detour-ai-augment`.
- Never run or import `src.repl`; inspect its implementation only.
- Treat `data/scisci_process.duckdb` as the sole data source and open it only
  read-only. Do not inspect other files under `data/` or `.aicode/`.
- Git is read-only: never stage or unstage.
- Preserve every inline comment signed off by a human.
- Detour remains isolated: no `src/cli.py` edits, no cross-detour imports, and
  no use of another detour/main CLI database.

## Current state

- `TASK.md` was reread in full on 2026-09-14. Never run or import `src.repl`.
- The worktree is intentionally dirty and contains both staged and unstaged
  changes from the ongoing collaboration. Git remains read-only: do not stage,
  unstage, reset, restore, or infer authorship from index state. In particular,
  `ai_augment_backend_store.py` is currently untracked, and several core files
  show `MM`.
- The exact active authorization is the seven-part contract below. It permits
  completion and direct test adaptation only within that boundary. Broader
  Dashboard storage/probe/lifecycle ideas are analysis only. Protected BDD is
  excluded and must not be edited; a staged BDD diff already exists and must be
  preserved unless the Human Operator gives new direction.
- The authorized implementation is substantially present: protected replay-log
  and detour-DB resource models, unprotected Backend store and CAS models,
  server-owned runtime construction, protected IPC request handling, the
  singular-outerdict rename, and shared `FrozenStrictModel` adoption.
- The implementation is not ready for acceptance. The Human Operator identified
  that `api.lifespan()` injects a runtime-closing `project_record` callback into
  the store, and that `_project_readme_record` is stale in name and abstraction;
  it handles generic HTTP records and does not transparently project through
  the Codex record contract. The last design proposal was discussion only and
  was not approved.
- Current verification has two known code/test blockers plus one hygiene
  blocker: duplicate same-named replay-hash tests cause mypy/Ruff failure; the
  byte-identical DuckDB test replays successfully but produces different file
  hashes; a UI timeout test requires `< 1` while the protected constant is `1`;
  and `git diff --check` reports trailing whitespace in the newly added
  `FrozenStrictModel` docstring. Do not alter these outside authorization.
- Latest local focused results: 12 Backend/IPC tests passed with one Unix-socket
  policy skip, and five directly affected UI tests passed. The broader hermetic
  run excluding the replay-hash test produced 259 passed, 12 skipped, five
  deselected, and one failure (the timeout assertion). Full strict detour mypy
  reports only the duplicate replay-test definition.
- The Human Operator previously reported `pixi run elevate` at 10/10, but that
  predates the latest store/projection edits and must not be treated as final
  validation. This environment cannot exercise its Unix-socket cases because
  of the execution profile.

## Historical record

The dated material from **Detour baseline** through the active contract records
completed investigation and earlier decisions. It is retained for provenance,
not as current status or authorization. Where an old status conflicts with the
current state or active contract, the current sections control.

## Detour baseline

- Production composition: `backend.server` acquires the single-process lock,
  runs either full FastAPI + Flask IPC or IPC-only Flask, and constructs the
  shared `AiAugmentDetourConfig`/context. Full startup proves remote audit
  readability, synchronizes replay projection, and starts stdin session-ID
  handoff before serving.
- Public `/pull` and `/push` exchanges are buffered by authoritative middleware,
  validated as schema 1.1 UUIDv7 records, appended + fsynced before response,
  projected transactionally, and followed by asynchronous accepted-push commit
  work. Projection validates links, CAS bytes/hash/line count, appendwatch,
  submission schema, rollout evidence, retry obligations, and accepted output.
- Flask IPC owns `/query` and run-outcome snapshot routes over a mode-0600 Unix
  socket. The Control Centre never opens the writable detour DB; full mode uses
  the Backend's one connection and synchronization, IPC-only opens it read-only.
- Dashboard source data is validated/cached from the main DB, while run queue
  and journal are NiceGUI-owned. The supervisor starts Backend before Codex,
  hands the discovered session UUID to Backend stdin, records completed/failed/
  cancelled outcome before process teardown, and cleans up owned processes on
  shutdown and failures.
- Protected operator harness creates isolated replay/CAS/detour outputs while
  symlinking the authorized main DB read-only; it hashes production data before
  and after. The suite checks deployed appendwatch topology, drives dashboard
  queueing through Playwright/Codex to terminal 410, validates replay/CAS/IPC
  ordering and integrity, and verifies the rendered researcher card.
- Current `HEAD` is `46dae82`, including the completed private-header and
  protected deployment-path patches. The worktree was clean before recording
  the current test investigation.

## Current operator request — historical refactor assessment

Compare the current AI-augment detour codebase with its state on September 7,
2026, immediately before the deep refactor. Deliver an objective account of
changes plus an engineering assessment. Determine the historical boundary from
Git commit timestamps/content rather than assuming a revision. Review production
code, tests, configuration/tasks, and authoritative lifecycle documentation;
quantify and categorize the diff, trace major architectural behavior changes,
and distinguish evidence from judgment. Git remains read-only.

### Assessment plan

1. Identify and justify the September 7 pre-refactor baseline commit.
2. Quantify changed files/lines and group changes by subsystem.
3. Compare architecture, persistence, lifecycle, API, dashboard, and tests.
4. Inspect commit sequence to separate refactor intent from incidental changes.
5. Report benefits, costs, risks, and production-readiness implications.

### Historical boundary

- Baseline: `5bb8db96c8a0738b5e068720a5ccd38b370d7723`, authored/committed
  2026-09-07 08:26:51 UTC, “detour ai augment ipc: open detour db readonly”.
  It is both the last first-parent commit on September 7 and the result of
  `git rev-list -1 --before=2026-09-08T00:00:00Z HEAD`.
- Refactor starts at its child `44447cc` on 2026-09-08 13:28:13 -04:00,
  “detour ai augment: add acme and architecture protocols”, followed by the
  explicitly breaking `cfbd739` and the large protocol/context/lifecycle/test
  sequence through `83f7033` on September 11.
- Comparison target is `5bb8db9..HEAD`; unrelated task/config commits after
  `83f7033` will be identified separately rather than attributed to the detour
  refactor.

### Quantified scope and evidence

- Whole-tree `5bb8db9..HEAD`: 79 files, 11,339 insertions, 7,380 deletions,
  including unrelated post-refactor bookkeeping. Refactor-relevant scope
  through `83f7033` has 64 changed files and 10,468 insertions / 5,807
  deletions: 13 added, 17 modified, 4 deleted, and 30 renamed; 16 renames are
  byte-identical moves. The 20
  first-parent refactor commits run from `44447cc` through `83f7033`; later
  commits are task/config bookkeeping rather than AI-augment implementation.
- Detour source grew from 28 Python/shell files and 17,011 lines to 35 files
  and 19,807 lines (+2,796, about 16%). Tests grew from 11 Python files / 11,704
  lines / 186 named tests to 13 / 13,456 / 199 (+13 named tests).
- Major new structure: a 649-line Acme-inspired Protocol architecture, a
  shared `@implements` static structural checker, a mirrored `protected/`
  subtree, typed context/configuration models, outerdict/commit/query/outcome
  models, a run-outcome control module, a standalone Backend server composer,
  and a protected pytest/operator plugin. Strict mypy and third-party stubs
  were enabled globally.
- A meaningful portion is relocation: deployment, appendwatch, inference
  samples, submission models, and operator assets moved under `protected/`.
  The substantive work centralizes duplicated Backend/dashboard source models
  and lifecycles, uses typed `NameKey`/UUID/path values, and makes Backend
  context own a validated immutable source-population representation.
- Public `/pull` and `/push` semantics remain largely intact. Startup is now
  composed in `backend.server`; FastAPI domain lifespan and Flask IPC are
  separated, with full and IPC-only modes sharing the same entry point.
- Durable/API breaking changes: `/commit` now nests an explicit Codex session,
  rollout, and appendwatch record; accepted output stores commit ID plus the
  exact commit request instead of an attempt ID; projected validation rows were
  replaced by complete agent-runtime attempt records; and `/query` returns full
  attempts/outerdicts/run outcomes rather than flattened accepted-attempt/card
  DTOs. No legacy parser or schema migration was found.
- New `/completed`, `/failed`, and `/cancelled` IPC exchanges capture a fresh
  rollout CAS snapshot and appendwatch report before teardown, append the full
  exchange to the replay log, return 200 for complete capture or 500 for a
  logged partial capture, and remain archival during replay.
- Resource integrity was tightened: both release-map and replay-log configured
  hashes are enforced. This corrects the old behavior that effectively trusted
  the replay log's current hash, but makes hash rollover for that mutable log an
  explicit operational responsibility.
- Test additions cover run-outcome persistence/partial capture/display,
  composition boundaries, strict commit round trips, replay-hash enforcement,
  provenance, and cancellation timing. Prior handoff reports 205 passed, 47
  skipped, and 3 root-only deselected; root and real operator contours remain
  Human Operator-run and are not newly executed for this read-only assessment.
- The BDD layer is a known deferred exception, not part of that standard-suite
  result. The old feature file was deleted and the BDD test moved under
  `protected/`, while its imports, feature lookup, support imports, and Pixi
  tasks still use pre-refactor paths. A direct collection check now fails with
  `ModuleNotFoundError` for the removed `backend.helpers.data_models.server_event`.
  The prior handoff explicitly records this stale BDD wiring as outside its
  scope with WIP in a Git stash.

### Emerging assessment

- Benefits: materially stronger ownership, type-level contracts, source-data
  invariants, identity/provenance, lifecycle auditability, shutdown capture,
  and production-oriented E2E isolation.
- Costs/risks: a hard persisted-format compatibility boundary; roughly 16%
  source growth and substantial protocol ceremony; still-large `api.py` and
  `ui.py`; social rather than technical enforcement of `protected/`; a mutable
  replay-log hash runbook requirement; currently broken/deferred BDD
  traceability; and residual integration risk from a three-day sequence of
  WIP/breaking commits before root/real operator tests are run.
- Production decision required: treat this as a fresh storage/replay epoch or
  provide an explicit migration. Do not deploy it as a drop-in reader of the
  September 7 DB/replay state.

## Next actions

1. [done] Establish the exact September 7 baseline and refactor commit range.
2. [done] Quantify and classify source/test/file changes.
3. [done] Trace architecture, lifecycle, persistence, and API behavior changes.
4. [done] Verify compatibility findings and synthesize the objective report.

## Assessment conclusion

The current design is materially more production-defensible than the September
7 design for a fresh storage epoch: it represents component ownership and
connector contracts explicitly, removes duplicated domain projections, records
commit provenance losslessly, and captures terminal run evidence before
teardown. The September 7 implementation already had the important public
pull/push, replay-first, CAS, appendwatch, retry, and post-validation safety
properties; the refactor strengthens and organizes them rather than replacing a
weak prototype wholesale.

Production should nevertheless be gated on (1) an explicit fresh-epoch versus
migration decision for replay/DB state, ideally with a versioned commit payload;
(2) a documented or automated replay-log hash rollover procedure; (3) repair or
formal retirement of the stale BDD traceability suite; and (4) the outstanding
root appendwatch, real operator, full/IPC-only, and dashboard smoke contours.
Avoid another broad architectural rewrite before those gates: use their concrete
failures to drive smaller changes.

## Current operator request — repository LOC

Counted current tracked first-party Python and shell code under `src/` and
`tests/`, excluding documentation, configuration, data, assets, notebooks,
task/chat history, and vendored `src/github.com` code. Tests are classified by
test directory/name; notably AI-augment `sample_deploy/test_proxy.py` is test
code despite residing under a source subtree. Physical LOC is `wc -l`;
"code-like" LOC excludes blank and full-line `#` comment lines but retains
docstrings and inline comments.

| Component | Prod physical/code-like | Test physical/code-like | Combined physical/code-like |
|---|---:|---:|---:|
| Main pipeline | 10,916 / 9,859 | 5,894 / 5,256 | 16,810 / 15,115 |
| `detour_ai_augment` | 18,806 / 16,702 | 14,457 / 12,685 | 33,263 / 29,387 |
| `detour_mode0_econ_stats` | 2,413 / 2,229 | 1,212 / 1,152 | 3,625 / 3,381 |
| `detour_mode3_pgf_stats` | 979 / 901 | 573 / 510 | 1,552 / 1,411 |
| `detour_step4_breakdown` | 333 / 281 | 672 / 564 | 1,005 / 845 |
| Shared detour package initializer | 3 / 2 | 0 / 0 | 3 / 2 |
| **Total** | **33,450 / 29,974** | **22,808 / 20,167** | **56,258 / 50,141** |

## Current operator request — forward-compatible private headers

Implement a surgical AI-augment change requested by the
`[!NOTE]` in `tasks/tasks-20260810-outerdict-mask/src/TASK.md`:

- `Name-Key` -> `NameKey`, retaining the canonical value
  `ktp.first_name="...", ktp.last_name="..."`.
- `Source-Key` -> `SourceKey`, changing the single-rollout value to
  `ktp.filename="...", ktp.fragment;type="line_number";line_number="..."`.

### Findings and recommendation

- Agree with doing this now. These are private synthetic `/commit` request
  headers and Unix-socket run-outcome request/response headers, not public
  `/pull` or `/push`; no production replay epoch has started, so compatibility
  risk is low and this avoids persisting the soon-obsolete source-key grammar.
- Behavioral production changes can remain concentrated in
  `commit_event.py` and `run_outcome.py`: header constants and canonical
  source-key formatting/parsing. Existing imports propagate them through API,
  IPC, run-outcome response, query/outerdict validation, and dashboard.
- Update the authoritative README, protected operator instructions, locale
  wording, and exact-shape tests/fixtures. The new shape is the sole
  authoritative definition: production code, docs, and tests must contain no
  fallback, compatibility branch, legacy terminology, or regression fixture
  memorializing the superseded spelling.
- Keep this patch limited to AI augment's one filename plus `line_number`
  fragment. Do not prematurely implement the upcoming task's general
  multi-filename `SourceKey`, source resolution, or main-pipeline
  `ktp.fragment` migration. The future shared model must decide tuple ordering,
  duplicate handling, resource resolution, and fragment value typing.
- Add focused tests for exact commit and run-outcome exchanges, round trips,
  malformed/noncanonical fragments, filename basename validation, and
  case-insensitive inbound HTTP field-name handling. Then run the non-BDD suite;
  BDD remains the separately documented stale contour.
- This is another durable replay-shape break under HTTP record schema `1.1`.
  It is acceptable before production, but should be finalized before the first
  durable run; later changes would require versioning or migration.
- Human clarified that RFC 8941 is obsolete in favor of RFC 9651. The pointed
  `tmp/rfc-9651.md` currently exists but is empty (0 bytes and untracked), so no
  local text could be cited. Under RFC 9651 semantics, the proposed examples
  are Structured Fields Dictionaries: scalar `ktp.filename` is a String,
  plural filenames form an Inner List, and bare `ktp.fragment` has `type` plus
  fragment-value Parameters. The key dots/underscores and shown spacing are
  compatible with that grammar.
- RFC 9651 plain Strings are visible ASCII. A read-only query of the sole source
  DB confirms all 307 current first/last-name pairs contain only visible ASCII,
  so this does not raise current-cohort risk. A future general shared model must
  explicitly support RFC 9651 Display Strings for Unicode or reject unsupported
  values; it should not rely on JSON-only escapes while claiming Structured
  Fields conformance.

### Replay/projection effect of a header-only patch

- Authoritative replay record classes are initial/retry/terminal `GET /pull`,
  `POST /push`, synthetic `POST /commit`, and IPC `POST
  /completed|/failed|/cancelled`. After the proposed patch, the old source-key
  grammar and `ktp.fragment_type` disappear from commit and outcome headers.
- `ktp.fragment_type` remains in the initial 200 pull response because
  `configured_pull_lines()` serializes existing XLSX and SSN innerdicts. Push
  bodies, commit bodies, retry markdown, terminal 410 normalized submission +
  selected DOCX ground truth, and run-outcome bodies do not add that field.
- Current replay logic does not interpret the pull's source-key fields when
  validating a commit: `_namekey_from_original_pull()` extracts only first and
  last name. The new header parser can still return `(filename, line_count)`,
  which is the only interface consumed by rollout and appendwatch validation.
  Therefore the mixed interim representations do not break current behavior.
- The replayed detour DB will still contain `ktp.fragment_type` in rebuildable
  projections: raw `detour_http_records` mirrors the initial pull; serialized
  agent-runtime attempts embed their pull and, for applicable cohorts, a full
  ground-truth innerdict; and `codex_output_rows` explicitly writes a
  `ktp.fragment_type = line_number` column which flows to `codex_output` and
  `codex_innerdicts`. This is independent of commit-header parsing.
- This does not defeat the forward-looking goal. The authoritative fact needed
  to recreate accepted AI output is the new commit `SourceKey` plus commit body,
  rollout, push, and source context. A later main-pipeline migration can change
  the output schema/materialization and rebuild the disposable detour DB. The
  immutable old pull payload will remain historical raw input; future replay
  code must continue treating it as opaque except for identity, or explicitly
  normalize it if it starts validating every historical innerdict.

### RFC 9651 confirmation

- The local RFC is now populated (1,686 lines) and confirms that RFC 9651
  obsoletes RFC 8941. Both headers must be defined as whole Dictionary
  Structured Fields; parsing must fail as a unit, with field-specific semantic
  constraints applied after generic parsing.
- The proposed serialization follows RFC 9651's recommended form: ordered
  dictionary members use `, `; a Boolean-true dictionary member omits `=?1`
  and carries `;` parameters; lowercase keys may contain digits, `_`, `-`, `.`,
  and `*`; an Inner List uses parentheses and space-delimited items; and String
  escaping is limited to DQUOTE and backslash.
- Implementation scope contains no historical-format recognition or rejection
  test. Strictness means parsing the complete new Dictionary shape, validating
  exact required member/value/parameter types and semantics, and accepting only
  the chosen canonical serialization for this private authoritative record.

### Implementation status

- Core patch is implemented in the existing commit/run-outcome header models.
  Header field names are now `NameKey` and `SourceKey`; the source value is the
  exact canonical scalar-filename plus parameterized `line_number` Dictionary.
- Serialization/parsing now uses RFC 9651 String escaping: only DQUOTE and
  backslash are escaped, and values outside visible ASCII fail. Parsers consume
  the full selected canonical serialization, enforce basename and positive
  decimal line-count semantics, and do not contain compatibility logic.
- Shared main-pipeline `SourceKey`, pull payloads, output projection, database
  schema, public API bodies, and replay schema version are unchanged.
- Updated the authoritative lifecycle README, protected operator curl command,
  locale text, exact synthetic commit fixture, and dashboard commit fixture.
- Added exact `NameKey` and `SourceKey` round trips (including RFC String
  escaping) plus strict malformed/noncanonical tests written only against the
  authoritative new grammar.
- Focused verification is green: Ruff checks pass; selected Backend header,
  synthetic-commit, and run-outcome tests report 13 passed / 112 deselected;
  Backend IPC tests report 7 passed / 1 skipped; full dashboard UI tests report
  46 passed.
- Focused strict mypy traversed unchanged main-pipeline dependencies and found
  five existing errors in `jsonlines.py`, `sourcekey.py`, `duckdb_utils.py`, and
  `pipeline_manager.py`; it reported none in the three changed production
  modules themselves. Ruff reports all changed Python files clean.
- The Human Operator emphasized the future multi-file contour. RFC 9651
  confirms that a Dictionary value containing filenames is an Inner List whose
  serialized Strings are space-delimited inside parentheses. Read-only queries
  against the main DB confirm current SSN/parquet innerdicts encode an ordered
  JSON-text list of nine filenames and use an `author_id` fragment. The future
  HTTP conversion must serialize those as
  `ktp.filename=("file1.parquet" "file2.parquet")`, never as a quoted JSON
  array. The present AI-augment parser remains intentionally scalar because a
  Codex rollout snapshot has exactly one source filename; the String helper can
  serialize each future Inner List member.
- Standard non-BDD AI-augment suite is green: 215 passed, 47 skipped, and 3
  root-only tests deselected; the separately selected real-API test skipped
  because `OPENALEX_API_KEY` is unavailable. Root, real operator, and the known
  stale BDD contours were not run.
- Final audit is clean: Ruff passes all changed Python files, `git diff
  HEAD --check` passes, and current detour production/docs/tests contain no
  superseded header field names. The protected operator header-generation
  snippet was executed successfully and emits the canonical `NameKey` value.
- Implementation is complete. No database, replay log, shared `SourceKey`,
  pull shape, or output projection was modified.

## Current operator request — pre-commit/operator test investigation

The Human Operator ran `pixi run pre-commit-operator`, captured output under
`logs/from_operator`, and interrupted when the real operator E2E reached its
redeployment prompt. Investigate all failures first; do not run the real
operator E2E from this environment.

### Reproduced failures and causes

- `logs/from_operator/pre-commit.log` shows plain `pre-commit` stopped at Ruff
  with 11 errors. Running `pixi run -e detour-ai-augment ruff` here reproduces
  the same 11 errors exactly, so this is repository state, not a Lima/macOS
  discrepancy. They comprise three import-order errors, two missing blank-line
  errors, five over-100-character lines, and one post-function spacing error in
  five AI-refactor files plus `src/helpers/architecture.py`. Most are mechanical
  fallout from moving protected imports/files; one import error is in the known
  stale BDD module.
- Plain pre-commit would still fail after Ruff: its `lint` dependency also runs
  strict mypy over all `src tests`. Reproduction finds 213 errors in 24 files.
  Exactly 100 are from the protected sample proxy and its tests because the
  mypy exclusion still names the pre-refactor unprotected path. Another 25 are
  from the known stale BDD test. The remaining 88 span existing main-pipeline,
  other-detour, and test typing debt exposed when global `strict = true` was
  enabled by `892dfc5` on September 9. This means the global lint gate has not
  been green since that trial configuration, independent of the header patch.
- `logs/from_operator/pre-commit-extra.log` first fails in `test-repl-extra`
  during collection, before any selected real-API test runs. Reproduction with
  `pytest --collect-only . -m real_api` is exact. Commit `ac7fe5b` moved the
  detour pytest plugin/conftest and tests under `protected/` but left
  `tool.pytest.ini_options.norecursedirs` pointing only at old paths. Broad
  main-pipeline `pytest .` now descends into `protected/tests`, where pytest 9
  correctly rejects a detour-only `pytest_plugins` declaration in a nested
  conftest. The protected sample-deploy path is stale there too, causing its
  tests to be collected and unknown-marker warnings to appear.
- Moving the plugin declaration to repository-root `conftest.py`, as pytest's
  generic error suggests, is not the right first fix for this repository: main
  and detour suites are intentionally separate. The surgical correction is to
  update broad-main-suite recursion exclusions to the moved protected paths;
  targeted AI-augment suites can continue loading their local plugin.
- The root AI-augment suite never ran because `test-repl-extra &&
  test-detour-ai-augment-root` short-circuited on collection. The operator E2E
  itself did not report a test failure: it reached the plugin's expected
  `Redeploy AIVM before each operator test? [y/N]` prompt and was interrupted.

### Approved repair boundary and current verification

- The operator wrappers and their intentional continue-on-failure behavior are
  explicitly out of scope. A proposed `set -e` change was rejected and no
  wrapper diff remains.
- Pytest recursion exclusions now follow the refactored protected test and
  sample-deploy paths and exclude the known paused/stale BDD subtree. The safe
  broad collection check subsequently passed with 1 selected / 143 deselected.
- Repository mypy is restored to its prior non-strict settings and excludes the
  complete AI-augment subtree. A dedicated `mypy-detour-ai-augment` task checks
  that subtree with literal `strict = true`; protected sample deployment and
  paused BDD are excluded. Imported shared modules retain their types via
  `follow_imports = silent` but do not emit strict diagnostics in this pass.
- Dedicated strict verification is green: 40 AI-augment files, zero issues.
- The Human Operator rolled back unauthorized fixes outside AI augment. Current
  source diffs are confined to the AI-augment subtree; root `pyproject.toml`
  contains only the approved test/mypy wiring. Do not edit non-AI-detour source
  or tests without explicit authorization.
- The Human Operator moved `pandas-stubs`, `types-lxml`, and `types-psutil` from
  project-wide dependencies into the AI-augment feature. This is the clean
  resolution for the 20 unrelated ordinary-mypy diagnostics: default mypy
  regains its prior effective type surface while strict AI-augment mypy retains
  all three stubs. No unrelated source typing changes remain.
- `lint` now binds ordinary Ruff/mypy explicitly to the default environment and
  strict AI-augment mypy explicitly to `detour-ai-augment`, making this split
  stable regardless of the launching environment. Verification is green:
  default Ruff passes, default mypy checks 68 files with zero issues, and strict
  AI-augment mypy checks 40 files with zero issues.
- Ruff additively excludes the already-paused BDD subtree. The remaining shared
  architecture finding was the original refactor-related one-blank-line
  formatting defect and is fixed without changing behavior.
- Ruff did not remove `build_cards`/`write_cards_zip` from Backend `api.py`; it
  moved that import from line 42 to the later `src.helpers` group. Both names
  remain imported and are called by accepted-output card validation.
- Plain `pre-commit` is no longer blocked in lint. Its full safe test contour is
  next. The former extra-suite collection blocker is repaired; full
  `pre-commit-extra` still includes Human Operator root/operator contours and
  will not be run from this environment.
- First safe `pre-commit` launch exposed an environment-resolution issue before
  tests: the aggregate `test-detours` task used bare names for feature-owned
  Mode 0 and AI-augment tasks, so no single environment could resolve both.
  Aggregate test dependencies now bind main/Step 4/Mode 3 to `default`, Mode 0
  to `detour-mode0-econ-stats`, and AI augment to `detour-ai-augment`. The same
  explicit ownership is applied to `test-repl`, `test-repl-extra`, and direct
  `pre-commit-extra` dependencies. This does not alter operator wrapper control
  flow or the command the Human Operator runs.
- Full `pre-commit` now clears Ruff and both mypy passes, then reaches the main
  test suite. In this Linux workspace that suite reports 106 passed / 4 skipped
  / 34 failed: failures require the configured `splink_udfs` extension (network
  download is unavailable and configured binaries are under the operator's
  `/Volumes/home/aicode/...`) or one fixture under that same operator-only
  absolute tree. These are environment/resource failures, not failures caused
  by the AI-augment patch. Do not alter main-pipeline tests or resource handling
  to accommodate this workspace; the exact contour must run in Lima/operator.
- Safe extra prerequisite is green: `test-repl-extra` collected 144 main tests,
  selected the one `real_api` case, and skipped it because no case/key was
  available (1 skipped / 143 deselected).
- Standard non-root/non-operator AI-augment verification remains green after
  the lint/task changes: 215 passed / 47 skipped / 3 deselected; the separately
  selected protected real-API test skipped because `OPENALEX_API_KEY` is
  unavailable. Root and real operator tasks were not run.

## Current operator request — deployment path audit

Audit the AI-augment deployment and provisioning scripts after the
protected/non-protected split. Check every repository-relative source path,
script-to-script handoff, generated configuration path, and test/documented
entry point. Fix only stale path wiring caused by the split; do not execute the
root deployment or real operator contours.

### Plan

1. [done] Read `deploy.sh` and `provision.sh` completely and resolve all
   host paths against the current tree.
2. [done] Trace callers, tests, documentation, and pre-refactor history for
   path contracts that moved under `protected/`.
3. [done] Apply the surgical path correction.
4. [done] Run shell syntax, focused hermetic tests, lint/type checks as
   relevant, and a final stale-path search.

### Findings and implementation

- Commit `c8941ec` moved both runtime shell programs and `appendwatch.py` into
  `protected/` byte-for-byte, while the Backend audit protocol implementation
  `audit_read.py` remained in the non-protected source tree.
  The unchanged `deploy.sh` default therefore still looked for `audit_read.py`
  beside protected appendwatch, where no such file exists.
- Corrected only that stale host-source default: from the protected runtime
  directory it now walks to the detour root and selects
  `src/control_centre/appendwatch/audit_read.py`. The adjacent provisioning
  program and protected appendwatch defaults already resolve to existing files.
- `provision.sh` contains no repository-relative source paths. It receives the
  two guest source paths from `deploy.sh`; all remaining paths are explicit
  guest account, systemd, SSH, Codex, or restricted mount paths and remain
  coherent. No provisioning edit was necessary.
### Verification

- Both shell programs pass `bash -n`; all three resolved source files exist.
- The proposed one-off path-layout test was rejected and removed by the Human
  Operator; no test encodes this completed repository reorganization.
- Full `lint` gate passes: Ruff, ordinary mypy (68 files), and strict
  AI-augment mypy (40 files).
- `git diff --check` passes. Root deployment and real operator tests were not
  run.

## Current operator request — production AI-augment test failure

Investigate the Human Operator's complete production-machine log at
`logs/from_operator/test-detour-ai-augment.log`. The run collected 265 tests,
selected 262, and ended with 7 failed / 213 passed / 42 skipped / 3 deselected.
All seven failures are Control Centre browser tests. The dashboard children
did start and accept HTTP; their `/` page returned HTTP 500 because the
handwritten `BrowserController` test double lacked `drain_notifications`, added
to the production controller/page contract by `0394e81c`. `wait_for_server`
caught that `HTTPError` through `URLError`, retried for 30 seconds, hid the child
traceback, and finally killed each still-live child. The Human Operator's direct
child run exposed the actual traceback. This is cross-platform test-double
drift, not a slow macOS startup or a production-controller defect.

### Agreed replacement boundary

- The Human Operator does not want the fake-controller browser suite repaired
  as an E2E. A browser E2E must launch the real production dashboard, controller,
  Backend, IPC, database/replay/CAS projection, SSH transport, appendwatch, and
  Playwright UI. No production class, HTTP endpoint, or subprocess seam is to
  be monkeypatched.
- Only Codex is deterministic. The fixture creates a real SSH key and an
  isolated SSH-accessible guest tree containing a dummy Codex executable and
  real rollout/appendwatch files. The dummy creates a UUIDv7 Codex session
  JSONL after launch and performs real HTTP `/pull` and `/push` requests against
  the production Backend. The real appendwatch process watches that JSONL, and
  normal production SSH/audit code reads the resulting files.
- Do not replace `ssh` with a fake command or emulate audit command output. Test
  setup may configure real credentials, paths, ports, and isolated source/output
  resources only. This makes the browser contour hermetic while preserving the
  production lifecycle beneath the Codex boundary.
- Startup failure reporting should fail immediately on HTTP 500 and use a
  three-second readiness ceiling; the Human Operator will not accept a longer
  wait. The current unstaged interim diff still adds the missing method to the
  obsolete fake controller, adds a component regression around it, and improves
  startup diagnostics. Rework/remove that fake-controller repair as part of
  the native E2E replacement rather than treating it as final.

### Current plan

1. [in progress] Trace exact production SSH, Codex launch, appendwatch, config,
   and test-resource contracts needed by an isolated real-SSH fixture.
2. [pending] Add the smallest deterministic Codex dummy and isolated guest
   runtime that satisfy those contracts with real files and HTTP.
3. [pending] Replace the handwritten-controller browser harness with production
   dashboard composition and retain behavior-oriented Playwright assertions.
4. [pending] Run safe focused tests, Ruff, strict detour mypy, and diff checks;
   hand off any root/real operator contour to the Human Operator.

### Native startup findings

- The Human Operator has now completed the real production contour: dashboard
  startup, namekey queueing, Codex run, completed signoff, and result DOCX
  download all succeeded. Remaining findings are production rough edges, not a
  failed end-to-end lifecycle.
- Manual `serve --ipc-only` skipped the task's stable socket export because its
  branch ran and exited before the normal-mode exports. It consequently used
  Python's platform temporary directory (`/var/folders/.../T` on macOS), while
  normal manual mode used `/tmp/detour-manual-${UID}.sock`. Moved the existing
  socket export above the mode branch so both manual modes use the same path;
  Backend socket-selection logic is unchanged.
- The Human Operator's direct `pixi run dashboard` first exposed two independent
  replay-resource failures: the configured SHA-256 had a trailing ASCII space,
  and the 908,009-byte replay log lacked a terminating newline. File type,
  ownership, readability, and writability were correct. The replay-specific
  wrapper checks writable/non-symlink/newline safety before `RegisteredResource`
  performs exact hash verification, while wrapping all failures in one generic
  validation message.
- After those were addressed, the real dashboard exposed a production config
  parser defect: `AiAugmentDetourConfig`'s `mode="before"` validator inserted a
  `Path` object into `model_validate_json()` input, and strict JSON-mode Path
  validation rejected that validator-produced value. The surgical fix emits
  the derived detour DB path as a string and lets Pydantic convert it normally.
  Existing read-only config/source coverage now exercises `from_json()` instead
  of bypassing the production parser with `model_validate()`; the focused test
  passes.
- The first native browser-test draft still times out at its three-second
  readiness boundary on the Human Operator's machine. Do not increase that
  deadline. Remove the fresh Python/NiceGUI import from the measured child
  startup path (Linux fork from the already imported test process) and preserve
  immediate HTTP-500/child-log diagnostics.
- Local no-socket validation confirms the synthetic source fixture loads through
  the production `from_json()` and context paths with exactly 307 researchers,
  cohorts 196/78/33, and five multidraw researchers. Full browser execution is
  unavailable in this sandbox because localhost socket creation is denied.

## Proposed dashboard data-ownership simplification

- No code change is authorized yet. The Human proposes removing
  `SOURCE_DATA_STORAGE_KEY`, its host-filesystem fingerprint, and all direct
  main-DB/`AiAugmentBackendContext` source-factory use from the Control Centre.
  The Backend still derives the complete population because unfiltered
  `GET /query` returns it. The Control Centre context must consequently stop
  inheriting the Backend context; the current architecture Protocol also models
  that unwanted inheritance and needs separation.
- A valid persisted `BACKEND_DATABASE_STORAGE_KEY` `QueryResponse` becomes the
  sole source for researcher population, ground truth, attempts, committed
  output, run outcomes, table/history projection, and cards. With no persisted
  response on a first-ever start, the table is empty. Dashboard-owned queue and
  run-event journals remain separate control-plane state; live availability and
  Codex-busy status remain process probes.
- Ordinary UI rendering must never query IPC. Remove the current periodic
  owned-Backend query, Backend-readiness history query, and per-namekey card
  query. A distinct **Refresh statuses** action only probes process/API/IPC
  availability. A **Query IPC** action is enabled only when neither a full nor
  IPC Backend is running; it owns a short-lived `--ipc-only` child, waits for
  the Unix socket, performs one unfiltered GET `/query`, validates/applies/
  persists the response, and stops the child in `finally`. The existing
  supervisor supports only full mode, so its process/log/stop machinery can be
  reused but IPC-only launch and socket readiness are new behavior.
- Centralize specific browser notifications for missing/invalid cached state,
  process startup, unavailable IPC, unavailable detour DB, and invalid query
  response, directing the operator to the appropriate button. Without an IPC
  query the dashboard cannot know whether a valid cached response matches the
  current DB; it can only label it cached/unverified. A successful Query IPC
  replaces it.
- Exact current run ordering: Backend startup alone does not mutate `Run`; the
  Codex start callback appends `STARTED`, after which `Run.is_running()` is true
  and UI projects `RUNNING`. After Codex exit, `_finalize_run` performs an IPC
  GET (unless a commit ID is already journalled), appends `PUSH_ACCEPTED` when
  found, and returns the proposed terminal outcome. `_record_run_outcome` then
  POSTs `/completed|failed|cancelled` and refreshes the Backend snapshot. Only
  after it returns does `_execute_run` append the terminal event that actually
  changes `Run.lifecycle`/`run_outcome`; this ordering is tested. The terminal
  transition is not currently conditional on response code 200: expected IPC
  failure is reduced to a notification and 500 denotes partial archival capture.
- Not all run facts are outside query IPC. Queue/start/PID/session/rollout/exit
  and terminal events are in the dashboard journal, but acceptance, commit ID,
  persisted attempt/validation/output, and persisted run-outcome evidence come
  from IPC. Preserve automatic lifecycle IPC while making ordinary display
  refresh explicit unless the Human directs a lifecycle-contract change.
- Bootstrapping issue to resolve before implementation: current IPC-only query
  opens the detour DB read-only and cannot create/replay a missing DB. With no
  stored response, that failure leaves an empty table and therefore no namekey
  to queue, so the full Backend can never be launched from the UI. Either the
  owned query mode must initialize/synchronize the detour DB, or a narrowly
  defined absent-DB query must still return the source population without
  masking a missing projection for a non-empty replay log.
- Added only condensed `Run.lifecycle -> ...` annotations in `_execute_run`
  and `_process_queued_run` immediately after the relevant event application;
  no `Run.run_outcome` annotations or behavior changes.

## Current operator request — core state-authority audit

Perform an excruciatingly meticulous, multifaceted audit for the Multiple
Sources of Truth anti-pattern in the Codex-session parser and Backend replay
into the detour database. The target invariant is a hermetic contour from a
main-DB outerdict missing its DOCX innerdict to an AI-augmented replacement
innerdict, with the complete Codex interaction captured immutably in the replay
log and every disposable projection derived directly and transparently from
that record.

### Audit plan

1. [complete] Inventory the authoritative lifecycle and all Codex-parse,
   replay, projection, persistence, and query surfaces.
2. [complete] Trace field-level lineage and state transitions across runtime,
   replay, rebuild, restart, retry, and failure contours.
3. [complete] Inspect tests and invariants for duplicate mutable state, hidden
   derivation, divergent parsers/read paths, stale projections, and provenance
   gaps at component, record, transaction, database, and operator levels.
4. [complete] Report prioritized evidence, distinguish defects from deliberate
   archival duplication, and recommend the smallest core-strengthening steps.

This is an audit only; no production or test implementation change is yet
authorized by this request.

### Audit result

- Verdict: the contour has a strong fail-closed capture foundation, but is not
  yet a hermetic, reproducible replay system. The exact HTTP exchanges and
  appendwatch capture are durably written before responses; commit records bind
  pull/push IDs, session identity, and rollout CAS metadata. However, the
  detour DB can silently cease to be a direct projection of the immutable
  record, and a clean rebuild can depend on mutable current state.
- Critical: the projection checkpoint authenticates only the last projected
  replay line, not the full prefix. A same-length mutation to an earlier line
  is accepted if the last line remains unchanged. A temporary diagnostic
  proved the resulting replay/DB divergence (`replay_line_1='b'` while the
  projected row remained `'a'`).
- Critical: commit interpretation is not sealed. Rebuild invokes the current
  main-DB/release-map-derived source objects, match implementation/version,
  timezone, seed policy, and, for standardized retry submissions, live
  OpenAlex/ROR validation. The captured bytes therefore do not uniquely
  determine their interpretation.
- Critical: broad post-commit projection exceptions are converted into a
  durable failed-attempt projection and the checkpoint advances. Transient CAS,
  dependency, configuration, source, or parser failures can consequently be
  frozen as submission failures and are not retried after their cause is fixed.
- Critical: IPC-only query reads the current detour DB without synchronizing it
  to, or cryptographically checking it against, the replay log. It can serve a
  stale but structurally valid competing truth.
- High: already projected commit CAS blobs are not revalidated, and run-outcome
  CAS blobs are not replay-validated at all. Deletion/corruption after a
  checkpoint can leave the projection apparently healthy. The authoritative
  immutable set is therefore replay log plus CAS, but that set has no complete
  verified root.
- High: retry folds consume baseline/evidence rows from the derived detour DB;
  query separately assembles attempt and output tables; the response models do
  not enforce conservation between accepted attempts, commit records, and
  output rows. Validly shaped projection corruption can influence future work
  or escape detection.
- High: replay route validation is strict only for `POST /commit`; other
  records are admitted by a generic HTTP shape check. Unknown routes and
  malformed run outcomes can be checkpointed before route-specific parsing.
- High: the documented claim that a persisted terminal `410 Gone` reconstructs
  final output is not implemented. Output is actually derived on commit; the
  410 is stored raw and has no explicit commit edge.
- High: final output construction resolves its source researcher from the
  current main DB and mutates cached `AiAugmentOuterDict` instances with
  committed output. The exact selected source outerdict is not sealed into a
  run, so source and projection state are muddied.
- High: generated card ZIPs are live-only, unmanifested filesystem projections.
  Rebuild neither recreates nor verifies them, and stale/orphan artifacts can
  survive independently of replay.
- Medium: Codex indexes are keyed chiefly by the mutable rollout filename and
  cumulative prefix rather than exact CAS SHA plus line ordinal/hash. Computed
  line hashes are discarded, weakening attempt-specific provenance.
- Medium: the Codex parser contains duplicated interpretations: session
  filename time and top-level summary time are not cross-validated; only the
  first turn context supplies metadata; citation extraction and citation
  stripping use separate grammars; broadly named indexes intentionally omit
  uncited call chains without recording a projection/version contract.
- Medium: some causal links are inferred from ordering, including retry
  original-pull resolution; terminal records do not explicitly identify the
  accepted commit. Backend crash/restart resets process globals, so subsequent
  run-outcome capture can lose links that remain recoverable from replay.
- Medium: ground truth chooses the first complete DOCX source row without an
  explicit uniqueness/draw policy. The authorized read-only source aggregate
  contains four namekeys with multiple complete DOCX rows, so this ambiguity is
  observable even though their eligible-cohort membership was not inferred.

Strong existing properties include append-plus-fsync before public response,
cooperating process and replay locks, strict UUIDv7 commit models, explicit
pull/push references and ordinals, canonical key cross-validation, CAS
hash/size/line-count checks for newly projected commits, embedded appendwatch
bytes, transaction rollback around failed commit work, deterministic candidate
ordering/seed reset, and substantial malformed-rollout/retry coverage.

Nine focused tests passed. They also exposed the central coverage gap: there is
no test that destroys the detour DB, rebuilds only from replay plus CAS, and
compares every relation/query/artifact; the restart retry test reopens the same
DB, and the operator workflow validates the already-built DB. Missing mutation
tests include earlier-prefix edits, post-checkpoint CAS corruption, stale
IPC-only projection, current-source/config/network drift, cross-table
conservation corruption, unknown routes/malformed outcomes, and stale files.

Recommended repair order: define the immutable authority and pure-reducer
contract; bind checkpoints to the complete replay prefix and all CAS; refuse to
checkpoint infrastructure/projection failures; seal the exact source input and
all interpretation versions/dependency results; remove live main-DB/network
reads from replay; key Codex provenance to exact CAS lines; enforce projection
conservation; apply one freshness gate to full and IPC-only queries; and add a
destructive rebuild-equivalence plus corruption-matrix test suite.

## Current operator request — standardized card labelling review

Review only; no implementation change is authorized yet. The Human reports
that card rendering omits the existing `**AI-generated text**:` marker from AI
standardized fields and asks whether card construction is centralized.

### Findings

- Mechanical Markdown card construction is centralized in
  `src/helpers/cards.py::build_cards`, and ZIP/DOCX materialization is likewise
  centralized there. This renderer is intentionally generic: it prints every
  non-excluded innerdict value verbatim and has no knowledge of AI-augment
  columns.
- Detour-specific card construction is only partially centralized. There are
  exactly two production `build_cards` calls in the detour: accepted-attempt ZIP
  construction in Backend `api.py` and Dashboard preview construction in
  `ui.py`. Both first call the shared `selected_card_outer_dict`, so one common
  transform currently governs their row selection and standardized-placeholder
  suppression. However, each caller independently composes that transform with
  `build_cards`, intro/exclusions, and the one-card assertion; there is no
  single detour card-builder entry point. The Dashboard DOCX download renders
  the already-built Dashboard Markdown and is not a third construction path.
- `render_codex_values` decorates narrative AI values with
  `codex_parse.render_ai_value`, which supplies `**AI-generated text**:`, but
  serializes each standardized value directly to compact JSON. This is the
  correct canonical storage representation. `selected_card_outer_dict` deep
  copies the rows and parses standardized JSON only to hide null/scalar empty
  placeholders; for every non-empty value it leaves the bare JSON string
  unchanged. Generic `build_cards` then renders that bare value verbatim. The
  missing prefix is therefore deterministic in Backend ZIPs, Dashboard
  Markdown, and Dashboard-downloaded DOCX files.
- The main-pipeline Step 10 is the only other production `build_cards` caller.
  It is not an AI-augment card contour and should not acquire AI-column policy
  through a global change to the generic renderer.
- No test asserts the standardized-field card representation or the marker.
  The captured-contour test checks selected values and provenance fields only;
  the operator browser test merely requires a non-empty card. A test-side
  `rendered_cards` capture is populated but not asserted.

### Suggested surgical change

1. Preserve compact JSON unchanged in `codex_output_rows` and all query models;
   do not add Markdown to `render_codex_values` standardized storage.
2. Introduce one detour-specific `build_ai_augment_cards` helper, preferably in
   a small detour card module rather than Backend `api.py`. It should own the
   deep-copy/selection transform, empty-standardized suppression, standardized
   display decoration, common exclusions, generic `build_cards` invocation,
   and exactly-one-card invariant. Both Backend and Dashboard should call only
   this helper.
3. For each non-empty canonical standardized JSON string, decorate the card
   copy as `**AI-generated text**: {canonical_json}`. Do not quote the whole
   JSON string: JSON string values already carry quotes, while numbers, arrays,
   and objects require their native representation.
4. Centralize the exact marker spelling used by narrative, standardized, and
   comment rendering so it cannot drift.
5. Add focused tests for string, integer, list, and object standardized values;
   null/placeholder suppression; exactly one marker; canonical payload
   preservation; no mutation of the source outerdict; and byte-identical
   Backend/Dashboard Markdown from the common helper. Add one operator assertion
   that a known standardized field visibly carries the marker.

### Implemented standardized card labelling

- Added one canonical `AI_GENERATED_TEXT_PREFIX` and
  `render_ai_standardized_value` beside the existing narrative/comment
  renderers in protected `codex_parse.py`; existing narrative and comment output
  is unchanged.
- `selected_card_outer_dict` now decorates every non-empty value named by
  `AI_AUGMENT_STANDARDIZED_COLUMNS` on its deep-copied card projection. It
  continues to suppress JSON null and configured scalar placeholders. The
  canonical compact JSON in source/query/detour rows is not changed.
- Because both production detour card paths already pass through
  `selected_card_outer_dict`, this fixes Backend TXT/DOCX ZIP cards, Dashboard
  Markdown, and Dashboard-downloaded DOCX without changing generic main-pipeline
  card rendering.
- Added regression coverage across all nine standardized columns with JSON
  string, integer, array, and object forms; exact rendered marker/value text;
  null and both configured empty placeholders; and source-innerdict
  immutability.
- Validation: Backend `test_api.py` passes with 127 tests and 2 skips; focused
  strict mypy over the three changed Python files succeeds; Ruff checks succeed;
  and `git diff --check` succeeds. Full strict detour mypy remains blocked by 13
  pre-existing errors in the Human-modified Control Centre tests
  (`test_ui_e2e.py` and `test_ui.py`), unrelated to this patch.

## Proposed terminal-410 SourceKey response header

Review only; no implementation is yet authorized. The Human proposes giving a
terminal `GET /pull` 410 response the same kind of response header produced for
run-outcome snapshot requests.

- The run-outcome response currently has only a `SourceKey` response header,
  canonically produced from rollout filename and line count. Its pull/push
  record IDs are in `RunOutcomeResponseBody`, not in response headers.
- A 410 can and should identify the exact accepted commit snapshot without
  rereading the live rollout. Its accepted `AgentRuntimeAttemptRecord` contains
  the commit, whose mandatory canonical `SourceKey` identifies the rollout
  filename and commit-time line count. Reparse/re-render that value through the
  existing SourceKey helpers and return it on the 410 response. It should share
  the run-outcome header mechanism/type, not necessarily its eventual value:
  the rollout normally grows while Codex receives the 410 and exits, so the
  later run-outcome snapshot can correctly have a larger line count.
- This is meaningful provenance: the 410 SourceKey can equal the accepted
  commit SourceKey, and the commit directly references the originating pull and
  push. It is therefore a transitive causal chain. SourceKey alone is not a
  direct pull/push/commit record-ID edge and can match both rejected and
  accepted attempts if a retry occurs without rollout growth; replay must
  resolve it to exactly one prior accepted commit.
- Merely emitting the header would be low difficulty but mostly documentary.
  The worthwhile surgical patch also route-validates terminal 410 records:
  require a canonical SourceKey, resolve exactly one earlier accepted commit
  with an equal SourceKey, and require the 410 body to equal that accepted
  attempt's normalized standardized submission plus optional selected ground
  truth. Infrastructure/linkage failure must abort projection rather than be
  checkpointed as a failed submission.
- Public FastAPI/Starlette response headers pass through ASGI in lowercase
  (`sourcekey`), whereas run-outcome records are constructed directly with the
  logical `SourceKey` spelling. Header names are HTTP-case-insensitive, but the
  persisted model uses an ordinary case-sensitive dict. The patch must use one
  shared case-insensitive accessor or canonicalize this known persisted header;
  otherwise the two paths only appear to share a contract.
- Implementation remains small: factor a shared SourceKey-response helper;
  add the accepted-commit-derived header in `authoritative_pull`; document it in
  the OpenAPI 410 response; add a strict terminal-410 parser/projector check;
  and test live response, replay-log capture, accepted-commit equality, missing/
  malformed/mismatched headers, retry ambiguity, body mismatch, and both
  ground-truth/no-ground-truth responses. No main-pipeline or cross-detour
  change is needed.

## Backend lifecycle wording correction

- Renamed the remaining stale Backend lifecycle member/value from
  `BackendLifecycle.COMPLETE = "complete"` to
  `BackendLifecycle.COMPLETED = "completed"` in the protected architecture
  contract, concrete enum, accepted-attempt transition, terminal-pull gate, and
  Backend test.
- Confirmed that no standalone `COMPLETE`, `"complete"`, `CANCELED`, or
  `"canceled"` lifecycle wording remains in the detour Python/Markdown corpus.
  Existing run terminology remains `COMPLETED` and British `CANCELLED`.
- Validation: Backend `test_api.py` passes with 127 tests and 2 skips; Ruff and
  focused strict mypy pass across all four touched lifecycle files; and
  `git diff --check` passes.

## Current operator report — IPC-only query crashes on persisted standardized attempt

Diagnosis only; no fix is yet authorized. The Human's `pixi run serve
--ipc-only` starts and answers `OPTIONS /query`, then fatally exits on the first
GET query while reconstructing a persisted `AgentRuntimeAttemptRecord`.

- This is not an IPC socket/startup failure. IPC-only deliberately opens the
  existing detour DB read-only and does not synchronize or reproduce it from
  replay. The crash begins in `_attempt_records` while parsing an already
  projected attempt for the query response.
- `_AgentRuntimeAttemptRecordJson.submission` is a union containing live
  `Submission` and `StandardizedSubmission` models. The plain branch correctly
  rejects the nine `standardized_value` fields as extras; the standardized
  branch reaches `AcademicInstitution.validate_institution`, whose Pydantic
  model validator performs live OpenAlex and ROR HTTP requests and requires
  `OPENALEX_API_KEY`. The IPC-only branch of the `serve` task exits before
  loading that key, producing the reported aggregate union error.
- Setting/exporting the key is not the correct fix. Querying immutable persisted
  records must not perform external validation. It would also make read latency
  and success depend on current network/API data.
- The supplied 11-line replay log reproduces the model failure directly: its
  second push has seven academic-institution objects, and direct standardized
  parsing without the key produces 45 validation errors headed by the same
  missing-key cause.
- The same flaw likely explains the previously observed very slow browser E2E.
  A query parses persisted attempt submissions once in the IPC Backend. The
  Dashboard then parses them once in `_QueryResponseJson` and a second time via
  `AgentRuntimeAttemptRecord.from_serialized_json`. For this accepted attempt,
  seven institutions times OpenAlex plus ROR times three passes permits 42
  needless external requests per query.
- Other persisted-state revalidation exists in `_derive_retry_obligations`,
  which reparses prior standardized submissions and likewise must not rerun
  external institution checks. The current retry push itself is separately
  parsed through the live validation path and should retain the intended live
  policy until the larger hermetic-replay design is corrected.
- The subsequently supplied CAS contains all three referenced blobs. Their
  actual SHA-256 digests, byte sizes, and line counts exactly match the two
  commits (411,209/96 and 490,726/129) and `/completed` terminal snapshot
  (510,548/147). The supplied 307-row release map also exactly matches the
  configured `a1cd6f...a5a7c` digest. Its initial directory mode was `0444`,
  which prevented traversal; only the owner traverse bit was added. The
  original replay log remains unchanged and read-only.
- A real isolated reconstruction was then completed against the authoritative
  source DB, supplied release map/log/CAS, and a fresh `/tmp` detour DB. In the
  current environment, the first attempt replayed as the expected evidence
  rejection. The second attempt did *not* reproduce its historical accepted
  result: lack of `OPENALEX_API_KEY` made current
  `StandardizedSubmission.model_validate_json` reject it at
  `pydantic_validation`, storing `submission=None`. Projection nevertheless
  checkpointed all 11 records, including the immutable `/completed` 200 record.
  The resulting projection therefore says both attempts were rejected while
  separately saying the run completed successfully.
- IPC query against that fresh projection succeeds precisely because replay
  erased the second standardized submission. It returns two rejected attempts,
  the `/completed` 200 outcome, 307 outerdicts, and 16,450,217 bytes of JSON.
  By contrast, the Human's production projection was made with live validation
  available and retained the accepted standardized submission; IPC-only then
  crashes while revalidating that persisted value without the key. Thus clean
  replay and read-only query disagree based solely on current credentials and
  external validation availability.
- Running the native full `pixi ... serve` task in this checkout also stops at
  its explicit launcher check because `.env` has no `OPENALEX_API_KEY`. Adding
  the key would conceal the read-path bug and make replay depend on live
  OpenAlex/ROR state; it is not a sound repair.

### Recommended repair boundary

- Immediate surgical fix: introduce an explicit persisted-data validation
  context for `AcademicInstitution` which performs all structural Pydantic
  validation but suppresses external OpenAlex/ROR rechecks. Use it only in
  `AgentRuntimeAttemptRecord.from_serialized_json`, the initial
  `_QueryResponseJson` parse, and prior-submission parsing in
  `_derive_retry_obligations`. Default/live `StandardizedSubmission` parsing
  must continue to run its current validation, and tests must prove the two
  paths remain distinct.
- Also remove the Dashboard's second attempt reconstruction pass: once the
  response DTO has been validated structurally, convert it once rather than
  serialize and parse each attempt again.
- Longer-term hermetic fix: remove network I/O from Pydantic construction,
  model external institution validation as an explicit live operation, capture
  its exact evidence immutably, and make replay consume that capture. The
  immediate context patch repairs read/query behavior but cannot make clean
  projection reproduce the historical accepted attempt: `_execute_attempt`
  itself currently reruns external validation while replaying the second
  commit. The projector must consume an authoritative captured validation
  result rather than silently checkpoint a newly rejected interpretation of a
  historically completed run.

### Exact proposed repair shape

- If only the immediate read failure is patched, add an explicit Pydantic
  persisted-data context whose sole effect is to return from
  `AcademicInstitution.validate_institution` before its OpenAlex/ROR calls.
  Default/no context remains the current live behavior. Pass that context from
  `AgentRuntimeAttemptRecord.from_serialized_json`, the first
  `_QueryResponseJson.model_validate_json`, and the historical submission read
  in `_derive_retry_obligations`. Add a conversion helper accepting an already
  validated `_AgentRuntimeAttemptRecordJson`, and use it from `QueryResponse`
  instead of serializing each model and parsing it a second time.
- That context switch is an interim patch only. In the preferred complete
  repair, remove `os.getenv`, mutable `OPENALEX_PARAMS`, and `requests.get`
  entirely from `AcademicInstitution`; all submission models become pure and
  every read path receives structural validation automatically. Add an
  explicit Backend institution validator invoked only while handling a new
  standardized push. It receives the key explicitly, uses request-local
  parameters, distinguishes invalid submitted references from operator/network
  configuration failures, and returns canonical captures of every OpenAlex/ROR
  response used.
- Replace the request-only synthetic `/commit` with a finalized synthetic HTTP
  exchange. Preserve its current request body (pull/push/session/rollout/report
  linkage) and add a strict response body containing the post-commit
  validation, normalized submission when available, ground-truth innerdict when
  accepted, canonical evidence assessment when available, the exact accepted
  replacement innerdict when accepted, and ordered institution-validation
  captures. The captures contain provider, submitted field/index path, key-free
  request target, response status, and bounded canonical response bytes plus
  digest; they must cover every non-sentinel institution reference exactly once
  and may contain no extras. The commit response is the sole authoritative
  outcome; the attempt/output/audit DuckDB tables are projections of it, not
  parallel authorities.
- Refactor `_commit_accepted_push`/`append_authoritative_record` so attempt
  evaluation occurs in an uncommitted DuckDB transaction, produces the
  finalized commit response, fsyncs that one self-contained commit line, then
  commits the projection/checkpoint. If log append fails, roll back. If the
  process dies after fsync but before DuckDB commit, startup can reconstruct
  from the finalized line. Materialized cards should be generated only after
  authoritative fsync/DB commit because they are replaceable projections.
- On replay, `_validate_projected_commit` structurally parses the push and uses
  only captured institution responses. It performs no environment lookup or
  network request, rebuilds the deterministic rollout/evidence/output tables,
  and requires its derived post-commit result to equal the committed response
  before advancing the checkpoint. Missing, malformed, mismatched, duplicated,
  or unused captures, or an outcome disagreement, are projection conflicts—not
  newly synthesized rejected attempts.
- Tests should prove: persisted attempt/query/retry reads make zero HTTP calls;
  malformed persisted structures remain rejected; live institution checking
  still occurs; a live run with fake HTTP responses followed by DB deletion,
  key removal, and network-disabled replay yields equal table/query projections;
  capture or outcome tampering fails before checkpoint advancement; and log
  fsync/DB-commit failure points never expose a committed projection without a
  complete authoritative commit record. No legacy commit parser or fallback is
  proposed.

### Whole-file replay determinism test (2026-09-13)

- No existing test performed two complete authoritative replays from JSONL,
  deleted the first detour database, and compared the two database-file hashes.
- Added that exact test using the supplied replay log, release map, CAS, and the
  real replay implementation. It closes the first database, hashes it, deletes
  it, reconstructs the same path from the same inputs, closes it, and compares
  the second whole-file SHA-256.
- The invariant currently fails. The first database hash was
  `782c3a0ae7381d634c311cb194241846c00d55d93d90b83fb0d1a466ccc86fdb`;
  the second was
  `67c50ba3de33c587801ff44d6fba29a2fb4f3c0cc582423d9c4953b76f480382`.
- A retained-file diagnostic established that the replayed projections are
  logically identical: all nine base tables have equal row counts and zero
  `EXCEPT ALL` differences in either direction. The equal-size files differ in
  only 63 bytes. Those bytes are the checksums and final eight payload bytes of
  four 256-KiB DuckDB overflow-string blocks, belonging to `assessment`,
  `baseline`, `codex.cite_text`, and the authoritative HTTP `record`. DuckDB
  1.5.1 does not serialize the unused block-tail bytes canonically; stale
  zero/`0xff`/text bytes differ between reconstructions, and the corresponding
  whole-block checksums consequently differ. The mismatch is therefore in the
  physical DuckDB representation, not in replayed table data.

## Current operator request — protected replay/DB ownership models

Implement only the agreed storage ownership refactor:

- Add a public frozen `AiAugmentRegisteredResource` base under protected
  Backend data models.
- Add `ReplayLogRegisteredResource`, directly inheriting that base and owning
  the replay-log descriptor, process lock, append lock, durable append, and
  context-manager lifetime. It derives its filesystem path through inherited
  `__fspath__`; it has no duplicate `path` field/property.
- Add `AiAugmentDetourDB`, owning the projected DuckDB path/connection and
  context-manager lifetime.
- Change protected AI-augment configuration fields to these models and replace
  downstream manual/global open-close use with `with ... as ...` ownership.
- Preserve existing replay, offset, hash, tail-repair, DuckDB extension, and
  read-only IPC behavior. Do not add unrelated integrity policy or replay
  changes. If existing tests expose a design issue, stop and request approval
  before expanding the patch.

### Implementation checkpoint

- Added the three protected models and changed configuration to expose
  `detour_db: AiAugmentDetourDB` and a `ReplayLogRegisteredResource`. Full Backend lifetime
  now directly enters both configured objects; IPC-only directly enters
  `AiAugmentDetourDB.read_only()`. Replay append is owned by the entered replay
  resource. The unauthorized `startup_complete`, `ExitStack`, separate
  `open_detour_database`, and `_backend_detour_database` adapter have been
  removed.
- Removed the production global DuckDB connection/path and replay-log
  descriptor/manual open-close functions. Only `AiAugmentDetourDB` opens the
  projected DuckDB, with both modes explicit; direct opens elsewhere are for
  the source database.
- Both prior approvals were resolved narrowly: the hash-enforcement test
  temporarily changes the fixture's mode for direct tampering, and the model
  preserves native DuckDB open exceptions without adding translation policy.
- Writable and read-only database contexts both return `AiAugmentDetourDB`.
  Source/detour path comparison is exposed by the model rather than by reaching
  through its path field. The operator test retains the model and no longer
  extracts a path or opens the projected database directly.
- `ReplayLogRegisteredResource` owns reads as well as locked durable appends.
  Replay parsing receives bytes from the open model; no active caller converts
  the replay resource back to `Path`. Tail repair and requested hash
  verification execute under its context lock without a copied resource.
- Removed the stale path-oriented adapters and unused open-error locale strings.
  The broad diagnostic now reports an API lifespan failure instead of
  mislabelling every post-startup failure as startup.
- Per operator authorization, the four remaining UI-test count names now use
  `completed`, matching the production lifecycle model.
- Literal stale-symbol searches are clean across active detour production and
  tests. The explicitly paused/excluded protected BDD file was restored
  unchanged at operator request and was neither adapted nor tested.
- Validation: strict detour mypy passed for all 43 source files; Ruff passed;
  focused ownership tests passed (10); Backend API/IPC tests passed (134, with
  3 skips and only the known physical DuckDB hash test deselected); UI unit
  tests passed (46); operator preflight passed (3); and the complete included
  non-root/non-network contour passed (253, 12 skipped, 5 deselected). The seven
  browser E2E cases were collected and skipped because no browser runtime is
  available in this environment. `git diff --check` passed.

### UI E2E browser selection (2026-09-13)

- UI E2E tests now launch the Google Chrome channel by default. If Chrome
  launch fails, the test failure explicitly directs the operator to rerun with
  `--playwright-chromium`.
- The single pytest opt-in affects both existing browser launch sites and uses
  Playwright Chromium by omitting the Chrome channel.
- Ruff and focused mypy pass, and pytest exposes the new option. The full
  opt-in UI E2E invocation collected all seven tests, but this environment
  skipped them before browser launch because local sockets are unavailable.
  A direct Playwright Chromium launch also confirmed that its separately
  downloaded browser executable is not installed in this environment.
- Final configured `test-detour-ai-augment` rerun passed: 254 tests passed, 13
  skipped, and 3 deselected. Its separate real-API check was skipped because
  `OPENALEX_API_KEY` is unavailable. The seven UI E2E cases were among the
  skips because this environment disallows local sockets.

### Operator-elevated socket tests (2026-09-13)

- Added a narrowly scoped feature task for the elevated contour. It runs
  the seven UI browser E2Es, the real mode-0600 Unix IPC test, and the two
  appendwatch socket cases that the current Codex permission profile skips.
- The task uses `script -q -e -c` so combined stdout/stderr is both shown live
  and captured under `logs/from_operator`; it
  preserves pytest's exit status and does not use `set -e`.
- Pixi recognizes the task and `git diff --check` passes. It remains for the
  operator to run outside this session's network-disabled seccomp policy.
- The first operator run exposed a test-harness failure: startup errors were
  treated as transient unavailability for 30 seconds, child output was omitted
  from the timeout, and pytest continued into the next E2E case.
- Narrow correction only: startup HTTP errors now fail immediately; timeout
  and HTTP-error handling
  terminates and drains the child so its complete captured output is embedded
  in the pytest failure; and this operator task uses `-x`.
- The second operator run stopped after the first failure in 7.02 seconds. It
  received no HTTP response and the child emitted no captured output before
  the three-second startup deadline, so there was no exception trace to attach.
- The failing E2E child uses the injected `BrowserController`, not production
  config/backend startup, so replay-log hash verification is not involved.
  Code inspection also shows a latent incompatibility: UI refresh calls
  `drain_notifications()`, which that injected controller does not implement.
  This mismatch is now patched with a no-op method on the fake.
- Focused Ruff and strict mypy passed; all seven UI E2Es collect and skip in
  the socket-restricted development environment; `git diff --check` passed.
- The first `script` quoting attempt was not executable because TOML consumed
  the inner quote escapes. Replaced it with the repository's established
  `'"'"'"'` shell-quoting pattern and ran the actual Pixi task end to end:
  output was visible live, the log was populated, and the task returned zero
  for the expected 10 socket-policy skips in this environment.
- Current failure diagnosis is two-layered. A fresh import of the E2E server
  module took 5.62 seconds and production Dashboard UI alone took 6.42 seconds
  here, so the three-second deadline expires before the child can answer or
  emit useful startup output. With the former longer deadline, the first page
  request reached the second failure: production `refresh()` calls
  `drain_notifications()`, but the cast-masked fake `BrowserController` lacks
  it. `0394e81` added both the method and call to production on September 10;
  static comparison finds this is the fake's only missing UI-used member.
- Reviewed `stash@{0}` read-only and did not apply/pop it. It is a later
  QoL/native-E2E refactor, not the repair vehicle for the authoritative seven
  existing tests. It also retains the three-second cold-dashboard deadline.
- Operator approved the repairs to the current seven-test contour: allow ten
  seconds for the measured six-second cold import/startup, retain ten seconds
  for orderly child shutdown/output draining, retain immediate HTTP-error
  failure, and add the fake controller's missing no-op
  `drain_notifications()` method. The QoL stash remains untouched.
- Focused Ruff, strict mypy, and `git diff --check` pass after the two test
  edits. All seven browser cases collect; this execution environment still
  skips them at socket creation, so actual pass/fail awaits the operator task.
- The next operator run reached browser launch without a Dashboard failure and
  stopped immediately because system Chrome is absent. Per operator direction,
  the task is now the feature-scoped `elevate`: `pixi run elevate` automatically
  selects the `detour-ai-augment` environment and opts into Playwright Chromium
  internally. Live/captured output is written to
  `logs/from_operator/elevate.log`.
- The exact `pixi run elevate` command was executed here, proving environment
  routing and shell quoting; all ten cases skipped only because this Codex
  profile forbids local sockets. Actual pass/fail awaits the operator rerun.
- The operator rerun exposed an unprovisioned browser: opting into Playwright
  Chromium selects its browser but does not install it. The expected
  `chromium_headless_shell-1234` executable is absent, so no browser test ran.
  This was deterministically knowable here and should have been handled before
  handoff. `elevate` now runs the non-root
  `python -m playwright install --only-shell chromium` inside the logged
  `script` command before pytest, joined by `&&`. An initially proposed
  `--with-deps` was removed at operator direction because this contour must not
  require sudo or install host OS packages.
- The non-root browser download succeeded. Launch now fails before any browser
  assertion because the minimal Ubuntu host lacks `libatk-1.0.so.0`. Direct
  `ldd` inspection finds exactly nine unresolved libraries: ATK, AT-SPI bridge,
  AT-SPI, Xcomposite, Xdamage, Xfixes, Xrandr, GBM, and ALSA. The proper
  non-root contour is to supply their conda-forge runtime packages in the two
  Linux target sections of the detour feature and expose `$CONDA_PREFIX/lib`
  to the downloaded browser through `LD_LIBRARY_PATH`. The operator approved
  and these manifest/task edits are now applied. Pixi parses the feature/task;
  lock solving cannot run under this profile because conda-forge DNS/network is
  blocked, so the network-enabled `pixi run elevate` operator run must resolve
  and install the added packages before executing the contour.
- The resolved non-root browser runtime works: Chromium launched and the first
  four UI E2Es passed. The fifth fails on a stale September 3 assertion that
  expects `attempt-1` in the commit-record-ID column; current production and
  the fake both put a UUIDv7 there. The final browser-contract test contains
  three more stale `attempt-1`/`attempt-2` assertions for the same pre-refactor
  convention. Per operator approval, the fifth test now validates UUIDv7 and
  the final test identifies its two attempt rows through their existing
  `ai-value-1`/`ai-value-2` projections.
- Post-edit validation: Ruff and the configured strict detour mypy contour
  pass (43 source files), the seven browser cases collect, stale `attempt-N`
  literals are absent, and `git diff --check` passes. This profile still skips
  browser execution at socket creation; operator `pixi run elevate` remains
  required for actual pass/fail.
- Final operator `pixi run elevate` result: all seven UI browser E2Es and all
  three elevated socket tests passed, with zero skips (10 passed in 113.35s).
  The non-root Playwright browser and conda library contour is therefore
  exercised end to end. The lockfile resolved both Linux targets, Pixi's
  feature/task dry run succeeds, and final `git diff --check` passes.

## Current operator request — focused `ui.py` ownership audit (2026-09-14)

Analyze, without changing production or test code, whether the same
behavior-owning/OOP refactor applied to Backend configuration is worthwhile for
the Dashboard. Focus on duplicated authorities, module-level mutable state,
anemic wrappers, and behavior placed outside the model that owns it; do not
recommend a broad file split merely because `ui.py` is large.

### Audit plan

1. [done] Inventory module functions/globals and large classes.
2. [done] Trace source/query persistence, run journal/queue, cards,
   application lifecycle, and Backend/Codex ownership.
3. [done] Cross-check concrete duplication and stale-state risks against
   adjacent models and tests.
4. [done] Return a prioritized, surgical proposal; make no code changes.

### Findings

- Highest-risk duplication is Dashboard data: the complete source outerdicts
  are cached under `SOURCE_DATA_STORAGE_KEY`, the complete query response is
  cached again under `BACKEND_DATABASE_STORAGE_KEY`, and the controller then
  maintains separate mutable researcher, namekey, ground-truth, attempt,
  committed-innerdict, and run-outcome projections. Applying a query response
  mutates only `committed_innerdicts` onto the separately sourced outerdict and
  discards the response's other source fields.
- Card reads form a second live-data contour. The IPC client performs an
  implicit namekey query, while the page and client each cache the rendered
  card independently. Page invalidation never clears the client cache, so an
  explicit refresh or rerun can still redisplay stale markdown.
- A nominal UI snapshot is not a read: each page's one-second timer calls
  `snapshot()`, which calls `refresh_idle_state()` and, while the owned Backend
  runs, performs and persists a full IPC query response. Multiple pages multiply
  this I/O. Page construction and explicit refresh also repeat availability
  checks.
- Run mutation/replay behavior lives in module functions while `Run` remains
  mostly anemic. The controller separately owns the full event list and replayed
  run map. The persisted queue cannot be mechanically deleted: a run is removed
  from it before waiting for Codex to become idle but still has `QUEUED`
  lifecycle, so current events alone do not identify queue membership.
- Application composition is held by mutable module globals (`SERVICES`, config
  path, lifecycle-configured flag) and free functions. `_ApplicationServices`
  duplicates references already retained by the controller. The `SERVICES is
  not None` startup branch mainly supports global-injection tests and would
  start an already-created controller again in a repeated production startup.
- `Final` lookup dictionaries remain mutable objects. More importantly, UI
  projection code imports the Backend API's private `_PushValidationError` and
  several implementation helpers, indicating a leaky boundary.
- The best focused sequence is: (1) one immutable QueryResponse-derived
  Dashboard snapshot, removing the source-cache/repository contour, hidden card
  IPC, duplicate card caches, and timer-driven full queries; (2) a `RunJournal`
  that owns event application/replay while preserving current queue semantics;
  (3) a locally constructed `ControlCentreApplication` owning composition and
  lifecycle, eliminating mutable runtime globals. Each should be separately
  reviewed. IPC-only auto-start and projection-freshness metadata are behavior
  changes and should not be smuggled into these refactors.
- Do not split `_ControlCentrePage`, `_BackendSupervisor`, `_CodexRunner`,
  `_AttemptReconciler`, or `_VariableProjector` solely because `ui.py` is large;
  these are substantially behavior-rich and cohesive at their current seams.
  Pure formatting helpers likewise do not benefit from artificial classes.

No production or test code was changed for this audit.

### Proposed explicit Dashboard operations

- Dashboard startup should restore only `AiAugmentDashboardStorage`; absent a
  stored query snapshot, the grid is empty and both probe groups begin as `not
  probed`. Page construction and its timer perform no network, SSH, IPC, source
  database, or query-response work.
- `Probe Backend` explicitly checks the full API and IPC health concurrently
  and updates two volatile statuses. It never calls `/query` or changes the
  stored Dashboard snapshot.
- `Probe AI Agent Runtime` explicitly exercises the exact production SSH route
  with a byte roundtrip, then runs the existing supported
  `/home/ai/.local/bin/codex login status` command over that route. It reports
  AIVM/SSH reachability separately from Codex authentication; if transport
  fails, authentication is `not checked`, not `unauthenticated`.
- `Query IPC` is the sole display-data hydration capability. It strictly parses
  `QueryResponse`, constructs a complete immutable `DashboardQuerySnapshot`,
  and asks `AiAugmentDashboardStorage` to replace the prior snapshot without
  merging. Construction must complete before any mutation; failure preserves
  both the stored and current snapshot. The click handler reports concise
  success/failure to that user while the server log records stages and the full
  exception.
- The one-second page timer may remain for local run/UI repainting, but its
  snapshot path becomes pure. Probe results should not persist across Dashboard
  restart because they immediately become stale.
- Remove current implicit full queries from Backend readiness, timer refresh,
  card rendering, and post-run-outcome refresh. Card rendering uses only the
  stored query snapshot.
- One material lifecycle dependency remains: `_finalize_run()` currently calls
  `/query` to decide whether the just-exited Codex session produced an accepted
  commit. If absolutely only the button may call `/query`, preserve run semantics
  through a new narrow Backend IPC completion-status port returning only the
  session's accepted commit ID/status; do not give the run controller access to
  `QueryResponse`. This endpoint is a separately approved connector change.
- Use capability separation: the page's explicit query action alone receives
  the query client; storage-backed display/controller code does not. Run-outcome
  POST and narrow completion-status capabilities remain separate from Dashboard
  hydration.

No implementation was authorized or performed.

## Current authorized implementation contract (2026-09-14)

This is the active scope. Broader Dashboard storage/probe/lifecycle proposals
above remain analysis only and are not authorized.

1. **`AiAugmentBackendStore`**
   - Own replay-log and detour-DB lifetimes together.
   - Own synchronization, freshness checks, append/project/checkpoint ordering,
     and the active connection.
   - Expose only `writable()`, `read_only()`, and the short-lived writable
     `threading_lock()` operation context.
   - Remove the ambiguous `healthy` state and old projection context.
   - Eliminate stale direct production access to DB/replay paths and child
     contexts.
2. **`AiAugmentCAS`**
   - One unprotected class owns rollout copy, hashing, publication, conflict
     checks, and replay lookup.
   - Add no CAS support classes.
   - Backend store receives the same CAS instance owned by configuration.
3. **Configuration and composition**
   - Keep release map and replay log separately on `AiAugmentDetourConfig` as
     registered resources; remove `AiAugmentResources`.
   - `AiAugmentDetourConfig` inherits from both `PipelineConfig` and
     `FrozenStrictModel`: shared fields/validators come from the former and the
     detour's immutable strict model policy comes from the latter.
   - Move `configure_runtime()` to `server.py` and construct one explicit
     runtime for full and IPC-only modes.
   - Remove `RUNTIME_CONFIGURATION` and lazy/global runtime access.
4. **IPC query contour**
   - Put `QueryRequest` in the unprotected Dashboard data-model package and
     make it a `FrozenStrictModel`.
   - Replace `_build_query_response` with
     `handle_query_request(runtime, ipc_request) -> QueryResponse`.
   - Nest attempt and run-outcome DB readers inside that handler; keep raw
     DuckDB connections out of top-level query helper interfaces.
   - Flask alone constructs `QueryRequest` and serializes `QueryResponse`.
   - Full mode invokes the handler under `backend_store.threading_lock()`;
     IPC-only invokes it inside the already-open read-only store.
   - Use named nested handlers, not `functools.partial`.
5. **Shared strict model base**
   - Replace every detour model repeating exactly
     `extra="forbid", frozen=True, strict=True` with `FrozenStrictModel`.
   - Preserve materially different/custom model configurations and verify with
     literal plus multiline grep.
6. **Tests**
   - Surgically adapt only tests directly affected by these ownership/API
     changes.
   - Add focused tests proving `backend_store.connection` and
     `handle_query_request()` fail outside a store context, and that managed
     writable/read-only access succeeds through the store connection.
   - Do not modify excluded protected BDD tests.
   - Do not remove or rename the known duplicate replay-hash test without
     separate approval.
7. **Verification**
   - Grep for stale removed APIs and direct production path/context access.
   - Run Ruff, strict detour mypy, focused Backend/IPC tests, then the configured
     test suite.
   - Stop for authorization if any required change exceeds this list.

### Current handoff status

#### Implemented inside the agreed contract

- `ReplayLogRegisteredResource` is a protected registered resource and locked
  context manager. It owns mode changes, no-follow open, flock, tail repair,
  reads, durable append, and fsync.
- `AiAugmentDetourDB` is the protected projected-DB context model. It owns
  writable/read-only DuckDB connection lifetime and loads ordinary
  `splink_udfs` on every connection, independently of Codex-match version.
- Unprotected `AiAugmentCAS` owns rollout copying, hashing/line counting,
  conflict detection, atomic publication/fsync, and replay lookup. No auxiliary
  CAS classes were retained.
- Unprotected `AiAugmentBackendStore` jointly opens replay log and detour DB,
  exposes the managed connection, checks/synchronizes checkpoints, serializes
  writable operations with `threading_lock()`, and performs replay-log-first
  append followed by projection.
- `AiAugmentDetourConfig` directly owns release-map and replay-log registered
  resources plus the shared CAS/store instances. `AiAugmentResources` is gone.
  It inherits `PipelineConfig, FrozenStrictModel`; effective config is
  `extra="forbid", frozen=True, strict=True`. JSON configuration is validated
  in JSON mode so strict parsing still admits JSON path strings.
- `server.configure_runtime()` is the sole runtime constructor. Full and
  IPC-only startup use one explicit context; `RUNTIME_CONFIGURATION` and lazy
  runtime lookup are gone. Full mode composes FastAPI and threaded Flask IPC;
  IPC-only enters the store read-only and runs the blocking Flask server.
- Protected IPC now exposes `handle_query_request(runtime, QueryRequest)` and
  `handle_run_outcome_request(...)`. `QueryRequest` is an unprotected
  `FrozenStrictModel`; Flask alone converts HTTP to/from request/response
  models. Attempt and run-outcome readers are nested in the query handler.
- The AI-detour projection type and identifiers consistently use
  `AiAugmentSingularOuterDict` / `singular_outerdict`; bare `OuterDict` remains
  only for the original main-pipeline multi-namekey card input.
- Models whose complete policy was exactly strict/frozen/extra-forbid now use
  `FrozenStrictModel`; models with additional/different Pydantic behavior retain
  their custom configuration.
- Directly affected tests were adapted. Focused guards prove store connection
  and query access fail outside a managed context and work in writable/read-only
  contexts. Test doubles no longer hide incomplete config construction behind
  opaque casts/unused ignores. Operator test DB reads now enter the Backend
  store rather than its child DB directly.

#### Unresolved architecture finding — no change authorized

- `api.lifespan()` defines nested `project_record`, closes over the runtime,
  and passes it to `backend_store.writable(project_record)`.
- The store retains this behavior temporarily in mutable `_project_record`,
  typed only as `Callable[..., ...]`; append and startup replay silently depend
  on it being installed. The store imports multiple private `api.py` functions,
  while `api.py` injects the real projection behavior back into the store.
- `_project_readme_record` is stale terminology and an over-broad operation: it
  inserts every authoritative HTTP record, conditionally recognizes commits,
  performs post-commit validation, writes attempt projection/checkpoint rows,
  and owns transaction rollback/commit. Related stale names are
  `_validated_readme_record` and `_initialize_readme_authoritative_schema`.
- The Human Operator additionally rejected treating a renamed
  `_project_authoritative_record` as sufficient: the projector still begins
  from a generic `HttpRequestLogRecord`/route branch rather than transparently
  using the established Codex/commit record contract.
- Lifecycle ownership is split: `api.py` has the domain ASGI lifespan;
  `server.py` wraps it and starts/stops synchronous Flask IPC; IPC-only is
  managed directly in `server.main()`. `ipc.py` appropriately has no ASGI
  lifespan, but the current split leaves `server.py` short of being the single
  resource-lifecycle composition root.
- A possible redistribution using only current abstractions was discussed:
  configuration as immutable configuration/resources, Backend store as the
  physical replay/DB mechanism, and Backend context as owner of config + store
  + domain projection. This was not approved, and the Codex-record-contract
  objection means it must be reconsidered rather than implemented verbatim.

#### Verification at handoff

- Ruff on the latest directly changed production/tests passes when the known
  duplicate-definition `F811` is explicitly ignored.
- Full strict detour mypy checks 46 files and reports exactly one error: the
  duplicate definition of
  `test_authoritative_replay_recreates_byte_identical_detour_database` at
  `tests/backend/test_api.py:4488` and `:4545`. The active contract explicitly
  forbids removing or renaming either without separate approval.
- Focused Backend/IPC/config/server tests: 12 passed, one skipped because this
  execution profile forbids Unix sockets.
- Directly affected Dashboard context/cache tests: five passed.
- The replay determinism test was run separately. Both replay passes completed
  with the same projected validation logs, but raw DuckDB file SHA-256 values
  differed; the assertion failed. It also records an OpenAlex-key-dependent
  Pydantic rejection during each replay. No repair is authorized.
- Broader non-root/non-network run, with only the named replay test excluded:
  259 passed, 12 skipped, five deselected, one failed. The sole failure is
  `test_backend_api_availability_uses_short_fail_fast_timeout`, which asserts
  `BACKEND_AVAILABILITY_TIMEOUT_SECONDS < 1` while the protected value is `1`.
- `git diff --check` currently fails on trailing whitespace in the
  `FrozenStrictModel` docstring in `src/helpers/architecture.py`. This was
  detected during handoff and not edited because the request was to update
  WORK only.
- The prior Human Operator `pixi run elevate` result was 10 passed in 113.35s,
  with no skips. It predates the latest ownership/projection edits; rerun it
  after the architecture issue is resolved. The full production operator E2E
  has not validated the latest work.

#### Required next steps

1. Re-read `TASK.md` and this current contract before touching code.
2. Review the Codex session/commit/attempt contracts in protected architecture
   and `commit_event.py`, then present a concrete projection ownership/data-flow
   proposal to the Human Operator. Do not implement it without approval.
3. Preserve the contract's existing store/CAS/resource behavior while resolving
   the callback, stale README terminology, generic-record branching, and
   lifecycle ownership; stop if the required shape expands scope.
4. Request separate decisions for the duplicate replay test, physical DuckDB
   equivalence criterion, replay-time external/Pydantic validation, the timeout
   assertion, and whitespace-only source edit. None is implicitly authorized.
5. After approved implementation, repeat stale-symbol/direct-child-access
   greps, Ruff, full strict detour mypy, focused Backend/IPC tests, the configured
   suite, and Human Operator `pixi run elevate` plus the real operator E2E.

#### Worktree safety

- Preserve all existing staged and unstaged changes. Never stage, unstage,
  restore, reset, or pop a stash. Use `git status --short`, `git diff`, and
  `git diff --cached` read-only before editing overlapping files.
- The protected BDD directory remains excluded by Pytest/Ruff configuration and
  outside the active scope. It currently has a staged modification; do not
  touch it absent explicit Human authorization.
- Use `apply_patch` for edits and `pixi run -e detour-ai-augment` for every
  Python/test/lint command. Do not run or import `src.repl`.

## Historical implementation and audit log

Everything below this heading predates the handoff snapshot above. It is kept
only as dated evidence; it is not current status or authorization.

### Singular outerdict protocol rename

- Propagated the semantic distinction throughout the detour: the implementation
  is `AiAugmentSingularOuterDict`, its module is
  `ai_augment_singular_outer_dict.py`, and detour-owned identifiers and
  `QueryResponse` fields use `singular_outerdict` / `singular_outerdicts`.
- Bare `OuterDict` remains only where Backend API constructs and returns the
  original main-pipeline multi-namekey `OuterDict` used for card generation.
- Protected architecture and IPC declarations, production callers, and active
  tests were updated consistently. No compatibility alias or old serialized
  field was retained.
- Ruff and import checks pass. Focused IPC, Backend API, and Dashboard tests:
  185 passed, 3 skipped, 1 deselected. The deselected case is the separately
  identified stale duplicate authoritative-replay test.
- All seven browser E2E tests were also invoked here, but this execution
  environment skipped them because local sockets are unavailable; this is not
  counted as runtime validation of the browser boundary.
- Operator reran `pixi run elevate`; `logs/from_operator/elevate.log` confirms
  all seven browser E2E tests passed. The next real-socket IPC test failed at
  `_BackendDatabaseClient.available()`: Werkzeug logged `OPTIONS /query` as
  HTTP 200, but the client returned `False`. `available()` currently suppresses
  the underlying `OSError`/`HTTPException`, so the log cannot identify the
  precise client-side failure; its 0.25-second availability timeout is the
  leading explanation. Because the task uses `pytest -x`, the two subsequent
  appendwatch tests did not run.
- Operator removed the inappropriate `pytest -x` and reports the subsequent
  `pixi run elevate` completed with all 10 selected tests passing.

### Protected IPC completion — historical implementation snapshot

Approved narrow scope: repair the protected `ipc.py` move and downstream
callers; make `_build_query_response` the shared full/IPC-only assembler;
uniformly apply optional namekey selection to attempts, returned
outerdicts/commits, and run outcomes; avoid mutating context-owned outerdicts;
retain and correctly invoke `_full_dashboard_query_response_json_handler`;
then run focused and configured checks. No unrelated refactor is authorized.

Implemented within that scope:
- Protected IPC imports and API-owned references are wired; source Backend,
  Dashboard, active tests, operator tests, and excluded BDD imports now point
  to the protected module.
- `_build_query_response` is shared by full and IPC-only modes, uniformly
  filters run outcomes when a namekey is supplied, and copies selected
  outerdicts before attaching committed values. Its docstring now states the
  actual provenance, optional-filter, and connection-ownership contract.
- The full handler factory remains and is invoked; IPC-only calls the shared
  builder. Stale moved test seams were updated without changing behavior.

Verification so far:
- focused IPC: 7 passed, 1 sandbox Unix-socket skip;
- Backend API excluding one stale duplicate test: 132 passed, 2 skipped;
- complete non-root/non-operator feature selection with that duplicate
  deselected: 258 passed, 13 skipped, 4 deselected;
- Ruff/import checks pass for the moved IPC and active callers.

One unrelated pre-existing blocker needs explicit approval: `test_api.py`
contains two same-named replay-determinism tests. The later stale definition
shadows the current context-manager version, calls deleted
`detour_db_path`/`close_backend_detour_database` APIs, fails pytest, and causes
Ruff F811. Proposed action is only to delete the stale second definition at
the current lines 4426–4473, retaining the first current test unchanged.

### Revised protected `ipc.py` / `_build_query_response` review

- The revised `_build_query_response` correctly starts centralizing assembly,
  but its docstring does not match provenance or selection. The runtime context
  supplies configured source outerdicts; the separately passed connection
  supplies projected attempts, commits, and run-outcome records. The caller,
  not the context or builder, owns connection synchronization/lifetime. Keeping
  `conn` explicit is correct because full and IPC-only callers manage it
  differently.
- `namekey` is optional, so the contract is either one selected researcher or
  the complete population. Attempts and returned outerdicts/commits currently
  honor it, but `_run_outcome_records(conn)` returns every researcher's outcome
  records. Thus the body's most important behavior contradicts the docstring.
- The builder mutates `runtime.ai_augment_outerdicts` to attach committed
  innerdicts. It should construct returned outerdict copies instead, preserving
  the configured context as input and making query assembly repeatable.
- Proposed narrow shape: make `_build_query_response` the sole builder used by
  full and IPC-only paths; apply `namekey` uniformly to attempts, outerdicts /
  commits, and run outcomes; do not mutate context-owned outerdicts; document
  source-vs-projection provenance, optional filtering, and caller-owned
  connection lifetime.
- The broader WIP move still cannot run: relative imports point into nonexistent
  protected packages, downstream code still imports the removed source module,
  API-owned symbols remain unqualified, IPC-only calls undefined
  `_query_response`, and full startup passes the zero-argument handler factory
  where a one-argument handler is required. The identity factory should be
  removed and `_full_dashboard_query_response_json` passed directly; IPC-only
  should call `_build_query_response`.

No implementation was authorized or performed.

### Current protected IPC and `QueryResponse` review

- A Codex session does not map 0..1 to `QueryResponse`; `QueryResponse` is the
  aggregate envelope. One Dashboard `Run` should map to at most one session,
  but one session can legitimately have zero or more attempt records because a
  Pydantic/DuckDB rejection moves Backend to `RETRY` and permits another push
  from the same session. At most one of those attempts can be accepted.
- The serialized query envelope currently contains: every selected projected
  commit attempt (full pull record, full commit record, post-commit validation,
  optional submission, optional ground-truth innerdict); selected complete
  `AiAugmentOuterDict` objects (XLSX/SSN/DOCX sources, cohort metadata, and
  accepted committed innerdicts); and run-outcome HTTP records decoded as
  `RunOutcomeResponse`. This duplicates some commit, accepted-output, and
  ground-truth information across branches.
- Optional namekey filtering is applied to attempt records and outerdicts, but
  not to run-outcome records. The builder mutates runtime-owned outerdicts to
  inject queried committed innerdicts. `QueryResponse` has no acquisition
  metadata or cross-branch/session-cardinality validator, and its frozen shell
  contains mutable `AiAugmentOuterDict` instances.
- The human WIP move of `ipc.py` to protected is not yet runnable. The protected
  module first fails import because its relative `control_centre` import points
  inside `protected/src`, while `server.py`, Dashboard, and tests still import
  the removed source-side module. Ruff additionally reports unresolved names
  left by moving API logic into IPC. There are also direct call defects: the
  full-server handler factory is passed instead of called, and the IPC-only
  path calls undefined `_query_response` rather than the local query builder.
- No code was changed; these are review findings for the WIP refactor.

### Attempt reconciliation and variable projection under the proposed design

- `_AttemptReconciler` currently performs several unrelated jobs: validates
  consistency among attempt records and committed innerdicts, associates
  run-outcome responses, combines Backend attempts with Dashboard-owned runs,
  suppresses some duplicate rows, sorts history, and chooses each researcher's
  current lifecycle. Its `_AttemptView` is an exclusive union of a Backend
  attempt or a local `Run`, so it does not actually represent their association.
- Merely retaining this reconciler after making `CODEX_EXITED` terminal would
  be incorrect: local runs would no longer gain `accepted_commit_record_id`, so
  later queried attempts would not replace/match them. The authoritative join
  must use the already-durable Codex `session_id`, permit multiple Backend
  attempts for one session, and never guess associations for sessionless data.
- In the proposed architecture, the standalone `_AttemptReconciler` can be
  removed. `DashboardQuerySnapshot` should own strict validation and immutable
  Backend indexes by namekey, commit ID, and session ID. The Dashboard storage
  aggregate, which owns both that snapshot and the run journal, should expose
  researcher state by explicitly overlaying local runs on queried Backend facts
  via session ID. The responsibility remains, but becomes transparent behavior
  of the objects that own the data.
- `_VariableProjector` converts one researcher/attempt and the selected
  variable into grid values, including AI text, ground truth, footnotes,
  metadata, lifecycle, and action; it also synthesizes the never-attempted
  `READY` row. It holds no state and adds no useful ownership boundary.
- The standalone `_VariableProjector` can also be removed. Rich immutable
  researcher/attempt view objects can expose their own per-variable grid
  projection, with the selected variable and volatile runtime state passed
  explicitly. This keeps NiceGUI widget construction outside the snapshot,
  avoids replacement module-level helpers/globals, and leaves one direct path:
  stored query response + run journal -> researcher state -> selected-variable
  row.

No implementation was authorized or performed.

### `CODEX_EXITED` terminal-cycle verification

- Current normal events are `QUEUED -> STARTED ->` optional
  `REMOTE_PID_DISCOVERED -> SESSION_DISCOVERED -> ROLLOUT_DISCOVERED ->
  CODEX_EXITED`, followed by `_finalize_run()`'s optional `PUSH_ACCEPTED`, a
  run-outcome IPC POST, and `COMPLETED|FAILED|CANCELLED`. The proposed normal
  Control Centre cycle stops at the existing `CODEX_EXITED` comment and then
  gracefully winds down its processes.
- This is operationally viable because Backend lifespan shutdown waits for all
  authoritative accepted-push background tasks before closing replay log and
  DuckDB, and `_BackendSupervisor.stop()` waits for process exit. A later
  IPC-only query therefore sees the settled replay projection, provided Query
  IPC is allowed only after owned Backend cleanup completes.
- It does not work by deleting `_finalize_run()` alone. Today `CODEX_EXITED`
  still satisfies `Run.is_running()`, does not satisfy `Run.is_finished()`, is
  rendered as `RUNNING`, remains cancellable, and is marked `FAILED` as an
  abandoned run on Dashboard restart/shutdown. `Run` must treat it as a
  finished Control Centre fact without inventing a Backend-derived
  `run_outcome`.
- Current reconciliation cannot fill the result after a later query. It
  suppresses a Dashboard run only through `accepted_commit_record_id`, which is
  currently populated by `_finalize_run()`. The new reconciliation must join
  queried attempts to Dashboard runs by the already durable Codex `session_id`;
  accepted/rejected attempts then determine the displayed Backend result while
  the run journal remains unchanged at `CODEX_EXITED`. Multiple commits from
  one retrying session must remain one run with multiple attempt rows.
- With no matching queried attempt, the honest state is `CODEX_EXITED` / no
  Backend attempt in this snapshot, not automatically `FAILED`. A full query
  made after quiescent Backend shutdown can establish absence; a snapshot that
  predates exit cannot. Query snapshots therefore need their own acquisition
  identity/time, and the explicit button should remain unavailable during
  owned Backend cleanup.
- Queued cancellation can remain terminal `CANCELLED` because no Codex process
  will exit. Active cancellation naturally records `CANCEL_REQUESTED` then
  `CODEX_EXITED`; orchestration/startup/cleanup failures can remain explicit
  `FAILED` events. Normal completion no longer writes `PUSH_ACCEPTED` or a
  terminal outcome into the Dashboard journal.
- Removing current run-outcome POSTs outright would weaken the immutable audit
  contour. A commit snapshots rollout/report at push time, whereas the existing
  outcome record snapshots the final rollout after exit and is the only such
  capture when no push/commit occurred. To preserve the stated whole-session
  evidence goal without deriving lifecycle from Backend response, replace the
  outcome-labelled normal POST with a neutral durable `codex-exited` capture;
  wait for persistence but never use its response to mutate Run lifecycle.
  This is a separate replay/connector-format decision requiring approval.
- The resulting normal control lifecycle is hermetic from Backend *outcome*
  responses, but not literally from every Backend response: startup still uses
  health/readiness responses and Codex itself necessarily uses pull/push. The
  current readiness path also performs an authoritative `GET /pull` in addition
  to `/query`; only the latter was within the explicit request so far.

No implementation was authorized or performed.

## Current operator request — DuckDB extension ownership (2026-09-14)

Approved narrow scope only:

- `AiAugmentDetourDB` owns loading the ordinary `splink_udfs` database
  extension whenever it opens its connection, in both writable and read-only
  modes. Extension loading no longer depends on a Codex-match version.
- `AiAugmentBackendContext.detour_database()` only selects/enters the database
  mode; it no longer loads the extension or defines the misleading
  `CODEX_TOKEN_EXTENSION` name.
- `_build_query_response` receives only the runtime and optional namekey. It
  uses the already-open
  `runtime.pipeline_config.detour_db.connection`; callers establish the full
  synchronized or IPC-only read-only context without separately passing the
  same connection.
- Directly affected tests were adapted to the new owner and retain their prior
  behavior. No unrelated replay, query, lifecycle, or database policy change
  is authorized.

Verification so far:

- Focused ownership/IPC tests: 14 passed, 1 restricted Unix-socket skip.
- Active Backend API/IPC tests: 139 passed, 3 skipped, 1 known stale duplicate
  replay-hash test deselected.
- Ruff passes the changed production files and `test_api.py` when the known
  duplicate-definition F811 is excluded.
- Full strict detour mypy reaches only that same pre-existing stale duplicate
  test: one `no-redef` and two calls to its deleted DB-close API. Do not delete
  or repair it without separate approval.
- Focused strict mypy passes the four changed production modules. Literal stale
  searches find no `CODEX_TOKEN_EXTENSION`, context-owned extension loader, or
  `_build_query_response` call that passes a separate connection.
- The configured feature suite completed with 257 passed / 13 skipped / 3
  deselected and two failures outside this patch: the known duplicate replay
  test, and the existing UI timeout assertion requiring the configured value
  to be below one second while that value is exactly one second. No change was
  made to either unapproved contour.
- `git diff --check` passes. The approved implementation is complete; elevated
  browser/socket execution remains represented by the Human Operator's prior
  10/10 pass and was not rerun for this Backend-only ownership patch.
- While verification was running, the Human Operator changed the DB's writable
  context from direct object entry to `writable()`. Preserved that API,
  connected `AiAugmentBackendContext.detour_database()` to it, and updated only
  the directly affected open/close tests. Final active Backend API/IPC result
  after that integration is 139 passed / 3 skipped / 1 known stale duplicate
  deselected; focused DB ownership is 4 passed. Ruff, focused strict mypy, and
  `git diff --check` pass.

## Current operator request — unified Backend store aggregate (2026-09-14)

Implement only the approved aggregate shape, with
`ai_augment_backend_store.py` under the unprotected Backend data-model package:

- `AiAugmentBackendStore` composes the registered replay log and
  `AiAugmentDetourDB`; replay remains authoritative and DuckDB remains its
  disposable projection.
- The store alone owns their joint writable/read-only lifetimes, operation
  lock, replay synchronization/freshness check, append-fsync-project-checkpoint
  ordering, and managed projection connection capability.
- Remove the global detour DB lock, context-owned DB adapter, free
  synchronization contexts/functions, and direct production use of either
  child store or either filesystem path.
- Full mode opens the joint writable store; IPC-only opens the joint read-only
  store and fails if its projection is not current with the replay log.
- Preserve replay parsing, projection, checkpoint, append, extension loading,
  and failure semantics. Adapt only direct callers and active tests; the
  explicitly excluded/restored BDD file remains untouched.
- Added approved simplification: remove the anemic `AiAugmentResources`
  wrapper. `AiAugmentDetourConfig` directly owns the named frozen release-map
  and replay-log resources and exposes their immutable tuple through a regular
  `registered_resources` property. The validator constructs both resources,
  then the detour DB, then the Backend store from the existing replay-log/DB
  objects.
- Additional approved scope: replace raw `rollout_cas_dir` access with an
  unprotected, frozen `AiAugmentCAS` model. It owns temporary ingestion,
  hashing/line counting, conflict detection, atomic publication/fsync, and
  replay-time blob lookup/validation. The Backend store receives the same CAS
  object and no production caller constructs CAS paths directly.
- Additional approved scope: make `server.py` the sole composition root.
  `configure_runtime` moves there and returns one context without assigning
  process-global state; full API+IPC and IPC-only are both constructed from
  that explicit context. Delete `RUNTIME_CONFIGURATION`, its accessor, and the
  IPC-only lazy configuration closure.
- Implementation boundary: inject the runtime-bound projection callable once
  when opening the writable Backend store. Append/query operations then use the
  opened store without passing its owning runtime back into it; read-only IPC
  needs only the store's replay/projection freshness check.
- Additional approved refinement: remove the ambiguous store `healthy` state
  and the third `projection()` resource mode. Keep only joint `writable()` and
  `read_only()` lifetimes; writable operations that must be atomic with replay
  projection use the store's short-lived `threading_lock()` context.
- Additional approved query contour: `QueryRequest` is a strict, frozen
  Pydantic model in the unprotected Dashboard data-model package. Protected
  IPC exposes `handle_query_request(runtime, ipc_request) -> QueryResponse`;
  the Flask adapter alone parses HTTP into that request and serializes the
  response. Query-local attempt and run-outcome DuckDB reads are nested in the
  handler so no raw connection appears in top-level helper interfaces. Full
  mode invokes it under `threading_lock()` and IPC-only invokes it directly
  within the already-open read-only store.
- Human-added `src.helpers.architecture.FrozenStrictModel` is now the approved
  base for every detour model that previously repeated exactly
  `extra="forbid", frozen=True, strict=True`; preserve model-specific Pydantic
  configurations that add or differ in behavior. Literal and multiline grep
  must show no remaining copy of that exact configuration in the detour.

## Current operator report — IPC-only query crashes on persisted standardized attempt

Diagnosis only; no fix is yet authorized. The Human's `pixi run serve
--ipc-only` starts and answers `OPTIONS /query`, then fatally exits on the first
GET query while reconstructing a persisted `AgentRuntimeAttemptRecord`.

- This is not an IPC socket/startup failure. IPC-only deliberately opens the
  existing detour DB read-only and does not synchronize or reproduce it from
  replay. The crash begins in `_attempt_records` while parsing an already
  projected attempt for the query response.
- `_AgentRuntimeAttemptRecordJson.submission` is a union containing live
  `Submission` and `StandardizedSubmission` models. The plain branch correctly
  rejects the nine `standardized_value` fields as extras; the standardized
  branch reaches `AcademicInstitution.validate_institution`, whose Pydantic
  model validator performs live OpenAlex and ROR HTTP requests and requires
  `OPENALEX_API_KEY`. The IPC-only branch of the `serve` task exits before
  loading that key, producing the reported aggregate union error.
- Setting/exporting the key is not the correct fix. Querying immutable persisted
  records must not perform external validation. It would also make read latency
  and success depend on current network/API data.
- The supplied 11-line replay log reproduces the model failure directly: its
  second push has seven academic-institution objects, and direct standardized
  parsing without the key produces 45 validation errors headed by the same
  missing-key cause.
- The same flaw likely explains the previously observed very slow browser E2E.
  A query parses persisted attempt submissions once in the IPC Backend. The
  Dashboard then parses them once in `_QueryResponseJson` and a second time via
  `AgentRuntimeAttemptRecord.from_serialized_json`. For this accepted attempt,
  seven institutions times OpenAlex plus ROR times three passes permits 42
  needless external requests per query.
- Other persisted-state revalidation exists in `_derive_retry_obligations`,
  which reparses prior standardized submissions and likewise must not rerun
  external institution checks. The current retry push itself is separately
  parsed through the live validation path and should retain the intended live
  policy until the larger hermetic-replay design is corrected.
- The subsequently supplied CAS contains all three referenced blobs. Their
  actual SHA-256 digests, byte sizes, and line counts exactly match the two
  commits (411,209/96 and 490,726/129) and `/completed` terminal snapshot
  (510,548/147). The supplied 307-row release map also exactly matches the
  configured `a1cd6f...a5a7c` digest. Its initial directory mode was `0444`,
  which prevented traversal; only the owner traverse bit was added. The
  original replay log remains unchanged and read-only.
- A real isolated reconstruction was then completed against the authoritative
  source DB, supplied release map/log/CAS, and a fresh `/tmp` detour DB. In the
  current environment, the first attempt replayed as the expected evidence
  rejection. The second attempt did *not* reproduce its historical accepted
  result: lack of `OPENALEX_API_KEY` made current
  `StandardizedSubmission.model_validate_json` reject it at
  `pydantic_validation`, storing `submission=None`. Projection nevertheless
  checkpointed all 11 records, including the immutable `/completed` 200 record.
  The resulting projection therefore says both attempts were rejected while
  separately saying the run completed successfully.
- IPC query against that fresh projection succeeds precisely because replay
  erased the second standardized submission. It returns two rejected attempts,
  the `/completed` 200 outcome, 307 outerdicts, and 16,450,217 bytes of JSON.
  By contrast, the Human's production projection was made with live validation
  available and retained the accepted standardized submission; IPC-only then
  crashes while revalidating that persisted value without the key. Thus clean
  replay and read-only query disagree based solely on current credentials and
  external validation availability.
- Running the native full `pixi ... serve` task in this checkout also stops at
  its explicit launcher check because `.env` has no `OPENALEX_API_KEY`. Adding
  the key would conceal the read-path bug and make replay depend on live
  OpenAlex/ROR state; it is not a sound repair.

### Recommended repair boundary

- Immediate surgical fix: introduce an explicit persisted-data validation
  context for `AcademicInstitution` which performs all structural Pydantic
  validation but suppresses external OpenAlex/ROR rechecks. Use it only in
  `AgentRuntimeAttemptRecord.from_serialized_json`, the initial
  `_QueryResponseJson` parse, and prior-submission parsing in
  `_derive_retry_obligations`. Default/live `StandardizedSubmission` parsing
  must continue to run its current validation, and tests must prove the two
  paths remain distinct.
- Also remove the Dashboard's second attempt reconstruction pass: once the
  response DTO has been validated structurally, convert it once rather than
  serialize and parse each attempt again.
- Longer-term hermetic fix: remove network I/O from Pydantic construction,
  model external institution validation as an explicit live operation, capture
  its exact evidence immutably, and make replay consume that capture. The
  immediate context patch repairs read/query behavior but cannot make clean
  projection reproduce the historical accepted attempt: `_execute_attempt`
  itself currently reruns external validation while replaying the second
  commit. The projector must consume an authoritative captured validation
  result rather than silently checkpoint a newly rejected interpretation of a
  historically completed run.

### Exact proposed repair shape

- If only the immediate read failure is patched, add an explicit Pydantic
  persisted-data context whose sole effect is to return from
  `AcademicInstitution.validate_institution` before its OpenAlex/ROR calls.
  Default/no context remains the current live behavior. Pass that context from
  `AgentRuntimeAttemptRecord.from_serialized_json`, the first
  `_QueryResponseJson.model_validate_json`, and the historical submission read
  in `_derive_retry_obligations`. Add a conversion helper accepting an already
  validated `_AgentRuntimeAttemptRecordJson`, and use it from `QueryResponse`
  instead of serializing each model and parsing it a second time.
- That context switch is an interim patch only. In the preferred complete
  repair, remove `os.getenv`, mutable `OPENALEX_PARAMS`, and `requests.get`
  entirely from `AcademicInstitution`; all submission models become pure and
  every read path receives structural validation automatically. Add an
  explicit Backend institution validator invoked only while handling a new
  standardized push. It receives the key explicitly, uses request-local
  parameters, distinguishes invalid submitted references from operator/network
  configuration failures, and returns canonical captures of every OpenAlex/ROR
  response used.
- Replace the request-only synthetic `/commit` with a finalized synthetic HTTP
  exchange. Preserve its current request body (pull/push/session/rollout/report
  linkage) and add a strict response body containing the post-commit
  validation, normalized submission when available, ground-truth innerdict when
  accepted, canonical evidence assessment when available, the exact accepted
  replacement innerdict when accepted, and ordered institution-validation
  captures. The captures contain provider, submitted field/index path, key-free
  request target, response status, and bounded canonical response bytes plus
  digest; they must cover every non-sentinel institution reference exactly once
  and may contain no extras. The commit response is the sole authoritative
  outcome; the attempt/output/audit DuckDB tables are projections of it, not
  parallel authorities.
- Refactor `_commit_accepted_push`/`append_authoritative_record` so attempt
  evaluation occurs in an uncommitted DuckDB transaction, produces the
  finalized commit response, fsyncs that one self-contained commit line, then
  commits the projection/checkpoint. If log append fails, roll back. If the
  process dies after fsync but before DuckDB commit, startup can reconstruct
  from the finalized line. Materialized cards should be generated only after
  authoritative fsync/DB commit because they are replaceable projections.
- On replay, `_validate_projected_commit` structurally parses the push and uses
  only captured institution responses. It performs no environment lookup or
  network request, rebuilds the deterministic rollout/evidence/output tables,
  and requires its derived post-commit result to equal the committed response
  before advancing the checkpoint. Missing, malformed, mismatched, duplicated,
  or unused captures, or an outcome disagreement, are projection conflicts—not
  newly synthesized rejected attempts.
- Tests should prove: persisted attempt/query/retry reads make zero HTTP calls;
  malformed persisted structures remain rejected; live institution checking
  still occurs; a live run with fake HTTP responses followed by DB deletion,
  key removal, and network-disabled replay yields equal table/query projections;
  capture or outcome tampering fails before checkpoint advancement; and log
  fsync/DB-commit failure points never expose a committed projection without a
  complete authoritative commit record. No legacy commit parser or fallback is
  proposed.

### Whole-file replay determinism test (2026-09-13)

- No existing test performed two complete authoritative replays from JSONL,
  deleted the first detour database, and compared the two database-file hashes.
- Added that exact test using the supplied replay log, release map, CAS, and the
  real replay implementation. It closes the first database, hashes it, deletes
  it, reconstructs the same path from the same inputs, closes it, and compares
  the second whole-file SHA-256.
- The invariant currently fails. The first database hash was
  `782c3a0ae7381d634c311cb194241846c00d55d93d90b83fb0d1a466ccc86fdb`;
  the second was
  `67c50ba3de33c587801ff44d6fba29a2fb4f3c0cc582423d9c4953b76f480382`.
- A retained-file diagnostic established that the replayed projections are
  logically identical: all nine base tables have equal row counts and zero
  `EXCEPT ALL` differences in either direction. The equal-size files differ in
  only 63 bytes. Those bytes are the checksums and final eight payload bytes of
  four 256-KiB DuckDB overflow-string blocks, belonging to `assessment`,
  `baseline`, `codex.cite_text`, and the authoritative HTTP `record`. DuckDB
  1.5.1 does not serialize the unused block-tail bytes canonically; stale
  zero/`0xff`/text bytes differ between reconstructions, and the corresponding
  whole-block checksums consequently differ. The mismatch is therefore in the
  physical DuckDB representation, not in replayed table data.

## Current operator request — protected replay/DB ownership models

Implement only the agreed storage ownership refactor:

- Add a public frozen `AiAugmentRegisteredResource` base under protected
  Backend data models.
- Add `ReplayLogRegisteredResource`, directly inheriting that base and owning
  the replay-log descriptor, process lock, append lock, durable append, and
  context-manager lifetime. It derives its filesystem path through inherited
  `__fspath__`; it has no duplicate `path` field/property.
- Add `AiAugmentDetourDB`, owning the projected DuckDB path/connection and
  context-manager lifetime.
- Change protected AI-augment configuration fields to these models and replace
  downstream manual/global open-close use with `with ... as ...` ownership.
- Preserve existing replay, offset, hash, tail-repair, DuckDB extension, and
  read-only IPC behavior. Do not add unrelated integrity policy or replay
  changes. If existing tests expose a design issue, stop and request approval
  before expanding the patch.

### Implementation checkpoint

- Added the three protected models and changed configuration to expose
  `detour_db: AiAugmentDetourDB` and a `ReplayLogRegisteredResource`. Full Backend lifetime
  now directly enters both configured objects; IPC-only directly enters
  `AiAugmentDetourDB.read_only()`. Replay append is owned by the entered replay
  resource. The unauthorized `startup_complete`, `ExitStack`, separate
  `open_detour_database`, and `_backend_detour_database` adapter have been
  removed.
- Removed the production global DuckDB connection/path and replay-log
  descriptor/manual open-close functions. Only `AiAugmentDetourDB` opens the
  projected DuckDB, with both modes explicit; direct opens elsewhere are for
  the source database.
- Both prior approvals were resolved narrowly: the hash-enforcement test
  temporarily changes the fixture's mode for direct tampering, and the model
  preserves native DuckDB open exceptions without adding translation policy.
- Writable and read-only database contexts both return `AiAugmentDetourDB`.
  Source/detour path comparison is exposed by the model rather than by reaching
  through its path field. The operator test retains the model and no longer
  extracts a path or opens the projected database directly.
- `ReplayLogRegisteredResource` owns reads as well as locked durable appends.
  Replay parsing receives bytes from the open model; no active caller converts
  the replay resource back to `Path`. Tail repair and requested hash
  verification execute under its context lock without a copied resource.
- Removed the stale path-oriented adapters and unused open-error locale strings.
  The broad diagnostic now reports an API lifespan failure instead of
  mislabelling every post-startup failure as startup.
- Per operator authorization, the four remaining UI-test count names now use
  `completed`, matching the production lifecycle model.
- Literal stale-symbol searches are clean across active detour production and
  tests. The explicitly paused/excluded protected BDD file was restored
  unchanged at operator request and was neither adapted nor tested.
- Validation: strict detour mypy passed for all 43 source files; Ruff passed;
  focused ownership tests passed (10); Backend API/IPC tests passed (134, with
  3 skips and only the known physical DuckDB hash test deselected); UI unit
  tests passed (46); operator preflight passed (3); and the complete included
  non-root/non-network contour passed (253, 12 skipped, 5 deselected). The seven
  browser E2E cases were collected and skipped because no browser runtime is
  available in this environment. `git diff --check` passed.

### UI E2E browser selection (2026-09-13)

- UI E2E tests now launch the Google Chrome channel by default. If Chrome
  launch fails, the test failure explicitly directs the operator to rerun with
  `--playwright-chromium`.
- The single pytest opt-in affects both existing browser launch sites and uses
  Playwright Chromium by omitting the Chrome channel.
- Ruff and focused mypy pass, and pytest exposes the new option. The full
  opt-in UI E2E invocation collected all seven tests, but this environment
  skipped them before browser launch because local sockets are unavailable.
  A direct Playwright Chromium launch also confirmed that its separately
  downloaded browser executable is not installed in this environment.
- Final configured `test-detour-ai-augment` rerun passed: 254 tests passed, 13
  skipped, and 3 deselected. Its separate real-API check was skipped because
  `OPENALEX_API_KEY` is unavailable. The seven UI E2E cases were among the
  skips because this environment disallows local sockets.

### Operator-elevated socket tests (2026-09-13)

- Added a narrowly scoped feature task for the elevated contour. It runs
  the seven UI browser E2Es, the real mode-0600 Unix IPC test, and the two
  appendwatch socket cases that the current Codex permission profile skips.
- The task uses `script -q -e -c` so combined stdout/stderr is both shown live
  and captured under `logs/from_operator`; it
  preserves pytest's exit status and does not use `set -e`.
- Pixi recognizes the task and `git diff --check` passes. It remains for the
  operator to run outside this session's network-disabled seccomp policy.
- The first operator run exposed a test-harness failure: startup errors were
  treated as transient unavailability for 30 seconds, child output was omitted
  from the timeout, and pytest continued into the next E2E case.
- Narrow correction only: startup HTTP errors now fail immediately; timeout
  and HTTP-error handling
  terminates and drains the child so its complete captured output is embedded
  in the pytest failure; and this operator task uses `-x`.
- The second operator run stopped after the first failure in 7.02 seconds. It
  received no HTTP response and the child emitted no captured output before
  the three-second startup deadline, so there was no exception trace to attach.
- The failing E2E child uses the injected `BrowserController`, not production
  config/backend startup, so replay-log hash verification is not involved.
  Code inspection also shows a latent incompatibility: UI refresh calls
  `drain_notifications()`, which that injected controller does not implement.
  This mismatch is now patched with a no-op method on the fake.
- Focused Ruff and strict mypy passed; all seven UI E2Es collect and skip in
  the socket-restricted development environment; `git diff --check` passed.
- The first `script` quoting attempt was not executable because TOML consumed
  the inner quote escapes. Replaced it with the repository's established
  `'"'"'"'` shell-quoting pattern and ran the actual Pixi task end to end:
  output was visible live, the log was populated, and the task returned zero
  for the expected 10 socket-policy skips in this environment.
- Current failure diagnosis is two-layered. A fresh import of the E2E server
  module took 5.62 seconds and production Dashboard UI alone took 6.42 seconds
  here, so the three-second deadline expires before the child can answer or
  emit useful startup output. With the former longer deadline, the first page
  request reached the second failure: production `refresh()` calls
  `drain_notifications()`, but the cast-masked fake `BrowserController` lacks
  it. `0394e81` added both the method and call to production on September 10;
  static comparison finds this is the fake's only missing UI-used member.
- Reviewed `stash@{0}` read-only and did not apply/pop it. It is a later
  QoL/native-E2E refactor, not the repair vehicle for the authoritative seven
  existing tests. It also retains the three-second cold-dashboard deadline.
- Operator approved the repairs to the current seven-test contour: allow ten
  seconds for the measured six-second cold import/startup, retain ten seconds
  for orderly child shutdown/output draining, retain immediate HTTP-error
  failure, and add the fake controller's missing no-op
  `drain_notifications()` method. The QoL stash remains untouched.
- Focused Ruff, strict mypy, and `git diff --check` pass after the two test
  edits. All seven browser cases collect; this execution environment still
  skips them at socket creation, so actual pass/fail awaits the operator task.
- The next operator run reached browser launch without a Dashboard failure and
  stopped immediately because system Chrome is absent. Per operator direction,
  the task is now the feature-scoped `elevate`: `pixi run elevate` automatically
  selects the `detour-ai-augment` environment and opts into Playwright Chromium
  internally. Live/captured output is written to
  `logs/from_operator/elevate.log`.
- The exact `pixi run elevate` command was executed here, proving environment
  routing and shell quoting; all ten cases skipped only because this Codex
  profile forbids local sockets. Actual pass/fail awaits the operator rerun.
- The operator rerun exposed an unprovisioned browser: opting into Playwright
  Chromium selects its browser but does not install it. The expected
  `chromium_headless_shell-1234` executable is absent, so no browser test ran.
  This was deterministically knowable here and should have been handled before
  handoff. `elevate` now runs the non-root
  `python -m playwright install --only-shell chromium` inside the logged
  `script` command before pytest, joined by `&&`. An initially proposed
  `--with-deps` was removed at operator direction because this contour must not
  require sudo or install host OS packages.
- The non-root browser download succeeded. Launch now fails before any browser
  assertion because the minimal Ubuntu host lacks `libatk-1.0.so.0`. Direct
  `ldd` inspection finds exactly nine unresolved libraries: ATK, AT-SPI bridge,
  AT-SPI, Xcomposite, Xdamage, Xfixes, Xrandr, GBM, and ALSA. The proper
  non-root contour is to supply their conda-forge runtime packages in the two
  Linux target sections of the detour feature and expose `$CONDA_PREFIX/lib`
  to the downloaded browser through `LD_LIBRARY_PATH`. The operator approved
  and these manifest/task edits are now applied. Pixi parses the feature/task;
  lock solving cannot run under this profile because conda-forge DNS/network is
  blocked, so the network-enabled `pixi run elevate` operator run must resolve
  and install the added packages before executing the contour.
- The resolved non-root browser runtime works: Chromium launched and the first
  four UI E2Es passed. The fifth fails on a stale September 3 assertion that
  expects `attempt-1` in the commit-record-ID column; current production and
  the fake both put a UUIDv7 there. The final browser-contract test contains
  three more stale `attempt-1`/`attempt-2` assertions for the same pre-refactor
  convention. Per operator approval, the fifth test now validates UUIDv7 and
  the final test identifies its two attempt rows through their existing
  `ai-value-1`/`ai-value-2` projections.
- Post-edit validation: Ruff and the configured strict detour mypy contour
  pass (43 source files), the seven browser cases collect, stale `attempt-N`
  literals are absent, and `git diff --check` passes. This profile still skips
  browser execution at socket creation; operator `pixi run elevate` remains
  required for actual pass/fail.
- Final operator `pixi run elevate` result: all seven UI browser E2Es and all
  three elevated socket tests passed, with zero skips (10 passed in 113.35s).
  The non-root Playwright browser and conda library contour is therefore
  exercised end to end. The lockfile resolved both Linux targets, Pixi's
  feature/task dry run succeeds, and final `git diff --check` passes.

## Current operator request — focused `ui.py` ownership audit (2026-09-14)

Analyze, without changing production or test code, whether the same
behavior-owning/OOP refactor applied to Backend configuration is worthwhile for
the Dashboard. Focus on duplicated authorities, module-level mutable state,
anemic wrappers, and behavior placed outside the model that owns it; do not
recommend a broad file split merely because `ui.py` is large.

### Audit plan

1. [done] Inventory module functions/globals and large classes.
2. [done] Trace source/query persistence, run journal/queue, cards,
   application lifecycle, and Backend/Codex ownership.
3. [done] Cross-check concrete duplication and stale-state risks against
   adjacent models and tests.
4. [done] Return a prioritized, surgical proposal; make no code changes.

### Findings

- Highest-risk duplication is Dashboard data: the complete source outerdicts
  are cached under `SOURCE_DATA_STORAGE_KEY`, the complete query response is
  cached again under `BACKEND_DATABASE_STORAGE_KEY`, and the controller then
  maintains separate mutable researcher, namekey, ground-truth, attempt,
  committed-innerdict, and run-outcome projections. Applying a query response
  mutates only `committed_innerdicts` onto the separately sourced outerdict and
  discards the response's other source fields.
- Card reads form a second live-data contour. The IPC client performs an
  implicit namekey query, while the page and client each cache the rendered
  card independently. Page invalidation never clears the client cache, so an
  explicit refresh or rerun can still redisplay stale markdown.
- A nominal UI snapshot is not a read: each page's one-second timer calls
  `snapshot()`, which calls `refresh_idle_state()` and, while the owned Backend
  runs, performs and persists a full IPC query response. Multiple pages multiply
  this I/O. Page construction and explicit refresh also repeat availability
  checks.
- Run mutation/replay behavior lives in module functions while `Run` remains
  mostly anemic. The controller separately owns the full event list and replayed
  run map. The persisted queue cannot be mechanically deleted: a run is removed
  from it before waiting for Codex to become idle but still has `QUEUED`
  lifecycle, so current events alone do not identify queue membership.
- Application composition is held by mutable module globals (`SERVICES`, config
  path, lifecycle-configured flag) and free functions. `_ApplicationServices`
  duplicates references already retained by the controller. The `SERVICES is
  not None` startup branch mainly supports global-injection tests and would
  start an already-created controller again in a repeated production startup.
- `Final` lookup dictionaries remain mutable objects. More importantly, UI
  projection code imports the Backend API's private `_PushValidationError` and
  several implementation helpers, indicating a leaky boundary.
- The best focused sequence is: (1) one immutable QueryResponse-derived
  Dashboard snapshot, removing the source-cache/repository contour, hidden card
  IPC, duplicate card caches, and timer-driven full queries; (2) a `RunJournal`
  that owns event application/replay while preserving current queue semantics;
  (3) a locally constructed `ControlCentreApplication` owning composition and
  lifecycle, eliminating mutable runtime globals. Each should be separately
  reviewed. IPC-only auto-start and projection-freshness metadata are behavior
  changes and should not be smuggled into these refactors.
- Do not split `_ControlCentrePage`, `_BackendSupervisor`, `_CodexRunner`,
  `_AttemptReconciler`, or `_VariableProjector` solely because `ui.py` is large;
  these are substantially behavior-rich and cohesive at their current seams.
  Pure formatting helpers likewise do not benefit from artificial classes.

No production or test code was changed for this audit.

### Proposed explicit Dashboard operations

- Dashboard startup should restore only `AiAugmentDashboardStorage`; absent a
  stored query snapshot, the grid is empty and both probe groups begin as `not
  probed`. Page construction and its timer perform no network, SSH, IPC, source
  database, or query-response work.
- `Probe Backend` explicitly checks the full API and IPC health concurrently
  and updates two volatile statuses. It never calls `/query` or changes the
  stored Dashboard snapshot.
- `Probe AI Agent Runtime` explicitly exercises the exact production SSH route
  with a byte roundtrip, then runs the existing supported
  `/home/ai/.local/bin/codex login status` command over that route. It reports
  AIVM/SSH reachability separately from Codex authentication; if transport
  fails, authentication is `not checked`, not `unauthenticated`.
- `Query IPC` is the sole display-data hydration capability. It strictly parses
  `QueryResponse`, constructs a complete immutable `DashboardQuerySnapshot`,
  and asks `AiAugmentDashboardStorage` to replace the prior snapshot without
  merging. Construction must complete before any mutation; failure preserves
  both the stored and current snapshot. The click handler reports concise
  success/failure to that user while the server log records stages and the full
  exception.
- The one-second page timer may remain for local run/UI repainting, but its
  snapshot path becomes pure. Probe results should not persist across Dashboard
  restart because they immediately become stale.
- Remove current implicit full queries from Backend readiness, timer refresh,
  card rendering, and post-run-outcome refresh. Card rendering uses only the
  stored query snapshot.
- One material lifecycle dependency remains: `_finalize_run()` currently calls
  `/query` to decide whether the just-exited Codex session produced an accepted
  commit. If absolutely only the button may call `/query`, preserve run semantics
  through a new narrow Backend IPC completion-status port returning only the
  session's accepted commit ID/status; do not give the run controller access to
  `QueryResponse`. This endpoint is a separately approved connector change.
- Use capability separation: the page's explicit query action alone receives
  the query client; storage-backed display/controller code does not. Run-outcome
  POST and narrow completion-status capabilities remain separate from Dashboard
  hydration.

No implementation was authorized or performed.

### `CODEX_EXITED` terminal-cycle verification

- Current normal events are `QUEUED -> STARTED ->` optional
  `REMOTE_PID_DISCOVERED -> SESSION_DISCOVERED -> ROLLOUT_DISCOVERED ->
  CODEX_EXITED`, followed by `_finalize_run()`'s optional `PUSH_ACCEPTED`, a
  run-outcome IPC POST, and `COMPLETED|FAILED|CANCELLED`. The proposed normal
  Control Centre cycle stops at the existing `CODEX_EXITED` comment and then
  gracefully winds down its processes.
- This is operationally viable because Backend lifespan shutdown waits for all
  authoritative accepted-push background tasks before closing replay log and
  DuckDB, and `_BackendSupervisor.stop()` waits for process exit. A later
  IPC-only query therefore sees the settled replay projection, provided Query
  IPC is allowed only after owned Backend cleanup completes.
- It does not work by deleting `_finalize_run()` alone. Today `CODEX_EXITED`
  still satisfies `Run.is_running()`, does not satisfy `Run.is_finished()`, is
  rendered as `RUNNING`, remains cancellable, and is marked `FAILED` as an
  abandoned run on Dashboard restart/shutdown. `Run` must treat it as a
  finished Control Centre fact without inventing a Backend-derived
  `run_outcome`.
- Current reconciliation cannot fill the result after a later query. It
  suppresses a Dashboard run only through `accepted_commit_record_id`, which is
  currently populated by `_finalize_run()`. The new reconciliation must join
  queried attempts to Dashboard runs by the already durable Codex `session_id`;
  accepted/rejected attempts then determine the displayed Backend result while
  the run journal remains unchanged at `CODEX_EXITED`. Multiple commits from
  one retrying session must remain one run with multiple attempt rows.
- With no matching queried attempt, the honest state is `CODEX_EXITED` / no
  Backend attempt in this snapshot, not automatically `FAILED`. A full query
  made after quiescent Backend shutdown can establish absence; a snapshot that
  predates exit cannot. Query snapshots therefore need their own acquisition
  identity/time, and the explicit button should remain unavailable during
  owned Backend cleanup.
- Queued cancellation can remain terminal `CANCELLED` because no Codex process
  will exit. Active cancellation naturally records `CANCEL_REQUESTED` then
  `CODEX_EXITED`; orchestration/startup/cleanup failures can remain explicit
  `FAILED` events. Normal completion no longer writes `PUSH_ACCEPTED` or a
  terminal outcome into the Dashboard journal.
- Removing current run-outcome POSTs outright would weaken the immutable audit
  contour. A commit snapshots rollout/report at push time, whereas the existing
  outcome record snapshots the final rollout after exit and is the only such
  capture when no push/commit occurred. To preserve the stated whole-session
  evidence goal without deriving lifecycle from Backend response, replace the
  outcome-labelled normal POST with a neutral durable `codex-exited` capture;
  wait for persistence but never use its response to mutate Run lifecycle.
  This is a separate replay/connector-format decision requiring approval.
- The resulting normal control lifecycle is hermetic from Backend *outcome*
  responses, but not literally from every Backend response: startup still uses
  health/readiness responses and Codex itself necessarily uses pull/push. The
  current readiness path also performs an authoritative `GET /pull` in addition
  to `/query`; only the latter was within the explicit request so far.

No implementation was authorized or performed.
