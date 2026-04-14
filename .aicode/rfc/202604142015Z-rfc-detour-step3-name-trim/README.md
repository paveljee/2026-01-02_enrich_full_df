# RFC: Detour for Step-3 Name Whitespace Trimming with Full Main-Flow Baseline

**Timestamp (UTC):** 2026-04-14 20:15Z  \
**Author:** GPT-5 Codex (OpenAI)

## Task summary
Define a new detour that will be implemented in two explicit phases:
- first, create a detour that replicates the main REPL workflow exactly and proves there are no regressions relative to the main flow,
- then introduce the smallest possible detour-local change in step 3 so both first and last names are trimmed on both ends before being written into `ktp.first_name` and `ktp.last_name`.

This RFC is intentionally pre-implementation and serves as a review checkpoint before any detour code is written.

## Goals
- Capture the exact detour scope requested by the user.
- Follow the existing detour philosophy already documented in this repo.
- Keep the new detour self-contained, directly runnable, and isolated from both `src/repl.py` and other detours.
- Establish a two-phase implementation plan that first proves exact main-flow equivalence.
- Limit the eventual behavioral change to a single semantic deviation point: step 3 name trimming before populating `ktp.first_name` / `ktp.last_name`.
- Define the testing strategy needed to prove both baseline equivalence and the later minimal step-3 divergence safely.

## Non-goals
- Implementing the new detour in this RFC.
- Modifying the main REPL workflow or any main step module as part of this RFC.
- Expanding the detour into a general-purpose name-normalization framework.
- Introducing broader normalization changes such as case folding changes, internal whitespace collapsing, punctuation cleanup, or fuzzy matching changes.

---

## Repo detour constraints that this RFC follows

From the existing detour RFCs and codebase, the new detour should follow these rules:
- It must be a standalone detour under `src/detours`.
- It must run directly via `python -m src.detours.<module>`.
- It must not require new CLI wiring in `src/repl.py` or `src/cli.py`.
- It must not import another detour module.
- It must use dedicated detour DB/state paths and never touch the main pipeline DB/state.
- It must match main-step behavior exactly until the detour's declared deviation point.
- Any deviation must be intentional, explicit, minimal, and directly tied to detour goals.
- The test strategy should follow the existing per-detour pattern: one dedicated test module, with contract, isolation, reproducibility, and main-vs-detour comparison checks.

These constraints come directly from:
- `.aicode/rfc/202602200311Z-rfc-detours-wiring/README.md`
- the current reference detour implementation in `src/detours/detour_step4_breakdown.py`
- the current reference detour tests in `tests/test_detour_step4_breakdown.py`

---

## Main REPL workflow that the detour must mirror

Under `pixi run repl`, the pipeline currently runs the full `STEP_ORDER`:
1. `01_register_resources`
2. `02_load_xlsx`
3. `03_infer_names`
4. `04_add_economy_priority`
5. `05_sample_population`
6. `06_build_outerdict`
7. `07_match_xlsx`
8. `08_match_docx`
9. `09_match_parquet`
10. `10_build_cards`

The relevant name flow for this RFC is:
- step 2 loads raw HCR XLSX cells into `population`
- step 3 derives semantic KTP names into `population_names`
- step 5 exposes those names in `samples_with_names` / `samples_with_context`
- step 6 freezes sampled names into `OuterDict` name keys
- steps 7-9 consume those keys for XLSX, DOCX, and SciSciNet matching
- step 10 uses the resulting innerdicts for subset selection and card output

That makes step 3 the earliest semantic choke point where KTP names are defined for the rest of the workflow.

---

## Why step 3 is the right deviation point

The current pipeline behavior copies inferred name-column values into `ktp.first_name` and `ktp.last_name` without trimming. After that:
- step 5 propagates those values into sampled-name views,
- step 6 serializes them into `name_key`,
- step 8 joins `OUTERDICT_NAME_VIEW` back to `SAMPLES_WITH_NAMES_VIEW` on names,
- step 9 performs exact full-name SciSciNet matching against those names.

So if leading or trailing whitespace survives into step 3, it becomes a workflow-wide semantic value rather than just a raw-source artifact.

This is why the eventual change should happen in step 3 rather than later:
- trimming only in step 6 is too late and risks drift between `OUTERDICT_NAME_VIEW` and `SAMPLES_WITH_NAMES_VIEW`
- trimming only in step 9 would patch only the SciSciNet symptom, not the semantic KTP name fields
- changing `NameKey` globally would be broader and riskier than needed, especially because resume/loading paths rely on exact serialized `name_key` strings

