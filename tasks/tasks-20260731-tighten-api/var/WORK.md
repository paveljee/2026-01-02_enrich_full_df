# AI augmentation workflow audit

## Objective and outcome

Audit `src/detours/detour_ai_augment/src` and `src/detours/detour_ai_augment/tests` against the authoritative `src/detours/detour_ai_augment/README.md`, traverse `## Workflow` item by item, and specify the operator E2E tests needed to prove every stated variant. Tests must reuse existing detour source functions/classes; no new source function or class may be added.

Outcome: the README's August 25 HTTP workflow is not implemented by the current source, and the test suite is independently stale after several source refactors. The E2E suite must not be patched to approve current behavior: doing so would preserve the superseded synchronous JSONL protocol. Source contract gaps are listed below, followed by a test suite that can reuse existing source once those gaps are implemented by modifying existing functions/classes.

No detour source or test file was changed during this audit. This report is the requested deliverable.

## Constraints observed

- All project commands were run through `pixi run -e detour-ai-augment`.
- `src.repl` was reviewed but never run or imported for execution.
- Git was used read-only; nothing was staged or unstaged.
- Human-signed inline comments were not changed.
- The only data artifact inspected was `data/scisci_process.duckdb`, opened read-only. It has the expected main-pipeline tables/views used by the detour, including `xlsx_innerdicts`, `docx_innerdicts`, `ssn_innerdicts`, and `card_partitions`.
- The main pipeline writes `data/scisci_process.duckdb`; the detour opens it read-only and derives a separate `*.detour_ai_augment.duckdb` path. No other detour is imported.

## Authoritative change

Commit `1f0fc71` changed the README from the old synchronous JSONL/task-complete protocol to this stateful HTTP contract:

- `GET /pull`: Markdown, strong ETag, `200`; matching `If-None-Match` gives `304`; any error gives opaque `500`.
- `POST /push`: immediate `202` plus `Location: /pull`; validation is reported later by `GET /pull`; a previous push still processing gives `409`; other unavailability gives opaque `500`.
- A completed rollout reaches `410` on `GET /pull` and/or `POST /push`, with instructions to stop and remain idle.
- One AI Agent Runtime workflow handles one configured HCR profile.

## Current source reality

- `authoritative_pull()` returns `application/x-ndjson`, normally `200`, validation feedback as `422`, and configuration failures as `503`. It does not read `If-None-Match` or emit an ETag.
- `authoritative_push()` performs rollout copy, appendwatch validation, submission validation, private commit, DB projection, card generation, and response generation synchronously. It returns `200`, `422`, or `503`, with no `Location`.
- `HTTP_ETAG_HEADER` and the strong formatter `HTTP_ETAG_SHA256_TEMPLATE` exist but are unused.
- `AuthoritativeHttpMiddleware` already supplies a generic opaque `500` exception fallback and a `409` command lock, but the route handlers return obsolete `422`/`503` responses deliberately. Its serialized/public route set does not include `GET /pull`.
- No `202`, `304`, or `410` implementation exists anywhere in detour source.
- There is no durable pending-push/processing state or worker. `AttemptRecord` appears only after the synchronous private commit.
- Accepted submissions already consume the active sanction in `CONTROL_SANCTIONS_TABLE`; that durable state can be reused to distinguish terminal `410` from missing/misconfigured `500`.
- `sanctioned_pull_lines()` is the existing task renderer, but it emits JSONL. It can be modified to render Markdown without introducing a new source function.
- Existing replay-log projection, `SubmissionCommit`, `AttemptRecord`, `execute_attempt()`, retry evidence state, CAS copy, appendwatch validation, and card generation are suitable to retain.
- `ControlCentreController._finalize_run()` currently infers completion from a synchronously persisted accepted attempt only after Codex exits. It has no explicit `202`/ETag/`410` handshake.
- Provisioning and isolation are substantially current: `deploy.sh`/`provision.sh` create or start Lima, private-key SSH, a non-sudo `ai` user, a restricted mount, pinned VS Code/Codex, a protected appendwatch service, a `0600` environment file, and Codex config with `[agents] enabled = false`.

## Test-suite staleness baseline

