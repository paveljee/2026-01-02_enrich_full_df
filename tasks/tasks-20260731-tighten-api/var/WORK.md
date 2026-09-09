# Tighten API — current work

## Authority and constraints

- Authoritative behavior is
  `src/detours/detour_ai_augment/README.md`, especially **Lifecycle**.
- Follow `tasks/tasks-20260731-tighten-api/src/TASK.md`.
- Run every command through the `detour-ai-augment` Pixi environment.
- Git is read-only: never stage or unstage. Preserve all Human Operator staged
  edits, including the `RunEventKind` spelling changes in `run_event.py`.
- Never run `src.repl`; the main pipeline database is read-only.
- Keep changes surgical. Do not add migrations, aliases, fallbacks, or
  compatibility handling for a contract that was incorrect.
- Protect the expensive Human-operated E2E contour with hermetic regressions.

## Current objective

Audit and then correct the accepted-commit, persisted HTTP-record, attempt, and
Dashboard run models to one authoritative contract:

- The replay commit request body is unversioned. Only the enclosing
  `HttpRequestLogRecord` retains a schema version; all body-version fields,
  branches, tests, and documentation are removed outright.
- The corrected shared HTTP-log shape enforces `dict[str, str]` request and
  response headers and `str | None` request and response bodies for all newly
  validated records. Do not preserve the incorrect permissive v1 field types
  from `aicode/staging`; failures there belong to that implementation.
- `ReplayCommit` is replaced by the clearer unversioned
  `CommitRequestBody` and `RunOutcomeResponseBody` models.
- A new `CodexSessionRecord` contains the authoritative session UUID supplied
  through Backend stdin plus `CodexRolloutRecord` and
  `AppendwatchReportRecord`. The session UUID is never inferred from a filename
  or another artifact.
- `CommitLogRecord` and `RunOutcomeLogRecord` inherit
  `HttpRequestLogRecord` and add their respective Lifecycle restrictions, so
  each serialized subtype remains valid as the base HTTP record.
- `AttemptRecord` carries the complete `CommitLogRecord`, one nested
  `PostCommitValidation`, and the complete actual result-bearing `GET /pull`
  `HttpRequestLogRecord`; HTTP code, headers, and body are derived from that
  pull rather than duplicated.
- Dashboard helpers own one authoritative Pydantic `Run` model and its
  completed/failed/cancelled `RunOutcome`. Run lifecycle state is distinct
  from outcome; `status` is never used as a synonym for outcome. All authored
  code, documentation, tests, fields, and messages use this vocabulary.
- Audit all Pydantic models and dataclasses in `backend/api.py` and Dashboard
  `ui.py`; centralize only duplicated protocol/domain models, retaining local
  algorithmic, persisted-storage, presentation, and process-handle models when
  they have a concrete purpose.

## Audit conclusions

- Current `ReplayCommit` mixes two versioned body shapes, flattens
  session/artifact fields, and contains normalization and serialization
  branches that the corrected contract removes.
- Current commit replay derives the session UUID from the rollout filename.
  That derivation must become validation against the stdin-authoritative UUID,
  never the source of identity.
- Current `AttemptRecord` and `ProjectedValidationOutcome` duplicate commit
  IDs, pull/push provenance, session, rollout hash, response data, and timing.
- Backend query DTOs are re-wrapped into duplicate Dashboard DTOs. The Backend
  protocol models can be consumed directly after validation.
- Dashboard run state is currently split between `RunStatus`, mutable
  `RunRecord`, `RunEvent`, and separate saved-snapshot models. Run ownership and
  the three mutually exclusive outcomes belong in Dashboard helpers.
- `RunEvent` remains valuable as the append-only storage/recovery format; the
  staged Human Operator spelling must be retained.
- Persisted NiceGUI cache models, replay-validation models, UI presentation
  models, and operational process handles each serve distinct purposes and
  should not be collapsed merely to reduce class count.
- `AttemptRecord` should retain the full `CommitLogRecord`, nested
  `PostCommitValidation`, and full result-bearing pull record. Commit UUID/time,
  push and source provenance, namekey, session UUID, rollout hash, HTTP response
  code/headers/body, and canonical request hash are derivable and should not be
  duplicated.
- `PostCommitValidation` centralizes `stage`, `result`, and `detail`, with strict
  `PostCommitValidationStage` and `PostCommitValidationResult` enums replacing the
  scattered string constants.
