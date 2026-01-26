# RFC 009: Candidate Generation (LONG Format)

Timestamp: 2026-01-26T14:16:34Z

## Scope (Single Testable Unit)
Generate candidate SciSciNet author matches in LONG format using DuckDB. All implementation lives under `./pkg_20260126_roadmap/`.

This RFC covers only candidate generation (matching names to author IDs) and output to `candidates.csv`.

## Required Source of Truth (Must Reuse)
- Name normalization and matching semantics from:
  - `./pkg_20251223_word_tables/src/name_utils.py` (`unify_first_last`)
- DuckDB connection and extensions from:
  - `./repl.py` (`PipelineManager.connect_db` installs `splink_udfs`)

## Implementation Instructions (Must Follow)
1. **Name preparation**
   - Apply `unify_first_last` to the merged CSV rows to obtain `ktp.first_name` and `ktp.last_name`.
2. **DuckDB candidate generation**
   - Join `csv_with_docx` to `author_details.parquet` using fuzzy name containment logic (same semantics as the sampler pipeline).
   - Use `splink_udfs` if available for improved similarity scoring.
3. **Ranking**
   - Rank candidates per `draw_number` in descending similarity order, and cap to a configurable max (e.g., 10).
4. **Output**
   - Export `candidates.csv` in LONG format with `draw_number`, `authorid`, `display_name`, `candidate_rank`, and confidence score if available.

## Test Fixture Requirements
- Create a minimal `author_details.parquet` with a few authors that include:
  - Unique matches
  - Ambiguous matches (same last name, different first names)

## Testing Requirements (Implement With This RFC)
### Unit Tests
- Verify ranking is deterministic and sorted by similarity.
- Verify LONG format output has multiple rows per draw.

### Integration Tests
- Generate candidates from fixture inputs and verify expected candidate counts per draw.

### Regression Tests
- Freeze fixture inputs and compare `candidates.csv` hash to a golden file.

## Output Location
All new implementation for the roadmap must live under:
- `./pkg_20260126_roadmap/`
