# RFC: Full End-to-End Walkthrough for REPL and Mode-3 `p_gf` Detour

**Timestamp (UTC):** 2026-03-10 15:21Z  \
**Author:** GPT-5 Codex (OpenAI)

## Task summary
Provide a complete execution walkthrough for:
- the full `src/repl.py` flow (including scaffolding and all pipeline steps), and
- the full `src/detours/detour_mode3_pgf_stats.py` flow.

This RFC is intentionally exhaustive and sequence-first so critical junctions can be isolated for review later.

## Goals
- Enumerate all invocation paths and branch behavior for REPL.
- Enumerate the exact sequential processing performed by each REPL step (`01` through `10`).
- Enumerate the exact sequential processing in the mode-3 read-only detour.
- Capture control flow, side effects, invariants, and output artifacts.

## Non-goals
- Deciding mini-dataset strategy.
- Refactoring or modifying pipeline code.
- Covering the step-4 breakdown detour (explicitly out of scope).

---

## 1) FULL End-to-End REPL Walkthrough (`src/repl.py` + full step chain)

### 1.1 Invocation surface

Primary entrypoint:
- `python -m src.repl --config <config.json> (--new | --resume|--continue) [--yes] [--non-interactive] [--quiet]`

Project wrappers:
- `pixi run repl` runs: `python -m src.repl --config config.repl.json --new --yes --non-interactive`
- `pixi run module --module_name src.repl` runs the same branch in `pyproject.toml`

Hard CLI constraints:
1. `--config` is required.
2. Exactly one of `--new` or `--resume/--continue` is required.
3. `--yes` changes prompt behavior in both `--new` and `--resume` paths.

Representative invocation matrix:
1. `--new` + interactive shell + no `--yes`:
- Prompts `Reset pipeline state and database? [y/N]`.
- If not `y`, initialization fails (`Pipeline reset confirmation required for --new`).
2. `--new --yes`:
- Skips reset prompt and proceeds directly.
3. `--new --non-interactive` without `--yes`:
- No prompt available; reset is not confirmed; initialization fails.
4. `--resume` + interactive + no `--yes`:
- Prompts `Resume pipeline from next step? [y/N]`; non-`y` exits cleanly before running steps.
5. `--resume --non-interactive --yes`:
- Resumes immediately without prompt.
6. `--resume --non-interactive` without `--yes`:
- Prints warning and diagnostics path, then exits before running steps.
7. `--quiet`:
- Still runs steps and writes diagnostics report; only reduces diagnostic section verbosity behavior passed to `run_step`.

### 1.2 Top-level process in `main()`

Sequential flow:
1. Parse args.
2. Call `run_reproduction(args)`.
3. Handle `KeyboardInterrupt` with exit code `130`.
4. Handle any other exception via Rich traceback and exit `1`.

### 1.3 `run_reproduction(args)` control flow

#### 1.3.1 Runtime mode setup
1. Compute `interactive = not args.non_interactive`.
2. Initialize `reset_confirmed = False`, `auto_confirm = bool(args.yes)`.
3. For `--new`:
- If `--yes`: set `reset_confirmed = True`.
- Else if interactive: prompt for reset confirmation.
- Else non-interactive/no-yes: leave `reset_confirmed = False`.

#### 1.3.2 Pipeline initialization via `init_pipeline(...)`

Call:
- `init_pipeline(args, interactive=interactive, reset_confirmed=reset_confirmed)`

This returns:
- `context` (`PipelineContext`)
- `steps_to_run` (ordered step IDs)
- `monitor` (`ResourceMonitor`, started)

### 1.4 `init_pipeline(...)` full sequence (`src/helpers/init.py`)

1. Validate `args.config` exists.
2. Parse config JSON into `PipelineConfig`.
- Enforces required `files_config` keys and required fields per entry.
- Enforces at least one HCR key prefix (`hcr_xlsx_...`).
- Normalizes `sample_draw_sizes` integer shorthand into `{"size": int, "replace": False}`.
3. Build `PipelineManager(state_file, db_file)`.
4. Open DuckDB connection (`manager.connect_db()`):
- `SET memory_limit='20GB'`
- `INSTALL splink_udfs FROM community; LOAD splink_udfs;`
5. Start `ResourceMonitor` thread.

New-run reset path:
6. If `args.new` and `reset_confirmed` is false: raise ValueError.
7. If `args.new` and confirmed: `_reset_pipeline(...)`.
- Drops canonical tables:
  - `registered_resources`, `population`, `population_names`, `population_economy`, `samples`,
  - `outerdict_stub`, `xlsx_innerdicts`, `docx_rows`, `docx_innerdicts`,
  - `ssn_author_matches`, `ssn_innerdicts`
