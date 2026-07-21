# Author-ID card detour spec workbook

## Constraints

- Specification only in this task; do not implement the detour yet.
- Preserve the human section of `SPEC.md`. Never run/import `src.repl`; git use
  remains read-only.
- Data inspection was limited to `data/scisci_process.duckdb` opened read-only
  under the linked prerequisites and the explicitly supplied TXT fixtures in
  `data/test_data/detour_authorid_card/`.
- Eventual runtime input is `--authorid` plus the nine configured SciSciNet
  parquets only. Never use the pipeline DB/state, HCR/XLSX, DOCX, World Bank,
  derived name keys, OpenAlex cache/network, or generated outputs.

## Status

- Completed: reviewed the changed human section, linked prerequisites, existing
  detours, step 9, step 10/card rendering, and the supplied card fixtures.
- Completed: revised the AI section after feedback so it no longer independently
  specifies step-9 SQL behavior.
- Completed: final consistency check of the shortened specification.

## Settled contract

- Step 9 is the source of truth. Implement by copying its module into the detour
  module and making the smallest adaptations; do not import the step and
  do not create a separately designed implementation.
- `--authorid` is already selected. Remove only the upstream author discovery and
  selection path; preserve the copied downstream SciSciNet and paper-level path.
- Runtime reads the nine SciSciNet parquets from config in an in-memory DuckDB.
  The pipeline DB, unrelated sources, OpenAlex-only data, network, and generated
  artifacts are outside the detour.
- Output is the one copied step-9 innerdict projected to the human-specified
  SciSciNet field boundary and rendered with the existing step-10/card logic.
  Never synthesize fields that belonged to the removed selection context.
- The module is standalone and stdout-only.

## Fixture notes for the executor

- `data/test_data/detour_authorid_card/` contains TXT card oracles, not standalone
  parquet/config fixtures.
- Keep all detour coverage in
  `tests/test_detours/test_detour_authorid_card.py`. Derive end-to-end expectations
  from the corresponding SciSciNet card subsections and current step-9 behavior;
  do not duplicate step 9 in test code.

## Verification

- `src.repl` was not run or imported.
- The only database inspection used
  `duckdb.connect("data/scisci_process.duckdb", read_only=True)`.
- No fixture or source data was modified.
- No application tests were run because only Markdown specifications changed.
