# RFC: REPL Pipeline Refactor Plan (Steps + Helpers Architecture)

**Timestamp (UTC):** 2026-02-04 12:00Z  \
**Author:** GPT-5.2-Codex (OpenAI)

## Task summary
Create a standalone, implementation-ready RFC that codifies the **new REPL pipeline architecture** and **step order** based on human feedback. The design introduces a `helpers/` package, formal step transaction boundaries, and immutable step outputs to enable deterministic resume behavior.

## Goals
- Replace the strict “two-jump” rule with a clear, acyclic dependency graph: `repl` → `steps` → `helpers`.
- Define an authoritative **Init → RunSteps → CleanUp** lifecycle with transactional behavior and failure handling.
- Specify the **exact step order**, inputs/outputs, persistence rules, and resume guarantees.
- Prepare for implementation with a migration plan and clear interfaces.

## Non-goals
- Implementing the refactor in this RFC.
- Changing algorithmic matching logic beyond wiring and persistence rules.
- Changing output formats or card content.

## Background (current state highlights)
- `src/repl.py` currently owns **ResourceMonitor**, **PipelineManager**, CLI argument parsing, and the step-by-step orchestration; it imports and runs each stage directly. It also owns console rendering and diagnostics. (`src/repl.py`)
- Population loading is performed by `build_population_table`, which normalizes headers to `hcr.*`, stamps `hcr.row_number`/`hcr.filename`, and inserts rows into DuckDB. (`src/hcr_xlsx/loader.py`)
- `OuterDict` and `NameKey` live under `src/data_models`, supporting name-key serialization and append-only inner dict collection. (`src/data_models/outer_dict.py`)

## Proposed architecture

### Package boundaries
- **repl module:** orchestration, console rendering, step execution policy.
- **steps package:** one module per step; each step is a single entry point used by REPL.
- **helpers package:** shared utilities and moved classes (ResourceMonitor, PipelineManager, config loading, diagnostics helpers).

### Import rules
- `repl` may import from `steps` and `helpers`.
- `steps` may import from `helpers`.
- `helpers` must not import from `repl` or `steps`.

## Lifecycle overview

### Init (REPL → helpers.init)
`helpers.init` is responsible for:
- Parsing CLI args passed from REPL.
- **Loading config from JSON only** (deprecate defaults; JSON required).
- Initializing `ResourceMonitor`, `PipelineManager`, DuckDB connection, and diagnostics reporter.
- Constructing the **ordered step list** based on `--new` vs `--resume`.
- Performing pipeline reset **only** if `--new` and **only after confirmation** (`Y` in interactive mode or `--yes` non-interactive).
- Returning all initialized objects + step list to REPL.

### RunSteps (REPL-owned)
- REPL iterates the ordered step list and wraps each step with:
  - transaction start
  - exception handling
  - rollback on failure
  - step status tracking
- **REPL owns all console rendering** and file dumping for user-visible artifacts.

### CleanUp (REPL-owned)
- Always executed, even if a step failed.
- Closes resources, finalizes diagnostics, and prints concluding messages.

## Transaction and persistence model
- Each step **must** be transactionally isolated (no partial output on failure).
- Each step writes **new immutable tables/views**; later steps **never mutate** prior outputs.
- Resume behavior uses the latest successful step’s persisted outputs to reconstruct in-memory state (e.g., `OuterDict`).

## Step order (authoritative)
The following is the **only supported order** for new runs; `--resume` starts from the next incomplete step.

### Step 1 — Register resources
- Discover XLSX/DOCX/parquet inputs internally.
- Return `RegisteredResource` objects for all inputs.

### Step 2 — Load XLSX → population
- Load each XLSX into DuckDB `population` with `hcr.*` normalization.
- Record `hcr.row_number` and `hcr.filename`.
- Return artifacts for REPL to dump (e.g., `population` DF) + user-facing content.
- **Rule:** `population` is immutable from this point onward.

### Step 3 — Name column inference → `ktp.first_name` / `ktp.last_name`
- Create a new DuckDB table (1:1 to `population`) with inferred name columns.
- Persist a view for resume.
- Return DF joining `population` + inferred names + user content.

### Step 4 — Economy/priority enrichment
- Create a new DuckDB table (1:1 to `population`) with `ktp.economy` and `ktp.priority`.
- World Bank data is **loaded and dropped inside this step**; it never persists in DuckDB.
- Persist a view for resume.
- Return DF joining `population` + name table + economy/priority + user content.

