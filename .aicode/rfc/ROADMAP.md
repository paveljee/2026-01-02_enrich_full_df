# Pipeline Roadmap (Root: `./pkg_20260126_roadmap/`)

Timestamp: 2026-01-26T14:16:34Z

## 1) Root Project Location
All roadmap implementation work must live under:
- `./pkg_20260126_roadmap/`

This includes new CLI commands, DuckDB pipelines, CSV merging logic, enrichment steps, and exports.

## 2) Existing Code That Must Be Reused (Minimal Changes Only)
The roadmap *must* reuse the existing code and logic below. Do not change logic or comments unless strictly necessary for integration.

### Sampling
Upstream references to fetch during implementation (implementers must fetch and preserve these files verbatim):
- https://github.com/paveljee/research-integrity-ktp/blob/analysis/2025-08-19-sampler/analyses/2025-08-19_sampler/sampler.py
- https://github.com/paveljee/research-integrity-ktp/blob/analysis/2025-12-23_pilot_sampler/analyses/2025-12-23_pilot_sampler/pilot_sampler.py

### CSV Merge + DOCX Logic + Cards
- CSV validation/merge, DOCX parsing, card export: `./pkg_20251223_word_tables/src/cli.py`
- Name utilities and name matching logic: `./pkg_20251223_word_tables/src/name_utils.py`
- Column constants (including `RIGHT_NAME_COL`): `./pkg_20251223_word_tables/src/_vars.py`
- Schema example (full_df): `./pkg_20251223_word_tables/tests/test_unify_names.py::hcr_row`

### Parquet Enrichment
- Enrichment REPL and file verification: `./repl.py`

Supplemental schema references for test fixtures:
- https://github.com/paveljee/research-integrity-ktp/blob/v0.1.0-pilot.1751566592/test_run_outputs/test_run_report.md

### Minimal RDF Reference
- https://github.com/paveljee/research-integrity-ktp/blob/v0.1.0-pilot.1751566592/test_run.py

## 3) Pipeline Phases and RFC Mapping
Each RFC is a **single testable unit** and must include unit/integration/regression tests.

1. **Main XLSX Sampling** → RFC 001
2. **Pilot XLSX Sampling** → RFC 002
3. **Merge & Validate CSVs** → RFC 003
4. **DOCX Parse + DuckDB Name Match** → RFC 004
5. **Card Generation (Markdown/DOCX)** → RFC 005
6. **Parquet Enrichment** → RFC 006
7. **JSONL Enrichment** → RFC 007
8. **RDF Export (Minimal)** → RFC 008
9. **Candidate Generation (LONG)** → RFC 009
10. **Deduplication + Status Tracking** → RFC 010

## 4) Key Architectural Requirements (Must Hold)
- Sampling is part of the pipeline and must preserve deterministic draw numbering.
- Docx matching must occur **before** candidate generation and must be 100% successful or abort.
- Candidates (if implemented later) are LONG format; deduplication collapses to ≤1 row per draw.
- JSONL joins must occur only after deduplication and be deterministic by `authorid`.
- All joins should be done in DuckDB (name matching is ported from Python semantics).
- Validation gates must be enforced between phases.

## 5) High-Level Data Flow (Reference)
```
INPUTS (all verified by hash):
├─ XLSX files (HCR lists) - multiple files
├─ DOCX files (manual tables) - multiple files, NO unique IDs
├─ Parquet files (SciSciNet) - multiple files
├─ JSONL files (future) - multiple files, one info type per file
└─ Ontology file (TTL/RDF)

PHASE 1: XLSX sampling → sample_*.csv
PHASE 1b: Merge samples → merged_samples.csv
PHASE 2: DOCX reconstruction → csv_with_docx
PHASE 3: Candidate generation (future) → candidates.csv
[MANUAL DEDUPLICATION]
PHASE 4: Enrichment (parquet + JSONL) → enriched_final
PHASE 5: Export → RDF + cards
```

## 6) Validation Gates (Examples)
- DOCX matching must produce exactly one match per CSV row; otherwise abort.
- Deduplication must be subset of candidates and unique per draw.
- Enrichment only applies to matched rows.

## 7) CLI Commands (Target)
Commands should mirror existing workflows, but operate in `./pkg_20260126_roadmap/`:
```
sciscinet sample --xlsx-dir data/hcr/ --n 40 --seed 42
sciscinet pilot --xlsx-dir data/hcr/ --names triples.json
sciscinet merge-samples --sample-dir samples/
sciscinet match-docx --docx-dir input/docx/
sciscinet enrich --parquet-dir input/parquet/ --jsonl-dir input/jsonl/
sciscinet export --formats trig,markdown-cards
```

## 8) Output Layout (Target)
```
./pkg_20260126_roadmap/
├─ config.json
├─ data/
│  ├─ scisci_process.duckdb
│  ├─ merged_samples.csv
│  ├─ candidates.csv
│  └─ enriched_final.csv
├─ input/
│  ├─ hcr_lists/
│  ├─ docx_tables/
│  ├─ parquets/
│  ├─ jsonl/
│  └─ ontology.ttl
└─ output/
   ├─ enriched_data.trig
   ├─ enriched_data.nquads
   ├─ enriched_data.jsonld
   ├─ researcher_cards.zip (markdown)
   └─ researcher_cards.zip (docx)
```
