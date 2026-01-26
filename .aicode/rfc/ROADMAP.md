## Complete Pipeline Architecture

### 1. **The True Data Flow**

```
INPUTS (all verified by hash):
├─ XLSX files (HCR lists) - multiple files
├─ DOCX files (manual tables) - multiple files, NO unique IDs
├─ Parquet files (SciSciNet) - multiple files
├─ JSONL files (future) - multiple files, one info type per file
└─ Ontology file (TTL/RDF)

PHASE 1: EXTRACTION
├─ Sample XLSX → multiple CSV files (deterministic, seed=42)
│   Output: sample_2024-XX-XX.csv (20 rows)
│           sample_2024-YY-YY.csv (40 rows)
│           ... (total 310 rows across all files)
│
└─ Merge CSV files → single master CSV
    Output: merged_samples.csv (310 rows)
    Columns: [draw_number, hcr.filename, hcr.row_number, priority, hcr.first_name, hcr.last_name, ...]

PHASE 2: DOCX RECONSTRUCTION
├─ Parse all DOCX tables → docx_combined (310 rows total)
│   (Users created these manually, one DOCX row per CSV row, but forgot IDs)
│
└─ Fuzzy name matching to reconstruct 1:1 correspondence
    Algorithm: For each CSV row, find DOCX row where:
      - docx.combined_name CONTAINS csv.first_name AND
      - docx.combined_name CONTAINS csv.last_name AND
      - EXACTLY ONE match (else: error)
    
    Output: csv_with_docx (310 rows)
    Validation: COUNT(DISTINCT csv.draw_number) = 310
                COUNT(DISTINCT docx.row_id) = 310

PHASE 3: PARQUET CANDIDATE GENERATION
├─ Fuzzy match CSV names → SciSciNet author IDs
│   (May produce multiple candidates per CSV row)
│
└─ Generate candidates with metadata
    Output: candidates.csv (could be 310-3100 rows)
    Columns: [draw_number, csv_first_name, csv_last_name, 
              authorid, display_name, match_confidence,
              candidate_rank, ...]
    
    Structure: LONG format (multiple rows per draw_number)
    Example:
      draw_number=1, authorid=123, candidate_rank=1, confidence=0.95
      draw_number=1, authorid=456, candidate_rank=2, confidence=0.82
      draw_number=2, authorid=789, candidate_rank=1, confidence=0.88

[PIPELINE PAUSES - AWAITING MANUAL DEDUPLICATION]

User receives:
  - candidates.csv
  - Instructions: "Keep only confirmed matches, delete ambiguous ones"

User returns:
  - deduplicated.csv (≤310 rows, LONG format still okay)
  
Pipeline validates:
  1. Is subset of candidates.csv ✓
  2. Each draw_number appears AT MOST once ✓
  3. Only draw_numbers from original merged_samples.csv ✓
  
Pipeline derives final status for each CSV row:
  - If draw_number in deduplicated.csv → MATCHED (authorid assigned)
  - If draw_number NOT in deduplicated.csv → UNMATCHED (excluded from enrichment)

PHASE 4: ENRICHMENT (only for MATCHED rows)
├─ Join by authorid to other parquets:
│   ├─ author_papers → paper IDs
│   ├─ hit_papers → hit counts
│   └─ fields → field info
│
└─ Join by authorid to JSONL files (future):
    ├─ residence.jsonl (310 rows, one per draw_number)
    ├─ education.jsonl (310 rows, one per draw_number)
    └─ ... more as needed
    
    Output: enriched_final (≤310 rows, only MATCHED)
    Columns: [draw_number, hcr.*, docx.*, authorid, 
              paper_ids, hit_counts, field_ids,
              residence, education, ...]

PHASE 5: EXPORT (multiple formats from enriched_final)
├─ RDF formats (all from same graph):
│   ├─ .trig
│   ├─ .nquads
│   └─ .jsonld
│
└─ Card formats (one file per row in enriched_final):
    ├─ markdown-cards.zip (≤310 .txt files)
    └─ docx-cards.zip (≤310 .docx files via pandoc)
```

### 2. **Critical Architectural Insights**

**A. DOCX Matching is NOT Defensive - It’s Essential**

The fuzzy name matching recreates the lost deterministic mapping. This must:

- Run BEFORE candidate generation (Phase 2, not Phase 3)
- Be 100% successful (any failures = abort pipeline)
- Store the reconstructed mapping persistently

**B. Candidate Structure is LONG Format**

From the new module’s join logic, candidates.csv has:

