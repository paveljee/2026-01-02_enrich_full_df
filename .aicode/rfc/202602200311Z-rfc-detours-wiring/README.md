# RFC: Self-Contained Detour Modules in `src/detours`

**Timestamp (UTC):** 2026-02-20 03:11Z  \
**Author:** GPT-5 Codex (OpenAI)

## Task summary
Define how to add detours as standalone, reproducible pipeline variants under `src/detours`. A detour is an independent module that runs end-to-end logic on its own, without coupling to `src/cli.py` and without coupling to other detours. This RFC specifies the first detour (`step4_breakdown`) and the test coverage required to ship this model safely.

## Goals
- Introduce detours as first-class, standalone execution units.
- Keep detour implementation simple: one module, one full flow.
- Preserve strict separation between detour work and `src/cli.py`.
- Preserve strict separation between one detour and another.
- Enforce strict step-identical behavior with main CLI pipeline until the intentional deviation point.
- Enforce database isolation so each detour uses its own DB and never overlaps with main pipeline DB state.
- Add test coverage that validates behavior, isolation, and reproducibility.

## Non-goals
- Reworking `src/cli.py` to run or route detours.
- Building a registry/discovery system for detours.

## Architecture

### Package layout
`src/detours` contains only:
- `src/detours/__init__.py`
- one module per detour, for example `src/detours/detour_step4_breakdown.py`

No registry, base class, dispatcher, or shared orchestration code belongs inside `src/detours`.

### Isolation boundaries
Detours are isolated at four levels:
1. Detour vs CLI: detour development does not touch `src/cli.py`; CLI development does not touch detours.
2. Detour vs detour: no detour imports another detour.
3. Runtime entrypoints: each detour is launched directly via `python -m src.detours.<module>`.
4. Database state: each detour uses its own DB instance/path and never touches main CLI DB state or another detour DB.

### Optional helper policy
`src/helpers/detours_runtime.py` is optional.

Use it only when all conditions are true:
- The helper is technical/infrastructural (not business flow logic).
- Reuse across multiple detours is real and immediate.
- Copy/paste would clearly reduce correctness or maintainability.

If those conditions are not met, keep logic inside each detour module and do not add shared helper code.

## Detour module contract
Each detour module should expose:
- `DETOUR_ID: str`
- `DETOUR_NAME: str`
- `DETOUR_DESCRIPTION: str`
- `run_detour(config, interactive=False, diagnostics=None) -> DetourResult`

`DetourResult` should include:
- `success: bool`
- `steps_completed: list[str]`
- `summary: str`
- optional `metadata` for deterministic assertions

Contract expectations:
- Deterministic output for fixed seed/config.
- Explicit logging/printing of major stages.
- No reliance on a global detour index/registry.
- Behavior must match main CLI step behavior exactly until the detour's declared deviation point.
- Any deviation from main steps must be intentional, explicit, and directly tied to detour goals (never incidental).

## Execution model
Detours are run directly as modules.

Canonical example:
- `python -m src.detours.detour_step4_breakdown`

Implications:
- No `--detour` wiring in CLI.
- No runtime lookup table for selecting detours.
- Usage is explicit by module name.

## First detour: `detour_step4_breakdown`

### Intent
Create a reproducible detour that runs pipeline work through step 4 (inclusive), then emits a comprehensive data breakdown and exits.

### Expected behavior
1. Initialize runtime/config similarly to normal step execution context.
2. Run steps 1 through 4 in order.
3. Do not execute step 5 or later.
4. Keep step semantics for steps 1 through 4 strictly identical to main CLI behavior.
5. Produce a comprehensive, stable, human-readable breakdown.
6. Return a structured `DetourResult`.

### Breakdown content requirements
Output must include:
- Total rows in active working tables/dataframes at detour end.
- Row counts by `hcr.filename`.
- Null/empty statistics for key step-4 output columns.
- Value distributions for enrichment outputs (economy/priority-related fields).
- Integrity summary (e.g., unique names, duplicate indicators).

Output must be deterministic in section order and row ordering.

