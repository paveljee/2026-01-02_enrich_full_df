# Codex working guidance for this repository

The user explicitly assigned Codex ownership of this file. Every Codex instance
working here must read, apply, and maintain it without waiting for another
reminder. This is a concise set of durable working agreements, not a task log or
a substitute for current user instructions.

## Keep this file current

- When a correction, preference, or verified project constraint will matter in
  future work, update this file during that task. Consolidate existing guidance
  instead of appending a running history.
- Whenever you read or edit this file, check relevant guidance against the
  current repository and user instructions. Remove or revise stale, superseded,
  or conflicting entries immediately. Before finishing a task that produced a
  new lesson, confirm it is captured and surrounding guidance is still accurate.
- Keep only actionable, generalizable guidance. Do not store transient task
  status, speculative claims, secrets, hashes, or session-specific permissions.
  Explicit instructions from the user in the current session override this file.
- Treat a disappeared or reverted edit as an intentional user rollback unless
  there is clear evidence otherwise. Do not reapply it on your own; inspect the
  current state and continue from the user's chosen version.

## Hard access boundaries

- Git is read-only in this repository, across sessions, with no exceptions.
  Never use Git to stage, commit, restore, reset, checkout, merge, rebase, or
  otherwise write.
- Never run `src.repl` or any detour, by any wrapper or entry point. Never ask
  for approval to run either. This has no exceptions.
- The user-designated DuckDB file is the only permitted data source and the
  single source of truth. Open it with an explicitly read-only connection
  (for example, `duckdb.connect(path, read_only=True)`); never modify it or
  connect to another database. Do not look for, read, create, or touch other
  data files, logs, outputs, or artifacts, including `data/`.
- Code, configuration JSON, and tests may be read for review. This does not
  prohibit edits to them when the user authorizes an implementation task.
  Do not inspect `.aicode/` except this `AGENTS.md`, or inspect prohibited
  data and artifacts while reviewing code.

## Working agreements learned here

- Make surgical edits within the requested scope. Reuse existing production
  helpers and local step logic rather than inventing abstractions or making
  unrelated refactors. Preserve established data flow and serialization.
  OpenAlex HTTP-log serialization currently uses
  `record.model_dump_json(ensure_ascii=True)`; do not propose a second format.
- For OpenAlex HTTP tests, use real `requests.Response` objects and intercept
  requests at the HTTP boundary. Do not replace production step logic with fake
  DuckDB connections, resource objects, or patched step functions.
- Run Python-related commands through `pixi run`. For authorized code changes,
  run relevant tests, Ruff, and mypy when they respect the hard access
  boundaries; report any check that cannot be run. `pixi run` never grants
  permission to launch `src.repl`, detours, or access prohibited artifacts.

## Detour architecture (review only, not execution permission)

- Detour development does not touch `src/cli.py`.
- No detour imports another detour.
- Each detour's direct launch form is
  `pixi run -e $FEATURE python -m src.detours.<module>`; agents must not run it
  or request approval to run it.
- Each detour uses its own database and never touches the main CLI database
  state or another detour's database. Agents must not inspect those databases.