- Multiple rows per original CSV row (one per candidate)
- Must be collapsed to at most one row per `draw_number` during deduplication
- Users delete unwanted rows, keeping their preferred match

**C. JSONL Files Mirror CSV Structure**

Each JSONL:

- Has exactly 310 rows (one per original sample)
- Keyed by `authorid` (after deduplication establishes mapping)
- Adds orthogonal enrichment (residence, education, etc.)
- Join is deterministic 1:1 after Phase 4

**D. The “Ultimate Selection” Concept**

When user deduplicates, some draw_numbers might have 5 candidates. User:

- Picks the “ultimate selection” (the correct match) → kept in deduplicated.csv
- Deletes the other 4 rows
- OR deletes all 5 rows if none are correct → draw_number disappears entirely

Pipeline must track both outcomes:

```python
matched_draws = set(deduplicated_df['draw_number'])
original_draws = set(merged_samples_df['draw_number'])
unmatched_draws = original_draws - matched_draws

status_df = pd.DataFrame({
    'draw_number': list(original_draws),
    'status': ['MATCHED' if d in matched_draws else 'UNMATCHED' 
               for d in original_draws],
    'authorid': [deduplicated_df[deduplicated_df['draw_number']==d]['authorid'].iloc[0]
                 if d in matched_draws else None
                 for d in original_draws]
})
```

### 3. **Revised DuckDB Schema**

```sql
-- Phase 1: Sampling (runs within pipeline now)
CREATE TABLE xlsx_sources AS 
    SELECT * FROM read_excel_multiple('input/*.xlsx');

CREATE TABLE sampled_rows AS
    SELECT *, ROW_NUMBER() OVER (ORDER BY random()) as draw_number
    FROM xlsx_sources
    WHERE <sampling logic with seed>;

-- Phase 1b: Merge historical samples
CREATE TABLE merged_samples AS
    SELECT * FROM read_csv('input/sample_*.csv');

-- Phase 2: DOCX reconstruction
CREATE TABLE docx_parsed AS
    SELECT ROW_NUMBER() OVER () as docx_row_id, *
    FROM read_csv('temp/docx_parsed.csv');  -- from python-docx parsing

CREATE TABLE docx_match_attempts AS
    SELECT 
        csv.draw_number,
        csv.first_name as csv_first,
        csv.last_name as csv_last,
        docx.docx_row_id,
        docx.combined_name as docx_name,
        -- Similarity scoring
        (LOWER(docx.combined_name) LIKE '%' || LOWER(csv.first_name) || '%')::int +
        (LOWER(docx.combined_name) LIKE '%' || LOWER(csv.last_name) || '%')::int 
        as match_score
    FROM merged_samples csv
    CROSS JOIN docx_parsed docx
    WHERE match_score = 2;  -- Both names must match

-- Validation: ensure 1:1
CREATE TABLE docx_validation AS
    SELECT draw_number, COUNT(*) as match_count
    FROM docx_match_attempts
    GROUP BY draw_number
    HAVING match_count != 1;

-- If docx_validation is empty, proceed:
CREATE TABLE csv_with_docx AS
    SELECT 
        csv.*,
        docx.* EXCLUDE (docx_row_id, combined_name)
    FROM merged_samples csv
    JOIN docx_match_attempts dma ON csv.draw_number = dma.draw_number
    JOIN docx_parsed docx ON dma.docx_row_id = docx.docx_row_id;

-- Phase 3: Candidate generation
CREATE TABLE author_candidates AS
    SELECT 
        csv.draw_number,
        csv.first_name,
        csv.last_name,
        auth.authorid,
        auth.display_name,
        ROW_NUMBER() OVER (
            PARTITION BY csv.draw_number 
            ORDER BY <similarity_metric> DESC
        ) as candidate_rank
    FROM csv_with_docx csv
    JOIN read_parquet('parquets/author_details.parquet') auth
        ON LOWER(UNACCENT(auth.display_name)) LIKE '%' || LOWER(csv.first_name) || '%'
        AND LOWER(UNACCENT(auth.display_name)) LIKE '%' || LOWER(csv.last_name) || '%'
    WHERE candidate_rank <= 10;  -- Max 10 candidates per row

-- Export candidates.csv
COPY author_candidates TO 'output/candidates.csv';

-- [MANUAL DEDUPLICATION]

-- Phase 4: Load deduplicated
CREATE TABLE deduplicated AS
    SELECT * FROM read_csv('input/deduplicated.csv');

-- Validation
CREATE TABLE dedupe_validation AS
    SELECT 
        COUNT(DISTINCT draw_number) as unique_draws,
        COUNT(*) as total_rows,
        (COUNT(*) = COUNT(DISTINCT draw_number))::int as is_one_to_one
    FROM deduplicated;

-- Must pass: is_one_to_one = 1

-- Create status tracking
CREATE TABLE draw_status AS
    SELECT 
        orig.draw_number,
        COALESCE(ded.authorid, NULL) as authorid,
        CASE 
            WHEN ded.authorid IS NOT NULL THEN 'MATCHED'
            ELSE 'UNMATCHED'
        END as status
    FROM merged_samples orig
    LEFT JOIN deduplicated ded ON orig.draw_number = ded.draw_number;

-- Phase 4: Enrichment (only MATCHED)
CREATE TABLE enriched_final AS
    SELECT 
        st.draw_number,
        st.authorid,
        csv.*, 
        papers.paperid,
        hits.hit_1pct,
        fields.field_name,
        res.residence,  -- from residence.jsonl
        edu.education   -- from education.jsonl
    FROM draw_status st
    JOIN csv_with_docx csv ON st.draw_number = csv.draw_number
    LEFT JOIN read_parquet('parquets/author_papers.parquet') papers 
        ON st.authorid = papers.authorid
    LEFT JOIN read_parquet('parquets/hit_papers.parquet') hits 
        ON papers.paperid = hits.paperid
    LEFT JOIN read_parquet('parquets/fields.parquet') fields 
        ON hits.fieldid = fields.id
    LEFT JOIN read_json('jsonl/residence.jsonl') res 
        ON st.authorid = res.authorid
    LEFT JOIN read_json('jsonl/education.jsonl') edu 
        ON st.authorid = edu.authorid
    WHERE st.status = 'MATCHED';

-- Export
COPY enriched_final TO 'output/enriched_final.csv';
```

