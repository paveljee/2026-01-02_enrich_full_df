# Tighten API — active Lifecycle alignment and executable specification

## Completed deploy regression (2026-09-07)

- Fresh macOS deployment reaches `Lima instance created` and proves a normal
  session to the Lima jump account, but the first private `ai` connection fails
  with `Stdio forwarding request failed: Session open refused by peer`.
- Live inspection proved that private `aivm-sshd.service` did not exist because
  `cloud-final.service` aborted first: guest `chown root:aivm-audit` was denied
  on the macOS reverse-SSHFS-mounted appendwatch directory. The ProxyJump error
  was only the downstream symptom.
- Preserve the mounted directory's host ownership and mode 0700. The restricted
  audit authorization already invokes only its root-owned dispatcher through
  narrowly scoped passwordless sudo, so the audit account needs no direct DAC
  ownership of the mounted tree. Keep the approved appendwatch `0640` opt-in.
- Added a hermetic regression rejecting mounted-tree `chown`; `bash -n`, Ruff,
  mypy, and all 10 audit-read tests pass. The broader non-root detour suite passes
  with 169 passed, 50 environment-dependent skips, and 3 deselected (excluding
  the separate, stashed/unreviewed BDD collector). Fresh-Lima deployment remains
  for operator confirmation on macOS.

## Authority and constraints

- Authoritative contract: indexed
  `src/detours/detour_ai_augment/README.md`, especially **Lifecycle**.
- Follow `tasks/tasks-20260731-tighten-api/src/TASK.md`; preserve every
  Human-Operator-signed-off comment.
- All commands run through `pixi run -e detour-ai-augment`.
- Git is read-only; never stage or unstage. Main pipeline DB is read-only and
  `src.repl` must never be run.
- Changes remain surgical, piecemeal, incremental, and protected upstream
  before the Human Operator runs costly real E2E tests.

## Indexed README review

- The revised architecture coherently documents this implementation as a
  same-host Control Centre/Backend adapter while permitting other remote
  adapters.
- Dashboard source preparation already occurs during application startup:
  `AiAugmentCtlCtrContext` opens the main DB read-only and derives
  `SourcePopulationRow`s; `ControlCentreController.start` loads researchers
  and linked ground truth before starting the worker. Add explicit coverage;
  do not rewrite this production path.
- Residual prose caveats reported to the Human Operator: Dashboard starts a
  Codex process inside an already-running Runtime, not the Runtime itself;
  graceful cleanup cannot execute after SIGKILL/host loss; and an error that
  prevents server startup cannot expose an HTTP 500.

## Authorized production patches

1. Separate guest/host OpenAlex credentials. Dashboard must pass the host key
   only to Backend; Codex must source the independently provisioned guest env.
   Operator preflight verifies the guest key without overwriting the host key.
2. Add one fixed Backend-host singleton `fcntl.flock`, independent of config
   and replay-log path, while retaining the replay-log descriptor/lock used for
   authoritative append/fsync. Release both on startup failure and shutdown.
3. During Backend configuration, load and retain the configured
   `SourceResearcher`/innerdicts through the read-only source connection.
   Initial `/pull` consumes this Backend-owned prepared state.
4. `BackendSupervisor.start` must fail if it already owns a process; it must
   never silently replace one.
5. A Dashboard run finalizes through Backend IPC after Codex exits, records a
   terminal status, and then winds down owned Codex/SSH and Backend processes
   before `task_done` or the next queue item.
6. Apply the same idempotent teardown on startup errors, execution exceptions,
   active cancellation, queued cancellation, and catchable Dashboard shutdown.
   Queued cancellation immediately removes persisted queue membership and
   becomes canceled without starting Backend/Codex.
7. Guest-idle detection must cover any relevant Codex process owned by the
   Runtime account, not only the exact Dashboard `codex exec` command line.

## Regression obligations

- Host/guest OpenAlex values may differ and are never copied over one another.
- A second Backend with a different config/replay log cannot acquire the
  singleton; lock release permits a later Backend.
- Backend startup prepares source rows once; initial pull does not reopen the
  source DB.
- Normal complete, failed finalization, Backend-start failure, Codex-start
  failure, active cancellation, queued cancellation, Dashboard shutdown, and
  two sequential queue items all prove correct process ownership and ordering.
- Dashboard startup explicitly proves read-only source population and linked
  ground-truth preparation.
- Broad Codex busy detection prevents a new session from starting.

## Pytest-BDD phase

After production alignment and focused regressions:

- Create
  `src/detours/detour_ai_augment/tests/features/detour_ai_augment_lifecycle.feature`.
- Create
  `src/detours/detour_ai_augment/tests/test_detour_ai_augment_bdd.py`.
- Trace all Lifecycle preamble invariants and numbered items. Reuse production
  entry points and extracted/shared test support; do not call pytest test
  functions from other tests.
- Separate hermetic, Linux/root `needs_sudo`, and macOS/AIVM `operator`
  scenarios using existing markers. Add a Pixi meta-task that executes the
  module in the required passes, analogous to the current operator suite.
- Interactive Human/LLM discretion is specified as a supported/observed
  boundary; deterministic claims are tested at the surrounding interfaces.

