# AI augment production-preparation workbook

## Objective

Work with the Human Operator to prepare the AI-augmentation detour for
production, using its `README.md` lifecycle as the authoritative contract.
No concrete production issue or requested contour has yet been supplied.

## Hard constraints

- Run commands through `pixi run -e detour-ai-augment`.
- Never run or import `src.repl`; inspect its implementation only.
- Treat `data/scisci_process.duckdb` as the sole data source and open it only
  read-only. Do not inspect other files under `data/` or `.aicode/`.
- Git is read-only: never stage or unstage.
- Preserve every inline comment signed off by a human.
- Detour remains isolated: no `src/cli.py` edits, no cross-detour imports, and
  no use of another detour/main CLI database.

## Current state

- Loaded the task, `config.repl.json`, `src/repl.py`, the complete authoritative
  detour README, and the complete prior-task handoff.
- Prior handoff reports the non-BDD suite at 205 passed / 47 skipped / 3
  root-only deselected, with real operator and dashboard smoke contours left
  for the Human Operator.
- Lifecycle contract includes one HCR per Backend run; append-only rollout
  monitoring; replay-log-first event persistence; Backend-owned projection and
  detour DB; post-commit model/rollout/appendwatch validation; follow-up retry
  pulls; terminal 410 pull; archival run-outcome capture; and Control Centre
  orchestration/recovery through Backend IPC.
- Worktree baseline was clean before this workbook was initialized; currently
  only this `WORK.md` is modified. Signed-off comments were inventoried and
  must remain untouched.
- `src.repl --new` parses `PipelineConfig`, opens the configured DB through
  `PipelineManager`, resets schema/state after confirmation, creates a session,
  then transactionally runs the ten registered steps from resource registration
  through card rendering. Its prohibited command has not been run or imported.
- Main-pipeline data flow was traced: XLSX population/name/economy sampling
  builds the outerdict stub; XLSX, DOCX, and SciSciNet matching materialize the
  three JSONL innerdict tables; card building materializes eligibility flags in
  `card_partitions` before rendering outputs.
- Opened only `data/scisci_process.duckdb`, explicitly with
  `duckdb.connect(..., read_only=True)`. Persisted source contract is healthy:
  `xlsx_innerdicts` 307/307 rows/namekeys, `docx_innerdicts` 307/307,
  `ssn_innerdicts` 304/304, union 307, `card_partitions` 307/307. All serialized
  namekeys/innerdicts parsed through production helpers. Draw multiplicity is
  302 single-draw + 5 double-draw, matching the detour invariant.
- Now inspect the production detour and tests before asking for the first
  concrete operator contour/failure.

## Detour baseline

- Production composition: `backend.server` acquires the single-process lock,
  runs either full FastAPI + Flask IPC or IPC-only Flask, and constructs the
  shared `AiAugmentDetourConfig`/context. Full startup proves remote audit
  readability, synchronizes replay projection, and starts stdin session-ID
  handoff before serving.
- Public `/pull` and `/push` exchanges are buffered by authoritative middleware,
  validated as schema 1.1 UUIDv7 records, appended + fsynced before response,
  projected transactionally, and followed by asynchronous accepted-push commit
  work. Projection validates links, CAS bytes/hash/line count, appendwatch,
  submission schema, rollout evidence, retry obligations, and accepted output.
- Flask IPC owns `/query` and run-outcome snapshot routes over a mode-0600 Unix
  socket. The Control Centre never opens the writable detour DB; full mode uses
  the Backend's one connection and synchronization, IPC-only opens it read-only.
- Dashboard source data is validated/cached from the main DB, while run queue
  and journal are NiceGUI-owned. The supervisor starts Backend before Codex,
  hands the discovered session UUID to Backend stdin, records completed/failed/
  cancelled outcome before process teardown, and cleans up owned processes on
  shutdown and failures.
- Protected operator harness creates isolated replay/CAS/detour outputs while
  symlinking the authorized main DB read-only; it hashes production data before
  and after. The suite checks deployed appendwatch topology, drives dashboard
  queueing through Playwright/Codex to terminal 410, validates replay/CAS/IPC
  ordering and integrity, and verifies the rendered researcher card.
