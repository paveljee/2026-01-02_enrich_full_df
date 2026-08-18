# Tighten API — current handoff

## Purpose

This file contains only the live context needed to continue the current task after
compaction. Read this file and `tasks/tasks-20260731-tighten-api/src/TASK.md` in
full before doing anything else. Together they are the complete handoff; use only
focused repository lookups for implementation details.

## Operating constraints

- `src/TASK.md` is the immutable human specification. Do not edit it.
- Do not edit the frozen legacy SPEC, README, `.env.example`, sample runs,
  historical rollout/submission data, or ground-truth data.
- Every command uses `pixi run`. Git is read-only: do not stage, unstage, commit,
  reset, checkout, restore, or otherwise mutate Git state.
- Apply file edits through one complete, reviewable
  `pixi run apply_patch <<'PATCH' ... PATCH` command.
- Keep changes surgical. Do not add compatibility fallbacks for discarded
  schemas/databases and do not create new modules.
- Human-facing backend wording belongs in
  `backend/helpers/locale.py`. Tests belong in
  `src/detours/detour_ai_augment/tests`.
- Keep this handoff current whenever decisions, staged state, implementation
  state, or verification results change. Remove superseded material instead of
  accumulating history.

## Live objective and contract

- Current incident: startup reconciliation reports archived attempts, but a
  newly generated detour DB contains only the archive-inventory table. Accepted
  archived attempts therefore do not populate accepted-output storage and are
  absent from researcher cards. The required invariant is full recovery: if the
  detour DB is deleted while saved attempt directories remain, the next
  dashboard startup must rebuild all canonical detour tables/views and data
  identically to the deleted DB, in chronological attempt order and
  idempotently. Kenneth G. Cassman (draw 178; accepted attempt
  `20260813T140034_929598Z_35bd447bcd514323a31c1456c91983cf`) is the concrete
  regression. A mere manifest-inventory table is insufficient.
- Recovery has exactly two inputs: researcher/source context read from the
  authoritative main source DB without modifying it, and attempt-proper content
  scanned from archived attempt directories. Do not draw unrelated researcher
  rows or any other data from the main DB. Do not reconstruct DB rows from card
  ZIPs, DOCX, TXT, or other rendered outputs. A one-off DOCX inspection was only
  diagnostic and is not part of the design.
- Old manifests/attempts that do not satisfy the current recovery contract are
  simply invalid: do not add a legacy/discard category and do not replay them.
  Log the number of invalid attempts and replay only recent valid attempts.
  The current archive scan establishes the concrete boundary: 24 August 4
  attempts lack required rollout `line_count` metadata and are invalid; the
  other 105 match their directory ID and canonical rollout filename, size,
  SHA-256, and line count. Any later parse/replay failure is likewise invalid
  and must not be partially restored.
- Implement all current requirements in TASK, including exhaustive v1/v2 Codex
  evidence assessment, immutable run-scoped retry baselines, structured
  withdrawal, standardized retry submissions, persistence/rendering, dedicated
  roundtrip tests, and executable requirement-to-evidence mapping.
- A first push is validated with
  `backend/helpers/data_models/submission.py::Submission`. Its public description
  and example are the legacy plain contract: every evidence-bearing variable,
  including race/ethnicity/language/culture, has `value` plus
  `web_search_excerpts`; optional comments have only `value`.
- A first Pydantic-valid but evidence-invalid push establishes the immutable
  baseline. Every later push for that sanctioned run is validated with
  `pydantic_to_paste.py::StandardizedSubmission`; retry guidance says
  standardized values are now required and includes that schema plus the full
  standardized L. Fei-Fei example. Pydantic-invalid first pushes create no
  baseline.
- A first push that is fully accepted must be converted to a fully valid
  `StandardizedSubmission` before accepted-output writing. Supply explicit
  schema-valid NR placeholders for every standardized value; object-valued
  fields receive their required nested NR/NA placeholder object rather than a
  top-level scalar. The accepted DB write therefore always consumes the retry
  model, without widening its object-valued annotations.
- Retry immutability applies to raw field values and evidence as specified in
  TASK. Synthetic first-push NR values must not prevent a retry from supplying
  required standardized values after an evidence rejection.
- Each evidence-bearing variable gets a separate
  `ktp.ai_augment_*_standardized` DuckDB/card field immediately after its plain
  field. Store deterministic compact JSON for `standardized_value`; attach no
  duplicate footnotes. Hide only whole null/NA/NR standardized values in card
  display through a detour-local placeholder extension while retaining them in
  DuckDB.
- `pydantic_to_paste.py` remains the standalone schema shown to retrying agents.
  Ordinary academic-institution validation performs live OpenAlex/ROR checks;
  static fixture construction alone may bypass those checks with
  `model_construct`.
