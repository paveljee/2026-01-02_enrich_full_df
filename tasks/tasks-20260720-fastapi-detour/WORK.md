## FastAPI detour spec workbook

### Constraints

- Scope is specification only: fill the AI-authored section of `SPEC.md`;
  do not implement the detour in this task.
- Follow the inherited task contract: never run `src.repl`; use only
  `data/scisci_process.duckdb` and only read-only if database inspection is
  needed; do not inspect other data artifacts; git commands are read-only.
- The detour may reuse repo concepts/helpers, but its runtime must not import or
  invoke the main REPL/step registry and must never write to the main database.

### Status

- Completed: read the human section of this task and the referenced prerequisite
  spec.
- Completed: inspected the repository detour conventions, current step-10 subset
  and partition implementation, final-card rendering, config, dependency setup,
  and detour isolation tests.
- Completed: audited current cohorts and required-field missingness directly
  against the source DuckDB in read-only mode.
- Completed: wrote and cross-checked the AI section as an explicit
  API/state-machine/storage/validation/test contract.

### Findings so far

- "partition 4 of subset 2" is the current docx/data-augmentation queue:
  `KTP_PARTITION_DOCX_VALUE = 4`.
- The May prerequisite's `76/231` subset counts are historical and stale under
  the current matching rules. Direct read-only inspection of the current DB
  shows 307 total namekeys and 126 persisted mode-2 partition rows, hence
  subset 1 = 181 and subset 2 = 126. Current subset-2 partition counts are
  partition 1 = 17, partition 2 = 9, and partition 4 = 100.
- Existing read-only analysis detours open the configured DuckDB with
  `read_only=True`, expose a module CLI, avoid `src.repl`, `src.steps`, pipeline
  initialization/runtime helpers, and imports from sibling detours.
- The current project has Pydantic but not FastAPI/Uvicorn as direct dependencies.
- The executor-visible record must be derived from the same selected outerdict
  data and exclusions/order as final cards; the API should not read generated
  DOCX/TXT/ZIP artifacts as an alternate source of truth.
- All 100 current partition-4 namekeys have exactly one DOCX innerdict and fail
  DOCX completeness. Their missing required-field counts are education 71, age
  at first publication 53, academic position 41, gender 38, links 27, social
  capital 25, and place of residence 20.
- All 181 current subset-1 namekeys have complete DOCX ground truth: 178 have one
  complete row, two have two, and one has four. Seeded copies of real
  partition-4 missing-field masks therefore provide realistic eval redactions.
- A separate writable DuckDB should own workflow state, assignments, immutable
  request/submission history, confirmations, commit/rollout evidence, supervisor
  gates, and generated reports. Ground truth for eval rows stays in memory or in
  the read-only source query path and is never returned in the initial payload.

### Verification

- Confirmed the human-authored section remains untouched; the spec change begins
  after `## how ai understood the spec`.
- `git diff --cached --check` reports no whitespace errors.
- Did not run `src.repl`; every database connection used for this work set
  `read_only=True`.
- No application tests were run because this task changes specification/workbook
  Markdown only.