The user-requested change is narrow and should stay narrow:
- trim leading and trailing whitespace on both first and last names
- do it before those values become `ktp.first_name` / `ktp.last_name`
- do not otherwise reinterpret the names

---

## Proposed detour (v1)

### Module
- `src/detours/detour_step3_name_trim.py`

### Test module
- `tests/test_detour_step3_name_trim.py`

### Entrypoint
- `python -m src.detours.detour_step3_name_trim --config config.repl.json`

### Runtime model

This detour should be a normal step-running detour:
- it should detourize `db_file` and `state_file`
- it should initialize runtime/config the same way the reference step-running detour does
- it should run pipeline steps in order
- it should print main-REPL-like progress output
- it should return a structured `DetourResult`

Unlike the read-only stats detour, this one should create and use its own detour DB because it is running steps.

### Package shape

Because the current repo uses single-file detours and this detour has only one intended deviation point, the default shape should remain simple:
- one detour module file
- no detour registry
- no cross-detour imports
- no new shared helper unless technical reuse is immediate and clearly justified

For the eventual phase-2 deviation, the preferred approach is:
- keep orchestration inside the detour module
- keep main-step reuse for all unchanged steps
- introduce a detour-local copy or detour-local reimplementation of step 3 only

That preserves the local review surface while keeping the detour self-contained.

---

## Two-phase implementation plan

### Phase 1: exact main-workflow baseline detour

Intent:
- build the detour shell first
- run the same workflow as main REPL
- prove the detour framework itself introduces no regressions

Expected behavior in phase 1:
- run the full workflow through step 10
- use the same main step functions as the main workflow for every step
- produce equivalent database objects and step artifacts relative to main flow for the same config/seed
- keep the detour fully isolated via dedicated DB/state paths

Important property:
- in phase 1 there is no declared deviation point yet
- therefore the detour must be fully identical to main flow from start to finish

Why phase 1 matters:
- it gives a trustworthy baseline before touching behavior
- it separates detour orchestration risk from step-3 behavior-change risk
- it makes later regressions easier to attribute

### Phase 2: minimal detour-local step-3 change

After phase 1 is proven green, phase 2 introduces the only behavior change:
- in step 3, trim both first and last names on both ends before writing them into `ktp.first_name` and `ktp.last_name`

More explicitly, the eventual detour-local step 3 should:
- preserve the existing inferred source-column selection logic
- preserve `NULL` handling
- apply leading/trailing whitespace trimming to the chosen first-name value
- apply leading/trailing whitespace trimming to the chosen last-name value
- then write those trimmed results into `population_names`

The eventual detour-local step 3 should not:
- modify raw `population` / `hcr.*` source columns
- collapse internal whitespace
- strip punctuation
- lowercase names
- add fuzzy matching
- modify later step logic

Declared deviation point after phase 2:
- `03_infer_names`

Expected unchanged behavior after phase 2:
- steps 1-2 remain exact main-flow reuse
- steps 4-10 remain exact main-step reuse
- detour isolation model remains unchanged

Expected downstream effect after phase 2:
- sampled semantic KTP names no longer preserve leading/trailing whitespace artifacts from source cells
- `name_key` construction uses trimmed semantic names
- step-7 XLSX and step-8 DOCX matching continue to work from those trimmed semantic names
- step-9 SciSciNet exact-name matching is no longer defeated by leading/trailing whitespace in sampled KTP names

---

## Detailed trimming scope for phase 2

The intended trimming behavior should be deliberately minimal:
- apply trimming only to the values destined for `ktp.first_name` and `ktp.last_name`
- trim both left and right edges
- leave internal spaces intact
- do not change raw source columns

Examples of intended behavior:
- `" Gaoquan"` -> `"Gaoquan"`
- `"Gaoquan "` -> `"Gaoquan"`
- `" Shi "` -> `"Shi"`
- `"Mary Ann"` stays `"Mary Ann"`
- `"van der Waals"` stays `"van der Waals"`

Expected interaction with existing downstream logic:
- if a value becomes `''` after trimming, existing step-6 empty-name exclusion logic can continue to handle it
- step-10 XLSX exactness logic already strips token values when evaluating payload equality, so this change should align semantics earlier rather than inventing a new rule

---

## Testing strategy

The testing plan should follow the existing detour philosophy and be explicitly split by implementation phase.

### Test module
- `tests/test_detour_step3_name_trim.py`

### Phase-1 tests: prove detour shell has zero behavioral drift

These tests should mirror the reference detour pattern as closely as possible.

Required checks:
- contract checks:
  - module exposes `DETOUR_ID`, `DETOUR_NAME`, `DETOUR_DESCRIPTION`, `run_detour(...)`
  - `run_detour(...)` returns the expected result shape