- Current `HEAD` is `ac918a50`; the AI-augment implementation is unchanged
  after refactor endpoint `83f7033`. Later commits only change task/chat/Codex
  configuration. Current worktree status includes only this modified workbook.
  The ordinary suite was not redundantly rerun; prior handoff's last result
  remains 205 passed, 47 skipped, 3 root-only deselected.

## Current operator request — historical refactor assessment

Compare the current AI-augment detour codebase with its state on September 7,
2026, immediately before the deep refactor. Deliver an objective account of
changes plus an engineering assessment. Determine the historical boundary from
Git commit timestamps/content rather than assuming a revision. Review production
code, tests, configuration/tasks, and authoritative lifecycle documentation;
quantify and categorize the diff, trace major architectural behavior changes,
and distinguish evidence from judgment. Git remains read-only.

### Assessment plan

1. Identify and justify the September 7 pre-refactor baseline commit.
2. Quantify changed files/lines and group changes by subsystem.
3. Compare architecture, persistence, lifecycle, API, dashboard, and tests.
4. Inspect commit sequence to separate refactor intent from incidental changes.
5. Report benefits, costs, risks, and production-readiness implications.

### Historical boundary

- Baseline: `5bb8db96c8a0738b5e068720a5ccd38b370d7723`, authored/committed
  2026-09-07 08:26:51 UTC, “detour ai augment ipc: open detour db readonly”.
  It is both the last first-parent commit on September 7 and the result of
  `git rev-list -1 --before=2026-09-08T00:00:00Z HEAD`.
- Refactor starts at its child `44447cc` on 2026-09-08 13:28:13 -04:00,
  “detour ai augment: add acme and architecture protocols”, followed by the
  explicitly breaking `cfbd739` and the large protocol/context/lifecycle/test
  sequence through `83f7033` on September 11.
- Comparison target is `5bb8db9..HEAD`; unrelated task/config commits after
  `83f7033` will be identified separately rather than attributed to the detour
  refactor.

### Quantified scope and evidence

- Whole-tree `5bb8db9..HEAD`: 79 files, 11,339 insertions, 7,380 deletions,
  including unrelated post-refactor bookkeeping. Refactor-relevant scope
  through `83f7033` has 64 changed files and 10,468 insertions / 5,807
  deletions: 13 added, 17 modified, 4 deleted, and 30 renamed; 16 renames are
  byte-identical moves. The 20
  first-parent refactor commits run from `44447cc` through `83f7033`; later
  commits are task/config bookkeeping rather than AI-augment implementation.
- Detour source grew from 28 Python/shell files and 17,011 lines to 35 files
  and 19,807 lines (+2,796, about 16%). Tests grew from 11 Python files / 11,704
  lines / 186 named tests to 13 / 13,456 / 199 (+13 named tests).
- Major new structure: a 649-line Acme-inspired Protocol architecture, a
  shared `@implements` static structural checker, a mirrored `protected/`
  subtree, typed context/configuration models, outerdict/commit/query/outcome
  models, a run-outcome control module, a standalone Backend server composer,
  and a protected pytest/operator plugin. Strict mypy and third-party stubs
  were enabled globally.
- A meaningful portion is relocation: deployment, appendwatch, inference
  samples, submission models, and operator assets moved under `protected/`.
  The substantive work centralizes duplicated Backend/dashboard source models
  and lifecycles, uses typed `NameKey`/UUID/path values, and makes Backend
  context own a validated immutable source-population representation.
- Public `/pull` and `/push` semantics remain largely intact. Startup is now
  composed in `backend.server`; FastAPI domain lifespan and Flask IPC are
  separated, with full and IPC-only modes sharing the same entry point.
- Durable/API breaking changes: `/commit` now nests an explicit Codex session,
  rollout, and appendwatch record; accepted output stores commit ID plus the
  exact commit request instead of an attempt ID; projected validation rows were
  replaced by complete agent-runtime attempt records; and `/query` returns full
  attempts/outerdicts/run outcomes rather than flattened accepted-attempt/card
  DTOs. No legacy parser or schema migration was found.
- New `/completed`, `/failed`, and `/cancelled` IPC exchanges capture a fresh
  rollout CAS snapshot and appendwatch report before teardown, append the full
  exchange to the replay log, return 200 for complete capture or 500 for a
  logged partial capture, and remain archival during replay.