## Testing strategy
Testing should match the no-registry, self-contained module model and use one test module per detour.

For this detour, use a single file:
- `tests/test_detour_step4_breakdown.py`

That single module should cover all required checks:
- Contract checks: metadata fields exist and `run_detour(...)` returns expected result shape.
- Entrypoint check: `python -m src.detours.detour_step4_breakdown` executes successfully.
- Isolation checks: detour does not import `src/cli.py` or other detour modules.
- DB isolation checks: detour DB is distinct from main CLI DB and from any other detour DB.
- Pre-deviation identicality checks:
  - Run main flow and detour flow in separate DBs with same inputs/seed.
  - For each step up to and including step 4, compare expected intermediate tables/views directly across both DBs.
  - Assert strict identicality of schemas and row contents (with deterministic ordering rules).
- Post-deviation checks:
  - Assert step 5+ artifacts are absent in the detour DB when not part of detour goals.
  - Assert breakdown output exists and core aggregates are correct.
- Reproducibility checks: repeated runs with fixed config/seed produce identical outputs.

## Implementation plan
1. Create `src/detours/__init__.py`.
2. Add `src/detours/detour_step4_breakdown.py` with full self-contained flow.
3. Ensure detour uses a dedicated DB that cannot overlap with main CLI DB.
4. Add `src/helpers/detours_runtime.py` only if a clearly justified technical helper emerges.
5. Add `tests/test_detour_step4_breakdown.py` covering all contract, isolation, identicality, and output assertions.
6. Run project checks and test suite.

## Acceptance criteria
- `src/detours` contains only `__init__.py` and detour modules.
- `detour_step4_breakdown` runs directly via `python -m src.detours.detour_step4_breakdown`.
- No registry/discovery layer is introduced.
- `src/cli.py` is unchanged for detour support.
- Detours remain isolated from each other.
- Detour DB state is isolated from main CLI DB state and from other detour DBs.
- For steps up to the declared deviation point, detour outputs are strictly identical to main CLI outputs.
- `tests/test_detour_step4_breakdown.py` passes with all required checks.

## Risks and mitigations
- Risk: duplicated utility code across detours.
- Mitigation: allow optional `src/helpers/detours_runtime.py` only for clearly meaningful, technical reuse.

- Risk: output assertions become brittle.
- Mitigation: assert both stable section headers and structured result metadata.

- Risk: accidental coupling to CLI or other detours.
- Mitigation: add explicit import-isolation tests and keep module entrypoints direct.

- Risk: hidden drift from main-step behavior before deviation.
- Mitigation: compare intermediate tables/views across two separate DBs step-by-step up to the deviation point.

## Rollout notes
- Land one detour first (`detour_step4_breakdown`) as the reference pattern.
- Use that pattern for future detours without introducing registry/dispatcher complexity.
- Keep detour architecture additive and isolated.

## Implementation log (full chat work record)

This section documents the full work completed in this thread, including RFC rewrites, implementation, regressions discovered, and test-harness hardening. It is intentionally detailed so future detour work can reuse both the code and the process lessons.

### 1. RFC creation and repeated design corrections (before implementation)

Initial work created a new RFC directory and README at:
- `.aicode/rfc/202602200311Z-rfc-detours-wiring/README.md`

The RFC then went through multiple rounds of correction based on user feedback:

- **Round 1:** initial detours RFC proposed a registry/base model under `src/detours`.
- **Round 2:** corrected package layout to keep `src/detours` minimal and move potential shared runtime logic to `src/helpers/detours_runtime.py`.
- **Round 3:** removed REPL/CLI dispatch assumptions and documented direct module execution:
  - `python -m src.detours.detour_step4_breakdown`
- **Round 4:** removed registry/discovery entirely and documented each detour as self-contained and isolated from:
  - `src/cli.py`
  - other detours
- **Round 5:** rewrote the RFC holistically (instead of patch-by-patch constraints) so the document matched the intended architecture as a coherent design.
- **Round 6:** clarified non-goals wording (removed the awkward “Implementing detours in this RFC” line).
- **Round 7:** added strict pre-deviation identicality requirements:
  - detours must use the same step semantics as the main pipeline until the detour’s declared deviation point
  - deviations are allowed only if explicitly dictated by detour goals
