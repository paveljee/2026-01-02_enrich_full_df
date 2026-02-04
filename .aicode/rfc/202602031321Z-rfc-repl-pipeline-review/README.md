# RFC: REPL Pipeline Review & Step-by-Step Action Map

**Timestamp (UTC):** 2026-02-03 13:21Z  \
**Author:** GPT-5.2-Codex (OpenAI)

## Task summary
Review `src/repl.py` and all imported modules to build a detailed, end-to-end mental model of the REPL pipeline. Document that understanding here, then enumerate **every pipeline action** in explicit step notation. Each step includes **input**, **transformations** (maximum detail), and **output**.

## Goals
- Provide a thorough, grounded understanding of how the REPL orchestrates the pipeline.
- Trace the behavior of every imported object used by `src/repl.py`.
- Enumerate the pipeline actions as a clear, ordered list of steps with explicit I/O and transformations.

## Non-goals
- Changing pipeline logic.
- Running or benchmarking the pipeline.

---

## Detailed REPL review (imports and behaviors)

### `src/repl.py` (orchestration)
- **Primary role:** Coordinates the KTP pipeline: input discovery, resource registration, database resets, population loading, preprocessing, sampling, indexing, matching (XLSX/DOCX/SciSciNet), card rendering, output packaging, and diagnostics reporting.
- **Key collaborators:**
  - `PipelineConfig` (config paths, sampling controls, output format).
  - `PipelineManager` (state file + DuckDB connection with memory limit).
  - `ResourceMonitor` (RSS peak tracking).
  - `DiagnosticsReport` (writes Markdown report with stage summaries).
  - `build_population_table`, `sample_population`, `sample_pilot`, `index_samples`, `match_population`, `load_docx_tables`, `match_docx`, `match_parquet`, `build_cards`, `write_cards_zip`.

### `src/_vars.py` (constants)
- **Provides constants** for all column names (KTP/HCR/DOCX/CSV) plus sampling and priority metadata.
- `HCR_XLSX_NAME_COLS` is a **mutable global mapping** from XLSX filename → (first_col, last_col). It is populated at runtime if empty.

### `src/config.py` (config defaults)
- `PipelineConfig` defines paths to data sources and output settings.
- `FILES_CONFIG` supplies the SciSciNet parquet paths and hashes.
- `from_json` allows a JSON config override and coerces string paths into `Path` objects.

### `src/data_models/*` (data primitives)
- **`NameKey`**: Pydantic model with first/last names serialized to a JSON key string.
- **`InnerDict`**: Wraps a record and validates that the matching procedure defines `dataset_id_field`.
- **`OuterDict`**: Mapping of `NameKey` (via JSON key) to lists of `InnerDict` records; provides add/ensure helpers.
- **`RegisteredResource`**: Holds resource metadata (name/hash/group/type/url). Verifies hashes on init; computes hash for local or remote URLs.
- **`SourceKey`**: Combines a `RegisteredResource` with a fragment (row id, author id, etc.) to uniquely identify a record. The fragment is tagged with a `FragmentType` via the resource.

### `src/utils/resources.py` (resource registration)
- `register_resource` computes/uses hashes, then builds `RegisteredResource` with a file URL.
- `register_resources` maps a list of paths into a `{name: RegisteredResource}` dictionary.

### `src/utils/files.py` (file discovery)
- `find_files_by_extension` globs (or rglobs) for a specific extension.

### `src/utils/duckdb.py` (DuckDB frame registration)
- `register_frame` registers a pandas DataFrame into DuckDB as a table and then unregisters the temporary view.

### `src/utils/name_keys.py` (name key utilities)
- `build_outer_dict_from_names` builds an `OuterDict` from unique name pairs.
- `build_name_key_frame` produces a DataFrame with JSON key + first/last names for joins.

### `src/utils/records.py` (outer dict appends)
- `append_records` converts raw records into `InnerDict` objects and appends them into `OuterDict` using a `SourceKey` built from a registered resource and fragment id.

### `src/hcr_xlsx/loader.py` (population load)
- Reads each XLSX file (skipping temp `~$`) and normalizes headers via `normalize_hcr_header`.
- Adds row index (1-based with a +2 offset), filename, and population index.
- Coerces all non-index columns to strings.
- Dynamically **aligns schema** with an existing DuckDB table (adds new columns, fills missing, reorders).
- Inserts into (or creates) the `population` table in DuckDB.

### `src/hcr_xlsx/preprocessor.py` (sampling metadata)
- Loads World Bank high-income economies.
- Derives per-row **economies**, **priority**, and **priority group** from affiliation text.
- Converts filename to string and adds the computed columns.

### `src/hcr_xlsx/sampler.py` (sampling)
- `sample_population` draws rows with replacement using a seeded RNG and writes to `samples` with draw labels and preprocessed metadata.
- `sample_pilot` selects a fixed pilot list by name/category for a given filename and appends to `samples` with `pilot.N` draw labels.
- `_append_samples_table` aligns schema with existing `samples` table as needed.

### `src/hcr_xlsx/indexer.py` (name indexing)
- Uses `HCR_XLSX_NAME_COLS` mapping to **derive first/last names for each sampled row**, writes them into `samples`, and generates JSON name keys.
- Builds an `OuterDict` from unique names.

### `src/hcr_xlsx/matcher.py` (population matching)
- Builds a `name_keys` table from `OuterDict`.
- Constructs case expressions to select the correct name column based on `hcr.filename`.
- Matches population rows when last name equals and first-name token exists in the population first-name field.
- Appends matched rows to `OuterDict` with an XLSX fragment id.