- Drops canonical views:
  - `population_with_names`, `population_with_names_economy`, `samples_with_context`,
  - `samples_with_names`, `outerdict_name_keys`, `xlsx_matches`, `xlsx_output`,
  - `docx_matches`, `docx_output`
- Drops any remaining `ssn_%` objects discovered in `information_schema.tables`.
- Resets manager state JSON (`steps_completed`, `session_dir`).

Session and diagnostics pathing:
8. Determine `session_stamp`:
- `--new`: always new timestamp and saved to state.
- `--resume`: reuse saved session stamp if present, otherwise create/save one.
9. Create `DiagnosticsReport` at `data/diagnostics/<session_stamp>/repl_diagnostics.md`.
10. Compute `steps_to_run`:
- `--new`: full `STEP_ORDER`.
- `--resume`: only steps not marked done in state.

Resume hydration of context dependencies:
11. If step `01_register_resources` marked done, re-register resources into context.
12. If step `06_build_outerdict` marked done, reconstruct `OuterDict` from `outerdict_stub` keys.
13. If downstream match steps are already done, re-append persisted innerdict payloads into reconstructed `OuterDict`:
- `07_match_xlsx`: load from `xlsx_innerdicts` JSONL table.
- `08_match_docx`: load from `docx_innerdicts` JSONL table.
- `09_match_parquet`: load from `ssn_author_output` rows table.

Context return:
14. Return `InitResult(context, steps_to_run, monitor)`.
15. On any init error: stop monitor, close DB manager, re-raise.

### 1.5 Session log + diagnostics wiring in REPL runtime

After init returns:
1. Set session log path: `data/diagnostics/<session_stamp>/repl_session.log`.
2. If `--new` + confirmed reset and old session log exists: delete it.
3. Load prior session log lines into `log_history` if file exists.
4. Define `log(msg, style)`:
- Append styled line to session log file.
- Append to in-memory history.
- Print via Rich.
5. Assign `context.log = log` so steps can emit live logs.
6. If interactive, print prior history and emit resume marker timestamp in config timezone.

### 1.6 Resume confirmation branch at runtime

If `args.resume`:
1. If no `--yes` and interactive: ask `Resume pipeline from next step? [y/N]`; non-`y` returns early.
2. If no `--yes` and non-interactive: print warning + diagnostics path and return early.
3. Else proceed to step execution loop.

### 1.7 Step execution loop semantics (`run_step` transaction wrapper)

For each `step_id` in `steps_to_run`:
1. Resolve function from `STEP_REGISTRY`; unknown step -> ValueError.
2. Call `run_step(step_id, step_fn, context, log=log, verbose=not args.quiet)`.

`run_step(...)` behavior:
1. If state already marks step done: return `StepResult(messages=[Skipped...])`.
2. Log `Running step: <id>`.
3. `BEGIN` transaction.
4. Execute `step_fn(context)`.
5. On success:
- `COMMIT`
- mark state done in state file.
6. On exception:
- `ROLLBACK`
- append failed section to diagnostics report
- re-raise.
7. If verbose and step has diagnostics/messages, append section to diagnostics markdown.
8. Dump artifacts to `data/diagnostics/<session>/step_artifacts`:
- DataFrames -> CSV files
- list[DataFrame] -> indexed CSV files
- `OuterDict` -> JSON
- `Path` artifacts -> tracked in message list
9. Append artifact summary messages to step result.

Back in REPL loop:
3. Print every step message via `log(..., green)`.
4. If current step is `10_build_cards`, capture `zip_path` and card count.
5. If interactive and no `--yes`, prompt `Continue to next step? [y/N]` after each step.

### 1.8 Full step chain (`01` → `10`) with sequential processing

#### Step `01_register_resources`
1. Resolve configured HCR XLSX paths from `files_config` entries with HCR key prefix.
2. Discover DOCX files in `docx_dir` (non-recursive, skip `~$`).
3. Register all pipeline resources with hash verification:
- SciSciNet parquets (`author_details`, `authors`, `authors_paper`, `paper_author_affiliation`, `affiliations`, `hit_papers_0`, `hit_papers_1`, `fields`)
- HCR XLSX resources
- World Bank XLSX resource
- DOCX resources
4. Persist resource registry table `registered_resources`.
5. Return resource counts and examples in diagnostics.

#### Step `02_load_xlsx`
1. Iterate all registered XLSX resources.
2. Read XLSX via pandas/openpyxl (skip temporary lock files).
3. Normalize headers to `hcr.*` format.
4. Add `hcr.row_number` (excel-like row index +2), `hcr.filename`, and global `ktp.population_index`.
5. Coerce non-index columns to string.
6. Create/append table `population`, dynamically adding missing columns when files differ schema.
7. Return full `population` DataFrame artifact and row/column counts.