- **Round 8:** added database isolation requirements:
  - one DB per detour
  - no overlap with main pipeline DB
  - no overlap with other detours
- **Round 9:** rewrote testing strategy to require a single per-detour test module (`tests/test_detour_step4_breakdown.py`) covering:
  - contract
  - entrypoint
  - import isolation
  - DB isolation
  - step-by-step pre-deviation identicality
  - post-deviation behavior
  - reproducibility

### 2. First implementation of detour package and example detour

Implemented the first detour package and example module:

- `src/detours/__init__.py`
- `src/detours/detour_step4_breakdown.py`

Key behavior in the initial detour implementation:
- Direct module entrypoint via `python -m src.detours.detour_step4_breakdown --config <path>`
- Dedicated detour DB/state files derived from config names using a detour suffix
- Reuse of the exact existing step execution path via:
  - `STEP_REGISTRY`
  - `run_step(...)`
- Execution of steps 1 through 4 only:
  - `01_register_resources`
  - `02_load_xlsx`
  - `03_infer_names`
  - `04_add_economy_priority`
- Step-4 breakdown output including:
  - total rows
  - row counts by `hcr.filename`
  - null/empty stats for selected columns
  - priority / priority group / income group distributions
  - integrity summary
- `DetourResult` metadata recording:
  - steps completed
  - detour DB/state paths
  - (later) diagnostics path

### 3. Initial detour test module implementation

Implemented `tests/test_detour_step4_breakdown.py` as the single test module for the detour, including:

- **Contract and isolation checks**
  - module metadata constants present
  - `run_detour(...)` returns expected shape
  - AST import checks to ensure no `src/cli.py` import and no cross-detour import

- **DB isolation check**
  - detour DB path and state path differ from main config DB/state paths
  - detour DB contains step-4 view and does not contain step-5 artifacts such as `samples`

- **In-process pre-deviation identicality**
  - runs main and detour step functions in separate DBs
  - compares expected tables/views after each step (1–4)
  - compares schemas and row content
  - compares per-step artifact hashes in the two in-process runs

- **Entrypoint/reproducibility**
  - runs the detour via `python -m src.detours.detour_step4_breakdown`
  - checks for expected output sections
  - (later refined) checks reproducibility of deterministic output portions

### 4. Output-style alignment with main REPL

The user correctly pointed out that the detour output did not “look” like the main REPL:
- missing Rich-styled logs
- missing detailed step messages
- different CLI feel

Detour implementation was then updated to align its look/behavior with the main REPL conventions:
- Rich console output (`rich.console.Console`)
- step log lines emitted through the same `run_step(...)` flow
- printing per-step messages (including “Artifacts dumped” messages)
- execution metrics table (Rich `Table`) with peak RAM usage
- diagnostics report path output
- support for `--non-interactive` switch (detour defaults to rich-styled output)

Tests were updated accordingly to assert step logs and metrics presence.

### 5. Step-4 artifact hash regression discovered by manual run comparison

The user manually compared real artifact hashes from:
- detour run diagnostics session `20260219_225124`
- main `pixi run repl` diagnostics session `20260219_225400`

Observed regression:
- step-4 artifact hashes differed for:
  - `04_add_economy_priority_population_with_economy_df.csv`

Investigation performed:
- compared file sizes (same)
- compared headers (same)
- ran row diffs
- found differences in JSON array ordering within step-4 outputs (same elements, different order)

Root cause:
- `src/steps/step_04_add_economy_priority.py` used unordered aggregation:
  - `list(DISTINCT m.country)`
- JSON arrays and JSON payload values could vary in order across runs/processes

### 6. Determinism fix in step 4

Fixed `src/steps/step_04_add_economy_priority.py` to sort country lists before JSON serialization:

- `ktp.hcr_world_bank_economies`
  - changed to use `list_sort(list(DISTINCT m.country) ...)`
- `ktp.hcr_world_bank_economies_match`
  - changed JSON object value to use `list_sort(list(DISTINCT m.country))`