### `src/manual_docx/loader.py` + `src/parse_docx.py` (DOCX parsing)
- `parse_docx_table` extracts all tables from a DOCX by reading `word/document.xml` in the docx zip.
- Runs are converted into text with formatting markers (or plain text for header row), then tables are returned as DataFrames.
- `load_docx_tables` normalizes column names, stamps filename/table/row indices, and creates a per-row fragment id.

### `src/manual_docx/matcher.py` (DOCX matching)
- Joins `OuterDict` name keys to DOCX rows by lowercased, alphanumeric-only first/last name containment in a “Researcher/author” column.
- Appends matched DOCX rows to `OuterDict` using DOCX fragment ids.

### `src/sciscinet_parquet/matcher.py` (SciSciNet matching)
- Normalizes sample rows into a `match_key_norm` (lowercased “first last”).
- Reads SciSciNet parquet data in DuckDB (author details, authors->papers, hit papers levels).
- Builds bridge and aggregation tables to associate name keys with author ids and hit metrics.
- Appends matched author rows to `OuterDict` with author-id fragments.

### `src/cards.py` (card rendering + packaging)
- `build_cards` renders per-name markdown with introduction, draw information, provenance info, and field values.
- `write_cards_zip` writes either `.txt` cards or converts Markdown to DOCX via Pandoc, then zips all cards.

---

## Pipeline action list (step-by-step I/O + transformations)

> Each step is written as: **Step N — Input → Transformations → Output**.

### Step 1 — Initialize configuration + telemetry
- **Input:** Optional JSON config path; default config values.
- **Transformations:**
  - Parse CLI args, load `PipelineConfig` (default or from JSON).
  - Start `ResourceMonitor` for RSS tracking.
  - Create `PipelineManager`, open DuckDB connection, set `memory_limit='20GB'`.
  - Initialize diagnostics report file and rich live layout (if interactive).
- **Output:** Initialized config, diagnostics writer, live console, DuckDB connection, resource monitor running.

### Step 2 — Discover XLSX inputs
- **Input:** `config.xlsx_dir` path.
- **Transformations:**
  - Glob for `.xlsx` files (non-recursive).
  - Filter out temp files starting with `~$` for reporting.
  - Emit summary to diagnostics (count + example names).
- **Output:** `xlsx_files` list; diagnostics section with counts/examples.

### Step 3 — Infer XLSX name columns (if needed)
- **Input:** `xlsx_files` + `HCR_XLSX_NAME_COLS`.
- **Transformations:**
  - If mapping is empty, load each XLSX and normalize headers.
  - Heuristically match candidate “first/last” headers.
  - Populate `HCR_XLSX_NAME_COLS` with inferred mapping; report examples.
- **Output:** Populated `HCR_XLSX_NAME_COLS` mapping; diagnostics section.

### Step 4 — Register resources
- **Input:** XLSX file list + config paths for parquet/world bank/DOCX.
- **Transformations:**
  - Create `RegisteredResource` entries for SciSciNet parquet files (with hash checks).
  - Register XLSX input files for population sampling.
  - Register World Bank XLSX and DOCX resources.
- **Output:** `PipelineResources` object with parquet/xlsx/docx/world_bank resources; diagnostics section.

### Step 5 — Reset pipeline tables/views
- **Input:** DuckDB connection.
- **Transformations:**
  - Drop tables: `population`, `samples`, `name_keys`, `docx_rows`, `docx_name_keys`, `matched_authors_bridge`, `author_papers`, `final_agg`.
  - Drop view: `all_hits`.
- **Output:** Clean database state; diagnostics section.

### Step 6 — Load population table (XLSX → DuckDB)
- **Input:** Registered XLSX resources + DuckDB connection.
- **Transformations:**
  - Read each XLSX into pandas, normalize headers (`hcr.*`), add `hcr.row_number`, `hcr.filename`, `ktp.population_index`.
  - Coerce non-index columns to `string` dtype.
  - Align schema with existing `population` table (add columns, fill missing, reorder).
  - Insert into `population` table.
- **Output:** DuckDB `population` table; diagnostics section with rows/columns.

### Step 7 — Load World Bank economies
- **Input:** Registered World Bank XLSX resource.
- **Transformations:**
  - Read `Country Analytical History` sheet.
  - Filter rows where column 38 == “H” (high income).
  - Extract column 1 values as economy names.
- **Output:** `economies` list; diagnostics section with count/examples.

### Step 8 — Sample population draws
- **Input:** DuckDB `population` table, `economies`, seed, draw sizes.
- **Transformations:**
  - Validate sum(draw_sizes) == 300.
  - For each draw size:
    - Sample population indices with replacement using seeded RNG.
    - Join indices to `population` rows.
    - Assign sequential draw numbers.
    - Copy `hcr.filename` → `ktp.filename`.
    - Preprocess sample rows: compute economies, priority, priority group.
    - Append into `samples` table with schema alignment.
- **Output:** DuckDB `samples` table with 300 rows + metadata; diagnostics section.

### Step 9 — Sample pilot rows
- **Input:** DuckDB `population`, pilot filename, pilot name/category triples, economies list.
- **Transformations:**
  - Join population rows against pilot triples for exact match on first/last/category.
  - Preserve pilot ordering with an explicit sort key.
  - Assign `pilot.N` draw labels.
  - Preprocess rows and append to `samples`.
- **Output:** Pilot rows appended to `samples`; diagnostics in sampling section.

### Step 10 — Index samples (build name keys)
- **Input:** `samples` table + `HCR_XLSX_NAME_COLS` mapping.
- **Transformations:**
  - For each row, choose the correct first/last name columns based on `hcr.filename`.
  - Write derived `ktp.first_name`/`ktp.last_name` to samples.
  - Generate JSON `name_key` per row and persist back into `samples` table.

