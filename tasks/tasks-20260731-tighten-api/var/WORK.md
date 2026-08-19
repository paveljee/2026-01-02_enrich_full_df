# Tighten API — current handoff

## Required operating rules

- Read this file and `tasks/tasks-20260731-tighten-api/src/TASK.md` in full
  immediately after every compaction. Together they are the complete context;
  make only focused code lookups afterward.
- Keep this file current and standalone throughout the work. Replace superseded
  content; do not preserve a progress diary.
- `src/TASK.md` is human-owned and immutable. Do not edit the frozen legacy
  SPEC, README, `.env.example`, sample runs, historical submissions/rollouts, or
  ground-truth data.
- Run every command through `pixi run`. Git is read-only. Apply edits only with
  a complete reviewable `pixi run apply_patch <<'PATCH' ... PATCH` command.
- Use only `pixi run pre-commit 2>&1` for final verification; do not run lint or
  component test contours separately. The operator will inspect the full result.
- Keep changes surgical; add no compatibility fallbacks or production modules.
- Human-facing backend wording belongs in `backend/helpers/locale.py`; tests
  belong in `src/detours/detour_ai_augment/tests`.

## Current objective

Implement the six fixes approved after the first real dashboard-launched Codex
execution: one authoritative appendwatch path shared by deploy/dashboard/backend;
a sanctioned real `/pull` readiness probe; DB-only persistence and exact rebuild
of every run ever shown in attempt history, including pre-push failures; complete
test isolation from production attempts; graceful teardown under Ctrl-C and
other termination; and focused reconstruction, chaos, and operator E2E tests,
including one complete dashboard -> AIVM -> Codex -> `/pull`/`/push` -> DuckDB
-> researcher-card workflow.
The manually launched VS Code extension remains outside the sanctioned workflow
and requires no change.

Archive reconciliation remains one canonical pathway and one centralized
write-intent boundary: attempt directory -> strict replay -> detour DuckDB ->
dashboard. Do not add a second loader or read cards/history from archives.

## Observed real execution failure

- A manually launched VS Code Codex chat reached OpenAPI but was correctly
  denied `/pull` because it was not a Control Centre-sanctioned run. The later
  dashboard-launched Sheikh CLI run was separately discovered and sanctioned.
- Sheikh run `537e7c78-6d50-4476-836b-d05807b9841f`, session
  `01a01ac7-d2ef-7041-b66e-b73679fdd0f5`, then failed `/pull` because
  `FASTAPI_DETOUR_APPENDWATCH_REPORT` did not resolve to a readable regular
  host file. No `/push` occurred.
- Backend readiness currently proves only that `/openapi.json` responds.
  `BackendSupervisor` inherits an optional appendwatch environment value, while
  `api.py` otherwise uses a duplicated hardcoded host path; deployment derives
  its own report path from its mount. No runtime handshake binds these paths and
  no preflight checks appendwatch before a Codex process is launched.
- Approved appendwatch binding: `deploy.sh` writes the non-secret guest report
  path into Lima's conventional top-level
  `param.FASTAPI_DETOUR_APPENDWATCH_REPORT` mapping. Provisioning consumes the
  corresponding `PARAM_...` value once; it is not exposed as an ordinary guest
  environment variable. Dashboard reads the
  persisted `~/.lima/aivm/lima.yaml` read-only, maps that guest path through the
  matching `mounts[].mountPoint` to its host `mounts[].location`, validates the
  resulting regular report file, and passes it explicitly to backend. Backend
  has no independent default. Do not use `.env` or a shared runtime handoff
  file for this topology.
- The no-redeploy operator fixture proves only `limactl shell ... true`, so the
  green operator tests did not check appendwatch health or a sanctioned pull.
- The durable run journal contains Sheikh's queued, started, session-discovered,
  rollout-discovered, sanctioned, Codex-exited, and failed events. The detour DB
  contains only an empty `control_centre_archived_attempts` table. The
  reconciler intentionally includes only queued/running journal records, so a
  terminal run without a backend push manifest disappears from history.
- User requirement: every run ever shown in attempt history must remain visible
  after terminal transition, relaunch, and full DB reconstruction, including
  pre-push configuration failures. Preserve one validated canonical persistence
  pathway rather than displaying terminal journal state as a second source.
