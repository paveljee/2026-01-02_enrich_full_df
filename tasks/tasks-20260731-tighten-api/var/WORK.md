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

## Active surgical context pass

- Add these exact architectural contracts:
  - `BackendComponent.ContextProperty`: `pipeline_config`,
    `configured_namekey`, `ai_augment_outerdicts_factory()`, cached/computed
    `ai_augment_outerdicts`, and `configured_ai_augment_outerdict()`.
  - `ControlCentreComponent.ContextProperty` inherits the Backend context
    contract and adds `openalex_api_key` and `lima_configuration`.
- Type both outer-dict collections and the Backend lookup result through
  `BackendComponent.ControlCentrePort.AiAugmentOuterDictProperty` in
  `architecture.py`. Concrete Pydantic implementations retain concrete runtime
  types and carry explicit `@implements[...]()` checks.
- Move both concrete context modules from `protected/src/...` to the matching
  unprotected `src/...` paths.
- Remove the monolithic Control Centre `load()` method. `create_services`
  constructs `AiAugmentDetourConfig` once; context values are implemented as
  focused fields or cached/computed properties. Preserve the existing
  NiceGUI source-data cache path.
- Contexts must not duplicate detour DB, replay-log, CAS, release-map, source
  DB, timezone, or related configuration. Those are accessed through
  `pipeline_config`; appendwatch location is derived from
  `lima_configuration`.
- Update only directly affected production import paths, constructors, and
  context member access. Do not add deferred imports, runtime protocol checks,
  or Pydantic protocol field loopholes.
- Verify with focused production import/Ruff/mypy checks only; no test edits or
  pytest runs.

## Active event-model wiring

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
- Replace every remaining production `PreparedPullResponse` path with the
  existing `AgentRuntimeAttemptRecord`: its `AgentRuntimeAttempt` owns the pull,
  commit, and post-commit validation; the Backend record additionally owns the
  parsed submission and optional ground-truth `InnerDict`. Derive the next pull
  response from that model at the transport boundary.
- Update Backend IPC and Control Centre production imports/consumers to the
  split event modules. Do not edit tests yet.

## Active context-owned source population

- `BackendComponent.ContextProperty` owns the
  `ai_augment_outerdicts_factory()` contract and the cached/computed
  `ai_augment_outerdicts` result. `ControlCentreComponent.ContextProperty`
  inherits that Backend context contract and adds only its OpenAlex and Lima
  properties.
- `AiAugmentBackendContext` now owns the complete source-DuckDB population
  derivation. It loads the configured release map, reconstructs the source
  innerdicts and cohorts, and assigns `ai_augment_rnd` with the existing exact
  population-wide algorithm: shuffle the contiguous RND range using
  `Random(pipeline_config.sample_seed)` and map it to sorted canonical
  namekeys.
- `AiAugmentControlCentreContext` inherits that implementation. A validated
  NiceGUI source-data cache may seed the context directly; otherwise the
  inherited factory runs. `AiAugmentOuterDict` consumes the resulting required
  integer and does not derive population identity itself.
- `api.py` and `ui.py` no longer own or call an outer-dict derivation function.

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
- Focused `py_compile` passed for all four edited production modules. Ruff
  passes for `backend/server.py` and `backend/ipc.py`; whole-file Ruff/import
  checks for `api.py` and `ui.py` remain blocked by the already-recorded stale
  event-model split (`PreparedPullResponse`, removed outcome-table constants,
  and `server_event` imports). Tests remain untouched as directed.

## Parked production work
- Finish `AiAugmentDetourConfig` ownership: configured release map and replay
  log, human-maintained startup SHA-256 validation, derived Detour DB path, and
  rollout CAS remain static pipeline configuration. Control Centre validates
  once and supplies the validated config to owned Backend starts; a manually
  launched Backend validates on each startup.
- The shared Backend process-entrypoint design remains undecided by the Human
  Operator; do not implement it yet.