- entrypoint check:
  - `python -m src.detours.detour_step3_name_trim` executes successfully
- import isolation:
  - no `src.cli` import
  - no cross-detour import
- DB/state isolation:
  - detour DB path and state path differ from main config DB/state paths
- full identicality against main flow:
  - run main and detour in separate DBs with same config/seed
  - compare DB objects and artifact hashes across the full workflow, not just early steps
  - assert deterministic reproducibility across repeated detour runs

The intent of phase-1 tests is simple:
- if they fail, the detour shell is not yet trustworthy enough to carry a behavior change

### Phase-2 tests: keep pre-deviation identity and verify only the intended step-3 change

Once phase 2 begins, the declared deviation point moves to step 3.

Required checks:
- keep contract, entrypoint, import-isolation, and DB-isolation tests
- pre-deviation identicality:
  - steps 1-2 must remain strictly identical to main flow
- targeted step-3 assertions on synthetic fixtures:
  - leading whitespace is removed from first and last names
  - trailing whitespace is removed from first and last names
  - already-clean names remain unchanged
  - raw `population` source columns remain unchanged
  - trimmed semantic names land in `population_names`
- downstream regression checks on synthetic fixtures:
  - `samples_with_names` reflects the trimmed semantic names
  - `outerdict_stub` / `OUTERDICT_NAME_VIEW` contain trimmed keys
  - a representative whitespace-sensitive SciSciNet exact-name case now matches where main flow would miss
- reproducibility remains stable for the detour

### Test-harness note from existing detour work

The reference detour tests already surfaced one repo-specific hazard:
- `HCR_XLSX_NAME_COLS` is global mutable state and should be isolated/reset in tests

This new detour test module should inherit that lesson directly and include the same kind of test isolation fixture.

---

## Implementation plan

1. Create a new RFC-approved detour module:
   - `src/detours/detour_step3_name_trim.py`
2. Add a dedicated test module:
   - `tests/test_detour_step3_name_trim.py`
3. Implement phase 1 first:
   - dedicated detour DB/state paths
   - self-contained direct module entrypoint
   - full main-workflow execution using existing main step functions only
4. Add phase-1 identicality and isolation tests, including full-workflow comparison to main flow.
5. Only after phase 1 is green, introduce phase-2 detour-local step-3 logic.
6. Keep the phase-2 code change minimal and tightly diffable against `src/steps/step_03_infer_names.py`.
7. Add phase-2 targeted trimming tests and downstream regression checks.
8. Keep all changes confined to the new detour module and its tests unless a narrowly technical shared helper is clearly justified.

---

## Acceptance criteria

- The RFC is approved before implementation begins.
- The new detour follows the existing self-contained detour philosophy.
- The new detour is isolated from `src/repl.py`, `src/cli.py`, and all other detours.
- The new detour uses dedicated DB/state paths.
- Phase 1 proves exact equivalence to the main workflow across the full pipeline for the same config/seed.
- Phase 2 introduces exactly one declared semantic deviation point: step 3 name trimming before `ktp.first_name` / `ktp.last_name` are stored.
- Phase 2 does not modify raw HCR source columns.
- Phase 2 does not introduce broader normalization behavior beyond leading/trailing trimming of first and last names.
- Tests cover contract, entrypoint, isolation, reproducibility, phase-1 exact equivalence, and phase-2 minimal-diff behavior.

---

## Risks and mitigations

- Risk: the detour framework itself drifts from main flow before any intended behavior change.
- Mitigation: require a full exact-equivalence phase before allowing the step-3 deviation.

- Risk: trimming gets introduced too late in the workflow and causes name-view drift.
- Mitigation: declare step 3 as the only intended deviation point.

- Risk: the eventual change broadens from trimming into a larger normalization rewrite.
- Mitigation: explicitly constrain phase 2 to leading/trailing trimming only, on both first and last names, before populating KTP semantic name fields.

- Risk: changing global models or helpers creates resume / persisted-key side effects.
- Mitigation: keep the change detour-local and centered on step 3 rather than `NameKey` or global serialization behavior.

- Risk: detour tests become flaky because of repo-global mutable state.
- Mitigation: copy the isolation pattern already learned in the reference detour tests, especially around `HCR_XLSX_NAME_COLS`.

---

## Final recommendation

This should be treated as a careful, two-stage detour project rather than a quick one-off patch.

The right order is:
1. build a trustworthy full-workflow detour that is provably identical to main flow,
2. then add the single detour-local step-3 trim and verify only that narrow semantic change.

That sequence matches both the technical shape of this pipeline and the detour philosophy already established in this repo.
