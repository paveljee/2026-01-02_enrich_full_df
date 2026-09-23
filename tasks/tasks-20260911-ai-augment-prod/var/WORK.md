# AI augment production — lifecycle architecture wiring

## Current scope

- Treat `a17256a6bee0d35ccec19efc2c91346d4522f530` and its parent as one architectural revamp. Current `protected/src/architecture.py` is the authority for shape; the lifecycle README may be stale and will be reconciled later.
- Trace changed architecture models through implementation in detour README lifecycle order, Backend startup through dashboard DOCX download / `publish completed`. README is sequencing guidance; architecture is shape authority. Replay log is the principal artifact; detour DB is secondary and reconstructible from canonical log and CAS. DOCX is a dumb card rendering of structured innerdicts supplied through the detour DB query. Only surgical code and existing-test edits; no new/redundant tests. `pre-commit-operator` should pass in the operator environment. Architecture edits require targeted approval.

## Constraints

- Follow `src/TASK.md`; preserve signed-off human comments. Git read-only, no `src.repl`, no main DB/data/artifact inspection. Run project commands with `pixi run -e detour-ai-augment`.
- Never consult the removed former WORK or `HUMANS.md`. This file is new and task-specific.
- User reports pre-architecture-change baseline passes operator pre-commit; this Linux host cannot run macOS/Lima/Chrome operator workflow.

## Implemented

- Kept manual and dashboard-owned `backend.server.main` launches, lock, hash/source checks, namekey choice, replay/DB behavior, and full versus IPC-only Store modes. `AiAugmentBackendContext` now exposes guarded `backend_store`, bound for the Store lifetime (including rebuild) and cleared in `finally`.
- Dashboard `_BackendSupervisor.wait_until_ready` polls `OPTIONS /query` over Unix IPC and, for full mode, HTTP 200 from `GET /openapi.json`. Existing timeout, process-exit, and failed-start cleanup remain. Startup no longer calls `GET /pull`; its later `probe_pull` remains. Early preflight log now says configuration/source validated instead of Backend ready.
- Removed active guest/appendwatch SSH probe from full API lifespan. Later `_capture_push_commit` evidence-read failure handling remains. Stdin session reader remains at startup. Dashboard still reads static Lima configuration for child environment/report path; decoupling later push config is out of scope.
- Wired moved request/response, Store, outerdict, Codex innerdict, validation, commit, RunEvent/Run, RunOutcome, and promise contracts with genuine `@implements` assertions and minimal adapters. `BackendValidationRecord` is the Agent Runtime port attempt; legacy `AgentRuntimeAttempt` remains the internal validation-time projection, not a fake port wrapper. Query projection binds optional validation attempts to outcome response records; derived link is not written to canonical replay log. Protected IPC rehydrates concrete query response from raw protocol record.
- Human Operator approved **only** changing `RunProperty.events` to `@property`; applied one decorator in `protected/src/architecture.py`, retaining the concrete `Run.events` field. Human Operator directed no architecture change for commit reconstruction: canonical commit raw stores pull/push IDs, so concrete factory has an optional `resolve_http_record` keyword and requires it to resolve rich body. The architecture signature's `*` is a keyword-only marker, not `*args`.
- Query reads detour DB projection; dashboard card selects committed innerdicts from that query and renders markdown/DOCX. `publish completed` uses the same card renderer. No separate DOCX data store or new replay-log payload. Existing committed-innerdict behavior is preserved even if dashboard run outcome failed; architecture's `/completed` docstring is descriptive but conflicts with tested behavior, so no unapproved change.
- Agent-added startup tests were removed; existing readiness, response-promise, FakeBackend fixture, and history-only replay assertions changed surgically for the new contracts. No README or main DB edit.

## Verification and known limits

- Final non-browser detour suite: **750 passed, 12 skipped** (`pytest -q -x --tb=short --basetemp=/tmp/ai-augment-final-pytest`, both detour test trees, browser test file excluded). Existing `test_ui.py`: **206 passed**. Browser suite's fixture-only completed-query DB/query test: **1 passed**. Focused replay-history cases: **4 passed** after a single existing assertion was changed to compare durable serialized records, not new optional Pydantic private attempt link.
- Final configured detour mypy: **success, 55 source files**. `ruff check src tests` and `git diff --check`: pass.
- `test_ui_e2e.py::test_completed_grid_row_uses_real_query_ipc` fixture reached host TCP socket creation and failed with `PermissionError` before dashboard execution. `pre-commit-operator` is macOS/Lima/Chrome-only; not runnable here. Default-scope `mypy src tests` in the detour pixi environment has 20 errors in 7 untouched non-detour files; operator's default environment differs, and this TASK restricts project commands to the detour environment. Do not change unrelated files.
- No human-operated E2E was run. Local full-suite reruns temporarily filled `/tmp`; own completed/cancelled pytest temp directories and disposable local caches were cleared, with no repository data touched. Final full run passed from a clean temp base.