---

## Implementation log (2026-02-04)
- Removed unused modules and tests that were no longer referenced by `src/repl.py` and the step-based pipeline. This trimmed legacy `hcr_xlsx/*` matcher/indexer/sampler, `manual_docx/*` matcher/indexer/sampler, and `sciscinet_parquet/*` modules plus their unused tests so the repo matches the current step-driven architecture.
- Reimplemented CSV sample validation as an end-to-end pipeline test using the current steps (`step_03_infer_names`, `step_04_add_economy_priority`, `step_05_sampling`) and the real XLSX + ground-truth CSVs. The test compares `(hcr.filename, hcr.row_number, ktp.draw_number)` via `Counter` to ensure exact agreement.
- Fixed sampling order determinism by preserving per-draw sample ordering. Each draw now stores `sample_id` with sampled indices and orders the join by `sample_id` before assigning draw labels. This restores exact draw-number alignment with the ground-truth CSVs.
- Test run summary:
- Command: `pixi run pre-commit`
- Ruff: passed
- MyPy: passed
- Pytest: passed (38 tests, including `tests/test_csv_sample_validation.py::test_csv_rows_match_samples`)
- Consolidated all non-REPL modules into `src/helpers` and removed the legacy root/layout:
- Moved `config.py`, `_vars.py`, `cards.py`, `parse_docx.py`, and `data_models/` into `src/helpers/`.
- Folded `hcr_xlsx` loader/preprocessor into `src/helpers/hcr.py` and folded DOCX parsing/loading into `src/helpers/docx_loader.py` + `src/helpers/docx_parse.py`.
- Removed `src/utils`, `src/manual_docx`, `src/hcr_xlsx`, and empty `src/sciscinet_parquet` directories; updated all imports/tests accordingly.
- Added `src/helpers/files.py` and inlined register-resource helpers into `src/helpers/resources.py`.
- Test run summary (post-refactor):
- Command: `pixi run pre-commit`
- Ruff: passed
- MyPy: passed
- Pytest: passed (38 tests)
  - Build `OuterDict` from unique name pairs.
- **Output:** Updated `samples` table (with name keys); initialized `OuterDict`.

### Step 11 — Match population rows (XLSX)
- **Input:** `OuterDict`, `population` table, XLSX resources.
- **Transformations:**
  - Build `name_keys` table from `OuterDict`.
  - Use filename-based CASE expressions to map the correct columns to name fields.
  - Match rows where last name matches and first-name token is contained in population first name field.
  - Attach `ktp.source_key` with XLSX fragment id and append to `OuterDict`.
- **Output:** `OuterDict` enriched with XLSX population matches; diagnostics section.

### Step 12 — Load DOCX tables
- **Input:** Registered DOCX resources.
- **Transformations:**
  - Parse each DOCX table from `word/document.xml`.
  - Normalize column names and add filename/table/row indices.
  - Build `ktp.docx_fragment` identifiers (`table{idx}_row{idx}`).
  - Concatenate into a single DataFrame.
- **Output:** `docx_df` DataFrame of DOCX rows; diagnostics section.

### Step 13 — Match DOCX rows
- **Input:** `OuterDict`, `docx_df`, DOCX resources.
- **Transformations:**
  - Normalize/resolve the “Researcher/author” column name.
  - Clean first/last names to lowercase alphanumeric sequences.
  - Clean DOCX name field similarly.
  - Match when both first and last tokens appear in the DOCX row text.
  - Append matched rows to `OuterDict` using DOCX fragments.
- **Output:** `OuterDict` enriched with DOCX matches; diagnostics section.

### Step 14 — Match SciSciNet parquet data
- **Input:** `OuterDict`, `samples` DataFrame, SciSciNet parquet resources + paths.
- **Transformations:**
  - Create `match_key_norm` as lowercase “first last”.
  - Read author details, explode alternative names, and join on exact normalized name.
  - Join author ids to paper ids; combine hit paper datasets into a single view.
  - Aggregate hit metrics and field ids per author + name key.
  - Append matched author records into `OuterDict` with author-id fragments.
- **Output:** `OuterDict` enriched with SciSciNet matches; diagnostics section.

### Step 15 — Render cards
- **Input:** `OuterDict`, draw counts, excluded columns, intro date.
- **Transformations:**
  - For each name key, build a markdown card with introduction, draw labels, and per-source field listings.
  - Include provenance note for original first/last column names when available.
  - Sanitize a filename token from the name/draw label.
- **Output:** Dictionary of `{docx_filename: card_text}`; diagnostics section.

### Step 16 — Package cards into output zip
- **Input:** Cards dictionary + output format + reference docx.
- **Transformations:**
  - If `txt`, write text files and zip.
  - If `docx`, run Pandoc conversion from markdown to docx using reference doc.
  - Create a zip archive containing all generated files.
- **Output:** Output zip path for card artifacts; diagnostics section.

### Step 17 — Report metrics + finalize
- **Input:** Peak RAM stats, cards count, diagnostics path.
- **Transformations:**
  - Stop live UI, finalize resource monitor and connection.
  - Render a small metrics table to console.
  - Print output and diagnostics locations.
- **Output:** Terminal summary and returned output zip path.

---

