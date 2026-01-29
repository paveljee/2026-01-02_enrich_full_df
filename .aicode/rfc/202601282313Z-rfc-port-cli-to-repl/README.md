# RFC: Port CLI in-memory matching pipeline into repl.py duckdb pipeline

**Timestamp (UTC):** 2026-01-28 23:13Z  \
**Author:** GPT-5.2-Codex (OpenAI)

## Task summary

The user requests that we **retire `pkg_20251223_word_tables/src/cli.py`** by **porting/rewiring all of its logic and imported matching modules** into the mature DuckDB-based pipeline in `repl.py`. The port must **replace all pandas/numpy matching logic with DuckDB logic** while retaining the **outer/inner dict abstraction** used in `repl.py`, and unify around the same CSV schema already used in both inputs. Additionally, I must **not modify any files other than this RFC** and must present a thorough, obsessive implementation plan before any code changes are made.

This RFC documents:
- Current behavior of `cli.py` and its dependency modules.
- Current behavior and architecture of `repl.py`.
- Gaps and differences (in-memory pandas vs. DuckDB SQL pipeline).
- A step-by-step plan to rewire/port the entire CLI logic into the `repl.py` pipeline using DuckDB for matching and aggregation, while preserving the `OuterDict` abstraction semantics.
- Questions for the human architect.

## Repo review (deep & thorough)

### 1. `pkg_20251223_word_tables/src/cli.py`

**Core pipeline:** `process_documents(docx_dir, csv_dir, recursive, output_dir, output_format)`.

Key steps (current in-memory, pandas-based):
1. **Locate files** using `find_files_by_extension` for DOCX and CSVs.
2. **Validate CSV headers** (`validate_csv_headers`) by reading column names and comparing sets.
3. **Parse DOCX**: `parse_docx_table` returns list of DataFrames; add filename to each frame.
4. **Load CSVs**: `pd.read_csv` each file; append `ktp.filename` field.
5. **Normalize names from CSV**: `unify_first_last` builds `ktp.first_name`/`ktp.last_name` + original column name trackers.
6. **Normalize DOCX columns**: `docx_df.rename` sanitizes headers to ensure stable column keys.
7. **Build `OuterDict`** using unique name pairs from CSV.
8. **Match CSV rows** via `CsvMatcher` (inner join on normalized first/last name).
9. **Match DOCX rows** via `DocxMatcher` (substring match of cleaned first+last within docx “Researcher/author” field using a cross-merge with numpy vectorized `np.char.find`).
10. **Create cards** per name: header, fun fact (from original name colnames), and details for each matched inner row.
11. **Output**: Write either `.txt` or `.docx` per name (pandoc for docx), zip them into one file.

**Observations:**
- All matching is performed in memory (`pandas`/`numpy`).
- Both CSV and DOCX matching are based on first/last name derived from CSV.
- `OuterDict` data model is agnostic to storage. It’s populated via matched records.
- `RIGHT_NAME_COL` in DOCX is `Researcher/author` (from `_vars.py`).
- Name normalization is a mix of manual cleaning (`unify_first_last` + `_clean_series` in DocxMatcher), not using DuckDB’s `unaccent` or SQL regex.

### 2. `pkg_20251223_word_tables/src/matchers/*`

- `CsvMatcher`: builds a name-key DataFrame from `OuterDict`, inner-joins on `ktp.first_name`, `ktp.last_name`, then groups to append records into inner lists.
- `DocxMatcher`: cleans names and docx strings by removing non-alphanumeric and casefolding. Performs a cross merge and uses `np.char.find` substring matching to decide if docx row contains both first and last names.

**Observations:**
- `DocxMatcher` is O(N×M) cross-join in-memory. DuckDB can represent this, but must be careful about size.
- Matching algorithm uses substring matching (not tokenized or exact). This must be preserved in SQL port to DuckDB.

### 3. `pkg_20251223_word_tables/src/name_utils.py`

- `unify_first_last`: chooses first/last from multiple potential CSV column names.
- `match_csv_docx_names`: alternative vectorized matcher (per-row match). This is also in-memory, not used by `cli.py` but helpful reference.

