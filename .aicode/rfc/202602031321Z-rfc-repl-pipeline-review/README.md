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

## Open questions / follow-ups
- None for this RFC. The intent is purely documentation.