- Resource integrity was tightened: both release-map and replay-log configured
  hashes are enforced. This corrects the old behavior that effectively trusted
  the replay log's current hash, but makes hash rollover for that mutable log an
  explicit operational responsibility.
- Test additions cover run-outcome persistence/partial capture/display,
  composition boundaries, strict commit round trips, replay-hash enforcement,
  provenance, and cancellation timing. Prior handoff reports 205 passed, 47
  skipped, and 3 root-only deselected; root and real operator contours remain
  Human Operator-run and are not newly executed for this read-only assessment.
- The BDD layer is a known deferred exception, not part of that standard-suite
  result. The old feature file was deleted and the BDD test moved under
  `protected/`, while its imports, feature lookup, support imports, and Pixi
  tasks still use pre-refactor paths. A direct collection check now fails with
  `ModuleNotFoundError` for the removed `backend.helpers.data_models.server_event`.
  The prior handoff explicitly records this stale BDD wiring as outside its
  scope with WIP in a Git stash.

### Emerging assessment

- Benefits: materially stronger ownership, type-level contracts, source-data
  invariants, identity/provenance, lifecycle auditability, shutdown capture,
  and production-oriented E2E isolation.
- Costs/risks: a hard persisted-format compatibility boundary; roughly 16%
  source growth and substantial protocol ceremony; still-large `api.py` and
  `ui.py`; social rather than technical enforcement of `protected/`; a mutable
  replay-log hash runbook requirement; currently broken/deferred BDD
  traceability; and residual integration risk from a three-day sequence of
  WIP/breaking commits before root/real operator tests are run.
- Production decision required: treat this as a fresh storage/replay epoch or
  provide an explicit migration. Do not deploy it as a drop-in reader of the
  September 7 DB/replay state.

## Next actions

1. [done] Establish the exact September 7 baseline and refactor commit range.
2. [done] Quantify and classify source/test/file changes.
3. [done] Trace architecture, lifecycle, persistence, and API behavior changes.
4. [done] Verify compatibility findings and synthesize the objective report.

## Assessment conclusion

The current design is materially more production-defensible than the September
7 design for a fresh storage epoch: it represents component ownership and
connector contracts explicitly, removes duplicated domain projections, records
commit provenance losslessly, and captures terminal run evidence before
teardown. The September 7 implementation already had the important public
pull/push, replay-first, CAS, appendwatch, retry, and post-validation safety
properties; the refactor strengthens and organizes them rather than replacing a
weak prototype wholesale.

Production should nevertheless be gated on (1) an explicit fresh-epoch versus
migration decision for replay/DB state, ideally with a versioned commit payload;
(2) a documented or automated replay-log hash rollover procedure; (3) repair or
formal retirement of the stale BDD traceability suite; and (4) the outstanding
root appendwatch, real operator, full/IPC-only, and dashboard smoke contours.
Avoid another broad architectural rewrite before those gates: use their concrete
failures to drive smaller changes.

## Current operator request — repository LOC

Counted current tracked first-party Python and shell code under `src/` and
`tests/`, excluding documentation, configuration, data, assets, notebooks,
task/chat history, and vendored `src/github.com` code. Tests are classified by
test directory/name; notably AI-augment `sample_deploy/test_proxy.py` is test
code despite residing under a source subtree. Physical LOC is `wc -l`;
"code-like" LOC excludes blank and full-line `#` comment lines but retains
docstrings and inline comments.

| Component | Prod physical/code-like | Test physical/code-like | Combined physical/code-like |
|---|---:|---:|---:|
| Main pipeline | 10,916 / 9,859 | 5,894 / 5,256 | 16,810 / 15,115 |
| `detour_ai_augment` | 18,806 / 16,702 | 14,457 / 12,685 | 33,263 / 29,387 |
| `detour_mode0_econ_stats` | 2,413 / 2,229 | 1,212 / 1,152 | 3,625 / 3,381 |
| `detour_mode3_pgf_stats` | 979 / 901 | 573 / 510 | 1,552 / 1,411 |
| `detour_step4_breakdown` | 333 / 281 | 672 / 564 | 1,005 / 845 |
| Shared detour package initializer | 3 / 2 | 0 / 0 | 3 / 2 |
| **Total** | **33,450 / 29,974** | **22,808 / 20,167** | **56,258 / 50,141** |