### 4. `pkg_20251223_word_tables/src/parse_docx.py`

- Parses DOCX XML into tables, extracts rich formatting (bold, italic, etc.) into Markdown-ish formatting for each cell. Header row is plain text for stable column names.
- Final DataFrame for each table uses first row as columns, then rows for data.

### 5. `repl.py`

- A full DuckDB-backed pipeline for reproducible, large-scale enrichment, with:
  - SHA256 verification of inputs.
  - DuckDB persistent DB file (`data/scisci_process.duckdb`).
  - Use of `splink_udfs` to perform `unaccent` normalization.
  - Multi-step pipeline managed by `PipelineManager` for resumability.
  - Final output is a CSV, built via DuckDB query and then `df.to_csv`.
- Uses `input_df` in CSV and normalizes into a DuckDB table `input_researchers`.
- Core logic is all in DuckDB SQL; pandas only used for final extraction and for loading input CSV.

**Observations:**
- `repl.py` is tuned for a different dataset (SciSciNet), but does expose a robust, reproducible DB pipeline style.
- There is already an **outer/inner dict abstraction** referenced by the user, presumably in `repl.py`’s data modeling or usage pattern (though not explicitly in current code). It appears the user wants to apply the `OuterDict`/`InnerDict` pattern from `pkg_20251223_word_tables` as a top-level abstraction to the DuckDB-backed pipeline.
- The ported CLI logic must live here, not in `cli.py`.

## Goal alignment & constraints

1. **Delete/retire CLI** by porting its logic into `repl.py` (the mature DuckDB pipeline).
2. **Move all matching logic** (CSV match + DOCX match) **from pandas/numpy to DuckDB SQL**.
3. **Unify around CSV schema** (input_df in `repl.py` and CSVs from `cli.py` are the same).
4. **Keep the outer/inner dict abstraction** that `repl.py` uses, and have DuckDB feed it.
5. **Do not edit any files** besides this RFC for now.

## Proposed architecture after port (high-level)

1. **Replace CLI entrypoints** with `repl.py` as a single pipeline orchestrator.
2. **Add DuckDB tables for DOCX-derived data**:
   - Parse DOCX tables with existing `parse_docx_table` into pandas (the parsing step must still be in Python). Immediately register each table in DuckDB.
   - Persist combined DOCX rows in DuckDB table `docx_rows` (with `ktp.filename`).
   - Ensure columns are sanitized to `ktp.table_1_*` naming as in current CLI.
3. **Normalize CSV inputs** using DuckDB operations:
   - Load CSV files into DuckDB; add `ktp.filename` based on file name.
   - Apply `unify_first_last` logic: either implement as SQL (CASE-based column coalescing) or use a Python pre-step to populate `ktp.first_name`, `ktp.last_name`, and original column names before writing into DuckDB.
4. **Derive `OuterDict` keys** in DuckDB:
   - `SELECT DISTINCT ktp.first_name, ktp.last_name` to build name keys.
5. **Matching in DuckDB**:
   - **CSV match**: SQL inner join between CSV table and name key table on first/last.
   - **DOCX match**: SQL cross join between name key table and DOCX rows, using a cleaned `Researcher/author` column + cleaned first/last (regex replace + lower) with substring matching using `POSITION` or `INSTR`.
   - Store results in DuckDB `matched_csv` and `matched_docx` tables.
6. **Rebuild `OuterDict`** from DuckDB matched tables, yielding inner dict lists by name key.
7. **Render cards** using the same logic (fun fact, draw numbers, docx filename, etc.), but source from DuckDB query results instead of pandas groupby.
8. **Output** (txt/docx + zip), same as CLI.

## Detailed plan & actions (implementation intentions)

### Phase 0 — Setup & sanity
- Confirm `parse_docx_table` still needed in Python, but move all matching into DuckDB.
- Confirm schema parity: `repl.py` input CSV schema is the same as CLI CSVs.
- Decide scope of CLI replacement (replace CLI entrypoints or leave stubs that call `repl.py`).
- Define new `repl.py` steps analogous to existing `PipelineManager` steps but for the word-table pipeline, or integrate into existing steps with a new pipeline class.

