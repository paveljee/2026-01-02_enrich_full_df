# Tighten API — architecture model alignment

## Authority and constraints

- Follow `tasks/tasks-20260731-tighten-api/src/TASK.md` and the authoritative
  `src/detours/detour_ai_augment/README.md`.
- Current Human Operator direction includes making strict mypy clean throughout
  `src/detours/detour_ai_augment/`, without touching code outside that subtree.
- Every concrete protocol implementation must have an explicit, colocated
  `@implements[ExactProtocol]()` static conformance check.
- Git is strictly read-only. Use `apply_patch` for edits; never stage, unstage,
  restore, reset, pop, or apply a stash.
- Run every command through `pixi run -e detour-ai-augment`; never run
  `src.repl` or write the main pipeline database.
- Preserve Human Operator edits and signed-off comments. Add no migration,
  compatibility, alias, or legacy handling for the superseded contract.

## Completed implementation

- `architecture.py` defines six architecturally owned property protocols:
  Backend post-commit validation stage/result, Backend Agent Runtime-port
  appendwatch encoding, and Control Centre run phase/outcome/event kind. Their
  precise literal value sets are part of those structural contracts.
- The corresponding enums remain in their owning concrete modules
  (`server_event.py` and `run_event.py`) and explicitly implement those
  protocols. Appendwatch encoding remains losslessly serialized as the literal
  JSON string `"base64"`; the persisted Backend run-outcome field remains its
  actual Backend-owned string.
- Run-outcome response and HTTP-record properties belong to
  `BackendComponent.ControlCentrePort`, because Backend produces and persists
  them for the Control Centre.
- `ControlCentreComponent.RunProperty.events` explicitly relates each
  materialized Control Centre run to the ordered immutable `RunEventProperty`
  facts from which it is projected. `replay_run_events` retains each event only
  after validating and applying it; its heading now correctly identifies a
  Control Centre run projection.
- `backend/helpers/data_models/server_event.py` implements the Backend-owned,
  Agent Runtime connector, Agent Runtime attempt, and Control Centre connector
  data models defined by `architecture.py`.
- `control_centre/dashboard/helpers/data_models/run_event.py` implements the
  Control Centre run and run-event data models.
- All 17 architectural protocol implementations have explicit colocated
  `@implements[ExactProtocol]()` static checks.
- Commit serialization is lossless: pull/push record identities, the
  stdin-authoritative Codex session UUID, rollout hash/size/line count, and
  appendwatch bytes round-trip through the serialized contract.
- Backend API/IPC and Control Centre code now consume the concrete models and
  the component/connector vocabulary from the architectural contract. No
  superseded schema migration remains.

## Verification state

- Architecture, Backend, and Control Centre source passed Ruff and mypy: 22
  source files checked by mypy with no issues.
- Combined focused Backend API/IPC and Control Centre unit suite: 132 passed,
  37 environment skips.
- Operator execution remains Human Operator work and was not run here.

## Final scope

- Accidental post-architecture changes to the BDD test module, notebook,
  manifest, Makefile, and `pyproject.toml` were removed; those files exactly
  match the current branch baseline.
- The worktree retains only the architecture/API/UI implementation and its
  associated tests/docs, plus this current ledger.
- The existing `stash@{0}: wip bdd` remains untouched.
- The surgical exact-type tightening passes Ruff, mypy protocol conformance
  across 22 source files, direct runtime identity/import smoke checks, and the
  focused architecture-facing suite: 132 passed with 37 environment skips.
- The explicit run/event projection link passes Ruff, the same 22-file mypy
  check, its focused provenance regression, and all 46 Control Centre unit
  tests.

## Strict-mypy cleanup

- All strict mypy diagnostics reported under
  `src/detours/detour_ai_augment/` are resolved without broad ignores,
  compatibility aliases, or artificial public re-exports.
- Production imports now use canonical owners for shared types, Detour
  constants, HTTP status codes, and server-event headers. The Control Centre's
  immediate HTTP availability probe now converts its response status to the
  declared integer type.
- Tests now import models/constants from their defining modules and patch the
  actual shared dependency objects. Strict findings also exposed and corrected
  stale lifecycle-test names for run outcomes, dashboard query responses, and
  authoritative record persistence.
- Repo-configured `mypy src tests` now reports 88 errors in 21 files, with zero
  errors in the Detour subtree; every remaining diagnostic is outside the
  Human Operator's explicit edit boundary.
- Ruff passes across all Detour source and tests. The affected non-operator,
  non-sudo, non-live-API suite passes with 195 tests and 46 environment skips
  (4 deselected).
- The lifecycle BDD module cannot be collected in this worktree because its
  referenced `tests/features/detour_ai_augment_lifecycle.feature` is absent.
  No BDD artifact was recreated or retrieved from the untouched stash.

## Architectural implementation decorator

- The proposed generic `implements[Proto]` identity decorator was reviewed
  and approved. Under the repository's mypy, it accepts conforming classes,
  rejects missing or incompatible nested members at the decorator, preserves
  the concrete class type, and returns the identical class object at runtime;
  it intentionally performs no runtime validation.
- All 17 concrete architectural implementations now carry the exact colocated
  `@implements[...]()` decorator in `server_event.py` or `run_event.py`; the
  detached `TYPE_CHECKING`/`cast` checks and their imports were removed. The
  `EntityProtocol` example now documents the decorator form.
- Verification passes: Ruff across the complete Detour tree, strict mypy over
  all 36 Detour source/test files (with imported out-of-scope modules silent),
  and the focused Backend/Control Centre suite with 125 passed and 36
  environment skips.