- Completion must run the marked live OpenAlex/ROR API test with the real
  `OPENALEX_API_KEY`. Control Centre execution must also pass that environment
  variable into the Lima/AIVM Codex process. Its guest-side roundtrip belongs in
  the established provision/deploy verification flow (not pytest) and must show
  a visible checkmark or cross without logging the secret value.
- Standardized scalar/list definitions remain typing aliases. Fixture-only
  `model_construct` assignments use their underlying validated-compatible
  scalar/list values directly; do not replace the aliases with Pydantic root
  models or add generic fixture machinery.

## Current repository and staged state

- Current HEAD: `64a06e2 detour ai augment: manually code two fixtures`.
- Current staged paths:
  - `pixi.lock`
  - `pyproject.toml`
  - `agent_runtime/README.md`
  - `agent_runtime/deploy.sh`
  - `backend/api.py`
  - `backend/helpers/data_models/mixin.py`
  - `backend/helpers/data_models/pydantic_to_paste.py`
  - `backend/helpers/data_models/submission.py`
  - `backend/helpers/data_models/submission_fixture.py`
  - `backend/helpers/locale.py`
  - `backend/helpers/vars.py`
  - `control_centre/dashboard/helpers/locale.py`
  - `control_centre/dashboard/ui.py`
  - `tests/test_api.py`
  - `tests/test_control_centre.py`
  - `tests/test_pydantic_to_paste.py`
  - `tasks/tasks-20260731-tighten-api/manifest.json.old`
  - this WORK file
- At the latest read-only status check, every changed code/config/test path
  listed above is staged. This WORK file alone has a current unstaged handoff
  update atop its staged version. Do not alter the index.
- `manifest.json.old` is operator-owned staged history of the former 39-line
  manifest. Preserve it.
- The operator added pinned `httpx2==2.12.0` beside retained `httpx==0.28.1`
  for Starlette's preferred TestClient backend and regenerated `pixi.lock`.
- The operator added `agent_runtime/README.md` with the intended macOS alias:
  the alias reads the real repository `.env`, exports `OPENALEX_API_KEY`, and
  directly invokes the repository `deploy.sh`.
- Accepted staged model changes currently make comments evidence-free through
  `CommentsSubmission`, add missing initial researcher-author evidence, add the
  retry author's ORCID/OpenAlex evidence, add the retry-example locale template,
  and derive standardized column labels/pairs from the evidence columns.

## Current implementation state

- The operator's latest fixture change preserves standardized typing aliases,
  assigns their scalar/list values directly under fixture-only
  `model_construct`, and retains the minimal non-generic `SubmissionFixture`.
  The previous alias-constructor import failure and generic-annotation mismatch
  are resolved.
- API/model tests now derive the standardized-only field name from
  `StandardizedFieldSubmission` while deriving plain value/evidence names from
  `FieldSubmission`; the former three-field unpacking failure is resolved.
- Fresh focused model verification: 22 passed, 1 `real_api` test deselected.
- The API now selects plain versus standardized validation from the persisted
  sanctioned-run baseline before parsing the body. Raw retry obligations no
  longer freeze standardized values. Every accepted write receives a
  `StandardizedSubmission`; a successful first submission is converted with
  explicit schema-valid placeholder models/values.
- The output schema interleaves each plain evidence field with its derived
  standardized column. Accepted rendering stores compact JSON standardized
  values without footnotes, and card-only copies hide whole null/NA/NR values.
- Fresh focused API verification: 71 passed, 1 intentionally skipped. This
  includes the current nine-field July E2E and archived Haanen assertions over
  its original 22 evidence items (21 exact, one near) while supplying the newly
  required field separately for current-schema validation.
- The dedicated successful-first-push conversion test is now added and passes;
  it proves raw values/evidence are retained and every standardized field gets
  the explicit schema-valid initial placeholder.
- The existing real July TXT/DOCX roundtrip now also proves plain/standardized
  schema adjacency, compact JSON persistence, preserved innerdict order,
  placeholder hiding, visible object-valued standardized fields, and absence of
  duplicate standardized footnotes. Both parametrized cases pass.
- A sanctioned real-July rejection/retry roundtrip now passes. It proves the
  first evidence-invalid plain push creates exactly one immutable baseline/audit,
  exposes the standardized retry contract, rejects a later plain payload at
  Pydantic validation, and materializes no accepted row, card, or response file.
- Control Centre already writes a mode-0600-style remote environment file with
  an exported `OPENALEX_API_KEY`, sources it in the remote exec command, and
  passes the key to the backend process. Existing focused tests cover command
  construction without revealing the key. `agent_runtime/deploy.sh` now adds a
  secret-safe guest roundtrip to its established `verify_instance` flow: it
  writes the same env path over SSH, sources it in AIVM, compares only SHA-256
  digests, verifies mode 600, and reports explicit checkmark/cross status.
