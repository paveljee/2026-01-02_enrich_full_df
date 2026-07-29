# MAR missingness-mask SPEC workbook

## Scope

- Read the human-authored cells in `SPEC.ipynb`; do not alter them or implement code.
- Follow the prerequisite specification and inspect repository code/data contracts referenced by the task.
- Fill only the `## how ai understood the spec` section with an executor-ready design.

## Status

- Completed: followed the May prerequisite and the current FastAPI/missing-field context.
- Completed: reviewed card rendering, subset/DOCX completeness, innerdict materialization,
  economy/priority fields, SSN hit selection, `ssnau` metrics, and sampler-facing records.
- Completed: audited `data/scisci_process.duckdb` through `read_only=True` connections only.
- Completed: filled only the AI markdown cell with the model, validation, cache, sampler,
  evaluator, reproducibility, and acceptance contracts; no code was implemented.

## Current source findings

- 307 source keys split into 100 incomplete required-DOCX masks for train/test and
  207 all-one masks reserved for inference.
- Persisted context comprises 2,018 XLSX, 317 DOCX, and 2,044 SSN innerdicts; SSN
  rows represent 304 source keys.
- Required DOCX targets resolve dynamically to eight fields. The 100 incomplete keys
  contain 25 distinct masks; `ktp.table_1_researcher_author` is never missing.
- Field missing counts are education 71, age 53, academic position 41, gender 38,
  links 27, social capital 25, place of residence 20, and researcher/author 0.
- The model must estimate mask pattern conditional on at least one missing field; the
  specified split cannot estimate the population probability of any missingness.

## Guardrails

- Never run `src.repl`; database inspection uses `config.repl.json` and DuckDB `read_only=True` only.
- The 307 source keys are grouping units; do not split rows from one source key across folds.
- Truly complete keys are inference-only. Keys with observed missingness supply train/test labels.
- Preserve all human-written notebook cells and their commentary verbatim.

## Verification

- `jq` parses the edited notebook successfully.
- A structural comparison against `HEAD` confirms cells 0–6 are unchanged.
- No application/model tests were run because this task is specification-only.