#### Step `03_infer_names`
1. If global `HCR_XLSX_NAME_COLS` mapping is empty:
- infer first/last name columns per XLSX by candidate header matching.
2. Validate every configured XLSX has a mapping.
3. Build filename-conditioned SQL CASE expressions for first and last names.
4. Create table `population_names` with `ktp.population_index`, `ktp.first_name`, `ktp.last_name`.
5. Create view `population_with_names` joining `population` + `population_names`.
6. Return merged DataFrame artifact.

#### Step `04_add_economy_priority`
1. Load World Bank sheet `Country Analytical History`.
2. Locate latest FY column in sheet dynamically.
3. Build `income_map` from country + aliases (`KTP_COUNTRY_ALIASES`) to income labels.
4. Infer affiliation columns from `population` schema and filename-specific overrides (`HCR_XLSX_AFFILIATIONS_COLS`).
5. Create `population_economy`:
- tokenize affiliation text
- fuzzy token containment match against `income_map.match_norm`
- compute economies JSON list, income group, economy match payload
- assign priority and priority-group labels using country buckets (greater china, non-English non-EU HIC, EU, English HIC)
6. Create view `population_with_names_economy` joining population + names + economy output.
7. Select a stable column ordering for output artifact.
8. Return merged DataFrame artifact and country-entry diagnostics.

#### Step `05_sample_population`
1. Validate draw size total equals `total_draws - pilot_count`.
2. Load population index pool.
3. Build pilot exclusion set by matching configured pilot triples in pilot XLSX file.
4. Precompute random draw batches by `sample_draw_sizes`, honoring per-draw `replace` flag and exclusion state.
5. Materialize each random draw:
- build temporary `sample_indices`
- join to `population`
- append to `samples` with draw labels
6. Materialize pilot draws:
- query pilot rows
- enforce expected pilot count
- stable order by configured triple sequence
- assign labels `pilot.1`, `pilot.2`, ...
- append to `samples`
7. Create views:
- `samples_with_context` (joins samples + population + names + economy, sorted by draw semantics)
- `samples_with_names` (minimal join for downstream name matching)
8. Drop temp tables and return joined DataFrame artifact.

#### Step `06_build_outerdict`
1. Identify rows in `samples_with_names` with null/empty first/last names.
2. Log excluded row previews and counts.
3. Create excluded-key archive objects:
- table `outerdict_stub_excluded`
- view `outerdict_name_keys_excluded`
4. Build unique valid name pairs from `samples_with_names`.
5. Create in-memory `OuterDict` from these name keys.
6. Persist key universe objects:
- table `outerdict_stub`
- view `outerdict_name_keys`
7. Return artifacts containing `outer_dict` and excluded archive `OuterDict`.

#### Step `07_match_xlsx`
1. Compute HCR payload column set (`hcr.*` minus excluded columns).
2. Build view `xlsx_matches`:
- normalize name keys and population names
- token-based matching (`last exact`, first-token containment)
- attach draw labels if available
- include economy/priority + HCR payload columns
- include structured `ktp.xlsx_match` JSON payload
- apply canonical draw/source ordering via shared draw sort CTEs
3. Materialize grouped JSONL table `xlsx_innerdicts` keyed by `name_key`.
4. Append JSONL innerdict rows to `context.outer_dict` via `XlsxMatchProcedure`.
5. Create `xlsx_output` view and load output DataFrame artifact.

#### Step `08_match_docx`
1. Parse DOCX resources using `load_single_table_docx` (strictly one table per file).
2. Normalize DOCX column names to `ktp.table_1_*` namespace.
3. Attach footnotes/comments metadata and per-row row number.
4. Persist raw DOCX rows to `docx_rows` table.
5. Validate required researcher/author name column exists.
6. Build view `docx_matches`:
- normalize source name tokens and docx name field
- match by substring containment of normalized first/last tokens
- attach draw labels and structured `ktp.docx_match` payload
- apply shared draw/source ordering
7. Materialize grouped JSONL table `docx_innerdicts`.
8. Append JSONL innerdict rows to `context.outer_dict` via `DocxMatchProcedure`.
9. Create `docx_output` view and return output DataFrame artifact.

#### Step `09_match_parquet` (largest critical junction)

