# Codex working guidance for this repository

The user explicitly assigned Codex ownership of this file. Every Codex instance working here must read, apply, and maintain it without waiting for another reminder. This is a concise set of durable working agreements, not a task log or a substitute for current user instructions.

## Keep this file current

- When a correction, preference, or verified project constraint will matter in future work, update this file during that task. Consolidate existing guidance instead of appending a running history.
- Whenever you read or edit this file, check the relevant guidance against the current repository and user instructions. Remove or revise stale, superseded, or conflicting entries immediately. Before finishing a task that produced a new lesson, confirm the lesson is captured and the surrounding guidance is still accurate.
- Keep only actionable, generalizable guidance. Do not store transient task status, speculative claims, secrets, hashes, or session-specific permissions. Explicit instructions from the user in the current session override this file.
- Keep the repository-root `AGENTS.md` pointer working; this nested file is not automatically discovered from the root.

## Working agreements learned here

- Make surgical changes within the requested scope. Reuse existing production helpers and local step logic before introducing abstractions or moving tightly coupled code. Do not refactor adjacent behavior merely because a narrow change makes it convenient.
- Preserve established data flow and serialization conventions when adding checks or exceptions. Inspect the existing writer or helper first; do not invent a second format for the same model. Avoid opportunistic substitutions of equivalent-looking expressions.
- For OpenAlex HTTP tests, use real `requests.Response` objects and intercept `requests.get` at the HTTP boundary. When testing step behavior, exercise the real DuckDB connection, resource registration, and pipeline logic; do not replace those internals with fake contexts, connections, or patched step functions.
- Run Python tools through `pixi run`. Verify affected behavior with focused tests and lint, and run the project mypy check (`pixi run mypy`) before reporting completion. Report any check that could not run.