## Files inspected
- `src/repl.py`
- `src/_vars.py`
- `src/config.py`
- `src/data_models/__init__.py`
- `src/data_models/outer_dict.py`
- `src/data_models/source_key.py`
- `src/hcr_xlsx/loader.py`
- `src/hcr_xlsx/preprocessor.py`
- `src/hcr_xlsx/sampler.py`
- `src/hcr_xlsx/indexer.py`
- `src/hcr_xlsx/matcher.py`
- `src/manual_docx/loader.py`
- `src/manual_docx/matcher.py`
- `src/parse_docx.py`
- `src/sciscinet_parquet/matcher.py`
- `src/utils/files.py`
- `src/utils/resources.py`
- `src/utils/duckdb.py`
- `src/utils/name_keys.py`
- `src/utils/records.py`

## Validation results (code vs RFC)
This section re-validates every statement in this RFC against the current codebase and records the outcome. The review re-walked the pipeline in execution order and cross-checked each described transformation, input, and output against the implementations listed in **Files inspected**.

### Verified statements (no discrepancies)
- **Pipeline orchestration and sequencing:** The step order and control flow in the RFC matches `run_reproduction()` in `src/repl.py`, including discovery → registration → reset → population load → world bank preprocessing → sampling (population + pilot) → indexing → matching (XLSX/DOCX/SciSciNet) → card rendering → zip output → summary/metrics.
- **Resource registration:** The described registration of parquet, XLSX, DOCX, and world bank resources, along with hash verification, matches `register_pipeline_resources()` and `utils/resources.py`.
- **Population loading:** Header normalization, row index offset (+2), filename stamping, population index, and schema alignment are all consistent with `hcr_xlsx/loader.py`.
- **Sampling:** Replacement sampling, deterministic RNG, draw-number assignment, preprocessing of economies/priority, and schema alignment match `hcr_xlsx/sampler.py`.
- **Pilot sampling:** Exact matching on first/last/category, ordering preservation, and `pilot.N` draw labels match `sample_pilot()` in `hcr_xlsx/sampler.py`.
- **Indexing:** Per-file name column selection using `HCR_XLSX_NAME_COLS`, name-key generation, and `OuterDict` creation align with `hcr_xlsx/indexer.py` and `utils/name_keys.py`.
- **Matching stages:** XLSX, DOCX, and SciSciNet matching behaviors and join logic align with `hcr_xlsx/matcher.py`, `manual_docx/matcher.py`, and `sciscinet_parquet/matcher.py`.
- **DOCX parsing and normalization:** Table extraction, run-to-text conversion, and column normalization are consistent with `parse_docx.py` and `manual_docx/loader.py`.
- **Card rendering and packaging:** Markdown rendering, docx conversion via Pandoc (when requested), and zip creation match `cards.py`.
- **Diagnostics and metrics:** Diagnostics report creation, counts/examples logging, live console updates, and peak RAM tracking are consistent with `src/repl.py`.

### Clarifications (behavioral nuance, not contradictions)
- **State file usage:** `PipelineManager` loads a state file, but the current REPL flow does not persist step completion during normal execution. The `signal_handler()` message indicates “State saved,” but there is no explicit call to `save_state()` in `src/repl.py` today. This RFC does not claim state persistence during execution; the note here clarifies the current implementation behavior.

### Outcome
All RFC statements and step descriptions are consistent with the current codebase. No corrections were required; the document accurately reflects the pipeline implementation as written.

## Open questions / follow-ups
- None for this RFC. The intent is purely documentation.

---

## Proposed refactor plan: transactional step architecture for REPL

Below is a concrete, implementation-ready plan to refactor the REPL so each pipeline step is **fully encapsulated**, **transactional**, **uniformly structured**, and **two-jumps max** from `src/repl.py` (REPL → step module). The plan aligns with the “game level / checkpoint” model, ensuring deterministic resumability and a consistent diagnostics story per step.

### Guiding principles
- **Two-jump accessibility:** From `src/repl.py`, each step is a single import and a single function call. The function lives in a dedicated step module. Any logic beyond trivial orchestration lives in the step module itself.
- **Uniform step interface:** Every step uses the same standardized signature and returns a structured output object. Each step’s code documents **input → transform → output** in one place.
- **Transactional semantics:** A step is atomic: either it completes and persists its output + diagnostics + state checkpoint, or it fails without partial state.
- **Checkpointed progression:** `PipelineManager` becomes the authoritative checkpoint manager. Steps check “done” status before executing; on success they mark done; on failure they do not.
- **Interactive gating:** In interactive mode, the user opts to continue after each step. Non-interactive mode runs exactly one step and exits (resume picks up at next step).
- **Diagnostics per step:** Each step emits a self-contained report to the diagnostics directory and **dumps outputs** (or references to them) so the user can inspect before proceeding.

### Step 0: Define a unified step contract
**Action:** Add a step protocol + result payload (e.g., `StepResult`) used by all steps.  
**Required fields:**
- `step_id: str` (stable identifier, e.g., `"load_population"`).
- `inputs: dict[str, Any]` (serialized summary of inputs).
- `transforms: list[str]` (structured bullets of transformations, order preserved).
- `outputs: dict[str, Any]` (summary of outputs; include file paths or table names).
- `artifacts: dict[str, Path | str]` (paths to outputs dumped to disk).
- `metrics: dict[str, Any]` (counts, timings, memory, etc.).
- `status: Literal["success", "skipped", "failed"]`.
  
**Implementation detail:** Each step returns a `StepResult`, and the REPL is responsible for writing a standardized diagnostics report using the result.

### Step 1: Introduce a step runner in `repl.py`
**Action:** In `src/repl.py`, define a **single** `run_step(step_fn, context)` helper that:
1. Checks `PipelineManager.is_done(step_id)`.
2. If done: return a `StepResult` with `status="skipped"`.
3. If not done: executes step function in a try/except.
4. On success: writes diagnostics report for the step, dumps artifacts, marks state as done.
5. On failure: writes diagnostics report with failure details and re-raises.