- `ProjectedValidationOutcome` overlaps `AttemptRecord`, but the Backend still
  needs a transient prepared-pull value between validation and the client's
  actual `GET /pull`. It must not fabricate an HTTP record. The persisted
  `AttemptRecord.pull` is formed only from the complete exchange emitted by the
  shared authoritative HTTP logger.
- Both `CommitLogRecord.request_body` and
  `RunOutcomeLogRecord.response_body` remain JSON strings, as required by the
  corrected base HTTP model, and each subtype validates its decoded body
  without serializing an extra parsed field.
- `CompactSessionMetadata` is a real persisted boundary and should remain,
  with stronger UUID/datetime typing if changed. Backend rollout parsing has a
  distinct richer internal session object. The Dashboard's duplicate session
  and accepted-attempt wrappers can be removed in favor of the validated IPC
  models.
- Retry obligations, evidence audit objects, and `CodexTextResult` validate
  persisted or untrusted JSON and remain justified. Backend algorithmic
  dataclasses remain justified as transient execution/index structures.
- Dashboard source-cache Pydantic models remain justified because they validate
  persisted NiceGUI storage. Researcher/view/selection and process-handle
  dataclasses remain useful local projections or ownership handles.
- Dashboard presentation should use explicit run phase and run outcome fields.
  `ready` is researcher availability, not a run phase or outcome. Existing UI
  filters/columns that combine these concepts should be labeled and modeled as
  a presentation union rather than calling all values a status.
- The Backend keeps no dependency on Control Centre models. IPC path-to-outcome
  mapping stays at the Dashboard boundary; Backend IPC uses outcome vocabulary
  without importing the Dashboard's authoritative `Run` model.

## Contract edge under review

Run-outcome capture may happen before stdin supplies a session UUID, while the
appendwatch report can still be captured. To preserve that evidence without
inventing identity, the proposed strict shape is a present
`CodexSessionRecord` whose `session_id`, `rollout`, and `appendwatch_report` are
individually nullable in `RunOutcomeResponseBody`; `CommitRequestBody` adds
validation requiring all of them. `RunOutcomeLogRecord` keeps the HTTP response
body as a JSON string and validates its decoded value as
`RunOutcomeResponseBody`.

The Architecture section introduces a stronger ownership distinction that must
precede implementation:

- `AgentRuntimeAttempt` means one AI Agent Runtime/Codex-session effort for one
  configured HCR, whether initiated manually or orchestrated by the Control
  Centre; it may contain multiple pull/push/commit cycles.
- `ControlCentreRun` means the Control Centre's orchestration record around an
  Agent Runtime attempt. The Dashboard is the current Control Centre adapter,
  not the definition of a run.
- The Backend's current row-per-commit `AttemptRecord` is therefore misnamed.
  The proposed `{commit, post_commit_validation, pull}` model is a Backend commit-result
  projection, not an Agent Runtime attempt. Its final name and the aggregate
  `AgentRuntimeAttempt` shape must be settled before implementation.
- Connector records (`HttpRequestLogRecord`, `CommitLogRecord`, and
  `RunOutcomeLogRecord`) remain distinct from component-owned state. Dashboard
  code should use explicit `ControlCentreRun*` names; Backend/query code should
  not call a single committed push an attempt or a run.
This is the sole material contract choice awaiting Human Operator confirmation.

## Existing verified foundation

- `/completed`, `/failed`, and `/cancelled` are Flask Unix-socket IPC routes in
  `backend/ipc.py`; `api.py` owns reusable persistence/domain operations only.
- `backend/server.py` composes full API plus IPC, or read-only IPC-only mode.
- Dashboard-first startup, later API/IPC detection, explicit Refresh hydration,
  source-data caching, and read-only IPC-only database access were smoke-tested
  by the Human Operator.
- Restricted `aivm-audit` rollout/report access and clean deploy were confirmed
  on macOS/Lima.
- The accepted Aziz Sheikh push fixture is the non-production regression
  source; no final `410 Gone` production fixture is required.

## Next actions

1. Settle the architecture-owned `AgentRuntimeAttempt`, `ControlCentreRun`, and
   per-commit result vocabulary and shapes with the Human Operator; no broad
   implementation is authorized yet.
2. After approval, update staged Lifecycle wording first where necessary,
   implement direct replacements, add hermetic regressions, and run focused
   then complete Detour verification.
