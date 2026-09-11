# AI augment production-preparation workbook

## Objective

Work with the Human Operator to prepare the AI-augmentation detour for
production, using its `README.md` lifecycle as the authoritative contract.
Current concrete issue: investigate and repair the `pre-commit-operator`
workflow based on the Human Operator's captured logs.

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

- Loaded the task, `config.repl.json`, `src/repl.py`, the complete authoritative
  detour README, and the complete prior-task handoff.
- Prior handoff reports the non-BDD suite at 205 passed / 47 skipped / 3
  root-only deselected, with real operator and dashboard smoke contours left
  for the Human Operator.
- Lifecycle contract includes one HCR per Backend run; append-only rollout
  monitoring; replay-log-first event persistence; Backend-owned projection and
  detour DB; post-commit model/rollout/appendwatch validation; follow-up retry
  pulls; terminal 410 pull; archival run-outcome capture; and Control Centre
  orchestration/recovery through Backend IPC.
- Worktree baseline was clean before this workbook was initialized; currently
  only this `WORK.md` is modified. Signed-off comments were inventoried and
  must remain untouched.
- `src.repl --new` parses `PipelineConfig`, opens the configured DB through
  `PipelineManager`, resets schema/state after confirmation, creates a session,
  then transactionally runs the ten registered steps from resource registration
  through card rendering. Its prohibited command has not been run or imported.
- Main-pipeline data flow was traced: XLSX population/name/economy sampling
  builds the outerdict stub; XLSX, DOCX, and SciSciNet matching materialize the
  three JSONL innerdict tables; card building materializes eligibility flags in
  `card_partitions` before rendering outputs.
- Opened only `data/scisci_process.duckdb`, explicitly with
  `duckdb.connect(..., read_only=True)`. Persisted source contract is healthy:
  `xlsx_innerdicts` 307/307 rows/namekeys, `docx_innerdicts` 307/307,
  `ssn_innerdicts` 304/304, union 307, `card_partitions` 307/307. All serialized
  namekeys/innerdicts parsed through production helpers. Draw multiplicity is
  302 single-draw + 5 double-draw, matching the detour invariant.
- Now inspect the production detour and tests before asking for the first
  concrete operator contour/failure.

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
- Current `HEAD` is `8cd9c11`, including the completed private-header patch.
  The worktree was clean before recording the current test investigation.

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