- Production archives increased from 149 to 159 invalid attempts before this
  run. The latest records are `testserver`/`testclient` empty pushes created by
  `test_missing_rollout_is_generic_503_and_pull_fails_closed` and
  `test_control_mode_without_sanction_fails_both_routes_without_env_fallback`,
  which do not isolate `ATTEMPTS_DIR`. Tests must never write production data.
- Ctrl-C during the active UI timer produced an expected interrupted AIVM probe
  as an unhandled traceback; shutdown must stop refresh work before tearing down
  remote/backend processes.

## Operator test contour

- Keep the repository-global `tests/conftest.py` unchanged. The explicitly
  authorized detour-local test conftest owns the `operator` marker/options,
  prompt, AIVM deployment/probe fixture, and default skip; ordinary test and
  pre-commit runs skip operator tests unless explicitly selected.
- The explicitly authorized
  `src/detours/detour_ai_augment/tests/test_e2e_operator.py` runs real
  dashboard, backend, archive replay, DuckDB, AIVM, and Playwright surfaces.
  Production collaborators must not be replaced by fakes.
- Cover three independent contours: fresh isolated DB rebuild and aggregate
  reconciliation log; browser exposure of 307 rows and a real source-backed
  researcher card, plus DuckDB-backed attempt history whenever strict replay
  yields a current-contract accepted attempt; restart/idempotency with no
  duplicate attempts and unchanged browser/database state. Production archives
  are inputs, not fixtures whose validity may be assumed.
- Isolate writes by using a temporary config and a symlink to the real read-only
  source DB, so the sibling detour DB and output/state paths are temporary.
  Never modify the operator's real detour DB or archived attempts.
- The Pixi task under the `detour-ai-augment` feature selects all `operator`
  tests and forwards extra pytest arguments.
- The operator contour asks whether AIVM should be redeployed before each test,
  with No as the current default. Support `--always-redeploy`,
  `--always-redeploy --yes` for noninteractive confirmation, and an explicit
  no-redeploy option. A declined/default-disabled redeploy continues only if the
  existing AIVM is reachable. Never remove the Lima instance after tests.
- Every operator invocation must explain its sanctuary before prompting or
  applying an explicit redeploy/no-redeploy choice: within repository
  production data the contour uses only the main database and archived attempts,
  both read-only; complete pre/post hashes cover both entire production data
  trees; the Lima `aivm` instance is ephemeral and outside that preservation
  guarantee.
- Redeployment invokes the repository `agent_runtime/deploy.sh` contour with
  `REPO_DIR` and the real `.env` `OPENALEX_API_KEY`. The deploy script may accept
  `--yes`; successful provisioning/verification exits 0 without opening an SSH
  shell, while declining replacement exits 1.
- Every operator test requires the real AIVM to be present/reachable. Lima is
  provisioned only through the deployment script, not mocked or recreated by
  test internals.

## Relevant implementation constraints

- The dashboard now accepts `--config` and passes that exact path to the
  separately supervised backend module. Operator tests therefore use a
  temporary config, source-DB symlink, sibling detour DB, state path, and output
  path while retaining the production startup/replay/rendering implementation.
- Startup reconciliation now runs before the initial external-Codex busy probe,
  through the controller's single reconciliation call site. It creates and
  loads canonical DuckDB state even when an external run is active; later busy
  observations still request one safe idle rescan. Remote busy detection now
  matches the complete centralized detour Codex exec command rather than every
  process containing `codex`.
- The detour-local test conftest owns the operator marker, no-default prompt,
  `--always-redeploy`, `--no-redeploy`, and `--yes`. Its autouse fixture invokes
  repository `deploy.sh --yes` before each operator test when confirmed, always
  probes the resulting/current `aivm`, and never tears it down. `deploy.sh`
  accepts `--yes`, exits 1 when replacement is declined, and exits 0 after
  verification instead of opening an SSH shell.
- The Pixi `test-detour-ai-augment-operator` task selects the operator tests in
  `test_e2e_operator.py`. Its existing three tests cover fresh real archive
  replay, Playwright history/card rendering, and restart equality. Each test
  also hashes both production
  data trees (`REPOSITORY_ROOT/data` and the detour-local `data`) after optional
  deployment and after test cleanup, asserting exact tree/content equality. The
  complete-tree hashes use concurrent per-file digests combined in sorted path
  order; do not replace this with a metadata cache or narrow the protected
  trees. No production collaborator is replaced.
