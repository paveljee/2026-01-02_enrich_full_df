# Tighten API: completion record

## Objective

Bring `src/detours/detour_ai_augment/src` and its detour tests into full
alignment with the reviewed, authoritative README workflow.

## Constraints observed

- Every command was run through `pixi run -e detour-ai-augment`.
- `src.repl` was never run or imported; no data artifacts were inspected.
- Git use remained read-only; nothing was staged or unstaged.
- Human-signed inline comments were preserved.
- Main-pipeline tests and schema-1 behavior were not changed.

## Completed implementation

- **HTTP contract:** every finite public `GET /pull` and `POST /push`
  exchange is assigned a Backend UUIDv7, validated as
  `HttpRequestLogRecord(schema_version="1.1")`, and appended/fsynced before
  send through the same durable function used for synthetic commit.
- **Push state:** accepted push changes state to busy, persists `202` with
  `Location: /pull`, exposes persisted `503`/ `Retry-After: 1` pulls while
  busy, and starts post-accept processing only after the accepted record is
  durable. The session UUID is read from stdin and required by the first push.
- **Commit:** Backend copies the discovered session rollout to SHA-256 CAS,
  reads exact appendwatch bytes, creates the exact unsent null-response
  `POST http://invalid/commit` README contour, and appends/fsyncs it before
  any domain, appendwatch, rollout-content, submission, or evidence validation.
  A commit-append failure terminates the Backend process.
- **Replay projection:** DuckDB synchronizes from replay JSONL plus referenced
  rollout CAS, validates linkage and exact Structured Field headers, and
  transactionally projects records, attempts, outcomes, and accepted domain
  effects. Failed domain effects roll back while their committed record and
  opaque outcome remain projected.
- **Outcome pulls:** expected submission/evidence rejection produces persisted
  `200 text/markdown` retry linkage; integrity/configuration/unexpected
  failure produces persisted opaque `500`; acceptance produces persisted
  `410 application/x-ndjson` with accepted innerdict first and optional
  ground truth second.
- **Startup:** fresh Backend state canonicalizes the selected environment
  namekey, proves local appendwatch-report and remote Codex-session-directory
  readability, acquires the replay lock, synchronizes projection, then starts
  the stdin session reader.
- **Dashboard:** queue and run events live only in NiceGUI
  `app.storage.general`. Dequeue starts/replaces a namekey-configured fresh
  Backend, starts a fresh `codex exec`, then supplies the discovered session
  UUID to Backend stdin while Codex is already working. Backend sanction,
  control-push, and control-commit machinery was removed.
- **Surface:** OpenAPI advertises only public `/pull` and `/push`, including
  async/poll statuses, and does not expose integrity internals. The hidden
  read-only dashboard endpoint remains for attempt/card views.
- **Documentation:** corrected the reviewed README appendwatch path to
  `src/control_centre/appendwatch/appendwatch.py`.

## Regression coverage

- Durable before-send public recording and UUIDv7 identity.
- Exact synthetic commit contour and strict header/base64 parsing.
- Push busy/linkage/session behavior and background fatal handling.
- Transaction rollback plus replay restart/projection synchronization.
- Post-commit Markdown, opaque 500, and terminal 410 outcomes.
- Startup input-readability proof and stdin session handoff.
- Exact appendwatch filename/duplicate/ancestor-compromise behavior.
- OpenAPI route/status contract.
- Dashboard-only persisted queue, fresh Backend/Codex ordering, process
  replacement, and stdin handoff.
- Operator E2E contour rewritten to assert replay linkage, CAS metadata,
  appendwatch topology, terminal output, and unchanged production data.

## Verification

- `pixi run -e detour-ai-augment lint`: passed (Ruff; mypy over 92 files).
- Non-root complete detour suite: **108 passed, 49 skipped**.
- Real-API test: correctly skipped because `OPENALEX_API_KEY` is unavailable.
- `git diff --check`: passed.
- Full `pre-commit` task was invoked but Pixi cannot resolve
  `test-detour-mode0-econ-stats` from the `detour-ai-augment` feature
  environment, despite that task existing only in its own feature.
- Manual full-contour audit:
  - repo lint passed;
  - mode-3 detour: 6 passed;
  - main pytest contour: 100 passed, 4 skipped, 34 environment failures from
    unavailable `splink_udfs`/network and a host-only `/Volumes/...` fixture;
  - step-4 failures likewise require unavailable `splink_udfs`;
  - mode-0: 2 passed, 2 failed because managed sandboxing blocks the
    Kaleido/Chromium `shutdown` syscall;
  - official AI-augment root task cannot enter `sudo` under the container's
    no-new-privileges flag; its equivalent non-root suite passed as above.

## Status

Implementation and change-related verification are complete. Remaining
pre-commit failures are task-graph or execution-environment limitations, not
failures in the detour changes.