Sequential sub-phases:
1. Validate `context.outer_dict` and `context.resources` are initialized.
2. Load parquet file paths from config.
3. Emit legend lines for log tag semantics.
4. Create `ssn_author_matches` by exact normalized name match against `author_details` (`display_name` + alternatives).
5. Create `ssn_author_papers` by joining matched authors to `authors_paper`.
6. Create `ssn_all_hits` union table from level0/level1 hit parquet filtered to needed papers.
7. Create `ssn_author_hit_agg` and identify zero-hit rows.
8. Create filtered view `ssn_author_matches_nonzero_hit` and distinct author-id view `ssn_author_match_nonzero_hit_author_ids`.
9. Create `ssn_author_agg` (paper list and field-id aggregates) limited to nonzero-hit matched author pairs.
10. Materialize filtered parquet-derived tables via `_create_parquet_table(...)`:
- matched `author_details`
- matched `authors`
- matched `paper_author_affiliation`
- matched `affiliations`
11. Create author-level output table `ssn_author_output` joining match rows + materialized parquet tables + aggregates.
12. Compute diagnostics:
- top-paper reduction estimate
- top-institution reduction estimate
- field-id display-name mapping coverage
13. Create final enriched innerdict table `ssn_innerdicts`:
- top-K papers per author
- top-K institutions per author
- concept display names
- draw/source ordering
- drop intermediate draw-order helper columns
14. Append row-wise innerdicts from `ssn_innerdicts` to `context.outer_dict` via `ParquetMatchProcedure`.
15. Create sorted output view `ssn_parquet_output` and load output DataFrame artifact.
16. Return step messages/diagnostics with matched row counts.

#### Step `10_build_cards`
1. Validate `OuterDict` exists.
2. Read `card_subset_mode` and validate against supported modes.
3. Define helper predicates for filtering:
- sciscinet-innerdict detection by filename provenance
- exactness test for `ktp.xlsx_match` payload
- docx table-field completeness (required `ktp.table_1_*` non-empty except optional columns/placeholders)
4. Evaluate all names and classify each into subset modes `0..4`:
- Mode 0: no filtering
- Mode 1: exactly-one-sciscinet + exact-xlsx + complete-docx
- Mode 2: complement of mode 1
- Mode 3: exactly-one-sciscinet + exact-xlsx
- Mode 4: complement of mode 3
5. Log mode pass/fail table.
6. Build filtered `OuterDict` for selected mode.
7. Build card intro text with timezone-aware date and subset note.
8. Render cards via `build_cards(...)` with progress callbacks.
9. Write zip output via `write_cards_zip(...)`:
- `txt` mode: write text files and zip
- `docx` mode: run pandoc conversions (parallel workers) then zip
10. Return artifacts: `cards` map and output `zip_path`.

### 1.9 Completion, exception, and teardown behavior

Normal completion:
1. Stop monitor and compute peak RAM.
2. Close pipeline manager connection.
3. Print execution metrics table.
4. Log metrics and diagnostics report path to session log.
5. If cards built, log output zip path.
6. Return `zip_path` or `None`.

Exception path:
1. Any exception in loop logs `Exited prematurely: <Type>: <msg>`.
2. Exception re-raised to `main()` handler.
3. `main()` prints traceback and exits non-zero.
4. `run_step` ensures failed step transaction rollback and diagnostics section append.

### 1.10 Strict function invocation ledger (called functions only)

This subsection is a strict call ledger for the executed REPL path. It separates:
1. functions that are actually invoked by script execution, and
2. nearby functions that exist in code but are not invoked on this path.

#### 1.10.1 Top-level REPL call tree

`src.repl.main()` invokes, in order:
1. `argparse.ArgumentParser(...)`
2. `parser.add_argument(...)` / `add_mutually_exclusive_group(...)`
3. `parser.parse_args()`
4. `run_reproduction(args)`
5. on interrupt: `console.print(...)`, `sys.exit(130)`
6. on other exception: `console.print_exception()`, `sys.exit(1)`

`src.repl.run_reproduction(args)` invokes, in order/branches:
1. `init_pipeline(args, interactive=..., reset_confirmed=...)`
2. filesystem session-log operations:
- `session_log_path.exists()`
- `session_log_path.unlink()` (new-run reset path only)
- `session_log_path.read_text(...)` (if existing)
3. closure definitions:
- `print_history()` (called only when interactive)
- `log(...)` (called throughout runtime)
4. `print_history()` (interactive only)
5. resume prompt branch:
- `console.print(...)`
- `console.input(...)`
6. step loop per `step_id`:
- `STEP_REGISTRY.get(step_id)`
- `run_step(step_id, step_fn, context, log=log, verbose=not args.quiet)`
- `log(...)` for every message line
7. shutdown path:
- `monitor.stop()` (if monitor exists)
- `context.manager.close()` (if context exists)
8. summary output:
- `Table(...)`, `m_table.add_column(...)`, `m_table.add_row(...)`, `console.print(m_table)`
- additional `log(...)` calls for metrics/diagnostics/output path