**Benefits:** Ensures **transactionality** and **consistent diagnostics** in one place.

### Step 2: Create dedicated step modules (one per pipeline step)
**Action:** Each step becomes its own module, e.g.:
- `src/steps/01_discover_xlsx.py`
- `src/steps/02_infer_name_columns.py`
- `src/steps/03_register_resources.py`
- `src/steps/04_reset_db.py`
- `src/steps/05_load_population.py`
- `src/steps/06_load_world_bank.py`
- `src/steps/07_sample_population.py`
- `src/steps/08_sample_pilot.py`
- `src/steps/09_index_samples.py`
- `src/steps/10_match_population.py`
- `src/steps/11_load_docx.py`
- `src/steps/12_match_docx.py`
- `src/steps/13_match_parquet.py`
- `src/steps/14_render_cards.py`
- `src/steps/15_package_cards.py`
- `src/steps/16_finalize.py`

**Structure of each step module:**
1. A top-level function `run(context) -> StepResult`.
2. Inline comments that explicitly label **Input**, **Transform**, **Output** sections.
3. No deep nesting or opaque helpers unless they are local to that module (no jumping further than the module).

### Step 3: Define a shared `PipelineContext`
**Action:** Centralize shared state in a `PipelineContext` object, passed to every step.
- Should include: config, conn, resources, xlsx_files, docx_df, outer_dict, cards, zip_path, diagnostics_dir, etc.
- Steps read/write fields they own (explicitly documented in their module).

**Benefit:** Makes step input/output explicit and discoverable in one place.

### Step 4: Standardize diagnostics per step
**Action:** Replace ad-hoc reporting with **one diagnostics writer** that consumes a `StepResult` and writes:
- **Step summary** (inputs/transformations/outputs).
- **Metrics** (counts/timings/ram).
- **Artifacts** (table snapshots, sample rows, file previews).

**Artifact expectations per step (examples):**
- Discover XLSX: write a CSV with file list + metadata.
- Load population: dump schema + sample rows to JSON/CSV.
- Match steps: dump matched rows sample + counts.
- Cards: dump list of card filenames, counts, sample card text.

### Step 5: Implement transactional behavior with `PipelineManager`
**Action:** Treat each step as a transaction boundary:
- **Before step:** confirm prerequisites are present in context.
- **During step:** stage outputs in temp locations or temp tables.
- **After step success:** move temp outputs to canonical names; only then call `save_state(step_id)`.
- **On failure:** ensure temp artifacts are cleaned or clearly marked as partial (no state update).

**Example for DuckDB:** use temp tables (`_tmp_*`) and `ALTER TABLE RENAME` only after validation.

### Step 6: Interactive vs non-interactive control flow
**Action:** Modify REPL so:
- **Interactive mode:** after each step, prompt user to “Continue” or “Stop”. If stop, exit cleanly with state saved.
- **Non-interactive mode:** run **exactly one step** and exit. Add `--resume` to continue at next step.

**Implementation:** The step runner can return a `StepResult`, and REPL decides whether to proceed based on mode.

### Step 7: Enforce a canonical step order
**Action:** In `repl.py`, declare a **single ordered list** of step functions. The REPL loops through them. This order is the single source of truth.

**Benefit:** Clean, auditable progression and consistent checkpointing.

### Step 8: Validate step contracts with linting/tests
**Action:** Add lightweight tests that:
- Ensure each step module exposes `run(context)`.
- Ensure each step returns a `StepResult` with required fields.
- Validate that step IDs are unique and ordered.

### Step 9: Migration strategy (incremental refactor)
**Action:** Refactor the REPL **step-by-step** without big-bang changes:
1. Introduce `PipelineContext`, `StepResult`, and step runner.
2. Move the **first step only** (XLSX discovery) into a module.
3. Iterate through steps in order, converting one at a time.
4. Keep existing functionality working after each conversion.

### Step 10: Ensure diagnostics are complete and reviewable between steps
**Action:** Make “diagnostics per step” mandatory.  
Before moving to the next step (in interactive mode), the user is shown the path to the diagnostics folder and a short summary of what changed.

---

## Expected outcomes
- REPL reads as a **clear pipeline of steps** where inputs/transformations/outputs are obvious at a glance.
- Each step is **self-contained, transactional, and resumable**.
- Diagnostics tell the full story of each step, including **input capture, transformation narrative, and output artifacts**.
- The pipeline becomes easier to debug, easier to extend, and safer to resume.

## Human feedback on proposed refactor plan

human review is concerned about a few things:

- humans see that the two jump requirement is too tight. in light of this we may allow this architecture: we have repl module, steps package and helpers package. steps contains one module per each step. helps contains one module per each helper category. repl module is allowed to import from steps and from helpers. steps are allowed to import from helpers. thats it.

- order and content of steps. how it should work i list below. important note 1: pipeline catches any exceptions arising from within step and properly fails the step, rolls back transaction, steps pipeline. important note 2: repl owns all console rendering.

Repl starts with Init, then does RunSteps, then CleanUp.

Init: REPL starts with triggering  init. It imports init from helpers. Inside this what happens: it reads cli args passed from REPL module, loads config from json (deprecate default - only load from json must be supported), initializes resource monitor, duck db, pipeine config, pipeline manager, diagnostic report. Creates a list of steps which must be run by pipeline, depending on whether --new or --resume was used; and if REPL started in an interactive mode then REPL itself passes the appropriate flag to step 1. Passes all these instances back to the repl.

Note btw that resource monitor, pipeline manager etc classes should be moved from repl module to helpers.