### 4. **JSONL Integration Details**

Since each JSONL has 310 rows (one per researcher):

```jsonl
// residence.jsonl
{"authorid": "A123", "country": "Canada", "city": "Toronto"}
{"authorid": "A456", "country": "USA", "city": "Boston"}
...
(310 lines total)

// education.jsonl
{"authorid": "A123", "degree": "PhD", "institution": "MIT"}
{"authorid": "A456", "degree": "PhD", "institution": "Stanford"}
...
(310 lines total)
```

DuckDB join:

```sql
LEFT JOIN read_json_auto('residence.jsonl') res 
    ON enriched.authorid = res.authorid
```

If a draw_number is UNMATCHED (no authorid), it won’t join to any JSONL data.

### 5. **Sampling Integration**

The sampling code becomes `core/ingestion/xlsx_sampler.py`:

```python
class XLSXSampler:
    def __init__(self, seed=42):
        self.rng = np.random.default_rng(seed)
        self.draw_count = 0
    
    def sample(self, xlsx_dir: Path, n: int, output_path: Path):
        """Sample n rows from XLSX files."""
        # Load all XLSX
        # Apply sampling logic
        # Increment draw_count
        # Save to output_path
        pass
    
    def merge_samples(self, sample_dir: Path, output_path: Path):
        """Merge all historical sample CSVs."""
        samples = list(sample_dir.glob("sample_*.csv"))
        df = pd.concat([pd.read_csv(s) for s in sorted(samples)])
        df.to_csv(output_path, index=False)
```

**User workflow:**

**Option A: Start fresh**

```bash
sciscinet sample --xlsx-dir data/hcr_lists/ --n 40 --output samples/sample_2025-01-20.csv
```

**Option B: Use existing samples**

```bash
sciscinet run --sample-dir samples/  # merges all sample_*.csv
```

### 6. **Pipeline State Machine**

```python
class PipelineState(Enum):
    INIT = "init"
    FILES_VERIFIED = "files_verified"
    SAMPLES_MERGED = "samples_merged"
    DOCX_MATCHED = "docx_matched"
    CANDIDATES_GENERATED = "candidates_generated"
    AWAITING_DEDUPE = "awaiting_deduplication"
    DEDUPE_LOADED = "dedupe_loaded"
    ENRICHMENT_COMPLETE = "enrichment_complete"
    EXPORTED = "exported"
```

Transitions:

```
INIT → verify_files() → FILES_VERIFIED
FILES_VERIFIED → merge_samples() → SAMPLES_MERGED
SAMPLES_MERGED → match_docx() → DOCX_MATCHED
DOCX_MATCHED → generate_candidates() → CANDIDATES_GENERATED
CANDIDATES_GENERATED → export_candidates() → AWAITING_DEDUPE

[USER MANUAL WORK]

AWAITING_DEDUPE → load_deduplicated() → DEDUPE_LOADED
DEDUPE_LOADED → enrich() → ENRICHMENT_COMPLETE
ENRICHMENT_COMPLETE → export() → EXPORTED
```