- `deploy.sh` now follows that alias contract: it has no self-install/copy mode,
  resolves provision and appendwatch directly beside the repository script, and
  requires the alias-exported real key before any Lima deletion or creation. It
  does not parse or source dotenv itself. Shell syntax and the absent-key early
  failure path pass locally.
- The operator subsequently ran the deployment verifier on macOS and confirmed
  that the actual `OPENALEX_API_KEY` AIVM roundtrip passes with the success
  checkmark. The operator then reran the complete deploy/provision flow through
  the documented repository alias and confirmed every check is green, including
  the actual OpenAlex-key environment roundtrip.
- The `dashboard` Pixi task now reads `OPENALEX_API_KEY` from the repository
  `.env` into the Control Centre process, matching the operator's deploy alias
  without weakening `RuntimeConfiguration`'s required-environment check. This
  was verified non-interactively by instantiating the real
  `RuntimeConfiguration` in the detour environment; it completed successfully
  without printing the secret. The interactive launch itself was denied before
  execution by the command harness.
- The missing language variable was traced to the authoritative
  `DOCX_TO_AI_AUGMENT_COLUMNS` mapping from which the Control Centre derives
  `VARIABLE_SPECS`. The mapping now includes
  `ktp.table_1_race_ethnicity_language_culture`; ground-truth completeness uses
  the main pipeline's existing optional-DOCX-column set so an empty value does
  not disqualify a ground-truth row. Focused variable-registry coverage passes.
- The marked live OpenAlex/ROR pytest initially skipped because its test-local
  repository root incorrectly used `parents[1]`; this was surgically corrected
  to `parents[4]`, matching the other detour tests. The explicit `-m real_api`
  run now passes against both live services (1 passed in 1.21s).
- A fresh full detour run collected 159 tests. All API tests, including the new
  conversion/July retry/persistence roundtrips, passed; the intentionally
  disabled multiple-match test skipped; and the prior Starlette/httpx warning is
  absent under `httpx2`. The run exposed five failures in the real-config Control
  Centre tests. Supplying the established fake key fixed four. The operator has
  now deleted the stale detour DuckDB that caused the remaining real-card failure
  and will regenerate it de novo; do not add migration or compatibility logic.
- `pixi run lint` is green: Ruff formatting/linting and Mypy all pass.
- A final `pixi run lint` after the pyproject/test adjustment is also green, and
  both staged and unstaged diff checks pass.
- `pixi run git diff --cached --check` passes.
- Deleting the detour DuckDB revealed that the persistent run journal can still
  make archived attempts visible in the dashboard. Dashboard startup now scans
  complete `submissions/attempts/*/attempt.json` manifests in ascending canonical
  attempt-ID order and stores each exact manifest JSON text in a dedicated detour-DB archive
  inventory keyed by attempt ID. Missing rows alone are inserted; repeated startup
  is idempotent and logs inserted/discovered counts plus the source directory.
  The focused chronological/idempotent roundtrip passes, and all 129 current
  real manifests validate against the inventory model without touching the
  deleted operator DB.
- The exact `pixi run pre-commit 2>&1` contour has now been run. Ruff, Mypy,
  default tests, explicit main-pipeline real-API tests, and all non-AI detours
  passed. The AI-augment run produced 158 passes, one intentional skip, and two
  failures: one stale test duplicated superseded locale wording, and the
  real-database card test found no accepted attempts in the freshly regenerated
  empty detour DB. The browser line-spacing assertion now passes. The stale
  wording assertion has been removed rather than duplicating the centralized
  human label in a test; focused verification remains to run.
- `test-detour-ai-augment-root` now keeps its complete suite invocation and then
  explicitly invokes the marked live OpenAlex/ROR test by node ID with
  `-m real_api`, following the repository's established explicit real-API test
  contour. The full suite's copy of that live test passed, but the explicit
  second invocation was not reached because the DB-backed test failed before
  the shell `&&`. Both the repaired focused OpenAPI example test and the exact
  explicit `-m real_api` OpenAlex/ROR node have now been run directly in the
  detour environment and pass (one pass each). Rerun the whole task after the
  operator's regenerated DB contains accepted data.

## Next actions

1. Determine whether current saved attempt artifacts contain every input needed
   to replay all DB mutations exactly. Then replace inventory-only
   reconciliation with canonical full-DB reconstruction/replay, adding focused
   deletion/rebuild identity, chronological/idempotent, and Cassman-card
   roundtrip coverage.
2. Rerun the complete detour suite and `pixi run pre-commit 2>&1` with no
   deselection; the real-card test should pass from reconciled accepted data.
3. Rebuild `build/AGENTS.md`, `build/SPECS.ipynb`, and `manifest.json` under the
   Makefile's atomic requirement-to-evidence rules, then run
   `pixi run --frozen make validate` from the task directory.
