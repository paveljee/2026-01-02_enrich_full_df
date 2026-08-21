# Tighten API — current handoff

## Operating rules

- Read this file and `tasks/tasks-20260731-tighten-api/src/TASK.md` in full
  immediately after every compaction; together they are the complete context.
- Keep this file current and standalone, replacing superseded content rather
  than retaining a progress diary.
- `src/TASK.md` is human-owned. Do not edit it, the frozen legacy SPEC, README,
  `.env.example`, sample runs, historical submissions/rollouts, or ground truth.
- Run every command through `pixi run`. Git is read-only. Apply edits only with
  a complete `pixi run apply_patch <<'PATCH' ... PATCH` command.
- Never remove or alter inline comments marked as signed off by the human.
- Put ad hoc investigation artifacts under the repository's `./tmp`, never the
  filesystem-root `/tmp`, so the human can inspect them easily.
- Verify only with `pixi run pre-commit 2>&1`; operator tests remain a separate
  explicit contour on the operator machine.
- Keep production changes surgical. Human-facing backend wording belongs in
  `backend/helpers/locale.py`; detour tests belong under
  `src/detours/detour_ai_augment/tests`.

## Current objective

Before creating the interface-owned BDD pilot, repair and operator-verify the
original
`src/detours/detour_ai_augment/tests/test_e2e_operator.py::test_complete_dashboard_aivm_codex_push_db_and_card_workflow`.
Preserve its real isolated-runtime, dashboard, Chrome, Lima/AIVM, Codex,
accepted push, DuckDB, researcher-card, and restart contour, but replace its
removed attempts-directory, manifest, run-journal, callback, `ControlSnapshot`,
and `source_key` dependencies with the current authoritative replay JSONL,
control-pull projection, and `ktp.namekey` contract. Prompt the human operator
to run the exact node once it is ready. Do not create the BDD feature/test until
that original node passes.

After operator confirmation, add one whole-feature Gherkin file and one
adjacent pytest-bdd module under `tasks/tasks-20260731-tighten-api/var`.
The composed node keeps the exact behavioral name
`test_e2e_operator_bdd.py::test_complete_dashboard_aivm_codex_push_db_and_card_workflow`,
which is also the shared tag on every participating Scenario. Add a detour Pixi
task for the pilot. Declare all 19 TASK interfaces as Rules, populating only the
scenarios traversed by this accepted-run contour.

Each populated Rule owns its scenarios, so every Scenario subject is that
interface's owning node. All participating nodes outside the interface are
named in Given steps. Every participating Scenario carries the exact test-
address tag. Steps should refer only to real, vetted Python objects wherever
possible, including inherited `AiAugmentDetourConfig` fields, and use custom
pytest-bdd parsing plus `target_fixture` phase outputs so later Given steps
consume earlier Then states. A deterministic adapter composes the tagged
interface scenarios into one pytest node; the Pixi task invokes it. This is a
real corrective pilot: fix concrete code defects encountered in its contour,
but make no unrelated refactors.

## Canonical researcher/source vocabulary

- `SourceKey` in the main data model identifies provenance: one
  `RegisteredResource` plus one typed fragment. Its persisted components are
  carried inside an innerdict as `ktp.filename`, `ktp.fragment_type`, and
  `ktp.fragment`.
- `KTP_NAMEKEY_COL` (`ktp.namekey`) is the researcher grouping identity: the
  canonical JSON serialization of `ktp.first_name` and `ktp.last_name`.
- `KTP_INNERDICT_JSONLINES_COL` (`ktp.innerdicts`) stores zero or more JSONL
  source-fragment records grouped under one `ktp.namekey`. The read-only main DB
  has 307 distinct namekeys, and a single namekey can own many XLSX/DOCX/SSN
  innerdicts.
- Older detour internals and legacy prose sometimes call the serialized
  researcher namekey a `source_key`; do not propagate that conflation into the
  new HTTP contract and never invent `ktp.source_key`. New control-boundary
  researcher identifiers are namekeys and use the authoritative
  `KTP_NAMEKEY_COL` definition where a wire/column key is required.

## Required target contract

- Backend API exclusively owns one append-only JSONL and the detour DuckDB,
  including every detour-DB read/write and every authoritative-log write.
  Dashboard and agent runtime access neither directly. The dashboard owns its
  read-only main-DB connection and Lima/deploy reads, derives the 307-row source
  population and ground truth there, and sends/observes durable run state only
  through authenticated backend control push/pull.
- The JSONL contains literal schema-V2 `HttpRequestLogRecord` entries for every
  dashboard sanction push, public submission push, and backend-private control
  commit exchange. Pulls are read-only queries and are not logged. A public
  submission and its private PUT commit are one transaction; the private commit
  body carries appendwatch and all other replay metadata without exposing it to
  the public client.
- Rollout snapshots are the only large archived files. Store them in a
  SHA-256-addressed CAS; all other replay data belongs in typed HTTP bodies.
  `rollout_cas_dir` is always a required `config_ai_augment.json` value; the
  backend must fail configuration validation when it is absent and must never
  define, derive, or guess that path elsewhere.