- A complete AST audit found 189 class definitions: 29 Acme/architecture
  declarations, 17 decorated concrete protocol implementations, and 143
  undecorated concrete classes.

## Current architecture-alignment pass

The Human Operator set three cumulative criteria for required architecture
coverage. A class requires a protocol when (1) its instances or nested members
are serialized/projected into durable storage, (2) it is a direct schema
consumed by the dashboard or researcher-card renderer, or (3) it is a
message/artifact crossing a boundary between README architecture components.

The canonical `pydantic_to_paste` Submission family is exempt from duplicate
architecture protocols: its Pydantic models are already the intentionally
located wire contract. Private `_...Json` serializer models likewise provide
physical serialization for public semantic models and should not receive a
second protocol.

The Human Operator authorized a surgical first tranche from the class audit.
The Backend query response now returns accepted materializations as the existing
main-pipeline `InnerDict`; no parallel accepted-attempt or accepted-output model
is permitted. Query requests and run-outcome requests are Control Centre-owned
Backend-port properties; query and run-outcome responses remain Backend-owned
Control Centre-port properties.

Required gaps comprise Backend retry/evidence/Codex durable projections;
Backend–AI Agent Runtime rollout/pull models; Backend–Control Centre IPC and
query models; persisted source/cache and appendwatch models; the Control
Centre's direct dashboard/card view models; durable deployment configuration
models; and the illustrative inference proxy's two SQLite record models. The
boundary criterion also exposes that Control Centre–AI Agent Runtime traffic
and the LLM Inference API are less fully represented in `architecture.py` than
Backend ports. No production code was changed during this audit.

Ownership is assigned by semantic authority, not current module location:
Backend-owned durable projections are component properties; exact HTTP/IPC and
SSH-side representations are properties of the relevant component port;
Control Centre domain/cache projections are component properties while direct
NiceGUI/card contracts belong to a new Human Operator port; guest appendwatch
state belongs to AI Agent Runtime; and inference pricing/request history belongs
to the LLM Inference API. `AiAugmentDetourConfig` is the exception: Backend and
Control Centre independently load one durable shared configuration, so the
concrete model should implement one component-property protocol for each
consumer rather than pretending the model itself traverses a connector.

`CompactSessionMetadata` is removed from the protocol-gap count. It is not an
independent architectural entity: it is the Backend's private, canonical JSON
summary projection of the CAS-addressed Codex rollout. The intended refactor is
to internalize it as `_CodexRolloutRecordSummaryJson` and expose the summary
construction/restoration operation on `CodexRolloutRecord`, without adding the
summary to the serialized commit/run-outcome `CodexRolloutRecord` shape.

The compact-summary refactor and connector request/response protocols are now
implemented. Public validators, restorers, and serializers used by concrete
protocol implementations are declared in `architecture.py`; Pydantic hooks are
private adapters to those declared methods. Current strict mypy has zero Detour
diagnostics; Ruff only reports import ordering left by the in-progress edits.

## Current run-outcome connector pass

- `RunOutcomeRequest` owns and validates the request-only HTTP record.
  `RunOutcomeResponse` owns and validates the completed exchange while reusing
  that typed request. The superseded `RunOutcomeLogRecord` model and its
  duplicate validator are being removed.
- The replay log receives only the response model's plain
  `HttpRequestLogRecord` projection. Replay reconstructs the typed response,
  which reconstructs and reuses the typed request; persistence itself performs
  no run-outcome semantic validation.
- The Control Centre-owned outcome/request models are isolated in
  `run_outcome.py`; `run_event.py` imports them, and Backend response models no
  longer use a `TYPE_CHECKING` or local import from `run_event.py`.
- `AcceptedInnerDictSummary` implements the Human Operator-finalized
  `AcceptedInnerDictSummaryProperty`: it retains the complete `InnerDict` and
  owns namekey, commit UUID, Codex session UUID, and text projection
  validation. The dashboard no longer interprets accepted innerdicts through
  free helper functions.
- The Human Operator rejected private `_BackendRunOutcomeResponse` and
  `_RunOutcomeSnapshot` wrappers as redundant. The dashboard must retain exact
  `RunOutcomeResponse` models returned by Backend query state, attach those
  responses directly to `_AttemptView`, and derive savedness, Codex session
  identity, and appendwatch display status as view properties without another
  transport/domain model.
- Flask remains a transport adapter. One closed outcome/path mapping and the
  canonical Name-Key codec define the request wire shape; no aliases,
  migrations, or compatibility logic will be added.
- Current implementation task: remove both redundant UI wrappers; retain and
  reconcile exact `RunOutcomeResponse` objects; immediately refresh persisted
  Backend query state after posting a run outcome and before Backend shutdown;
  align concrete `QueryResponse` and all callers with the finalized
  `accepted_innerdict_summaries` property; then run Ruff, strict mypy, focused
  Backend/Control Centre regressions, broader Detour checks, and
  `git diff --check`.
- After that correction is verified, rerun the complete AST/class audit across
  the Detour, compare protocol coverage and architectural classification with
  the preceding 189-class/17-implementation audit, and report concrete progress
  plus every remaining candidate and whether it merits a protocol,
  simplification, merger, privacy, or no architectural treatment.
- After this surgical correction is verified, rerun the full AST audit of every
  class defined under `src/detours/detour_ai_augment/src`. Compare it with the
  previous 189-class/17-implementation audit using the approved criteria:
  durable-storage participation, direct Human Operator visualization, and
  traffic across README architecture component boundaries. Report concrete
  progress and classify every remaining justified protocol gap versus private
  implementation detail/overengineering.