Pipeline reset is also inside the Init stuff but it is only performed if —new is chosen and ONLY after confirmation by user (user confirms with Y in interactive or passes —yes in noninteractive).

Now REPL has a list of steps to run. So it start running them. Below I list all steps in case of new session.

1) register all resources. searching for xlsx, docx, parquet will be internalized within this step. step returns an object with all needed RegisteredResource objects.

2) Load xlsx. The input is xlsx registered resources and world bank registered resource, and ofc duckdb connection and any other necessary stuff from Init (for example - but  not necessarily limited to -  diagnostic report to which step can contribute). Inside the step all xlsx are loaded one by one into population table in duckdb. during this process headers are "hcr.*" normalized and hcr.row_number, hcr.filename, are recorded. Step returns to REPL (in addition to db transaction/pipeline manager scope that REPL  must close if no exceptions came from within step), the artifacts that must be dumped (ie pandas df dumped from population table) and content that must be displayed to user (either interactive or noninteractive). REPL handles the dumping and rendering.

Note that population table is untampered with since then. Note that EVERY artifact (or rather its origin - duckdb table) must never be touched by subsequent steps.

2) new cols are added - name col inference. so new table is created in duckdb that points 1-to-1 to population table rows and has two other cols: ktp.first name and ktp.last name. Returns to REPL (also view is saved in duckdb for future reuse if resumed from this step): pandas df that joins population table and the new table; content to output to user.

3) new cols are added - ktp.economy and ktp.priority. again new table is created in duck db, 1-to-1 to population table. returns to REPL (also view is saved in duckdb for future reuse if resumed from this step): df that joins population, ktp first last name, and these new columns, content to output to user.

Note that world bank table never persists in the duck db and is only used to fill in appropriate columns. then it'd dropped. all happens within this step.

4) sampling. entire sampling happens in this step. samples table is created. it only contains the following cols: ktp filename (1-to-1 to hcr.filename), ktp fragment (1-to-1 to hcr.row_number), ktp.draw_number (new col). this way each row uniquely identifies a record from one of the XLSX RegisteredResource's, plus adds its draw number, therefore uniquely identifying a draw. Returns to REP (creates a view in duckdb which then is dumped to df): df that inner joins samples table with population table and tables from step 2 and step 3 (for naming cols in the resulting table prefer colnames from samples table); content to output to user.

5) building index - namekeys and outerdict stub. everything is ready by that point: ktp first last name are available from step 2 and samples table available from step 4, so it's straightforward. 

Note that the outerdict stub must be persisted in a dedicated duckdb table, from which it can then be loaded on any —-resume. The table has only two columns: json serialized first/last key (string); list of inner dicts serialized as json lines (meaning that each row contains entire json lines of inner dicts attributable to this first/last key; at this point obviously the list of inner dicts is empty for all namekeys).

Remember that tables created at a step are never modified by subsequent steps. So this table is also immutable - only to be used to load outerdict stub into memory if resumed from this step.

Note also that outerdict-to samples 1-to-1 match is NOT guaranteed. This is because if there are several rows in samples table that have same first name and last name, they would be conflicting. That's not a problem though - we solve this in step 6 by adding every matching row as an inner dict. Just to keep in mind that we must always use the outerdict stub table as "left" table, not samples table.

Also note that outerdict object must persist throughout the pipeline. We only pass reference to it down to steps, which can append innerdicts to keys.

Steps must not be allowed to modify outerdict in any way except appending innerdicts. No removing of innerdicts, no anything. Of course never modifying any keys of outerdict. Such functionality must never be implemented for outerdict in the first place. Only append or extend innerdict(s) by namekey, plus reading (such as getting by namekey, dumping).

Step returns to REPL: outerdict object (REPL will dump it to a JSON file where serialized first/last is a key and list of innerdicts is value; please incorporate this functionality into outerdict class itself - REPL will just trigger it); contents to output to user. 

6) here we start filling in innerdicts. and at this step we use population table. we create a new VIEW: right join population table to outerdict stubs table, on first and last name key (we deserialize outerdict stub's table keys in-duckdb query on the fly using json_parse). it has the following columns: ktp.first name, ktp last name, ktp draw number, ktp filename, ktp fragment, ktp.xlsx_match (json serialized dict: normalized ktp first and last name from the left as key, normalized ktp first and last name from the right as value). so here we must get any (ktp filename, ktp fragment) tuple from population table that matches the given first/last namekey. matching is done such that lower(unaccent(ktp.last_name)) is an exact match, and at the same time lower(unaccent(ktp.first_name)) is tokenized by "any whitespace sequence", and the first token from outerdict stub table must be present among population table's tokens.

But we need to create innerdicts. So we create a TABLE which will persist as the result of this step if we need to resume: two columns, namekey (json serialized) and innerdicts (serialized to json lines). each inner dict is a row from the new view for the given namekey - so we sort of group by namekey and the grouping function for the remaining columns is that we json serialize these rows. This is what we persist and also from which the step creates innerdict instances which it extends into outerdict instance by namekey.

Now let's talk about what the step returns to REPL. Returning outerdict is not even needed because REPL already has reference to it and so it can access it. On the other hand, our table with innerdicts is not user friendly. So what step returns to REPL  – creates a view: OUTER join our new table with population table, samples table, and tables from step 2 and step 3 (by name key); dumps df dump from the view and returns that df; also returns content to output to user.

Both views we created in this step we preserve in the duckdb.

7) at this step we continue filling innerdicts - this time with data from docx files. the architecture of this step is basically the same as step 6, the differences being that it also under the hood must load docx files and that the matching logic is different.