#### 1.10.2 Initialization call tree (`src/helpers/init.py`)

`init_pipeline(...)` invokes:
1. `PipelineConfig.from_json(Path(args.config))`
2. `PipelineManager(...)`
3. `manager.connect_db()`
4. `ResourceMonitor()`, `monitor.start()`
5. new-run branch:
- `_reset_pipeline(conn, manager)` -> `conn.execute(...)` table/view drops + `manager.reset_state()`
6. session handling:
- `datetime.now().strftime(...)`
- `manager.set_session_dir(...)` / `manager.get_session_dir()`
7. diagnostics:
- `DiagnosticsReport(diagnostics_dir)`
8. resume hydration branches:
- `manager.is_done(...)` checks
- `register_pipeline_resources(config)` when needed
- `_load_outerdict_stub(conn, OUTERDICT_STUB_TABLE)` when needed
- `append_innerdicts_from_jsonlines_table(...)` for XLSX/DOCX restoration when needed
- `append_innerdicts_from_rows_table(...)` for parquet restoration when needed
9. context assembly:
- `PipelineContext(...)`
10. on init exception:
- `monitor.stop()`
- `manager.close()`

`_load_outerdict_stub(...)` invokes:
1. `conn.execute(...).fetchall()`
2. `NameKey.from_json_key(...)` for each row
3. `OuterDict.from_name_keys(...)`

#### 1.10.3 Step runtime wrapper call tree (`src/helpers/repl_runtime.py`)

`run_step(...)` invokes:
1. `context.manager.is_done(step_id)`
2. `log(...)` ("Running step")
3. `context.conn.execute("BEGIN")`
4. `step_fn(context)` (one of steps `01`..`10`)
5. success path:
- `context.conn.execute("COMMIT")`
- `context.manager.save_state(step_id)`
6. failure path:
- `context.conn.execute("ROLLBACK")`
- `context.diagnostics.add_section(...)`
7. diagnostics path:
- `context.diagnostics.add_section(...)` (verbose mode)
8. artifact path:
- `dump_artifacts(context, step_id, result.artifacts)`

`dump_artifacts(...)` invokes (by artifact type):
1. `context.artifacts_dir.mkdir(...)`
2. parquet special list path:
- `DataFrame.to_csv(...)`
3. generic DataFrame path:
- `DataFrame.to_csv(...)`
4. `OuterDict` path:
- `artifact.dump_json(path)`
5. path artifacts:
- append `Path` directly

#### 1.10.4 Per-step invoked helper functions (`01`..`10`)

Step `01_register_resources` invokes:
1. `configured_hcr_xlsx_paths(...)`
2. `discover_docx_files(...)`
3. `register_pipeline_resources(...)`
4. `_resource_registry_frame(...)`
5. `register_frame(...)`
6. `context.conn.execute(...)` (create/drop registry temp table)

Inside `register_pipeline_resources(...)` (called by step 01):
1. repeated `register_resource(...)`
2. `configured_hcr_xlsx_paths(...)`
3. `configured_hcr_xlsx_entries(...)`
4. `register_resources(...)` for XLSX and DOCX batches
5. `discover_docx_files(...)`

Step `02_load_xlsx` invokes:
1. `_build_population_table(...)`
2. `conn.execute(...).df()` for artifact load

Inside `_build_population_table(...)`:
1. `Path(resource.__fspath__())`
2. `pd.read_excel(...)`
3. `_normalize_hcr_header(...)`
4. `conn.execute(...)` table existence/schema queries
5. `register_frame(...)`
6. `conn.execute(...)` insert/alter SQL

Step `03_infer_names` invokes:
1. `_infer_name_columns_from_xlsx(...)` (if mapping empty)
2. `_build_name_expr(...)` twice
3. `conn.execute(...)` create table/view SQL
4. `conn.execute(...).df()`

Inside `_infer_name_columns_from_xlsx(...)`:
1. `pd.read_excel(...)`
2. `_normalize_hcr_header(...)`
3. local `pick(...)`

Step `04_add_economy_priority` invokes:
1. `_load_income_labels(...)`
2. `pd.DataFrame(...)`
3. `register_frame(...)`
4. `conn.execute(...)` for table/view creation
5. `_infer_affiliation_columns(...)`
6. `_normalize_affiliation_map(...)`
7. `_affiliation_case(...)` (which invokes `_affiliation_expression(...)`)
8. `_non_english_non_eu_hics(...)`
9. local `_countries_for(...)`
10. local `_sql_in_list(...)`
11. final `conn.execute(...).df()`

