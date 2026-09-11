# Tighten API — current work

## Authority and constraints

- Follow `tasks/tasks-20260731-tighten-api/src/TASK.md` and the authoritative
  `src/detours/detour_ai_augment/README.md`.
- Git is read-only. Use `apply_patch`; do not stage, unstage, restore, reset,
  apply, or pop a stash.
- Run every command through `pixi run -e detour-ai-augment`.
- Do not touch the main pipeline database or invoke `src.repl`.
- Preserve all Human Operator edits and signed-off comments. Add no migration,
  compatibility, alias, or legacy behavior for superseded contracts.
- Complete production code before touching tests. The Human Operator has not
  authorized the parked test-fix pass or operator execution.
- `protected/` may be edited only deliberately and with elevated scrutiny.

## Completed context and source-population pass

- Added these exact architectural contracts:
  - `BackendComponent.ContextProperty`: `pipeline_config`,
    `configured_namekey`, `ai_augment_outerdicts_factory()`, cached/computed
    `ai_augment_outerdicts`, and `configured_ai_augment_outerdict()`.
  - `ControlCentreComponent.ContextProperty` inherits the Backend context
    contract and adds `openalex_api_key` and `lima_configuration`.
- Typed both outer-dict collections and the Backend lookup result through
  `BackendComponent.ControlCentrePort.AiAugmentOuterDictProperty` in
  `architecture.py`. Concrete Pydantic implementations retain concrete runtime
  types and carry explicit `@implements[...]()` checks.
- Moved both concrete context modules from `protected/src/...` to the matching
  unprotected `src/...` paths.
- Removed the monolithic Control Centre `load()` method. `create_services`
  constructs `AiAugmentDetourConfig` once; context values are implemented as
  focused fields or cached/computed properties. Preserve the existing
  NiceGUI source-data cache path.
- Contexts do not duplicate detour DB, replay-log, CAS, release-map, source
  DB, timezone, or related configuration. Those are accessed through
  `pipeline_config`; appendwatch location is derived from
  `lima_configuration`.
- `AiAugmentBackendContext` owns source-DuckDB population derivation, including
  release-batch loading, source innerdict/cohort reconstruction, and the exact
  population-wide seeded RND assignment. `AiAugmentControlCentreContext`
  inherits it and may seed it from the validated NiceGUI source-data cache.
  `api.py` and `ui.py` no longer own a duplicate outer-dict factory.
- Updated directly affected production import paths, constructors, and context
  member access without deferred imports, runtime protocol checks, or Pydantic
  protocol field loopholes.

## Completed event-model wiring

- The Human Operator split `server_event.py` into `commit_event.py`,
  `run_outcome_response.py`, and `query_response.py`; preserve that ownership
  and remove stale production imports of `server_event`.
- The Human Operator removed `PreparedPullResponse` because it duplicated
  architectural records and transport fields. Keep
  `AgentRuntimeComponent.AttemptProperty` limited to the Agent Runtime attempt.
  Implement `BackendComponent.AgentRuntimePort.AttemptRecordProperty` as the
  Backend-owned connector record combining that attempt with the actual pushed
  `Submission | StandardizedSubmission | None` and the optional ground-truth
  `InnerDict`. Render NDJSON only at the `/pull` transport boundary.
- Keep projection and in-memory workflow state model-backed; pass complete
  records/models rather than bare UUID/string identities. Add no replacement
  prepared-response DTO.
- `InnerDict.procedure` is now deliberately excluded from serialization.
  `AgentRuntimeAttemptRecord` serializes the actual `InnerDict` and requires its
  matching procedure when loaded alone. `QueryResponse` resolves that procedure
  without a global caller argument: it first rehydrates each researcher’s
  `AiAugmentOuterDict`, resolves the attempt researcher through the commit
  `Name-Key`, and uses that researcher’s DOCX-origin innerdict procedure for the
  ground-truth row. Attempts without ground truth require no procedure.
- Replaced every production `PreparedPullResponse` path with the existing
  `AgentRuntimeAttemptRecord`: its `AgentRuntimeAttempt` owns the pull, commit,
  and post-commit validation; the Backend connector record additionally owns
  the parsed submission and optional ground-truth `InnerDict`. The persisted
  attempt table now stores that complete model, and `/pull` derives retry or
  accepted NDJSON responses only at the transport boundary.
- The live commit path reuses the exact attempt object created by projection
  instead of immediately reconstructing it from DuckDB.
- Updated Backend IPC and Control Centre production imports/consumers to the
  split event modules. The dashboard retains full Backend attempt records and
  unwraps the Agent Runtime attempt explicitly during reconciliation. Tests
  remain untouched.

## Completed lifecycle consolidation

- `BackendComponent.LifecycleProperty` is the single Backend lifecycle
  vocabulary. `BackendLifecycle` now implements the former workflow states and
  post-commit validation stages/results; `PostCommitValidation.stage` and
  `.result` both use that model and validate their respective lifecycle
  subsets. The separate workflow-status, validation-stage, and
  validation-result models and consumers are removed.