### Phase 1 — DuckDB schema design

**Tables to create:**
1. `ktp_csv_raw` (all CSV rows with `ktp.filename` and original columns)
2. `ktp_csv_norm` (same as raw + `ktp.first_name`, `ktp.last_name`, `ktp.first_name_original_column_name`, `ktp.last_name_original_column_name`)
3. `ktp_docx_raw` (all parsed DOCX rows + `ktp.filename` + normalized/sanitized column names)
4. `ktp_names` (distinct names from CSV; includes JSON key of `NameKey` for OuterDict)
5. `ktp_csv_matches` (CSV rows joined to `ktp_names`)
6. `ktp_docx_matches` (DOCX rows matched by substring to `ktp_names`)

**Name key schema:**
- Use `NameKey` JSON string as a deterministic `name_key` column to align with `OuterDict` keys.
- SQL expression example:
  ```sql
  json_object('ktp.first_name', ktp_first, 'ktp.last_name', ktp_last)
  ```
  or use Python to generate canonical JSON strings via `NameKey.to_json_key()` after pulling distinct names.

### Phase 2 — Port `unify_first_last` to DuckDB

**Goal:** reproduce `unify_first_last` logic (which selects first/last from multiple possible columns) using SQL, avoiding pandas.

Options:
- **Option A (SQL CASE + COALESCE):**
  - Identify first-name candidates among known columns (e.g., `hcr.firstname_middlename`, `hcr.first_name`, `hcr.firstname`).
  - Identify last-name candidates among known columns (e.g., `hcr.lastname`, `hcr.familyname`, `hcr.last_name`).
  - Choose first non-null (and non-empty) value for each and store the column name used in the `_orig` fields.
- **Option B (Python pre-pass):**
  - Use `unify_first_last` on each row in a pandas DF, then register the normalized result into DuckDB.
  - This keeps exact behavior but still pushes matching and joins into DuckDB.

**Preferred (alignment with request):** Option A if feasible, to fully remove pandas logic except for file parsing and I/O.

### Phase 3 — Docx name matching via DuckDB

**Match semantics to preserve:**
- Casefolded, non-alphanumeric stripped.
- “Match” if `docx_clean` contains `first_clean` **and** `last_clean` as substrings (order irrelevant).

**DuckDB equivalent:**
- Use `regexp_replace` to remove `[^0-9A-Za-z]` and `lower` to casefold.
- `POSITION(first_clean IN docx_clean) > 0 AND POSITION(last_clean IN docx_clean) > 0`.

Example SQL fragment:
```sql
WITH
  names AS (...),
  docx AS (...),
  cross AS (
    SELECT
      n.name_key,
      regexp_replace(lower(n.first_name), '[^0-9a-z]+', '', 'g') AS first_clean,
      regexp_replace(lower(n.last_name), '[^0-9a-z]+', '', 'g') AS last_clean,
      regexp_replace(lower(d."Researcher/author"), '[^0-9a-z]+', '', 'g') AS docx_clean,
      d.*
    FROM names n
    CROSS JOIN docx d
  )
SELECT *
FROM cross
WHERE POSITION(first_clean IN docx_clean) > 0
  AND POSITION(last_clean IN docx_clean) > 0;
```

**Performance considerations:**
- Cross join can be huge; consider filtering to non-empty names and docx_clean not empty.
- Potentially add pre-filter on first or last initial to reduce cross join size.
- If dataset large, use `JOIN` on tokenized surnames in `docx_clean` using `LIKE` or `regexp_matches` (though substring match still required).

### Phase 4 — Constructing `OuterDict` from DuckDB

**Current behavior:**
- `OuterDict` is seeded with all unique names.
- CSV and DOCX matches append `InnerDict`s to the inner list for each name key.

