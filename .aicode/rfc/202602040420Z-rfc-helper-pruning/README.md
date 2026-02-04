# RFC: Helper Pruning + Step Self-Containment Refactor

**Timestamp (UTC):** 2026-02-04 04:20Z  \
**Author:** GPT-5.2-Codex (OpenAI)

## Task summary

The user requested a refactor that makes step modules more self-contained and prunes helpers aggressively. Only truly shared, technical helpers should remain. SQL queries should not be abstracted into helpers. Additionally, `src/repl.py` should be slimmer and focus on the main pipeline runner (historically called `run_reproduction`), with other orchestration details moved out.

## Goals
- Remove helper modules that mainly hide step-specific logic or SQL.
- Inline step-specific logic into its owning step module.
- Keep only minimal, technical helpers that are broadly shared.
- Reduce `src/repl.py` to the main pipeline runner plus CLI glue.

## Non-goals
- Changing pipeline behavior or algorithmic semantics.
- Modifying data formats or outputs beyond structural refactor.

## Plan (high level)
1. Inventory helpers and classify them as:
   - **Keep:** broadly shared, technical (e.g., constants, schema, duckdb registration, config, resource registry, diagnostics, monitor).
   - **Inline:** step-specific logic, especially SQL.
2. Inline targeted helpers into their owning step modules.
3. Move REPL orchestration helpers out of `src/repl.py` so the file is mostly the pipeline runner.
4. Update tests to import from the new locations.
5. Run `pixi run pre-commit`.

## Candidate changes (anticipated)
- Inline HCR XLSX load + economy/priority logic into `step_02_load_xlsx.py` / `step_04_add_economy_priority.py`.
- Inline XLSX/DOCX/Parquet innerdict append logic directly into steps (no SQL in helpers).
- Inline XLSX name inference helper into `step_03_infer_names.py`.
- Move DOCX load/normalize into `step_08_match_docx.py` (keep low-level DOCX XML parsing as technical helper).
- Remove thin wrapper helpers (`models.py`, `cards_helpers.py`, `outerdict_io.py`, etc.).
- Keep shared technical helpers: constants, schema, duckdb frame registration, resource registry, config, diagnostics, monitor, parquet column utils, JSON lines.

## Report

### Summary of changes
- Removed helper modules that were primarily step-specific wrappers:
  - Dropped `helpers/hcr.py`, `helpers/name_inference.py`, `helpers/docx_loader.py`,
    `helpers/outerdict_io.py`, `helpers/models.py`, and `helpers/cards_helpers.py`.
- Inlined step-owned logic directly into step modules:
  - `step_02_load_xlsx.py` now owns XLSX loading + population table creation.
  - `step_03_infer_names.py` now owns XLSX header inference logic.
  - `step_04_add_economy_priority.py` now owns World Bank parsing + economy/priority logic.
  - `step_07_match_xlsx.py`, `step_08_match_docx.py`, and `step_09_match_parquet.py`
    now append innerdicts directly without helper indirection.
- Moved DOCX normalization/loading into `step_08_match_docx.py`, leaving only low-level
  DOCX XML parsing in `helpers/docx_parse.py`.
- Simplified REPL to focus on the main runner:
  - Renamed the main entry to `run_reproduction`.
  - Moved CLI-specific utilities (`confirm_reset`, `run_step`, artifact dumping) into
    `helpers/repl_runtime.py`.
- Updated tests to import from the new locations, especially DOCX loader functions now
  living in `step_08_match_docx.py`.

### Test run
- Command: `pixi run pre-commit`
- Ruff: passed
- MyPy: passed
- Pytest: passed (37 passed, 1 skipped)
- Skipped: `tests/test_csv_sample_validation.py::test_csv_rows_match_samples` (sample data not present at the expected path)