loading docx files: so from REPL we have all RegisteredResource instances for each docx file in question. We load them into a single, new table in duckdb the way similar to how we loaded xlsx at step 2: one by one we load them, "ktp.table_1_*" normalize them (including normalize_docx_column_name of course) and record ktp.filename, ktp.table_1_row_number. so yes, we assume that every docx must have exactly one table. if that's not the case for any of them, raise and exception from within step. and like with excel, we start row numbering from 1 here.

matching: again we create a VIEW with cols: ktp.first name, ktp last name, ktp draw number, ktp.filename, ktp.fragment, ktp.docx_match (json serialized dict: normalized ktp.first_name and ktp.last_name as key and normalized researcher author as value; see normalization rules below). to fill it, we right join docx with outerdict stub table keeping any (ktp.filename, ktp.table_1_row_number) tuple from docx table that matches ktp.first, last name from outer dict stub table. in the joined view, you use ktp.fragment colname for ktp.table_1_row_number. the matching logic is such that we (on the left - outer dict stub table) we tokenize lower(unaccent(ktp.first_name)) and lower(unaccent(ktp.first_name)) by "any whitespace sequence" and (on the right - docx table) we tokenize lower(unaccent("Researcher/author")) by "any whitespace sequence", and then (right join logic) we keep any rows where ALL tokens from outerdict stub table are found among docx table tokens.

then we create a TABLE with two columns, namekey (json serialized) and innerdicts (serialized to json lines). each inner dict is a row from the new view for the given namekey - so we sort of group by namekey and the grouping function for the remaining columns is that we json serialize these rows. This is what we persist and also from which the step creates innerdict instances which it extends into outerdict instance by namekey.

Returns to REPL – creates a view: OUTER join our new table with population table and samples table; dumps df dump from the view and returns that df; also returns content to output to user.

8) we add parquet data to outerdict. the logic is very similar to steps 6 and 8 in general, just with specifics for parquets.

we create one TABLE per parquet, two VIEWS per parquet, and two TABLEs per entire step while we right join parquet data to outerdict stub table (using logic already available from parquet matcher). This way we persist the matches conveniently.

The one table per parquet: for every of the parquets it must contain the original columns. these tables will be like a slice of rows from parquet, after matching. to clarify, ALL COLS from parquet must be preserved there. so it's the same parquet but only the matched rows. these tables must also normalize parquet colnames (using logic we used to normalize colnames before) to "ssnad.*" for author details, "ssnap.*" for authors papers, "ssnhpl0.*" for hit papers level 0, "ssnhpl1.*" for hit papers level 1. a "ssn.filename" column must also be added containing filename from registered resource.

to clarify, these tables are produced from the matching procedure already described in the parquet matcher. they are all uniquely matched via authorid (author details <-> authors papers) and paperid (authors papers <-> hit papers level 0, authors papers <-> hit papers level 1).

First table per step: note it's a TABLE because it must persist. It links outerdict stub table to author details. it contains cols: ktp.first name, ktp last name, ssnad.author id, ssnad.display_name, ssnad.display_name_alternatives, ktp.ssnad_match (json serialized dict: normalized ktp first and last name as key, normalized display name with display name alternatives as value).

The first VIEW per parquet will be to bring together per parquet data and "first table per step". it will have columns: ktp.first, last name, ktp.filename (equal to ssn.filename), ktp.fragment (parquet's unique row id - authorid for author parquets or paperid for hit parquets), and then ALL cols that come from the corresponding per-parquet table.

Second TABLE per step is for producing innerdicts (which again persists and will be used to pick up from this step on resume): two columns, namekey (json serialized) and innerdicts (serialized to json lines). using "per-parquet views", we just add each row from there as an innerdict for the matching namekey.

The second VIEW per step: this one is for returning to user - OUTER join our "first view per parquet" with population table and samples table.

Return to REPL; dumps all "2nd view per parquet" into dfs returns a list of these dfs; also returns content to output to user. REPL will dump all of these df into separate files (i.e., one file per parquet) so user can review.

9) prepare card from outerdict. this is just as currently implemented.

CleanUp. This is always executed. It properly handles winding down all operations and prints concluding message(s) to user.

---

## Implementation efforts (post-feedback)
This section documents the concrete work completed to implement the human feedback end-to-end.