- JSONL file order is canonical. DuckDB is an ephemeral projection rebuilt from
  the read-only main source DB, the authoritative log, and verified CAS blobs.
  No directory scan, cross-log merge, UUID ordering, or timestamp ordering may
  reconstruct state.
- Startup validates the configured
  `detour_ai_augment_backend_api_replay_log` `RegisteredResource`, repairs only
  an incomplete final JSONL line only after explicit operator confirmation, and
  replays in line order. Refusal or unavailable input leaves the log unchanged
  and fails startup. A projection may be
  behind and catch up; disagreement with an already projected prefix or an
  unverifiable CAS reference fails startup loudly. A projection failure after a
  committed log append makes the backend unhealthy and fail-closed until repair.
- Guard the data directory/log with a process-level single-writer lock so a
  second backend refuses to start.

## HTTP/state semantics

- There are five endpoint contours: dashboard sanction push/status pull, public
  annotation push/task pull, and an unmounted backend-only PUT commit endpoint.
  The commit is invoked through an in-process HTTP/ASGI transport and cannot be
  reached through Uvicorn. Its request and response remain literal HTTP fields.
- One global non-waiting command gate covers both pushes. A concurrent push gets
  an immediate logged BUSY response; pulls remain readable and tolerate the
  pre-commit or post-commit state.
- A successful internal push idempotently establishes exactly one active
  sanction. External pull repeatedly returns that task; after a failed commit it
  returns the same task with public retry guidance. A correct external push and
  commit consume the sanction. Subsequent public pull uses the existing no-
  sanction 503 configuration response until a human sanctions another run.
- Both push contours carry stable idempotency/correlation identity. Retrying an
  already committed request cannot duplicate a transition.
- Dashboard sends an internal push normally but treats internal pull/status as
  truth. Agent instructions similarly require external push followed by public
  pull polling; HTTP push delivery is notification, not the commit mechanism.
- Push routes use finite buffered JSON responses, not streaming responses.

## Commit and failure invariants

- Middleware structurally captures complete literal exchanges for sanction push,
  public push, and private commit. The private commit is durably appended and
  projected before public push can return. Once the public response is complete
  and ready to send, the public push exchange is appended as audit without
  duplicating the committed transition. Canonical line order is therefore
  always private PUT commit before its corresponding public POST push.
- Authoritative commit order is: validate/calculate response and next state;
  append complete HTTP record; fsync (commit); apply DuckDB/state projection;
  send response. Do not irreversibly mutate domain state before the JSONL commit.
- Crash before append commits nothing. A partial final line is truncated to the
  prior newline at startup. Crash after fsync is committed and replay catches up
  DuckDB. Crash after projection but before response remains committed and is
  discovered by polling/idempotent retry.
- JSONL append errors cannot return success. DuckDB failure after JSONL commit
  cannot roll back the transaction and must make the backend unhealthy. Client
  timeout does not imply failure. Requests that never reach the ASGI application
  are outside the logging boundary.
- Every internal backend failure exposed to the public client uses exactly the
  existing `CONFIGURATION_ERROR_DETAIL`; no other internal wording may leak.
  Operator-facing server logs are separate: they identify the concrete route,
  stage/gate/line, and underlying cause granularly and never tell the operator
  to contact the human operator.

## Shared HTTP model state

- `HttpRequestLogRecord` is one strict model with schema versions 1 and 2.
  Main-pipeline/OpenAlex producers remain exact schema V1 and historical logs
  retain their original 13-field wire contract.
- V2 declares optional `port`, `coerce_schema_v1`, and
  `ready_to_respond_at_unix_usec`. V1 rejects these keys on input and omits them
  on serialization. Native V2 preserves supplied values and defaults them to
  null/false. Opt-in V1 coercion first validates the common projection strictly
  as V1; an absent response-ready field then receives the normal null V2 default.
- Detour logging is native V2 and does not use coercion. TASK now requires the
  backend middleware to populate `ready_to_respond_at_unix_usec` because it logs
  responses the backend is about to send. These server-side records always set
  `received_at_unix_usec` to null because the backend is sending, not receiving,
  the recorded response.
- Focused shared tests prove V1 rejection/serialization, V2 optional ports,
  IPv6/default/local ports, V2 schema exposure, coercion, and non-null
  response-ready JSON roundtrip.

## Current implementation state

- `api.py` now has only the new backend-owned contour: required config-sourced
  `rollout_cas_dir`, operator-confirmed tail repair, process locking, typed
  control/attempt/commit models, one transactional record projector, pure-ASGI
  buffered schema-V2 logging middleware, public/control push-pull routes, and the
  unmounted private commit app. The old manifest/attempt-directory restore,
  dashboard callback, unsanctioned sample-row fallback, and renamed/dead legacy
  routes have been deleted outright; do not reintroduce compatibility paths.