Effect:
- step-4 artifact content becomes deterministic for country-list ordering
- detour vs main artifact hashes can now match reliably across separate processes

### 7. Test harness hardening after the step-4 regression

The user correctly challenged the first subprocess-level test as patchy and not reference-grade.

The harness was refactored to be cleaner and reusable for future detours:

- Replaced ad-hoc subprocess comparison with a structured subprocess runner:
  - `_run_pipeline_subprocess(config_path, mode="main" | "detour")`
- Subprocess now emits a machine-readable `SNAPSHOT::<json>` line
- Added snapshot parsing helper:
  - `_parse_snapshot(stdout)`

Snapshot contents include:
- `artifact_hashes_by_step` for all steps up to deviation (1–4)
- `db_objects` snapshot for tables/views in the DB:
  - object type (table/view)
  - row count
  - schema hash
  - stable data hash (order-normalized)
- DB file path used by the run

New reference-style invariant test added:
- `test_pre_deviation_artifact_hash_parity_against_main`
  - runs both main and detour in subprocesses
  - compares `artifact_hashes_by_step` across all pre-deviation steps
  - compares `db_objects` snapshots
  - asserts DB-path isolation

This was added in addition to the in-process step-by-step table/view equality test.

### 8. Slow real-config equivalence test added

Per user request, added a slow test that validates pre-deviation equivalence using the real project config:

- `test_slow_real_config_pre_deviation_full_equivalence`
- marked with `@pytest.mark.slow`
- uses `config.repl.json` (copied to a temp config with temp output/DB/state targets)
- runs both main and detour subprocess harnesses
- compares:
  - all pre-deviation artifact hashes
  - DB object snapshots (schema + data hashes)
  - DB path isolation

This provides a high-confidence integration check against real data while remaining optional.

### 9. Slow-test execution policy fixed (skip by default)

The user correctly pointed out that marking a test `slow` does not automatically prevent it from running in default pytest runs.

Fix implemented:
- added `tests/conftest.py` with collection-time logic:
  - slow tests are skipped unless `-m slow` is explicitly provided

Also updated `pyproject.toml`:
- registered pytest marker:
  - `"slow: long-running integration tests against real config/data"`

Result:
- `pixi run pre-commit` no longer runs the slow test by default
- slow test can be run explicitly via:
  - `pixi run test "-m slow tests/test_detour_step4_breakdown.py"`

### 10. Test output robustness fixes (ANSI / Rich formatting)

The detour contract test originally failed in some environments because Rich styling inserted ANSI escapes into captured stdout.

Fix:
- Added ANSI stripping helper in `tests/test_detour_step4_breakdown.py`
- Updated text assertions to check against stripped output (`plain_stdout`)

This keeps tests stable across terminals and environments while preserving Rich output in implementation.

### 11. Test isolation fix for global mutable name-column mapping

A major environment-dependent test failure occurred in the main worktree but not in the detour worktree:
- `test_csv_sample_validation.py` ran (with real data) in main worktree and populated `HCR_XLSX_NAME_COLS`
- detour contract test then reused that global state against synthetic test XLSX files
- step 3 failed with a DuckDB binder error (`hcr.firstname_middlename` vs `hcr.first_name`)

Root cause:
- global mutable state leakage through `src.helpers.vars.HCR_XLSX_NAME_COLS`

Fix:
- added an `autouse` fixture in `tests/test_detour_step4_breakdown.py` that:
  - snapshots `HCR_XLSX_NAME_COLS`
  - clears it before each detour test
  - restores it after each test

This made the detour test module stable regardless of whether other tests populate the mapping.

### 12. Main-vs-detour subprocess baseline isolation improvement

Critical review identified that the subprocess harness imported detour code even in `mode="main"`, which weakens the “main baseline is independent” property.

Fix:
- moved detour import (`run_detour`) inside the `mode == "detour"` branch of the subprocess script

This keeps the `mode="main"` subprocess closer to an actual independent main-pipeline baseline.

### 13. DB/data hash normalization improvements in tests