### 7. **Validation Gates**

Each transition has validation:

**Before DOCX_MATCHED:**

```python
def validate_docx_matching():
    result = conn.execute("SELECT * FROM docx_validation").df()
    if not result.empty:
        failures = result['draw_number'].tolist()
        raise ValueError(f"DOCX matching failed for draw_numbers: {failures}")
```

**Before DEDUPE_LOADED:**

```python
def validate_deduplicated(dedupe_path, candidates_path):
    dedupe = pd.read_csv(dedupe_path)
    candidates = pd.read_csv(candidates_path)
    
    # Check 1: Subset
    assert set(dedupe['draw_number']).issubset(set(candidates['draw_number']))
    
    # Check 2: One per draw_number
    assert len(dedupe) == dedupe['draw_number'].nunique()
    
    # Check 3: All from original samples
    original = pd.read_csv('data/merged_samples.csv')
    assert set(dedupe['draw_number']).issubset(set(original['draw_number']))
```

### 8. **Streamlit UI - Phase Navigation**

```
┌─────────────────────────────────────────────────────┐
│ Phase: [✓ Verify] → [✓ Merge] → [⚠ Match DOCX]     │
└─────────────────────────────────────────────────────┘

Current: Matching DOCX tables to CSV rows...

Progress: ████████████████░░░░ 78% (242/310 matched)

Issues Found:
  • Draw #45: No match for "Smith, John"
  • Draw #127: Multiple matches for "Lee, Wei"

[View Details] [Abort] [Skip & Continue]
```

### 9. **CLI Commands - Complete Set**

```bash
# Setup
sciscinet init --config myproject.json  # Creates template config

# Sampling (optional, if starting fresh)
sciscinet sample --xlsx-dir data/hcr/ --n 40 --seed 42

# Main pipeline
sciscinet run                            # Runs until AWAITING_DEDUPE
sciscinet run --resume-with dedupe.csv  # Continues from DEDUPE_LOADED

# Individual phases (for debugging)
sciscinet verify-files
sciscinet merge-samples
sciscinet match-docx
sciscinet generate-candidates

# Deduplication helpers
sciscinet dedupe status              # Shows where we are
sciscinet dedupe validate dedupe.csv # Checks file before loading

# Export
sciscinet export --formats trig,markdown-cards

# Utilities
sciscinet status        # Show current state
sciscinet reset         # Clear all state, keep data
sciscinet reset --hard  # Delete everything
```

### 10. **File Organization**

```
project/
├─ config.json          # User configuration
├─ data/
│   ├─ scisci_process.duckdb     # All tables
│   ├─ pipeline_state.json       # Current phase
│   ├─ merged_samples.csv        # Phase 1 output
│   ├─ candidates.csv            # Phase 3 output
│   ├─ deduplicated.csv          # User provides
│   └─ enriched_final.csv        # Phase 4 output
├─ input/
│   ├─ hcr_lists/
│   │   └─ *.xlsx
│   ├─ docx_tables/
│   │   └─ *.docx
│   ├─ parquets/
│   │   └─ *.parquet
│   ├─ jsonl/
│   │   └─ *.jsonl
│   └─ ontology.ttl
├─ samples/              # Historical samples (optional)
│   ├─ sample_2024-XX-XX.csv
│   └─ sample_2024-YY-YY.csv
└─ output/
    ├─ enriched_data.trig
    ├─ enriched_data.nquads
    ├─ enriched_data.jsonld
    ├─ researcher_cards.zip (markdown)
    └─ researcher_cards.zip (docx)
```

### 11. **Key Architectural Principles**

1. **Sampling is now part of the pipeline** (not pre-processing)
1. **DOCX matching is Phase 2** (before candidates, not after)
1. **Candidates are LONG format** (multiple rows per draw_number)
1. **Deduplication produces at most 310 rows** (one per draw_number)
1. **Status tracking preserves UNMATCHED** (for audit trail)
1. **JSONL joins are deterministic** (by authorid, after dedupe)
1. **All joins in DuckDB** (no pandas matching)
1. **Validation at every gate** (pipeline aborts on failures)

### 12. **Open Questions Resolved**

✅ Candidates structure: LONG format, validated
✅ Name matching: Essential, not defensive
✅ JSONL: By authorid, 310 rows per file
✅ Sampling: Integrated into pipeline
