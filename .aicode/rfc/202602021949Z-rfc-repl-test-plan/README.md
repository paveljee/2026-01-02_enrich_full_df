# RFC: REPL Pipeline Test Plan & Data Requirements

**Timestamp (UTC):** 2026-02-02 19:49Z  \
**Author:** GPT-5.2-Codex (OpenAI)

## Task summary

The user asked for a repo review focused on the REPL pipeline and a **detailed plan** to build comprehensive test suites for each package and pipeline step. The plan must also **enumerate the exact files needed to run tests** (e.g., DOCX, parquet, XLSX). Tests exist but coverage is poor, so I attempted to check coverage using Pixi and documented the result.

## Repo review (REPL pipeline focus)

Primary entrypoint: `src/repl.py`.

Pipeline steps (in order):
1. Discover XLSX inputs in `config.xlsx_dir`.
2. Register resources (XLSX, DOCX, parquet, World Bank) with integrity hashes.
3. Build DuckDB population table from XLSX files (`hcr_xlsx/loader.py`).
4. Load high-income economies from World Bank XLSX (`hcr_xlsx/preprocessor.py`).
5. Sample population draws + pilot samples (`hcr_xlsx/sampler.py`).
6. Index samples into `OuterDict` name keys (`hcr_xlsx/indexer.py`).
7. Match population rows to name keys (DuckDB join, `hcr_xlsx/matcher.py`).
8. Load DOCX tables (`manual_docx/loader.py`).
9. Match DOCX rows by substring (DuckDB cross join, `manual_docx/matcher.py`).
10. Match SciSciNet parquet data (DuckDB reads + joins, `sciscinet_parquet/matcher.py`).
11. Render cards (`cards.py`) and write ZIP (txt/docx).

Core data models:
- `OuterDict`/`InnerDict` with `NameKey` JSON keys (`src/data_models/outer_dict.py`).
- `RegisteredResource` + `SourceKey` for provenance (`src/data_models/source_key.py`).

Supporting modules:
- `src/parse_docx.py` (XML extraction of DOCX tables)
- `src/name_utils.py` (name unification and CSV↔DOCX matcher)
- `src/utils/*` (DuckDB helpers, resource registry, name key frames)

## Coverage check status (Pixi)

Attempted coverage with Pixi using:
- `pixi run pytest -- --cov=src --cov-report=term`

Result:
- `pytest-cov` is **not installed**, so pytest treats `--cov=src` as a path and errors.
- `coverage` module is also absent in the environment.

Conclusion: **Coverage cannot be measured yet** without adding `pytest-cov` (or `coverage`) to dependencies and a Pixi task to run it.

## Proposed test plan (by package + pipeline step)

### Phase 0 — Enable coverage (foundation)
- **✅ Already done by human.** Add `pytest-cov` to `pyproject.toml` dependencies.
- Add Pixi task (e.g., `cov`) to run:
  - `pytest -vv --cov=src --cov-report=term-missing --cov-report=xml`
- Keep `pixi run test` unchanged for quick runs.

### Phase 1 — Data models (unit tests)
- `NameKey` serialization roundtrips (already partially covered). Extend to:
  - Unicode + punctuation normalization expectations (if any are desired).
- `InnerDict` validation:
  - Missing `dataset_id_field` raises.
- `OuterDict`:
  - `add_inner`, `ensure_inner_list`, and `items` ordering / behavior.
- `SourceKey`:
  - Fragment type mismatch, string key parsing edge cases.

### Phase 2 — Utilities
- `utils/duckdb.register_frame`:
  - Overwrite behavior and table schema retention.
- `utils/resources`:
  - `register_resource` uses expected hash when provided.
  - `register_resources` applies per-file expected hashes.
- `utils/files.find_files_by_extension`:
  - Already tested; add edge case for uppercase extensions.
- `utils/name_keys`:
  - `build_name_key_frame` order and content.

