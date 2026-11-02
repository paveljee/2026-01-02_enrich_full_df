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
- Production code was completed before the Human Operator authorized the
  ordinary test-adaptation pass. Real operator execution remains reserved for
  the Human Operator.
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
  errors in four shared modules outside this detour.

## Completed architecture audit

- Re-audited the production classes after the context, event-model, and
  lifecycle refactors. Every interface currently declared in
  `architecture.py` has a concrete `@implements[...]()` implementation; focused
  strict mypy reports no detour errors. Transient parser, process, controller,
  HTTP-adapter, and UI-rendering classes remain private implementation details.
- Human Operator declined additional architecture properties for the private
  Backend retry/evidence/provenance projections and Control Centre source cache
  or queue representation. These are implementation-owned persistence and
  caching details, not component properties or connector contracts. Their
  existing private classes are intentional; the queue's durable representation
  likewise remains private while its lifecycle behavior stays prescribed by
  README.md and the existing `Run`/`RunEvent` contracts.
- Tightened `RunEvent.rollout_jsonl` to `PurePosixPath | None` in both its
  interface and implementation. Pydantic JSON-mode persistence retains the
  existing string representation.
- Removed `_GroundTruthRecord`; source and projection paths now retain the
  existing `InnerDict`. `_ResearcherGridRow` and `_ResearcherCardView` retain
  their existing `AiAugmentOuterDict` instead of copying its
  identity/classification fields.
- Tightened IPC run-outcome route collections to the existing
  `RunOutcomePath` model, converting to strings only at SQL and Flask
  boundaries.
- Other retained primitive/generic annotations are at actual JSON, HTTP, ASGI,
  DuckDB, NiceGUI, operating-system, subprocess, or rendered-UI boundaries.
  Existing full models are passed by reference within each process. Model
  reconstruction remains confined to explicit transport/storage rehydration.
- The optional protected LLM inference sample deployment is not part of the
  implemented default lifecycle and is excluded from this production-interface
  expansion. Appendwatch daemon internals remain implementation details; the
  durable captured report is already formalized by
  `AppendwatchReportRecordProperty`.

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
  modules outside this detour.
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

## Completed verification and test adaptation

- Adapted the ordinary Backend, IPC, Control Centre, appendwatch, audit-read,
  UI, Playwright, and operator-preflight tests to the current paths, identities,
  nested records, and component lifecycles. No main-pipeline test was changed.
- Adapted the protected real-operator harness without executing a real
  operator contour. Its three tests collect successfully; the hermetic
  operator-preflight module passes all three tests.
- Updated the non-BDD Pixi test tasks and moved-path documentation/scripts.
  BDD/notebook work remains explicitly outside scope: its WIP stays in the Git
  stash, and the stale protected BDD test and BDD task wiring remain untouched.
- `pixi run -e detour-ai-augment test-detour-ai-augment` succeeds with 205
  passed, 47 environment-dependent or intentional skips, and three root-only
  tests deselected. Its separately selected live-API test skips because this
  environment has no `OPENALEX_API_KEY`.
- The three root-only appendwatch tests collect successfully and remain for the
  Human Operator to execute with the required privilege. No real operator,
  manual Backend, or dashboard contour was executed here.
- Ruff E/F/I checks and Python compilation pass across the adapted detour
  files. Strict mypy reports no detour production or test errors; its only five
  findings are in shared modules outside the detour and outside this task's
  write scope.
- Git remained read-only. The main database and `src.repl` were not touched.

## Human Operator handoff

- The codebase and non-BDD test harness are ready for the Human Operator's
  root-only appendwatch test, real operator suite, and manual full/IPC-only
  dashboard smoke contours on real namekeys.

## Completed shared protected pytest configuration

- The fixture and hook implementation remains protected in
  `protected/tests/pytest_plugin.py`. Thin `conftest.py` registration points in
  both the protected and unprotected test roots load that same plugin, so both
  trees receive the protected fixtures and autouse behavior without duplicate
  registration during combined collection.
- The protected operator-preflight regression imports its directly exercised
  implementation helpers from the protected plugin. Combined protected and
  unprotected collection succeeds, and pytest resolves the unprotected UI E2E
  suite's `repository_root` fixture from the protected plugin.
