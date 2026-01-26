# RFC 007: JSONL Enrichment (Residence/Education/etc.)

Timestamp: 2026-01-26T14:16:34Z

## Scope (Single Testable Unit)
Implement JSONL-based enrichment joined by `authorid`. All implementation lives under `./pkg_20260126_roadmap/`.

This RFC covers only JSONL ingestion and join logic; it does not include parquet enrichment or RDF export.

## Required Source of Truth (Must Reuse)
There is no prior implementation; use the roadmap definition in `.aicode/rfc/ROADMAP.md` for structure and validation gates. JSONL files must be joined by `authorid` *after* deduplication.

## Implementation Instructions (Must Follow)
1. **Input format**
   - Each JSONL file contains 1 row per researcher keyed by `authorid`.
2. **Join logic**
   - Join JSONL datasets to the matched/enriched dataframe using `authorid`.
   - Only matched rows should receive JSONL enrichment values.
3. **Determinism**
   - Ensure JSONL joins are deterministic and repeatable.

## Test Fixture Requirements
- Create small JSONL fixtures (e.g., residence, education) with 2–3 rows keyed by `authorid`.
- Include one JSONL row that does not match any author to confirm non-join behavior.

## Testing Requirements (Implement With This RFC)
### Unit Tests
- Verify JSONL read produces expected schema.
- Verify unmatched authors do not receive JSONL fields.

### Integration Tests
- Join JSONL fixtures to a small matched dataset and confirm output shape and column values.

### Regression Tests
- Freeze JSONL fixtures and compare enriched output hash to a golden file.

## Output Location
All new implementation for the roadmap must live under:
- `./pkg_20260126_roadmap/`
