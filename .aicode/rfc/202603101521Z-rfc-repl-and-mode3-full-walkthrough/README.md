# RFC: Full End-to-End Walkthrough for REPL and Mode-3 `p_gf` Detour

## Human notes

> [!NOTE]
> This RFC concerns the `--new` pathway only.

> [!WARNING]
> For AI: **don't touch** this section, ever.

After source code review for the `--new` pathway, I can see that the code base is clean and logical. The reason why I ignored the `--resume` pathway here is because it is not supposed to be a reference execution but rather is supported to facilitate repeated reruns during testing. And so because the purpose of this RFC is to design the exposure of critical code logic junctions to the team for review, the resume pathway can basically be considered scaffolding.

So, what happens in `repl.py`, on a high level, is that it orchestrates running of `run()` functions from each step, sequentially, as defined neatly under [src/steps/\_\_init\_\_.py](/src/steps/__init__.py). Each run function takes a `PipelineContext` object as its argument and returns a `StepResult` object as its output. Very clean. After getting all the step results, `repl.py` basically just prints the diagnostics, wraps up and exists. Therefore, because this scaffolding is a thin wrapper, we can jump directly into the `run()` functions of each step and scrutinize what’s going on there. Ideally we would hand off for review either the full `run()` functions or isolate the specific parts thereof and reimport later.

