# WORK

## Current State

- SPEC approved; implementation is now authorized.
- Human SPEC text has been revised again; current task is to refresh the AI section so it reads as the current contract, not a change log.
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
7. Run targeted checks, `pixi run pre-commit`, and record results.

## Doing Now

- SPEC AI section refreshed for the latest human text; see Done/Notes for the implementation implication.

## Done

- Created this workbook.
- Confirmed step 10 currently nests subset rule logic inside `run()`.
- Confirmed artifact dumping already writes any DataFrame in `StepResult.artifacts` as CSV.
- Chosen implementation shape: extract rule evaluation helpers, persist the one-row-per-namekey partition table from a sorted DataFrame, and create the review view over the partition table plus existing xlsx/sciscinet/docx output views.
- Added centralized schema constants for `card_partitions` and `card_partition_review`.
- Added centralized vars labels for `ktp.partition`, all five partition flags, `ktp.ff_discard`, `ktp.ff_note`, partition value constants, and explicit `ssnad.*` review columns.
- Refactored step 10 rule evaluation into module-level helpers.
- Added mode gating: partition table/view artifacts are materialized only for modes 1 and 2.
- Added focused tests in `tests/test_step_10_build_cards.py`; initial targeted run passed (`5 passed`).
- Verified targeted lint: `pixi run python -m ruff check src/steps/step_10_build_cards.py tests/test_step_10_build_cards.py src/helpers/vars.py src/helpers/schema.py` passed.
- Verified targeted type check: `pixi run python -m mypy src/steps/step_10_build_cards.py tests/test_step_10_build_cards.py src/helpers/vars.py src/helpers/schema.py` passed.
- Verified focused tests: `pixi run pytest -q tests/test_step_10_build_cards.py` passed (`5 passed`).
- Verified nearby coverage: `pixi run pytest -q tests/test_cards.py tests/test_outer_dict.py tests/test_step_10_build_cards.py` passed (`10 passed, 1 skipped`).
- Ran full test suite: `pixi run pytest -q` reached `51 passed, 3 skipped, 6 failed`; failures are in detour tests outside step 10.
- Ran requested pre-commit: `pixi run pre-commit` passed Ruff and mypy across `src tests`, then failed in the pytest task with the same 6 detour failures.
- Re-read revised human SPEC before touching the AI section.
- Re-checked the approved DuckDB source in read-only mode: `card_partitions` has 231 rows with partition counts 31/100/100, and `card_partition_review` has 1,250 rows after `LOAD splink_udfs;`.
- Confirmed the currently persisted review view does not yet implement the revised singleton-enrichment behavior: partition 2 review rows have 0 non-null HCR/xlsx context fields in the current DB.
- Updated the AI section to emphasize the current operating constraints, DuckDB-only source of truth, `LOAD splink_udfs;` note for review-view audits, and the review-view singleton enrichment requirement from the revised human text.

## Notes

- Use `env -u CODEX_SANDBOX_NETWORK_DISABLED apply_patch` for patch edits in this session; plain `apply_patch` update/delete hits a local sandbox-helper loopback error.
- Full-suite/pre-commit detour failures observed:
  - `tests/test_detour_mode0_econ_stats.py` has 2 failures because the default pixi env lacks optional `plotly`/`kaleido`; the error message points to the `detour-mode0-econ-stats` pixi environment.
  - `tests/test_detour_step4_breakdown.py` has 4 failures because the fixture workbook does not expose the currently expected `FY26` World Bank income column.
- `src.repl` was not run.
- Revised human text introduces/clarifies a review-view logic requirement: non-primary context columns should be populated only when the other domain has a singleton match for the source key; ambiguous non-primary context should remain empty. The AI section now states this as current contract.
- Follow-up clarification: this singleton-fill rule is global, including xlsx/excel-row review rows. The partition focus domain is exploded by row; every non-focus domain is filled only when it has exactly one linked innerdict/value for the source key.