- Removed the unused `transport`, `rollout_copy`, and
  `appendwatch_report_copy` values inherited from the former validation-stage
  model: those operations precede commit and were never post-commit validation
  stages or retained Backend lifecycle state.
- The live Backend keeps the established synchronous behavior with the unified
  model: `ready`/`retry` accept a push after an authoritative pull, `busy`
  covers accepted-push processing, and the resulting state is `retry`,
  `complete`, or `failed`. Post-commit records use the same lifecycle model for
  their detailed stage and result.
- `ControlCentreComponent.LifecycleProperty` is the single Control Centre
  lifecycle vocabulary. `RunLifecycle` implements source-ready, queued/running
  presentation, the existing durable run-event milestones, and the three run
  outcomes. `Run` and `RunEvent`, run-outcome IPC models, reconciliation,
  filters, projections, and rendered grid values all retain this model until
  the final UI serialization boundary.
- `ControlCentreComponent.BackendPort.RunOutcomePathProperty` prescribes the
  three run-outcome HTTP paths. Concrete production code implements it as the
  `RunOutcomePath` string enum and uses that model for produced request paths;
  only the HTTP-record parser accepts a plain string and immediately validates
  it through the concrete model.
- Removed the separate run-event-kind, run-phase, run-outcome, and researcher-
  activity models. No transient Backend-query or run-outcome HTTP-call labels
  were added because production logic does not retain those as lifecycle
  state. Production spelling is consistently `cancelled`.
- Production modules compile. Focused Ruff undefined/unused-name checks pass;
  focused strict mypy reports no detour errors and only the five recorded
  errors in four shared modules outside this detour. Tests remain untouched as
  directed.

## Active architecture audit

- After the current surgical model wiring, repeat the requested audit of all
  classes defined under `src/detours/detour_ai_augment/src` and report progress
  against the previous audit.
- Add `@implements[...]()` wherever an architecture interface exists but its
  downstream implementation lacks the decorator.
- Classes that are persisted, visualized to the Human Operator, or exchanged
  between architecture components are the classes to consider for interfaces;
  consolidate incidental implementation classes rather than over-model them.
- Keep module-local classes private with a leading underscore unless they live
  under `data_models` or implement an interface from `architecture.py`.
- Audit every production type annotation under the detour's `src/` and
  `protected/src/` trees that uses a plain Python type instead of an available
  domain or architecture model. Each retained primitive, generic container,
  `Any`, `object`, or bare identity type must be justified as an actual parsing,
  validation, transport, serialization, operating-system, or storage boundary;
  replace unjustified uses with the established model and pass that object by
  reference.
- Scrutinize the detour for unwarranted recreation of objects. Ideally, create
  each object once within a process lifecycle, pass it by reference efficiently
  throughout that lifecycle, and mutate it deliberately where necessary.
- Completed the first object-identity pass: removed the temporary response-file
  DTO/path; the live commit path retains its projected attempt; configured and
  cached source objects are constructed once per process; query projection
  updates the Backend-owned outerdict objects and reuses the population tuple;
  and HTTP-record subclasses now expose themselves rather than rebuilding an
  equivalent base model. Reconstruction remains only at explicit HTTP, JSONL,
  DuckDB, CAS-metadata, or NiceGUI-storage boundaries.
- Variables holding `Submission | StandardizedSubmission` are named
  `submission_payload`. Backend namekeys are `NameKey` models after one parse at
  the HTTP boundary; serialized strings are produced only for headers/storage.
  Removed the local `SubmissionPayload` alias; annotations spell out the two
  approved submission models.
- Every interface currently declared in `architecture.py` has a concrete
  `@implements[...]()` implementation, and focused mypy reports no detour
  conformance errors. The class audit still needs Human Operator direction on
  whether to expand protected architecture for Backend-private durable
  retry/evidence projection records and Control Centre-private durable source
  cache records. Transient parser, process, controller, and UI-rendering helper
  classes remain private implementation details.
- Retry-chain traversal now accepts and returns complete
  `HttpRequestLogRecord` models through `_original_pull_record`; commit
  validation resolves the original pull once and extracts its `record_id` only
  at the retry-table boundary. Removed every `cast()` from Backend `api.py`:
  required rollout/JSON text is extracted by a validated-value helper that
  returns `str` or raises the call site's specific error, while DuckDB and ASGI
  boundary values carry concrete annotations. Focused mypy has no detour errors
  after the change.
- `_process_retry_attempt` now receives the complete original pull and
  `BackendCommitRecord`; it derives the retry-table key, attempt key, and Codex
  session value only while constructing SQL values.
  `_attempt_record_from_serialized_json` now receives the complete commit HTTP
  record already held by its caller instead of accepting its UUID and querying
  the same record again.