Step `05_sample_population` invokes:
1. local `log(...)` (delegates `context.log(...)`)
2. `conn.execute(...).df()/fetchall()/fetchone()`
3. `register_frame(conn, "pilot_triples", ...)`
4. `np.random.default_rng(...)`
5. `_precompute_draw_batches(...)`
6. per-draw:
- `register_frame(conn, "sample_indices", ...)`
- `conn.execute(...).df()`
- `_append_samples(...)`
7. pilot append branch:
- `_append_samples(...)`
8. view creation SQL via `conn.execute(...)`
9. cleanup SQL drop temp tables

Step `06_build_outerdict` invokes:
1. local `_normalize_name_part(...)`
2. local `_name_key_json(...)`
3. `conn.execute(...).df()`
4. `register_frame(...)` for excluded stub + active stub
5. `conn.execute(...)` create tables/views
6. `NameKey(...)` model construction
7. `OuterDict.from_name_keys(...)`
8. `OuterDict(...)` constructor for excluded archive

Step `07_match_xlsx` invokes:
1. `conn.execute(...).fetchall()` for schema
2. `hcr_excluded_columns(...)`
3. `draw_sort_ctes_sql(...)`
4. `draw_sort_order_by_sql(...)`
5. `conn.execute(...)` create view SQL
6. `conn.execute(...).df()`
7. `dumps_jsonlines(...)`
8. `register_frame(...)`
9. `append_innerdicts_from_jsonlines_table(..., procedure=XlsxMatchProcedure(), ...)`
10. `conn.execute(...)` create output view + load output DF

Step `08_match_docx` invokes:
1. `load_single_table_docx(context.resources.docx_resources)`
2. `register_frame(...)`
3. `normalize_docx_column_name(RIGHT_NAME_COL)`
4. `draw_sort_ctes_sql(...)`
5. `draw_sort_order_by_sql(...)`
6. `conn.execute(...)` create match view + load DF
7. `dumps_jsonlines(...)`
8. `register_frame(...)`
9. `append_innerdicts_from_jsonlines_table(..., procedure=DocxMatchProcedure(), ...)`
10. `conn.execute(...)` create output view + load output DF

Inside `load_single_table_docx(...)` (called by step 08):
1. `Path(resource.__fspath__())`
2. `parse_docx_tables_and_notes(path)`
3. `normalize_docx_column_name(...)`
4. pandas frame construction/concat

Step `09_match_parquet` invokes:
1. `normalize_parquet_column_name(...)`
2. local `scalar_int(...)`
3. local `log_tag(...)`
4. multiple `conn.execute(...)` table/view materializations + metrics queries
5. `_create_parquet_table(...)` four times for matched parquet tables
6. `parquet_columns(...)` (inside `_create_parquet_table`)
7. `parquet_filename(...)` (inside `_create_parquet_table` and additional filename payload paths)
8. `draw_sort_ctes_sql(...)`
9. `draw_sort_order_by_sql(...)`
10. `append_innerdicts_from_rows_table(..., procedure=ParquetMatchProcedure(), key_column=KTP_SOURCE_KEY_COL)`
11. `conn.execute(...).df()` for output dataframe

Step `10_build_cards` invokes:
1. local `log(...)`
2. local `progress_bar(...)`
3. local `hcr_bundle_name(...)`
4. local callbacks `on_build_progress(...)` and `on_conversion_progress(...)`
5. local `_filtered_outer_dict(...)` and its nested helpers:
- `_mode_matches(...)`
- `_extract_filenames(...)`
- `_is_sciscinet_inner(...)`
- `_is_exact_xlsx_match_payload(...)`
- `_has_present_xlsx_match_payload(...)`
- `_is_non_empty_value(...)`
- `_has_complete_docx_table_fields(...)`
6. `OuterDict.from_name_keys(...)` and `subset_outer.add_inner(...)`
7. `datetime.now(ZoneInfo(...)).strftime(...)`
8. `build_cards(...)`
9. `write_cards_zip(...)`

#### 1.10.5 Defined but not invoked on the REPL step path

1. `src.steps.step_08_match_docx.load_docx_tables(...)` is defined but step `08` runtime invokes `load_single_table_docx(...)`, not `load_docx_tables(...)`.
2. Any detour module entrypoints are not invoked by REPL path.

---

## 2) FULL End-to-End Mode-3 `p_gf` Stats Detour Walkthrough (`src/detours/detour_mode3_pgf_stats.py`)

### 2.1 Invocation surface

Primary entrypoint:
- `python -m src.detours.detour_mode3_pgf_stats --config <config.json>`