Critical review also identified a null-normalization collision risk:
- normalizing nulls to `"<NA>"` could collide with a literal string value of `"<NA>"`

Fix:
- changed normalization sentinel to a dedicated test sentinel string in:
  - in-process dataframe normalization (`_normalize_frame`)
  - subprocess DB snapshot hashing (`stable_frame_hash`)

### 14. Temp-directory containment for test artifacts and diagnostics

The user requested that detour tests not write diagnostics/artifacts into the repository `data/` folder.

Fixes applied in `tests/test_detour_step4_breakdown.py`:
- subprocess runs are launched with:
  - `cwd=config_path.parent` (pytest temp directory)
- subprocesses receive a `PYTHONPATH` including repo root so `src` imports still work
- in-process detour contract test uses `monkeypatch.chdir(config_path.parent)`
- AST read path changed to use `REPO_ROOT` absolute path so source loading still works after cwd change

Result:
- diagnostics and step artifacts produced during detour tests are written under pytest temp dirs
- no test artifact leakage into repo `data/` from this test module

### 15. Validation commands run during the thread

A large number of validation runs were executed while iterating. The key ones included:

- `pixi run test tests/test_detour_step4_breakdown.py`
- `pixi run ruff`
- `pixi run mypy`
- `pixi run pre-commit` (adopted as the preferred validation command)
- `pixi run test "-m slow tests/test_detour_step4_breakdown.py"` (explicit slow test run)
- `pixi run test tests/test_csv_sample_validation.py` (after creating real-data symlinks)

Per user request, `pixi run pre-commit` became the default “final verification” path because it reduces drift between lint/type/test checks.

### 16. Real-data symlink setup in this worktree for CSV validation test

To make `tests/test_csv_sample_validation.py` runnable in this detour worktree, symlinks were created under `data/` to point at the real datasets referenced by `config.repl.json`:

- `data/2024-Historical-Highly-Cited-Researchers-lists - final`
- `data/samples`
- `data/OGHIST_2025_07_01.xlsx`

After creating symlinks, `pixi run test tests/test_csv_sample_validation.py` passed in this worktree.

### 17. Net result of implementation and hardening

By the end of this thread, the following was achieved:

- RFC fully rewritten and aligned with the intended detour architecture
- First detour implemented as a self-contained module:
  - `src/detours/detour_step4_breakdown.py`
- No registry/discovery system introduced
- Detour runs directly as a module and uses dedicated DB/state files
- Detour look-and-feel aligned with main REPL (Rich logs + metrics)
- Step-4 nondeterministic ordering regression fixed in production step code
- Detour test harness upgraded into a reusable reference pattern:
  - in-process step-by-step equality
  - subprocess main-vs-detour parity snapshots
  - artifact hash parity across all pre-deviation steps
  - DB object schema/data hash parity
  - slow real-config parity test
  - proper slow-test gating
  - ANSI-safe output assertions
  - global state isolation
  - tempdir artifact containment

### 18. Important lessons captured for future detours

- Pre-deviation equivalence must be checked at multiple layers:
  - intermediate DB objects
  - artifact bytes/hashes
  - subprocess-level behavior
- Determinism bugs may hide in JSON/list ordering even when logic is “correct”
- Global mutable state in shared vars can make tests pass in one worktree and fail in another
- Rich output can break naive string assertions unless ANSI codes are stripped
- Reference tests should be cleanly structured because future detours will copy the pattern

## Revalidation snapshot (post-hardening rerun)

This section records a fresh rerun performed after the implementation and test-harness hardening described above, to ensure the RFC reflects the current behavior rather than historical intermediate states.

### Commands re-run

- `pixi run test tests/test_detour_step4_breakdown.py`
- `pixi run python -m src.detours.detour_step4_breakdown --config config.repl.json --non-interactive`

### Detour test module rerun result

Result from `tests/test_detour_step4_breakdown.py`:
- `4 passed, 1 skipped`

Breakdown:
- Passed:
  - `test_detour_contract_entrypoint_isolation_and_db_separation`
  - `test_detour_step4_identicality_against_main_per_step`
  - `test_detour_module_entrypoint_and_reproducibility`
  - `test_pre_deviation_artifact_hash_parity_against_main`