### Phase 3 — HCR XLSX pipeline
- `hcr_xlsx/loader.build_population_table`:
  - Normalizes headers, row numbering, filename injection, population index uniqueness.
- `hcr_xlsx/preprocessor.preprocess_samples`:
  - Economies extraction, priority logic, non-English HIC grouping.
- `hcr_xlsx/sampler.sample_population`:
  - Deterministic sampling for a fixed seed; draw numbering.
- `hcr_xlsx/sampler.sample_pilot`:
  - Pilot ordering and draw label formatting.
- `hcr_xlsx/indexer.index_samples`:
  - Correct mapping of name columns by filename; raises on missing mapping.
- `hcr_xlsx/matcher.match_population`:
  - Substring matching of first name token, case-insensitive.

### Phase 4 — Manual DOCX pipeline
- `manual_docx/loader.normalize_docx_column_name`:
  - Column normalization rules (prefix, punctuation, whitespace).
- `manual_docx/loader.load_docx_tables`:
  - Table index + row index + fragment IDs.
- `manual_docx/matcher.match_docx`:
  - Name substring logic matches `parse_docx` semantics.
  - Handle missing name column with clear error.

### Phase 5 — SciSciNet parquet pipeline
- `sciscinet_parquet/matcher.match_parquet`:
  - Build small synthetic parquet files via DuckDB `COPY` for:
    - `author_details` (display_name + alternatives)
    - `authors_paper`
    - `hit_papers_level0/1`
  - Verify:
    - `matched_authors_bridge` construction
    - `final_agg` content
    - Output records contain `ktp.source_key` fragments and filename

### Phase 6 — Cards + output
- `cards.build_cards`:
  - Intro/header, fun-fact injection, draw number formatting.
  - Excluded columns are omitted from card content.
- `cards.write_cards_zip`:
  - TXT mode creates ZIP with expected filenames.
  - DOCX mode: skip if `pandoc` missing; otherwise validate ZIP entries.

### Phase 7 — REPL integration tests
- Minimal end-to-end test using tiny synthetic datasets:
  - 1–2 XLSX rows, 1 DOCX table, small parquet files.
- Assert:
  - `OuterDict` entries exist after matching.
  - Cards ZIP produced with expected count and filenames.
- Optional: Add a “slow” marker for full data integration tests.

## Required files & test data access

### For current tests to run without skipping
These tests are skipped unless the following exist:
- **✅ READ-ONLY!** `/Volumes/Users/Anonymous/Workshop/202504161200UTC-4_Nancy_Baxter_Andrea_Tricco_collabs/2024-Historical-Highly-Cited-Researchers-lists - final/*.xlsx` (HCR XLSX inputs)
- **✅ READ-ONLY!** `/Volumes/Users/Anonymous/Workshop/202504161200UTC-4_Nancy_Baxter_Andrea_Tricco_collabs/analyses/2026-01-02_enrich_full_df/data/samples/*.csv` (sample CSVs used in validation)
- **✅ READ-ONLY!** `/Volumes/Users/Anonymous/Workshop/202504161200UTC-4_Nancy_Baxter_Andrea_Tricco_collabs/analyses/2026-01-02_enrich_full_df/data/manual_extractions/*.docx` (manual DOCX tables)
- **✅ READ-ONLY!** `/Volumes/Users/Anonymous/Workshop/202504161200UTC-4_Nancy_Baxter_Andrea_Tricco_collabs/analyses/2026-01-02_enrich_full_df/data/OGHIST_2025_07_01.xlsx` (World Bank economies file)

### For REPL pipeline integration tests
In addition to the above:
- ✅ `resources/pandoc-custom-reference.docx` (already in repo)
- ✅ `pandoc` binary in PATH (for DOCX output tests)