## Verification

- Run focused tests after each atomic patch.
- Then run complete Detour tests, Ruff, mypy, lock/TOML/diff checks, the new BDD
  runner, and the full applicable pre-commit suite through Pixi.
- Real macOS/Lima operator execution remains the final Human-Operator proof if
  unavailable in this Linux environment; report that limitation exactly.

## Progress

- Rewired the restored task Makefile away from `src/TASK.md`: manifest,
  validation, and their embedded tests now receive the active Detour README **Lifecycle** contract from
  `nl -ba $(TASK) | sed -n '82,159p'`. `TASK` retains file provenance,
  while `TASK_CMD` alone selects the text and emits its absolute source
  line numbers; the tests do not override either variable. Internal Python
  consistently names the configured path `task_path`. The explicitly retired block beginning at line 161 is
  excluded. Embedded Makefile verification passes: **10 manifest tests** and
  **29 validator tests**; a disposable real-README generation confirmed all
  **78** entries and the selected-task hash. Task-related Python identifiers,
  diagnostics, and execution summaries consistently use `task` terminology;
  `"source"` remains only where required by the manifest and notebook schemas.
- Completed the Control Centre **Download DOCX** follow-up without expanding
  Backend IPC. The page passes the exact displayed Markdown to a shared wrapper
  around the established Pandoc/reference-DOCX renderer, reuses the canonical
  card filename transformation, and delivers the resulting bytes through
  NiceGUI. The button is disabled until a nonempty card is displayed, remains
  disabled during rendering, reports render failures, and is cleared when its
  card becomes stale through selection, queue, or rerun changes.
- Added focused helper/UI coverage and a real Playwright regression that opens
  a displayed card, downloads the browser artifact, checks its exact suggested
  filename and DOCX package/content, then proves stale-card clearing. The
  socket-backed Playwright test collects but is skipped in this container;
  direct execution of the same Pandoc/reference path produced a valid 12,631
  byte DOCX containing the supplied literal card text.

- Completed guest/host OpenAlex separation: `CodexRunner` no longer rewrites
  the provisioned guest environment, and operator preflight no longer replaces
  the host Backend key with the observed guest value. Focused Ruff passed;
  focused Control Centre and operator-preflight tests: **5 passed**.
- Completed Backend lifecycle alignment: one fixed host-wide singleton flock,
  retained replay-log lock, startup-time read-only source/namekey preparation,
  and initial pull consumption of the prepared researcher. Backend module:
  **68 passed, 36 skipped**; focused Ruff/mypy passed.
- Completed Dashboard lifecycle alignment: it refuses an already-owned Backend,
  serializes queue items through terminal status and owned-process teardown,
  cleans up startup/finalization/cancellation/shutdown paths, removes canceled
  queued items, leaves the guest OpenAlex environment untouched, and detects
  every runtime-account `codex` process. Dashboard module: **24 passed**;
  focused Ruff/mypy passed.
- Added explicit regressions that Dashboard context derives source population
  through a read-only DB connection and that controller startup prepares both
  source rows and linked ground truth before starting its worker.
- Completed the executable Lifecycle specification: a 9-scenario Gherkin
  feature and pytest-bdd module trace every preamble invariant and all 32
  numbered Lifecycle items. Seven hermetic scenarios pass; the extracted
  `needs_sudo` and `operator` contours are independently marked and collect.
- Added serial Pixi BDD tasks for hermetic, root, and operator passes plus the
  `test-detour-ai-augment-bdd` meta-runner. The root pass cannot execute in this
  Linux container because its no-new-privileges policy prevents sudo; the real
  macOS/Lima operator pass remains Human-Operator execution.
- Enforced the documented UTF-8 NDJSON response content type exactly for the
  initial and terminal `/pull` responses, with regression coverage.
- Verification completed for the work in scope:
  - BDD hermetic pass: **7 passed, 2 deselected**; root and operator scenarios
    collect independently.
  - Complete non-root AI-Augment suite: **175 passed, 51 skipped, 4
    deselected**; separate real-API check skipped because this worker has no
    `OPENALEX_API_KEY`.
  - Card and Control Centre unit modules: **31 passed**. The new Playwright
    regression and complete seven-test UI E2E module skip only because local
    sockets are unavailable in this execution environment.
  - Whole-repository Ruff and mypy: clean (**99 source files** checked by
    mypy). Mode-3 detour: **6 passed**. Pixi lock and staged/unstaged diff
    checks: clean.
- Environment-limited verification is recorded, not hidden: this container's
  no-new-privileges policy prevents the root BDD pass; it has no macOS/Lima
  operator contour; DuckDB cannot download `splink_udfs` and configured binary
  paths point outside this container; Kaleido/Chromium cannot start under its
  process sandbox. The latest top-level pre-commit attempt therefore stopped in
  its main-pipeline pytest leg with **34 failures** caused by unavailable
  `splink_udfs`/absolute external fixture paths; its Ruff and mypy legs passed.
  The complete AI-Augment suite and all static checks pass.
- Final audit preserved the Human Operator's staged/unstaged README state and
  made no staging changes.