Behavioral contract:
1. No `--new`/`--resume` semantics (unlike REPL).
2. No detour-specific runtime flags in current version.
3. Read-only analytics over an existing DB.

### 2.2 Top-level process in `main()`

1. Parse required `--config`.
2. Load `PipelineConfig`.
3. Call `run_detour(config)`.
4. If result unsuccessful, raise runtime error.
5. Keyboard interrupt exits `130`; other exceptions re-raised.

### 2.3 `run_detour(config)` full sequence

1. Start `ResourceMonitor`.
2. Open DuckDB connection in read-only mode:
- `duckdb.connect(str(config.db_file), read_only=True)`
3. Build metadata by calling `_build_mode3_pgf_metadata(conn)`.
4. Print human-readable summary via `_print_summary(metadata)`.
5. Construct `DetourResult` with:
- `success=True`
- `steps_completed=[]` (`DETOUR_STEPS` is empty)
- summary text
- metadata payload
6. On exception:
- print red failure line
- re-raise
7. Finally:
- stop monitor, capture peak RAM
- close connection
8. Print execution metrics table and return `DetourResult`.

### 2.4 `_build_mode3_pgf_metadata(conn)` full sequence

#### 2.4.1 Base counts and key universe
1. Count population rows from `population_with_names_economy`.
2. Load ordered key universe from `outerdict_stub.name_key`.
3. Set `outerdict_keys = len(outer_keys)`.

#### 2.4.2 Load XLSX payloads per key
1. Read `name_key, innerdicts` from `xlsx_innerdicts`.
2. Parse each `innerdicts` blob as JSON Lines (`loads_jsonlines`).
3. Collect `ktp.xlsx_match` payload values per `name_key`.

Helper predicates used:
- `_has_present_xlsx_match_payload(value)`
- `_is_exact_xlsx_match_payload(value)`

Exactness logic details:
1. Empty/None payload is not exact unless treated as absent.
2. Valid exact payload requires matching token set and matching normalized last-name fields between source-key and matched row.
3. Any malformed JSON string payload fails exactness.

#### 2.4.3 Load parquet innerdict evidence per key
1. Read from `ssn_innerdicts` columns:
- `ktp.source_key`
- `ssnau.p_gf`
- `ssnau.inference_counts`
- `ssnau.inference_sources`
2. Build:
- sciscinet row count per key
- full row tuples per key for selected-key extraction

#### 2.4.4 Reconstruct mode-3 selection

For each key in `outer_keys`:
1. `sciscinet_exactly_one_ok := sciscinet_count == 1`.
2. `xlsx_exact_ok := any(present payload) and all(present payload exact)`.
3. Count pass totals per rule.
4. If both rules pass:
- append key to selected set
- enforce invariant: exactly one sciscinet row tuple exists
- append that tuple’s `p_gf` to distribution array
- if `p_gf` missing, capture `(inference_counts, inference_sources)` for audit.

#### 2.4.5 Compute distribution statistics

From selected set:
1. `selected_names`
2. non-missing vector and `non_missing_n`, `missing_n`
3. mean, SD, SE, 95% CI
4. min, q1, median, q3, max
5. IQR and Tukey fences
6. lower/upper/total outlier counts and percentages

#### 2.4.6 Compute bucket partition and invariants

Buckets over selected set:
1. missing
2. exactly `0`
3. exactly `0.5`
4. exactly `1`
5. `(0, 0.5)` exclusive
6. `(0.5, 1)` exclusive

Invariant checks:
1. Bucket partition sum must equal selected count.
2. Missing-`p_gf` tuple count must equal missing bucket count.

#### 2.4.7 Missing `p_gf` inference audit

For missing `p_gf` selected rows, compute:
1. `inference_counts == 0`, `!=0`, `NULL`
2. `inference_sources == 0`, `!=0`, `NULL`
3. both-zero count
4. whether all missing rows have both-zero (or `None` when no missing rows)

#### 2.4.8 Metadata payload assembly

Returns structured dictionary with:
1. identity and scope:
- detour_id, mode, mode_description, db_file, tables_used
2. counts block
3. rule_counts block
4. pgf_distribution block
5. pgf_outliers_tukey block
6. pgf_buckets block
7. missing_pgf_inference_audit block

### 2.5 `_print_summary(metadata)` full output sequence

1. Print detour header, DB path, mode description, tables used.
2. Render and print `Selection Counts` table.
3. Render and print `Mode-3 Rule Counts` table.
4. Render and print `p_gf Distribution` table.
5. Render and print `p_gf Buckets` table.
6. Render and print `Missing p_gf Inference Audit` table.
7. Render and print `Outliers (Tukey 1.5*IQR)` table.

### 2.6 Failure and teardown behavior