- The dashboard boundary has now been converted to authenticated backend
  control push/pull. `ui.py` no longer owns a run journal, detour database,
  archive reconciler, local sanction plane, researcher-card renderer, or
  backend-facing NiceGUI callback endpoints. It intentionally retains the
  read-only main-DB `SourceRepository` and Lima/deploy reads. Backend control
  snapshots supply run events, attempts, accepted output, sanctions, and lazily
  requested card Markdown; the UI keeps its source population/ground-truth
  reads, live queue/process handles, and caches.
- Backend startup readiness now requires both OpenAPI and a valid authenticated
  control pull. A public pull is additionally probed after sanctioning, before
  the Codex run is allowed to proceed.
- A repository/DB audit established that the detour had conflated researcher
  namekeys with provenance source keys. The new backend models and processing
  path are currently being renamed to `namekey`; `ktp.source_key` was removed
  from the control query and `KTP_NAMEKEY_COL` now supplies the query alias.
  Active backend and dashboard code now consistently uses `namekey` and
  `KTP_NAMEKEY_COL`; the retry-baseline database column was also corrected from
  `sourcekey` to `namekey`. Remaining old terminology is confined to tests that
  still assert the removed architecture and must be replaced, not accommodated.
- The latest `pixi run pre-commit 2>&1` passes Ruff and reaches mypy. The active
  production modules, `test_e2e_operator.py`, and the migrated real-browser
  `test_control_centre_e2e.py` are mypy-clean. Mypy stops on 170 stale-contract
  errors confined to `test_api.py` and `test_control_centre.py`: removed
  manifests/attempt directories, callback endpoints, local journal/control
  plane, and obsolete source-key tests. Replace those stale tests with
  authoritative-log and namekey/control-boundary roundtrips rather than
  restoring aliases or compatibility code.
- Existing appendwatch, evidence matching, retry-baseline, and researcher-card
  behavior remains required inside the new transaction/replay boundary.
- The human explicitly removed the AIVM workbook/prompt contour after the
  current TASK text was written. Purge `/home/ai/workdir/WORKBOOK.md`,
  `/home/ai/workdir/PROMPT.md`, host-workbook initialization/synchronization,
  workbook commit snapshots, and replay materialization. The Control Centre
  passes only the vetted Backend OpenAPI URL directly to Codex; do not retain a
  compatibility field or branch for workbook data.
- Operator-marked tests remain an explicit separate contour.
- Operator fixture setup probes AIVM liveness before guest-dependent checks.
  On a reuse run, a stopped/unreachable instance prompts the operator to start
  it; `--yes` starts it noninteractively, refusal fails clearly, and tests never
  delete the instance. The instance remains running after the contour. The
  separate `deploy.sh` stop-after-deploy and optional post-test stop prompts
  recorded in `var/HUMANS.md` remain pending lifecycle work.
  Reuse runs source the authoritative `ai`-owned
  `/home/ai/workdir/.openalex.env` inside Lima and export that value only into
  the test/dashboard process. A host `OPENALEX_API_KEY` is required only when
  the operator elects to redeploy; deployment is followed by the same guest
  roundtrip. Stopped AIVM, missing guest key, and inactive appendwatch have
  separate setup errors.
- The human restored the pytest-bdd dependency in project configuration; leave
  it in place, but do not add the BDD pilot files until the original accepted-
  run operator node passes.
- The selected accepted-run operator test now uses a temporary authoritative
  replay JSONL, rollout CAS, and reconstructed DuckDB. The same test module
  contains no active attempts-directory, manifest, journal, callback, or
  `source_key` branch. Sanctioned pull, failure persistence, DB reconstruction,
  signal chaos, and accepted-run/restart scenarios now use the replay-log
  contour. Three useful archive-era scenarios are explicitly preserved as
  commented-out tests with their original names and assertions; do not delete
  them, and adapt them to authoritative replay fixtures after the accepted-run
  node is proven.

## Immediate implementation sequence

1. The operator rerun proved the guest-key/lifecycle correction and then exposed
   a durable action failure: the button remained `QUEUE` for 30 seconds. A real
   backend/control-client probe under repository `./tmp` identified the cause:
   decorator-style FastAPI middleware received Starlette's private
   `_StreamingResponse` and crashed on `response.body` for every control push.
   The middleware is now a pure ASGI wrapper that buffers the request, captures
   the untouched finite response messages, commits the complete HTTP exchange,
   and only then forwards those messages. Three upstream layers are green: a
   focused middleware regression; an actual FastAPI control-push -> JSONL ->
   DuckDB -> control-pull roundtrip that deletes and rebuilds the DB from replay;
   and the real NiceGUI/Playwright browser contract, including `QUEUE` ->
   `CANCEL` while preserving UI state. All three focused regressions pass
   together. The repository gate passes Ruff and stops only on the 170 known
   stale-test mypy errors documented above. Ask the operator for one rerun of
   the exact accepted-workflow node. Keep the positive
   `QUEUE`/`RERUN` -> `CANCEL` and `CANCEL` -> `RERUN` assertion. Operator tests
   retain merged dashboard stdout/stderr and tee every line live; the dedicated
   Pixi task uses pytest `tee-sys`.
2. Only after it passes, add the whole-feature `.feature`, adjacent BDD test,
   deterministic tagged-scenario composer, and detour Pixi pilot task.
