# RFC: Full End-to-End Walkthrough for REPL and Mode-3 `p_gf` Detour

**Timestamp (UTC):** 2026-03-10 15:21Z  \
**Author:** GPT-5 Codex (OpenAI)

## 1) FULL end-to-end REPL walkthrough (atomic invocation + SQL walkthrough)
1. `src.repl.main()` starts and creates `argparse.ArgumentParser(description="KTP pipeline runner.")`.
2. `main()` registers CLI arguments: `--config`, mutually-exclusive `--new`/`--resume(--continue)`, optional `--yes`, `--non-interactive`, `--quiet`.
3. `main()` invokes `parser.parse_args()`.
4. `main()` invokes `run_reproduction(args)` inside `try`.
5. If Ctrl+C occurs, `main()` invokes `console.print("Process Interrupted")` and `sys.exit(130)`.
6. If any other exception escapes, `main()` invokes `console.print_exception()` and `sys.exit(1)`.
7. `run_reproduction(args)` computes runtime switches: `interactive = not args.non_interactive`, `auto_confirm = bool(args.yes)`.
8. If `args.new` and `args.yes`, `reset_confirmed = True`.
9. If `args.new` and interactive without `--yes`, `run_reproduction()` invokes `console.input("Reset pipeline state and database? [y/N]")` and sets `reset_confirmed` only when input is `y`.
10. If `args.new` and non-interactive without `--yes`, `reset_confirmed` remains `False`.
11. `run_reproduction()` invokes `init_pipeline(args, interactive=interactive, reset_confirmed=reset_confirmed)`.
12. `init_pipeline()` validates `args.config`; if missing, raises `ValueError("A JSON config file is required...")`.
13. `init_pipeline()` invokes `PipelineConfig.from_json(Path(args.config))`.
14. `PipelineConfig.from_json()` invokes `model_validate_json(...)` and enforces schema/validators.
15. Config validation enforces required `files_config` keys, required file-entry fields (`path`, `sha256`, `desc`), at least one key with `hcr_xlsx_` prefix, and normalizes integer `sample_draw_sizes` to dict specs.
16. `init_pipeline()` constructs `PipelineManager(config.state_file, config.db_file)`.
17. `PipelineManager.__init__()` invokes `_load_state()`; if no state file, uses default `{"steps_completed": [], "session_dir": None}`.
18. `init_pipeline()` invokes `manager.connect_db()`.
19. `connect_db()` invokes `duckdb.connect(str(self.db_file))`.
20. `connect_db()` executes SQL: `SET memory_limit='20GB'`.
21. `connect_db()` executes SQL: `INSTALL splink_udfs FROM community; LOAD splink_udfs;`.
22. `init_pipeline()` constructs `ResourceMonitor()` and invokes `monitor.start()`.
23. If `args.new` and `reset_confirmed` is false, `init_pipeline()` raises `ValueError("Pipeline reset confirmation required for --new.")`.
24. If `args.new` and confirmed, `init_pipeline()` invokes `_reset_pipeline(conn, manager)`.
25. `_reset_pipeline()` executes SQL `DROP TABLE IF EXISTS ...` for canonical pipeline tables (`registered_resources`, `population`, `population_names`, `population_economy`, `samples`, `outerdict_stub`, `xlsx_innerdicts`, `docx_rows`, `docx_innerdicts`, `ssn_author_matches`, `ssn_innerdicts`).
26. `_reset_pipeline()` executes SQL `DROP VIEW IF EXISTS ...` for canonical views (`population_with_names`, `population_with_names_economy`, `samples_with_context`, `samples_with_names`, `outerdict_name_keys`, `xlsx_matches`, `xlsx_output`, `docx_matches`, `docx_output`).
27. `_reset_pipeline()` executes SQL against `information_schema.tables` to discover all objects with name like `ssn_%` and drops each by type (`BASE TABLE` => `DROP TABLE`, `VIEW` => `DROP VIEW`).
28. `_reset_pipeline()` invokes `manager.reset_state()`; this clears in-memory state and unlinks state file if present.
29. `init_pipeline()` sets `session_stamp`: for new runs, invokes `datetime.now().strftime("%Y%m%d_%H%M%S")` and `manager.set_session_dir(session_stamp)`.
30. On resume runs, `init_pipeline()` invokes `manager.get_session_dir()`; if absent, generates/saves a fresh timestamp.
31. `manager.set_session_dir(...)` writes JSON state file (ensuring parent dir exists).
32. `init_pipeline()` constructs `DiagnosticsReport(Path("data/diagnostics") / session_stamp)`.
33. `DiagnosticsReport` ensures diagnostics directory exists and creates `repl_diagnostics.md` with header if missing.
34. `init_pipeline()` computes `steps_to_run` as full `STEP_ORDER` for `--new`, else as `[step for step in STEP_ORDER if not manager.is_done(step)]`.
35. If `manager.is_done(STEP_REGISTER_RESOURCES)` is true, `init_pipeline()` invokes `register_pipeline_resources(config)` to hydrate `context.resources` for resume workflows.
36. `register_pipeline_resources()` invokes many `register_resource(...)` calls for each configured parquet and world-bank file.
37. `register_resource(...)` uses provided expected hash when present; otherwise it invokes `_compute_hash_via_resource(path)` first, then constructs `RegisteredResource(..., verify_hash_on_init=True)` and verifies hash on init.
38. `register_pipeline_resources()` invokes `configured_hcr_xlsx_paths(config)` and `register_resources(...)` for HCR XLSX files.
39. `register_pipeline_resources()` invokes `discover_docx_files(config.docx_dir)` and `register_resources(...)` for DOCX files.
40. `discover_docx_files()` invokes `find_files_by_extension(docx_dir, "docx", recursive=False)` and filters `~$` files.
41. If `manager.is_done(STEP_BUILD_OUTERDICT)` is true, `init_pipeline()` invokes `_load_outerdict_stub(conn, table_name=OUTERDICT_STUB_TABLE)`; and if `resources is None` in that branch, it invokes `register_pipeline_resources(config)` before hydrating resume innerdicts.
42. `_load_outerdict_stub()` executes SQL: `SELECT name_key FROM outerdict_stub`.
43. `_load_outerdict_stub()` invokes `NameKey.from_json_key(...)` for each row and then `OuterDict.from_name_keys(...)`.
44. If resume state marks step `07` done, `init_pipeline()` invokes `append_innerdicts_from_jsonlines_table(conn, table_name=xlsx_innerdicts, outer_dict=..., procedure=XlsxMatchProcedure())`.
45. That helper executes SQL: `SELECT name_key, innerdicts FROM xlsx_innerdicts`, parses JSONL payload per key, constructs `InnerDict.from_mapping(...)`, and appends via `outer_dict.add_inner_by_key(...)`.
46. If resume state marks step `08` done, `init_pipeline()` invokes `append_innerdicts_from_jsonlines_table(... table_name=docx_innerdicts, procedure=DocxMatchProcedure())`.
47. If resume state marks step `09` done, `init_pipeline()` invokes `append_innerdicts_from_rows_table(conn, table_name=ssn_author_output, outer_dict=..., procedure=ParquetMatchProcedure())` without overriding `key_column`.
48. `append_innerdicts_from_rows_table()` executes SQL `SELECT * FROM ssn_author_output`, then looks for default key column `name_key`; if absent, it raises `ValueError(\"Missing name_key column in ssn_author_output\")`; otherwise it streams batches, reconstructs records, and appends innerdicts.
49. `init_pipeline()` constructs and returns `InitResult(context=PipelineContext(...), steps_to_run=..., monitor=...)`.
50. If any init exception occurs, `init_pipeline()` invokes `monitor.stop()`, `manager.close()`, then re-raises.
51. Back in `run_reproduction()`, it stores `context`, `steps_to_run`, and `monitor` from `init_result`.
52. `run_reproduction()` computes session log path: `context.diagnostics.path.parent / "repl_session.log"`.
53. If new run with confirmed reset and old session log exists, it invokes `session_log_path.unlink()`.
54. If session log exists, it invokes `session_log_path.read_text(...)`, parses each line into `(style, message)` tuples for history replay.
55. `run_reproduction()` defines closure `print_history()` that prints historical lines and emits a resume marker with `datetime.now(ZoneInfo(context.config.timezone)).strftime(...)`.
56. `run_reproduction()` defines closure `log(msg, style)` that appends to session log file, appends to in-memory history, and prints via Rich.
57. `run_reproduction()` sets `context.log = log` so step modules can emit runtime logs.
58. If interactive, `run_reproduction()` invokes `print_history()` before continuing.
59. If `args.resume` and no `--yes` in interactive mode, it prompts with `console.input("> ")`; non-`y` returns early.
60. If `args.resume` and no `--yes` in non-interactive mode, it prints warning + diagnostics path and returns early.
61. `run_reproduction()` enters loop `for step_id in steps_to_run:`.
62. Per iteration, it invokes `STEP_REGISTRY.get(step_id)`.
63. If `step_fn is None`, raises `ValueError("Unknown step: ...")`.
64. It invokes `run_step(step_id, step_fn, context, log=log, verbose=not args.quiet)`.
65. `run_step()` checks `context.manager.is_done(step_id)`; if true, returns `StepResult(messages=["Skipped ..."])`.
66. Otherwise `run_step()` invokes `log("Running step: ...", "cyan")`.
67. `run_step()` executes SQL `BEGIN`.
68. `run_step()` invokes the step function `step_fn(context)`.
69. On step success, `run_step()` executes SQL `COMMIT` and invokes `context.manager.save_state(step_id)`.
70. On step failure, `run_step()` executes SQL `ROLLBACK`, invokes `context.diagnostics.add_section(f"{step_id} (failed)", [error])`, then re-raises.
71. If verbose and step diagnostics/messages exist, `run_step()` invokes `context.diagnostics.add_section(step_id, ...)`.
72. `run_step()` invokes `dump_artifacts(context, step_id, result.artifacts)`.
73. `dump_artifacts()` ensures artifacts dir exists with `mkdir(parents=True, exist_ok=True)`.
74. If artifacts include parquet view names/dfs lists, it writes each DataFrame with `to_csv(...)` named `<step_id>_<view_name>.csv`.
75. For any direct DataFrame artifact it writes `<step_id>_<artifact>.csv`.
76. For list-of-DataFrame artifacts, writes `<step_id>_<artifact>_<idx>.csv`.
77. For `OuterDict` artifact, invokes `dump_json(...)` to write `<step_id>_<artifact>.json`.
78. For `Path` artifact, records path directly as dumped artifact.
79. `run_step()` appends artifact summary lines to `result.messages` and returns.
80. Back in loop, `run_reproduction()` invokes `log(line, style="green")` for every returned message line.
81. If `step_id == STEP_BUILD_CARDS`, it reads `result.artifacts.get("zip_path")` and `result.artifacts.get("cards")`, storing `zip_path` and `card_count`.
82. If interactive and no `--yes`, it prompts `Continue to next step? [y/N]`; non-`y` breaks loop.
83. If any exception escapes loop, `run_reproduction()` invokes `log("Exited prematurely: ...", style="red")` and re-raises.
84. `run_reproduction()` always enters `finally`: invokes `monitor.stop()` if monitor exists; then invokes `context.manager.close()` if context exists.
85. After loop completion, `run_reproduction()` builds a Rich metrics table and prints peak RAM (and cards count if known).
86. It invokes `log("Execution Metrics", ...)`, `log("Peak RAM Usage: ...")`, optional `log("Cards: ...")`, and `log("Diagnostics report saved to: ...")`.
87. If `zip_path` exists, invokes `log("Success! Output saved to: ...")`.
88. `run_reproduction()` returns `zip_path` (or `None` if not produced).
89. Loop step invocation order is always `STEP_ORDER` when `--new`: `01_register_resources`, `02_load_xlsx`, `03_infer_names`, `04_add_economy_priority`, `05_sample_population`, `06_build_outerdict`, `07_match_xlsx`, `08_match_docx`, `09_match_parquet`, `10_build_cards`.
90. Step `01_register_resources.run(context)` starts by invoking `configured_hcr_xlsx_paths(context.config)`.
91. It invokes `discover_docx_files(context.config.docx_dir)`.
92. It invokes `register_pipeline_resources(context.config)` and stores in `context.resources`.
93. It invokes internal `_resource_registry_frame(resources)` to assemble a pandas frame of resource metadata.
94. It invokes `register_frame(context.conn, "registered_resources_frame", resources_df)`.
95. `register_frame()` invokes `conn.register(name, df)`, SQL `CREATE OR REPLACE TABLE <name> AS SELECT * FROM <name>`, then `conn.unregister(name)` best-effort.
96. Step 01 executes SQL: `CREATE OR REPLACE TABLE registered_resources AS SELECT * FROM registered_resources_frame`.
97. Step 01 executes SQL: `DROP TABLE IF EXISTS registered_resources_frame`.
98. Step 01 returns `StepResult` with message counts and artifact paths for discovered xlsx/docx files.
99. Step `02_load_xlsx.run(context)` invokes `_build_population_table(conn, context.resources.xlsx_resources, table_name=population, ...)`.
100. `_build_population_table()` loops through XLSX resources, invoking `Path(resource.__fspath__())` per resource.
101. It skips non-`.xlsx` and temporary `~$` files.
102. It invokes `pd.read_excel(path, engine="openpyxl")`.
103. It invokes `_normalize_hcr_header(...)` for each input column and prepends `hcr.` naming.
104. It adds row/index columns: `hcr.row_number = reset_index + 2`, `hcr.filename`, and global `ktp.population_index` sequence.
105. It coerces non-index columns to `string` dtype.
106. It executes SQL existence check: `SELECT COUNT(*) FROM information_schema.tables WHERE table_name = ?`.
107. If table exists, it executes SQL `PRAGMA table_info('population')` and computes schema diff.
108. For new columns it executes SQL `ALTER TABLE population ADD COLUMN "<col>" <type>`.
109. It pads missing columns in DataFrame with `pd.NA`, reorders to table schema, invokes `register_frame(conn, "population_frame", df)`, then SQL `INSERT INTO population SELECT * FROM population_frame`.
110. If table does not exist, it invokes `register_frame(conn, "population", df)` which materializes `population` directly.
111. Back in step 02, it executes SQL `SELECT * FROM population` to load artifact DataFrame and returns row/column counts.
112. Step `03_infer_names.run(context)` verifies resources exist; if `HCR_XLSX_NAME_COLS` is empty, it infers mappings per XLSX via `_infer_name_columns_from_xlsx(...)`.
113. `_infer_name_columns_from_xlsx()` invokes `pd.read_excel(...)`, normalizes headers, then helper `pick(...)` to find first/last columns by candidate tokens.
114. Step 03 validates every configured XLSX has mapping; missing mappings raise `ValueError`.
115. Step 03 invokes `_build_name_expr(HCR_XLSX_NAME_COLS, 0)` and `_build_name_expr(..., 1)` to build filename-conditioned CASE expressions.
116. Step 03 executes SQL: `CREATE OR REPLACE TABLE population_names AS SELECT p.ktp.population_index, <first_case> AS ktp.first_name, <last_case> AS ktp.last_name FROM population p`.
117. Step 03 executes SQL: `CREATE OR REPLACE VIEW population_with_names AS SELECT p.*, n.ktp.first_name, n.ktp.last_name FROM population p JOIN population_names n ON p.ktp.population_index = n.ktp.population_index`.
118. Step 03 executes SQL `SELECT * FROM population_with_names` and returns artifact.
119. Step `04_add_economy_priority.run(context)` invokes `_load_income_labels(context.resources.world_bank_resource)`.
120. `_load_income_labels()` invokes `pd.read_excel(sheet_name="Country Analytical History", header=None)`.
121. It scans rows for an `FY##` token, picks the last FY column, then builds canonical country-to-income map and alias-expanded match rows using `KTP_COUNTRY_ALIASES`.
122. Step 04 builds DataFrame from income rows and invokes `register_frame(conn, "income_map_frame", ...)`.
123. Step 04 executes SQL: `CREATE OR REPLACE TABLE income_map AS SELECT * FROM income_map_frame`.
124. Step 04 executes SQL: `DROP TABLE IF EXISTS income_map_frame`.
125. Step 04 executes SQL `DESCRIBE population` to infer affiliation columns.
126. It invokes `_infer_affiliation_columns(...)` for primary and secondary defaults.
127. It invokes `_normalize_affiliation_map(HCR_XLSX_AFFILIATIONS_COLS, index=0/1)`.
128. It invokes `_affiliation_case(...)` twice to produce filename-aware primary/secondary affiliation SQL expressions.
129. It computes country buckets using `_non_english_non_eu_hics(...)`, local `_countries_for(...)`, and local `_sql_in_list(...)`.
130. Step 04 executes core SQL to create `population_economy` with CTEs `aff` and `matches`.
131. Inside that SQL it invokes key operations: `regexp_replace(lower(unaccent(...)))`, token-space containment match `(' ' || aff_tokens || ' ') LIKE '% ' || m.match_norm || ' %'`, aggregated JSON economies via `to_json(list_sort(list(DISTINCT m.country) FILTER ...))`, income-group priority CASE logic, and priority-group label CASE logic.
132. Step 04 executes SQL: `CREATE OR REPLACE VIEW population_with_names_economy AS SELECT p.*, n.*, e.<economy fields> FROM population p JOIN population_names n ... JOIN population_economy e ...`.
133. Step 04 executes SQL `DESCRIBE population_with_names_economy` then SQL `SELECT <ordered_cols> FROM population_with_names_economy` and returns artifact.
134. Step `05_sampling.run(context)` validates arithmetic: `sum(sample_draw_sizes) == total_draws - pilot_count`; else raises `ValueError`.
135. It executes SQL `SELECT ktp.population_index FROM population` and creates numpy `index_pool`.
136. It creates `pilot_triples` DataFrame from `PILOT_NAME_CATEGORY_TRIPLES`, invokes `register_frame(conn, "pilot_triples", ...)`.
137. It executes SQL to fetch pilot exclusion indices by joining `population` to `pilot_triples` on first/last/category and filtering `hcr.filename = pilot_xlsx_name`.
138. It invokes `np.random.default_rng(context.config.sample_seed)`.
139. It invokes `_precompute_draw_batches(index_pool, draw_specs, rng, seen_indices_initial=pilot_population_indices)`.
140. `_precompute_draw_batches()` iterates each draw spec; with `replace=True` invokes `rng.choice(index_pool, size=draw_size, replace=True)`; with `replace=False` computes remaining pool excluding seen indices and validates capacity.
141. For each precomputed draw, step 05 creates `sample_indices` DataFrame and invokes `register_frame(conn, "sample_indices", ...)`.
142. For each draw, step 05 executes SQL joining `population` to `sample_indices` to get filename+fragment rows ordered by `sample_id`.
143. It labels draw numbers and invokes `_append_samples(conn, sample_df[[ktp.filename, ktp.fragment, ktp.draw_number]])`.
144. `_append_samples()` invokes `register_frame(conn, "samples_frame", df)`, checks table existence via SQL on `information_schema.tables`, then either SQL `INSERT INTO samples SELECT ... FROM samples_frame` or SQL `CREATE TABLE samples AS SELECT ... FROM samples_frame`, and drops temp table.
145. Step 05 executes SQL query for pilot rows joined with `pilot_triples`, enforces expected pilot count, orders by configured tuple order, sets labels `pilot.1...`, and invokes `_append_samples(...)`.
146. Step 05 executes SQL to create `samples_with_context` view using joins to `population`, `population_names`, and `population_economy` with draw-order CASE sorting.
147. Step 05 executes SQL to create `samples_with_names` view as reduced join.
148. Step 05 executes SQL drops: `DROP TABLE IF EXISTS sample_indices`, `DROP TABLE IF EXISTS pilot_triples`.
149. Step 05 executes SQL `SELECT * FROM samples_with_context` and returns artifact.
150. Step `06_build_outerdict_stub.run(context)` executes SQL selecting excluded-name rows from `samples_with_names` where first/last is null/empty, with deterministic draw/file sort ordering.
151. It logs excluded-row diagnostics and preview lines.
152. It builds excluded key JSON strings via local `_name_key_json(...)` and invokes `register_frame(conn, "outerdict_excluded_stub_frame", ...)`.
153. It executes SQL: `CREATE OR REPLACE TABLE outerdict_stub_excluded AS SELECT * FROM outerdict_excluded_stub_frame`.
154. It executes SQL: `DROP TABLE IF EXISTS outerdict_excluded_stub_frame`.
155. It executes SQL: `CREATE OR REPLACE VIEW outerdict_name_keys_excluded AS SELECT name_key AS ktp.source_key, json_extract_string(...) AS ktp.first_name, json_extract_string(...) AS ktp.last_name FROM outerdict_stub_excluded`.
156. It executes SQL: `SELECT DISTINCT ktp.first_name, ktp.last_name FROM samples_with_names`; then pandas-side filtering drops null/empty pairs before key construction.
157. It constructs `NameKey(...)` objects and invokes `OuterDict.from_name_keys(name_keys)`; assigns to `context.outer_dict`; it also constructs `outer_dict_excluded = OuterDict(data={name_key_json: [] ...})` for excluded null/empty-name keys.
158. It builds active stub DataFrame and invokes `register_frame(conn, "outerdict_stub_frame", ...)`.
159. It executes SQL: `CREATE OR REPLACE TABLE outerdict_stub AS SELECT * FROM outerdict_stub_frame`.
160. It executes SQL: `DROP TABLE IF EXISTS outerdict_stub_frame`.
161. It executes SQL: `CREATE OR REPLACE VIEW outerdict_name_keys AS SELECT name_key AS ktp.source_key, json_extract_string(...) AS ktp.first_name, json_extract_string(...) AS ktp.last_name FROM outerdict_stub`.
162. Step `07_match_xlsx.run(context)` executes SQL `DESCRIBE population` and invokes `hcr_excluded_columns(...)` to decide payload columns.
163. It invokes `draw_sort_ctes_sql(draw_col=ktp.draw_number, source_key_col=ktp.source_key)` and `draw_sort_order_by_sql(...)` to embed deterministic sort CTE SQL.
164. Step 07 executes SQL `CREATE OR REPLACE VIEW xlsx_matches AS WITH name_draws, pop_names, base, row_ranked, ranked ...`.
165. In `name_draws`, SQL computes normalized source-key tokens with `lower(unaccent(...))`, `regexp_split_to_array`, and first token extraction via `list_extract`.
166. In `pop_names`, SQL joins `population` + `population_names` + left joins `population_economy` and `registered_resources`, while deriving normalized token arrays for population names.
167. In `base`, SQL joins `name_draws` to `pop_names` with key conditions `nd.nd_last_clean = p.pop_last_clean` and `list_contains(p.pop_first_tokens, nd.nd_first_token)`.
168. In `base`, SQL emits structured JSON `ktp.xlsx_match` using `json_object(...)` including source-key token list and matched-pop token list.
169. Step 07 executes SQL `SELECT * FROM xlsx_matches` to pandas, filters non-null filename rows, groups by `ktp.source_key`, serializes grouped records via `dumps_jsonlines(...)`.
170. Step 07 invokes `register_frame(conn, "xlsx_innerdict_frame", inner_df)`.
171. It executes SQL: `CREATE OR REPLACE TABLE xlsx_innerdicts AS SELECT * FROM xlsx_innerdict_frame`.
172. It executes SQL: `DROP TABLE IF EXISTS xlsx_innerdict_frame`.
173. It invokes `append_innerdicts_from_jsonlines_table(conn, table_name=xlsx_innerdicts, outer_dict=context.outer_dict, procedure=XlsxMatchProcedure(), required_columns={ktp.filename, ktp.fragment})`.
174. It executes SQL: `CREATE OR REPLACE VIEW xlsx_output AS WITH base AS (SELECT * FROM xlsx_matches WHERE ktp.filename IS NOT NULL), row_ranked, ranked SELECT ... ORDER BY ...`.
175. It executes SQL `SELECT * FROM xlsx_output` and returns artifact.
176. Step `08_match_docx.run(context)` invokes `load_single_table_docx(context.resources.docx_resources)`.
177. `load_single_table_docx()` loops resources, skips `~$` files, invokes `parse_docx_tables_and_notes(path)`, enforces exactly one table, normalizes columns with `normalize_docx_column_name(...)`, adds `ktp.table_1_footnotes`, `ktp.table_1_comments`, `ktp.filename`, and `ktp.table_1_row_number`.
178. If parse mismatch occurs (bad zip, row-comment count mismatch, missing table), it raises descriptive `ValueError`.
179. Step 08 invokes `register_frame(conn, "docx_frame", docx_df)`.
180. Step 08 executes SQL: `CREATE OR REPLACE TABLE docx_rows AS SELECT * FROM docx_frame`.
181. Step 08 executes SQL: `DROP TABLE IF EXISTS docx_frame`.
182. Step 08 invokes `normalize_docx_column_name(RIGHT_NAME_COL)` and validates that normalized column exists in loaded DOCX frame.
183. Step 08 invokes `draw_sort_ctes_sql(...)` and `draw_sort_order_by_sql(...)`.
184. Step 08 executes SQL: `CREATE OR REPLACE VIEW docx_matches AS WITH name_draws, names_clean, docx_clean, base, row_ranked, ranked ...`.
185. In `name_draws`, SQL left joins `outerdict_name_keys` to `samples_with_names` to attach draw labels.
186. In `names_clean`, SQL normalizes names with `regexp_replace(lower(unaccent(...)), '[^0-9a-z]+', '', 'g')`.
187. In `docx_clean`, SQL normalizes candidate docx name field similarly.
188. In `base`, SQL uses `RIGHT JOIN names_clean nd ON POSITION(nd.first_clean IN d.docx_clean) > 0 AND POSITION(nd.last_clean IN d.docx_clean) > 0`, then left joins `registered_resources`.
189. Step 08 executes SQL `SELECT * FROM docx_matches`, drops `docx_clean` column if present, filters non-null filename rows, groups by key, serializes JSONL via `dumps_jsonlines(...)`.
190. Step 08 invokes `register_frame(conn, "docx_innerdict_frame", inner_df)`.
191. It executes SQL: `CREATE OR REPLACE TABLE docx_innerdicts AS SELECT * FROM docx_innerdict_frame`.
192. It executes SQL: `DROP TABLE IF EXISTS docx_innerdict_frame`.
193. It invokes `append_innerdicts_from_jsonlines_table(conn, table_name=docx_innerdicts, outer_dict=context.outer_dict, procedure=DocxMatchProcedure(), required_columns={ktp.filename, ktp.fragment})`.
194. It executes SQL: `CREATE OR REPLACE VIEW docx_output AS WITH base AS (SELECT * FROM docx_matches WHERE ktp.filename IS NOT NULL), row_ranked, ranked SELECT ... ORDER BY ...`.
195. It executes SQL `SELECT * FROM docx_output` and returns artifact.
196. Step `09_match_parquet.run(context)` validates `context.outer_dict` and `context.resources` are present.
197. Step 09 reads parquet file paths from `context.config.files_config` for `author_details`, `authors`, `authors_paper`, `paper_author_affiliation`, `affiliations`, `hit_papers_0`, `hit_papers_1`, and `fields`.
198. Step 09 logs legend entries from `STEP_MATCH_PARQUET_LOG_LEGEND_LINES`.
199. Step 09 executes SQL: `CREATE OR REPLACE TABLE ssn_author_matches AS WITH names, parq AS (...) SELECT DISTINCT ... FROM names JOIN parq ON lower(unaccent(p.alt_name)) = n.match_key_norm`.
200. `parq` CTE unions exploded `display_name_alternatives` and direct `display_name` rows from `read_parquet(author_details_path)`.
201. Step 09 executes SQL aggregate stats query on `ssn_author_matches` for row/name/author counts.
202. Step 09 executes SQL: `CREATE OR REPLACE TABLE ssn_author_papers AS SELECT m.name_key, m."ssnad.authorid" AS authorid, pap.paperid FROM ssn_author_matches m JOIN read_parquet(authors_paper_path) pap ON pap.authorid = m."ssnad.authorid"`.
203. Step 09 executes SQL stats query on `ssn_author_papers` for row/pair/paper counts.
204. Step 09 executes SQL: `CREATE OR REPLACE TABLE ssn_all_hits AS WITH needed_papers AS (SELECT DISTINCT paperid FROM ssn_author_papers) SELECT ... FROM read_parquet(hit_papers_0) JOIN needed_papers UNION ALL SELECT ... FROM read_parquet(hit_papers_1) JOIN needed_papers`.
205. Step 09 executes SQL stats query on `ssn_all_hits`.
206. Step 09 executes SQL: `CREATE OR REPLACE TABLE ssn_author_hit_agg AS SELECT ap.name_key, ap.authorid, SUM(COALESCE(h.hit_1pct,0)) AS "ktp.ssn_sum_hit_1pct" FROM ssn_author_papers ap LEFT JOIN ssn_all_hits h ON ap.paperid=h.paperid GROUP BY ap.name_key, ap.authorid`.
207. Step 09 executes SQL stats query on `ssn_author_hit_agg` (zero/nonzero/null counts).
208. Step 09 executes SQL count query for zero-hit rows removed.
209. Step 09 executes SQL: `CREATE OR REPLACE VIEW ssn_author_matches_nonzero_hit AS SELECT m.* FROM ssn_author_matches m LEFT JOIN ssn_author_hit_agg agg ON ... WHERE agg."ktp.ssn_sum_hit_1pct" IS NULL OR agg."ktp.ssn_sum_hit_1pct" <> 0`.
210. Step 09 executes SQL stats query on `ssn_author_matches_nonzero_hit`.
211. Step 09 executes SQL: `CREATE OR REPLACE VIEW ssn_author_match_nonzero_hit_author_ids AS SELECT DISTINCT "ssnad.authorid" FROM ssn_author_matches_nonzero_hit`.
212. Step 09 executes SQL scalar count on that distinct-author-id view.
213. Step 09 executes SQL: `CREATE OR REPLACE TABLE ssn_author_agg AS SELECT ap.name_key, ap.authorid, SUM(COALESCE(h.hit_1pct,0)) AS "ktp.ssn_sum_hit_1pct", LIST(ap.paperid) FILTER (WHERE h.level='level0') AS "ssn.paperids_level0", LIST(ap.paperid) FILTER (WHERE h.level='level1') AS "ssn.paperids_level1", LIST(DISTINCT h.fieldid) AS "ssn.field_ids_list" FROM ssn_author_papers ap LEFT JOIN ssn_all_hits h ... WHERE EXISTS (SELECT 1 FROM ssn_author_matches_nonzero_hit ...) GROUP BY ap.name_key, ap.authorid`.
214. Step 09 executes SQL scalar count on `ssn_author_agg`.
215. Step 09 invokes `_create_parquet_table(...)` for matched `author_details` table.
216. `_create_parquet_table()` invokes `parquet_columns(conn, path)` (which runs `DESCRIBE SELECT * FROM read_parquet('<path>')`).
217. `_create_parquet_table()` invokes `normalize_parquet_column_name(...)` for each parquet field.
218. `_create_parquet_table()` invokes `parquet_filename(path)` and executes SQL `CREATE OR REPLACE TABLE <target> AS SELECT parq.<cols as normalized>, '<filename>' AS <filename_col> FROM read_parquet('<path>') parq <join_sql>`.
219. Step 09 repeats `_create_parquet_table(...)` for matched `authors` table (joined by distinct nonzero author ids).
220. Step 09 repeats `_create_parquet_table(...)` for matched `paper_author_affiliation` table (joined by distinct nonzero author ids).
221. Step 09 repeats `_create_parquet_table(...)` for matched `affiliations` table (joined by distinct institution ids derived from matched paper-author-affiliation rows).
222. Step 09 executes SQL counts for each matched parquet-derived table.
223. Step 09 executes SQL: `CREATE OR REPLACE TABLE ssn_author_output AS SELECT m.name_key AS ktp.source_key, ... a.*, au.*, CAST(agg."ssn.paperids_level0" AS VARCHAR), CAST(agg."ssn.paperids_level1" AS VARCHAR), CAST(agg."ssn.field_ids_list" AS VARCHAR), agg."ktp.ssn_sum_hit_1pct" FROM ssn_author_matches_nonzero_hit m JOIN <matched_author_details> a ... JOIN <matched_authors> au ... LEFT JOIN ssn_author_agg agg ...`.
224. Step 09 executes SQL scalar count on `ssn_author_output`.
225. Step 09 executes SQL diagnostic query estimating top-works reduction (`SUM(paper_count)` vs `SUM(LEAST(paper_count, TOP_K_WORKS))`).
226. Step 09 executes SQL diagnostic query estimating top-institutions reduction (`SUM(institution_count)` vs `SUM(LEAST(..., TOP_K_INSTITUTIONS))`).
227. Step 09 executes SQL diagnostic query for field-id display-name mapping coverage by joining exploded field IDs to `read_parquet(fields_path)`.
228. Step 09 executes SQL: `CREATE OR REPLACE TABLE ssn_innerdicts AS WITH paper_hits, paper_ranked, top_papers, affiliation_counts, affiliation_ranked, top_institutions, field_lookup, concept_display, enriched, source_draw, base, row_ranked, ranked SELECT ...`.
229. In this SQL, it ranks papers by hit score, builds top-K OpenAlex paper URLs, ranks institutions by paper count, builds top-K institution JSON objects, maps field IDs to display names, and reattaches draw ordering.
230. Step 09 executes SQL scalar count on `ssn_innerdicts`.
231. Step 09 invokes `append_innerdicts_from_rows_table(conn, table_name=ssn_innerdicts, outer_dict=context.outer_dict, procedure=ParquetMatchProcedure(), key_column=ktp.source_key)`.
232. Step 09 executes SQL: `CREATE OR REPLACE VIEW ssn_parquet_output AS WITH source_draw, base, row_ranked, ranked SELECT ... ORDER BY ...`.
233. Step 09 logs (non-SQL) the number of filtered zero-hit rows via `log_tag(...)`.
234. Step 09 executes SQL `SELECT * FROM ssn_parquet_output` into pandas output frame and returns step artifact.
235. Step `10_build_cards.run(context)` checks `context.outer_dict` exists; else raises `ValueError`.
236. Step 10 reads `subset_mode = int(context.config.card_subset_mode)` and validates membership in `CARD_BUILD_SUBSET_DESCRIPTIONS`.
237. Step 10 defines logging/progress closures and helper predicate closures used for subset filtering.
238. `_extract_filenames(value)` parses filenames from scalar string/list/json-list payloads.
239. `_is_sciscinet_inner(inner, sciscinet_filenames)` checks if any filename fields intersect SciSciNet resource names.
240. `_is_exact_xlsx_match_payload(value)` treats `None`/blank/non-string payloads as non-failing in that helper path, and for non-blank strings parses JSON then enforces exact token/last-name equivalence.
241. `_has_present_xlsx_match_payload(value)` defines non-empty payload presence.
242. `_is_non_empty_value(value)` handles string emptiness/placeholder semantics for docx fields.
243. `_has_complete_docx_table_fields(inner)` requires non-empty required `ktp.table_1_*` fields (except optional-empty set).
244. `_filtered_outer_dict()` iterates every `(NameKey, innerdicts)` from `outer_dict.items()`.
245. For each name, it computes `sciscinet_exactly_one_ok`, `xlsx_exact_ok`, and `docx_complete_ok`.
246. `_filtered_outer_dict()` applies `_mode_matches(mode, ...)` for all modes `0..4` and stores lists per mode.
247. `_filtered_outer_dict()` logs rule pass/fail and mode counts table.
248. `_filtered_outer_dict()` invokes `OuterDict.from_name_keys(...)` for selected names and re-appends matching innerdicts.
249. Step 10 computes intro date via `datetime.now(ZoneInfo(context.config.timezone)).strftime("%B %d, %Y")` and appends subset note.
250. Step 10 invokes `build_cards(selected_outer_dict, total_draws=..., intro=..., excluded_cols=..., progress_callback=on_build_progress)`.
251. `build_cards()` iterates `outer_dict.items()`, derives draw labels, header, optional fun-fact from original name-column provenance fields, emits per-innerdict field blocks excluding configured columns/NaN, and returns `{filename: markdown}` map.
252. Step 10 invokes `write_cards_zip(cards, output_dir, zip_name, output_format=context.config.output_format, reference_docx=context.config.pandoc_reference_docx, docx_workers=..., progress_callback=on_conversion_progress)`.
253. In TXT mode, `write_cards_zip()` writes each card to `<tmp>/<name>.txt` and zips all files.
254. In DOCX mode, `write_cards_zip()` copies reference docx, writes `.md` files, invokes pandoc conversion via `_render_docx()` in thread pool, then zips rendered `.docx` files.
255. Step 10 returns `StepResult(artifacts={"cards": cards, "zip_path": zip_path}, messages=[...], diagnostics=[...])`.
256. After loop, REPL prints execution metrics table and logs diagnostics/output paths; this final output is the terminal end of the full REPL invocation chain.