- Backend and dashboard currently use ports 8612 and 8611. Operator tests must
  own/validate the real contour and terminate spawned processes cleanly without
  removing AIVM.
- The canonical archive implementation already performs strict HTTP-log replay,
  chronological restoration, idempotent DuckDB markers, aggregate-only invalid
  logging, and DuckDB-only terminal history. Preserve those contracts.
- `control_centre_runs.jsonl` is the durable reconstruction input for every
  dashboard-visible control run, including terminal pre-push failures. A
  validated projection of those runs belongs in DuckDB; the dashboard reads
  all attempt history from DuckDB and must reconstruct it exactly from the
  journal after deletion of the detour database. Push manifests remain the
  canonical reconstruction input for push-attempt payload/response content.
- The private backend write endpoint used to project run-journal events into
  DuckDB is authenticated with a per-dashboard-process control token. Port 8612
  is reverse-forwarded into AIVM, so a hidden route alone would be agent-callable;
  the token is passed only to the host backend process and is never placed in
  Lima or exposed through OpenAPI.
- Preserve all staged/operator-owned changes. Git is read-only and the index
  must not be altered. The proxy static asset and README are out of scope.

## Current implementation state

- The six approved fixes are implemented. `deploy.sh` persists the appendwatch
  guest path in Lima's top-level `param` mapping; dashboard maps it read-only
  through exactly one persisted mount and passes the validated host report to a
  backend that has no independent path default. The abandoned `.env` and shared
  runtime-file approaches are absent.
- A sanctioned `/pull` is probed after sanction and before waiting for Codex.
  Failure cancels Codex and records durable failed history.
- The journal is the immutable reconstruction input, while its ordered DuckDB
  projection is the sole dashboard history source. The authenticated hidden
  backend endpoint rescans archived attempts before DB writes. Terminal
  pre-push runs persist, restart, and rebuild exactly after detour-DB deletion;
  accepted run events deduplicate against accepted attempt manifests.
- Backend and SSH subprocesses are owned and reaped. Graceful shutdown cancels
  active Codex work and persists terminal failure; backend watches its dashboard
  parent; restart terminates abandoned guest PIDs and repairs SIGKILL-interrupted
  run history.
- Ordinary tests use temporary Lima topology and runtime-local attempt roots, so
  they no longer create production attempts. Focused roundtrips cover the hidden
  authenticated event endpoint, immutable-prefix/idempotent persistence, exact
  DB reconstruction, appendwatch propagation, failed sanctioned pulls, and
  shutdown during Codex startup.
- Production allows archived-attempt symlinks through
  `ALLOW_ARCHIVED_ATTEMPT_SYMLINKS=True`. Every operator test fails immediately
  if that setting is False. Archive contours symlink read-only production
  attempt entries into a temporary attempts root; newly generated attempts are
  real temporary directories. No test manufactures the disabled mode.
- `pixi run pre-commit 2>&1` completed successfully after the implementation:
  ruff, mypy, the main tests, detour tests, and configured real-API test all
  passed. Operator tests are intentionally separate and have not been executed
  in this Linux session.

## Current operator E2E boundary

- Proven: isolated detour DB creation, strict production-archive scan and
  aggregate reconciliation, a real UI summary reporting 307 researchers, one
  real source row searchable in the grid, source-backed researcher-card
  rendering, clean browser console, complete DB/browser restart equality,
  repeatable process restart, AIVM reachability, real backend supervision, and
  unchanged complete production data trees. The test does not enumerate all
  307 rows in Chrome.
- Six additional real operator contours are implemented but await execution on
  the operator machine: existing-AIVM appendwatch topology; sanctioned `/pull`;
  terminal pre-push persistence; exact DB/history reconstruction after DB
  deletion; SIGINT/SIGTERM/SIGKILL recovery; and one complete dashboard -> AIVM
  -> Codex -> `/pull` -> `/push` -> DuckDB -> researcher-card workflow.
  Queue/serial dequeue/rerun, evidence retry/withdrawal, and generated TXT/DOCX
  remain additional operator contours.

## Immediate next action

Update the TASK atomic requirement-to-evidence artifacts and run its prescribed
validation. The operator then runs `pixi run test-detour-ai-augment-operator` on
the real control machine/AIVM; preserve both production data trees read-only.