- `pytest --collect-only -q src/detours/detour_ai_augment/tests` collects 172 tests, then fails importing `test_e2e_operator.py` because `control_ui.BACKEND_PORT` moved to `control_centre/dashboard/helpers/vars.py`.
- Executing any sampled detour test fails in the autouse fixture before the test body: `conftest.py` monkeypatches removed `control_ui.LIMA_CONFIG_PATH`. The bound value now used by `AiAugmentCtlCtrContext` is in `control_centre/dashboard/helpers/data_models/ai_augment_context.py`.
- Static audit found 42 unique removed module attributes referenced by live tests: 20 in `test_api.py`, 20 in `test_control_centre.py`, and 2 in `test_e2e_operator.py` (117 total references). These include deleted manifest/archive APIs and superseded `RuntimeConfiguration`, `RunJournal`, `ControlPlane`, `SanctionSnapshot`, and control-run-events APIs.
- `test_api.py` mixes current authoritative replay tests with old attempts-directory/manifest and old sanction/control-route tests, especially around lines 3074 onward.
- `test_control_centre.py` largely targets the deleted pre-authoritative architecture. Current replacements are `AiAugmentCtlCtrContext`, `SourceRepository`, `BackendControlClient`, backend control events, authoritative replay projection, and `AttemptRecord`; source compatibility aliases must not be added.
- `test_e2e_operator.py` has useful current scaffolding and six active scenarios, but its assertions still assume synchronous push results. The final happy-path test expects the private commit to precede the public push in the log, which is the reverse of the new `202` workflow.
- The repository's default pytest path excludes this detour. The explicit feature tasks `test-detour-ai-augment-root` and `test-detour-ai-augment-operator` are therefore the relevant gates.

## Workflow audit

| README item | Required behavior | Existing reusable source/test contour | Status / required proof |
|---|---|---|---|
| 1 | Operator provisions or starts AI Agent Runtime | `deploy.sh`; `operator_aivm`; Lima start/redeploy options | Implemented; split fresh-provision and reuse/start operator lanes. |
| 2 | Operator connects over SSH and configures Codex session/environment | private SSH commands, `CodexRunner`, `.openalex.env`, Codex config, appendwatch | Mostly implemented; operator test must verify actual guest identity, permissions, env, versions, and disabled agents. |
| 3 | Operator deploys Backend with one HCR and required env | `BackendSupervisor`, `AiAugmentCtlCtrContext`, `SourceRepository`, control sanction | Implemented for Control Centre orchestration; prove backend is host-side, source DB read-only, detour state temporary/separate, and exactly one active sanction. |
| 4 | Operator initiates LLM request | `ControlCentreController.queue()`, `CodexRunner.start()`, fixed OpenAPI-URL prompt | Implemented for non-interactive Codex CLI. It does not exercise the README's VS Code chat example or rendered-chat review. |
| 5 | Runtime retrieves task with `GET /pull` | reverse SSH forward, `BackendSupervisor.probe_pull()`, existing sanctioned-pull operator test | Connector exists, but current operator test calls from the host rather than proving the AIVM-to-Backend connector. |
| 6 | `GET`: Markdown `200` + strong ETag; matching cache gives `304`; opaque `500` | `authoritative_pull()`, `sanctioned_pull_lines()`, ETag constants, middleware | Missing source contract. No current E2E can truthfully assert it. |
| 7 | Sequential LLM calls/tools; multi-agent disabled | provisioned Codex config, one `CodexRunner` process/session, rollout parser/CAS | Disabled agents can be proved. Provider-side inference sequencing cannot be proved from current Backend/Control Centre telemetry; only single-session ordered rollout events can be audited. |
| 8 | Runtime may `POST /push` | real Codex full-flow test, public push log, rollout/CAS | Connector and push exist. A no-push/crash path exists, but deterministic “LLM chose not to push” control is absent. |
| 9 | `POST`: `202` + `Location`; deferred validation through updated pull/ETag; `409` busy; opaque `500` | `authoritative_push()`, middleware lock, replay log, `execute_attempt()`, private commit | Missing source state machine. Current behavior is synchronous `200`/`422`/`503`. |
| 10 | Runtime receives `410` on pull and/or push and stops/idles | consumed sanction state; remote PID probes/cancel helpers | Missing HTTP behavior and explicit Codex/Control Centre completion handshake. |
| 11 | Operator reviews logs/submissions and repeats or adjusts | replay JSONL, detour DB, CAS, browser history/card, restart/rebuild tests | Strong reusable contour. VS Code rendered-chat review is not represented by the current CLI-based harness and remains a manual acceptance step. |
| 12 | One runtime workflow is limited to one configured HCR profile | one active sanction, one Codex session per run, serialized controller queue | Structurally supported; needs an E2E proving no second namekey enters one session and rehydration creates a distinct run/session. |

