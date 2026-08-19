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

Fix the real Control Centre startup contour and add operator-only, full-stack
coverage that cannot pass through fakes.

The observed real failure is:

- `pixi run dashboard` starts the real backend and reports the Control Centre
  ready, but emits no archive-reconciliation summary, creates no detour DuckDB,
  and cannot show a researcher card.
- `ControlCentreController.start()` currently probes the broad AIVM process
  pattern before reconciliation. If any Codex process matches, the method
  returns before archive replay and DB loading. `researcher_card()` also refuses
  while that busy state is set. Startup must reconcile/load canonical state
  before the backend writer starts and before external-busy gating; external
  busy must still prevent new execution and offer Queue only.
- Archive reconciliation remains one canonical pathway and one centralized
  write-intent boundary: attempt directory -> strict replay -> detour DuckDB ->
  dashboard. Do not add a second loader or read cards/history from archives.

## Operator test contour

- Keep the repository-global `tests/conftest.py` unchanged. The explicitly
  authorized detour-local test conftest owns the `operator` marker/options,
  prompt, AIVM deployment/probe fixture, and default skip; ordinary test and
  pre-commit runs skip operator tests unless explicitly selected.
- Add the explicitly authorized
  `src/detours/detour_ai_augment/tests/test_e2e_operator.py`. Its tests run real
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
- Add a Pixi task under the `detour-ai-augment` feature that selects all
  `operator` tests and forwards extra pytest arguments.
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
- The new Pixi `test-detour-ai-augment-operator` task selects the three tests in
  `test_e2e_operator.py`. They cover fresh real archive replay with aggregate
  counts, real Playwright history/card rendering for a canonical accepted
  attempt and all 307 researchers, and restart equality of browser state plus
  every DuckDB table row and sequence. Each test also hashes both production
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
- `control_centre_runs.jsonl` is only transient queued/running process state;
  terminal history comes only from validated DuckDB attempt manifests.
- Preserve all staged/operator-owned changes. Git is read-only and the index
  must not be altered. The proxy static asset and README are out of scope.

## Verification and evidence

- `pixi run pre-commit 2>&1` is green after the operator fixes: Ruff and mypy
  pass, the detour suite reports 165 passed and 4 skipped (the three operator
  tests plus the deliberately disabled multiple-evidence-match test), and the
  separately selected real-API test passes.
- Real macOS operator runs exposed and then cleared the archive-validity and
  DuckDB-lock assumptions: current production archives may contain zero
  current-contract accepted attempts, and direct DB inspection occurs only
  after dashboard shutdown. With those fixes, the fresh rebuild test passes.
  The two browser tests stopped before application assertions because their
  default Playwright launch requested a missing arm64 Chromium headless shell.
  That shell is not the Google Chrome browser used by the real operator. The
  operator browser contour now launches the host's installed Google Chrome via
  Playwright's `chrome` channel in headless mode. The Pixi task is again a
  direct pytest invocation with no browser-cache diagnostics or installation;
  Google Chrome is an explicit operator-host prerequisite.
- Then bring `build/AGENTS.md`, `build/SPECS.ipynb`, and `manifest.json` into
  atomic requirement-to-evidence alignment with TASK and run
  `pixi run --frozen make validate` from the task directory.

## Immediate next action

Run `pixi run pre-commit 2>&1`, then the operator must rerun
`pixi run test-detour-ai-augment-operator` on macOS. Address only concrete
real-contour failures; once it passes, update the TASK evidence artifacts and
run the prescribed task validation.