**DuckDB equivalent:**
- Query matched rows grouped by `name_key`.
- Serialize each row to JSON or mapping, then hydrate `InnerDict` in Python.
- Preserve `procedure.dataset_id_field` metadata: CSV and DOCX procedure objects can be reused.

**Plan:**
1. Query `ktp_names` to build name keys via `NameKey` (Python). Build `OuterDict`.
2. Query `ktp_csv_matches` and `ktp_docx_matches` as records grouped by `name_key`.
3. For each group, call `_append_records` on matcher-like helper (or directly `OuterDict.ensure_inner_list_by_key`).

### Phase 5 — Card generation & output (DuckDB-backed)

- Keep existing rendering logic (draw numbers, fun fact, header, per-row fields) in Python.
- Source data from `OuterDict` which now originates from DuckDB matches.
- Output creation (TXT/DOCX + ZIP) remains unchanged.

### Phase 6 — CLI retirement and integration

- Remove or stub `cli.py` (or rewire CLI to call `repl.py` pipeline). Per user request, “get rid of cli.py” suggests deprecating or removing entrypoints.
- Consolidate all functionality inside `repl.py`, possibly with a new “word table enrichment” pipeline class or mode.
- Ensure `repl.py` supports file inputs for DOCX and CSV directories (mirrors CLI options).

### Phase 7 — Reproducibility & state management

- Consider using `PipelineManager` to persist steps for this new pipeline as well.
- Write metadata (e.g., `pipeline_state.json`) to a separate namespace to avoid conflict with SciSciNet pipeline steps.

## Potential issues & design decisions

1. **DuckDB SQL vs Python for unify_first_last:**
   - Full SQL implementation may be complex but is doable with `CASE` and `COALESCE` if input columns are consistent.

2. **Cross join blowup for DOCX matching:**
   - DuckDB can handle cross joins, but for large CSV/Docx counts it may be expensive. Consider filtering with surname tokens or even indexing docx rows by last name token.

3. **OuterDict serialization:**
   - `OuterDict` uses JSON keys; in DuckDB, `json_object` ordering may differ. To ensure stable keys, build keys in Python using `NameKey` after pulling distinct names.

4. **CLI removal vs. deprecation:**
   - The user wants to get rid of CLI; will confirm whether to delete file or keep a wrapper that calls `repl.py` for backwards compatibility.

5. **Pandoc dependency for DOCX output:**
   - `cli.py` uses pandoc and a reference docx; if this is moved to `repl.py`, we must preserve the reference file path and validate that pandoc is available.

## Explicit action list (planned edits later, not done now)

1. **Add a new pipeline section** in `repl.py` for word-table enrichment, potentially under a CLI mode or a config flag.
2. **Replace in-memory matching with DuckDB SQL** queries and store matches in tables.
3. **Port name normalization logic** into DuckDB or a minimal Python-to-DuckDB transform step.
4. **Build `OuterDict` from DuckDB results** and reuse existing card generation logic.
5. **Remove or deprecate `cli.py`** (depending on decision).
6. **Add tests / validation scripts**: compare outputs of old CLI vs. new pipeline for a sample dataset.

## Q&A for human architect

1. **CLI removal expectation:** Should `cli.py` be deleted outright, or left as a thin wrapper that calls `repl.py` for backward compatibility?
2. **Name normalization authority:** Do you require a **pure DuckDB SQL** implementation of `unify_first_last`, or is a minimal Python pre-processing step acceptable as long as matching is DuckDB-based?
3. **Output format parity:** Must the output ZIP naming and file naming be byte-for-byte identical to current CLI outputs, or is functional equivalence acceptable?
4. **Docx matching scale:** Do you expect the docx matching to be large enough to require additional optimizations (indexing / pre-tokenizing), or is a direct cross join acceptable?
5. **`OuterDict` placement:** Should the `OuterDict`/`InnerDict` abstraction remain in `pkg_20251223_word_tables`, or should it be moved into `repl.py` (or a new shared module)?
6. **Pipeline coexistence:** Should the existing SciSciNet pipeline in `repl.py` remain intact, or is this a repurposing of `repl.py` into the word-table pipeline exclusively?