## Missing source capabilities that block truthful E2E tests

These are alerts, not requests to add source functions/classes. Most can be implemented by modifying the named existing functions/classes.

1. **Pull representation/state:** modify `sanctioned_pull_lines()` and `authoritative_pull()` to return state-specific Markdown, exact `text/markdown; charset=utf-8`, and opaque `500` on all nonterminal errors.
2. **ETag protocol:** use the existing strong ETag formatter in `authoritative_pull()`; accept `Request` so matching `If-None-Match` returns bodyless `304`; change the ETag whenever task/validation/terminal-visible state changes.
3. **Durable deferred push:** current push has no accepted-but-processing state. Extend existing `AttemptRecord`/`SubmissionCommit` and authoritative projection, or otherwise reuse the existing replay log/table, so request receipt is durable before `202`, processing survives restart, and one pending push is observable as busy. A design decision is required on where processing runs; current source has no worker.
4. **Push response contract:** modify `authoritative_push()` and its OpenAPI metadata to return `202` with `Location: /pull` independent of validation outcome, `409` while prior processing is active, and generic `500` otherwise.
5. **Deferred feedback:** validation rejection must be persisted and rendered only by later `GET /pull`; current `execute_attempt()` already produces the required accepted/rejected/configuration outcome and retry detail.
6. **Terminal contract:** use consumed sanction/accepted-attempt state in existing handlers to return `410` instructions from pull and push. Keep the pull representation Markdown; the README does not prescribe a terminal push content type. Distinguish terminal state from a genuinely absent or corrupt sanction, which remains opaque `500`.
7. **Replay/log projection:** if pull exchanges and their ETags are part of the operator audit trail, add `GET /pull` to the existing middleware/projection path by modifying `AuthoritativeHttpMiddleware` and `project_authoritative_record()`. Current projection rejects pull records.
8. **Control Centre completion:** modify `BackendSupervisor.probe_pull()`, `ControlCentreController._execute_run()`, and/or `_finalize_run()` so a real Codex run completes only after the new deferred outcome is durable and the runtime has encountered `410`, not merely because a synchronous push created an accepted attempt.
9. **Deterministic operator controls:** no existing source hook deterministically holds a push in “processing,” makes the LLM choose no push, records provider-side request concurrency, or exposes a rendered VS Code chat. Busy can be stress-tested with concurrent real requests, but without a durable processing state it will be race-prone. The no-push and rendered-chat cases must remain explicit manual checks unless existing functions are modified to make those states controllable.

No new named source function/class appears necessary for items 1, 2, 4–8: existing handlers, middleware, models, projection, controller, and renderer can be modified. Item 3 is the architectural blocker; it must still obey the no-new-function/class rule if implemented in this task.

## Required operator E2E suite

The scenarios below are the minimum workflow suite. They are intentionally not a Cartesian product: two provisioning lanes plus focused transport/error tests and one full real-Agent contour cover the independent variants.

### E2E-01 — fresh runtime provisioning and configuration

Run the operator suite with `--always-redeploy --yes`. Reuse `operator_aivm`, `deploy.sh`, and `aivm_ai_command()`.

Assert: Lima is newly provisioned and reachable only through the private SSH contour; session user is `ai`; no passwordless sudo; repository mount is inaccessible to `ai`; pinned VS Code/Codex are present; Codex config enables the intended model/tool sandbox but has `[agents] enabled = false`; `.openalex.env` is `0600` and nonempty without logging its value; appendwatch is enabled, active, nonempty, and inaccessible to `ai`.

Covers workflow 1, 2, and the multi-agent part of 7. No missing source capability.

### E2E-02 — existing runtime start/reuse

Run with `--no-redeploy --yes` against a stopped existing `aivm`. Reuse `operator_aivm`'s current start branch and the E2E-01 probes; place a harmless guest marker before stopping and prove it survives start.

Assert: the existing VM starts, is not silently recreated, retains required configuration, and remains ready for a new Codex session.

Covers the “starts” variant in workflow 1 and rehydration precondition in 10/11. No missing source capability.

