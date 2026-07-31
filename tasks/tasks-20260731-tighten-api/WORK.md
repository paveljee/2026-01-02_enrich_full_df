# Tighten API — planning workbook

## Status

- Implementation complete and verified.
- Reviewed and preserved the human-reviewed staged deployment edits; Git remains read-only.
- Reviewed the inherited setup, current detour README/assets/scripts/API/watcher/tests, prior FastAPI-detour context, and the bundled sample rollout.
- Latest human edit requires surgical implementation: only necessary code changes, with unrelated code and comments untouched.
- Protected appendwatch deployment, the ordered `/push` gate, strict evidence model, and reviewer artifacts are implemented.

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
7. Add focused copied-report, acquisition-order, evidence-schema, generic-error, real-rollout, and report tests; preserve existing appendwatch tests. Deployment relies on its executable runtime probes plus shell syntax validation rather than decorative source-text assertions.

## Verification

- Confirmed the human-authored section was not edited by this work; the AI addition starts after `## how ai understood the spec`.
- Public OpenAPI text does not disclose appendwatch/rollout internals. Excerpt string/list limits are permissive derivatives of the bounded raw request body, not invented web-tool limits.
- `bash -n` passes for `deploy.sh` and `provision.sh`; Ruff and mypy pass for the changed API and focused tests.
- Detour regression result: 69 passed, 3 existing privilege/platform skips. The only warning is from FastAPI's TestClient compatibility shim.
- Real-world coverage uses only the bundled sample Codex rollout: 107 records and 9 eligible web pairs, including search/open/click. Full `/push` acceptance and exact-excerpt rejection run against that rollout with synthetic ground truth; an independent test-side JSONL oracle verifies the exact linked call/output/event objects, hashes, field placement, deduplication, and exclusion of unrelated objects in `response.md`.
- Final scope/whitespace audit passes. `SPEC.md`, `README.md`, `appendwatch.py`, and its existing tests are unchanged.
- Git was used read-only. `src.repl` and the pipeline database were not opened.
