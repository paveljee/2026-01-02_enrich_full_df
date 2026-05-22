# WORK

## Current State

- SPEC approved; implementation is now authorized.
- `src.repl` must not be run directly for this task.
- Git staging/unstaging is not allowed; only read-only git commands.
- Partition/breakdown/review-view logic applies only to `card_subset_mode` 1 and 2.
- Modes other than 1 or 2 keep existing card-selection/building behavior and skip partition artifacts.

## Plan

1. Inspect step 10, runtime artifact dumping, schema/vars constants, and test patterns.
2. Add centralized schema/table/view names and vars labels/constants.
3. Refactor step 10 so subset filtering and partition materialization share one rule evaluation path.
4. Persist a one-row-per-namekey breakdown table for modes 1/2 only.
5. Build a review DataFrame/view with the exact SPEC column order and add it as a CSV artifact for modes 1/2 only.
6. Add focused tests for rule classification, ordering, mode gating, and review view shape.
7. Run targeted tests and record results.

## Doing Now

- Inspecting existing code and tests before implementation edits.

## Done

- Created this workbook.

## Notes

- Use `env -u CODEX_SANDBOX_NETWORK_DISABLED apply_patch` for patch edits in this session; plain `apply_patch` update/delete hits a local sandbox-helper loopback error.