### E2E-03 — orchestrated backend, sanction, AIVM pull, and conditional cache

Adapt `test_sanctioned_pull_succeeds_through_the_real_dashboard_and_aivm`. Reuse `authoritative_runtime()`, `running_authoritative_dashboard()`, `operator_target()`, `browser_execute_action()`, `wait_for_authoritative_sanction()`, and the existing reverse-forward constants. Perform the public HTTP calls from the `ai` guest, not from the host.

Assert: Backend runs on the Control Centre host; one exact eligible namekey is sanctioned; initial pull is `200`, exact Markdown UTF-8, has a syntactically strong ETag, contains instructions for only that profile, and omits ground truth; matching `If-None-Match` is bodyless `304`; a stale/nonmatching tag returns `200` with the current body/tag.

Covers workflow 3–6 and 12. Blocked by missing capabilities 1–2.

### E2E-04 — accepted push with deferred validation feedback

After a real sanctioned session/rollout exists, stop the Codex process before its own push, keep an approved reverse forward, and submit a deliberately invalid JSON payload from `ai`. Reuse `ControlRun`, public routes, `authoritative_records()`, `stored_attempt_record()`, and existing retry/validation machinery.

Assert: push returns `202` and `Location: /pull`, never `422` and never validation detail; the request is durably logged before processing; a conditional pull using the pre-push ETag eventually returns `200` with a new ETag and Markdown validation guidance; matching the new ETag gives `304`; DB/browser history records one rejected attempt; no card/output is accepted.

Covers validation-error and updated-pull variants in workflow 8–9. Blocked by missing capabilities 3–5.

### E2E-05 — concurrent push conflict

From `ai`, send two overlapping pushes for one sanctioned run. Reuse the existing middleware command lock, public push route, authoritative log, and DB snapshot helpers.

Assert: exactly one request is durably accepted as `202`; the other is `409`; no duplicate commit/attempt/card is created; after processing settles, pull reflects only the accepted request. Repeat after Backend restart to prove pending/busy state is durable.

Covers the `409` variant in workflow 9. Blocked by missing durable processing state; current request-duration lock alone is insufficient for a deterministic operator test.

### E2E-06 — opaque `500` on pull and push unavailability

Parameterize public endpoint. Reuse temporary `authoritative_runtime()` paths so production data remains untouched. For pull, remove/break only the temporary source-DB symlink after startup. For push, change only the temporary authoritative replay log length behind the running process so its append offset check fails before the response can be durably accepted.

Assert: both endpoints return `500` with the same operator-contact message and no exception type, filesystem path, DB detail, rollout detail, appendwatch detail, traceback, or validation guidance in body/headers. The server remains reviewable/restartable.

Covers error variants in workflow 6 and 9. Blocked by status normalization in capabilities 1 and 4.

### E2E-07 — full real Dashboard → AIVM → Codex → Backend happy path

Adapt `test_complete_dashboard_aivm_codex_push_db_and_card_workflow`. Reuse all current dashboard/browser, sanction, replay, commit, CAS, appendwatch, attempt, PID, and card helpers plus `parse_rollout()`/`build_rollout_index()`.

Assert: one queued profile creates one run/session/rollout; ordered rollout contains one agent session and no multi-agent/subagent activity; AIVM observes initial Markdown/ETag; at least one push receives `202`; accepted validation becomes durable; a later pull changes ETag; the runtime encounters terminal `410` on pull or push and exits; commit/attempt/CAS hash/appendwatch/card all agree on run, session, namekey, and attempt; no second profile appears anywhere.

Covers the orchestrated happy path for workflow 3–10 and 12. Blocked by capabilities 1–8. Provider-side request sequencing remains unobservable; the strongest available proof is one ordered rollout with agents disabled.

### E2E-08 — terminal `410` on both public endpoints

After E2E-07 consumes the sanction, call both endpoints from `ai`; for push use any bounded JSON payload. Reuse consumed sanction state, public routes, authoritative log, and remote PID probes.

Assert: `GET /pull` and `POST /push` each return `410` with human-readable instructions to stop and remain idle until operator rehydration; pull remains Markdown; neither call creates a new attempt; the Codex PID is gone; repeated terminal calls remain `410` and do not mutate accepted state.

Covers both allowed terminal endpoint variants in workflow 10. Blocked by capability 6.