### For SciSciNet parquet matching
Access to these parquet files referenced in `src/config.py`:
- **✅ READ-ONLY!** `/Volumes/home/anonymous/sciscinet/v2/hf/xet/sciscinet_author_details.parquet`
- **✅ READ-ONLY!** `/Volumes/home/anonymous/sciscinet/v2/hf/xet/sciscinet_authors_paperid.parquet`
- **✅ READ-ONLY!** `/Volumes/home/anonymous/sciscinet/v2/hf/xet/hit_papers_level0.parquet`
- **✅ READ-ONLY!** `/Volumes/home/anonymous/sciscinet/v2/hf/xet/hit_papers_level1.parquet`
- **✅ READ-ONLY!** `/Volumes/home/anonymous/sciscinet/v2/hf/xet/sciscinet_fields.parquet`

### Optional / legacy inputs
Referenced in config but not currently used by `run_reproduction`:
- **⚠️ NOT NEEDED - remove the refererence. CSV samples above are the ones to be used for testing.** `/Volumes/home/anonymous/research-integrity-ktp/analyses/2025-12-23_pilot_sampler/pilot_sample_2025-07-24.csv`

## Read-only checks (2026-02-02 19:49Z)

Method: read-only metadata checks using `os.access(path, R_OK/W_OK)` plus glob expansion; no writes performed.