- Skipped (by design unless explicitly selected with `-m slow`):
  - `test_slow_real_config_pre_deviation_full_equivalence`

This confirms the non-slow detour reference harness remains green after all fixes (global-state isolation, ANSI-safe output assertions, tempdir containment, subprocess snapshot parity, and deterministic step-4 output ordering).

### Direct detour module rerun result (real config)

Command:
- `python -m src.detours.detour_step4_breakdown --config config.repl.json --non-interactive`

Observed behavior (matching intended detour design):
- Step logs printed in main-REPL-like style for steps 1–4
- Step messages emitted (including artifact dump locations)
- Breakdown printed after step 4
- Execution metrics printed
- Diagnostics path emitted

Observed step results:
- Step 1 (`01_register_resources`)
  - XLSX resources: `11`
  - DOCX resources: `9`
  - Parquet resources: `8`
- Step 2 (`02_load_xlsx`)
  - Population rows: `59665`
  - Columns: `26`
- Step 3 (`03_infer_names`)
  - Inferred mappings for `11` XLSX files
- Step 4 (`04_add_economy_priority`)
  - Computed economies for `217` country entries

Observed breakdown summary:
- Total rows: `59665`
- Rows by file:
  - `2014_HCR.xlsx`: `3215`
  - `2015_HCR.xlsx`: `3126`
  - `2016_HCR.xlsx`: `3266`
  - `2017_HCR.xlsx`: `3538`
  - `2018_HCR.xlsx`: `6079`
  - `2019_HCR.xlsx`: `6216`
  - `2020_HCR.xlsx`: `6389`
  - `2021_HCR.xlsx`: `6602`
  - `2022_HCR.xlsx`: `7221`
  - `2023_HCR.xlsx`: `7127`
  - `2024_HCR.xlsx`: `6886`
- Null/empty stats (selected columns):
  - `ktp.first_name`: `null=3`, `empty=3`
  - `ktp.last_name`: `null=1`, `empty=1`
  - `ktp.hcr_world_bank_economies`: `null=0`, `empty=0`
  - `ktp.priority`: `null=0`, `empty=0`
  - `ktp.priority_label`: `null=0`, `empty=0`
- Priority distribution:
  - `1`: `803`
  - `2`: `8795`
  - `3`: `5350`
  - `4`: `11182`
  - `5`: `33535`
- Priority group distribution:
  - `ENGLISH_HICS`: `33535`
  - `EU_COUNTRIES`: `11182`
  - `GREATER_CHINA`: `8795`
  - `LMICS_NO_GREATER_CHINA_OR_UNKNOWN`: `803`
  - `NON_ENGLISH_NON_EU_HICS_NO_GREATER_CHINA`: `5350`
- Income group distribution:
  - `High income countries`: `51986`
  - `Low income LMICs`: `1`
  - `Lower middle income LMICs`: `181`
  - `Upper middle income LMICs`: `7471`
  - `None`: `26`
- Integrity summary:
  - Unique name pairs: `19790`
  - Duplicate name rows: `39875`

Execution metrics observed:
- Peak RAM Usage: `0.51 GB`

Diagnostics output path from this rerun:
- `data/diagnostics/20260223_133014/repl_diagnostics.md`

### Current confidence statement

After this rerun, the implementation and tests appear consistent with the RFC’s stated goals:
- direct detour execution works on real config
- detour stops at the declared deviation point (after step 4)
- detour presents a main-REPL-like operator experience
- test harness remains green and continues to enforce pre-deviation equivalence and isolation properties (non-slow path by default, slow path available explicitly)

### Slow-test revalidation (explicit run)

Per follow-up validation request, the explicit slow test was also run:
- `pixi run test "-m slow tests/test_detour_step4_breakdown.py"`

Observed result:
- `1 passed, 4 deselected in 42.41s`

This confirms the real-config slow equivalence check currently passes when selected explicitly, and that the default test run continues to skip it unless `-m slow` is provided.