As for detours, their structure is of course designed to vary depending on the kind of the detour, so there is no general guidance here. However, speaking specifically of `detour_mode3_pgf_stats.py`, I confirm that all it does is just open a pre-created p_gf-focused database, **read-only**, and run some stats on this. The p_gf-focused database is created from running REPL with [config_p_gf.json](/config_p_gf.json) config, which only differs from the main config in that it uses [mode 3](/src/helpers/vars.py#L153) and adds another, `n=59355` batch (sampled without replacement), therefore exhausing the entire HCR dataset (across all XLSX files from 2014 to 2024 inclusive). Therefore, handing off this detour for review is pretty straightforward – we just need to hand off the function that does all the database stats, and, well, of course we would need a suitable lighter database fixture because the actual database is ~4.5 GB. Alternatively, though, it may not be a big deal to share the actual database; however, this sort of ruins the posterity between REPL and the detour. It therefore may be better to come up with a nice way to minify datasets, create a new `config_min.json` and `config_p_gf_min.json`, for example, and run the default REPL on that.

Signed-off: Pavel

## AI-generated content

**Timestamp (UTC):** 2026-03-10 15:21Z  \
**Author:** GPT-5 Codex (OpenAI)

## 1) FULL end-to-end REPL walkthrough (atomic invocation + SQL walkthrough)
1. [scaffolding] `src.repl.main()` starts and creates `argparse.ArgumentParser(description="KTP pipeline runner.")`.
2. [scaffolding] `main()` registers CLI arguments: `--config`, mutually-exclusive `--new`/`--resume(--continue)`, optional `--yes`, `--non-interactive`, `--quiet`.
3. [scaffolding] `main()` invokes `parser.parse_args()`.
4. [scaffolding] `main()` invokes `run_reproduction(args)` inside `try`.
5. [scaffolding] If Ctrl+C occurs, `main()` invokes `console.print("Process Interrupted")` and `sys.exit(130)`.
6. [scaffolding] If any other exception escapes, `main()` invokes `console.print_exception()` and `sys.exit(1)`.
7. [scaffolding] `run_reproduction(args)` computes runtime switches: `interactive = not args.non_interactive`, `auto_confirm = bool(args.yes)`.
8. [scaffolding] If `args.new` and `args.yes`, `reset_confirmed = True`.
9. [scaffolding] If `args.new` and interactive without `--yes`, `run_reproduction()` invokes `console.input("Reset pipeline state and database? [y/N]")` and sets `reset_confirmed` only when input is `y`.
10. [scaffolding] If `args.new` and non-interactive without `--yes`, `reset_confirmed` remains `False`.
11. [scaffolding] `run_reproduction()` invokes `init_pipeline(args, interactive=interactive, reset_confirmed=reset_confirmed)`.
12. [scaffolding] `init_pipeline()` validates `args.config`; if missing, raises `ValueError("A JSON config file is required...")`.
13. [scaffolding] `init_pipeline()` invokes `PipelineConfig.from_json(Path(args.config))`.
14. [scaffolding] `PipelineConfig.from_json()` invokes `model_validate_json(...)` and enforces schema/validators.
15. [scaffolding] Config validation enforces required `files_config` keys, required file-entry fields (`path`, `sha256`, `desc`), at least one key with `hcr_xlsx_` prefix, and normalizes integer `sample_draw_sizes` to dict specs.
16. [scaffolding] `init_pipeline()` constructs `PipelineManager(config.state_file, config.db_file)`.
17. [scaffolding] `PipelineManager.__init__()` invokes `_load_state()`; if no state file, uses default `{"steps_completed": [], "session_dir": None}`.
18. [scaffolding] `init_pipeline()` invokes `manager.connect_db()`.
19. [scaffolding] `connect_db()` invokes `duckdb.connect(str(self.db_file))`.
20. [scaffolding] `connect_db()` executes SQL: `SET memory_limit='20GB'`.
21. [scaffolding] `connect_db()` executes SQL: `INSTALL splink_udfs FROM community; LOAD splink_udfs;`.
22. [scaffolding] `init_pipeline()` constructs `ResourceMonitor()` and invokes `monitor.start()`.
23. [scaffolding] If `args.new` and `reset_confirmed` is false, `init_pipeline()` raises `ValueError("Pipeline reset confirmation required for --new.")`.
24. [scaffolding] If `args.new` and confirmed, `init_pipeline()` invokes `_reset_pipeline(conn, manager)`.
25. [scaffolding] `_reset_pipeline()` executes SQL `DROP TABLE IF EXISTS ...` for canonical pipeline tables (`registered_resources`, `population`, `population_names`, `population_economy`, `samples`, `outerdict_stub`, `xlsx_innerdicts`, `docx_rows`, `docx_innerdicts`, `ssn_author_matches`, `ssn_innerdicts`).
26. [scaffolding] `_reset_pipeline()` executes SQL `DROP VIEW IF EXISTS ...` for canonical views (`population_with_names`, `population_with_names_economy`, `samples_with_context`, `samples_with_names`, `outerdict_name_keys`, `xlsx_matches`, `xlsx_output`, `docx_matches`, `docx_output`).
27. [scaffolding] `_reset_pipeline()` executes SQL against `information_schema.tables` to discover all objects with name like `ssn_%` and drops each by type (`BASE TABLE` => `DROP TABLE`, `VIEW` => `DROP VIEW`).
28. [scaffolding] `_reset_pipeline()` invokes `manager.reset_state()`; this clears in-memory state and unlinks state file if present.
29. [scaffolding] `init_pipeline()` sets `session_stamp`: for new runs, invokes `datetime.now().strftime("%Y%m%d_%H%M%S")` and `manager.set_session_dir(session_stamp)`.
30. [scaffolding] `manager.set_session_dir(...)` writes JSON state file (ensuring parent dir exists).
31. [scaffolding] `init_pipeline()` constructs `DiagnosticsReport(Path("data/diagnostics") / session_stamp)`.
32. [scaffolding] `DiagnosticsReport` ensures diagnostics directory exists and creates `repl_diagnostics.md` with header if missing.
33. [scaffolding] For a fresh `--new` run, `init_pipeline()` sets `steps_to_run = STEP_ORDER`.
34. [scaffolding] For this fresh-run path, `manager.is_done(STEP_REGISTER_RESOURCES)` and `manager.is_done(STEP_BUILD_OUTERDICT)` evaluate false, so the state-hydration branches are skipped.
35. [scaffolding] `init_pipeline()` constructs and returns `InitResult(context=PipelineContext(...), steps_to_run=..., monitor=...)`.
36. [scaffolding] If any init exception occurs, `init_pipeline()` invokes `monitor.stop()`, `manager.close()`, then re-raises.
37. [scaffolding] Back in `run_reproduction()`, it stores `context`, `steps_to_run`, and `monitor` from `init_result`.
38. [scaffolding] `run_reproduction()` computes session log path: `context.diagnostics.path.parent / "repl_session.log"`.
39. [scaffolding] If new run with confirmed reset and old session log exists, it invokes `session_log_path.unlink()`.
40. [scaffolding] `run_reproduction()` defines closure `log(msg, style)` that appends to session log file, appends to in-memory history, and prints via Rich.
41. [scaffolding] `run_reproduction()` sets `context.log = log` so step modules can emit runtime logs.
42. [scaffolding] `run_reproduction()` enters loop `for step_id in steps_to_run:`.
43. [scaffolding] Per iteration, it invokes `STEP_REGISTRY.get(step_id)`.
44. [scaffolding] If `step_fn is None`, raises `ValueError("Unknown step: ...")`.
45. [scaffolding] It invokes `run_step(step_id, step_fn, context, log=log, verbose=not args.quiet)`.
46. [scaffolding] `run_step()` checks `context.manager.is_done(step_id)`; if true, returns `StepResult(messages=["Skipped ..."])`.
47. [scaffolding] Otherwise `run_step()` invokes `log("Running step: ...", "cyan")`.
48. [scaffolding] `run_step()` executes SQL `BEGIN`.
49. [scaffolding] `run_step()` invokes the step function `step_fn(context)`.
50. [scaffolding] On step success, `run_step()` executes SQL `COMMIT` and invokes `context.manager.save_state(step_id)`.
51. [scaffolding] On step failure, `run_step()` executes SQL `ROLLBACK`, invokes `context.diagnostics.add_section(f"{step_id} (failed)", [error])`, then re-raises.
52. [scaffolding] If verbose and step diagnostics/messages exist, `run_step()` invokes `context.diagnostics.add_section(step_id, ...)`.
53. [scaffolding] `run_step()` invokes `dump_artifacts(context, step_id, result.artifacts)`.
54. [scaffolding] `dump_artifacts()` ensures artifacts dir exists with `mkdir(parents=True, exist_ok=True)`.
55. [scaffolding] If artifacts include parquet view names/dfs lists, it writes each DataFrame with `to_csv(...)` named `<step_id>_<view_name>.csv`.
56. [scaffolding] For any direct DataFrame artifact it writes `<step_id>_<artifact>.csv`.
57. [scaffolding] For list-of-DataFrame artifacts, writes `<step_id>_<artifact>_<idx>.csv`.
58. [scaffolding] For `OuterDict` artifact, invokes `dump_json(...)` to write `<step_id>_<artifact>.json`.
59. [scaffolding] For `Path` artifact, records path directly as dumped artifact.
60. [scaffolding] `run_step()` appends artifact summary lines to `result.messages` and returns.
61. [scaffolding] Back in loop, `run_reproduction()` invokes `log(line, style="green")` for every returned message line.
62. [scaffolding] If `step_id == STEP_BUILD_CARDS`, it reads `result.artifacts.get("zip_path")` and `result.artifacts.get("cards")`, storing `zip_path` and `card_count`.
63. [scaffolding] If interactive and no `--yes`, it prompts `Continue to next step? [y/N]`; non-`y` breaks loop.
64. [scaffolding] If any exception escapes loop, `run_reproduction()` invokes `log("Exited prematurely: ...", style="red")` and re-raises.
65. [scaffolding] `run_reproduction()` always enters `finally`: invokes `monitor.stop()` if monitor exists; then invokes `context.manager.close()` if context exists.
66. [scaffolding] After loop completion, `run_reproduction()` builds a Rich metrics table and prints peak RAM (and cards count if known).
67. [scaffolding] It invokes `log("Execution Metrics", ...)`, `log("Peak RAM Usage: ...")`, optional `log("Cards: ...")`, and `log("Diagnostics report saved to: ...")`.
68. [scaffolding] If `zip_path` exists, invokes `log("Success! Output saved to: ...")`.
69. [scaffolding] `run_reproduction()` returns `zip_path` (or `None` if not produced).
70. [scaffolding] Loop step invocation order is always `STEP_ORDER` when `--new`: `01_register_resources`, `02_load_xlsx`, `03_infer_names`, `04_add_economy_priority`, `05_sample_population`, `06_build_outerdict`, `07_match_xlsx`, `08_match_docx`, `09_match_parquet`, `10_build_cards`.
71. [scaffolding] Step `01_register_resources.run(context)` starts by invoking `configured_hcr_xlsx_paths(context.config)`.
72. [scaffolding] It invokes `discover_docx_files(context.config.docx_dir)`.
73. [logic-io] It invokes `register_pipeline_resources(context.config)` and stores in `context.resources`. Rationale: This is external input I/O because configured source files are rehydrated into validated runtime resource objects.
74. [logic-transform] It invokes internal `_resource_registry_frame(resources)` to assemble a pandas frame of resource metadata. Rationale: This is logic-transform because registered resource objects are transformed into a tabular metadata relation consumed by downstream joins.
75. [logic-transform] It invokes `register_frame(context.conn, "registered_resources_frame", resources_df)`. Rationale: This is logic-transform because transformed resource metadata are materialized into DuckDB for subsequent SQL logic.
76. [logic-transform] `register_frame()` invokes `conn.register(name, df)`, SQL `CREATE OR REPLACE TABLE <name> AS SELECT * FROM <name>`, then `conn.unregister(name)` best-effort. Rationale: This is logic-transform because in-memory tabular metadata are persisted as a concrete relation.
77. [logic-transform] Step 01 executes SQL: `CREATE OR REPLACE TABLE registered_resources AS SELECT * FROM registered_resources_frame`. Rationale: This is logic-transform because the canonical resource registry table is materialized and becomes a data source for later transformations.
78. [scaffolding] Step 01 executes SQL: `DROP TABLE IF EXISTS registered_resources_frame`.
79. [scaffolding] Step 01 returns `StepResult` with message counts and artifact paths for discovered xlsx/docx files.
80. [scaffolding] Step `02_load_xlsx.run(context)` invokes `_build_population_table(conn, context.resources.xlsx_resources, table_name=population, ...)`.
81. [scaffolding] `_build_population_table()` loops through XLSX resources, invoking `Path(resource.__fspath__())` per resource.
82. [logic-transform] It skips non-`.xlsx` and temporary `~$` files. Rationale: This is logic-transform because source-row inclusion is filtered at intake, which changes which records enter downstream transformations.
83. [logic-io] It invokes `pd.read_excel(path, engine="openpyxl")`. Rationale: This is external input I/O because source XLSX rows are parsed into in-memory tabular data that seed downstream processing.
84. [logic-transform] It invokes `_normalize_hcr_header(...)` for each input column and prepends `hcr.` naming. Rationale: This is logic-transform because values are canonicalized, which changes matching and grouping behavior downstream.
85. [logic-transform] It adds row/index columns: `hcr.row_number = reset_index + 2`, `hcr.filename`, and global `ktp.population_index` sequence. Rationale: This is logic-transform because it changes data content, structure, selection, or ordering used by downstream steps.
86. [logic-transform] It coerces non-index columns to `string` dtype. Rationale: This is logic-transform because it changes data content, structure, selection, or ordering used by downstream steps.
87. [scaffolding] It executes SQL existence check: `SELECT COUNT(*) FROM information_schema.tables WHERE table_name = ?`.
88. [scaffolding] If table exists, it executes SQL `PRAGMA table_info('population')` and computes schema diff.
89. [logic-transform] For new columns it executes SQL `ALTER TABLE population ADD COLUMN "<col>" <type>`. Rationale: This is logic-transform because it changes data content, structure, selection, or ordering used by downstream steps.
90. [logic-transform] It pads missing columns in DataFrame with `pd.NA`, reorders to table schema, invokes `register_frame(conn, "population_frame", df)`, then SQL `INSERT INTO population SELECT * FROM population_frame`. Rationale: This is logic-transform because in-memory transformed data are staged into DuckDB relations for further transformation steps.
91. [logic-transform] If table does not exist, it invokes `register_frame(conn, "population", df)` which materializes `population` directly. Rationale: This is logic-transform because in-memory transformed data are staged into DuckDB relations for further transformation steps.
92. [scaffolding] Back in step 02, it executes SQL `SELECT * FROM population` to load artifact DataFrame and returns row/column counts.
93. [scaffolding] Step `03_infer_names.run(context)` verifies resources exist; if `HCR_XLSX_NAME_COLS` is empty, it infers mappings per XLSX via `_infer_name_columns_from_xlsx(...)`.
94. [logic-io] `_infer_name_columns_from_xlsx()` invokes `pd.read_excel(...)`, normalizes headers, then helper `pick(...)` to find first/last columns by candidate tokens. Rationale: This is external input I/O because source XLSX rows are parsed into in-memory tabular data that seed downstream processing.
95. [logic-transform] Step 03 validates every configured XLSX has mapping; missing mappings raise `ValueError`. Rationale: This is logic-transform because validation gates the transformation path by enforcing that required mapping state is complete.
96. [logic-transform] Step 03 invokes `_build_name_expr(HCR_XLSX_NAME_COLS, 0)` and `_build_name_expr(..., 1)` to build filename-conditioned CASE expressions. Rationale: This is logic-transform because it changes data content, structure, selection, or ordering used by downstream steps.
97. [logic-transform] Step 03 executes SQL: `CREATE OR REPLACE TABLE population_names AS SELECT p.ktp.population_index, <first_case> AS ktp.first_name, <last_case> AS ktp.last_name FROM population p`. Rationale: This is logic-transform because SQL materializes a derived relation that changes data shape/content via selection, joins, or aggregation.
98. [logic-transform] Step 03 executes SQL: `CREATE OR REPLACE VIEW population_with_names AS SELECT p.*, n.ktp.first_name, n.ktp.last_name FROM population p JOIN population_names n ON p.ktp.population_index = n.ktp.population_index`. Rationale: This is logic-transform because SQL materializes a derived relation that changes data shape/content via selection, joins, or aggregation.
99. [scaffolding] Step 03 executes SQL `SELECT * FROM population_with_names` and returns artifact.
100. [scaffolding] Step `04_add_economy_priority.run(context)` invokes `_load_income_labels(context.resources.world_bank_resource)`.
101. [logic-io] `_load_income_labels()` invokes `pd.read_excel(sheet_name="Country Analytical History", header=None)`. Rationale: This is external input I/O because source XLSX rows are parsed into in-memory tabular data that seed downstream processing.
102. [logic-transform] It scans rows for an `FY##` token, picks the last FY column, then builds canonical country-to-income map and alias-expanded match rows using `KTP_COUNTRY_ALIASES`. Rationale: This is logic-transform because it changes data content, structure, selection, or ordering used by downstream steps.
103. [logic-transform] Step 04 builds DataFrame from income rows and invokes `register_frame(conn, "income_map_frame", ...)`. Rationale: This is logic-transform because in-memory transformed data are staged into DuckDB relations for further transformation steps.
104. [logic-transform] Step 04 executes SQL: `CREATE OR REPLACE TABLE income_map AS SELECT * FROM income_map_frame`. Rationale: This is logic-transform because SQL materializes a derived relation that changes data shape/content via selection, joins, or aggregation.
105. [scaffolding] Step 04 executes SQL: `DROP TABLE IF EXISTS income_map_frame`.
106. [scaffolding] Step 04 executes SQL `DESCRIBE population` to infer affiliation columns.
107. [logic-transform] It invokes `_infer_affiliation_columns(...)` for primary and secondary defaults. Rationale: This is logic-transform because it changes data content, structure, selection, or ordering used by downstream steps.
108. [logic-transform] It invokes `_normalize_affiliation_map(HCR_XLSX_AFFILIATIONS_COLS, index=0/1)`. Rationale: This is logic-transform because values are canonicalized, which changes matching and grouping behavior downstream.
109. [logic-transform] It invokes `_affiliation_case(...)` twice to produce filename-aware primary/secondary affiliation SQL expressions. Rationale: This is logic-transform because it changes data content, structure, selection, or ordering used by downstream steps.
110. [logic-transform] It computes country buckets using `_non_english_non_eu_hics(...)`, local `_countries_for(...)`, and local `_sql_in_list(...)`. Rationale: This is logic-transform because new derived flags, scores, or summary statistics are computed from existing data.
111. [logic-transform] Step 04 executes core SQL to create `population_economy` with CTEs `aff` and `matches`. Rationale: This is logic-transform because it changes data content, structure, selection, or ordering used by downstream steps.
112. [logic-transform] Inside that SQL it invokes key operations: `regexp_replace(lower(unaccent(...)))`, token-space containment match `(' ' || aff_tokens || ' ') LIKE '% ' || m.match_norm || ' %'`, aggregated JSON economies via `to_json(list_sort(list(DISTINCT m.country) FILTER ...))`, income-group priority CASE logic, and priority-group label CASE logic. Rationale: This is logic-transform because it changes data content, structure, selection, or ordering used by downstream steps.
113. [logic-transform] Step 04 executes SQL: `CREATE OR REPLACE VIEW population_with_names_economy AS SELECT p.*, n.*, e.<economy fields> FROM population p JOIN population_names n ... JOIN population_economy e ...`. Rationale: This is logic-transform because SQL materializes a derived relation that changes data shape/content via selection, joins, or aggregation.
114. [scaffolding] Step 04 executes SQL `DESCRIBE population_with_names_economy` then SQL `SELECT <ordered_cols> FROM population_with_names_economy` and returns artifact.
115. [scaffolding] Step `05_sampling.run(context)` validates arithmetic: `sum(sample_draw_sizes) == total_draws - pilot_count`; else raises `ValueError`.
116. [logic-transform] It executes SQL `SELECT ktp.population_index FROM population` and creates numpy `index_pool`. Rationale: This is logic-transform because it changes data content, structure, selection, or ordering used by downstream steps.
117. [logic-transform] It creates `pilot_triples` DataFrame from `PILOT_NAME_CATEGORY_TRIPLES`, invokes `register_frame(conn, "pilot_triples", ...)`. Rationale: This is logic-transform because in-memory transformed data are staged into DuckDB relations for further transformation steps.
118. [logic-transform] It executes SQL to fetch pilot exclusion indices by joining `population` to `pilot_triples` on first/last/category and filtering `hcr.filename = pilot_xlsx_name`. Rationale: This is logic-transform because it changes data content, structure, selection, or ordering used by downstream steps.
119. [logic-transform] It invokes `np.random.default_rng(context.config.sample_seed)`. Rationale: This is logic-transform because it changes data content, structure, selection, or ordering used by downstream steps.
120. [logic-transform] It invokes `_precompute_draw_batches(index_pool, draw_specs, rng, seen_indices_initial=pilot_population_indices)`. Rationale: This is logic-transform because sampling rules actively determine which population rows are selected for analysis.
121. [logic-transform] `_precompute_draw_batches()` iterates each draw spec; with `replace=True` invokes `rng.choice(index_pool, size=draw_size, replace=True)`; with `replace=False` computes remaining pool excluding seen indices and validates capacity. Rationale: This is logic-transform because sampling rules actively determine which population rows are selected for analysis.
122. [logic-transform] For each precomputed draw, step 05 creates `sample_indices` DataFrame and invokes `register_frame(conn, "sample_indices", ...)`. Rationale: This is logic-transform because in-memory transformed data are staged into DuckDB relations for further transformation steps.
123. [logic-transform] For each draw, step 05 executes SQL joining `population` to `sample_indices` to get filename+fragment rows ordered by `sample_id`. Rationale: This is logic-transform because it changes data content, structure, selection, or ordering used by downstream steps.
124. [logic-transform] It labels draw numbers and invokes `_append_samples(conn, sample_df[[ktp.filename, ktp.fragment, ktp.draw_number]])`. Rationale: This is logic-transform because it changes data content, structure, selection, or ordering used by downstream steps.
125. [logic-transform] `_append_samples()` invokes `register_frame(conn, "samples_frame", df)`, checks table existence via SQL on `information_schema.tables`, then either SQL `INSERT INTO samples SELECT ... FROM samples_frame` or SQL `CREATE TABLE samples AS SELECT ... FROM samples_frame`, and drops temp table. Rationale: This is logic-transform because in-memory transformed data are staged into DuckDB relations for further transformation steps.
126. [logic-transform] Step 05 executes SQL query for pilot rows joined with `pilot_triples`, enforces expected pilot count, orders by configured tuple order, sets labels `pilot.1...`, and invokes `_append_samples(...)`. Rationale: This is logic-transform because it changes data content, structure, selection, or ordering used by downstream steps.
127. [logic-transform] Step 05 executes SQL to create `samples_with_context` view using joins to `population`, `population_names`, and `population_economy` with draw-order CASE sorting. Rationale: This is logic-transform because it changes data content, structure, selection, or ordering used by downstream steps.
128. [logic-transform] Step 05 executes SQL to create `samples_with_names` view as reduced join. Rationale: This is logic-transform because it changes data content, structure, selection, or ordering used by downstream steps.
129. [scaffolding] Step 05 executes SQL drops: `DROP TABLE IF EXISTS sample_indices`, `DROP TABLE IF EXISTS pilot_triples`.
130. [scaffolding] Step 05 executes SQL `SELECT * FROM samples_with_context` and returns artifact.
131. [logic-transform] Step `06_build_outerdict_stub.run(context)` executes SQL selecting excluded-name rows from `samples_with_names` where first/last is null/empty, with deterministic draw/file sort ordering. Rationale: This is logic-transform because it changes data content, structure, selection, or ordering used by downstream steps.
132. [scaffolding] It logs excluded-row diagnostics and preview lines.
133. [logic-transform] It builds excluded key JSON strings via local `_name_key_json(...)` and invokes `register_frame(conn, "outerdict_excluded_stub_frame", ...)`. Rationale: This is logic-transform because in-memory transformed data are staged into DuckDB relations for further transformation steps.
134. [logic-transform] It executes SQL: `CREATE OR REPLACE TABLE outerdict_stub_excluded AS SELECT * FROM outerdict_excluded_stub_frame`. Rationale: This is logic-transform because SQL materializes a derived relation that changes data shape/content via selection, joins, or aggregation.
135. [scaffolding] It executes SQL: `DROP TABLE IF EXISTS outerdict_excluded_stub_frame`.
136. [logic-transform] It executes SQL: `CREATE OR REPLACE VIEW outerdict_name_keys_excluded AS SELECT name_key AS ktp.source_key, json_extract_string(...) AS ktp.first_name, json_extract_string(...) AS ktp.last_name FROM outerdict_stub_excluded`. Rationale: This is logic-transform because SQL materializes a derived relation that changes data shape/content via selection, joins, or aggregation.
137. [logic-transform] It executes SQL: `SELECT DISTINCT ktp.first_name, ktp.last_name FROM samples_with_names`; then pandas-side filtering drops null/empty pairs before key construction. Rationale: This is logic-transform because it changes data content, structure, selection, or ordering used by downstream steps.
138. [logic-transform] It constructs `NameKey(...)` objects and invokes `OuterDict.from_name_keys(name_keys)`; assigns to `context.outer_dict`; it also constructs `outer_dict_excluded = OuterDict(data={name_key_json: [] ...})` for excluded null/empty-name keys. Rationale: This is logic-transform because raw key fields are converted into structured key objects used for subsequent matching/grouping.
139. [logic-transform] It builds active stub DataFrame and invokes `register_frame(conn, "outerdict_stub_frame", ...)`. Rationale: This is logic-transform because in-memory transformed data are staged into DuckDB relations for further transformation steps.
140. [logic-transform] It executes SQL: `CREATE OR REPLACE TABLE outerdict_stub AS SELECT * FROM outerdict_stub_frame`. Rationale: This is logic-transform because SQL materializes a derived relation that changes data shape/content via selection, joins, or aggregation.
141. [scaffolding] It executes SQL: `DROP TABLE IF EXISTS outerdict_stub_frame`.
142. [logic-transform] It executes SQL: `CREATE OR REPLACE VIEW outerdict_name_keys AS SELECT name_key AS ktp.source_key, json_extract_string(...) AS ktp.first_name, json_extract_string(...) AS ktp.last_name FROM outerdict_stub`. Rationale: This is logic-transform because SQL materializes a derived relation that changes data shape/content via selection, joins, or aggregation.
143. [scaffolding] Step `07_match_xlsx.run(context)` executes SQL `DESCRIBE population` and invokes `hcr_excluded_columns(...)` to decide payload columns.
144. [logic-transform] It invokes `draw_sort_ctes_sql(draw_col=ktp.draw_number, source_key_col=ktp.source_key)` and `draw_sort_order_by_sql(...)` to embed deterministic sort CTE SQL. Rationale: This is logic-transform because these helpers inject CASE/ranking expressions that deterministically reorder matched rows before grouping and output materialization.
145. [logic-transform] Step 07 executes SQL `CREATE OR REPLACE VIEW xlsx_matches AS WITH name_draws, pop_names, base, row_ranked, ranked ...`. Rationale: This is logic-transform because SQL materializes a derived relation that changes data shape/content via selection, joins, or aggregation.
146. [logic-transform] In `name_draws`, SQL computes normalized source-key tokens with `lower(unaccent(...))`, `regexp_split_to_array`, and first token extraction via `list_extract`. Rationale: This is logic-transform because values are canonicalized, which changes matching and grouping behavior downstream.
147. [logic-transform] In `pop_names`, SQL joins `population` + `population_names` + left joins `population_economy` and `registered_resources`, while deriving normalized token arrays for population names. Rationale: This is logic-transform because values are canonicalized, which changes matching and grouping behavior downstream.
148. [logic-transform] In `base`, SQL joins `name_draws` to `pop_names` with key conditions `nd.nd_last_clean = p.pop_last_clean` and `list_contains(p.pop_first_tokens, nd.nd_first_token)`. Rationale: This is logic-transform because it changes data content, structure, selection, or ordering used by downstream steps.
149. [logic-transform] In `base`, SQL emits structured JSON `ktp.xlsx_match` using `json_object(...)` including source-key token list and matched-pop token list. Rationale: This is logic-transform because records are re-encoded into structured payloads consumed by downstream matching and card generation.
150. [logic-transform] Step 07 executes SQL `SELECT * FROM xlsx_matches` to pandas, filters non-null filename rows, groups by `ktp.source_key`, serializes grouped records via `dumps_jsonlines(...)`. Rationale: This is logic-transform because records are re-encoded into structured payloads consumed by downstream matching and card generation.
151. [logic-transform] Step 07 invokes `register_frame(conn, "xlsx_innerdict_frame", inner_df)`. Rationale: This is logic-transform because in-memory transformed data are staged into DuckDB relations for further transformation steps.
152. [logic-transform] It executes SQL: `CREATE OR REPLACE TABLE xlsx_innerdicts AS SELECT * FROM xlsx_innerdict_frame`. Rationale: This is logic-transform because SQL materializes a derived relation that changes data shape/content via selection, joins, or aggregation.
153. [scaffolding] It executes SQL: `DROP TABLE IF EXISTS xlsx_innerdict_frame`.
154. [logic-transform] It invokes `append_innerdicts_from_jsonlines_table(conn, table_name=xlsx_innerdicts, outer_dict=context.outer_dict, procedure=XlsxMatchProcedure(), required_columns={ktp.filename, ktp.fragment})`. Rationale: This is logic-transform because matched records are rehydrated and attached to per-name objects that drive downstream logic.
155. [logic-transform] It executes SQL: `CREATE OR REPLACE VIEW xlsx_output AS WITH base AS (SELECT * FROM xlsx_matches WHERE ktp.filename IS NOT NULL), row_ranked, ranked SELECT ... ORDER BY ...`. Rationale: This is logic-transform because SQL materializes a derived relation that changes data shape/content via selection, joins, or aggregation.
156. [scaffolding] It executes SQL `SELECT * FROM xlsx_output` and returns artifact.
157. [scaffolding] Step `08_match_docx.run(context)` invokes `load_single_table_docx(context.resources.docx_resources)`.
158. [logic-io] `load_single_table_docx()` loops resources, skips `~$` files, invokes `parse_docx_tables_and_notes(path)`, enforces exactly one table, normalizes columns with `normalize_docx_column_name(...)`, adds `ktp.table_1_footnotes`, `ktp.table_1_comments`, `ktp.filename`, and `ktp.table_1_row_number`. Rationale: This is external input I/O because raw DOCX content is parsed from source files into structured rows.
159. [scaffolding] If parse mismatch occurs (bad zip, row-comment count mismatch, missing table), it raises descriptive `ValueError`.
160. [logic-transform] Step 08 invokes `register_frame(conn, "docx_frame", docx_df)`. Rationale: This is logic-transform because in-memory transformed data are staged into DuckDB relations for further transformation steps.
161. [logic-transform] Step 08 executes SQL: `CREATE OR REPLACE TABLE docx_rows AS SELECT * FROM docx_frame`. Rationale: This is logic-transform because SQL materializes a derived relation that changes data shape/content via selection, joins, or aggregation.
162. [scaffolding] Step 08 executes SQL: `DROP TABLE IF EXISTS docx_frame`.
163. [scaffolding] Step 08 invokes `normalize_docx_column_name(RIGHT_NAME_COL)` and validates that normalized column exists in loaded DOCX frame.
164. [logic-transform] Step 08 invokes `draw_sort_ctes_sql(...)` and `draw_sort_order_by_sql(...)`. Rationale: This is logic-transform because these helpers inject row ranking and source-level draw precedence SQL that changes output ordering and tie-resolution.
165. [logic-transform] Step 08 executes SQL: `CREATE OR REPLACE VIEW docx_matches AS WITH name_draws, names_clean, docx_clean, base, row_ranked, ranked ...`. Rationale: This is logic-transform because SQL materializes a derived relation that changes data shape/content via selection, joins, or aggregation.
166. [logic-transform] In `name_draws`, SQL left joins `outerdict_name_keys` to `samples_with_names` to attach draw labels. Rationale: This is logic-transform because it changes data content, structure, selection, or ordering used by downstream steps.
167. [logic-transform] In `names_clean`, SQL normalizes names with `regexp_replace(lower(unaccent(...)), '[^0-9a-z]+', '', 'g')`. Rationale: This is logic-transform because values are canonicalized, which changes matching and grouping behavior downstream.
168. [logic-transform] In `docx_clean`, SQL normalizes candidate docx name field similarly. Rationale: This is logic-transform because values are canonicalized, which changes matching and grouping behavior downstream.
169. [logic-transform] In `base`, SQL uses `RIGHT JOIN names_clean nd ON POSITION(nd.first_clean IN d.docx_clean) > 0 AND POSITION(nd.last_clean IN d.docx_clean) > 0`, then left joins `registered_resources`. Rationale: This is logic-transform because it changes data content, structure, selection, or ordering used by downstream steps.
170. [logic-transform] Step 08 executes SQL `SELECT * FROM docx_matches`, drops `docx_clean` column if present, filters non-null filename rows, groups by key, serializes JSONL via `dumps_jsonlines(...)`. Rationale: This is logic-transform because records are re-encoded into structured payloads consumed by downstream matching and card generation.
171. [logic-transform] Step 08 invokes `register_frame(conn, "docx_innerdict_frame", inner_df)`. Rationale: This is logic-transform because in-memory transformed data are staged into DuckDB relations for further transformation steps.
172. [logic-transform] It executes SQL: `CREATE OR REPLACE TABLE docx_innerdicts AS SELECT * FROM docx_innerdict_frame`. Rationale: This is logic-transform because SQL materializes a derived relation that changes data shape/content via selection, joins, or aggregation.
173. [scaffolding] It executes SQL: `DROP TABLE IF EXISTS docx_innerdict_frame`.
174. [logic-transform] It invokes `append_innerdicts_from_jsonlines_table(conn, table_name=docx_innerdicts, outer_dict=context.outer_dict, procedure=DocxMatchProcedure(), required_columns={ktp.filename, ktp.fragment})`. Rationale: This is logic-transform because matched records are rehydrated and attached to per-name objects that drive downstream logic.
175. [logic-transform] It executes SQL: `CREATE OR REPLACE VIEW docx_output AS WITH base AS (SELECT * FROM docx_matches WHERE ktp.filename IS NOT NULL), row_ranked, ranked SELECT ... ORDER BY ...`. Rationale: This is logic-transform because SQL materializes a derived relation that changes data shape/content via selection, joins, or aggregation.
176. [scaffolding] It executes SQL `SELECT * FROM docx_output` and returns artifact.
177. [scaffolding] Step `09_match_parquet.run(context)` validates `context.outer_dict` and `context.resources` are present.
178. [scaffolding] Step 09 reads parquet file paths from `context.config.files_config` for `author_details`, `authors`, `authors_paper`, `paper_author_affiliation`, `affiliations`, `hit_papers_0`, `hit_papers_1`, and `fields`.
179. [scaffolding] Step 09 logs legend entries from `STEP_MATCH_PARQUET_LOG_LEGEND_LINES`.
180. [logic-io] Step 09 executes SQL: `CREATE OR REPLACE TABLE ssn_author_matches AS WITH names, parq AS (...) SELECT DISTINCT ... FROM names JOIN parq ON lower(unaccent(p.alt_name)) = n.match_key_norm`. Rationale: This is logic I/O because it performs a true external/persisted data intake step or a true end-user handoff output step.
181. [logic-io] `parq` CTE unions exploded `display_name_alternatives` and direct `display_name` rows from `read_parquet(author_details_path)`. Rationale: This is external input I/O because source parquet data are pulled into the active query path.
182. [scaffolding] Step 09 executes SQL aggregate stats query on `ssn_author_matches` for row/name/author counts.
183. [logic-io] Step 09 executes SQL: `CREATE OR REPLACE TABLE ssn_author_papers AS SELECT m.name_key, m."ssnad.authorid" AS authorid, pap.paperid FROM ssn_author_matches m JOIN read_parquet(authors_paper_path) pap ON pap.authorid = m."ssnad.authorid"`. Rationale: This is external input I/O because raw parquet records are read from source files into DuckDB tables for later transforms.
184. [scaffolding] Step 09 executes SQL stats query on `ssn_author_papers` for row/pair/paper counts.
185. [logic-io] Step 09 executes SQL: `CREATE OR REPLACE TABLE ssn_all_hits AS WITH needed_papers AS (SELECT DISTINCT paperid FROM ssn_author_papers) SELECT ... FROM read_parquet(hit_papers_0) JOIN needed_papers UNION ALL SELECT ... FROM read_parquet(hit_papers_1) JOIN needed_papers`. Rationale: This is external input I/O because raw parquet records are read from source files into DuckDB tables for later transforms.
186. [scaffolding] Step 09 executes SQL stats query on `ssn_all_hits`.
187. [logic-transform] Step 09 executes SQL: `CREATE OR REPLACE TABLE ssn_author_hit_agg AS SELECT ap.name_key, ap.authorid, SUM(COALESCE(h.hit_1pct,0)) AS "ktp.ssn_sum_hit_1pct" FROM ssn_author_papers ap LEFT JOIN ssn_all_hits h ON ap.paperid=h.paperid GROUP BY ap.name_key, ap.authorid`. Rationale: This is logic-transform because SQL materializes a derived relation that changes data shape/content via selection, joins, or aggregation.
188. [scaffolding] Step 09 executes SQL stats query on `ssn_author_hit_agg` (zero/nonzero/null counts).
189. [scaffolding] Step 09 executes SQL count query for zero-hit rows removed.
190. [logic-transform] Step 09 executes SQL: `CREATE OR REPLACE VIEW ssn_author_matches_nonzero_hit AS SELECT m.* FROM ssn_author_matches m LEFT JOIN ssn_author_hit_agg agg ON ... WHERE agg."ktp.ssn_sum_hit_1pct" IS NULL OR agg."ktp.ssn_sum_hit_1pct" <> 0`. Rationale: This is logic-transform because SQL materializes a derived relation that changes data shape/content via selection, joins, or aggregation.
191. [scaffolding] Step 09 executes SQL stats query on `ssn_author_matches_nonzero_hit`.
192. [logic-transform] Step 09 executes SQL: `CREATE OR REPLACE VIEW ssn_author_match_nonzero_hit_author_ids AS SELECT DISTINCT "ssnad.authorid" FROM ssn_author_matches_nonzero_hit`. Rationale: This is logic-transform because SQL materializes a derived relation that changes data shape/content via selection, joins, or aggregation.
193. [scaffolding] Step 09 executes SQL scalar count on that distinct-author-id view.
194. [logic-transform] Step 09 executes SQL: `CREATE OR REPLACE TABLE ssn_author_agg AS SELECT ap.name_key, ap.authorid, SUM(COALESCE(h.hit_1pct,0)) AS "ktp.ssn_sum_hit_1pct", LIST(ap.paperid) FILTER (WHERE h.level='level0') AS "ssn.paperids_level0", LIST(ap.paperid) FILTER (WHERE h.level='level1') AS "ssn.paperids_level1", LIST(DISTINCT h.fieldid) AS "ssn.field_ids_list" FROM ssn_author_papers ap LEFT JOIN ssn_all_hits h ... WHERE EXISTS (SELECT 1 FROM ssn_author_matches_nonzero_hit ...) GROUP BY ap.name_key, ap.authorid`. Rationale: This is logic-transform because SQL materializes a derived relation that changes data shape/content via selection, joins, or aggregation.
195. [scaffolding] Step 09 executes SQL scalar count on `ssn_author_agg`.
196. [logic-io] Step 09 invokes `_create_parquet_table(...)` for matched `author_details` table. Rationale: This is external input I/O because the helper materializes a matched subset by reading source parquet records.
197. [logic-io] `_create_parquet_table()` invokes `parquet_columns(conn, path)` (which runs `DESCRIBE SELECT * FROM read_parquet('<path>')`). Rationale: This is external input I/O because source parquet data are pulled into the active query path.
198. [logic-transform] `_create_parquet_table()` invokes `normalize_parquet_column_name(...)` for each parquet field. Rationale: This is logic-transform because values are canonicalized, which changes matching and grouping behavior downstream.
199. [logic-io] `_create_parquet_table()` invokes `parquet_filename(path)` and executes SQL `CREATE OR REPLACE TABLE <target> AS SELECT parq.<cols as normalized>, '<filename>' AS <filename_col> FROM read_parquet('<path>') parq <join_sql>`. Rationale: This is external input I/O because raw parquet records are read from source files into DuckDB tables for later transforms.
200. [logic-io] Step 09 repeats `_create_parquet_table(...)` for matched `authors` table (joined by distinct nonzero author ids). Rationale: This is external input I/O because source parquet rows are read to materialize the matched authors subset.
201. [logic-io] Step 09 repeats `_create_parquet_table(...)` for matched `paper_author_affiliation` table (joined by distinct nonzero author ids). Rationale: This is external input I/O because source parquet rows are read to materialize matched author-paper-affiliation links.
202. [logic-io] Step 09 repeats `_create_parquet_table(...)` for matched `affiliations` table (joined by distinct institution ids derived from matched paper-author-affiliation rows). Rationale: This is external input I/O because source parquet rows are read to materialize matched institution records.
203. [scaffolding] Step 09 executes SQL counts for each matched parquet-derived table.
204. [logic-transform] Step 09 executes SQL: `CREATE OR REPLACE TABLE ssn_author_output AS SELECT m.name_key AS ktp.source_key, ... a.*, au.*, CAST(agg."ssn.paperids_level0" AS VARCHAR), CAST(agg."ssn.paperids_level1" AS VARCHAR), CAST(agg."ssn.field_ids_list" AS VARCHAR), agg."ktp.ssn_sum_hit_1pct" FROM ssn_author_matches_nonzero_hit m JOIN <matched_author_details> a ... JOIN <matched_authors> au ... LEFT JOIN ssn_author_agg agg ...`. Rationale: This is logic-transform because SQL materializes a derived relation that changes data shape/content via selection, joins, or aggregation.
205. [scaffolding] Step 09 executes SQL scalar count on `ssn_author_output`.
206. [scaffolding] Step 09 executes SQL diagnostic query estimating top-works reduction (`SUM(paper_count)` vs `SUM(LEAST(paper_count, TOP_K_WORKS))`).
207. [scaffolding] Step 09 executes SQL diagnostic query estimating top-institutions reduction (`SUM(institution_count)` vs `SUM(LEAST(..., TOP_K_INSTITUTIONS))`).
208. [scaffolding] Step 09 executes SQL diagnostic query for field-id display-name mapping coverage by joining exploded field IDs to `read_parquet(fields_path)`.
209. [logic-io] Step 09 executes SQL: `CREATE OR REPLACE TABLE ssn_innerdicts AS WITH paper_hits, paper_ranked, top_papers, affiliation_counts, affiliation_ranked, top_institutions, field_lookup, concept_display, enriched, source_draw, base, row_ranked, ranked SELECT ...`. Rationale: This is external input I/O because this materialization reads field parquet input while building the enriched innerdict table.
210. [logic-transform] In this SQL, it ranks papers by hit score, builds top-K OpenAlex paper URLs, ranks institutions by paper count, builds top-K institution JSON objects, maps field IDs to display names, and reattaches draw ordering. Rationale: This is logic-transform because it changes data content, structure, selection, or ordering used by downstream steps.
211. [scaffolding] Step 09 executes SQL scalar count on `ssn_innerdicts`.
212. [logic-transform] Step 09 invokes `append_innerdicts_from_rows_table(conn, table_name=ssn_innerdicts, outer_dict=context.outer_dict, procedure=ParquetMatchProcedure(), key_column=ktp.source_key)`. Rationale: This is logic-transform because matched records are rehydrated and attached to per-name objects that drive downstream logic.
213. [logic-transform] Step 09 executes SQL: `CREATE OR REPLACE VIEW ssn_parquet_output AS WITH source_draw, base, row_ranked, ranked SELECT ... ORDER BY ...`. Rationale: This is logic-transform because SQL materializes a derived relation that changes data shape/content via selection, joins, or aggregation.
214. [scaffolding] Step 09 logs (non-SQL) the number of filtered zero-hit rows via `log_tag(...)`.
215. [scaffolding] Step 09 executes SQL `SELECT * FROM ssn_parquet_output` into pandas output frame and returns step artifact.
216. [scaffolding] Step `10_build_cards.run(context)` checks `context.outer_dict` exists; else raises `ValueError`.
217. [scaffolding] Step 10 reads `subset_mode = int(context.config.card_subset_mode)` and validates membership in `CARD_BUILD_SUBSET_DESCRIPTIONS`.
218. [scaffolding] Step 10 defines logging/progress closures and helper predicate closures used for subset filtering.
219. [logic-transform] `_extract_filenames(value)` parses filenames from scalar string/list/json-list payloads. Rationale: This is logic-transform because it changes data content, structure, selection, or ordering used by downstream steps.
220. [logic-transform] `_is_sciscinet_inner(inner, sciscinet_filenames)` checks if any filename fields intersect SciSciNet resource names. Rationale: This is logic-transform because it changes data content, structure, selection, or ordering used by downstream steps.
221. [logic-transform] `_is_exact_xlsx_match_payload(value)` treats `None`/blank/non-string payloads as non-failing in that helper path, and for non-blank strings parses JSON then enforces exact token/last-name equivalence. Rationale: This is logic-transform because it changes data content, structure, selection, or ordering used by downstream steps.
222. [logic-transform] `_has_present_xlsx_match_payload(value)` defines non-empty payload presence. Rationale: This is logic-transform because it changes data content, structure, selection, or ordering used by downstream steps.
223. [logic-transform] `_is_non_empty_value(value)` handles string emptiness/placeholder semantics for docx fields. Rationale: This is logic-transform because it changes data content, structure, selection, or ordering used by downstream steps.
224. [logic-transform] `_has_complete_docx_table_fields(inner)` requires non-empty required `ktp.table_1_*` fields (except optional-empty set). Rationale: This is logic-transform because it changes data content, structure, selection, or ordering used by downstream steps.
225. [logic-transform] `_filtered_outer_dict()` iterates every `(NameKey, innerdicts)` from `outer_dict.items()`. Rationale: This is logic-transform because it changes data content, structure, selection, or ordering used by downstream steps.
226. [logic-transform] For each name, it computes `sciscinet_exactly_one_ok`, `xlsx_exact_ok`, and `docx_complete_ok`. Rationale: This is logic-transform because new derived flags, scores, or summary statistics are computed from existing data.
227. [logic-transform] `_filtered_outer_dict()` applies `_mode_matches(mode, ...)` for all modes `0..4` and stores lists per mode. Rationale: This is logic-transform because it changes data content, structure, selection, or ordering used by downstream steps.
228. [scaffolding] `_filtered_outer_dict()` logs rule pass/fail and mode counts table.
229. [logic-transform] `_filtered_outer_dict()` invokes `OuterDict.from_name_keys(...)` for selected names and re-appends matching innerdicts. Rationale: This is logic-transform because raw key fields are converted into structured key objects used for subsequent matching/grouping.
230. [scaffolding] Step 10 computes intro date via `datetime.now(ZoneInfo(context.config.timezone)).strftime("%B %d, %Y")` and appends subset note.
231. [scaffolding] Step 10 invokes `build_cards(selected_outer_dict, total_draws=..., intro=..., excluded_cols=..., progress_callback=on_build_progress)`.
232. [logic-transform] `build_cards()` iterates `outer_dict.items()`, derives draw labels, header, optional fun-fact from original name-column provenance fields, emits per-innerdict field blocks excluding configured columns/NaN, and returns `{filename: markdown}` map. Rationale: This is logic-transform because structured records are rendered into card content that forms the final deliverable payload.
233. [logic-io] Step 10 invokes `write_cards_zip(cards, output_dir, zip_name, output_format=context.config.output_format, reference_docx=context.config.pandoc_reference_docx, docx_workers=..., progress_callback=on_conversion_progress)`. Rationale: This is final handoff I/O because finished cards are written to deliverable output files.
234. [logic-io] In TXT mode, `write_cards_zip()` writes each card to `<tmp>/<name>.txt` and zips all files. Rationale: This is final handoff I/O because finished cards are written to deliverable output files.
235. [logic-io] In DOCX mode, `write_cards_zip()` copies reference docx, writes `.md` files, invokes pandoc conversion via `_render_docx()` in thread pool, then zips rendered `.docx` files. Rationale: This is final handoff I/O because finished cards are written to deliverable output files.
236. [scaffolding] Step 10 returns `StepResult(artifacts={"cards": cards, "zip_path": zip_path}, messages=[...], diagnostics=[...])`.
237. [scaffolding] After loop, REPL prints execution metrics table and logs diagnostics/output paths; this final output is the terminal end of the full REPL invocation chain.

## 2) FULL end-to-end mode3 `p_gf` detour walkthrough (atomic invocation + SQL walkthrough)
1. [scaffolding] `src.detours.detour_mode3_pgf_stats.main()` starts and creates `argparse.ArgumentParser(...)` with description.
2. [scaffolding] `main()` registers required `--config` argument.
3. [scaffolding] `main()` invokes `parser.parse_args()`.
4. [scaffolding] `main()` invokes `PipelineConfig.from_json(args.config)`.
5. [scaffolding] `main()` invokes `run_detour(config)`.
6. [scaffolding] If `run_detour()` returns unsuccessful result, `main()` raises `RuntimeError(result.summary)`.
7. [scaffolding] If Ctrl+C occurs, `main()` invokes `sys.exit(130)`.
8. [scaffolding] Other exceptions are re-raised.
9. [scaffolding] `run_detour(config, interactive=True, diagnostics=None)` discards `interactive` and `diagnostics` (`del` statements), because this detour is read-only and not REPL-driven.
10. [scaffolding] `run_detour()` constructs `ResourceMonitor()` and invokes `monitor.start()`.
11. [logic-io] `run_detour()` opens DB read-only via `duckdb.connect(str(config.db_file), read_only=True)`. Rationale: This is external input I/O because the persisted DuckDB database file is opened as the detour data source.
12. [scaffolding] `run_detour()` invokes `_build_mode3_pgf_metadata(conn)`.
13. [logic-transform] `_build_mode3_pgf_metadata()` invokes `_scalar_int(conn, "SELECT COUNT(*) FROM population_with_names_economy")`. Rationale: This is logic-transform because it changes data content, structure, selection, or ordering used by downstream steps.
14. [logic-transform] `_scalar_int()` executes SQL and returns int scalar; if row missing, raises runtime error. Rationale: This is logic-transform because it changes data content, structure, selection, or ordering used by downstream steps.
15. [logic-transform] `_build_mode3_pgf_metadata()` executes SQL: `SELECT name_key FROM outerdict_stub ORDER BY name_key` and builds ordered outer-key list. Rationale: This is logic-transform because it changes data content, structure, selection, or ordering used by downstream steps.
16. [logic-transform] `_build_mode3_pgf_metadata()` executes SQL: `SELECT name_key, innerdicts FROM xlsx_innerdicts`. Rationale: This is logic-transform because it changes data content, structure, selection, or ordering used by downstream steps.
17. [logic-transform] For each xlsx row, `_build_mode3_pgf_metadata()` invokes `loads_jsonlines(inner_blob or "")`. Rationale: This is logic-transform because records are re-encoded into structured payloads consumed by downstream matching and card generation.
18. [logic-transform] For each parsed innerdict, it collects `inner.get(KTP_XLSX_MATCH_COL)` into `xlsx_payloads_by_key[name_key]`. Rationale: This is logic-transform because it changes data content, structure, selection, or ordering used by downstream steps.
19. [logic-transform] `_build_mode3_pgf_metadata()` executes SQL selecting parquet evidence from `ssn_innerdicts`: `SELECT "ktp.source_key", "ssnau.p_gf", "ssnau.inference_counts", "ssnau.inference_sources" FROM ssn_innerdicts`. Rationale: This is logic-transform because it changes data content, structure, selection, or ordering used by downstream steps.
20. [logic-transform] It accumulates `sciscinet_count_by_key[source_key] += 1` and tuple lists per source key. Rationale: This is logic-transform because it changes data content, structure, selection, or ordering used by downstream steps.
21. [logic-transform] It iterates each key in ordered `outer_keys`. Rationale: This is logic-transform because it changes data content, structure, selection, or ordering used by downstream steps.
22. [logic-transform] For each key, computes `sciscinet_exactly_one_ok = (count == 1)`. Rationale: This is logic-transform because new derived flags, scores, or summary statistics are computed from existing data.
23. [logic-transform] For each key, computes xlsx rule `xlsx_exact_ok = any(_has_present_xlsx_match_payload(v) for v in payloads) and all(_is_exact_xlsx_match_payload(v) for v in payloads)`. Rationale: This is logic-transform because new derived flags, scores, or summary statistics are computed from existing data.
24. [logic-transform] `_has_present_xlsx_match_payload(value)` returns false for `None`, false for blank strings, otherwise true unless `pd.isna(value)` for non-strings. Rationale: This is logic-transform because it changes data content, structure, selection, or ordering used by downstream steps.
25. [logic-transform] `_is_exact_xlsx_match_payload(value)` returns true for absent/blank/non-string by design path, else parses JSON and verifies exact token/last-name equivalence between source-key fields and matched-pop fields. Rationale: This is logic-transform because it changes data content, structure, selection, or ordering used by downstream steps.
26. [logic-transform] If key passes both rules, it is added to mode-3 selected set. Rationale: This is logic-transform because it changes data content, structure, selection, or ordering used by downstream steps.
27. [logic-transform] For selected keys, detour enforces invariant `len(sciscinet_rows_for_key) == 1`; otherwise raises runtime error. Rationale: This is logic-transform because it changes data content, structure, selection, or ordering used by downstream steps.
28. [logic-transform] For selected key, it appends `p_gf` to distribution list. Rationale: This is logic-transform because it changes data content, structure, selection, or ordering used by downstream steps.
29. [logic-transform] If selected key has missing `p_gf`, it appends `(inference_counts, inference_sources)` to missing-audit list. Rationale: This is logic-transform because it changes data content, structure, selection, or ordering used by downstream steps.
30. [logic-transform] After selection, detour computes `selected_names`, `non_missing_values` vector, `non_missing_n`, `missing_n`. Rationale: This is logic-transform because new derived flags, scores, or summary statistics are computed from existing data.
31. [logic-transform] It computes mean, SD (`ddof=1` when `n>1`), SE, and 95% CI bounds. Rationale: This is logic-transform because new derived flags, scores, or summary statistics are computed from existing data.
32. [logic-transform] It computes min, q1, median, q3, max via numpy quantiles. Rationale: This is logic-transform because new derived flags, scores, or summary statistics are computed from existing data.
33. [logic-transform] It computes IQR, lower fence, upper fence, lower/upper/total outlier counts. Rationale: This is logic-transform because new derived flags, scores, or summary statistics are computed from existing data.
34. [logic-transform] It computes bucket counts over selected set: missing, exact 0, exact 0.5, exact 1, (0,0.5), (0.5,1). Rationale: This is logic-transform because new derived flags, scores, or summary statistics are computed from existing data.
35. [logic-transform] It checks bucket partition invariant: bucket sum must equal selected count; otherwise raises runtime error. Rationale: This is logic-transform because it changes data content, structure, selection, or ordering used by downstream steps.
36. [logic-transform] It checks missing-audit invariant: number of missing-audit tuples must equal missing bucket count; otherwise raises runtime error. Rationale: This is logic-transform because it changes data content, structure, selection, or ordering used by downstream steps.
37. [logic-transform] It computes missing audit tallies (`inference_counts` zero/nonzero/null and `inference_sources` zero/nonzero/null). Rationale: This is logic-transform because new derived flags, scores, or summary statistics are computed from existing data.
38. [logic-transform] It computes `both_zero` and `all_missing_pgf_have_both_zero` (or `None` when no missing rows). Rationale: This is logic-transform because new derived flags, scores, or summary statistics are computed from existing data.
39. [scaffolding] It invokes `_db_file_from_pragma(conn)`.
40. [scaffolding] `_db_file_from_pragma()` executes SQL `PRAGMA database_list` and returns active DB file path from result row.
41. [logic-transform] `_build_mode3_pgf_metadata()` invokes `_pct(...)` repeatedly to compute all percentage fields across counts, buckets, and audit blocks. Rationale: This is logic-transform because new derived flags, scores, or summary statistics are computed from existing data.
42. [logic-transform] `_build_mode3_pgf_metadata()` returns metadata dict containing identity/scope, counts, rule counts, distribution stats, outlier stats, bucket stats, and missing audit stats. Rationale: This is logic-transform because it changes data content, structure, selection, or ordering used by downstream steps.
43. [logic-io] Back in `run_detour()`, it invokes `_print_summary(metadata)`. Rationale: This is final handoff I/O because computed mode-3 p_gf results are rendered and shown to the end user.
44. [logic-io] `_print_summary()` invokes `console.print(...)` for header lines (detour name, DB path, mode description, tables used). Rationale: This is final handoff I/O because computed mode-3 p_gf results are rendered and shown to the end user.
45. [logic-io] `_print_summary()` constructs Rich `Selection Counts` table and invokes `add_row(...)` for population rows, outerdict keys, selected counts, and p_gf participation percentages. Rationale: This is final handoff I/O because computed mode-3 p_gf results are rendered and shown to the end user.
46. [logic-io] `_print_summary()` constructs Rich `Mode-3 Rule Counts` table and invokes `add_row(...)` for sciscinet exactly-one pass/fail and xlsx exact pass/fail. Rationale: This is final handoff I/O because computed mode-3 p_gf results are rendered and shown to the end user.
47. [logic-io] `_print_summary()` constructs Rich `p_gf Distribution` table and invokes `add_row(...)` for non-missing N, mean, CI, SD, SE, min, Q1, median, Q3, max. Rationale: This is final handoff I/O because computed mode-3 p_gf results are rendered and shown to the end user.
48. [logic-io] `_print_summary()` constructs Rich `p_gf Buckets` table and invokes `add_row(...)` for each bucket raw count and `% of mode-3`. Rationale: This is final handoff I/O because computed mode-3 p_gf results are rendered and shown to the end user.
49. [logic-io] `_print_summary()` constructs Rich `Missing p_gf Inference Audit` table and invokes `add_row(...)` for missing count, both-zero status, and all inference count/source splits. Rationale: This is final handoff I/O because computed mode-3 p_gf results are rendered and shown to the end user.
50. [logic-io] `_print_summary()` constructs Rich `Outliers` table and invokes `add_row(...)` for IQR, fences, lower/upper/total outliers, and outlier percent. Rationale: This is final handoff I/O because computed mode-3 p_gf results are rendered and shown to the end user.
51. [scaffolding] Back in `run_detour()`, after summary print, it constructs `DetourResult(success=True, steps_completed=[], summary=..., metadata=metadata)`.
52. [scaffolding] If any exception occurs in build/print path, `run_detour()` invokes `console.print("[red]Exited prematurely: ...[/red]")` and re-raises.
53. [scaffolding] In `finally`, `run_detour()` invokes `monitor.stop()` and stores peak RAM.
54. [scaffolding] In `finally`, if connection was opened, it invokes `conn.close()`.
55. [scaffolding] After finally, `run_detour()` constructs and prints Rich `Execution Metrics` table with peak RAM.
56. [scaffolding] It prints two additional metrics lines (`Execution Metrics`, `Peak RAM Usage: ...`).
57. [scaffolding] `run_detour()` returns `DetourResult`.
58. [scaffolding] `main()` receives result and exits successfully if `result.success` is true.
59. [scaffolding] Defined but not invoked in this runtime path: `_round_or_none(...)` exists in module but is never called by `main()`, `run_detour()`, `_build_mode3_pgf_metadata()`, or `_print_summary()`.