- UUID typing audit:
  - Retain UUIDs that are the values themselves: Codex session identity;
    Control Centre `Run`/`RunEvent` identity and durable event references;
    required commit/run-outcome serialized ID fields; UUID-keyed indexes and
    deduplication sets; and parsing/generation at JSONL, IPC, browser, shell, or
    SQL boundaries. Resolver callbacks and `_projected_http_record` are explicit
    ID-to-record rehydration boundaries.
  - Backend workflow state now retains current/pending pull and latest push as
    complete `HttpRequestLogRecord` objects and the Codex session as `UUID`.
    `_retry_baseline_exists` receives the original pull record and extracts its
    ID only at the retry-table boundary.
  - Removed the unused
    `CommitRequestBody.record_ids_from_serialized_json` bare-ID projection and
    its architecture declaration.
  - Control Centre startup replay remains the storage rehydration boundary.
    Thereafter each run is one maintained mutable `Run`: the queue, active-run
    state, Codex handle, runner, and orchestration methods pass that object by
    reference, and appending an event mutates it incrementally instead of
    rebuilding all runs. UUID-keyed indexes and persisted/browser IDs remain
    explicit boundaries.
  - Dashboard attempt views now retain either the complete Backend
    `AgentRuntimeAttemptRecord` or the complete Control Centre `Run` and derive
    identity, timestamps, activity, and failure details from that source.
- Replaced `ground_truth_for_researcher` with
  `AiAugmentOuterDict.ground_truth_innerdict() -> InnerDict | None`. The source
  selector and the durable attempt field intentionally represent the same
  domain object at different lifecycle stages; only `/pull` and dashboard-view
  construction flatten `.data`.

## Completed dashboard-owned hash verification

- Added Backend CLI option `--danger-no-verify-hash`. Its only semantic effect
  is to pass `verify_hash_on_init=False` to the detour's configured
  `RegisteredResource` constructions. Manual full and IPC-only Backend starts
  retain verified construction by default.
- The Control Centre verifies its configured release-map and replay-log
  resources once during startup. Its source-cache path retains the verified
  release-map object, and every full Backend process it owns receives the
  danger flag so the child does not repeat content hashing.
- The replay log now receives its configured SHA-256 instead of silently using
  its current hash. Both detour configured SHA-256 values are enforced only by
  `RegisteredResource` initialization; no detour-local direct configured-hash
  comparison exists. Runtime rollout CAS and replay-projection hashes remain
  unaffected.
- The shared main-pipeline resource helper was deliberately left unchanged;
  this implementation is contained under the AI-augment detour.
- Manual and Control Centre-owned Backend processes now share the
  `backend.server` CLI entrypoint. The Control Centre invokes that same
  entrypoint as a subprocess with `--danger-no-verify-hash` only after its own
  successful configured-resource verification.
- The stale event-model imports and removed-table references are resolved.
  Focused `py_compile`, detour-wide Ruff F821, and production-module imports
  pass. Focused strict mypy reports only the recorded errors in four shared
  modules outside this detour. Tests remain untouched as directed.
- Centralized the detour's registered resources under the frozen
  `AiAugmentDetourConfig.resources` registry. Its resource objects are also
  frozen, preserving each initialization-time verification result. Backend
  subprocess creation now fails before any state change or spawn unless every
  registered resource was hash-verified during Control Centre configuration
  construction. The child still skips the duplicate checks.

## Completed configuration ownership

- `AiAugmentDetourConfig` owns the configured release map, replay log, derived
  Detour DB path, and rollout CAS as static child-config properties derived
  from the existing config JSON fields.
- `create_services` constructs the Control Centre's pipeline configuration
  once from the required config path and passes the configuration object
  downstream; other models derive their configuration from that object rather
  than receiving the config path.
- Human-maintained configured SHA-256 values are checked only through
  `RegisteredResource` initialization: once by the Control Centre, and on each
  manual Backend start. The Control Centre-owned Backend receives
  `--danger-no-verify-hash`; that option changes only
  `verify_hash_on_init=False` for those configured resources.
- The Control Centre CLI requires `--config`. Source-cache validation now
  rehydrates a matching cached outer-dict tuple once and passes that same tuple
  into the Control Centre context.

## Parked verification and test work

- Complete production code first. Then, only after the Human Operator
  authorizes test work, adapt the detour tests and run focused static, mypy,
  hermetic, root, and operator checks. Do not alter main-pipeline tests.
- Rebuild `tasks/tasks-20260731-tighten-api/build/SPECS.ipynb` as the
  authoritative, human-readable executable evidence for every selected README
  Lifecycle line and make it pass the task Makefile's `validate` target.
- Every notebook code cell must be independently executable in VS Code through
  an ipykernel and must expose the actual behavioral logic, not breadcrumbs or
  opaque wrappers. Notebook-specific helpers belong in explicit notebook
  cells; genuinely reusable test helpers may remain in existing detour test
  modules. Create no additional helper modules and keep `conftest.py` shallow
  without autouse machinery.
- Automatic Makefile execution covers hermetic evidence only. Evidence that
  genuinely requires root or a Human Operator uses the existing `needs_sudo`
  or `operator` marks and is run manually; use `operator` only where automatic
  execution cannot prove the behavior. The finished manifest/notebook must
  pass `make validate`.
- Preserve ordinary pytest execution and, barring unavoidable contract
  changes, its collected test count/results: behavioral logic may be projected
  from the authoritative notebook into existing tests without introducing a
  separate pytest-bdd/Gherkin layer.
