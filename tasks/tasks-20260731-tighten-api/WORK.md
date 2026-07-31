# Tighten API — planning workbook

## Status

- Specification complete; implementation is not authorized in this task.
- Reviewed the inherited setup, current detour README/assets/scripts/API/watcher/tests, prior FastAPI-detour context, and the bundled sample rollout.
- Latest human edit requires surgical implementation: only necessary code changes, with unrelated code and comments untouched.

## Confirmed findings

- The mounted macOS project path is already denied to the `ai` user at its parent directory; root can use that protected mount for appendwatch code and reports, and the host backend can read the same files.
- Current appendwatch provides append-only monitoring, sticky `COMPROMISED` state, fail-closed handling for monitoring gaps, and atomic report replacement, but it is not provisioned or managed by systemd.
- Current `/push` accepts exactly the nine annotation keys with non-null values, writes the submission plus ground truth, and performs no rollout or appendwatch checks.
- Sample Codex web activity links a `response_item/function_call` (`namespace: "web"`, `name: "run"`) to a `response_item/function_call_output` by `call_id`; `event_msg/web_search_end` with the same ID is additional metadata. Web search, open, and click all use the same web `run` call family.
- Human-spec ordering is authoritative: SCP the configured rollout first, atomically/version-copy the appendwatch report second, then parse that immutable report copy. Only an OK entry for the copied rollout permits payload/evidence validation.
- Missing rollout-path configuration must be generic to the runtime but explicit in backend logs; failed evidence validation must likewise return only brief generic guidance.

## Implementation plan captured in SPEC

1. Stage appendwatch in the protected mounted control directory; persist it with root systemd and verify it is active before opening the `ai` shell, without redesigning private SSH.
2. Reuse appendwatch's current atomic tree report and OK/COMPROMISED behavior; add no second report/state system unless proven indispensable.
3. Keep the chat-specific rollout path manual in root `.env` and reuse the existing deployment SSH/key/report settings without a new configuration subsystem.
4. Enforce `/push` order: SCP rollout, version-copy the existing tree report, check only that copy, parse the archived rollout, then run Pydantic.
5. Extend each of the nine fields to carry `value` plus exact `web_search_excerpts`; accept matches only from linked Codex web `run` call/output pairs for search/open/click.
6. Archive the rollout/report evidence and emit a field-oriented Markdown report containing complete escaped call/output objects, AI output, and ground truth.
7. Add only focused deployment, copied-report, acquisition-order, evidence-schema, generic-error, and report tests listed in `SPEC.md`; preserve existing appendwatch tests.

## Verification

- Confirmed the human-authored section was not edited by this work; the AI addition starts after `## how ai understood the spec`.
- `git diff --check` and `git diff --cached --check` pass for `SPEC.md` and `WORK.md`.
- No production code or data was changed; no application tests were run for this Markdown-only task.
- Git was used read-only. `src.repl` and the pipeline database were not opened.