Failure path:
1. Any exception in metadata build or summary print logs red failure line.
2. Exception re-raised to module entrypoint.

Teardown path (always):
1. Stop monitor.
2. Close read-only connection if opened.
3. Print execution metrics with peak RAM.

### 2.7 Strict function invocation ledger (called functions only)

#### 2.7.1 Entrypoint call tree

`src.detours.detour_mode3_pgf_stats.main()` invokes:
1. `argparse.ArgumentParser(...)`
2. `parser.add_argument("--config", ...)`
3. `parser.parse_args()`
4. `PipelineConfig.from_json(args.config)`
5. `run_detour(config)`
6. if failure result: `RuntimeError(...)`
7. interrupt handling: `sys.exit(130)`

#### 2.7.2 Runtime call tree

`run_detour(config, interactive=True, diagnostics=None)` invokes:
1. `ResourceMonitor()`
2. `monitor.start()`
3. `duckdb.connect(str(config.db_file), read_only=True)`
4. `_build_mode3_pgf_metadata(conn)`
5. `_print_summary(metadata)`
6. `DetourResult(...)`
7. failure branch: `console.print(...)` red error line
8. finally:
- `monitor.stop()`
- `conn.close()` (if opened)
9. metrics rendering:
- `Table(...)`, `add_column(...)`, `add_row(...)`, `console.print(...)`
10. return `DetourResult`

#### 2.7.3 Metadata builder call tree

`_build_mode3_pgf_metadata(conn)` invokes:
1. `_scalar_int(conn, ...)` for population row count
2. `conn.execute(...).fetchall()` for `outerdict_stub` keys
3. `conn.execute(...).fetchall()` for `xlsx_innerdicts`
4. `loads_jsonlines(...)` to parse JSONL payload blobs
5. `inner.get(KTP_XLSX_MATCH_COL)` per parsed record
6. `conn.execute(...).fetchall()` for `ssn_innerdicts`
7. `_has_present_xlsx_match_payload(...)` in mode-3 xlsx rule
8. `_is_exact_xlsx_match_payload(...)` in mode-3 xlsx rule
9. numpy/math statistics stack:
- `np.array(...)`
- `non_missing_values.mean()/std()/min()/max()`
- `np.quantile(...)`
- `math.sqrt(...)`
- `np.sum(...)`
10. local `_eq_count(...)` for exact-value bucket counts
11. `_db_file_from_pragma(conn)`
12. repeated `_pct(...)` for all percentages in metadata blocks

`_scalar_int(...)` invokes:
1. `conn.execute(sql).fetchone()`
2. raises `RuntimeError(...)` when row missing

`_db_file_from_pragma(...)` invokes:
1. `conn.execute("PRAGMA database_list").fetchone()`

`_has_present_xlsx_match_payload(...)` invokes:
1. `value.strip()` for strings
2. `pd.isna(value)` for non-strings

`_is_exact_xlsx_match_payload(...)` invokes:
1. `json.loads(raw)`
2. payload field extraction `.get(...)`
3. normalization via `str(...).strip()`
4. sorted token-set comparisons

#### 2.7.4 Summary renderer call tree

`_print_summary(metadata)` invokes:
1. `console.print(...)` header lines
2. Rich table construction/printing for each section:
- `Selection Counts`
- `Mode-3 Rule Counts`
- `p_gf Distribution`
- `p_gf Buckets`
- `Missing p_gf Inference Audit`
- `Outliers (Tukey 1.5*IQR)`

#### 2.7.5 Defined but not invoked on detour runtime path

1. `_round_or_none(...)` is defined in this module but is not called by `main()` / `run_detour()` / `_build_mode3_pgf_metadata()` / `_print_summary()` in current code.

---

## Source files walked end-to-end for this RFC
- `src/repl.py`
- `src/helpers/init.py`
- `src/helpers/repl_runtime.py`
- `src/helpers/config.py`
- `src/helpers/pipeline_manager.py`
- `src/helpers/diagnostics.py`
- `src/helpers/resources.py`
- `src/steps/__init__.py`
- `src/steps/shared.py`
- `src/steps/step_01_register_resources.py`
- `src/steps/step_02_load_xlsx.py`
- `src/steps/step_03_infer_names.py`
- `src/steps/step_04_add_economy_priority.py`
- `src/steps/step_05_sampling.py`
- `src/steps/step_06_build_outerdict_stub.py`
- `src/steps/step_07_match_xlsx.py`
- `src/steps/step_08_match_docx.py`
- `src/steps/step_09_match_parquet.py`
- `src/steps/step_10_build_cards.py`
- `src/detours/detour_mode3_pgf_stats.py`
