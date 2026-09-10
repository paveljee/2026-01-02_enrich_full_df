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
- The rejected `_BackendRunOutcomeResponse` and `_RunOutcomeSnapshot` wrappers
  are removed. `_AttemptView` retains the exact Backend-owned
  `RunOutcomeResponse`; savedness, Codex session identity, and appendwatch
  display status are derived directly as view properties. The Control Centre
  posts a run outcome, marks that post once acknowledged, and immediately
  refreshes Backend query state before owned-process shutdown; it never creates
  a substitute response locally. Concrete `QueryResponse`, its wire shape, and
  every caller now use the finalized `accepted_innerdict_summaries` contract.
- Verification is green: Ruff passes; strict mypy with imported out-of-scope
  modules silent checks 37 Detour source/test files with no issues; Control
  Centre unit tests are 46 passed; focused Backend API/IPC tests are 86 passed
  and 37 environment skips; the broader non-root/non-operator/non-real-API
  suite (excluding the pre-existing uncollectable BDD module) is 205 passed,
  46 environment skips, and 7 deselections; `git diff --check` passes. Whole
  Detour collection still stops at the pre-existing missing BDD feature file.

## Repeated complete class/protocol audit

- AST inventory now finds 192 class declarations under the Detour `src` tree:
  35 Acme/protocol declarations, 22 explicit `@implements[...]()` concrete
  implementations, and 135 other classes. The preceding audit found
  189/29/17/143 respectively, so formal declarations increased by six,
  concrete checked implementations increased by five, and unclassified
  concrete classes decreased by eight despite three net new declarations.
  Another 48 classes under the ordinary Detour test tree are test-local and do
  not warrant architecture protocols.
- The authoritative replay/IPC/run core is now well covered: Backend workflow,
  commit, post-commit validation, Codex and appendwatch capture, Agent Runtime
  attempts, accepted innerdict summaries, query responses, run-outcome response
  bodies/responses, Control Centre runs/events/phases/outcomes, and query and
  run-outcome requests all have explicit static conformance checks. Compact
  session metadata is correctly internalized as
  `_CodexRolloutRecordSummaryJson` behind `CodexRolloutRecord` methods rather
  than remaining a competing architectural entity.
- Remaining durable Backend candidates are the retry obligation family,
  evidence-audit family, `PreparedPullResponse`, indexed rollout/FC/FCO/
  turn-reference rows, `_EvidenceMatch`, `SourceResearcher`, and the shared
  `AiAugmentDetourConfig`. `_ResearcherContext`, `_ArchivedFile`, and overlapping
  `_SessionMetadata`/`_RolloutIndex` intermediates should preferentially be
  merged into existing rich models instead of receiving parallel protocols.
- Remaining Control Centre durable/UI candidates are `SourceCohort`,
  `IneligibilityCategory`, `SourcePopulationRow`, `_SourceInputFingerprint`,
  `_CachedSourceData`, `_GroundTruthRecord`, `_VariableSpec`, the displayed
  activity/API/action/availability enums and record, and the direct selection,
  attempt projection, grid row, card, counts, and UI snapshot models. Internal
  `_Researcher`/`_ResearcherView`/`_AttemptView` assembly should stay private or
  be consolidated; protocol coverage belongs on the direct Human Operator-port
  inputs and outputs.
- Remaining deployment/guest candidates are appendwatch `Record`,
  `AuditReadConfiguration`, `LimaMount`, and `LimaConfiguration`. The
  illustrative LLM Inference API still has two durable SQLite projections,
  `PriceQuote` and `LogEvent`, requiring component ownership if that sample is
  kept in architecture scope.
- Canonical `pydantic_to_paste` submission models and main-pipeline entities
  already own their contracts and require no duplicate protocols. Private JSON
  serializers, exceptions/locales, transient validation aggregates, process
  handles, framework adapters, connector service implementations, UI handles,
  and test doubles likewise should remain unprotocolled. The larger structural
  gap is that `architecture.py` still names only Backend, Agent Runtime, and
  Control Centre components; formal Human Operator and LLM Inference API ports
  are prerequisites for correctly owning the remaining direct UI and sample
  inference contracts.

## Current protocol-decoration pass

- Audit every existing `architecture.py` property protocol against concrete
  Detour implementations. Add the exact colocated `@implements[...]()`
  decorator wherever a concrete implementation exists but lacks it; do not
  manufacture implementations for component/port namespace protocols. Verify
  completeness mechanically, then run Ruff, strict Detour mypy, focused tests,
  and `git diff --check`.
- After this surgical correction is verified, rerun the full AST audit of every
  class defined under `src/detours/detour_ai_augment/src`. Compare it with the
  previous 189-class/17-implementation audit using the approved criteria:
  durable-storage participation, direct Human Operator visualization, and
  traffic across README architecture component boundaries. Report concrete
  progress and classify every remaining justified protocol gap versus private
  implementation detail/overengineering.
- Added Human Operator scope: perform the previously proposed consolidation
  where private intermediate classes duplicate existing rich architectural
  models. Keep this surgical: preserve genuinely distinct UI projections and
  do not use consolidation as authority to add the remaining new protocols.

## Current unified outer-dict pass

- Human Operator replaced the source-wrapper/committed-outerdict split with
  one maintained Detour-local `AiAugmentOuterDict` per canonical namekey.
  It owns XLSX, SSN, and DOCX innerdict tuples separately; provenance-expanded
  committed innerdicts; and `ai_augment_rnd`, `ai_augment_cohort`, and
  `ai_augment_ineligibility_category`.
- `QueryResponse` is to expose attempts, `ai_augment_outerdicts`, and run-outcome
  records. The Control Centre maintains the 307 per-namekey aggregates and
  reconciles Backend-returned committed state into those existing references;
  310 remains a sample/draw reference, not a design-level outer-dict count.
- Remove the superseded source population/researcher, dashboard researcher,
  accepted-summary, and separate committed-outerdict projections. Preserve
  explicit protocol implementations and add exact `@implements[...]()` checks
  for the newly concrete contracts. No migration or compatibility layer.
- Tighten commit provenance at the same boundary: `CommitRequestBody` alone
  owns the typed pull, push, and Codex-session members. `BackendCommitRecord`
  remains the specialized durable HTTP record and exposes one validated
  `commit_request_body` projection instead of duplicating those three members.
- Complete and verify the Detour production implementation before making any
  further test changes. The partially migrated tests remain parked until the
  Human Operator explicitly authorizes the test-fix pass.

## Deferred Detour configuration correction

- Preserve the main `PipelineConfig` contract and add Detour-specific static
  computed configuration on `AiAugmentDetourConfig`: the configured
  `map_subset_0_to_batch` resource, Backend replay-log resource, and derived
  Detour DuckDB path belong to that child model rather than being independently
  reinterpreted as runtime configuration.
- At startup, resolve each configured resource with its human-maintained
  SHA-256 and fail on mismatch exactly as the main pipeline does. Do not replace
  the configured replay-log hash with its observed hash; the Human Operator
  updates the configuration explicitly.
- The Control Centre performs these static hash checks once and passes the
  validated configuration to each Backend process it starts, avoiding repeated
  verification over its start/stop cycle. A Backend started manually performs
  the checks on each startup. During execution, use the startup-validated
  resource objects without rechecking their hashes.
## Deferred AI-augment RND ownership correction

- Move `ai_augment_rnd` generation into the `AiAugmentOuterDict` BaseModel as
  model-owned default-factory behavior. Remove the separate RND assignment from
  `derive_ai_augment_outerdicts`; callers should not manufacture a property
  whose construction belongs to the aggregate model.