### Step 5 — Sampling
- Create `samples` with only: `ktp.filename`, `ktp.fragment` (from `hcr.row_number`), `ktp.draw_number`.
- Return a view that inner joins `samples` with `population` and step-3/4 tables (prefer sample column names), dumped to DF by REPL.

### Step 6 — Build namekeys + outerdict stub
- Create immutable DuckDB table: `namekey` (JSON) + `innerdicts` (JSON lines, empty lists at this step).
- Build in-memory `outerdict` from the stub table.
- **OuterDict rule:** only append innerdicts; no mutation/removal of keys or prior innerdicts.
- Return `outerdict` to REPL (REPL triggers `outerdict.dump_json()`), plus user content.

### Step 7 — XLSX matching (populate innerdicts)
- Create a **view**: right join `population` to outerdict stub by namekey (JSON parse in-query).
- Matching: exact `lower(unaccent(last_name))`; first-name token containment (outerdict token in population tokens).
- Persist a **table**: `namekey` + `innerdicts` (JSON lines grouped per key).
- Extend `outerdict` from this table.
- Return a user-facing **view**: outer join `innerdicts` with `population`, `samples`, and step-3/4 tables.

### Step 8 — DOCX matching (populate innerdicts)
- Load all DOCX tables into DuckDB with `ktp.table_1_*` normalization, `ktp.filename`, `ktp.table_1_row_number` (start at 1).
- Require exactly **one** table per DOCX; otherwise raise an exception.
- Create a **view**: right join DOCX to outerdict stub on namekey with token containment (all outerdict tokens contained in docx tokens for “Researcher/author”).
- Persist a **table**: `namekey` + `innerdicts` (JSON lines grouped per key).
- Extend `outerdict` from this table.
- Return a user-facing **view**: outer join `innerdicts` with `population` and `samples`.

### Step 9 — Parquet matching (populate innerdicts)
- For each parquet: create a matched-row table containing **all original columns**, normalized with `ssnad.*`, `ssnap.*`, `ssnhpl0.*`, `ssnhpl1.*`, plus `ssn.filename`.
- Persist a **table** linking outerdict stub to author details (`ktp.first_name`, `ktp.last_name`, `ssnad.author_id`, `ssnad.display_name`, `ssnad.display_name_alternatives`, `ktp.ssnad_match`).
- Create per-parquet **views** combining author-link + matched parquet rows (`ktp.first_name`, `ktp.last_name`, `ktp.filename`, `ktp.fragment`, plus all parquet columns).
- Persist a **table**: `namekey` + `innerdicts` (JSON lines) populated from per-parquet views.
- Extend `outerdict` from this table.
- Return per-parquet user-facing **views** (outer-joined with `population` + `samples`) as DFs; REPL dumps one file per parquet.

### Step 10 — Build cards
- Generate cards from `outerdict` (same as current implementation).

## Diagnostics + user output ownership
- Steps **return** diagnostics payloads and artifacts, but **REPL owns rendering and dumping**.
- A step failure must be surfaced to the user with clear status, while ensuring the pipeline can safely resume.

## Resume rules
- Each step persists **immutable** tables/views; no step mutates prior outputs.
- `outerdict` persists in memory but is reconstructed from persisted tables on resume.
- Resuming picks up from the last successful step and **reuses** persisted artifacts.

## Implementation plan (incremental)
1. Create `helpers/` package and move `ResourceMonitor`, `PipelineManager`, and config loading there.
2. Add `helpers.init` to replace init logic in REPL and return a full context object.
3. Add a step runner in REPL with transaction boundaries, exception handling, and step state recording.
4. Move steps into `steps/` modules in order, starting with resource registration and XLSX load.
5. Introduce immutable table/view naming conventions for all step outputs.
6. Add `OuterDict.dump_json()` to make REPL dumping explicit and safe.

## Open questions for human review (remaining)
1. **JSON-only config:** Should REPL error if no config path is provided, or default to `config.repl.json` if present?
2. **Step state format:** Should `PipelineManager` continue storing a simple `steps_completed` list, or move to a structured record that includes step timestamps and artifact pointers?
3. **Artifact naming:** Do you want standardized filenames per step (e.g., `step_05_sampling.csv`), or timestamped outputs?
4. **Interactive gating:** Confirm whether steps 1–10 should all prompt in interactive mode, or only after data-heavy steps (sampling/matching).