| Path | Exists | Readable | Writable |
| --- | --- | --- | --- |
| `/Volumes/Users/Anonymous/Workshop/202504161200UTC-4_Nancy_Baxter_Andrea_Tricco_collabs/2024-Historical-Highly-Cited-Researchers-lists - final/2014_HCR.xlsx` | Yes | Yes | No |
| `/Volumes/Users/Anonymous/Workshop/202504161200UTC-4_Nancy_Baxter_Andrea_Tricco_collabs/2024-Historical-Highly-Cited-Researchers-lists - final/2015_HCR.xlsx` | Yes | Yes | No |
| `/Volumes/Users/Anonymous/Workshop/202504161200UTC-4_Nancy_Baxter_Andrea_Tricco_collabs/2024-Historical-Highly-Cited-Researchers-lists - final/2016_HCR.xlsx` | Yes | Yes | No |
| `/Volumes/Users/Anonymous/Workshop/202504161200UTC-4_Nancy_Baxter_Andrea_Tricco_collabs/2024-Historical-Highly-Cited-Researchers-lists - final/2017_HCR.xlsx` | Yes | Yes | No |
| `/Volumes/Users/Anonymous/Workshop/202504161200UTC-4_Nancy_Baxter_Andrea_Tricco_collabs/2024-Historical-Highly-Cited-Researchers-lists - final/2018_HCR.xlsx` | Yes | Yes | No |
| `/Volumes/Users/Anonymous/Workshop/202504161200UTC-4_Nancy_Baxter_Andrea_Tricco_collabs/2024-Historical-Highly-Cited-Researchers-lists - final/2019_HCR.xlsx` | Yes | Yes | No |
| `/Volumes/Users/Anonymous/Workshop/202504161200UTC-4_Nancy_Baxter_Andrea_Tricco_collabs/2024-Historical-Highly-Cited-Researchers-lists - final/2020_HCR.xlsx` | Yes | Yes | No |
| `/Volumes/Users/Anonymous/Workshop/202504161200UTC-4_Nancy_Baxter_Andrea_Tricco_collabs/2024-Historical-Highly-Cited-Researchers-lists - final/2021_HCR.xlsx` | Yes | Yes | No |
| `/Volumes/Users/Anonymous/Workshop/202504161200UTC-4_Nancy_Baxter_Andrea_Tricco_collabs/2024-Historical-Highly-Cited-Researchers-lists - final/2022_HCR.xlsx` | Yes | Yes | No |
| `/Volumes/Users/Anonymous/Workshop/202504161200UTC-4_Nancy_Baxter_Andrea_Tricco_collabs/2024-Historical-Highly-Cited-Researchers-lists - final/2023_HCR.xlsx` | Yes | Yes | No |
| `/Volumes/Users/Anonymous/Workshop/202504161200UTC-4_Nancy_Baxter_Andrea_Tricco_collabs/2024-Historical-Highly-Cited-Researchers-lists - final/2024_HCR.xlsx` | Yes | Yes | No |
| `/Volumes/Users/Anonymous/Workshop/202504161200UTC-4_Nancy_Baxter_Andrea_Tricco_collabs/2024-Historical-Highly-Cited-Researchers-lists - final/~$2014_HCR.xlsx` | Yes | Yes | No |
| `/Volumes/Users/Anonymous/Workshop/202504161200UTC-4_Nancy_Baxter_Andrea_Tricco_collabs/2024-Historical-Highly-Cited-Researchers-lists - final/~$2020_HCR.xlsx` | Yes | Yes | No |
| `/Volumes/Users/Anonymous/Workshop/202504161200UTC-4_Nancy_Baxter_Andrea_Tricco_collabs/analyses/2026-01-02_enrich_full_df/data/samples/pilot_sample_2025-07-24.csv` | Yes | Yes | No |
| `/Volumes/Users/Anonymous/Workshop/202504161200UTC-4_Nancy_Baxter_Andrea_Tricco_collabs/analyses/2026-01-02_enrich_full_df/data/samples/random_samples_2025-08-18.csv` | Yes | Yes | No |
| `/Volumes/Users/Anonymous/Workshop/202504161200UTC-4_Nancy_Baxter_Andrea_Tricco_collabs/analyses/2026-01-02_enrich_full_df/data/samples/random_samples_2025-08-27.csv` | Yes | Yes | No |
| `/Volumes/Users/Anonymous/Workshop/202504161200UTC-4_Nancy_Baxter_Andrea_Tricco_collabs/analyses/2026-01-02_enrich_full_df/data/samples/random_samples_2025-09-23.csv` | Yes | Yes | No |
| `/Volumes/Users/Anonymous/Workshop/202504161200UTC-4_Nancy_Baxter_Andrea_Tricco_collabs/analyses/2026-01-02_enrich_full_df/data/samples/random_samples_2025-10-14.csv` | Yes | Yes | No |
| `/Volumes/Users/Anonymous/Workshop/202504161200UTC-4_Nancy_Baxter_Andrea_Tricco_collabs/analyses/2026-01-02_enrich_full_df/data/samples/random_samples_2025-10-24.csv` | Yes | Yes | No |
| `/Volumes/Users/Anonymous/Workshop/202504161200UTC-4_Nancy_Baxter_Andrea_Tricco_collabs/analyses/2026-01-02_enrich_full_df/data/samples/random_samples_2025-10-27.csv` | Yes | Yes | No |
| `/Volumes/Users/Anonymous/Workshop/202504161200UTC-4_Nancy_Baxter_Andrea_Tricco_collabs/analyses/2026-01-02_enrich_full_df/data/samples/random_samples_2025-11-04.csv` | Yes | Yes | No |
| `/Volumes/Users/Anonymous/Workshop/202504161200UTC-4_Nancy_Baxter_Andrea_Tricco_collabs/analyses/2026-01-02_enrich_full_df/data/samples/random_samples_2025-11-13.csv` | Yes | Yes | No |
| `/Volumes/Users/Anonymous/Workshop/202504161200UTC-4_Nancy_Baxter_Andrea_Tricco_collabs/analyses/2026-01-02_enrich_full_df/data/manual_extractions/RI_pilot_extraction_2025AUG19_HI (n=10)_fixed_space_norm_header.docx` | Yes | Yes | No |
| `/Volumes/Users/Anonymous/Workshop/202504161200UTC-4_Nancy_Baxter_Andrea_Tricco_collabs/analyses/2026-01-02_enrich_full_df/data/manual_extractions/RI_sample_1_2025AUG22_HI.docx` | Yes | Yes | No |
| `/Volumes/Users/Anonymous/Workshop/202504161200UTC-4_Nancy_Baxter_Andrea_Tricco_collabs/analyses/2026-01-02_enrich_full_df/data/manual_extractions/RI_sample_2_2025SEPT16_DR_fixed_names.docx` | Yes | Yes | No |
| `/Volumes/Users/Anonymous/Workshop/202504161200UTC-4_Nancy_Baxter_Andrea_Tricco_collabs/analyses/2026-01-02_enrich_full_df/data/manual_extractions/RI_sample_3_2025SEPT27_HI (n=40)_added_fei_wang.docx` | Yes | Yes | No |
| `/Volumes/Users/Anonymous/Workshop/202504161200UTC-4_Nancy_Baxter_Andrea_Tricco_collabs/analyses/2026-01-02_enrich_full_df/data/manual_extractions/RI_sample_4_2025OCT14_DR (n=40).docx` | Yes | Yes | No |
| `/Volumes/Users/Anonymous/Workshop/202504161200UTC-4_Nancy_Baxter_Andrea_Tricco_collabs/analyses/2026-01-02_enrich_full_df/data/manual_extractions/RI_sample_5_2025OCT24_DR (n=40)_clarified_nielsenlo.docx` | Yes | Yes | No |
| `/Volumes/Users/Anonymous/Workshop/202504161200UTC-4_Nancy_Baxter_Andrea_Tricco_collabs/analyses/2026-01-02_enrich_full_df/data/manual_extractions/RI_sample_6_2025NOV01_HI (n=40)_norm_header.docx` | Yes | Yes | No |
| `/Volumes/Users/Anonymous/Workshop/202504161200UTC-4_Nancy_Baxter_Andrea_Tricco_collabs/analyses/2026-01-02_enrich_full_df/data/manual_extractions/RI_sample_7_2025NOV04_DR (n=40).docx` | Yes | Yes | No |
| `/Volumes/Users/Anonymous/Workshop/202504161200UTC-4_Nancy_Baxter_Andrea_Tricco_collabs/analyses/2026-01-02_enrich_full_df/data/manual_extractions/RI_sample_8_2025NOV18_HI (n=40)_norm_header_fixed_names.docx` | Yes | Yes | No |
| `/Volumes/Users/Anonymous/Workshop/202504161200UTC-4_Nancy_Baxter_Andrea_Tricco_collabs/analyses/2026-01-02_enrich_full_df/data/OGHIST_2025_07_01.xlsx` | Yes | Yes | No |
| `/Users/anonymous/.codex/worktrees/c5ef/2026-01-02_enrich_full_df/resources/pandoc-custom-reference.docx` | Yes | Yes | Yes |
| `/Volumes/home/anonymous/sciscinet/v2/hf/xet/sciscinet_author_details.parquet` | Yes | Yes | No |
| `/Volumes/home/anonymous/sciscinet/v2/hf/xet/sciscinet_authors_paperid.parquet` | Yes | Yes | No |
| `/Volumes/home/anonymous/sciscinet/v2/hf/xet/hit_papers_level0.parquet` | Yes | Yes | No |
| `/Volumes/home/anonymous/sciscinet/v2/hf/xet/hit_papers_level1.parquet` | Yes | Yes | No |
| `/Volumes/home/anonymous/sciscinet/v2/hf/xet/sciscinet_fields.parquet` | Yes | Yes | No |

## Open questions / alignment

1. Should we add a `pixi run cov` task and make coverage gating part of CI (if any), or keep it optional? = **We add but keep it optional.**
2. For heavy integration tests, do you prefer:
   - **THIS ->>>** Local-only (skipped unless data files exist), or
   - A small checked-in synthetic dataset to keep CI deterministic?
3. Any preference on naming convention for test markers (e.g., `@pytest.mark.integration` / `@pytest.mark.slow`)? = **No preference.**