- Refactored the pipeline architecture into the required three-tier structure: `src/repl.py` as orchestrator, `src/steps/` with one module per step, and `src/helpers/` with helper categories. Steps now import only helpers, while helpers encapsulate access to existing modules and utilities.
- Implemented `Init → RunSteps → CleanUp` flow in `src/repl.py`, including:
- Mandatory JSON config loading (`--config` required) with no default-config execution path.
- `--new`/`--resume` mutually-exclusive mode selection plus `--yes` confirmation gate for destructive reset.
- Transactional step runner that wraps each step in `BEGIN/COMMIT` and `ROLLBACK` on exceptions, records a diagnostics failure section, and halts the pipeline immediately.
- CleanUp guaranteed via `try/finally`, always stopping resource monitor, closing DuckDB, printing metrics, and reporting diagnostics output location.
- Moved REPL-owned classes into helpers:
- `ResourceMonitor` → `src/helpers/resource_monitor.py`
- `PipelineManager` → `src/helpers/pipeline_manager.py`
- `DiagnosticsReport` → `src/helpers/diagnostics.py`
- Added `src/helpers/init.py` that performs JSON config load, resource monitor setup, DuckDB connect, diagnostics init, and reset handling (only when `--new` + confirmation). It returns a `PipelineContext` plus the computed step list, and reconstructs `OuterDict` for resumes by loading persisted tables.
- Implemented full step set as specified, each in its own module:
- Step 1 `register_resources`: internalizes file discovery, registers XLSX/DOCX/parquet resources, returns counts and artifacts.
- Step 2 `load_xlsx`: loads XLSX into immutable `population` table and returns a full DataFrame dump.
- Step 3 `infer_names`: infers name columns per XLSX, creates `population_names` table plus `population_with_names` view and returns a joined DataFrame.
- Step 4 `add_economy_priority`: computes `ktp.economies` + `ktp.priority` using World Bank data only in-memory, persists `population_economy` table + `population_with_names_economy` view, returns a joined DataFrame.
- Step 5 `sample_population`: creates a minimal `samples` table with only `ktp.filename`, `ktp.fragment`, and `ktp.draw_number`, including pilot samples; persists `samples_with_context` and `samples_with_names` views; returns a joined DataFrame for review.
- Step 6 `build_outerdict`: creates immutable `outerdict_stub` table with JSON-serialized name keys + empty JSON-lines list, plus `outerdict_name_keys` view; builds and returns `OuterDict` for in-memory persistence.
- Step 7 `match_xlsx`: creates `xlsx_matches` view with required columns and matching logic, persists `xlsx_innerdicts` table (JSON-lines per namekey), appends into `OuterDict`, and creates `xlsx_output` view for user review.
- Step 8 `match_docx`: loads DOCX files (exactly one table per file), normalizes `ktp.table_1_*` columns with 1-based row numbering, creates `docx_matches` view and `docx_innerdicts` table, appends into `OuterDict`, and creates `docx_output` view for review.
- Step 9 `match_parquet`: builds `ssn_author_matches` (outerdict-to-author linkage), creates one matched table per parquet with full column preservation and normalized prefixes (`ssnad.*`, `ssnap.*`, `ssnhpl0.*`, `ssnhpl1.*`) plus `ssn.filename`, then creates one view per parquet plus one output view per parquet, and persists `ssn_innerdicts` (JSON-lines per namekey) appended into `OuterDict`.
- Step 10 `build_cards`: produces cards and output zip exactly as before, using the updated `OuterDict` as its source.
- Added a shared `PipelineContext` + `StepResult` in `src/helpers/context.py` to standardize step I/O, and centralized artifacts dumping in REPL (DataFrames → CSV; `OuterDict` → JSON).
- Implemented explicit table/view naming in `src/helpers/schema.py` and ensured all created tables are immutable across later steps.
- Added JSON-lines utilities and durable `OuterDict` support:
- `OuterDict` is now append-only (no mutation helpers), returns read-only views of data, and includes `dump_json()` for REPL-driven persistence.
- `helpers/jsonlines.py` provides safe JSON-lines serialization for innerdicts with `default=str` to handle parquet-derived types.
- `helpers/outerdict_io.py` loads stub tables and appends innerdicts on resume using persisted JSON-lines tables.
- Implemented a DOCX loader specialized for the pipeline’s requirements in `helpers/docx_loader.py` (exactly one table, normalized column names, 1-based row numbering).
- Implemented parquet column normalization and schema discovery helpers in `helpers/parquet_utils.py`.
- Updated tests for the new `OuterDict` API and added a new test for `OuterDict.dump_json`. All tests now run under `pixi`.
- Test run (from workspace root): `pixi run test` (31 passed, 3 skipped).

## Test execution report (real data, skipped tests)
This section records the full test execution using real data paths, including the previously skipped tests and their outcomes.

- Initial run with only repo-local data (no `data/` fixtures) produced 3 skips:
- `tests/test_csv_sample_validation.py::test_csv_rows_match_samples` skipped because `data/xlsx`, `data/samples`, and `data/OGHIST_2025_07_01.xlsx` were missing.
- `tests/test_match_names.py::test_match_csv_docx_names_on_full_dataset` skipped because `data/samples` and `data/manual_extractions` were missing.
- `tests/test_unify_names.py::test_unify_first_last_on_full_dataset` skipped because `data/samples` was missing.

- To execute these against real datasets, I linked the real data paths into the repo `data/` directory:
- `data/xlsx` → `/Volumes/Users/Anonymous/Workshop/202504161200UTC-4_Nancy_Baxter_Andrea_Tricco_collabs/2024-Historical-Highly-Cited-Researchers-lists - final`
- `data/samples` → `/Volumes/Users/Anonymous/Workshop/202504161200UTC-4_Nancy_Baxter_Andrea_Tricco_collabs/analyses/2026-01-02_enrich_full_df/data/samples`
- `data/manual_extractions` → filtered links to valid DOCX files from `/Volumes/Users/Anonymous/Workshop/202504161200UTC-4_Nancy_Baxter_Andrea_Tricco_collabs/analyses/2026-01-02_enrich_full_df/data/manual_extractions` (excluding `~$` temp file causing `BadZipFile`)
- `data/OGHIST_2025_07_01.xlsx` → `/Volumes/Users/Anonymous/Workshop/202504161200UTC-4_Nancy_Baxter_Andrea_Tricco_collabs/analyses/2026-01-02_enrich_full_df/data/OGHIST_2025_07_01.xlsx`

- Re-run: `pixi run test` resulted in 33 passed and 1 failed. The remaining failure is **data ambiguity** in `tests/test_match_names.py::test_match_csv_docx_names_on_full_dataset`:
- `match_csv_docx_names` raised multiple-match errors for 7 CSV rows (duplicate name occurrences in DOCX data):  
  `beeckman, tom` (csv_idx=113, 287),  
  `lin, zhiqun` (csv_idx=201, 302),  
  `mangione, carolm` (csv_idx=242, 306),  
  `kanatzidis, mercouri` (csv_idx=251).
