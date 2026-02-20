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