## 2) FULL end-to-end mode3 `p_gf` detour walkthrough (atomic invocation + SQL walkthrough)
1. `src.detours.detour_mode3_pgf_stats.main()` starts and creates `argparse.ArgumentParser(...)` with description.
2. `main()` registers required `--config` argument.
3. `main()` invokes `parser.parse_args()`.
4. `main()` invokes `PipelineConfig.from_json(args.config)`.
5. `main()` invokes `run_detour(config)`.
6. If `run_detour()` returns unsuccessful result, `main()` raises `RuntimeError(result.summary)`.
7. If Ctrl+C occurs, `main()` invokes `sys.exit(130)`.
8. Other exceptions are re-raised.
9. `run_detour(config, interactive=True, diagnostics=None)` discards `interactive` and `diagnostics` (`del` statements), because this detour is read-only and not REPL-driven.
10. `run_detour()` constructs `ResourceMonitor()` and invokes `monitor.start()`.
11. `run_detour()` opens DB read-only via `duckdb.connect(str(config.db_file), read_only=True)`.
12. `run_detour()` invokes `_build_mode3_pgf_metadata(conn)`.
13. `_build_mode3_pgf_metadata()` invokes `_scalar_int(conn, "SELECT COUNT(*) FROM population_with_names_economy")`.
14. `_scalar_int()` executes SQL and returns int scalar; if row missing, raises runtime error.
15. `_build_mode3_pgf_metadata()` executes SQL: `SELECT name_key FROM outerdict_stub ORDER BY name_key` and builds ordered outer-key list.
16. `_build_mode3_pgf_metadata()` executes SQL: `SELECT name_key, innerdicts FROM xlsx_innerdicts`.
17. For each xlsx row, `_build_mode3_pgf_metadata()` invokes `loads_jsonlines(inner_blob or "")`.
18. For each parsed innerdict, it collects `inner.get(KTP_XLSX_MATCH_COL)` into `xlsx_payloads_by_key[name_key]`.
19. `_build_mode3_pgf_metadata()` executes SQL selecting parquet evidence from `ssn_innerdicts`: `SELECT "ktp.source_key", "ssnau.p_gf", "ssnau.inference_counts", "ssnau.inference_sources" FROM ssn_innerdicts`.
20. It accumulates `sciscinet_count_by_key[source_key] += 1` and tuple lists per source key.
21. It iterates each key in ordered `outer_keys`.
22. For each key, computes `sciscinet_exactly_one_ok = (count == 1)`.
23. For each key, computes xlsx rule `xlsx_exact_ok = any(_has_present_xlsx_match_payload(v) for v in payloads) and all(_is_exact_xlsx_match_payload(v) for v in payloads)`.
24. `_has_present_xlsx_match_payload(value)` returns false for `None`, false for blank strings, otherwise true unless `pd.isna(value)` for non-strings.
25. `_is_exact_xlsx_match_payload(value)` returns true for absent/blank/non-string by design path, else parses JSON and verifies exact token/last-name equivalence between source-key fields and matched-pop fields.
26. If key passes both rules, it is added to mode-3 selected set.
27. For selected keys, detour enforces invariant `len(sciscinet_rows_for_key) == 1`; otherwise raises runtime error.
28. For selected key, it appends `p_gf` to distribution list.
29. If selected key has missing `p_gf`, it appends `(inference_counts, inference_sources)` to missing-audit list.
30. After selection, detour computes `selected_names`, `non_missing_values` vector, `non_missing_n`, `missing_n`.
31. It computes mean, SD (`ddof=1` when `n>1`), SE, and 95% CI bounds.
32. It computes min, q1, median, q3, max via numpy quantiles.
33. It computes IQR, lower fence, upper fence, lower/upper/total outlier counts.
34. It computes bucket counts over selected set: missing, exact 0, exact 0.5, exact 1, (0,0.5), (0.5,1).
35. It checks bucket partition invariant: bucket sum must equal selected count; otherwise raises runtime error.
36. It checks missing-audit invariant: number of missing-audit tuples must equal missing bucket count; otherwise raises runtime error.
37. It computes missing audit tallies (`inference_counts` zero/nonzero/null and `inference_sources` zero/nonzero/null).
38. It computes `both_zero` and `all_missing_pgf_have_both_zero` (or `None` when no missing rows).
39. It invokes `_db_file_from_pragma(conn)`.
40. `_db_file_from_pragma()` executes SQL `PRAGMA database_list` and returns active DB file path from result row.
41. `_build_mode3_pgf_metadata()` invokes `_pct(...)` repeatedly to compute all percentage fields across counts, buckets, and audit blocks.
42. `_build_mode3_pgf_metadata()` returns metadata dict containing identity/scope, counts, rule counts, distribution stats, outlier stats, bucket stats, and missing audit stats.
43. Back in `run_detour()`, it invokes `_print_summary(metadata)`.
44. `_print_summary()` invokes `console.print(...)` for header lines (detour name, DB path, mode description, tables used).
45. `_print_summary()` constructs Rich `Selection Counts` table and invokes `add_row(...)` for population rows, outerdict keys, selected counts, and p_gf participation percentages.
46. `_print_summary()` constructs Rich `Mode-3 Rule Counts` table and invokes `add_row(...)` for sciscinet exactly-one pass/fail and xlsx exact pass/fail.
47. `_print_summary()` constructs Rich `p_gf Distribution` table and invokes `add_row(...)` for non-missing N, mean, CI, SD, SE, min, Q1, median, Q3, max.
48. `_print_summary()` constructs Rich `p_gf Buckets` table and invokes `add_row(...)` for each bucket raw count and `% of mode-3`.
49. `_print_summary()` constructs Rich `Missing p_gf Inference Audit` table and invokes `add_row(...)` for missing count, both-zero status, and all inference count/source splits.
50. `_print_summary()` constructs Rich `Outliers` table and invokes `add_row(...)` for IQR, fences, lower/upper/total outliers, and outlier percent.
51. Back in `run_detour()`, after summary print, it constructs `DetourResult(success=True, steps_completed=[], summary=..., metadata=metadata)`.
52. If any exception occurs in build/print path, `run_detour()` invokes `console.print("[red]Exited prematurely: ...[/red]")` and re-raises.
53. In `finally`, `run_detour()` invokes `monitor.stop()` and stores peak RAM.
54. In `finally`, if connection was opened, it invokes `conn.close()`.
55. After finally, `run_detour()` constructs and prints Rich `Execution Metrics` table with peak RAM.
56. It prints two additional metrics lines (`Execution Metrics`, `Peak RAM Usage: ...`).
57. `run_detour()` returns `DetourResult`.
58. `main()` receives result and exits successfully if `result.success` is true.
59. Defined but not invoked in this runtime path: `_round_or_none(...)` exists in module but is never called by `main()`, `run_detour()`, `_build_mode3_pgf_metadata()`, or `_print_summary()`.