### E2E-09 — no accepted push / premature Agent exit

Retain and rename `test_terminal_pre_push_failure_persists_in_db_and_browser_after_restart`. Kill the real remote PID only after proving the initial pull, then restart the dashboard.

Assert: no public push/attempt/card exists; run becomes failed rather than complete; sanction is safely revoked; no orphan PID remains; failure is visible after restart; a newly rehydrated run can be queued.

Covers backend/control robustness when the discretionary push never occurs. Existing helpers suffice. This does not prove an LLM voluntarily chose not to push; no deterministic source capability exists for that distinction.

### E2E-10 — operator review, restart, and one-profile rehydration

Combine/adapt the accepted-flow restart assertions, `canonical_database_snapshot()`, `browser_state()`, replay-log rebuild test, and a second queue/rerun action.

Assert: Backend logs expose pull/push statuses and ETag transitions; rejected/accepted attempts and submission/card are reviewable in the browser; restart/reprojection is idempotent; first and second runs have distinct run/session IDs; each session contains only its one configured namekey; no stale validation or ETag leaks into the rehydrated run.

Covers workflow 11–12 and restart durability. Blocked by pull logging/ETag state and completion capabilities. The README's mandatory rendered VS Code chat review cannot be automated by the current non-interactive `codex exec` harness; retain it as an explicit human sign-off or provide an existing VS Code-operated contour before claiming full coverage.

## Non-workflow operator regressions to retain

The existing signal-chaos, DB deletion/rebuild, browser idempotence, appendwatch topology, and orphan-process tests remain valuable. They should be migrated to current imports/state but are not substitutes for E2E-03 through E2E-10.

## Upstream coverage required before operator runs

Per the task's testing philosophy, add hermetic/regression coverage before asking the operator to discover protocol failures:

1. ASGI state-matrix tests for pull `{200, 304, 410, 500}` and push `{202, 409, 410, 500}`, exact content types/headers, and opaque bodies.
2. ETag tests proving stability for unchanged state and change after rejection, retry, acceptance, and rehydration.
3. Deferred-push replay tests proving receipt-before-`202`, pending/busy durability across restart, exactly-once processing, and no validation leakage through push.
4. OpenAPI tests proving the Markdown/ETag/Location/status contract and continued omission of rollout/appendwatch internals.
5. Control Centre tests proving completion waits for accepted durable state plus terminal `410`, and no-push exit remains failed.
6. Replay-projection tests for any newly logged pull records and exact DB rebuild after deletion.

All can be written against existing source functions/classes after those functions/classes implement the README contract.

## Test migration order

1. Repair `conftest.py` to patch the actual `AiAugmentCtlCtrContext` module binding; preserve the signed-off Human Operator block exactly.
2. Update moved imports in operator tests (`BACKEND_PORT`/SSH/path constants from `helpers.vars`; `RuntimeConfiguration` to `AiAugmentCtlCtrContext`).
3. Remove tests of deleted manifest/archive/journal/control-plane APIs; rewrite their intent against authoritative replay, backend control events, `AttemptRecord`, `SourceRepository`, and `BackendControlClient`. Do not restore source aliases.
4. Implement and pass the upstream HTTP state/replay tests.
5. Migrate existing operator regressions, then implement E2E-01 through E2E-10.

## Verification evidence

- Read-only review covered the README, backend route/middleware/replay/validation code, Control Centre lifecycle, AIVM deployment/provisioning, current tests, feature tasks, main REPL initialization path, and current configs.
- Read-only DuckDB inspection confirmed 46 main-schema tables/views in `data/scisci_process.duckdb`; no writes were made.
- Collection command: `pixi run -e detour-ai-augment pytest --collect-only -q src/detours/detour_ai_augment/tests` → 172 collected before one operator-module import error; exit 2.
- Representative execution of `test_api.py`, `test_control_centre.py`, `test_control_centre_e2e.py`, and `test_pydantic_to_paste.py` each fails at the stale autouse Lima fixture before its first test body.
- No operator test was run: it requires the real AIVM/operator environment and currently cannot collect.

## Decision for the next executor

Do not implement the proposed operator assertions against current public routes. First align the existing source functions/classes with the README contract, especially durable deferred push processing. Then repair stale test imports/architectural assumptions, wire the upstream matrix, and only then run the human-operated E2E suite.
